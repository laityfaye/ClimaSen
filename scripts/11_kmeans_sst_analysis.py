"""
Script d'analyse de classification non supervisée par K-Means
sur les champs SST associés aux événements extrêmes.

Auteur: Équipe de recherche climatologique
Date: 2024
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any
import json
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, davies_bouldin_score
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

# Imports du projet
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.config.settings import (
    PROCESSED_DATA_DIR, OUTPUT_DIR, VISUALIZATION_DIR, RAW_DATA_DIR, EXPORT_DIR,
    get_output_path, create_output_directories
)
from src.data.sst_loader import load_sst_for_extreme_events
from src.config.settings import PHASE_COLORS, PLOT_PARAMS


class KMeansSSTAnalyzer:
    """
    Analyseur de classification non supervisée par K-Means
    sur les champs SST vectorisés des événements extrêmes.
    """
    
    def __init__(self, n_clusters_range: Tuple[int, int] = (2, 20),
                 random_state: int = 42):
        """
        Initialise l'analyseur K-Means.
        
        Args:
            n_clusters_range (Tuple[int, int]): Plage de nombres de clusters à tester
            random_state (int): Graine aléatoire pour reproductibilité
        """
        self.n_clusters_range = n_clusters_range
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.kmeans_model = None
        self.pca_model = None
        self.n_pca_components = None
        self.optimal_k = None
        self.cluster_labels = None
        self.sst_matrix = None
        self.sst_normalized = None
        self.dates = None
        self.metadata = None
        self.events_df = None
        self.events_df_loaded = None  # DataFrame filtré avec uniquement les événements chargés

        # Résultats de l'analyse
        self.clustering_results = {}
        self.evaluation_metrics = {}
        self.centroids_sst = None
        
        print("[INFO] Analyseur K-Means SST initialisé")
        print(f"   Plage de clusters: {n_clusters_range[0]}-{n_clusters_range[1]}")
    
    def load_data(self, events_file: Path = None) -> bool:
        """
        Charge les données d'événements extrêmes et les champs SST associés.
        
        Args:
            events_file (Path, optional): Chemin vers le fichier CSV des événements.
                                        Par défaut: data/processed/extreme_events_phases_senegal.csv
        
        Returns:
            bool: True si le chargement a réussi
        """
        print("\n" + "="*80)
        print("ÉTAPE 1: CHARGEMENT DES DONNÉES")
        print("="*80)
        
        # Charger les événements extrêmes
        if events_file is None:
            events_file = PROCESSED_DATA_DIR / "extreme_events_phases_senegal.csv"
        
        if not events_file.exists():
            print(f"[ERREUR] Fichier d'événements non trouvé: {events_file}")
            return False
        
        print(f"[CHARGEMENT] Chargement des événements extrêmes: {events_file.name}")
        self.events_df = pd.read_csv(events_file, parse_dates=['date'], index_col='date')
        
        print(f"[OK] {len(self.events_df)} événements chargés")
        print(f"   Période: {self.events_df.index.min().strftime('%Y-%m-%d')} à "
              f"{self.events_df.index.max().strftime('%Y-%m-%d')}")
        
        # Filtrer les événements de 1983 à 2023
        original_count = len(self.events_df)
        self.events_df = self.events_df[
            (self.events_df.index.year >= 1983) & (self.events_df.index.year <= 2023)
        ]
        filtered_count = len(self.events_df)
        
        if filtered_count < original_count:
            print(f"\n[INFO] Filtrage des événements: période 1983-2023")
            print(f"   [ATTENTION] {filtered_count} événements conservés (sur {original_count})")
            print(f"   Période filtrée: {self.events_df.index.min().strftime('%Y-%m-%d')} à "
                  f"{self.events_df.index.max().strftime('%Y-%m-%d')}")
        
        # Vérifier les années disponibles dans les fichiers SST
        sst_dir = RAW_DATA_DIR / "SST"
        if sst_dir.exists():
            sst_files = list(sst_dir.glob("*.nc"))
            available_years = set()
            for sst_file in sst_files:
                for year in range(1980, 2030):
                    if str(year) in sst_file.name:
                        available_years.add(year)
                        break
            
            if available_years:
                print(f"\n[INFO] Fichiers SST disponibles pour les années: {sorted(available_years)}")
                missing_years = set(range(1983, 2024)) - available_years
                if missing_years:
                    print(f"   [ATTENTION] Fichiers SST manquants pour les années: {sorted(missing_years)}")
                    print(f"   Les événements de ces années ne pourront pas être chargés")
                    
                    # Compter les événements par catégorie
                    events_with_sst = self.events_df[self.events_df.index.year.isin(available_years)]
                    events_without_sst = self.events_df[self.events_df.index.year.isin(missing_years)]
                    
                    print(f"\n   [STATS] RÉSUMÉ DE LA SITUATION:")
                    print(f"      - Evenements avec fichiers SST disponibles: {len(events_with_sst)}")
                    print(f"      - Evenements sans fichiers SST: {len(events_without_sst)}")
                    print(f"      - Total evenements 1983-2023: {len(self.events_df)}")
                    print(f"\n   [CONSEIL] POUR ANALYSER TOUS LES {len(self.events_df)} ÉVÉNEMENTS:")
                    print(f"      Ajoutez les {len(missing_years)} fichiers SST manquants dans:")
                    print(f"      {sst_dir}")
                    print(f"      Format attendu: sst_day_anom_YYYY.nc (ex: sst_day_anom_1985.nc)")
                    print(f"      Le code analysera automatiquement tous les événements une fois")
                    print(f"      les fichiers SST ajoutés. Aucune modification du code n'est nécessaire!")
        
        # Charger les champs SST
        print(f"\n[CHARGEMENT] Chargement des champs SST pour {len(self.events_df)} événements...")
        try:
            self.sst_matrix, self.dates, self.metadata = load_sst_for_extreme_events(
                self.events_df,
                sst_dir=None,  # Utilise le chemin par défaut
                variable=None  # Utilise la première variable disponible
            )
            
            print(f"[OK] Données SST chargées:")
            print(f"   Matrice: {self.sst_matrix.shape} (n_événements × n_pixels)")
            n_pixels = self.metadata['n_features']
            print(f"   Pixels (points de grille) par champ SST : {n_pixels:,}")
            print(f"   Forme des champs SST (lat × lon): {self.metadata.get('sst_shape', 'N/A')}")
            
            # Filtrer events_df pour ne garder que les événements effectivement chargés
            if self.dates is not None and len(self.dates) > 0:
                dates_set = set(self.dates)
                self.events_df_loaded = self.events_df[self.events_df.index.isin(dates_set)].copy()
                print(f"   Événements avec SST chargés: {len(self.events_df_loaded)} (sur {len(self.events_df)})")
                
                if len(self.events_df_loaded) < len(self.events_df):
                    print(f"\n   [ATTENTION] ATTENTION: Seulement {len(self.events_df_loaded)} événements analysés sur {len(self.events_df)}")
                    print(f"      Raison: Fichiers SST manquants pour certaines années")
                    print(f"      Pour analyser tous les événements, ajoutez les fichiers SST manquants")
            else:
                self.events_df_loaded = self.events_df.copy()
            
            return True
            
        except Exception as e:
            print(f"[ERREUR] Erreur lors du chargement SST: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _detrend_sst_pixels(self, matrix: np.ndarray) -> np.ndarray:
        """
        Retire la tendance lineaire inter-annuelle par pixel SST (vectorise).

        Pour chaque pixel j, ajuste y_j = a_j * annee + b_j sur l'ensemble des
        evenements et soustrait la composante de tendance a_j * (annee - annee_moy).
        Cela supprime le signal de rechauffement climatique commun a tous les pixels
        avant la PCA, de sorte que le K-Means partitionne des patterns de circulation
        plutot que des epoque froides vs. chaudes.

        Args:
            matrix (np.ndarray): Matrice (n_evenements x n_pixels), float32 ou float64.

        Returns:
            np.ndarray: Matrice detrendee en float32.
        """
        if self.dates is None or len(self.dates) == 0:
            print("   Avertissement: dates non disponibles, detrend ignore.")
            return matrix.astype(np.float32)

        years = np.array([pd.Timestamp(d).year for d in self.dates], dtype=np.float64)
        years_c = years - years.mean()
        denom = np.dot(years_c, years_c)
        if denom < 1e-10:
            return matrix.astype(np.float32)

        matrix_f64 = matrix.astype(np.float64)
        # Pentes OLS vectorisees : slope_j = (years_c . col_j) / ||years_c||^2
        slopes = (years_c @ matrix_f64) / denom        # (n_pixels,)
        detrended = matrix_f64 - np.outer(years_c, slopes)
        return detrended.astype(np.float32)

    def preprocess_data(self, pca_variance_threshold: float = 0.90,
                        detrend_sst: bool = False) -> bool:
        """
        Pretraite les donnees SST : normalisation puis reduction de dimensionnalite
        par PCA pour ameliorer la qualite du clustering.

        Args:
            pca_variance_threshold (float): Fraction de variance cumulee a conserver (defaut: 0.90)
            detrend_sst (bool): Si True, retire la tendance lineaire inter-annuelle
                par pixel avant la normalisation. Recommande pour separer les patterns
                de circulation du signal de rechauffement climatique (defaut: False).

        Returns:
            bool: True si le pretraitement a reussi
        """
        print("\n" + "="*80)
        print("ETAPE 2: PRETRAITEMENT DES DONNEES")
        print("="*80)

        if self.sst_matrix is None:
            print("Aucune donnee SST chargee")
            return False

        # --- 2a. Detrend lineaire inter-annuel (optionnel) ---
        if detrend_sst:
            print("Detrend lineaire inter-annuel par pixel SST...")
            matrix_raw = self._detrend_sst_pixels(self.sst_matrix)
            print(f"   Tendance lineaire (annee) retiree de {matrix_raw.shape[1]:,} pixels")
            print(f"   Les clusters refleront des patterns de circulation, "
                  f"non la tendance temporelle.")
        else:
            matrix_raw = self.sst_matrix.astype(np.float32)
            print("Note: detrend_sst=False — les clusters peuvent capturer partiellement")
            print("      la tendance de rechauffement SST (epoque froide vs. chaude).")
            print("      Relancez avec detrend_sst=True pour isoler les patterns de circulation.")

        # --- 2b. Normalisation (float64 pour precision, converti en float32 ensuite) ---
        print("Normalisation des donnees SST...")

        matrix_f64 = matrix_raw.astype(np.float64)
        mean = np.mean(matrix_f64, axis=0, keepdims=True)       # float64
        std  = np.std(matrix_f64,  axis=0, ddof=0, keepdims=True)  # float64
        std  = np.where(std == 0, 1.0, std)

        sst_normalized = ((matrix_f64 - mean) / std).astype(np.float32)  # retour float32

        # Verification NaN avant PCA (donnees manquantes, couverture OISST incomplete)
        n_nan = int(np.isnan(sst_normalized).sum())
        if n_nan > 0:
            print(f"   [ATTENTION] {n_nan} valeurs NaN dans la matrice SST normalisee.")
            print(f"   Remplacement par 0 (valeur normalisee neutre).")
            sst_normalized = np.nan_to_num(sst_normalized, nan=0.0)

        self.scaler_mean_  = mean.flatten().astype(np.float32)
        self.scaler_scale_ = std.flatten().astype(np.float32)

        print(f"   Donnees normalisees: {sst_normalized.shape}")
        print(f"   Moyenne: {np.mean(sst_normalized):.6f}, Ecart-type: {np.std(sst_normalized):.6f}")

        # --- 2c. Réduction de dimensionnalité par PCA ---
        n_samples, n_features = sst_normalized.shape
        print(f"\nReduction de dimensionnalite par PCA...")
        print(f"   Dimensions originales: {n_features} features pour {n_samples} echantillons")
        print(f"   Seuil de variance cumulee: {pca_variance_threshold:.0%}")

        # PCA avec seuil de variance direct (sklearn supporte float pour n_components).
        # Permet de ne retenir que les composantes expliquant `pca_variance_threshold`
        # de la variance sans calculer de composantes superflues.
        # Le solveur 'full' est requis pour les seuils flottants.
        max_components = min(n_samples - 1, n_features)
        pca_threshold = min(float(pca_variance_threshold), 1.0)

        self.pca_model = PCA(n_components=pca_threshold, svd_solver='full')
        try:
            sst_pca = self.pca_model.fit_transform(sst_normalized)
        except ValueError:
            # Fallback : le seuil demande plus de composantes que disponibles
            self.pca_model = PCA(n_components=min(max_components, 200))
            sst_pca = self.pca_model.fit_transform(sst_normalized)
            cum_var = np.cumsum(self.pca_model.explained_variance_ratio_)
            n_trunc = max(2, int(np.searchsorted(cum_var, pca_variance_threshold)) + 1)
            sst_pca = sst_pca[:, :n_trunc]

        n_components = max(self.pca_model.n_components_, 2)
        self.sst_matrix_scaled = sst_pca[:, :n_components].astype(np.float32)
        self.n_pca_components = n_components

        cumulative_variance = np.cumsum(self.pca_model.explained_variance_ratio_)
        print(f"   {n_components} composantes retenues")
        print(f"   Variance expliquee: {cumulative_variance[n_components - 1]:.1%}")
        print(f"   Reduction: {n_features} -> {n_components} dimensions "
              f"({n_components / n_features:.1%} des dimensions originales)")
        print(f"   Taille memoire: {self.sst_matrix_scaled.nbytes / (1024**2):.2f} MB")

        # Conserver aussi les données normalisées (pour les centroïdes SST)
        self.sst_normalized = sst_normalized

        return True
    
    @staticmethod
    def _find_elbow_geometric(k_values: list, inertias: list) -> int:
        """
        Détecte le coude par la méthode géométrique (distance maximale à la droite
        reliant le premier et le dernier point de la courbe d'inertie).

        C'est l'implémentation standard de la « méthode du coude » décrite dans
        la littérature (Thorndike, 1953 ; Satopää et al., 2011 « Kneedle »).

        Args:
            k_values: Liste des valeurs de k testées
            inertias: Inerties correspondantes

        Returns:
            int: Valeur de k au coude
        """
        # Normaliser les axes dans [0, 1] pour que la distance soit isotrope
        k_arr = np.array(k_values, dtype=np.float64)
        inertia_arr = np.array(inertias, dtype=np.float64)

        k_norm = (k_arr - k_arr.min()) / (k_arr.max() - k_arr.min())
        inertia_norm = (inertia_arr - inertia_arr.min()) / (inertia_arr.max() - inertia_arr.min() + 1e-12)

        # Droite entre le premier point (k_min) et le dernier point (k_max)
        p1 = np.array([k_norm[0], inertia_norm[0]])
        p2 = np.array([k_norm[-1], inertia_norm[-1]])

        # Distance de chaque point à cette droite
        line_vec = p2 - p1
        line_len = np.linalg.norm(line_vec)

        # Vectorise : distance de chaque point a la droite (produit vectoriel 2D)
        points = np.column_stack([k_norm, inertia_norm])  # (n_k, 2)
        d_vecs = p1 - points                               # (n_k, 2)
        distances = np.abs(
            line_vec[0] * d_vecs[:, 1] - line_vec[1] * d_vecs[:, 0]
        ) / (line_len + 1e-12)

        return int(k_values[int(np.argmax(distances))])

    def find_optimal_k(self, max_k: int = None, n_gap_bootstraps: int = 0) -> int:
        """
        Détermine le nombre optimal de clusters en combinant 3 méthodes :
          1. Méthode du coude   — distance géométrique maximale sur la courbe d'inertie
          2. Silhouette         — maximisation du score de silhouette
          3. Davies-Bouldin     — minimisation de l'indice DB

        Le k optimal final est sélectionné par **vote majoritaire** (3 voix).
        En cas d'ex aequo, le tiebreaker est : silhouette > coude.

        Args:
            max_k (int, optional): Nombre maximum de clusters à tester
            n_gap_bootstraps (int): Parametre inutilise, conserve pour compatibilite

        Returns:
            int: Nombre optimal de clusters
        """
        print("\n" + "="*80)
        print("ETAPE 3: DETERMINATION DU NOMBRE OPTIMAL DE CLUSTERS")
        print("         (Coude - Silhouette - Davies-Bouldin)")
        print("="*80)

        if self.sst_matrix_scaled is None:
            print("[ERREUR] Données non prétraitées")
            return None

        max_k = max_k or self.n_clusters_range[1]
        n_samples = self.sst_matrix_scaled.shape[0]
        max_k = min(max_k, n_samples - 1)
        k_range = list(range(self.n_clusters_range[0], max_k + 1))

        print(f"[RECHERCHE] Test de {len(k_range)} valeurs de k : {k_range}")
        print(f"   Methodes actives : coude, silhouette, Davies-Bouldin")

        inertias = []
        silhouette_scores = []
        db_scores = []

        for k in k_range:
            print(f"   k={k}...", end=" ", flush=True)

            kmeans = KMeans(n_clusters=k, random_state=self.random_state, n_init=20)
            labels = kmeans.fit_predict(self.sst_matrix_scaled)

            inertia = kmeans.inertia_
            sil_score = silhouette_score(self.sst_matrix_scaled, labels)
            db_score  = davies_bouldin_score(self.sst_matrix_scaled, labels)

            inertias.append(inertia)
            silhouette_scores.append(sil_score)
            db_scores.append(db_score)

            print(f"ok  sil={sil_score:.3f}  DB={db_score:.3f}")

        # --- Stocker toutes les métriques ---
        self.evaluation_metrics = {
            'k_range':                   [int(k) for k in k_range],
            'inertias':                  [float(v) for v in inertias],
            'silhouette_scores':         [float(v) for v in silhouette_scores],
            'davies_bouldin_scores':     [float(v) for v in db_scores],
        }

        # --- k optimal par chaque méthode ---
        k_elbow          = self._find_elbow_geometric(k_range, inertias)
        k_silhouette     = k_range[int(np.argmax(silhouette_scores))]
        k_davies_bouldin = k_range[int(np.argmin(db_scores))]

        # --- Construire le mapping k -> méthodes qui le soutiennent ---
        method_votes: Dict[int, List[str]] = {k: [] for k in k_range}
        method_votes[k_elbow].append("coude")
        method_votes[k_silhouette].append("silhouette")
        method_votes[k_davies_bouldin].append("Davies-Bouldin")

        # --- Tableau récapitulatif ---
        remarques = [
            " | ".join(method_votes[k]) if method_votes[k] else ""
            for k in k_range
        ]
        table_df = pd.DataFrame({
            'k':               k_range,
            'Inertie':         [round(x, 2) for x in inertias],
            'Silhouette':      [round(x, 4) for x in silhouette_scores],
            'Davies-Bouldin':  [round(x, 4) for x in db_scores],
            'Methode(s)':      remarques,
        })
        print("\n[INFO] Tableau synthetique des 3 methodes :")
        print(table_df.to_string(index=False))

        # --- Vote majoritaire ---
        candidates = [k_elbow, k_silhouette, k_davies_bouldin]
        vote_counter = Counter(candidates)
        max_votes  = max(vote_counter.values())
        k_winners  = [k for k, v in vote_counter.items() if v == max_votes]
        n_methods  = len(candidates)

        print(f"\n[VOTE]  Resultats du vote ({n_methods} methodes) :")
        print(f"   Coude :             k = {k_elbow}")
        print(f"   Silhouette :        k = {k_silhouette}"
              f"  (score={silhouette_scores[k_range.index(k_silhouette)]:.3f})")
        print(f"   Davies-Bouldin :    k = {k_davies_bouldin}"
              f"  (score={db_scores[k_range.index(k_davies_bouldin)]:.3f})")
        print()
        for k_val, n_v in sorted(vote_counter.items()):
            methods_str = ", ".join(method_votes[k_val])
            print(f"   k={k_val} -> {n_v}/{n_methods} vote(s)  [{methods_str}]")

        # --- Seuil de qualité silhouette ---
        best_sil_score = silhouette_scores[k_range.index(k_silhouette)]
        SILHOUETTE_THRESHOLD = 0.25
        if best_sil_score < SILHOUETTE_THRESHOLD:
            print(f"\n[ATTENTION]  ATTENTION : Meilleur score de silhouette = {best_sil_score:.3f}"
                  f" (< {SILHOUETTE_THRESHOLD})")
            print(f"   La structure de clusters est faible. Interprétez avec prudence.")

        # --- Décision finale ---
        k_max_tested = max(k_range)
        if len(k_winners) == 1:
            self.optimal_k = k_winners[0]
            decision = f"vote majoritaire {max_votes}/{n_methods} méthodes"
        else:
            # Tiebreaker : silhouette > coude
            if k_silhouette in k_winners:
                self.optimal_k = k_silhouette
                decision = (f"ex aequo ({max_votes}/{n_methods}) "
                            f"- tiebreaker silhouette -> k={k_silhouette}")
            elif k_elbow in k_winners:
                self.optimal_k = k_elbow
                decision = (f"ex aequo ({max_votes}/{n_methods}) "
                            f"- tiebreaker coude -> k={k_elbow}")
            else:
                self.optimal_k = k_winners[0]
                decision = f"ex aequo ({max_votes}/{n_methods}) – premier candidat retenu"

        # --- Regle de parcimonie : si le vote designe le dernier k teste (k_max),
        # les indices (Silhouette, Davies-Bouldin, Gap) favorisent souvent k_max
        # par artefact de frontiere (pas de penalite au-dela de k_max).
        # On retient alors k_coude, plus parcimonieux et interpretatble.
        # [ATTENTION] Cette regle remplace le vote ; verifiez les courbes si k_max >> k_coude.
        if self.optimal_k == k_max_tested and k_elbow < k_max_tested:
            print(f"\n   [ATTENTION] Parcimonie appliquee :")
            print(f"   Vote -> k={k_max_tested} (limite superieure testee).")
            print(f"   Fallback -> k_coude={k_elbow} (plus parcimonieux).")
            print(f"   Verifiez les courbes d'evaluation pour confirmer ce choix.")
            self.optimal_k = k_elbow
            decision = (f"vote -> k={k_max_tested} (dernier k teste) ; "
                        f"parcimonie -> k_coude={k_elbow}")

        # --- Sauvegarder les détails ---
        self.evaluation_metrics.update({
            'k_elbow':               int(k_elbow),
            'k_silhouette':          int(k_silhouette),
            'k_davies_bouldin':      int(k_davies_bouldin),
            'best_silhouette_score': float(best_sil_score),
            'votes':        {str(k): int(v) for k, v in vote_counter.items()},
            'method_votes': {str(k): v for k, v in method_votes.items() if v},
            'optimal_k':    int(self.optimal_k),
            'decision':     decision,
        })

        print(f"\n[OK] k optimal retenu : {self.optimal_k}  ({decision})")

        return self.optimal_k
    
    def perform_clustering(self, n_clusters: int = None) -> np.ndarray:
        """
        Effectue la classification K-Means avec le nombre de clusters optimal.
        
        Args:
            n_clusters (int, optional): Nombre de clusters. Si None, utilise optimal_k.
        
        Returns:
            np.ndarray: Labels de clusters pour chaque événement
        """
        print("\n" + "="*80)
        print("ÉTAPE 4: CLASSIFICATION K-MEANS")
        print("="*80)
        
        if self.sst_matrix_scaled is None:
            print("[ERREUR] Données non prétraitées")
            return None
        
        n_clusters = n_clusters or self.optimal_k
        
        if n_clusters is None:
            print("[ERREUR] Nombre de clusters non déterminé. Exécutez find_optimal_k() d'abord.")
            return None
        
        print(f"[INFO] Classification avec k={n_clusters} clusters...")
        
        # K-Means
        self.kmeans_model = KMeans(
            n_clusters=n_clusters,
            random_state=self.random_state,
            n_init=20,
            max_iter=300
        )
        
        self.cluster_labels = self.kmeans_model.fit_predict(self.sst_matrix_scaled)
        
        # Statistiques des clusters
        unique_labels, counts = np.unique(self.cluster_labels, return_counts=True)
        
        print(f"[OK] Classification terminée:")
        for label, count in zip(unique_labels, counts):
            percentage = (count / len(self.cluster_labels)) * 100
            print(f"   Cluster {label}: {count} événements ({percentage:.1f}%)")
        
        # Stocker les résultats (convertir tous les types numpy en types Python natifs)
        # Convertir les centroïdes (qui peuvent être float32) en float Python
        centroids = self.kmeans_model.cluster_centers_.tolist()
        centroids_float = [[float(val) for val in row] for row in centroids]

        # Reprojeter les centroïdes de l'espace PCA vers l'espace SST original
        # pour permettre la visualisation géographique (cartes SST)
        centroids_sst = None
        if self.pca_model is not None:
            centroids_pca = self.kmeans_model.cluster_centers_.astype(np.float32)
            # Inverse PCA -> espace normalise SST
            # (pca_model.n_components_ == centroids_pca.shape[1] : pas de padding necessaire)
            centroids_sst = self.pca_model.inverse_transform(centroids_pca).astype(np.float32)
            # Denormaliser : (Z * std) + mean => anomalie SST reelle
            if hasattr(self, 'scaler_mean_') and hasattr(self, 'scaler_scale_'):
                centroids_sst = centroids_sst * self.scaler_scale_ + self.scaler_mean_
                print(f"   Centroides denormalises vers anomalie SST reelle.")
            print(f"   Centroides reprojetes en espace SST: {centroids_sst.shape}")

        n_pixels_sst = self.sst_matrix.shape[1] if self.sst_matrix is not None else None
        self.clustering_results = {
            'n_clusters': int(n_clusters),
            'n_pixels_sst': int(n_pixels_sst) if n_pixels_sst is not None else None,
            'n_pca_components': int(self.n_pca_components) if self.n_pca_components is not None else None,
            'labels': [int(label) for label in self.cluster_labels.tolist()],
            'centroids': centroids_float,
            'inertia': float(self.kmeans_model.inertia_),
            'n_iter': int(self.kmeans_model.n_iter_)
        }
        self.centroids_sst = centroids_sst
        
        return self.cluster_labels
    
    def analyze_cluster_characteristics(self) -> pd.DataFrame:
        """
        Analyse les caractéristiques de chaque cluster en relation avec les événements.
        
        Returns:
            pd.DataFrame: DataFrame avec les caractéristiques par cluster
        """
        print("\n" + "="*80)
        print("ÉTAPE 5: ANALYSE DES CARACTÉRISTIQUES DES CLUSTERS")
        print("="*80)
        
        if self.cluster_labels is None:
            print("[ERREUR] Classification non effectuée")
            return pd.DataFrame()
        
        # Utiliser le DataFrame filtré avec uniquement les événements chargés
        if self.events_df_loaded is None or len(self.events_df_loaded) == 0:
            print("[ERREUR] Aucune donnée d'événements chargée")
            return pd.DataFrame()
        
        # Vérifier que les longueurs correspondent
        if len(self.cluster_labels) != len(self.events_df_loaded):
            print(f"[ATTENTION] Incohérence: {len(self.cluster_labels)} labels pour {len(self.events_df_loaded)} événements")
            # Prendre uniquement les événements qui correspondent aux labels
            min_len = min(len(self.cluster_labels), len(self.events_df_loaded))
            self.cluster_labels = self.cluster_labels[:min_len]
            self.events_df_loaded = self.events_df_loaded.iloc[:min_len].copy()
        
        # Ajouter les labels de cluster aux événements
        events_with_clusters = self.events_df_loaded.copy()
        events_with_clusters['cluster'] = self.cluster_labels
        
        # Analyser par cluster
        cluster_stats = []
        
        for cluster_id in sorted(np.unique(self.cluster_labels)):
            cluster_events = events_with_clusters[events_with_clusters['cluster'] == cluster_id]
            
            stats = {
                'cluster': cluster_id,
                'n_events': len(cluster_events),
                'percentage': (len(cluster_events) / len(events_with_clusters)) * 100,
                
                # Caractéristiques temporelles
                'mean_year': cluster_events['year'].mean(),
                'mean_month': cluster_events['month'].mean(),
                'mean_day_of_year': cluster_events['day_of_year'].mean(),
                
                # Caractéristiques de précipitation
                'mean_max_precip': cluster_events['max_precip'].mean(),
                'mean_mean_precip': cluster_events['mean_precip'].mean(),
                'mean_coverage_percent': cluster_events['coverage_percent'].mean(),
                
                # Caractéristiques d'anomalie
                'mean_max_anomaly': cluster_events['max_anomaly'].mean(),
                'mean_mean_anomaly': cluster_events['mean_anomaly'].mean(),
                
                # Distribution par phase
                'phase_distribution': cluster_events['phase'].value_counts().to_dict(),
                
                # Distribution par année
                'years_range': (cluster_events['year'].min(), cluster_events['year'].max()),
                'n_years': cluster_events['year'].nunique()
            }
            
            cluster_stats.append(stats)
        
        cluster_df = pd.DataFrame(cluster_stats)
        
        print("[STATS] Caractéristiques des clusters:")
        print(cluster_df[['cluster', 'n_events', 'percentage', 'mean_month', 
                         'mean_max_precip', 'mean_max_anomaly']].to_string())
        
        return cluster_df
    
    def visualize_results(self, output_dir: Path = None, phase_name: str = None) -> List[Path]:
        """
        Crée les visualisations des résultats de classification.
        
        Args:
            output_dir (Path, optional): Dossier de sortie pour les visualisations
            phase_name (str, optional): Nom de la phase pour personnaliser les titres
        
        Returns:
            List[Path]: Liste des chemins des fichiers de visualisation créés
        """
        print("\n" + "="*80)
        print("ÉTAPE 6: CRÉATION DES VISUALISATIONS")
        if phase_name:
            print(f"Phase: {phase_name}")
        print("="*80)
        
        if output_dir is None:
            if phase_name:
                output_dir = VISUALIZATION_DIR / "clustering" / phase_name
            else:
                output_dir = VISUALIZATION_DIR / "clustering"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        created_files = []
        
        # Configuration des graphiques
        plt.style.use('seaborn-v0_8-whitegrid')
        sns.set_palette("husl")
        
        # Titre avec phase si disponible
        phase_title = f" - {phase_name}" if phase_name else ""
        
        # 0. Tableau synthétique des 4 méthodes (image)
        if self.evaluation_metrics:
            _k_range   = self.evaluation_metrics['k_range']
            _inertias  = self.evaluation_metrics['inertias']
            _sil       = self.evaluation_metrics['silhouette_scores']
            _db        = self.evaluation_metrics.get('davies_bouldin_scores',    [None]*len(_k_range))
            _gap       = self.evaluation_metrics.get('gap_values',               [None]*len(_k_range))
            _mv        = self.evaluation_metrics.get('method_votes', {})

            col_k      = [str(x) for x in _k_range]
            col_iner   = [f"{x:.2e}" if x >= 1e4 else f"{x:.4f}" for x in _inertias]
            col_sil    = [f"{x:.4f}" for x in _sil]
            col_db     = [f"{x:.4f}" if x is not None else "N/A" for x in _db]
            col_rem    = [", ".join(_mv.get(str(k), [])) for k in _k_range]

            table_data = [[k, i, s, db, r]
                          for k, i, s, db, r
                          in zip(col_k, col_iner, col_sil, col_db, col_rem)]
            headers = ['k', 'Inertie', 'Silhouette', 'Davies-Bouldin', 'Methode(s)']

            fig_table, ax_table = plt.subplots(figsize=(16, max(4, 0.45 * len(_k_range) + 1)))
            ax_table.axis('off')
            tbl = ax_table.table(
                cellText=table_data, colLabels=headers,
                loc='center', cellLoc='center',
                colColours=['#e0e0e0'] * 5,
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(9)
            tbl.scale(1.1, 2.2)
            ax_table.set_title(
                f'Tableau synthetique - 3 methodes de selection du k optimal{phase_title}',
                fontsize=13, fontweight='bold', pad=20)
            plt.tight_layout()
            filepath_table = output_dir / "00_tableau_k_3_methodes.png"
            plt.savefig(filepath_table, dpi=300, bbox_inches='tight')
            plt.close()
            created_files.append(filepath_table)
            print(f"[OK] Graphique sauvegarde: {filepath_table.name}")

        # 1. Évaluation du nombre optimal de clusters (3 méthodes)
        if self.evaluation_metrics:
            fig, axes = plt.subplots(1, 3, figsize=(18, 6))
            fig.suptitle(
                f'Evaluation du Nombre Optimal de Clusters - 3 Methodes{phase_title}',
                fontsize=16, fontweight='bold')

            _k_range  = self.evaluation_metrics['k_range']
            _k_elbow  = self.evaluation_metrics.get('k_elbow')
            _k_sil    = self.evaluation_metrics.get('k_silhouette')
            _k_db     = self.evaluation_metrics.get('k_davies_bouldin')
            _inertias = self.evaluation_metrics['inertias']
            _sil      = self.evaluation_metrics['silhouette_scores']
            _db       = self.evaluation_metrics.get('davies_bouldin_scores', [])

            # Suffixe pour identifier la phase sur chaque sous-graphique
            _subtitle = phase_title if phase_title else ""

            # (0) Inertie - Methode du coude
            ax = axes[0]
            ax.plot(_k_range, _inertias, 'bo-', linewidth=2, markersize=8, label='Inertie')
            if _k_elbow is not None:
                ax.axvline(_k_elbow, color='darkgreen', linestyle='--', alpha=0.7,
                           label=f'k coude = {_k_elbow}')
            ax.set_xlabel('k', fontsize=11)
            ax.set_ylabel('Inertie (WSS)', fontsize=11)
            ax.set_title(f'Methode du Coude{_subtitle}', fontsize=12, fontweight='bold')
            ax.set_xticks(_k_range); ax.legend(fontsize=9); ax.grid(True, alpha=0.3, axis='y')

            # (1) Silhouette
            ax = axes[1]
            ax.plot(_k_range, _sil, 'go-', linewidth=2, markersize=8, label='Silhouette')
            if _k_sil is not None:
                ax.plot(_k_sil, _sil[_k_range.index(_k_sil)], 'b*', markersize=14,
                        zorder=5, label=f'k opt = {_k_sil}')
            ax.set_xlabel('k', fontsize=11)
            ax.set_ylabel('Score de Silhouette', fontsize=11)
            ax.set_title(f'Silhouette (max){_subtitle}', fontsize=12, fontweight='bold')
            ax.set_xticks(_k_range); ax.legend(fontsize=9); ax.grid(True, alpha=0.3, axis='y')

            # (2) Davies-Bouldin
            ax = axes[2]
            if _db:
                ax.plot(_k_range, _db, 'mo-', linewidth=2, markersize=8, label='Davies-Bouldin')
                if _k_db is not None:
                    ax.plot(_k_db, _db[_k_range.index(_k_db)], 'm*', markersize=14,
                            zorder=5, label=f'k opt = {_k_db}')
            ax.set_xlabel('k', fontsize=11)
            ax.set_ylabel('Indice Davies-Bouldin', fontsize=11)
            ax.set_title(f'Davies-Bouldin (min){_subtitle}', fontsize=12, fontweight='bold')
            ax.set_xticks(_k_range); ax.legend(fontsize=9); ax.grid(True, alpha=0.3, axis='y')

            plt.tight_layout()
            filepath = output_dir / "01_evaluation_clusters.png"
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()
            created_files.append(filepath)
            print(f"[OK] Graphique sauvegarde: {filepath.name}")
        
        # 2. Visualisation PCA des clusters (les 2 premières composantes du PCA déjà calculé)
        if self.cluster_labels is not None and self.pca_model is not None:
            # Utiliser les 2 premières composantes du PCA déjà calculé en prétraitement
            sst_pca_2d = self.sst_matrix_scaled[:, :2]
            var_ratios = self.pca_model.explained_variance_ratio_

            fig, ax = plt.subplots(figsize=(12, 8))

            unique_labels = sorted(np.unique(self.cluster_labels))
            colors = plt.cm.tab10(np.linspace(0, 1, len(unique_labels)))

            for i, label in enumerate(unique_labels):
                mask = self.cluster_labels == label
                ax.scatter(sst_pca_2d[mask, 0], sst_pca_2d[mask, 1],
                          c=[colors[i]], label=f'Cluster {label}',
                          s=50, alpha=0.6, edgecolors='black', linewidth=0.5)

            # Centroïdes (déjà dans l'espace PCA)
            centroids = self.kmeans_model.cluster_centers_[:, :2]
            ax.scatter(centroids[:, 0], centroids[:, 1],
                     c='red', marker='X', s=200, label='Centroïdes',
                     edgecolors='black', linewidth=1.5, zorder=10)

            ax.set_xlabel(f'PC1 ({var_ratios[0]:.1%} de variance)', fontsize=12)
            ax.set_ylabel(f'PC2 ({var_ratios[1]:.1%} de variance)', fontsize=12)
            title = f'Visualisation des Clusters en 2D (PCA){phase_title}'
            subtitle = f'{self.n_pca_components} composantes retenues pour le clustering'
            ax.set_title(f'{title}\n{subtitle}', fontsize=14, fontweight='bold')
            ax.legend(loc='best', fontsize=10)
            ax.grid(True, alpha=0.3)

            plt.tight_layout()

            filepath = output_dir / "02_clusters_pca.png"
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()
            created_files.append(filepath)
            print(f"[OK] Graphique sauvegardé: {filepath.name}")
        
        # 3. Distribution temporelle par cluster
        if self.cluster_labels is not None and self.events_df_loaded is not None:
            events_with_clusters = self.events_df_loaded.copy()
            events_with_clusters['cluster'] = self.cluster_labels
            
            fig, axes = plt.subplots(2, 2, figsize=(16, 12))
            fig.suptitle(f'Caractéristiques Temporelles et Spatiales par Cluster{phase_title}', 
                        fontsize=16, fontweight='bold')
            
            # Distribution par mois
            cluster_month = pd.crosstab(events_with_clusters['cluster'], 
                                       events_with_clusters['month'])
            cluster_month.plot(kind='bar', ax=axes[0, 0], width=0.8)
            axes[0, 0].set_xlabel('Cluster', fontsize=12)
            axes[0, 0].set_ylabel('Nombre d\'événements', fontsize=12)
            axes[0, 0].set_title('Distribution par Mois', fontsize=13, fontweight='bold')
            axes[0, 0].legend(title='Mois', bbox_to_anchor=(1.05, 1), loc='upper left')
            axes[0, 0].grid(True, alpha=0.3, axis='y')
            
            # Distribution par phase
            cluster_phase = pd.crosstab(events_with_clusters['cluster'], 
                                       events_with_clusters['phase'])
            cluster_phase.plot(kind='bar', ax=axes[0, 1], width=0.8)
            axes[0, 1].set_xlabel('Cluster', fontsize=12)
            axes[0, 1].set_ylabel('Nombre d\'événements', fontsize=12)
            axes[0, 1].set_title('Distribution par Phase', fontsize=13, fontweight='bold')
            axes[0, 1].legend(title='Phase', bbox_to_anchor=(1.05, 1), loc='upper left')
            axes[0, 1].grid(True, alpha=0.3, axis='y')
            
            # Distribution par année
            cluster_year = pd.crosstab(events_with_clusters['cluster'], 
                                      events_with_clusters['year'])
            cluster_year.plot(kind='bar', ax=axes[1, 0], width=0.8, stacked=True)
            axes[1, 0].set_xlabel('Cluster', fontsize=12)
            axes[1, 0].set_ylabel('Nombre d\'événements', fontsize=12)
            axes[1, 0].set_title('Distribution par Année', fontsize=13, fontweight='bold')
            axes[1, 0].legend(title='Année', bbox_to_anchor=(1.05, 1), loc='upper left', ncol=2)
            axes[1, 0].grid(True, alpha=0.3, axis='y')
            
            # Intensité moyenne par cluster
            cluster_intensity = events_with_clusters.groupby('cluster').agg({
                'max_precip': 'mean',
                'mean_precip': 'mean',
                'max_anomaly': 'mean'
            })
            
            x = np.arange(len(cluster_intensity))
            width = 0.25
            axes[1, 1].bar(x - width, cluster_intensity['max_precip'], width, 
                         label='Max précipitation', alpha=0.8)
            axes[1, 1].bar(x, cluster_intensity['mean_precip'], width, 
                         label='Moyenne précipitation', alpha=0.8)
            axes[1, 1].bar(x + width, cluster_intensity['max_anomaly'], width, 
                         label='Max anomalie', alpha=0.8)
            axes[1, 1].set_xlabel('Cluster', fontsize=12)
            axes[1, 1].set_ylabel('Valeur moyenne', fontsize=12)
            axes[1, 1].set_title('Intensité Moyenne par Cluster', fontsize=13, fontweight='bold')
            axes[1, 1].set_xticks(x)
            axes[1, 1].set_xticklabels(cluster_intensity.index)
            axes[1, 1].legend()
            axes[1, 1].grid(True, alpha=0.3, axis='y')
            
            plt.tight_layout()
            
            filepath = output_dir / "03_caracteristiques_clusters.png"
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()
            created_files.append(filepath)
            print(f"[OK] Graphique sauvegardé: {filepath.name}")
        
        return created_files
    
    def save_results(self, output_dir: Path = None, phase_name: str = None) -> Dict[str, Path]:
        """
        Sauvegarde les résultats de l'analyse.
        
        Args:
            output_dir (Path, optional): Dossier de sortie
            phase_name (str, optional): Nom de la phase pour personnaliser les fichiers
        
        Returns:
            Dict[str, Path]: Dictionnaire des fichiers créés
        """
        print("\n" + "="*80)
        print("ÉTAPE 7: SAUVEGARDE DES RÉSULTATS")
        if phase_name:
            print(f"Phase: {phase_name}")
        print("="*80)
        
        if output_dir is None:
            if phase_name:
                output_dir = OUTPUT_DIR / "clustering" / phase_name
            else:
                output_dir = OUTPUT_DIR / "clustering"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = {}
        
        # Préfixe pour les fichiers si phase spécifiée
        prefix = f"{phase_name}_" if phase_name else ""
        
        # 1. Résultats de classification
        if self.clustering_results:
            results_file = output_dir / f"{prefix}kmeans_clustering_results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(self.clustering_results, f, indent=2, ensure_ascii=False)
            saved_files['clustering_results'] = results_file
            print(f"[OK] Résultats sauvegardés: {results_file.name}")
        
        # 2. Métriques d'évaluation
        if self.evaluation_metrics:
            metrics_file = output_dir / f"{prefix}kmeans_evaluation_metrics.json"
            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(self.evaluation_metrics, f, indent=2, ensure_ascii=False)
            saved_files['evaluation_metrics'] = metrics_file
            print(f"[OK] Métriques sauvegardées: {metrics_file.name}")

            # Tableau complet 3 methodes
            _kr   = self.evaluation_metrics['k_range']
            _ke   = self.evaluation_metrics.get('k_elbow')
            _ks   = self.evaluation_metrics.get('k_silhouette')
            _kdb  = self.evaluation_metrics.get('k_davies_bouldin')
            _mv_s = self.evaluation_metrics.get('method_votes', {})
            _db_s = self.evaluation_metrics.get('davies_bouldin_scores', [None] * len(_kr))
            _rem  = [" | ".join(_mv_s.get(str(k), [])) for k in _kr]

            table_df = pd.DataFrame({
                'k':              _kr,
                'Inertie':        self.evaluation_metrics['inertias'],
                'Silhouette':     self.evaluation_metrics['silhouette_scores'],
                'Davies-Bouldin': _db_s,
                'Methode(s)':     _rem,
            })
            table_file = output_dir / f"{prefix}tableau_k_3_methodes.csv"
            table_df.to_csv(table_file, index=False, encoding='utf-8-sig')
            saved_files['tableau_k_methodes'] = table_file
            print(f"[OK] Tableau k / 3 methodes sauvegarde: {table_file.name}")

            # Rapport texte (lisible sans Excel)
            table_txt = output_dir / f"{prefix}tableau_k_3_methodes.txt"
            with open(table_txt, 'w', encoding='utf-8') as f:
                f.write("Tableau des k - 3 methodes de selection du k optimal\n")
                f.write("=" * 70 + "\n\n")
                f.write(table_df.to_string(index=False) + "\n\n")
                f.write("Resume des k optimaux par methode :\n")
                f.write(f"  Coude :             k = {_ke}\n")
                f.write(f"  Silhouette :        k = {_ks}\n")
                f.write(f"  Davies-Bouldin :    k = {_kdb}\n")
                f.write(f"\n  k optimal retenu (vote) : "
                        f"{self.evaluation_metrics.get('optimal_k', 'N/A')}\n")
                f.write(f"  Decision : {self.evaluation_metrics.get('decision', 'N/A')}\n")
            saved_files['tableau_k_txt'] = table_txt
            print(f"[OK] Rapport tableau (txt) sauvegarde: {table_txt.name}")
        
        # 3. Événements avec labels de cluster
        if self.cluster_labels is not None and self.events_df_loaded is not None:
            events_with_clusters = self.events_df_loaded.copy()
            events_with_clusters['cluster'] = self.cluster_labels
            events_file = output_dir / f"{prefix}events_with_clusters.csv"
            events_with_clusters.to_csv(events_file, index=True)
            saved_files['events_with_clusters'] = events_file
            print(f"[OK] Événements avec clusters sauvegardés: {events_file.name}")
        
        # 4. Centroïdes SST (espace grille original, pour visualisation géographique)
        if self.centroids_sst is not None:
            centroids_sst_file = output_dir / f"{prefix}centroids_sst.npy"
            np.save(centroids_sst_file, self.centroids_sst)
            saved_files['centroids_sst'] = centroids_sst_file
            print(f"[OK] Centroïdes SST sauvegardés: {centroids_sst_file.name} ({self.centroids_sst.shape})")

        # 5. Caractéristiques des clusters
        cluster_characteristics = self.analyze_cluster_characteristics()
        if not cluster_characteristics.empty:
            characteristics_file = output_dir / f"{prefix}cluster_characteristics.csv"
            cluster_characteristics.to_csv(characteristics_file, index=False)
            saved_files['cluster_characteristics'] = characteristics_file
            print(f"[OK] Caractéristiques des clusters sauvegardées: {characteristics_file.name}")
        
        return saved_files
    
    def run_complete_analysis(self, events_file: Path = None,
                              output_dir: Path = None) -> bool:
        """
        Exécute l'analyse complète de classification K-Means.
        
        Args:
            events_file (Path, optional): Fichier CSV des événements
            output_dir (Path, optional): Dossier de sortie
        
        Returns:
            bool: True si l'analyse a réussi
        """
        print("\n" + "="*80)
        print("ANALYSE COMPLÈTE DE CLASSIFICATION K-MEANS SUR SST")
        print("="*80)
        
        # Étape 1: Chargement
        if not self.load_data(events_file):
            return False
        
        # Étape 2: Prétraitement
        if not self.preprocess_data():
            return False
        
        # Étape 3: Détermination du k optimal
        self.find_optimal_k()
        
        # Étape 4: Classification
        self.perform_clustering()
        
        # Étape 5: Analyse des caractéristiques
        self.analyze_cluster_characteristics()
        
        # Étape 6: Visualisations
        phase_name = None  # Pour compatibilité avec analyse globale
        self.visualize_results(output_dir, phase_name=phase_name)
        
        # Étape 7: Sauvegarde
        self.save_results(output_dir, phase_name=phase_name)
        
        print("\n" + "="*80)
        print("[OK] ANALYSE TERMINÉE AVEC SUCCÈS")
        print("="*80)
        
        return True
    
    def run_analysis_for_phase(self, phase_file: Path, phase_name: str,
                               output_base_dir: Path = None,
                               forced_k: int = None,
                               detrend_sst: bool = False) -> bool:
        """
        Exécute l'analyse complète pour une phase spécifique.

        Args:
            phase_file (Path): Fichier CSV des événements de la phase
            phase_name (str): Nom de la phase (ex: 'Phase_1_debut')
            output_base_dir (Path, optional): Dossier de base pour les sorties
            forced_k (int, optional): Forcer un k fixe (contourne find_optimal_k)
            detrend_sst (bool): Si True, retire la tendance lineaire SST par pixel
                avant la PCA. Recommande pour separer patterns de circulation
                et signal de rechauffement climatique (defaut: False).

        Returns:
            bool: True si l'analyse a réussi
        """
        print("\n" + "="*80)
        print(f"ANALYSE K-MEANS POUR {phase_name.upper()}")
        print("="*80)
        
        # Réinitialiser les résultats pour cette phase
        self.kmeans_model = None
        self.pca_model = None
        self.n_pca_components = None
        self.optimal_k = None
        self.cluster_labels = None
        self.sst_matrix = None
        self.sst_normalized = None
        self.dates = None
        self.metadata = None
        self.events_df = None
        self.events_df_loaded = None
        self.clustering_results = {}
        self.evaluation_metrics = {}
        self.centroids_sst = None
        self.sst_matrix_scaled = None
        
        # Définir les dossiers de sortie pour cette phase
        if output_base_dir is None:
            output_base_dir = OUTPUT_DIR
        
        phase_output_dir = output_base_dir / "clustering" / phase_name
        phase_viz_dir = VISUALIZATION_DIR / "clustering" / phase_name
        
        # Étape 1: Chargement
        if not self.load_data(phase_file):
            print(f"[ERREUR] Échec du chargement pour {phase_name}")
            return False
        
        # Étape 2: Prétraitement
        if not self.preprocess_data(detrend_sst=detrend_sst):
            print(f"Echec du pretraitement pour {phase_name}")
            return False

        # Étape 3: Détermination du k optimal (toujours calculer pour générer les figures)
        self.find_optimal_k()
        if forced_k is not None:
            print(f"\n[INFO] K forcé à {forced_k} (contourne la recherche automatique)")
            self.optimal_k = forced_k

        # Étape 4: Classification
        self.perform_clustering()
        
        # Étape 5: Analyse des caractéristiques
        self.analyze_cluster_characteristics()
        
        # Étape 6: Visualisations
        self.visualize_results(phase_viz_dir, phase_name=phase_name)
        
        # Étape 7: Sauvegarde
        self.save_results(phase_output_dir, phase_name=phase_name)
        
        print(f"\n[OK] Analyse terminée pour {phase_name}")
        print(f"   Nombre optimal de clusters: {self.optimal_k}")
        print(f"   Visualisations: {phase_viz_dir}")
        print(f"   Résultats: {phase_output_dir}")
        
        return True


def run_analysis_by_phase(detrend_sst: bool = False):
    """
    Exécute l'analyse K-Means séparément pour chaque phase de saison.

    Args:
        detrend_sst (bool): Si True, retire la tendance lineaire SST par pixel
            avant PCA+KMeans (supprime le signal de rechauffement climatique).
    """
    print("\n" + "="*80)
    print("ANALYSE K-MEANS PAR PHASE DE SAISON")
    print("="*80)
    
    # Créer les dossiers de sortie
    create_output_directories()
    
    # Définir les fichiers de phase
    phase_files = {
        'Phase_1_debut': EXPORT_DIR / "extreme_events_phase_1_debut.csv",
        'Phase_2_pleine': EXPORT_DIR / "extreme_events_phase_2_pleine.csv",
        'Phase_3_fin': EXPORT_DIR / "extreme_events_phase_3_fin.csv"
    }
    
    phase_names = {
        'Phase_1_debut': 'Debut de saison (Mai-Juin)',
        'Phase_2_pleine': 'Pleine saison (Juillet-Aout)',
        'Phase_3_fin': 'Fin de saison (Septembre-Octobre)'
    }

    # K optimaux selectionnes par regle de parcimonie (k_coude) de l'algorithme
    # Phase_1: k_elbow=6, Phase_2: k_elbow=6, Phase_3: k_elbow=5
    phase_forced_k = {
        'Phase_1_debut': 6,
        'Phase_2_pleine': 6,
        'Phase_3_fin': 5,
    }
    
    # Vérifier que les fichiers existent
    missing_files = [phase for phase, file in phase_files.items() if not file.exists()]
    if missing_files:
        print(f"\n[ATTENTION] Fichiers manquants pour les phases suivantes:")
        for phase in missing_files:
            print(f"   - {phase}: {phase_files[phase]}")
        print(f"\n[CONSEIL] Exécutez d'abord le script 03b_split_events_by_phase.py pour créer ces fichiers.")
        return False
    
    # Initialiser l'analyseur
    analyzer = KMeansSSTAnalyzer(n_clusters_range=(2, 10), random_state=42)

    # Résultats par phase
    results_summary = {}
    
    # Analyser chaque phase
    for phase_key, phase_file in phase_files.items():
        print(f"\n{'='*80}")
        print(f"TRAITEMENT DE LA PHASE: {phase_names[phase_key]}")
        print(f"{'='*80}")
        
        success = analyzer.run_analysis_for_phase(
            phase_file=phase_file,
            phase_name=phase_key,
            forced_k=phase_forced_k[phase_key],
            detrend_sst=detrend_sst,
        )
        
        if success:
            results_summary[phase_key] = {
                'optimal_k': analyzer.optimal_k,
                'n_events': len(analyzer.events_df_loaded) if analyzer.events_df_loaded is not None else 0,
                'n_clusters': analyzer.clustering_results.get('n_clusters', 0) if analyzer.clustering_results else 0
            }
        else:
            print(f"[ERREUR] Échec de l'analyse pour {phase_key}")
            results_summary[phase_key] = {'error': 'Échec de l\'analyse'}
    
    # Résumé final
    print("\n" + "="*80)
    print("RÉSUMÉ DE L'ANALYSE PAR PHASE")
    print("="*80)
    
    for phase_key, summary in results_summary.items():
        print(f"\n{phase_names[phase_key]} ({phase_key}):")
        if 'error' in summary:
            print(f"   [ERREUR] {summary['error']}")
        else:
            print(f"   [OK] {summary['n_events']} événements analysés")
            print(f"   [STATS] Nombre optimal de clusters: {summary['optimal_k']}")
            print(f"    Résultats: {OUTPUT_DIR / 'clustering' / phase_key}")
            print(f"    Visualisations: {VISUALIZATION_DIR / 'clustering' / phase_key}")
    
    return True


def main():
    """Fonction principale."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Analyse de classification K-Means sur les champs SST des événements extrêmes'
    )
    parser.add_argument(
        '--by-phase',
        action='store_true',
        help='Analyser séparément chaque phase de saison (recommandé)'
    )
    parser.add_argument(
        '--phase-file',
        type=str,
        help='Fichier CSV d\'événements spécifique (pour analyse d\'une seule phase)'
    )
    parser.add_argument(
        '--phase-name',
        type=str,
        help='Nom de la phase (si --phase-file est utilisé)'
    )
    parser.add_argument(
        '--detrend-sst',
        action='store_true',
        default=True,
        help=(
            'Retire la tendance lineaire inter-annuelle par pixel SST avant PCA+KMeans. '
            'Recommande pour isoler les patterns de circulation du signal de '
            'rechauffement climatique (defaut: True).'
        )
    )

    args = parser.parse_args()

    # Créer les dossiers de sortie
    create_output_directories()

    # Mode par défaut: analyse par phase
    if args.by_phase or (not args.phase_file):
        print("\nMODE: Analyse par phase de saison")
        if args.detrend_sst:
            print("Option --detrend-sst activee : tendance SST retiree par pixel.")
        success = run_analysis_by_phase(detrend_sst=args.detrend_sst)
    elif args.phase_file:
        # Analyse d'un fichier spécifique
        phase_file = Path(args.phase_file)
        phase_name = args.phase_name or phase_file.stem

        print(f"\nMODE: Analyse d'un fichier specifique")
        print(f"   Fichier: {phase_file}")
        print(f"   Phase: {phase_name}")

        analyzer = KMeansSSTAnalyzer(n_clusters_range=(2, 10), random_state=42)
        success = analyzer.run_analysis_for_phase(
            phase_file, phase_name, detrend_sst=args.detrend_sst
        )
    else:
        # Analyse globale (tous événements ensemble)
        print("\n[INFO] MODE: Analyse globale (tous événements)")

        analyzer = KMeansSSTAnalyzer(n_clusters_range=(2, 10), random_state=42)
        success = analyzer.run_complete_analysis()
        
        if success:
            print("\n[OK] L'analyse de classification K-Means est terminée!")
            print(f"   Nombre optimal de clusters: {analyzer.optimal_k}")
            print(f"   Visualisations: {VISUALIZATION_DIR / 'clustering'}")
            print(f"   Résultats: {OUTPUT_DIR / 'clustering'}")
    
    if not success:
        print("\n[ERREUR] L'analyse a échoué. Vérifiez les erreurs ci-dessus.")


if __name__ == "__main__":
    main()

