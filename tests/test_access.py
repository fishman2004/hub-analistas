"""Fase 2: PIN, bloqueio, sessões do dia e papéis."""

import sqlite3
from datetime import date

import pytest

from conftest import at
from hub.access import (change_pin, create_pin, has_admin, reset_pin, session_person, set_access, start_session,
                        verify_pin)
from hub.db import SCHEMA, SCHEMA_VERSION, Database, events
from hub.people import ValidationError, add_person, deactivate_person, get_person


@pytest.fixture
def team(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    return db, kayo, bianca


def stored_hash(db, person_id):
    with db.connect() as conn:
        return conn.execute("SELECT pin_hash FROM people WHERE id = ?", (person_id,)).fetchone()[0]


def test_pin_is_stored_only_as_salted_hash(team):
    db, kayo, bianca = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    create_pin(db, at(8), bianca.id, "1234", "1234")
    a, b = stored_hash(db, kayo.id), stored_hash(db, bianca.id)
    assert "1234" not in a and a.startswith("pbkdf2_sha256$")
    assert a != b  # mesmo PIN, sal diferente


@pytest.mark.parametrize("pin, confirm, message", [
    ("123", "123", "O PIN tem de 4 a 6 números."),
    ("1234567", "1234567", "O PIN tem de 4 a 6 números."),
    ("12a4", "12a4", "O PIN tem de 4 a 6 números."),
    ("1234", "4321", "Os dois PINs não são iguais."),
])
def test_pin_rules(team, pin, confirm, message):
    db, kayo, _ = team
    with pytest.raises(ValidationError, match=message):
        create_pin(db, at(8), kayo.id, pin, confirm)
    assert not get_person(db, kayo.id).has_pin


def test_cannot_create_pin_twice(team):
    db, kayo, _ = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    with pytest.raises(ValidationError, match="já tem PIN"):
        create_pin(db, at(9), kayo.id, "9999", "9999")


def test_first_pin_becomes_admin_only_once(team):
    db, kayo, bianca = team
    assert not has_admin(db)
    create_pin(db, at(8), kayo.id, "1234", "1234")
    create_pin(db, at(8), bianca.id, "5678", "5678")
    assert get_person(db, kayo.id).is_admin and not get_person(db, bianca.id).is_admin
    assert get_person(db, kayo.id).role == "analista"


def test_five_wrong_pins_lock_for_some_minutes(team):
    db, kayo, _ = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    for left in (4, 3, 2, 1):
        with pytest.raises(ValidationError, match=f"Mais {left} tentativa"):
            verify_pin(db, at(9), kayo.id, "0000")
    with pytest.raises(ValidationError, match="Bloqueado até as 09:05"):
        verify_pin(db, at(9), kayo.id, "0000")
    # bloqueado: nem o PIN certo entra
    with pytest.raises(ValidationError, match="depois das 09:05"):
        verify_pin(db, at(9, 3), kayo.id, "1234")
    verify_pin(db, at(9, 6), kayo.id, "1234")


def test_right_pin_resets_the_count(team):
    db, kayo, _ = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    for _ in range(4):
        with pytest.raises(ValidationError):
            verify_pin(db, at(9), kayo.id, "0000")
    verify_pin(db, at(9), kayo.id, "1234")
    with pytest.raises(ValidationError, match="Mais 4 tentativas"):
        verify_pin(db, at(9), kayo.id, "0000")


def test_change_pin(team):
    db, kayo, _ = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    with pytest.raises(ValidationError, match="PIN atual não confere"):
        change_pin(db, at(9), kayo.id, "0000", "5555", "5555")
    change_pin(db, at(9), kayo.id, "1234", "5555", "5555")
    verify_pin(db, at(10), kayo.id, "5555")


def test_session_lasts_until_midnight(team):
    db, kayo, _ = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    token = start_session(db, at(8), kayo.id)
    assert session_person(db, at(23, 59), token).id == kayo.id
    assert session_person(db, at(0, 1, day=20), token) is None
    assert session_person(db, at(9), "token-inventado") is None


def test_admin_resets_pin_and_ends_sessions(team):
    db, kayo, bianca = team
    create_pin(db, at(8), kayo.id, "1234", "1234")  # vira administrador
    create_pin(db, at(8), bianca.id, "5678", "5678")
    token = start_session(db, at(8), bianca.id)
    with pytest.raises(PermissionError):
        reset_pin(db, at(9), get_person(db, bianca.id), kayo.id)
    reset_pin(db, at(9), get_person(db, kayo.id), bianca.id)
    assert not get_person(db, bianca.id).has_pin
    assert session_person(db, at(9), token) is None
    create_pin(db, at(10), bianca.id, "2468", "2468")  # cria outro no próximo acesso


def test_roles_and_admin_flag(team):
    db, kayo, bianca = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    admin = get_person(db, kayo.id)
    with pytest.raises(PermissionError):
        set_access(db, at(9), get_person(db, bianca.id), kayo.id, "gestor", False)
    set_access(db, at(9), admin, bianca.id, "gestor", True)
    b = get_person(db, bianca.id)
    assert b.role == "gestor" and b.is_manager and b.is_admin
    # agora há dois administradores: dá para tirar um
    set_access(db, at(9), admin, kayo.id, "analista", False)
    assert not get_person(db, kayo.id).is_admin
    kinds = [e["kind"] for e in events(db, date(2026, 10, 19), date(2026, 10, 19))]
    assert "papel_alterado" in kinds and "admin_alterado" in kinds


def test_always_one_admin_left(team):
    db, kayo, _ = team
    create_pin(db, at(8), kayo.id, "1234", "1234")
    admin = get_person(db, kayo.id)
    with pytest.raises(ValidationError, match="pelo menos um administrador"):
        set_access(db, at(9), admin, kayo.id, "analista", False)
    with pytest.raises(ValidationError, match="única pessoa administradora"):
        deactivate_person(db, at(9), kayo.id, kayo.id)
    with pytest.raises(ValidationError, match="Papel inválido"):
        set_access(db, at(9), admin, kayo.id, "chefe", True)


# ---------- migração a partir de um banco da v1 ----------

def make_v1_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO people(name, initials, color) VALUES ('Kayo', 'K', '#7FB2E5')")
    conn.execute("INSERT INTO demands(title, owner_id, column_, created_at, updated_at) "
                 "VALUES ('Relatório Aurora', 1, 'todo', '2026-10-19T08:00:00', '2026-10-19T08:00:00')")
    conn.execute("INSERT INTO events(at, actor_id, kind, subject, detail) "
                 "VALUES ('2026-10-19T08:00:00', 1, 'demanda_criada', 'demanda:1', 'Relatório Aurora')")
    conn.commit()
    conn.close()


def test_v1_database_migrates_without_losing_data(tmp_path):
    path = tmp_path / "hub.db"
    make_v1_db(path)
    db = Database(path)
    db.init()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("SELECT title FROM demands").fetchone()[0] == "Relatório Aurora"
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    kayo = get_person(db, 1)
    assert (kayo.name, kayo.role, kayo.is_admin, kayo.has_pin) == ("Kayo", "analista", False, False)
    # cópia do banco antes de mexer, com nome que a limpeza das cópias diárias não apaga
    copies = list((tmp_path / "copias").glob("antes-da-v1-*.db"))
    assert len(copies) == 1
    old = sqlite3.connect(copies[0])
    assert old.execute("SELECT COUNT(*) FROM demands").fetchone()[0] == 1
    old.close()
    # abrir de novo não migra nem copia outra vez
    db.init()
    assert len(list((tmp_path / "copias").glob("*.db"))) == 1


def test_new_database_needs_no_backup(tmp_path):
    db = Database(tmp_path / "hub.db")
    db.init()
    assert not (tmp_path / "copias").exists()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
