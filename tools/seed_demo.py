"""Prepara uma pasta de demonstração com equipe e demandas FICTÍCIAS.

Serve para apresentar o Hub e tirar prints sem dados reais:

    PowerShell:  $env:HUB_DADOS = "$env:TEMP\\hub-demo"
    cmd:         set HUB_DADOS=%TEMP%\\hub-demo
    depois:      .venv\\Scripts\\python -m tools.seed_demo
"""

import csv
import os
import shutil
from pathlib import Path
from datetime import date, datetime, time, timedelta

from hub.access import create_pin, set_access
from hub.db import Database, put_setting
from hub.demands import create_demand, move_demand, routine_ref, toggle_folder
from hub.envios import COLUMNS, SETTING_FOLDER, analyst_slug
from hub.horas import save_entry, set_balance
from hub.paths import data_dir
from hub.paineis import panel_folder
from hub.people import add_person, get_person, list_people
from hub.presence import set_status
from hub.prioridades import add_priority, create_default_list, mark_done
from hub.rotinas import create_suggested, list_routines

TEAM = ["Ana Souza", "Bianca Lima", "Carla Dias", "Diego Rocha", "Elisa Prado"]
DEMO_PIN = "1234"
POMBO_FOLDER = "Histórico do Pombo"


def seed(now: datetime | None = None) -> Database:
    if not os.environ.get("HUB_DADOS"):
        raise SystemExit("Defina HUB_DADOS com uma pasta só para a demonstração (veja o README).")
    db = Database(data_dir() / "hub.db")
    db.init()
    if list_people(db, active_only=False):
        raise SystemExit(f"{db.path} já tem uma equipe cadastrada. Use outra pasta em HUB_DADOS.")

    now = now or datetime.now()
    early = now.replace(hour=8, minute=0, second=0, microsecond=0)
    ana, bianca, carla, diego, elisa = (add_person(db, early, None, n) for n in TEAM)
    today = now.date()
    for person in (ana, bianca, carla, diego, elisa):
        create_pin(db, early, person.id, DEMO_PIN, DEMO_PIN)  # Ana, a primeira, vira administradora
    set_access(db, early, get_person(db, ana.id), bianca.id, "gestor", True)

    def demand(owner, title, column="todo", minutes=0, **kw):
        d = create_demand(db, early + timedelta(minutes=minutes), owner.id, title=title, owner_id=owner.id, **kw)
        if column != "todo":
            move_demand(db, min(now, early + timedelta(minutes=minutes + 30)), owner.id, d.id, column)
        return d

    demand(ana, "Acompanhamento de vendas da pasta A", "doing", 5, folder="A")
    demand(ana, "Conferir integração do fechamento", "todo", 10, due=today)
    demand(ana, "Blacklist da pasta F", "done", 15, folder="F")
    demand(bianca, "Plano de excelência Brisa", "doing", 20, folder="C", requested_by="Gerente Comercial")
    demand(bianca, "Acompanhamento do Canal Farma", "todo", 25, folder="G", due=today + timedelta(days=2))
    demand(bianca, "Comissões dos vendedores", "todo", 30, reserved=True, due=today + timedelta(days=1))
    demand(carla, "Relatório de cobertura por cliente", "doing", 35, folder="B", requested_by="Rafael")
    demand(carla, "Comparativo de rotas", "todo", 40, due=today - timedelta(days=1))
    demand(carla, "Acompanhamento da pasta B", "done", 45, folder="B")
    demand(diego, "Acompanhamento Serrano", "doing", 50, folder="D")
    demand(diego, "Avaliação de desempenho de RCA", "todo", 55, reserved=True)
    demand(diego, "Fechamento da campanha de outubro", "done", 60, folder="D")
    demand(elisa, "Aprovar pedidos fora de rota", "todo", 65)
    demand(elisa, "Positivações do dia para a gestão", "done", 70)
    demand(elisa, "Cadastrar vendedores em clientes novos", "todo", 75, requested_by="Supervisão")

    for person, status in ((ana, "Na sala"), (bianca, "Em reunião"), (carla, "Na sala"), (diego, "Pausa")):
        set_status(db, early + timedelta(minutes=90), person.id, status)
    # banco de horas fictício: saldo base do "RH" até 10 dias atrás e os dias lançados depois
    gestora = get_person(db, bianca.id)
    start = today - timedelta(days=10)
    for k, person in enumerate((ana, bianca, carla, diego, elisa)):
        set_balance(db, early, gestora, person.id, (k - 2) * 95, start)
        for n in range(1, 10):
            day = start + timedelta(days=n)
            if day.weekday() < 5 and day < today and (n + k) % 6:  # alguns dias ficam sem lançamento
                save_entry(db, early, get_person(db, person.id), day, f"07:{40 + (n * 7 + k) % 20:02d}",
                           f"18:{(n * 11 + k * 3) % 40:02d}")
    # rotinas sugeridas, com a Ana como responsável. As que já passaram do horário hoje ficam como a
    # equipe faria: PHD concluída, a transferência das 14:50 com as três pastas e a das 16:50 pela metade
    create_suggested(db, early, get_person(db, ana.id))
    routines = {r.label: r for r in list_routines(db)}
    steps = (("08:40", "PHD · positivação diária 08:00", ana, None),
             ("14:52", "Transferência de pedidos 14:50", bianca, "B"),
             ("14:55", "Transferência de pedidos 14:50", carla, "C"),
             ("14:57", "Transferência de pedidos 14:50", ana, "F"),
             ("15:10", "Atualização de positivações no grupo de gestão comercial 15:00", ana, None),
             ("16:53", "Transferência de pedidos 16:50", bianca, "B"))
    for hhmm, label, person, folder in steps:
        when, routine = datetime.combine(today, time.fromisoformat(hhmm)), routines[label]
        if when > now or not routine.runs_on(today):
            continue
        if folder:
            toggle_folder(db, when, person.id, routine_ref(routine.id, today), folder)
        else:
            move_demand(db, when, person.id, routine_ref(routine.id, today), "done")
    # prioridades do mês: a lista padrão com duas já feitas, mais um item com pasta e prazo
    first, second, *_ = create_default_list(db, early, ana)
    mark_done(db, min(now, early + timedelta(minutes=40)), ana, first.id)
    mark_done(db, min(now, early + timedelta(minutes=80)), bianca, second.id)
    add_priority(db, early, carla, "Novos acompanhamentos da pasta B", folder="B", due_day=25)
    # planilhas fictícias dos painéis (tools/exemplos), para as telas de metas aparecerem na TV
    for f in (Path(__file__).parent / "exemplos").iterdir():
        shutil.copy(f, panel_folder(db) / f.name)
    # histórico fictício do Pombo, para a tela Envios do dia aparecer na TV
    pombo = write_pombo_history(db.path.parent / POMBO_FOLDER, now)
    with db.connect() as conn:
        put_setting(conn, SETTING_FOLDER, str(pombo))
    return db


def write_pombo_history(root: Path, now: datetime) -> Path:
    """Grava um histórico do Pombo FICTÍCIO (mesmo formato do pombo/history.py) com os envios de hoje
    até agora: enviados, uma falha depois de 4 tentativas, uma nova tentativa em andamento, uma espera
    pela atualização do arquivo, um "não atualizado", um "perdido" e um envio manual."""
    today = now.date()
    lines: dict[Path, list[list[str]]] = {}

    def run(who: str, did: str, name: str, scheduled: datetime, *events, manual: bool = False, files="Relatório.xlsx"):
        if scheduled > now:
            return  # ainda não chegou a hora: o Pombo não gravou nada
        label = f"manual {scheduled:%Y-%m-%d %H:%M:%S}" if manual else f"{scheduled:%Y-%m-%d %H:%M}"
        for minutes, channel, target, status, detail in events:
            when = scheduled + timedelta(minutes=minutes)
            if when > now:
                continue
            key = f"{'group' if channel == 'whatsapp' else 'list'}:{analyst_slug(target)}" if channel else ""
            path = root / analyst_slug(who) / f"{when:%Y-%m}.csv"
            lines.setdefault(path, []).append([f"{when:%Y-%m-%d %H:%M:%S}", who, name, label, channel, target,
                                               files, status, detail, did, key])

    def at(hour: int, minute: int = 0, day: date = today) -> datetime:
        return datetime(day.year, day.month, day.day, hour, minute)

    def ago(minutes: int) -> datetime:
        return (now - timedelta(minutes=minutes)).replace(second=0, microsecond=0)

    ok = "enviado", ""
    timeout = "falhou", "WhatsApp: tempo esgotado"
    ana, bianca, carla, diego, elisa = TEAM
    run(ana, "vendas", "Vendas Diárias", at(17, day=today - timedelta(days=1)),
        (0, "email", "Gestão", *ok))  # ontem: não aparece hoje
    run(bianca, "fechamento", "Fechamento de ontem", at(7), (150, "", "", "perdido", "programa fechado no horário"))
    run(ana, "vendas", "Vendas Diárias", at(7, 30), (1, "email", "Gestão", *ok), (1, "whatsapp", "Comercial — Vendas", *ok))
    run(carla, "positivacao", "Positivação do dia", at(8), (0, "email", "Supervisores", *ok))
    run(diego, "base", "Base 8081 (CSV)", at(8),
        (0, "", "", "esperando", "(DADOS) - 8081 - Vendas.csv: não atualizado hoje (esperando até 09:00)"),
        (60, "", "", "desistiu", "(DADOS) - 8081 - Vendas.csv: não atualizado hoje"), files="(DADOS) - 8081 - Vendas.csv")
    run(elisa, "rotas", "Pedidos fora de rota", at(9), (0, "email", "Gestão", *ok),
        *[(m, "whatsapp", "Supervisão Norte", *timeout) for m in (0, 5, 10, 15)])
    run(ana, "plano", "Plano de Excelência", at(10), (0, "email", "Gestor Comercial", *ok),
        (0, "whatsapp", "Supervisores", *timeout), (5, "whatsapp", "Supervisores", *ok))
    run(bianca, "cobertura", "Cobertura por cliente", at(11), (1, "email", "Gestão", *ok))
    run(ana, "vendas", "Vendas Diárias", at(12), (0, "email", "Gestão", *ok), (0, "whatsapp", "Comercial — Vendas", *ok))
    run(diego, "ranking", "Ranking de vendedores", at(13, 30), (0, "whatsapp", "Comercial — Vendas", *ok))
    run(elisa, "metas", "Metas da semana", at(14), (2, "email", "Gestão", *ok), (2, "email", "Supervisores", *ok),
        (2, "email", "Diretoria Comercial", *ok))
    run(carla, "positivacao", "Positivação do dia", at(15),
        (0, "whatsapp", "Supervisores", "esperando", "WhatsApp desconectado"), (12, "whatsapp", "Supervisores", *ok))
    run(bianca, "cobertura", "Cobertura por cliente", at(16, 20), (0, "email", "Gestão", *ok), manual=True)
    run(ana, "vendas", "Vendas Diárias", at(17), (0, "email", "Gestão", *ok), (0, "whatsapp", "Comercial — Vendas", *ok))
    # perto de agora: uma nova tentativa em andamento e uma espera pela atualização do arquivo
    run(carla, "pedidos", "Pedidos do dia", ago(4), (1, "email", "Gestão", *ok), (1, "whatsapp", "Supervisores", *timeout))
    waiting = ago(20)
    run(diego, "rotas", "Positivação por rota", waiting,
        (0, "", "", "esperando", f"Positivacao_rotas.xlsx: não atualizado hoje (esperando até {waiting + timedelta(hours=1):%H:%M})"))

    root.mkdir(parents=True, exist_ok=True)
    for path, rows in lines.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:  # como o Pombo: UTF-8 com BOM
            out = csv.writer(f)
            out.writerow(COLUMNS)
            out.writerows(sorted(rows))
    return root


if __name__ == "__main__":
    print("pasta de demonstração:", seed().path.parent)
    print(f"PIN de todos: {DEMO_PIN} (Ana Souza é administradora; Bianca Lima é gestora e administradora)")
