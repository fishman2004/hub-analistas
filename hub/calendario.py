"""Calendário (fase 13): compromissos, feriados e ausências, mais o que o Hub já sabe (prazos das
demandas, prazos das prioridades do mês e rotinas), num lugar só. E a tela Agenda da TV.

Feriados nacionais são calculados (os fixos e os que dependem da Páscoa), não gravados: a tabela
holidays só guarda os da cidade e o liga/desliga de um nacional. Carnaval e Corpus Christi são ponto
facultativo, então começam desligados. Os feriados ativos tiram o dia das metas dos painéis, das
rotinas (salvo "roda também em feriado") e do que falta lançar no banco de horas.

Compromisso que se repete também é calculado na hora (toda semana, todo mês ou todo ano), a partir
da primeira data. "Só eu" aparece só para quem criou; reservado aparece como "Compromisso reservado"
para quem não participa, como a demanda reservada.
"""

import calendar as cal
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .db import Database, log_event
from .people import Person, ValidationError

KINDS = {"reuniao": "Reunião", "entrega": "Entrega", "treinamento": "Treinamento", "evento": "Evento"}
REPEATS = {"": "Não repete", "semanal": "Toda semana", "mensal": "Todo mês", "anual": "Todo ano"}
RESERVED_TEXT = "Compromisso reservado"
MAX_TITLE, MAX_PLACE, MAX_DESCRIPTION, MAX_REASON = 120, 80, 2000, 80
MAX_DAYS = 31  # um compromisso ou ausência de vários dias: até um mês
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

NATIONAL_FIXED = [(1, 1, "Confraternização Universal"), (4, 21, "Tiradentes"), (5, 1, "Dia do Trabalho"),
                  (9, 7, "Independência do Brasil"), (10, 12, "Nossa Senhora Aparecida"), (11, 2, "Finados"),
                  (11, 15, "Proclamação da República"), (11, 20, "Dia da Consciência Negra"), (12, 25, "Natal")]
# dias contados a partir da Páscoa; o último campo diz se começa ligado (ponto facultativo começa desligado)
NATIONAL_EASTER = [(-48, "Carnaval (segunda)", False), (-47, "Carnaval (terça)", False),
                   (-2, "Sexta-feira Santa", True), (60, "Corpus Christi", False)]


# ---------- feriados ----------

def easter(year: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    day = (h + m - 7 * n + 114) % 31 + 1
    return date(year, month, day)


def national(year: int) -> dict[date, tuple[str, bool]]:
    """Os feriados nacionais do ano: {dia: (nome, começa ligado)}."""
    out = {date(year, m, d): (name, True) for m, d, name in NATIONAL_FIXED}
    e = easter(year)
    for offset, name, on in NATIONAL_EASTER:
        out[e + timedelta(days=offset)] = (name, on)
    return out


@dataclass(frozen=True)
class Holiday:
    day: date
    name: str
    source: str  # 'nacional' ou 'local'
    active: bool


class Holidays:
    """Os feriados que valem, para qualquer ano: os nacionais calculados (com o liga/desliga gravado)
    mais os da cidade. `dia in feriados` diz se o dia é feriado ativo."""

    def __init__(self, rows=(), nationals: bool = True) -> None:
        self._nationals = nationals
        self._rows = {date.fromisoformat(r["day"]): (r["name"], r["source"], bool(r["active"])) for r in rows}
        self._years: dict[int, dict[date, Holiday]] = {}
        self.signature = (nationals, tuple(sorted((k.isoformat(), *v) for k, v in self._rows.items())))

    def year(self, year: int) -> dict[date, Holiday]:
        if year not in self._years:
            out = ({d: Holiday(d, name, "nacional", on) for d, (name, on) in national(year).items()}
                   if self._nationals else {})
            for d, (name, source, active) in self._rows.items():
                if d.year != year:
                    continue
                if source == "nacional" and d in out:
                    out[d] = Holiday(d, out[d].name, "nacional", active)
                elif source == "local":
                    out[d] = Holiday(d, name, "local", active)
            self._years[year] = dict(sorted(out.items()))
        return self._years[year]

    def __eq__(self, other: object) -> bool:  # o cache dos painéis compara: mesmos feriados, mesmo cálculo
        return isinstance(other, Holidays) and other.signature == self.signature

    def __hash__(self) -> int:
        return hash(self.signature)

    def get(self, day: date) -> Holiday | None:
        h = self.year(day.year).get(day)
        return h if h and h.active else None

    def __contains__(self, day: object) -> bool:
        return isinstance(day, date) and self.get(day) is not None

    def between(self, start: date, end: date) -> dict[date, Holiday]:
        out = {}
        for y in range(start.year, end.year + 1):
            out.update({d: h for d, h in self.year(y).items() if h.active and start <= d <= end})
        return out


NO_HOLIDAYS = Holidays(nationals=False)  # sem feriado nenhum (o cálculo puro dos painéis, nos testes)


def load_holidays(conn) -> Holidays:
    return Holidays(conn.execute("SELECT * FROM holidays").fetchall())


def holidays(db: Database) -> Holidays:
    with db.connect() as conn:
        return load_holidays(conn)


def can_manage_holidays(person: Person | None) -> bool:
    return person is not None and (person.is_manager or person.is_admin)


def add_local_holiday(db: Database, now: datetime, actor: Person, day: date, name: str) -> None:
    if not can_manage_holidays(actor):
        raise PermissionError("Só o gestor e os administradores mudam os feriados.")
    name = " ".join((name or "").split())
    if not name:
        raise ValidationError("Informe o nome do feriado.")
    if len(name) > MAX_PLACE:
        raise ValidationError(f"Nome muito longo (máximo {MAX_PLACE}).")
    if day in national(day.year):
        raise ValidationError("Esse dia já é feriado nacional: ligue ou desligue na lista.")
    with db.connect() as conn:
        conn.execute("INSERT INTO holidays(day, name, source, active) VALUES (?, ?, 'local', 1) "
                     "ON CONFLICT(day) DO UPDATE SET name = excluded.name, active = 1", (day.isoformat(), name))
        log_event(conn, now, actor.id, "feriado_criado", "calendario:feriado", f"{day:%d/%m/%Y} {name}")


def set_holiday_active(db: Database, now: datetime, actor: Person, day: date, active: bool) -> None:
    """Liga ou desliga um feriado nacional (por exemplo, a empresa trabalha no Carnaval) ou um da cidade."""
    if not can_manage_holidays(actor):
        raise PermissionError("Só o gestor e os administradores mudam os feriados.")
    with db.connect() as conn:
        h = load_holidays(conn).year(day.year).get(day)
        if h is None:
            raise ValidationError("Feriado não encontrado.")
        conn.execute("INSERT INTO holidays(day, name, source, active) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT(day) DO UPDATE SET active = excluded.active",
                     (day.isoformat(), h.name, h.source, int(active)))
        log_event(conn, now, actor.id, "feriado_ligado" if active else "feriado_desligado", "calendario:feriado",
                  f"{day:%d/%m/%Y} {h.name}")


def remove_local_holiday(db: Database, now: datetime, actor: Person, day: date) -> None:
    if not can_manage_holidays(actor):
        raise PermissionError("Só o gestor e os administradores mudam os feriados.")
    with db.connect() as conn:
        r = conn.execute("SELECT name FROM holidays WHERE day = ? AND source = 'local'", (day.isoformat(),)).fetchone()
        if r is None:
            raise ValidationError("Feriado não encontrado.")
        conn.execute("DELETE FROM holidays WHERE day = ?", (day.isoformat(),))
        log_event(conn, now, actor.id, "feriado_removido", "calendario:feriado", f"{day:%d/%m/%Y} {r['name']}")


def business_days(year: int, month: int, hol: Holidays = NO_HOLIDAYS, saturdays: bool = False) -> list[date]:
    """Dias úteis do mês: segunda a sexta (e sábado, se pedir), sem os feriados ativos."""
    last = cal.monthrange(year, month)[1]
    limit = 6 if saturdays else 5
    return [d for d in (date(year, month, n) for n in range(1, last + 1)) if d.weekday() < limit and d not in hol]


# ---------- compromissos ----------

@dataclass(frozen=True)
class Event:
    id: int
    title: str
    kind: str
    starts_on: date
    ends_on: date | None
    starts_at: str | None
    ends_at: str | None
    place: str | None
    description: str | None
    visibility: str
    reserved: bool
    repeat: str
    created_by: int | None
    people: tuple[int, ...] = ()

    @property
    def span(self) -> int:
        return (self.ends_on - self.starts_on).days if self.ends_on else 0

    @property
    def time_label(self) -> str:
        if not self.starts_at:
            return "dia todo"
        return self.starts_at + (f"–{self.ends_at}" if self.ends_at else "")


def _event_row(r, people: tuple[int, ...]) -> Event:
    return Event(r["id"], r["title"], r["kind"], date.fromisoformat(r["starts_on"]),
                 date.fromisoformat(r["ends_on"]) if r["ends_on"] else None, r["starts_at"], r["ends_at"],
                 r["place"], r["description"], r["visibility"], bool(r["reserved"]), r["repeat"], r["created_by"],
                 people)


def can_see_event(e: Event, person: Person) -> bool:
    """O compromisso aparece para a pessoa? ("só eu": só quem criou)."""
    return e.visibility == "equipe" or e.created_by == person.id


def can_see_title(e: Event, person: Person) -> bool:
    if not can_see_event(e, person):
        return False
    return (not e.reserved or person.is_manager or person.is_admin or person.id == e.created_by
            or person.id in e.people)


def can_edit_event(e: Event, person: Person) -> bool:
    if e.visibility == "pessoal":
        return e.created_by == person.id
    return person.id == e.created_by or person.is_manager or person.is_admin


def _load_events(conn, extra: str = "", args: tuple = ()) -> list[Event]:
    rows = conn.execute("SELECT * FROM events_cal WHERE deleted = 0" + extra, args).fetchall()
    people: dict[int, list[int]] = {}
    for r in conn.execute("SELECT event_id, person_id FROM event_people"):
        people.setdefault(r["event_id"], []).append(r["person_id"])
    return [_event_row(r, tuple(sorted(people.get(r["id"], [])))) for r in rows]


def get_event(db: Database, event_id: int) -> Event | None:
    with db.connect() as conn:
        found = _load_events(conn, " AND id = ?", (event_id,))
    return found[0] if found else None


def all_events(db: Database) -> dict[int, Event]:
    """Todos os compromissos, apagados também (o histórico ainda fala deles)."""
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM events_cal").fetchall()
        people: dict[int, list[int]] = {}
        for r in conn.execute("SELECT event_id, person_id FROM event_people"):
            people.setdefault(r["event_id"], []).append(r["person_id"])
    return {r["id"]: _event_row(r, tuple(sorted(people.get(r["id"], [])))) for r in rows}


def _clean_event(title, kind, starts_on, ends_on, starts_at, ends_at, place, description, visibility, repeat):
    title = " ".join((title or "").split())
    place = " ".join((place or "").split()) or None
    description = (description or "").replace("\r\n", "\n").strip() or None
    starts_at, ends_at = (starts_at or "").strip() or None, (ends_at or "").strip() or None
    if not title:
        raise ValidationError("Informe o título.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Título muito longo (máximo {MAX_TITLE}).")
    if kind not in KINDS:
        raise ValidationError("Escolha o tipo.")
    if repeat not in REPEATS:
        raise ValidationError("Repetição inválida.")
    if visibility not in ("equipe", "pessoal"):
        raise ValidationError("Escolha quem vê.")
    if starts_on is None:
        raise ValidationError("Informe a data.")
    if ends_on == starts_on:
        ends_on = None
    if ends_on is not None and ends_on < starts_on:
        raise ValidationError("A data final precisa ser depois da inicial.")
    if ends_on is not None and (ends_on - starts_on).days > MAX_DAYS:
        raise ValidationError(f"Um compromisso pode durar até {MAX_DAYS} dias.")
    for value, label in ((starts_at, "início"), (ends_at, "fim")):
        if value is not None and not _HHMM.fullmatch(value):
            raise ValidationError(f"Horário de {label} inválido (use HH:MM).")
    if ends_at and not starts_at:
        raise ValidationError("Informe também o horário de início.")
    if ends_at and starts_at and ends_at <= starts_at and ends_on is None:
        raise ValidationError("O fim precisa ser depois do início.")
    if place and len(place) > MAX_PLACE:
        raise ValidationError(f"Local muito longo (máximo {MAX_PLACE}).")
    if description and len(description) > MAX_DESCRIPTION:
        raise ValidationError(f"Descrição muito longa (máximo {MAX_DESCRIPTION}).")
    return title, place, description, starts_at, ends_at, ends_on


def save_event(db: Database, now: datetime, actor: Person, event_id: int | None, *, title: str, kind: str,
               starts_on: date | None, ends_on: date | None = None, starts_at: str = "", ends_at: str = "",
               place: str = "", description: str = "", visibility: str = "equipe", reserved: bool = False,
               repeat: str = "", people: list[int] = ()) -> Event:
    title, place, description, starts_at, ends_at, ends_on = _clean_event(
        title, kind, starts_on, ends_on, starts_at, ends_at, place, description, visibility, repeat)
    if visibility == "pessoal":
        reserved, people = False, []  # "só eu" já não aparece para ninguém
    with db.connect() as conn:
        active = {r[0] for r in conn.execute("SELECT id FROM people WHERE active = 1")}
        chosen = sorted({int(p) for p in people})
        current = None
        if event_id is not None:
            found = _load_events(conn, " AND id = ?", (event_id,))
            current = found[0] if found else None
            if current is None:
                raise ValidationError("Compromisso não encontrado.")
            if not can_edit_event(current, actor):
                raise PermissionError("Muda um compromisso quem criou, o gestor e os administradores.")
        keep = set(current.people) if current else set()
        if any(p not in active and p not in keep for p in chosen):
            raise ValidationError("Escolha só pessoas da equipe.")
        values = (title, kind, starts_on.isoformat(), ends_on.isoformat() if ends_on else None, starts_at, ends_at,
                  place, description, visibility, int(reserved), repeat, now.isoformat(timespec="seconds"))
        if current is None:
            cur = conn.execute("INSERT INTO events_cal(title, kind, starts_on, ends_on, starts_at, ends_at, place, "
                               "description, visibility, reserved, repeat, updated_at, created_by, created_at) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (*values, actor.id, now.isoformat(timespec="seconds")))
            event_id, kind_log = cur.lastrowid, "compromisso_criado"
        else:
            conn.execute("UPDATE events_cal SET title = ?, kind = ?, starts_on = ?, ends_on = ?, starts_at = ?, "
                         "ends_at = ?, place = ?, description = ?, visibility = ?, reserved = ?, repeat = ?, "
                         "updated_at = ? WHERE id = ?", (*values, event_id))
            kind_log = "compromisso_editado"
        conn.execute("DELETE FROM event_people WHERE event_id = ?", (event_id,))
        conn.executemany("INSERT INTO event_people(event_id, person_id) VALUES (?, ?)",
                         [(event_id, p) for p in chosen])
        if visibility == "equipe":  # "só eu" não vai para o histórico, que toda a equipe lê
            log_event(conn, now, actor.id, kind_log, f"compromisso:{event_id}", title)
        return _load_events(conn, " AND id = ?", (event_id,))[0]


def delete_event(db: Database, now: datetime, actor: Person, event_id: int) -> None:
    with db.connect() as conn:
        found = _load_events(conn, " AND id = ?", (event_id,))
        if not found:
            raise ValidationError("Compromisso não encontrado.")
        e = found[0]
        if not can_edit_event(e, actor):
            raise PermissionError("Apaga um compromisso quem criou, o gestor e os administradores.")
        conn.execute("UPDATE events_cal SET deleted = 1 WHERE id = ?", (event_id,))
        if e.visibility == "equipe":
            log_event(conn, now, actor.id, "compromisso_excluido", f"compromisso:{event_id}", e.title)


def _add_months(d: date, months: int) -> date | None:
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return date(y, m, d.day) if d.day <= cal.monthrange(y, m)[1] else None  # dia 31 num mês de 30: pula


def occurrences(e: Event, start: date, end: date) -> list[date]:
    """Os dias em que o compromisso começa dentro (ou passa por) [start, end]."""
    out = []
    first = e.starts_on
    if e.repeat == "":
        candidates = [first]
    elif e.repeat == "semanal":
        skip = max(0, (start - first).days - e.span) // 7
        candidates = []
        d = first + timedelta(weeks=skip)
        while d <= end:
            candidates.append(d)
            d += timedelta(weeks=1)
    elif e.repeat == "mensal":
        candidates, n = [], max(0, (start.year - first.year) * 12 + start.month - first.month - 1)
        while True:
            d = _add_months(first, n)
            n += 1
            if d is None:
                continue
            if d > end:
                break
            candidates.append(d)
    else:  # anual
        candidates = []
        for y in range(max(first.year, start.year - 1), end.year + 1):
            try:
                candidates.append(first.replace(year=y))
            except ValueError:
                continue  # 29/02
    for d in candidates:
        if d >= first and d <= end and d + timedelta(days=e.span) >= start:
            out.append(d)
    return out


def events_between(db: Database, viewer: Person, start: date, end: date) -> list[tuple[date, Event]]:
    """Cada dia (dentro do período) de cada compromisso que a pessoa pode ver."""
    with db.connect() as conn:
        events = _load_events(conn)
    out = []
    for e in events:
        if not can_see_event(e, viewer):
            continue
        for first in occurrences(e, start, end):
            for n in range(e.span + 1):
                d = first + timedelta(days=n)
                if start <= d <= end:
                    out.append((d, e))
    return sorted(out, key=lambda x: (x[0], x[1].starts_at or "", x[1].title.lower()))


# ---------- ausências ----------

@dataclass(frozen=True)
class Absence:
    id: int
    person_id: int
    starts_on: date
    ends_on: date
    reason: str | None
    created_by: int | None


def _absence_row(r) -> Absence:
    return Absence(r["id"], r["person_id"], date.fromisoformat(r["starts_on"]), date.fromisoformat(r["ends_on"]),
                   r["reason"], r["created_by"])


def can_mark_absence(actor: Person, person_id: int) -> bool:
    """A própria pessoa marca a sua; o gestor marca de qualquer um."""
    return actor.id == person_id or actor.is_manager


def can_see_reason(viewer: Person, a: Absence) -> bool:
    """O motivo (férias, curso, médico...) é só da pessoa e do gestor."""
    return viewer.id == a.person_id or viewer.is_manager


def add_absence(db: Database, now: datetime, actor: Person, person_id: int, starts_on: date | None,
                ends_on: date | None, reason: str = "") -> Absence:
    if not can_mark_absence(actor, person_id):
        raise PermissionError("Cada pessoa marca a própria ausência; o gestor marca a de qualquer um.")
    if starts_on is None:
        raise ValidationError("Informe o primeiro dia da ausência.")
    ends_on = ends_on or starts_on
    if ends_on < starts_on:
        raise ValidationError("O último dia precisa ser depois do primeiro.")
    if (ends_on - starts_on).days > 60:
        raise ValidationError("Uma ausência pode ter até 60 dias. Para mais, marque em partes.")
    reason = " ".join((reason or "").split()) or None
    if reason and len(reason) > MAX_REASON:
        raise ValidationError(f"Motivo muito longo (máximo {MAX_REASON}).")
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM people WHERE id = ? AND active = 1", (person_id,)).fetchone() is None:
            raise ValidationError("Escolha uma pessoa da equipe.")
        cur = conn.execute("INSERT INTO absences(person_id, starts_on, ends_on, reason, created_by, created_at) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (person_id, starts_on.isoformat(), ends_on.isoformat(), reason,
                                                         actor.id, now.isoformat(timespec="seconds")))
        # no histórico, só o período: o motivo fica de fora
        log_event(conn, now, actor.id, "ausencia_marcada", f"pessoa:{person_id}",
                  f"{starts_on:%d/%m}" + (f" a {ends_on:%d/%m}" if ends_on != starts_on else ""))
        return _absence_row(conn.execute("SELECT * FROM absences WHERE id = ?", (cur.lastrowid,)).fetchone())


def delete_absence(db: Database, now: datetime, actor: Person, absence_id: int) -> None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM absences WHERE id = ? AND deleted = 0", (absence_id,)).fetchone()
        if r is None:
            raise ValidationError("Ausência não encontrada.")
        a = _absence_row(r)
        if not can_mark_absence(actor, a.person_id):
            raise PermissionError("Cada pessoa tira a própria ausência; o gestor tira a de qualquer um.")
        conn.execute("UPDATE absences SET deleted = 1 WHERE id = ?", (absence_id,))
        log_event(conn, now, actor.id, "ausencia_removida", f"pessoa:{a.person_id}", f"{a.starts_on:%d/%m}")


def absences_between(db: Database, start: date, end: date) -> list[Absence]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM absences WHERE deleted = 0 AND starts_on <= ? AND ends_on >= ? "
                            "ORDER BY starts_on", (end.isoformat(), start.isoformat())).fetchall()
    return [_absence_row(r) for r in rows]


def absent_today(db: Database, today: date) -> dict[int, date]:
    """Quem está ausente hoje e até quando (para a faixa de presença da TV)."""
    out: dict[int, date] = {}
    for a in absences_between(db, today, today):
        out[a.person_id] = max(out.get(a.person_id, a.ends_on), a.ends_on)
    return out


# ---------- o que aparece em cada dia ----------

@dataclass(frozen=True)
class Item:
    """Uma linha do calendário num dia."""
    kind: str  # compromisso, feriado, ausencia, prazo, prioridade, rotina
    title: str
    time: str = ""
    link: str = ""
    color: str = ""
    initials: str = ""
    late: bool = False
    note: str = ""


FILTERS = {"compromissos": "Compromissos", "feriados": "Feriados", "ausencias": "Ausências",
           "prazos": "Prazos das demandas", "prioridades": "Prioridades do mês", "rotinas": "Rotinas",
           "rotinas_mes": "Rotinas do mês"}
DEFAULT_FILTERS = ("compromissos", "feriados", "ausencias", "prazos", "prioridades")  # rotinas lotariam o mês


def day_items(db: Database, viewer: Person, start: date, end: date, today: date,
              filters: tuple[str, ...] = DEFAULT_FILTERS) -> dict[date, list[Item]]:
    """Tudo o que a pessoa pode ver em cada dia do período, já com as reservadas mascaradas."""
    from .demands import can_see, is_overdue, RESERVED_TEXT as DEMAND_RESERVED
    from .people import list_people
    from .prioridades import is_late, list_month
    from .rotinas import list_routines

    people = {p.id: p for p in list_people(db, active_only=False)}
    out: dict[date, list[Item]] = {}

    def add(d: date, item: Item) -> None:
        out.setdefault(d, []).append(item)

    hol = holidays(db)
    if "feriados" in filters:
        for d, h in hol.between(start, end).items():
            add(d, Item("feriado", h.name, note="feriado" + (" da cidade" if h.source == "local" else "")))
    if "ausencias" in filters:
        for a in absences_between(db, start, end):
            p = people.get(a.person_id)
            if p is None:
                continue
            reason = a.reason if a.reason and can_see_reason(viewer, a) else ""
            d = max(a.starts_on, start)
            while d <= min(a.ends_on, end):
                add(d, Item("ausencia", f"{p.name} ausente", color=p.color, initials=p.initials,
                            note=(f"até {a.ends_on:%d/%m}" if a.ends_on != a.starts_on else "") +
                                 (f" · {reason}" if reason else "")))
                d += timedelta(days=1)
    if "compromissos" in filters:
        for d, e in events_between(db, viewer, start, end):
            title = e.title if can_see_title(e, viewer) else RESERVED_TEXT
            who = [people[p] for p in e.people if p in people]
            add(d, Item("compromisso", title, time=e.time_label, link=f"/calendario/{e.id}",
                        color=who[0].color if len(who) == 1 else "", initials=" ".join(p.initials for p in who),
                        note=("🔒 só eu" if e.visibility == "pessoal" else KINDS[e.kind]) +
                             (f" · {e.place}" if e.place and can_see_title(e, viewer) else "")))
    if "prazos" in filters:
        with db.connect() as conn:
            rows = conn.execute("SELECT * FROM demands WHERE deleted = 0 AND due BETWEEN ? AND ? AND routine_id IS NULL",
                                (start.isoformat(), end.isoformat())).fetchall()
        from .demands import _row as demand_row
        for r in rows:
            dm = demand_row(r)
            p = people.get(dm.owner_id)
            visible = can_see(dm, viewer)
            add(dm.due, Item("prazo", dm.title if visible else DEMAND_RESERVED,
                             link=f"/demandas/{dm.id}" if visible else "", color=p.color if p else "",
                             initials=p.initials if p else "", late=is_overdue(dm, today),
                             note="concluída" if dm.column == "done" else "prazo"))
    if "prioridades" in filters:
        month = date(start.year, start.month, 1)
        while month <= end:
            for item in list_month(db, f"{month:%Y-%m}"):
                if item.due_day is None:
                    continue
                last = cal.monthrange(month.year, month.month)[1]
                d = date(month.year, month.month, min(item.due_day, last))
                if start <= d <= end:
                    add(d, Item("prioridade", item.title, link="/prioridades", late=is_late(item, today),
                                note="feita" if item.done else "prioridade do mês"))
            month = _add_months(month, 1)
    if "rotinas" in filters:
        routines = [r for r in list_routines(db) if r.active]
        d = start
        while d <= end:
            for r in routines:
                if r.runs_on(d):
                    p = people.get(r.owner_id)
                    add(d, Item("rotina", r.name, time=r.starts_at, link="/rotinas", color=p.color if p else "",
                                initials=p.initials if p else "", note="rotina"))
            d += timedelta(days=1)
    if "rotinas_mes" in filters:  # fase 19: o calendário de rotinas do gestor, com a cor da categoria
        from .rotinas_mes import by_day
        for d, occs in by_day(db, start, end).items():
            for o in occs:
                add(d, Item("rotina_mes", f"{o.category.name}: {o.routine.title}", link="/calendario?visao=rotinas",
                            color=o.category.color, late=o.routine.highlight and not o.done,
                            note="feita" if o.done else "rotina do mês"))
    order = {"feriado": 0, "ausencia": 1, "compromisso": 2, "rotina_mes": 3, "rotina": 4, "prazo": 5, "prioridade": 6}
    for items in out.values():
        items.sort(key=lambda i: (order[i.kind], i.time or "99", i.title.lower()))
    return out


# ---------- TV: tela Agenda ----------

AGENDA_DAYS = 4  # hoje e os próximos dias úteis: no máximo 4 grupos lado a lado (a TV nunca rola)


def tv_agenda(db: Database, now: datetime) -> dict | None:
    """Hoje e os próximos dias úteis: compromissos da equipe (sem descrição; reservado mascarado),
    feriados e quem está ausente (só "Ausente", nunca o motivo). Sem nada, sai da rotação."""
    from .people import list_people

    today = now.date()
    hol = holidays(db)
    days = [today]
    d = today
    while len(days) < AGENDA_DAYS:
        d += timedelta(days=1)
        if d.weekday() < 6 or d in hol:  # domingo só entra se for feriado (para avisar)
            days.append(d)
    end = days[-1]
    people = {p.id: p for p in list_people(db, active_only=False)}
    with db.connect() as conn:
        events = [e for e in _load_events(conn) if e.visibility == "equipe"]
    groups = []
    for d in days:
        items = []
        h = hol.get(d)
        if h:
            items.append({"tipo": "feriado", "titulo": h.name, "hora": "feriado"})
        for e in events:
            if not any(first <= d <= first + timedelta(days=e.span) for first in occurrences(e, d, d)):
                continue
            who = [people[p] for p in e.people if p in people]
            items.append({"tipo": "compromisso", "titulo": RESERVED_TEXT if e.reserved else e.title,
                          "hora": e.time_label, "reservado": e.reserved, "rotulo": KINDS[e.kind],
                          "pessoas": [{"initials": p.initials, "color": p.color} for p in who]})
        for a in absences_between(db, d, d):
            p = people.get(a.person_id)
            if p and p.active:
                items.append({"tipo": "ausencia", "titulo": "Ausente", "hora": f"até {a.ends_on:%d/%m}",
                              "pessoas": [{"initials": p.initials, "color": p.color}], "nome": p.name})
        items.sort(key=lambda i: ({"feriado": 0, "compromisso": 1, "ausencia": 2}[i["tipo"]], i["hora"]))
        if items:
            label = "Hoje" if d == today else "Amanhã" if d == today + timedelta(days=1) else WEEKDAYS[d.weekday()].capitalize()
            groups.append({"label": label, "data": f"{d:%d/%m}", "itens": items})
    return {"groups": groups} if groups else None
