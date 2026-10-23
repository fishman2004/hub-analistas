"""As telas da TV e a rotação entre elas.

Cada tela é registrada aqui com um nome, o tempo padrão e uma função que monta os dados dela.
A função devolve None quando a tela não tem o que mostrar: assim ela sai da rotação sozinha.
Para uma fase nova "plugar" uma tela: escreva a função, registre em SCREENS e crie o desenho
correspondente em static/tv-telas/ (ver tv.js). Nenhuma outra tela precisa mudar.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from .calendario import tv_agenda
from .db import Database, log_event
from .demands import Demand, board, is_overdue, tv_card
from .envios import tv_envios
from .paineis import tv_focos, tv_fornecedores, tv_metas_dia, tv_metas_mes
from .people import Person, ValidationError, list_people
from .prioridades import tv_prioridades
from .rotinas_mes import tv_rotinas_mes
from .trilha import tv_trilhas

@dataclass(frozen=True)
class Screen:
    id: str
    label: str
    default_seconds: int
    build: Callable[[Database, datetime], dict | None]
    always: bool = False  # o Quadro está sempre na rotação


MIN_SECONDS, MAX_SECONDS = 5, 300
PAGE_DEFAULT, PAGE_MIN, PAGE_MAX = 10, 4, 60


# ---------- telas ----------

def _quadro(db: Database, now: datetime) -> dict:
    return {}  # o Quadro usa "columns" e "counts", que já vão na resposta da TV


def _prazos(db: Database, now: datetime) -> dict | None:
    """Prazos da semana: atrasadas e o que vence nos próximos 6 dias (reservadas mascaradas como no Quadro)."""
    today = now.date()
    columns = board(db, now)
    owners = {p.id: p for p in list_people(db, active_only=False)}
    # rotina de hoje não é "prazo" (ela tem horário e está no Quadro): só entra aqui se atrasar
    open_demands = [d for d in columns["todo"] + columns["doing"] if d.due and d.due <= today + timedelta(days=6)
                    and (d.routine_id is None or is_overdue(d, today))]
    if not open_demands:
        return None
    groups: dict[str, list[Demand]] = {}
    for d in sorted(open_demands, key=lambda d: (d.due, d.created_at)):
        groups.setdefault(_day_label(d, today), []).append(d)
    return {"groups": [{"label": label, "cards": [tv_card(d, owners[d.owner_id], today, owners) for d in items]}
                       for label, items in groups.items()]}


def _day_label(d: Demand, today: date) -> str:
    if is_overdue(d, today):
        return "Atrasadas"
    if d.due == today:
        return "Hoje"
    if d.due == today + timedelta(days=1):
        return "Amanhã"
    return "Próximos dias"  # no máximo 4 grupos lado a lado: a TV nunca rola


SCREENS: list[Screen] = [
    Screen("quadro", "Quadro", 30, _quadro, always=True),
    # trilha do dia (fase 20): a trilha de horários de cada analista, com a luz do que foi feito
    Screen("trilhas", "Trilhas do dia", 25, tv_trilhas),
    Screen("prazos", "Prazos da semana", 15, _prazos),
    # calendário (fase 13): compromissos da equipe, feriados e ausências de hoje e dos próximos dias
    Screen("agenda", "Agenda", 15, tv_agenda),
    # rotinas do mês (fase 19): o calendário do mês inteiro e, depois, um zoom no dia de hoje;
    # desde a fase 24 com os compromissos da equipe também (o id fica "rotinas-mes" para não mexer nos modos)
    Screen("rotinas-mes", "Calendário do mês", 25, tv_rotinas_mes),
    # prioridades do início do mês (fase 8): fica na rotação até tudo estar feito
    Screen("prioridades", "Prioridades do mês", 15, tv_prioridades),
    # painéis de dados (fase 5): só porcentagens, e só entram quando as planilhas estão na pasta
    Screen("metas-mes", "Metas do mês", 20, tv_metas_mes),
    Screen("metas-dia", "Metas do dia", 15, tv_metas_dia),
    Screen("produtos-foco", "Produtos foco", 15, tv_focos),
    Screen("fornecedores", "Fornecedores", 15, tv_fornecedores),
    # envios do Pombo (fase 9): só entra com a pasta do histórico configurada e algum envio hoje
    Screen("envios", "Envios do dia", 15, tv_envios),
]
SCREEN_IDS = {s.id for s in SCREENS}


# ---------- configurações ----------

def screen_config(db: Database) -> dict:
    """O modo Padrão (fase 14): tempo e se está ligada, para cada tela, mais o tempo de cada página das colunas.
    Os outros modos ficam na página Modos da TV."""
    from .modos import default_mode

    mode = default_mode(db)
    always = {s.id for s in SCREENS if s.always}
    defaults = {s.id: s.default_seconds for s in SCREENS}
    return {"screens": [{"id": s.id, "label": s.label, "seconds": s.seconds, "enabled": s.enabled,
                         "always": s.id in always, "default_seconds": defaults[s.id]} for s in mode.screens],
            "page_seconds": mode.page_seconds}


def save_screen_config(db: Database, now: datetime, actor: Person, seconds: dict[str, str], enabled: set[str],
                       page_seconds: str) -> None:
    """Configurações → TV: muda o modo Padrão (só administradores, como antes)."""
    from .modos import default_mode, save_mode

    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    mode = default_mode(db)
    for s in SCREENS:
        raw = seconds.get(s.id, "")
        if not raw.isdigit() or not MIN_SECONDS <= int(raw) <= MAX_SECONDS:
            raise ValidationError(f"Tempo de \"{s.label}\": use de {MIN_SECONDS} a {MAX_SECONDS} segundos.")
    if not page_seconds.isdigit() or not PAGE_MIN <= int(page_seconds) <= PAGE_MAX:
        raise ValidationError(f"Tempo de cada página: use de {PAGE_MIN} a {PAGE_MAX} segundos.")
    always = {s.id for s in SCREENS if s.always}
    save_mode(db, now, actor, mode.id, name=mode.name, page_seconds=page_seconds, sound=mode.sound,
              hide_titles=mode.hide_titles, rule={}, rule_on=False,
              screens=[(s.id, seconds[s.id], s.id in always or s.id in enabled) for s in mode.screens])
    with db.connect() as conn:
        log_event(conn, now, actor.id, "config_tv", "config:tv", "")


def rotation(db: Database, now: datetime, mode=None) -> dict:
    """O que a TV recebe: as telas que entram na rotação agora (com tempo e dados) e o tempo das páginas.
    A ordem, os tempos e as telas ligadas vêm do modo que vale agora (fase 14). Se nenhuma tela do modo
    tiver o que mostrar, o Quadro aparece: a TV nunca fica vazia."""
    from .modos import current

    if mode is None:
        mode = current(db, now).mode
    builders = {s.id: s.build for s in SCREENS}
    screens = []
    for s in mode.screens:
        if not s.enabled:
            continue
        data = builders[s.id](db, now)
        if data is None:
            continue  # sem conteúdo: sai da rotação até ter de novo
        screens.append({"id": s.id, "label": s.label, "seconds": s.seconds, "data": data})
    if not screens:
        quadro = next(s for s in SCREENS if s.always)
        seconds = next((s.seconds for s in mode.screens if s.id == quadro.id), quadro.default_seconds)
        screens.append({"id": quadro.id, "label": quadro.label, "seconds": seconds, "data": quadro.build(db, now)})
    return {"screens": screens, "page_seconds": mode.page_seconds}
