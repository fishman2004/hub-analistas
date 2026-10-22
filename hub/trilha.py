"""Trilha do dia (fase 20): as "rotinas micro" do gestor, a trilha de horários de cada analista.

Cada pessoa tem blocos de horário por dia da semana (08:00 às 09:00 Acompanhamento da pasta, 09:01 às
09:30 Black-list...), com ícone, cor e o que fazer. No dia, cada bloco tem uma situação, calculada na
hora, nunca agendada:

- futuro: o horário ainda não chegou;
- agora: estamos dentro do horário do bloco;
- feito: marcado como feito até o fim do horário;
- feito_atrasado: marcado depois do fim;
- nao_feito: o horário acabou e ninguém marcou ("luz negativa" na TV);
- pausa: o intervalo, que nunca fica "não feito".

Quem marca: a própria pessoa, o gestor e os administradores, só no dia de hoje. Bloco ligado a uma
rotina com horário (fase 7) acende sozinho quando o cartão da rotina é concluído no quadro. A trilha
não roda em feriado nem para quem está ausente no Calendário.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .calendario import absent_today, load_holidays
from .db import Database, log_event
from .people import Person, ValidationError, list_people

WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
MAX_TITLE, MAX_DETAILS = 60, 400
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
# ícone: (nome no formulário, cor padrão). O desenho de cada um está em static/trilha-icones.svg
ICONS = {
    "email": ("E-mail", "#f08a24"), "lista": ("Lista", "#9bd37a"), "rota": ("Rota", "#f5d63d"),
    "conversa": ("Conversa", "#43a047"), "alvo": ("Alvo / campanha", "#fff0a8"), "pausa": ("Intervalo", "#7e3fb0"),
    "analise": ("Análise", "#9bd37a"), "carrinho": ("Pedidos", "#f08a24"), "loja": ("Loja", "#e5484d"),
    "documento": ("Documento", "#5bb8ea"), "planilha": ("Planilha", "#2e7d32"), "envio": ("Envio", "#3f7fd8"),
    "telefone": ("Telefone", "#43a047"), "reuniao": ("Reunião", "#3f7fd8"), "estrela": ("Destaque", "#f5d63d"),
    "relogio": ("Relógio", "#8a95a1"),
}
COLORS = {"#f08a24": "Laranja", "#f5d63d": "Amarelo", "#fff0a8": "Creme", "#9bd37a": "Verde-claro",
          "#43a047": "Verde", "#2e7d32": "Verde-escuro", "#5bb8ea": "Azul-claro", "#3f7fd8": "Azul",
          "#7e3fb0": "Roxo", "#e5484d": "Vermelho", "#ff6fae": "Rosa", "#8a95a1": "Cinza"}
KINDS = {"tarefa": "Tarefa", "pausa": "Pausa (intervalo)"}


@dataclass(frozen=True)
class Block:
    id: int
    person_id: int
    weekdays: tuple[int, ...]
    starts_at: str
    ends_at: str
    title: str
    details: str
    icon: str
    color: str
    kind: str
    routine_id: int | None
    active: bool

    @property
    def lines(self) -> list[str]:
        return [x.strip() for x in self.details.splitlines() if x.strip()]

    @property
    def is_break(self) -> bool:
        return self.kind == "pausa"

    def start(self, day: date) -> datetime:
        return datetime.combine(day, time.fromisoformat(self.starts_at))

    def end(self, day: date) -> datetime:
        return datetime.combine(day, time.fromisoformat(self.ends_at))


def _block(r) -> Block:
    return Block(r["id"], r["person_id"], tuple(int(x) for x in r["weekdays"].split(",") if x), r["starts_at"],
                 r["ends_at"], r["title"], r["details"], r["icon"], r["color"], r["kind"], r["routine_id"],
                 bool(r["active"]))


def list_blocks(db: Database, person_id: int) -> list[Block]:
    """Os blocos ativos da pessoa, pelo horário."""
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM trail_blocks WHERE person_id = ? AND active = 1 ORDER BY starts_at, id",
                            (person_id,)).fetchall()
    return [_block(r) for r in rows]


def get_block(db: Database, block_id: int) -> Block | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM trail_blocks WHERE id = ? AND active = 1", (block_id,)).fetchone()
    return _block(r) if r else None


def can_edit(actor: Person | None, person_id: int) -> bool:
    """Montar a trilha e marcar os blocos: a própria pessoa, o gestor e os administradores."""
    return actor is not None and (actor.id == person_id or actor.is_manager or actor.is_admin)


def can_see_summary(actor: Person | None) -> bool:
    """O resumo da semana de toda a equipe: o gestor e os administradores (cada um vê o seu)."""
    return actor is not None and (actor.is_manager or actor.is_admin)


# ---------- montar ----------

def _clean(weekdays, starts_at, ends_at, title, details, icon, color, kind) -> tuple:
    title = " ".join((title or "").split())
    details = "\n".join(x.strip() for x in (details or "").replace("\r\n", "\n").split("\n") if x.strip())
    starts_at, ends_at = (starts_at or "").strip(), (ends_at or "").strip()
    days = sorted({int(d) for d in weekdays})
    if not title:
        raise ValidationError("Informe o nome do bloco.")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Nome muito longo (máximo {MAX_TITLE}).")
    if len(details) > MAX_DETAILS:
        raise ValidationError(f"O que fazer: no máximo {MAX_DETAILS} letras.")
    if not days or any(d not in range(7) for d in days):
        raise ValidationError("Marque pelo menos um dia da semana.")
    if not _HHMM.fullmatch(starts_at) or not _HHMM.fullmatch(ends_at):
        raise ValidationError("Horário inválido (use HH:MM, por exemplo 09:01).")
    if ends_at <= starts_at:
        raise ValidationError("O fim precisa ser depois do início.")
    if icon not in ICONS:
        raise ValidationError("Escolha o ícone.")
    if color not in COLORS:
        raise ValidationError("Escolha a cor.")
    if kind not in KINDS:
        raise ValidationError("Escolha o tipo do bloco.")
    return days, starts_at, ends_at, title, details


def _clash(conn, person_id: int, block_id: int | None, days: list[int], starts_at: str, ends_at: str) -> str | None:
    """Outro bloco da mesma pessoa no mesmo dia da semana e num horário que se cruza (a linha do tempo quebraria)."""
    for r in conn.execute("SELECT * FROM trail_blocks WHERE person_id = ? AND active = 1 AND id IS NOT ?",
                          (person_id, block_id)):
        b = _block(r)
        common = set(b.weekdays) & set(days)
        if common and b.starts_at < ends_at and starts_at < b.ends_at:
            return f"Esse horário cruza com “{b.title}” ({b.starts_at} às {b.ends_at}) na {WEEKDAYS[min(common)]}."
    return None


def save_block(db: Database, now: datetime, actor: Person, block_id: int | None, *, person_id: int,
               weekdays: list[int], starts_at: str, ends_at: str, title: str, details: str = "", icon: str = "lista",
               color: str = "", kind: str = "tarefa", routine_id: int | None = None) -> Block:
    if not can_edit(actor, person_id):
        raise PermissionError("Monta a trilha a própria pessoa, o gestor e os administradores.")
    color = color or ICONS.get(icon, ("", ""))[1]
    days, starts_at, ends_at, title, details = _clean(weekdays, starts_at, ends_at, title, details, icon, color, kind)
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM people WHERE id = ?", (person_id,)).fetchone() is None:
            raise ValidationError("Pessoa não encontrada.")
        if block_id is not None:
            current = conn.execute("SELECT * FROM trail_blocks WHERE id = ? AND active = 1", (block_id,)).fetchone()
            if current is None or current["person_id"] != person_id:
                raise ValidationError("Bloco não encontrado.")
        if routine_id is not None and conn.execute("SELECT 1 FROM routines WHERE id = ?", (routine_id,)).fetchone() is None:
            raise ValidationError("Rotina não encontrada.")
        problem = _clash(conn, person_id, block_id, days, starts_at, ends_at)
        if problem:
            raise ValidationError(problem)
        stamp = now.isoformat(timespec="seconds")
        values = (",".join(map(str, days)), starts_at, ends_at, title, details, icon, color, kind, routine_id)
        if block_id is None:
            block_id = conn.execute("INSERT INTO trail_blocks(person_id, weekdays, starts_at, ends_at, title, details, "
                                    "icon, color, kind, routine_id, created_at, updated_at) "
                                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    (person_id, *values, stamp, stamp)).lastrowid
        else:
            conn.execute("UPDATE trail_blocks SET weekdays = ?, starts_at = ?, ends_at = ?, title = ?, details = ?, "
                         "icon = ?, color = ?, kind = ?, routine_id = ?, updated_at = ? WHERE id = ?",
                         (*values, stamp, block_id))
        return _block(conn.execute("SELECT * FROM trail_blocks WHERE id = ?", (block_id,)).fetchone())


def remove_block(db: Database, now: datetime, actor: Person, block_id: int) -> None:
    """Tira o bloco da trilha (as marcas dos dias que passaram ficam guardadas)."""
    b = get_block(db, block_id)
    if b is None:
        raise ValidationError("Bloco não encontrado.")
    if not can_edit(actor, b.person_id):
        raise PermissionError("Monta a trilha a própria pessoa, o gestor e os administradores.")
    with db.connect() as conn:
        conn.execute("UPDATE trail_blocks SET active = 0, updated_at = ? WHERE id = ?",
                     (now.isoformat(timespec="seconds"), block_id))


def copy_trail(db: Database, now: datetime, actor: Person, source_id: int, target_id: int) -> int:
    """Copia a trilha de uma pessoa para outra que ainda não tem nenhum bloco. Devolve quantos copiou."""
    if not can_edit(actor, target_id):
        raise PermissionError("Monta a trilha a própria pessoa, o gestor e os administradores.")
    if source_id == target_id:
        raise ValidationError("Escolha outra pessoa para copiar.")
    if list_blocks(db, target_id):
        raise ValidationError("Essa trilha já tem blocos: tire os blocos antes de copiar outra.")
    blocks = list_blocks(db, source_id)
    if not blocks:
        raise ValidationError("Essa pessoa ainda não tem trilha para copiar.")
    for b in blocks:
        save_block(db, now, actor, None, person_id=target_id, weekdays=list(b.weekdays), starts_at=b.starts_at,
                   ends_at=b.ends_at, title=b.title, details=b.details, icon=b.icon, color=b.color, kind=b.kind)
    with db.connect() as conn:
        log_event(conn, now, actor.id, "trilha_copiada", f"pessoa:{target_id}", f"{len(blocks)} blocos")
    return len(blocks)


# a trilha do modelo do gestor (prints de segunda e terça). Dias: 0 = segunda
_ALL, _MON, _TUE = [0, 1, 2, 3, 4], [0, 2, 4], [1, 3]
_DEVOLUTIVAS = "Devolutivas\nRetornos pendentes\nAtendimento extra\nReorganização de demandas"
_PHD = "PHD\nAcompanhamento de rota\nInsights de visitas e roteiro"
SUGGESTED = (
    # dias, início, fim, nome, o que fazer, ícone, cor (vazio = a do ícone), tipo
    (_ALL, "08:00", "09:00", "Acompanhamento da pasta",
     "Acompanhamento da pasta\nAPEX: acompanhamento dos planos de excelência\nInteração e agendamento de demandas extras",
     "email", "", "tarefa"),
    (_MON, "09:01", "09:30", "Black-list", "Batalha naval", "lista", "", "tarefa"),
    (_TUE, "09:01", "09:30", "MSL", "Melhor sortimento em loja", "estrela", "#5bb8ea", "tarefa"),
    (_ALL, "09:31", "10:00", "PHD", _PHD, "rota", "", "tarefa"),
    (_ALL, "10:01", "11:00", "Devolutivas", _DEVOLUTIVAS, "conversa", "", "tarefa"),
    (_MON, "11:01", "11:44", "Campanhas ativas", "Campanhas ativas", "alvo", "", "tarefa"),
    (_TUE, "11:01", "11:44", "Loja Perfeita", "Top contas\nPDV premiado", "loja", "", "tarefa"),
    (_ALL, "11:45", "13:00", "Intervalo", "", "pausa", "", "pausa"),
    (_ALL, "13:01", "14:00", "Insights", "Insights dos 10 maiores clientes\nAnálise G4 (financeiro, positivação, fornecedor)",
     "analise", "", "tarefa"),
    (_ALL, "14:01", "15:00", "Devolutivas", _DEVOLUTIVAS, "conversa", "", "tarefa"),
    (_ALL, "15:00", "15:30", "Transferência de pedidos", "Transferência de pedidos", "carrinho", "", "tarefa"),
    (_ALL, "15:31", "16:00", "PHD", _PHD, "rota", "", "tarefa"),
    (_ALL, "16:01", "17:00", "Devolutivas", _DEVOLUTIVAS, "conversa", "", "tarefa"),
    (_ALL, "17:01", "18:00", "Acompanhamento da pasta", "Acompanhamento da pasta\nAPEX\nReunião PEX", "email", "",
     "tarefa"),
)


def create_suggested(db: Database, now: datetime, actor: Person, person_id: int) -> int:
    """Cria a trilha do modelo para quem ainda não tem bloco nenhum."""
    if not can_edit(actor, person_id):
        raise PermissionError("Monta a trilha a própria pessoa, o gestor e os administradores.")
    if list_blocks(db, person_id):
        raise ValidationError("Essa trilha já tem blocos: o modelo só entra numa trilha vazia.")
    for days, start, end, title, details, icon, color, kind in SUGGESTED:
        save_block(db, now, actor, None, person_id=person_id, weekdays=days, starts_at=start, ends_at=end, title=title,
                   details=details, icon=icon, color=color, kind=kind)
    with db.connect() as conn:
        log_event(conn, now, actor.id, "trilha_modelo", f"pessoa:{person_id}", f"{len(SUGGESTED)} blocos")
    return len(SUGGESTED)


# ---------- o dia ----------

@dataclass(frozen=True)
class Step:
    """Um bloco num dia, com a situação calculada."""
    block: Block
    status: str  # futuro, agora, feito, feito_atrasado, nao_feito, pausa
    done_at: datetime | None = None
    done_by: int | None = None
    auto: bool = False  # acendeu pela rotina ligada

    @property
    def now(self) -> bool:
        return self.status == "agora"


def _status(b: Block, day: date, now: datetime, done_at: datetime | None) -> str:
    if b.is_break:
        return "pausa"
    if done_at is not None:
        return "feito" if done_at <= b.end(day) else "feito_atrasado"
    if now < b.start(day):
        return "futuro"
    if now < b.end(day):
        return "agora"
    return "nao_feito"


def trails_on(db: Database, day: date, now: datetime, person_ids: list[int] | None = None) -> dict[int, list[Step]]:
    """A trilha de cada pessoa no dia (só quem tem bloco nesse dia da semana). Em feriado, nada.
    Para um dia que já passou, use now no fim do dia: o que ninguém marcou fica "não feito"."""
    with db.connect() as conn:
        if day in load_holidays(conn):
            return {}
        rows = conn.execute("SELECT * FROM trail_blocks WHERE active = 1 ORDER BY starts_at, id").fetchall()
        marks = {r["block_id"]: r for r in conn.execute("SELECT * FROM trail_marks WHERE day = ?", (day.isoformat(),))}
        routine_done = {r["routine_id"]: r["done_at"] for r in conn.execute(
            "SELECT routine_id, done_at FROM demands WHERE routine_day = ? AND routine_id IS NOT NULL AND deleted = 0 "
            "AND column_ = 'done' AND done_at IS NOT NULL", (day.isoformat(),))}
    out: dict[int, list[Step]] = {}
    for r in rows:
        b = _block(r)
        if r["created_at"][:10] > day.isoformat():
            continue  # o bloco ainda não existia nesse dia (o resumo não cobra o que foi criado depois)
        if day.weekday() not in b.weekdays or (person_ids is not None and b.person_id not in person_ids):
            continue
        m = marks.get(b.id)
        done_at, done_by, auto = None, None, False
        if m:
            done_at, done_by = datetime.fromisoformat(m["done_at"]), m["done_by"]
        elif b.routine_id in routine_done:
            done_at, auto = datetime.fromisoformat(routine_done[b.routine_id]), True
        out.setdefault(b.person_id, []).append(Step(b, _status(b, day, now, done_at), done_at, done_by, auto))
    return out


def my_trail(db: Database, person_id: int, now: datetime) -> list[Step]:
    """A trilha de hoje da pessoa (vazia se ela está ausente no Calendário ou se é feriado)."""
    if person_id in absent_today(db, now.date()):
        return []
    return trails_on(db, now.date(), now, [person_id]).get(person_id, [])


def mark(db: Database, now: datetime, actor: Person, block_id: int, done: bool = True) -> None:
    """Marca (ou desmarca) o bloco como feito hoje."""
    b = get_block(db, block_id)
    if b is None:
        raise ValidationError("Bloco não encontrado.")
    if not can_edit(actor, b.person_id):
        raise PermissionError("Marca o bloco a própria pessoa, o gestor e os administradores.")
    if b.is_break:
        raise ValidationError("O intervalo não precisa ser marcado.")
    today = now.date()
    with db.connect() as conn:
        if today.weekday() not in b.weekdays or today in load_holidays(conn):
            raise ValidationError("Esse bloco não é de hoje.")
        if done:
            cur = conn.execute("INSERT OR IGNORE INTO trail_marks(block_id, day, done_by, done_at) VALUES (?, ?, ?, ?)",
                               (block_id, today.isoformat(), actor.id, now.isoformat(timespec="seconds")))
            if cur.rowcount:
                late = " (depois do horário)" if now > b.end(today) else ""
                log_event(conn, now, actor.id, "trilha_feito", f"pessoa:{b.person_id}",
                          f"{b.starts_at} {b.title}{late}")
        else:
            cur = conn.execute("DELETE FROM trail_marks WHERE block_id = ? AND day = ?", (block_id, today.isoformat()))
            if cur.rowcount:
                log_event(conn, now, actor.id, "trilha_desfeito", f"pessoa:{b.person_id}", f"{b.starts_at} {b.title}")


def counts(steps: list[Step]) -> dict:
    tasks = [s for s in steps if s.status != "pausa"]
    return {"feitos": sum(s.status in ("feito", "feito_atrasado") for s in tasks),
            "no_horario": sum(s.status == "feito" for s in tasks),
            "atrasados": sum(s.status == "feito_atrasado" for s in tasks),
            "perdidos": sum(s.status == "nao_feito" for s in tasks),
            "total": len(tasks)}


def week_summary(db: Database, now: datetime, days: int = 5) -> list[dict]:
    """Os últimos dias úteis (hoje inclusive, só os blocos que já terminaram): quanto cada um fez no horário."""
    with db.connect() as conn:
        hol = load_holidays(conn)
    today, picked, d = now.date(), [], now.date()
    while len(picked) < days and (today - d).days < 30:
        if d.weekday() < 5 and d not in hol:
            picked.append(d)
        d -= timedelta(days=1)
    totals: dict[int, dict] = {}
    for day in picked:
        cut = now if day == today else datetime.combine(day, time.max)
        away = absent_today(db, day)
        for pid, steps in trails_on(db, day, cut).items():
            if pid in away:
                continue  # dia de folga ou férias não conta como "sem marcar"
            ended = [s for s in steps if s.status in ("feito", "feito_atrasado", "nao_feito")]
            t = totals.setdefault(pid, {"no_horario": 0, "atrasados": 0, "perdidos": 0, "total": 0})
            c = counts(ended)
            for k in t:
                t[k] += c[k]
    people = {p.id: p for p in list_people(db)}
    out = [{"pessoa": people[pid], **t, "pct": round(100 * t["no_horario"] / t["total"]) if t["total"] else None}
           for pid, t in totals.items() if pid in people]
    return sorted(out, key=lambda x: x["pessoa"].name.lower())


# ---------- TV: tela Trilhas do dia ----------

def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def tv_trilhas(db: Database, now: datetime) -> dict | None:
    """Uma linha por analista com trilha hoje (quem está ausente fica de fora), com a posição de cada bloco
    no eixo do dia, a situação e o bloco de agora por extenso. Sem trilha hoje, a tela sai da rotação."""
    from .pastas import folders_by_person

    today = now.date()
    away = absent_today(db, today)
    trails = {pid: steps for pid, steps in trails_on(db, today, now).items() if pid not in away}
    people = {p.id: p for p in list_people(db)}
    trails = {pid: steps for pid, steps in trails.items() if pid in people}
    if not trails:
        return None
    first = min(_minutes(s.block.starts_at) for steps in trails.values() for s in steps)
    last = max(_minutes(s.block.ends_at) for steps in trails.values() for s in steps)
    start, end = first // 60 * 60, -(-last // 60) * 60
    span = max(end - start, 60)
    pct = lambda m: round(100 * (m - start) / span, 2)  # noqa: E731
    hhmm = now.strftime("%H:%M")
    folders = folders_by_person(db)
    rows = []
    for pid, steps in sorted(trails.items(), key=lambda kv: people[kv[0]].name.lower()):
        p = people[pid]
        current = next((s for s in steps if s.now), None)
        upcoming = next((s for s in steps if s.block.starts_at > hhmm), None)
        breaking = next((s for s in steps if s.status == "pausa" and s.block.starts_at <= hhmm < s.block.ends_at), None)
        focus, label = ((current, "agora") if current else (breaking, "pausa") if breaking
                        else (upcoming, "proximo") if upcoming else (None, "fim"))
        rows.append({
            "nome": p.name, "iniciais": p.initials, "cor": p.color, "pastas": " ".join(folders.get(pid, ())),
            **counts(steps),
            "blocos": [{"inicio": s.block.starts_at, "fim": s.block.ends_at, "titulo": s.block.title,
                        "icone": s.block.icon, "cor": s.block.color, "status": s.status,
                        "pos": pct(_minutes(s.block.starts_at)),
                        "larg": round(100 * (_minutes(s.block.ends_at) - _minutes(s.block.starts_at)) / span, 2)}
                       for s in steps],
            "foco": {"tipo": label, **({"inicio": focus.block.starts_at, "fim": focus.block.ends_at,
                                        "titulo": focus.block.title,
                                        "detalhes": [x for x in focus.block.lines if x != focus.block.title][:3],
                                        "icone": focus.block.icon, "cor": focus.block.color} if focus else {})},
        })
    hours = [f"{h:02d}:00" for h in range(start // 60, end // 60 + 1)]
    return {"inicio": f"{start // 60:02d}:00", "fim": f"{end // 60:02d}:00", "agora": hhmm,
            "agora_pct": max(0, min(100, pct(now.hour * 60 + now.minute))),
            "horas": [{"hora": h, "pos": pct(_minutes(h))} for h in hours], "linhas": rows}
