"""Servidor do Hub: a tela da TV e o app dos analistas."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..access import (ROLES, change_pin, create_pin, end_session, has_admin, reset_pin, session_end, session_person,
                      set_access, start_session, verify_pin)
from ..db import Database, events, first_event_day
from ..demands import (COLUMN_LABELS, COLUMNS, FOLDERS, RESERVED_TEXT, all_demands, board, can_see, create_demand,
                       delete_demand, find_demand, is_overdue, move_demand, tv_card, update_demand)
from ..people import (PALETTE, Person, ValidationError, add_person, deactivate_person, get_person, list_people,
                      update_person)
from ..gestor import DUE_FILTERS, can_open, filter_demands, team_summary
from ..presence import STATUSES, presence_board, set_status
from ..telas import MAX_SECONDS, MIN_SECONDS, PAGE_MAX, PAGE_MIN, rotation, save_screen_config, screen_config

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

    @app.get("/api/tv")
    def api_tv():
        now = clock()
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
            **rotation(db, now),
        }

    # ---------- app do analista ----------

    templates.env.globals.update(
        COLUMN_LABELS=COLUMN_LABELS, FOLDERS=FOLDERS, STATUSES=STATUSES, is_overdue=is_overdue,
        can_see=can_see, RESERVED_TEXT=RESERVED_TEXT,
    )

    templates.env.globals["ROLES"] = ROLES

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
        return {
            "status": status,
            "columns": board(db, now, owner_id=None if show_all else user.id),
            "owners": {p.id: p for p in list_people(db, active_only=False)},
            "today": now.date(),
            "show_all": show_all,
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
    def quadro(request: Request, todas: int = 0):
        user = me(request)
        if user is None:
            return to_login()
        return page(request, "quadro.html", user, **board_context(user, bool(todas)))

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
        return page(request, "demanda.html", user, status_code, v=values, people=people, **ctx)

    def parse_demand(form) -> tuple[dict, dict]:
        values = {
            "title": form.get("title", ""), "owner_id": form.get("owner_id", ""), "folder": form.get("folder", ""),
            "requested_by": form.get("requested_by", ""), "due": form.get("due", ""), "reserved": "reserved" in form,
        }
        try:
            due = date.fromisoformat(values["due"]) if values["due"] else None
        except ValueError:
            raise ValidationError("Data inválida.")
        owner = int(values["owner_id"]) if values["owner_id"].isdigit() else 0
        fields = dict(title=values["title"], owner_id=owner, folder=values["folder"] or None,
                      requested_by=values["requested_by"] or None, due=due, reserved=values["reserved"])
        return values, fields

    @app.get("/demandas/nova", response_class=HTMLResponse)
    def demanda_nova(request: Request):
        user = me(request)
        if user is None:
            return to_login()
        return demand_form(request, user, {"id": "", "title": "", "owner_id": str(user.id), "folder": "",
                                           "requested_by": "", "due": "", "reserved": False})

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
            create_demand(db, clock(), user.id, **fields)
        except ValidationError as exc:
            values.update({k: form.get(k, "") for k in ("title", "owner_id", "folder", "requested_by", "due")},
                          reserved="reserved" in form)
            return demand_form(request, user, values, 422, error=str(exc))
        return RedirectResponse("/", status_code=303)

    @app.get("/demandas/{demand_id}", response_class=HTMLResponse)
    def demanda_editar(request: Request, demand_id: int):
        user = me(request)
        if user is None:
            return to_login()
        d = find_demand(db, demand_id)
        if d is None:
            return RedirectResponse("/", status_code=303)
        if not can_see(d, user):
            return forbidden(request, user, "Esta demanda é reservada. Só o dono, quem criou, o gestor e os administradores podem abrir.")
        return demand_form(request, user, {
            "id": d.id, "title": d.title, "owner_id": str(d.owner_id), "folder": d.folder or "",
            "requested_by": d.requested_by or "", "due": d.due.isoformat() if d.due else "", "reserved": d.reserved,
        })

    def hidden_from(user: Person, demand_id: int) -> bool:
        d = find_demand(db, demand_id)
        return d is not None and not can_see(d, user)

    def reserved_forbidden(request: Request, user: Person) -> HTMLResponse:
        return forbidden(request, user, "Esta demanda é reservada. Só o dono, quem criou, o gestor e os administradores podem mexer nela.")

    @app.post("/demandas/{demand_id}")
    async def demanda_salvar(request: Request, demand_id: int):
        user = me(request)
        if user is None:
            return to_login()
        if hidden_from(user, demand_id):
            return reserved_forbidden(request, user)
        form = await request.form()
        values = {"id": demand_id}
        try:
            parsed, fields = parse_demand(form)
            values.update(parsed)
            update_demand(db, clock(), user.id, demand_id, **fields)
        except ValidationError as exc:
            values.update({k: form.get(k, "") for k in ("title", "owner_id", "folder", "requested_by", "due")},
                          reserved="reserved" in form)
            return demand_form(request, user, values, 422, error=str(exc))
        return RedirectResponse("/", status_code=303)

    @app.post("/demandas/{demand_id}/mover")
    def demanda_mover(request: Request, demand_id: int, column: str = Form(...)):
        user = me(request)
        if user is None:
            return to_login()
        if hidden_from(user, demand_id):
            return reserved_forbidden(request, user)
        try:
            move_demand(db, clock(), user.id, demand_id, column)
        except ValidationError:
            pass  # outro PC já excluiu: o quadro atualizado mostra a verdade
        return RedirectResponse(request.headers.get("referer") or "/", status_code=303)

    @app.post("/demandas/{demand_id}/excluir")
    def demanda_excluir(request: Request, demand_id: int):
        user = me(request)
        if user is None:
            return to_login()
        if hidden_from(user, demand_id):
            return reserved_forbidden(request, user)
        try:
            delete_demand(db, clock(), user.id, demand_id)
        except ValidationError:
            pass
        return RedirectResponse("/", status_code=303)

    # ---------- configurações (administrador) ----------

    def config_page(request: Request, user: Person, status_code: int = 200, **ctx) -> HTMLResponse:
        return page(request, "configuracoes.html", user, status_code, config=screen_config(db),
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
    title = ""
    if subject.startswith("demanda:"):
        d = demands.get(ref_id)
        title = detail if d is None else d.title if can_see(d, viewer) else RESERVED_TEXT
    name = people[ref_id].name if subject.startswith("pessoa:") and ref_id in people else detail
    return {
        "demanda_criada": f"{who} criou “{title}”",
        "demanda_editada": f"{who} editou “{title}”",
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
        "admin_alterado": f"{who} {'tornou' if detail == 'sim' else 'tirou'} {name} {'administrador' if detail == 'sim' else 'de administrador'}",
    }.get(kind, f"{who}: {kind}")
