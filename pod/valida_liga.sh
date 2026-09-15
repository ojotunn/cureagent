#!/bin/bash
# Para a triagem do alvo reprovado e poe a placa na validacao do proximo.
# Nada e apagado: os ligantes do CYP51 ficam guardados.
pkill -f "[r]oda\.sh"      2>/dev/null
pkill -f "[p]repara\.py"   2>/dev/null
pkill -x vina              2>/dev/null
sleep 2
cd /work
[ -d ligs ] && mv ligs ligs_cyp51_$(date +%s) 2>/dev/null
mkdir -p ligs docked out
rm -f docked/*.txt 2>/dev/null
setsid nohup python /work/valida.py \
  "trypanothione reductase Trypanosoma cruzi" \
  "trypanothione reductase" \
  "Trypanosoma cruzi" 60 \
  > /work/out/valida.log 2>&1 < /dev/null &
disown
sleep 5
echo "validador=$(pgrep -f '[v]alida\.py' | wc -l)"
tail -5 /work/out/valida.log
