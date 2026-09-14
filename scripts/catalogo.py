"""
Catalogo de alvos de doencas negligenciadas.

Mede TODOS os candidatos de uma vez e guarda: quantas estruturas existem, quantos
inibidores medidos, e baixa os ativos. Assim a proxima escolha de alvo nao custa
uma tarde de pesquisa — ja esta medida e no disco.

Guarda tambem os alvos HUMANOS equivalentes, quando existem: inibir a proteina do
parasita sem inibir a do hospedeiro e a pergunta de seletividade que um laboratorio
faz, e sem esses dados nao ha como responder.

  python scripts/catalogo.py            mede tudo e salva
  python scripts/catalogo.py --ativos   idem, e baixa os compostos de cada alvo
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = r"C:\Higgsfield Games\keys"
SAIDA = os.path.join(BASE, "results", "catalogo")
API = "https://www.ebi.ac.uk/chembl/api/data"
RCSB = "https://search.rcsb.org/rcsbsearch/v2/query"

# (doenca, apelido, termo no ChEMBL, termo no PDB, sitio, ORGANISMO exigido)
ALVOS = [
    # ---- Chagas ----
    ("Chagas disease", "TcCYP51", "sterol 14-alpha demethylase Trypanosoma cruzi",
     "CYP51 Trypanosoma cruzi", "deep, heme", "Trypanosoma cruzi"),
    ("Chagas disease", "Cruzain", "cruzipain", "cruzain", "shallow cleft (REJECTED)", "Trypanosoma cruzi"),
    ("Chagas disease", "TcTR (trypanothione reductase)",
     "trypanothione reductase Trypanosoma cruzi", "trypanothione reductase Trypanosoma cruzi", "wide", "Trypanosoma cruzi"),
    ("Chagas disease", "TcGAPDH",
     "glyceraldehyde-3-phosphate dehydrogenase Trypanosoma cruzi",
     "GAPDH Trypanosoma cruzi", "cofactor pocket", "Trypanosoma cruzi"),
    # ---- Leishmaniose ----
    ("Leishmaniasis", "LdTR", "trypanothione reductase Leishmania",
     "trypanothione reductase Leishmania", "wide", "Leishmania"),
    ("Leishmaniasis", "LmPTR1", "pteridine reductase Leishmania",
     "pteridine reductase Leishmania", "folate pocket", "Leishmania"),
    ("Leishmaniasis", "Ld arginase", "arginase Leishmania", "arginase Leishmania", "metal", "Leishmania"),
    # ---- Doenca do sono ----
    ("Sleeping sickness", "TbPTR1", "pteridine reductase Trypanosoma brucei",
     "pteridine reductase Trypanosoma brucei", "folate pocket", "Trypanosoma brucei"),
    ("Sleeping sickness", "Rhodesain", "rhodesain", "rhodesain", "shallow cleft", "Trypanosoma brucei"),
    ("Sleeping sickness", "TbGAPDH", "glyceraldehyde-3-phosphate dehydrogenase Trypanosoma brucei",
     "GAPDH Trypanosoma brucei", "cofactor pocket", "Trypanosoma brucei"),
    # ---- Esquistossomose ----
    ("Schistosomiasis", "SmHDAC8", "histone deacetylase 8 Schistosoma",
     "histone deacetylase 8 Schistosoma", "deep, zinc", "Schistosoma"),
    ("Schistosomiasis", "SmTGR", "thioredoxin glutathione reductase Schistosoma",
     "thioredoxin glutathione reductase Schistosoma", "flavin", "Schistosoma"),
    ("Schistosomiasis", "SmGST", "glutathione S-transferase Schistosoma",
     "glutathione transferase Schistosoma", "medium", "Schistosoma"),
    ("Schistosomiasis", "SmDHODH", "dihydroorotate dehydrogenase Schistosoma",
     "dihydroorotate dehydrogenase Schistosoma", "deep", "Schistosoma"),
    # ---- Malaria ----
    ("Malaria", "PfDHFR", "dihydrofolate reductase Plasmodium falciparum",
     "dihydrofolate reductase Plasmodium", "folate pocket", "Plasmodium falciparum"),
    ("Malaria", "PfDHODH", "dihydroorotate dehydrogenase Plasmodium falciparum",
     "dihydroorotate dehydrogenase Plasmodium", "deep", "Plasmodium falciparum"),
    ("Malaria", "Plasmepsin II", "plasmepsin 2 Plasmodium falciparum",
     "plasmepsin Plasmodium", "aspartic protease", "Plasmodium falciparum"),
    ("Malaria", "Falcipain-2", "falcipain-2", "falcipain", "shallow cleft", "Plasmodium falciparum"),
    # ---- Tuberculose ----
    ("Tuberculosis", "InhA", "enoyl-[acyl-carrier-protein] reductase Mycobacterium tuberculosis",
     "InhA Mycobacterium tuberculosis", "deep, NADH", "Mycobacterium tuberculosis"),
    ("Tuberculosis", "DprE1", "decaprenylphosphoryl-beta-D-ribose oxidase Mycobacterium",
     "DprE1 Mycobacterium tuberculosis", "deep, flavin", "Mycobacterium"),
    # ---- Outras NTDs ----
    ("Toxoplasmosis", "TgCDPK1", "calcium-dependent protein kinase 1 Toxoplasma",
     "CDPK1 Toxoplasma gondii", "kinase pocket", "Toxoplasma"),
    ("Onchocerciasis", "Ov chitinase", "chitinase Onchocerca", "chitinase Onchocerca", "tunnel", "Onchocerca"),
    ("Lymphatic filariasis", "Bm asparaginyl-tRNA synthetase",
     "asparaginyl-tRNA synthetase Brugia", "Brugia malayi synthetase", "deep", "Brugia"),
    ("Mycetoma", "Mm CYP51", "sterol 14-alpha demethylase Madurella",
     "CYP51 Madurella", "deep, heme", "Madurella"),
    ("Amoebiasis", "Eh alcohol dehydrogenase", "alcohol dehydrogenase Entamoeba",
     "alcohol dehydrogenase Entamoeba", "metal", "Entamoeba"),
    # ---- contrapartes HUMANAS, para seletividade ----
    ("[human counterpart]", "Human CYP51", "lanosterol 14-alpha demethylase Homo sapiens",
     "human CYP51", "deep, heme", "Homo sapiens"),
    ("[human counterpart]", "Human HDAC8", "histone deacetylase 8 Homo sapiens",
     "human HDAC8", "deep, zinc", "Homo sapiens"),
    ("[human counterpart]", "Human DHFR", "dihydrofolate reductase Homo sapiens",
     "human dihydrofolate reductase", "folate pocket", "Homo sapiens"),
    ("[human counterpart]", "Cathepsin L", "cathepsin L Homo sapiens",
     "human cathepsin L", "shallow cleft", "Homo sapiens"),
]


def get(url, tentativas=3):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ehrlich/1.0"})
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            if i == tentativas - 1:
                return None
            time.sleep(2)
    return None


def acha_alvo(termo, organismo=None):
    """Busca por texto traz o alvo de QUALQUER organismo — inclusive o humano
    quando se procura o do parasita. Sem conferir o organismo, o catalogo enche
    de numero que parece certo e nao e."""
    d = get(f"{API}/target/search?q={urllib.parse.quote(termo)}&format=json&limit=25")
    if not d:
        return None
    candidatos = [t for t in d.get("targets", [])
                  if t.get("target_type") == "SINGLE PROTEIN"]
    if organismo:
        alvo = organismo.lower()
        exatos = [t for t in candidatos
                  if alvo in (t.get("organism") or "").lower()]
        if not exatos:
            return None          # melhor nao ter numero do que ter o errado
        candidatos = exatos
    # entre os do organismo certo, o que tem mais dados medidos
    melhor, melhor_n = None, -1
    for t in candidatos[:6]:
        n = conta_medidas(t["target_chembl_id"])
        if n > melhor_n:
            melhor, melhor_n = t, n
    if melhor is None:
        return None
    return {"id": melhor["target_chembl_id"], "nome": melhor.get("pref_name"),
            "organismo": melhor.get("organism"), "medidas": melhor_n}


def conta_medidas(tid):
    d = get(f"{API}/activity?target_chembl_id={tid}"
            "&standard_type__in=IC50,Ki&format=json&limit=1")
    return d["page_meta"]["total_count"] if d else 0


def conta_pdb(termo):
    q = {"query": {"type": "terminal", "service": "full_text",
                   "parameters": {"value": termo}},
         "return_type": "entry",
         "request_options": {"paginate": {"start": 0, "rows": 1}}}
    d = get(RCSB + "?json=" + urllib.parse.quote(json.dumps(q)))
    return d.get("total_count", 0) if d else 0


def baixa_ativos(tid, destino):
    """Todos os compostos medidos daquele alvo, com SMILES e potencia."""
    regs, url, pag = [], (f"{API}/activity?target_chembl_id={tid}"
                          "&standard_type__in=IC50,Ki&format=json&limit=1000"), 0
    while url and pag < 15:
        d = get(url)
        if not d:
            break
        regs.extend(d["activities"])
        nxt = d["page_meta"].get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else None
        pag += 1

    por_mol = {}
    for a in regs:
        smi, val, un = a.get("canonical_smiles"), a.get("standard_value"), a.get("standard_units")
        if not smi or val is None or un != "nM":
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        cid = a["molecule_chembl_id"]
        if val > 0 and (cid not in por_mol or val < por_mol[cid]["nM"]):
            por_mol[cid] = {"smiles": smi, "nM": val, "tipo": a.get("standard_type")}
    saida = [{"chembl_id": k, **v} for k, v in por_mol.items()]
    with open(destino, "w") as fh:
        json.dump(saida, fh)
    return len(saida)


def main():
    baixar = "--ativos" in sys.argv
    os.makedirs(SAIDA, exist_ok=True)
    catalogo = []

    print(f"{'doenca':<22} {'alvo':<34} {'PDB':>5} {'medidas':>8}  sitio")
    print("-" * 96)
    for doenca, apelido, q_chembl, q_pdb, sitio, organismo in ALVOS:
        alvo = acha_alvo(q_chembl, organismo)
        medidas = alvo["medidas"] if alvo else 0
        n_pdb = conta_pdb(q_pdb)
        item = {"doenca": doenca, "alvo": apelido, "sitio": sitio,
                "pdb": n_pdb, "medidas": medidas,
                "chembl": alvo["id"] if alvo else None,
                "chembl_nome": alvo["nome"] if alvo else None,
                "organismo": alvo["organismo"] if alvo else None}
        if baixar and alvo and medidas >= 25:
            arq = os.path.join(SAIDA, f"ativos_{apelido.replace(' ', '_').replace('(', '').replace(')', '')}.json")
            item["ativos_baixados"] = baixa_ativos(alvo["id"], arq)
            item["arquivo"] = os.path.basename(arq)
        catalogo.append(item)
        marca = "*" if medidas >= 100 and n_pdb >= 10 else " "
        print(f"{marca}{doenca:<21} {apelido:<34} {n_pdb:>5} {medidas:>8}  {sitio}")

    catalogo.sort(key=lambda x: -(x["medidas"] or 0))
    with open(os.path.join(SAIDA, "catalogo.json"), "w") as fh:
        json.dump({"gerado_em": "2026-09-14", "alvos": catalogo}, fh, indent=1)

    bons = [c for c in catalogo if c["medidas"] >= 100 and c["pdb"] >= 10]
    print(f"\n{len(catalogo)} alvos medidos · {len(bons)} trabalhaveis "
          "(>=100 medidas e >=10 estruturas)")
    print(f"gravado em {SAIDA}")


if __name__ == "__main__":
    main()
