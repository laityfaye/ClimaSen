#!/usr/bin/env python3
# src/visualization/teleconnections_plots.py
"""
Module de visualisation pour l'analyse des téléconnexions climatiques - VERSION CORRIGÉE.

Ce module crée des graphiques compatibles avec la structure des résultats
de la version scientifiquement corrigée.

Auteur: [Votre nom]
Date: [Date]
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import numpy as np
import pandas as pd
from pathlib import Path
import warnings
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings('ignore')

# Configuration des graphiques
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")

class TeleconnectionsVisualizerCorrected:
    """
    Visualisateur pour l'analyse des téléconnexions climatiques - VERSION CORRIGÉE.
    Compatible avec la nouvelle structure des résultats.
    """
    
    def __init__(self, analyzer):
        """
        Initialise le visualisateur.
        
        Args:
            analyzer: Instance de TeleconnectionsAnalyzer avec les résultats corrigés
        """
        self.analyzer = analyzer
        
        # Configuration des couleurs
        self.colors = {
            'IOD': '#1f77b4',      # Bleu
            'Nino34': '#ff7f0e',   # Orange  
            'TNA': '#2ca02c',      # Vert
            'SAOD': '#d62728',     # Rouge
            'ATL3': '#9467bd'      # Violet
        }
        
        # Configuration des styles
        self.fig_size = (15, 10)
        self.dpi = 300
        self.font_size = 12
        
    def plot_lag_correlations_corrected(self, output_file: str):
        """
        CORRIGÉ: Graphique des corrélations en fonction du décalage temporel.
        Compatible avec la nouvelle structure des résultats.
        
        Args:
            output_file (str): Chemin du fichier de sortie
        """
        print("   📊 Création: Corrélations avec décalages (VERSION CORRIGÉE)...")
        
        if not hasattr(self.analyzer, 'correlations_results') or not self.analyzer.correlations_results:
            print("      ⚠️  Pas de données de corrélations avec décalages")
            return
        
        # CORRECTION : Adapter à la nouvelle structure (index -> metric -> lag)
        lag_data = {}
        
        for index_name, index_results in self.analyzer.correlations_results.items():
            # Prendre la première métrique disponible (généralement 'frequency')
            metric_names = list(index_results.keys())
            if not metric_names:
                continue
                
            # Utiliser la métrique avec le plus de données significatives
            best_metric = metric_names[0]
            max_significant = 0
            
            for metric_name, lag_results in index_results.items():
                significant_count = sum(1 for lag_data_item in lag_results.values() 
                                      if lag_data_item.get('pearson', {}).get('is_significant_corrected', False))
                if significant_count > max_significant:
                    max_significant = significant_count
                    best_metric = metric_name
            
            # Extraire les données pour cette métrique
            lag_results = index_results[best_metric]
            
            lags = []
            correlations = []
            p_values = []
            is_significant = []
            is_physical_optimal = []
            
            for lag_key, lag_result in lag_results.items():
                if lag_key.startswith('lag_'):
                    lag_months = int(lag_key.split('_')[1])
                    pearson_data = lag_result.get('pearson', {})
                    
                    correlation = pearson_data.get('correlation', np.nan)
                    if not np.isnan(correlation):
                        lags.append(lag_months)
                        correlations.append(correlation)
                        p_values.append(pearson_data.get('p_value_corrected', pearson_data.get('p_value', 1.0)))
                        is_significant.append(pearson_data.get('is_significant_corrected', False))
                        is_physical_optimal.append(lag_result.get('is_physical_optimal', False))
            
            if lags:
                lag_data[index_name] = {
                    'lags': lags,
                    'correlations': correlations,
                    'p_values': p_values,
                    'is_significant': is_significant,
                    'is_physical_optimal': is_physical_optimal,
                    'metric_used': best_metric
                }
        
        if not lag_data:
            print("      ⚠️  Aucune donnée de corrélation valide")
            return
        
        # Créer le graphique
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=self.fig_size, dpi=self.dpi)
        fig.suptitle('Corrélations avec Décalages Temporels (Version Scientifiquement Corrigée)\n'
                    'Indices Climatiques vs Événements Extrêmes au Sénégal', 
                    fontsize=16, fontweight='bold')
        
        # Graphique 1: Coefficients de corrélation
        for index_name, data in lag_data.items():
            color = self.colors.get(index_name, '#333333')
            
            # Ligne principale
            ax1.plot(data['lags'], data['correlations'], 
                    'o-', color=color, label=f"{index_name} ({data['metric_used']})", 
                    linewidth=2.5, markersize=6)
            
            # NOUVEAU : Marquer les corrélations significatives après correction FDR
            significant_indices = [i for i, is_sig in enumerate(data['is_significant']) if is_sig]
            if significant_indices:
                sig_lags = [data['lags'][i] for i in significant_indices]
                sig_corrs = [data['correlations'][i] for i in significant_indices]
                ax1.scatter(sig_lags, sig_corrs, 
                           color=color, s=150, marker='*', 
                           edgecolors='white', linewidth=2,
                           zorder=5, label=f'{index_name} significatif')
            
            # NOUVEAU : Marquer les lags physiques optimaux
            optimal_indices = [i for i, is_opt in enumerate(data['is_physical_optimal']) if is_opt]
            if optimal_indices:
                opt_lags = [data['lags'][i] for i in optimal_indices]
                opt_corrs = [data['correlations'][i] for i in optimal_indices]
                ax1.scatter(opt_lags, opt_corrs, 
                           color=color, s=100, marker='s', 
                           edgecolors='black', linewidth=1,
                           zorder=4, alpha=0.7)
        
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax1.axhline(y=0.15, color='orange', linestyle='--', alpha=0.5, label='Seuil climatologique faible')
        ax1.axhline(y=-0.15, color='orange', linestyle='--', alpha=0.5)
        ax1.axhline(y=0.25, color='red', linestyle='--', alpha=0.5, label='Seuil climatologique modéré')
        ax1.axhline(y=-0.25, color='red', linestyle='--', alpha=0.5)
        
        ax1.set_xlabel('Décalage (mois)', fontsize=self.font_size)
        ax1.set_ylabel('Coefficient de Corrélation', fontsize=self.font_size)
        ax1.set_title('Évolution des Corrélations par Décalage (Après Correction FDR)', fontsize=14)
        ax1.legend(loc='upper right', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # Graphique 2: Significativité (p-values corrigées)
        for index_name, data in lag_data.items():
            color = self.colors.get(index_name, '#333333')
            ax2.semilogy(data['lags'], data['p_values'], 
                        'o-', color=color, label=f"{index_name}",
                        linewidth=2, markersize=5)
        
        ax2.axhline(y=0.05, color='red', linestyle='--', 
                   label='Seuil significativité (p=0.05)')
        ax2.axhline(y=0.01, color='darkred', linestyle='--', 
                   label='Haute significativité (p=0.01)')
        
        ax2.set_xlabel('Décalage (mois)', fontsize=self.font_size)
        ax2.set_ylabel('Valeur p corrigée (échelle log)', fontsize=self.font_size)
        ax2.set_title('Significativité Statistique (Après Correction FDR)', fontsize=14)
        ax2.legend(loc='upper right', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        # Ajout d'annotations améliorées
        ax1.text(0.02, 0.98, '★ = Significatif après correction FDR\n□ = Lag physique optimal', 
                transform=ax1.transAxes, fontsize=10, 
                bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
                verticalalignment='top')
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        plt.close()
        
        print(f"      ✅ Sauvegardé: {output_path}")
    
    def plot_phase_correlations_corrected(self, output_file: str):
        """
        CORRIGÉ: Graphique des corrélations par phases de la saison des pluies.
        Compatible avec la nouvelle structure des résultats.
        
        Args:
            output_file (str): Chemin du fichier de sortie
        """
        print("   🌧️  Création: Corrélations par phases (VERSION CORRIGÉE)...")
        
        if not hasattr(self.analyzer, 'phase_correlations') or not self.analyzer.phase_correlations:
            print("      ⚠️  Pas de données de corrélations par phases")
            return
        
        # CORRECTION : Adapter à la nouvelle structure (phase -> metric -> index)
        phase_names = {
            'Phase_1_debut': 'Début\n(Mai-Juin)',
            'Phase_2_pleine': 'Pleine\n(Juillet-Août)',
            'Phase_3_fin': 'Fin\n(Septembre-Octobre)'
        }
        
        # Collecter toutes les corrélations par phase
        all_phase_data = []
        
        for phase_key, phase_results in self.analyzer.phase_correlations.items():
            if phase_key in phase_names:
                for metric_name, metric_results in phase_results.items():
                    for index_name, corr_data in metric_results.items():
                        all_phase_data.append({
                            'phase': phase_key,
                            'metric': metric_name,
                            'index': index_name,
                            'correlation': corr_data.get('correlation', np.nan),
                            'p_value': corr_data.get('p_value_corrected', corr_data.get('p_value', 1.0)),
                            'is_significant': corr_data.get('is_significant_corrected', False),
                            'variance_explained': corr_data.get('variance_explained', 0)
                        })
        
        if not all_phase_data:
            print("      ⚠️  Aucune donnée de corrélation par phase")
            return
        
        # Créer le DataFrame
        df_phase = pd.DataFrame(all_phase_data)
        
        # Créer le graphique
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), dpi=self.dpi)
        fig.suptitle('Corrélations par Phases de la Saison des Pluies (Version Scientifiquement Corrigée)\n'
                    'Indices Climatiques vs Événements Extrêmes au Sénégal',
                    fontsize=16, fontweight='bold')
        
        # Graphique 1: Heatmap des corrélations pour la métrique principale
        # Choisir la métrique avec le plus de corrélations significatives
        metric_counts = df_phase[df_phase['is_significant']]['metric'].value_counts()
        main_metric = metric_counts.index[0] if len(metric_counts) > 0 else df_phase['metric'].iloc[0]
        
        df_main_metric = df_phase[df_phase['metric'] == main_metric]
        
        if len(df_main_metric) > 0:
            pivot_corr = df_main_metric.pivot(index='index', columns='phase', values='correlation')
            pivot_corr = pivot_corr.reindex(columns=['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin'])
            pivot_corr.columns = [phase_names[col] for col in pivot_corr.columns if col in phase_names]
            
            im1 = ax1.imshow(pivot_corr.values, cmap='RdBu_r', aspect='auto', 
                            vmin=-0.3, vmax=0.3)  # Ajusté pour corrélations plus faibles
            
            # Configuration de la heatmap
            ax1.set_xticks(range(len(pivot_corr.columns)))
            ax1.set_xticklabels(pivot_corr.columns, fontsize=12)
            ax1.set_yticks(range(len(pivot_corr.index)))
            ax1.set_yticklabels(pivot_corr.index, fontsize=12)
            ax1.set_title(f'Matrice des Corrélations - {main_metric}', fontsize=14, fontweight='bold')
            
            # Ajouter les valeurs dans les cellules avec marquage significativité
            for i in range(len(pivot_corr.index)):
                for j in range(len(pivot_corr.columns)):
                    value = pivot_corr.iloc[i, j]
                    if not np.isnan(value):
                        # Vérifier si significatif après correction
                        phase_key = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin'][j]
                        index_name = pivot_corr.index[i]
                        
                        matching_row = df_main_metric[
                            (df_main_metric['phase'] == phase_key) & 
                            (df_main_metric['index'] == index_name)
                        ]
                        
                        is_sig = matching_row['is_significant'].iloc[0] if len(matching_row) > 0 else False
                        
                        text_color = 'white' if abs(value) > 0.15 else 'black'
                        text = f'{value:.3f}'  # Plus de précision pour les faibles corrélations
                        if is_sig:
                            text += '*'
                        
                        ax1.text(j, i, text, ha='center', va='center', 
                                color=text_color, fontweight='bold', fontsize=10)
            
            # Colorbar pour la heatmap
            cbar1 = plt.colorbar(im1, ax=ax1, shrink=0.8)
            cbar1.set_label('Coefficient de Corrélation', fontsize=12)
        else:
            ax1.text(0.5, 0.5, 'Aucune donnée\ndisponible', 
                    transform=ax1.transAxes, ha='center', va='center',
                    fontsize=14, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray"))
        
        # Graphique 2: Barplot des corrélations significatives (toutes métriques)
        significant_corr = df_phase[df_phase['is_significant'] == True].copy()
        
        if len(significant_corr) > 0:
            # Trier par force de corrélation
            significant_corr = significant_corr.sort_values('variance_explained', ascending=False)
            
            # Créer des positions pour les barres
            x_pos = range(len(significant_corr))
            bar_values = significant_corr['correlation'].values
            bar_colors = [self.colors.get(idx, '#333333') for idx in significant_corr['index']]
            
            bars = ax2.bar(x_pos, bar_values, color=bar_colors, alpha=0.8, edgecolor='black')
            
            # Labels pour les barres
            bar_labels = []
            for _, row in significant_corr.iterrows():
                phase_short = phase_names[row['phase']].split('\n')[0]
                bar_labels.append(f"{row['index']}\n{row['metric']}\n{phase_short}")
            
            ax2.set_xticks(x_pos)
            ax2.set_xticklabels(bar_labels, rotation=45, ha='right', fontsize=9)
            ax2.set_ylabel('Coefficient de Corrélation', fontsize=12)
            ax2.set_title('Corrélations Significatives (Après Correction FDR)', fontsize=14, fontweight='bold')
            ax2.axhline(y=0, color='black', linestyle='-', alpha=0.5)
            ax2.grid(True, alpha=0.3, axis='y')
            
            # Ajouter les valeurs et variance expliquée sur les barres
            for i, (bar, (_, row)) in enumerate(zip(bars, significant_corr.iterrows())):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height + np.sign(height)*0.005,
                        f'{height:.3f}\n({row["variance_explained"]:.1f}%)', 
                        ha='center', va='bottom' if height > 0 else 'top',
                        fontweight='bold', fontsize=9)
        else:
            ax2.text(0.5, 0.5, 'Aucune corrélation\nsignificative après\ncorrection FDR', 
                    transform=ax2.transAxes, ha='center', va='center',
                    fontsize=14, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightcoral", alpha=0.7))
            ax2.set_title('Corrélations Significatives (Après Correction FDR)', fontsize=14, fontweight='bold')
        
        # Note explicative améliorée
        fig.text(0.02, 0.02, '* = Significatif après correction FDR (p < 0.05)\nVariance expliquée entre parenthèses', 
                fontsize=10, style='italic')
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        plt.close()
        
        print(f"      ✅ Sauvegardé: {output_path}")
    
    def plot_enso_analysis_corrected(self, output_file: str):
        """
        CORRIGÉ: Graphique de l'analyse spécifique ENSO.
        
        Args:
            output_file (str): Chemin du fichier de sortie
        """
        print("   🌊 Création: Analyse ENSO (VERSION CORRIGÉE)...")
        
        if not hasattr(self.analyzer, 'climate_indices') or self.analyzer.climate_indices is None:
            print("      ⚠️  Données d'indices climatiques non disponibles")
            return
        
        if 'Nino34' not in self.analyzer.climate_indices.columns:
            print("      ⚠️  Indice Nino34 non disponible")
            return
        
        # Récupérer les données
        nino34 = self.analyzer.climate_indices['Nino34'].dropna()
        
        # Calculer les métriques d'événements
        if hasattr(self.analyzer, 'extreme_events') and self.analyzer.extreme_events is not None:
            # Utiliser les métriques climatologiques calculées
            try:
                event_metrics = self.analyzer.calculate_event_metrics_climatological()
                events_monthly = event_metrics['frequency']  # Utiliser la fréquence
            except:
                # Fallback vers l'ancienne méthode
                events_monthly = self.analyzer.extreme_events.groupby(
                    self.analyzer.extreme_events['date'].dt.to_period('M')
                ).size()
                events_monthly.index = events_monthly.index.to_timestamp()
        else:
            print("      ⚠️  Données d'événements extrêmes non disponibles")
            return
        
        # Créer le graphique
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(18, 12), dpi=self.dpi)
        fig.suptitle('Analyse de l\'Impact ENSO sur les Événements Extrêmes (Version Corrigée)\n'
                    'Indice Niño 3.4 vs Précipitations Extrêmes au Sénégal',
                    fontsize=16, fontweight='bold')
        
        # Graphique 1: Série temporelle de Niño 3.4
        dates = nino34.index
        ax1.plot(dates, nino34.values, color='#ff7f0e', linewidth=1.5, alpha=0.8)
        
        # Zones El Niño et La Niña
        ax1.axhline(y=0.5, color='red', linestyle='--', alpha=0.7, label='Seuil El Niño (+0.5°C)')
        ax1.axhline(y=-0.5, color='blue', linestyle='--', alpha=0.7, label='Seuil La Niña (-0.5°C)')
        ax1.fill_between(dates, 0.5, nino34.values.max(), where=(nino34.values >= 0.5), 
                        color='red', alpha=0.2, label='Conditions El Niño')
        ax1.fill_between(dates, -0.5, nino34.values.min(), where=(nino34.values <= -0.5),
                        color='blue', alpha=0.2, label='Conditions La Niña')
        
        ax1.set_ylabel('Anomalie SST Niño 3.4 (°C)', fontsize=12)
        ax1.set_title('Évolution de l\'Indice Niño 3.4', fontsize=14, fontweight='bold')
        ax1.legend(fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # Graphique 2: Fréquence mensuelle des événements
        common_dates = events_monthly.index.intersection(nino34.index)
        events_aligned = events_monthly.loc[common_dates]
        
        ax2.bar(events_aligned.index, events_aligned.values, width=20, 
               color='#2ca02c', alpha=0.7, edgecolor='darkgreen')
        ax2.set_ylabel('Nombre d\'Événements Extrêmes', fontsize=12)
        ax2.set_title('Fréquence Mensuelle des Événements Extrêmes', fontsize=14, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='y')
        
        # Graphique 3: Scatterplot Niño 3.4 vs Événements avec corrélation corrigée
        nino34_aligned = nino34.loc[common_dates]
        
        # CORRECTION : Récupérer la corrélation depuis les résultats corrigés
        nino34_correlation = np.nan
        nino34_p_value = 1.0
        
        if hasattr(self.analyzer, 'correlations_results') and 'Nino34' in self.analyzer.correlations_results:
            # Chercher la corrélation avec la fréquence au lag optimal
            for lag_key, lag_data in self.analyzer.correlations_results['Nino34'].get('frequency', {}).items():
                pearson_data = lag_data.get('pearson', {})
                if pearson_data.get('is_significant_corrected', False):
                    nino34_correlation = pearson_data['correlation']
                    nino34_p_value = pearson_data.get('p_value_corrected', pearson_data.get('p_value', 1.0))
                    break
        
        # Si pas trouvé dans les résultats, calculer directement
        if np.isnan(nino34_correlation):
            from scipy.stats import pearsonr
            if len(nino34_aligned) > 0 and len(events_aligned) > 0:
                nino34_correlation, nino34_p_value = pearsonr(nino34_aligned, events_aligned)
        
        scatter = ax3.scatter(nino34_aligned, events_aligned, 
                            c=nino34_aligned, cmap='RdBu_r', 
                            s=50, alpha=0.7, edgecolors='black', linewidth=0.5)
        
        # Ligne de tendance
        if not np.isnan(nino34_correlation):
            z = np.polyfit(nino34_aligned, events_aligned, 1)
            p = np.poly1d(z)
            ax3.plot(nino34_aligned.sort_values(), p(nino34_aligned.sort_values()), 
                    "r--", alpha=0.8, linewidth=2)
        
        ax3.set_xlabel('Indice Niño 3.4 (°C)', fontsize=12)
        ax3.set_ylabel('Nombre d\'Événements Extrêmes', fontsize=12)
        
        # Titre avec information de correction FDR
        corr_status = "Significatif" if nino34_p_value < 0.05 else "Non significatif"
        ax3.set_title(f'Corrélation Niño 3.4 vs Événements\nr = {nino34_correlation:.3f}, p = {nino34_p_value:.3f} ({corr_status})', 
                     fontsize=14, fontweight='bold')
        ax3.grid(True, alpha=0.3)
        
        # Colorbar pour le scatterplot
        cbar = plt.colorbar(scatter, ax=ax3, shrink=0.8)
        cbar.set_label('Indice Niño 3.4 (°C)', fontsize=10)
        
        # Graphique 4: Distribution par phases ENSO (version corrigée)
        try:
            # Utiliser la classification ENSO corrigée
            if hasattr(self.analyzer, 'identify_enso_events_oni_standard'):
                enso_events = self.analyzer.identify_enso_events_oni_standard()
            else:
                enso_events = self.analyzer.identify_enso_events()
        except:
            enso_events = {}
        
        if enso_events and any(key in enso_events for key in ['el_nino', 'la_nina', 'neutral']):
            phase_data = []
            
            for enso_type in ['el_nino', 'la_nina', 'neutral']:
                if enso_type in enso_events:
                    years = enso_events[enso_type]
                    # Compter les événements pour ces années
                    type_events = []
                    for year in years:
                        year_events = self.analyzer.extreme_events[
                            self.analyzer.extreme_events['year'] == year
                        ]
                        type_events.append(len(year_events))
                    
                    if type_events:
                        phase_data.append({
                            'type': enso_type,
                            'events': type_events,
                            'mean': np.mean(type_events),
                            'std': np.std(type_events),
                            'n_years': len(type_events)
                        })
            
            if phase_data:
                types = [d['type'] for d in phase_data]
                means = [d['mean'] for d in phase_data]
                stds = [d['std'] for d in phase_data]
                
                colors_enso = {'el_nino': 'red', 'la_nina': 'blue', 'neutral': 'gray'}
                bar_colors = [colors_enso.get(t, 'gray') for t in types]
                
                bars = ax4.bar(types, means, yerr=stds, color=bar_colors, 
                              alpha=0.7, capsize=5, edgecolor='black')
                
                # Ajouter les valeurs sur les barres
                for bar, mean, std, data in zip(bars, means, stds, phase_data):
                    ax4.text(bar.get_x() + bar.get_width()/2., bar.get_height() + std + 0.5,
                            f'{mean:.1f}±{std:.1f}\n(n={data["n_years"]})',
                            ha='center', va='bottom', fontweight='bold', fontsize=10)
                
                ax4.set_ylabel('Événements Extrêmes / An', fontsize=12)
                ax4.set_title('Fréquence Moyenne par Phase ENSO (Standards ONI)', fontsize=14, fontweight='bold')
                ax4.set_xticklabels(['El Niño', 'La Niña', 'Neutre'])
                ax4.grid(True, alpha=0.3, axis='y')
                
                # Test statistique si données suffisantes
                if len(phase_data) >= 2:
                    from scipy.stats import f_oneway
                    all_events = [d['events'] for d in phase_data]
                    if all(len(events) > 1 for events in all_events):
                        f_stat, p_val = f_oneway(*all_events)
                        ax4.text(0.02, 0.98, f'ANOVA: F={f_stat:.2f}, p={p_val:.3f}', 
                                transform=ax4.transAxes, fontsize=10,
                                bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"),
                                verticalalignment='top')
            else:
                ax4.text(0.5, 0.5, 'Classification ENSO\ninsuffisante', 
                        transform=ax4.transAxes, ha='center', va='center',
                        fontsize=14, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray"))
        else:
            ax4.text(0.5, 0.5, 'Données ENSO\nnon disponibles', 
                    transform=ax4.transAxes, ha='center', va='center',
                    fontsize=14, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray"))
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        plt.close()
        
        print(f"      ✅ Sauvegardé: {output_path}")
    
    def plot_teleconnections_summary_corrected(self, output_file: str):
        """
        CORRIGÉ: Graphique de résumé des téléconnexions avec validation physique.
        
        Args:
            output_file (str): Chemin du fichier de sortie
        """
        print("   📈 Création: Résumé des téléconnexions (VERSION CORRIGÉE)...")
        
        # Créer un graphique de synthèse amélioré
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(18, 12), dpi=self.dpi)
        fig.suptitle('Synthèse de l\'Analyse des Téléconnexions Climatiques (Version Scientifiquement Corrigée)\n'
                    'Impact des Indices Climatiques sur les Événements Extrêmes au Sénégal',
                    fontsize=16, fontweight='bold')
        
        # Graphique 1: Performance par indice (variance expliquée max)
        if hasattr(self.analyzer, 'correlations_results') and self.analyzer.correlations_results:
            
            indices_performance = {}
            
            for index_name, index_results in self.analyzer.correlations_results.items():
                max_variance = 0
                significant_count = 0
                physical_optimal_count = 0
                
                for metric_results in index_results.values():
                    for lag_data in metric_results.values():
                        pearson_data = lag_data.get('pearson', {})
                        
                        if pearson_data.get('is_significant_corrected', False):
                            significant_count += 1
                            variance = pearson_data.get('variance_explained', 0)
                            max_variance = max(max_variance, variance)
                            
                            if lag_data.get('is_physical_optimal', False):
                                physical_optimal_count += 1
                
                indices_performance[index_name] = {
                    'max_variance': max_variance,
                    'significant_count': significant_count,
                    'physical_optimal_count': physical_optimal_count
                }
            
            if indices_performance:
                indices = list(indices_performance.keys())
                variances = [indices_performance[idx]['max_variance'] for idx in indices]
                colors = [self.colors.get(idx, '#333333') for idx in indices]
                
                bars = ax1.bar(indices, variances, color=colors, alpha=0.8, edgecolor='black')
                ax1.set_ylabel('Variance Expliquée Max (%)', fontsize=12)
                ax1.set_title('Performance par Indice Climatique\n(Variance Expliquée Maximale)', 
                             fontsize=14, fontweight='bold')
                ax1.grid(True, alpha=0.3, axis='y')
                
                # Ajouter les valeurs sur les barres avec info physique
                for bar, idx in zip(bars, indices):
                    height = bar.get_height()
                    physical_count = indices_performance[idx]['physical_optimal_count']
                    total_sig = indices_performance[idx]['significant_count']
                    
                    if height > 0:
                        ax1.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                                f'{height:.1f}%\n({physical_count}/{total_sig} opt)', 
                                ha='center', va='bottom', fontweight='bold', fontsize=10)
                
                # Ligne de seuil climatologique
                ax1.axhline(y=2, color='orange', linestyle='--', alpha=0.7, 
                           label='Seuil climatologique (2%)')
                ax1.axhline(y=5, color='red', linestyle='--', alpha=0.7, 
                           label='Seuil pertinence (5%)')
                ax1.legend()
        
        # Graphique 2: Distribution des lags significatifs
        if hasattr(self.analyzer, 'correlations_results') and self.analyzer.correlations_results:
            
            all_significant_lags = []
            physical_optimal_lags = []
            
            for index_name, index_results in self.analyzer.correlations_results.items():
                for metric_results in index_results.values():
                    for lag_key, lag_data in metric_results.items():
                        if lag_key.startswith('lag_'):
                            lag_num = int(lag_key.split('_')[1])
                            pearson_data = lag_data.get('pearson', {})
                            
                            if pearson_data.get('is_significant_corrected', False):
                                all_significant_lags.append(lag_num)
                                
                                if lag_data.get('is_physical_optimal', False):
                                    physical_optimal_lags.append(lag_num)
            
            if all_significant_lags:
                # Histogramme des lags
                max_lag = max(all_significant_lags)
                bins = range(0, max_lag + 2)
                
                ax2.hist(all_significant_lags, bins=bins, alpha=0.7, color='skyblue', 
                        edgecolor='black', label=f'Tous significatifs (n={len(all_significant_lags)})')
                
                if physical_optimal_lags:
                    ax2.hist(physical_optimal_lags, bins=bins, alpha=0.9, color='darkgreen', 
                            edgecolor='black', label=f'Lags physiques optimaux (n={len(physical_optimal_lags)})')
                
                ax2.set_xlabel('Décalage (mois)', fontsize=12)
                ax2.set_ylabel('Nombre de Corrélations Significatives', fontsize=12)
                ax2.set_title('Distribution des Lags Significatifs\n(Après Correction FDR)', 
                             fontsize=14, fontweight='bold')
                ax2.legend()
                ax2.grid(True, alpha=0.3, axis='y')
            else:
                ax2.text(0.5, 0.5, 'Aucune corrélation\nsignificative', 
                        transform=ax2.transAxes, ha='center', va='center',
                        fontsize=14, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightcoral"))
        
        # Graphique 3: Validation physique vs statistique
        if hasattr(self.analyzer, 'correlations_results') and self.analyzer.correlations_results:
            
            # Compter par indice
            validation_data = {}
            
            for index_name in self.analyzer.correlations_results.keys():
                total_significant = 0
                physical_validated = 0
                
                for metric_results in self.analyzer.correlations_results[index_name].values():
                    for lag_data in metric_results.values():
                        pearson_data = lag_data.get('pearson', {})
                        
                        if pearson_data.get('is_significant_corrected', False):
                            total_significant += 1
                            
                            if lag_data.get('is_physical_optimal', False):
                                physical_validated += 1
                
                if total_significant > 0:
                    validation_data[index_name] = {
                        'total': total_significant,
                        'validated': physical_validated,
                        'rate': physical_validated / total_significant * 100
                    }
            
            if validation_data:
                indices = list(validation_data.keys())
                rates = [validation_data[idx]['rate'] for idx in indices]
                colors = [self.colors.get(idx, '#333333') for idx in indices]
                
                bars = ax3.bar(indices, rates, color=colors, alpha=0.8, edgecolor='black')
                ax3.set_ylabel('Taux de Validation Physique (%)', fontsize=12)
                ax3.set_title('Validation Physique des Téléconnexions\n(% aux Lags Physiques Optimaux)', 
                             fontsize=14, fontweight='bold')
                ax3.grid(True, alpha=0.3, axis='y')
                ax3.set_ylim(0, 100)
                
                # Ligne de seuil de validation
                ax3.axhline(y=50, color='orange', linestyle='--', alpha=0.7, 
                           label='Seuil validation (50%)')
                ax3.legend()
                
                # Ajouter les valeurs
                for bar, idx in zip(bars, indices):
                    height = bar.get_height()
                    validated = validation_data[idx]['validated']
                    total = validation_data[idx]['total']
                    
                    ax3.text(bar.get_x() + bar.get_width()/2., height + 2,
                            f'{height:.0f}%\n({validated}/{total})', 
                            ha='center', va='bottom', fontweight='bold', fontsize=10)
        
        # Graphique 4: Timeline des téléconnexions par métrique
        if hasattr(self.analyzer, 'correlations_results') and self.analyzer.correlations_results:
            
            # Organiser par métrique
            metrics_data = {}
            
            for index_name, index_results in self.analyzer.correlations_results.items():
                for metric_name, metric_results in index_results.items():
                    if metric_name not in metrics_data:
                        metrics_data[metric_name] = {}
                    
                    best_correlation = 0
                    best_lag = 0
                    is_significant = False
                    
                    for lag_key, lag_data in metric_results.items():
                        if lag_key.startswith('lag_'):
                            pearson_data = lag_data.get('pearson', {})
                            correlation = pearson_data.get('correlation', 0)
                            
                            if abs(correlation) > abs(best_correlation):
                                best_correlation = correlation
                                best_lag = int(lag_key.split('_')[1])
                                is_significant = pearson_data.get('is_significant_corrected', False)
                    
                    if best_correlation != 0:
                        metrics_data[metric_name][index_name] = {
                            'correlation': best_correlation,
                            'lag': best_lag,
                            'significant': is_significant
                        }
            
            if metrics_data:
                # Créer un graphique en timeline
                y_pos = 0
                metric_positions = {}
                
                for metric_name, indices_data in metrics_data.items():
                    metric_positions[metric_name] = y_pos
                    
                    for index_name, data in indices_data.items():
                        color = self.colors.get(index_name, '#333333')
                        alpha = 1.0 if data['significant'] else 0.3
                        
                        # Barre horizontale proportionnelle à la corrélation
                        width = abs(data['correlation']) * 10  # Facteur d'échelle
                        
                        bar = ax4.barh(y_pos, width, left=data['lag'], height=0.6, 
                                      color=color, alpha=alpha, edgecolor='black')
                        
                        # Label de l'indice
                        ax4.text(data['lag'] + width/2, y_pos, index_name, 
                                ha='center', va='center', fontsize=9, 
                                fontweight='bold', color='white' if alpha > 0.5 else 'black')
                    
                    y_pos += 1
                
                # Configuration des axes
                ax4.set_yticks(list(metric_positions.values()))
                ax4.set_yticklabels(list(metric_positions.keys()))
                ax4.set_xlabel('Décalage (mois) et Force de Corrélation', fontsize=12)
                ax4.set_title('Vue d\'Ensemble par Métrique\n(Largeur ∝ |Corrélation|)', 
                             fontsize=14, fontweight='bold')
                ax4.grid(True, alpha=0.3, axis='x')
                
                # Légende pour la significativité
                ax4.text(0.98, 0.02, 'Opaque = Significatif\nTransparent = Non significatif', 
                        transform=ax4.transAxes, fontsize=10,
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"),
                        horizontalalignment='right', verticalalignment='bottom')
        
        plt.tight_layout()
        
        # Sauvegarder
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=self.dpi, bbox_inches='tight')
        plt.close()
        
        print(f"      ✅ Sauvegardé: {output_path}")
    
    def create_all_visualizations_corrected(self, output_dir: str):
        """
        Crée toutes les visualisations des téléconnexions (VERSION CORRIGÉE).
        
        Args:
            output_dir (str): Répertoire de sortie
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        print("🎨 Génération complète des visualisations téléconnexions (VERSION CORRIGÉE)...")
        
        # Liste des graphiques à créer avec nouvelles méthodes
        visualizations = [
            ('lag_correlations_corrected.png', self.plot_lag_correlations_corrected),
            ('phase_correlations_corrected.png', self.plot_phase_correlations_corrected),
            ('enso_analysis_corrected.png', self.plot_enso_analysis_corrected),
            ('teleconnections_summary_corrected.png', self.plot_teleconnections_summary_corrected)
        ]
        
        created_files = []
        
        for filename, plot_function in visualizations:
            try:
                output_file = output_path / filename
                plot_function(str(output_file))
                created_files.append(str(output_file))
            except Exception as e:
                print(f"   ❌ Erreur création {filename}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n✅ Visualisations créées: {len(created_files)}")
        for file_path in created_files:
            print(f"   • {Path(file_path).name}")
        
        return created_files


# CLASSE DE COMPATIBILITÉ POUR L'ANCIEN INTERFACE
class TeleconnectionsVisualizer(TeleconnectionsVisualizerCorrected):
    """
    Classe de compatibilité qui redirige vers les méthodes corrigées.
    """
    
    def plot_lag_correlations(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.plot_lag_correlations_corrected(output_file)
    
    def plot_phase_correlations(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.plot_phase_correlations_corrected(output_file)
    
    def plot_enso_analysis(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.plot_enso_analysis_corrected(output_file)
    
    def plot_teleconnections_summary(self, output_file: str):
        """Redirige vers la version corrigée."""
        return self.plot_teleconnections_summary_corrected(output_file)
    
    def create_all_visualizations(self, output_dir: str):
        """Redirige vers la version corrigée."""
        return self.create_all_visualizations_corrected(output_dir)


if __name__ == "__main__":
    print("🎨 Module de visualisation pour téléconnexions (VERSION CORRIGÉE)")
    print("=" * 70)
    print("Ce module crée des graphiques compatibles avec la structure corrigée:")
    print("• Corrélations avec décalages temporels (après correction FDR)")
    print("• Corrélations par phases (avec validation physique)")
    print("• Analyse spécifique ENSO (standards ONI)")
    print("• Synthèse avec métriques de validation")
    print("\nNouvelles fonctionnalités:")
    print("• Marquage des lags physiques optimaux")
    print("• Affichage variance expliquée")
    print("• Validation croisée physique-statistique")
    print("• Correction FDR intégrée")
    print("\nUtilisation:")
    print("  from src.visualization.teleconnections_plots import TeleconnectionsVisualizerCorrected")
    print("  viz = TeleconnectionsVisualizerCorrected(analyzer)")
    print("  viz.create_all_visualizations_corrected('output_dir')")