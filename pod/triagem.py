"""
Triagem continua, no pod. Este e o motor.

Pega moleculas da biblioteca, doca contra o receptor, grava o score. Escreve o
progresso num JSON a cada lote pequeno, para a tela ter o que mostrar enquanto
ainda esta trabalhando — nao no fim.

Nao inventa nada: cada linha do resultado e uma molecula que passou pelo Vina.
"""

import json, os, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

RDLogger.DisableLog("rdApp.*")

BASE = "/work"
VINA = f"{BASE}/vina"
REC = f"{BASE}/target/receptor.pdbqt"
MK_LIG = "mk_prepare_ligand.py"

# sitio do TcCYP51, medido do ligante cristalografico
CENTRO = (2.49, -24.48, 18.32)
TAM = (22.0, 22.0, 22.0)
EXH = 8
SEED = 42

PROGRESSO = f"{BASE}/out/progresso.json"
RESULTADOS = f"{BASE}/out/resultados.jsonl"


def prepara(args):
    cid, smi = args
    out = f"{BASE}/ligs/{cid}.pdbqt"
    if os.path.exists(out): return cid
    m = Chem.MolFromSmiles(smi)
    if m is None: return None
    m = Chem.AddHs(m)
    p = AllChem.ETKDGv3(); p.randomSeed = SEED
    if AllChem.EmbedMolecule(m, p) != 0: return None
    try: AllChem.MMFFOptimizeMolecule(m, maxIters=400)
    except Exception: pass
    sdf = out.replace(".pdbqt", ".sdf")
    Chem.MolToMolFile(m, sdf)
    subprocess.run([MK_LIG, "-i", sdf, "-o", out], capture_output=True)
    try: os.remove(sdf)
    except OSError: pass
    return cid if os.path.exists(out) else None


def doca(cid):
    lig = f"{BASE}/ligs/{cid}.pdbqt"
    if not os.path.exists(lig): return (cid, None)
    r = subprocess.run([VINA, "--receptor", REC, "--ligand", lig,
        "--center_x", str(CENTRO[0]), "--center_y", str(CENTRO[1]),
        "--center_z", str(CENTRO[2]),
        "--size_x", str(TAM[0]), "--size_y", str(TAM[1]), "--size_z", str(TAM[2]),
        "--exhaustiveness", str(EXH), "--seed", str(SEED),
        "--num_modes", "1", "--cpu", "1"], capture_output=True, text=True)
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p) >= 2 and p[0] == "1":
            try: return (cid, float(p[1]))
            except ValueError: pass
    return (cid, None)


def main():
    os.makedirs(f"{BASE}/ligs", exist_ok=True)
    os.makedirs(f"{BASE}/out", exist_ok=True)
    mols = json.load(open(f"{BASE}/moleculas.json"))
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else len(mols)
    mols = mols[:limite]
    n_cpu = os.cpu_count()
    print(f"triando {len(mols)} moleculas em {n_cpu} nucleos", flush=True)

    feitos = set()
    if os.path.exists(RESULTADOS):
        for l in open(RESULTADOS):
            try: feitos.add(json.loads(l)["id"])
            except Exception: pass
    mols = [m for m in mols if m.get("chembl_id", m.get("id")) not in feitos]
    print(f"  {len(feitos)} ja feitas, {len(mols)} pela frente", flush=True)

    t0 = time.time()
    total = 0
    FATIA = 200            # escreve progresso a cada fatia
    saida = open(RESULTADOS, "a")

    for i in range(0, len(mols), FATIA):
        bloco = mols[i:i+FATIA]
        pares = [(m.get("chembl_id", m.get("id")), m["smiles"]) for m in bloco]

        with ProcessPoolExecutor(max_workers=n_cpu) as ex:
            prontos = [c for c in ex.map(prepara, pares) if c]
        with ProcessPoolExecutor(max_workers=n_cpu) as ex:
            for cid, score in ex.map(doca, prontos):
                if score is None: continue
                saida.write(json.dumps({"id": cid, "score": round(score, 2)}) + "\n")
                total += 1
        saida.flush()

        dt = time.time() - t0
        json.dump({
            "triadas": total + len(feitos),
            "nesta_sessao": total,
            "segundos": round(dt, 1),
            "seg_por_molecula": round(dt / max(1, total), 3),
            "por_hora": round(total / max(dt, 1) * 3600),
            "nucleos": n_cpu,
            "receptor": "TcCYP51 3KHM",
            "atualizado": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, open(PROGRESSO, "w"), indent=1)

        print(f"  {total} triadas · {dt/60:.1f} min · "
              f"{total/max(dt,1)*3600:.0f}/hora", flush=True)

    saida.close()
    print(f"\nfim: {total} moleculas em {(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
