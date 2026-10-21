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
from hub.prioridades import add_priority, by_folder, list_month, mark_done, tv_prioridades, undo_done
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
    # Bia marca as suas duas pastas de uma vez
    p = mark_done(db, at(9), bia, general.id)
    assert [m.folder for m in p.marks] == ["B", "C"] and p.missing == ("D",) and not p.done
    with pytest.raises(ValidationError, match="não é das suas pastas"):
        mark_done(db, at(9), bia, only_d.id)
    with pytest.raises(PermissionError, match="Só quem cuida da pasta D"):
        mark_done(db, at(9), bia, general.id, "D")
    p = mark_done(db, at(10), caio, general.id)
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
    mark_done(db, at(9), bia, general.id)
    data = tv_prioridades(db, at(10))
    card = next(i for i in data["items"] if i["title"] == "Entregar as campanhas")
    assert [(f["folder"], f["done"], f["initials"]) for f in card["folders"]] == [
        ("B", True, bia.initials), ("C", True, bia.initials), ("D", False, None)]
    assert "Bia" not in str(data)  # na TV, só iniciais
    mark_done(db, at(10), caio, general.id)
    mark_done(db, at(10), caio, item(db, "Conferir a rota").id)
    assert tv_prioridades(db, at(11)) is None  # tudo feito: a tela sai da rotação


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
    assert "Marcar como feita (B, C)" in page and "falta · Caio" in page and "Cada pessoa marca as suas pastas" in page
    assert c.post(f"/prioridades/{p.id}/feita", follow_redirects=False).status_code == 303
    page = c.get("/prioridades").text
    assert "✓ Bia · 19/10 12:00" in page and "Marcar como feita (B, C)" not in page
    assert c.post(f"/prioridades/{p.id}/feita?pasta=D").status_code == 403
    # o gestor cobre a pasta D
    g = login(gil)
    assert f'action="/prioridades/{p.id}/feita?pasta=D"' in g.get("/prioridades").text
    g.post(f"/prioridades/{p.id}/feita?pasta=D")
    page = g.get("/prioridades").text
    assert "1 de 1 feitas" in page and "feita por todas as pastas" in page
    history = g.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "Bia marcou “Entregar as comissões” como feita nas pastas B e C" in history
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
