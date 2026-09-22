"""Outil search_documents: recherche dans le memoire et l article.

Corpus synthetique: aucun acces a l index reel, aucun .docx, aucun disque.
"""
import pytest

from jarvis.knowledge import bm25
from jarvis.tools import documents
from jarvis.tools.common import ToolInputError


@pytest.fixture
def corpus():
    passages = [
        {"ordre": 0, "document": "memoire",
         "section": "Chapitre 2 > 2.1 Donnees de precipitations : CHIRPS",
         "texte": "Les precipitations quotidiennes proviennent du produit CHIRPS, "
                  "retenu pour sa resolution de 0.05 degre et sa couverture "
                  "continue depuis 1981 sur toute l Afrique de l Ouest. " + "detail " * 200},
        {"ordre": 1, "document": "article",
         "section": "2. Donnees et methodologie > 2.2 Detection des evenements",
         "texte": "Un evenement extreme est retenu lorsque l anomalie standardisee "
                  "depasse deux ecarts-types sur au moins quarante pixels."},
        {"ordre": 2, "document": "memoire",
         "section": "Chapitre 4 > 4.1 Discussion du signal atlantique",
         "texte": "Le signal atlantique domine la pleine saison, ce qui distingue "
                  "ce travail de la litterature centree sur ENSO."},
    ]
    return {
        "version": 1,
        "documents": [
            {"cle": "memoire", "titre": "Memoire de Master", "auteur": "Laity Faye",
             "statut": "non publie", "n_passages": 2},
            {"cle": "article", "titre": "Article Sahel senegalais", "auteur": "Laity Faye",
             "statut": "en preparation", "n_passages": 1},
        ],
        "passages": passages,
        "index": bm25.construire(passages),
    }


def lancer(corpus, **params):
    return documents.run(params, {"knowledge": corpus})


def test_recherche_nominale(corpus):
    res = lancer(corpus, query="CHIRPS resolution")
    assert res["n_resultats"] >= 1
    assert "CHIRPS" in res["passages"][0]["section"]


def test_chaque_passage_porte_sa_citation(corpus):
    """Sans reference de section, Jarvis affirmerait au lieu de citer."""
    res = lancer(corpus, query="detection evenements anomalie")
    passage = res["passages"][0]
    assert passage["citation"].startswith(("Memoire,", "Article,"))
    assert passage["section"] in passage["citation"]
    assert passage["document_titre"]


def test_extrait_plafonne(corpus):
    """Le memoire n est pas publie et le widget est public: aucun passage ne
    doit sortir en entier."""
    res = lancer(corpus, query="CHIRPS resolution")
    passage = res["passages"][0]
    assert len(passage["extrait"]) <= documents.EXTRAIT_MAX + 10
    assert passage["extrait_tronque"] is True
    assert passage["extrait"].endswith("[...]")


def test_filtre_par_document(corpus):
    res = lancer(corpus, query="evenements extremes anomalie", document="article")
    assert res["filtre_document"] == "article"
    assert all(p["document"] == "article" for p in res["passages"])


def test_limite(corpus):
    assert len(lancer(corpus, query="precipitations evenements signal", limit=1)["passages"]) == 1


def test_aucun_resultat_n_est_pas_une_erreur(corpus):
    res = lancer(corpus, query="zzzz terme absent")
    assert res["n_resultats"] == 0
    assert res["passages"] == []
    assert "Reformule" in res["message"]


def test_query_obligatoire(corpus):
    with pytest.raises(ToolInputError) as exc:
        lancer(corpus)
    assert "query est requis" in str(exc.value)


def test_query_vide(corpus):
    with pytest.raises(ToolInputError):
        lancer(corpus, query="   ")


def test_limite_hors_bornes(corpus):
    with pytest.raises(ToolInputError):
        lancer(corpus, query="CHIRPS", limit=50)


def test_document_inconnu(corpus):
    with pytest.raises(ToolInputError) as exc:
        lancer(corpus, query="CHIRPS", document="these_de_quelqu_un_d_autre")
    assert "memoire" in str(exc.value)


def test_catalogue_annonce(corpus):
    res = lancer(corpus, query="CHIRPS")
    cles = {d["cle"] for d in res["documents_disponibles"]}
    assert cles == {"memoire", "article"}


def test_note_de_citation_presente(corpus):
    res = lancer(corpus, query="CHIRPS")
    assert "Cite le document" in res["note"]


def test_declaration_impose_des_mots_cles():
    """Une question complete donne de mauvais resultats en lexical: la
    description doit le dire au modele."""
    assert "MOTS-CLES" in documents.DESCRIPTION
    assert documents.SCHEMA["required"] == ["query"]
