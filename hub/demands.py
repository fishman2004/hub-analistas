"""Demandas e o quadro A fazer / Fazendo / Concluído hoje."""

from dataclasses import dataclass
from datetime import date, datetime

from .db import Database, log_event
from .people import Person, ValidationError

COLUMNS = ("todo", "doing", "done")
COLUMN_LABELS = {"todo": "A fazer", "doing": "Fazendo", "done": "Concluído hoje"}
FOLDERS = ("A", "B", "C", "D", "E", "F", "G")
RESERVED_TEXT = "Demanda reservada"
MAX_TITLE = 120
MAX_REQUESTED_BY = 60


@dataclass(frozen=True)
class Demand:
    id: int
    title: str
    owner_id: int
    folder: str | None
    requested_by: str | None
    due: date | None
    reserved: bool
    column: str
    created_at: datetime
    updated_at: datetime
    done_at: datetime | None
    created_by: int | None = None


def _row(r) -> Demand:
    return Demand(
        r["id"], r["title"], r["owner_id"], r["folder"], r["requested_by"],
        date.fromisoformat(r["due"]) if r["due"] else None, bool(r["reserved"]), r["column_"],
        datetime.fromisoformat(r["created_at"]), datetime.fromisoformat(r["updated_at"]),
        datetime.fromisoformat(r["done_at"]) if r["done_at"] else None,
        r["created_by"],
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _clean(conn, title: str, owner_id: int, folder: str | None, requested_by: str | None,
           current_owner_id: int | None = None) -> tuple:
    title = " ".join((title or "").split())
    requested_by = " ".join((requested_by or "").split()) or None
    folder = folder or None
    if not title:
        raise ValidationError("Informe o título.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Título muito longo (máximo {MAX_TITLE}).")
    owner = conn.execute("SELECT active FROM people WHERE id = ?", (owner_id,)).fetchone()
    # manter o dono atual vale mesmo se ele foi desativado; só não dá para escolher um desativado novo
    if owner is None or (not owner["active"] and owner_id != current_owner_id):
        raise ValidationError("Escolha o dono da demanda.")
    if folder is not None and folder not in FOLDERS:
        raise ValidationError("Pasta inválida.")
    if requested_by and len(requested_by) > MAX_REQUESTED_BY:
        raise ValidationError(f"\"Pedido por\" muito longo (máximo {MAX_REQUESTED_BY}).")
    return title, folder, requested_by


def _get(conn, demand_id: int):
    r = conn.execute("SELECT * FROM demands WHERE id = ? AND deleted = 0", (demand_id,)).fetchone()
    if r is None:
        raise ValidationError("Demanda não encontrada.")
    return r


def create_demand(db: Database, now: datetime, actor_id: int | None, *, title: str, owner_id: int,
                  folder: str | None = None, requested_by: str | None = None, due: date | None = None,
                  reserved: bool = False) -> Demand:
    with db.connect() as conn:
        title, folder, requested_by = _clean(conn, title, owner_id, folder, requested_by)
        cur = conn.execute(
            "INSERT INTO demands(title, owner_id, folder, requested_by, due, reserved, column_, created_at, updated_at, "
            "created_by) VALUES (?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?)",
            (title, owner_id, folder, requested_by, due.isoformat() if due else None, int(reserved), _iso(now), _iso(now),
             actor_id),
        )
        log_event(conn, now, actor_id, "demanda_criada", f"demanda:{cur.lastrowid}", title)
        return _row(_get(conn, cur.lastrowid))


def update_demand(db: Database, now: datetime, actor_id: int | None, demand_id: int, *, title: str, owner_id: int,
                  folder: str | None, requested_by: str | None, due: date | None, reserved: bool) -> Demand:
    with db.connect() as conn:
        current = _get(conn, demand_id)
        title, folder, requested_by = _clean(conn, title, owner_id, folder, requested_by, current["owner_id"])
        conn.execute(
            "UPDATE demands SET title = ?, owner_id = ?, folder = ?, requested_by = ?, due = ?, reserved = ?, "
            "updated_at = ? WHERE id = ?",
            (title, owner_id, folder, requested_by, due.isoformat() if due else None, int(reserved), _iso(now), demand_id),
        )
        log_event(conn, now, actor_id, "demanda_editada", f"demanda:{demand_id}", title)
        return _row(_get(conn, demand_id))


def move_demand(db: Database, now: datetime, actor_id: int | None, demand_id: int, column: str) -> Demand:
    if column not in COLUMNS:
        raise ValidationError("Coluna inválida.")
    with db.connect() as conn:
        _get(conn, demand_id)
        done_at = _iso(now) if column == "done" else None
        conn.execute("UPDATE demands SET column_ = ?, done_at = ?, updated_at = ? WHERE id = ?",
                     (column, done_at, _iso(now), demand_id))
        log_event(conn, now, actor_id, "demanda_movida", f"demanda:{demand_id}", column)
        return _row(_get(conn, demand_id))


def delete_demand(db: Database, now: datetime, actor_id: int | None, demand_id: int) -> None:
    with db.connect() as conn:
        r = _get(conn, demand_id)
        conn.execute("UPDATE demands SET deleted = 1, updated_at = ? WHERE id = ?", (_iso(now), demand_id))
        log_event(conn, now, actor_id, "demanda_excluida", f"demanda:{demand_id}", r["title"])


def find_demand(db: Database, demand_id: int) -> Demand | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM demands WHERE id = ? AND deleted = 0", (demand_id,)).fetchone()
    return _row(r) if r else None


def all_demands(db: Database) -> dict[int, Demand]:
    """Cada demanda, inclusive as excluídas (para o histórico do app)."""
    with db.connect() as conn:
        return {r["id"]: _row(r) for r in conn.execute("SELECT * FROM demands")}


def can_see(d: Demand, person: Person) -> bool:
    """Título de demanda reservada: só o gestor, administradores, o dono e quem criou."""
    return (not d.reserved or person.is_manager or person.is_admin
            or person.id in (d.owner_id, d.created_by))


def is_overdue(d: Demand, today: date) -> bool:
    return d.due is not None and d.due < today and d.column != "done"


def board(db: Database, now: datetime, owner_id: int | None = None) -> dict[str, list[Demand]]:
    sql = "SELECT * FROM demands WHERE deleted = 0"
    args: list = []
    if owner_id is not None:
        sql += " AND owner_id = ?"
        args.append(owner_id)
    with db.connect() as conn:
        rows = [_row(r) for r in conn.execute(sql, args)]
    today = now.date()

    def open_key(d: Demand):
        # atrasadas primeiro, depois prazo mais próximo (sem prazo por último), depois as mais antigas
        return (not is_overdue(d, today), d.due is None, d.due or date.max, d.created_at)

    return {
        "todo": sorted((d for d in rows if d.column == "todo"), key=open_key),
        "doing": sorted((d for d in rows if d.column == "doing"), key=open_key),
        "done": sorted((d for d in rows if d.column == "done" and d.done_at and d.done_at.date() == today),
                       key=lambda d: d.done_at, reverse=True),
    }


def tv_card(d: Demand, owner: Person, today: date) -> dict:
    """O cartão como a TV o recebe. Demanda reservada não leva título, pasta nem quem pediu."""
    return {
        "id": d.id,
        "initials": owner.initials,
        "color": owner.color,
        "title": RESERVED_TEXT if d.reserved else d.title,
        "folder": None if d.reserved else d.folder,
        "requested_by": None if d.reserved else d.requested_by,
        "due": d.due.isoformat() if d.due else None,
        "overdue": is_overdue(d, today),
        "reserved": d.reserved,
    }
