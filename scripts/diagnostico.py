"""
Por que o redocking falhou? Quatro medidas, nenhum chute.

1. Os PDBQT do receptor tem a proteina inteira?
2. Os tres ligantes estao no mesmo lugar depois da superposicao?
3. score_only: qual a energia que o Vina da para a POSE DO CRISTAL?
      - melhor que a pose achada  -> problema de BUSCA (caixa grande / exhaustiveness)
      - pior que a pose achada    -> problema de PREPARACAO (clash, protonacao, etc.)
4. local_only: minimizando a partir da pose do cristal, ela fica no lugar?
      - fica  -> a pose e um minimo valido; o Vina so nao a encontra sozinho
      - foge  -> o campo de forca nao ve essa pose como boa: preparacao suspeita
"""

import os
import subprocess

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import rdMolAlign

RDLogger.DisableLog("rdApp.*")

BASE = r"C:\Higgsfield Games\keys"
WORK = os.path.join(BASE, "results", "frente_a")
TARGET = os.path.join(BASE, "target")
SCRIPTS = r"C:\Users\Michel\AppData\Local\Programs\Python\Python310\Scripts"
MK_EXP = os.path.join(SCRIPTS, "mk_export.exe")
VINA = os.path.join(BASE, "tools", "vina.exe")

CASOS = [("1ME3", "P10"), ("1ME4", "T10")]


def coords(path, so_hetatm=False):
    xyz = []
    with open(path) as fh:
        for ln in fh:
            if ln.startswith("HETATM") or (not so_hetatm and ln.startswith("ATOM")):
                xyz.append([float(ln[30:38]), float(ln[38:46]), float(ln[46:54])])
    return np.array(xyz)


def conta_pdbqt(path):
    if not os.path.exists(path):
        return None
    n = 0
    with open(path) as fh:
        for ln in fh:
            if ln.startswith(("ATOM", "HETATM")):
                n += 1
    return n


print("=" * 72)
print("1. RECEPTORES PREPARADOS")
print("=" * 72)
for pdb_id in ["1AIM", "1ME3", "1ME4"]:
    for suf in [".pdbqt", "_rigid.pdbqt"]:
        p = os.path.join(WORK, f"{pdb_id}_rec{suf}")
        n = conta_pdbqt(p)
        if n:
            print(f"  {pdb_id}_rec{suf}: {n} atomos")
    box = os.path.join(WORK, f"{pdb_id}_rec.box.txt")
    if os.path.exists(box):
        print(f"    box.txt: {open(box).read().strip().splitlines()}")

print()
print("=" * 72)
print("2. OS LIGANTES ESTAO NO MESMO LUGAR?")
print("=" * 72)
cent = {}
for pdb_id, lig in [("1AIM", "ZYA")] + CASOS:
    p = os.path.join(WORK, f"{pdb_id}_{lig}_cristal.pdb")
    c = coords(p, so_hetatm=True)
    cent[lig] = c.mean(axis=0)
    ext = c.max(axis=0) - c.min(axis=0)
    print(f"  {lig:4s} centroide ({cent[lig][0]:7.2f},{cent[lig][1]:7.2f},"
          f"{cent[lig][2]:7.2f})  extensao ({ext[0]:.1f},{ext[1]:.1f},{ext[2]:.1f}) A")
chaves = list(cent)
for i in range(len(chaves)):
    for j in range(i + 1, len(chaves)):
        d = np.linalg.norm(cent[chaves[i]] - cent[chaves[j]])
        print(f"  distancia {chaves[i]}-{chaves[j]}: {d:.2f} A")

print()
print("=" * 72)
print("3 e 4. SCORE_ONLY e LOCAL_ONLY na pose do cristal")
print("=" * 72)


def extrai_energia(saida, rotulo):
    for ln in saida.splitlines():
        s = ln.strip()
        if s.startswith(rotulo):
            return s
    return None


for pdb_id, lig in CASOS:
    rec = os.path.join(WORK, f"{pdb_id}_rec.pdbqt")
    if not os.path.exists(rec):
        rec = os.path.join(WORK, f"{pdb_id}_rec_rigid.pdbqt")
    ligq = os.path.join(WORK, f"{pdb_id}_{lig}_lig.pdbqt")
    print(f"\n--- {pdb_id} / {lig} ---")
    if not (os.path.exists(rec) and os.path.exists(ligq)):
        print("  arquivos faltando:", rec, ligq)
        continue

    r = subprocess.run([VINA, "--receptor", rec, "--ligand", ligq, "--score_only"],
                       capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    linha = extrai_energia(saida, "Estimated Free Energy")
    if linha is None:
        for ln in saida.splitlines():
            if "Affinity" in ln or "energy" in ln.lower():
                linha = ln.strip()
                break
    print(f"  score_only da pose do cristal: {linha}")

    out = os.path.join(WORK, f"local_{pdb_id}_{lig}.pdbqt")
    r = subprocess.run([VINA, "--receptor", rec, "--ligand", ligq,
                        "--local_only", "--out", out],
                       capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    aff = None
    for ln in saida.splitlines():
        p = ln.split()
        if len(p) >= 2 and p[0] == "1":
            try:
                aff = float(p[1])
            except ValueError:
                pass
    if not os.path.exists(out):
        print("  local_only nao escreveu saida:")
        for ln in saida.strip().splitlines()[-8:]:
            print("   ", ln)
        continue

    sdf = os.path.join(WORK, f"local_{pdb_id}_{lig}.sdf")
    subprocess.run([MK_EXP, out, "-s", sdf], capture_output=True, text=True)
    ref = Chem.RemoveHs(Chem.MolFromMolFile(
        os.path.join(WORK, f"{pdb_id}_{lig}_ref.sdf"), removeHs=True))
    poses = [m for m in Chem.SDMolSupplier(sdf, removeHs=True) if m]
    if poses and ref:
        rms = rdMolAlign.CalcRMS(Chem.RemoveHs(poses[0]), ref)
        print(f"  local_only: {aff} kcal/mol, RMSD apos minimizar = {rms:.2f} A")
    else:
        print("  local_only: nao consegui ler a pose minimizada")
