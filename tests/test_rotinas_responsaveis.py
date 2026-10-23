"""Pedidos do Kayo (23/10/2026): rotina com mais de um responsável, remover uma rotina e tirar todos os
blocos da trilha de uma pessoa de uma vez."""

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import trilha
from hub.access import create_pin, set_access
from hub.db import events
from hub.demands import board, find_card, move_demand, tv_card
from hub.people import ValidationError, add_person, get_person, list_people
from hub.rotinas import get_routine, list_routines, remove_routine, save_routine
from hub.trilha import list_blocks, save_block
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"
SEG = 19  # segunda, 19/10/2026


@pytest.fixture
def team(db):
    people = {n: add_person(db, at(7), None, n) for n in ("Kayo", "Bia", "Gil", "Duda")}
    for p in people.values():
        create_pin(db, at(7), p.id, "1234", "1234")
    set_access(db, at(7), get_person(db, people["Kayo"].id), people["Gil"].id, "gestor", False)
    return db, {n: get_person(db, p.id) for n, p in people.items()}


def rotina(db, who, owners, name="Transferência de pedidos", **kw):
    fields = dict(name=name, weekdays=[0, 1, 2, 3, 4], starts_at="14:50", deadline=None, folders=[], waits_for=[],
                  owner_ids=[p.id for p in owners])
    fields.update(kw)
    return save_routine(db, at(7), who, None, **fields)


# ---------- vários responsáveis ----------

def test_routine_with_several_owners_shows_on_each_board(team):
    db, t = team
    r = rotina(db, t["Kayo"], [t["Bia"], t["Gil"]])
    assert (r.owner_id, r.owners) == (t["Bia"].id, (t["Bia"].id, t["Gil"].id))
    for who in ("Bia", "Gil"):
        assert [d.title for d in board(db, at(15, day=SEG), owner_id=t[who].id)["todo"]] == [r.name]
    assert board(db, at(15, day=SEG), owner_id=t["Duda"].id)["todo"] == []
    assert len(board(db, at(15, day=SEG))["todo"]) == 1  # o quadro de todos: um cartão só
    # qualquer um dos responsáveis mexe, e o cartão vai junto para o outro
    move_demand(db, at(15, 5, day=SEG), t["Gil"].id, f"rotina-{r.id}-2026-10-{SEG}", "doing")
    assert board(db, at(15, 6, day=SEG), owner_id=t["Bia"].id)["doing"][0].title == r.name


def test_owner_rules_and_list(team):
    db, t = team
    r = rotina(db, t["Kayo"], [t["Bia"], t["Bia"], t["Gil"]])  # repetido conta uma vez só
    assert r.owners == (t["Bia"].id, t["Gil"].id)
    with pytest.raises(ValidationError, match="pelo menos um responsável"):
        rotina(db, t["Kayo"], [], name="Outra")
    # um responsável de verdade é obrigatório; o antigo owner_id sozinho ainda funciona
    solo = save_routine(db, at(7), t["Kayo"], None, name="Solo", weekdays=[0], starts_at="09:00", deadline=None,
                        owner_id=t["Duda"].id, folders=[], waits_for=[])
    assert solo.owners == (t["Duda"].id,)
    # trocar a lista de responsáveis
    again = save_routine(db, at(8), t["Kayo"], r.id, name=r.name, weekdays=[0, 1], starts_at=r.starts_at,
                         deadline=None, folders=[], waits_for=[], owner_ids=[t["Gil"].id])
    assert again.owners == (t["Gil"].id,) and again.owner_id == t["Gil"].id


def test_tv_card_carries_the_other_owners(team):
    db, t = team
    r = rotina(db, t["Kayo"], [t["Bia"], t["Gil"]])
    d = board(db, at(15, day=SEG))["todo"][0]
    people = {p.id: p for p in list_people(db)}
    card = tv_card(d, people[d.owner_id], at(15, day=SEG).date(), people)
    assert card["initials"] == t["Bia"].initials
    assert card["routine"]["others"] == [{"initials": t["Gil"].initials, "color": t["Gil"].color}]


def test_routine_form_saves_several_owners(team):
    db, t = team
    c = login(TestClient(create_app(db, clock=lambda: at(9, day=SEG)), base_url=BASE), t["Kayo"])
    r = c.post("/rotinas", data={"name": "Conferir metas", "starts_at": "10:00", "weekdays": ["0", "1"],
                                 "owner_id": str(t["Bia"].id), "also": [str(t["Gil"].id), str(t["Bia"].id)]},
               follow_redirects=False)
    assert r.status_code == 303
    saved = next(x for x in list_routines(db) if x.name == "Conferir metas")
    assert saved.owners == (t["Bia"].id, t["Gil"].id)
    page = c.get(f"/rotinas/{saved.id}").text
    assert "Outros responsáveis" in page and f'value="{t["Gil"].id}" checked' in page
    assert "Bia" in c.get("/rotinas").text and "Gil" in c.get("/rotinas").text


# ---------- remover ----------

def test_remove_routine_keeps_history_and_blocks_links(team):
    db, t = team
    r = rotina(db, t["Kayo"], [t["Bia"]])
    after = rotina(db, t["Kayo"], [t["Bia"]], name="Depois", starts_at="15:00", waits_for=[r.id])
    card = find_card(db, at(15, day=SEG), f"rotina-{r.id}-2026-10-{SEG}")
    with pytest.raises(PermissionError):
        remove_routine(db, at(16, day=SEG), t["Bia"], r.id)
    remove_routine(db, at(16, day=SEG), t["Kayo"], r.id)
    assert [x.id for x in list_routines(db)] == [after.id]
    assert get_routine(db, r.id).removed and not get_routine(db, r.id).active  # fica guardada
    assert get_routine(db, after.id).waits_for == ()  # ninguém espera por uma rotina que saiu
    assert [d.title for d in board(db, at(17, day=SEG))["todo"]] == ["Depois"]
    assert card.title == r.name  # a demanda que ela já gerou continua existindo
    kinds = [e["kind"] for e in events(db, at(0, day=SEG).date(), at(23, day=SEG).date())]
    assert "rotina_removida" in kinds
    with pytest.raises(ValidationError, match="não encontrada"):
        remove_routine(db, at(17, day=SEG), t["Kayo"], r.id)
    # o mesmo nome e horário podem ser cadastrados de novo
    rotina(db, t["Kayo"], [t["Bia"]])


def test_remove_routine_page(team):
    db, t = team
    r = rotina(db, t["Kayo"], [t["Bia"]])
    c = login(TestClient(create_app(db, clock=lambda: at(9, day=SEG)), base_url=BASE), t["Kayo"])
    assert f'action="/rotinas/{r.id}/remover"' in c.get("/rotinas").text
    page = c.post(f"/rotinas/{r.id}/remover").text
    assert "foi removida" in page and f'action="/rotinas/{r.id}/remover"' not in page
    assert c.get(f"/rotinas/{r.id}", follow_redirects=False).status_code == 303
    assert "removeu a rotina" in c.get("/historico").text
    cb = login(TestClient(create_app(db, clock=lambda: at(9, day=SEG)), base_url=BASE), t["Bia"])
    assert cb.post(f"/rotinas/{r.id}/remover").status_code == 403


# ---------- trilha: tirar tudo ----------

def bloco(db, p, start, end, title):
    return save_block(db, at(7), p, None, person_id=p.id, weekdays=[0, 1, 2, 3, 4], starts_at=start, ends_at=end,
                      title=title)


def test_remove_all_trail_blocks(team):
    db, t = team
    ana, bia = t["Duda"], t["Bia"]
    for p in (ana, bia):
        bloco(db, p, "09:00", "10:00", "PHD")
        bloco(db, p, "10:00", "11:00", "Devolutivas")
    with pytest.raises(PermissionError):
        trilha.remove_all(db, at(9), bia, ana.id)  # colega não
    assert trilha.remove_all(db, at(9), ana, ana.id) == 2
    assert list_blocks(db, ana.id) == [] and len(list_blocks(db, bia.id)) == 2
    assert trilha.remove_all(db, at(9), ana, ana.id) == 0  # vazia: nada a tirar
    assert trilha.remove_all(db, at(9), t["Gil"], bia.id) == 2  # o gestor pode


def test_remove_all_page(team):
    db, t = team
    ana = t["Duda"]
    bloco(db, ana, "09:00", "10:00", "PHD")
    bloco(db, ana, "10:00", "11:00", "Devolutivas")
    c = login(TestClient(create_app(db, clock=lambda: at(9, day=SEG)), base_url=BASE), ana)
    page = c.get("/trilha/montar").text
    assert 'action="/trilha/montar/tirar-tudo"' in page and "Tirar todos os blocos (2)" in page
    r = c.post("/trilha/montar/tirar-tudo", data={"pessoa": str(ana.id)}, follow_redirects=False)
    assert r.status_code == 303 and list_blocks(db, ana.id) == []
    after = c.get(r.headers["location"]).text
    assert "2 blocos tirados" in after and "Tirar todos os blocos" not in after
    assert "tirou todos os blocos (2) da trilha de Duda" in c.get("/historico").text
    cb = login(TestClient(create_app(db, clock=lambda: at(9, day=SEG)), base_url=BASE), t["Bia"])
    assert cb.post("/trilha/montar/tirar-tudo", data={"pessoa": str(ana.id)}).status_code == 403
