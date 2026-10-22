"""Entrar pelo nome e pedir cadastro (fase 17).

A pessoa digita o nome e o PIN. Quem ainda não está no Hub faz um pedido de cadastro, já com o PIN
que escolheu, e só entra depois que um administrador aprova. Num Hub vazio, o primeiro cadastro já
nasce administrador (é a única forma de alguém conseguir gerenciar o Hub).
"""

import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta

from .access import ROLES, check_pin_format, hash_pin, require_admin
from .db import Database, log_event
from .people import PALETTE, Person, ValidationError, _default_initials, _row, _validate

MAX_PENDING = 5
EXPIRE_DAYS = 7
SIGNUP_ROLES = ("analista", "assistente")  # gestor e administrador só depois, em Pessoas


def name_key(name: str) -> str:
    """O nome do jeito que se compara: sem acento, sem maiúscula e sem espaço sobrando ("ana  sOUZA" = "Ana Souza")."""
    plain = unicodedata.normalize("NFKD", name or "")
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def find_by_name(db: Database, name: str) -> Person | None:
    """A pessoa ativa com esse nome (sem diferença de acento e maiúscula)."""
    key = name_key(name)
    if not key:
        return None
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM people WHERE active = 1").fetchall()
    return next((_row(r) for r in rows if name_key(r["name"]) == key), None)


def hub_is_empty(db: Database) -> bool:
    with db.connect() as conn:
        return conn.execute("SELECT 1 FROM people").fetchone() is None


# ---------- pedidos de cadastro ----------

@dataclass(frozen=True)
class Signup:
    id: int
    name: str
    initials: str
    created_at: datetime


def _clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if len(name) < 2:
        raise ValidationError("Informe o seu nome.")
    if len(name) > 60:
        raise ValidationError("Nome muito comprido (até 60 letras).")
    if not re.fullmatch(r"[A-Za-zÀ-ÿ' .-]+", name):
        raise ValidationError("Use só letras no nome.")
    return name


def _check_new_person(conn, name: str, initials: str, pin: str, confirm: str) -> str:
    """Confere nome, iniciais e PIN de um cadastro novo e devolve as iniciais certas."""
    initials = (initials.strip() or _default_initials(name)).upper()
    check_pin_format(pin)
    if pin != confirm:
        raise ValidationError("Os dois PINs não são iguais.")
    key = name_key(name)
    for r in conn.execute("SELECT name, active FROM people"):
        if name_key(r["name"]) == key:
            if r["active"]:
                raise ValidationError("Você já tem cadastro: volte e entre com o seu nome e PIN.")
            raise ValidationError("Esse nome já foi do Hub. Peça a um administrador para reativar.")
    _validate(conn, name, initials, PALETTE[0], None)
    return initials


def _purge(conn, now: datetime) -> None:
    limit = (now - timedelta(days=EXPIRE_DAYS)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM signup_requests WHERE created_at < ?", (limit,))


def request_signup(db: Database, now: datetime, name: str, initials: str, pin: str, confirm: str) -> Signup:
    """Pedido de cadastro: fica esperando um administrador. O PIN já vai guardado (só o resumo, como sempre)."""
    name = _clean_name(name)
    with db.connect() as conn:
        _purge(conn, now)
        initials = _check_new_person(conn, name, initials, pin, confirm)
        pending = conn.execute("SELECT name FROM signup_requests").fetchall()
        if any(name_key(r["name"]) == name_key(name) for r in pending):
            raise ValidationError("Já existe um pedido com esse nome esperando aprovação.")
        if len(pending) >= MAX_PENDING:
            raise ValidationError("Já há muitos pedidos esperando aprovação. Peça a um administrador para olhar.")
        cur = conn.execute("INSERT INTO signup_requests(name, initials, pin_hash, created_at) VALUES (?, ?, ?, ?)",
                           (name, initials, hash_pin(pin), now.isoformat(timespec="seconds")))
        log_event(conn, now, None, "cadastro_pedido", f"pedido:{cur.lastrowid}", name)
    return Signup(cur.lastrowid, name, initials, now)


def pending(db: Database, now: datetime) -> list[Signup]:
    with db.connect() as conn:
        _purge(conn, now)
        rows = conn.execute("SELECT * FROM signup_requests ORDER BY created_at, id").fetchall()
    return [Signup(r["id"], r["name"], r["initials"], datetime.fromisoformat(r["created_at"])) for r in rows]


def is_pending(db: Database, now: datetime, name: str) -> bool:
    return any(name_key(s.name) == name_key(name) for s in pending(db, now))


def approve(db: Database, now: datetime, actor: Person, request_id: int, role: str = "analista") -> Person:
    """O administrador aprova: a pessoa passa a existir, com o PIN que escolheu no pedido."""
    require_admin(actor)
    if role not in SIGNUP_ROLES:
        raise ValidationError("Papel inválido para um cadastro novo.")
    with db.connect() as conn:
        _purge(conn, now)
        req = conn.execute("SELECT * FROM signup_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            raise ValidationError("Esse pedido não existe mais (pode ter vencido depois de 7 dias).")
        key = name_key(req["name"])
        if any(name_key(r["name"]) == key for r in conn.execute("SELECT name FROM people")):
            raise ValidationError(f"Já existe alguém chamado {req['name']} no Hub. Recuse o pedido.")
        used = {r[0] for r in conn.execute("SELECT color FROM people WHERE active = 1")}
        color = next((c for c in PALETTE if c not in used), PALETTE[0])
        cur = conn.execute("INSERT INTO people(name, initials, color, role, pin_hash) VALUES (?, ?, ?, ?, ?)",
                           (req["name"], req["initials"], color, role, req["pin_hash"]))
        conn.execute("DELETE FROM signup_requests WHERE id = ?", (request_id,))
        log_event(conn, now, actor.id, "cadastro_aprovado", f"pessoa:{cur.lastrowid}", ROLES[role])
        return _row(conn.execute("SELECT * FROM people WHERE id = ?", (cur.lastrowid,)).fetchone())


def reject(db: Database, now: datetime, actor: Person, request_id: int) -> None:
    require_admin(actor)
    with db.connect() as conn:
        req = conn.execute("SELECT name FROM signup_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            raise ValidationError("Esse pedido não existe mais.")
        conn.execute("DELETE FROM signup_requests WHERE id = ?", (request_id,))
        log_event(conn, now, actor.id, "cadastro_recusado", f"pedido:{request_id}", req["name"])


def create_first_admin(db: Database, now: datetime, name: str, initials: str, pin: str, confirm: str) -> Person:
    """Hub vazio (instalação nova): quem se cadastra primeiro entra direto, já como administrador."""
    name = _clean_name(name)
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM people").fetchone() is not None:
            raise ValidationError("O Hub já tem gente cadastrada: peça o cadastro a um administrador.")
        initials = _check_new_person(conn, name, initials, pin, confirm)
        cur = conn.execute("INSERT INTO people(name, initials, color, is_admin, pin_hash) VALUES (?, ?, ?, 1, ?)",
                           (name, initials, PALETTE[0], hash_pin(pin)))
        log_event(conn, now, cur.lastrowid, "pessoa_criada", f"pessoa:{cur.lastrowid}", name)
        log_event(conn, now, cur.lastrowid, "admin_definido", f"pessoa:{cur.lastrowid}", "primeiro acesso")
        return _row(conn.execute("SELECT * FROM people WHERE id = ?", (cur.lastrowid,)).fetchone())


# ---------- limite por aparelho ----------

class DeviceLimiter:
    """Conta os erros de cada aparelho (pelo endereço na rede), em qualquer nome.

    O bloqueio por nome (5 erros) não segura quem vai trocando de nome; este segura. Fica só na memória:
    reiniciar o Hub zera a contagem, o que não tem problema para o tamanho da sala.
    """

    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, device: str, now_ts: float) -> list[float]:
        recent = [t for t in self._hits.get(device, []) if now_ts - t < self.window]
        if recent:
            self._hits[device] = recent
        else:
            self._hits.pop(device, None)
        return recent

    def wait_minutes(self, device: str, now_ts: float | None = None) -> int:
        """0 = pode tentar; senão, quantos minutos faltam para o aparelho poder tentar de novo."""
        ts = time.time() if now_ts is None else now_ts
        with self._lock:
            recent = self._recent(device, ts)
            if len(recent) < self.max_failures:
                return 0
            free_at = recent[-self.max_failures] + self.window
            return max(1, int((free_at - ts + 59) // 60))

    def hit(self, device: str, now_ts: float | None = None) -> None:
        ts = time.time() if now_ts is None else now_ts
        with self._lock:
            self._hits[device] = self._recent(device, ts) + [ts]
