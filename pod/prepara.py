"""
Prepara ligantes: SMILES -> PDBQT. Roda em rajadas, chamado pelo supervisor.

Nao guarda estado: olha o que ja existe em /work/ligs e prepara os proximos.
Se morrer no meio, o que ficou pronto continua pronto.
"""
import json, os, subprocess, sys
from multiprocessing import Pool

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

RDLogger.DisableLog("rdApp.*")
BASE = "/work"
LIGS = sys.argv[2] if len(sys.argv) > 2 else BASE + "/prod/ligs"


def prepara(args):
    cid, smi = args
    out = "%s/%s.pdbqt" % (LIGS, cid)
    if os.path.exists(out):
        return cid
    try:
        m = Chem.MolFromSmiles(smi)
        if m is None:
            return None
        m = Chem.AddHs(m)
        p = AllChem.ETKDGv3()
        p.randomSeed = 42
        if AllChem.EmbedMolecule(m, p) != 0:
            return None
        try:
            AllChem.MMFFOptimizeMolecule(m, maxIters=400)
        except Exception:
            pass
        sdf = out.replace(".pdbqt", ".sdf")
        Chem.MolToMolFile(m, sdf)
        subprocess.run(["mk_prepare_ligand.py", "-i", sdf, "-o", out],
                       capture_output=True, timeout=120)
        try:
            os.remove(sdf)
        except OSError:
            pass
    except Exception:
        return None
    return cid if os.path.exists(out) else None


def main():
    quantos = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    os.makedirs(LIGS, exist_ok=True)
    mols = json.load(open(BASE + "/moleculas.json"))
    tem = set(f[:-6] for f in os.listdir(LIGS) if f.endswith(".pdbqt"))

    fila = []
    for m in mols:
        cid = m.get("chembl_id") or m.get("id")
        smi = m.get("smiles")
        if not cid or not smi or cid in tem:
            continue
        fila.append((cid, smi))
        if len(fila) >= quantos:
            break

    if not fila:
        print("nada a preparar", flush=True)
        return

    ok = 0
    with Pool(processes=10) as pool:
        for r in pool.imap_unordered(prepara, fila, chunksize=4):
            if r:
                ok += 1
    print("preparados %d de %d" % (ok, len(fila)), flush=True)


if __name__ == "__main__":
    main()
