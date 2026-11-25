// Tema do app: automático (segue o Windows), claro ou escuro, salvo no navegador de cada pessoa.
// Carrega no <head>, antes de desenhar a página, para não piscar o tema errado.
// A TV não usa este arquivo: ela tem o tema próprio.
// Fase 27: mais duas opções, "Natal" (vermelho, claro) e "Natal preto", que vestem o tema de Natal (natal.css e
// natal.js) mesmo fora da época. Na época (1º/12 a 6/1, ou ligado em Configurações), o servidor já põe a
// classe "natal" no <html> para todo mundo, e as outras opções escolhem só o claro ou o escuro dele.
(function () {
  "use strict";
  const CHAVE = "hub-tema";
  const ORDEM = ["auto", "claro", "escuro", "natal", "natal-preto"];
  const NOMES = { auto: "automático", claro: "claro", escuro: "escuro", natal: "Natal", "natal-preto": "Natal preto" };
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

  const epoca = raiz.classList.contains("natal");  // o servidor ligou o Natal para todos
  const natalino = (t) => epoca || t.startsWith("natal");

  function aplicar(t) {
    if (t === "auto") raiz.removeAttribute("data-tema");
    else raiz.setAttribute("data-tema", t);
    raiz.classList.toggle("natal", natalino(t));
  }

  let atual = ler();
  aplicar(atual);

  document.addEventListener("DOMContentLoaded", () => {
    const botao = document.getElementById("tema");
    if (!botao) return;
    const mostrar = () => {
      botao.textContent = "Tema: " + NOMES[atual];
      botao.title = "Trocar o tema (automático, claro, escuro, Natal ou Natal preto)";
    };
    mostrar();
    botao.hidden = false;  // sem JavaScript o botão não faria nada, então só aparece aqui
    botao.addEventListener("click", () => {
      const antes = natalino(atual);
      atual = ORDEM[(ORDEM.indexOf(atual) + 1) % ORDEM.length];
      salvar(atual);
      // entrou ou saiu do Natal: recarrega, para a neve, as luzinhas e os sons começarem (ou pararem) certinhos
      if (natalino(atual) !== antes) { location.reload(); return; }
      aplicar(atual);
      mostrar();
    });
  });
})();
