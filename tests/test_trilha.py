"""Fase 20: a trilha do dia de cada analista (blocos de horário, luz acesa ou negativa) e a tela da TV."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import trilha
from hub.access import set_access
from hub.calendario import add_absence, add_local_holiday
from hub.demands import move_demand
from hub.modos import mask_titles
from hub.people import ValidationError, add_person, get_person
from hub.rotinas import save_routine
from hub.telas import rotation
from hub.trilha import (copy_trail, counts, create_suggested, list_blocks, mark, my_trail, remove_block, save_block,
                        trails_on, tv_trilhas, week_summary)
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    ana = add_person(db, at(7), None, "Ana Souza")
    caio = add_person(db, at(7), None, "Caio Lopes")
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url=BASE), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", False)
    return db, *(get_person(db, p.id) for p in (kayo, bianca, ana, caio))


def bloco(db, actor, person, start="09:00", end="10:00", title="PHD", days=(0, 1, 2, 3, 4), **kw):
    return save_block(db, at(7), actor, None, person_id=person.id, weekdays=list(days), starts_at=start, ends_at=end,
                      title=title, **kw)


def status(db, person, now):
    return {s.block.title: s.status for s in my_trail(db, person.id, now)}


# ---------- montar ----------

def test_who_can_build_a_trail(env):
    db, kayo, bianca, ana, caio = env
    bloco(db, ana, ana)  # a própria pessoa
    bloco(db, bianca, ana, "10:00", "11:00", "Devolutivas")  # o gestor
    bloco(db, kayo, ana, "11:00", "12:00", "Insights")  # o administrador
    with pytest.raises(PermissionError):
        bloco(db, caio, ana, "13:00", "14:00", "Outro")  # um colega, não
    assert [b.title for b in list_blocks(db, ana.id)] == ["PHD", "Devolutivas", "Insights"]


def test_validations_and_overlap(env):
    db, kayo, bianca, ana, caio = env
    bloco(db, ana, ana, "09:00", "10:00", days=(0, 2))
    with pytest.raises(ValidationError, match="cruza com “PHD”"):
        bloco(db, ana, ana, "09:30", "10:30", "Outro", days=(2,))
    bloco(db, ana, ana, "09:30", "10:30", "Na terça", days=(1,))  # outro dia da semana: pode
    bloco(db, ana, ana, "10:00", "10:30", "Logo depois", days=(0,))  # encostado: pode
    with pytest.raises(ValidationError, match="depois do início"):
        bloco(db, ana, ana, "11:00", "11:00", "Zero")
    with pytest.raises(ValidationError, match="Horário inválido"):
        bloco(db, ana, ana, "9h", "10:00", "Errado")
    with pytest.raises(ValidationError, match="pelo menos um dia"):
        bloco(db, ana, ana, "12:00", "13:00", "Sem dia", days=())
    with pytest.raises(ValidationError, match="ícone"):
        bloco(db, ana, ana, "12:00", "13:00", "Ícone", icon="nada")
    b = bloco(db, ana, ana, "12:00", "13:00", "Cor do ícone", icon="rota")
    assert b.color == trilha.ICONS["rota"][1]  # sem cor escolhida, fica a do ícone


def test_suggested_and_copy_only_into_an_empty_trail(env):
    db, kayo, bianca, ana, caio = env
    assert create_suggested(db, at(7), bianca, ana.id) == len(trilha.SUGGESTED)
    with pytest.raises(ValidationError, match="trilha vazia"):
        create_suggested(db, at(7), bianca, ana.id)
    monday = [s.block.title for s in my_trail(db, ana.id, at(7))]
    assert monday[:3] == ["Acompanhamento da pasta", "Black-list", "PHD"] and "MSL" not in monday
    tuesday = [s.block.title for s in my_trail(db, ana.id, at(7, day=20))]
    assert "MSL" in tuesday and "Black-list" not in tuesday
    assert copy_trail(db, at(7), caio, ana.id, caio.id) == len(trilha.SUGGESTED)
    with pytest.raises(ValidationError, match="já tem blocos"):
        copy_trail(db, at(7), caio, ana.id, caio.id)
    remove_block(db, at(8), caio, list_blocks(db, caio.id)[0].id)
    assert len(list_blocks(db, caio.id)) == len(trilha.SUGGESTED) - 1


# ---------- o dia ----------

def test_statuses_through_the_day(env):
    db, kayo, bianca, ana, caio = env
    phd = bloco(db, ana, ana, "09:00", "10:00", "PHD")
    dev = bloco(db, ana, ana, "10:00", "11:00", "Devolutivas")
    bloco(db, ana, ana, "11:00", "12:00", "Insights")
    bloco(db, ana, ana, "12:00", "13:00", "Intervalo", icon="pausa", kind="pausa")
    assert status(db, ana, at(8)) == {"PHD": "futuro", "Devolutivas": "futuro", "Insights": "futuro",
                                      "Intervalo": "pausa"}
    mark(db, at(9, 40), ana, phd.id)
    assert status(db, ana, at(10, 30))["PHD"] == "feito" and status(db, ana, at(10, 30))["Devolutivas"] == "agora"
    mark(db, at(11, 15), bianca, dev.id)  # o gestor marca, depois do horário: âmbar
    st = status(db, ana, at(12, 30))
    assert (st["Devolutivas"], st["Insights"]) == ("feito_atrasado", "nao_feito")
    c = counts(my_trail(db, ana.id, at(12, 30)))
    assert (c["feitos"], c["no_horario"], c["atrasados"], c["perdidos"], c["total"]) == (2, 1, 1, 1, 3)
    mark(db, at(12, 40), ana, phd.id, False)  # desfazer
    assert status(db, ana, at(12, 40))["PHD"] == "nao_feito"


def test_mark_only_today_and_not_the_break(env):
    db, kayo, bianca, ana, caio = env
    b = bloco(db, ana, ana, days=(1,))  # só terça
    pausa = bloco(db, ana, ana, "12:00", "13:00", "Intervalo", icon="pausa", kind="pausa")
    with pytest.raises(ValidationError, match="não é de hoje"):
        mark(db, at(9), ana, b.id)  # hoje é segunda
    with pytest.raises(ValidationError, match="intervalo"):
        mark(db, at(12, 30), ana, pausa.id)
    with pytest.raises(PermissionError):
        mark(db, at(9, day=20), caio, b.id)


def test_linked_routine_lights_the_block(env):
    db, kayo, bianca, ana, caio = env
    r = save_routine(db, at(7), kayo, None, name="Transferência de pedidos", weekdays=[0, 1, 2, 3, 4],
                     starts_at="15:00", deadline=None, owner_id=ana.id, folders=[], waits_for=[])
    bloco(db, ana, ana, "15:00", "15:30", "Transferência", routine_id=r.id)
    move_demand(db, at(15, 10), ana.id, f"rotina-{r.id}-2026-10-19", "done")
    [step] = my_trail(db, ana.id, at(15, 20))
    assert step.status == "feito" and step.auto


def test_holiday_absence_and_blocks_created_later(env):
    db, kayo, bianca, ana, caio = env
    bloco(db, ana, ana)
    add_local_holiday(db, at(7), kayo, date(2026, 10, 21), "Aniversário da cidade")
    assert trails_on(db, date(2026, 10, 21), at(12, day=21)) == {}
    add_absence(db, at(7), ana, ana.id, date(2026, 10, 20), None, "Folga")
    assert my_trail(db, ana.id, at(12, day=20)) == []
    # o bloco foi criado no dia 19: não cobra os dias de antes
    assert trails_on(db, date(2026, 10, 16), at(23, day=16)) == {}


def test_week_summary(env):
    db, kayo, bianca, ana, caio = env
    b = bloco(db, ana, ana)
    bloco(db, caio, caio)
    mark(db, at(9, 30), ana, b.id)  # segunda, no horário
    mark(db, at(10, 30, day=20), ana, b.id)  # terça, depois
    add_absence(db, at(7), caio, caio.id, date(2026, 10, 20), None, "")  # Caio de folga na terça
    rows = {x["pessoa"].name: x for x in week_summary(db, at(12, day=21))}
    assert {k: rows["Ana Souza"][k] for k in ("no_horario", "atrasados", "perdidos", "total", "pct")} == \
        {"no_horario": 1, "atrasados": 1, "perdidos": 1, "total": 3, "pct": 33}
    assert rows["Caio Lopes"]["total"] == 2  # segunda e quarta; a terça de folga não conta


# ---------- TV ----------

def test_tv_screen(env):
    db, kayo, bianca, ana, caio = env
    assert tv_trilhas(db, at(12)) is None
    assert "trilhas" not in [s["id"] for s in rotation(db, at(12))["screens"]]
    create_suggested(db, at(7), bianca, ana.id)
    create_suggested(db, at(7), bianca, caio.id)
    add_absence(db, at(7), caio, caio.id, date(2026, 10, 19), None, "")
    data = tv_trilhas(db, at(10, 30))
    assert (data["inicio"], data["fim"], data["agora"]) == ("08:00", "18:00", "10:30")
    assert data["agora_pct"] == 25 and data["horas"][0] == {"hora": "08:00", "pos": 0}
    [linha] = data["linhas"]  # Caio está ausente
    assert linha["nome"] == "Ana Souza" and linha["blocos"][0]["pos"] == 0 and linha["blocos"][0]["larg"] == 10
    assert linha["foco"]["tipo"] == "agora" and linha["foco"]["titulo"] == "Devolutivas"
    assert linha["foco"]["detalhes"] == ["Retornos pendentes", "Atendimento extra", "Reorganização de demandas"]
    assert tv_trilhas(db, at(12))["linhas"][0]["foco"]["tipo"] == "pausa"
    assert tv_trilhas(db, at(18, 30))["linhas"][0]["foco"]["tipo"] == "fim"
    assert "trilhas" in [s["id"] for s in rotation(db, at(10, 30))["screens"]]


def test_visit_mode_hides_the_texts(env):
    db, kayo, bianca, ana, caio = env
    create_suggested(db, at(7), bianca, ana.id)
    payload = {"columns": {"todo": [], "doing": [], "done": []}, **rotation(db, at(10, 30))}
    mask_titles(payload)
    s = next(s for s in payload["screens"] if s["id"] == "trilhas")
    [linha] = s["data"]["linhas"]
    assert all(b["titulo"] == "" and b["icone"] for b in linha["blocos"])
    assert linha["foco"]["titulo"] == "" and linha["foco"]["detalhes"] == []


# ---------- app ----------

def test_web_pages_and_marking(env):
    db, kayo, bianca, ana, caio = env
    app = create_app(db, clock=lambda: at(9, 30))
    ca, cc = TestClient(app, base_url=BASE), TestClient(app, base_url=BASE)
    login(ca, ana)
    login(cc, caio)
    assert "Criar a trilha do modelo" in ca.get("/trilha/montar").text
    r = ca.post("/trilha/montar/modelo", data={"pessoa": str(ana.id)}, follow_redirects=False)
    assert r.status_code == 303 and "pessoa=" in r.headers["location"]
    assert ca.post("/trilha/montar", data={"pessoa": str(ana.id), "weekdays": ["0"], "starts_at": "09:10",
                                            "ends_at": "09:20", "title": "Cruzando", "icon": "lista",
                                            "kind": "tarefa"}).status_code == 422
    phd = next(b for b in list_blocks(db, ana.id) if b.title == "PHD")
    # o Quadro mostra a faixa "Minha trilha de hoje"
    home = ca.get("/").text
    assert "Minha trilha de hoje" in home and "PHD" in home
    r = ca.post(f"/trilha/{phd.id}/feito", data={"feito": "1", "volta": "/"}, follow_redirects=False)
    assert r.headers["location"] == "/#minha-trilha"
    assert next(s for s in my_trail(db, ana.id, at(9, 40)) if s.block.id == phd.id).status == "feito"
    assert cc.post(f"/trilha/{phd.id}/feito", data={"feito": "0"}).status_code == 403  # trilha de outro
    assert cc.get(f"/trilha/montar?pessoa={ana.id}").status_code == 403
    page = cc.get("/trilha").text
    assert "Ana Souza" in page and "Últimos 5 dias úteis".upper() not in page  # o resumo do Caio fica vazio
    r = ca.post(f"/trilha/{phd.id}/feito", data={"feito": "1", "volta": "https://fora"}, follow_redirects=False)
    assert r.headers["location"] == "/trilha"  # volta só para páginas do Hub
    tirar = ca.post(f"/trilha/montar/{phd.id}/tirar", follow_redirects=False)
    assert tirar.status_code == 303 and phd.id not in [b.id for b in list_blocks(db, ana.id)]


def test_database_from_1_11_gains_the_tables(tmp_path):
    import sqlite3
    from hub.db import Database
    path = tmp_path / "hub.db"
    d = Database(path)
    d.init()
    p = add_person(d, at(7), None, "Kayo")
    with sqlite3.connect(path) as conn:
        for table in ("trail_marks", "trail_blocks"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("PRAGMA user_version = 13")
    d.init()
    assert list_blocks(d, p.id) == [] and (tmp_path / "copias").is_dir()
