// Tela "Produtos foco": para cada produto foco, a positivação (META) e o financeiro (META II), em %
// da meta, do melhor para o pior.
// Se não couber tudo, passa as páginas com fade no mesmo tempo das colunas do Quadro (a TV nunca rola).
(function () {
  "use strict";
  const { el } = HubTV;
  const { textoPct, cabecalho, barra } = HubPainel;
  const FADE_MS = 450;
  let estado = { paginas: [], pagina: 0, escalas: [120, 120], esperado: 0 };
  let secao = null;
  let segundosPagina = 10;
  let ultimaTroca = Date.now();

  function linha(f) {
    const l = el("div", "linha-foco");
    const nome = el("div", "foco-nome");
    nome.append(el("span", "", f.nome));
    if (f.classe) nome.append(el("span", "foco-classe", f.classe));
    l.append(nome);
    [[f.pos, f.pos_tier], [f.fin, f.fin_tier]].forEach(([valor, faixa], i) => {
      const lado = el("div", "foco-lado" + (valor === null ? " sem-meta" : ""));
      lado.append(barra(valor, faixa, estado.escalas[i], [{ valor: estado.esperado, classe: "marca-esperado" }]));
      lado.append(el("div", "pct", textoPct(valor)));
      l.append(lado);
    });
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
    if (!secao || !secao.classList.contains("ativa") || estado.paginas.length < 2 || HubTV.pausada()) return;
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
      cabecalho(sec, "Produtos foco", dados, true);
      const caixa = sec.querySelector(".focos");
      if (caixa.classList.contains("trocando")) return;  // no meio do fade: atualiza no próximo ciclo
      // cada coluna com a própria escala: um financeiro de 300% não esmaga as barras de positivação
      estado.escalas = ["pos", "fin"].map((k) => Math.max(120, ...dados.focos.map((f) => (f[k] || 0) + 10)));
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
