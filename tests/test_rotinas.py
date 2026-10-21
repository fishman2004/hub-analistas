"""Fase 7: rotinas com horário, o cartão calculado, as pastas, a espera, o prazo e o aviso da TV."""

import json
import sqlite3
import struct
import threading
import wave
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import demands as demands_module
from hub import rotinas as rotinas_module
from hub.access import create_pin, set_access
from hub.db import SCHEMA, SCHEMA_VERSION, Database, events
from hub.demands import (board, delete_demand, find_card, is_overdue, move_demand, toggle_folder, tv_card,
                         update_demand)
from hub.people import ValidationError, add_person, get_person, list_people
from hub.rotinas import (SUGGESTED, create_suggested, list_routines, save_routine, set_routine_active, tv_alerts,
                         weekdays_label)
from hub.telas import rotation
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
SEG, TER = 19, 20  # dias de outubro de 2026 (conftest.at): 19 é segunda, 20 é terça


@pytest.fixture
def team(db):
    people = {n: add_person(db, at(7), None, n) for n in ("Kayo", "Bia", "Gil")}
    for p in people.values():
        create_pin(db, at(7), p.id, "1234", "1234")  # Kayo, o primeiro, vira administrador
    set_access(db, at(7), get_person(db, people["Kayo"].id), people["Gil"].id, "gestor", False)
    return db, {n: get_person(db, p.id) for n, p in people.items()}


def rotina(db, owner, name="Transferência de pedidos", by=None, **kw):
    """Cadastra uma rotina de seg a sex às 14:50 para `owner`; quem cadastra é um administrador (ou `by`)."""
    fields = dict(name=name, weekdays=[0, 1, 2, 3, 4], starts_at="14:50", deadline=None, owner_id=owner.id,
                  folders=[], waits_for=[])
    fields.update(kw)
    by = by or next(x for x in list_people(db) if x.is_admin)
    return save_routine(db, at(7), by, None, **fields)


def cards(db, now, column="todo", owner_id=None):
    return [d for d in board(db, now, owner_id=owner_id)[column]]


def count_demands(db):
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM demands").fetchone()[0]


def ref(r, day=SEG):
    return f"rotina-{r.id}-2026-10-{day}"


def client(db, person, now=at(15)):
    c = TestClient(create_app(db, clock=lambda: now), base_url=BASE)
    c.post(f"/entrar/{person.id}", data={"pin": "1234"})
    return c


# ---------- quando o cartão aparece ----------

def test_card_appears_on_its_days_once_the_time_comes(team):
    db, p = team
    r = rotina(db, p["Kayo"], "Comparativo de rotas no grupo de gestão comercial", weekdays=[1, 3], starts_at="10:00")
    assert cards(db, at(9, 59, day=TER)) == []  # terça, antes do horário
    [card] = cards(db, at(10, day=TER))
    assert (card.id, card.ref, card.title, card.owner_id) == (None, ref(r, TER), r.name, p["Kayo"].id)
    assert card.routine.time == "10:00" and card.due == date(2026, 10, TER) and card.column == "todo"
    assert cards(db, at(12, day=SEG)) == []  # segunda não é dia dela
    assert cards(db, at(12, day=TER), owner_id=p["Bia"].id) == []  # só no quadro do responsável
    set_routine_active(db, at(11, day=TER), p["Kayo"], r.id, False)
    assert cards(db, at(12, day=TER)) == []


def test_card_is_calculated_not_stored(team):
    db, p = team
    rotina(db, p["Kayo"])
    for _ in range(3):
        assert len(cards(db, at(15))) == 1
    assert count_demands(db) == 0  # nenhuma tarefa agendada gravou nada


def test_weekdays_label():
    assert weekdays_label((0, 1, 2, 3, 4)) == "seg a sex"
    assert weekdays_label((1, 3)) == "ter e qui"
    assert weekdays_label((0, 2, 4)) == "seg, qua e sex"
    assert weekdays_label(tuple(range(7))) == "todos os dias"
    assert rotinas_module.FOLDERS == demands_module.FOLDERS


# ---------- vira demanda quando alguém mexe ----------

def test_first_interaction_makes_a_real_demand_once(team):
    db, p = team
    r = rotina(db, p["Kayo"])
    d = move_demand(db, at(15), p["Bia"].id, ref(r), "doing")
    assert (d.routine_id, d.routine_day, d.column, d.title) == (r.id, date(2026, 10, SEG), "doing", r.name)
    assert d.created_at == at(14, 50)  # nasce no horário da rotina: o cartão não muda de lugar
    again = move_demand(db, at(15, 5), p["Kayo"].id, ref(r), "todo")  # um PC com a página antiga
    assert again.id == d.id and count_demands(db) == 1
    [card] = cards(db, at(15, 10))
    assert card.id == d.id and card.ref == str(d.id) and card.routine.time == "14:50"
    kinds = [e["kind"] for e in events(db, date(2026, 10, SEG), date(2026, 10, SEG)) if e["subject"] == f"demanda:{d.id}"]
    assert kinds.count("rotina_demanda") == 1 and kinds.count("demanda_movida") == 2
    # no dia seguinte, a rotina aparece de novo, calculada; a de ontem, que ficou aberta, aparece atrasada antes
    assert [c.ref for c in cards(db, at(15, day=TER))] == [str(d.id), ref(r, TER)]


def test_edit_also_counts_as_interaction(team):
    db, p = team
    r = rotina(db, p["Kayo"])
    d = update_demand(db, at(15), p["Kayo"].id, ref(r), title="Transferência (só B hoje)", owner_id=p["Bia"].id,
                      folder=None, requested_by=None, due=date(2026, 10, SEG), reserved=False)
    assert d.routine_id == r.id and d.owner_id == p["Bia"].id and count_demands(db) == 1


def test_only_todays_due_routines_can_become_demands(team):
    db, p = team
    r = rotina(db, p["Kayo"])
    with pytest.raises(ValidationError, match="não está no quadro agora"):
        move_demand(db, at(14), p["Kayo"].id, ref(r), "doing")  # ainda não chegou o horário
    with pytest.raises(ValidationError, match="não está no quadro agora"):
        move_demand(db, at(15, day=TER), p["Kayo"].id, ref(r, SEG), "doing")  # cartão de ontem
    with pytest.raises(ValidationError, match="Demanda não encontrada"):
        move_demand(db, at(15), p["Kayo"].id, "rotina-x", "doing")
    assert count_demands(db) == 0
    assert find_card(db, at(15), ref(r)).id is None and count_demands(db) == 0  # abrir o formulário não cria


def test_unique_per_day_even_with_two_pcs_at_once(team):
    db, p = team
    r = rotina(db, p["Kayo"], folders=["B", "C", "F"])
    errors = []

    def worker(person, folder):
        try:
            toggle_folder(Database(db.path), at(15), person.id, ref(r), folder)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(p[n], f)) for n, f in (("Kayo", "B"), ("Bia", "C"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and count_demands(db) == 1
    [card] = cards(db, at(15, 1), "doing")
    assert set(card.routine.checked) == {"B", "C"}


def test_deleting_the_card_skips_the_routine_only_today(team):
    db, p = team
    r = rotina(db, p["Kayo"])
    delete_demand(db, at(15), p["Kayo"].id, ref(r))
    assert cards(db, at(16)) == []
    assert [c.ref for c in cards(db, at(15, day=TER))] == [ref(r, TER)]


# ---------- pastas ----------

def test_folders_finish_the_routine_and_unchecking_reopens(team):
    db, p = team
    r = rotina(db, p["Kayo"], folders=["F", "B", "C"])
    assert r.folders == ("B", "C", "F")
    d = toggle_folder(db, at(14, 55), p["Bia"].id, ref(r), "B")
    assert d.column == "doing"  # a primeira pasta marcada já mostra que começou
    with pytest.raises(ValidationError, match="Faltam as pastas C, F"):
        move_demand(db, at(14, 56), p["Kayo"].id, d.id, "done")
    toggle_folder(db, at(14, 57), p["Kayo"].id, d.id, "C")
    done = toggle_folder(db, at(14, 58), p["Gil"].id, d.id, "F")
    assert done.column == "done" and done.done_at == at(14, 58)
    [card] = cards(db, at(15), "done")
    assert card.routine.checked == ("B", "C", "F")
    reopened = toggle_folder(db, at(15, 5), p["Bia"].id, d.id, "C")
    assert reopened.column == "doing" and reopened.done_at is None
    with pytest.raises(ValidationError, match="Essa pasta não faz parte desta rotina"):
        toggle_folder(db, at(15, 6), p["Bia"].id, d.id, "A")
    marks = [(e["kind"], e["actor_id"], e["detail"]) for e in events(db, date(2026, 10, SEG), date(2026, 10, SEG))
             if e["kind"].startswith("pasta_")]
    assert marks[::-1] == [("pasta_marcada", p["Bia"].id, "B"), ("pasta_marcada", p["Kayo"].id, "C"),
                           ("pasta_marcada", p["Gil"].id, "F"), ("pasta_desmarcada", p["Bia"].id, "C")]


def test_folder_toggle_on_a_normal_demand_is_refused(team):
    db, p = team
    from hub.demands import create_demand
    d = create_demand(db, at(8), p["Kayo"].id, title="Normal", owner_id=p["Kayo"].id, folder="B")
    with pytest.raises(ValidationError, match="Essa pasta não faz parte desta rotina"):
        toggle_folder(db, at(9), p["Kayo"].id, d.id, "B")


# ---------- liberada depois de ----------

def test_waits_until_the_other_routine_is_done(team):
    db, p = team
    transf = rotina(db, p["Kayo"], folders=["B"], deadline="15:00")
    atual = rotina(db, p["Bia"], "Atualização de positivações no grupo de gestão comercial", starts_at="15:00",
                   waits_for=[transf.id])
    [card] = cards(db, at(15, 5), owner_id=p["Bia"].id)
    assert card.routine.waiting == ("Transferência de pedidos 14:50",)
    for column in ("doing", "done"):
        with pytest.raises(ValidationError, match="Aguardando: Transferência de pedidos 14:50"):
            move_demand(db, at(15, 5), p["Bia"].id, ref(atual), column)
    assert count_demands(db) == 0  # a recusa não deixa demanda criada pela metade
    toggle_folder(db, at(15, 6), p["Kayo"].id, ref(transf), "B")  # transferência concluída
    [card] = cards(db, at(15, 7), owner_id=p["Bia"].id)
    assert card.routine.waiting == ()
    assert move_demand(db, at(15, 7), p["Bia"].id, ref(atual), "doing").column == "doing"


def test_waiting_only_counts_routines_that_run_today(team):
    db, p = team
    terca = rotina(db, p["Kayo"], "Só às terças", weekdays=[1])
    dispensada = rotina(db, p["Kayo"], "Dispensada hoje", starts_at="14:00")
    atual = rotina(db, p["Bia"], "Depois das duas", starts_at="15:00", waits_for=[terca.id, dispensada.id])
    [card] = cards(db, at(15), owner_id=p["Bia"].id)
    assert card.routine.waiting == ("Dispensada hoje 14:00",)  # a de terça não roda na segunda
    delete_demand(db, at(15), p["Kayo"].id, ref(dispensada))  # dispensada hoje: não segura mais ninguém
    assert move_demand(db, at(15, 1), p["Bia"].id, ref(atual), "doing").column == "doing"


# ---------- prazo ----------

def test_deadline_makes_the_card_late(team):
    db, p = team
    r = rotina(db, p["Kayo"], "PHD · positivação diária", starts_at="08:00", deadline="09:00")
    [card] = cards(db, at(8, 30))
    assert card.routine.deadline == "09:00" and not card.routine.late and not is_overdue(card, date(2026, 10, SEG))
    [card] = cards(db, at(9, 1))
    assert card.routine.late and is_overdue(card, date(2026, 10, SEG))
    tv = TestClient(create_app(db, clock=lambda: at(9, 1)), base_url=BASE).get("/api/tv").json()
    assert tv["overdue"] == 1  # entra no aviso de atrasadas da TV
    assert tv["columns"]["todo"][0]["overdue"] is True and tv["columns"]["todo"][0]["routine"]["late"] is True
    move_demand(db, at(9, 2), p["Kayo"].id, ref(r), "done")
    [card] = cards(db, at(9, 3), "done")
    assert not is_overdue(card, date(2026, 10, SEG))
    # sem concluir, no dia seguinte o cartão de ontem fica atrasado pela data, como qualquer demanda
    move_demand(db, at(9, 4), p["Kayo"].id, card.id, "doing")
    [old] = cards(db, at(7, day=TER), "doing")
    assert is_overdue(old, date(2026, 10, TER)) and not old.routine.late


# ---------- cadastro ----------

@pytest.mark.parametrize("kwargs, message", [
    ({"name": "  "}, "Informe o nome da rotina."),
    ({"name": "x" * 81}, r"Nome muito longo \(máximo 80\)."),
    ({"weekdays": []}, "Marque pelo menos um dia da semana."),
    ({"weekdays": [7]}, "Dia da semana inválido."),
    ({"starts_at": "25:00"}, "Horário inválido"),
    ({"starts_at": "8:00"}, "Horário inválido"),
    ({"deadline": "14:50"}, "O prazo precisa ser depois do horário"),
    ({"deadline": "amanhã"}, "Prazo inválido"),
    ({"folders": ["Z"]}, "Pasta inválida."),
    ({"owner_id": 999}, "Escolha o responsável pela rotina."),
    ({"waits_for": [999]}, "Rotina não encontrada"),
])
def test_validation_messages(team, kwargs, message):
    db, p = team
    with pytest.raises(ValidationError, match=message):
        rotina(db, p["Kayo"], **kwargs)


def test_no_duplicates_and_no_cycles(team):
    db, p = team
    a = rotina(db, p["Kayo"])
    with pytest.raises(ValidationError, match="Já existe a rotina “transferência de pedidos” às 14:50"):
        rotina(db, p["Kayo"], "transferência de pedidos")
    b = rotina(db, p["Kayo"], "Relatório", starts_at="15:00", waits_for=[a.id])
    fields = dict(name=a.name, weekdays=[0], starts_at="14:50", deadline=None, owner_id=p["Kayo"].id, folders=[])
    for waits in ([b.id], [a.id]):
        with pytest.raises(ValidationError, match="não pode esperar por ela mesma"):
            save_routine(db, at(8), p["Kayo"], a.id, waits_for=waits, **fields)


def test_only_manager_and_admins_change_routines(team):
    db, p = team
    with pytest.raises(PermissionError):
        rotina(db, p["Bia"], by=p["Bia"])
    r = rotina(db, p["Gil"], by=p["Gil"])  # gestor (sem ser administrador)
    with pytest.raises(PermissionError):
        set_routine_active(db, at(8), p["Bia"], r.id, False)
    with pytest.raises(PermissionError):
        create_suggested(db, at(8), p["Bia"])
    edited = save_routine(db, at(8), p["Kayo"], r.id, name="Transferência", weekdays=[0], starts_at="16:50",
                          deadline="17:00", owner_id=p["Bia"].id, folders=["B"], waits_for=[])
    assert (edited.name, edited.weekdays, edited.deadline, edited.owner_id) == ("Transferência", (0,), "17:00", p["Bia"].id)
    kinds = [(e["kind"], e["actor_id"]) for e in events(db, date(2026, 10, SEG), date(2026, 10, SEG))
             if e["subject"] == f"rotina:{r.id}"]
    assert kinds == [("rotina_editada", p["Kayo"].id), ("rotina_criada", p["Gil"].id)]


def test_suggested_routines(team):
    db, p = team
    assert create_suggested(db, at(8), p["Gil"]) == len(SUGGESTED) == 6
    assert create_suggested(db, at(8), p["Kayo"]) == 0  # já existem: não duplica
    routines = {r.label: r for r in list_routines(db)}
    assert all(r.owner_id == p["Gil"].id for r in routines.values())
    phd = routines["PHD · positivação diária 08:00"]
    assert (phd.weekdays, phd.deadline) == ((0, 1, 2, 3, 4), "09:00")
    for start, deadline, after in (("14:50", "15:00", "15:00"), ("16:50", "17:00", "17:00")):
        transf = routines[f"Transferência de pedidos {start}"]
        assert (transf.folders, transf.deadline) == (("B", "C", "F"), deadline)
        assert routines[f"Atualização de positivações no grupo de gestão comercial {after}"].waits_for == (transf.id,)
    assert routines["Comparativo de rotas no grupo de gestão comercial 10:00"].weekdays == (1, 3)


# ---------- TV ----------

def test_tv_gets_routine_cards_and_alerts_without_reserved_data(team):
    db, p = team
    transf = rotina(db, p["Kayo"], folders=["B", "C", "F"], deadline="15:00")
    secreta = rotina(db, p["Bia"], "Fechamento", starts_at="15:00")
    rotina(db, p["Bia"], "Mais tarde", starts_at="17:00")
    toggle_folder(db, at(14, 55), p["Bia"].id, ref(transf), "C")
    update_demand(db, at(15, 1), p["Bia"].id, ref(secreta), title="Comissões secretas", owner_id=p["Bia"].id,
                  folder="D", requested_by="Diretoria", due=None, reserved=True)
    c = TestClient(create_app(db, clock=lambda: at(15, 2)), base_url=BASE)
    data = c.get("/api/tv").json()
    [card] = data["columns"]["doing"]
    assert card["routine"] == {"time": "14:50", "deadline": "15:00", "folders": ["B", "C", "F"], "checked": ["C"],
                               "waiting": [], "late": True}
    [hidden] = data["columns"]["todo"]
    assert hidden["title"] == "Demanda reservada" and hidden["routine"] is None and hidden["folder"] is None
    # avisos: as rotinas de hoje, inclusive a das 17:00; a que virou reservada não vai
    assert [(a["key"], a["time"], a["name"]) for a in data["avisos"]] == [
        (ref(transf), "14:50", "Transferência de pedidos"), (f"rotina-3-2026-10-{SEG}", "17:00", "Mais tarde")]
    assert data["avisos"][0]["at"] == "2026-10-19T14:50:00" and data["avisos"][0]["deadline"] == "15:00"
    body = c.get("/api/tv").text
    assert "Comissões" not in body and "Diretoria" not in body and "Fechamento" not in body
    assert tv_alerts(db, at(9, day=25)) == []  # domingo: nada


def test_deadlines_screen_only_shows_late_routines(team):
    db, p = team
    rotina(db, p["Kayo"], deadline="15:00")
    assert [s["id"] for s in rotation(db, at(14, 55))["screens"]] == ["quadro"]  # rotina de hoje não é "prazo"
    prazos = next(s for s in rotation(db, at(15, 1))["screens"] if s["id"] == "prazos")
    assert [g["label"] for g in prazos["data"]["groups"]] == ["Atrasadas"]


def test_reserved_routine_card_is_masked(team):
    db, p = team
    r = rotina(db, p["Kayo"], folders=["B"])
    d = update_demand(db, at(15), p["Kayo"].id, ref(r), title="Assunto sensível", owner_id=p["Kayo"].id, folder=None,
                      requested_by=None, due=None, reserved=True)
    [card] = cards(db, at(15, 1))
    data = tv_card(card, p["Kayo"], date(2026, 10, SEG))
    assert data["title"] == "Demanda reservada" and data["routine"] is None
    assert "Assunto" not in json.dumps(data, ensure_ascii=False) and data["id"] == str(d.id)


# ---------- app ----------

def test_routines_page_permissions(team):
    db, p = team
    bia = client(db, p["Bia"])
    assert 'href="/rotinas"' in bia.get("/").text
    page = bia.get("/rotinas")
    assert page.status_code == 200 and "Nova rotina" not in page.text and "Criar rotinas sugeridas" not in page.text
    form = {"name": "Conferência", "weekdays": ["0", "2"], "starts_at": "11:00", "deadline": "", "owner_id": str(p["Bia"].id)}
    assert bia.post("/rotinas", data=form).status_code == 403
    assert bia.post("/rotinas/sugeridas").status_code == 403
    assert list_routines(db) == []
    gil = client(db, p["Gil"])
    assert "Nova rotina" in gil.get("/rotinas").text
    r = gil.post("/rotinas", data={**form, "folders": ["B", "C"]}, follow_redirects=False)
    assert r.status_code == 303
    [made] = list_routines(db)
    assert (made.weekdays, made.folders, made.deadline) == ((0, 2), ("B", "C"), None)
    assert bia.get(f"/rotinas/{made.id}").status_code == 403
    assert bia.post(f"/rotinas/{made.id}/ativa", data={"active": "0"}).status_code == 403
    r = gil.post(f"/rotinas/{made.id}", data={**form, "name": "", "folders": ["B"]})
    assert r.status_code == 422 and "Informe o nome da rotina." in r.text
    kayo = client(db, p["Kayo"])
    assert kayo.post(f"/rotinas/{made.id}/ativa", data={"active": "0"}, follow_redirects=False).status_code == 303
    assert not list_routines(db)[0].active
    r = kayo.post("/rotinas/sugeridas")
    assert r.status_code == 200 and "6 rotinas criadas" in r.text
    assert "Transferência de pedidos" in bia.get("/rotinas").text and "seg a sex" in bia.get("/rotinas").text


def test_any_analyst_marks_a_folder_and_sees_the_routine(team):
    db, p = team
    r = rotina(db, p["Kayo"], folders=["B", "C", "F"], deadline="15:00")
    bia = client(db, p["Bia"], now=at(14, 55))
    home = bia.get("/").text
    assert "Pastas para marcar" in home and "Transferência de pedidos" in home  # rotina do Kayo, com pastas
    assert f'action="/demandas/{ref(r)}/pasta"' in home
    assert bia.post(f"/demandas/{ref(r)}/pasta", data={"folder": "B"}, follow_redirects=False).status_code == 303
    [card] = cards(db, at(14, 56), "doing")
    assert card.routine.checked == ("B",)
    kayo = client(db, p["Kayo"], now=at(14, 56))
    mine = kayo.get("/").text
    assert "rotina 14:50 · até 15:00" in mine and f'href="/demandas/{card.id}"' in mine
    assert "Pastas para marcar" not in mine  # a rotina é dele: está nas colunas
    html = kayo.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "Bia marcou a pasta B em “Transferência de pedidos”" in html
    assert "Kayo cadastrou a rotina “Transferência de pedidos 14:50”" in html


def test_virtual_card_edit_form_and_blocked_move_message(team):
    db, p = team
    transf = rotina(db, p["Kayo"], folders=["B"])
    atual = rotina(db, p["Kayo"], "Atualização", starts_at="15:00", waits_for=[transf.id])
    kayo = client(db, p["Kayo"], now=at(15, 1))
    home = kayo.get("/").text
    assert "Aguardando: Transferência de pedidos 14:50" in home
    form = kayo.get(f"/demandas/{ref(atual)}").text
    assert "Atualização" in form and f'action="/demandas/{ref(atual)}"' in form and count_demands(db) == 0
    r = kayo.post(f"/demandas/{ref(atual)}/mover", data={"column": "doing"})
    assert r.status_code == 422 and "Aguardando: Transferência de pedidos 14:50" in r.text
    r = kayo.post(f"/demandas/{ref(atual)}", data={"title": "Atualização das 15h", "owner_id": str(p["Bia"].id)},
                  follow_redirects=False)
    assert r.status_code == 303 and cards(db, at(15, 2), owner_id=p["Bia"].id)[0].title == "Atualização das 15h"


def test_gestor_table_links_routine_cards(team):
    db, p = team
    r = rotina(db, p["Kayo"])
    html = client(db, p["Gil"]).get("/gestor").text
    assert f'href="/demandas/{ref(r)}"' in html


# ---------- migração, som e quiosque ----------

def test_v1_database_gets_routines(tmp_path):
    path = tmp_path / "hub.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO people(name, initials, color) VALUES ('Kayo', 'K', '#7FB2E5')")
    conn.execute("INSERT INTO demands(title, owner_id, column_, created_at, updated_at) "
                 "VALUES ('Relatório Aurora', 1, 'todo', '2026-10-19T08:00:00', '2026-10-19T08:00:00')")
    conn.commit()
    conn.close()
    db = Database(path)
    db.init()
    with db.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 5
        assert tuple(conn.execute("SELECT title, routine_id, routine_day FROM demands").fetchone()) == (
            "Relatório Aurora", None, None)
    create_pin(db, at(8), 1, "1234", "1234")  # vira administrador
    kayo = get_person(db, 1)
    r = rotina(db, kayo)
    move_demand(db, at(15), kayo.id, ref(r), "doing")
    assert [d.title for d in board(db, at(15))["doing"]] == ["Transferência de pedidos"]
    assert [d.title for d in board(db, at(15))["todo"]] == ["Relatório Aurora"]


def test_alert_sound_is_small_and_matches_the_generator():
    from tools.gerar_som import TARGET, build

    assert TARGET.name == "aviso.wav" and TARGET.exists()
    data, fresh = TARGET.read_bytes(), build()
    assert len(data) < 100_000 and len(fresh) == len(data) and fresh[:44] == data[:44]
    # o arquivo é o que o script gera (com folga de 1 no arredondamento, que muda de um sistema para outro)
    frames = lambda raw: struct.unpack(f"<{(len(raw) - 44) // 2}h", raw[44:])
    assert max(abs(a - b) for a, b in zip(frames(data), frames(fresh))) <= 1
    with wave.open(str(TARGET)) as w:
        assert w.getnchannels() == 1 and 1.0 < w.getnframes() / w.getframerate() < 3.0
    tv_js = (Path(__file__).parents[1] / "hub" / "web" / "static" / "tv.js").read_text(encoding="utf-8")
    assert "/static/aviso.wav" in tv_js and "localStorage" in tv_js


def test_tv_kiosk_allows_sound_without_a_click(monkeypatch):
    from hub import winsys

    calls = []
    monkeypatch.setattr(winsys.sys, "platform", "win32")
    monkeypatch.setattr(winsys.subprocess, "Popen", lambda args, **kw: calls.append(args))
    winsys.open_tv("http://127.0.0.1:8800/tv")
    assert "--autoplay-policy=no-user-gesture-required" in calls[0] and "--kiosk" in calls[0]
