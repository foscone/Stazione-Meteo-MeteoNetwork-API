"""Client per le API MeteoNetwork (https://api.meteonetwork.it/v3).

Gestisce il token Bearer: lo legge da un file di stato persistente, lo usa
finche' valido e lo rigenera automaticamente via login quando scade (401).
"""
import os
import json
import logging
from pathlib import Path

import requests

log = logging.getLogger("meteonetwork")

BASE_URL = "https://api.meteonetwork.it/v3"
STATE_DIR = Path(os.environ.get("STATE_DIR", "/state"))
TOKEN_FILE = STATE_DIR / "token.txt"

MAIL = os.environ.get("METEONETWORK_MAIL", "")
PASSWORD = os.environ.get("METEONETWORK_PASSWORD", "")


def _load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return os.environ.get("METEONETWORK_TOKEN", "").strip()


def _save_token(token: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)


def login() -> str:
    """Effettua il login e restituisce un nuovo access token."""
    log.info("Login MeteoNetwork per rinnovare il token...")
    resp = requests.post(
        f"{BASE_URL}/login",
        files={"email": (None, MAIL), "password": (None, PASSWORD)},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Login senza access_token: {resp.text[:200]}")
    _save_token(token)
    log.info("Token aggiornato con successo.")
    return token


def _get(path: str, params: dict | None = None) -> list | dict:
    """GET autenticata con retry automatico dopo refresh del token su 401."""
    token = _load_token()
    for attempt in range(2):
        resp = requests.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=30,
        )
        if resp.status_code == 401 and attempt == 0:
            log.warning("Token scaduto (401), rigenero...")
            token = login()
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Autenticazione fallita dopo il refresh del token")


def data_realtime(station_code: str) -> dict:
    data = _get(f"/data-realtime/{station_code}")
    return data[0] if isinstance(data, list) else data


def data_daily(station_code: str, observation_date: str | None = None) -> dict | None:
    """Dati giornalieri della stazione. Se `observation_date` (YYYY-MM-DD) e'
    fornita, restituisce il giorno richiesto (per il backfill storico); altrimenti
    l'ultimo disponibile. Ritorna None se per quella data non ci sono dati."""
    params = {"observation_date": observation_date} if observation_date else None
    data = _get(f"/data-daily/{station_code}", params=params)
    if isinstance(data, list):
        return data[0] if data else None
    return data or None
