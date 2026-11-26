import socket
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

import hub.__main__ as entry
from conftest import at
from hub import winsys
from hub.backup import make_backup
from hub.people import add_person


def test_backup_creates_readable_copy_and_keeps_14(db, tmp_path):
    add_person(db, at(8), None, "Kayo")
    dest = tmp_path / "copias"
    for i in range(16):
        make_backup(db.path, dest, date(2026, 10, 1) + timedelta(days=i))
    files = sorted(p.name for p in dest.glob("hub-*.db"))
    assert len(files) == 14 and files[0] == "hub-2026-10-03.db" and files[-1] == "hub-2026-10-16.db"
    with sqlite3.connect(dest / "hub-2026-10-16.db") as conn:
        assert conn.execute("SELECT name FROM people").fetchone()[0] == "Kayo"


def test_same_day_backup_is_overwritten(db, tmp_path):
    make_backup(db.path, tmp_path, date(2026, 10, 19))
    make_backup(db.path, tmp_path, date(2026, 10, 19))
    assert len(list(tmp_path.glob("hub-*.db"))) == 1


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_port_cannot_be_taken_twice():
    port = free_port()
    first = entry.acquire_port(port)
    try:
        assert first is not None and entry.acquire_port(port) is None
    finally:
        first.close()


def test_server_config_without_console(monkeypatch):
    from fastapi import FastAPI

    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    entry.server_config(FastAPI())


def test_second_instance_only_opens_tv(monkeypatch, tmp_path):
    port = free_port()
    holder = entry.acquire_port(port)
    opened, dbs = [], []
    monkeypatch.setattr(entry, "PORT", port)
    monkeypatch.setattr(entry, "running_version", lambda p: entry.__version__)
    monkeypatch.setattr(entry, "open_tv", lambda url: opened.append(url))
    monkeypatch.setattr(entry, "Database", lambda *a, **k: dbs.append(1))
    monkeypatch.setenv("HUB_DADOS", str(tmp_path))
    try:
        entry.main()
    finally:
        holder.close()
    assert opened == [f"http://127.0.0.1:{port}/tv"] and dbs == []


def test_old_hub_left_open_is_replaced(monkeypatch):
    # o Hub antigo continuou aberto depois de atualizar: o iniciar.bat fecha ele e fica com a porta
    port = free_port()
    holder = entry.acquire_port(port)
    stopped = []

    def stop(p):
        stopped.append(p)
        holder.close()

    monkeypatch.setattr(entry, "running_version", lambda p: "1.20.0")
    monkeypatch.setattr(entry, "stop_hub_on_port", stop)
    sock = entry.replace_old_hub(port, wait_seconds=5)
    try:
        assert stopped == [port] and sock is not None
    finally:
        sock and sock.close()


def test_same_version_is_left_alone(monkeypatch):
    stopped = []
    monkeypatch.setattr(entry, "running_version", lambda p: entry.__version__)
    monkeypatch.setattr(entry, "stop_hub_on_port", lambda p: stopped.append(p))
    assert entry.replace_old_hub(free_port()) is None and stopped == []


def test_running_version_reads_versao_and_old_hub_is_none(db):
    import threading

    import uvicorn
    from fastapi import FastAPI

    from hub.web.app import create_app

    for app, expected in ((create_app(db), entry.__version__), (FastAPI(), None)):
        port = free_port()
        server = uvicorn.Server(uvicorn.Config(app, port=port, log_config=None, log_level="error"))
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        try:
            assert entry.running_version(port, tries=20, wait=0.25) == expected
        finally:
            server.should_exit = True
            t.join(5)


# o atalho é gravado na codificação do Prompt ("oem"), que só existe no Windows
@pytest.mark.skipif(sys.platform != "win32", reason="só no Windows")
def test_start_with_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    winsys.set_start_with_windows(True, Path(r"C:\Users\usuario\Área de Trabalho\hub-analistas"))
    f = winsys.startup_file()
    assert f.name == "Hub.cmd" and "Área de Trabalho" in f.read_text(encoding="oem")
    winsys.set_start_with_windows(False, Path("x"))
    assert not f.exists()
