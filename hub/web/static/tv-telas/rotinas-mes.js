// Tela "Rotinas do mês" (fase 19): o calendário de rotinas do gestor. Primeiro o mês inteiro, como o
// modelo (segunda a sexta largas, fim de semana estreito, uma cor por categoria). Depois de um tempo
// (40% do tempo da tela, no máximo 10 s), um zoom no quadradinho de hoje: ele cresce até ocupar a tela
// e abre a lista do dia, grande, com o que já foi feito e o próximo dia útil ao lado.
// Com a TV pausada, ↑ ↓ alternam entre o mês e o dia. No PDF, viram duas folhas.
// Fase 24: os compromissos da equipe (da Agenda) entram também, em cinza com a hora, depois das rotinas.
// Só entra na rotação com alguma rotina do mês ou algum compromisso no mês (o servidor decide).
(function () {
  "use strict";
  const { el } = HubTV;
  const ZOOM_MS = 1600;
  const CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  const SEMANA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];
  let ultimo = "";
  let segundos = 25;
  let fase = "mes";
  let timer = null;

  function compromisso(i, grande) {
    const b = el("div", "rmt-item rmt-compromisso");
    b.append(el("span", "rmt-hora", i.hora === "dia todo" ? (grande ? "dia todo" : "") : i.hora.split("–")[0]));
    const texto = el("span", "rmt-texto");
    texto.append(el("b", "", i.categoria + (i.titulo ? ":" : "")), document.createTextNode(i.titulo ? " " + i.titulo : ""));
    b.append(texto);
    if (grande) for (const p of i.pessoas.slice(0, 4)) {
      const ini = el("span", "ini", p.initials);
      ini.style.setProperty("--cor", p.color);
      b.append(ini);
    }
    if (grande && i.pessoas.length > 4) b.append(el("span", "rmt-por", "+" + (i.pessoas.length - 4)));
    return b;
  }

  function barra(i, grande) {
    if (i.tipo === "compromisso") return compromisso(i, grande);
    const b = el("div", "rmt-item" + (i.destaque ? " destaque" : "") + (i.feita ? " feita" : ""));
    b.style.setProperty("--cat", i.cor);
    b.style.setProperty("--cat-texto", i.texto_cor);
    if (grande) {
      const ok = el("span", "rmt-marca");
      if (i.feita) ok.innerHTML = CHECK;  // só o ícone fixo; o texto entra por textContent
      b.append(ok);
    }
    const texto = el("span", "rmt-texto");
    texto.append(el("b", "", i.categoria + (i.titulo ? ":" : "")), document.createTextNode(i.titulo ? " " + i.titulo : ""));
    b.append(texto);
    if (grande && i.quem) {
      const ini = el("span", "ini", i.quem.initials);
      ini.style.setProperty("--cor", i.quem.color);
      b.append(ini);
    }
    if (grande && i.feita && i.feita_por) b.append(el("span", "rmt-por", "feita · " + i.feita_por));
    return b;
  }

  function desenharMes(caixa, dados) {
    caixa.replaceChildren();
    const cab = el("div", "rmt-linha rmt-cabeca");
    for (const d of SEMANA) cab.append(el("div", "", d));
    caixa.append(cab);
    let n = 0;
    for (const semana of dados.semanas) {
      const linha = el("div", "rmt-linha");
      for (const d of semana) {
        const cel = el("div", "rmt-dia" + (d.fora ? " fora" : "") + (d.hoje ? " hoje" : "") + (d.fds ? " fds" : "") + (d.feriado ? " feriado" : ""));
        cel.style.setProperty("--i", n++);
        cel.append(el("span", "rmt-num", String(d.dia)));
        if (d.feriado) cel.append(el("span", "rmt-feriado", d.fds ? "Feriado" : d.feriado));
        if (!d.fora && !d.fds) for (const i of d.itens) cel.append(barra(i, false));
        linha.append(cel);
      }
      caixa.append(linha);
    }
    caixa.style.setProperty("--semanas", dados.semanas.length);
    // o que não cabe no quadradinho vira "+ N" (a TV nunca rola nem corta uma linha no meio)
    for (const cel of caixa.querySelectorAll(".rmt-dia")) {
      const itens = cel.querySelectorAll(".rmt-item");
      if (!itens.length || cel.scrollHeight <= cel.clientHeight) continue;
      const mais = el("div", "rmt-mais");
      cel.append(mais);
      let tirados = 0;
      for (let k = itens.length - 1; k >= 0 && cel.scrollHeight > cel.clientHeight; k--) {
        itens[k].remove();
        mais.textContent = "+ " + (++tirados);
      }
    }
  }

  function coluna(dia, classe, vazio) {
    const col = el("section", "rmt-col " + classe);
    const topo = el("header", "rmt-col-topo");
    topo.append(el("h2", "", dia.rotulo));
    col.append(topo);
    if (dia.feriado) col.append(el("div", "rmt-feriado-grande", "Feriado · " + dia.feriado));
    const lista = el("div", "rmt-lista");
    if (!dia.itens.length) lista.append(el("div", "vazio", vazio));
    for (const i of dia.itens) lista.append(barra(i, true));
    if (dia.itens.length > 8) lista.classList.add("muitos");
    col.append(lista);
    return col;
  }

  function desenharDia(caixa, dados) {
    caixa.replaceChildren();
    const hoje = coluna(dados.hoje, "rmt-hoje", "Nada no calendário hoje.");
    if (dados.hoje.total) {
      const conta = el("div", "rmt-conta");
      conta.append(el("strong", "", dados.hoje.feitas + " de " + dados.hoje.total), document.createTextNode(" feitas"));
      const trilho = el("div", "rmt-progresso");
      const cheio = el("div", "cheio");
      cheio.style.width = (100 * dados.hoje.feitas / dados.hoje.total) + "%";
      trilho.append(cheio);
      hoje.querySelector(".rmt-col-topo").append(conta);
      hoje.insertBefore(trilho, hoje.querySelector(".rmt-lista"));
    }
    hoje.querySelectorAll(".rmt-item").forEach((b, k) => b.style.setProperty("--i", k));
    caixa.append(hoje, coluna(dados.proximo, "rmt-proximo", "Nada no próximo dia útil."));
  }

  function rotuloFase(sec) {
    sec.querySelector(".rm-passo").textContent = fase === "mes" ? "o mês" : "o dia";
    sec.querySelector(".pagina").textContent = (fase === "mes" ? 1 : 2) + "/2";
  }

  function irPara(sec, nova, animar) {
    clearTimeout(timer);
    fase = nova;
    const palco = sec.querySelector(".rm-palco");
    const mes = sec.querySelector(".rm-mes");
    const zoom = sec.querySelector(".rm-zoom");
    palco.classList.toggle("sem-animacao", !animar);
    if (nova === "mes") {
      mes.style.transform = "";
      palco.classList.remove("no-dia");
    } else {
      // o quadradinho de hoje cresce até ocupar o palco (de onde ele está até o centro)
      const alvo = mes.querySelector(".rmt-dia.hoje") || mes.querySelector(".rmt-dia:not(.fora)");
      if (!animar) { mes.style.transform = ""; void mes.offsetWidth; }  // mede sem a escala de antes
      if (alvo) {
        const p = palco.getBoundingClientRect();
        const c = alvo.getBoundingClientRect();
        const atual = mes.getBoundingClientRect();
        const x = c.left - atual.left, y = c.top - atual.top;  // posição dentro do mês, sem a escala
        const escala = Math.min(p.width / c.width, p.height / c.height) * 0.92;
        const dx = (p.width - c.width * escala) / 2 - x * escala;
        const dy = (p.height - c.height * escala) / 2 - y * escala;
        mes.style.transform = "translate(" + dx + "px, " + dy + "px) scale(" + escala + ")";
      }
      palco.classList.add("no-dia");
    }
    zoom.setAttribute("aria-hidden", nova === "mes" ? "true" : "false");
    rotuloFase(sec);
  }

  HubTV.registrar("rotinas-mes", {
    desenhar(sec, dados, tudo) {
      const tela = (tudo && tudo.screens || []).find((t) => t.id === "rotinas-mes");
      if (tela) segundos = tela.seconds;
      sec.querySelector(".tela-titulo").textContent = dados.titulo;
      const json = JSON.stringify(dados);
      if (json === ultimo) return;  // nada mudou: não redesenha (no meio do zoom, piscaria)
      ultimo = json;
      desenharMes(sec.querySelector(".rm-mes"), dados);
      desenharDia(sec.querySelector(".rm-zoom"), dados);
      if (fase === "dia") irPara(sec, "dia", false);  // um dia que mudou: o zoom continua no lugar
      rotuloFase(sec);
    },
    aoMostrar(sec) {
      // começa sempre pelo mês, com os dias entrando em cascata, e marca a hora do zoom
      irPara(sec, "mes", false);
      const palco = sec.querySelector(".rm-palco");
      palco.classList.remove("entrando");
      void palco.offsetWidth;  // reinicia a animação de entrada
      palco.classList.add("entrando");
      if (HubTV.exportando) return;
      const espera = Math.min(10000, Math.max(3000, segundos * 400));
      timer = setTimeout(() => irPara(sec, "dia", true), espera);
    },
    pagina(sec) {
      irPara(sec, fase === "mes" ? "dia" : "mes", !HubTV.exportando);
    },
  });
})();
