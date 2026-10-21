// Peças comuns das telas de painéis de dados (fase 5): cabeçalho, legenda e SVG.
// Regra do gestor: a TV mostra só gráficos e porcentagens. O servidor já manda só isso.
(function () {
  "use strict";
  const el = (...a) => HubTV.el(...a);
  const SVG = "http://www.w3.org/2000/svg";
  const FAIXAS = [["bom", "100% ou mais"], ["atencao", "80 a 99%"], ["alerta", "70 a 79%"], ["critico", "abaixo de 70%"]];

  function textoPct(p) { return p === null || p === undefined ? "—" : p + "%"; }

  function svg(tag, attrs, texto) {
    const e = document.createElementNS(SVG, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  // cabeçalho: título, período, "atualizado às" e o aviso de dados velhos; ritmo=true explica as cores do mês
  function cabecalho(sec, titulo, dados, ritmo) {
    const topo = sec.querySelector(".painel-topo");
    topo.replaceChildren();
    const esq = el("div", "painel-titulo");
    esq.append(el("h1", "tela-titulo", titulo));
    const info = el("span", "painel-info", dados.mes + " · vendas até " + dados.dia_semana + ", " + dados.ate);
    esq.append(info);
    if (dados.atualizado) esq.append(el("span", "painel-info", "atualizado " + (dados.atualizado.includes("/") ? "em " : "às ") + dados.atualizado));
    if (dados.velho) esq.append(el("span", "painel-velho", "Dados desatualizados"));
    topo.append(esq);
    const leg = el("div", "legenda");
    if (ritmo) leg.append(el("span", "legenda-nome", "Ritmo:"));
    for (const [faixa, nome] of FAIXAS) {
      const item = el("span", "legenda-item");
      item.append(el("i", "faixa-" + faixa), document.createTextNode(nome));
      leg.append(item);
    }
    if (ritmo) {
      const item = el("span", "legenda-item");
      item.append(el("i", "marca-esperado"), document.createTextNode("esperado até hoje (" + dados.esperado + "%)"));
      leg.append(item);
    }
    topo.append(leg);
  }

  // barra horizontal de 0 a "escala"% com a linha dos 100% e, se quiser, a marca do esperado
  function barra(valor, faixa, escala, marcas) {
    const trilho = el("div", "trilho");
    const cheio = el("div", "cheio faixa-" + faixa);
    cheio.style.width = Math.min(100, ((valor || 0) / escala) * 100) + "%";
    trilho.append(cheio);
    const cem = el("div", "linha-100");
    cem.style.left = (100 / escala) * 100 + "%";
    trilho.append(cem);
    for (const m of marcas || []) {
      if (m.valor === null || m.valor === undefined || m.valor > escala) continue;
      const marca = el("div", m.classe);
      marca.style.left = (m.valor / escala) * 100 + "%";
      trilho.append(marca);
    }
    return trilho;
  }

  // letra da pasta na cor padrão da empresa (tv.css: --pasta-A ...); o total, o Canal Farma e o Televendas (TLV) ficam neutros
  function letraPasta(pasta, texto) {
    const t = texto || pasta;
    return el("div", "letra pasta-" + (/^[A-G]$/.test(pasta) ? pasta : "T") + (t.length > 1 ? " longa" : ""), t);
  }

  window.HubPainel = { textoPct, svg, cabecalho, barra, letraPasta };
})();
