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

  function item(i) {
    const card = el("div", "prio-item" + (i.done ? " feita" : "") + (i.late ? " atrasada" : ""));
    const marca = el("span", "prio-marca");
    if (i.done) marca.innerHTML = CHECK;  // só o ícone fixo; o texto vindo do servidor entra por textContent
    card.append(marca);
    const texto = el("div", "prio-texto");
    texto.append(el("div", "prio-titulo", i.title));
    if (i.due_day && !i.done) texto.append(el("div", "prio-prazo", (i.late ? "atrasada · " : "") + "até dia " + i.due_day));
    card.append(texto);
    if (i.folders && i.folders.length > 1) {
      // por pasta (fase 16): cada pasta com o check e as iniciais de quem fez, ou apagada enquanto falta
      const pastas = el("div", "prio-pastas");
      for (const f of i.folders) {
        const chip = el("span", "prio-pasta" + (f.done ? " feita" : ""));
        chip.append(el("span", "letra pasta-" + f.folder, f.folder));
        if (f.done && f.initials) {
          const ini = el("span", "ini", f.initials);
          ini.style.setProperty("--cor", f.color);
          chip.append(ini);
        }
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
