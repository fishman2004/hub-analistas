import io
import sqlite3
from dataclasses import replace
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from conftest import at
from hub import horas
from hub.horas import (can_see, delete_entry, duration, export_rows, import_balances, parse_duration, save_entry,
                       save_journey, set_balance, summary)
from hub.people import ValidationError, add_person, get_person
from hub.web.app import create_app
from test_web_app import BASE, login

# 19/10/2026 é segunda-feira; a jornada padrão é das 8h às 18h (10:00, almoço dentro) de segunda a sexta


@pytest.fixture
def team(db):
    gestor = add_person(db, at(7), None, "Gabriela Gestora")
    ana = add_person(db, at(7), None, "Ana Souza")
    bia = add_person(db, at(7), None, "Bianca Lima")
    with db.connect() as conn:
        conn.execute("UPDATE people SET role = 'gestor', is_admin = 1 WHERE id = ?", (gestor.id,))
    return get_person(db, gestor.id), ana, bia


def test_durations_from_the_base_spreadsheet():
    assert parse_duration("12:30") == 750 and parse_duration("-03:15") == -195 and parse_duration("+1:05") == 65
    assert parse_duration("12,5") == 750 and parse_duration(1.5) == 90 and parse_duration("-2h") == -120
    assert parse_duration(time(4, 20)) == 260 and parse_duration(timedelta(hours=30)) == 1800
    assert duration(750) == "+12:30" and duration(-195) == "-03:15" and duration(0) == "00:00"
    with pytest.raises(ValidationError, match="Saldo que não entendi"):
        parse_duration("muito")


def test_day_entry_and_balance(db, team):
    _, ana, _ = team
    save_entry(db, at(9, day=20), ana, date(2026, 10, 19), "07:50", "18:12")  # 10h22: +22min
    save_entry(db, at(9, day=21), ana, date(2026, 10, 20), "08:30", "17:00")  # 8h30: -1h30
    s = summary(db, ana.id, date(2026, 10, 21))
    assert [e.day for e in s.entries] == [date(2026, 10, 20), date(2026, 10, 19)]
    assert s.entries[1].worked == 622 and s.entries[1].diff == 22
    assert s.balance == 22 - 90 and s.base is None
    assert s.missing == []  # sem saldo base, os dias sem lançamento contam do primeiro lançamento


def test_entry_validation(db, team):
    _, ana, _ = team
    day = date(2026, 10, 19)
    with pytest.raises(ValidationError, match="saída tem de ser depois"):
        save_entry(db, at(9, day=20), ana, day, "18:00", "08:00")
    with pytest.raises(ValidationError, match="formato hh:mm"):
        save_entry(db, at(9, day=20), ana, day, "8h", "18:00")
    with pytest.raises(ValidationError, match="formato hh:mm"):
        save_entry(db, at(9, day=20), ana, day, "08:00", "25:00")
    with pytest.raises(ValidationError, match="ainda não chegou"):
        save_entry(db, at(9, day=20), ana, date(2026, 10, 21), "08:00", "18:00")


def test_no_duplicate_day_and_correction_goes_to_history(db, team):
    _, ana, _ = team
    day = date(2026, 10, 19)
    save_entry(db, at(9, day=20), ana, day, "08:00", "17:00")
    with pytest.raises(ValidationError, match="já foi lançado"):
        save_entry(db, at(9, day=20), ana, day, "08:00", "18:00")
    save_entry(db, at(10, day=20), ana, day, "08:00", "18:00", correcting=True)
    assert summary(db, ana.id, date(2026, 10, 20)).entries[0].saida == 18 * 60
    delete_entry(db, at(11, day=20), ana, day)
    with db.connect() as conn:
        kinds = [(r["kind"], r["subject"], r["detail"]) for r in conn.execute(
            "SELECT * FROM events WHERE kind LIKE 'horas_%' ORDER BY id")]
    assert kinds == [("horas_lancado", f"horas:{ana.id}", "19/10"),
                     ("horas_corrigido", f"horas:{ana.id}", "19/10: 08:00–17:00 → 08:00–18:00"),
                     ("horas_excluido", f"horas:{ana.id}", "19/10: 08:00–18:00")]


def test_base_balance_and_missing_days(db, team):
    gestor, ana, bia = team
    set_balance(db, at(9, day=13), gestor, ana.id, 600, date(2026, 10, 9))  # +10h até sexta 09/10
    with pytest.raises(ValidationError, match="já está no saldo base"):
        save_entry(db, at(9, day=20), ana, date(2026, 10, 9), "08:00", "18:00")
    save_entry(db, at(9, day=20), ana, date(2026, 10, 13), "08:00", "17:00")  # -1h
    s = summary(db, ana.id, date(2026, 10, 20))
    assert s.base == 600 and s.balance == 540
    # 14 a 19/10 sem lançamento, sem contar sábado e domingo (sem jornada) nem o feriado de 12/10;
    # hoje (20) ainda não conta
    assert s.missing == [date(2026, 10, 19), date(2026, 10, 16), date(2026, 10, 15), date(2026, 10, 14)]
    with pytest.raises(PermissionError):
        set_balance(db, at(9), ana, bia.id, 60, date(2026, 10, 9))  # analista não mexe no saldo de ninguém


def test_holiday_has_no_planned_hours(db, team):
    _, ana, _ = team
    save_entry(db, at(9, day=13), ana, date(2026, 10, 12), "08:00", "12:00")  # 12/10: feriado nacional
    s = summary(db, ana.id, date(2026, 10, 13))
    assert s.balance == 4 * 60 and date(2026, 10, 12) not in s.missing


def test_journey_is_configurable_and_saturday_can_count(db, team):
    gestor, ana, _ = team
    save_journey(db, at(9), gestor, "08:00", "04:00")
    save_entry(db, at(9, day=19), ana, date(2026, 10, 17), "08:00", "12:00")  # sábado
    assert summary(db, ana.id, date(2026, 10, 19)).balance == 0
    with pytest.raises(PermissionError):
        save_journey(db, at(9), ana, "09:00", "")


def xlsx(rows):
    book = Workbook()
    for r in rows:
        book.active.append(r)
    out = io.BytesIO()
    book.save(out)
    out.seek(0)
    return out


def test_import_base_spreadsheet(db, team):
    gestor, ana, bia = team
    data = xlsx([["Nome", "Saldo", "Data"], ["ana souza", "-03:15", "15/10/2026"], ["Bianca Lima", 12.5, None],
                 ["Pessoa Fora do Hub", "01:00", None], [None, None, None]])
    updated, unknown = import_balances(db, at(9, day=20), gestor, "Banco de horas.xlsx", data)
    assert updated == 2 and unknown == ["Pessoa Fora do Hub"]
    a, b = summary(db, ana.id, date(2026, 10, 20)), summary(db, bia.id, date(2026, 10, 20))
    assert (a.base, a.as_of) == (-195, date(2026, 10, 15))
    assert (b.base, b.as_of) == (750, date(2026, 10, 19))  # sem DATA: vale até ontem
    csv_data = io.BytesIO("NOME;SALDO\nAna Souza;02:00\n".encode("cp1252"))
    assert import_balances(db, at(9, day=20), gestor, "base.csv", csv_data) == (1, [])
    with pytest.raises(ValidationError, match="Faltam as colunas: SALDO"):
        import_balances(db, at(9, day=20), gestor, "base.csv", io.BytesIO(b"NOME;HORAS\nAna;1\n"))
    with pytest.raises(ValidationError, match="Ana Souza: Saldo que não entendi"):
        import_balances(db, at(9, day=20), gestor, "base.csv", io.BytesIO(b"NOME;SALDO\nAna Souza;x\n"))
    with pytest.raises(PermissionError):
        import_balances(db, at(9), ana, "base.csv", io.BytesIO(b"NOME;SALDO\n"))


def test_who_can_see_hours(team):
    gestor, ana, bia = team
    assert can_see(ana, ana.id) and can_see(gestor, ana.id)
    assert not can_see(bia, ana.id) and not can_see(None, ana.id)
    admin_only = replace(bia, is_admin=True)
    assert not can_see(admin_only, ana.id)  # administrador não basta: só a pessoa e o gestor


def test_export_for_the_manager(db, team):
    gestor, ana, _ = team
    set_balance(db, at(9), gestor, ana.id, 60, date(2026, 10, 16))
    save_entry(db, at(9, day=20), ana, date(2026, 10, 19), "07:48", "18:00")
    saldos = export_rows(db, date(2026, 10, 20), "saldos")
    assert saldos[0][:2] == ["Nome", "Saldo"]
    assert ["Ana Souza", "+01:12", "+01:00", "16/10/2026", "19/10/2026", 0] in saldos
    lanc = export_rows(db, date(2026, 10, 20), "lancamentos")
    assert lanc[1] == ["Ana Souza", "19/10/2026", "segunda", "07:48", "18:00", "10:12", "10:00", "+00:12"]
    assert horas.to_csv(lanc).startswith("﻿Nome;Dia".encode())


# ---------- páginas ----------

@pytest.fixture
def web(db, team):
    return TestClient(create_app(db, clock=lambda: at(9, day=20)), base_url=BASE)


def test_person_launches_and_sees_only_their_own(db, team, web):
    gestor, ana, bia = team
    login(web, ana)
    r = web.post("/horas", data={"dia": "2026-10-19", "entrada": "07:48", "saida": "18:00"}, follow_redirects=False)
    assert r.status_code == 303
    page = web.get("/horas").text
    assert "+00:12" in page and "19/10" in page
    assert web.get("/horas/equipe").status_code == 403
    assert web.get(f"/horas/equipe/{bia.id}").status_code == 403
    assert web.get("/horas/exportar?tipo=saldos&formato=csv").status_code == 403
    r = web.post("/horas", data={"dia": "2026-10-19", "entrada": "08:00", "saida": "18:00"})
    assert r.status_code == 422 and "já foi lançado" in r.text


def test_manager_sees_everyone_imports_and_exports(db, team, web):
    gestor, ana, bia = team
    save_entry(db, at(9, day=20), ana, date(2026, 10, 19), "08:00", "18:00")
    login(web, gestor)
    page = web.get("/horas/equipe").text
    assert "Ana Souza" in page and "Bianca Lima" in page
    assert "08:00" in web.get(f"/horas/equipe/{ana.id}").text
    r = web.post("/horas/equipe/importar", files={"arquivo": ("base.csv", b"NOME;SALDO\nBianca Lima;-01:00\n")})
    assert r.status_code == 200 and "1 pessoa" in r.text
    r = web.get("/horas/exportar?tipo=saldos&formato=csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "Bianca Lima;-01:00" in r.content.decode("utf-8-sig")
    r = web.get("/horas/exportar?tipo=lancamentos&formato=xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_history_hides_hours_from_other_analysts(db, team, web):
    gestor, ana, bia = team
    save_entry(db, at(9, day=20), ana, date(2026, 10, 19), "08:00", "18:00")
    save_entry(db, at(9, day=20), ana, date(2026, 10, 19), "08:00", "17:00", correcting=True)
    login(web, bia)
    assert "banco de horas de" not in web.get("/historico").text
    web.cookies.clear()
    login(web, ana)
    assert "corrigiu o banco de horas de 19/10" in web.get("/historico").text
    web.cookies.clear()
    login(web, gestor)
    assert "Ana Souza corrigiu o banco de horas" in web.get("/historico").text


def test_tv_never_touches_the_hours_tables(db, team, tmp_path):
    gestor, ana, _ = team
    set_balance(db, at(9), gestor, ana.id, 754, date(2026, 10, 16))
    save_entry(db, at(9, day=20), ana, date(2026, 10, 19), "07:13", "18:41")

    statements = []

    class Traced(type(db)):
        def connect(self):
            ctx = super().connect()
            conn = ctx.__enter__()
            conn.set_trace_callback(statements.append)

            class Wrapper:
                def __enter__(self_inner):
                    return conn

                def __exit__(self_inner, *exc):
                    return ctx.__exit__(*exc)
            return Wrapper()

    traced = Traced(db.path)
    client = TestClient(create_app(traced, clock=lambda: at(9, day=20)), base_url=BASE)
    body = client.get("/api/tv").text
    assert statements and not any("hours_" in s for s in statements)
    assert "07:13" not in body and "18:41" not in body and "12:34" not in body


def test_v1_database_gets_the_hours_tables(tmp_path):
    from hub.db import SCHEMA, Database
    path = tmp_path / "hub.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO people(name, initials, color) VALUES ('Ana Souza', 'AS', '#7FB2E5')")
    conn.commit()
    conn.close()
    db = Database(path)
    db.init()
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM hours_entries").fetchone()[0] == 0
        assert conn.execute("SELECT name FROM people").fetchone()[0] == "Ana Souza"
