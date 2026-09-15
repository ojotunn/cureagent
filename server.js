// Servidor do EHRLICH.
//
// Ele nao e mais so um servidor de arquivos. Antes, a fila de compras e o estado
// do motor eram calculados na maquina de quem estava desenvolvendo e empurrados
// por commit. Isso significava que o site congelava quando essa maquina fechava,
// e a pagina passava a mentir sobre o que a placa estava fazendo.
//
// Agora o servidor:
//   1. LE A CHAIN sozinho, a cada 90s, e monta a fila de lotes;
//   2. RECEBE o estado da placa por POST /api/motor, autenticado por segredo;
//   3. SERVE /data/lotes.json a partir disso, caindo no arquivo em disco
//      enquanto a primeira leitura nao termina.
//
// Nenhuma dependencia, de proposito: o build no Railway nao instala nada.

const http = require("http");
const fs = require("fs");
const path = require("path");
const { negociacoes, blocoAtual, horaDoBloco } = require("./agente/chain.js");

const RAIZ = path.join(__dirname, "site");
const PORTA = process.env.PORT || 8440;
const SEGREDO = process.env.EHRLICH_TOKEN || "";
const MOLECULAS_POR_ETH = Number(process.env.MOLECULAS_POR_ETH || 250000);
const INTERVALO_CHAIN = Number(process.env.INTERVALO_CHAIN || 90) * 1000;

const TIPOS = {
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
  ".pdb": "chemical/x-pdb",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
};

function leJSON(p, padrao) {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return padrao; }
}

/* ------------------------------------------------ estado vivo, em memoria */
const vivo = {
  compras: null,        // lista crua vinda da chain
  desdeBloco: null,     // bloco mais antigo com compra, para a janela nao rolar
  motor: null,          // ultimo estado empurrado pela placa
  motorEm: 0,           // quando chegou (ms)
  chainEm: 0,
  chainErro: null,
};

const horaCache = new Map();

// Os horarios dos blocos eram buscados um a um, em serie. Com quase 500 compras
// isso fazia o servidor levar quase um minuto para ter a fila depois de cada
// deploy, e nesse intervalo a pagina mostrava o arquivo velho do disco como se
// fosse o estado atual. Agora vao em paralelo, em lotes.
async function carregaHoras(blocos) {
  const faltam = [...new Set(blocos)].filter((b) => !horaCache.has(b));
  const LOTE = 25;
  for (let i = 0; i < faltam.length; i += LOTE) {
    const fatia = faltam.slice(i, i + LOTE);
    const horas = await Promise.all(
      fatia.map((b) => horaDoBloco(b).catch(() => null)));
    fatia.forEach((b, k) => horaCache.set(b, horas[k]));
  }
}

/* ------------------------------------------------------ leitura da chain */
async function leChain() {
  const tk = leJSON(path.join(RAIZ, "token.json"), {});
  if (!tk.curva) throw new Error("token.json sem curva");

  const fim = await blocoAtual();
  // A janela era rolante (fim - 200000). Conforme a chain avanca, compras
  // antigas saiam pela tras da janela e sumiam da fila sem aviso. O inicio
  // agora fica preso no bloco mais antigo ja visto.
  const de = vivo.desdeBloco != null
    ? vivo.desdeBloco
    : Math.max(0, fim - 200000);

  const FATIA = 50000;
  const eventos = [];
  let falhas = 0;
  for (let b = de; b <= fim; b += FATIA) {
    const ate = Math.min(b + FATIA - 1, fim);
    let ok = false;
    // uma fatia que falha levava junto TODAS as compras daquele intervalo, e o
    // resultado parcial ia para a pagina como se fosse a fila inteira
    for (let tentativa = 0; tentativa < 3 && !ok; tentativa++) {
      try {
        eventos.push(...await negociacoes(tk.curva, b, ate));
        ok = true;
      } catch (e) {
        if (tentativa === 2) {
          falhas++;
          console.error("fatia " + b + "-" + ate + " desistiu: " + e.message);
        } else {
          await new Promise((r) => setTimeout(r, 1500 * (tentativa + 1)));
        }
      }
    }
  }

  if (falhas) {
    vivo.chainErro = falhas + " fatia(s) da chain falharam; fila anterior mantida";
    vivo.chainEm = Date.now();
    // sem fila anterior nao ha o que manter, mas tambem nao se publica um
    // numero que sabemos estar incompleto
    console.error(vivo.chainErro);
    return;
  }

  const compras = eventos.filter((e) => e.tipo === "compra");
  if (compras.length) {
    const menor = Math.min(...compras.map((c) => c.bloco));
    if (vivo.desdeBloco == null || menor < vivo.desdeBloco) vivo.desdeBloco = menor;
  }
  // uma varredura completa que devolve menos compras que a anterior significa
  // que a chain respondeu de forma inconsistente: nao se apaga fila com isso
  if (vivo.compras && compras.length < vivo.compras.length) {
    vivo.chainErro = "varredura devolveu " + compras.length + " compras contra " +
                     vivo.compras.length + " anteriores; fila anterior mantida";
    vivo.chainEm = Date.now();
    console.error(vivo.chainErro);
    return;
  }
  await carregaHoras(compras.map((c) => c.bloco));
  const lotes = [];
  for (const c of compras) {
    const h = horaCache.get(c.bloco) || null;
    lotes.push({
      ts: h ? h.toISOString().slice(0, 16).replace("T", " ") : null,
      endereco: c.quem,
      eth: Number(c.eth.toFixed(6)),
      moleculas: null,
      melhor: null,
      gpu_min: null,
      cota: Math.round(c.eth * MOLECULAS_POR_ETH),
      tx: c.tx,
      log: c.indice,
      bloco: c.bloco,
      estado: "queued",
    });
  }
  vivo.compras = lotes;
  vivo.chainEm = Date.now();
  vivo.chainErro = null;
  console.log("chain: " + lotes.length + " compras ate o bloco " + fim);
}

/* --------------------------------------------- custo real das placas alugadas */
async function custoDasPlacas() {
  const chave = process.env.RUNPOD_API_KEY;
  const ids = (process.env.RUNPOD_POD_IDS || process.env.RUNPOD_POD_ID || "")
                .split(",").map((s) => s.trim()).filter(Boolean);
  if (!chave || !ids.length) return null;

  // gasto = soma de (horas de cada placa x preco por hora dela). Somar as horas
  // e multiplicar pela soma dos precos daria numero errado com placas que
  // subiram em momentos diferentes.
  let gasto = 0, horaTotal = 0, maisVelha = 0, vivas = 0;
  for (const id of ids) {
    try {
      const r = await fetch("https://rest.runpod.io/v1/pods/" + id,
                            { headers: { Authorization: "Bearer " + chave } });
      if (!r.ok) continue;
      const p = await r.json();
      const ini = Date.parse(String(p.lastStartedAt || p.createdAt || "")
                               .replace(" +0000 UTC", "Z").replace(" ", "T"));
      if (!ini) continue;
      const h = (Date.now() - ini) / 3600000;
      const preco = Number(p.costPerHr) || 0;
      gasto += h * preco;
      horaTotal += preco;
      if (h > maisVelha) maisVelha = h;
      vivas += 1;
    } catch (e) { /* uma placa fora nao derruba a conta das outras */ }
  }
  if (!vivas) return null;
  return { horas: maisVelha, hora: horaTotal, placas: vivas, gasto };
}
let custo = null;

/* ------------------------------------------------------- monta o lotes.json */
function montaLotes() {
  const disco = leJSON(path.join(RAIZ, "data", "lotes.json"), {});
  if (!vivo.compras) return disco;             // ainda nao leu a chain

  // a placa so conta como viva se falou nos ultimos 6 minutos
  const fresco = vivo.motor && (Date.now() - vivo.motorEm) < 360000;
  const m = fresco ? Object.assign({}, vivo.motor) : null;
  if (m && custo) {
    m.gpu = m.gpu || "RTX 4000 SFF Ada";
    m.placas = custo.placas;
    m.gpu_hora = Number(custo.hora.toFixed(2));
    m.gpu_gasto_usd = Number(custo.gasto.toFixed(2));
    m.horas = Number(custo.horas.toFixed(2));
  }

  const lotes = vivo.compras.map((l) => Object.assign({}, l));
  // A fila so anda com TRIAGEM. Validacao nao gasta cota de comprador.
  if (m && m.estado === "screening") {
    let resta = m.triadas || 0;
    const ordem = lotes.slice().sort((a, b) => (a.bloco || 0) - (b.bloco || 0));
    for (const l of ordem) {
      const feito = resta <= 0 ? 0 : Math.min(l.cota || 0, resta);
      l.moleculas = feito || null;
      l.estado = feito >= (l.cota || 0) && l.cota ? "pronto" : feito ? "running" : "queued";
      resta -= feito;
    }
  }
  lotes.sort((a, b) => (b.bloco || 0) - (a.bloco || 0));

  const enderecos = {};
  for (const l of lotes) enderecos[l.endereco] = 1;

  return {
    _comentario: disco._comentario,
    modo: m ? "live" : "parado",
    mostrar_endereco: disco.mostrar_endereco || "truncado",
    atualizado_em: new Date().toISOString().slice(0, 16).replace("T", " "),
    fonte: "servidor: chain lida direto, placa por push",
    resumo: {
      financiadores: Object.keys(enderecos).length,
      moleculas_financiadas: lotes.reduce((s, l) => s + (l.moleculas || 0), 0),
      minutos_gpu: Math.round((custo && custo.horas ? custo.horas : 0) * 60),
      na_fila: lotes.filter((l) => l.estado === "queued").length,
      cota_total: lotes.reduce((s, l) => s + (l.cota || 0), 0),
    },
    motor: m,
    fila_alvos: (fresco && vivo.motor.fila_alvos) || disco.fila_alvos || null,
    lotes,
  };
}

/* ------------------------------------------------------------------ HTTP */
function corpo(req, limite) {
  const teto = limite || 262144;
  return new Promise((ok, falha) => {
    let n = 0; const partes = [];
    req.on("data", (c) => {
      n += c.length;
      if (n > teto) { falha(new Error("payload grande")); req.destroy(); return; }
      partes.push(c);
    });
    req.on("end", () => ok(Buffer.concat(partes).toString("utf8")));
    req.on("error", falha);
  });
}

const servidor = http.createServer(async (req, res) => {
  let caminho;
  try { caminho = decodeURIComponent(new URL(req.url, "http://x").pathname); }
  catch { res.writeHead(400); return res.end("bad request"); }

  // ---- a placa reporta o que esta fazendo
  if (req.method === "POST" && caminho === "/api/motor") {
    const auth = req.headers.authorization || "";
    if (!SEGREDO || auth !== "Bearer " + SEGREDO) {
      res.writeHead(401); return res.end("unauthorized");
    }
    try {
      const d = JSON.parse(await corpo(req));
      if (!d || typeof d !== "object") throw new Error("json invalido");
      vivo.motor = d;
      vivo.motorEm = Date.now();
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ ok: true }));
    } catch (e) {
      res.writeHead(400); return res.end("bad json: " + e.message);
    }
  }

  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { Allow: "GET, HEAD, POST" });
    return res.end("method not allowed");
  }

  // ---- o arquivo que a tela le vem da memoria, nao do disco
  if (caminho === "/data/lotes.json") {
    const corpoJson = Buffer.from(JSON.stringify(montaLotes(), null, 1));
    res.writeHead(200, {
      "Content-Type": TIPOS[".json"],
      "Content-Length": corpoJson.length,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });
    return res.end(req.method === "HEAD" ? undefined : corpoJson);
  }

  // ---- diagnostico honesto, para conferir de fora se esta vivo
  if (caminho === "/api/estado") {
    const d = {
      chain_lida_ha_s: vivo.chainEm ? Math.round((Date.now() - vivo.chainEm) / 1000) : null,
      compras: vivo.compras ? vivo.compras.length : null,
      motor_recebido_ha_s: vivo.motorEm ? Math.round((Date.now() - vivo.motorEm) / 1000) : null,
      motor_estado: vivo.motor ? vivo.motor.estado : null,
      desde_bloco: vivo.desdeBloco,
      placas: custo ? custo.placas : null,
      chain_erro: vivo.chainErro,
    };
    const b = Buffer.from(JSON.stringify(d, null, 1));
    res.writeHead(200, { "Content-Type": TIPOS[".json"], "Cache-Control": "no-store" });
    return res.end(req.method === "HEAD" ? undefined : b);
  }

  if (caminho === "/" || caminho === "") caminho = "/index.html";
  const alvo = path.join(RAIZ, path.normalize(caminho));
  if (!alvo.startsWith(RAIZ)) { res.writeHead(403); return res.end("forbidden"); }

  fs.readFile(alvo, (err, dados) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      return res.end("not found");
    }
    const ext = path.extname(alvo).toLowerCase();
    const cab = {
      "Content-Type": TIPOS[ext] || "application/octet-stream",
      "Content-Length": dados.length,
      "Cache-Control": ext === ".html" || ext === ".json" ? "no-store"
                                                          : "public, max-age=3600",
      "X-Content-Type-Options": "nosniff",
    };
    if (ext === ".csv") {
      cab["Content-Disposition"] = 'attachment; filename="' + path.basename(alvo) + '"';
    }
    res.writeHead(200, cab);
    res.end(req.method === "HEAD" ? undefined : dados);
  });
});

servidor.listen(PORTA, () => console.log("EHRLICH servindo em :" + PORTA));

/* ------------------------------------------------------------- os relogios */
async function ciclo() {
  // as duas leituras sao independentes: em serie, o custo da placa so aparecia
  // depois da varredura inteira da chain, e a pagina mostrava travessao
  const [, c] = await Promise.all([
    leChain().catch((e) => {
      vivo.chainErro = e.message; console.error("chain:", e.message);
    }),
    custoDasPlacas().catch(() => null),
  ]);
  if (c) custo = c;
}
ciclo();
setInterval(ciclo, INTERVALO_CHAIN);
