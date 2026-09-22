"""Moteur de recherche BM25: classement, ponderation des titres, doublons."""
import pytest

from jarvis.knowledge import bm25


@pytest.fixture
def passages():
    return [
        {"ordre": 0, "document": "memoire", "section": "2.1 Donnees de precipitations : CHIRPS",
         "texte": "Les precipitations quotidiennes proviennent du produit CHIRPS, "
                  "retenu pour sa resolution spatiale fine et sa couverture longue."},
        {"ordre": 1, "document": "memoire", "section": "3.2 Teleconnexions oceaniques",
         "texte": "Le signal atlantique domine en pleine saison. La correlation "
                  "avec AMO est la plus forte, ce qui appelle une discussion."},
        {"ordre": 2, "document": "article", "section": "2.2 Donnees de precipitations : CHIRPS",
         "texte": "Les precipitations quotidiennes proviennent du produit CHIRPS, "
                  "retenu pour sa resolution spatiale fine et sa couverture longue."},
        {"ordre": 3, "document": "article", "section": "6. Conclusion",
         "texte": "En conclusion, la detection des evenements et l analyse des "
                  "correlations ouvrent des perspectives operationnelles."},
        {"ordre": 4, "document": "memoire", "section": "2.2 Methodologie de detection des evenements",
         "texte": "Un evenement est retenu lorsque l anomalie standardisee depasse "
                  "deux ecarts-types sur un nombre suffisant de pixels."},
    ]


@pytest.fixture
def index(passages):
    return bm25.construire(passages)


def test_index_couvre_tous_les_passages(index, passages):
    assert index["n"] == len(passages)
    assert len(index["longueurs"]) == len(passages)
    assert index["longueur_moyenne"] > 0


def test_terme_specifique_remonte_le_bon_passage(index, passages):
    resultats = bm25.rechercher(index, passages, "CHIRPS resolution", 1)
    assert "CHIRPS" in resultats[0][0]["section"]


def test_le_titre_de_section_pese_plus_que_le_corps(index, passages):
    """Regression: une conclusion citant 'detection' en passant remontait
    devant la section de methodologie qui porte ce titre."""
    resultats = bm25.rechercher(index, passages, "detection des evenements", 1)
    assert "Methodologie de detection" in resultats[0][0]["section"]


def test_doublons_memoire_article_ecartes(index, passages):
    """Les deux documents partagent des paragraphes identiques: les renvoyer
    tous les deux gaspille le contexte."""
    resultats = bm25.rechercher(index, passages, "CHIRPS precipitations quotidiennes", 3)
    textes = [p["texte"] for p, _ in resultats]
    assert len(textes) == len(set(textes))


def test_doublons_conservables_sur_demande(index, passages):
    avec = bm25.rechercher(index, passages, "CHIRPS precipitations quotidiennes", 3,
                           dedupliquer=False)
    sans = bm25.rechercher(index, passages, "CHIRPS precipitations quotidiennes", 3)
    assert len(avec) > len(sans)


def test_filtre_par_document(index, passages):
    resultats = bm25.rechercher(index, passages, "CHIRPS", 5, document="article")
    assert resultats
    assert all(p["document"] == "article" for p, _ in resultats)


def test_requete_sans_correspondance(index, passages):
    assert bm25.rechercher(index, passages, "zzzz inexistant", 3) == []


def test_requete_vide(index, passages):
    assert bm25.rechercher(index, passages, "", 3) == []
    assert bm25.rechercher(index, passages, "le de la", 3) == []


def test_limite_respectee(index, passages):
    assert len(bm25.rechercher(index, passages, "precipitations correlations", 2)) <= 2


def test_scores_decroissants(index, passages):
    resultats = bm25.rechercher(index, passages, "precipitations CHIRPS detection", 4)
    scores = [s for _, s in resultats]
    assert scores == sorted(scores, reverse=True)


def test_synonyme_trouve_le_passage(index, passages):
    """'pluie' n apparait nulle part dans le corpus, qui dit 'precipitations'."""
    resultats = bm25.rechercher(index, passages, "pluie quotidienne", 1)
    assert resultats
    assert "precipitations" in resultats[0][0]["texte"]


def test_idf_toujours_positif():
    """Un terme present dans plus de la moitie des passages ne doit pas
    penaliser le score."""
    assert bm25._idf(10, 9) > 0
    assert bm25._idf(10, 1) > bm25._idf(10, 9)
