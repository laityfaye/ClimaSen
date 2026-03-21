#!/usr/bin/env python3
# scripts/04_teleconnections_analysis.py
"""
Analyse des teleconnexions climatiques - INDICES JOURNALIERS SST (OISST v2).

Liens entre les modes de variabilite climatique a grande echelle et les
precipitations extremes au Senegal. Approche entierement journaliere :

  - Indices SST calcules depuis NOAA OISST v2 (0.25deg, journalier, 1983-2023)
  - Correspondance directe evenement(jour D) x indice(jour D - lag)
  - 11 indices : Nino12, Nino3, Nino34, Nino4, IOD, IOBM,
                 TNA, TSA, ATL3, AMM, AMO
  - Lags testes en jours : 0, 1, 3, 5, 7, 14, 30, 60, 90
  - Correlations Pearson et Spearman sans detrend ni test de stationnarite
  - Analyse par phase de saison (Debut / Pleine saison / Fin)

Usage :
    python scripts/04_teleconnections_analysis.py
    python scripts/04_teleconnections_analysis.py --no-by-phase
    python scripts/04_teleconnections_analysis.py --lags 0 7 14 30 60
    python scripts/04_teleconnections_analysis.py --output-dir outputs/teleconnections
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

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
    "max_precip":       "Precipitation max (mm)",
    "mean_precip":      "Precipitation moyenne (mm)",
    "max_anomaly":      "Anomalie max (sigma)",
    "coverage_percent": "Couverture spatiale (%)",
}

DEFAULT_LAGS = [0, 1, 3, 5, 7, 14, 30, 60, 90]  # jours

PHASES = {
    "Phase_1_debut":  "Debut de saison (Mai-Jun)",
    "Phase_2_pleine": "Pleine saison (Jul-Aou)",
    "Phase_3_fin":    "Fin de saison (Sep-Oct)",
}

PHASE_COLORS = {
    "Phase_1_debut":  "#2196F3",
    "Phase_2_pleine": "#FF5722",
    "Phase_3_fin":    "#4CAF50",
    "Toutes phases":  "#9C27B0",
}

MIN_OBS = 10


# ==============================================================================
# 1. CHARGEMENT DES DONNEES
# ==============================================================================

def load_events(path: Path) -> pd.DataFrame:
    """Charge les evenements extremes."""
    print(f"  Evenements : {path.name}")
    df = pd.read_csv(path, parse_dates=["date"])
    print(f"    -> {len(df)} evenements  "
          f"({df['date'].min().date()} -- {df['date'].max().date()})")
    return df


def load_daily_indices(path: Path) -> pd.DataFrame:
    """Charge les indices journaliers SST."""
    print(f"  Indices SST : {path.name}")
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.set_index("date")
    available = [c for c in ALL_INDICES if c in df.columns]
    df = df[available]
    print(f"    -> {len(df)} jours  "
          f"({df.index.min().date()} -- {df.index.max().date()})")
    print(f"    -> {len(available)} indices : {', '.join(available)}")
    return df


# ==============================================================================
# 2. FUSION EVENEMENTS x INDICES (avec lag en jours)
# ==============================================================================

def merge_events_indices(events: pd.DataFrame,
                         daily_idx: pd.DataFrame,
                         lag_days: int) -> pd.DataFrame:
    """
    Pour chaque evenement a la date D, recupere les valeurs de tous les indices
    a la date D - lag_days (l'indice precede l'evenement).

    Returns DataFrame avec colonnes : date, phase, metriques + indices.
    """
    ev = events.copy()
    ev["lookup_date"] = ev["date"] - pd.Timedelta(days=lag_days)

    merged = ev.merge(
        daily_idx.reset_index().rename(columns={"date": "lookup_date"}),
        on="lookup_date",
        how="left"
    )
    return merged


# ==============================================================================
# 3. CALCUL DES CORRELATIONS
# ==============================================================================

def _sig(p: float) -> str:
    if p < 0.001: return "***"
    if p < 0.01:  return "**"
    if p < 0.05:  return "*"
    return ""


def compute_correlations(events: pd.DataFrame,
                         daily_idx: pd.DataFrame,
                         phase_filter: str = None,
                         lags: list = None) -> pd.DataFrame:
    """
    Calcule Pearson et Spearman pour chaque (metrique, indice, lag).

    Returns
    -------
    DataFrame avec colonnes : metric, metric_label, index, lag_days,
                              pearson_r, pearson_p, spearman_r, spearman_p, n
    """
    if lags is None:
        lags = DEFAULT_LAGS

    ev = events.copy()
    if phase_filter:
        ev = ev[ev["phase"] == phase_filter]

    avail_idx = [c for c in ALL_INDICES if c in daily_idx.columns]
    rows = []

    for lag in lags:
        merged = merge_events_indices(ev, daily_idx, lag)
        for metric, metric_label in METRICS.items():
            if metric not in merged.columns:
                continue
            for idx in avail_idx:
                sub = merged[[metric, idx]].dropna()
                n = len(sub)
                if n < MIN_OBS:
                    continue
                xv = sub[metric].values
                yv = sub[idx].values
                pr, pp = pearsonr(xv, yv)
                sr, sp = spearmanr(xv, yv)
                rows.append({
                    "metric":       metric,
                    "metric_label": metric_label,
                    "index":        idx,
                    "lag_days":     lag,
                    "pearson_r":    round(pr, 4),
                    "pearson_p":    round(pp, 4),
                    "spearman_r":   round(sr, 4),
                    "spearman_p":   round(sp, 4),
                    "n":            n,
                    "sig_pearson":  _sig(pp),
                    "sig_spearman": _sig(sp),
                })

    return pd.DataFrame(rows)


# ==============================================================================
# 4. VISUALISATIONS
# ==============================================================================

def plot_heatmap_lag0(corr_df: pd.DataFrame, phase_name: str, out_dir: Path):
    """Heatmap Pearson + Spearman pour toutes metriques x indices (lag=0)."""
    if not MATPLOTLIB_AVAILABLE or corr_df.empty:
        return

    df0 = corr_df[corr_df["lag_days"] == 0]
    if df0.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(20, 5))
    fig.suptitle(f"Correlations journalieres (lag=0 j) -- {phase_name}",
                 fontsize=12, fontweight="bold")

    for ax, r_col, p_col, title in [
        (axes[0], "pearson_r",  "pearson_p",  "Pearson r"),
        (axes[1], "spearman_r", "spearman_p", "Spearman rho"),
    ]:
        try:
            pivot   = df0.pivot(index="metric_label", columns="index", values=r_col)
            pivot_p = df0.pivot(index="metric_label", columns="index", values=p_col)
            cols_ord = [c for c in ALL_INDICES if c in pivot.columns]
            pivot   = pivot[cols_ord]
            pivot_p = pivot_p[cols_ord]
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
    slug = phase_name.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")
    fname = out_dir / f"heatmap_{slug}.png"
    plt.savefig(fname, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"    -> {fname.name}")


def plot_lag_curves(corr_df: pd.DataFrame, metric: str,
                    phase_name: str, out_dir: Path):
    """Courbes des correlations en fonction du lag (jours) pour une metrique."""
    if not MATPLOTLIB_AVAILABLE or corr_df.empty:
        return

    sub_metric = corr_df[corr_df["metric"] == metric]
    if sub_metric.empty:
        return

    avail_idx = sub_metric["index"].unique().tolist()
    colors = plt.cm.tab10(np.linspace(0, 1, len(avail_idx)))

    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle(
        f"Correlations decalees -- {METRICS.get(metric, metric)}\n{phase_name}",
        fontsize=11, fontweight="bold"
    )

    for ax, r_col, p_col, title in [
        (axes[0], "pearson_r",  "pearson_p",  "Pearson r"),
        (axes[1], "spearman_r", "spearman_p", "Spearman rho"),
    ]:
        for idx, color in zip(avail_idx, colors):
            s = sub_metric[sub_metric["index"] == idx].sort_values("lag_days")
            ax.plot(s["lag_days"], s[r_col], marker="o", label=idx,
                    linewidth=1.6, color=color, markersize=4)
            sig = s[s[p_col] < 0.05]
            ax.scatter(sig["lag_days"], sig[r_col], s=60, color=color, zorder=5)

        ax.axhline(0,    color="black", lw=0.8, linestyle="--")
        ax.axhline( 0.3, color="gray",  lw=0.5, linestyle=":")
        ax.axhline(-0.3, color="gray",  lw=0.5, linestyle=":")
        ax.set_xlabel("Lag (jours)")
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


def plot_summary(all_corrs: dict, out_dir: Path):
    """Synthese : barres Pearson (lag=0) par phase pour max_precip et max_anomaly."""
    if not MATPLOTLIB_AVAILABLE:
        return

    metrics_show = ["max_precip", "max_anomaly"]
    phases_list  = list(all_corrs.keys())
    n_m, n_p     = len(metrics_show), len(phases_list)

    fig, axes = plt.subplots(n_m, n_p,
                              figsize=(max(5 * n_p, 12), 4 * n_m),
                              sharey="row")
    if n_p == 1: axes = axes.reshape(n_m, 1)
    if n_m == 1: axes = axes.reshape(1, n_p)

    fig.suptitle("Correlations Pearson (lag=0) par phase et metrique",
                 fontsize=12, fontweight="bold")

    for col_i, (phase_key, corr_df) in enumerate(all_corrs.items()):
        label = PHASES.get(phase_key, phase_key)
        df0 = (corr_df[corr_df["lag_days"] == 0]
               if not corr_df.empty else pd.DataFrame())

        for row_i, metric in enumerate(metrics_show):
            ax = axes[row_i][col_i]
            sub = df0[df0["metric"] == metric] if not df0.empty else pd.DataFrame()

            if sub.empty:
                ax.text(0.5, 0.5, "Pas de donnees",
                        ha="center", va="center", transform=ax.transAxes)
                ax.set_title(f"{label}\n{METRICS.get(metric, metric)}", fontsize=8)
                continue

            sub = sub.sort_values("pearson_r")
            bar_colors = ["#c62828" if r < 0 else "#1565C0" for r in sub["pearson_r"]]
            bars = ax.barh(sub["index"], sub["pearson_r"],
                           color=bar_colors, edgecolor="white", height=0.6)

            ax.axvline(0,    color="black", lw=0.8)
            ax.axvline( 0.3, color="gray",  lw=0.5, linestyle=":")
            ax.axvline(-0.3, color="gray",  lw=0.5, linestyle=":")
            ax.set_xlim(-1, 1)

            for bar, (_, row_s) in zip(bars, sub.iterrows()):
                r   = row_s["pearson_r"]
                stars = _sig(row_s["pearson_p"])
                ha  = "left" if r >= 0 else "right"
                off = 0.03 if r >= 0 else -0.03
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


def plot_lag_heatmap(corr_df: pd.DataFrame, metric: str,
                     phase_name: str, out_dir: Path):
    """Heatmap 2D : indices x lags pour une metrique."""
    if not MATPLOTLIB_AVAILABLE or corr_df.empty:
        return

    sub = corr_df[corr_df["metric"] == metric]
    if sub.empty:
        return

    try:
        pivot = sub.pivot(index="index", columns="lag_days", values="pearson_r")
        pivot_p = sub.pivot(index="index", columns="lag_days", values="pearson_p")
        rows_ord = [c for c in ALL_INDICES if c in pivot.index]
        pivot   = pivot.loc[rows_ord]
        pivot_p = pivot_p.loc[rows_ord]
    except Exception:
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(
        f"Pearson r : {METRICS.get(metric, metric)} -- {phase_name}",
        fontsize=11, fontweight="bold"
    )

    if SEABORN_AVAILABLE:
        sns.heatmap(pivot, ax=ax, cmap="RdBu_r", center=0,
                    vmin=-0.5, vmax=0.5, annot=False,
                    linewidths=0.4, linecolor="gray",
                    cbar_kws={"label": "Pearson r", "shrink": 0.8})
    else:
        im = ax.imshow(pivot.values, cmap="RdBu_r", vmin=-0.5, vmax=0.5, aspect="auto")
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

    ax.set_xlabel("Lag (jours)")
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


# ==============================================================================
# 5. RAPPORT TEXTE
# ==============================================================================

def generate_report(all_corrs: dict, n_events: int, n_sst: int,
                    lags: list, out_dir: Path):
    """Rapport texte complet."""
    sep  = "=" * 84
    sep2 = "-" * 60
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        sep,
        "RAPPORT -- TELECONNEXIONS CLIMATIQUES (INDICES JOURNALIERS SST OISST v2)",
        "Precipitations extremes au Senegal x Indices SST journaliers",
        sep,
        f"Genere le        : {now}",
        f"Evenements total : {n_events}",
        f"Avec SST (1983+) : {n_sst}",
        f"Lags testes (j)  : {lags}",
        f"Indices          : {', '.join(ALL_INDICES)}",
        "",
        "METHODE : correlation directe evenement(jour D) x indice(jour D - lag)",
        "Source SST : NOAA OISST v2 High-Resolution 0.25deg (journalier)",
        "Aucun detrend. Aucun test de stationnarite. Agregation mensuelle : NON.",
        "",
    ]

    for phase_key, corr_df in all_corrs.items():
        label = PHASES.get(phase_key, phase_key)
        lines += [sep, f"PHASE : {label}", sep]

        if corr_df.empty:
            lines.append("  (aucune donnee)")
            continue

        for lag in lags:
            df_lag = corr_df[corr_df["lag_days"] == lag]
            if df_lag.empty:
                continue

            lines.append(f"\n  -- Lag = {lag} jour(s) --")
            hdr = (f"  {'Metrique':<30} {'Indice':<8}"
                   f" {'Pearson r':>10} {'sig':>4} {'p':>8}"
                   f"  {'Spearman':>10} {'sig':>4} {'p':>8}  {'n':>5}")
            lines.append(hdr)
            lines.append("  " + "-" * 84)

            for metric in METRICS:
                sub = df_lag[df_lag["metric"] == metric].sort_values("index")
                for _, row in sub.iterrows():
                    lines.append(
                        f"  {row['metric_label']:<30} {row['index']:<8}"
                        f" {row['pearson_r']:>+10.4f} {row['sig_pearson']:>4}"
                        f" {row['pearson_p']:>8.4f}"
                        f"  {row['spearman_r']:>+10.4f} {row['sig_spearman']:>4}"
                        f" {row['spearman_p']:>8.4f}  {int(row['n']):>5}"
                    )
                lines.append("")

    lines += [
        sep,
        "LEGENDE",
        sep,
        "  * p<0.05  ** p<0.01  *** p<0.001",
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
# 6. PIPELINE PRINCIPAL
# ==============================================================================

def run(by_phase: bool = True,
        lags: list = None,
        output_dir: Path = OUTPUT_DIR):

    if lags is None:
        lags = DEFAULT_LAGS

    print()
    print("=" * 70)
    print("  TELECONNEXIONS CLIMATIQUES -- INDICES JOURNALIERS SST OISST v2")
    print("=" * 70)
    print(f"  Analyse par phase : {'Oui' if by_phase else 'Non'}")
    print(f"  Lags (jours)      : {lags}")
    print(f"  Indices           : {len(ALL_INDICES)}")

    viz_dir = output_dir / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)
    viz_dir.mkdir(parents=True, exist_ok=True)

    # ── Chargement ────────────────────────────────────────────────────────────
    print("\n[1/5] Chargement")
    events    = load_events(EVENTS_FILE)
    daily_idx = load_daily_indices(INDICES_FILE)

    sst_start   = daily_idx.index.min()
    events_sst  = events[events["date"] >= sst_start].copy()
    n_excluded  = len(events) - len(events_sst)
    print(f"\n  Evenements utilisables (SST disponible) : {len(events_sst)}"
          f"  (exclus avant {sst_start.date()} : {n_excluded})")

    # ── Configurations de phases ──────────────────────────────────────────────
    if by_phase:
        phase_configs = {
            "Toutes phases": None,
            **{k: k for k in PHASES},
        }
    else:
        phase_configs = {"Toutes phases": None}

    # ── Correlations ──────────────────────────────────────────────────────────
    print("\n[2/5] Calcul des correlations")
    all_corrs = {}

    for phase_key, phase_filter in phase_configs.items():
        label = PHASES.get(phase_key, phase_key)
        print(f"\n  > {label}")

        ev_phase = events_sst.copy()
        if phase_filter:
            ev_phase = ev_phase[ev_phase["phase"] == phase_filter]

        print(f"    {len(ev_phase)} evenements")

        if len(ev_phase) < MIN_OBS:
            all_corrs[phase_key] = pd.DataFrame()
            continue

        corr_df = compute_correlations(ev_phase, daily_idx, lags=lags)
        all_corrs[phase_key] = corr_df

        if not corr_df.empty:
            out_csv = output_dir / f"correlations_{phase_key}.csv"
            corr_df.to_csv(out_csv, index=False)
            print(f"    Sauvegarde : {out_csv.name}")

    # ── Visualisations ────────────────────────────────────────────────────────
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

    # ── Rapport ───────────────────────────────────────────────────────────────
    print("\n[4/5] Rapport")
    generate_report(all_corrs, len(events), len(events_sst), lags, output_dir)

    # ── Resume console ────────────────────────────────────────────────────────
    print("\n[5/5] Resume")
    print()
    print("=" * 78)
    print("  CORRELATIONS PEARSON (lag=0) -- max_precip")
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
        df0 = corr_df[(corr_df["lag_days"] == 0) &
                      (corr_df["metric"] == "max_precip")]
        row_str = f"  {label:<28}"
        for idx in ALL_INDICES:
            sub = df0[df0["index"] == idx]
            if sub.empty:
                row_str += "      n/a"
            else:
                r = sub["pearson_r"].values[0]
                p = sub["pearson_p"].values[0]
                row_str += f" {r:+7.3f}{_sig(p):<1}"
        print(row_str)

    print()
    print("  * p<0.05  ** p<0.01  *** p<0.001")
    print(f"\n  Resultats dans : {output_dir}")
    print("=" * 78)
    print()


# ==============================================================================
# ENTREE DU PROGRAMME
# ==============================================================================

def setup_arguments():
    parser = argparse.ArgumentParser(
        description="Teleconnexions climatiques -- indices journaliers SST OISST v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Indices SST (11) : Nino12, Nino3, Nino34, Nino4, IOD, IOBM,
                   TNA, TSA, ATL3, AMM, AMO
Source SST       : NOAA OISST v2 (0.25deg, journalier, 1983-2023)
Lags par defaut  : 0, 1, 3, 5, 7, 14, 30, 60, 90 jours

Exemples :
  python scripts/04_teleconnections_analysis.py
  python scripts/04_teleconnections_analysis.py --no-by-phase
  python scripts/04_teleconnections_analysis.py --lags 0 7 30 90
  python scripts/04_teleconnections_analysis.py --output-dir outputs/teleconnections
        """
    )
    parser.add_argument(
        "--by-phase", action="store_true", default=True,
        help="Analyser chaque phase de saison separement (defaut: True)"
    )
    parser.add_argument(
        "--no-by-phase", dest="by_phase", action="store_false",
        help="Desactiver l'analyse par phases (analyse globale)"
    )
    parser.add_argument(
        "--lags", type=int, nargs="+", default=DEFAULT_LAGS,
        metavar="N",
        help="Lags en jours (ex: --lags 0 7 30 90)"
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(OUTPUT_DIR),
        help=f"Repertoire de sortie (defaut: {OUTPUT_DIR})"
    )
    # Arguments legacy gardes pour compatibilite (ignores)
    parser.add_argument("--corrected",              action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--max-lag",                type=int,            help=argparse.SUPPRESS)
    parser.add_argument("--use-physical-constraints",action="store_true",help=argparse.SUPPRESS)
    parser.add_argument("--min-observations",       type=int,            help=argparse.SUPPRESS)
    parser.add_argument("--significance-level",     type=float,          help=argparse.SUPPRESS)
    parser.add_argument("--enso-threshold",         type=float,          help=argparse.SUPPRESS)
    parser.add_argument("--skip-visualization",     action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-report",            action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--verbose",                action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-physical-validation",action="store_true",help=argparse.SUPPRESS)
    parser.add_argument("--force-legacy",           action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--events-file",            type=str,            help=argparse.SUPPRESS)
    parser.add_argument("--indices-file",           type=str,            help=argparse.SUPPRESS)
    return parser


if __name__ == "__main__":
    parser = setup_arguments()
    args   = parser.parse_args()
    run(
        by_phase   = args.by_phase,
        lags       = sorted(set(args.lags)),
        output_dir = Path(args.output_dir),
    )
