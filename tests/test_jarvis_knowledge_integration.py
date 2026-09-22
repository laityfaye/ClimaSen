"""Integration: l index documentaire reel repond-il aux bonnes sections ?

Les tests unitaires verifient la mecanique sur un corpus jouet. Celui-ci
verifie la seule chose qu ils ne peuvent pas: que sur le VRAI memoire et le
VRAI article, une question courante retombe sur la section qui traite le sujet.
C est le garde-fou contre une regression de pertinence -- un changement de
tokenisation ou de ponderation peut laisser tous les tests unitaires au vert
tout en degradant les reponses.

Se saute si l index n a pas ete construit.
"""
import json

import pytest

from jarvis import tools
from jarvis.knowledge import FICHIER_INDEX, charger

pytestmark = pytest.mark.skipif(
    not FICHIER_INDEX.exists(),
    reason="Index documentaire absent (scripts/15_build_jarvis_index.py)",
)


@pytest.fixture(scope="module")
def corpus():
    return charger()


def test_corpus_complet(corpus):
    cles = {d["cle"] for d in corpus["documents"]}
    assert cles == {"memoire", "article"}
    assert len(corpus["passages"]) > 100
    assert corpus["index"]["n"] == len(corpus["passages"])


def test_aucun_passage_vide(corpus):
    assert all(p["texte"].strip() for p in corpus["passages"])
    assert all(p["section"] for p in corpus["passages"])


def test_table_des_matieres_exclue(corpus):
    """Les entrees de table des matieres remonteraient en tete de toute
    recherche thematique sans rien apprendre."""
    sections = {p["section"] for p in corpus["passages"]}
    assert not any(s.lower().startswith("sommaire") for s in sections)
    assert not any("liste des figures" in s.lower() for s in sections)


# Chaque question doit retomber sur une section dont le titre contient l un de
# ces fragments. Volontairement tolerant sur la section exacte: c est la
# pertinence du sujet qui est testee, pas un classement au passage pres.
ATTENTES = [
    ("CHIRPS choix donnees precipitation", ["chirps", "donnees"]),
    ("correction autocorrelation AR1 degres de liberte", ["statistique", "teleconnexion"]),
    ("K-means classification motifs SST", ["classification", "sst"]),
    ("detection evenements extremes seuil ecart-type", ["detection", "evenement", "methodolog"]),
    ("phases de la saison des pluies", ["phase", "saison", "evenement", "caracterisation"]),
]


@pytest.mark.parametrize("requete,fragments", ATTENTES)
def test_pertinence_des_reponses(corpus, requete, fragments):
    from jarvis.knowledge import bm25
    from jarvis.knowledge.texte import normaliser

    resultats = bm25.rechercher(corpus["index"], corpus["passages"], requete, 3)
    assert resultats, "aucun resultat pour %r" % requete
    sections = [normaliser(p["section"]) for p, _ in resultats]
    assert any(any(f in s for f in fragments) for s in sections), (
        "%r -> %s" % (requete, sections)
    )


@pytest.mark.asyncio
async def test_outil_sur_l_index_reel():
    resultat = await tools.execute(
        "search_documents", {"query": "CHIRPS resolution spatiale"}, "public")
    assert not resultat["is_error"], resultat["content"]
    donnees = json.loads(resultat["content"])
    assert donnees["passages"]
    assert "CHIRPS" in donnees["passages"][0]["extrait"].upper()


@pytest.mark.asyncio
async def test_taille_bornee_sur_l_index_reel():
    resultat = await tools.execute(
        "search_documents", {"query": "teleconnexion correlation", "limit": 5}, "public")
    assert len(resultat["content"]) <= tools.MAX_RESULT_CHARS


def test_index_refuse_si_version_de_texte_differente(tmp_path):
    """Un index construit avec une autre tokenisation renverrait des passages
    sans rapport, sans lever la moindre erreur."""
    import gzip

    from jarvis.knowledge import CorpusIndisponible, charger

    faux = tmp_path / "corpus.json.gz"
    with gzip.open(faux, "wt", encoding="utf-8") as flux:
        json.dump({"version": 1, "version_texte": -1, "documents": [],
                   "passages": [], "index": {"longueurs": []}}, flux)
    with pytest.raises(CorpusIndisponible) as exc:
        charger(faux)
    assert "Reconstruire" in str(exc.value)
