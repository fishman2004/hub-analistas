"""Justificativas (pedido do Kayo ao confirmar a v5): marcar feita continua só hoje, mas dá para escrever por que
uma rotina do mês ficou sem fazer (hoje ou nos últimos 31 dias) e por que um bloco da trilha de hoje ficou vermelho
ou âmbar."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import rotinas_mes, trilha
from hub.access import set_access
from hub.db import events
from hub.modos import mask_titles
from hub.people import ValidationError, add_person, get_person
from hub.telas import rotation
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"
SEG = date(2026, 10, 19)


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    ana = add_person(db, at(7), None, "Ana Souza")
    caio = add_person(db, at(7), None, "Caio Lopes")
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url=BASE), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", False)
    return db, *(get_person(db, p.id) for p in (kayo, bianca, ana, caio))


def monday_routine(db, bianca):
    cat = rotinas_mes.list_categories(db)[0]
    return rotinas_mes.save_routine(db, at(7), bianca, None, category_id=cat.id, title="Conferir metas",
                                    rule={"tipo": "semana", "dias": [0]})


def occ(db, r, day):
    return next(o for o in rotinas_mes.by_day(db, day, day)[day] if o.routine.id == r.id)


# ---------- rotinas do mês ----------

def test_month_routine_note_today_and_past_days(env):
    db, kayo, bianca, ana, caio = env
    r = monday_routine(db, bianca)
    rotinas_mes.justify(db, at(10), ana, r.id, SEG, "  Sistema fora do ar \r\n até 11h ")
    o = occ(db, r, SEG)
    assert (o.note, o.note_by, o.done) == ("Sistema fora do ar\naté 11h", ana.id, False)
    # uma semana depois, o dia 19 ainda pode ser justificado (e o texto é trocado)
    rotinas_mes.justify(db, at(10, day=26), caio, r.id, SEG, "Feita só a pasta A")
    assert (occ(db, r, SEG).note, occ(db, r, SEG).note_by) == ("Feita só a pasta A", caio.id)
    rotinas_mes.justify(db, at(10, day=26), caio, r.id, SEG, "   ")  # vazio tira
    assert occ(db, r, SEG).note == ""
    kinds = [e["kind"] for e in events(db, date(2026, 10, 19), date(2026, 10, 26))]
    assert "rotina_mes_justificada" in kinds and "rotina_mes_justificativa_tirada" in kinds


def test_month_routine_note_rules(env):
    db, kayo, bianca, ana, caio = env
    r = monday_routine(db, bianca)
    with pytest.raises(ValidationError, match="não acontece nesse dia"):
        rotinas_mes.justify(db, at(10, day=21), ana, r.id, date(2026, 10, 20), "x")  # terça
    with pytest.raises(ValidationError, match="dia que já passou"):
        rotinas_mes.justify(db, at(10), ana, r.id, date(2026, 10, 26), "x")  # futuro
    with pytest.raises(ValidationError, match="últimos 31 dias"):
        rotinas_mes.justify(db, at(10), ana, r.id, date(2026, 9, 14), "x")
    with pytest.raises(ValidationError, match="muito longa"):
        rotinas_mes.justify(db, at(10), ana, r.id, SEG, "x" * 301)


def test_month_routine_note_pages(env):
    db, kayo, bianca, ana, caio = env
    r = monday_routine(db, bianca)
    c = login(TestClient(create_app(db, clock=lambda: at(10, day=26)), base_url=BASE), ana)
    page = c.get("/calendario?visao=rotinas").text
    assert "Hoje, 26/10" in page and "💬 Justificar" in page
    assert 'href="/calendario?visao=rotinas&data=2026-10-19&ver=2026-10-19#hoje"' in page  # dia que passou
    r1 = c.post(f"/calendario/rotinas-do-mes/{r.id}/justificar", data={"dia": "2026-10-19", "texto": "Faltou o arquivo"},
                follow_redirects=False)
    assert r1.status_code == 303 and "ver=2026-10-19" in r1.headers["location"]
    past = c.get("/calendario?visao=rotinas&data=2026-10-19&ver=2026-10-19").text
    assert "Dia 19/10 · já passou" in past and "💬 Faltou o arquivo" in past and "✓ Feita" not in past
    assert 'title="Justificativa: Faltou o arquivo"' in c.get("/calendario?visao=rotinas").text  # marca na grade
    assert c.post(f"/calendario/rotinas-do-mes/{r.id}/justificar",
                  data={"dia": "2026-10-20", "texto": "x"}).status_code == 422
    c.post(f"/calendario/rotinas-do-mes/{r.id}/justificar", data={"dia": "2026-10-19", "texto": "a", "tirar": "1"})
    assert occ(db, r, SEG).note == ""


def test_tv_month_screen_never_shows_the_note(env):
    db, kayo, bianca, ana, caio = env
    r = monday_routine(db, bianca)
    rotinas_mes.justify(db, at(10), ana, r.id, SEG, "Motivo pessoal")
    assert "Motivo pessoal" not in str(rotation(db, at(12)))


# ---------- trilha ----------

def bloco(db, person, start="09:00", end="10:00", title="PHD", **kw):
    return trilha.save_block(db, at(7), person, None, person_id=person.id, weekdays=[0, 1, 2, 3, 4],
                             starts_at=start, ends_at=end, title=title, **kw)


def step(db, person, b, now):
    return next(s for s in trilha.my_trail(db, person.id, now) if s.block.id == b.id)


def test_trail_note(env):
    db, kayo, bianca, ana, caio = env
    b = bloco(db, ana)
    with pytest.raises(ValidationError, match="ainda não começou"):
        trilha.justify(db, at(8), ana, b.id, "x")
    with pytest.raises(PermissionError):
        trilha.justify(db, at(11), caio, b.id, "x")  # colega não
    trilha.justify(db, at(11), bianca, b.id, "Reunião com o gerente")  # o gestor sim
    s = step(db, ana, b, at(11))
    assert (s.status, s.note, s.note_by) == ("nao_feito", "Reunião com o gerente", bianca.id)
    assert trilha.counts([s])["justificados"] == 1
    trilha.mark(db, at(11, 5), ana, b.id)  # marcou depois: âmbar e continua justificado
    assert trilha.counts(trilha.my_trail(db, ana.id, at(11, 6)))["justificados"] == 1
    # no dia seguinte a justificativa não aparece (é do dia) e o resumo conta o que foi justificado
    assert step(db, ana, b, at(11, day=20)).note == ""
    row = next(x for x in trilha.week_summary(db, at(12, day=20)) if x["pessoa"].id == ana.id)
    assert (row["atrasados"], row["justificados"]) == (1, 1)
    pausa = bloco(db, ana, "12:00", "13:00", "Intervalo", icon="pausa", kind="pausa")
    with pytest.raises(ValidationError, match="intervalo"):
        trilha.justify(db, at(12, 30), ana, pausa.id, "x")


def test_trail_note_pages_and_tv(env):
    db, kayo, bianca, ana, caio = env
    b = bloco(db, ana)
    app = create_app(db, clock=lambda: at(10, 30))
    ca, cc = TestClient(app, base_url=BASE), TestClient(app, base_url=BASE)
    login(ca, ana)
    login(cc, caio)
    assert "💬 Justificar" in ca.get("/").text
    r = ca.post(f"/trilha/{b.id}/justificar", data={"texto": "Cliente ligou", "volta": "/"}, follow_redirects=False)
    assert r.headers["location"].startswith("/?ok=") and r.headers["location"].endswith("#minha-trilha")
    home = ca.get(r.headers["location"]).text
    assert "Justificativa salva." in home and "💬 Justificado" in home and "Cliente ligou" in home
    assert cc.post(f"/trilha/{b.id}/justificar", data={"texto": "x"}).status_code == 403
    assert "Ana Souza justificou o bloco 09:00 PHD da trilha de Ana Souza" in ca.get("/historico").text
    page = cc.get("/trilha").text  # o colega vê que foi justificado, sem o botão
    assert "💬 Justificado" in page and 'action="/trilha/%d/justificar"' % b.id not in page
    # a TV não mostra o texto
    payload = rotation(db, at(10, 30))
    assert "Cliente ligou" not in str(payload)
    mask_titles({"columns": {"todo": [], "doing": [], "done": []}, **payload})
    ca.post(f"/trilha/{b.id}/justificar", data={"texto": "x", "tirar": "1"})
    assert step(db, ana, b, at(10, 31)).note == ""
