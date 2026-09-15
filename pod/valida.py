"""
Validacao de alvo, autonoma, para rodar no pod.

Recebe o alvo por argumento e faz tudo: acha o cristal, prepara o receptor,
coleta os inibidores medidos, pareia decoys, roda o enriquecimento e diz o AUC.

  python valida.py "<termo PDB>" "<termo ChEMBL>" "<organismo>" [n_ativos]

O criterio e o mesmo que reprovou a cruzaina e o CYP51: AUC >= 0,70. Fixado
antes de rodar, como sempre.
"""

import json, os, subprocess, sys, time, urllib.parse, urllib.request
from concurrent.futures import ProcessPoolExecutor

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

RDLogger.DisableLog("rdApp.*")

BASE = "/work"
VINA = f"{BASE}/vina"
MK_LIG = "mk_prepare_ligand.py"
MK_REC = "mk_prepare_receptor.py"
API = "https://www.ebi.ac.uk/chembl/api/data"
RCSB = "https://search.rcsb.org/rcsbsearch/v2/query"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

COFATORES = {"NAD", "NAI", "NAP", "NDP", "FAD", "FMN", "HEM", "ZN", "MG", "MN"}
IGNORAR = {"HOH","SO4","GOL","EDO","PO4","CL","NA","K","CA","ACT","DMS","MES",
           "TRS","PEG","IOD","BR","NO3","FMT","ACY","IMD","CIT","EPE","MPD","SCN",
           # familia do polietilenoglicol e outros aditivos de cristalizacao: nao
           # sao ligantes, e um deles (PG4) chegou a definir a caixa de docking
           "PG4","PGE","P6G","1PE","2PE","PE4","PE5","PE8","XPE","7PE","12P",
           "P33","DIO","TRT","BME","DTT","TCE","SIN","MRD","BU3","GOL","FLC",
           "TAR","MLI","MLA","SUC","AKR","NH4","UNX","UNL"}
EXH = 8
SEED = 42
N_ATIVOS = int(sys.argv[4]) if len(sys.argv) > 4 else 50
DECOYS_POR_ATIVO = 12


def get(url, tipo="json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = r.read()
    return json.loads(d) if tipo == "json" else d.decode("utf-8", "replace")


def log(m): print(m, flush=True)


# ---------------------------------------------------------------- cristal
def confere_identidade(pdb_id, termo_proteina, organismo):
    """A estrutura e mesmo esta proteina, neste organismo?

    O full_text do RCSB casa por relevancia, nao por identidade. Procurando
    GAPDH de T. cruzi ele devolveu di-hidrofolato redutase; procurando
    tripanotiona redutase de T. cruzi devolveu a de T. brucei, e o validador
    docou inibidores de uma especie na proteina de outra e publicou o AUC
    como se fosse verdade. Sem esta conferencia o resto nao significa nada.
    """
    try:
        ids = (get("https://data.rcsb.org/rest/v1/core/entry/%s" % pdb_id)
               .get("rcsb_entry_container_identifiers", {})
               .get("polymer_entity_ids") or ["1"])
    except Exception:
        return False
    esperado_org = [p for p in organismo.lower().split() if len(p) > 2]
    chaves = [p for p in termo_proteina.lower().replace("-", " ").split()
              if len(p) > 3]
    for eid in ids[:6]:
        try:
            d = get("https://data.rcsb.org/rest/v1/core/polymer_entity/%s/%s"
                    % (pdb_id, eid))
        except Exception:
            continue
        desc = ((d.get("rcsb_polymer_entity") or {})
                .get("pdbx_description") or "").lower()
        orgs = " ".join((o.get("scientific_name") or "")
                        for o in (d.get("rcsb_entity_source_organism") or [])).lower()
        if not all(p in orgs for p in esperado_org):
            continue
        acertos = sum(1 for k in chaves if k in desc)
        if acertos < max(1, (len(chaves) + 1) // 2):
            continue
        return True
    return False


def acha_cristal(termo_pdb, termo_proteina=None, organismo=None):
    # Duas consultas em vez de uma. A frase inteira e precisa mas estreita:
    # para a tripanotiona redutase ela devolvia 13 entradas. O nome da
    # proteina sozinho devolve 100, de varios organismos, e quem separa o
    # organismo certo e a conferencia de identidade, nao a sorte da busca.
    termos = [termo_pdb]
    if termo_proteina and termo_proteina.lower() not in termo_pdb.lower():
        termos.append(termo_proteina)
    elif termo_proteina:
        termos.append(termo_proteina)
    ids = []
    for t in termos:
        q = {"query": {"type": "terminal", "service": "full_text",
                       "parameters": {"value": t}},
             "return_type": "entry",
             "request_options": {"paginate": {"start": 0, "rows": 100}}}
        try:
            achados = [x["identifier"] for x in
                       get(RCSB + "?json=" + urllib.parse.quote(json.dumps(q)))
                       .get("result_set", [])]
        except Exception as e:
            log("  busca '%s' falhou: %s" % (t, e))
            achados = []
        for i in achados:
            if i not in ids:
                ids.append(i)
    log("  %d estruturas na busca" % len(ids))

    candidatos = []
    for pdb_id in ids[:60]:
        # identidade primeiro: se nao e a proteina certa no organismo certo,
        # nem vale gastar chamada olhando os ligantes dela
        if termo_proteina and organismo:
            if not confere_identidade(pdb_id, termo_proteina, organismo):
                continue
        try:
            e = get(f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}")
        except Exception:
            continue
        for eid in (e.get("rcsb_entry_container_identifiers", {})
                     .get("non_polymer_entity_ids") or []):
            try:
                ne = get("https://data.rcsb.org/rest/v1/core/nonpolymer_entity/"
                         f"{pdb_id}/{eid}")
                code = (ne.get("pdbx_entity_nonpoly") or {}).get("comp_id")
                if not code or code in IGNORAR or code in COFATORES:
                    continue
                c = get(f"https://data.rcsb.org/rest/v1/core/chemcomp/{code}")
                smi = next((x["descriptor"] for x in
                            (c.get("pdbx_chem_comp_descriptor") or [])
                            if x.get("type","").startswith("SMILES")), None)
                if not smi: continue
                mol = Chem.MolFromSmiles(smi)
                if mol is None: continue
                n = mol.GetNumHeavyAtoms()
                t = rdMolDescriptors.CalcNumRotatableBonds(mol)
                if not (12 <= n <= 40 and t <= 10): continue
                # covalente?
                hdr = get(f"https://files.rcsb.org/header/{pdb_id}.pdb", "txt")
                if any(l.startswith("LINK") and code in l for l in hdr.splitlines()):
                    continue
                res = next((float(l.split()[3]) for l in hdr.splitlines()
                            if "RESOLUTION." in l and l.split()[3][0].isdigit()), 9.9)
                candidatos.append((res, pdb_id, code, n, t))
                log(f"    candidato: {pdb_id}/{code}  {res} A  {n} atomos  {t} torsoes")
            except Exception:
                continue
    candidatos.sort(key=lambda c: c[0])
    return candidatos


# ---------------------------------------------------------------- receptor
def prepara_receptor(pdb_id, lig_code):
    p = f"{BASE}/target/{pdb_id}.pdb"
    if not os.path.exists(p):
        urllib.request.urlretrieve(
            f"https://files.rcsb.org/download/{pdb_id}.pdb", p)
    linhas = open(p).readlines()
    cadeia = next((l[21] for l in linhas
                   if l.startswith("HETATM") and l[17:20].strip() == lig_code), None)
    rec, lig, cof = [], [], []
    for l in linhas:
        if not l.startswith(("ATOM","HETATM")): continue
        if l[16] not in (" ","A") or l[76:78].strip() == "H": continue
        rn = l[17:20].strip()
        if l.startswith("ATOM") and l[21] == cadeia: rec.append(l)
        elif l.startswith("HETATM") and rn in COFATORES and l[21] == cadeia: cof.append(l)
        elif l.startswith("HETATM") and rn == lig_code and l[21] == cadeia: lig.append(l)

    open(f"{BASE}/target/rec.pdb","w").writelines(rec + ["END\n"])
    open(f"{BASE}/target/lig.pdb","w").writelines(lig + ["END\n"])
    open(f"{BASE}/target/cof.pdb","w").writelines(cof)
    log(f"  receptor {len(rec)} atomos · cofator {len(cof)} · ligante {len(lig)}")

    import numpy as np
    xyz = np.array([[float(l[30:38]),float(l[38:46]),float(l[46:54])] for l in lig])
    centro = xyz.mean(axis=0)
    tam = (xyz.max(axis=0) - xyz.min(axis=0)) + 10.0
    tam = [max(t, 20.0) for t in tam]

    base = f"{BASE}/target/rec"
    r = subprocess.run([MK_REC,"--read_pdb",f"{BASE}/target/rec.pdb","-o",base,"-p",
        "--box_center",*[f"{v:.3f}" for v in centro],
        "--box_size",*[f"{v:.3f}" for v in tam],
        "--default_altloc","A","--charge_model","gasteiger","--forgive_extra_bonds"],
        capture_output=True, text=True)
    pdbqt = next((base+s for s in (".pdbqt","_rigid.pdbqt") if os.path.exists(base+s)), None)
    if not pdbqt:
        log("  !! receptor nao preparou:\n" + r.stderr[-400:]); return None, None, None

    # cofator entra direto no PDBQT (o Meeko nao monta template para ele)
    TIPO = {"C":"C","N":"NA","O":"OA","S":"SA","P":"P","FE":"Fe","ZN":"Zn","MG":"Mg"}
    extra = []
    for l in cof:
        el = (l[76:78].strip() or l[12:14].strip()).upper()
        if el in TIPO:
            extra.append(f"{l[:54]}  1.00  0.00     0.000 {TIPO[el]:<2}\n")
    if extra:
        with open(pdbqt,"a") as fh: fh.writelines(extra)
        log(f"  cofator anexado: {len(extra)} atomos")

    # deixa o alvo descrito em disco: a triagem le daqui e nao do meu codigo.
    # Sem isto, aprovar um alvo novo exigia eu reescrever o motor na mao.
    json.dump({"receptor": pdbqt, "pdb": pdb_id, "ligante": lig_code,
               "centro": [float(v) for v in centro],
               "tamanho": [float(v) for v in tam]},
              open(BASE + "/target/alvo.json", "w"), indent=1)
    return pdbqt, centro, tam


# ---------------------------------------------------------------- ativos
def alvo_chembl(termo, organismo):
    d = get(f"{API}/target/search?q={urllib.parse.quote(termo)}&format=json&limit=25")
    cands = [t for t in d.get("targets",[])
             if t.get("target_type")=="SINGLE PROTEIN"
             and organismo.lower() in (t.get("organism") or "").lower()]
    melhor, n_melhor = None, -1
    for t in cands[:6]:
        a = get(f"{API}/activity?target_chembl_id={t['target_chembl_id']}"
                "&standard_type__in=IC50,Ki&format=json&limit=1")
        n = a["page_meta"]["total_count"]
        if n > n_melhor: melhor, n_melhor = t, n
    return (melhor["target_chembl_id"], melhor["pref_name"], n_melhor) if melhor else (None,None,0)


def coleta(tid, limite_paginas=8):
    regs, url, pag = [], (f"{API}/activity?target_chembl_id={tid}"
                          "&standard_type__in=IC50,Ki&format=json&limit=1000"), 0
    while url and pag < limite_paginas:
        d = get(url); regs.extend(d["activities"]); pag += 1
        nxt = d["page_meta"].get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else None
    por = {}
    for a in regs:
        smi, v, u = a.get("canonical_smiles"), a.get("standard_value"), a.get("standard_units")
        if not smi or v is None or u != "nM": continue
        try: v = float(v)
        except Exception: continue
        cid = a["molecule_chembl_id"]
        if 0 < v and (cid not in por or v < por[cid]["nM"]):
            por[cid] = {"smiles":smi,"nM":v}
    saida = []
    for cid, d in por.items():
        m = Chem.MolFromSmiles(d["smiles"])
        if m is None or d["nM"] > 10000: continue
        mw = Descriptors.MolWt(m); t = rdMolDescriptors.CalcNumRotatableBonds(m)
        if mw > 600 or t > 10: continue
        saida.append({"id":cid,"smiles":d["smiles"],"nM":d["nM"],"mw":mw,
                      "logp":Descriptors.MolLogP(m),"tors":t,
                      "hbd":rdMolDescriptors.CalcNumHBD(m),
                      "hba":rdMolDescriptors.CalcNumHBA(m)})
    saida.sort(key=lambda x: x["nM"])
    return saida


def pool_decoys(n_alvo=6000):
    cache = f"{BASE}/pool.json"
    if os.path.exists(cache): return json.load(open(cache))
    pool, vistos = [], set()
    for off in range(0, 60000, 2000):
        try:
            d = get(f"{API}/molecule?format=json&limit=200&offset={off}"
                    "&molecule_properties__full_mwt__gte=200"
                    "&molecule_properties__full_mwt__lte=600")
        except Exception: continue
        for m in d.get("molecules",[]):
            st = m.get("molecule_structures") or {}
            smi, cid = st.get("canonical_smiles"), m.get("molecule_chembl_id")
            if smi and cid not in vistos:
                vistos.add(cid); pool.append({"id":cid,"smiles":smi})
        if len(pool) >= n_alvo: break
    json.dump(pool, open(cache,"w")); return pool


def pareia(ativos, pool):
    def props(smi):
        m = Chem.MolFromSmiles(smi)
        return None if m is None else (Descriptors.MolWt(m), Descriptors.MolLogP(m),
            rdMolDescriptors.CalcNumRotatableBonds(m), rdMolDescriptors.CalcNumHBD(m),
            rdMolDescriptors.CalcNumHBA(m))
    pp = [(p, props(p["smiles"])) for p in pool]
    pp = [(p, q) for p, q in pp if q]
    ids = {a["id"] for a in ativos}; usados = set(); decoys = []
    for a in ativos:
        pa = (a["mw"], a["logp"], a["tors"], a["hbd"], a["hba"])
        n = 0
        for p, q in pp:
            if p["id"] in usados or p["id"] in ids: continue
            if (abs(q[0]-pa[0])<=30 and abs(q[1]-pa[1])<=1.2 and abs(q[2]-pa[2])<=2
                    and abs(q[3]-pa[3])<=2 and abs(q[4]-pa[4])<=2):
                usados.add(p["id"]); decoys.append(p); n += 1
                if n >= DECOYS_POR_ATIVO: break
    return decoys


# ---------------------------------------------------------------- docking
def gera(args):
    cid, smi, tag = args
    out = f"{BASE}/ligs/{tag}_{cid}.pdbqt"
    if os.path.exists(out): return True
    m = Chem.MolFromSmiles(smi)
    if m is None: return False
    m = Chem.AddHs(m); p = AllChem.ETKDGv3(); p.randomSeed = SEED
    if AllChem.EmbedMolecule(m, p) != 0: return False
    try: AllChem.MMFFOptimizeMolecule(m, maxIters=500)
    except Exception: pass
    sdf = out.replace(".pdbqt",".sdf"); Chem.MolToMolFile(m, sdf)
    r = subprocess.run([MK_LIG,"-i",sdf,"-o",out], capture_output=True)
    os.remove(sdf)
    return os.path.exists(out)


def doca(args):
    lig, rec, centro, tam = args
    nome = os.path.basename(lig).replace(".pdbqt","")
    saida = f"{BASE}/docked/{nome}.txt"
    if os.path.exists(saida): return
    r = subprocess.run([VINA,"--receptor",rec,"--ligand",lig,
        "--center_x",str(centro[0]),"--center_y",str(centro[1]),"--center_z",str(centro[2]),
        "--size_x",str(tam[0]),"--size_y",str(tam[1]),"--size_z",str(tam[2]),
        "--exhaustiveness",str(EXH),"--seed",str(SEED),"--num_modes","1","--cpu","1"],
        capture_output=True, text=True)
    sc = None
    for l in r.stdout.splitlines():
        p = l.split()
        if len(p)>=2 and p[0]=="1":
            try: sc = float(p[1]); break
            except ValueError: pass
    open(saida,"w").write(str(sc))


def registra_parada(motivo, extra=None):
    """Toda saida antecipada grava o motivo REAL.

    Antes quem registrava era o ciclo, e ele so sabia que nao houve
    resultado, entao escrevia um palpite em forma de ou/ou: sem cristal
    nao-covalente OU sem inibidor medido. Para a pteridina redutase, que tem
    79 inibidores medidos, esse palpite era falso, e ia para a pagina como se
    fosse ciencia.
    """
    d = {"auc": None, "motivo": motivo}
    if extra:
        d.update(extra)
    json.dump(d, open(BASE + "/out/resultado.json", "w"), indent=1)
    log("  PARANDO: " + motivo)


def main():
    termo_pdb, termo_chembl, organismo = sys.argv[1], sys.argv[2], sys.argv[3]
    t0 = time.time()
    log(f"ALVO: {termo_chembl} [{organismo}]\n")

    log("1. procurando cristal nao-covalente com ligante drug-like")
    candidatos = acha_cristal(termo_pdb, termo_chembl, organismo)
    if not candidatos:
        registra_parada("no PDB entry matched this protein in this organism, "
                        "or none had a non-covalent drug-like ligand")
        return
    log(f"  {len(candidatos)} cristais candidatos")

    log("2. preparando receptor")
    rec = centro = tam = None
    pdb_id = code = None
    for cres, cpdb, ccode, cn, ct in candidatos:
        log(f"  tentando {cpdb}/{ccode}  {cres} A  {cn} atomos  {ct} torsoes")
        try:
            rec, centro, tam = prepara_receptor(cpdb, ccode)
        except Exception as e:
            log(f"  !! {type(e).__name__}: {e}"); rec = None
        if rec:
            pdb_id, code = cpdb, ccode
            break
    if not rec:
        registra_parada("a matching crystal was found but the receptor could "
                        "not be prepared from any candidate")
        return
    log(f"  escolhido {pdb_id}/{code} · caixa centro "
        f"{[round(v,1) for v in centro]} tamanho {[round(v,1) for v in tam]}")

    log("3. inibidores medidos")
    tid, nome, total = alvo_chembl(termo_chembl, organismo)
    if not tid:
        registra_parada("no single-protein ChEMBL target for this name "
                        "in this organism")
        return
    log(f"  {tid} ({nome}) — {total} medidas")
    ativos = coleta(tid)[:N_ATIVOS]
    if not ativos:
        registra_parada("ChEMBL has %d measurements for this target but none "
                        "usable: needs IC50 or Ki in nM, potency under 10 uM, "
                        "molecular weight under 600 and at most 10 rotatable "
                        "bonds" % total,
                        {"chembl": tid, "medidas": total})
        return
    log(f"  {len(ativos)} aproveitaveis, mais potente {ativos[0]['nM']:.2f} nM\n")

    log("4. decoys pareados")
    decoys = pareia(ativos, pool_decoys())
    log(f"  {len(decoys)} decoys\n")

    log("5. gerando 3D")
    tarefas = ([(a["id"],a["smiles"],"ativo") for a in ativos]
               + [(d["id"],d["smiles"],"decoy") for d in decoys])
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        ok = sum(1 for r in ex.map(gera, tarefas) if r)
    log(f"  {ok}/{len(tarefas)} preparados\n")

    log(f"6. docking em {os.cpu_count()} nucleos")
    ligs = [f"{BASE}/ligs/{f}" for f in sorted(os.listdir(f"{BASE}/ligs"))
            if f.endswith(".pdbqt")]
    t1 = time.time()
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        list(ex.map(doca, [(l, rec, centro, tam) for l in ligs]))
    dt = time.time() - t1
    log(f"  {len(ligs)} moleculas em {dt/60:.1f} min "
        f"({dt/max(1,len(ligs)):.2f} s/molecula com {os.cpu_count()} nucleos)\n")

    log("7. resultado")
    res_list = []
    for f in os.listdir(f"{BASE}/docked"):
        if not f.endswith(".txt"): continue
        try: sc = float(open(f"{BASE}/docked/{f}").read().strip())
        except Exception: continue
        res_list.append((sc, 1 if f.startswith("ativo_") else 0, f[:-4]))
    at = [r for r in res_list if r[1]==1]; de = [r for r in res_list if r[1]==0]
    if not at or not de: log("  faltam dados"); return
    pares = ganhos = emp = 0
    for s1,y1,_ in at:
        for s2,y2,_ in de:
            pares += 1
            if s1 < s2: ganhos += 1
            elif s1 == s2: emp += 1
    auc = (ganhos + 0.5*emp)/pares
    MIN_ATIVOS = 15
    if len(at) < MIN_ATIVOS:
        # AUC sobre 5 ativos nao e veredicto, e ruido com aparencia de numero.
        # Foi assim que a tripanotiona redutase "reprovou" com 0,209.
        registra_parada("only %d actives survived preparation and docking, "
                        "below the %d needed for an enrichment verdict to mean "
                        "anything" % (len(at), MIN_ATIVOS),
                        {"auc_bruto": round(auc, 3), "n_ativos": len(at),
                         "n_decoys": len(de), "pdb": pdb_id})
        return
    res_list.sort(key=lambda r: r[0])
    def ef(frac):
        k = max(1, round(len(res_list)*frac))
        topo = sum(1 for s,y,_ in res_list[:k] if y==1)
        esp = k*len(at)/len(res_list)
        return topo/esp if esp else 0
    log(f"  AUC-ROC : {auc:.3f}   (corte 0,70)")
    log(f"  EF 1%   : {ef(0.01):.1f}x")
    log(f"  EF 5%   : {ef(0.05):.1f}x")
    log(f"  ativos {len(at)} · decoys {len(de)}")
    log(f"\n  VEREDICTO: {'PASSOU' if auc >= 0.70 else 'reprovado'}")
    json.dump({"alvo":termo_chembl,"pdb":pdb_id,"ligante":code,"auc":auc,
               "ef1":ef(0.01),"ef5":ef(0.05),"n_ativos":len(at),"n_decoys":len(de),
               "segundos_por_molecula":dt/max(1,len(ligs)),
               "nucleos":os.cpu_count(),"minutos":dt/60},
              open(f"{BASE}/out/resultado.json","w"), indent=1)
    log(f"\ntempo total: {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        import traceback
        traceback.print_exc()
        # a pagina precisa poder dizer o que quebrou, com o nome do erro,
        # em vez de herdar um palpite sobre cristal ou inibidor
        try:
            registra_parada("the validation run crashed: %s: %s"
                            % (type(_e).__name__, _e))
        except Exception:
            pass
        raise SystemExit(1)
