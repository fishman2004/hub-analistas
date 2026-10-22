"""Base 8081 automática do Google Drive (fase 22).

O gestor tem uma automação que salva a "(DADOS) - 8081 - Vendas" no Google Drive com frequência.
Uma "ponte" do Apps Script (tools/drive/ponte-8081.gs), publicada pela própria conta Google que
tem o arquivo, entrega esse arquivo só para quem manda a chave certa. Este módulo, de tempos em
tempos, pergunta à ponte se o arquivo mudou e, se mudou, baixa e grava na pasta dos painéis com o
nome certo. A TV pega o arquivo novo como sempre (pela data de modificação).

Segurança:
- O arquivo no Drive continua fechado (sem "qualquer pessoa com o link"): só a ponte o lê.
- A chave fica no hub.db do PC da sala, nunca no repositório, e não vai para o hub.log nem para
  as mensagens de erro. O endereço só pode ser de script.google.com, para a chave não ir parar
  em outro lugar.
- O arquivo baixado só troca o anterior depois de lido sem erro: download pela metade ou
  planilha sem as colunas da 8081 nunca chega à TV.
"""

import base64
import binascii
import json
import logging
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import Database, get_setting, log_event, put_setting
from .paineis import FILES_BY_KEY, MAX_UPLOAD_BYTES, find_file, install_file, panel_folder
from .people import Person, ValidationError
from .planilhas import EXTENSIONS, PlanilhaError, read_rows

log = logging.getLogger("hub.drive")

SETTING_URL = "drive.url"
SETTING_KEY = "drive.chave"
SETTING_MINUTES = "drive.minutos"
SETTING_STATE = "drive.estado"  # JSON com a última verificação, o último download e o último erro
MINUTES_DEFAULT, MINUTES_MIN, MINUTES_MAX = 10, 2, 120
URL_PREFIX = "https://script.google.com/"
KEY_MIN = 32
TIMEOUT_SECONDS = 120
TARGET = FILES_BY_KEY["vendas"]
_sync_lock = threading.Lock()  # um download por vez (o laço e o botão "Baixar agora")


# ---------- configuração ----------

def interval_minutes(db: Database) -> int:
    raw = get_setting(db, SETTING_MINUTES)
    return int(raw) if raw and raw.isdigit() else MINUTES_DEFAULT


def enabled(db: Database) -> bool:
    return bool(get_setting(db, SETTING_URL) and get_setting(db, SETTING_KEY))


def state(db: Database) -> dict:
    raw = get_setting(db, SETTING_STATE)
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _put_state(db: Database, **changes) -> dict:
    current = state(db)
    current.update(changes)
    with db.connect() as conn:
        put_setting(conn, SETTING_STATE, json.dumps(current))
    return current


def drive_config(db: Database) -> dict:
    """O que a página mostra. A chave nunca volta para a tela: só se existe ou não."""
    st = state(db)
    when = {k: datetime.fromisoformat(st[k]) for k in ("verificado", "baixado", "modificado") if st.get(k)}
    return {"url": get_setting(db, SETTING_URL) or "", "has_key": bool(get_setting(db, SETTING_KEY)),
            "minutes": interval_minutes(db), "enabled": enabled(db), "error": st.get("erro", ""), **when}


def new_key() -> str:
    return secrets.token_urlsafe(32)  # 43 letras e números: impossível de adivinhar


def save_drive_config(db: Database, now: datetime, actor: Person, url: str, key: str, minutes: str,
                      generate: bool = False) -> str | None:
    """Grava a configuração. Devolve a chave nova quando o administrador pediu para gerar uma
    (é a única vez que ela aparece na tela, para colar na ponte)."""
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    url = url.strip()
    key = key.strip()
    if url and not url.startswith(URL_PREFIX):
        raise ValidationError("Use o endereço do app da Web do Apps Script, que começa com "
                              f"{URL_PREFIX} e termina com /exec.")
    if not minutes.isdigit() or not MINUTES_MIN <= int(minutes) <= MINUTES_MAX:
        raise ValidationError(f"Verificar a cada: use de {MINUTES_MIN} a {MINUTES_MAX} minutos.")
    if key and len(key) < KEY_MIN:
        raise ValidationError(f"A chave precisa de pelo menos {KEY_MIN} letras e números. Use \"Gerar chave nova\".")
    created = new_key() if generate else None
    with db.connect() as conn:
        put_setting(conn, SETTING_URL, url or None)
        put_setting(conn, SETTING_MINUTES, str(int(minutes)))
        if created or key:
            put_setting(conn, SETTING_KEY, created or key)
        if not url:
            put_setting(conn, SETTING_KEY, None)  # desligar apaga a chave também
            put_setting(conn, SETTING_STATE, None)
        log_event(conn, now, actor.id, "config_drive", "config:drive", "ligado" if url else "desligado")
    return created


# ---------- download ----------

@dataclass(frozen=True)
class Resultado:
    ok: bool
    changed: bool = False
    message: str = ""


def _http_get(url: str, timeout: int) -> bytes:
    # o urllib já usa o proxy configurado no Windows, se a empresa tiver um
    context = ssl.create_default_context()
    request = urllib.request.Request(url, headers={"User-Agent": "Hub-dos-Analistas"})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        data = response.read(MAX_UPLOAD_BYTES * 2)  # o arquivo vem em base64, um terço maior
    return data


def _ask(url: str, key: str, since: str, fetch) -> dict:
    query = {"chave": key}
    if since:
        query["desde"] = since
    full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
    try:
        raw = fetch(full, TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        raise ValidationError(f"O Google respondeu com erro {exc.code}. Confira o endereço da ponte e se ela "
                              "foi implantada para \"Qualquer pessoa\".") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ValidationError(f"Sem conexão com o Google ({reason.__class__.__name__}). Confira se o PC da sala "
                              "abre sites da internet.") from None
    try:
        answer = json.loads(raw)
    except ValueError:
        raise ValidationError("A ponte não respondeu como esperado (veio uma página em vez dos dados). Confira se "
                              "o endereço termina com /exec e se a implantação é \"Qualquer pessoa\".") from None
    if not isinstance(answer, dict):
        raise ValidationError("A ponte não respondeu como esperado.")
    return answer


def sync(db: Database, now: datetime, fetch=None) -> Resultado:
    """Pergunta à ponte se a 8081 mudou e, se mudou, baixa, confere e grava na pasta dos painéis."""
    url, key = get_setting(db, SETTING_URL), get_setting(db, SETTING_KEY)
    if not url or not key:
        return Resultado(False, message="Download do Drive desligado.")
    with _sync_lock:
        try:
            result = _sync(db, url, key, fetch or _http_get)
        except ValidationError as exc:
            _put_state(db, verificado=now.isoformat(timespec="seconds"), erro=str(exc))
            log.warning("8081 do Drive: %s", exc)
            return Resultado(False, message=str(exc))
        except Exception:  # nada derruba o Hub; o detalhe vai para o hub.log (sem a chave)
            log.exception("falha inesperada ao baixar a 8081 do Drive")
            message = "Falha inesperada ao baixar. O detalhe está no hub.log."
            _put_state(db, verificado=now.isoformat(timespec="seconds"), erro=message)
            return Resultado(False, message=message)
    changes = {"verificado": now.isoformat(timespec="seconds"), "erro": ""}
    if result.changed:
        changes["baixado"] = now.isoformat(timespec="seconds")
        changes["modificado"] = result.message  # sem linha no histórico: seriam dezenas por dia
        log.info("8081 do Drive baixada (alterada no Drive em %s)", result.message)
    _put_state(db, **changes)
    return Resultado(True, result.changed,
                     "Arquivo novo baixado." if result.changed else "O arquivo do Drive não mudou.")


def _sync(db: Database, url: str, key: str, fetch) -> Resultado:
    folder = panel_folder(db)
    since = state(db).get("modificado_drive", "") if find_file(folder, TARGET.base) else ""
    answer = _ask(url, key, since, fetch)
    if not answer.get("ok"):
        error = str(answer.get("erro", ""))
        if error == "chave":
            raise ValidationError("A ponte recusou a chave. A chave daqui tem de ser igual à CHAVE_HUB do script.")
        raise ValidationError(f"A ponte não conseguiu ler o arquivo no Drive: {error[:200] or 'sem detalhe'}.")
    modified = str(answer.get("modificado", ""))
    if answer.get("igual"):
        return Resultado(True, False)
    ext = "." + str(answer.get("tipo", "")).lower().lstrip(".")
    if ext not in EXTENSIONS:
        raise ValidationError(f"O arquivo do Drive está em {ext}: a 8081 precisa ser {', '.join(EXTENSIONS)}.")
    try:
        content = base64.b64decode(str(answer.get("conteudo", "")), validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("O arquivo chegou incompleto. O Hub tenta de novo na próxima verificação.") from None
    if not content:
        raise ValidationError("O arquivo do Drive está vazio.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValidationError("O arquivo do Drive é grande demais (máximo 200 MB).")
    partial = folder / (TARGET.base + ".baixando" + ext)  # com a extensão certa, para dar para ler
    try:
        partial.write_bytes(content)
        try:
            read_rows(partial, TARGET.columns)  # só troca o arquivo da TV se ele estiver legível
        except PlanilhaError as exc:
            raise ValidationError(f"O arquivo do Drive não foi usado: {exc}") from None
        stamp = _drive_time(modified)
        if stamp is not None:  # "atualizado às" da TV = quando a automação gerou o arquivo
            os.utime(partial, (stamp, stamp))
        install_file(folder, TARGET, partial, ext)
    finally:
        partial.unlink(missing_ok=True)
    _put_state(db, modificado_drive=modified)
    return Resultado(True, True, _local_text(modified))


def _drive_time(text: str) -> float | None:
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _local_text(text: str) -> str:
    stamp = _drive_time(text)
    return datetime.fromtimestamp(stamp).isoformat(timespec="seconds") if stamp is not None else ""


# ---------- o laço em segundo plano ----------

def due(db: Database, now: datetime) -> bool:
    if not enabled(db):
        return False
    last = state(db).get("verificado")
    if not last:
        return True
    return (now - datetime.fromisoformat(last)).total_seconds() >= interval_minutes(db) * 60


def loop(db_path: Path, tick_seconds: int = 30) -> None:
    """Roda para sempre (linha de fundo do __main__): olha a cada 30 s se já está na hora."""
    while True:
        try:
            db = Database(db_path)
            now = datetime.now()
            if due(db, now):
                sync(db, now)
        except Exception:
            log.exception("falha no laço do download do Drive")
        time.sleep(tick_seconds)
