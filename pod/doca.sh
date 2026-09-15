#!/bin/bash
# Doca UM ligante. A caixa vem do ambiente, exportada uma vez pelo supervisor,
# para nao subir um Python por molecula so para ler o mesmo JSON.
L="$1"
ID=$(basename "$L" .pdbqt)
[ -n "$REC" ] || exit 1
S=$(/work/vina --receptor "$REC" --ligand "$L" \
    --center_x "$CX" --center_y "$CY" --center_z "$CZ" \
    --size_x "$SX" --size_y "$SY" --size_z "$SZ" \
    --exhaustiveness 8 --seed 42 --num_modes 1 --cpu 1 2>/dev/null \
    | awk '$1=="1"{print $2; exit}')
if [ -n "$S" ]; then
  printf '{"id":"%s","score":%s,"t":%s}\n' "$ID" "$S" "$(date +%s)" >> /work/out/scores.jsonl
fi
