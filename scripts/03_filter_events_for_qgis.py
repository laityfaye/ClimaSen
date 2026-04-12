#!/usr/bin/env python3
"""
Script d'extraction d'événements pluviométriques spécifiques pour cartographie QGIS.

Ce script extrait directement depuis les données CHIRPS brutes les événements suivants :
- 1985-08-06 (Événement historique)
- 2009-08-28 (Événement de pleine saison)
- 2012-09-28 (Événement de fin de saison)
- 2000-10-16 (Événement tardif)
- 2022-05-27 (Événement précoce)

Sortie : Fichiers CSV prêts pour l'import dans QGIS avec :
- Coordonnées géographiques
- Valeurs de précipitation
- Anomalies standardisées
- Informations géographiques (régions, départements)
- Classification par phases de saison des pluies

Utilisation:
    python scripts/extract_specific_events_qgis.py

Auteur: Équipe de recherche climatologique
Date: 2025-01-XX
Version: 1.0
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
from typing import List, Dict, Tuple, Any
from matplotlib.path import Path as MplPath

# Configuration des warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=UserWarning)


# ─── Masque geometrique Senegal ───────────────────────────────────────────────

def build_boundary_paths(boundary_geojson: dict) -> list:
    """
    Construit des objets matplotlib.path.Path depuis un GeoJSON MultiPolygon/Polygon.
    Chaque path correspond a un sous-polygone (ile, enclave, etc.).
    """
    paths = []
    for feature in boundary_geojson.get("features", []):
        geom = feature.get("geometry", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])

        if gtype == "MultiPolygon":
            for polygon in coords:
                if polygon and polygon[0]:
                    ring = np.array(polygon[0])  # anneau exterieur [lon, lat]
                    paths.append(MplPath(ring))
        elif gtype == "Polygon":
            if coords and coords[0]:
                ring = np.array(coords[0])
                paths.append(MplPath(ring))

    return paths


def filter_points_in_senegal(lons: np.ndarray, lats: np.ndarray,
                              boundary_paths: list) -> np.ndarray:
    """
    Retourne un masque boolen : True si le point (lon, lat) est
    a l'interieur du Senegal (union de tous les sous-polygones).
    Utilise contains_points() vectorise pour la performance.
    """
    if not boundary_paths:
        # Pas de geometrie disponible : on garde tous les points
        return np.ones(len(lons), dtype=bool)

    points = np.column_stack([lons, lats])  # shape (N, 2) en (lon, lat)
    inside = np.zeros(len(lons), dtype=bool)
    for path in boundary_paths:
        inside |= path.contains_points(points)
    return inside


# Configuration des chemins
def setup_project_paths():
    """Configure les chemins du projet."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    src_dir = project_root / "src"
    
    for path_str in [str(project_root), str(src_dir)]:
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    
    return project_root

PROJECT_ROOT = setup_project_paths()

# Import des modules géographiques avec fallback
try:
    from src.utils.geographic_references import SenegalGeography
    GEOGRAPHY_AVAILABLE = True
    print("✅ Module géographique avancé importé")
except ImportError:
    GEOGRAPHY_AVAILABLE = False
    print("⚠️ Module géographique basique utilisé")
    
    class SenegalGeography:
        @staticmethod
        def identify_region(lat, lon):
            """Identification basique des régions."""
            if lat > 15.5:
                return "Saint-Louis/Louga/Matam"
            elif lat > 14.5:
                return "Dakar/Thiès/Diourbel"
            elif lat > 13.5:
                return "Kaolack/Fatick/Kaffrine/Tambacounda"
            else:
                return "Ziguinchor/Kolda/Sédhiou/Kédougou"
        
        @staticmethod
        def identify_climate_zone(lat, lon):
            """Identification basique des zones climatiques."""
            if lat > 15.5:
                return "Zone sahélienne"
            elif lat > 13.5:
                return "Zone soudano-sahélienne"
            else:
                return "Zone soudanienne"

# Labels des criteres de selection (date -> label)
EVENT_LABELS = {}

def select_target_events_from_catalog(catalog_path: str) -> tuple:
    """
    Selectionne automatiquement 6 evenements representatifs depuis le catalogue.

    Criteres:
    - Plus intense        : max_precip le plus eleve
    - Moins intense       : max_precip le plus faible (>0)
    - Plus grande couverture spatiale : coverage_percent max
    - Plus petite couverture spatiale : coverage_percent min
    - Plus grande anomalie : max_anomaly max
    - Plus petite anomalie : max_anomaly min (>0)
    """
    try:
        df_cat = pd.read_csv(catalog_path, encoding='utf-8')

        # Filtrer les evenements avec precipitation > 0
        df_valid = df_cat[df_cat['max_precip'] > 0].copy()

        criteria = {
            'plus_intense':           df_valid.loc[df_valid['max_precip'].idxmax(), 'date'],
            'moins_intense':          df_valid.loc[df_valid['max_precip'].idxmin(), 'date'],
            'plus_grande_couverture': df_valid.loc[df_valid['coverage_percent'].idxmax(), 'date'],
            'plus_petite_couverture': df_valid.loc[df_valid['coverage_percent'].idxmin(), 'date'],
            'plus_grande_anomalie':   df_valid.loc[df_valid['max_anomaly'].idxmax(), 'date'],
            'plus_petite_anomalie':   df_valid.loc[df_valid['max_anomaly'].idxmin(), 'date'],
        }

        # Regrouper les criteres par date (un evenement peut satisfaire plusieurs criteres)
        seen = {}
        for criterion, date in criteria.items():
            seen.setdefault(date, []).append(criterion)

        labels = {date: ' + '.join(crits) for date, crits in seen.items()}

        print("\nEVENEMENTS SELECTIONNES AUTOMATIQUEMENT DEPUIS LE CATALOGUE:")
        print("-" * 60)
        for criterion, date in criteria.items():
            row = df_valid[df_valid['date'] == date].iloc[0]
            print(f"  [{criterion}] {date}")
            print(f"    max_precip={row['max_precip']:.1f}mm  "
                  f"coverage={row['coverage_percent']:.1f}%  "
                  f"max_anomaly={row['max_anomaly']:.2f}sigma  "
                  f"phase={row['phase']}")

        unique_dates = list(seen.keys())
        print(f"\n  Total evenements uniques a extraire: {len(unique_dates)}")

        return unique_dates, labels

    except Exception as e:
        print(f"ERREUR selection catalogue: {e}")
        import traceback
        traceback.print_exc()
        # Fallback vers les evenements hardcodes
        fallback = ['1985-08-06', '2009-08-28', '2012-09-28', '2000-10-16', '2022-05-27']
        fallback_labels = {d: 'selection_manuelle' for d in fallback}
        return fallback, fallback_labels


# Chargement du catalogue et selection dynamique des evenements cibles
_catalog_path = Path(__file__).parent.parent / "data" / "processed" / "extreme_events_phases_senegal.csv"
TARGET_EVENTS, EVENT_LABELS = select_target_events_from_catalog(str(_catalog_path))

# Chargement de la geometrie Senegal (masque point-dans-polygone)
_boundary_path = Path(__file__).parent.parent / "data" / "geographic" / "senegal_boundaries.geojson"
SENEGAL_BOUNDARY_PATHS = []
if _boundary_path.exists():
    with open(str(_boundary_path), "r", encoding="utf-8") as _f:
        _boundary_geojson = json.load(_f)
    SENEGAL_BOUNDARY_PATHS = build_boundary_paths(_boundary_geojson)
    print(f"Geometrie Senegal chargee : {len(SENEGAL_BOUNDARY_PATHS)} sous-polygone(s)")
else:
    print("AVERTISSEMENT : senegal_boundaries.geojson non trouve, filtrage geometrique desactive")

# Configuration géographique Sénégal
SENEGAL_BOUNDS = {
    'lat_min': 12.3, 'lat_max': 16.7,
    'lon_min': -17.45, 'lon_max': -11.35
}

# Classification par phases de saison des pluies
RAINFALL_PHASES = {
    'Phase_1_debut': {'months': [5, 6], 'description': 'Début de saison (Mai-Juin)'},
    'Phase_2_pleine': {'months': [7, 8], 'description': 'Pleine saison (Juillet-Août)'},
    'Phase_3_fin': {'months': [9, 10], 'description': 'Fin de saison (Septembre-Octobre)'},
    'Hors_saison': {'months': [11, 12, 1, 2, 3, 4], 'description': 'Saison sèche'}
}

def get_phase_from_month(month: int) -> str:
    """Détermine la phase de saison des pluies à partir du mois."""
    if month in [5, 6]:
        return 'Phase_1_debut'
    elif month in [7, 8]:
        return 'Phase_2_pleine'
    elif month in [9, 10]:
        return 'Phase_3_fin'
    else:
        return 'Hors_saison'


class SpecificEventsExtractor:
    """
    Extracteur spécialisé pour les événements ciblés avec sortie QGIS.
    """
    
    def __init__(self, chirps_file_path: str):
        """
        Initialise l'extracteur.
        
        Args:
            chirps_file_path (str): Chemin vers le fichier CHIRPS
        """
        self.chirps_file_path = Path(chirps_file_path)
        self.target_events = [datetime.strptime(date, '%Y-%m-%d') for date in TARGET_EVENTS]
        self.event_labels = EVENT_LABELS
        self.geography = SenegalGeography()
        
        # Données chargées
        self.precip_data = None
        self.dates = None
        self.lats = None
        self.lons = None
        self.climatology = None
        self.std_dev = None
        
        print(f"🎯 SpecificEventsExtractor initialisé")
        print(f"   Fichier CHIRPS: {self.chirps_file_path}")
        print(f"   Événements ciblés: {len(self.target_events)}")
        
        if not self.chirps_file_path.exists():
            raise FileNotFoundError(f"Fichier CHIRPS non trouvé: {chirps_file_path}")
    
    def load_chirps_data(self) -> bool:
        """
        Charge les données CHIRPS pour le Sénégal.
        
        Returns:
            bool: Succès du chargement
        """
        print("\n🔄 CHARGEMENT DES DONNÉES CHIRPS")
        print("-" * 50)
        
        try:
            with h5py.File(self.chirps_file_path, 'r') as f:
                print(f"📂 Clés disponibles: {list(f.keys())}")
                
                # Charger les coordonnées complètes
                full_latitude = np.array(f['latitude']).flatten()
                full_longitude = np.array(f['longitude']).flatten()
                data_shape = f['precip'].shape
                
                print(f"   Shape complète: {data_shape}")
                print(f"   Période: {data_shape[0]} jours")
                
                # Masques pour extraire le Sénégal
                lat_mask = ((full_latitude >= SENEGAL_BOUNDS['lat_min']) & 
                           (full_latitude <= SENEGAL_BOUNDS['lat_max']))
                lon_mask = ((full_longitude >= SENEGAL_BOUNDS['lon_min']) & 
                           (full_longitude <= SENEGAL_BOUNDS['lon_max']))
                
                self.lats = full_latitude[lat_mask]
                self.lons = full_longitude[lon_mask]
                
                print(f"🗺️ Zone Sénégal:")
                print(f"   Latitudes: {len(self.lats)} points ({self.lats.min():.2f}°N à {self.lats.max():.2f}°N)")
                print(f"   Longitudes: {len(self.lons)} points ({abs(self.lons.max()):.2f}°W à {abs(self.lons.min()):.2f}°W)")
                
                # Charger les données de précipitation par chunks
                chunk_size = 365  # Une année à la fois
                total_days = data_shape[0]
                senegal_chunks = []
                
                print(f"📦 Chargement par chunks de {chunk_size} jours...")
                
                for start_idx in range(0, total_days, chunk_size):
                    end_idx = min(start_idx + chunk_size, total_days)
                    print(f"   Chunk: jours {start_idx+1}-{end_idx}")
                    
                    chunk_data = f['precip'][start_idx:end_idx, :, :].astype(np.float32)
                    senegal_chunk = chunk_data[:, lat_mask, :][:, :, lon_mask]
                    senegal_chunks.append(senegal_chunk)
                    
                    del chunk_data
                
                # Assembler les données
                self.precip_data = np.concatenate(senegal_chunks, axis=0)
                del senegal_chunks
                
                # Générer les dates
                start_date = datetime(1981, 1, 1)
                self.dates = [start_date + timedelta(days=i) for i in range(total_days)]
                
                print(f"✅ Données chargées:")
                print(f"   Shape finale: {self.precip_data.shape}")
                print(f"   Mémoire: {self.precip_data.nbytes / (1024**2):.1f} MB")
                print(f"   Période: {self.dates[0].strftime('%Y-%m-%d')} à {self.dates[-1].strftime('%Y-%m-%d')}")
                
                return True
                
        except Exception as e:
            print(f"❌ Erreur chargement: {e}")
            return False
    
    def calculate_climatology(self) -> bool:
        """
        Calcule la climatologie et les anomalies standardisées.
        
        Returns:
            bool: Succès du calcul
        """
        print("\n🔬 CALCUL DE LA CLIMATOLOGIE")
        print("-" * 40)
        
        try:
            # Calculer jour par jour de l'année (1-366)
            doy_array = np.array([d.timetuple().tm_yday for d in self.dates])
            n_days = 366  # Incluant année bissextile
            n_lat, n_lon = self.precip_data.shape[1], self.precip_data.shape[2]
            
            self.climatology = np.zeros((n_days, n_lat, n_lon))
            self.std_dev = np.zeros((n_days, n_lat, n_lon))
            
            print(f"📊 Calcul pour {n_days} jours de l'année...")
            
            for day in range(1, n_days + 1):
                # Indices pour ce jour de l'année
                day_indices = np.where(doy_array == day)[0]
                
                if len(day_indices) > 0:
                    day_data = self.precip_data[day_indices, :, :]
                    
                    # Moyenne et écart-type
                    self.climatology[day-1, :, :] = np.nanmean(day_data, axis=0)
                    self.std_dev[day-1, :, :] = np.nanstd(day_data, axis=0, ddof=1)
                    
                    # Éviter division par zéro
                    self.std_dev[day-1, :, :] = np.where(
                        np.isnan(self.std_dev[day-1, :, :]) | (self.std_dev[day-1, :, :] < 0.01),
                        0.1,
                        self.std_dev[day-1, :, :]
                    )
            
            print(f"✅ Climatologie calculée")
            print(f"   Précipitation climatologique moyenne: {np.nanmean(self.climatology):.2f} mm")
            print(f"   Écart-type moyen: {np.nanmean(self.std_dev):.2f} mm")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur climatologie: {e}")
            return False
    
    def find_event_indices(self) -> Dict[str, int]:
        """
        Trouve les indices temporels des événements ciblés.
        
        Returns:
            Dict[str, int]: Mapping date -> index
        """
        print("\n🎯 LOCALISATION DES ÉVÉNEMENTS CIBLÉS")
        print("-" * 45)
        
        event_indices = {}
        
        for target_date in self.target_events:
            # Chercher la date exacte
            for i, date in enumerate(self.dates):
                if (date.year == target_date.year and 
                    date.month == target_date.month and 
                    date.day == target_date.day):
                    event_indices[target_date.strftime('%Y-%m-%d')] = i
                    print(f"✅ {target_date.strftime('%Y-%m-%d')}: index {i}")
                    break
            else:
                print(f"❌ {target_date.strftime('%Y-%m-%d')}: non trouvé")
        
        print(f"\n📊 Événements localisés: {len(event_indices)}/{len(self.target_events)}")
        return event_indices
    
    def extract_event_data(self, event_date: str, event_index: int) -> pd.DataFrame:
        """
        Extrait les données détaillées pour un événement spécifique.
        
        Args:
            event_date (str): Date de l'événement
            event_index (int): Index temporel
            
        Returns:
            pd.DataFrame: Données de l'événement pour QGIS
        """
        print(f"\n📊 EXTRACTION: {event_date}")
        print("-" * 30)
        
        # Données du jour
        day_precip = self.precip_data[event_index, :, :]
        
        # Calculer les anomalies
        date_obj = datetime.strptime(event_date, '%Y-%m-%d')
        doy = date_obj.timetuple().tm_yday
        
        if doy <= len(self.climatology):
            climatology_day = self.climatology[doy-1, :, :]
            std_day = self.std_dev[doy-1, :, :]
            
            # Anomalies standardisées
            anomalies = np.divide(
                day_precip - climatology_day,
                std_day,
                out=np.zeros_like(day_precip),
                where=(std_day > 0.01)
            )
        else:
            climatology_day = np.zeros_like(day_precip)
            anomalies = np.zeros_like(day_precip)
        
        # Créer le DataFrame pour chaque pixel
        data_rows = []
        
        for i, lat in enumerate(self.lats):
            for j, lon in enumerate(self.lons):
                # Valeurs pour ce pixel
                precip_val = day_precip[i, j]
                clim_val = climatology_day[i, j]
                anomaly_val = anomalies[i, j]
                
                # Passer les NaN
                if np.isnan(precip_val):
                    continue
                
                # Informations géographiques
                region = self.geography.identify_region(lat, lon)
                climate_zone = self.geography.identify_climate_zone(lat, lon)
                
                # Classification par phase
                phase = get_phase_from_month(date_obj.month)
                phase_description = RAINFALL_PHASES[phase]['description']
                
                # Critere de selection de cet evenement
                selection_criterion = self.event_labels.get(event_date, 'selection_manuelle')

                # Créer la ligne de données
                row = {
                    # Identifiants
                    'event_date': event_date,
                    'selection_criterion': selection_criterion,
                    'pixel_id': f"{event_date}_{i:03d}_{j:03d}",
                    
                    # Coordonnées géographiques (QGIS)
                    'longitude': float(lon),
                    'latitude': float(lat),
                    'grid_i': int(i),
                    'grid_j': int(j),
                    
                    # Données météorologiques
                    'precipitation_mm': float(precip_val),
                    'climatology_mm': float(clim_val),
                    'anomaly_standardized': float(anomaly_val),
                    'anomaly_mm': float(precip_val - clim_val),
                    
                    # Classifications
                    'is_extreme': bool(anomaly_val > 2.0),
                    'is_intense': bool(precip_val > 20.0),
                    'intensity_category': self._categorize_intensity(precip_val),
                    'anomaly_category': self._categorize_anomaly(anomaly_val),
                    
                    # Informations temporelles
                    'year': int(date_obj.year),
                    'month': int(date_obj.month),
                    'day': int(date_obj.day),
                    'day_of_year': int(doy),
                    'season_phase': phase,
                    'phase_description': phase_description,
                    
                    # Informations géographiques
                    'region': region,
                    'climate_zone': climate_zone,
                    
                    # Métriques pour visualisation
                    'precip_percentile': self._calculate_percentile(precip_val, day_precip),
                    'anomaly_percentile': self._calculate_percentile(anomaly_val, anomalies),
                    
                    # Coordonnées pour calculs
                    'utm_zone': '28N',  # Zone UTM du Sénégal
                    'distance_to_coast': self._distance_to_coast(lat, lon),
                }
                
                data_rows.append(row)

        df = pd.DataFrame(data_rows)

        # ── Filtrage geometrique : garder uniquement les pixels dans le Senegal ──
        if len(df) > 0 and SENEGAL_BOUNDARY_PATHS:
            lons_arr = df["longitude"].values
            lats_arr = df["latitude"].values
            inside_mask = filter_points_in_senegal(lons_arr, lats_arr,
                                                   SENEGAL_BOUNDARY_PATHS)
            n_before = len(df)
            df = df[inside_mask].reset_index(drop=True)
            n_removed = n_before - len(df)
            if n_removed > 0:
                print(f"   Filtrage geometrique : {n_removed} pixels hors Senegal supprimes "
                      f"({len(df)}/{n_before} conserves)")

        # Statistiques de l'événement
        if len(df) > 0:
            extreme_pixels = (df['anomaly_standardized'] > 2.0).sum()
            intense_pixels = (df['precipitation_mm'] > 20.0).sum()
            max_precip = df['precipitation_mm'].max()
            max_anomaly = df['anomaly_standardized'].max()
            mean_precip = df['precipitation_mm'].mean()
            
            print(f"   📍 Pixels extraits: {len(df)}")
            print(f"   🌧️ Précipitation max: {max_precip:.1f} mm")
            print(f"   📊 Précipitation moyenne: {mean_precip:.2f} mm")
            print(f"   ⚡ Pixels extrêmes (>2σ): {extreme_pixels}")
            print(f"   💧 Pixels intenses (>20mm): {intense_pixels}")
            print(f"   📈 Anomalie max: {max_anomaly:.2f}σ")
            print(f"   🏛️ Régions touchées: {df['region'].nunique()}")
        
        return df
    
    def _categorize_intensity(self, precip: float) -> str:
        """Catégorise l'intensité de précipitation."""
        if precip < 1:
            return 'trace'
        elif precip < 5:
            return 'faible'
        elif precip < 20:
            return 'modérée'
        elif precip < 50:
            return 'forte'
        elif precip < 100:
            return 'très forte'
        else:
            return 'extrême'
    
    def _categorize_anomaly(self, anomaly: float) -> str:
        """Catégorise l'anomalie standardisée."""
        if anomaly < -2:
            return 'très sèche'
        elif anomaly < -1:
            return 'sèche'
        elif anomaly < 1:
            return 'normale'
        elif anomaly < 2:
            return 'humide'
        elif anomaly < 3:
            return 'très humide'
        else:
            return 'exceptionelle'
    
    def _calculate_percentile(self, value: float, array: np.ndarray) -> float:
        """Calcule le percentile d'une valeur dans un array."""
        valid_array = array[~np.isnan(array)]
        if len(valid_array) == 0:
            return 50.0
        return float(np.percentile(valid_array, 100 * np.sum(valid_array <= value) / len(valid_array)))
    
    def _distance_to_coast(self, lat: float, lon: float) -> float:
        """Estime la distance approximative à la côte (en km)."""
        # Approximation simple basée sur la longitude (côte ouest)
        coast_lon = -17.5  # Longitude approximative de la côte
        distance_deg = abs(lon - coast_lon)
        # Conversion approximative en km
        distance_km = distance_deg * 111.32 * np.cos(np.radians(lat))
        return float(distance_km)
    
    def create_summary_statistics(self, all_events_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Crée un résumé statistique des événements.
        
        Args:
            all_events_data (Dict[str, pd.DataFrame]): Données de tous les événements
            
        Returns:
            pd.DataFrame: Résumé statistique
        """
        print("\n📈 CRÉATION DU RÉSUMÉ STATISTIQUE")
        print("-" * 40)
        
        summary_rows = []
        
        for event_date, df in all_events_data.items():
            if df.empty:
                continue
            
            date_obj = datetime.strptime(event_date, '%Y-%m-%d')
            phase = get_phase_from_month(date_obj.month)
            
            # Calculs statistiques
            extreme_pixels = (df['anomaly_standardized'] > 2.0).sum()
            intense_pixels = (df['precipitation_mm'] > 20.0).sum()
            total_pixels = len(df)
            
            # Statistiques de précipitation
            precip_stats = df['precipitation_mm'].describe()
            anomaly_stats = df['anomaly_standardized'].describe()
            
            # Analyse spatiale
            regions_affected = df['region'].nunique()
            main_region = df['region'].mode().iloc[0] if len(df) > 0 else 'Inconnue'
            
            # Centroïde pondéré par l'intensité
            if total_pixels > 0:
                weights = df['precipitation_mm'].values
                centroid_lat = np.average(df['latitude'].values, weights=weights)
                centroid_lon = np.average(df['longitude'].values, weights=weights)
            else:
                centroid_lat = centroid_lon = np.nan
            
            summary_row = {
                'event_date': event_date,
                'year': int(date_obj.year),
                'month': int(date_obj.month),
                'day': int(date_obj.day),
                'season_phase': phase,
                'phase_description': RAINFALL_PHASES[phase]['description'],
                
                # Couverture spatiale
                'total_pixels': int(total_pixels),
                'extreme_pixels': int(extreme_pixels),
                'intense_pixels': int(intense_pixels),
                'extreme_percentage': float(extreme_pixels / total_pixels * 100) if total_pixels > 0 else 0,
                'intense_percentage': float(intense_pixels / total_pixels * 100) if total_pixels > 0 else 0,
                
                # Statistiques de précipitation
                'precip_mean': float(precip_stats['mean']),
                'precip_median': float(precip_stats['50%']),
                'precip_max': float(precip_stats['max']),
                'precip_std': float(precip_stats['std']),
                'precip_p95': float(df['precipitation_mm'].quantile(0.95)),
                
                # Statistiques d'anomalie
                'anomaly_mean': float(anomaly_stats['mean']),
                'anomaly_median': float(anomaly_stats['50%']),
                'anomaly_max': float(anomaly_stats['max']),
                'anomaly_std': float(anomaly_stats['std']),
                
                # Analyse géographique
                'regions_affected': int(regions_affected),
                'main_region': main_region,
                'centroid_lat': float(centroid_lat) if not np.isnan(centroid_lat) else None,
                'centroid_lon': float(centroid_lon) if not np.isnan(centroid_lon) else None,
                
                # Classification qualitative
                'event_type': self._classify_event_type(extreme_pixels, intense_pixels, total_pixels),
                'spatial_extent': self._classify_spatial_extent(total_pixels),
                'intensity_level': self._classify_intensity_level(precip_stats['max']),
            }
            
            summary_rows.append(summary_row)
        
        summary_df = pd.DataFrame(summary_rows)
        
        if len(summary_df) > 0:
            print(f"✅ Résumé créé pour {len(summary_df)} événements")
            print(f"   Phases représentées: {summary_df['season_phase'].nunique()}")
            print(f"   Années couvertes: {summary_df['year'].nunique()}")
        
        return summary_df
    
    def _classify_event_type(self, extreme_pixels: int, intense_pixels: int, total_pixels: int) -> str:
        """Classifie le type d'événement."""
        if total_pixels == 0:
            return 'inconnu'
        
        extreme_pct = extreme_pixels / total_pixels * 100
        intense_pct = intense_pixels / total_pixels * 100
        
        if extreme_pct > 20:
            return 'exceptionnellement extrême'
        elif extreme_pct > 10:
            return 'très extrême'
        elif extreme_pct > 5:
            return 'extrême'
        elif intense_pct > 30:
            return 'très intense'
        elif intense_pct > 15:
            return 'intense'
        else:
            return 'modéré'
    
    def _classify_spatial_extent(self, total_pixels: int) -> str:
        """Classifie l'étendue spatiale."""
        if total_pixels > 5000:
            return 'très étendu'
        elif total_pixels > 2000:
            return 'étendu'
        elif total_pixels > 500:
            return 'modéré'
        else:
            return 'localisé'
    
    def _classify_intensity_level(self, max_precip: float) -> str:
        """Classifie le niveau d'intensité maximum."""
        if max_precip > 150:
            return 'catastrophique'
        elif max_precip > 100:
            return 'très élevé'
        elif max_precip > 50:
            return 'élevé'
        elif max_precip > 20:
            return 'modéré'
        else:
            return 'faible'
    
    def save_to_csv(self, all_events_data: Dict[str, pd.DataFrame], 
                    summary_df: pd.DataFrame, output_dir: Path) -> Dict[str, str]:
        """
        Sauvegarde toutes les données au format CSV pour QGIS.
        
        Args:
            all_events_data (Dict[str, pd.DataFrame]): Données détaillées par événement
            summary_df (pd.DataFrame): Résumé statistique
            output_dir (Path): Dossier de sortie
            
        Returns:
            Dict[str, str]: Chemins des fichiers générés
        """
        print("\n💾 SAUVEGARDE AU FORMAT CSV")
        print("-" * 35)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files = {}
        
        try:
            # 1. Fichiers individuels par événement
            for event_date, df in all_events_data.items():
                if df.empty:
                    continue

                # Construire le nom de fichier avec le critere de selection
                criterion_label = self.event_labels.get(event_date, 'selection_manuelle')
                # Nettoyer le label pour le nom de fichier (pas d'espaces ni de '+')
                criterion_slug = criterion_label.replace(' + ', '_').replace(' ', '_')
                filename = f"event_{criterion_slug}_{event_date.replace('-', '')}_pixels.csv"
                filepath = output_dir / filename

                # Réorganiser les colonnes pour QGIS
                qgis_columns = [
                    'longitude', 'latitude',  # Coordonnées en premier pour QGIS
                    'event_date', 'selection_criterion', 'pixel_id',
                    'precipitation_mm', 'anomaly_standardized', 'climatology_mm',
                    'is_extreme', 'is_intense', 'intensity_category', 'anomaly_category',
                    'region', 'climate_zone', 'season_phase', 'phase_description',
                    'year', 'month', 'day', 'day_of_year',
                    'precip_percentile', 'anomaly_percentile', 'distance_to_coast'
                ]
                
                df_qgis = df[qgis_columns].copy()
                df_qgis.to_csv(filepath, index=False, encoding='utf-8')
                
                generated_files[f'event_{event_date}'] = str(filepath)
                print(f"   ✅ {filename}: {len(df)} pixels")
            
            # 2. Fichier combiné de tous les événements
            if all_events_data:
                combined_df = pd.concat(all_events_data.values(), ignore_index=True)
                combined_path = output_dir / "all_specific_events_pixels.csv"
                
                qgis_columns = [
                    'longitude', 'latitude',  # Coordonnées en premier
                    'event_date', 'selection_criterion', 'pixel_id',
                    'precipitation_mm', 'anomaly_standardized', 'climatology_mm',
                    'is_extreme', 'is_intense', 'intensity_category', 'anomaly_category',
                    'region', 'climate_zone', 'season_phase', 'phase_description',
                    'year', 'month', 'day', 'day_of_year',
                    'precip_percentile', 'anomaly_percentile', 'distance_to_coast'
                ]
                
                combined_df_qgis = combined_df[qgis_columns].copy()
                combined_df_qgis.to_csv(combined_path, index=False, encoding='utf-8')
                
                generated_files['all_events_combined'] = str(combined_path)
                print(f"   ✅ all_specific_events_pixels.csv: {len(combined_df)} pixels")
            
            # 3. Résumé statistique des événements
            if not summary_df.empty:
                summary_path = output_dir / "events_summary_statistics.csv"
                summary_df.to_csv(summary_path, index=False, encoding='utf-8')
                
                generated_files['summary_statistics'] = str(summary_path)
                print(f"   ✅ events_summary_statistics.csv: {len(summary_df)} événements")
            
            # 4. Centroïdes des événements (pour visualisation globale)
            if not summary_df.empty and 'centroid_lat' in summary_df.columns:
                centroids_df = summary_df[['event_date', 'centroid_lon', 'centroid_lat', 
                                          'precip_max', 'anomaly_max', 'season_phase', 
                                          'main_region', 'event_type', 'intensity_level']].copy()
                
                # Renommer pour QGIS
                centroids_df.columns = ['event_date', 'longitude', 'latitude', 
                                       'max_precipitation', 'max_anomaly', 'season_phase',
                                       'main_region', 'event_type', 'intensity_level']
                
                centroids_path = output_dir / "events_centroids.csv"
                centroids_df.to_csv(centroids_path, index=False, encoding='utf-8')
                
                generated_files['centroids'] = str(centroids_path)
                print(f"   ✅ events_centroids.csv: {len(centroids_df)} centroïdes")
            
            # 5. Métadonnées pour QGIS
            metadata = {
                'title': 'Événements pluviométriques extrêmes spécifiques - Sénégal',
                'description': 'Extraction CHIRPS des evenements selectionnes automatiquement: plus/moins intense, plus/petite couverture, plus/moins grande anomalie',
                'selection_criteria': {k: v for k, v in EVENT_LABELS.items()},
                'source': 'CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)',
                'spatial_resolution': '0.25° (~25 km)',
                'temporal_resolution': 'daily',
                'coordinate_system': 'WGS84 (EPSG:4326)',
                'created_at': datetime.now().isoformat(),
                'created_by': 'SpecificEventsExtractor v1.0',
                'target_events': TARGET_EVENTS,
                'geographic_bounds': SENEGAL_BOUNDS,
                'rainfall_phases': RAINFALL_PHASES,
                'data_columns': {
                    'longitude': 'Longitude en degrés décimaux (WGS84)',
                    'latitude': 'Latitude en degrés décimaux (WGS84)',
                    'precipitation_mm': 'Précipitation en mm/jour',
                    'anomaly_standardized': 'Anomalie standardisée (écarts-type)',
                    'climatology_mm': 'Climatologie moyenne en mm/jour',
                    'is_extreme': 'Pixel extrême (anomalie > 2σ)',
                    'is_intense': 'Pixel intense (précipitation > 20mm)',
                    'intensity_category': 'Catégorie d\'intensité',
                    'anomaly_category': 'Catégorie d\'anomalie',
                    'region': 'Région administrative du Sénégal',
                    'climate_zone': 'Zone climatique',
                    'season_phase': 'Phase de saison des pluies',
                    'distance_to_coast': 'Distance approximative à la côte (km)'
                },
                'usage_notes': [
                    'Importer les fichiers CSV dans QGIS avec longitude/latitude comme coordonnées',
                    'Utiliser le système de coordonnées WGS84 (EPSG:4326)',
                    'Les valeurs NaN ont été filtrées des données',
                    'Chaque pixel représente une cellule de grille CHIRPS de ~25km',
                    'Les anomalies > 2σ sont considérées comme extrêmes'
                ],
                'files_generated': list(generated_files.keys())
            }
            
            metadata_path = output_dir / "metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            generated_files['metadata'] = str(metadata_path)
            print(f"   ✅ metadata.json: informations techniques")
            
            print(f"\n📁 {len(generated_files)} fichiers générés dans {output_dir}")
            
            return generated_files
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde: {e}")
            return {}
    
    def run_extraction(self, output_dir: str = "outputs/specific_events_qgis") -> bool:
        """
        Lance l'extraction complète des événements spécifiques.
        
        Args:
            output_dir (str): Dossier de sortie
            
        Returns:
            bool: Succès de l'extraction
        """
        print("EXTRACTION D'EVENEMENTS SPECIFIQUES POUR QGIS")
        print("=" * 60)
        print("Evenements cibles (selection automatique):")
        for i, event_date in enumerate(TARGET_EVENTS, 1):
            event_datetime = datetime.strptime(event_date, '%Y-%m-%d')
            phase = get_phase_from_month(event_datetime.month)
            phase_desc = RAINFALL_PHASES[phase]['description']
            criterion = EVENT_LABELS.get(event_date, 'selection_manuelle')
            print(f"   {i}. {event_date} [{criterion}] - {phase_desc}")
        
        try:
            # Étape 1: Chargement des données
            if not self.load_chirps_data():
                return False
            
            # Étape 2: Calcul de la climatologie
            if not self.calculate_climatology():
                return False
            
            # Étape 3: Localisation des événements
            event_indices = self.find_event_indices()
            if not event_indices:
                print("❌ Aucun événement trouvé dans les données")
                return False
            
            # Étape 4: Extraction des données pour chaque événement
            all_events_data = {}
            
            print(f"\n📊 EXTRACTION DES DONNÉES PAR ÉVÉNEMENT")
            print("-" * 45)
            
            for event_date, event_index in event_indices.items():
                event_df = self.extract_event_data(event_date, event_index)
                if not event_df.empty:
                    all_events_data[event_date] = event_df
                else:
                    print(f"⚠️ Aucune donnée extraite pour {event_date}")
            
            if not all_events_data:
                print("❌ Aucune donnée extraite pour les événements")
                return False
            
            # Étape 5: Création du résumé statistique
            summary_df = self.create_summary_statistics(all_events_data)
            
            # Étape 6: Sauvegarde
            output_path = Path(output_dir)
            generated_files = self.save_to_csv(all_events_data, summary_df, output_path)
            
            if not generated_files:
                print("❌ Échec de la sauvegarde")
                return False
            
            # Rapport final
            self._print_final_report(all_events_data, summary_df, generated_files, output_path)
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur durant l'extraction: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _print_final_report(self, all_events_data: Dict[str, pd.DataFrame], 
                           summary_df: pd.DataFrame, generated_files: Dict[str, str],
                           output_path: Path):
        """Affiche le rapport final détaillé."""
        
        print("\n" + "="*60)
        print("🎉 EXTRACTION TERMINÉE AVEC SUCCÈS")
        print("="*60)
        
        # Statistiques générales
        total_pixels = sum(len(df) for df in all_events_data.values())
        total_extreme = sum((df['anomaly_standardized'] > 2.0).sum() for df in all_events_data.values())
        total_intense = sum((df['precipitation_mm'] > 20.0).sum() for df in all_events_data.values())
        
        print(f"STATISTIQUES GLOBALES:")
        print(f"   Evenements extraits: {len(all_events_data)}/{len(TARGET_EVENTS)}")
        print(f"   Criteres de selection:")
        for date, label in EVENT_LABELS.items():
            print(f"     {date} -> {label}")
        print(f"   Pixels totaux: {total_pixels:,}")
        print(f"   Pixels extrêmes (>2σ): {total_extreme:,} ({total_extreme/total_pixels*100:.1f}%)")
        print(f"   Pixels intenses (>20mm): {total_intense:,} ({total_intense/total_pixels*100:.1f}%)")
        
        if not summary_df.empty:
            print(f"\n💧 PRÉCIPITATIONS:")
            print(f"   Maximum global: {summary_df['precip_max'].max():.1f} mm")
            print(f"   Moyenne globale: {summary_df['precip_mean'].mean():.2f} mm")
            print(f"   Anomalie maximale: {summary_df['anomaly_max'].max():.2f}σ")
        
        print(f"\n🌧️ RÉPARTITION PAR PHASES:")
        if not summary_df.empty:
            phase_counts = summary_df['season_phase'].value_counts()
            for phase, count in phase_counts.items():
                phase_desc = RAINFALL_PHASES[phase]['description']
                print(f"   {phase_desc}: {count} événement(s)")
        
        print(f"\n🗺️ RÉPARTITION GÉOGRAPHIQUE:")
        if all_events_data:
            all_regions = set()
            for df in all_events_data.values():
                all_regions.update(df['region'].unique())
            print(f"   Régions affectées: {len(all_regions)}")
            print(f"   Principales régions: {', '.join(list(all_regions)[:5])}")
        
        print(f"\n📁 FICHIERS GÉNÉRÉS ({len(generated_files)}):")
        for file_type, filepath in generated_files.items():
            filename = Path(filepath).name
            file_size_mb = Path(filepath).stat().st_size / (1024**2)
            print(f"   • {filename}: {file_size_mb:.2f} MB")
        
        print(f"\n🗂️ DOSSIER DE SORTIE: {output_path.absolute()}")
        
        print(f"\n🎯 UTILISATION DANS QGIS:")
        print(f"   1. Ouvrir QGIS")
        print(f"   2. Couche > Ajouter une couche > Ajouter une couche de texte délimité")
        print(f"   3. Sélectionner les fichiers CSV générés")
        print(f"   4. Définir 'longitude' et 'latitude' comme coordonnées X/Y")
        print(f"   5. Choisir le SCR: WGS84 (EPSG:4326)")
        print(f"   6. Styliser selon 'precipitation_mm' ou 'anomaly_standardized'")
        
        print(f"\n💡 SUGGESTIONS DE VISUALISATION:")
        print(f"   • Cartes de chaleur par intensité de précipitation")
        print(f"   • Classification par anomalies standardisées")
        print(f"   • Animation temporelle des événements")
        print(f"   • Comparaison entre phases de saison des pluies")
        print(f"   • Analyse spatiale par région administrative")
        
        print(f"\n📊 VARIABLES CLÉS POUR L'ANALYSE:")
        print(f"   • precipitation_mm: Intensité des pluies")
        print(f"   • anomaly_standardized: Écart à la normale")
        print(f"   • is_extreme: Marqueur d'événements exceptionnels")
        print(f"   • region: Localisation administrative")
        print(f"   • season_phase: Classification saisonnière")
        
        print(f"\n✨ EXTRACTION PRÊTE POUR L'ANALYSE GÉOSPATIALE!")


def main():
    """Fonction principale du script."""
    
    print("🎯 EXTRACTEUR D'ÉVÉNEMENTS SPÉCIFIQUES POUR QGIS")
    print("Version 1.0 - Optimisé pour l'analyse géospatiale")
    print("="*60)
    
    try:
        # Configuration du fichier CHIRPS avec recherche automatique
        chirps_path = None
        
        # Option 1: Argument en ligne de commande
        if len(sys.argv) > 1:
            chirps_path = sys.argv[1]
            print(f"📁 Fichier spécifié: {chirps_path}")
        
        # Option 2: Recherche automatique dans plusieurs emplacements
        else:
            print("🔍 Recherche automatique du fichier CHIRPS...")
            
            possible_paths = [
                # Windows paths relatifs
                "data/raw/chirps_WA_1981_2023_dayly.mat",
                "data/chirps_WA_1981_2023_dayly.mat",
                "chirps_WA_1981_2023_dayly.mat",
                
                # Dossier courant et parents
                "./chirps_WA_1981_2023_dayly.mat",
                "../data/chirps_WA_1981_2023_dayly.mat",
                "../../data/chirps_WA_1981_2023_dayly.mat",
                
                # Dossiers Windows typiques
                f"{Path.home()}/Documents/chirps_WA_1981_2023_dayly.mat",
                f"{Path.home()}/Desktop/chirps_WA_1981_2023_dayly.mat",
                f"{Path.home()}/Downloads/chirps_WA_1981_2023_dayly.mat",
                
                # Dans le dossier du script
                f"{Path(__file__).parent}/chirps_WA_1981_2023_dayly.mat",
                f"{Path(__file__).parent.parent}/data/chirps_WA_1981_2023_dayly.mat",
                f"{Path(__file__).parent.parent}/data/raw/chirps_WA_1981_2023_dayly.mat",
            ]
            
            # Recherche avec patterns plus flexibles
            script_dir = Path(__file__).parent
            project_dir = script_dir.parent
            
            # Recherche récursive dans le projet
            for pattern in ["**/chirps*.mat", "**/CHIRPS*.mat", "**/*chirps*.mat"]:
                for found_file in project_dir.glob(pattern):
                    if found_file.is_file() and "chirps" in found_file.name.lower():
                        possible_paths.append(str(found_file))
            
            # Recherche dans les disques Windows
            if os.name == 'nt':  # Windows
                for drive in ['C:', 'D:', 'E:']:
                    for pattern in [f"{drive}/data/**/chirps*.mat", f"{drive}/Users/**/chirps*.mat"]:
                        try:
                            for found_file in Path(drive).glob(pattern.replace(f"{drive}/", "")):
                                if found_file.is_file():
                                    possible_paths.append(str(found_file))
                        except:
                            pass
            
            # Tester chaque chemin
            for path in possible_paths:
                if os.path.exists(path):
                    chirps_path = path
                    print(f"✅ Fichier trouvé: {chirps_path}")
                    break
                else:
                    print(f"   ❌ Non trouvé: {path}")
        
        # Validation finale
        if not chirps_path:
            print(f"\n❌ FICHIER CHIRPS NON TROUVÉ!")
            print(f"\n🔍 SOLUTIONS:")
            print(f"   1. Spécifier le chemin exact:")
            print(f"      python {sys.argv[0]} \"C:\\chemin\\vers\\chirps_WA_1981_2023_dayly.mat\"")
            print(f"   2. Placer le fichier dans un de ces dossiers:")
            print(f"      • {Path(__file__).parent}/")
            print(f"      • {Path(__file__).parent.parent}/data/")
            print(f"      • {Path.home()}/Downloads/")
            print(f"      • {Path.home()}/Desktop/")
            print(f"   3. Télécharger depuis: https://data.chc.ucsb.edu/products/CHIRPS-2.0/")
            print(f"\n💡 Le fichier doit contenir 'chirps' dans son nom et avoir l'extension .mat")
            return False
        
        if not os.path.exists(chirps_path):
            print(f"❌ Fichier spécifié non trouvé: {chirps_path}")
            return False
        
        # Validation du fichier et affichage des informations
        try:
            file_size_mb = os.path.getsize(chirps_path) / (1024**2)
            print(f"📁 Fichier CHIRPS validé: {Path(chirps_path).name}")
            print(f"📏 Taille: {file_size_mb:.1f} MB")
            print(f"📍 Chemin: {chirps_path}")
            
            if file_size_mb < 100:
                print(f"⚠️ ATTENTION: Fichier petit ({file_size_mb:.1f} MB)")
                print(f"   Les données peuvent être incomplètes")
                confirm = input(f"   Continuer quand même? (o/N): ").strip().lower()
                if confirm not in ['o', 'oui', 'y', 'yes']:
                    return False
        
        except Exception as e:
            print(f"❌ Erreur lecture fichier: {e}")
            return False
        
        # Validation des prérequis
        try:
            import h5py
            print("✅ Module h5py disponible")
        except ImportError:
            print("❌ Module h5py requis: pip install h5py")
            return False
        
        # Configuration de sortie avec chemin Windows
        output_dir = "outputs/specific_events_qgis"
        
        # Créer le dossier de sortie s'il n'existe pas
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        print(f"📂 Dossier de sortie: {Path(output_dir).absolute()}")
        
        # Vérification espace disque
        try:
            import shutil
            free_space_gb = shutil.disk_usage('.').free / (1024**3)
            print(f"💾 Espace disque disponible: {free_space_gb:.1f} GB")
            
            if free_space_gb < 1:
                print(f"⚠️ Espace disque faible, les fichiers de sortie peuvent être volumineux")
        except:
            pass
        
        # Confirmation utilisateur (si interactif)
        if sys.stdin.isatty():
            print(f"\n❓ CONFIRMATION:")
            print(f"   Événements à extraire: {len(TARGET_EVENTS)}")
            print(f"   Durée estimée: 2-5 minutes")
            print(f"   Espace nécessaire: ~50-200 MB")
            
            confirm = input(f"\n🔄 Lancer l'extraction? (o/N): ").strip().lower()
            if confirm not in ['o', 'oui', 'y', 'yes']:
                print("❌ Extraction annulée")
                return False
        
        # Lancement de l'extraction
        print(f"\n🚀 DÉBUT DE L'EXTRACTION - {datetime.now().strftime('%H:%M:%S')}")
        
        start_time = datetime.now()
        
        # Créer et lancer l'extracteur
        extractor = SpecificEventsExtractor(chirps_path)
        success = extractor.run_extraction(output_dir)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if success:
            print(f"\n🎊 EXTRACTION RÉUSSIE EN {duration:.1f} SECONDES")
            print(f"📁 Résultats disponibles dans: {Path(output_dir).absolute()}")
            
            # Instructions finales
            print(f"\n📋 ÉTAPES SUIVANTES:")
            print(f"   1. Ouvrir QGIS")
            print(f"   2. Importer les fichiers CSV générés")
            print(f"   3. Configurer les coordonnées (longitude/latitude)")
            print(f"   4. Créer des visualisations thématiques")
            print(f"   5. Analyser les patterns spatiaux")
            
            return True
        else:
            print(f"\n💥 EXTRACTION ÉCHOUÉE APRÈS {duration:.1f} SECONDES")
            return False
    
    except KeyboardInterrupt:
        print(f"\n⏹️ EXTRACTION INTERROMPUE PAR L'UTILISATEUR")
        return False
    
    except Exception as e:
        print(f"\n💥 ERREUR INATTENDUE: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = main()
        exit_code = 0 if success else 1
        
        if success:
            print(f"\n✨ MISSION ACCOMPLIE!")
            print(f"🗺️ Données prêtes pour l'analyse géospatiale dans QGIS")
        else:
            print(f"\n❌ MISSION ÉCHOUÉE")
            print(f"🔧 Consulter les messages d'erreur ci-dessus")
        
        sys.exit(exit_code)
        
    except Exception as critical_error:
        print(f"\n💀 ERREUR CRITIQUE: {critical_error}")
        sys.exit(2)