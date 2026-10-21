"""Fase 16: pastas de cada pessoa, prioridades do mês marcadas por pasta e o papel Assistente."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import horas
from hub.access import create_pin, set_access
from hub.db import SCHEMA_VERSION, events
from hub.pastas import folders_by_person, folders_of, owners, set_folders
from hub.people import ValidationError, add_person, get_person
from hub.prioridades import (GOAL_STEPS, add_priority, by_folder, create_default_list, list_month, mark_done,
                             parse_steps, tv_prioridades, undo_done)
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
OUT = "2026-10"


@pytest.fixture
def team(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bia = add_person(db, at(7), None, "Bia")
    caio = add_person(db, at(7), None, "Caio", color="#9AD48F")
    duda = add_person(db, at(7), None, "Duda")
    gil = add_person(db, at(7), None, "Gil")
    for p in (kayo, bia, caio, duda, gil):
        create_pin(db, at(7), p.id, "1234", "1234")  # o primeiro (Kayo) vira administrador
    kayo = get_person(db, kayo.id)
    set_access(db, at(7), kayo, duda.id, "assistente", False)
    set_access(db, at(7), kayo, gil.id, "gestor", False)
    set_folders(db, at(7), kayo, bia.id, ["C", "B"])
    set_folders(db, at(7), kayo, caio.id, ["D"])
    return db, kayo, get_person(db, bia.id), get_person(db, caio.id), get_person(db, duda.id), get_person(db, gil.id)


def item(db, title):
    return next(p for p in list_month(db, OUT) if p.title == title)


def test_schema_has_the_folder_tables():
    assert SCHEMA_VERSION == 11


def test_folders_of_each_person(team):
    db, kayo, bia, caio, duda, _ = team
    assert folders_of(db, bia.id) == ("B", "C") and folders_by_person(db) == {bia.id: ("B", "C"), caio.id: ("D",)}
    assert {f: [p.name for p in ps] for f, ps in owners(db).items()} == {"B": ["Bia"], "C": ["Bia"], "D": ["Caio"]}
    set_folders(db, at(8), kayo, caio.id, ["D", "C"])  # pasta com duas pessoas
    assert [p.name for p in owners(db)["C"]] == ["Bia", "Caio"]
    with pytest.raises(ValidationError, match="Pasta inválida"):
        set_folders(db, at(8), kayo, bia.id, ["Z"])
    with pytest.raises(ValidationError, match="Assistente não tem pasta"):
        set_folders(db, at(8), kayo, duda.id, ["A"])
    with pytest.raises(PermissionError):
        set_folders(db, at(8), bia, caio.id, [])
    # quem vira assistente sai das pastas
    set_access(db, at(8), kayo, caio.id, "assistente", False)
    assert folders_of(db, caio.id) == () and "D" not in owners(db)
    details = [e["detail"] for e in events(db, date(2026, 10, 19), date(2026, 10, 19)) if e["kind"] == "pastas_alteradas"]
    assert "Bia: B, C" in details and "Caio: C, D" in details


def test_each_folder_marks_its_part(team):
    db, kayo, bia, caio, duda, gil = team
    general = add_priority(db, at(8), kayo, "Entregar as comissões", due_day=10)
    only_d = add_priority(db, at(8), kayo, "Conferir a rota", folder="D")
    p = item(db, general.title)
    assert p.required == ("B", "C", "D") and p.missing == ("B", "C", "D") and not p.done
    assert item(db, only_d.title).required == ("D",)
    # Bia tem duas pastas: escolhe qual concluiu
    with pytest.raises(ValidationError, match="Escolha qual das suas pastas"):
        mark_done(db, at(9), bia, general.id)
    mark_done(db, at(9), bia, general.id, "B")
    p = mark_done(db, at(9), bia, general.id, "C")
    assert [m.folder for m in p.marks] == ["B", "C"] and p.missing == ("D",) and not p.done
    with pytest.raises(ValidationError, match="não é das suas pastas"):
        mark_done(db, at(9), bia, only_d.id)
    with pytest.raises(PermissionError, match="Só quem cuida da pasta D"):
        mark_done(db, at(9), bia, general.id, "D")
    p = mark_done(db, at(10), caio, general.id)  # uma pasta só (D): não precisa escolher
    assert p.done and p.done_at is None and p.mark("D").done_by == caio.id
    # desfazer só a própria pasta; o gestor cobre qualquer pasta
    p = undo_done(db, at(11), bia, general.id, "C")
    assert p.missing == ("C",)
    p = mark_done(db, at(11), gil, general.id, "C")
    assert p.done and p.mark("C").done_by == gil.id
    assert by_folder(list_month(db, OUT)) == [("B", 1, 1), ("C", 1, 1), ("D", 1, 2)]
    # assistente não faz as prioridades
    for action in (mark_done, undo_done):
        with pytest.raises(PermissionError, match="Assistente"):
            action(db, at(12), duda, only_d.id)
    with pytest.raises(PermissionError, match="Assistente"):
        add_priority(db, at(12), duda, "Outra")


def test_without_folders_it_is_one_mark_as_before(db):
    kayo = add_person(db, at(7), None, "Kayo")
    create_pin(db, at(7), kayo.id, "1234", "1234")
    kayo = get_person(db, kayo.id)
    p = add_priority(db, at(8), kayo, "Lançar a meta")
    p = mark_done(db, at(9), kayo, p.id)
    assert p.required == () and p.done and p.done_by == kayo.id


def test_old_single_mark_still_counts_for_all_folders(team, db):
    db, kayo, bia, *_ = team
    p = add_priority(db, at(8), kayo, "Lançar a meta")
    with db.connect() as conn:  # marcada antes da fase 16 (marcação única)
        conn.execute("UPDATE priorities SET done_by = ?, done_at = ? WHERE id = ?", (kayo.id, at(8).isoformat(), p.id))
    p = item(db, "Lançar a meta")
    assert p.done and p.missing == ()
    p = undo_done(db, at(9), bia, p.id)  # desfazer volta o item todo para em aberto, pasta por pasta
    assert p.done_at is None and p.missing == ("B", "C", "D")


def test_tv_shows_each_folder_with_initials(team):
    db, kayo, bia, caio, *_ = team
    general = add_priority(db, at(8), kayo, "Entregar as campanhas")
    add_priority(db, at(8), kayo, "Conferir a rota", folder="D")
    mark_done(db, at(9), bia, general.id, "B")
    mark_done(db, at(9), bia, general.id, "C")
    data = tv_prioridades(db, at(10))
    card = next(i for i in data["items"] if i["title"] == "Entregar as campanhas")
    # a TV mostra a pasta que concluiu, não quem marcou
    assert [(f["folder"], f["done"]) for f in card["folders"]] == [("B", True), ("C", True), ("D", False)]
    assert "Bia" not in str(data) and bia.initials not in [f.get("initials") for f in card["folders"]]
    mark_done(db, at(10), caio, general.id)
    mark_done(db, at(10), caio, item(db, "Conferir a rota").id)
    assert tv_prioridades(db, at(11)) is None  # tudo feito: a tela sai da rotação


def test_goals_have_steps_marked_per_folder(team):
    db, kayo, bia, caio, duda, gil = team
    metas, *_ = create_default_list(db, at(8), kayo)
    assert metas.title == "Metas do mês" and metas.steps == GOAL_STEPS and len(GOAL_STEPS) == 4
    with pytest.raises(ValidationError, match="Escolha a etapa"):
        mark_done(db, at(9), caio, metas.id)
    with pytest.raises(ValidationError, match="Escolha a etapa"):
        mark_done(db, at(9), caio, metas.id, step=4)
    for n in range(3):
        p = mark_done(db, at(9), caio, metas.id, step=n)
    assert p.steps_done("D") == 3 and not p.folder_done("D") and p.missing == ("B", "C", "D")
    p = mark_done(db, at(10), caio, metas.id, step=3)
    assert p.folder_done("D") and p.missing == ("B", "C")
    p = undo_done(db, at(10), caio, metas.id, step=1)  # desfazer uma etapa reabre a pasta
    assert not p.folder_done("D") and p.steps_done("D") == 3
    mark_done(db, at(11), bia, metas.id, "B", 0)
    card = next(i for i in tv_prioridades(db, at(11))["items"] if i["title"] == "Metas do mês")
    assert card["steps"] == list(GOAL_STEPS)
    assert [(f["folder"], f["steps"]) for f in card["folders"]] == [
        ("B", [True, False, False, False]), ("C", [False] * 4), ("D", [True, False, True, True])]
    assert tv_prioridades(db, at(11))["items"][0]["title"] == "Metas do mês"  # à parte, sempre em cima
    with pytest.raises(ValidationError, match="pelo menos duas"):
        add_priority(db, at(12), kayo, "Outra", steps=("Uma",))
    assert parse_steps("  Enviar  \n\n Conferir ") == ("Enviar", "Conferir")
    history = [e["detail"] for e in events(db, date(2026, 10, 19), date(2026, 10, 19)) if e["kind"] == "prioridade_pasta_feita"]
    assert "D|Metas do mês · Gerente devolve a planilha" in history


def test_assistant_has_own_journey(team):
    db, kayo, bia, caio, duda, gil = team
    assert horas.journey(db)["semana"] == 600 and horas.journey(db, assistant=True)["semana"] == 360
    horas.save_journey(db, at(8), gil, "04:00", "", assistant=True)
    assert horas.journey(db, assistant=True)["semana"] == 240 and horas.journey(db)["semana"] == 600
    horas.save_entry(db, at(18), duda, date(2026, 10, 19), "08:00", "12:30")
    horas.save_entry(db, at(18), bia, date(2026, 10, 19), "08:00", "18:00")
    assert horas.summary(db, duda.id, date(2026, 10, 20)).balance == 30
    assert horas.summary(db, bia.id, date(2026, 10, 20)).balance == 0


# ---------- páginas ----------

@pytest.fixture
def web(team):
    db, *people = team
    app = create_app(db, clock=lambda: at(12))

    def login(person):
        c = TestClient(app, base_url=BASE)
        c.post(f"/entrar/{person.id}", data={"pin": "1234"})
        return c

    return db, *people, login


def test_priorities_page_by_folder(web):
    db, kayo, bia, caio, duda, gil, login = web
    p = add_priority(db, at(8), kayo, "Entregar as comissões")
    c = login(bia)
    page = c.get("/prioridades").text
    # Bia tem duas pastas: um botão por pasta, sem "marcar todas"
    assert f'action="/prioridades/{p.id}/feita?pasta=B"' in page and f'action="/prioridades/{p.id}/feita?pasta=C"' in page
    assert "Marcar como feita" not in page and "Cada pessoa marca as suas pastas" in page
    assert c.post(f"/prioridades/{p.id}/feita?pasta=B", follow_redirects=False).status_code == 303
    c.post(f"/prioridades/{p.id}/feita?pasta=C")
    page = c.get("/prioridades").text
    assert page.count("✓ concluída") == 2 and "Bia · 19/10" not in page  # a pasta, não quem fez
    # Caio tem uma pasta só: o botão do lado marca a dele
    assert f'action="/prioridades/{p.id}/feita?pasta=D"><button>Marcar como feita (pasta D)' in login(caio).get("/prioridades").text
    assert c.post(f"/prioridades/{p.id}/feita?pasta=D").status_code == 403
    # o gestor cobre a pasta D
    g = login(gil)
    assert f'action="/prioridades/{p.id}/feita?pasta=D"' in g.get("/prioridades").text
    g.post(f"/prioridades/{p.id}/feita?pasta=D")
    page = g.get("/prioridades").text
    assert "1 de 1 feitas" in page and "concluída por todas as pastas" in page
    history = g.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "Bia marcou “Entregar as comissões” como feita na pasta B" in history
    assert "Gil marcou “Entregar as comissões” como feita na pasta D" in history
    # assistente: só consulta
    a = login(duda)
    page = a.get("/prioridades").text
    assert "Assistente não faz as prioridades do mês" in page and "Acrescentar item" not in page
    assert f"/prioridades/{p.id}/desfazer" not in page
    assert a.post(f"/prioridades/{p.id}/desfazer").status_code == 403


def test_people_page_sets_folders_and_assistant(web):
    db, kayo, bia, caio, duda, gil, login = web
    c = login(kayo)
    page = c.get("/pessoas").text
    assert '<option value="assistente"' in page and "Assistente: sem pasta própria" in page
    assert c.post(f"/pessoas/{caio.id}/pastas", data={"pasta": ["E", "D"]}, follow_redirects=False).status_code == 303
    assert folders_of(db, caio.id) == ("D", "E")
    assert c.post(f"/pessoas/{duda.id}/pastas", data={"pasta": ["A"]}).status_code == 422
    assert login(bia).post(f"/pessoas/{caio.id}/pastas", data={"pasta": []}).status_code == 403
    page = login(gil).get("/horas/equipe").text
    assert "Jornada dos assistentes" in page and 'value="06:00"' in page


def test_goals_table_on_the_page(web):
    db, kayo, bia, caio, duda, gil, login = web
    c = login(bia)
    c.post("/prioridades/padrao")
    metas = list_month(db, OUT)[0]
    page = c.get("/prioridades").text
    assert 'class="etapas"' in page and "Gerente devolve a planilha" in page and "0 de 3 pastas concluíram" in page
    assert f"/prioridades/{metas.id}/feita?pasta=B&etapa=0" in page
    assert f"/prioridades/{metas.id}/feita?pasta=D&etapa=0" not in page  # pasta D é do Caio
    for n in range(4):
        c.post(f"/prioridades/{metas.id}/feita?pasta=B&etapa={n}")
    page = c.get("/prioridades").text
    assert "1 de 3 pastas concluíram" in page and "concluída" in page
    r = c.post("/prioridades", data={"title": "Campanha nova", "folder": "", "prazo": "", "etapas": "Montar\nEnviar"},
               follow_redirects=False)
    assert r.status_code == 303 and list_month(db, OUT)[-1].steps == ("Montar", "Enviar")
