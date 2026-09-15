#!/bin/bash
# Doca UM ligante contra o alvo descrito em /work/target/alvo.json.
# O alvo nao esta escrito aqui de proposito: quem aprova o alvo e a validacao.
L="$1"
ID=$(basename "$L" .pdbqt)
A=/work/target/alvo.json
[ -f "$A" ] || exit 1
read REC CX CY CZ SX SY SZ <<< "$(python - <<'PY'
import json
a = json.load(open("/work/target/alvo.json"))
print(a["receptor"], *["%.3f" % v for v in a["centro"]], *["%.3f" % v for v in a["tamanho"]])
PY
)"
S=$(/work/vina --receptor "$REC" --ligand "$L" \
    --center_x "$CX" --center_y "$CY" --center_z "$CZ" \
    --size_x "$SX" --size_y "$SY" --size_z "$SZ" \
    --exhaustiveness 8 --seed 42 --num_modes 1 --cpu 1 2>/dev/null \
    | awk '$1=="1"{print $2; exit}')
if [ -n "$S" ]; then
  printf '{"id":"%s","score":%s,"t":%s}\n' "$ID" "$S" "$(date +%s)" >> /work/out/scores.jsonl
fi
