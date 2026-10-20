"""Prepara uma pasta de demonstração com equipe e demandas FICTÍCIAS.

Serve para apresentar o Hub e tirar prints sem dados reais:

    PowerShell:  $env:HUB_DADOS = "$env:TEMP\\hub-demo"
    cmd:         set HUB_DADOS=%TEMP%\\hub-demo
    depois:      .venv\\Scripts\\python -m tools.seed_demo
"""

import os
import shutil
from pathlib import Path
from datetime import date, datetime, timedelta

from hub.access import create_pin, set_access
from hub.db import Database
from hub.demands import create_demand, move_demand
from hub.horas import save_entry, set_balance
from hub.paths import data_dir
from hub.paineis import panel_folder
from hub.people import add_person, get_person, list_people
from hub.presence import set_status

TEAM = ["Ana Souza", "Bianca Lima", "Carla Dias", "Diego Rocha", "Elisa Prado"]
DEMO_PIN = "1234"


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
    # planilhas fictícias dos painéis (tools/exemplos), para as telas de metas aparecerem na TV
    for f in (Path(__file__).parent / "exemplos").iterdir():
        shutil.copy(f, panel_folder(db) / f.name)
    return db


if __name__ == "__main__":
    print("pasta de demonstração:", seed().path.parent)
    print(f"PIN de todos: {DEMO_PIN} (Ana Souza é administradora; Bianca Lima é gestora e administradora)")
