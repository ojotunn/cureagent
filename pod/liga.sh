#!/bin/bash
# Liga o motor destacado do SSH. Os colchetes no padrao evitam que o pkill
# case com a propria linha de comando e mate quem esta lancando.
pkill -f "[r]oda\.sh"     2>/dev/null
pkill -f "[p]rogresso\.sh" 2>/dev/null
pkill -f "[m]otor\.py"     2>/dev/null
pkill -x vina              2>/dev/null
sleep 2
mkdir -p /work/out
cd /work
setsid nohup bash -c 'while true; do bash /work/roda.sh; sleep 5; done' \
  >> /work/out/sup.log 2>&1 < /dev/null &
disown
setsid nohup bash /work/progresso.sh >> /work/out/prog.log 2>&1 < /dev/null &
disown
sleep 3
echo "supervisor=$(pgrep -f '[r]oda\.sh' | wc -l) progresso=$(pgrep -f '[p]rogresso\.sh' | wc -l)"
