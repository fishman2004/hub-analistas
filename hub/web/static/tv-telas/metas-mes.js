// Tela "Metas do mês": evolução do financeiro total no mês e um cartão por pasta (A a G e o total)
// para financeiro e positivações. Só porcentagens: a cor diz se o ritmo está bom.
(function () {
  "use strict";
  const { el } = HubTV;
  const { svg, textoPct, cabecalho, barra } = HubPainel;
  let ultimo = null;

  function evolucao(caixa, dias) {
    caixa.replaceChildren();
    const w = caixa.clientWidth, h = caixa.clientHeight;
    if (!w || !h) return;
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const esq = 3.6 * rem, baixo = 2.2 * rem, topo = 1.8 * rem;
    const reais = dias.filter((d) => d.real !== null).map((d) => d.real);
    const maximo = Math.max(100, ...reais) * 1.08;
    const y = (v) => topo + (h - topo - baixo) * (1 - v / maximo);
    const passo = (w - esq) / dias.length;
    const g = svg("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, role: "img",
      "aria-label": "Evolução do financeiro no mês, em porcentagem da meta" });
    for (const v of [25, 50, 75, 100]) {
      g.append(svg("line", { x1: esq, x2: w, y1: y(v), y2: y(v), class: v === 100 ? "grade grade-100" : "grade" }));
      g.append(svg("text", { x: esq - .6 * rem, y: y(v), class: "eixo", "text-anchor": "end", "dominant-baseline": "middle" }, v + "%"));
    }
    const largura = Math.max(2, passo * .62);
    let ultimo = null;
    dias.forEach((d, i) => {
      const cx = esq + passo * (i + .5);
      if (d.real !== null) {
        const topoBarra = y(d.real), alt = Math.max(0, y(0) - topoBarra);
        g.append(svg("rect", { x: cx - largura / 2, y: topoBarra, width: largura, height: alt, rx: Math.min(4, largura / 3),
          class: "dia faixa-" + d.tier + (d.util ? "" : " fim-de-semana") }));
        ultimo = { cx, topoBarra, d };
      }
      g.append(svg("text", { x: cx, y: h - .7 * rem, class: "eixo" + (d.util ? "" : " eixo-fds"), "text-anchor": "middle" }, String(d.dia)));
    });
    // a linha do esperado: onde o acumulado deveria estar em cada dia para fechar o mês em 100%
    const pontos = dias.map((d, i) => `${esq + passo * (i + .5)},${y(d.meta)}`).join(" ");
    g.append(svg("polyline", { points: pontos, class: "linha-esperado" }));
    if (ultimo) {
      g.append(svg("text", { x: ultimo.cx, y: ultimo.topoBarra - .5 * rem, class: "rotulo", "text-anchor": "middle" }, textoPct(ultimo.d.real)));
    }
    caixa.append(g);
  }

  function cartoes(caixa, lista, esperado) {
    caixa.replaceChildren();
    for (const c of lista) {
      const card = el("div", "cartao-pasta faixa-borda-" + c.tier + (c.pasta === "T" ? " total" : ""));
      card.append(el("div", "letra", c.pasta));  // "T" = total, como no painel do Excel
      card.append(el("div", "pct", textoPct(c.pct)));
      card.append(barra(c.pct, c.tier, 120, [{ valor: esperado, classe: "marca-esperado" }]));
      caixa.append(card);
    }
  }

  HubTV.registrar("metas-mes", {
    desenhar(sec, dados) {
      ultimo = dados;
      cabecalho(sec, "Metas do mês", dados, true);
      cartoes(sec.querySelector('[data-serie="financeiro"]'), dados.financeiro, dados.esperado);
      cartoes(sec.querySelector('[data-serie="positivacao"]'), dados.positivacao, dados.esperado);
      // o gráfico por último: ele mede o espaço que sobrou depois dos cartões
      evolucao(sec.querySelector(".grafico"), dados.evolucao);
    },
    aoMostrar(sec) {
      if (ultimo) evolucao(sec.querySelector(".grafico"), ultimo.evolucao);
    },
  });
})();
