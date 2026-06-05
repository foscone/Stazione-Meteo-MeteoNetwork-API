"""Scheduler interno del collector.

Sostituisce un cron esterno: e' un singolo processo che resta vivo e lancia i
fetch a intervalli regolari. Vantaggi rispetto a un cron in container:
- nessun crash-loop: un errore in un tick non termina il processo, quindi un
  eventuale rate limit (429) viene semplicemente saltato fino al tick successivo;
- intervalli allineati all'orologio (es. :00/:15/:30/:45).

Configurazione (env):
  REALTIME_INTERVAL_MIN  ogni quanti minuti recuperare il realtime (default 15)
  DAILY_HOUR             ora a cui recuperare il daily, una volta al giorno (default 9)
  RUN_AT_START          se "true", esegue un primo realtime all'avvio (default true)
"""
import os
import time
import signal
import logging
from datetime import datetime, timedelta

from collector import fetch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("scheduler")

REALTIME_INTERVAL_MIN = int(os.environ.get("REALTIME_INTERVAL_MIN", "15"))
DAILY_HOUR = int(os.environ.get("DAILY_HOUR", "9"))
RUN_AT_START = os.environ.get("RUN_AT_START", "true").lower() in ("1", "true", "yes")

_stop = False


def _handle_signal(signum, frame):
    global _stop
    _stop = True
    log.info("Ricevuto segnale %s, arresto in corso...", signum)


def next_tick(now, minutes):
    """Prossimo istante 'tondo' multiplo di `minutes` (secondo 0)."""
    base = now.replace(second=0, microsecond=0)
    step = minutes - (base.minute % minutes)
    return base + timedelta(minutes=step)


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log.info(
        "Scheduler avviato: realtime ogni %d min, daily alle %02d:00, stazioni=%s",
        REALTIME_INTERVAL_MIN, DAILY_HOUR, ",".join(fetch.station_codes()) or "(nessuna)",
    )

    last_daily = None

    if RUN_AT_START:
        log.info("Recupero realtime iniziale...")
        fetch.run("realtime")

    while not _stop:
        target = next_tick(datetime.now(), REALTIME_INTERVAL_MIN)
        # Dorme fino al prossimo tick, ma si risveglia per controllare _stop.
        while not _stop:
            remaining = (target - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 30))
        if _stop:
            break

        now = datetime.now()

        # Daily una sola volta al giorno, al primo tick a partire da DAILY_HOUR.
        if now.hour >= DAILY_HOUR and last_daily != now.date():
            log.info("Recupero daily...")
            if fetch.run("daily") == 0:
                last_daily = now.date()

        log.info("Recupero realtime...")
        fetch.run("realtime")

    log.info("Scheduler terminato.")


if __name__ == "__main__":
    main()
