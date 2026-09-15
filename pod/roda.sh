#!/bin/bash
# Supervisor da triagem financiada. Nao para: se algo cair, a volta do laco refaz.
#
# So roda em alvo aprovado. O alvo vem de /work/target/alvo.json, escrito pela
# validacao — o motor nao escolhe proteina, o portao de enriquecimento escolhe.
export PATH=/opt/conda/bin:/usr/local/bin:$PATH
cd /work
mkdir -p out ligs
touch out/scores.jsonl
NUC=$(nproc)
PAR=$((NUC - 6)); [ $PAR -lt 1 ] && PAR=1

while true; do
  if [ ! -f /work/target/alvo.json ]; then
    echo "$(date +%H:%M:%S) sem alvo aprovado — esperando" >> out/motor.log
    sleep 60; continue
  fi
  eval "$(python - <<'PY'
import json
a = json.load(open("/work/target/alvo.json"))
print('export REC=%s' % a["receptor"])
for k, v in zip(("CX","CY","CZ"), a["centro"]):  print('export %s=%.3f' % (k, v))
for k, v in zip(("SX","SY","SZ"), a["tamanho"]): print('export %s=%.3f' % (k, v))
PY
)"

  # --- fila: ligantes preparados que ainda nao tem score ---
  cut -d'"' -f4 out/scores.jsonl 2>/dev/null | sort -u > /tmp/feitos.txt
  ls ligs/*.pdbqt 2>/dev/null | sed 's|.*/||; s|\.pdbqt$||' | sort > /tmp/todos.txt
  comm -23 /tmp/todos.txt /tmp/feitos.txt | sed 's|^|/work/ligs/|; s|$|.pdbqt|' > /tmp/fila.txt
  N=$(wc -l < /tmp/fila.txt)

  # --- pouca fila? prepara mais ligantes antes de docar ---
  if [ "$N" -lt 400 ]; then
    echo "$(date +%H:%M:%S) preparando mais ligantes (fila=$N)" >> out/motor.log
    timeout 900 python /work/prepara.py 800 >> out/prep.log 2>&1
    NOVOS=$(ls ligs/*.pdbqt 2>/dev/null | wc -l)
    [ "$NOVOS" -le "$((N + $(wc -l < /tmp/feitos.txt)))" ] && sleep 30
    continue
  fi

  echo "$(date +%H:%M:%S) docando $N ligantes em $PAR nucleos contra $REC" >> out/motor.log
  xargs -a /tmp/fila.txt -P "$PAR" -n 1 bash /work/doca.sh
done
