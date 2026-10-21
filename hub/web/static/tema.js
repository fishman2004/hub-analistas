// Tema do app: automático (segue o Windows), claro ou escuro, salvo no navegador de cada pessoa.
// Carrega no <head>, antes de desenhar a página, para não piscar o tema errado.
// A TV não usa este arquivo: ela tem o tema próprio.
(function () {
  "use strict";
  const CHAVE = "hub-tema";
  const ORDEM = ["auto", "claro", "escuro"];
  const NOMES = { auto: "automático", claro: "claro", escuro: "escuro" };
  const raiz = document.documentElement;

  function ler() {
    try {
      const t = localStorage.getItem(CHAVE);
      return ORDEM.includes(t) ? t : "auto";
    } catch (e) {
      return "auto";  // navegador sem armazenamento: fica no automático, sem quebrar
    }
  }

  function salvar(t) {
    try { localStorage.setItem(CHAVE, t); } catch (e) { /* vale só até recarregar */ }
  }

  function aplicar(t) {
    if (t === "auto") raiz.removeAttribute("data-tema");
    else raiz.setAttribute("data-tema", t);
  }

  let atual = ler();
  aplicar(atual);

  document.addEventListener("DOMContentLoaded", () => {
    const botao = document.getElementById("tema");
    if (!botao) return;
    const mostrar = () => {
      botao.textContent = "Tema: " + NOMES[atual];
      botao.title = "Trocar o tema (automático, claro ou escuro)";
    };
    mostrar();
    botao.hidden = false;  // sem JavaScript o botão não faria nada, então só aparece aqui
    botao.addEventListener("click", () => {
      atual = ORDEM[(ORDEM.indexOf(atual) + 1) % ORDEM.length];
      aplicar(atual);
      salvar(atual);
      mostrar();
    });
  });
})();
