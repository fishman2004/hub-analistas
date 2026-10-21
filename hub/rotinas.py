"""Rotinas com horário (fase 7): o cadastro e quando cada rotina vale.

Uma rotina não é uma tarefa agendada. Nos dias marcados, quando chega o horário, o quadro
calcula o cartão dela em "A fazer" do responsável (ver demands.board). Ele só vira uma demanda
de verdade quando alguém mexe nele. Se o PC passar a noite desligado, nada fica para trás.

Só o gestor e os administradores cadastram e mudam rotinas; todo mundo vê a lista.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .calendario import load_holidays
from .db import Database, log_event, put_setting
from .people import Person, ValidationError

WEEKDAY_LABELS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")  # date.weekday(): segunda = 0
WORKDAYS = (0, 1, 2, 3, 4)
FOLDERS = ("A", "B", "C", "D", "E", "F", "G")  # as mesmas de demands.FOLDERS (que importa este arquivo)
MAX_NAME = 80
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
TEST_SETTING = "rotinas.aviso_teste"  # quando alguém clicou em "Testar aviso na TV agora"
TEST_WINDOW = timedelta(minutes=2)  # a TV que buscar o estado neste tempo toca o teste
TEST_NAME = "Teste do aviso"


@dataclass(frozen=True)
class Routine:
    id: int
    name: str
    weekdays: tuple[int, ...]
    starts_at: str  # "HH:MM"
    deadline: str | None  # "HH:MM"
    owner_id: int
    folders: tuple[str, ...]
    waits_for: tuple[int, ...]
    active: bool
    on_holidays: bool = False  # roda também em feriado (fase 13)
    holidays: object = field(default=(), repr=False, compare=False)  # calendario.Holidays (os feriados ativos)

    @property
    def label(self) -> str:
        """Nome e horário: há duas "Transferência de pedidos" no mesmo dia."""
        return f"{self.name} {self.starts_at}"

    def runs_on(self, day: date) -> bool:
        """Ativa, no dia da semana e, num feriado, só se roda também em feriado."""
        return self.active and day.weekday() in self.weekdays and (self.on_holidays or day not in self.holidays)

    def is_due(self, now: datetime) -> bool:
        """Vale hoje e o horário já chegou: o cartão aparece no quadro."""
        return self.runs_on(now.date()) and now.strftime("%H:%M") >= self.starts_at

    def start(self, day: date) -> datetime:
        return datetime.combine(day, time.fromisoformat(self.starts_at))

    def deadline_at(self, day: date) -> datetime | None:
        return datetime.combine(day, time.fromisoformat(self.deadline)) if self.deadline else None


def _row(r, hol) -> Routine:
    return Routine(
        r["id"], r["name"], tuple(int(x) for x in r["weekdays"].split(",") if x), r["starts_at"], r["deadline"],
        r["owner_id"], tuple(r["folders"]), tuple(int(x) for x in r["waits_for"].split(",") if x), bool(r["active"]),
        bool(r["on_holidays"]), hol,
    )


def load_routines(conn) -> dict[int, Routine]:
    """Todas as rotinas (inclusive as desativadas), por número. Para quem já tem uma conexão aberta.
    Cada uma já sabe os feriados do calendário: num feriado, só aparece a que roda também em feriado."""
    hol = load_holidays(conn)
    return {r["id"]: _row(r, hol) for r in conn.execute("SELECT * FROM routines")}


def list_routines(db: Database) -> list[Routine]:
    with db.connect() as conn:
        routines = load_routines(conn).values()
    return sorted(routines, key=lambda r: (not r.active, r.starts_at, r.name.lower()))


def get_routine(db: Database, routine_id: int) -> Routine | None:
    with db.connect() as conn:
        return load_routines(conn).get(routine_id)


def can_manage(person: Person | None) -> bool:
    """Cadastrar e mudar rotinas: o gestor e os administradores."""
    return person is not None and (person.is_admin or person.is_manager)


def weekdays_label(days: tuple[int, ...]) -> str:
    """(0, 1, 2, 3, 4) -> "seg a sex"; (1, 3) -> "ter e qui"."""
    days = tuple(sorted(set(days)))
    if len(days) == 7:
        return "todos os dias"
    if len(days) >= 3 and days == tuple(range(days[0], days[-1] + 1)):
        return f"{WEEKDAY_LABELS[days[0]]} a {WEEKDAY_LABELS[days[-1]]}"
    names = [WEEKDAY_LABELS[d] for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " e " + names[-1]


# ---------- cadastro ----------

def _check_cycle(routines: dict[int, Routine], routine_id: int, waits_for: tuple[int, ...]) -> None:
    # A espera B e B espera A: nenhuma das duas sairia do lugar
    graph = {r.id: r.waits_for for r in routines.values()}
    graph[routine_id] = waits_for
    pending, seen = list(waits_for), set()
    while pending:
        current = pending.pop()
        if current == routine_id:
            raise ValidationError("Uma rotina não pode esperar por ela mesma (nem por outra que espera por ela).")
        if current not in seen:
            seen.add(current)
            pending.extend(graph.get(current, ()))


def save_routine(db: Database, now: datetime, actor: Person, routine_id: int | None, *, name: str,
                 weekdays: list[int], starts_at: str, deadline: str | None, owner_id: int, folders: list[str],
                 waits_for: list[int], on_holidays: bool = False) -> Routine:
    """Cria (routine_id None) ou muda uma rotina. Vale a partir do próximo cálculo do quadro."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as rotinas.")
    name = " ".join((name or "").split())
    starts_at, deadline = (starts_at or "").strip(), (deadline or "").strip() or None
    if not name:
        raise ValidationError("Informe o nome da rotina.")
    if len(name) > MAX_NAME:
        raise ValidationError(f"Nome muito longo (máximo {MAX_NAME}).")
    days = sorted({int(d) for d in weekdays})
    if not days:
        raise ValidationError("Marque pelo menos um dia da semana.")
    if any(d not in range(7) for d in days):
        raise ValidationError("Dia da semana inválido.")
    if not _HHMM.fullmatch(starts_at):
        raise ValidationError("Horário inválido (use HH:MM, por exemplo 14:50).")
    if deadline is not None:
        if not _HHMM.fullmatch(deadline):
            raise ValidationError("Prazo inválido (use HH:MM, por exemplo 15:00).")
        if deadline <= starts_at:
            raise ValidationError("O prazo precisa ser depois do horário em que a rotina aparece.")
    if any(f not in FOLDERS for f in folders):
        raise ValidationError("Pasta inválida.")
    chosen_folders = "".join(f for f in FOLDERS if f in folders)
    waits = tuple(sorted({int(w) for w in waits_for}))
    with db.connect() as conn:
        routines = load_routines(conn)
        current = routines.get(routine_id) if routine_id is not None else None
        if routine_id is not None and current is None:
            raise ValidationError("Rotina não encontrada.")
        owner = conn.execute("SELECT active FROM people WHERE id = ?", (owner_id,)).fetchone()
        # manter o responsável atual vale mesmo se ele foi desativado; só não dá para escolher um desativado novo
        if owner is None or (not owner["active"] and (current is None or owner_id != current.owner_id)):
            raise ValidationError("Escolha o responsável pela rotina.")
        if any(w not in routines for w in waits):
            raise ValidationError("Rotina não encontrada em “Liberada depois de”.")
        if routine_id is not None:
            _check_cycle(routines, routine_id, waits)
        clash = next((r for r in routines.values() if r.id != routine_id and r.starts_at == starts_at
                      and r.name.lower() == name.lower()), None)
        if clash:
            raise ValidationError(f"Já existe a rotina “{name}” às {starts_at}.")
        values = (name, ",".join(map(str, days)), starts_at, deadline, owner_id, chosen_folders,
                  ",".join(map(str, waits)), int(on_holidays))
        if current is None:
            cur = conn.execute("INSERT INTO routines(name, weekdays, starts_at, deadline, owner_id, folders, waits_for, "
                               "on_holidays) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)
            routine_id, kind = cur.lastrowid, "rotina_criada"
        else:
            conn.execute("UPDATE routines SET name = ?, weekdays = ?, starts_at = ?, deadline = ?, owner_id = ?, "
                         "folders = ?, waits_for = ?, on_holidays = ? WHERE id = ?", (*values, routine_id))
            kind = "rotina_editada"
        log_event(conn, now, actor.id, kind, f"rotina:{routine_id}", f"{name} {starts_at}")
        return load_routines(conn)[routine_id]


def set_routine_active(db: Database, now: datetime, actor: Person, routine_id: int, active: bool) -> None:
    """Desativar tira a rotina do quadro e da TV a partir de agora. As demandas que ela já gerou ficam."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores mudam as rotinas.")
    with db.connect() as conn:
        routine = load_routines(conn).get(routine_id)
        if routine is None:
            raise ValidationError("Rotina não encontrada.")
        if routine.active == active:
            return
        conn.execute("UPDATE routines SET active = ? WHERE id = ?", (int(active), routine_id))
        log_event(conn, now, actor.id, "rotina_reativada" if active else "rotina_desativada", f"rotina:{routine_id}",
                  routine.label)


# As rotinas que o Kayo passou (outubro de 2026). O responsável é quem clica em "Criar rotinas
# sugeridas" e dá para mudar depois. Os itens do início do mês ficam para a fase 8.
SUGGESTED = (
    # nome, dias, aparece às, prazo, pastas, liberada depois de (nome, horário)
    ("PHD · positivação diária", WORKDAYS, "08:00", "09:00", "", None),
    ("Transferência de pedidos", WORKDAYS, "14:50", "15:00", "BCF", None),
    ("Atualização de positivações no grupo de gestão comercial", WORKDAYS, "15:00", None, "",
     ("Transferência de pedidos", "14:50")),
    ("Transferência de pedidos", WORKDAYS, "16:50", "17:00", "BCF", None),
    ("Atualização de positivações no grupo de gestão comercial", WORKDAYS, "17:00", None, "",
     ("Transferência de pedidos", "16:50")),
    ("Comparativo de rotas no grupo de gestão comercial", (1, 3), "10:00", None, "", None),  # horário a confirmar
)


def create_suggested(db: Database, now: datetime, actor: Person) -> int:
    """Cria as rotinas sugeridas que ainda não existem (mesmo nome e horário). Devolve quantas criou."""
    created = 0
    for name, days, starts_at, deadline, folders, after in SUGGESTED:
        existing = {(r.name.lower(), r.starts_at): r.id for r in list_routines(db)}
        if (name.lower(), starts_at) in existing:
            continue
        waits = [existing[(after[0].lower(), after[1])]] if after and (after[0].lower(), after[1]) in existing else []
        save_routine(db, now, actor, None, name=name, weekdays=list(days), starts_at=starts_at, deadline=deadline,
                     owner_id=actor.id, folders=list(folders), waits_for=waits)
        created += 1
    return created


# ---------- TV ----------

def tv_alerts(db: Database, now: datetime) -> list[dict]:
    """Os avisos sonoros de hoje: cada rotina que vale hoje, com o horário (inclusive as que ainda
    não chegaram, para a TV tocar na hora certa entre uma busca e outra). Se o cartão de hoje de
    uma rotina foi marcado como reservado, o aviso dela não vai para a TV. Logo depois de um
    "Testar aviso na TV agora", vai também o aviso de teste."""
    today = now.date()
    with db.connect() as conn:
        routines = load_routines(conn)
        reserved = {r[0] for r in conn.execute(
            "SELECT routine_id FROM demands WHERE routine_day = ? AND reserved = 1 AND deleted = 0", (today.isoformat(),))}
        test = conn.execute("SELECT value FROM settings WHERE key = ?", (TEST_SETTING,)).fetchone()
    alerts = [
        {"key": f"rotina-{r.id}-{today.isoformat()}", "at": r.start(today).isoformat(timespec="seconds"),
         "time": r.starts_at, "deadline": r.deadline, "name": r.name}
        for r in sorted(routines.values(), key=lambda r: (r.starts_at, r.name.lower()))
        if r.runs_on(today) and r.id not in reserved
    ]
    clicked = datetime.fromisoformat(test[0]) if test else None
    if clicked and clicked <= now <= clicked + TEST_WINDOW:
        # a chave termina com a data, como as outras: a TV guarda só as de hoje (ver tv.js)
        alerts.append({"key": f"teste-{clicked:%H%M%S}-{today.isoformat()}", "at": clicked.isoformat(timespec="seconds"),
                       "time": clicked.strftime("%H:%M"), "deadline": None, "name": TEST_NAME})
    return alerts


def alerts_today(db: Database, now: datetime) -> list[dict]:
    """Os avisos de hoje para a tela de Rotinas: os mesmos da TV, com o que já passou e o próximo."""
    alerts = [a for a in tv_alerts(db, now) if a["key"].startswith("rotina-")]
    stamp = now.isoformat(timespec="seconds")
    next_at = next((a["at"] for a in alerts if a["at"] > stamp), None)  # duas no mesmo horário: as duas são o próximo
    return [{**a, "passed": a["at"] <= stamp, "next": a["at"] == next_at} for a in alerts]


def start_test_alert(db: Database, now: datetime, actor: Person) -> None:
    """Faz a TV tocar o aviso agora, para conferir o som e a faixa sem esperar uma rotina."""
    if not can_manage(actor):
        raise PermissionError("Só o gestor e os administradores testam o aviso da TV.")
    with db.connect() as conn:
        put_setting(conn, TEST_SETTING, now.isoformat(timespec="seconds"))
        log_event(conn, now, actor.id, "aviso_teste", "rotinas", "")
