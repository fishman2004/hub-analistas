"""Banco de horas: saldo inicial (planilha do RH, pelo gestor) e a entrada e saída de cada dia.

Não substitui o RH: serve para o analista saber se está com horas extras ou negativas. Cada um
lança a entrada e a saída do dia pelo comprovante do ponto. Almoço não tem ponto: a jornada já é
o horário inteiro (das 8h às 18h = 10:00), com o almoço dentro.

Dado sensível. Quem pode ver as horas de alguém: a própria pessoa e o gestor (can_see). A TV não
importa este módulo e o endereço dela nunca consulta estas tabelas (um teste confere).

O saldo é calculado, não guardado: saldo base + a diferença de cada dia lançado depois da data do
saldo base (trabalhado menos a jornada do dia). Dia sem lançamento não conta: aparece na lista de
"dias sem lançamento" para a pessoa completar.
"""

import csv
import io
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import BinaryIO

from .calendario import load_holidays
from .db import Database, log_event
from .people import Person, ValidationError, list_people
from .planilhas import EXTENSIONS, PlanilhaError, day as parse_day, normalize, read_rows

SETTING_WEEK = "horas.jornada.semana"
SETTING_SATURDAY = "horas.jornada.sabado"
WEEK_DEFAULT, SATURDAY_DEFAULT = 10 * 60, 0  # das 8h às 18h de segunda a sexta; sábado sem jornada
MISSING_WINDOW = 31  # dias para trás na lista de dias sem lançamento
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


# ---------- quem vê ----------

def can_see(viewer: Person | None, person_id: int) -> bool:
    """As horas de alguém: só a própria pessoa e o gestor. Administrador não basta."""
    return viewer is not None and (viewer.id == person_id or viewer.is_manager)


def require_manager(actor: Person | None) -> None:
    if actor is None or not actor.is_manager:
        raise PermissionError("Só o gestor pode fazer isso.")


# ---------- horas em texto ----------

def parse_hhmm(text: str, label: str) -> int:
    """'08:05' ou '8:05' -> minutos desde a meia-noite."""
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValidationError(f"{label}: use o formato hh:mm (ex.: 08:05).")
    return int(m.group(1)) * 60 + int(m.group(2))


def hhmm(minutes: int | None) -> str:
    return "" if minutes is None else f"{minutes // 60:02d}:{minutes % 60:02d}"


def duration(minutes: int, signed: bool = True) -> str:
    """Saldo ou diferença: '+12:30', '-03:15', '00:00'."""
    sign = "-" if minutes < 0 else "+" if minutes > 0 and signed else ""
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def parse_duration(value: object) -> int:
    """Saldo como vem da planilha base: '12:30', '-03:15', '+1:05', '12,5' (horas), número de horas,
    ou hora/duração de verdade do Excel. Devolve minutos."""
    if isinstance(value, timedelta):
        return round(value.total_seconds() / 60)
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(value * 60)
    text = str(value or "").strip().replace(" ", "")
    m = re.fullmatch(r"([+-]?)(\d+):(\d{2})(?::\d{2})?", text)
    if m:
        minutes = int(m.group(2)) * 60 + int(m.group(3))
        return -minutes if m.group(1) == "-" else minutes
    m = re.fullmatch(r"([+-]?\d+(?:[.,]\d+)?)h?", text)
    if m:
        return round(float(m.group(1).replace(",", ".")) * 60)
    raise ValidationError(f"Saldo que não entendi: {text[:20]!r} (use hh:mm, ex.: -03:15).")


# ---------- jornada ----------

def _setting(conn, key: str, default: int) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return int(row[0]) if row else default


def journey_from(conn) -> dict:
    # feriados do calendário (fase 13): não pedem lançamento, e hora trabalhada neles é toda extra
    return {"semana": _setting(conn, SETTING_WEEK, WEEK_DEFAULT),
            "sabado": _setting(conn, SETTING_SATURDAY, SATURDAY_DEFAULT),
            "feriados": load_holidays(conn)}


def journey(db: Database) -> dict:
    with db.connect() as conn:
        return journey_from(conn)


def planned_for(day: date, j: dict) -> int:
    if day in j.get("feriados", ()):
        return 0
    if day.weekday() < 5:
        return j["semana"]
    return j["sabado"] if day.weekday() == 5 else 0


def save_journey(db: Database, now: datetime, actor: Person, week: str, saturday: str) -> None:
    require_manager(actor)
    values = {SETTING_WEEK: parse_hhmm(week, "Jornada de segunda a sexta"),
              SETTING_SATURDAY: parse_hhmm(saturday or "00:00", "Jornada de sábado")}
    with db.connect() as conn:
        for key, value in values.items():
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
        log_event(conn, now, actor.id, "horas_jornada", "config:horas",
                  f"{hhmm(values[SETTING_WEEK])} / sábado {hhmm(values[SETTING_SATURDAY])}")


# ---------- lançamentos ----------

@dataclass(frozen=True)
class Entry:
    day: date
    entrada: int
    saida: int
    planned: int

    @property
    def worked(self) -> int:
        return self.saida - self.entrada

    @property
    def diff(self) -> int:
        return self.worked - self.planned


def _entry(r, j: dict) -> Entry:
    d = date.fromisoformat(r["day"])
    return Entry(d, parse_hhmm(r["entrada"], ""), parse_hhmm(r["saida"], ""), planned_for(d, j))


def _balance_row(conn, person_id: int):
    return conn.execute("SELECT * FROM hours_balance WHERE person_id = ?", (person_id,)).fetchone()


def check_times(entrada: str, saida: str) -> tuple[int, int]:
    start = parse_hhmm(entrada, "Entrada")
    end = parse_hhmm(saida, "Saída")
    if end <= start:
        raise ValidationError("A saída tem de ser depois da entrada.")
    return start, end


def save_entry(db: Database, now: datetime, actor: Person, day: date, entrada: str, saida: str,
               correcting: bool = False) -> None:
    """Lança (ou corrige) um dia do próprio banco de horas. Cada um lança só o seu."""
    if day > now.date():
        raise ValidationError("Não dá para lançar um dia que ainda não chegou.")
    values = tuple(hhmm(t) for t in check_times(entrada, saida))
    with db.connect() as conn:
        base = _balance_row(conn, actor.id)
        if base and day <= date.fromisoformat(base["as_of"]):
            raise ValidationError(f"Esse dia já está no saldo base (até {date.fromisoformat(base['as_of']):%d/%m/%Y}).")
        old = conn.execute("SELECT * FROM hours_entries WHERE person_id = ? AND day = ?",
                           (actor.id, day.isoformat())).fetchone()
        stamp = now.isoformat(timespec="seconds")
        if old and not correcting:
            raise ValidationError(f"O dia {day:%d/%m} já foi lançado. Para mudar, use Corrigir na lista.")
        if old:
            before = f"{old['entrada']}–{old['saida']}"
            conn.execute("UPDATE hours_entries SET entrada = ?, saida = ?, updated_at = ? WHERE id = ?",
                         (*values, stamp, old["id"]))
            log_event(conn, now, actor.id, "horas_corrigido", f"horas:{actor.id}",
                      f"{day:%d/%m}: {before} → {values[0]}–{values[1]}")
        else:
            conn.execute("INSERT INTO hours_entries(person_id, day, entrada, saida, created_at, updated_at) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (actor.id, day.isoformat(), *values, stamp, stamp))
            log_event(conn, now, actor.id, "horas_lancado", f"horas:{actor.id}", f"{day:%d/%m}")


def delete_entry(db: Database, now: datetime, actor: Person, day: date) -> None:
    with db.connect() as conn:
        old = conn.execute("SELECT * FROM hours_entries WHERE person_id = ? AND day = ?",
                           (actor.id, day.isoformat())).fetchone()
        if old is None:
            raise ValidationError("Esse dia não está lançado.")
        conn.execute("DELETE FROM hours_entries WHERE id = ?", (old["id"],))
        log_event(conn, now, actor.id, "horas_excluido", f"horas:{actor.id}",
                  f"{day:%d/%m}: {old['entrada']}–{old['saida']}")


# ---------- saldo ----------

@dataclass(frozen=True)
class Summary:
    person_id: int
    base: int | None  # saldo base em minutos (None: o gestor ainda não lançou)
    as_of: date | None
    entries: list[Entry]  # do mais novo para o mais antigo, só os que contam no saldo
    missing: list[date]

    @property
    def balance(self) -> int:
        return (self.base or 0) + sum(e.diff for e in self.entries)

    @property
    def last_day(self) -> date | None:
        return self.entries[0].day if self.entries else None


def summary(db: Database, person_id: int, today: date) -> Summary:
    with db.connect() as conn:
        j = journey_from(conn)
        base = _balance_row(conn, person_id)
        as_of = date.fromisoformat(base["as_of"]) if base else None
        rows = conn.execute("SELECT * FROM hours_entries WHERE person_id = ? AND day > ? ORDER BY day DESC",
                            (person_id, as_of.isoformat() if as_of else "")).fetchall()
    entries = [_entry(r, j) for r in rows]
    done = {e.day for e in entries}
    start = today - timedelta(days=MISSING_WINDOW)
    if as_of and as_of >= start:
        start = as_of + timedelta(days=1)
    elif not as_of and entries:
        start = max(start, min(done))  # sem saldo base: conta a partir do primeiro lançamento
    elif not as_of:
        start = today
    missing = [d for d in (start + timedelta(n) for n in range((today - start).days))
               if planned_for(d, j) > 0 and d not in done]
    return Summary(person_id, base["minutes"] if base else None, as_of, entries, missing[::-1])


def team(db: Database, today: date) -> list[tuple[Person, Summary]]:
    return [(p, summary(db, p.id, today)) for p in list_people(db)]


def set_balance(db: Database, now: datetime, actor: Person, person_id: int, minutes: int, as_of: date) -> None:
    """Saldo base de alguém até uma data (inclusive). Lançamentos até essa data deixam de contar."""
    require_manager(actor)
    if as_of > now.date():
        raise ValidationError("A data do saldo não pode ser no futuro.")
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM people WHERE id = ? AND active = 1", (person_id,)).fetchone() is None:
            raise ValidationError("Pessoa não encontrada.")
        _store_balance(conn, now, actor, person_id, minutes, as_of, "ajuste")


def _store_balance(conn, now: datetime, actor: Person, person_id: int, minutes: int, as_of: date, how: str) -> None:
    conn.execute("INSERT INTO hours_balance(person_id, minutes, as_of, updated_at, updated_by) VALUES (?, ?, ?, ?, ?) "
                 "ON CONFLICT(person_id) DO UPDATE SET minutes = excluded.minutes, as_of = excluded.as_of, "
                 "updated_at = excluded.updated_at, updated_by = excluded.updated_by",
                 (person_id, minutes, as_of.isoformat(), now.isoformat(timespec="seconds"), actor.id))
    log_event(conn, now, actor.id, "horas_saldo", f"horas:{person_id}",
              f"{how}: {duration(minutes)} até {as_of:%d/%m/%Y}")


IMPORT_COLUMNS = {"nome": "NOME", "saldo": "SALDO"}


def import_balances(db: Database, now: datetime, actor: Person, filename: str, data: BinaryIO) -> tuple[int, list[str]]:
    """Planilha base (NOME, SALDO e, se tiver, DATA): grava o saldo base de cada pessoa encontrada.

    Sem a coluna DATA, o saldo vale até ontem. O arquivo não fica guardado no Hub: é lido e descartado.
    Devolve quantas pessoas foram atualizadas e os nomes da planilha que não bateram com ninguém.
    """
    require_manager(actor)
    suffix = Path(filename or "").suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValidationError(f"Envie a planilha em {', '.join(EXTENSIONS)}.")
    fd, temp = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data.read())
        try:
            rows = read_rows(Path(temp), {**IMPORT_COLUMNS, "data": "DATA"})
        except PlanilhaError as exc:
            if "DATA" not in str(exc) or "NOME" in str(exc) or "SALDO" in str(exc):
                raise ValidationError(str(exc)) from None
            rows = read_rows(Path(temp), IMPORT_COLUMNS)
    except PlanilhaError as exc:
        raise ValidationError(str(exc)) from None
    finally:
        os.unlink(temp)
    people = {normalize(p.name): p for p in list_people(db)}
    yesterday = now.date() - timedelta(days=1)
    parsed, unknown = [], []
    for r in rows:
        name = " ".join(str(r["nome"] or "").split())
        if not name:
            continue
        person = people.get(normalize(name))
        if person is None:
            unknown.append(name)
            continue
        try:
            as_of = parse_day(r["data"]) if r.get("data") not in (None, "") else yesterday
            parsed.append((person, parse_duration(r["saldo"]), as_of))
        except (ValidationError, PlanilhaError) as exc:
            raise ValidationError(f"{name}: {exc}") from None
    with db.connect() as conn:  # tudo ou nada: um erro no meio não deixa metade importada
        for person, minutes, as_of in parsed:
            _store_balance(conn, now, actor, person.id, minutes, as_of, "planilha")
    return len(parsed), unknown


# ---------- exportar (gestor) ----------

def export_rows(db: Database, today: date, kind: str, start: date | None = None, end: date | None = None) -> list[list]:
    if kind == "saldos":
        rows = [["Nome", "Saldo", "Saldo base", "Saldo base até", "Último dia lançado", "Dias sem lançamento"]]
        for p, s in team(db, today):
            rows.append([p.name, duration(s.balance), duration(s.base) if s.base is not None else "",
                         f"{s.as_of:%d/%m/%Y}" if s.as_of else "", f"{s.last_day:%d/%m/%Y}" if s.last_day else "",
                         len(s.missing)])
        return rows
    rows = [["Nome", "Dia", "Dia da semana", "Entrada", "Saída", "Horas no dia", "Jornada", "Diferença"]]
    for p, s in team(db, today):
        for e in sorted(s.entries, key=lambda e: e.day):
            if (start and e.day < start) or (end and e.day > end):
                continue
            rows.append([p.name, f"{e.day:%d/%m/%Y}", DIAS[e.day.weekday()], hhmm(e.entrada), hhmm(e.saida),
                         duration(e.worked, False), duration(e.planned, False), duration(e.diff)])
    return rows


def to_csv(rows: list[list]) -> bytes:
    out = io.StringIO()
    csv.writer(out, delimiter=";").writerows(rows)  # ";" e BOM: o Excel em português abre direto
    return ("﻿" + out.getvalue()).encode("utf-8")


def to_xlsx(rows: list[list], title: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = title[:31]
    for row in rows:
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
