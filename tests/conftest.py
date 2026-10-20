from datetime import datetime

import pytest

from hub.db import Database


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "hub.db")
    d.init()
    return d


def at(h: int, m: int = 0, day: int = 19) -> datetime:
    """Horário em 2026-10 (19 = segunda-feira)."""
    return datetime(2026, 10, day, h, m)


@pytest.fixture(autouse=True)
def paineis_sem_segundo_plano(monkeypatch):
    """Nos testes, a leitura dos painéis acontece na hora (no Hub de verdade, em segundo plano)."""
    from hub import paineis

    monkeypatch.setattr(paineis, "BACKGROUND", False)
    monkeypatch.setattr(paineis, "_stores", {})
