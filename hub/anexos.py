"""Anexos (fase 11): arquivos guardados junto de uma demanda (e, na fase 12, de uma nota).

O arquivo vai para a pasta Anexos (padrão %LOCALAPPDATA%\\Hub\\Anexos, fora do código e fora do
banco), com um nome aleatório e sem a extensão: o nome original fica só no banco. Assim nenhum nome
estranho ("..\\..\\", acentos, nomes repetidos) chega ao disco e nada é sobrescrito. Uma nova versão
é um arquivo novo que aponta para o anterior (replaces). Remover só marca: o arquivo fica na lixeira
por TRASH_DAYS e depois a limpeza diária apaga do disco.

Este módulo não decide quem pode o quê: quem chama (demandas, notas) confere a permissão antes.
"""

import hashlib
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from .db import Database, get_setting, log_event, put_setting
from .paths import data_dir
from .people import Person, ValidationError

SETTING_FOLDER = "anexos.pasta"
MAX_BYTES = 25 * 1024 * 1024
MAX_PER_PARENT = 20
MIN_FREE_BYTES = 2 * 1024 ** 3  # abaixo disso no disco, o Hub recusa receber arquivos
TRASH_DAYS = 30
MAX_NAME = 150

_ZIP, _OLE = b"PK\x03\x04", b"\xd0\xcf\x11\xe0"
# extensão -> como o arquivo começa (None: texto, sem assinatura). Executáveis, scripts, .zip, .html e
# planilhas com macro (.xlsm) ficam de fora de propósito.
EXTENSIONS: dict[str, bytes | None] = {
    ".xlsx": _ZIP, ".xlsb": _ZIP, ".docx": _ZIP, ".pptx": _ZIP, ".xls": _OLE, ".doc": _OLE,
    ".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff",
    ".csv": None, ".txt": None,
}
ACCEPT = ",".join(EXTENSIONS)  # para o <input type=file accept=...>


@dataclass(frozen=True)
class Attachment:
    id: int
    kind: str
    parent_id: int
    name: str
    stored: str
    size: int
    uploaded_by: int | None
    uploaded_at: datetime
    replaces: int | None
    deleted_at: datetime | None
    versions: tuple["Attachment", ...] = ()  # versões anteriores, da mais nova para a mais antiga

    @property
    def size_text(self) -> str:
        return size_text(self.size)


def size_text(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB".replace(".", ",")
    return f"{n / 1024 ** 3:.1f} GB".replace(".", ",")


def _row(r) -> Attachment:
    return Attachment(r["id"], r["kind"], r["parent_id"], r["name"], r["stored"], r["size"], r["uploaded_by"],
                      datetime.fromisoformat(r["uploaded_at"]), r["replaces"],
                      datetime.fromisoformat(r["deleted_at"]) if r["deleted_at"] else None)


# ---------- pasta ----------

def default_folder() -> Path:
    return data_dir() / "Anexos"


def folder(db: Database) -> Path:
    custom = get_setting(db, SETTING_FOLDER)
    return Path(custom) if custom else default_folder()


def save_folder(db: Database, now: datetime, actor: Person, value: str) -> None:
    """Um administrador aponta os anexos para outra pasta (por exemplo, na rede). Em branco: a padrão."""
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    value = value.strip().strip('"')
    if value:
        path = Path(value)
        if not path.is_absolute():
            raise ValidationError("Informe o caminho completo da pasta, por exemplo Y:\\Hub\\Anexos.")
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise ValidationError("O Hub não conseguiu abrir nem criar essa pasta.")
    with db.connect() as conn:
        put_setting(conn, SETTING_FOLDER, value or None)
        log_event(conn, now, actor.id, "config_anexos", "config:anexos", value)


def path_of(db: Database, a: Attachment) -> Path:
    return folder(db) / a.stored


# ---------- guardar ----------

def clean_name(filename: str) -> str:
    """Só o nome do arquivo, sem pasta (o navegador pode mandar "C:\\...\\arquivo.xlsx")."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch >= " " and ch not in '<>:"|?*').strip(" .")
    if not name:
        raise ValidationError("O arquivo precisa ter um nome.")
    if len(name) > MAX_NAME:
        stem, ext = os.path.splitext(name)
        name = stem[: MAX_NAME - len(ext)] + ext
    return name


def _check_extension(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXTENSIONS:
        raise ValidationError(f"“{name}”: esse tipo de arquivo não é aceito. Aceitos: "
                              + ", ".join(e.lstrip(".") for e in EXTENSIONS) + ".")
    return ext


def _check_type(name: str, head: bytes) -> None:
    ext = _check_extension(name)
    signature = EXTENSIONS[ext]
    if signature is not None and not head.startswith(signature):
        raise ValidationError(f"“{name}” não parece ser um arquivo {ext.lstrip('.').upper()} de verdade.")


def save(db: Database, now: datetime, actor: Person, kind: str, parent_id: int, filename: str, data: BinaryIO,
         replaces: int | None = None, subject: str = "") -> Attachment:
    """Grava um arquivo novo (ou uma nova versão de `replaces`) e registra no histórico em `subject`."""
    name = clean_name(filename)
    _check_extension(name)  # antes de gravar qualquer coisa
    base = folder(db)
    with db.connect() as conn:
        if replaces is not None:
            old = conn.execute("SELECT * FROM attachments WHERE id = ? AND kind = ? AND parent_id = ? "
                               "AND deleted_at IS NULL", (replaces, kind, parent_id)).fetchone()
            if old is None or _replaced(conn, replaces):
                raise ValidationError("Esse arquivo não está mais na lista. Atualize a página.")
        elif len(_current_ids(conn, kind, parent_id)) >= MAX_PER_PARENT:
            raise ValidationError(f"Já há {MAX_PER_PARENT} arquivos aqui. Remova algum antes de anexar outro.")
    try:
        base.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(base).free
    except OSError:
        raise ValidationError("A pasta dos anexos não está acessível agora. Avise um administrador.")
    if free < MIN_FREE_BYTES:
        raise ValidationError("O disco do PC da sala está quase cheio: o Hub não está recebendo arquivos. "
                              "Avise um administrador.")
    month = now.strftime("%Y-%m")
    (base / month).mkdir(exist_ok=True)
    stored = f"{month}/{secrets.token_hex(16)}"
    target = base / stored
    partial = target.with_name(target.name + ".enviando")
    digest, size, head = hashlib.sha256(), 0, b""
    try:
        with open(partial, "wb") as out:
            while chunk := data.read(1024 * 1024):
                if not head:
                    head = chunk[:8]
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValidationError(f"“{name}” é grande demais (máximo {MAX_BYTES // 1024 ** 2} MB).")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise ValidationError(f"“{name}” está vazio.")
        _check_type(name, head)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO attachments(kind, parent_id, name, stored, size, sha256, uploaded_by, uploaded_at, replaces) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, parent_id, name, stored, size, digest.hexdigest(), actor.id, now.isoformat(timespec="seconds"),
                 replaces))
            if subject:
                log_event(conn, now, actor.id, "anexo_versao" if replaces else "anexo_enviado", subject, name)
            return _row(conn.execute("SELECT * FROM attachments WHERE id = ?", (cur.lastrowid,)).fetchone())
    except Exception:
        target.unlink(missing_ok=True)  # o banco recusou: não deixa arquivo órfão
        raise


# ---------- listar ----------

def _replaced(conn, attachment_id: int) -> bool:
    return conn.execute("SELECT 1 FROM attachments WHERE replaces = ?", (attachment_id,)).fetchone() is not None


def _current_ids(conn, kind: str, parent_id: int) -> list[int]:
    """Os arquivos da lista: não removidos e sem uma versão mais nova."""
    return [r[0] for r in conn.execute(
        "SELECT id FROM attachments a WHERE kind = ? AND parent_id = ? AND deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM attachments b WHERE b.replaces = a.id)", (kind, parent_id))]


def _chain(conn, a: Attachment) -> tuple[Attachment, ...]:
    out, previous = [], a.replaces
    while previous is not None:
        r = conn.execute("SELECT * FROM attachments WHERE id = ?", (previous,)).fetchone()
        if r is None:
            break
        out.append(_row(r))
        previous = r["replaces"]
    return tuple(out)


def list_for(db: Database, kind: str, parent_id: int) -> list[Attachment]:
    with db.connect() as conn:
        ids = _current_ids(conn, kind, parent_id)
        rows = [_row(r) for r in conn.execute(
            f"SELECT * FROM attachments WHERE id IN ({','.join('?' * len(ids))}) ORDER BY uploaded_at, id", ids)]
        return [Attachment(**{**a.__dict__, "versions": _chain(conn, a)}) for a in rows]


def counts(db: Database, kind: str) -> dict[int, int]:
    """Quantos arquivos cada demanda (ou nota) tem, para o 📎 do quadro."""
    with db.connect() as conn:
        return {r[0]: r[1] for r in conn.execute(
            "SELECT parent_id, COUNT(*) FROM attachments a WHERE kind = ? AND deleted_at IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM attachments b WHERE b.replaces = a.id) GROUP BY parent_id", (kind,))}


def get(db: Database, attachment_id: int) -> Attachment | None:
    """Um arquivo (ou uma versão anterior) que ainda pode ser baixado: não removido nem apagado do disco."""
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM attachments WHERE id = ? AND purged = 0", (attachment_id,)).fetchone()
        if r is None:
            return None
        a = _row(r)
        # versão anterior: vale o que acontecer com a versão atual da corrente
        head = r
        while head is not None and head["deleted_at"] is None:
            head = conn.execute("SELECT * FROM attachments WHERE replaces = ?", (head["id"],)).fetchone()
        return None if head is not None else a


def find(db: Database, attachment_id: int) -> Attachment | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    return _row(r) if r else None


# ---------- remover, lixeira e limpeza ----------

def _chain_ids(conn, attachment_id: int) -> list[int]:
    ids, previous = [attachment_id], attachment_id
    while (r := conn.execute("SELECT replaces FROM attachments WHERE id = ?", (previous,)).fetchone()) and r[0]:
        ids.append(r[0])
        previous = r[0]
    return ids


def remove(db: Database, now: datetime, actor: Person, a: Attachment, subject: str = "") -> None:
    """Tira da lista o arquivo e as versões anteriores dele (vão juntos para a lixeira)."""
    with db.connect() as conn:
        ids = _chain_ids(conn, a.id)
        conn.execute(f"UPDATE attachments SET deleted_at = ?, deleted_by = ? WHERE id IN ({','.join('?' * len(ids))}) "
                     "AND deleted_at IS NULL", [now.isoformat(timespec="seconds"), actor.id, *ids])
        if subject:
            log_event(conn, now, actor.id, "anexo_removido", subject, a.name)


def trash(db: Database, now: datetime, kind: str) -> list[Attachment]:
    """Os arquivos removidos nos últimos TRASH_DAYS dias (só a versão que estava na lista)."""
    since = (now - timedelta(days=TRASH_DAYS)).isoformat(timespec="seconds")
    with db.connect() as conn:
        return [_row(r) for r in conn.execute(
            "SELECT * FROM attachments a WHERE kind = ? AND deleted_at >= ? AND purged = 0 "
            "AND NOT EXISTS (SELECT 1 FROM attachments b WHERE b.replaces = a.id) ORDER BY deleted_at DESC",
            (kind, since))]


def restore(db: Database, now: datetime, actor: Person, a: Attachment, subject: str = "") -> None:
    with db.connect() as conn:
        r = conn.execute("SELECT deleted_at, purged FROM attachments WHERE id = ?", (a.id,)).fetchone()
        if r is None or r["deleted_at"] is None or r["purged"]:
            raise ValidationError("Esse arquivo não está mais na lixeira.")
        ids = _chain_ids(conn, a.id)
        conn.execute(f"UPDATE attachments SET deleted_at = NULL, deleted_by = NULL WHERE id IN "
                     f"({','.join('?' * len(ids))}) AND deleted_at = ? AND purged = 0", [*ids, r["deleted_at"]])
        if subject:
            log_event(conn, now, actor.id, "anexo_restaurado", subject, a.name)


def purge(db: Database, now: datetime) -> int:
    """Apaga do disco o que está na lixeira há mais de TRASH_DAYS dias. Roda com a cópia diária."""
    limit = (now - timedelta(days=TRASH_DAYS)).isoformat(timespec="seconds")
    base = folder(db)
    with db.connect() as conn:
        rows = conn.execute("SELECT id, stored FROM attachments WHERE deleted_at < ? AND purged = 0", (limit,)).fetchall()
        for r in rows:
            try:
                (base / r["stored"]).unlink(missing_ok=True)
            except OSError:
                continue  # arquivo preso: tenta de novo amanhã
            conn.execute("UPDATE attachments SET purged = 1 WHERE id = ?", (r["id"],))
    return len(rows)


def usage(db: Database) -> dict:
    """Espaço que os anexos ocupam (inclusive a lixeira) e o espaço livre no disco da pasta."""
    with db.connect() as conn:
        used = conn.execute("SELECT COALESCE(SUM(size), 0) FROM attachments WHERE purged = 0").fetchone()[0]
        files = conn.execute("SELECT COUNT(*) FROM attachments WHERE purged = 0").fetchone()[0]
    try:
        free = shutil.disk_usage(folder(db) if folder(db).exists() else data_dir()).free
    except OSError:
        free = None
    return {"used": size_text(used), "files": files, "free": size_text(free) if free is not None else "?",
            "low": free is not None and free < MIN_FREE_BYTES}
