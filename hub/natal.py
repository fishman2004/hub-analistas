"""Tema de Natal (fase 27): o visual natalino no app e na TV, a música de fundo da TV e os sinos nos avisos.

Tudo fica na tabela settings (sem migração):
- natal_modo: "auto" (padrão: liga sozinho de 1º de dezembro a 6 de janeiro, Dia de Reis), "ligado" ou "desligado";
- natal_musica: "1"/"0", se a TV da sala toca a música de fundo enquanto o tema está ligado (padrão: sim);
- natal_volume: de 0 a 100, o volume da música na TV (padrão 25). Os sinos dos avisos tocam sempre no volume cheio;
- natal_tv_estilo: "vermelho" (padrão) ou "preto", a versão do tema na TV. No app, cada pessoa escolhe no botão
  Tema ("Natal" ou "Natal preto"), e pode escolher o Natal mesmo fora da época.

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
SETTING_TV_STYLE = "natal_tv_estilo"
SETTING_SANTA_WHERE = "natal_noel_onde"
SETTING_SANTA_MINUTES = "natal_noel_minutos"
SETTING_SANTA_HEIGHT = "natal_noel_altura"
SETTING_SANTA_NOW = "natal_noel_agora"
SETTING_SANTA_SOUND = "natal_noel_som"  # "1": guizos quando ele passa na TV (padrão: sem som)
SETTING_TRACKS = "natal_faixas"      # as faixas ligadas, separadas por vírgula (sem a linha: todas)
SETTING_ORDER = "natal_ordem"        # "aleatoria" ou "lista"
SETTING_GAP = "natal_intervalo"      # segundos de silêncio entre uma música e outra
SETTING_ALERT_SOUND = "som_aviso"  # vale o ano todo, não só no Natal

MODES = {"auto": "Automático (1º de dezembro a 6 de janeiro)", "ligado": "Ligado agora", "desligado": "Desligado"}
TV_STYLES = {"vermelho": "Vermelho (noite azul, como o app)", "preto": "Preto e dourado"}
SANTA_WHERE = {"tv_app": "Na TV e no app", "tv": "Só na TV", "app": "Só no app", "nenhum": "Em nenhum lugar"}
SANTA_HEIGHTS = {"sorteada": "Cada vez numa altura", "topo": "Em cima", "meio": "No meio", "baixo": "Embaixo"}
DEFAULT_SANTA_MINUTES = 6
SANTA_MIN, SANTA_MAX = 1, 60
ALERT_SOUNDS = {
    "auto": "Automático (sinos de Natal no Natal, o de sempre no resto do ano)",
    "padrao": "O de sempre",
    "sinos": "Sinos de Natal (guizos e Jingle Bells)",
    "igreja": "Sino de igreja (blém-blém)",
    "carrilhao": "Carrilhão de relógio (dim-dom-dim-dom)",
    "caixinha": "Caixinha de música",
    "guizos": "Guizos de trenó",
}
# as músicas (todas de domínio público); os ids são os mesmos de static/natal.js
TRACKS = {"jingle": "Jingle Bells", "noite": "Noite Feliz", "wewish": "We Wish You a Merry Christmas",
          "deck": "Deck the Halls", "noite-piano": "Noite Feliz (piano suave)",
          "jingle-piano": "Jingle Bells (piano suave)", "neve": "Pianinho de neve (ambiente)",
          "lareira": "Lareira (ambiente)", "sinos": "Sinos ao longe (ambiente)"}
ORDERS = {"aleatoria": "Aleatória", "lista": "Na ordem da lista"}
DEFAULT_GAP = 5
GAP_MAX = 300
DEFAULT_VOLUME = 25
CHRISTMAS = (12, 25)


def in_season(today: date) -> bool:
    """O período do automático: de 1º de dezembro até o Dia de Reis (6 de janeiro)."""
    return today.month == 12 or (today.month == 1 and today.day <= 6)


def config(db: Database) -> dict:
    mode = get_setting(db, SETTING_MODE)
    volume = get_setting(db, SETTING_VOLUME)
    style = get_setting(db, SETTING_TV_STYLE)
    return {
        "mode": mode if mode in MODES else "auto",
        "music": get_setting(db, SETTING_MUSIC) != "0",
        "volume": int(volume) if volume and volume.isdigit() and 0 <= int(volume) <= 100 else DEFAULT_VOLUME,
        "tv_style": style if style in TV_STYLES else "vermelho",
        **santa_and_sound(db),
        **music_options(db),
    }


def music_options(db: Database) -> dict:
    tracks = get_setting(db, SETTING_TRACKS)
    chosen = [t for t in (tracks or "").split(",") if t in TRACKS] if tracks is not None else list(TRACKS)
    order = get_setting(db, SETTING_ORDER)
    gap = get_setting(db, SETTING_GAP)
    return {
        "tracks": chosen or list(TRACKS),
        "order": order if order in ORDERS else "aleatoria",
        "gap": int(gap) if gap and gap.isdigit() and int(gap) <= GAP_MAX else DEFAULT_GAP,
    }


def santa_and_sound(db: Database) -> dict:
    where = get_setting(db, SETTING_SANTA_WHERE)
    minutes = get_setting(db, SETTING_SANTA_MINUTES)
    height = get_setting(db, SETTING_SANTA_HEIGHT)
    sound = get_setting(db, SETTING_ALERT_SOUND)
    return {
        "santa_where": where if where in SANTA_WHERE else "tv_app",
        "santa_minutes": int(minutes) if minutes and minutes.isdigit() and SANTA_MIN <= int(minutes) <= SANTA_MAX
        else DEFAULT_SANTA_MINUTES,
        "santa_height": height if height in SANTA_HEIGHTS else "sorteada",
        "santa_sound": get_setting(db, SETTING_SANTA_SOUND) == "1",
        "alert_sound": sound if sound in ALERT_SOUNDS else "auto",
    }


def santa_for(db: Database, place: str) -> dict | None:
    """Se o Papai Noel passa nesse lugar ("tv" ou "app"), de quanto em quanto tempo e em que altura."""
    cfg = santa_and_sound(db)
    if cfg["santa_where"] not in ("tv_app", place):
        return None
    return {"minutos": cfg["santa_minutes"], "altura": cfg["santa_height"], "som": cfg["santa_sound"]}


def alert_sound(db: Database, today: date) -> str:
    """O som que a TV toca nos avisos das rotinas. No automático: sinos no Natal, o de sempre fora dele."""
    sound = santa_and_sound(db)["alert_sound"]
    if sound == "auto":
        return "sinos" if is_on(db, today) else "padrao"
    return sound


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
    return {"ligado": on, "musica": on and cfg["music"], "volume": cfg["volume"], "estilo": cfg["tv_style"],
            "faixas": cfg["tracks"], "ordem": cfg["order"], "intervalo": cfg["gap"],
            "faltam": days_to_christmas(now.date()) if on else None,
            # Papai Noel (fase 27): None = não passa na TV; "agora" muda quando alguém pede para ele passar já
            "noel": santa_for(db, "tv") if on else None,
            "noel_agora": get_setting(db, SETTING_SANTA_NOW) or ""}


def save_config(db: Database, now: datetime, actor: Person, mode: str, music: bool, volume: str,
                tv_style: str = "vermelho", tracks: list[str] | None = None, order: str = "aleatoria",
                gap: str = str(DEFAULT_GAP)) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    if mode not in MODES:
        raise ValidationError("Escolha como o tema de Natal liga: automático, ligado ou desligado.")
    if tv_style not in TV_STYLES:
        raise ValidationError("Escolha a versão do tema na TV: vermelho ou preto.")
    volume = volume.strip()
    if not volume.isdigit() or not 0 <= int(volume) <= 100:
        raise ValidationError("Volume da música: use de 0 a 100.")
    tracks = list(TRACKS) if tracks is None else [t for t in TRACKS if t in tracks]
    if not tracks:
        raise ValidationError("Deixe pelo menos uma música marcada (ou desligue a música de fundo).")
    if order not in ORDERS:
        raise ValidationError("Escolha a ordem das músicas: aleatória ou na ordem da lista.")
    gap = gap.strip()
    if not gap.isdigit() or int(gap) > GAP_MAX:
        raise ValidationError(f"Intervalo entre as músicas: use de 0 a {GAP_MAX} segundos.")
    with db.connect() as conn:
        put_setting(conn, SETTING_MODE, None if mode == "auto" else mode)
        put_setting(conn, SETTING_MUSIC, None if music else "0")
        put_setting(conn, SETTING_VOLUME, None if int(volume) == DEFAULT_VOLUME else str(int(volume)))
        put_setting(conn, SETTING_TV_STYLE, None if tv_style == "vermelho" else tv_style)
        put_setting(conn, SETTING_TRACKS, None if tracks == list(TRACKS) else ",".join(tracks))
        put_setting(conn, SETTING_ORDER, None if order == "aleatoria" else order)
        put_setting(conn, SETTING_GAP, None if int(gap) == DEFAULT_GAP else str(int(gap)))
        log_event(conn, now, actor.id, "config_natal", "config:natal",
                  f"{mode}, música {'ligada' if music else 'desligada'}, volume {int(volume)}, TV {tv_style}, "
                  f"{len(tracks)} de {len(TRACKS)} faixas")


def save_santa(db: Database, now: datetime, actor: Person, where: str, minutes: str, height: str,
               sound: bool = False) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    if where not in SANTA_WHERE or height not in SANTA_HEIGHTS:
        raise ValidationError("Escolha onde e em que altura o Papai Noel passa.")
    minutes = minutes.strip()
    if not minutes.isdigit() or not SANTA_MIN <= int(minutes) <= SANTA_MAX:
        raise ValidationError(f"Papai Noel: use de {SANTA_MIN} a {SANTA_MAX} minutos.")
    with db.connect() as conn:
        put_setting(conn, SETTING_SANTA_WHERE, None if where == "tv_app" else where)
        put_setting(conn, SETTING_SANTA_MINUTES, None if int(minutes) == DEFAULT_SANTA_MINUTES else str(int(minutes)))
        put_setting(conn, SETTING_SANTA_HEIGHT, None if height == "sorteada" else height)
        put_setting(conn, SETTING_SANTA_SOUND, "1" if sound else None)
        log_event(conn, now, actor.id, "config_natal", "config:natal",
                  f"Papai Noel: {SANTA_WHERE[where].lower()}, a cada {int(minutes)} min, {SANTA_HEIGHTS[height].lower()}")


def santa_now(db: Database, now: datetime, actor: Person) -> None:
    """Qualquer pessoa pode fazer o Papai Noel passar já na TV da sala (com o tema ligado)."""
    with db.connect() as conn:
        put_setting(conn, SETTING_SANTA_NOW, now.isoformat(timespec="seconds"))
        log_event(conn, now, actor.id, "natal_noel_agora", "config:natal", "")


def save_alert_sound(db: Database, now: datetime, actor: Person, sound: str) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    if sound not in ALERT_SOUNDS:
        raise ValidationError("Escolha um dos sons da lista.")
    with db.connect() as conn:
        put_setting(conn, SETTING_ALERT_SOUND, None if sound == "auto" else sound)
        log_event(conn, now, actor.id, "config_som_aviso", "config:som", ALERT_SOUNDS[sound])
