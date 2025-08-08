# src/visualization/geographic_plots.py
"""
Module de visualisation géographique centralisé et amélioré.
Intégré avec les nouvelles références géographiques du Sénégal.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon, Circle
import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, List, Tuple
import warnings
import sys
from pathlib import Path
from datetime import datetime

# Imports avec gestion robuste des erreurs
try:
    from ..config.settings import (
        REGION_COLORS, CLIMATE_COLORS, PHASE_COLORS, PLOT_PARAMS,
        get_output_path, PROJECT_INFO
    )
    from ..utils.geographic_references import SenegalGeography, analyze_geographic_distribution
    from ..utils.season_classifier import get_phase_from_month
except ImportError:
    try:
        from src.config.settings import (
            REGION_COLORS, CLIMATE_COLORS, PHASE_COLORS, PLOT_PARAMS,
            get_output_path, PROJECT_INFO
        )
        from src.utils.geographic_references import SenegalGeography, analyze_geographic_distribution
        from src.utils.season_classifier import get_phase_from_month
    except ImportError:
        # Configuration de fallback
        REGION_COLORS = {
            'Dakar': '#FF6B6B', 'Thiès': '#4ECDC4', 'Diourbel': '#45B7D1',
            'Fatick': '#96CEB4', 'Kaolack': '#FECA57', 'Default': '#808080'
        }
        CLIMATE_COLORS = {
            'sahelienne': '#FFA07A', 'soudano_sahelienne': '#98FB98',
            'soudanienne': '#228B22', 'cotiere': '#87CEEB', 'Default': '#808080'
        }
        PHASE_COLORS = {
            'Phase_1_debut': '#87CEEB', 'Phase_2_pleine': '#1E90FF',
            'Phase_3_fin': '#4682B4', 'Hors_saison': '#D3D3D3'
        }
        PLOT_PARAMS = {
            'figure_size': (15, 8), 'figure_size_large': (20, 12),
            'dpi': 300, 'style': 'default', 'font_size': 12
        }
        PROJECT_INFO = {'title': 'Analyse des précipitations extrêmes au Sénégal'}
        
        def get_output_path(key): return f"outputs/visualizations/{key}.png"
        def get_phase_from_month(month): return 'Phase_2_pleine' if month in [7, 8] else 'Hors_saison'
        
        class SenegalGeography:
            SENEGAL_BOUNDS = {'lat_min': 12.3, 'lat_max': 16.7, 'lon_min': -17.55, 'lon_max': -11.35}
            REGIONS = {}
            CITIES = {}
            CLIMATE_ZONES = {}
            @staticmethod
            def identify_region(lat, lon): return "Région indéterminée"
            @staticmethod
            def identify_climate_zone(lat, lon): return "Zone indéterminée"
        
        def analyze_geographic_distribution(coords): return {}

warnings.filterwarnings('ignore')


class EnhancedSenegalMapVisualizer:
    """
    Visualiseur cartographique avancé pour le Sénégal avec intégration complète
    des références géographiques et analyses des événements extrêmes.
    """
    
    def __init__(self):
        """Initialise le visualiseur avec toutes les références géographiques."""
        self.geo = SenegalGeography()
        self.bounds = self.geo.SENEGAL_BOUNDS
        
        # Configuration des couleurs et styles
        self.region_colors = REGION_COLORS
        self.climate_colors = CLIMATE_COLORS
        self.phase_colors = PHASE_COLORS
        
        print("🗺️  EnhancedSenegalMapVisualizer initialisé")
        print(f"   Régions disponibles: {len(self.geo.REGIONS)}")
        print(f"   Villes principales: {len(self.geo.CITIES)}")
        print(f"   Zones climatiques: {len(self.geo.CLIMATE_ZONES)}")
    
    def create_senegal_base_map(self, ax, show_cities: bool = True, 
                              show_regions: bool = True, show_climate_zones: bool = False,
                              title: str = None) -> None:
        """
        Crée une carte de base du Sénégal avec tous les éléments géographiques.
        
        Args:
            ax: Axe matplotlib
            show_cities (bool): Afficher les villes
            show_regions (bool): Afficher les régions
            show_climate_zones (bool): Afficher les zones climatiques
            title (str, optional): Titre de la carte
        """
        
        # Fond de carte (océan Atlantique)
        ocean_patch = patches.Rectangle(
            (self.bounds['lon_min'], self.bounds['lat_min']),
            self.bounds['lon_max'] - self.bounds['lon_min'],
            self.bounds['lat_max'] - self.bounds['lat_min'],
            facecolor='lightblue', alpha=0.2, edgecolor='none', zorder=0
        )
        ax.add_patch(ocean_patch)
        
        # Zones climatiques en arrière-plan
        if show_climate_zones:
            self._add_climate_zones(ax)
        
        # Limites des régions
        if show_regions:
            self._add_regional_boundaries(ax)
        
        # Villes principales
        if show_cities:
            self._add_cities(ax)
        
        # Frontières nationales
        self._add_national_boundaries(ax)
        
        # Configuration des axes
        ax.set_xlim(self.bounds['lon_min'] - 0.2, self.bounds['lon_max'] + 0.2)
        ax.set_ylim(self.bounds['lat_min'] - 0.2, self.bounds['lat_max'] + 0.2)
        ax.set_xlabel('Longitude (°E)', fontsize=PLOT_PARAMS['font_size'])
        ax.set_ylabel('Latitude (°N)', fontsize=PLOT_PARAMS['font_size'])
        ax.grid(True, alpha=0.3, linestyle=':', color='gray')
        
        if title:
            ax.set_title(title, fontsize=PLOT_PARAMS['title_size'], fontweight='bold', pad=20)
    
    def _add_climate_zones(self, ax):
        """Ajoute les zones climatiques comme arrière-plan - VERSION CORRIGÉE."""
        try:
            for zone_name, zone_info in self.geo.CLIMATE_ZONES.items():
                bounds = zone_info.get('bounds', {})
                color = self.climate_colors.get(zone_name, '#808080')
                
                if 'lat_min' in bounds and 'lat_max' in bounds:
                    # Zone horizontale (par latitude)
                    zone_patch = patches.Rectangle(
                        (self.bounds['lon_min'], bounds['lat_min']),
                        self.bounds['lon_max'] - self.bounds['lon_min'],
                        bounds['lat_max'] - bounds['lat_min'],
                        facecolor=color, alpha=0.15, edgecolor='none', zorder=1
                    )
                    ax.add_patch(zone_patch)
                    
                    # Label de la zone - VERSION CORRIGÉE
                    # Utiliser .get() pour éviter les KeyError
                    zone_label = zone_info.get('name', zone_name)  # Fallback au nom de la clé
                    
                    ax.text(self.bounds['lon_min'] + 0.1, 
                        (bounds['lat_min'] + bounds['lat_max']) / 2,
                        zone_label, rotation=90, fontsize=10,
                        verticalalignment='center', alpha=0.7,
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        except Exception as e:
            print(f"❌ Erreur lors de l'ajout des zones climatiques: {e}")
            # Continuer sans les zones climatiques plutôt que de faire planter le programme
            pass

    def _add_regional_boundaries(self, ax):
        """Ajoute les limites des régions administratives."""
        for region_name, region_info in self.geo.REGIONS.items():
            bounds = region_info['bounds']
            color = self.region_colors.get(region_name, '#808080')
            
            # Rectangle de la région
            region_rect = patches.Rectangle(
                (bounds['lon_min'], bounds['lat_min']),
                bounds['lon_max'] - bounds['lon_min'],
                bounds['lat_max'] - bounds['lat_min'],
                linewidth=1.5, edgecolor=color, facecolor='none',
                linestyle='-', alpha=0.7, zorder=2
            )
            ax.add_patch(region_rect)
            
            # Nom de la région au centre
            center_lat = (bounds['lat_min'] + bounds['lat_max']) / 2
            center_lon = (bounds['lon_min'] + bounds['lon_max']) / 2
            ax.text(center_lon, center_lat, region_name, 
                   fontsize=9, fontweight='bold', ha='center', va='center',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8),
                   zorder=3)
    
    def _add_cities(self, ax):
        """Ajoute les villes principales du Sénégal."""
        for city_name, city_info in self.geo.CITIES.items():
            lat, lon = city_info['lat'], city_info['lon']
            
            # Vérifier que la ville est dans les limites
            if (self.bounds['lat_min'] <= lat <= self.bounds['lat_max'] and
                self.bounds['lon_min'] <= lon <= self.bounds['lon_max']):
                
                # Couleur et taille selon le type de ville
                if city_info['type'] == 'capitale':
                    color, size = 'red', 12
                    marker = 's'  # Carré pour la capitale
                elif city_info['type'] == 'capitale_region':
                    color, size = 'blue', 8
                    marker = 'o'  # Cercle pour les capitales régionales
                elif city_info['type'] == 'ville_religieuse':
                    color, size = 'purple', 10
                    marker = '^'  # Triangle pour les villes religieuses
                else:
                    color, size = 'darkgreen', 6
                    marker = 'o'
                
                # Marker de la ville
                ax.plot(lon, lat, marker, color=color, markersize=size,
                       markeredgecolor='white', markeredgewidth=1.5, 
                       alpha=0.9, zorder=4)
                
                # Nom de la ville
                ax.annotate(city_name, (lon, lat),
                           xytext=(5, 5), textcoords='offset points',
                           fontsize=8, fontweight='bold', color='black',
                           bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.9),
                           zorder=5)
    
    def _add_national_boundaries(self, ax):
        """Ajoute les frontières nationales du Sénégal."""
        # Contour principal du pays
        main_boundary = patches.Rectangle(
            (self.bounds['lon_min'], self.bounds['lat_min']),
            self.bounds['lon_max'] - self.bounds['lon_min'],
            self.bounds['lat_max'] - self.bounds['lat_min'],
            linewidth=3, edgecolor='black', facecolor='none',
            linestyle='-', zorder=6
        )
        ax.add_patch(main_boundary)
        
        # Label "SÉNÉGAL"
        ax.text(self.bounds['lon_min'] + 1, self.bounds['lat_max'] - 0.5,
               'SÉNÉGAL', fontsize=16, fontweight='bold',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.8),
               zorder=7)
    
    def create_events_spatial_map(self, df_events: pd.DataFrame, 
                                 figsize: Tuple[int, int] = None) -> str:
        """
        Crée une carte de distribution spatiale des événements extrêmes.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            figsize (tuple, optional): Taille de la figure
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("🗺️  Création: Carte de distribution spatiale des événements")
        
        if figsize is None:
            figsize = PLOT_PARAMS['figure_size_large']
        
        fig, axes = plt.subplots(1, 2, figsize=figsize)
        fig.suptitle(f'{PROJECT_INFO["title"]}\nDistribution spatiale des événements extrêmes',
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold')
        
        # 1. Carte principale avec événements
        self.create_senegal_base_map(axes[0], show_cities=True, show_regions=True,
                                   title="Localisation des événements")
        
        if not df_events.empty and 'centroid_lat' in df_events.columns:
            # Ajouter la colonne phase si elle n'existe pas
            if 'phase' not in df_events.columns:
                df_events['phase'] = df_events['month'].apply(get_phase_from_month)
            
            # Événements par phase
            for phase in self.phase_colors.keys():
                if phase in df_events['phase'].values:
                    phase_data = df_events[df_events['phase'] == phase]
                    
                    if not phase_data.empty:
                        # Taille proportionnelle à la couverture
                        sizes = phase_data['coverage_percent'] * 3
                        
                        scatter = axes[0].scatter(
                            phase_data['centroid_lon'], phase_data['centroid_lat'],
                            c=self.phase_colors[phase], s=sizes, alpha=0.7,
                            edgecolors='black', linewidth=0.8, 
                            label=f"Phase {phase.split('_')[1]}" if '_' in phase else phase,
                            zorder=8
                        )
            
            # Légende pour les phases
            axes[0].legend(loc='upper left', bbox_to_anchor=(0.02, 0.98), fontsize=10)
        
        # 2. Carte de densité par région
        self.create_senegal_base_map(axes[1], show_cities=False, show_regions=True,
                                   title="Densité par région")
        
        if not df_events.empty and 'centroid_region' in df_events.columns:
            # Calculer la densité par région
            region_counts = df_events['centroid_region'].value_counts()
            
            for region_name, region_info in self.geo.REGIONS.items():
                count = region_counts.get(region_name, 0)
                bounds = region_info['bounds']
                
                # Intensité de couleur basée sur le nombre d'événements
                if count > 0:
                    alpha = min(0.8, 0.2 + (count / region_counts.max()) * 0.6)
                    color = 'red'
                else:
                    alpha = 0.1
                    color = 'gray'
                
                # Rectangle coloré pour la région
                region_patch = patches.Rectangle(
                    (bounds['lon_min'], bounds['lat_min']),
                    bounds['lon_max'] - bounds['lon_min'],
                    bounds['lat_max'] - bounds['lat_min'],
                    facecolor=color, alpha=alpha, edgecolor='black', linewidth=1,
                    zorder=2
                )
                axes[1].add_patch(region_patch)
                
                # Ajouter le nombre d'événements
                center_lat = (bounds['lat_min'] + bounds['lat_max']) / 2
                center_lon = (bounds['lon_min'] + bounds['lon_max']) / 2
                axes[1].text(center_lon, center_lat, str(count),
                           fontsize=12, fontweight='bold', ha='center', va='center',
                           color='white' if count > 0 else 'black',
                           bbox=dict(boxstyle='circle,pad=0.3', 
                                   facecolor='black' if count > 0 else 'white', alpha=0.8),
                           zorder=3)
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('spatial_distribution', fig)
        return output_path
    
    def create_climate_zones_analysis(self, df_events: pd.DataFrame) -> str:
        """
        Crée une analyse des événements par zones climatiques - VERSION CORRIGÉE.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("🌡️  Création: Analyse par zones climatiques")
        
        fig, axes = plt.subplots(2, 2, figsize=PLOT_PARAMS['figure_size_large'])
        fig.suptitle(f'{PROJECT_INFO["title"]}\nAnalyse par zones climatiques',
                    fontsize=PLOT_PARAMS['title_size'], fontweight='bold')
        
        # 1. Carte des zones climatiques
        self.create_senegal_base_map(axes[0,0], show_cities=False, show_regions=False,
                                show_climate_zones=True, title="Zones climatiques du Sénégal")
        
        # 2. Distribution des événements par zone climatique
        if not df_events.empty and 'centroid_climate_zone' in df_events.columns:
            climate_counts = df_events['centroid_climate_zone'].value_counts()
            colors = [self.climate_colors.get(zone, '#808080') for zone in climate_counts.index]
            
            wedges, texts, autotexts = axes[0,1].pie(
                climate_counts.values, labels=climate_counts.index,
                colors=colors, autopct='%1.1f%%', startangle=90
            )
            axes[0,1].set_title('Répartition par zones climatiques', fontweight='bold')
        else:
            axes[0,1].text(0.5, 0.5, 'Aucune donnée\nde zone climatique\ndisponible', 
                        ha='center', va='center', transform=axes[0,1].transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
            axes[0,1].set_title('Répartition par zones climatiques', fontweight='bold')
        
        # 3. Intensité moyenne par zone climatique - VERSION CORRIGÉE
        if not df_events.empty and 'centroid_climate_zone' in df_events.columns:
            try:
                # Créer une copie propre pour éviter les problèmes d'attributs
                climate_cols = ['centroid_climate_zone', 'max_precip', 'coverage_percent']
                df_clean = df_events[climate_cols].copy().dropna()
                
                if not df_clean.empty:
                    climate_stats = (df_clean.groupby('centroid_climate_zone')
                                .agg({
                                    'max_precip': ['mean', 'std', 'count'],
                                    'coverage_percent': 'mean'
                                })
                                .round(2)
                                .reset_index())
                    
                    # Aplatir les colonnes multi-niveaux
                    climate_stats.columns = ['zone', 'max_precip_mean', 'max_precip_std', 'max_precip_count', 'coverage_percent_mean']
                    
                    zones = climate_stats['zone'].tolist()
                    mean_precip = climate_stats['max_precip_mean'].tolist()
                    std_precip = climate_stats['max_precip_std'].tolist()
                    colors_bars = [self.climate_colors.get(zone, '#808080') for zone in zones]
                    
                    x_pos = np.arange(len(zones))
                    bars = axes[1,0].bar(x_pos, mean_precip, yerr=std_precip,
                                    color=colors_bars, alpha=0.8, capsize=5)
                    
                    axes[1,0].set_xticks(x_pos)
                    axes[1,0].set_xticklabels(zones, rotation=45, ha='right')
                    axes[1,0].set_ylabel('Précipitation moyenne (mm)')
                    axes[1,0].set_title('Intensité par zone climatique', fontweight='bold')
                    axes[1,0].grid(True, alpha=0.3)
                    
                    # Ajouter les valeurs sur les barres
                    for bar, val in zip(bars, mean_precip):
                        height = bar.get_height()
                        axes[1,0].text(bar.get_x() + bar.get_width()/2., height + height*0.05,
                                    f'{val:.1f}', ha='center', va='bottom', fontsize=9)
                else:
                    axes[1,0].text(0.5, 0.5, 'Données insuffisantes\npour l\'analyse climatique', 
                                ha='center', va='center', transform=axes[1,0].transAxes,
                                fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                    axes[1,0].set_title('Intensité par zone climatique', fontweight='bold')
            except Exception as e:
                print(f"❌ Erreur lors de l'analyse climatique: {e}")
                axes[1,0].text(0.5, 0.5, f'Erreur lors de l\'analyse:\n{str(e)[:50]}...', 
                            ha='center', va='center', transform=axes[1,0].transAxes,
                            fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                axes[1,0].set_title('Intensité par zone climatique', fontweight='bold')
        else:
            axes[1,0].text(0.5, 0.5, 'Colonne zone climatique\nmanquante', 
                        ha='center', va='center', transform=axes[1,0].transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
            axes[1,0].set_title('Intensité par zone climatique', fontweight='bold')
        
        # 4. Caractéristiques des zones climatiques - VERSION CORRIGÉE
        axes[1,1].axis('off')
        
        try:
            # Vérifier que les données des zones climatiques existent
            if hasattr(self.geo, 'CLIMATE_ZONES') and self.geo.CLIMATE_ZONES:
                zones_text = "CARACTÉRISTIQUES DES ZONES CLIMATIQUES\n\n"
                
                for zone_name, zone_info in self.geo.CLIMATE_ZONES.items():
                    # Utiliser .get() pour éviter les KeyError
                    zone_display_name = zone_info.get('name', zone_name.replace('_', ' ').title())
                    precipitation_range = zone_info.get('precipitation_range', 'Non spécifié')
                    characteristics = zone_info.get('characteristics', 'Non spécifié')
                    regions = zone_info.get('regions', [])
                    
                    zones_text += f"🌿 {zone_display_name}\n"
                    zones_text += f"   Précipitations: {precipitation_range}\n"
                    zones_text += f"   Caractéristiques: {characteristics}\n"
                    
                    # Gestion sécurisée des régions
                    if regions:
                        if isinstance(regions, list):
                            regions_display = ', '.join(regions[:3])
                        else:
                            regions_display = str(regions)
                        zones_text += f"   Régions: {regions_display}\n"
                    else:
                        zones_text += "   Régions: Non spécifiées\n"
                    
                    zones_text += "\n"
                
                axes[1,1].text(0.05, 0.95, zones_text, transform=axes[1,1].transAxes,
                            fontsize=11, verticalalignment='top',
                            bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgreen', alpha=0.8))
            else:
                # Données non disponibles
                fallback_text = """ZONES CLIMATIQUES DU SÉNÉGAL

    🌿 Zone Sahélienne (Nord)
    Précipitations: 200-400 mm/an
    Caractéristiques: Climat sec, végétation clairsemée
    
    🌿 Zone Soudano-Sahélienne (Centre)
    Précipitations: 400-600 mm/an
    Caractéristiques: Transition, savane arborée
    
    🌿 Zone Soudanienne (Sud)
    Précipitations: 600-1200 mm/an
    Caractéristiques: Végétation dense, forêts
    
    🌿 Zone Côtière (Ouest)
    Précipitations: Variable
    Caractéristiques: Influence océanique"""
                
                axes[1,1].text(0.05, 0.95, fallback_text, transform=axes[1,1].transAxes,
                            fontsize=11, verticalalignment='top',
                            bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8))
        
        except Exception as e:
            print(f"❌ Erreur lors de l'affichage des caractéristiques climatiques: {e}")
            error_text = f"Erreur lors de l'affichage\ndes caractéristiques:\n{str(e)[:50]}..."
            axes[1,1].text(0.5, 0.5, error_text, 
                        ha='center', va='center', transform=axes[1,1].transAxes,
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = self._save_plot('climate_zones', fig)
        return output_path
    
    def create_regional_detailed_analysis(self, df_events: pd.DataFrame) -> str:
            """
            Crée une analyse détaillée par régions administratives - VERSION CORRIGÉE.
            
            Args:
                df_events (pd.DataFrame): DataFrame des événements
                
            Returns:
                str: Chemin du fichier sauvegardé
            """
            print("🏛️  Création: Analyse détaillée par régions")
            
            fig, axes = plt.subplots(2, 2, figsize=PLOT_PARAMS['figure_size_large'])
            fig.suptitle(f'{PROJECT_INFO["title"]}\nAnalyse détaillée par régions administratives',
                        fontsize=PLOT_PARAMS['title_size'], fontweight='bold')
            
            # 1. Carte avec coloration par fréquence
            self.create_senegal_base_map(axes[0,0], show_cities=True, show_regions=False,
                                    title="Fréquence des événements par région")
            
            if not df_events.empty and 'centroid_region' in df_events.columns:
                region_counts = df_events['centroid_region'].value_counts()
                max_count = region_counts.max() if len(region_counts) > 0 else 1
                
                for region_name, region_info in self.geo.REGIONS.items():
                    bounds = region_info['bounds']
                    count = region_counts.get(region_name, 0)
                    
                    # Gradient de couleur basé sur la fréquence
                    intensity = count / max_count if max_count > 0 else 0
                    color = plt.cm.Reds(0.3 + intensity * 0.7)  # Du rouge clair au rouge foncé
                    
                    region_patch = patches.Rectangle(
                        (bounds['lon_min'], bounds['lat_min']),
                        bounds['lon_max'] - bounds['lon_min'],
                        bounds['lat_max'] - bounds['lat_min'],
                        facecolor=color, alpha=0.7, edgecolor='black', linewidth=1,
                        zorder=2
                    )
                    axes[0,0].add_patch(region_patch)
                
                # Colorbar
                sm = plt.cm.ScalarMappable(cmap=plt.cm.Reds, 
                                        norm=plt.Normalize(vmin=0, vmax=max_count))
                sm.set_array([])
                cbar = plt.colorbar(sm, ax=axes[0,0], shrink=0.8)
                cbar.set_label('Nombre d\'événements')
            
            # 2. Top 10 des régions
            if not df_events.empty and 'centroid_region' in df_events.columns:
                top_regions = df_events['centroid_region'].value_counts().head(10)
                colors_regions = [self.region_colors.get(region, '#808080') for region in top_regions.index]
                
                bars = axes[0,1].barh(range(len(top_regions)), top_regions.values,
                                    color=colors_regions, alpha=0.8)
                
                axes[0,1].set_yticks(range(len(top_regions)))
                axes[0,1].set_yticklabels(top_regions.index, fontsize=10)
                axes[0,1].set_xlabel('Nombre d\'événements')
                axes[0,1].set_title('Top 10 des régions affectées', fontweight='bold')
                axes[0,1].grid(True, alpha=0.3, axis='x')
                
                # Ajouter les valeurs
                for i, (bar, count) in enumerate(zip(bars, top_regions.values)):
                    axes[0,1].text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                                f'{count}', ha='left', va='center', fontsize=9)
            
            # 3. Statistiques d'intensité par région - VERSION CORRIGÉE
            if not df_events.empty and 'centroid_region' in df_events.columns:
                try:
                    # Créer une copie propre pour éviter les problèmes d'attributs
                    required_cols = ['centroid_region', 'max_precip', 'coverage_percent']
                    missing_cols = [col for col in required_cols if col not in df_events.columns]
                    
                    if not missing_cols:
                        # Créer une copie propre sans les attributs problématiques
                        df_clean = df_events[required_cols].copy()
                        
                        # Supprimer les valeurs manquantes
                        df_clean = df_clean.dropna()
                        
                        if not df_clean.empty:
                            # Calculer les statistiques de manière sécurisée
                            regional_stats = (df_clean.groupby('centroid_region')
                                            .agg({
                                                'max_precip': 'mean',
                                                'coverage_percent': 'mean'
                                            })
                                            .round(2)
                                            .reset_index())
                            
                            # Prendre les 8 régions avec le plus d'événements
                            top_8_regions = df_events['centroid_region'].value_counts().head(8).index
                            regional_stats_filtered = regional_stats[regional_stats['centroid_region'].isin(top_8_regions)]
                            
                            if not regional_stats_filtered.empty:
                                x_pos = np.arange(len(regional_stats_filtered))
                                width = 0.35
                                
                                bars1 = axes[1,0].bar(x_pos - width/2, regional_stats_filtered['max_precip'],
                                                    width, label='Précipitation (mm)', alpha=0.8, color='skyblue')
                                bars2 = axes[1,0].bar(x_pos + width/2, regional_stats_filtered['coverage_percent'],
                                                    width, label='Couverture (%)', alpha=0.8, color='lightcoral')
                                
                                axes[1,0].set_xticks(x_pos)
                                axes[1,0].set_xticklabels(regional_stats_filtered['centroid_region'], 
                                                        rotation=45, ha='right', fontsize=9)
                                axes[1,0].set_ylabel('Valeurs moyennes')
                                axes[1,0].set_title('Statistiques moyennes par région', fontweight='bold')
                                axes[1,0].legend()
                                axes[1,0].grid(True, alpha=0.3)
                            else:
                                axes[1,0].text(0.5, 0.5, 'Données insuffisantes\npour les statistiques régionales', 
                                            ha='center', va='center', transform=axes[1,0].transAxes,
                                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                                axes[1,0].set_title('Statistiques moyennes par région', fontweight='bold')
                        else:
                            axes[1,0].text(0.5, 0.5, 'Aucune donnée valide\npour les statistiques', 
                                        ha='center', va='center', transform=axes[1,0].transAxes,
                                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
                            axes[1,0].set_title('Statistiques moyennes par région', fontweight='bold')
                    else:
                        axes[1,0].text(0.5, 0.5, f'Colonnes manquantes:\n{", ".join(missing_cols)}', 
                                    ha='center', va='center', transform=axes[1,0].transAxes,
                                    fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))
                        axes[1,0].set_title('Statistiques moyennes par région', fontweight='bold')
                
                except Exception as e:
                    print(f"❌ Erreur lors du calcul des statistiques régionales: {e}")
                    axes[1,0].text(0.5, 0.5, f'Erreur lors du calcul:\n{str(e)[:50]}...', 
                                ha='center', va='center', transform=axes[1,0].transAxes,
                                fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
                    axes[1,0].set_title('Statistiques moyennes par région', fontweight='bold')
            
            # 4. Informations statistiques
            axes[1,1].axis('off')
            
            if not df_events.empty and 'centroid_region' in df_events.columns:
                try:
                    # Calculer des statistiques régionales de manière sécurisée
                    total_regions = len(self.geo.REGIONS)
                    affected_regions = df_events['centroid_region'].nunique()
                    
                    region_counts = df_events['centroid_region'].value_counts()
                    most_affected = region_counts.index[0] if len(region_counts) > 0 else "Aucune"
                    most_affected_count = region_counts.iloc[0] if len(region_counts) > 0 else 0
                    
                    least_affected_regions = [r for r in self.geo.REGIONS.keys() 
                                            if r not in df_events['centroid_region'].values]
                    
                    stats_text = f"""STATISTIQUES RÉGIONALES

    📊 Couverture géographique:
    • Régions totales: {total_regions}
    • Régions affectées: {affected_regions}
    • Couverture: {affected_regions/total_regions*100:.1f}%

    🎯 Région la plus affectée:
    • {most_affected}
    • {most_affected_count} événements

    🌿 Régions épargnées:
    • {len(least_affected_regions)} régions
    • Principales: {', '.join(least_affected_regions[:3]) if least_affected_regions else 'Aucune'}

    📈 Répartition moyenne:
    • {len(df_events)/affected_regions:.1f} événements/région affectée
                    """
                    
                    axes[1,1].text(0.05, 0.95, stats_text, transform=axes[1,1].transAxes,
                                fontsize=11, verticalalignment='top',
                                bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8))
                
                except Exception as e:
                    print(f"❌ Erreur lors du calcul des statistiques générales: {e}")
                    error_text = f"Erreur lors du calcul\ndes statistiques:\n{str(e)[:50]}..."
                    axes[1,1].text(0.5, 0.5, error_text, 
                                ha='center', va='center', transform=axes[1,1].transAxes,
                                fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
            else:
                axes[1,1].text(0.5, 0.5, "Données insuffisantes pour l'analyse régionale", 
                            ha='center', va='center', transform=axes[1,1].transAxes,
                            fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray"))
            
            plt.tight_layout()
            
            # Sauvegarder
            output_path = self._save_plot('regional_analysis', fig)
            return output_path
           
    def create_reference_map(self, title: str = "Carte de référence du Sénégal",
                           figsize: Tuple[int, int] = None) -> str:
        """
        Crée une carte de référence complète du Sénégal.
        
        Args:
            title (str): Titre de la carte
            figsize (tuple, optional): Taille de la figure
            
        Returns:
            str: Chemin du fichier sauvegardé
        """
        print("📍 Création: Carte de référence complète")
        
        if figsize is None:
            figsize = PLOT_PARAMS['figure_size']
        
        fig, ax = plt.subplots(1, 1, figsize=figsize)
        
        # Créer la carte de base complète
        self.create_senegal_base_map(ax, show_cities=True, show_regions=True,
                                   show_climate_zones=True, title=title)
        
        # Légendes complètes
        legend_elements = []
        
        # Légende des villes
        legend_elements.extend([
            plt.Line2D([0], [0], marker='s', color='w', markerfacecolor='red',
                      markersize=8, label='Capitale (Dakar)'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='blue',
                      markersize=6, label='Capitales régionales'),
            plt.Line2D([0], [0], marker='^', color='w', markerfacecolor='purple',
                      markersize=6, label='Villes religieuses'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='darkgreen',
                      markersize=4, label='Autres villes')
        ])
        
        # Légende des zones
        legend_elements.extend([
            patches.Patch(facecolor='lightblue', alpha=0.3, label='Zone océanique'),
            patches.Patch(facecolor='black', alpha=0.8, label='Frontières nationales'),
            patches.Patch(facecolor='gray', alpha=0.5, label='Limites régionales')
        ])
        
        ax.legend(handles=legend_elements, loc='upper left', 
                 bbox_to_anchor=(0.02, 0.98), fontsize=10)
        
        # Informations complémentaires
        info_text = f"""RÉPUBLIQUE DU SÉNÉGAL

🌍 Coordonnées géographiques:
   {self.bounds['lat_min']}°N - {self.bounds['lat_max']}°N
   {abs(self.bounds['lon_max'])}°W - {abs(self.bounds['lon_min'])}°W

🏛️  Divisions administratives:
   • {len(self.geo.REGIONS)} régions
   • ~{sum(len(r['departements']) for r in self.geo.REGIONS.values())} départements
   • {len(self.geo.CITIES)} villes principales

🌡️  Zones climatiques:
   • Sahélienne (Nord)
   • Soudano-sahélienne (Centre)
   • Soudanienne (Sud)
   • Côtière (Ouest)
        """
        
        ax.text(0.72, 0.02, info_text, transform=ax.transAxes,
               fontsize=9, verticalalignment='bottom',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='lightyellow', alpha=0.9))
        
        # Sauvegarder
        output_path = self._save_plot('reference_map', fig)
        return output_path
    
    def _save_plot(self, plot_key: str, fig) -> str:
        """Sauvegarde un graphique avec gestion des erreurs."""
        try:
            output_path = get_output_path(plot_key)
            fig.savefig(output_path, dpi=PLOT_PARAMS['dpi'], bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            print(f"   ✅ Sauvegardé: {output_path}")
            plt.close(fig)
            return output_path
        except Exception as e:
            # Fallback
            fallback_path = f"outputs/visualizations/{plot_key}.png"
            fig.savefig(fallback_path, dpi=PLOT_PARAMS['dpi'], bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            print(f"   ✅ Sauvegardé (fallback): {fallback_path}")
            plt.close(fig)
            return fallback_path
    
    def create_all_geographic_visualizations(self, df_events: pd.DataFrame) -> Dict[str, str]:
        """
        Génère toutes les visualisations géographiques (sans zones climatiques).
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Dict[str, str]: Chemins des fichiers générés
        """
        print("🗺️  GÉNÉRATION COMPLÈTE DES VISUALISATIONS GÉOGRAPHIQUES")
        print("=" * 60)
        
        generated_files = {}
        
        try:
            # 1. Carte de référence
            generated_files['reference_map'] = self.create_reference_map()
            
            # 2. Distribution spatiale des événements
            if not df_events.empty:
                generated_files['spatial_distribution'] = self.create_events_spatial_map(df_events)
                
                # 3. Analyse régionale détaillée (zones climatiques supprimées)
                generated_files['regional_analysis'] = self.create_regional_detailed_analysis(df_events)
            
            print(f"\n✅ TOUTES LES VISUALISATIONS GÉOGRAPHIQUES GÉNÉRÉES!")
            print(f"   Nombre de cartes créées: {len(generated_files)}")
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
class SenegalMapVisualizer(EnhancedSenegalMapVisualizer):
    """Alias pour compatibilité avec l'ancien nom."""
    
    def add_geographic_references(self, ax, event_lat: Optional[float] = None,
                                event_lon: Optional[float] = None):
        """Version simplifiée pour compatibilité."""
        self.create_senegal_base_map(ax, show_cities=True, show_regions=True)
        
        # Marquer l'événement si fourni
        if event_lat is not None and event_lon is not None:
            ax.plot(event_lon, event_lat, '*', color='yellow', markersize=15,
                   markeredgecolor='black', markeredgewidth=1.5, 
                   label='Centroïde événement', zorder=10)
            ax.legend()


def create_geographic_summary_plot(df_events: pd.DataFrame) -> str:
    """
    Fonction de convenance pour créer un résumé géographique rapide.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        str: Chemin du fichier sauvegardé
    """
    visualizer = EnhancedSenegalMapVisualizer()
    return visualizer.create_events_spatial_map(df_events)


def create_climate_zones_plot(df_events: pd.DataFrame) -> str:
    """
    Fonction de convenance pour l'analyse des zones climatiques.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        str: Chemin du fichier sauvegardé
    """
    visualizer = EnhancedSenegalMapVisualizer()
    return visualizer.create_climate_zones_analysis(df_events)


def create_regional_analysis_plot(df_events: pd.DataFrame) -> str:
    """
    Fonction de convenance pour l'analyse régionale.
    
    Args:
        df_events (pd.DataFrame): DataFrame des événements
        
    Returns:
        str: Chemin du fichier sauvegardé
    """
    visualizer = EnhancedSenegalMapVisualizer()
    return visualizer.create_regional_detailed_analysis(df_events)


class GeographicAnalyzer:
    """
    Classe utilitaire pour analyser la distribution géographique des événements.
    """
    
    def __init__(self):
        self.geo = SenegalGeography()
        self.visualizer = EnhancedSenegalMapVisualizer()
    
    def analyze_geographic_patterns(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyse complète des patterns géographiques.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            
        Returns:
            Dict[str, Any]: Résultats de l'analyse
        """
        print("🔍 Analyse des patterns géographiques")
        
        if df_events.empty:
            return {'status': 'no_data', 'message': 'Aucun événement à analyser'}
        
        analysis = {
            'total_events': len(df_events),
            'geographic_coverage': {},
            'intensity_patterns': {},
            'seasonal_patterns': {},
            'hotspots': {},
            'recommendations': []
        }
        
        # 1. Couverture géographique
        if 'centroid_region' in df_events.columns:
            analysis['geographic_coverage'] = self._analyze_geographic_coverage(df_events)
        
        # 2. Patterns d'intensité
        if all(col in df_events.columns for col in ['centroid_region', 'max_precip', 'coverage_percent']):
            analysis['intensity_patterns'] = self._analyze_intensity_patterns(df_events)
        
        # 3. Patterns saisonniers par zone
        if 'centroid_climate_zone' in df_events.columns:
            analysis['seasonal_patterns'] = self._analyze_seasonal_patterns(df_events)
        
        # 4. Identification des hotspots
        if all(col in df_events.columns for col in ['centroid_lat', 'centroid_lon']):
            analysis['hotspots'] = self._identify_hotspots(df_events)
        
        # 5. Recommandations
        analysis['recommendations'] = self._generate_recommendations(analysis)
        
        return analysis
    
    def _analyze_geographic_coverage(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse la couverture géographique."""
        total_regions = len(self.geo.REGIONS)
        affected_regions = df_events['centroid_region'].nunique()
        region_counts = df_events['centroid_region'].value_counts()
        
        return {
            'total_regions': total_regions,
            'affected_regions': affected_regions,
            'coverage_percentage': (affected_regions / total_regions) * 100,
            'most_affected_region': region_counts.index[0] if len(region_counts) > 0 else None,
            'least_affected_regions': [r for r in self.geo.REGIONS.keys() 
                                     if r not in df_events['centroid_region'].values],
            'region_distribution': region_counts.to_dict(),
            'concentration_index': self._calculate_concentration_index(region_counts)
        }
    
    def _analyze_intensity_patterns(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse les patterns d'intensité par région."""
        regional_stats = df_events.groupby('centroid_region').agg({
            'max_precip': ['mean', 'max', 'std'],
            'coverage_percent': ['mean', 'max'],
            'max_anomaly': ['mean', 'max']
        }).round(2)
        
        # Identifier les régions avec les plus fortes intensités
        mean_precip_by_region = regional_stats[('max_precip', 'mean')].sort_values(ascending=False)
        
        return {
            'regional_statistics': regional_stats.to_dict(),
            'highest_intensity_regions': mean_precip_by_region.head(5).to_dict(),
            'intensity_variability': regional_stats[('max_precip', 'std')].to_dict(),
            'coverage_leaders': regional_stats[('coverage_percent', 'mean')].sort_values(ascending=False).head(5).to_dict()
        }
    
    def _analyze_seasonal_patterns(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Analyse les patterns saisonniers par zone climatique."""
        if 'phase' not in df_events.columns:
            df_events['phase'] = df_events['month'].apply(get_phase_from_month)
        
        seasonal_climate = df_events.groupby(['centroid_climate_zone', 'phase']).size().unstack(fill_value=0)
        
        # Préférences saisonnières par zone
        preferences = {}
        for zone in seasonal_climate.index:
            zone_data = seasonal_climate.loc[zone]
            dominant_phase = zone_data.idxmax()
            preferences[zone] = {
                'dominant_phase': dominant_phase,
                'phase_distribution': zone_data.to_dict(),
                'seasonality_strength': zone_data.max() / zone_data.sum() if zone_data.sum() > 0 else 0
            }
        
        return {
            'climate_seasonal_matrix': seasonal_climate.to_dict(),
            'zone_preferences': preferences,
            'overall_seasonality': df_events.groupby('phase').size().to_dict()
        }
    
    def _identify_hotspots(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Identifie les hotspots géographiques d'événements extrêmes."""
        # Clustering simple basé sur la densité spatiale
        try:
            from sklearn.cluster import DBSCAN
            
            coords = df_events[['centroid_lat', 'centroid_lon']].values
            
            # DBSCAN pour identifier les clusters
            clustering = DBSCAN(eps=0.5, min_samples=3).fit(coords)
            labels = clustering.labels_
            
            # Analyser les clusters
            unique_labels = set(labels)
            hotspots = {}
            
            for label in unique_labels:
                if label == -1:  # Bruit
                    continue
                
                cluster_mask = labels == label
                cluster_events = df_events[cluster_mask]
                
                hotspots[f'hotspot_{label}'] = {
                    'center_lat': cluster_events['centroid_lat'].mean(),
                    'center_lon': cluster_events['centroid_lon'].mean(),
                    'event_count': len(cluster_events),
                    'avg_intensity': cluster_events['max_precip'].mean(),
                    'avg_coverage': cluster_events['coverage_percent'].mean(),
                    'dominant_region': cluster_events['centroid_region'].mode().iloc[0] if not cluster_events['centroid_region'].mode().empty else 'Unknown'
                }
            
            return {
                'hotspots_identified': len(hotspots),
                'hotspot_details': hotspots,
                'noise_events': (labels == -1).sum(),
                'clustering_method': 'DBSCAN'
            }
        
        except ImportError:
            # Fallback sans sklearn
            return self._identify_hotspots_simple(df_events)
    
    def _identify_hotspots_simple(self, df_events: pd.DataFrame) -> Dict[str, Any]:
        """Identification simple des hotspots sans sklearn."""
        # Grille simple pour identifier les zones de forte densité
        lat_bins = np.linspace(df_events['centroid_lat'].min(), 
                              df_events['centroid_lat'].max(), 5)
        lon_bins = np.linspace(df_events['centroid_lon'].min(), 
                              df_events['centroid_lon'].max(), 5)
        
        # Compter les événements par cellule de grille
        lat_indices = np.digitize(df_events['centroid_lat'], lat_bins) - 1
        lon_indices = np.digitize(df_events['centroid_lon'], lon_bins) - 1
        
        grid_counts = {}
        for i, (lat_idx, lon_idx) in enumerate(zip(lat_indices, lon_indices)):
            key = f"{lat_idx}_{lon_idx}"
            if key not in grid_counts:
                grid_counts[key] = []
            grid_counts[key].append(i)
        
        # Identifier les cellules avec le plus d'événements
        hotspots = {}
        for key, event_indices in grid_counts.items():
            if len(event_indices) >= 3:  # Seuil minimum
                cluster_events = df_events.iloc[event_indices]
                lat_idx, lon_idx = map(int, key.split('_'))
                
                hotspots[f'grid_hotspot_{key}'] = {
                    'center_lat': cluster_events['centroid_lat'].mean(),
                    'center_lon': cluster_events['centroid_lon'].mean(),
                    'event_count': len(cluster_events),
                    'avg_intensity': cluster_events['max_precip'].mean(),
                    'avg_coverage': cluster_events['coverage_percent'].mean(),
                    'grid_cell': key
                }
        
        return {
            'hotspots_identified': len(hotspots),
            'hotspot_details': hotspots,
            'clustering_method': 'simple_grid'
        }
    
    def _calculate_concentration_index(self, region_counts: pd.Series) -> float:
        """Calcule un index de concentration géographique (type Gini)."""
        if len(region_counts) <= 1:
            return 1.0
        
        # Coefficient de Gini simplifié
        sorted_counts = region_counts.sort_values()
        n = len(sorted_counts)
        index = np.arange(1, n + 1)
        
        gini = (2 * np.sum(index * sorted_counts)) / (n * np.sum(sorted_counts)) - (n + 1) / n
        return gini
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Génère des recommandations basées sur l'analyse."""
        recommendations = []
        
        # Couverture géographique
        coverage = analysis.get('geographic_coverage', {})
        if coverage.get('coverage_percentage', 0) < 50:
            recommendations.append("Étendre la surveillance aux régions moins couvertes")
        
        concentration_index = coverage.get('concentration_index', 0)
        if concentration_index > 0.6:
            recommendations.append("Les événements sont très concentrés géographiquement - approfondir l'analyse locale")
        
        # Hotspots
        hotspots = analysis.get('hotspots', {})
        if hotspots.get('hotspots_identified', 0) > 0:
            recommendations.append(f"Attention particulière aux {hotspots['hotspots_identified']} hotspots identifiés")
        
        # Patterns d'intensité
        intensity = analysis.get('intensity_patterns', {})
        if intensity.get('highest_intensity_regions'):
            top_region = list(intensity['highest_intensity_regions'].keys())[0]
            recommendations.append(f"Surveillance renforcée recommandée pour la région {top_region}")
        
        return recommendations
    
    def generate_geographic_report(self, df_events: pd.DataFrame, 
                                 output_path: str = None) -> str:
        """
        Génère un rapport géographique complet.
        
        Args:
            df_events (pd.DataFrame): DataFrame des événements
            output_path (str, optional): Chemin de sortie du rapport
            
        Returns:
            str: Contenu du rapport
        """
        analysis = self.analyze_geographic_patterns(df_events)
        
        report = []
        report.append("=" * 80)
        report.append("RAPPORT D'ANALYSE GÉOGRAPHIQUE - ÉVÉNEMENTS EXTRÊMES")
        report.append("=" * 80)
        report.append(f"Date de génération: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Nombre total d'événements analysés: {analysis['total_events']}")
        report.append("")
        
        # Couverture géographique
        coverage = analysis.get('geographic_coverage', {})
        if coverage:
            report.append("1. COUVERTURE GÉOGRAPHIQUE")
            report.append("-" * 30)
            report.append(f"   Régions du Sénégal: {coverage['total_regions']}")
            report.append(f"   Régions affectées: {coverage['affected_regions']}")
            report.append(f"   Taux de couverture: {coverage['coverage_percentage']:.1f}%")
            report.append(f"   Région la plus affectée: {coverage['most_affected_region']}")
            report.append(f"   Index de concentration: {coverage['concentration_index']:.3f}")
            report.append("")
        
        # Hotspots
        hotspots = analysis.get('hotspots', {})
        if hotspots.get('hotspots_identified', 0) > 0:
            report.append("2. HOTSPOTS IDENTIFIÉS")
            report.append("-" * 25)
            report.append(f"   Nombre de hotspots: {hotspots['hotspots_identified']}")
            
            for hotspot_name, details in hotspots['hotspot_details'].items():
                report.append(f"   📍 {hotspot_name}:")
                report.append(f"      Position: {details['center_lat']:.2f}°N, {details['center_lon']:.2f}°E")
                report.append(f"      Événements: {details['event_count']}")
                report.append(f"      Intensité moyenne: {details['avg_intensity']:.1f} mm")
                report.append(f"      Région dominante: {details['dominant_region']}")
            report.append("")
        
        # Patterns d'intensité
        intensity = analysis.get('intensity_patterns', {})
        if intensity:
            report.append("3. PATTERNS D'INTENSITÉ")
            report.append("-" * 25)
            highest_regions = intensity.get('highest_intensity_regions', {})
            report.append("   Régions à plus forte intensité:")
            for i, (region, intensity_val) in enumerate(list(highest_regions.items())[:5], 1):
                report.append(f"      {i}. {region}: {intensity_val:.1f} mm")
            report.append("")
        
        # Recommandations
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            report.append("4. RECOMMANDATIONS")
            report.append("-" * 20)
            for i, rec in enumerate(recommendations, 1):
                report.append(f"   {i}. {rec}")
            report.append("")
        
        # Fin du rapport
        report.append("=" * 80)
        report.append("FIN DU RAPPORT GÉOGRAPHIQUE")
        report.append("=" * 80)
        
        report_content = "\n".join(report)
        
        # Sauvegarder si chemin spécifié
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"✅ Rapport géographique généré: {output_path}")
        
        return report_content


if __name__ == "__main__":
    print("🗺️  Module de visualisation géographique amélioré")
    print("=" * 60)
    print("Ce module contient les outils pour:")
    print("• Créer des cartes de référence complètes du Sénégal")
    print("• Visualiser la distribution spatiale des événements extrêmes")
    print("• Analyser les patterns par régions administratives")
    print("• Étudier la répartition par zones climatiques")
    print("• Identifier les hotspots géographiques")
    print("• Générer des rapports d'analyse géographique")
    print()
    print("🆕 Nouvelles fonctionnalités:")
    print("• Intégration complète avec SenegalGeography")
    print("• Cartes multi-niveaux (régions, départements, zones climatiques)")
    print("• Analyse de hotspots avec clustering")
    print("• Métriques de concentration géographique")
    print("• Rapports automatisés")
    print()
    print("📊 Utilisation:")
    print("visualizer = EnhancedSenegalMapVisualizer()")
    print("files = visualizer.create_all_geographic_visualizations(df_events)")
    print()
    print("analyzer = GeographicAnalyzer()")
    print("analysis = analyzer.analyze_geographic_patterns(df_events)")
    print("report = analyzer.generate_geographic_report(df_events)")
    print()
    print("✅ Module prêt à l'utilisation!")