// Tela "Trilhas do dia" (fase 20): a trilha de horários de cada analista, uma linha por pessoa, com o
// tempo de verdade no eixo (das 08:00 às 18:00). Cada bloco é uma bolinha com o ícone, acesa conforme a
// situação: apagada (ainda não chegou), pulsando (agora), acesa em verde (feito no horário), âmbar
// (feito depois) e a "luz negativa" vermelha (o horário passou sem marcar). Um ponto de luz marca o
// agora e, toda vez que a tela aparece, uma luz varre a trilha do começo do dia até agora, acendendo
// cada bloco no passo dela. À direita, o bloco de agora por extenso. Com mais de 4 pessoas, passa as
// páginas com fade (a TV nunca rola). Só entra na rotação quando alguém tem trilha hoje.
(function () {
  "use strict";
  const { el } = HubTV;
  const POR_PAGINA = 4;
  const VARREDURA_MS = 2600;  // a varredura de uma trilha inteira (do começo ao fim do eixo)
  const FADE_MS = 450;
  const SVG = "http://www.w3.org/2000/svg";
  const versao = (document.querySelector('script[src*="tv.js"]').src.split("v=")[1] || "");
  const ROTULOS = { agora: "Agora", pausa: "Intervalo", proximo: "Próximo", fim: "Dia encerrado" };
  let dados = null;
  let ultimo = "";
  let pagina = 0;
  let paginas = 1;
  let ultimaTroca = Date.now();
  let segundosPagina = 10;
  let timerVarredura = null;

  function icone(nome) {
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(SVG, "use");
    if (/^[a-z]+$/.test(nome)) use.setAttribute("href", "/static/trilha-icones.svg?v=" + versao + "#" + nome);
    svg.append(use);
    return svg;
  }

  function bloco(b, agoraPct, atraso) {
    const centro = b.pos + b.larg / 2;
    const d = el("div", "tr-bloco st-" + b.status + (b.larg >= 6 ? " largo" : ""));
    d.style.left = b.pos + "%";
    d.style.width = b.larg + "%";
    d.style.setProperty("--bloco", b.cor);
    // a luz da varredura passa por aqui neste tempo (só nos blocos que já começaram)
    if (centro <= agoraPct + b.larg / 2 && b.status !== "futuro") {
      d.classList.add("varre");
      d.style.setProperty("--dl", (atraso + VARREDURA_MS * Math.min(centro, agoraPct) / 100) + "ms");
    }
    d.append(el("span", "tr-seg"));
    const bola = el("span", "tr-bola");
    bola.append(icone(b.icone));
    if (b.status === "feito" || b.status === "feito_atrasado") bola.append(el("span", "tr-selo", "✓"));
    else if (b.status === "nao_feito") bola.append(el("span", "tr-selo", "✕"));
    d.append(bola, el("span", "tr-h", b.inicio));
    if (b.larg >= 6 && b.titulo) d.append(el("span", "tr-t", b.titulo));
    return d;
  }

  function foco(f, linha) {
    const caixa = el("div", "tr-foco tipo-" + f.tipo);
    if (f.titulo !== undefined) caixa.style.setProperty("--bloco", f.cor);
    const rot = el("div", "tr-foco-rot");
    rot.append(el("b", "", ROTULOS[f.tipo]));
    if (f.tipo === "agora") rot.append(document.createTextNode(" · " + f.inicio + " às " + f.fim));
    else if (f.tipo === "pausa") rot.append(document.createTextNode(" · até " + f.fim));
    else if (f.tipo === "proximo") rot.append(document.createTextNode(" · " + f.inicio));
    caixa.append(rot);
    if (f.titulo) caixa.append(el("div", "tr-foco-titulo", f.titulo));
    if (f.tipo === "agora" && f.detalhes && f.detalhes.length) {
      const ul = el("ul", "tr-foco-itens");
      for (const x of f.detalhes) ul.append(el("li", "", x));
      caixa.append(ul);
    }
    const conta = el("div", "tr-foco-conta");
    conta.append(el("span", "ok", "✓ " + linha.feitos + " de " + linha.total));
    if (linha.perdidos) conta.append(el("span", "nao", "✕ " + linha.perdidos + " sem marcar"));
    caixa.append(conta);
    return caixa;
  }

  function desenharPagina(sec) {
    const linhas = sec.querySelector(".tr-linhas");
    linhas.replaceChildren();
    const lista = dados.linhas.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);
    linhas.style.setProperty("--n", Math.max(lista.length, 3));
    lista.forEach((l, k) => {
      const atraso = k * 180;
      const linha = el("div", "tr-linha");
      linha.style.setProperty("--d0", atraso + "ms");
      const quem = el("div", "tr-quem");
      const ini = el("span", "ini", l.iniciais);
      ini.style.setProperty("--cor", l.cor);
      const nome = el("div", "tr-nome");
      nome.append(el("b", "", l.nome));
      if (l.pastas) nome.append(el("span", "", "Pasta" + (l.pastas.length > 1 ? "s " : " ") + l.pastas));
      quem.append(ini, nome);
      const pista = el("div", "tr-pista");
      pista.append(el("div", "tr-trilho"));
      const rastro = el("div", "tr-rastro");
      rastro.style.width = dados.agora_pct + "%";
      pista.append(rastro);
      for (const b of l.blocos) pista.append(bloco(b, dados.agora_pct, atraso));
      const ponto = el("div", "tr-ponto");
      ponto.style.left = dados.agora_pct + "%";
      const cometa = el("div", "tr-cometa");
      cometa.style.setProperty("--ate", dados.agora_pct + "%");
      cometa.style.setProperty("--dur", Math.max(400, VARREDURA_MS * dados.agora_pct / 100) + "ms");
      pista.append(ponto, cometa);
      linha.append(quem, pista, foco(l.foco, l));
      linhas.append(linha);
    });
    sec.querySelector(".pagina").textContent = paginas > 1 ? (pagina + 1) + "/" + paginas : "";
  }

  function desenharEixo(sec) {
    const eixo = sec.querySelector(".tr-eixo");
    eixo.replaceChildren(el("div"));
    const regua = el("div", "tr-regua");
    for (const h of dados.horas) {
      if (Math.abs(h.pos - dados.agora_pct) < 3.5) continue;  // o selo do agora fica no lugar
      const marca = el("span", "", h.hora.slice(0, 2) + "h");
      marca.style.left = h.pos + "%";
      regua.append(marca);
    }
    const agora = el("span", "tr-regua-agora", dados.agora);
    agora.style.left = dados.agora_pct + "%";
    regua.append(agora);
    eixo.append(regua, el("div"));
  }

  function varrer(sec) {
    // reinicia a luz que varre as trilhas; depois tira a classe, para um redesenho não repetir a varredura
    const grade = sec.querySelector(".tr-grade");
    clearTimeout(timerVarredura);
    grade.classList.remove("varrendo");
    void grade.offsetWidth;
    if (HubTV.exportando) return;
    grade.classList.add("varrendo");
    timerVarredura = setTimeout(() => grade.classList.remove("varrendo"), VARREDURA_MS + POR_PAGINA * 180 + 1500);
  }

  function trocar(sec, direcao) {
    if (paginas < 2) return;
    const linhas = sec.querySelector(".tr-linhas");
    linhas.classList.add("trocando");
    ultimaTroca = Date.now();
    setTimeout(() => {
      pagina = (pagina + direcao + paginas) % paginas;
      desenharPagina(sec);
      linhas.classList.remove("trocando");
      varrer(sec);
    }, HubTV.exportando ? 0 : FADE_MS);
  }

  HubTV.registrar("trilhas", {
    desenhar(sec, novos, tudo) {
      segundosPagina = (tudo && tudo.page_seconds) || segundosPagina;
      const json = JSON.stringify(novos);
      if (json !== ultimo) {
        ultimo = json;
        dados = novos;
        paginas = Math.max(1, Math.ceil(dados.linhas.length / POR_PAGINA));
        if (pagina >= paginas) pagina = 0;
        desenharEixo(sec);
        desenharPagina(sec);
      }
      const ativa = sec.classList.contains("ativa");
      if (ativa && !HubTV.pausada() && Date.now() - ultimaTroca >= segundosPagina * 1000) trocar(sec, 1);
    },
    aoMostrar(sec) {
      if (pagina !== 0 && dados) { pagina = 0; desenharPagina(sec); }
      ultimaTroca = Date.now();
      varrer(sec);
    },
    pagina(sec, direcao) {
      if (HubTV.exportando) {  // no PDF: uma folha por página, sem esperar o fade
        pagina = (pagina + direcao + paginas) % paginas;
        desenharPagina(sec);
        return;
      }
      trocar(sec, direcao);
    },
  });
})();
