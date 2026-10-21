// Tela "Metas do mês": evolução do financeiro total (cada dia e o acumulado do mês) e um cartão por pasta (A a G e o total)
// para financeiro e positivações. Só porcentagens: a cor diz se o ritmo está bom.
(function () {
  "use strict";
  const { el } = HubTV;
  const { svg, textoPct, cabecalho, barra, letraPasta } = HubPainel;
  let ultimo = null;

  // barras: quanto cada dia fez da meta do dia; linha: o acumulado do mês contra o que já devia ter
  // sido feito. As duas usam a mesma régua: 100% é estar na meta.
  function evolucao(caixa, dias, acumulado) {
    caixa.replaceChildren();
    const w = caixa.clientWidth, h = caixa.clientHeight;
    if (!w || !h) return;
    const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
    const esq = 3.6 * rem, baixo = 2.2 * rem, topo = 2.4 * rem;
    const valores = dias.flatMap((d) => [d.real, d.ritmo]).filter((v) => v !== null);
    const maximo = Math.max(100, ...valores) * 1.08;
    const y = (v) => topo + (h - topo - baixo) * (1 - v / maximo);
    const passo = (w - esq) / dias.length;
    const g = svg("svg", { width: w, height: h, viewBox: `0 0 ${w} ${h}`, role: "img",
      "aria-label": "Financeiro de cada dia contra a meta do dia e acumulado do mês contra o esperado, em porcentagem" });
    for (const v of [25, 50, 75, 100]) {
      g.append(svg("line", { x1: esq, x2: w, y1: y(v), y2: y(v), class: v === 100 ? "grade grade-100" : "grade" }));
      g.append(svg("text", { x: esq - .6 * rem, y: y(v), class: "eixo", "text-anchor": "end", "dominant-baseline": "middle" }, v + "%"));
    }
    const largura = Math.max(2, passo * .62);
    const x = (i) => esq + passo * (i + .5);
    let barra = null, ponto = null;
    dias.forEach((d, i) => {
      if (d.real !== null) {
        const topoBarra = y(d.real), alt = Math.max(0, y(0) - topoBarra);
        g.append(svg("rect", { x: x(i) - largura / 2, y: topoBarra, width: largura, height: alt, rx: Math.min(4, largura / 3),
          class: "dia faixa-" + d.tier }));
        barra = { cx: x(i), topoBarra, d };
      }
      if (d.ritmo !== null) ponto = { cx: x(i), cy: y(d.ritmo) };
      g.append(svg("text", { x: x(i), y: h - .7 * rem, class: "eixo" + (d.util ? "" : " eixo-fds"), "text-anchor": "middle" }, String(d.dia)));
    });
    const pontos = dias.map((d, i) => (d.ritmo === null ? null : `${x(i)},${y(d.ritmo)}`)).filter(Boolean).join(" ");
    if (pontos) {
      g.append(svg("polyline", { points: pontos, class: "linha-mes-fundo" }));  // contorno: a linha aparece por cima das barras
      g.append(svg("polyline", { points: pontos, class: "linha-mes" }));
    }
    if (barra) {
      // o rótulo do dia vai acima da barra e do ponto da linha, para um não cobrir o outro
      const alto = Math.min(barra.topoBarra, ponto && ponto.cx === barra.cx ? ponto.cy - .4 * rem : Infinity);
      g.append(svg("text", { x: barra.cx, y: alto - .6 * rem, class: "rotulo", "text-anchor": "middle" }, textoPct(barra.d.real)));
    }
    if (ponto) {
      g.append(svg("circle", { cx: ponto.cx, cy: ponto.cy, r: .45 * rem, class: "ponto-mes" }));
      // à direita do último ponto (onde ainda não há barras): quanto do mês já foi feito
      g.append(svg("text", { x: ponto.cx + 1.2 * rem, y: ponto.cy, class: "rotulo rotulo-mes", "text-anchor": "start",
        "dominant-baseline": "middle" }, "mês " + textoPct(acumulado)));
    }
    caixa.append(g);
  }

  function cartoes(caixa, lista, esperado) {
    caixa.replaceChildren();
    for (const c of lista) {
      const card = el("div", "cartao-pasta faixa-borda-" + c.tier + (c.pasta === "T" ? " total" : ""));
      card.append(letraPasta(c.pasta));  // "T" = total da Polybalas, como no painel do Excel
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
      evolucao(sec.querySelector(".grafico"), dados.evolucao, dados.acumulado);
    },
    aoMostrar(sec) {
      if (ultimo) evolucao(sec.querySelector(".grafico"), ultimo.evolucao, ultimo.acumulado);
    },
  });
})();
