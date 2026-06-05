#!/bin/sh
# Avvio del collector: lo scheduler Python interno gestisce gli intervalli e
# resta vivo (niente crash-loop). Vedi collector/scheduler.py.
set -e
cd /app
exec python -m collector.scheduler
