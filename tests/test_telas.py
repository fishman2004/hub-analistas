"""Fase 4: TV em rotação, telas registráveis e a página Configurações."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub.access import create_pin
from hub.demands import create_demand, move_demand
from hub.people import ValidationError, add_person, get_person
from hub.telas import SCREENS, rotation, save_screen_config, screen_config
from hub.web.app import create_app

BASE = "http://hub-sala:8800"


@pytest.fixture
def setup(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bia = add_person(db, at(7), None, "Bia")
    create_pin(db, at(7), kayo.id, "1234", "1234")  # administrador
    create_pin(db, at(7), bia.id, "1234", "1234")
    app = create_app(db, clock=lambda: at(12))
    return db, get_person(db, kayo.id), get_person(db, bia.id), app


def login(app, person):
    c = TestClient(app, base_url=BASE)
    c.post(f"/entrar/{person.id}", data={"pin": "1234"})
    return c


PANELS = {"metas-mes": "20", "metas-dia": "15", "produtos-foco": "15", "fornecedores": "15",  # telas da fase 5
          "prioridades": "15",  # fase 8
          "envios": "15",  # fase 9
          "agenda": "15",  # fase 13
          "rotinas-mes": "25",  # fase 19
          "trilhas": "25"}  # fase 20


def ids(db, now=at(12)):
    return [s["id"] for s in rotation(db, now)["screens"]]


def test_board_is_always_in_rotation_and_empty_screens_leave(setup):
    db, kayo, *_ = setup
    assert ids(db) == ["quadro"]  # sem prazos na semana: só o Quadro
    create_demand(db, at(8), kayo.id, title="Longe", owner_id=kayo.id, due=date(2026, 11, 30))
    assert ids(db) == ["quadro"]
    d = create_demand(db, at(8), kayo.id, title="Amanhã", owner_id=kayo.id, due=date(2026, 10, 20))
    assert ids(db) == ["quadro", "prazos"]
    move_demand(db, at(9), kayo.id, d.id, "done")  # concluída não conta
    assert ids(db) == ["quadro"]


def test_deadline_groups(setup):
    db, kayo, *_ = setup
    for title, due in [("Atrasada", date(2026, 10, 15)), ("Hoje", date(2026, 10, 19)),
                       ("Amanhã", date(2026, 10, 20)), ("Sexta", date(2026, 10, 23)), ("Fora", date(2026, 10, 26))]:
        create_demand(db, at(8), kayo.id, title=title, owner_id=kayo.id, due=due)
    prazos = next(s for s in rotation(db, at(12))["screens"] if s["id"] == "prazos")
    groups = {g["label"]: [c["title"] for c in g["cards"]] for g in prazos["data"]["groups"]}
    assert groups == {"Atrasadas": ["Atrasada"], "Hoje": ["Hoje"], "Amanhã": ["Amanhã"], "Próximos dias": ["Sexta"]}


def test_default_times_and_settings(setup):
    db, kayo, bia, _ = setup
    create_demand(db, at(8), kayo.id, title="Hoje", owner_id=kayo.id, due=date(2026, 10, 19))
    rot = rotation(db, at(12))
    assert [(s["id"], s["seconds"]) for s in rot["screens"]] == [("quadro", 30), ("prazos", 15)]
    assert rot["page_seconds"] == 10
    save_screen_config(db, at(9), kayo, {"quadro": "45", "prazos": "20", **PANELS}, set(), "8")
    rot = rotation(db, at(12))
    assert [(s["id"], s["seconds"]) for s in rot["screens"]] == [("quadro", 45)]  # prazos desligada
    assert rot["page_seconds"] == 8
    with pytest.raises(PermissionError):
        save_screen_config(db, at(9), bia, {"quadro": "45", "prazos": "20", **PANELS}, {"prazos"}, "8")
    for bad in ({"quadro": "2", "prazos": "20", **PANELS}, {"quadro": "abc", "prazos": "20", **PANELS},
                {"quadro": "30", **PANELS}):
        with pytest.raises(ValidationError):
            save_screen_config(db, at(9), kayo, bad, {"prazos"}, "8")
    with pytest.raises(ValidationError):
        save_screen_config(db, at(9), kayo, {"quadro": "30", "prazos": "15", **PANELS}, {"prazos"}, "1")


def test_every_registered_screen_has_a_drawing(setup):
    *_, app = setup
    tv = TestClient(app, base_url=BASE)
    html = tv.get("/tv").text
    for s in SCREENS:
        assert f'data-tela="{s.id}"' in html
        assert tv.get(f"/static/tv-telas/{s.id}.js").status_code == 200
        assert f"/static/tv-telas/{s.id}.js" in html


def test_api_tv_carries_rotation_and_overdue(setup):
    db, kayo, _, app = setup
    create_demand(db, at(8), kayo.id, title="Atrasada", owner_id=kayo.id, due=date(2026, 10, 15))
    create_demand(db, at(8), kayo.id, title="Comissões secretas", owner_id=kayo.id, due=date(2026, 10, 20),
                  reserved=True, requested_by="Diretoria")
    tv = TestClient(app, base_url=BASE)
    data = tv.get("/api/tv").json()
    assert data["overdue"] == 1 and data["page_seconds"] == 10
    assert [s["id"] for s in data["screens"]] == ["quadro", "prazos"]
    body = tv.get("/api/tv").text
    assert "Comissões secretas" not in body and "Diretoria" not in body  # nem na tela de prazos


def test_settings_page_is_admin_only(setup):
    db, kayo, bia, app = setup
    analyst = login(app, bia)
    assert 'href="/configuracoes"' not in analyst.get("/").text
    assert analyst.get("/configuracoes").status_code == 403
    assert analyst.post("/configuracoes", data={"segundos_quadro": "60"}).status_code == 403
    admin = login(app, kayo)
    assert 'href="/configuracoes"' in admin.get("/").text
    panels = {f"segundos_{k}": v for k, v in PANELS.items()}
    r = admin.post("/configuracoes", data={"segundos_quadro": "40", "segundos_prazos": "12",
                                           "ligada_prazos": "on", "pagina": "6", **panels})
    assert r.status_code == 200 and "Salvo" in r.text
    cfg = screen_config(db)
    assert [(s["id"], s["seconds"], s["enabled"]) for s in cfg["screens"] if s["id"] in ("quadro", "prazos")] == \
        [("quadro", 40, True), ("prazos", 12, True)]
    assert cfg["page_seconds"] == 6
    r = admin.post("/configuracoes", data={"segundos_quadro": "1", "segundos_prazos": "12", "pagina": "6", **panels})
    assert r.status_code == 422 and "de 5 a 300 segundos" in r.text
    assert "mudou as configurações da TV" in admin.get("/historico?de=2026-10-19&ate=2026-10-19").text
