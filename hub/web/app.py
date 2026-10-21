"""Servidor do Hub: a tela da TV e o app dos analistas."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlencode, urlsplit

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..access import (ROLES, change_pin, create_pin, end_session, has_admin, reset_pin, session_end, session_person,
                      set_access, start_session, verify_pin)
from ..db import Database, events, first_event_day
from ..demands import (CHANGES_SEP, COLUMN_LABELS, COLUMNS, FOLDERS, MAX_DETAILS, RESERVED_TEXT, all_demands, board,
                       can_remove_file, can_see, create_demand, delete_demand, ensure_demand, find_card, find_demand,
                       is_overdue, move_demand, search_demands, toggle_folder, touch_demand, tv_card, update_demand)
from .. import anexos
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
                       save_routine, set_routine_active, start_test_alert, tv_alerts, weekdays_label)
from ..prioridades import (DEFAULT_LIST, add_priority, can_remove, create_default_list, is_late, is_month, last_day,
                           list_month, mark_done, month_label, month_of, parse_due_day, past_months, remove_priority,
                           undo_done)
from ..telas import MAX_SECONDS, MIN_SECONDS, PAGE_MAX, PAGE_MIN, rotation, save_screen_config, screen_config
from .. import tvcontrole

HERE = Path(__file__).parent
COOKIE = "hub_sessao"


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

    @app.get("/api/tv")
    def api_tv(tela: str = "", pausada: str = "", espiar: str = ""):
        now = clock()
        if tela and not espiar:  # a aba "no meu PC" não conta como a TV da sala
            seen.update(tela, pausada == "1", now)
        owners = {p.id: p for p in list_people(db, active_only=False)}
        columns = board(db, now)
        return {
            "now": now.isoformat(timespec="seconds"),
            "people": [
                {"name": p.name, "initials": p.initials, "color": p.color, "status": status,
                 "since": since.strftime("%H:%M")}
                for p, status, since in presence_board(db, now)
            ],
            "columns": {c: [tv_card(d, owners[d.owner_id], now.date()) for d in columns[c]] for c in COLUMNS},
            "counts": {c: len(columns[c]) for c in COLUMNS},
            # aviso fixo em todas as telas da rotação
            "overdue": sum(is_overdue(d, now.date()) for d in columns["todo"] + columns["doing"]),
            # aviso sonoro de cada rotina de hoje: a TV toca uma vez, quando chega o horário
            "avisos": tv_alerts(db, now),
            # pausa pelo app (fase 10) e quanto dura a pausa feita com um clique na própria TV
            "pausa": tvcontrole.tv_payload(db, now, owners),
            "pausa_minutos": tvcontrole.DEFAULT_MINUTES,
            **rotation(db, now),
        }

    # ---------- TV da sala: pausar, trocar de tela e ver uma tela no meu PC (fase 10) ----------

    def tv_room_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        now = clock()
        pause = tvcontrole.current_pause(db, now)
        who = get_person(db, pause["por"]) if pause and pause.get("por") else None
        return page(request, "tv-da-sala.html", user, status_code, seen=seen.get(now), pause=pause,
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

    # ---------- app do analista ----------

    templates.env.globals.update(
        COLUMN_LABELS=COLUMN_LABELS, FOLDERS=FOLDERS, STATUSES=STATUSES, is_overdue=is_overdue,
        can_see=can_see, RESERVED_TEXT=RESERVED_TEXT,
    )

    templates.env.globals.update(ROLES=ROLES, WEEKDAY_LABELS=WEEKDAY_LABELS, weekdays_label=weekdays_label,
                                 can_manage_routines=can_manage)

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
        columns = everything if show_all else {c: [d for d in everything[c] if d.owner_id == user.id] for c in COLUMNS}
        # rotinas da equipe com pastas: cada um marca a sua, mesmo sem ser o responsável pelo cartão
        shared = [] if show_all else [d for c in ("todo", "doing") for d in everything[c]
                                      if d.routine and d.routine.folders and d.owner_id != user.id and can_see(d, user)]
        return {
            "status": status,
            "columns": columns,
            "shared": shared,
            "owners": {p.id: p for p in list_people(db, active_only=False)},
            "today": now.date(),
            "show_all": show_all,
            "clips": anexos.counts(db, "demanda"),  # 📎 no cartão (só no app, nunca na TV)
        }

    def forbidden(request: Request, user: Person, message: str = "") -> HTMLResponse:
        return page(request, "sem-permissao.html", user, 403, message=message)

    @app.get("/entrar", response_class=HTMLResponse)
    def entrar(request: Request):
        return page(request, "entrar.html", None, people=list_people(db))

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
        now = clock()
        try:
            if person.has_pin:
                verify_pin(db, now, person_id, pin)
            else:
                create_pin(db, now, person_id, pin, confirmar)
        except ValidationError as exc:
            return pin_page(request, get_person(db, person_id), 422, str(exc))
        token = start_session(db, now, person_id)
        r = RedirectResponse("/", status_code=303)
        seconds = int((session_end(now) - now).total_seconds())
        r.set_cookie(COOKIE, token, max_age=max(seconds, 60), httponly=True, samesite="lax")
        return r

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

    @app.get("/", response_class=HTMLResponse)
    def quadro(request: Request, todas: int = 0, concluida: str = ""):
        user = me(request)
        if user is None:
            return to_login()
        done = find_demand(db, int(concluida)) if concluida.isdigit() else None
        done = done if done is not None and done.column == "done" and can_see(done, user) else None
        return page(request, "quadro.html", user, concluida=done, **board_context(user, bool(todas)))

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
        return False

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
                    "owner_id": str(user.id), "folders": [], "waits_for": []}
        return {"id": r.id, "name": r.name, "weekdays": list(r.weekdays), "starts_at": r.starts_at,
                "deadline": r.deadline or "", "owner_id": str(r.owner_id), "folders": list(r.folders),
                "waits_for": list(r.waits_for)}

    def routines_page(request: Request, user: Person, status_code: int = 200, v: dict | None = None,
                      **ctx) -> HTMLResponse:
        people = list_people(db)
        routines = list_routines(db)
        v = v or routine_values(user=user)
        # responsável desativado continua na lista desta rotina, como no formulário de demanda
        owner = get_person(db, int(v["owner_id"])) if str(v.get("owner_id", "")).isdigit() else None
        if owner and not owner.active:
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
        return {"name": str(form.get("name", "")), "weekdays": ints("weekdays"),
                "starts_at": str(form.get("starts_at", "")), "deadline": str(form.get("deadline", "")),
                "owner_id": int(owner) if owner.isdigit() else 0, "folders": [str(f) for f in form.getlist("folders")],
                "waits_for": ints("waits_for")}

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
            v = {**fields, "id": routine_id or "", "owner_id": str(fields["owner_id"])}
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
        if r is None:
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

    # ---------- prioridades do mês ----------

    def priorities_page(request: Request, user: Person, month: str = "", status_code: int = 200, **ctx) -> HTMLResponse:
        now = clock()
        current = month_of(now)
        # um mês anterior abre só para consulta; mês inválido ou futuro volta para o atual
        month = month if is_month(month) and month <= current else current
        items = list_month(db, month)
        ctx.setdefault("v", {"title": "", "folder": "", "prazo": ""})
        return page(request, "prioridades.html", user, status_code, month=month, current=current, items=items,
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
    def prioridades_acrescentar(request: Request, title: str = Form(""), folder: str = Form(""), prazo: str = Form("")):
        user = me(request)
        if user is None:
            return to_login()
        try:
            add_priority(db, clock(), user, title, folder or None, parse_due_day(prazo))
        except ValidationError as exc:
            return priorities_page(request, user, status_code=422, error=str(exc),
                                   v={"title": title, "folder": folder, "prazo": prazo})
        return back_to_priorities()

    @app.post("/prioridades/padrao")
    def prioridades_padrao(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        create_default_list(db, clock(), user)  # o mês já tem lista (outro PC criou antes): não muda nada
        return back_to_priorities()

    @app.post("/prioridades/{item_id}/{action}")
    def prioridades_item(request: Request, item_id: int, action: str):
        user = me(request)
        if user is None:
            return to_login()
        actions = {"feita": mark_done, "desfazer": undo_done, "remover": remove_priority}
        if action not in actions:
            return Response(status_code=404)
        try:
            actions[action](db, clock(), user, item_id)
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
                    paineis=panel_config(db), pombo=pombo_config(db),
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
        return page(request, "paineis.html", user, status_code, snap=snap, now=now,
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
                    own=person.id == user.id, default_day=default_day, journey=horas.journey(db), h=horas, **ctx)

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
                    journey=horas.journey(db), h=horas, people=list_people(db), **ctx)

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
    def horas_jornada(request: Request, semana: str = Form(""), sabado: str = Form("")):
        user, stop = hours_manager_only(request)
        if stop:
            return stop
        try:
            horas.save_journey(db, clock(), user, semana, sabado)
        except ValidationError as exc:
            return team_hours_page(request, user, 422, error=str(exc))
        return team_hours_page(request, user, ok="Jornada salva.")

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
        lines = [(datetime.fromisoformat(r["at"]), describe(r, people, demands, user)) for r in rows]
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
        return page(request, "pessoas.html", user, status_code, people=list_people(db), palette=PALETTE, **ctx)

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

    @app.post("/pessoas/{person_id}/pin")
    def pessoas_redefinir_pin(request: Request, person_id: int):
        user, stop = admin_only(request)
        if stop:
            return stop
        reset_pin(db, clock(), user, person_id)
        return RedirectResponse("/pessoas", status_code=303)

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


def describe(row, people: dict, demands: dict, viewer: Person) -> str:
    """Uma linha de histórico em português. Demanda reservada só mostra o título a quem pode vê-lo."""
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
    file_name = f"“{detail}”" if visible else "um arquivo"  # nome de arquivo de reservada também é escondido
    name = people[ref_id].name if subject.startswith("pessoa:") and ref_id in people else detail
    name_of = lambda pid: people[pid].name if pid in people else "alguém"
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
        "rotina_editada": f"{who} editou a rotina “{detail}”",
        "rotina_desativada": f"{who} desativou a rotina “{detail}”",
        "rotina_reativada": f"{who} reativou a rotina “{detail}”",
        "rotina_demanda": f"{who} mexeu pela primeira vez hoje na rotina “{title}”",
        "pasta_marcada": f"{who} marcou a pasta {detail} em “{title}”",
        "pasta_desmarcada": f"{who} desmarcou a pasta {detail} em “{title}”",
        "admin_alterado": f"{who} {'tornou' if detail == 'sim' else 'tirou'} {name} {'administrador' if detail == 'sim' else 'de administrador'}",
        "prioridade_criada": f"{who} acrescentou “{detail}” às prioridades do mês",
        "prioridade_feita": f"{who} marcou como feita a prioridade “{detail}”",
        "prioridade_desfeita": f"{who} desmarcou a prioridade “{detail}”",
        "prioridade_removida": f"{who} removeu “{detail}” das prioridades do mês",
        "prioridades_padrao": f"{who} criou a lista padrão de prioridades de {month_label(detail) if is_month(detail) else detail}",
    }.get(kind, f"{who}: {kind}")
