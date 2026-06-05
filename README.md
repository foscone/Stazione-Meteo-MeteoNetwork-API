# Meteo Dashboard

Dashboard meteo per **più stazioni** MeteoNetwork: visualizza i dati storici e
in tempo reale in forma tabellare e con grafici, permette di **confrontare le
annate** tra loro e di passare da una stazione all'altra con un selettore.

Stazioni monitorate di default (configurabili in `.env`):

| Codice   | Stazione                  |
|----------|---------------------------|
| `STAZIONE1` | Padova - Centro           |
| `STAZIONE2` | Palestro - Montecengio    |
| `STAZIONE3` | Padova - Montà            |

Lo storico nel backup riguarda solo `STAZIONE1`; per le altre stazioni i dati
vengono raccolti dal collector a partire dal primo avvio.

Il progetto è completamente dockerizzato e composto da tre servizi:

| Servizio    | Ruolo                                                                 |
|-------------|-----------------------------------------------------------------------|
| `db`        | MariaDB 10.5 con lo storico ripristinato dal backup                   |
| `web`       | API REST (FastAPI) + dashboard web statica                            |
| `collector` | Recupera in automatico i nuovi dati dalle API MeteoNetwork via cron   |

## Avvio rapido

```bash
# 1. Configura i segreti
cp .env.example .env        # poi modifica i valori in .env

# 2. (Opzionale) Ripristina lo storico dal backup
#    Copia il dump SQL del backup del database in db/init/02-data.sql
#    Viene caricato automaticamente SOLO al primo avvio (volume vuoto).
cp backup/meteo-*.sql db/init/02-data.sql

# 3. Avvia tutto
docker compose up -d --build
```

La dashboard è poi raggiungibile su **http://localhost:8080** (porta
configurabile con `WEB_PORT`).

## Ripristino dei dati storici

Il backup del backup del database (cartella `backup/`, ignorata da git)
contiene un dump MariaDB con le tabelle `daily_rolando` e `realtime_rolando`.

- Lo **schema** è versionato in [db/init/01-schema.sql](db/init/01-schema.sql)
  e crea le tabelle vuote: il progetto parte funzionante anche senza backup.
- I **dati** vanno copiati in `db/init/02-data.sql` (file gitignored). All'avvio
  iniziale del container `db` (volume `db_data` vuoto) tutti i file in
  `db/init/` vengono eseguiti in ordine alfabetico: prima lo schema, poi i dati.

> Per ricaricare il dump dopo il primo avvio, azzera il volume:
> `docker compose down -v && docker compose up -d --build`

## Recupero automatico dei nuovi dati

Il servizio `collector` esegue uno **scheduler Python interno**
([scheduler.py](app/collector/scheduler.py)): un singolo processo che resta vivo
e lancia i fetch a intervalli regolari (niente cron esterno, niente crash-loop —
un eventuale rate limit viene saltato fino al tick successivo invece di far
ripartire il container).

- **realtime** ogni `REALTIME_INTERVAL_MIN` minuti → tabella `realtime_rolando`
- **daily** una volta al giorno a partire da `DAILY_HOUR` → tabella `daily_rolando`

Ad ogni esecuzione il collector cicla su **tutte le stazioni** indicate in
`STATION_CODES` (con una breve pausa tra una e l'altra per rispettare i rate
limit). I dati sono presi dalle API MeteoNetwork (`/v3/data-realtime` e
`/v3/data-daily`); ogni record è distinto dalla colonna `station_code`.
Il **token Bearer** viene letto da `.env`, salvato nel volume `collector_state`
e **rigenerato automaticamente** con login email/password quando scade (HTTP 401).

Pianificazione e stazioni si configurano da `.env`:

```
STATION_CODES=STAZIONE1,STAZIONE2,STAZIONE3
REALTIME_INTERVAL_MIN=15
DAILY_HOUR=9
RUN_AT_START=true
```

## API REST

Tutti gli endpoint dei dati accettano il parametro opzionale `station=<codice>`
(default: la prima stazione configurata).

| Endpoint                                   | Descrizione                                  |
|--------------------------------------------|----------------------------------------------|
| `GET /api/stations`                        | Elenco stazioni disponibili (per il selettore)|
| `GET /api/station`                         | Metadati della stazione                      |
| `GET /api/years`                           | Anni disponibili                             |
| `GET /api/latest`                          | Ultima rilevazione in tempo reale            |
| `GET /api/daily?year=&start=&end=`         | Dati giornalieri (tabella/grafici)           |
| `GET /api/realtime?limit=&start=&end=`     | Rilevazioni in tempo reale                   |
| `GET /api/compare?metric=&years=2025,2026` | Confronto annate per giorno dell'anno        |
| `GET /api/monthly?metric=`                 | Aggregati mensili per anno                   |
| `GET /api/metrics`                         | Metriche disponibili per i confronti         |

## Dashboard

In alto un **selettore stazione** cambia la stazione su tutte le sezioni.
Quattro sezioni:

1. **Andamento giornaliero** — temperature (min/med/max) e pioggia per anno.
2. **Confronto annate** — stessa metrica sovrapposta per giorno dell'anno + barre mensili.
3. **Tempo reale** — temperatura, umidità e vento delle ultime rilevazioni.
4. **Tabella dati** — dati giornalieri in forma tabellare.

## Sicurezza / git

- `.env` e l'intera cartella `backup/` sono in [.gitignore](.gitignore).
- Il dump dei dati (`db/init/02-data.sql`) **non** viene versionato.
- In repo c'è solo `.env.example` con placeholder.
