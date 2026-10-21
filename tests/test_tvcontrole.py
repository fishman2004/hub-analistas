"""Fase 10: pausa da TV pelo app e na própria TV."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import tvcontrole
from hub.db import put_setting
from hub.people import add_person
from hub.web.app import create_app
from test_web_app import login


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    clock = {"now": at(12)}
    client = TestClient(create_app(db, clock=lambda: clock["now"]), base_url="http://hub-sala:8800")
    return client, db, kayo, bianca, clock


def test_pause_expires_by_itself(db):
    kayo = add_person(db, at(7), None, "Kayo")
    tvcontrole.pause(db, at(12), kayo, "prazos", "15")
    assert tvcontrole.current_pause(db, at(12, 14))["tela"] == "prazos"
    assert tvcontrole.current_pause(db, at(12, 15)) is None
    tvcontrole.pause(db, at(12), kayo, "quadro", "dia")
    assert tvcontrole.current_pause(db, at(23, 59)) is not None
    assert tvcontrole.current_pause(db, at(0, 0, day=20)) is None


def test_pause_validates_screen_and_duration(db):
    kayo = add_person(db, at(7), None, "Kayo")
    with pytest.raises(tvcontrole.ValidationError):
        tvcontrole.pause(db, at(12), kayo, "nao-existe", "15")
    with pytest.raises(tvcontrole.ValidationError):
        tvcontrole.pause(db, at(12), kayo, "quadro", "999")


def test_broken_setting_counts_as_no_pause(db):
    with db.connect() as conn:
        put_setting(conn, tvcontrole.PAUSE_SETTING, "{estragado")
    assert tvcontrole.current_pause(db, at(12)) is None


def test_api_tv_sends_pause_with_initials(env):
    c, db, kayo, _, clock = env
    assert c.get("/api/tv").json()["pausa"] is None
    login(c, kayo)
    r = c.post("/tv-da-sala/pausar", data={"tela": "quadro", "minutos": "5"}, follow_redirects=False)
    assert r.status_code == 303
    data = c.get("/api/tv").json()
    assert data["pausa"]["tela"] == "quadro" and data["pausa"]["iniciais"] == kayo.initials
    assert data["pausa_minutos"] == 15
    clock["now"] = at(12, 6)
    assert c.get("/api/tv").json()["pausa"] is None


def test_pause_needs_pin(env):
    c, db, *_ = env
    r = c.post("/tv-da-sala/pausar", data={"tela": "quadro", "minutos": "5"}, follow_redirects=False)
    assert r.headers["location"] == "/entrar"
    assert tvcontrole.current_pause(db, at(12)) is None
    assert c.get("/tv-da-sala", follow_redirects=False).status_code == 303


def test_pause_on_current_screen_uses_what_the_tv_reported(env):
    c, db, kayo, _, clock = env
    login(c, kayo)
    r = c.post("/tv-da-sala/pausar", data={"tela": "atual", "minutos": "15"})
    assert r.status_code == 422 and "não está conectada" in r.text
    c.get("/api/tv?tela=prazos&pausada=0")
    assert "Na TV agora:</strong> Prazos da semana" in c.get("/tv-da-sala").text
    c.post("/tv-da-sala/pausar", data={"tela": "atual", "minutos": "15"})
    assert tvcontrole.current_pause(db, clock["now"])["tela"] == "prazos"


def test_my_pc_tab_does_not_count_as_the_room_tv(env):
    c, db, kayo, _, clock = env
    login(c, kayo)
    c.get("/api/tv?tela=prazos&pausada=1&espiar=1")
    assert "não está conectada" in c.get("/tv-da-sala").text
    c.get("/api/tv?tela=quadro&pausada=0")
    clock["now"] = at(12) + timedelta(seconds=31)
    assert "não está conectada" in c.get("/tv-da-sala").text


def test_step_goes_around_the_rotation(env):
    c, db, kayo, _, clock = env
    login(c, kayo)
    c.get("/api/tv?tela=quadro")
    c.post("/tv-da-sala/trocar", data={"direcao": "proxima"})
    # sem outras telas com conteúdo, a rotação é só o Quadro
    assert tvcontrole.current_pause(db, clock["now"])["tela"] == "quadro"
    from hub.demands import create_demand
    from datetime import date
    create_demand(db, at(8), kayo.id, title="Com prazo", owner_id=kayo.id, due=date(2026, 10, 20))
    c.post("/tv-da-sala/trocar", data={"direcao": "proxima"})
    assert tvcontrole.current_pause(db, clock["now"])["tela"] == "prazos"
    c.post("/tv-da-sala/trocar", data={"direcao": "anterior"})
    assert tvcontrole.current_pause(db, clock["now"])["tela"] == "quadro"


def test_next_page_counts_up_and_pauses_on_the_board(env):
    c, db, kayo, _, clock = env
    login(c, kayo)
    c.post("/tv-da-sala/pagina")
    first = c.get("/api/tv").json()["pausa"]
    assert first["tela"] == "quadro" and first["pagina"] == 1
    c.post("/tv-da-sala/pagina")
    assert c.get("/api/tv").json()["pausa"]["pagina"] == 2


def test_resume_and_history(env):
    c, db, kayo, _, clock = env
    login(c, kayo)
    c.post("/tv-da-sala/pausar", data={"tela": "quadro", "minutos": "30"})
    c.post("/tv-da-sala/retomar")
    assert c.get("/api/tv").json()["pausa"] is None
    hist = c.get("/historico").text
    assert "Kayo pausou a TV da sala em “Quadro”" in hist
    assert "Kayo fez a TV da sala voltar a passar as telas" in hist


def test_tv_has_pause_badge_and_keys(env):
    c, *_ = env
    html = c.get("/tv").text
    assert 'id="pausa"' in html
    js = c.get("/static/tv.js").text
    assert "alternarPausa" in js and "espiar=1" in js and "ArrowLeft" in js
