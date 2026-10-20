"""Integração com o Pombo (fase 9): os envios do dia, lidos do histórico CSV que o Pombo grava.

O Pombo (projeto irmão, https://github.com/fishman2004/pombo) grava cada envio numa pasta, em geral
da rede: `<pasta do histórico>/<analista>/<AAAA-MM>.csv`, um arquivo por analista por mês. O Hub só
lê esses arquivos, nunca escreve neles, e interpreta as linhas do mesmo jeito que o Pombo
(pombo/history.py e pombo/engine.py): linha estragada é ignorada, cada destinatário é reconhecido
pelo identificador (ou pelo nome, nas linhas antigas) e "falhou" seguido de "enviado" é sucesso.

A TV recebe só o horário, o nome do envio, o analista, o canal e a situação. Destinatários, detalhes
dos erros e nomes de arquivo ficam na página Envios do app.

A leitura roda numa linha separada (a pasta de rede pode estar lenta ou fora do ar e a TV não pode
esperar) e cada arquivo só é relido quando muda (data e tamanho). Se um arquivo não abrir (aberto
no Excel) ou a pasta cair, o Hub segue com a última leitura boa e avisa.
"""

import csv
import logging
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .db import Database, get_setting, log_event, put_setting
from .people import Person, ValidationError, list_people
from .planilhas import normalize

log = logging.getLogger("hub.envios")

# o contrato do histórico, igual a pombo/history.py (o Pombo só acrescenta colunas no fim)
COLUMNS = (
    "data_hora", "analista", "envio", "horario_agendado", "canal",
    "destinatario", "arquivos", "status", "detalhe", "envio_id", "destinatario_id",
)
SUCCESS = {"enviado", "demonstracao"}
MAX_ATTEMPTS = 4  # pombo/rules.py: 1 tentativa + 3 novas, uma a cada 5 min
RETRY_EVERY = timedelta(minutes=5)
# falha com tentativas sobrando e a última há menos que isso: o Pombo ainda vai tentar de novo
RETRY_WINDOW = RETRY_EVERY * 2

SETTING_FOLDER = "pombo.pasta"
REFRESH_SECONDS = 5  # a TV busca a cada 5 s; a pasta é olhada no máximo nesse ritmo
PAGE_WAIT_SECONDS = 8  # a página Envios espera a leitura até isso; depois mostra a última
BACKGROUND = True  # no Hub de verdade, a leitura roda numa linha separada; os testes desligam

FOLDER_ERROR = "Não consegui abrir a pasta (está fora da rede ou o caminho mudou?)."
LOCKED_ERROR = "Não consegui ler o arquivo (está aberto no Excel?). Mostrando a última leitura."
CHANNELS = {"email": "E-mail", "whatsapp": "WhatsApp"}

# situação de cada rodada e o grupo dela: ok, com falha ou em andamento
GROUPS = {
    "enviado": "ok", "manual": "ok",
    "parcial": "falha", "falhou": "falha", "desistiu": "falha", "perdido": "falha",
    "tentando": "andamento", "conexao": "andamento", "esperando": "andamento",
}


# ---------- leitura do CSV (igual ao Pombo) ----------

@dataclass(frozen=True)
class Row:
    when: datetime
    analyst: str
    dispatch_name: str
    run: str  # "AAAA-MM-DD HH:MM" (agendada) ou "manual AAAA-MM-DD HH:MM:SS" (Enviar agora)
    channel: str  # vazio nas linhas da rodada inteira (esperando, desistiu, perdido)
    target: str
    files: str
    status: str
    detail: str
    dispatch_id: str
    target_key: str = ""  # vazio em linhas antigas e nas linhas da rodada inteira


def analyst_slug(name: str) -> str:
    """O nome da pasta que o Pombo cria para cada analista ("Ana Souza" -> "ana-souza")."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "-".join(plain.lower().split()) or "analista"


def parse_line(values: list[str]) -> Row:
    """Uma linha do CSV, como o Pombo lê (history._from_csv). Linha estragada: ValueError."""
    when = datetime.strptime(values[0], "%Y-%m-%d %H:%M:%S")
    if len(values) < 10:
        raise ValueError("linha incompleta")
    # arquivos de versões antigas não têm as colunas do fim; colunas novas no fim são ignoradas
    return Row(when, *(values[1:] + [""] * (len(COLUMNS) - len(values)))[: len(COLUMNS) - 1])


def read_history(path: Path) -> tuple[list[Row], int]:
    """As linhas boas do arquivo e quantas foram ignoradas. Arquivo travado: OSError."""
    rows, skipped = [], 0
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # cabeçalho
        for values in reader:
            if not values:
                continue
            try:
                rows.append(parse_line(values))
            except (ValueError, TypeError):
                skipped += 1  # salva pelo Excel ou cortada numa queda de energia: o Pombo também ignora
    return rows, skipped


def run_time(run: str) -> tuple[datetime | None, bool]:
    """O horário da rodada pelo rótulo dela e se foi um "Enviar agora" (manual)."""
    manual = run.startswith("manual ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(run.removeprefix("manual "), fmt), manual
        except ValueError:
            continue
    return None, False


# ---------- cada rodada do dia ----------

@dataclass
class Destinatario:
    channel: str
    label: str
    state: str  # enviado, tentando, falhou ou esperando (o canal está fora do ar)
    attempts: int  # quantas vezes falhou
    detail: str
    last: datetime
    demo: bool = False

    @property
    def order(self) -> int:  # no detalhe da página, os problemas primeiro
        return ("falhou", "tentando", "esperando", "enviado").index(self.state)


@dataclass
class Rodada:
    folder: str  # a pasta do analista no histórico
    analyst: str
    dispatch_id: str
    dispatch_name: str
    run: str
    scheduled: datetime
    manual: bool
    targets: list[Destinatario]
    state: str
    detail: str = ""

    @property
    def group(self) -> str:
        return GROUPS[self.state]

    @property
    def sent(self) -> int:
        return sum(t.state == "enviado" for t in self.targets)

    @property
    def failed(self) -> int:
        return sum(t.state == "falhou" for t in self.targets)

    @property
    def total(self) -> int:
        return len(self.targets)

    @property
    def channels(self) -> list[str]:
        return sorted({t.channel for t in self.targets}, key=lambda c: (c not in CHANNELS, c))

    @property
    def hour(self) -> str:
        return f"{self.scheduled:%H:%M}"

    @property
    def demo(self) -> bool:
        sent = [t for t in self.targets if t.state == "enviado"]
        return bool(sent) and all(t.demo for t in sent)


def _target_key(r: Row) -> tuple[str, str]:
    # como o Pombo casa a linha com o destinatário (engine._matches): pelo identificador e, nas
    # linhas antigas sem ele, pelo nome
    return r.channel, ("id:" + r.target_key) if r.target_key else ("nome:" + r.target)


def _targets(rows: list[Row], now: datetime) -> list[Destinatario]:
    by_target: dict[tuple, list[Row]] = {}
    for r in rows:
        by_target.setdefault(_target_key(r), []).append(r)
    out = []
    for (channel, _), items in by_target.items():
        failures = [r for r in items if r.status == "falhou"]
        good = [r for r in items if r.status in SUCCESS]
        last = items[-1]
        if good:
            state, detail = "enviado", ""
        elif failures:
            retry = len(failures) < MAX_ATTEMPTS and now - failures[-1].when <= RETRY_WINDOW
            state, detail = ("tentando" if retry else "falhou"), failures[-1].detail
        else:
            state, detail = "esperando", last.detail  # canal fora do ar: o Pombo envia quando voltar
        out.append(Destinatario(channel, last.target, state, len(failures), detail,
                                good[0].when if good else last.when,
                                demo=bool(good) and all(r.status == "demonstracao" for r in good)))
    return out


def _covered_by_manual(rows: list[Row], dispatch: str, scheduled: datetime) -> datetime | None:
    """Um "Enviar agora" depois do horário já cumpriu a rodada agendada (engine._covered_by_manual)."""
    times = [r.when for r in rows if (r.dispatch_id or r.dispatch_name) == dispatch and r.run.startswith("manual ")
             and r.channel and r.when >= scheduled and r.when.date() == scheduled.date()]
    return min(times, default=None)


def _build(folder: str, dispatch: str, run: str, items: list[Row], all_rows: list[Row], now: datetime) -> Rodada:
    scheduled, manual = run_time(run)
    scheduled = scheduled or items[0].when  # rótulo que não deu para ler: vale a hora da primeira linha
    analyst = next((r.analyst for r in reversed(items) if r.analyst), "")
    targets = _targets([r for r in items if r.channel], now)
    rodada = Rodada(folder, analyst, dispatch, items[-1].dispatch_name, run, scheduled, manual, targets, "enviado")
    states = {t.state for t in targets}
    if targets:
        # algo já foi enviado ou tentado: isso importa mais que a espera pelo arquivo (como no Pombo)
        if "falhou" in states:
            rodada.state = "parcial" if "enviado" in states else "falhou"
            rodada.detail = next(t.detail for t in reversed(targets) if t.state == "falhou")
        elif "tentando" in states:
            rodada.state = "tentando"
        elif "esperando" in states:
            rodada.state = "conexao"
            rodada.detail = next(t.detail for t in targets if t.state == "esperando")
        return rodada
    if not manual and (when := _covered_by_manual(all_rows, dispatch, scheduled)):
        rodada.state, rodada.detail = "manual", f"{when:%H:%M}"
        return rodada
    for status in ("perdido", "desistiu", "esperando"):  # a ordem da tela Hoje do Pombo
        row = next((r for r in reversed(items) if r.status == status), None)
        if row:
            rodada.state, rodada.detail = status, row.detail
            return rodada
    rodada.state, rodada.detail = "esperando", items[-1].detail  # situação que esta versão não conhece
    return rodada


def runs_of_day(rows_by_folder: dict[str, list[Row]], day: date, now: datetime) -> list[Rodada]:
    """As rodadas com horário no dia, de todos os analistas, por horário."""
    runs = []
    for folder, rows in rows_by_folder.items():
        groups: dict[tuple[str, str], list[Row]] = {}
        for r in rows:  # o mesmo envio_id pode existir no Pombo de outro analista: a pasta separa
            groups.setdefault((r.dispatch_id or r.dispatch_name, r.run), []).append(r)
        for (dispatch, run), items in groups.items():
            scheduled = run_time(run)[0] or items[0].when
            if scheduled.date() == day:  # rodada de ontem com tentativa depois da meia-noite fica fora
                runs.append(_build(folder, dispatch, run, items, rows, now))
    return sorted(runs, key=lambda r: (r.scheduled, normalize(r.dispatch_name), r.folder))


def status_text(r: Rodada) -> str:
    """A situação curta, com o símbolo, igual na TV e no app."""
    if r.state in ("parcial", "falhou"):
        return f"⚠ {r.failed} falha" + ("s" if r.failed > 1 else "")
    return {
        "enviado": "✓ tudo enviado",
        "manual": f"✓ enviado às {r.detail} (manual)",
        "tentando": "↻ tentando de novo",
        "conexao": "⏳ esperando conexão",
        "esperando": "⏳ esperando atualização",
        "desistiu": "⚠ não atualizado",
        "perdido": "⚠ perdido",
    }[r.state]


def count_text(r: Rodada) -> str:
    if not r.total:
        return ""
    return f"{r.sent} de {r.total} enviado{'s' if r.total > 1 else ''}" + (" (demonstração)" if r.demo else "")


def channel_text(r: Rodada) -> str:
    return " · ".join(CHANNELS.get(c, c.capitalize()) for c in r.channels) or "—"


def target_text(t: Destinatario) -> str:
    """Uma linha do detalhe de um destinatário, para a página Envios."""
    if t.state == "enviado":
        return f"{'demonstração' if t.demo else 'enviado'} às {t.last:%H:%M}"
    if t.state == "tentando":
        return f"falhou às {t.last:%H:%M}, o Pombo vai tentar de novo ({t.attempts} de {MAX_ATTEMPTS} tentativas)"
    if t.state == "falhou":
        return f"falhou, {t.attempts} tentativa{'s' if t.attempts > 1 else ''} (a última às {t.last:%H:%M})"
    return f"esperando o canal desde {t.last:%H:%M}"


# ---------- pasta e configurações ----------

def history_folder(db: Database) -> Path | None:
    """A pasta do histórico do Pombo. Sem pasta escolhida, a integração está desligada."""
    custom = get_setting(db, SETTING_FOLDER)
    return Path(custom) if custom else None


def pombo_config(db: Database) -> dict:
    return {"folder": get_setting(db, SETTING_FOLDER) or ""}


def save_pombo_config(db: Database, now: datetime, actor: Person, folder: str) -> None:
    if actor is None or not actor.is_admin:
        raise PermissionError("Só administradores podem fazer isso.")
    folder = folder.strip().strip('"')
    if folder and not Path(folder).is_dir():
        raise ValidationError(f"Não encontrei a pasta {folder}. Confira o caminho (ou deixe em branco para desligar).")
    with db.connect() as conn:
        put_setting(conn, SETTING_FOLDER, folder or None)
        log_event(conn, now, actor.id, "config_pombo", "config:pombo", "")


# ---------- leitura em segundo plano, com cache ----------

@dataclass
class FileStatus:
    folder: str  # a pasta do analista
    path: Path
    analyst: str = ""
    modified: datetime | None = None
    lines: int = 0
    skipped: int = 0
    error: str = ""
    kept: bool = False  # não deu para ler agora: valem as linhas da última leitura boa

    @property
    def exists(self) -> bool:
        return self.modified is not None


@dataclass
class Leitura:
    folder: Path
    month: str
    checked: datetime | None  # a última vez que a pasta foi lida inteira
    error: str = ""
    hint: str = ""
    files: list[FileStatus] = field(default_factory=list)
    rows: dict[str, list[Row]] = field(default_factory=dict)  # {pasta do analista: linhas do mês}


class EnviosStore:
    def __init__(self, db: Database, background: bool | None = None) -> None:
        self.db = db
        self.background = BACKGROUND if background is None else background
        self._lock = threading.Lock()  # protege o resultado e o controle da linha de leitura
        self._work = threading.Lock()  # uma leitura por vez
        self._thread: threading.Thread | None = None
        self._started = 0.0
        self._snapshot: Leitura | None = None
        self._cache: dict[str, tuple] = {}  # {caminho: (assinatura, linhas, ignoradas)}
        self._logged: dict[str, str] = {}  # o último problema de cada arquivo que foi para o hub.log

    def get(self, now: datetime, wait: bool = False) -> Leitura | None:
        """A última leitura da pasta. A TV nunca espera: a leitura nova roda numa linha separada e
        aparece na próxima busca. Com wait=True (a página Envios), espera alguns segundos por ela."""
        folder = history_folder(self.db)
        if folder is None:
            return None
        if not self.background:
            self._refresh(folder, now)
            return self._current(folder)
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            stale = (self._snapshot is None or self._snapshot.folder != folder
                     or time.monotonic() - self._started >= REFRESH_SECONDS)
            if not running and (stale or wait):
                self._started = time.monotonic()
                self._thread = threading.Thread(target=self._refresh, args=(folder, now), daemon=True, name="pombo")
                self._thread.start()
            thread = self._thread
        if wait and thread is not None:
            thread.join(PAGE_WAIT_SECONDS)
        return self._current(folder)

    def _current(self, folder: Path) -> Leitura | None:
        with self._lock:
            snap = self._snapshot
        return snap if snap is not None and snap.folder == folder else None  # pasta trocada: nada da antiga

    def _refresh(self, folder: Path, now: datetime) -> None:
        with self._work:
            snap = self._read(folder, now)
        with self._lock:
            self._snapshot = snap

    def _note(self, key: str, problem: str) -> None:
        # cada problema vai uma vez para o hub.log, e não a cada 5 s enquanto durar
        if problem and self._logged.get(key) != problem:
            log.warning("pombo: %s", problem)
        self._logged[key] = problem

    def _read(self, folder: Path, now: datetime) -> Leitura:
        previous = self._current(folder)
        month = f"{now:%Y-%m}"
        try:
            subfolders = sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))
            single = not subfolders and any(folder.glob("????-??.csv"))
        except OSError:
            self._note("pasta", f"não consegui abrir a pasta do histórico {folder}")
            if previous is not None:  # pasta de rede fora do ar: segue com a última leitura e avisa
                return Leitura(folder, previous.month, previous.checked, FOLDER_ERROR, previous.hint,
                               previous.files, previous.rows)
            return Leitura(folder, month, None, FOLDER_ERROR)
        self._note("pasta", "")
        files, rows, seen = [], {}, set()
        for sub in subfolders:
            path = sub / f"{month}.csv"
            status = FileStatus(sub.name, path)
            files.append(status)
            key = str(path)
            seen.add(key)
            try:
                st = path.stat()
            except FileNotFoundError:
                self._cache.pop(key, None)  # nenhum envio deste analista no mês
                continue
            except OSError:
                st = None
            status.modified = datetime.fromtimestamp(st.st_mtime) if st else None
            cached = self._cache.get(key)
            signature = (st.st_mtime_ns, st.st_size) if st else None
            if st is None or cached is None or cached[0] != signature:
                try:
                    if st is None:
                        raise OSError("sem acesso")
                    parsed, skipped = read_history(path)
                    cached = (signature, parsed, skipped)
                    self._cache[key] = cached
                    self._note(key, f"{sub.name}/{path.name}: {skipped} linha(s) ignorada(s)" if skipped else "")
                except OSError:
                    status.error, status.kept = LOCKED_ERROR, cached is not None
                    self._note(key, f"não consegui ler {sub.name}/{path.name} (aberto no Excel?)")
            if cached is not None:
                rows[sub.name] = cached[1]
                status.lines, status.skipped = len(cached[1]), cached[2]
                status.analyst = next((r.analyst for r in reversed(cached[1]) if r.analyst), "")
        for key in list(self._cache):
            if key not in seen:
                del self._cache[key]  # virou o mês ou o analista saiu da pasta
        hint = ("Esta parece a pasta de um analista só. Escolha a pasta de cima, a que tem uma pasta para cada "
                "analista.") if single else ""
        return Leitura(folder, month, now, "", hint, files, rows)


_stores: dict[str, EnviosStore] = {}
_stores_lock = threading.Lock()


def store_for(db: Database) -> EnviosStore:
    with _stores_lock:
        key = str(db.path.resolve())
        if key not in _stores:
            _stores[key] = EnviosStore(db)
        return _stores[key]


# ---------- quem é cada analista ----------

def analyst_info(folder: str, name: str, people: list[Person]) -> tuple[str, str, str]:
    """Nome, iniciais e cor: os do Hub quando a pessoa está cadastrada (pelo nome que o Pombo grava ou
    pela pasta que ele cria com esse nome); senão, o nome que o Pombo gravou, sem cor própria."""
    for p in sorted(people, key=lambda p: not p.active):
        if analyst_slug(p.name) == folder or (name and normalize(p.name) == normalize(name)):
            return p.name, p.initials, p.color
    shown = name or folder.replace("-", " ").title()
    return shown, "".join(w[0] for w in shown.split()[:2]).upper(), ""


def who_is_who(db: Database, snap: Leitura) -> dict[str, tuple[str, str, str]]:
    people = list_people(db, active_only=False)
    return {f.folder: analyst_info(f.folder, f.analyst, people) for f in snap.files}


def warning(snap: Leitura, who: dict) -> str:
    if snap.error:
        return "Pasta do Pombo fora do ar"
    locked = [who.get(f.folder, (f.folder,))[0] for f in snap.files if f.error]
    return f"Histórico de {', '.join(locked)} travado (aberto no Excel?)" if locked else ""


# ---------- o que vai para a TV (sem destinatários nem detalhes) ----------

def tv_envios(db: Database, now: datetime) -> dict | None:
    snap = store_for(db).get(now)
    if snap is None:
        return None
    runs = runs_of_day(snap.rows, now.date(), now)
    if not runs:
        return None
    who = who_is_who(db, snap)
    rodadas = []
    for r in runs:
        name, initials, color = who.get(r.folder) or analyst_info(r.folder, r.analyst, [])
        rodadas.append({"hora": r.hour, "manual": r.manual, "envio": r.dispatch_name, "analista": name,
                        "iniciais": initials, "cor": color, "canal": channel_text(r), "grupo": r.group,
                        "situacao": status_text(r), "contagem": count_text(r)})
    return {"atualizado": f"{snap.checked:%H:%M}" if snap.checked else "", "aviso": warning(snap, who),
            "resumo": {g: sum(r.group == g for r in runs) for g in ("ok", "falha", "andamento")},
            "rodadas": rodadas}
