#!/bin/sh
# Avvio del collector: genera la crontab dalle variabili d'ambiente e
# lancia supercronic, che esegue i fetch a intervalli regolari loggando su stdout.
set -e

cd /app

CRON_REALTIME="${CRON_REALTIME:-*/15 * * * *}"
CRON_DAILY="${CRON_DAILY:-0 9 * * *}"
CRONTAB_FILE=/state/crontab

mkdir -p /state

cat > "$CRONTAB_FILE" <<EOF
# Generato automaticamente da entrypoint.sh - non modificare a mano
$CRON_REALTIME cd /app && python -m collector.fetch realtime
$CRON_DAILY cd /app && python -m collector.fetch daily
EOF

echo "[collector] Crontab attiva:"
cat "$CRONTAB_FILE"

# Primo recupero realtime all'avvio, cosi' la dashboard ha subito un dato fresco.
echo "[collector] Recupero realtime iniziale..."
python -m collector.fetch realtime || echo "[collector] fetch iniziale fallito (riprovo allo scadere del cron)"

exec supercronic "$CRONTAB_FILE"
