"""Outil search_extreme_events: catalogue des evenements extremes."""
import pytest

from jarvis.tools import events
from jarvis.tools.common import ToolInputError


def lancer(jeu_events, **params):
    return events.run(params, {"events": jeu_events})


def test_sans_filtre_renvoie_tout_le_catalogue(jeu_events):
    res = lancer(jeu_events)
    assert res["n_total"] == 4
    assert res["n_renvoyes"] == 4
    assert res["evenements"][0]["max_precip_mm"] == 80.0  # tri par intensite


def test_filtre_par_annee_et_phase(jeu_events):
    res = lancer(jeu_events, year=2005, phase="Phase_2_pleine")
    assert res["n_total"] == 2
    assert {e["date"] for e in res["evenements"]} == {"2005-07-11", "2005-08-03"}


def test_phase_acceptee_en_langage_courant(jeu_events):
    """Le modele ecrit 'pleine saison', pas 'Phase_2_pleine'."""
    assert lancer(jeu_events, phase="pleine saison")["filtres"]["phase"] == "Phase_2_pleine"
    assert lancer(jeu_events, phase=2)["filtres"]["phase"] == "Phase_2_pleine"


def test_region_insensible_aux_accents(jeu_events):
    """Le catalogue ecrit 'Kedougou' avec accents; le modele rarement."""
    res = lancer(jeu_events, region="kedougou")
    assert res["n_total"] == 1
    assert res["evenements"][0]["date"] == "2001-05-20"


def test_filtre_par_intensite_minimale(jeu_events):
    res = lancer(jeu_events, min_max_precip=50)
    assert res["n_total"] == 2
    assert all(e["max_precip_mm"] >= 50 for e in res["evenements"])


def test_limite_borne_le_detail_mais_pas_le_total(jeu_events):
    """Le total doit rester exact: c est lui que le modele citera."""
    res = lancer(jeu_events, limit=1)
    assert res["n_total"] == 4
    assert res["n_renvoyes"] == 1


def test_tri_par_date_croissante(jeu_events):
    res = lancer(jeu_events, sort_by="date", ascending=True)
    dates = [e["date"] for e in res["evenements"]]
    assert dates == sorted(dates)


def test_aucun_resultat_n_est_pas_une_erreur(jeu_events):
    """'Aucun evenement' est une reponse legitime, pas un echec."""
    res = lancer(jeu_events, year=1999)
    assert res["n_total"] == 0
    assert res["evenements"] == []
    assert "Aucun evenement" in res["message"]


def test_statistiques_et_repartition(jeu_events):
    res = lancer(jeu_events, phase="Phase_2_pleine")
    stats = res["statistiques"]
    assert stats["max_precip_maximal_mm"] == 80.0
    assert stats["repartition_par_phase"] == {"Phase_2_pleine": 2}
    assert stats["regions_les_plus_touchees"][0]["region"] == "Tambacounda"


def test_intervalle_incoherent_est_refuse(jeu_events):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_events, year_min=2010, year_max=2000)
    assert "year_min" in str(exc.value)


def test_limite_hors_bornes_est_refusee(jeu_events):
    with pytest.raises(ToolInputError):
        lancer(jeu_events, limit=500)


def test_mois_invalide_est_refuse(jeu_events):
    with pytest.raises(ToolInputError):
        lancer(jeu_events, month=13)
