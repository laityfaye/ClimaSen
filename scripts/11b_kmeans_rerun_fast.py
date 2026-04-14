"""
11b_kmeans_rerun_fast.py
Relance K-Means en chargeant directement les donnees PCA pre-calculees.
Beaucoup plus rapide que 11_kmeans_sst_analysis.py (pas de chargement SST/NetCDF).

Usage (memes arguments que 11_kmeans_sst_analysis.py) :
    py -3 scripts/11b_kmeans_rerun_fast.py --by-phase --k-phase1=4 --k-phase2=5 --k-phase3=3
    py -3 scripts/11b_kmeans_rerun_fast.py --global --k-all=7
    py -3 scripts/11b_kmeans_rerun_fast.py --k-phase1=4 --k-phase2=5 --k-phase3=3 --k-all=7
"""

import argparse
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score

sys.path.append(str(Path(__file__).parent.parent))
from src.config.settings import OUTPUT_DIR, VISUALIZATION_DIR

CLUSTERING_DIR  = OUTPUT_DIR / "clustering"
VIZ_DIR         = VISUALIZATION_DIR / "clustering"
RANDOM_STATE    = 42
N_INIT          = 20
MAX_ITER        = 300
K_RANGE_DEFAULT = (2, 15)


# ─── Methode du coude (identique a 11_kmeans_sst_analysis.py) ─────────────────
def _find_elbow_geometric(k_values, inertias):
    k_arr       = np.array(k_values, dtype=np.float64)
    inertia_arr = np.array(inertias, dtype=np.float64)
    k_norm      = (k_arr - k_arr.min()) / (k_arr.max() - k_arr.min() + 1e-12)
    i_norm      = (inertia_arr - inertia_arr.min()) / (inertia_arr.max() - inertia_arr.min() + 1e-12)
    p1, p2      = np.array([k_norm[0], i_norm[0]]), np.array([k_norm[-1], i_norm[-1]])
    line_vec    = p2 - p1
    line_len    = np.linalg.norm(line_vec) + 1e-12
    points      = np.column_stack([k_norm, i_norm])
    d_vecs      = p1 - points
    distances   = np.abs(line_vec[0] * d_vecs[:, 1] - line_vec[1] * d_vecs[:, 0]) / line_len
    return int(k_values[int(np.argmax(distances))])


# ─── Fonction principale par phase ────────────────────────────────────────────
def run_fast(phase_name: str, forced_k: int):
    """
    Charge la matrice PCA pre-calculee, relance K-Means avec forced_k,
    et ecrase les fichiers de resultats dans outputs/clustering/{phase_name}/.
    Les fichiers centroids_sst.npy et kmeans_input_pca.* ne sont PAS touches.
    """
    out_dir = CLUSTERING_DIR / phase_name
    viz_dir = VIZ_DIR / phase_name
    viz_dir.mkdir(parents=True, exist_ok=True)
    prefix  = f"{phase_name}_"

    # ── 1. Chargement de la matrice PCA ───────────────────────────────────────
    pca_file = out_dir / f"{prefix}kmeans_input_pca.csv"
    if not pca_file.exists():
        print(f"[ERREUR] Fichier PCA introuvable : {pca_file}")
        print(f"   Lancez d'abord 11_kmeans_sst_analysis.py pour generer les donnees.")
        return False

    print(f"\n{'='*70}")
    print(f"PHASE : {phase_name}  |  k demande = {forced_k}")
    print(f"{'='*70}")
    print(f"[CHARGEMENT] {pca_file.name}")

    df = pd.read_csv(pca_file, encoding='utf-8-sig')
    pc_cols = [c for c in df.columns if c.startswith('PC')]
    X       = df[pc_cols].values.astype(np.float32)
    n_events, n_comp = X.shape
    print(f"[OK] Matrice chargee : {n_events} evenements x {n_comp} composantes PCA")

    if forced_k >= n_events:
        print(f"[ERREUR] k={forced_k} >= n_evenements={n_events}. Choisissez un k plus petit.")
        return False

    # ── 2. Evaluation sur la plage de k (pour courbes coude / silhouette) ─────
    k_min   = K_RANGE_DEFAULT[0]
    k_max   = min(K_RANGE_DEFAULT[1], n_events - 1)
    # S'assurer que forced_k est dans la plage evaluee
    k_max   = max(k_max, forced_k)
    k_range = list(range(k_min, k_max + 1))

    print(f"\n[EVALUATION] Calcul des metriques pour k = {k_range[0]}..{k_range[-1]}...")
    inertias, sil_scores, db_scores = [], [], []

    for ki in k_range:
        km     = KMeans(n_clusters=ki, random_state=RANDOM_STATE, n_init=N_INIT, max_iter=MAX_ITER)
        labels = km.fit_predict(X)
        inertias.append(float(km.inertia_))
        sil_scores.append(float(silhouette_score(X, labels)))
        db_scores.append(float(davies_bouldin_score(X, labels)))
        print(f"   k={ki}  sil={sil_scores[-1]:.3f}  DB={db_scores[-1]:.3f}")

    # Methodes de selection du k optimal
    k_elbow    = _find_elbow_geometric(k_range, inertias)
    k_sil      = k_range[int(np.argmax(sil_scores))]
    k_db       = k_range[int(np.argmin(db_scores))]

    method_votes = {k: [] for k in k_range}
    method_votes[k_elbow].append("coude")
    method_votes[k_sil].append("silhouette")
    method_votes[k_db].append("Davies-Bouldin")

    vote_counter = Counter([k_elbow, k_sil, k_db])
    max_votes    = max(vote_counter.values())
    k_winners    = [k for k, v in vote_counter.items() if v == max_votes]
    k_optimal_auto = k_winners[0] if len(k_winners) == 1 else k_sil

    print(f"\n[VOTE]  Coude={k_elbow}  Silhouette={k_sil}  DB={k_db}  -> auto={k_optimal_auto}")
    print(f"[INFO]  K retenu (force) = {forced_k}")

    # ── 3. Clustering final avec forced_k ─────────────────────────────────────
    km_final = KMeans(
        n_clusters=forced_k,
        random_state=RANDOM_STATE,
        n_init=N_INIT,
        max_iter=MAX_ITER,
    )
    labels = km_final.fit_predict(X)
    print(f"\n[OK] K-Means termine  inertie={km_final.inertia_:.2f}")
    unique, counts = np.unique(labels, return_counts=True)
    for cl, cnt in zip(unique, counts):
        print(f"   Cluster {cl} : {cnt} evenements ({cnt/n_events*100:.1f}%)")

    # ── 4. Reconstruction du DataFrame evenements + clusters ──────────────────
    events_df = df.drop(columns=pc_cols + (['cluster'] if 'cluster' in df.columns else []))
    events_df = events_df.copy()
    events_df['cluster'] = labels

    # ── 5. Caracteristiques des clusters ──────────────────────────────────────
    needed_cols = ['max_precip', 'mean_precip', 'coverage_percent',
                   'max_anomaly', 'mean_anomaly', 'year', 'month', 'day_of_year', 'phase']
    missing = [c for c in needed_cols if c not in events_df.columns]
    if missing:
        # Recharger les colonnes manquantes depuis events_with_clusters existant
        ew_file = out_dir / f"{prefix}events_with_clusters.csv"
        if ew_file.exists():
            ref = pd.read_csv(ew_file)
            ref['date'] = ref['date'].astype(str).str[:10]
            events_df['date'] = events_df['date'].astype(str).str[:10]
            for col in missing:
                if col in ref.columns:
                    events_df = events_df.merge(
                        ref[['date', col]].drop_duplicates('date'),
                        on='date', how='left'
                    )

    cluster_stats = []
    for cid in sorted(unique):
        ev = events_df[events_df['cluster'] == cid]
        stats = {
            'cluster':              cid,
            'n_events':             int(len(ev)),
            'percentage':           float(len(ev) / n_events * 100),
            'mean_year':            float(ev['year'].mean())            if 'year'             in ev.columns else None,
            'mean_month':           float(ev['month'].mean())           if 'month'            in ev.columns else None,
            'mean_day_of_year':     float(ev['day_of_year'].mean())     if 'day_of_year'      in ev.columns else None,
            'mean_max_precip':      float(ev['max_precip'].mean())      if 'max_precip'       in ev.columns else None,
            'mean_mean_precip':     float(ev['mean_precip'].mean())     if 'mean_precip'      in ev.columns else None,
            'mean_coverage_percent':float(ev['coverage_percent'].mean())if 'coverage_percent' in ev.columns else None,
            'mean_max_anomaly':     float(ev['max_anomaly'].mean())     if 'max_anomaly'      in ev.columns else None,
            'mean_mean_anomaly':    float(ev['mean_anomaly'].mean())    if 'mean_anomaly'     in ev.columns else None,
            'n_years':              int(ev['year'].nunique())           if 'year'             in ev.columns else None,
        }
        if 'phase' in ev.columns:
            stats['phase_distribution'] = ev['phase'].value_counts().to_dict()
        cluster_stats.append(stats)

    chars_df = pd.DataFrame(cluster_stats)

    # ── 6. Tableau k / 3 methodes ─────────────────────────────────────────────
    remarques = [" | ".join(method_votes[k]) if method_votes[k] else "" for k in k_range]
    table_df  = pd.DataFrame({
        'k':               k_range,
        'Inertie':         [round(v, 2)  for v in inertias],
        'Silhouette':      [round(v, 4)  for v in sil_scores],
        'Davies-Bouldin':  [round(v, 4)  for v in db_scores],
        'Methode(s)':      remarques,
    })

    # ── 7. Mise a jour du fichier kmeans_input_pca.csv avec les nouveaux labels ─
    df_updated = df.drop(columns=['cluster'] if 'cluster' in df.columns else [])
    df_updated['cluster'] = labels
    df_updated.to_csv(pca_file, index=False, encoding='utf-8-sig')

    # ── 8. Sauvegarde des resultats ───────────────────────────────────────────
    # 8a. events_with_clusters.csv
    ew_out = out_dir / f"{prefix}events_with_clusters.csv"
    events_df.to_csv(ew_out, index=False, encoding='utf-8')
    print(f"[OK] {ew_out.name}")

    # 8b. cluster_characteristics.csv
    chars_out = out_dir / f"{prefix}cluster_characteristics.csv"
    chars_df.to_csv(chars_out, index=False, encoding='utf-8')
    print(f"[OK] {chars_out.name}")

    # 8c. kmeans_evaluation_metrics.json
    best_sil_idx = int(np.argmax(sil_scores))
    metrics_dict = {
        'k_range':               k_range,
        'inertias':              inertias,
        'silhouette_scores':     sil_scores,
        'davies_bouldin_scores': db_scores,
        'k_elbow':               k_elbow,
        'k_silhouette':          k_sil,
        'k_davies_bouldin':      k_db,
        'optimal_k':             forced_k,
        'best_silhouette_score': sil_scores[best_sil_idx],
        'decision':              f'k force a {forced_k} via dashboard (auto={k_optimal_auto})',
        'method_votes':          {str(k): v for k, v in method_votes.items()},
        'n_samples':             n_events,
        'n_pca_components':      n_comp,
        'source':                'fast_rerun_pca',
    }
    metrics_out = out_dir / f"{prefix}kmeans_evaluation_metrics.json"
    with open(metrics_out, 'w', encoding='utf-8') as fh:
        json.dump(metrics_dict, fh, indent=2, ensure_ascii=False)
    print(f"[OK] {metrics_out.name}")

    # 8d. kmeans_clustering_results.json
    results_dict = {
        'n_clusters':    forced_k,
        'optimal_k':     forced_k,
        'inertia':       float(km_final.inertia_),
        'cluster_sizes': {str(int(cl)): int(cnt) for cl, cnt in zip(unique, counts)},
        'source':        'fast_rerun_pca',
    }
    results_out = out_dir / f"{prefix}kmeans_clustering_results.json"
    with open(results_out, 'w', encoding='utf-8') as fh:
        json.dump(results_dict, fh, indent=2, ensure_ascii=False)
    print(f"[OK] {results_out.name}")

    # 8e. tableau_k_3_methodes.csv + .txt
    k3_out = out_dir / f"{prefix}tableau_k_3_methodes.csv"
    table_df.to_csv(k3_out, index=False, encoding='utf-8-sig')
    k3_txt = out_dir / f"{prefix}tableau_k_3_methodes.txt"
    with open(k3_txt, 'w', encoding='utf-8') as fh:
        fh.write("Tableau des k - 3 methodes de selection du k optimal\n")
        fh.write("=" * 70 + "\n\n")
        fh.write(table_df.to_string(index=False) + "\n\n")
        fh.write(f"  Coude :          k = {k_elbow}\n")
        fh.write(f"  Silhouette :     k = {k_sil}\n")
        fh.write(f"  Davies-Bouldin : k = {k_db}\n")
        fh.write(f"\n  k optimal retenu (force) : {forced_k}\n")
    print(f"[OK] {k3_out.name}")

    # 8f. Variance PCA (deja present, on ne la touche pas)

    # ── 9. Mise a jour des visualisations ─────────────────────────────────────
    _update_visualizations(
        X, labels, forced_k, k_range, inertias, sil_scores, db_scores,
        k_elbow, k_sil, k_db, chars_df, phase_name, viz_dir
    )

    print(f"\n[OK] Phase {phase_name} terminee en mode rapide (k={forced_k})")
    return True


# ─── Regeneration des figures ─────────────────────────────────────────────────
def _update_visualizations(X, labels, k, k_range, inertias, sil_scores, db_scores,
                            k_elbow, k_sil, k_db, chars_df, phase_name, viz_dir):

    phase_title = f" - {phase_name}"

    # Figure 00 : tableau synthetique
    remarques  = []
    mv = {ki: [] for ki in k_range}
    mv[k_elbow].append("coude")
    mv[k_sil].append("silhouette")
    mv[k_db].append("Davies-Bouldin")
    for ki in k_range:
        remarques.append(" | ".join(mv[ki]) if mv[ki] else "")

    table_data = [
        [str(ki),
         f"{iner:.2e}" if iner >= 1e4 else f"{iner:.4f}",
         f"{sil:.4f}", f"{db:.4f}", rem]
        for ki, iner, sil, db, rem
        in zip(k_range, inertias, sil_scores, db_scores, remarques)
    ]
    fig, ax = plt.subplots(figsize=(16, max(4, 0.45 * len(k_range) + 1)))
    ax.axis('off')
    tbl = ax.table(
        cellText=table_data,
        colLabels=['k', 'Inertie', 'Silhouette', 'Davies-Bouldin', 'Methode(s)'],
        loc='center', cellLoc='center', colColours=['#e0e0e0'] * 5,
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.1, 2.2)
    ax.set_title(f'Tableau synthetique - 3 methodes{phase_title}',
                 fontsize=13, fontweight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(viz_dir / "00_tableau_k_3_methodes.png", dpi=300, bbox_inches='tight')
    plt.close()

    # Figure 01 : courbes d'evaluation
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(f'Evaluation du Nombre Optimal de Clusters{phase_title}',
                 fontsize=16, fontweight='bold')

    axes[0].plot(k_range, inertias, 'bo-', linewidth=2, markersize=8)
    if k_elbow:
        axes[0].axvline(k_elbow, color='darkgreen', linestyle='--', alpha=0.7,
                        label=f'k coude = {k_elbow}')
    axes[0].axvline(k, color='red', linestyle=':', alpha=0.8, label=f'k retenu = {k}')
    axes[0].set_xlabel('k'); axes[0].set_ylabel('Inertie (WSS)')
    axes[0].set_title('Methode du Coude'); axes[0].legend(); axes[0].set_xticks(k_range)

    axes[1].plot(k_range, sil_scores, 'go-', linewidth=2, markersize=8)
    if k_sil:
        axes[1].axvline(k_sil, color='darkgreen', linestyle='--', alpha=0.7,
                        label=f'k silhouette = {k_sil}')
    axes[1].axvline(k, color='red', linestyle=':', alpha=0.8, label=f'k retenu = {k}')
    axes[1].set_xlabel('k'); axes[1].set_ylabel('Score Silhouette')
    axes[1].set_title('Methode Silhouette'); axes[1].legend(); axes[1].set_xticks(k_range)

    axes[2].plot(k_range, db_scores, 'ro-', linewidth=2, markersize=8)
    if k_db:
        axes[2].axvline(k_db, color='darkgreen', linestyle='--', alpha=0.7,
                        label=f'k DB = {k_db}')
    axes[2].axvline(k, color='red', linestyle=':', alpha=0.8, label=f'k retenu = {k}')
    axes[2].set_xlabel('k'); axes[2].set_ylabel('Davies-Bouldin')
    axes[2].set_title('Davies-Bouldin'); axes[2].legend(); axes[2].set_xticks(k_range)

    plt.tight_layout()
    plt.savefig(viz_dir / "01_evaluation_clusters.png", dpi=300, bbox_inches='tight')
    plt.close()

    # Figure 02 : PCA scatter (PC1 vs PC2)
    colors = plt.cm.tab20(np.linspace(0, 1, k))
    fig, ax = plt.subplots(figsize=(10, 8))
    for cid in range(k):
        mask = labels == cid
        ax.scatter(X[mask, 0], X[mask, 1], color=colors[cid],
                   label=f'Cluster {cid} (n={mask.sum()})', alpha=0.7, s=40)
    ax.set_xlabel('PC1'); ax.set_ylabel('PC2')
    ax.set_title(f'Clusters K-Means dans l\'espace PCA{phase_title} (k={k})')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=9)
    plt.tight_layout()
    plt.savefig(viz_dir / "02_clusters_pca.png", dpi=300, bbox_inches='tight')
    plt.close()

    # Figure 03 : caracteristiques des clusters
    if not chars_df.empty and 'mean_max_precip' in chars_df.columns:
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        fig.suptitle(f'Caracteristiques des Clusters{phase_title}', fontsize=14, fontweight='bold')
        cl_ids = chars_df['cluster'].tolist()
        c_arr  = [colors[int(c)] for c in cl_ids]

        ax = axes[0]
        ax.bar(cl_ids, chars_df['n_events'], color=c_arr, edgecolor='black', linewidth=0.5)
        ax.set_xlabel('Cluster'); ax.set_ylabel('Nb evenements')
        ax.set_title('Taille des clusters'); ax.set_xticks(cl_ids)

        ax = axes[1]
        if 'mean_max_precip' in chars_df.columns:
            ax.bar(cl_ids, chars_df['mean_max_precip'], color=c_arr, edgecolor='black', linewidth=0.5)
        ax.set_xlabel('Cluster'); ax.set_ylabel('Precip max moyenne (mm)')
        ax.set_title('Precipitation max moyenne'); ax.set_xticks(cl_ids)

        ax = axes[2]
        if 'mean_month' in chars_df.columns:
            ax.bar(cl_ids, chars_df['mean_month'], color=c_arr, edgecolor='black', linewidth=0.5)
            ax.set_ylim(4, 11); ax.set_yticks(range(5, 11))
            ax.set_yticklabels(['Mai', 'Jun', 'Jul', 'Aou', 'Sep', 'Oct'])
        ax.set_xlabel('Cluster'); ax.set_ylabel('Mois moyen')
        ax.set_title('Positionnement temporel moyen'); ax.set_xticks(cl_ids)

        plt.tight_layout()
        plt.savefig(viz_dir / "03_caracteristiques_clusters.png", dpi=300, bbox_inches='tight')
        plt.close()

    print(f"[OK] Visualisations mises a jour dans {viz_dir}")


# ─── Point d'entree ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Relance rapide K-Means depuis les donnees PCA pre-calculees'
    )
    parser.add_argument('--by-phase',   action='store_true',
                        help='Relancer uniquement les 3 phases (sans All_phases)')
    parser.add_argument('--global',     dest='global_only', action='store_true',
                        help='Relancer uniquement All_phases')
    parser.add_argument('--k-phase1',   type=int, default=None, metavar='K')
    parser.add_argument('--k-phase2',   type=int, default=None, metavar='K')
    parser.add_argument('--k-phase3',   type=int, default=None, metavar='K')
    parser.add_argument('--k-all',      type=int, default=None, metavar='K')
    args = parser.parse_args()

    # K par defaut (memes valeurs que 11_kmeans_sst_analysis.py)
    default_k = {
        'Phase_1_debut':  6,
        'Phase_2_pleine': 6,
        'Phase_3_fin':    5,
        'All_phases':     9,
    }
    k_map = {
        'Phase_1_debut':  args.k_phase1 or default_k['Phase_1_debut'],
        'Phase_2_pleine': args.k_phase2 or default_k['Phase_2_pleine'],
        'Phase_3_fin':    args.k_phase3 or default_k['Phase_3_fin'],
        'All_phases':     args.k_all    or default_k['All_phases'],
    }

    if args.global_only:
        phases = ['All_phases']
    elif args.by_phase:
        phases = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin']
    else:
        phases = ['Phase_1_debut', 'Phase_2_pleine', 'Phase_3_fin', 'All_phases']

    print("=" * 70)
    print("RELANCE RAPIDE K-MEANS (depuis donnees PCA)")
    print(f"Phases : {phases}")
    for ph in phases:
        print(f"  {ph} -> k={k_map[ph]}")
    print("=" * 70)

    success = True
    for ph in phases:
        ok = run_fast(ph, k_map[ph])
        if not ok:
            success = False

    if success:
        print("\n[OK] Toutes les phases traitees avec succes.")
    else:
        print("\n[ERREUR] Certaines phases ont echoue.")
        sys.exit(1)


if __name__ == "__main__":
    main()
