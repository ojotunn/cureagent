#!/bin/bash
# O ciclo que nao para.
#
# Enquanto nao houver alvo aprovado, valida o proximo candidato da fila. Quando
# um passar no portao, a triagem financiada assume e nao devolve o controle.
# Nada aqui espera uma pessoa: o site nunca deve mostrar "not running" porque
# alguem foi dormir.
export PATH=/opt/conda/bin:/usr/local/bin:$PATH
cd /work
mkdir -p out out/alvos target prod/ligs docked ligs

reg() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> /work/out/ciclo.log; }

# se ja existe um validador lancado a mao, respeita e espera terminar
# ADOCAO: se um validador foi lancado a mao (foi o caso do primeiro alvo) e
# deixou resultado, esse trabalho entra na fila como resultado do primeiro
# candidato ainda sem veredicto. Sem isto o ciclo recomecaria a mesma
# validacao do zero e jogaria fora horas de placa.
adota() {
  python - <<'PY'
import json, os, shutil
if not os.path.exists("/work/out/resultado.json"):
    raise SystemExit(0)
alvos = json.load(open("/work/alvos.json"))
pasta = "/work/out/alvos"
os.makedirs(pasta, exist_ok=True)
alvo = next((a for a in alvos
             if not os.path.exists(os.path.join(pasta, a["id"] + ".json"))), None)
if alvo is None:
    raise SystemExit(0)
r = json.load(open("/work/out/resultado.json"))
r["id"] = alvo["id"]
json.dump(r, open(os.path.join(pasta, alvo["id"] + ".json"), "w"), indent=1)
if (r.get("auc") or 0) >= 0.70 and os.path.exists("/work/target/alvo.json"):
    shutil.copy("/work/target/alvo.json", "/work/target/aprovado.json")
print("adotado: " + alvo["id"])
PY
}

while pgrep -f "[v]alida\.py" > /dev/null; do sleep 30; done
adota >> /work/out/ciclo.log 2>&1


while true; do
  D=$(python /work/proximo_alvo.py 2>/dev/null)
  ACAO="${D%%|*}"

  case "$ACAO" in
    APROVADO)
      reg "alvo aprovado (${D#*|}) — triagem financiada assume"
      bash /work/roda.sh
      sleep 10
      ;;

    VALIDAR)
      IFS='|' read -r _ ID PDB CHEMBL ORG <<< "$D"
      reg "validando $ID"
      rm -f /work/out/resultado.json
      rm -rf /work/ligs /work/docked
      mkdir -p /work/ligs /work/docked
      python /work/valida.py "$PDB" "$CHEMBL" "$ORG" 60 > /work/out/valida.log 2>&1
      if [ -f /work/out/resultado.json ]; then
        python - "$ID" <<'PY'
import json, shutil, sys
i = sys.argv[1]
r = json.load(open("/work/out/resultado.json"))
r["id"] = i
json.dump(r, open("/work/out/alvos/%s.json" % i, "w"), indent=1)
if (r.get("auc") or 0) >= 0.70:
    shutil.copy("/work/target/alvo.json", "/work/target/aprovado.json")
PY
        reg "fim de $ID"
      else
        # sem resultado = nao deu para montar o teste. Registra e segue, senao
        # o ciclo tentaria o mesmo alvo impossivel para sempre.
        python - "$ID" "$CHEMBL" <<'PY'
import json, sys
json.dump({"id": sys.argv[1], "alvo": sys.argv[2], "auc": None,
           "motivo": "no non-covalent crystal with a drug-like ligand, "
                     "or no measured inhibitors in ChEMBL"},
          open("/work/out/alvos/%s.json" % sys.argv[1], "w"), indent=1)
PY
        reg "$ID sem teste possivel"
      fi
      ;;

    *)
      reg "fila de alvos esgotada"
      sleep 300
      ;;
  esac
done
