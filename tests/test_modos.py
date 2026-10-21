"""Fase 14: modos da TV (receitas da rotação), regras automáticas, troca à mão e as páginas."""

import sqlite3
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import modos
from hub.access import set_access
from hub.calendario import Holidays, NO_HOLIDAYS, add_local_holiday
from hub.db import Database
from hub.demands import create_demand
from hub.people import ValidationError, add_person, get_person
from hub.telas import rotation
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    ana = add_person(db, at(7), None, "Ana Souza")
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url=BASE), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", False)
    clock = {"now": at(12)}
    app = create_app(db, clock=lambda: clock["now"])
    ck, cb, ca = (TestClient(app, base_url=BASE) for _ in range(3))
    for c, p in ((ck, kayo), (cb, bianca), (ca, ana)):
        login(c, p)
    return db, clock, ck, cb, ca, get_person(db, kayo.id), get_person(db, bianca.id), get_person(db, ana.id)


def by_key(db):
    return {m.builtin: m for m in modos.list_modes(db) if m.builtin}


def ids(db, now):
    return [s["id"] for s in rotation(db, now)["screens"]]


def test_default_mode_copies_old_settings(tmp_path):
    path = tmp_path / "hub.db"
    from hub.db import MIGRATIONS, SCHEMA
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for number, sql in MIGRATIONS:
        if number <= 9:
            conn.executescript(sql)
    conn.execute("PRAGMA user_version = 9")
    conn.executemany("INSERT INTO settings(key, value) VALUES (?, ?)",
                     [("tela.quadro.segundos", "45"), ("tela.prazos.ligada", "0"), ("tv.pagina.segundos", "7")])
    conn.commit()
    conn.close()
    db = Database(path)
    db.init()
    padrao = modos.default_mode(db)
    seconds = {s.id: (s.seconds, s.enabled) for s in padrao.screens}
    assert seconds["quadro"] == (45, True) and seconds["prazos"][1] is False and seconds["agenda"] == (15, True)
    assert padrao.page_seconds == 7
    keys = by_key(db)
    assert {"inicio-mes", "fim-mes", "visita", "reuniao", "so-quadro"} <= set(keys)
    assert keys["inicio-mes"].rule_on and keys["fim-mes"].rule_on and not keys["visita"].rule_on
    assert len(modos.list_modes(db)) == len(modos.BUILTINS)  # ler de novo não cria outra vez


def test_rules():
    hol = Holidays()
    first5 = {"tipo": "primeiros_dias_uteis", "n": 5}
    last5 = {"tipo": "ultimos_dias_uteis", "n": 5}
    # outubro/2026: 1º é quinta; 12 é feriado. 5º dia útil = 07/10; os 5 últimos = 26 a 30
    assert modos.rule_matches(first5, datetime(2026, 10, 1, 9), hol)
    assert modos.rule_matches(first5, datetime(2026, 10, 3, 9), hol)  # sábado no meio conta
    assert modos.rule_matches(first5, datetime(2026, 10, 7, 9), hol)
    assert not modos.rule_matches(first5, datetime(2026, 10, 8, 9), hol)
    assert modos.rule_matches(last5, datetime(2026, 10, 26, 9), hol) and modos.rule_matches(last5, datetime(2026, 10, 31, 9), hol)
    assert not modos.rule_matches(last5, datetime(2026, 10, 23, 9), hol)
    # janeiro/2027: 1º é feriado (sexta); o 1º dia útil é 04/01 e o 5º, 08/01
    assert modos.rule_matches(first5, datetime(2027, 1, 8, 9), hol) and not modos.rule_matches(first5, datetime(2027, 1, 11, 9), hol)
    assert not modos.rule_matches(first5, datetime(2027, 1, 8, 9), NO_HOLIDAYS)  # sem o feriado, o 5º seria 07/01
    week = {"tipo": "dias_da_semana", "dias": [0, 1, 2, 3, 4], "janelas": [["14:40", "15:10"], ["16:40", "17:10"]]}
    assert modos.rule_matches(week, datetime(2026, 10, 19, 14, 50), hol)
    assert not modos.rule_matches(week, datetime(2026, 10, 19, 15, 10), hol)
    assert not modos.rule_matches(week, datetime(2026, 10, 24, 14, 50), hol)  # sábado
    assert modos.rule_matches({"tipo": "dias_do_mes", "de": 10, "ate": 15}, datetime(2026, 10, 12, 9), hol)
    assert modos.rule_label(week) == "seg a sex, das 14:40 às 15:10 e das 16:40 às 17:10"
    with pytest.raises(ValidationError):
        modos.parse_rule("dias_da_semana", days=[])
    with pytest.raises(ValidationError):
        modos.parse_rule("dias_da_semana", days=["0"], windows="15:00-14:00")
    assert modos.parse_rule("primeiros_dias_uteis", n="3") == {"tipo": "primeiros_dias_uteis", "n": 3}


def test_automatic_modes_and_holiday(env):
    db, *_ = env
    assert modos.current(db, at(12)).mode.is_default  # 19/10: nenhuma regra vale
    now = modos.current(db, at(12, day=27))
    assert now.mode.builtin == "fim-mes" and now.how == "automatico"
    assert modos.current(db, at(12, day=2)).mode.builtin == "inicio-mes"
    assert modos.current(db, at(12, day=8)).mode.is_default
    bianca = get_person(db, 2)
    add_local_holiday(db, at(9), bianca, date(2026, 10, 5), "Feriado da cidade")  # empurra o 5º dia útil para 08/10
    assert modos.current(db, at(12, day=8)).mode.builtin == "inicio-mes"


def test_manual_wins_and_expires(env):
    db, clock, ck, cb, ca, kayo, bianca, ana = env
    visita = by_key(db)["visita"]
    r = ca.post("/tv-da-sala/modo", data={"modo": str(visita.id), "ate": "60"}, follow_redirects=False)
    assert r.status_code == 303  # qualquer pessoa com PIN troca o modo
    now = modos.current(db, at(12, 30))
    assert now.mode.id == visita.id and now.how == "manual" and now.by == ana.id
    assert modos.current(db, at(13, 1)).mode.is_default  # passou 1 hora: volta ao automático
    modos.choose(db, at(12), ana, visita.id, "dia")
    assert modos.current(db, at(12, day=27)).mode.builtin == "fim-mes"  # o "até o fim do dia" acabou
    modos.choose(db, at(12), ana, visita.id, "sempre")
    assert modos.current(db, at(12, day=27)).mode.id == visita.id
    ca.post("/tv-da-sala/modo", data={"modo": "automatico"})
    assert modos.current(db, at(12)).mode.is_default
    hist = ck.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "pôs a TV da sala no modo “Visita”" in hist and "voltar ao modo automático" in hist
    assert "Modo da TV" in ca.get("/tv-da-sala").text


def test_priority_breaks_ties(env):
    db, _, _, _, _, kayo, *_ = env
    keys = by_key(db)
    modos.set_rule_on(db, at(9), kayo, keys["sabado"].id, True)
    saturday_end = at(10, day=31)  # sábado, 31/10: Fim de mês e Sábado valem
    assert modos.current(db, saturday_end).mode.builtin == "fim-mes"
    for _ in range(len(modos.BUILTINS)):
        modos.move_mode(db, at(9), kayo, keys["sabado"].id, -1)
    assert modos.current(db, saturday_end).mode.builtin == "sabado"


def test_mode_drives_rotation_and_falls_back_to_board(env):
    db, _, _, _, _, kayo, *_ = env
    keys = by_key(db)
    create_demand(db, at(8), kayo.id, title="Prazo", owner_id=kayo.id, due=date(2026, 10, 20))
    assert ids(db, at(12)) == ["quadro", "prazos"]
    assert ids(db, at(12, day=2))[:1] == ["quadro"]  # Início de mês
    rot = rotation(db, at(12), keys["apresentacao"])  # só painéis, sem planilhas: cai no Quadro
    assert [s["id"] for s in rot["screens"]] == ["quadro"]
    reuniao = rotation(db, at(12), keys["reuniao"])
    assert all(s["seconds"] == 60 for s in reuniao["screens"])


def test_hide_titles_never_sends_titles(env):
    db, clock, ck, *_, kayo, _, ana = env
    create_demand(db, at(8), kayo.id, title="Comissões da pasta B", owner_id=ana.id, due=date(2026, 10, 20),
                  requested_by="Gerente")
    modos.choose(db, at(12), kayo, by_key(db)["visita"].id, "dia")
    tv = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE).get("/api/tv")
    body = tv.text
    assert "Comissões" not in body and "Gerente" not in body
    data = tv.json()
    assert data["modo"]["nome"] == "Visita" and not data["modo"]["padrao"]
    assert data["columns"]["todo"][0]["title"] == "Demanda" and data["columns"]["todo"][0]["initials"] == ana.initials


def test_silent_mode_marks_alerts(env):
    db, *_, kayo, _, _ = env
    from hub.rotinas import start_test_alert
    start_test_alert(db, at(12), kayo)
    modos.choose(db, at(12), kayo, by_key(db)["reuniao"].id, "dia")
    data = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE).get("/api/tv").json()
    assert data["avisos"] and all(a["mudo"] for a in data["avisos"])


def test_preview_does_not_touch_the_room(env):
    db, _, ck, *_ = env
    so_quadro = by_key(db)["so-quadro"]
    data = ck.get(f"/api/tv?espiar=1&modo={so_quadro.id}").json()
    assert data["modo"] == {"nome": "Só o quadro", "padrao": False, "previa": True}
    assert modos.current(db, at(12)).mode.is_default
    assert ck.get(f"/api/tv?modo={so_quadro.id}").json()["modo"]["padrao"]  # sem espiar, vale a sala


def test_only_manager_and_admins_edit_modes(env):
    db, _, ck, cb, ca, *_ = env
    assert ca.get("/modos").status_code == 200  # todos veem e pré-visualizam
    assert ca.get("/modos/novo").status_code == 403
    assert ca.post("/modos", data={"name": "X"}).status_code == 403
    data = {"name": "Fechamento da pasta B", "tela": ["metas-dia", "quadro"], "ligada": ["metas-dia", "quadro"],
            "segundos_metas-dia": "30", "segundos_quadro": "20", "page_seconds": "8", "sound": "1",
            "tipo": "dias_do_mes", "de": "28", "ate": "31", "rule_on": "1"}
    r = cb.post("/modos", data=data, follow_redirects=False)  # a gestora cria
    assert r.status_code == 303
    m = next(m for m in modos.list_modes(db) if m.name == "Fechamento da pasta B")
    assert [(s.id, s.seconds) for s in m.screens if s.enabled] == [("metas-dia", 30), ("quadro", 20)]
    assert m.rule == {"tipo": "dias_do_mes", "de": 28, "ate": 31} and m.rule_on and m.page_seconds == 8
    assert cb.post("/modos", data={**data, "name": "fechamento da pasta b"}).status_code == 422  # nome repetido
    assert cb.post("/modos", data={**data, "name": "Outro", "ligada": []}).status_code == 422
    copy = cb.post(f"/modos/{m.id}/duplicar", follow_redirects=False)
    assert copy.status_code == 303
    assert cb.post(f"/modos/{by_key(db)['visita'].id}/excluir").status_code == 422  # pronto: não apaga
    assert cb.post(f"/modos/{m.id}/excluir", follow_redirects=False).status_code == 303
    assert "Fechamento da pasta B (cópia)" in ck.get("/modos").text
    hist = ck.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "criou o modo da TV “Fechamento da pasta B”" in hist and "apagou o modo da TV" in hist


def test_new_screen_of_a_future_phase_joins_every_mode(env, monkeypatch):
    db, *_ = env
    from hub import telas
    future = telas.Screen("nova", "Tela nova", 12, lambda db, now: {"x": 1})
    monkeypatch.setattr(telas, "SCREENS", [*telas.SCREENS, future])
    padrao = next(s for s in modos.default_mode(db).screens if s.id == "nova")
    inicio = next(s for m in modos.list_modes(db) if m.builtin == "inicio-mes" for s in m.screens if s.id == "nova")
    assert padrao.enabled and not inicio.enabled and padrao.seconds == 12
