"""Tema de Natal (fase 27): liga sozinho em dezembro, liga/desliga em Configurações, música só na TV da sala."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from hub import natal
from hub.access import create_pin
from hub.modos import list_modes
from hub.people import add_person, get_person
from hub.web.app import create_app

BASE = "http://hub-sala:8800"
NOVEMBRO = datetime(2026, 11, 25, 10, 0)
DEZEMBRO = datetime(2026, 12, 10, 10, 0)


def team(db, now):
    ana = add_person(db, now, None, "Ana Souza")
    bruno = add_person(db, now, None, "Bruno Reis")
    create_pin(db, now, ana.id, "1234", "1234")  # a primeira a criar o PIN vira administradora
    create_pin(db, now, bruno.id, "1234", "1234")
    return get_person(db, ana.id), get_person(db, bruno.id)


def login(app, person):
    c = TestClient(app, base_url=BASE)
    c.post(f"/entrar/{person.id}", data={"pin": "1234"})
    return c


@pytest.mark.parametrize("dia, ligado", [
    (date(2026, 11, 30), False), (date(2026, 12, 1), True), (date(2026, 12, 31), True),
    (date(2027, 1, 6), True), (date(2027, 1, 7), False), (date(2026, 7, 1), False),
])
def test_auto_season_is_december_to_epiphany(db, dia, ligado):
    assert natal.is_on(db, dia) is ligado


def test_days_to_christmas():
    assert natal.days_to_christmas(date(2026, 11, 25)) == 30
    assert natal.days_to_christmas(date(2026, 12, 25)) == 0
    assert natal.days_to_christmas(date(2026, 12, 26)) == 364


def test_admin_turns_it_on_now_and_off(db):
    ana, bruno = team(db, NOVEMBRO)
    with pytest.raises(PermissionError):
        natal.save_config(db, NOVEMBRO, bruno, "ligado", True, "25")
    natal.save_config(db, NOVEMBRO, ana, "ligado", True, "40")
    assert natal.is_on(db, NOVEMBRO.date()) and natal.config(db)["volume"] == 40
    natal.save_config(db, DEZEMBRO, ana, "desligado", True, "40")
    assert not natal.is_on(db, DEZEMBRO.date())
    with pytest.raises(natal.ValidationError):
        natal.save_config(db, NOVEMBRO, ana, "ligado", True, "150")
    with pytest.raises(natal.ValidationError):
        natal.save_config(db, NOVEMBRO, ana, "sempre", True, "20")


def test_app_wears_the_theme_only_when_on(db):
    ana, _ = team(db, NOVEMBRO)
    c = login(create_app(db, clock=lambda: NOVEMBRO), ana)
    html = c.get("/").text
    # fora da época, sem o tema; o CSS e o botão ficam prontos (escondidos) para quem escolher "Natal" no Tema
    assert 'class="natal"' not in html
    natal.save_config(db, NOVEMBRO, ana, "ligado", True, "25")
    html = c.get("/").text
    assert '<html lang="pt-BR" class="natal">' in html and "natal.css" in html and 'id="natal-som"' in html
    # a tela de entrar também ganha o tema
    assert 'class="natal"' in TestClient(create_app(db, clock=lambda: NOVEMBRO), base_url=BASE).get("/entrar").text


def test_december_turns_on_by_itself(db):
    ana, _ = team(db, DEZEMBRO)
    assert 'class="natal"' in login(create_app(db, clock=lambda: DEZEMBRO), ana).get("/").text


def test_tv_payload(db):
    ana, _ = team(db, NOVEMBRO)
    app = create_app(db, clock=lambda: NOVEMBRO)
    tv = TestClient(app, base_url=BASE)
    assert tv.get("/api/tv").json()["natal"] == {"ligado": False, "musica": False, "volume": 25, "estilo": "vermelho",
                                                 "faltam": None, "noel": None, "noel_agora": ""}
    natal.save_config(db, NOVEMBRO, ana, "ligado", True, "30")
    assert tv.get("/api/tv").json()["natal"] == {"ligado": True, "musica": True, "volume": 30, "estilo": "vermelho",
                                                 "faltam": 30, "noel": {"minutos": 6, "altura": "sorteada"},
                                                 "noel_agora": ""}
    natal.save_config(db, NOVEMBRO, ana, "ligado", False, "30", "preto")
    assert tv.get("/api/tv").json()["natal"]["musica"] is False
    assert tv.get("/api/tv").json()["natal"]["estilo"] == "preto"
    html = tv.get("/tv").text
    assert "natal.js" in html and "natal.css" in html and 'id="natal-contagem"' in html


def test_mode_without_sound_stops_the_music(db):
    ana, _ = team(db, DEZEMBRO)
    app = create_app(db, clock=lambda: DEZEMBRO)
    reuniao = next(m for m in list_modes(db) if not m.sound)
    admin = login(app, ana)
    assert TestClient(app, base_url=BASE).get("/api/tv").json()["natal"]["musica"] is True
    admin.post("/tv-da-sala/modo", data={"modo": str(reuniao.id), "ate": "dia"})
    payload = TestClient(app, base_url=BASE).get("/api/tv").json()
    assert payload["modo"]["nome"] == reuniao.name
    # a música para junto com o som do aviso; o visual continua
    assert payload["natal"]["ligado"] is True and payload["natal"]["musica"] is False


def test_config_page_and_route(db):
    ana, bruno = team(db, NOVEMBRO)
    app = create_app(db, clock=lambda: NOVEMBRO)
    assert login(app, bruno).post("/configuracoes/natal", data={"modo": "ligado", "volume": "25"}).status_code == 403
    admin = login(app, ana)
    html = admin.get("/configuracoes").text
    assert "Tema de Natal" in html and 'id="natal-ouvir"' in html
    r = admin.post("/configuracoes/natal", data={"modo": "ligado", "musica": "1", "volume": "35"})
    assert r.status_code == 200 and "Salvo." in r.text and 'class="natal"' in r.text
    assert natal.config(db) == {"mode": "ligado", "music": True, "volume": 35, "tv_style": "vermelho",
                                 "santa_where": "tv_app", "santa_minutes": 6, "santa_height": "sorteada",
                                 "alert_sound": "auto"}
    admin.post("/configuracoes/natal", data={"modo": "ligado", "musica": "1", "volume": "35", "tv": "preto"})
    assert natal.config(db)["tv_style"] == "preto"
    assert admin.post("/configuracoes/natal", data={"modo": "ligado", "volume": "35", "tv": "azul"}).status_code == 422
    r = admin.post("/configuracoes/natal", data={"modo": "ligado", "volume": "abc"})
    assert r.status_code == 422 and "Volume da música" in r.text
    # sem a caixinha marcada, a música fica desligada; e fica no histórico
    admin.post("/configuracoes/natal", data={"modo": "auto", "volume": "25"})
    assert {k: natal.config(db)[k] for k in ("mode", "music", "volume", "tv_style")} == {
        "mode": "auto", "music": False, "volume": 25, "tv_style": "vermelho"}
    assert "mudou o tema de Natal" in admin.get("/historico").text


def test_static_files_are_served(db):
    c = TestClient(create_app(db, clock=lambda: NOVEMBRO), base_url=BASE)
    js = c.get("/static/natal.js").text
    assert "AudioContext" in js and "Jingle Bells" in js and "http" not in js.split("// ---------- músicas")[1]
    assert c.get("/static/natal-papai-noel.svg").status_code == 200
    assert c.get("/static/natal-gorro.svg").status_code == 200
    css = c.get("/static/natal.css").text
    assert "prefers-reduced-motion" in css


def test_personal_theme_offers_both_christmas_options(db):
    js = TestClient(create_app(db, clock=lambda: NOVEMBRO), base_url=BASE).get("/static/tema.js").text
    assert '"natal", "natal-preto"' in js and "Natal preto" in js
    css = TestClient(create_app(db, clock=lambda: NOVEMBRO), base_url=BASE).get("/static/natal.css").text
    assert 'html.natal[data-tema="natal-preto"]' in css and "body[data-tv].natal-preto" in css


def test_santa_where_when_and_height(db):
    ana, bruno = team(db, NOVEMBRO)
    app = create_app(db, clock=lambda: NOVEMBRO)
    natal.save_config(db, NOVEMBRO, ana, "ligado", True, "25")
    admin = login(app, ana)
    assert 'data-noel-minutos="6" data-noel-altura="sorteada"' in admin.get("/").text
    assert login(app, bruno).post("/configuracoes/natal/noel", data={"onde": "tv", "minutos": "3", "altura": "topo"}).status_code == 403
    r = admin.post("/configuracoes/natal/noel", data={"onde": "tv", "minutos": "3", "altura": "topo"})
    assert r.status_code == 200 and "Salvo." in r.text
    tv = TestClient(app, base_url=BASE)
    assert tv.get("/api/tv").json()["natal"]["noel"] == {"minutos": 3, "altura": "topo"}
    assert "data-noel-minutos" not in admin.get("/").text  # só na TV: o app não recebe
    admin.post("/configuracoes/natal/noel", data={"onde": "app", "minutos": "10", "altura": "baixo"})
    assert tv.get("/api/tv").json()["natal"]["noel"] is None
    assert 'data-noel-minutos="10" data-noel-altura="baixo"' in admin.get("/").text
    r = admin.post("/configuracoes/natal/noel", data={"onde": "tv", "minutos": "0", "altura": "topo"})
    assert r.status_code == 422 and "de 1 a 60 minutos" in r.text
    # Passar agora: só com o Papai Noel na TV
    assert "desligado na TV" in admin.post("/configuracoes/natal/noel-agora").text
    admin.post("/configuracoes/natal/noel", data={"onde": "tv_app", "minutos": "6", "altura": "sorteada"})
    r = admin.post("/configuracoes/natal/noel-agora")
    assert r.status_code == 200 and "passa na TV da sala" in r.text
    assert tv.get("/api/tv").json()["natal"]["noel_agora"] == NOVEMBRO.isoformat(timespec="seconds")
    assert "fez o Papai Noel passar na TV" in admin.get("/historico").text


def test_alert_sound_selector(db):
    ana, bruno = team(db, NOVEMBRO)
    app = create_app(db, clock=lambda: NOVEMBRO)
    tv = TestClient(app, base_url=BASE)
    assert tv.get("/api/tv").json()["som_aviso"] == "padrao"  # automático, fora do Natal: o de sempre
    natal.save_config(db, NOVEMBRO, ana, "ligado", True, "25")
    assert tv.get("/api/tv").json()["som_aviso"] == "sinos"  # automático, no Natal: sinos
    admin = login(app, ana)
    html = admin.get("/configuracoes").text
    assert 'id="som-aviso"' in html and "Sino de igreja" in html and 'id="som-ouvir"' in html
    assert login(app, bruno).post("/configuracoes/som-aviso", data={"som": "igreja"}).status_code == 403
    assert admin.post("/configuracoes/som-aviso", data={"som": "igreja"}).status_code == 200
    assert tv.get("/api/tv").json()["som_aviso"] == "igreja"
    natal.save_config(db, NOVEMBRO, ana, "desligado", True, "25")
    assert tv.get("/api/tv").json()["som_aviso"] == "igreja"  # escolhido: vale o ano todo
    assert admin.post("/configuracoes/som-aviso", data={"som": "buzina"}).status_code == 422
    assert "mudou o som dos avisos" in admin.get("/historico").text
    js = tv.get("/static/natal.js").text
    for som in ("igreja", "carrilhao", "caixinha", "guizos"):
        assert som + "()" in js
