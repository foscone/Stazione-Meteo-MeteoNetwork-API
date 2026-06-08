"""Indicizzazione delle foto: legge dai metadati EXIF la data/ora di scatto.

Le immagini stanno in una cartella montata (PHOTOS_DIR). Per ogni file si ricava
l'istante di scatto da EXIF (DateTimeOriginal); in mancanza, si usa la data di
ultima modifica del file.
"""
import logging
from pathlib import Path
from datetime import datetime

from PIL import Image

log = logging.getLogger("photos")

IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

# Tag EXIF
_DT_ORIGINAL = 36867   # DateTimeOriginal (IFD Exif)
_DT_DIGITIZED = 36868  # DateTimeDigitized (IFD Exif)
_DT = 306              # DateTime (IFD0)
_EXIF_IFD = 0x8769     # puntatore al sub-IFD Exif


def _parse_exif_dt(value):
    """EXIF salva le date come 'YYYY:MM:DD HH:MM:SS'."""
    try:
        return datetime.strptime(str(value).strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def exif_datetime(path: Path):
    """Restituisce (datetime, has_exif). has_exif=False se ricavata dal file."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if exif:
                # DateTimeOriginal/Digitized stanno nel sub-IFD Exif
                try:
                    sub = exif.get_ifd(_EXIF_IFD)
                except Exception:
                    sub = {}
                for tag in (_DT_ORIGINAL, _DT_DIGITIZED):
                    dt = _parse_exif_dt(sub.get(tag))
                    if dt:
                        return dt, True
                dt = _parse_exif_dt(exif.get(_DT))
                if dt:
                    return dt, True
    except Exception as e:
        log.debug("EXIF non leggibile per %s: %s", path.name, e)

    # Fallback: data di modifica del file
    return datetime.fromtimestamp(path.stat().st_mtime), False


def index_photos(folder):
    """Elenca le immagini della cartella (anche nelle sottocartelle) con il loro
    istante di scatto.

    Ritorna una lista di dict ordinati per data:
    {rel, file, folder, taken_at, has_exif}
    dove `folder` è la sottocartella relativa ("" se la foto è nella radice) e
    `rel` è il percorso relativo (per costruire l'URL).
    """
    base = Path(folder)
    if not base.is_dir():
        return []
    items = []
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMG_EXT:
            continue
        rel = p.relative_to(base)
        parent = str(rel.parent)
        sub = "" if parent == "." else parent.replace("\\", "/")
        taken_at, has_exif = exif_datetime(p)
        items.append({
            "rel": str(rel).replace("\\", "/"),
            "file": p.name,
            "folder": sub,
            "taken_at": taken_at,
            "has_exif": has_exif,
        })
    items.sort(key=lambda x: x["taken_at"])
    return items
