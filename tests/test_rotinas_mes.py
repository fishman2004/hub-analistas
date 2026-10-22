"""Fase 19: rotinas do mês (o calendário de rotinas do gestor) e a tela da TV com o zoom no dia."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import at
from hub import rotinas_mes
from hub.access import set_access
from hub.calendario import Holidays, day_items
from hub.modos import mask_titles
from hub.people import ValidationError, add_person, get_person
from hub.rotinas_mes import (by_day, create_suggested, list_categories, mark_done, month_weeks, occurs_on, parse_rule,
                             rule_label, save_category, save_routine, set_active, tv_rotinas_mes)
from hub.telas import rotation
from hub.web.app import create_app
from test_web_app import login

BASE = "http://hub-sala:8800"


@pytest.fixture
def env(db):
    kayo = add_person(db, at(7), None, "Kayo")
    bianca = add_person(db, at(7), None, "Bianca")
    ana = add_person(db, at(7), None, "Ana Souza")
    login(TestClient(create_app(db, clock=lambda: at(7)), base_url=BASE), kayo)  # Kayo vira admin
    set_access(db, at(7), get_person(db, kayo.id), bianca.id, "gestor", False)
    app = create_app(db, clock=lambda: at(12))
    cb, ca = TestClient(app, base_url=BASE), TestClient(app, base_url=BASE)
    login(cb, bianca)
    login(ca, ana)
    return db, cb, ca, get_person(db, kayo.id), get_person(db, bianca.id), get_person(db, ana.id)


def cat(db, name="Acompanhamentos"):
    return next(c for c in list_categories(db) if c.name == name)


def titles(db, day):
    return [o.routine.title for o in by_day(db, day, day).get(day, [])]


# ---------- regras ----------

def test_seeded_categories_and_contrast(db):
    names = [c.name for c in list_categories(db)]
    assert names[:3] == ["Acompanhamentos", "Gestão de equipe", "Metas"] and "APEX" in names
    assert cat(db, "APEX").text_color == "#ffffff"  # azul-marinho: texto claro
    assert cat(db, "Metas").text_color == "#10161d"  # amarelo: texto escuro


def test_business_day_rules_follow_the_managers_model(db):
    """Maio de 2026, como o print do gestor: o 1º de maio é feriado e empurra o 1º dia útil para o dia 4."""
    hol = Holidays()
    assert occurs_on({"tipo": "dia_util", "n": 1}, date(2026, 5, 4), hol)
    assert occurs_on({"tipo": "dia_util", "n": 3}, date(2026, 5, 6), hol)
    assert occurs_on({"tipo": "dia_util", "n": 5}, date(2026, 5, 8), hol)
    assert occurs_on({"tipo": "dia_util", "n": 11}, date(2026, 5, 18), hol)
    assert occurs_on({"tipo": "dia_util_fim", "n": 1}, date(2026, 5, 29), hol)
    assert occurs_on({"tipo": "dia_util_fim", "n": 3}, date(2026, 5, 27), hol)
    assert occurs_on({"tipo": "dia_util_fim", "n": 4}, date(2026, 5, 26), hol)
    assert not occurs_on({"tipo": "dia_util", "n": 30}, date(2026, 5, 29), hol)  # o mês não tem 30 dias úteis
    # semana: nunca em feriado
    assert occurs_on({"tipo": "semana", "dias": [4]}, date(2026, 5, 8), hol)
    assert not occurs_on({"tipo": "semana", "dias": [4]}, date(2026, 5, 1), hol)


def test_fixed_day_moves_to_the_next_business_day(db):
    hol = Holidays()
    # 10/10/2026 é sábado e 12/10 é feriado: vai para terça, 13/10
    assert occurs_on({"tipo": "dia", "dia": 10}, date(2026, 10, 13), hol)
    assert not occurs_on({"tipo": "dia", "dia": 10}, date(2026, 10, 10), hol)
    # 31/10/2026 é sábado e 02/11 é Finados: cai no mês seguinte, em 03/11
    assert occurs_on({"tipo": "dia", "dia": 31}, date(2026, 11, 3), hol)
    # dia 31 num mês de 30 dias: o último dia do mês (30/11/2026 é segunda)
    assert occurs_on({"tipo": "dia", "dia": 31}, date(2026, 11, 30), hol)
    assert occurs_on({"tipo": "data", "data": "2026-10-24"}, date(2026, 10, 24), hol)


def test_parse_rule_and_labels():
    assert parse_rule("semana", ["0", "3", "9"]) == {"tipo": "semana", "dias": [0, 3]}
    assert parse_rule("dia_util", n="3") == {"tipo": "dia_util", "n": 3}
    assert parse_rule("data", on="2026-10-24") == {"tipo": "data", "data": "2026-10-24"}
    for kind, kw, msg in (("semana", {}, "dia da semana"), ("dia_util_fim", {"n": "0"}, "dia útil"),
                          ("dia", {"day": "40"}, "Dia do mês"), ("data", {"on": "ontem"}, "data"), ("x", {}, "quando")):
        with pytest.raises(ValidationError, match=msg):
            parse_rule(kind, **kw)
    assert rule_label({"tipo": "semana", "dias": [0, 1, 2, 3, 4]}) == "toda semana, seg a sex"
    assert rule_label({"tipo": "semana", "dias": [0, 3]}) == "toda seg e qui"
    assert rule_label({"tipo": "dia_util_fim", "n": 1}) == "último dia útil do mês"
    assert rule_label({"tipo": "dia_util", "n": 3}) == "3º dia útil do mês"


def test_month_weeks_start_on_sunday():
    weeks = month_weeks(2026, 5)
    assert weeks[0][0] == date(2026, 4, 26) and weeks[-1][-1] == date(2026, 6, 6) and len(weeks) == 6
    assert all(len(w) == 7 for w in weeks)


# ---------- cadastro e permissões ----------

def test_only_manager_and_admins_manage(env):
    db, cb, ca, kayo, bianca, ana = env
    rule = {"tipo": "semana", "dias": [0]}
    with pytest.raises(PermissionError):
        save_routine(db, at(9), ana, None, category_id=cat(db).id, title="Blacklist", rule=rule)
    with pytest.raises(PermissionError):
        save_category(db, at(9), ana, None, "Nova", "#123456")
    r = save_routine(db, at(9), bianca, None, category_id=cat(db).id, title="  Blacklist  ", rule=rule)
    assert r.title == "Blacklist" and r.rule_text == "toda seg"
    save_routine(db, at(9), kayo, r.id, category_id=cat(db, "Metas").id, title="Blacklist", rule=rule, highlight=True,
                 owner_id=ana.id)
    r = rotinas_mes.get_routine(db, r.id)
    assert r.highlight and r.owner_id == ana.id and r.category_id == cat(db, "Metas").id
    with pytest.raises(ValidationError, match="categoria"):
        save_routine(db, at(9), kayo, None, category_id=999, title="X", rule=rule)
    with pytest.raises(ValidationError, match="o que é"):
        save_routine(db, at(9), kayo, None, category_id=cat(db).id, title=" ", rule=rule)


def test_categories(env):
    db, cb, ca, kayo, bianca, ana = env
    c = save_category(db, at(9), bianca, None, "Campanhas", "#AABBCC")
    assert c.color == "#aabbcc" and c.position == 9
    with pytest.raises(ValidationError, match="Já existe"):
        save_category(db, at(9), bianca, None, "campanhas", "#000000")
    with pytest.raises(ValidationError, match="cor"):
        save_category(db, at(9), bianca, c.id, "Campanhas", "azul")
    save_routine(db, at(9), bianca, None, category_id=c.id, title="Ativas", rule={"tipo": "semana", "dias": [1]})
    with pytest.raises(ValidationError, match="ainda tem rotinas"):
        rotinas_mes.remove_category(db, at(9), bianca, c.id)
    set_active(db, at(9), bianca, rotinas_mes.list_routines(db)[0].id, False)
    rotinas_mes.remove_category(db, at(9), bianca, c.id)
    assert "Campanhas" not in [x.name for x in list_categories(db, active_only=True)]


def test_suggested_routines_build_the_may_calendar(env):
    db, cb, ca, kayo, bianca, ana = env
    with pytest.raises(PermissionError):
        create_suggested(db, at(9), ana)
    assert create_suggested(db, at(9), bianca) == len(rotinas_mes.SUGGESTED)
    assert create_suggested(db, at(9), bianca) == 0  # já existem: não duplica
    assert titles(db, date(2026, 5, 1)) == []  # feriado
    may4 = titles(db, date(2026, 5, 4))
    # as do mês primeiro (não podem passar), depois as da semana
    assert may4[0] == "Apuração de resultados referente ao mês anterior (M-1)" and "Blacklist" in may4
    assert "Input de metas no sistema" in titles(db, date(2026, 5, 6))
    assert "Integradoras de resultados" in titles(db, date(2026, 5, 8))
    assert any("Revisão de desempenho" in t for t in titles(db, date(2026, 5, 18)))
    assert "Encerramento do período comissionado da força de vendas" in titles(db, date(2026, 5, 26))
    assert "Início de apurações e comissões" in titles(db, date(2026, 5, 27))
    assert "Devolutiva de correções das comissões" in titles(db, date(2026, 5, 29))
    assert "Campanhas" in titles(db, date(2026, 5, 5)) and "Campanhas" not in titles(db, date(2026, 5, 4))


# ---------- feito no dia ----------

def test_anyone_marks_done_only_today(env):
    db, cb, ca, kayo, bianca, ana = env
    r = save_routine(db, at(9), bianca, None, category_id=cat(db).id, title="Desempenho", rule={"tipo": "semana", "dias": [0]})
    tue = save_routine(db, at(9), bianca, None, category_id=cat(db).id, title="Campanhas", rule={"tipo": "semana", "dias": [1]})
    mark_done(db, at(10), ana, r.id)
    mark_done(db, at(11), kayo, r.id)  # já feita: fica quem marcou primeiro
    o = by_day(db, date(2026, 10, 19), date(2026, 10, 19))[date(2026, 10, 19)][0]
    assert o.done and o.done_by == ana.id and o.done_at == at(10)
    assert not by_day(db, date(2026, 10, 26), date(2026, 10, 26))[date(2026, 10, 26)][0].done  # outra segunda
    with pytest.raises(ValidationError, match="não é de hoje"):
        mark_done(db, at(10), ana, tue.id)
    mark_done(db, at(12), ana, r.id, False)
    assert not by_day(db, date(2026, 10, 19), date(2026, 10, 19))[date(2026, 10, 19)][0].done
    set_active(db, at(12), bianca, r.id, False)
    with pytest.raises(ValidationError, match="não encontrada"):
        mark_done(db, at(12), ana, r.id)


# ---------- TV ----------

def test_tv_screen_leaves_rotation_without_routines(env):
    db, *_ = env
    assert tv_rotinas_mes(db, at(12)) is None
    assert "rotinas-mes" not in [s["id"] for s in rotation(db, at(12))["screens"]]


def test_tv_screen_month_today_and_next(env):
    db, cb, ca, kayo, bianca, ana = env
    create_suggested(db, at(9), bianca)
    first = rotinas_mes.list_routines(db)[0]
    r = save_routine(db, at(9), bianca, None, category_id=cat(db, "APEX").id, title="Reunião", owner_id=ana.id,
                     rule={"tipo": "data", "data": "2026-10-19"}, highlight=True)
    mark_done(db, at(10), kayo, r.id)
    data = tv_rotinas_mes(db, at(12))
    assert data["titulo"] == "Calendário do mês · outubro de 2026"
    days = [d for w in data["semanas"] for d in w]
    assert days[0]["data"] == "2026-09-27" and len(data["semanas"]) == 5
    assert next(d for d in days if d["data"] == "2026-10-12")["feriado"] == "Nossa Senhora Aparecida"
    hoje = data["hoje"]
    assert hoje["hoje"] and hoje["rotulo"] == "Hoje · segunda, 19/10" and hoje["feitas"] == 1
    reuniao = hoje["itens"][0]
    assert reuniao == {"categoria": "APEX", "cor": "#14295a", "texto_cor": "#ffffff", "titulo": "Reunião",
                       "destaque": True, "feita": True, "quem": {"initials": ana.initials, "color": ana.color},
                       "feita_por": kayo.initials}
    assert data["proximo"]["rotulo"] == "Amanhã, 20/10" and data["proximo"]["itens"]
    assert first.title in [i["titulo"] for d in days for i in d["itens"]]
    assert "rotinas-mes" in [s["id"] for s in rotation(db, at(12))["screens"]]


def test_tv_month_shows_team_events_even_without_routines(env):
    """Fase 24: o Kayo cadastrou só compromissos na Agenda e esperava o mês com o zoom na TV."""
    from hub.calendario import save_event

    db, cb, ca, kayo, bianca, ana = env
    save_event(db, at(9), kayo, None, title="Teste", kind="reuniao", starts_on=date(2026, 10, 19), people=[ana.id])
    save_event(db, at(9), kayo, None, title="Segredo", kind="entrega", starts_on=date(2026, 10, 22), starts_at="14:00",
               reserved=True)
    save_event(db, at(9), kayo, None, title="Só meu", kind="evento", starts_on=date(2026, 10, 19), visibility="pessoal")
    data = tv_rotinas_mes(db, at(12))
    assert data["titulo"] == "Calendário do mês · outubro de 2026"
    assert data["hoje"]["itens"] == [{"tipo": "compromisso", "categoria": "Reunião", "titulo": "Teste", "hora": "dia todo",
                                      "pessoas": [{"initials": ana.initials, "color": ana.color}]}]
    assert data["hoje"]["total"] == 0  # a conta "feitas" é só das rotinas
    days = {d["data"]: d for w in data["semanas"] for d in w}
    assert [(i["titulo"], i["hora"]) for i in days["2026-10-22"]["itens"]] == [("Compromisso reservado", "14:00")]
    assert "Só meu" not in str(data) and "Segredo" not in str(data)
    assert "rotinas-mes" in [s["id"] for s in rotation(db, at(12))["screens"]]
    # rotinas primeiro, depois os compromissos
    create_suggested(db, at(9), bianca)
    itens = tv_rotinas_mes(db, at(12))["hoje"]["itens"]
    assert itens[-1]["tipo"] == "compromisso" and "tipo" not in itens[0]


def test_visit_mode_hides_the_texts(env):
    db, cb, ca, kayo, bianca, ana = env
    create_suggested(db, at(9), bianca)
    payload = {"columns": {"todo": [], "doing": [], "done": []}, **rotation(db, at(12))}
    mask_titles(payload)
    s = next(s for s in payload["screens"] if s["id"] == "rotinas-mes")
    items = [i for w in s["data"]["semanas"] for d in w for i in d["itens"]] + s["data"]["hoje"]["itens"]
    assert items and all(i["titulo"] == "" and i["categoria"] for i in items)


# ---------- app ----------

def test_calendar_filter_shows_month_routines(env):
    db, cb, ca, kayo, bianca, ana = env
    create_suggested(db, at(9), bianca)
    day = date(2026, 10, 19)
    assert not [i for i in day_items(db, ana, day, day, day).get(day, []) if i.kind == "rotina_mes"]
    items = [i for i in day_items(db, ana, day, day, day, ("rotinas_mes",))[day]]
    assert items[0].title.startswith("Acompanhamentos: ") or ":" in items[0].title
    assert all(i.kind == "rotina_mes" and i.color for i in items)


def test_web_pages_and_permissions(env):
    db, cb, ca, kayo, bianca, ana = env
    page = ca.get("/calendario?visao=rotinas")
    assert page.status_code == 200 and "Nenhuma rotina do mês cadastrada" in page.text
    assert "Cadastrar rotinas do mês" not in page.text  # analista não cadastra
    assert ca.post("/calendario/rotinas-do-mes/sugeridas").status_code == 403
    assert ca.post("/calendario/rotinas-do-mes", data={"category_id": "1", "title": "X", "tipo": "semana",
                                                        "dias": ["0"]}).status_code == 403
    r = cb.post("/calendario/rotinas-do-mes", data={"category_id": str(cat(db).id), "title": "Blacklist",
                                                     "tipo": "semana", "dias": ["0", "3"]}, follow_redirects=False)
    assert r.status_code == 303
    bad = cb.post("/calendario/rotinas-do-mes", data={"category_id": str(cat(db).id), "title": "Sem dia",
                                                       "tipo": "semana"})
    assert bad.status_code == 422 and "Marque pelo menos um dia" in bad.text and "Sem dia" in bad.text
    routine = rotinas_mes.list_routines(db)[0]
    cadastro = cb.get(f"/calendario/rotinas-do-mes?editar={routine.id}")
    assert "Editar rotina do mês" in cadastro.text and "toda seg e qui" in cadastro.text
    view = ca.get("/calendario?visao=rotinas")
    assert "Hoje, 19/10" in view.text and "Blacklist" in view.text and "✓ Feita" in view.text
    assert ca.post(f"/calendario/rotinas-do-mes/{routine.id}/feita", data={"feita": "1"},
                   follow_redirects=False).status_code == 303
    assert "1 de 1 feitas" in ca.get("/calendario?visao=rotinas").text
    assert cb.post("/calendario/rotinas-do-mes/categorias", data={"nome": "Campanhas", "cor": "#123456"},
                   follow_redirects=False).status_code == 303
    assert "Campanhas" in cb.get("/calendario/rotinas-do-mes").text
    # outro mês: navega sem erro
    assert ca.get("/calendario?visao=rotinas&data=2026-05-01").status_code == 200


def test_database_from_1_10_gains_the_tables(tmp_path):
    import sqlite3
    from hub.db import Database
    path = tmp_path / "hub.db"
    d = Database(path)
    d.init()
    add_person(d, at(7), None, "Kayo")
    with sqlite3.connect(path) as conn:
        for table in ("trail_notes", "month_routine_notes", "trail_marks", "trail_blocks", "month_routine_marks", "month_routines", "month_categories"):
            conn.execute(f"DROP TABLE {table}")
        conn.execute("PRAGMA user_version = 12")
    d.init()
    assert len(list_categories(d)) == 8 and (tmp_path / "copias").is_dir()
