#!/usr/bin/env python3
"""Tests de src/analysis/teleconnections.py (TeleconnectionsAnalyzer).

Ce module implemente une seconde approche des teleconnexions, distincte de
scripts/04_teleconnections_analysis.py : travail au pas MENSUEL, lags physiques
par indice (0-12 mois), metriques d intensite (moyenne, p95, p99) en plus de la
frequence, classification ENSO selon les standards ONI, et correction FDR pour
tests multiples.

Priorite des tests : les decisions scientifiques (preprocessing qui preserve le
signal climatique, classification ENSO, seuils d interpretation) plutot que la
mise en forme des messages.

Note d environnement : ce module ecrit des emoji sur stdout et leve donc
UnicodeEncodeError sur une console Windows cp1252. Sous pytest la capture se
fait en UTF-8, les tests passent. Voir le rapport accompagnant ces tests.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from conftest import donnees_synthetiques, paire_correlee  # noqa: E402
from src.analysis.teleconnections import TeleconnectionsAnalyzer  # noqa: E402


# =============================================================================
# Configuration
# =============================================================================

class TestInitialisation:
    def test_valeurs_par_defaut(self):
        a = TeleconnectionsAnalyzer()
        assert a.significance_level == 0.05
        assert a.min_observations == 30
        assert a.multiple_testing_correction is True

    def test_lags_physiques_declares_par_indice(self):
        """Chaque indice a une fenetre de lags justifiee physiquement : ENSO agit
        sur le Sahel via la circulation de Walker (3-6 mois), l Atlantique nord
        est plus proche donc plus rapide (0-2 mois)."""
        a = TeleconnectionsAnalyzer()
        assert a.physical_lags["Nino34"]["optimal"] == [3, 4, 5, 6]
        assert a.physical_lags["IOD"]["optimal"] == [1, 2, 3]
        assert a.physical_lags["TNA"]["optimal"] == [0, 1, 2]
        for config in a.physical_lags.values():
            assert config["min"] <= min(config["optimal"])
            assert max(config["optimal"]) <= config["max"]

    def test_metriques_d_evenement_declarees(self):
        a = TeleconnectionsAnalyzer()
        assert a.event_metrics == ["intensity_mean", "intensity_p95",
                                   "intensity_p99", "frequency"]


# =============================================================================
# Stationnarite
# =============================================================================

class TestStationnarite:
    def test_bruit_blanc_declare_stationnaire(self):
        a = TeleconnectionsAnalyzer()
        serie = pd.Series(np.random.default_rng(1).normal(size=200))
        res = a.test_stationarity(serie, "bruit blanc")
        # Le module renvoie des booleens numpy (np.True_), pas des bool Python :
        # on teste la valeur de verite, pas l identite.
        assert bool(res["is_stationary"])
        assert bool(res["adf_stationary"])

    def test_marche_aleatoire_declaree_non_stationnaire(self):
        a = TeleconnectionsAnalyzer()
        marche = pd.Series(np.cumsum(np.random.default_rng(2).normal(size=200)))
        res = a.test_stationarity(marche, "marche aleatoire")
        assert not bool(res["is_stationary"])

    def test_serie_trop_courte_signale_l_erreur(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        res = a.test_stationarity(pd.Series([1.0, 2.0, 3.0]), "courte")
        assert not bool(res["is_stationary"])
        assert "error" in res
        assert res["n_obs"] == 3

    def test_les_valeurs_manquantes_sont_ecartees(self):
        a = TeleconnectionsAnalyzer()
        serie = pd.Series(np.random.default_rng(3).normal(size=100))
        serie.iloc[::10] = np.nan
        assert a.test_stationarity(serie, "trouee")["n_obs"] == 90

    def test_structure_du_resultat(self):
        a = TeleconnectionsAnalyzer()
        res = a.test_stationarity(
            pd.Series(np.random.default_rng(4).normal(size=150)), "x")
        for cle in ("adf_statistic", "adf_pvalue", "adf_stationary",
                    "kpss_statistic", "kpss_pvalue", "kpss_stationary",
                    "is_stationary", "recommendation"):
            assert cle in res

    def test_stationnarite_exige_les_deux_tests(self):
        """ADF et KPSS ont des hypotheses nulles opposees : la serie n est
        declaree stationnaire que si les deux concordent."""
        a = TeleconnectionsAnalyzer()
        res = a.test_stationarity(
            pd.Series(np.random.default_rng(5).normal(size=200)), "x")
        assert res["is_stationary"] == (res["adf_stationary"] and res["kpss_stationary"])


# =============================================================================
# Recommandation de preprocessing (logique pure)
# =============================================================================

class TestRecommandationPreprocessing:
    @pytest.fixture
    def a(self):
        return TeleconnectionsAnalyzer()

    def test_serie_stationnaire_analysee_directement(self, a):
        reco = a._get_climatological_preprocessing_recommendation(True, True, "Nino34")
        assert "Analyser directement" in reco

    def test_indice_climatique_jamais_differencie(self, a):
        """Decision scientifique centrale : differencier un indice climatique
        detruirait les oscillations basse frequence qu on cherche justement a
        correler. Pour un indice, on detrend, on ne differencie jamais."""
        for nom in ("Nino34", "IOD", "TNA"):
            reco = a._get_climatological_preprocessing_recommendation(False, False, nom)
            assert "Detrend" in reco or "Détrend" in reco
            assert "ifferenciation" not in reco and "ifférenciation" not in reco

    def test_serie_non_climatique_peut_etre_differenciee(self, a):
        reco = a._get_climatological_preprocessing_recommendation(
            False, False, "Precipitation")
        assert "ifférenciation" in reco or "ifferenciation" in reco

    def test_tendance_deterministe_detrend_seulement(self, a):
        reco = a._get_climatological_preprocessing_recommendation(True, False, "X")
        assert "Tendance déterministe" in reco or "Tendance deterministe" in reco

    def test_racine_unitaire_differenciation_par_precaution(self, a):
        reco = a._get_climatological_preprocessing_recommendation(False, True, "X")
        assert "racine unitaire" in reco


# =============================================================================
# Preprocessing
# =============================================================================

class TestPreprocessing:
    def test_un_indice_climatique_n_est_jamais_differencie(self):
        """Garantie la plus importante du module : quoi qu il arrive, la serie
        d un indice ne subit pas de differenciation."""
        a = TeleconnectionsAnalyzer(min_observations=30)
        marche = pd.Series(np.cumsum(np.random.default_rng(6).normal(size=200)),
                           index=pd.date_range("1990-01-01", periods=200, freq="MS"))
        _, meta = a.preprocess_series_climatologically_safe(marche, is_climate_index=True)
        assert "differencing" not in meta["transformations_applied"]

    def test_la_standardisation_est_appliquee(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        serie = pd.Series(np.random.default_rng(7).normal(loc=50, scale=8, size=200),
                          index=pd.date_range("1990-01-01", periods=200, freq="MS"))
        traitee, meta = a.preprocess_series_climatologically_safe(serie)
        assert "standardization" in meta["transformations_applied"]
        assert abs(traitee.mean()) < 1e-9
        assert traitee.std() == pytest.approx(1.0)

    def test_les_parametres_de_standardisation_sont_traces(self):
        """Sans mean et std, impossible de revenir aux unites physiques."""
        a = TeleconnectionsAnalyzer(min_observations=30)
        serie = pd.Series(np.random.default_rng(8).normal(loc=20, scale=3, size=200),
                          index=pd.date_range("1990-01-01", periods=200, freq="MS"))
        _, meta = a.preprocess_series_climatologically_safe(serie)
        params = meta["standardization_params"]
        assert params["mean"] == pytest.approx(serie.mean(), abs=1e-6)
        assert params["std"] > 0

    def test_serie_constante_pas_de_division_par_zero(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        plate = pd.Series([5.0] * 100,
                          index=pd.date_range("1990-01-01", periods=100, freq="MS"))
        traitee, meta = a.preprocess_series_climatologically_safe(plate)
        assert "standardization" not in meta["transformations_applied"]
        assert traitee.notna().all()

    def test_serie_trop_courte_non_standardisee(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        courte = pd.Series(np.arange(10, dtype=float),
                           index=pd.date_range("1990-01-01", periods=10, freq="MS"))
        _, meta = a.preprocess_series_climatologically_safe(courte)
        assert "standardization" not in meta["transformations_applied"]

    def test_longueurs_tracees(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        serie = pd.Series(np.random.default_rng(9).normal(size=150),
                          index=pd.date_range("1990-01-01", periods=150, freq="MS"))
        _, meta = a.preprocess_series_climatologically_safe(serie)
        assert meta["original_length"] == 150
        assert meta["final_length"] > 0


# =============================================================================
# Metriques d evenement
# =============================================================================

class TestMetriquesEvenements:
    def test_erreur_si_evenements_non_charges(self):
        with pytest.raises(ValueError, match="non charg"):
            TeleconnectionsAnalyzer().calculate_event_metrics_climatological()

    def test_frequence_et_intensites_calculees(self, analyseur):
        metrics = analyseur.calculate_event_metrics_climatological()
        assert set(metrics) == {"frequency", "intensity_mean",
                                "intensity_p95", "intensity_p99"}

    def test_la_colonne_d_intensite_est_detectee(self, analyseur):
        """max_precip contient 'precip' : la detection par mot-cle doit la voir."""
        metrics = analyseur.calculate_event_metrics_climatological()
        assert metrics["intensity_mean"].gt(0).any()

    def test_index_mensuel_continu(self, analyseur):
        """Les mois sans evenement doivent exister dans la serie, sinon
        l alignement avec les indices sauterait des pas de temps."""
        freq = analyseur.calculate_event_metrics_climatological()["frequency"]
        ecarts = pd.Series(freq.index).diff().dropna().dt.days
        assert ecarts.between(28, 31).all()

    def test_la_frequence_vaut_zero_hors_saison(self, analyseur):
        """Les evenements synthetiques n existent qu en juillet-septembre."""
        freq = analyseur.calculate_event_metrics_climatological()["frequency"]
        hors_saison = freq[~freq.index.month.isin([7, 8, 9])]
        assert (hors_saison == 0).all()

    def test_l_intensite_est_remplie_a_zero_hors_evenement(self, analyseur):
        """Caracterisation d un choix de modelisation, a connaitre avant
        d interpreter : un mois sans evenement recoit une intensite de 0 mm,
        et non NaN. Ces zeros entrent dans les correlations et diluent le
        signal d intensite. Le script de production, lui, laisse NaN et les
        exclut par dropna()."""
        metrics = analyseur.calculate_event_metrics_climatological()
        hors = metrics["intensity_mean"][
            ~metrics["intensity_mean"].index.month.isin([7, 8, 9])]
        assert (hors == 0).all()
        assert hors.notna().all()

    def test_les_percentiles_sont_ordonnes(self, analyseur):
        m = analyseur.calculate_event_metrics_climatological()
        actifs = m["intensity_mean"] > 0
        assert (m["intensity_p99"][actifs] >= m["intensity_p95"][actifs] - 1e-9).all()


# =============================================================================
# Alignement temporel
# =============================================================================

class TestAlignement:
    @pytest.fixture
    def series(self):
        idx = pd.date_range("1990-01-01", periods=60, freq="MS")
        evenements = pd.Series(np.arange(60, dtype=float), index=idx)
        indice = pd.Series(np.arange(100, 160, dtype=float), index=idx)
        return evenements, indice

    def test_lag_zero_conserve_tout(self, series):
        ev, idx = series
        a, b = TeleconnectionsAnalyzer().align_temporal_data_safe(ev, idx, 0)
        assert len(a) == len(b) == 60

    def test_le_lag_decale_l_indice_vers_le_passe(self, series):
        """Un lag de 3 associe l evenement du mois t a l indice du mois t-3 :
        c est l indice qui PRECEDE l evenement, sens requis pour une
        anticipation."""
        ev, idx = series
        a, b = TeleconnectionsAnalyzer().align_temporal_data_safe(ev, idx, 3)
        premier = a.index[0]
        assert b.loc[premier] == idx.loc[premier - pd.DateOffset(months=3)]

    def test_le_lag_raccourcit_la_serie(self, series):
        ev, idx = series
        a, _ = TeleconnectionsAnalyzer().align_temporal_data_safe(ev, idx, 6)
        assert len(a) == 54

    def test_aucun_recouvrement_donne_des_series_vides(self):
        ev = pd.Series([1.0] * 10, index=pd.date_range("1990-01-01", periods=10, freq="MS"))
        idx = pd.Series([1.0] * 10, index=pd.date_range("2050-01-01", periods=10, freq="MS"))
        a, b = TeleconnectionsAnalyzer().align_temporal_data_safe(ev, idx, 0)
        assert len(a) == 0 and len(b) == 0

    def test_les_paires_incompletes_sont_ecartees(self, series):
        ev, idx = series
        ev = ev.copy()
        ev.iloc[5:10] = np.nan
        a, b = TeleconnectionsAnalyzer().align_temporal_data_safe(ev, idx, 0)
        assert len(a) == len(b) == 55
        assert a.notna().all() and b.notna().all()


# =============================================================================
# Correlation robuste
# =============================================================================

class TestCorrelationRobuste:
    @pytest.fixture
    def a(self):
        return TeleconnectionsAnalyzer(min_observations=30)

    def test_echantillon_insuffisant_refuse(self, a):
        res = a.calculate_correlation_robust(pd.Series([1.0, 2.0, 3.0]),
                                             pd.Series([1.0, 2.0, 3.0]))
        assert res["reliable"] is False
        assert np.isnan(res["correlation"])
        assert "insuffisant" in res["strength"]

    @pytest.mark.parametrize("r_cible,attendu", [
        (0.65, "Très forte"),
        (0.45, "Forte"),
        (0.30, "Modérée"),
        (0.18, "Faible"),
        (0.05, "Très faible"),
    ])
    def test_bandes_d_interpretation(self, a, r_cible, attendu):
        """Seuils 0.6 / 0.4 / 0.25 / 0.15 sur |r|, verifies avec des series
        dont la correlation vaut exactement la valeur voulue."""
        x, y = paire_correlee(r_cible)
        res = a.calculate_correlation_robust(pd.Series(x), pd.Series(y))
        assert res["correlation"] == pytest.approx(r_cible, abs=1e-6)
        assert res["strength"].startswith(attendu)

    def test_les_bandes_ne_dependent_pas_du_signe(self, a):
        x, y = paire_correlee(-0.65)
        assert a.calculate_correlation_robust(
            pd.Series(x), pd.Series(y))["strength"].startswith("Très forte")

    def test_variance_expliquee(self, a):
        x, y = paire_correlee(0.5)
        res = a.calculate_correlation_robust(pd.Series(x), pd.Series(y))
        assert res["variance_explained"] == pytest.approx(25.0, abs=1e-4)

    def test_spearman_disponible(self, a):
        x, y = paire_correlee(0.6)
        res = a.calculate_correlation_robust(pd.Series(x), pd.Series(y), "spearman")
        assert res["method"] == "spearman"
        assert res["correlation"] > 0.5

    def test_methode_inconnue_ne_leve_pas(self, a):
        """L erreur est capturee et retournee, elle n interrompt pas une
        analyse de plusieurs centaines de correlations."""
        res = a.calculate_correlation_robust(pd.Series(np.arange(50.0)),
                                             pd.Series(np.arange(50.0)), "kendall")
        assert np.isnan(res["correlation"])
        assert "error" in res

    def test_seuil_de_significativite_respecte(self, a):
        x, y = paire_correlee(0.05, n=40)
        res = a.calculate_correlation_robust(pd.Series(x), pd.Series(y))
        assert res["is_significant"] == (res["p_value"] < a.significance_level)

    def test_resultat_vide_normalise(self, a):
        vide = a._create_empty_correlation_result(7)
        assert vide["n_obs"] == 7
        assert vide["reliable"] is False
        assert np.isnan(vide["correlation"])


# =============================================================================
# Correction pour tests multiples
# =============================================================================

class TestTestsMultiples:
    @pytest.fixture
    def a(self):
        return TeleconnectionsAnalyzer()

    def test_liste_vide(self, a):
        assert a.apply_multiple_testing_correction([]) == ([], [])

    def test_la_correction_ne_peut_qu_augmenter_les_p_values(self, a):
        brutes = [0.001, 0.01, 0.02, 0.04, 0.3, 0.6]
        _, corrigees = a.apply_multiple_testing_correction(brutes)
        for brute, corrigee in zip(brutes, corrigees):
            assert corrigee >= brute - 1e-12

    def test_fdr_reduit_le_nombre_de_significatifs(self, a):
        """Tester 300 correlations produit des faux positifs par construction :
        sur 300 p-values uniformes, environ 15 passent le seuil de 5 % par
        pur hasard. Le FDR doit les ecarter."""
        rng = np.random.default_rng(11)
        brutes = list(rng.uniform(size=300))
        rejets, _ = a.apply_multiple_testing_correction(brutes)
        avant = sum(p < 0.05 for p in brutes)
        assert avant > 0
        assert sum(rejets) < avant

    def test_bonferroni_plus_severe_que_fdr(self, a):
        brutes = [0.001, 0.008, 0.02, 0.03, 0.045, 0.2]
        fdr, _ = a.apply_multiple_testing_correction(brutes, "fdr_bh")
        bonf, _ = a.apply_multiple_testing_correction(brutes, "bonferroni")
        assert sum(bonf) <= sum(fdr)

    def test_methode_inconnue_retombe_sans_correction(self, a):
        brutes = [0.001, 0.2]
        rejets, corrigees = a.apply_multiple_testing_correction(brutes, "inexistante")
        assert corrigees == brutes
        assert rejets == [True, False]


# =============================================================================
# Classification ENSO
# =============================================================================

class TestClassificationENSO:
    def _analyseur_avec_nino(self, valeurs_par_annee):
        idx = pd.date_range("1990-01-01", "2000-12-01", freq="MS")
        serie = pd.Series(0.0, index=idx)
        for annee, valeur in valeurs_par_annee.items():
            masque = serie.index.year == annee
            serie[masque] = valeur
        a = TeleconnectionsAnalyzer()
        a.climate_indices = pd.DataFrame({"Nino34": serie}, index=idx)
        return a

    def test_sans_nino34_pas_de_classification(self):
        a = TeleconnectionsAnalyzer()
        a.climate_indices = pd.DataFrame(
            {"IOD": [0.1] * 24},
            index=pd.date_range("1990-01-01", periods=24, freq="MS"))
        assert a.identify_enso_events_oni_standard() == {}

    def test_el_nino_detecte(self):
        a = self._analyseur_avec_nino({1994: 2.0, 1995: 2.0})
        res = a.identify_enso_events_oni_standard()
        assert 1995 in res["el_nino"]

    def test_la_nina_detectee(self):
        a = self._analyseur_avec_nino({1994: -2.0, 1995: -2.0})
        res = a.identify_enso_events_oni_standard()
        assert 1995 in res["la_nina"]

    def test_annee_neutre(self):
        a = self._analyseur_avec_nino({})
        res = a.identify_enso_events_oni_standard()
        assert len(res["neutral"]) > 0
        assert res["el_nino"] == [] and res["la_nina"] == []

    def test_une_annee_ne_peut_pas_etre_dans_deux_categories(self):
        a = self._analyseur_avec_nino({1994: 2.0, 1995: 2.0, 1997: -2.0, 1998: -2.0})
        res = a.identify_enso_events_oni_standard()
        toutes = res["el_nino"] + res["la_nina"] + res["neutral"]
        assert len(toutes) == len(set(toutes))

    def test_le_seuil_est_configurable(self):
        a = self._analyseur_avec_nino({1994: 0.7, 1995: 0.7})
        assert 1995 in a.identify_enso_events_oni_standard(threshold=0.5)["el_nino"]
        assert 1995 not in a.identify_enso_events_oni_standard(threshold=1.5)["el_nino"]

    def test_la_methode_est_tracee(self):
        res = self._analyseur_avec_nino({}).identify_enso_events_oni_standard(0.5)
        assert res["threshold"] == 0.5
        assert res["method"] == "ONI_standard_corrected"


# =============================================================================
# Bootstrap
# =============================================================================

class TestBootstrap:
    def test_echantillon_insuffisant(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        res = a.bootstrap_correlation_confidence(pd.Series([1.0, 2.0]),
                                                 pd.Series([1.0, 2.0]), 100)
        assert np.isnan(res["ci_lower"]) and np.isnan(res["ci_upper"])

    def test_l_intervalle_encadre_l_estimation(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        x, y = paire_correlee(0.6, n=150)
        np.random.seed(0)
        res = a.bootstrap_correlation_confidence(pd.Series(x), pd.Series(y),
                                                 n_bootstrap=400)
        assert res["ci_lower"] < 0.6 < res["ci_upper"]

    def test_intervalle_ordonne_et_ecart_type_positif(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        x, y = paire_correlee(0.3, n=150)
        np.random.seed(1)
        res = a.bootstrap_correlation_confidence(pd.Series(x), pd.Series(y), 400)
        assert res["ci_lower"] < res["ci_upper"]
        assert res["bootstrap_std"] > 0
        assert res["n_bootstrap_valid"] >= 100

    def test_un_intervalle_plus_confiant_est_plus_large(self):
        a = TeleconnectionsAnalyzer(min_observations=30)
        x, y = paire_correlee(0.4, n=150)
        np.random.seed(2)
        etroit = a.bootstrap_correlation_confidence(pd.Series(x), pd.Series(y), 500, 0.80)
        np.random.seed(2)
        large = a.bootstrap_correlation_confidence(pd.Series(x), pd.Series(y), 500, 0.99)
        assert (large["ci_upper"] - large["ci_lower"]) > (etroit["ci_upper"] - etroit["ci_lower"])


# =============================================================================
# Chargement de fichiers
# =============================================================================

class TestChargement:
    def test_chargement_nominal(self, tmp_path):
        events, _ = donnees_synthetiques()
        chemin = tmp_path / "events.csv"
        events.to_csv(chemin, index=False)

        a = TeleconnectionsAnalyzer()
        df = a.load_extreme_events(str(chemin))
        assert len(df) == len(events)
        assert a.extreme_events is not None
        assert pd.api.types.is_datetime64_any_dtype(df["date"])

    def test_colonnes_obligatoires_manquantes(self, tmp_path):
        """L erreur est avalee et un DataFrame vide retourne. C est le
        comportement actuel : l appelant doit tester le resultat, il ne recevra
        pas d exception."""
        chemin = tmp_path / "incomplet.csv"
        pd.DataFrame({"date": ["1990-01-01"]}).to_csv(chemin, index=False)
        assert TeleconnectionsAnalyzer().load_extreme_events(str(chemin)).empty

    def test_format_non_csv_refuse(self, tmp_path):
        chemin = tmp_path / "donnees.xlsx"
        chemin.write_text("pas un csv", encoding="utf-8")
        assert TeleconnectionsAnalyzer().load_extreme_events(str(chemin)).empty

    def test_fichier_absent(self):
        assert TeleconnectionsAnalyzer().load_extreme_events("/absent.csv").empty

    def test_chargement_des_indices(self, tmp_path):
        _, indices = donnees_synthetiques()
        chemin = tmp_path / "indices.csv"
        indices.to_csv(chemin, index_label="date")

        a = TeleconnectionsAnalyzer()
        df = a.load_climate_indices(str(chemin))
        assert list(df.columns) == ["Nino34", "IOD", "TNA"]
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    def test_les_tests_de_stationnarite_sont_memorises(self, tmp_path):
        _, indices = donnees_synthetiques()
        chemin = tmp_path / "indices.csv"
        indices.to_csv(chemin, index_label="date")

        a = TeleconnectionsAnalyzer()
        a.load_climate_indices(str(chemin))
        assert set(a.stationarity_results) == {"Nino34", "IOD", "TNA"}


# =============================================================================
# Analyse complete
# =============================================================================

class TestAnalyseComplete:
    def test_donnees_non_chargees(self):
        with pytest.raises(ValueError, match="non charg"):
            TeleconnectionsAnalyzer().analyze_teleconnections_with_physical_lags()

    def test_structure_des_resultats(self, analyseur_avec_resultats):
        res = analyseur_avec_resultats.correlations_results
        assert set(res) == {"Nino34", "IOD", "TNA"}
        assert set(res["Nino34"]) == {"frequency", "intensity_mean",
                                      "intensity_p95", "intensity_p99"}
        for cle in res["Nino34"]["frequency"]:
            assert cle.startswith("lag_")

    def test_les_lags_physiques_sont_respectes(self, analyseur_avec_resultats):
        """TNA est declare 0-12 ; avec max_lag=6 on attend 0-6."""
        lags = sorted(int(k.split("_")[1])
                      for k in analyseur_avec_resultats.correlations_results["TNA"]["frequency"])
        assert lags == [0, 1, 2, 3, 4, 5, 6]

    def test_les_lags_optimaux_sont_marques(self, analyseur_avec_resultats):
        freq = analyseur_avec_resultats.correlations_results["Nino34"]["frequency"]
        marques = {int(k.split("_")[1]) for k, v in freq.items()
                   if v["is_physical_optimal"]}
        assert marques == {3, 4, 5, 6}

    def test_chaque_resultat_porte_pearson_et_spearman(self, analyseur_avec_resultats):
        res = analyseur_avec_resultats.correlations_results["IOD"]["frequency"]["lag_1"]
        assert "pearson" in res and "spearman" in res
        assert res["n_months"] > 0

    def test_la_correction_fdr_est_appliquee(self, analyseur_avec_resultats):
        """Apres correction, chaque resultat exploitable porte sa p-value
        corrigee en plus de la p-value brute."""
        trouve = 0
        for metriques in analyseur_avec_resultats.correlations_results.values():
            for lags in metriques.values():
                for res in lags.values():
                    p = res["pearson"]
                    if not np.isnan(p["p_value"]):
                        assert "p_value_corrected" in p
                        assert p["p_value_corrected"] >= p["p_value"] - 1e-12
                        trouve += 1
        assert trouve > 0

    def test_la_correction_ne_cree_jamais_de_significativite(self, analyseur_avec_resultats):
        """Une correlation non significative avant correction ne peut pas le
        devenir apres."""
        for metriques in analyseur_avec_resultats.correlations_results.values():
            for lags in metriques.values():
                for res in lags.values():
                    p = res["pearson"]
                    if p.get("is_significant_corrected"):
                        assert p["is_significant"]

    def test_le_resume_est_generable(self, analyseur_avec_resultats):
        resume = analyseur_avec_resultats.generate_correlation_summary_corrected()
        assert isinstance(resume, dict) and resume

    def test_l_analyse_par_phases(self, analyseur_avec_resultats):
        phases = analyseur_avec_resultats.phase_correlations
        assert isinstance(phases, dict)

    def test_sauvegarde_des_resultats(self, analyseur_avec_resultats, tmp_path):
        analyseur_avec_resultats.save_results_corrected(str(tmp_path))
        produits = list(tmp_path.rglob("*"))
        fichiers = [f for f in produits if f.is_file()]
        assert fichiers, "aucun fichier de resultat ecrit"
        assert all(f.stat().st_size > 0 for f in fichiers)


# =============================================================================
# Validation de bout en bout : le module retrouve-t-il un signal connu ?
# =============================================================================

class TestRecuperationDUnSignalConnu:
    """Test le plus exigeant de la suite.

    On fabrique des donnees ou l intensite des evenements depend de Nino34 avec
    exactement 3 mois de decalage, puis on verifie que l analyse redecouvre ce
    decalage. Tous les autres tests verifient des mecanismes ; celui-ci verifie
    que l ensemble repond a la question scientifique posee.
    """

    def _corr(self, a, indice, metrique, lag):
        return a.correlations_results[indice][metrique]["lag_%d" % lag]["pearson"]["correlation"]

    def test_le_lag_injecte_est_retrouve(self, analyseur_signal_fort):
        from conftest import INDICE_PILOTE, LAG_INJECTE
        lags = analyseur_signal_fort.correlations_results[INDICE_PILOTE]["intensity_mean"]
        meilleur = max(
            (int(k.split("_")[1]) for k in lags),
            key=lambda lag: abs(self._corr(analyseur_signal_fort, INDICE_PILOTE,
                                           "intensity_mean", lag)),
        )
        assert meilleur == LAG_INJECTE

    def test_la_correlation_au_bon_lag_est_tres_forte(self, analyseur_signal_fort):
        from conftest import INDICE_PILOTE, LAG_INJECTE
        r = self._corr(analyseur_signal_fort, INDICE_PILOTE, "intensity_mean", LAG_INJECTE)
        assert r > 0.9

    def test_le_signe_du_lien_est_respecte(self, analyseur_signal_fort):
        """L intensite a ete construite croissante avec Nino34 : la correlation
        doit etre positive, pas seulement forte."""
        from conftest import INDICE_PILOTE, LAG_INJECTE
        assert self._corr(analyseur_signal_fort, INDICE_PILOTE,
                          "intensity_mean", LAG_INJECTE) > 0

    def test_les_indices_sans_lien_ne_ressortent_pas(self, analyseur_signal_fort):
        """IOD et TNA sont du bruit pur dans ce jeu : aucune de leurs
        correlations ne doit survivre a la correction FDR. Un faux positif ici
        signalerait une correction defaillante."""
        for indice in ("IOD", "TNA"):
            for lags in analyseur_signal_fort.correlations_results[indice].values():
                for res in lags.values():
                    assert not res["pearson"].get("is_significant_corrected", False), (
                        "%s ressort significatif alors qu il est du bruit" % indice)

    def test_le_lien_est_detecte_sur_toutes_les_metriques(self, analyseur_signal_fort):
        from conftest import INDICE_PILOTE, LAG_INJECTE
        for metrique in ("frequency", "intensity_mean", "intensity_p95", "intensity_p99"):
            r = self._corr(analyseur_signal_fort, INDICE_PILOTE, metrique, LAG_INJECTE)
            assert abs(r) > 0.8, "%s : r=%.3f" % (metrique, r)

    def test_le_lag_trouve_est_dans_la_fenetre_physique(self, analyseur_signal_fort):
        """Nino34 declare 3-6 mois comme physiquement optimaux : le lag retrouve
        doit y figurer, ce qui valide la coherence entre la contrainte physique
        declaree et le signal effectivement detecte."""
        from conftest import INDICE_PILOTE, LAG_INJECTE
        assert analyseur_signal_fort.correlations_results[INDICE_PILOTE][
            "intensity_mean"]["lag_%d" % LAG_INJECTE]["is_physical_optimal"]
