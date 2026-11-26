"""Zerar o histórico (pedido do Kayo, 26/11/2026): apagar o que foi feito nos testes antes de começar o uso oficial.

Só um administrador, com o próprio PIN e digitando APAGAR. Apaga o que ACONTECEU (demandas, histórico, marcas,
compromissos...) e mantém o que foi MONTADO: pessoas e PINs, rotinas, trilhas, rotinas do mês, modos da TV,
feriados, pastas e configurações.

Antes de apagar, o banco inteiro é copiado para %LOCALAPPDATA%\\Hub\\copias\\antes-de-zerar-AAAA-MM-DD-HHMM.db,
e os arquivos dos anexos apagados vão para uma pasta "Anexos apagados AAAA-MM-DD HHMM" (nada some do disco).
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import anexos
from .access import require_admin, verify_pin
from .db import Database, log_event
from .people import Person, ValidationError

CONFIRM_WORD = "APAGAR"


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    help: str
    default: bool
    tables: tuple[str, ...]          # apagadas nesta ordem (as filhas antes das mães)
    attachment_kind: str | None = None


GROUPS: tuple[Group, ...] = (
    Group("demandas", "Demandas e quadro",
          "Todos os cartões (abertos, concluídos e apagados), as pastas marcadas nas rotinas e os anexos das demandas.",
          True, ("routine_folders", "demands"), "demanda"),
    Group("historico", "Histórico", "A página Histórico inteira (quem fez o quê e quando).", True, ("events",)),
    Group("marcas", "Marcas das rotinas do mês e da trilha",
          "O que foi marcado como feito e as justificativas. As rotinas e os blocos continuam cadastrados.",
          True, ("month_routine_marks", "month_routine_notes", "trail_marks", "trail_notes")),
    Group("prioridades", "Prioridades do mês", "Os itens das listas de prioridades e o que foi marcado neles.",
          True, ("priority_marks", "priorities")),
    Group("calendario", "Compromissos e ausências",
          "O que foi lançado no Calendário. Os feriados cadastrados continuam.", True,
          ("event_people", "events_cal", "absences")),
    Group("horas", "Entradas e saídas do banco de horas",
          "Os horários lançados dia a dia. O saldo base vindo do RH continua.", True, ("hours_entries",)),
    Group("notas", "Notas pessoais de todo mundo",
          "O bloco de notas de cada pessoa (inclusive anexos). Desligado por padrão: as notas são particulares.",
          False, ("notes",), "nota"),
)
BY_KEY = {g.key: g for g in GROUPS}


# tabelas de ligação: vão junto, mas não entram na contagem que aparece na tela
LINKS = {"routine_folders", "priority_marks", "event_people"}


def counts(db: Database) -> dict[str, int]:
    """Quantos registros cada grupo apagaria agora (para mostrar antes de confirmar)."""
    with db.connect() as conn:
        return {g.key: sum(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in g.tables if t not in LINKS)
                for g in GROUPS}


def backup_before(db: Database, now: datetime) -> Path:
    dest = db.path.parent / "copias"  # a mesma pasta das cópias diárias
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"antes-de-zerar-{now:%Y-%m-%d-%H%M}.db"
    n = 1
    while target.exists():
        n += 1
        target = dest / f"antes-de-zerar-{now:%Y-%m-%d-%H%M}-{n}.db"
    source, copy = sqlite3.connect(db.path), sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    return target


def zerar(db: Database, now: datetime, actor: Person | None, pin: str, confirm: str, keys: list[str]) -> dict:
    """Apaga os grupos escolhidos. Devolve {"apagados": {grupo: n}, "copia": caminho, "anexos": pasta ou None}."""
    require_admin(actor)
    chosen = [BY_KEY[k] for k in dict.fromkeys(keys) if k in BY_KEY]
    if not chosen:
        raise ValidationError("Escolha pelo menos uma coisa para apagar.")
    if (confirm or "").strip().upper() != CONFIRM_WORD:
        raise ValidationError(f"Para confirmar, digite {CONFIRM_WORD} na caixinha.")
    verify_pin(db, now, actor.id, pin or "")  # PIN errado: erro (e conta para o bloqueio, como no Entrar)

    copy = backup_before(db, now)
    files_dir = anexos.folder(db)
    moved_to = None
    removed: dict[str, int] = {}
    to_move: list[str] = []
    with db.connect() as conn:
        for g in chosen:
            if g.attachment_kind:
                rows = conn.execute("SELECT stored FROM attachments WHERE kind = ?", (g.attachment_kind,)).fetchall()
                to_move += [r["stored"] for r in rows]
                conn.execute("DELETE FROM attachments WHERE kind = ?", (g.attachment_kind,))
            total = 0
            for t in g.tables:
                n = conn.execute(f"DELETE FROM {t}").rowcount
                total += 0 if t in LINKS else n
            removed[g.key] = total
        detail = ", ".join(f"{BY_KEY[k].label}: {n}" for k, n in removed.items())
        log_event(conn, now, actor.id, "historico_zerado", "config:zerar", f"{detail} · cópia {copy.name}")

    # os arquivos saem do caminho, mas ficam guardados (a cópia do banco não leva os anexos)
    if to_move:
        moved_to = files_dir.parent / f"Anexos apagados {now:%Y-%m-%d %H%M}"
        for stored in to_move:
            src = files_dir / stored
            if src.is_file():
                dst = moved_to / stored
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
    return {"apagados": removed, "copia": str(copy), "anexos": str(moved_to) if moved_to else None}
