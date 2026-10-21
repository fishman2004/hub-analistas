"""Prioridades do início do mês: a lista de cada mês, quem fez cada item e a tela da TV.

O mês vem da data (AAAA-MM), sem tarefa agendada: no dia 1º a lista nova começa vazia e a do mês
anterior fica só para consulta. A tela da TV sai da rotação sozinha quando tudo estiver feito.

Por pasta (fase 16): quando as pessoas estão ligadas às suas pastas (página Pessoas), cada item é marcado
pasta por pasta, por quem cuida dela, e só fica feito quando todas as pastas fizeram. Item com pasta
escolhida pede só aquela pasta. Sem ninguém ligado a pasta nenhuma, vale a marcação única de antes.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .db import Database, log_event
from .demands import FOLDERS
from .paineis import MESES
from .pastas import folders_by_person, owners
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
class Mark:
    """Uma pasta que já fez o item: quem marcou e quando."""
    folder: str
    done_by: int | None
    done_at: datetime


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
    done_by: int | None  # marcação única (sem pastas ligadas, ou de antes da fase 16): vale o item todo
    done_at: datetime | None
    required: tuple[str, ...] = ()  # as pastas que precisam fazer; vazio = marcação única
    marks: tuple[Mark, ...] = field(default=())

    def mark(self, folder: str) -> Mark | None:
        return next((m for m in self.marks if m.folder == folder), None)

    @property
    def missing(self) -> tuple[str, ...]:
        """As pastas que ainda não fizeram (vazio quando o item está feito)."""
        if self.done_at is not None:
            return ()
        done = {m.folder for m in self.marks}
        return tuple(f for f in self.required if f not in done)

    @property
    def done(self) -> bool:
        return self.done_at is not None or (bool(self.required) and not self.missing)


def _row(r, covered: tuple[str, ...] = (), marks: tuple[Mark, ...] = ()) -> Priority:
    if not covered:
        required: tuple[str, ...] = ()
    else:
        wanted = {r["folder"]} if r["folder"] else set(covered)
        # uma pasta que já marcou continua aparecendo, mesmo que a pessoa tenha saído dela depois
        wanted |= {m.folder for m in marks}
        required = tuple(f for f in FOLDERS if f in wanted)
    return Priority(r["id"], r["month"], r["title"], r["folder"], r["due_day"], r["position"], r["created_by"],
                    datetime.fromisoformat(r["created_at"]), r["done_by"],
                    datetime.fromisoformat(r["done_at"]) if r["done_at"] else None, required, marks)


def covered_folders(db: Database) -> tuple[str, ...]:
    """As pastas que têm alguém ligado (e que fazem as prioridades). Vazio: marcação única, como antes."""
    return tuple(owners(db))


def _marks(conn, ids: list[int]) -> dict[int, tuple[Mark, ...]]:
    if not ids:
        return {}
    rows = conn.execute(f"SELECT * FROM priority_marks WHERE priority_id IN ({','.join('?' * len(ids))})", ids)
    found: dict[int, list[Mark]] = {}
    for m in rows:
        found.setdefault(m["priority_id"], []).append(
            Mark(m["folder"], m["done_by"], datetime.fromisoformat(m["done_at"])))
    return {i: tuple(sorted(ms, key=lambda m: FOLDERS.index(m.folder) if m.folder in FOLDERS else 99))
            for i, ms in found.items()}


def _full(conn, r, covered: tuple[str, ...]) -> Priority:
    return _row(r, covered, _marks(conn, [r["id"]]).get(r["id"], ()))


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
    covered = covered_folders(db)
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM priorities WHERE month = ? AND deleted = 0 ORDER BY position, id",
                            (month,)).fetchall()
        marks = _marks(conn, [r["id"] for r in rows])
        return [_row(r, covered, marks.get(r["id"], ())) for r in rows]


def by_folder(items: list[Priority]) -> list[tuple[str, int, int]]:
    """O resumo por pasta: (pasta, quantos itens ela já fez, quantos ela precisa fazer)."""
    result = []
    for f in FOLDERS:
        mine = [p for p in items if f in p.required]
        if mine:
            result.append((f, sum(p.done_at is not None or p.mark(f) is not None for p in mine), len(mine)))
    return result


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
    _not_assistant(actor)
    month = month_of(now)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")  # trava a escrita antes de conferir: dois cliques não criam dois itens
        title, folder = _clean(conn, month, title, folder, due_day)
        item_id = _insert(conn, now, actor, month, title, folder, due_day)
        log_event(conn, now, actor.id, "prioridade_criada", f"prioridade:{item_id}", title)
        return _row(_get(conn, item_id))


def create_default_list(db: Database, now: datetime, actor: Person) -> list[Priority]:
    """Cria a lista padrão no mês atual, só se ele ainda não tiver nenhum item. Devolve o que criou."""
    _not_assistant(actor)
    month = month_of(now)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")  # dois PCs clicando juntos: o segundo encontra a lista pronta
        if conn.execute("SELECT 1 FROM priorities WHERE month = ? AND deleted = 0", (month,)).fetchone():
            return []
        ids = [_insert(conn, now, actor, month, *item) for item in DEFAULT_LIST]
        log_event(conn, now, actor.id, "prioridades_padrao", f"prioridades:{month}", month)
        return [_row(_get(conn, i)) for i in ids]


def _not_assistant(actor: Person) -> None:
    if actor.is_assistant:
        raise PermissionError("Assistente não faz as prioridades do mês: elas ficam com quem cuida das pastas.")


def can_mark(person: Person, folder: str, mine: tuple[str, ...]) -> bool:
    """Marcar (ou desfazer) uma pasta: quem cuida dela, e o gestor ou um administrador (para cobrir uma falta)."""
    return not person.is_assistant and (folder in mine or person.is_manager or person.is_admin)


def _folders_for(item: Priority, actor: Person, folder: str | None, mine: tuple[str, ...], marked: bool) -> list[str]:
    """As pastas que a ação vai mudar: a pasta pedida, ou as pastas da pessoa que estão em aberto (ou marcadas)."""
    if folder:
        if folder not in item.required:
            raise ValidationError("Esse item não é dessa pasta.")
        if not can_mark(actor, folder, mine):
            raise PermissionError(f"Só quem cuida da pasta {folder}, o gestor ou um administrador marca essa pasta.")
        return [folder] if (item.mark(folder) is not None) == marked else []
    targets = [f for f in item.required if f in mine]
    if not targets:
        raise ValidationError("Esse item não é das suas pastas. Quem cuida das pastas marca a sua.")
    return [f for f in targets if (item.mark(f) is not None) == marked]


def _log_folders(conn, now: datetime, actor: Person, kind: str, item_id: int, folders: list[str], title: str) -> None:
    # "B,C|título": a descrição do histórico separa as pastas do título (o título não tem "|" no começo)
    log_event(conn, now, actor.id, kind, f"prioridade:{item_id}", f"{','.join(folders)}|{title}")


def mark_done(db: Database, now: datetime, actor: Person, item_id: int, folder: str | None = None) -> Priority:
    """Marca como feito; fica guardado quem fez e quando.

    Com pastas: marca a pasta pedida ou, sem pasta, as pastas da própria pessoa que estão em aberto.
    Sem pastas ligadas: qualquer pessoa (menos assistente) marca o item todo, como antes.
    """
    _not_assistant(actor)
    covered = covered_folders(db)
    mine = folders_by_person(db).get(actor.id, ())
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        item = _full(conn, _current(conn, now, item_id), covered)
        if not item.required:
            # "done_at IS NULL": se outro PC marcou junto, continua valendo quem fez primeiro
            cur = conn.execute("UPDATE priorities SET done_by = ?, done_at = ? WHERE id = ? AND done_at IS NULL",
                               (actor.id, _iso(now), item_id))
            if cur.rowcount:
                log_event(conn, now, actor.id, "prioridade_feita", f"prioridade:{item_id}", item.title)
        elif item.done_at is None:
            folders = _folders_for(item, actor, folder, mine, marked=False)
            conn.executemany("INSERT OR IGNORE INTO priority_marks(priority_id, folder, done_by, done_at) "
                             "VALUES (?, ?, ?, ?)", [(item_id, f, actor.id, _iso(now)) for f in folders])
            if folders:
                _log_folders(conn, now, actor, "prioridade_pasta_feita", item_id, folders, item.title)
        return _full(conn, _get(conn, item_id), covered)


def undo_done(db: Database, now: datetime, actor: Person, item_id: int, folder: str | None = None) -> Priority:
    _not_assistant(actor)
    covered = covered_folders(db)
    mine = folders_by_person(db).get(actor.id, ())
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        item = _full(conn, _current(conn, now, item_id), covered)
        if item.done_at is not None:
            # a marcação única vale para o item todo: desfazer volta tudo para em aberto
            conn.execute("UPDATE priorities SET done_by = NULL, done_at = NULL WHERE id = ?", (item_id,))
            log_event(conn, now, actor.id, "prioridade_desfeita", f"prioridade:{item_id}", item.title)
        elif item.required:
            folders = _folders_for(item, actor, folder, mine, marked=True)
            conn.executemany("DELETE FROM priority_marks WHERE priority_id = ? AND folder = ?",
                             [(item_id, f) for f in folders])
            if folders:
                _log_folders(conn, now, actor, "prioridade_pasta_desfeita", item_id, folders, item.title)
        return _full(conn, _get(conn, item_id), covered)


def can_remove(item: Priority, person: Person) -> bool:
    """Remover: quem criou o item ou um administrador."""
    return person.is_admin or (item.created_by == person.id and not person.is_assistant)


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
    iniciais e a cor de quem fez (sem nome, sem horário, sem quem criou). Com pastas, cada item leva as
    pastas que precisam fazer, cada uma com o check e as iniciais de quem marcou, ou em aberto.
    """
    month, today = month_of(now), now.date()
    items = list_month(db, month)
    if not items or all(p.done for p in items):
        return None
    people = {p.id: p for p in list_people(db, active_only=False)}

    def ini(person_id):
        who = people.get(person_id)
        return {"initials": who.initials if who else None, "color": who.color if who else None}

    def card(p: Priority) -> dict:
        data = {"title": p.title, "folder": p.folder, "due_day": p.due_day, "late": is_late(p, today),
                "done": p.done, **ini(p.done_by if p.done_at else None)}
        if p.required and p.done_at is None:
            marks = [{"folder": f, "done": p.mark(f) is not None, **ini(p.mark(f).done_by if p.mark(f) else None)}
                     for f in p.required]
            data["folders"] = marks
            if len(p.required) == 1 and p.done:  # uma pasta só: as iniciais de quem fez, como antes
                data.update(ini(p.marks[0].done_by))
        return data

    # as atrasadas primeiro, depois as outras em aberto e por fim as feitas (cada grupo na ordem da lista):
    # se a tela tiver mais de uma página, o que a sala precisa ver fica na primeira
    ordered = sorted(items, key=lambda p: (p.done, not is_late(p, today)))
    return {"month": month_label(month), "done_count": sum(p.done for p in items), "total": len(items),
            "late_count": sum(is_late(p, today) for p in items), "items": [card(p) for p in ordered]}
