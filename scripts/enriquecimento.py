"""
TESTE DE ENRIQUECIMENTO — o que decide se a triagem faz sentido.

Pergunta: dado um conjunto de inibidores de cruzaina MEDIDOS misturados com
decoys pareados por propriedade, o protocolo poe os ativos no topo do ranking?

E este o teste que espelha a producao: triar milhoes e olhar os melhores. Pose
nao importa; ordem importa.

Rodado no MESMO ajuste da producao (mesmo receptor, mesma caixa, mesmo
exhaustiveness). Validar num ajuste melhor do que o de producao seria enganacao.

Metricas:
  AUC-ROC  — 0,50 e sorteio; >= 0,70 e util para triagem
  EF1%     — quantas vezes mais ativos no 1% do topo do que o esperado por azar
  EF5%     — idem no 5%

Uso:
  python enriquecimento.py prep          coleta decoys, gera 3D e PDBQT
  python enriquecimento.py medir         cronometra 10 dockings e estima o total
  python enriquecimento.py dock          roda tudo (demorado; use em background)
  python enriquecimento.py metricas      calcula AUC e EF do que ja docou
"""

import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")

BASE = r"C:\Higgsfield Games\keys"
WORK = os.path.join(BASE, "results", "frente_a")
ENR = os.path.join(WORK, "enriquecimento")
LIGS = os.path.join(ENR, "ligs")
DOCK = os.path.join(ENR, "docked")
SCRIPTS = r"C:\Users\Michel\AppData\Local\Programs\Python\Python310\Scripts"
MK_LIG = os.path.join(SCRIPTS, "mk_prepare_ligand.exe")
VINA = os.path.join(BASE, "tools", "vina.exe")
API = "https://www.ebi.ac.uk/chembl/api/data"

RECEPTOR = os.path.join(WORK, "1AIM_rec.pdbqt")
# caixa centrada no sitio (centroide dos ligantes cristalograficos), 20 A cubica
CENTRO = (99.125, 21.293, -15.633)
TAMANHO = (20.0, 20.0, 20.0)
EXHAUSTIVENESS = 8          # ajuste de producao
SEED = 42

N_ATIVOS = 50
DECOYS_POR_ATIVO = 12
random.seed(7)


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------- preparacao

def baixa_pool_decoys(n_alvo=6000):
    """Pool de moleculas do ChEMBL para servir de decoy (presumidas inativas)."""
    cache = os.path.join(ENR, "pool_decoys.json")
    if os.path.exists(cache):
        pool = json.load(open(cache))
        log(f"  pool em cache: {len(pool)} moleculas")
        return pool
    pool = []
    vistos = set()
    for offset in range(0, 60000, 2000):
        url = (f"{API}/molecule?format=json&limit=200&offset={offset}"
               "&molecule_properties__full_mwt__gte=200"
               "&molecule_properties__full_mwt__lte=600")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "keys/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.load(r)
        except Exception as e:  # noqa: BLE001
            log(f"  aviso: offset {offset} falhou ({e})")
            continue
        for m in d.get("molecules", []):
            st = m.get("molecule_structures") or {}
            smi = st.get("canonical_smiles")
            cid = m.get("molecule_chembl_id")
            if not smi or cid in vistos:
                continue
            vistos.add(cid)
            pool.append(dict(chembl_id=cid, smiles=smi))
        log(f"  offset {offset}: pool com {len(pool)}")
        if len(pool) >= n_alvo:
            break
    json.dump(pool, open(cache, "w"))
    return pool


def props(smi):
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    return dict(mw=Descriptors.MolWt(mol), logp=Descriptors.MolLogP(mol),
                hbd=rdMolDescriptors.CalcNumHBD(mol),
                hba=rdMolDescriptors.CalcNumHBA(mol),
                tors=rdMolDescriptors.CalcNumRotatableBonds(mol),
                carga=Chem.GetFormalCharge(mol))


def escolhe_decoys(ativos, pool):
    """Pareamento por propriedade: MW +-30, logP +-1.2, torsoes +-2, HBD/HBA +-2."""
    pool_p = []
    for p in pool:
        pr = props(p["smiles"])
        if pr:
            pool_p.append((p, pr))
    log(f"  pool com propriedades: {len(pool_p)}")

    ids_ativos = {a["chembl_id"] for a in ativos}
    usados = set()
    decoys = []
    for a in ativos:
        pa = props(a["smiles"])
        cand = []
        for p, pr in pool_p:
            if p["chembl_id"] in usados or p["chembl_id"] in ids_ativos:
                continue
            if (abs(pr["mw"] - pa["mw"]) <= 30 and abs(pr["logp"] - pa["logp"]) <= 1.2
                    and abs(pr["tors"] - pa["tors"]) <= 2
                    and abs(pr["hbd"] - pa["hbd"]) <= 2
                    and abs(pr["hba"] - pa["hba"]) <= 2):
                cand.append(p)
            if len(cand) >= DECOYS_POR_ATIVO:
                break
        for c in cand:
            usados.add(c["chembl_id"])
            decoys.append(c)
    log(f"  decoys pareados: {len(decoys)} para {len(ativos)} ativos")
    return decoys


def gera_pdbqt(args):
    cid, smi, destino = args
    out = os.path.join(LIGS, f"{destino}_{cid}.pdbqt")
    if os.path.exists(out):
        return cid, True, "cache"
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return cid, False, "smiles"
    mol = Chem.AddHs(mol)
    p = AllChem.ETKDGv3()
    p.randomSeed = SEED
    if AllChem.EmbedMolecule(mol, p) != 0:
        return cid, False, "embed"
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=500)
    except Exception:  # noqa: BLE001
        pass
    sdf = os.path.join(LIGS, f"{destino}_{cid}.sdf")
    Chem.MolToMolFile(mol, sdf)
    r = subprocess.run([MK_LIG, "-i", sdf, "-o", out],
                       capture_output=True, text=True)
    os.remove(sdf)
    if r.returncode != 0 or not os.path.exists(out):
        return cid, False, "meeko"
    return cid, True, "ok"


def prep():
    os.makedirs(LIGS, exist_ok=True)
    os.makedirs(DOCK, exist_ok=True)
    ativos_todos = json.load(open(os.path.join(WORK, "ativos_cruzaina.json")))

    # amostra estratificada: metade dos mais potentes, metade espalhada
    ativos_todos.sort(key=lambda x: x["nM"])
    topo = ativos_todos[: N_ATIVOS // 2]
    resto = random.sample(ativos_todos[N_ATIVOS // 2:], N_ATIVOS - len(topo))
    ativos = topo + resto
    log(f"ativos escolhidos: {len(ativos)} "
        f"(potencia {ativos[0]['nM']:.2f} a {max(a['nM'] for a in ativos):.0f} nM)")

    log("\nbaixando pool de decoys...")
    pool = baixa_pool_decoys()
    log("\npareando decoys por propriedade...")
    decoys = escolhe_decoys(ativos, pool)

    json.dump(dict(ativos=ativos, decoys=decoys),
              open(os.path.join(ENR, "conjunto.json"), "w"), indent=1)

    tarefas = ([(a["chembl_id"], a["smiles"], "ativo") for a in ativos]
               + [(d["chembl_id"], d["smiles"], "decoy") for d in decoys])
    log(f"\ngerando 3D + PDBQT de {len(tarefas)} moleculas...")
    ok = falhas = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for i, (cid, sucesso, motivo) in enumerate(ex.map(gera_pdbqt, tarefas), 1):
            if sucesso:
                ok += 1
            else:
                falhas += 1
            if i % 100 == 0:
                log(f"  {i}/{len(tarefas)}  ok={ok} falhas={falhas} "
                    f"({time.time() - t0:.0f}s)")
    log(f"\npreparados: {ok}   falhas: {falhas}   em {time.time() - t0:.0f}s")


# ---------------------------------------------------------------- docking

def doca_um(caminho_lig):
    nome = os.path.basename(caminho_lig).replace(".pdbqt", "")
    out = os.path.join(DOCK, f"{nome}.pdbqt")
    log_txt = os.path.join(DOCK, f"{nome}.txt")
    if os.path.exists(log_txt):
        return nome, None, 0.0
    t0 = time.time()
    r = subprocess.run(
        [VINA, "--receptor", RECEPTOR, "--ligand", caminho_lig,
         "--center_x", str(CENTRO[0]), "--center_y", str(CENTRO[1]),
         "--center_z", str(CENTRO[2]),
         "--size_x", str(TAMANHO[0]), "--size_y", str(TAMANHO[1]),
         "--size_z", str(TAMANHO[2]),
         "--exhaustiveness", str(EXHAUSTIVENESS), "--seed", str(SEED),
         "--num_modes", "1", "--cpu", "1", "--out", out],
        capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    melhor = None
    for ln in saida.splitlines():
        p = ln.split()
        if len(p) >= 2 and p[0] == "1":
            try:
                melhor = float(p[1])
                break
            except ValueError:
                pass
    with open(log_txt, "w") as fh:
        fh.write(f"{melhor}\n")
    return nome, melhor, time.time() - t0


def lista_ligs():
    return sorted(os.path.join(LIGS, f) for f in os.listdir(LIGS)
                  if f.endswith(".pdbqt"))


def medir():
    ligs = lista_ligs()[:10]
    log(f"cronometrando {len(ligs)} dockings (1 cpu cada, sequencial)...")
    t0 = time.time()
    for l in ligs:
        nome, score, dt = doca_um(l)
        log(f"  {nome}: {score} kcal/mol em {dt:.1f}s")
    total = time.time() - t0
    por = total / max(1, len(ligs))
    n = len(lista_ligs())
    cpus = os.cpu_count()
    log(f"\nmedia: {por:.1f}s por molecula em 1 cpu")
    log(f"total de moleculas: {n}")
    log(f"com {cpus} processos em paralelo: ~{n * por / cpus / 60:.0f} min")


def dock():
    ligs = [l for l in lista_ligs()
            if not os.path.exists(os.path.join(
                DOCK, os.path.basename(l).replace(".pdbqt", ".txt")))]
    log(f"docking de {len(ligs)} moleculas com {os.cpu_count()} processos...")
    t0 = time.time()
    feitos = 0
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for nome, score, dt in ex.map(doca_um, ligs):
            feitos += 1
            if feitos % 50 == 0:
                el = time.time() - t0
                log(f"  {feitos}/{len(ligs)}  {el/60:.1f} min  "
                    f"restam ~{(len(ligs)-feitos)*el/feitos/60:.0f} min")
    log(f"\nconcluido em {(time.time() - t0)/60:.1f} min")


# ---------------------------------------------------------------- metricas

def metricas():
    conj = json.load(open(os.path.join(ENR, "conjunto.json")))
    rotulo = {a["chembl_id"]: 1 for a in conj["ativos"]}
    rotulo.update({d["chembl_id"]: 0 for d in conj["decoys"]})

    resultados = []
    for f in os.listdir(DOCK):
        if not f.endswith(".txt"):
            continue
        nome = f[:-4]
        partes = nome.split("_", 1)
        if len(partes) != 2:
            continue
        cid = partes[1]
        if cid not in rotulo:
            continue
        try:
            v = open(os.path.join(DOCK, f)).read().strip()
            score = float(v)
        except (ValueError, TypeError):
            continue
        resultados.append((score, rotulo[cid], cid))

    if not resultados:
        log("nada docado ainda")
        return
    n_at = sum(1 for r in resultados if r[1] == 1)
    n_de = len(resultados) - n_at
    log(f"docados: {len(resultados)}  ({n_at} ativos, {n_de} decoys)")
    if n_at == 0 or n_de == 0:
        log("faltam ativos ou decoys para calcular metrica")
        return

    resultados.sort(key=lambda x: x[0])   # mais negativo = melhor

    # AUC-ROC pela contagem de pares concordantes
    pares = ganhos = empates = 0
    for s1, y1, _ in resultados:
        for s2, y2, _ in resultados:
            if y1 == 1 and y2 == 0:
                pares += 1
                if s1 < s2:
                    ganhos += 1
                elif s1 == s2:
                    empates += 1
    auc = (ganhos + 0.5 * empates) / pares

    def ef(frac):
        k = max(1, int(round(len(resultados) * frac)))
        topo = sum(1 for s, y, _ in resultados[:k] if y == 1)
        esperado = k * n_at / len(resultados)
        return topo / esperado if esperado else 0.0, topo, k

    ef1, t1, k1 = ef(0.01)
    ef5, t5, k5 = ef(0.05)
    ef10, t10, k10 = ef(0.10)

    log("")
    log("=" * 60)
    log("RESULTADO DO ENRIQUECIMENTO")
    log("=" * 60)
    log(f"AUC-ROC : {auc:.3f}   (0,50 = sorteio; >= 0,70 = util para triagem)")
    log(f"EF 1%   : {ef1:.1f}x  ({t1} ativos nos {k1} melhores)")
    log(f"EF 5%   : {ef5:.1f}x  ({t5} ativos nos {k5} melhores)")
    log(f"EF 10%  : {ef10:.1f}x ({t10} ativos nos {k10} melhores)")
    log("")
    log("10 melhores scores:")
    for s, y, cid in resultados[:10]:
        log(f"  {s:7.2f}  {'ATIVO' if y else 'decoy'}  {cid}")

    json.dump(dict(auc=auc, ef1=ef1, ef5=ef5, ef10=ef10,
                   n_ativos=n_at, n_decoys=n_de,
                   exhaustiveness=EXHAUSTIVENESS, caixa=TAMANHO),
              open(os.path.join(ENR, "metricas.json"), "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "medir"
    {"prep": prep, "medir": medir, "dock": dock, "metricas": metricas}[cmd]()
