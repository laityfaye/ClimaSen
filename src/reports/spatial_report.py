# src/reports/spatial_report.py
"""
Générateur de rapports spatiaux avancé et centralisé.
Version améliorée intégrée avec les nouvelles fonctionnalités de la plateforme.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import json
import warnings

# Imports avec gestion robuste des erreurs
try:
    from ..config.settings import (
        PROJECT_INFO, REGION_COLORS, CLIMATE_COLORS, PHASE_COLORS,
        get_output_path, RAINFALL_PHASES, get_configuration_summary
    )
    from ..utils.geographic_references import SenegalGeography, analyze_geographic_distribution
    from ..utils.season_classifier import get_phase_from_month
    from ..analysis.spatial_metrics import summarize_spatial_metrics, calculate_event_similarity
except ImportError:
    try:
        from src.config.settings import (
            PROJECT_INFO, REGION_COLORS, CLIMATE_COLORS, PHASE_COLORS,
            get_output_path, RAINFALL_PHASES, get_configuration_summary
        )
        from src.utils.geographic_references import SenegalGeography, analyze_geographic_distribution
        from src.utils.season_classifier import get_phase_from_month
        from src.analysis.spatial_metrics import summarize_spatial_metrics, calculate_event_similarity
    except ImportError:
        # Configuration de fallback
        PROJECT_INFO = {
            'title': 'Analyse des précipitations extrêmes au Sénégal',
            'version': '2.0.0',
            'author': 'Équipe de recherche climatologique'
        }
        RAINFALL_PHASES = {
            'Phase_1_debut': {'months': [5, 6], 'description': 'Début de saison'},
            'Phase_2_pleine': {'months': [7, 8], 'description': 'Pleine saison'},
            'Phase_3_fin': {'months': [9, 10], 'description': 'Fin de saison'},
            'Hors_saison': {'months': [11, 12, 1, 2, 3, 4], 'description': 'Hors saison'}
        }
        REGION_COLORS = {'Default': '#808080'}
        CLIMATE_COLORS = {'Default': '#808080'}
        PHASE_COLORS = {'Default': '#808080'}
        
        def get_output_path(key): return f"outputs/reports/{key}.txt"
        def get_phase_from_month(month): return 'Phase_2_pleine' if month in [7, 8] else 'Hors_saison'
        def get_configuration_summary(): return {}
        def analyze_geographic_distribution(coords): return {}
        def summarize_spatial_metrics(metrics): return {}
        def calculate_event_similarity(m1, m2): return 0.5
        
        class SenegalGeography:
            REGIONS = {}
            CLIMATE_ZONES = {}
            @staticmethod
            def identify_region(lat, lon): return "Région indéterminée"
            @staticmethod
            def identify_climate_zone(lat, lon): return "Zone indéterminée"

warnings.filterwarnings('ignore')


class EnhancedSpatialReportGenerator:
    """
    Générateur avancé pour tous les rapports spatiaux avec intégration complète
    des nouvelles fonctionnalités de la plateforme.
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialise le générateur avec toutes les références.
        
        Args:
            output_dir (Path, optional): Dossier de sortie personnalisé
        """
        self.output_dir = Path(output_dir) if output_dir else Path("outputs/reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialiser les références
        self.project_info = PROJECT_INFO
        self.geo = SenegalGeography()
        self.rainfall_phases = RAINFALL_PHASES
        
        print("🗺️  EnhancedSpatialReportGenerator initialisé")
        print(f"   Dossier de sortie: {self.output_dir}")
        print(f"   Version: {self.project_info.get('version', '2.0.0')}")
    
    def generate_comprehensive_spatial_report(self, spatial_results: List[Dict[str, Any]], 
                                            analysis_type: str = "spatial_analysis",
                                            title: str = "Analyse Spatiale Avancée",
                                            df_events: Optional[pd.DataFrame] = None) -> str:
        """
        Génère un rapport spatial complet et avancé.
        
        Args:
            spatial_results (List[Dict]): Résultats de l'analyse spatiale
            analysis_type (str): Type d'analyse
            title (str): Titre du rapport
            df_events (pd.DataFrame, optional): DataFrame des événements pour analyse croisée
            
        Returns:
            str: Chemin du fichier généré
        """
        print(f"\n📄 GÉNÉRATION DU RAPPORT SPATIAL COMPLET")
        print("=" * 60)
        print(f"Type d'analyse: {analysis_type}")
        print(f"Nombre d'événements: {len(spatial_results)}")
        
        if not spatial_results:
            print("❌ Aucun résultat spatial à analyser")
            return self._generate_empty_report(analysis_type, title)
        
        # Convertir en DataFrame pour analyse
        df = pd.DataFrame(spatial_results)
        
        # Enrichir avec des analyses croisées
        df_enriched = self._enrich_spatial_data(df, df_events)
        
        # Effectuer l'analyse spatiale complète
        spatial_analysis = self._perform_comprehensive_spatial_analysis(df_enriched)
        
        # Générer le rapport
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        filename = f"rapport_spatial_{analysis_type.lower()}_{datetime.now().strftime('%Y%m%d')}.txt"
        report_path = self.output_dir / filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            self._write_report_header(f, title, analysis_type, timestamp, len(spatial_results))
            self._write_executive_summary(f, df_enriched, spatial_analysis)
            self._write_spatial_distribution_analysis(f, spatial_analysis)
            self._write_phase_based_analysis(f, df_enriched, spatial_analysis)
            self._write_geographic_analysis(f, spatial_analysis)
            self._write_intensity_analysis(f, spatial_analysis)
            self._write_event_details(f, spatial_results[:10])  # Top 10
            self._write_comparative_analysis(f, df_enriched, spatial_analysis)
            self._write_spatial_patterns(f, spatial_analysis)
            self._write_quality_assessment(f, spatial_analysis)
            self._write_recommendations(f, spatial_analysis, analysis_type)
            self._write_technical_appendix(f, df_enriched, spatial_analysis)
        
        print(f"✅ Rapport spatial généré: {report_path}")
        return str(report_path)
    
    def _enrich_spatial_data(self, df: pd.DataFrame, df_events: Optional[pd.DataFrame]) -> pd.DataFrame:
        """Enrichit les données spatiales avec des analyses croisées."""
        df_enriched = df.copy()
        
        # Ajouter les phases si pas présentes
        if 'phase' not in df_enriched.columns and 'date' in df_enriched.columns:
            df_enriched['date_parsed'] = pd.to_datetime(df_enriched['date'])
            df_enriched['month'] = df_enriched['date_parsed'].dt.month
            df_enriched['phase'] = df_enriched['month'].apply(get_phase_from_month)
        
        # Enrichir avec des métriques géographiques
        if 'centroid_lat' in df_enriched.columns and 'centroid_lon' in df_enriched.columns:
            df_enriched['region'] = df_enriched.apply(
                lambda row: self.geo.identify_region(row['centroid_lat'], row['centroid_lon']), 
                axis=1
            )
            df_enriched['climate_zone'] = df_enriched.apply(
                lambda row: self.geo.identify_climate_zone(row['centroid_lat'], row['centroid_lon']), 
                axis=1
            )
        
        # Ajouter des métriques dérivées
        if 'max_intensity_mm' in df_enriched.columns and 'total_area_km2' in df_enriched.columns:
            df_enriched['intensity_per_km2'] = df_enriched['max_intensity_mm'] / df_enriched['total_area_km2']
            df_enriched['total_volume_mm_km2'] = df_enriched['max_intensity_mm'] * df_enriched['total_area_km2']
        
        # Classification par taille d'événement
        if 'total_area_km2' in df_enriched.columns:
            df_enriched['size_category'] = pd.cut(
                df_enriched['total_area_km2'], 
                bins=[0, 5000, 15000, 30000, float('inf')],
                labels=['Petit', 'Moyen', 'Grand', 'Très grand']
            )
        
        # Classification par intensité
        if 'max_intensity_mm' in df_enriched.columns:
            df_enriched['intensity_category'] = pd.cut(
                df_enriched['max_intensity_mm'],
                bins=[0, 25, 50, 100, float('inf')],
                labels=['Modéré', 'Intense', 'Très intense', 'Extrême']
            )
        
        return df_enriched
    
    def _perform_comprehensive_spatial_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Effectue une analyse spatiale complète."""
        analysis = {
            'general_statistics': self._calculate_general_spatial_statistics(df),
            'geographic_distribution': self._analyze_geographic_distribution(df),
            'phase_analysis': self._analyze_spatial_by_phases(df),
            'intensity_patterns': self._analyze_intensity_patterns(df),
            'size_distribution': self._analyze_size_distribution(df),
            'spatial_clustering': self._analyze_spatial_clustering(df),
            'temporal_spatial_evolution': self._analyze_temporal_spatial_evolution(df),
            'quality_metrics': self._calculate_quality_metrics(df)
        }
        
        return analysis
    
    def _calculate_general_spatial_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calcule les statistiques spatiales générales."""
        stats = {
            'total_events': len(df),
            'total_area_affected': float(df['total_area_km2'].sum()) if 'total_area_km2' in df.columns else 0,
            'average_event_size': float(df['total_area_km2'].mean()) if 'total_area_km2' in df.columns else 0,
            'median_event_size': float(df['total_area_km2'].median()) if 'total_area_km2' in df.columns else 0,
            'largest_event_size': float(df['total_area_km2'].max()) if 'total_area_km2' in df.columns else 0,
            'smallest_event_size': float(df['total_area_km2'].min()) if 'total_area_km2' in df.columns else 0
        }
        
        if 'max_intensity_mm' in df.columns:
            stats.update({
                'average_max_intensity': float(df['max_intensity_mm'].mean()),
                'peak_intensity': float(df['max_intensity_mm'].max()),
                'median_intensity': float(df['max_intensity_mm'].median())
            })
        
        if 'coverage_percent' in df.columns:
            stats.update({
                'average_coverage': float(df['coverage_percent'].mean()),
                'max_coverage': float(df['coverage_percent'].max()),
                'total_senegal_affected': float(df['coverage_percent'].sum())  # Pourcentage cumulé
            })
        
        # Statistiques de position
        if 'centroid_lat' in df.columns and 'centroid_lon' in df.columns:
            stats.update({
                'geographic_center': {
                    'latitude': float(df['centroid_lat'].mean()),
                    'longitude': float(df['centroid_lon'].mean())
                },
                'geographic_dispersion': {
                    'lat_std': float(df['centroid_lat'].std()),
                    'lon_std': float(df['centroid_lon'].std())
                },
                'geographic_extent': {
                    'lat_range': float(df['centroid_lat'].max() - df['centroid_lat'].min()),
                    'lon_range': float(df['centroid_lon'].max() - df['centroid_lon'].min())
                }
            })
        
        return stats
    
    def _analyze_geographic_distribution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyse la distribution géographique détaillée."""
        geo_analysis = {}
        
        # Distribution par régions
        if 'region' in df.columns:
            try:
                # CORRECTION: Gérer les erreurs d'agrégation
                agg_dict = {}
                
                if 'total_area_km2' in df.columns:
                    agg_dict['total_area_km2'] = ['count', 'sum', 'mean']
                else:
                    agg_dict['region'] = ['count']  # Utiliser la colonne region elle-même
                
                if 'max_intensity_mm' in df.columns:
                    agg_dict['max_intensity_mm'] = ['mean', 'max']
                
                if agg_dict:
                    region_stats = df.groupby('region').agg({col: ['count', 'mean'] for col in ['total_area_km2', 'max_intensity_mm'] if col in df.columns}).round(2)
                    
                    # Convertir les index multi-niveaux en dictionnaire simple
                    region_stats_dict = {}
                    for region in region_stats.index:
                        region_stats_dict[region] = {}
                        for col in region_stats.columns:
                            if isinstance(col, tuple):
                                key = f"{col[0]}_{col[1]}"
                            else:
                                key = str(col)
                            region_stats_dict[region][key] = region_stats.loc[region, col]
                    
                    geo_analysis['regional_distribution'] = {
                        'event_counts': df['region'].value_counts().to_dict(),
                        'detailed_stats': region_stats_dict,
                        'most_affected_region': df['region'].value_counts().index[0] if len(df) > 0 else None,
                        'regional_diversity': len(df['region'].unique())
                    }
            except Exception as e:
                print(f"Erreur dans l'analyse régionale: {e}")
                geo_analysis['regional_distribution'] = {
                    'event_counts': df['region'].value_counts().to_dict(),
                    'detailed_stats': {},
                    'most_affected_region': df['region'].value_counts().index[0] if len(df) > 0 else None,
                    'regional_diversity': len(df['region'].unique())
                }
        
        # Distribution par zones climatiques
        if 'climate_zone' in df.columns:
            try:
                agg_dict = {}
                
                if 'total_area_km2' in df.columns:
                    agg_dict['total_area_km2'] = ['count', 'mean']
                else:
                    agg_dict['climate_zone'] = ['count']
                
                if 'max_intensity_mm' in df.columns:
                    agg_dict['max_intensity_mm'] = 'mean'
                
                if agg_dict:
                    climate_stats = df.groupby('climate_zone').agg({col: ['count', 'mean'] for col in ['total_area_km2', 'max_intensity_mm'] if col in df.columns}).round(2)
                    
                    # Convertir les index multi-niveaux
                    climate_stats_dict = {}
                    for zone in climate_stats.index:
                        climate_stats_dict[zone] = {}
                        for col in climate_stats.columns:
                            if isinstance(col, tuple):
                                key = f"{col[0]}_{col[1]}"
                            else:
                                key = str(col)
                            climate_stats_dict[zone][key] = climate_stats.loc[zone, col]
                    
                    geo_analysis['climate_distribution'] = {
                        'event_counts': df['climate_zone'].value_counts().to_dict(),
                        'detailed_stats': climate_stats_dict,
                        'climate_diversity': len(df['climate_zone'].unique())
                    }
            except Exception as e:
                print(f"Erreur dans l'analyse climatique: {e}")
                geo_analysis['climate_distribution'] = {
                    'event_counts': df['climate_zone'].value_counts().to_dict(),
                    'detailed_stats': {},
                    'climate_diversity': len(df['climate_zone'].unique())
                }
        
        # Hotspots géographiques
        if 'centroid_lat' in df.columns and 'centroid_lon' in df.columns:
            try:
                geo_analysis['hotspots'] = self._identify_spatial_hotspots(df)
            except Exception as e:
                print(f"Erreur dans l'identification des hotspots: {e}")
                geo_analysis['hotspots'] = {'status': 'error', 'message': str(e)}
        
        return geo_analysis
    
    def _analyze_spatial_by_phases(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyse spatiale par phases de saison des pluies."""
        if 'phase' not in df.columns:
            return {'status': 'no_phase_data', 'message': 'Données de phases non disponibles'}
        
        phase_analysis = {}
        
        # Distribution par phases
        phase_counts = df['phase'].value_counts()
        phase_analysis['phase_distribution'] = {}
        
        for phase, count in phase_counts.items():
            phase_info = self.rainfall_phases.get(phase, {})
            phase_data = df[df['phase'] == phase]
            
            phase_stats = {
                'event_count': int(count),
                'percentage': float(count / len(df) * 100),
                'description': phase_info.get('description', phase),
                'months': phase_info.get('months', [])
            }
            
            # Statistiques spatiales par phase
            if len(phase_data) > 0:
                if 'total_area_km2' in phase_data.columns:
                    phase_stats.update({
                        'avg_area': float(phase_data['total_area_km2'].mean()),
                        'total_area': float(phase_data['total_area_km2'].sum()),
                        'max_area': float(phase_data['total_area_km2'].max())
                    })
                
                if 'max_intensity_mm' in phase_data.columns:
                    phase_stats.update({
                        'avg_intensity': float(phase_data['max_intensity_mm'].mean()),
                        'max_intensity': float(phase_data['max_intensity_mm'].max())
                    })
                
                # Régions préférentielles par phase
                if 'region' in phase_data.columns:
                    phase_stats['preferred_regions'] = phase_data['region'].value_counts().head(3).to_dict()
            
            phase_analysis['phase_distribution'][phase] = phase_stats
        
        # Comparaison inter-phases
        if len(phase_counts) > 1:
            phase_analysis['inter_phase_comparison'] = self._compare_phases_spatially(df)
        
        return phase_analysis
    
    def _analyze_intensity_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyse les patterns d'intensité spatiale."""
        if 'max_intensity_mm' not in df.columns:
            return {'status': 'no_intensity_data'}
        
        intensity_analysis = {}
        
        # Distribution par catégories d'intensité
        if 'intensity_category' in df.columns:
            intensity_dist = df['intensity_category'].value_counts()
            intensity_analysis['intensity_distribution'] = {
                category: {
                    'count': int(count),
                    'percentage': float(count / len(df) * 100)
                }
                for category, count in intensity_dist.items()
            }
        
        # Relation intensité-surface
        if 'total_area_km2' in df.columns:
            correlation = df['max_intensity_mm'].corr(df['total_area_km2'])
            intensity_analysis['intensity_area_relationship'] = {
                'correlation': float(correlation),
                'interpretation': self._interpret_correlation(correlation)
            }
        
        # Hotspots d'intensité
        top_intensity_events = df.nlargest(5, 'max_intensity_mm')
        intensity_analysis['intensity_hotspots'] = []
        
        for _, event in top_intensity_events.iterrows():
            hotspot = {
                'date': event.get('date', 'Unknown'),
                'intensity': float(event['max_intensity_mm']),
                'location': {
                    'lat': float(event.get('centroid_lat', 0)),
                    'lon': float(event.get('centroid_lon', 0)),
                    'region': event.get('region', 'Unknown')
                }
            }
            intensity_analysis['intensity_hotspots'].append(hotspot)
        
        return intensity_analysis
    
    def _analyze_size_distribution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyse la distribution des tailles d'événements."""
        if 'total_area_km2' not in df.columns:
            return {'status': 'no_size_data'}
        
        size_analysis = {}
        
        # Distribution par catégories de taille
        if 'size_category' in df.columns:
            size_dist = df['size_category'].value_counts()
            size_analysis['size_distribution'] = {
                category: {
                    'count': int(count),
                    'percentage': float(count / len(df) * 100),
                    'avg_intensity': float(df[df['size_category'] == category]['max_intensity_mm'].mean()) 
                    if 'max_intensity_mm' in df.columns else None
                }
                for category, count in size_dist.items()
            }
        
        # Statistiques de taille
        sizes = df['total_area_km2']
        size_analysis['size_statistics'] = {
            'mean': float(sizes.mean()),
            'median': float(sizes.median()),
            'std': float(sizes.std()),
            'min': float(sizes.min()),
            'max': float(sizes.max()),
            'q25': float(sizes.quantile(0.25)),
            'q75': float(sizes.quantile(0.75)),
            'q90': float(sizes.quantile(0.90)),
            'q95': float(sizes.quantile(0.95))
        }
        
        # Événements exceptionnellement grands
        threshold_95 = sizes.quantile(0.95)
        large_events = df[df['total_area_km2'] >= threshold_95]
        
        size_analysis['exceptional_events'] = {
            'threshold_km2': float(threshold_95),
            'count': len(large_events),
            'percentage': float(len(large_events) / len(df) * 100),
            'total_area': float(large_events['total_area_km2'].sum()),
            'dates': large_events.get('date', pd.Series()).tolist()[:5]  # Top 5 dates
        }
        
        return size_analysis
    
    def _analyze_spatial_clustering(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyse le clustering spatial des événements."""
        if not all(col in df.columns for col in ['centroid_lat', 'centroid_lon']):
            return {'status': 'no_coordinates'}
        
        clustering_analysis = {}
        
        # Dispersion spatiale
        lat_std = df['centroid_lat'].std()
        lon_std = df['centroid_lon'].std()
        
        clustering_analysis['spatial_dispersion'] = {
            'latitude_std': float(lat_std),
            'longitude_std': float(lon_std),
            'overall_dispersion': float(np.sqrt(lat_std**2 + lon_std**2)),
            'clustering_level': self._assess_clustering_level(lat_std, lon_std)
        }
        
        # Centre de gravité
        center_lat = df['centroid_lat'].mean()
        center_lon = df['centroid_lon'].mean()
        
        clustering_analysis['center_of_mass'] = {
            'latitude': float(center_lat),
            'longitude': float(center_lon),
            'region': self.geo.identify_region(center_lat, center_lon),
            'climate_zone': self.geo.identify_climate_zone(center_lat, center_lon)
        }
        
        # Distance moyenne au centre
        df_temp = df.copy()
        df_temp['distance_to_center'] = np.sqrt(
            (df_temp['centroid_lat'] - center_lat)**2 + 
            (df_temp['centroid_lon'] - center_lon)**2
        )
        
        clustering_analysis['distance_statistics'] = {
            'mean_distance_to_center': float(df_temp['distance_to_center'].mean()),
            'max_distance_to_center': float(df_temp['distance_to_center'].max()),
            'std_distance_to_center': float(df_temp['distance_to_center'].std())
        }
        
        return clustering_analysis
    
    def _analyze_temporal_spatial_evolution(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyse l'évolution spatio-temporelle."""
        if 'date' not in df.columns:
            return {'status': 'no_temporal_data'}
        
        temporal_analysis = {}
        
        try:
            # Préparer les données temporelles
            df_temp = df.copy()
            df_temp['date_parsed'] = pd.to_datetime(df_temp['date'])
            df_temp['year'] = df_temp['date_parsed'].dt.year
            df_temp['month'] = df_temp['date_parsed'].dt.month
            
            # Évolution annuelle des surfaces
            if 'total_area_km2' in df_temp.columns:
                yearly_area = df_temp.groupby('year')['total_area_km2'].agg(['count', 'sum', 'mean']).round(2)
                
                # Convertir en dictionnaire simple
                yearly_area_dict = {}
                for year in yearly_area.index:
                    yearly_area_dict[str(year)] = {
                        'count': yearly_area.loc[year, 'count'],
                        'sum': yearly_area.loc[year, 'sum'],
                        'mean': yearly_area.loc[year, 'mean']
                    }
                
                temporal_analysis['yearly_evolution'] = {
                    'area_statistics': yearly_area_dict,
                    'trend_analysis': self._calculate_trend(yearly_area)
                }
            
            # Évolution des centroïdes dans le temps
            if all(col in df_temp.columns for col in ['centroid_lat', 'centroid_lon']):
                yearly_centroids = df_temp.groupby('year')[['centroid_lat', 'centroid_lon']].mean().round(4)
                
                # Convertir en dictionnaire simple
                yearly_centroids_dict = {}
                for year in yearly_centroids.index:
                    yearly_centroids_dict[str(year)] = {
                        'centroid_lat': yearly_centroids.loc[year, 'centroid_lat'],
                        'centroid_lon': yearly_centroids.loc[year, 'centroid_lon']
                    }
                
                temporal_analysis['centroid_evolution'] = {
                    'yearly_centroids': yearly_centroids_dict,
                    'spatial_migration': self._calculate_spatial_migration(yearly_centroids)
                }
                
        except Exception as e:
            print(f"Erreur dans l'analyse temporelle: {e}")
            temporal_analysis['status'] = 'error'
            temporal_analysis['message'] = str(e)
        
        return temporal_analysis
    
    def _calculate_quality_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calcule les métriques de qualité des données spatiales."""
        quality_metrics = {}
        
        # Complétude des données
        required_columns = ['date', 'centroid_lat', 'centroid_lon', 'total_area_km2', 'max_intensity_mm']
        present_columns = [col for col in required_columns if col in df.columns]
        
        quality_metrics['data_completeness'] = {
            'required_columns': required_columns,
            'present_columns': present_columns,
            'completeness_ratio': float(len(present_columns) / len(required_columns)),
            'missing_columns': [col for col in required_columns if col not in df.columns]
        }
        
        # Validation des coordonnées géographiques
        if all(col in df.columns for col in ['centroid_lat', 'centroid_lon']):
            senegal_bounds = {'lat_min': 12.3, 'lat_max': 16.7, 'lon_min': -17.55, 'lon_max': -11.35}

            valid_coords = (
                (df['centroid_lat'] >= senegal_bounds['lat_min']) &
                (df['centroid_lat'] <= senegal_bounds['lat_max']) &
                (df['centroid_lon'] >= senegal_bounds['lon_min']) &
                (df['centroid_lon'] <= senegal_bounds['lon_max'])
            )
            
            quality_metrics['coordinate_validation'] = {
                'total_events': len(df),
                'valid_coordinates': int(valid_coords.sum()),
                'invalid_coordinates': int((~valid_coords).sum()),
                'validity_ratio': float(valid_coords.sum() / len(df))
            }
        
        # Validation des valeurs physiques
        quality_metrics['physical_validation'] = {}
        
        if 'total_area_km2' in df.columns:
            valid_areas = (df['total_area_km2'] > 0) & (df['total_area_km2'] < 200000)  # Max théorique Sénégal
            quality_metrics['physical_validation']['area_validation'] = {
                'valid_areas': int(valid_areas.sum()),
                'invalid_areas': int((~valid_areas).sum()),
                'validity_ratio': float(valid_areas.sum() / len(df))
            }
        
        if 'max_intensity_mm' in df.columns:
            valid_intensities = (df['max_intensity_mm'] > 0) & (df['max_intensity_mm'] < 1000)  # Max physique
            quality_metrics['physical_validation']['intensity_validation'] = {
                'valid_intensities': int(valid_intensities.sum()),
                'invalid_intensities': int((~valid_intensities).sum()),
                'validity_ratio': float(valid_intensities.sum() / len(df))
            }
        
        # Score de qualité global
        quality_scores = []
        if 'completeness_ratio' in quality_metrics['data_completeness']:
            quality_scores.append(quality_metrics['data_completeness']['completeness_ratio'])
        
        if 'coordinate_validation' in quality_metrics:
            quality_scores.append(quality_metrics['coordinate_validation']['validity_ratio'])
        
        if quality_scores:
            quality_metrics['overall_quality'] = {
                'quality_score': float(np.mean(quality_scores)),
                'quality_level': self._get_quality_level(np.mean(quality_scores))
            }
        
        return quality_metrics
    
    def _identify_spatial_hotspots(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identifie les hotspots spatiaux."""
        if not all(col in df.columns for col in ['centroid_lat', 'centroid_lon']):
            return {'status': 'no_coordinates'}
        
        # Clustering simple par grille
        lat_bins = 5  # 5x5 grille
        lon_bins = 5
        
        lat_edges = np.linspace(df['centroid_lat'].min(), df['centroid_lat'].max(), lat_bins + 1)
        lon_edges = np.linspace(df['centroid_lon'].min(), df['centroid_lon'].max(), lon_bins + 1)
        
        df_temp = df.copy()
        df_temp['lat_bin'] = pd.cut(df_temp['centroid_lat'], lat_edges, labels=range(lat_bins))
        df_temp['lon_bin'] = pd.cut(df_temp['centroid_lon'], lon_edges, labels=range(lon_bins))
        
        # Compter les événements par cellule
        grid_counts = df_temp.groupby(['lat_bin', 'lon_bin']).size().reset_index(name='event_count')
        
        # Identifier les hotspots (cellules avec > moyenne + 1 écart-type)
        threshold = grid_counts['event_count'].mean() + grid_counts['event_count'].std()
        hotspots = grid_counts[grid_counts['event_count'] >= threshold]
        
        hotspot_details = []
        for _, hotspot in hotspots.iterrows():
            lat_idx = int(hotspot['lat_bin'])
            lon_idx = int(hotspot['lon_bin'])
            
            center_lat = (lat_edges[lat_idx] + lat_edges[lat_idx + 1]) / 2
            center_lon = (lon_edges[lon_idx] + lon_edges[lon_idx + 1]) / 2
            
            hotspot_details.append({
                'grid_cell': f"{lat_idx}_{lon_idx}",
                'event_count': int(hotspot['event_count']),
                'center_coordinates': {
                    'latitude': float(center_lat),
                    'longitude': float(center_lon)
                },
                'region': self.geo.identify_region(center_lat, center_lon),
                'climate_zone': self.geo.identify_climate_zone(center_lat, center_lon)
            })
        
        return {
            'hotspot_count': len(hotspot_details),
            'detection_threshold': float(threshold),
            'hotspot_details': hotspot_details
        }
    
    def _compare_phases_spatially(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Compare les phases spatialement."""
        comparison = {}
        
        phases = df['phase'].unique()
        
        for i, phase1 in enumerate(phases):
            for phase2 in phases[i+1:]:
                phase1_data = df[df['phase'] == phase1]
                phase2_data = df[df['phase'] == phase2]
                
                comparison_key = f"{phase1}_vs_{phase2}"
                
                comparison[comparison_key] = {
                    'event_count_diff': len(phase1_data) - len(phase2_data),
                    'avg_area_diff': float(phase1_data['total_area_km2'].mean() - phase2_data['total_area_km2'].mean()) if 'total_area_km2' in df.columns else None,
                    'avg_intensity_diff': float(phase1_data['max_intensity_mm'].mean() - phase2_data['max_intensity_mm'].mean()) if 'max_intensity_mm' in df.columns else None
                }
        
        return comparison
    
    def _interpret_correlation(self, correlation: float) -> str:
        """Interprète une corrélation."""
        abs_corr = abs(correlation)
        direction = "positive" if correlation > 0 else "négative"
        
        if abs_corr > 0.8:
            return f"Corrélation {direction} très forte"
        elif abs_corr > 0.6:
            return f"Corrélation {direction} forte"
        elif abs_corr > 0.4:
            return f"Corrélation {direction} modérée"
        elif abs_corr > 0.2:
            return f"Corrélation {direction} faible"
        else:
            return "Corrélation négligeable"
    
    def _assess_clustering_level(self, lat_std: float, lon_std: float) -> str:
        """Évalue le niveau de clustering spatial."""
        overall_std = np.sqrt(lat_std**2 + lon_std**2)
        
        if overall_std < 0.5:
            return "Très concentré"
        elif overall_std < 1.0:
            return "Concentré"
        elif overall_std < 2.0:
            return "Modérément dispersé"
        else:
            return "Très dispersé"
    
    def _calculate_trend(self, yearly_data: pd.DataFrame) -> Dict[str, Any]:
        """Calcule les tendances temporelles."""
        if len(yearly_data) < 3:
            return {'status': 'insufficient_data'}
        
        years = yearly_data.index.values
        trends = {}
        
        for column in yearly_data.columns:
            values = yearly_data[column].values
            
            # Régression linéaire simple
            trend_coeff = np.polyfit(years, values, 1)[0]
            
            trends[column] = {
                'slope': float(trend_coeff),
                'interpretation': 'Croissante' if trend_coeff > 0.01 else 'Décroissante' if trend_coeff < -0.01 else 'Stable'
            }
        
        return trends
    
    def _calculate_spatial_migration(self, yearly_centroids: pd.DataFrame) -> Dict[str, Any]:
        """Calcule la migration spatiale des centroïdes."""
        if len(yearly_centroids) < 2:
            return {'status': 'insufficient_data'}
        
        # Calculer les distances entre années consécutives
        distances = []
        for i in range(1, len(yearly_centroids)):
            prev_year = yearly_centroids.iloc[i-1]
            curr_year = yearly_centroids.iloc[i]
            
            distance = np.sqrt(
                (curr_year['centroid_lat'] - prev_year['centroid_lat'])**2 +
                (curr_year['centroid_lon'] - prev_year['centroid_lon'])**2
            )
            distances.append(distance)
        
        return {
            'mean_annual_migration': float(np.mean(distances)),
            'max_annual_migration': float(np.max(distances)),
            'total_migration': float(np.sum(distances)),
            'migration_trend': 'Stable' if np.std(distances) < 0.1 else 'Variable'
        }
    
    def _get_quality_level(self, score: float) -> str:
        """Détermine le niveau de qualité."""
        if score >= 0.9:
            return "EXCELLENT"
        elif score >= 0.8:
            return "TRÈS BON"
        elif score >= 0.7:
            return "BON"
        elif score >= 0.6:
            return "ACCEPTABLE"
        else:
            return "INSUFFISANT"
    
    def _write_report_header(self, f, title: str, analysis_type: str, timestamp: str, event_count: int):
        """Écrit l'en-tête du rapport."""
        f.write(f"RAPPORT SPATIAL AVANCÉ - {title.upper()}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Projet: {self.project_info.get('title', 'Analyse des précipitations extrêmes')}\n")
        f.write(f"Version: {self.project_info.get('version', '2.0.0')}\n")
        f.write(f"Auteur: {self.project_info.get('author', 'Équipe de recherche')}\n")
        f.write(f"Date de génération: {timestamp}\n")
        f.write(f"Type d'analyse: {analysis_type}\n")
        f.write(f"Nombre d'événements analysés: {event_count}\n")
        f.write(f"Période: 1981-2023 (43 ans)\n\n")
    
    def _write_executive_summary(self, f, df: pd.DataFrame, analysis: Dict[str, Any]):
        """Écrit le résumé exécutif."""
        f.write("RÉSUMÉ EXÉCUTIF\n")
        f.write("-" * 20 + "\n")
        
        general_stats = analysis.get('general_statistics', {})
        
        f.write(f"• Événements analysés: {general_stats.get('total_events', 0)}\n")
        f.write(f"• Surface totale affectée: {general_stats.get('total_area_affected', 0):.0f} km²\n")
        f.write(f"• Taille moyenne d'événement: {general_stats.get('average_event_size', 0):.0f} km²\n")
        f.write(f"• Plus grand événement: {general_stats.get('largest_event_size', 0):.0f} km²\n")
        f.write(f"• Intensité maximale observée: {general_stats.get('peak_intensity', 0):.1f} mm/jour\n")
        f.write(f"• Intensité moyenne: {general_stats.get('average_max_intensity', 0):.1f} mm/jour\n")
        
        # Centre géographique
        if 'geographic_center' in general_stats:
            center = general_stats['geographic_center']
            f.write(f"• Centre géographique: {center['latitude']:.3f}°N, {abs(center['longitude']):.3f}°W\n")
        
        # Dispersion
        if 'geographic_dispersion' in general_stats:
            disp = general_stats['geographic_dispersion']
            f.write(f"• Dispersion géographique: {disp['lat_std']:.3f}° (lat), {disp['lon_std']:.3f}° (lon)\n")
        
        f.write("\n")
    
    def _write_spatial_distribution_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse de distribution spatiale."""
        f.write("1. ANALYSE DE LA DISTRIBUTION SPATIALE\n")
        f.write("-" * 45 + "\n")
        
        general_stats = analysis.get('general_statistics', {})
        
        f.write("1.1 Statistiques générales de taille:\n")
        f.write(f"    Superficie moyenne par événement: {general_stats.get('average_event_size', 0):.0f} km²\n")
        f.write(f"    Superficie médiane: {general_stats.get('median_event_size', 0):.0f} km²\n")
        f.write(f"    Plus petit événement: {general_stats.get('smallest_event_size', 0):.0f} km²\n")
        f.write(f"    Plus grand événement: {general_stats.get('largest_event_size', 0):.0f} km²\n")
        f.write(f"    Surface totale cumulée: {general_stats.get('total_area_affected', 0):.0f} km²\n\n")
        
        # Distribution des tailles
        size_analysis = analysis.get('size_distribution', {})
        if 'size_distribution' in size_analysis:
            f.write("1.2 Distribution par catégories de taille:\n")
            for category, stats in size_analysis['size_distribution'].items():
                f.write(f"    • {category}: {stats['count']} événements ({stats['percentage']:.1f}%)\n")
                if stats['avg_intensity']:
                    f.write(f"      Intensité moyenne: {stats['avg_intensity']:.1f} mm/jour\n")
            f.write("\n")
        
        # Événements exceptionnels
        if 'exceptional_events' in size_analysis:
            exceptional = size_analysis['exceptional_events']
            f.write("1.3 Événements exceptionnellement grands:\n")
            f.write(f"    Seuil (P95): {exceptional['threshold_km2']:.0f} km²\n")
            f.write(f"    Nombre: {exceptional['count']} événements ({exceptional['percentage']:.1f}%)\n")
            f.write(f"    Surface totale: {exceptional['total_area']:.0f} km²\n")
            if exceptional['dates']:
                f.write(f"    Dates principales: {', '.join(exceptional['dates'][:3])}\n")
            f.write("\n")
    
    def _write_phase_based_analysis(self, f, df: pd.DataFrame, analysis: Dict[str, Any]):
        """Écrit l'analyse par phases."""
        f.write("2. ANALYSE PAR PHASES DE SAISON DES PLUIES\n")
        f.write("-" * 50 + "\n")
        
        phase_analysis = analysis.get('phase_analysis', {})
        if phase_analysis.get('status') == 'no_phase_data':
            f.write("Données de phases non disponibles.\n\n")
            return
        
        f.write("2.1 Distribution spatiale par phases:\n")
        phase_dist = phase_analysis.get('phase_distribution', {})
        
        # Trier par pourcentage décroissant
        sorted_phases = sorted(phase_dist.items(), 
                             key=lambda x: x[1].get('percentage', 0), reverse=True)
        
        for phase, stats in sorted_phases:
            f.write(f"\n    • {stats.get('description', phase)}:\n")
            f.write(f"      Événements: {stats['event_count']} ({stats['percentage']:.1f}%)\n")
            f.write(f"      Mois concernés: {stats['months']}\n")
            
            if 'avg_area' in stats:
                f.write(f"      Surface moyenne: {stats['avg_area']:.0f} km²\n")
                f.write(f"      Surface totale: {stats['total_area']:.0f} km²\n")
                f.write(f"      Plus grand événement: {stats['max_area']:.0f} km²\n")
            
            if 'avg_intensity' in stats:
                f.write(f"      Intensité moyenne: {stats['avg_intensity']:.1f} mm/jour\n")
                f.write(f"      Intensité maximale: {stats['max_intensity']:.1f} mm/jour\n")
            
            if 'preferred_regions' in stats:
                f.write(f"      Régions préférentielles: {', '.join(list(stats['preferred_regions'].keys())[:3])}\n")
        
        # Comparaison inter-phases
        if 'inter_phase_comparison' in phase_analysis:
            f.write("\n2.2 Comparaisons inter-phases:\n")
            comparisons = phase_analysis['inter_phase_comparison']
            for comparison_key, stats in comparisons.items():
                phases = comparison_key.replace('_vs_', ' vs ')
                f.write(f"    • {phases}:\n")
                f.write(f"      Différence d'événements: {stats['event_count_diff']:+d}\n")
                if stats['avg_area_diff']:
                    f.write(f"      Différence surface moyenne: {stats['avg_area_diff']:+.0f} km²\n")
                if stats['avg_intensity_diff']:
                    f.write(f"      Différence intensité moyenne: {stats['avg_intensity_diff']:+.1f} mm/jour\n")
        
        f.write("\n")
    
    def _write_geographic_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse géographique."""
        f.write("3. ANALYSE GÉOGRAPHIQUE DÉTAILLÉE\n")
        f.write("-" * 40 + "\n")
        
        geo_analysis = analysis.get('geographic_distribution', {})
        
        # Distribution régionale
        if 'regional_distribution' in geo_analysis:
            regional = geo_analysis['regional_distribution']
            f.write("3.1 Distribution par régions administratives:\n")
            
            event_counts = regional.get('event_counts', {})
            sorted_regions = sorted(event_counts.items(), key=lambda x: x[1], reverse=True)
            
            for i, (region, count) in enumerate(sorted_regions[:10], 1):
                total_events = sum(event_counts.values())
                pct = count / total_events * 100 if total_events > 0 else 0
                f.write(f"    {i:2d}. {region}: {count} événements ({pct:.1f}%)\n")
            
            if regional.get('most_affected_region'):
                f.write(f"\n    Région la plus affectée: {regional['most_affected_region']}\n")
            f.write(f"    Diversité régionale: {regional.get('regional_diversity', 0)} régions touchées\n\n")
        
        # Distribution par zones climatiques
        if 'climate_distribution' in geo_analysis:
            climate = geo_analysis['climate_distribution']
            f.write("3.2 Distribution par zones climatiques:\n")
            
            climate_counts = climate.get('event_counts', {})
            for zone, count in climate_counts.items():
                total_events = sum(climate_counts.values())
                pct = count / total_events * 100 if total_events > 0 else 0
                f.write(f"    • {zone}: {count} événements ({pct:.1f}%)\n")
            
            f.write(f"    Diversité climatique: {climate.get('climate_diversity', 0)} zones touchées\n\n")
        
        # Hotspots géographiques
        if 'hotspots' in geo_analysis:
            hotspots = geo_analysis['hotspots']
            if hotspots.get('hotspot_count', 0) > 0:
                f.write("3.3 Hotspots géographiques identifiés:\n")
                f.write(f"    Nombre de hotspots: {hotspots['hotspot_count']}\n")
                f.write(f"    Seuil de détection: {hotspots['detection_threshold']:.1f} événements/cellule\n")
                
                for i, hotspot in enumerate(hotspots['hotspot_details'][:5], 1):
                    coords = hotspot['center_coordinates']
                    f.write(f"    {i}. Cellule {hotspot['grid_cell']}: {hotspot['event_count']} événements\n")
                    f.write(f"       Position: {coords['latitude']:.3f}°N, {abs(coords['longitude']):.3f}°W\n")
                    f.write(f"       Région: {hotspot['region']}, Zone: {hotspot['climate_zone']}\n")
                f.write("\n")
    
    def _write_intensity_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse d'intensité."""
        f.write("4. ANALYSE D'INTENSITÉ SPATIALE\n")
        f.write("-" * 35 + "\n")
        
        intensity_analysis = analysis.get('intensity_patterns', {})
        if intensity_analysis.get('status') == 'no_intensity_data':
            f.write("Données d'intensité non disponibles.\n\n")
            return
        
        # Distribution par catégories
        if 'intensity_distribution' in intensity_analysis:
            f.write("4.1 Distribution par catégories d'intensité:\n")
            intensity_dist = intensity_analysis['intensity_distribution']
            
            for category, stats in intensity_dist.items():
                f.write(f"    • {category}: {stats['count']} événements ({stats['percentage']:.1f}%)\n")
            f.write("\n")
        
        # Relation intensité-surface
        if 'intensity_area_relationship' in intensity_analysis:
            relationship = intensity_analysis['intensity_area_relationship']
            f.write("4.2 Relation intensité-surface:\n")
            f.write(f"    Corrélation: {relationship['correlation']:.3f}\n")
            f.write(f"    Interprétation: {relationship['interpretation']}\n\n")
        
        # Hotspots d'intensité
        if 'intensity_hotspots' in intensity_analysis:
            f.write("4.3 Hotspots d'intensité (Top 5):\n")
            hotspots = intensity_analysis['intensity_hotspots']
            
            for i, hotspot in enumerate(hotspots, 1):
                location = hotspot['location']
                f.write(f"    {i}. {hotspot['date']}: {hotspot['intensity']:.1f} mm/jour\n")
                f.write(f"       Position: {location['lat']:.3f}°N, {abs(location['lon']):.3f}°W\n")
                f.write(f"       Région: {location['region']}\n")
            f.write("\n")
    
    def _write_event_details(self, f, spatial_results: List[Dict]):
        """Écrit les détails des événements principaux."""
        f.write("5. DÉTAILS DES ÉVÉNEMENTS PRINCIPAUX (TOP 10)\n")
        f.write("-" * 55 + "\n")
        
        for i, result in enumerate(spatial_results, 1):
            f.write(f"RANG #{result.get('rank', i)}: {result.get('date', 'Date inconnue')}\n")
            f.write("=" * 40 + "\n")
            
            # Localisation
            f.write(f"Localisation:\n")
            f.write(f"  • Région: {result.get('region', result.get('centroid_region', 'Inconnue'))}\n")
            if 'centroid_lat' in result and 'centroid_lon' in result:
                f.write(f"  • Centroïde: {result['centroid_lat']:.4f}°N, {abs(result['centroid_lon']):.4f}°W\n")
            if 'climate_zone' in result or 'centroid_climate_zone' in result:
                zone = result.get('climate_zone', result.get('centroid_climate_zone', 'Inconnue'))
                f.write(f"  • Zone climatique: {zone}\n")
            
            # Métriques spatiales
            f.write(f"Métriques spatiales:\n")
            if 'total_area_km2' in result:
                f.write(f"  • Surface affectée: {result['total_area_km2']:.0f} km²\n")
            if 'coverage_percent' in result:
                f.write(f"  • Couverture: {result['coverage_percent']:.1f}% du territoire\n")
            if 'num_pixels_affected' in result:
                f.write(f"  • Pixels affectés: {result['num_pixels_affected']}\n")
            
            # Métriques d'intensité
            f.write(f"Métriques d'intensité:\n")
            if 'max_intensity_mm' in result:
                f.write(f"  • Intensité maximale: {result['max_intensity_mm']:.1f} mm/jour\n")
            
            # Statistiques d'intensité détaillées
            if 'intensity_stats' in result and isinstance(result['intensity_stats'], dict):
                stats = result['intensity_stats']
                if 'mean' in stats:
                    f.write(f"  • Intensité moyenne: {stats['mean']:.1f} mm/jour\n")
                if 'median' in stats:
                    f.write(f"  • Intensité médiane: {stats['median']:.1f} mm/jour\n")
                if 'p95' in stats:
                    f.write(f"  • P95: {stats['p95']:.1f} mm/jour\n")
            
            # Métriques de forme
            if 'geometry_metrics' in result:
                geom = result['geometry_metrics']
                if isinstance(geom, dict):
                    f.write(f"Métriques géométriques:\n")
                    if 'aspect_ratio' in geom:
                        f.write(f"  • Ratio d'aspect: {geom['aspect_ratio']:.2f}\n")
                    if 'diagonal_km' in geom:
                        f.write(f"  • Diagonale: {geom['diagonal_km']:.0f} km\n")
            
            # Métriques de forme avancées
            if 'shape_metrics' in result:
                shape = result['shape_metrics']
                if isinstance(shape, dict):
                    if 'compactness' in shape:
                        f.write(f"  • Compacité: {shape['compactness']:.3f}\n")
                    if 'elongation' in shape:
                        f.write(f"  • Élongation: {shape['elongation']:.2f}\n")
            
            # Phase saisonnière
            if 'phase' in result:
                phase_info = self.rainfall_phases.get(result['phase'], {})
                phase_desc = phase_info.get('description', result['phase'])
                f.write(f"Phase saisonnière: {phase_desc}\n")
            
            f.write("\n")
    
    def _write_comparative_analysis(self, f, df: pd.DataFrame, analysis: Dict[str, Any]):
        """Écrit l'analyse comparative."""
        f.write("6. ANALYSE COMPARATIVE ET CLUSTERING\n")
        f.write("-" * 40 + "\n")
        
        # Clustering spatial
        clustering = analysis.get('spatial_clustering', {})
        if 'spatial_dispersion' in clustering:
            f.write("6.1 Analyse du clustering spatial:\n")
            dispersion = clustering['spatial_dispersion']
            f.write(f"    Dispersion latitudinale: {dispersion['latitude_std']:.3f}°\n")
            f.write(f"    Dispersion longitudinale: {dispersion['longitude_std']:.3f}°\n")
            f.write(f"    Dispersion globale: {dispersion['overall_dispersion']:.3f}°\n")
            f.write(f"    Niveau de clustering: {dispersion['clustering_level']}\n\n")
        
        if 'center_of_mass' in clustering:
            center = clustering['center_of_mass']
            f.write("6.2 Centre de gravité des événements:\n")
            f.write(f"    Position: {center['latitude']:.4f}°N, {abs(center['longitude']):.4f}°W\n")
            f.write(f"    Région: {center['region']}\n")
            f.write(f"    Zone climatique: {center['climate_zone']}\n\n")
        
        if 'distance_statistics' in clustering:
            distances = clustering['distance_statistics']
            f.write("6.3 Statistiques de distance au centre:\n")
            f.write(f"    Distance moyenne: {distances['mean_distance_to_center']:.3f}°\n")
            f.write(f"    Distance maximale: {distances['max_distance_to_center']:.3f}°\n")
            f.write(f"    Écart-type: {distances['std_distance_to_center']:.3f}°\n\n")
        
        # Corrélations entre variables
        if all(col in df.columns for col in ['max_intensity_mm', 'total_area_km2']):
            corr_intensity_area = df['max_intensity_mm'].corr(df['total_area_km2'])
            f.write("6.4 Corrélations entre variables spatiales:\n")
            f.write(f"    Intensité vs Surface: {corr_intensity_area:.3f}\n")
            
            if 'coverage_percent' in df.columns:
                corr_intensity_coverage = df['max_intensity_mm'].corr(df['coverage_percent'])
                corr_area_coverage = df['total_area_km2'].corr(df['coverage_percent'])
                f.write(f"    Intensité vs Couverture: {corr_intensity_coverage:.3f}\n")
                f.write(f"    Surface vs Couverture: {corr_area_coverage:.3f}\n")
            f.write("\n")
    
    def _write_spatial_patterns(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse des patterns spatiaux."""
        f.write("7. PATTERNS SPATIO-TEMPORELS\n")
        f.write("-" * 30 + "\n")
        
        temporal_analysis = analysis.get('temporal_spatial_evolution', {})
        if temporal_analysis.get('status') == 'no_temporal_data':
            f.write("Données temporelles non disponibles pour l'analyse spatio-temporelle.\n\n")
            return
        
        # Évolution annuelle
        if 'yearly_evolution' in temporal_analysis:
            f.write("7.1 Évolution temporelle des surfaces:\n")
            yearly_evol = temporal_analysis['yearly_evolution']
            
            if 'trend_analysis' in yearly_evol:
                trends = yearly_evol['trend_analysis']
                for metric, trend_data in trends.items():
                    if metric == 'count':
                        f.write(f"    Fréquence annuelle: Tendance {trend_data['interpretation'].lower()}\n")
                    elif metric == 'sum':
                        f.write(f"    Surface totale annuelle: Tendance {trend_data['interpretation'].lower()}\n")
                    elif metric == 'mean':
                        f.write(f"    Surface moyenne annuelle: Tendance {trend_data['interpretation'].lower()}\n")
            f.write("\n")
        
        # Migration des centroïdes
        if 'centroid_evolution' in temporal_analysis:
            f.write("7.2 Migration spatiale des centroïdes:\n")
            centroid_evol = temporal_analysis['centroid_evolution']
            
            if 'spatial_migration' in centroid_evol:
                migration = centroid_evol['spatial_migration']
                if migration.get('status') != 'insufficient_data':
                    f.write(f"    Migration annuelle moyenne: {migration['mean_annual_migration']:.4f}°\n")
                    f.write(f"    Migration maximale: {migration['max_annual_migration']:.4f}°\n")
                    f.write(f"    Migration totale: {migration['total_migration']:.4f}°\n")
                    f.write(f"    Tendance de migration: {migration['migration_trend']}\n")
                else:
                    f.write("    Données insuffisantes pour analyser la migration\n")
            f.write("\n")
    
    def _write_quality_assessment(self, f, analysis: Dict[str, Any]):
        """Écrit l'évaluation de qualité."""
        f.write("8. ÉVALUATION DE LA QUALITÉ DES DONNÉES SPATIALES\n")
        f.write("-" * 55 + "\n")
        
        quality = analysis.get('quality_metrics', {})
        
        # Complétude des données
        if 'data_completeness' in quality:
            completeness = quality['data_completeness']
            f.write("8.1 Complétude des données:\n")
            f.write(f"    Colonnes requises: {len(completeness['required_columns'])}\n")
            f.write(f"    Colonnes présentes: {len(completeness['present_columns'])}\n")
            f.write(f"    Taux de complétude: {completeness['completeness_ratio']:.1%}\n")
            
            if completeness['missing_columns']:
                f.write(f"    Colonnes manquantes: {', '.join(completeness['missing_columns'])}\n")
            f.write("\n")
        
        # Validation des coordonnées
        if 'coordinate_validation' in quality:
            coord_val = quality['coordinate_validation']
            f.write("8.2 Validation des coordonnées géographiques:\n")
            f.write(f"    Coordonnées valides: {coord_val['valid_coordinates']}/{coord_val['total_events']}\n")
            f.write(f"    Taux de validité: {coord_val['validity_ratio']:.1%}\n")
            
            if coord_val['invalid_coordinates'] > 0:
                f.write(f"    ⚠️  Coordonnées invalides détectées: {coord_val['invalid_coordinates']}\n")
            f.write("\n")
        
        # Validation physique
        if 'physical_validation' in quality:
            phys_val = quality['physical_validation']
            f.write("8.3 Validation des valeurs physiques:\n")
            
            if 'area_validation' in phys_val:
                area_val = phys_val['area_validation']
                f.write(f"    Surfaces valides: {area_val['valid_areas']}/{area_val['valid_areas'] + area_val['invalid_areas']}\n")
                f.write(f"    Taux de validité (surfaces): {area_val['validity_ratio']:.1%}\n")
            
            if 'intensity_validation' in phys_val:
                intensity_val = phys_val['intensity_validation']
                f.write(f"    Intensités valides: {intensity_val['valid_intensities']}/{intensity_val['valid_intensities'] + intensity_val['invalid_intensities']}\n")
                f.write(f"    Taux de validité (intensités): {intensity_val['validity_ratio']:.1%}\n")
            f.write("\n")
        
        # Score de qualité global
        if 'overall_quality' in quality:
            overall = quality['overall_quality']
            f.write("8.4 Évaluation globale de qualité:\n")
            f.write(f"    Score de qualité: {overall['quality_score']:.1%}\n")
            f.write(f"    Niveau de qualité: {overall['quality_level']}\n\n")
    
    def _write_recommendations(self, f, analysis: Dict[str, Any], analysis_type: str):
        """Écrit les recommandations."""
        f.write("9. RECOMMANDATIONS ET PERSPECTIVES\n")
        f.write("-" * 40 + "\n")
        
        # Recommandations basées sur l'analyse
        recommendations = self._generate_smart_recommendations(analysis, analysis_type)
        
        f.write("9.1 Recommandations opérationnelles:\n")
        for i, rec in enumerate(recommendations['operational'], 1):
            f.write(f"    {i}. {rec}\n")
        f.write("\n")
        
        f.write("9.2 Recommandations de surveillance:\n")
        for i, rec in enumerate(recommendations['surveillance'], 1):
            f.write(f"    {i}. {rec}\n")
        f.write("\n")
        
        f.write("9.3 Recommandations scientifiques:\n")
        for i, rec in enumerate(recommendations['scientific'], 1):
            f.write(f"    {i}. {rec}\n")
        f.write("\n")
        
        f.write("9.4 Perspectives d'amélioration:\n")
        for i, rec in enumerate(recommendations['improvements'], 1):
            f.write(f"    {i}. {rec}\n")
        f.write("\n")
    
    def _write_technical_appendix(self, f, df: pd.DataFrame, analysis: Dict[str, Any]):
        """Écrit l'annexe technique."""
        f.write("10. ANNEXE TECHNIQUE\n")
        f.write("-" * 25 + "\n")
        
        f.write("10.1 Méthodologie d'analyse spatiale:\n")
        f.write("    • Source des données: CHIRPS (0.25° ~25km résolution)\n")
        f.write("    • Métriques calculées: Surface, intensité, centroïde, compacité\n")
        f.write("    • Classification automatique par phases de saison des pluies\n")
        f.write("    • Identification géographique avec SenegalGeography\n")
        f.write("    • Analyse de clustering spatial par grille 5x5\n")
        f.write("    • Validation multi-critères des données\n\n")
        
        f.write("10.2 Structure des données analysées:\n")
        f.write(f"    • Nombre total d'événements: {len(df)}\n")
        f.write(f"    • Colonnes disponibles: {len(df.columns)}\n")
        f.write(f"    • Variables spatiales: {', '.join([col for col in df.columns if any(x in col for x in ['area', 'intensity', 'centroid', 'coverage'])])}\n")
        
        if 'phase' in df.columns:
            f.write(f"    • Classification par phases: Oui\n")
        if 'region' in df.columns:
            f.write(f"    • Identification géographique: Oui\n")
        f.write("\n")
        
        f.write("10.3 Paramètres de configuration:\n")
        try:
            config_summary = get_configuration_summary()
            f.write(f"    • Version de la plateforme: {config_summary.get('project_info', {}).get('version', '2.0.0')}\n")
            f.write(f"    • Phases configurées: {config_summary.get('phases_count', 4)}\n")
            f.write(f"    • Zones climatiques: {config_summary.get('climate_zones_count', 4)}\n")
        except:
            f.write("    • Configuration standard utilisée\n")
        f.write("\n")
        
        f.write("10.4 Formules utilisées:\n")
        f.write("    • Surface pixel: lat_km × lon_km × cos(latitude)\n")
        f.write("    • Distance: Formule de Haversine\n")
        f.write("    • Compacité: 4π × Area / Perimeter²\n")
        f.write("    • Corrélation: Coefficient de Pearson\n")
        f.write("    • Clustering: Grille géographique + seuil statistique\n\n")
        
        f.write("10.5 Contact et support:\n")
        contact_email = self.project_info.get('contact_email', 'contact@recherche-climat.org')
        f.write(f"    • Email: {contact_email}\n")
        doc_url = self.project_info.get('documentation_url', 'https://github.com/projet-senegal-climat')
        f.write(f"    • Documentation: {doc_url}\n")
        f.write(f"    • Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("FIN DU RAPPORT SPATIAL\n")
        f.write("=" * 80 + "\n")
    
    def _generate_smart_recommendations(self, analysis: Dict[str, Any], analysis_type: str) -> Dict[str, List[str]]:
        """Génère des recommandations intelligentes basées sur l'analyse."""
        recommendations = {
            'operational': [],
            'surveillance': [],
            'scientific': [],
            'improvements': []
        }
        
        # Recommandations opérationnelles
        general_stats = analysis.get('general_statistics', {})
        if general_stats.get('peak_intensity', 0) > 100:
            recommendations['operational'].append(
                f"Infrastructure adaptée aux intensités extrêmes (jusqu'à {general_stats['peak_intensity']:.0f} mm/jour)"
            )
        
        if general_stats.get('largest_event_size', 0) > 50000:
            recommendations['operational'].append(
                f"Systèmes d'alerte précoce pour événements de grande envergure (>{general_stats['largest_event_size']:.0f} km²)"
            )
        
        # Recommandations de surveillance
        geo_analysis = analysis.get('geographic_distribution', {})
        if 'regional_distribution' in geo_analysis:
            most_affected = geo_analysis['regional_distribution'].get('most_affected_region')
            if most_affected:
                recommendations['surveillance'].append(f"Surveillance prioritaire de la région {most_affected}")
        
        hotspots = geo_analysis.get('hotspots', {})
        if hotspots.get('hotspot_count', 0) > 0:
            recommendations['surveillance'].append(
                f"Monitoring renforcé des {hotspots['hotspot_count']} hotspots identifiés"
            )
        
        # Recommandations scientifiques
        phase_analysis = analysis.get('phase_analysis', {})
        if 'phase_distribution' in phase_analysis:
            dominant_phase = max(phase_analysis['phase_distribution'].items(), 
                               key=lambda x: x[1].get('percentage', 0))
            recommendations['scientific'].append(
                f"Études approfondies pendant la {dominant_phase[1].get('description', 'phase dominante').lower()}"
            )
        
        clustering = analysis.get('spatial_clustering', {})
        if 'spatial_dispersion' in clustering:
            cluster_level = clustering['spatial_dispersion'].get('clustering_level', '')
            if cluster_level in ['Très concentré', 'Concentré']:
                recommendations['scientific'].append(
                    "Investigation des mécanismes de concentration spatiale des événements"
                )
        
        # Recommandations d'amélioration
        quality = analysis.get('quality_metrics', {})
        if 'overall_quality' in quality:
            quality_level = quality['overall_quality'].get('quality_level', '')
            if quality_level in ['ACCEPTABLE', 'INSUFFISANT']:
                recommendations['improvements'].append("Amélioration de la qualité des données d'entrée")
        
        recommendations['improvements'].extend([
            "Intégration avec données pluviométriques in-situ pour validation",
            "Développement de modèles prédictifs basés sur les patterns identifiés",
            "Extension de l'analyse à d'autres pays sahéliens",
            "Couplage avec indices climatiques (ENSO, IOD, AMO)"
        ])
        
        return recommendations
    
    def _generate_empty_report(self, analysis_type: str, title: str) -> str:
        """Génère un rapport vide en cas d'absence de données."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        filename = f"rapport_spatial_{analysis_type.lower()}_empty.txt"
        report_path = self.output_dir / filename
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"RAPPORT SPATIAL - {title.upper()}\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Date de génération: {timestamp}\n")
            f.write(f"Type d'analyse: {analysis_type}\n")
            f.write(f"Statut: AUCUNE DONNÉE À ANALYSER\n\n")
            f.write("RÉSUMÉ:\n")
            f.write("Aucun résultat spatial n'a été fourni pour l'analyse.\n")
            f.write("Veuillez vérifier les données d'entrée et relancer l'analyse.\n\n")
            f.write("RECOMMANDATIONS:\n")
            f.write("1. Vérifier la détection des événements extrêmes\n")
            f.write("2. Contrôler les critères de sélection\n")
            f.write("3. Valider les données CHIRPS d'entrée\n")
        
        print(f"✅ Rapport vide généré: {report_path}")
        return str(report_path)
    
    def generate_spatial_summary_json(self, spatial_results: List[Dict[str, Any]], 
                                    analysis_type: str = "spatial_analysis") -> str:
        """
        Génère un résumé JSON des analyses spatiales.
        
        Args:
            spatial_results (List[Dict]): Résultats de l'analyse spatiale
            analysis_type (str): Type d'analyse
            
        Returns:
            str: Chemin du fichier JSON généré
        """
        print(f"\n📊 GÉNÉRATION DU RÉSUMÉ JSON SPATIAL")
        print("-" * 50)
        
        if not spatial_results:
            return self._generate_empty_json(analysis_type)
        
        # Convertir en DataFrame et enrichir
        df = pd.DataFrame(spatial_results)
        df_enriched = self._enrich_spatial_data(df, None)
        
        # Effectuer l'analyse
        analysis = self._perform_comprehensive_spatial_analysis(df_enriched)
        
        # Créer le résumé JSON
        summary = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'analysis_type': analysis_type,
                'generator_version': '2.0.0',
                'project_info': self.project_info
            },
            'summary_statistics': {
                'total_events': len(spatial_results),
                'total_area_affected_km2': float(df['total_area_km2'].sum()) if 'total_area_km2' in df.columns else 0,
                'average_event_size_km2': float(df['total_area_km2'].mean()) if 'total_area_km2' in df.columns else 0,
                'peak_intensity_mm': float(df['max_intensity_mm'].max()) if 'max_intensity_mm' in df.columns else 0,
                'average_intensity_mm': float(df['max_intensity_mm'].mean()) if 'max_intensity_mm' in df.columns else 0
            },
            'spatial_analysis': self._convert_numpy_types(analysis),
            'top_events': spatial_results[:10],  # Top 10
            'quality_assessment': analysis.get('quality_metrics', {}),
            'recommendations': self._generate_smart_recommendations(analysis, analysis_type)
        }
        
        # Convertir les types NumPy
        summary = self._convert_numpy_types(summary)
        
        # Sauvegarder
        filename = f"resume_spatial_{analysis_type.lower()}_{datetime.now().strftime('%Y%m%d')}.json"
        json_path = self.output_dir / filename
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Résumé JSON généré: {json_path}")
        return str(json_path)
    
    def _generate_empty_json(self, analysis_type: str) -> str:
        """Génère un JSON vide."""
        empty_summary = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'analysis_type': analysis_type,
                'status': 'no_data'
            },
            'summary_statistics': {
                'total_events': 0
            },
            'message': 'Aucune donnée spatiale à analyser'
        }
        
        filename = f"resume_spatial_{analysis_type.lower()}_empty.json"
        json_path = self.output_dir / filename
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(empty_summary, f, indent=2, ensure_ascii=False)
        
        return str(json_path)
    
    def _convert_numpy_types(self, obj):
        """Convertit les types NumPy pour la sérialisation JSON - VERSION CORRIGÉE."""
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d')
        elif isinstance(obj, pd.Series):
            return obj.tolist()
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, dict):
            converted_dict = {}
            for key, value in obj.items():
                if isinstance(key, tuple):
                    key_str = '_'.join(str(k) for k in key)
                elif isinstance(key, (np.integer, np.floating)):
                    key_str = str(int(key) if isinstance(key, np.integer) else float(key))
                elif pd.isna(key):
                    key_str = 'unknown'
                else:
                    key_str = str(key)
                converted_dict[key_str] = self._convert_numpy_types(value)
            return converted_dict
        elif isinstance(obj, list):
            return [self._convert_numpy_types(item) for item in obj]
        elif isinstance(obj, tuple):
            return list(obj)
        elif pd.isna(obj):
            return None
        elif hasattr(obj, 'item'):
            try:
                return obj.item()
            except:
                return str(obj)
        else:
            return obj
    def generate_all_spatial_reports(self, spatial_results: List[Dict[str, Any]], 
                                   analysis_type: str = "comprehensive_spatial",
                                   title: str = "Analyse Spatiale Complète",
                                   df_events: Optional[pd.DataFrame] = None) -> Dict[str, str]:
        """
        Génère tous les rapports spatiaux (TXT + JSON).
        
        Args:
            spatial_results (List[Dict]): Résultats de l'analyse spatiale
            analysis_type (str): Type d'analyse
            title (str): Titre des rapports
            df_events (pd.DataFrame, optional): DataFrame des événements
            
        Returns:
            Dict[str, str]: Chemins des fichiers générés
        """
        print("🗺️  GÉNÉRATION COMPLÈTE DES RAPPORTS SPATIAUX")
        print("=" * 60)
        
        generated_files = {}
        
        try:
            # 1. Rapport texte complet
            print("📄 Génération du rapport texte...")
            text_report = self.generate_comprehensive_spatial_report(
                spatial_results, analysis_type, title, df_events
            )
            generated_files['text_report'] = text_report
            
            # 2. Résumé JSON
            print("📊 Génération du résumé JSON...")
            json_summary = self.generate_spatial_summary_json(spatial_results, analysis_type)
            generated_files['json_summary'] = json_summary
            
            print(f"\n✅ TOUS LES RAPPORTS SPATIAUX GÉNÉRÉS!")
            print(f"   Fichiers créés: {len(generated_files)}")
            for report_type, path in generated_files.items():
                print(f"   • {report_type}: {path}")
            
            return generated_files
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération: {e}")
            import traceback
            traceback.print_exc()
            return generated_files


# Classe de compatibilité avec l'ancienne interface
class SpatialReportGenerator(EnhancedSpatialReportGenerator):
    """Alias pour compatibilité avec l'ancien nom."""
    
    def generate_comprehensive_report(self, spatial_results: List[Dict[str, Any]], 
                                    analysis_type: str, title: str) -> str:
        """
        Version de compatibilité de la méthode principale.
        
        Args:
            spatial_results (List[Dict]): Résultats de l'analyse spatiale
            analysis_type (str): Type d'analyse
            title (str): Titre du rapport
            
        Returns:
            str: Chemin du fichier généré
        """
        return self.generate_comprehensive_spatial_report(
            spatial_results, analysis_type, title
        )


# Fonctions utilitaires pour l'export et l'analyse
def create_spatial_report(spatial_results: List[Dict[str, Any]], 
                         analysis_type: str = "spatial_analysis",
                         title: str = "Analyse Spatiale",
                         output_dir: Optional[Path] = None,
                         df_events: Optional[pd.DataFrame] = None) -> Dict[str, str]:
    """
    Fonction de convenance pour créer un rapport spatial complet.
    
    Args:
        spatial_results (List[Dict]): Résultats de l'analyse spatiale
        analysis_type (str): Type d'analyse
        title (str): Titre du rapport
        output_dir (Path, optional): Dossier de sortie
        df_events (pd.DataFrame, optional): DataFrame des événements
        
    Returns:
        Dict[str, str]: Chemins des fichiers générés
    """
    generator = EnhancedSpatialReportGenerator(output_dir)
    return generator.generate_all_spatial_reports(
        spatial_results, analysis_type, title, df_events
    )


def analyze_spatial_quality(spatial_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fonction utilitaire pour analyser rapidement la qualité des données spatiales.
    
    Args:
        spatial_results (List[Dict]): Résultats de l'analyse spatiale
        
    Returns:
        Dict[str, Any]: Métriques de qualité
    """
    if not spatial_results:
        return {'status': 'no_data', 'quality_level': 'INSUFFISANT'}
    
    generator = EnhancedSpatialReportGenerator()
    df = pd.DataFrame(spatial_results)
    df_enriched = generator._enrich_spatial_data(df, None)
    analysis = generator._perform_comprehensive_spatial_analysis(df_enriched)
    
    return analysis.get('quality_metrics', {})


if __name__ == "__main__":
    print("🗺️  Module de génération de rapports spatiaux avancés - Version 2.0.0")
    print("=" * 80)
    print("Ce module contient les outils pour:")
    print("• Générer des rapports spatiaux complets et détaillés")
    print("• Analyser la distribution géographique des événements")
    print("• Évaluer les patterns spatiaux par phases de saison des pluies")
    print("• Identifier les hotspots géographiques automatiquement")
    print("• Calculer des métriques de qualité spatiale")
    print("• Analyser le clustering et la dispersion spatiale")
    print("• Suivre l'évolution spatio-temporelle")
    print("• Générer des recommandations intelligentes")
    print()
    print("🆕 Nouvelles fonctionnalités:")
    print("• Intégration complète avec SenegalGeography")
    print("• Classification automatique par phases de saison des pluies")
    print("• Analyse de hotspots avec détection automatique")
    print("• Métriques de forme avancées (compacité, élongation)")
    print("• Validation multi-critères des données spatiales")
    print("• Export dual (TXT détaillé + JSON machine-readable)")
    print("• Recommandations contextuelles basées sur l'analyse")
    print("• Clustering spatial et analyse de migration temporelle")
    print()
    print("📊 Utilisation:")
    print("generator = EnhancedSpatialReportGenerator()")
    print("files = generator.generate_all_spatial_reports(spatial_results, 'analysis', 'Titre')")
    print("quality = analyze_spatial_quality(spatial_results)")
    print()
    print("✅ Module prêt à l'utilisation!")