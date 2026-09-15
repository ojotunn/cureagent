// Transforma compras da curva em lotes, e escreve o que o site le.
//
// Regra dura: um lote so diz "moleculas triadas" depois que a placa rodou de
// verdade. Antes disso ele fica em fila, e a tela diz isso. Nunca inventar
// numero para a pagina parecer mais viva do que esta.

const fs = require("fs");
const path = require("path");
const { negociacoes, blocoAtual, horaDoBloco } = require("./chain.js");

const RAIZ = path.join(__dirname, "..");
const ARQ_LOTES = path.join(RAIZ, "site", "data", "lotes.json");
const ARQ_TOKEN = path.join(RAIZ, "site", "token.json");

// quantas moleculas cada ETH comprado financia. Derivado do custo de placa:
// a A5000 sai a $0,16/h e faz da ordem de 12k moleculas/hora na estimativa
// atual — o numero real substitui este assim que a primeira hora for medida.
const MOLECULAS_POR_ETH = Number(process.env.MOLECULAS_POR_ETH || 250000);

function leJSON(p, padrao) {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return padrao; }
}

function trunca(e) { return e ? `${e.slice(0, 6)}…${e.slice(-4)}` : ""; }

async function varre({ desdeBloco, ate } = {}) {
  const tk = leJSON(ARQ_TOKEN, {});
  if (!tk.curva) throw new Error("token.json sem a curva — nada a varrer");

  const fim = ate ?? await blocoAtual();
  const de = desdeBloco ?? Math.max(0, fim - 200000);

  // a chain recusa janelas muito grandes: varre em fatias
  const FATIA = 50000;
  const eventos = [];
  for (let b = de; b <= fim; b += FATIA) {
    const ateFatia = Math.min(b + FATIA - 1, fim);
    try {
      eventos.push(...await negociacoes(tk.curva, b, ateFatia));
    } catch (e) {
      console.error(`  fatia ${b}-${ateFatia} falhou: ${e.message}`);
    }
  }

  const compras = eventos.filter((e) => e.tipo === "compra");
  console.log(`${eventos.length} negociacoes (${compras.length} compras) ` +
              `entre os blocos ${de} e ${fim}`);
  return { compras, vendas: eventos.length - compras.length, de, fim };
}

async function escreve({ compras, modo = "queued" }) {
  const anterior = leJSON(ARQ_LOTES, {});
  const jaTem = new Map((anterior.lotes || []).map((l) => [l.tx + ":" + l.log, l]));

  const lotes = [];
  for (const c of compras) {
    const chave = c.tx + ":" + c.indice;
    const existente = jaTem.get(chave);
    if (existente && existente.estado === "pronto") {
      lotes.push(existente);       // ja rodou: nao mexe
      continue;
    }
    const hora = await horaDoBloco(c.bloco);
    lotes.push({
      ts: hora ? hora.toISOString().slice(0, 16).replace("T", " ") : null,
      endereco: c.quem,
      eth: Number(c.eth.toFixed(6)),
      moleculas: existente?.moleculas ?? null,   // null = ainda nao rodou
      melhor: existente?.melhor ?? null,
      gpu_min: existente?.gpu_min ?? null,
      cota: Math.round(c.eth * MOLECULAS_POR_ETH),  // quanto ESTE lote da direito
      tx: c.tx,
      log: c.indice,
      bloco: c.bloco,
      estado: existente?.estado ?? "queued",
    });
  }
  lotes.sort((a, b) => (b.bloco || 0) - (a.bloco || 0));

  const prontos = lotes.filter((l) => l.estado === "pronto");
  const saida = {
    _comentario: anterior._comentario,
    modo,
    mostrar_endereco: anterior.mostrar_endereco || "truncado",
    atualizado_em: new Date().toISOString().slice(0, 16).replace("T", " "),
    resumo: {
      financiadores: new Set(lotes.map((l) => l.endereco)).size,
      moleculas_financiadas: prontos.reduce((s, l) => s + (l.moleculas || 0), 0),
      minutos_gpu: prontos.reduce((s, l) => s + (l.gpu_min || 0), 0),
      na_fila: lotes.filter((l) => l.estado === "queued").length,
      cota_total: lotes.reduce((s, l) => s + (l.cota || 0), 0),
    },
    lotes,
  };
  fs.writeFileSync(ARQ_LOTES, JSON.stringify(saida, null, 1));
  return saida;
}

module.exports = { varre, escreve, trunca };

if (require.main === module) {
  (async () => {
    const { compras } = await varre({});
    const s = await escreve({ compras });
    console.log(`\n${s.resumo.financiadores} financiadores · ` +
                `${s.resumo.na_fila} lotes na fila · ` +
                `${s.resumo.cota_total.toLocaleString("en-US")} moleculas de cota`);
    for (const l of s.lotes.slice(0, 8))
      console.log(`  ${l.ts}  ${trunca(l.endereco)}  ${l.eth} ETH  ` +
                  `cota ${l.cota.toLocaleString("en-US")}  [${l.estado}]`);
  })().catch((e) => { console.error("erro:", e.message); process.exit(1); });
}
