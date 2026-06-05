"""Recupero dati dalla stazione MeteoNetwork e salvataggio nel database.

Uso:
    python -m collector.fetch realtime
    python -m collector.fetch daily

Invocato a intervalli regolari da supercronic (vedi collector/crontab).
"""
import os
import sys
import time
import logging

import requests

from api.db import get_connection
from collector import meteonetwork

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("collector")


def station_codes():
    """Elenco delle stazioni da monitorare (env STATION_CODES, fallback STATION_CODE)."""
    raw = os.environ.get("STATION_CODES") or os.environ.get("STATION_CODE", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


# Pausa tra una stazione e l'altra per rispettare i rate limit dell'API.
INTER_STATION_DELAY = float(os.environ.get("INTER_STATION_DELAY", "3"))


def _f(v):
    """float o None."""
    return None if v in (None, "") else float(v)


def _i(v):
    """int o None."""
    return None if v in (None, "") else int(float(v))


def save_realtime(station_code):
    data = meteonetwork.data_realtime(station_code)
    sql = """
        INSERT INTO realtime_rolando (
            observation_time_local, observation_time_utc, station_code, place, area,
            latitude, longitude, altitude, country, region_name, temperature, smlp, rh,
            wind_speed, wind_direction, wind_direction_degree, wind_gust, rain_rate,
            daily_rain, dew_point, name
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    values = (
        data.get("observation_time_local"), data.get("observation_time_utc"),
        data.get("station_code"), data.get("place"), data.get("area"),
        _f(data.get("latitude")), _f(data.get("longitude")), _i(data.get("altitude")),
        data.get("country"), data.get("region_name"), _f(data.get("temperature")),
        _f(data.get("smlp")), _f(data.get("rh")), _f(data.get("wind_speed")),
        data.get("wind_direction"), _i(data.get("wind_direction_degree")),
        _f(data.get("wind_gust")), _f(data.get("rain_rate")), _f(data.get("daily_rain")),
        _f(data.get("dew_point")), data.get("name"),
    )
    _insert(sql, values, f"realtime/{station_code}")


def save_daily(station_code):
    data = meteonetwork.data_daily(station_code)
    obs_date = data.get("observation_date")

    # Evita duplicati: salta se la giornata e' gia' stata salvata.
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM daily_rolando WHERE observation_date=%s AND station_code=%s LIMIT 1",
                (obs_date, data.get("station_code")),
            )
            if cur.fetchone():
                log.info("Dati daily del %s gia' presenti, salto.", obs_date)
                return
    finally:
        conn.close()

    sql = """
        INSERT INTO daily_rolando (
            observation_date, station_code, station_name, area, latitude, longitude,
            altitude, country, region_name, t_min, t_med, t_max, rh_min, rh_med, rh_max,
            slpres, w_max, w_med, w_dir, rain, rad_med, rad_max, uv_med, uv_max
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    values = (
        obs_date, data.get("station_code"), data.get("station_name"), data.get("area"),
        _f(data.get("latitude")), _f(data.get("longitude")), _i(data.get("altitude")),
        data.get("country"), data.get("region_name"), _f(data.get("t_min")),
        _f(data.get("t_med")), _f(data.get("t_max")), _i(data.get("rh_min")),
        _i(data.get("rh_med")), _i(data.get("rh_max")), _f(data.get("slpres")),
        _f(data.get("w_max")), _f(data.get("w_med")), data.get("w_dir"),
        _f(data.get("rain")), _f(data.get("rad_med")), _f(data.get("rad_max")),
        _f(data.get("uv_med")), _f(data.get("uv_max")),
    )
    _insert(sql, values, f"daily/{station_code}")


def _insert(sql, values, kind):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
        conn.commit()
        log.info("Dati %s salvati con successo.", kind)
    except Exception:
        conn.rollback()
        log.exception("Errore nel salvataggio dei dati %s", kind)
        raise
    finally:
        conn.close()


def run(kind):
    """Recupera `kind` ('realtime'|'daily') per tutte le stazioni configurate.

    Ogni stazione e' indipendente: un errore (incluso un rate limit 429) su una
    non blocca le altre e non interrompe lo scheduler. Restituisce il numero di
    stazioni fallite.
    """
    codes = station_codes()
    if not codes:
        log.error("Nessuna stazione configurata (STATION_CODES)")
        return 1

    save = save_realtime if kind == "realtime" else save_daily
    failures = 0
    for i, code in enumerate(codes):
        if i:
            time.sleep(INTER_STATION_DELAY)
        try:
            save(code)
        except requests.HTTPError as e:
            failures += 1
            # 429/4xx/5xx: log conciso, niente traceback (rumore inutile)
            log.warning("Fetch %s %s non riuscito: %s", kind, code, e)
        except Exception:
            failures += 1
            log.exception("Fetch %s fallito per la stazione %s", kind, code)
    return failures


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("realtime", "daily"):
        print("Uso: python -m collector.fetch [realtime|daily]", file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if run(sys.argv[1]) else 0)


if __name__ == "__main__":
    main()
