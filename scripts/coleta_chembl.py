"""
Coleta inibidores de cruzaina MEDIDOS EXPERIMENTALMENTE (ChEMBL CHEMBL3563).

Serve para o teste que realmente importa para triagem virtual: ENRIQUECIMENTO.
O protocolo consegue por ativos conhecidos acima de inativos? E isso, e nao
reproduzir pose, que decide se olhar os 20 melhores de 4 milhoes faz sentido.

Filtro dos ativos:
  - IC50 ou Ki medidos, em nM, com valor
  - potencia <= 10 uM (pChEMBL >= 5) — generoso de proposito, para ter n
  - peso molecular <= 600, torsoes rotaveis <= 10  (perfil drug-like, que e o
    que a producao vai docar; NAO peptidomimeticos de 14 torsoes)
"""

import json
import os
import urllib.request

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")

BASE = r"C:\Higgsfield Games\keys"
OUT = os.path.join(BASE, "results", "frente_a")
API = "https://www.ebi.ac.uk/chembl/api/data"
ALVO = "CHEMBL3563"

MAX_TORSOES = 10
MAX_MW = 600.0


def pega(url):
    req = urllib.request.Request(url, headers={"User-Agent": "keys-validation/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def coleta_atividades():
    registros = []
    url = (f"{API}/activity?target_chembl_id={ALVO}"
           f"&standard_type__in=IC50,Ki&format=json&limit=1000")
    pagina = 0
    while url:
        d = pega(url)
        registros.extend(d["activities"])
        pagina += 1
        nxt = d["page_meta"].get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else None
        print(f"  pagina {pagina}: {len(registros)} atividades acumuladas", flush=True)
        if pagina >= 12:
            break
    return registros


def main():
    os.makedirs(OUT, exist_ok=True)
    print("coletando atividades do ChEMBL...", flush=True)
    atividades = coleta_atividades()

    por_mol = {}
    for a in atividades:
        smi = a.get("canonical_smiles")
        val = a.get("standard_value")
        unid = a.get("standard_units")
        if not smi or val is None or unid != "nM":
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if val <= 0:
            continue
        chid = a["molecule_chembl_id"]
        # guarda o mais potente por molecula
        if chid not in por_mol or val < por_mol[chid]["nM"]:
            por_mol[chid] = dict(smiles=smi, nM=val, tipo=a.get("standard_type"))

    print(f"\n{len(atividades)} atividades -> {len(por_mol)} moleculas unicas com valor em nM")

    linhas = []
    descartes = {"nao_leu": 0, "potencia": 0, "mw": 0, "torsoes": 0}
    hist_tors = {}
    for chid, d in por_mol.items():
        mol = Chem.MolFromSmiles(d["smiles"])
        if mol is None:
            descartes["nao_leu"] += 1
            continue
        if d["nM"] > 10000:
            descartes["potencia"] += 1
            continue
        mw = Descriptors.MolWt(mol)
        tors = rdMolDescriptors.CalcNumRotatableBonds(mol)
        hist_tors[tors] = hist_tors.get(tors, 0) + 1
        if mw > MAX_MW:
            descartes["mw"] += 1
            continue
        if tors > MAX_TORSOES:
            descartes["torsoes"] += 1
            continue
        linhas.append(dict(chembl_id=chid, smiles=d["smiles"], nM=d["nM"],
                           tipo=d["tipo"], mw=round(mw, 1), torsoes=tors,
                           logp=round(Descriptors.MolLogP(mol), 2),
                           hbd=rdMolDescriptors.CalcNumHBD(mol),
                           hba=rdMolDescriptors.CalcNumHBA(mol)))

    print(f"descartados: {descartes}")
    print(f"\nATIVOS APROVEITAVEIS: {len(linhas)}")

    print("\ndistribuicao de torsoes rotaveis (todos os medidos, antes do corte):")
    for t in sorted(hist_tors):
        barra = "#" * min(60, hist_tors[t])
        print(f"  {t:2d} torsoes: {hist_tors[t]:4d} {barra}")

    linhas.sort(key=lambda x: x["nM"])
    print("\n10 mais potentes que passaram o filtro:")
    for r in linhas[:10]:
        print(f"  {r['chembl_id']:15s} {r['tipo']:5s} {r['nM']:9.1f} nM  "
              f"MW {r['mw']:6.1f}  tors {r['torsoes']:2d}  logP {r['logp']:5.2f}")

    dest = os.path.join(OUT, "ativos_cruzaina.json")
    with open(dest, "w") as fh:
        json.dump(linhas, fh, indent=1)
    print(f"\ngravado: {dest}")


if __name__ == "__main__":
    main()
