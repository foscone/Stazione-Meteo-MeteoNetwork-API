"""Accesso al database MariaDB. Connessione per-richiesta con cursore a dizionario."""
import os
import pymysql
from pymysql.cursors import DictCursor

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "db"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "meteo"),
    "password": os.environ.get("DB_PASS", ""),
    "database": os.environ.get("DB_NAME", "meteo"),
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
}


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def query(sql, params=None):
    """Esegue una SELECT e restituisce una lista di dizionari."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql, params=None):
    rows = query(sql, params)
    return rows[0] if rows else None
