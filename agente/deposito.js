// Deposito das compras. Append-only, uma linha por compra, chaveado pela
// assinatura da transacao.
//
// Este arquivo E a memoria do projeto sobre quem pagou. A API da pump.fun so
// mostra as ~100 compras mais recentes e nao pagina, entao o que nao for
// gravado aqui na hora esta perdido para sempre. Por isso:
//
//   - append-only: nunca reescreve linha, nunca apaga. Um bug meu no futuro
//     pode gravar besteira nova, mas nao pode sumir com comprador antigo.
//   - chaveado por assinatura: reprocessar a mesma janela da API e inofensivo.
//   - registra QUANDO o coletor comecou. Se ele subiu depois do lancamento, a
//     fila esta incompleta e o site tem que dizer isso, nao fingir que esta
//     inteira. Foi essa mentira silenciosa que sumiu com os 38 primeiros
//     compradores no pons.

const fs = require("fs");
const path = require("path");

class Deposito {
  constructor(dir) {
    this.dir = dir;
    this.arqCompras = path.join(dir, "compras.jsonl");
    this.arqMeta = path.join(dir, "coletor.json");
    this.porTx = new Map();
    this.meta = null;
  }

  abre() {
    fs.mkdirSync(this.dir, { recursive: true });

    // meta: quando o coletor comecou a olhar
    try {
      this.meta = JSON.parse(fs.readFileSync(this.arqMeta, "utf8"));
    } catch {
      this.meta = { iniciado_em: new Date().toISOString(), mint: null };
      this._gravaMeta();
    }

    // compras ja conhecidas
    let linhas = 0, ruins = 0;
    try {
      const bruto = fs.readFileSync(this.arqCompras, "utf8");
      for (const l of bruto.split("\n")) {
        if (!l.trim()) continue;
        linhas++;
        try {
          const c = JSON.parse(l);
          if (c && c.tx) this.porTx.set(c.tx, c);
        } catch { ruins++; }
      }
    } catch { /* primeira vez */ }
    return { linhas, ruins, compras: this.porTx.size };
  }

  _gravaMeta() {
    fs.writeFileSync(this.arqMeta, JSON.stringify(this.meta, null, 1));
  }

  /** Marca qual token o coletor esta seguindo. */
  fixaMint(mint) {
    if (this.meta.mint === mint) return;
    this.meta.mint = mint;
    this.meta.mint_fixado_em = new Date().toISOString();
    this._gravaMeta();
  }

  /**
   * Grava as compras que ainda nao conhecia. Devolve as novas.
   * Escreve com fsync para nao perder compra num reinicio do container.
   */
  registra(trades) {
    const novas = [];
    for (const t of trades) {
      if (t.tipo !== "compra") continue;
      if (!t.tx || this.porTx.has(t.tx)) continue;
      const c = {
        tx: t.tx, quem: t.quem, sol: t.sol, usd: t.usd,
        ts: t.ts, cursor: t.cursor,
        visto_em: new Date().toISOString(),
      };
      this.porTx.set(t.tx, c);
      novas.push(c);
    }
    if (novas.length) {
      const fh = fs.openSync(this.arqCompras, "a");
      try {
        fs.writeSync(fh, novas.map((c) => JSON.stringify(c)).join("\n") + "\n");
        fs.fsyncSync(fh);
      } finally {
        fs.closeSync(fh);
      }
    }
    return novas;
  }

  /** Todas as compras, da mais nova para a mais velha. */
  compras() {
    return [...this.porTx.values()].sort((a, b) => (b.ts || 0) - (a.ts || 0));
  }

  /**
   * A fila esta completa? So se o coletor comecou antes da primeira compra.
   * Sem isto o site afirmaria uma fila inteira que ele nunca viu inteira.
   */
  integridade() {
    const todas = this.compras();
    const inicio = Date.parse(this.meta.iniciado_em) || null;
    const primeira = todas.length ? Math.min(...todas.map((c) => c.ts || Infinity)) : null;
    const completa = inicio != null && (primeira == null || inicio <= primeira);
    return {
      coletor_desde: this.meta.iniciado_em,
      primeira_compra: primeira ? new Date(primeira).toISOString() : null,
      completa,
      compras: todas.length,
    };
  }
}

module.exports = { Deposito };
