// Tela "Envios do dia" (fase 9): uma linha por rodada de envio do Pombo, com o horário, o envio, o
// analista, o canal e a situação. Destinatários e o motivo das falhas não vêm para a TV (ficam no app).
// Só entra na rotação quando a pasta do Pombo está configurada e há envio hoje (o servidor decide).
// Se não couber tudo, passa as páginas com fade no mesmo tempo das colunas do Quadro (a TV nunca rola).
(function () {
  "use strict";
  const { el } = HubTV;
  const FADE_MS = 450;
  const RESUMO = [["ok", "✓", "enviados"], ["falha", "⚠", "com falha"], ["andamento", "⏳", "em andamento"]];
  let estado = { paginas: [], pagina: 0 };
  let secao = null;
  let segundosPagina = 10;
  let ultimaTroca = Date.now();

  function cabecalho(sec, dados) {
    const topo = sec.querySelector(".painel-topo");
    topo.replaceChildren();
    const esq = el("div", "painel-titulo");
    esq.append(el("h1", "tela-titulo", "Envios do dia"));
    if (dados.atualizado) esq.append(el("span", "painel-info", "atualizado às " + dados.atualizado));
    if (dados.aviso) esq.append(el("span", "painel-velho", dados.aviso));
    topo.append(esq);
    const resumo = el("div", "envios-resumo");
    for (const [grupo, simbolo, nome] of RESUMO) {
      const n = dados.resumo[grupo] || 0;
      if (n) resumo.append(el("span", "resumo-item grupo-" + grupo, simbolo + " " + n + " " + nome));
    }
    topo.append(resumo);
  }

  function linha(r) {
    const l = el("div", "linha-envio grupo-" + r.grupo);
    const hora = el("div", "envio-hora", r.hora);
    if (r.manual) hora.append(el("span", "envio-manual", "manual"));
    const quem = el("div", "envio-analista");
    const ini = el("span", "ini" + (r.cor ? "" : " sem-cor"), r.iniciais);
    if (r.cor) ini.style.setProperty("--cor", r.cor);
    quem.append(ini, el("span", "envio-pessoa", r.analista));
    const situacao = el("div", "envio-situacao");
    situacao.append(el("span", "selo", r.situacao));
    if (r.contagem) situacao.append(el("span", "envio-contagem", r.contagem));
    l.append(hora, el("div", "envio-nome", r.envio), quem, el("div", "envio-canal", r.canal), situacao);
    return l;
  }

  function paginar(caixa, rodadas) {
    // divide em páginas que cabem, medindo de verdade (como as colunas do Quadro)
    const paginas = [];
    let i = 0;
    while (i < rodadas.length) {
      caixa.replaceChildren();
      const pagina = [];
      while (i < rodadas.length) {
        caixa.append(linha(rodadas[i]));
        if (caixa.scrollHeight > caixa.clientHeight && pagina.length) { caixa.lastChild.remove(); break; }
        pagina.push(rodadas[i]);
        i++;
      }
      paginas.push(pagina);
    }
    return paginas;
  }

  function desenharPagina() {
    const caixa = secao.querySelector(".envios");
    caixa.replaceChildren();
    for (const r of estado.paginas[estado.pagina] || []) caixa.append(linha(r));
    secao.querySelector(".pagina").textContent =
      estado.paginas.length > 1 ? (estado.pagina + 1) + "/" + estado.paginas.length : "";
  }

  setInterval(() => {
    if (!secao || !secao.classList.contains("ativa") || estado.paginas.length < 2) return;
    if (Date.now() - ultimaTroca < segundosPagina * 1000) return;
    ultimaTroca = Date.now();
    const caixa = secao.querySelector(".envios");
    caixa.classList.add("trocando");
    setTimeout(() => {
      estado.pagina = (estado.pagina + 1) % estado.paginas.length;
      desenharPagina();
      caixa.classList.remove("trocando");
    }, FADE_MS);
  }, 500);

  HubTV.registrar("envios", {
    desenhar(sec, dados, tudo) {
      secao = sec;
      segundosPagina = tudo.page_seconds || 10;
      cabecalho(sec, dados);
      const caixa = sec.querySelector(".envios");
      if (caixa.classList.contains("trocando")) return;  // no meio do fade: atualiza no próximo ciclo
      estado.paginas = paginar(caixa, dados.rodadas);
      estado.pagina = Math.min(estado.pagina, estado.paginas.length - 1);
      desenharPagina();
    },
    aoMostrar() {
      estado.pagina = 0;
      ultimaTroca = Date.now();
      if (secao) desenharPagina();
    },
  });
})();
