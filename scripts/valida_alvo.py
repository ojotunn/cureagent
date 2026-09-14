"""
FRENTE A — validacao do protocolo de docking da cruzaina.

Pergunta unica desta fatia: o protocolo reencontra um inibidor conhecido na
posicao em que o cristal mostra que ele esta?

Dois testes:
  1. REDOCKING   — ligante docado de volta no proprio cristal. Auto-consistente.
                   Se falhar aqui, o pipeline esta errado.
  2. CROSS-DOCK  — o mesmo ligante docado no receptor de TRIAGEM (1AIM).
                   E este que prova que o 1AIM serve como alvo prospectivo.

Criterio da literatura: RMSD <= 2,0 A contra a pose cristalografica.
RMSD calculado SEM realinhar (CalcRMS), considerando simetria molecular.

DECISOES DE PREPARACAO (registradas de proposito, nao escolhidas no escuro):
- Complexos covalentes (2OZ2/K777, 1AIM/ZYA) nao validam nada: o ligante esta
  preso na Cys25 (LINK ~1,7 A) e docking nao-covalente nunca reproduz isso.
  Verificado nos proprios arquivos PDB. Servem como referencia de sitio.
- Tudo e levado ao FRAME DE COORDENADAS DO 1AIM por superposicao de Ca
  (gemmi). Sem isso, RMSD entre estruturas diferentes nao significa nada.
- Uma unica caixa de busca para todos os testes, centrada no sitio do 1AIM:
  e a mesma caixa que a producao vai usar. Nao se ajusta caixa por ligante
  para melhorar o resultado.
- Altloc: mantem apenas ' ' ou 'A'. Hidrogenios do cristal descartados e
  readicionados pelo RDKit (o Meeko exige H explicitos).
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
SCRIPTS = r"C:\Users\Michel\AppData\Local\Programs\Python\Python310\Scripts"
MK_REC = os.path.join(SCRIPTS, "mk_prepare_receptor.exe")
MK_LIG = os.path.join(SCRIPTS, "mk_prepare_ligand.exe")
MK_EXP = os.path.join(SCRIPTS, "mk_export.exe")
VINA = os.path.join(BASE, "tools", "vina.exe")

FRAME = "1AIM"          # frame de coordenadas de referencia e receptor de triagem
LIG_FRAME = "ZYA"       # ligante covalente do 1AIM: define o sitio
CASOS = [("1ME3", "P10"), ("1ME4", "T10")]   # nao-covalentes, 1,20 A

PADDING = 5.0
EXHAUSTIVENESS = 32
SEED = 42


def log(m):
    print(m, flush=True)


def roda(cmd, desc):
    r = subprocess.run(cmd, capture_output=True, text=True)
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        log(f"  [FALHOU] {desc} (codigo {r.returncode})")
        for ln in saida.strip().splitlines()[-10:]:
            log(f"    {ln}")
        return False, saida
    return True, saida


def alinha_ao_frame(pdb_id):
    """Superpoe pdb_id no frame do 1AIM por Ca. Devolve caminho do PDB transformado."""
    destino = os.path.join(WORK, f"{pdb_id}_no_frame_{FRAME}.pdb")
    if pdb_id == FRAME:
        st = gemmi.read_structure(os.path.join(TARGET, f"{pdb_id}.pdb"))
        st.setup_entities()
        st.write_pdb(destino)
        log(f"  {pdb_id}: e o proprio frame de referencia")
        return destino, 0.0

    st_ref = gemmi.read_structure(os.path.join(TARGET, f"{FRAME}.pdb"))
    st_mov = gemmi.read_structure(os.path.join(TARGET, f"{pdb_id}.pdb"))
    st_ref.setup_entities()
    st_mov.setup_entities()
    pol_ref = st_ref[0]["A"].get_polymer()
    pol_mov = st_mov[0]["A"].get_polymer()
    sup = gemmi.calculate_superposition(
        pol_ref, pol_mov, gemmi.PolymerType.PeptideL, gemmi.SupSelect.CaP
    )
    st_mov[0].transform_pos_and_adp(sup.transform)
    st_mov.write_pdb(destino)
    log(f"  {pdb_id} -> frame {FRAME}: RMSD de Ca = {sup.rmsd:.2f} A "
        f"({sup.count} pares)")
    return destino, sup.rmsd


def separa(pdb_path, pdb_id, lig_code):
    """Receptor (ATOM) e ligante (HETATM do codigo) da cadeia onde o ligante esta."""
    with open(pdb_path) as fh:
        linhas = fh.readlines()

    cadeia = None
    for ln in linhas:
        if ln.startswith("HETATM") and ln[17:20].strip() == lig_code:
            cadeia = ln[21]
            break
    if cadeia is None:
        raise SystemExit(f"ligante {lig_code} nao encontrado em {pdb_id}")

    rec, lig = [], []
    for ln in linhas:
        if not (ln.startswith("ATOM") or ln.startswith("HETATM")):
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

    rec_path = os.path.join(WORK, f"{pdb_id}_rec.pdb")
    with open(rec_path, "w") as fh:
        fh.writelines(rec)
        fh.write("END\n")
    lig_path = os.path.join(WORK, f"{pdb_id}_{lig_code}_cristal.pdb")
    with open(lig_path, "w") as fh:
        fh.writelines(lig)
        fh.write("END\n")
    log(f"  receptor {len(rec)} atomos (cadeia {cadeia}) | ligante {len(lig)} atomos")
    return rec_path, lig_path


def coords_pdb(path):
    xyz = []
    with open(path) as fh:
        for ln in fh:
            if ln.startswith(("ATOM", "HETATM")):
                xyz.append([float(ln[30:38]), float(ln[38:46]), float(ln[46:54])])
    return np.array(xyz)


def ligante_com_ordens(pdb_id, lig_code, lig_pdb):
    """PDB nao tem ordem de ligacao: recupera do template ideal do RCSB e poe H."""
    tpl = Chem.MolFromMolFile(os.path.join(TARGET, f"{lig_code}_ideal.sdf"),
                              removeHs=True)
    bruto = Chem.MolFromPDBFile(lig_pdb, removeHs=True, sanitize=False)
    if tpl is None or bruto is None:
        raise SystemExit(f"leitura falhou para {pdb_id}/{lig_code}")
    mol = AllChem.AssignBondOrdersFromTemplate(tpl, bruto)
    Chem.SanitizeMol(mol)
    ref_pesados = Chem.Mol(mol)                      # para RMSD
    mol_h = Chem.AddHs(mol, addCoords=True)          # para o Meeko
    sdf = os.path.join(WORK, f"{pdb_id}_{lig_code}_ref.sdf")
    Chem.MolToMolFile(mol_h, sdf)
    log(f"  {lig_code}: ordens do template OK, {ref_pesados.GetNumAtoms()} atomos "
        f"pesados + {mol_h.GetNumAtoms() - ref_pesados.GetNumAtoms()} H")
    return sdf, ref_pesados


def caixa_comum(lista_pdb_ligantes):
    """Caixa unica cobrindo todos os ligantes de referencia + padding."""
    todos = np.vstack([coords_pdb(p) for p in lista_pdb_ligantes])
    lo, hi = todos.min(axis=0), todos.max(axis=0)
    centro = (lo + hi) / 2.0
    tamanho = (hi - lo) + 2 * PADDING
    log(f"  caixa unica: centro ({centro[0]:.2f}, {centro[1]:.2f}, {centro[2]:.2f}) "
        f"tamanho ({tamanho[0]:.1f}, {tamanho[1]:.1f}, {tamanho[2]:.1f}) A")
    return centro, tamanho


def prepara_receptor(pdb_id, rec_pdb, centro, tamanho):
    base = os.path.join(WORK, f"{pdb_id}_rec")
    cmd = [MK_REC, "--read_pdb", rec_pdb, "-o", base, "-p", "-v",
           "--box_center", *[f"{v:.3f}" for v in centro],
           "--box_size", *[f"{v:.3f}" for v in tamanho],
           "--default_altloc", "A", "--charge_model", "gasteiger"]
    ok, saida = roda(cmd, f"preparar receptor {pdb_id}")
    if not ok:
        return None, None
    pdbqt = base + ".pdbqt"
    if not os.path.exists(pdbqt):
        alt = base + "_rigid.pdbqt"
        pdbqt = alt if os.path.exists(alt) else None
    caixa = base + ".box.txt"
    if not os.path.exists(caixa):
        caixa = None
    return pdbqt, caixa


def prepara_ligante(sdf, tag):
    out = os.path.join(WORK, f"{tag}_lig.pdbqt")
    ok, _ = roda([MK_LIG, "-i", sdf, "-o", out], f"preparar ligante {tag}")
    return out if ok else None


def doca(rec_pdbqt, centro, tamanho, lig_pdbqt, tag):
    out = os.path.join(WORK, f"{tag}_docked.pdbqt")
    cmd = [VINA, "--receptor", rec_pdbqt, "--ligand", lig_pdbqt,
           "--center_x", f"{centro[0]:.3f}", "--center_y", f"{centro[1]:.3f}",
           "--center_z", f"{centro[2]:.3f}",
           "--size_x", f"{tamanho[0]:.3f}", "--size_y", f"{tamanho[1]:.3f}",
           "--size_z", f"{tamanho[2]:.3f}",
           "--exhaustiveness", str(EXHAUSTIVENESS), "--seed", str(SEED),
           "--num_modes", "9", "--out", out]
    ok, saida = roda(cmd, f"docking {tag}")
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


def rmsds_contra_cristal(docked, ref_mol, tag):
    sdf = os.path.join(WORK, f"{tag}_docked.sdf")
    ok, _ = roda([MK_EXP, docked, "-s", sdf], f"exportar poses {tag}")
    if not ok or not os.path.exists(sdf):
        return None
    poses = [m for m in Chem.SDMolSupplier(sdf, removeHs=True) if m is not None]
    if not poses:
        return None
    ref = Chem.RemoveHs(ref_mol)
    vals = []
    for m in poses:
        try:
            vals.append(rdMolAlign.CalcRMS(Chem.RemoveHs(m), ref))
        except Exception as e:  # noqa: BLE001
            log(f"  aviso: RMSD de uma pose falhou ({e})")
    return vals or None


def main():
    os.makedirs(WORK, exist_ok=True)
    for exe in (MK_REC, MK_LIG, MK_EXP, VINA):
        if not os.path.exists(exe):
            raise SystemExit(f"nao encontrei {exe}")

    log("=" * 72)
    log(f"1. SUPERPOSICAO — tudo levado ao frame do {FRAME}")
    log("=" * 72)
    caminhos = {}
    for pdb_id in [FRAME] + [c[0] for c in CASOS]:
        caminhos[pdb_id], _ = alinha_ao_frame(pdb_id)

    log("\n" + "=" * 72)
    log("2. SEPARACAO E PREPARACAO")
    log("=" * 72)
    dados = {}
    log(f"\n{FRAME} / {LIG_FRAME} (covalente — so define o sitio)")
    rec_frame_pdb, lig_frame_pdb = separa(caminhos[FRAME], FRAME, LIG_FRAME)
    ligantes_ref_pdb = [lig_frame_pdb]

    for pdb_id, lig in CASOS:
        log(f"\n{pdb_id} / {lig}")
        rec_pdb, lig_pdb = separa(caminhos[pdb_id], pdb_id, lig)
        ref_sdf, ref_mol = ligante_com_ordens(pdb_id, lig, lig_pdb)
        dados[(pdb_id, lig)] = dict(rec_pdb=rec_pdb, ref_sdf=ref_sdf,
                                    ref_mol=ref_mol, lig_pdb=lig_pdb)
        ligantes_ref_pdb.append(lig_pdb)

    log("\n-- caixa de busca --")
    centro, tamanho = caixa_comum(ligantes_ref_pdb)

    log("\n-- receptores --")
    rec_pdbqt = {}
    rec_pdbqt[FRAME], _ = prepara_receptor(FRAME, rec_frame_pdb, centro, tamanho)
    for (pdb_id, lig), d in dados.items():
        rec_pdbqt[pdb_id], _ = prepara_receptor(pdb_id, d["rec_pdb"], centro, tamanho)

    log("\n-- ligantes --")
    for (pdb_id, lig), d in dados.items():
        d["lig_pdbqt"] = prepara_ligante(d["ref_sdf"], f"{pdb_id}_{lig}")

    resultados = []

    log("\n" + "=" * 72)
    log("3. TESTE 1 — REDOCKING (ligante no proprio cristal)")
    log("=" * 72)
    for (pdb_id, lig), d in dados.items():
        if not (rec_pdbqt.get(pdb_id) and d.get("lig_pdbqt")):
            log(f"{pdb_id}/{lig}: preparacao incompleta, pulado")
            continue
        tag = f"redock_{pdb_id}_{lig}"
        out, aff = doca(rec_pdbqt[pdb_id], centro, tamanho, d["lig_pdbqt"], tag)
        if not out:
            continue
        rs = rmsds_contra_cristal(out, d["ref_mol"], tag)
        if rs:
            resultados.append(("REDOCK", f"{pdb_id}/{lig}", aff, rs[0], min(rs)))
            log(f"{pdb_id}/{lig}: {aff} kcal/mol | pose 1 = {rs[0]:.2f} A | "
                f"melhor das {len(rs)} = {min(rs):.2f} A")

    log("\n" + "=" * 72)
    log(f"4. TESTE 2 — CROSS-DOCKING no receptor de triagem ({FRAME})")
    log("=" * 72)
    if rec_pdbqt.get(FRAME):
        for (pdb_id, lig), d in dados.items():
            if not d.get("lig_pdbqt"):
                continue
            tag = f"cross_{FRAME}_{lig}"
            out, aff = doca(rec_pdbqt[FRAME], centro, tamanho, d["lig_pdbqt"], tag)
            if not out:
                continue
            rs = rmsds_contra_cristal(out, d["ref_mol"], tag)
            if rs:
                resultados.append(("CROSS", f"{FRAME}<-{lig}", aff, rs[0], min(rs)))
                log(f"{lig} em {FRAME}: {aff} kcal/mol | pose 1 = {rs[0]:.2f} A | "
                    f"melhor das {len(rs)} = {min(rs):.2f} A")
    else:
        log(f"receptor {FRAME} nao preparado — cross-docking impossivel")

    log("\n" + "=" * 72)
    log("VEREDICTO")
    log("=" * 72)
    if not resultados:
        log("NADA RODOU. Protocolo nao validado.")
        sys.exit(1)
    for tipo, nome, aff, r1, rbest in resultados:
        v = "PASSOU" if r1 <= 2.0 else ("recuperada" if rbest <= 2.0 else "FALHOU")
        log(f"{tipo:7s} {nome:16s} aff={str(aff):>6s}  pose1={r1:5.2f} A  "
            f"melhor={rbest:5.2f} A  -> {v}")

    redock = [r for r in resultados if r[0] == "REDOCK"]
    cross = [r for r in resultados if r[0] == "CROSS"]
    log("")
    if redock and all(r[3] <= 2.0 for r in redock):
        log("REDOCKING: protocolo reproduz a pose cristalografica. VALIDADO.")
    else:
        log("REDOCKING: nao reproduziu a pose. NAO seguir para a fatia 2 assim.")
    if cross:
        if all(r[3] <= 2.0 for r in cross):
            log(f"CROSS-DOCK: {FRAME} serve como receptor de triagem. VALIDADO.")
        elif any(r[4] <= 2.0 for r in cross):
            log(f"CROSS-DOCK: pose certa aparece mas nao em 1o lugar no {FRAME}. "
                "Aceitavel para triagem (o filtro e por lote, nao por pose unica), "
                "mas registrar.")
        else:
            log(f"CROSS-DOCK: {FRAME} NAO reproduz as poses. Rever a escolha de "
                "receptor antes da fatia 2.")


if __name__ == "__main__":
    main()
