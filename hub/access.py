"""Quem pode entrar e fazer o quê: PIN, sessões do dia, papéis e administradores."""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, time, timedelta

from .db import Database, log_event
from .people import Person, ValidationError, get_person

ROLES = {"analista": "Analista", "assistente": "Assistente", "gestor": "Gestor"}
MAX_ATTEMPTS = 5
LOCK_MINUTES = 5
PBKDF2_ROUNDS = 200_000


# ---------- PIN ----------

def check_pin_format(pin: str) -> None:
    if not re.fullmatch(r"\d{4,6}", pin or ""):
        raise ValidationError("O PIN tem de 4 a 6 números.")


def hash_pin(pin: str) -> str:
    """Só o resumo vai para o banco, com um sal diferente para cada pessoa: o PIN em si nunca é guardado."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def pin_matches(pin: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        attempt = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(rounds))
    except ValueError:
        return False
    return hmac.compare_digest(attempt.hex(), digest)


def _promote_first_admin(conn, now: datetime, person_id: int) -> None:
    # sem nenhum administrador (instalação nova ou logo depois da atualização da v1),
    # quem cria o primeiro PIN vira administrador, para alguém conseguir gerenciar o Hub
    if conn.execute("SELECT 1 FROM people WHERE is_admin = 1 AND active = 1").fetchone() is None:
        conn.execute("UPDATE people SET is_admin = 1 WHERE id = ?", (person_id,))
        log_event(conn, now, person_id, "admin_definido", f"pessoa:{person_id}", "primeiro acesso")


def create_pin(db: Database, now: datetime, person_id: int, pin: str, confirm: str) -> None:
    """Primeiro acesso (ou depois de um administrador redefinir): a pessoa cria o próprio PIN."""
    check_pin_format(pin)
    if pin != confirm:
        raise ValidationError("Os dois PINs não são iguais.")
    with db.connect() as conn:
        row = conn.execute("SELECT pin_hash, active FROM people WHERE id = ?", (person_id,)).fetchone()
        if row is None or not row["active"]:
            raise ValidationError("Pessoa não encontrada.")
        if row["pin_hash"] is not None:
            raise ValidationError("Essa pessoa já tem PIN. Peça a um administrador para redefinir.")
        conn.execute("UPDATE people SET pin_hash = ?, failed_pins = 0, locked_until = NULL WHERE id = ?",
                     (hash_pin(pin), person_id))
        log_event(conn, now, person_id, "pin_criado", f"pessoa:{person_id}", "")
        _promote_first_admin(conn, now, person_id)


def change_pin(db: Database, now: datetime, person_id: int, current: str, pin: str, confirm: str) -> None:
    check_pin_format(pin)
    if pin != confirm:
        raise ValidationError("Os dois PINs novos não são iguais.")
    with db.connect() as conn:
        row = conn.execute("SELECT pin_hash FROM people WHERE id = ?", (person_id,)).fetchone()
        if row is None or row["pin_hash"] is None or not pin_matches(current, row["pin_hash"]):
            raise ValidationError("O PIN atual não confere.")
        conn.execute("UPDATE people SET pin_hash = ? WHERE id = ?", (hash_pin(pin), person_id))
        log_event(conn, now, person_id, "pin_trocado", f"pessoa:{person_id}", "")


def verify_pin(db: Database, now: datetime, person_id: int, pin: str) -> None:
    """Confere o PIN. Depois de 5 erros seguidos, aquele nome fica bloqueado por alguns minutos."""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM people WHERE id = ? AND active = 1", (person_id,)).fetchone()
        if row is None or row["pin_hash"] is None:
            raise ValidationError("Pessoa não encontrada.")
        if row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now:
            until = datetime.fromisoformat(row["locked_until"])
            raise ValidationError(f"Muitas tentativas erradas. Tente de novo depois das {until:%H:%M}.")
        if pin_matches(pin, row["pin_hash"]):
            conn.execute("UPDATE people SET failed_pins = 0, locked_until = NULL WHERE id = ?", (person_id,))
            return
        # o erro sai depois do "with": levantar lá dentro desfaria a contagem de tentativas
        failed = row["failed_pins"] + 1
        if failed >= MAX_ATTEMPTS:
            until = now + timedelta(minutes=LOCK_MINUTES)
            conn.execute("UPDATE people SET failed_pins = 0, locked_until = ? WHERE id = ?",
                         (until.isoformat(timespec="seconds"), person_id))
            log_event(conn, now, None, "pin_bloqueado", f"pessoa:{person_id}", "")
            message = f"PIN errado {MAX_ATTEMPTS} vezes. Bloqueado até as {until:%H:%M}."
        else:
            conn.execute("UPDATE people SET failed_pins = ? WHERE id = ?", (failed, person_id))
            left = MAX_ATTEMPTS - failed
            message = f"PIN errado. Mais {left} tentativa{'s' if left > 1 else ''} antes de bloquear."
    raise ValidationError(message)


def reset_pin(db: Database, now: datetime, actor: Person, person_id: int) -> None:
    """Esqueceu o PIN: um administrador apaga, e a pessoa cria um novo no próximo acesso."""
    require_admin(actor)
    with db.connect() as conn:
        conn.execute("UPDATE people SET pin_hash = NULL, failed_pins = 0, locked_until = NULL WHERE id = ?",
                     (person_id,))
        conn.execute("DELETE FROM sessions WHERE person_id = ?", (person_id,))
        log_event(conn, now, actor.id, "pin_redefinido", f"pessoa:{person_id}", "")


# ---------- sessões ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_end(now: datetime) -> datetime:
    """A sessão vale o dia de trabalho e acaba à meia-noite."""
    return datetime.combine(now.date() + timedelta(days=1), time.min)


def start_session(db: Database, now: datetime, person_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(timespec="seconds"),))
        conn.execute("INSERT INTO sessions(token_hash, person_id, expires_at) VALUES (?, ?, ?)",
                     (_token_hash(token), person_id, session_end(now).isoformat(timespec="seconds")))
        log_event(conn, now, person_id, "entrou", f"pessoa:{person_id}", "")
    return token


def session_person(db: Database, now: datetime, token: str | None) -> Person | None:
    if not token:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT person_id FROM sessions WHERE token_hash = ? AND expires_at > ?",
                           (_token_hash(token), now.isoformat(timespec="seconds"))).fetchone()
    if row is None:
        return None
    person = get_person(db, row["person_id"])
    return person if person and person.active and person.has_pin else None


def end_session(db: Database, token: str | None) -> None:
    if token:
        with db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


# ---------- papéis ----------

def require_admin(actor: Person | None) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")


def has_admin(db: Database) -> bool:
    with db.connect() as conn:
        return conn.execute("SELECT 1 FROM people WHERE is_admin = 1 AND active = 1").fetchone() is not None


def set_access(db: Database, now: datetime, actor: Person, person_id: int, role: str, is_admin: bool) -> None:
    """Muda o papel (analista, assistente ou gestor) e a marcação de administrador. Sempre sobra um administrador.

    Assistente não tem pasta própria: ao virar assistente, a pessoa sai das pastas que tinha.
    """
    require_admin(actor)
    if role not in ROLES:
        raise ValidationError("Papel inválido.")
    with db.connect() as conn:
        row = conn.execute("SELECT name, role, is_admin FROM people WHERE id = ? AND active = 1", (person_id,)).fetchone()
        if row is None:
            raise ValidationError("Pessoa não encontrada.")
        if row["is_admin"] and not is_admin:
            others = conn.execute("SELECT COUNT(*) FROM people WHERE is_admin = 1 AND active = 1 AND id != ?",
                                  (person_id,)).fetchone()[0]
            if others == 0:
                raise ValidationError("O Hub precisa de pelo menos um administrador.")
        if row["role"] != role:
            conn.execute("UPDATE people SET role = ? WHERE id = ?", (role, person_id))
            log_event(conn, now, actor.id, "papel_alterado", f"pessoa:{person_id}", ROLES[role])
            if role == "assistente":
                conn.execute("DELETE FROM person_folders WHERE person_id = ?", (person_id,))
        if bool(row["is_admin"]) != is_admin:
            conn.execute("UPDATE people SET is_admin = ? WHERE id = ?", (int(is_admin), person_id))
            log_event(conn, now, actor.id, "admin_alterado", f"pessoa:{person_id}", "sim" if is_admin else "não")
