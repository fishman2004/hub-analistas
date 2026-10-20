"""Painéis de dados (fase 5): metas de venda e positivação lidas das planilhas que o time exporta.

As 5 planilhas ficam numa pasta só delas (a "pasta dos painéis"), com nomes fixos. O Hub lê,
calcula meta x realizado por pasta (A a G e o total) e manda para a TV **só porcentagens**:
regra do gestor, porque muita gente passa pela sala. Valores em reais, quantidades e nomes de
vendedores ou clientes não saem deste módulo.

Leitura com cache: só relê um arquivo quando a data de modificação ou o tamanho mudam. Arquivo
ausente ou quebrado tira da rotação só as telas que dependem dele e vai para o hub.log.
O contrato de cada arquivo está em docs/paineis.md.
"""

import calendar
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from .db import Database, log_event
from .people import Person, ValidationError
from .planilhas import EXTENSIONS, PlanilhaError, code, day, normalize, number, read_rows

log = logging.getLogger("hub.paineis")


@dataclass(frozen=True)
class Arquivo:
    key: str
    base: str  # nome do arquivo sem a extensão
    label: str
    columns: dict[str, str]  # {chave interna: nome da coluna na planilha}


FILES = (
    Arquivo("metas", "(BASE) - Metas Polybalas - Financeiro e Positivações", "Metas de financeiro e positivação",
            {"vendedor": "ID VENDEDOR", "fornecedor": "ID FORN", "meta_fin": "META FINANCEIRA",
             "meta_pos": "META POSITIVAÇÃO"}),
    Arquivo("focos", "(BASE) - Produtos Focos (KPI's)", "Produtos foco",
            {"produto": "ID PRODUTO", "foco": "PRODUTO FOCO"}),
    Arquivo("fornecedores", "(BASE) - Fornecedores Polybalas", "Fornecedores e pastas",
            {"fornecedor": "ID FORNECEDOR", "nome": "FORNECEDOR", "grupo": "FORNECEDOR II", "pasta": "PASTA"}),
    Arquivo("metas_kpi", "(BASE) - Metas Polybalas - KPI's e Produtos Focos", "Metas dos produtos foco",
            {"vendedor": "ID", "foco": "PRODUTO FOCO", "classe": "CLASSIFICACAO", "meta": "META",
             "meta2": "META II"}),
    Arquivo("vendas", "(DADOS) - 8081 - Vendas", "Vendas (8081)",
            {"data": "DATA PEDIDO", "cliente": "ID CLIENTE",
             "produto": "ID PRODUTO", "fornecedor": "ID FORNECEDOR", "valor": "VALOR"}),
)
FILES_BY_KEY = {f.key: f for f in FILES}

DEFAULT_FOLDER_NAME = "Painéis"
SETTING_FOLDER = "paineis.pasta"
SETTING_STALE = "paineis.velho.horas"
STALE_DEFAULT, STALE_MIN, STALE_MAX = 24, 1, 168
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

TIERS = ((100, "bom"), (80, "atencao"), (70, "alerta"))  # abaixo de 70%: "critico"
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
         "novembro", "dezembro"]
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
TOTAL = "T"


# ---------- pasta e configurações ----------

def _setting(db: Database, key: str) -> str | None:
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def default_folder(db: Database) -> Path:
    return db.path.parent / DEFAULT_FOLDER_NAME


def panel_folder(db: Database) -> Path:
    """A pasta escolhida em Configurações ou, sem escolha, "Painéis" ao lado do banco do Hub."""
    custom = _setting(db, SETTING_FOLDER)
    if custom:
        return Path(custom)
    folder = default_folder(db)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stale_hours(db: Database) -> int:
    raw = _setting(db, SETTING_STALE)
    return int(raw) if raw and raw.isdigit() else STALE_DEFAULT


def panel_config(db: Database) -> dict:
    return {"folder": _setting(db, SETTING_FOLDER) or "", "default_folder": str(default_folder(db)),
            "stale_hours": stale_hours(db)}


def save_panel_config(db: Database, now: datetime, actor: Person, folder: str, hours: str) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    folder = folder.strip().strip('"')
    if folder and not Path(folder).is_dir():
        raise ValidationError(f"Não encontrei a pasta {folder}. Confira o caminho (ou deixe em branco para usar a padrão).")
    if not hours.isdigit() or not STALE_MIN <= int(hours) <= STALE_MAX:
        raise ValidationError(f"Aviso de dados velhos: use de {STALE_MIN} a {STALE_MAX} horas.")
    with db.connect() as conn:
        if folder:
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (SETTING_FOLDER, folder))
        else:
            conn.execute("DELETE FROM settings WHERE key = ?", (SETTING_FOLDER,))
        conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (SETTING_STALE, str(int(hours))))
        log_event(conn, now, actor.id, "config_paineis", "config:paineis", "")


def find_file(folder: Path, base: str) -> Path | None:
    """O arquivo com esse nome em qualquer formato aceito; havendo mais de um, o mais novo."""
    found = [folder / (base + ext) for ext in EXTENSIONS if (folder / (base + ext)).is_file()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def save_upload(db: Database, now: datetime, actor: Person, key: str, filename: str, data: BinaryIO) -> Path:
    """Envio pelo navegador: grava na pasta com o nome certo, trocando o arquivo anterior de uma vez."""
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    target = FILES_BY_KEY.get(key)
    if target is None:
        raise ValidationError("Arquivo desconhecido.")
    ext = Path(filename or "").suffix.lower()
    if ext not in EXTENSIONS:
        raise ValidationError(f"Envie a planilha em {', '.join(EXTENSIONS)}.")
    folder = panel_folder(db)
    partial = folder / (target.base + ".enviando")
    size = 0
    try:
        with open(partial, "wb") as out:
            while chunk := data.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValidationError("Arquivo grande demais (máximo 200 MB).")
                out.write(chunk)
        final = folder / (target.base + ext)
        os.replace(partial, final)  # a TV nunca vê o arquivo pela metade
    finally:
        partial.unlink(missing_ok=True)
    for other in EXTENSIONS:
        if other != ext:
            (folder / (target.base + other)).unlink(missing_ok=True)
    with db.connect() as conn:
        log_event(conn, now, actor.id, "painel_arquivo", f"painel:{key}", target.label)
    return final


# ---------- leitura de cada arquivo ----------

def _parse(key: str, path: Path):
    rows = read_rows(path, FILES_BY_KEY[key].columns)
    if key == "fornecedores":
        out = {}
        for r in rows:
            pasta = str(r["pasta"] or "").strip().upper()
            supplier = code(r["fornecedor"])
            if supplier and pasta:
                out[supplier] = (normalize(r["grupo"] or r["nome"]), pasta)
        return out
    if key == "metas":
        return [(code(r["vendedor"]), code(r["fornecedor"]), number(r["meta_fin"]), number(r["meta_pos"]))
                for r in rows]
    if key == "focos":
        return {code(r["produto"]): str(r["foco"]).strip() for r in rows if r["foco"]}
    if key == "metas_kpi":
        return [(code(r["vendedor"]), str(r["foco"] or "").strip(), str(r["classe"] or "").strip(),
                 number(r["meta"]), number(r["meta2"])) for r in rows if r["foco"]]
    # vendas: só o que o cálculo usa. Todas as posições (L, B, M, F) contam; cancelado nem vem na extração
    out = []
    for r in rows:
        if r["data"] in (None, ""):
            continue  # linha de total sem data no fim da exportação
        out.append(Venda(code(r["cliente"]), code(r["produto"]), code(r["fornecedor"]),
                         day(r["data"]), number(r["valor"])))
    if not out:
        raise PlanilhaError("Nenhuma venda no arquivo.")
    return out


@dataclass(frozen=True)
class Venda:
    cliente: str
    produto: str
    fornecedor: str
    dia: date
    valor: float


# ---------- cálculo ----------

def workdays(year: int, month: int) -> list[date]:
    """Dias de venda do mês: segunda a sábado (sábado é dia de venda até meio-dia). Feriados não são descontados."""
    last = calendar.monthrange(year, month)[1]
    return [d for d in (date(year, month, n) for n in range(1, last + 1)) if is_sales_day(d)]


def is_sales_day(d: date) -> bool:
    return d.weekday() < 6  # domingo não tem meta


def pct(real: float, meta: float) -> int | None:
    return round(real / meta * 100) if meta > 0 else None


def tier(value: int | None) -> str:
    if value is None:
        return "sem-meta"
    return next((name for limit, name in TIERS if value >= limit), "critico")


def _pace_tier(real_pct: int | None, expected: int) -> str:
    # no mês, a cor diz se o ritmo está bom: realizado comparado ao esperado até o último dia com venda
    if real_pct is None:
        return "sem-meta"
    return tier(round(real_pct / expected * 100) if expected else real_pct)


def _month(vendas: list[Venda]) -> tuple[date, list[Venda], list[date], int]:
    """O mês da venda mais recente: último dia, vendas do mês, dias de venda e % esperado até o último dia."""
    last = max(v.dia for v in vendas)
    month = [v for v in vendas if (v.dia.year, v.dia.month) == (last.year, last.month)]
    days = workdays(last.year, last.month)
    return last, month, days, round(sum(d <= last for d in days) / len(days) * 100)


def compute_metas(fornecedores: dict, metas: list, vendas: list[Venda]) -> dict:
    """Meta x realizado por pasta e no total, no mês da venda mais recente do arquivo.

    Positivação é a contagem distinta de clientes, como a empresa conta: o cliente que comprou de
    2 fornecedores da pasta é 1 positivação para a pasta e 1 para o total, sem acumular. No dia, contam
    os clientes positivados pela primeira vez no mês naquele dia (na pasta ou no total).
    """
    last, month, days, expected = _month(vendas)
    sales_day = is_sales_day(last)

    meta_fin: dict[str, float] = {}
    meta_pos: dict[str, float] = {}
    no_folder = 0
    for _, supplier, fin, pos in metas:
        if supplier not in fornecedores:
            no_folder += 1
            continue
        pasta = fornecedores[supplier][1]
        meta_fin[pasta] = meta_fin.get(pasta, 0) + fin
        meta_pos[pasta] = meta_pos.get(pasta, 0) + pos

    real_fin: dict[str, float] = {}
    day_fin: dict[str, float] = {}
    first_buy: dict[tuple, date] = {}  # (pasta ou T, cliente) -> primeiro dia de compra no mês
    unknown = set()
    daily_total = [0.0] * (calendar.monthrange(last.year, last.month)[1] + 1)
    for v in month:
        info = fornecedores.get(v.fornecedor)
        if info is None:
            unknown.add(v.fornecedor)
            continue
        pasta = info[1]
        real_fin[pasta] = real_fin.get(pasta, 0) + v.valor
        daily_total[v.dia.day] += v.valor
        if v.dia == last:
            day_fin[pasta] = day_fin.get(pasta, 0) + v.valor
        for level in (pasta, TOTAL):
            key = (level, v.cliente)
            if key not in first_buy or v.dia < first_buy[key]:
                first_buy[key] = v.dia

    pastas = sorted(set(meta_fin) | set(real_fin))

    def totals(values: dict) -> dict:
        return {**values, TOTAL: sum(values.values())}

    meta_fin, meta_pos, real_fin, day_fin = totals(meta_fin), totals(meta_pos), totals(real_fin), totals(day_fin)
    real_pos: dict[str, int] = {}
    day_pos: dict[str, int] = {}
    for (level, _), first in first_buy.items():  # o total tem a contagem própria: não é a soma das pastas
        real_pos[level] = real_pos.get(level, 0) + 1
        day_pos[level] = day_pos.get(level, 0) + (first == last)
    share = 1 / len(days)

    def month_cards(real: dict, meta: dict) -> list[dict]:
        cards = []
        for p in pastas + [TOTAL]:
            value = pct(real.get(p, 0), meta.get(p, 0))
            cards.append({"pasta": p, "pct": value, "tier": _pace_tier(value, expected)})
        return cards

    def day_bars(real: dict, meta: dict) -> list[dict]:
        bars = []
        for p in [TOTAL] + pastas:
            value = pct(real.get(p, 0), meta.get(p, 0) * share) if sales_day else None
            bars.append({"pasta": p, "pct": value, "tier": tier(value)})
        return bars

    evolution = []
    accumulated = 0.0
    passed = 0
    for n in range(1, len(daily_total)):
        d = date(last.year, last.month, n)
        passed += is_sales_day(d)
        accumulated += daily_total[n]
        target = round(passed / len(days) * 100)
        real = pct(accumulated, meta_fin[TOTAL]) if d <= last else None
        evolution.append({"dia": n, "util": is_sales_day(d), "meta": target, "real": real,
                          "tier": _pace_tier(real, target) if real is not None else "futuro"})

    warnings = []
    if no_folder:
        warnings.append(f"{no_folder} linha(s) de meta com fornecedor que não está na planilha de fornecedores.")
    if unknown:
        warnings.append(f"{len(unknown)} fornecedor(es) com venda que não estão na planilha de fornecedores.")
    return {
        "year": last.year, "month": last.month, "last_day": last, "expected": expected, "is_workday": sales_day,
        "financeiro": {"mes": month_cards(real_fin, meta_fin), "dia": day_bars(day_fin, meta_fin)},
        "positivacao": {"mes": month_cards(real_pos, meta_pos), "dia": day_bars(day_pos, meta_pos)},
        "evolucao": evolution, "warnings": warnings,
    }


def compute_focos(focos: dict, metas_kpi: list, vendas: list[Venda]) -> dict:
    """Produtos foco: META é positivação (clientes distintos que compraram algum produto do foco)
    e META II é financeiro (soma de VALOR dos produtos do foco)."""
    last, month, _, expected = _month(vendas)
    goals: dict[str, dict] = {}
    for _, name, klass, meta, meta2 in metas_kpi:
        g = goals.setdefault(normalize(name), {"nome": name, "classe": klass, "meta": 0.0, "meta2": 0.0})
        g["meta"] += meta
        g["meta2"] += meta2
    clients: dict[str, set] = {}
    value: dict[str, float] = {}
    for v in month:
        if v.produto in focos:
            key = normalize(focos[v.produto])
            clients.setdefault(key, set()).add(v.cliente)
            value[key] = value.get(key, 0) + v.valor
    known = {normalize(f) for f in focos.values()}
    rows = []
    for key, g in goals.items():
        if g["meta"] <= 0 and g["meta2"] <= 0:
            continue
        pos = pct(len(clients.get(key, ())), g["meta"])
        fin = pct(value.get(key, 0), g["meta2"])
        rows.append({"nome": g["nome"], "classe": g["classe"],
                     "pos": pos, "pos_tier": _pace_tier(pos, expected),
                     "fin": fin, "fin_tier": _pace_tier(fin, expected)})
    rows.sort(key=lambda r: -(r["pos"] if r["pos"] is not None else r["fin"] or 0))
    missing = [g["nome"] for k, g in goals.items() if k not in known]
    warnings = [f"{len(missing)} produto(s) foco sem nenhum produto na planilha de produtos foco."] if missing else []
    return {"year": last.year, "month": last.month, "last_day": last, "expected": expected, "focos": rows,
            "warnings": warnings}


# ---------- cache e situação dos arquivos ----------

@dataclass
class FileStatus:
    key: str
    label: str
    base: str
    path: Path | None = None
    modified: datetime | None = None
    rows: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.path is not None and not self.error


@dataclass
class Snapshot:
    folder: Path
    files: list[FileStatus]
    metas: dict | None = None
    focos: dict | None = None
    errors: list[str] = field(default_factory=list)

    def status(self, key: str) -> FileStatus:
        return next(f for f in self.files if f.key == key)

    def modified(self, *keys: str) -> datetime | None:
        dates = [self.status(k).modified for k in keys if self.status(k).modified]
        return max(dates) if dates else None


METAS_NEEDS = ("fornecedores", "metas", "vendas")
FOCOS_NEEDS = ("focos", "metas_kpi", "vendas")
BACKGROUND = True  # no Hub de verdade, a leitura roda numa linha separada; os testes desligam


class PanelStore:
    def __init__(self, db: Database, background: bool | None = None) -> None:
        self.db = db
        self.background = BACKGROUND if background is None else background
        self._lock = threading.Lock()  # protege só a troca do resultado: a TV nunca espera a leitura
        self._work_lock = threading.Lock()
        self._signature = None
        self._running = None
        self._snapshot: Snapshot | None = None
        self._parsed: dict[str, tuple] = {}  # {chave: (assinatura do arquivo, dados ou None, erro, linhas)}

    def _current_signature(self):
        folder = panel_folder(self.db)
        files = []
        for f in FILES:
            try:
                path = find_file(folder, f.base) if folder.is_dir() else None
                st = path.stat() if path else None
            except OSError:  # pasta de rede fora do ar
                path, st = None, None
            files.append((f.key, str(path) if path else None, st.st_mtime_ns if st else None,
                          st.st_size if st else None))
        return folder, tuple(files)

    def get(self, wait: bool = False) -> Snapshot | None:
        """A última leitura. Se algum arquivo mudou, relê: em segundo plano para a TV (que não pode
        esperar) ou na hora com wait=True (a página dos painéis, que mostra a situação de agora)."""
        folder, signature = self._current_signature()
        with self._lock:
            if signature == self._signature:
                return self._snapshot
            if wait or not self.background:
                with self._work_lock:
                    self._publish(self._refresh(folder, signature), signature)
                return self._snapshot
            if self._running != signature:
                self._running = signature
                threading.Thread(target=self._refresh_locked, args=(folder, signature), daemon=True,
                                 name="paineis").start()
            return self._snapshot  # enquanto lê, a TV continua com a leitura anterior

    def _refresh_locked(self, folder, signature) -> None:
        with self._work_lock:
            snap = self._refresh(folder, signature)
        with self._lock:
            self._publish(snap, signature)

    def _publish(self, snap: Snapshot, signature) -> None:
        self._snapshot, self._signature, self._running = snap, signature, None

    def _refresh(self, folder: Path, signature) -> Snapshot:
        files, data = [], {}
        for f, (key, path, mtime_ns, size) in zip(FILES, signature):
            status = FileStatus(f.key, f.label, f.base)
            files.append(status)
            if path is None:
                status.error = "Arquivo não encontrado na pasta." if folder.is_dir() else "Não consegui abrir a pasta."
                self._parsed.pop(key, None)
                continue
            status.path = Path(path)
            status.modified = datetime.fromtimestamp(mtime_ns / 1e9)
            file_sig = (path, mtime_ns, size)
            cached = self._parsed.get(key)
            if cached is None or cached[0] != file_sig:
                try:
                    parsed = _parse(key, Path(path))
                    cached = (file_sig, parsed, "", len(parsed))
                except (PlanilhaError, OSError) as exc:
                    message = str(exc) if isinstance(exc, PlanilhaError) else "Não consegui ler o arquivo (está aberto ou salvando?)."
                    cached = (file_sig, None, message, 0)
                    log.warning("painel: %s: %s", Path(path).name, message)
                except Exception:
                    log.exception("painel: erro inesperado ao ler %s", Path(path).name)
                    cached = (file_sig, None, "Erro inesperado ao ler (detalhes no hub.log).", 0)
                self._parsed[key] = cached
            _, data[key], status.error, status.rows = cached
        snap = Snapshot(folder, files)
        if all(data.get(k) is not None for k in METAS_NEEDS):
            snap.metas = self._safe(compute_metas, data["fornecedores"], data["metas"], data["vendas"], snap)
        if all(data.get(k) is not None for k in FOCOS_NEEDS):
            snap.focos = self._safe(compute_focos, data["focos"], data["metas_kpi"], data["vendas"], snap)
        return snap

    @staticmethod
    def _safe(fn, *args):
        *inputs, snap = args
        try:
            return fn(*inputs)
        except Exception:
            log.exception("painel: erro no cálculo (%s)", fn.__name__)
            snap.errors.append("Erro no cálculo dos painéis (detalhes no hub.log).")
            return None


_stores: dict[str, PanelStore] = {}
_stores_lock = threading.Lock()


def store_for(db: Database) -> PanelStore:
    with _stores_lock:
        key = str(db.path.resolve())
        if key not in _stores:
            _stores[key] = PanelStore(db)
        return _stores[key]


# ---------- o que vai para a TV (só porcentagens) ----------

def _when(moment: datetime, now: datetime) -> str:
    return f"{moment:%H:%M}" if moment.date() == now.date() else f"{moment:%d/%m} às {moment:%H:%M}"


def _header(db: Database, snap: Snapshot, section: dict, keys: tuple, now: datetime) -> dict:
    modified = snap.modified(*keys)
    stale = modified is not None and now - modified > timedelta(hours=stale_hours(db))
    last = section["last_day"]
    return {"mes": f"{MESES[section['month'] - 1].capitalize()} de {section['year']}",
            "ate": f"{last:%d/%m}", "dia_semana": DIAS[last.weekday()],
            "atualizado": _when(modified, now) if modified else "", "velho": stale,
            "esperado": section["expected"]}


def tv_metas_mes(db: Database, now: datetime) -> dict | None:
    snap = store_for(db).get()
    if snap is None or snap.metas is None:
        return None
    m = snap.metas
    return {**_header(db, snap, m, METAS_NEEDS, now), "evolucao": m["evolucao"],
            "financeiro": m["financeiro"]["mes"], "positivacao": m["positivacao"]["mes"]}


def tv_metas_dia(db: Database, now: datetime) -> dict | None:
    snap = store_for(db).get()
    if snap is None or snap.metas is None or not snap.metas["is_workday"]:
        return None  # domingo não tem meta diária
    m = snap.metas
    return {**_header(db, snap, m, METAS_NEEDS, now), "financeiro": m["financeiro"]["dia"],
            "positivacao": m["positivacao"]["dia"]}


def tv_focos(db: Database, now: datetime) -> dict | None:
    snap = store_for(db).get()
    if snap is None or snap.focos is None or not snap.focos["focos"]:
        return None
    f = snap.focos
    return {**_header(db, snap, f, FOCOS_NEEDS, now), "focos": f["focos"]}
