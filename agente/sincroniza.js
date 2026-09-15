// Puxa o que a placa produziu e publica no site.
//
// Distingue as duas coisas que a placa faz, porque so uma delas e o que os
// compradores pagaram:
//
//   VALIDACAO  - o portao de qualidade do projeto. Doca inibidores medidos
//                contra decoys e mede o AUC. NAO abate a fila de ninguem.
//   TRIAGEM    - a busca de verdade, so num alvo que passou no portao.
//                Ai sim cada molecula abate a cota de quem pagou.
//
// Confundir as duas seria dizer que o dinheiro virou busca quando virou teste.

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const RAIZ = path.join(__dirname, "..");
const [IP, PORTA] = fs.readFileSync(path.join(RAIZ, "pod.ssh"), "utf8").trim().split(/\s+/);
const CHAVE = path.join(process.env.USERPROFILE || process.env.HOME, ".ssh", "flypad_runpod");
const SSH = `ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ` +
            `-o ConnectTimeout=25 -i "${CHAVE}" -p ${PORTA} root@${IP}`;

const GPU = "RTX 4000 SFF Ada";

// .env sem dependencia: a chave da RunPod nunca e impressa
try {
  const bruto = fs.readFileSync(path.join(RAIZ, ".env"), "utf8");
  for (let l of bruto.split(String.fromCharCode(10))) {
    l = l.replace(String.fromCharCode(13), "");
    if (!l || l.trim().startsWith("#")) continue;
    const j = l.indexOf("=");
    if (j <= 0) continue;
    const k = l.slice(0, j).trim(), v = l.slice(j + 1).trim();
    if (k && !process.env[k]) process.env[k] = v;
  }
} catch {}

const POD_ID = (() => {
  try { return fs.readFileSync(path.join(RAIZ, "pod.id"), "utf8").trim(); }
  catch { return null; }
})();

// Quanto a placa ja custou NESTA corrida. Vem da RunPod, nao de estimativa minha.
async function custoDaPlaca() {
  if (!POD_ID || !process.env.RUNPOD_API_KEY) return null;
  try {
    const r = await fetch("https://rest.runpod.io/v1/pods/" + POD_ID,
      { headers: { Authorization: "Bearer " + process.env.RUNPOD_API_KEY } });
    if (!r.ok) return null;
    const p = await r.json();
    const ini = Date.parse(String(p.lastStartedAt || p.createdAt || "")
                             .replace(" +0000 UTC", "Z").replace(" ", "T"));
    if (!ini) return null;
    const horas = (Date.now() - ini) / 3600000;
    const hora = Number(p.costPerHr) || 0;
    return { horas, hora, gasto: horas * hora };
  } catch { return null; }
}

function remoto(cmd) {
  try {
    return execSync(`${SSH} "${cmd.replace(/"/g, '\\"')}"`,
                    { encoding: "utf8", timeout: 90000,
                      stdio: ["ignore", "pipe", "ignore"] });
  } catch { return ""; }
}

// uma viagem so: tudo que a tela precisa, separado por marcadores
function leituraDoPod() {
  const bruto = remoto([
    "echo '<<VAL>>'; pgrep -f '[v]alida.py' | wc -l",
    "echo '<<TRI>>'; pgrep -f '[r]oda.sh' | wc -l",
    "echo '<<LOG>>'; tail -25 /work/out/valida.log 2>/dev/null",
    "echo '<<DOCK>>'; ls /work/docked/*.txt 2>/dev/null | wc -l",
    "echo '<<RES>>'; cat /work/out/resultado.json 2>/dev/null",
    "echo '<<PROG>>'; cat /work/out/progresso.json 2>/dev/null",
    "echo '<<SCORES>>'; wc -l < /work/out/scores.jsonl 2>/dev/null",
    "echo '<<NUC>>'; nproc",
    "echo '<<FIM>>'",
  ].join("; "));

  const p = (a, b) => {
    const i = bruto.indexOf(`<<${a}>>`), j = bruto.indexOf(`<<${b}>>`);
    return i < 0 || j < 0 ? "" : bruto.slice(i + a.length + 4, j).trim();
  };
  return {
    validando: Number(p("VAL", "TRI")) > 0,
    triando: Number(p("TRI", "LOG")) > 0,
    log: p("LOG", "DOCK"),
    docadas: Number(p("DOCK", "RES")) || 0,
    resultado: (() => { try { return JSON.parse(p("RES", "PROG")); } catch { return null; } })(),
    progresso: (() => { try { return JSON.parse(p("PROG", "SCORES")); } catch { return null; } })(),
    triadas: Number(p("SCORES", "NUC")) || 0,
    nucleos: Number(p("NUC", "FIM")) || 56,
  };
}

// a ultima linha do log do validador vira a frase que a pagina mostra
const ETAPAS = [
  [/procurando cristal/i,   "searching for a non-covalent crystal"],
  [/escolhido:/i,           "crystal chosen"],
  [/preparando receptor/i,  "preparing the receptor"],
  [/caixa:/i,               "binding box measured"],
  [/inibidores medidos/i,   "collecting measured inhibitors from ChEMBL"],
  [/decoys pareados/i,      "pairing property-matched decoys"],
  [/gerando 3D/i,           "generating 3D conformers"],
  [/docking em/i,           "docking actives against decoys"],
  [/resultado/i,            "computing enrichment"],
];

// o cristal escolhido sai do proprio log do validador, nao de um palpite meu
function cristalDoLog(log) {
  const m = log.match(new RegExp("escolhido ([A-Za-z0-9]+)/([A-Za-z0-9]+)"));
  return m ? { pdb: m[1], ligante: m[2] } : null;
}

function etapaDoLog(log) {
  const linhas = log.split("\n").map((l) => l.trim()).filter(Boolean);
  for (let i = linhas.length - 1; i >= 0; i--) {
    for (const [re, txt] of ETAPAS) if (re.test(linhas[i])) return txt;
  }
  return "starting up";
}

function montaMotor(d, custo) {
  if (d.validando || (d.resultado && !d.triando)) {
    const r = d.resultado;
    return {
      estado: "validating",
      etapa: r ? (r.auc >= 0.70 ? "passed the gate" : "failed the gate")
               : etapaDoLog(d.log),
      alvo: "T. cruzi trypanothione reductase",
      alvo_nota: "Deep hydrophobic pocket, organic FAD cofactor, no catalytic " +
                 "metal — the three properties the two rejected targets lacked.",
      receptor: r ? `PDB ${r.pdb}`
               : (cristalDoLog(d.log) ? `PDB ${cristalDoLog(d.log).pdb}` : "selecting crystal"),
      gpu: GPU,
      gpu_hora: custo ? Number(custo.hora.toFixed(2)) : null,
      gpu_gasto_usd: custo ? Number(custo.gasto.toFixed(2)) : null,
      horas: custo ? Number(custo.horas.toFixed(2)) : null,
      nucleos: d.nucleos,
      docadas: d.docadas,
      auc: r ? Number(r.auc.toFixed(3)) : null,
      corte: 0.70,
      atualizado: new Date().toISOString().slice(0, 16).replace("T", " "),
    };
  }
  if (d.triando) {
    return {
      estado: "screening",
      etapa: "screening the funded library",
      receptor: d.progresso?.receptor || "—",
      gpu: GPU,
      gpu_hora: custo ? Number(custo.hora.toFixed(2)) : null,
      gpu_gasto_usd: custo ? Number(custo.gasto.toFixed(2)) : null,
      horas: custo ? Number(custo.horas.toFixed(2)) : null,
      nucleos: d.nucleos,
      triadas: d.triadas,
      por_hora: d.progresso?.por_hora || null,
      seg_por_molecula: d.progresso?.seg_por_molecula || null,
      atualizado: new Date().toISOString().slice(0, 16).replace("T", " "),
    };
  }
  return null;
}

function publica(d, custo) {
  const arq = path.join(RAIZ, "site", "data", "lotes.json");
  const j = JSON.parse(fs.readFileSync(arq, "utf8"));
  const motor = montaMotor(d, custo);

  j.modo = motor ? "live" : "parado";
  j.motor = motor;

  // A fila so anda com TRIAGEM. Validacao nao gasta cota de comprador.
  if (motor && motor.estado === "screening") {
    let resta = d.triadas;
    const lotes = [...(j.lotes || [])].sort((a, b) => (a.bloco || 0) - (b.bloco || 0));
    for (const l of lotes) {
      const cota = l.cota || 0;
      const feito = resta <= 0 ? 0 : Math.min(cota, resta);
      l.moleculas = feito;
      l.estado = feito >= cota && cota > 0 ? "pronto" : feito > 0 ? "running" : "queued";
      resta -= feito;
    }
    j.lotes = lotes.sort((a, b) => (b.bloco || 0) - (a.bloco || 0));
    j.resumo = {
      ...j.resumo,
      moleculas_financiadas: lotes.reduce((s, l) => s + (l.moleculas || 0), 0),
      na_fila: lotes.filter((l) => l.estado === "queued").length,
    };
  }

  fs.writeFileSync(arq, JSON.stringify(j, null, 1));
  return motor;
}

function deploy(msg) {
  try {
    execSync("git add -A", { cwd: RAIZ, stdio: "ignore" });
    execSync(`git -c user.name=ojotunn -c user.email=jotunnartworks@gmail.com ` +
             `commit -q -m "${msg}"`, { cwd: RAIZ, stdio: "ignore" });
    execSync("git push -q origin main", { cwd: RAIZ, stdio: "ignore", timeout: 180000 });
    // o Railway deste projeto nao deploya sozinho no push: tem que mandar subir
    execSync("railway up --service cureagent --detach",
             { cwd: RAIZ, stdio: "ignore", timeout: 300000 });
    return true;
  } catch { return false; }
}

async function main() {
  const intervalo = Number(process.env.INTERVALO || 120) * 1000;
  let assinatura = "";
  for (;;) {
    try {
      const d = leituraDoPod();
      const custo = await custoDaPlaca();
      const m = publica(d, custo);
      const nova = JSON.stringify([m?.estado, m?.etapa, m?.docadas, m?.triadas, m?.auc]);
      if (nova !== assinatura) {
        const ok = deploy(
          m ? `Engine: ${m.estado} · ${m.etapa}` + 
              (m.docadas ? ` · ${m.docadas} docked` : "") +
              (m.triadas ? ` · ${m.triadas} screened` : "")
            : "Engine: idle");
        console.log(`${new Date().toISOString().slice(11, 19)}  ` +
                    `${m?.estado || "parado"} · ${m?.etapa || "-"} · ` +
                    `docked ${m?.docadas ?? "-"} · push ${ok ? "ok" : "falhou"}`);
        assinatura = nova;
      }
    } catch (e) {
      console.log("erro no ciclo:", e.message);
    }
    await new Promise((r) => setTimeout(r, intervalo));
  }
}

if (require.main === module) main();
