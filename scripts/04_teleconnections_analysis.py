#!/usr/bin/env python3
# scripts/04_teleconnections_analysis.py
"""
Script principal pour l'analyse des téléconnexions climatiques - VERSION SCIENTIFIQUEMENT CORRIGÉE.

Ce script analyse les liens statistiques entre les modes de variabilité climatique
à grande échelle (ENSO, IOD, TNA) et l'intensité des événements de précipitations
extrêmes au Sénégal, avec corrections méthodologiques majeures.

CORRECTIONS APPLIQUÉES :
- Préprocessing non-destructeur du signal climatique
- Métriques d'intensité au lieu de fréquence seule
- Lags étendus et justifiés physiquement
- Classification ENSO selon standards ONI
- Validation climatologique automatique

Usage:
    python scripts/04_teleconnections_analysis.py
    python scripts/04_teleconnections_analysis.py --max-lag 12 --use-physical-constraints
    python scripts/04_teleconnections_analysis.py --events-file path/to/events.csv

Auteur: [Votre nom]
Date: [Date]
"""

import sys
import argparse
import time
from pathlib import Path
import pandas as pd
import numpy as np

# Ajouter le répertoire racine au path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.analysis.teleconnections import (
    TeleconnectionsAnalyzer, 
    analyze_teleconnections_complete_scientifically_corrected
)
from src.data.climate_indices_loader import ClimateIndicesLoader
from src.reports.teleconnections_report import TeleconnectionsReportGenerator
from src.visualization.teleconnections_plots import TeleconnectionsVisualizer
from src.config.settings import (
    PROCESSED_DATA_DIR, OUTPUT_DIR, REPORTS_DIR, VISUALIZATION_DIR,
    create_output_directories, print_project_info
)

def setup_arguments():
    """Configure les arguments de ligne de commande avec options scientifiques."""
    parser = argparse.ArgumentParser(
        description="Analyse des téléconnexions climatiques (VERSION SCIENTIFIQUEMENT CORRIGÉE)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CORRECTIONS MAJEURES APPLIQUÉES :
  • Préprocessing non-destructeur du signal climatique
  • Métriques d'intensité des événements extrêmes  
  • Lags physiquement justifiés (2-12 mois par indice)
  • Classification ENSO selon standards ONI
  • Correction FDR pour tests multiples
  • Validation climatologique automatique

Exemples:
  python scripts/04_teleconnections_analysis.py --corrected
  python scripts/04_teleconnections_analysis.py --max-lag 12 --use-physical-constraints
  python scripts/04_teleconnections_analysis.py --min-observations 30 --corrected
        """
    )
    
    # Fichiers d'entrée
    parser.add_argument(
        '--events-file',
        type=str,
        default=None,
        help='Chemin vers le fichier des événements extrêmes (CSV)'
    )
    
    parser.add_argument(
        '--indices-file', 
        type=str,
        default=None,
        help='Chemin vers le fichier des indices climatiques (CSV)'
    )
    
    # NOUVEAU : Paramètres scientifiques corrigés
    parser.add_argument(
        '--corrected',
        action='store_true',
        help='Utiliser la version scientifiquement corrigée (RECOMMANDÉ)'
    )
    
    parser.add_argument(
        '--max-lag',
        type=int,
        default=12,  # CORRECTION : étendu à 12 mois
        help='Décalage maximal en mois pour l\'analyse (défaut: 12, min recommandé pour ENSO)'
    )
    
    parser.add_argument(
        '--use-physical-constraints',
        action='store_true',
        default=True,
        help='Utiliser les contraintes physiques par indice (RECOMMANDÉ)'
    )
    
    parser.add_argument(
        '--min-observations',
        type=int,
        default=30,  # CORRECTION : seuil rigoureux
        help='Nombre minimum d\'observations pour fiabilité (défaut: 30)'
    )
    
    parser.add_argument(
        '--significance-level',
        type=float,
        default=0.05,
        help='Niveau de significativité pour les tests (défaut: 0.05)'
    )
    
    parser.add_argument(
        '--enso-threshold',
        type=float,
        default=0.5,
        help='Seuil pour la classification ENSO en °C (défaut: 0.5, standard ONI)'
    )
    
    # Options de sortie
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Répertoire de sortie principal'
    )
    
    parser.add_argument(
        '--skip-visualization',
        action='store_true',
        help='Ne pas générer les visualisations'
    )
    
    parser.add_argument(
        '--skip-report',
        action='store_true', 
        help='Ne pas générer le rapport détaillé'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Mode verbeux pour plus de détails'
    )
    
    # NOUVEAU : Options de validation
    parser.add_argument(
        '--skip-physical-validation',
        action='store_true',
        help='Ignorer la validation physique des téléconnexions'
    )
    
    parser.add_argument(
        '--force-legacy',
        action='store_true',
        help='Forcer l\'utilisation de l\'ancienne version (NON RECOMMANDÉ)'
    )
    
    return parser

def validate_input_files_corrected(events_file: Path, indices_file: Path) -> bool:
    """
    Valide les fichiers d'entrée avec vérifications scientifiques renforcées.
    
    Args:
        events_file (Path): Fichier des événements extrêmes
        indices_file (Path): Fichier des indices climatiques
        
    Returns:
        bool: True si les fichiers sont valides pour analyse scientifique
    """
    print("🔍 VALIDATION DES FICHIERS D'ENTRÉE (VERSION SCIENTIFIQUE)")
    print("=" * 70)
    
    errors = []
    warnings = []
    
    # Vérifier l'existence des fichiers
    if not events_file.exists():
        errors.append(f"Fichier d'événements non trouvé: {events_file}")
    else:
        print(f"   ✅ Événements extrêmes: {events_file}")
        
        # Vérification approfondie du fichier d'événements
        try:
            df_events = pd.read_csv(events_file)
            required_cols = ['date', 'year', 'month', 'phase']
            missing_cols = [col for col in required_cols if col not in df_events.columns]
            
            if missing_cols:
                errors.append(f"Colonnes manquantes dans le fichier d'événements: {missing_cols}")
            else:
                print(f"      Colonnes requises présentes: {required_cols}")
                
                # NOUVEAU : Vérifier colonnes d'intensité
                intensity_cols = [col for col in df_events.columns 
                                if any(keyword in col.lower() for keyword in 
                                     ['precipitation', 'rainfall', 'precip', 'intensity', 'amount', 'mm'])]
                
                if intensity_cols:
                    print(f"      ✅ Colonnes d'intensité détectées: {intensity_cols}")
                else:
                    warnings.append("Aucune colonne d'intensité détectée - analyse limitée à la fréquence")
                
                # Vérifier la taille de l'échantillon
                if len(df_events) < 30:
                    warnings.append(f"Échantillon petit ({len(df_events)} événements) - résultats peu fiables")
                
                # Vérifier la période temporelle
                df_events['date'] = pd.to_datetime(df_events['date'])
                period_years = (df_events['date'].max() - df_events['date'].min()).days / 365.25
                
                if period_years < 10:
                    warnings.append(f"Période courte ({period_years:.1f} ans) - téléconnexions difficiles à détecter")
                elif period_years >= 30:
                    print(f"      ✅ Période climatologique appropriée: {period_years:.1f} ans")
                else:
                    print(f"      ⚠️  Période modérée: {period_years:.1f} ans")
                
        except Exception as e:
            errors.append(f"Erreur lecture fichier d'événements: {e}")
    
    if not indices_file.exists():
        errors.append(f"Fichier d'indices non trouvé: {indices_file}")
    else:
        print(f"   ✅ Indices climatiques: {indices_file}")
        
        # Vérification approfondie du fichier d'indices
        try:
            df_indices = pd.read_csv(indices_file)
            expected_indices = ['IOD', 'Nino34', 'TNA']
            available_indices = [idx for idx in expected_indices if idx in df_indices.columns]
            
            if not available_indices:
                errors.append("Aucun indice climatique standard trouvé (IOD, Nino34, TNA)")
            else:
                print(f"      ✅ Indices disponibles: {available_indices}")
                
                # NOUVEAU : Vérifier la qualité des indices
                for index_name in available_indices:
                    index_series = df_indices[index_name].dropna()
                    
                    if len(index_series) < 100:
                        warnings.append(f"Indice {index_name} : données insuffisantes ({len(index_series)} obs)")
                    
                    # Vérifier les valeurs aberrantes
                    z_scores = np.abs((index_series - index_series.mean()) / index_series.std())
                    outliers = (z_scores > 4).sum()
                    
                    if outliers > len(index_series) * 0.05:  # Plus de 5% d'outliers
                        warnings.append(f"Indice {index_name} : {outliers} valeurs aberrantes détectées")
                
        except Exception as e:
            errors.append(f"Erreur lecture fichier d'indices: {e}")
    
    # Affichage des résultats
    if errors:
        print("\n❌ ERREURS CRITIQUES:")
        for error in errors:
            print(f"   • {error}")
    
    if warnings:
        print("\n⚠️  AVERTISSEMENTS:")
        for warning in warnings:
            print(f"   • {warning}")
    
    if not errors and not warnings:
        print("\n✅ Validation complète réussie - Fichiers optimaux pour analyse")
        return True
    elif not errors:
        print("\n🟡 Validation réussie avec avertissements - Procéder avec prudence")
        return True
    else:
        print("\n❌ Validation échouée - Corriger les erreurs avant de continuer")
        return False

def run_teleconnections_analysis_corrected(args):
    """
    Lance l'analyse complète des téléconnexions avec corrections scientifiques.
    
    Args:
        args: Arguments de ligne de commande
    """
    start_time = time.time()
    
    # Affichage des informations du projet
    print_project_info()
    
    # NOUVEAU : Avertissement sur la version utilisée
    if args.force_legacy and not args.corrected:
        print("\n⚠️  AVERTISSEMENT: Version legacy forcée - Non recommandée pour publication")
        print("   Utilisez --corrected pour la version scientifiquement validée")
    elif args.corrected or not args.force_legacy:
        print("\n✅ UTILISATION DE LA VERSION SCIENTIFIQUEMENT CORRIGÉE")
        print("   Toutes les corrections méthodologiques appliquées")
    
    # Configuration des chemins
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        suffix = "_scientifically_corrected" if args.corrected else "_legacy"
        output_dir = OUTPUT_DIR / f"teleconnections{suffix}"
    
    # Chemins par défaut si non spécifiés
    if args.events_file:
        events_file = Path(args.events_file)
    else:
        events_file = PROCESSED_DATA_DIR / "extreme_events_phases_senegal.csv"
    
    if args.indices_file:
        indices_file = Path(args.indices_file)
    else:
        indices_file = PROCESSED_DATA_DIR / "climate_indices_combined.csv"
    
    print(f"\n📁 CONFIGURATION DES CHEMINS")
    print("=" * 50)
    print(f"   Événements: {events_file}")
    print(f"   Indices: {indices_file}")
    print(f"   Sortie: {output_dir}")
    
    # Créer les dossiers de sortie
    create_output_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Charger ou créer les indices si nécessaire
    if not load_or_create_indices(indices_file):
        print("\n❌ Impossible de procéder sans indices climatiques")
        return False
    
    # Validation des fichiers d'entrée (version renforcée)
    if not validate_input_files_corrected(events_file, indices_file):
        print("\n❌ Validation échouée - Arrêt de l'analyse")
        return False
    
    # ============================================================================
    # ÉTAPE 1: CHOIX DE LA VERSION D'ANALYSE
    # ============================================================================
    
    if args.corrected or (not args.force_legacy):
        print(f"\n{'='*100}")
        print("ANALYSE SCIENTIFIQUEMENT CORRIGÉE DES TÉLÉCONNEXIONS")
        print("="*100)
        
        try:
            # Utiliser la fonction corrigée
            analyzer = analyze_teleconnections_complete_scientifically_corrected(
                events_file=str(events_file),
                indices_file=str(indices_file),
                output_dir=str(output_dir),
                min_observations=args.min_observations,
                apply_corrections=True,
                max_lag=args.max_lag,
                use_physical_constraints=args.use_physical_constraints
            )
            
            print("✅ Analyse scientifiquement corrigée terminée")
            
        except Exception as e:
            print(f"❌ Erreur pendant l'analyse corrigée: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    else:
        # Version legacy (déconseillée)
        print(f"\n{'='*100}")
        print("ANALYSE LEGACY DES TÉLÉCONNEXIONS (NON RECOMMANDÉE)")
        print("="*100)
        print("⚠️  Cette version contient des défauts méthodologiques")
        
        try:
            # Initialiser l'analyseur legacy
            analyzer = TeleconnectionsAnalyzer(significance_level=args.significance_level)
            
            # Charger les données
            print("🔄 Chargement des données...")
            events_df = analyzer.load_extreme_events(str(events_file))
            indices_df = analyzer.load_climate_indices(str(indices_file))
            
            if events_df.empty or indices_df.empty:
                print("❌ Échec du chargement des données")
                return False
            
            # Analyse legacy avec décalages temporels
            print(f"\n🔄 Analyse legacy avec décalages (0-{args.max_lag} mois)...")
            lag_results = analyzer.analyze_teleconnections_with_lags(
                max_lag=args.max_lag, 
                verbose=args.verbose
            )
            
            # Analyse par phases de saison
            print(f"\n🔄 Analyse par phases de saison...")
            phase_results = analyzer.analyze_seasonal_teleconnections()
            
            # Analyse spécifique ENSO
            print(f"\n🔄 Analyse spécifique ENSO...")
            enso_results = analyzer.analyze_enso_impact()
            
            # Sauvegarder les résultats
            analyzer.save_results(str(output_dir))
            
            print("✅ Analyse legacy terminée (avec limitations)")
            
        except Exception as e:
            print(f"❌ Erreur pendant l'analyse legacy: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return False
    
    # ============================================================================
    # ÉTAPE 2: GÉNÉRATION DES VISUALISATIONS (Version compatible)
    # ============================================================================
    
    if not args.skip_visualization:
        print(f"\n{'='*80}")
        print("GÉNÉRATION DES VISUALISATIONS (VERSION CORRIGÉE)")
        print("="*80)
        
        try:
            # CORRECTION : Utiliser la classe corrigée
            from src.visualization.teleconnections_plots import TeleconnectionsVisualizerCorrected
            
            visualizer = TeleconnectionsVisualizerCorrected(analyzer)
            viz_dir = output_dir / "visualizations"
            viz_dir.mkdir(parents=True, exist_ok=True)
            
            print("🎨 Génération des graphiques compatibles...")
            
            # Utiliser les méthodes corrigées
            print("   📊 Corrélations avec décalages (version corrigée)...")
            visualizer.plot_lag_correlations_corrected(str(viz_dir / "lag_correlations_corrected.png"))
            
            print("   🌧️  Corrélations par phases (version corrigée)...")
            visualizer.plot_phase_correlations_corrected(str(viz_dir / "phase_correlations_corrected.png"))
            
            print("   🌊 Analyse ENSO (version corrigée)...")
            visualizer.plot_enso_analysis_corrected(str(viz_dir / "enso_analysis_corrected.png"))
            
            print("   📈 Résumé des téléconnexions (version corrigée)...")
            visualizer.plot_teleconnections_summary_corrected(str(viz_dir / "teleconnections_summary_corrected.png"))
            
            print("✅ Visualisations corrigées générées avec succès")
            
        except Exception as e:
            print(f"❌ Erreur pendant la génération des visualisations: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    # ============================================================================
    # ÉTAPE 3: GÉNÉRATION DU RAPPORT (Version compatible)
    # ============================================================================
    
    if not args.skip_report:
        print(f"\n{'='*80}")
        print("GÉNÉRATION DU RAPPORT DÉTAILLÉ (VERSION CORRIGÉE)")
        print("="*80)
        
        try:
            # CORRECTION : Utiliser la classe corrigée
            from src.reports.teleconnections_report import TeleconnectionsReportGeneratorCorrected
            
            report_generator = TeleconnectionsReportGeneratorCorrected(analyzer)
            
            # Nom de fichier adapté à la version
            version_suffix = "_scientifically_corrected"
            report_file = output_dir / f"rapport_teleconnections{version_suffix}.txt"
            
            print("📄 Génération du rapport (version corrigée)...")
            report_generator.generate_complete_report_corrected(str(report_file))
            
            # Rapport en format JSON pour post-traitement
            json_report_file = output_dir / f"rapport_teleconnections{version_suffix}.json"
            report_generator.generate_json_report_corrected(str(json_report_file))
            
            # Export Excel du résumé des corrélations (version corrigée)
            excel_file = output_dir / f"resume_correlations{version_suffix}.xlsx"
            try:
                report_generator.export_summary_excel_corrected(str(excel_file))
            except Exception as e:
                print(f"   ⚠️  Export Excel échoué: {e}")
                # Fallback vers CSV
                csv_file = output_dir / f"resume_correlations{version_suffix}.csv"
                summary_df = report_generator.generate_summary_table_corrected()
                summary_df.to_csv(csv_file, index=False)
                print(f"   ✅ Export CSV alternatif: {csv_file}")
            
            print("✅ Rapport corrigé généré avec succès")
            
        except Exception as e:
            print(f"❌ Erreur pendant la génération du rapport: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            visualizer.plot_teleconnections_summary(str(viz_dir / "teleconnections_summary.png"))
            
            print("✅ Visualisations générées")
            
        except Exception as e:
            print(f"❌ Erreur pendant la génération des visualisations: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    # ============================================================================
    # ÉTAPE 3: GÉNÉRATION DU RAPPORT (Version adaptée)
    # ============================================================================
    
    if not args.skip_report:
        print(f"\n{'='*80}")
        print("GÉNÉRATION DU RAPPORT DÉTAILLÉ")
        print("="*80)
        
        try:
            report_generator = TeleconnectionsReportGenerator(analyzer)
            
            # Nom de fichier adapté à la version
            version_suffix = "_scientifically_corrected" if args.corrected else "_legacy"
            report_file = output_dir / f"rapport_teleconnections{version_suffix}.txt"
            
            print("📄 Génération du rapport...")
            report_generator.generate_complete_report(str(report_file))
            
            # Rapport en format JSON pour post-traitement
            json_report_file = output_dir / f"rapport_teleconnections{version_suffix}.json"
            report_generator.generate_json_report(str(json_report_file))
            
            # Export Excel du résumé des corrélations
            excel_file = output_dir / f"resume_correlations{version_suffix}.xlsx"
            try:
                report_generator.export_summary_excel(str(excel_file))
            except Exception as e:
                print(f"   ⚠️  Export Excel échoué: {e}")
            
            print("✅ Rapport généré")
            
        except Exception as e:
            print(f"❌ Erreur pendant la génération du rapport: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
    
    # ============================================================================
    # RÉSUMÉ FINAL SCIENTIFIQUE
    # ============================================================================
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\n{'='*100}")
    print("🎉 ANALYSE DES TÉLÉCONNEXIONS TERMINÉE")
    print("="*100)
    
    print(f"⏱️  PERFORMANCE:")
    print(f"   Durée totale: {duration:.1f} secondes ({duration/60:.1f} minutes)")
    
    # Résumé scientifique adapté à la version
    if args.corrected or (not args.force_legacy):
        print(f"\n📊 RÉSULTATS SCIENTIFIQUEMENT CORRIGÉS:")
        
        if hasattr(analyzer, 'generate_correlation_summary_corrected'):
            summary = analyzer.generate_correlation_summary_corrected()
            quality_metrics = summary['quality_metrics']
            climate_assessment = summary['climatological_assessment']
            
            print(f"   Tests effectués: {quality_metrics['total_tests_performed']}")
            print(f"   Tests fiables: {quality_metrics['reliable_tests']} ({quality_metrics['reliability_rate']:.1%})")
            print(f"   Significatifs après correction FDR: {quality_metrics['significant_after_correction']}")
            print(f"   Validation physique: {quality_metrics['physical_optimal_significant']} ({quality_metrics['physical_validation_rate']:.1%})")
            print(f"   Cohérence climatologique: {climate_assessment['physical_coherence']}")
            
            # Top téléconnexions physiquement validées
            if summary['physical_optimal_correlations']:
                print(f"\n🎯 TOP TÉLÉCONNEXIONS PHYSIQUEMENT VALIDÉES:")
                for i, corr in enumerate(summary['physical_optimal_correlations'][:3], 1):
                    print(f"   {i}. {corr['index']} ({corr['metric']}) - Lag {corr['lag'].replace('lag_', '')} mois:")
                    print(f"      r={corr['correlation']:+.3f}, variance={corr['variance_explained']:.1f}%")
            
            # Évaluation scientifique finale
            print(f"\n🔬 ÉVALUATION SCIENTIFIQUE:")
            if quality_metrics['physical_validation_rate'] > 0.5 and quality_metrics['reliability_rate'] > 0.7:
                print("   ✅ ACCEPTABLE POUR PUBLICATION avec validations complémentaires")
            elif quality_metrics['significance_rate_corrected'] > 0 and quality_metrics['physical_validation_rate'] > 0.2:
                print("   🟡 RÉSULTATS PRÉLIMINAIRES - Validation externe requise")
            else:
                print("   🔴 INSUFFISANT POUR PUBLICATION - Révision méthodologique nécessaire")
    
    else:
        print(f"\n📊 RÉSULTATS LEGACY (AVEC LIMITATIONS):")
        print("   ⚠️  Cette version contient des défauts méthodologiques")
        print("   ⚠️  Résultats non validés pour publication scientifique")
        print("   ➡️  Utilisez --corrected pour analyse rigoureuse")
    
    print(f"\n📁 FICHIERS GÉNÉRÉS:")
    print(f"   📊 Résultats principaux: {output_dir}/")
    print(f"   📈 Visualisations: {output_dir}/visualizations/")
    
    version_label = "scientifiquement corrigée" if args.corrected else "legacy"
    print(f"   📄 Rapport ({version_label}): {output_dir}/rapport_teleconnections_*.txt")
    print(f"   📋 Rapport JSON: {output_dir}/rapport_teleconnections_*.json")
    
    # Recommandations finales
    print(f"\n🎯 RECOMMANDATIONS FINALES:")
    
    if args.corrected or (not args.force_legacy):
        print("   • Examiner le rapport de validation climatologique")
        print("   • Vérifier la cohérence physique des téléconnexions détectées")
        print("   • Valider les résultats sur période indépendante")
        print("   • Développer modèles prédictifs basés sur téléconnexions validées")
        print("   • Investiguer les mécanismes physiques des liens détectés")
    else:
        print("   • ⚠️  PRIORITÉ: Relancer avec --corrected")
        print("   • Ne pas utiliser ces résultats pour publication")
        print("   • Appliquer les corrections méthodologiques")
    
    print(f"\n✅ ANALYSE TERMINÉE - Code de sortie: 0")
    return True

def load_or_create_indices(indices_file: Path) -> bool:
    """
    Charge les indices climatiques ou les crée s'ils n'existent pas.
    
    Args:
        indices_file (Path): Chemin vers le fichier d'indices
        
    Returns:
        bool: True si les indices sont disponibles
    """
    if indices_file.exists():
        return True
    
    print("📥 CRÉATION DES INDICES CLIMATIQUES")
    print("=" * 50)
    print("Les indices climatiques n'existent pas encore.")
    print("Tentative de création automatique...")
    
    try:
        # Utiliser le loader d'indices climatiques
        loader = ClimateIndicesLoader()
        indices, combined_df = loader.load_all_indices()
        
        if not combined_df.empty:
            # Sauvegarder le dataset combiné
            indices_file.parent.mkdir(parents=True, exist_ok=True)
            combined_df.to_csv(indices_file)
            print(f"✅ Indices créés et sauvegardés: {indices_file}")
            return True
        else:
            print("❌ Impossible de créer les indices climatiques")
            return False
            
    except Exception as e:
        print(f"❌ Erreur lors de la création des indices: {e}")
        print("\nVeuillez:")
        print("   1. Vérifier la présence des fichiers d'indices bruts")
        print("   2. Exécuter le loader d'indices séparément")
        print("   3. Ou fournir un fichier d'indices existant")
        return False

def main():
    """Fonction principale avec gestion des versions."""
    # Configuration des arguments
    parser = setup_arguments()
    args = parser.parse_args()
    
    # Vérification rapide des paramètres
    if args.max_lag < 0 or args.max_lag > 24:
        print("❌ Le décalage maximal doit être entre 0 et 24 mois")
        return 1
    
    if args.significance_level <= 0 or args.significance_level >= 1:
        print("❌ Le niveau de significativité doit être entre 0 et 1")
        return 1
    
    # NOUVEAU : Avertissement sur paramètres non scientifiques
    if args.max_lag < 6:
        print("⚠️  ATTENTION: Lag maximal < 6 mois peut manquer des téléconnexions ENSO")
    
    if args.min_observations < 30:
        print("⚠️  ATTENTION: Minimum < 30 observations compromet la fiabilité statistique")
    
    # Affichage des paramètres si mode verbeux
    if args.verbose:
        print(f"\n🔧 PARAMÈTRES D'ANALYSE:")
        print(f"   Version: {'Scientifiquement corrigée' if args.corrected else 'Legacy'}")
        print(f"   Décalage maximal: {args.max_lag} mois")
        print(f"   Contraintes physiques: {args.use_physical_constraints}")
        print(f"   Observations minimum: {args.min_observations}")
        print(f"   Niveau de significativité: {args.significance_level}")
        print(f"   Seuil ENSO: ±{args.enso_threshold}°C")
        print(f"   Mode verbeux: {args.verbose}")
    
    # Recommandation automatique de la version corrigée
    if not args.corrected and not args.force_legacy:
        print(f"\n💡 RECOMMANDATION: Utilisation automatique de la version corrigée")
        print(f"   Ajoutez --force-legacy pour forcer l'ancienne version (non recommandé)")
        args.corrected = True
    
    # Lancer l'analyse
    try:
        success = run_teleconnections_analysis_corrected(args)
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n⚠️  Analyse interrompue par l'utilisateur")
        return 1
        
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)