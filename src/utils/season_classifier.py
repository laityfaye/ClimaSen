# src/utils/season_classifier.py
"""
Module de classification par phases de la saison des pluies pour le Sénégal.
Focus sur les 3 phases distinctes de la saison pluvieuse.
"""

import pandas as pd
from typing import Tuple, Dict
import sys
from pathlib import Path

# Configuration des phases de la saison des pluies
PHASES_SAISON_PLUIES = {
    'Phase_1_debut': {
        'months': [5, 6],
        'description': 'Début de saison des pluies (Mai-Juin)',
        'caracteristiques': 'Installation progressive des pluies'
    },
    'Phase_2_pleine': {
        'months': [7, 8], 
        'description': 'Pleine saison des pluies (Juillet-Août)',
        'caracteristiques': 'Pic des précipitations'
    },
    'Phase_3_fin': {
        'months': [9, 10],
        'description': 'Fin de saison des pluies (Septembre-Octobre)', 
        'caracteristiques': 'Diminution progressive des pluies'
    }
}

def get_phase_from_month(month: int) -> str:
    """
    Détermine la phase de la saison des pluies à partir du mois.
    
    Args:
        month (int): Numéro du mois (1-12)
        
    Returns:
        str: Phase correspondante ou 'Hors_saison'
    """
    if month in [5, 6]:
        return 'Phase_1_debut'
    elif month in [7, 8]:
        return 'Phase_2_pleine'
    elif month in [9, 10]:
        return 'Phase_3_fin'
    else:
        return 'Hors_saison'


def classify_rainfall_phases(df_events: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """
    Classification par phases de la saison des pluies pour le Sénégal.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        Tuple[pd.DataFrame, str]: (DataFrame avec classification, statut_validation)
    """
    print("\n🌧️  CLASSIFICATION PAR PHASES DE LA SAISON DES PLUIES")
    print("=" * 60)
    print("Définition des phases (focus saison des pluies uniquement):")
    print("• Phase 1 (Début)  : Mai-Juin - Installation progressive")
    print("• Phase 2 (Pleine) : Juillet-Août - Pic des précipitations")
    print("• Phase 3 (Fin)    : Septembre-Octobre - Diminution progressive")
    
    # Filtrer uniquement les événements de la saison des pluies
    df_saison_pluies = df_events[df_events['month'].isin([5, 6, 7, 8, 9, 10])].copy()
    
    print(f"\n📊 FILTRAGE DES DONNÉES:")
    print(f"   Total événements: {len(df_events)}")
    print(f"   Événements saison des pluies: {len(df_saison_pluies)}")
    print(f"   Événements filtrés (hors saison): {len(df_events) - len(df_saison_pluies)}")
    
    if len(df_saison_pluies) == 0:
        print("❌ Aucun événement dans la saison des pluies!")
        return df_events, "AUCUN_EVENEMENT"
    
    # Appliquer la classification par phases
    df_saison_pluies['phase'] = df_saison_pluies['month'].apply(get_phase_from_month)
    
    # Statistiques par phases
    phase_counts = df_saison_pluies['phase'].value_counts()
    total_events = len(df_saison_pluies)
    
    print(f"\n📈 DISTRIBUTION PAR PHASES:")
    for phase in ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']:
        count = phase_counts.get(phase, 0)
        percentage = count / total_events * 100 if total_events > 0 else 0
        phase_info = PHASES_SAISON_PLUIES[phase]
        print(f"   {phase}: {count} événements ({percentage:.1f}%)")
        print(f"     └─ {phase_info['description']}")
    
    # Validation de la distribution
    validation_status = validate_phase_distribution(phase_counts, total_events)
    
    print(f"\n🔍 VALIDATION DE LA DISTRIBUTION:")
    print_validation_status(validation_status, phase_counts, total_events)
    
    return df_saison_pluies, validation_status


def validate_phase_distribution(phase_counts: pd.Series, total_events: int) -> str:
    """
    Valide la distribution des événements par phases.
    
    Args:
        phase_counts (pd.Series): Comptage par phases
        total_events (int): Total des événements
        
    Returns:
        str: Statut de validation
    """
    if total_events == 0:
        return "AUCUN_EVENEMENT"
    
    # Calculer les pourcentages
    phase2_pct = phase_counts.get('Phase_2_pleine', 0) / total_events * 100
    phase1_pct = phase_counts.get('Phase_1_debut', 0) / total_events * 100
    phase3_pct = phase_counts.get('Phase_3_fin', 0) / total_events * 100
    
    # Validation basée sur la concentration attendue en phase 2
    if phase2_pct >= 50:
        return "EXCELLENT"  # Phase 2 dominante comme attendu
    elif phase2_pct >= 40:
        return "TRES_COHERENT"
    elif phase2_pct >= 30:
        return "COHERENT"
    elif phase2_pct >= 20:
        return "MODERE"
    else:
        return "INCOHERENT"


def print_validation_status(status: str, phase_counts: pd.Series, total_events: int):
    """
    Affiche le statut de validation avec détails.
    
    Args:
        status (str): Statut de validation
        phase_counts (pd.Series): Comptage par phases
        total_events (int): Total des événements
    """
    phase2_pct = phase_counts.get('Phase_2_pleine', 0) / total_events * 100 if total_events > 0 else 0
    
    if status == "EXCELLENT":
        print(f"✅ Excellente distribution: {phase2_pct:.1f}% en phase 2 (pleine saison)")
        print("   La concentration en pleine saison est optimale")
    elif status == "TRES_COHERENT":
        print(f"✅ Très cohérent: {phase2_pct:.1f}% en phase 2 (pleine saison)")
        print("   Distribution bien alignée avec le climat sahélien")
    elif status == "COHERENT":
        print(f"✅ Cohérent: {phase2_pct:.1f}% en phase 2 (pleine saison)")
        print("   Distribution acceptable")
    elif status == "MODERE":
        print(f"⚠️  Modéré: {phase2_pct:.1f}% en phase 2 (pleine saison)")
        print("   Distribution moins concentrée que attendu")
    elif status == "INCOHERENT":
        print(f"❌ Incohérent: {phase2_pct:.1f}% en phase 2 (pleine saison)")
        print("   Distribution ne correspond pas au pattern climatique")
    else:
        print("❌ Aucun événement à analyser")


class RainfallPhaseClassifier:
    """
    Classe pour la classification par phases de la saison des pluies.
    """
    
    def __init__(self):
        """Initialise le classificateur par phases."""
        self.phases_info = PHASES_SAISON_PLUIES
    
    def filter_rainy_season(self, df_events: pd.DataFrame) -> pd.DataFrame:
        """
        Filtre les événements pour ne garder que ceux de la saison des pluies.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            pd.DataFrame: DataFrame filtré (Mai-Octobre uniquement)
        """
        return df_events[df_events['month'].isin([5, 6, 7, 8, 9, 10])].copy()
    
    def classify_by_phases(self, df_events: pd.DataFrame) -> pd.DataFrame:
        """
        Classifie les événements par phases de la saison des pluies.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            pd.DataFrame: DataFrame avec colonne 'phase' ajoutée
        """
        df_filtered = self.filter_rainy_season(df_events)
        df_filtered['phase'] = df_filtered['month'].apply(get_phase_from_month)
        return df_filtered
    
    def get_phase_statistics(self, df_events: pd.DataFrame) -> Dict[str, Dict]:
        """
        Calcule les statistiques détaillées par phase.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements avec phases
            
        Returns:
            Dict[str, Dict]: Statistiques par phase
        """
        stats = {}
        
        for phase in df_events['phase'].unique():
            if phase == 'Hors_saison':
                continue
                
            phase_data = df_events[df_events['phase'] == phase]
            
            stats[phase] = {
                'count': len(phase_data),
                'percentage': len(phase_data) / len(df_events) * 100,
                'avg_coverage': phase_data['coverage_percent'].mean(),
                'avg_precipitation': phase_data['max_precip'].mean(),
                'avg_anomaly': phase_data['max_anomaly'].mean(),
                'median_precipitation': phase_data['max_precip'].median(),
                'max_precipitation': phase_data['max_precip'].max(),
                'min_precipitation': phase_data['max_precip'].min(),
                'std_precipitation': phase_data['max_precip'].std(),
                'months': list(phase_data['month'].unique()),
                'description': self.phases_info[phase]['description'],
                'caracteristiques': self.phases_info[phase]['caracteristiques']
            }
        
        return stats
    
    def classify_and_analyze(self, df_events: pd.DataFrame) -> Tuple[pd.DataFrame, str, Dict]:
        """
        Classification complète avec analyse détaillée.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Tuple[pd.DataFrame, str, Dict]: (DataFrame classifié, statut, statistiques)
        """
        print("\n🌧️  CLASSIFICATION PAR PHASES DE LA SAISON DES PLUIES")
        print("=" * 60)
        
        # Filtrer et classifier
        df_classified = self.classify_by_phases(df_events)
        
        if len(df_classified) == 0:
            print("❌ Aucun événement dans la saison des pluies!")
            return df_events, "AUCUN_EVENEMENT", {}
        
        # Statistiques détaillées
        stats = self.get_phase_statistics(df_classified)
        
        print(f"\n📊 ANALYSE DÉTAILLÉE PAR PHASES:")
        print(f"   Total événements analysés: {len(df_classified)}")
        print(f"   Événements filtrés (hors saison): {len(df_events) - len(df_classified)}")
        
        for phase in ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']:
            if phase in stats:
                s = stats[phase]
                print(f"\n   🔹 {phase}:")
                print(f"     Description: {s['description']}")
                print(f"     Événements: {s['count']} ({s['percentage']:.1f}%)")
                print(f"     Précipitation: {s['avg_precipitation']:.1f}mm (moy), {s['max_precipitation']:.1f}mm (max)")
                print(f"     Couverture: {s['avg_coverage']:.1f}%")
                print(f"     Mois concernés: {s['months']}")
        
        # Validation
        phase_counts = df_classified['phase'].value_counts()
        validation_status = validate_phase_distribution(phase_counts, len(df_classified))
        
        print(f"\n🔍 VALIDATION CLIMATOLOGIQUE:")
        print_validation_status(validation_status, phase_counts, len(df_classified))
        
        return df_classified, validation_status, stats
    
    def get_phase_description(self, phase: str) -> str:
        """
        Retourne la description d'une phase.
        
        Args:
            phase (str): Nom de la phase
            
        Returns:
            str: Description de la phase
        """
        return self.phases_info.get(phase, {}).get('description', 'Phase inconnue')


def get_month_name_fr(month: int) -> str:
    """
    Retourne le nom du mois en français.
    
    Args:
        month (int): Numéro du mois (1-12)
        
    Returns:
        str: Nom du mois en français
    """
    month_names = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    return month_names.get(month, 'Inconnu')


def get_phase_color(phase: str) -> str:
    """
    Retourne une couleur associée à chaque phase pour les visualisations.
    
    Args:
        phase (str): Nom de la phase
        
    Returns:
        str: Code couleur hexadécimal
    """
    colors = {
        'Phase_1_debut': '#87CEEB',   # Bleu ciel (début)
        'Phase_2_pleine': '#1E90FF',  # Bleu royal (pleine)
        'Phase_3_fin': '#4682B4',     # Bleu acier (fin)
        'Hors_saison': '#D3D3D3'      # Gris (hors saison)
    }
    return colors.get(phase, '#000000')


if __name__ == "__main__":
    print("Module de classification par phases de la saison des pluies")
    print("=" * 60)
    print("Ce module contient les outils pour:")
    print("• Filtrer uniquement les événements de la saison des pluies")
    print("• Classifier par phases (début, pleine, fin)")
    print("• Analyser la distribution temporelle des événements")
    print("• Valider la cohérence climatologique")
    print("\nPhases définies:")
    for phase, info in PHASES_SAISON_PLUIES.items():
        print(f"• {phase}: {info['description']}")
        print(f"  └─ {info['caracteristiques']}")