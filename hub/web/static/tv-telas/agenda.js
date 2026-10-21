// Tela "Agenda" (fase 13): hoje e os próximos dias úteis, um grupo por dia, com os compromissos
// da equipe, os feriados e quem está ausente. Sem descrição; reservado vem mascarado do servidor.
// Só entra na rotação quando há alguma coisa (o servidor decide). O que não couber vira "+ N".
(function () {
  "use strict";
  const { el } = HubTV;

  function linha(i) {
    const card = el("div", "ag-item ag-" + i.tipo + (i.reservado ? " reservada" : ""));
    card.append(el("div", "ag-hora", i.hora));
    const texto = el("div", "ag-texto");
    texto.append(el("div", "ag-titulo", i.tipo === "ausencia" ? i.nome + " · " + i.titulo : i.titulo));
    if (i.rotulo) texto.append(el("div", "ag-rotulo", i.rotulo));
    card.append(texto);
    const quem = el("div", "ag-quem");
    for (const p of i.pessoas || []) {
      const ini = el("span", "ini", p.initials);
      ini.style.setProperty("--cor", p.color);
      quem.append(ini);
    }
    card.append(quem);
    return card;
  }

  function encaixar(caixa, itens) {
    caixa.replaceChildren();
    for (let n = 0; n < itens.length; n++) {
      caixa.append(linha(itens[n]));
      if (caixa.scrollHeight > caixa.clientHeight && n > 0) {
        caixa.lastChild.remove();
        const resto = itens.length - n;
        caixa.append(el("div", "mais", "+ " + resto));
        while (caixa.scrollHeight > caixa.clientHeight && caixa.children.length > 2) {
          caixa.children[caixa.children.length - 2].remove();
          caixa.lastChild.textContent = "+ " + (itens.length - caixa.children.length + 1);
        }
        return;
      }
    }
  }

  HubTV.registrar("agenda", {
    desenhar(sec, dados) {
      const area = sec.querySelector(".agenda");
      area.replaceChildren();
      const grupos = dados.groups.slice(0, 4);  // até 4 dias lado a lado; a TV nunca rola
      area.style.setProperty("--grupos", grupos.length);
      for (const g of grupos) {
        const col = el("section", "coluna" + (g.label === "Hoje" ? " grupo-hoje" : ""));
        const h = el("h2", "", g.label + " ");
        h.append(el("span", "contagem", g.data));
        const caixa = el("div", "cartoes");
        col.append(h, caixa);
        area.append(col);
        encaixar(caixa, g.itens);
      }
    },
  });
})();
