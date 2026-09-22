#!/usr/bin/env python3
"""Tests du coeur scientifique des teleconnexions.

Cible : scripts/04_teleconnections_analysis.py, le script qui produit
reellement les correlations publiees (CSV de outputs/teleconnections/, lus
ensuite par le dashboard). Les fonctions testees ici sont pures et
deterministes : detrend, autocorrelation AR1, degres de liberte effectifs
(Chelton 1983), p-values corrigees, agregation annuelle avec lag en mois.

Ce que ces tests protegent : une regression silencieuse sur ces fonctions ne
ferait pas planter le pipeline, elle changerait les chiffres du memoire.

Note : le module s appelle "04_..." et commence par un chiffre, il n est donc
pas importable par `import`. On le charge par son chemin.
"""
import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import pearsonr

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "04_teleconnections_analysis.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("teleconnections_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["teleconnections_script"] = module
    spec.loader.exec_module(module)
    return module


tc = _load_module()


# =============================================================================
# Jeux de donnees synthetiques
# =============================================================================

def make_indices(index_name="Nino34", first_year=1982, last_year=2023):
    """Indices mensuels dont la valeur encode sa propre date : annee*100 + mois.

    Cela permet d affirmer exactement QUELS mois ont ete moyennes par
    merge_annual_lag, au lieu de se contenter d un ordre de grandeur.
    """
    rows = [{"year": y, "month": m, index_name: y * 100 + m}
            for y in range(first_year, last_year + 1)
            for m in range(1, 13)]
    df = pd.DataFrame(rows)
    df["ym_ord"] = df["year"] * 12 + df["month"]
    return df


def make_events(records):
    """records : liste de (annee, mois, n_events, max_precip, mean_precip)."""
    rows = [{"year": y, "month": m, "n_events": n,
             "max_precip": mx, "mean_precip": mn,
             "max_anomaly": 3.0, "coverage_percent": 20.0}
            for (y, m, n, mx, mn) in records]
    df = pd.DataFrame(rows)
    df["ym_ord"] = df["year"] * 12 + df["month"]
    return df


def ar1_series(n, rho, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros(n)
    for i in range(1, n):
        out[i] = rho * out[i - 1] + rng.normal()
    return out


# =============================================================================
# Autocorrelation AR1
# =============================================================================

class TestAR1:
    def test_bruit_blanc_proche_de_zero(self):
        """Serie longue a dessein : sur 400 points l estimateur AR1 a un
        ecart-type d environ 0.05 et un tirage malchanceux depasse 0.15.
        Sur 5000 points il se resserre autour de 0.014."""
        x = np.random.default_rng(1).normal(size=5000)
        assert abs(tc.compute_ar1(x)) < 0.06

    def test_serie_autocorrelee_detectee(self):
        assert tc.compute_ar1(ar1_series(400, 0.85, seed=2)) > 0.7

    def test_autocorrelation_negative_detectee(self):
        alterne = np.array([1.0, -1.0] * 50)
        assert tc.compute_ar1(alterne) < -0.9

    def test_serie_constante_ne_divise_pas_par_zero(self):
        assert tc.compute_ar1(np.ones(50)) == 0.0

    def test_serie_trop_courte(self):
        assert tc.compute_ar1(np.array([1.0, 2.0, 3.0])) == 0.0

    def test_valeur_exacte_sur_un_cas_calculable(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        xc = x - x.mean()
        attendu = float(np.sum(xc[1:] * xc[:-1]) / np.sum(xc ** 2))
        assert tc.compute_ar1(x) == pytest.approx(attendu)


# =============================================================================
# Degres de liberte effectifs (Chelton 1983)
# =============================================================================

class TestNEff:
    def test_series_independantes_conservent_leurs_degres_de_liberte(self):
        rng = np.random.default_rng(3)
        n_eff = tc.compute_n_eff(rng.normal(size=41), rng.normal(size=41))
        assert n_eff >= 35        # proche de n=41

    def test_l_autocorrelation_reduit_fortement_n_eff(self):
        """Le coeur de la correction : 41 annees fortement autocorrelees ne
        valent pas 41 observations independantes."""
        a = ar1_series(41, 0.9, seed=4)
        b = ar1_series(41, 0.9, seed=5)
        assert tc.compute_n_eff(a, b) < 20

    def test_borne_inferieure(self):
        a = ar1_series(41, 0.99, seed=6)
        assert tc.compute_n_eff(a, a) >= 3

    def test_borne_superieure(self):
        """n_eff ne peut jamais depasser n, meme en autocorrelation negative."""
        alterne = np.array([1.0, -1.0] * 20 + [1.0])
        assert tc.compute_n_eff(alterne, alterne) <= 41

    def test_formule_de_chelton(self):
        a = ar1_series(60, 0.7, seed=8)
        b = ar1_series(60, 0.5, seed=9)
        r1a, r1b = tc.compute_ar1(a), tc.compute_ar1(b)
        attendu = int(round(60 * (1 - r1a * r1b) / (1 + r1a * r1b)))
        assert tc.compute_n_eff(a, b) == max(3, min(attendu, 60))


# =============================================================================
# p-values recalculees sur n_eff
# =============================================================================

class TestPValueNEff:
    def test_reproduit_scipy_quand_n_eff_vaut_n(self):
        """Ancrage : sans correction, on doit retomber exactement sur la
        p-value de scipy. Si ce test casse, la formule t-Student a derive."""
        rng = np.random.default_rng(10)
        x = rng.normal(size=41)
        y = 0.6 * x + 0.8 * rng.normal(size=41)
        r, p_scipy = pearsonr(x, y)
        assert tc.p_from_r_neff(r, len(x)) == pytest.approx(p_scipy, abs=1e-12)

    def test_reduire_n_eff_augmente_la_p_value(self):
        """La consequence scientifique de la correction : moins de degres de
        liberte, donc moins de significativite pour le meme r."""
        r = 0.35
        assert tc.p_from_r_neff(r, 41) < tc.p_from_r_neff(r, 20) < tc.p_from_r_neff(r, 10)

    def test_correlation_nulle_donne_p_egal_un(self):
        assert tc.p_from_r_neff(0.0, 41) == pytest.approx(1.0)

    def test_n_eff_degenere(self):
        assert tc.p_from_r_neff(0.9, 2) == 1.0
        assert tc.p_from_r_neff(0.9, 1) == 1.0

    def test_correlation_parfaite_ne_produit_pas_nan(self):
        """r = 1 ferait diviser par zero sans l ecretage de la fonction."""
        for r in (1.0, -1.0):
            p = tc.p_from_r_neff(r, 41)
            assert math.isfinite(p) and p >= 0.0

    def test_correlation_indefinie_n_est_jamais_significative(self):
        """Regression. pearsonr et spearmanr renvoient nan sur une serie
        constante. Avant correction, l ecretage max(-1, min(1, nan)) ramenait
        ce nan a ~1.0 : la p-value tombait a 1e-191 et une correlation
        INEXISTANTE ressortait avec trois etoiles.

        Les 1320 correlations publiees ne contenaient aucun r indefini, donc
        les chiffres du memoire ne sont pas concernes ; le garde-fou evite que
        cela arrive sur un jeu de donnees futur.
        """
        assert tc.p_from_r_neff(float("nan"), 41) == 1.0
        assert tc._sig(tc.p_from_r_neff(float("nan"), 41)) == ""

    def test_une_serie_constante_ne_produit_pas_d_etoiles(self):
        """Le meme defaut, vu depuis le calcul complet."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r, _ = pearsonr(np.zeros(41),
                            np.random.default_rng(0).normal(size=41))
        assert math.isnan(r)
        assert tc._sig(tc.p_from_r_neff(r, tc.compute_n_eff(
            np.zeros(41), np.random.default_rng(0).normal(size=41)))) == ""

    def test_symetrie_du_signe(self):
        assert tc.p_from_r_neff(0.4, 30) == pytest.approx(tc.p_from_r_neff(-0.4, 30))

    def test_cas_complet_autocorrele(self):
        """Bout en bout : deux series AR(0.9) sans lien reel ne doivent pas
        ressortir significatives une fois la correction appliquee."""
        a = ar1_series(41, 0.9, seed=11)
        b = ar1_series(41, 0.9, seed=12)
        r, _ = pearsonr(a, b)
        n_eff = tc.compute_n_eff(a, b)
        assert n_eff < 41
        assert tc.p_from_r_neff(r, n_eff) > tc.p_from_r_neff(r, 41)


# =============================================================================
# Seuils de significativite
# =============================================================================

class TestSeuils:
    @pytest.mark.parametrize("p,attendu", [
        (0.0001, "***"), (0.0009, "***"),
        (0.001, "**"), (0.005, "**"), (0.009, "**"),
        (0.01, "*"), (0.03, "*"), (0.049, "*"),
        (0.05, ""), (0.2, ""), (1.0, ""),
    ])
    def test_seuils_stricts(self, p, attendu):
        """Comparaisons strictes : p = 0.05 n est PAS significatif."""
        assert tc._sig(p) == attendu


# =============================================================================
# Detrend lineaire
# =============================================================================

class TestDetrend:
    def test_une_droite_parfaite_devient_nulle(self):
        residus = tc.apply_detrend(np.arange(41, dtype=float) * 3.5 + 10.0)
        assert np.abs(residus).max() < 1e-9

    def test_le_signal_rapide_survit_au_detrend(self):
        """Une oscillation rapide est quasi orthogonale a la droite de
        tendance : le detrend la laisse intacte."""
        t = np.arange(41, dtype=float)
        signal = np.sin(2 * np.pi * t / 5.0)        # 8 cycles sur la fenetre
        residus = tc.apply_detrend(2.0 * t + 100.0 + signal)
        assert np.corrcoef(residus, signal)[0, 1] > 0.99

    def test_une_oscillation_lente_est_partiellement_absorbee(self):
        """Mise en garde methodologique, pas un defaut : sur 41 ans, un signal
        de periode comparable a la fenetre est en partie confondu avec la
        tendance et le detrend en retire une fraction. Cela concerne les
        indices a variabilite lente (AMO notamment) : leur correlation apres
        detrend est une borne basse."""
        t = np.arange(41, dtype=float)
        lent = np.sin(2 * np.pi * t / 40.0)         # un seul cycle
        residus = tc.apply_detrend(2.0 * t + 100.0 + lent)
        r = np.corrcoef(residus, lent)[0, 1]
        assert r < 0.999

    def test_serie_trop_courte_inchangee(self):
        court = np.array([5.0, 9.0])
        assert np.array_equal(tc.apply_detrend(court), court)

    def test_colonne_absente_ignoree(self):
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
        assert tc.detrend_columns(df, ["inexistante"]).equals(df)

    def test_le_dataframe_source_n_est_pas_modifie(self):
        df = pd.DataFrame({"a": np.arange(10, dtype=float)})
        avant = df["a"].copy()
        tc.detrend_columns(df, ["a"])
        assert df["a"].equals(avant)

    def test_les_nan_restent_a_leur_place(self):
        df = pd.DataFrame({"a": [1.0, 2.0, np.nan, 4.0, 5.0, 6.0]})
        out = tc.detrend_columns(df, ["a"])
        assert out["a"].isna().tolist() == [False, False, True, False, False, False]
        assert abs(out["a"].dropna().sum()) < 1e-9

    def test_colonne_entiere_convertie_sans_erreur(self):
        df = pd.DataFrame({"n": [1, 2, 3, 4, 5]})
        out = tc.detrend_columns(df, ["n"])
        assert np.abs(out["n"].values).max() < 1e-9

    def test_moins_de_trois_valeurs_valides_non_detrendee(self):
        df = pd.DataFrame({"a": [1.0, 2.0, np.nan, np.nan]})
        out = tc.detrend_columns(df, ["a"])
        assert out["a"].dropna().tolist() == [1.0, 2.0]


# =============================================================================
# Agregation annuelle et decalage en mois
# =============================================================================

class TestMergeAnnualLag:
    def test_lag_zero_moyenne_les_mois_de_la_phase(self):
        merged = tc.merge_annual_lag(
            make_events([(2000, 7, 1, 50.0, 10.0)]), make_indices(),
            phase_months=[7, 8], lag_months=0, idx_cols=["Nino34"])
        ligne = merged[merged["year"] == 2000].iloc[0]
        # Valeurs encodees : 2000*100+7 et 2000*100+8 -> moyenne 200007.5
        assert ligne["Nino34"] == pytest.approx(200007.5)

    def test_lag_de_trois_mois_recule_bien_de_trois_mois(self):
        merged = tc.merge_annual_lag(
            make_events([(2000, 7, 1, 50.0, 10.0)]), make_indices(),
            phase_months=[7, 8], lag_months=3, idx_cols=["Nino34"])
        ligne = merged[merged["year"] == 2000].iloc[0]
        # Jul-3=Avr, Aou-3=Mai -> moyenne de 200004 et 200005
        assert ligne["Nino34"] == pytest.approx(200004.5)

    def test_le_lag_bascule_sur_l_annee_precedente(self):
        """Cas limite le plus fragile : phase Mai-Juin avec un lag de 6 mois
        pointe sur Novembre-Decembre de l ANNEE PRECEDENTE."""
        merged = tc.merge_annual_lag(
            make_events([(2000, 5, 1, 50.0, 10.0)]), make_indices(),
            phase_months=[5, 6], lag_months=6, idx_cols=["Nino34"])
        ligne = merged[merged["year"] == 2000].iloc[0]
        # Mai-6 = Nov(1999), Jun-6 = Dec(1999) -> moyenne de 199911 et 199912
        assert ligne["Nino34"] == pytest.approx(199911.5)

    def test_agregation_des_metriques_sur_les_mois_de_la_phase(self):
        merged = tc.merge_annual_lag(
            make_events([(2000, 7, 2, 50.0, 10.0),
                         (2000, 8, 3, 80.0, 20.0)]),
            make_indices(), phase_months=[7, 8], lag_months=0,
            idx_cols=["Nino34"])
        ligne = merged[merged["year"] == 2000].iloc[0]
        assert ligne["n_events"] == 5           # somme
        assert ligne["max_precip"] == 80.0      # maximum
        assert ligne["mean_precip"] == 15.0     # moyenne

    def test_les_mois_hors_phase_sont_ignores(self):
        merged = tc.merge_annual_lag(
            make_events([(2000, 7, 2, 50.0, 10.0),
                         (2000, 9, 9, 999.0, 999.0)]),   # septembre, hors phase
            make_indices(), phase_months=[7, 8], lag_months=0,
            idx_cols=["Nino34"])
        ligne = merged[merged["year"] == 2000].iloc[0]
        assert ligne["n_events"] == 2
        assert ligne["max_precip"] == 50.0

    def test_toutes_les_annees_sont_presentes(self):
        merged = tc.merge_annual_lag(
            make_events([(2000, 7, 1, 50.0, 10.0)]), make_indices(),
            phase_months=[7, 8], lag_months=0, idx_cols=["Nino34"])
        assert merged["year"].tolist() == list(range(1983, 2024))

    def test_annee_sans_evenement(self):
        """n_events = 0 (comptage), intensites NaN (rien a mesurer)."""
        merged = tc.merge_annual_lag(
            make_events([(2000, 7, 1, 50.0, 10.0)]), make_indices(),
            phase_months=[7, 8], lag_months=0, idx_cols=["Nino34"])
        vide = merged[merged["year"] == 1995].iloc[0]
        assert vide["n_events"] == 0
        assert pd.isna(vide["max_precip"])


# =============================================================================
# Calcul complet des correlations
# =============================================================================

def events_lineaires_plus_signal():
    """Evenements dont l intensite = tendance + sinusoide, sur 1983-2023."""
    records = []
    for i, year in enumerate(range(1983, 2024)):
        signal = math.sin(i / 3.0) * 10.0
        records.append((year, 7, max(1, int(round(i / 4 + signal / 5 + 10))),
                        2.0 * i + 50.0 + signal, 10.0))
    return make_events(records)


def indices_lineaires_plus_signal():
    rows = []
    for y in range(1982, 2024):
        for m in range(1, 13):
            i = y - 1983
            rows.append({"year": y, "month": m,
                         "Nino34": 5.0 * i + math.sin(i / 3.0) * 10.0})
    df = pd.DataFrame(rows)
    df["ym_ord"] = df["year"] * 12 + df["month"]
    return df


class TestComputeCorrelations:
    def test_colonnes_de_sortie(self):
        df = tc.compute_correlations(events_lineaires_plus_signal(),
                                     indices_lineaires_plus_signal(),
                                     phase_months=[7, 8], lags=[0])
        for col in ("metric", "index", "lag_months", "pearson_r", "pearson_p",
                    "pearson_p_neff", "spearman_r", "spearman_p_neff",
                    "n", "n_eff", "sig_pearson", "sig_pearson_nom"):
            assert col in df.columns

    def test_les_etoiles_viennent_de_p_neff_pas_de_p_nominale(self):
        """Decision methodologique du memoire : la significativite affichee est
        celle corrigee de l autocorrelation."""
        df = tc.compute_correlations(events_lineaires_plus_signal(),
                                     indices_lineaires_plus_signal(),
                                     phase_months=[7, 8], lags=[0])
        assert not df.empty
        for _, row in df.iterrows():
            assert row["sig_pearson"] == tc._sig(row["pearson_p_neff"])
            assert row["sig_pearson_nom"] == tc._sig(row["pearson_p"])

    def test_n_eff_jamais_superieur_a_n(self):
        df = tc.compute_correlations(events_lineaires_plus_signal(),
                                     indices_lineaires_plus_signal(),
                                     phase_months=[7, 8], lags=[0])
        assert (df["n_eff"] <= df["n"]).all()
        assert (df["n_eff"] >= 3).all()

    def test_les_lags_demandes_sont_tous_calcules(self):
        df = tc.compute_correlations(events_lineaires_plus_signal(),
                                     indices_lineaires_plus_signal(),
                                     phase_months=[7, 8], lags=[0, 2, 5])
        assert sorted(df["lag_months"].unique()) == [0, 2, 5]

    def test_les_intensites_sont_detrendees_mais_pas_les_comptages(self):
        """max_precip est detrendee, n_events ne l est pas (comptage entier).

        Consequence observable : face a un indice detrende reduit a sa
        sinusoide, max_precip correle quasi parfaitement, tandis que n_events
        garde sa tendance et correle moins bien.
        """
        df = tc.compute_correlations(events_lineaires_plus_signal(),
                                     indices_lineaires_plus_signal(),
                                     phase_months=[7, 8], lags=[0])
        r_intensite = abs(df[(df["metric"] == "max_precip")
                             & (df["index"] == "Nino34")]["pearson_r"].iloc[0])
        r_comptage = abs(df[(df["metric"] == "n_events")
                            & (df["index"] == "Nino34")]["pearson_r"].iloc[0])
        assert r_intensite > 0.99
        assert r_comptage < r_intensite

    def test_min_obs_ecarte_les_intensites_mais_pas_les_comptages(self):
        """Quatre annees seulement comportent des evenements.

        Les metriques d intensite n existent que ces annees-la : 4 points,
        sous MIN_OBS=10, elles sont ecartees. n_events, lui, est defini pour
        les 41 annees (zero quand il ne s est rien passe) et reste calcule.
        C est voulu : l analyse de FREQUENCE a besoin des annees a zero,
        l analyse d INTENSITE n a rien a mesurer ces annees-la."""
        maigre = make_events([(1990 + i, 7, 1, 50.0 + i, 10.0) for i in range(4)])
        df = tc.compute_correlations(maigre, make_indices(),
                                     phase_months=[7, 8], lags=[0])
        metriques = set(df["metric"].unique())
        assert metriques == {"n_events"}
        assert df["n"].iloc[0] == 41

    def test_schema_preserve_quand_aucun_indice_connu(self):
        """Meme sans une seule correlation calculable, le DataFrame garde ses
        colonnes : le code aval (export CSV, graphiques) ne doit pas planter."""
        inconnus = make_indices(index_name="IndiceQuiNExistePas")
        df = tc.compute_correlations(make_events([(1990, 7, 1, 50.0, 10.0)]),
                                     inconnus, phase_months=[7, 8], lags=[0])
        assert df.empty
        assert "sig_pearson" in df.columns
        assert "sig_spearman" in df.columns


# =============================================================================
# Chargement des donnees
# =============================================================================

class TestChargement:
    def test_agregation_mensuelle_des_evenements(self, tmp_path):
        csv = tmp_path / "events.csv"
        pd.DataFrame([
            {"date": "1990-07-05", "max_precip": 40.0, "mean_precip": 10.0,
             "max_anomaly": 3.0, "coverage_percent": 20.0},
            {"date": "1990-07-20", "max_precip": 60.0, "mean_precip": 20.0,
             "max_anomaly": 5.0, "coverage_percent": 30.0},
        ]).to_csv(csv, index=False)

        out = tc.load_events_monthly(csv)
        juillet = out[(out["year"] == 1990) & (out["month"] == 7)].iloc[0]
        assert juillet["n_events"] == 2
        assert juillet["max_precip"] == 60.0      # maximum
        assert juillet["mean_precip"] == 15.0     # moyenne
        assert juillet["max_anomaly"] == 4.0      # moyenne

    def test_les_evenements_anterieurs_a_1983_sont_exclus(self, tmp_path):
        """Les indices SST commencent en 1983 : correler au-dela serait
        correler avec du vide."""
        csv = tmp_path / "events.csv"
        pd.DataFrame([
            {"date": "1981-07-05", "max_precip": 40.0, "mean_precip": 10.0,
             "max_anomaly": 3.0, "coverage_percent": 20.0},
            {"date": "1990-07-05", "max_precip": 40.0, "mean_precip": 10.0,
             "max_anomaly": 3.0, "coverage_percent": 20.0},
        ]).to_csv(csv, index=False)

        out = tc.load_events_monthly(csv)
        assert out["year"].min() == 1983
        assert out["n_events"].sum() == 1

    def test_calendrier_complet_des_mois_de_saison(self, tmp_path):
        """Les mois sans evenement doivent exister a zero, sinon l analyse de
        frequence ne verrait que les mois ou il s est passe quelque chose."""
        csv = tmp_path / "events.csv"
        pd.DataFrame([
            {"date": "1990-07-05", "max_precip": 40.0, "mean_precip": 10.0,
             "max_anomaly": 3.0, "coverage_percent": 20.0},
        ]).to_csv(csv, index=False)

        out = tc.load_events_monthly(csv)
        assert sorted(out["month"].unique()) == [5, 6, 7, 8, 9, 10]
        assert len(out) == 41 * 6                       # 1983-2023 x 6 mois
        assert (out["n_events"] == 0).sum() == 41 * 6 - 1
        vide = out[(out["year"] == 1990) & (out["month"] == 8)].iloc[0]
        assert vide["n_events"] == 0
        assert pd.isna(vide["max_precip"])

    def test_moyenne_mensuelle_des_indices(self, tmp_path):
        csv = tmp_path / "indices.csv"
        pd.DataFrame([
            {"date": "1990-07-01", "Nino34": 1.0, "TSA": -1.0},
            {"date": "1990-07-02", "Nino34": 3.0, "TSA": 1.0},
            {"date": "1990-08-01", "Nino34": 10.0, "TSA": 0.0},
        ]).to_csv(csv, index=False)

        out = tc.load_indices_monthly(csv)
        juillet = out[(out["year"] == 1990) & (out["month"] == 7)].iloc[0]
        assert juillet["Nino34"] == 2.0
        assert juillet["TSA"] == 0.0
        assert len(out) == 2

    def test_les_colonnes_hors_liste_sont_ignorees(self, tmp_path):
        csv = tmp_path / "indices.csv"
        pd.DataFrame([
            {"date": "1990-07-01", "Nino34": 1.0, "IndiceInconnu": 99.0},
        ]).to_csv(csv, index=False)

        out = tc.load_indices_monthly(csv)
        assert "Nino34" in out.columns
        assert "IndiceInconnu" not in out.columns


# =============================================================================
# Coherence de la configuration
# =============================================================================

class TestConfiguration:
    def test_les_trois_phases_couvrent_mai_a_octobre(self):
        mois = sorted(m for months in tc.PHASE_MONTHS.values() for m in months)
        assert mois == [5, 6, 7, 8, 9, 10]

    def test_chaque_phase_a_un_libelle(self):
        assert set(tc.PHASE_MONTHS) == set(tc.PHASES)

    def test_les_lags_vont_de_zero_a_cinq_mois(self):
        assert tc.DEFAULT_LAGS == [0, 1, 2, 3, 4, 5]

    def test_les_onze_indices_sst(self):
        assert len(tc.ALL_INDICES) == 11
        for famille in ("Nino34", "IOD", "TSA", "ATL3", "AMM", "AMO"):
            assert famille in tc.ALL_INDICES

    def test_les_cinq_metriques(self):
        assert set(tc.METRICS) == {"max_precip", "mean_precip", "max_anomaly",
                                   "coverage_percent", "n_events"}
