"""Controle da TV da sala pelo app (fase 10): pausar numa tela, trocar de tela, passar a página e retomar.

A pausa fica na tabela settings (sem migração) e sempre tem prazo, para a TV nunca ficar esquecida
parada: passou do prazo, ela some sozinha (calculado, não agendado). Qual tela está na TV agora o
servidor só guarda na memória, a partir da própria busca da TV (/api/tv?tela=...).
"""

import json
import threading
from datetime import datetime, time, timedelta

from .db import Database, get_setting, log_event, put_setting
from .people import Person, ValidationError
from .telas import SCREENS, rotation

PAUSE_SETTING = "tv.pausa"
DEFAULT_MINUTES = 15
DURATIONS = {"5": "5 minutos", "15": "15 minutos", "30": "30 minutos", "60": "1 hora", "dia": "até o fim do dia"}
SEEN_FRESH = timedelta(seconds=30)  # sem busca da TV há mais que isso: "a TV não está conectada"
LABELS = {s.id: s.label for s in SCREENS}


def _until(now: datetime, minutes: str) -> datetime:
    if minutes == "dia":
        return datetime.combine(now.date(), time(23, 59, 59))
    if minutes not in DURATIONS:
        raise ValidationError("Escolha por quanto tempo a TV fica pausada.")
    return now + timedelta(minutes=int(minutes))


def current_pause(db: Database, now: datetime) -> dict | None:
    """A pausa que vale agora: {tela, ate, por, pagina}, ou None (sem pausa ou já passou do prazo)."""
    raw = get_setting(db, PAUSE_SETTING)
    if not raw:
        return None
    try:
        pause = json.loads(raw)
        if datetime.fromisoformat(pause["ate"]) <= now:
            return None
    except (ValueError, KeyError, TypeError):
        return None  # valor estragado: como se não houvesse pausa
    return pause


def _save(db: Database, now: datetime, actor: Person, screen: str, until: datetime, page: int, kind: str) -> None:
    value = {"tela": screen, "ate": until.isoformat(timespec="seconds"), "por": actor.id, "pagina": page}
    with db.connect() as conn:
        put_setting(conn, PAUSE_SETTING, json.dumps(value))
        if kind:
            log_event(conn, now, actor.id, kind, "tv", LABELS.get(screen, screen))


def pause(db: Database, now: datetime, actor: Person, screen: str, minutes: str = str(DEFAULT_MINUTES)) -> None:
    if screen not in LABELS:
        raise ValidationError("Escolha uma tela da TV.")
    current = current_pause(db, now)
    page = current["pagina"] if current else 0
    _save(db, now, actor, screen, _until(now, minutes), page, "tv_pausa")


def resume(db: Database, now: datetime, actor: Person) -> None:
    with db.connect() as conn:
        put_setting(conn, PAUSE_SETTING, None)
        log_event(conn, now, actor.id, "tv_retomada", "tv", "")


def step(db: Database, now: datetime, actor: Person, direction: int, seen: str | None) -> str:
    """Anterior (-1) ou próxima (+1) tela da rotação de agora, a partir da pausada ou da que está na TV.
    Sem pausa, a TV fica pausada na tela nova pelo tempo padrão. Devolve o id da tela nova."""
    ids = [s["id"] for s in rotation(db, now)["screens"]]
    current = current_pause(db, now)
    base = current["tela"] if current else seen
    i = ids.index(base) if base in ids else (-1 if direction > 0 else 0)
    screen = ids[(i + direction) % len(ids)] if ids else "quadro"
    until = datetime.fromisoformat(current["ate"]) if current else _until(now, str(DEFAULT_MINUTES))
    _save(db, now, actor, screen, until, current["pagina"] if current else 0, "tv_pausa")
    return screen


def next_page(db: Database, now: datetime, actor: Person) -> None:
    """Passa as colunas do Quadro para a página seguinte (a TV conta as mudanças do número 'pagina').
    Sem a TV pausada no Quadro, pausa nele primeiro."""
    current = current_pause(db, now)
    if current and current["tela"] == "quadro":
        until, page = datetime.fromisoformat(current["ate"]), current["pagina"] + 1
    else:
        until, page = (datetime.fromisoformat(current["ate"]) if current else _until(now, str(DEFAULT_MINUTES))), 1
    _save(db, now, actor, "quadro", until, page, "" if current and current["tela"] == "quadro" else "tv_pausa")


def tv_payload(db: Database, now: datetime, people: dict[int, Person]) -> dict | None:
    """O que a TV recebe da pausa: a tela, até quando, as iniciais de quem pausou e o contador de páginas."""
    current = current_pause(db, now)
    if current is None:
        return None
    who = people.get(current.get("por"))
    return {"tela": current["tela"], "ate": current["ate"], "iniciais": who.initials if who else "",
            "pagina": current.get("pagina", 0)}


class Seen:
    """Qual tela está na TV agora, pelo que a própria TV contou na última busca (só na memória)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value: tuple[str, bool, datetime] | None = None

    def update(self, screen: str, paused: bool, now: datetime) -> None:
        if screen not in LABELS:
            return
        with self._lock:
            self._value = (screen, paused, now)

    def get(self, now: datetime) -> dict | None:
        with self._lock:
            value = self._value
        if value is None or now - value[2] > SEEN_FRESH:
            return None
        screen, paused, at = value
        return {"tela": screen, "label": LABELS[screen], "pausada": paused, "segundos": int((now - at).total_seconds())}
