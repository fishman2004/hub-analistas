import pytest

from conftest import at
from hub.db import Database
from hub.demands import board
from hub.envios import tv_envios
from hub.people import add_person, list_people
from hub.prioridades import list_month, month_of
from tools.seed_demo import seed


def test_refuses_without_dedicated_folder(monkeypatch):
    monkeypatch.delenv("HUB_DADOS", raising=False)
    with pytest.raises(SystemExit):
        seed()


def test_refuses_over_real_team(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DADOS", str(tmp_path))
    real = Database(tmp_path / "hub.db")
    real.init()
    add_person(real, at(8), None, "Pessoa Real")
    with pytest.raises(SystemExit):
        seed()
    assert [p.name for p in list_people(real)] == ["Pessoa Real"]


def test_seeds_empty_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DADOS", str(tmp_path))
    seed(now=at(10))
    db = Database(tmp_path / "hub.db")
    assert len(list_people(db)) == 5
    columns = board(db, at(10))
    everything = columns["todo"] + columns["doing"] + columns["done"]
    assert any(d.reserved for d in everything) and columns["done"]
    people = {p.name: p for p in list_people(db)}
    assert all(p.has_pin for p in people.values())
    assert people["Ana Souza"].is_admin and people["Bianca Lima"].is_manager
    items = list_month(db, month_of(at(10)))
    assert len(items) == 4 and sum(p.done for p in items) == 1  # as comissões, feitas pelas 4 pastas
    metas = items[0]
    assert metas.steps and metas.missing == ("C", "D", "E", "F", "G") and metas.folder_done("A")
    envios = tv_envios(db, at(10))  # o histórico fictício do Pombo entra na TV
    assert envios and {"ok", "falha", "andamento"} == {r["grupo"] for r in envios["rodadas"]}
    assert all(r["hora"] <= "10:00" for r in envios["rodadas"])  # só o que já aconteceu
