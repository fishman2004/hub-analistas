"""Fase 18: o Hub no celular (menu, atalho na tela inicial, QR Code e o endereço para o celular)."""

import hashlib
import re

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import celular
from hub.access import create_pin
from hub.people import add_person
from hub.qr import qr_matrix, qr_svg
from hub.web.app import create_app

BASE = "http://192.168.0.15:8800"


@pytest.fixture
def client(db):
    kayo = add_person(db, at(7), None, "Kayo")
    create_pin(db, at(7), kayo.id, "1234", "1234")
    c = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE)
    c.post("/entrar", data={"nome": "Kayo", "pin": "1234"})
    return c


# ---------- QR Code ----------

def _finder_ok(grid, x0, y0):
    """O quadrado do canto: borda escura, anel claro e miolo 3x3 escuro."""
    for dy in range(7):
        for dx in range(7):
            ring = max(abs(dx - 3), abs(dy - 3))
            if grid[y0 + dy][x0 + dx] != (ring != 2):
                return False
    return True


@pytest.mark.parametrize("text, version", [("A", 1), ("http://192.168.0.15:8800/entrar", 3), ("x" * 60, 4),
                                           ("y" * 150, 8), ("z" * 213, 10)])
def test_qr_has_the_right_size_and_corners(text, version):
    grid = qr_matrix(text)
    n = version * 4 + 17
    assert len(grid) == n and all(len(row) == n for row in grid)
    assert _finder_ok(grid, 0, 0) and _finder_ok(grid, n - 7, 0) and _finder_ok(grid, 0, n - 7)
    assert all(grid[6][x] == (x % 2 == 0) for x in range(8, n - 8))  # linha de tempo
    assert grid[n - 8][8]  # o módulo sempre escuro


def test_qr_format_bits_are_valid():
    """Os 15 bits de formato (copiados nos dois lugares) são um código válido de nível M."""
    grid = qr_matrix("http://192.168.0.15:8800/entrar")
    n = len(grid)
    first = [grid[i][8] for i in (0, 1, 2, 3, 4, 5, 7)] + [grid[8][8], grid[8][7]] + [grid[8][14 - i] for i in range(9, 15)]
    second = [grid[8][n - 1 - i] for i in range(8)] + [grid[n - 15 + i][8] for i in range(8, 15)]
    assert first == second
    bits = sum(int(b) << i for i, b in enumerate(first)) ^ 0x5412
    data = bits >> 10
    assert data >> 3 == 0  # nível M
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    assert bits == (data << 10 | rem)


@pytest.mark.parametrize("text, digest", [("http://192.168.0.15:8800/entrar", "82e73bfa009c442d"),
                                          ("z" * 213, "b2bb2b06366d4879")])
def test_qr_is_stable(text, digest):
    # estes desenhos foram lidos com um leitor de QR Code (versões 1 a 10, as 8 máscaras); se o código
    # do QR mudar e este teste falhar, confira com a câmera de um celular antes de trocar os números
    grid = qr_matrix(text)
    bits = "".join("1" if c else "0" for row in grid for c in row)
    assert hashlib.sha256(bits.encode()).hexdigest()[:16] == digest


def test_qr_svg_and_limits():
    svg = qr_svg("http://192.168.0.15:8800/entrar")
    assert svg.startswith("<svg") and 'viewBox="0 0 37 37"' in svg and 'fill="#fff"' in svg
    with pytest.raises(ValueError):
        qr_matrix("x" * 300)


# ---------- endereço para o celular ----------

def test_phone_address():
    assert celular.phone_address("192.168.0.15:8800", 8800, "10.0.0.9") == "http://192.168.0.15:8800"
    # abriu pelo nome do PC: o celular recebe o número (muitos celulares não acham nome de PC Windows)
    assert celular.phone_address("PC-SALA:8800", 8800, "10.0.0.9") == "http://10.0.0.9:8800"
    assert celular.phone_address("PC-SALA:8800", 8800, None) == "http://PC-SALA:8800"
    # no próprio PC da sala
    assert celular.phone_address("127.0.0.1:8800", 8800, "10.0.0.9") == "http://10.0.0.9:8800"
    assert celular.phone_address("localhost:8800", 8800, None) is None


def test_lan_ip_never_returns_loopback():
    ip = celular.lan_ip()
    assert ip is None or not ip.startswith("127.")


# ---------- páginas ----------

def test_celular_page_shows_qr_and_address(client):
    html = client.get("/celular").text
    assert "192.168.0.15:8800" in html and "<svg" in html and "Adicionar à tela inicial" in html
    assert 'aria-current="page">No celular' in html


def test_celular_page_needs_login(db):
    c = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE)
    r = c.get("/celular", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/entrar"


def test_manifest_and_icons(client):
    anon = TestClient(client.app, base_url=BASE)
    r = anon.get("/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    data = r.json()
    assert data["short_name"] == "Hub" and data["display"] == "standalone" and data["start_url"] == "/"
    for icon in data["icons"]:
        assert anon.get(icon["src"]).status_code == 200, icon["src"]
    assert anon.get("/static/icones/hub-180.png").status_code == 200


def test_every_page_is_ready_for_the_phone(client):
    for url in ("/entrar", "/", "/celular", "/demandas", "/horas"):
        html = (client if url != "/entrar" else TestClient(client.app, base_url=BASE)).get(url).text
        assert 'name="viewport"' in html and 'rel="manifest"' in html and "apple-touch-icon" in html, url
    html = client.get("/").text
    # o menu do celular abre sem JavaScript
    assert re.search(r'<input type="checkbox" id="menu-abrir"', html) and 'for="menu-abrir"' in html


def test_tv_is_unchanged(client):
    html = client.get("/tv").text
    assert "menu-abrir" not in html and "manifest" not in html
