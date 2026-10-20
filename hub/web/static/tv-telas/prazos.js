// Tela "Prazos da semana": atrasadas e o que vence nos próximos dias, um grupo por dia.
// Só entra na rotação quando há prazo na semana (o servidor decide).
(function () {
  "use strict";
  HubTV.registrar("prazos", {
    desenhar(sec, dados) {
      const area = sec.querySelector(".prazos");
      area.replaceChildren();
      const grupos = dados.groups.slice(0, 4);  // até 4 grupos lado a lado; a TV nunca rola
      area.style.setProperty("--grupos", grupos.length);
      for (const g of grupos) {
        const col = HubTV.el("section", "coluna" + (g.label === "Atrasadas" ? " grupo-atraso" : ""));
        const h = HubTV.el("h2", "", g.label + " ");
        h.append(HubTV.el("span", "contagem", String(g.cards.length)));
        const caixa = HubTV.el("div", "cartoes");
        col.append(h, caixa);
        area.append(col);
        HubTV.encaixar(caixa, g.cards);
      }
    },
  });
})();
