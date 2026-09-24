"""Outil analyze_extreme_events: tendance, periodes, saisonnalite, regions."""
import pandas as pd
import pytest

from jarvis.tools import analyse_evenements as outil
from jarvis.tools.common import ToolInputError


def _catalogue(evenements_par_an, debut=1981, region="Tambacounda",
               phase="Phase_2_pleine", mois=8, precip=40.0):
    lignes = []
    for k, n in enumerate(evenements_par_an):
        annee = debut + k
        for j in range(n):
            lignes.append({"date": pd.Timestamp(annee, mois, 1 + j),
                           "year": annee, "month": mois, "phase": phase,
                           "max_precip": precip + j, "mean_precip": 20.0,
                           "coverage_percent": 10.0, "max_anomaly": 3.0,
                           "centroid_region": region})
    return pd.DataFrame(lignes)


@pytest.fixture
def croissant():
    """1981-2020: 1 evenement par an au debut, 5 a la fin."""
    comptes = [1 + k // 10 for k in range(40)]
    return {"events": _catalogue(comptes)}


# --- tendance ---------------------------------------------------------------------
def test_tendance_a_la_hausse_detectee(croissant):
    res = outil.run({"analysis": "tendance"}, croissant)
    assert res["metrique"] == "n_events"
    assert res["n_annees"] == 40
    # Escalier d'une marche par decennie: la pente de Sen en est proche,
    # sans y etre egale (0.909 ici).
    assert res["pente_sen_par_decennie"] == pytest.approx(1.0, abs=0.15)
    assert res["p_mann_kendall"] < 0.001
    assert res["verdict"] == "tendance a la hausse significative"
    assert res["moyenne_premiere_moitie"]["valeur"] < res["moyenne_seconde_moitie"]["valeur"]


def test_les_annees_sans_evenement_comptent_pour_zero():
    """Un simple groupby ferait disparaitre les annees calmes."""
    comptes = [3] * 5 + [0] * 5 + [3] * 10
    res = outil.run({"analysis": "tendance"}, {"events": _catalogue(comptes)})
    serie = dict((a, v) for a, v in res["serie_annuelle"])
    assert res["n_annees"] == 20
    assert serie[1986] == 0
    assert res["moyenne_premiere_moitie"]["valeur"] == 1.5


def test_zeros_comptes_meme_quand_le_filtre_vide_le_debut():
    df = pd.concat([_catalogue([2] * 20, region="Matam"),
                    _catalogue([0] * 10 + [1] * 10, region="Kolda")])
    res = outil.run({"analysis": "tendance", "region": "kolda"}, {"events": df})
    assert res["filtres"]["annees"] == [1981, 2000]
    assert res["n_annees"] == 20


def test_serie_constante_sans_tendance():
    res = outil.run({"analysis": "tendance"}, {"events": _catalogue([2] * 20)})
    assert res["verdict"] == "aucune variation"
    assert res["pente_sen_par_decennie"] == 0


def test_tendance_d_intensite(croissant):
    res = outil.run({"analysis": "tendance", "metric": "max_precip"}, croissant)
    assert res["metrique"] == "max_precip"
    assert res["serie_annuelle"][0] == [1981, 40.0]


def test_tendance_refusee_sur_trop_peu_d_annees(croissant):
    res = outil.run({"analysis": "tendance", "year_min": 1981,
                     "year_max": 1985}, croissant)
    assert "Trop peu" in res["message"]


def test_bornes_inversees(croissant):
    with pytest.raises(ToolInputError, match="year_min"):
        outil.run({"analysis": "tendance", "year_min": 2000,
                   "year_max": 1990}, croissant)


# --- comparer_periodes -------------------------------------------------------------
def test_comparer_periodes_par_defaut_en_deux_moities(croissant):
    res = outil.run({"analysis": "comparer_periodes"}, croissant)
    assert res["periode_1"]["annees"] == [1981, 2000]
    assert res["periode_2"]["annees"] == [2001, 2020]
    assert res["periode_2"]["evenements_par_an"] > res["periode_1"]["evenements_par_an"]
    assert res["difference_significative"] is True


def test_meme_coupure_que_la_tendance(croissant):
    t = outil.run({"analysis": "tendance"}, croissant)
    c = outil.run({"analysis": "comparer_periodes"}, croissant)
    assert t["moyenne_premiere_moitie"]["annees"] == c["periode_1"]["annees"]


def test_comparer_periodes_explicites(croissant):
    res = outil.run({"analysis": "comparer_periodes",
                     "period_1": [1981, 1990], "period_2": [2011, 2020]},
                    croissant)
    assert res["periode_1"]["n_evenements"] == 10
    assert res["periode_2"]["n_evenements"] == 40


@pytest.mark.parametrize("periode", [[1990], "1990-2000", [2000, 1990], ["a", "b"]])
def test_periode_invalide(croissant, periode):
    with pytest.raises(ToolInputError):
        outil.run({"analysis": "comparer_periodes", "period_1": periode}, croissant)


def test_intensite_comparee_evenement_par_evenement(croissant):
    res = outil.run({"analysis": "comparer_periodes", "metric": "max_precip"},
                    croissant)
    assert "par evenement" in res["grandeur_testee"]


# --- saisonnalite et regions -----------------------------------------------------
@pytest.fixture
def varie():
    return {"events": pd.concat([
        _catalogue([3] * 10, region="Tambacounda", phase="Phase_2_pleine", mois=8),
        _catalogue([1] * 10, region="Kolda", phase="Phase_3_fin", mois=9,
                   precip=80.0),
        _catalogue([1] * 10, region="Tambacounda", phase="Phase_1_debut", mois=6),
    ])}


def test_saisonnalite(varie):
    res = outil.run({"analysis": "saisonnalite"}, varie)
    assert res["n_evenements"] == 50
    assert res["mois_le_plus_actif"] == "aout"
    parts = {p["phase"]: p["part_pct"] for p in res["par_phase"]}
    assert parts == {"Phase_1_debut": 20.0, "Phase_2_pleine": 60.0,
                     "Phase_3_fin": 20.0}


def test_regions(varie):
    res = outil.run({"analysis": "regions"}, varie)
    assert [r["region"] for r in res["regions"]] == ["Tambacounda", "Kolda"]
    tamba = res["regions"][0]
    assert tamba["n_evenements"] == 40
    assert tamba["phase_dominante"] == "pleine saison (juillet-aout)"
    assert res["regions"][1]["max_precip_moyen_mm"] == 80.0


def test_filtre_par_phase(varie):
    res = outil.run({"analysis": "regions", "phase": "fin"}, varie)
    assert [r["region"] for r in res["regions"]] == ["Kolda"]


def test_analyse_requise(varie):
    with pytest.raises(ToolInputError, match="analysis est requis"):
        outil.run({}, varie)


def test_resultat_serialisable(croissant):
    import json
    for analyse in outil.ANALYSES:
        json.dumps(outil.run({"analysis": analyse}, croissant))
