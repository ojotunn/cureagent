// Leitura de compras na pump.fun (Solana). So LE: nenhuma chave, nenhuma
// assinatura, nenhuma carteira.
//
// POR QUE ESTE DESENHO, e nao uma varredura da chain como no pons:
//
// A API de trades da pump.fun (swap-api v2) entrega compra e venda ja
// normalizadas, com endereco, SOL, dolar, hora e assinatura, e continua
// funcionando DEPOIS que o token gradua para o AMM. Medido em 16/09/2026: o
// teto do parametro limit esta entre 100 e 150, e NENHUM parametro de
// paginacao funciona — before, cursor, offset, page e skip sao todos
// ignorados e a resposta e sempre a mais recente.
//
// Ler o historico pelo RPC da Solana e possivel (6000 assinaturas em 3,8s pela
// Helius) mas exige decodificar dois formatos de evento diferentes, um para a
// curva e outro para o AMM, e inferir quem e o comprador entre a pool e o
// pagador da taxa, que na Solana raramente sao a mesma conta. Isso quebra
// quando a pump.fun muda o layout.
//
// Entao: este modulo le o presente, e quem guarda o passado e o arquivo em
// disco (deposito.js). A consequencia operacional e uma regra dura, e foi por
// nao cumprir o equivalente dela no pons que os 38 primeiros compradores
// sumiram da fila: O COLETOR TEM QUE ESTAR DE PE ANTES DO LANCAMENTO.

const SWAP = "https://swap-api.pump.fun/v2";
const FRONT = "https://frontend-api-v3.pump.fun";

// a API responde 403 sem User-Agent de navegador
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
           "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

// medido: 100 passa, 150 e recusado com lista vazia
const TETO_LIMIT = 100;

async function pega(url, tentativas = 3) {
  let espera = 1200;
  for (let i = 0; i < tentativas; i++) {
    try {
      const r = await fetch(url, {
        headers: { "user-agent": UA, accept: "application/json" },
      });
      if (r.status === 429 || r.status >= 500) throw new Error("http " + r.status);
      if (!r.ok) throw new Error("http " + r.status);
      return await r.json();
    } catch (e) {
      if (i === tentativas - 1) throw e;
      await new Promise((ok) => setTimeout(ok, espera));
      espera *= 2;
    }
  }
}

/**
 * Os trades mais recentes do token, do mais antigo para o mais novo.
 * Cada item: {tipo, sol, usd, quem, ts, tx, cursor}
 */
async function tradesRecentes(mint, limite = TETO_LIMIT) {
  const n = Math.min(Math.max(1, limite | 0), TETO_LIMIT);
  const j = await pega(SWAP + "/coins/" + mint + "/trades?limit=" + n);
  const lista = Array.isArray(j) ? j : (j && j.trades) || [];
  const saida = [];
  for (const t of lista) {
    const tipo = t.type === "buy" ? "compra" : t.type === "sell" ? "venda" : null;
    if (!tipo) continue;
    const tx = String(t.tx || "");
    if (!tx) continue;                      // sem assinatura nao da para deduplicar
    saida.push({
      tipo,
      sol: Number(t.amountSol || 0),
      usd: Number(t.amountUsd || 0),
      quem: String(t.userAddress || ""),
      ts: Date.parse(t.timestamp) || null,
      tx,
      cursor: String(t.slotIndexId || ""),
    });
  }
  // a API devolve do mais novo para o mais velho
  saida.reverse();
  return saida;
}

/** Ficha do token: preco, market cap, se graduou. Tolerante a falha. */
async function ficha(mint) {
  try {
    const c = await pega(FRONT + "/coins/" + mint, 2);
    return {
      nome: c.name || null,
      ticker: c.symbol || null,
      mcap_usd: Number(c.usd_market_cap || 0) || null,
      graduou: !!c.complete,
      criador: c.creator || null,
      criado_em: c.created_timestamp ? Number(c.created_timestamp) : null,
    };
  } catch {
    return null;
  }
}

module.exports = { tradesRecentes, ficha, TETO_LIMIT };

if (require.main === module) {
  const mint = process.argv[2];
  if (!mint) {
    console.error("uso: node pump.js <mint>");
    process.exit(1);
  }
  (async () => {
    const f = await ficha(mint);
    console.log("ficha:", JSON.stringify(f));
    const t = await tradesRecentes(mint);
    const compras = t.filter((x) => x.tipo === "compra");
    console.log(t.length + " trades lidos, " + compras.length + " compras");
    for (const c of compras.slice(-6)) {
      console.log("  " + new Date(c.ts).toISOString().slice(0, 19) +
                  "  " + c.quem.slice(0, 8) +
                  "  " + c.sol.toFixed(5) + " SOL" +
                  "  $" + c.usd.toFixed(2) +
                  "  " + c.tx.slice(0, 10));
    }
  })().catch((e) => { console.error("erro:", e.message); process.exit(1); });
}
