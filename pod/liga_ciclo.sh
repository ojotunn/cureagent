#!/bin/bash
# Sobe o ciclo destacado do SSH, sem encostar no validador que ja roda.
#
# O padrao e ancorado em /work/ciclo.sh porque "[c]iclo.sh" casa dentro do nome
# deste proprio arquivo (liga_ciclo.sh) e o lancador se mataria antes de ligar.
pkill -f "[/]work/ciclo\.sh" 2>/dev/null
sleep 1
mkdir -p /work/out
cd /work
setsid nohup bash -c 'while true; do bash /work/ciclo.sh; sleep 5; done' \
  >> /work/out/ciclo_sup.log 2>&1 < /dev/null &
disown
sleep 3
echo "ciclo=$(pgrep -f '[/]work/ciclo\.sh' | wc -l) validador=$(pgrep -f '[v]alida\.py' | wc -l)"
