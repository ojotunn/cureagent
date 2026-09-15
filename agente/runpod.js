// Aluguel de placa na RunPod, pela API REST v1.
//
// O pod so existe enquanto ha fila. Sem compra, sem pod, sem custo — essa e a
// razao de o projeto nao sangrar quando o token esta parado.
//
// A chave vem do .env e NUNCA e impressa, nem em log de erro.

const API = "https://rest.runpod.io/v1";

function chave() {
  const k = process.env.RUNPOD_API_KEY;
  if (!k) throw new Error("RUNPOD_API_KEY ausente no ambiente");
  return k;
}

async function req(caminho, opcoes = {}) {
  const r = await fetch(API + caminho, {
    ...opcoes,
    headers: {
      Authorization: `Bearer ${chave()}`,
      "Content-Type": "application/json",
      ...(opcoes.headers || {}),
    },
  });
  const texto = await r.text();
  let corpo;
  try { corpo = texto ? JSON.parse(texto) : null; } catch { corpo = texto; }
  if (!r.ok) {
    // mensagem da API sem vazar a chave
    const msg = typeof corpo === "string" ? corpo : JSON.stringify(corpo);
    throw new Error(`RunPod ${opcoes.method || "GET"} ${caminho}: ${r.status} ${msg}`);
  }
  return corpo;
}

/** Placas disponiveis e preco por hora. */
async function gpus() {
  const lista = await req("/gpuTypes");
  return (Array.isArray(lista) ? lista : []).map((g) => ({
    id: g.id,
    nome: g.displayName,
    memoriaGb: g.memoryInGb,
    seguro: g.securePrice,
    comunidade: g.communityPrice,
  }));
}

/** Pods da conta, com custo e estado. */
async function pods() {
  const lista = await req("/pods");
  return (Array.isArray(lista) ? lista : []).map((p) => ({
    id: p.id,
    nome: p.name,
    estado: p.desiredStatus,
    custoHora: p.costPerHr,
    gpu: p.machine?.gpuTypeId || p.gpuTypeIds?.[0],
    imagem: p.imageName,
    criadoEm: p.createdAt,
  }));
}

/** Liga uma placa. So chamar quando ha fila de verdade. */
async function ligar({ gpu, nome = "ehrlich-docking", disco = 40,
                       imagem = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04" }) {
  const p = await req("/pods", {
    method: "POST",
    body: JSON.stringify({
      name: nome,
      imageName: imagem,
      gpuTypeIds: [gpu],
      gpuCount: 1,
      containerDiskInGb: disco,
      volumeInGb: 0,
      ports: ["22/tcp"],
      cloudType: "COMMUNITY",
    }),
  });
  return { id: p.id, estado: p.desiredStatus, custoHora: p.costPerHr };
}

/** Desliga e destroi. Pod parado que continua existindo ainda cobra disco. */
async function desligar(id) {
  await req(`/pods/${id}`, { method: "DELETE" });
  return true;
}

async function estado(id) {
  const p = await req(`/pods/${id}`);
  return { id: p.id, estado: p.desiredStatus, custoHora: p.costPerHr,
           ip: p.publicIp, portas: p.portMappings };
}

module.exports = { gpus, pods, ligar, desligar, estado };
