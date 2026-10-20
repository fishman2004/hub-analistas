"""Fase 5: painéis de dados lidos das planilhas, com só porcentagens indo para a TV."""

import json
import logging
import os
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from conftest import at
from hub import paineis
from hub.access import create_pin
from hub.paineis import FILES_BY_KEY, Venda, compute_focos, compute_metas, panel_folder, store_for, workdays
from hub.people import ValidationError, add_person, get_person
from hub.planilhas import PlanilhaError, code, normalize, number, read_rows
from hub.telas import rotation
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
EXEMPLOS = Path(__file__).parent.parent / "tools" / "exemplos"
# 17/09/2026 é o último dia com venda nos exemplos; a TV "olha" no dia seguinte
NOW = datetime(2026, 9, 18, 9, 0)


def put_examples(db):
    folder = panel_folder(db)
    for f in EXEMPLOS.iterdir():
        shutil.copy(f, folder / f.name)  # copy (sem 2): data de modificação = agora
        os.utime(folder / f.name, (NOW.timestamp(), NOW.timestamp()))
    return folder


def screens(db, now=NOW):
    return {s["id"]: s for s in rotation(db, now)["screens"]}


# ---------- leitura das planilhas ----------

def test_csv_like_excel_saves_in_portuguese(tmp_path):
    f = tmp_path / "v.csv"
    f.write_bytes("Código;Positivação;Valor;Data\n 7 ;Sim;1.234,56;05/09/2026\n\n8;Não;;\n".encode("cp1252"))
    rows = read_rows(f, {"id": "CODIGO", "pos": "positivacao", "valor": "VALOR"})
    assert rows == [{"id": " 7 ", "pos": "Sim", "valor": "1.234,56"}, {"id": "8", "pos": "Não", "valor": ""}]
    assert number("1.234,56") == 1234.56 and number("") == 0 and number(12) == 12 and number("27.45") == 27.45
    assert code(" 7 ") == "7" and code(19143.0) == "19143" and code("45.0") == "45"
    assert normalize("  Meta   POSITIVAÇÃO ") == "META POSITIVACAO"
    with pytest.raises(PlanilhaError, match="não é número"):
        number("abc")


def test_csv_with_comma_and_utf8(tmp_path):
    f = tmp_path / "v.csv"
    f.write_text("ID,NOME\n1,Ação\n", encoding="utf-8-sig")
    assert read_rows(f, {"id": "ID", "nome": "NOME"}) == [{"id": "1", "nome": "Ação"}]


def test_missing_columns_and_bad_files(tmp_path):
    f = tmp_path / "v.csv"
    f.write_text("ID;OUTRA\n1;2\n", encoding="utf-8")
    with pytest.raises(PlanilhaError, match="Faltam as colunas: VALOR, DATA"):
        read_rows(f, {"id": "ID", "v": "VALOR", "d": "DATA"})
    empty = tmp_path / "vazio.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(PlanilhaError, match="vazio"):
        read_rows(empty, {"id": "ID"})
    broken = tmp_path / "quebrada.xlsx"
    broken.write_bytes(b"isto nao e um xlsx")
    with pytest.raises(PlanilhaError, match="Não consegui abrir"):
        read_rows(broken, {"id": "ID"})
    with pytest.raises(PlanilhaError, match="não é aceito"):
        read_rows(tmp_path / "x.xls", {"id": "ID"})


def test_xlsx_header_can_start_below_blank_rows(tmp_path):
    book = Workbook()
    sheet = book.active
    sheet.append([])
    sheet.append(["ID FORN", "META FINANCEIRA"])
    sheet.append([19143, 6301.5])
    book.save(tmp_path / "m.xlsx")
    assert read_rows(tmp_path / "m.xlsx", {"f": "ID FORN", "m": "META FINANCEIRA"}) == [{"f": 19143, "m": 6301.5}]


# ---------- cálculo ----------

FORN = {"1": ("GRUPO X", "A"), "2": ("GRUPO X", "A"), "3": ("GRUPO Y", "B")}  # 1 e 2 são divisões unificadas


def v(cliente, forn, dia, valor, produto="p"):
    return Venda(cliente, produto, forn, date(2026, 9, dia), valor)


def test_month_goals_by_folder_and_total():
    # setembro/2026 tem 26 dias de venda (segunda a sábado); até quinta 17/09 passaram 15 (58%)
    assert len(workdays(2026, 9)) == 26
    metas = [("10", "1", 1000, 4), ("11", "1", 1000, 4), ("10", "3", 2000, 2), ("10", "99", 500, 1)]
    vendas = [
        v("c1", "1", 1, 300), v("c1", "2", 2, 200),  # mesmo cliente no fornecedor unificado X: positiva 1 vez
        v("c1", "1", 3, 100),                         # voltou no cliente: não positiva de novo
        v("c4", "1", 17, 60),
        v("c1", "3", 10, 100),                        # o mesmo cliente no fornecedor Y conta para Y
        v("c2", "3", 17, 500), v("c3", "3", 17, 500),
        v("c9", "77", 17, 999),                       # fornecedor fora da planilha: não conta
        Venda("c1", "p", "1", date(2026, 8, 31), 5000),  # mês anterior: não conta
    ]
    m = compute_metas(FORN, metas, vendas)
    assert m["last_day"] == date(2026, 9, 17) and m["expected"] == 58 and m["is_workday"]
    fin = {c["pasta"]: c["pct"] for c in m["financeiro"]["mes"]}
    assert fin == {"A": 33, "B": 55, "T": 44}  # A: 660/2000, B: 1100/2000, T: 1760/4000
    pos = {c["pasta"]: c["pct"] for c in m["positivacao"]["mes"]}
    assert pos == {"A": 25, "B": 150, "T": 50}  # A: 2 clientes de X / 8, B: 3 de Y / 2, T: 5/10
    # cor do mês = ritmo: B fez 55% com 58% esperado (95% do ritmo); A fez 33% (57%); T 44% (76%)
    tiers = {c["pasta"]: c["tier"] for c in m["financeiro"]["mes"]}
    assert tiers == {"A": "critico", "B": "atencao", "T": "alerta"}
    # meta do dia = meta do mês / 26 dias de venda
    dia = {c["pasta"]: c["pct"] for c in m["financeiro"]["dia"]}
    assert dia == {"T": 689, "A": 78, "B": 1300}
    assert [c["pasta"] for c in m["financeiro"]["dia"]] == ["T", "A", "B"]
    # positivação do dia = clientes positivados pela primeira vez no mês naquele dia
    pos_dia = {c["pasta"]: c["pct"] for c in m["positivacao"]["dia"]}
    assert pos_dia == {"T": 780, "A": 325, "B": 2600}  # A: c4 (1 de 8/26), B: c2 e c3 (2 de 2/26)
    assert len(m["warnings"]) == 2  # meta e venda de fornecedores fora da planilha
    evo = {e["dia"]: e for e in m["evolucao"]}
    assert len(evo) == 30 and evo[17]["real"] == 44 and evo[17]["meta"] == 58 and evo[18]["real"] is None
    assert evo[1]["real"] == 8 and evo[5]["util"] is True  # sábado é dia de venda
    assert evo[6]["util"] is False and evo[6]["meta"] == evo[5]["meta"]  # domingo não
    assert evo[30]["meta"] == 100 and evo[18]["tier"] == "futuro"


def test_saturday_has_daily_goal_sunday_does_not():
    m = compute_metas(FORN, [("10", "1", 2600, 4)], [v("c1", "1", 19, 50)])  # 19/09 é sábado
    assert m["is_workday"] and m["financeiro"]["dia"][0]["pct"] == 50
    m = compute_metas(FORN, [("10", "1", 1000, 4)], [v("c1", "1", 20, 100)])  # 20/09 é domingo
    assert not m["is_workday"]
    assert all(c["pct"] is None and c["tier"] == "sem-meta" for c in m["financeiro"]["dia"])


def test_focus_products_positivation_and_financial_goal():
    focos = {"p1": "PILHAS", "p2": "PILHAS", "p3": "HIGIENE"}
    # META = positivação (clientes); META II = financeiro
    metas = [("10", "PILHAS", "VAREJO", 4, 600), ("11", "Pilhas", "VAREJO", 6, 0), ("10", "HIGIENE", "VAREJO", 5, 0),
             ("10", "SEM PRODUTO", "FARMA", 2, 0)]
    vendas = [v("c1", "1", 1, 100, "p1"), v("c1", "1", 2, 50, "p2"), v("c1", "1", 2, 30, "p1"),
              v("c2", "1", 3, 40, "p3"), v("c3", "1", 17, 1, "x")]
    f = compute_focos(focos, metas, vendas)
    rows = {r["nome"]: r for r in f["focos"]}
    assert rows["PILHAS"]["pos"] == 10 and rows["PILHAS"]["fin"] == 30  # 1 cliente de 10; 180 de 600
    assert rows["HIGIENE"]["pos"] == 20 and rows["HIGIENE"]["fin"] is None  # sem META II
    assert rows["SEM PRODUTO"]["pos"] == 0
    assert [r["nome"] for r in f["focos"]] == ["HIGIENE", "PILHAS", "SEM PRODUTO"]
    assert f["warnings"] == ["1 produto(s) foco sem nenhum produto na planilha de produtos foco."]


# ---------- da pasta até a TV ----------

def walk(value, path=""):
    if isinstance(value, dict):
        for k, item in value.items():
            yield from walk(item, f"{path}.{k}")
    elif isinstance(value, list):
        for item in value:
            yield from walk(item, path + "[]")
    else:
        yield path, value


def test_examples_reach_the_tv_with_percentages_only(db):
    assert not {"metas-mes", "metas-dia", "produtos-foco"} & set(screens(db))  # pasta vazia: fora da rotação
    put_examples(db)
    data = screens(db)
    assert {"metas-mes", "metas-dia", "produtos-foco"} <= set(data)
    mes = data["metas-mes"]["data"]
    assert mes["mes"] == "Setembro de 2026" and mes["ate"] == "17/09" and mes["dia_semana"] == "quinta"
    assert mes["atualizado"] == "09:00" and mes["velho"] is False and mes["esperado"] == 58
    assert [c["pasta"] for c in mes["financeiro"]] == list("ABCDEFG") + ["T"]
    # nenhum valor em reais, quantidade ou nome de vendedor/cliente: só %, letras das pastas e textos fixos
    allowed_numbers = {"pct", "esperado", "meta", "real", "dia", "pos", "fin"}
    for sid in ("metas-mes", "metas-dia", "produtos-foco"):
        for path, value in walk(data[sid]["data"]):
            key = path.rsplit(".", 1)[-1].removesuffix("[]")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert key in allowed_numbers and isinstance(value, int), path
    body = json.dumps(rotation(db, NOW))
    for secret in ("VENDEDOR", "CLIENTE", "SUPERVISOR", "FORNECEDOR", "PRODUTO 0", "31000"):
        assert secret not in body


def test_tv_endpoint_carries_panels(db):
    put_examples(db)
    app = create_app(db, clock=lambda: NOW)
    data = TestClient(app, base_url=BASE).get("/api/tv").json()
    assert {"metas-mes", "metas-dia", "produtos-foco"} <= {s["id"] for s in data["screens"]}
    html = TestClient(app, base_url=BASE).get("/tv").text
    assert "/static/tv-paineis.js" in html


def test_changed_file_is_reread_and_broken_file_only_drops_its_screens(db, caplog):
    folder = put_examples(db)
    store = store_for(db)
    first = store.get()
    assert store.get() is first  # nada mudou: não relê
    focos = folder / (FILES_BY_KEY["focos"].base + ".xlsx")
    focos.write_bytes(b"arquivo salvo pela metade")
    with caplog.at_level(logging.WARNING, logger="hub.paineis"):
        data = screens(db)
    assert "produtos-foco" not in data and "metas-mes" in data  # só a tela que usa o arquivo sai
    assert "Produtos Focos" in caplog.text
    snap = store.get()
    assert not snap.status("focos").ok and "Não consegui abrir" in snap.status("focos").error
    assert snap.status("vendas").ok and snap.status("vendas").rows > 1000
    shutil.copy(EXEMPLOS / focos.name, focos)
    assert "produtos-foco" in screens(db)


def test_missing_file_and_stale_warning(db):
    folder = put_examples(db)
    assert screens(db, datetime(2026, 9, 19, 10, 0))["metas-mes"]["data"]["velho"] is True  # mais de 24 h
    (folder / (FILES_BY_KEY["metas"].base + ".xlsx")).unlink()
    data = screens(db)
    assert "metas-mes" not in data and "metas-dia" not in data and "produtos-foco" in data
    assert store_for(db).get().status("metas").error == "Arquivo não encontrado na pasta."


def test_total_row_without_date_and_unreachable_folder(db, tmp_path):
    folder = put_examples(db)
    sales = folder / (FILES_BY_KEY["vendas"].base + ".csv")
    with open(sales, "a", encoding="cp1252") as f:
        f.write(";;;;;;;;;;;;;;999999,00;\n")  # linha de total que algumas exportações trazem no fim
    assert "metas-mes" in screens(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO settings(key, value) VALUES ('paineis.pasta', ?)", (str(tmp_path / "rede-fora"),))
    assert not {"metas-mes", "produtos-foco"} & set(screens(db))
    assert store_for(db).get().status("vendas").error == "Não consegui abrir a pasta."


# ---------- páginas: painéis, envio e configurações ----------

@pytest.fixture
def people(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bia = add_person(db, at(7), None, "Bia")
    create_pin(db, at(7), kayo.id, "1234", "1234")  # administrador
    create_pin(db, at(7), bia.id, "1234", "1234")
    app = create_app(db, clock=lambda: NOW)
    return get_person(db, kayo.id), get_person(db, bia.id), app


def login(app, person):
    c = TestClient(app, base_url=BASE)
    c.post(f"/entrar/{person.id}", data={"pin": "1234"})
    return c


def test_panels_page_shows_each_file(db, people):
    kayo, bia, app = people
    put_examples(db)
    html = login(app, bia).get("/paineis").text
    assert str(panel_folder(db)) in html and "Lida (" in html
    assert "(DADOS) - 8081 - Vendas" in html and 'href="/paineis"' in html
    assert "/paineis/enviar/" not in html  # analista não envia arquivo
    assert "/paineis/enviar/vendas" in login(app, kayo).get("/paineis").text


def test_upload_replaces_file_with_the_right_name(db, people):
    kayo, bia, app = people
    folder = panel_folder(db)
    (folder / (FILES_BY_KEY["vendas"].base + ".xlsx")).write_bytes(b"velho")
    csv_bytes = (EXEMPLOS / (FILES_BY_KEY["vendas"].base + ".csv")).read_bytes()
    files = {"arquivo": ("8081.csv", csv_bytes, "text/csv")}
    assert login(app, bia).post("/paineis/enviar/vendas", files=files).status_code == 403
    admin = login(app, kayo)
    r = admin.post("/paineis/enviar/vendas", files=files, follow_redirects=False)
    assert r.status_code == 303
    assert (folder / (FILES_BY_KEY["vendas"].base + ".csv")).read_bytes() == csv_bytes
    assert not (folder / (FILES_BY_KEY["vendas"].base + ".xlsx")).exists()  # o antigo, em outro formato, sai
    assert not list(folder.glob("*.enviando"))
    r = admin.post("/paineis/enviar/vendas", files={"arquivo": ("vendas.pdf", b"x", "application/pdf")})
    assert r.status_code == 422 and ".xlsx, .xlsm, .csv" in r.text
    assert admin.post("/paineis/enviar/outra", files=files).status_code == 422
    assert "enviou a planilha “Vendas (8081)”" in admin.get("/historico?de=2026-09-18&ate=2026-09-18").text


def test_panel_settings(db, people, tmp_path):
    kayo, bia, app = people
    other = tmp_path / "rede"
    other.mkdir()
    assert login(app, bia).post("/configuracoes/paineis", data={"pasta": str(other), "horas": "48"}).status_code == 403
    admin = login(app, kayo)
    r = admin.post("/configuracoes/paineis", data={"pasta": str(tmp_path / "nao-existe"), "horas": "48"})
    assert r.status_code == 422 and "Não encontrei a pasta" in r.text
    r = admin.post("/configuracoes/paineis", data={"pasta": str(other), "horas": "500"})
    assert r.status_code == 422 and "de 1 a 168 horas" in r.text
    r = admin.post("/configuracoes/paineis", data={"pasta": f'"{other}"', "horas": "48"})
    assert r.status_code == 200 and "Salvo" in r.text
    assert panel_folder(db) == other and paineis.stale_hours(db) == 48
    admin.post("/configuracoes/paineis", data={"pasta": "", "horas": "24"})
    assert panel_folder(db) == db.path.parent / "Painéis"
    with pytest.raises(PermissionError):
        paineis.save_panel_config(db, NOW, bia, "", "24")
    with pytest.raises(ValidationError):
        paineis.save_panel_config(db, NOW, kayo, "", "0")
