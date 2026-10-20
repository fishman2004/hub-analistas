"""Fase 8: prioridades do início do mês (lista do mês, quem fez, a página e a tela da TV)."""

import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub.access import create_pin
from hub.db import SCHEMA_VERSION, Database, events
from hub.people import ValidationError, add_person, get_person
from hub.prioridades import (add_priority, create_default_list, is_late, list_month, mark_done, month_label,
                             month_of, parse_due_day, remove_priority, tv_prioridades, undo_done)
from hub.telas import rotation
from hub.web.app import create_app
from test_access import make_v1_db

BASE = "http://hub-sala:8800"
OUT = "2026-10"
NOV_1 = datetime(2026, 11, 1, 0, 0)


@pytest.fixture
def team(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bia = add_person(db, at(7), None, "Bia")
    caio = add_person(db, at(7), None, "Caio", color="#9AD48F")
    for p in (kayo, bia, caio):
        create_pin(db, at(7), p.id, "1234", "1234")  # o primeiro (Kayo) vira administrador
    return db, get_person(db, kayo.id), get_person(db, bia.id), get_person(db, caio.id)


def titles(db, month=OUT):
    return [p.title for p in list_month(db, month)]


def kinds(db):
    return [e["kind"] for e in reversed(events(db, at(0).date(), NOV_1.date()))]


# ---------- a lista do mês ----------

def test_add_items_to_the_current_month(team):
    db, kayo, bia, _ = team
    a = add_priority(db, at(8), bia, "  Meta   do mês ")
    b = add_priority(db, at(9), kayo, "Novos acompanhamentos", folder="C", due_day=10)
    assert (a.month, a.title, a.folder, a.due_day, a.position, a.created_by, a.created_at) == (
        OUT, "Meta do mês", None, None, 1, bia.id, at(8))
    assert (b.folder, b.due_day, b.position, b.done) == ("C", 10, 2, False)
    assert titles(db) == ["Meta do mês", "Novos acompanhamentos"]
    for title, folder, due, message in [("", None, None, "Informe o item"), ("x" * 121, None, None, "muito longo"),
                                        ("Outro", "Z", None, "Pasta inválida"), ("meta do MÊS", None, None, "já está"),
                                        ("Outro", None, 0, "de 1 a 31"), ("Outro", None, 32, "de 1 a 31")]:
        with pytest.raises(ValidationError, match=message):
            add_priority(db, at(10), kayo, title, folder=folder, due_day=due)
    add_priority(db, at(10), kayo, "Novos acompanhamentos", folder="D")  # mesma frase, outra pasta: vale
    assert kinds(db).count("prioridade_criada") == 3
    with pytest.raises(ValidationError, match="de 1 a 30"):  # novembro tem 30 dias
        add_priority(db, NOV_1, kayo, "Outro", due_day=31)


def test_due_day_from_the_form():
    assert parse_due_day("") is None and parse_due_day(" 10 ") == 10
    for bad in ("dez", "10/11", "-1"):
        with pytest.raises(ValidationError, match="dia do mês"):
            parse_due_day(bad)


def test_late_after_the_due_day_while_open(team):
    db, kayo, bia, _ = team
    item = add_priority(db, at(8, day=1), kayo, "Entregar as comissões", due_day=10)
    free = add_priority(db, at(8, day=1), kayo, "Sem prazo")
    assert not is_late(item, at(18, day=10).date())  # "até dia 10" ainda vale no dia 10
    assert is_late(item, at(8, day=11).date()) and not is_late(free, at(8, day=31).date())
    assert is_late(item, NOV_1.date())  # o mês acabou com ela em aberto
    done = mark_done(db, at(9, day=12), bia, item.id)
    assert not is_late(done, at(9, day=12).date())  # feita (mesmo depois do prazo) não está atrasada


def test_done_and_undo_record_who_and_when(team):
    db, kayo, bia, caio = team
    item = add_priority(db, at(8), kayo, "Fechamentos")
    done = mark_done(db, at(10, 30), bia, item.id)
    assert (done.done, done.done_by, done.done_at) == (True, bia.id, at(10, 30))
    # outro PC marca de novo ao mesmo tempo: continua valendo quem fez primeiro, sem linha nova no histórico
    again = mark_done(db, at(10, 31), caio, item.id)
    assert (again.done_by, again.done_at) == (bia.id, at(10, 30))
    undone = undo_done(db, at(11), caio, item.id)  # qualquer pessoa desfaz
    assert (undone.done, undone.done_by, undone.done_at) == (False, None, None)
    assert kinds(db)[-2:] == ["prioridade_feita", "prioridade_desfeita"]
    who = [(e["kind"], e["actor_id"]) for e in events(db, at(0).date(), at(0).date()) if e["kind"].startswith("prio")]
    assert ("prioridade_feita", bia.id) in who and ("prioridade_desfeita", caio.id) in who


def test_only_the_creator_or_an_admin_removes(team):
    db, kayo, bia, caio = team
    mine = add_priority(db, at(8), bia, "Apuração de campanhas")
    other = add_priority(db, at(8), bia, "Fechamentos")
    with pytest.raises(PermissionError):
        remove_priority(db, at(9), caio, mine.id)
    remove_priority(db, at(9), bia, mine.id)       # quem criou
    remove_priority(db, at(9), kayo, other.id)     # administrador
    assert titles(db) == []
    with pytest.raises(ValidationError):
        remove_priority(db, at(9), kayo, mine.id)  # já removido
    with pytest.raises(ValidationError):
        mark_done(db, at(9), kayo, mine.id)
    with db.connect() as conn:  # remoção só marca: o item continua guardado
        assert conn.execute("SELECT COUNT(*) FROM priorities WHERE deleted = 1").fetchone()[0] == 2


def test_month_boundaries(team):
    db, kayo, bia, _ = team
    assert month_of(datetime(2026, 10, 31, 23, 59)) == OUT and month_of(NOV_1) == "2026-11"
    assert month_label(OUT) == "outubro de 2026" and month_label("2027-01") == "janeiro de 2027"
    old = add_priority(db, datetime(2026, 10, 31, 23, 59), kayo, "Fechamentos")
    assert tv_prioridades(db, datetime(2026, 10, 31, 23, 59)) is not None
    # virou o mês: a lista nova começa vazia, a TV não mostra a do mês passado e ela fica só para consulta
    assert list_month(db, "2026-11") == [] and tv_prioridades(db, NOV_1) is None
    for action in (mark_done, undo_done, remove_priority):
        with pytest.raises(ValidationError, match="mês atual"):
            action(db, NOV_1, kayo, old.id)
    new = add_priority(db, NOV_1, bia, "Fechamentos")  # o mesmo item no mês novo
    assert (new.month, new.position) == ("2026-11", 1) and titles(db) == ["Fechamentos"]


def test_default_list_is_created_once(team):
    db, kayo, bia, _ = team
    created = create_default_list(db, at(8), bia)
    expected = ["Lançar a meta no sistema", "Confirmar o recebimento da meta com o gerente",
                "Entregar as comissões", "Entregar as campanhas"]
    assert [p.title for p in created] == expected == titles(db)
    assert [(p.folder, p.due_day) for p in created] == [(None, None), (None, None), (None, 10), (None, 15)]
    assert [p.position for p in created] == [1, 2, 3, 4]
    assert {p.created_by for p in created} == {bia.id}
    assert create_default_list(db, at(9), kayo) == []  # de novo (ou duplo clique): nada muda
    assert len(titles(db)) == len(expected)
    assert kinds(db).count("prioridades_padrao") == 1
    # com qualquer item no mês, a lista padrão não entra
    assert create_default_list(db, NOV_1, kayo) != []
    add_priority(db, datetime(2026, 12, 1, 8), kayo, "Só esta")
    assert create_default_list(db, datetime(2026, 12, 1, 9), kayo) == []


# ---------- TV ----------

def ids(db, now=at(12)):
    return [s["id"] for s in rotation(db, now)["screens"]]


def test_tv_screen_leaves_when_empty_or_all_done(team):
    db, kayo, bia, _ = team
    assert tv_prioridades(db, at(12)) is None and "prioridades" not in ids(db)
    a = add_priority(db, at(8), kayo, "Meta do mês")
    b = add_priority(db, at(8), kayo, "Fechamentos")
    assert "prioridades" in ids(db)
    mark_done(db, at(9), bia, a.id)
    assert "prioridades" in ids(db)
    mark_done(db, at(10), bia, b.id)
    assert tv_prioridades(db, at(12)) is None and "prioridades" not in ids(db)  # tudo feito: sai sozinha
    undo_done(db, at(11), kayo, b.id)
    assert "prioridades" in ids(db)
    remove_priority(db, at(11), kayo, b.id)  # o que sobrou está feito
    assert "prioridades" not in ids(db)


def test_tv_payload_has_only_what_the_screen_draws(team):
    db, kayo, bia, caio = team
    a = add_priority(db, at(8), kayo, "Lançar a meta no sistema")
    add_priority(db, at(8), kayo, "Novos acompanhamentos", folder="B", due_day=25)
    c = add_priority(db, at(8), kayo, "Entregar as comissões", due_day=10)
    add_priority(db, at(8), kayo, "Entregar as campanhas", due_day=15)
    mark_done(db, at(9), caio, a.id)
    mark_done(db, at(9), bia, c.id)  # dia 19: comissões feitas depois do prazo; campanhas atrasadas
    data = tv_prioridades(db, at(12))
    assert set(data) == {"month", "done_count", "total", "late_count", "items"}
    assert (data["month"], data["done_count"], data["total"], data["late_count"]) == ("outubro de 2026", 2, 4, 1)
    # atrasadas, depois as outras em aberto e por fim as feitas, com as iniciais e a cor de quem fez
    assert data["items"] == [
        {"title": "Entregar as campanhas", "folder": None, "due_day": 15, "late": True, "done": False,
         "initials": None, "color": None},
        {"title": "Novos acompanhamentos", "folder": "B", "due_day": 25, "late": False, "done": False,
         "initials": None, "color": None},
        {"title": "Lançar a meta no sistema", "folder": None, "due_day": None, "late": False, "done": True,
         "initials": "C", "color": "#9AD48F"},
        {"title": "Entregar as comissões", "folder": None, "due_day": 10, "late": False, "done": True,
         "initials": bia.initials, "color": bia.color},
    ]


def test_api_tv_carries_the_screen_without_names_or_times(team):
    db, kayo, bia, caio = team
    a = add_priority(db, at(8), caio, "Fechamentos")
    add_priority(db, at(8), caio, "Meta do mês")
    mark_done(db, at(9, 47), bia, a.id)
    body = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE).get("/api/tv").json()
    screen = next(s for s in body["screens"] if s["id"] == "prioridades")
    assert screen["label"] == "Prioridades do mês" and screen["seconds"] == 15
    text = str(screen["data"])
    assert "Bia" not in text and "Caio" not in text and "09:47" not in text and "T09" not in text


# ---------- página /prioridades ----------

@pytest.fixture
def web(team):
    db, kayo, bia, caio = team
    clock = {"now": at(12)}
    app = create_app(db, clock=lambda: clock["now"])

    def login(person):
        c = TestClient(app, base_url=BASE)
        c.post(f"/entrar/{person.id}", data={"pin": "1234"})
        return c

    return db, kayo, bia, caio, clock, login


def test_page_flow(web):
    db, kayo, bia, caio, _, login = web
    assert TestClient(create_app(db), base_url=BASE).get("/prioridades", follow_redirects=False).status_code == 303
    c = login(bia)
    page = c.get("/prioridades").text
    assert 'href="/prioridades"' in page and "Criar lista padrão do mês" in page and "outubro de 2026" in page
    assert c.post("/prioridades/padrao", follow_redirects=False).status_code == 303
    page = c.get("/prioridades").text
    assert "Confirmar o recebimento da meta com o gerente" in page and "0 de 4 feitas" in page
    assert "Criar lista padrão do mês" not in page  # o mês já tem lista
    # dia 19: "Entregar as comissões" (até dia 10) e "Entregar as campanhas" (até dia 15) estão atrasadas
    assert page.count("atrasada · até dia") == 2 and "2 atrasadas" in page
    r = c.post("/prioridades", data={"title": "Conferir bonificações", "folder": "E", "prazo": "25"},
               follow_redirects=False)
    assert r.status_code == 303 and list_month(db, OUT)[-1].title == "Conferir bonificações"
    assert "até dia 25" in c.get("/prioridades").text
    r = c.post("/prioridades", data={"title": "Outro", "folder": "", "prazo": "40"})
    assert r.status_code == 422 and "de 1 a 31" in r.text and 'value="Outro"' in r.text  # mantém o que digitou
    r = c.post("/prioridades", data={"title": "", "folder": "", "prazo": ""})
    assert r.status_code == 422 and "Informe o item" in r.text
    first = list_month(db, OUT)[0]
    c.post(f"/prioridades/{first.id}/feita")
    page = c.get("/prioridades").text
    assert "1 de 5 feitas" in page and "feita por Bia em 19/10 às 12:00" in page and "Desfazer" in page
    c.post(f"/prioridades/{first.id}/desfazer")
    assert not list_month(db, OUT)[0].done
    history = c.get("/historico?de=2026-10-19&ate=2026-10-19").text
    for line in ("Bia criou a lista padrão de prioridades de outubro de 2026",
                 "Bia acrescentou “Conferir bonificações” às prioridades do mês",
                 "Bia marcou como feita a prioridade “Lançar a meta no sistema”",
                 "Bia desmarcou a prioridade “Lançar a meta no sistema”"):
        assert line in history


def test_remove_button_and_permission(web):
    db, kayo, bia, caio, _, login = web
    item = add_priority(db, at(8), bia, "Apuração de campanhas")
    other = login(caio)
    assert f'action="/prioridades/{item.id}/remover"' not in other.get("/prioridades").text
    assert other.post(f"/prioridades/{item.id}/remover").status_code == 403
    assert other.post(f"/prioridades/{item.id}/feita", follow_redirects=False).status_code == 303  # marcar, pode
    admin = login(kayo)
    assert f'action="/prioridades/{item.id}/remover"' in admin.get("/prioridades").text
    admin.post(f"/prioridades/{item.id}/remover")
    assert titles(db) == []
    assert "Kayo removeu “Apuração de campanhas” das prioridades do mês" in admin.get(
        "/historico?de=2026-10-19&ate=2026-10-19").text


def test_previous_months_are_read_only(web):
    db, kayo, bia, caio, clock, login = web
    item = add_priority(db, at(8), bia, "Fechamentos")
    mark_done(db, at(9), caio, item.id)
    clock["now"] = datetime(2026, 11, 3, 9)
    c = login(bia)
    page = c.get("/prioridades").text
    assert "novembro de 2026" in page and "Criar lista padrão do mês" in page
    assert 'href="/prioridades?mes=2026-10"' in page  # os meses anteriores com lista
    old = c.get("/prioridades?mes=2026-10").text
    assert "Fechamentos" in old and "feita por Caio" in old and "1 de 1 feitas" in old
    assert "<form" not in old.split("<main>")[1].split("</main>")[0]  # só consulta: nenhum botão
    r = c.post(f"/prioridades/{item.id}/desfazer")
    assert r.status_code == 422 and "mês atual" in r.text
    assert list_month(db, OUT)[0].done
    assert c.get("/prioridades?mes=bobagem").status_code == 200  # mês inválido: volta para o atual


# ---------- migração ----------

def test_v1_database_gets_the_priorities_table(tmp_path):
    path = tmp_path / "hub.db"
    make_v1_db(path)
    db = Database(path)
    db.init()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 6
        assert conn.execute("SELECT title FROM demands").fetchone()[0] == "Relatório Aurora"
    kayo = get_person(db, 1)
    item = add_priority(db, at(8), kayo, "Meta do mês")
    assert list_month(db, OUT) == [item]
    db.init()  # abrir de novo não migra outra vez
    assert len(list((tmp_path / "copias").glob("*.db"))) == 1
    old = sqlite3.connect(next((tmp_path / "copias").glob("*.db")))
    assert old.execute("SELECT name FROM sqlite_master WHERE name = 'priorities'").fetchone() is None
    old.close()
