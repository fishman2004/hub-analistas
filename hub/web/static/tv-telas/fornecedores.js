// Tela "Fornecedores das pastas": tudo o que saiu dos fornecedores de cada pasta, vendido por qualquer
// equipe (Televendas e outras pastas incluídas), contra a soma das metas desses fornecedores.
// No mês, a cor é o ritmo (com a marca do esperado); no dia, a meta do dia. Só porcentagens.
(function () {
  "use strict";
  const { el } = HubTV;
  const { textoPct, cabecalho, barra, letraPasta } = HubPainel;

  function barras(caixa, lista, campo, faixa, minimo, marcas) {
    caixa.replaceChildren();
    const escala = Math.max(minimo, ...lista.map((b) => (b[campo] || 0) + 10));
    for (const b of lista) {
      const linha = el("div", "linha-pasta" + (b.pasta === "T" ? " total" : ""));
      linha.append(letraPasta(b.pasta, b.pasta === "T" ? "Total" : b.pasta));
      linha.append(barra(b[campo], b[faixa], escala, marcas));
      linha.append(el("div", "pct", textoPct(b[campo])));
      caixa.append(linha);
    }
  }

  HubTV.registrar("fornecedores", {
    desenhar(sec, dados) {
      cabecalho(sec, "Fornecedores das pastas", dados, true);
      barras(sec.querySelector('[data-serie="mes"]'), dados.pastas, "pct", "tier", 120,
        [{ valor: dados.esperado, classe: "marca-esperado" }]);
      barras(sec.querySelector('[data-serie="dia"]'), dados.pastas, "dia", "dia_tier", 150);
    },
  });
})();
