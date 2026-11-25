"""Tema de Natal (fase 27): o visual natalino no app e na TV, a música de fundo da TV e os sinos nos avisos.

Tudo fica na tabela settings (sem migração):
- natal_modo: "auto" (padrão: liga sozinho de 1º de dezembro a 6 de janeiro, Dia de Reis), "ligado" ou "desligado";
- natal_musica: "1"/"0", se a TV da sala toca a música de fundo enquanto o tema está ligado (padrão: sim);
- natal_volume: de 0 a 100, o volume da música na TV (padrão 25). Os sinos dos avisos tocam sempre no volume cheio.

A música e os sinos são gerados no próprio navegador (Web Audio), a partir de melodias de domínio público
(Jingle Bells, Noite Feliz, We Wish You a Merry Christmas, O Tannenbaum, Deck the Halls): nenhum arquivo de
áudio de terceiros, nada de internet.
"""

from __future__ import annotations

from datetime import date, datetime

from .db import Database, get_setting, log_event, put_setting
from .people import Person, ValidationError

SETTING_MODE = "natal_modo"
SETTING_MUSIC = "natal_musica"
SETTING_VOLUME = "natal_volume"

MODES = {"auto": "Automático (1º de dezembro a 6 de janeiro)", "ligado": "Ligado agora", "desligado": "Desligado"}
DEFAULT_VOLUME = 25
CHRISTMAS = (12, 25)


def in_season(today: date) -> bool:
    """O período do automático: de 1º de dezembro até o Dia de Reis (6 de janeiro)."""
    return today.month == 12 or (today.month == 1 and today.day <= 6)


def config(db: Database) -> dict:
    mode = get_setting(db, SETTING_MODE)
    volume = get_setting(db, SETTING_VOLUME)
    return {
        "mode": mode if mode in MODES else "auto",
        "music": get_setting(db, SETTING_MUSIC) != "0",
        "volume": int(volume) if volume and volume.isdigit() and 0 <= int(volume) <= 100 else DEFAULT_VOLUME,
    }


def is_on(db: Database, today: date) -> bool:
    mode = config(db)["mode"]
    return mode == "ligado" or (mode == "auto" and in_season(today))


def days_to_christmas(today: date) -> int:
    """Quantos dias faltam para o Natal deste ano (0 no dia; depois do Natal, conta para o do ano que vem)."""
    christmas = date(today.year, *CHRISTMAS)
    if today > christmas:
        christmas = date(today.year + 1, *CHRISTMAS)
    return (christmas - today).days


def tv_payload(db: Database, now: datetime) -> dict:
    """O que a TV precisa saber: se o tema está ligado, se toca a música e em que volume."""
    cfg = config(db)
    on = is_on(db, now.date())
    return {"ligado": on, "musica": on and cfg["music"], "volume": cfg["volume"],
            "faltam": days_to_christmas(now.date()) if on else None}


def save_config(db: Database, now: datetime, actor: Person, mode: str, music: bool, volume: str) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    if mode not in MODES:
        raise ValidationError("Escolha como o tema de Natal liga: automático, ligado ou desligado.")
    volume = volume.strip()
    if not volume.isdigit() or not 0 <= int(volume) <= 100:
        raise ValidationError("Volume da música: use de 0 a 100.")
    with db.connect() as conn:
        put_setting(conn, SETTING_MODE, None if mode == "auto" else mode)
        put_setting(conn, SETTING_MUSIC, None if music else "0")
        put_setting(conn, SETTING_VOLUME, None if int(volume) == DEFAULT_VOLUME else str(int(volume)))
        log_event(conn, now, actor.id, "config_natal", "config:natal",
                  f"{mode}, música {'ligada' if music else 'desligada'}, volume {int(volume)}")
