"""Banco SQLite do Hub e o histórico de tudo o que acontece."""

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    initials TEXT NOT NULL,
    color TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS demands (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    owner_id INTEGER NOT NULL REFERENCES people(id),
    folder TEXT,
    requested_by TEXT,
    due TEXT,
    reserved INTEGER NOT NULL DEFAULT 0,
    column_ TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    done_at TEXT,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS presence (
    person_id INTEGER PRIMARY KEY REFERENCES people(id),
    status TEXT NOT NULL,
    since TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor_id INTEGER,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_at ON events(at);
"""

# Mudanças no banco depois da v1, em ordem. Cada uma roda uma vez só (o número fica no
# PRAGMA user_version), inteira ou nada, e só acrescenta: nunca apaga dados.
MIGRATIONS: list[tuple[int, str]] = [
    (1, """
        -- v2 · papéis e PIN: quem já existe vira analista sem PIN e cria o PIN no primeiro acesso
        ALTER TABLE people ADD COLUMN role TEXT NOT NULL DEFAULT 'analista';
        ALTER TABLE people ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE people ADD COLUMN pin_hash TEXT;
        ALTER TABLE people ADD COLUMN failed_pins INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE people ADD COLUMN locked_until TEXT;
        CREATE TABLE sessions (
            token_hash TEXT PRIMARY KEY,
            person_id INTEGER NOT NULL REFERENCES people(id),
            expires_at TEXT NOT NULL
        );
    """),
    (2, """
        -- v2 · demanda reservada: quem criou também vê o título (vem do histórico para as antigas)
        ALTER TABLE demands ADD COLUMN created_by INTEGER REFERENCES people(id);
        UPDATE demands SET created_by = (
            SELECT actor_id FROM events
            WHERE kind = 'demanda_criada' AND subject = 'demanda:' || demands.id
            ORDER BY id LIMIT 1
        );
    """),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Uma conexão por operação: grava tudo junto ou nada (rollback em erro)."""
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            # WAL: leituras (a TV) não esperam escritas (os analistas) e aguenta queda de energia melhor
            conn.execute("PRAGMA journal_mode = WAL")
            has_data = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'people'").fetchone() is not None
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            conn.executescript(SCHEMA)
        if version >= SCHEMA_VERSION:
            return
        if has_data:
            # banco de uma versão anterior: guarda uma cópia antes de mexer
            self.backup_before_migration(version)
        for number, sql in MIGRATIONS:
            if number > version:
                with self.connect() as conn:
                    conn.executescript(f"BEGIN; {sql}; PRAGMA user_version = {number}; COMMIT;")

    def backup_before_migration(self, version: int) -> Path:
        # nome fora do padrão hub-AAAA-MM-DD.db: a limpeza das cópias diárias não apaga esta
        dest = self.path.parent / "copias" / f"antes-da-v{version + 1}-{datetime.now():%Y%m%d-%H%M%S}.db"
        dest.parent.mkdir(parents=True, exist_ok=True)
        source, copy = sqlite3.connect(self.path), sqlite3.connect(dest)
        try:
            source.backup(copy)
        finally:
            copy.close()
            source.close()
        return dest


def log_event(conn: sqlite3.Connection, at: datetime, actor_id: int | None, kind: str, subject: str, detail: str) -> None:
    conn.execute(
        "INSERT INTO events(at, actor_id, kind, subject, detail) VALUES (?, ?, ?, ?, ?)",
        (at.isoformat(timespec="seconds"), actor_id, kind, subject, detail),
    )


def events(db: Database, start: date, end: date, person_id: int | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM events WHERE at >= ? AND at <= ?"
    args: list = [datetime.combine(start, time.min).isoformat(), datetime.combine(end, time.max).isoformat()]
    if person_id is not None:
        # quem fez, ou o dono da demanda citada
        sql += (" AND (actor_id = ? OR (subject LIKE 'demanda:%' AND "
                "CAST(substr(subject, 9) AS INTEGER) IN (SELECT id FROM demands WHERE owner_id = ?)))")
        args += [person_id, person_id]
    with db.connect() as conn:
        return conn.execute(sql + " ORDER BY at DESC, id DESC", args).fetchall()


def first_event_day(db: Database) -> date | None:
    """Dia do registro mais antigo do histórico (para abrir o histórico completo)."""
    with db.connect() as conn:
        first = conn.execute("SELECT MIN(at) FROM events").fetchone()[0]
    return datetime.fromisoformat(first).date() if first else None
