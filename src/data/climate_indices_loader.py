#!/usr/bin/env python3
# src/data/climate_indices_loader.py
"""
Module de chargement et préparation des indices climatiques pour l'analyse des téléconnexions.

Ce module charge les indices IOD, Nino34, et TNA depuis vos fichiers existants
et les prépare pour l'analyse des corrélations avec les événements extrêmes.

Auteur: [Votre nom]
Date: [Date]
"""

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional
import warnings

warnings.filterwarnings('ignore')

class ClimateIndicesLoader:
    """
    Classe pour charger et préprocesser les indices climatiques.
    """
    
    def __init__(self, data_path: str = None):
        """
        Initialise le loader d'indices climatiques.
        
        Args:
            data_path (str): Chemin vers le dossier contenant les fichiers d'indices
        """
        if data_path is None:
            # Utiliser le chemin par défaut basé sur votre architecture
            project_root = Path(__file__).parent.parent.parent
            self.data_path = project_root / "data" / "raw" / "climate_indices"
        else:
            self.data_path = Path(data_path)
        
        # Configuration des fichiers d'indices basée sur vos noms
        self.indices_files = {
            'IOD': 'IOD_index.xlsx',
            'Nino34': 'Nino34_index.csv', 
            'TNA': 'TNA_index.csv'
        }
        
        # Stockage des données chargées
        self.indices_data = {}
        self.combined_data = None
        
    def load_iod_index(self) -> pd.Series:
        """
        Charge l'indice IOD depuis le fichier Excel.
        Format attendu: colonnes Year, Jan, Feb, ..., Dec
        
        Returns:
            pd.Series: Série temporelle de l'indice IOD
        """
        print("🔄 Chargement de l'indice IOD...")
        
        file_path = self.data_path / self.indices_files['IOD']
        
        try:
            # Chargement du fichier Excel
            df = pd.read_excel(file_path)
            
            print(f"   Colonnes disponibles: {df.columns.tolist()}")
            
            # Vérifier la présence des colonnes mensuelles
            month_cols = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            
            available_months = [col for col in month_cols if col in df.columns]
            print(f"   ✅ Colonnes mensuelles trouvées: {available_months}")
            
            if 'Year' not in df.columns:
                raise ValueError("Colonne 'Year' manquante dans le fichier IOD")
            
            # Filtrer les années valides
            df_clean = df[(df['Year'] >= 1870) & (df['Year'] <= 2024)].copy()
            print(f"   ✅ Années valides: {df_clean['Year'].min()}-{df_clean['Year'].max()}")
            
            # Conversion en série temporelle
            iod_series = []
            dates = []
            
            for _, row in df_clean.iterrows():
                year = int(row['Year'])
                for i, month in enumerate(available_months, 1):
                    value = row[month]
                    if pd.notna(value) and value != -99.99:  # Exclusion valeurs manquantes
                        date = pd.Timestamp(year, i, 1)
                        dates.append(date)
                        iod_series.append(float(value))
            
            # Création de la série pandas
            iod_ts = pd.Series(iod_series, index=dates, name='IOD')
            iod_ts = iod_ts.sort_index()
            
            print(f"   ✅ IOD traité: {len(iod_ts)} enregistrements")
            print(f"   📊 Période: {iod_ts.index.min()} à {iod_ts.index.max()}")
            print(f"   📊 Statistiques: μ={iod_ts.mean():.3f}, σ={iod_ts.std():.3f}")
            
            return iod_ts
            
        except Exception as e:
            print(f"❌ Erreur lors du chargement IOD: {e}")
            return pd.Series(dtype=float)
    
    def load_nino34_index(self) -> pd.Series:
        """
        Charge l'indice Nino34 depuis le fichier CSV.
        Format attendu: colonnes Date, Valeur
        
        Returns:
            pd.Series: Série temporelle de l'indice Nino34
        """
        print("🔄 Chargement de l'indice Nino34...")
        
        file_path = self.data_path / self.indices_files['Nino34']
        
        try:
            # Chargement du fichier CSV
            df = pd.read_csv(file_path)
            
            print(f"   Colonnes disponibles: {df.columns.tolist()}")
            
            # Identifier la colonne de valeurs (généralement la deuxième)
            date_col = df.columns[0]
            value_col = df.columns[1]
            
            print(f"   Traitement format Date-Valeur pour Nino34")
            
            # Conversion des dates
            dates = pd.to_datetime(df[date_col], errors='coerce')
            values = pd.to_numeric(df[value_col], errors='coerce')
            
            # Nettoyage des données
            valid_mask = dates.notna() & values.notna() & (values != -99.99)
            
            clean_dates = dates[valid_mask]
            clean_values = values[valid_mask]
            
            print(f"   ✅ {len(clean_dates)} dates valides après conversion")
            
            # Suppression des valeurs aberrantes (|z-score| > 4)
            z_scores = np.abs((clean_values - clean_values.mean()) / clean_values.std())
            outlier_mask = z_scores <= 4
            
            final_dates = clean_dates[outlier_mask]
            final_values = clean_values[outlier_mask]
            
            outliers_removed = len(clean_values) - len(final_values)
            print(f"   🧹 NINO34: {outliers_removed} valeurs aberrantes supprimées")
            
            # Création de la série pandas
            nino34_ts = pd.Series(final_values.values, index=final_dates, name='Nino34')
            nino34_ts = nino34_ts.sort_index()
            
            print(f"   ✅ Nino34 traité: {len(nino34_ts)} enregistrements valides")
            print(f"   📊 Période: {nino34_ts.index.min()} à {nino34_ts.index.max()}")
            print(f"   📊 Statistiques: μ={nino34_ts.mean():.3f}, σ={nino34_ts.std():.3f}, "
                  f"min={nino34_ts.min():.3f}, max={nino34_ts.max():.3f}")
            
            return nino34_ts
            
        except Exception as e:
            print(f"❌ Erreur lors du chargement Nino34: {e}")
            return pd.Series(dtype=float)
    
    def load_tna_index(self) -> pd.Series:
        """
        Charge l'indice TNA (Tropical North Atlantic) depuis le fichier CSV.
        Format attendu: colonnes Date, Valeur
        
        Returns:
            pd.Series: Série temporelle de l'indice TNA
        """
        print("🔄 Chargement de l'indice TNA...")
        
        file_path = self.data_path / self.indices_files['TNA']
        
        try:
            # Chargement du fichier CSV
            df = pd.read_csv(file_path)
            
            print(f"   Colonnes disponibles: {df.columns.tolist()}")
            
            # Identifier les colonnes
            date_col = df.columns[0]
            value_col = df.columns[1]
            
            print(f"   Traitement format Date-Valeur pour TNA")
            
            # Conversion des dates et valeurs
            dates = pd.to_datetime(df[date_col], errors='coerce')
            values = pd.to_numeric(df[value_col], errors='coerce')
            
            # Nettoyage des données
            valid_mask = dates.notna() & values.notna() & (values != -99.99)
            
            clean_dates = dates[valid_mask]
            clean_values = values[valid_mask]
            
            print(f"   ✅ {len(clean_dates)} dates valides après conversion")
            
            # Suppression des valeurs aberrantes
            z_scores = np.abs((clean_values - clean_values.mean()) / clean_values.std())
            outlier_mask = z_scores <= 4
            
            final_dates = clean_dates[outlier_mask]
            final_values = clean_values[outlier_mask]
            
            outliers_removed = len(clean_values) - len(final_values)
            print(f"   🧹 TNA: {outliers_removed} valeurs aberrantes supprimées")
            
            # Création de la série pandas
            tna_ts = pd.Series(final_values.values, index=final_dates, name='TNA')
            tna_ts = tna_ts.sort_index()
            
            print(f"   ✅ TNA traité: {len(tna_ts)} enregistrements valides")
            print(f"   📊 Période: {tna_ts.index.min()} à {tna_ts.index.max()}")
            print(f"   📊 Statistiques: μ={tna_ts.mean():.3f}, σ={tna_ts.std():.3f}, "
                  f"min={tna_ts.min():.3f}, max={tna_ts.max():.3f}")
            
            return tna_ts
            
        except Exception as e:
            print(f"❌ Erreur lors du chargement TNA: {e}")
            return pd.Series(dtype=float)
    
    def load_all_indices(self) -> Dict[str, pd.Series]:
        """
        Charge tous les indices climatiques.
        
        Returns:
            Dict[str, pd.Series]: Dictionnaire contenant tous les indices
        """
        print("\n" + "="*80)
        print("🌊 CHARGEMENT DES INDICES CLIMATIQUES")
        print("="*80)
        
        indices = {}
        
        # Chargement de chaque indice
        indices['IOD'] = self.load_iod_index()
        print("✅ IOD chargé avec succès\n")
        
        indices['Nino34'] = self.load_nino34_index()
        print("✅ Nino34 chargé avec succès\n")
        
        indices['TNA'] = self.load_tna_index()
        print("✅ TNA chargé avec succès\n")
        
        # Vérification que tous les indices sont chargés
        successful_indices = {name: series for name, series in indices.items() 
                            if not series.empty}
        
        print(f"📊 RÉSUMÉ DU CHARGEMENT:")
        print(f"   Indices chargés avec succès: {len(successful_indices)}/3")
        for name, series in successful_indices.items():
            print(f"   • {name}: {len(series)} observations "
                  f"({series.index.min().strftime('%Y-%m')} à {series.index.max().strftime('%Y-%m')})")
        
        self.indices_data = successful_indices
        return successful_indices
    
    def create_combined_dataset(self, start_date: str = '1981-01-01', 
                               end_date: str = '2023-12-31') -> pd.DataFrame:
        """
        Crée un dataset combiné avec tous les indices pour la période d'étude.
        
        Args:
            start_date (str): Date de début (format YYYY-MM-DD)
            end_date (str): Date de fin (format YYYY-MM-DD)
            
        Returns:
            pd.DataFrame: Dataset combiné avec tous les indices
        """
        print("\n🔄 CRÉATION DU DATASET COMBINÉ")
        print("-" * 50)
        
        if not self.indices_data:
            print("❌ Aucun indice chargé. Lancez d'abord load_all_indices()")
            return pd.DataFrame()
        
        # Période d'étude
        period_start = pd.Timestamp(start_date)
        period_end = pd.Timestamp(end_date)
        
        # Création de l'index temporel mensuel
        monthly_index = pd.date_range(start=period_start, end=period_end, freq='MS')
        
        # DataFrame vide avec l'index temporel
        combined_df = pd.DataFrame(index=monthly_index)
        
        # Ajout de chaque indice avec interpolation
        for name, series in self.indices_data.items():
            print(f"   Intégration de l'indice {name}...")
            
            # Resampling mensuel si nécessaire
            if series.index.freq != 'MS':
                series_monthly = series.resample('MS').mean()
            else:
                series_monthly = series
            
            # Intersection avec la période d'étude
            series_period = series_monthly.loc[period_start:period_end]
            
            # Ajout au dataframe combiné
            combined_df[name] = series_period
            
            # Statistiques de couverture
            coverage = (combined_df[name].notna().sum() / len(combined_df)) * 100
            print(f"     Couverture: {coverage:.1f}% ({combined_df[name].notna().sum()}/{len(combined_df)} mois)")
        
        # Interpolation des valeurs manquantes (méthode conservative)
        print(f"\n🔧 Traitement des valeurs manquantes...")
        
        before_interpolation = combined_df.isnull().sum().sum()
        
        # Interpolation linéaire limitée (max 3 mois consécutifs)
        combined_df_interpolated = combined_df.interpolate(method='linear', limit=3)
        
        after_interpolation = combined_df_interpolated.isnull().sum().sum()
        
        print(f"   Valeurs manquantes avant interpolation: {before_interpolation}")
        print(f"   Valeurs manquantes après interpolation: {after_interpolation}")
        print(f"   Valeurs interpolées: {before_interpolation - after_interpolation}")
        
        # Statistiques finales
        print(f"\n📊 DATASET COMBINÉ FINAL:")
        print(f"   Période: {combined_df_interpolated.index.min().strftime('%Y-%m')} à "
              f"{combined_df_interpolated.index.max().strftime('%Y-%m')}")
        print(f"   Nombre de mois: {len(combined_df_interpolated)}")
        print(f"   Indices disponibles: {list(combined_df_interpolated.columns)}")
        
        # Statistiques descriptives
        print(f"\n   Statistiques descriptives:")
        for col in combined_df_interpolated.columns:
            stats = combined_df_interpolated[col].describe()
            print(f"     {col}: μ={stats['mean']:.3f}, σ={stats['std']:.3f}, "
                  f"min={stats['min']:.3f}, max={stats['max']:.3f}")
        
        self.combined_data = combined_df_interpolated
        return combined_df_interpolated
    
    def create_lagged_features(self, max_lag: int = 6) -> pd.DataFrame:
        """
        Crée des features avec décalages temporels pour l'analyse prédictive.
        
        Args:
            max_lag (int): Nombre maximum de mois de décalage
            
        Returns:
            pd.DataFrame: Dataset avec features décalées
        """
        print(f"\n🔄 CRÉATION DES FEATURES AVEC DÉCALAGES (lag 0-{max_lag})")
        print("-" * 50)
        
        if self.combined_data is None:
            print("❌ Dataset combiné non disponible. Lancez d'abord create_combined_dataset()")
            return pd.DataFrame()
        
        lagged_features = []
        feature_names = []
        
        for col in self.combined_data.columns:
            for lag in range(max_lag + 1):
                # Création de la feature décalée
                lagged_series = self.combined_data[col].shift(lag)
                lagged_features.append(lagged_series)
                
                # Nom de la feature
                if lag == 0:
                    feature_name = f"{col}_current"
                else:
                    feature_name = f"{col}_lag{lag}"
                
                feature_names.append(feature_name)
        
        # Combinaison en DataFrame
        lagged_df = pd.concat(lagged_features, axis=1, keys=feature_names)
        
        # Suppression des lignes avec trop de valeurs manquantes
        # (on garde seulement les lignes avec au moins 70% de données)
        threshold = len(lagged_df.columns) * 0.7
        lagged_df_clean = lagged_df.dropna(thresh=int(threshold))
        
        print(f"   Features créées: {len(feature_names)}")
        print(f"   Mois avec données suffisantes: {len(lagged_df_clean)}/{len(lagged_df)}")
        print(f"   Période effective: {lagged_df_clean.index.min().strftime('%Y-%m')} à "
              f"{lagged_df_clean.index.max().strftime('%Y-%m')}")
        
        return lagged_df_clean
    
    def save_processed_data(self, output_dir: str = None):
        """
        Sauvegarde les données traitées.
        
        Args:
            output_dir (str): Répertoire de sortie
        """
        if output_dir is None:
            project_root = Path(__file__).parent.parent.parent
            output_dir = project_root / "data" / "processed"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n💾 SAUVEGARDE DES DONNÉES TRAITÉES")
        print("-" * 50)
        
        # Sauvegarde du dataset combiné
        if self.combined_data is not None:
            combined_file = output_dir / "climate_indices_combined.csv"
            self.combined_data.to_csv(combined_file)
            print(f"   ✅ Dataset combiné: {combined_file}")
        
        # Sauvegarde des séries individuelles
        for name, series in self.indices_data.items():
            series_file = output_dir / f"climate_index_{name.lower()}.csv"
            series.to_csv(series_file, header=True)
            print(f"   ✅ Indice {name}: {series_file}")
        
        print("✅ Sauvegarde terminée avec succès")


def load_climate_indices(data_path: str = None) -> Tuple[Dict[str, pd.Series], pd.DataFrame]:
    """
    Fonction de convenance pour charger tous les indices climatiques.
    
    Args:
        data_path (str): Chemin vers les fichiers d'indices
        
    Returns:
        Tuple[Dict[str, pd.Series], pd.DataFrame]: (indices individuels, dataset combiné)
    """
    loader = ClimateIndicesLoader(data_path)
    
    # Chargement des indices
    indices = loader.load_all_indices()
    
    # Création du dataset combiné
    combined_dataset = loader.create_combined_dataset()
    
    # Sauvegarde
    loader.save_processed_data()
    
    return indices, combined_dataset


if __name__ == "__main__":
    # Test du module
    print("Test du module de chargement des indices climatiques")
    print("=" * 80)
    
    # Exemple d'utilisation
    loader = ClimateIndicesLoader()
    
    # Chargement complet
    indices, combined_df = load_climate_indices()
    
    # Création des features décalées
    lagged_features = loader.create_lagged_features(max_lag=6)
    
    print(f"\n🎯 RÉSULTATS FINAUX:")
    print(f"   Indices chargés: {len(indices)}")
    print(f"   Dataset combiné: {combined_df.shape}")
    print(f"   Features décalées: {lagged_features.shape}")
    
    print("\n✅ Module testé avec succès!")