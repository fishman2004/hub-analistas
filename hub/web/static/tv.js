// TV da sala: busca o estado a cada 5 s e passa de uma tela para a outra sozinha (sem recarregar).
// Nunca rola. Se o servidor cair, mantém a última tela e avisa "sem atualização desde HH:MM".
// Todo texto vindo do servidor entra por textContent (nunca innerHTML).
//
// Telas são módulos: cada arquivo em static/tv-telas/ chama HubTV.registrar("id", { desenhar, aoMostrar })
// e tem um <section class="tela" data-tela="id"> em tv.html. O servidor diz quais entram na rotação
// e por quanto tempo (hub/telas.py). Uma tela nova não mexe nas outras.
//
// Aviso das rotinas (fase 7): o /api/tv manda as rotinas de hoje com o horário. Quando o horário
// chega, a TV toca o som uma vez e mostra uma faixa por cima de qualquer tela por ~20 s. As rotinas
// já tocadas ficam guardadas (na memória e no localStorage), para recarregar a página não tocar de novo.
//
// Pausa (fase 10): um clique ou a tecla Espaço pausa na tela atual (← → trocam de tela, ↑ ↓ passam as
// páginas do Quadro) e ela volta sozinha depois do tempo padrão. A pausa feita pelo app (página "TV da
// sala") chega no /api/tv e vence a local. Com ?tela=<id>&fixa=1, a aba é "a TV no meu PC": nasce
// pausada naquela tela, não obedece à pausa da sala, não toca aviso e não conta como a TV da sala.
(function () {
  "use strict";
  const INTERVALO_MS = 5000;
  const DIAS = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
  const CLASSE_STATUS = { "Na sala": "st-sala", "Em reunião": "st-reuniao", "Pausa": "st-pausa", "Fora da empresa": "st-fora" };
  const CADEADO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm-3 8V7a3 3 0 0 1 6 0v3z"/></svg>';
  const RELOGIO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 2a8 8 0 1 1 0 16 8 8 0 0 1 0-16zm-1 3v5.4l4.3 2.6 1-1.7-3.3-2V7z"/></svg>';
  const SINO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 22a2.5 2.5 0 0 0 2.4-2h-4.8a2.5 2.5 0 0 0 2.4 2zm7-6V11a7 7 0 0 0-5.5-6.8V3.5a1.5 1.5 0 0 0-3 0v.7A7 7 0 0 0 5 11v5l-2 2v1h18v-1z"/></svg>';
  const AVISO_MS = 20000;  // quanto tempo a faixa do aviso fica na tela
  const ATRASO_MAX_MS = 10 * 60 * 1000;  // TV ligada depois disso: o aviso não toca atrasado
  const GUARDADOS = "hub.avisos.tocados";
  const modulos = {};
  let ultimaAtualizacao = null;
  let ultimoEstado = null;
  let rotacao = [{ id: "quadro", label: "Quadro", seconds: 30 }];
  let atual = "quadro";
  let inicioTela = Date.now();
  const PARAMS = new URLSearchParams(location.search);
  const ESPIAR = PARAMS.get("fixa") === "1";
  let pedida = ESPIAR ? PARAMS.get("tela") : null;  // a tela que a aba "no meu PC" abre primeiro
  let pausaLocal = ESPIAR ? { ate: Infinity } : null;
  let pausaRemota = null;  // { tela, ate, iniciais, pagina }, do /api/tv
  let paginaRemota;  // contador de "página seguinte" pelo app; undefined até a primeira busca
  let minutosPausa = 15;

  // ---------- peças que as telas reaproveitam ----------

  function el(tag, cls, texto) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function dataCurta(iso) {  // "2026-10-20" -> "20/10"
    return iso.slice(8, 10) + "/" + iso.slice(5, 7);
  }

  function cartao(c) {
    const r = c.routine;  // rotina (fase 7): horário, prazo, pastas e espera; nunca vem em reservada
    const card = el("div", "cartao" + (c.reserved ? " reservada" : "") + (c.overdue ? " atrasada" : "") + (r ? " rotina" : ""));
    card.style.setProperty("--cor", c.color);
    card.append(el("div", "ini", c.initials));
    const titulo = el("div", "titulo");
    if (c.reserved) titulo.innerHTML = CADEADO;  // só o ícone fixo; o texto entra abaixo por textContent
    titulo.append(document.createTextNode(c.title));
    card.append(titulo);
    const meta = el("div", "meta");
    if (r) {
      const atrasada = r.late && c.overdue;
      const hora = el("span", "rotina-hora" + (atrasada ? " atraso" : ""));
      hora.innerHTML = RELOGIO;
      hora.append(document.createTextNode(atrasada ? "atrasada · até " + r.deadline
        : "rotina " + r.time + (r.deadline ? " · até " + r.deadline : "")));
      meta.append(hora);
    }
    if (c.folder) meta.append(el("span", "", "Pasta " + (c.folder === "G" ? "G (Canal Farma)" : c.folder)));
    if (c.requested_by) meta.append(el("span", "", "Pedido por " + c.requested_by));
    // rotina de hoje: o prazo já está junto do horário; a data só aparece se ela ficou de outro dia
    if (c.overdue && !(r && r.late)) meta.append(el("span", "atraso", "atrasada · prazo " + dataCurta(c.due)));
    else if (c.due && !r) meta.append(el("span", "", "prazo " + dataCurta(c.due)));
    if (r && r.waiting.length) meta.append(el("span", "aguardando", "Aguardando: " + r.waiting.join(", ")));
    if (meta.childElementCount) card.append(meta);
    if (r && r.folders.length) {
      // uma letra por pasta: cheia (com a cor da pasta) quando já marcou, apagada quando falta
      const pastas = el("div", "pastas-rotina");
      for (const f of r.folders) {
        const chip = el("span", "pasta-chip" + (r.checked.includes(f) ? " marcada" : ""), f);
        chip.dataset.pasta = f;
        pastas.append(chip);
      }
      pastas.append(el("span", "pastas-conta", r.checked.length + "/" + r.folders.length));
      card.append(pastas);
    }
    return card;
  }

  const cabe = (caixa) => caixa.scrollHeight <= caixa.clientHeight;

  function paginar(caixa, cartoes) {
    // divide os cartões em páginas que cabem na caixa, medindo de verdade (as telas fora do ar
    // ficam invisíveis mas continuam ocupando espaço, então a medida vale para todas)
    const paginas = [];
    let i = 0;
    while (i < cartoes.length) {
      caixa.replaceChildren();
      const pagina = [];
      while (i < cartoes.length) {
        caixa.append(cartao(cartoes[i]));
        if (!cabe(caixa) && pagina.length) { caixa.lastChild.remove(); break; }
        pagina.push(cartoes[i]);
        i++;
      }
      paginas.push(pagina);
    }
    return paginas;
  }

  function encaixar(caixa, cartoes, vazio) {
    // acrescenta enquanto cabe; o que sobrar vira "+ N demandas"
    caixa.replaceChildren();
    if (!cartoes.length) { caixa.append(el("div", "vazio", vazio || "Nada aqui.")); return; }
    let mostrados = 0;
    for (const c of cartoes) {
      caixa.append(cartao(c));
      if (!cabe(caixa)) { caixa.lastChild.remove(); break; }
      mostrados++;
    }
    if (mostrados === cartoes.length) return;
    const mais = el("div", "mais");
    caixa.append(mais);
    while (true) {
      mais.textContent = "+ " + (cartoes.length - mostrados) + (cartoes.length - mostrados === 1 ? " demanda" : " demandas");
      if (cabe(caixa) || mostrados === 0) break;
      mais.previousSibling.remove();
      mostrados--;
    }
  }

  // ---------- partes fixas: relógio, presença, avisos ----------

  function relogio() {
    const agora = new Date();
    document.getElementById("data").textContent =
      DIAS[agora.getDay()] + ", " + String(agora.getDate()).padStart(2, "0") + "/" + String(agora.getMonth() + 1).padStart(2, "0");
    document.getElementById("hora").textContent =
      String(agora.getHours()).padStart(2, "0") + ":" + String(agora.getMinutes()).padStart(2, "0");
  }

  function desenharPresenca(pessoas) {
    const faixa = document.getElementById("presenca");
    faixa.replaceChildren();
    for (const p of pessoas) {
      const card = el("div", "pessoa " + (CLASSE_STATUS[p.status] || "st-fora"));
      card.style.setProperty("--cor", p.color);
      card.append(el("div", "ini", p.initials), el("div", "nome", p.name));
      const st = el("div", "status");
      st.append(el("b", "", p.status), el("span", "", "desde " + p.since));
      card.append(st);
      faixa.append(card);
    }
  }

  function avisoAtrasadas(n) {
    const aviso = document.getElementById("atrasadas");
    aviso.hidden = !n;
    aviso.textContent = n === 1 ? "1 demanda atrasada" : n + " demandas atrasadas";
  }

  function semConexao() {
    const aviso = document.getElementById("sem-conexao");
    const quando = ultimaAtualizacao
      ? String(ultimaAtualizacao.getHours()).padStart(2, "0") + ":" + String(ultimaAtualizacao.getMinutes()).padStart(2, "0")
      : "--:--";
    aviso.textContent = "Sem atualização desde " + quando;
    aviso.hidden = false;
  }

  // ---------- aviso sonoro das rotinas ----------

  let avisos = [];
  let desvio = 0;  // relógio do servidor menos o deste navegador (a TV pode estar em outro PC)
  let hoje = "";
  let timerAviso = null;
  const som = new Audio("/static/aviso.wav");
  const tocados = new Set(lerTocados());

  function lerTocados() {
    try { return JSON.parse(localStorage.getItem(GUARDADOS) || "[]"); } catch (e) { return []; }
  }

  function guardarTocados() {
    // a chave termina com a data ("rotina-5-2026-10-20"): guarda só as de hoje, para não crescer
    try { localStorage.setItem(GUARDADOS, JSON.stringify([...tocados].filter((k) => k.endsWith(hoje)))); } catch (e) { /* sem armazenamento: fica só na memória */ }
  }

  function mostrarAviso(lista) {
    const faixa = document.getElementById("aviso-rotina");
    faixa.replaceChildren();
    const icone = el("div", "aviso-icone");
    icone.innerHTML = SINO;
    const textos = el("div", "aviso-textos");
    textos.append(el("div", "aviso-rotulo", lista.length === 1 ? "Hora da rotina" : "Hora das rotinas"));
    for (const a of lista) {
      const linha = el("div", "aviso-linha");
      linha.append(el("b", "", a.time), document.createTextNode(" " + a.name));
      if (a.deadline) linha.append(el("span", "aviso-prazo", "até " + a.deadline));
      textos.append(linha);
    }
    faixa.append(icone, textos);
    faixa.hidden = false;
    clearTimeout(timerAviso);
    timerAviso = setTimeout(() => { faixa.hidden = true; }, AVISO_MS);
    try {
      som.currentTime = 0;
      const tocando = som.play();
      // o navegador bloqueou o som: a faixa aparece igual, com a dica (ver o roteiro da fase 7)
      if (tocando) tocando.catch(() => textos.append(el("div", "aviso-mudo", "Som bloqueado pelo navegador: veja o roteiro da fase 7.")));
    } catch (e) { /* sem som: fica só a faixa */ }
  }

  function conferirAvisos() {
    if (ESPIAR || !avisos.length) return;  // a TV aberta no PC de alguém não toca aviso
    const agora = Date.now() + desvio;
    const novos = [];
    let mudou = false;
    for (const a of avisos) {
      if (tocados.has(a.key)) continue;
      const quando = new Date(a.at).getTime();
      if (agora < quando) continue;
      tocados.add(a.key);
      mudou = true;
      if (agora - quando <= ATRASO_MAX_MS) novos.push(a);  // TV desligada no horário: não toca atrasado
    }
    if (mudou) guardarTocados();
    if (novos.length) mostrarAviso(novos);
  }

  // ---------- rotação ----------

  function secao(id) {
    return document.querySelector('.tela[data-tela="' + id + '"]');
  }

  function desenharIndicador() {
    const caixa = document.getElementById("rotacao");
    caixa.replaceChildren();
    if (rotacao.length < 2) return;  // uma tela só: nada a indicar
    for (const t of rotacao) {
      const item = el("div", "rot-item" + (t.id === atual ? " ativa" : ""));
      item.append(el("span", "rot-nome", t.label));
      const barra = el("span", "rot-barra");
      barra.append(el("span", "rot-progresso"));
      item.append(barra);
      caixa.append(item);
    }
  }

  function mostrar(id) {
    atual = id;
    inicioTela = Date.now();
    for (const s of document.querySelectorAll(".tela")) s.classList.toggle("ativa", s.dataset.tela === id);
    const m = modulos[id];
    if (m && m.aoMostrar) m.aoMostrar(secao(id));
    desenharIndicador();
  }

  // ---------- pausa ----------

  const remota = () => !ESPIAR && pausaRemota;
  const pausada = () => Boolean(remota() || pausaLocal);
  const horaCurta = (d) => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");

  function desenharPausa() {
    const selo = document.getElementById("pausa");
    selo.hidden = !pausada();
    document.getElementById("rotacao").hidden = pausada();  // o selo fica no lugar do indicador da rotação
    if (ESPIAR) selo.textContent = "⏸ No seu PC · ← → trocam a tela";
    else if (pausaRemota) selo.textContent = "⏸ Pausada" + (pausaRemota.iniciais ? " por " + pausaRemota.iniciais : "")
      + " · volta às " + pausaRemota.ate.slice(11, 16);
    else if (pausaLocal) selo.textContent = "⏸ Pausada · volta às " + horaCurta(new Date(pausaLocal.ate));
  }

  function alternarPausa() {
    if (ESPIAR) return;  // a aba no meu PC fica sempre parada
    if (remota()) {  // pausa do app vence: quem retoma é o app (ou o prazo)
      const selo = document.getElementById("pausa");
      selo.classList.remove("piscar"); void selo.offsetWidth; selo.classList.add("piscar");
      return;
    }
    pausaLocal = pausaLocal ? null : { ate: Date.now() + minutosPausa * 60000 };
    if (!pausaLocal) inicioTela = Date.now();  // volta à rotação com o tempo cheio da tela
    desenharPausa();
  }

  function trocarTela(direcao) {
    if (remota() || rotacao.length < 2) return;
    if (!pausaLocal) pausaLocal = { ate: Date.now() + minutosPausa * 60000 };
    const i = rotacao.findIndex((t) => t.id === atual);
    mostrar(rotacao[(i + direcao + rotacao.length) % rotacao.length].id);
    desenharPausa();
  }

  function trocarPagina(direcao) {
    const m = modulos[atual];
    if (m && m.pagina) m.pagina(secao(atual), direcao);
  }

  function passo() {
    if (pausaLocal && pausaLocal.ate <= Date.now()) {  // o prazo da pausa passou: volta sozinha
      pausaLocal = null;
      inicioTela = Date.now();
      desenharPausa();
    }
    if (pedida && rotacao.some((t) => t.id === pedida)) { mostrar(pedida); pedida = null; return; }
    if (remota()) {
      // pausada pelo app: fica na tela pedida (ou na primeira, se ela saiu da rotação)
      const alvo = rotacao.some((t) => t.id === pausaRemota.tela) ? pausaRemota.tela : rotacao[0].id;
      if (alvo !== atual) mostrar(alvo);
      return;
    }
    const tela = rotacao.find((t) => t.id === atual);
    if (!tela) { mostrar(rotacao[0].id); return; }  // a tela atual saiu da rotação
    if (pausaLocal) return;  // parada: nem troca de tela nem anda a barra
    const passou = Date.now() - inicioTela;
    if (passou >= tela.seconds * 1000 && rotacao.length > 1) {
      const i = rotacao.findIndex((t) => t.id === atual);
      mostrar(rotacao[(i + 1) % rotacao.length].id);
      return;
    }
    const progresso = document.querySelector(".rot-item.ativa .rot-progresso");
    if (progresso) progresso.style.width = Math.min(100, (passou / (tela.seconds * 1000)) * 100) + "%";
  }

  function desenharTelas(dados) {
    const telas = (dados.screens || []).filter((t) => modulos[t.id] && secao(t.id));
    for (const t of telas) modulos[t.id].desenhar(secao(t.id), t.data, dados);
    const antes = rotacao.map((t) => t.id).join();
    rotacao = telas.length ? telas : [{ id: "quadro", label: "Quadro", seconds: 30 }];
    if (rotacao.map((t) => t.id).join() !== antes) desenharIndicador();
  }

  async function atualizar() {
    relogio();
    try {
      // servidor travado (aceita a conexão mas não responde) também conta como "sem atualização"
      // conta qual tela está aparecendo, para a página "TV da sala" do app saber
      const url = "/api/tv?tela=" + encodeURIComponent(atual) + "&pausada=" + (pausada() ? 1 : 0) + (ESPIAR ? "&espiar=1" : "");
      const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(4000) });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const dados = await r.json();
      ultimaAtualizacao = new Date();
      document.getElementById("sem-conexao").hidden = true;
      ultimoEstado = dados;
      desvio = new Date(dados.now).getTime() - Date.now();
      hoje = dados.now.slice(0, 10);
      avisos = dados.avisos || [];
      minutosPausa = dados.pausa_minutos || 15;
      const antes = pausaRemota;
      pausaRemota = dados.pausa || null;
      if (antes && !pausaRemota) inicioTela = Date.now();  // o app retomou: a tela começa com o tempo cheio
      const pagina = pausaRemota && pausaRemota.tela === "quadro" ? pausaRemota.pagina : 0;
      if (paginaRemota !== undefined && pagina > paginaRemota && remota()) trocarPagina(1);
      paginaRemota = pagina;
      desenharPausa();
      conferirAvisos();
      desenharPresenca(dados.people);
      avisoAtrasadas(dados.overdue || 0);
      desenharTelas(dados);
    } catch (e) {
      semConexao();  // mantém a última tela (e a rotação continua com o último estado)
    }
  }

  window.HubTV = {
    registrar(id, modulo) { modulos[id] = modulo; },
    pausada,
    el, cartao, paginar, encaixar, dataCurta,
  };

  window.addEventListener("load", () => {
    // a TV pode mudar de tamanho (quiosque abrindo): redesenha com o último estado
    window.addEventListener("resize", () => { if (ultimoEstado) desenharTelas(ultimoEstado); });
    document.addEventListener("click", alternarPausa);
    document.addEventListener("keydown", (e) => {
      const teclas = { " ": () => alternarPausa(), ArrowLeft: () => trocarTela(-1), ArrowRight: () => trocarTela(1),
                       ArrowUp: () => trocarPagina(-1), ArrowDown: () => trocarPagina(1) };
      if (teclas[e.key]) { e.preventDefault(); teclas[e.key](); }
    });
    atualizar();
    setInterval(atualizar, INTERVALO_MS);
    setInterval(passo, 250);
    setInterval(conferirAvisos, 1000);  // o aviso toca na hora, sem esperar a próxima busca
  });
})();
