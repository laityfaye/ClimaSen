#!/usr/bin/env python3
"""
Script de visualisation de la distribution annuelle des événements extrêmes par phases
Génère un graphique montrant les anomalies standardisées et le nombre d'événements
pour les phases de début, pleine saison et fin de la saison des pluies au Sénégal.

Auteur: Équipe de recherche climatologique
Version: 2.1.0
Date: 2024-01-15
Modification: Statistiques et légendes déplacées en dehors de la zone graphique
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys
import warnings
warnings.filterwarnings('ignore')

# Configuration du style matplotlib
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams.update({
    'font.size': 12,
    'axes.titlesize': 16,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
    'figure.titlesize': 18,
    'figure.dpi': 300
})

def load_extreme_events_data():
    """
    Charge les données d'événements extrêmes depuis le fichier CSV.
    
    Returns:
        pandas.DataFrame: Données des événements extrêmes
    """
    # Chemin vers le fichier de données
    data_path = Path("data/processed/extreme_events_phases_senegal.csv")
    
    if not data_path.exists():
        raise FileNotFoundError(f"Le fichier {data_path} n'existe pas. "
                              "Veuillez vous assurer que l'analyse de détection a été exécutée.")
    
    # Chargement des données
    df = pd.read_csv(data_path)
    
    # Conversion de la colonne date
    df['date'] = pd.to_datetime(df['date'])
    
    # Filtrer uniquement les phases de la saison des pluies
    phases_saison = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']
    df_filtered = df[df['phase'].isin(phases_saison)].copy()
    
    print(f"✅ Données chargées: {len(df_filtered)} événements extrêmes")
    print(f"   Période: {df_filtered['year'].min()}-{df_filtered['year'].max()}")
    print(f"   Phases incluses: {list(df_filtered['phase'].unique())}")
    
    return df_filtered

def calculate_annual_statistics(df):
    """
    Calcule les statistiques annuelles par phase.
    
    Args:
        df (pandas.DataFrame): Données des événements extrêmes
        
    Returns:
        pandas.DataFrame: Statistiques annuelles par phase et année
    """
    # Groupement par année et phase
    annual_stats = df.groupby(['year', 'phase']).agg({
        'mean_anomaly': ['mean', 'count'],  # Anomalie moyenne et nombre d'événements
        'max_anomaly': 'max',               # Anomalie maximale
        'std_anomaly': 'mean'               # Écart-type moyen des anomalies
    }).round(3)
    
    # Aplatir les colonnes multi-niveaux
    annual_stats.columns = ['_'.join(col).strip() for col in annual_stats.columns]
    annual_stats = annual_stats.rename(columns={
        'mean_anomaly_mean': 'anomalie_moyenne',
        'mean_anomaly_count': 'nombre_evenements',
        'max_anomaly_max': 'anomalie_max',
        'std_anomaly_mean': 'ecart_type_anomalie'
    })
    
    # Réinitialiser l'index pour avoir year et phase comme colonnes
    annual_stats = annual_stats.reset_index()
    
    return annual_stats

def create_phase_distribution_plot(annual_stats):
    """
    Crée la visualisation de la distribution annuelle par phases.
    
    Args:
        annual_stats (pandas.DataFrame): Statistiques annuelles
        
    Returns:
        matplotlib.figure.Figure: Figure matplotlib
    """
    # Configuration des couleurs simplifiées et élégantes
    phase_colors = {
        'Phase_1_debut': '#2C3E50',   # Bleu marine
        'Phase_2_pleine': '#34495E',  # Gris bleuté
        'Phase_3_fin': '#5D6D7E'      # Gris ardoise
    }
    
    # Couleurs neutres et professionnelles pour les barres
    event_color = '#85C1E9'      # Bleu clair pour événements
    anomaly_color = '#5DADE2'    # Bleu moyen pour anomalies
    mean_line_color = '#E74C3C'  # Rouge pour les lignes de moyenne
    
    phase_names = {
        'Phase_1_debut': 'Phase 1 - Début (Mai-Juin)',
        'Phase_2_pleine': 'Phase 2 - Pleine (Juillet-Août)',
        'Phase_3_fin': 'Phase 3 - Fin (Septembre-Octobre)'
    }
    
    # Créer la figure avec sous-graphiques (6 graphiques: 2 par phase)
    # Augmenter la hauteur pour faire de la place aux éléments externes
    fig, axes = plt.subplots(6, 1, figsize=(20, 30))
    fig.patch.set_facecolor('#FAFAFA')
    fig.suptitle('Distribution Annuelle des Événements Extrêmes par Phases\n'
                 'Nombre d\'Événements et Anomalies Standardisées - Sénégal (1981-2023)',
                 fontsize=22, fontweight='bold', y=0.98, color='#2C3E50',
                 bbox=dict(boxstyle="round,pad=0.8", facecolor='white', 
                          edgecolor='#BDC3C7', linewidth=2))
    
    phases = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']
    
    # Obtenir la plage complète des années pour toutes les phases
    all_years = sorted(annual_stats['year'].unique())
    
    for i, phase in enumerate(phases):
        # Indices des axes pour cette phase (nombre d'événements puis anomalies)
        ax_events = axes[i * 2]      # Graphique du nombre d'événements (en haut)
        ax_anomalies = axes[i * 2 + 1]  # Graphique des anomalies (en bas)
        
        # Filtrer les données pour cette phase
        phase_data = annual_stats[annual_stats['phase'] == phase]
        
        if phase_data.empty:
            ax_events.text(0.5, 0.5, f'Aucune donnée pour {phase_names[phase]}', 
                          transform=ax_events.transAxes, ha='center', va='center',
                          fontsize=14, alpha=0.7, color='#7F8C8D')
            ax_anomalies.text(0.5, 0.5, f'Aucune donnée pour {phase_names[phase]}', 
                             transform=ax_anomalies.transAxes, ha='center', va='center',
                             fontsize=14, alpha=0.7, color='#7F8C8D')
            continue
        
        # Créer un DataFrame complet avec toutes les années (remplir les manquantes avec 0)
        complete_data = pd.DataFrame({'year': all_years})
        complete_data = complete_data.merge(phase_data, on='year', how='left')
        complete_data['anomalie_moyenne'] = complete_data['anomalie_moyenne'].fillna(0)
        complete_data['nombre_evenements'] = complete_data['nombre_evenements'].fillna(0)
        
        # Calculer les moyennes (seulement sur les données non nulles)
        actual_data = phase_data[phase_data['nombre_evenements'] > 0]
        if not actual_data.empty:
            mean_events = actual_data['nombre_evenements'].mean()
            mean_anomaly = actual_data['anomalie_moyenne'].mean()
        else:
            mean_events = 0
            mean_anomaly = 0
        
        # === GRAPHIQUE DU NOMBRE D'ÉVÉNEMENTS (en haut) ===
        bars_events = ax_events.bar(complete_data['year'], complete_data['nombre_evenements'], 
                                   color=event_color, alpha=0.7, width=0.75,
                                   label='Nombre d\'événements', 
                                   edgecolor='white', linewidth=1.5)
        
        # Ligne de moyenne pour les événements
        if mean_events > 0:
            ax_events.axhline(y=mean_events, color=mean_line_color, linestyle='--', 
                             linewidth=2.5, alpha=0.8, 
                             label=f'Moyenne: {mean_events:.1f}')
        
        # Configuration du graphique des événements
        ax_events.set_ylabel('Nombre d\'Événements', fontsize=15, fontweight='bold', 
                            color='#2C3E50')
        ax_events.tick_params(axis='y', labelcolor='#2C3E50', labelsize=12)
        ax_events.tick_params(axis='x', labelsize=11)
        ax_events.grid(True, alpha=0.4, axis='y', linestyle='-', linewidth=0.8, color='#D5DBDB')
        ax_events.set_facecolor('white')
        
        # Titre avec plus d'espace en haut
        ax_events.set_title(f'{phase_names[phase]} - Nombre d\'Événements', 
                           fontsize=17, fontweight='bold', color=phase_colors[phase], 
                           pad=80,  # Augmenté pour faire de la place
                           bbox=dict(boxstyle="round,pad=0.5", facecolor='#ECF0F1', 
                                    edgecolor=phase_colors[phase], linewidth=2))
        
        # === GRAPHIQUE DES ANOMALIES (en bas) ===
        bars_anomalies = ax_anomalies.bar(complete_data['year'], complete_data['anomalie_moyenne'], 
                                         color=anomaly_color, alpha=0.7, width=0.75,
                                         label='Anomalie standardisée moyenne', 
                                         edgecolor='white', linewidth=1.5)
        
        # Ligne de moyenne pour les anomalies
        if mean_anomaly != 0:
            ax_anomalies.axhline(y=mean_anomaly, color=mean_line_color, linestyle='--', 
                                linewidth=2.5, alpha=0.8, 
                                label=f'Moyenne: {mean_anomaly:.2f}')
        
        # Ligne de référence à zéro
        ax_anomalies.axhline(y=0, color='#34495E', linestyle='-', 
                            linewidth=1, alpha=0.6)
        
        # Configuration du graphique des anomalies
        ax_anomalies.set_ylabel('Anomalie Standardisée', fontsize=15, fontweight='bold', 
                               color='#2C3E50')
        ax_anomalies.tick_params(axis='y', labelcolor='#2C3E50', labelsize=12)
        ax_anomalies.tick_params(axis='x', labelsize=11)
        ax_anomalies.grid(True, alpha=0.4, axis='y', linestyle='-', linewidth=0.8, color='#D5DBDB')
        ax_anomalies.set_facecolor('white')
        
        # Titre avec plus d'espace en haut
        ax_anomalies.set_title(f'{phase_names[phase]} - Anomalies Standardisées', 
                              fontsize=17, fontweight='bold', color=phase_colors[phase], 
                              pad=80,  # Augmenté pour faire de la place
                              bbox=dict(boxstyle="round,pad=0.5", facecolor='#ECF0F1', 
                                       edgecolor=phase_colors[phase], linewidth=2))
        
        # Configuration de l'axe des années pour les deux graphiques
        for ax in [ax_events, ax_anomalies]:
            ax.set_xticks(all_years[::2])  # Afficher une année sur deux pour plus de lisibilité
            ax.set_xticklabels(all_years[::2], rotation=45, ha='right', fontsize=10, fontweight='bold')
            ax.set_xlim(all_years[0] - 0.8, all_years[-1] + 0.8)
            
            # Style des bordures amélioré
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color('#85929E')
            ax.spines['left'].set_linewidth(1.5)
            ax.spines['bottom'].set_color('#85929E')
            ax.spines['bottom'].set_linewidth(1.5)
        
        # Ajouter le label des années seulement sur le graphique du bas de chaque phase
        ax_anomalies.set_xlabel('Année', fontsize=15, fontweight='bold', color='#2C3E50')
        
        # Statistiques pour affichage (uniquement pour les années avec des données)
        if not actual_data.empty:
            total_events = actual_data['nombre_evenements'].sum()
            max_events_year = actual_data.loc[actual_data['nombre_evenements'].idxmax(), 'year']
            max_events_count = actual_data['nombre_evenements'].max()
            min_anomaly = actual_data['anomalie_moyenne'].min()
            max_anomaly = actual_data['anomalie_moyenne'].max()
            
            # === STATISTIQUES ET LÉGENDES PLACÉES AU-DESSUS DU GRAPHIQUE ===
            
            # Statistiques pour événements (au-dessus du graphique, côté gauche)
            stats_text = (f'Total: {total_events} événements | '
                         f'Maximum: {max_events_count} ({max_events_year}) | '
                         f'Moyenne: {mean_events:.1f} événements/an')
            
            # Placer les statistiques au-dessus du graphique en utilisant les coordonnées de l'axe
            ax_events.text(0.02, 1.12, stats_text, transform=ax_events.transAxes,
                          fontsize=12, fontweight='bold', color='#2C3E50',
                          bbox=dict(boxstyle='round,pad=0.6', facecolor='white', 
                                   alpha=0.95, edgecolor='#85929E', linewidth=1.5),
                          verticalalignment='bottom')
            
            # Légende pour événements (au-dessus du graphique, côté droit)
            legend_events = ax_events.legend(loc='center', bbox_to_anchor=(0.85, 1.08), 
                                           frameon=True, fancybox=True, shadow=True,
                                           facecolor='white', edgecolor='#85929E', 
                                           fontsize=12, framealpha=0.95, ncol=2)
            
            # Statistiques pour anomalies (au-dessus du graphique, côté gauche)
            anomaly_stats_text = (f'Anomalie min: {min_anomaly:.2f} | '
                                 f'Anomalie max: {max_anomaly:.2f} | '
                                 f'Moyenne: {mean_anomaly:.2f}')
            
            # Placer les statistiques au-dessus du graphique en utilisant les coordonnées de l'axe
            ax_anomalies.text(0.02, 1.12, anomaly_stats_text, transform=ax_anomalies.transAxes,
                             fontsize=12, fontweight='bold', color='#2C3E50',
                             bbox=dict(boxstyle='round,pad=0.6', facecolor='white', 
                                      alpha=0.95, edgecolor='#85929E', linewidth=1.5),
                             verticalalignment='bottom')
            
            # Légende pour anomalies (au-dessus du graphique, côté droit)
            legend_anomalies = ax_anomalies.legend(loc='center', bbox_to_anchor=(0.85, 1.08), 
                                                 frameon=True, fancybox=True, shadow=True,
                                                 facecolor='white', edgecolor='#85929E', 
                                                 fontsize=12, framealpha=0.95, ncol=2)
        
        # Ajustement des limites des axes (pas besoin d'espace supplémentaire maintenant)
        if not complete_data['nombre_evenements'].empty:
            y_max_events = complete_data['nombre_evenements'].max()
            if y_max_events > 0:
                ax_events.set_ylim(0, y_max_events + 1)
        
        if not complete_data['anomalie_moyenne'].empty:
            y_max_anomaly = complete_data['anomalie_moyenne'].max()
            y_min_anomaly = complete_data['anomalie_moyenne'].min()
            if y_max_anomaly > 0:
                margin = max(0.4, (y_max_anomaly - y_min_anomaly) * 0.1)
                ax_anomalies.set_ylim(min(y_min_anomaly - margin, -0.3), 
                                     y_max_anomaly + margin + 0.3)
    
    # Ajustement de l'espacement avec plus d'espace entre titre et graphiques
    plt.tight_layout()
    plt.subplots_adjust(top=0.88, hspace=1.2, bottom=0.06, left=0.08, right=0.96)
    
    return fig

def save_visualization(fig, output_dir):
    """
    Sauvegarde la visualisation dans le dossier spécifié.
    
    Args:
        fig (matplotlib.figure.Figure): Figure à sauvegarder
        output_dir (Path): Dossier de destination
    """
    # Créer le dossier s'il n'existe pas
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Chemin du fichier de sortie
    output_path = output_dir / "02_distribution_annuelle_phases.png"
    
    # Sauvegarder avec haute résolution
    fig.savefig(output_path, dpi=300, bbox_inches='tight', 
               facecolor='white', edgecolor='none')
    
    print(f"✅ Visualisation sauvegardée: {output_path}")
    
    return output_path

def generate_summary_statistics(annual_stats):
    """
    Génère des statistiques résumées pour le rapport.
    
    Args:
        annual_stats (pandas.DataFrame): Statistiques annuelles
        
    Returns:
        dict: Dictionnaire des statistiques résumées
    """
    summary = {}
    
    phases = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']
    phase_names = {
        'Phase_1_debut': 'Début (Mai-Juin)',
        'Phase_2_pleine': 'Pleine (Juillet-Août)',
        'Phase_3_fin': 'Fin (Septembre-Octobre)'
    }
    
    for phase in phases:
        phase_data = annual_stats[annual_stats['phase'] == phase]
        
        if not phase_data.empty:
            summary[phase_names[phase]] = {
                'nombre_annees': len(phase_data),
                'total_evenements': phase_data['nombre_evenements'].sum(),
                'moyenne_evenements_par_an': phase_data['nombre_evenements'].mean(),
                'anomalie_moyenne': phase_data['anomalie_moyenne'].mean(),
                'anomalie_max': phase_data['anomalie_max'].max(),
                'annee_plus_active': phase_data.loc[phase_data['nombre_evenements'].idxmax(), 'year'],
                'max_evenements_annee': phase_data['nombre_evenements'].max()
            }
    
    return summary

def main():
    """
    Fonction principale du script.
    """
    print("=" * 80)
    print("🌧️  GÉNÉRATION DE LA DISTRIBUTION ANNUELLE PAR PHASES")
    print("=" * 80)
    
    try:
        # 1. Chargement des données
        print("\n📊 Chargement des données...")
        df = load_extreme_events_data()
        
        # 2. Calcul des statistiques annuelles
        print("\n📈 Calcul des statistiques annuelles...")
        annual_stats = calculate_annual_statistics(df)
        print(f"   Statistiques calculées pour {len(annual_stats)} combinaisons année-phase")
        
        # 3. Création de la visualisation
        print("\n🎨 Création de la visualisation...")
        fig = create_phase_distribution_plot(annual_stats)
        
        # 4. Sauvegarde
        print("\n💾 Sauvegarde de la visualisation...")
        output_dir = Path("outputs/visualizations/Distribution")
        output_path = save_visualization(fig, output_dir)
        
        # 5. Génération des statistiques résumées
        print("\n📋 Génération des statistiques résumées...")
        summary = generate_summary_statistics(annual_stats)
        
        # Affichage du résumé
        print("\n" + "=" * 60)
        print("📊 RÉSUMÉ DES STATISTIQUES PAR PHASE")
        print("=" * 60)
        
        for phase_name, stats in summary.items():
            print(f"\n🔹 {phase_name}:")
            print(f"   • Période d'analyse: {stats['nombre_annees']} années")
            print(f"   • Total d'événements: {stats['total_evenements']}")
            print(f"   • Moyenne par an: {stats['moyenne_evenements_par_an']:.1f} événements")
            print(f"   • Anomalie moyenne: {stats['anomalie_moyenne']:.2f}")
            print(f"   • Anomalie maximale: {stats['anomalie_max']:.2f}")
            print(f"   • Année la plus active: {stats['annee_plus_active']} "
                  f"({stats['max_evenements_annee']} événements)")
        
        print("\n" + "=" * 80)
        print("✅ ANALYSE TERMINÉE AVEC SUCCÈS!")
        print(f"📁 Fichier généré: {output_path}")
        print(f"📊 Visualisation prête pour présentation")
        print("=" * 80)
        
        # Fermer la figure pour libérer la mémoire
        plt.close(fig)
        
    except FileNotFoundError as e:
        print(f"❌ Erreur: {e}")
        print("   Veuillez vous assurer que le fichier de données existe.")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()