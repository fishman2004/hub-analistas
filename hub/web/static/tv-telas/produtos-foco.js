// Tela "Produtos foco": clientes positivados em cada produto foco, em % da meta, do melhor para o pior.
// Se não couber tudo, passa as páginas com fade no mesmo tempo das colunas do Quadro (a TV nunca rola).
(function () {
  "use strict";
  const { el } = HubTV;
  const { textoPct, cabecalho, barra } = HubPainel;
  const FADE_MS = 450;
  let estado = { paginas: [], pagina: 0, escala: 150, esperado: 0 };
  let secao = null;
  let segundosPagina = 10;
  let ultimaTroca = Date.now();

  function linha(f) {
    const l = el("div", "linha-foco");
    const nome = el("div", "foco-nome");
    nome.append(el("span", "", f.nome));
    if (f.classe) nome.append(el("span", "foco-classe", f.classe));
    l.append(nome);
    l.append(barra(f.pct, f.tier, estado.escala, [
      { valor: estado.esperado, classe: "marca-esperado" },
      { valor: f.meta2, classe: "marca-meta2" },
    ]));
    l.append(el("div", "pct", textoPct(f.pct)));
    return l;
  }

  function desenharPagina() {
    const caixa = secao.querySelector(".focos");
    caixa.replaceChildren();
    for (const f of estado.paginas[estado.pagina] || []) caixa.append(linha(f));
    secao.querySelector(".pagina").textContent =
      estado.paginas.length > 1 ? (estado.pagina + 1) + "/" + estado.paginas.length : "";
  }

  setInterval(() => {
    if (!secao || !secao.classList.contains("ativa") || estado.paginas.length < 2) return;
    if (Date.now() - ultimaTroca < segundosPagina * 1000) return;
    ultimaTroca = Date.now();
    const caixa = secao.querySelector(".focos");
    caixa.classList.add("trocando");
    setTimeout(() => {
      estado.pagina = (estado.pagina + 1) % estado.paginas.length;
      desenharPagina();
      caixa.classList.remove("trocando");
    }, FADE_MS);
  }, 500);

  HubTV.registrar("produtos-foco", {
    desenhar(sec, dados, tudo) {
      secao = sec;
      segundosPagina = tudo.page_seconds || 10;
      cabecalho(sec, "Produtos foco", dados, true, dados.focos.some((f) => f.meta2 !== null));
      const caixa = sec.querySelector(".focos");
      if (caixa.classList.contains("trocando")) return;  // no meio do fade: atualiza no próximo ciclo
      estado.escala = Math.max(150, ...dados.focos.map((f) => Math.max(f.pct || 0, f.meta2 || 0) + 10));
      estado.esperado = dados.esperado;
      // mede quantas linhas cabem com uma linha de verdade
      caixa.replaceChildren(linha(dados.focos[0]));
      const alturaLinha = caixa.firstChild.getBoundingClientRect().height;
      const gap = parseFloat(getComputedStyle(caixa).rowGap) || 0;
      const cabem = Math.max(1, Math.floor((caixa.clientHeight + gap) / (alturaLinha + gap)));
      const paginas = [];
      for (let i = 0; i < dados.focos.length; i += cabem) paginas.push(dados.focos.slice(i, i + cabem));
      estado.paginas = paginas;
      estado.pagina = Math.min(estado.pagina, paginas.length - 1);
      desenharPagina();
    },
    aoMostrar() {
      estado.pagina = 0;
      ultimaTroca = Date.now();
      if (secao) desenharPagina();
    },
  });
})();
