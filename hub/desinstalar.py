"""Ajuda do desinstalar.bat: mostra onde estão os dados, guarda uma cópia e apaga os dados.

Só usa a biblioteca padrão (roda mesmo com o ambiente quebrado, com o Python do Windows).
O desinstalar.bat fecha o Hub antes de chamar isto, e cuida sozinho do "abrir com o Windows"
e dos arquivos do programa.

    python -m hub.desinstalar info          mostra a pasta dos dados e as pastas escolhidas fora dela
    python -m hub.desinstalar copia         grava "Hub - copia AAAA-MM-DD HHMM.zip" na Área de Trabalho
    python -m hub.desinstalar apagar-dados  apaga a pasta dos dados (%LOCALAPPDATA%\\Hub)
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

DB_NAME = "hub.db"
# pastas que um administrador pode trocar em Configurações (podem estar na rede)
FOLDER_SETTINGS = {
    "paineis.pasta": "Planilhas dos painéis",
    "anexos.pasta": "Anexos das demandas",
    "phd.pasta": "Planilhas do PHD",
}


def data_dir() -> Path:
    """A mesma pasta de hub.paths.data_dir, mas sem criá-la se não existir."""
    custom = os.environ.get("HUB_DADOS")
    return Path(custom) if custom else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Hub"


def desktop_dir() -> Path:
    """A Área de Trabalho de verdade (no Windows pode estar no OneDrive)."""
    if sys.platform == "win32":
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_DESKTOPDIRECTORY = 0x10
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 and buf.value:
            return Path(buf.value)
    desk = Path.home() / "Desktop"
    return desk if desk.is_dir() else Path.home()


def external_folders(data: Path) -> list[tuple[str, Path]]:
    """As pastas escolhidas em Configurações que ficam fora da pasta dos dados (o desinstalador não mexe nelas)."""
    db_path = data / DB_NAME
    if not db_path.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            rows = dict(conn.execute("SELECT key, value FROM settings").fetchall())
        finally:
            conn.close()
    except sqlite3.Error:
        return []
    found = []
    for key, label in FOLDER_SETTINGS.items():
        value = (rows.get(key) or "").strip()
        if not value:
            continue
        path = Path(value)
        if not _inside(path, data):
            found.append((label, path))
    return found


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def make_backup_zip(data: Path, dest_dir: Path, now: datetime) -> Path:
    """Um .zip com tudo da pasta dos dados; o banco entra como uma cópia inteira e consistente."""
    if not data.is_dir():
        raise FileNotFoundError(f"A pasta dos dados não existe: {data}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"Hub - copia {now:%Y-%m-%d %H%M}.zip"
    n = 1
    while target.exists():
        n += 1
        target = dest_dir / f"Hub - copia {now:%Y-%m-%d %H%M} ({n}).zip"
    partial = target.with_name(target.name + ".gravando")
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = None
        if (data / DB_NAME).is_file():
            # a API de backup junta o hub.db com o hub.db-wal: a cópia sai inteira num arquivo só
            snapshot = Path(tmp) / DB_NAME
            source, copy = sqlite3.connect(data / DB_NAME), sqlite3.connect(snapshot)
            try:
                source.backup(copy)
            finally:
                copy.close()
                source.close()
        try:
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                if snapshot:
                    zf.write(snapshot, DB_NAME)
                for f in sorted(data.rglob("*")):
                    rel = f.relative_to(data)
                    if not f.is_file() or rel.as_posix() in (DB_NAME, DB_NAME + "-wal", DB_NAME + "-shm"):
                        continue
                    zf.write(f, rel.as_posix())
            with zipfile.ZipFile(partial) as zf:
                bad = zf.testzip()
            if bad:
                raise OSError(f"A cópia saiu com defeito em {bad}.")
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    partial.replace(target)
    return target


def remove_data(data: Path) -> bool:
    """Apaga a pasta dos dados. Recusa qualquer pasta que não pareça a do Hub. False = não havia pasta."""
    if not data.exists():
        return False
    resolved = data.resolve()
    forbidden = {Path(resolved.anchor), Path.home().resolve()}
    for var in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
        if os.environ.get(var):
            forbidden.add(Path(os.environ[var]).resolve())
    if resolved in forbidden or not resolved.is_dir():
        raise ValueError(f"Por segurança, não apago esta pasta: {data}")
    if resolved.name.lower() != "hub" and not (resolved / DB_NAME).exists():
        raise ValueError(f"Esta pasta não parece ser a dos dados do Hub, não apaguei: {data}")
    shutil.rmtree(resolved)
    return True


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else ""
    data = data_dir()
    try:
        if cmd == "info":
            if (data / DB_NAME).is_file():
                print(f"  Os dados do Hub estao em: {data}")
            elif data.is_dir():
                print(f"  Pasta dos dados (sem banco): {data}")
            else:
                print("  Nao encontrei a pasta dos dados do Hub neste PC.")
            ext = external_folders(data)
            if ext:
                print("  Estas pastas foram escolhidas em Configuracoes e NAO serao apagadas:")
                for label, path in ext:
                    print(f"    - {label}: {path}")
            return 0
        if cmd == "copia":
            target = make_backup_zip(data, desktop_dir(), datetime.now())
            print(f"  Copia guardada em: {target}")
            return 0
        if cmd == "apagar-dados":
            if remove_data(data):
                print(f"  Dados apagados: {data}")
            else:
                print("  Nao havia dados para apagar.")
            return 0
    except Exception as exc:  # o .bat só precisa saber se deu certo; a mensagem vai para a tela
        print(f"  ERRO: {exc}")
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
