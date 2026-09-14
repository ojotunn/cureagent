"""
Mede os alvos candidatos antes de escolher a doenca.

Para cada um: quantas estruturas existem no PDB e quantos inibidores medidos
existem no ChEMBL. Sem isso a escolha vira palpite — e ja aprendemos com a
cruzaina que alvo bonito no papel pode nao ser trabalhavel.
"""

import json
import urllib.parse
import urllib.request

CANDIDATOS = [
    # (doenca, alvo, busca no ChEMBL, busca no PDB)
    ("Chagas", "TcCYP51 (sterol 14a-demethylase)",
     "sterol 14-alpha demethylase Trypanosoma cruzi", "CYP51 Trypanosoma cruzi"),
    ("Leishmaniasis", "LdCYP51",
     "sterol 14-alpha demethylase Leishmania", "CYP51 Leishmania"),
    ("Sleeping sickness", "TbPTR1 (pteridine reductase)",
     "pteridine reductase Trypanosoma brucei", "pteridine reductase Trypanosoma"),
    ("Sleeping sickness", "TbDHFR",
     "dihydrofolate reductase Trypanosoma brucei", "dihydrofolate reductase Trypanosoma"),
    ("Schistosomiasis", "SmTGR (thioredoxin glutathione reductase)",
     "thioredoxin glutathione reductase Schistosoma", "thioredoxin glutathione reductase Schistosoma"),
    ("Malaria", "PfDHFR",
     "dihydrofolate reductase Plasmodium falciparum", "dihydrofolate reductase Plasmodium"),
    ("Chagas", "Cruzain (JA REPROVADO)",
     "cruzipain", "cruzain"),
]

API = "https://www.ebi.ac.uk/chembl/api/data"
RCSB = "https://search.rcsb.org/rcsbsearch/v2/query"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ehrlich/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def chembl(termo):
    """Alvo + quantos compostos medidos com potencia."""
    try:
        d = get(f"{API}/target/search?q={urllib.parse.quote(termo)}"
                "&format=json&limit=5")
    except Exception:  # noqa: BLE001
        return None, 0, 0
    alvos = [t for t in d.get("targets", [])
             if t.get("target_type") == "SINGLE PROTEIN"]
    if not alvos:
        return None, 0, 0
    tid = alvos[0]["target_chembl_id"]
    try:
        a = get(f"{API}/activity?target_chembl_id={tid}"
                "&standard_type__in=IC50,Ki&format=json&limit=1")
        total = a["page_meta"]["total_count"]
    except Exception:  # noqa: BLE001
        total = 0
    return tid, total, len(alvos)


def pdb(termo):
    consulta = {
        "query": {"type": "terminal", "service": "full_text",
                  "parameters": {"value": termo}},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": 1}},
    }
    try:
        d = get(RCSB + "?json=" + urllib.parse.quote(json.dumps(consulta)))
        return d.get("total_count", 0)
    except Exception:  # noqa: BLE001
        return 0


print(f"{'doenca':<20} {'alvo':<38} {'PDB':>5} {'ChEMBL':>7} {'medidas':>8}")
print("-" * 82)
for doenca, alvo, q_chembl, q_pdb in CANDIDATOS:
    tid, medidas, _ = chembl(q_chembl)
    n_pdb = pdb(q_pdb)
    print(f"{doenca:<20} {alvo:<38} {n_pdb:>5} {tid or '—':>7} {medidas:>8}")
