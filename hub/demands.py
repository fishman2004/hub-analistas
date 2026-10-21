"""Demandas e o quadro A fazer / Fazendo / Concluído hoje.

Rotinas (fase 7): nos dias e no horário de cada rotina, o quadro calcula um cartão dela em
"A fazer" do responsável, sem gravar nada. O cartão só vira uma demanda de verdade (uma por
rotina e por dia) na primeira vez que alguém mexe nele: move, edita ou marca uma pasta.
Enquanto é só cálculo, o app aponta para ele por "rotina-<número>-<AAAA-MM-DD>".
"""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime

from .db import Database, log_event
from .people import Person, ValidationError
from .rotinas import Routine, load_routines

COLUMNS = ("todo", "doing", "done")
COLUMN_LABELS = {"todo": "A fazer", "doing": "Fazendo", "done": "Concluído hoje"}
FOLDERS = ("A", "B", "C", "D", "E", "F", "G")
RESERVED_TEXT = "Demanda reservada"
MAX_TITLE = 120
MAX_REQUESTED_BY = 60
_ROUTINE_REF = re.compile(r"rotina-(\d+)-(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class RoutineInfo:
    """O que o cartão de uma rotina mostra a mais, calculado a cada montagem do quadro."""
    time: str  # "14:50"
    deadline: str | None  # "15:00"
    folders: tuple[str, ...]  # pastas que marcam
    checked: tuple[str, ...]  # pastas já marcadas
    waiting: tuple[str, ...]  # rotinas que ainda faltam terminar ("Transferência de pedidos 14:50")
    late: bool  # passou do prazo de hoje

    @property
    def label(self) -> str:
        return f"rotina {self.time}" + (f" · até {self.deadline}" if self.deadline else "")


@dataclass(frozen=True)
class Demand:
    id: int | None  # None: cartão de rotina ainda só calculado
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
    routine_id: int | None = None
    routine_day: date | None = None
    routine: RoutineInfo | None = None  # só nos cartões que vêm do quadro

    @property
    def ref(self) -> str:
        """Como o app aponta para o cartão: o número da demanda, ou a rotina e o dia."""
        return str(self.id) if self.id is not None else routine_ref(self.routine_id, self.routine_day)


def routine_ref(routine_id: int, day: date) -> str:
    return f"rotina-{routine_id}-{day.isoformat()}"


def _row(r) -> Demand:
    return Demand(
        r["id"], r["title"], r["owner_id"], r["folder"], r["requested_by"],
        date.fromisoformat(r["due"]) if r["due"] else None, bool(r["reserved"]), r["column_"],
        datetime.fromisoformat(r["created_at"]), datetime.fromisoformat(r["updated_at"]),
        datetime.fromisoformat(r["done_at"]) if r["done_at"] else None,
        r["created_by"], r["routine_id"], date.fromisoformat(r["routine_day"]) if r["routine_day"] else None,
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


def _parse_ref(ref: str) -> tuple[int, date] | None:
    m = _ROUTINE_REF.fullmatch(ref)
    try:
        return (int(m[1]), date.fromisoformat(m[2])) if m else None
    except ValueError:
        return None


def _resolve(conn, now: datetime, actor_id: int | None, ref: int | str) -> int:
    """O número da demanda de um cartão. O cartão calculado de uma rotina vira demanda aqui, dentro
    da mesma gravação da ação: se a ação for recusada, nada fica criado pela metade."""
    if isinstance(ref, int) or ref.isdigit():
        return int(ref)
    parsed = _parse_ref(ref)
    if parsed is None:
        raise ValidationError("Demanda não encontrada.")
    routine_id, day = parsed
    existing = conn.execute("SELECT id, deleted FROM demands WHERE routine_id = ? AND routine_day = ?",
                            (routine_id, day.isoformat())).fetchone()
    if existing is not None:
        if existing["deleted"]:
            raise ValidationError("Essa rotina foi dispensada hoje.")
        return existing["id"]  # outro PC já mexeu: é o mesmo cartão
    routine = load_routines(conn).get(routine_id)
    if routine is None or day != now.date() or not routine.is_due(now):
        raise ValidationError("Essa rotina não está no quadro agora. Atualize a página.")
    # OR IGNORE + o índice único: dois PCs ao mesmo tempo criam uma demanda só
    cur = conn.execute(
        "INSERT OR IGNORE INTO demands(title, owner_id, due, reserved, column_, created_at, updated_at, routine_id, "
        "routine_day) VALUES (?, ?, ?, 0, 'todo', ?, ?, ?, ?)",
        (routine.name, routine.owner_id, day.isoformat(), _iso(routine.start(day)), _iso(now), routine_id,
         day.isoformat()),
    )
    demand_id = conn.execute("SELECT id FROM demands WHERE routine_id = ? AND routine_day = ?",
                             (routine_id, day.isoformat())).fetchone()["id"]
    if cur.rowcount:
        log_event(conn, now, actor_id, "rotina_demanda", f"demanda:{demand_id}", routine.label)
    return demand_id


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


def update_demand(db: Database, now: datetime, actor_id: int | None, demand_id: int | str, *, title: str,
                  owner_id: int, folder: str | None, requested_by: str | None, due: date | None,
                  reserved: bool) -> Demand:
    with db.connect() as conn:
        demand_id = _resolve(conn, now, actor_id, demand_id)
        current = _get(conn, demand_id)
        title, folder, requested_by = _clean(conn, title, owner_id, folder, requested_by, current["owner_id"])
        conn.execute(
            "UPDATE demands SET title = ?, owner_id = ?, folder = ?, requested_by = ?, due = ?, reserved = ?, "
            "updated_at = ? WHERE id = ?",
            (title, owner_id, folder, requested_by, due.isoformat() if due else None, int(reserved), _iso(now), demand_id),
        )
        log_event(conn, now, actor_id, "demanda_editada", f"demanda:{demand_id}", title)
        return _row(_get(conn, demand_id))


def _set_column(conn, now: datetime, actor_id: int | None, demand_id: int, column: str) -> None:
    done_at = _iso(now) if column == "done" else None
    conn.execute("UPDATE demands SET column_ = ?, done_at = ?, updated_at = ? WHERE id = ?",
                 (column, done_at, _iso(now), demand_id))
    log_event(conn, now, actor_id, "demanda_movida", f"demanda:{demand_id}", column)


def move_demand(db: Database, now: datetime, actor_id: int | None, demand_id: int | str, column: str) -> Demand:
    if column not in COLUMNS:
        raise ValidationError("Coluna inválida.")
    with db.connect() as conn:
        demand_id = _resolve(conn, now, actor_id, demand_id)
        r = _get(conn, demand_id)
        if r["routine_id"] is not None and column != "todo":
            _check_routine_move(conn, now, r, column)
        _set_column(conn, now, actor_id, demand_id, column)
        return _row(_get(conn, demand_id))


def delete_demand(db: Database, now: datetime, actor_id: int | None, demand_id: int | str) -> None:
    """Excluir o cartão de uma rotina dispensa a rotina só naquele dia: amanhã ela aparece de novo."""
    with db.connect() as conn:
        demand_id = _resolve(conn, now, actor_id, demand_id)
        r = _get(conn, demand_id)
        conn.execute("UPDATE demands SET deleted = 1, updated_at = ? WHERE id = ?", (_iso(now), demand_id))
        log_event(conn, now, actor_id, "demanda_excluida", f"demanda:{demand_id}", r["title"])


def find_demand(db: Database, demand_id: int) -> Demand | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM demands WHERE id = ? AND deleted = 0", (demand_id,)).fetchone()
    return _row(r) if r else None


def find_card(db: Database, now: datetime, ref: str) -> Demand | None:
    """O cartão pelo endereço do app: uma demanda, ou a rotina de hoje (sem criar nada)."""
    if ref.isdigit():
        return find_demand(db, int(ref))
    parsed = _parse_ref(ref)
    if parsed is None:
        return None
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM demands WHERE routine_id = ? AND routine_day = ? AND deleted = 0",
                         (parsed[0], parsed[1].isoformat())).fetchone()
    if r is not None:
        return _row(r)  # outro PC já mexeu nela
    return next((d for column in board(db, now).values() for d in column if d.ref == ref), None)


def all_demands(db: Database) -> dict[int, Demand]:
    """Cada demanda, inclusive as excluídas (para o histórico do app)."""
    with db.connect() as conn:
        return {r["id"]: _row(r) for r in conn.execute("SELECT * FROM demands")}


def can_see(d: Demand, person: Person) -> bool:
    """Título de demanda reservada: só o gestor, administradores, o dono e quem criou."""
    return (not d.reserved or person.is_manager or person.is_admin
            or person.id in (d.owner_id, d.created_by))


def is_overdue(d: Demand, today: date) -> bool:
    """Prazo antes de hoje, ou rotina de hoje que passou do horário do prazo, e fora de Concluído."""
    if d.column == "done":
        return False
    return (d.due is not None and d.due < today) or (d.routine is not None and d.routine.late)


# ---------- rotinas ----------

def _settled_today(conn, today: date) -> tuple[set[int], set[int]]:
    """Rotinas com cartão de hoje (para não calcular de novo) e as resolvidas hoje: concluídas ou dispensadas."""
    rows = conn.execute("SELECT routine_id, column_, deleted FROM demands WHERE routine_day = ? AND "
                        "routine_id IS NOT NULL", (today.isoformat(),)).fetchall()
    return ({r["routine_id"] for r in rows},
            {r["routine_id"] for r in rows if r["deleted"] or r["column_"] == "done"})


def _waiting(routine: Routine, day: date, today: date, routines: dict[int, Routine], settled: set[int]) -> tuple[str, ...]:
    # só a espera de hoje: a rotina esperada também precisa valer hoje (dia da semana e ativa)
    if day != today:
        return ()
    return tuple(routines[w].label for w in routine.waits_for
                 if w in routines and routines[w].runs_on(today) and w not in settled)


def _checked(conn, demand_id: int) -> set[str]:
    return {r[0] for r in conn.execute("SELECT folder FROM routine_folders WHERE demand_id = ?", (demand_id,))}


def _waiting_message(waiting: tuple[str, ...]) -> str:
    return f"Aguardando: {', '.join(waiting)}. Esta rotina só começa depois que {'ela for concluída' if len(waiting) == 1 else 'elas forem concluídas'}."


def _check_routine_move(conn, now: datetime, r, column: str) -> None:
    """Rotina que espera outra não começa nem conclui; rotina com pastas conclui sozinha, quando todas marcarem."""
    routines = load_routines(conn)
    routine = routines.get(r["routine_id"])
    if routine is None:
        return
    _, settled = _settled_today(conn, now.date())
    waiting = _waiting(routine, date.fromisoformat(r["routine_day"]), now.date(), routines, settled)
    if waiting:
        raise ValidationError(_waiting_message(waiting))
    if column == "done":
        missing = [f for f in routine.folders if f not in _checked(conn, r["id"])]
        if missing:
            raise ValidationError(f"Faltam as pastas {', '.join(missing)}. A rotina conclui sozinha quando todas "
                                  "forem marcadas.")


def toggle_folder(db: Database, now: datetime, actor_id: int | None, demand_id: int | str, folder: str) -> Demand:
    """Marca (ou desmarca) uma pasta no cartão de uma rotina. Qualquer pessoa marca; o histórico guarda quem.
    A primeira marcada leva o cartão para Fazendo; com todas marcadas ele vai sozinho para Concluído
    hoje, e desmarcar uma reabre em Fazendo."""
    with db.connect() as conn:
        demand_id = _resolve(conn, now, actor_id, demand_id)
        r = _get(conn, demand_id)
        routines = load_routines(conn)
        routine = routines.get(r["routine_id"]) if r["routine_id"] is not None else None
        if routine is None or folder not in routine.folders:
            raise ValidationError("Essa pasta não faz parte desta rotina.")
        checked = _checked(conn, demand_id)
        if folder in checked:
            conn.execute("DELETE FROM routine_folders WHERE demand_id = ? AND folder = ?", (demand_id, folder))
            checked.discard(folder)
            log_event(conn, now, actor_id, "pasta_desmarcada", f"demanda:{demand_id}", folder)
        else:
            _, settled = _settled_today(conn, now.date())
            waiting = _waiting(routine, date.fromisoformat(r["routine_day"]), now.date(), routines, settled)
            if waiting:
                raise ValidationError(_waiting_message(waiting))
            conn.execute("INSERT INTO routine_folders(demand_id, folder, person_id, at) VALUES (?, ?, ?, ?)",
                         (demand_id, folder, actor_id, _iso(now)))
            checked.add(folder)
            log_event(conn, now, actor_id, "pasta_marcada", f"demanda:{demand_id}", folder)
        column = r["column_"]
        if all(f in checked for f in routine.folders):
            target = "done"
        elif column == "done" or (column == "todo" and checked):
            target = "doing"
        else:
            target = column
        if target != column:
            _set_column(conn, now, actor_id, demand_id, target)
        return _row(_get(conn, demand_id))


def _with_routines(conn, rows: list[Demand], now: datetime, owner_id: int | None) -> list[Demand]:
    """Junta ao quadro o que as rotinas acrescentam: o horário, as pastas, a espera e o prazo de cada
    cartão de rotina, e o cartão calculado de cada rotina de hoje que ainda não virou demanda."""
    routines = load_routines(conn)
    if not routines:
        return rows
    today = now.date()
    on_board, settled = _settled_today(conn, today)
    ids = [d.id for d in rows if d.routine_id is not None]
    checks: dict[int, set[str]] = {}
    if ids:
        marks = conn.execute(f"SELECT demand_id, folder FROM routine_folders WHERE demand_id IN ({','.join('?' * len(ids))})", ids)
        for m in marks:
            checks.setdefault(m["demand_id"], set()).add(m["folder"])

    def info(routine: Routine, day: date, column: str, checked: set[str]) -> RoutineInfo:
        deadline = routine.deadline_at(day)
        return RoutineInfo(
            routine.starts_at, routine.deadline, routine.folders, tuple(f for f in routine.folders if f in checked),
            () if column == "done" else _waiting(routine, day, today, routines, settled),
            column != "done" and day == today and deadline is not None and now > deadline,
        )

    result = [replace(d, routine=info(routines[d.routine_id], d.routine_day, d.column, checks.get(d.id, set())))
              if d.routine_id in routines else d for d in rows]
    for routine in routines.values():
        if routine.id in on_board or not routine.is_due(now) or (owner_id is not None and routine.owner_id != owner_id):
            continue
        start = routine.start(today)
        result.append(Demand(None, routine.name, routine.owner_id, None, None, today, False, "todo", start, start, None,
                             None, routine.id, today, info(routine, today, "todo", set())))
    return result


def board(db: Database, now: datetime, owner_id: int | None = None) -> dict[str, list[Demand]]:
    sql = "SELECT * FROM demands WHERE deleted = 0"
    args: list = []
    if owner_id is not None:
        sql += " AND owner_id = ?"
        args.append(owner_id)
    with db.connect() as conn:
        rows = _with_routines(conn, [_row(r) for r in conn.execute(sql, args)], now, owner_id)
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
    """O cartão como a TV o recebe. Demanda reservada não leva título, pasta, quem pediu nem nada da rotina."""
    routine = None
    if d.routine is not None and not d.reserved:
        routine = {"time": d.routine.time, "deadline": d.routine.deadline, "folders": list(d.routine.folders),
                   "checked": list(d.routine.checked), "waiting": list(d.routine.waiting), "late": d.routine.late}
    return {
        "id": d.ref,
        "initials": owner.initials,
        "color": owner.color,
        "title": RESERVED_TEXT if d.reserved else d.title,
        "folder": None if d.reserved else d.folder,
        "requested_by": None if d.reserved else d.requested_by,
        "due": d.due.isoformat() if d.due else None,
        "overdue": is_overdue(d, today),
        "reserved": d.reserved,
        "routine": routine,
    }
