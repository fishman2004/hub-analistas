"""Fase 9: os envios do dia, lidos do histórico CSV que o Pombo grava, na TV e na página Envios."""

import csv
import json
import logging
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import envios
from hub.access import create_pin
from hub.envios import (COLUMNS, EnviosStore, history_folder, parse_line, read_history, run_time, runs_of_day,
                        save_pombo_config, status_text, store_for)
from hub.people import ValidationError, add_person, get_person
from hub.telas import rotation
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
NOW = at(12)  # segunda, 19/10/2026, 12:00


def line(when: datetime, run: str, canal="email", para="Gestão", status="enviado", detalhe="",
         envio="Vendas Diárias", envio_id="vendas", para_id=None, analista="Ana Souza") -> list[str]:
    """Uma linha do histórico, como o Pombo grava (pombo/history.py). Sem canal = linha da rodada inteira."""
    if para_id is None:
        para_id = ("list:" + para.lower().replace(" ", "-")) if canal else ""
    return [f"{when:%Y-%m-%d %H:%M:%S}", analista, envio, run, canal, para if canal else "", "Vendas.xlsx",
            status, detalhe, envio_id, para_id]


def write(root: Path, folder: str, lines: list[list[str]], month: str = "2026-10") -> Path:
    path = root / folder / f"{month}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        out = csv.writer(f)
        out.writerow(COLUMNS)
        out.writerows(lines)
    return path


def append(path: Path, lines: list[list[str]]) -> None:
    with path.open("a", encoding="utf-8", newline="") as f:  # o Pombo acrescenta sem BOM
        csv.writer(f).writerows(lines)


def day_runs(lines_by_folder: dict, now: datetime = NOW):
    rows = {folder: [parse_line(v) for v in lines] for folder, lines in lines_by_folder.items()}
    return runs_of_day(rows, now.date(), now)


R8, R9, R10 = "2026-10-19 08:00", "2026-10-19 09:00", "2026-10-19 10:00"


# ---------- leitura, igual à do Pombo ----------

def test_reads_the_history_like_the_pombo(tmp_path):
    path = write(tmp_path, "ana-souza", [
        line(at(8, 1), R8),
        # versão antiga do Pombo: sem a coluna destinatario_id no fim
        ["2026-10-19 08:02:00", "Ana Souza", "Vendas Diárias", R8, "whatsapp", "Comercial", "V.xlsx", "enviado", "", "vendas"],
        [],
        ["19/10/2026;lixo do Excel"],  # linha salva pelo Excel
        ["2026-10-19 08:0"],  # cortada numa queda de energia
        ["2026-10-19 08:05:00", "Ana Souza"],  # incompleta
        line(at(8, 3), R8, para="Supervisores") + ["coluna futura"],  # o Pombo só acrescenta colunas no fim
    ])
    with path.open("ab") as f:  # um byte que não é UTF-8 não derruba a leitura
        f.write("2026-10-19 08:04:00,Ana Souza,Relat\xf3rio,2026-10-19 08:00,email,Gestão,R.xlsx,enviado,,rel,list:l1\r\n"
                .encode("cp1252"))
    rows, skipped = read_history(path)
    assert len(rows) == 4 and skipped == 3
    assert rows[0].when == at(8, 1) and rows[0].target_key == "list:gestão" and rows[0].status == "enviado"
    assert rows[1].channel == "whatsapp" and rows[1].target_key == ""
    assert rows[2].target == "Supervisores" and rows[2].target_key == "list:supervisores"
    assert rows[3].dispatch_name.startswith("Relat") and rows[3].dispatch_id == "rel"


def test_run_labels():
    assert run_time("2026-10-19 08:00") == (at(8), False)
    assert run_time("manual 2026-10-19 09:12:03") == (datetime(2026, 10, 19, 9, 12, 3), True)
    assert run_time("qualquer coisa") == (None, False)


# ---------- cada rodada: enviado, falha, em andamento ----------

def test_all_sent_and_demo_count_as_success():
    [r] = day_runs({"ana-souza": [
        line(at(8, 1), R8, "email", "Gestão"),
        line(at(8, 1), R8, "whatsapp", "Comercial", "demonstracao", "modo demonstração: nada foi enviado"),
    ]})
    assert (r.state, r.group, r.sent, r.failed, r.total) == ("enviado", "ok", 2, 0, 2)
    assert r.channels == ["email", "whatsapp"] and r.scheduled == at(8) and not r.manual and r.hour == "08:00"
    assert status_text(r) == "✓ tudo enviado" and r.analyst == "Ana Souza"


def test_retries_follow_the_pombo():
    # falhou e depois saiu = enviado; 4 falhas no mesmo destinatário = 1 falha (o Pombo desiste depois de 4)
    lines = [line(at(9, 0), R9, "whatsapp", "Supervisores", "falhou", "tempo esgotado"),
             line(at(9, 5), R9, "whatsapp", "Supervisores", "enviado"),
             line(at(9, 0), R9, "email", "Gestão", "enviado")]
    lines += [line(at(9, m), R9, "whatsapp", "Norte", "falhou", f"tentativa {i}") for i, m in enumerate((0, 5, 10, 15), 1)]
    [r] = day_runs({"ana-souza": lines})
    assert (r.state, r.group, r.sent, r.failed, r.total) == ("parcial", "falha", 2, 1, 3)
    norte = next(t for t in r.targets if t.label == "Norte")
    assert (norte.state, norte.attempts, norte.detail) == ("falhou", 4, "tentativa 4")
    assert status_text(r) == "⚠ 1 falha"
    [r] = day_runs({"ana-souza": [line(at(9), R9, "email", "Gestão", "falhou", "caixa cheia"),
                                  line(at(9), R9, "email", "Diretoria", "falhou", "caixa cheia")]})
    assert (r.state, r.sent, r.failed) == ("falhou", 0, 2) and status_text(r) == "⚠ 2 falhas"


def test_recent_failure_is_still_being_retried():
    lines = [line(at(11, 58), "2026-10-19 11:58", "whatsapp", "Supervisores", "falhou", "tempo esgotado")]
    [r] = day_runs({"ana-souza": lines}, now=at(12))
    assert (r.state, r.group) == ("tentando", "andamento")  # o Pombo tenta de novo a cada 5 min
    assert status_text(r) == "↻ tentando de novo"
    [r] = day_runs({"ana-souza": lines}, now=at(12, 30))
    assert (r.state, r.group, r.failed) == ("falhou", "falha", 1)  # passou da hora e não tentou (Pombo fechado?)
    four = [line(at(11, m), "2026-10-19 11:40", "email", "Gestão", "falhou", "x") for m in (40, 45, 50, 55)]
    [r] = day_runs({"ana-souza": four}, now=at(11, 56))
    assert r.state == "falhou"  # 4 tentativas: o Pombo não tenta mais sozinho


def test_channel_down_and_whole_run_rows():
    waiting = [line(at(10), R10, "whatsapp", "Supervisores", "esperando", "WhatsApp desconectado")]
    [r] = day_runs({"ana-souza": waiting})
    assert (r.state, r.group, r.sent, r.total) == ("conexao", "andamento", 0, 1)
    assert status_text(r) == "⏳ esperando conexão"
    [r] = day_runs({"ana-souza": waiting + [line(at(10, 20), R10, "whatsapp", "Supervisores", "enviado")]})
    assert r.state == "enviado"
    # linhas da rodada inteira (sem canal): esperando a atualização do arquivo, desistiu, perdido
    file_wait = line(at(10), R10, "", "", "esperando", "Vendas.xlsx: não atualizado hoje (esperando até 11:00)")
    [r] = day_runs({"ana-souza": [file_wait]})
    assert (r.state, r.group, r.total) == ("esperando", "andamento", 0)
    assert r.detail == "Vendas.xlsx: não atualizado hoje (esperando até 11:00)" and r.channels == []
    assert status_text(r) == "⏳ esperando atualização"
    [r] = day_runs({"ana-souza": [file_wait, line(at(11), R10, "", "", "desistiu", "Vendas.xlsx: não atualizado hoje")]})
    assert (r.state, r.group, status_text(r)) == ("desistiu", "falha", "⚠ não atualizado")
    [r] = day_runs({"ana-souza": [line(at(12, 5), R10, "", "", "perdido", "programa fechado no horário")]})
    assert (r.state, r.group, status_text(r)) == ("perdido", "falha", "⚠ perdido")
    # algo enviado depois da espera vale mais que a espera (como na tela Hoje do Pombo)
    [r] = day_runs({"ana-souza": [file_wait, line(at(10, 30), R10, "email", "Gestão")]})
    assert r.state == "enviado"


def test_manual_send_covers_the_scheduled_run():
    manual = "manual 2026-10-19 09:12:03"
    runs = day_runs({"ana-souza": [
        line(at(8), R8, "", "", "esperando", "Vendas.xlsx: não atualizado hoje (esperando até 09:00)"),
        line(at(9), R8, "", "", "desistiu", "Vendas.xlsx: não atualizado hoje"),
        line(datetime(2026, 10, 19, 9, 12, 3), manual, "email", "Gestão"),
    ]})
    assert [(r.run, r.state, r.group) for r in runs] == [(R8, "manual", "ok"), (manual, "enviado", "ok")]
    assert status_text(runs[0]) == "✓ enviado às 09:12 (manual)"  # o "Enviar agora" cumpriu a rodada
    assert runs[1].manual and runs[1].hour == "09:12"


def test_recipients_are_matched_like_the_pombo():
    # linhas antigas, sem identificador: vale o nome
    old = [["2026-10-19 08:01:00", "Ana Souza", "Vendas", R8, "email", "Gestão", "V.xlsx", "falhou", "x", "vendas"],
           ["2026-10-19 08:06:00", "Ana Souza", "Vendas", R8, "email", "Gestão", "V.xlsx", "enviado", "", "vendas"]]
    [r] = day_runs({"ana-souza": old})
    assert (r.state, r.sent, r.total) == ("enviado", 1, 1)
    # mesmo nome, contatos diferentes: cada um tem a própria situação
    same_name = [line(at(8), R8, "email", "Supervisão", para_id="contact:c1"),
                 line(at(8), R8, "email", "Supervisão", "falhou", "caixa cheia", para_id="contact:c2")]
    [r] = day_runs({"ana-souza": same_name})
    assert (r.sent, r.failed, r.total) == (1, 1, 2)


def test_only_todays_runs_of_every_analyst_sorted_by_time():
    runs = day_runs({
        "ana-souza": [line(at(17, day=18), "2026-10-18 17:00", envio="Ontem"),
                      line(datetime(2026, 10, 19, 0, 4), "2026-10-18 23:55", envio="Virou o dia"),
                      line(at(14), "2026-10-19 14:00", envio="Plano", envio_id="plano"),
                      line(at(8), R8, envio="Vendas Diárias")],
        "carla-dias": [line(at(8), R8, envio="Vendas Diárias", analista="Carla Dias"),  # mesmo id em outro PC
                       line(at(14), "2026-10-19 14:00", envio="Cobertura", envio_id="cob", analista="Carla Dias")],
    })
    assert [(r.hour, r.dispatch_name, r.folder) for r in runs] == [
        ("08:00", "Vendas Diárias", "ana-souza"), ("08:00", "Vendas Diárias", "carla-dias"),
        ("14:00", "Cobertura", "carla-dias"), ("14:00", "Plano", "ana-souza")]


# ---------- pasta, cache e o que vai para a TV ----------

@pytest.fixture
def team(db):
    ana = add_person(db, at(7), None, "Ana Souza")
    bruno = add_person(db, at(7), None, "Bruno Reis")
    create_pin(db, at(7), ana.id, "1234", "1234")  # a primeira a criar o PIN vira administradora
    create_pin(db, at(7), bruno.id, "1234", "1234")
    app = create_app(db, clock=lambda: NOW)
    return get_person(db, ana.id), get_person(db, bruno.id), app


def login(app, person):
    c = TestClient(app, base_url=BASE)
    c.post(f"/entrar/{person.id}", data={"pin": "1234"})
    return c


def screens(db, now=NOW):
    return {s["id"]: s for s in rotation(db, now)["screens"]}


def sample(root: Path) -> Path:
    write(root, "ana-souza", [
        line(at(8, 1), R8, "email", "Gestão"),
        line(at(8, 1), R8, "whatsapp", "Comercial Vendas"),
        line(at(10), R10, "email", "Gestão", envio="Plano de Excelência", envio_id="plano"),
    ] + [line(at(10, m), R10, "whatsapp", "Supervisores Norte", "falhou", "SMTP 550 contato@exemplo.com",
              envio="Plano de Excelência", envio_id="plano") for m in (0, 5, 10, 15)])
    write(root, "carla-dias", [line(at(9), R9, envio="Positivação do dia", envio_id="pos", analista="Carla Dias"),
                               line(at(17, day=18), "2026-10-18 17:00", envio="Envio de ontem", analista="Carla Dias")])
    return root


def test_tv_screen_shows_todays_runs_without_recipients(db, team, tmp_path):
    ana, _, app = team
    assert "envios" not in screens(db)  # sem a pasta, a integração fica desligada
    root = sample(tmp_path / "historico")
    save_pombo_config(db, NOW, ana, str(root))
    data = screens(db)["envios"]["data"]
    assert data["atualizado"] == "12:00" and data["aviso"] == ""
    assert data["resumo"] == {"ok": 2, "falha": 1, "andamento": 0}
    first, carla, plano = data["rodadas"]
    assert first == {"hora": "08:00", "manual": False, "envio": "Vendas Diárias", "analista": "Ana Souza",
                     "iniciais": ana.initials, "cor": ana.color, "canal": "E-mail · WhatsApp", "grupo": "ok",
                     "situacao": "✓ tudo enviado", "contagem": "2 de 2 enviados"}
    assert (carla["analista"], carla["iniciais"], carla["cor"]) == ("Carla Dias", "CD", "")  # não está no Hub
    assert (plano["grupo"], plano["situacao"], plano["contagem"]) == ("falha", "⚠ 1 falha", "1 de 2 enviados")
    body = json.dumps(rotation(db, NOW), ensure_ascii=False)
    for secret in ("Gestão", "Supervisores Norte", "Comercial Vendas", "SMTP", "contato@exemplo.com", "Vendas.xlsx",
                   "Envio de ontem"):
        assert secret not in body  # destinatários, detalhes e arquivos ficam só no app
    tv = TestClient(app, base_url=BASE).get("/api/tv").json()
    assert "envios" in [s["id"] for s in tv["screens"]]


def test_screen_leaves_without_runs_today(db, team, tmp_path):
    ana, _, _ = team
    root = tmp_path / "historico"
    write(root, "ana-souza", [line(at(17, day=18), "2026-10-18 17:00")])
    save_pombo_config(db, NOW, ana, str(root))
    assert "envios" not in screens(db)  # só tem envio de ontem
    shutil.rmtree(root)  # a pasta sumiu
    snap = store_for(db).get(NOW, wait=True)
    assert snap.error.startswith("Não consegui abrir a pasta") and "envios" not in screens(db)


def test_offline_folder_keeps_the_last_reading_with_a_warning(db, team, tmp_path, caplog):
    ana, _, _ = team
    root = sample(tmp_path / "historico")
    save_pombo_config(db, NOW, ana, str(root))
    assert len(screens(db)["envios"]["data"]["rodadas"]) == 3
    root.rename(tmp_path / "fora")  # a pasta da rede caiu
    with caplog.at_level(logging.WARNING, logger="hub.envios"):
        data = screens(db, at(12, 5))["envios"]["data"]
        screens(db, at(12, 6))
    assert len(data["rodadas"]) == 3 and data["atualizado"] == "12:00" and "fora do ar" in data["aviso"]
    assert caplog.text.count("não consegui abrir a pasta") == 1  # vai uma vez para o hub.log, não a cada 5 s


def test_locked_file_keeps_the_last_good_rows(db, team, tmp_path, monkeypatch, caplog):
    ana, _, _ = team
    root = sample(tmp_path / "historico")
    save_pombo_config(db, NOW, ana, str(root))
    assert len(screens(db)["envios"]["data"]["rodadas"]) == 3
    path = root / "ana-souza" / "2026-10.csv"
    append(path, [line(at(11, 30), "2026-10-19 11:30", envio="Nova rodada", envio_id="nova")])
    locked = {"on": True}
    real_open = Path.open

    def excel_open(self, *args, **kwargs):  # o Excel abriu o CSV e não deixa ler
        if locked["on"] and self == path:
            raise PermissionError("arquivo em uso")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", excel_open)
    with caplog.at_level(logging.WARNING, logger="hub.envios"):
        snap = store_for(db).get(NOW, wait=True)
    status = next(f for f in snap.files if f.folder == "ana-souza")
    assert "aberto no Excel" in status.error and status.kept
    data = screens(db)["envios"]["data"]
    assert len(data["rodadas"]) == 3 and "Ana Souza" in data["aviso"]  # segue com a última leitura boa
    assert "2026-10.csv" in caplog.text
    locked["on"] = False
    assert len(screens(db)["envios"]["data"]["rodadas"]) == 4  # liberou: lê de novo


def test_reads_again_only_when_a_file_changes(db, team, tmp_path, monkeypatch):
    ana, _, _ = team
    root = sample(tmp_path / "historico")
    save_pombo_config(db, NOW, ana, str(root))
    calls = []
    real = envios.read_history
    monkeypatch.setattr(envios, "read_history", lambda path: calls.append(path.parent.name) or real(path))
    screens(db)
    screens(db)
    assert sorted(calls) == ["ana-souza", "carla-dias"]
    append(root / "carla-dias" / "2026-10.csv", [line(at(11), "2026-10-19 11:00", envio="Cobertura", envio_id="cob",
                                                      analista="Carla Dias")])
    assert len(screens(db)["envios"]["data"]["rodadas"]) == 4
    assert calls[2:] == ["carla-dias"]


def test_tv_never_waits_for_a_slow_folder(db, team, tmp_path, monkeypatch):
    ana, _, _ = team
    save_pombo_config(db, NOW, ana, str(sample(tmp_path / "historico")))
    release = threading.Event()
    real = envios.read_history

    def slow(path):  # pasta de rede lenta
        release.wait(5)
        return real(path)

    monkeypatch.setattr(envios, "read_history", slow)
    store = EnviosStore(db, background=True)
    started = time.monotonic()
    assert store.get(NOW) is None  # a primeira leitura ainda está em andamento: a TV segue sem a tela
    assert store.get(NOW) is None
    assert time.monotonic() - started < 1
    release.set()
    snap = store.get(NOW, wait=True)  # a página espera um pouco pela leitura
    assert snap is not None and sorted(snap.rows) == ["ana-souza", "carla-dias"]


# ---------- página Envios e Configurações ----------

def test_envios_page_shows_failures_and_files(db, team, tmp_path):
    ana, bruno, app = team
    assert TestClient(app, base_url=BASE).get("/envios", follow_redirects=False).status_code == 303
    html = login(app, bruno).get("/envios").text
    assert 'href="/envios"' in html and "desligada" in html
    root = sample(tmp_path / "historico")
    save_pombo_config(db, NOW, ana, str(root))
    html = login(app, bruno).get("/envios").text
    assert "Plano de Excelência" in html and "Supervisores Norte" in html and "4 tentativas" in html
    assert "SMTP 550 contato@exemplo.com" in html  # o detalhe da falha
    assert str(root) in html and "ana-souza" in html and "carla-dias" in html  # a situação de cada arquivo
    assert "Envio de ontem" not in html


def test_folder_of_a_single_analyst_gets_a_hint(db, team, tmp_path):
    ana, bruno, app = team
    root = sample(tmp_path / "historico")
    save_pombo_config(db, NOW, ana, str(root / "ana-souza"))  # escolheu a pasta de um analista só
    assert "a pasta de cima" in login(app, bruno).get("/envios").text


def test_pombo_folder_setting_is_admin_only(db, team, tmp_path):
    ana, bruno, app = team
    root = tmp_path / "historico"
    root.mkdir()
    assert login(app, bruno).post("/configuracoes/pombo", data={"pasta": str(root)}).status_code == 403
    admin = login(app, ana)
    assert "Pasta do histórico do Pombo" in admin.get("/configuracoes").text
    r = admin.post("/configuracoes/pombo", data={"pasta": str(tmp_path / "nao-existe")})
    assert r.status_code == 422 and "Não encontrei a pasta" in r.text
    r = admin.post("/configuracoes/pombo", data={"pasta": f'"{root}"'})
    assert r.status_code == 200 and "Salvo" in r.text and history_folder(db) == root
    admin.post("/configuracoes/pombo", data={"pasta": "  "})
    assert history_folder(db) is None  # em branco: integração desligada
    with pytest.raises(PermissionError):
        save_pombo_config(db, NOW, bruno, str(root))
    with pytest.raises(ValidationError):
        save_pombo_config(db, NOW, ana, str(root / "x"))
    assert "mudou a pasta do histórico do Pombo" in admin.get("/historico?de=2026-10-19&ate=2026-10-19").text
