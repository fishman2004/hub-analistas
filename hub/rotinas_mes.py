"""Rotinas do mês (fase 19): o calendário de rotinas do gestor (as "rotinas macro").

Cada rotina tem uma categoria com cor (Acompanhamentos, Metas, Comissionamento...), um texto e uma
regra de repetição. Os dias são calculados na hora, como o resto do Hub, nunca gravados um a um:

- semana: nos dias da semana marcados ("toda segunda e quinta");
- dia_util: o N-ésimo dia útil do mês ("3º dia útil");
- dia_util_fim: o N-ésimo dia útil contando do fim (1 = o último dia útil);
- dia: um dia fixo do mês; caindo em fim de semana ou feriado, vai para o próximo dia útil;
- data: uma data só.

Dia útil é segunda a sexta, sem os feriados ligados no Calendário (fase 13). Não é compromisso (não
tem horário) nem rotina com aviso (fase 7, que vira cartão no quadro): é o plano do que a equipe
acompanha em cada dia. Qualquer pessoa marca uma rotina como feita no dia de hoje; fica guardado quem.
Cadastrar e mudar: o gestor e os administradores.
"""

import calendar as cal
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .calendario import Holidays, business_days, load_holidays
from .db import Database, log_event
from .people import Person, ValidationError

RULES = {"semana": "Toda semana", "dia_util": "Dia útil do mês", "dia_util_fim": "Dia útil antes do fim do mês",
         "dia": "Dia do mês", "data": "Uma data só"}
WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
MAX_TITLE, MAX_CATEGORY = 120, 40
MAX_NOTE, NOTE_DAYS = 300, 31  # justificativa: até 300 letras, para hoje e os últimos 31 dias
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


# ---------- categorias ----------

@dataclass(frozen=True)
class Category:
    id: int
    name: str
    color: str
    position: int
    active: bool

    @property
    def text_color(self) -> str:
        """Texto escuro sobre cor clara e claro sobre cor escura (o amarelo e o azul-marinho do modelo)."""
        return text_on(self.color)


def text_on(color: str) -> str:
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lum = 0.2126 * r ** 2.2 + 0.7152 * g ** 2.2 + 0.0722 * b ** 2.2
    return "#10161d" if lum > 0.2 else "#ffffff"


def _category(r) -> Category:
    return Category(r["id"], r["name"], r["color"], r["position"], bool(r["active"]))


def list_categories(db: Database, active_only: bool = False) -> list[Category]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM month_categories ORDER BY position, id").fetchall()
    return [c for c in map(_category, rows) if c.active or not active_only]


def can_manage(person: Person | None) -> bool:
    """Cadastrar e mudar as rotinas do mês e as categorias: o gestor e os administradores."""
    return person is not None and (person.is_manager or person.is_admin)


def save_category(db: Database, now: datetime, actor: Person, category_id: int | None, name: str,
                  color: str) -> Category:
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as categorias.")
    name = " ".join((name or "").split())
    color = (color or "").strip()
    if not name:
        raise ValidationError("Informe o nome da categoria.")
    if len(name) > MAX_CATEGORY:
        raise ValidationError(f"Nome muito longo (máximo {MAX_CATEGORY}).")
    if not _COLOR.fullmatch(color):
        raise ValidationError("Escolha a cor da categoria.")
    with db.connect() as conn:
        clash = conn.execute("SELECT id FROM month_categories WHERE lower(name) = lower(?) AND id IS NOT ?",
                             (name, category_id)).fetchone()
        if clash:
            raise ValidationError(f"Já existe a categoria “{name}”.")
        if category_id is None:
            position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM month_categories").fetchone()[0]
            category_id = conn.execute("INSERT INTO month_categories(name, color, position) VALUES (?, ?, ?)",
                                       (name, color.lower(), position)).lastrowid
            kind = "categoria_criada"
        else:
            if conn.execute("SELECT 1 FROM month_categories WHERE id = ?", (category_id,)).fetchone() is None:
                raise ValidationError("Categoria não encontrada.")
            conn.execute("UPDATE month_categories SET name = ?, color = ?, active = 1 WHERE id = ?",
                         (name, color.lower(), category_id))
            kind = "categoria_editada"
        log_event(conn, now, actor.id, kind, f"categoria:{category_id}", name)
        return _category(conn.execute("SELECT * FROM month_categories WHERE id = ?", (category_id,)).fetchone())


def remove_category(db: Database, now: datetime, actor: Person, category_id: int) -> None:
    """Some da lista de escolha; só dá quando nenhuma rotina ativa usa a categoria."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as categorias.")
    with db.connect() as conn:
        r = conn.execute("SELECT name FROM month_categories WHERE id = ?", (category_id,)).fetchone()
        if r is None:
            raise ValidationError("Categoria não encontrada.")
        if conn.execute("SELECT 1 FROM month_routines WHERE category_id = ? AND active = 1", (category_id,)).fetchone():
            raise ValidationError(f"“{r['name']}” ainda tem rotinas ativas: mude a categoria delas antes.")
        conn.execute("UPDATE month_categories SET active = 0 WHERE id = ?", (category_id,))
        log_event(conn, now, actor.id, "categoria_removida", f"categoria:{category_id}", r["name"])


# ---------- regras ----------

def next_business_day(day: date, hol: Holidays) -> date:
    while day.weekday() >= 5 or day in hol:
        day += timedelta(days=1)
    return day


def _fixed_day(year: int, month: int, n: int, hol: Holidays) -> date:
    return next_business_day(date(year, month, min(n, cal.monthrange(year, month)[1])), hol)


def occurs_on(rule: dict, day: date, hol: Holidays, _cache: dict | None = None) -> bool:
    """A regra cai neste dia? (_cache guarda os dias úteis de cada mês quando se testa um mês inteiro.)"""
    kind = rule.get("tipo")
    if kind == "semana":
        return day.weekday() in rule.get("dias", ()) and day not in hol
    if kind == "data":
        return day.isoformat() == rule.get("data")
    if kind == "dia":
        prev = (day.replace(day=1) - timedelta(days=1))  # o dia 31 de um sábado pode cair no mês seguinte
        return day in (_fixed_day(day.year, day.month, rule["dia"], hol), _fixed_day(prev.year, prev.month, rule["dia"], hol))
    if kind in ("dia_util", "dia_util_fim"):
        key = (day.year, day.month)
        cache = _cache if _cache is not None else {}
        if key not in cache:
            cache[key] = business_days(day.year, day.month, hol)
        days, n = cache[key], rule.get("n", 0)
        if not 1 <= n <= len(days):
            return False
        return day == (days[n - 1] if kind == "dia_util" else days[-n])
    return False


def rule_label(rule: dict) -> str:
    kind = rule.get("tipo")
    if kind == "semana":
        days = rule.get("dias", [])
        if days == [0, 1, 2, 3, 4]:
            return "toda semana, seg a sex"
        names = [WEEKDAYS[d] for d in days]
        return "toda " + (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " e " + names[-1])
    if kind == "dia_util":
        return f"{rule['n']}º dia útil do mês"
    if kind == "dia_util_fim":
        return "último dia útil do mês" if rule["n"] == 1 else f"{rule['n']}º dia útil antes do fim do mês"
    if kind == "dia":
        return f"dia {rule['dia']} (ou o próximo dia útil)"
    if kind == "data":
        return "só em " + date.fromisoformat(rule["data"]).strftime("%d/%m/%Y")
    return ""


def parse_rule(kind: str, days: list[str] = (), n: str = "", day: str = "", on: str = "") -> dict:
    """A regra do formulário: valida e devolve o que fica no banco."""
    if kind not in RULES:
        raise ValidationError("Escolha quando a rotina acontece.")
    if kind == "semana":
        chosen = sorted({int(d) for d in days if str(d).isdigit() and 0 <= int(d) <= 5})
        if not chosen:
            raise ValidationError("Marque pelo menos um dia da semana.")
        return {"tipo": kind, "dias": chosen}
    if kind in ("dia_util", "dia_util_fim"):
        if not n.isdigit() or not 1 <= int(n) <= 23:
            raise ValidationError("Qual dia útil: de 1 a 23.")
        return {"tipo": kind, "n": int(n)}
    if kind == "dia":
        if not day.isdigit() or not 1 <= int(day) <= 31:
            raise ValidationError("Dia do mês: de 1 a 31.")
        return {"tipo": kind, "dia": int(day)}
    try:
        return {"tipo": kind, "data": date.fromisoformat(on).isoformat()}
    except ValueError:
        raise ValidationError("Informe a data.") from None


# ---------- rotinas ----------

@dataclass(frozen=True)
class MonthRoutine:
    id: int
    category_id: int
    title: str
    rule: dict
    highlight: bool
    owner_id: int | None
    active: bool

    @property
    def rule_text(self) -> str:
        return rule_label(self.rule)


def _routine(r) -> MonthRoutine:
    return MonthRoutine(r["id"], r["category_id"], r["title"], json.loads(r["rule"]), bool(r["highlight"]),
                        r["owner_id"], bool(r["active"]))


# a ordem dentro do dia: as que acontecem uma vez no mês primeiro (são as que não podem passar), depois as da
# semana; dentro de cada grupo, a ordem do cadastro (como o gestor escreveu)
_RULE_ORDER = {"data": 0, "dia_util": 1, "dia": 1, "dia_util_fim": 1, "semana": 2}


def list_routines(db: Database) -> list[MonthRoutine]:
    with db.connect() as conn:
        rows = conn.execute("SELECT r.* FROM month_routines r JOIN month_categories c ON c.id = r.category_id "
                            "ORDER BY r.active DESC, c.position, r.title").fetchall()
    return [_routine(r) for r in rows]


def get_routine(db: Database, routine_id: int) -> MonthRoutine | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM month_routines WHERE id = ?", (routine_id,)).fetchone()
    return _routine(r) if r else None


def save_routine(db: Database, now: datetime, actor: Person, routine_id: int | None, *, category_id: int,
                 title: str, rule: dict, highlight: bool = False, owner_id: int | None = None) -> MonthRoutine:
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as rotinas do mês.")
    title = " ".join((title or "").split())
    if not title:
        raise ValidationError("Informe o que é a rotina.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Texto muito longo (máximo {MAX_TITLE}).")
    with db.connect() as conn:
        cat = conn.execute("SELECT active FROM month_categories WHERE id = ?", (category_id,)).fetchone()
        current = conn.execute("SELECT * FROM month_routines WHERE id = ?", (routine_id,)).fetchone() if routine_id else None
        if routine_id is not None and current is None:
            raise ValidationError("Rotina não encontrada.")
        if cat is None or (not cat["active"] and (current is None or current["category_id"] != category_id)):
            raise ValidationError("Escolha a categoria.")
        if owner_id is not None:
            owner = conn.execute("SELECT active FROM people WHERE id = ?", (owner_id,)).fetchone()
            if owner is None or (not owner["active"] and (current is None or current["owner_id"] != owner_id)):
                raise ValidationError("Escolha o responsável (ou deixe sem).")
        stamp = now.isoformat(timespec="seconds")
        values = (category_id, title, json.dumps(rule), int(highlight), owner_id)
        if current is None:
            routine_id = conn.execute("INSERT INTO month_routines(category_id, title, rule, highlight, owner_id, "
                                      "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                      (*values, actor.id, stamp, stamp)).lastrowid
            kind = "rotina_mes_criada"
        else:
            conn.execute("UPDATE month_routines SET category_id = ?, title = ?, rule = ?, highlight = ?, owner_id = ?, "
                         "updated_at = ? WHERE id = ?", (*values, stamp, routine_id))
            kind = "rotina_mes_editada"
        log_event(conn, now, actor.id, kind, f"rotina_mes:{routine_id}", title)
        return _routine(conn.execute("SELECT * FROM month_routines WHERE id = ?", (routine_id,)).fetchone())


def set_active(db: Database, now: datetime, actor: Person, routine_id: int, active: bool) -> None:
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as rotinas do mês.")
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM month_routines WHERE id = ?", (routine_id,)).fetchone()
        if r is None:
            raise ValidationError("Rotina não encontrada.")
        if bool(r["active"]) == active:
            return
        conn.execute("UPDATE month_routines SET active = ? WHERE id = ?", (int(active), routine_id))
        log_event(conn, now, actor.id, "rotina_mes_reativada" if active else "rotina_mes_desativada",
                  f"rotina_mes:{routine_id}", r["title"])


# ---------- o que acontece em cada dia ----------

@dataclass(frozen=True)
class Occurrence:
    """Uma rotina do mês num dia, com a categoria e se já foi feita."""
    routine: MonthRoutine
    category: Category
    done_by: int | None = None
    done_at: datetime | None = None
    note: str = ""  # justificativa do dia (fase de justificativas)
    note_by: int | None = None
    note_at: datetime | None = None

    @property
    def done(self) -> bool:
        return self.done_at is not None


def by_day(db: Database, start: date, end: date, with_notes: bool = True) -> dict[date, list[Occurrence]]:
    """As rotinas do mês ativas de cada dia do período (dia sem rotina fica de fora), já em ordem.
    A TV pede with_notes=False: as justificativas nem são lidas lá."""
    with db.connect() as conn:
        hol = load_holidays(conn)
        cats = {r["id"]: _category(r) for r in conn.execute("SELECT * FROM month_categories")}
        routines = [_routine(r) for r in conn.execute("SELECT * FROM month_routines WHERE active = 1")]
        marks = {(r["routine_id"], r["day"]): r for r in conn.execute(
            "SELECT * FROM month_routine_marks WHERE day BETWEEN ? AND ?", (start.isoformat(), end.isoformat()))}
        notes = {(r["routine_id"], r["day"]): r for r in conn.execute(
            "SELECT * FROM month_routine_notes WHERE day BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()))} if with_notes else {}
    routines.sort(key=lambda r: (_RULE_ORDER.get(r.rule.get("tipo"), 3), r.id))
    out: dict[date, list[Occurrence]] = {}
    cache: dict = {}
    d = start
    while d <= end:
        for r in routines:
            if occurs_on(r.rule, d, hol, cache):
                m = marks.get((r.id, d.isoformat()))
                n = notes.get((r.id, d.isoformat()))
                out.setdefault(d, []).append(Occurrence(
                    r, cats[r.category_id], m["done_by"] if m else None,
                    datetime.fromisoformat(m["done_at"]) if m else None, n["text"] if n else "",
                    n["written_by"] if n else None, datetime.fromisoformat(n["written_at"]) if n else None))
        d += timedelta(days=1)
    return out


def mark_done(db: Database, now: datetime, actor: Person, routine_id: int, done: bool = True) -> None:
    """Marca (ou desmarca) a rotina como feita hoje. Só vale no dia de hoje e num dia em que ela acontece."""
    today = now.date()
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM month_routines WHERE id = ? AND active = 1", (routine_id,)).fetchone()
        if r is None:
            raise ValidationError("Rotina não encontrada.")
        if not occurs_on(json.loads(r["rule"]), today, load_holidays(conn)):
            raise ValidationError("Essa rotina não é de hoje.")
        if done:
            cur = conn.execute("INSERT OR IGNORE INTO month_routine_marks(routine_id, day, done_by, done_at) "
                               "VALUES (?, ?, ?, ?)", (routine_id, today.isoformat(), actor.id,
                                                       now.isoformat(timespec="seconds")))
            if cur.rowcount:
                log_event(conn, now, actor.id, "rotina_mes_feita", f"rotina_mes:{routine_id}", r["title"])
        else:
            cur = conn.execute("DELETE FROM month_routine_marks WHERE routine_id = ? AND day = ?",
                               (routine_id, today.isoformat()))
            if cur.rowcount:
                log_event(conn, now, actor.id, "rotina_mes_desfeita", f"rotina_mes:{routine_id}", r["title"])


def justify(db: Database, now: datetime, actor: Person, routine_id: int, day: date, text: str) -> None:
    """Escreve (ou troca) a justificativa da rotina num dia: hoje ou um dos últimos 31 dias em que ela aconteceu.
    Marcar feita continua só hoje; a justificativa explica o que ficou sem fazer, atrasou ou saiu em parte.
    Texto vazio tira a justificativa."""
    text = "\n".join(x.strip() for x in (text or "").replace("\r\n", "\n").split("\n")).strip()
    if len(text) > MAX_NOTE:
        raise ValidationError(f"Justificativa muito longa (máximo {MAX_NOTE} letras).")
    today = now.date()
    if day > today:
        raise ValidationError("Só dá para justificar hoje ou um dia que já passou.")
    if (today - day).days > NOTE_DAYS:
        raise ValidationError(f"Só dá para justificar os últimos {NOTE_DAYS} dias.")
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM month_routines WHERE id = ? AND active = 1", (routine_id,)).fetchone()
        if r is None:
            raise ValidationError("Rotina não encontrada.")
        if not occurs_on(json.loads(r["rule"]), day, load_holidays(conn)):
            raise ValidationError("Essa rotina não acontece nesse dia.")
        if text:
            conn.execute("INSERT INTO month_routine_notes(routine_id, day, text, written_by, written_at) "
                         "VALUES (?, ?, ?, ?, ?) ON CONFLICT(routine_id, day) DO UPDATE SET text = excluded.text, "
                         "written_by = excluded.written_by, written_at = excluded.written_at",
                         (routine_id, day.isoformat(), text, actor.id, now.isoformat(timespec="seconds")))
            log_event(conn, now, actor.id, "rotina_mes_justificada", f"rotina_mes:{routine_id}",
                      f"{r['title']} ({day.strftime('%d/%m')})")
        elif conn.execute("DELETE FROM month_routine_notes WHERE routine_id = ? AND day = ?",
                          (routine_id, day.isoformat())).rowcount:
            log_event(conn, now, actor.id, "rotina_mes_justificativa_tirada", f"rotina_mes:{routine_id}",
                      f"{r['title']} ({day.strftime('%d/%m')})")


def month_weeks(year: int, month: int) -> list[list[date]]:
    """As semanas (de domingo a sábado, como o modelo do gestor) que cobrem o mês."""
    first = date(year, month, 1)
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    last = date(year, month, cal.monthrange(year, month)[1])
    end = last + timedelta(days=5 - last.weekday() if last.weekday() != 6 else 6)
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    return [days[i:i + 7] for i in range(0, len(days), 7)]


# ---------- as rotinas do modelo do gestor ----------

_WEEK = [0, 1, 2, 3, 4]
SUGGESTED = (
    # categoria, texto, regra, destaque
    ("Gestão de equipe", "Análises KPIs e Tendências", {"tipo": "semana", "dias": [1, 3]}, False),
    ("Acompanhamentos", "Desempenho Pasta Diário", {"tipo": "semana", "dias": _WEEK}, False),
    ("Acompanhamentos", "Blacklist", {"tipo": "semana", "dias": [0, 3]}, False),
    ("Acompanhamentos", "APEX", {"tipo": "semana", "dias": [0, 2, 4]}, False),
    ("Acompanhamentos", "Campanhas", {"tipo": "semana", "dias": [1, 3]}, False),
    ("Acompanhamentos", "Acompanhamento do representante dia", {"tipo": "semana", "dias": _WEEK}, False),
    ("Acompanhamentos", "MSL das marcas foco", {"tipo": "semana", "dias": [0, 2, 4]}, False),
    ("Fechamento", "Apuração de resultados referente ao mês anterior (M-1)", {"tipo": "dia_util", "n": 1}, False),
    ("Metas", "Gerar média para formulação de metas", {"tipo": "dia_util", "n": 1}, False),
    ("Abertura", "Início do novo ciclo de remuneração da gestão", {"tipo": "dia_util", "n": 1}, False),
    ("Comissionamento", "Encerramento do período de remuneração da gestão", {"tipo": "dia_util", "n": 1}, True),
    ("Metas", "Input de metas no sistema", {"tipo": "dia_util", "n": 3}, False),
    ("APEX", "Reunião de desempenhos · Planos de excelência · Quarter atual (M-1)", {"tipo": "dia_util", "n": 3}, False),
    ("Validações", "Integradoras de resultados", {"tipo": "dia_util", "n": 5}, False),
    ("APEX", "Reunião de desempenhos · Planos de excelência · Revisão de desempenho (M)", {"tipo": "dia_util", "n": 11},
     False),
    ("Comissionamento", "Encerramento do período comissionado da força de vendas", {"tipo": "dia_util_fim", "n": 4},
     False),
    ("Comissionamento", "Início de apurações e comissões", {"tipo": "dia_util_fim", "n": 3}, True),
    ("Comissionamento", "Início do novo ciclo de remuneração da força de vendas", {"tipo": "dia_util_fim", "n": 3}, False),
    ("Comissionamento", "Entrega do relatório de remuneração para conferência", {"tipo": "dia_util_fim", "n": 3}, False),
    ("Comissionamento", "Devolutiva de correções das comissões", {"tipo": "dia_util_fim", "n": 1}, True),
)


def create_suggested(db: Database, now: datetime, actor: Person) -> int:
    """Cria as rotinas do modelo que ainda não existem (mesma categoria e texto). Devolve quantas criou."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as rotinas do mês.")
    cats = {c.name.lower(): c for c in list_categories(db)}
    existing = {(r.category_id, r.title.lower()) for r in list_routines(db)}
    created = 0
    for cat_name, title, rule, highlight in SUGGESTED:
        cat = cats.get(cat_name.lower())
        if cat is None:  # alguém apagou a categoria do modelo: volta com a cor de antes
            cat = save_category(db, now, actor, None, cat_name, "#a9d8e6")
            cats[cat_name.lower()] = cat
        if (cat.id, title.lower()) in existing:
            continue
        save_routine(db, now, actor, None, category_id=cat.id, title=title, rule=rule, highlight=highlight)
        created += 1
    return created


# ---------- TV: tela Rotinas do mês ----------

def _tv_item(o: Occurrence, people: dict) -> dict:
    owner = people.get(o.routine.owner_id)
    return {"categoria": o.category.name, "cor": o.category.color, "texto_cor": o.category.text_color,
            "titulo": o.routine.title, "destaque": o.routine.highlight, "feita": o.done,
            "quem": {"initials": owner.initials, "color": owner.color} if owner else None,
            "feita_por": people[o.done_by].initials if o.done and o.done_by in people else ""}


def tv_rotinas_mes(db: Database, now: datetime) -> dict | None:
    """O mês inteiro (como o modelo do gestor) e o dia de hoje em destaque, com o próximo dia útil.
    Desde a fase 24, com as rotinas do mês e os compromissos da equipe da Agenda (as rotinas primeiro).
    Sem nenhuma rotina do mês e nenhum compromisso no mês, a tela sai da rotação."""
    from .calendario import tv_team_events
    from .people import list_people

    today = now.date()
    weeks = month_weeks(today.year, today.month)
    with db.connect() as conn:
        hol = load_holidays(conn)
    nxt = next_business_day(today + timedelta(days=1), hol)
    start, end = weeks[0][0], max(weeks[-1][-1], nxt)
    routines = by_day(db, start, end, with_notes=False)
    people = {p.id: p for p in list_people(db, active_only=False)}
    events = tv_team_events(db, start, end, people)
    if not any(routines.values()) and not any(events.values()):
        return None
    items = {d: [_tv_item(o, people) for o in routines.get(d, [])] + events.get(d, [])
             for d in set(routines) | set(events)}

    def day(d: date) -> dict:
        h = hol.get(d)
        return {"data": d.isoformat(), "dia": d.day, "fora": d.month != today.month, "hoje": d == today,
                "fds": d.weekday() >= 5, "feriado": h.name if h else "",
                "itens": items.get(d, [])}

    today_items = routines.get(today, [])
    return {
        "titulo": f"Calendário do mês · {cal_month(today)}",
        "semanas": [[day(d) for d in w] for w in weeks],
        "hoje": {**day(today), "rotulo": f"Hoje · {WEEKDAY_NAMES[today.weekday()]}, {today:%d/%m}",
                 "feitas": sum(o.done for o in today_items), "total": len(today_items)},
        "proximo": {**day(nxt), "rotulo": f"{'Amanhã' if nxt == today + timedelta(days=1) else WEEKDAY_NAMES[nxt.weekday()].capitalize()}, {nxt:%d/%m}"},
    }


MONTH_NAMES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
               "novembro", "dezembro"]
WEEKDAY_NAMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def cal_month(d: date) -> str:
    return f"{MONTH_NAMES[d.month - 1]} de {d.year}"
