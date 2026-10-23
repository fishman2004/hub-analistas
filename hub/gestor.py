"""Visão do gestor: o dia da equipe numa tela só, e todas as demandas com filtros."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .db import Database
from .demands import COLUMNS, Demand, board, is_overdue, is_owner
from .people import Person
from .presence import presence_board

DUE_FILTERS = {"": "Qualquer prazo", "hoje": "Vence hoje", "semana": "Vence em 7 dias", "sem": "Sem prazo"}


@dataclass(frozen=True)
class TeamRow:
    person: Person
    status: str
    since: datetime
    todo: int
    doing: int
    done_today: int
    overdue: int


def can_open(person: Person) -> bool:
    """A visão do gestor é do gestor; administradores também abrem, porque já gerenciam a equipe."""
    return person.is_manager or person.is_admin


def team_summary(db: Database, now: datetime) -> list[TeamRow]:
    columns = board(db, now)
    today = now.date()
    rows = []
    for person, status, since in presence_board(db, now):
        mine = {c: [d for d in columns[c] if is_owner(d, person.id)] for c in COLUMNS}
        overdue = sum(is_overdue(d, today) for d in mine["todo"] + mine["doing"])
        rows.append(TeamRow(person, status, since, len(mine["todo"]), len(mine["doing"]), len(mine["done"]), overdue))
    return rows


def _due_matches(d: Demand, due: str, today: date) -> bool:
    if due == "hoje":
        return d.due == today
    if due == "semana":
        return d.due is not None and today <= d.due <= today + timedelta(days=7)
    if due == "sem":
        return d.due is None
    return True


def filter_demands(db: Database, now: datetime, *, owner_id: int | None = None, column: str = "",
                   due: str = "", overdue_only: bool = False) -> list[Demand]:
    """Todas as demandas abertas e as concluídas hoje, na ordem do quadro, com os filtros aplicados."""
    columns = board(db, now, owner_id=owner_id)
    today = now.date()
    chosen = [column] if column in COLUMNS else list(COLUMNS)
    return [d for c in chosen for d in columns[c]
            if _due_matches(d, due, today) and (not overdue_only or is_overdue(d, today))]
