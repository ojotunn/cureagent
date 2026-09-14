"""
CONTROLE POSITIVO — o pipeline esta errado, ou o alvo e que e dificil?

Roda exatamente o mesmo protocolo (Meeko 0.8 + Vina 1.2.5, mesma preparacao,
mesma caixa nativa + 5 A, mesmo calculo de RMSD) em sistemas onde o redocking
e classicamente facil e documentado em tutorial:

  3PTB / BEN   tripsina + benzamidina   (bolso profundo, ligante rigido)
  1STP / BTN   estreptavidina + biotina (o caso-escola de afinidade)
  1HVR / XK2   HIV protease + inibidor  (sitio fechado, ligante medio)

Se estes PASSAREM (RMSD <= 2,0 A na pose 1), o pipeline esta correto e o
problema e a cruzaina: sitio raso e aberto, onde a funcao de score do Vina nao
reconhece a pose cristalografica. Isso e um achado sobre o ALVO.

Se estes FALHAREM, o erro e meu e nao ha conclusao nenhuma sobre a cruzaina.
"""

import os
import subprocess
import urllib.request

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, rdMolAlign

RDLogger.DisableLog("rdApp.*")

BASE = r"C:\Higgsfield Games\keys"
TARGET = os.path.join(BASE, "target")
CTRL = os.path.join(BASE, "results", "frente_a", "controle")
SCRIPTS = r"C:\Users\Michel\AppData\Local\Programs\Python\Python310\Scripts"
MK_REC = os.path.join(SCRIPTS, "mk_prepare_receptor.exe")
MK_LIG = os.path.join(SCRIPTS, "mk_prepare_ligand.exe")
MK_EXP = os.path.join(SCRIPTS, "mk_export.exe")
VINA = os.path.join(BASE, "tools", "vina.exe")

CASOS = [("3PTB", "BEN"), ("1STP", "BTN"), ("1HVR", "XK2")]
PADDING = 5.0
EXHAUSTIVENESS = 32
SEED = 42


def log(m):
    print(m, flush=True)


def roda(cmd, desc):
    r = subprocess.run(cmd, capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        log(f"    [FALHOU] {desc}")
        for ln in saida.strip().splitlines()[-6:]:
            log(f"      {ln}")
        return False, saida
    return True, saida


def baixa(url, destino):
    if not os.path.exists(destino):
        urllib.request.urlretrieve(url, destino)
    return destino


def main():
    os.makedirs(CTRL, exist_ok=True)
    resultados = []

    for pdb_id, lig in CASOS:
        log(f"\n=== {pdb_id} / {lig} ===")
        pdb = baixa(f"https://files.rcsb.org/download/{pdb_id}.pdb",
                    os.path.join(TARGET, f"{pdb_id}.pdb"))

        # covalente?
        covalente = any(ln.startswith("LINK") and lig in ln
                        for ln in open(pdb))
        if covalente:
            log("  tem LINK com o ligante — nao serve de controle")
            continue

        linhas = open(pdb).readlines()
        cadeia = next((ln[21] for ln in linhas
                       if ln.startswith("HETATM") and ln[17:20].strip() == lig), None)
        if cadeia is None:
            log(f"  ligante {lig} nao encontrado")
            continue

        rec, ligl = [], []
        for ln in linhas:
            if not ln.startswith(("ATOM", "HETATM")):
                continue
            if ln[16] not in (" ", "A") or ln[76:78].strip() == "H":
                continue
            if ln.startswith("ATOM"):
                rec.append(ln)
            elif ln[17:20].strip() == lig and ln[21] == cadeia:
                ligl.append(ln)

        tag = f"{pdb_id}_{lig}"
        rec_p = os.path.join(CTRL, f"{tag}_rec.pdb")
        lig_p = os.path.join(CTRL, f"{tag}_lig.pdb")
        open(rec_p, "w").writelines(rec + ["END\n"])
        open(lig_p, "w").writelines(ligl + ["END\n"])
        log(f"  receptor {len(rec)} atomos | ligante {len(ligl)} atomos")

        tpl_p = os.path.join(TARGET, f"{lig}_ideal.sdf")
        try:
            baixa(f"https://files.rcsb.org/ligands/download/{lig}_ideal.sdf", tpl_p)
        except Exception as e:  # noqa: BLE001
            log(f"  template nao baixou ({e})")
            continue
        tpl = Chem.MolFromMolFile(tpl_p, removeHs=True)
        bruto = Chem.MolFromPDBFile(lig_p, removeHs=True, sanitize=False)
        if tpl is None or bruto is None:
            log("  leitura do ligante falhou")
            continue
        try:
            mol = AllChem.AssignBondOrdersFromTemplate(tpl, bruto)
            Chem.SanitizeMol(mol)
        except Exception as e:  # noqa: BLE001
            log(f"  template nao casou ({e})")
            continue
        ref = Chem.Mol(mol)
        tors = Chem.rdMolDescriptors.CalcNumRotatableBonds(mol)
        sdf = os.path.join(CTRL, f"{tag}_ref.sdf")
        Chem.MolToMolFile(Chem.AddHs(mol, addCoords=True), sdf)
        log(f"  {ref.GetNumAtoms()} atomos pesados, {tors} torsoes")

        lig_pdbqt = os.path.join(CTRL, f"{tag}_lig.pdbqt")
        if not roda([MK_LIG, "-i", sdf, "-o", lig_pdbqt], f"ligante {tag}")[0]:
            continue

        c = np.array([[float(ln[30:38]), float(ln[38:46]), float(ln[46:54])]
                      for ln in ligl])
        lo, hi = c.min(axis=0), c.max(axis=0)
        centro = (lo + hi) / 2
        tamanho = (hi - lo) + 2 * PADDING

        base = os.path.join(CTRL, f"{tag}_rec")
        cmd = [MK_REC, "--read_pdb", rec_p, "-o", base, "-p",
               "--box_center", *[f"{v:.3f}" for v in centro],
               "--box_size", *[f"{v:.3f}" for v in tamanho],
               "--default_altloc", "A", "--charge_model", "gasteiger",
               "--forgive_extra_bonds"]
        if not roda(cmd, f"receptor {tag}")[0]:
            continue
        rec_pdbqt = next((base + s for s in (".pdbqt", "_rigid.pdbqt")
                          if os.path.exists(base + s)), None)
        if rec_pdbqt is None:
            log("  pdbqt do receptor nao apareceu")
            continue

        out = os.path.join(CTRL, f"{tag}_docked.pdbqt")
        ok, saida = roda([VINA, "--receptor", rec_pdbqt, "--ligand", lig_pdbqt,
                          "--center_x", f"{centro[0]:.3f}",
                          "--center_y", f"{centro[1]:.3f}",
                          "--center_z", f"{centro[2]:.3f}",
                          "--size_x", f"{tamanho[0]:.3f}",
                          "--size_y", f"{tamanho[1]:.3f}",
                          "--size_z", f"{tamanho[2]:.3f}",
                          "--exhaustiveness", str(EXHAUSTIVENESS),
                          "--seed", str(SEED), "--num_modes", "9",
                          "--cpu", "2", "--out", out], f"docking {tag}")
        if not ok:
            continue
        aff = None
        for ln in saida.splitlines():
            p = ln.split()
            if len(p) >= 2 and p[0] == "1":
                try:
                    aff = float(p[1])
                    break
                except ValueError:
                    pass

        sdf_out = os.path.join(CTRL, f"{tag}_docked.sdf")
        roda([MK_EXP, out, "-s", sdf_out], f"export {tag}")
        poses = [m for m in Chem.SDMolSupplier(sdf_out, removeHs=True) if m]
        refh = Chem.RemoveHs(ref)
        vals = []
        for m in poses:
            try:
                vals.append(rdMolAlign.CalcRMS(Chem.RemoveHs(m), refh))
            except Exception:  # noqa: BLE001
                pass
        if vals:
            resultados.append((tag, tors, aff, vals[0], min(vals)))
            log(f"  RESULTADO: {aff} kcal/mol | pose 1 = {vals[0]:.2f} A | "
                f"melhor = {min(vals):.2f} A")

    log("\n" + "=" * 68)
    log("VEREDICTO DO CONTROLE")
    log("=" * 68)
    if not resultados:
        log("nenhum controle rodou — nao da para concluir nada")
        return
    for tag, tors, aff, r1, rb in resultados:
        v = "PASSOU" if r1 <= 2.0 else "FALHOU"
        log(f"  {tag:12s} {tors:2d} tors  aff={aff:7.2f}  pose1={r1:5.2f} A  "
            f"melhor={rb:5.2f} A  -> {v}")
    passou = sum(1 for r in resultados if r[3] <= 2.0)
    log("")
    if passou == len(resultados):
        log("PIPELINE CORRETO. Os classicos reproduzem a pose cristalografica.")
        log("Logo, a falha na cruzaina e propriedade DO ALVO, nao do codigo.")
    elif passou == 0:
        log("PIPELINE COM ERRO. Nem os casos faceis passam — a conclusao sobre")
        log("a cruzaina fica suspensa ate isto ser corrigido.")
    else:
        log(f"PARCIAL: {passou}/{len(resultados)}. Investigar caso a caso.")


if __name__ == "__main__":
    main()
