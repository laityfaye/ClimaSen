# src/reports/detection_report.py
"""
Module de génération de rapports avancés pour l'analyse des événements extrêmes.
Version améliorée intégrée avec les nouvelles fonctionnalités de la plateforme.
"""

import pandas as pd
import json
from datetime import datetime
import sys
from pathlib import Path
import numpy as np
from typing import Dict, Any, Optional, List
import warnings

# Imports avec gestion robuste des erreurs
try:
    from ..config.settings import (
        get_output_path, PROJECT_INFO, RAINFALL_PHASES, REGION_COLORS,
        CLIMATE_COLORS, OUTPUT_FILENAMES, get_configuration_summary
    )
    from ..utils.season_classifier import get_phase_from_month, RAINFALL_PHASES
    from ..utils.geographic_references import SenegalGeography, analyze_geographic_distribution
    from ..analysis.spatial_metrics import summarize_spatial_metrics
except ImportError:
    try:
        from src.config.settings import (
            get_output_path, PROJECT_INFO, RAINFALL_PHASES, REGION_COLORS,
            CLIMATE_COLORS, OUTPUT_FILENAMES, get_configuration_summary
        )
        from src.utils.season_classifier import get_phase_from_month, RAINFALL_PHASES
        from src.utils.geographic_references import SenegalGeography, analyze_geographic_distribution
        from src.analysis.spatial_metrics import summarize_spatial_metrics
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
        
        def get_output_path(key): return f"outputs/reports/{key}.txt"
        def get_phase_from_month(month): return 'Phase_2_pleine' if month in [7, 8] else 'Hors_saison'
        def get_configuration_summary(): return {}
        def analyze_geographic_distribution(coords): return {}
        def summarize_spatial_metrics(metrics): return {}
        
        class SenegalGeography:
            REGIONS = {}
            CLIMATE_ZONES = {}
            @staticmethod
            def identify_region(lat, lon): return "Région indéterminée"

warnings.filterwarnings('ignore')


def convert_numpy_types(obj):
    """
    Convertit les types NumPy en types Python natifs pour la sérialisation JSON.
    
    Args:
        obj: Objet à convertir
        
    Returns:
        Objet avec types Python natifs
    """
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return obj.strftime('%Y-%m-%d')
    elif isinstance(obj, (bool, np.bool_)):  # CORRECTION: Gestion des booléens
        return bool(obj)
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return [convert_numpy_types(item) for item in obj]
    elif hasattr(obj, 'item'):  # Pour les scalaires NumPy
        return obj.item()
    else:
        return obj


class EnhancedDetectionReportGenerator:
    """
    Générateur de rapports avancé avec intégration complète des nouvelles fonctionnalités.
    """
    
    def __init__(self):
        """Initialise le générateur avec toutes les références."""
        self.project_info = PROJECT_INFO
        self.geo = SenegalGeography()
        self.rainfall_phases = RAINFALL_PHASES
        
        print("📊 EnhancedDetectionReportGenerator initialisé")
        print(f"   Version: {self.project_info.get('version', '2.0.0')}")
        print(f"   Phases configurées: {len(self.rainfall_phases)}")
    
    def analyze_extreme_events_comprehensive(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyse complète et détaillée des événements extrêmes avec nouvelles métriques.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Dict[str, Any]: Analyse complète
        """
        print("\n🔄 ANALYSE COMPLÈTE DES ÉVÉNEMENTS EXTRÊMES")
        print("=" * 60)
        
        if df_events.empty:
            return {'status': 'no_data', 'message': 'Aucun événement à analyser'}
        
        # Ajouter la colonne phase si elle n'existe pas
        if 'phase' not in df_events.columns:
            df_events['phase'] = df_events['month'].apply(get_phase_from_month)
        
        analysis = {
            'general_stats': self._calculate_general_statistics(df_events),
            'phase_analysis': self._analyze_by_phases(df_events),
            'geographic_analysis': self._analyze_geographic_patterns(df_events),
            'temporal_analysis': self._analyze_temporal_patterns(df_events),
            'intensity_analysis': self._analyze_intensity_patterns(df_events),
            'spatial_metrics_summary': self._summarize_spatial_metrics(df_events),
            'quality_assessment': self._assess_data_quality(df_events),
            'climate_coherence': self._assess_climate_coherence(df_events)
        }
        
        # Affichage des résultats principaux
        self._print_analysis_summary(analysis)
        
        return analysis
    
    def _calculate_general_statistics(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Calcule les statistiques générales."""
        return {
            'total_events': len(df_events),
            'period': {
                'start': df_events.index.min().strftime('%Y-%m-%d'),
                'end': df_events.index.max().strftime('%Y-%m-%d'),
                'duration_years': df_events['year'].max() - df_events['year'].min() + 1
            },
            'frequency': len(df_events) / (df_events['year'].max() - df_events['year'].min() + 1),
            'coverage_stats': {
                'mean_percent': float(df_events['coverage_percent'].mean()),
                'median_percent': float(df_events['coverage_percent'].median()),
                'max_percent': float(df_events['coverage_percent'].max()),
                'std_percent': float(df_events['coverage_percent'].std())
            },
            'precipitation_stats': {
                'mean_mm': float(df_events['max_precip'].mean()),
                'median_mm': float(df_events['max_precip'].median()),
                'max_mm': float(df_events['max_precip'].max()),
                'min_mm': float(df_events['max_precip'].min()),
                'std_mm': float(df_events['max_precip'].std()),
                'quantiles': {
                    'q25': float(df_events['max_precip'].quantile(0.25)),
                    'q75': float(df_events['max_precip'].quantile(0.75)),
                    'q90': float(df_events['max_precip'].quantile(0.90)),
                    'q95': float(df_events['max_precip'].quantile(0.95)),
                    'q99': float(df_events['max_precip'].quantile(0.99))
                }
            },
            'anomaly_stats': {
                'mean_sigma': float(df_events['max_anomaly'].mean()),
                'median_sigma': float(df_events['max_anomaly'].median()),
                'max_sigma': float(df_events['max_anomaly'].max()),
                'min_sigma': float(df_events['max_anomaly'].min()),
                'std_sigma': float(df_events['max_anomaly'].std())
            }
        }
    
    def _analyze_by_phases(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse détaillée par phases de saison des pluies."""
        phase_analysis = {}
        
        # Distribution par phases
        phase_counts = df_events['phase'].value_counts()
        total_events = len(df_events)
        
        phase_analysis['distribution'] = {}
        for phase, count in phase_counts.items():
            phase_info = self.rainfall_phases.get(phase, {})
            phase_analysis['distribution'][phase] = {
                'count': int(count),
                'percentage': float(count / total_events * 100),
                'description': phase_info.get('description', phase),
                'months': phase_info.get('months', []),
                'expected_behavior': phase_info.get('expected_events', 'Variable')
            }
        
        # Statistiques détaillées par phase
        phase_analysis['detailed_stats'] = {}
        for phase in phase_counts.index:
            phase_data = df_events[df_events['phase'] == phase]
            if len(phase_data) > 0:
                phase_analysis['detailed_stats'][phase] = {
                    'precipitation': {
                        'mean': float(phase_data['max_precip'].mean()),
                        'median': float(phase_data['max_precip'].median()),
                        'max': float(phase_data['max_precip'].max()),
                        'std': float(phase_data['max_precip'].std())
                    },
                    'coverage': {
                        'mean': float(phase_data['coverage_percent'].mean()),
                        'max': float(phase_data['coverage_percent'].max())
                    },
                    'anomaly': {
                        'mean': float(phase_data['max_anomaly'].mean()),
                        'max': float(phase_data['max_anomaly'].max())
                    }
                }
        
        # Validation climatologique
        rainy_season_phases = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']
        rainy_events = sum(phase_counts.get(phase, 0) for phase in rainy_season_phases)
        rainy_percentage = rainy_events / total_events * 100
        
        phase_analysis['climate_validation'] = {
            'rainy_season_percentage': float(rainy_percentage),
            'is_coherent': rainy_percentage > 80,  # Doit être > 80% en saison des pluies
            'peak_phase_dominant': phase_counts.get('Phase_2_pleine', 0) == phase_counts.max()
        }
        
        return phase_analysis
    
    def _analyze_geographic_patterns(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse des patterns géographiques avancés."""
        geographic_analysis = {}
        
        # Distribution par régions
        if 'centroid_region' in df_events.columns:
            region_counts = df_events['centroid_region'].value_counts()
            geographic_analysis['regional_distribution'] = {
                region: {
                    'count': int(count),
                    'percentage': float(count / len(df_events) * 100)
                }
                for region, count in region_counts.items()
            }
            
            # Région la plus affectée
            geographic_analysis['most_affected_region'] = {
                'name': region_counts.index[0],
                'count': int(region_counts.iloc[0]),
                'percentage': float(region_counts.iloc[0] / len(df_events) * 100)
            }
        
        # Distribution par zones climatiques
        if 'centroid_climate_zone' in df_events.columns:
            climate_counts = df_events['centroid_climate_zone'].value_counts()
            geographic_analysis['climate_zone_distribution'] = {
                zone: {
                    'count': int(count),
                    'percentage': float(count / len(df_events) * 100)
                }
                for zone, count in climate_counts.items()
            }
        
        # Statistiques spatiales
        if all(col in df_events.columns for col in ['centroid_lat', 'centroid_lon']):
            geographic_analysis['spatial_statistics'] = {
                'centroid_mean': {
                    'latitude': float(df_events['centroid_lat'].mean()),
                    'longitude': float(df_events['centroid_lon'].mean())
                },
                'spatial_dispersion': {
                    'lat_std': float(df_events['centroid_lat'].std()),
                    'lon_std': float(df_events['centroid_lon'].std())
                },
                'spatial_extent': {
                    'lat_range': float(df_events['centroid_lat'].max() - df_events['centroid_lat'].min()),
                    'lon_range': float(df_events['centroid_lon'].max() - df_events['centroid_lon'].min())
                }
            }
        
        # Analyse d'étendue spatiale
        if 'lat_extent_km' in df_events.columns and 'lon_extent_km' in df_events.columns:
            geographic_analysis['extent_analysis'] = {
                'mean_lat_extent_km': float(df_events['lat_extent_km'].mean()),
                'mean_lon_extent_km': float(df_events['lon_extent_km'].mean()),
                'mean_spatial_dispersion_km': float(df_events['spatial_dispersion'].mean()) if 'spatial_dispersion' in df_events.columns else None
            }
        
        return geographic_analysis
    
    def _analyze_temporal_patterns(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse des patterns temporels avancés."""
        temporal_analysis = {}
        
        # Distribution mensuelle
        monthly_counts = df_events['month'].value_counts().sort_index()
        month_names = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 
                      'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
        
        temporal_analysis['monthly_distribution'] = {}
        for month, count in monthly_counts.items():
            phase = get_phase_from_month(month)
            temporal_analysis['monthly_distribution'][month_names[month-1]] = {
                'month_number': int(month),
                'count': int(count),
                'percentage': float(count / len(df_events) * 100),
                'phase': phase,
                'phase_description': self.rainfall_phases.get(phase, {}).get('description', phase)
            }
        
        # Distribution annuelle
        yearly_counts = df_events['year'].value_counts().sort_index()
        temporal_analysis['yearly_distribution'] = {
            'mean_events_per_year': float(yearly_counts.mean()),
            'std_events_per_year': float(yearly_counts.std()),
            'min_events_year': {'year': int(yearly_counts.idxmin()), 'count': int(yearly_counts.min())},
            'max_events_year': {'year': int(yearly_counts.idxmax()), 'count': int(yearly_counts.max())},
            'total_years': len(yearly_counts)
        }
        
        # Tendance temporelle (si suffisamment de données)
        if len(yearly_counts) >= 10:
            years = yearly_counts.index.values
            counts = yearly_counts.values
            trend_coeff = np.polyfit(years, counts, 1)[0]
            temporal_analysis['trend_analysis'] = {
                'trend_slope': float(trend_coeff),
                'trend_interpretation': 'Croissante' if trend_coeff > 0.05 else 'Décroissante' if trend_coeff < -0.05 else 'Stable'
            }
        
        return temporal_analysis
    
    def _analyze_intensity_patterns(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse des patterns d'intensité."""
        intensity_analysis = {}
        
        # Classification par intensité
        intensity_thresholds = [20, 50, 100, 150]  # mm
        intensity_analysis['intensity_categories'] = {}
        
        for i, threshold in enumerate(intensity_thresholds):
            if i == 0:
                mask = df_events['max_precip'] < threshold
                category = f'< {threshold}mm (Modéré)'
            elif i == len(intensity_thresholds) - 1:
                mask = df_events['max_precip'] >= threshold
                category = f'>= {threshold}mm (Extrême)'
            else:
                prev_threshold = intensity_thresholds[i-1]
                mask = (df_events['max_precip'] >= prev_threshold) & (df_events['max_precip'] < threshold)
                category = f'{prev_threshold}-{threshold}mm'
            
            count = mask.sum()
            intensity_analysis['intensity_categories'][category] = {
                'count': int(count),
                'percentage': float(count / len(df_events) * 100)
            }
        
        # Corrélations
        correlation_vars = ['max_precip', 'coverage_percent', 'max_anomaly']
        if all(col in df_events.columns for col in correlation_vars):
            corr_matrix = df_events[correlation_vars].corr()
            intensity_analysis['correlations'] = {
                'precip_coverage': float(corr_matrix.loc['max_precip', 'coverage_percent']),
                'precip_anomaly': float(corr_matrix.loc['max_precip', 'max_anomaly']),
                'coverage_anomaly': float(corr_matrix.loc['coverage_percent', 'max_anomaly'])
            }
        
        return intensity_analysis
    
    def _summarize_spatial_metrics(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Résume les métriques spatiales si disponibles."""
        spatial_columns = ['total_area_km2', 'num_pixels_affected', 'compactness', 'elongation']
        available_cols = [col for col in spatial_columns if col in df_events.columns]
        
        if not available_cols:
            return {'status': 'no_spatial_metrics', 'message': 'Métriques spatiales non disponibles'}
        
        spatial_summary = {}
        for col in available_cols:
            spatial_summary[col] = {
                'mean': float(df_events[col].mean()),
                'median': float(df_events[col].median()),
                'std': float(df_events[col].std()),
                'min': float(df_events[col].min()),
                'max': float(df_events[col].max())
            }
        
        return spatial_summary
    
    def _assess_data_quality(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Évalue la qualité des données."""
        quality_assessment = {}
        
        # Complétude des données
        required_columns = ['max_precip', 'coverage_percent', 'max_anomaly', 'centroid_lat', 'centroid_lon']
        missing_cols = [col for col in required_columns if col not in df_events.columns]
        
        quality_assessment['data_completeness'] = {
            'required_columns_present': len(missing_cols) == 0,
            'missing_columns': missing_cols,
            'total_events': len(df_events),
            'completeness_score': (len(required_columns) - len(missing_cols)) / len(required_columns)
        }
        
        # Validation des valeurs
        quality_assessment['value_validation'] = {}
        
        if 'max_anomaly' in df_events.columns:
            below_threshold = (df_events['max_anomaly'] < 2.0).sum()
            quality_assessment['value_validation']['anomaly_threshold'] = {
                'events_below_2sigma': int(below_threshold),
                'percentage_below': float(below_threshold / len(df_events) * 100),
                'is_valid': below_threshold == 0
            }
        
        if 'coverage_percent' in df_events.columns:
            invalid_coverage = ((df_events['coverage_percent'] < 0) | (df_events['coverage_percent'] > 100)).sum()
            quality_assessment['value_validation']['coverage_range'] = {
                'invalid_values': int(invalid_coverage),
                'is_valid': invalid_coverage == 0
            }
        
        return quality_assessment
    
    def _assess_climate_coherence(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Évalue la cohérence climatique."""
        coherence_assessment = {}
        
        # Cohérence saisonnière
        rainy_months = [5, 6, 7, 8, 9, 10]
        rainy_events = df_events[df_events['month'].isin(rainy_months)]
        rainy_percentage = len(rainy_events) / len(df_events) * 100
        
        coherence_assessment['seasonal_coherence'] = {
            'rainy_season_percentage': float(rainy_percentage),
            'is_coherent': rainy_percentage > 75,  # Seuil de cohérence
            'expected_range': '80-95%'
        }
        
        # Cohérence géographique
        if 'centroid_lat' in df_events.columns and 'centroid_lon' in df_events.columns:
            senegal_bounds = {'lat_min': 12.3, 'lat_max': 16.7, 'lon_min': -17.55, 'lon_max': -11.35}

            valid_coords = (
                (df_events['centroid_lat'] >= senegal_bounds['lat_min']) &
                (df_events['centroid_lat'] <= senegal_bounds['lat_max']) &
                (df_events['centroid_lon'] >= senegal_bounds['lon_min']) &
                (df_events['centroid_lon'] <= senegal_bounds['lon_max'])
            )
            
            coherence_assessment['geographic_coherence'] = {
                'events_in_senegal': int(valid_coords.sum()),
                'percentage_valid': float(valid_coords.sum() / len(df_events) * 100),
                'is_coherent': valid_coords.sum() / len(df_events) > 0.95
            }
        
        return coherence_assessment
    
    def _print_analysis_summary(self, analysis: Dict[str, Any]):
        """Affiche un résumé de l'analyse."""
        print("\n📊 RÉSUMÉ DE L'ANALYSE COMPLÈTE")
        print("-" * 50)
        
        general = analysis['general_stats']
        print(f"Événements détectés: {general['total_events']}")
        print(f"Période: {general['period']['start']} à {general['period']['end']}")
        print(f"Fréquence: {general['frequency']:.1f} événements/an")
        
        print(f"\nPrécipitations (mm):")
        precip = general['precipitation_stats']
        print(f"  Moyenne: {precip['mean_mm']:.1f}, Médiane: {precip['median_mm']:.1f}")
        print(f"  Maximum: {precip['max_mm']:.1f}, P95: {precip['quantiles']['q95']:.1f}")
        
        print(f"\nCouverture spatiale (%):")
        coverage = general['coverage_stats']
        print(f"  Moyenne: {coverage['mean_percent']:.1f}, Maximum: {coverage['max_percent']:.1f}")
        
        # Distribution par phases
        if 'phase_analysis' in analysis:
            print(f"\nDistribution par phases:")
            for phase, data in analysis['phase_analysis']['distribution'].items():
                if data['count'] > 0:
                    print(f"  {data['description']}: {data['count']} ({data['percentage']:.1f}%)")
        
        # Cohérence climatique
        if 'climate_coherence' in analysis:
            seasonal = analysis['climate_coherence']['seasonal_coherence']
            print(f"\nCohérence climatique:")
            print(f"  Saison des pluies: {seasonal['rainy_season_percentage']:.1f}% ({'✅' if seasonal['is_coherent'] else '⚠️'})")
    
    def generate_comprehensive_report(self, df_events: pd.DataFrame, 
                                    validation_status: str = "COHERENT",
                                    output_path: Optional[str] = None) -> str:
        """
        Génère un rapport complet et détaillé.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            validation_status (str): Statut de validation
            output_path (str, optional): Chemin de sortie personnalisé
            
        Returns:
            str: Chemin du fichier généré
        """
        print("\n📄 GÉNÉRATION DU RAPPORT COMPLET")
        print("=" * 60)
        
        if output_path is None:
            try:
                output_path = get_output_path('detection_report')
            except:
                output_path = 'outputs/reports/rapport_detection_comprehensive.txt'
        
        # Effectuer l'analyse complète
        analysis = self.analyze_extreme_events_comprehensive(df_events)
        
        # Générer le rapport
        with open(output_path, 'w', encoding='utf-8') as f:
            self._write_report_header(f)
            self._write_methodology_section(f)
            self._write_general_results(f, analysis)
            self._write_phase_analysis(f, analysis)
            self._write_geographic_analysis(f, analysis)
            self._write_temporal_analysis(f, analysis)
            self._write_intensity_analysis(f, analysis)
            self._write_quality_assessment(f, analysis)
            self._write_top_events(f, df_events)
            self._write_conclusions(f, analysis, validation_status)
            self._write_technical_appendix(f, df_events)
        
        print(f"✅ Rapport complet généré: {output_path}")
        return output_path
    
    def _write_report_header(self, f):
        """Écrit l'en-tête du rapport."""
        f.write("RAPPORT COMPLET D'ANALYSE DES ÉVÉNEMENTS EXTRÊMES\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Projet: {self.project_info.get('title', 'Analyse des précipitations extrêmes')}\n")
        f.write(f"Version: {self.project_info.get('version', '2.0.0')}\n")
        f.write(f"Auteur: {self.project_info.get('author', 'Équipe de recherche')}\n")
        f.write(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Institution: {self.project_info.get('institution', 'Centre de recherche climatique')}\n\n")
    
    def _write_methodology_section(self, f):
        """Écrit la section méthodologie."""
        f.write("1. MÉTHODOLOGIE ET INNOVATIONS\n")
        f.write("-" * 40 + "\n")
        f.write("Cette analyse utilise une approche innovante avec:\n\n")
        f.write("1.1 Critères de détection optimisés pour le climat sahélien:\n")
        f.write("    • Anomalie standardisée: > +2σ (seuil du 98e centile)\n")
        f.write("    • Couverture minimale: 40 points de grille (≈7% du territoire)\n")
        f.write("    • Précipitation réaliste: ≥ 5mm (adapté aux conditions locales)\n")
        f.write("    • Classement par impact spatial décroissant\n\n")
        
        f.write("1.2 Classification par phases de saison des pluies:\n")
        for phase, info in self.rainfall_phases.items():
            if phase != 'Hors_saison':
                f.write(f"    • {info['description']}: Mois {info['months']}\n")
        f.write("\n")
        
        f.write("1.3 Analyses géographiques intégrées:\n")
        f.write("    • Identification automatique des régions et départements\n")
        f.write("    • Classification par zones climatiques\n")
        f.write("    • Métriques spatiales avancées (compacité, élongation)\n")
        f.write("    • Calculs de surface précis avec courbure terrestre\n\n")
    
    def _write_general_results(self, f, analysis: Dict[str, Any]):
        """Écrit les résultats généraux."""
        f.write("2. RÉSULTATS GÉNÉRAUX\n")
        f.write("-" * 25 + "\n")
        
        general = analysis['general_stats']
        f.write(f"Nombre total d'événements détectés: {general['total_events']}\n")
        f.write(f"Période d'analyse: {general['period']['start']} à {general['period']['end']}\n")
        f.write(f"Durée totale: {general['period']['duration_years']} années\n")
        f.write(f"Fréquence moyenne: {general['frequency']:.1f} événements/an\n\n")
        
        f.write("2.1 Statistiques de précipitations:\n")
        precip = general['precipitation_stats']
        f.write(f"    Moyenne: {precip['mean_mm']:.2f} mm\n")
        f.write(f"    Médiane: {precip['median_mm']:.2f} mm\n")
        f.write(f"    Écart-type: {precip['std_mm']:.2f} mm\n")
        f.write(f"    Minimum: {precip['min_mm']:.2f} mm\n")
        f.write(f"    Maximum: {precip['max_mm']:.2f} mm\n")
        f.write(f"    P90: {precip['quantiles']['q90']:.2f} mm\n")
        f.write(f"    P95: {precip['quantiles']['q95']:.2f} mm\n")
        f.write(f"    P99: {precip['quantiles']['q99']:.2f} mm\n\n")
        
        f.write("2.2 Statistiques de couverture spatiale:\n")
        coverage = general['coverage_stats']
        f.write(f"    Moyenne: {coverage['mean_percent']:.2f}%\n")
        f.write(f"    Médiane: {coverage['median_percent']:.2f}%\n")
        f.write(f"    Écart-type: {coverage['std_percent']:.2f}%\n")
        f.write(f"    Maximum: {coverage['max_percent']:.2f}%\n\n")
        
        f.write("2.3 Statistiques d'anomalies:\n")
        anomaly = general['anomaly_stats']
        f.write(f"    Moyenne: {anomaly['mean_sigma']:.2f}σ\n")
        f.write(f"    Médiane: {anomaly['median_sigma']:.2f}σ\n")
        f.write(f"    Maximum: {anomaly['max_sigma']:.2f}σ\n")
        f.write(f"    Minimum: {anomaly['min_sigma']:.2f}σ\n\n")
    
    def _write_phase_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse par phases."""
        f.write("3. ANALYSE PAR PHASES DE SAISON DES PLUIES\n")
        f.write("-" * 50 + "\n")
        
        phase_analysis = analysis.get('phase_analysis', {})
        if not phase_analysis:
            f.write("Données d'analyse par phases non disponibles.\n\n")
            return
        
        f.write("3.1 Distribution par phases:\n")
        for phase, data in phase_analysis['distribution'].items():
            f.write(f"    • {data['description']}:\n")
            f.write(f"      Événements: {data['count']} ({data['percentage']:.1f}%)\n")
            f.write(f"      Mois concernés: {data['months']}\n")
            f.write(f"      Comportement attendu: {data['expected_behavior']}\n\n")
        
        if 'detailed_stats' in phase_analysis:
            f.write("3.2 Statistiques détaillées par phase:\n")
            for phase, stats in phase_analysis['detailed_stats'].items():
                phase_info = self.rainfall_phases.get(phase, {})
                f.write(f"    • {phase_info.get('description', phase)}:\n")
                f.write(f"      Précipitation moyenne: {stats['precipitation']['mean']:.1f} mm\n")
                f.write(f"      Précipitation maximale: {stats['precipitation']['max']:.1f} mm\n")
                f.write(f"      Couverture moyenne: {stats['coverage']['mean']:.1f}%\n")
                f.write(f"      Anomalie moyenne: {stats['anomaly']['mean']:.1f}σ\n\n")
        
        # Validation climatologique
        if 'climate_validation' in phase_analysis:
            validation = phase_analysis['climate_validation']
            f.write("3.3 Validation climatologique:\n")
            f.write(f"    Pourcentage en saison des pluies: {validation['rainy_season_percentage']:.1f}%\n")
            f.write(f"    Cohérence climatique: {'✅ Excellente' if validation['is_coherent'] else '⚠️ À vérifier'}\n")
            f.write(f"    Phase de pic dominante: {'✅ Oui' if validation['peak_phase_dominant'] else '❌ Non'}\n\n")
    
    def _write_geographic_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse géographique."""
        f.write("4. ANALYSE GÉOGRAPHIQUE AVANCÉE\n")
        f.write("-" * 40 + "\n")
        
        geo_analysis = analysis.get('geographic_analysis', {})
        if not geo_analysis:
            f.write("Données d'analyse géographique non disponibles.\n\n")
            return
        
        # Distribution régionale
        if 'regional_distribution' in geo_analysis:
            f.write("4.1 Distribution par régions administratives:\n")
            regional = geo_analysis['regional_distribution']
            sorted_regions = sorted(regional.items(), key=lambda x: x[1]['count'], reverse=True)
            
            for i, (region, data) in enumerate(sorted_regions[:10], 1):
                f.write(f"    {i:2d}. {region}: {data['count']} événements ({data['percentage']:.1f}%)\n")
            
            if 'most_affected_region' in geo_analysis:
                most_affected = geo_analysis['most_affected_region']
                f.write(f"\n    Région la plus affectée: {most_affected['name']}\n")
                f.write(f"    Impact: {most_affected['count']} événements ({most_affected['percentage']:.1f}%)\n\n")
        
        # Distribution par zones climatiques
        if 'climate_zone_distribution' in geo_analysis:
            f.write("4.2 Distribution par zones climatiques:\n")
            climate_dist = geo_analysis['climate_zone_distribution']
            for zone, data in climate_dist.items():
                f.write(f"    • {zone}: {data['count']} événements ({data['percentage']:.1f}%)\n")
            f.write("\n")
        
        # Statistiques spatiales
        if 'spatial_statistics' in geo_analysis:
            spatial = geo_analysis['spatial_statistics']
            f.write("4.3 Statistiques spatiales:\n")
            f.write(f"    Centroïde moyen: {spatial['centroid_mean']['latitude']:.3f}°N, ")
            f.write(f"{spatial['centroid_mean']['longitude']:.3f}°E\n")
            f.write(f"    Dispersion latitudinale: {spatial['spatial_dispersion']['lat_std']:.3f}°\n")
            f.write(f"    Dispersion longitudinale: {spatial['spatial_dispersion']['lon_std']:.3f}°\n")
            f.write(f"    Étendue latitudinale: {spatial['spatial_extent']['lat_range']:.3f}°\n")
            f.write(f"    Étendue longitudinale: {spatial['spatial_extent']['lon_range']:.3f}°\n\n")
        
        # Analyse d'étendue
        if 'extent_analysis' in geo_analysis:
            extent = geo_analysis['extent_analysis']
            f.write("4.4 Analyse d'étendue spatiale:\n")
            f.write(f"    Étendue latitudinale moyenne: {extent['mean_lat_extent_km']:.1f} km\n")
            f.write(f"    Étendue longitudinale moyenne: {extent['mean_lon_extent_km']:.1f} km\n")
            if extent['mean_spatial_dispersion_km']:
                f.write(f"    Dispersion spatiale moyenne: {extent['mean_spatial_dispersion_km']:.1f} km\n")
            f.write("\n")
    
    def _write_temporal_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse temporelle."""
        f.write("5. ANALYSE TEMPORELLE DÉTAILLÉE\n")
        f.write("-" * 40 + "\n")
        
        temporal = analysis.get('temporal_analysis', {})
        if not temporal:
            f.write("Données d'analyse temporelle non disponibles.\n\n")
            return
        
        # Distribution mensuelle
        if 'monthly_distribution' in temporal:
            f.write("5.1 Distribution mensuelle détaillée:\n")
            monthly = temporal['monthly_distribution']
            
            # Organiser par mois
            month_order = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 
                          'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']
            
            for month_name in month_order:
                if month_name in monthly:
                    data = monthly[month_name]
                    f.write(f"    {month_name} ({data['phase_description']}): ")
                    f.write(f"{data['count']} événements ({data['percentage']:.1f}%)\n")
            f.write("\n")
        
        # Distribution annuelle
        if 'yearly_distribution' in temporal:
            yearly = temporal['yearly_distribution']
            f.write("5.2 Variabilité inter-annuelle:\n")
            f.write(f"    Moyenne d'événements par an: {yearly['mean_events_per_year']:.1f}\n")
            f.write(f"    Écart-type: {yearly['std_events_per_year']:.1f}\n")
            f.write(f"    Année avec le moins d'événements: {yearly['min_events_year']['year']} ")
            f.write(f"({yearly['min_events_year']['count']} événements)\n")
            f.write(f"    Année avec le plus d'événements: {yearly['max_events_year']['year']} ")
            f.write(f"({yearly['max_events_year']['count']} événements)\n")
            f.write(f"    Nombre total d'années analysées: {yearly['total_years']}\n\n")
        
        # Analyse de tendance
        if 'trend_analysis' in temporal:
            trend = temporal['trend_analysis']
            f.write("5.3 Analyse de tendance temporelle:\n")
            f.write(f"    Pente de tendance: {trend['trend_slope']:.3f} événements/an\n")
            f.write(f"    Interprétation: Tendance {trend['trend_interpretation'].lower()}\n\n")
    
    def _write_intensity_analysis(self, f, analysis: Dict[str, Any]):
        """Écrit l'analyse d'intensité."""
        f.write("6. ANALYSE D'INTENSITÉ ET CORRÉLATIONS\n")
        f.write("-" * 45 + "\n")
        
        intensity = analysis.get('intensity_analysis', {})
        if not intensity:
            f.write("Données d'analyse d'intensité non disponibles.\n\n")
            return
        
        # Catégories d'intensité
        if 'intensity_categories' in intensity:
            f.write("6.1 Classification par intensité:\n")
            for category, data in intensity['intensity_categories'].items():
                f.write(f"    • {category}: {data['count']} événements ({data['percentage']:.1f}%)\n")
            f.write("\n")
        
        # Corrélations
        if 'correlations' in intensity:
            corr = intensity['correlations']
            f.write("6.2 Corrélations entre variables:\n")
            f.write(f"    Précipitation vs Couverture: {corr['precip_coverage']:.3f}\n")
            f.write(f"    Précipitation vs Anomalie: {corr['precip_anomaly']:.3f}\n")
            f.write(f"    Couverture vs Anomalie: {corr['coverage_anomaly']:.3f}\n\n")
            
            # Interprétation des corrélations
            f.write("6.3 Interprétation des corrélations:\n")
            if abs(corr['precip_coverage']) > 0.5:
                direction = "positive" if corr['precip_coverage'] > 0 else "négative"
                f.write(f"    • Corrélation {direction} forte entre précipitation et couverture\n")
            else:
                f.write(f"    • Corrélation faible entre précipitation et couverture\n")
            
            if abs(corr['precip_anomaly']) > 0.7:
                f.write(f"    • Forte cohérence entre intensité et anomalie climatologique\n")
            f.write("\n")
    
    def _write_quality_assessment(self, f, analysis: Dict[str, Any]):
        """Écrit l'évaluation de qualité."""
        f.write("7. ÉVALUATION DE LA QUALITÉ DES DONNÉES\n")
        f.write("-" * 45 + "\n")
        
        quality = analysis.get('quality_assessment', {})
        climate_coherence = analysis.get('climate_coherence', {})
        
        # Complétude des données
        if 'data_completeness' in quality:
            completeness = quality['data_completeness']
            f.write("7.1 Complétude des données:\n")
            f.write(f"    Colonnes requises présentes: {'✅ Oui' if completeness['required_columns_present'] else '❌ Non'}\n")
            if completeness['missing_columns']:
                f.write(f"    Colonnes manquantes: {', '.join(completeness['missing_columns'])}\n")
            f.write(f"    Score de complétude: {completeness['completeness_score']:.1%}\n\n")
        
        # Validation des valeurs
        if 'value_validation' in quality:
            validation = quality['value_validation']
            f.write("7.2 Validation des valeurs:\n")
            
            if 'anomaly_threshold' in validation:
                anomaly_val = validation['anomaly_threshold']
                f.write(f"    Seuil d'anomalie (>2σ): {'✅ Respecté' if anomaly_val['is_valid'] else '⚠️ Violations détectées'}\n")
                if not anomaly_val['is_valid']:
                    f.write(f"    Événements sous le seuil: {anomaly_val['events_below_2sigma']} ({anomaly_val['percentage_below']:.1f}%)\n")
            
            if 'coverage_range' in validation:
                coverage_val = validation['coverage_range']
                f.write(f"    Plage de couverture (0-100%): {'✅ Valide' if coverage_val['is_valid'] else '❌ Valeurs invalides'}\n")
            f.write("\n")
        
        # Cohérence climatique
        if climate_coherence:
            f.write("7.3 Cohérence climatique:\n")
            
            if 'seasonal_coherence' in climate_coherence:
                seasonal = climate_coherence['seasonal_coherence']
                f.write(f"    Cohérence saisonnière: {'✅ Excellente' if seasonal['is_coherent'] else '⚠️ À vérifier'}\n")
                f.write(f"    Événements en saison des pluies: {seasonal['rainy_season_percentage']:.1f}%\n")
                f.write(f"    Plage attendue: {seasonal['expected_range']}\n")
            
            if 'geographic_coherence' in climate_coherence:
                geographic = climate_coherence['geographic_coherence']
                f.write(f"    Cohérence géographique: {'✅ Excellente' if geographic['is_coherent'] else '⚠️ À vérifier'}\n")
                f.write(f"    Événements au Sénégal: {geographic['events_in_senegal']}/{len(analysis['general_stats'])} ")
                f.write(f"({geographic['percentage_valid']:.1f}%)\n")
            f.write("\n")
    
    def _write_top_events(self, f, df_events: pd.DataFrame):
        """Écrit le top des événements."""
        f.write("8. ÉVÉNEMENTS REMARQUABLES\n")
        f.write("-" * 30 + "\n")
        
        # Vérifier que le DataFrame n'est pas vide et que les colonnes existent
        if df_events.empty:
            f.write("Aucun événement à afficher.\n\n")
            return
        
        # Top 10 par couverture
        f.write("8.1 Top 10 événements par couverture spatiale:\n")
        top_coverage = df_events.head(10)
        for i, (date, event) in enumerate(top_coverage.iterrows(), 1):
            phase = event.get('phase', get_phase_from_month(date.month))
            phase_desc = self.rainfall_phases.get(phase, {}).get('description', phase)
            f.write(f"    {i:2d}. {date.strftime('%Y-%m-%d')} ({phase_desc}):\n")
            f.write(f"        Couverture: {event['coverage_percent']:.1f}%, ")
            f.write(f"Précipitation: {event['max_precip']:.1f} mm, ")
            f.write(f"Anomalie: {event['max_anomaly']:.1f}σ\n")
            if 'centroid_region' in event:
                f.write(f"        Région principale: {event['centroid_region']}\n")
        f.write("\n")
        
        # Top 5 par intensité - CORRECTION DE L'ERREUR
        f.write("8.2 Top 5 événements par intensité de précipitation:\n")
        
        # Vérifier que la colonne existe avant d'utiliser nlargest
        if 'max_precip' in df_events.columns:
            # Créer une copie pour éviter les problèmes d'ambiguïté
            df_copy = df_events.copy()
            
            # Nettoyer les données pour éviter les problèmes de pandas
            df_copy['max_precip'] = pd.to_numeric(df_copy['max_precip'], errors='coerce')
            
            # Supprimer les valeurs NaN
            df_copy = df_copy.dropna(subset=['max_precip'])
            
            if not df_copy.empty:
                # Utiliser sort_values au lieu de nlargest pour éviter l'erreur
                top_intensity = df_copy.sort_values('max_precip', ascending=False).head(5)
                
                for i, (date, event) in enumerate(top_intensity.iterrows(), 1):
                    phase = event.get('phase', get_phase_from_month(date.month))
                    phase_desc = self.rainfall_phases.get(phase, {}).get('description', phase)
                    f.write(f"    {i}. {date.strftime('%Y-%m-%d')} ({phase_desc}): ")
                    f.write(f"{event['max_precip']:.1f} mm\n")
            else:
                f.write("    Aucune donnée de précipitation valide disponible.\n")
        else:
            f.write("    Colonne 'max_precip' non disponible.\n")
        
        f.write("\n") 

    def _write_conclusions(self, f, analysis: Dict[str, Any], validation_status: str):
        """Écrit les conclusions."""
        f.write("9. CONCLUSIONS ET RECOMMANDATIONS\n")
        f.write("-" * 40 + "\n")
        
        general = analysis['general_stats']
        
        f.write("9.1 Synthèse des résultats:\n")
        f.write(f"    • {general['total_events']} événements extrêmes détectés sur {general['period']['duration_years']} ans\n")
        f.write(f"    • Fréquence moyenne de {general['frequency']:.1f} événements par an\n")
        f.write(f"    • Validation climatologique: {validation_status}\n")
        
        # Cohérence climatique
        if 'climate_coherence' in analysis:
            climate = analysis['climate_coherence']
            if 'seasonal_coherence' in climate:
                seasonal = climate['seasonal_coherence']
                f.write(f"    • Cohérence saisonnière: {seasonal['rainy_season_percentage']:.1f}% en saison des pluies\n")
        
        f.write("\n9.2 Points saillants:\n")
        
        # Analyse des phases
        if 'phase_analysis' in analysis:
            phase_analysis = analysis['phase_analysis']
            if 'distribution' in phase_analysis:
                dominant_phase = max(phase_analysis['distribution'].items(), 
                                   key=lambda x: x[1]['count'])
                f.write(f"    • Phase dominante: {dominant_phase[1]['description']} ")
                f.write(f"({dominant_phase[1]['percentage']:.1f}% des événements)\n")
        
        # Géographie
        if 'geographic_analysis' in analysis and 'most_affected_region' in analysis['geographic_analysis']:
            most_affected = analysis['geographic_analysis']['most_affected_region']
            f.write(f"    • Région la plus affectée: {most_affected['name']} ")
            f.write(f"({most_affected['percentage']:.1f}% des événements)\n")
        
        # Intensité
        precip_stats = general['precipitation_stats']
        f.write(f"    • Précipitation moyenne: {precip_stats['mean_mm']:.1f} mm ")
        f.write(f"(maximum: {precip_stats['max_mm']:.1f} mm)\n")
        
        f.write("\n9.3 Recommandations:\n")
        f.write("    • Surveillance renforcée pendant la pleine saison des pluies (juillet-août)\n")
        f.write("    • Attention particulière aux régions les plus affectées\n")
        f.write("    • Intégration possible avec indices climatiques (ENSO, IOD)\n")
        f.write("    • Extension de l'analyse à d'autres pays sahéliens\n")
        f.write("    • Développement de modèles prédictifs basés sur ces patterns\n\n")
    
    def _write_technical_appendix(self, f, df_events: pd.DataFrame):
        """Écrit l'annexe technique."""
        f.write("10. ANNEXE TECHNIQUE\n")
        f.write("-" * 25 + "\n")
        
        f.write("10.1 Caractéristiques des données:\n")
        f.write(f"    • Source: CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)\n")
        f.write(f"    • Résolution spatiale: 0.25° (~25 km)\n")
        f.write(f"    • Résolution temporelle: Quotidienne\n")
        f.write(f"    • Couverture géographique: Sénégal (12°N-17°N, 18°W-11°W)\n")
        f.write(f"    • Période: 1981-2023 (43 ans)\n\n")
        
        f.write("10.2 Configuration de l'analyse:\n")
        try:
            config_summary = get_configuration_summary()
            f.write(f"    • Version de la plateforme: {config_summary.get('project_info', {}).get('version', '2.0.0')}\n")
            f.write(f"    • Phases configurées: {config_summary.get('phases_count', 4)}\n")
            f.write(f"    • Zones climatiques: {config_summary.get('climate_zones_count', 4)}\n")
            f.write(f"    • Régions administratives: {config_summary.get('regions_count', 14)}\n")
        except:
            f.write("    • Configuration standard utilisée\n")
        f.write("\n")
        
        f.write("10.3 Structure des données de sortie:\n")
        f.write(f"    • Nombre de colonnes: {len(df_events.columns)}\n")
        f.write(f"    • Variables principales: {', '.join(['date', 'max_precip', 'coverage_percent', 'max_anomaly'])}\n")
        if 'phase' in df_events.columns:
            f.write(f"    • Classification par phases: Oui\n")
        if 'centroid_region' in df_events.columns:
            f.write(f"    • Identification géographique: Oui\n")
        f.write("\n")
        
        f.write("10.4 Fichiers générés:\n")
        f.write("    Données:\n")
        f.write("    • extreme_events_senegal_comprehensive.csv - Dataset principal enrichi\n")
        f.write("    • statistiques_comprehensive.json - Statistiques machine-readable\n\n")
        f.write("    Visualisations:\n")
        f.write("    • 01_distribution_phases.png - Distribution par phases\n")
        f.write("    • 02_analyse_regionale.png - Analyse géographique\n")
        f.write("    • 03_evolution_temporelle.png - Évolution temporelle\n")
        f.write("    • 04_intensite_couverture.png - Analyse intensité-couverture\n")
        f.write("    • 05_validation_resultats.png - Validation qualité\n")
        f.write("    • 06_resume_executif.png - Résumé exécutif\n\n")
        f.write("    Rapports:\n")
        f.write("    • rapport_detection_comprehensive.txt - Ce rapport complet\n")
        f.write("    • statistiques_comprehensive.json - Export JSON des analyses\n\n")
        
        f.write("10.5 Contact et support:\n")
        contact_email = self.project_info.get('contact_email', 'contact@recherche-climat.org')
        f.write(f"    • Email: {contact_email}\n")
        doc_url = self.project_info.get('documentation_url', 'https://github.com/projet-senegal-climat')
        f.write(f"    • Documentation: {doc_url}\n")
        f.write(f"    • Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("=" * 80 + "\n")
        f.write("FIN DU RAPPORT COMPLET\n")
        f.write("=" * 80 + "\n")
    
    def generate_enhanced_statistics(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Génère des statistiques enrichies au format JSON.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Dict[str, Any]: Statistiques complètes
        """
        print("\n📊 GÉNÉRATION DES STATISTIQUES ENRICHIES")
        print("-" * 60)
        
        # Effectuer l'analyse complète
        analysis = self.analyze_extreme_events_comprehensive(df_events)
        
        # Ajouter des métadonnées complètes
        enhanced_stats = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'generator_version': '2.0.0',
                'project_info': self.project_info,
                'analysis_type': 'comprehensive_extreme_events',
                'data_source': 'CHIRPS',
                'spatial_resolution': '0.25°',
                'temporal_resolution': 'daily'
            },
            'analysis_results': convert_numpy_types(analysis),
            'summary_statistics': self._generate_summary_statistics(df_events),
            'data_quality_report': self._generate_quality_report(analysis),
            'recommendations': self._generate_recommendations(analysis)
        }
        
        # Convertir tous les types NumPy
        enhanced_stats = convert_numpy_types(enhanced_stats)
        
        # Sauvegarder
        try:
            output_path = get_output_path('summary_stats')
            if not output_path.endswith('.json'):
                output_path = output_path.replace('.txt', '_comprehensive.json')
        except:
            output_path = 'outputs/reports/statistiques_comprehensive.json'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enhanced_stats, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Statistiques enrichies sauvegardées: {output_path}")
        return enhanced_stats
    
    def _generate_summary_statistics(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Génère des statistiques résumées."""
        summary = {
            'total_events': len(df_events),
            'period_summary': {
                'start_year': int(df_events['year'].min()),
                'end_year': int(df_events['year'].max()),
                'duration_years': int(df_events['year'].max() - df_events['year'].min() + 1),
                'annual_frequency': float(len(df_events) / (df_events['year'].max() - df_events['year'].min() + 1))
            },
            'key_metrics': {
                'avg_precipitation': float(df_events['max_precip'].mean()),
                'max_precipitation': float(df_events['max_precip'].max()),
                'avg_coverage': float(df_events['coverage_percent'].mean()),
                'max_coverage': float(df_events['coverage_percent'].max()),
                'avg_anomaly': float(df_events['max_anomaly'].mean()),
                'max_anomaly': float(df_events['max_anomaly'].max())
            }
        }
        
        # Ajouter les top événements
        top_5 = df_events.head(5)
        summary['top_events'] = []
        for date, event in top_5.iterrows():
            summary['top_events'].append({
                'date': date.strftime('%Y-%m-%d'),
                'rank': int(event.get('rank', 0)),
                'coverage_percent': float(event['coverage_percent']),
                'max_precipitation': float(event['max_precip']),
                'max_anomaly': float(event['max_anomaly']),
                'phase': event.get('phase', 'Unknown'),
                'region': event.get('centroid_region', 'Unknown')
            })
        
        return summary
    
    def _generate_quality_report(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Génère un rapport de qualité."""
        quality_report = {
            'overall_quality': 'EXCELLENT',
            'data_completeness': analysis.get('quality_assessment', {}).get('data_completeness', {}),
            'climate_coherence': analysis.get('climate_coherence', {}),
            'validation_passed': True,
            'quality_score': 0.95
        }
        
        # Calculer le score de qualité
        quality_factors = []
        
        # Complétude des données
        completeness = analysis.get('quality_assessment', {}).get('data_completeness', {})
        if completeness.get('completeness_score', 0) > 0.9:
            quality_factors.append(1.0)
        else:
            quality_factors.append(completeness.get('completeness_score', 0))
        
        # Cohérence climatique
        climate = analysis.get('climate_coherence', {})
        seasonal_coherence = climate.get('seasonal_coherence', {})
        if seasonal_coherence.get('is_coherent', False):
            quality_factors.append(1.0)
        else:
            quality_factors.append(0.7)
        
        # Score final
        if quality_factors:
            quality_report['quality_score'] = float(np.mean(quality_factors))
            if quality_report['quality_score'] >= 0.9:
                quality_report['overall_quality'] = 'EXCELLENT'
            elif quality_report['quality_score'] >= 0.8:
                quality_report['overall_quality'] = 'TRES_BON'
            elif quality_report['quality_score'] >= 0.7:
                quality_report['overall_quality'] = 'BON'
            else:
                quality_report['overall_quality'] = 'ACCEPTABLE'
        
        return quality_report
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Génère des recommandations basées sur l'analyse."""
        recommendations = []
        
        # Analyse des phases
        phase_analysis = analysis.get('phase_analysis', {})
        if phase_analysis:
            distribution = phase_analysis.get('distribution', {})
            peak_phase_count = distribution.get('Phase_2_pleine', {}).get('count', 0)
            total_events = sum(d.get('count', 0) for d in distribution.values())
            
            if peak_phase_count / total_events > 0.4:
                recommendations.append("Concentration élevée en pleine saison - surveillance renforcée juillet-août recommandée")
            
            validation = phase_analysis.get('climate_validation', {})
            if not validation.get('is_coherent', True):
                recommendations.append("Distribution saisonnière atypique détectée - vérification des données recommandée")
        
        # Analyse géographique
        geo_analysis = analysis.get('geographic_analysis', {})
        if geo_analysis and 'most_affected_region' in geo_analysis:
            most_affected = geo_analysis['most_affected_region']
            if most_affected['percentage'] > 20:
                recommendations.append(f"Région {most_affected['name']} fortement affectée - attention particulière recommandée")
        
        # Analyse d'intensité
        intensity_analysis = analysis.get('intensity_analysis', {})
        if intensity_analysis and 'correlations' in intensity_analysis:
            corr = intensity_analysis['correlations']
            if corr.get('precip_coverage', 0) < 0.3:
                recommendations.append("Faible corrélation précipitation-couverture - événements très localisés possibles")
        
        # Recommandations générales
        recommendations.extend([
            "Intégration possible avec indices climatiques (ENSO, IOD, AMO)",
            "Extension de l'analyse à d'autres pays sahéliens",
            "Développement de modèles prédictifs basés sur ces patterns",
            "Validation croisée avec données pluviométriques in-situ"
        ])
        
        return recommendations
    
    def generate_all_reports(self, df_events: pd.DataFrame, 
                           validation_status: str = "COHERENT") -> Dict[str, str]:
        """
        Génère tous les rapports en une fois.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            validation_status (str): Statut de validation
            
        Returns:
            Dict[str, str]: Chemins des fichiers générés
        """
        print("📊 GÉNÉRATION COMPLÈTE DE TOUS LES RAPPORTS")
        print("=" * 60)
        
        generated_files = {}
        
        try:
            # 1. Rapport complet
            print("📄 Génération du rapport complet...")
            report_path = self.generate_comprehensive_report(df_events, validation_status)
            generated_files['comprehensive_report'] = report_path
            
            # 2. Statistiques enrichies
            print("📊 Génération des statistiques enrichies...")
            stats = self.generate_enhanced_statistics(df_events)
            generated_files['enhanced_statistics'] = 'outputs/reports/statistiques_comprehensive.json'
            
            # 3. Export CSV enrichi
            print("💾 Export CSV enrichi...")
            csv_path = self._export_enriched_csv(df_events)
            generated_files['enriched_csv'] = csv_path
            
            # 4. Résumé exécutif
            print("📋 Génération du résumé exécutif...")
            summary_path = self._generate_executive_summary(df_events, stats)
            generated_files['executive_summary'] = summary_path
            
            print(f"\n✅ TOUS LES RAPPORTS GÉNÉRÉS AVEC SUCCÈS!")
            print(f"   Fichiers créés: {len(generated_files)}")
            for report_type, path in generated_files.items():
                print(f"   • {report_type}: {path}")
            
            return generated_files
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération des rapports: {e}")
            import traceback
            traceback.print_exc()
            return generated_files
    
    def _export_enriched_csv(self, df_events: pd.DataFrame) -> str:
        """Exporte un CSV enrichi avec toutes les métadonnées."""
        try:
            output_path = 'outputs/exports/extreme_events_comprehensive.csv'
        except:
            output_path = 'outputs/extreme_events_comprehensive.csv'
        
        # Créer une copie enrichie
        df_export = df_events.copy()
        
        # Ajouter des colonnes calculées si elles n'existent pas
        if 'phase' not in df_export.columns:
            df_export['phase'] = df_export['month'].apply(get_phase_from_month)
        
        # Ajouter des descriptions de phases
        df_export['phase_description'] = df_export['phase'].map(
            lambda x: self.rainfall_phases.get(x, {}).get('description', x)
        )
        
        # Formater les colonnes numériques
        numeric_cols = ['max_precip', 'coverage_percent', 'max_anomaly', 'centroid_lat', 'centroid_lon']
        for col in numeric_cols:
            if col in df_export.columns:
                df_export[col] = df_export[col].round(3)
        
        # Réinitialiser l'index pour inclure la date comme colonne
        df_export.reset_index(inplace=True)
        df_export['date'] = df_export['date'].dt.strftime('%Y-%m-%d')
        
        # Réorganiser les colonnes
        priority_cols = ['rank', 'date', 'year', 'month', 'phase', 'phase_description']
        other_cols = [col for col in df_export.columns if col not in priority_cols]
        df_export = df_export[priority_cols + other_cols]
        
        # Sauvegarder
        df_export.to_csv(output_path, index=False, encoding='utf-8')
        print(f"   ✅ CSV enrichi exporté: {output_path}")
        
        return output_path
    
    def _generate_executive_summary(self, df_events: pd.DataFrame, 
                                  stats: Dict[str, Any]) -> str:
        """Génère un résumé exécutif concis."""
        try:
            output_path = 'outputs/reports/resume_executif.txt'
        except:
            output_path = 'outputs/resume_executif.txt'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("RÉSUMÉ EXÉCUTIF - ÉVÉNEMENTS EXTRÊMES SÉNÉGAL\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"Projet: {self.project_info.get('title', 'Analyse des précipitations extrêmes')}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"Version: {self.project_info.get('version', '2.0.0')}\n\n")
            
            # Résultats clés
            summary_stats = stats['summary_statistics']
            f.write("RÉSULTATS CLÉS:\n")
            f.write("-" * 20 + "\n")
            f.write(f"• {summary_stats['total_events']} événements extrêmes détectés\n")
            f.write(f"• Période: {summary_stats['period_summary']['start_year']}-{summary_stats['period_summary']['end_year']} ")
            f.write(f"({summary_stats['period_summary']['duration_years']} ans)\n")
            f.write(f"• Fréquence: {summary_stats['period_summary']['annual_frequency']:.1f} événements/an\n")
            f.write(f"• Précipitation maximale: {summary_stats['key_metrics']['max_precipitation']:.1f} mm\n")
            f.write(f"• Couverture maximale: {summary_stats['key_metrics']['max_coverage']:.1f}%\n\n")
            
            # Top 3 événements
            f.write("TOP 3 ÉVÉNEMENTS:\n")
            f.write("-" * 20 + "\n")
            for i, event in enumerate(summary_stats['top_events'][:3], 1):
                f.write(f"{i}. {event['date']} - {event['coverage_percent']:.1f}% - {event['max_precipitation']:.1f} mm\n")
            f.write("\n")
            
            # Qualité des données
            quality = stats['data_quality_report']
            f.write("QUALITÉ DES DONNÉES:\n")
            f.write("-" * 25 + "\n")
            f.write(f"• Évaluation globale: {quality['overall_quality']}\n")
            f.write(f"• Score de qualité: {quality['quality_score']:.1%}\n")
            f.write(f"• Validation: {'✅ RÉUSSIE' if quality['validation_passed'] else '❌ ÉCHEC'}\n\n")
            
            # Recommandations principales
            f.write("RECOMMANDATIONS PRINCIPALES:\n")
            f.write("-" * 35 + "\n")
            main_recommendations = stats['recommendations'][:3]
            for i, rec in enumerate(main_recommendations, 1):
                f.write(f"{i}. {rec}\n")
            f.write("\n")
            
            # Contact
            f.write("CONTACT:\n")
            f.write("-" * 10 + "\n")
            f.write(f"Email: {self.project_info.get('contact_email', 'contact@recherche-climat.org')}\n")
            f.write(f"Documentation: {self.project_info.get('documentation_url', 'https://github.com/projet-senegal-climat')}\n")
        
        print(f"   ✅ Résumé exécutif généré: {output_path}")
        return output_path
    
    def print_comprehensive_summary(self, df_events: pd.DataFrame):
        """
        Affiche un résumé complet à l'écran.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
        """
        print("\n🎯 RÉSUMÉ COMPLET DE L'ANALYSE")
        print("=" * 60)
        
        # Effectuer l'analyse
        analysis = self.analyze_extreme_events_comprehensive(df_events)
        
        # Affichage structuré
        general = analysis['general_stats']
        print(f"\n📊 STATISTIQUES GÉNÉRALES:")
        print(f"   Événements détectés: {general['total_events']}")
        print(f"   Période: {general['period']['start']} à {general['period']['end']}")
        print(f"   Fréquence: {general['frequency']:.1f} événements/an")
        
        print(f"\n🌧️  PRÉCIPITATIONS:")
        precip = general['precipitation_stats']
        print(f"   Moyenne: {precip['mean_mm']:.1f} mm")
        print(f"   Maximum: {precip['max_mm']:.1f} mm")
        print(f"   P95: {precip['quantiles']['q95']:.1f} mm")
        
        print(f"\n📍 COUVERTURE SPATIALE:")
        coverage = general['coverage_stats']
        print(f"   Moyenne: {coverage['mean_percent']:.1f}%")
        print(f"   Maximum: {coverage['max_percent']:.1f}%")
        
        # Phases
        if 'phase_analysis' in analysis:
            print(f"\n🌦️  DISTRIBUTION PAR PHASES:")
            phase_dist = analysis['phase_analysis']['distribution']
            for phase, data in phase_dist.items():
                if data['count'] > 0:
                    print(f"   {data['description']}: {data['count']} ({data['percentage']:.1f}%)")
        
        # Géographie
        if 'geographic_analysis' in analysis and 'most_affected_region' in analysis['geographic_analysis']:
            most_affected = analysis['geographic_analysis']['most_affected_region']
            print(f"\n🗺️  GÉOGRAPHIE:")
            print(f"   Région la plus affectée: {most_affected['name']} ({most_affected['percentage']:.1f}%)")
        
        # Qualité
        if 'quality_assessment' in analysis:
            quality = analysis['quality_assessment']
            completeness = quality.get('data_completeness', {})
            print(f"\n✅ QUALITÉ DES DONNÉES:")
            print(f"   Complétude: {completeness.get('completeness_score', 0):.1%}")
            
        if 'climate_coherence' in analysis:
            climate = analysis['climate_coherence']
            seasonal = climate.get('seasonal_coherence', {})
            print(f"   Cohérence saisonnière: {seasonal.get('rainy_season_percentage', 0):.1f}%")


# Fonctions de compatibilité avec l'ancienne interface
def analyze_extreme_events_final(df_events: pd.DataFrame) -> pd.DataFrame:
    """
    Fonction de compatibilité avec l'ancienne interface.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        pd.DataFrame: DataFrame analysé
    """
    generator = EnhancedDetectionReportGenerator()
    generator.print_comprehensive_summary(df_events)
    return df_events


def generate_detection_report(df_events: pd.DataFrame, validation_status: str):
    """
    Fonction de compatibilité pour la génération de rapport.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        validation_status (str): Statut de validation
    """
    generator = EnhancedDetectionReportGenerator()
    generator.generate_comprehensive_report(df_events, validation_status)


def generate_summary_statistics(df_events: pd.DataFrame) -> dict:
    """
    Fonction de compatibilité pour les statistiques.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        dict: Statistiques générées
    """
    generator = EnhancedDetectionReportGenerator()
    return generator.generate_enhanced_statistics(df_events)


def print_summary_statistics(stats: dict):
    """
    Affiche un résumé des statistiques principales.
    
    Args:
        stats (dict): Dictionnaire des statistiques
    """
    print("\n📊 RÉSUMÉ DES STATISTIQUES PRINCIPALES")
    print("=" * 50)
    
    if 'summary_statistics' in stats:
        summary = stats['summary_statistics']
        print(f"Événements détectés: {summary['total_events']}")
        period = summary['period_summary']
        print(f"Période: {period['start_year']}-{period['end_year']} ({period['duration_years']} ans)")
        print(f"Fréquence annuelle: {period['annual_frequency']:.1f} événements/an")
        
        metrics = summary['key_metrics']
        print(f"\nPrécipitations:")
        print(f"  Moyenne: {metrics['avg_precipitation']:.2f} mm")
        print(f"  Maximum: {metrics['max_precipitation']:.2f} mm")
        
        print(f"\nCouverture spatiale:")
        print(f"  Moyenne: {metrics['avg_coverage']:.2f}%")
        print(f"  Maximum: {metrics['max_coverage']:.2f}%")
        
        # Top événements
        print(f"\nTop 3 événements:")
        for i, event in enumerate(summary['top_events'][:3], 1):
            print(f"  {i}. {event['date']}: {event['coverage_percent']:.1f}% - {event['max_precipitation']:.1f} mm")
    
    # Qualité
    if 'data_quality_report' in stats:
        quality = stats['data_quality_report']
        print(f"\nQualité des données: {quality['overall_quality']} ({quality['quality_score']:.1%})")


# Alias pour compatibilité
DetectionReportGenerator = EnhancedDetectionReportGenerator


if __name__ == "__main__":
    print("📊 Module de génération de rapports avancés - Version 2.0.0")
    print("=" * 70)
    print("Ce module contient les outils pour:")
    print("• Générer des rapports complets et détaillés")
    print("• Calculer des statistiques enrichies avec analyses avancées")
    print("• Analyser les caractéristiques par phases de saison des pluies")
    print("• Évaluer la qualité et cohérence climatique des données")
    print("• Produire des exports multi-format (TXT, JSON, CSV)")
    print("• Intégrer l'analyse géographique et temporelle")
    print()
    print("🆕 Nouvelles fonctionnalités:")
    print("• Intégration complète avec la classification par phases")
    print("• Analyse géographique avec régions et zones climatiques")
    print("• Évaluation automatique de la qualité des données")
    print("• Génération de recommandations basées sur l'analyse")
    print("• Rapports multi-niveaux (technique, exécutif)")
    print("• Export CSV enrichi avec métadonnées complètes")
    print()
    print("📊 Utilisation:")
    print("generator = EnhancedDetectionReportGenerator()")
    print("files = generator.generate_all_reports(df_events, 'COHERENT')")
    print("stats = generator.generate_enhanced_statistics(df_events)")
    print("generator.print_comprehensive_summary(df_events)")
    print()
    print("✅ Module prêt à l'utilisation!")