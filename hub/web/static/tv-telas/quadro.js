// Tela "Quadro": as três colunas. Coluna com mais demandas do que cabem passa as páginas
// sozinha, com um fade, no tempo configurado (em vez de esconder o resto em "+ N").
(function () {
  "use strict";
  const FADE_MS = 450;
  const colunas = {};  // col -> { paginas, pagina }
  let segundosPagina = 10;
  let ultimaTroca = Date.now();

  function desenharColuna(sec, col) {
    const estado = colunas[col];
    const caixa = sec.querySelector(".cartoes");
    caixa.replaceChildren();
    const pagina = estado.paginas[estado.pagina] || [];
    if (!pagina.length) caixa.append(HubTV.el("div", "vazio", "Nada aqui."));
    for (const c of pagina) caixa.append(HubTV.cartao(c));
    sec.querySelector(".pagina").textContent =
      estado.paginas.length > 1 ? (estado.pagina + 1) + "/" + estado.paginas.length : "";
  }

  function trocarPaginas(secaoTela) {
    for (const sec of secaoTela.querySelectorAll(".coluna")) {
      const estado = colunas[sec.dataset.col];
      if (!estado || estado.paginas.length < 2) continue;
      const caixa = sec.querySelector(".cartoes");
      caixa.classList.add("trocando");
      setTimeout(() => {
        estado.pagina = (estado.pagina + 1) % estado.paginas.length;
        desenharColuna(sec, sec.dataset.col);
        caixa.classList.remove("trocando");
      }, FADE_MS);
    }
  }

  let secaoTela = null;
  setInterval(() => {
    // só passa as páginas com o Quadro na tela; ao voltar, ele recomeça da primeira (aoMostrar)
    if (secaoTela && secaoTela.classList.contains("ativa") && Date.now() - ultimaTroca >= segundosPagina * 1000) {
      ultimaTroca = Date.now();
      trocarPaginas(secaoTela);
    }
  }, 500);

  HubTV.registrar("quadro", {
    desenhar(sec, _dados, tudo) {
      secaoTela = sec;
      segundosPagina = tudo.page_seconds || 10;
      for (const coluna of sec.querySelectorAll(".coluna")) {
        const col = coluna.dataset.col;
        coluna.querySelector(".contagem").textContent = tudo.counts[col];
        const caixa = coluna.querySelector(".cartoes");
        if (caixa.classList.contains("trocando")) continue;  // no meio do fade: atualiza no próximo ciclo
        const paginas = HubTV.paginar(caixa, tudo.columns[col]);
        const anterior = colunas[col];
        colunas[col] = { paginas, pagina: anterior ? Math.min(anterior.pagina, Math.max(paginas.length - 1, 0)) : 0 };
        desenharColuna(coluna, col);
      }
    },
    aoMostrar(sec) {
      // quem olha para a TV vê as colunas desde a primeira página
      for (const col in colunas) colunas[col].pagina = 0;
      for (const coluna of sec.querySelectorAll(".coluna")) if (colunas[coluna.dataset.col]) desenharColuna(coluna, coluna.dataset.col);
      ultimaTroca = Date.now();
    },
  });
})();
