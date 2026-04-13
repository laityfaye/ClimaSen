#!/usr/bin/env python3
# scripts/04_teleconnections_analysis.py
"""
Analyse des teleconnexions climatiques - AGREGATION MENSUELLE + DETREND LINEAIRE.
APPROCHE PRINCIPALE RETENUE pour la these.

Methodologie :
  - Agregation mensuelle des evenements extremes (par mois calendaire)
  - Agregation mensuelle des indices SST (moyenne des valeurs journalieres)
  - Detrend lineaire (scipy.signal.detrend) applique sur chaque serie
    pour enlever les tendances a long terme avant le calcul des correlations
  - Lags testes en MOIS : 0, 1, 2, 3, 6, 9, 12
  - 5 metriques incluant le nombre d evenements par mois (n_events)
  - Correlations Pearson et Spearman
  - Correction autocorrelation : degres de liberte effectifs n_eff (Chelton 1983)
  - P-values corrigees AR1 : t = r*sqrt((n_eff-2)/(1-r^2)) ~ Student(n_eff-2)
  - Significativite (etoiles) : seuils sur p_neff uniquement (pas de correction FDR)
  - Analyse par phase de saison (Debut / Pleine saison / Fin)

Usage :
    python scripts/04_teleconnections_analysis.py
    python scripts/04_teleconnections_analysis.py --no-by-phase
    python scripts/04_teleconnections_analysis.py --lags 0 1 3 6 12
    python scripts/04_teleconnections_analysis.py --output-dir outputs/teleconnections
"""

import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr, t as t_dist
from scipy.signal import detrend as scipy_detrend

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import seaborn as sns
    SEABORN_AVAILABLE = True
except ImportError:
    SEABORN_AVAILABLE = False

# ==============================================================================
# CHEMINS DU PROJET
# ==============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EVENTS_FILE  = PROJECT_ROOT / "data" / "processed" / "extreme_events_phases_senegal.csv"
INDICES_FILE = PROJECT_ROOT / "data" / "raw" / "climate_indices" / "daily_indices_all.csv"
OUTPUT_DIR   = PROJECT_ROOT / "outputs" / "teleconnections"

# ==============================================================================
# CONFIGURATION
# ==============================================================================

ALL_INDICES = [
    "Nino12", "Nino3", "Nino34", "Nino4",   # Famille ENSO
    "IOD", "IOBM",                            # Ocean Indien
    "TNA", "TSA", "ATL3", "AMM", "AMO",      # Atlantique
]

METRICS = {
    "max_precip":        "Precipitation max mensuel (mm)",
    "mean_precip":       "Precipitation moy. (mm)",
    "max_anomaly":       "Anomalie max moy. (sigma)",
    "coverage_percent":  "Couverture spatiale moy. (%)",
    "n_events":          "Nombre d evenements",
}

# Lags en mois
DEFAULT_LAGS = [0, 1, 2, 3, 6, 9, 12]

PHASES = {
    "Phase_1_debut":  "Debut de saison (Mai-Jun)",
    "Phase_2_pleine": "Pleine saison (Jul-Aou)",
    "Phase_3_fin":    "Fin de saison (Sep-Oct)",
}

# Mois correspondant a chaque phase
PHASE_MONTHS = {
    "Phase_1_debut":  [5, 6],
    "Phase_2_pleine": [7, 8],
    "Phase_3_fin":    [9, 10],
}

PHASE_COLORS = {
    "Phase_1_debut":  "#2196F3",
    "Phase_2_pleine": "#FF5722",
    "Phase_3_fin":    "#4CAF50",
    "Toutes phases":  "#9C27B0",
}

MIN_OBS = 10  # minimum de mois pour calculer une correlation


# ==============================================================================
# 1. CHARGEMENT ET AGREGATION MENSUELLE
# ==============================================================================

def load_events_monthly(path: Path) -> pd.DataFrame:
    """
    Charge les evenements extremes et les agregee par mois.

    Pour chaque mois de saison (mai-octobre, 1983-2023) :
      - n_events          : nombre d evenements dans le mois (0 si aucun)
      - max_precip        : maximum du max_precip des evenements du mois (NaN si n_events=0)
      - mean_precip       : moyenne du mean_precip (NaN si n_events=0)
      - max_anomaly       : moyenne du max_anomaly (NaN si n_events=0)
      - coverage_percent  : moyenne du coverage_percent (NaN si n_events=0)

    Les mois sans evenement sont inclus (n_events=0) pour l analyse de frequence.
    Les metriques d intensite restent NaN pour ces mois et sont exclues
    automatiquement par dropna() dans compute_correlations().
    """
    print(f"  Evenements : {path.name}")
    df = pd.read_csv(path, parse_dates=["date"])

    # Filtrer a la periode couverte par les indices SST (1983+)
    n_total = len(df)
    df = df[df["date"].dt.year >= 1983].copy()
    n_excluded = n_total - len(df)
    print(f"    -> {len(df)} evenements (1983+)  "
          f"[{n_excluded} exclus avant 1983]  "
          f"({df['date'].min().date()} -- {df['date'].max().date()})")

    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # Agregation mensuelle (mois avec au moins 1 evenement)
    agg = df.groupby(["year", "month"]).agg(
        n_events         = ("date",            "count"),
        max_precip       = ("max_precip",       "max"),
        mean_precip      = ("mean_precip",      "mean"),
        max_anomaly      = ("max_anomaly",      "mean"),
        coverage_percent = ("coverage_percent", "mean"),
    ).reset_index()

    # Calendrier complet des mois de saison (mai-octobre, 1983-2023)
    # pour inclure les mois a n_events=0 dans l analyse de frequence
    SEASON_MONTHS = sorted(set(
        m for months in PHASE_MONTHS.values() for m in months
    ))
    full_calendar = pd.DataFrame(
        [(y, m) for y in range(1983, 2024) for m in SEASON_MONTHS],
        columns=["year", "month"]
    )

    # Fusionner : les mois sans evenement obtiennent n_events=0, NaN ailleurs
    agg = full_calendar.merge(agg, on=["year", "month"], how="left")
    agg["n_events"] = agg["n_events"].fillna(0).astype(int)

    # Identifiant numerique ordinal pour le calcul des lags (year*12 + month)
    agg["ym_ord"] = agg["year"] * 12 + agg["month"]

    n_with_events = (agg["n_events"] > 0).sum()
    n_zero        = (agg["n_events"] == 0).sum()
    print(f"    -> {n_with_events} mois avec evenements + "
          f"{n_zero} mois a zero = {len(agg)} mois de saison (mai-oct, 1983-2023)")
    return agg


def load_indices_monthly(path: Path) -> pd.DataFrame:
    """
    Charge les indices journaliers SST et les agregee en moyennes mensuelles.
    Retourne un DataFrame avec une ligne par (annee, mois).
    """
    print(f"  Indices SST : {path.name}")
    df = pd.read_csv(path, parse_dates=["date"])
    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month

    available = [c for c in ALL_INDICES if c in df.columns]

    monthly = df.groupby(["year", "month"])[available].mean().reset_index()
    monthly["ym_ord"] = monthly["year"] * 12 + monthly["month"]

    y_min = monthly["year"].min()
    m_min = monthly["month"].min()
    y_max = monthly["year"].max()
    m_max = monthly["month"].max()
    print(f"    -> {len(monthly)} mois  "
          f"({y_min}-{m_min:02d} -- {y_max}-{m_max:02d})")
    print(f"    -> {len(available)} indices : {', '.join(available)}")
    return monthly


# ==============================================================================
# 2. DETREND LINEAIRE
# ==============================================================================

def apply_detrend(values: np.ndarray) -> np.ndarray:
    """
    Applique un detrend lineaire sur un tableau de valeurs.
    Supprime la tendance lineaire (pente + ordonnee a l origine).
    Utilise scipy.signal.detrend avec type='linear'.
    """
    if len(values) < 3:
        return values
    return scipy_detrend(values, type='linear')


def detrend_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Applique le detrend lineaire sur chaque colonne specifiee.
    Le detrend est calcule uniquement sur les valeurs non-NaN.
    Retourne une copie du DataFrame avec les colonnes detrendees.
    """
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        valid = df[col].notna()
        if valid.sum() < 3:
            continue
        # Convertir en float pour eviter FutureWarning avec colonnes entieres
        df[col] = df[col].astype(float)
        vals = df.loc[valid, col].values
        df.loc[valid, col] = apply_detrend(vals)
    return df


# ==============================================================================
# 2b. DEGRES DE LIBERTE EFFECTIFS (AR1)
# ==============================================================================

def compute_ar1(x: np.ndarray) -> float:
    """
    Autocorrelation a lag-1 (AR1) d une serie centree.
    Retourne 0.0 si la serie est trop courte ou de variance nulle.
    """
    if len(x) < 4:
        return 0.0
    xc  = x - x.mean()
    den = np.sum(xc ** 2)
    if den == 0:
        return 0.0
    return float(np.sum(xc[1:] * xc[:-1]) / den)


def compute_n_eff(x: np.ndarray, y: np.ndarray) -> int:
    """
    Degres de liberte effectifs selon Chelton (1983) pour deux series AR1.

    Formule : n_eff = n * (1 - r1x * r1y) / (1 + r1x * r1y)
    Ou r1x et r1y sont les autocorrelations a lag-1 de x et y.

    n_eff est borne entre 3 et n. Un n_eff < n indique une autocorrelation
    positive qui gonfle la significativite nominale.
    """
    n   = len(x)
    r1x = compute_ar1(x)
    r1y = compute_ar1(y)
    denom = 1.0 + r1x * r1y
    if denom <= 0:
        return n
    n_eff = int(round(n * (1.0 - r1x * r1y) / denom))
    return max(3, min(n_eff, n))


def p_from_r_neff(r: float, n_eff: int) -> float:
    """
    Recalcule la p-value d un coefficient de correlation (Pearson ou Spearman)
    en utilisant les degres de liberte effectifs n_eff au lieu de n.

    Formule standard : t = r * sqrt((n_eff - 2) / (1 - r^2))
    sous H0 : t ~ Student(df = n_eff - 2)

    Note : la meme approximation t-Student s applique a Spearman rho pour n >= 10
    (Zar, 1972). La p-value nominale de pearsonr/spearmanr utilise n, pas n_eff,
    ce qui surestime la significativite quand les series sont autocorrelees.
    """
    if n_eff <= 2:
        return 1.0
    r_clipped = max(-1.0 + 1e-10, min(1.0 - 1e-10, r))
    t_stat = r_clipped * np.sqrt((n_eff - 2) / (1.0 - r_clipped ** 2))
    return float(2.0 * t_dist.sf(abs(t_stat), df=n_eff - 2))


# ==============================================================================
# 3. FUSION EVENEMENTS x INDICES AVEC LAG EN MOIS
# ==============================================================================

def merge_monthly_lag(events_m: pd.DataFrame,
                      indices_m: pd.DataFrame,
                      lag_months: int,
                      idx_cols: list) -> pd.DataFrame:
    """
    Pour chaque mois d evenement M, recupere les indices SST au mois (M - lag).

    La date de l evenement est M ; le signal SST precurseur est a M - lag_months.
    Exemple : lag=3 => si evenement en Juillet, on regarde l indice d Avril.
    """
    ev = events_m.copy()
    ev["lookup_ord"] = ev["ym_ord"] - lag_months

    idx = indices_m[["ym_ord"] + idx_cols].rename(
        columns={"ym_ord": "lookup_ord"}
    )

    merged = ev.merge(idx, on="lookup_ord", how="left")
    return merged


# ==============================================================================
# 4. CALCUL DES CORRELATIONS
# ==============================================================================

def _sig(p: float) -> str:
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    return ""


def compute_correlations(events_m: pd.DataFrame,
                         indices_m: pd.DataFrame,
                         phase_filter: str = None,
                         lags: list = None) -> pd.DataFrame:
    """
    Calcule Pearson et Spearman (apres detrend) pour chaque
    combinaison (metrique, indice, lag en mois).

    Le detrend est applique separement sur les metriques et sur les indices
    avant le calcul de chaque correlation.
    """
    if lags is None:
        lags = DEFAULT_LAGS

    avail_idx = [c for c in ALL_INDICES if c in indices_m.columns]
    avail_met = [m for m in METRICS     if m in events_m.columns]

    # Filtrage par phase (sur les mois correspondants)
    ev = events_m.copy()
    if phase_filter and phase_filter in PHASE_MONTHS:
        months_ok = PHASE_MONTHS[phase_filter]
        ev = ev[ev["month"].isin(months_ok)]

    rows = []

    for lag in lags:
        merged = merge_monthly_lag(ev, indices_m, lag, avail_idx)

        # Detrend lineaire sur les indices SST et les metriques d intensite.
        # n_events est exclu : variable de comptage entier >= 0,
        # le detrend genererait des valeurs negatives sans sens physique.
        merged_dt = detrend_columns(merged, avail_idx)
        metrics_to_detrend = [m for m in avail_met if m != "n_events"]
        merged_dt = detrend_columns(merged_dt, metrics_to_detrend)

        for metric in avail_met:
            metric_label = METRICS[metric]
            for idx in avail_idx:
                sub = merged_dt[[metric, idx]].dropna()
                n = len(sub)
                if n < MIN_OBS:
                    continue
                xv    = sub[metric].values.astype(float)
                yv    = sub[idx].values.astype(float)
                pr, pp = pearsonr(xv, yv)
                sr, sp = spearmanr(xv, yv)
                n_eff  = compute_n_eff(xv, yv)
                # P-values corrigees avec n_eff (Chelton 1983)
                pp_neff = p_from_r_neff(pr, n_eff)
                sp_neff = p_from_r_neff(sr, n_eff)
                rows.append({
                    "metric":           metric,
                    "metric_label":     metric_label,
                    "index":            idx,
                    "lag_months":       lag,
                    "pearson_r":        round(pr, 4),
                    "pearson_p":        round(pp, 4),
                    "pearson_p_neff":   round(pp_neff, 4),
                    "spearman_r":       round(sr, 4),
                    "spearman_p":       round(sp, 4),
                    "spearman_p_neff":  round(sp_neff, 4),
                    "n":                n,
                    "n_eff":            n_eff,
                    # Etoiles nominales conservees pour comparaison
                    "sig_pearson_nom":  _sig(pp),
                    "sig_spearman_nom": _sig(sp),
                })

    df = pd.DataFrame(rows)
    if df.empty:
        df["sig_pearson"]  = pd.Series(dtype=str)
        df["sig_spearman"] = pd.Series(dtype=str)
        return df

    # Etoiles basees sur p_neff seulement (correction AR1, sans FDR)
    df["sig_pearson"]  = df["pearson_p_neff"].apply(_sig)
    df["sig_spearman"] = df["spearman_p_neff"].apply(_sig)
    return df


# ==============================================================================
# 5. VISUALISATIONS
# ==============================================================================

def plot_heatmap_lag0(corr_df: pd.DataFrame, phase_name: str, out_dir: Path):
    """Heatmap Pearson + Spearman pour toutes metriques x indices (lag=0)."""
    if not MATPLOTLIB_AVAILABLE or corr_df.empty:
        return

    df0 = corr_df[corr_df["lag_months"] == 0]
    if df0.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(20, 6))
    fig.suptitle(
        f"Correlations mensuelles (lag=0 mois, apres detrend lineaire)\n{phase_name}",
        fontsize=12, fontweight="bold"
    )

    for ax, r_col, p_col, title in [
        (axes[0], "pearson_r",  "pearson_p_neff",  "Pearson r"),
        (axes[1], "spearman_r", "spearman_p_neff", "Spearman rho"),
    ]:
        try:
            pivot   = df0.pivot(index="metric_label", columns="index", values=r_col)
            pivot_p = df0.pivot(index="metric_label", columns="index", values=p_col)
            cols_ord = [c for c in ALL_INDICES if c in pivot.columns]
            pivot    = pivot[cols_ord]
            pivot_p  = pivot_p[cols_ord]
        except Exception:
            continue

        if SEABORN_AVAILABLE:
            sns.heatmap(pivot, ax=ax, cmap="RdBu_r", center=0,
                        vmin=-1, vmax=1, annot=False,
                        linewidths=0.4, linecolor="gray",
                        cbar_kws={"shrink": 0.8})
        else:
            im = ax.imshow(pivot.values, cmap="RdBu_r",
                           vmin=-1, vmax=1, aspect="auto")
            plt.colorbar(im, ax=ax, shrink=0.8)
            ax.set_xticks(range(len(pivot.columns)))
            ax.set_xticklabels(pivot.columns, rotation=45, ha="right")
            ax.set_yticks(range(len(pivot.index)))
            ax.set_yticklabels(pivot.index, rotation=0)

        for i, row_lbl in enumerate(pivot.index):
            for j, col_lbl in enumerate(pivot.columns):
                val = pivot.loc[row_lbl, col_lbl]
                pv  = pivot_p.loc[row_lbl, col_lbl]
                if pd.notna(val):
                    stars = _sig(pv)
                    color = "white" if abs(val) > 0.4 else "black"
                    ax.text(j + 0.5, i + 0.5, f"{val:+.2f}{stars}",
                            ha="center", va="center",
                            fontsize=7.5, color=color, fontweight="bold")

        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Indice SST")
        ax.tick_params(axis='x', rotation=45)

    plt.tight_layout()
    slug  = phase_name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")
    fname = out_dir / f"heatmap_{slug}.png"
    plt.savefig(fname, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"    -> {fname.name}")


def plot_lag_curves(corr_df: pd.DataFrame, metric: str,
                    phase_name: str, out_dir: Path):
    """Courbes de correlation en fonction du lag (mois) pour une metrique."""
    if not MATPLOTLIB_AVAILABLE or corr_df.empty:
        return

    sub_metric = corr_df[corr_df["metric"] == metric]
    if sub_metric.empty:
        return

    avail_idx = sub_metric["index"].unique().tolist()
    colors    = plt.cm.tab10(np.linspace(0, 1, len(avail_idx)))

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle(
        f"Correlations mensuelles decalees (apres detrend) -- "
        f"{METRICS.get(metric, metric)}\n{phase_name}",
        fontsize=11, fontweight="bold"
    )

    for ax, r_col, p_col, title in [
        (axes[0], "pearson_r",  "pearson_p_neff",  "Pearson r"),
        (axes[1], "spearman_r", "spearman_p_neff", "Spearman rho"),
    ]:
        for idx, color in zip(avail_idx, colors):
            s = sub_metric[sub_metric["index"] == idx].sort_values("lag_months")
            ax.plot(s["lag_months"], s[r_col], marker="o", label=idx,
                    linewidth=1.6, color=color, markersize=4)
            sig = s[s[p_col] < 0.05]
            ax.scatter(sig["lag_months"], sig[r_col], s=60, color=color, zorder=5)

        ax.axhline(0,    color="black", lw=0.8, linestyle="--")
        ax.axhline( 0.3, color="gray",  lw=0.5, linestyle=":")
        ax.axhline(-0.3, color="gray",  lw=0.5, linestyle=":")
        ax.set_xlabel("Lag (mois)")
        ax.set_ylabel(title)
        ax.set_title(title)
        ax.legend(fontsize=7, ncol=2)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    slug  = phase_name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")
    mslug = metric.replace(" ", "_")
    fname = out_dir / f"lag_{mslug}_{slug}.png"
    plt.savefig(fname, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"    -> {fname.name}")


def plot_lag_heatmap(corr_df: pd.DataFrame, metric: str,
                     phase_name: str, out_dir: Path):
    """Heatmap 2D : indices x lags (mois) pour une metrique donnee."""
    if not MATPLOTLIB_AVAILABLE or corr_df.empty:
        return

    sub = corr_df[corr_df["metric"] == metric]
    if sub.empty:
        return

    try:
        pivot   = sub.pivot(index="index", columns="lag_months", values="pearson_r")
        pivot_p = sub.pivot(index="index", columns="lag_months", values="pearson_p_neff")
        rows_ord = [c for c in ALL_INDICES if c in pivot.index]
        pivot    = pivot.loc[rows_ord]
        pivot_p  = pivot_p.loc[rows_ord]
    except Exception:
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(
        f"Pearson r (apres detrend) : {METRICS.get(metric, metric)} -- {phase_name}",
        fontsize=11, fontweight="bold"
    )

    if SEABORN_AVAILABLE:
        sns.heatmap(pivot, ax=ax, cmap="RdBu_r", center=0,
                    vmin=-0.5, vmax=0.5, annot=False,
                    linewidths=0.4, linecolor="gray",
                    cbar_kws={"label": "Pearson r", "shrink": 0.8})
    else:
        im = ax.imshow(pivot.values, cmap="RdBu_r",
                       vmin=-0.5, vmax=0.5, aspect="auto")
        plt.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")

    for i, idx in enumerate(pivot.index):
        for j, lag in enumerate(pivot.columns):
            val = pivot.loc[idx, lag]
            pv  = pivot_p.loc[idx, lag]
            if pd.notna(val):
                stars = _sig(pv)
                color = "white" if abs(val) > 0.3 else "black"
                ax.text(j + 0.5, i + 0.5, f"{val:+.2f}{stars}",
                        ha="center", va="center",
                        fontsize=7, color=color, fontweight="bold")

    ax.set_xlabel("Lag (mois)")
    ax.set_ylabel("Indice SST")
    ax.set_xticks([c + 0.5 for c in range(len(pivot.columns))])
    ax.set_xticklabels([str(int(c)) for c in pivot.columns])
    ax.set_yticks([r + 0.5 for r in range(len(pivot.index))])
    ax.set_yticklabels(pivot.index, rotation=0)

    plt.tight_layout()
    slug  = phase_name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")
    mslug = metric.replace(" ", "_")
    fname = out_dir / f"lag_heatmap_{mslug}_{slug}.png"
    plt.savefig(fname, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"    -> {fname.name}")


def plot_summary(all_corrs: dict, out_dir: Path):
    """Synthese : barres Pearson lag=0 par phase pour max_precip et n_events."""
    if not MATPLOTLIB_AVAILABLE:
        return

    metrics_show = ["max_precip", "n_events"]
    phases_list  = list(all_corrs.keys())
    n_m, n_p     = len(metrics_show), len(phases_list)

    fig, axes = plt.subplots(n_m, n_p,
                              figsize=(max(5 * n_p, 12), 4 * n_m),
                              sharey="row")
    if n_p == 1: axes = axes.reshape(n_m, 1)
    if n_m == 1: axes = axes.reshape(1, n_p)

    fig.suptitle(
        "Correlations Pearson (lag=0 mois, apres detrend) par phase et metrique",
        fontsize=12, fontweight="bold"
    )

    for col_i, (phase_key, corr_df) in enumerate(all_corrs.items()):
        label = PHASES.get(phase_key, phase_key)
        df0   = (corr_df[corr_df["lag_months"] == 0]
                 if not corr_df.empty else pd.DataFrame())

        for row_i, metric in enumerate(metrics_show):
            ax  = axes[row_i][col_i]
            sub = df0[df0["metric"] == metric] if not df0.empty else pd.DataFrame()

            if sub.empty:
                ax.text(0.5, 0.5, "Pas de donnees",
                        ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{label}\n{METRICS.get(metric, metric)}", fontsize=8)
                continue

            sub        = sub.sort_values("pearson_r")
            bar_colors = ["#c62828" if r < 0 else "#1565C0"
                          for r in sub["pearson_r"]]
            bars       = ax.barh(sub["index"], sub["pearson_r"],
                                 color=bar_colors, edgecolor="white", height=0.6)

            ax.axvline(0,    color="black", lw=0.8)
            ax.axvline( 0.3, color="gray",  lw=0.5, linestyle=":")
            ax.axvline(-0.3, color="gray",  lw=0.5, linestyle=":")
            ax.set_xlim(-1, 1)

            for bar, (_, row_s) in zip(bars, sub.iterrows()):
                r     = row_s["pearson_r"]
                stars = _sig(row_s["pearson_p_neff"])
                ha    = "left"  if r >= 0 else "right"
                off   = 0.03   if r >= 0 else -0.03
                ax.text(r + off, bar.get_y() + bar.get_height() / 2,
                        f"{r:+.3f}{stars}",
                        va="center", ha=ha, fontsize=7.5, fontweight="bold")

            ax.set_title(f"{label}\n{METRICS.get(metric, metric)}", fontsize=8)
            ax.set_xlabel("Pearson r")
            ax.grid(True, axis='x', alpha=0.3)

    plt.tight_layout()
    fname = out_dir / "synthese_correlations.png"
    plt.savefig(fname, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"    -> {fname.name}")


# ==============================================================================
# 6. RAPPORT TEXTE
# ==============================================================================

def generate_report(all_corrs: dict, n_events_raw: int, n_months: int,
                    lags: list, out_dir: Path):
    """Rapport texte complet."""
    sep = "=" * 84
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        sep,
        "RAPPORT -- TELECONNEXIONS (AGREGATION MENSUELLE + DETREND LINEAIRE)",
        "Precipitations extremes au Senegal x Indices SST mensuels",
        sep,
        f"Genere le             : {now}",
        f"Evenements bruts      : {n_events_raw} (1983-2023)",
        f"Mois de saison total  : {n_months} (n_events=0 inclus pour frequence)",
        f"Lags testes (mois)    : {lags}",
        f"Indices               : {', '.join(ALL_INDICES)}",
        "",
        "METHODE :",
        "  1. Agregation mensuelle : calendrier complet mai-oct (1983-2023)",
        "     n_events=0 pour les mois sans evenements (intensite : NaN)",
        "     max_precip = maximum mensuel (pas moyenne) pour capter l evenement extreme",
        "  2. Agregation mensuelle : moyenne des indices SST journaliers par mois",
        "  3. Detrend lineaire (scipy.signal.detrend type=linear) sur indices SST",
        "     et metriques d intensite -- n_events exclu (comptage, valeurs >= 0)",
        "  4. Correlation Pearson + Spearman a differents lags en mois",
        "  5. n_eff : degres de liberte effectifs (Chelton 1983, AR1)",
        "     n_eff = n*(1-r1x*r1y)/(1+r1x*r1y)  -- autocorrelation lag-1 des series",
        "     n_eff < n indique une autocorrelation positive (significativite surestimee)",
        "  6. P-values corrigees AR1 : t = r*sqrt((n_eff-2)/(1-r^2)) ~ Student(n_eff-2)",
        "     p_neff : p-value recalculee avec n_eff degres de liberte.",
        "     Les etoiles (*/**/***) sont basees sur p_neff (pas de correction FDR pour tests multiples).",
        "     p_nom : p-value brute (n independant) conservee pour reference.",
        "Source SST : NOAA OISST v2 High-Resolution 0.25deg (journalier -> mensuel)",
        "",
    ]

    for phase_key, corr_df in all_corrs.items():
        label = PHASES.get(phase_key, phase_key)
        lines += [sep, f"PHASE : {label}", sep]

        if corr_df.empty:
            lines.append("  (aucune donnee)")
            continue

        for lag in lags:
            df_lag = corr_df[corr_df["lag_months"] == lag]
            if df_lag.empty:
                continue

            lines.append(f"\n  -- Lag = {lag} mois --")
            hdr = (f"  {'Metrique':<32} {'Indice':<8}"
                   f" {'Pearson r':>10} {'sig':>4} {'p_neff':>8} {'p_nom':>8}"
                   f"  {'Spearman':>10} {'sig':>4} {'p_neff':>8} {'p_nom':>8}"
                   f"  {'n':>5}  {'n_eff':>6}")
            lines.append(hdr)
            lines.append("  " + "-" * 118)

            for metric in METRICS:
                sub = df_lag[df_lag["metric"] == metric].sort_values("index")
                for _, row in sub.iterrows():
                    n_eff_val   = int(row["n_eff"]) if "n_eff" in row and pd.notna(row["n_eff"]) else int(row["n"])
                    pp_neff_val = row["pearson_p_neff"]  if "pearson_p_neff"  in row else row["pearson_p"]
                    sp_neff_val = row["spearman_p_neff"] if "spearman_p_neff" in row else row["spearman_p"]
                    lines.append(
                        f"  {row['metric_label']:<32} {row['index']:<8}"
                        f" {row['pearson_r']:>+10.4f} {row['sig_pearson']:>4}"
                        f" {pp_neff_val:>8.4f} {row['pearson_p']:>8.4f}"
                        f"  {row['spearman_r']:>+10.4f} {row['sig_spearman']:>4}"
                        f" {sp_neff_val:>8.4f} {row['spearman_p']:>8.4f}"
                        f"  {int(row['n']):>5}  {n_eff_val:>6}"
                    )
                lines.append("")

    lines += [
        sep,
        "LEGENDE",
        sep,
        "  * p<0.05  ** p<0.01  *** p<0.001   (seuils appliques sur p_neff)",
        "  n       : nombre d observations (mois) apres dropna",
        "  n_eff   : degres de liberte effectifs AR1 (Chelton 1983)",
        "            n_eff = n*(1-r1x*r1y)/(1+r1x*r1y)",
        "            Si n_eff << n -> autocorrelation elevee -> significativite surestimee",
        "  p_neff  : p-value recalculee avec n_eff (t = r*sqrt((n_eff-2)/(1-r^2)))",
        "            Les etoiles (*/**/***) sont derivees de p_neff.",
        "  p_nom   : p-value nominale brute (utilise n, conservee pour reference)",
        "",
        "  Interpretation de |r| :",
        "  < 0.2          : Tres faible",
        "  0.2 -- 0.4     : Faible",
        "  0.4 -- 0.6     : Moderee",
        "  0.6 -- 0.8     : Forte",
        "  > 0.8          : Tres forte",
        "",
        sep,
        "FIN DU RAPPORT",
        sep,
    ]

    out_file = out_dir / "rapport_teleconnections.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"    -> {out_file.name}")


# ==============================================================================
# 7. PIPELINE PRINCIPAL
# ==============================================================================

def run(by_phase: bool = True,
        lags: list = None,
        output_dir: Path = OUTPUT_DIR):

    if lags is None:
        lags = DEFAULT_LAGS

    print()
    print("=" * 70)
    print("  TELECONNEXIONS -- AGREGATION MENSUELLE + DETREND LINEAIRE")
    print("=" * 70)
    print(f"  Analyse par phase : {'Oui' if by_phase else 'Non'}")
    print(f"  Lags (mois)       : {lags}")
    print(f"  Indices           : {len(ALL_INDICES)}")
    print(f"  Detrend           : scipy.signal.detrend (type=linear)")

    viz_dir = output_dir / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)
    viz_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    print("\n[1/5] Chargement et agregation mensuelle")
    events_m  = load_events_monthly(EVENTS_FILE)
    indices_m = load_indices_monthly(INDICES_FILE)

    # Nombre d evenements bruts (avant filtre 1983)
    n_events_raw = len(
        pd.read_csv(EVENTS_FILE, parse_dates=["date"])
    )
    n_months = len(events_m)

    # ------------------------------------------------------------------
    if by_phase:
        phase_configs = {
            "Toutes phases": None,
            **{k: k for k in PHASES},
        }
    else:
        phase_configs = {"Toutes phases": None}

    # ------------------------------------------------------------------
    print("\n[2/5] Calcul des correlations (agregation mensuelle + detrend lineaire)")
    all_corrs = {}

    for phase_key, phase_filter in phase_configs.items():
        label = PHASES.get(phase_key, phase_key)
        print(f"\n  > {label}")

        ev_phase = events_m.copy()
        if phase_filter and phase_filter in PHASE_MONTHS:
            months_ok = PHASE_MONTHS[phase_filter]
            ev_phase  = ev_phase[ev_phase["month"].isin(months_ok)]

        n_zero_phase = (ev_phase["n_events"] == 0).sum()
        print(f"    {len(ev_phase)} mois de saison "
              f"(dont {n_zero_phase} a zero pour n_events)")

        if len(ev_phase) < MIN_OBS:
            all_corrs[phase_key] = pd.DataFrame()
            continue

        corr_df = compute_correlations(
            ev_phase, indices_m,
            phase_filter=phase_filter,
            lags=lags
        )
        all_corrs[phase_key] = corr_df

        if not corr_df.empty:
            out_csv = output_dir / f"correlations_{phase_key}.csv"
            corr_df.to_csv(out_csv, index=False)
            print(f"    Sauvegarde : {out_csv.name}")

    # ------------------------------------------------------------------
    print("\n[3/5] Visualisations")
    for phase_key, corr_df in all_corrs.items():
        label = PHASES.get(phase_key, phase_key)
        if corr_df.empty:
            continue
        print(f"  > {label}")
        plot_heatmap_lag0(corr_df, label, viz_dir)
        for metric in METRICS:
            plot_lag_curves(corr_df, metric, label, viz_dir)
            plot_lag_heatmap(corr_df, metric, label, viz_dir)

    print(f"  > Synthese")
    plot_summary(all_corrs, viz_dir)

    # ------------------------------------------------------------------
    print("\n[4/5] Rapport")
    generate_report(all_corrs, n_events_raw, n_months, lags, output_dir)

    # ------------------------------------------------------------------
    print("\n[5/5] Resume")
    print()
    print("=" * 78)
    print("  CORRELATIONS PEARSON (lag=0, detrend, mensuel) -- max_precip")
    print("=" * 78)
    hdr = f"  {'Phase':<28}"
    for idx in ALL_INDICES:
        hdr += f" {idx:>8}"
    print(hdr)
    print("  " + "-" * (28 + 9 * len(ALL_INDICES)))

    for phase_key, corr_df in all_corrs.items():
        label = PHASES.get(phase_key, phase_key)[:28]
        if corr_df.empty:
            print(f"  {label:<28}  (pas de donnees)")
            continue
        df0 = corr_df[(corr_df["lag_months"] == 0) &
                      (corr_df["metric"] == "max_precip")]
        row_str = f"  {label:<28}"
        for idx in ALL_INDICES:
            sub = df0[df0["index"] == idx]
            if sub.empty:
                row_str += "      n/a"
            else:
                r = sub["pearson_r"].values[0]
                p = sub["pearson_p_neff"].values[0]
                row_str += f" {r:+7.3f}{_sig(p):<1}"
        print(row_str)

    print()
    print("  * p<0.05  ** p<0.01  *** p<0.001  (seuils sur p_neff, correction AR1)")
    print(f"\n  Resultats dans : {output_dir}")
    print("=" * 78)
    print()


# ==============================================================================
# ENTREE DU PROGRAMME
# ==============================================================================

def setup_arguments():
    parser = argparse.ArgumentParser(
        description="Teleconnexions climatiques -- agregation mensuelle + detrend lineaire",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Indices SST (11) : Nino12, Nino3, Nino34, Nino4, IOD, IOBM,
                   TNA, TSA, ATL3, AMM, AMO
Source SST       : NOAA OISST v2 (0.25deg, journalier -> mensuel)
Lags par defaut  : 0, 1, 2, 3, 6, 9, 12 mois
Detrend          : scipy.signal.detrend(type='linear') sur chaque serie

Exemples :
  python scripts/04_1_teleconnections.py
  python scripts/04_1_teleconnections.py --no-by-phase
  python scripts/04_1_teleconnections.py --lags 0 1 3 6 12
  python scripts/04_1_teleconnections.py --output-dir outputs/teleconnections_monthly
        """
    )
    parser.add_argument(
        "--by-phase", action="store_true", default=True,
        help="Analyser chaque phase separement (defaut: True)"
    )
    parser.add_argument(
        "--no-by-phase", dest="by_phase", action="store_false",
        help="Analyse globale uniquement (sans decoupe par phase)"
    )
    parser.add_argument(
        "--lags", type=int, nargs="+", default=DEFAULT_LAGS,
        metavar="N",
        help="Lags en mois (ex: --lags 0 1 3 6 12)"
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(OUTPUT_DIR),
        help=f"Repertoire de sortie (defaut: {OUTPUT_DIR})"
    )
    return parser


if __name__ == "__main__":
    parser = setup_arguments()
    args   = parser.parse_args()
    run(
        by_phase   = args.by_phase,
        lags       = sorted(set(args.lags)),
        output_dir = Path(args.output_dir),
    )
