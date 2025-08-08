# src/visualization/detection_plots.py
"""
Module de visualisation pour les événements de précipitations extrêmes.
Version améliorée intégrée avec les nouvelles fonctionnalités du projet.
"""

import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, List
import warnings
import sys
from pathlib import Path
from datetime import datetime

# Imports avec gestion robuste des erreurs
try:
    from ..config.settings import (
        PHASE_COLORS, REGION_COLORS, CLIMATE_COLORS, PLOT_PARAMS, 
        get_output_path, VISUALIZATION_FILENAMES, RAINFALL_PHASES,
        PROJECT_INFO
    )
    from ..utils.geographic_references import SenegalGeography
    from ..utils.season_classifier import get_phase_from_month
except ImportError:
    try:
        from src.config.settings import (
            PHASE_COLORS, REGION_COLORS, CLIMATE_COLORS, PLOT_PARAMS,
            get_output_path, VISUALIZATION_FILENAMES, RAINFALL_PHASES,
            PROJECT_INFO
        )
        from src.utils.geographic_references import SenegalGeography
        from src.utils.season_classifier import get_phase_from_month
    except ImportError:
        # Configuration de fallback
        PHASE_COLORS = {
            'Phase_1_debut': '#87CEEB',
            'Phase_2_pleine': '#1E90FF', 
            'Phase_3_fin': '#4682B4',
            'Hors_saison': '#D3D3D3'
        }
        REGION_COLORS = {'Default': '#808080'}
        CLIMATE_COLORS = {'Default': '#808080'}
        PLOT_PARAMS = {
            'figure_size': (15, 8),
            'figure_size_large': (20, 12),
            'dpi': 300,
            'style': 'seaborn-v0_8-whitegrid',
            'font_size': 12
        }
        RAINFALL_PHASES = {
            'Phase_1_debut': {'months': [5, 6], 'description': 'Début de saison'},
            'Phase_2_pleine': {'months': [7, 8], 'description': 'Pleine saison'},
            'Phase_3_fin': {'months': [9, 10], 'description': 'Fin de saison'},
            'Hors_saison': {'months': [11, 12, 1, 2, 3, 4], 'description': 'Hors saison'}
        }
        PROJECT_INFO = {'title': 'Analyse des précipitations extrêmes au Sénégal'}
        
        def get_output_path(key):
            return f"outputs/visualizations/{key}.png"
        
        def get_phase_from_month(month):
            if month in [5, 6]: return 'Phase_1_debut'
            elif month in [7, 8]: return 'Phase_2_pleine'
            elif month in [9, 10]: return 'Phase_3_fin'
            else: return 'Hors_saison'
        
        class SenegalGeography:
            @staticmethod
            def identify_region(lat, lon): return "Région indéterminée"

warnings.filterwarnings('ignore')


class EnhancedDetectionVisualizer:
    """
    Visualiseur avancé pour les événements de précipitations extrêmes avec nouvelles fonctionnalités.
    """
    
    def __init__(self):
        """Initialise le visualiseur avec configuration avancée."""
        self.geo = SenegalGeography()
        self.setup_style()
        
        # Statistiques pour les visualisations
        self.stats = {}
        
        print("🎨 EnhancedDetectionVisualizer initialisé")
        print(f"   Style: {PLOT_PARAMS.get('style', 'default')}")
        print(f"   Résolution: {PLOT_PARAMS.get('dpi', 300)} DPI")
    
    def setup_style(self):
        """Configure le style des visualisations."""
        try:
            plt.style.use(PLOT_PARAMS.get('style', 'seaborn-v0_8-whitegrid'))
        except:
            plt.style.use('default')
        
        # Configuration globale
        plt.rcParams.update({
            'font.size': PLOT_PARAMS.get('font_size', 12),
            'axes.titlesize': PLOT_PARAMS.get('title_size', 16),
            'axes.labelsize': PLOT_PARAMS.get('label_size', 14),
            'legend.fontsize': PLOT_PARAMS.get('legend_size', 11),
            'figure.titlesize': PLOT_PARAMS.get('title_size', 16),
            'lines.linewidth': PLOT_PARAMS.get('line_width', 2.5),
            'grid.alpha': PLOT_PARAMS.get('grid_alpha', 0.3)
        })
    
    def create_phase_distribution_plot(self, df_events: pd.DataFrame) -> str:
        """
        Crée la visualisation de distribution par phases de saison des pluies.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("🌧️  Création: Distribution par phases de saison des pluies")
        
        # Ajouter la colonne phase si elle n'existe pas
        if 'phase' not in df_events.columns:
            df_events['phase'] = df_events['month'].apply(get_phase_from_month)
        
        fig, axes = plt.subplots(2, 2, figsize=PLOT_PARAMS['figure_size_large'])
        fig.suptitle(f'{PROJECT_INFO["title"]}\nDistribution par phases de la saison des pluies', 
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold', y=0.98)
        
        # 1. Distribution générale par phases (camembert)
        phase_counts = df_events['phase'].value_counts()
        colors = [PHASE_COLORS.get(phase, '#808080') for phase in phase_counts.index]
        
        # Labels avec pourcentages et descriptions
        labels = []
        for phase in phase_counts.index:
            phase_info = RAINFALL_PHASES.get(phase, {})
            description = phase_info.get('description', phase)
            months = phase_info.get('months', [])
            labels.append(f"{description}\n({phase_counts[phase]} événements)")
        
        wedges, texts, autotexts = axes[0,0].pie(
            phase_counts.values, labels=labels, colors=colors,
            autopct='%1.1f%%', startangle=90, textprops={'fontsize': 10}
        )
        axes[0,0].set_title('Répartition générale par phases', fontweight='bold', pad=20)
        
        # 2. Évolution mensuelle avec phases
        monthly_phase = df_events.groupby(['month', 'phase']).size().unstack(fill_value=0)
        
        months = range(1, 13)
        bottom = np.zeros(12)
        
        for phase in ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin', 'Hors_saison']:
            if phase in monthly_phase.columns:
                values = [monthly_phase.loc[m, phase] if m in monthly_phase.index else 0 for m in months]
                axes[0,1].bar(months, values, bottom=bottom, 
                            color=PHASE_COLORS.get(phase, '#808080'),
                            label=RAINFALL_PHASES[phase]['description'], alpha=0.8)
                bottom += values
        
        axes[0,1].set_title('Distribution mensuelle par phases', fontweight='bold')
        axes[0,1].set_xlabel('Mois')
        axes[0,1].set_ylabel('Nombre d\'événements')
        axes[0,1].legend(loc='upper right', fontsize=9)
        axes[0,1].grid(True, alpha=0.3)
        axes[0,1].set_xticks(months)
        
        # 3. Statistiques d'intensité par phase
        phase_stats = df_events.groupby('phase').agg({
            'max_precip': ['mean', 'std', 'count'],
            'coverage_percent': 'mean',
            'max_anomaly': 'mean'
        }).round(2)
        
        phases_order = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin', 'Hors_saison']
        phases_in_data = [p for p in phases_order if p in phase_stats.index]
        
        x_pos = np.arange(len(phases_in_data))
        mean_precip = [phase_stats.loc[p, ('max_precip', 'mean')] for p in phases_in_data]
        std_precip = [phase_stats.loc[p, ('max_precip', 'std')] for p in phases_in_data]
        colors_bars = [PHASE_COLORS.get(p, '#808080') for p in phases_in_data]
        
        bars = axes[1,0].bar(x_pos, mean_precip, yerr=std_precip, 
                           color=colors_bars, alpha=0.8, capsize=5)
        
        axes[1,0].set_title('Précipitation moyenne par phase', fontweight='bold')
        axes[1,0].set_ylabel('Précipitation (mm)')
        axes[1,0].set_xticks(x_pos)
        axes[1,0].set_xticklabels([RAINFALL_PHASES[p]['description'] for p in phases_in_data], 
                                rotation=45, ha='right')
        axes[1,0].grid(True, alpha=0.3)
        
        # Ajouter les valeurs sur les barres
        for bar, val in zip(bars, mean_precip):
            height = bar.get_height()
            axes[1,0].text(bar.get_x() + bar.get_width()/2., height + height*0.05,
                         f'{val:.1f}', ha='center', va='bottom', fontsize=9)
        
        # 4. Box plot des anomalies par phase
        phase_data = []
        phase_labels = []
        for phase in phases_in_data:
            phase_anomalies = df_events[df_events['phase'] == phase]['max_anomaly']
            if len(phase_anomalies) > 0:
                phase_data.append(phase_anomalies)
                phase_labels.append(RAINFALL_PHASES[phase]['description'])
        
        if phase_data:
            bp = axes[1,1].boxplot(phase_data, labels=phase_labels, patch_artist=True)
            
            # Colorer les box plots
            for patch, phase in zip(bp['boxes'], phases_in_data[:len(bp['boxes'])]):
                patch.set_facecolor(PHASE_COLORS.get(phase, '#808080'))
                patch.set_alpha(0.7)
        
        axes[1,1].set_title('Distribution des anomalies par phase', fontweight='bold')
        axes[1,1].set_ylabel('Anomalie (σ)')
        axes[1,1].tick_params(axis='x', rotation=45)
        axes[1,1].grid(True, alpha=0.3)
        axes[1,1].axhline(y=2, color='red', linestyle='--', alpha=0.7, label='Seuil détection')
        axes[1,1].legend()
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('phase_distribution')
        
        # Sauvegarder les statistiques
        self.stats['phase_distribution'] = {
            'phase_counts': phase_counts.to_dict(),
            'phase_stats': phase_stats.to_dict(),
            'total_events': len(df_events)
        }
        
        return output_path
    
    
    def create_geographic_analysis_plot(self, df_events: pd.DataFrame) -> str:
        """
        Crée la visualisation d'analyse géographique simplifiée avec seulement 2 graphiques.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("🗺️  Création: Analyse géographique simplifiée (2 graphiques)")
        
        # Créer une figure avec 1 ligne et 2 colonnes
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        fig.suptitle(f'{PROJECT_INFO["title"]}\nAnalyse géographique des événements extrêmes', 
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold', y=0.95)
        
        # 1. Distribution par régions
        if 'centroid_region' in df_events.columns:
            region_counts = df_events['centroid_region'].value_counts().head(10)
            colors_regions = [REGION_COLORS.get(region, '#808080') for region in region_counts.index]
            
            bars = axes[0].bar(range(len(region_counts)), region_counts.values, 
                            color=colors_regions, alpha=0.8)
            axes[0].set_xticks(range(len(region_counts)))
            axes[0].set_xticklabels(region_counts.index, fontsize=10, rotation=45, ha='right')
            axes[0].set_ylabel('Nombre d\'événements', fontsize=12)
            axes[0].set_title('Distribution par régions\n(Top 10)', fontweight='bold', fontsize=14)
            axes[0].grid(True, alpha=0.3, axis='y')
            
            # Ajouter les valeurs
            for i, (bar, count) in enumerate(zip(bars, region_counts.values)):
                axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() + bar.get_height()*0.02,
                            f'{count}', ha='center', va='bottom', fontsize=10)
        else:
            # Afficher un message si la colonne n'existe pas
            axes[0].text(0.5, 0.5, 'Colonne \'centroid_region\'\nmanquante', 
                        ha='center', va='center', transform=axes[0].transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
            axes[0].set_title('Distribution par régions\n(Top 10)', fontweight='bold', fontsize=14)
        
        # 2. Distribution par zones climatiques - VERSION CORRIGÉE
        if 'centroid_climate_zone' in df_events.columns:
            climate_counts = df_events['centroid_climate_zone'].value_counts()
            
            if not climate_counts.empty:
                # Définir une palette de couleurs pour les zones climatiques
                climate_color_palette = [
                    '#FF6B6B',  # Rouge corail
                    '#4ECDC4',  # Turquoise
                    '#45B7D1',  # Bleu ciel
                    '#96CEB4',  # Vert menthe
                    '#FECA57',  # Jaune orangé
                    '#FF9FF3',  # Rose
                    '#54A0FF',  # Bleu
                    '#5F27CD',  # Violet
                    '#00D2D3',  # Cyan
                    '#FF9F43'   # Orange
                ]
                
                # Assigner des couleurs aux zones climatiques
                colors_climate = []
                for i, zone in enumerate(climate_counts.index):
                    if zone in CLIMATE_COLORS and CLIMATE_COLORS[zone] != '#808080':
                        # Utiliser la couleur définie si elle existe et n'est pas par défaut
                        colors_climate.append(CLIMATE_COLORS[zone])
                    else:
                        # Utiliser la palette cyclique
                        colors_climate.append(climate_color_palette[i % len(climate_color_palette)])
                
                wedges, texts, autotexts = axes[1].pie(
                    climate_counts.values, 
                    labels=climate_counts.index,
                    colors=colors_climate, 
                    autopct='%1.1f%%', 
                    startangle=90,
                    textprops={'fontsize': 11}
                )
                
                # Améliorer la lisibilité des labels
                for autotext in autotexts:
                    autotext.set_color('white')
                    autotext.set_fontweight('bold')
                    autotext.set_fontsize(10)
                
                axes[1].set_title('Répartition par zones climatiques', fontweight='bold', fontsize=14)
            else:
                axes[1].text(0.5, 0.5, 'Aucune donnée\nde zone climatique', 
                            ha='center', va='center', transform=axes[1].transAxes,
                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                axes[1].set_title('Répartition par zones climatiques', fontweight='bold', fontsize=14)
        else:
            # Afficher un message si la colonne n'existe pas
            axes[1].text(0.5, 0.5, 'Colonne \'centroid_climate_zone\'\nmanquante', 
                        ha='center', va='center', transform=axes[1].transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
            axes[1].set_title('Répartition par zones climatiques', fontweight='bold', fontsize=14)
        
        # Ajuster l'espacement
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('regional_analysis')
        
        return output_path

    def create_temporal_evolution_plot(self, df_events: pd.DataFrame) -> str:
        """
        Crée la visualisation d'évolution temporelle simplifiée avec seulement 2 graphiques.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("📅 Création: Évolution temporelle simplifiée (2 graphiques)")
        
        # Créer une figure avec 1 ligne et 2 colonnes
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        fig.suptitle(f'{PROJECT_INFO["title"]}\nÉvolution temporelle des événements extrêmes', 
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold', y=0.95)
        
        # 1. Évolution annuelle par phases
        if 'phase' not in df_events.columns:
            df_events['phase'] = df_events['month'].apply(get_phase_from_month)
        
        try:
            yearly_phase = df_events.groupby(['year', 'phase']).size().unstack(fill_value=0)
            
            for phase in ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']:
                if phase in yearly_phase.columns:
                    axes[0].plot(yearly_phase.index, yearly_phase[phase], 
                                marker='o', label=RAINFALL_PHASES[phase]['description'],
                                color=PHASE_COLORS[phase], linewidth=2.5, markersize=5)
            
            axes[0].set_title('Évolution annuelle par phases', fontweight='bold', fontsize=14)
            axes[0].set_xlabel('Année', fontsize=12)
            axes[0].set_ylabel('Nombre d\'événements', fontsize=12)
            axes[0].legend(fontsize=11)
            axes[0].grid(True, alpha=0.3)
            
        except Exception as e:
            print(f"❌ Erreur évolution annuelle: {e}")
            axes[0].text(0.5, 0.5, 'Erreur dans l\'évolution\nannuelle par phases', 
                        ha='center', va='center', transform=axes[0].transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            axes[0].set_title('Évolution annuelle par phases', fontweight='bold', fontsize=14)
        
        # 2. Tendances d'intensité dans le temps - VERSION CORRIGÉE
        try:
            # Créer une copie propre pour éviter les problèmes d'attributs
            intensity_cols = ['year', 'max_precip', 'coverage_percent', 'max_anomaly']
            missing_cols = [col for col in intensity_cols if col not in df_events.columns]
            
            if not missing_cols:
                df_intensity = df_events[intensity_cols].copy().dropna()
                
                if not df_intensity.empty:
                    yearly_intensity = (df_intensity.groupby('year')
                                    .agg({
                                        'max_precip': ['mean', 'max'],
                                        'coverage_percent': 'mean',
                                        'max_anomaly': 'mean'
                                    })
                                    .reset_index())
                    
                    # Aplatir les colonnes multi-niveaux
                    yearly_intensity.columns = ['year', 'max_precip_mean', 'max_precip_max', 
                                            'coverage_percent_mean', 'max_anomaly_mean']
                    yearly_intensity.set_index('year', inplace=True)
                    
                    ax2 = axes[1]
                    ax2_twin = ax2.twinx()
                    
                    line1 = ax2.plot(yearly_intensity.index, yearly_intensity['max_precip_mean'],
                                    color='blue', marker='o', label='Précipitation moyenne', 
                                    linewidth=2.5, markersize=5)
                    line2 = ax2_twin.plot(yearly_intensity.index, yearly_intensity['coverage_percent_mean'],
                                        color='red', marker='s', label='Couverture moyenne', 
                                        linewidth=2.5, markersize=5)
                    
                    ax2.set_xlabel('Année', fontsize=12)
                    ax2.set_ylabel('Précipitation (mm)', color='blue', fontsize=12)
                    ax2_twin.set_ylabel('Couverture (%)', color='red', fontsize=12)
                    ax2.set_title('Tendances d\'intensité', fontweight='bold', fontsize=14)
                    ax2.grid(True, alpha=0.3)
                    
                    # Légende combinée
                    lines = line1 + line2
                    labels = [l.get_label() for l in lines]
                    ax2.legend(lines, labels, loc='upper left', fontsize=11)
                else:
                    axes[1].text(0.5, 0.5, 'Données insuffisantes\npour l\'analyse d\'intensité', 
                                ha='center', va='center', transform=axes[1].transAxes,
                                fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                    axes[1].set_title('Tendances d\'intensité', fontweight='bold', fontsize=14)
            else:
                axes[1].text(0.5, 0.5, f'Colonnes manquantes:\n{", ".join(missing_cols)}', 
                            ha='center', va='center', transform=axes[1].transAxes,
                            fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
                axes[1].set_title('Tendances d\'intensité', fontweight='bold', fontsize=14)
        except Exception as e:
            print(f"❌ Erreur lors de l'analyse d'intensité: {e}")
            axes[1].text(0.5, 0.5, f'Erreur lors de l\'analyse:\n{str(e)[:50]}...', 
                        ha='center', va='center', transform=axes[1].transAxes,
                        fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            axes[1].set_title('Tendances d\'intensité', fontweight='bold', fontsize=14)
        
        # Ajuster l'espacement
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('temporal_evolution')
        
        return output_path

    def create_intensity_coverage_analysis(self, df_events: pd.DataFrame) -> str:
        """
        Crée l'analyse détaillée intensité-couverture.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("⚡ Création: Analyse intensité-couverture")
        
        fig, axes = plt.subplots(2, 2, figsize=PLOT_PARAMS['figure_size_large'])
        fig.suptitle(f'{PROJECT_INFO["title"]}\nAnalyse intensité-couverture des événements extrêmes', 
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold', y=0.98)
        
        # 1. Scatter plot principal avec phases
        if 'phase' not in df_events.columns:
            df_events['phase'] = df_events['month'].apply(get_phase_from_month)
        
        for phase in PHASE_COLORS.keys():
            if phase in df_events['phase'].values:
                phase_data = df_events[df_events['phase'] == phase]
                axes[0,0].scatter(phase_data['coverage_percent'], phase_data['max_precip'],
                                color=PHASE_COLORS[phase], label=RAINFALL_PHASES[phase]['description'],
                                alpha=0.7, s=50, edgecolors='black', linewidth=0.5)
        
        axes[0,0].set_xlabel('Couverture spatiale (%)')
        axes[0,0].set_ylabel('Précipitation maximale (mm)')
        axes[0,0].set_title('Relation intensité-couverture\npar phases', fontweight='bold')
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Distribution des intensités
        axes[0,1].hist(df_events['max_precip'], bins=30, alpha=0.7, 
                      color='skyblue', edgecolor='black', linewidth=0.5, density=True)
        
        # Statistiques
        mean_precip = df_events['max_precip'].mean()
        median_precip = df_events['max_precip'].median()
        
        axes[0,1].axvline(x=mean_precip, color='red', linestyle='--', 
                         label=f'Moyenne: {mean_precip:.1f} mm')
        axes[0,1].axvline(x=median_precip, color='orange', linestyle='--', 
                         label=f'Médiane: {median_precip:.1f} mm')
        
        axes[0,1].set_title('Distribution des précipitations', fontweight='bold')
        axes[0,1].set_xlabel('Précipitation maximale (mm)')
        axes[0,1].set_ylabel('Densité de probabilité')
        axes[0,1].legend()
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Distribution des couvertures
        axes[1,0].hist(df_events['coverage_percent'], bins=30, alpha=0.7, 
                      color='lightcoral', edgecolor='black', linewidth=0.5, density=True)
        
        mean_coverage = df_events['coverage_percent'].mean()
        median_coverage = df_events['coverage_percent'].median()
        
        axes[1,0].axvline(x=mean_coverage, color='red', linestyle='--', 
                         label=f'Moyenne: {mean_coverage:.1f}%')
        axes[1,0].axvline(x=median_coverage, color='orange', linestyle='--', 
                         label=f'Médiane: {median_coverage:.1f}%')
        
        axes[1,0].set_title('Distribution des couvertures', fontweight='bold')
        axes[1,0].set_xlabel('Couverture spatiale (%)')
        axes[1,0].set_ylabel('Densité de probabilité')
        axes[1,0].legend()
        axes[1,0].grid(True, alpha=0.3)
        
        # 4. Matrice de corrélation des métriques
        numeric_cols = ['max_precip', 'coverage_percent', 'max_anomaly']
        if 'lat_extent_km' in df_events.columns:
            numeric_cols.extend(['lat_extent_km', 'lon_extent_km'])
        
        correlation_data = df_events[numeric_cols].corr()
        
        im = axes[1,1].imshow(correlation_data, cmap='RdBu_r', vmin=-1, vmax=1)
        
        # Ajouter les valeurs de corrélation
        for i in range(len(correlation_data)):
            for j in range(len(correlation_data)):
                text = axes[1,1].text(j, i, f'{correlation_data.iloc[i, j]:.2f}',
                                    ha="center", va="center", color="black", fontsize=10)
        
        axes[1,1].set_xticks(range(len(correlation_data)))
        axes[1,1].set_yticks(range(len(correlation_data)))
        axes[1,1].set_xticklabels(correlation_data.columns, rotation=45, ha='right')
        axes[1,1].set_yticklabels(correlation_data.columns)
        axes[1,1].set_title('Corrélations entre métriques', fontweight='bold')
        
        # Colorbar
        cbar = plt.colorbar(im, ax=axes[1,1], shrink=0.8)
        cbar.set_label('Coefficient de corrélation')
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('intensity_coverage')
        
        return output_path
    
    def create_validation_plots(self, df_events: pd.DataFrame) -> str:
        """
        Crée les graphiques de validation des résultats.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("🔍 Création: Validation des résultats")
        
        fig, axes = plt.subplots(2, 2, figsize=PLOT_PARAMS['figure_size_large'])
        fig.suptitle(f'{PROJECT_INFO["title"]}\nValidation et contrôle qualité', 
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold', y=0.98)
        
        # 1. Validation des seuils de détection
        axes[0,0].hist(df_events['max_anomaly'], bins=30, alpha=0.7, 
                      color='orange', edgecolor='black', linewidth=0.5)
        axes[0,0].axvline(x=2.0, color='red', linestyle='--', linewidth=2, 
                         label='Seuil détection (2σ)')
        axes[0,0].set_title('Validation seuil d\'anomalie', fontweight='bold')
        axes[0,0].set_xlabel('Anomalie maximale (σ)')
        axes[0,0].set_ylabel('Nombre d\'événements')
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # Statistiques
        below_threshold = (df_events['max_anomaly'] < 2.0).sum()
        if below_threshold > 0:
            axes[0,0].text(0.05, 0.95, f'⚠️ {below_threshold} événements < 2σ', 
                          transform=axes[0,0].transAxes, bbox=dict(boxstyle='round', facecolor='yellow'))
        
        # 2. Cohérence saisonnière
        monthly_distribution = df_events['month'].value_counts().sort_index()
        rainy_season_months = [5, 6, 7, 8, 9, 10]
        
        colors_validation = ['lightgreen' if m in rainy_season_months else 'lightcoral' 
                           for m in monthly_distribution.index]
        
        bars = axes[0,1].bar(monthly_distribution.index, monthly_distribution.values,
                           color=colors_validation, alpha=0.8, edgecolor='black', linewidth=0.5)
        
        axes[0,1].set_title('Cohérence saisonnière', fontweight='bold')
        axes[0,1].set_xlabel('Mois')
        axes[0,1].set_ylabel('Nombre d\'événements')
        axes[0,1].grid(True, alpha=0.3)
        
        # Calculer le pourcentage en saison des pluies
        rainy_events = df_events[df_events['month'].isin(rainy_season_months)]
        rainy_pct = len(rainy_events) / len(df_events) * 100
        axes[0,1].text(0.05, 0.95, f'Saison des pluies: {rainy_pct:.1f}%', 
                      transform=axes[0,1].transAxes, 
                      bbox=dict(boxstyle='round', facecolor='lightgreen'))
        
        # 3. Distribution géographique
        if 'centroid_lat' in df_events.columns and 'centroid_lon' in df_events.columns:
            # Vérifier que les coordonnées sont dans les limites du Sénégal
            senegal_bounds = self.geo.SENEGAL_BOUNDS
            
            valid_coords = (
                (df_events['centroid_lat'] >= senegal_bounds['lat_min']) &
                (df_events['centroid_lat'] <= senegal_bounds['lat_max']) &
                (df_events['centroid_lon'] >= senegal_bounds['lon_min']) &
                (df_events['centroid_lon'] <= senegal_bounds['lon_max'])
            )
            
            # Scatter plot des coordonnées
            axes[1,0].scatter(df_events.loc[valid_coords, 'centroid_lon'], 
                            df_events.loc[valid_coords, 'centroid_lat'],
                            c='green', alpha=0.6, s=30, label='Coordonnées valides')
            
            if (~valid_coords).any():
                axes[1,0].scatter(df_events.loc[~valid_coords, 'centroid_lon'], 
                                df_events.loc[~valid_coords, 'centroid_lat'],
                                c='red', alpha=0.6, s=30, label='Coordonnées invalides')
            
            # Limites du Sénégal
            axes[1,0].axhspan(senegal_bounds['lat_min'], senegal_bounds['lat_max'], 
                            alpha=0.1, color='green', label='Limites Sénégal')
            axes[1,0].axvspan(senegal_bounds['lon_min'], senegal_bounds['lon_max'], 
                            alpha=0.1, color='green')
            
            axes[1,0].set_title('Validation géographique', fontweight='bold')
            axes[1,0].set_xlabel('Longitude (°)')
            axes[1,0].set_ylabel('Latitude (°)')
            axes[1,0].legend()
            axes[1,0].grid(True, alpha=0.3)
            
            # Statistiques de validation
            valid_pct = valid_coords.sum() / len(df_events) * 100
            axes[1,0].text(0.05, 0.95, f'Valides: {valid_pct:.1f}%', 
                          transform=axes[1,0].transAxes,
                          bbox=dict(boxstyle='round', facecolor='lightgreen'))
        
        # 4. Métriques de qualité globale
        quality_metrics = self._calculate_quality_metrics(df_events)
        
        metrics_names = list(quality_metrics.keys())
        metrics_values = list(quality_metrics.values())
        colors_quality = ['green' if v >= 0.8 else 'orange' if v >= 0.6 else 'red' 
                         for v in metrics_values]
        
        bars = axes[1,1].barh(range(len(metrics_names)), metrics_values,
                            color=colors_quality, alpha=0.8)
        
        axes[1,1].set_yticks(range(len(metrics_names)))
        axes[1,1].set_yticklabels(metrics_names, fontsize=10)
        axes[1,1].set_xlabel('Score de qualité')
        axes[1,1].set_title('Métriques de qualité', fontweight='bold')
        axes[1,1].set_xlim(0, 1)
        axes[1,1].grid(True, alpha=0.3, axis='x')
        
        # Ajouter les valeurs
        for i, (bar, val) in enumerate(zip(bars, metrics_values)):
            axes[1,1].text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2,
                         f'{val:.2f}', ha='left', va='center', fontsize=9)
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('validation_plots')
        
        return output_path
    
    def create_executive_summary(self, df_events: pd.DataFrame) -> str:
        """
        Crée un résumé exécutif visuel - VERSION CORRIGÉE.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("📊 Création: Résumé exécutif")
        
        try:
            fig = plt.figure(figsize=(20, 14))
            gs = fig.add_gridspec(3, 4, hspace=0.3, wspace=0.3)
            
            # Titre principal
            fig.suptitle(f'{PROJECT_INFO["title"]}\nRésumé Exécutif - Analyse des Événements Extrêmes', 
                        fontsize=20, fontweight='bold', y=0.95)
            
            # 1. Statistiques clés (grande section)
            ax_stats = fig.add_subplot(gs[0, :2])
            self._create_key_statistics_panel(ax_stats, df_events)
            
            # 2. Distribution temporelle
            ax_temporal = fig.add_subplot(gs[0, 2:])
            try:
                if 'phase' not in df_events.columns:
                    df_events['phase'] = df_events['month'].apply(get_phase_from_month)
                
                phase_counts = df_events['phase'].value_counts()
                if not phase_counts.empty:
                    colors = [PHASE_COLORS.get(phase, '#808080') for phase in phase_counts.index]
                    ax_temporal.pie(phase_counts.values, 
                                labels=[RAINFALL_PHASES.get(p, {}).get('description', p) for p in phase_counts.index],
                                colors=colors, autopct='%1.1f%%')
                    ax_temporal.set_title('Distribution par Phases', fontweight='bold', fontsize=14)
                else:
                    ax_temporal.text(0.5, 0.5, 'Aucune donnée\nde phase disponible', 
                                ha='center', va='center', transform=ax_temporal.transAxes,
                                fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                    ax_temporal.set_title('Distribution par Phases', fontweight='bold', fontsize=14)
            except Exception as e:
                print(f"❌ Erreur distribution temporelle: {e}")
                ax_temporal.text(0.5, 0.5, 'Erreur dans la\ndistribution temporelle', 
                            ha='center', va='center', transform=ax_temporal.transAxes,
                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                ax_temporal.set_title('Distribution par Phases', fontweight='bold', fontsize=14)
            
            # 3. Top 5 événements
            ax_top = fig.add_subplot(gs[1, :2])
            self._create_top_events_table(ax_top, df_events)
            
            # 4. Tendances temporelles
            ax_trends = fig.add_subplot(gs[1, 2:])
            try:
                if 'year' in df_events.columns and not df_events.empty:
                    yearly_counts = df_events.groupby('year').size()
                    if not yearly_counts.empty:
                        ax_trends.plot(yearly_counts.index, yearly_counts.values, 
                                    marker='o', linewidth=3, markersize=6, color='blue')
                        ax_trends.set_title('Évolution Temporelle', fontweight='bold', fontsize=14)
                        ax_trends.set_ylabel('Événements/an')
                        ax_trends.grid(True, alpha=0.3)
                    else:
                        ax_trends.text(0.5, 0.5, 'Aucune donnée\ntemporelle', 
                                    ha='center', va='center', transform=ax_trends.transAxes,
                                    fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                        ax_trends.set_title('Évolution Temporelle', fontweight='bold', fontsize=14)
                else:
                    ax_trends.text(0.5, 0.5, 'Colonne année\nmanquante', 
                                ha='center', va='center', transform=ax_trends.transAxes,
                                fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
                    ax_trends.set_title('Évolution Temporelle', fontweight='bold', fontsize=14)
            except Exception as e:
                print(f"❌ Erreur tendances temporelles: {e}")
                ax_trends.text(0.5, 0.5, 'Erreur dans les\ntendances temporelles', 
                            ha='center', va='center', transform=ax_trends.transAxes,
                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                ax_trends.set_title('Évolution Temporelle', fontweight='bold', fontsize=14)
            
            # 5. Répartition géographique
            ax_geo = fig.add_subplot(gs[2, :2])
            try:
                if 'centroid_region' in df_events.columns:
                    region_counts = df_events['centroid_region'].value_counts().head(8)
                    if not region_counts.empty:
                        colors_regions = [REGION_COLORS.get(region, '#808080') for region in region_counts.index]
                        bars = ax_geo.barh(range(len(region_counts)), region_counts.values, 
                                        color=colors_regions, alpha=0.8)
                        ax_geo.set_yticks(range(len(region_counts)))
                        ax_geo.set_yticklabels(region_counts.index, fontsize=10)
                        ax_geo.set_title('Principales Régions Affectées', fontweight='bold', fontsize=14)
                        ax_geo.grid(True, alpha=0.3, axis='x')
                    else:
                        ax_geo.text(0.5, 0.5, 'Aucune donnée\nrégionale', 
                                ha='center', va='center', transform=ax_geo.transAxes,
                                fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                        ax_geo.set_title('Principales Régions Affectées', fontweight='bold', fontsize=14)
                else:
                    ax_geo.text(0.5, 0.5, 'Colonne région\nmanquante', 
                            ha='center', va='center', transform=ax_geo.transAxes,
                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
                    ax_geo.set_title('Principales Régions Affectées', fontweight='bold', fontsize=14)
            except Exception as e:
                print(f"❌ Erreur répartition géographique: {e}")
                ax_geo.text(0.5, 0.5, 'Erreur dans la\nrépartition géographique', 
                        ha='center', va='center', transform=ax_geo.transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                ax_geo.set_title('Principales Régions Affectées', fontweight='bold', fontsize=14)
            
            # 6. Intensité vs Couverture
            ax_scatter = fig.add_subplot(gs[2, 2:])
            try:
                required_cols = ['coverage_percent', 'max_precip', 'max_anomaly']
                if all(col in df_events.columns for col in required_cols):
                    df_clean = df_events[required_cols].dropna()
                    if not df_clean.empty:
                        scatter = ax_scatter.scatter(df_clean['coverage_percent'], df_clean['max_precip'],
                                                c=df_clean['max_anomaly'], cmap='viridis', 
                                                s=50, alpha=0.7, edgecolors='black', linewidth=0.5)
                        ax_scatter.set_xlabel('Couverture (%)')
                        ax_scatter.set_ylabel('Précipitation (mm)')
                        ax_scatter.set_title('Intensité vs Couverture', fontweight='bold', fontsize=14)
                        ax_scatter.grid(True, alpha=0.3)
                        
                        # Colorbar
                        cbar = plt.colorbar(scatter, ax=ax_scatter)
                        cbar.set_label('Anomalie (σ)')
                    else:
                        ax_scatter.text(0.5, 0.5, 'Données insuffisantes\npour le scatter plot', 
                                    ha='center', va='center', transform=ax_scatter.transAxes,
                                    fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                        ax_scatter.set_title('Intensité vs Couverture', fontweight='bold', fontsize=14)
                else:
                    missing_cols = [col for col in required_cols if col not in df_events.columns]
                    ax_scatter.text(0.5, 0.5, f'Colonnes manquantes:\n{", ".join(missing_cols)}', 
                                ha='center', va='center', transform=ax_scatter.transAxes,
                                fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
                    ax_scatter.set_title('Intensité vs Couverture', fontweight='bold', fontsize=14)
            except Exception as e:
                print(f"❌ Erreur scatter plot: {e}")
                ax_scatter.text(0.5, 0.5, 'Erreur dans le\nscatter plot', 
                            ha='center', va='center', transform=ax_scatter.transAxes,
                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                ax_scatter.set_title('Intensité vs Couverture', fontweight='bold', fontsize=14)
            
            # Sauvegarder
            output_path = self._save_plot('executive_summary')
            
            return output_path
            
        except Exception as e:
            print(f"❌ Erreur majeure dans create_executive_summary: {e}")
            # Créer un graphique d'erreur minimal
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, f'Erreur lors de la création\ndu résumé exécutif:\n{str(e)[:100]}...', 
                ha='center', va='center', transform=ax.transAxes,
                fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            ax.set_title('Résumé Exécutif - Erreur', fontweight='bold', fontsize=16)
            ax.axis('off')
            
            output_path = self._save_plot('executive_summary')
            return output_path
        
    def _create_key_statistics_panel(self, ax, df_events: pd.DataFrame):
        """Crée le panneau des statistiques clés."""
        ax.axis('off')
        
        # Calculer les statistiques
        total_events = len(df_events)
        period_years = df_events['year'].max() - df_events['year'].min() + 1
        frequency = total_events / period_years
        mean_precip = df_events['max_precip'].mean()
        max_precip = df_events['max_precip'].max()
        mean_coverage = df_events['coverage_percent'].mean()
        
        # Créer le texte des statistiques
        stats_text = f"""
STATISTIQUES CLÉS

📊 Période d'analyse: {df_events['year'].min()}-{df_events['year'].max()} ({period_years} ans)
🌩️  Total d'événements: {total_events}
📈 Fréquence moyenne: {frequency:.1f} événements/an

💧 Précipitation moyenne: {mean_precip:.1f} mm
🏔️  Précipitation maximale: {max_precip:.1f} mm
🗺️  Couverture moyenne: {mean_coverage:.1f}%

🎯 Critères de détection:
   • Anomalie > +2σ
   • Couverture ≥ 40 points
   • Précipitation ≥ 5mm
        """
        
        ax.text(0.05, 0.95, stats_text, transform=ax.transAxes, fontsize=12,
               verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
    
    def _create_top_events_table(self, ax, df_events: pd.DataFrame):
        """Crée le tableau des top événements - VERSION CORRIGÉE."""
        ax.axis('off')
        
        try:
            # Vérifier que les colonnes requises existent
            required_cols = ['max_precip', 'coverage_percent', 'max_anomaly']
            missing_cols = [col for col in required_cols if col not in df_events.columns]
            
            if missing_cols:
                ax.text(0.5, 0.5, f'Colonnes manquantes:\n{", ".join(missing_cols)}', 
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
                ax.set_title('Top 5 Événements (par intensité)', fontweight='bold', fontsize=14, pad=20)
                return
            
            # Créer une copie propre pour éviter les problèmes d'attributs
            df_clean = df_events[required_cols].copy()
            
            # Ajouter la colonne région si elle existe
            if 'centroid_region' in df_events.columns:
                df_clean['centroid_region'] = df_events['centroid_region'].copy()
            
            # Ajouter l'index comme colonne pour garder la référence de date
            df_clean['event_date'] = df_events.index
            
            # Supprimer les lignes avec des valeurs manquantes
            df_clean = df_clean.dropna(subset=required_cols)
            
            if df_clean.empty:
                ax.text(0.5, 0.5, 'Aucun événement valide\npour le classement', 
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                ax.set_title('Top 5 Événements (par intensité)', fontweight='bold', fontsize=14, pad=20)
                return
            
            # Trier par précipitation maximale (approche sécurisée)
            top_events = df_clean.sort_values('max_precip', ascending=False).head(5)
            
            # Créer le tableau
            table_data = []
            
            # En-tête
            if 'centroid_region' in top_events.columns:
                table_data.append(['Rang', 'Date', 'Précip (mm)', 'Couverture (%)', 'Anomalie (σ)', 'Région'])
            else:
                table_data.append(['Rang', 'Date', 'Précip (mm)', 'Couverture (%)', 'Anomalie (σ)'])
            
            # Données
            for i, (idx, event) in enumerate(top_events.iterrows(), 1):
                try:
                    # Formater la date
                    if hasattr(event['event_date'], 'strftime'):
                        date_str = event['event_date'].strftime('%Y-%m-%d')
                    else:
                        date_str = str(event['event_date'])[:10]  # Premiers 10 caractères
                    
                    row = [
                        str(i),
                        date_str,
                        f"{event['max_precip']:.1f}",
                        f"{event['coverage_percent']:.1f}",
                        f"{event['max_anomaly']:.1f}"
                    ]
                    
                    if 'centroid_region' in event and pd.notna(event['centroid_region']):
                        region_name = str(event['centroid_region'])[:15]  # Limiter la longueur
                        row.append(region_name)
                    elif 'centroid_region' in top_events.columns:
                        row.append('N/A')
                    
                    table_data.append(row)
                    
                except Exception as e:
                    # En cas d'erreur sur un événement, continuer avec les autres
                    print(f"❌ Erreur lors du formatage de l'événement {i}: {e}")
                    continue
            
            if len(table_data) <= 1:  # Seulement l'en-tête
                ax.text(0.5, 0.5, 'Erreur lors du formatage\ndes événements', 
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                ax.set_title('Top 5 Événements (par intensité)', fontweight='bold', fontsize=14, pad=20)
                return
            
            # Afficher le tableau
            table = ax.table(cellText=table_data, cellLoc='center', loc='center',
                            colWidths=[0.1, 0.2, 0.15, 0.15, 0.15] + ([0.25] if len(table_data[0]) > 5 else []))
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 1.8)
            
            # Styliser l'en-tête
            for i in range(len(table_data[0])):
                table[(0, i)].set_facecolor('#4CAF50')
                table[(0, i)].set_text_props(weight='bold', color='white')
            
            ax.set_title('Top 5 Événements (par intensité)', fontweight='bold', fontsize=14, pad=20)
            
        except Exception as e:
            print(f"❌ Erreur lors de la création du tableau des top événements: {e}")
            ax.text(0.5, 0.5, f'Erreur lors de la création\ndu tableau:\n{str(e)[:50]}...', 
                ha='center', va='center', transform=ax.transAxes,
                fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            ax.set_title('Top 5 Événements (par intensité)', fontweight='bold', fontsize=14, pad=20)
    
    def _calculate_quality_metrics(self, df_events: pd.DataFrame) -> Dict[str, float]:
        """Calcule les métriques de qualité des données."""
        metrics = {}
        
        # Cohérence saisonnière
        rainy_season_months = [5, 6, 7, 8, 9, 10]
        rainy_events = df_events[df_events['month'].isin(rainy_season_months)]
        metrics['Cohérence saisonnière'] = len(rainy_events) / len(df_events)
        
        # Validité géographique
        if 'centroid_lat' in df_events.columns:
            bounds = self.geo.SENEGAL_BOUNDS
            valid_coords = (
                (df_events['centroid_lat'] >= bounds['lat_min']) &
                (df_events['centroid_lat'] <= bounds['lat_max']) &
                (df_events['centroid_lon'] >= bounds['lon_min']) &
                (df_events['centroid_lon'] <= bounds['lon_max'])
            )
            metrics['Validité géographique'] = valid_coords.sum() / len(df_events)
        
        # Seuil d'anomalie
        valid_anomalies = (df_events['max_anomaly'] >= 2.0).sum()
        metrics['Respect seuil anomalie'] = valid_anomalies / len(df_events)
        
        # Complétude des données
        required_cols = ['max_precip', 'coverage_percent', 'max_anomaly']
        completeness = df_events[required_cols].notna().all(axis=1).sum()
        metrics['Complétude données'] = completeness / len(df_events)
        
        return metrics
    
    def _save_plot(self, plot_key: str) -> str:
        """Sauvegarde un graphique avec gestion des erreurs."""
        try:
            output_path = get_output_path(plot_key)
            plt.savefig(output_path, dpi=PLOT_PARAMS['dpi'], bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            print(f"   ✅ Sauvegardé: {output_path}")
            plt.close()
            return output_path
        except Exception as e:
            # Fallback
            fallback_path = f"outputs/visualizations/{plot_key}.png"
            plt.savefig(fallback_path, dpi=PLOT_PARAMS['dpi'], bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            print(f"   ✅ Sauvegardé (fallback): {fallback_path}")
            plt.close()
            return fallback_path
    
    def create_all_visualizations(self, df_events: pd.DataFrame, 
                                lats: Optional[np.ndarray] = None, 
                                lons: Optional[np.ndarray] = None) -> Dict[str, str]:
        """
        Génère toutes les visualisations (sans zones climatiques).
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            lats (np.ndarray, optional): Latitudes
            lons (np.ndarray, optional): Longitudes
            
        Returns:
            Dict[str, str]: Chemins des fichiers générés
        """
        print("🎨 GÉNÉRATION COMPLÈTE DES VISUALISATIONS")
        print("=" * 60)
        
        if df_events.empty:
            print("❌ Aucun événement à visualiser")
            return {}
        
        generated_files = {}
        
        try:
            # 1. Distribution par phases
            generated_files['phase_distribution'] = self.create_phase_distribution_plot(df_events)
            
            # 2. Évolution temporelle (simplifiée)
            generated_files['temporal_evolution'] = self.create_temporal_evolution_plot(df_events)
            
            # 3. Analyse intensité-couverture
            generated_files['intensity_coverage'] = self.create_intensity_coverage_analysis(df_events)
            
            # 4. Validation
            generated_files['validation'] = self.create_validation_plots(df_events)
            
            # 5. Analyse géographique (régionale)
            generated_files['geographic_analysis'] = self.create_geographic_analysis_plot(df_events)
            
            # 6. Résumé exécutif
            generated_files['executive_summary'] = self.create_executive_summary(df_events)
            
            print(f"\n✅ TOUTES LES VISUALISATIONS GÉNÉRÉES AVEC SUCCÈS!")
            print(f"   Nombre de fichiers créés: {len(generated_files)}")
            print(f"   Fichiers générés:")
            for key, path in generated_files.items():
                print(f"   • {key}: {path}")
            
            return generated_files
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération: {e}")
            import traceback
            traceback.print_exc()
            return generated_files
        
# Fonctions de compatibilité avec l'ancienne interface
def create_detection_visualizations_part1(df_events: pd.DataFrame):
    """Fonction de compatibilité - Distribution saisonnière."""
    visualizer = EnhancedDetectionVisualizer()
    return visualizer.create_phase_distribution_plot(df_events)

def create_detection_visualizations_part2(df_events: pd.DataFrame):
    """Fonction de compatibilité - Intensité et couverture."""
    visualizer = EnhancedDetectionVisualizer()
    return visualizer.create_intensity_coverage_analysis(df_events)

def create_detection_visualizations_part3(df_events: pd.DataFrame):
    """Fonction de compatibilité - Évolution temporelle."""
    visualizer = EnhancedDetectionVisualizer()
    return visualizer.create_temporal_evolution_plot(df_events)

def create_spatial_distribution_visualization(df_events: pd.DataFrame, 
                                           lats: np.ndarray, lons: np.ndarray):
    """Fonction de compatibilité - Distribution spatiale."""
    visualizer = EnhancedDetectionVisualizer()
    return visualizer.create_geographic_analysis_plot(df_events)


class DetectionVisualizer(EnhancedDetectionVisualizer):
    """Alias pour compatibilité avec l'ancien nom."""
    pass


if __name__ == "__main__":
    print("🎨 Module de visualisation des événements extrêmes - Version Améliorée")
    print("=" * 70)
    print("Ce module contient les outils pour:")
    print("• Visualiser la distribution par phases de saison des pluies")
    print("• Analyser la répartition géographique avec régions/départements")
    print("• Créer des analyses temporelles avancées")
    print("• Générer des graphiques intensité-couverture détaillés")
    print("• Valider la qualité des détections")
    print("• Produire des résumés exécutifs visuels")
    print()
    print("🆕 Nouvelles fonctionnalités:")
    print("• Intégration avec la classification par phases")
    print("• Analyses géographiques avec références administratives")
    print("• Métriques de validation automatiques")
    print("• Résumés exécutifs complets")
    print("• Gestion robuste des erreurs")
    print()
    print("📊 Utilisation:")
    print("visualizer = EnhancedDetectionVisualizer()")
    print("files = visualizer.create_all_visualizations(df_events, lats, lons)")
    print()
    print("✅ Module prêt à l'utilisation!")