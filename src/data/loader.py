# src/data/loader.py
"""
Module de chargement et préparation des données CHIRPS pour l'analyse des précipitations extrêmes au Sénégal.
"""

import numpy as np
import h5py
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
import warnings
import sys
from pathlib import Path

# Ajouter le dossier parent au path pour les imports
try:
    from ..config.settings import SENEGAL_BOUNDS
except ImportError:
    # Import absolu comme fallback  
    try:
        from src.config.settings import SENEGAL_BOUNDS
    except ImportError:
        # Seulement en dernier recours
        SENEGAL_BOUNDS = {
            'lat_min': 12.0, 'lat_max': 17.0,
            'lon_min': -18.0, 'lon_max': -11.0
        }

warnings.filterwarnings('ignore')
class ChirpsDataLoader:
    """Classe pour le chargement et la préparation des données CHIRPS."""
    
    def __init__(self, file_path: str):
        """
        Initialise le loader avec le chemin du fichier CHIRPS.
        
        Args:
            file_path (str): Chemin vers le fichier CHIRPS .mat
        """
        self.file_path = file_path
        self.senegal_bounds = SENEGAL_BOUNDS
    
    def load_raw_data(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Charge les données brutes depuis le fichier CHIRPS.
        
        Returns:
            Tuple contenant (precip, lats, lons) ou (None, None, None) en cas d'erreur
        """
        print("[INFO] CHARGEMENT DES DONNÉES CHIRPS BRUTES")
        print("-" * 50)
        
        try:
            with h5py.File(self.file_path, 'r') as f:
                print(f"Clés disponibles: {list(f.keys())}")
                
                # Extraction des données
                precip = np.array(f.get('precip'))
                lats = np.array(f.get('latitude')).flatten()
                lons = np.array(f.get('longitude')).flatten()
                
                print(f"Forme des données: precip {precip.shape}, lats {lats.shape}, lons {lons.shape}")
                
                return precip, lats, lons
                
        except Exception as e:
            print(f"[ERREUR] Erreur lors du chargement: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None
    
    def create_date_series(self, n_days: int, start_year: int = 1981) -> list:
        """
        Crée une série de dates pour les données CHIRPS.
        
        Args:
            n_days (int): Nombre de jours dans la série
            start_year (int): Année de début (défaut: 1981)
            
        Returns:
            list: Liste des dates
        """
        start_date = datetime(start_year, 1, 1)
        dates = [start_date + timedelta(days=i) for i in range(n_days)]
        return dates
    
    def extract_region_data(self, precip: np.ndarray, lats: np.ndarray, 
                           lons: np.ndarray, bounds: Optional[Dict[str, float]] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Extrait les données pour une région spécifique.
        
        Args:
            precip (np.ndarray): Données de précipitation
            lats (np.ndarray): Latitudes
            lons (np.ndarray): Longitudes
            bounds (dict, optional): Limites géographiques
            
        Returns:
            Tuple contenant les données régionales (precip_region, lats_region, lons_region)
        """
        if bounds is None:
            bounds = self.senegal_bounds
        
        # Indices correspondant à la région
        lat_indices = np.where((lats >= bounds['lat_min']) & (lats <= bounds['lat_max']))[0]
        lon_indices = np.where((lons >= bounds['lon_min']) & (lons <= bounds['lon_max']))[0]
        
        # Extraction des données de la région
        region_precip = precip[:, lat_indices, :][:, :, lon_indices]
        region_lats = lats[lat_indices]
        region_lons = lons[lon_indices]
        
        return region_precip, region_lats, region_lons
    
    def validate_data_quality(self, precip_data: np.ndarray, dates: list) -> Dict[str, Any]:
        """
        Valide la qualité des données chargées.
        
        Args:
            precip_data (np.ndarray): Données de précipitation
            dates (list): Liste des dates
            
        Returns:
            dict: Statistiques de validation
        """
        total_values = precip_data.size
        nan_count = np.isnan(precip_data).sum()
        nan_percentage = (nan_count / total_values) * 100
        
        stats = {
            'total_values': total_values,
            'nan_count': nan_count,
            'nan_percentage': nan_percentage,
            'shape': precip_data.shape,
            'date_range': {
                'start': dates[0].strftime('%Y-%m-%d'),
                'end': dates[-1].strftime('%Y-%m-%d'),
                'duration_years': (dates[-1] - dates[0]).days / 365.25
            },
            'precipitation_stats': {
                'mean': np.nanmean(precip_data),
                'std': np.nanstd(precip_data),
                'min': np.nanmin(precip_data),
                'max': np.nanmax(precip_data)
            }
        }
        
        return stats
    
    def print_validation_summary(self, stats: Dict[str, Any], region_name: str = "Sénégal"):
        """
        Affiche un résumé de la validation des données.
        
        Args:
            stats (dict): Statistiques de validation
            region_name (str): Nom de la région
        """
        print(f"✅ Données du {region_name} extraites: {stats['shape']}")
        print(f"   Période: {stats['date_range']['start']} à {stats['date_range']['end']}")
        print(f"   Durée: {stats['date_range']['duration_years']:.1f} années")
        print(f"   Points de grille: {stats['shape'][1] * stats['shape'][2]} points")
        print(f"   Valeurs NaN: {stats['nan_count']:,} / {stats['total_values']:,} ({stats['nan_percentage']:.1f}%)")
        print(f"   Précipitation moyenne: {stats['precipitation_stats']['mean']:.2f} mm/jour")
        print(f"   Écart-type: {stats['precipitation_stats']['std']:.2f} mm/jour")
        print(f"   Min/Max: {stats['precipitation_stats']['min']:.1f} / {stats['precipitation_stats']['max']:.1f} mm/jour")
    
    def load_senegal_data(self) -> Tuple[Optional[np.ndarray], Optional[list], Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Charge et prépare les données CHIRPS spécifiquement pour le Sénégal.
        
        Returns:
            Tuple contenant (senegal_precip, dates, senegal_lats, senegal_lons)
        """
        print("🔄 CHARGEMENT DES DONNÉES CHIRPS - SÉNÉGAL")
        print("=" * 60)
        
        # 1. Charger les données brutes
        precip, lats, lons = self.load_raw_data()
        
        if precip is None:
            return None, None, None, None
        
        # 2. Créer la série de dates
        dates = self.create_date_series(precip.shape[0])
        
        # 3. Extraire les données du Sénégal
        senegal_precip, senegal_lats, senegal_lons = self.extract_region_data(precip, lats, lons)
        
        # 4. Valider la qualité des données
        stats = self.validate_data_quality(senegal_precip, dates)
        self.print_validation_summary(stats)
        
        return senegal_precip, dates, senegal_lats, senegal_lons


def load_chirps_senegal(file_path: str) -> Tuple[Optional[np.ndarray], Optional[list], Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Fonction de convenance pour charger les données CHIRPS du Sénégal.
    
    Args:
        file_path (str): Chemin vers le fichier CHIRPS
        
    Returns:
        Tuple contenant (precip_data, dates, lats, lons) ou (None, None, None, None) en cas d'erreur
    """
    loader = ChirpsDataLoader(file_path)
    return loader.load_senegal_data()


if __name__ == "__main__":
    # Test du module
    print("Test du module de chargement des données CHIRPS")
    print("=" * 60)
    
    # Vous pouvez tester avec votre fichier
    # file_path = 'data/raw/chirps_WA_1981_2023_dayly.mat'
    # loader = ChirpsDataLoader(file_path)
    # precip_data, dates, lats, lons = loader.load_senegal_data()
    
    print("Module chargé avec succès")
    print("Utilisez ChirpsDataLoader(file_path).load_senegal_data() pour charger vos données")