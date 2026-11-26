import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import zerar
from hub.access import create_pin
from hub.db import events, log_event
from hub.demands import board, create_demand
from hub.people import ValidationError, add_person, get_person, list_people
from hub.web.app import create_app

BASE = "http://hub-sala:8800"


@pytest.fixture
def team(db):
    kayo = add_person(db, at(7), None, "Kayo")
    create_pin(db, at(7), kayo.id, "1234", "1234")  # o primeiro com PIN vira administrador
    bianca = add_person(db, at(7), None, "Bianca")
    create_pin(db, at(7), bianca.id, "5678", "5678")
    return db, get_person(db, kayo.id), get_person(db, bianca.id)


def fill(db, kayo):
    create_demand(db, at(9), kayo.id, title="Teste 1", owner_id=kayo.id)
    create_demand(db, at(9), kayo.id, title="Teste 2", owner_id=kayo.id)
    with db.connect() as conn:
        conn.execute("INSERT INTO notes(person_id, title, created_at, updated_at) VALUES (?, 'minha', 'x', 'x')",
                     (kayo.id,))
        conn.execute("INSERT INTO holidays(day, name, source) VALUES ('2026-11-20', 'Feriado da cidade', 'local')")


def test_only_admin_with_pin_and_word(team):
    db, kayo, bianca = team
    fill(db, kayo)
    with pytest.raises(PermissionError):
        zerar.zerar(db, at(10), bianca, "5678", "APAGAR", ["demandas"])
    with pytest.raises(ValidationError, match="APAGAR"):
        zerar.zerar(db, at(10), kayo, "1234", "apaga", ["demandas"])
    with pytest.raises(ValidationError, match="PIN errado"):
        zerar.zerar(db, at(10), kayo, "9999", "APAGAR", ["demandas"])
    with pytest.raises(ValidationError, match="pelo menos uma"):
        zerar.zerar(db, at(10), kayo, "1234", "APAGAR", [])
    assert len(board(db, at(10))["todo"]) == 2  # nada foi apagado


def test_wipes_what_happened_and_keeps_setup(team):
    db, kayo, bianca = team
    fill(db, kayo)
    keys = [g.key for g in zerar.GROUPS if g.default]
    result = zerar.zerar(db, at(10), kayo, "1234", "apagar", keys)
    assert result["apagados"]["demandas"] == 2 and "notas" not in result["apagados"]
    assert board(db, at(10))["todo"] == []
    # pessoas, PINs, feriados e as notas (desligadas por padrão) continuam
    assert {p.name for p in list_people(db)} == {"Kayo", "Bianca"}
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM holidays").fetchone()[0] == 1
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM events")]
    assert kinds == ["historico_zerado"]  # o histórico começa com o registro de quem zerou
    # a cópia de antes tem tudo
    with sqlite3.connect(result["copia"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM demands").fetchone()[0] == 2


def test_attachment_files_are_kept_aside(team, tmp_path, monkeypatch):
    db, kayo, _ = team
    from hub import anexos

    monkeypatch.setattr(anexos, "folder", lambda db: tmp_path / "Anexos")
    d = create_demand(db, at(9), kayo.id, title="Com anexo", owner_id=kayo.id)
    f = tmp_path / "Anexos" / "2026-10" / "abc"
    f.parent.mkdir(parents=True)
    f.write_text("oi")
    with db.connect() as conn:
        conn.execute("INSERT INTO attachments(kind, parent_id, name, stored, size, sha256, uploaded_at) "
                     "VALUES ('demanda', ?, 'a.txt', '2026-10/abc', 2, 'x', 'x')", (d.id,))
    result = zerar.zerar(db, at(10), kayo, "1234", "APAGAR", ["demandas"])
    assert not f.exists()
    assert (tmp_path / result["anexos"] / "2026-10" / "abc").read_text() == "oi"


def test_page_and_form(team):
    db, kayo, bianca = team
    fill(db, kayo)
    c = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE)
    c.post(f"/entrar/{kayo.id}", data={"pin": "1234"})
    page = c.get("/configuracoes").text
    assert "Zerar o histórico" in page and "(2)" in page
    r = c.post("/configuracoes/zerar", data={"grupo_demandas": "on", "pin": "0000", "confirmar": "APAGAR"})
    assert r.status_code == 422 and "PIN errado" in r.text
    r = c.post("/configuracoes/zerar", data={"grupo_demandas": "on", "pin": "1234", "confirmar": "APAGAR"})
    assert r.status_code == 200 and "o histórico foi zerado" in r.text
    assert board(db, at(12))["todo"] == []
    other = TestClient(c.app, base_url=BASE)
    other.post(f"/entrar/{bianca.id}", data={"pin": "5678"})
    assert other.post("/configuracoes/zerar", data={"grupo_historico": "on", "pin": "5678",
                                                     "confirmar": "APAGAR"}).status_code == 403
