"""Outil get_teleconnection: correlations SST / pluies extremes."""
import pytest

from jarvis.tools import teleconnections
from jarvis.tools.common import ToolInputError


def lancer(jeu_correlations, **params):
    return teleconnections.run(params, {"correlations": jeu_correlations})


def test_un_indice_sur_tous_les_lags(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine", index="Nino34")
    assert res["n_resultats"] == 6
    lags = [ligne["lag_mois"] for ligne in res["correlations"]]
    # Un seul indice: ordre chronologique, plus lisible qu un classement.
    assert lags == [0, 1, 2, 3, 4, 5]


def test_classement_par_intensite_quand_tous_les_indices(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine")
    forces = [abs(ligne["pearson_r"]) for ligne in res["correlations"]]
    assert forces == sorted(forces, reverse=True)


def test_p_value_citee_est_celle_corrigee_ar1(jeu_correlations):
    """Citer la p-value nominale surestimerait la significativite."""
    res = lancer(jeu_correlations, phase="Phase_2_pleine", index="Nino34", lag=0)
    ligne = res["correlations"][0]
    assert ligne["p_neff"] == pytest.approx(0.004)
    assert ligne["significativite"] == "**"


def test_non_significatif_est_dit_explicitement(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine", index="IOD", lag=0)
    assert res["correlations"][0]["significativite"] == "non significatif"


def test_filtre_significatives_seulement(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine", only_significant=True)
    assert res["n_resultats"] == res["n_significatives"]
    assert all(ligne["p_neff"] < 0.05 for ligne in res["correlations"])


def test_aucune_significative_renvoie_un_message(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine", index="IOD",
                 only_significant=True)
    assert res["correlations"] == []
    assert "Aucune correlation significative" in res["message"]
    assert res["avertissement"]


def test_metrique_par_defaut_est_max_precip(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine")
    assert res["metrique"] == "max_precip"


def test_autre_metrique(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine", metric="n_events")
    assert res["n_resultats"] == 1
    assert res["metrique_label"].startswith("nombre")


def test_avertissement_toujours_present(jeu_correlations):
    """Une correlation livree sans mise en garde serait trompeuse."""
    res = lancer(jeu_correlations, phase="Phase_2_pleine")
    assert "causalite" in res["avertissement"]
    assert "AR1" in res["avertissement"]


def test_phase_obligatoire(jeu_correlations):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_correlations)
    assert "phase est requis" in str(exc.value)


def test_phase_sans_resultats(jeu_correlations):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_correlations, phase="Phase_1_debut")
    assert "disponibles" in str(exc.value)


def test_lag_hors_bornes(jeu_correlations):
    with pytest.raises(ToolInputError):
        lancer(jeu_correlations, phase="Phase_2_pleine", lag=12)


def test_correlation_la_plus_forte(jeu_correlations):
    res = lancer(jeu_correlations, phase="Phase_2_pleine", index="Nino34")
    assert res["correlation_la_plus_forte"]["lag_mois"] == 0
    assert res["correlation_la_plus_forte"]["pearson_r"] == pytest.approx(-0.31)
