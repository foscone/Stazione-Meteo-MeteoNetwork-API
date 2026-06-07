"""Backfill dei dati giornalieri storici.

Recupera dall'API MeteoNetwork i daily passati (un giorno per richiesta, via
?observation_date=YYYY-MM-DD) e li salva nel DB. Pensato per popolare lo storico
delle stazioni che non erano nel backup (es. Palestro, Montà).

L'API ha un throttling di 5 richieste/minuto sul daily: di default attendiamo
14 secondi tra una richiesta e l'altra. Lo script e':
- idempotente/ripartibile: i giorni gia' presenti vengono saltati senza chiamare l'API;
- resistente ai 429: in caso di rate limit attende e riprova.

Uso (dentro il container collector):
    python -m collector.backfill --start 2025-02-10
    python -m collector.backfill --stations codice_stazione_1,codice_stazione_2 --start 2024-01-01 --end 2025-12-31
"""
import os
import sys
import time
import logging
import argparse
from datetime import date, timedelta

import requests

from collector import fetch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("backfill")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main():
    ap = argparse.ArgumentParser(description="Backfill daily storici MeteoNetwork")
    ap.add_argument("--stations", help="codici separati da virgola (default: STATION_CODES)")
    ap.add_argument("--start", required=True, help="data inizio YYYY-MM-DD")
    ap.add_argument("--end", help="data fine YYYY-MM-DD (default: ieri)")
    ap.add_argument("--delay", type=float, default=14.0,
                    help="secondi tra le richieste API (default 14, throttle 5/min)")
    args = ap.parse_args()

    stations = ([s.strip() for s in args.stations.split(",") if s.strip()]
                if args.stations else fetch.station_codes())
    if not stations:
        log.error("Nessuna stazione specificata")
        sys.exit(1)

    start = parse_date(args.start)
    end = parse_date(args.end) if args.end else date.today() - timedelta(days=1)
    if end < start:
        log.error("La data fine precede la data inizio")
        sys.exit(1)

    days = list(daterange(start, end))
    log.info("Backfill di %d stazioni x %d giorni (%s -> %s), delay %.0fs",
             len(stations), len(days), start, end, args.delay)

    saved = skipped = empty = errors = 0
    for code in stations:
        log.info("=== Stazione %s ===", code)
        for d in days:
            iso = d.isoformat()
            try:
                status = _save_with_retry(code, iso, args.delay)
            except Exception:
                errors += 1
                log.exception("Errore irreversibile su %s %s", code, iso)
                continue

            if status == "saved":
                saved += 1
                time.sleep(args.delay)  # throttle solo dopo una vera chiamata API
            elif status == "empty":
                empty += 1
                time.sleep(args.delay)  # anche "nessun dato" e' una chiamata API
            else:  # skipped: nessuna chiamata API, nessuna pausa
                skipped += 1

    log.info("Backfill completato: %d salvati, %d gia' presenti, %d senza dati, %d errori",
             saved, skipped, empty, errors)


def _save_with_retry(code, iso, delay, max_retries=5):
    """Salva un giorno, gestendo i 429 con attesa progressiva."""
    for attempt in range(max_retries):
        try:
            return fetch.save_daily(code, iso)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 429:
                wait = max(delay, 60) * (attempt + 1)
                log.warning("429 su %s %s: attendo %.0fs (tentativo %d/%d)",
                            code, iso, wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            log.warning("HTTP %s su %s %s: salto", status, code, iso)
            return "empty"
    log.error("Troppi 429 su %s %s, salto", code, iso)
    return "empty"


if __name__ == "__main__":
    main()
