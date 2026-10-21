"""Fase 3: visão do gestor e quem vê o título de uma demanda reservada."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub.access import create_pin, set_access
from hub.demands import board, can_see, create_demand, move_demand
from hub.gestor import filter_demands, team_summary
from hub.people import add_person, get_person
from hub.presence import set_status
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
PIN = "1234"


@pytest.fixture
def team(db):
    """Ana administradora (primeiro PIN), Gil gestor, Bia e Caio analistas."""
    names = ["Ana", "Gil", "Bia", "Caio"]
    people = {n: add_person(db, at(7), None, n) for n in names}
    for p in people.values():
        create_pin(db, at(7), p.id, PIN, PIN)
    set_access(db, at(7), get_person(db, people["Ana"].id), people["Gil"].id, "gestor", False)
    people = {n: get_person(db, p.id) for n, p in people.items()}
    app = create_app(db, clock=lambda: at(12))
    return db, people, app


def client(app, person):
    c = TestClient(app, base_url=BASE)
    r = c.post(f"/entrar/{person.id}", data={"pin": PIN}, follow_redirects=False)
    assert r.status_code == 303
    return c


def test_who_sees_a_reserved_title(team):
    db, p, _ = team
    # Bia criou uma demanda reservada para o Caio
    d = create_demand(db, at(8), p["Bia"].id, title="Comissões", owner_id=p["Caio"].id, reserved=True)
    assert d.created_by == p["Bia"].id
    assert can_see(d, p["Bia"]) and can_see(d, p["Caio"])      # quem criou e o dono
    assert can_see(d, p["Gil"]) and can_see(d, p["Ana"])       # gestor e administradora
    caio_own = create_demand(db, at(8), p["Caio"].id, title="Avaliação", owner_id=p["Caio"].id, reserved=True)
    assert not can_see(caio_own, p["Bia"])
    normal = create_demand(db, at(8), p["Caio"].id, title="Rotas", owner_id=p["Caio"].id)
    assert can_see(normal, p["Bia"])


def test_analyst_board_masks_others_reserved(team):
    db, p, app = team
    d = create_demand(db, at(8), p["Caio"].id, title="Avaliação de RCA", owner_id=p["Caio"].id, reserved=True,
                      folder="D", requested_by="Diretoria", due=date(2026, 10, 21))
    bia = client(app, p["Bia"])
    for url in ("/?todas=1", "/parcial/quadro?todas=1"):
        html = bia.get(url).text
        assert "Demanda reservada" in html and "Avaliação de RCA" not in html
        assert "Diretoria" not in html and "Pasta D" not in html
        assert f"/demandas/{d.id}" not in html  # sem link e sem botões
        assert "prazo 21/10" in html
    caio = client(app, p["Caio"])
    assert "Avaliação de RCA" in caio.get("/").text


def test_analyst_cannot_open_or_touch_others_reserved(team):
    db, p, app = team
    d = create_demand(db, at(8), p["Caio"].id, title="Avaliação de RCA", owner_id=p["Caio"].id, reserved=True)
    bia = client(app, p["Bia"])
    r = bia.get(f"/demandas/{d.id}")
    assert r.status_code == 403 and "Avaliação de RCA" not in r.text
    assert bia.post(f"/demandas/{d.id}", data={"title": "x", "owner_id": str(p["Bia"].id)}).status_code == 403
    assert bia.post(f"/demandas/{d.id}/mover", data={"column": "doing"}).status_code == 403
    assert bia.post(f"/demandas/{d.id}/excluir").status_code == 403
    assert board(db, at(12))["todo"][0].title == "Avaliação de RCA"
    for who in ("Caio", "Gil", "Ana"):
        assert "Avaliação de RCA" in client(app, p[who]).get(f"/demandas/{d.id}").text, who


def test_history_masks_reserved_titles(team):
    db, p, app = team
    d = create_demand(db, at(8), p["Caio"].id, title="Avaliação de RCA", owner_id=p["Caio"].id, reserved=True)
    move_demand(db, at(9), p["Caio"].id, d.id, "doing")
    url = "/historico?de=2026-10-19&ate=2026-10-19"
    html = client(app, p["Bia"]).get(url).text
    assert "Avaliação de RCA" not in html and "Caio criou “Demanda reservada”" in html
    assert "Avaliação de RCA" in client(app, p["Gil"]).get(url).text


def test_only_manager_and_admins_open_gestor(team):
    db, p, app = team
    bia = client(app, p["Bia"])
    assert 'href="/gestor"' not in bia.get("/").text
    r = bia.get("/gestor")
    assert r.status_code == 403
    for who in ("Gil", "Ana"):
        c = client(app, p[who])
        assert 'href="/gestor"' in c.get("/").text
        assert c.get("/gestor").status_code == 200


def test_team_summary(team):
    db, p, app = team
    set_status(db, at(9), p["Bia"].id, "Em reunião")
    create_demand(db, at(8), p["Bia"].id, title="Atrasada", owner_id=p["Bia"].id, due=date(2026, 10, 15))
    d = create_demand(db, at(8), p["Bia"].id, title="Feita", owner_id=p["Bia"].id)
    move_demand(db, at(10), p["Bia"].id, d.id, "done")
    row = {r.person.name: r for r in team_summary(db, at(12))}["Bia"]
    assert (row.status, row.since.strftime("%H:%M")) == ("Em reunião", "09:00")
    assert (row.todo, row.doing, row.done_today, row.overdue) == (1, 0, 1, 1)
    html = client(app, p["Gil"]).get("/gestor").text
    assert "Em reunião" in html and "desde 09:00" in html and "Atrasada" in html


def test_gestor_filters(team):
    db, p, app = team
    create_demand(db, at(8), p["Bia"].id, title="Da Bia atrasada", owner_id=p["Bia"].id, due=date(2026, 10, 15))
    create_demand(db, at(8), p["Bia"].id, title="Da Bia sem prazo", owner_id=p["Bia"].id)
    d = create_demand(db, at(8), p["Caio"].id, title="Do Caio hoje", owner_id=p["Caio"].id, due=date(2026, 10, 19))
    move_demand(db, at(9), p["Caio"].id, d.id, "doing")
    titles = lambda **kw: [x.title for x in filter_demands(db, at(12), **kw)]
    assert titles(owner_id=p["Bia"].id) == ["Da Bia atrasada", "Da Bia sem prazo"]
    assert titles(column="doing") == ["Do Caio hoje"]
    assert titles(due="hoje") == ["Do Caio hoje"]
    assert titles(due="sem") == ["Da Bia sem prazo"]
    assert titles(overdue_only=True) == ["Da Bia atrasada"]
    gil = client(app, p["Gil"])
    html = gil.get(f"/gestor?pessoa={p['Caio'].id}&coluna=doing").text
    assert "Do Caio hoje" in html and "Da Bia sem prazo" not in html
    assert "Da Bia atrasada" in gil.get("/gestor?atrasadas=1").text
    assert "Nenhuma demanda" in gil.get("/gestor?prazo=hoje&pessoa=" + str(p["Bia"].id)).text


def test_gestor_sees_reserved_titles_in_the_list(team):
    db, p, app = team
    create_demand(db, at(8), p["Caio"].id, title="Avaliação de RCA", owner_id=p["Caio"].id, reserved=True)
    html = client(app, p["Gil"]).get("/gestor").text
    assert "Avaliação de RCA" in html and "Reservada" in html
