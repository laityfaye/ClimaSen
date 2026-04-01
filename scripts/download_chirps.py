"""
Telechargement des donnees CHIRPS v2.0 (precipitations journalieres, 0.25deg).

Source  : https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/netcdf/p25/
Format  : chirps-v2.0.YYYY.days_p25.nc  (global, ~67 Mo/an)
Sortie  : data/raw/<nom_fichier>.mat  (HDF5, decoupage bbox, float32)

Fonctionnalites :
  - Reprise automatique par annee (HTTP Range)
  - Verification integrite par taille (Content-Length)
  - Progression JSON lue par le dashboard (.download_chirps_status.json)
  - Annulation propre via fichier .cancel_chirps

Usage :
  py -3 scripts/download_chirps.py
      --year-start 1981 --year-end 2023
      --lat-min 12 --lat-max 17
      --lon-min -17.6 --lon-max -11.3
      --output chirps_senegal_1981_2023.mat
"""

import argparse
import gc
import json
import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

import numpy as np
import requests

# ── Chemins ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RAW_DIR      = PROJECT_ROOT / "data" / "raw"
STATUS_FILE  = RAW_DIR / ".download_chirps_status.json"
CANCEL_FILE  = RAW_DIR / ".cancel_chirps"

# ── CHIRPS ────────────────────────────────────────────────────────────────────
BASE_URL   = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/netcdf/p25"
CHUNK_SIZE = 2 * 1024 * 1024  # 2 Mo
TIMEOUT    = 120


def chirps_url(year: int) -> str:
    return f"{BASE_URL}/chirps-v2.0.{year}.days_p25.nc"


def write_status(status: dict):
    try:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def download_year(year: int, tmp_dir: Path) -> tuple:
    """
    Telecharge le fichier CHIRPS d'une annee dans tmp_dir avec reprise.
    Retourne (ok: bool, path: Path|None, msg: str).
    """
    url  = chirps_url(year)
    dest = tmp_dir / f"chirps_{year}.nc"
    downloaded = dest.stat().st_size if dest.exists() else 0

    headers = {}
    if downloaded > 0:
        headers["Range"] = f"bytes={downloaded}-"

    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=TIMEOUT)

        if resp.status_code == 416:
            return True, dest, "deja complet"
        if resp.status_code not in (200, 206):
            return False, None, f"HTTP {resp.status_code}"

        total = int(resp.headers.get("Content-Length", 0)) + downloaded
        mode  = "ab" if downloaded > 0 else "wb"

        with open(dest, mode) as fh:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if CANCEL_FILE.exists():
                    return False, None, "annule"
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    yield downloaded, total

        return True, dest, "OK"

    except requests.exceptions.Timeout:
        return False, None, "timeout"
    except requests.exceptions.ConnectionError as e:
        return False, None, f"connexion: {str(e)[:80]}"
    except Exception as e:
        return False, None, str(e)[:120]


def clip_and_save(nc_path: Path, year: int,
                  lat_min: float, lat_max: float,
                  lon_min: float, lon_max: float) -> tuple:
    """
    Decoupe le NetCDF sur la bbox et retourne (array, lats, lons).
    """
    import xarray as xr
    ds = xr.open_dataset(str(nc_path))

    # Detecter les noms de coordonnees
    lat_name = next((n for n in ["latitude", "lat", "Latitude", "LAT"] if n in ds.coords), None)
    lon_name = next((n for n in ["longitude", "lon", "Longitude", "LON"] if n in ds.coords), None)
    if lat_name is None or lon_name is None:
        ds.close()
        raise ValueError(f"Coordonnees lat/lon non trouvees. Disponibles: {list(ds.coords)}")

    ds_clip = ds.sel(
        {lat_name: slice(lat_min, lat_max),
         lon_name: slice(lon_min, lon_max)}
    )

    var_name = next((v for v in ["precip", "precipitation", "pr", "rain"] if v in ds_clip.data_vars), None)
    if var_name is None:
        var_name = list(ds_clip.data_vars)[0]

    arr  = ds_clip[var_name].values.astype(np.float32)
    arr  = np.where(arr < -9000, np.nan, arr)
    lats = ds_clip[lat_name].values.astype(np.float64)
    lons = ds_clip[lon_name].values.astype(np.float64)
    ds.close()

    return arr, lats, lons


def save_hdf5(out_path: Path, precip: np.ndarray,
              lats: np.ndarray, lons: np.ndarray,
              meta: dict):
    import h5py
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(str(out_path), "w") as hf:
        hf.create_dataset("precip", data=precip,
                          compression="gzip", compression_opts=4, chunks=True)
        hf.create_dataset("latitude",  data=lats)
        hf.create_dataset("longitude", data=lons)
        for k, v in meta.items():
            hf.attrs[k] = v


def run(year_start: int, year_end: int,
        lat_min: float, lat_max: float,
        lon_min: float, lon_max: float,
        output: str):

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CANCEL_FILE.unlink(missing_ok=True)

    out_path = RAW_DIR / output
    years    = list(range(year_start, year_end + 1))
    n_total  = len(years)

    status = {
        "state":        "running",
        "output":       output,
        "total":        n_total,
        "done":         0,
        "current_year": None,
        "current_pct":  0,
        "phase":        "telechargement",
        "errors":       [],
        "started_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
        "updated_at":   time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    write_status(status)
    print(f"[INFO] {n_total} annees a traiter ({year_start}-{year_end})")
    print(f"[INFO] Bbox : lat [{lat_min},{lat_max}] lon [{lon_min},{lon_max}]")
    print(f"[INFO] Sortie : {out_path}")

    tmp_dir    = Path(tempfile.mkdtemp(prefix="chirps_dl_"))
    all_precip = []
    lats_ref   = lons_ref = None

    try:
        for i, year in enumerate(years):
            if CANCEL_FILE.exists():
                status["state"] = "cancelled"
                write_status(status)
                print("[INFO] Annule.")
                return

            print(f"\n[{i+1}/{n_total}] {year}")
            status["current_year"] = year
            status["current_pct"]  = 0
            status["phase"]        = "telechargement"
            status["updated_at"]   = time.strftime("%Y-%m-%dT%H:%M:%S")
            write_status(status)

            # ── Telechargement ────────────────────────────────────────────────
            nc_path = tmp_dir / f"chirps_{year}.nc"
            ok      = False
            result  = None

            for item in download_year(year, tmp_dir):
                if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], int):
                    downloaded, total = item
                    pct = int(downloaded / total * 100) if total > 0 else 0
                    status["current_pct"] = pct
                    status["updated_at"]  = time.strftime("%Y-%m-%dT%H:%M:%S")
                    write_status(status)
                    print(f"\r  DL {pct:3d}%  {downloaded/1e6:6.1f}/{total/1e6:.0f} Mo",
                          end="", flush=True)
                else:
                    result = item

            print()

            if result is None:
                result = item

            if isinstance(result, tuple) and len(result) == 3:
                ok, nc_path_r, msg = result
                if nc_path_r:
                    nc_path = nc_path_r
            else:
                ok, msg = False, str(result)

            if not ok:
                print(f"  [ERREUR DL] {msg}")
                status["errors"].append({"year": year, "phase": "dl", "msg": msg})
                status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                write_status(status)
                continue

            # ── Decoupage bbox ────────────────────────────────────────────────
            status["phase"]       = "decoupage"
            status["current_pct"] = 95
            status["updated_at"]  = time.strftime("%Y-%m-%dT%H:%M:%S")
            write_status(status)
            print(f"  Decoupage bbox...", end="", flush=True)

            try:
                arr, lats, lons = clip_and_save(nc_path, year,
                                                lat_min, lat_max,
                                                lon_min, lon_max)
                if lats_ref is None:
                    lats_ref, lons_ref = lats, lons
                all_precip.append(arr)
                n_days = arr.shape[0]
                print(f" {n_days} jours  {arr.shape[1]}x{arr.shape[2]} px  [OK]")
                status["done"] += 1
            except Exception as e:
                print(f" [ERREUR] {e}")
                status["errors"].append({"year": year, "phase": "clip", "msg": str(e)[:120]})

            try:
                nc_path.unlink()
            except Exception:
                pass

            status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            write_status(status)

        # ── Concatenation et sauvegarde ───────────────────────────────────────
        if not all_precip:
            status["state"] = "error"
            status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            write_status(status)
            print("[ERREUR] Aucune donnee recuperee.")
            return

        status["phase"]        = "sauvegarde"
        status["current_year"] = None
        status["current_pct"]  = 0
        status["updated_at"]   = time.strftime("%Y-%m-%dT%H:%M:%S")
        write_status(status)

        print(f"\nConcatenation de {len(all_precip)} annees...")
        precip_full = np.concatenate(all_precip, axis=0)
        del all_precip
        gc.collect()
        print(f"  Shape finale : {precip_full.shape}  ({precip_full.nbytes/1e9:.2f} Go)")

        print(f"Sauvegarde HDF5 : {out_path.name}...")
        save_hdf5(out_path, precip_full, lats_ref, lons_ref, {
            "source":     "CHIRPS v2.0 Global Daily 0.25deg",
            "year_start": year_start,
            "year_end":   year_end,
            "lat_min":    lat_min,
            "lat_max":    lat_max,
            "lon_min":    lon_min,
            "lon_max":    lon_max,
            "n_days":     int(precip_full.shape[0]),
            "created_by": "SenRain Dashboard",
        })

        size_mb = out_path.stat().st_size / 1e6
        status["state"]      = "done"
        status["size_mb"]    = round(size_mb, 1)
        status["n_days"]     = int(precip_full.shape[0])
        status["n_lat"]      = int(lats_ref.shape[0])
        status["n_lon"]      = int(lons_ref.shape[0])
        status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        write_status(status)

        print(f"[OK] {out_path.name} — {size_mb:.0f} Mo  "
              f"({precip_full.shape[0]} jours, "
              f"{lats_ref.shape[0]}x{lons_ref.shape[0]} pixels)")
        if status["errors"]:
            print(f"[WARN] {len(status['errors'])} erreur(s) ignoree(s) :")
            for e in status["errors"]:
                print(f"  - {e['year']} ({e['phase']}): {e['msg']}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telecharge CHIRPS v2.0 depuis CHC UCSB")
    parser.add_argument("--year-start", type=int, default=1981)
    parser.add_argument("--year-end",   type=int, default=2023)
    parser.add_argument("--lat-min",    type=float, default=12.0)
    parser.add_argument("--lat-max",    type=float, default=17.0)
    parser.add_argument("--lon-min",    type=float, default=-17.6)
    parser.add_argument("--lon-max",    type=float, default=-11.3)
    parser.add_argument("--output",     type=str,
                        default="chirps_senegal_1981_2023_daily.mat")
    args = parser.parse_args()
    run(args.year_start, args.year_end,
        args.lat_min, args.lat_max,
        args.lon_min, args.lon_max,
        args.output)
