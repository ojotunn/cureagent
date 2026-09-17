// Servidor do EHRLICH — pump.fun / Solana.
//
// Tres responsabilidades, nenhuma dependendo de maquina de desenvolvedor:
//   1. COLETA as compras do token na pump.fun e grava cada uma em disco;
//   2. RECEBE o estado da placa por POST /api/motor, autenticado por segredo;
//   3. SERVE /data/lotes.json a partir disso.
//
// -------------------------------------------------------------------------
// A MUDANCA DE DESENHO QUE IMPORTA
//
// No lancamento anterior (pons) cada compra ganhava uma COTA FIXA de moleculas:
// 250.000 por ETH. Isso criou uma divida impagavel. 57 compradores financiaram
// 4.253.843 moleculas e nenhuma foi triada, porque a cota era calculada sobre o
// VOLUME comprado enquanto o projeto so recebe a TAXA DE CRIADOR, que e uma
// fracao pequena do volume. A promessa era maior que a receita por construcao,
// antes de qualquer bug.
//
// Aqui nao existe cota. Cada compra tem o que a pessoa pagou e a FATIA que
// aquilo representa do total pago. As moleculas sao repartidas por essa fatia
// conforme sao triadas de verdade. Nao da para dever molecula nenhuma, porque
// as moleculas sao o trabalho que ja aconteceu, nao um numero prometido.
// -------------------------------------------------------------------------
//
// Nenhuma dependencia: o build no Railway nao instala nada.

const http = require("http");
const fs = require("fs");
const path = require("path");
const { tradesRecentes, ficha } = require("./agente/pump.js");
const { Deposito } = require("./agente/deposito.js");

const RAIZ = path.join(__dirname, "site");
const PORTA = process.env.PORT || 8440;
const SEGREDO = process.env.EHRLICH_TOKEN || "";
const DADOS = process.env.DADOS || path.join(__dirname, "dados");
const INTERVALO = Number(process.env.INTERVALO_COLETA || 6) * 1000;

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

const deposito = new Deposito(DADOS);
const aberto = deposito.abre();
console.log("deposito: " + aberto.compras + " compras conhecidas" +
            (aberto.ruins ? " (" + aberto.ruins + " linhas ilegiveis ignoradas)" : ""));

const vivo = {
  motor: null,
  motorEm: 0,
  coletaEm: 0,
  coletaErro: null,
  ficha: null,
  novasNoUltimo: 0,
};

/* ------------------------------------------------------------- coleta */
async function coleta() {
  const tk = leJSON(path.join(RAIZ, "token.json"), {});
  if (!tk.mint) {                     // antes do lancamento nao ha o que coletar
    vivo.coletaErro = null;
    return;
  }
  deposito.fixaMint(tk.mint);
  const trades = await tradesRecentes(tk.mint);
  const novas = deposito.registra(trades);
  vivo.novasNoUltimo = novas.length;
  vivo.coletaEm = Date.now();
  vivo.coletaErro = null;
  if (novas.length) console.log("coleta: +" + novas.length + " compras");
}

/* --------------------------------------------- custo real das placas */
async function custoDasPlacas() {
  const chave = process.env.RUNPOD_API_KEY;
  const ids = (process.env.RUNPOD_POD_IDS || "")
                .split(",").map((s) => s.trim()).filter(Boolean);
  if (!chave || !ids.length) return null;

  // gasto = soma de (horas de cada placa x preco dela). Somar horas e
  // multiplicar pela soma dos precos erraria com placas de idades diferentes.
  let gasto = 0, precoHora = 0, maisVelha = 0, vivas = 0;
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
      gasto += h * (Number(p.costPerHr) || 0);
      precoHora += Number(p.costPerHr) || 0;
      if (h > maisVelha) maisVelha = h;
      vivas += 1;
    } catch { /* uma placa fora nao derruba a conta das outras */ }
  }
  if (!vivas) return null;
  return { horas: maisVelha, hora: precoHora, placas: vivas, gasto };
}
let custo = null;

/* ------------------------------------------------- monta o lotes.json */
function montaLotes() {
  const disco = leJSON(path.join(RAIZ, "data", "lotes.json"), {});
  const tk = leJSON(path.join(RAIZ, "token.json"), {});

  const fresco = vivo.motor && (Date.now() - vivo.motorEm) < 360000;
  const m = fresco ? Object.assign({}, vivo.motor) : null;
  if (m && custo) {
    m.placas = custo.placas;
    m.gpu_hora = Number(custo.hora.toFixed(2));
    m.gpu_gasto_usd = Number(custo.gasto.toFixed(2));
    m.horas = Number(custo.horas.toFixed(2));
  }

  const compras = deposito.compras();
  const totalUsd = compras.reduce((s, c) => s + (c.usd || 0), 0);
  const triadas = (m && m.triadas) || 0;

  // fatia de cada comprador no total pago, e as moleculas que essa fatia ja
  // rendeu. Nada aqui e promessa: e reparticao de trabalho ja feito.
  const lotes = compras.map((c) => {
    const fatia = totalUsd > 0 ? (c.usd || 0) / totalUsd : 0;
    const minhas = Math.floor(triadas * fatia);
    return {
      ts: c.ts ? new Date(c.ts).toISOString().slice(0, 16).replace("T", " ") : null,
      endereco: c.quem,
      sol: Number((c.sol || 0).toFixed(6)),
      usd: Number((c.usd || 0).toFixed(2)),
      fatia: Number((fatia * 100).toFixed(3)),
      moleculas: minhas || null,
      tx: c.tx,
      estado: triadas > 0 ? (m && m.estado === "screening" ? "running" : "credited")
                          : "waiting",
    };
  });

  const enderecos = {};
  for (const l of lotes) enderecos[l.endereco] = 1;
  const integridade = deposito.integridade();

  return {
    _comentario: disco._comentario,
    rede: "Solana · pump.fun",
    mint: tk.mint || null,
    modo: m ? "live" : "parado",
    mostrar_endereco: disco.mostrar_endereco || "truncado",
    atualizado_em: new Date().toISOString().slice(0, 16).replace("T", " "),
    fonte: "servidor: compras coletadas da pump.fun e gravadas em disco",
    integridade,
    resumo: {
      financiadores: Object.keys(enderecos).length,
      compras: lotes.length,
      pago_usd: Number(totalUsd.toFixed(2)),
      moleculas_triadas: triadas,
      minutos_gpu: Math.round(((custo && custo.horas) || 0) * 60),
    },
    motor: m,
    fila_alvos: (fresco && vivo.motor.fila_alvos) || disco.fila_alvos || null,
    pausado: m ? null : (disco.pausado || null),
    ficha: vivo.ficha,
    lotes,
  };
}

/* ---------------------------------------------------------------- HTTP */
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

  if (caminho === "/data/lotes.json") {
    const b = Buffer.from(JSON.stringify(montaLotes(), null, 1));
    res.writeHead(200, {
      "Content-Type": TIPOS[".json"], "Content-Length": b.length,
      "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    });
    return res.end(req.method === "HEAD" ? undefined : b);
  }

  // diagnostico honesto, conferivel de fora
  if (caminho === "/api/estado") {
    const tk = leJSON(path.join(RAIZ, "token.json"), {});
    const d = {
      rede: "solana/pump.fun",
      mint: tk.mint || null,
      coleta_ha_s: vivo.coletaEm ? Math.round((Date.now() - vivo.coletaEm) / 1000) : null,
      coleta_erro: vivo.coletaErro,
      novas_no_ultimo_ciclo: vivo.novasNoUltimo,
      integridade: deposito.integridade(),
      motor_recebido_ha_s: vivo.motorEm
        ? Math.round((Date.now() - vivo.motorEm) / 1000) : null,
      motor_estado: vivo.motor ? vivo.motor.estado : null,
      placas: custo ? custo.placas : null,
      deposito: DADOS,
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

/* ---------------------------------------------------------- os relogios */
async function ciclo() {
  await coleta().catch((e) => {
    vivo.coletaErro = e.message;
    console.error("coleta:", e.message);
  });
}
async function cicloLento() {
  const tk = leJSON(path.join(RAIZ, "token.json"), {});
  if (tk.mint) {
    const f = await ficha(tk.mint).catch(() => null);
    if (f) vivo.ficha = f;
  }
  const c = await custoDasPlacas().catch(() => null);
  if (c) custo = c;
}
ciclo(); cicloLento();
setInterval(ciclo, INTERVALO);
setInterval(cicloLento, 90000);
