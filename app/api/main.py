"""API REST della dashboard meteo + serving del frontend statico."""
import os
from pathlib import Path
from datetime import timedelta
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .queries import DAILY_DEDUP, METRICS
from .photos import index_photos

app = FastAPI(title="Meteo Dashboard", version="1.2")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
PHOTOS_DIR = Path(os.environ.get("PHOTOS_DIR", "/app/photos"))


def configured_stations() -> list[str]:
    """Stazioni configurate via env (la prima e' la principale)."""
    raw = os.environ.get("STATION_CODES") or os.environ.get("STATION_CODE", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def station_labels() -> dict[str, str]:
    """Etichette leggibili per stazione, da env STATION_LABELS.

    Formato: 'codice=Etichetta;codice=Etichetta'. Usate per la dashboard
    quando i dati API non bastano a distinguere le stazioni (es. il campo
    'place' vale 'Padova' per piu' stazioni).
    """
    raw = os.environ.get("STATION_LABELS", "")
    labels = {}
    for part in raw.split(";"):
        if "=" in part:
            code, label = part.split("=", 1)
            code, label = code.strip(), label.strip()
            if code and label:
                labels[code] = label
    return labels


def default_station() -> str | None:
    """Stazione di default: la prima configurata, o quella con piu' dati."""
    env = configured_stations()
    if env:
        return env[0]
    row = db.query_one(
        "SELECT station_code FROM daily_rolando "
        "GROUP BY station_code ORDER BY COUNT(*) DESC LIMIT 1"
    )
    return row["station_code"] if row else None


def resolve_station(station: str | None) -> str | None:
    return station or default_station()


@app.get("/api/health")
def health():
    try:
        db.query_one("SELECT 1 AS ok")
        return {"status": "ok"}
    except Exception as e:  # pragma: no cover
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


@app.get("/api/stations")
def stations():
    """Elenco stazioni disponibili: quelle configurate (in ordine) + eventuali
    altre gia' presenti nei dati. Nome ricavato dai dati salvati."""
    rows = db.query(
        """
        SELECT x.station_code AS station_code,
          COALESCE(
            (SELECT d.station_name FROM daily_rolando d
             WHERE d.station_code = x.station_code AND d.station_name IS NOT NULL
             ORDER BY d.id DESC LIMIT 1),
            (SELECT r.place FROM realtime_rolando r
             WHERE r.station_code = x.station_code AND r.place IS NOT NULL
             ORDER BY r.id DESC LIMIT 1)
          ) AS name,
          (SELECT COUNT(*) FROM daily_rolando d2 WHERE d2.station_code = x.station_code) AS daily_count
        FROM (
            SELECT DISTINCT station_code FROM daily_rolando
            UNION
            SELECT DISTINCT station_code FROM realtime_rolando
        ) x
        """
    )
    labels = station_labels()

    def name_for(code, db_name):
        # Priorita': etichetta configurata > nome dai dati > codice
        return labels.get(code) or db_name or code

    by_code = {r["station_code"]: r for r in rows}
    out, seen = [], set()
    # Prima le stazioni configurate, nel loro ordine
    for c in configured_stations():
        r = by_code.get(c)
        out.append({"station_code": c, "name": name_for(c, r["name"] if r else None)})
        seen.add(c)
    # Poi eventuali altre stazioni gia' nei dati
    for r in rows:
        if r["station_code"] not in seen:
            out.append({"station_code": r["station_code"],
                        "name": name_for(r["station_code"], r["name"])})
    return out


@app.get("/api/station")
def station(station: str | None = Query(None)):
    """Metadati della stazione. Usa lo storico daily; se assente (stazione
    senza dati daily) fa fallback all'ultima rilevazione realtime. Il nome
    visualizzato usa l'etichetta configurata, se presente."""
    st = resolve_station(station)
    row = db.query_one(
        f"SELECT station_code, station_name, area, region_name, country, "
        f"latitude, longitude, altitude FROM ({DAILY_DEDUP}) t "
        f"WHERE station_code = %s ORDER BY observation_date DESC LIMIT 1",
        (st,),
    )
    if not row:
        # Nessuno storico daily: ricavo i metadati dal realtime piu' recente.
        row = db.query_one(
            "SELECT station_code, place AS station_name, area, region_name, "
            "country, latitude, longitude, altitude FROM realtime_rolando "
            "WHERE station_code = %s ORDER BY observation_time_local DESC LIMIT 1",
            (st,),
        )
    label = station_labels().get(st)
    if not row:
        return {"station_code": st, "station_name": label or st}
    if label:
        row["station_name"] = label
    return row


@app.get("/api/years")
def years(station: str | None = Query(None)):
    """Anni disponibili nei dati giornalieri della stazione."""
    st = resolve_station(station)
    rows = db.query(
        "SELECT DISTINCT YEAR(observation_date) AS year FROM daily_rolando "
        "WHERE station_code = %s ORDER BY year DESC",
        (st,),
    )
    return [r["year"] for r in rows]


@app.get("/api/latest")
def latest(station: str | None = Query(None)):
    """Ultima rilevazione in tempo reale della stazione."""
    st = resolve_station(station)
    row = db.query_one(
        "SELECT * FROM realtime_rolando WHERE station_code = %s "
        "ORDER BY observation_time_local DESC LIMIT 1",
        (st,),
    )
    if not row:
        raise HTTPException(404, "Nessun dato in tempo reale disponibile")
    return row


@app.get("/api/daily")
def daily(
    station: str | None = Query(None),
    start: str | None = Query(None, description="data inizio YYYY-MM-DD"),
    end: str | None = Query(None, description="data fine YYYY-MM-DD"),
    year: int | None = Query(None),
):
    """Righe giornaliere (deduplicate) per la tabella e i grafici."""
    st = resolve_station(station)
    where, params = ["station_code = %s"], [st]
    if year:
        where.append("YEAR(observation_date) = %s")
        params.append(year)
    if start:
        where.append("observation_date >= %s")
        params.append(start)
    if end:
        where.append("observation_date <= %s")
        params.append(end)
    clause = "WHERE " + " AND ".join(where)
    sql = (
        f"SELECT observation_date, t_min, t_med, t_max, rh_min, rh_med, rh_max, "
        f"slpres, w_med, w_max, w_dir, rain, rad_max, uv_max "
        f"FROM ({DAILY_DEDUP}) t {clause} ORDER BY observation_date ASC"
    )
    return db.query(sql, params)


@app.get("/api/realtime")
def realtime(
    station: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(500, le=5000),
):
    """Rilevazioni in tempo reale in un intervallo (default: ultime 500)."""
    st = resolve_station(station)
    where, params = ["station_code = %s"], [st]
    if start:
        where.append("observation_time_local >= %s")
        params.append(start)
    if end:
        where.append("observation_time_local <= %s")
        params.append(end)
    clause = "WHERE " + " AND ".join(where)
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
    station: str | None = Query(None),
):
    """Serie giornaliere allineate per giorno-dell'anno, una per anno.

    Confronta la stessa metrica della stessa stazione tra annate diverse:
    asse x = MM-DD, ogni anno e' una linea.
    """
    if metric not in METRICS:
        raise HTTPException(400, f"metrica non valida: {metric}")
    col = METRICS[metric]["col"]
    st = resolve_station(station)
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
        f"WHERE station_code = %s AND YEAR(observation_date) IN ({placeholders}) "
        f"ORDER BY observation_date ASC"
    )
    rows = db.query(sql, [st, *year_list])
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
def monthly(metric: str = Query("t_med"), station: str | None = Query(None)):
    """Aggregato mensile per ogni anno (media o somma a seconda della metrica)."""
    if metric not in METRICS:
        raise HTTPException(400, f"metrica non valida: {metric}")
    m = METRICS[metric]
    st = resolve_station(station)
    fn = "SUM" if m["agg"] == "sum" else "AVG"
    sql = (
        f"SELECT YEAR(observation_date) AS year, MONTH(observation_date) AS month, "
        f"ROUND({fn}({m['col']}), 1) AS value "
        f"FROM ({DAILY_DEDUP}) t WHERE station_code = %s "
        f"GROUP BY year, month ORDER BY year, month"
    )
    rows = db.query(sql, (st,))
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


def weather_at(st, hour_dt):
    """Meteo associato a una fascia oraria per la stazione `st`.

    Cerca la rilevazione realtime piu' vicina entro ±2 ore; se non c'e',
    ripiega sul riepilogo giornaliero di quella data.
    """
    mid = hour_dt + timedelta(minutes=30)
    lo = hour_dt - timedelta(hours=2)
    hi = hour_dt + timedelta(hours=3)
    rt = db.query_one(
        "SELECT observation_time_local, temperature, rh, dew_point, smlp, "
        "wind_speed, wind_gust, wind_direction, rain_rate, daily_rain, "
        "ABS(TIMESTAMPDIFF(SECOND, observation_time_local, %s)) AS diff "
        "FROM realtime_rolando "
        "WHERE station_code = %s AND observation_time_local BETWEEN %s AND %s "
        "ORDER BY diff ASC LIMIT 1",
        (mid.strftime("%Y-%m-%d %H:%M:%S"), st,
         lo.strftime("%Y-%m-%d %H:%M:%S"), hi.strftime("%Y-%m-%d %H:%M:%S")),
    )
    if rt:
        rt.pop("diff", None)
        rt["source"] = "realtime"
        return rt

    d = db.query_one(
        f"SELECT observation_date, t_min, t_med, t_max, rh_med, slpres, "
        f"w_med, w_max, w_dir, rain FROM ({DAILY_DEDUP}) t "
        f"WHERE station_code = %s AND observation_date = %s LIMIT 1",
        (st, hour_dt.strftime("%Y-%m-%d")),
    )
    if d:
        d["source"] = "daily"
        return d
    return None


@app.get("/api/photos")
def photos(station: str | None = Query(None)):
    """Foto della cartella montata (e sue sottocartelle), raggruppate prima per
    cartella (il nome è il titolo) e poi per fascia oraria (1 ora), con il meteo
    della stazione selezionata in quel momento."""
    st = resolve_station(station)
    items = index_photos(PHOTOS_DIR)

    # cartella -> ora -> lista foto
    folders: dict = {}
    for it in items:
        hour = it["taken_at"].replace(minute=0, second=0, microsecond=0)
        folders.setdefault(it["folder"], {}).setdefault(hour, []).append(it)

    # sottocartelle in ordine alfabetico, la radice ("") per ultima
    def folder_key(name):
        return (name == "", name.lower())

    groups = []
    for folder in sorted(folders, key=folder_key):
        events = []
        for hour in sorted(folders[folder], reverse=True):  # più recenti per primi
            ph = sorted(folders[folder][hour], key=lambda x: x["taken_at"])
            events.append({
                "hour": hour.strftime("%Y-%m-%dT%H:%M:%S"),
                "photos": [{
                    "file": p["file"],
                    "url": "/photos/" + quote(p["rel"], safe="/"),
                    "taken_at": p["taken_at"].strftime("%Y-%m-%dT%H:%M:%S"),
                    "has_exif": p["has_exif"],
                } for p in ph],
                "weather": weather_at(st, hour),
            })
        groups.append({"folder": folder, "events": events})

    return {"station": st, "count": len(items), "groups": groups}


# File statici: le foto caricate dall'utente e il frontend.
# L'ordine conta: /api/* (sopra) e /photos hanno la precedenza sul catch-all "/".
if PHOTOS_DIR.is_dir():
    app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
