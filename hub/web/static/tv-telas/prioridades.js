// Tela "Prioridades do mês": a lista do início do mês como checklist, com quantas já foram feitas.
// Só entra na rotação enquanto houver item em aberto (o servidor decide). Os em aberto aparecem em
// destaque (os atrasados primeiro, em vermelho); os feitos levam o check e as iniciais de quem fez.
// Com as pastas ligadas às pessoas, cada item mostra as pastas que já fizeram e as que faltam.
// Tudo cabendo, uma coluna; senão, duas e, se ainda não couber, passa as páginas com fade no mesmo
// tempo das colunas do Quadro (a TV nunca rola).
(function () {
  "use strict";
  const { el } = HubTV;
  const FADE_MS = 450;
  const CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  let estado = { paginas: [], pagina: 0 };
  let secao = null;
  let segundosPagina = 10;
  let ultimaTroca = Date.now();

  const cabe = (caixa) => caixa.scrollHeight <= caixa.clientHeight;

  function etapas(i) {
    // item com etapas (Metas do mês), à parte: etapas nas linhas, pastas nas colunas; a pasta que
    // concluiu tem a coluna destacada. Ocupa a largura toda, mesmo com a lista em duas colunas.
    const card = el("div", "prio-tabela" + (i.late ? " atrasada" : ""));
    const topo = el("div", "prio-tabela-topo");
    topo.append(el("div", "prio-titulo", i.title));
    const feitas = i.folders.filter((f) => f.done).length;
    topo.append(el("div", "prio-prazo", feitas + " de " + i.folders.length + " pastas concluíram" +
      (i.due_day ? " · " + (i.late ? "atrasada · " : "") + "até dia " + i.due_day : "")));
    card.append(topo);
    const grade = el("div", "etapas-grade");
    grade.style.gridTemplateColumns = "minmax(0, 1fr) repeat(" + i.folders.length + ", 4.6rem)";
    grade.append(el("span", "cab"));
    for (const f of i.folders) {
      const cab = el("span", "cab col" + (f.done ? " concluida" : ""));
      cab.append(el("span", "letra pasta-" + f.folder, f.folder));
      grade.append(cab);
    }
    i.steps.forEach((nome, n) => {
      const ultima = n === i.steps.length - 1;
      const rot = el("span", "etapa" + (ultima ? " ultima" : ""));
      rot.append(el("span", "num", String(n + 1)), document.createTextNode(nome));
      grade.append(rot);
      for (const f of i.folders) {
        const cel = el("span", "cel col" + (f.done ? " concluida" : "") + (f.steps[n] ? " sim" : " nao") + (ultima ? " ultima" : ""));
        if (f.steps[n]) cel.innerHTML = CHECK;
        else cel.textContent = "✕";
        grade.append(cel);
      }
    });
    card.append(grade);
    return card;
  }

  function item(i) {
    if (i.steps && i.folders) return etapas(i);
    const card = el("div", "prio-item" + (i.done ? " feita" : "") + (i.late ? " atrasada" : ""));
    const marca = el("span", "prio-marca");
    if (i.done) marca.innerHTML = CHECK;  // só o ícone fixo; o texto vindo do servidor entra por textContent
    card.append(marca);
    const texto = el("div", "prio-texto");
    texto.append(el("div", "prio-titulo", i.title));
    if (i.due_day && !i.done) texto.append(el("div", "prio-prazo", (i.late ? "atrasada · " : "") + "até dia " + i.due_day));
    card.append(texto);
    if (i.folders && i.folders.length > 1) {
      // por pasta (fase 16): a pasta que concluiu fica acesa com o check, a que falta fica apagada
      const pastas = el("div", "prio-pastas");
      for (const f of i.folders) {
        const chip = el("span", "prio-pasta" + (f.done ? " feita" : ""));
        chip.append(el("span", "letra pasta-" + f.folder, f.folder));
        if (f.done) chip.insertAdjacentHTML("beforeend", '<span class="ok">' + CHECK + "</span>");
        pastas.append(chip);
      }
      card.append(pastas);
      return card;
    }
    if (i.folder) card.append(el("span", "letra pasta-" + i.folder, i.folder));
    if (i.done && i.initials) {
      const ini = el("span", "ini", i.initials);
      ini.style.setProperty("--cor", i.color);
      card.append(ini);
    }
    return card;
  }

  function paginar(caixa, itens) {
    // acrescenta enquanto cabe, medindo de verdade; o que não couber vai para a página seguinte
    const paginas = [];
    let n = 0;
    while (n < itens.length) {
      caixa.replaceChildren();
      const pagina = [];
      while (n < itens.length) {
        caixa.append(item(itens[n]));
        if (!cabe(caixa) && pagina.length) { caixa.lastChild.remove(); break; }
        pagina.push(itens[n]);
        n++;
      }
      paginas.push(pagina);
    }
    return paginas;
  }

  function desenharPagina() {
    const caixa = secao.querySelector(".prio-itens");
    caixa.replaceChildren(...(estado.paginas[estado.pagina] || []).map(item));
    secao.querySelector(".prio-conta .pagina").textContent =
      estado.paginas.length > 1 ? (estado.pagina + 1) + "/" + estado.paginas.length : "";
  }

  setInterval(() => {
    if (!secao || !secao.classList.contains("ativa") || estado.paginas.length < 2 || HubTV.pausada()) return;
    if (Date.now() - ultimaTroca < segundosPagina * 1000) return;
    ultimaTroca = Date.now();
    const caixa = secao.querySelector(".prio-itens");
    caixa.classList.add("trocando");
    setTimeout(() => {
      estado.pagina = (estado.pagina + 1) % estado.paginas.length;
      desenharPagina();
      caixa.classList.remove("trocando");
    }, FADE_MS);
  }, 500);

  HubTV.registrar("prioridades", {
    desenhar(sec, dados, tudo) {
      secao = sec;
      segundosPagina = tudo.page_seconds || 10;
      sec.querySelector(".tela-titulo").textContent = "Prioridades de " + dados.month;
      const conta = sec.querySelector(".prio-conta");
      conta.replaceChildren(document.createTextNode(dados.done_count + " de " + dados.total + " feitas"));
      if (dados.late_count) {
        conta.append(el("span", "atraso", " · " + dados.late_count + (dados.late_count === 1 ? " atrasada" : " atrasadas")));
      }
      conta.append(el("span", "pagina"));
      sec.querySelector(".prio-barra .cheio").style.width = (dados.total ? (100 * dados.done_count) / dados.total : 0) + "%";
      const caixa = sec.querySelector(".prio-itens");
      if (caixa.classList.contains("trocando")) return;  // no meio do fade: atualiza no próximo ciclo
      caixa.classList.remove("duas");
      caixa.replaceChildren(...dados.items.map(item));
      if (!cabe(caixa)) caixa.classList.add("duas");
      estado.paginas = paginar(caixa, dados.items);
      estado.pagina = Math.min(estado.pagina, estado.paginas.length - 1);
      desenharPagina();
    },
    pagina(sec, direcao) {  // pausada: seta ↑ ↓ na TV; na exportação em PDF, cada página vira uma folha
      ultimaTroca = Date.now();
      if (estado.paginas.length < 2) return;
      estado.pagina = (estado.pagina + direcao + estado.paginas.length) % estado.paginas.length;
      desenharPagina();
    },
    aoMostrar() {
      estado.pagina = 0;
      ultimaTroca = Date.now();
      if (secao) desenharPagina();
    },
  });
})();
