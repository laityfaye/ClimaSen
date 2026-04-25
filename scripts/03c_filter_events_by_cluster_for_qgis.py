#!/usr/bin/env python3
"""
Extraction d'evenements representatifs par cluster pour cartographie QGIS.

Pour chaque cluster (par phase), selectionne les 4 evenements representatifs :
  - plus_intense        : max_precip maximum
  - moins_intense       : max_precip minimum
  - plus_grande_couverture : coverage_percent maximum
  - plus_petite_couverture : coverage_percent minimum

Sortie : Fichiers CSV prêts pour QGIS, organises par phase et cluster.

Utilisation:
    py -3 scripts/03c_filter_events_by_cluster_for_qgis.py [chemin_chirps.mat]
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import h5py
from datetime import datetime, timedelta
import warnings
import json
from typing import List, Dict, Tuple
from matplotlib.path import Path as MplPath

warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=UserWarning)

import matplotlib
matplotlib.use('Agg')


# ── Chemins projet ────────────────────────────────────────────────────────────

def setup_project_paths():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    src_dir = project_root / "src"
    for p in [str(project_root), str(src_dir)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    return project_root

PROJECT_ROOT = setup_project_paths()


# ── Module geographique ───────────────────────────────────────────────────────

try:
    from src.utils.geographic_references import SenegalGeography
    GEOGRAPHY_AVAILABLE = True
    print("Module geographique avance importe")
except ImportError:
    GEOGRAPHY_AVAILABLE = False
    print("Module geographique basique utilise")

    class SenegalGeography:
        @staticmethod
        def identify_region(lat, lon):
            if lat > 15.5:
                return "Saint-Louis/Louga/Matam"
            elif lat > 14.5:
                return "Dakar/Thies/Diourbel"
            elif lat > 13.5:
                return "Kaolack/Fatick/Kaffrine/Tambacounda"
            else:
                return "Ziguinchor/Kolda/Sedhiou/Kedougou"

        @staticmethod
        def identify_climate_zone(lat, lon):
            if lat > 15.5:
                return "Zone sahelienne"
            elif lat > 13.5:
                return "Zone soudano-sahelienne"
            else:
                return "Zone soudanienne"


# ── Constantes ────────────────────────────────────────────────────────────────

SENEGAL_BOUNDS = {
    'lat_min': 12.3, 'lat_max': 16.7,
    'lon_min': -17.45, 'lon_max': -11.35
}

RAINFALL_PHASES = {
    'Phase_1_debut':  {'months': [5, 6],        'description': 'Debut de saison (Mai-Juin)'},
    'Phase_2_pleine': {'months': [7, 8],        'description': 'Pleine saison (Juillet-Aout)'},
    'Phase_3_fin':    {'months': [9, 10],       'description': 'Fin de saison (Septembre-Octobre)'},
    'Hors_saison':    {'months': [11,12,1,2,3,4], 'description': 'Saison seche'},
}

CRITERIA = {
    'plus_intense':           ('max_precip',        'idxmax'),
    'moins_intense':          ('max_precip',        'idxmin'),
    'plus_grande_couverture': ('coverage_percent',  'idxmax'),
    'plus_petite_couverture': ('coverage_percent',  'idxmin'),
}

MIN_OBS = 10  # minimum observations pour calculer une correlation


# ── Masque geometrique Senegal ────────────────────────────────────────────────

def build_boundary_paths(boundary_geojson: dict) -> list:
    paths = []
    for feature in boundary_geojson.get("features", []):
        geom = feature.get("geometry", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "MultiPolygon":
            for polygon in coords:
                if polygon and polygon[0]:
                    paths.append(MplPath(np.array(polygon[0])))
        elif gtype == "Polygon":
            if coords and coords[0]:
                paths.append(MplPath(np.array(coords[0])))
    return paths


def filter_points_in_senegal(lons: np.ndarray, lats: np.ndarray,
                              boundary_paths: list) -> np.ndarray:
    if not boundary_paths:
        return np.ones(len(lons), dtype=bool)
    points = np.column_stack([lons, lats])
    inside = np.zeros(len(lons), dtype=bool)
    for path in boundary_paths:
        inside |= path.contains_points(points)
    return inside


# Charger la geometrie au demarrage
_boundary_path = PROJECT_ROOT / "data" / "geographic" / "senegal_boundaries.geojson"
SENEGAL_BOUNDARY_PATHS = []
if _boundary_path.exists():
    with open(str(_boundary_path), "r", encoding="utf-8") as _f:
        _geojson = json.load(_f)
    SENEGAL_BOUNDARY_PATHS = build_boundary_paths(_geojson)
    print(f"Geometrie Senegal chargee : {len(SENEGAL_BOUNDARY_PATHS)} sous-polygone(s)")
else:
    print("AVERTISSEMENT : senegal_boundaries.geojson non trouve, filtrage geometrique desactive")


# ── Selection des evenements par cluster ──────────────────────────────────────

def load_cluster_events(clustering_dir: Path) -> Dict[str, pd.DataFrame]:
    """
    Charge tous les fichiers events_with_clusters.csv disponibles.
    Retourne un dict {phase_name -> DataFrame}.
    """
    phase_data = {}
    for phase_dir in clustering_dir.iterdir():
        if not phase_dir.is_dir():
            continue
        csv_file = phase_dir / f"{phase_dir.name}_events_with_clusters.csv"
        if not csv_file.exists():
            continue
        df = pd.read_csv(str(csv_file), encoding='utf-8')
        phase_data[phase_dir.name] = df
        print(f"  Phase {phase_dir.name}: {len(df)} evenements, "
              f"{df['cluster'].nunique()} clusters")
    return phase_data


def select_events_per_cluster(phase_data: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
    """
    Pour chaque phase et chaque cluster, selectionne les 4 evenements representatifs.

    Retourne un dict structure:
        {phase -> {cluster_id -> {criterion -> date_str}}}
    """
    selection = {}

    for phase, df in phase_data.items():
        selection[phase] = {}
        clusters = sorted(df['cluster'].unique())

        for cluster_id in clusters:
            df_c = df[df['cluster'] == cluster_id].copy()

            if len(df_c) < 2:
                print(f"  [{phase}] Cluster {cluster_id}: seulement {len(df_c)} "
                      f"evenement(s), skip")
                continue

            chosen = {}
            for criterion, (col, func) in CRITERIA.items():
                if col not in df_c.columns:
                    print(f"  [{phase}] Cluster {cluster_id}: colonne '{col}' manquante")
                    continue
                idx = getattr(df_c[col], func)()
                date_str = df_c.loc[idx, 'date']
                chosen[criterion] = date_str

            selection[phase][cluster_id] = chosen
            print(f"  [{phase}] Cluster {cluster_id} ({len(df_c)} evt): "
                  + ", ".join(f"{k}={v}" for k, v in chosen.items()))

    return selection


def build_target_list(selection: Dict[str, dict]) -> Tuple[List[str], Dict[str, list]]:
    """
    Construit la liste unique des dates a extraire et leur mapping
    date -> [(phase, cluster, criterion), ...]
    """
    date_meta: Dict[str, list] = {}

    for phase, clusters in selection.items():
        for cluster_id, criteria in clusters.items():
            for criterion, date_str in criteria.items():
                date_meta.setdefault(date_str, []).append(
                    (phase, cluster_id, criterion))

    unique_dates = list(date_meta.keys())
    return unique_dates, date_meta


# ── Extraction CHIRPS ─────────────────────────────────────────────────────────

class ClusterEventsExtractor:
    """Extrait les pixels CHIRPS pour les evenements representatifs par cluster."""

    def __init__(self, chirps_path: str, target_dates: List[str],
                 date_meta: Dict[str, list]):
        self.chirps_path = Path(chirps_path)
        self.target_dates = target_dates
        self.date_meta = date_meta
        self.geography = SenegalGeography()

        self.precip_data = None
        self.dates = None
        self.lats = None
        self.lons = None
        self.climatology = None
        self.std_dev = None

        print(f"\nClusterEventsExtractor initialise")
        print(f"  Fichier CHIRPS : {self.chirps_path}")
        print(f"  Dates uniques  : {len(self.target_dates)}")

        if not self.chirps_path.exists():
            raise FileNotFoundError(f"Fichier CHIRPS non trouve : {chirps_path}")

    # ── Chargement CHIRPS ─────────────────────────────────────────────────────

    def load_chirps_data(self) -> bool:
        print("\nCHARGEMENT CHIRPS")
        print("-" * 40)
        try:
            with h5py.File(str(self.chirps_path), 'r') as f:
                full_lat = np.array(f['latitude']).flatten()
                full_lon = np.array(f['longitude']).flatten()
                data_shape = f['precip'].shape
                print(f"  Shape complete : {data_shape}")

                lat_mask = ((full_lat >= SENEGAL_BOUNDS['lat_min']) &
                            (full_lat <= SENEGAL_BOUNDS['lat_max']))
                lon_mask = ((full_lon >= SENEGAL_BOUNDS['lon_min']) &
                            (full_lon <= SENEGAL_BOUNDS['lon_max']))

                self.lats = full_lat[lat_mask]
                self.lons = full_lon[lon_mask]

                chunk_size = 365
                total_days = data_shape[0]
                chunks = []

                print(f"  Chargement par chunks de {chunk_size} jours...")
                for start in range(0, total_days, chunk_size):
                    end = min(start + chunk_size, total_days)
                    chunk = f['precip'][start:end, :, :].astype(np.float32)
                    chunks.append(chunk[:, lat_mask, :][:, :, lon_mask])
                    del chunk

                self.precip_data = np.concatenate(chunks, axis=0)
                del chunks

                start_date = datetime(1981, 1, 1)
                self.dates = [start_date + timedelta(days=i) for i in range(total_days)]

                print(f"  Shape finale : {self.precip_data.shape}")
                print(f"  Periode : {self.dates[0].strftime('%Y-%m-%d')} "
                      f"a {self.dates[-1].strftime('%Y-%m-%d')}")
                return True

        except Exception as e:
            print(f"ERREUR chargement : {e}")
            return False

    # ── Climatologie ──────────────────────────────────────────────────────────

    def calculate_climatology(self) -> bool:
        print("\nCALCUL CLIMATOLOGIE")
        print("-" * 40)
        try:
            doy_array = np.array([d.timetuple().tm_yday for d in self.dates])
            n_lat, n_lon = self.precip_data.shape[1], self.precip_data.shape[2]
            self.climatology = np.zeros((366, n_lat, n_lon))
            self.std_dev = np.zeros((366, n_lat, n_lon))

            for day in range(1, 367):
                idx = np.where(doy_array == day)[0]
                if len(idx) > 0:
                    d = self.precip_data[idx]
                    self.climatology[day-1] = np.nanmean(d, axis=0)
                    sd = np.nanstd(d, axis=0, ddof=1)
                    self.std_dev[day-1] = np.where(
                        np.isnan(sd) | (sd < 0.01), 0.1, sd)

            print(f"  Climatologie calculee (366 jours x {n_lat} x {n_lon})")
            return True
        except Exception as e:
            print(f"ERREUR climatologie : {e}")
            return False

    # ── Extraction d'un evenement ─────────────────────────────────────────────

    def extract_event(self, date_str: str) -> pd.DataFrame:
        """Extrait les pixels CHIRPS pour une date donnee."""
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')

        # Trouver l'index temporel
        t_idx = None
        for i, d in enumerate(self.dates):
            if d.year == date_obj.year and d.month == date_obj.month and d.day == date_obj.day:
                t_idx = i
                break

        if t_idx is None:
            print(f"  Date non trouvee : {date_str}")
            return pd.DataFrame()

        day_precip = self.precip_data[t_idx]
        doy = date_obj.timetuple().tm_yday
        clim_day = self.climatology[doy-1]
        std_day = self.std_dev[doy-1]

        anomalies = np.divide(
            day_precip - clim_day, std_day,
            out=np.zeros_like(day_precip),
            where=(std_day > 0.01)
        )

        # Assembler les metadonnees pour cet evenement
        metas = self.date_meta.get(date_str, [])
        # Construire un label lisible (peut satisfaire plusieurs criteres)
        label_parts = []
        for (phase, cluster_id, criterion) in metas:
            label_parts.append(f"C{cluster_id}_{criterion}")
        selection_label = " + ".join(sorted(set(label_parts)))

        # Phase depuis le mois
        month = date_obj.month
        if month in [5, 6]:
            phase_key = 'Phase_1_debut'
        elif month in [7, 8]:
            phase_key = 'Phase_2_pleine'
        elif month in [9, 10]:
            phase_key = 'Phase_3_fin'
        else:
            phase_key = 'Hors_saison'

        rows = []
        for i, lat in enumerate(self.lats):
            for j, lon in enumerate(self.lons):
                pval = day_precip[i, j]
                if np.isnan(pval):
                    continue
                rows.append({
                    'event_date':            date_str,
                    'selection_label':       selection_label,
                    'pixel_id':              f"{date_str}_{i:03d}_{j:03d}",
                    'longitude':             float(lon),
                    'latitude':              float(lat),
                    'precipitation_mm':      float(pval),
                    'climatology_mm':        float(clim_day[i, j]),
                    'anomaly_standardized':  float(anomalies[i, j]),
                    'anomaly_mm':            float(pval - clim_day[i, j]),
                    'is_extreme':            bool(anomalies[i, j] > 2.0),
                    'is_intense':            bool(pval > 20.0),
                    'intensity_category':    self._cat_intensity(pval),
                    'anomaly_category':      self._cat_anomaly(anomalies[i, j]),
                    'year':                  date_obj.year,
                    'month':                 date_obj.month,
                    'day':                   date_obj.day,
                    'day_of_year':           doy,
                    'season_phase':          phase_key,
                    'phase_description':     RAINFALL_PHASES[phase_key]['description'],
                    'region':                self.geography.identify_region(lat, lon),
                    'climate_zone':          self.geography.identify_climate_zone(lat, lon),
                    'distance_to_coast_km':  abs(lon - (-17.5)) * 111.32 * np.cos(np.radians(lat)),
                })

        df = pd.DataFrame(rows)

        # Filtrage geometrique
        if len(df) > 0 and SENEGAL_BOUNDARY_PATHS:
            inside = filter_points_in_senegal(
                df['longitude'].values, df['latitude'].values,
                SENEGAL_BOUNDARY_PATHS)
            n_before = len(df)
            df = df[inside].reset_index(drop=True)
            if n_before - len(df) > 0:
                print(f"    Filtrage geo : {n_before - len(df)} pixels supprimes "
                      f"({len(df)}/{n_before} conserves)")

        if len(df) > 0:
            print(f"  {date_str} : {len(df)} pixels, "
                  f"max={df['precipitation_mm'].max():.1f}mm, "
                  f"couv.extrem={df['is_extreme'].sum()}")

        return df

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _cat_intensity(self, v: float) -> str:
        if v < 1:   return 'trace'
        if v < 5:   return 'faible'
        if v < 20:  return 'moderee'
        if v < 50:  return 'forte'
        if v < 100: return 'tres forte'
        return 'extreme'

    def _cat_anomaly(self, v: float) -> str:
        if v < -2:  return 'tres seche'
        if v < -1:  return 'seche'
        if v < 1:   return 'normale'
        if v < 2:   return 'humide'
        if v < 3:   return 'tres humide'
        return 'exceptionnelle'

    # ── Sauvegarde ────────────────────────────────────────────────────────────

    def save_results(self, selection: Dict[str, dict],
                     all_event_data: Dict[str, pd.DataFrame],
                     output_dir: Path):
        """Organise et sauvegarde les CSV par phase/cluster."""
        output_dir.mkdir(parents=True, exist_ok=True)
        generated = []
        all_combined = []

        QGIS_COLS = [
            'longitude', 'latitude', 'event_date', 'selection_label', 'pixel_id',
            'precipitation_mm', 'anomaly_standardized', 'climatology_mm',
            'is_extreme', 'is_intense', 'intensity_category', 'anomaly_category',
            'region', 'climate_zone', 'season_phase', 'phase_description',
            'year', 'month', 'day', 'day_of_year', 'distance_to_coast_km',
        ]

        for phase, clusters in selection.items():
            phase_dir = output_dir / phase
            phase_dir.mkdir(parents=True, exist_ok=True)

            phase_rows = []  # pour CSV recapitulatif de la phase

            for cluster_id, criteria in clusters.items():
                cluster_dir = phase_dir / f"cluster_{cluster_id}"
                cluster_dir.mkdir(parents=True, exist_ok=True)

                cluster_frames = []
                summary_rows = []

                for criterion, date_str in criteria.items():
                    df = all_event_data.get(date_str, pd.DataFrame())
                    if df.empty:
                        continue

                    # Fichier individuel
                    fname = (f"cluster{cluster_id}_{criterion}_"
                             f"{date_str.replace('-','')}_pixels.csv")
                    fpath = cluster_dir / fname
                    cols_avail = [c for c in QGIS_COLS if c in df.columns]
                    df[cols_avail].to_csv(str(fpath), index=False, encoding='utf-8')
                    generated.append(fpath)
                    print(f"  Sauvegarde : {fpath.name} ({len(df)} pixels)")

                    # Ajouter colonne cluster/criterion pour les fichiers combines
                    df_tag = df.copy()
                    df_tag['cluster'] = cluster_id
                    df_tag['criterion'] = criterion
                    df_tag['phase'] = phase
                    cluster_frames.append(df_tag)
                    all_combined.append(df_tag)

                    # Ligne recapitulative
                    summary_rows.append({
                        'phase':      phase,
                        'cluster':    cluster_id,
                        'criterion':  criterion,
                        'date':       date_str,
                        'n_pixels':   len(df),
                        'max_precip': df['precipitation_mm'].max(),
                        'mean_precip': df['precipitation_mm'].mean(),
                        'coverage_extreme_pct': df['is_extreme'].mean() * 100,
                        'max_anomaly': df['anomaly_standardized'].max(),
                        'n_extreme_pixels': int(df['is_extreme'].sum()),
                    })

                # CSV combine du cluster
                if cluster_frames:
                    comb = pd.concat(cluster_frames, ignore_index=True)
                    comb_path = cluster_dir / f"cluster{cluster_id}_all_events.csv"
                    comb.to_csv(str(comb_path), index=False, encoding='utf-8')
                    generated.append(comb_path)
                    print(f"  Combine cluster : {comb_path.name} ({len(comb)} pixels)")

                # CSV recapitulatif du cluster
                if summary_rows:
                    sum_df = pd.DataFrame(summary_rows)
                    sum_path = cluster_dir / f"cluster{cluster_id}_summary.csv"
                    sum_df.to_csv(str(sum_path), index=False, encoding='utf-8')
                    generated.append(sum_path)
                    phase_rows.extend(summary_rows)

            # CSV recapitulatif de la phase
            if phase_rows:
                phase_sum = pd.DataFrame(phase_rows)
                psum_path = phase_dir / f"{phase}_clusters_summary.csv"
                phase_sum.to_csv(str(psum_path), index=False, encoding='utf-8')
                generated.append(psum_path)
                print(f"  Recap phase : {psum_path.name}")

        # CSV global toutes phases / tous clusters
        if all_combined:
            global_df = pd.concat(all_combined, ignore_index=True)
            global_path = output_dir / "all_cluster_events_combined.csv"
            global_df.to_csv(str(global_path), index=False, encoding='utf-8')
            generated.append(global_path)
            print(f"\nFichier global : {global_path.name} ({len(global_df)} pixels)")

        # Metadonnees
        metadata = {
            'title': 'Evenements representatifs par cluster - Senegal',
            'source': 'CHIRPS v2.0',
            'selection_criteria': list(CRITERIA.keys()),
            'coordinate_system': 'WGS84 (EPSG:4326)',
            'created_at': datetime.now().isoformat(),
            'files_generated': [str(p) for p in generated],
        }
        meta_path = output_dir / "metadata.json"
        with open(str(meta_path), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        generated.append(meta_path)

        print(f"\n{len(generated)} fichiers generes dans {output_dir.absolute()}")
        return generated

    # ── Pipeline principal ────────────────────────────────────────────────────

    def run(self, selection: Dict[str, dict], output_dir: Path) -> bool:
        if not self.load_chirps_data():
            return False
        if not self.calculate_climatology():
            return False

        # Extraire chaque date unique (une seule fois)
        print("\nEXTRACTION DES EVENEMENTS")
        print("-" * 40)
        all_event_data = {}
        for date_str in self.target_dates:
            df = self.extract_event(date_str)
            if not df.empty:
                all_event_data[date_str] = df

        if not all_event_data:
            print("ERREUR : aucune donnee extraite")
            return False

        print("\nSAUVEGARDE")
        print("-" * 40)
        self.save_results(selection, all_event_data, output_dir)
        return True


# ── Main ──────────────────────────────────────────────────────────────────────

def find_chirps_file() -> str:
    candidates = [
        "data/raw/chirps_WA_1981_2023_dayly.mat",
        "data/chirps_WA_1981_2023_dayly.mat",
        "chirps_WA_1981_2023_dayly.mat",
        str(Path(__file__).parent.parent / "data" / "raw" / "chirps_WA_1981_2023_dayly.mat"),
    ]
    # Recherche recursive dans le projet
    project_dir = Path(__file__).parent.parent
    for pattern in ["**/chirps*.mat", "**/*chirps*.mat"]:
        for found in project_dir.glob(pattern):
            if found.is_file():
                candidates.append(str(found))
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


def main():
    print("EXTRACTION D'EVENEMENTS PAR CLUSTER POUR QGIS")
    print("=" * 55)

    # ── Fichier CHIRPS ────────────────────────────────────────────────────────
    chirps_path = sys.argv[1] if len(sys.argv) > 1 else find_chirps_file()
    if not chirps_path:
        print("ERREUR : fichier CHIRPS non trouve.")
        print("Usage : py -3 scripts/03c_filter_events_by_cluster_for_qgis.py [chirps.mat]")
        return False

    print(f"Fichier CHIRPS : {chirps_path}")

    # ── Chargement des clusters ───────────────────────────────────────────────
    clustering_dir = PROJECT_ROOT / "outputs" / "clustering"
    if not clustering_dir.exists():
        print(f"ERREUR : dossier clustering introuvable : {clustering_dir}")
        return False

    print("\nCHARGEMENT DES DONNEES DE CLUSTERING")
    print("-" * 40)
    phase_data = load_cluster_events(clustering_dir)

    if not phase_data:
        print("ERREUR : aucun fichier events_with_clusters.csv trouve")
        return False

    # ── Selection des evenements representatifs ───────────────────────────────
    print("\nSELECTION DES EVENEMENTS REPRESENTATIFS PAR CLUSTER")
    print("-" * 55)
    selection = select_events_per_cluster(phase_data)

    target_dates, date_meta = build_target_list(selection)
    print(f"\nTotal dates uniques a extraire : {len(target_dates)}")

    # ── Extraction et sauvegarde ──────────────────────────────────────────────
    output_dir = PROJECT_ROOT / "outputs" / "cluster_events_qgis"

    extractor = ClusterEventsExtractor(chirps_path, target_dates, date_meta)
    success = extractor.run(selection, output_dir)

    if success:
        print("\nEXTRACTION TERMINEE")
        print(f"Resultats dans : {output_dir.absolute()}")
        print("\nUtilisation QGIS :")
        print("  1. Couche > Ajouter couche > Texte delimite")
        print("  2. Champs X=longitude, Y=latitude")
        print("  3. SCR : WGS84 (EPSG:4326)")
        print("  4. Styliser par precipitation_mm ou anomaly_standardized")
    else:
        print("\nECHEC DE L'EXTRACTION")

    return success


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        import traceback
        print(f"\nERREUR : {e}")
        traceback.print_exc()
        sys.exit(2)
