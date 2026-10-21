"""Fase 13: calendário (compromissos, feriados e ausências) e a tela Agenda da TV."""

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import calendario
from hub.access import set_access
from hub.calendario import (NO_HOLIDAYS, Holidays, add_absence, add_local_holiday, business_days, easter,
                            events_between, holidays, occurrences, save_event, set_holiday_active, tv_agenda)
from hub.db import Database
from hub.people import ValidationError, add_person, get_person
from hub.rotinas import list_routines, save_routine
from hub.web.app import create_app
from test_web_app import login


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    ana = add_person(db, at(7), None, "Ana Souza")
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url="http://hub-sala:8800"), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", False)
    app = create_app(db, clock=lambda: at(12))
    ck, cb, ca = (TestClient(app, base_url="http://hub-sala:8800") for _ in range(3))
    login(ck, kayo)
    login(cb, bianca)
    login(ca, ana)
    return db, ck, cb, ca, get_person(db, kayo.id), get_person(db, bianca.id), get_person(db, ana.id)


def event(db, actor, title="Reunião de fechamento", day=date(2026, 10, 20), **kw):
    return save_event(db, at(9), actor, None, title=title, kind=kw.pop("kind", "reuniao"), starts_on=day, **kw)


# ---------- feriados ----------

def test_easter_and_national_holidays():
    assert easter(2026) == date(2026, 4, 5) and easter(2027) == date(2027, 3, 28) and easter(2024) == date(2024, 3, 31)
    hol = Holidays()
    assert date(2026, 4, 3) in hol  # Sexta-feira Santa
    assert date(2026, 10, 12) in hol and date(2026, 11, 20) in hol
    assert date(2026, 2, 16) not in hol and date(2026, 6, 4) not in hol  # Carnaval e Corpus Christi: desligados
    assert date(2026, 10, 12) not in NO_HOLIDAYS
    assert len(business_days(2026, 10, hol)) == 21 and len(business_days(2026, 10)) == 22


def test_manage_holidays(env):
    db, ck, cb, ca, kayo, bianca, ana = env
    with pytest.raises(PermissionError):
        add_local_holiday(db, at(9), ana, date(2026, 11, 30), "Aniversário da cidade")
    add_local_holiday(db, at(9), bianca, date(2026, 11, 30), "Aniversário da cidade")
    with pytest.raises(ValidationError, match="feriado nacional"):
        add_local_holiday(db, at(9), bianca, date(2026, 11, 2), "Outro")
    set_holiday_active(db, at(9), kayo, date(2026, 2, 16), True)  # a empresa folga no Carnaval
    set_holiday_active(db, at(9), kayo, date(2026, 10, 12), False)  # e trabalha no dia 12
    hol = holidays(db)
    assert date(2026, 11, 30) in hol and date(2026, 2, 16) in hol and date(2026, 10, 12) not in hol
    assert hol == holidays(db) and hash(hol) == hash(holidays(db))  # o cache dos painéis compara assim
    html = ck.get("/calendario/feriados?ano=2026").text
    assert "Aniversário da cidade" in html and "Desligado" in html
    assert ca.post("/calendario/feriados/2026-11-30/remover").status_code == 403
    assert cb.post("/calendario/feriados/2026-11-30/remover", follow_redirects=False).status_code == 303
    assert date(2026, 11, 30) not in holidays(db)
    hist = ck.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "acrescentou o feriado 30/11/2026 Aniversário da cidade" in hist and "desligou o feriado 12/10/2026" in hist


def test_holiday_hides_routines_unless_marked(env):
    db, _, _, _, kayo, _, ana = env
    every_day = dict(weekdays=[0, 1, 2, 3, 4], starts_at="09:00", deadline=None, owner_id=ana.id, folders=[],
                     waits_for=[])
    save_routine(db, at(9), kayo, None, name="PHD", **every_day)
    save_routine(db, at(9), kayo, None, name="Plantão", on_holidays=True, **every_day)
    by_name = {r.name: r for r in list_routines(db)}
    assert not by_name["PHD"].runs_on(date(2026, 10, 12)) and by_name["PHD"].runs_on(date(2026, 10, 13))
    assert by_name["Plantão"].runs_on(date(2026, 10, 12))


# ---------- compromissos ----------

def test_repeat_is_calculated():
    base = dict(id=1, title="x", kind="reuniao", ends_on=None, starts_at=None, ends_at=None, place=None,
                description=None, visibility="equipe", reserved=False, created_by=1)
    weekly = calendario.Event(starts_on=date(2026, 10, 5), repeat="semanal", **base)
    assert occurrences(weekly, date(2026, 10, 19), date(2026, 10, 31)) == [date(2026, 10, 19), date(2026, 10, 26)]
    monthly = calendario.Event(starts_on=date(2026, 1, 31), repeat="mensal", **base)
    assert occurrences(monthly, date(2026, 2, 1), date(2026, 4, 30)) == [date(2026, 3, 31)]  # sem 31 em fev/abr
    yearly = calendario.Event(starts_on=date(2025, 10, 20), repeat="anual", **base)
    assert occurrences(yearly, date(2026, 10, 1), date(2026, 10, 31)) == [date(2026, 10, 20)]
    once = calendario.Event(starts_on=date(2026, 10, 20), repeat="", **{**base, "ends_on": date(2026, 10, 22)})
    assert occurrences(once, date(2026, 10, 21), date(2026, 10, 21)) == [date(2026, 10, 20)]  # passa pelo dia 21
    assert occurrences(once, date(2026, 10, 23), date(2026, 10, 31)) == []


def test_validation(env):
    db, *_, ana = env
    for bad in (dict(title=""), dict(starts_at="25:00"), dict(ends_at="10:00"),
                dict(starts_at="10:00", ends_at="09:00"), dict(ends_on=date(2026, 10, 1))):
        with pytest.raises(ValidationError):
            event(db, ana, **{"title": "Reunião", **bad})


def test_private_and_reserved_events(env):
    db, ck, cb, ca, kayo, bianca, ana = env
    mine = event(db, ana, "Dentista da Ana", visibility="pessoal", description="consulta")
    reserved = event(db, kayo, "Conversa de promoção", reserved=True, people=[kayo.id], description="pauta secreta")
    team = event(db, ana, "Treinamento Power BI", kind="treinamento", starts_at="14:00", ends_at="16:00")
    month = ca.get("/calendario?data=2026-10-20").text
    assert "Dentista da Ana" in month and "Conversa de promoção" not in month and "Compromisso reservado" in month
    other = ck.get("/calendario?visao=semana&data=2026-10-20").text
    assert "Dentista" not in other and "Conversa de promoção" in other and "Treinamento Power BI" in other
    assert ck.get(f"/calendario/{mine.id}").status_code == 404  # "só eu": nem o administrador
    assert ca.get(f"/calendario/{reserved.id}").status_code == 403
    assert "pauta secreta" in cb.get(f"/calendario/{reserved.id}").text  # o gestor vê
    # editar: quem criou, o gestor e os administradores
    assert ca.post(f"/calendario/{reserved.id}/excluir").status_code == 403
    r = cb.post(f"/calendario/{team.id}", data={"title": "Treinamento Power BI (sala 2)", "kind": "treinamento",
                                                "starts_on": "2026-10-20", "visibility": "equipe"},
                follow_redirects=False)
    assert r.status_code == 303
    with pytest.raises(PermissionError):
        calendario.delete_event(db, at(9), kayo, mine.id)
    # o histórico não fala do "só eu" e mascara o reservado para quem não participa
    hist = ca.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "Dentista" not in hist and "Conversa de promoção" not in hist and "Compromisso reservado" in hist
    assert "Conversa de promoção" in ck.get("/historico?de=2026-10-19&ate=2026-10-19").text


def test_create_through_the_app(env):
    _, _, _, ca, *_ = env
    assert "Novo compromisso" in ca.get("/calendario/novo?data=2026-10-22").text
    r = ca.post("/calendario", data={"title": "Entrega do relatório Aurora", "kind": "entrega",
                                     "starts_on": "2026-10-22", "visibility": "equipe", "repeat": ""},
                follow_redirects=False)
    assert r.status_code == 303 and "data=2026-10-22" in r.headers["location"]
    assert "Entrega do relatório Aurora" in ca.get("/calendario?visao=lista&data=2026-10-19").text
    r = ca.post("/calendario", data={"title": "", "kind": "entrega", "starts_on": "2026-10-22"})
    assert r.status_code == 422 and "Informe o título" in r.text


def test_filters_and_what_the_hub_already_knows(env):
    db, ck, *_, kayo, _, ana = env
    from hub.demands import create_demand
    create_demand(db, at(8), kayo.id, title="Relatório da pasta B", owner_id=ana.id, due=date(2026, 10, 23))
    html = ck.get("/calendario?data=2026-10-20").text
    assert "Relatório da pasta B" in html and "Nossa Senhora Aparecida" in html
    html = ck.get("/calendario?data=2026-10-20&filtros=1&f=feriados").text
    assert "Relatório da pasta B" not in html and "Nossa Senhora Aparecida" in html


# ---------- ausências ----------

def test_absences(env):
    db, ck, cb, ca, kayo, bianca, ana = env
    with pytest.raises(PermissionError):
        add_absence(db, at(9), kayo, ana.id, date(2026, 10, 19), date(2026, 10, 23))  # admin não é gestor
    r = ca.post("/calendario/ausencias", data={"pessoa": str(ana.id), "de": "2026-10-19", "ate": "2026-10-23",
                                               "motivo": "Consulta médica"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Consulta médica" in ca.get("/calendario").text and "Consulta médica" in cb.get("/calendario").text
    assert "Consulta médica" not in ck.get("/calendario").text  # o motivo é só da pessoa e do gestor
    hist = ck.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "marcou ausência de Ana Souza (19/10 a 23/10)" in hist and "Consulta" not in hist
    with pytest.raises(ValidationError):
        add_absence(db, at(9), ana, ana.id, date(2026, 10, 1), date(2026, 12, 31))


# ---------- TV ----------

def test_presence_strip_shows_absent_until(env):
    db, ck, *_, ana = env
    add_absence(db, at(9), ana, ana.id, date(2026, 10, 19), date(2026, 10, 25), "Férias")
    people = {p["name"]: p for p in ck.get("/api/tv").json()["people"]}
    assert people["Ana Souza"]["ausente_ate"] == "25/10" and people["Kayo"]["ausente_ate"] == ""
    assert "Férias" not in ck.get("/api/tv").text


def test_tv_agenda_never_leaks(env):
    db, ck, *_, kayo, bianca, ana = env
    assert tv_agenda(db, at(12)) is None
    event(db, kayo, "Fechamento", day=date(2026, 10, 19), starts_at="15:00", description="pauta detalhada",
          place="Sala 3", people=[kayo.id, ana.id])
    event(db, kayo, "Conversa de promoção", day=date(2026, 10, 20), reserved=True)
    event(db, ana, "Dentista da Ana", day=date(2026, 10, 19), visibility="pessoal")
    add_absence(db, at(9), ana, ana.id, date(2026, 10, 21), date(2026, 10, 21), "Consulta médica")
    data = tv_agenda(db, at(12))
    assert [g["label"] for g in data["groups"]] == ["Hoje", "Amanhã", "Quarta"]
    assert [i["titulo"] for i in data["groups"][0]["itens"]] == ["Fechamento"]
    assert data["groups"][0]["itens"][0]["hora"] == "15:00"
    tv = ck.get("/api/tv").text
    for secret in ("pauta detalhada", "Sala 3", "Conversa de promoção", "Dentista", "Consulta médica"):
        assert secret not in tv
    assert "Compromisso reservado" in tv and '"agenda"' in tv
    # domingo só entra se for feriado; feriado aparece no grupo do dia
    days = tv_agenda(db, at(12, day=9))  # sexta 09/10: sábado, segunda (12/10, feriado)...
    assert days is not None and any(i["tipo"] == "feriado" for g in days["groups"] for i in g["itens"])


def test_migration_9_from_a_1_4_0_database(tmp_path):
    from hub.db import MIGRATIONS, SCHEMA
    path = tmp_path / "hub.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for number, sql in MIGRATIONS:
        if number <= 8:
            conn.executescript(sql)
    conn.execute("PRAGMA user_version = 8")
    conn.execute("INSERT INTO people(name, initials, color) VALUES ('Ana Souza', 'AS', '#7FB2E5')")
    conn.execute("INSERT INTO routines(name, weekdays, starts_at, owner_id) VALUES ('PHD', '0,1,2,3,4', '09:00', 1)")
    conn.commit()
    conn.close()
    db = Database(path)
    db.init()
    with db.connect() as c:
        assert c.execute("SELECT on_holidays FROM routines").fetchone()[0] == 0
        for table in ("events_cal", "event_people", "holidays", "absences"):
            assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert date(2026, 10, 12) in holidays(db)
    assert events_between(db, get_person(db, 1), date(2026, 10, 1), date(2026, 10, 31)) == []
