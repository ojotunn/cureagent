"""
Exporta as POSES REAIS do docking para a tela reproduzir.

Cada arquivo de saida do Vina guarda onde a molecula foi parar dentro do
sitio. Sao coordenadas de verdade, do run que aconteceu — nada de animacao
inventada. A tela reproduz isso em sequencia.

Formato enxuto: elementos numa string, coordenadas num array achatado com
1 casa decimal (0,1 A e mais fino que a espessura do traco na tela).
"""

import json
import os

BASE = r"C:\Higgsfield Games\keys"
DOCK = os.path.join(BASE, "results", "frente_a", "enriquecimento", "docked")
ENR = os.path.join(BASE, "results", "frente_a", "enriquecimento")
DADOS = os.path.join(BASE, "site", "data")

# tipo de atomo do AutoDock -> elemento quimico
TIPOS = {
    "C": "C", "A": "C", "N": "N", "NA": "N", "NS": "N",
    "O": "O", "OA": "O", "OS": "O", "S": "S", "SA": "S",
    "F": "F", "Cl": "Cl", "CL": "Cl", "Br": "Br", "BR": "Br",
    "I": "I", "P": "P", "Si": "Si", "B": "B",
    "Fe": "Fe", "Zn": "Zn", "Mg": "Mg", "Ca": "Ca", "Mn": "Mn",
}


def primeira_pose(caminho):
    """So o MODEL 1: e a pose que o Vina ranqueou em primeiro."""
    els, xyz = [], []
    dentro = False
    with open(caminho) as fh:
        for ln in fh:
            if ln.startswith("MODEL"):
                if dentro:
                    break
                dentro = True
                continue
            if ln.startswith("ENDMDL"):
                break
            if not ln.startswith(("ATOM", "HETATM")):
                continue
            tipo = ln[77:79].strip()
            el = TIPOS.get(tipo)
            if el is None:          # HD, H e o que nao reconhecemos ficam de fora
                continue
            els.append(el)
            xyz.extend([round(float(ln[30:38]), 1),
                        round(float(ln[38:46]), 1),
                        round(float(ln[46:54]), 1)])
    return els, xyz


def main():
    conjunto = json.load(open(os.path.join(ENR, "conjunto.json")))
    rotulo = {a["chembl_id"]: (1, a.get("nM")) for a in conjunto["ativos"]}
    rotulo.update({d["chembl_id"]: (0, None) for d in conjunto["decoys"]})

    poses = []
    sem_score = falhou = 0
    for arq in sorted(os.listdir(DOCK)):
        if not arq.endswith(".pdbqt"):
            continue
        nome = arq[:-6]
        partes = nome.split("_", 1)
        if len(partes) != 2:
            continue
        cid = partes[1]
        if cid not in rotulo:
            continue
        try:
            score = float(open(os.path.join(DOCK, nome + ".txt")).read().strip())
        except (ValueError, TypeError, FileNotFoundError):
            sem_score += 1
            continue
        els, xyz = primeira_pose(os.path.join(DOCK, arq))
        if not els:
            falhou += 1
            continue
        ativo, nM = rotulo[cid]
        poses.append({"id": cid, "s": round(score, 2), "a": ativo,
                      "el": ",".join(els), "xyz": xyz,
                      **({"nM": round(nM, 1)} if nM else {})})

    poses.sort(key=lambda p: p["s"])          # melhor score primeiro

    saida = {
        "run": "2026-09-14",
        "alvo": "1AIM",
        "nota": "Real docked poses from the run of 2026-09-14. Coordinates are "
                "as the docking produced them; nothing here is simulated for "
                "display.",
        "poses": poses,
    }
    destino = os.path.join(DADOS, "poses.json")
    with open(destino, "w") as fh:
        json.dump(saida, fh, separators=(",", ":"))

    tam = os.path.getsize(destino) / 1024
    atomos = sum(len(p["el"].split(",")) for p in poses)
    print(f"poses exportadas: {len(poses)}")
    print(f"atomos totais: {atomos}  (media {atomos/max(1,len(poses)):.0f} por molecula)")
    print(f"sem score: {sem_score}   sem atomos: {falhou}")
    print(f"arquivo: {tam:.0f} KB")


if __name__ == "__main__":
    main()
