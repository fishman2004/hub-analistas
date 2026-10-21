"""Fase 15: exportar telas da TV em PDF (pela janela de impressão), com a mesma regra da TV."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub.demands import create_demand
from hub.people import add_person
from hub.telas import SCREENS
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    app = create_app(db, clock=lambda: at(14, 32))
    c = login(TestClient(app, base_url=BASE), kayo)
    return db, app, c, kayo


def test_needs_pin(env):
    _, app, *_ = env
    r = TestClient(app, base_url=BASE).get("/tv/exportar?tela=quadro", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/entrar"


def test_page_draws_the_tv_from_the_same_data_and_logs(env):
    db, _, c, kayo = env
    create_demand(db, at(8), kayo.id, title="Comissões secretas", owner_id=kayo.id, reserved=True)
    html = c.get("/tv/exportar?tela=metas-mes").text
    assert 'class="exportar"' in html and 'data-exportar="metas-mes"' in html
    assert "<title>Hub - Metas do mês - 2026-10-19 14h32</title>" in html
    assert f"gerado em 19/10/2026 às 14:32 por {kayo.initials}" in html  # só as iniciais de quem exportou
    for s in SCREENS:  # o mesmo desenho da TV, tela por tela
        assert f'data-tela="{s.id}"' in html and f"/static/tv-telas/{s.id}.js" in html
    assert "Comissões" not in html  # os dados vêm do /api/tv, já com a regra da TV
    assert "clara=1" in html and "Versão clara" in html
    assert 'class="exportar clara"' in c.get("/tv/exportar?tela=todas&clara=1").text
    hist = c.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "exportou em PDF a tela “Metas do mês” da TV" in hist
    assert "exportou em PDF a tela “Todas as telas” da TV" in hist


def test_current_screen_and_unknown(env):
    _, app, c, _ = env
    r = c.get("/tv/exportar?tela=agora")
    assert r.status_code == 422 and "não está conectada" in r.text
    TestClient(app, base_url=BASE).get("/api/tv?tela=prazos&pausada=0")  # a TV da sala conta que está em Prazos
    assert 'data-exportar="prazos"' in c.get("/tv/exportar?tela=agora").text
    assert c.get("/tv/exportar?tela=horas").status_code == 404


def test_tv_room_page_offers_export(env):
    db, _, c, kayo = env
    create_demand(db, at(8), kayo.id, title="Prazo", owner_id=kayo.id, due=date(2026, 10, 20))
    html = c.get("/tv-da-sala").text
    assert "/tv/exportar?tela=agora" in html and "/tv/exportar?tela=todas" in html
    assert "/tv/exportar?tela=prazos" in html
