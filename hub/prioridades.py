"""Prioridades do início do mês: a lista de cada mês, quem fez cada item e a tela da TV.

O mês vem da data (AAAA-MM), sem tarefa agendada: no dia 1º a lista nova começa vazia e a do mês
anterior fica só para consulta. A tela da TV sai da rotação sozinha quando tudo estiver feito.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime

from .db import Database, log_event
from .demands import FOLDERS
from .paineis import MESES
from .people import Person, ValidationError, list_people

MAX_TITLE = 120
# lista padrão do mês, com os itens do Kayo: (título, pasta, prazo em dia do mês).
# Depois de criada, dá para remover e acrescentar itens à vontade.
DEFAULT_LIST: list[tuple[str, str | None, int | None]] = [
    ("Lançar a meta no sistema", None, None),
    ("Confirmar o recebimento da meta com o gerente", None, None),
    ("Entregar as comissões", None, 10),
    ("Entregar as campanhas", None, 15),
]


@dataclass(frozen=True)
class Priority:
    id: int
    month: str
    title: str
    folder: str | None
    due_day: int | None  # "até dia 10"
    position: int
    created_by: int | None
    created_at: datetime
    done_by: int | None
    done_at: datetime | None

    @property
    def done(self) -> bool:
        return self.done_at is not None


def _row(r) -> Priority:
    return Priority(r["id"], r["month"], r["title"], r["folder"], r["due_day"], r["position"], r["created_by"],
                    datetime.fromisoformat(r["created_at"]), r["done_by"],
                    datetime.fromisoformat(r["done_at"]) if r["done_at"] else None)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


# ---------- o mês ----------

def month_of(day: date) -> str:
    """O mês de uma data, como fica no banco: "2026-10"."""
    return f"{day:%Y-%m}"


def is_month(text: str) -> bool:
    return re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text or "") is not None


def month_label(month: str) -> str:
    """ "2026-10" -> "outubro de 2026" """
    year, number = month.split("-")
    return f"{MESES[int(number) - 1]} de {year}"


def last_day(month: str) -> int:
    year, number = month.split("-")
    return calendar.monthrange(int(year), int(number))[1]


def parse_due_day(text: str | None) -> int | None:
    """O prazo como vem do formulário: em branco é sem prazo."""
    text = (text or "").strip()
    if not text:
        return None
    if not text.isdigit():
        raise ValidationError("Prazo: informe o dia do mês, só o número (por exemplo, 10).")
    return int(text)


def is_late(p: Priority, today: date) -> bool:
    """Atrasada: em aberto e já passou do dia do prazo. "Até dia 10" ainda vale no dia 10."""
    if p.done or p.due_day is None:
        return False
    current = month_of(today)
    return p.month < current or (p.month == current and today.day > p.due_day)


# ---------- a lista ----------

def list_month(db: Database, month: str) -> list[Priority]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM priorities WHERE month = ? AND deleted = 0 ORDER BY position, id", (month,))
        return [_row(r) for r in rows]


def past_months(db: Database, now: datetime) -> list[str]:
    """Meses anteriores que tiveram lista, do mais recente para o mais antigo (para consulta)."""
    with db.connect() as conn:
        rows = conn.execute("SELECT DISTINCT month FROM priorities WHERE deleted = 0 AND month < ? ORDER BY month DESC",
                            (month_of(now),))
        return [r[0] for r in rows]


def _get(conn, item_id: int):
    r = conn.execute("SELECT * FROM priorities WHERE id = ? AND deleted = 0", (item_id,)).fetchone()
    if r is None:
        raise ValidationError("Item não encontrado.")
    return r


def _current(conn, now: datetime, item_id: int):
    """O item, desde que seja do mês atual: os meses anteriores ficam só para consulta."""
    r = _get(conn, item_id)
    if r["month"] != month_of(now):
        raise ValidationError("Só dá para mudar a lista do mês atual.")
    return r


def _clean(conn, month: str, title: str, folder: str | None, due_day: int | None) -> tuple[str, str | None]:
    title = " ".join((title or "").split())
    folder = folder or None
    if not title:
        raise ValidationError("Informe o item.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Item muito longo (máximo {MAX_TITLE}).")
    if folder is not None and folder not in FOLDERS:
        raise ValidationError("Pasta inválida.")
    if due_day is not None and not 1 <= due_day <= last_day(month):
        raise ValidationError(f"Prazo: use um dia de 1 a {last_day(month)}.")
    # comparação no Python: o lower() do SQLite não conhece acentos ("MÊS")
    existing = conn.execute("SELECT title, folder FROM priorities WHERE month = ? AND deleted = 0", (month,))
    if any(r["title"].casefold() == title.casefold() and r["folder"] == folder for r in existing):
        raise ValidationError("Esse item já está na lista do mês.")
    return title, folder


def _insert(conn, now: datetime, actor: Person, month: str, title: str, folder: str | None,
            due_day: int | None) -> int:
    position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM priorities WHERE month = ?",
                            (month,)).fetchone()[0]
    cur = conn.execute("INSERT INTO priorities(month, title, folder, due_day, position, created_by, created_at) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?)", (month, title, folder, due_day, position, actor.id, _iso(now)))
    return cur.lastrowid


def add_priority(db: Database, now: datetime, actor: Person, title: str, folder: str | None = None,
                 due_day: int | None = None) -> Priority:
    """Acrescenta um item no fim da lista do mês atual (pasta e prazo são opcionais)."""
    month = month_of(now)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")  # trava a escrita antes de conferir: dois cliques não criam dois itens
        title, folder = _clean(conn, month, title, folder, due_day)
        item_id = _insert(conn, now, actor, month, title, folder, due_day)
        log_event(conn, now, actor.id, "prioridade_criada", f"prioridade:{item_id}", title)
        return _row(_get(conn, item_id))


def create_default_list(db: Database, now: datetime, actor: Person) -> list[Priority]:
    """Cria a lista padrão no mês atual, só se ele ainda não tiver nenhum item. Devolve o que criou."""
    month = month_of(now)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")  # dois PCs clicando juntos: o segundo encontra a lista pronta
        if conn.execute("SELECT 1 FROM priorities WHERE month = ? AND deleted = 0", (month,)).fetchone():
            return []
        ids = [_insert(conn, now, actor, month, *item) for item in DEFAULT_LIST]
        log_event(conn, now, actor.id, "prioridades_padrao", f"prioridades:{month}", month)
        return [_row(_get(conn, i)) for i in ids]


def mark_done(db: Database, now: datetime, actor: Person, item_id: int) -> Priority:
    """Qualquer pessoa marca como feito; fica guardado quem fez e quando."""
    with db.connect() as conn:
        r = _current(conn, now, item_id)
        # "done_at IS NULL": se outro PC marcou junto, continua valendo quem fez primeiro
        cur = conn.execute("UPDATE priorities SET done_by = ?, done_at = ? WHERE id = ? AND done_at IS NULL",
                           (actor.id, _iso(now), item_id))
        if cur.rowcount:
            log_event(conn, now, actor.id, "prioridade_feita", f"prioridade:{item_id}", r["title"])
        return _row(_get(conn, item_id))


def undo_done(db: Database, now: datetime, actor: Person, item_id: int) -> Priority:
    with db.connect() as conn:
        r = _current(conn, now, item_id)
        cur = conn.execute("UPDATE priorities SET done_by = NULL, done_at = NULL WHERE id = ? AND done_at IS NOT NULL",
                           (item_id,))
        if cur.rowcount:
            log_event(conn, now, actor.id, "prioridade_desfeita", f"prioridade:{item_id}", r["title"])
        return _row(_get(conn, item_id))


def can_remove(item: Priority, person: Person) -> bool:
    """Remover: quem criou o item ou um administrador."""
    return person.is_admin or item.created_by == person.id


def remove_priority(db: Database, now: datetime, actor: Person, item_id: int) -> None:
    with db.connect() as conn:
        r = _current(conn, now, item_id)
        if not can_remove(_row(r), actor):
            raise PermissionError("Só quem criou o item ou um administrador pode remover.")
        conn.execute("UPDATE priorities SET deleted = 1 WHERE id = ?", (item_id,))
        log_event(conn, now, actor.id, "prioridade_removida", f"prioridade:{item_id}", r["title"])


# ---------- TV ----------

def tv_prioridades(db: Database, now: datetime) -> dict | None:
    """A tela da TV. Sem lista no mês, ou com tudo feito, devolve None e a tela sai da rotação.

    Vai só o que a tela desenha: o título, a pasta, o prazo, se está atrasada e, nos itens feitos, as
    iniciais e a cor de quem fez (sem nome, sem horário, sem quem criou).
    """
    month, today = month_of(now), now.date()
    items = list_month(db, month)
    if not items or all(p.done for p in items):
        return None
    people = {p.id: p for p in list_people(db, active_only=False)}

    def card(p: Priority) -> dict:
        who = people.get(p.done_by) if p.done else None
        return {"title": p.title, "folder": p.folder, "due_day": p.due_day, "late": is_late(p, today),
                "done": p.done, "initials": who.initials if who else None, "color": who.color if who else None}

    # as atrasadas primeiro, depois as outras em aberto e por fim as feitas (cada grupo na ordem da lista):
    # se a tela tiver mais de uma página, o que a sala precisa ver fica na primeira
    ordered = sorted(items, key=lambda p: (p.done, not is_late(p, today)))
    return {"month": month_label(month), "done_count": sum(p.done for p in items), "total": len(items),
            "late_count": sum(is_late(p, today) for p in items), "items": [card(p) for p in ordered]}
