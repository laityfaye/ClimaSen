# src/analysis/detection.py
"""
Module de détection des événements de précipitations extrêmes.
Intègre les nouvelles références géographiques et la classification par phases.
"""

import numpy as np
import pandas as pd
from typing import Tuple, List, Dict, Any, Optional
from tqdm import tqdm
import sys
from pathlib import Path
from datetime import datetime

# Imports avec gestion des erreurs
try:
    from ..config.settings import DETECTION_CRITERIA, RAINFALL_PHASES
    from ..utils.season_classifier import get_phase_from_month, RainfallPhaseClassifier
    from ..utils.geographic_references import SenegalGeography, analyze_geographic_distribution
    from ..analysis.spatial_metrics import EnhancedSpatialMetricsCalculator
except ImportError:
    try:
        from src.config.settings import DETECTION_CRITERIA, RAINFALL_PHASES
        from src.utils.season_classifier import get_phase_from_month, RainfallPhaseClassifier
        from src.utils.geographic_references import SenegalGeography, analyze_geographic_distribution
        from src.analysis.spatial_metrics import EnhancedSpatialMetricsCalculator
    except ImportError:
        # Valeurs par défaut en dernier recours
        DETECTION_CRITERIA = {
            'threshold_anomaly': 2.0,
            'min_grid_points': 40,
            'min_precipitation': 5.0,
            'min_affected_area': 1000,
            'min_coverage_percent': 5.0
        }
        RAINFALL_PHASES = {
            'Phase_1_debut': {'months': [5, 6]},
            'Phase_2_pleine': {'months': [7, 8]},
            'Phase_3_fin': {'months': [9, 10]},
            'Hors_saison': {'months': [11, 12, 1, 2, 3, 4]}
        }
        
        # Classes de fallback simplifiées
        class RainfallPhaseClassifier:
            def filter_rainy_season(self, df): return df
            def classify_by_phases(self, df): return df
        
        class SenegalGeography:
            @staticmethod
            def identify_region(lat, lon): return "Région indéterminée"
            @staticmethod
            def identify_department(lat, lon): return "Département indéterminé", "Région indéterminée"
            @staticmethod
            def identify_climate_zone(lat, lon): return "Zone indéterminée"
        
        class EnhancedSpatialMetricsCalculator:
            def calculate_comprehensive_metrics(self, *args, **kwargs): return {}
        
        def get_phase_from_month(month):
            if month in [5, 6]: return 'Phase_1_debut'
            elif month in [7, 8]: return 'Phase_2_pleine'
            elif month in [9, 10]: return 'Phase_3_fin'
            else: return 'Hors_saison'
        
        def analyze_geographic_distribution(coords):
            return {}


def detect_extreme_precipitation_events_final(precip_data: np.ndarray, std_anomalies: np.ndarray, 
                                            dates: List, lats: np.ndarray, lons: np.ndarray) -> pd.DataFrame:
    """
    Détection finale des événements de précipitations extrêmes avec analyse géographique intégrée.
    VERSION CORRIGÉE - Validation géographique stricte pour éviter les points hors Sénégal.
    
    Args:
        precip_data (np.ndarray): Données de précipitation (temps, lat, lon)
        std_anomalies (np.ndarray): Anomalies standardisées
        dates (List): Liste des dates
        lats (np.ndarray): Latitudes
        lons (np.ndarray): Longitudes
        
    Returns:
        pd.DataFrame: DataFrame des événements détectés avec analyses géographiques
    """
    print("\n🔄 DÉTECTION DES ÉVÉNEMENTS EXTRÊMES - VERSION FINALE CORRIGÉE")
    print("-" * 60)
    print("Critères de détection optimisés:")
    print("• Anomalie standardisée: > +2σ (98e centile)")
    print("• Points de grille minimum: 40 (≈7% superficie)")
    print("• Précipitation maximale: ≥ 5mm (réaliste pour le Sénégal)")
    print("• Classement: par couverture spatiale décroissante")
    print("• Nouvelles fonctionnalités:")
    print("  - Classification par phases de saison des pluies")
    print("  - Identification géographique automatique")
    print("  - Métriques spatiales avancées")
    print("  - ✅ CORRECTION: Validation géographique stricte")
    
    # Paramètres optimisés
    THRESHOLD_ANOMALY = DETECTION_CRITERIA['threshold_anomaly']
    MIN_GRID_POINTS = DETECTION_CRITERIA['min_grid_points']
    MIN_PRECIPITATION = DETECTION_CRITERIA['min_precipitation']
    
    # ✅ AJOUT: Limites précises du Sénégal pour validation géographique
    SENEGAL_BOUNDS = {
        'lat_min': 12.3, 'lat_max': 16.7,
        'lon_min': -17.55, 'lon_max': -11.35
    }
    
    def is_in_senegal(lat, lon):
        """Vérifie si un point est dans les limites du Sénégal."""
        return (SENEGAL_BOUNDS['lat_min'] <= lat <= SENEGAL_BOUNDS['lat_max'] and 
                SENEGAL_BOUNDS['lon_min'] <= lon <= SENEGAL_BOUNDS['lon_max'])
    
    n_time, n_lat, n_lon = precip_data.shape
    total_grid_points = n_lat * n_lon
    
    # ✅ AJOUT: Créer un masque géographique pour le Sénégal
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing='ij')
    senegal_mask = np.zeros_like(lat_grid, dtype=bool)
    
    for i in range(len(lats)):
        for j in range(len(lons)):
            if is_in_senegal(lats[i], lons[j]):
                senegal_mask[i, j] = True
    
    senegal_grid_points = np.sum(senegal_mask)
    print(f"🗺️ Masque Sénégal: {senegal_grid_points} points validés sur {total_grid_points}")
    
    # Initialiser les outils d'analyse
    geo = SenegalGeography()
    spatial_calculator = EnhancedSpatialMetricsCalculator()
    
    print(f"\nParamètres de détection:")
    print(f"   Points de grille Sénégal: {senegal_grid_points}")
    print(f"   Seuil minimum: {MIN_GRID_POINTS} points ({MIN_GRID_POINTS/senegal_grid_points*100:.1f}%)")
    print(f"   Seuil d'anomalie: +{THRESHOLD_ANOMALY}σ")
    print(f"   Seuil de précipitation: {MIN_PRECIPITATION} mm")
    
    extreme_events = []
    geographic_corrections = 0
    rejected_events = 0
    
    print("\nRecherche des événements extrêmes avec validation géographique...")
    
    for i in tqdm(range(n_time), desc="Détection et validation"):
        # Données du jour
        day_precip = precip_data[i, :, :]
        day_anomalies = std_anomalies[i, :, :]
        
        # ✅ CORRECTION: Masque des points dépassant le seuil d'anomalie ET dans le Sénégal
        extreme_mask = (
            (day_anomalies > THRESHOLD_ANOMALY) & 
            ~np.isnan(day_anomalies) & 
            senegal_mask  # Limiter au territoire sénégalais
        )
        n_extreme_points = np.sum(extreme_mask)
        
        # Vérifier le critère de couverture minimale
        if n_extreme_points >= MIN_GRID_POINTS:
            # ✅ CORRECTION: Vérifier la précipitation max DANS LA ZONE EXTRÊME validée
            extreme_precip = day_precip[extreme_mask]
            max_precip_in_extreme = np.nanmax(extreme_precip)
            
            if not np.isnan(max_precip_in_extreme) and max_precip_in_extreme >= MIN_PRECIPITATION:
                # Informations temporelles
                event_date = dates[i]
                month = event_date.month
                year = event_date.year
                day_of_year = event_date.timetuple().tm_yday
                
                # Classification par phase de saison des pluies
                phase = get_phase_from_month(month)
                
                # Pourcentage de couverture (par rapport au territoire sénégalais)
                coverage_percent = (n_extreme_points / senegal_grid_points) * 100
                
                # Statistiques des précipitations dans les zones extrêmes
                mean_precip = np.nanmean(extreme_precip)
                min_precip = np.nanmin(extreme_precip)
                std_precip = np.nanstd(extreme_precip)
                
                # Statistiques des anomalies dans les zones extrêmes
                extreme_anomalies = day_anomalies[extreme_mask]
                mean_anomaly = np.nanmean(extreme_anomalies)
                max_anomaly = np.nanmax(extreme_anomalies)
                std_anomaly = np.nanstd(extreme_anomalies)
                
                # Analyse géographique
                lat_indices, lon_indices = np.where(extreme_mask)
                
                # Centroïde géographique pondéré par l'intensité
                weights = extreme_precip
                centroid_lat = np.average(lats[lat_indices], weights=weights)
                centroid_lon = np.average(lons[lon_indices], weights=weights)
                
                # ✅ CORRECTION: Position du maximum d'intensité SEULEMENT dans la zone extrême validée
                masked_precip = np.where(extreme_mask, day_precip, np.nan)
                
                if not np.all(np.isnan(masked_precip)):
                    max_idx = np.unravel_index(np.nanargmax(masked_precip), masked_precip.shape)
                    max_lat = lats[max_idx[0]]
                    max_lon = lons[max_idx[1]]
                    max_precip_day = masked_precip[max_idx]
                    
                    # ✅ VALIDATION: Double vérification géographique
                    if not is_in_senegal(max_lat, max_lon):
                        # Fallback: utiliser le centroïde qui est forcément valide
                        max_lat = centroid_lat
                        max_lon = centroid_lon
                        max_precip_day = max_precip_in_extreme
                        geographic_corrections += 1
                        if geographic_corrections <= 5:  # Afficher seulement les 5 premiers
                            print(f"   ⚠️ Correction géographique appliquée pour {event_date.strftime('%Y-%m-%d')}")
                else:
                    # Cas d'urgence: utiliser le centroïde
                    max_lat = centroid_lat
                    max_lon = centroid_lon
                    max_precip_day = max_precip_in_extreme
                    geographic_corrections += 1
                
                # ✅ VALIDATION FINALE: Vérifier que toutes les coordonnées sont valides
                if is_in_senegal(centroid_lat, centroid_lon) and is_in_senegal(max_lat, max_lon):
                    
                    # Identification géographique du centroïde
                    centroid_region = geo.identify_region(centroid_lat, centroid_lon)
                    centroid_department, _ = geo.identify_department(centroid_lat, centroid_lon)
                    centroid_climate_zone = geo.identify_climate_zone(centroid_lat, centroid_lon)
                    
                    # Identification géographique du maximum d'intensité
                    max_region = geo.identify_region(max_lat, max_lon)
                    max_department, _ = geo.identify_department(max_lat, max_lon)
                    
                    # Étendue géographique (dans la zone validée)
                    lat_extent = lats[lat_indices].max() - lats[lat_indices].min()
                    lon_extent = lons[lon_indices].max() - lons[lon_indices].min()
                    
                    # Conversion en km (approximative)
                    lat_extent_km = lat_extent * 111.32  # 1° latitude ≈ 111.32 km
                    lon_extent_km = lon_extent * 111.32 * np.cos(np.radians(centroid_lat))
                    
                    # Métriques spatiales avancées (version simplifiée)
                    event_data_series = pd.Series({
                        'max_precip': max_precip_day,
                        'coverage_percent': coverage_percent,
                        'centroid_lat': centroid_lat,
                        'centroid_lon': centroid_lon,
                        'max_anomaly': max_anomaly
                    })
                    
                    # Analyse des coordonnées affectées (toutes validées)
                    affected_coords = [(lats[lat_indices[j]], lons[lon_indices[j]]) 
                                     for j in range(len(lat_indices))]
                    
                    # Distribution géographique
                    geo_distribution = analyze_geographic_distribution(affected_coords)
                    
                    # Stocker l'événement avec toutes les informations validées
                    extreme_events.append({
                        # Informations temporelles
                        'date': event_date,
                        'month': month,
                        'year': year,
                        'day_of_year': day_of_year,
                        'phase': phase,
                        
                        # Métriques spatiales de base
                        'coverage_points': n_extreme_points,
                        'coverage_percent': coverage_percent,
                        
                        # Statistiques de précipitation
                        'mean_precip': mean_precip,
                        'max_precip': float(max_precip_day),
                        'min_precip': min_precip,
                        'std_precip': std_precip,
                        
                        # Statistiques d'anomalie
                        'mean_anomaly': mean_anomaly,
                        'max_anomaly': max_anomaly,
                        'std_anomaly': std_anomaly,
                        
                        # Géographie - Centroïde (VALIDÉ)
                        'centroid_lat': centroid_lat,
                        'centroid_lon': centroid_lon,
                        'centroid_region': centroid_region,
                        'centroid_department': centroid_department,
                        'centroid_climate_zone': centroid_climate_zone,
                        
                        # Géographie - Maximum d'intensité (VALIDÉ)
                        'max_intensity_lat': max_lat,
                        'max_intensity_lon': max_lon,
                        'max_intensity_region': max_region,
                        'max_intensity_department': max_department,
                        
                        # Étendue géographique
                        'lat_extent_deg': lat_extent,
                        'lon_extent_deg': lon_extent,
                        'lat_extent_km': lat_extent_km,
                        'lon_extent_km': lon_extent_km,
                        
                        # Distribution géographique
                        'regions_affected': len(geo_distribution.get('regions', {})),
                        'departments_affected': len(geo_distribution.get('departements', {})),
                        'climate_zones_affected': len(geo_distribution.get('zones_climatiques', {})),
                        
                        # Métriques dérivées
                        'intensity_concentration': np.sum(extreme_precip**2) / np.sum(extreme_precip)**2,
                        'spatial_dispersion': np.sqrt(lat_extent_km**2 + lon_extent_km**2),
                        'anomaly_severity': max_anomaly / THRESHOLD_ANOMALY,
                        
                        # ✅ AJOUT: Flag de validation géographique
                        'geographic_validation': 'PASSED'
                    })
                    
                else:
                    # Rejeter l'événement - coordonnées invalides
                    rejected_events += 1
                    if rejected_events <= 3:  # Afficher seulement les 3 premiers
                        print(f"   ❌ Événement {event_date.strftime('%Y-%m-%d')} rejeté - coordonnées invalides")
    
    print(f"\n✅ Détection terminée:")
    print(f"   Événements détectés: {len(extreme_events)}")
    print(f"   Corrections géographiques: {geographic_corrections}")
    print(f"   Événements rejetés: {rejected_events}")
    
    if extreme_events:
        # Créer DataFrame
        df_events = pd.DataFrame(extreme_events)
        df_events.set_index('date', inplace=True)
        
        # CLASSEMENT PAR COUVERTURE SPATIALE (décroissant)
        df_events.sort_values(['coverage_points', 'max_anomaly'], 
                            ascending=[False, False], inplace=True)
        
        # Ajouter un rang pour chaque événement
        df_events['rank'] = range(1, len(df_events) + 1)
        
        print(f"   Période: {df_events.index.min().strftime('%Y-%m-%d')} à {df_events.index.max().strftime('%Y-%m-%d')}")
        print(f"   Fréquence moyenne: {len(df_events)/(df_events['year'].max()-df_events['year'].min()+1):.1f} événements/an")
        
        # ✅ VALIDATION GÉOGRAPHIQUE FINALE
        print(f"\n🔍 VALIDATION GÉOGRAPHIQUE FINALE:")
        outside_senegal_centroids = 0
        outside_senegal_max_intensity = 0
        
        for _, event in df_events.iterrows():
            if not is_in_senegal(event['centroid_lat'], event['centroid_lon']):
                outside_senegal_centroids += 1
            if not is_in_senegal(event['max_intensity_lat'], event['max_intensity_lon']):
                outside_senegal_max_intensity += 1
        
        print(f"   ✅ Centroïdes hors Sénégal: {outside_senegal_centroids} (devrait être 0)")
        print(f"   ✅ Points max intensité hors Sénégal: {outside_senegal_max_intensity} (devrait être 0)")
        
        # Validation des critères
        print(f"\n🔍 VALIDATION DES CRITÈRES:")
        print(f"   ✅ Tous les événements: anomalie > +{THRESHOLD_ANOMALY}σ")
        print(f"   ✅ Tous les événements: couverture ≥ {MIN_GRID_POINTS} points")
        print(f"   ✅ Tous les événements: précipitation ≥ {MIN_PRECIPITATION} mm")
        print(f"   ✅ Tous les événements: coordonnées dans le Sénégal")
        print(f"   📊 Précipitation moyenne: {df_events['max_precip'].mean():.2f} mm")
        print(f"   📊 Précipitation médiane: {df_events['max_precip'].median():.2f} mm")
        print(f"   📊 Couverture moyenne: {df_events['coverage_percent'].mean():.2f}%")
        print(f"   📊 Anomalie moyenne: {df_events['max_anomaly'].mean():.2f}σ")
        
        # Analyse par phases
        print(f"\n🌧️  ANALYSE PAR PHASES:")
        phase_counts = df_events['phase'].value_counts()
        for phase, count in phase_counts.items():
            pct = count / len(df_events) * 100
            phase_info = RAINFALL_PHASES.get(phase, {})
            months = phase_info.get('months', [])
            print(f"   {phase}: {count} événements ({pct:.1f}%) - Mois: {months}")
        
        # Analyse géographique
        print(f"\n🗺️  ANALYSE GÉOGRAPHIQUE:")
        region_counts = df_events['centroid_region'].value_counts()
        print(f"   Régions les plus affectées:")
        for region, count in region_counts.head(5).items():
            pct = count / len(df_events) * 100
            print(f"      • {region}: {count} événements ({pct:.1f}%)")
        
        climate_counts = df_events['centroid_climate_zone'].value_counts()
        print(f"   Zones climatiques:")
        for zone, count in climate_counts.items():
            pct = count / len(df_events) * 100
            print(f"      • {zone}: {count} événements ({pct:.1f}%)")
        
        return df_events
    else:
        print("❌ Aucun événement détecté avec ces critères")
        return pd.DataFrame()
    
def analyze_spatial_distribution(df_events: pd.DataFrame, lats: np.ndarray, 
                               lons: np.ndarray) -> Tuple[pd.Series, pd.Series]:
    """
    Analyse la distribution spatiale des événements extrêmes avec informations géographiques.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        lats (np.ndarray): Latitudes
        lons (np.ndarray): Longitudes
        
    Returns:
        Tuple[pd.Series, pd.Series]: (régions_lat, régions_lon)
    """
    print("\n🔄 ANALYSE DE LA DISTRIBUTION SPATIALE AVANCÉE")
    print("-" * 60)
    
    # Statistiques spatiales
    print("📍 Statistiques des centroïdes:")
    print(f"   Latitude moyenne: {df_events['centroid_lat'].mean():.3f}°N")
    print(f"   Longitude moyenne: {df_events['centroid_lon'].mean():.3f}°E")
    print(f"   Écart-type latitude: {df_events['centroid_lat'].std():.3f}°")
    print(f"   Écart-type longitude: {df_events['centroid_lon'].std():.3f}°")
    
    # Étendue géographique
    print(f"\n📏 Étendue géographique moyenne:")
    print(f"   Latitude: {df_events['lat_extent_km'].mean():.1f} km")
    print(f"   Longitude: {df_events['lon_extent_km'].mean():.1f} km")
    print(f"   Dispersion spatiale: {df_events['spatial_dispersion'].mean():.1f} km")
    
    # Analyse par régions administratives
    print(f"\n🏛️  Distribution par régions administratives:")
    region_stats = df_events.groupby('centroid_region').agg({
        'max_precip': ['mean', 'max'],
        'coverage_percent': 'mean',
        'max_anomaly': 'mean'
    }).round(2)
    
    for region in region_stats.index:
        count = (df_events['centroid_region'] == region).sum()
        pct = count / len(df_events) * 100
        avg_precip = region_stats.loc[region, ('max_precip', 'mean')]
        avg_coverage = region_stats.loc[region, ('coverage_percent', 'mean')]
        print(f"   • {region}: {count} événements ({pct:.1f}%)")
        print(f"     Précipitation moyenne: {avg_precip:.1f} mm")
        print(f"     Couverture moyenne: {avg_coverage:.1f}%")
    
    # Analyse par zones climatiques
    print(f"\n🌡️  Distribution par zones climatiques:")
    climate_stats = df_events.groupby('centroid_climate_zone').agg({
        'max_precip': ['mean', 'count'],
        'max_anomaly': 'mean'
    }).round(2)
    
    for zone in climate_stats.index:
        count = int(climate_stats.loc[zone, ('max_precip', 'count')])
        pct = count / len(df_events) * 100
        avg_precip = climate_stats.loc[zone, ('max_precip', 'mean')]
        avg_anomaly = climate_stats.loc[zone, ('max_anomaly', 'mean')]
        print(f"   • {zone}: {count} événements ({pct:.1f}%)")
        print(f"     Précipitation moyenne: {avg_precip:.1f} mm")
        print(f"     Anomalie moyenne: {avg_anomaly:.1f}σ")
    
    # Régions préférentielles (analyse traditionnelle)
    lat_bins = np.linspace(df_events['centroid_lat'].min(), df_events['centroid_lat'].max(), 5)
    lon_bins = np.linspace(df_events['centroid_lon'].min(), df_events['centroid_lon'].max(), 5)
    
    # 4 labels pour 5 bins
    lat_regions = pd.cut(df_events['centroid_lat'], bins=lat_bins, 
                        labels=['Sud', 'Sud-Centre', 'Nord-Centre', 'Nord'])
    lon_regions = pd.cut(df_events['centroid_lon'], bins=lon_bins, 
                        labels=['Ouest', 'Ouest-Centre', 'Est-Centre', 'Est'])
    
    print(f"\n📊 Distribution régionale simplifiée (Latitude):")
    for region, count in lat_regions.value_counts().items():
        pct = count / len(df_events) * 100
        print(f"   {region}: {count} événements ({pct:.1f}%)")
    
    print(f"\n📊 Distribution régionale simplifiée (Longitude):")
    for region, count in lon_regions.value_counts().items():
        pct = count / len(df_events) * 100
        print(f"   {region}: {count} événements ({pct:.1f}%)")
    
    return lat_regions, lon_regions


def analyze_temporal_patterns(df_events: pd.DataFrame) -> Dict[str, Any]:
    """
    Analyse les patterns temporels des événements extrêmes.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        Dict[str, Any]: Statistiques temporelles
    """
    print("\n🔄 ANALYSE DES PATTERNS TEMPORELS")
    print("-" * 60)
    
    # Analyse mensuelle
    monthly_counts = df_events['month'].value_counts().sort_index()
    print("📅 Distribution mensuelle:")
    month_names = {1: 'Jan', 2: 'Fév', 3: 'Mar', 4: 'Avr', 5: 'Mai', 6: 'Juin',
                  7: 'Juil', 8: 'Août', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Déc'}
    
    for month, count in monthly_counts.items():
        pct = count / len(df_events) * 100
        print(f"   {month_names[month]}: {count} événements ({pct:.1f}%)")
    
    # Analyse par phases
    print("\n🌧️  Distribution par phases de saison des pluies:")
    phase_analysis = df_events.groupby('phase').agg({
        'max_precip': ['mean', 'max', 'count'],
        'coverage_percent': 'mean',
        'max_anomaly': 'mean'
    }).round(2)
    
    for phase in phase_analysis.index:
        count = int(phase_analysis.loc[phase, ('max_precip', 'count')])
        pct = count / len(df_events) * 100
        avg_precip = phase_analysis.loc[phase, ('max_precip', 'mean')]
        max_precip = phase_analysis.loc[phase, ('max_precip', 'max')]
        avg_coverage = phase_analysis.loc[phase, ('coverage_percent', 'mean')]
        
        # Informations sur la phase
        phase_info = RAINFALL_PHASES.get(phase, {})
        months = phase_info.get('months', [])
        
        print(f"   • {phase} (mois {months}):")
        print(f"     Événements: {count} ({pct:.1f}%)")
        print(f"     Précipitation: {avg_precip:.1f} mm (moyenne), {max_precip:.1f} mm (max)")
        print(f"     Couverture moyenne: {avg_coverage:.1f}%")
    
    # Analyse annuelle
    yearly_counts = df_events['year'].value_counts().sort_index()
    print(f"\n📊 Statistiques annuelles:")
    print(f"   Nombre moyen d'événements par an: {yearly_counts.mean():.1f}")
    print(f"   Écart-type: {yearly_counts.std():.1f}")
    print(f"   Années les plus actives:")
    for year, count in yearly_counts.head(5).items():
        print(f"      {year}: {count} événements")
    
    # Tendances
    if len(yearly_counts) > 10:
        # Calcul simple de tendance
        years = yearly_counts.index.values
        counts = yearly_counts.values
        trend = np.polyfit(years, counts, 1)[0]
        print(f"   Tendance: {trend:+.2f} événements/an")
    
    return {
        'monthly_counts': monthly_counts,
        'phase_analysis': phase_analysis,
        'yearly_counts': yearly_counts,
        'total_events': len(df_events),
        'mean_events_per_year': yearly_counts.mean(),
        'std_events_per_year': yearly_counts.std()
    }


class ExtremeEventDetector:
    """
    Classe pour la détection des événements de précipitations extrêmes avec analyses avancées.
    """
    
    def __init__(self, threshold_anomaly: float = None, min_grid_points: int = None, 
                 min_precipitation: float = None):
        """
        Initialise le détecteur d'événements extrêmes.
        
        Args:
            threshold_anomaly (float, optional): Seuil d'anomalie standardisée
            min_grid_points (int, optional): Nombre minimum de points de grille
            min_precipitation (float, optional): Précipitation minimale
        """
        self.threshold_anomaly = threshold_anomaly or DETECTION_CRITERIA['threshold_anomaly']
        self.min_grid_points = min_grid_points or DETECTION_CRITERIA['min_grid_points']
        self.min_precipitation = min_precipitation or DETECTION_CRITERIA['min_precipitation']
        
        # Initialiser les outils d'analyse
        self.geo = SenegalGeography()
        self.phase_classifier = RainfallPhaseClassifier()
        self.spatial_calculator = EnhancedSpatialMetricsCalculator()
        
        print(f"🔧 Détecteur d'événements extrêmes initialisé")
        print(f"   Seuil d'anomalie: {self.threshold_anomaly}σ")
        print(f"   Points minimum: {self.min_grid_points}")
        print(f"   Précipitation minimum: {self.min_precipitation} mm")
    
    def detect_events(self, precip_data: np.ndarray, anomalies: np.ndarray, 
                     dates: List, lats: np.ndarray, lons: np.ndarray) -> pd.DataFrame:
        """
        Détecte les événements de précipitations extrêmes avec analyses complètes.
        
        Args:
            precip_data (np.ndarray): Données de précipitation
            anomalies (np.ndarray): Anomalies standardisées
            dates (List): Liste des dates
            lats (np.ndarray): Latitudes
            lons (np.ndarray): Longitudes
            
        Returns:
            pd.DataFrame: DataFrame des événements détectés avec analyses
        """
        # Sauvegarder les critères actuels
        current_criteria = DETECTION_CRITERIA.copy()
        
        # Mettre à jour avec les valeurs de l'instance
        DETECTION_CRITERIA['threshold_anomaly'] = self.threshold_anomaly
        DETECTION_CRITERIA['min_grid_points'] = self.min_grid_points
        DETECTION_CRITERIA['min_precipitation'] = self.min_precipitation
        
        try:
            # Détecter les événements
            df_events = detect_extreme_precipitation_events_final(
                precip_data, anomalies, dates, lats, lons
            )
            
            if not df_events.empty:
                # Analyses supplémentaires
                print("\n🔍 ANALYSES SUPPLÉMENTAIRES")
                print("-" * 40)
                
                # Analyse temporelle
                temporal_stats = analyze_temporal_patterns(df_events)
                
                # Analyse spatiale
                lat_regions, lon_regions = analyze_spatial_distribution(df_events, lats, lons)
                
                # Ajouter les résultats aux métadonnées
                df_events.attrs['temporal_analysis'] = temporal_stats
                df_events.attrs['spatial_regions'] = {
                    'lat_regions': lat_regions,
                    'lon_regions': lon_regions
                }
                
                print("\n✅ Analyses terminées avec succès")
            
            return df_events
            
        finally:
            # Restaurer les critères originaux
            DETECTION_CRITERIA.update(current_criteria)
    
    def get_event_summary(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Génère un résumé des événements détectés.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Dict[str, Any]: Résumé des événements
        """
        if df_events.empty:
            return {'total_events': 0, 'message': 'Aucun événement détecté'}
        
        # Statistiques générales
        summary = {
            'total_events': len(df_events),
            'period': {
                'start': df_events.index.min().strftime('%Y-%m-%d'),
                'end': df_events.index.max().strftime('%Y-%m-%d'),
                'years': df_events['year'].max() - df_events['year'].min() + 1
            },
            'frequency': len(df_events) / (df_events['year'].max() - df_events['year'].min() + 1),
            
            # Statistiques d'intensité
            'intensity_stats': {
                'mean_precipitation': df_events['max_precip'].mean(),
                'max_precipitation': df_events['max_precip'].max(),
                'mean_coverage': df_events['coverage_percent'].mean(),
                'max_coverage': df_events['coverage_percent'].max(),
                'mean_anomaly': df_events['max_anomaly'].mean(),
                'max_anomaly': df_events['max_anomaly'].max()
            },
            
            # Distribution par phases
            'phase_distribution': df_events['phase'].value_counts().to_dict(),
            
            # Distribution géographique
            'geographic_distribution': {
                'regions': df_events['centroid_region'].value_counts().to_dict(),
                'climate_zones': df_events['centroid_climate_zone'].value_counts().to_dict(),
                'most_affected_region': df_events['centroid_region'].value_counts().index[0],
                'most_affected_climate_zone': df_events['centroid_climate_zone'].value_counts().index[0]
            },
            
            # Top événements
            'top_events': {
                'by_intensity': df_events.nlargest(5, 'max_precip')[['max_precip', 'coverage_percent', 'centroid_region']].to_dict('records'),
                'by_coverage': df_events.nlargest(5, 'coverage_percent')[['coverage_percent', 'max_precip', 'centroid_region']].to_dict('records'),
                'by_anomaly': df_events.nlargest(5, 'max_anomaly')[['max_anomaly', 'max_precip', 'centroid_region']].to_dict('records')
            }
        }
        
        return summary
    
    def validate_detection_quality(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Valide la qualité de la détection des événements.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Dict[str, Any]: Résultats de validation
        """
        if df_events.empty:
            return {'valid': False, 'reason': 'Aucun événement détecté'}
        
        validation = {
            'valid': True,
            'total_events': len(df_events),
            'criteria_validation': {},
            'quality_metrics': {},
            'recommendations': []
        }
        
        # Validation des critères
        validation['criteria_validation'] = {
            'anomaly_threshold': {
                'criterion': f"> {self.threshold_anomaly}σ",
                'min_value': df_events['max_anomaly'].min(),
                'passed': df_events['max_anomaly'].min() > self.threshold_anomaly
            },
            'grid_points': {
                'criterion': f">= {self.min_grid_points} points",
                'min_value': df_events['coverage_points'].min(),
                'passed': df_events['coverage_points'].min() >= self.min_grid_points
            },
            'precipitation': {
                'criterion': f">= {self.min_precipitation} mm",
                'min_value': df_events['max_precip'].min(),
                'passed': df_events['max_precip'].min() >= self.min_precipitation
            }
        }
        
        # Métriques de qualité
        validation['quality_metrics'] = {
            'frequency_per_year': len(df_events) / (df_events['year'].max() - df_events['year'].min() + 1),
            'seasonal_consistency': self._check_seasonal_consistency(df_events),
            'geographic_distribution': self._check_geographic_distribution(df_events),
            'intensity_distribution': self._check_intensity_distribution(df_events)
        }
        
        # Recommandations
        freq = validation['quality_metrics']['frequency_per_year']
        if freq < 1:
            validation['recommendations'].append("Fréquence faible - considérer réduire les seuils")
        elif freq > 20:
            validation['recommendations'].append("Fréquence élevée - considérer augmenter les seuils")
        
        if not validation['quality_metrics']['seasonal_consistency']:
            validation['recommendations'].append("Distribution saisonnière atypique détectée")
        
        return validation
    
    def _check_seasonal_consistency(self, df_events: pd.DataFrame) -> bool:
        """Vérifie la cohérence saisonnière des événements."""
        # La majorité des événements devrait être en saison des pluies
        rainy_season_months = [5, 6, 7, 8, 9, 10]
        rainy_season_events = df_events[df_events['month'].isin(rainy_season_months)]
        
        return len(rainy_season_events) / len(df_events) > 0.8
    
    def _check_geographic_distribution(self, df_events: pd.DataFrame) -> bool:
        """Vérifie la distribution géographique des événements."""
        # Vérifier que les événements ne sont pas concentrés dans une seule région
        region_counts = df_events['centroid_region'].value_counts()
        max_concentration = region_counts.iloc[0] / len(df_events)
        
        return max_concentration < 0.6  # Pas plus de 60% dans une seule région
    
    def _check_intensity_distribution(self, df_events: pd.DataFrame) -> bool:
        """Vérifie la distribution d'intensité des événements."""
        # Vérifier que les intensités suivent une distribution réaliste
        q75 = df_events['max_precip'].quantile(0.75)
        q25 = df_events['max_precip'].quantile(0.25)
        
        # Ratio interquartile raisonnable
        return q75 / q25 < 5.0 if q25 > 0 else True


def export_events_to_csv(df_events: pd.DataFrame, filepath: str) -> None:
    """
    Exporte les événements vers un fichier CSV.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        filepath (str): Chemin du fichier de sortie
    """
    if df_events.empty:
        print("❌ Aucun événement à exporter")
        return
    
    # Préparer les données pour l'export
    export_df = df_events.copy()
    export_df.reset_index(inplace=True)
    
    # Formater les colonnes
    export_df['date'] = export_df['date'].dt.strftime('%Y-%m-%d')
    
    # Colonnes numériques à arrondir
    numeric_cols = ['max_precip', 'mean_precip', 'coverage_percent', 'max_anomaly', 
                   'mean_anomaly', 'centroid_lat', 'centroid_lon', 'lat_extent_km', 
                   'lon_extent_km', 'spatial_dispersion']
    
    for col in numeric_cols:
        if col in export_df.columns:
            export_df[col] = export_df[col].round(3)
    
    # Sauvegarder
    export_df.to_csv(filepath, index=False, encoding='utf-8')
    print(f"✅ Événements exportés vers: {filepath}")
    print(f"   Nombre d'événements: {len(export_df)}")
    print(f"   Colonnes: {len(export_df.columns)}")


def generate_detection_report(df_events: pd.DataFrame, output_path: str = None) -> str:
    """
    Génère un rapport de détection détaillé.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        output_path (str, optional): Chemin de sortie du rapport
        
    Returns:
        str: Contenu du rapport
    """
    if df_events.empty:
        return "Aucun événement détecté - rapport non généré"
    
    # Générer le rapport
    report = []
    report.append("=" * 80)
    report.append("RAPPORT DE DÉTECTION DES ÉVÉNEMENTS EXTRÊMES")
    report.append("=" * 80)
    report.append(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Nombre total d'événements: {len(df_events)}")
    report.append("")
    
    # Période d'analyse
    report.append("1. PÉRIODE D'ANALYSE")
    report.append("-" * 20)
    report.append(f"   Début: {df_events.index.min().strftime('%Y-%m-%d')}")
    report.append(f"   Fin: {df_events.index.max().strftime('%Y-%m-%d')}")
    report.append(f"   Durée: {df_events['year'].max() - df_events['year'].min() + 1} années")
    report.append(f"   Fréquence: {len(df_events)/(df_events['year'].max()-df_events['year'].min()+1):.1f} événements/an")
    report.append("")
    
    # Statistiques d'intensité
    report.append("2. STATISTIQUES D'INTENSITÉ")
    report.append("-" * 30)
    report.append(f"   Précipitation maximale:")
    report.append(f"      Moyenne: {df_events['max_precip'].mean():.1f} mm")
    report.append(f"      Médiane: {df_events['max_precip'].median():.1f} mm")
    report.append(f"      Maximum: {df_events['max_precip'].max():.1f} mm")
    report.append(f"      Minimum: {df_events['max_precip'].min():.1f} mm")
    report.append(f"   Couverture spatiale:")
    report.append(f"      Moyenne: {df_events['coverage_percent'].mean():.1f}%")
    report.append(f"      Maximum: {df_events['coverage_percent'].max():.1f}%")
    report.append(f"   Anomalie standardisée:")
    report.append(f"      Moyenne: {df_events['max_anomaly'].mean():.1f}σ")
    report.append(f"      Maximum: {df_events['max_anomaly'].max():.1f}σ")
    report.append("")
    
    # Distribution temporelle
    report.append("3. DISTRIBUTION TEMPORELLE")
    report.append("-" * 30)
    
    # Par phases
    phase_counts = df_events['phase'].value_counts()
    report.append("   Par phases de saison des pluies:")
    for phase, count in phase_counts.items():
        pct = count / len(df_events) * 100
        phase_info = RAINFALL_PHASES.get(phase, {})
        months = phase_info.get('months', [])
        report.append(f"      {phase}: {count} événements ({pct:.1f}%) - Mois: {months}")
    
    # Par mois
    monthly_counts = df_events['month'].value_counts().sort_index()
    report.append("   Par mois:")
    month_names = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
                  'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
    for month, count in monthly_counts.items():
        pct = count / len(df_events) * 100
        report.append(f"      {month_names[month-1]}: {count} événements ({pct:.1f}%)")
    report.append("")
    
    # Distribution géographique
    report.append("4. DISTRIBUTION GÉOGRAPHIQUE")
    report.append("-" * 35)
    
    # Par régions
    region_counts = df_events['centroid_region'].value_counts()
    report.append("   Par régions administratives:")
    for region, count in region_counts.items():
        pct = count / len(df_events) * 100
        report.append(f"      {region}: {count} événements ({pct:.1f}%)")
    
    # Par zones climatiques
    climate_counts = df_events['centroid_climate_zone'].value_counts()
    report.append("   Par zones climatiques:")
    for zone, count in climate_counts.items():
        pct = count / len(df_events) * 100
        report.append(f"      {zone}: {count} événements ({pct:.1f}%)")
    report.append("")
    
    # Top événements
    report.append("5. TOP ÉVÉNEMENTS")
    report.append("-" * 20)
    
    # Par intensité
    report.append("   Par intensité (précipitation maximale):")
    top_intensity = df_events.nlargest(5, 'max_precip')
    for i, (date, event) in enumerate(top_intensity.iterrows(), 1):
        report.append(f"      {i}. {date.strftime('%Y-%m-%d')}: {event['max_precip']:.1f} mm")
        report.append(f"         Région: {event['centroid_region']}, Couverture: {event['coverage_percent']:.1f}%")
    
    # Par couverture
    report.append("   Par couverture spatiale:")
    top_coverage = df_events.nlargest(5, 'coverage_percent')
    for i, (date, event) in enumerate(top_coverage.iterrows(), 1):
        report.append(f"      {i}. {date.strftime('%Y-%m-%d')}: {event['coverage_percent']:.1f}%")
        report.append(f"         Région: {event['centroid_region']}, Précipitation: {event['max_precip']:.1f} mm")
    report.append("")
    
    # Métriques avancées
    report.append("6. MÉTRIQUES AVANCÉES")
    report.append("-" * 25)
    report.append(f"   Étendue spatiale moyenne:")
    report.append(f"      Latitude: {df_events['lat_extent_km'].mean():.1f} km")
    report.append(f"      Longitude: {df_events['lon_extent_km'].mean():.1f} km")
    report.append(f"      Dispersion: {df_events['spatial_dispersion'].mean():.1f} km")
    report.append(f"   Concentration d'intensité moyenne: {df_events['intensity_concentration'].mean():.3f}")
    report.append(f"   Sévérité d'anomalie moyenne: {df_events['anomaly_severity'].mean():.1f}")
    report.append("")
    
    # Critères de détection
    report.append("7. CRITÈRES DE DÉTECTION UTILISÉS")
    report.append("-" * 35)
    report.append(f"   Seuil d'anomalie: > {DETECTION_CRITERIA['threshold_anomaly']}σ")
    report.append(f"   Points de grille minimum: {DETECTION_CRITERIA['min_grid_points']}")
    report.append(f"   Précipitation minimum: {DETECTION_CRITERIA['min_precipitation']} mm")
    report.append("")
    
    # Fin du rapport
    report.append("=" * 80)
    report.append("FIN DU RAPPORT")
    report.append("=" * 80)
    
    # Joindre les lignes
    report_content = "\n".join(report)
    
    # Sauvegarder si chemin spécifié
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"✅ Rapport généré: {output_path}")
    
    return report_content


if __name__ == "__main__":
    print("🌩️  Module de détection des événements extrêmes - Version améliorée")
    print("=" * 70)
    print("Ce module contient les outils pour:")
    print("• Détecter les événements de précipitations extrêmes")
    print("• Analyser la distribution spatiale et temporelle")
    print("• Classifier par phases de saison des pluies")
    print("• Identifier les régions et zones climatiques affectées")
    print("• Calculer des métriques spatiales avancées")
    print("• Valider la qualité de la détection")
    print("• Générer des rapports détaillés")
    print("• Exporter les résultats")
    print()
    print("🔧 Nouveautés de cette version:")
    print("• Intégration avec les références géographiques du Sénégal")
    print("• Classification automatique par phases de saison des pluies")
    print("• Métriques spatiales avancées (étendue, dispersion, concentration)")
    print("• Identification automatique des régions et départements")
    print("• Analyse des zones climatiques affectées")
    print("• Validation de la qualité des détections")
    print("• Génération de rapports détaillés")
    print()
    print("📊 Utilisation:")
    print("detector = ExtremeEventDetector()")
    print("df_events = detector.detect_events(precip_data, anomalies, dates, lats, lons)")
    print("summary = detector.get_event_summary(df_events)")
    print("validation = detector.validate_detection_quality(df_events)")
    print()
    print("✅ Module prêt à l'utilisation!")