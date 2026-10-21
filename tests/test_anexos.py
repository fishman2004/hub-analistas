"""Fase 11: detalhes, anexos das demandas, linha do tempo e busca."""

import io
import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import anexos
from hub.access import set_access
from hub.demands import create_demand, move_demand, search_demands, update_demand
from hub.people import ValidationError, add_person, get_person
from hub.web.app import create_app
from test_web_app import login

XLSX = b"PK\x03\x04" + b"planilha" * 100
PDF = b"%PDF-1.4 relatorio"


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DADOS", str(tmp_path / "dados"))


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    carla = add_person(db, at(7), None, "Carla")
    clock = {"now": at(12)}
    app = create_app(db, clock=lambda: clock["now"])
    clients = [TestClient(app, base_url="http://hub-sala:8800") for _ in range(3)]
    login(clients[0], kayo)
    login(clients[1], bianca)
    login(clients[2], carla)
    return clients, db, (kayo, bianca, carla), clock


def upload(c, ref, name, data, url=None):
    return c.post(url or f"/demandas/{ref}/anexos", files=[("arquivos", (name, io.BytesIO(data)))],
                  follow_redirects=False)


# ---------- módulo ----------

def test_save_keeps_name_only_in_the_database(db):
    kayo = add_person(db, at(7), None, "Kayo")
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    a = anexos.save(db, at(9), kayo, "demanda", d.id, "C:\\Users\\kayo\\..\\Metas outubro.xlsx", io.BytesIO(XLSX))
    assert a.name == "Metas outubro.xlsx" and a.size == len(XLSX)
    path = anexos.path_of(db, a)
    assert path.read_bytes() == XLSX and path.parent.name == "2026-10"
    assert "Metas" not in path.name and "." not in path.name  # nome aleatório, sem a extensão
    assert path.is_relative_to(anexos.folder(db))


@pytest.mark.parametrize("name, data, message", [
    ("macro.xlsm", XLSX, "não é aceito"),
    ("programa.exe", b"MZ", "não é aceito"),
    ("pagina.html", b"<script>", "não é aceito"),
    ("falso.pdf", b"MZ\x90\x00", "não parece"),
    ("vazio.csv", b"", "vazio"),
])
def test_refuses_bad_files(db, name, data, message):
    kayo = add_person(db, at(7), None, "Kayo")
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    with pytest.raises(ValidationError, match=message):
        anexos.save(db, at(9), kayo, "demanda", d.id, name, io.BytesIO(data))
    assert anexos.list_for(db, "demanda", d.id) == []
    assert not [p for p in anexos.folder(db).rglob("*") if p.is_file()]  # nada sobrou no disco


def test_size_and_count_limits(db, monkeypatch):
    kayo = add_person(db, at(7), None, "Kayo")
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    monkeypatch.setattr(anexos, "MAX_BYTES", 100)
    with pytest.raises(ValidationError, match="grande demais"):
        anexos.save(db, at(9), kayo, "demanda", d.id, "grande.csv", io.BytesIO(b"x" * 101))
    monkeypatch.setattr(anexos, "MAX_PER_PARENT", 2)
    for i in range(2):
        anexos.save(db, at(9), kayo, "demanda", d.id, f"a{i}.csv", io.BytesIO(b"x"))
    with pytest.raises(ValidationError, match="Remova algum"):
        anexos.save(db, at(9), kayo, "demanda", d.id, "a3.csv", io.BytesIO(b"x"))


def test_refuses_when_disk_is_almost_full(db, monkeypatch):
    kayo = add_person(db, at(7), None, "Kayo")
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    monkeypatch.setattr(anexos, "MIN_FREE_BYTES", 10 ** 18)
    with pytest.raises(ValidationError, match="quase cheio"):
        anexos.save(db, at(9), kayo, "demanda", d.id, "a.csv", io.BytesIO(b"x"))


def test_new_version_keeps_the_old_one_and_remove_takes_the_chain(db):
    kayo = add_person(db, at(7), None, "Kayo")
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    v1 = anexos.save(db, at(9), kayo, "demanda", d.id, "metas.xlsx", io.BytesIO(XLSX))
    v2 = anexos.save(db, at(10), kayo, "demanda", d.id, "metas v2.xlsx", io.BytesIO(XLSX + b"2"), replaces=v1.id)
    [current] = anexos.list_for(db, "demanda", d.id)
    assert current.id == v2.id and [o.id for o in current.versions] == [v1.id]
    assert anexos.get(db, v1.id) is not None  # a versão anterior continua baixando
    with pytest.raises(ValidationError):
        anexos.save(db, at(11), kayo, "demanda", d.id, "x.xlsx", io.BytesIO(XLSX), replaces=v1.id)
    anexos.remove(db, at(12), kayo, current)
    assert anexos.list_for(db, "demanda", d.id) == []
    assert anexos.get(db, v1.id) is None and anexos.get(db, v2.id) is None
    [trashed] = anexos.trash(db, at(13), "demanda")
    assert trashed.id == v2.id
    anexos.restore(db, at(13), kayo, trashed)
    assert [a.id for a in anexos.list_for(db, "demanda", d.id)] == [v2.id]
    assert anexos.get(db, v1.id) is not None


def test_purge_only_after_thirty_days(db):
    kayo = add_person(db, at(7), None, "Kayo")
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    a = anexos.save(db, at(9), kayo, "demanda", d.id, "a.pdf", io.BytesIO(PDF))
    anexos.remove(db, at(10), kayo, a)
    path = anexos.path_of(db, a)
    assert anexos.purge(db, at(10) + timedelta(days=29)) == 0 and path.exists()
    assert anexos.purge(db, at(10) + timedelta(days=31)) == 1 and not path.exists()
    assert anexos.trash(db, at(10) + timedelta(days=31), "demanda") == []
    with pytest.raises(ValidationError):
        anexos.restore(db, at(10) + timedelta(days=31), kayo, a)


# ---------- detalhes e histórico ----------

def test_details_and_changes_in_history(env):
    (c, *_), db, (kayo, bianca, _), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id, due=date(2026, 10, 22),
                      details="Ver a aba 2")
    assert d.details == "Ver a aba 2"
    update_demand(db, at(9), kayo.id, d.id, title="Relatório", owner_id=bianca.id, folder="B", requested_by=None,
                  due=date(2026, 10, 25), reserved=False, details="Ver a aba 3")
    hist = c.get("/historico").text
    assert "editou “Relatório”: dono Kayo → Bianca, pasta nenhuma → B, prazo 22/10 → 25/10, detalhes" in hist
    with pytest.raises(ValidationError, match="Detalhes muito longos"):
        update_demand(db, at(9), kayo.id, d.id, title="Relatório", owner_id=bianca.id, folder=None,
                      requested_by=None, due=None, reserved=False, details="x" * 4001)


def test_reserved_changes_and_file_names_are_hidden(env):
    (c_kayo, _, c_carla), db, (kayo, _, carla), _ = env
    d = create_demand(db, at(8), kayo.id, title="Comissões", owner_id=kayo.id, reserved=True)
    update_demand(db, at(9), kayo.id, d.id, title="Comissões RCA", owner_id=kayo.id, folder=None, requested_by=None,
                  due=date(2026, 10, 25), reserved=True)
    upload(c_kayo, d.id, "comissoes-rca.xlsx", XLSX)
    hist = c_carla.get("/historico").text
    assert "Comissões" not in hist and "comissoes-rca" not in hist and "um arquivo" in hist
    assert "prazo" not in hist
    assert "comissoes-rca.xlsx" in c_kayo.get("/historico").text


def test_demand_form_shows_details_files_and_timeline(env):
    (c, *_), db, (kayo, *_), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id, details="Ver a aba 2")
    upload(c, d.id, "metas.xlsx", XLSX)
    html = c.get(f"/demandas/{d.id}").text
    assert "Ver a aba 2" in html and "metas.xlsx" in html and "Linha do tempo" in html
    assert "anexou “metas.xlsx” em “Relatório”" in html


# ---------- rotas ----------

def test_upload_download_and_headers(env):
    (c_kayo, c_bianca, _), db, (kayo, *_), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    r = upload(c_kayo, d.id, "Relatório final.pdf", PDF)
    assert r.status_code == 303 and r.headers["location"].startswith(f"/demandas/{d.id}?ok=")
    [a] = anexos.list_for(db, "demanda", d.id)
    r = c_bianca.get(f"/anexos/{a.id}")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment;") and "Relat" in r.headers["content-disposition"]
    anon = TestClient(c_kayo.app, base_url="http://hub-sala:8800")
    assert anon.get(f"/anexos/{a.id}", follow_redirects=False).headers["location"] == "/entrar"


def test_reserved_files_only_for_who_sees_the_demand(env):
    (c_kayo, _, c_carla), db, (kayo, _, carla), _ = env
    d = create_demand(db, at(8), kayo.id, title="Comissões", owner_id=kayo.id, reserved=True)
    upload(c_kayo, d.id, "comissoes.xlsx", XLSX)
    [a] = anexos.list_for(db, "demanda", d.id)
    assert c_carla.get(f"/anexos/{a.id}").status_code == 404
    assert upload(c_carla, d.id, "x.xlsx", XLSX).status_code == 403


def test_anyone_who_sees_attaches_but_only_some_remove(env):
    (c_kayo, c_bianca, c_carla), db, (kayo, bianca, carla), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    upload(c_bianca, d.id, "da-bianca.csv", b"a;b")
    upload(c_kayo, d.id, "do-kayo.csv", b"a;b")
    files = {a.name: a for a in anexos.list_for(db, "demanda", d.id)}
    # Carla não anexou nem é dona: não remove
    assert c_carla.post(f"/demandas/{d.id}/anexos/{files['do-kayo.csv'].id}/remover").status_code == 403
    # Bianca remove o que ela anexou; o dono (Kayo) remove qualquer um
    assert c_bianca.post(f"/demandas/{d.id}/anexos/{files['da-bianca.csv'].id}/remover",
                         follow_redirects=False).status_code == 303
    assert c_kayo.post(f"/demandas/{d.id}/anexos/{files['do-kayo.csv'].id}/remover",
                       follow_redirects=False).status_code == 303
    assert anexos.list_for(db, "demanda", d.id) == []
    # gestor remove de qualquer um
    set_access(db, at(9), get_person(db, kayo.id), carla.id, "gestor", False)
    upload(c_bianca, d.id, "outro.csv", b"a;b")
    [a] = anexos.list_for(db, "demanda", d.id)
    assert c_carla.post(f"/demandas/{d.id}/anexos/{a.id}/remover", follow_redirects=False).status_code == 303


def test_new_version_route(env):
    (c, *_), db, (kayo, *_), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    upload(c, d.id, "metas.xlsx", XLSX)
    [a] = anexos.list_for(db, "demanda", d.id)
    r = upload(c, d.id, "metas.xlsx", XLSX + b"2", url=f"/demandas/{d.id}/anexos/{a.id}/versao")
    assert r.status_code == 303
    [b] = anexos.list_for(db, "demanda", d.id)
    assert b.replaces == a.id and len(b.versions) == 1
    assert "nova versão de “metas.xlsx”" in c.get("/historico").text


def test_refused_file_shows_the_reason(env):
    (c, *_), db, (kayo, *_), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    r = upload(c, d.id, "virus.exe", b"MZ")
    assert r.status_code == 422 and "não é aceito" in r.text


def test_new_demand_with_files(env):
    (c, *_), db, (kayo, *_), _ = env
    r = c.post("/demandas", data={"title": "Com arquivo", "owner_id": str(kayo.id), "details": "Leia o PDF"},
               files=[("arquivos", ("pedido.pdf", io.BytesIO(PDF)))], follow_redirects=False)
    assert r.status_code == 303
    [d] = search_demands(db, kayo, text="arquivo")
    assert d.details == "Leia o PDF" and [a.name for a in anexos.list_for(db, "demanda", d.id)] == ["pedido.pdf"]
    assert "📎 1" in c.get("/").text


def test_routine_card_becomes_demand_when_a_file_arrives(env):
    (c, *_), db, (kayo, *_), clock = env
    from hub.rotinas import save_routine
    set_access(db, at(7), get_person(db, kayo.id), kayo.id, "gestor", True)
    save_routine(db, at(7), get_person(db, kayo.id), None, name="PHD", weekdays=[0, 1, 2, 3, 4], starts_at="08:00",
                 deadline="", owner_id=kayo.id, folders=[], waits_for=[])
    ref = f"rotina-1-{clock['now'].date().isoformat()}"
    assert upload(c, ref, "phd.csv", b"a;b").status_code == 303
    [d] = search_demands(db, kayo, text="PHD")
    assert d.routine_id == 1 and len(anexos.list_for(db, "demanda", d.id)) == 1


def test_tv_never_reads_attachments_nor_details(env, db):
    (c, *_), _, (kayo, *_), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id, details="segredo da aba 2")
    upload(c, d.id, "metas-secretas.xlsx", XLSX)
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

    tv = TestClient(create_app(Traced(db.path), clock=lambda: at(12)), base_url="http://hub-sala:8800")
    body = tv.get("/api/tv").text
    assert statements and not any("attachments" in s for s in statements)
    assert "segredo" not in body and "metas-secretas" not in body and "📎" not in body


def test_concluding_offers_to_attach(env):
    (c, *_), db, (kayo, *_), _ = env
    d = create_demand(db, at(8), kayo.id, title="Relatório", owner_id=kayo.id)
    move_demand(db, at(9), kayo.id, d.id, "doing")
    r = c.post(f"/demandas/{d.id}/mover", data={"column": "done"}, headers={"referer": "http://hub-sala:8800/"},
               follow_redirects=False)
    assert r.headers["location"] == f"/?concluida={d.id}"
    assert "Anexar o arquivo final?" in c.get(r.headers["location"]).text


# ---------- busca ----------

def test_search_finds_old_done_demands_and_hides_reserved_text(env):
    (c_kayo, _, c_carla), db, (kayo, _, carla), clock = env
    old = create_demand(db, at(8, day=1), kayo.id, title="Campanha de setembro", owner_id=kayo.id,
                        details="planilha do fornecedor")
    move_demand(db, at(9, day=1), kayo.id, old.id, "done")
    create_demand(db, at(8), kayo.id, title="Comissões campanha", owner_id=kayo.id, reserved=True)
    html = c_kayo.get("/demandas?q=campanha").text
    assert "Campanha de setembro" in html and "Comissões campanha" in html and "Concluída em 01/10/2026" in html
    assert "Campanha de setembro" in c_kayo.get("/demandas?q=fornecedor").text
    html = c_carla.get("/demandas?q=campanha").text
    assert "Campanha de setembro" in html and "Comissões" not in html and "1 demanda" in html
    # sem texto, a reservada aparece mascarada
    html = c_carla.get("/demandas").text
    assert "Comissões" not in html and "Demanda reservada" in html


def test_search_filters(env):
    (c, *_), db, (kayo, bianca, _), _ = env
    a = create_demand(db, at(8), kayo.id, title="Pasta B", owner_id=bianca.id, folder="B")
    create_demand(db, at(8), kayo.id, title="Sem pasta", owner_id=kayo.id)
    anexos.save(db, at(9), kayo, "demanda", a.id, "a.csv", io.BytesIO(b"x"))
    assert "Sem pasta" not in c.get(f"/demandas?pessoa={bianca.id}").text
    assert "Sem pasta" not in c.get("/demandas?pasta=B").text
    html = c.get("/demandas?anexos=1").text
    assert "Pasta B" in html and "Sem pasta" not in html


def test_migration_7_from_a_1_1_0_database(tmp_path):
    from hub.db import MIGRATIONS, SCHEMA, Database
    path = tmp_path / "hub.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for number, sql in MIGRATIONS:
        if number <= 6:
            conn.executescript(sql)
    conn.execute("PRAGMA user_version = 6")
    conn.execute("INSERT INTO people(name, initials, color) VALUES ('Ana Souza', 'AS', '#7FB2E5')")
    conn.execute("INSERT INTO demands(title, owner_id, column_, created_at, updated_at) "
                 "VALUES ('Antiga', 1, 'todo', '2026-10-01T08:00:00', '2026-10-01T08:00:00')")
    conn.commit()
    conn.close()
    db = Database(path)
    db.init()
    with db.connect() as c:
        assert c.execute("SELECT details FROM demands").fetchone()[0] is None
        assert c.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 0
    assert list((tmp_path / "copias").glob("antes-da-v*.db"))
