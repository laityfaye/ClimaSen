"""Outil search_extreme_events: catalogue des evenements extremes."""
import pytest

from jarvis.tools import events
from jarvis.tools.common import ToolInputError


def lancer(jeu_events, population=None, **params):
    # population=None : jeu facultatif absent, aucun acces disque.
    return events.run(params, {"events": jeu_events, "population_touchee": population})


def _population():
    """Extrait au format du script 33 (+ colonnes 2026 du script 37)."""
    import pandas as pd
    return pd.DataFrame({
        "date": ["2005-07-11", "2012-09-28", "2001-05-20"],
        "population_touchee_2023": [3_000_000, 18_069_311, 200_000],
        "part_population_nationale_pct": [16.53, 99.54, 1.1],
        "departements_touches": [9, 46, 2],
        "departement_le_plus_touche": ["TAMBACOUNDA", "M’BACKE", "SALEMATA"],
        "population_touchee_2026": [3_240_000, 19_513_054, None],
    }).set_index("date")


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


# --- habitants des zones touchees (script 33, projection 2026 du script 37) -----
def test_sans_jeu_de_population_aucun_champ_habitants(jeu_events):
    res = lancer(jeu_events)
    assert "habitants_zone_touchee_2023" not in res["evenements"][0]
    assert "population" not in res


def test_chaque_evenement_porte_ses_habitants(jeu_events):
    res = lancer(jeu_events, _population(), year=2012)
    evt = res["evenements"][0]
    assert evt["habitants_zone_touchee_2023"] == 18_069_311
    assert evt["part_population_nationale_pct"] == 99.5
    assert evt["departements_touches"] == 46
    assert evt["habitants_meme_zone_2026_projection"] == 19_513_054
    assert "sinistres" in res["population"]["lecture"]


def test_projection_absente_n_invente_rien(jeu_events):
    evt = lancer(jeu_events, _population(), year=2001)["evenements"][0]
    assert evt["habitants_zone_touchee_2023"] == 200_000
    assert "habitants_meme_zone_2026_projection" not in evt


def test_tri_par_habitants_et_statistiques(jeu_events):
    res = lancer(jeu_events, _population(), sort_by="population_touchee")
    assert [e["date"] for e in res["evenements"][:2]] == ["2012-09-28", "2005-07-11"]
    stats = res["statistiques"]["habitants_zone_touchee_2023"]
    assert stats["maximum"] == 18_069_311 and stats["date_du_maximum"] == "2012-09-28"
    assert stats["mediane"] == 3_000_000        # 3 evenements renseignes sur 4


def test_tri_par_habitants_sans_le_jeu_est_refuse(jeu_events):
    with pytest.raises(ToolInputError, match="habitants"):
        lancer(jeu_events, sort_by="population_touchee")


def test_memes_chiffres_que_la_fiche_evenement():
    """Vraies sorties : la valeur rendue est celle du CSV du script 33."""
    import pandas as pd
    from pathlib import Path
    from jarvis.tools import dataset
    csv = (Path(__file__).resolve().parent.parent / "outputs" / "exposition_evenements"
           / "population_touchee_evenements.csv")
    if not csv.exists():
        pytest.skip("script 33 non lance")
    attendu = pd.read_csv(csv, encoding="utf-8").set_index("date")
    res = events.run({"sort_by": "population_touchee", "limit": 1},
                     {"events": dataset.get("events")})
    evt = res["evenements"][0]
    assert evt["habitants_zone_touchee_2023"] == int(attendu["population_touchee_2023"].max())
    assert evt["date"] == attendu["population_touchee_2023"].idxmax()
