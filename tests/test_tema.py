"""Tema claro/escuro: o app oferece a escolha, a TV não muda com ela."""

import re

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import __version__
from hub.people import add_person
from hub.web.app import create_app


@pytest.fixture
def client(db):
    kayo = add_person(db, at(7), None, "Kayo")
    c = TestClient(create_app(db, clock=lambda: at(12)), base_url="http://hub-sala:8800")
    return c, kayo


def test_entrar_has_theme_button_and_script(client):
    c, _ = client
    html = c.get("/entrar").text
    assert f'src="/static/tema.js?v={__version__}"' in html
    # o script vem no <head>, antes da página aparecer, para não piscar o tema errado
    assert html.index("tema.js") < html.index("<body>")
    assert re.search(r'<button[^>]*id="tema"', html)


def test_board_has_theme_button(client):
    c, kayo = client
    c.post(f"/entrar/{kayo.id}", data={"pin": "1234", "confirmar": "1234"})
    html = c.get("/").text
    assert 'id="tema"' in html and "tema.js" in html


def test_tv_ignores_personal_theme(client):
    c, _ = client
    html = c.get("/tv").text
    assert "tema.js" not in html and 'id="tema"' not in html and "app.css" not in html


def test_theme_files_are_served(client):
    c, _ = client
    js = c.get("/static/tema.js")
    assert js.status_code == 200 and "localStorage" in js.text
    css = c.get("/static/app.css").text
    # escolha manual e o automático (segue o Windows) usam as mesmas cores escuras
    assert ':root[data-tema="escuro"]' in css
    assert ":root:not([data-tema])" in css and "prefers-color-scheme: dark" in css
    assert ".tema[hidden]" in css
