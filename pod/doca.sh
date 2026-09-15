#!/bin/bash
# Doca UM ligante e grava o score na hora.
# Uma linha curta com >> e append atomico: varios processos podem escrever juntos.
L="$1"
ID=$(basename "$L" .pdbqt)
S=$(/work/vina --receptor /work/target/receptor.pdbqt --ligand "$L" \
    --center_x 2.49 --center_y -24.48 --center_z 18.32 \
    --size_x 22 --size_y 22 --size_z 22 \
    --exhaustiveness 8 --seed 42 --num_modes 1 --cpu 1 2>/dev/null \
    | awk '$1=="1"{print $2; exit}')
if [ -n "$S" ]; then
  printf '{"id":"%s","score":%s,"t":%s}\n' "$ID" "$S" "$(date +%s)" >> /work/out/scores.jsonl
fi
