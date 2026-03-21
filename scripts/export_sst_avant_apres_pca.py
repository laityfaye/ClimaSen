"""
Export des matrices SST avant et apres PCA pour chaque phase.

Fichiers generes (dans outputs/clustering/exports_pca/) :
  Phase_X_avant_pca_region.csv  : SST normalise sur la region Atlantique/Afrique Ouest
                                   (sous-ensemble geographique lisible, N events x M pixels)
  Phase_X_apres_pca.csv         : SST projete en espace PCA (N events x n_composantes)

Usage :
    py -3 scripts/export_sst_avant_apres_pca.py
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.data.sst_loader import load_sst_for_extreme_events
from src.config.settings import PROCESSED_DATA_DIR, RAW_DATA_DIR, OUTPUT_DIR

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Seuil PCA : 90% de variance expliquee (identique au script 11)
PCA_VARIANCE_THRESHOLD = 0.90

# Sous-region geographique pour le CSV "avant PCA"
# Atlantique tropical + Afrique de l'Ouest : zone pertinente pour les teleconnexions
REGION_LAT_MIN = -20.0
REGION_LAT_MAX =  30.0
REGION_LON_MIN = -60.0
REGION_LON_MAX =  20.0

PHASES = {
    "Phase_1_debut":  {"mois": [5, 6],  "label": "Debut (Mai-Jun)"},
    "Phase_2_pleine": {"mois": [7, 8],  "label": "Pleine (Jul-Aou)"},
    "Phase_3_fin":    {"mois": [9, 10], "label": "Fin (Sep-Oct)"},
}

OUT_DIR = OUTPUT_DIR / "clustering" / "exports_pca"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# CHARGEMENT DES EVENEMENTS
# ==============================================================================

events_file = PROCESSED_DATA_DIR / "extreme_events_phases_senegal.csv"
print(f"Chargement des evenements : {events_file.name}")
events_all = pd.read_csv(events_file, parse_dates=["date"], index_col="date")
events_all = events_all[
    (events_all.index.year >= 1983) & (events_all.index.year <= 2023)
]
print(f"  Total evenements 1983-2023 : {len(events_all)}")

# ==============================================================================
# PIPELINE PAR PHASE
# ==============================================================================

for phase_name, cfg in PHASES.items():
    print()
    print("=" * 70)
    print(f"  PHASE : {phase_name}  ({cfg['label']})")
    print("=" * 70)

    # --- Filtrage par mois ---
    events_phase = events_all[events_all.index.month.isin(cfg["mois"])]
    print(f"  Evenements dans la phase : {len(events_phase)}")

    # --- Chargement SST ---
    print("  Chargement des champs SST...")
    sst_matrix, dates, metadata = load_sst_for_extreme_events(
        events_phase,
        sst_dir=None,
        variable=None
    )

    n_events, n_pixels = sst_matrix.shape
    print(f"  Matrice SST brute : {n_events} evenements x {n_pixels} pixels")

    # Recuperer les coordonnees lat/lon depuis le metadata
    lats = np.array(metadata.get("lats", []))
    lons = np.array(metadata.get("lons", []))

    dates_index = pd.DatetimeIndex(dates)

    # ==================================================================
    # ETAPE A : NORMALISATION (identique au script 11)
    # ==================================================================
    print("  Normalisation pixel par pixel...")
    matrix_f64 = sst_matrix.astype(np.float64)
    mean = np.mean(matrix_f64, axis=0, keepdims=True)
    std  = np.std(matrix_f64,  axis=0, ddof=0, keepdims=True)
    std  = np.where(std == 0, 1.0, std)
    sst_normalized = ((matrix_f64 - mean) / std).astype(np.float32)
    print(f"  Matrice normalisee : {sst_normalized.shape}")

    # ==================================================================
    # SAUVEGARDE AVANT PCA : sous-region geographique
    # ==================================================================
    if len(lats) == n_pixels and len(lons) == n_pixels:
        mask_region = (
            (lats >= REGION_LAT_MIN) & (lats <= REGION_LAT_MAX) &
            (lons >= REGION_LON_MIN) & (lons <= REGION_LON_MAX)
        )
        n_region = mask_region.sum()
        print(f"  Region Atlantique/Afrique Ouest : {n_region} pixels selectionnes")

        sst_region = sst_normalized[:, mask_region]
        lats_region = lats[mask_region]
        lons_region = lons[mask_region]

        # Colonnes : lat_lon pour identifier chaque pixel
        col_names = [f"lat{lat:.2f}_lon{lon:.2f}"
                     for lat, lon in zip(lats_region, lons_region)]

        df_avant = pd.DataFrame(sst_region, index=dates_index, columns=col_names)
        df_avant.index.name = "date"

        # Ajouter colonnes descriptives en tete
        df_avant.insert(0, "phase", phase_name)
        df_avant.insert(1, "year", dates_index.year)
        df_avant.insert(2, "month", dates_index.month)

        out_avant = OUT_DIR / f"{phase_name}_avant_pca_region.csv"
        df_avant.to_csv(out_avant, float_format="%.4f")
        size_mb = out_avant.stat().st_size / (1024**2)
        print(f"  SAUVEGARDE avant PCA : {out_avant.name}  "
              f"({n_events} lignes x {n_region+3} colonnes, {size_mb:.1f} MB)")
    else:
        print("  AVERTISSEMENT : coordonnees lat/lon non disponibles dans metadata.")
        print("  Export avant PCA ignore (impossible d'identifier les pixels).")

    # ==================================================================
    # ETAPE B : PCA (identique au script 11)
    # ==================================================================
    print("  Reduction PCA...")
    max_components = min(n_events, n_pixels)
    pca_model = PCA(n_components=max_components)
    sst_pca_full = pca_model.fit_transform(sst_normalized)

    cumvar = np.cumsum(pca_model.explained_variance_ratio_)
    n_comp = int(np.searchsorted(cumvar, PCA_VARIANCE_THRESHOLD)) + 1
    n_comp = max(n_comp, 2)
    n_comp = min(n_comp, max_components)

    sst_pca = sst_pca_full[:, :n_comp]
    print(f"  {n_comp} composantes retenues "
          f"(variance expliquee : {cumvar[n_comp-1]:.1%})")

    # ==================================================================
    # SAUVEGARDE APRES PCA
    # ==================================================================
    col_pca = [f"PC{i+1}" for i in range(n_comp)]
    df_apres = pd.DataFrame(sst_pca, index=dates_index, columns=col_pca)
    df_apres.index.name = "date"

    # Ajouter colonnes descriptives + variance expliquee par PC
    df_apres.insert(0, "phase", phase_name)
    df_apres.insert(1, "year",  dates_index.year)
    df_apres.insert(2, "month", dates_index.month)

    out_apres = OUT_DIR / f"{phase_name}_apres_pca.csv"
    df_apres.to_csv(out_apres, float_format="%.4f")
    size_mb = out_apres.stat().st_size / (1024**2)
    print(f"  SAUVEGARDE apres PCA  : {out_apres.name}  "
          f"({n_events} lignes x {n_comp+3} colonnes, {size_mb:.2f} MB)")

    # ------------------------------------------------------------------
    # FICHIER COMPLEMENTAIRE : variance expliquee par composante
    # ------------------------------------------------------------------
    df_var = pd.DataFrame({
        "composante":        col_pca,
        "variance_expliquee": pca_model.explained_variance_ratio_[:n_comp].round(6),
        "variance_cumulee":   cumvar[:n_comp].round(6),
    })
    out_var = OUT_DIR / f"{phase_name}_pca_variance_expliquee.csv"
    df_var.to_csv(out_var, index=False)
    print(f"  SAUVEGARDE variance   : {out_var.name}")

# ==============================================================================
# RESUME FINAL
# ==============================================================================
print()
print("=" * 70)
print("  FICHIERS GENERES dans : outputs/clustering/exports_pca/")
print("=" * 70)
for f in sorted(OUT_DIR.iterdir()):
    size_mb = f.stat().st_size / (1024**2)
    print(f"  {f.name:<55}  {size_mb:6.2f} MB")
print()
