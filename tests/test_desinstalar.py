"""desinstalar.bat: a parte em Python (cópia dos dados, pastas de fora e apagar com segurança)."""

import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from hub import desinstalar
from hub.db import Database, put_setting

AGORA = datetime(2026, 11, 26, 9, 5)


@pytest.fixture
def dados(tmp_path, monkeypatch):
    pasta = tmp_path / "Hub"
    pasta.mkdir()
    monkeypatch.setenv("HUB_DADOS", str(pasta))
    db = Database(pasta / "hub.db")
    db.init()
    (pasta / "copias").mkdir()
    (pasta / "copias" / "hub-2026-11-25.db").write_bytes(b"copia")
    (pasta / "Anexos" / "2026-11").mkdir(parents=True)
    (pasta / "Anexos" / "2026-11" / "abc").write_bytes(b"anexo")
    (pasta / "hub.log").write_text("log", encoding="utf-8")
    return pasta, db


def test_copia_tem_o_banco_inteiro_mesmo_com_wal(dados, tmp_path):
    pasta, db = dados
    # deixa uma gravação só no -wal (conexão aberta, sem checkpoint)
    conn = sqlite3.connect(pasta / "hub.db")
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("INSERT INTO settings (key, value) VALUES ('teste', 'no-wal')")
    conn.commit()
    assert (pasta / "hub.db-wal").exists()

    zip_path = desinstalar.make_backup_zip(pasta, tmp_path / "Desktop", AGORA)
    conn.close()

    assert zip_path.name == "Hub - copia 2026-11-26 0905.zip"
    with zipfile.ZipFile(zip_path) as zf:
        nomes = set(zf.namelist())
        assert {"hub.db", "hub.log", "copias/hub-2026-11-25.db", "Anexos/2026-11/abc"} <= nomes
        assert not {"hub.db-wal", "hub.db-shm"} & nomes
        (tmp_path / "x").mkdir()
        zf.extract("hub.db", tmp_path / "x")
    restaurado = sqlite3.connect(tmp_path / "x" / "hub.db")
    assert restaurado.execute("SELECT value FROM settings WHERE key = 'teste'").fetchone() == ("no-wal",)
    restaurado.close()


def test_copia_nao_sobrescreve_outra_do_mesmo_minuto(dados, tmp_path):
    pasta, _ = dados
    a = desinstalar.make_backup_zip(pasta, tmp_path / "Desktop", AGORA)
    b = desinstalar.make_backup_zip(pasta, tmp_path / "Desktop", AGORA)
    assert a != b and a.exists() and b.exists()
    assert not list((tmp_path / "Desktop").glob("*.gravando"))


def test_pastas_escolhidas_fora_dos_dados_sao_avisadas(dados, tmp_path):
    pasta, db = dados
    with db.connect() as conn:
        put_setting(conn, "paineis.pasta", str(tmp_path / "rede" / "Paineis"))
        put_setting(conn, "anexos.pasta", str(pasta / "Anexos"))  # dentro dos dados: vai junto
    fora = desinstalar.external_folders(pasta)
    assert fora == [("Planilhas dos painéis", tmp_path / "rede" / "Paineis")]


def test_apagar_dados(dados, capsys):
    pasta, _ = dados
    assert desinstalar.main(["apagar-dados"]) == 0
    assert not pasta.exists()
    assert desinstalar.main(["apagar-dados"]) == 0
    assert "Nao havia dados" in capsys.readouterr().out


def test_apagar_recusa_pasta_que_nao_e_do_hub(tmp_path, monkeypatch):
    outra = tmp_path / "Documentos"
    outra.mkdir()
    (outra / "planilha.xlsx").write_bytes(b"x")
    monkeypatch.setenv("HUB_DADOS", str(outra))
    assert desinstalar.main(["apagar-dados"]) == 1
    assert (outra / "planilha.xlsx").exists()
    with pytest.raises(ValueError):
        desinstalar.remove_data(Path.home())


def test_info_e_copia_pela_linha_de_comando(dados, tmp_path, monkeypatch, capsys):
    pasta, _ = dados
    monkeypatch.setattr(desinstalar, "desktop_dir", lambda: tmp_path / "Desktop")
    assert desinstalar.main(["info"]) == 0
    assert str(pasta) in capsys.readouterr().out
    assert desinstalar.main(["copia"]) == 0
    assert len(list((tmp_path / "Desktop").glob("Hub - copia *.zip"))) == 1
    assert desinstalar.main([]) == 2


def test_copia_sem_pasta_de_dados_falha_sem_criar_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("HUB_DADOS", str(tmp_path / "nao-existe"))
    monkeypatch.setattr(desinstalar, "desktop_dir", lambda: tmp_path / "Desktop")
    assert desinstalar.main(["copia"]) == 1
    assert not (tmp_path / "nao-existe").exists()


def test_desinstalar_bat_e_ascii_com_crlf():
    bat = Path(__file__).resolve().parent.parent / "desinstalar.bat"
    raw = bat.read_bytes()
    raw.decode("ascii")  # o cmd.exe lê na página de código OEM: nada de acentos
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    texto = raw.decode("ascii")
    assert "hub.desinstalar copia" in texto and "Startup\\Hub.cmd" in texto
