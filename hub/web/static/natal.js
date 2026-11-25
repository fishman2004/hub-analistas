// Tema de Natal (fase 27), usado pelo app e pela TV. Tudo aqui é um extra: sem este script o Hub funciona igual.
// - visual: neve caindo atrás dos cartões (um <canvas> só, leve) e um varal de luzinhas no topo. As cores e
//   os enfeites ficam no CSS (natal-app.css e natal-tv.css), que só valem com a classe "natal" no <html>.
// - música de fundo: melodias de Natal de domínio público (Jingle Bells, Noite Feliz, We Wish You a Merry
//   Christmas, Deck the Halls) tocadas por um "sininho de caixinha de música" gerado aqui mesmo (Web Audio),
//   com um baixo suave e um pouco de eco. Nenhum arquivo de áudio, nada de internet.
// - sinos: o som dos avisos no Natal (guizos de trenó e um sino tocando o começo de Jingle Bells).
// Com "menos movimento" ligado no Windows, a neve não cai e as luzinhas não piscam.
(function () {
  "use strict";
  const raiz = document.documentElement;
  const calmo = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- visual ----------

  let neve = null;

  function criarNeve() {
    const tela = document.createElement("canvas");
    tela.className = "natal-neve";
    tela.setAttribute("aria-hidden", "true");
    document.body.prepend(tela);
    const ctx = tela.getContext("2d");
    let flocos = [];
    // a cor vem do CSS (--natal-neve): azulada no tema claro do app, branca no escuro e na TV
    const cor = getComputedStyle(document.body).getPropertyValue("--natal-neve").trim() || "#fff";
    let largura = 0;
    let altura = 0;
    function medir() {
      const escala = Math.min(window.devicePixelRatio || 1, 2);
      largura = window.innerWidth;
      altura = window.innerHeight;
      tela.width = largura * escala;
      tela.height = altura * escala;
      ctx.setTransform(escala, 0, 0, escala, 0, 0);
      const quantos = Math.round(Math.min(140, (largura * altura) / 16000));
      flocos = Array.from({ length: quantos }, () => novo(true));
    }
    function novo(qualquerAltura) {
      const r = 1 + Math.random() * 2.6;
      return { x: Math.random() * largura, y: qualquerAltura ? Math.random() * altura : -5, r,
               vy: 0.25 + r * 0.22, fase: Math.random() * 6.28, a: 0.35 + Math.random() * 0.5 };
    }
    let ultimo = 0;
    let parado = false;
    function quadro(t) {
      if (parado) return;
      requestAnimationFrame(quadro);
      if (t - ultimo < 33) return;  // ~30 quadros por segundo: leve para o PC da sala
      const passo = Math.min((t - ultimo) / 33, 3);
      ultimo = t;
      ctx.clearRect(0, 0, largura, altura);
      for (const f of flocos) {
        f.y += f.vy * passo;
        f.fase += 0.012 * passo;
        f.x += Math.sin(f.fase) * 0.35 * passo;
        if (f.y > altura + 5) Object.assign(f, novo(false));
        ctx.globalAlpha = f.a;
        ctx.beginPath();
        ctx.arc(f.x, f.y, f.r, 0, 6.2832);
        ctx.fillStyle = cor;
        ctx.fill();
      }
    }
    medir();
    window.addEventListener("resize", medir);
    if (calmo) quadro(1000);  // um quadro só: a neve fica parada
    else requestAnimationFrame(quadro);
    if (calmo) parado = true;
    return { tela, parar() { parado = true; tela.remove(); window.removeEventListener("resize", medir); } };
  }

  function criarVaral() {
    const varal = document.createElement("div");
    varal.className = "natal-varal";
    varal.setAttribute("aria-hidden", "true");
    const cores = ["vermelha", "dourada", "verde", "azul"];
    for (let i = 0; i < 40; i++) {
      const luz = document.createElement("i");
      luz.className = "luz " + cores[i % cores.length];
      luz.style.setProperty("--i", i);
      varal.append(luz);
    }
    document.body.prepend(varal);
    return varal;
  }

  let varal = null;

  // Papai Noel no trenó (natal-papai-noel.svg, desenho próprio) passando de um lado para o outro.
  // Onde passa, de quanto em quanto tempo e em que altura vêm de Configurações → Papai Noel.
  let timerNoel = null;
  let aoPassar = null;
  let noelCfg = null;  // { minutos, altura } ou null (não passa aqui)
  const ALTURAS = { topo: [6, 14], meio: [34, 44], baixo: [60, 70], sorteada: [10, 60] };

  function papaiNoel(forcar) {
    if (calmo || document.querySelector(".natal-papai-noel")) return;
    if (!forcar && !raiz.classList.contains("natal")) return;
    const [de, ate] = ALTURAS[(noelCfg && noelCfg.altura) || "sorteada"] || ALTURAS.sorteada;
    const voo = document.createElement("div");
    voo.className = "natal-papai-noel";
    voo.setAttribute("aria-hidden", "true");
    voo.style.top = (de + Math.random() * (ate - de)) + "vh";
    voo.style.setProperty("--dur", (11 + Math.random() * 5).toFixed(1) + "s");
    const img = document.createElement("img");
    img.src = "/static/natal-papai-noel.svg";
    img.alt = "";
    voo.append(img);
    document.body.append(voo);
    voo.addEventListener("animationend", (e) => { if (e.target === voo) voo.remove(); });
    if (aoPassar) aoPassar();
  }

  function agendarNoel(primeiro) {
    clearTimeout(timerNoel);
    if (!noelCfg || !raiz.classList.contains("natal")) return;
    const media = noelCfg.minutos * 60;
    const espera = primeiro !== undefined ? primeiro : media * (0.7 + Math.random() * 0.6);
    timerNoel = setTimeout(() => { papaiNoel(); agendarNoel(); }, espera * 1000);
  }

  // muda onde/quando o Papai Noel passa (a TV chama a cada busca; só reagenda se mudou)
  function configurarNoel(cfg) {
    const novo = cfg && cfg.minutos ? { minutos: Number(cfg.minutos), altura: cfg.altura || "sorteada" } : null;
    if (JSON.stringify(novo) === JSON.stringify(noelCfg)) return;
    const antes = noelCfg;
    noelCfg = novo;
    if (!novo) { clearTimeout(timerNoel); return; }
    if (!antes || antes.minutos !== novo.minutos) agendarNoel(Math.min(20 + Math.random() * 30, novo.minutos * 60));
  }

  // opcoes.noel = { minutos, altura } (sem ela, o Papai Noel não passa); opcoes.aoPassar = o que fazer quando passa
  function vestir(ligado, opcoes) {
    raiz.classList.toggle("natal", ligado);
    if (ligado && !neve) {
      neve = criarNeve();
      varal = criarVaral();
      if (opcoes && opcoes.aoPassar) aoPassar = opcoes.aoPassar;
      noelCfg = null;
      configurarNoel(opcoes && opcoes.noel);
    } else if (ligado && opcoes && "noel" in opcoes) {
      configurarNoel(opcoes.noel);
    }
    if (!ligado && neve) {
      neve.parar(); neve = null; varal.remove(); varal = null;
      clearTimeout(timerNoel);
      noelCfg = null;
      for (const v of document.querySelectorAll(".natal-papai-noel")) v.remove();
    }
  }

  // ---------- som ----------

  let ctx = null;
  let saida = null;   // tudo passa por aqui
  let eco = null;     // reverberação gerada (ruído que some), para soar como numa sala
  let volMusica = null;

  function audio() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    saida = ctx.createDynamicsCompressor();
    saida.connect(ctx.destination);
    eco = ctx.createConvolver();
    const n = Math.floor(ctx.sampleRate * 2.2);
    const ir = ctx.createBuffer(2, n, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = ir.getChannelData(c);
      for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, 3.2);
    }
    eco.buffer = ir;
    const molhado = ctx.createGain();
    molhado.gain.value = 0.28;
    eco.connect(molhado).connect(saida);
    volMusica = ctx.createGain();
    volMusica.gain.value = 0;
    volMusica.connect(saida);
    volMusica.connect(eco);
    return ctx;
  }

  // o navegador só deixa tocar depois de um clique (a TV da sala abre com a permissão: ver hub/winsys.py)
  function desbloquear() {
    const c = audio();
    if (c && c.state === "suspended") c.resume().catch(() => {});
    return c;
  }

  const NOTAS = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  function freq(nome, transpor) {
    const m = /^([A-G])(#|b)?(\d)$/.exec(nome);
    const midi = 12 * (Number(m[3]) + 1) + NOTAS[m[1]] + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0) + transpor;
    return 440 * Math.pow(2, (midi - 69) / 12);
  }

  // sininho de caixinha de música: a nota e dois harmônicos que somem rápido
  // a nota soa e some sozinha, mas é abafada logo depois da seguinte começar: sem isso, as notas compridas
  // ficavam tocando por baixo das próximas e embolavam
  function caixinha(destino, f, t, dur, forca) {
    const fim = t + Math.min(Math.max(0.5, dur + 0.25), 2.6);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(0.22 * forca, t + 0.006);
    env.gain.exponentialRampToValueAtTime(0.03 * forca, Math.max(t + 0.3, fim - 0.12));
    env.gain.exponentialRampToValueAtTime(0.0005, fim);
    env.connect(destino);
    for (const [mult, g] of [[1, 1], [2, 0.28], [3, 0.07]]) {
      const o = ctx.createOscillator();
      const v = ctx.createGain();
      o.type = "sine";
      o.frequency.value = f * mult;
      v.gain.value = g;
      o.connect(v).connect(env);
      o.start(t);
      o.stop(fim + 0.02);
    }
  }

  function baixo(destino, f, t, forca) {
    const o = ctx.createOscillator();
    const filtro = ctx.createBiquadFilter();
    const env = ctx.createGain();
    o.type = "triangle";
    o.frequency.value = f;
    filtro.type = "lowpass";
    filtro.frequency.value = 600;
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(0.16 * forca, t + 0.02);
    env.gain.exponentialRampToValueAtTime(0.0008, t + 0.7);
    o.connect(filtro).connect(env).connect(destino);
    o.start(t);
    o.stop(t + 0.75);
  }

  let ruido = null;
  function bufferRuido() {
    if (ruido) return ruido;
    ruido = ctx.createBuffer(1, Math.floor(ctx.sampleRate * 0.25), ctx.sampleRate);
    const d = ruido.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    return ruido;
  }

  // guizo de trenó: um chiado agudo e brilhante bem curto
  function guizo(destino, t, forca) {
    const s = ctx.createBufferSource();
    s.buffer = bufferRuido();
    const filtro = ctx.createBiquadFilter();
    filtro.type = "bandpass";
    filtro.frequency.value = 6500 + Math.random() * 2500;
    filtro.Q.value = 3;
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(0.5 * forca, t + 0.004);
    env.gain.exponentialRampToValueAtTime(0.0008, t + 0.12);
    s.connect(filtro).connect(env).connect(destino);
    s.start(t);
    s.stop(t + 0.15);
    for (const f of [4100, 5300, 7900]) {  // um pouco de metal por cima
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = f * (0.97 + Math.random() * 0.06);
      g.gain.setValueAtTime(0.05 * forca, t);
      g.gain.exponentialRampToValueAtTime(0.0005, t + 0.09);
      o.connect(g).connect(destino);
      o.start(t);
      o.stop(t + 0.1);
    }
  }

  // sino de mão: parciais fora da série harmônica, cada uma sumindo no seu tempo
  function sino(destino, f, t, forca) {
    const parciais = [[1, 1, 2.4], [2, 0.55, 1.5], [3.01, 0.3, 1], [4.17, 0.22, 0.7], [5.43, 0.14, 0.45], [6.8, 0.08, 0.3]];
    for (const [mult, g, decai] of parciais) {
      const o = ctx.createOscillator();
      const v = ctx.createGain();
      o.frequency.value = f * mult;
      v.gain.setValueAtTime(0.0001, t);
      v.gain.exponentialRampToValueAtTime(0.12 * g * forca, t + 0.003);
      v.gain.exponentialRampToValueAtTime(0.0005, t + decai);
      o.connect(v).connect(destino);
      o.start(t);
      o.stop(t + decai + 0.05);
    }
  }

  // ---------- músicas (domínio público) ----------
  // melodia: "nota:tempos" ("R" é pausa); baixo: a nota de cada compasso (tocada no 1º tempo e a quinta no meio)
  const MUSICAS = [
    { id: "jingle", nome: "Jingle Bells", bpm: 132, compasso: 4, transpor: 0, guizos: true,
      melodia: "E5:1 E5:1 E5:2 E5:1 E5:1 E5:2 E5:1 G5:1 C5:1.5 D5:.5 E5:4 F5:1 F5:1 F5:1.5 F5:.5 F5:1 E5:1 E5:1 E5:.5 E5:.5 "
        + "E5:1 D5:1 D5:1 E5:1 D5:2 G5:2 E5:1 E5:1 E5:2 E5:1 E5:1 E5:2 E5:1 G5:1 C5:1.5 D5:.5 E5:4 "
        + "F5:1 F5:1 F5:1.5 F5:.5 F5:1 E5:1 E5:1 E5:.5 E5:.5 G5:1 G5:1 F5:1 D5:1 C5:4",
      baixo: "C C C C F C D G C C C C F C G C" },
    { id: "noite", nome: "Noite Feliz", bpm: 84, compasso: 3, transpor: -12,
      melodia: "G5:1.5 A5:.5 G5:1 E5:3 G5:1.5 A5:.5 G5:1 E5:3 D6:2 D6:1 B5:3 C6:2 C6:1 G5:3 "
        + "A5:2 A5:1 C6:1.5 B5:.5 A5:1 G5:1.5 A5:.5 G5:1 E5:3 A5:2 A5:1 C6:1.5 B5:.5 A5:1 G5:1.5 A5:.5 G5:1 E5:3 "
        + "D6:2 D6:1 F6:1.5 D6:.5 B5:1 C6:3 E6:3 C6:1 G5:1 E5:1 G5:1.5 F5:.5 D5:1 C5:6",
      baixo: "C C C C G G C C F F C C F F C C G G C C C G C C" },
    { id: "wewish", nome: "We Wish You a Merry Christmas", bpm: 150, compasso: 3, transpor: 12, repetir: 2,
      melodia: "R:2 G4:1 C5:1 C5:.5 D5:.5 C5:.5 B4:.5 A4:1 A4:1 A4:1 D5:1 D5:.5 E5:.5 D5:.5 C5:.5 B4:1 G4:1 G4:1 "
        + "E5:1 E5:.5 F5:.5 E5:.5 D5:.5 C5:1 A4:1 G4:.5 G4:.5 A4:1 D5:1 B4:1 C5:2 R:1",
      baixo: "- C F D G A F G C" },
    { id: "deck", nome: "Deck the Halls", bpm: 120, compasso: 4, transpor: 12,
      melodia: "G4:1.5 F4:.5 E4:1 D4:1 C4:1 D4:1 E4:1 C4:1 D4:.5 E4:.5 F4:.5 D4:.5 E4:1.5 D4:.5 C4:1 B3:1 C4:2 "
        + "G4:1.5 F4:.5 E4:1 D4:1 C4:1 D4:1 E4:1 C4:1 D4:.5 E4:.5 F4:.5 D4:.5 E4:1.5 D4:.5 C4:1 B3:1 C4:2 "
        + "D4:1.5 E4:.5 F4:1 D4:1 E4:1.5 F4:.5 G4:1 D4:1 E4:.5 F#4:.5 G4:1 A4:.5 B4:.5 C5:1 B4:1 A4:1 G4:2 "
        + "G4:1.5 F4:.5 E4:1 D4:1 C4:1 D4:1 E4:1 C4:1 A4:.5 A4:.5 A4:.5 A4:.5 G4:1.5 F4:.5 E4:1 D4:1 C4:2",
      baixo: "C C G C C C G C G C D G C C F C" },
  ];
  const QUINTA = { C: "G", D: "A", E: "B", F: "C", G: "D", A: "E", B: "F#" };

  // agenda uma música inteira a partir do instante t, num volume próprio dela; devolve quando ela termina
  function agendar(m, destino, t) {
    const seg = 60 / m.bpm;
    let beat = 0;
    for (let r = 0; r < (m.repetir || 1); r++) {
      const inicio = beat;
      for (const item of m.melodia.split(/\s+/)) {
        const [nota, tempos] = item.split(":");
        const dur = Number(tempos);
        if (nota !== "R") {
          const forte = (beat - inicio) % m.compasso === 0 ? 1 : 0.8;
          caixinha(destino, freq(nota, m.transpor), t + beat * seg, dur * seg, forte);
        }
        beat += dur;
      }
      m.baixo.split(" ").forEach((raizNota, i) => {
        if (raizNota === "-") return;
        const b = inicio + i * m.compasso;
        baixo(destino, freq(raizNota + "3", 0), t + b * seg, 1);
        if (m.compasso === 4) baixo(destino, freq(QUINTA[raizNota] + "2", 0), t + (b + 2) * seg, 0.7);
        else for (const k of [1, 2]) baixo(destino, freq(QUINTA[raizNota] + "3", 0), t + (b + k) * seg, 0.45);
        if (m.guizos) for (let k = 0; k < m.compasso; k++) guizo(destino, t + (b + k + 0.5) * seg, 0.18);
      });
    }
    return t + beat * seg;
  }

  const musica = { ligada: false, volume: 25, timer: null, atual: null, fila: [], seq: 0,
                   faixas: MUSICAS.map((m) => m.id), ordem: "aleatoria", intervalo: 5, tipo: "app", cedidoAte: 0 };

  function ganhoDoVolume(v) { return Math.pow(Math.max(0, Math.min(100, v)) / 100, 1.6) * 1.4; }

  function escolher() {
    const lista = MUSICAS.filter((m) => musica.faixas.includes(m.id));
    const faixas = lista.length ? lista : MUSICAS;
    if (musica.ordem === "lista") return faixas[musica.seq++ % faixas.length];
    if (!musica.fila.length) musica.fila = faixas.slice().sort(() => Math.random() - 0.5);
    return musica.fila.shift();
  }

  function soltar(g) {  // a música que estava tocando some em 0,2 s e sai do som
    if (!g) return;
    g.gain.setTargetAtTime(0, ctx.currentTime, 0.06);
    setTimeout(() => g.disconnect(), 500);
  }

  function proxima() {
    clearTimeout(musica.timer);
    if (!musica.ligada) return;
    soltar(musica.atual);
    const m = escolher();
    const g = ctx.createGain();
    g.connect(volMusica);
    musica.atual = g;
    musica.nome = m.nome;
    const fim = agendar(m, g, ctx.currentTime + 0.3);
    // entre uma música e outra, o silêncio escolhido em Configurações
    musica.timer = setTimeout(proxima, (fim - ctx.currentTime + 1.5 + musica.intervalo) * 1000);
  }

  // ---------- uma aba por vez no mesmo PC ----------
  // Duas abas do Hub tocando (a TV e o app, ou a TV aberta duas vezes) embolam as músicas. As abas que tocam
  // avisam as outras a cada 2 s; quem recebe para. A TV dá a vez para o app ("Ouvir a música aqui") e volta
  // sozinha uns segundos depois que ele parar; entre duas iguais, fica a que começou por último.
  const ID = Math.random().toString(36).slice(2);
  let canal = null;
  try { canal = new BroadcastChannel("hub-natal-musica"); } catch (e) { /* navegador antigo: cada aba por si */ }
  let inicio = 0;
  if (canal) {
    canal.onmessage = (e) => {
      const d = e.data || {};
      if (d.id === ID || d.tipo === undefined) return;
      musica.cedidoAte = Date.now() + 6000;
      const outraMandaMais = d.tipo === "app" && musica.tipo === "tv";
      const outraEMaisNova = d.tipo === musica.tipo && d.inicio > inicio;
      if (musica.ligada && (outraMandaMais || outraEMaisNova)) pararMusica();
      if (!musica.ligada) musica.cedidoAte = Date.now() + 6000;
    };
    setInterval(() => { if (musica.ligada) canal.postMessage({ id: ID, tipo: musica.tipo, inicio }); }, 2000);
  }

  // opcoes: { tipo: "tv" | "app", faixas, ordem, intervalo }
  function tocarMusica(volume, opcoes) {
    if (opcoes) {
      if (opcoes.tipo) musica.tipo = opcoes.tipo;
      if (Array.isArray(opcoes.faixas) && opcoes.faixas.join() !== musica.faixas.join()) {
        musica.faixas = opcoes.faixas.slice();
        musica.fila = [];
      }
      if (opcoes.ordem) musica.ordem = opcoes.ordem;
      if (Number.isFinite(Number(opcoes.intervalo))) musica.intervalo = Number(opcoes.intervalo);
    }
    if (!musica.ligada && musica.tipo === "tv" && Date.now() < musica.cedidoAte) return false;  // outra aba deste PC toca
    const c = desbloquear();
    if (!c) return false;
    const novoVolume = volume !== undefined && volume !== musica.volume;
    if (volume !== undefined) musica.volume = volume;
    // só mexe no volume quando ele muda (a TV chama a cada 5 s; não pode desfazer a baixada dos sinos)
    if (!musica.ligada || novoVolume) volMusica.gain.setTargetAtTime(ganhoDoVolume(musica.volume), c.currentTime, 0.4);
    if (!musica.ligada) {
      musica.ligada = true;
      inicio = Date.now();
      if (canal) canal.postMessage({ id: ID, tipo: musica.tipo, inicio });
      proxima();
    } else if (musica.atual && !musica.faixas.includes(MUSICAS.find((m) => m.nome === musica.nome)?.id)) {
      proxima();  // a faixa que estava tocando foi desmarcada: passa para uma das marcadas
    }
    return true;
  }

  function pararMusica() {
    if (!musica.ligada) return;
    musica.ligada = false;
    clearTimeout(musica.timer);
    soltar(musica.atual);
    musica.atual = null;
  }

  // o som dos avisos: guizos de trenó e um sino tocando "Jingle bells, jingle bells" (curto: só o começo)
  function sinos(opcoes) {
    const curto = Boolean(opcoes && opcoes.curto);
    const c = desbloquear();
    if (!c || c.state !== "running") return false;
    const t0 = c.currentTime + 0.05;
    const destino = ctx.createGain();
    destino.gain.value = curto ? 0.6 : 1;
    destino.connect(saida);
    destino.connect(eco);
    // a música baixa enquanto os sinos tocam
    if (musica.ligada) {
      volMusica.gain.setTargetAtTime(ganhoDoVolume(musica.volume) * 0.15, t0, 0.08);
      volMusica.gain.setTargetAtTime(ganhoDoVolume(musica.volume), t0 + (curto ? 1.5 : 4.5), 0.6);
    }
    for (let i = 0; i < (curto ? 6 : 12); i++) guizo(destino, t0 + i * 0.075 + (i % 2) * 0.02, 0.9);
    const seg = 60 / 190;
    const toque = curto ? "E6:1 E6:1 E6:2" : "E6:1 E6:1 E6:2 E6:1 E6:1 E6:2 E6:1 G6:1 C6:1.5 D6:.5 E6:4";
    let beat = 0;
    for (const item of toque.split(" ")) {
      const [nota, tempos] = item.split(":");
      sino(destino, freq(nota, -12), t0 + 0.55 + beat * seg, 1);
      beat += Number(tempos);
    }
    setTimeout(() => destino.disconnect(), (0.55 + beat * seg + 3) * 1000);
    return true;
  }

  // ---------- os outros sons dos avisos (Configurações → Som dos avisos) ----------

  function preparar(segundos) {
    const c = desbloquear();
    if (!c || c.state !== "running") return null;
    const t0 = c.currentTime + 0.05;
    const destino = ctx.createGain();
    destino.connect(saida);
    destino.connect(eco);
    if (musica.ligada) {  // a música baixa enquanto o aviso toca
      volMusica.gain.setTargetAtTime(ganhoDoVolume(musica.volume) * 0.15, t0, 0.08);
      volMusica.gain.setTargetAtTime(ganhoDoVolume(musica.volume), t0 + segundos, 0.6);
    }
    setTimeout(() => destino.disconnect(), (segundos + 5) * 1000);
    return { destino, t0 };
  }

  // sino grande: um "hum" grave e parciais de sino que demoram a sumir
  function sinoGrande(destino, f, t, forca) {
    const parciais = [[0.5, 0.5, 5], [1, 1, 4], [1.19, 0.45, 2.6], [1.5, 0.35, 2.2], [2, 0.4, 1.8], [2.5, 0.2, 1.2], [3, 0.15, 0.9], [4.2, 0.08, 0.6]];
    for (const [mult, g, decai] of parciais) {
      const o = ctx.createOscillator();
      const v = ctx.createGain();
      o.frequency.value = f * mult;
      v.gain.setValueAtTime(0.0001, t);
      v.gain.exponentialRampToValueAtTime(0.14 * g * forca, t + 0.004);
      v.gain.exponentialRampToValueAtTime(0.0004, t + decai);
      o.connect(v).connect(destino);
      o.start(t);
      o.stop(t + decai + 0.05);
    }
  }

  const AVISOS = {
    sinos: () => sinos(),
    igreja() {  // blém... blém... blém
      const p = preparar(6);
      if (!p) return false;
      [[0, "E4"], [1.6, "C4"], [3.2, "E4"]].forEach(([t, n]) => sinoGrande(p.destino, freq(n, 0), p.t0 + t, 1));
      return true;
    },
    carrilhao() {  // o toque dos relógios de torre (Westminster, 1793, domínio público)
      const p = preparar(6);
      if (!p) return false;
      "G4 E5 D5 C5 . G4 D5 E5 C5".split(" ").forEach((n, i) => { if (n !== ".") sino(p.destino, freq(n, 0), p.t0 + i * 0.55, 1.2); });
      return true;
    },
    caixinha() {
      const p = preparar(3);
      if (!p) return false;
      "C6 E6 G6 C7 G6 E6 C7".split(" ").forEach((n, i) => caixinha(p.destino, freq(n, 0), p.t0 + i * 0.16, 0.5, i === 6 ? 1.2 : 0.9));
      return true;
    },
    guizos() {
      const p = preparar(2.5);
      if (!p) return false;
      for (let i = 0; i < 26; i++) guizo(p.destino, p.t0 + i * 0.07 + (i % 2) * 0.025 + Math.floor(i / 6) * 0.12, 1);
      return true;
    },
  };

  // toca o som escolhido para os avisos; devolve false quando é o "de sempre" (o aviso.wav) ou não deu para tocar
  function tocarAviso(tipo) {
    return Boolean(AVISOS[tipo] && AVISOS[tipo]());
  }

  // guizos de trenó baixinhos, para quando o Papai Noel passa na TV com a música ligada
  function guizosDoTreno() {
    if (!ctx || ctx.state !== "running") return;
    const destino = ctx.createGain();
    destino.gain.value = 0.25;
    destino.connect(volMusica);
    const t0 = ctx.currentTime + 0.1;
    for (let i = 0; i < 28; i++) guizo(destino, t0 + i * 0.16 + (i % 2) * 0.05, 0.6);
    setTimeout(() => destino.disconnect(), 6000);
  }

  window.HubNatal = {
    vestir,
    papaiNoel,
    configurarNoel,
    guizosDoTreno,
    tocarAviso,
    desbloquear,
    sinos,
    musica: { tocar: tocarMusica, parar: pararMusica, proxima: () => proxima(),
              get ligada() { return musica.ligada; }, get nome() { return musica.nome; } },
  };

  // ---------- app ----------
  // A TV chama HubNatal pelo tv.js. No app, o tema vem ligado pelo servidor (classe "natal" no <html>) e cada
  // pessoa escolhe se quer os sons no próprio PC (desligados por padrão, salvos no navegador).
  document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.tv !== undefined) return;
    const CHAVE = "hub-natal-sons";
    const ligado = raiz.classList.contains("natal");
    const corpo = document.body.dataset;
    // o Papai Noel passa no app só se Configurações → Papai Noel deixar (o servidor manda no <body>)
    if (ligado) vestir(true, { noel: corpo.noelMinutos ? { minutos: corpo.noelMinutos, altura: corpo.noelAltura } : null });

    // Configurações: ouvir a música e os sinos aqui mesmo
    const ouvir = document.getElementById("natal-ouvir");
    const pular = document.getElementById("natal-pular");
    if (pular) pular.addEventListener("click", () => proxima());
    const noelVer = document.getElementById("noel-ver");
    if (noelVer) {
      noelVer.hidden = false;
      noelVer.addEventListener("click", () => {
        const marcada = document.querySelector('input[name="altura"]:checked');
        const guardada = noelCfg;
        noelCfg = { minutos: 60, altura: marcada ? marcada.value : "sorteada" };
        papaiNoel(true);
        noelCfg = guardada;
      });
    }
    const somOuvir = document.getElementById("som-ouvir");
    if (somOuvir) {
      somOuvir.hidden = false;
      somOuvir.addEventListener("click", () => {
        let tipo = document.getElementById("som").value;
        if (tipo === "auto") tipo = raiz.classList.contains("natal") ? "sinos" : "padrao";
        desbloquear();
        setTimeout(() => {
          if (!tocarAviso(tipo)) { try { new Audio("/static/aviso.wav").play().catch(() => {}); } catch (e) { /* sem som */ } }
        }, 60);
      });
    }
    if (ouvir) {
      ouvir.hidden = false;
      ouvir.addEventListener("click", () => {
        if (musica.ligada) { pararMusica(); ouvir.textContent = "▶ Ouvir a música aqui"; if (pular) pular.hidden = true; return; }
        const v = Number(document.getElementById("natal-volume").value);
        const faixas = [...document.querySelectorAll('input[name="faixas"]:checked')].map((i) => i.value);
        const ordem = document.querySelector('input[name="ordem"]:checked');
        if (tocarMusica(Number.isFinite(v) ? v : 25, { tipo: "app", faixas, ordem: ordem ? ordem.value : "aleatoria",
                                                       intervalo: document.getElementById("natal-intervalo").value })) {
          ouvir.textContent = "■ Parar a música";
          if (pular) pular.hidden = false;
        }
      });
    }

    const botao = document.getElementById("natal-som");
    if (!ligado || !botao) return;
    let sons = false;
    try { sons = localStorage.getItem(CHAVE) === "1"; } catch (e) { /* sem armazenamento: desligado */ }
    const mostrar = () => {
      botao.textContent = sons ? "🔔 Sons de Natal" : "🔕 Sons de Natal";
      botao.setAttribute("aria-pressed", String(sons));
      botao.title = sons ? "Desligar a música e os sinos neste PC" : "Ligar a música de Natal e os sinos neste PC";
    };
    mostrar();
    botao.hidden = false;
    botao.addEventListener("click", () => {
      sons = !sons;
      try { localStorage.setItem(CHAVE, sons ? "1" : "0"); } catch (e) { /* vale até recarregar */ }
      mostrar();
      if (sons) { tocarMusica(18); setTimeout(() => sinos({ curto: true }), 80); } else pararMusica();
    });
    if (!sons) return;
    // som ligado: o navegador só deixa tocar depois do primeiro clique ou tecla na página
    const comecar = () => {
      document.removeEventListener("pointerdown", comecar, true);
      document.removeEventListener("keydown", comecar, true);
      desbloquear();  // o primeiro clique libera o som da página
      if (!musica.ligada) tocarMusica(18);
    };
    tocarMusica(18);
    if (!ctx || ctx.state !== "running") {
      document.addEventListener("pointerdown", comecar, true);
      document.addEventListener("keydown", comecar, true);
    }
    // aviso de sucesso aparecendo (hub.js): um sininho curto
    if (document.querySelector(".sucesso")) {
      const tocar = () => sinos({ curto: true });
      if (ctx && ctx.state === "running") setTimeout(tocar, 150);
      else ctx && ctx.addEventListener("statechange", function uma() {
        if (ctx.state === "running") { ctx.removeEventListener("statechange", uma); setTimeout(tocar, 150); }
      });
    }
  });
})();
