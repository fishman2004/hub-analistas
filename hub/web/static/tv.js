// TV da sala: busca o estado a cada 5 s e passa de uma tela para a outra sozinha (sem recarregar).
// Nunca rola. Se o servidor cair, mantém a última tela e avisa "sem atualização desde HH:MM".
// Todo texto vindo do servidor entra por textContent (nunca innerHTML).
//
// Telas são módulos: cada arquivo em static/tv-telas/ chama HubTV.registrar("id", { desenhar, aoMostrar })
// e tem um <section class="tela" data-tela="id"> em tv.html. O servidor diz quais entram na rotação
// e por quanto tempo (hub/telas.py). Uma tela nova não mexe nas outras.
(function () {
  "use strict";
  const INTERVALO_MS = 5000;
  const DIAS = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
  const CLASSE_STATUS = { "Na sala": "st-sala", "Em reunião": "st-reuniao", "Pausa": "st-pausa", "Fora da empresa": "st-fora" };
  const CADEADO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm-3 8V7a3 3 0 0 1 6 0v3z"/></svg>';
  const modulos = {};
  let ultimaAtualizacao = null;
  let ultimoEstado = null;
  let rotacao = [{ id: "quadro", label: "Quadro", seconds: 30 }];
  let atual = "quadro";
  let inicioTela = Date.now();

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
    const card = el("div", "cartao" + (c.reserved ? " reservada" : "") + (c.overdue ? " atrasada" : ""));
    card.style.setProperty("--cor", c.color);
    card.append(el("div", "ini", c.initials));
    const titulo = el("div", "titulo");
    if (c.reserved) titulo.innerHTML = CADEADO;  // só o ícone fixo; o texto entra abaixo por textContent
    titulo.append(document.createTextNode(c.title));
    card.append(titulo);
    const meta = el("div", "meta");
    if (c.folder) meta.append(el("span", "", "Pasta " + (c.folder === "G" ? "G (Canal Farma)" : c.folder)));
    if (c.requested_by) meta.append(el("span", "", "Pedido por " + c.requested_by));
    if (c.overdue) meta.append(el("span", "atraso", "atrasada · prazo " + dataCurta(c.due)));
    else if (c.due) meta.append(el("span", "", "prazo " + dataCurta(c.due)));
    if (meta.childElementCount) card.append(meta);
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

  function passo() {
    const tela = rotacao.find((t) => t.id === atual);
    if (!tela) { mostrar(rotacao[0].id); return; }  // a tela atual saiu da rotação
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
      const r = await fetch("/api/tv", { cache: "no-store", signal: AbortSignal.timeout(4000) });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const dados = await r.json();
      ultimaAtualizacao = new Date();
      document.getElementById("sem-conexao").hidden = true;
      ultimoEstado = dados;
      desenharPresenca(dados.people);
      avisoAtrasadas(dados.overdue || 0);
      desenharTelas(dados);
    } catch (e) {
      semConexao();  // mantém a última tela (e a rotação continua com o último estado)
    }
  }

  window.HubTV = {
    registrar(id, modulo) { modulos[id] = modulo; },
    el, cartao, paginar, encaixar, dataCurta,
  };

  window.addEventListener("load", () => {
    // a TV pode mudar de tamanho (quiosque abrindo): redesenha com o último estado
    window.addEventListener("resize", () => { if (ultimoEstado) desenharTelas(ultimoEstado); });
    atualizar();
    setInterval(atualizar, INTERVALO_MS);
    setInterval(passo, 250);
  });
})();
