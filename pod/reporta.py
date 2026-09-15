"""
Descreve, em JSON, o que a placa esta fazendo agora.

Este e o unico canal entre a placa e o site. Nao inventa nada: todo campo sai
de um arquivo que a propria execucao escreveu, ou de uma contagem de processo.
Se nao da para saber, o campo vem nulo — e a pagina mostra travessao.
"""

import json, os, subprocess, sys, time

BASE = "/work"
CORTE = 0.70

ETAPAS = [
    ("procurando cristal",  "searching for a non-covalent crystal"),
    ("escolhido",           "crystal chosen"),
    ("preparando receptor", "preparing the receptor"),
    ("inibidores medidos",  "collecting measured inhibitors from ChEMBL"),
    ("decoys pareados",     "pairing property-matched decoys"),
    ("gerando 3D",          "generating 3D conformers"),
    ("docking em",          "docking actives against decoys"),
    ("resultado",           "computing enrichment"),
]


def rodando(padrao):
    try:
        r = subprocess.run(["pgrep", "-f", padrao], capture_output=True, text=True)
        return bool(r.stdout.strip())
    except Exception:
        return False


def conta(pasta, sufixo, excluir=None):
    try:
        n = 0
        for f in os.listdir(pasta):
            if not f.endswith(sufixo):
                continue
            if excluir and excluir in f:
                continue
            n += 1
        return n
    except Exception:
        return 0


def linhas(caminho):
    try:
        with open(caminho, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def texto(caminho, cauda=8000):
    try:
        with open(caminho, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - cauda))
            return fh.read().decode("utf-8", "replace").replace("\x00", "")
    except Exception:
        return ""


def etapa_e_cristal(log):
    etapa, cristal = None, None
    for linha in log.splitlines():
        l = linha.strip()
        for chave, txt in ETAPAS:
            if chave in l:
                etapa = txt
        if l.startswith("escolhido "):
            try:
                cristal = l.split()[1].split("/")[0]
            except Exception:
                pass
    return etapa, cristal


def fila(validando=False):
    """A fila de alvos com o veredicto de cada um. E o que prova que isto e um
    processo e nao uma promessa: os reprovados ficam na lista, com o numero."""
    try:
        alvos = json.load(open(BASE + "/alvos.json"))
    except Exception:
        return []
    saida = []
    for a in alvos:
        r = None
        try:
            r = json.load(open("%s/out/alvos/%s.json" % (BASE, a["id"])))
        except Exception:
            pass
        auc = (r or {}).get("auc")
        saida.append({
            "id": a["id"],
            "nome": a["nome"],
            "doenca": a["doenca"],
            "porque": a["porque"],
            "auc": round(auc, 3) if isinstance(auc, (int, float)) else None,
            "estado": ("passed" if isinstance(auc, (int, float)) and auc >= CORTE
                       else "rejected" if r is not None
                       else "queued"),
            "motivo": (r or {}).get("motivo"),
            "pdb": (r or {}).get("pdb"),
        })
    # o primeiro sem veredicto e o que esta na bancada agora
    if validando:
        for a in saida:
            if a["estado"] == "queued":
                a["estado"] = "validating"
                break
    return saida


def main():
    validando = rodando("[v]alida.py")
    triando = rodando("[/]work/roda.sh")
    log = texto(BASE + "/out/valida.log")
    etapa, cristal = etapa_e_cristal(log)
    nucleos = os.cpu_count()

    try:
        aprov = json.load(open(BASE + "/target/aprovado.json"))
    except Exception:
        aprov = None

    d = {
        "nucleos": nucleos,
        "biblioteca": conta(BASE + "/prod/ligs", ".pdbqt", "_out"),
        "fila_alvos": fila(validando),
        "atualizado": time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
    }

    if triando and aprov:
        d.update({
            "estado": "screening",
            "etapa": "screening the funded library",
            "receptor": "PDB %s" % aprov.get("pdb", "—"),
            "alvo": next((f["nome"] for f in d["fila_alvos"] if f["estado"] == "passed"), None),
            "triadas": linhas(BASE + "/out/scores.jsonl"),
            "biblioteca": conta(BASE + "/prod/ligs", ".pdbqt", "_out"),
        })
    elif validando:
        atual = next((f for f in d["fila_alvos"] if f["estado"] == "validating"), None)
        d.update({
            "estado": "validating",
            "etapa": etapa or "starting up",
            "alvo": atual["nome"] if atual else None,
            "alvo_nota": atual["porque"] if atual else None,
            "receptor": ("PDB %s" % cristal) if cristal else "selecting crystal",
            "docadas": conta(BASE + "/docked", ".txt"),
            "total": conta(BASE + "/ligs", ".pdbqt", "_out"),
            "auc": None,
            "corte": CORTE,
        })
    else:
        d.update({"estado": "idle", "etapa": "between targets"})

    json.dump(d, sys.stdout)


if __name__ == "__main__":
    main()
