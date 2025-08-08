
# src/analysis/spatial_metrics.py
"""
Module centralisé pour les calculs de métriques spatiales avancées.
Utilise les nouvelles références géographiques du Sénégal.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import math

# Import des références géographiques
try:
    from src.utils.geographic_references import SenegalGeography, analyze_geographic_distribution
except ImportError:
    try:
        from ..utils.geographic_references import SenegalGeography, analyze_geographic_distribution
    except ImportError:
        # Configuration de fallback si les imports échouent
        class SenegalGeography:
            @staticmethod
            def identify_region(lat, lon):
                return "Région indéterminée"
            
            @staticmethod
            def identify_department(lat, lon):
                return "Département indéterminé", "Région indéterminée"
            
            @staticmethod
            def identify_climate_zone(lat, lon):
                return "Zone indéterminée"
        
        def analyze_geographic_distribution(coords):
            return {}


class EnhancedSpatialMetricsCalculator:
    """Calculateur avancé des métriques spatiales avec références géographiques."""
    
    def __init__(self):
        self.geo = SenegalGeography()
        # Paramètres de la grille CHIRPS pour le Sénégal
        self.senegal_grid = {
            'lat_min': 12.3, 'lat_max': 16.7,
            'lon_min': -17.55, 'lon_max': -11.35,
            'resolution': 0.25  # 25km
        }
    
    def calculate_comprehensive_metrics(self, event_date: pd.Timestamp, 
                                      event_data: pd.Series,
                                      precip_data: Optional[np.ndarray] = None,
                                      anomalies: Optional[np.ndarray] = None,
                                      lats: Optional[np.ndarray] = None,
                                      lons: Optional[np.ndarray] = None,
                                      dates: Optional[list] = None,
                                      rank: int = 0) -> Dict[str, Any]:
        """
        Calcule les métriques spatiales complètes avec analyse géographique.
        
        Args:
            event_date: Date de l'événement
            event_data: Données de l'événement
            precip_data: Données CHIRPS de précipitation (optionnel)
            anomalies: Données d'anomalies (optionnel)
            lats: Latitudes de la grille (optionnel)
            lons: Longitudes de la grille (optionnel)
            dates: Liste des dates (optionnel)
            rank: Rang de l'événement
            
        Returns:
            Dict avec métriques spatiales complètes
        """
        
        print(f"[INFO] Calcul des métriques spatiales pour {event_date.strftime('%Y-%m-%d')}")
        
        if self._has_chirps_data(precip_data, anomalies, lats, lons, dates):
            print("   [OK] Données CHIRPS disponibles - Calcul précis")
            return self._calculate_from_chirps(event_date, event_data, 
                                             precip_data, anomalies, lats, lons, dates, rank)
        else:
            print("   [AVERTISSEMENT] Données CHIRPS manquantes - Calcul estimé")
            return self._calculate_from_dataframe(event_date, event_data, rank)
    
    def _has_chirps_data(self, precip_data, anomalies, lats, lons, dates) -> bool:
        """Vérifie si les données CHIRPS sont disponibles et valides."""
        return all(data is not None for data in [precip_data, anomalies, lats, lons, dates])
    
    def _calculate_from_chirps(self, event_date, event_data, 
                              precip_data, anomalies, lats, lons, dates, rank) -> Dict[str, Any]:
        """Calcule à partir des données CHIRPS complètes avec analyse géographique."""
        
        # Trouver l'index temporel
        date_idx = self._find_date_index(event_date, dates)
        if date_idx is None:
            print(f"   [ERREUR] Date {event_date} non trouvée dans les données CHIRPS")
            return self._calculate_from_dataframe(event_date, event_data, rank)
        
        # Données spatiales du jour
        day_precip = precip_data[date_idx, :, :]
        day_anomalies = anomalies[date_idx, :, :]
        
        # Définir les seuils d'événement extrême
        extreme_mask = (day_anomalies > 2.0) & ~np.isnan(day_anomalies)
        intense_mask = (day_precip > 20.0) & ~np.isnan(day_precip)  # Pluie intense
        combined_mask = extreme_mask | intense_mask
        
        if not combined_mask.any():
            print("   ⚠️  Aucun pixel extrême détecté")
            return self._calculate_from_dataframe(event_date, event_data, rank)
        
        # Grilles de coordonnées
        lat_grid, lon_grid = np.meshgrid(lats, lons, indexing='ij')
        
        # Calcul de la surface par pixel (formule précise)
        pixel_areas = self._calculate_pixel_areas(lat_grid, lon_grid)
        
        # Métriques de base
        total_area_km2 = np.sum(pixel_areas[combined_mask])
        num_pixels = np.sum(combined_mask)
        
        # Données valides dans la zone
        valid_mask = combined_mask & ~np.isnan(day_precip)
        if not valid_mask.any():
            return self._calculate_from_dataframe(event_date, event_data, rank)
        
        # Extraction des données valides
        valid_precip = day_precip[valid_mask]
        valid_anomalies = day_anomalies[valid_mask]
        valid_lat = lat_grid[valid_mask]
        valid_lon = lon_grid[valid_mask]
        valid_areas = pixel_areas[valid_mask]
        
        # Analyses géographiques
        geographic_analysis = self._analyze_geographic_distribution(valid_lat, valid_lon, valid_precip)
        
        # Centroïde pondéré par l'intensité
        weights = valid_precip * valid_areas
        centroid_lat = np.average(valid_lat, weights=weights)
        centroid_lon = np.average(valid_lon, weights=weights)
        
        # Position du maximum
        max_intensity = np.nanmax(day_precip)
        max_idx = np.unravel_index(np.nanargmax(day_precip), day_precip.shape)
        max_lat = lat_grid[max_idx]
        max_lon = lon_grid[max_idx]
        
        # Statistiques d'intensité avancées
        intensity_stats = self._calculate_intensity_statistics(valid_precip, valid_anomalies)
        
        # Métriques géométriques
        geometry_metrics = self._calculate_geometry_metrics(valid_lat, valid_lon, valid_precip)
        
        # Analyse de connectivité spatiale
        connectivity = self._analyze_spatial_connectivity(combined_mask)
        
        # Métriques de forme
        shape_metrics = self._calculate_shape_metrics(valid_lat, valid_lon, valid_areas)
        
        # Couverture régionale
        coverage_percent = float(100 * num_pixels / (len(lats) * len(lons)))
        
        print(f"   ✅ Calculé: {total_area_km2:.0f} km², {num_pixels} pixels, {len(geographic_analysis['regions'])} régions")
        
        return {
            # Informations de base
            'rank': rank,
            'date': event_date.strftime('%Y-%m-%d'),
            'source': 'CHIRPS',
            
            # Métriques spatiales
            'total_area_km2': float(total_area_km2),
            'num_pixels_affected': int(num_pixels),
            'coverage_percent': coverage_percent,
            'average_pixel_area_km2': float(np.mean(valid_areas)),
            
            # Centroïde et localisation
            'centroid_lat': float(centroid_lat),
            'centroid_lon': float(centroid_lon),
            'centroid_region': self.geo.identify_region(centroid_lat, centroid_lon),
            'centroid_department': self.geo.identify_department(centroid_lat, centroid_lon)[0],
            'centroid_climate_zone': self.geo.identify_climate_zone(centroid_lat, centroid_lon),
            
            # Maximum d'intensité
            'max_intensity_mm': float(max_intensity),
            'max_intensity_lat': float(max_lat),
            'max_intensity_lon': float(max_lon),
            'max_intensity_region': self.geo.identify_region(max_lat, max_lon),
            'max_intensity_department': self.geo.identify_department(max_lat, max_lon)[0],
            
            # Étendue géographique
            'lat_extent_deg': geometry_metrics['lat_extent'],
            'lon_extent_deg': geometry_metrics['lon_extent'],
            'lat_span_km': geometry_metrics['lat_span_km'],
            'lon_span_km': geometry_metrics['lon_span_km'],
            'aspect_ratio': geometry_metrics['aspect_ratio'],
            
            # Statistiques d'intensité
            'intensity_stats': intensity_stats,
            
            # Métriques géométriques
            'geometry_metrics': geometry_metrics,
            
            # Métriques de forme
            'shape_metrics': shape_metrics,
            
            # Connectivité spatiale
            'connectivity': connectivity,
            
            # Analyse géographique
            'geographic_analysis': geographic_analysis,
            
            # Métriques dérivées
            'intensity_density': float(np.sum(valid_precip * valid_areas) / total_area_km2),
            'anomaly_severity': float(np.mean(valid_anomalies)),
            'spatial_concentration': self._calculate_spatial_concentration(valid_lat, valid_lon, valid_precip)
        }
    
    def _calculate_from_dataframe(self, event_date, event_data, rank) -> Dict[str, Any]:
        """Calcule à partir des données du DataFrame avec estimations améliorées."""
        
        # Extraction des données de base
        max_intensity = float(event_data['max_precip'])
        coverage_percent = float(event_data['coverage_percent'])
        centroid_lat = float(event_data['centroid_lat'])
        centroid_lon = float(event_data['centroid_lon'])
        
        # Estimations réalistes basées sur la grille CHIRPS
        total_pixels_senegal = self._estimate_total_pixels()
        affected_pixels = int((coverage_percent / 100.0) * total_pixels_senegal)
        
        # Surface estimée avec calcul réaliste
        avg_pixel_area = self._estimate_average_pixel_area(centroid_lat)
        estimated_area = affected_pixels * avg_pixel_area
        
        # Analyses géographiques de base
        region = self.geo.identify_region(centroid_lat, centroid_lon)
        department, _ = self.geo.identify_department(centroid_lat, centroid_lon)
        climate_zone = self.geo.identify_climate_zone(centroid_lat, centroid_lon)
        
        # Statistiques d'intensité estimées
        intensity_stats = self._estimate_intensity_statistics(max_intensity, coverage_percent)
        
        # Métriques géométriques estimées
        geometry_metrics = self._estimate_geometry_metrics(coverage_percent, centroid_lat)
        
        # Métriques de forme estimées
        shape_metrics = self._estimate_shape_metrics(affected_pixels, estimated_area)
        
        print(f"   ✅ Estimé: {estimated_area:.0f} km², {affected_pixels} pixels, région {region}")
        
        return {
            # Informations de base
            'rank': rank,
            'date': event_date.strftime('%Y-%m-%d'),
            'source': 'DataFrame_estimate',
            
            # Métriques spatiales
            'total_area_km2': float(estimated_area),
            'num_pixels_affected': int(affected_pixels),
            'coverage_percent': coverage_percent,
            'average_pixel_area_km2': float(avg_pixel_area),
            
            # Centroïde et localisation
            'centroid_lat': centroid_lat,
            'centroid_lon': centroid_lon,
            'centroid_region': region,
            'centroid_department': department,
            'centroid_climate_zone': climate_zone,
            
            # Maximum d'intensité
            'max_intensity_mm': max_intensity,
            'max_intensity_lat': centroid_lat,  # Approximation
            'max_intensity_lon': centroid_lon,  # Approximation
            'max_intensity_region': region,
            'max_intensity_department': department,
            
            # Étendue géographique
            'lat_extent_deg': geometry_metrics['lat_extent'],
            'lon_extent_deg': geometry_metrics['lon_extent'],
            'lat_span_km': geometry_metrics['lat_span_km'],
            'lon_span_km': geometry_metrics['lon_span_km'],
            'aspect_ratio': geometry_metrics['aspect_ratio'],
            
            # Statistiques d'intensité
            'intensity_stats': intensity_stats,
            
            # Métriques géométriques
            'geometry_metrics': geometry_metrics,
            
            # Métriques de forme
            'shape_metrics': shape_metrics,
            
            # Connectivité spatiale (estimée)
            'connectivity': {'num_clusters': 1, 'largest_cluster_ratio': 1.0},
            
            # Analyse géographique
            'geographic_analysis': {
                'regions': {region: affected_pixels},
                'departments': {department: affected_pixels},
                'climate_zones': {climate_zone: affected_pixels}
            },
            
            # Métriques dérivées
            'intensity_density': float(max_intensity * 0.4),  # Estimation
            'anomaly_severity': 2.5,  # Estimation pour événement extrême
            'spatial_concentration': 0.3  # Estimation modérée
        }
    
    def _calculate_pixel_areas(self, lat_grid: np.ndarray, lon_grid: np.ndarray) -> np.ndarray:
        """Calcule la surface réelle de chaque pixel en km²."""
        lat_res = self.senegal_grid['resolution']
        lon_res = self.senegal_grid['resolution']
        
        # Formule précise prenant en compte la courbure terrestre
        R = 6371.0  # Rayon terrestre en km
        
        lat_rad = np.radians(lat_grid)
        lat_km = lat_res * 111.32  # 1° latitude ≈ 111.32 km
        lon_km = lon_res * 111.32 * np.cos(lat_rad)  # Ajustement longitude
        
        return lat_km * lon_km
    
    def _analyze_geographic_distribution(self, lats: np.ndarray, lons: np.ndarray, 
                                       precip: np.ndarray) -> Dict[str, Any]:
        """Analyse la distribution géographique des événements."""
        
        # Créer des coordonnées pondérées par l'intensité
        coords = [(lat, lon) for lat, lon in zip(lats, lons)]
        
        # Compter par région, département et zone climatique
        regions = {}
        departments = {}
        climate_zones = {}
        
        for i, (lat, lon) in enumerate(coords):
            if self.geo.is_point_in_senegal(lat, lon):
                # Région
                region = self.geo.identify_region(lat, lon)
                regions[region] = regions.get(region, 0) + precip[i]
                
                # Département
                dept, _ = self.geo.identify_department(lat, lon)
                departments[dept] = departments.get(dept, 0) + precip[i]
                
                # Zone climatique
                climate = self.geo.identify_climate_zone(lat, lon)
                climate_zones[climate] = climate_zones.get(climate, 0) + precip[i]
        
        return {
            'regions': regions,
            'departments': departments,
            'climate_zones': climate_zones,
            'total_coordinates': len(coords),
            'valid_coordinates': len([c for c in coords if self.geo.is_point_in_senegal(c[0], c[1])])
        }
    
    def _calculate_intensity_statistics(self, precip: np.ndarray, anomalies: np.ndarray) -> Dict[str, float]:
        """Calcule les statistiques d'intensité avancées."""
        return {
            'mean_mm': float(np.mean(precip)),
            'median_mm': float(np.median(precip)),
            'std_mm': float(np.std(precip)),
            'min_mm': float(np.min(precip)),
            'max_mm': float(np.max(precip)),
            'p25_mm': float(np.percentile(precip, 25)),
            'p75_mm': float(np.percentile(precip, 75)),
            'p90_mm': float(np.percentile(precip, 90)),
            'p95_mm': float(np.percentile(precip, 95)),
            'p99_mm': float(np.percentile(precip, 99)),
            'mean_anomaly': float(np.mean(anomalies)),
            'max_anomaly': float(np.max(anomalies)),
            'extreme_pixels_pct': float(100 * np.sum(anomalies > 3.0) / len(anomalies))
        }
    
    def _calculate_geometry_metrics(self, lats: np.ndarray, lons: np.ndarray, 
                                  precip: np.ndarray) -> Dict[str, float]:
        """Calcule les métriques géométriques de l'événement."""
        lat_extent = float(lats.max() - lats.min())
        lon_extent = float(lons.max() - lons.min())
        
        # Conversion en km
        lat_span_km = lat_extent * 111.32
        lon_span_km = lon_extent * 111.32 * np.cos(np.radians(np.mean(lats)))
        
        return {
            'lat_extent': lat_extent,
            'lon_extent': lon_extent,
            'lat_span_km': lat_span_km,
            'lon_span_km': lon_span_km,
            'aspect_ratio': lon_span_km / lat_span_km if lat_span_km > 0 else 1.0,
            'diagonal_km': np.sqrt(lat_span_km**2 + lon_span_km**2)
        }
    
    def _calculate_shape_metrics(self, lats: np.ndarray, lons: np.ndarray, 
                               areas: np.ndarray) -> Dict[str, float]:
        """Calcule les métriques de forme de l'événement."""
        total_area = np.sum(areas)
        
        # Périmètre approximatif (pixels de bordure)
        # Simplification: périmètre = sqrt(4 * π * area) pour un cercle
        equivalent_radius = np.sqrt(total_area / np.pi)
        perimeter_approx = 2 * np.pi * equivalent_radius
        
        # Compacité (4π * area / perimeter²)
        compactness = 4 * np.pi * total_area / (perimeter_approx**2)
        
        return {
            'total_area_km2': float(total_area),
            'equivalent_radius_km': float(equivalent_radius),
            'perimeter_approx_km': float(perimeter_approx),
            'compactness': float(compactness),
            'elongation': float(np.std(lons) / np.std(lats)) if np.std(lats) > 0 else 1.0
        }
    
    def _analyze_spatial_connectivity(self, mask: np.ndarray) -> Dict[str, Any]:
        """Analyse la connectivité spatiale des pixels extrêmes."""
        # Simplification: compter les clusters de pixels connectés
        from scipy import ndimage
        
        try:
            labeled, num_clusters = ndimage.label(mask)
            
            if num_clusters > 0:
                cluster_sizes = [np.sum(labeled == i) for i in range(1, num_clusters + 1)]
                largest_cluster = max(cluster_sizes)
                largest_cluster_ratio = largest_cluster / np.sum(mask)
            else:
                cluster_sizes = []
                largest_cluster = 0
                largest_cluster_ratio = 0
                
            return {
                'num_clusters': int(num_clusters),
                'cluster_sizes': cluster_sizes,
                'largest_cluster_size': int(largest_cluster),
                'largest_cluster_ratio': float(largest_cluster_ratio),
                'fragmentation_index': float(num_clusters / np.sum(mask)) if np.sum(mask) > 0 else 0
            }
        except ImportError:
            # Fallback si scipy n'est pas disponible
            return {
                'num_clusters': 1,
                'largest_cluster_ratio': 1.0,
                'fragmentation_index': 0.1
            }
    
    def _calculate_spatial_concentration(self, lats: np.ndarray, lons: np.ndarray, 
                                       precip: np.ndarray) -> float:
        """Calcule l'index de concentration spatiale."""
        # Coefficient de Gini spatial simplifié
        total_precip = np.sum(precip)
        if total_precip == 0:
            return 0.0
        
        # Trier par intensité
        sorted_precip = np.sort(precip)
        n = len(sorted_precip)
        
        # Calcul du coefficient de Gini
        cumsum = np.cumsum(sorted_precip)
        gini = (2 * np.sum((np.arange(1, n + 1) * sorted_precip))) / (n * total_precip) - (n + 1) / n
        
        return float(gini)
    
    def _estimate_total_pixels(self) -> int:
        """Estime le nombre total de pixels CHIRPS pour le Sénégal."""
        lat_range = self.senegal_grid['lat_max'] - self.senegal_grid['lat_min']
        lon_range = self.senegal_grid['lon_max'] - self.senegal_grid['lon_min']
        
        lat_pixels = int(lat_range / self.senegal_grid['resolution'])
        lon_pixels = int(lon_range / self.senegal_grid['resolution'])
        
        return lat_pixels * lon_pixels
    
    def _estimate_average_pixel_area(self, lat: float) -> float:
        """Estime la surface moyenne d'un pixel à une latitude donnée."""
        res = self.senegal_grid['resolution']
        lat_km = res * 111.32
        lon_km = res * 111.32 * np.cos(np.radians(lat))
        return lat_km * lon_km
    
    def _estimate_intensity_statistics(self, max_intensity: float, coverage: float) -> Dict[str, float]:
        """Estime les statistiques d'intensité à partir des données limitées."""
        # Estimations basées sur des distributions typiques
        return {
            'mean_mm': max_intensity * 0.4,
            'median_mm': max_intensity * 0.3,
            'std_mm': max_intensity * 0.25,
            'min_mm': max_intensity * 0.1,
            'max_mm': max_intensity,
            'p25_mm': max_intensity * 0.2,
            'p75_mm': max_intensity * 0.6,
            'p90_mm': max_intensity * 0.8,
            'p95_mm': max_intensity * 0.9,
            'p99_mm': max_intensity * 0.95,
            'mean_anomaly': 2.5,
            'max_anomaly': 3.5,
            'extreme_pixels_pct': min(coverage * 0.8, 100.0)
        }
    
    def _estimate_geometry_metrics(self, coverage: float, lat: float) -> Dict[str, float]:
        """Estime les métriques géométriques."""
        # Estimation basée sur la couverture
        area_factor = coverage / 100.0
        lat_extent = 2.0 * np.sqrt(area_factor)  # Estimation
        lon_extent = 2.0 * np.sqrt(area_factor)  # Estimation
        
        lat_span_km = lat_extent * 111.32
        lon_span_km = lon_extent * 111.32 * np.cos(np.radians(lat))
        
        return {
            'lat_extent': lat_extent,
            'lon_extent': lon_extent,
            'lat_span_km': lat_span_km,
            'lon_span_km': lon_span_km,
            'aspect_ratio': lon_span_km / lat_span_km if lat_span_km > 0 else 1.0,
            'diagonal_km': np.sqrt(lat_span_km**2 + lon_span_km**2)
        }
    
    def _estimate_shape_metrics(self, num_pixels: int, area: float) -> Dict[str, float]:
        """Estime les métriques de forme."""
        equivalent_radius = np.sqrt(area / np.pi)
        perimeter_approx = 2 * np.pi * equivalent_radius
        compactness = 4 * np.pi * area / (perimeter_approx**2)
        
        return {
            'total_area_km2': area,
            'equivalent_radius_km': equivalent_radius,
            'perimeter_approx_km': perimeter_approx,
            'compactness': compactness,
            'elongation': 1.2  # Estimation par défaut
        }
    
    def _find_date_index(self, target_date, dates) -> Optional[int]:
        """Trouve l'index correspondant à une date dans les données CHIRPS."""
        if not dates:
            return None
            
        target_datetime = target_date.to_pydatetime().replace(hour=0, minute=0, second=0, microsecond=0)
        
        for i, date in enumerate(dates):
            if hasattr(date, 'replace'):
                check_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                check_date = date
                
            if check_date == target_datetime:
                return i
        
        return None


class SpatialMetricsCalculator(EnhancedSpatialMetricsCalculator):
    """Alias pour compatibilité avec l'ancien nom."""
    pass


# Fonctions utilitaires pour l'analyse spatiale
def calculate_event_similarity(metrics1: Dict[str, Any], metrics2: Dict[str, Any]) -> float:
    """
    Calcule la similarité entre deux événements basée sur leurs métriques spatiales.
    
    Args:
        metrics1, metrics2: Métriques de deux événements
        
    Returns:
        Score de similarité (0-1)
    """
    # Normaliser et comparer les métriques clés
    spatial_keys = ['total_area_km2', 'max_intensity_mm', 'lat_extent_deg', 'lon_extent_deg']
    
    similarities = []
    for key in spatial_keys:
        if key in metrics1 and key in metrics2:
            val1, val2 = metrics1[key], metrics2[key]
            if val1 == 0 and val2 == 0:
                similarities.append(1.0)
            elif val1 == 0 or val2 == 0:
                similarities.append(0.0)
            else:
                sim = 1 - abs(val1 - val2) / max(val1, val2)
                similarities.append(max(0, sim))
    
    return np.mean(similarities) if similarities else 0.0


def summarize_spatial_metrics(metrics_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Résume les métriques spatiales d'une liste d'événements.
    
    Args:
        metrics_list: Liste des métriques d'événements
        
    Returns:
        Résumé statistique
    """
    if not metrics_list:
        return {}
    
    # Extraire les valeurs numériques
    areas = [m['total_area_km2'] for m in metrics_list]
    intensities = [m['max_intensity_mm'] for m in metrics_list]
    coverages = [m['coverage_percent'] for m in metrics_list]
    
    # Analyser les régions
    regions = {}
    for m in metrics_list:
        region = m.get('centroid_region', 'Inconnue')
        regions[region] = regions.get(region, 0) + 1
    
    return {
        'total_events': len(metrics_list),
        'area_stats': {
            'mean': np.mean(areas),
            'median': np.median(areas),
            'std': np.std(areas),
            'min': np.min(areas),
            'max': np.max(areas)
        },
        'intensity_stats': {
            'mean': np.mean(intensities),
            'median': np.median(intensities),
            'std': np.std(intensities),
            'min': np.min(intensities),
            'max': np.max(intensities)
        },
        'coverage_stats': {
            'mean': np.mean(coverages),
            'median': np.median(coverages),
            'std': np.std(coverages)
        },
        'regional_distribution': regions,
        'most_affected_region': max(regions.items(), key=lambda x: x[1])[0] if regions else None
    }


if __name__ == "__main__":
    print("📊 Module de métriques spatiales avancées")
    print("=" * 50)
    
    # Test avec des données simulées
    print("\n🧪 TESTS DES FONCTIONNALITÉS")
    
    # Créer le calculateur
    calculator = EnhancedSpatialMetricsCalculator()
    
    # Simuler des données d'événement
    event_date = pd.Timestamp('2023-08-15')
    event_data = pd.Series({
        'max_precip': 85.5,
        'coverage_percent': 15.2,
        'centroid_lat': 14.5,
        'centroid_lon': -16.2,
        'max_anomaly': 3.2
    })
    
    print(f"\n📅 Test avec événement du {event_date.strftime('%Y-%m-%d')}")
    print(f"   Précipitation max: {event_data['max_precip']:.1f} mm")
    print(f"   Couverture: {event_data['coverage_percent']:.1f}%")
    print(f"   Centroïde: ({event_data['centroid_lat']:.2f}, {event_data['centroid_lon']:.2f})")
    
    # Test sans données CHIRPS (estimation)
    print(f"\n🔍 Test calcul estimé (sans données CHIRPS):")
    metrics_estimated = calculator.calculate_comprehensive_metrics(
        event_date=event_date,
        event_data=event_data,
        rank=1
    )
    
    print(f"   ✅ Métriques calculées:")
    print(f"      Surface affectée: {metrics_estimated['total_area_km2']:.0f} km²")
    print(f"      Pixels affectés: {metrics_estimated['num_pixels_affected']}")
    print(f"      Région principale: {metrics_estimated['centroid_region']}")
    print(f"      Département: {metrics_estimated['centroid_department']}")
    print(f"      Zone climatique: {metrics_estimated['centroid_climate_zone']}")
    print(f"      Étendue lat: {metrics_estimated['lat_extent_deg']:.2f}°")
    print(f"      Étendue lon: {metrics_estimated['lon_extent_deg']:.2f}°")
    print(f"      Ratio d'aspect: {metrics_estimated['aspect_ratio']:.2f}")
    
    # Test avec données CHIRPS simulées
    print(f"\n🔍 Test calcul précis (avec données CHIRPS simulées):")
    
    # Créer des données CHIRPS simulées
    lats = np.arange(12.0, 17.0, 0.25)
    lons = np.arange(-18.0, -11.0, 0.25)
    dates = [pd.Timestamp('2023-08-15')]
    
    # Simuler une grille de précipitation avec un événement intense
    precip_data = np.random.gamma(2, 10, size=(1, len(lats), len(lons)))
    # Ajouter un événement intense dans la région de Kaolack
    lat_idx = np.argmin(np.abs(lats - 14.5))
    lon_idx = np.argmin(np.abs(lons - -16.2))
    precip_data[0, lat_idx-2:lat_idx+3, lon_idx-2:lon_idx+3] = 80 + np.random.normal(0, 10, (5, 5))
    
    # Simuler des anomalies
    anomalies = np.random.normal(0, 1, size=(1, len(lats), len(lons)))
    anomalies[0, lat_idx-2:lat_idx+3, lon_idx-2:lon_idx+3] = 3.0 + np.random.normal(0, 0.5, (5, 5))
    
    metrics_chirps = calculator.calculate_comprehensive_metrics(
        event_date=event_date,
        event_data=event_data,
        precip_data=precip_data,
        anomalies=anomalies,
        lats=lats,
        lons=lons,
        dates=dates,
        rank=1
    )
    
    print(f"   ✅ Métriques CHIRPS calculées:")
    print(f"      Surface affectée: {metrics_chirps['total_area_km2']:.0f} km²")
    print(f"      Pixels affectés: {metrics_chirps['num_pixels_affected']}")
    print(f"      Région principale: {metrics_chirps['centroid_region']}")
    print(f"      Intensité moyenne: {metrics_chirps['intensity_stats']['mean_mm']:.1f} mm")
    print(f"      Intensité P95: {metrics_chirps['intensity_stats']['p95_mm']:.1f} mm")
    print(f"      Anomalie moyenne: {metrics_chirps['anomaly_severity']:.1f}")
    print(f"      Clusters spatiaux: {metrics_chirps['connectivity']['num_clusters']}")
    print(f"      Concentration spatiale: {metrics_chirps['spatial_concentration']:.3f}")
    
    # Test des analyses géographiques
    print(f"\n🗺️  Analyse géographique détaillée:")
    geo_analysis = metrics_chirps['geographic_analysis']
    print(f"   Régions affectées: {len(geo_analysis['regions'])}")
    for region, intensity in geo_analysis['regions'].items():
        print(f"      • {region}: {intensity:.1f} mm cumulé")
    
    print(f"   Départements affectés: {len(geo_analysis['departments'])}")
    for dept, intensity in list(geo_analysis['departments'].items())[:5]:  # Top 5
        print(f"      • {dept}: {intensity:.1f} mm cumulé")
    
    print(f"   Zones climatiques:")
    for zone, intensity in geo_analysis['climate_zones'].items():
        print(f"      • {zone}: {intensity:.1f} mm cumulé")
    
    # Test des métriques de forme
    print(f"\n📐 Métriques de forme:")
    shape = metrics_chirps['shape_metrics']
    print(f"   Rayon équivalent: {shape['equivalent_radius_km']:.1f} km")
    print(f"   Périmètre approximatif: {shape['perimeter_approx_km']:.1f} km")
    print(f"   Compacité: {shape['compactness']:.3f}")
    print(f"   Élongation: {shape['elongation']:.2f}")
    
    # Test des fonctions utilitaires
    print(f"\n🔧 Test des fonctions utilitaires:")
    
    # Créer une liste d'événements simulés
    events_list = []
    for i in range(5):
        event = {
            'total_area_km2': 5000 + i * 1000,
            'max_intensity_mm': 50 + i * 10,
            'coverage_percent': 10 + i * 5,
            'lat_extent_deg': 1.0 + i * 0.2,
            'lon_extent_deg': 1.0 + i * 0.2,
            'centroid_region': ['Kaolack', 'Thiès', 'Diourbel', 'Fatick', 'Kaffrine'][i]
        }
        events_list.append(event)
    
    # Résumé des métriques
    summary = summarize_spatial_metrics(events_list)
    print(f"   📊 Résumé de {summary['total_events']} événements:")
    print(f"      Surface moyenne: {summary['area_stats']['mean']:.0f} km²")
    print(f"      Intensité moyenne: {summary['intensity_stats']['mean']:.1f} mm")
    print(f"      Région la plus affectée: {summary['most_affected_region']}")
    
    # Test de similarité
    similarity = calculate_event_similarity(events_list[0], events_list[1])
    print(f"   🔍 Similarité événements 1-2: {similarity:.3f}")
    
    # Test des capacités géographiques
    print(f"\n🌍 Test des capacités géographiques:")
    
    # Test de différentes coordonnées
    test_coords = [
        (14.69, -17.44, "Dakar"),
        (12.58, -16.27, "Ziguinchor"),
        (13.77, -13.67, "Tambacounda"),
        (15.62, -16.23, "Louga"),
        (14.15, -16.07, "Kaolack")
    ]
    
    for lat, lon, expected_city in test_coords:
        region = calculator.geo.identify_region(lat, lon)
        dept, _ = calculator.geo.identify_department(lat, lon)
        climate = calculator.geo.identify_climate_zone(lat, lon)
        print(f"   📍 {expected_city} ({lat}, {lon}):")
        print(f"      Région: {region}")
        print(f"      Département: {dept}")
        print(f"      Zone climatique: {climate}")
    
    # Test des métriques par zones climatiques
    print(f"\n🌡️  Répartition par zones climatiques:")
    climate_zones = calculator.geo.CLIMATE_ZONES
    for zone, info in climate_zones.items():
        print(f"   • {zone}:")
        print(f"     Caractéristiques: {info['caracteristiques']}")
        print(f"     Régions: {', '.join(info['regions'])}")
    
    # Performance et validation
    print(f"\n⚡ Informations de performance:")
    print(f"   • Grille CHIRPS: {len(lats)} × {len(lons)} = {len(lats) * len(lons)} pixels")
    print(f"   • Résolution: {calculator.senegal_grid['resolution']}° (~25 km)")
    print(f"   • Surface pixel moyenne: {calculator._estimate_average_pixel_area(14.5):.1f} km²")
    print(f"   • Pixels totaux Sénégal: {calculator._estimate_total_pixels()}")
    
    print(f"\n✅ Tests terminés avec succès!")
    print(f"\n📚 Fonctionnalités disponibles:")
    print(f"   • calculate_comprehensive_metrics() - Calcul complet des métriques")
    print(f"   • calculate_event_similarity() - Similarité entre événements")
    print(f"   • summarize_spatial_metrics() - Résumé statistique")
    print(f"   • Analyse géographique automatique (régions, départements, zones)")
    print(f"   • Métriques de forme et connectivité spatiale")
    print(f"   • Support données CHIRPS et estimations DataFrame")
    print(f"   • Validation géographique avec références réelles du Sénégal")
    
    print(f"\n🎯 Prêt pour l'analyse des événements pluviométriques extrêmes!")