"""
Decide o que a placa faz agora. Uma linha na saida, lida pelo ciclo.sh.

  APROVADO|<id>                              -> existe alvo que passou: triar
  VALIDAR|<id>|<pdb>|<chembl>|<organismo>    -> proximo candidato a testar
  FIM                                        -> fila esgotada

A ordem da fila esta em alvos.json e nao muda sozinha. O que decide e o AUC.
"""
import json, os, sys

BASE = "/work"
CORTE = 0.70


def main():
    alvos = json.load(open(BASE + "/alvos.json"))
    pasta = BASE + "/out/alvos"
    os.makedirs(pasta, exist_ok=True)

    for a in alvos:
        caminho = "%s/%s.json" % (pasta, a["id"])
        if not os.path.exists(caminho):
            continue
        try:
            r = json.load(open(caminho))
        except Exception:
            continue
        auc = r.get("auc")
        if auc is not None and auc >= CORTE:
            print("APROVADO|%s" % a["id"])
            return

    for a in alvos:
        if os.path.exists("%s/%s.json" % (pasta, a["id"])):
            continue
        print("VALIDAR|%s|%s|%s|%s" % (a["id"], a["pdb"], a["chembl"], a["organismo"]))
        return

    print("FIM")


if __name__ == "__main__":
    main()
