# src/config/settings.py
"""
Configuration centralisée pour l'analyse des précipitations extrêmes au Sénégal.
Version mise à jour avec phases de saison des pluies et références géographiques.
"""

import os
from pathlib import Path
from typing import Dict, List, Any

# ============================================================================
# CHEMINS ET DOSSIERS
# ============================================================================

# Dossier racine du projet
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Dossiers de données
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
GEOGRAPHIC_DATA_DIR = DATA_DIR / "geographic"

# Dossiers de sortie
OUTPUT_DIR = PROJECT_ROOT / "outputs"
VISUALIZATION_DIR = OUTPUT_DIR / "visualizations"
REPORTS_DIR = OUTPUT_DIR / "reports"
EXPORT_DIR = OUTPUT_DIR / "exports"

# Sous-dossiers de visualisation organisés par type d'analyse
DETECTION_VIZ_DIR = VISUALIZATION_DIR / "detection"
SPATIAL_VIZ_DIR = VISUALIZATION_DIR / "spatial"
TEMPORAL_VIZ_DIR = VISUALIZATION_DIR / "temporal"
PHASE_VIZ_DIR = VISUALIZATION_DIR / "phases"
GEOGRAPHIC_VIZ_DIR = VISUALIZATION_DIR / "geographic"
COMPARATIVE_VIZ_DIR = VISUALIZATION_DIR / "comparative"

# Fichiers de données
CHIRPS_FILENAME = "chirps_WA_1981_2023_dayly.mat"
CHIRPS_FILEPATH = RAW_DATA_DIR / CHIRPS_FILENAME

# ============================================================================
# PARAMÈTRES GÉOGRAPHIQUES AVANCÉS
# ============================================================================

# Limites géographiques du Sénégal (précises)
SENEGAL_BOUNDS = {
    'lat_min': 12.3,
    'lat_max': 16.7,
    'lon_min': -17.55,
    'lon_max': -11.35
}

# Paramètres de la grille CHIRPS
CHIRPS_GRID = {
    'resolution': 0.25,  # Résolution en degrés (≈25km)
    'lat_pixels': 20,    # Nombre de pixels latitude
    'lon_pixels': 28,    # Nombre de pixels longitude
    'total_pixels': 560  # Total pour le Sénégal
}

# Zones climatiques du Sénégal
CLIMATE_ZONES = {
    'sahelienne': {
        'name': 'Zone sahélienne',
        'regions': ['Saint-Louis', 'Louga', 'Matam'],
        'precipitation_range': '<400mm/an',
        'characteristics': 'Climat sahélien sec'
    },
    'soudano_sahelienne': {
        'name': 'Zone soudano-sahélienne',
        'regions': ['Thiès', 'Diourbel', 'Fatick', 'Kaolack', 'Kaffrine', 'Tambacounda'],
        'precipitation_range': '400-800mm/an',
        'characteristics': 'Climat semi-aride'
    },
    'soudanienne': {
        'name': 'Zone soudanienne',
        'regions': ['Kédougou', 'Kolda', 'Sédhiou', 'Ziguinchor'],
        'precipitation_range': '>800mm/an',
        'characteristics': 'Climat tropical humide'
    },
    'cotiere': {
        'name': 'Zone côtière',
        'regions': ['Dakar'],
        'precipitation_range': 'Variable',
        'characteristics': 'Climat océanique tempéré'
    }
}

# ============================================================================
# CLASSIFICATION PAR PHASES DE LA SAISON DES PLUIES
# ============================================================================

# Nouvelle classification focalisée sur la saison des pluies
RAINFALL_PHASES = {
    'Phase_1_debut': {
        'months': [5, 6],
        'name_fr': 'Début de saison',
        'name_en': 'Early season',
        'description': 'Mai-Juin - Installation progressive des pluies',
        'characteristics': 'Précipitations irrégulières, début de la mousson',
        'color': '#87CEEB',  # Bleu ciel
        'expected_events': 'Faible à modéré'
    },
    'Phase_2_pleine': {
        'months': [7, 8],
        'name_fr': 'Pleine saison',
        'name_en': 'Peak season',
        'description': 'Juillet-Août - Pic des précipitations',
        'characteristics': 'Maximum pluviométrique, événements intenses',
        'color': '#1E90FF',  # Bleu royal
        'expected_events': 'Élevé'
    },
    'Phase_3_fin': {
        'months': [9, 10],
        'name_fr': 'Fin de saison',
        'name_en': 'Late season',
        'description': 'Septembre-Octobre - Diminution progressive',
        'characteristics': 'Décroissance des précipitations, fin de mousson',
        'color': '#4682B4',  # Bleu acier
        'expected_events': 'Modéré'
    },
    'Hors_saison': {
        'months': [11, 12, 1, 2, 3, 4],
        'name_fr': 'Hors saison',
        'name_en': 'Off season',
        'description': 'Novembre-Avril - Saison sèche',
        'characteristics': 'Précipitations négligeables',
        'color': '#D3D3D3',  # Gris
        'expected_events': 'Très faible'
    }
}

# Classification saisonnière traditionnelle (pour compatibilité)
SEASONS_SENEGAL = {
    'saison_seche': {
        'months': [11, 12, 1, 2, 3, 4],
        'name_fr': 'Saison sèche',
        'description': 'Novembre à Avril - Période de faibles précipitations',
        'color': '#E74C3C'
    },
    'saison_des_pluies': {
        'months': [5, 6, 7, 8, 9, 10],
        'name_fr': 'Saison des pluies',
        'description': 'Mai à Octobre - Période de précipitations importantes',
        'color': '#27AE60'
    }
}

# ============================================================================
# PARAMÈTRES DE DÉTECTION D'ÉVÉNEMENTS EXTRÊMES
# ============================================================================

DETECTION_CRITERIA = {
    # Seuils principaux
    'threshold_anomaly': 2.0,          # Seuil d'anomalie standardisée
    'threshold_intense': 20.0,         # Seuil de précipitation intense (mm)
    'threshold_extreme': 50.0,         # Seuil de précipitation extrême (mm)
    
    # Critères spatiaux
    'min_grid_points': 40,             # Nombre minimum de points de grille
    'min_affected_area': 1000,         # Surface minimale affectée (km²)
    'min_coverage_percent': 5.0,       # Couverture minimale (%)
    
    # Critères d'intensité
    'min_precipitation': 5.0,          # Précipitation minimale (mm)
    'min_std_threshold': 0.001,        # Seuil minimal d'écart-type
    'min_anomaly_strength': 1.5,       # Force minimale d'anomalie
    
    # Critères temporels
    'min_duration_hours': 6,           # Durée minimale (heures)
    'max_gap_days': 2,                 # Écart maximal entre événements (jours)
    
    # Critères de forme et connectivité
    'min_compactness': 0.1,           # Compacité minimale
    'max_fragmentation': 0.5,         # Fragmentation maximale
    'min_cluster_ratio': 0.3          # Ratio minimal du cluster principal
}

# Paramètres pour le calcul de la climatologie
CLIMATOLOGY_PARAMS = {
    'smoothing_window': 15,            # Taille de la fenêtre de lissage
    'min_observations': 5,             # Nombre minimum d'observations
    'n_days_year': 366,                # Nombre de jours dans l'année
    'percentiles': [10, 25, 50, 75, 90, 95, 99],  # Percentiles à calculer
    'reference_period': (1981, 2010),  # Période de référence climatologique
    'update_frequency': 'daily'        # Fréquence de mise à jour
}

# ============================================================================
# PARAMÈTRES DE MÉTRIQUES SPATIALES
# ============================================================================

SPATIAL_METRICS = {
    # Métriques de base
    'calculate_area': True,            # Calculer la surface affectée
    'calculate_centroid': True,        # Calculer le centroïde
    'calculate_intensity_stats': True, # Statistiques d'intensité
    
    # Métriques géométriques
    'calculate_extent': True,          # Calculer l'étendue
    'calculate_aspect_ratio': True,    # Calculer le ratio d'aspect
    'calculate_compactness': True,     # Calculer la compacité
    'calculate_elongation': True,      # Calculer l'élongation
    
    # Métriques de connectivité
    'analyze_connectivity': True,      # Analyser la connectivité
    'identify_clusters': True,         # Identifier les clusters
    'calculate_fragmentation': True,   # Calculer la fragmentation
    
    # Métriques géographiques
    'identify_regions': True,          # Identifier les régions
    'identify_departments': True,      # Identifier les départements
    'identify_climate_zones': True,    # Identifier les zones climatiques
    
    # Paramètres de calcul
    'use_intensity_weighting': True,   # Pondération par intensité
    'use_area_weighting': True,        # Pondération par surface
    'min_cluster_size': 5,             # Taille minimale des clusters
    'connectivity_threshold': 1.0      # Seuil de connectivité (pixels)
}

# ============================================================================
# PARAMÈTRES DE VISUALISATION AVANCÉS
# ============================================================================

# Couleurs pour les phases de la saison des pluies
PHASE_COLORS = {
    'Phase_1_debut': '#87CEEB',        # Bleu ciel
    'Phase_2_pleine': '#1E90FF',       # Bleu royal
    'Phase_3_fin': '#4682B4',          # Bleu acier
    'Hors_saison': '#D3D3D3'           # Gris
}

# Couleurs pour les zones climatiques
CLIMATE_COLORS = {
    'sahelienne': '#FFA07A',           # Saumon clair
    'soudano_sahelienne': '#98FB98',   # Vert pâle
    'soudanienne': '#228B22',          # Vert forêt
    'cotiere': '#87CEEB'               # Bleu ciel
}

# Couleurs pour les régions (gradient)
REGION_COLORS = {
    'Dakar': '#FF6B6B',               # Rouge corail
    'Thiès': '#4ECDC4',               # Turquoise
    'Diourbel': '#45B7D1',            # Bleu ciel
    'Fatick': '#96CEB4',              # Vert menthe
    'Kaolack': '#FECA57',             # Jaune
    'Kaffrine': '#FF9FF3',            # Rose
    'Tambacounda': '#54A0FF',         # Bleu
    'Kédougou': '#5F27CD',            # Violet
    'Kolda': '#00D2D3',               # Cyan
    'Sédhiou': '#FF9F43',             # Orange
    'Ziguinchor': '#1DD1A1',          # Vert émeraude
    'Saint-Louis': '#FFD93D',         # Or
    'Louga': '#6C5CE7',               # Violet clair
    'Matam': '#A29BFE'                # Lavande
}

# Paramètres de tracé
PLOT_PARAMS = {
    'figure_size': (15, 8),           # Taille par défaut
    'figure_size_large': (20, 12),    # Taille pour analyses complexes
    'figure_size_small': (10, 6),     # Taille pour graphiques simples
    'dpi': 300,                       # Résolution
    'style': 'seaborn-v0_8-whitegrid', # Style par défaut
    'font_size': 12,                  # Taille de police
    'title_size': 16,                 # Taille titre
    'label_size': 14,                 # Taille labels
    'legend_size': 11,                # Taille légende
    'alpha_scatter': 0.7,             # Transparence scatter
    'alpha_hist': 0.8,                # Transparence histogramme
    'alpha_fill': 0.3,                # Transparence remplissage
    'line_width': 2.5,                # Épaisseur lignes
    'marker_size': 6,                 # Taille marqueurs
    'marker_edge_width': 1.5,         # Épaisseur bord marqueurs
    'grid_alpha': 0.3,                # Transparence grille
    'spine_width': 1.2                # Épaisseur bordures
}

# ============================================================================
# PARAMÈTRES NUMÉRIQUES ET QUALITÉ
# ============================================================================

NUMERICAL_PARAMS = {
    # Valeurs de remplacement
    'pos_inf_replacement': 15,
    'neg_inf_replacement': -15,
    'nan_replacement': 0,
    
    # Précision numérique
    'float_precision': 1e-10,
    'coordinate_precision': 4,        # Décimales pour coordonnées
    'metric_precision': 2,            # Décimales pour métriques
    
    # Seuils de validation
    'min_valid_ratio': 0.7,          # Ratio minimal de données valides
    'max_missing_consecutive': 5,     # Jours consécutifs manquants max
    'outlier_threshold': 5.0,         # Seuil de détection d'outliers (sigma)
    
    # Paramètres de performance
    'chunk_size': 1000,              # Taille des chunks pour traitement
    'max_memory_gb': 8,              # Mémoire maximale utilisable
    'parallel_processes': 4          # Nombre de processus parallèles
}

# ============================================================================
# NOMS DE FICHIERS DE SORTIE ORGANISÉS
# ============================================================================

OUTPUT_FILENAMES = {
    # Fichiers de données principales
    'extreme_events': 'extreme_events_phases_senegal.csv',
    'spatial_metrics': 'spatial_metrics_detailed.csv',
    'climatology': 'climatology_senegal.npz',
    'anomalies': 'standardized_anomalies_senegal.npz',
    'phase_statistics': 'phase_statistics_summary.json',
    
    # Rapports et analyses
    'detection_report': 'rapport_detection_phases.txt',
    'spatial_analysis_report': 'rapport_analyse_spatiale.txt',
    'geographic_summary': 'resume_geographique.json',
    'validation_report': 'rapport_validation.txt',
    
    # Exports pour utilisateurs
    'events_export': 'evenements_extremes_export.xlsx',
    'summary_dashboard': 'dashboard_resume.html',
    'metadata': 'metadata_complete.json'
}

VISUALIZATION_FILENAMES = {
    # Analyses temporelles
    'phase_distribution': '01_distribution_phases.png',
    'temporal_evolution': '02_evolution_temporelle.png',
    'seasonal_patterns': '03_patterns_saisonniers.png',
    
    # Analyses spatiales
    'spatial_distribution': '04_distribution_spatiale.png',
    'regional_analysis': '05_analyse_regionale.png',
    'climate_zones': '06_zones_climatiques.png',
    
    # Métriques et comparaisons
    'intensity_coverage': '07_intensite_couverture.png',
    'spatial_metrics': '08_metriques_spatiales.png',
    'comparative_analysis': '09_analyse_comparative.png',
    
    # Validations
    'validation_plots': '10_validation_analyses.png',
    'quality_assessment': '11_evaluation_qualite.png',
    
    # Synthèse
    'executive_summary': '12_synthese_executive.png'
}

# ============================================================================
# MÉTADONNÉES DU PROJET ÉTENDUES
# ============================================================================

PROJECT_INFO = {
    'title': 'Analyse des précipitations extrêmes au Sénégal par phases',
    'subtitle': 'Caractérisation spatio-temporelle des événements pluviométriques',
    'author': 'Équipe de recherche climatologique',
    'institution': 'Centre de recherche climatique',
    'version': '2.0.0',
    'last_update': '2024-01-15',
    
    # Données et méthodes
    'data_source': 'CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)',
    'temporal_coverage': '1981-2023 (43 ans)',
    'spatial_coverage': 'Sénégal (12°N-17°N, 18°W-11°W)',
    'temporal_resolution': 'Quotidienne',
    'spatial_resolution': '0.25° (~25 km)',
    
    # Innovations méthodologiques
    'key_features': [
        'Classification par phases de la saison des pluies',
        'Métriques spatiales avancées',
        'Analyse géographique par entités administratives',
        'Validation climatologique intégrée',
        'Visualisations interactives'
    ],
    
    # Références
    'data_reference': 'Funk, C., et al. (2015). The climate hazards infrared precipitation with stations—a new environmental record for monitoring extremes. Scientific Data, 2(1), 1-21.',
    'methodology_reference': 'Méthode développée spécifiquement pour le climat sahélien',
    
    # Contacts
    'contact_email': 'contact@recherche-climat.org',
    'documentation_url': 'https://github.com/projet-senegal-climat'
}

# ============================================================================
# FONCTIONS UTILITAIRES ÉTENDUES
# ============================================================================

def create_output_directories():
    """Crée tous les dossiers de sortie nécessaires."""
    directories = [
        # Dossiers principaux
        OUTPUT_DIR, VISUALIZATION_DIR, REPORTS_DIR, EXPORT_DIR,
        PROCESSED_DATA_DIR, GEOGRAPHIC_DATA_DIR,
        
        # Sous-dossiers de visualisation
        DETECTION_VIZ_DIR, SPATIAL_VIZ_DIR, TEMPORAL_VIZ_DIR,
        PHASE_VIZ_DIR, GEOGRAPHIC_VIZ_DIR, COMPARATIVE_VIZ_DIR
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    
    print("[OK] Tous les dossiers de sortie ont ete crees")
    return directories

def get_phase_from_month(month: int) -> str:
    """Détermine la phase de la saison des pluies à partir du mois."""
    for phase_name, phase_info in RAINFALL_PHASES.items():
        if month in phase_info['months']:
            return phase_name
    return 'Hors_saison'

def get_season_from_month(month: int) -> str:
    """Détermine la saison traditionnelle à partir du mois (pour compatibilité)."""
    if month in SEASONS_SENEGAL['saison_seche']['months']:
        return 'Saison_seche'
    elif month in SEASONS_SENEGAL['saison_des_pluies']['months']:
        return 'Saison_des_pluies'
    else:
        return 'Indetermine'

def get_climate_zone_regions(zone_name: str) -> List[str]:
    """Retourne les régions d'une zone climatique."""
    return CLIMATE_ZONES.get(zone_name, {}).get('regions', [])

def get_phase_color(phase_name: str) -> str:
    """Retourne la couleur associée à une phase."""
    return PHASE_COLORS.get(phase_name, '#808080')

def get_region_color(region_name: str) -> str:
    """Retourne la couleur associée à une région."""
    return REGION_COLORS.get(region_name, '#808080')

def get_output_path(filename_key: str) -> Path:
    """Génère le chemin complet pour un fichier de sortie."""
    if filename_key in OUTPUT_FILENAMES:
        filename = OUTPUT_FILENAMES[filename_key]
        
        # Déterminer le dossier selon l'extension
        if filename.endswith('.txt'):
            return REPORTS_DIR / filename
        elif filename.endswith('.json'):
            return PROCESSED_DATA_DIR / filename
        elif filename.endswith('.xlsx') or filename.endswith('.html'):
            return EXPORT_DIR / filename
        else:
            return PROCESSED_DATA_DIR / filename
            
    elif filename_key in VISUALIZATION_FILENAMES:
        filename = VISUALIZATION_FILENAMES[filename_key]
        
        # Déterminer le sous-dossier selon le type d'analyse
        if 'phase' in filename or 'temporal' in filename or 'seasonal' in filename:
            return PHASE_VIZ_DIR / filename
        elif 'spatial' in filename or 'regional' in filename or 'climate' in filename:
            return SPATIAL_VIZ_DIR / filename
        elif 'comparative' in filename or 'metrics' in filename:
            return COMPARATIVE_VIZ_DIR / filename
        else:
            return DETECTION_VIZ_DIR / filename
    else:
        raise ValueError(f"Clé de fichier inconnue: {filename_key}")

def validate_configuration() -> bool:
    """Valide la cohérence de la configuration."""
    validation_errors = []
    
    # Vérifier la cohérence des phases
    all_months = set()
    for phase_info in RAINFALL_PHASES.values():
        phase_months = set(phase_info['months'])
        if all_months & phase_months:
            validation_errors.append("Chevauchement de mois entre phases")
        all_months.update(phase_months)
    
    if all_months != set(range(1, 13)):
        validation_errors.append("Tous les mois ne sont pas couverts par les phases")
    
    # Vérifier les seuils de détection
    if DETECTION_CRITERIA['threshold_anomaly'] <= 0:
        validation_errors.append("Seuil d'anomalie doit être positif")
    
    if DETECTION_CRITERIA['min_grid_points'] <= 0:
        validation_errors.append("Nombre minimum de points de grille doit être positif")
    
    # Vérifier les limites géographiques
    if SENEGAL_BOUNDS['lat_min'] >= SENEGAL_BOUNDS['lat_max']:
        validation_errors.append("Limites de latitude incohérentes")
    
    if SENEGAL_BOUNDS['lon_min'] >= SENEGAL_BOUNDS['lon_max']:
        validation_errors.append("Limites de longitude incohérentes")
    
    if validation_errors:
        print("❌ Erreurs de configuration détectées:")
        for error in validation_errors:
            print(f"   • {error}")
        return False
    else:
        print("✅ Configuration validée avec succès")
        return True

def print_project_info():
    """Affiche les informations détaillées du projet."""
    print("=" * 80)
    print(f"🎯 {PROJECT_INFO['title']}")
    print(f"   {PROJECT_INFO['subtitle']}")
    print("=" * 80)
    print(f"Version: {PROJECT_INFO['version']} (mise à jour: {PROJECT_INFO['last_update']})")
    print(f"Auteur: {PROJECT_INFO['author']}")
    print(f"Institution: {PROJECT_INFO['institution']}")
    print()
    print("📊 DONNÉES:")
    print(f"   Source: {PROJECT_INFO['data_source']}")
    print(f"   Couverture temporelle: {PROJECT_INFO['temporal_coverage']}")
    print(f"   Couverture spatiale: {PROJECT_INFO['spatial_coverage']}")
    print(f"   Résolution temporelle: {PROJECT_INFO['temporal_resolution']}")
    print(f"   Résolution spatiale: {PROJECT_INFO['spatial_resolution']}")
    print()
    print("🔬 INNOVATIONS MÉTHODOLOGIQUES:")
    for feature in PROJECT_INFO['key_features']:
        print(f"   • {feature}")
    print()
    print("🌧️  PHASES DE LA SAISON DES PLUIES:")
    for phase_name, phase_info in RAINFALL_PHASES.items():
        if phase_name != 'Hors_saison':
            print(f"   • {phase_info['name_fr']}: {phase_info['description']}")
    print()
    print("🌍 ZONES CLIMATIQUES:")
    for zone_name, zone_info in CLIMATE_ZONES.items():
        print(f"   • {zone_info['name']}: {zone_info['precipitation_range']}")
    print("=" * 80)

def get_configuration_summary() -> Dict[str, Any]:
    """Retourne un résumé de la configuration pour export."""
    return {
        'project_info': PROJECT_INFO,
        'phases_count': len(RAINFALL_PHASES),
        'climate_zones_count': len(CLIMATE_ZONES),
        'detection_criteria': DETECTION_CRITERIA,
        'spatial_resolution': CHIRPS_GRID['resolution'],
        'temporal_coverage': PROJECT_INFO['temporal_coverage'],
        'regions_count': len(REGION_COLORS),
        'output_files_count': len(OUTPUT_FILENAMES),
        'visualization_files_count': len(VISUALIZATION_FILENAMES)
    }

if __name__ == "__main__":
    print("🔧 Configuration du projet - Version 2.0.0")
    print_project_info()
    
    print("\n🔍 Validation de la configuration:")
    is_valid = validate_configuration()
    
    if is_valid:
        print("\n📁 Création des dossiers de sortie:")
        directories = create_output_directories()
        
        print(f"\n📊 Résumé de la configuration:")
        summary = get_configuration_summary()
        print(f"   • Phases définies: {summary['phases_count']}")
        print(f"   • Zones climatiques: {summary['climate_zones_count']}")
        print(f"   • Régions: {summary['regions_count']}")
        print(f"   • Fichiers de sortie: {summary['output_files_count']}")
        print(f"   • Visualisations: {summary['visualization_files_count']}")
        
        print("\n✅ Configuration prête pour l'analyse!")
    else:
        print("\n❌ Veuillez corriger les erreurs de configuration avant de continuer.")