"""
VALIDACAO DE POSE com os cristais certos.

Os peptidomimeticos de 13-14 torsoes (1ME3/1ME4) sao o pior caso para docking e
nao representam o que a producao vai triar. A busca no PDB achou complexos
NAO-COVALENTES com ligantes drug-like, que e o perfil real:

  4W5C/3H7   0 torsoes   MW 186
  4W5B/3H5   2 torsoes   MW 255
  4W5C/3H6   3 torsoes   MW 321
  4KLB/1RV   5 torsoes   MW 283
  3KKU/B95   6 torsoes   MW 374
  1U9Q/186  10 torsoes   MW 408

Dois testes por caso:
  REDOCK  — no proprio cristal, caixa centrada no ligante nativo + 5 A
  CROSS   — no receptor de triagem (1AIM), caixa de producao de 20 A

Antes de tudo: confere se o ligante esta no SITIO CATALITICO. Fragmento em
sitio alosterico nao valida nada para o que a triagem procura.
"""

import os
import subprocess
import sys

import gemmi
import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, rdMolAlign

RDLogger.DisableLog("rdApp.*")

BASE = r"C:\Higgsfield Games\keys"
TARGET = os.path.join(BASE, "target")
WORK = os.path.join(BASE, "results", "frente_a")
POSE = os.path.join(WORK, "pose")
SCRIPTS = r"C:\Users\Michel\AppData\Local\Programs\Python\Python310\Scripts"
MK_REC = os.path.join(SCRIPTS, "mk_prepare_receptor.exe")
MK_LIG = os.path.join(SCRIPTS, "mk_prepare_ligand.exe")
MK_EXP = os.path.join(SCRIPTS, "mk_export.exe")
VINA = os.path.join(BASE, "tools", "vina.exe")

FRAME = "1AIM"
SITIO = np.array([99.125, 21.293, -15.633])   # centro do sitio catalitico
CAIXA_PRODUCAO = (20.0, 20.0, 20.0)
PADDING = 5.0
EXHAUSTIVENESS = 32      # redocking: busca generosa
EXH_PRODUCAO = 8         # cross-docking: ajuste de producao
SEED = 42

CASOS = [("4W5C", "3H7"), ("4W5B", "3H5"), ("4W5C", "3H6"),
         ("4KLB", "1RV"), ("3KKU", "B95"), ("1U9Q", "186")]


def log(m):
    print(m, flush=True)


def roda(cmd, desc, mostrar=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        if mostrar:
            log(f"    [FALHOU] {desc}")
            for ln in saida.strip().splitlines()[-6:]:
                log(f"      {ln}")
        return False, saida
    return True, saida


def baixa(pdb_id):
    p = os.path.join(TARGET, f"{pdb_id}.pdb")
    if not os.path.exists(p):
        import urllib.request
        urllib.request.urlretrieve(f"https://files.rcsb.org/download/{pdb_id}.pdb", p)
    return p


def alinha(pdb_id, lig_code=None):
    """Leva pdb_id ao frame do 1AIM por Ca.

    A cadeia usada na superposicao e a cadeia de proteina MAIS PROXIMA do
    ligante — nao a de melhor RMSD. Numa estrutura com varias copias, o ligante
    fica no sitio da copia dele; alinhar pela copia errada joga o ligante a
    dezenas de angstroms do sitio e produz um falso "fora do sitio".
    """
    destino = os.path.join(POSE, f"{pdb_id}_{lig_code or 'x'}_frame.pdb")
    st_mov = gemmi.read_structure(baixa(pdb_id))
    st_mov.setup_entities()
    if pdb_id == FRAME and lig_code in (None, "ZYA"):
        st_mov.write_pdb(destino)
        return destino, 0.0, "A"

    # centroide do ligante no frame nativo
    alvo = None
    if lig_code:
        pts = []
        for ch in st_mov[0]:
            for res in ch:
                if res.name == lig_code:
                    pts.extend([[a.pos.x, a.pos.y, a.pos.z] for a in res])
        if pts:
            alvo = np.array(pts).mean(axis=0)

    st_ref = gemmi.read_structure(baixa(FRAME))
    st_ref.setup_entities()
    cad_ref = st_ref[0]["A"].get_polymer()

    escolhida = None
    for ch in st_mov[0]:
        pol = ch.get_polymer()
        if len(pol) < 100:
            continue
        if alvo is None:
            criterio = 0.0
        else:
            ca = np.array([[r["CA"][0].pos.x, r["CA"][0].pos.y, r["CA"][0].pos.z]
                           for r in pol if r.find_atom("CA", "*")])
            criterio = float(np.linalg.norm(ca - alvo, axis=1).min())
        if escolhida is None or criterio < escolhida[0]:
            escolhida = (criterio, ch.name, pol)

    if escolhida is None:
        return None, None, None
    dist_min, nome_cad, pol_mov = escolhida
    sup = gemmi.calculate_superposition(cad_ref, pol_mov, gemmi.PolymerType.PeptideL,
                                        gemmi.SupSelect.CaP)
    st_mov[0].transform_pos_and_adp(sup.transform)
    st_mov.write_pdb(destino)
    return destino, sup.rmsd, nome_cad


def separa(pdb_path, pdb_id, lig_code):
    with open(pdb_path) as fh:
        linhas = fh.readlines()
    cadeia = None
    for ln in linhas:
        if ln.startswith("HETATM") and ln[17:20].strip() == lig_code:
            cadeia = ln[21]
            break
    if cadeia is None:
        return None, None
    rec, lig = [], []
    for ln in linhas:
        if not ln.startswith(("ATOM", "HETATM")):
            continue
        if ln[16] not in (" ", "A"):
            continue
        if ln[76:78].strip() == "H":
            continue
        if ln.startswith("ATOM") and ln[21] == cadeia:
            rec.append(ln)
        elif (ln.startswith("HETATM") and ln[17:20].strip() == lig_code
              and ln[21] == cadeia):
            lig.append(ln)
    if not lig:
        return None, None
    tag = f"{pdb_id}_{lig_code}"
    rec_p = os.path.join(POSE, f"{tag}_rec.pdb")
    lig_p = os.path.join(POSE, f"{tag}_lig.pdb")
    with open(rec_p, "w") as fh:
        fh.writelines(rec), fh.write("END\n")
    with open(lig_p, "w") as fh:
        fh.writelines(lig), fh.write("END\n")
    return rec_p, lig_p


def xyz(path):
    a = []
    for ln in open(path):
        if ln.startswith(("ATOM", "HETATM")):
            a.append([float(ln[30:38]), float(ln[38:46]), float(ln[46:54])])
    return np.array(a)


def ligante_sdf(tag, lig_code, lig_pdb):
    import urllib.request
    tpl_p = os.path.join(TARGET, f"{lig_code}_ideal.sdf")
    if not os.path.exists(tpl_p):
        urllib.request.urlretrieve(
            f"https://files.rcsb.org/ligands/download/{lig_code}_ideal.sdf", tpl_p)
    tpl = Chem.MolFromMolFile(tpl_p, removeHs=True)
    bruto = Chem.MolFromPDBFile(lig_pdb, removeHs=True, sanitize=False)
    if tpl is None or bruto is None:
        return None, None
    try:
        mol = AllChem.AssignBondOrdersFromTemplate(tpl, bruto)
        Chem.SanitizeMol(mol)
    except Exception as e:  # noqa: BLE001
        log(f"    template nao casou ({e})")
        return None, None
    ref = Chem.Mol(mol)
    mol_h = Chem.AddHs(mol, addCoords=True)
    sdf = os.path.join(POSE, f"{tag}_ref.sdf")
    Chem.MolToMolFile(mol_h, sdf)
    return sdf, ref


def prep_receptor(tag, rec_pdb, centro, tamanho):
    base = os.path.join(POSE, f"{tag}_rec")
    ok, _ = roda([MK_REC, "--read_pdb", rec_pdb, "-o", base, "-p",
                  "--box_center", *[f"{v:.3f}" for v in centro],
                  "--box_size", *[f"{v:.3f}" for v in tamanho],
                  "--default_altloc", "A", "--charge_model", "gasteiger",
                  "--forgive_extra_bonds"],
                 f"receptor {tag}", mostrar=False)
    if not ok:
        ok, _ = roda([MK_REC, "--read_pdb", rec_pdb, "-o", base, "-p",
                      "--box_center", *[f"{v:.3f}" for v in centro],
                      "--box_size", *[f"{v:.3f}" for v in tamanho],
                      "--default_altloc", "A", "--charge_model", "gasteiger"],
                     f"receptor {tag}")
    if not ok:
        return None
    for suf in (".pdbqt", "_rigid.pdbqt"):
        if os.path.exists(base + suf):
            return base + suf
    return None


def doca(rec, centro, tamanho, lig, tag, exh):
    out = os.path.join(POSE, f"{tag}_docked.pdbqt")
    ok, saida = roda([VINA, "--receptor", rec, "--ligand", lig,
                      "--center_x", f"{centro[0]:.3f}", "--center_y", f"{centro[1]:.3f}",
                      "--center_z", f"{centro[2]:.3f}",
                      "--size_x", f"{tamanho[0]:.3f}", "--size_y", f"{tamanho[1]:.3f}",
                      "--size_z", f"{tamanho[2]:.3f}",
                      "--exhaustiveness", str(exh), "--seed", str(SEED),
                      "--num_modes", "9", "--cpu", "2", "--out", out], f"docking {tag}")
    if not ok:
        return None, None
    aff = None
    for ln in saida.splitlines():
        p = ln.split()
        if len(p) >= 2 and p[0] == "1":
            try:
                aff = float(p[1])
                break
            except ValueError:
                pass
    return out, aff


def rmsds(docked, ref_mol, tag):
    sdf = os.path.join(POSE, f"{tag}_docked.sdf")
    ok, _ = roda([MK_EXP, docked, "-s", sdf], f"export {tag}")
    if not ok or not os.path.exists(sdf):
        return None
    poses = [m for m in Chem.SDMolSupplier(sdf, removeHs=True) if m]
    if not poses:
        return None
    ref = Chem.RemoveHs(ref_mol)
    vals = []
    for m in poses:
        try:
            vals.append(rdMolAlign.CalcRMS(Chem.RemoveHs(m), ref))
        except Exception:  # noqa: BLE001
            pass
    return vals or None


def main():
    os.makedirs(POSE, exist_ok=True)
    rec_frame_pdbqt = None
    resultados = []

    log("=" * 74)
    log("PREPARACAO E CONFERENCIA DE SITIO")
    log("=" * 74)
    casos_ok = []
    for pdb_id, lig in CASOS:
        tag = f"{pdb_id}_{lig}"
        log(f"\n{tag}")
        alinhado, rms_ca, cad = alinha(pdb_id, lig)
        if alinhado is None:
            log("  nao consegui alinhar")
            continue
        log(f"  superposto pela cadeia {cad} (a do ligante): Ca RMSD {rms_ca:.2f} A")
        rec_pdb, lig_pdb = separa(alinhado, pdb_id, lig)
        if rec_pdb is None:
            log("  ligante nao encontrado apos alinhar")
            continue
        c = xyz(lig_pdb)
        dist = np.linalg.norm(c.mean(axis=0) - SITIO)
        log(f"  ligante a {dist:.1f} A do centro do sitio catalitico", )
        if dist > 12.0:
            log("  >>> FORA do sitio catalitico. Descartado (nao valida a triagem).")
            continue
        sdf, ref_mol = ligante_sdf(tag, lig, lig_pdb)
        if sdf is None:
            continue
        ok, _ = roda([MK_LIG, "-i", sdf, "-o", os.path.join(POSE, f"{tag}_lig.pdbqt")],
                     f"ligante {tag}")
        if not ok:
            continue
        lo, hi = c.min(axis=0), c.max(axis=0)
        centro_nativo = (lo + hi) / 2
        tam_nativo = (hi - lo) + 2 * PADDING
        rec_pdbqt = prep_receptor(tag, rec_pdb, centro_nativo, tam_nativo)
        if rec_pdbqt is None:
            continue
        casos_ok.append(dict(tag=tag, pdb_id=pdb_id, lig=lig, ref_mol=ref_mol,
                             lig_pdbqt=os.path.join(POSE, f"{tag}_lig.pdbqt"),
                             rec_pdbqt=rec_pdbqt, centro=centro_nativo,
                             tamanho=tam_nativo))
        log(f"  pronto (caixa nativa {tam_nativo.round(1)})")

    # receptor de triagem
    log(f"\n{FRAME} (receptor de triagem)")
    alinhado, _, _ = alinha(FRAME, "ZYA")
    rec_f_pdb, _ = separa(alinhado, FRAME, "ZYA")
    if rec_f_pdb:
        rec_frame_pdbqt = prep_receptor(f"{FRAME}_triagem", rec_f_pdb,
                                        SITIO, CAIXA_PRODUCAO)
        log(f"  {'ok' if rec_frame_pdbqt else 'falhou'}")

    log("\n" + "=" * 74)
    log("TESTE 1 — REDOCKING no proprio cristal")
    log("=" * 74)
    for c in casos_ok:
        out, aff = doca(c["rec_pdbqt"], c["centro"], c["tamanho"],
                        c["lig_pdbqt"], f"redock_{c['tag']}", EXHAUSTIVENESS)
        if not out:
            continue
        rs = rmsds(out, c["ref_mol"], f"redock_{c['tag']}")
        if rs:
            resultados.append(("REDOCK", c["tag"], aff, rs[0], min(rs)))
            log(f"  {c['tag']:12s} {aff:7.2f} kcal/mol  pose1 = {rs[0]:5.2f} A  "
                f"melhor = {min(rs):5.2f} A")

    log("\n" + "=" * 74)
    log(f"TESTE 2 — CROSS-DOCKING no {FRAME}, caixa e exhaustiveness de PRODUCAO")
    log("=" * 74)
    if rec_frame_pdbqt:
        for c in casos_ok:
            out, aff = doca(rec_frame_pdbqt, SITIO, CAIXA_PRODUCAO,
                            c["lig_pdbqt"], f"cross_{c['tag']}", EXH_PRODUCAO)
            if not out:
                continue
            rs = rmsds(out, c["ref_mol"], f"cross_{c['tag']}")
            if rs:
                resultados.append(("CROSS", c["tag"], aff, rs[0], min(rs)))
                log(f"  {c['tag']:12s} {aff:7.2f} kcal/mol  pose1 = {rs[0]:5.2f} A  "
                    f"melhor = {min(rs):5.2f} A")

    log("\n" + "=" * 74)
    log("VEREDICTO")
    log("=" * 74)
    if not resultados:
        log("nada rodou")
        sys.exit(1)
    for tipo, nome, aff, r1, rb in resultados:
        v = "PASSOU" if r1 <= 2.0 else ("recuperada" if rb <= 2.0 else "FALHOU")
        log(f"{tipo:7s} {nome:12s} aff={aff:7.2f}  pose1={r1:5.2f}  "
            f"melhor={rb:5.2f}  -> {v}")
    for tipo in ("REDOCK", "CROSS"):
        sub = [r for r in resultados if r[0] == tipo]
        if not sub:
            continue
        passou = sum(1 for r in sub if r[3] <= 2.0)
        log(f"\n{tipo}: {passou}/{len(sub)} com pose 1 dentro de 2,0 A")


if __name__ == "__main__":
    main()
