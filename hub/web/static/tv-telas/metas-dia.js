// Tela "Metas do dia": quanto cada pasta fez da meta do dia (meta do mês dividida pelos dias úteis),
// em financeiro e em positivações. Só porcentagens.
(function () {
  "use strict";
  const { el } = HubTV;
  const { textoPct, cabecalho, barra } = HubPainel;

  function barras(caixa, lista) {
    caixa.replaceChildren();
    const escala = Math.max(150, ...lista.map((b) => (b.pct || 0) + 10));
    for (const b of lista) {
      const linha = el("div", "linha-pasta" + (b.pasta === "T" ? " total" : ""));
      linha.append(el("div", "letra", b.pasta === "T" ? "Total" : b.pasta));
      linha.append(barra(b.pct, b.tier, escala));
      linha.append(el("div", "pct", textoPct(b.pct)));
      caixa.append(linha);
    }
  }

  HubTV.registrar("metas-dia", {
    desenhar(sec, dados) {
      cabecalho(sec, "Metas do dia · " + dados.ate, dados, false);
      barras(sec.querySelector('[data-serie="financeiro"]'), dados.financeiro);
      barras(sec.querySelector('[data-serie="positivacao"]'), dados.positivacao);
    },
  });
})();
