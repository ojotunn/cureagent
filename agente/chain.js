// Leitura da pons. So LE: nenhuma chave, nenhuma assinatura, nenhuma carteira.
//
// As assinaturas abaixo foram DECODIFICADAS de um token real da pons
// (CDTEST, curva 0x7983…11B1) em 14/09/2026, lendo eth_getLogs e conferindo o
// formato de cada evento. Nao vieram de documentacao — vieram da chain.
//
//   COMPRA  0xec36bf57…   topic[1]=comprador  data[0]=ETH pago
//                         data[1]=tokens      data[2]=taxa
//   VENDA   0x8113d738…   topic[1]=vendedor   data[0]=tokens vendidos
//                         data[1]=ETH recebido data[2]=taxa

const RPC = process.env.PONS_RPC || "https://rpc.mainnet.chain.robinhood.com";

// o RPC recusa requisicao sem User-Agent de navegador (403)
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const EVENTO_COMPRA =
  "0xec36bf571f136799e8dc0b0b8bea4b04d8bd3d43de838aab0d5fc21d4cbfc455";
const EVENTO_VENDA =
  "0x8113d738abdcb6b38357e9d53a54a7157861a09031b453651f0fe7fe151f59df";

async function rpc(metodo, params) {
  const r = await fetch(RPC, {
    method: "POST",
    headers: { "Content-Type": "application/json", "User-Agent": UA },
    body: JSON.stringify({ jsonrpc: "2.0", method: metodo, params, id: 1 }),
  });
  if (!r.ok) throw new Error(`RPC ${metodo}: HTTP ${r.status}`);
  const d = await r.json();
  if (d.error) throw new Error(`RPC ${metodo}: ${JSON.stringify(d.error)}`);
  return d.result;
}

const paraNumero = (hex) => BigInt(hex);
const wei = (x) => Number(x) / 1e18;
const endereco = (topic) => "0x" + topic.slice(-40);

function palavras(data) {
  const s = data.startsWith("0x") ? data.slice(2) : data;
  const out = [];
  for (let i = 0; i < s.length; i += 64) out.push(BigInt("0x" + s.slice(i, i + 64)));
  return out;
}

async function blocoAtual() {
  return Number(paraNumero(await rpc("eth_blockNumber", [])));
}

/** Compras e vendas de uma curva, entre dois blocos. */
async function negociacoes(curva, deBloco, ateBloco = "latest") {
  const logs = await rpc("eth_getLogs", [{
    address: curva,
    fromBlock: typeof deBloco === "number" ? "0x" + deBloco.toString(16) : deBloco,
    toBlock: typeof ateBloco === "number" ? "0x" + ateBloco.toString(16) : ateBloco,
  }]);

  const eventos = [];
  for (const l of logs) {
    const assinatura = l.topics?.[0];
    if (assinatura !== EVENTO_COMPRA && assinatura !== EVENTO_VENDA) continue;
    const d = palavras(l.data);
    const compra = assinatura === EVENTO_COMPRA;
    eventos.push({
      tipo: compra ? "compra" : "venda",
      quem: endereco(l.topics[1]),
      eth: wei(compra ? d[0] : d[1]),
      tokens: wei(compra ? d[1] : d[0]),
      taxa: wei(d[2] ?? 0n),
      bloco: Number(paraNumero(l.blockNumber)),
      tx: l.transactionHash,
      indice: Number(paraNumero(l.logIndex)),
    });
  }
  eventos.sort((a, b) => a.bloco - b.bloco || a.indice - b.indice);
  return eventos;
}

/** Hora de um bloco, para carimbar o lote com tempo real. */
async function horaDoBloco(numero) {
  const b = await rpc("eth_getBlockByNumber",
                      ["0x" + numero.toString(16), false]);
  return b ? new Date(Number(paraNumero(b.timestamp)) * 1000) : null;
}

module.exports = { rpc, blocoAtual, negociacoes, horaDoBloco,
                   EVENTO_COMPRA, EVENTO_VENDA };
