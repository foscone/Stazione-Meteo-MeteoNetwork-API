# Meteo Dashboard

> Dashboard Docker che raccoglie in automatico i dati di una o più stazioni
> [MeteoNetwork](https://www.meteonetwork.it) (storico + tempo reale) e li
> mostra in tabelle e grafici, con confronto tra annate.

Dashboard meteo per **più stazioni** MeteoNetwork: visualizza i dati storici e
in tempo reale in forma tabellare e con grafici, permette di **confrontare le
annate** tra loro e di passare da una stazione all'altra con un selettore.

Le stazioni da monitorare si configurano in `.env` tramite i loro codici
MeteoNetwork (vedi `STATION_CODES`). Lo storico iniziale può essere ripristinato
da un dump del database; le nuove rilevazioni vengono poi raccolte in automatico
dal collector.

Il progetto è completamente dockerizzato e composto da tre servizi:

| Servizio    | Ruolo                                                                 |
|-------------|-----------------------------------------------------------------------|
| `db`        | MariaDB 10.5 con lo storico ripristinato dal backup                   |
| `web`       | API REST (FastAPI) + dashboard web statica                            |
| `collector` | Recupera in automatico i nuovi dati dalle API MeteoNetwork            |

## Avvio rapido

```bash
# 1. Configura i segreti
cp .env.example .env        # poi modifica i valori in .env

# 2. (Opzionale) Ripristina lo storico da un dump del database
#    Copia il tuo dump SQL in db/init/02-data.sql
#    Viene caricato automaticamente SOLO al primo avvio (volume vuoto).

# 3. Avvia tutto
docker compose up -d --build
```

La dashboard è poi raggiungibile su **http://localhost:8080** (porta
configurabile con `WEB_PORT`).

## Ripristino dei dati storici

Un dump MariaDB con le tabelle `daily_rolando` e `realtime_rolando` può essere
usato per ripristinare lo storico.

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

### Etichette stazioni

Il campo `place` dell'API può essere uguale per più stazioni. Per distinguerle in
dashboard si usano etichette da `STATION_LABELS` (`codice=Etichetta` separati da
`;`):

```
STATION_LABELS=codice_stazione_1=La mia stazione;codice_stazione_2=Altra stazione
```

### Backfill dello storico giornaliero

Per le stazioni non presenti nel backup si può recuperare lo **storico daily**
dall'API (un giorno per richiesta, `?observation_date=`).
Lo **storico realtime non è recuperabile**: l'API espone solo l'istante corrente.

L'endpoint daily ha un throttling di **5 richieste/minuto**, quindi il backfill è
lento (~14s a richiesta). Lo script è idempotente e ripartibile (salta i giorni
già presenti) e gestisce i 429 con attese progressive:

```bash
# tutte le stazioni configurate, dal 10/02/2025 a ieri
docker compose exec collector python -m collector.backfill --start 2025-02-10

# solo alcune stazioni, intervallo specifico
docker compose exec collector python -m collector.backfill \
    --stations codice_stazione_1,codice_stazione_2 --start 2024-01-01 --end 2025-12-31
```

Il **token Bearer** viene letto da `.env`, salvato nel volume `collector_state`
e **rigenerato automaticamente** con login email/password quando scade (HTTP 401).

Pianificazione e stazioni si configurano da `.env`:

```
STATION_CODES=codice_stazione_1,codice_stazione_2
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
3. **Tempo reale** — temperatura, umidità e vento delle ultime rilevazioni;
   con i campi *Dal/Al* si consulta il dettaglio a 15 minuti di un giorno o
   intervallo passato, *Recenti* torna alla vista live.
4. **Tabella dati** — dati giornalieri in forma tabellare.
5. **Foto** — galleria delle foto con il meteo del momento dello scatto.

## Foto con meteo dello scatto

Trascinando immagini nella cartella [photos/](photos/) (montata nel container
`web`), il sistema ne legge i **metadati EXIF** per ricavare la data/ora di
scatto e le mostra nella scheda **Foto**. Le foto vengono raggruppate prima per
**cartella** (il nome della sottocartella diventa il titolo del gruppo; le foto
nella radice non hanno titolo) e poi per **fascia oraria** (intervalli di un'ora).
Per ogni gruppo orario viene associato il **meteo** della stazione selezionata:
la rilevazione *realtime* più vicina (entro ±2 ore) oppure, in mancanza, il
riepilogo giornaliero.

Quando per una foto è disponibile il dato dettagliato, un pulsante **Dettaglio
meteo 48h** apre i grafici a 15 minuti (temperatura/umidità, precipitazioni,
vento) nella finestra **48 ore prima → qualche ora dopo** lo scatto, con una
linea verticale 📷 sull'istante della foto.

- Formati: `.jpg`, `.jpeg`, `.png`, `.tiff`, `.webp`.
- Senza data EXIF si usa la data di modifica del file.
- Le immagini **non** vengono versionate in git.
- Endpoint: `GET /api/photos?station=<codice>`.

## Sicurezza / git

- `.env` (con le credenziali e i codici stazione reali) è in [.gitignore](.gitignore).
- Il dump dei dati (`db/init/02-data.sql`) **non** viene versionato.
- In repo c'è solo `.env.example` con placeholder.

## LOG

```
# log del collector (è il servizio che recupera i dati dalle API)
sudo docker compose logs collector

# in tempo reale (segue gli aggiornamenti)
sudo docker compose logs -f collector

# solo le ultime 50 righe
sudo docker compose logs --tail 50 collector

# tutti i servizi insieme
sudo docker compose logs -f
```

```
sudo docker compose exec db sh -c \
'mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" -e "
USE meteo;
SELECT station_code,
       MAX(observation_time_local) AS ultima_osservazione,
       MAX(created_at)             AS ultimo_inserimento,
       COUNT(*)                    AS righe
FROM realtime_rolando GROUP BY station_code;"'
```