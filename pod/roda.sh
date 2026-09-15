#!/bin/bash
# Supervisor da triagem. Nao para: se algo cair, a volta do laco refaz.
#
# Sem multiprocessing do Python — foi ele que trabalhou em silencio e morreu.
# Aqui cada molecula que termina vira uma linha na hora, pelo doca.sh.
export PATH=/opt/conda/bin:/usr/local/bin:$PATH
cd /work
mkdir -p out ligs
touch out/scores.jsonl
NUC=$(nproc)
PAR=$((NUC - 6)); [ $PAR -lt 1 ] && PAR=1

while true; do
  # --- fila: ligantes preparados que ainda nao tem score ---
  cut -d'"' -f4 out/scores.jsonl 2>/dev/null | sort -u > /tmp/feitos.txt
  ls ligs/*.pdbqt 2>/dev/null | sed 's|.*/||; s|\.pdbqt$||' | sort > /tmp/todos.txt
  comm -23 /tmp/todos.txt /tmp/feitos.txt | sed 's|^|/work/ligs/|; s|$|.pdbqt|' > /tmp/fila.txt
  N=$(wc -l < /tmp/fila.txt)

  # --- pouca fila? prepara mais ligantes antes de docar ---
  if [ "$N" -lt 400 ]; then
    echo "$(date +%H:%M:%S) preparando mais ligantes (fila=$N)" >> out/motor.log
    timeout 900 python /work/prepara.py 800 >> out/prep.log 2>&1
    continue
  fi

  echo "$(date +%H:%M:%S) docando $N ligantes em $PAR nucleos" >> out/motor.log
  xargs -a /tmp/fila.txt -P "$PAR" -n 1 bash /work/doca.sh
done
