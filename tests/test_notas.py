"""Fase 12: bloco de notas pessoal (só a dona vê) com anexos."""

import io
import zipfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import anexos, notas
from hub.access import set_access
from hub.people import ValidationError, add_person, deactivate_person, get_person
from hub.web.app import create_app
from test_web_app import login

PDF = b"%PDF-1.4 nota"


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DADOS", str(tmp_path / "dados"))


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    # Bianca é gestora e administradora: mesmo assim não vê as notas do Kayo
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url="http://hub-sala:8800"), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", True)
    clock = {"now": at(12)}
    app = create_app(db, clock=lambda: clock["now"])
    ck, cb = (TestClient(app, base_url="http://hub-sala:8800") for _ in range(2))
    login(ck, kayo)
    login(cb, bianca)
    return ck, cb, db, get_person(db, kayo.id), get_person(db, bianca.id), clock


def new_note(c, title="Ideias", body="texto"):
    r = c.post("/notas", follow_redirects=False)
    note_id = int(r.headers["location"].rsplit("/", 1)[1])
    c.post(f"/notas/{note_id}", data={"title": title, "body": body})
    return note_id


def test_create_edit_and_list(env):
    ck, _, db, kayo, _, _ = env
    note_id = new_note(ck, "Ideias do mês", "Painel por pasta\nComparar com setembro")
    html = ck.get("/notas").text
    assert "Ideias do mês" in html and "Painel por pasta" in html
    html = ck.get(f"/notas/{note_id}").text
    assert "Comparar com setembro" in html


def test_only_the_owner_sees_not_even_manager_or_admin(env):
    ck, cb, db, kayo, bianca, _ = env
    note_id = new_note(ck, "Segredo do Kayo", "conteúdo")
    assert "Segredo" not in cb.get("/notas").text
    r = cb.get(f"/notas/{note_id}")
    assert r.status_code == 404 and "Segredo" not in r.text
    assert cb.post(f"/notas/{note_id}", data={"title": "x", "body": "y"}).status_code == 404
    assert cb.post(f"/notas/{note_id}/excluir").status_code == 404
    assert notas.get_note(db, kayo, note_id).title == "Segredo do Kayo"


def test_notes_never_in_history_gestor_or_tv(env):
    ck, cb, db, kayo, _, _ = env
    note_id = new_note(ck, "Segredo do Kayo", "conteúdo secreto")
    ck.post(f"/notas/{note_id}/anexos", files=[("arquivos", ("plano-secreto.pdf", io.BytesIO(PDF)))])
    for url in ("/historico", "/gestor", "/demandas"):
        body = cb.get(url).text + ck.get(url).text
        assert "Segredo" not in body and "plano-secreto" not in body, url
    tv = ck.get("/api/tv").text
    assert "Segredo" not in tv and "plano-secreto" not in tv


def test_tv_never_reads_notes(env, db):
    ck, *_ = env
    new_note(ck)
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

    TestClient(create_app(Traced(db.path), clock=lambda: at(12)), base_url="http://hub-sala:8800").get("/api/tv")
    assert statements and not any("notes" in s for s in statements)


def test_autosave_returns_json(env):
    ck, _, db, kayo, _, _ = env
    note_id = new_note(ck)
    r = ck.post(f"/notas/{note_id}", data={"title": "Nova", "body": "digitando"}, headers={"X-Hub-Auto": "1"})
    assert r.status_code == 200 and r.json()["salvo"] == "12:00"
    assert notas.get_note(db, kayo, note_id).body == "digitando"
    r = ck.post(f"/notas/{note_id}", data={"title": "Nova", "body": "x" * 20001}, headers={"X-Hub-Auto": "1"})
    assert r.status_code == 422 and "muito longo" in r.json()["erro"]


def test_empty_title_becomes_sem_titulo(db):
    kayo = add_person(db, at(7), None, "Kayo")
    assert notas.create_note(db, at(8), kayo, "  ", "").title == "Sem título"


def test_pin_archive_search(env):
    ck, _, db, kayo, _, _ = env
    a = new_note(ck, "Antiga", "fornecedor X")
    b = new_note(ck, "Fixada", "y")
    ck.post(f"/notas/{b}/fixar")
    assert [n.title for n in notas.list_notes(db, kayo)][0] == "Fixada"
    ck.post(f"/notas/{a}/arquivar")
    assert "Antiga" not in ck.get("/notas").text
    assert "Antiga" in ck.get("/notas?aba=arquivadas").text
    assert "Antiga" in ck.get("/notas?q=fornecedor").text  # a busca acha as arquivadas também


def test_trash_restore_and_purge(env):
    ck, _, db, kayo, _, clock = env
    note_id = new_note(ck, "Apagar", "x")
    ck.post(f"/notas/{note_id}/anexos", files=[("arquivos", ("a.pdf", io.BytesIO(PDF)))])
    [a] = anexos.list_for(db, notas.KIND, note_id)
    ck.post(f"/notas/{note_id}/excluir")
    assert "Apagar" not in ck.get("/notas").text and "Apagar" in ck.get("/notas?aba=lixeira").text
    assert ck.get(f"/anexos/{a.id}").status_code == 404  # nota na lixeira: o arquivo não baixa
    ck.post(f"/notas/{note_id}/restaurar")
    assert "Apagar" in ck.get("/notas").text
    ck.post(f"/notas/{note_id}/excluir")
    assert notas.purge(db, at(12) + timedelta(days=29)) == 0
    assert notas.purge(db, at(12) + timedelta(days=31)) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    assert anexos.purge(db, at(12) + timedelta(days=31)) == 1
    assert not anexos.path_of(db, a).exists()


def test_note_files_only_for_the_owner_and_not_in_admin_trash(env):
    ck, cb, db, kayo, bianca, _ = env
    note_id = new_note(ck)
    ck.post(f"/notas/{note_id}/anexos", files=[("arquivos", ("meu-plano.pdf", io.BytesIO(PDF)))])
    [a] = anexos.list_for(db, notas.KIND, note_id)
    assert ck.get(f"/anexos/{a.id}").content == PDF
    assert cb.get(f"/anexos/{a.id}").status_code == 404
    ck.post(f"/notas/{note_id}/anexos/{a.id}/remover")
    assert "meu-plano" not in cb.get("/configuracoes").text  # a lixeira do administrador é só das demandas


def test_turn_into_demand_with_files(env):
    ck, _, db, kayo, _, _ = env
    note_id = new_note(ck, "Relatório novo", "Passos:\n1. puxar a 8081")
    ck.post(f"/notas/{note_id}/anexos", files=[("arquivos", ("rascunho.pdf", io.BytesIO(PDF)))])
    r = ck.post(f"/notas/{note_id}/virar-demanda", data={"copiar": "1"}, follow_redirects=False)
    demand_id = int(r.headers["location"].split("?")[0].rsplit("/", 1)[1])
    from hub.demands import find_demand
    d = find_demand(db, demand_id)
    assert d.title == "Relatório novo" and d.owner_id == kayo.id and "8081" in d.details
    [copy] = anexos.list_for(db, "demanda", d.id)
    assert copy.name == "rascunho.pdf" and anexos.path_of(db, copy).read_bytes() == PDF
    assert len(anexos.list_for(db, notas.KIND, note_id)) == 1  # a nota continua com o dela


def test_zip_export(env):
    ck, _, db, kayo, _, _ = env
    a = new_note(ck, "Ideias", "Comparar com setembro")
    new_note(ck, "Ideias", "outra com o mesmo título")
    ck.post(f"/notas/{a}/anexos", files=[("arquivos", ("plano.pdf", io.BytesIO(PDF)))])
    r = ck.get("/notas/baixar")
    assert r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"Ideias.txt", "Ideias (2).txt"} <= names
    assert any(n.endswith("arquivos/plano.pdf") for n in names)


def test_admin_erases_notes_of_someone_who_left(env):
    ck, cb, db, kayo, bianca, _ = env
    ana = add_person(db, at(7), None, "Ana Souza")
    notas.create_note(db, at(8), ana, "Da Ana", "x")
    with pytest.raises(ValidationError):
        notas.erase_person_notes(db, at(9), kayo, ana)  # ainda ativa
    deactivate_person(db, at(9), kayo.id, ana.id)
    html = ck.get("/pessoas").text
    assert "Ana Souza · 1 nota" in html and "Da Ana" not in html
    ck.post(f"/pessoas/{ana.id}/apagar-notas")
    assert notas.count_for(db, ana.id) == 0
