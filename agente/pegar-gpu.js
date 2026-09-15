// Fica tentando ligar uma placa ate conseguir.
//
// A RunPod esvazia e enche o tempo todo; "no instances currently available" nao
// e erro, e fila. Este script percorre as placas por preco e repete ate pegar.
//
// Cuidado que custou uma GPU: NUNCA destruir o pod que esta rodando antes de o
// substituto estar de pe. Aqui so se cria.

const fs = require("fs");
const path = require("path");

const API = "https://rest.runpod.io/v1";
// sem User-Agent de navegador o Cloudflare devolve 403 (error 1010)
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
           "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const GPUS = [
  ["NVIDIA RTX A5000", 0.160], ["NVIDIA RTX A4000", 0.170],
  ["NVIDIA RTX 4000 SFF Ada Generation", 0.180], ["NVIDIA RTX A4500", 0.190],
  ["NVIDIA GeForce RTX 3090", 0.220], ["NVIDIA GeForce RTX 4090", 0.340],
  ["NVIDIA RTX A6000", 0.490], ["NVIDIA L4", 0.430],
  ["NVIDIA RTX 2000 Ada Generation", 0.280], ["NVIDIA L40S", 0.860],
];

const chave = () => {
  const env = fs.readFileSync(path.join(__dirname, "..", ".env"), "utf8");
  const m = env.match(/^RUNPOD_API_KEY=(.+)$/m);
  if (!m) throw new Error("RUNPOD_API_KEY ausente");
  return m[1].trim();
};

async function tenta(gpu, cloud, pub, K) {
  const r = await fetch(`${API}/pods`, {
    method: "POST",
    headers: { Authorization: `Bearer ${K}`, "Content-Type": "application/json",
               "User-Agent": UA },
    body: JSON.stringify({
      name: "ehrlich-docking",
      imageName: "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04",
      gpuTypeIds: [gpu], gpuCount: 1,
      containerDiskInGb: 40, volumeInGb: 0,
      cloudType: cloud, ports: ["22/tcp"],
      env: { PUBLIC_KEY: pub },
    }),
  });
  const t = await r.text();
  let d; try { d = JSON.parse(t); } catch { d = { erro: t.slice(0, 80) }; }
  return r.ok && d.id ? d : null;
}

async function main() {
  const K = chave();
  const pub = fs.readFileSync(
    path.join(process.env.USERPROFILE || process.env.HOME, ".ssh",
              "flypad_runpod.pub"), "utf8").trim();

  const limite = Number(process.env.TENTATIVAS || 40);
  for (let volta = 1; volta <= limite; volta++) {
    for (const cloud of ["COMMUNITY", "SECURE"]) {
      for (const [gpu, preco] of GPUS) {
        const p = await tenta(gpu, cloud, pub, K);
        if (p) {
          console.log(`LIGOU  ${gpu} [${cloud}]  $${p.costPerHr}/h  id=${p.id}`);
          fs.writeFileSync(path.join(__dirname, "..", "pod.id"), p.id);
          return p;
        }
      }
    }
    console.log(`volta ${volta}: nada livre ainda, esperando 30s…`);
    await new Promise((r) => setTimeout(r, 30000));
  }
  console.log("nenhuma placa apareceu no limite de tentativas");
  return null;
}

if (require.main === module) main().catch((e) => {
  console.error("erro:", e.message); process.exit(1);
});
module.exports = { main };
