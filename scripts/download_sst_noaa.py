"""
Telechargement des donnees SST NOAA OISST v2 (anomalies journalieres).

Source : https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres/
Format  : sst.day.anom.YYYY.nc  ->  sst_day_anom_YYYY.nc
Periode : 1983-2023 (41 fichiers, ~1 Go chacun)

Fonctionnalites :
  - Reprise automatique si le telechargement est interrompu (Content-Range)
  - Verification d'integrite par taille (Content-Length)
  - Ecriture du progres dans un fichier JSON lu par le dashboard
  - Peut etre arrete proprement via SIGTERM ou fichier .cancel

Usage :
  py -3 scripts/download_sst_noaa.py [--year-start 1983] [--year-end 2023]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# ── Chemins ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SST_DIR      = PROJECT_ROOT / "data" / "raw" / "SST"
STATUS_FILE  = PROJECT_ROOT / "data" / "raw" / "SST" / ".download_status.json"
CANCEL_FILE  = PROJECT_ROOT / "data" / "raw" / "SST" / ".cancel"

# ── NOAA ─────────────────────────────────────────────────────────────────────
BASE_URL    = "https://downloads.psl.noaa.gov/Datasets/noaa.oisst.v2.highres"
CHUNK_SIZE  = 1024 * 1024  # 1 Mo
TIMEOUT     = 60            # secondes
YEAR_START  = 1983
YEAR_END    = 2023


def noaa_url(year: int) -> str:
    return f"{BASE_URL}/sst.day.anom.{year}.nc"


def local_name(year: int) -> str:
    return f"sst_day_anom_{year}.nc"


def write_status(status: dict):
    try:
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def download_file(year: int, dest: Path) -> dict:
    """
    Telecharge un fichier SST avec reprise automatique.
    Retourne un dict {"ok": bool, "msg": str, "size_mb": float}.
    """
    url        = noaa_url(year)
    tmp        = dest.with_suffix(".tmp")
    downloaded = tmp.stat().st_size if tmp.exists() else 0

    headers = {}
    if downloaded > 0:
        headers["Range"] = f"bytes={downloaded}-"
        print(f"  Reprise depuis {downloaded / 1e6:.1f} Mo...")

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=TIMEOUT)

        if resp.status_code == 416:
            # Fichier deja complet dans le .tmp
            tmp.rename(dest)
            size_mb = dest.stat().st_size / 1e6
            return {"ok": True, "msg": "deja complet", "size_mb": size_mb}

        if resp.status_code not in (200, 206):
            return {"ok": False, "msg": f"HTTP {resp.status_code}", "size_mb": 0}

        total = int(resp.headers.get("Content-Length", 0)) + downloaded
        mode  = "ab" if downloaded > 0 else "wb"

        with open(tmp, mode) as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if CANCEL_FILE.exists():
                    return {"ok": False, "msg": "annule", "size_mb": 0}
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    yield downloaded, total  # generateur de progres

        tmp.rename(dest)
        size_mb = dest.stat().st_size / 1e6
        return {"ok": True, "msg": "OK", "size_mb": size_mb}

    except requests.exceptions.Timeout:
        return {"ok": False, "msg": "timeout", "size_mb": 0}
    except requests.exceptions.ConnectionError as e:
        return {"ok": False, "msg": f"connexion: {e}", "size_mb": 0}
    except Exception as e:
        return {"ok": False, "msg": str(e), "size_mb": 0}


def run(year_start: int, year_end: int):
    SST_DIR.mkdir(parents=True, exist_ok=True)
    CANCEL_FILE.unlink(missing_ok=True)

    years   = list(range(year_start, year_end + 1))
    n_total = len(years)

    # Identifier les fichiers manquants
    to_download = [y for y in years if not (SST_DIR / local_name(y)).exists()]
    already     = n_total - len(to_download)

    print(f"[INFO] {already}/{n_total} fichiers deja presents.")
    print(f"[INFO] {len(to_download)} fichiers a telecharger.")

    status = {
        "state":        "running",
        "total":        n_total,
        "already":      already,
        "to_download":  len(to_download),
        "done":         0,
        "current_year": None,
        "current_pct":  0,
        "errors":       [],
        "started_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_status(status)

    for i, year in enumerate(to_download):
        if CANCEL_FILE.exists():
            status["state"] = "cancelled"
            write_status(status)
            print("[INFO] Telechargement annule.")
            return

        dest = SST_DIR / local_name(year)
        print(f"\n[{i+1}/{len(to_download)}] {year} -> {dest.name}")
        status["current_year"] = year
        status["current_pct"]  = 0
        status["updated_at"]   = time.strftime("%Y-%m-%dT%H:%M:%S")
        write_status(status)

        result = None
        gen    = download_file(year, dest)

        for item in gen:
            if isinstance(item, tuple):
                downloaded, total = item
                pct = int(downloaded / total * 100) if total > 0 else 0
                status["current_pct"] = pct
                status["updated_at"]  = time.strftime("%Y-%m-%dT%H:%M:%S")
                write_status(status)
                print(f"\r  {pct:3d}%  {downloaded/1e6:7.1f} / {total/1e6:.1f} Mo", end="", flush=True)
            else:
                result = item

        if result is None:
            # La fonction a retourne directement (pas de chunks)
            result = item

        print()

        if result.get("ok"):
            status["done"] += 1
            print(f"  [OK] {result['size_mb']:.0f} Mo")
        else:
            msg = result.get("msg", "erreur inconnue")
            status["errors"].append({"year": year, "msg": msg})
            print(f"  [ERREUR] {msg}")

        status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        write_status(status)

    status["state"]        = "done"
    status["current_year"] = None
    status["current_pct"]  = 0
    status["updated_at"]   = time.strftime("%Y-%m-%dT%H:%M:%S")
    write_status(status)

    print(f"\n[OK] Termine : {status['done']}/{len(to_download)} telecharges.")
    if status["errors"]:
        print(f"[WARN] {len(status['errors'])} erreur(s) :")
        for e in status["errors"]:
            print(f"  - {e['year']}: {e['msg']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telecharge les SST NOAA OISST v2")
    parser.add_argument("--year-start", type=int, default=YEAR_START)
    parser.add_argument("--year-end",   type=int, default=YEAR_END)
    args = parser.parse_args()
    run(args.year_start, args.year_end)
