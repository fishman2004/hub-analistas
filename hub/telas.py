"""As telas da TV e a rotação entre elas.

Cada tela é registrada aqui com um nome, o tempo padrão e uma função que monta os dados dela.
A função devolve None quando a tela não tem o que mostrar: assim ela sai da rotação sozinha.
Para uma fase nova "plugar" uma tela: escreva a função, registre em SCREENS e crie o desenho
correspondente em static/tv-telas/ (ver tv.js). Nenhuma outra tela precisa mudar.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from .db import Database, log_event
from .demands import Demand, board, is_overdue, tv_card
from .envios import tv_envios
from .paineis import tv_focos, tv_fornecedores, tv_metas_dia, tv_metas_mes
from .people import Person, ValidationError, list_people
from .prioridades import tv_prioridades

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
    return {"groups": [{"label": label, "cards": [tv_card(d, owners[d.owner_id], today) for d in items]}
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
    Screen("prazos", "Prazos da semana", 15, _prazos),
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

def _settings(db: Database) -> dict[str, str]:
    with db.connect() as conn:
        return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}


def screen_config(db: Database) -> dict:
    """Tempo e se está ligada, para cada tela, mais o tempo de cada página das colunas."""
    stored = _settings(db)
    screens = []
    for s in SCREENS:
        seconds = int(stored.get(f"tela.{s.id}.segundos", s.default_seconds))
        enabled = s.always or stored.get(f"tela.{s.id}.ligada", "1") == "1"
        screens.append({"id": s.id, "label": s.label, "seconds": seconds, "enabled": enabled, "always": s.always,
                        "default_seconds": s.default_seconds})
    return {"screens": screens, "page_seconds": int(stored.get("tv.pagina.segundos", PAGE_DEFAULT))}


def save_screen_config(db: Database, now: datetime, actor: Person, seconds: dict[str, str], enabled: set[str],
                       page_seconds: str) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    values: dict[str, str] = {}
    for s in SCREENS:
        raw = seconds.get(s.id, "")
        if not raw.isdigit() or not MIN_SECONDS <= int(raw) <= MAX_SECONDS:
            raise ValidationError(f"Tempo de \"{s.label}\": use de {MIN_SECONDS} a {MAX_SECONDS} segundos.")
        values[f"tela.{s.id}.segundos"] = str(int(raw))
        if not s.always:
            values[f"tela.{s.id}.ligada"] = "1" if s.id in enabled else "0"
    if not page_seconds.isdigit() or not PAGE_MIN <= int(page_seconds) <= PAGE_MAX:
        raise ValidationError(f"Tempo de cada página: use de {PAGE_MIN} a {PAGE_MAX} segundos.")
    values["tv.pagina.segundos"] = str(int(page_seconds))
    with db.connect() as conn:
        conn.executemany("INSERT INTO settings(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", values.items())
        log_event(conn, now, actor.id, "config_tv", "config:tv", "")


def rotation(db: Database, now: datetime) -> dict:
    """O que a TV recebe: as telas que entram na rotação agora (com tempo e dados) e o tempo das páginas."""
    config = screen_config(db)
    builders = {s.id: s.build for s in SCREENS}
    screens = []
    for s in config["screens"]:
        if not s["enabled"]:
            continue
        data = builders[s["id"]](db, now)
        if data is None:
            continue  # sem conteúdo: sai da rotação até ter de novo
        screens.append({"id": s["id"], "label": s["label"], "seconds": s["seconds"], "data": data})
    return {"screens": screens, "page_seconds": config["page_seconds"]}
