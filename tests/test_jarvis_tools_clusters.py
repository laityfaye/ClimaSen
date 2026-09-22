"""Outil get_risk_cluster: regimes oceaniques du K-Means."""
import pytest

from jarvis.tools import clusters
from jarvis.tools.common import ToolInputError


def lancer(jeu_clustering, jeu_events, **params):
    return clusters.run(params, {"clustering": jeu_clustering,
                                 "events": jeu_events})


def test_tous_les_regimes_d_une_phase(jeu_clustering, jeu_events):
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine")
    assert len(res["clusters"]) == 2
    assert res["methode"]["k_retenu"] == 2
    assert res["methode"]["silhouette"] == pytest.approx(0.13)


def test_un_regime_precis(jeu_clustering, jeu_events):
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine", cluster=0)
    assert len(res["clusters"]) == 1
    profil = res["clusters"][0]
    assert profil["cluster"] == 0
    assert profil["n_evenements"] == 2
    assert profil["max_precip_moyen_mm"] == 62.5
    assert profil["annee_moyenne"] == 2005


def test_regions_jointes_par_la_date(jeu_clustering, jeu_events):
    """Les regions viennent du catalogue, jointes sur la date de l evenement."""
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine", cluster=0)
    regions = {r["region"] for r in res["clusters"][0]["regions_principales"]}
    assert regions == {"Kedougou", "Tambacounda"}


def test_regions_desactivables(jeu_clustering, jeu_events):
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine",
                 include_regions=False)
    assert "regions_principales" not in res["clusters"][0]


def test_nature_des_clusters_toujours_rappelee(jeu_clustering, jeu_events):
    """Sans ce rappel, un regime oceanique passerait pour une zone du Senegal."""
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine")
    assert "pas une zone du Senegal" in res["nature"]


def test_cluster_d_une_date(jeu_clustering, jeu_events):
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine",
                 date="2005-07-11")
    assert res["evenement"]["trouve"] is True
    assert res["evenement"]["cluster"] == 0
    assert res["evenement"]["max_precip_mm"] == 80.0


def test_date_sans_evenement_classe(jeu_clustering, jeu_events):
    res = lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine",
                 date="1990-07-01")
    assert res["evenement"]["trouve"] is False
    assert "Aucun evenement" in res["evenement"]["message"]


def test_toutes_phases_pointe_sur_all_phases(jeu_clustering, jeu_events):
    """load_clustering nomme la phase agregee All_phases."""
    res = lancer(jeu_clustering, jeu_events, phase="Toutes phases")
    assert res["phase"] == "Toutes phases"
    assert len(res["clusters"]) == 2


def test_phase_obligatoire(jeu_clustering, jeu_events):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_clustering, jeu_events)
    assert "phase est requis" in str(exc.value)


def test_cluster_inexistant_liste_les_disponibles(jeu_clustering, jeu_events):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_clustering, jeu_events, phase="Phase_2_pleine", cluster=9)
    assert "0, 1" in str(exc.value)


def test_phase_sans_clustering(jeu_clustering, jeu_events):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_clustering, jeu_events, phase="Phase_3_fin")
    assert "disponibles" in str(exc.value)
