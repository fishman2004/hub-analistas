// O que vale em todas as páginas do app (fase 21). Tudo aqui é um extra: sem este script o Hub funciona igual.
// - menu: o grupo aberto fecha ao clicar fora ou com Esc; no celular, o grupo da página atual já abre
// - "Ir para…" (Ctrl+K): uma caixinha para pular para qualquer página digitando
// - avisos de sucesso: viram um aviso no canto, com uma barrinha de tempo, que some sozinho
// - formulários: o botão mostra que está enviando e um segundo clique não manda de novo
// - "vivo": o que mudou desde a última vez que a página apareceu brilha um instante (cartões do quadro,
//   blocos da trilha); usado também pelo app.js na atualização de 10 s do quadro
// - números que contam até o valor ([data-contar])
(function () {
  "use strict";
  const calmo = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const celular = window.matchMedia("(max-width: 760px)");

  // ---------- menu ----------
  const grupos = [...document.querySelectorAll(".topo .grupo")];
  for (const g of grupos) {
    g.addEventListener("toggle", () => {
      if (g.open && !celular.matches) for (const o of grupos) if (o !== g) o.open = false;
    });
  }
  document.addEventListener("click", (e) => {
    if (celular.matches) return;
    for (const g of grupos) if (g.open && !g.contains(e.target)) g.open = false;
  });
  // a caixinha da justificativa na trilha fecha ao clicar fora dela ou com Esc
  document.addEventListener("click", (e) => {
    for (const d of document.querySelectorAll("details.tr-just[open]")) {
      if (!d.querySelector(".tr-just-caixa").contains(e.target) && !d.querySelector("summary").contains(e.target)) d.open = false;
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") for (const d of document.querySelectorAll("details.tr-just[open]")) d.open = false;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const aberto = grupos.find((g) => g.open);
    if (aberto && !celular.matches) { aberto.open = false; aberto.querySelector("summary").focus(); }
  });
  if (celular.matches) for (const g of grupos) if (g.classList.contains("aqui")) g.open = true;

  // ---------- Ir para… (Ctrl+K) ----------
  const EXTRAS = [
    ["Nova demanda", "/demandas/nova"], ["Montar minha trilha", "/trilha/montar"],
    ["Rotinas do mês", "/calendario?visao=rotinas"], ["Trocar meu PIN", "/meu-pin"],
  ];
  const semAcento = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const nav = document.querySelector(".topo nav");
  let caixa = null;

  function destinos() {
    const vistos = new Set();
    const lista = [];
    for (const a of nav.querySelectorAll("a[href]")) {
      const grupo = a.closest(".grupo");
      const nome = a.firstChild.textContent.trim();
      lista.push([nome, a.getAttribute("href"), grupo ? grupo.querySelector("summary").firstChild.textContent.trim() : ""]);
    }
    for (const [nome, href] of EXTRAS) lista.push([nome, href, "Atalho"]);
    return lista.filter(([, href]) => !vistos.has(href) && vistos.add(href));
  }

  function montarCaixa() {
    const dlg = document.createElement("dialog");
    dlg.className = "ir-para";
    dlg.setAttribute("aria-label", "Ir para uma página");
    dlg.innerHTML = '<form method="dialog"><input type="search" placeholder="Ir para… (digite o nome da página)" ' +
      'aria-label="Página" autocomplete="off"><ul role="listbox"></ul><p class="ir-para-dica">' +
      "<kbd>↑</kbd> <kbd>↓</kbd> escolher · <kbd>Enter</kbd> abrir · <kbd>Esc</kbd> fechar</p></form>";
    document.body.append(dlg);
    const campo = dlg.querySelector("input");
    const ul = dlg.querySelector("ul");
    const todos = destinos();
    let marcado = 0;
    let vistos = todos;

    function desenhar() {
      const q = semAcento(campo.value.trim());
      vistos = todos.filter(([nome, , grupo]) => !q || semAcento(nome + " " + grupo).includes(q));
      marcado = Math.min(marcado, Math.max(vistos.length - 1, 0));
      ul.replaceChildren(...vistos.map(([nome, href, grupo], i) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", i === marcado ? "true" : "false");
        const a = document.createElement("a");
        a.href = href;
        a.textContent = nome;
        if (grupo) { const s = document.createElement("small"); s.textContent = grupo; a.append(s); }
        li.append(a);
        li.addEventListener("mousemove", () => { if (marcado !== i) { marcado = i; marcar(); } });
        return li;
      }));
      if (!vistos.length) {
        const li = document.createElement("li");
        li.className = "vazio";
        li.textContent = "Nenhuma página com esse nome.";
        ul.append(li);
      }
    }
    function marcar() {
      [...ul.children].forEach((li, i) => li.setAttribute("aria-selected", i === marcado ? "true" : "false"));
      const atual = ul.children[marcado];
      if (atual) atual.scrollIntoView({ block: "nearest" });
    }
    campo.addEventListener("input", () => { marcado = 0; desenhar(); });
    campo.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!vistos.length) return;
        marcado = (marcado + (e.key === "ArrowDown" ? 1 : -1) + vistos.length) % vistos.length;
        marcar();
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (vistos[marcado]) window.location.href = vistos[marcado][1];
      }
    });
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });  // clique fora da caixa
    dlg.abrir = () => { campo.value = ""; marcado = 0; desenhar(); dlg.showModal(); campo.focus(); };
    return dlg;
  }

  function abrirIrPara() {
    if (!nav || typeof HTMLDialogElement === "undefined") return;
    caixa = caixa || montarCaixa();
    if (!caixa.open) caixa.abrir();
  }
  if (nav) {
    const botao = document.getElementById("ir-para-abrir");
    if (botao) { botao.hidden = false; botao.addEventListener("click", abrirIrPara); }
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") { e.preventDefault(); abrirIrPara(); }
    });
  }

  // ---------- avisos de sucesso ----------
  const TEMPO_AVISO = 6000;
  const sucessos = [...document.querySelectorAll("main .sucesso")];
  if (sucessos.length) {
    const pilha = document.createElement("div");
    pilha.className = "avisos-pilha";
    document.body.append(pilha);
    for (const s of sucessos) {
      s.classList.add("aviso-flutuante");
      s.style.setProperty("--tempo", TEMPO_AVISO + "ms");
      const fechar = document.createElement("button");
      fechar.type = "button";
      fechar.className = "aviso-fechar";
      fechar.setAttribute("aria-label", "Fechar o aviso");
      fechar.textContent = "×";
      const barra = document.createElement("span");
      barra.className = "aviso-tempo";
      s.append(fechar, barra);
      pilha.append(s);
      let restante = TEMPO_AVISO;
      let inicio = Date.now();
      let timer = null;
      const sair = () => {
        clearTimeout(timer);
        s.classList.add("saindo");
        setTimeout(() => s.remove(), calmo ? 0 : 300);
      };
      const contar = () => { inicio = Date.now(); timer = setTimeout(sair, restante); };
      s.addEventListener("mouseenter", () => { clearTimeout(timer); restante -= Date.now() - inicio; s.classList.add("parado"); });
      s.addEventListener("mouseleave", () => { s.classList.remove("parado"); contar(); });
      fechar.addEventListener("click", sair);
      contar();
    }
  }

  // ---------- formulários: um envio só ----------
  document.addEventListener("submit", (e) => {
    const form = e.target;
    if (e.defaultPrevented || form.method === "dialog") return;
    if (form.dataset.enviando) { e.preventDefault(); return; }
    form.dataset.enviando = "1";
    const botao = e.submitter || form.querySelector("button:not([type=button])");
    if (botao) { botao.classList.add("enviando"); botao.setAttribute("aria-busy", "true"); }
  });
  window.addEventListener("pageshow", () => {  // voltar pelo navegador: o formulário volta a funcionar
    for (const f of document.querySelectorAll("form[data-enviando]")) delete f.dataset.enviando;
    for (const b of document.querySelectorAll(".enviando")) { b.classList.remove("enviando"); b.removeAttribute("aria-busy"); }
  });

  // ---------- vivo: o que mudou acende ----------
  // Cada elemento com data-vivo (a chave) e data-estado (a situação). A foto fica no sessionStorage da página
  // por 10 minutos: depois de um clique em "Concluir", a página recarrega e o cartão que mudou brilha.
  const busca = new URLSearchParams(location.search);
  busca.delete("ok");  // a mensagem de sucesso depois de um clique não muda a página
  const CHAVE = "hub-vivo:" + location.pathname + "?" + busca.toString();
  const VALIDADE = 10 * 60 * 1000;
  function foto(raiz) {
    const f = {};
    for (const x of (raiz || document).querySelectorAll("[data-vivo]")) f[x.dataset.vivo] = x.dataset.estado || "";
    return f;
  }
  function guardar(f) {
    try { sessionStorage.setItem(CHAVE, JSON.stringify({ t: Date.now(), f })); } catch (e) { /* sem armazenamento: tudo bem */ }
  }
  function acender(antes, raiz) {
    if (!antes) return;
    for (const x of (raiz || document).querySelectorAll("[data-vivo]")) {
      const era = antes[x.dataset.vivo];
      const agora = x.dataset.estado || "";
      if (era === agora) continue;
      x.classList.remove("mudou", "novo");
      void x.offsetWidth;  // reinicia a animação se já estava acesa
      x.classList.add(era === undefined ? "novo" : "mudou");
      setTimeout(() => x.classList.remove("mudou", "novo"), 2600);
    }
  }
  if (document.querySelector("[data-vivo]")) {
    let antes = null;
    try {
      const salvo = JSON.parse(sessionStorage.getItem(CHAVE) || "null");
      if (salvo && Date.now() - salvo.t < VALIDADE) antes = salvo.f;
    } catch (e) { antes = null; }
    acender(antes);
    guardar(foto());
  }
  window.HubVivo = {
    // chamado pelo app.js depois de trocar o HTML do quadro
    atualizou(raiz, antes) { acender(antes, raiz); guardar(foto()); },
    foto,
  };

  // ---------- números que contam ----------
  function contar(el) {
    const alvo = parseInt(el.dataset.contar, 10);
    if (!Number.isFinite(alvo) || calmo || alvo === 0) return;
    const no = [...el.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim() !== "");
    if (!no) return;
    const dur = Math.min(900, 300 + alvo * 40);
    const t0 = performance.now();
    const passo = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      no.textContent = String(Math.round(alvo * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(passo);
    };
    no.textContent = "0";
    requestAnimationFrame(passo);
  }
  function contarTudo(raiz) {
    for (const el of (raiz || document).querySelectorAll("[data-contar]:not([data-contado])")) {
      el.dataset.contado = "1";
      contar(el);
    }
  }
  contarTudo();
})();
