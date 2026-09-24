"""Outil analyze_teleconnections: bilan, comparaison de phases, robustesse.

Donnees synthetiques construites pour que chaque verdict soit connu d'avance.
"""
import pandas as pd
import pytest

from jarvis.tools import analyse_teleconnexions as outil
from jarvis.tools.common import INDICES, ToolInputError


def _ligne(indice, lag, r, p_neff, p=None, rs=None, ps_neff=None,
           metric="max_precip"):
    return {"metric": metric, "index": indice, "lag_months": lag,
            "pearson_r": r, "pearson_p": p if p is not None else p_neff,
            "pearson_p_neff": p_neff,
            "spearman_r": rs if rs is not None else r,
            "spearman_p_neff": ps_neff if ps_neff is not None else p_neff,
            "n": 41, "n_eff": 35.0}


def _phase_bruit():
    """66 tests, aucun significatif: tout ce qu'on trouverait par hasard."""
    return pd.DataFrame([_ligne(i, lag, 0.05, 0.6)
                         for i in INDICES for lag in range(6)])


def _phase_signal():
    """AMO fortement lie a tous les lags, plus deux cas pieges."""
    lignes = []
    for i in INDICES:
        for lag in range(6):
            if i == "AMO":
                lignes.append(_ligne(i, lag, -0.45, 0.003))
            elif i == "TNA" and lag == 2:
                # Isole: lags voisins nuls, Spearman ne confirme pas.
                lignes.append(_ligne(i, lag, 0.33, 0.04, rs=0.10, ps_neff=0.5))
            elif i == "IOD" and lag == 0:
                # Significatif seulement avant correction AR1.
                lignes.append(_ligne(i, lag, 0.30, 0.09, p=0.03))
            else:
                lignes.append(_ligne(i, lag, 0.02, 0.8))
    return pd.DataFrame(lignes)


@pytest.fixture
def donnees():
    signal = _phase_signal()
    return {"correlations": {
        "Phase_1_debut": _phase_bruit(),
        "Phase_2_pleine": signal,
        "Phase_3_fin": _phase_bruit(),
        "Toutes phases": signal,
    }}


# --- bilan_significativite ----------------------------------------------------
def test_bilan_compare_au_hasard(donnees):
    res = outil.run({"analysis": "bilan_significativite"}, donnees)
    par_phase = {p["phase"]: p for p in res["phases"]}
    assert set(par_phase) == {"Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"}

    bruit = par_phase["Phase_1_debut"]
    assert bruit["n_tests"] == 66
    assert bruit["n_significatives_ar1"] == 0
    assert bruit["attendues_par_hasard"] == pytest.approx(3.3)
    assert "pas plus" in bruit["verdict"]

    signal = par_phase["Phase_2_pleine"]
    assert signal["n_significatives_ar1"] == 7      # 6 lags AMO + TNA lag 2
    assert signal["n_significatives_nominales"] == 8  # + IOD avant AR1
    assert signal["p_binomiale"] < 0.05
    assert "nettement plus" in signal["verdict"]


def test_bilan_par_bassin(donnees):
    res = outil.run({"analysis": "bilan_significativite",
                     "phase": "pleine"}, donnees)
    assert len(res["phases"]) == 1
    bassins = {b["bassin"]: b for b in res["phases"][0]["par_bassin"]}
    assert bassins["Atlantique"]["n_significatives"] == 7
    assert bassins["Atlantique"]["correlation_la_plus_forte"]["indice"] == "AMO"
    assert bassins["Pacifique (ENSO)"]["n_significatives"] == 0


def test_bilan_rappelle_la_dependance_des_tests(donnees):
    res = outil.run({"analysis": "bilan_significativite"}, donnees)
    assert "pas independants" in res["limite"]
    assert "FDR" in res["avertissement"]


# --- comparer_phases -----------------------------------------------------------
def test_comparer_phases(donnees):
    res = outil.run({"analysis": "comparer_phases", "index": "amo"}, donnees)
    assert res["indice"] == "AMO"
    assert res["bassin"] == "Atlantique"
    par_phase = {p["phase"]: p for p in res["phases"]}
    assert par_phase["Phase_2_pleine"]["n_lags_significatifs"] == 6
    assert par_phase["Phase_2_pleine"]["meilleur_lag"]["pearson_r"] == -0.45
    assert par_phase["Phase_1_debut"]["n_lags_significatifs"] == 0
    assert res["signe_stable_entre_phases_significatives"] is True


def test_comparer_phases_exige_un_indice(donnees):
    with pytest.raises(ToolInputError, match="index est requis"):
        outil.run({"analysis": "comparer_phases"}, donnees)


# --- robustesse -------------------------------------------------------------------
def test_robustesse_distingue_robuste_et_fragile(donnees):
    res = outil.run({"analysis": "robustesse", "phase": "Phase_2_pleine",
                     "limit": 15}, donnees)
    par_cle = {(c["indice"], c["lag_mois"]): c for c in res["correlations"]}

    amo = par_cle[("AMO", 3)]
    assert amo["verdict"] == "robuste"
    assert amo["score_sur_3"] == 3

    tna = par_cle[("TNA", 2)]
    assert tna["criteres"] == {"significative_apres_AR1": True,
                               "confirmee_par_spearman": False,
                               "lags_voisins_coherents": False}
    assert tna["verdict"] == "fragile"

    iod = par_cle[("IOD", 0)]
    assert iod["criteres"]["significative_apres_AR1"] is False
    assert iod["verdict"] == "fragile"
    assert res["significatives_seulement_sans_correction_AR1"] == 1


def test_robustesse_classe_les_robustes_en_tete(donnees):
    res = outil.run({"analysis": "robustesse", "phase": "Phase_2_pleine",
                     "limit": 15}, donnees)
    scores = [c["score_sur_3"] for c in res["correlations"]]
    assert scores == sorted(scores, reverse=True)
    assert res["repartition"] == {"robuste": 6, "moderee": 0, "fragile": 2}


def test_robustesse_filtre_par_indice(donnees):
    res = outil.run({"analysis": "robustesse", "phase": "Phase_2_pleine",
                     "index": "TNA"}, donnees)
    assert {c["indice"] for c in res["correlations"]} == {"TNA"}


def test_robustesse_exige_une_phase(donnees):
    with pytest.raises(ToolInputError, match="phase est requis"):
        outil.run({"analysis": "robustesse"}, donnees)


def test_robustesse_phase_absente(donnees):
    del donnees["correlations"]["Phase_3_fin"]
    with pytest.raises(ToolInputError, match="Aucun resultat"):
        outil.run({"analysis": "robustesse", "phase": "fin"}, donnees)


# --- parametres -------------------------------------------------------------------
def test_analyse_requise(donnees):
    with pytest.raises(ToolInputError, match="analysis est requis"):
        outil.run({}, donnees)


def test_analyse_inconnue(donnees):
    with pytest.raises(ToolInputError, match="Valeurs acceptees"):
        outil.run({"analysis": "prevision"}, donnees)


def test_autre_metrique_sans_resultat(donnees):
    res = outil.run({"analysis": "bilan_significativite",
                     "metric": "n_events"}, donnees)
    assert res["phases"] == []
