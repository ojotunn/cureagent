#!/bin/bash
# Escreve o progresso a cada 20s: e o que a tela do site le.
cd /work
mkdir -p out
T0=$(date +%s); N0=$(wc -l < out/scores.jsonl 2>/dev/null || echo 0)
while true; do
  N=$(wc -l < out/scores.jsonl 2>/dev/null || echo 0)
  DT=$(( $(date +%s) - T0 )); [ $DT -lt 1 ] && DT=1
  D=$((N - N0))
  printf '{"triadas":%s,"nesta_sessao":%s,"por_hora":%s,"seg_por_molecula":%s,"nucleos":%s,"receptor":"TcCYP51 3KHM","atualizado":"%s"}\n' \
    "$N" "$D" "$((D * 3600 / DT))" "$(awk -v a=$DT -v b=$D 'BEGIN{printf "%.1f", (b>0? a/b : 0)}')" \
    "$(nproc)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > out/progresso.json
  sleep 20
done
