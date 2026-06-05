"""Query SQL e registro delle metriche per la dashboard."""

# Nel dump possono esistere piu' record per la stessa data: teniamo solo
# l'ultimo inserito per ogni (stazione, observation_date).
DAILY_DEDUP = """
    SELECT d.* FROM daily_rolando d
    JOIN (
        SELECT station_code, observation_date, MAX(id) AS mid
        FROM daily_rolando
        GROUP BY station_code, observation_date
    ) last ON d.id = last.mid
"""

# Metriche giornaliere disponibili: etichetta, colonna, unita', aggregazione
# usata per i riepiloghi mensili (avg = media, sum = somma cumulata).
METRICS = {
    "t_min":  {"label": "Temp. minima",  "col": "t_min",  "unit": "°C",  "agg": "avg"},
    "t_med":  {"label": "Temp. media",   "col": "t_med",  "unit": "°C",  "agg": "avg"},
    "t_max":  {"label": "Temp. massima", "col": "t_max",  "unit": "°C",  "agg": "avg"},
    "rain":   {"label": "Pioggia",       "col": "rain",   "unit": "mm",  "agg": "sum"},
    "rh_med": {"label": "Umidità media", "col": "rh_med", "unit": "%",   "agg": "avg"},
    "slpres": {"label": "Pressione",     "col": "slpres", "unit": "hPa", "agg": "avg"},
    "w_med":  {"label": "Vento medio",   "col": "w_med",  "unit": "km/h","agg": "avg"},
    "w_max":  {"label": "Raffica max",   "col": "w_max",  "unit": "km/h","agg": "avg"},
}
