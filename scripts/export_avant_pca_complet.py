"""
Export des matrices SST AVANT PCA pour chaque phase.

Deux formats de sortie :
  1. NPZ (NumPy compresse) - matrice complete (N x 691200)
     Phase_X_avant_pca_COMPLET.npz
     -> Lisible avec : data = np.load(...); matrix = data['sst_normalise']

  2. CSV lisible - sous-region Atlantique/Afrique Ouest avec coordonnees lat/lon
     Phase_X_avant_pca_region_AtlAfr.csv
     -> Colonnes = pixels identifies par lat/lon (ex: lat14.25_lon-15.75)
     -> Dimensions : N lignes x ~5000-7000 colonnes selon la region

Dimensions exactes avant PCA :
  Phase 1 : 286 lignes x 691200 colonnes
  Phase 2 : 498 lignes x 691200 colonnes
  Phase 3 : 479 lignes x 691200 colonnes

Usage :
    py -3 -X utf8 scripts/export_avant_pca_complet.py
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.data.sst_loader import load_sst_for_extreme_events
from src.config.settings import PROCESSED_DATA_DIR, RAW_DATA_DIR, OUTPUT_DIR

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Grille OISST v2 connue (60S-60N, 0.25 deg)
# 480 lat x 1440 lon = 691 200 pixels
LATS_GLOBAL = np.arange(-59.875, 60.0, 0.25)   # 480 valeurs
LONS_GLOBAL = np.arange(-179.875, 180.0, 0.25) # 1440 valeurs

# Grille complete : chaque pixel identifie par sa position dans la matrice aplatie
# Ordre : lat varie lentement, lon varie vite (ordre C/row-major)
LATS_FLAT = np.repeat(LATS_GLOBAL, len(LONS_GLOBAL))   # 691200
LONS_FLAT = np.tile(LONS_GLOBAL, len(LATS_GLOBAL))      # 691200

# Sous-region pour le CSV lisible : Atlantique Tropical + Afrique de l'Ouest
# Pertinent pour les teleconnexions avec le Senegal
REGION_LAT_MIN = -20.0
REGION_LAT_MAX =  30.0
REGION_LON_MIN = -60.0
REGION_LON_MAX =  20.0

PHASES = {
    "Phase_1_debut":  {"mois": [5, 6]},
    "Phase_2_pleine": {"mois": [7, 8]},
    "Phase_3_fin":    {"mois": [9, 10]},
}

OUT_DIR = OUTPUT_DIR / "clustering" / "exports_pca"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# CHARGEMENT EVENEMENTS
# ==============================================================================

events_file = PROCESSED_DATA_DIR / "extreme_events_phases_senegal.csv"
print(f"Chargement des evenements : {events_file.name}")
events_all = pd.read_csv(events_file, parse_dates=["date"], index_col="date")
events_all = events_all[
    (events_all.index.year >= 1983) & (events_all.index.year <= 2023)
]
print(f"  Total : {len(events_all)} evenements 1983-2023\n")

# Masque de la sous-region geographique
mask_region = (
    (LATS_FLAT >= REGION_LAT_MIN) & (LATS_FLAT <= REGION_LAT_MAX) &
    (LONS_FLAT >= REGION_LON_MIN) & (LONS_FLAT <= REGION_LON_MAX)
)
n_region = mask_region.sum()
print(f"Sous-region Atl/Afr Ouest ({REGION_LAT_MIN}-{REGION_LAT_MAX}N, "
      f"{REGION_LON_MIN}-{REGION_LON_MAX}E) : {n_region} pixels\n")

# ==============================================================================
# PIPELINE PAR PHASE
# ==============================================================================

for phase_name, cfg in PHASES.items():
    print("=" * 70)
    print(f"  PHASE : {phase_name}")
    print("=" * 70)

    # Filtrage par mois
    events_phase = events_all[events_all.index.month.isin(cfg["mois"])]
    n_events = len(events_phase)
    print(f"  Evenements : {n_events}")

    # Chargement SST
    print("  Chargement des champs SST...")
    sst_matrix, dates, metadata = load_sst_for_extreme_events(
        events_phase, sst_dir=None, variable=None
    )

    n_ev, n_pix = sst_matrix.shape
    print(f"  Matrice SST brute : {n_ev} x {n_pix} pixels")
    assert n_pix == 691200, f"Attention : n_pixels={n_pix}, attendu 691200"

    dates_index = pd.DatetimeIndex(dates)

    # Normalisation pixel par pixel
    print("  Normalisation...")
    matrix_f64 = sst_matrix.astype(np.float64)
    mean = np.mean(matrix_f64, axis=0, keepdims=True)
    std  = np.std(matrix_f64,  axis=0, ddof=0, keepdims=True)
    std  = np.where(std == 0, 1.0, std)
    sst_norm = ((matrix_f64 - mean) / std).astype(np.float32)
    print(f"  Matrice normalisee : {sst_norm.shape[0]} lignes x {sst_norm.shape[1]} colonnes")

    # ------------------------------------------------------------------
    # FORMAT 1 : NPZ compresse (matrice complete 691200 colonnes)
    # ------------------------------------------------------------------
    out_npz = OUT_DIR / f"{phase_name}_avant_pca_COMPLET.npz"
    print(f"  Sauvegarde NPZ complet...")
    np.savez_compressed(
        out_npz,
        sst_normalise  = sst_norm,          # (N x 691200) float32
        sst_brut       = sst_matrix,         # (N x 691200) float32
        dates          = np.array([str(d)[:10] for d in dates]),
        lats           = LATS_FLAT,          # (691200,)
        lons           = LONS_FLAT,          # (691200,)
        phase          = np.array([phase_name]),
        n_events       = np.array([n_ev]),
        n_pixels       = np.array([n_pix]),
    )
    size_mb = out_npz.stat().st_size / (1024**2)
    print(f"  SAUVEGARDE NPZ : {out_npz.name}")
    print(f"    -> {n_ev} lignes x {n_pix} colonnes  ({size_mb:.1f} MB compresse)")
    print(f"    -> Charger avec : data = np.load('{out_npz.name}')")
    print(f"    -> Matrice      : data['sst_normalise']  shape={sst_norm.shape}")
    print(f"    -> Dates        : data['dates']")
    print(f"    -> Coordonnees  : data['lats'], data['lons']")

    # ------------------------------------------------------------------
    # FORMAT 2 : CSV lisible - sous-region geographique
    # ------------------------------------------------------------------
    sst_region = sst_norm[:, mask_region]                   # (N x n_region)
    lats_r     = LATS_FLAT[mask_region]
    lons_r     = LONS_FLAT[mask_region]

    # Noms de colonnes : lat_lon
    col_names = [f"lat{lat:.3f}_lon{lon:.3f}"
                 for lat, lon in zip(lats_r, lons_r)]

    df_region = pd.DataFrame(sst_region, index=dates_index, columns=col_names)
    df_region.index.name = "date"
    df_region.insert(0, "phase", phase_name)
    df_region.insert(1, "year",  dates_index.year)
    df_region.insert(2, "month", dates_index.month)

    out_csv = OUT_DIR / f"{phase_name}_avant_pca_region_AtlAfr.csv"
    print(f"\n  Sauvegarde CSV sous-region...")
    df_region.to_csv(out_csv, float_format="%.4f")
    size_mb_csv = out_csv.stat().st_size / (1024**2)
    print(f"  SAUVEGARDE CSV : {out_csv.name}")
    print(f"    -> {n_ev} lignes x {n_region} colonnes  ({size_mb_csv:.1f} MB)")
    print(f"    -> Region : lat [{REGION_LAT_MIN},{REGION_LAT_MAX}] "
          f"lon [{REGION_LON_MIN},{REGION_LON_MAX}]")
    print()

# ==============================================================================
# RESUME
# ==============================================================================
print()
print("=" * 70)
print("  TOUS LES FICHIERS GENERES : outputs/clustering/exports_pca/")
print("=" * 70)
print(f"  {'Fichier':<55} {'Taille':>8}")
print("  " + "-" * 65)
for f in sorted(OUT_DIR.iterdir()):
    size_mb = f.stat().st_size / (1024**2)
    print(f"  {f.name:<55} {size_mb:>7.1f} MB")
print()
print("  LECTURE DU NPZ :")
print("    import numpy as np")
print("    data   = np.load('Phase_1_debut_avant_pca_COMPLET.npz')")
print("    matrix = data['sst_normalise']   # shape (286, 691200)")
print("    dates  = data['dates']           # dates des evenements")
print("    lats   = data['lats']            # latitude de chaque pixel")
print("    lons   = data['lons']            # longitude de chaque pixel")
