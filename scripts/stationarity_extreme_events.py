"""
Tests de stationnarité (ADF + KPSS) sur les séries temporelles
dérivées des événements extrêmes de précipitation au Sénégal.

Séries testées :
  - Fréquence annuelle (nombre d'événements/an)
  - Intensité moyenne annuelle (max_precip moyen/an)
  - Intensité P95 annuelle (percentile 95 de max_precip/an)
  - Intensité P99 annuelle (percentile 99 de max_precip/an)

Pour chaque série : test global + par phase de la saison des pluies.
"""

import sys
import io
import json
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*p-value is smaller.*")
warnings.filterwarnings("ignore", message=".*p-value is greater.*")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = PROJECT_ROOT / "outputs" / "exports" / "extreme_events_comprehensive.csv"
OUTPUT_JSON = PROJECT_ROOT / "outputs" / "reports" / "stationarity_extreme_events.json"


def run_adf_kpss(series: np.ndarray, name: str) -> dict:
    """Exécute ADF et KPSS sur une série et retourne un dict de résultats."""
    clean = series[~np.isnan(series)]
    n = len(clean)
    if n < 10:
        return {
            "series_name": name,
            "n_obs": n,
            "error": "Série trop courte (< 10 observations)"
        }

    # ADF
    maxlag = min(12, n // 3 - 1)
    adf_stat, adf_p, *_ = adfuller(clean, autolag='AIC', maxlag=max(1, maxlag))
    adf_stationary = adf_p < 0.05

    # KPSS
    kpss_stat, kpss_p, *_ = kpss(clean, regression='c', nlags='auto')
    kpss_stationary = kpss_p > 0.05

    # Verdict combiné
    if adf_stationary and kpss_stationary:
        verdict = "Stationnaire"
        recommendation = "Série stationnaire — analyser directement"
    elif not adf_stationary and not kpss_stationary:
        verdict = "Non stationnaire (racine unitaire)"
        recommendation = "Différenciation d'ordre 1 recommandée"
    elif adf_stationary and not kpss_stationary:
        verdict = "Tendance déterministe"
        recommendation = "Détrend linéaire recommandé"
    else:
        verdict = "Ambiguë"
        recommendation = "Investigation supplémentaire nécessaire"

    return {
        "series_name": name,
        "n_obs": int(n),
        "adf_statistic": round(float(adf_stat), 4),
        "adf_pvalue": float(f"{adf_p:.6e}"),
        "adf_stationary": adf_stationary,
        "kpss_statistic": round(float(kpss_stat), 4),
        "kpss_pvalue": round(float(kpss_p), 4),
        "kpss_stationary": kpss_stationary,
        "verdict": verdict,
        "recommendation": recommendation,
    }


def build_annual_series(df: pd.DataFrame, phase_filter: str = None) -> dict:
    """Construit les 4 séries annuelles à partir du DataFrame d'événements."""
    sub = df if phase_filter is None else df[df["phase"] == phase_filter]

    freq = sub.groupby("year").size()
    intensity_mean = sub.groupby("year")["max_precip"].mean()
    intensity_p95 = sub.groupby("year")["max_precip"].quantile(0.95)
    intensity_p99 = sub.groupby("year")["max_precip"].quantile(0.99)

    # Re-indexer sur toutes les années pour avoir des 0 si pas d'événements
    all_years = range(df["year"].min(), df["year"].max() + 1)
    freq = freq.reindex(all_years, fill_value=0)

    return {
        "Fréquence annuelle": freq.values.astype(float),
        "Intensité moyenne (max_precip)": intensity_mean.values,
        "Intensité P95 (max_precip)": intensity_p95.values,
        "Intensité P99 (max_precip)": intensity_p99.values,
    }


def main():
    print("=" * 70)
    print("TESTS DE STATIONNARITÉ — SÉRIES D'ÉVÉNEMENTS EXTRÊMES")
    print("=" * 70)

    df = pd.read_csv(INPUT_CSV)
    print(f"\nDonnées chargées : {len(df)} événements, {df['year'].nunique()} années")
    print(f"Période : {df['year'].min()} – {df['year'].max()}")

    phases = [None, "Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]
    phase_labels = {
        None: "Global",
        "Phase_1_debut": "Phase 1 — Début (mai-juin)",
        "Phase_2_pleine": "Phase 2 — Pleine (juil-août)",
        "Phase_3_fin": "Phase 3 — Fin (sept-oct)",
    }

    all_results = {}

    for phase in phases:
        label = phase_labels[phase]
        key = phase if phase else "Global"
        print(f"\n{'─' * 70}")
        print(f"  {label}")
        print(f"{'─' * 70}")

        series_dict = build_annual_series(df, phase)
        phase_results = {}

        for series_name, values in series_dict.items():
            full_name = f"{series_name} [{label}]"
            result = run_adf_kpss(values, full_name)
            phase_results[series_name] = result

            # Affichage console
            if "error" in result:
                print(f"\n  {series_name}: {result['error']}")
            else:
                adf_ok = "✅" if result["adf_stationary"] else "❌"
                kpss_ok = "✅" if result["kpss_stationary"] else "❌"
                print(f"\n  {series_name} (n={result['n_obs']})")
                print(f"    ADF  : stat={result['adf_statistic']:>8.4f}  p={result['adf_pvalue']:<12}  {adf_ok}")
                print(f"    KPSS : stat={result['kpss_statistic']:>8.4f}  p={result['kpss_pvalue']:<12}  {kpss_ok}")
                print(f"    → {result['verdict']} — {result['recommendation']}")

        all_results[key] = phase_results

    # Tableau récapitulatif
    print(f"\n\n{'=' * 70}")
    print("TABLEAU RÉCAPITULATIF")
    print(f"{'=' * 70}")
    header = f"{'Série':<45} {'ADF stat':>9} {'ADF p':>10} {'ADF':>4} {'KPSS stat':>10} {'KPSS p':>8} {'KPSS':>5}  {'Verdict'}"
    print(header)
    print("─" * len(header))

    for phase_key, phase_results in all_results.items():
        phase_label = phase_labels.get(phase_key, phase_key)
        if phase_key != "Global":
            print(f"\n  [{phase_label}]")
        else:
            print(f"\n  [Global]")
        for series_name, r in phase_results.items():
            if "error" in r:
                print(f"  {series_name:<43} {'N/A':>9} {'N/A':>10} {'—':>4} {'N/A':>10} {'N/A':>8} {'—':>5}  {r['error']}")
            else:
                adf_s = "Oui" if r["adf_stationary"] else "Non"
                kpss_s = "Oui" if r["kpss_stationary"] else "Non"
                print(f"  {series_name:<43} {r['adf_statistic']:>9.4f} {r['adf_pvalue']:>10} {adf_s:>4} {r['kpss_statistic']:>10.4f} {r['kpss_pvalue']:>8.4f} {kpss_s:>5}  {r['verdict']}")

    # Sauvegarde JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n\nRésultats sauvegardés → {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
