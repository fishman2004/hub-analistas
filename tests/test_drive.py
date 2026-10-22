"""Fase 22: o Hub baixa sozinho a 8081 do Google Drive, pela ponte do Apps Script com chave."""

import base64
import json
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import drive
from hub.access import create_pin
from hub.paineis import find_file, panel_folder, store_for
from hub.people import ValidationError, add_person, get_person
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
URL = "https://script.google.com/macros/s/ABC123/exec"
KEY = "k" * 43
VENDAS = Path(__file__).parent.parent / "tools" / "exemplos" / "(DADOS) - 8081 - Vendas.csv"
NOW = datetime(2026, 9, 18, 9, 0)
BASE_NAME = "(DADOS) - 8081 - Vendas"


class Ponte:
    """Faz o papel da ponte do Apps Script (tools/drive/ponte-8081.gs)."""

    def __init__(self, content: bytes = VENDAS.read_bytes(), tipo: str = "csv",
                 modificado: str = "2026-09-18T11:30:00.000Z", key: str = KEY):
        self.content, self.tipo, self.modificado, self.key = content, tipo, modificado, key
        self.calls = []

    def __call__(self, url: str, timeout: int) -> bytes:
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.calls.append(query)
        if query.get("chave") != self.key:
            return json.dumps({"ok": False, "erro": "chave"}).encode()
        if query.get("desde") == self.modificado:
            return json.dumps({"ok": True, "igual": True, "modificado": self.modificado}).encode()
        return json.dumps({"ok": True, "modificado": self.modificado, "tipo": self.tipo,
                           "conteudo": base64.b64encode(self.content).decode()}).encode()


@pytest.fixture
def people(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bia = add_person(db, at(7), None, "Bia")
    create_pin(db, at(7), kayo.id, "1234", "1234")  # administrador
    create_pin(db, at(7), bia.id, "1234", "1234")
    return get_person(db, kayo.id), get_person(db, bia.id), create_app(db, clock=lambda: NOW)


def login(app, person):
    c = TestClient(app, base_url=BASE)
    c.post(f"/entrar/{person.id}", data={"pin": "1234"})
    return c


def turn_on(db, admin, minutes="10"):
    drive.save_drive_config(db, NOW, admin, URL, KEY, minutes)


# ---------- configuração ----------

def test_config_validates_and_never_shows_the_key(db, people):
    kayo, bia, app = people
    with pytest.raises(PermissionError):
        drive.save_drive_config(db, NOW, bia, URL, KEY, "10")
    with pytest.raises(ValidationError, match="script.google.com"):
        drive.save_drive_config(db, NOW, kayo, "https://exemplo.com/roubar", KEY, "10")
    with pytest.raises(ValidationError, match="de 2 a 120 minutos"):
        drive.save_drive_config(db, NOW, kayo, URL, KEY, "1")
    with pytest.raises(ValidationError, match="pelo menos 32"):
        drive.save_drive_config(db, NOW, kayo, URL, "curta", "10")
    assert not drive.enabled(db)
    created = drive.save_drive_config(db, NOW, kayo, URL, "", "15", generate=True)
    assert len(created) >= 32 and drive.enabled(db) and drive.interval_minutes(db) == 15
    # em branco mantém a chave guardada
    drive.save_drive_config(db, NOW, kayo, URL, "", "15")
    assert drive.get_setting(db, drive.SETTING_KEY) == created
    cfg = drive.drive_config(db)
    assert cfg["has_key"] and created not in json.dumps(cfg, default=str)
    # tela de configurações: a chave aparece só uma vez, logo depois de gerar
    admin = login(app, kayo)
    assert created not in admin.get("/configuracoes").text
    r = admin.post("/configuracoes/drive", data={"url": URL, "chave": "", "minutos": "10", "gerar": "1"})
    assert r.status_code == 200 and "CHAVE_HUB" in r.text
    second = drive.get_setting(db, drive.SETTING_KEY)
    assert second != created and second in r.text
    assert second not in admin.get("/configuracoes").text
    assert login(app, bia).post("/configuracoes/drive", data={"url": URL, "minutos": "10"}).status_code == 403
    # desligar apaga a chave
    admin.post("/configuracoes/drive", data={"url": "", "chave": "", "minutos": "10"})
    assert not drive.enabled(db) and drive.get_setting(db, drive.SETTING_KEY) is None


# ---------- download ----------

def test_download_puts_the_8081_in_the_panels_folder(db, people):
    kayo, _, _ = people
    turn_on(db, kayo)
    ponte = Ponte()
    result = drive.sync(db, NOW, ponte)
    assert result.ok and result.changed
    saved = find_file(panel_folder(db), BASE_NAME)
    assert saved is not None and saved.suffix == ".csv" and saved.read_bytes() == VENDAS.read_bytes()
    # a data do arquivo é a do Drive (para o "atualizado às" e o aviso de dados velhos)
    assert saved.stat().st_mtime == datetime.fromisoformat("2026-09-18T11:30:00+00:00").timestamp()
    assert store_for(db).get(wait=True).status("vendas").ok
    # da segunda vez manda o "desde" e não baixa de novo
    again = drive.sync(db, NOW + timedelta(minutes=10), ponte)
    assert again.ok and not again.changed and ponte.calls[-1]["desde"] == ponte.modificado
    cfg = drive.drive_config(db)
    assert cfg["baixado"] == NOW and cfg["verificado"] == NOW + timedelta(minutes=10) and cfg["error"] == ""
    assert not [p for p in panel_folder(db).iterdir() if "baixando" in p.name]


def test_new_format_replaces_the_old_file(db, people):
    from openpyxl import Workbook

    kayo, _, _ = people
    turn_on(db, kayo)
    drive.sync(db, NOW, Ponte())
    book = Workbook()
    book.active.append(["DATA PEDIDO", "ID CLIENTE", "NOME RCA", "NOME SUPERVISOR", "ID PRODUTO", "ID FORNECEDOR", "VALOR"])
    book.active.append(["18/09/2026", 1, "A-XX-01- ANA", "A-XX (BIA)", 7, 9, 10.5])
    path = db.path.parent / "novo.xlsx"
    book.save(path)
    assert drive.sync(db, NOW, Ponte(path.read_bytes(), "xlsx", "2026-09-18T12:00:00Z")).changed
    folder = panel_folder(db)
    assert (folder / f"{BASE_NAME}.xlsx").is_file() and not (folder / f"{BASE_NAME}.csv").exists()


def test_bad_file_never_replaces_the_good_one(db, people):
    kayo, _, _ = people
    turn_on(db, kayo)
    drive.sync(db, NOW, Ponte())
    saved = find_file(panel_folder(db), BASE_NAME)
    good = saved.read_bytes()
    bad = drive.sync(db, NOW, Ponte(b"COLUNA;OUTRA\n1;2\n", modificado="2026-09-18T12:00:00Z"))
    assert not bad.ok and "Faltam as colunas" in bad.message
    assert saved.read_bytes() == good
    assert not drive.sync(db, NOW, Ponte(tipo="pdf", modificado="x")).ok
    assert "vazio" in drive.sync(db, NOW, Ponte(b"", modificado="y")).message
    assert not [p for p in panel_folder(db).iterdir() if "baixando" in p.name]
    assert "vazio" in drive.drive_config(db)["error"]  # a página mostra o último problema


def test_wrong_key_and_network_errors_are_explained_without_the_key(db, people, caplog):
    kayo, _, _ = people
    turn_on(db, kayo)
    r = drive.sync(db, NOW, Ponte(key="outra" * 10))
    assert not r.ok and "recusou a chave" in r.message

    def offline(url, timeout):
        raise urllib.error.URLError(OSError("sem rede " + url))

    r = drive.sync(db, NOW, offline)
    assert not r.ok and "Sem conexão" in r.message and KEY not in r.message

    def html_page(url, timeout):
        return b"<html>Entrar no Google</html>"

    r = drive.sync(db, NOW, html_page)
    assert not r.ok and "/exec" in r.message
    assert KEY not in caplog.text and KEY not in json.dumps(drive.state(db))


def test_due_respects_the_interval(db, people):
    kayo, _, _ = people
    assert not drive.due(db, NOW)  # desligado
    turn_on(db, kayo, "10")
    assert drive.due(db, NOW)
    drive.sync(db, NOW, Ponte())
    assert not drive.due(db, NOW + timedelta(minutes=9))
    assert drive.due(db, NOW + timedelta(minutes=10))


def test_panels_page_shows_the_status_and_download_now(db, people, monkeypatch):
    kayo, bia, app = people
    html = login(app, kayo).get("/paineis").text
    assert "Base 8081 do Google Drive" in html and "/configuracoes#drive" in html
    turn_on(db, kayo)
    ponte = Ponte()
    monkeypatch.setattr(drive, "_http_get", ponte)
    assert login(app, bia).post("/paineis/drive/baixar").status_code == 403
    assert "/paineis/drive/baixar" not in login(app, bia).get("/paineis").text
    r = login(app, kayo).post("/paineis/drive/baixar")
    assert r.status_code == 200 and "Arquivo novo baixado" in r.text and "ligado" in r.text
    assert "18/09 às 09:00" in r.text
    r = login(app, kayo).post("/paineis/drive/baixar")
    assert "não mudou" in r.text
    ponte.key = "outra" * 10
    r = login(app, kayo).post("/paineis/drive/baixar")
    assert r.status_code == 422 and "recusou a chave" in r.text


def test_bridge_script_keeps_the_key_out_of_the_code():
    script = (Path(__file__).parent.parent / "tools" / "drive" / "ponte-8081.gs").read_text(encoding="utf-8")
    assert "getProperty('CHAVE_HUB')" in script and "function doGet" in script
    assert "chave.length < 32" in script and "erro: 'chave'" in script
