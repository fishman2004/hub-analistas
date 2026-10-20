"""As pessoas da equipe: nome, iniciais e a cor que as identifica na TV."""

import re
from dataclasses import dataclass
from datetime import datetime

from .db import Database, log_event

# cores bem diferentes entre si e legíveis sobre o fundo escuro da TV
PALETTE = ("#7FB2E5", "#F0B24A", "#E8A3C4", "#9AD48F", "#C8A7F0", "#F2867A", "#6FD3D0", "#E6D36B")


class ValidationError(ValueError):
    """Erro de preenchimento, com a mensagem pronta para mostrar na tela."""


@dataclass(frozen=True)
class Person:
    id: int
    name: str
    initials: str
    color: str
    active: bool
    role: str = "analista"
    is_admin: bool = False
    has_pin: bool = False

    @property
    def is_manager(self) -> bool:
        return self.role == "gestor"


def _row(r) -> Person:
    return Person(r["id"], r["name"], r["initials"], r["color"], bool(r["active"]),
                  r["role"], bool(r["is_admin"]), r["pin_hash"] is not None)


def _default_initials(name: str) -> str:
    return "".join(w[0] for w in name.split()[:2]).upper()


def _validate(conn, name: str, initials: str, color: str, person_id: int | None) -> None:
    if not name:
        raise ValidationError("Informe o nome.")
    if not re.fullmatch(r"[A-Za-zÀ-ÿ]{1,3}", initials):
        raise ValidationError("Use de 1 a 3 letras nas iniciais.")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise ValidationError("Cor inválida.")
    clash = conn.execute("SELECT id FROM people WHERE lower(name) = lower(?) AND id IS NOT ?", (name, person_id)).fetchone()
    if clash:
        raise ValidationError("Já existe alguém com esse nome.")


def add_person(db: Database, now: datetime, actor_id: int | None, name: str, initials: str = "", color: str = "") -> Person:
    name = " ".join(name.split())
    with db.connect() as conn:
        # quem foi desativado volta com o mesmo cadastro (e o mesmo histórico), em vez de ser recusado
        old = conn.execute("SELECT id FROM people WHERE lower(name) = lower(?) AND active = 0", (name,)).fetchone()
        if old:
            conn.execute("UPDATE people SET active = 1 WHERE id = ?", (old["id"],))
            log_event(conn, now, actor_id, "pessoa_reativada", f"pessoa:{old['id']}", name)
            return _row(conn.execute("SELECT * FROM people WHERE id = ?", (old["id"],)).fetchone())
        initials = (initials.strip() or _default_initials(name)).upper()
        if not color:
            used = {r[0] for r in conn.execute("SELECT color FROM people WHERE active = 1")}
            color = next((c for c in PALETTE if c not in used), PALETTE[0])
        _validate(conn, name, initials, color, None)
        cur = conn.execute("INSERT INTO people(name, initials, color) VALUES (?, ?, ?)", (name, initials, color))
        log_event(conn, now, actor_id, "pessoa_criada", f"pessoa:{cur.lastrowid}", name)
        return _row(conn.execute("SELECT * FROM people WHERE id = ?", (cur.lastrowid,)).fetchone())


def update_person(db: Database, now: datetime, actor_id: int | None, person_id: int, *,
                  name: str | None = None, initials: str | None = None, color: str | None = None) -> Person:
    current = get_person(db, person_id)
    if current is None:
        raise ValidationError("Pessoa não encontrada.")
    new_name = " ".join((name if name is not None else current.name).split())
    new_initials = (initials if initials is not None else current.initials).strip().upper()
    new_color = color if color is not None else current.color
    with db.connect() as conn:
        _validate(conn, new_name, new_initials, new_color, person_id)
        conn.execute("UPDATE people SET name = ?, initials = ?, color = ? WHERE id = ?",
                     (new_name, new_initials, new_color, person_id))
        log_event(conn, now, actor_id, "pessoa_editada", f"pessoa:{person_id}", new_name)
    return get_person(db, person_id)


def deactivate_person(db: Database, now: datetime, actor_id: int | None, person_id: int) -> None:
    with db.connect() as conn:
        admins = [r[0] for r in conn.execute("SELECT id FROM people WHERE is_admin = 1 AND active = 1")]
        if admins == [person_id]:
            raise ValidationError("Essa é a única pessoa administradora. Marque outra antes de desativar.")
        conn.execute("UPDATE people SET active = 0 WHERE id = ?", (person_id,))
        conn.execute("DELETE FROM sessions WHERE person_id = ?", (person_id,))
        log_event(conn, now, actor_id, "pessoa_desativada", f"pessoa:{person_id}", "")


def list_people(db: Database, active_only: bool = True) -> list[Person]:
    sql = "SELECT * FROM people" + (" WHERE active = 1" if active_only else "") + " ORDER BY name COLLATE NOCASE"
    with db.connect() as conn:
        return [_row(r) for r in conn.execute(sql)]


def get_person(db: Database, person_id: int) -> Person | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    return _row(r) if r else None
