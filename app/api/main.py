"""API REST della dashboard meteo + serving del frontend statico."""
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .queries import DAILY_DEDUP, METRICS

app = FastAPI(title="Meteo Dashboard", version="1.0")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/api/health")
def health():
    try:
        db.query_one("SELECT 1 AS ok")
        return {"status": "ok"}
    except Exception as e:  # pragma: no cover
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


@app.get("/api/station")
def station():
    """Metadati della stazione (presi dall'ultima rilevazione daily)."""
    row = db.query_one(
        f"SELECT station_code, station_name, area, region_name, country, "
        f"latitude, longitude, altitude FROM ({DAILY_DEDUP}) t "
        f"ORDER BY observation_date DESC LIMIT 1"
    )
    if not row:
        return {"station_code": os.environ.get("STATION_CODE", "")}
    return row


@app.get("/api/years")
def years():
    """Anni disponibili nei dati giornalieri (piu' recenti per primi)."""
    rows = db.query(
        "SELECT DISTINCT YEAR(observation_date) AS year FROM daily_rolando "
        "ORDER BY year DESC"
    )
    return [r["year"] for r in rows]


@app.get("/api/latest")
def latest():
    """Ultima rilevazione in tempo reale (condizioni attuali)."""
    row = db.query_one(
        "SELECT * FROM realtime_rolando ORDER BY observation_time_local DESC LIMIT 1"
    )
    if not row:
        raise HTTPException(404, "Nessun dato in tempo reale disponibile")
    return row


@app.get("/api/daily")
def daily(
    start: str | None = Query(None, description="data inizio YYYY-MM-DD"),
    end: str | None = Query(None, description="data fine YYYY-MM-DD"),
    year: int | None = Query(None),
):
    """Righe giornaliere (deduplicate) per la tabella e i grafici."""
    where, params = [], []
    if year:
        where.append("YEAR(observation_date) = %s")
        params.append(year)
    if start:
        where.append("observation_date >= %s")
        params.append(start)
    if end:
        where.append("observation_date <= %s")
        params.append(end)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = (
        f"SELECT observation_date, t_min, t_med, t_max, rh_min, rh_med, rh_max, "
        f"slpres, w_med, w_max, w_dir, rain, rad_max, uv_max "
        f"FROM ({DAILY_DEDUP}) t {clause} ORDER BY observation_date ASC"
    )
    return db.query(sql, params)


@app.get("/api/realtime")
def realtime(
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(500, le=5000),
):
    """Rilevazioni in tempo reale in un intervallo (default: ultime 500)."""
    where, params = [], []
    if start:
        where.append("observation_time_local >= %s")
        params.append(start)
    if end:
        where.append("observation_time_local <= %s")
        params.append(end)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = (
        f"SELECT observation_time_local, temperature, rh, dew_point, smlp, "
        f"wind_speed, wind_gust, wind_direction, rain_rate, daily_rain "
        f"FROM realtime_rolando {clause} "
        f"ORDER BY observation_time_local DESC LIMIT %s"
    )
    params.append(limit)
    rows = db.query(sql, params)
    rows.reverse()  # ordine cronologico crescente per i grafici
    return rows


@app.get("/api/compare")
def compare(
    metric: str = Query("t_med"),
    years: str = Query(..., description="anni separati da virgola, es. 2025,2026"),
):
    """Serie giornaliere allineate per giorno-dell'anno, una per anno.

    Permette di confrontare la stessa metrica tra annate diverse:
    l'asse x e' MM-DD, ogni anno e' una linea.
    """
    if metric not in METRICS:
        raise HTTPException(400, f"metrica non valida: {metric}")
    col = METRICS[metric]["col"]
    try:
        year_list = [int(y) for y in years.split(",") if y.strip()]
    except ValueError:
        raise HTTPException(400, "parametro years non valido")
    if not year_list:
        raise HTTPException(400, "specificare almeno un anno")

    placeholders = ",".join(["%s"] * len(year_list))
    sql = (
        f"SELECT YEAR(observation_date) AS year, "
        f"DATE_FORMAT(observation_date, '%%m-%%d') AS md, {col} AS value "
        f"FROM ({DAILY_DEDUP}) t "
        f"WHERE YEAR(observation_date) IN ({placeholders}) "
        f"ORDER BY observation_date ASC"
    )
    rows = db.query(sql, year_list)
    series: dict[int, list] = {y: [] for y in year_list}
    for r in rows:
        series[r["year"]].append({"md": r["md"], "value": r["value"]})
    return {
        "metric": metric,
        "label": METRICS[metric]["label"],
        "unit": METRICS[metric]["unit"],
        "series": series,
    }


@app.get("/api/monthly")
def monthly(metric: str = Query("t_med")):
    """Aggregato mensile per ogni anno (media o somma a seconda della metrica).

    Utile per confronti a barre tra annate.
    """
    if metric not in METRICS:
        raise HTTPException(400, f"metrica non valida: {metric}")
    m = METRICS[metric]
    fn = "SUM" if m["agg"] == "sum" else "AVG"
    sql = (
        f"SELECT YEAR(observation_date) AS year, MONTH(observation_date) AS month, "
        f"ROUND({fn}({m['col']}), 1) AS value "
        f"FROM ({DAILY_DEDUP}) t "
        f"GROUP BY year, month ORDER BY year, month"
    )
    rows = db.query(sql)
    out: dict[int, dict] = {}
    for r in rows:
        out.setdefault(r["year"], {})[r["month"]] = r["value"]
    return {
        "metric": metric,
        "label": m["label"],
        "unit": m["unit"],
        "agg": m["agg"],
        "data": out,
    }


@app.get("/api/metrics")
def metrics():
    """Elenco delle metriche selezionabili nei confronti."""
    return [{"key": k, **v} for k, v in METRICS.items()]


# Frontend statico (montato per ultimo cosi' /api/* ha la precedenza)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
