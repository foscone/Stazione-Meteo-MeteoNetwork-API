# Cartella foto

Trascina qui le tue fotografie (`.jpg`, `.jpeg`, `.png`, `.tiff`, `.webp`).

Il sistema legge i **metadati EXIF** di ogni foto per ricavare la **data e ora
di scatto** e, nella scheda **Foto** della dashboard, mostra le foto raggruppate
per **fascia oraria** (intervalli di un'ora) insieme ai **dati meteo** rilevati
in quel momento dalla stazione selezionata.

Note:
- Se una foto non ha la data EXIF (es. molti PNG o immagini modificate), viene
  usata la data di ultima modifica del file.
- Le immagini in questa cartella **non vengono versionate** in git (solo questo
  README e `.gitkeep`).
- La cartella è montata nel container `web` in sola lettura.
