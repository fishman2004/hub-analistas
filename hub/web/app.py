"""Servidor do Hub: a tela da TV e o app dos analistas."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlencode, urlsplit

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..access import (ROLES, change_pin, create_pin, end_session, has_admin, reset_pin, session_end, session_person,
                      set_access, start_session, verify_pin)
from ..db import Database, events, first_event_day, log_event
from ..demands import (CHANGES_SEP, COLUMN_LABELS, COLUMNS, FOLDERS, MAX_DETAILS, RESERVED_TEXT, all_demands, board,
                       can_remove_file, can_see, create_demand, delete_demand, ensure_demand, find_card, find_demand,
                       is_overdue, is_owner, move_demand, search_demands, toggle_folder, touch_demand, tv_card, update_demand)
from .. import anexos, cadastro, calendario, celular, drive, modos, notas, pastas, phd, rotinas_mes, trilha
from ..people import (PALETTE, Person, ValidationError, add_person, deactivate_person, get_person, list_people,
                      update_person)
from ..envios import (channel_text, count_text, history_folder, pombo_config, runs_of_day, save_pombo_config,
                      status_text, target_text, who_is_who)
from ..envios import store_for as envios_store
from ..gestor import DUE_FILTERS, can_open, filter_demands, team_summary
from .. import horas
from ..paineis import STALE_MAX, STALE_MIN, panel_config, save_panel_config, save_upload, stale_hours, store_for
from ..presence import STATUSES, presence_board, set_status
from ..rotinas import (WEEKDAY_LABELS, alerts_today, can_manage, create_suggested, get_routine, list_routines,
                       remove_routine, save_routine, set_routine_active, start_test_alert, tv_alerts, weekdays_label)
from ..qr import qr_svg
from ..prioridades import (DEFAULT_LIST, add_priority, by_folder, can_mark, can_remove, create_default_list, is_late,
                           is_month, last_day, list_month, mark_done, month_label, month_of, parse_due_day, parse_steps,
                           past_months,
                           remove_priority, undo_done)
from ..telas import MAX_SECONDS, MIN_SECONDS, PAGE_MAX, PAGE_MIN, rotation, save_screen_config, screen_config
from .. import tvcontrole

HERE = Path(__file__).parent
MONTHS = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
          "Novembro", "Dezembro"]
COOKIE = "hub_sessao"
LOGIN_MAX_FAILURES = 10  # erros seguidos de um mesmo aparelho, em qualquer nome...
LOGIN_WINDOW_MINUTES = 15  # ...dentro deste tempo: o aparelho espera até o erro mais antigo sair da conta
SIGNUPS_PER_DEVICE = 3  # pedidos de cadastro por aparelho, por hora
PHONE_PORT = 8800  # a porta do Hub (hub/__main__.py), para o endereço do celular


def create_app(db: Database, clock: Callable[[], datetime] = datetime.now) -> FastAPI:
    app = FastAPI(title="Hub dos Analistas", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    # ?v=versão nos arquivos estáticos: a TV não fica presa a um CSS/JS antigo depois de atualizar
    templates.env.globals["version"] = __version__

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        # outro site aberto no navegador de alguém não pode mandar formulários para o Hub
        if request.method == "POST":
            source = request.headers.get("origin") or request.headers.get("referer")
            if source and urlsplit(source).netloc != request.headers.get("host"):
                return Response("Origem não permitida.", status_code=403)
        return await call_next(request)

    # ---------- TV ----------

    @app.get("/tv", response_class=HTMLResponse)
    def tv(request: Request):
        # só o esqueleto: os dados chegam pelo /api/tv, já sem nada de demanda reservada
        return templates.TemplateResponse(request, "tv.html", {})

    seen = tvcontrole.Seen()  # qual tela está na TV agora (só na memória)

    @app.get("/tv/exportar", response_class=HTMLResponse)
    def tv_exportar(request: Request, tela: str = "todas", clara: str = ""):
        """Exportar em PDF (fase 15): a TV desenhada em folhas, com os mesmos dados do /api/tv, e a janela
        de impressão do navegador ("Salvar como PDF"). Pede PIN e fica no histórico: o PDF sai da sala."""
        user = me(request)
        if user is None:
            return to_login()
        now = clock()
        if tela == "agora":
            current = seen.get(now)
            if current is None:
                return tv_room_page(request, user, 422, error="A TV da sala não está conectada agora: escolha "
                                    "uma tela da lista para exportar.")
            tela = current["tela"]
        if tela != "todas" and tela not in tvcontrole.LABELS:
            return Response(status_code=404)
        label = "Todas as telas" if tela == "todas" else tvcontrole.LABELS[tela]
        with db.connect() as conn:
            log_event(conn, now, user.id, "tv_exportada", "tv", label)
        light = clara == "1"
        other = {"tela": tela, **({} if light else {"clara": "1"})}
        return templates.TemplateResponse(request, "tv.html", {"exportar": {
            "tela": tela, "rotulo": label, "clara": light, "outra_versao": f"/tv/exportar?{urlencode(other)}",
            "titulo": f"Hub - {label} - {now:%Y-%m-%d %Hh%M}",  # o Edge sugere o título como nome do PDF
            "rodape": f"Hub dos Analistas · {{tela}} · gerado em {now:%d/%m/%Y} às {now:%H:%M} por {user.initials}"}})

    @app.get("/api/tv")
    def api_tv(tela: str = "", pausada: str = "", espiar: str = "", modo: str = ""):
        now = clock()
        if tela and not espiar:  # a aba "no meu PC" não conta como a TV da sala
            seen.update(tela, pausada == "1", now)
        owners = {p.id: p for p in list_people(db, active_only=False)}
        columns = board(db, now)
        # ausente pelo calendário (fase 13) e sem ter marcado outra presença hoje: "Ausente até dd/mm"
        away = calendario.absent_today(db, now.date())
        # pré-visualizar um modo (fase 14): só na aba "no meu PC", nunca muda a TV da sala
        preview = modos.get_mode(db, int(modo)) if espiar and modo.isdigit() else None
        mode = preview or modos.current(db, now).mode
        payload = {
            "now": now.isoformat(timespec="seconds"),
            "people": [
                {"name": p.name, "initials": p.initials, "color": p.color, "status": status,
                 "since": since.strftime("%H:%M"),
                 "ausente_ate": away[p.id].strftime("%d/%m") if p.id in away and status == STATUSES[-1] else ""}
                for p, status, since in presence_board(db, now)
            ],
            "columns": {c: [tv_card(d, owners[d.owner_id], now.date(), owners) for d in columns[c]] for c in COLUMNS},
            "counts": {c: len(columns[c]) for c in COLUMNS},
            # aviso fixo em todas as telas da rotação
            "overdue": sum(is_overdue(d, now.date()) for d in columns["todo"] + columns["doing"]),
            # aviso sonoro de cada rotina de hoje: a TV toca uma vez, quando chega o horário
            "avisos": tv_alerts(db, now),
            # pausa pelo app (fase 10) e quanto dura a pausa feita com um clique na própria TV
            "pausa": tvcontrole.tv_payload(db, now, owners),
            "pausa_minutos": tvcontrole.DEFAULT_MINUTES,
            "modo": {"nome": mode.name, "padrao": mode.is_default, "previa": preview is not None},
            **rotation(db, now, mode),
        }
        if not mode.sound:  # modo sem som (ex.: Reunião na sala): a faixa aparece, sem tocar
            for a in payload["avisos"]:
                a["mudo"] = True
        if mode.hide_titles:  # modo com os títulos escondidos (ex.: Visita): o texto nem sai do servidor
            modos.mask_titles(payload)
        return payload

    # ---------- TV da sala: pausar, trocar de tela e ver uma tela no meu PC (fase 10) ----------

    def tv_room_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        now = clock()
        pause = tvcontrole.current_pause(db, now)
        who = get_person(db, pause["por"]) if pause and pause.get("por") else None
        mode_now = modos.current(db, now)
        return page(request, "tv-da-sala.html", user, status_code, seen=seen.get(now), pause=pause,
                    mode_now=mode_now, mode_by=get_person(db, mode_now.by) if mode_now.by else None,
                    modes=modos.list_modes(db), mode_durations=modos.DURATIONS,
                    pause_who=who, pause_until=datetime.fromisoformat(pause["ate"]) if pause else None,
                    screens=rotation(db, now)["screens"], labels=tvcontrole.LABELS, durations=tvcontrole.DURATIONS,
                    default_minutes=str(tvcontrole.DEFAULT_MINUTES), **ctx)

    def back_to_tv_room(message: str) -> RedirectResponse:
        return RedirectResponse(f"/tv-da-sala?ok={quote(message)}", status_code=303)

    @app.get("/tv-da-sala", response_class=HTMLResponse)
    def tv_da_sala(request: Request, ok: str = ""):
        user = me(request)
        return to_login() if user is None else tv_room_page(request, user, ok=ok)

    @app.post("/tv-da-sala/pausar")
    def tv_da_sala_pausar(request: Request, tela: str = Form("atual"), minutos: str = Form("15")):
        user = me(request)
        if user is None:
            return to_login()
        if tela == "atual":
            current = seen.get(clock())
            if current is None:
                return tv_room_page(request, user, 422, error="A TV da sala não está conectada agora. "
                                    "Escolha uma tela da lista para ela abrir quando conectar.")
            tela = current["tela"]
        try:
            tvcontrole.pause(db, clock(), user, tela, minutos)
        except ValidationError as exc:
            return tv_room_page(request, user, 422, error=str(exc))
        return back_to_tv_room(f"A TV da sala fica em “{tvcontrole.LABELS[tela]}”. Ela obedece em até 5 segundos.")

    @app.post("/tv-da-sala/trocar")
    def tv_da_sala_trocar(request: Request, direcao: str = Form("proxima")):
        user = me(request)
        if user is None:
            return to_login()
        current = seen.get(clock())
        screen = tvcontrole.step(db, clock(), user, -1 if direcao == "anterior" else 1,
                                 current["tela"] if current else None)
        return back_to_tv_room(f"A TV da sala foi para “{tvcontrole.LABELS[screen]}” e fica pausada nela.")

    @app.post("/tv-da-sala/pagina")
    def tv_da_sala_pagina(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        tvcontrole.next_page(db, clock(), user)
        return back_to_tv_room("As colunas do Quadro passam para a página seguinte.")

    @app.post("/tv-da-sala/retomar")
    def tv_da_sala_retomar(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        tvcontrole.resume(db, clock(), user)
        return back_to_tv_room("A TV da sala voltou a passar as telas sozinha.")

    @app.post("/tv-da-sala/modo")
    def tv_da_sala_modo(request: Request, modo: str = Form(""), ate: str = Form("dia")):
        user = me(request)
        if user is None:
            return to_login()
        if modo == "automatico":
            modos.back_to_automatic(db, clock(), user)
            return back_to_tv_room("A TV da sala voltou ao modo automático.")
        try:
            mode = modos.choose(db, clock(), user, int(modo) if modo.isdigit() else 0, ate)
        except ValidationError as exc:
            return tv_room_page(request, user, 422, error=str(exc))
        return back_to_tv_room(f"A TV da sala está no modo “{mode.name}” {modos.DURATIONS[ate]}. "
                               "Ela troca em até 5 segundos.")

    # ---------- modos da TV (fase 14) ----------

    def modes_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        return page(request, "modos.html", user, status_code, modes=modos.list_modes(db),
                    mode_now=modos.current(db, clock()), can_manage=modos.can_manage(user), **ctx)

    def mode_form(request: Request, user: Person, v: dict, status_code: int = 200, **ctx) -> HTMLResponse:
        return page(request, "modo.html", user, status_code, v=v, RULES=modos.RULES, WEEKDAYS=modos.WEEKDAYS,
                    MIN=modos.MIN_SECONDS, MAX=modos.MAX_SECONDS, PAGE_MIN=modos.PAGE_MIN, PAGE_MAX=modos.PAGE_MAX,
                    **ctx)

    def mode_values(m) -> dict:
        rule = m.rule
        return {"id": m.id, "name": m.name, "is_default": m.is_default, "builtin": m.builtin,
                "page_seconds": str(m.page_seconds), "sound": m.sound, "hide_titles": m.hide_titles,
                "screens": [{"id": s.id, "label": s.label, "seconds": str(s.seconds), "enabled": s.enabled}
                            for s in m.screens],
                "rule_on": m.rule_on, "tipo": rule.get("tipo", ""), "n": str(rule.get("n", 5)),
                "de": str(rule.get("de", "")), "ate": str(rule.get("ate", "")), "dias": rule.get("dias", []),
                "janelas": ", ".join(f"{a}-{b}" for a, b in rule.get("janelas", []))}

    def parse_mode(form) -> tuple[dict, dict]:
        labels = {s.id: s.label for s in modos.default_mode(db).screens}
        order = [str(x) for x in form.getlist("tela") if str(x) in labels]
        on = set(form.getlist("ligada"))
        screens = [{"id": t, "label": labels[t], "seconds": str(form.get(f"segundos_{t}", "")).strip(),
                    "enabled": t in on} for t in order]
        v = {"name": str(form.get("name", "")), "page_seconds": str(form.get("page_seconds", "")).strip(),
             "sound": form.get("sound") == "1", "hide_titles": form.get("hide_titles") == "1",
             "screens": screens, "rule_on": form.get("rule_on") == "1", "tipo": str(form.get("tipo", "")),
             "n": str(form.get("n", "")).strip(), "de": str(form.get("de", "")).strip(),
             "ate": str(form.get("ate", "")).strip(), "dias": [int(d) for d in form.getlist("dias") if str(d).isdigit()],
             "janelas": str(form.get("janelas", ""))}
        return v, {"name": v["name"], "page_seconds": v["page_seconds"], "sound": v["sound"],
                   "hide_titles": v["hide_titles"], "rule_on": v["rule_on"],
                   "screens": [(x["id"], x["seconds"], x["enabled"]) for x in screens]}

    def manage_modes(request: Request) -> tuple[Person | None, Response | None]:
        user = me(request)
        if user is None:
            return None, to_login()
        if not modos.can_manage(user):
            return user, forbidden(request, user, "Só o gestor e os administradores mudam os modos da TV.")
        return user, None

    def back_to_modes(message: str) -> RedirectResponse:
        return RedirectResponse(f"/modos?ok={quote(message)}", status_code=303)

    @app.get("/modos", response_class=HTMLResponse)
    def modos_lista(request: Request, ok: str = ""):
        user = me(request)
        return to_login() if user is None else modes_page(request, user, ok=ok)

    @app.get("/modos/novo", response_class=HTMLResponse)
    def modos_novo(request: Request):
        user, denied = manage_modes(request)
        if denied:
            return denied
        base = mode_values(modos.default_mode(db))
        v = {**base, "id": "", "name": "", "is_default": False, "builtin": None, "rule_on": False, "tipo": "",
             "screens": [{**x, "enabled": False} for x in base["screens"]]}
        return mode_form(request, user, v)

    async def mode_save(request: Request, mode_id: int | None):
        user, denied = manage_modes(request)
        if denied:
            return denied
        form = await request.form()
        v, fields = parse_mode(form)
        current = modos.get_mode(db, mode_id) if mode_id else None
        if mode_id and current is None:
            return Response(status_code=404)
        v.update(id=mode_id or "", is_default=bool(current and current.is_default),
                 builtin=current.builtin if current else None)
        try:
            rule = {} if v["is_default"] else modos.parse_rule(v["tipo"], v["n"], v["de"], v["ate"],
                                                                [str(d) for d in v["dias"]], v["janelas"])
            saved = modos.save_mode(db, clock(), user, mode_id, rule=rule, **fields)
        except ValidationError as exc:
            return mode_form(request, user, v, 422, error=str(exc))
        return back_to_modes(f"Modo “{saved.name}” salvo.")

    @app.post("/modos")
    async def modos_criar(request: Request):
        return await mode_save(request, None)

    @app.get("/modos/{mode_id}", response_class=HTMLResponse)
    def modos_editar(request: Request, mode_id: int):
        user, denied = manage_modes(request)
        if denied:
            return denied
        m = modos.get_mode(db, mode_id)
        return Response(status_code=404) if m is None else mode_form(request, user, mode_values(m))

    @app.post("/modos/{mode_id}")
    async def modos_salvar(request: Request, mode_id: int):
        return await mode_save(request, mode_id)

    @app.post("/modos/{mode_id}/{acao}")
    def modos_acao(request: Request, mode_id: int, acao: str):
        user, denied = manage_modes(request)
        if denied:
            return denied
        now = clock()
        try:
            if acao == "duplicar":
                copy = modos.duplicate_mode(db, now, user, mode_id)
                return RedirectResponse(f"/modos/{copy.id}", status_code=303)
            if acao == "excluir":
                modos.delete_mode(db, now, user, mode_id)
                return back_to_modes("Modo apagado.")
            if acao in ("subir", "descer"):
                modos.move_mode(db, now, user, mode_id, -1 if acao == "subir" else 1)
                return back_to_modes("Ordem dos modos salva.")
            if acao in ("ligar-regra", "desligar-regra"):
                modos.set_rule_on(db, now, user, mode_id, acao == "ligar-regra")
                return back_to_modes("Regra " + ("ligada." if acao == "ligar-regra" else "desligada."))
        except ValidationError as exc:
            return modes_page(request, user, 422, error=str(exc))
        return Response(status_code=404)

    # ---------- app do analista ----------

    templates.env.globals.update(
        COLUMN_LABELS=COLUMN_LABELS, FOLDERS=FOLDERS, STATUSES=STATUSES, is_overdue=is_overdue,
        can_see=can_see, RESERVED_TEXT=RESERVED_TEXT,
    )

    templates.env.globals.update(ROLES=ROLES, WEEKDAY_LABELS=WEEKDAY_LABELS, weekdays_label=weekdays_label,
                                 can_manage_routines=can_manage)
    # pedidos de cadastro esperando: o número aparece no menu Pessoas dos administradores
    templates.env.globals["signups_waiting"] = lambda: len(cadastro.pending(db, clock()))

    def me(request: Request) -> Person | None:
        # a sessão é criada ao entrar com o PIN e acaba à meia-noite (ou ao clicar em Sair)
        return session_person(db, clock(), request.cookies.get(COOKIE))

    def page(request: Request, name: str, user: Person | None, status_code: int = 200, **ctx) -> HTMLResponse:
        return templates.TemplateResponse(request, name, {"user": user, **ctx}, status_code=status_code)

    def to_login() -> RedirectResponse:
        return RedirectResponse("/entrar", status_code=303)

    def board_context(user: Person, show_all: bool) -> dict:
        now = clock()
        # a presença vai junto no trecho que se atualiza: um app aberto de ontem não mostra o status velho
        status = next((s for p, s, _ in presence_board(db, now) if p.id == user.id), STATUSES[-1])
        everything = board(db, now)
        columns = everything if show_all else {c: [d for d in everything[c] if is_owner(d, user.id)] for c in COLUMNS}
        # rotinas da equipe com pastas: cada um marca a sua, mesmo sem ser o responsável pelo cartão
        shared = [] if show_all else [d for c in ("todo", "doing") for d in everything[c]
                                      if d.routine and d.routine.folders and not is_owner(d, user.id) and can_see(d, user)]
        return {
            "status": status,
            "columns": columns,
            "shared": shared,
            "owners": {p.id: p for p in list_people(db, active_only=False)},
            "today": now.date(),
            "show_all": show_all,
            "clips": anexos.counts(db, "demanda"),  # 📎 no cartão (só no app, nunca na TV)
            # trilha do dia (fase 20): a faixa "Minha trilha de hoje" em cima do quadro
            "trail": [] if show_all else trilha.my_trail(db, user.id, now),
            "trail_counts": trilha.counts(trilha.my_trail(db, user.id, now)) if not show_all else {},
        }

    def forbidden(request: Request, user: Person, message: str = "") -> HTMLResponse:
        return page(request, "sem-permissao.html", user, 403, message=message)

    # erros de PIN e nomes que não existem, contados por aparelho (em qualquer nome), e pedidos de cadastro
    login_limiter = cadastro.DeviceLimiter(LOGIN_MAX_FAILURES, LOGIN_WINDOW_MINUTES * 60)
    signup_limiter = cadastro.DeviceLimiter(SIGNUPS_PER_DEVICE, 3600)

    def device(request: Request) -> str:
        return request.client.host if request.client else "?"

    def login_page(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
        return page(request, "entrar.html", None, status_code, empty=cadastro.hub_is_empty(db), **ctx)

    def blocked_page(request: Request, minutes: int) -> HTMLResponse:
        return login_page(request, 429, error=f"Muitas tentativas erradas neste aparelho. Tente de novo daqui a "
                                              f"{minutes} minuto{'s' if minutes > 1 else ''}.")

    def signed_in(now: datetime, person_id: int) -> RedirectResponse:
        token = start_session(db, now, person_id)
        r = RedirectResponse("/", status_code=303)
        seconds = int((session_end(now) - now).total_seconds())
        r.set_cookie(COOKIE, token, max_age=max(seconds, 60), httponly=True, samesite="lax")
        return r

    @app.get("/entrar", response_class=HTMLResponse)
    def entrar(request: Request):
        return login_page(request)

    @app.post("/entrar")
    def entrar_nome(request: Request, nome: str = Form(""), pin: str = Form("")):
        """Fase 17: a pessoa digita o nome (sem diferença de acento e maiúscula) e o PIN."""
        minutes = login_limiter.wait_minutes(device(request))
        if minutes:
            return blocked_page(request, minutes)
        now = clock()
        person = cadastro.find_by_name(db, nome)
        if person is None:
            if cadastro.is_pending(db, now, nome):
                return login_page(request, 422, nome=nome, error="Seu pedido de cadastro ainda está esperando um "
                                                                 "administrador aprovar.")
            login_limiter.hit(device(request))
            return login_page(request, 422, nome=nome, unknown=True, error="Não achei ninguém com esse nome no Hub.")
        if not person.has_pin:
            # cadastrado por um administrador e ainda sem PIN: vai criar o PIN, como no primeiro acesso
            return RedirectResponse(f"/entrar/{person.id}", status_code=303)
        try:
            verify_pin(db, now, person.id, pin)
        except ValidationError as exc:
            login_limiter.hit(device(request))
            return login_page(request, 422, nome=nome, error=str(exc))
        return signed_in(now, person.id)

    @app.get("/entrar/cadastro", response_class=HTMLResponse)
    def cadastro_form(request: Request, nome: str = ""):
        return page(request, "cadastro.html", None, empty=cadastro.hub_is_empty(db), v={"nome": nome})

    @app.post("/entrar/cadastro")
    def cadastro_pedir(request: Request, nome: str = Form(""), iniciais: str = Form(""), pin: str = Form(""),
                       confirmar: str = Form("")):
        now = clock()
        empty = cadastro.hub_is_empty(db)
        v = {"nome": nome, "iniciais": iniciais}
        minutes = signup_limiter.wait_minutes(device(request))
        if minutes and not empty:
            return page(request, "cadastro.html", None, 429, empty=empty, v=v,
                        error="Este aparelho já mandou pedidos demais. Tente de novo mais tarde.")
        try:
            if empty:
                person = cadastro.create_first_admin(db, now, nome, iniciais, pin, confirmar)
                return signed_in(now, person.id)
            cadastro.request_signup(db, now, nome, iniciais, pin, confirmar)
        except ValidationError as exc:
            return page(request, "cadastro.html", None, 422, empty=empty, v=v, error=str(exc))
        signup_limiter.hit(device(request))
        return page(request, "cadastro.html", None, sent=True, v=v)

    def pin_page(request: Request, person: Person, status_code: int = 200, error: str = "") -> HTMLResponse:
        return page(request, "pin.html", None, status_code, person=person, error=error,
                    first_admin=not has_admin(db))

    @app.get("/entrar/{person_id}", response_class=HTMLResponse)
    def entrar_pessoa(request: Request, person_id: int):
        person = get_person(db, person_id)
        if person is None or not person.active:
            return to_login()
        return pin_page(request, person)

    @app.post("/entrar/{person_id}")
    def entrar_pin(request: Request, person_id: int, pin: str = Form(""), confirmar: str = Form("")):
        person = get_person(db, person_id)
        if person is None or not person.active:
            return to_login()
        minutes = login_limiter.wait_minutes(device(request))
        if minutes:
            return blocked_page(request, minutes)
        now = clock()
        try:
            if person.has_pin:
                verify_pin(db, now, person_id, pin)
            else:
                create_pin(db, now, person_id, pin, confirmar)
        except ValidationError as exc:
            if person.has_pin:
                login_limiter.hit(device(request))
            return pin_page(request, get_person(db, person_id), 422, str(exc))
        return signed_in(now, person_id)

    @app.post("/sair")
    def sair(request: Request):
        end_session(db, request.cookies.get(COOKIE))
        r = to_login()
        r.delete_cookie(COOKIE)
        return r

    @app.get("/meu-pin", response_class=HTMLResponse)
    def meu_pin(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        return page(request, "meu-pin.html", user)

    @app.post("/meu-pin")
    def meu_pin_salvar(request: Request, atual: str = Form(""), pin: str = Form(""), confirmar: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        try:
            change_pin(db, clock(), user.id, atual, pin, confirmar)
        except ValidationError as exc:
            return page(request, "meu-pin.html", user, 422, error=str(exc))
        return page(request, "meu-pin.html", user, ok=True)

    # ---------- celular (fase 18) ----------

    @app.get("/manifest.webmanifest")
    def manifest():
        # o atalho na tela inicial do celular: nome, ícone e cor do Hub
        return JSONResponse({
            "name": "Hub dos Analistas",
            "short_name": "Hub",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#16212c",
            "theme_color": "#16212c",
            "lang": "pt-BR",
            "icons": [
                {"src": "/static/icones/hub-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icones/hub-512.png", "sizes": "512x512", "type": "image/png"},
                {"src": "/static/hub.svg", "sizes": "any", "type": "image/svg+xml"},
            ],
        }, media_type="application/manifest+json")

    @app.get("/celular", response_class=HTMLResponse)
    def celular_page(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        address = celular.phone_address(request.headers.get("host", ""), PHONE_PORT, celular.lan_ip())
        url = f"{address}/entrar" if address else None
        return page(request, "celular.html", user, address=address,
                    qr=qr_svg(url) if url else None)

    @app.get("/", response_class=HTMLResponse)
    def quadro(request: Request, todas: int = 0, concluida: str = "", ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        done = find_demand(db, int(concluida)) if concluida.isdigit() else None
        done = done if done is not None and done.column == "done" and can_see(done, user) else None
        return page(request, "quadro.html", user, concluida=done, ok=ok, **board_context(user, bool(todas)))

    @app.get("/parcial/quadro", response_class=HTMLResponse)
    def quadro_parcial(request: Request, todas: int = 0):
        user = me(request)
        if user is None:
            return Response(status_code=401)
        return page(request, "_quadro.html", user, **board_context(user, bool(todas)))

    @app.post("/presenca")
    def presenca(request: Request, status: str = Form(...)):
        user = me(request)
        if user is None:
            return to_login()
        set_status(db, clock(), user.id, status)
        return RedirectResponse("/", status_code=303)

    def demand_form(request: Request, user: Person, values: dict, status_code: int = 200, **ctx) -> HTMLResponse:
        people = list_people(db)
        # dono desativado continua na lista desta demanda; senão o navegador escolheria outro dono sozinho
        owner_id = int(values["owner_id"]) if str(values.get("owner_id", "")).isdigit() else None
        owner = get_person(db, owner_id) if owner_id else None
        if owner and not owner.active:
            people = people + [owner]
        demand = find_demand(db, int(values["id"])) if str(values.get("id", "")).isdigit() else None
        if demand is not None:
            ctx.setdefault("files", anexos.list_for(db, "demanda", demand.id))
            ctx.setdefault("timeline", demand_timeline(demand, user))
        everyone = {p.id: p for p in list_people(db, active_only=False)}
        return page(request, "demanda.html", user, status_code, v=values, people=people, demand=demand,
                    everyone=everyone, accept=anexos.ACCEPT, max_mb=anexos.MAX_BYTES // 1024 ** 2,
                    max_files=anexos.MAX_PER_PARENT, max_details=MAX_DETAILS, can_remove_file=can_remove_file, **ctx)

    def demand_timeline(d, user: Person) -> list[tuple[datetime, str]]:
        """Tudo o que aconteceu com uma demanda, do mais antigo ao mais novo."""
        with db.connect() as conn:
            rows = conn.execute("SELECT * FROM events WHERE subject = ? ORDER BY at, id", (f"demanda:{d.id}",)).fetchall()
        people = {p.id: p for p in list_people(db, active_only=False)}
        return [(datetime.fromisoformat(r["at"]), describe(r, people, {d.id: d}, user)) for r in rows]

    def parse_demand(form) -> tuple[dict, dict]:
        values = {
            "title": form.get("title", ""), "owner_id": form.get("owner_id", ""), "folder": form.get("folder", ""),
            "requested_by": form.get("requested_by", ""), "due": form.get("due", ""), "reserved": "reserved" in form,
            "details": form.get("details", ""),
        }
        try:
            due = date.fromisoformat(values["due"]) if values["due"] else None
        except ValueError:
            raise ValidationError("Data inválida.")
        owner = int(values["owner_id"]) if values["owner_id"].isdigit() else 0
        fields = dict(title=values["title"], owner_id=owner, folder=values["folder"] or None,
                      requested_by=values["requested_by"] or None, due=due, reserved=values["reserved"],
                      details=values["details"])
        return values, fields

    @app.get("/demandas/nova", response_class=HTMLResponse)
    def demanda_nova(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        return demand_form(request, user, {"id": "", "title": "", "owner_id": str(user.id), "folder": "",
                                           "requested_by": "", "due": "", "reserved": False, "details": ""})

    @app.post("/demandas")
    async def demanda_criar(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        form = await request.form()
        values = {"id": ""}
        try:
            parsed, fields = parse_demand(form)
            values.update(parsed)
            d = create_demand(db, clock(), user.id, **fields)
        except ValidationError as exc:
            values.update({k: form.get(k, "") for k in ("title", "owner_id", "folder", "requested_by", "due", "details")},
                          reserved="reserved" in form)
            return demand_form(request, user, values, 422, error=str(exc))
        problem = save_files(user, d, uploads(form))
        if problem:  # a demanda já foi criada: mostra a página dela com o motivo do arquivo recusado
            return demand_form(request, user, demand_values(d), 422, error_files=problem)
        return RedirectResponse("/", status_code=303)

    def uploads(form) -> list:
        return [f for f in form.getlist("arquivos") if getattr(f, "filename", "")]

    def save_files(user: Person, d, files: list, replaces: int | None = None) -> str:
        """Grava os arquivos enviados; devolve o motivo do primeiro recusado (os outros seguem)."""
        problems = []
        for f in files:
            try:
                anexos.save(db, clock(), user, "demanda", d.id, f.filename, f.file, replaces=replaces,
                            subject=f"demanda:{d.id}")
            except ValidationError as exc:
                problems.append(str(exc))
        if len(problems) < len(files):
            touch_demand(db, clock(), d.id)
        return " ".join(problems)

    def demand_values(d) -> dict:
        return {"id": d.ref, "title": d.title, "owner_id": str(d.owner_id), "folder": d.folder or "",
                "requested_by": d.requested_by or "", "due": d.due.isoformat() if d.due else "", "reserved": d.reserved,
                "routine": d.routine_id is not None, "details": d.details or ""}

    # {ref}: o número da demanda, ou "rotina-<número>-<dia>" para o cartão calculado de uma rotina de hoje,
    # que vira demanda na primeira ação (mover, salvar, excluir ou marcar pasta). Abrir o formulário não cria nada.
    @app.get("/demandas/{ref}", response_class=HTMLResponse)
    def demanda_editar(request: Request, ref: str, ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        d = find_card(db, clock(), ref)
        if d is None:
            return RedirectResponse("/", status_code=303)
        if not can_see(d, user):
            return forbidden(request, user, "Esta demanda é reservada. Só o dono, quem criou, o gestor e os administradores podem abrir.")
        return demand_form(request, user, demand_values(d), ok_files=ok)

    def hidden_from(user: Person, ref: str) -> bool:
        d = find_card(db, clock(), ref)
        return d is not None and not can_see(d, user)

    def reserved_forbidden(request: Request, user: Person) -> HTMLResponse:
        return forbidden(request, user, "Esta demanda é reservada. Só o dono, quem criou, o gestor e os administradores podem mexer nela.")

    @app.post("/demandas/{ref}")
    async def demanda_salvar(request: Request, ref: str):
        user = me(request)
        if user is None:
            return to_login()
        card = find_card(db, clock(), ref)
        if card is not None and not can_see(card, user):
            return reserved_forbidden(request, user)
        form = await request.form()
        values = {"id": ref, "routine": card is not None and card.routine_id is not None}
        try:
            parsed, fields = parse_demand(form)
            values.update(parsed)
            update_demand(db, clock(), user.id, ref, **fields)
        except ValidationError as exc:
            values.update({k: form.get(k, "") for k in ("title", "owner_id", "folder", "requested_by", "due", "details")},
                          reserved="reserved" in form)
            return demand_form(request, user, values, 422, error=str(exc))
        return RedirectResponse("/", status_code=303)

    # ---------- anexos das demandas (fase 11) ----------

    def file_target(request: Request, ref: str):
        """A demanda para anexar (o cartão de rotina vira demanda aqui), ou a resposta de recusa."""
        user = me(request)
        if user is None:
            return None, None, to_login()
        if hidden_from(user, ref):
            return user, None, reserved_forbidden(request, user)
        try:
            return user, ensure_demand(db, clock(), user.id, ref), None
        except ValidationError as exc:
            return user, None, board_error(request, user, str(exc))

    def back_to_demand(d, message: str) -> RedirectResponse:
        return RedirectResponse(f"/demandas/{d.id}?ok={quote(message)}#arquivos", status_code=303)

    @app.post("/demandas/{ref}/anexos")
    async def demanda_anexar(request: Request, ref: str):
        user, d, stop = file_target(request, ref)
        if stop:
            return stop
        files = uploads(await request.form())
        if not files:
            return demand_form(request, user, demand_values(d), 422, error_files="Escolha um arquivo para anexar.")
        problem = save_files(user, d, files)
        if problem:
            return demand_form(request, user, demand_values(d), 422, error_files=problem)
        return back_to_demand(d, "Arquivo anexado." if len(files) == 1 else f"{len(files)} arquivos anexados.")

    def demand_file(d, attachment_id: int):
        a = anexos.find(db, attachment_id)
        ok = a is not None and a.kind == "demanda" and a.parent_id == d.id and a.deleted_at is None
        return a if ok else None

    @app.post("/demandas/{ref}/anexos/{attachment_id}/versao")
    async def demanda_anexo_versao(request: Request, ref: str, attachment_id: int):
        user, d, stop = file_target(request, ref)
        if stop:
            return stop
        a = demand_file(d, attachment_id)
        files = uploads(await request.form())[:1]
        if a is None:
            return demand_form(request, user, demand_values(d), 422, error_files="Esse arquivo não está mais na lista.")
        if not files:
            return demand_form(request, user, demand_values(d), 422, error_files="Escolha o arquivo da nova versão.")
        problem = save_files(user, d, files, replaces=a.id)
        if problem:
            return demand_form(request, user, demand_values(d), 422, error_files=problem)
        return back_to_demand(d, f"Nova versão de “{a.name}” enviada. A anterior fica em “versões anteriores”.")

    @app.post("/demandas/{ref}/anexos/{attachment_id}/remover")
    def demanda_anexo_remover(request: Request, ref: str, attachment_id: int):
        user, d, stop = file_target(request, ref)
        if stop:
            return stop
        a = demand_file(d, attachment_id)
        if a is None:
            return back_to_demand(d, "Esse arquivo já tinha sido removido.")
        if not can_remove_file(d, a.uploaded_by, user):
            return forbidden(request, user, "Remove um arquivo quem anexou, o dono da demanda, o gestor e os administradores.")
        anexos.remove(db, clock(), user, a, subject=f"demanda:{d.id}")
        touch_demand(db, clock(), d.id)
        return back_to_demand(d, f"“{a.name}” foi para a lixeira. Um administrador consegue restaurar por "
                                 f"{anexos.TRASH_DAYS} dias.")

    @app.get("/anexos/{attachment_id}")
    def anexo_baixar(request: Request, attachment_id: int):
        user = me(request)
        if user is None:
            return to_login()
        a = anexos.get(db, attachment_id)
        if a is None or not file_allowed(a, user):
            return page(request, "sem-permissao.html", user, 404, message="Arquivo não encontrado (ele pode ter sido removido).")
        path = anexos.path_of(db, a)
        if not path.is_file():
            return page(request, "sem-permissao.html", user, 404,
                        message="O arquivo não está na pasta dos anexos. Avise um administrador.")
        # sempre como download, nunca aberto dentro do Hub
        return FileResponse(path, filename=a.name, media_type="application/octet-stream",
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
                            content_disposition_type="attachment")

    def file_allowed(a, user: Person) -> bool:
        if a.kind == "demanda":
            d = find_demand(db, a.parent_id)
            return d is not None and can_see(d, user)
        if a.kind == notas.KIND:  # arquivo de nota: só a dona, nem gestor nem administrador
            return notas.get_note(db, user, a.parent_id) is not None
        return False

    # ---------- bloco de notas pessoal (fase 12): só a dona vê; nada vai para o histórico ----------

    def notes_page(request: Request, user: Person, note=None, status_code: int = 200, q: str = "", aba: str = "",
                   **ctx) -> HTMLResponse:
        listed = notas.list_notes(db, user, text=q, archived=aba == "arquivadas", trash=aba == "lixeira")
        files = anexos.list_for(db, notas.KIND, note.id) if note else []
        return page(request, "notas.html", user, status_code, notes=listed, note=note, files=files, q=q, aba=aba,
                    accept=anexos.ACCEPT, max_mb=anexos.MAX_BYTES // 1024 ** 2, max_files=anexos.MAX_PER_PARENT,
                    max_body=notas.MAX_BODY, trash_days=notas.TRASH_DAYS,
                    clips=anexos.counts(db, notas.KIND), **ctx)

    def my_note(request: Request, note_id: int, deleted: bool = False):
        user = me(request)
        if user is None:
            return None, None, to_login()
        try:
            return user, notas._own(db, user, note_id, deleted), None
        except ValidationError:
            # de outra pessoa ou inexistente: a mesma resposta, para não contar que a nota existe
            return user, None, page(request, "sem-permissao.html", user, 404, message="Nota não encontrada.")

    def back_to_note(note_id: int, message: str = "") -> RedirectResponse:
        return RedirectResponse(f"/notas/{note_id}" + (f"?ok={quote(message)}" if message else ""), status_code=303)

    @app.get("/notas", response_class=HTMLResponse)
    def notas_lista(request: Request, q: str = "", aba: str = ""):
        user = me(request)
        return to_login() if user is None else notes_page(request, user, q=q, aba=aba)

    @app.post("/notas")
    def notas_criar(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        return back_to_note(notas.create_note(db, clock(), user).id)

    @app.get("/notas/baixar")
    def notas_baixar(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        name = f"Minhas notas {clock().strftime('%Y-%m-%d')}.zip"
        return Response(notas.export_zip(db, user), media_type="application/zip",
                        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}",
                                 "Cache-Control": "no-store"})

    @app.get("/notas/{note_id}", response_class=HTMLResponse)
    def notas_abrir(request: Request, note_id: int, ok: str = "", q: str = "", aba: str = ""):
        user, note, stop = my_note(request, note_id)
        return stop or notes_page(request, user, note, ok=ok, q=q, aba="arquivadas" if note.archived else aba)

    @app.post("/notas/{note_id}")
    async def notas_salvar(request: Request, note_id: int):
        user, note, stop = my_note(request, note_id)
        auto = request.headers.get("x-hub-auto") == "1"  # gravação automática enquanto a pessoa digita
        if stop:
            return JSONResponse({"erro": "Nota não encontrada."}, 404) if auto and user else stop
        form = await request.form()
        try:
            saved = notas.save_note(db, clock(), user, note_id, str(form.get("title", "")), str(form.get("body", "")))
        except ValidationError as exc:
            if auto:
                return JSONResponse({"erro": str(exc)}, 422)
            return notes_page(request, user, note, 422, error=str(exc))
        if auto:
            return JSONResponse({"salvo": saved.updated_at.strftime("%H:%M"), "titulo": saved.title})
        return back_to_note(note_id, "Salvo.")

    @app.post("/notas/{note_id}/virar-demanda")
    def notas_virar_demanda(request: Request, note_id: int, copiar: str = Form("")):
        user, note, stop = my_note(request, note_id)
        if stop:
            return stop
        try:
            d = create_demand(db, clock(), user.id, title=note.title[:120], owner_id=user.id,
                              details=note.body[:MAX_DETAILS] or None)
        except ValidationError as exc:
            return notes_page(request, user, note, 422, error=str(exc))
        problems = []
        if copiar == "1":
            for a in anexos.list_for(db, notas.KIND, note.id):
                try:
                    with open(anexos.path_of(db, a), "rb") as data:
                        anexos.save(db, clock(), user, "demanda", d.id, a.name, data, subject=f"demanda:{d.id}")
                except (OSError, ValidationError) as exc:
                    problems.append(str(exc) if isinstance(exc, ValidationError) else f"“{a.name}” não abriu.")
        message = "Demanda criada a partir da nota." + (" " + " ".join(problems) if problems else "")
        return RedirectResponse(f"/demandas/{d.id}?ok={quote(message)}", status_code=303)

    @app.post("/notas/{note_id}/anexos")
    async def notas_anexar(request: Request, note_id: int):
        user, note, stop = my_note(request, note_id)
        if stop:
            return stop
        files = uploads(await request.form())
        if not files:
            return notes_page(request, user, note, 422, error_files="Escolha um arquivo para anexar.")
        problems = []
        for f in files:
            try:
                anexos.save(db, clock(), user, notas.KIND, note.id, f.filename, f.file)  # sem histórico
            except ValidationError as exc:
                problems.append(str(exc))
        if len(problems) < len(files):
            notas.touch(db, clock(), note.id)
        if problems:
            return notes_page(request, user, notas.get_note(db, user, note.id), 422, error_files=" ".join(problems))
        return back_to_note(note.id, "Arquivo anexado." if len(files) == 1 else f"{len(files)} arquivos anexados.")

    def note_file(note, attachment_id: int):
        a = anexos.find(db, attachment_id)
        ok = a is not None and a.kind == notas.KIND and a.parent_id == note.id and a.deleted_at is None
        return a if ok else None

    @app.post("/notas/{note_id}/anexos/{attachment_id}/versao")
    async def notas_anexo_versao(request: Request, note_id: int, attachment_id: int):
        user, note, stop = my_note(request, note_id)
        if stop:
            return stop
        a, files = note_file(note, attachment_id), uploads(await request.form())[:1]
        if a is None or not files:
            return notes_page(request, user, note, 422, error_files="Escolha o arquivo da nova versão.")
        try:
            anexos.save(db, clock(), user, notas.KIND, note.id, files[0].filename, files[0].file, replaces=a.id)
        except ValidationError as exc:
            return notes_page(request, user, note, 422, error_files=str(exc))
        notas.touch(db, clock(), note.id)
        return back_to_note(note.id, f"Nova versão de “{a.name}” enviada.")

    @app.post("/notas/{note_id}/anexos/{attachment_id}/remover")
    def notas_anexo_remover(request: Request, note_id: int, attachment_id: int):
        user, note, stop = my_note(request, note_id)
        if stop:
            return stop
        a = note_file(note, attachment_id)
        if a is not None:
            anexos.remove(db, clock(), user, a)
            notas.touch(db, clock(), note.id)
        return back_to_note(note.id, "Arquivo removido.")

    # depois das rotas acima: /notas/{id}/{ação} pegaria /anexos e /virar-demanda
    @app.post("/notas/{note_id}/{acao}")
    def notas_acao(request: Request, note_id: int, acao: str):
        flags = {"fixar": ("pinned", True), "desafixar": ("pinned", False),
                 "arquivar": ("archived", True), "desarquivar": ("archived", False)}
        if acao not in (*flags, "excluir", "restaurar"):
            return Response(status_code=404)
        user, note, stop = my_note(request, note_id, deleted=acao == "restaurar")
        if stop:
            return stop
        if acao == "excluir":
            notas.delete_note(db, clock(), user, note_id)
            return RedirectResponse(f"/notas?ok={quote('Nota na lixeira por ' + str(notas.TRASH_DAYS) + ' dias.')}",
                                    status_code=303)
        if acao == "restaurar":
            notas.restore_note(db, clock(), user, note_id)
            return back_to_note(note_id, "Nota restaurada.")
        notas.set_flag(db, clock(), user, note_id, *flags[acao])
        return back_to_note(note_id)

    # ---------- busca de demandas (fase 11) ----------

    @app.get("/demandas", response_class=HTMLResponse)
    def demandas_busca(request: Request, q: str = "", pessoa: str = "", pasta: str = "", coluna: str = "",
                       de: str = "", ate: str = "", anexos_: str = Query("", alias="anexos"), pagina: int = 1):
        user = me(request)
        if user is None:
            return to_login()
        try:
            start = date.fromisoformat(de) if de else None
            end = date.fromisoformat(ate) if ate else None
        except ValueError:
            start = end = None
        clips = anexos.counts(db, "demanda")
        found = search_demands(db, user, text=q, owner_id=int(pessoa) if pessoa.isdigit() else None,
                               folder=pasta or None, column=coluna or None, start=start, end=end,
                               with_files=set(clips) if anexos_ == "1" else None)
        per_page = 50
        pages = max(1, -(-len(found) // per_page))
        pagina = min(max(pagina, 1), pages)
        return page(request, "demandas.html", user, found=found[(pagina - 1) * per_page: pagina * per_page],
                    total=len(found), pagina=pagina, pages=pages, clips=clips,
                    f={"q": q, "pessoa": pessoa, "pasta": pasta, "coluna": coluna, "de": de, "ate": ate, "anexos": anexos_},
                    base_qs=urlencode({k: v for k, v in {"q": q, "pessoa": pessoa, "pasta": pasta, "coluna": coluna,
                                                         "de": de, "ate": ate, "anexos": anexos_}.items() if v}),
                    people=list_people(db, active_only=False), owners={p.id: p for p in list_people(db, active_only=False)},
                    today=clock().date())

    def board_error(request: Request, user: Person, message: str) -> HTMLResponse:
        # regra de rotina (esperando outra, faltam pastas): mostra o motivo em cima do quadro
        show_all = "todas=1" in (request.headers.get("referer") or "")
        return page(request, "quadro.html", user, 422, error=message, **board_context(user, show_all))

    @app.post("/demandas/{ref}/mover")
    def demanda_mover(request: Request, ref: str, column: str = Form(...)):
        user = me(request)
        if user is None:
            return to_login()
        if hidden_from(user, ref):
            return reserved_forbidden(request, user)
        try:
            moved = move_demand(db, clock(), user.id, ref, column)
        except ValidationError as exc:
            if str(exc) != "Demanda não encontrada.":
                return board_error(request, user, str(exc))
            # outro PC já excluiu: o quadro atualizado mostra a verdade
            moved = None
        back = request.headers.get("referer") or "/"
        if moved is not None and column == "done" and urlsplit(back).path == "/":
            # concluiu pelo quadro: oferece anexar o arquivo final (opcional)
            back = "/?" + "&".join(["concluida=" + str(moved.id)] + (["todas=1"] if "todas=1" in back else []))
        return RedirectResponse(back, status_code=303)

    @app.post("/demandas/{ref}/pasta")
    def demanda_pasta(request: Request, ref: str, folder: str = Form(...)):
        user = me(request)
        if user is None:
            return to_login()
        if hidden_from(user, ref):
            return reserved_forbidden(request, user)
        try:
            toggle_folder(db, clock(), user.id, ref, folder)
        except ValidationError as exc:
            return board_error(request, user, str(exc))
        return RedirectResponse(request.headers.get("referer") or "/", status_code=303)

    @app.post("/demandas/{ref}/excluir")
    def demanda_excluir(request: Request, ref: str):
        user = me(request)
        if user is None:
            return to_login()
        if hidden_from(user, ref):
            return reserved_forbidden(request, user)
        try:
            delete_demand(db, clock(), user.id, ref)
        except ValidationError:
            pass
        return RedirectResponse("/", status_code=303)

    # ---------- rotinas ----------

    def routine_values(r=None, user: Person | None = None) -> dict:
        if r is None:
            return {"id": "", "name": "", "weekdays": [0, 1, 2, 3, 4], "starts_at": "", "deadline": "",
                    "owner_id": str(user.id), "also": [], "folders": [], "waits_for": [], "on_holidays": False}
        return {"id": r.id, "name": r.name, "weekdays": list(r.weekdays), "starts_at": r.starts_at,
                "deadline": r.deadline or "", "owner_id": str(r.owner_id), "also": list(r.owners[1:]),
                "folders": list(r.folders), "waits_for": list(r.waits_for), "on_holidays": r.on_holidays}

    def routines_page(request: Request, user: Person, status_code: int = 200, v: dict | None = None,
                      **ctx) -> HTMLResponse:
        people = list_people(db)
        routines = list_routines(db)
        v = v or routine_values(user=user)
        # responsável desativado continua na lista desta rotina, como no formulário de demanda
        chosen = [int(v["owner_id"])] if str(v.get("owner_id", "")).isdigit() else []
        for pid in chosen + list(v.get("also", [])):
            owner = get_person(db, pid)
            if owner and not owner.active and owner not in people:
                people = people + [owner]
        return page(request, "rotinas.html", user, status_code, routines=routines, by_id={r.id: r for r in routines},
                    people=people, owners={p.id: p for p in list_people(db, active_only=False)}, v=v,
                    can_manage=can_manage(user), alerts=alerts_today(db, clock()), **ctx)

    def manager_only(request: Request) -> tuple[Person | None, Response | None]:
        user = me(request)
        if user is None:
            return None, to_login()
        if not can_manage(user):
            return user, forbidden(request, user, "Só o gestor e os administradores mudam as rotinas.")
        return user, None

    def parse_routine(form) -> dict:
        def ints(key: str) -> list[int]:
            return [int(x) for x in form.getlist(key) if str(x).isdigit()]
        owner = str(form.get("owner_id", ""))
        first = int(owner) if owner.isdigit() else 0
        # o responsável principal (o dono do cartão) e, depois, os outros marcados
        owners = [first] + [p for p in ints("also") if p != first]
        return {"name": str(form.get("name", "")), "weekdays": ints("weekdays"),
                "starts_at": str(form.get("starts_at", "")), "deadline": str(form.get("deadline", "")),
                "owner_ids": owners, "folders": [str(f) for f in form.getlist("folders")],
                "waits_for": ints("waits_for"), "on_holidays": form.get("on_holidays") == "1"}

    @app.get("/rotinas", response_class=HTMLResponse)
    def rotinas(request: Request):
        user = me(request)
        return to_login() if user is None else routines_page(request, user)

    @app.post("/rotinas/sugeridas")
    def rotinas_sugeridas(request: Request):
        user, stop = manager_only(request)
        if stop:
            return stop
        created = create_suggested(db, clock(), user)
        plural = "s" if created != 1 else ""
        message = (f"{created} rotina{plural} criada{plural}, com você como responsável. Dá para mudar em Editar."
                   if created else "As rotinas sugeridas já existem.")
        return routines_page(request, user, ok=message)

    @app.post("/rotinas/testar-aviso")
    def rotinas_testar_aviso(request: Request):
        user, stop = manager_only(request)
        if stop:
            return stop
        start_test_alert(db, clock(), user)
        return routines_page(request, user, ok="Aviso de teste enviado. Em até 5 segundos, a TV da sala toca o som e "
                             "mostra a faixa “Teste do aviso” por 20 segundos. Se a faixa aparecer sem som, o Edge da "
                             "TV está bloqueando o som (veja “Som na TV” no roteiro da fase 7).")

    async def routine_save(request: Request, routine_id: int | None):
        user, stop = manager_only(request)
        if stop:
            return stop
        fields = parse_routine(await request.form())
        try:
            save_routine(db, clock(), user, routine_id, **fields)
        except ValidationError as exc:
            v = {**fields, "id": routine_id or "", "owner_id": str(fields["owner_ids"][0]), "also": fields["owner_ids"][1:]}
            return routines_page(request, user, 422, v=v, error=str(exc))
        return RedirectResponse("/rotinas", status_code=303)

    @app.post("/rotinas")
    async def rotinas_criar(request: Request):
        return await routine_save(request, None)

    @app.get("/rotinas/{routine_id}", response_class=HTMLResponse)
    def rotinas_editar(request: Request, routine_id: int):
        user, stop = manager_only(request)
        if stop:
            return stop
        r = get_routine(db, routine_id)
        if r is None or r.removed:
            return RedirectResponse("/rotinas", status_code=303)
        return routines_page(request, user, v=routine_values(r))

    @app.post("/rotinas/{routine_id}")
    async def rotinas_salvar(request: Request, routine_id: int):
        return await routine_save(request, routine_id)

    @app.post("/rotinas/{routine_id}/ativa")
    def rotinas_ativa(request: Request, routine_id: int, active: str = Form("1")):
        user, stop = manager_only(request)
        if stop:
            return stop
        try:
            set_routine_active(db, clock(), user, routine_id, active == "1")
        except ValidationError as exc:
            return routines_page(request, user, 422, error=str(exc))
        return RedirectResponse("/rotinas", status_code=303)

    @app.post("/rotinas/{routine_id}/remover")
    def rotinas_remover(request: Request, routine_id: int):
        user, stop = manager_only(request)
        if stop:
            return stop
        try:
            r = remove_routine(db, clock(), user, routine_id)
        except ValidationError as exc:
            return routines_page(request, user, 422, error=str(exc))
        return routines_page(request, user, ok=f"“{r.label}” foi removida. As demandas que ela já gerou continuam "
                             "no histórico.")

    # ---------- trilha do dia (fase 20) ----------

    def trail_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        now = clock()
        people = {p.id: p for p in list_people(db)}
        away = calendario.absent_today(db, now.date())
        trails = {pid: steps for pid, steps in trilha.trails_on(db, now.date(), now).items() if pid in people}
        order = sorted(trails, key=lambda pid: (pid != user.id, people[pid].name.lower()))
        summary = trilha.week_summary(db, now)
        if not trilha.can_see_summary(user):
            summary = [x for x in summary if x["pessoa"].id == user.id]
        return page(request, "trilha.html", user, status_code, trails=[(people[pid], trails[pid]) for pid in order],
                    away=away, counts=trilha.counts, summary=summary, can_edit=trilha.can_edit, now=now,
                    has_mine=bool(trilha.list_blocks(db, user.id)), **ctx)

    @app.get("/trilha", response_class=HTMLResponse)
    def trilha_ver(request: Request, ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        return trail_page(request, user, ok=ok)

    def safe_back(volta: str, fallback: str) -> str:
        return volta if volta in ("/", "/trilha") else fallback

    @app.post("/trilha/{block_id}/feito")
    def trilha_feito(request: Request, block_id: int, feito: str = Form("1"), volta: str = Form("/trilha")):
        user = me(request)
        if user is None:
            return to_login()
        try:
            trilha.mark(db, clock(), user, block_id, feito == "1")
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return trail_page(request, user, 422, error=str(exc))
        back = safe_back(volta, "/trilha")
        return RedirectResponse(back + ("#minha-trilha" if back == "/" else ""), status_code=303)

    @app.post("/trilha/{block_id}/justificar")
    def trilha_justificar(request: Request, block_id: int, texto: str = Form(""), tirar: str = Form(""),
                          volta: str = Form("/trilha")):
        user = me(request)
        if user is None:
            return to_login()
        try:
            trilha.justify(db, clock(), user, block_id, "" if tirar == "1" else texto)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return trail_page(request, user, 422, error=str(exc))
        back = safe_back(volta, "/trilha")
        message = quote("Justificativa tirada." if tirar == "1" or not texto.strip() else "Justificativa salva.")
        return RedirectResponse(f"{back}?ok={message}" + ("#minha-trilha" if back == "/" else ""), status_code=303)

    def block_values(b=None, person_id: int | None = None) -> dict:
        if b is None:
            return {"id": "", "person_id": person_id, "weekdays": [0, 1, 2, 3, 4], "starts_at": "", "ends_at": "",
                    "title": "", "details": "", "icon": "lista", "color": "", "kind": "tarefa", "routine_id": ""}
        return {"id": b.id, "person_id": b.person_id, "weekdays": list(b.weekdays), "starts_at": b.starts_at,
                "ends_at": b.ends_at, "title": b.title, "details": b.details, "icon": b.icon, "color": b.color,
                "kind": b.kind, "routine_id": b.routine_id or ""}

    def build_page(request: Request, user: Person, person: Person, status_code: int = 200, v: dict | None = None,
                   **ctx) -> HTMLResponse:
        people = list_people(db)
        blocks = trilha.list_blocks(db, person.id)
        return page(request, "trilha-montar.html", user, status_code, person=person, blocks=blocks,
                    v=v or block_values(person_id=person.id), WEEKDAYS=trilha.WEEKDAYS, ICONS=trilha.ICONS,
                    COLORS=trilha.COLORS, KINDS=trilha.KINDS, routines=[r for r in list_routines(db) if r.active],
                    choices=[p for p in people if trilha.can_edit(user, p.id)],
                    sources=[p for p in people if p.id != person.id and trilha.list_blocks(db, p.id)],
                    weekday_label=weekdays_label, **ctx)

    def build_target(request: Request, user: Person, raw) -> Person | Response:
        person = get_person(db, int(raw)) if str(raw).isdigit() else user
        if person is None:
            return RedirectResponse("/trilha/montar", status_code=303)
        if not trilha.can_edit(user, person.id):
            return forbidden(request, user, "Monta a trilha a própria pessoa, o gestor e os administradores.")
        return person

    def back_to_build(person_id: int, message: str) -> RedirectResponse:
        return RedirectResponse(f"/trilha/montar?pessoa={person_id}&ok={quote(message)}", status_code=303)

    @app.get("/trilha/montar", response_class=HTMLResponse)
    def trilha_montar(request: Request, pessoa: str = "", editar: str = "", ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        person = build_target(request, user, pessoa)
        if not isinstance(person, Person):
            return person
        b = trilha.get_block(db, int(editar)) if editar.isdigit() else None
        return build_page(request, user, person, v=block_values(b, person.id) if b and b.person_id == person.id
                          else None, ok=ok)

    async def save_trail_block(request: Request, block_id: int | None):
        user = me(request)
        if user is None:
            return to_login()
        form = await request.form()
        person = build_target(request, user, form.get("pessoa", ""))
        if not isinstance(person, Person):
            return person
        routine = str(form.get("routine_id", ""))
        v = {"id": block_id or "", "person_id": person.id,
             "weekdays": [int(d) for d in form.getlist("weekdays") if str(d).isdigit()],
             **{k: str(form.get(k, "")) for k in ("starts_at", "ends_at", "title", "details", "icon", "color", "kind")},
             "routine_id": routine}
        try:
            trilha.save_block(db, clock(), user, block_id, person_id=person.id, weekdays=v["weekdays"],
                              starts_at=v["starts_at"], ends_at=v["ends_at"], title=v["title"], details=v["details"],
                              icon=v["icon"], color=v["color"], kind=v["kind"],
                              routine_id=int(routine) if routine.isdigit() else None)
        except ValidationError as exc:
            return build_page(request, user, person, 422, v=v, error=str(exc))
        return back_to_build(person.id, "Bloco salvo.")

    @app.post("/trilha/montar")
    async def trilha_bloco_criar(request: Request):
        return await save_trail_block(request, None)

    @app.post("/trilha/montar/modelo")
    def trilha_modelo(request: Request, pessoa: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        person = build_target(request, user, pessoa)
        if not isinstance(person, Person):
            return person
        try:
            n = trilha.create_suggested(db, clock(), user, person.id)
        except ValidationError as exc:
            return build_page(request, user, person, 422, error=str(exc))
        return back_to_build(person.id, f"Trilha do modelo criada ({n} blocos). Ajuste o que for diferente.")

    @app.post("/trilha/montar/copiar")
    def trilha_copiar(request: Request, pessoa: str = Form(""), de: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        person = build_target(request, user, pessoa)
        if not isinstance(person, Person):
            return person
        try:
            n = trilha.copy_trail(db, clock(), user, int(de) if de.isdigit() else 0, person.id)
        except ValidationError as exc:
            return build_page(request, user, person, 422, error=str(exc))
        return back_to_build(person.id, f"{n} blocos copiados.")

    @app.post("/trilha/montar/tirar-tudo")
    def trilha_tirar_tudo(request: Request, pessoa: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        person = build_target(request, user, pessoa)
        if not isinstance(person, Person):
            return person
        n = trilha.remove_all(db, clock(), user, person.id)
        return back_to_build(person.id, f"{n} blocos tirados. A trilha de {person.name} ficou vazia: dá para montar "
                             "de novo, criar a do modelo ou copiar de outra pessoa.")

    @app.post("/trilha/montar/{block_id}")
    async def trilha_bloco_salvar(request: Request, block_id: int):
        return await save_trail_block(request, block_id)

    @app.post("/trilha/montar/{block_id}/tirar")
    def trilha_bloco_tirar(request: Request, block_id: int):
        user = me(request)
        if user is None:
            return to_login()
        b = trilha.get_block(db, block_id)
        try:
            trilha.remove_block(db, clock(), user, block_id)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError:
            return RedirectResponse("/trilha/montar", status_code=303)
        return back_to_build(b.person_id, f"“{b.title}” saiu da trilha.")

    # ---------- calendário (fase 13) ----------

    def cal_day(text: str) -> date | None:
        try:
            return date.fromisoformat(text) if text else None
        except ValueError:
            return None

    def calendar_page(request: Request, user: Person, status_code: int = 200, visao: str = "mes", dia: str = "",
                      filtros: tuple[str, ...] = calendario.DEFAULT_FILTERS, **ctx) -> HTMLResponse:
        today = clock().date()
        visao = visao if visao in ("mes", "semana", "lista") else "mes"
        ref = cal_day(dia) or today
        if visao == "mes":
            first = ref.replace(day=1)
            start = first - timedelta(days=first.weekday())
            last = date(first.year, first.month, monthrange(first.year, first.month)[1])
            end = last + timedelta(days=6 - last.weekday())
            prev, nxt = (first - timedelta(days=1)).replace(day=1), last + timedelta(days=1)
            title = f"{MONTHS[first.month - 1]} de {first.year}"
        elif visao == "semana":
            start = ref - timedelta(days=ref.weekday())
            end = start + timedelta(days=6)
            prev, nxt = start - timedelta(days=7), start + timedelta(days=7)
            title = f"Semana de {start:%d/%m} a {end:%d/%m/%Y}"
        else:
            start, end = ref, ref + timedelta(days=29)
            prev, nxt = ref - timedelta(days=30), ref + timedelta(days=30)
            title = f"Próximos 30 dias a partir de {start:%d/%m/%Y}"
        items = calendario.day_items(db, user, start, end, today, filtros)
        days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
        upcoming = calendario.absences_between(db, today, today + timedelta(days=60))
        people = list_people(db, active_only=False)
        ctx.setdefault("a", {"pessoa": str(user.id), "de": "", "ate": "", "motivo": ""})
        return page(request, "calendario.html", user, status_code, visao=visao, ref=ref, start=start, end=end,
                    days=days, weeks=[days[i:i + 7] for i in range(0, len(days), 7)], items=items, today=today,
                    prev=prev, nxt=nxt, title=title, filtros=filtros, FILTERS=calendario.FILTERS, DEFAULT_FILTERS=calendario.DEFAULT_FILTERS,
                    WEEKDAYS=calendario.WEEKDAYS, month=ref.month, absences=upcoming,
                    by_id={p.id: p for p in people}, team=[p for p in people if p.active],
                    can_mark=calendario.can_mark_absence, can_see_reason=calendario.can_see_reason,
                    can_manage_holidays=calendario.can_manage_holidays(user), **ctx)

    def cal_filters(request: Request) -> tuple[str, ...]:
        # "filtros=1" vem do formulário dos filtros: sem ele (link, menu), valem os de sempre
        if request.query_params.get("filtros") != "1":
            return calendario.DEFAULT_FILTERS
        return tuple(f for f in calendario.FILTERS if f in request.query_params.getlist("f"))

    @app.get("/calendario", response_class=HTMLResponse)
    def calendario_ver(request: Request, visao: str = "mes", data: str = "", ok: str = "", ver: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        if visao == "rotinas":
            return month_routines_page(request, user, dia=data, ver=ver, ok=ok)
        return calendar_page(request, user, visao=visao, dia=data, filtros=cal_filters(request), ok=ok)

    # ---------- rotinas do mês (fase 19): o calendário de rotinas do gestor ----------

    def month_routines_page(request: Request, user: Person, status_code: int = 200, dia: str = "", ver: str = "",
                            **ctx) -> HTMLResponse:
        today = clock().date()
        picked = cal_day(ver)  # o quadro do lado mostra o dia escolhido (um dia que passou, para justificar) ou hoje
        selected = picked if picked and picked < today else today
        ref = (cal_day(dia) or picked or today).replace(day=1)
        weeks = rotinas_mes.month_weeks(ref.year, ref.month)
        items = rotinas_mes.by_day(db, min(weeks[0][0], selected), max(weeks[-1][-1], today))
        hol = calendario.holidays(db)
        last = date(ref.year, ref.month, monthrange(ref.year, ref.month)[1])
        return page(request, "rotinas-mes.html", user, status_code, weeks=weeks, items=items, today=today,
                    ref=ref, month=ref.month, title=f"{MONTHS[ref.month - 1]} de {ref.year}",
                    prev=(ref - timedelta(days=1)).replace(day=1), nxt=last + timedelta(days=1),
                    holidays=hol.between(weeks[0][0], weeks[-1][-1]), today_items=items.get(selected, []),
                    selected=selected, can_justify=(today - selected).days <= rotinas_mes.NOTE_DAYS,
                    categories=rotinas_mes.list_categories(db, active_only=True),
                    by_id={p.id: p for p in list_people(db, active_only=False)},
                    can_manage=rotinas_mes.can_manage(user), **ctx)

    def month_routine_values(r=None) -> dict:
        if r is None:
            return {"id": "", "category_id": "", "title": "", "tipo": "semana", "dias": [], "n": "", "dia": "",
                    "data": "", "highlight": False, "owner_id": ""}
        return {"id": r.id, "category_id": r.category_id, "title": r.title, "tipo": r.rule["tipo"],
                "dias": r.rule.get("dias", []), "n": str(r.rule.get("n", "")), "dia": str(r.rule.get("dia", "")),
                "data": r.rule.get("data", ""), "highlight": r.highlight, "owner_id": r.owner_id or ""}

    def month_routines_admin(request: Request, user: Person, status_code: int = 200, v: dict | None = None,
                             **ctx) -> HTMLResponse:
        routines = rotinas_mes.list_routines(db)
        categories = rotinas_mes.list_categories(db)
        people = list_people(db, active_only=False)
        return page(request, "rotinas-mes-cadastro.html", user, status_code, routines=routines,
                    categories=categories, cats={c.id: c for c in categories}, v=v or month_routine_values(),
                    team=[p for p in people if p.active or (v and str(p.id) == str(v.get("owner_id")))],
                    by_id={p.id: p for p in people}, RULES=rotinas_mes.RULES, WEEKDAYS=rotinas_mes.WEEKDAYS,
                    can_manage=rotinas_mes.can_manage(user), **ctx)

    def back_to_month_admin(message: str) -> RedirectResponse:
        return RedirectResponse(f"/calendario/rotinas-do-mes?ok={quote(message)}", status_code=303)

    def month_manager(request: Request) -> tuple[Person | None, Response | None]:
        user = me(request)
        if user is None:
            return None, to_login()
        if not rotinas_mes.can_manage(user):
            return user, forbidden(request, user, "Só o gestor e os administradores mudam as rotinas do mês.")
        return user, None

    @app.get("/calendario/rotinas-do-mes", response_class=HTMLResponse)
    def rotinas_mes_cadastro(request: Request, editar: str = "", ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        r = rotinas_mes.get_routine(db, int(editar)) if editar.isdigit() else None
        return month_routines_admin(request, user, v=month_routine_values(r), ok=ok)

    async def save_month_routine(request: Request, routine_id: int | None):
        user, refused = month_manager(request)
        if refused:
            return refused
        form = await request.form()
        v = {"id": routine_id or "", "category_id": str(form.get("category_id", "")), "title": str(form.get("title", "")),
             "tipo": str(form.get("tipo", "")), "dias": [int(d) for d in form.getlist("dias") if str(d).isdigit()],
             "n": str(form.get("n", "")), "dia": str(form.get("dia", "")), "data": str(form.get("data", "")),
             "highlight": form.get("highlight") == "1", "owner_id": str(form.get("owner_id", ""))}
        try:
            rule = rotinas_mes.parse_rule(v["tipo"], [str(d) for d in v["dias"]], v["n"], v["dia"], v["data"])
            rotinas_mes.save_routine(db, clock(), user, routine_id, category_id=int(v["category_id"] or 0),
                                     title=v["title"], rule=rule, highlight=v["highlight"],
                                     owner_id=int(v["owner_id"]) if v["owner_id"].isdigit() else None)
        except ValidationError as exc:
            return month_routines_admin(request, user, 422, v=v, error=str(exc))
        return back_to_month_admin("Rotina do mês salva.")

    @app.post("/calendario/rotinas-do-mes")
    async def rotinas_mes_criar(request: Request):
        return await save_month_routine(request, None)

    @app.post("/calendario/rotinas-do-mes/sugeridas")
    def rotinas_mes_sugeridas(request: Request):
        user, refused = month_manager(request)
        if refused:
            return refused
        n = rotinas_mes.create_suggested(db, clock(), user)
        return back_to_month_admin(f"{n} rotina{'s' if n != 1 else ''} do modelo criada{'s' if n != 1 else ''}."
                                   if n else "As rotinas do modelo já existem.")

    @app.post("/calendario/rotinas-do-mes/categorias")
    def rotinas_mes_categoria_criar(request: Request, nome: str = Form(""), cor: str = Form("")):
        user, refused = month_manager(request)
        if refused:
            return refused
        try:
            rotinas_mes.save_category(db, clock(), user, None, nome, cor)
        except ValidationError as exc:
            return month_routines_admin(request, user, 422, error=str(exc))
        return back_to_month_admin("Categoria criada.")

    @app.post("/calendario/rotinas-do-mes/categorias/{category_id}")
    def rotinas_mes_categoria_salvar(request: Request, category_id: int, nome: str = Form(""), cor: str = Form(""),
                                     acao: str = Form("salvar")):
        user, refused = month_manager(request)
        if refused:
            return refused
        try:
            if acao == "remover":
                rotinas_mes.remove_category(db, clock(), user, category_id)
            else:
                rotinas_mes.save_category(db, clock(), user, category_id, nome, cor)
        except ValidationError as exc:
            return month_routines_admin(request, user, 422, error=str(exc))
        return back_to_month_admin("Categoria removida." if acao == "remover" else "Categoria salva.")

    @app.post("/calendario/rotinas-do-mes/{routine_id}")
    async def rotinas_mes_salvar(request: Request, routine_id: int):
        return await save_month_routine(request, routine_id)

    @app.post("/calendario/rotinas-do-mes/{routine_id}/ativa")
    def rotinas_mes_ativa(request: Request, routine_id: int, active: str = Form("1")):
        user, refused = month_manager(request)
        if refused:
            return refused
        try:
            rotinas_mes.set_active(db, clock(), user, routine_id, active == "1")
        except ValidationError as exc:
            return month_routines_admin(request, user, 422, error=str(exc))
        return back_to_month_admin("Rotina reativada." if active == "1" else "Rotina desativada.")

    @app.post("/calendario/rotinas-do-mes/{routine_id}/feita")
    def rotinas_mes_feita(request: Request, routine_id: int, feita: str = Form("1")):
        user = me(request)
        if user is None:
            return to_login()
        try:
            rotinas_mes.mark_done(db, clock(), user, routine_id, feita == "1")
        except ValidationError as exc:
            return month_routines_page(request, user, 422, error=str(exc))
        return RedirectResponse("/calendario?visao=rotinas#hoje", status_code=303)

    @app.post("/calendario/rotinas-do-mes/{routine_id}/justificar")
    def rotinas_mes_justificar(request: Request, routine_id: int, dia: str = Form(""), texto: str = Form(""),
                               tirar: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        day = cal_day(dia) or clock().date()
        try:
            rotinas_mes.justify(db, clock(), user, routine_id, day, "" if tirar == "1" else texto)
        except ValidationError as exc:
            return month_routines_page(request, user, 422, dia=day.isoformat(), ver=day.isoformat(), error=str(exc))
        message = "Justificativa tirada." if tirar == "1" or not texto.strip() else "Justificativa salva."
        ver = f"&ver={day.isoformat()}" if day != clock().date() else ""
        return RedirectResponse(f"/calendario?visao=rotinas&data={day.isoformat()}{ver}&ok={quote(message)}#hoje",
                                status_code=303)

    def back_to_calendar(message: str = "", day: date | None = None) -> RedirectResponse:
        qs = {k: v for k, v in (("data", day.isoformat() if day else ""), ("ok", message)) if v}
        return RedirectResponse("/calendario" + (f"?{urlencode(qs)}" if qs else ""), status_code=303)

    def event_values(e=None, day: str = "", user: Person | None = None) -> dict:
        if e is None:
            return {"id": "", "title": "", "kind": "reuniao", "starts_on": day, "ends_on": "", "starts_at": "",
                    "ends_at": "", "place": "", "description": "", "visibility": "equipe", "reserved": False,
                    "repeat": "", "people": [user.id] if user else []}
        return {"id": e.id, "title": e.title, "kind": e.kind, "starts_on": e.starts_on.isoformat(),
                "ends_on": e.ends_on.isoformat() if e.ends_on else "", "starts_at": e.starts_at or "",
                "ends_at": e.ends_at or "", "place": e.place or "", "description": e.description or "",
                "visibility": e.visibility, "reserved": e.reserved, "repeat": e.repeat, "people": list(e.people)}

    def event_page(request: Request, user: Person, v: dict, status_code: int = 200, event=None,
                   **ctx) -> HTMLResponse:
        people = list_people(db)
        extra = [p for p in list_people(db, active_only=False) if not p.active and p.id in v["people"]]
        return page(request, "compromisso.html", user, status_code, v=v, event=event, team=people + extra,
                    KINDS=calendario.KINDS, REPEATS=calendario.REPEATS,
                    can_edit=event is None or calendario.can_edit_event(event, user),
                    creator=get_person(db, event.created_by) if event and event.created_by else None, **ctx)

    def parse_event(form) -> tuple[dict, dict]:
        values = {k: str(form.get(k, "")) for k in ("title", "kind", "starts_on", "ends_on", "starts_at", "ends_at",
                                                     "place", "description", "visibility", "repeat")}
        values["reserved"] = form.get("reserved") == "1"
        values["people"] = [int(p) for p in form.getlist("people") if str(p).isdigit()]
        fields = {**{k: values[k] for k in ("title", "kind", "starts_at", "ends_at", "place", "description",
                                            "visibility", "repeat", "reserved", "people")},
                  "starts_on": cal_day(values["starts_on"]), "ends_on": cal_day(values["ends_on"])}
        return values, fields

    @app.get("/calendario/novo", response_class=HTMLResponse)
    def calendario_novo(request: Request, data: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        day = cal_day(data) or clock().date()
        return event_page(request, user, event_values(day=day.isoformat(), user=user))

    @app.post("/calendario")
    async def calendario_criar(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        values, fields = parse_event(await request.form())
        try:
            e = calendario.save_event(db, clock(), user, None, **fields)
        except ValidationError as exc:
            return event_page(request, user, {**values, "id": ""}, 422, error=str(exc))
        return back_to_calendar("Compromisso salvo.", e.starts_on)

    # ausências e feriados vêm antes de /calendario/{id}, senão "ausencias" viraria um id
    @app.post("/calendario/ausencias")
    def calendario_ausencia(request: Request, pessoa: str = Form(""), de: str = Form(""), ate: str = Form(""),
                            motivo: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        person_id = int(pessoa) if pessoa.isdigit() else user.id
        try:
            calendario.add_absence(db, clock(), user, person_id, cal_day(de), cal_day(ate), motivo)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return calendar_page(request, user, 422, error=str(exc),
                                 a={"pessoa": pessoa, "de": de, "ate": ate, "motivo": motivo})
        return back_to_calendar("Ausência marcada.", cal_day(de))

    @app.post("/calendario/ausencias/{absence_id}/excluir")
    def calendario_ausencia_excluir(request: Request, absence_id: int):
        user = me(request)
        if user is None:
            return to_login()
        try:
            calendario.delete_absence(db, clock(), user, absence_id)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return calendar_page(request, user, 422, error=str(exc))
        return back_to_calendar("Ausência removida.")

    def holidays_page(request: Request, user: Person, year: int, status_code: int = 200, **ctx) -> HTMLResponse:
        rows = calendario.holidays(db).year(year)
        return page(request, "feriados.html", user, status_code, year=year, rows=rows.values(),
                    can_manage=calendario.can_manage_holidays(user), WEEKDAYS=calendario.WEEKDAYS, **ctx)

    @app.get("/calendario/feriados", response_class=HTMLResponse)
    def calendario_feriados(request: Request, ano: str = "", ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        year = int(ano) if ano.isdigit() and 2000 <= int(ano) <= 2100 else clock().year
        return holidays_page(request, user, year, ok=ok)

    def back_to_holidays(year: int, message: str) -> RedirectResponse:
        return RedirectResponse(f"/calendario/feriados?ano={year}&ok={quote(message)}", status_code=303)

    @app.post("/calendario/feriados")
    def calendario_feriado_criar(request: Request, dia: str = Form(""), nome: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        day = cal_day(dia)
        try:
            if day is None:
                raise ValidationError("Informe o dia do feriado.")
            calendario.add_local_holiday(db, clock(), user, day, nome)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return holidays_page(request, user, day.year if day else clock().year, 422, error=str(exc),
                                 v={"dia": dia, "nome": nome})
        return back_to_holidays(day.year, "Feriado acrescentado.")

    @app.post("/calendario/feriados/{dia}/{acao}")
    def calendario_feriado_acao(request: Request, dia: str, acao: str):
        user = me(request)
        if user is None:
            return to_login()
        day = cal_day(dia)
        if day is None or acao not in ("ligar", "desligar", "remover"):
            return Response(status_code=404)
        try:
            if acao == "remover":
                calendario.remove_local_holiday(db, clock(), user, day)
            else:
                calendario.set_holiday_active(db, clock(), user, day, acao == "ligar")
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return holidays_page(request, user, day.year, 422, error=str(exc))
        return back_to_holidays(day.year, {"ligar": "Feriado ligado.", "desligar": "Feriado desligado: o dia "
                                           "volta a contar como dia útil.", "remover": "Feriado removido."}[acao])

    def visible_event(request: Request, user: Person, event_id: int):
        """O compromisso, se a pessoa pode abrir; senão, a resposta de erro."""
        e = calendario.get_event(db, event_id)
        if e is None or not calendario.can_see_event(e, user):
            return None, page(request, "sem-permissao.html", user, 404, message="Compromisso não encontrado.")
        if not calendario.can_see_title(e, user):
            return None, forbidden(request, user, "Compromisso reservado: só quem participa, o gestor e os "
                                                  "administradores abrem.")
        return e, None

    @app.get("/calendario/{event_id}", response_class=HTMLResponse)
    def calendario_abrir(request: Request, event_id: int, ok: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        e, error = visible_event(request, user, event_id)
        return error or event_page(request, user, event_values(e), event=e, ok=ok)

    @app.post("/calendario/{event_id}")
    async def calendario_salvar(request: Request, event_id: int):
        user = me(request)
        if user is None:
            return to_login()
        e, error = visible_event(request, user, event_id)
        if error:
            return error
        values, fields = parse_event(await request.form())
        try:
            saved = calendario.save_event(db, clock(), user, event_id, **fields)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return event_page(request, user, {**values, "id": event_id}, 422, event=e, error=str(exc))
        return back_to_calendar("Compromisso salvo.", saved.starts_on)

    @app.post("/calendario/{event_id}/excluir")
    def calendario_excluir(request: Request, event_id: int):
        user = me(request)
        if user is None:
            return to_login()
        e, error = visible_event(request, user, event_id)
        if error:
            return error
        try:
            calendario.delete_event(db, clock(), user, event_id)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        return back_to_calendar("Compromisso apagado.", e.starts_on)

    # ---------- prioridades do mês ----------

    def priorities_page(request: Request, user: Person, month: str = "", status_code: int = 200, **ctx) -> HTMLResponse:
        now = clock()
        current = month_of(now)
        # um mês anterior abre só para consulta; mês inválido ou futuro volta para o atual
        month = month if is_month(month) and month <= current else current
        items = list_month(db, month)
        mine = pastas.folders_of(db, user.id)
        ctx.setdefault("v", {"title": "", "folder": "", "prazo": "", "etapas": ""})
        return page(request, "prioridades.html", user, status_code, month=month, current=current, items=items,
                    mine=mine, owners=pastas.owners(db), folder_summary=by_folder(items),
                    can_mark=lambda folder: can_mark(user, folder, mine),
                    editable=month == current, months=[current] + past_months(db, now), today=now.date(),
                    done_count=sum(p.done for p in items), late_count=sum(is_late(p, now.date()) for p in items),
                    people={p.id: p for p in list_people(db, active_only=False)}, last_day=last_day(month),
                    month_label=month_label, is_late=is_late, can_remove=can_remove, DEFAULT_LIST=DEFAULT_LIST, **ctx)

    def back_to_priorities() -> RedirectResponse:
        return RedirectResponse("/prioridades", status_code=303)

    @app.get("/prioridades", response_class=HTMLResponse)
    def prioridades(request: Request, mes: str = ""):
        user = me(request)
        return to_login() if user is None else priorities_page(request, user, mes)

    @app.post("/prioridades")
    def prioridades_acrescentar(request: Request, title: str = Form(""), folder: str = Form(""), prazo: str = Form(""),
                                etapas: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        try:
            add_priority(db, clock(), user, title, folder or None, parse_due_day(prazo), parse_steps(etapas))
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return priorities_page(request, user, status_code=422, error=str(exc),
                                   v={"title": title, "folder": folder, "prazo": prazo, "etapas": etapas})
        return back_to_priorities()

    @app.post("/prioridades/padrao")
    def prioridades_padrao(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        try:
            create_default_list(db, clock(), user)  # o mês já tem lista (outro PC criou antes): não muda nada
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        return back_to_priorities()

    @app.post("/prioridades/{item_id}/{action}")
    def prioridades_item(request: Request, item_id: int, action: str, pasta: str = "", etapa: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        actions = {"feita": mark_done, "desfazer": undo_done, "remover": remove_priority}
        if action not in actions:
            return Response(status_code=404)
        try:
            if action == "remover":
                remove_priority(db, clock(), user, item_id)
            else:  # sem pasta: as pastas de quem clicou
                actions[action](db, clock(), user, item_id, pasta or None, int(etapa) if etapa.isdigit() else None)
        except PermissionError as exc:
            return forbidden(request, user, str(exc))
        except ValidationError as exc:
            return priorities_page(request, user, status_code=422, error=str(exc))
        return back_to_priorities()

    # ---------- configurações (administrador) ----------

    def config_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        demands = all_demands(db)
        trash = [(a, demands.get(a.parent_id)) for a in anexos.trash(db, clock(), "demanda")]
        return page(request, "configuracoes.html", user, status_code, config=screen_config(db),
                    anexos_cfg={"folder": str(anexos.folder(db)) if anexos.get_setting(db, anexos.SETTING_FOLDER) else "",
                                "default_folder": str(anexos.default_folder()), "usage": anexos.usage(db),
                                "trash": trash, "trash_days": anexos.TRASH_DAYS},
                    paineis=panel_config(db), drive=drive.drive_config(db),
                    drive_limits={"min": drive.MINUTES_MIN, "max": drive.MINUTES_MAX}, pombo=pombo_config(db),
                    stale_limits={"min": STALE_MIN, "max": STALE_MAX},
                    limits={"min": MIN_SECONDS, "max": MAX_SECONDS, "page_min": PAGE_MIN, "page_max": PAGE_MAX}, **ctx)

    @app.get("/configuracoes", response_class=HTMLResponse)
    def configuracoes(request: Request):
        user, stop = admin_only(request)
        return stop or config_page(request, user)

    @app.post("/configuracoes")
    async def configuracoes_salvar(request: Request):
        user, stop = admin_only(request)
        if stop:
            return stop
        form = await request.form()
        seconds = {k.removeprefix("segundos_"): str(v).strip() for k, v in form.items() if k.startswith("segundos_")}
        enabled = {k.removeprefix("ligada_") for k in form if k.startswith("ligada_")}
        try:
            save_screen_config(db, clock(), user, seconds, enabled, str(form.get("pagina", "")).strip())
        except ValidationError as exc:
            return config_page(request, user, 422, error=str(exc))
        return config_page(request, user, ok=True)

    @app.post("/configuracoes/anexos")
    def configuracoes_anexos(request: Request, pasta: str = Form("")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            anexos.save_folder(db, clock(), user, pasta)
        except ValidationError as exc:
            return config_page(request, user, 422, error_anexos=str(exc))
        return config_page(request, user, ok_anexos=True)

    @app.post("/configuracoes/anexos/{attachment_id}/restaurar")
    def configuracoes_anexo_restaurar(request: Request, attachment_id: int):
        user, stop = admin_only(request)
        if stop:
            return stop
        a = anexos.find(db, attachment_id)
        try:
            if a is None or a.kind != "demanda":
                raise ValidationError("Esse arquivo não está mais na lixeira.")
            anexos.restore(db, clock(), user, a, subject=f"demanda:{a.parent_id}")
        except ValidationError as exc:
            return config_page(request, user, 422, error_anexos=str(exc))
        return config_page(request, user, ok_anexos=f"“{a.name}” voltou para a demanda.")

    @app.post("/configuracoes/paineis")
    def configuracoes_paineis(request: Request, pasta: str = Form(""), horas: str = Form("")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            save_panel_config(db, clock(), user, pasta, horas.strip())
        except ValidationError as exc:
            return config_page(request, user, 422, error_paineis=str(exc))
        return config_page(request, user, ok_paineis=True)

    @app.post("/configuracoes/drive")
    def configuracoes_drive(request: Request, url: str = Form(""), chave: str = Form(""), minutos: str = Form(""),
                            gerar: str = Form("")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            created = drive.save_drive_config(db, clock(), user, url, chave, minutos.strip(), generate=bool(gerar))
        except ValidationError as exc:
            return config_page(request, user, 422, error_drive=str(exc))
        return config_page(request, user, ok_drive=True, new_key=created)

    @app.post("/configuracoes/pombo")
    def configuracoes_pombo(request: Request, pasta: str = Form("")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            save_pombo_config(db, clock(), user, pasta)
        except ValidationError as exc:
            return config_page(request, user, 422, error_pombo=str(exc))
        return config_page(request, user, ok_pombo=True)

    # ---------- painéis de dados ----------

    def panels_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        snap = store_for(db).get(wait=True)
        now = clock()
        sales = snap.status("vendas").modified
        return page(request, "paineis.html", user, status_code, snap=snap, now=now, drive=drive.drive_config(db),
                    phd=phd.phd_config(db),
                    stale=sales is not None and now - sales > timedelta(hours=stale_hours(db)), **ctx)

    @app.get("/paineis", response_class=HTMLResponse)
    def paineis(request: Request):
        user = me(request)
        return to_login() if user is None else panels_page(request, user)

    @app.post("/paineis/enviar/{key}")
    def paineis_enviar(request: Request, key: str, arquivo: UploadFile = File(...)):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            save_upload(db, clock(), user, key, arquivo.filename or "", arquivo.file)
        except ValidationError as exc:
            return panels_page(request, user, 422, error=str(exc))
        except OSError:
            return panels_page(request, user, 422, error="Não consegui gravar na pasta dos painéis. Confira se ela existe e se o PC da sala pode escrever nela.")
        return RedirectResponse("/paineis?enviado=1", status_code=303)

    @app.post("/paineis/drive/baixar")
    def paineis_drive_baixar(request: Request):
        user, stop = admin_only(request)
        if stop:
            return stop
        result = drive.sync(db, clock())
        if not result.ok:
            return panels_page(request, user, 422, error=result.message)
        if result.changed:
            store_for(db).get(wait=True)  # a página já mostra o arquivo novo lido
        return panels_page(request, user, drive_ok=result.message)

    @app.post("/paineis/phd/gerar")
    def paineis_phd_gerar(request: Request):
        user, stop = admin_only(request)
        if stop:
            return stop
        result = phd.generate(db, clock(), force=True)
        if not result.ok:
            return panels_page(request, user, 422, error=result.message)
        return panels_page(request, user, phd_ok=result.message)

    @app.post("/paineis/phd/configurar")
    def paineis_phd_configurar(request: Request, pasta: str = Form(""), areas: str = Form("")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            phd.save_phd_config(db, clock(), user, pasta, areas)
        except ValidationError as exc:
            return panels_page(request, user, 422, error=str(exc))
        result = phd.generate(db, clock(), force=True)
        return panels_page(request, user, phd_ok="Configuração salva. " + result.message)

    @app.get("/paineis/phd/{name}")
    def paineis_phd_baixar(request: Request, name: str):
        user = me(request)
        if user is None:
            return to_login()
        # só os arquivos que o próprio Hub gerou, nunca um caminho qualquer
        if name not in phd.state(db).get("arquivos", []):
            return Response(status_code=404)
        path = phd.output_folder(db) / name
        if not path.is_file():
            return Response(status_code=404)
        return FileResponse(path, filename=name,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ---------- envios do Pombo ----------

    @app.get("/envios", response_class=HTMLResponse)
    def envios_do_dia(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        now = clock()
        snap = envios_store(db).get(now, wait=True)
        runs = runs_of_day(snap.rows, now.date(), now) if snap else []
        return page(request, "envios.html", user, folder=history_folder(db), snap=snap, runs=runs, now=now,
                    who=who_is_who(db, snap) if snap else {}, status_text=status_text, count_text=count_text,
                    channel_text=channel_text, target_text=target_text,
                    groups={g: sum(r.group == g for r in runs) for g in ("ok", "falha", "andamento")})

    # ---------- visão do gestor ----------

    templates.env.globals["can_open_gestor"] = can_open

    @app.get("/gestor", response_class=HTMLResponse)
    def gestor(request: Request, pessoa: str = "", coluna: str = "", prazo: str = "", atrasadas: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        if not can_open(user):
            return forbidden(request, user, "Só o gestor e os administradores podem abrir a visão do gestor.")
        now = clock()
        owner_id = int(pessoa) if pessoa.isdigit() else None
        prazo = prazo if prazo in DUE_FILTERS else ""
        demands = filter_demands(db, now, owner_id=owner_id, column=coluna, due=prazo, overdue_only=bool(atrasadas))
        team = team_summary(db, now)
        return page(request, "gestor.html", user, team=team, demands=demands, today=now.date(), now=now,
                    owners={p.id: p for p in list_people(db, active_only=False)}, people=list_people(db),
                    f={"pessoa": pessoa, "coluna": coluna, "prazo": prazo, "atrasadas": bool(atrasadas)},
                    DUE_FILTERS=DUE_FILTERS, history_start=first_event_day(db) or now.date(),
                    totals={"done": sum(r.done_today for r in team), "overdue": sum(r.overdue for r in team),
                            "doing": sum(r.doing for r in team), "todo": sum(r.todo for r in team),
                            "in_room": sum(r.status == "Na sala" for r in team)})

    # ---------- banco de horas (só a própria pessoa e o gestor; a TV nunca consulta) ----------

    def hours_page(request: Request, user: Person, person: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        today = clock().date()
        s = horas.summary(db, person.id, today)
        default_day = s.missing[0] if s.missing else today - timedelta(days=1)
        return page(request, "horas.html", user, status_code, person=person, s=s, today=today,
                    own=person.id == user.id, default_day=default_day,
                    journey=horas.journey(db, person.is_assistant), h=horas, **ctx)

    @app.get("/horas", response_class=HTMLResponse)
    def horas_minhas(request: Request, corrigir: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        fix = None
        if corrigir:
            try:
                day = date.fromisoformat(corrigir)
            except ValueError:
                day = None
            fix = next((e for e in horas.summary(db, user.id, clock().date()).entries if e.day == day), None)
        return hours_page(request, user, user, fix=fix)

    @app.post("/horas")
    def horas_lancar(request: Request, dia: str = Form(""), entrada: str = Form(""), saida: str = Form(""),
                     corrigir: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        typed = {"dia": dia, "entrada": entrada, "saida": saida, "corrigir": corrigir}
        try:
            try:
                day = date.fromisoformat(dia)
            except ValueError:
                raise ValidationError("Escolha o dia.")
            horas.save_entry(db, clock(), user, day, entrada, saida, bool(corrigir))
        except ValidationError as exc:
            return hours_page(request, user, user, 422, error=str(exc), typed=typed)
        return RedirectResponse("/horas?salvo=1", status_code=303)

    @app.post("/horas/{dia}/excluir")
    def horas_excluir(request: Request, dia: str):
        user = me(request)
        if user is None:
            return to_login()
        try:
            horas.delete_entry(db, clock(), user, date.fromisoformat(dia))
        except (ValidationError, ValueError):
            pass  # já não estava lá: a página mostra a verdade
        return RedirectResponse("/horas", status_code=303)

    def hours_manager_only(request: Request) -> tuple[Person | None, Response | None]:
        user = me(request)
        if user is None:
            return None, to_login()
        if not user.is_manager:
            return user, forbidden(request, user, "O banco de horas da equipe é só do gestor.")
        return user, None

    def team_hours_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        today = clock().date()
        return page(request, "horas-equipe.html", user, status_code, rows=horas.team(db, today), today=today,
                    journey=horas.journey(db), assistant_journey=horas.journey(db, assistant=True), h=horas,
                    people=list_people(db), **ctx)

    @app.get("/horas/equipe", response_class=HTMLResponse)
    def horas_equipe(request: Request):
        user, stop = hours_manager_only(request)
        return stop or team_hours_page(request, user)

    @app.get("/horas/equipe/{person_id}", response_class=HTMLResponse)
    def horas_pessoa(request: Request, person_id: int):
        user, stop = hours_manager_only(request)
        if stop:
            return stop
        person = get_person(db, person_id)
        if person is None:
            return RedirectResponse("/horas/equipe", status_code=303)
        return hours_page(request, user, person)

    @app.post("/horas/equipe/importar")
    def horas_importar(request: Request, arquivo: UploadFile = File(...)):
        user, stop = hours_manager_only(request)
        if stop:
            return stop
        try:
            updated, unknown = horas.import_balances(db, clock(), user, arquivo.filename or "", arquivo.file)
        except ValidationError as exc:
            return team_hours_page(request, user, 422, error=str(exc))
        return team_hours_page(request, user, imported=updated, unknown=unknown)

    @app.post("/horas/equipe/saldo")
    def horas_saldo(request: Request, pessoa: str = Form(""), saldo: str = Form(""), data: str = Form("")):
        user, stop = hours_manager_only(request)
        if stop:
            return stop
        try:
            try:
                as_of = date.fromisoformat(data)
            except ValueError:
                raise ValidationError("Escolha a data do saldo.")
            if not pessoa.isdigit():
                raise ValidationError("Escolha a pessoa.")
            horas.set_balance(db, clock(), user, int(pessoa), horas.parse_duration(saldo), as_of)
        except ValidationError as exc:
            return team_hours_page(request, user, 422, error=str(exc))
        return team_hours_page(request, user, ok="Saldo base salvo.")

    @app.post("/horas/equipe/jornada")
    def horas_jornada(request: Request, semana: str = Form(""), sabado: str = Form(""), quem: str = Form("")):
        user, stop = hours_manager_only(request)
        if stop:
            return stop
        assistant = quem == "assistente"
        try:
            horas.save_journey(db, clock(), user, semana, sabado, assistant)
        except ValidationError as exc:
            return team_hours_page(request, user, 422, error=str(exc))
        return team_hours_page(request, user, ok="Jornada dos assistentes salva." if assistant else "Jornada salva.")

    @app.get("/horas/exportar")
    def horas_exportar(request: Request, tipo: str = "saldos", formato: str = "xlsx", de: str = "", ate: str = ""):
        user, stop = hours_manager_only(request)
        if stop:
            return stop
        today = clock().date()
        tipo = tipo if tipo in ("saldos", "lancamentos") else "saldos"
        try:
            start = date.fromisoformat(de) if de else None
            end = date.fromisoformat(ate) if ate else None
        except ValueError:
            start = end = None
        rows = horas.export_rows(db, today, tipo, start, end)
        name = f"banco-de-horas-{tipo}-{today:%Y-%m-%d}"
        if formato == "csv":
            content, media = horas.to_csv(rows), "text/csv; charset=utf-8"
        else:
            content, media = horas.to_xlsx(rows, tipo), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            formato = "xlsx"
        return Response(content, media_type=media,
                        headers={"Content-Disposition": f'attachment; filename="{name}.{formato}"'})

    # ---------- histórico ----------

    @app.get("/historico", response_class=HTMLResponse)
    def historico(request: Request, de: str = "", ate: str = "", pessoa: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        end = date.fromisoformat(ate) if ate else clock().date()
        start = date.fromisoformat(de) if de else end - timedelta(days=6)
        person_id = int(pessoa) if pessoa.isdigit() else None
        rows = events(db, start, end, person_id)
        people = {p.id: p for p in list_people(db, active_only=False)}
        demands = all_demands(db)
        # banco de horas: a linha só aparece para a própria pessoa e o gestor
        rows = [r for r in rows if not r["subject"].startswith("horas:")
                or horas.can_see(user, int(r["subject"].partition(":")[2]))]
        cal_events = calendario.all_events(db)
        lines = [(datetime.fromisoformat(r["at"]), describe(r, people, demands, user, cal_events)) for r in rows]
        return page(request, "historico.html", user, lines=lines, start=start, end=end, pessoa=pessoa,
                    people=list_people(db, active_only=False))

    # ---------- pessoas ----------

    def people_gate(request: Request) -> tuple[Person | None, Response | None]:
        """Pessoas é só de administrador. Exceção: Hub vazio, para cadastrar a primeira pessoa."""
        user = me(request)
        if not list_people(db):
            return user, None
        if user is None:
            return None, to_login()
        if not user.is_admin:
            return user, forbidden(request, user)
        return user, None

    def people_page(request: Request, user: Person | None, status_code: int = 200, **ctx) -> HTMLResponse:
        # quem saiu da equipe e deixou notas: o administrador só vê quantas são e pode apagar de vez
        left = [(p, notas.count_for(db, p.id)) for p in list_people(db, active_only=False) if not p.active]
        return page(request, "pessoas.html", user, status_code, people=list_people(db), palette=PALETTE,
                    folders_of=pastas.folders_by_person(db), signups=cadastro.pending(db, clock()),
                    SIGNUP_ROLES=cadastro.SIGNUP_ROLES, left_notes=[(p, n) for p, n in left if n], **ctx)

    @app.get("/pessoas", response_class=HTMLResponse)
    def pessoas(request: Request):
        user, stop = people_gate(request)
        return stop or people_page(request, user)

    @app.post("/pessoas")
    async def pessoas_salvar(request: Request):
        user, stop = people_gate(request)
        if stop:
            return stop
        form = await request.form()
        actor = user.id if user else None
        try:
            if form.get("id"):
                update_person(db, clock(), actor, int(form["id"]), name=form.get("name", ""),
                              initials=form.get("initials", ""), color=form.get("color", ""))
            else:
                add_person(db, clock(), actor, form.get("name", ""), form.get("initials", ""), form.get("color", ""))
        except ValidationError as exc:
            return people_page(request, user, 422, error=str(exc),
                               v={k: form.get(k, "") for k in ("id", "name", "initials", "color")})
        return RedirectResponse("/pessoas", status_code=303)

    def admin_only(request: Request) -> tuple[Person | None, Response | None]:
        user = me(request)
        if user is None:
            return None, to_login()
        if not user.is_admin:
            return user, forbidden(request, user)
        return user, None

    @app.post("/pessoas/pedidos/{request_id}/{acao}")
    def pessoas_pedido(request: Request, request_id: int, acao: str, role: str = Form("analista")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            if acao == "aprovar":
                person = cadastro.approve(db, clock(), user, request_id, role)
                return people_page(request, user, ok=f"{person.name} entrou na equipe como {ROLES[person.role]}. "
                                                     "Já pode entrar com o nome e o PIN que escolheu.")
            if acao == "recusar":
                cadastro.reject(db, clock(), user, request_id)
                return people_page(request, user, ok="Pedido recusado.")
        except ValidationError as exc:
            return people_page(request, user, 422, error=str(exc))
        return Response(status_code=404)

    @app.post("/pessoas/{person_id}/acesso")
    def pessoas_acesso(request: Request, person_id: int, role: str = Form(...), admin: str = Form("")):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            set_access(db, clock(), user, person_id, role, admin == "on")
        except ValidationError as exc:
            return people_page(request, user, 422, error=str(exc))
        return RedirectResponse("/pessoas", status_code=303)

    @app.post("/pessoas/{person_id}/pastas")
    async def pessoas_pastas(request: Request, person_id: int):
        user, stop = admin_only(request)
        if stop:
            return stop
        form = await request.form()
        try:
            pastas.set_folders(db, clock(), user, person_id, form.getlist("pasta"))
        except ValidationError as exc:
            return people_page(request, user, 422, error=str(exc))
        return RedirectResponse("/pessoas", status_code=303)

    @app.post("/pessoas/{person_id}/pin")
    def pessoas_redefinir_pin(request: Request, person_id: int):
        user, stop = admin_only(request)
        if stop:
            return stop
        reset_pin(db, clock(), user, person_id)
        return RedirectResponse("/pessoas", status_code=303)

    @app.post("/pessoas/{person_id}/apagar-notas")
    def pessoas_apagar_notas(request: Request, person_id: int):
        user, stop = admin_only(request)
        if stop:
            return stop
        person = get_person(db, person_id)
        try:
            if person is None:
                raise ValidationError("Pessoa não encontrada.")
            erased = notas.erase_person_notes(db, clock(), user, person)
        except ValidationError as exc:
            return people_page(request, user, 422, error=str(exc))
        return people_page(request, user, ok=f"{erased} nota{'s' if erased != 1 else ''} de {person.name} apagada{'s' if erased != 1 else ''} de vez.")

    @app.post("/pessoas/{person_id}/desativar")
    def pessoas_desativar(request: Request, person_id: int):
        user, stop = admin_only(request)
        if stop:
            return stop
        try:
            deactivate_person(db, clock(), user.id, person_id)
        except ValidationError as exc:
            return people_page(request, user, 422, error=str(exc))
        return RedirectResponse("/pessoas", status_code=303)

    app.state.templates = templates
    return app


def describe(row, people: dict, demands: dict, viewer: Person, cal_events: dict | None = None) -> str:
    """Uma linha de histórico em português. Demanda e compromisso reservados só mostram o título a quem pode vê-lo."""
    who = people[row["actor_id"]].name if row["actor_id"] in people else "Alguém"
    kind, subject, detail = row["kind"], row["subject"], row["detail"]
    ref = subject.partition(":")[2]
    ref_id = int(ref) if ref.isdigit() else 0  # "config:tv" não aponta para ninguém
    title, changes, visible = "", "", True
    if subject.startswith("demanda:"):
        d = demands.get(ref_id)
        visible = d is None or can_see(d, viewer)
        if kind == "demanda_editada":
            detail, _, changes = detail.partition(CHANGES_SEP)
        title = detail if d is None else d.title if visible else RESERVED_TEXT
    if subject.startswith("compromisso:"):
        e = (cal_events or {}).get(ref_id)
        title = detail if e is None or calendario.can_see_title(e, viewer) else calendario.RESERVED_TEXT
    file_name = f"“{detail}”" if visible else "um arquivo"  # nome de arquivo de reservada também é escondido
    name = people[ref_id].name if subject.startswith("pessoa:") and ref_id in people else detail
    name_of = lambda pid: people[pid].name if pid in people else "alguém"
    # prioridade por pasta: "B,C|título"
    folder_list, _, folder_title = detail.partition("|") if kind.startswith("prioridade_pasta_") else ("", "", "")
    folder_list = folder_list.split(",") if folder_list else []
    folder_text = (("na pasta " if len(folder_list) == 1 else "nas pastas ")
                   + ", ".join(folder_list[:-1]) + (" e " if len(folder_list) > 1 else "") + folder_list[-1]
                   if folder_list else "")
    return {
        "demanda_criada": f"{who} criou “{title}”",
        "demanda_editada": f"{who} editou “{title}”" + (f": {changes}" if changes and visible else ""),
        "anexo_enviado": f"{who} anexou {file_name} em “{title}”",
        "anexo_versao": f"{who} enviou uma nova versão de {file_name} em “{title}”",
        "anexo_removido": f"{who} removeu {file_name} de “{title}”",
        "anexo_restaurado": f"{who} restaurou {file_name} em “{title}”",
        "config_anexos": f"{who} mudou a pasta dos anexos",
        "demanda_movida": f"{who} moveu “{title}” para {COLUMN_LABELS.get(detail, detail)}",
        "demanda_excluida": f"{who} excluiu “{title}”",
        "presenca": f"{who} ficou: {detail}",
        "pessoa_criada": f"{who} cadastrou {name}",
        "cadastro_pedido": f"{detail} pediu cadastro no Hub",
        "cadastro_aprovado": f"{who} aprovou o cadastro de {name} ({detail})",
        "cadastro_recusado": f"{who} recusou o pedido de cadastro de {detail}",
        "pessoa_editada": f"{who} editou o cadastro de {name}",
        "pessoa_desativada": f"{who} desativou {name}",
        "pessoa_reativada": f"{who} reativou {name}",
        "entrou": f"{who} entrou no Hub",
        "pin_criado": f"{who} criou o próprio PIN",
        "pin_trocado": f"{who} trocou o próprio PIN",
        "pin_redefinido": f"{who} redefiniu o PIN de {name}",
        "pin_bloqueado": f"{name} ficou bloqueado por errar o PIN",
        "admin_definido": f"{name} virou administrador no primeiro acesso",
        "papel_alterado": f"{who} mudou o papel de {name} para {detail}",
        "config_tv": f"{who} mudou as configurações da TV",
        "config_paineis": f"{who} mudou as configurações dos painéis",
        "config_drive": f"{who} mudou o download da 8081 do Google Drive ({detail})",
        "config_phd": f"{who} mudou o PHD automático",
        "config_pombo": f"{who} mudou a pasta do histórico do Pombo",
        "painel_arquivo": f"{who} enviou a planilha “{detail}” dos painéis",
        "horas_lancado": f"{who} lançou o banco de horas de {detail}",
        "horas_corrigido": f"{who} corrigiu o banco de horas de {detail}",
        "horas_excluido": f"{who} apagou do banco de horas o dia {detail}",
        "horas_saldo": f"{who} definiu o saldo base do banco de horas de {name_of(ref_id)} ({detail})",
        "horas_jornada": f"{who} mudou a jornada do banco de horas ({detail})",
        "rotina_criada": f"{who} cadastrou a rotina “{detail}”",
        "aviso_teste": f"{who} testou o aviso da TV",
        "tv_pausa": f"{who} pausou a TV da sala em “{detail}”",
        "tv_retomada": f"{who} fez a TV da sala voltar a passar as telas",
        "tv_exportada": f"{who} exportou em PDF a tela “{detail}” da TV",
        "tv_modo": f"{who} pôs a TV da sala no modo “{detail}”",
        "tv_modo_automatico": f"{who} fez a TV da sala voltar ao modo automático",
        "modo_criado": f"{who} criou o modo da TV “{detail}”",
        "modo_editado": f"{who} editou o modo da TV “{detail}”",
        "modo_excluido": f"{who} apagou o modo da TV “{detail}”",
        "modo_regra_ligada": f"{who} ligou a regra automática do modo “{detail}”",
        "modo_regra_desligada": f"{who} desligou a regra automática do modo “{detail}”",
        "rotina_editada": f"{who} editou a rotina “{detail}”",
        "rotina_desativada": f"{who} desativou a rotina “{detail}”",
        "rotina_reativada": f"{who} reativou a rotina “{detail}”",
        "rotina_removida": f"{who} removeu a rotina “{detail}”",
        "rotina_demanda": f"{who} mexeu pela primeira vez hoje na rotina “{title}”",
        "pasta_marcada": f"{who} marcou a pasta {detail} em “{title}”",
        "pasta_desmarcada": f"{who} desmarcou a pasta {detail} em “{title}”",
        "admin_alterado": f"{who} {'tornou' if detail == 'sim' else 'tirou'} {name} {'administrador' if detail == 'sim' else 'de administrador'}",
        "compromisso_criado": f"{who} criou o compromisso “{title}”",
        "compromisso_editado": f"{who} editou o compromisso “{title}”",
        "compromisso_excluido": f"{who} apagou o compromisso “{title}”",
        "ausencia_marcada": f"{who} marcou ausência de {name_of(ref_id)} ({detail})",
        "ausencia_removida": f"{who} tirou a ausência de {name_of(ref_id)} de {detail}",
        "feriado_criado": f"{who} acrescentou o feriado {detail}",
        "feriado_ligado": f"{who} ligou o feriado {detail}",
        "feriado_desligado": f"{who} desligou o feriado {detail} (o dia volta a ser útil)",
        "feriado_removido": f"{who} removeu o feriado {detail}",
        "prioridade_criada": f"{who} acrescentou “{detail}” às prioridades do mês",
        "prioridade_feita": f"{who} marcou como feita a prioridade “{detail}”",
        "prioridade_pasta_feita": f"{who} marcou “{folder_title}” como feita {folder_text}",
        "prioridade_pasta_desfeita": f"{who} desmarcou “{folder_title}” {folder_text}",
        "pastas_alteradas": f"{who} mudou as pastas de {detail}",
        "prioridade_desfeita": f"{who} desmarcou a prioridade “{detail}”",
        "prioridade_removida": f"{who} removeu “{detail}” das prioridades do mês",
        "prioridades_padrao": f"{who} criou a lista padrão de prioridades de {month_label(detail) if is_month(detail) else detail}",
        # v5: rotinas do mês, trilha do dia e justificativas
        "categoria_criada": f"{who} criou a categoria “{detail}” das rotinas do mês",
        "categoria_editada": f"{who} mudou a categoria “{detail}” das rotinas do mês",
        "categoria_removida": f"{who} removeu a categoria “{detail}” das rotinas do mês",
        "rotina_mes_criada": f"{who} cadastrou a rotina do mês “{detail}”",
        "rotina_mes_editada": f"{who} mudou a rotina do mês “{detail}”",
        "rotina_mes_desativada": f"{who} desativou a rotina do mês “{detail}”",
        "rotina_mes_reativada": f"{who} reativou a rotina do mês “{detail}”",
        "rotina_mes_feita": f"{who} marcou a rotina do mês “{detail}” como feita",
        "rotina_mes_desfeita": f"{who} desmarcou a rotina do mês “{detail}”",
        "rotina_mes_justificada": f"{who} justificou a rotina do mês “{detail}”",
        "rotina_mes_justificativa_tirada": f"{who} tirou a justificativa da rotina do mês “{detail}”",
        "trilha_modelo": f"{who} criou a trilha do modelo para {name}",
        "trilha_copiada": f"{who} copiou uma trilha para {name}",
        "trilha_limpa": f"{who} tirou todos os blocos ({detail}) da trilha de {name}",
        "trilha_feito": f"{who} marcou como feito o bloco {detail} da trilha de {name}",
        "trilha_desfeito": f"{who} desmarcou o bloco {detail} da trilha de {name}",
        "trilha_justificada": f"{who} justificou o bloco {detail} da trilha de {name}",
        "trilha_justificativa_tirada": f"{who} tirou a justificativa do bloco {detail} da trilha de {name}",
    }.get(kind, f"{who}: {kind}")
