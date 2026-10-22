"""Fase 17: entrar pelo nome e PIN, pedido de cadastro aprovado por administrador e limite por aparelho."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import cadastro
from hub.access import create_pin, pin_matches
from hub.db import SCHEMA_VERSION, Database, events
from hub.people import ValidationError, add_person, deactivate_person, get_person, list_people
from hub.web.app import create_app

BASE = "http://hub-sala:8800"


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    create_pin(db, at(7), kayo.id, "1234", "1234")  # primeiro PIN: vira administrador
    ana = add_person(db, at(7), None, "Ana Souza")
    create_pin(db, at(7), ana.id, "5678", "5678")
    client = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE)
    return client, db, get_person(db, kayo.id), get_person(db, ana.id)


def enter(c, nome, pin):
    return c.post("/entrar", data={"nome": nome, "pin": pin}, follow_redirects=False)


# ---------- banco ----------

def test_migration_creates_the_signup_table(db):
    assert SCHEMA_VERSION >= 12
    with sqlite3.connect(db.path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(signup_requests)")]
    assert cols == ["id", "name", "initials", "pin_hash", "created_at"]


def test_old_database_gains_the_table_and_keeps_people(tmp_path):
    path = tmp_path / "hub.db"
    d = Database(path)
    d.init()
    add_person(d, at(7), None, "Kayo")
    with sqlite3.connect(path) as conn:
        conn.execute("DROP TABLE signup_requests")
        for table in ("month_routine_marks", "month_routines", "month_categories"):  # migrações seguintes (v5)
            conn.execute(f"DROP TABLE {table}")
        conn.execute("PRAGMA user_version = 11")
    d.init()
    assert [p.name for p in list_people(d)] == ["Kayo"]
    assert cadastro.pending(d, at(8)) == []


# ---------- nome ----------

def test_name_ignores_accents_case_and_spaces(env):
    _, db, _, ana = env
    for typed in ("Ana Souza", "ana souza", "  ANA   souza ", "Âna Sóuza"):
        assert cadastro.find_by_name(db, typed).id == ana.id
    assert cadastro.find_by_name(db, "Ana") is None
    assert cadastro.find_by_name(db, "") is None


def test_inactive_person_is_not_found(env):
    _, db, kayo, ana = env
    deactivate_person(db, at(8), kayo.id, ana.id)
    assert cadastro.find_by_name(db, "Ana Souza") is None


# ---------- entrar ----------

def test_login_with_name_and_pin(env):
    c, *_ = env
    r = enter(c, "ana souza", "5678")
    assert r.status_code == 303 and r.headers["location"] == "/" and "hub_sessao" in r.headers["set-cookie"]
    assert c.get("/", follow_redirects=False).status_code == 200


def test_wrong_pin_counts_down_and_locks_the_name(env):
    c, *_ = env
    r = enter(c, "Ana Souza", "0000")
    assert r.status_code == 422 and "Mais 4 tentativas" in r.text and "hub_sessao" not in r.headers.get("set-cookie", "")
    assert 'value="Ana Souza"' in r.text  # o nome continua preenchido
    for _ in range(4):
        r = enter(c, "Ana Souza", "0000")
    assert "Bloqueado" in r.text
    assert "Muitas tentativas" in enter(c, "Ana Souza", "5678").text


def test_unknown_name_offers_signup(env):
    c, *_ = env
    r = enter(c, "Bruno Lima", "1111")
    assert r.status_code == 422 and "Não achei ninguém" in r.text
    assert 'href="/entrar/cadastro?nome=Bruno%20Lima"' in r.text


def test_person_without_pin_goes_to_create_it(env):
    c, db, *_ = env
    caio = add_person(db, at(8), None, "Caio")
    r = enter(c, "caio", "")
    assert r.status_code == 303 and r.headers["location"] == f"/entrar/{caio.id}"
    assert "crie o seu PIN" in c.get(r.headers["location"]).text


def test_device_is_blocked_after_many_errors_in_any_name(env):
    c, *_ = env
    names = ["Fulano", "Beltrano", "Kayo", "Ana Souza"]
    for i in range(10):
        enter(c, names[i % len(names)], "0000")
    r = enter(c, "Kayo", "1234")  # mesmo com o PIN certo, o aparelho espera
    assert r.status_code == 429 and "neste aparelho" in r.text
    assert c.post("/entrar/1", data={"pin": "1234"}, follow_redirects=False).status_code == 429


def test_device_limiter_frees_after_the_window():
    limiter = cadastro.DeviceLimiter(3, 900)
    for t in (0, 10, 20):
        limiter.hit("pc-1", t)
    assert limiter.wait_minutes("pc-1", 30) == 15
    assert limiter.wait_minutes("pc-2", 30) == 0
    assert limiter.wait_minutes("pc-1", 901) == 0  # o primeiro erro saiu da conta


def test_old_links_still_work(env):
    c, _, kayo, _ = env
    r = c.post(f"/entrar/{kayo.id}", data={"pin": "1234"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


# ---------- pedido de cadastro ----------

def test_signup_request_then_admin_approves(env):
    c, db, kayo, _ = env
    r = c.post("/entrar/cadastro", data={"nome": "Bruno Lima", "iniciais": "", "pin": "2468", "confirmar": "2468"})
    assert r.status_code == 200 and "Pedido enviado" in r.text
    # ainda não entra
    r = enter(c, "bruno lima", "2468")
    assert r.status_code == 422 and "esperando um administrador" in r.text
    assert "Bruno Lima" not in [p.name for p in list_people(db)]
    # o administrador vê o pedido (com o número no menu) e aprova como assistente
    admin = TestClient(c.app, base_url=BASE)
    enter(admin, "Kayo", "1234")
    page = admin.get("/pessoas").text
    assert "Pedidos de cadastro (1)" in page and 'class="contador"' in page
    req = cadastro.pending(db, at(12))[0]
    assert req.initials == "BL"
    r = admin.post(f"/pessoas/pedidos/{req.id}/aprovar", data={"role": "assistente"})
    assert r.status_code == 200 and "Bruno Lima entrou na equipe como Assistente" in r.text
    bruno = cadastro.find_by_name(db, "Bruno Lima")
    assert bruno.role == "assistente" and not bruno.is_admin and bruno.has_pin
    assert cadastro.pending(db, at(12)) == []
    # agora entra com o PIN que escolheu no pedido
    assert enter(c, "Bruno Lima", "2468").status_code == 303
    html = admin.get("/historico?de=2026-10-19&ate=2026-10-19").text
    assert "Bruno Lima pediu cadastro no Hub" in html and "Kayo aprovou o cadastro de Bruno Lima (Assistente)" in html


def test_the_pin_is_never_stored_in_the_request(env):
    _, db, *_ = env
    cadastro.request_signup(db, at(9), "Bruno", "", "2468", "2468")
    with db.connect() as conn:
        stored = conn.execute("SELECT pin_hash FROM signup_requests").fetchone()[0]
    assert "2468" not in stored and pin_matches("2468", stored)


def test_admin_rejects(env):
    c, db, kayo, _ = env
    req = cadastro.request_signup(db, at(9), "Intruso", "", "1111", "1111")
    enter(c, "Kayo", "1234")
    r = c.post(f"/pessoas/pedidos/{req.id}/recusar")
    assert r.status_code == 200 and "Pedido recusado" in r.text
    assert cadastro.pending(db, at(12)) == [] and cadastro.find_by_name(db, "Intruso") is None
    assert any(e["kind"] == "cadastro_recusado" for e in events(db, at(0).date(), at(23).date()))


def test_only_admins_approve(env):
    c, db, _, ana = env
    req = cadastro.request_signup(db, at(9), "Bruno", "", "2468", "2468")
    enter(c, "Ana Souza", "5678")  # analista
    assert "Pedidos de cadastro" not in c.get("/").text
    for acao in ("aprovar", "recusar"):
        assert c.post(f"/pessoas/pedidos/{req.id}/{acao}", data={"role": "analista"}).status_code == 403
    anon = TestClient(c.app, base_url=BASE)
    r = anon.post(f"/pessoas/pedidos/{req.id}/aprovar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/entrar"
    assert len(cadastro.pending(db, at(12))) == 1
    with pytest.raises(PermissionError):
        cadastro.approve(db, at(12), ana, req.id)


def test_signup_cannot_ask_for_manager_or_admin(env):
    _, db, kayo, _ = env
    req = cadastro.request_signup(db, at(9), "Bruno", "", "2468", "2468")
    with pytest.raises(ValidationError):
        cadastro.approve(db, at(12), kayo, req.id, "gestor")
    p = cadastro.approve(db, at(12), kayo, req.id)
    assert (p.role, p.is_admin) == ("analista", False)


@pytest.mark.parametrize("nome, pin, confirmar, msg", [
    ("Ana Souza", "1111", "1111", "já tem cadastro"),
    ("ana sOUZA", "1111", "1111", "já tem cadastro"),
    ("Bruno", "12", "12", "4 a 6 números"),
    ("Bruno", "1111", "2222", "não são iguais"),
    ("B", "1111", "1111", "Informe o seu nome"),
    ("<script>", "1111", "1111", "só letras"),
])
def test_signup_validation(env, nome, pin, confirmar, msg):
    c, db, *_ = env
    r = c.post("/entrar/cadastro", data={"nome": nome, "pin": pin, "confirmar": confirmar})
    assert r.status_code == 422 and msg in r.text
    assert cadastro.pending(db, at(12)) == []


def test_former_member_must_be_reactivated_by_an_admin(env):
    _, db, kayo, ana = env
    deactivate_person(db, at(8), kayo.id, ana.id)
    with pytest.raises(ValidationError, match="reativar"):
        cadastro.request_signup(db, at(9), "Ana Souza", "", "1111", "1111")


def test_same_name_twice_and_max_pending(env):
    _, db, *_ = env
    cadastro.request_signup(db, at(9), "Bruno", "", "1111", "1111")
    with pytest.raises(ValidationError, match="Já existe um pedido"):
        cadastro.request_signup(db, at(9), "bruno", "", "1111", "1111")
    for name in ("Caio", "Duda", "Edu", "Fabi"):
        cadastro.request_signup(db, at(9), name, "", "1111", "1111")
    with pytest.raises(ValidationError, match="muitos pedidos"):
        cadastro.request_signup(db, at(9), "Gabi", "", "1111", "1111")


def test_requests_expire_after_seven_days(env):
    _, db, kayo, _ = env
    req = cadastro.request_signup(db, at(9), "Bruno", "", "1111", "1111")
    assert len(cadastro.pending(db, at(9, day=25))) == 1
    assert cadastro.pending(db, at(10, day=26)) == []
    with pytest.raises(ValidationError, match="não existe mais"):
        cadastro.approve(db, at(10, day=26), kayo, req.id)


def test_approve_refuses_if_the_name_was_taken_meanwhile(env):
    _, db, kayo, _ = env
    req = cadastro.request_signup(db, at(9), "Bruno", "", "1111", "1111")
    add_person(db, at(10), kayo.id, "Bruno")
    with pytest.raises(ValidationError, match="Já existe alguém"):
        cadastro.approve(db, at(11), kayo, req.id)


def test_one_device_cannot_flood_requests(env):
    c, db, *_ = env
    for name in ("Bruno", "Caio", "Duda"):
        assert c.post("/entrar/cadastro", data={"nome": name, "pin": "1111", "confirmar": "1111"}).status_code == 200
    r = c.post("/entrar/cadastro", data={"nome": "Edu", "pin": "1111", "confirmar": "1111"})
    assert r.status_code == 429 and len(cadastro.pending(db, at(12))) == 3


# ---------- primeiro administrador ----------

def test_empty_hub_creates_the_first_admin_and_signs_in(db):
    c = TestClient(create_app(db, clock=lambda: at(12)), base_url=BASE)
    assert "Criar o primeiro administrador" in c.get("/entrar").text
    r = c.post("/entrar/cadastro", data={"nome": "Kayo", "pin": "1234", "confirmar": "1234"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    kayo = list_people(db)[0]
    assert kayo.is_admin and kayo.has_pin and kayo.name == "Kayo"
    assert c.get("/pessoas").status_code == 200
    # depois disso, o próximo já vira pedido
    other = TestClient(c.app, base_url=BASE)
    r = other.post("/entrar/cadastro", data={"nome": "Ana", "pin": "1111", "confirmar": "1111"})
    assert "Pedido enviado" in r.text and len(list_people(db)) == 1


def test_first_admin_only_on_an_empty_hub(env):
    _, db, *_ = env
    with pytest.raises(ValidationError, match="já tem gente"):
        cadastro.create_first_admin(db, at(9), "Outro", "", "1111", "1111")
