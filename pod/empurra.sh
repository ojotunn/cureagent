#!/bin/bash
# Empurra o estado da placa para o site, a cada 45s.
#
# Sai da placa para o servidor, nunca o contrario: assim nao e preciso abrir
# porta nenhuma no pod nem guardar credencial de git aqui dentro. Se o site
# nao ouvir nada por 6 minutos, ele mesmo passa a dizer que o motor parou —
# e melhor a pagina admitir silencio do que repetir um numero velho.
export PATH=/opt/conda/bin:/usr/local/bin:$PATH
ALVO="${EHRLICH_URL:-https://ehrlich.bio}/api/motor"

if [ -z "$EHRLICH_TOKEN" ]; then
  echo "sem EHRLICH_TOKEN no ambiente — nao ha o que empurrar" >&2
  exit 1
fi

while true; do
  J=$(python /work/reporta.py 2>/dev/null)
  if [ -n "$J" ]; then
    C=$(printf '%s' "$J" | curl -s -o /dev/null -w '%{http_code}' \
          -X POST "$ALVO" \
          -H "Authorization: Bearer $EHRLICH_TOKEN" \
          -H "Content-Type: application/json" \
          --max-time 25 --data-binary @-)
    echo "$(date -u +%H:%M:%S) http=$C $(printf '%s' "$J" | head -c 120)" \
      >> /work/out/empurra.log
  else
    echo "$(date -u +%H:%M:%S) reporta.py nao produziu nada" >> /work/out/empurra.log
  fi
  # o log nao pode crescer para sempre numa placa alugada
  tail -n 400 /work/out/empurra.log > /work/out/empurra.log.tmp 2>/dev/null \
    && mv /work/out/empurra.log.tmp /work/out/empurra.log
  sleep 45
done
