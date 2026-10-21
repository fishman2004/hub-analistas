"""Modos da TV (fase 14): cada modo é uma receita da rotação (quais telas, em que ordem, quanto tempo
cada uma, o tempo das páginas, o som do aviso e se os títulos aparecem).

Qual modo vale agora é calculado a cada busca da TV, não agendado: a escolha feita à mão na página
TV da sala (enquanto não passar do prazo) vence; depois, o primeiro modo da lista com uma regra
ligada que vale agora; sem nenhum, o Padrão. O Padrão nasce das configurações da TV que já existiam
(no primeiro uso, porque os tempos padrão das telas estão no código), e os outros modos prontos
nascem junto. Uma tela nova de uma fase futura entra no fim de cada modo, ligada só no Padrão.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .calendario import business_days, load_holidays
from .db import Database, get_setting, log_event, put_setting
from .people import Person, ValidationError

CHOICE_SETTING = "tv.modo"
MIN_SECONDS, MAX_SECONDS = 5, 300
PAGE_DEFAULT, PAGE_MIN, PAGE_MAX = 10, 4, 60
MAX_NAME = 40
DURATIONS = {"dia": "até o fim do dia", "60": "por 1 hora", "sempre": "até trocar de novo"}
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
RULES = {"": "Não liga sozinho", "primeiros_dias_uteis": "Primeiros dias úteis do mês",
         "ultimos_dias_uteis": "Últimos dias úteis do mês", "dias_do_mes": "Dias do mês",
         "dias_da_semana": "Dias da semana"}
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
_PANELS = ["metas-mes", "metas-dia", "produtos-foco", "fornecedores"]
_ALL = ["quadro", "prazos", "agenda", "prioridades", *_PANELS, "envios"]
_WORKWEEK = [0, 1, 2, 3, 4]

# os modos que vêm prontos: (chave, nome, telas e segundos, opções, regra, regra ligada)
BUILTINS = [
    ("padrao", "Padrão", None, {}, {}, False),
    ("inicio-mes", "Início de mês", [("quadro", 40), ("prioridades", 25), ("prazos", 20), ("agenda", 15),
                                     ("envios", 15)], {}, {"tipo": "primeiros_dias_uteis", "n": 5}, True),
    ("fim-mes", "Fim de mês", [("metas-mes", 30), ("metas-dia", 20), ("fornecedores", 20), ("produtos-foco", 20),
                               ("quadro", 15)], {}, {"tipo": "ultimos_dias_uteis", "n": 5}, True),
    # brainstorm (fase 14): prontos, mas sem ligar sozinhos
    ("fechamento-dia", "Fechamento do dia", [("metas-dia", 25), ("quadro", 20), ("envios", 15)], {},
     {"tipo": "dias_da_semana", "dias": _WORKWEEK, "janelas": [["16:30", "18:00"]]}, False),
    ("transferencias", "Hora das transferências", [("quadro", 30), ("envios", 15)], {},
     {"tipo": "dias_da_semana", "dias": _WORKWEEK, "janelas": [["14:40", "15:10"], ["16:40", "17:10"]]}, False),
    ("sabado", "Sábado", [("metas-dia", 25), ("envios", 15), ("quadro", 20)], {},
     {"tipo": "dias_da_semana", "dias": [5]}, False),
    ("campanha", "Campanha / Produtos foco", [("produtos-foco", 30), ("fornecedores", 25), ("metas-mes", 15),
                                              ("quadro", 15)], {}, {}, False),
    ("reuniao", "Reunião na sala", [(s, 60) for s in _ALL], {"sound": False}, {}, False),
    ("apresentacao", "Apresentação dos painéis", [(s, 45) for s in _PANELS], {}, {}, False),
    ("visita", "Visita", [("quadro", 30), ("agenda", 15)], {"hide_titles": True}, {}, False),
    ("so-quadro", "Só o quadro", [("quadro", 30)], {}, {}, False),
]


@dataclass(frozen=True)
class ModeScreen:
    id: str
    label: str
    seconds: int
    enabled: bool


@dataclass(frozen=True)
class Mode:
    id: int
    name: str
    builtin: str | None
    page_seconds: int
    sound: bool
    hide_titles: bool
    rule: dict
    rule_on: bool
    priority: int
    screens: tuple[ModeScreen, ...] = field(default=())

    @property
    def is_default(self) -> bool:
        return self.builtin == "padrao"

    @property
    def rule_text(self) -> str:
        return rule_label(self.rule)


def can_manage(person: Person | None) -> bool:
    """Criar, editar, duplicar e apagar modos e as regras: gestor e administradores."""
    return person is not None and (person.is_manager or person.is_admin)


# ---------- regras ----------

def rule_label(rule: dict) -> str:
    kind = rule.get("tipo", "")
    if kind == "primeiros_dias_uteis":
        text = f"do dia 1º até o {rule['n']}º dia útil do mês"
    elif kind == "ultimos_dias_uteis":
        text = f"nos {rule['n']} últimos dias úteis do mês"
    elif kind == "dias_do_mes":
        text = f"do dia {rule['de']} ao dia {rule['ate']} do mês"
    elif kind == "dias_da_semana":
        days = rule.get("dias", [])
        text = "seg a sex" if days == _WORKWEEK else ", ".join(WEEKDAYS[d] for d in days)
    else:
        return ""
    windows = rule.get("janelas") or []
    if windows:
        text += ", " + " e ".join(f"das {a} às {b}" for a, b in windows)
    return text


def rule_matches(rule: dict, now: datetime, hol) -> bool:
    """A regra vale agora? Dia útil aqui é segunda a sexta, sem os feriados ligados no calendário."""
    kind, today = rule.get("tipo", ""), now.date()
    if kind in ("primeiros_dias_uteis", "ultimos_dias_uteis"):
        days = business_days(today.year, today.month, hol)
        n = rule.get("n", 0)
        if not days or n < 1:
            return False
        if kind == "primeiros_dias_uteis":  # do dia 1º até o n-ésimo dia útil (o fim de semana no meio conta)
            ok = today <= days[min(n, len(days)) - 1]
        else:  # do n-ésimo dia útil antes do fim até o último dia do mês
            ok = today >= days[max(len(days) - n, 0)]
    elif kind == "dias_do_mes":
        ok = rule.get("de", 0) <= today.day <= rule.get("ate", 0)
    elif kind == "dias_da_semana":
        ok = today.weekday() in rule.get("dias", [])
    else:
        return False
    windows = rule.get("janelas") or []
    if ok and windows:
        hhmm = now.strftime("%H:%M")
        ok = any(a <= hhmm < b for a, b in windows)
    return ok


def parse_rule(kind: str, n: str = "", start: str = "", end: str = "", days: list[str] = (),
               windows: str = "") -> dict:
    """A regra do formulário: valida e devolve o JSON que fica no banco."""
    if kind not in RULES:
        raise ValidationError("Escolha quando o modo liga sozinho.")
    if not kind:
        return {}
    rule: dict = {"tipo": kind}
    if kind in ("primeiros_dias_uteis", "ultimos_dias_uteis"):
        if not n.isdigit() or not 1 <= int(n) <= 15:
            raise ValidationError("Quantos dias úteis: de 1 a 15.")
        rule["n"] = int(n)
    elif kind == "dias_do_mes":
        if not (start.isdigit() and end.isdigit() and 1 <= int(start) <= int(end) <= 31):
            raise ValidationError("Dias do mês: do dia (1 a 31) até o dia (depois ou igual).")
        rule["de"], rule["ate"] = int(start), int(end)
    else:
        chosen = sorted({int(d) for d in days if str(d).isdigit() and 0 <= int(d) <= 6})
        if not chosen:
            raise ValidationError("Marque pelo menos um dia da semana.")
        rule["dias"] = chosen
    parsed = []
    for part in (p.strip() for p in (windows or "").split(",")):
        if not part:
            continue
        a, sep, b = (x.strip() for x in part.partition("-"))
        if not sep or not _HHMM.fullmatch(a) or not _HHMM.fullmatch(b) or b <= a:
            raise ValidationError("Horário: use HH:MM-HH:MM, separados por vírgula (ex.: 14:40-15:10, 16:40-17:10).")
        parsed.append([a, b])
    if parsed:
        rule["janelas"] = parsed
    return rule


# ---------- ler e gravar ----------

def _ensure(conn) -> None:
    """Cria os modos prontos no primeiro uso. O Padrão copia as configurações da TV que já existiam."""
    if conn.execute("SELECT 1 FROM tv_modes LIMIT 1").fetchone():
        return
    from .telas import SCREENS
    stored = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    stamp = datetime.now().isoformat(timespec="seconds")
    for priority, (key, name, screens, options, rule, rule_on) in enumerate(BUILTINS):
        if screens is None:  # Padrão: o que estava em Configurações (o que nunca mudou usa o padrão do código)
            page = int(stored.get("tv.pagina.segundos", PAGE_DEFAULT))
            screens = [(s.id, int(stored.get(f"tela.{s.id}.segundos", s.default_seconds)),
                        s.always or stored.get(f"tela.{s.id}.ligada", "1") == "1") for s in SCREENS]
        else:
            page = PAGE_DEFAULT
            screens = [(sid, seconds, True) for sid, seconds in screens]
        cur = conn.execute("INSERT OR IGNORE INTO tv_modes(name, builtin, page_seconds, sound, hide_titles, rule, "
                           "rule_on, priority, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (name, key, page, int(options.get("sound", True)), int(options.get("hide_titles", False)),
                            json.dumps(rule) if rule else "", int(rule_on), priority, stamp))
        if cur.rowcount:
            conn.executemany("INSERT OR IGNORE INTO tv_mode_screens(mode_id, screen, position, seconds, enabled) "
                             "VALUES (?, ?, ?, ?, ?)",
                             [(cur.lastrowid, sid, i, seconds, int(on)) for i, (sid, seconds, on) in enumerate(screens)])


def _load(conn) -> list[Mode]:
    from .telas import SCREENS
    _ensure(conn)
    labels = {s.id: s for s in SCREENS}
    rows: dict[int, list] = {}
    for r in conn.execute("SELECT * FROM tv_mode_screens ORDER BY position"):
        if r["screen"] in labels:  # tela que deixou de existir: fica de fora
            rows.setdefault(r["mode_id"], []).append(r)
    out = []
    for m in conn.execute("SELECT * FROM tv_modes ORDER BY priority, id"):
        screens = [ModeScreen(r["screen"], labels[r["screen"]].label, r["seconds"],
                              bool(r["enabled"]) or labels[r["screen"]].always and m["builtin"] == "padrao")
                   for r in rows.get(m["id"], [])]
        known = {s.id for s in screens}
        # tela nova (de uma fase futura): entra no fim, ligada só no Padrão
        screens += [ModeScreen(s.id, s.label, s.default_seconds, m["builtin"] == "padrao")
                    for s in SCREENS if s.id not in known]
        out.append(Mode(m["id"], m["name"], m["builtin"], m["page_seconds"], bool(m["sound"]), bool(m["hide_titles"]),
                        json.loads(m["rule"]) if m["rule"] else {}, bool(m["rule_on"]), m["priority"], tuple(screens)))
    return out


def list_modes(db: Database) -> list[Mode]:
    with db.connect() as conn:
        return _load(conn)


def get_mode(db: Database, mode_id: int) -> Mode | None:
    return next((m for m in list_modes(db) if m.id == mode_id), None)


def default_mode(db: Database) -> Mode:
    return next(m for m in list_modes(db) if m.is_default)


@dataclass(frozen=True)
class Current:
    mode: Mode
    how: str                      # 'manual', 'automatico' ou 'padrao'
    until: datetime | None = None  # escolha à mão: até quando (None = até trocar de novo)
    by: int | None = None


def _choice(db: Database, now: datetime) -> dict | None:
    raw = get_setting(db, CHOICE_SETTING)
    if not raw:
        return None
    try:
        choice = json.loads(raw)
        if choice.get("ate") and datetime.fromisoformat(choice["ate"]) <= now:
            return None
        return choice
    except (ValueError, TypeError, AttributeError):
        return None  # valor estragado: como se ninguém tivesse escolhido


def current(db: Database, now: datetime) -> Current:
    """O modo que vale agora: o escolhido à mão (até o prazo), o primeiro com regra que vale, ou o Padrão."""
    with db.connect() as conn:
        modes = _load(conn)
        hol = load_holidays(conn)
    choice = _choice(db, now)
    if choice:
        chosen = next((m for m in modes if m.id == choice.get("id")), None)
        if chosen:
            return Current(chosen, "manual", datetime.fromisoformat(choice["ate"]) if choice.get("ate") else None,
                           choice.get("por"))
    for m in modes:
        if m.rule_on and m.rule and rule_matches(m.rule, now, hol):
            return Current(m, "automatico")
    return Current(next(m for m in modes if m.is_default), "padrao")


def choose(db: Database, now: datetime, actor: Person, mode_id: int, duration: str = "dia") -> Mode:
    """Troca o modo da TV da sala (qualquer pessoa com PIN), até o fim do dia, por 1 hora ou até trocar."""
    mode = get_mode(db, mode_id)
    if mode is None:
        raise ValidationError("Escolha um modo.")
    if duration not in DURATIONS:
        raise ValidationError("Escolha até quando vale o modo.")
    until = (datetime.combine(now.date(), time(23, 59, 59)) if duration == "dia"
             else now + timedelta(hours=1) if duration == "60" else None)
    value = {"id": mode.id, "ate": until.isoformat(timespec="seconds") if until else None, "por": actor.id}
    with db.connect() as conn:
        put_setting(conn, CHOICE_SETTING, json.dumps(value))
        log_event(conn, now, actor.id, "tv_modo", "tv", mode.name)
    return mode


def back_to_automatic(db: Database, now: datetime, actor: Person) -> None:
    with db.connect() as conn:
        put_setting(conn, CHOICE_SETTING, None)
        log_event(conn, now, actor.id, "tv_modo_automatico", "tv", "")


def _clean_screens(screens: list[tuple[str, str, bool]]) -> list[tuple[str, int, bool]]:
    from .telas import SCREENS
    labels = {s.id: s.label for s in SCREENS}
    out, seen = [], set()
    for sid, raw, on in screens:
        if sid not in labels or sid in seen:
            continue
        seen.add(sid)
        raw = str(raw).strip()
        if not raw.isdigit() or not MIN_SECONDS <= int(raw) <= MAX_SECONDS:
            raise ValidationError(f"Tempo de \"{labels[sid]}\": use de {MIN_SECONDS} a {MAX_SECONDS} segundos.")
        out.append((sid, int(raw), bool(on)))
    out += [(s.id, s.default_seconds, False) for s in SCREENS if s.id not in seen]
    if not any(on for _, _, on in out):
        raise ValidationError("Ligue pelo menos uma tela.")
    return out


def save_mode(db: Database, now: datetime, actor: Person, mode_id: int | None, *, name: str,
              screens: list[tuple[str, str, bool]], page_seconds: str, sound: bool, hide_titles: bool,
              rule: dict, rule_on: bool) -> Mode:
    """Cria (mode_id None) ou muda um modo. `screens` vem na ordem da rotação: (tela, segundos, ligada)."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam os modos da TV.")
    name = " ".join((name or "").split())
    if not name:
        raise ValidationError("Dê um nome ao modo.")
    if len(name) > MAX_NAME:
        raise ValidationError(f"Nome muito longo (máximo {MAX_NAME}).")
    page_seconds = str(page_seconds).strip()
    if not page_seconds.isdigit() or not PAGE_MIN <= int(page_seconds) <= PAGE_MAX:
        raise ValidationError(f"Tempo de cada página: use de {PAGE_MIN} a {PAGE_MAX} segundos.")
    cleaned = _clean_screens(screens)
    with db.connect() as conn:
        modes = {m.id: m for m in _load(conn)}
        if mode_id is not None and mode_id not in modes:
            raise ValidationError("Modo não encontrado.")
        if any(m.name.casefold() == name.casefold() and m.id != mode_id for m in modes.values()):
            raise ValidationError("Já existe um modo com esse nome.")
        if mode_id is not None and modes[mode_id].is_default:
            if not dict((s, on) for s, _, on in cleaned).get("quadro"):
                raise ValidationError("No Padrão, o Quadro fica sempre ligado.")
            rule, rule_on = {}, False  # o Padrão vale quando nenhum outro vale: não tem regra
        values = (name, int(page_seconds), int(sound), int(hide_titles), json.dumps(rule) if rule else "",
                  int(rule_on and bool(rule)), now.isoformat(timespec="seconds"))
        if mode_id is None:
            priority = max((m.priority for m in modes.values()), default=-1) + 1
            cur = conn.execute("INSERT INTO tv_modes(name, page_seconds, sound, hide_titles, rule, rule_on, updated_at, "
                               "priority, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (*values, priority, actor.id))
            mode_id, kind = cur.lastrowid, "modo_criado"
        else:
            conn.execute("UPDATE tv_modes SET name = ?, page_seconds = ?, sound = ?, hide_titles = ?, rule = ?, "
                         "rule_on = ?, updated_at = ? WHERE id = ?", (*values, mode_id))
            kind = "modo_editado"
        conn.execute("DELETE FROM tv_mode_screens WHERE mode_id = ?", (mode_id,))
        conn.executemany("INSERT INTO tv_mode_screens(mode_id, screen, position, seconds, enabled) VALUES (?, ?, ?, ?, ?)",
                         [(mode_id, sid, i, seconds, int(on)) for i, (sid, seconds, on) in enumerate(cleaned)])
        log_event(conn, now, actor.id, kind, f"modo:{mode_id}", name)
        return next(m for m in _load(conn) if m.id == mode_id)


def duplicate_mode(db: Database, now: datetime, actor: Person, mode_id: int) -> Mode:
    source = get_mode(db, mode_id)
    if source is None:
        raise ValidationError("Modo não encontrado.")
    names = {m.name.casefold() for m in list_modes(db)}
    name, n = f"{source.name} (cópia)"[:MAX_NAME], 2
    while name.casefold() in names:
        name, n = f"{source.name} (cópia {n})"[:MAX_NAME], n + 1
    return save_mode(db, now, actor, None, name=name, screens=[(s.id, str(s.seconds), s.enabled) for s in source.screens],
                     page_seconds=str(source.page_seconds), sound=source.sound, hide_titles=source.hide_titles,
                     rule=source.rule, rule_on=False)  # a cópia não liga sozinha até alguém ligar


def delete_mode(db: Database, now: datetime, actor: Person, mode_id: int) -> None:
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam os modos da TV.")
    mode = get_mode(db, mode_id)
    if mode is None:
        raise ValidationError("Modo não encontrado.")
    if mode.builtin:
        raise ValidationError("Os modos que vêm prontos não se apagam: desligue a regra para ele não ligar sozinho.")
    with db.connect() as conn:
        conn.execute("DELETE FROM tv_mode_screens WHERE mode_id = ?", (mode_id,))
        conn.execute("DELETE FROM tv_modes WHERE id = ?", (mode_id,))
        choice = conn.execute("SELECT value FROM settings WHERE key = ?", (CHOICE_SETTING,)).fetchone()
        if choice and json.loads(choice["value"]).get("id") == mode_id:
            put_setting(conn, CHOICE_SETTING, None)  # estava na TV: volta ao automático
        log_event(conn, now, actor.id, "modo_excluido", f"modo:{mode_id}", mode.name)


def move_mode(db: Database, now: datetime, actor: Person, mode_id: int, direction: int) -> None:
    """Sobe (-1) ou desce (+1) na lista: com duas regras valendo, a de cima vence."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam os modos da TV.")
    modes = list_modes(db)
    i = next((n for n, m in enumerate(modes) if m.id == mode_id), None)
    if i is None:
        raise ValidationError("Modo não encontrado.")
    j = i + direction
    if not 0 <= j < len(modes):
        return
    modes[i], modes[j] = modes[j], modes[i]
    with db.connect() as conn:
        conn.executemany("UPDATE tv_modes SET priority = ? WHERE id = ?", [(n, m.id) for n, m in enumerate(modes)])


def set_rule_on(db: Database, now: datetime, actor: Person, mode_id: int, on: bool) -> None:
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam os modos da TV.")
    mode = get_mode(db, mode_id)
    if mode is None:
        raise ValidationError("Modo não encontrado.")
    if on and not mode.rule:
        raise ValidationError("Esse modo não tem regra: edite o modo e escolha quando ele liga sozinho.")
    with db.connect() as conn:
        conn.execute("UPDATE tv_modes SET rule_on = ? WHERE id = ?", (int(on), mode_id))
        log_event(conn, now, actor.id, "modo_regra_ligada" if on else "modo_regra_desligada", f"modo:{mode_id}",
                  mode.name)


# ---------- o que vai para a TV ----------

HIDDEN_CARD = "Demanda"


def mask_titles(payload: dict) -> None:
    """Modo com os títulos escondidos (ex.: Visita): o servidor nem manda os textos. Cada cartão
    fica só com a cor e as iniciais; as telas com texto livre perdem o texto."""
    def card(c: dict) -> dict:
        return {**c, "title": HIDDEN_CARD, "folder": None, "requested_by": None, "routine": None, "reserved": False}
    payload["columns"] = {col: [card(c) for c in cards] for col, cards in payload["columns"].items()}
    for s in payload["screens"]:
        data = s["data"]
        if s["id"] == "prazos":
            for g in data["groups"]:
                g["cards"] = [card(c) for c in g["cards"]]
        elif s["id"] == "agenda":
            for g in data["groups"]:
                for i in g["itens"]:
                    if i["tipo"] == "compromisso":
                        i["titulo"] = "Compromisso"
        elif s["id"] == "prioridades":
            for i in data["items"]:
                i["title"] = "Prioridade"
        elif s["id"] == "envios":
            for r in data["rodadas"]:
                r["envio"] = "Envio"
    for a in payload.get("avisos", []):
        a["name"] = "Rotina"
