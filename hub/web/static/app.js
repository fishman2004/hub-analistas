// Quadro do analista: recarrega o trecho do quadro (presença + colunas) a cada 10 s.
// Fica só nesta página: nos formulários nada se atualiza sozinho, para não apagar o que se digita.
// Fase 21: o cartão que chegou ou mudou de coluna (e o bloco da trilha que acendeu) brilha um instante (hub.js).
(function () {
  "use strict";
  const quadro = document.getElementById("quadro");
  if (!quadro) return;
  let atual = null;
  setInterval(async () => {
    if (document.hidden) return;
    // alguém escrevendo uma justificativa (ou com uma caixinha aberta): não troca nada até terminar
    const foco = document.activeElement;
    if (quadro.querySelector("details[open]") || (quadro.contains(foco) && /^(TEXTAREA|INPUT|SELECT)$/.test(foco.tagName))) return;
    try {
      const r = await fetch(quadro.dataset.parcial, { cache: "no-store", signal: AbortSignal.timeout(8000) });
      if (!r.ok) return;
      const html = await r.text();
      // só troca se algo mudou: trocar à toa tira o foco e pode engolir um clique
      if (html !== atual) {
        const antes = window.HubVivo ? window.HubVivo.foto(quadro) : null;
        quadro.innerHTML = html;  // HTML do próprio servidor, já escapado
        if (window.HubVivo) window.HubVivo.atualizou(quadro, antes);
      }
      atual = html;
    } catch (e) {
      // sem rede: mantém o que está na tela e tenta de novo no próximo ciclo
    }
  }, 10000);
})();
