"""Fase 21: menu em grupos, "Ir para…", avisos que somem, quadro vivo e as animações (app e TV).
O movimento em si é do navegador; aqui fica o que o servidor entrega e as regras de sempre (sem internet)."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import cadastro, trilha
from hub.access import set_access
from hub.demands import create_demand
from hub.people import add_person, get_person
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"
STATIC = Path(__file__).parent.parent / "hub" / "web" / "static"


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    ana = add_person(db, at(7), None, "Ana Souza")
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url=BASE), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", False)
    app = create_app(db, clock=lambda: at(10))
    clients = {}
    for p in (kayo, bianca, ana):
        clients[p.name] = login(TestClient(app, base_url=BASE), p)
    return db, clients, *(get_person(db, p.id) for p in (kayo, bianca, ana))


def nav(html):
    return html[html.index('<nav aria-label="Menu principal"'):html.index("</nav>")]


def test_menu_in_groups(env):
    db, c, kayo, bianca, ana = env
    menu = nav(c["Ana Souza"].get("/calendario").text)
    groups = re.findall(r"<summary>([^<]+)", menu)
    assert groups == ["Dia a dia", "Planejamento", "Dados", "TV e celular"]  # sem "Gestão" para o analista
    for href in ("/", "/trilha", "/demandas", "/notas", "/historico", "/rotinas", "/prioridades", "/calendario",
                 "/paineis", "/horas", "/envios", "/tv-da-sala", "/celular"):
        assert f'href="{href}"' in menu
    assert 'href="/gestor"' not in menu and 'href="/pessoas"' not in menu
    # o grupo da página atual fica marcado, e o link dela também
    assert '<details class="grupo aqui">\n        <summary>Planejamento' in menu
    assert 'aria-current="page">Calendário' in menu
    # Quadro e Trilha ficam fora dos grupos
    assert menu.index('href="/trilha"') < menu.index("<details")


def test_management_group(env):
    db, c, kayo, bianca, ana = env
    gestora = nav(c["Bianca"].get("/").text)
    assert "<summary>Gestão" in gestora and 'href="/gestor"' in gestora and 'href="/pessoas"' not in gestora
    admin = nav(c["Kayo"].get("/pessoas").text)
    assert 'href="/pessoas"' in admin and 'href="/configuracoes"' in admin
    assert '<details class="grupo aqui">\n        <summary>Gestão' in admin
    cadastro.request_signup(db, at(9), "Nova Pessoa", "", "2468", "2468")
    admin = nav(c["Kayo"].get("/").text)
    assert re.search(r'<summary>Gestão <span class="contador"[^>]*>1</span>', admin)  # o pedido aparece no grupo fechado


def test_scripts_and_quick_jump(env):
    db, c, kayo, bianca, ana = env
    html = c["Ana Souza"].get("/").text
    assert 'src="/static/hub.js?v=' in html and 'id="ir-para-abrir"' in html
    assert c["Ana Souza"].get("/static/hub.js").status_code == 200


def test_live_board_and_trail_have_keys(env):
    db, c, kayo, bianca, ana = env
    d = create_demand(db, at(8), ana.id, title="Conferir metas", owner_id=ana.id)
    trilha.create_suggested(db, at(7), ana, ana.id)
    html = c["Ana Souza"].get("/").text
    assert f'data-vivo="d:{d.id}" data-estado="todo"' in html
    first = trilha.my_trail(db, ana.id, at(10))[0]
    assert f'data-vivo="t:{first.block.id}" data-estado="{first.status}"' in html
    # a atualização de 10 s traz as mesmas chaves (é ela que o app.js compara)
    assert f'data-vivo="d:{d.id}"' in c["Ana Souza"].get("/parcial/quadro").text


def test_manager_numbers_count_up(env):
    db, c, kayo, bianca, ana = env
    create_demand(db, at(8), ana.id, title="Conferir metas", owner_id=ana.id)
    html = c["Bianca"].get("/gestor").text
    assert '<span class="numero" data-contar="1">1</span><span>a fazer</span>' in html


def test_success_message_still_rendered_by_the_server(env):
    """Sem JavaScript, o aviso continua na página; o hub.js só o leva para o canto e faz sumir."""
    db, c, kayo, bianca, ana = env
    html = c["Ana Souza"].get("/trilha/montar?ok=Bloco%20salvo.").text
    assert '<div class="sucesso" role="status">Bloco salvo.</div>' in html


def test_nothing_from_the_internet():
    for name in ("hub.js", "app.js", "tv.js", "app.css", "tv.css"):
        text = (STATIC / name).read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!www\.w3\.org)", text), name


def test_motion_respects_reduced_motion():
    for name in ("app.css", "tv.css"):
        assert "prefers-reduced-motion: reduce" in (STATIC / name).read_text(encoding="utf-8"), name
    assert "prefers-reduced-motion" in (STATIC / "hub.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in (STATIC / "tv.js").read_text(encoding="utf-8")
