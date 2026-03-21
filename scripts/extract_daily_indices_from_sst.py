#!/usr/bin/env python3
# scripts/extract_daily_indices_from_sst.py
"""
Extraction des indices climatiques journaliers depuis les fichiers SST NetCDF OISST v2.

Source SST : NOAA OISST v2 High-Resolution (0.25 deg, journalier, 60S-60N)
             data/raw/SST/sst_day_anom_YYYY.nc  (variable : anom)

Indices extraits :
  Famille ENSO  : Nino12, Nino3, Nino34, Nino4
  Ocean Indien  : IOD (Dipole Mode Index), IOBM
  Atlantique    : TNA, TSA, ATL3, AMM, AMO

Methode : moyenne spatiale de l'anomalie SST sur la boite geographique
          de chaque indice (standards internationaux).
          Aucun detrend, aucun filtre applique.

Sorties :
  data/raw/climate_indices/daily_indices_all.csv   (tous les indices en une table)
  data/raw/climate_indices/daily_{indice}.csv      (un fichier par indice)

Usage :
    python scripts/extract_daily_indices_from_sst.py
    python scripts/extract_daily_indices_from_sst.py --years 1990 2005
"""

import sys
import ctypes
import argparse
from ctypes import wintypes
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import xarray as xr

# ==============================================================================
# CHEMINS
# ==============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SST_DIR      = PROJECT_ROOT / "data" / "raw" / "SST"
OUT_DIR      = PROJECT_ROOT / "data" / "raw" / "climate_indices"

SST_VAR   = "anom"         # nom de la variable SST dans les fichiers
SST_EPOCH = pd.Timestamp("1800-01-01")  # epoch OISST confirmee

# ==============================================================================
# DEFINITIONS DES BOITES GEOGRAPHIQUES
# (lat_min, lat_max, lon_min, lon_max) — convention -180/+180
# ==============================================================================

BOXES = {
    # ── Famille ENSO ──────────────────────────────────────────────────────────
    "Nino12": (-10,   0,   -90,  -80),   # Pacifique Est cotier
    "Nino3":  ( -5,   5,  -150,  -90),   # Pacifique Est central
    "Nino34": ( -5,   5,  -170, -120),   # Pacifique Central (ENSO standard ONI)
    # Nino4 straddle le dateline → traitement special dans nino4_mean()

    # ── Ocean Indien ──────────────────────────────────────────────────────────
    "IOBM":   (-20,  20,    40,  100),   # Indian Ocean Basin Mode

    # ── Atlantique Tropical ───────────────────────────────────────────────────
    "TNA":    (5.5, 23.5, -57.5, -15),   # Tropical North Atlantic
    "TSA":    (-20,   0,   -30,   10),   # Tropical South Atlantic
    "ATL3":   ( -3,   3,   -20,    0),   # Golfe de Guinee (Gulf of Guinea)

    # ── Atlantique Nord ───────────────────────────────────────────────────────
    "AMO":    (  0,  60,   -80,    0),   # Atlantic Multidecadal Oscillation
}

# IOD = West Indian Ocean SST - East Indian Ocean SST
IOD_WEST = (-10,  10,  50,  70)   # West Tropical Indian Ocean (WTIO)
IOD_EAST = (-10,   0,  90, 110)   # South-East Tropical Indian Ocean (SETIO)

# Nino4 : 5S-5N, 160E-150W (straddle dateline)
NINO4_LAT = (-5, 5)
NINO4_LON_W = (160, 180)    # partie ouest du dateline (valeurs positives)
NINO4_LON_E = (-180, -150)  # partie est du dateline (valeurs negatives)

# Ordre de sortie des colonnes
ALL_INDICES = ["Nino12", "Nino3", "Nino34", "Nino4",
               "IOD", "IOBM",
               "TNA", "TSA", "ATL3", "AMM", "AMO"]


# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

def get_short_path(path_str: str) -> str:
    """Convertit un chemin Windows long (avec accents) en chemin 8.3."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetShortPathNameW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        kernel32.GetShortPathNameW.restype = wintypes.DWORD
        buf = ctypes.create_unicode_buffer(260)
        kernel32.GetShortPathNameW(path_str, buf, 260)
        return buf.value or path_str
    except Exception:
        return path_str


def find_coord(ds: xr.Dataset, candidates: list) -> str:
    """Retourne le premier nom de coordonnee trouve dans le dataset."""
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    return None


def decode_time_axis(ds: xr.Dataset, time_name: str) -> pd.DatetimeIndex:
    """
    Decode l'axe temporel du dataset en DatetimeIndex Pandas.
    Utilise les attributs 'units' de la variable time (CF conventions).
    Fallback : epoch OISST connue = 1800-01-01.
    """
    time_var = ds[time_name]
    units = time_var.attrs.get("units", "")

    if "days since" in units:
        epoch_str = units.replace("days since", "").strip()
        try:
            epoch = pd.Timestamp(epoch_str)
            deltas = [pd.Timedelta(days=float(t)) for t in time_var.values]
            return pd.DatetimeIndex([epoch + d for d in deltas])
        except Exception:
            pass

    # Fallback : epoch OISST = 1800-01-01 (confirme sur les fichiers du projet)
    deltas = [pd.Timedelta(days=float(t)) for t in time_var.values]
    return pd.DatetimeIndex([SST_EPOCH + d for d in deltas])


def spatial_mean(da: xr.DataArray,
                 lat_name: str, lon_name: str,
                 lat_min: float, lat_max: float,
                 lon_min: float, lon_max: float) -> np.ndarray:
    """
    Calcule la moyenne spatiale pondree par cos(lat) sur une boite geographique.
    Retourne un vecteur (n_temps,).
    """
    sub = da.sel({lat_name: slice(lat_min, lat_max),
                  lon_name: slice(lon_min, lon_max)})

    # Ponderation par cos(latitude) pour corriger la convergence des meridiens
    lats_rad = np.deg2rad(sub[lat_name].values)
    weights  = np.cos(lats_rad)

    # Appliquer les poids sur la dimension lat
    weighted = sub * xr.DataArray(weights, dims=[lat_name],
                                  coords={lat_name: sub[lat_name]})
    total_w  = sub.notnull() * xr.DataArray(weights, dims=[lat_name],
                                            coords={lat_name: sub[lat_name]})

    mean_val = weighted.sum(dim=[lat_name, lon_name]) / \
               total_w.sum(dim=[lat_name, lon_name])
    return mean_val.values


def nino4_mean(da: xr.DataArray, lat_name: str, lon_name: str) -> np.ndarray:
    """
    Nino4 straddle le dateline (160E-150W).
    Concatene les deux portions avant de faire la moyenne.
    """
    lat_min, lat_max = NINO4_LAT
    lats_sub = da.sel({lat_name: slice(lat_min, lat_max)})

    part_w = lats_sub.sel({lon_name: slice(*NINO4_LON_W)})  # 160E -> 180
    part_e = lats_sub.sel({lon_name: slice(*NINO4_LON_E)})  # -180 -> -150

    combined = xr.concat([part_w, part_e], dim=lon_name)

    lats_rad = np.deg2rad(combined[lat_name].values)
    weights  = np.cos(lats_rad)
    weighted = combined * xr.DataArray(weights, dims=[lat_name],
                                       coords={lat_name: combined[lat_name]})
    total_w  = combined.notnull() * xr.DataArray(weights, dims=[lat_name],
                                                  coords={lat_name: combined[lat_name]})
    mean_val = weighted.sum(dim=[lat_name, lon_name]) / \
               total_w.sum(dim=[lat_name, lon_name])
    return mean_val.values


# ==============================================================================
# EXTRACTION POUR UN FICHIER ANNUEL
# ==============================================================================

def extract_one_year(nc_path: Path) -> pd.DataFrame:
    """
    Extrait tous les indices climatiques journaliers depuis un fichier SST annuel.

    Returns
    -------
    DataFrame (n_jours x (1 + n_indices)) avec colonne 'date' et une par indice.
    DataFrame vide en cas d'erreur.
    """
    short = get_short_path(str(nc_path))

    try:
        ds = xr.open_dataset(short, decode_times=False, engine='netcdf4')
    except Exception:
        try:
            ds = xr.open_dataset(short, decode_times=False, engine='scipy')
        except Exception as e:
            print(f"    [ERREUR] Impossible d'ouvrir {nc_path.name}: {e}")
            return pd.DataFrame()

    try:
        # ── Detection des coordonnees ─────────────────────────────────────
        lat_name  = find_coord(ds, ['lat', 'latitude', 'Lat', 'LAT', 'LATITUDE'])
        lon_name  = find_coord(ds, ['lon', 'longitude', 'Lon', 'LON', 'LONGITUDE'])
        time_name = find_coord(ds, ['time', 'Time', 'TIME'])

        if None in (lat_name, lon_name, time_name):
            print(f"    [ERREUR] Coordonnees manquantes dans {nc_path.name}")
            return pd.DataFrame()

        if SST_VAR not in ds.data_vars:
            available = list(ds.data_vars)
            print(f"    [ERREUR] Variable '{SST_VAR}' absente. Disponibles: {available}")
            return pd.DataFrame()

        da = ds[SST_VAR]  # dims : (time, lat, lon)

        # ── Decodage des temps ────────────────────────────────────────────
        dates = decode_time_axis(ds, time_name)
        n_days = len(dates)

        # ── Extraction de chaque indice ───────────────────────────────────
        results = {"date": dates}

        # Indices a boite simple
        for name, (lat_mn, lat_mx, lon_mn, lon_mx) in BOXES.items():
            ts = spatial_mean(da, lat_name, lon_name,
                              lat_mn, lat_mx, lon_mn, lon_mx)
            results[name] = ts

        # Nino4 (straddle dateline)
        results["Nino4"] = nino4_mean(da, lat_name, lon_name)

        # IOD = West - East
        iod_w = spatial_mean(da, lat_name, lon_name, *IOD_WEST)
        iod_e = spatial_mean(da, lat_name, lon_name, *IOD_EAST)
        results["IOD"] = iod_w - iod_e

        # AMM simplifie = TNA - TSA
        results["AMM"] = results["TNA"] - results["TSA"]

        # ── Construction du DataFrame ─────────────────────────────────────
        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Arrondi a 4 decimales pour lisibilite
        idx_cols = [c for c in df.columns if c != "date"]
        df[idx_cols] = df[idx_cols].round(4)

        return df

    except Exception as e:
        print(f"    [ERREUR] Traitement {nc_path.name}: {e}")
        import traceback; traceback.print_exc()
        return pd.DataFrame()

    finally:
        ds.close()


# ==============================================================================
# PIPELINE PRINCIPAL
# ==============================================================================

def run(year_range: tuple = None):
    print()
    print("=" * 70)
    print("  EXTRACTION DES INDICES CLIMATIQUES JOURNALIERS DEPUIS SST")
    print("=" * 70)
    print(f"  Source  : {SST_DIR}")
    print(f"  Sortie  : {OUT_DIR}")
    print(f"  Indices : {', '.join(ALL_INDICES)}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Listage des fichiers SST disponibles ──────────────────────────────────
    nc_files = sorted(SST_DIR.glob("sst_day_anom_*.nc"))
    if not nc_files:
        print(f"[ERREUR] Aucun fichier SST trouve dans {SST_DIR}")
        sys.exit(1)

    # Filtrage par annees si demande
    if year_range:
        yr_min, yr_max = year_range
        nc_files = [f for f in nc_files
                    if any(str(y) in f.name
                           for y in range(yr_min, yr_max + 1))]

    print(f"  {len(nc_files)} fichiers SST a traiter")
    print(f"  Periode : {nc_files[0].name} -> {nc_files[-1].name}")
    print()

    # ── Extraction annee par annee ────────────────────────────────────────────
    all_dfs = []

    for i, nc_path in enumerate(nc_files, 1):
        year_tag = nc_path.stem.replace("sst_day_anom_", "")
        print(f"  [{i:2d}/{len(nc_files)}] {nc_path.name} ...", end=" ", flush=True)

        df_year = extract_one_year(nc_path)

        if df_year.empty:
            print("IGNORE")
            continue

        all_dfs.append(df_year)
        print(f"{len(df_year)} jours  [{df_year['date'].iloc[0].date()} "
              f"-> {df_year['date'].iloc[-1].date()}]")

    if not all_dfs:
        print("\n[ERREUR] Aucune donnee extraite.")
        sys.exit(1)

    # ── Concatenation et tri ─────────────────────────────────────────────────
    print()
    print("  Concatenation de toutes les annees...")
    full = pd.concat(all_dfs, ignore_index=True)
    full = full.sort_values("date").reset_index(drop=True)

    # Reordonner les colonnes
    ordered_cols = ["date"] + [c for c in ALL_INDICES if c in full.columns]
    full = full[ordered_cols]

    # ── Sauvegarde CSV combine ────────────────────────────────────────────────
    out_all = OUT_DIR / "daily_indices_all.csv"
    full.to_csv(out_all, index=False)
    print(f"  Sauvegarde : {out_all.name}  ({len(full)} lignes)")

    # ── Sauvegarde un CSV par indice ─────────────────────────────────────────
    print()
    print("  Sauvegarde des fichiers individuels :")
    for idx in ALL_INDICES:
        if idx not in full.columns:
            continue
        df_idx = full[["date", idx]].copy()
        out_idx = OUT_DIR / f"daily_{idx}.csv"
        df_idx.to_csv(out_idx, index=False)
        n_valid = df_idx[idx].notna().sum()
        print(f"    daily_{idx}.csv  ({n_valid} valeurs valides)")

    # ── Statistiques de synthese ─────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  STATISTIQUES DES INDICES EXTRAITS")
    print("=" * 70)
    print(f"  {'Indice':<10} {'Periode':^25} {'Min':>8} {'Max':>8} "
          f"{'Moy':>8} {'N valide':>10}")
    print("  " + "-" * 65)
    for idx in ALL_INDICES:
        if idx not in full.columns:
            continue
        col = full[idx]
        n_ok  = col.notna().sum()
        if n_ok == 0:
            continue
        d_min = full.loc[col.notna(), "date"].min().strftime("%Y-%m-%d")
        d_max = full.loc[col.notna(), "date"].max().strftime("%Y-%m-%d")
        periode = f"{d_min} / {d_max}"
        print(f"  {idx:<10} {periode:^25} {col.min():>8.3f} {col.max():>8.3f} "
              f"{col.mean():>8.3f} {n_ok:>10}")

    print()
    print(f"  Tous les fichiers dans : {OUT_DIR}")
    print("=" * 70)
    print()

    return full


# ==============================================================================
# ENTREE DU PROGRAMME
# ==============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Extraction des indices climatiques journaliers depuis SST OISST v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Indices extraits :
  Nino12  : Pacifique Est cotier    (0-10S, 90-80W)
  Nino3   : Pacifique Est central   (5S-5N, 150-90W)
  Nino34  : Pacifique Central ENSO  (5S-5N, 170-120W)
  Nino4   : Pacifique Ouest         (5S-5N, 160E-150W)
  IOD     : Dipole Ocean Indien     (West WTIO - East SETIO)
  IOBM    : Indian Ocean Basin Mode (20S-20N, 40-100E)
  TNA     : Atlantique Nord Trop.   (5.5-23.5N, 57.5-15W)
  TSA     : Atlantique Sud Trop.    (20S-0, 30W-10E)
  ATL3    : Golfe de Guinee         (3S-3N, 20-0W)
  AMM     : Atlantic Merid. Mode    (TNA - TSA, simplifie)
  AMO     : Atlantic Multidecadal   (0-60N, 80-0W)

Exemples :
  python scripts/extract_daily_indices_from_sst.py
  python scripts/extract_daily_indices_from_sst.py --years 1990 2023
        """
    )
    parser.add_argument(
        "--years", type=int, nargs=2, metavar=("DEBUT", "FIN"),
        default=None,
        help="Filtrer les annees (ex: --years 1990 2005)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args  = parse_args()
    run(year_range=tuple(args.years) if args.years else None)
