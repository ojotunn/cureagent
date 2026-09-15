#!/bin/bash
# Triagem financiada. So roda em alvo APROVADO, e usa a biblioteca de producao,
# separada da de validacao — misturar as duas corromperia o AUC.
export PATH=/opt/conda/bin:/usr/local/bin:$PATH
cd /work
mkdir -p out prod/ligs poses
touch out/scores.jsonl
NUC=$(nproc)
PAR=$((NUC - 4)); [ $PAR -lt 1 ] && PAR=1

while true; do
  if [ ! -f /work/target/aprovado.json ]; then
    echo "$(date -u +%H:%M:%S) sem alvo aprovado — esperando" >> out/motor.log
    sleep 60; continue
  fi

  eval "$(python - <<'PY'
import json
a = json.load(open("/work/target/aprovado.json"))
print('export REC=%s' % a["receptor"])
for k, v in zip(("CX","CY","CZ"), a["centro"]):  print('export %s=%.3f' % (k, v))
for k, v in zip(("SX","SY","SZ"), a["tamanho"]): print('export %s=%.3f' % (k, v))
PY
)"

  cut -d'"' -f4 out/scores.jsonl 2>/dev/null | sort -u > /tmp/feitos.txt
  # o grep tira as POSES que o Vina possa ter deixado ao lado dos ligantes
  ls prod/ligs/*.pdbqt 2>/dev/null | grep -v '_out\.pdbqt$' \
    | sed 's|.*/||; s|\.pdbqt$||' | sort > /tmp/todos.txt
  comm -23 /tmp/todos.txt /tmp/feitos.txt | sed 's|^|/work/prod/ligs/|; s|$|.pdbqt|' > /tmp/fila.txt
  N=$(wc -l < /tmp/fila.txt)

  if [ "$N" -lt 400 ]; then
    ANTES=$(ls prod/ligs/*.pdbqt 2>/dev/null | wc -l)
    echo "$(date -u +%H:%M:%S) preparando ligantes (fila=$N)" >> out/motor.log
    timeout 900 python /work/prepara.py 800 /work/prod/ligs >> out/prep.log 2>&1
    DEPOIS=$(ls prod/ligs/*.pdbqt 2>/dev/null | wc -l)
    if [ "$DEPOIS" -le "$ANTES" ]; then
      echo "$(date -u +%H:%M:%S) biblioteca esgotada em $DEPOIS ligantes" >> out/motor.log
      sleep 120
    fi
    continue
  fi

  echo "$(date -u +%H:%M:%S) docando $N em $PAR nucleos contra $REC" >> out/motor.log
  xargs -a /tmp/fila.txt -P "$PAR" -n 1 bash /work/doca.sh
done
