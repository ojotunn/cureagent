"""
Existe um cristal de cruzaina com ligante PEQUENO e NAO-COVALENTE?

Se existir, da para validar pose de verdade (redocking com RMSD), o que os
peptidomimeticos de 13-14 torsoes do 1ME3/1ME4 nao permitem.

Criterio do que serve:
  - ligante com 8 a 40 atomos pesados (nao e ion, nao e peptideo gigante)
  - <= 10 torsoes rotaveis
  - SEM registro LINK ligando o ligante a uma cisteina (nao-covalente)
"""

import json
import urllib.parse
import urllib.request

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")

IGNORAR = {"HOH", "SO4", "GOL", "EDO", "PO4", "CL", "NA", "K", "MG", "CA",
           "ZN", "ACT", "DMS", "MES", "TRS", "PEG", "IOD", "BR", "NO3",
           "FMT", "ACY", "IMD", "CIT", "EPE", "MPD", "SCN"}


def get(url, tipo="json"):
    req = urllib.request.Request(url, headers={"User-Agent": "keys/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dados = r.read()
    return json.loads(dados) if tipo == "json" else dados.decode("utf-8", "replace")


def busca_pdbs():
    import sys
    termo = " ".join(sys.argv[1:]) or "cruzain cruzipain"
    print(f"buscando: {termo}")
    consulta = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": termo},
        },
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": 100}},
    }
    url = ("https://search.rcsb.org/rcsbsearch/v2/query?json="
           + urllib.parse.quote(json.dumps(consulta)))
    d = get(url)
    return [x["identifier"] for x in d.get("result_set", [])]


def ligantes_do_pdb(pdb_id):
    """Devolve [(codigo, smiles)] dos ligantes relevantes."""
    try:
        d = get(f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}")
    except Exception:  # noqa: BLE001
        return []
    ids = d.get("rcsb_entry_container_identifiers", {}).get(
        "non_polymer_entity_ids", []) or []
    achados = []
    for eid in ids:
        try:
            e = get("https://data.rcsb.org/rest/v1/core/nonpolymer_entity/"
                    f"{pdb_id}/{eid}")
        except Exception:  # noqa: BLE001
            continue
        comp = e.get("pdbx_entity_nonpoly", {})
        code = comp.get("comp_id")
        if not code or code in IGNORAR:
            continue
        try:
            c = get(f"https://data.rcsb.org/rest/v1/core/chemcomp/{code}")
        except Exception:  # noqa: BLE001
            continue
        smi = None
        for d2 in c.get("rcsb_chem_comp_descriptor", {}).items():
            pass
        desc = c.get("pdbx_chem_comp_descriptor", []) or []
        for x in desc:
            if x.get("type") == "SMILES_CANONICAL" and x.get("program") == "OpenEye OEToolkits":
                smi = x.get("descriptor")
                break
        if smi is None:
            for x in desc:
                if x.get("type", "").startswith("SMILES"):
                    smi = x.get("descriptor")
                    break
        if smi:
            achados.append((code, smi))
    return achados


def tem_link_covalente(pdb_id, code):
    try:
        txt = get(f"https://files.rcsb.org/header/{pdb_id}.pdb", tipo="txt")
    except Exception:  # noqa: BLE001
        return None
    for ln in txt.splitlines():
        if ln.startswith("LINK") and code in ln and "CYS" in ln:
            return True
    return False


def main():
    pdbs = busca_pdbs()
    print(f"{len(pdbs)} estruturas encontradas na busca por cruzain/cruzipain")
    print(f"{pdbs}\n")

    bons, covalentes, grandes = [], [], []
    for pdb_id in pdbs:
        for code, smi in ligantes_do_pdb(pdb_id):
            mol = Chem.MolFromSmiles(smi)
            if mol is None:
                continue
            pesados = mol.GetNumHeavyAtoms()
            if pesados < 8 or pesados > 40:
                continue
            tors = rdMolDescriptors.CalcNumRotatableBonds(mol)
            mw = Descriptors.MolWt(mol)
            cov = tem_link_covalente(pdb_id, code)
            info = (pdb_id, code, pesados, tors, round(mw, 1), cov)
            if cov:
                covalentes.append(info)
            elif tors <= 10:
                bons.append(info)
            else:
                grandes.append(info)
            print(f"  {pdb_id} {code:4s} {pesados:3d} atomos  {tors:2d} torsoes  "
                  f"MW {mw:6.1f}  covalente={cov}")

    print("\n" + "=" * 68)
    print("CANDIDATOS A VALIDACAO DE POSE (nao-covalente, <= 10 torsoes)")
    print("=" * 68)
    if not bons:
        print("  NENHUM. Validacao de pose nao e possivel neste alvo com")
        print("  cristais publicos. O enriquecimento passa a ser a unica prova.")
    for pdb_id, code, n, t, mw, _ in sorted(bons, key=lambda x: x[3]):
        print(f"  {pdb_id}  ligante {code}  {n} atomos  {t} torsoes  MW {mw}")
    print(f"\n({len(covalentes)} covalentes e {len(grandes)} flexiveis demais "
          "foram descartados)")


if __name__ == "__main__":
    main()
