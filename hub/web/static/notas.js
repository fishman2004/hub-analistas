// Nota aberta: grava sozinha uns segundos depois da última tecla (o botão Salvar continua valendo).
// Se a rede cair, avisa "não salvo" e tenta de novo; sair da página com algo sem salvar pede confirmação.
(function () {
  "use strict";
  const form = document.getElementById("nota");
  const aviso = document.getElementById("salvo");
  if (!form || !aviso) return;
  const ESPERA_MS = 3000;
  let timer = null;
  let sujo = false;
  let gravando = false;

  async function gravar() {
    if (gravando) { timer = setTimeout(gravar, ESPERA_MS); return; }
    gravando = true;
    sujo = false;
    try {
      const r = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Hub-Auto": "1" },
                                           signal: AbortSignal.timeout(8000) });
      const dados = await r.json();
      if (!r.ok) throw new Error(dados.erro || "erro");
      aviso.textContent = "Salvo às " + dados.salvo;
      aviso.classList.remove("atraso");
    } catch (e) {
      sujo = true;
      aviso.textContent = "Não salvo" + (e.message && e.message !== "erro" && !e.name.includes("Abort") ? ": " + e.message : " (sem conexão)") + ". Tentando de novo…";
      aviso.classList.add("atraso");
      timer = setTimeout(gravar, ESPERA_MS * 3);
    } finally {
      gravando = false;
    }
  }

  form.addEventListener("input", () => {
    sujo = true;
    aviso.textContent = "Editando…";
    clearTimeout(timer);
    timer = setTimeout(gravar, ESPERA_MS);
  });
  form.addEventListener("submit", () => { sujo = false; clearTimeout(timer); });
  window.addEventListener("beforeunload", (e) => { if (sujo) { e.preventDefault(); e.returnValue = ""; } });
})();
