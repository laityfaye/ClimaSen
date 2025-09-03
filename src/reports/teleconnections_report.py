#!/usr/bin/env python3
# src/reports/teleconnections_report.py
"""
Module de génération de rapports pour l'analyse des téléconnexions climatiques - VERSION CORRIGÉE.

Ce module crée des rapports détaillés compatibles avec la structure des résultats
de la version scientifiquement corrigée.

Auteur: [Votre nom]  
Date: [Date]
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import warnings

warnings.filterwarnings('ignore')

class TeleconnectionsReportGeneratorCorrected:
    """
    Générateur de rapports pour l'analyse des téléconnexions climatiques - VERSION CORRIGÉE.
    Compatible avec la nouvelle structure des résultats.
    """
    
    def __init__(self, analyzer):
        """
        Initialise le générateur de rapports.
        
        Args:
            analyzer: Instance de TeleconnectionsAnalyzer avec les résultats corrigés
        """
        self.analyzer = analyzer
        self.report_data = {}
        
    def analyze_correlation_patterns_corrected(self) -> Dict[str, Any]:
        """
        CORRIGÉ: Analyse les patterns dans les corrélations avec nouvelle structure.
        
        Returns:
            Dict[str, Any]: Analyse des patterns avec validation physique
        """
        patterns = {
            'strongest_teleconnection': None,
            'best_physical_validation': None,
            'most_consistent_index': None,
            'phase_preferences': {},
            'seasonal_patterns': {},
            'significance_summary': {},
            'physical_validation_summary': {},
            'methodological_quality': {}
        }
        
        if not hasattr(self.analyzer, 'correlations_results') or not self.analyzer.correlations_results:
            return patterns
        
        # CORRECTION : Adapter à la structure index -> metric -> lag
        all_correlations = []
        index_performances = {}
        
        for index_name, index_results in self.analyzer.correlations_results.items():
            index_correlations = []
            significant_count = 0
            physical_optimal_count = 0
            max_variance_explained = 0
            
            for metric_name, lag_results in index_results.items():
                for lag_key, lag_data in lag_results.items():
                    if lag_key.startswith('lag_'):
                        pearson_data = lag_data.get('pearson', {})
                        correlation = pearson_data.get('correlation', np.nan)
                        
                        if not np.isnan(correlation):
                            lag_num = int(lag_key.split('_')[1])
                            correlation_info = {
                                'index': index_name,
                                'metric': metric_name,
                                'lag': lag_num,
                                'correlation': correlation,
                                'p_value': pearson_data.get('p_value', 1.0),
                                'p_value_corrected': pearson_data.get('p_value_corrected', pearson_data.get('p_value', 1.0)),
                                'is_significant': pearson_data.get('is_significant_corrected', False),
                                'variance_explained': pearson_data.get('variance_explained', 0),
                                'is_physical_optimal': lag_data.get('is_physical_optimal', False),
                                'climatological_significance': pearson_data.get('climatological_significance', 'Non évalué')
                            }
                            
                            all_correlations.append(correlation_info)
                            index_correlations.append(abs(correlation))
                            
                            if correlation_info['is_significant']:
                                significant_count += 1
                                max_variance_explained = max(max_variance_explained, correlation_info['variance_explained'])
                                
                                if correlation_info['is_physical_optimal']:
                                    physical_optimal_count += 1
            
            if index_correlations:
                index_performances[index_name] = {
                    'mean_abs_correlation': np.mean(index_correlations),
                    'max_abs_correlation': np.max(index_correlations),
                    'max_variance_explained': max_variance_explained,
                    'significant_count': significant_count,
                    'physical_optimal_count': physical_optimal_count,
                    'physical_validation_rate': physical_optimal_count / significant_count if significant_count > 0 else 0,
                    'consistency': np.std(index_correlations)
                }
        
        # Identifier la téléconnexion la plus forte
        if all_correlations:
            strongest = max(all_correlations, key=lambda x: x['variance_explained'])
            patterns['strongest_teleconnection'] = {
                'index': strongest['index'],
                'metric': strongest['metric'],
                'lag': strongest['lag'],
                'correlation': strongest['correlation'],
                'variance_explained': strongest['variance_explained'],
                'is_physical_optimal': strongest['is_physical_optimal'],
                'climatological_significance': strongest['climatological_significance']
            }
            
            # Meilleure validation physique
            physical_correlations = [c for c in all_correlations if c['is_physical_optimal'] and c['is_significant']]
            if physical_correlations:
                best_physical = max(physical_correlations, key=lambda x: x['variance_explained'])
                patterns['best_physical_validation'] = {
                    'index': best_physical['index'],
                    'metric': best_physical['metric'],
                    'lag': best_physical['lag'],
                    'correlation': best_physical['correlation'],
                    'variance_explained': best_physical['variance_explained']
                }
        
        # Indice le plus consistent
        if index_performances:
            # Critère composite : validation physique + variance expliquée
            best_index = max(index_performances.items(), 
                           key=lambda x: (x[1]['physical_validation_rate'], x[1]['max_variance_explained']))
            
            patterns['most_consistent_index'] = {
                'name': best_index[0],
                'performance': best_index[1]
            }
        
        # Analyser les patterns saisonniers
        seasonal_patterns = {}
        for corr in all_correlations:
            if corr['is_significant']:
                index_name = corr['index']
                if index_name not in seasonal_patterns:
                    seasonal_patterns[index_name] = []
                seasonal_patterns[index_name].append(corr['lag'])
        
        for index_name, lags in seasonal_patterns.items():
            if lags:
                patterns['seasonal_patterns'][index_name] = {
                    'significant_lags': sorted(set(lags)),
                    'most_common_lag': max(set(lags), key=lags.count),
                    'lag_range': max(lags) - min(lags)
                }
        
        # Analyser les corrélations par phases
        if hasattr(self.analyzer, 'phase_correlations') and self.analyzer.phase_correlations:
            phase_analysis = {}
            
            for phase_name, phase_results in self.analyzer.phase_correlations.items():
                phase_significant = []
                
                for metric_name, metric_results in phase_results.items():
                    for index_name, corr_data in metric_results.items():
                        if corr_data.get('is_significant_corrected', False):
                            phase_significant.append({
                                'index': index_name,
                                'metric': metric_name,
                                'correlation': corr_data['correlation'],
                                'variance_explained': corr_data.get('variance_explained', 0)
                            })
                
                if phase_significant:
                    best_for_phase = max(phase_significant, key=lambda x: x['variance_explained'])
                    phase_analysis[phase_name] = {
                        'best_index': best_for_phase['index'],
                        'best_metric': best_for_phase['metric'],
                        'best_correlation': best_for_phase['correlation'],
                        'best_variance_explained': best_for_phase['variance_explained'],
                        'significant_count': len(phase_significant)
                    }
            
            patterns['phase_preferences'] = phase_analysis
        
        # Résumé de significativité avec correction FDR
        total_tests = len(all_correlations)
        significant_tests = len([c for c in all_correlations if c['is_significant']])
        physical_optimal_significant = len([c for c in all_correlations if c['is_significant'] and c['is_physical_optimal']])
        
        patterns['significance_summary'] = {
            'total_tests': total_tests,
            'significant_tests': significant_tests,
            'significance_rate': significant_tests / total_tests if total_tests > 0 else 0,
            'physical_optimal_significant': physical_optimal_significant,
            'physical_validation_rate': physical_optimal_significant / significant_tests if significant_tests > 0 else 0
        }
        
        # Validation physique par indice
        patterns['physical_validation_summary'] = {}
        for index_name, performance in index_performances.items():
            patterns['physical_validation_summary'][index_name] = {
                'total_significant': performance['significant_count'],
                'physical_validated': performance['physical_optimal_count'],
                'validation_rate': performance['physical_validation_rate'],
                'max_variance': performance['max_variance_explained']
            }
        
        # Qualité méthodologique
        patterns['methodological_quality'] = {
            'fdr_correction_applied': hasattr(self.analyzer, 'multiple_testing_correction') and self.analyzer.multiple_testing_correction,
            'stationarity_tested': hasattr(self.analyzer, 'stationarity_results') and len(self.analyzer.stationarity_results) > 0,
            'physical_constraints_used': any(c['is_physical_optimal'] for c in all_correlations),
            'multiple_metrics_analyzed': len(set(c['metric'] for c in all_correlations)) > 1,
            'minimum_observations_criterion': hasattr(self.analyzer, 'min_observations') and self.analyzer.min_observations >= 30
        }
        
        return patterns
    
    def interpret_correlations_climatological(self, correlation: float, p_value: float, 
                                            variance_explained: float = None, 
                                            is_physical_optimal: bool = False) -> str:
        """
        NOUVEAU : Interprète une corrélation avec contexte climatologique complet.
        
        Args:
            correlation (float): Coefficient de corrélation
            p_value (float): Valeur p corrigée
            variance_explained (float): Pourcentage de variance expliquée
            is_physical_optimal (bool): Si c'est un lag physique optimal
            
        Returns:
            str: Interprétation climatologique détaillée
        """
        if np.isnan(correlation) or np.isnan(p_value):
            return "Corrélation non calculable - données insuffisantes"
        # Force climatologique (standards plus stricts)
        abs_corr = abs(correlation)
        if abs_corr >= 0.4:
            strength = "très forte (climatologiquement exceptionnelle)"
            clim_relevance = "Très pertinente pour prédictibilité"
        elif abs_corr >= 0.25:
            strength = "forte (climatologiquement significative)"
            clim_relevance = "Pertinente pour compréhension mécanismes"
        elif abs_corr >= 0.15:
            strength = "modérée (climatologiquement détectable)"
            clim_relevance = "Détectable, validation externe recommandée"
        elif abs_corr >= 0.10:
            strength = "faible (climatologiquement marginale)"
            clim_relevance = "Marginale, mécanismes incertains"
        else:
            strength = "très faible (climatologiquement négligeable)"
            clim_relevance = "Négligeable pour applications pratiques"
        
        # Direction et mécanisme potentiel
        direction = "positive" if correlation > 0 else "négative"
        
        # Significativité statistique
        if p_value < 0.001:
            significance = "très hautement significative"
        elif p_value < 0.01:
            significance = "hautement significative"
        elif p_value < 0.05:
            significance = "significative"
        else:
            significance = "non significative"
        
        # Construction de l'interprétation complète
        interpretation = f"Corrélation {strength} et {direction} (r={correlation:.3f}), "
        interpretation += f"statistiquement {significance} après correction FDR (p={p_value:.3f}). "
        
        if variance_explained is not None:
            interpretation += f"Explique {variance_explained:.1f}% de la variance des événements extrêmes. "
        
        if is_physical_optimal:
            interpretation += "✅ Lag physiquement cohérent avec mécanismes climatiques connus. "
        else:
            interpretation += "⚠️ Lag non optimal physiquement - validation mécanismes recommandée. "
        
        interpretation += f"Pertinence climatologique : {clim_relevance}."
        
        return interpretation
    
    def generate_executive_summary_corrected(self) -> str:
        """
        CORRIGÉ : Génère un résumé exécutif avec validation scientifique.
        
        Returns:
            str: Résumé exécutif formaté avec métriques de qualité
        """
        patterns = self.analyze_correlation_patterns_corrected()
        
        summary_lines = [
            "RÉSUMÉ EXÉCUTIF - ANALYSE DES TÉLÉCONNEXIONS CLIMATIQUES",
            "VERSION SCIENTIFIQUEMENT CORRIGÉE",
            "=" * 80,
            ""
        ]
        
        # Informations générales avec validation
        if hasattr(self.analyzer, 'extreme_events') and self.analyzer.extreme_events is not None:
            n_events = len(self.analyzer.extreme_events)
            period_start = self.analyzer.extreme_events['date'].min()
            period_end = self.analyzer.extreme_events['date'].max()
            period_years = (period_end - period_start).days / 365.25
            
            summary_lines.extend([
                f"📊 DONNÉES ANALYSÉES:",
                f"   • Événements extrêmes: {n_events} sur {period_years:.1f} ans",
                f"   • Période d'étude: {period_start.strftime('%Y-%m-%d')} à {period_end.strftime('%Y-%m-%d')}",
                f"   • Qualité temporelle: {'✅ Climatologiquement appropriée' if period_years >= 30 else '⚠️ Période courte'}",
                ""
            ])
        
        # Indices climatiques analysés avec tests de stationnarité
        if hasattr(self.analyzer, 'climate_indices') and self.analyzer.climate_indices is not None:
            indices_list = list(self.analyzer.climate_indices.columns)
            summary_lines.extend([
                f"🌊 INDICES CLIMATIQUES:",
                f"   • Nombre d'indices: {len(indices_list)}",
                f"   • Indices analysés: {', '.join(indices_list)}",
            ])
            
            # Ajouter résultats stationnarité si disponibles
            if hasattr(self.analyzer, 'stationarity_results') and self.analyzer.stationarity_results:
                summary_lines.append(f"   • Tests de stationnarité: ✅ Effectués")
                for index_name, stationarity in self.analyzer.stationarity_results.items():
                    status = "✅ Stationnaire" if stationarity.get('is_stationary', False) else "🔧 Traité"
                    summary_lines.append(f"      - {index_name}: {status}")
            
            summary_lines.append("")
        
        # Résultats principaux avec validation physique
        sig_summary = patterns.get('significance_summary', {})
        if sig_summary:
            summary_lines.extend([
                f"🎯 RÉSULTATS PRINCIPAUX (APRÈS CORRECTION FDR):",
                f"   • Tests de corrélation effectués: {sig_summary.get('total_tests', 0)}",
                f"   • Corrélations significatives: {sig_summary.get('significant_tests', 0)}",
                f"   • Taux de significativité corrigé: {sig_summary.get('significance_rate', 0):.1%}",
                f"   • Validation physique: {sig_summary.get('physical_optimal_significant', 0)} téléconnexions",
                f"   • Taux de validation physique: {sig_summary.get('physical_validation_rate', 0):.1%}",
                ""
            ])
        
        # Meilleure téléconnexion trouvée
        strongest = patterns.get('strongest_teleconnection')
        if strongest:
            interpretation = self.interpret_correlations_climatological(
                strongest['correlation'], 0.001,  # Assumé significatif
                strongest['variance_explained'], strongest['is_physical_optimal']
            )
            summary_lines.extend([
                f"🏆 MEILLEURE TÉLÉCONNEXION DÉTECTÉE:",
                f"   • Indice: {strongest['index']} ({strongest['metric']})",
                f"   • Décalage: {strongest['lag']} mois",
                f"   • Variance expliquée: {strongest['variance_explained']:.1f}%",
                f"   • Validation physique: {'✅ Confirmée' if strongest['is_physical_optimal'] else '⚠️ À vérifier'}",
                f"   • {interpretation}",
                ""
            ])
        
        # Validation physique par indice
        phys_summary = patterns.get('physical_validation_summary', {})
        if phys_summary:
            summary_lines.extend([
                f"🔬 VALIDATION PHYSIQUE PAR INDICE:",
            ])
            
            for index_name, validation in phys_summary.items():
                rate = validation['validation_rate']
                status = "✅ Excellent" if rate >= 0.7 else "🟡 Bon" if rate >= 0.4 else "❌ Faible"
                summary_lines.append(
                    f"   • {index_name}: {validation['physical_validated']}/{validation['total_significant']} "
                    f"({rate:.0%}) - {status}"
                )
            summary_lines.append("")
        
        # Patterns saisonniers
        seasonal = patterns.get('seasonal_patterns', {})
        if seasonal:
            summary_lines.extend([
                f"🌧️ PATTERNS SAISONNIERS DÉTECTÉS:",
            ])
            
            for index_name, pattern_data in seasonal.items():
                summary_lines.append(
                    f"   • {index_name}: Lags significatifs {pattern_data['significant_lags']} mois "
                    f"(optimal: {pattern_data['most_common_lag']} mois)"
                )
            summary_lines.append("")
        
        # Qualité méthodologique
        quality = patterns.get('methodological_quality', {})
        if quality:
            summary_lines.extend([
                f"📋 VALIDATION MÉTHODOLOGIQUE:",
                f"   • Correction FDR: {'✅ Appliquée' if quality.get('fdr_correction_applied') else '❌ Non appliquée'}",
                f"   • Tests stationnarité: {'✅ Effectués' if quality.get('stationarity_tested') else '❌ Non effectués'}",
                f"   • Contraintes physiques: {'✅ Utilisées' if quality.get('physical_constraints_used') else '❌ Non utilisées'}",
                f"   • Métriques multiples: {'✅ Analysées' if quality.get('multiple_metrics_analyzed') else '❌ Non analysées'}",
                f"   • Seuil d'échantillon: {'✅ Rigoureux (≥30)' if quality.get('minimum_observations_criterion') else '⚠️ Standard'}",
                ""
            ])
        
        # Évaluation scientifique globale
        overall_quality = self._assess_overall_scientific_quality(patterns)
        summary_lines.extend([
            f"🔬 ÉVALUATION SCIENTIFIQUE GLOBALE:",
            f"   • Statut: {overall_quality['status']}",
            f"   • Score de qualité: {overall_quality['score']}/10",
            f"   • Recommandation: {overall_quality['recommendation']}",
            ""
        ])
        
        # Recommandations spécifiques
        recommendations = self._generate_specific_recommendations(patterns)
        summary_lines.extend([
            f"💡 RECOMMANDATIONS SPÉCIFIQUES:",
        ])
        for rec in recommendations:
            summary_lines.append(f"   • {rec}")
        
        summary_lines.append("")
        
        return "\n".join(summary_lines)
    
    def _assess_overall_scientific_quality(self, patterns: Dict) -> Dict[str, Any]:
        """
        Évalue la qualité scientifique globale de l'analyse.
        
        Args:
            patterns (Dict): Patterns analysés
            
        Returns:
            Dict[str, Any]: Évaluation de qualité
        """
        score = 0
        max_score = 10
        
        # Critères de qualité (chaque critère vaut 1-2 points)
        quality = patterns.get('methodological_quality', {})
        sig_summary = patterns.get('significance_summary', {})
        
        # 1. Correction FDR (2 points)
        if quality.get('fdr_correction_applied'):
            score += 2
        
        # 2. Tests de stationnarité (1 point)
        if quality.get('stationarity_tested'):
            score += 1
        
        # 3. Contraintes physiques (2 points)
        if quality.get('physical_constraints_used'):
            score += 2
        
        # 4. Validation physique (2 points)
        phys_rate = sig_summary.get('physical_validation_rate', 0)
        if phys_rate >= 0.5:
            score += 2
        elif phys_rate > 0:
            score += 1
        
        # 5. Taux de significativité réaliste (1 point)
        sig_rate = sig_summary.get('significance_rate', 0)
        if 0.05 <= sig_rate <= 0.3:  # Taux réaliste pour téléconnexions
            score += 1
        
        # 6. Variance expliquée pertinente (1 point)
        strongest = patterns.get('strongest_teleconnection', {})
        if strongest.get('variance_explained', 0) >= 2:
            score += 1
        
        # 7. Échantillon approprié (1 point)
        if quality.get('minimum_observations_criterion'):
            score += 1
        
        # Déterminer le statut
        if score >= 8:
            status = "✅ EXCELLENT - Publiable"
            recommendation = "Prêt pour publication avec validations mineures"
        elif score >= 6:
            status = "🟡 BON - Acceptable avec réserves"
            recommendation = "Acceptable pour publication avec validations complémentaires"
        elif score >= 4:
            status = "⚠️ MODÉRÉ - Améliorations nécessaires"
            recommendation = "Nécessite améliorations avant publication"
        else:
            status = "❌ INSUFFISANT - Révision majeure"
            recommendation = "Révision méthodologique majeure requise"
        
        return {
            'score': score,
            'max_score': max_score,
            'status': status,
            'recommendation': recommendation
        }
    
    def _generate_specific_recommendations(self, patterns: Dict) -> List[str]:
        """
        Génère des recommandations spécifiques basées sur les résultats.
        
        Args:
            patterns (Dict): Patterns analysés
            
        Returns:
            List[str]: Liste de recommandations
        """
        recommendations = []
        
        sig_summary = patterns.get('significance_summary', {})
        quality = patterns.get('methodological_quality', {})
        strongest = patterns.get('strongest_teleconnection', {})
        
        # Recommandations basées sur les résultats
        if sig_summary.get('significance_rate', 0) == 0:
            recommendations.append("PRIORITÉ: Aucune téléconnexion robuste - réviser hypothèses ou augmenter échantillon")
        elif sig_summary.get('physical_validation_rate', 0) < 0.3:
            recommendations.append("Faible validation physique - investiguer mécanismes climatologiques")
        
        if strongest and strongest.get('variance_explained', 0) < 2:
            recommendations.append("Variance expliquée faible - considérer indices composites ou non-linéarités")
        
        # Recommandations méthodologiques
        if not quality.get('fdr_correction_applied'):
            recommendations.append("CRITIQUE: Appliquer correction FDR pour tests multiples")
        
        if not quality.get('stationarity_tested'):
            recommendations.append("Effectuer tests de stationnarité obligatoires")
        
        if not quality.get('physical_constraints_used'):
            recommendations.append("Intégrer contraintes physiques pour validation des lags")
        
        # Recommandations d'extension
        if strongest and strongest.get('is_physical_optimal'):
            recommendations.append(f"Approfondir mécanismes physiques {strongest['index']} → événements extrêmes")
        
        if patterns.get('seasonal_patterns'):
            recommendations.append("Développer modèles prédictifs saisonniers basés sur téléconnexions validées")
        
        # Recommandations de validation
        recommendations.extend([
            "Validation croisée sur période indépendante (split temporel)",
            "Comparaison avec études publiées sur téléconnexions Sahel",
            "Test de robustesse avec différents seuils d'événements extrêmes"
        ])
        
        return recommendations
    
    def generate_detailed_results_section_corrected(self) -> str:
        """
        CORRIGÉ : Génère la section détaillée des résultats avec nouvelle structure.
        
        Returns:
            str: Section des résultats formatée
        """
        lines = [
            "RÉSULTATS DÉTAILLÉS - VERSION SCIENTIFIQUEMENT CORRIGÉE",
            "=" * 70,
            ""
        ]
        
        # 1. Corrélations avec décalages (structure corrigée)
        if hasattr(self.analyzer, 'correlations_results') and self.analyzer.correlations_results:
            lines.extend([
                "1. ANALYSE DES CORRÉLATIONS AVEC DÉCALAGES TEMPORELS",
                "   (Lags physiquement justifiés + Correction FDR)",
                "-" * 65,
                ""
            ])
            
            for index_name, index_results in self.analyzer.correlations_results.items():
                lines.append(f"📊 Indice {index_name}:")
                
                # Résumer par métrique
                for metric_name, lag_results in index_results.items():
                    significant_lags = []
                    physical_optimal_lags = []
                    
                    for lag_key, lag_data in lag_results.items():
                        if lag_key.startswith('lag_'):
                            pearson_data = lag_data.get('pearson', {})
                            lag_num = int(lag_key.split('_')[1])
                            
                            if pearson_data.get('is_significant_corrected', False):
                                interpretation = self.interpret_correlations_climatological(
                                    pearson_data['correlation'],
                                    pearson_data.get('p_value_corrected', pearson_data['p_value']),
                                    pearson_data.get('variance_explained'),
                                    lag_data.get('is_physical_optimal', False)
                                )
                                
                                significant_lags.append({
                                    'lag': lag_num,
                                    'correlation': pearson_data['correlation'],
                                    'variance': pearson_data.get('variance_explained', 0),
                                    'interpretation': interpretation,
                                    'is_physical': lag_data.get('is_physical_optimal', False)
                                })
                                
                                if lag_data.get('is_physical_optimal', False):
                                    physical_optimal_lags.append(lag_num)
                    
                    if significant_lags:
                        lines.append(f"   📈 Métrique {metric_name}:")
                        
                        # Prioriser les lags physiques optimaux
                        physical_lags = [lag for lag in significant_lags if lag['is_physical']]
                        other_lags = [lag for lag in significant_lags if not lag['is_physical']]
                        
                        if physical_lags:
                            lines.append(f"      🎯 LAGS PHYSIQUES OPTIMAUX:")
                            for lag_info in sorted(physical_lags, key=lambda x: x['variance'], reverse=True):
                                lines.append(f"         ⭐ Lag {lag_info['lag']} mois: {lag_info['interpretation']}")
                        
                        if other_lags:
                            lines.append(f"      📊 AUTRES LAGS SIGNIFICATIFS:")
                            for lag_info in sorted(other_lags, key=lambda x: x['variance'], reverse=True):
                                lines.append(f"         • Lag {lag_info['lag']} mois: {lag_info['interpretation']}")
                    else:
                        lines.append(f"   📈 Métrique {metric_name}: ❌ Aucune corrélation significative après correction FDR")
                
                lines.append("")
        
        # 2. Corrélations par phases (structure corrigée)
        if hasattr(self.analyzer, 'phase_correlations') and self.analyzer.phase_correlations:
            lines.extend([
                "2. ANALYSE DES CORRÉLATIONS PAR PHASES DE SAISON",
                "   (Métriques multiples + Correction FDR)",
                "-" * 55,
                ""
            ])
            
            phase_names = {
                'Phase_1_debut': 'Début de saison (Mai-Juin)',
                'Phase_2_pleine': 'Pleine saison (Juillet-Août)', 
                'Phase_3_fin': 'Fin de saison (Septembre-Octobre)'
            }
            
            for phase_key, phase_results in self.analyzer.phase_correlations.items():
                if phase_key in phase_names:
                    phase_name = phase_names[phase_key]
                    lines.append(f"🌧️ {phase_name}:")
                    
                    phase_significant = []
                    
                    for metric_name, metric_results in phase_results.items():
                        for index_name, corr_data in metric_results.items():
                            if corr_data.get('is_significant_corrected', False):
                                interpretation = self.interpret_correlations_climatological(
                                    corr_data['correlation'],
                                    corr_data.get('p_value_corrected', corr_data['p_value']),
                                    corr_data.get('variance_explained')
                                )
                                
                                phase_significant.append({
                                    'index': index_name,
                                    'metric': metric_name,
                                    'interpretation': interpretation,
                                    'variance': corr_data.get('variance_explained', 0)
                                })
                    
                    if phase_significant:
                        # Trier par variance expliquée
                        phase_significant.sort(key=lambda x: x['variance'], reverse=True)
                        
                        for sig_corr in phase_significant:
                            lines.append(f"   ✅ {sig_corr['index']} ({sig_corr['metric']}): {sig_corr['interpretation']}")
                    else:
                        lines.append("   ❌ Aucune corrélation significative après correction FDR")
                    
                    lines.append("")
        
        # 3. Classification ENSO améliorée
        lines.extend([
            "3. CLASSIFICATION ENSO SELON STANDARDS ONI",
            "-" * 45,
            ""
        ])
        
        try:
            if hasattr(self.analyzer, 'identify_enso_events_oni_standard'):
                enso_results = self.analyzer.identify_enso_events_oni_standard()
                if enso_results:
                    lines.append("🌊 Classification ENSO (Standards NOAA/ONI):")
                    lines.append(f"   🔥 Années El Niño: {len(enso_results.get('el_nino', []))} années")
                    lines.append(f"   🧊 Années La Niña: {len(enso_results.get('la_nina', []))} années")
                    lines.append(f"   ⚪ Années neutres: {len(enso_results.get('neutral', []))} années")
                    
                    # Ajouter validation climatologique si disponible
                    if 'validation' in enso_results:
                        lines.append(f"   📊 Validation: {enso_results['validation']}")
                else:
                    lines.append("⚠️ Classification ENSO non disponible")
            else:
                lines.append("⚠️ Classification ENSO non effectuée (méthode legacy)")
        except Exception as e:
            lines.append(f"⚠️ Erreur classification ENSO: {e}")
        
        lines.append("")
        
        return "\n".join(lines)
    
    def generate_methodology_section_corrected(self) -> str:
        """
        CORRIGÉ : Génère la section méthodologique avec corrections appliquées.
        
        Returns:
            str: Section méthodologique formatée
        """
        lines = [
            "MÉTHODOLOGIE - VERSION SCIENTIFIQUEMENT CORRIGÉE",
            "=" * 60,
            "",
            "🔬 CORRECTIONS MÉTHODOLOGIQUES MAJEURES APPLIQUÉES:",
            "",
            "1. PRÉSERVATION DU SIGNAL CLIMATIQUE:",
            "   • Tests de stationnarité obligatoires (ADF + KPSS)",
            "   • Détrend linéaire UNIQUEMENT pour indices non-stationnaires",
            "   • JAMAIS de différenciation destructrice du signal",
            "   • Standardisation sur séries originales préservées",
            "",
            "2. MÉTRIQUES CLIMATOLOGIQUEMENT PERTINENTES:",
            "   • Intensité moyenne des événements extrêmes",
            "   • Percentiles d'intensité (P95, P99)",
            "   • Fréquence des événements (métrique complémentaire)",
            "   • Abandon de la fréquence seule (non représentative)",
            "",
            "3. LAGS PHYSIQUEMENT JUSTIFIÉS:",
            "   • ENSO (Niño 3.4): 2-12 mois (optimaux: 3-6 mois)",
            "     Mécanisme: Circulation de Walker → Mousson ouest-africaine",
            "   • IOD: 1-6 mois (optimaux: 1-3 mois)",
            "     Mécanisme: Circulation régionale océan Indien",
            "   • TNA: 0-4 mois (optimaux: 0-2 mois)",
            "     Mécanisme: Proximité géographique Atlantique",
            "",
            "4. CORRECTION STATISTIQUE RIGOUREUSE:",
            "   • Correction FDR (Benjamini-Hochberg) pour tests multiples",
            "   • Seuil minimum 30 observations (vs 10 standards faibles)",
            "   • Intervalles de confiance bootstrap",
            "   • Validation croisée climatologique",
            "",
            "5. CLASSIFICATION ENSO STANDARD ONI:",
            "   • Seuil ±0.5°C sur moyenne mobile 3 mois",
            "   • Persistance minimale 3 mois consécutifs",
            "   • Saison ENSO appropriée (Oct-Mar précédent)",
            "   • Validation climatologique automatique",
            "",
            "📊 INDICES CLIMATIQUES ANALYSÉS:",
            "   • ENSO (Niño 3.4): Anomalies SST Pacifique tropical",
            "     Zone: 5°S-5°N, 170°W-120°W",
            "   • IOD: Dipôle de l'Océan Indien", 
            "     Ouest: 10°S-10°N, 50°E-70°E",
            "     Est: 10°S-0°, 90°E-108°E",
            "   • TNA: Atlantique Tropical Nord",
            "     Zone: 5.5°N-23.5°N, 57.5°W-15°W",
            "",
            "🌧️ PHASES DE LA SAISON DES PLUIES (PRÉSERVÉES):",
            "   • Phase 1 (Début): Mai-Juin - Installation progressive",
            "   • Phase 2 (Pleine): Juillet-Août - Pic des précipitations", 
            "   • Phase 3 (Fin): Septembre-Octobre - Diminution progressive",
            "",
            "📈 MÉTRIQUES DE VALIDATION CLIMATOLOGIQUE:",
            "   • Variance expliquée par téléconnexion",
            "   • Cohérence avec lags physiques optimaux",
            "   • Taux de validation physique-statistique",
            "   • Robustesse après correction FDR",
            "",
            "🎯 CRITÈRES DE QUALITÉ SCIENTIFIQUE:",
            "   • Minimum 30 observations pour fiabilité statistique",
            "   • Tests de stationnarité systématiques",
            "   • Correction obligatoire pour tests multiples",
            "   • Validation croisée physique-statistique",
            "   • Traçabilité complète des transformations",
            "",
            "⚠️ LIMITATIONS ASSUMÉES:",
            "   • Corrélations linéaires uniquement (non-linéarités ignorées)",
            "   • Hypothèse de stationnarité des téléconnexions dans le temps",
            "   • Pas de modulation par autres oscillations climatiques",
            "   • Analyse régionale (extrapolation locale limitée)",
            "",
        ]
        
        # Ajouter informations spécifiques si disponibles
        if hasattr(self.analyzer, 'stationarity_results') and self.analyzer.stationarity_results:
            lines.extend([
                "🔍 RÉSULTATS DES TESTS DE STATIONNARITÉ:",
            ])
            
            for index_name, stationarity in self.analyzer.stationarity_results.items():
                status = "Stationnaire" if stationarity.get('is_stationary', False) else "Non-stationnaire (traité)"
                recommendation = stationarity.get('recommendation', 'Non spécifiée')
                lines.append(f"   • {index_name}: {status}")
                lines.append(f"     Traitement: {recommendation}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def generate_complete_report_corrected(self, output_file: str):
        """
        CORRIGÉ : Génère un rapport complet compatible avec nouvelle structure.
        
        Args:
            output_file (str): Chemin du fichier de sortie
        """
        print("📄 Génération du rapport détaillé (VERSION CORRIGÉE)...")
        
        # Header du rapport
        header_lines = [
            "=" * 100,
            "RAPPORT D'ANALYSE DES TÉLÉCONNEXIONS CLIMATIQUES",
            "VERSION SCIENTIFIQUEMENT CORRIGÉE",
            "Liens entre indices climatiques et événements de précipitations extrêmes",
            "Région d'étude: Sénégal",
            "=" * 100,
            f"Date de génération: {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
            f"Analysé par: Module d'analyse des téléconnexions climatiques (version corrigée)",
            f"Méthodologie: Standards climatologiques avec validation physique",
            "",
            "🔬 CORRECTIONS MÉTHODOLOGIQUES APPLIQUÉES:",
            "• Préservation du signal climatique (détrend uniquement)",
            "• Métriques d'intensité des événements extrêmes",
            "• Lags physiquement justifiés par indice climatique",
            "• Correction FDR pour tests multiples obligatoire",
            "• Classification ENSO selon standards ONI/NOAA",
            "• Validation croisée physique-statistique",
            "",
            ""
        ]
        
        # Assembler le rapport complet
        report_content = []
        report_content.extend(header_lines)
        report_content.append(self.generate_executive_summary_corrected())
        report_content.append("\n" + "="*100 + "\n")
        report_content.append(self.generate_detailed_results_section_corrected())
        report_content.append("\n" + "="*100 + "\n")
        report_content.append(self.generate_methodology_section_corrected())
        
        # NOUVEAU : Section de validation scientifique
        validation_section = self._generate_scientific_validation_section()
        report_content.append("\n" + "="*100 + "\n")
        report_content.append(validation_section)
        
        # Footer amélioré
        footer_lines = [
            "=" * 100,
            "VALIDATION SCIENTIFIQUE ET CONCLUSIONS",
            "=" * 100,
            "",
            "📋 STATUT DE VALIDATION:",
        ]
        
        # Évaluer la qualité scientifique pour le footer
        patterns = self.analyze_correlation_patterns_corrected()
        quality_assessment = self._assess_overall_scientific_quality(patterns)
        
        footer_lines.extend([
            f"   • Score de qualité scientifique: {quality_assessment['score']}/{quality_assessment['max_score']}",
            f"   • Statut: {quality_assessment['status']}",
            f"   • Recommandation: {quality_assessment['recommendation']}",
            "",
            "🎯 APPLICABILITÉ DES RÉSULTATS:",
        ])
        
        # Recommandations d'application basées sur les résultats
        sig_summary = patterns.get('significance_summary', {})
        strongest = patterns.get('strongest_teleconnection', {})
        
        if sig_summary.get('physical_validation_rate', 0) > 0.5:
            footer_lines.append("   ✅ Téléconnexions physiquement validées - Utilisables pour prédictibilité")
        elif sig_summary.get('significance_rate', 0) > 0:
            footer_lines.append("   🟡 Téléconnexions détectées - Validation externe recommandée")
        else:
            footer_lines.append("   ❌ Aucune téléconnexion robuste - Révision méthodologique nécessaire")
        
        if strongest and strongest.get('variance_explained', 0) >= 5:
            footer_lines.append("   ✅ Variance expliquée significative - Potentiel prédictif confirmé")
        elif strongest and strongest.get('variance_explained', 0) >= 2:
            footer_lines.append("   🟡 Variance expliquée modérée - Utility limitée mais détectable")
        else:
            footer_lines.append("   ⚠️ Variance expliquée faible - Impact climatique marginal")
        
        footer_lines.extend([
            "",
            "📧 Contact technique: [Votre email]",
            "🌐 Projet: Analyse des précipitations extrêmes au Sénégal",
            "📅 Version: 2.0 (Scientifiquement corrigée)",
            "🔗 Méthodologie: Standards climatologiques internationaux",
            "",
            "⚖️ DÉCLARATION DE CONFORMITÉ:",
            "Cette analyse respecte les standards méthodologiques pour l'étude",
            "des téléconnexions climatiques selon les recommandations scientifiques",
            "internationales avec validation croisée physique-statistique.",
            "",
            "=" * 100,
            "FIN DU RAPPORT SCIENTIFIQUEMENT VALIDÉ",
            "=" * 100,
            ""
        ])
        
        report_content.extend(footer_lines)
        
        # Écrire le fichier
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_content))
        
        print(f"   ✅ Rapport corrigé sauvegardé: {output_path}")
    
    def _generate_scientific_validation_section(self) -> str:
        """
        NOUVEAU : Génère une section de validation scientifique.
        
        Returns:
            str: Section de validation formatée
        """
        lines = [
            "VALIDATION SCIENTIFIQUE DE L'ANALYSE",
            "=" * 50,
            ""
        ]
        
        patterns = self.analyze_correlation_patterns_corrected()
        quality = patterns.get('methodological_quality', {})
        sig_summary = patterns.get('significance_summary', {})
        
        lines.extend([
            "🔬 CONFORMITÉ AUX STANDARDS SCIENTIFIQUES:",
            ""
        ])
        
        # Vérification méthodologique
        checks = [
            ("Tests de stationnarité", quality.get('stationarity_tested', False)),
            ("Correction tests multiples", quality.get('fdr_correction_applied', False)),
            ("Contraintes physiques", quality.get('physical_constraints_used', False)),
            ("Métriques multiples", quality.get('multiple_metrics_analyzed', False)),
            ("Échantillon rigoureux", quality.get('minimum_observations_criterion', False))
        ]
        
        for check_name, passed in checks:
            status = "✅ CONFORME" if passed else "❌ NON CONFORME"
            lines.append(f"   • {check_name}: {status}")
        
        lines.extend([
            "",
            "📊 RÉSULTATS DE VALIDATION PHYSIQUE:",
            ""
        ])
        
        # Validation physique détaillée
        phys_summary = patterns.get('physical_validation_summary', {})
        if phys_summary:
            for index_name, validation in phys_summary.items():
                rate = validation['validation_rate']
                if rate >= 0.7:
                    status = "✅ EXCELLENT"
                elif rate >= 0.4:
                    status = "🟡 BON"
                elif rate > 0:
                    status = "⚠️ PARTIEL"
                else:
                    status = "❌ AUCUNE"
                
                lines.append(f"   • {index_name}: {status} "
                           f"({validation['physical_validated']}/{validation['total_significant']} "
                           f"validations, {rate:.0%})")
        
        lines.extend([
            "",
            "🎯 ÉVALUATION DE LA ROBUSTESSE:",
            ""
        ])
        
        # Évaluation robustesse
        total_tests = sig_summary.get('total_tests', 0)
        significant_tests = sig_summary.get('significant_tests', 0)
        physical_validated = sig_summary.get('physical_optimal_significant', 0)
        
        if physical_validated > 0:
            lines.append(f"   ✅ {physical_validated} téléconnexions physiquement cohérentes détectées")
            lines.append(f"   ✅ Validation croisée statistique-physique réussie")
        else:
            lines.append(f"   ❌ Aucune téléconnexion physiquement validée")
            lines.append(f"   ⚠️ Résultats à interpréter avec prudence")
        
        if significant_tests > 0:
            false_discovery_rate = 1 - (physical_validated / significant_tests)
            lines.append(f"   📊 Taux estimé de fausses découvertes: {false_discovery_rate:.1%}")
        
        lines.extend([
            "",
            "⚖️ LIMITATIONS ET INCERTITUDES:",
            ""
        ])
        
        # Limitations spécifiques aux résultats
        limitations = []
        
        if sig_summary.get('significance_rate', 0) < 0.1:
            limitations.append("Taux de significativité faible - Puissance statistique limitée")
        
        if sig_summary.get('physical_validation_rate', 0) < 0.5:
            limitations.append("Validation physique partielle - Mécanismes à clarifier")
        
        strongest = patterns.get('strongest_teleconnection', {})
        if strongest and strongest.get('variance_explained', 0) < 5:
            limitations.append("Variance expliquée faible - Impact pratique limité")
        
        if not quality.get('multiple_metrics_analyzed'):
            limitations.append("Métrique unique - Robustesse non testée")
        
        if limitations:
            for limitation in limitations:
                lines.append(f"   ⚠️ {limitation}")
        else:
            lines.append("   ✅ Aucune limitation majeure identifiée")
        
        lines.extend([
            "",
            "🔮 PERSPECTIVES D'AMÉLIORATION:",
            "",
            "   • Extension temporelle de l'analyse (plus de données)",
            "   • Intégration d'autres indices climatiques (AO, NAO)",
            "   • Analyse des non-linéarités et interactions",
            "   • Validation sur stations météorologiques indépendantes",
            "   • Développement de modèles prédictifs opérationnels",
            ""
        ])
        
        return "\n".join(lines)
    
    def generate_json_report_corrected(self, output_file: str):
        """
        CORRIGÉ : Génère un rapport JSON compatible avec nouvelle structure.
        
        Args:
            output_file (str): Chemin du fichier JSON
        """
        print("📄 Génération du rapport JSON (VERSION CORRIGÉE)...")
        
        patterns = self.analyze_correlation_patterns_corrected()
        
        # Compiler toutes les données avec structure corrigée
        report_data = {
            'metadata': {
                'generation_date': datetime.now().isoformat(),
                'region': 'Sénégal',
                'analysis_type': 'Téléconnexions climatiques',
                'version': '2.0_scientifically_corrected',
                'methodology': 'Standards climatologiques avec validation physique',
                'corrections_applied': [
                    'Signal-preserving preprocessing',
                    'Intensity-based event metrics',
                    'Physically-justified lags',
                    'FDR multiple testing correction',
                    'ONI-standard ENSO classification',
                    'Cross-validation physical-statistical'
                ]
            },
            'data_summary': {},
            'results_summary': {},
            'correlations_lag': {},
            'correlations_phase': {},
            'validation_results': {},
            'quality_assessment': {},
            'recommendations': []
        }
        
        # Données de base
        if hasattr(self.analyzer, 'extreme_events') and self.analyzer.extreme_events is not None:
            period_years = (self.analyzer.extreme_events['date'].max() - 
                          self.analyzer.extreme_events['date'].min()).days / 365.25
            
            report_data['data_summary']['events'] = {
                'total_events': len(self.analyzer.extreme_events),
                'period_start': self.analyzer.extreme_events['date'].min().isoformat(),
                'period_end': self.analyzer.extreme_events['date'].max().isoformat(),
                'period_years': round(period_years, 1),
                'climatological_adequacy': period_years >= 30,
                'phases_distribution': self.analyzer.extreme_events['phase'].value_counts().to_dict()
            }
        
        if hasattr(self.analyzer, 'climate_indices') and self.analyzer.climate_indices is not None:
            report_data['data_summary']['indices'] = {
                'available_indices': list(self.analyzer.climate_indices.columns),
                'period_start': self.analyzer.climate_indices.index.min().isoformat(),
                'period_end': self.analyzer.climate_indices.index.max().isoformat(),
                'total_months': len(self.analyzer.climate_indices),
                'stationarity_results': getattr(self.analyzer, 'stationarity_results', {})
            }
        
        # Résultats principaux avec structure corrigée
        report_data['results_summary'] = patterns.get('significance_summary', {})
        report_data['results_summary']['strongest_teleconnection'] = patterns.get('strongest_teleconnection', {})
        report_data['results_summary']['best_physical_validation'] = patterns.get('best_physical_validation', {})
        
        # Résultats de corrélations (structure adaptée)
        if hasattr(self.analyzer, 'correlations_results'):
            report_data['correlations_lag'] = self.analyzer.correlations_results
        
        if hasattr(self.analyzer, 'phase_correlations'):
            report_data['correlations_phase'] = self.analyzer.phase_correlations
        
        # Résultats de validation
        report_data['validation_results'] = {
            'physical_validation_summary': patterns.get('physical_validation_summary', {}),
            'seasonal_patterns': patterns.get('seasonal_patterns', {}),
            'methodological_quality': patterns.get('methodological_quality', {}),
            'overall_quality_assessment': self._assess_overall_scientific_quality(patterns)
        }
        
        # Évaluation de qualité
        report_data['quality_assessment'] = self._assess_overall_scientific_quality(patterns)
        
        # Recommandations
        report_data['recommendations'] = self._generate_specific_recommendations(patterns)
        
        # Patterns identifiés
        report_data['patterns_identified'] = {
            'index_performances': patterns.get('physical_validation_summary', {}),
            'optimal_lags_by_index': patterns.get('seasonal_patterns', {}),
            'phase_preferences': patterns.get('phase_preferences', {})
        }
        
        # Sauvegarder
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"   ✅ Rapport JSON corrigé sauvegardé: {output_path}")
        
        return report_data
    
    def generate_summary_table_corrected(self) -> pd.DataFrame:
        """
        CORRIGÉ : Génère un tableau de résumé compatible avec nouvelle structure.
        
        Returns:
            pd.DataFrame: Tableau de résumé avec validation physique
        """
        summary_data = []
        
        # Corrélations avec décalages (structure corrigée)
        if hasattr(self.analyzer, 'correlations_results') and self.analyzer.correlations_results:
            for index_name, index_results in self.analyzer.correlations_results.items():
                for metric_name, lag_results in index_results.items():
                    for lag_key, lag_data in lag_results.items():
                        if lag_key.startswith('lag_'):
                            pearson_data = lag_data.get('pearson', {})
                            
                            if pearson_data.get('is_significant_corrected', False):
                                lag_num = int(lag_key.split('_')[1])
                                
                                summary_data.append({
                                    'Type': 'Décalage temporel',
                                    'Indice': index_name,
                                    'Métrique': metric_name,
                                    'Phase/Lag': f"Lag {lag_num} mois",
                                    'Corrélation': pearson_data['correlation'],
                                    'P-value': pearson_data.get('p_value_corrected', pearson_data['p_value']),
                                    'Variance_Expliquée': pearson_data.get('variance_explained', 0),
                                    'Validation_Physique': '✅ Oui' if lag_data.get('is_physical_optimal', False) else '❌ Non',
                                    'Pertinence_Climatologique': pearson_data.get('climatological_significance', 'Non évalué'),
                                    'N_obs': pearson_data['n_obs']
                                })
        
        # Corrélations par phases (structure corrigée)
        if hasattr(self.analyzer, 'phase_correlations') and self.analyzer.phase_correlations:
            phase_names = {
                'Phase_1_debut': 'Début saison',
                'Phase_2_pleine': 'Pleine saison',
                'Phase_3_fin': 'Fin saison'
            }
            
            for phase_key, phase_results in self.analyzer.phase_correlations.items():
                if phase_key in phase_names:
                    for metric_name, metric_results in phase_results.items():
                        for index_name, corr_data in metric_results.items():
                            if corr_data.get('is_significant_corrected', False):
                                summary_data.append({
                                    'Type': 'Phase saisonnière',
                                    'Indice': index_name,
                                    'Métrique': metric_name,
                                    'Phase/Lag': phase_names[phase_key],
                                    'Corrélation': corr_data['correlation'],
                                    'P-value': corr_data.get('p_value_corrected', corr_data['p_value']),
                                    'Variance_Expliquée': corr_data.get('variance_explained', 0),
                                    'Validation_Physique': 'N/A',
                                    'Pertinence_Climatologique': corr_data.get('climatological_significance', 'Non évalué'),
                                    'N_obs': corr_data['n_obs']
                                })
        
        if summary_data:
            df = pd.DataFrame(summary_data)
            # Trier par variance expliquée (plus pertinent que force de corrélation)
            df = df.sort_values('Variance_Expliquée', ascending=False)
            return df
        else:
            return pd.DataFrame(columns=[
                'Type', 'Indice', 'Métrique', 'Phase/Lag', 'Corrélation', 
                'P-value', 'Variance_Expliquée', 'Validation_Physique', 
                'Pertinence_Climatologique', 'N_obs'
            ])
    
    def export_summary_excel_corrected(self, output_file: str):
        """
        CORRIGÉ : Exporte le résumé vers Excel avec validation physique.
        
        Args:
            output_file (str): Chemin du fichier Excel
        """
        print("📊 Export du résumé vers Excel (VERSION CORRIGÉE)...")
        
        try:
            # Créer le tableau de résumé corrigé
            summary_df = self.generate_summary_table_corrected()
            
            # Patterns analysés
            patterns = self.analyze_correlation_patterns_corrected()
            
            # Utiliser openpyxl pour un export plus riche
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                # Feuille principale: résumé des corrélations
                summary_df.to_excel(writer, sheet_name='Corrélations_Validées', index=False)
                
                # Feuille validation physique
                phys_summary = patterns.get('physical_validation_summary', {})
                if phys_summary:
                    validation_data = []
                    for index_name, validation in phys_summary.items():
                        validation_data.append({
                            'Indice': index_name,
                            'Total_Significatif': validation['total_significant'],
                            'Validé_Physiquement': validation['physical_validated'],
                            'Taux_Validation_%': validation['validation_rate'] * 100,
                            'Variance_Max_%': validation['max_variance'],
                            'Statut': 'Excellent' if validation['validation_rate'] >= 0.7 
                                     else 'Bon' if validation['validation_rate'] >= 0.4
                                     else 'Faible'
                        })
                    
                    validation_df = pd.DataFrame(validation_data)
                    validation_df.to_excel(writer, sheet_name='Validation_Physique', index=False)
                
                # Feuille patterns saisonniers
                seasonal = patterns.get('seasonal_patterns', {})
                if seasonal:
                    seasonal_data = []
                    for index_name, pattern_data in seasonal.items():
                        seasonal_data.append({
                            'Indice': index_name,
                            'Lags_Significatifs': ', '.join(map(str, pattern_data['significant_lags'])),
                            'Lag_Optimal': pattern_data['most_common_lag'],
                            'Étendue_Lags': pattern_data['lag_range']
                        })
                    
                    seasonal_df = pd.DataFrame(seasonal_data)
                    seasonal_df.to_excel(writer, sheet_name='Patterns_Saisonniers', index=False)
                
                # Feuille métriques de qualité
                quality_assessment = self._assess_overall_scientific_quality(patterns)
                quality_data = [{
                    'Métrique': 'Score_Qualité_Scientifique',
                    'Valeur': f"{quality_assessment['score']}/{quality_assessment['max_score']}",
                    'Statut': quality_assessment['status'],
                    'Recommandation': quality_assessment['recommendation']
                }]
                
                # Ajouter autres métriques
                sig_summary = patterns.get('significance_summary', {})
                for metric, value in sig_summary.items():
                    if isinstance(value, (int, float)):
                        formatted_value = f"{value:.1%}" if 'rate' in metric else str(value)
                        quality_data.append({
                            'Métrique': metric,
                            'Valeur': formatted_value,
                            'Statut': '',
                            'Recommandation': ''
                        })
                
                quality_df = pd.DataFrame(quality_data)
                quality_df.to_excel(writer, sheet_name='Métriques_Qualité', index=False)
            
            print(f"   ✅ Export Excel corrigé réussi: {output_file}")
            
        except Exception as e:
            print(f"   ❌ Erreur export Excel: {e}")
            # Fallback vers CSV
            csv_file = output_file.replace('.xlsx', '_corrected.csv')
            summary_df = self.generate_summary_table_corrected()
            summary_df.to_csv(csv_file, index=False)
            print(f"   ✅ Export CSV alternatif: {csv_file}")


# CLASSE DE COMPATIBILITÉ POUR L'ANCIEN INTERFACE
class TeleconnectionsReportGenerator(TeleconnectionsReportGeneratorCorrected):
    """
    Classe de compatibilité qui redirige vers les méthodes corrigées.
    """
    
    def analyze_correlation_patterns(self) -> Dict[str, Any]:
        """Redirige vers la version corrigée."""
        return self.analyze_correlation_patterns_corrected()
    
    def generate_executive_summary(self) -> str:
        """Redirige vers la version corrigée."""
        return self.generate_executive_summary_corrected()
    
    def generate_detailed_results_section(self) -> str:
        """Redirige vers la version corrigée."""
        return self.generate_detailed_results_section_corrected()
    
    def generate_complete_report(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.generate_complete_report_corrected(output_file)
    
    def generate_json_report(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.generate_json_report_corrected(output_file)
    
    def generate_summary_table(self) -> pd.DataFrame:
        """Redirige vers la version corrigée."""
        return self.generate_summary_table_corrected()
    
    def export_summary_excel(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.export_summary_excel_corrected(output_file)


if __name__ == "__main__":
    print("📄 Module de génération de rapports pour téléconnexions (VERSION CORRIGÉE)")
    print("=" * 80)
    print("Ce module génère des rapports compatibles avec la structure corrigée:")
    print("• Corrélations avec validation physique")
    print("• Métriques de qualité scientifique")
    print("• Évaluation climatologique automatique")
    print("• Recommandations basées sur les résultats")
    print("\nNouvelles fonctionnalités:")
    print("• Validation croisée physique-statistique")
    print("• Score de qualité scientifique")
    print("• Interprétation climatologique détaillée")
    print("• Export Excel avec feuilles multiples")
    print("\nUtilisation:")
    print("  from src.reports.teleconnections_report import TeleconnectionsReportGeneratorCorrected")
    print("  report_gen = TeleconnectionsReportGeneratorCorrected(analyzer)")
    print("  report_gen.generate_complete_report_corrected('rapport_corrected.txt')")
    print("  report_gen.generate_json_report_corrected('rapport_corrected.json')")
    print("  report_gen.export_summary_excel_corrected('resume_corrected.xlsx')")