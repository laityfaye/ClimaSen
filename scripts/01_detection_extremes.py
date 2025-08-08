#!/usr/bin/env python3
# scripts/01_detection_extremes.py
"""
Script principal pour la détection des événements de précipitations extrêmes au Sénégal.
VERSION 4.0 COMPLÈTE INTÉGRÉE - Analyse avancée avec nouvelle architecture modulaire.

Ce script orchestre l'ensemble du processus d'analyse moderne :
1. Chargement optimisé des données CHIRPS (par chunks)
2. Calcul de la climatologie avancée avec validation
3. Détection des événements extrêmes avec métriques spatiales
4. Classification par phases de saison des pluies (innovation)
5. Analyse géographique automatique (régions, départements, zones climatiques)
6. Génération complète des visualisations et rapports avancés

Nouveautés Version 4.0:
- Intégration complète avec les nouvelles classes Enhanced*
- Classification par phases de saison des pluies (3 phases + hors saison)
- Références géographiques automatiques du Sénégal
- Métriques spatiales avancées avec courbure terrestre
- Validation climatologique multi-critères
- Rapports intelligents avec recommandations
- Visualisations thématiques par phases

Utilisation:
    python scripts/01_detection_extremes.py
    python scripts/01_detection_extremes.py /chemin/vers/chirps.mat

Auteur: Équipe de recherche climatologique
Date: 2025-07-17
Version: 4.0 - Architecture modulaire complète
"""

import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np
import h5py
import gc
from datetime import datetime, timedelta
import warnings
import json

# Supprimer les warnings non critiques
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=UserWarning)

# ============================================================================
# CONFIGURATION DES IMPORTS - VERSION 4.0 INTÉGRÉE
# ============================================================================

def setup_project_paths():
    """Configure les chemins du projet de manière robuste."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    src_dir = project_root / "src"
    
    # Ajouter SEULEMENT si pas déjà présent
    for path_str in [str(project_root), str(src_dir)]:
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    
    print(f"🔧 Chemins configurés: {project_root}")
    return project_root

PROJECT_ROOT = setup_project_paths()

# IMPORTS NOUVELLE ARCHITECTURE AVEC FALLBACKS INTELLIGENTS
try:
    from src.config.settings import (
        CHIRPS_FILEPATH, PROJECT_INFO, RAINFALL_PHASES,
        create_output_directories, print_project_info, 
        get_output_path, validate_configuration
    )
    print("✅ Configuration avancée importée")
    CONFIG_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Configuration basique utilisée: {e}")
    CONFIG_ADVANCED = False
    
    # Configuration de fallback améliorée
    CHIRPS_FILEPATH = "/app/data/raw/chirps_WA_1981_2023_dayly.mat"
    PROJECT_INFO = {
        'title': 'Analyse des précipitations extrêmes au Sénégal',
        'version': '4.0',
        'author': 'Équipe de recherche climatologique'
    }
    RAINFALL_PHASES = {
        'Phase_1_debut': {'months': [5, 6], 'description': 'Début de saison (Mai-Juin)'},
        'Phase_2_pleine': {'months': [7, 8], 'description': 'Pleine saison (Juillet-Août)'},
        'Phase_3_fin': {'months': [9, 10], 'description': 'Fin de saison (Septembre-Octobre)'},
        'Hors_saison': {'months': [11, 12, 1, 2, 3, 4], 'description': 'Saison sèche'}
    }
    
    def create_output_directories():
        dirs = ["outputs/data", "outputs/visualizations", "outputs/reports", 
               "outputs/exports", "outputs/visualizations/phases",
               "outputs/visualizations/spatial", "outputs/visualizations/temporal"]
        for d in dirs:
            Path(d).mkdir(parents=True, exist_ok=True)
    
    def print_project_info():
        print(f"📊 {PROJECT_INFO['title']}")
        print(f"Version: {PROJECT_INFO['version']}")
    
    def get_output_path(key):
        paths = {
            'extreme_events': 'outputs/data/extreme_events_phases_senegal.csv',
            'climatology': 'outputs/data/climatology_enhanced_senegal.npz',
            'anomalies': 'outputs/data/anomalies_standardized_senegal.npz',
            'detection_report': 'outputs/reports/rapport_detection_comprehensive.txt',
            'spatial_metrics': 'outputs/data/spatial_metrics_detailed.csv',
            'phase_statistics': 'outputs/data/phase_statistics_summary.json'
        }
        return paths.get(key, f'outputs/data/{key}.csv')
    
    def validate_configuration():
        return True

# Import du loader de données
try:
    from src.data.loader import ChirpsDataLoader
    print("✅ Loader CHIRPS avancé importé")
    LOADER_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Loader basique utilisé: {e}")
    LOADER_ADVANCED = False

# Import de l'analyse climatologique avancée
try:
    from src.analysis.climatology import (
        EnhancedClimatologyCalculator, 
        calculate_standardized_anomalies_robust,
        ClimatologyValidator
    )
    print("✅ Climatologie avancée importée")
    CLIMATOLOGY_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Climatologie basique utilisée: {e}")
    CLIMATOLOGY_ADVANCED = False

# Import de la détection avancée avec géolocalisation
try:
    from src.analysis.detection import ExtremeEventDetector
    from src.analysis.spatial_metrics import EnhancedSpatialMetricsCalculator
    print("✅ Détection et métriques spatiales avancées importées")
    DETECTION_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Détection basique utilisée: {e}")
    DETECTION_ADVANCED = False

# Import de la classification par phases
try:
    from src.utils.season_classifier import RainfallPhaseClassifier
    from src.utils.geographic_references import SenegalGeography
    print("✅ Classification par phases et géographie importées")
    CLASSIFICATION_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Classification basique utilisée: {e}")
    CLASSIFICATION_ADVANCED = False

# Import des visualisations avancées
try:
    from src.visualization.detection_plots import EnhancedDetectionVisualizer
    from src.visualization.geographic_plots import EnhancedSenegalMapVisualizer
    print("✅ Visualisations avancées importées")
    VISUALIZATION_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Visualisations basiques utilisées: {e}")
    VISUALIZATION_ADVANCED = False

# Import des rapports avancés
try:
    from src.reports.detection_report import EnhancedDetectionReportGenerator
    from src.reports.spatial_report import EnhancedSpatialReportGenerator
    print("✅ Rapports avancés importés")
    REPORTS_ADVANCED = True
except ImportError as e:
    print(f"⚠️ Rapports basiques utilisés: {e}")
    REPORTS_ADVANCED = False

print("✅ Imports terminés - Configuration déterminée")

# ============================================================================
# LOADER CHIRPS OPTIMISÉ MÉMOIRE - VERSION 4.0
# ============================================================================

class OptimizedChirpsLoader:
    """
    Loader CHIRPS optimisé pour Docker avec contraintes mémoire.
    Version 4.0 intégrée avec la nouvelle architecture.
    """
    
    def __init__(self, chirps_file_path: str):
        self.chirps_file_path = Path(chirps_file_path)
        self.chunk_size = 365  # Une année à la fois
        
        # Limites géographiques Sénégal (compatibilité avec SenegalGeography)
        self.senegal_bounds = {'lat_min': 12.3, 'lat_max': 16.7, 'lon_min': -17.55, 'lon_max': -11.35}

        if not self.chirps_file_path.exists():
            raise FileNotFoundError(f"Fichier CHIRPS non trouvé: {chirps_file_path}")
        
        print(f"🔧 OptimizedChirpsLoader v4.0 initialisé: {self.chirps_file_path}")
    
    def load_senegal_data(self):
        """
        Interface compatible avec ChirpsDataLoader mais optimisée mémoire.
        
        Returns:
            Tuple: (precip_data, dates, lats, lons)
        """
        print("🔄 CHARGEMENT OPTIMISÉ DES DONNÉES CHIRPS - SÉNÉGAL v4.0")
        print("=" * 70)
        
        # 1. Analyse des métadonnées
        with h5py.File(self.chirps_file_path, 'r') as f:
            print("🔍 Analyse des métadonnées CHIRPS:")
            print(f"   Clés disponibles: {list(f.keys())}")
            
            full_latitude = np.array(f['latitude']).flatten()
            full_longitude = np.array(f['longitude']).flatten()
            data_shape = f['precip'].shape
            
            print(f"   Shape complète: {data_shape}")
            print(f"   Résolution: ~{abs(full_latitude[1]-full_latitude[0]):.3f}° (~25km)")
            print(f"   Période: {data_shape[0]} jours")
        
        # 2. Masques géographiques pour le Sénégal
        lat_mask = (full_latitude >= self.senegal_bounds['lat_min']) & (full_latitude <= self.senegal_bounds['lat_max'])
        lon_mask = (full_longitude >= self.senegal_bounds['lon_min']) & (full_longitude <= self.senegal_bounds['lon_max'])
        
        senegal_lat = full_latitude[lat_mask]
        senegal_lon = full_longitude[lon_mask]
        
        print(f"🗺️ Zone Sénégal extraite:")
        print(f"   Latitudes: {lat_mask.sum()} points ({senegal_lat.min():.2f}°N à {senegal_lat.max():.2f}°N)")
        print(f"   Longitudes: {lon_mask.sum()} points ({abs(senegal_lon.max()):.2f}°W à {abs(senegal_lon.min()):.2f}°W)")
        
        # 3. Chargement par chunks avec optimisation mémoire
        total_days = data_shape[0]
        senegal_shape = (total_days, lat_mask.sum(), lon_mask.sum())
        memory_reduction = (1 - np.prod(senegal_shape) / np.prod(data_shape)) * 100
        
        print(f"📦 Chargement par chunks optimisé:")
        print(f"   Shape finale: {senegal_shape}")
        print(f"   Réduction mémoire: {memory_reduction:.1f}%")
        print(f"   Taille des chunks: {self.chunk_size} jours")
        
        senegal_data_chunks = []
        
        with h5py.File(self.chirps_file_path, 'r') as f:
            precip_dataset = f['precip']
            
            total_chunks = (total_days + self.chunk_size - 1) // self.chunk_size
            
            for start_idx in range(0, total_days, self.chunk_size):
                end_idx = min(start_idx + self.chunk_size, total_days)
                chunk_num = start_idx // self.chunk_size + 1
                
                print(f"   📦 Chunk {chunk_num}/{total_chunks}: jours {start_idx+1}-{end_idx}")
                
                # Charger et filtrer immédiatement
                chunk_data = precip_dataset[start_idx:end_idx, :, :].astype(np.float32)
                senegal_chunk = chunk_data[:, lat_mask, :][:, :, lon_mask]
                senegal_data_chunks.append(senegal_chunk)
                
                # Nettoyage immédiat
                del chunk_data, senegal_chunk
                gc.collect()
        
        # 4. Assemblage final
        print("🔧 Assemblage final des données...")
        senegal_data = np.concatenate(senegal_data_chunks, axis=0)
        del senegal_data_chunks
        gc.collect()
        
        # 5. Dates compatibles avec la nouvelle architecture
        start_date = datetime(1981, 1, 1)
        dates = [start_date + timedelta(days=i) for i in range(total_days)]
        
        # 6. Statistiques et validation
        valid_data = senegal_data[~np.isnan(senegal_data)]
        
        print(f"✅ Données Sénégal chargées avec succès:")
        print(f"   Shape finale: {senegal_data.shape}")
        print(f"   Mémoire: {senegal_data.nbytes / (1024**2):.1f} MB")
        print(f"   Période: {dates[0].strftime('%Y-%m-%d')} à {dates[-1].strftime('%Y-%m-%d')}")
        print(f"   Données valides: {len(valid_data)/senegal_data.size*100:.1f}%")
        print(f"   Précipitation: {valid_data.min():.2f}-{valid_data.max():.2f} mm (moy: {valid_data.mean():.2f})")
        
        return senegal_data, dates, senegal_lat, senegal_lon

# ============================================================================
# FALLBACK CLASSES POUR COMPATIBILITÉ
# ============================================================================

class BasicSeasonClassifier:
    """Classificateur saisonnier basique en cas d'import échoué."""
    
    def classify_and_validate(self, df_events):
        print("⚠️ Classification saisonnière basique")
        
        def get_phase(date):
            month = date.month
            if month in [5, 6]:
                return 'Phase_1_debut'
            elif month in [7, 8]:
                return 'Phase_2_pleine'
            elif month in [9, 10]:
                return 'Phase_3_fin'
            else:
                return 'Hors_saison'
        
        df_events['phase'] = df_events.index.map(get_phase)
        df_events['year'] = df_events.index.year
        df_events['month'] = df_events.index.month
        
        # Statistiques basiques
        phase_counts = df_events['phase'].value_counts()
        rainy_phases = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']
        rainy_events = sum(phase_counts.get(phase, 0) for phase in rainy_phases)
        rainy_pct = rainy_events / len(df_events) * 100 if len(df_events) > 0 else 0
        
        if rainy_pct > 75:
            validation = "COHERENT"
        elif rainy_pct > 60:
            validation = "MODERE"
        else:
            validation = "INCOHERENT"
        
        print(f"   Validation: {validation} ({rainy_pct:.1f}% en saison des pluies)")
        
        return df_events, validation

class BasicDetector:
    """Détecteur basique en cas d'import échoué."""
    
    def detect_events(self, precip_data, anomalies, dates, lats, lons):
        print("⚠️ Détection basique des événements extrêmes")
        
        # Critères basiques
        threshold_anomaly = 2.0
        min_grid_points = 40
        
        events_data = []
        n_time, n_lat, n_lon = precip_data.shape
        total_grid_points = n_lat * n_lon
        
        for i, date in enumerate(dates):
            day_precip = precip_data[i, :, :]
            day_anomalies = anomalies[i, :, :]
            
            # Masque des points extrêmes
            extreme_mask = (day_anomalies > threshold_anomaly) & ~np.isnan(day_anomalies)
            n_extreme_points = np.sum(extreme_mask)
            
            if n_extreme_points >= min_grid_points:
                max_precip = np.nanmax(day_precip)
                if max_precip >= 5.0:  # Seuil minimum
                    # Calculer les métriques basiques
                    extreme_precip = day_precip[extreme_mask]
                    extreme_anomalies = day_anomalies[extreme_mask]
                    
                    # Centroïde pondéré
                    lat_indices, lon_indices = np.where(extreme_mask)
                    weights = extreme_precip
                    centroid_lat = np.average(lats[lat_indices], weights=weights)
                    centroid_lon = np.average(lons[lon_indices], weights=weights)
                    
                    events_data.append({
                        'date': date,
                        'max_precip': float(max_precip),
                        'mean_precip': float(np.nanmean(extreme_precip)),
                        'max_anomaly': float(np.nanmax(extreme_anomalies)),
                        'mean_anomaly': float(np.nanmean(extreme_anomalies)),
                        'coverage_points': int(n_extreme_points),
                        'coverage_percent': float(n_extreme_points / total_grid_points * 100),
                        'centroid_lat': float(centroid_lat),
                        'centroid_lon': float(centroid_lon),
                        'month': date.month,
                        'year': date.year
                    })
        
        df = pd.DataFrame(events_data)
        if not df.empty:
            df.set_index('date', inplace=True)
            df.sort_values(['coverage_points', 'max_anomaly'], ascending=[False, False], inplace=True)
            df['rank'] = range(1, len(df) + 1)
        
        print(f"   Événements détectés: {len(df)}")
        return df

# ============================================================================
# CLASSE PRINCIPALE D'ANALYSE - VERSION 4.0 COMPLÈTE
# ============================================================================

class AdvancedExtremeEventsAnalyzer:
    """
    Analyseur d'événements extrêmes - Version 4.0 complète.
    Intègre toutes les nouvelles fonctionnalités de la plateforme.
    """
    
    def __init__(self, chirps_file_path: str = None):
        """Initialise l'analyseur avec la nouvelle architecture."""
        
        self.chirps_file_path = chirps_file_path or str(CHIRPS_FILEPATH)
        
        # Variables de données
        self.precip_data = None
        self.dates = None
        self.lats = None
        self.lons = None
        self.climatology = None
        self.std_dev = None
        self.anomalies = None
        self.extreme_events_df = None
        self.spatial_metrics = None
        
        # Initialiser les modules selon la disponibilité
        self._initialize_modules()
        
        print("✅ AdvancedExtremeEventsAnalyzer v4.0 initialisé")
        print(f"   Configuration: {'Avancée' if CONFIG_ADVANCED else 'Basique'}")
        print(f"   Détection: {'Avancée' if DETECTION_ADVANCED else 'Basique'}")
        print(f"   Classification: {'Par phases' if CLASSIFICATION_ADVANCED else 'Saisonnière simple'}")
    
    def _initialize_modules(self):
        """Initialise les modules selon leur disponibilité."""
        
        # Loader de données
        if LOADER_ADVANCED:
            self.loader_class = ChirpsDataLoader
        else:
            self.loader_class = OptimizedChirpsLoader
        
        # Climatologie
        if CLIMATOLOGY_ADVANCED:
            self.climatology_calculator = EnhancedClimatologyCalculator()
            self.climatology_validator = ClimatologyValidator()
        else:
            self.climatology_calculator = None
            self.climatology_validator = None
        
        # Détection
        if DETECTION_ADVANCED:
            self.detector = ExtremeEventDetector()
            self.spatial_calculator = EnhancedSpatialMetricsCalculator()
        else:
            self.detector = BasicDetector()
            self.spatial_calculator = None
        
        # Classification
        if CLASSIFICATION_ADVANCED:
            self.phase_classifier = RainfallPhaseClassifier()
            self.geography = SenegalGeography()
        else:
            self.phase_classifier = BasicSeasonClassifier()
            self.geography = None
        
        # Visualisations
        if VISUALIZATION_ADVANCED:
            self.detection_visualizer = EnhancedDetectionVisualizer()
            self.geographic_visualizer = EnhancedSenegalMapVisualizer()
        else:
            self.detection_visualizer = None
            self.geographic_visualizer = None
        
        # Rapports
        if REPORTS_ADVANCED:
            self.detection_reporter = EnhancedDetectionReportGenerator()
            self.spatial_reporter = EnhancedSpatialReportGenerator()
        else:
            self.detection_reporter = None
            self.spatial_reporter = None
    
    def step_1_load_data(self) -> bool:
        """Étape 1: Chargement optimisé des données."""
        
        print("\n" + "="*80)
        print("ÉTAPE 1: CHARGEMENT DES DONNÉES (VERSION 4.0)")
        print("="*80)
        
        if not os.path.exists(self.chirps_file_path):
            print(f"❌ Fichier CHIRPS non trouvé: {self.chirps_file_path}")
            return False
        
        try:
            # Utiliser le loader approprié
            if LOADER_ADVANCED:
                loader = ChirpsDataLoader(self.chirps_file_path)
                self.precip_data, self.dates, self.lats, self.lons = loader.load_senegal_data()
            else:
                loader = OptimizedChirpsLoader(self.chirps_file_path)
                self.precip_data, self.dates, self.lats, self.lons = loader.load_senegal_data()
            
            if self.precip_data is None:
                print("❌ Échec du chargement")
                return False
            
            print("✅ Données chargées avec succès")
            print(f"   Forme: {self.precip_data.shape}")
            print(f"   Période: {self.dates[0].strftime('%Y-%m-%d')} à {self.dates[-1].strftime('%Y-%m-%d')}")
            print(f"   Grille: {len(self.lats)} × {len(self.lons)} points")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur chargement: {e}")
            return False
    
    def step_2_calculate_climatology(self) -> bool:
        """Étape 2: Calcul climatologie avancée."""
        
        print("\n" + "="*80)
        print("ÉTAPE 2: CALCUL CLIMATOLOGIE AVANCÉE")
        print("="*80)
        
        try:
            if CLIMATOLOGY_ADVANCED:
                # Utiliser le calculateur avancé
                print("🔬 Utilisation de l'EnhancedClimatologyCalculator")
                
                self.climatology, self.std_dev, comprehensive_stats = \
                    self.climatology_calculator.calculate_comprehensive_climatology(
                        self.precip_data, self.dates
                    )
                
                # Calculer les anomalies avec méthode robuste
                self.anomalies = calculate_standardized_anomalies_robust(
                    self.precip_data, self.dates, self.climatology, self.std_dev
                )
                
                # Validation qualité
                validation = self.climatology_validator.validate_comprehensive(
                    self.climatology, self.std_dev, self.anomalies, self.dates
                )
                
                print(f"   Qualité climatologie: {validation['quality_level']}")
                
            else:
                # Calcul basique
                print("⚠️ Utilisation du calcul climatologique basique")
                from datetime import datetime
                
                # Calcul simple jour par jour
                doy = np.array([d.timetuple().tm_yday for d in self.dates])
                n_days = 366
                n_lat, n_lon = self.precip_data.shape[1], self.precip_data.shape[2]
                
                self.climatology = np.zeros((n_days, n_lat, n_lon))
                self.std_dev = np.zeros((n_days, n_lat, n_lon))
                
                for day in range(1, n_days + 1):
                    day_indices = np.where(doy == day)[0]
                    if len(day_indices) > 0:
                        day_data = self.precip_data[day_indices, :, :]
                        self.climatology[day-1, :, :] = np.nanmean(day_data, axis=0)
                        self.std_dev[day-1, :, :] = np.nanstd(day_data, axis=0, ddof=1)
                
                # Remplacer NaN par valeurs minimales
                self.std_dev = np.where(np.isnan(self.std_dev) | (self.std_dev < 0.01), 0.1, self.std_dev)
                
                # Calcul anomalies
                self.anomalies = np.full_like(self.precip_data, np.nan)
                for i, date in enumerate(self.dates):
                    day_idx = date.timetuple().tm_yday - 1
                    if day_idx < n_days:
                        clim = self.climatology[day_idx, :, :]
                        std = self.std_dev[day_idx, :, :]
                        valid_mask = (std > 0.01) & ~np.isnan(clim) & ~np.isnan(self.precip_data[i, :, :])
                        self.anomalies[i, valid_mask] = (self.precip_data[i, valid_mask] - clim[valid_mask]) / std[valid_mask]
                
                self.anomalies = np.nan_to_num(self.anomalies, nan=0, posinf=15, neginf=-15)
            
            print("✅ Climatologie calculée")
            print(f"   Anomalie max: {np.nanmax(self.anomalies):.1f}σ")
            print(f"   Anomalie min: {np.nanmin(self.anomalies):.1f}σ")
            
            gc.collect()
            return True
            
        except Exception as e:
            print(f"❌ Erreur climatologie: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def step_3_detect_extreme_events(self) -> bool:
        """Étape 3: Détection avancée avec métriques spatiales."""
        
        print("\n" + "="*80)
        print("ÉTAPE 3: DÉTECTION AVANCÉE DES ÉVÉNEMENTS EXTRÊMES")
        print("="*80)
        
        try:
            # Détecter les événements
            self.extreme_events_df = self.detector.detect_events(
                self.precip_data, self.anomalies, self.dates, self.lats, self.lons
            )
            
            if self.extreme_events_df.empty:
                print("❌ Aucun événement détecté")
                return False
            
            print(f"✅ {len(self.extreme_events_df)} événements détectés")
            
            # Calculer les métriques spatiales avancées si disponible
            if DETECTION_ADVANCED and self.spatial_calculator:
                print("🔬 Calcul des métriques spatiales avancées...")
                
                spatial_metrics_list = []
                for i, (date, event) in enumerate(self.extreme_events_df.iterrows()):
                    metrics = self.spatial_calculator.calculate_comprehensive_metrics(
                        event_date=date,
                        event_data=event,
                        precip_data=self.precip_data,
                        anomalies=self.anomalies,
                        lats=self.lats,
                        lons=self.lons,
                        dates=self.dates,
                        rank=event.get('rank', i+1)
                    )
                    spatial_metrics_list.append(metrics)
                
                self.spatial_metrics = spatial_metrics_list
                print(f"   Métriques spatiales calculées pour {len(spatial_metrics_list)} événements")
            
            # Statistiques de base
            print(f"   Période: {self.extreme_events_df.index.min().strftime('%Y-%m-%d')} à {self.extreme_events_df.index.max().strftime('%Y-%m-%d')}")
            print(f"   Précipitation moyenne: {self.extreme_events_df['max_precip'].mean():.2f} mm")
            
            if 'coverage_percent' in self.extreme_events_df.columns:
                print(f"   Couverture moyenne: {self.extreme_events_df['coverage_percent'].mean():.2f}%")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur détection: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def step_4_phase_classification(self) -> str:
        """Étape 4: Classification par phases de saison des pluies."""
        
        print("\n" + "="*80)
        print("ÉTAPE 4: CLASSIFICATION PAR PHASES DE SAISON DES PLUIES")
        print("="*80)
        
        try:
            if CLASSIFICATION_ADVANCED:
                print("🌧️ Classification avancée par phases")
                
                # Utiliser le classificateur par phases
                self.extreme_events_df = self.phase_classifier.classify_by_phases(self.extreme_events_df)
                
                # Analyser et valider
                _, validation_status, phase_stats = self.phase_classifier.classify_and_analyze(self.extreme_events_df)
                
                # Enrichir avec informations géographiques
                if self.geography:
                    print("🗺️ Enrichissement géographique...")
                    for idx, event in self.extreme_events_df.iterrows():
                        if 'centroid_lat' in event and 'centroid_lon' in event:
                            lat, lon = event['centroid_lat'], event['centroid_lon']
                            
                            # Identifier région, département, zone climatique
                            region = self.geography.identify_region(lat, lon)
                            dept, _ = self.geography.identify_department(lat, lon)
                            climate_zone = self.geography.identify_climate_zone(lat, lon)
                            
                            self.extreme_events_df.loc[idx, 'centroid_region'] = region
                            self.extreme_events_df.loc[idx, 'centroid_department'] = dept
                            self.extreme_events_df.loc[idx, 'centroid_climate_zone'] = climate_zone
                
            else:
                # Classification basique
                self.extreme_events_df, validation_status = self.phase_classifier.classify_and_validate(self.extreme_events_df)
            
            # Afficher les résultats
            print(f"✅ Classification terminée - Validation: {validation_status}")
            
            if 'phase' in self.extreme_events_df.columns:
                phase_counts = self.extreme_events_df['phase'].value_counts()
                print("📊 Distribution par phases:")
                for phase, count in phase_counts.items():
                    pct = count / len(self.extreme_events_df) * 100
                    phase_info = RAINFALL_PHASES.get(phase, {})
                    description = phase_info.get('description', phase)
                    print(f"   • {description}: {count} événements ({pct:.1f}%)")
            
            # Afficher répartition géographique si disponible
            if 'centroid_region' in self.extreme_events_df.columns:
                region_counts = self.extreme_events_df['centroid_region'].value_counts()
                print("🗺️ Répartition géographique (Top 5):")
                for region, count in region_counts.head().items():
                    pct = count / len(self.extreme_events_df) * 100
                    print(f"   • {region}: {count} événements ({pct:.1f}%)")
            
            return validation_status
            
        except Exception as e:
            print(f"❌ Erreur classification: {e}")
            import traceback
            traceback.print_exc()
            return "ERREUR"
    
    def step_5_generate_visualizations(self) -> bool:
        """Étape 5: Génération des visualisations avancées."""
        
        print("\n" + "="*80)
        print("ÉTAPE 5: GÉNÉRATION DES VISUALISATIONS AVANCÉES")
        print("="*80)
        
        try:
            generated_files = {}
            
            if VISUALIZATION_ADVANCED:
                print("🎨 Génération des visualisations avancées...")
                
                # Visualisations de détection
                detection_files = self.detection_visualizer.create_all_visualizations(
                    self.extreme_events_df, self.lats, self.lons
                )
                generated_files.update(detection_files)
                
                # Visualisations géographiques
                geographic_files = self.geographic_visualizer.create_all_geographic_visualizations(
                    self.extreme_events_df
                )
                generated_files.update(geographic_files)
                
                print(f"✅ {len(generated_files)} visualisations avancées générées")
                for viz_type, path in generated_files.items():
                    print(f"   • {viz_type}: {Path(path).name}")
                
            else:
                print("⚠️ Génération des visualisations basiques...")
                
                try:
                    import matplotlib.pyplot as plt
                    
                    # Créer dossier
                    Path("outputs/visualizations").mkdir(parents=True, exist_ok=True)
                    
                    # Graphique 1: Distribution par phases
                    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
                    fig.suptitle('Analyse des Événements Extrêmes - Sénégal', fontsize=16, fontweight='bold')
                    
                    # Distribution par phases
                    if 'phase' in self.extreme_events_df.columns:
                        phase_counts = self.extreme_events_df['phase'].value_counts()
                        colors = ['#87CEEB', '#1E90FF', '#4682B4', '#D3D3D3'][:len(phase_counts)]
                        axes[0,0].pie(phase_counts.values, labels=phase_counts.index, 
                                    colors=colors, autopct='%1.1f%%', startangle=90)
                        axes[0,0].set_title('Distribution par Phases de Saison')
                    
                    # Évolution temporelle
                    monthly_counts = self.extreme_events_df.groupby(self.extreme_events_df.index.month).size()
                    axes[0,1].bar(monthly_counts.index, monthly_counts.values, 
                                color='lightblue', alpha=0.8)
                    axes[0,1].set_title('Distribution Mensuelle')
                    axes[0,1].set_xlabel('Mois')
                    axes[0,1].set_ylabel('Nombre d\'événements')
                    
                    # Distribution des précipitations
                    axes[1,0].hist(self.extreme_events_df['max_precip'], bins=20, 
                                 alpha=0.7, color='green', edgecolor='black')
                    axes[1,0].set_title('Distribution des Précipitations')
                    axes[1,0].set_xlabel('Précipitation max (mm)')
                    axes[1,0].set_ylabel('Fréquence')
                    
                    # Relation précipitation-couverture
                    axes[1,1].scatter(self.extreme_events_df['coverage_percent'], 
                                    self.extreme_events_df['max_precip'],
                                    alpha=0.6, c='red')
                    axes[1,1].set_title('Précipitation vs Couverture')
                    axes[1,1].set_xlabel('Couverture (%)')
                    axes[1,1].set_ylabel('Précipitation (mm)')
                    
                    plt.tight_layout()
                    plt.savefig('outputs/visualizations/analyse_evenements_extremes.png', 
                              dpi=300, bbox_inches='tight')
                    plt.close()
                    
                    print("✅ Visualisations basiques générées")
                    generated_files['basic_analysis'] = 'outputs/visualizations/analyse_evenements_extremes.png'
                    
                except Exception as viz_error:
                    print(f"⚠️ Erreur visualisations: {viz_error}")
            
            return len(generated_files) > 0
            
        except Exception as e:
            print(f"❌ Erreur génération visualisations: {e}")
            return False
    
    def step_6_generate_reports(self, validation_status: str) -> bool:
        """Étape 6: Génération des rapports avancés."""
        
        print("\n" + "="*80)
        print("ÉTAPE 6: GÉNÉRATION DES RAPPORTS AVANCÉS")
        print("="*80)
        
        try:
            generated_reports = {}
            
            if REPORTS_ADVANCED:
                print("📊 Génération des rapports avancés...")
                
                # Rapport de détection complet
                detection_files = self.detection_reporter.generate_all_reports(
                    self.extreme_events_df, validation_status
                )
                generated_reports.update(detection_files)
                
                # Rapport spatial si métriques disponibles
                if self.spatial_metrics:
                    spatial_files = self.spatial_reporter.generate_all_spatial_reports(
                        self.spatial_metrics, 
                        analysis_type="comprehensive_detection",
                        title="Analyse Spatiale des Événements Extrêmes",
                        df_events=self.extreme_events_df
                    )
                    generated_reports.update(spatial_files)
                
                print(f"✅ {len(generated_reports)} rapports avancés générés")
                for report_type, path in generated_reports.items():
                    print(f"   • {report_type}: {Path(path).name}")
                
            else:
                print("⚠️ Génération du rapport basique...")
                
                # Rapport basique
                report_path = get_output_path('detection_report')
                Path(report_path).parent.mkdir(parents=True, exist_ok=True)
                
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write("RAPPORT DE DÉTECTION D'ÉVÉNEMENTS EXTRÊMES - SÉNÉGAL\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Version de l'analyse: 4.0\n\n")
                    
                    f.write("1. RÉSULTATS PRINCIPAUX\n")
                    f.write("-" * 25 + "\n")
                    f.write(f"Nombre d'événements détectés: {len(self.extreme_events_df)}\n")
                    f.write(f"Période d'analyse: {self.extreme_events_df.index.min().strftime('%Y-%m-%d')} à {self.extreme_events_df.index.max().strftime('%Y-%m-%d')}\n")
                    f.write(f"Validation climatologique: {validation_status}\n\n")
                    
                    f.write("2. STATISTIQUES D'INTENSITÉ\n")
                    f.write("-" * 30 + "\n")
                    f.write(f"Précipitation moyenne: {self.extreme_events_df['max_precip'].mean():.2f} mm\n")
                    f.write(f"Précipitation maximale: {self.extreme_events_df['max_precip'].max():.2f} mm\n")
                    f.write(f"Précipitation médiane: {self.extreme_events_df['max_precip'].median():.2f} mm\n")
                    
                    if 'coverage_percent' in self.extreme_events_df.columns:
                        f.write(f"Couverture moyenne: {self.extreme_events_df['coverage_percent'].mean():.2f}%\n")
                        f.write(f"Couverture maximale: {self.extreme_events_df['coverage_percent'].max():.2f}%\n")
                    
                    if 'phase' in self.extreme_events_df.columns:
                        f.write("\n3. DISTRIBUTION PAR PHASES\n")
                        f.write("-" * 30 + "\n")
                        phase_counts = self.extreme_events_df['phase'].value_counts()
                        for phase, count in phase_counts.items():
                            pct = count / len(self.extreme_events_df) * 100
                            phase_info = RAINFALL_PHASES.get(phase, {})
                            description = phase_info.get('description', phase)
                            f.write(f"{description}: {count} événements ({pct:.1f}%)\n")
                    
                    if 'centroid_region' in self.extreme_events_df.columns:
                        f.write("\n4. RÉPARTITION GÉOGRAPHIQUE\n")
                        f.write("-" * 35 + "\n")
                        region_counts = self.extreme_events_df['centroid_region'].value_counts()
                        for region, count in region_counts.head(10).items():
                            pct = count / len(self.extreme_events_df) * 100
                            f.write(f"{region}: {count} événements ({pct:.1f}%)\n")
                    
                    f.write("\n5. TOP 10 ÉVÉNEMENTS\n")
                    f.write("-" * 20 + "\n")
                    top_events = self.extreme_events_df.head(10)
                    for i, (date, event) in enumerate(top_events.iterrows(), 1):
                        f.write(f"{i:2d}. {date.strftime('%Y-%m-%d')}: {event['max_precip']:.1f} mm")
                        if 'coverage_percent' in event:
                            f.write(f" ({event['coverage_percent']:.1f}%)")
                        f.write("\n")
                
                print(f"✅ Rapport basique généré: {report_path}")
                generated_reports['basic_report'] = report_path
            
            return len(generated_reports) > 0
            
        except Exception as e:
            print(f"❌ Erreur génération rapports: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def step_7_save_data(self) -> bool:
        """Étape 7: Sauvegarde complète des données."""
        
        print("\n" + "="*80)
        print("ÉTAPE 7: SAUVEGARDE COMPLÈTE DES DONNÉES")
        print("="*80)
        
        try:
            # Créer dossiers
            for folder in ["outputs/data", "outputs/exports"]:
                Path(folder).mkdir(parents=True, exist_ok=True)
            
            saved_files = []
            
            # 1. Dataset principal enrichi
            main_output = get_output_path('extreme_events')
            
            # Préparer les données pour l'export
            df_export = self.extreme_events_df.copy()
            df_export.reset_index(inplace=True)
            df_export['date'] = df_export['date'].dt.strftime('%Y-%m-%d')
            
            # Arrondir les colonnes numériques
            numeric_cols = ['max_precip', 'mean_precip', 'coverage_percent', 'max_anomaly', 
                          'mean_anomaly', 'centroid_lat', 'centroid_lon']
            for col in numeric_cols:
                if col in df_export.columns:
                    df_export[col] = df_export[col].round(3)
            
            df_export.to_csv(main_output, index=False, encoding='utf-8')
            saved_files.append(main_output)
            print(f"✅ Dataset principal: {Path(main_output).name}")
            
            # 2. Métriques spatiales si disponibles
            if self.spatial_metrics:
                spatial_output = get_output_path('spatial_metrics')
                
                # Convertir les métriques en DataFrame
                spatial_df_data = []
                for metrics in self.spatial_metrics:
                    if isinstance(metrics, dict):
                        # Aplatir les métriques complexes
                        flat_metrics = {}
                        for key, value in metrics.items():
                            if isinstance(value, dict):
                                for sub_key, sub_value in value.items():
                                    if isinstance(sub_value, (int, float, str)):
                                        flat_metrics[f"{key}_{sub_key}"] = sub_value
                            elif isinstance(value, (int, float, str)):
                                flat_metrics[key] = value
                        
                        spatial_df_data.append(flat_metrics)
                
                if spatial_df_data:
                    spatial_df = pd.DataFrame(spatial_df_data)
                    spatial_df.to_csv(spatial_output, index=False, encoding='utf-8')
                    saved_files.append(spatial_output)
                    print(f"✅ Métriques spatiales: {Path(spatial_output).name}")
            
            # 3. Climatologie
            clim_output = get_output_path('climatology')
            np.savez_compressed(clim_output,
                              climatology=self.climatology,
                              std_dev=self.std_dev,
                              lats=self.lats,
                              lons=self.lons,
                              metadata={
                                  'created_at': datetime.now().isoformat(),
                                  'version': '4.0',
                                  'description': 'Climatologie quotidienne pour le Sénégal'
                              })
            saved_files.append(clim_output)
            print(f"✅ Climatologie: {Path(clim_output).name}")
            
            # 4. Anomalies
            anom_output = get_output_path('anomalies')
            np.savez_compressed(anom_output,
                              anomalies=self.anomalies,
                              dates=[d.strftime('%Y-%m-%d') for d in self.dates],
                              metadata={
                                  'created_at': datetime.now().isoformat(),
                                  'version': '4.0',
                                  'description': 'Anomalies standardisées quotidiennes'
                              })
            saved_files.append(anom_output)
            print(f"✅ Anomalies: {Path(anom_output).name}")
            
            # 5. Statistiques des phases (si disponible)
            if 'phase' in self.extreme_events_df.columns:
                phase_stats_output = get_output_path('phase_statistics')
                
                phase_stats = {}
                phase_counts = self.extreme_events_df['phase'].value_counts()
                
                for phase in RAINFALL_PHASES.keys():
                    if phase in phase_counts.index:
                        phase_data = self.extreme_events_df[self.extreme_events_df['phase'] == phase]
                        phase_stats[phase] = {
                            'count': int(phase_counts[phase]),
                            'percentage': float(phase_counts[phase] / len(self.extreme_events_df) * 100),
                            'description': RAINFALL_PHASES[phase]['description'],
                            'months': RAINFALL_PHASES[phase]['months'],
                            'avg_precipitation': float(phase_data['max_precip'].mean()),
                            'max_precipitation': float(phase_data['max_precip'].max()),
                            'avg_coverage': float(phase_data['coverage_percent'].mean()) if 'coverage_percent' in phase_data.columns else None
                        }
                
                with open(phase_stats_output, 'w', encoding='utf-8') as f:
                    json.dump(phase_stats, f, indent=2, ensure_ascii=False)
                
                saved_files.append(phase_stats_output)
                print(f"✅ Statistiques phases: {Path(phase_stats_output).name}")
            
            print(f"\n📁 {len(saved_files)} fichiers sauvegardés dans outputs/")
            
            # Nettoyage mémoire final
            gc.collect()
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur sauvegarde: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_complete_analysis(self) -> bool:
        """Lance l'analyse complète - Version 4.0."""
        
        try:
            # Validation configuration
            if CONFIG_ADVANCED:
                validate_configuration()
            
            # Affichage informations projet
            print_project_info()
            
            # Créer structure de dossiers
            create_output_directories()
            
            print(f"\n🚀 DÉBUT DE L'ANALYSE COMPLÈTE - VERSION 4.0")
            print(f"📊 Modules chargés:")
            print(f"   • Configuration: {'Avancée' if CONFIG_ADVANCED else 'Basique'}")
            print(f"   • Climatologie: {'EnhancedClimatologyCalculator' if CLIMATOLOGY_ADVANCED else 'Basique'}")
            print(f"   • Détection: {'ExtremeEventDetector + SpatialMetrics' if DETECTION_ADVANCED else 'Basique'}")
            print(f"   • Classification: {'RainfallPhaseClassifier' if CLASSIFICATION_ADVANCED else 'Saisonnière simple'}")
            print(f"   • Géographie: {'SenegalGeography intégrée' if CLASSIFICATION_ADVANCED else 'Non disponible'}")
            print(f"   • Visualisations: {'EnhancedVisualizers' if VISUALIZATION_ADVANCED else 'Basiques'}")
            print(f"   • Rapports: {'EnhancedReportGenerators' if REPORTS_ADVANCED else 'Basiques'}")
            
            # Exécution des étapes
            start_time = datetime.now()
            
            steps = [
                ("Chargement des données", self.step_1_load_data),
                ("Calcul climatologie", self.step_2_calculate_climatology),
                ("Détection événements", self.step_3_detect_extreme_events),
                ("Classification phases", self.step_4_phase_classification),
                ("Génération visualisations", self.step_5_generate_visualizations),
                ("Génération rapports", lambda: self.step_6_generate_reports(self.validation_status)),
                ("Sauvegarde données", self.step_7_save_data)
            ]
            
            for i, (step_name, step_func) in enumerate(steps, 1):
                step_start = datetime.now()
                print(f"\n{'='*20} ÉTAPE {i}/{len(steps)}: {step_name.upper()} {'='*20}")
                
                if i == 4:  # Classification
                    self.validation_status = step_func()
                    success = self.validation_status != "ERREUR"
                elif i == 6:  # Rapports
                    success = step_func()
                else:
                    success = step_func()
                
                step_duration = (datetime.now() - step_start).total_seconds()
                
                if success:
                    print(f"✅ {step_name} terminée en {step_duration:.1f}s")
                else:
                    print(f"❌ Échec: {step_name}")
                    return False
            
            # Résumé final
            total_duration = (datetime.now() - start_time).total_seconds()
            self.print_final_summary(total_duration)
            
            return True
            
        except Exception as e:
            print(f"\n💥 ERREUR CRITIQUE DURANT L'ANALYSE: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def print_final_summary(self, duration: float):
        """Affiche le résumé final complet."""
        
        print("\n" + "="*80)
        print("🎉 ANALYSE COMPLÈTE TERMINÉE AVEC SUCCÈS - VERSION 4.0")
        print("="*80)
        
        n_events = len(self.extreme_events_df)
        
        print(f"⏱️  PERFORMANCE:")
        print(f"   Durée totale: {duration:.1f} secondes ({duration/60:.1f} minutes)")
        print(f"   Mémoire utilisée: {self.precip_data.nbytes / (1024**2):.1f} MB")
        print(f"   Efficacité: {n_events/duration:.1f} événements/seconde")
        
        print(f"\n📊 RÉSULTATS PRINCIPAUX:")
        print(f"   Événements détectés: {n_events}")
        print(f"   Période: {self.extreme_events_df.index.min().strftime('%Y-%m-%d')} à {self.extreme_events_df.index.max().strftime('%Y-%m-%d')}")
        print(f"   Fréquence: {n_events/(self.extreme_events_df['year'].max()-self.extreme_events_df['year'].min()+1):.1f} événements/an")
        print(f"   Validation: {getattr(self, 'validation_status', 'Non définie')}")
        
        # Statistiques d'intensité
        print(f"\n💧 PRÉCIPITATIONS:")
        print(f"   Moyenne: {self.extreme_events_df['max_precip'].mean():.2f} mm")
        print(f"   Médiane: {self.extreme_events_df['max_precip'].median():.2f} mm")
        print(f"   Maximum: {self.extreme_events_df['max_precip'].max():.2f} mm")
        print(f"   P95: {self.extreme_events_df['max_precip'].quantile(0.95):.2f} mm")
        
        # Distribution par phases
        if 'phase' in self.extreme_events_df.columns:
            print(f"\n🌧️  DISTRIBUTION PAR PHASES:")
            phase_counts = self.extreme_events_df['phase'].value_counts()
            for phase, count in phase_counts.items():
                pct = count / n_events * 100
                phase_info = RAINFALL_PHASES.get(phase, {})
                description = phase_info.get('description', phase)
                print(f"   {description}: {count} événements ({pct:.1f}%)")
        
        # Répartition géographique
        if 'centroid_region' in self.extreme_events_df.columns:
            print(f"\n🗺️  RÉPARTITION GÉOGRAPHIQUE (Top 5):")
            region_counts = self.extreme_events_df['centroid_region'].value_counts()
            for region, count in region_counts.head().items():
                pct = count / n_events * 100
                print(f"   {region}: {count} événements ({pct:.1f}%)")
        
        # Couverture spatiale
        if 'coverage_percent' in self.extreme_events_df.columns:
            print(f"\n📍 COUVERTURE SPATIALE:")
            print(f"   Moyenne: {self.extreme_events_df['coverage_percent'].mean():.2f}%")
            print(f"   Maximum: {self.extreme_events_df['coverage_percent'].max():.2f}%")
        
        print(f"\n📁 FICHIERS GÉNÉRÉS:")
        print(f"   • Dataset principal: {get_output_path('extreme_events')}")
        print(f"   • Rapport détaillé: {get_output_path('detection_report')}")
        print(f"   • Climatologie: {get_output_path('climatology')}")
        print(f"   • Anomalies: {get_output_path('anomalies')}")
        if 'phase' in self.extreme_events_df.columns:
            print(f"   • Statistiques phases: {get_output_path('phase_statistics')}")
        if hasattr(self, 'spatial_metrics') and self.spatial_metrics:
            print(f"   • Métriques spatiales: {get_output_path('spatial_metrics')}")
        print(f"   • Visualisations: outputs/visualizations/")
        print(f"   • Rapports: outputs/reports/")
        
        print(f"\n🎯 INNOVATIONS VERSION 4.0 APPLIQUÉES:")
        if CLASSIFICATION_ADVANCED:
            print(f"   ✅ Classification par phases de saison des pluies")
        if CLASSIFICATION_ADVANCED and self.geography:
            print(f"   ✅ Géolocalisation automatique (régions/départements/zones)")
        if DETECTION_ADVANCED:
            print(f"   ✅ Métriques spatiales avancées avec courbure terrestre")
        if CLIMATOLOGY_ADVANCED:
            print(f"   ✅ Climatologie avec validation multi-critères")
        if VISUALIZATION_ADVANCED:
            print(f"   ✅ Visualisations thématiques par phases")
        if REPORTS_ADVANCED:
            print(f"   ✅ Rapports intelligents avec recommandations")
        
        print(f"\n🚀 ÉTAPES SUIVANTES RECOMMANDÉES:")
        print(f"   • Analyse des indices climatiques (SST, ENSO, IOD, AMO)")
        print(f"   • Développement de modèles prédictifs (ML/DL)")
        print(f"   • Validation croisée avec données in-situ")
        print(f"   • Extension vers d'autres pays sahéliens")
        print(f"   • Publication scientifique des résultats")
        
        print(f"\n💎 PLATEFORME PRÊTE POUR LA RECHERCHE AVANCÉE")

# ============================================================================
# FONCTION PRINCIPALE
# ============================================================================
def main():
    """Fonction principale du script - Version 4.0."""
    
    print("🌩️ DÉTECTION D'ÉVÉNEMENTS EXTRÊMES - SÉNÉGAL")
    print("VERSION 4.0 COMPLÈTE AVEC ARCHITECTURE MODULAIRE AVANCÉE")
    print("="*80)
    print("Innovations:")
    print("• Classification par phases de saison des pluies (3 phases + hors saison)")
    print("• Références géographiques automatiques (14 régions + départements)")
    print("• Métriques spatiales avancées avec courbure terrestre")
    print("• Validation climatologique multi-critères")
    print("• Rapports intelligents avec recommandations adaptatives")
    print("• Visualisations thématiques multi-échelles")
    print("="*80)
    
    try:
        # ====================================================================
        # 1. VALIDATION DES PRÉREQUIS ET CONFIGURATION
        # ====================================================================
        
        print("\n🔧 INITIALISATION ET VALIDATION")
        print("-" * 50)
        
        # Déterminer le fichier CHIRPS à utiliser
        chirps_file = None
        
        # Option 1: Argument en ligne de commande
        if len(sys.argv) > 1:
            chirps_file = sys.argv[1]
            print(f"📁 Fichier CHIRPS spécifié: {chirps_file}")
        
        # Option 2: Fichier configuré
        elif os.path.exists(str(CHIRPS_FILEPATH)):
            chirps_file = str(CHIRPS_FILEPATH)
            print(f"📁 Fichier CHIRPS configuré: {chirps_file}")
        
        # Option 3: Recherche automatique
        else:
            possible_paths = [
                "/app/data/raw/chirps_WA_1981_2023_dayly.mat",
                "data/raw/chirps_WA_1981_2023_dayly.mat",
                "chirps_WA_1981_2023_dayly.mat",
                "../data/chirps_WA_1981_2023_dayly.mat"
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    chirps_file = path
                    print(f"📁 Fichier CHIRPS trouvé automatiquement: {chirps_file}")
                    break
        
        # Validation finale du fichier
        if not chirps_file or not os.path.exists(chirps_file):
            print("❌ ERREUR: Fichier CHIRPS non trouvé!")
            print("\n🔍 Solutions possibles:")
            print("   1. Spécifier le chemin: python scripts/01_detection_extremes.py /chemin/vers/chirps.mat")
            print("   2. Placer le fichier dans: data/raw/chirps_WA_1981_2023_dayly.mat")
            print("   3. Configurer CHIRPS_FILEPATH dans src/config/settings.py")
            print("\n📥 Télécharger CHIRPS depuis: https://data.chc.ucsb.edu/products/CHIRPS-2.0/")
            return False
        
        # Validation des permissions
        if not os.access(chirps_file, os.R_OK):
            print(f"❌ ERREUR: Permissions insuffisantes pour lire {chirps_file}")
            return False
        
        # Validation de la taille (doit être > 100MB pour les données complètes)
        file_size_mb = os.path.getsize(chirps_file) / (1024**2)
        if file_size_mb < 100:
            print(f"⚠️ ATTENTION: Fichier CHIRPS petit ({file_size_mb:.1f} MB)")
            print("   Les données peuvent être incomplètes")
        else:
            print(f"✅ Fichier CHIRPS validé ({file_size_mb:.1f} MB)")
        
        # Validation de l'espace disque disponible
        import shutil
        disk_space_gb = shutil.disk_usage('.').free / (1024**3)
        if disk_space_gb < 1:
            print(f"⚠️ ATTENTION: Espace disque faible ({disk_space_gb:.1f} GB)")
        else:
            print(f"✅ Espace disque suffisant ({disk_space_gb:.1f} GB)")
        
        # ====================================================================
        # 2. AFFICHAGE DE LA CONFIGURATION DÉTECTÉE
        # ====================================================================
        
        print(f"\n📊 CONFIGURATION DÉTECTÉE")
        print("-" * 30)
        print(f"🐍 Python: {sys.version.split()[0]}")
        print(f"💻 Plateforme: {sys.platform}")
        print(f"📁 Répertoire: {Path.cwd()}")
        print(f"🧠 Modules avancés:")
        
        modules_status = {
            "Configuration": CONFIG_ADVANCED,
            "Loader": LOADER_ADVANCED,
            "Climatologie": CLIMATOLOGY_ADVANCED,
            "Détection": DETECTION_ADVANCED,
            "Classification": CLASSIFICATION_ADVANCED,
            "Visualisation": VISUALIZATION_ADVANCED,
            "Rapports": REPORTS_ADVANCED
        }
        
        advanced_count = sum(modules_status.values())
        for module, status in modules_status.items():
            status_icon = "✅" if status else "⚠️"
            status_text = "Avancé" if status else "Basique"
            print(f"   {status_icon} {module}: {status_text}")
        
        print(f"\n🎯 Niveau d'analyse: {advanced_count}/7 modules avancés")
        if advanced_count >= 6:
            analysis_level = "RECHERCHE AVANCÉE"
        elif advanced_count >= 4:
            analysis_level = "ANALYSE COMPLÈTE"
        elif advanced_count >= 2:
            analysis_level = "ANALYSE STANDARD"
        else:
            analysis_level = "ANALYSE BASIQUE"
        print(f"   Capacité: {analysis_level}")
        
        # ====================================================================
        # 3. INITIALISATION DE L'ANALYSEUR
        # ====================================================================
        
        print(f"\n🚀 INITIALISATION DE L'ANALYSEUR")
        print("-" * 40)
        
        # Estimation de la mémoire nécessaire
        expected_memory_mb = file_size_mb * 2.5  # Facteur empirique
        print(f"📏 Mémoire estimée nécessaire: {expected_memory_mb:.0f} MB")
        
        # Créer l'analyseur
        analyzer = AdvancedExtremeEventsAnalyzer(chirps_file)
        
        # ====================================================================
        # 4. CONFIRMATION UTILISATEUR (en mode interactif)
        # ====================================================================
        
        if len(sys.argv) == 1 and sys.stdin.isatty():  # Mode interactif
            print(f"\n❓ CONFIRMATION D'EXÉCUTION")
            print("-" * 30)
            print(f"Fichier CHIRPS: {Path(chirps_file).name}")
            print(f"Niveau d'analyse: {analysis_level}")
            print(f"Durée estimée: 2-10 minutes")
            print(f"Espace nécessaire: ~{expected_memory_mb:.0f} MB")
            
            confirm = input("\n🔄 Lancer l'analyse complète? (o/N): ").strip().lower()
            if confirm not in ['o', 'oui', 'y', 'yes']:
                print("❌ Analyse annulée par l'utilisateur")
                return False
        
        # ====================================================================
        # 5. LANCEMENT DE L'ANALYSE COMPLÈTE
        # ====================================================================
        
        print(f"\n🎬 DÉBUT DE L'ANALYSE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # Timer global
        analysis_start = datetime.now()
        
        # Exécuter l'analyse
        success = analyzer.run_complete_analysis()
        
        # ====================================================================
        # 6. GESTION DES RÉSULTATS
        # ====================================================================
        
        analysis_duration = (datetime.now() - analysis_start).total_seconds()
        
        if success:
            print(f"\n🎊 ANALYSE RÉUSSIE EN {analysis_duration:.1f} SECONDES")
            print("="*80)
            
            # Statistiques finales avancées
            if hasattr(analyzer, 'extreme_events_df') and not analyzer.extreme_events_df.empty:
                n_events = len(analyzer.extreme_events_df)
                years_span = analyzer.extreme_events_df['year'].max() - analyzer.extreme_events_df['year'].min() + 1
                frequency = n_events / years_span
                
                print(f"📈 MÉTRIQUES DE PERFORMANCE:")
                print(f"   • Efficacité temporelle: {n_events/analysis_duration:.2f} événements/seconde")
                print(f"   • Fréquence historique: {frequency:.2f} événements/an")
                print(f"   • Couverture temporelle: {years_span} années")
                
                # Top événements
                print(f"\n🏆 TOP 5 ÉVÉNEMENTS EXTRÊMES:")
                top_events = analyzer.extreme_events_df.head(5)
                for i, (date, event) in enumerate(top_events.iterrows(), 1):
                    intensity = event['max_precip']
                    coverage = event.get('coverage_percent', 0)
                    phase = event.get('phase', 'Inconnue')
                    
                    # Emoji selon l'intensité
                    if intensity > 100:
                        emoji = "🌊"  # Déluge
                    elif intensity > 75:
                        emoji = "⛈️"   # Orage intense
                    elif intensity > 50:
                        emoji = "🌧️"   # Pluie forte
                    else:
                        emoji = "💧"   # Pluie
                    
                    print(f"   {i}. {emoji} {date.strftime('%Y-%m-%d')}: {intensity:.1f}mm "
                          f"({coverage:.1f}% zone) - {phase}")
            
            # ====================================================================
            # 7. RECOMMANDATIONS INTELLIGENTES
            # ====================================================================
            
            print(f"\n🎯 RECOMMANDATIONS POUR LA SUITE:")
            print("-" * 40)
            
            if advanced_count >= 6:
                print("🔬 RECHERCHE AVANCÉE - Prêt pour publication:")
                print("   • Analyser les téléconnexions climatiques (ENSO, IOD, AMO)")
                print("   • Développer des modèles prédictifs ML/DL")
                print("   • Étendre à l'Afrique de l'Ouest complète")
                print("   • Intégrer des données satellitaires complémentaires")
            elif advanced_count >= 4:
                print("📊 ANALYSE COMPLÈTE - Approfondir l'étude:")
                print("   • Valider avec données pluviométriques in-situ")
                print("   • Analyser les impacts socio-économiques")
                print("   • Étudier les tendances à long terme")
            else:
                print("🔧 ANALYSE BASIQUE - Améliorer la configuration:")
                print("   • Installer les modules avancés manquants")
                print("   • Configurer la géolocalisation automatique")
                print("   • Activer les visualisations avancées")
            
            # ====================================================================
            # 8. INSTRUCTIONS DE CONSULTATION
            # ====================================================================
            
            print(f"\n📋 CONSULTATION DES RÉSULTATS:")
            print("-" * 35)
            print(f"📊 Dataset principal: {get_output_path('extreme_events')}")
            print(f"📄 Rapport détaillé: {get_output_path('detection_report')}")
            print(f"📈 Visualisations: outputs/visualizations/")
            print(f"🗂️  Données brutes: outputs/data/")
            
            if advanced_count >= 4:
                print(f"\n💡 FICHIERS SPÉCIALISÉS GÉNÉRÉS:")
                if CLASSIFICATION_ADVANCED:
                    print(f"   • Statistiques par phases: {get_output_path('phase_statistics')}")
                if DETECTION_ADVANCED:
                    print(f"   • Métriques spatiales: {get_output_path('spatial_metrics')}")
                print(f"   • Climatologie: {get_output_path('climatology')}")
                print(f"   • Anomalies: {get_output_path('anomalies')}")
            
            print(f"\n🔄 PROCHAINES EXÉCUTIONS:")
            print(f"   • Même analyse: python scripts/01_detection_extremes.py")
            print(f"   • Autre fichier: python scripts/01_detection_extremes.py /path/to/data.mat")
            print(f"   • Configuration: modifier src/config/settings.py")
            
            return True
            
        else:
            print(f"\n💥 ÉCHEC DE L'ANALYSE APRÈS {analysis_duration:.1f} SECONDES")
            print("="*80)
            
            print(f"🔍 DIAGNOSTIC:")
            
            # Diagnostic du problème
            if not hasattr(analyzer, 'precip_data') or analyzer.precip_data is None:
                print("   ❌ Problème de chargement des données CHIRPS")
                print("   💡 Vérifier le format et l'intégrité du fichier")
            elif not hasattr(analyzer, 'climatology') or analyzer.climatology is None:
                print("   ❌ Problème de calcul climatologique")
                print("   💡 Vérifier la cohérence temporelle des données")
            elif not hasattr(analyzer, 'extreme_events_df') or analyzer.extreme_events_df is None:
                print("   ❌ Problème de détection d'événements")
                print("   💡 Ajuster les seuils de détection")
            else:
                print("   ❌ Erreur durant la génération des sorties")
                print("   💡 Vérifier les permissions d'écriture")
            
            print(f"\n🛠️  SOLUTIONS:")
            print(f"   1. Réessayer avec des modules basiques")
            print(f"   2. Vérifier l'intégrité du fichier CHIRPS")
            print(f"   3. Libérer de l'espace disque")
            print(f"   4. Consulter les logs détaillés ci-dessus")
            
            return False
    
    except KeyboardInterrupt:
        print(f"\n\n⏹️  ANALYSE INTERROMPUE PAR L'UTILISATEUR")
        print("🔄 Pour reprendre, relancer le script")
        return False
    
    except MemoryError:
        print(f"\n\n💾 ERREUR: MÉMOIRE INSUFFISANTE")
        print("🔧 Solutions:")
        print("   • Fermer les autres applications")
        print("   • Utiliser un système avec plus de RAM")
        print("   • Traiter les données par chunks plus petits")
        return False
    
    except Exception as e:
        print(f"\n\n💥 ERREUR INATTENDUE: {e}")
        print("🐛 Rapport de bug:")
        import traceback
        traceback.print_exc()
        
        print(f"\n📧 Support:")
        print(f"   • Sauvegarder ce log complet")
        print(f"   • Vérifier les versions des dépendances")
        print(f"   • Contacter l'équipe de développement")
        
        return False

# ============================================================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================================================

if __name__ == "__main__":
    try:
        # Impression d'en-tête stylisée
        print("🌍 " + "="*76 + " 🌍")
        print("   ANALYSE CLIMATOLOGIQUE AVANCÉE - ÉVÉNEMENTS EXTRÊMES SÉNÉGAL")
        print("   Plateforme de recherche v4.0 - Architecture modulaire complète")
        print("🌍 " + "="*76 + " 🌍")
        
        # Configuration de l'encodage pour les sorties
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        
        # Lancement et gestion du code de sortie
        success = main()
        
        # Code de sortie approprié
        exit_code = 0 if success else 1
        
        # Message final
        if success:
            print(f"\n🎉 MISSION ACCOMPLIE! Code de sortie: {exit_code}")
            print("✨ Données prêtes pour la recherche climatologique avancée")
        else:
            print(f"\n❌ MISSION ÉCHOUÉE. Code de sortie: {exit_code}")
            print("🔄 Consulter les messages d'erreur et réessayer")
        
        print("🌍 " + "="*76 + " 🌍\n")
        
        # Nettoyage final de la mémoire
        import gc
        gc.collect()
        
        # Sortie propre
        sys.exit(exit_code)
        
    except Exception as critical_error:
        print(f"\n💀 ERREUR CRITIQUE AU DÉMARRAGE: {critical_error}")
        import traceback
        traceback.print_exc()
        sys.exit(2)  # Code d'erreur critique