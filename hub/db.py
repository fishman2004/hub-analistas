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
    (3, """
        -- v2 · TV em rotação: configurações do Hub (tempo de cada tela etc.), só o que mudou do padrão
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """),
    (4, """
        -- v2 · banco de horas: saldo base de cada pessoa (do RH, pelo gestor) e a entrada e saída de cada dia
        CREATE TABLE hours_balance (
            person_id INTEGER PRIMARY KEY REFERENCES people(id),
            minutes INTEGER NOT NULL,
            as_of TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by INTEGER REFERENCES people(id)
        );
        CREATE TABLE hours_entries (
            id INTEGER PRIMARY KEY,
            person_id INTEGER NOT NULL REFERENCES people(id),
            day TEXT NOT NULL,
            entrada TEXT NOT NULL,
            saida TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (person_id, day)
        );
    """),
    (5, """
        -- v2 · rotinas com horário: o cadastro, a demanda de cada dia (uma só por rotina) e as pastas marcadas
        CREATE TABLE routines (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            weekdays TEXT NOT NULL,              -- "0,1,2,3,4": segunda = 0 ... domingo = 6
            starts_at TEXT NOT NULL,             -- "HH:MM": quando o cartão aparece e a TV avisa
            deadline TEXT,                       -- "HH:MM" ou vazio: depois disso, atrasada
            owner_id INTEGER NOT NULL REFERENCES people(id),
            folders TEXT NOT NULL DEFAULT '',    -- pastas que marcam, por exemplo "BCF"
            waits_for TEXT NOT NULL DEFAULT '',  -- rotinas que precisam terminar antes, "3,4"
            active INTEGER NOT NULL DEFAULT 1
        );
        ALTER TABLE demands ADD COLUMN routine_id INTEGER REFERENCES routines(id);
        ALTER TABLE demands ADD COLUMN routine_day TEXT;
        CREATE UNIQUE INDEX demands_routine_day ON demands(routine_id, routine_day);
        CREATE TABLE routine_folders (
            demand_id INTEGER NOT NULL REFERENCES demands(id),
            folder TEXT NOT NULL,
            person_id INTEGER REFERENCES people(id),
            at TEXT NOT NULL,
            PRIMARY KEY (demand_id, folder)
        );
    """),
    (6, """
        -- v2 · prioridades do início do mês: a lista de cada mês (AAAA-MM), o prazo (dia do mês, opcional),
        -- quem criou, quem fez e quando. Remover só marca deleted = 1: o item continua guardado.
        CREATE TABLE priorities (
            id INTEGER PRIMARY KEY,
            month TEXT NOT NULL,
            title TEXT NOT NULL,
            folder TEXT,
            due_day INTEGER,
            position INTEGER NOT NULL,
            created_by INTEGER REFERENCES people(id),
            created_at TEXT NOT NULL,
            done_by INTEGER REFERENCES people(id),
            done_at TEXT,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX priorities_month ON priorities(month);
    """),
    (7, """
        -- v3 · demandas com detalhes e anexos. O arquivo fica na pasta Anexos (%LOCALAPPDATA%\\Hub\\Anexos),
        -- nunca no banco; aqui só o nome original, onde está, o tamanho e quem enviou. Remover só marca.
        ALTER TABLE demands ADD COLUMN details TEXT;
        CREATE TABLE attachments (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,                           -- 'demanda' (e 'nota', na fase 12)
            parent_id INTEGER NOT NULL,                   -- id da demanda (ou da nota)
            name TEXT NOT NULL,                           -- nome original, para mostrar e baixar
            stored TEXT NOT NULL UNIQUE,                  -- caminho dentro da pasta Anexos ("2026-10/ab12...")
            size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            uploaded_by INTEGER REFERENCES people(id),
            uploaded_at TEXT NOT NULL,
            replaces INTEGER REFERENCES attachments(id),  -- nova versão de outro arquivo
            deleted_at TEXT,
            deleted_by INTEGER REFERENCES people(id),
            purged INTEGER NOT NULL DEFAULT 0             -- 1: o arquivo saiu da lixeira e foi apagado do disco
        );
        CREATE INDEX attachments_parent ON attachments(kind, parent_id);
    """),
    (8, """
        -- v3 · bloco de notas pessoal: só a dona vê (nem o gestor, nem os administradores) e nada vai para
        -- o histórico geral. Os arquivos usam a tabela attachments com kind = 'nota'.
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            person_id INTEGER NOT NULL REFERENCES people(id),
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            pinned INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT                   -- na lixeira; 30 dias depois a nota é apagada de vez
        );
        CREATE INDEX notes_person ON notes(person_id, updated_at);
    """),
    (9, """
        -- v3 · calendário: compromissos (com repetição simples, calculada na hora), quem participa,
        -- feriados (os nacionais são calculados; aqui ficam os da cidade e o liga/desliga dos nacionais)
        -- e ausências da equipe. Rotinas podem rodar também em feriado.
        CREATE TABLE events_cal (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,                          -- reuniao, entrega, treinamento, evento
            starts_on TEXT NOT NULL,                     -- AAAA-MM-DD
            ends_on TEXT,                                -- último dia, se durar mais de um
            starts_at TEXT, ends_at TEXT,                -- HH:MM; vazio = dia todo
            place TEXT, description TEXT,
            visibility TEXT NOT NULL DEFAULT 'equipe',   -- 'equipe' ou 'pessoal' (só quem criou)
            reserved INTEGER NOT NULL DEFAULT 0,
            repeat TEXT NOT NULL DEFAULT '',             -- '', semanal, mensal, anual
            created_by INTEGER REFERENCES people(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE event_people (
            event_id INTEGER NOT NULL REFERENCES events_cal(id),
            person_id INTEGER NOT NULL REFERENCES people(id),
            PRIMARY KEY (event_id, person_id)
        );
        CREATE TABLE holidays (
            day TEXT PRIMARY KEY,                        -- AAAA-MM-DD
            name TEXT NOT NULL,
            source TEXT NOT NULL,                        -- 'local' (cadastrado) ou 'nacional' (liga/desliga)
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE absences (
            id INTEGER PRIMARY KEY,
            person_id INTEGER NOT NULL REFERENCES people(id),
            starts_on TEXT NOT NULL,
            ends_on TEXT NOT NULL,
            reason TEXT,                                 -- só a pessoa e o gestor veem
            created_by INTEGER REFERENCES people(id),
            created_at TEXT NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        ALTER TABLE routines ADD COLUMN on_holidays INTEGER NOT NULL DEFAULT 0;
    """),
    (10, """
        -- v3 · modos da TV: cada modo é uma receita da rotação (telas, ordem, tempos e opções), com uma
        -- regra para ligar sozinho. O modo "Padrão" nasce das configurações da TV que já existiam
        -- (feito no primeiro uso, em hub/modos.py, porque os tempos padrão das telas estão no código).
        CREATE TABLE tv_modes (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            builtin TEXT UNIQUE,                         -- 'padrao', 'inicio-mes'...: os prontos não se apagam
            page_seconds INTEGER NOT NULL DEFAULT 10,
            sound INTEGER NOT NULL DEFAULT 1,            -- toca o som do aviso das rotinas
            hide_titles INTEGER NOT NULL DEFAULT 0,      -- cartões só com cor e iniciais
            rule TEXT NOT NULL DEFAULT '',               -- JSON: {"tipo": "primeiros_dias_uteis", "n": 5}...
            rule_on INTEGER NOT NULL DEFAULT 0,
            priority INTEGER NOT NULL,                   -- duas regras valendo: a de cima na lista vence
            created_by INTEGER REFERENCES people(id),
            updated_at TEXT NOT NULL
        );
        CREATE TABLE tv_mode_screens (
            mode_id INTEGER NOT NULL REFERENCES tv_modes(id) ON DELETE CASCADE,
            screen TEXT NOT NULL,                        -- id em hub/telas.py SCREENS
            position INTEGER NOT NULL,
            seconds INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (mode_id, screen)
        );
    """),
    (11, """
        -- v3 · prioridades por pasta: cada analista cuida das suas pastas e marca a prioridade do mês
        -- por pasta (e, num item com etapas, etapa por etapa). As marcas antigas (priorities.done_by/
        -- done_at) continuam valendo para o item todo.
        CREATE TABLE person_folders (
            person_id INTEGER NOT NULL REFERENCES people(id),
            folder TEXT NOT NULL,                        -- A a G
            PRIMARY KEY (person_id, folder)
        );
        CREATE TABLE priority_marks (
            priority_id INTEGER NOT NULL REFERENCES priorities(id),
            folder TEXT NOT NULL,
            step INTEGER NOT NULL DEFAULT 0,             -- a etapa (item sem etapas: sempre 0)
            done_by INTEGER REFERENCES people(id),
            done_at TEXT NOT NULL,
            PRIMARY KEY (priority_id, folder, step)
        );
        ALTER TABLE priorities ADD COLUMN steps TEXT NOT NULL DEFAULT '';  -- as etapas, uma por linha
    """),
    (12, """
        -- v4 · entrar pelo nome: quem não tem cadastro pede, já com o PIN (só o resumo), e um
        -- administrador aprova. Pedido não aprovado em 7 dias some.
        CREATE TABLE signup_requests (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            initials TEXT NOT NULL,
            pin_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
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


def get_setting(db: Database, key: str) -> str | None:
    """Uma configuração da tabela settings. None = não foi mudada (vale o padrão)."""
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def put_setting(conn: sqlite3.Connection, key: str, value: str | None) -> None:
    """Grava uma configuração; None apaga a linha e volta para o padrão."""
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


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
