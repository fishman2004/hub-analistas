// Tela "Quadro": as três colunas. Coluna com mais demandas do que cabem passa as páginas
// sozinha, com um fade, no tempo configurado (em vez de esconder o resto em "+ N").
(function () {
  "use strict";
  const FADE_MS = 450;
  const colunas = {};  // col -> { paginas, pagina }
  let segundosPagina = 10;
  let ultimaTroca = Date.now();
  // fase 21: a demanda que acabou de chegar (ou de ser concluída) brilha na próxima vez que aparece na tela
  let vistas = null;  // id -> coluna no último desenho (null: primeiro desenho, nada brilha)
  const recentes = new Map();  // id -> { col, desde }

  function desenharColuna(sec, col) {
    const estado = colunas[col];
    const caixa = sec.querySelector(".cartoes");
    caixa.replaceChildren();
    const pagina = estado.paginas[estado.pagina] || [];
    const acabou = estado.pagina >= estado.paginas.length && estado.paginas.length > 0;  // PDF: coluna já terminou
    if (!pagina.length) caixa.append(HubTV.el("div", "vazio", acabou ? "Fim da coluna." : "Nada aqui."));
    const ativa = sec.closest(".tela").classList.contains("ativa") && !HubTV.exportando;
    for (const c of pagina) {
      const card = HubTV.cartao(c);
      const r = recentes.get(c.id);
      if (ativa && r && r.col === col) {
        card.classList.add(col === "done" ? "comemora" : "chegou");
        recentes.delete(c.id);
      }
      caixa.append(card);
    }
    sec.querySelector(".pagina").textContent =
      estado.paginas.length > 1 && !acabou ? (estado.pagina + 1) + "/" + estado.paginas.length : "";
  }

  function trocarPaginas(secaoTela, direcao = 1) {
    for (const sec of secaoTela.querySelectorAll(".coluna")) {
      const estado = colunas[sec.dataset.col];
      if (!estado || (HubTV.exportando ? estado.pagina >= estado.paginas.length : estado.paginas.length < 2)) continue;
      const caixa = sec.querySelector(".cartoes");
      caixa.classList.add("trocando");
      setTimeout(() => {
        // no PDF, cada página sai uma vez: a coluna que acabou fica vazia em vez de voltar à primeira
        estado.pagina = HubTV.exportando ? estado.pagina + direcao
          : (estado.pagina + direcao + estado.paginas.length) % estado.paginas.length;
        desenharColuna(sec, sec.dataset.col);
        caixa.classList.remove("trocando");
      }, FADE_MS);
    }
  }

  let secaoTela = null;
  setInterval(() => {
    // só passa as páginas com o Quadro na tela; ao voltar, ele recomeça da primeira (aoMostrar)
    // com a TV pausada (fase 10), a página fica a que está: quem passa é a seta ↑ ↓ ou o app
    if (secaoTela && secaoTela.classList.contains("ativa") && !HubTV.pausada()
        && Date.now() - ultimaTroca >= segundosPagina * 1000) {
      ultimaTroca = Date.now();
      trocarPaginas(secaoTela);
    }
  }, 500);

  HubTV.registrar("quadro", {
    desenhar(sec, _dados, tudo) {
      secaoTela = sec;
      segundosPagina = tudo.page_seconds || 10;
      const agora = Date.now();
      const novas = {};
      for (const col of ["todo", "doing", "done"]) {
        for (const c of tudo.columns[col]) {
          novas[c.id] = col;
          if (vistas && vistas[c.id] !== col && (col === "done" || vistas[c.id] === undefined)) recentes.set(c.id, { col, desde: agora });
        }
      }
      vistas = novas;
      for (const [id, r] of recentes) if (agora - r.desde > 60000) recentes.delete(id);
      for (const coluna of sec.querySelectorAll(".coluna")) {
        const col = coluna.dataset.col;
        coluna.querySelector(".contagem").textContent = tudo.counts[col];
        const caixa = coluna.querySelector(".cartoes");
        if (caixa.classList.contains("trocando")) continue;  // no meio do fade: atualiza no próximo ciclo
        const paginas = HubTV.paginar(caixa, tudo.columns[col]);
        const anterior = colunas[col];
        let pagina = anterior ? Math.min(anterior.pagina, Math.max(paginas.length - 1, 0)) : 0;
        // a demanda que acabou de chegar aqui puxa a coluna para a página dela, para a comemoração aparecer
        const nova = paginas.findIndex((p) => p.some((c) => (recentes.get(c.id) || {}).col === col));
        if (nova >= 0 && sec.classList.contains("ativa") && !HubTV.exportando) pagina = nova;
        colunas[col] = { paginas, pagina };
        desenharColuna(coluna, col);
      }
    },
    pagina(sec, direcao) {  // pausada: seta ↑ ↓ na TV ou "Página seguinte" no app
      ultimaTroca = Date.now();
      trocarPaginas(sec, direcao);
    },
    aoMostrar(sec) {
      // quem olha para a TV vê as colunas desde a primeira página
      for (const col in colunas) colunas[col].pagina = 0;
      for (const coluna of sec.querySelectorAll(".coluna")) if (colunas[coluna.dataset.col]) desenharColuna(coluna, coluna.dataset.col);
      ultimaTroca = Date.now();
    },
  });
})();
