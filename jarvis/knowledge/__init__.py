"""Base documentaire de Jarvis - Phase 3.

Le memoire et l'article vivent HORS du depot (dossier personnel de Laity), et
le serveur de production ne les aura jamais. L'index est donc construit hors
ligne par scripts/15_build_jarvis_index.py, puis embarque dans le depot sous
forme d'un seul fichier compresse.

Consequence voulue: a l'execution, aucune bibliotheque de lecture de documents,
aucun acces aux fichiers sources, aucun appel reseau. Jarvis ne lit qu'un
index deja construit.
"""
import gzip
import json
import logging
import threading
from pathlib import Path

log = logging.getLogger("jarvis.knowledge")

DOSSIER = Path(__file__).resolve().parent
FICHIER_INDEX = DOSSIER / "corpus.json.gz"

_verrou = threading.Lock()
_corpus = None


class CorpusIndisponible(Exception):
    """Index absent ou illisible. Jarvis doit le dire, pas improviser."""


def charger(chemin: Path = None) -> dict:
    """Charge l'index (une fois par process) et le garde en memoire.

    ~250 passages, environ 1 Mo decompresse: le garder entierement en memoire
    coute moins cher qu'une relecture disque a chaque question.
    """
    global _corpus
    if chemin is None and _corpus is not None:
        return _corpus
    cible = chemin or FICHIER_INDEX
    with _verrou:
        if chemin is None and _corpus is not None:
            return _corpus
        if not cible.exists():
            raise CorpusIndisponible(
                "Index documentaire absent: %s. Le construire avec "
                "scripts/15_build_jarvis_index.py." % cible.name
            )
        try:
            with gzip.open(cible, "rt", encoding="utf-8") as flux:
                donnees = json.load(flux)
        except Exception as exc:
            raise CorpusIndisponible(str(exc)) from exc
        _verifier(donnees)
        if chemin is None:
            _corpus = donnees
        log.info("Index documentaire charge: %d passages, %d documents.",
                 len(donnees["passages"]), len(donnees["documents"]))
        return donnees


def _verifier(donnees: dict) -> None:
    from .texte import VERSION as VERSION_TEXTE

    for cle in ("passages", "index", "documents", "version"):
        if cle not in donnees:
            raise CorpusIndisponible("Index incomplet: cle '%s' absente." % cle)
    if donnees.get("version_texte") != VERSION_TEXTE:
        # Refuser de servir vaut mieux que citer a cote: un index construit
        # avec une autre tokenisation renverrait des passages sans rapport,
        # et sans le moindre message d'erreur.
        raise CorpusIndisponible(
            "Index construit avec une autre version du traitement de texte "
            "(%s au lieu de %s). Reconstruire avec "
            "scripts/15_build_jarvis_index.py."
            % (donnees.get("version_texte"), VERSION_TEXTE)
        )
    if len(donnees["index"].get("longueurs", [])) != len(donnees["passages"]):
        # Un index desynchronise des passages ferait citer un extrait pour un
        # autre: mieux vaut refuser de servir que citer a cote.
        raise CorpusIndisponible("Index desynchronise des passages.")


def vider_cache() -> None:
    global _corpus
    with _verrou:
        _corpus = None
