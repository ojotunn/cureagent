"""
Zera o site para comecar uma campanha nova, com alvo novo.

Padrao: ARQUIVA, nao apaga. Os runs antigos saem dos contadores mas continuam
publicados como historico — o projeto inteiro se apoia em ter mostrado tambem
o que nao deu certo, e jogar isso fora custaria mais do que ganha.

  python scripts/reset.py                 arquiva e zera
  python scripts/reset.py --apagar        apaga de vez (irreversivel)
  python scripts/reset.py --so-mostrar    diz o que faria, sem tocar em nada

Depois de rodar: editar site/alvo.json com o alvo novo e trocar o PDB em
site/data/receptor.pdb.
"""

import json
import os
import shutil
import sys
import datetime

BASE = r"C:\Higgsfield Games\keys"
SITE = os.path.join(BASE, "site")
DADOS = os.path.join(SITE, "data")
WORK = os.path.join(BASE, "results", "frente_a")
ARQUIVO = os.path.join(BASE, "results", "arquivo")

VAZIO = {
    "gerado_em": None,
    "alvo": None,
    "triagem": {"moleculas_triadas": 0, "custo_gpu_usd": 0.0,
                "onde_rodou": None, "minutos": 0, "ranking": []},
    "validacao": {"enriquecimento": None, "pose": [], "controle_positivo": [],
                  "veredicto": None},
    "posts": [],
    "downloads": [],
    "roadmap": [],
    "roadmap_total": None,
    "historico": [],
}


def resumo_atual():
    """O que existe hoje, para virar uma linha de historico."""
    try:
        d = json.load(open(os.path.join(DADOS, "dados.json")))
    except Exception:  # noqa: BLE001
        return None
    alvo = d.get("alvo") or {}
    enr = (d.get("validacao") or {}).get("enriquecimento") or {}
    return {
        "alvo": alvo.get("nome"),
        "doenca": alvo.get("doenca"),
        "pdb": alvo.get("pdb_triagem"),
        "moleculas": (d.get("triagem") or {}).get("moleculas_triadas", 0),
        "auc": enr.get("auc"),
        "veredicto": alvo.get("estado"),
        "encerrado_em": d.get("gerado_em"),
    }


def main():
    apagar = "--apagar" in sys.argv
    so_mostrar = "--so-mostrar" in sys.argv

    r = resumo_atual()
    if r:
        print("campanha atual:")
        for k, v in r.items():
            print(f"  {k}: {v}")
    else:
        print("nao ha campanha atual legivel")

    arquivos_site = [f for f in os.listdir(DADOS)
                     if f.endswith((".json", ".csv"))] if os.path.isdir(DADOS) else []
    n_work = sum(len(fs) for _, _, fs in os.walk(WORK)) if os.path.isdir(WORK) else 0

    print(f"\narquivos de dados do site: {len(arquivos_site)}")
    print(f"arquivos de resultado brutos: {n_work}")
    print(f"modo: {'APAGAR' if apagar else 'arquivar'}")

    if so_mostrar:
        print("\n(--so-mostrar: nada foi alterado)")
        return

    # ---- arquiva ----
    if not apagar:
        marca = (r or {}).get("alvo") or "campanha"
        hoje = datetime.date.today().isoformat()
        destino = os.path.join(ARQUIVO, f"{marca}-{hoje}".replace(" ", "_"))
        os.makedirs(destino, exist_ok=True)
        for f in arquivos_site:
            shutil.copy2(os.path.join(DADOS, f), os.path.join(destino, f))
        if os.path.isdir(WORK):
            alvo_bruto = os.path.join(destino, "bruto")
            if os.path.exists(alvo_bruto):
                shutil.rmtree(alvo_bruto)
            shutil.copytree(WORK, alvo_bruto)
        print(f"\narquivado em: {destino}")

    # ---- zera o site ----
    saida = dict(VAZIO)
    if r:
        saida["historico"] = [r]
        # mantem historico anterior, se houver
        try:
            antigo = json.load(open(os.path.join(DADOS, "dados.json")))
            saida["historico"] = (antigo.get("historico") or []) + [r]
        except Exception:  # noqa: BLE001
            pass

    with open(os.path.join(DADOS, "dados.json"), "w") as fh:
        json.dump(saida, fh, indent=1)
    with open(os.path.join(DADOS, "poses.json"), "w") as fh:
        json.dump({"run": None, "alvo": None, "poses": []}, fh)
    for nome, cab in (("ranking.csv",
                       "rank,compound_id,vina_score_kcal_mol,class,measured_potency_nM"),
                      ("validation.csv",
                       "test,system,rotatable_bonds,affinity_kcal_mol,"
                       "rmsd_top_pose_A,rmsd_best_of_9_A,passed_2A")):
        with open(os.path.join(DADOS, nome), "w", newline="") as fh:
            fh.write(cab + "\n")

    # ---- limpa os brutos ----
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
        os.makedirs(WORK, exist_ok=True)

    print("\nsite zerado. contadores em 0, ranking e poses vazios.")
    if saida["historico"]:
        print(f"historico preservado: {len(saida['historico'])} campanha(s)")
    print("\nfalta agora:")
    print("  1. editar site/alvo.json com o alvo novo")
    print("  2. trocar site/data/receptor.pdb e site/data/site_ref.pdb")
    print("  3. rodar os scripts de validacao do alvo novo")


if __name__ == "__main__":
    main()
