# src/analysis/climatology.py
"""
Module d'analyse climatologique pour les données de précipitations.
Version améliorée avec intégration des nouveaux modules et optimisations.
"""

import numpy as np
from typing import Tuple, Dict, Any, List, Optional
from tqdm import tqdm
import warnings
import sys
from pathlib import Path
from datetime import datetime, timedelta
import gc

# Imports avec gestion d'erreurs robuste
try:
    from ..config.settings import CLIMATOLOGY_PARAMS, NUMERICAL_PARAMS, SENEGAL_BOUNDS
    from ..utils.season_classifier import get_phase_from_month, RAINFALL_PHASES
except ImportError:
    try:
        from src.config.settings import CLIMATOLOGY_PARAMS, NUMERICAL_PARAMS, SENEGAL_BOUNDS
        from src.utils.season_classifier import get_phase_from_month, RAINFALL_PHASES
    except ImportError:
        # Configuration de fallback
        CLIMATOLOGY_PARAMS = {
            'smoothing_window': 15,
            'min_observations': 5,
            'n_days_year': 366,
            'percentiles': [10, 25, 50, 75, 90, 95, 99],
            'reference_period': (1981, 2010),
            'update_frequency': 'daily'
        }
        NUMERICAL_PARAMS = {
            'pos_inf_replacement': 15,
            'neg_inf_replacement': -15,
            'nan_replacement': 0,
            'float_precision': 1e-10,
            'min_valid_ratio': 0.7
        }
        SENEGAL_BOUNDS = {
            'lat_min': 12.0, 'lat_max': 17.0,
            'lon_min': -18.0, 'lon_max': -11.0
        }
        RAINFALL_PHASES = {
            'Phase_1_debut': {'months': [5, 6]},
            'Phase_2_pleine': {'months': [7, 8]},
            'Phase_3_fin': {'months': [9, 10]},
            'Hors_saison': {'months': [11, 12, 1, 2, 3, 4]}
        }
        
        def get_phase_from_month(month):
            if month in [5, 6]: return 'Phase_1_debut'
            elif month in [7, 8]: return 'Phase_2_pleine'
            elif month in [9, 10]: return 'Phase_3_fin'
            else: return 'Hors_saison'

warnings.filterwarnings('ignore')


class EnhancedClimatologyCalculator:
    """
    Calculateur de climatologie avancé avec analyses saisonnières et spatiales.
    """
    
    def __init__(self, reference_period: tuple = None):
        """
        Initialise le calculateur de climatologie.
        
        Args:
            reference_period (tuple, optional): Période de référence (année_début, année_fin)
        """
        self.reference_period = reference_period or CLIMATOLOGY_PARAMS['reference_period']
        self.smoothing_window = CLIMATOLOGY_PARAMS['smoothing_window']
        self.min_observations = CLIMATOLOGY_PARAMS['min_observations']
        self.n_days_year = CLIMATOLOGY_PARAMS['n_days_year']
        self.percentiles = CLIMATOLOGY_PARAMS['percentiles']
        
        # Statistiques calculées
        self.climatology = None
        self.std_dev = None
        self.percentile_values = None
        self.seasonal_statistics = None
        
        print(f"🔧 EnhancedClimatologyCalculator initialisé")
        print(f"   Période de référence: {self.reference_period[0]}-{self.reference_period[1]}")
        print(f"   Fenêtre de lissage: {self.smoothing_window} jours")
        print(f"   Observations minimales: {self.min_observations}")
    
    def calculate_comprehensive_climatology(self, precip_data: np.ndarray, 
                                          dates: List) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Calcule une climatologie complète avec analyses saisonnières.
        
        Args:
            precip_data (np.ndarray): Données de précipitation (temps, lat, lon)
            dates (List): Liste des dates correspondantes
            
        Returns:
            Tuple[np.ndarray, np.ndarray, Dict]: (climatologie, écart_type, statistiques)
        """
        print("\n🔄 CALCUL DE LA CLIMATOLOGIE COMPLÈTE")
        print("=" * 60)
        
        # Filtrer la période de référence si spécifiée
        filtered_data, filtered_dates = self._filter_reference_period(precip_data, dates)
        
        # Calculer la climatologie de base
        print("📊 Calcul de la climatologie quotidienne...")
        climatology, std_dev = self._calculate_daily_climatology_robust(filtered_data, filtered_dates)
        
        # Calculer les percentiles
        print("📈 Calcul des percentiles...")
        percentile_values = self._calculate_percentiles(filtered_data, filtered_dates)
        
        # Analyses saisonnières
        print("🌧️  Analyse saisonnière...")
        seasonal_stats = self._calculate_seasonal_statistics(filtered_data, filtered_dates)
        
        # Analyses spatiales
        print("🗺️  Analyse spatiale...")
        spatial_stats = self._calculate_spatial_statistics(climatology, std_dev)
        
        # Validation de la qualité
        print("🔍 Validation de la qualité...")
        quality_metrics = self._validate_climatology_quality(climatology, std_dev, filtered_dates)
        
        # Stocker les résultats
        self.climatology = climatology
        self.std_dev = std_dev
        self.percentile_values = percentile_values
        self.seasonal_statistics = seasonal_stats
        
        # Statistiques complètes
        comprehensive_stats = {
            'seasonal_statistics': seasonal_stats,
            'spatial_statistics': spatial_stats,
            'percentile_values': percentile_values,
            'quality_metrics': quality_metrics,
            'reference_period': self.reference_period,
            'total_days': len(filtered_dates),
            'data_shape': filtered_data.shape
        }
        
        print("✅ Climatologie complète calculée avec succès")
        
        return climatology, std_dev, comprehensive_stats
    
    def _filter_reference_period(self, precip_data: np.ndarray, 
                               dates: List) -> Tuple[np.ndarray, List]:
        """
        Filtre les données selon la période de référence.
        
        Args:
            precip_data (np.ndarray): Données de précipitation
            dates (List): Liste des dates
            
        Returns:
            Tuple[np.ndarray, List]: (données filtrées, dates filtrées)
        """
        if self.reference_period is None:
            return precip_data, dates
        
        start_year, end_year = self.reference_period
        
        # Indices des dates dans la période de référence
        valid_indices = [
            i for i, date in enumerate(dates) 
            if start_year <= date.year <= end_year
        ]
        
        if not valid_indices:
            print(f"⚠️  Aucune donnée dans la période de référence {start_year}-{end_year}")
            return precip_data, dates
        
        filtered_data = precip_data[valid_indices]
        filtered_dates = [dates[i] for i in valid_indices]
        
        print(f"📅 Période de référence: {start_year}-{end_year}")
        print(f"   Données filtrées: {len(filtered_dates)}/{len(dates)} jours")
        print(f"   Période effective: {filtered_dates[0].strftime('%Y-%m-%d')} à {filtered_dates[-1].strftime('%Y-%m-%d')}")
        
        return filtered_data, filtered_dates
    
    def _calculate_daily_climatology_robust(self, precip_data: np.ndarray, 
                                          dates: List) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calcule la climatologie quotidienne avec gestion robuste des NaN.
        
        Args:
            precip_data (np.ndarray): Données de précipitation (temps, lat, lon)
            dates (List): Liste des dates correspondantes
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: (climatologie_lissée, ecart_type_lissé)
        """
        print("🔄 Calcul de la climatologie quotidienne robuste...")
        
        # Jours de l'année (1-366 pour années bissextiles)
        doy = np.array([d.timetuple().tm_yday for d in dates])
        
        n_days = self.n_days_year
        n_lat, n_lon = precip_data.shape[1], precip_data.shape[2]
        
        # Initialisation
        daily_climatology = np.full((n_days, n_lat, n_lon), np.nan)
        daily_std = np.full((n_days, n_lat, n_lon), np.nan)
        daily_count = np.zeros(n_days, dtype=int)
        
        # Calcul pour chaque jour de l'année
        for day in tqdm(range(1, n_days + 1), desc="Climatologie quotidienne"):
            day_indices = np.where(doy == day)[0]
            daily_count[day-1] = len(day_indices)
            
            if len(day_indices) >= self.min_observations:
                day_data = precip_data[day_indices, :, :]
                
                # Moyenne et écart-type avec gestion robuste des NaN
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    daily_climatology[day-1, :, :] = np.nanmean(day_data, axis=0)
                    daily_std[day-1, :, :] = np.nanstd(day_data, axis=0, ddof=1)
                    
                    # Remplacer les NaN dans l'écart-type par une valeur minimale
                    daily_std[day-1, :, :] = np.where(
                        np.isnan(daily_std[day-1, :, :]) | (daily_std[day-1, :, :] < NUMERICAL_PARAMS['float_precision']),
                        0.1,  # Valeur minimale pour éviter division par 0
                        daily_std[day-1, :, :]
                    )
        
        # Statistiques de validation
        valid_days = np.sum(daily_count >= self.min_observations)
        print(f"   Jours avec données suffisantes: {valid_days}/{n_days}")
        
        # Lissage avec fenêtre glissante
        print("🔄 Application du lissage temporal...")
        smoothed_climatology, smoothed_std = self._apply_temporal_smoothing(
            daily_climatology, daily_std, daily_count
        )
        
        # Validation finale
        self._validate_daily_climatology(smoothed_climatology, smoothed_std)
        
        return smoothed_climatology, smoothed_std
    
    def _apply_temporal_smoothing(self, daily_climatology: np.ndarray, 
                                daily_std: np.ndarray, daily_count: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Applique un lissage temporel avec fenêtre glissante cyclique.
        
        Args:
            daily_climatology (np.ndarray): Climatologie quotidienne
            daily_std (np.ndarray): Écarts-types quotidiens
            daily_count (np.ndarray): Nombre d'observations par jour
            
        Returns:
            Tuple[np.ndarray, np.ndarray]: (climatologie lissée, écart-type lissé)
        """
        n_days = self.n_days_year
        smoothed_climatology = np.full_like(daily_climatology, np.nan)
        smoothed_std = np.full_like(daily_std, np.nan)
        
        half_window = self.smoothing_window // 2
        
        for day in tqdm(range(n_days), desc="Lissage temporel"):
            # Fenêtre cyclique (gérer début/fin d'année)
            window_indices = []
            for i in range(-half_window, half_window + 1):
                idx = (day + i) % n_days
                window_indices.append(idx)
            
            # Sélectionner les données de la fenêtre
            window_clim = daily_climatology[window_indices, :, :]
            window_std = daily_std[window_indices, :, :]
            window_counts = daily_count[window_indices]
            
            # Pondération par le nombre d'observations
            weights = np.where(window_counts >= self.min_observations, window_counts, 0)
            total_weight = np.sum(weights)
            
            if total_weight > 0:
                # Moyennes pondérées
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    
                    # Climatologie lissée
                    weighted_clim = np.zeros_like(window_clim[0])
                    weighted_std = np.zeros_like(window_std[0])
                    
                    for i, weight in enumerate(weights):
                        if weight > 0:
                            weighted_clim += weight * np.nan_to_num(window_clim[i])
                            weighted_std += weight * np.nan_to_num(window_std[i])
                    
                    smoothed_climatology[day, :, :] = weighted_clim / total_weight
                    smoothed_std[day, :, :] = weighted_std / total_weight
            else:
                # Pas assez de données, utiliser la moyenne simple
                smoothed_climatology[day, :, :] = np.nanmean(window_clim, axis=0)
                smoothed_std[day, :, :] = np.nanmean(window_std, axis=0)
        
        return smoothed_climatology, smoothed_std
    
    def _calculate_percentiles(self, precip_data: np.ndarray, dates: List) -> Dict[str, np.ndarray]:
        """
        Calcule les percentiles pour chaque jour de l'année.
        
        Args:
            precip_data (np.ndarray): Données de précipitation
            dates (List): Liste des dates
            
        Returns:
            Dict[str, np.ndarray]: Percentiles par jour de l'année
        """
        doy = np.array([d.timetuple().tm_yday for d in dates])
        n_days = self.n_days_year
        n_lat, n_lon = precip_data.shape[1], precip_data.shape[2]
        
        # Dictionnaire pour stocker les percentiles
        percentile_dict = {}
        for p in self.percentiles:
            percentile_dict[f'p{p}'] = np.full((n_days, n_lat, n_lon), np.nan)
        
        # Calcul pour chaque jour de l'année
        for day in tqdm(range(1, n_days + 1), desc="Calcul percentiles"):
            day_indices = np.where(doy == day)[0]
            
            if len(day_indices) >= self.min_observations:
                day_data = precip_data[day_indices, :, :]
                
                # Calcul des percentiles
                for p in self.percentiles:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", category=RuntimeWarning)
                        percentile_dict[f'p{p}'][day-1, :, :] = np.nanpercentile(
                            day_data, p, axis=0
                        )
        
        return percentile_dict
    
    def _calculate_seasonal_statistics(self, precip_data: np.ndarray, dates: List) -> Dict[str, Any]:
        """
        Calcule les statistiques saisonnières par phases.
        
        Args:
            precip_data (np.ndarray): Données de précipitation
            dates (List): Liste des dates
            
        Returns:
            Dict[str, Any]: Statistiques saisonnières
        """
        seasonal_stats = {}
        
        # Grouper par phases
        for phase_name, phase_info in RAINFALL_PHASES.items():
            phase_months = phase_info['months']
            
            # Filtrer les données de cette phase
            phase_indices = [
                i for i, date in enumerate(dates) 
                if date.month in phase_months
            ]
            
            if phase_indices:
                phase_data = precip_data[phase_indices]
                
                # Calculer les statistiques
                seasonal_stats[phase_name] = {
                    'n_days': len(phase_indices),
                    'mean': float(np.nanmean(phase_data)),
                    'std': float(np.nanstd(phase_data)),
                    'min': float(np.nanmin(phase_data)),
                    'max': float(np.nanmax(phase_data)),
                    'median': float(np.nanmedian(phase_data)),
                    'p90': float(np.nanpercentile(phase_data, 90)),
                    'p95': float(np.nanpercentile(phase_data, 95)),
                    'p99': float(np.nanpercentile(phase_data, 99)),
                    'months': phase_months,
                    'description': phase_info.get('description', '')
                }
        
        return seasonal_stats
    
    def _calculate_spatial_statistics(self, climatology: np.ndarray, 
                                    std_dev: np.ndarray) -> Dict[str, Any]:
        """
        Calcule les statistiques spatiales de la climatologie.
        
        Args:
            climatology (np.ndarray): Climatologie quotidienne
            std_dev (np.ndarray): Écarts-types quotidiens
            
        Returns:
            Dict[str, Any]: Statistiques spatiales
        """
        spatial_stats = {
            'climatology': {
                'mean': float(np.nanmean(climatology)),
                'std': float(np.nanstd(climatology)),
                'min': float(np.nanmin(climatology)),
                'max': float(np.nanmax(climatology)),
                'median': float(np.nanmedian(climatology))
            },
            'variability': {
                'mean': float(np.nanmean(std_dev)),
                'std': float(np.nanstd(std_dev)),
                'min': float(np.nanmin(std_dev)),
                'max': float(np.nanmax(std_dev)),
                'median': float(np.nanmedian(std_dev))
            },
            'coefficient_of_variation': float(np.nanmean(std_dev) / np.nanmean(climatology)) if np.nanmean(climatology) > 0 else 0,
            'valid_ratio': float(np.sum(~np.isnan(climatology)) / climatology.size)
        }
        
        return spatial_stats
    
    def _validate_daily_climatology(self, climatology: np.ndarray, std_dev: np.ndarray):
        """
        Valide la qualité de la climatologie quotidienne.
        
        Args:
            climatology (np.ndarray): Climatologie quotidienne
            std_dev (np.ndarray): Écarts-types quotidiens
        """
        # Vérifications de base
        valid_clim = ~np.isnan(climatology).all(axis=(1, 2))
        valid_std = ~np.isnan(std_dev).all(axis=(1, 2))
        
        print(f"   Jours valides (climatologie): {valid_clim.sum()}/{self.n_days_year}")
        print(f"   Jours valides (écart-type): {valid_std.sum()}/{self.n_days_year}")
        
        # Statistiques générales
        print(f"   Précipitation climatologique moyenne: {np.nanmean(climatology):.2f} mm")
        print(f"   Variabilité moyenne: {np.nanmean(std_dev):.2f} mm")
        print(f"   Coefficient de variation: {np.nanmean(std_dev)/np.nanmean(climatology):.2f}")
        
        # Vérifications de cohérence
        if valid_clim.sum() < self.n_days_year * 0.8:
            print("   ⚠️  Attention: Moins de 80% des jours ont une climatologie valide")
        
        if np.nanmean(climatology) < 0.1:
            print("   ⚠️  Attention: Climatologie très faible")
        
        if np.nanmean(std_dev) > np.nanmean(climatology):
            print("   ⚠️  Attention: Variabilité supérieure à la moyenne")
    
    def _validate_climatology_quality(self, climatology: np.ndarray, std_dev: np.ndarray, 
                                    dates: List) -> Dict[str, Any]:
        """
        Évalue la qualité de la climatologie calculée.
        
        Args:
            climatology (np.ndarray): Climatologie quotidienne
            std_dev (np.ndarray): Écarts-types quotidiens
            dates (List): Liste des dates
            
        Returns:
            Dict[str, Any]: Métriques de qualité
        """
        quality_metrics = {
            'data_coverage': {
                'total_days': len(dates),
                'valid_climatology_days': np.sum(~np.isnan(climatology).all(axis=(1, 2))),
                'valid_std_days': np.sum(~np.isnan(std_dev).all(axis=(1, 2))),
                'coverage_ratio': np.sum(~np.isnan(climatology)) / climatology.size
            },
            'temporal_consistency': {
                'years_covered': dates[-1].year - dates[0].year + 1,
                'period_start': dates[0].strftime('%Y-%m-%d'),
                'period_end': dates[-1].strftime('%Y-%m-%d'),
                'reference_period_used': self.reference_period
            },
            'statistical_quality': {
                'mean_climatology': float(np.nanmean(climatology)),
                'mean_variability': float(np.nanmean(std_dev)),
                'coefficient_of_variation': float(np.nanmean(std_dev) / np.nanmean(climatology)) if np.nanmean(climatology) > 0 else 0,
                'min_observations_met': self.min_observations,
                'smoothing_applied': self.smoothing_window
            }
        }
        
        # Score de qualité global
        coverage_score = min(quality_metrics['data_coverage']['coverage_ratio'] * 100, 100)
        temporal_score = min(quality_metrics['temporal_consistency']['years_covered'] / 30 * 100, 100)  # 30 ans = référence
        
        quality_metrics['overall_quality'] = {
            'coverage_score': coverage_score,
            'temporal_score': temporal_score,
            'overall_score': (coverage_score + temporal_score) / 2,
            'quality_level': self._get_quality_level((coverage_score + temporal_score) / 2)
        }
        
        return quality_metrics
    
    def _get_quality_level(self, score: float) -> str:
        """
        Détermine le niveau de qualité basé sur le score.
        
        Args:
            score (float): Score de qualité (0-100)
            
        Returns:
            str: Niveau de qualité
        """
        if score >= 90:
            return "EXCELLENT"
        elif score >= 75:
            return "TRES_BON"
        elif score >= 60:
            return "BON"
        elif score >= 40:
            return "ACCEPTABLE"
        else:
            return "INSUFFISANT"


def calculate_standardized_anomalies_robust(precip_data: np.ndarray, dates: List, 
                                          climatology: np.ndarray, std_dev: np.ndarray) -> np.ndarray:
    """
    Calcule les anomalies standardisées avec gestion robuste des NaN.
    Version améliorée avec validation et optimisations.
    
    Args:
        precip_data (np.ndarray): Données de précipitation
        dates (List): Liste des dates
        climatology (np.ndarray): Climatologie quotidienne
        std_dev (np.ndarray): Écarts-types quotidiens
        
    Returns:
        np.ndarray: Anomalies standardisées
    """
    print("\n🔄 CALCUL DES ANOMALIES STANDARDISÉES (AMÉLIORÉ)")
    print("-" * 60)
    
    n_time, n_lat, n_lon = precip_data.shape
    standardized_anomalies = np.full_like(precip_data, np.nan)
    
    # Convertir les dates en jour de l'année (0-365 indexing)
    doy_idx = np.array([d.timetuple().tm_yday - 1 for d in dates])
    
    # Statistiques de traitement
    total_pixels = n_time * n_lat * n_lon
    processed_pixels = 0
    valid_pixels = 0
    
    print("🔄 Calcul des anomalies avec validation avancée...")
    
    for i in tqdm(range(len(dates)), desc="Anomalies standardisées"):
        day_idx = doy_idx[i]
        
        # Vérifier que l'index est valide
        if day_idx >= climatology.shape[0]:
            continue
        
        # Données du jour
        clim_day = climatology[day_idx, :, :]
        std_day = std_dev[day_idx, :, :]
        day_precip = precip_data[i, :, :]
        
        # Masque des valeurs valides avec critères stricts
        valid_mask = (
            (std_day > NUMERICAL_PARAMS['float_precision']) &  # Écart-type non nul
            ~np.isnan(std_day) &                               # Écart-type valide
            ~np.isnan(clim_day) &                              # Climatologie valide
            ~np.isnan(day_precip) &                            # Précipitation valide
            (clim_day >= 0) &                                  # Climatologie positive
            (day_precip >= 0)                                  # Précipitation positive
        )
        
        processed_pixels += valid_mask.size
        valid_pixels += valid_mask.sum()
        
        if valid_mask.any():
            # Calcul des anomalies standardisées
            anomalies = (day_precip[valid_mask] - clim_day[valid_mask]) / std_day[valid_mask]
            
            # Vérifier les valeurs infinies ou extrêmes
            finite_mask = np.isfinite(anomalies)
            if finite_mask.any():
                # Appliquer des limites raisonnables
                anomalies = np.clip(anomalies, -20, 20)  # Limiter à ±20σ
                standardized_anomalies[i, valid_mask] = anomalies
    
    # Remplacement final des valeurs problématiques
    standardized_anomalies = np.nan_to_num(
        standardized_anomalies, 
        nan=NUMERICAL_PARAMS['nan_replacement'], 
        posinf=NUMERICAL_PARAMS['pos_inf_replacement'], 
        neginf=NUMERICAL_PARAMS['neg_inf_replacement']
    )
    
    # Validation des résultats
    _validate_anomalies(standardized_anomalies, dates, processed_pixels, valid_pixels)
    
    # Nettoyage mémoire
    gc.collect()
    
    return standardized_anomalies


def _validate_anomalies(anomalies: np.ndarray, dates: List, 
                       processed_pixels: int, valid_pixels: int):
    """
    Valide les anomalies calculées.
    
    Args:
        anomalies (np.ndarray): Anomalies standardisées
        dates (List): Liste des dates
        processed_pixels (int): Nombre de pixels traités
        valid_pixels (int): Nombre de pixels valides
    """
    print(f"✅ Validation des anomalies:")
    print(f"   Pixels traités: {processed_pixels:,}")
    print(f"   Pixels valides: {valid_pixels:,} ({valid_pixels/processed_pixels*100:.1f}%)")
    
    # Statistiques des anomalies
    valid_anomalies = anomalies[~np.isnan(anomalies)]
    if len(valid_anomalies) > 0:
        print(f"   Anomalies valides: {len(valid_anomalies):,}")
        print(f"   Moyenne: {np.mean(valid_anomalies):.3f}σ")
        print(f"   Écart-type: {np.std(valid_anomalies):.3f}σ")
        print(f"   Min: {np.min(valid_anomalies):.1f}σ")
        print(f"   Max: {np.max(valid_anomalies):.1f}σ")
        
        # Vérifier la distribution
        extreme_positive = np.sum(valid_anomalies > 3)
        extreme_negative = np.sum(valid_anomalies < -3)
        total_valid = len(valid_anomalies)
        
        print(f"   Anomalies > +3σ: {extreme_positive:,} ({extreme_positive/total_valid*100:.3f}%)")
        print(f"   Anomalies < -3σ: {extreme_negative:,} ({extreme_negative/total_valid*100:.3f}%)")
        
        # Vérifications de cohérence
        if abs(np.mean(valid_anomalies)) > 0.1:
            print("   ⚠️  Attention: Moyenne des anomalies non centrée sur 0")
        
        if np.std(valid_anomalies) < 0.8 or np.std(valid_anomalies) > 1.2:
            print("   ⚠️  Attention: Écart-type des anomalies éloigné de 1")
        
        if extreme_positive / total_valid > 0.005:  # > 0.5% au lieu de ~0.1%
            print("   ⚠️  Attention: Trop d'anomalies positives extrêmes")
        
        if extreme_negative / total_valid > 0.005:  # > 0.5% au lieu de ~0.1%
            print("   ⚠️  Attention: Trop d'anomalies négatives extrêmes")
    
    # Validation temporelle
    daily_valid = np.sum(~np.isnan(anomalies).all(axis=(1, 2)))
    print(f"   Jours avec anomalies valides: {daily_valid}/{len(dates)} ({daily_valid/len(dates)*100:.1f}%)")


def calculate_daily_climatology_robust(precip_data: np.ndarray, dates: List) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calcule la climatologie quotidienne avec gestion robuste des NaN.
    Version de compatibilité avec l'ancien interface.
    
    Args:
        precip_data (np.ndarray): Données de précipitation (temps, lat, lon)
        dates (List): Liste des dates correspondantes
        
    Returns:
        Tuple[np.ndarray, np.ndarray]: (climatologie_lissée, ecart_type_lissé)
    """
    print("\n🔄 CALCUL DE LA CLIMATOLOGIE QUOTIDIENNE (COMPATIBILITÉ)")
    print("-" * 60)
    
    # Utiliser le calculateur avancé
    calculator = EnhancedClimatologyCalculator()
    climatology, std_dev = calculator._calculate_daily_climatology_robust(precip_data, dates)
    
    return climatology, std_dev


def calculate_climatology_and_anomalies(precip_data: np.ndarray, dates: List) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fonction principale pour calculer climatologie et anomalies.
    Version améliorée avec nouvelles fonctionnalités.
    
    Args:
        precip_data (np.ndarray): Données de précipitation
        dates (List): Liste des dates
        
    Returns:
        Tuple[np.ndarray, np.ndarray, np.ndarray]: (climatologie, écart_type, anomalies)
    """
    print("🔄 CALCUL COMPLET DE LA CLIMATOLOGIE ET DES ANOMALIES")
    print("=" * 70)
    
    # Vérifications initiales
    if precip_data is None or len(dates) == 0:
        raise ValueError("Données de précipitation ou dates manquantes")
    
    if precip_data.shape[0] != len(dates):
        raise ValueError("Nombre de jours incompatible entre données et dates")
    
    print(f"📊 Données d'entrée:")
    print(f"   Shape: {precip_data.shape}")
    print(f"   Période: {dates[0].strftime('%Y-%m-%d')} à {dates[-1].strftime('%Y-%m-%d')}")
    print(f"   Durée: {len(dates)} jours ({len(dates)/365.25:.1f} années)")
    
    # Statistiques de base
    valid_ratio = np.sum(~np.isnan(precip_data)) / precip_data.size
    print(f"   Données valides: {valid_ratio*100:.1f}%")
    
    if valid_ratio < NUMERICAL_PARAMS['min_valid_ratio']:
        print(f"   ⚠️  Attention: Ratio de données valides faible ({valid_ratio*100:.1f}%)")
    
    try:
        # Utiliser le calculateur avancé
        calculator = EnhancedClimatologyCalculator()
        
        # Calculer la climatologie complète
        climatology, std_dev, comprehensive_stats = calculator.calculate_comprehensive_climatology(
            precip_data, dates
        )
        
        # Calculer les anomalies
        anomalies = calculate_standardized_anomalies_robust(
            precip_data, dates, climatology, std_dev
        )
        
        # Afficher les résultats
        _print_comprehensive_results(comprehensive_stats)
        
        print("✅ Calcul terminé avec succès")
        
        return climatology, std_dev, anomalies
        
    except Exception as e:
        print(f"❌ Erreur lors du calcul: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback vers calcul basique
        print("🔄 Tentative avec calcul basique...")
        return _calculate_basic_climatology_fallback(precip_data, dates)


def _calculate_basic_climatology_fallback(precip_data: np.ndarray, dates: List) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calcul basique de climatologie en cas d'échec du calcul avancé.
    
    Args:
        precip_data (np.ndarray): Données de précipitation
        dates (List): Liste des dates
        
    Returns:
        Tuple[np.ndarray, np.ndarray, np.ndarray]: (climatologie, écart_type, anomalies)
    """
    print("⚠️  Utilisation du calcul basique de climatologie")
    
    # Calcul simple par jour de l'année
    doy = np.array([d.timetuple().tm_yday for d in dates])
    
    n_days = 366  # Inclure les années bissextiles
    n_lat, n_lon = precip_data.shape[1], precip_data.shape[2]
    
    # Initialisation
    climatology = np.zeros((n_days, n_lat, n_lon))
    std_dev = np.zeros((n_days, n_lat, n_lon))
    
    # Calcul pour chaque jour
    for day in range(1, n_days + 1):
        day_indices = np.where(doy == day)[0]
        
        if len(day_indices) > 0:
            day_data = precip_data[day_indices, :, :]
            climatology[day-1, :, :] = np.nanmean(day_data, axis=0)
            std_dev[day-1, :, :] = np.nanstd(day_data, axis=0, ddof=1)
    
    # Remplacer les NaN dans std_dev par une valeur minimale
    std_dev = np.where(np.isnan(std_dev) | (std_dev < 0.01), 0.1, std_dev)
    
    # Calcul des anomalies
    anomalies = np.full_like(precip_data, np.nan)
    
    for i, date in enumerate(dates):
        day_idx = date.timetuple().tm_yday - 1
        if day_idx < n_days:
            day_clim = climatology[day_idx, :, :]
            day_std = std_dev[day_idx, :, :]
            
            valid_mask = (day_std > 0.01) & ~np.isnan(day_clim) & ~np.isnan(precip_data[i, :, :])
            anomalies[i, valid_mask] = (precip_data[i, valid_mask] - day_clim[valid_mask]) / day_std[valid_mask]
    
    # Remplacer les valeurs infinies
    anomalies = np.nan_to_num(anomalies, nan=0, posinf=15, neginf=-15)
    
    print("✅ Calcul basique terminé")
    
    return climatology, std_dev, anomalies


def _print_comprehensive_results(comprehensive_stats: Dict[str, Any]):
    """
    Affiche les résultats complets de l'analyse climatologique.
    
    Args:
        comprehensive_stats (Dict[str, Any]): Statistiques complètes
    """
    print("\n📊 RÉSULTATS DE L'ANALYSE CLIMATOLOGIQUE")
    print("-" * 50)
    
    # Qualité générale
    quality = comprehensive_stats.get('quality_metrics', {}).get('overall_quality', {})
    if quality:
        print(f"🎯 Qualité globale: {quality.get('quality_level', 'INCONNU')} ({quality.get('overall_score', 0):.1f}%)")
    
    # Statistiques spatiales
    spatial_stats = comprehensive_stats.get('spatial_statistics', {})
    if spatial_stats:
        clim_stats = spatial_stats.get('climatology', {})
        var_stats = spatial_stats.get('variability', {})
        
        print(f"🌍 Statistiques spatiales:")
        print(f"   Climatologie: {clim_stats.get('mean', 0):.2f} ± {clim_stats.get('std', 0):.2f} mm")
        print(f"   Variabilité: {var_stats.get('mean', 0):.2f} ± {var_stats.get('std', 0):.2f} mm")
        print(f"   Coefficient de variation: {spatial_stats.get('coefficient_of_variation', 0):.2f}")
        print(f"   Données valides: {spatial_stats.get('valid_ratio', 0)*100:.1f}%")
    
    # Statistiques saisonnières
    seasonal_stats = comprehensive_stats.get('seasonal_statistics', {})
    if seasonal_stats:
        print(f"🌧️  Statistiques saisonnières:")
        
        for phase, stats in seasonal_stats.items():
            print(f"   {phase}:")
            print(f"     Moyenne: {stats.get('mean', 0):.2f} mm ({stats.get('n_days', 0)} jours)")
            print(f"     P95: {stats.get('p95', 0):.2f} mm, P99: {stats.get('p99', 0):.2f} mm")
    
    # Informations sur les percentiles
    percentile_values = comprehensive_stats.get('percentile_values', {})
    if percentile_values:
        print(f"📈 Percentiles calculés: {', '.join(percentile_values.keys())}")


class ClimatologyValidator:
    """
    Classe pour valider la qualité des calculs climatologiques.
    """
    
    def __init__(self):
        self.validation_results = {}
    
    def validate_comprehensive(self, climatology: np.ndarray, std_dev: np.ndarray, 
                             anomalies: np.ndarray, dates: List) -> Dict[str, Any]:
        """
        Validation complète des résultats climatologiques.
        
        Args:
            climatology (np.ndarray): Climatologie calculée
            std_dev (np.ndarray): Écarts-types
            anomalies (np.ndarray): Anomalies standardisées
            dates (List): Liste des dates
            
        Returns:
            Dict[str, Any]: Résultats de validation
        """
        print("\n🔍 VALIDATION COMPLÈTE DES RÉSULTATS CLIMATOLOGIQUES")
        print("-" * 60)
        
        validation_results = {
            'climatology_validation': self._validate_climatology(climatology),
            'std_dev_validation': self._validate_std_dev(std_dev),
            'anomalies_validation': self._validate_anomalies_distribution(anomalies),
            'temporal_validation': self._validate_temporal_consistency(dates),
            'overall_score': 0,
            'quality_level': 'UNKNOWN',
            'recommendations': []
        }
        
        # Calculer le score global
        validation_results['overall_score'] = self._calculate_overall_score(validation_results)
        validation_results['quality_level'] = self._determine_quality_level(validation_results['overall_score'])
        validation_results['recommendations'] = self._generate_recommendations(validation_results)
        
        self._print_validation_summary(validation_results)
        
        return validation_results
    
    def _validate_climatology(self, climatology: np.ndarray) -> Dict[str, Any]:
        """Valide la climatologie calculée."""
        valid_ratio = np.sum(~np.isnan(climatology)) / climatology.size
        mean_precip = np.nanmean(climatology)
        
        return {
            'valid_ratio': valid_ratio,
            'mean_precipitation': mean_precip,
            'is_valid': valid_ratio > 0.8 and 0.1 < mean_precip < 50,
            'issues': []
        }
    
    def _validate_std_dev(self, std_dev: np.ndarray) -> Dict[str, Any]:
        """Valide les écarts-types calculés."""
        valid_ratio = np.sum(~np.isnan(std_dev)) / std_dev.size
        mean_std = np.nanmean(std_dev)
        
        return {
            'valid_ratio': valid_ratio,
            'mean_std': mean_std,
            'is_valid': valid_ratio > 0.8 and mean_std > 0.01,
            'issues': []
        }
    
    def _validate_anomalies_distribution(self, anomalies: np.ndarray) -> Dict[str, Any]:
        """Valide la distribution des anomalies."""
        valid_anomalies = anomalies[~np.isnan(anomalies)]
        
        if len(valid_anomalies) == 0:
            return {'is_valid': False, 'issues': ['Aucune anomalie valide']}
        
        mean_anom = np.mean(valid_anomalies)
        std_anom = np.std(valid_anomalies)
        
        return {
            'mean_anomaly': mean_anom,
            'std_anomaly': std_anom,
            'is_valid': abs(mean_anom) < 0.1 and 0.8 < std_anom < 1.2,
            'extreme_positive': np.sum(valid_anomalies > 3) / len(valid_anomalies),
            'extreme_negative': np.sum(valid_anomalies < -3) / len(valid_anomalies),
            'issues': []
        }
    
    def _validate_temporal_consistency(self, dates: List) -> Dict[str, Any]:
        """Valide la cohérence temporelle."""
        if len(dates) < 2:
            return {'is_valid': False, 'issues': ['Pas assez de dates']}
        
        # Vérifier les gaps temporels
        gaps = []
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i-1]).days
            if gap > 1:
                gaps.append(gap)
        
        duration_years = (dates[-1] - dates[0]).days / 365.25
        
        return {
            'duration_years': duration_years,
            'total_days': len(dates),
            'gaps_count': len(gaps),
            'max_gap': max(gaps) if gaps else 0,
            'is_valid': duration_years >= 10 and len(gaps) < len(dates) * 0.05,
            'issues': []
        }
    
    def _calculate_overall_score(self, validation_results: Dict[str, Any]) -> float:
        """Calcule le score global de validation."""
        scores = []
        
        # Score climatologie
        if validation_results['climatology_validation']['is_valid']:
            scores.append(25)
        
        # Score écart-type
        if validation_results['std_dev_validation']['is_valid']:
            scores.append(25)
        
        # Score anomalies
        if validation_results['anomalies_validation']['is_valid']:
            scores.append(25)
        
        # Score temporel
        if validation_results['temporal_validation']['is_valid']:
            scores.append(25)
        
        return sum(scores)
    
    def _determine_quality_level(self, score: float) -> str:
        """Détermine le niveau de qualité."""
        if score >= 90:
            return "EXCELLENT"
        elif score >= 75:
            return "TRES_BON"
        elif score >= 60:
            return "BON"
        elif score >= 40:
            return "ACCEPTABLE"
        else:
            return "INSUFFISANT"
    
    def _generate_recommendations(self, validation_results: Dict[str, Any]) -> List[str]:
        """Génère des recommandations d'amélioration."""
        recommendations = []
        
        # Analyser chaque validation
        for key, result in validation_results.items():
            if isinstance(result, dict) and not result.get('is_valid', True):
                if key == 'climatology_validation':
                    recommendations.append("Améliorer la qualité des données de précipitation")
                elif key == 'std_dev_validation':
                    recommendations.append("Réviser le calcul des écarts-types")
                elif key == 'anomalies_validation':
                    recommendations.append("Vérifier la normalisation des anomalies")
                elif key == 'temporal_validation':
                    recommendations.append("Utiliser une période plus longue ou combler les gaps")
        
        return recommendations
    
    def _print_validation_summary(self, validation_results: Dict[str, Any]):
        """Affiche le résumé de validation."""
        print(f"🎯 Score global: {validation_results['overall_score']:.0f}/100")
        print(f"📊 Niveau de qualité: {validation_results['quality_level']}")
        
        if validation_results['recommendations']:
            print("💡 Recommandations:")
            for rec in validation_results['recommendations']:
                print(f"   • {rec}")


# Fonctions utilitaires pour l'export et la sauvegarde
def export_climatology_data(climatology: np.ndarray, std_dev: np.ndarray, 
                          lats: np.ndarray, lons: np.ndarray, 
                          output_file: str, comprehensive_stats: Dict[str, Any] = None):
    """
    Exporte les données climatologiques vers un fichier.
    
    Args:
        climatology (np.ndarray): Climatologie quotidienne
        std_dev (np.ndarray): Écarts-types quotidiens
        lats (np.ndarray): Latitudes
        lons (np.ndarray): Longitudes
        output_file (str): Fichier de sortie
        comprehensive_stats (Dict[str, Any], optional): Statistiques complètes
    """
    print(f"💾 Export des données climatologiques vers: {output_file}")
    
    # Préparer les métadonnées
    metadata = {
        'created_at': datetime.now().isoformat(),
        'version': '2.0',
        'description': 'Climatologie quotidienne pour le Sénégal',
        'reference_period': CLIMATOLOGY_PARAMS['reference_period'],
        'smoothing_window': CLIMATOLOGY_PARAMS['smoothing_window'],
        'shape': climatology.shape,
        'coordinate_system': 'WGS84'
    }
    
    # Ajouter les statistiques si disponibles
    if comprehensive_stats:
        metadata['statistics'] = comprehensive_stats
    
    # Sauvegarder
    np.savez_compressed(
        output_file,
        climatology=climatology,
        std_dev=std_dev,
        lats=lats,
        lons=lons,
        metadata=metadata
    )
    
    print(f"✅ Export terminé: {output_file}")


if __name__ == "__main__":
    print("🌦️  Module d'analyse climatologique avancé")
    print("=" * 60)
    print("Ce module contient les outils pour:")
    print("• Calculer la climatologie quotidienne lissée")
    print("• Calculer les anomalies standardisées robustes")
    print("• Analyser les statistiques saisonnières par phases")
    print("• Calculer les percentiles climatologiques")
    print("• Valider la qualité des calculs")
    print("• Exporter les résultats")
    print()
    print("🆕 Nouvelles fonctionnalités:")
    print("• EnhancedClimatologyCalculator - Calculs avancés")
    print("• ClimatologyValidator - Validation complète")
    print("• Analyses saisonnières par phases de pluies")
    print("• Statistiques spatiales détaillées")
    print("• Export avec métadonnées complètes")
    print()
    print("📊 Utilisation:")
    print("calculator = EnhancedClimatologyCalculator()")
    print("climatology, std_dev, stats = calculator.calculate_comprehensive_climatology(data, dates)")
    print("anomalies = calculate_standardized_anomalies_robust(data, dates, climatology, std_dev)")
    print()
    print("✅ Module prêt à l'utilisation!")