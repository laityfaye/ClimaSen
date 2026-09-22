"""Outil get_sst_index: lecture des indices SST.

Fonction pure testee directement, sans serveur, sans API, sans fichier.
"""
import pytest

from jarvis.tools import sst_index
from jarvis.tools.common import ToolInputError


def lancer(jeu_indices, **params):
    return sst_index.run(params, {"indices": jeu_indices})


def test_moyenne_et_extremes(jeu_indices):
    res = lancer(jeu_indices, index="Nino34")
    assert res["indice"] == "Nino34"
    assert res["unite"].startswith("anomalie")
    # La serie synthetique est une rampe de -1.5 a +1.5.
    assert res["resume"]["minimum"]["valeur"] == pytest.approx(-1.5, abs=0.01)
    assert res["resume"]["maximum"]["valeur"] == pytest.approx(1.5, abs=0.01)
    assert res["resume"]["minimum"]["date"] == "1983-01-01"
    assert res["periode"]["n_jours"] == len(jeu_indices)


def test_annee_seule_couvre_les_douze_mois(jeu_indices):
    """Piege: '1984' en borne de fin ne doit pas s arreter au 1er janvier."""
    res = lancer(jeu_indices, index="Nino34", date="1984")
    assert res["periode"]["debut"] == "1984-01-01"
    assert res["periode"]["fin"] == "1984-12-31"
    assert res["periode"]["n_jours"] == 366  # 1984 est bissextile


def test_mois_seul(jeu_indices):
    res = lancer(jeu_indices, index="IOD", date="1983-02")
    assert res["periode"]["debut"] == "1983-02-01"
    assert res["periode"]["fin"] == "1983-02-28"


def test_bascule_automatique_en_annuel(jeu_indices):
    """Au-dela de 24 mois, la serie mensuelle exploserait le contexte."""
    res = lancer(jeu_indices, index="Nino34")
    assert res["serie"]["pas"] == "annuelle"
    assert len(res["serie"]["points"]) == 3
    assert "annuel" in res["note"]


def test_serie_mensuelle_sur_courte_periode(jeu_indices):
    res = lancer(jeu_indices, index="Nino34", start="1983-01", end="1983-06")
    assert res["serie"]["pas"] == "mensuelle"
    assert len(res["serie"]["points"]) == 6
    assert res["serie"]["points"][0]["periode"] == "1983-01"


def test_alias_d_indice(jeu_indices):
    """Le modele ecrit rarement la forme exacte du fichier."""
    for saisie in ("nino 3.4", "NINO34", "enso"):
        assert lancer(jeu_indices, index=saisie)["indice"] == "Nino34"


def test_indice_inconnu_liste_les_valeurs_acceptees(jeu_indices):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_indices, index="ete")
    assert "Nino34" in str(exc.value)


def test_indice_absent_du_fichier(jeu_indices):
    """Indice valide pour la plateforme mais absent des colonnes lues."""
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_indices, index="AMO")
    assert "AMO" in str(exc.value)


def test_periode_hors_couverture(jeu_indices):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_indices, index="Nino34", date="2020")
    assert "couverture" in str(exc.value)


def test_date_mal_formee(jeu_indices):
    with pytest.raises(ToolInputError) as exc:
        lancer(jeu_indices, index="Nino34", date="hier")
    assert "AAAA-MM-JJ" in str(exc.value)


def test_schema_declare_index_obligatoire():
    assert sst_index.SCHEMA["required"] == ["index"]
    assert "Nino34" in sst_index.SCHEMA["properties"]["index"]["enum"]
