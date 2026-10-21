"""Ponto de entrada: `python -m hub` (é o que o iniciar.bat chama no PC reserva)."""

import logging
import socket
import sys
import threading
import time
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .db import Database
from .paths import data_dir
from .winsys import open_tv

PORT = 8800
BACKUP_EVERY_SECONDS = 24 * 3600
log = logging.getLogger("hub")


def acquire_port(port: int = PORT) -> socket.socket | None:
    """Reserva a porta do Hub para a rede toda. Ocupada = outra cópia já está aberta."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # sem isto, no Windows, dois programas conseguem dividir a mesma porta
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("0.0.0.0", port))
    except OSError:
        sock.close()
        return None
    return sock


def server_config(app):
    import uvicorn

    # log_config=None: sob pythonw (iniciar.bat) não há console e o log padrão do uvicorn quebra
    return uvicorn.Config(app, log_level="warning", log_config=None)


def _backup_loop(db_path: Path) -> None:
    from .backup import make_backup

    while True:
        try:
            make_backup(db_path, data_dir() / "copias", date.today())
        except Exception:
            log.exception("falha na cópia de segurança")
        try:
            from . import anexos
            from .db import Database

            anexos.purge(Database(db_path), datetime.now())  # lixeira dos anexos: some depois de 30 dias
        except Exception:
            log.exception("falha na limpeza da lixeira dos anexos")
        time.sleep(BACKUP_EVERY_SECONDS)


def main() -> None:
    tv_url = f"http://127.0.0.1:{PORT}/tv"
    sock = acquire_port(PORT)
    if sock is None:
        open_tv(tv_url)  # já está rodando: só mostra a TV
        return

    import uvicorn

    from .web.app import create_app
    from .winsys import keep_awake

    handler = RotatingFileHandler(data_dir() / "hub.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    keep_awake()
    db = Database(data_dir() / "hub.db")
    db.init()
    server = uvicorn.Server(server_config(create_app(db)))
    threading.Thread(target=_backup_loop, args=(db.path,), daemon=True, name="copias").start()
    threading.Timer(2.0, open_tv, args=(tv_url,)).start()
    log.info("Hub iniciado na porta %s", PORT)
    try:
        server.run(sockets=[sock])
    except Exception:
        log.exception("o servidor parou")
        raise


if __name__ == "__main__":
    main()
