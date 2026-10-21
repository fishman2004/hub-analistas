"""Bloco de notas pessoal (fase 12): cada pessoa vê só as próprias notas.

Ninguém mais abre uma nota: nem o gestor, nem os administradores (como no banco de horas, onde
até o administrador fica de fora). Por isso as notas também não entram no histórico geral, que
toda a equipe lê, e a TV nunca consulta a tabela. Os arquivos usam o módulo de anexos (kind 'nota').
Excluir manda para a lixeira; 30 dias depois a nota (com o texto) é apagada de vez.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import anexos
from .db import Database
from .people import Person, ValidationError

KIND = "nota"
MAX_TITLE = 120
MAX_BODY = 20_000
TRASH_DAYS = anexos.TRASH_DAYS
UNTITLED = "Sem título"


@dataclass(frozen=True)
class Note:
    id: int
    person_id: int
    title: str
    body: str
    pinned: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @property
    def preview(self) -> str:
        text = " ".join(self.body.split())
        return text[:90] + ("…" if len(text) > 90 else "")


def _row(r) -> Note:
    return Note(r["id"], r["person_id"], r["title"], r["body"], bool(r["pinned"]), bool(r["archived"]),
                datetime.fromisoformat(r["created_at"]), datetime.fromisoformat(r["updated_at"]),
                datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def can_see(note: Note, person: Person) -> bool:
    """Só a dona. Sem exceção para gestor ou administrador."""
    return person is not None and note.person_id == person.id


def _own(db: Database, person: Person, note_id: int, deleted: bool = False) -> Note:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    note = _row(r) if r else None
    if note is None or not can_see(note, person) or (note.deleted_at is not None) != deleted:
        raise ValidationError("Nota não encontrada.")
    return note


def get_note(db: Database, person: Person, note_id: int) -> Note | None:
    try:
        return _own(db, person, note_id)
    except ValidationError:
        return None


def _clean(title: str, body: str) -> tuple[str, str]:
    title = " ".join((title or "").split()) or UNTITLED
    body = (body or "").replace("\r\n", "\n")
    if len(title) > MAX_TITLE:
        raise ValidationError(f"Título muito longo (máximo {MAX_TITLE}).")
    if len(body) > MAX_BODY:
        raise ValidationError(f"Texto muito longo (máximo {MAX_BODY} caracteres).")
    return title, body


def create_note(db: Database, now: datetime, person: Person, title: str = "", body: str = "") -> Note:
    title, body = _clean(title, body)
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO notes(person_id, title, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                           (person.id, title, body, _iso(now), _iso(now)))
        return _row(conn.execute("SELECT * FROM notes WHERE id = ?", (cur.lastrowid,)).fetchone())


def save_note(db: Database, now: datetime, person: Person, note_id: int, title: str, body: str) -> Note:
    _own(db, person, note_id)
    title, body = _clean(title, body)
    with db.connect() as conn:
        conn.execute("UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                     (title, body, _iso(now), note_id))
        return _row(conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone())


def touch(db: Database, now: datetime, note_id: int) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE notes SET updated_at = ? WHERE id = ?", (_iso(now), note_id))


def set_flag(db: Database, now: datetime, person: Person, note_id: int, flag: str, value: bool) -> None:
    if flag not in ("pinned", "archived"):
        raise ValidationError("Ação inválida.")
    _own(db, person, note_id)
    with db.connect() as conn:
        conn.execute(f"UPDATE notes SET {flag} = ? WHERE id = ?", (int(value), note_id))


def delete_note(db: Database, now: datetime, person: Person, note_id: int) -> None:
    _own(db, person, note_id)
    with db.connect() as conn:
        conn.execute("UPDATE notes SET deleted_at = ? WHERE id = ?", (_iso(now), note_id))


def restore_note(db: Database, now: datetime, person: Person, note_id: int) -> None:
    _own(db, person, note_id, deleted=True)
    with db.connect() as conn:
        conn.execute("UPDATE notes SET deleted_at = NULL WHERE id = ?", (note_id,))


def list_notes(db: Database, person: Person, *, text: str = "", archived: bool = False,
               trash: bool = False) -> list[Note]:
    """As notas da pessoa: fixadas primeiro, depois as mais recentes. A busca olha título e texto
    (e, sem filtro de arquivadas, também acha as arquivadas)."""
    words = [w for w in text.lower().split() if w]
    with db.connect() as conn:
        rows = [_row(r) for r in conn.execute(
            "SELECT * FROM notes WHERE person_id = ? ORDER BY pinned DESC, updated_at DESC, id DESC", (person.id,))]
    out = []
    for n in rows:
        if trash != (n.deleted_at is not None):
            continue
        if not trash and not words and n.archived != archived:
            continue
        if words and not all(w in f"{n.title} {n.body}".lower() for w in words):
            continue
        out.append(n)
    return out


def count_for(db: Database, person_id: int) -> int:
    """Quantas notas uma pessoa tem (para o administrador, sem ver nenhuma)."""
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM notes WHERE person_id = ?", (person_id,)).fetchone()[0]


def erase_person_notes(db: Database, now: datetime, admin: Person, person: Person) -> int:
    """Um administrador apaga de vez as notas de quem saiu da equipe (pessoa desativada), sem abrir nenhuma."""
    if admin is None or not admin.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    if person.active:
        raise ValidationError("Só dá para apagar as notas de uma pessoa desativada.")
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM notes WHERE person_id = ?", (person.id,))]
        if ids:
            marks = ",".join("?" * len(ids))
            # os arquivos vão para a lixeira já vencida: a próxima limpeza tira do disco
            conn.execute(f"UPDATE attachments SET deleted_at = ? WHERE kind = ? AND parent_id IN ({marks}) "
                         "AND deleted_at IS NULL", [_iso(now - timedelta(days=TRASH_DAYS + 1)), KIND, *ids])
            conn.execute(f"DELETE FROM notes WHERE id IN ({marks})", ids)
    return len(ids)


def purge(db: Database, now: datetime) -> int:
    """Apaga de vez as notas que estão na lixeira há mais de 30 dias (os arquivos vão junto para a lixeira)."""
    limit = _iso(now - timedelta(days=TRASH_DAYS))
    with db.connect() as conn:
        rows = conn.execute("SELECT id, deleted_at FROM notes WHERE deleted_at < ?", (limit,)).fetchall()
        for r in rows:
            conn.execute("UPDATE attachments SET deleted_at = ? WHERE kind = ? AND parent_id = ? AND deleted_at IS NULL",
                         (r["deleted_at"], KIND, r["id"]))
            conn.execute("DELETE FROM notes WHERE id = ?", (r["id"],))
    return len(rows)


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or UNTITLED


def export_zip(db: Database, person: Person) -> bytes:
    """Todas as notas da pessoa (menos as da lixeira) num ZIP: cada nota em .txt e os arquivos numa pasta."""
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for n in list_notes(db, person) + list_notes(db, person, archived=True):
            base = _safe(n.title)[:60]
            name, i = base, 2
            while name.lower() in used:
                name, i = f"{base} ({i})", i + 1
            used.add(name.lower())
            header = f"{n.title}\nAtualizada em {n.updated_at.strftime('%d/%m/%Y %H:%M')}\n\n"
            z.writestr(f"{name}.txt", "﻿" + header + n.body)  # BOM: o Bloco de Notas do Windows lê os acentos
            for a in anexos.list_for(db, KIND, n.id):
                path = anexos.path_of(db, a)
                if path.is_file():
                    z.write(path, f"{name} - arquivos/{_safe(a.name)}")
    return buffer.getvalue()
