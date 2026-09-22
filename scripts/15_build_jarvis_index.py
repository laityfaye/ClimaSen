#!/usr/bin/env python3
"""Construit l'index documentaire de Jarvis (Phase 3).

A lancer sur le poste de Laity, la ou vivent le memoire et l'article. Le
resultat -- jarvis/knowledge/corpus.json.gz -- est versionne et deploye avec
l'application: le serveur ne lit jamais les .docx.

    py -3 scripts/15_build_jarvis_index.py
    py -3 scripts/15_build_jarvis_index.py --inspecter   (sans ecrire)

Exposition publique du memoire: voir CORPUS ci-dessous. Le memoire n'est pas
publie; le widget, lui, est public et anonyme. Retirer une entree de CORPUS et
reconstruire suffit a l'exclure.
"""
import argparse
import gzip
import json
import sys

# La console Windows est en CP1252: sans cela, le premier extrait accentue
# affiche fait planter le script sur un UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from jarvis.knowledge import bm25, docx, texte  # noqa: E402

# Les sources vivent hors du depot: dossier personnel, non versionne.
SOURCES = RACINE.parent / "recherche" / "Rédaction"

CORPUS = [
    {
        "cle": "memoire",
        "titre": "Memoire de Master - Teleconnexions et precipitations extremes au Senegal",
        "fichier": "Mémoire_VERSION_FINALE (1).docx",
        "auteur": "Laity Faye",
        "statut": "non publie",
    },
    {
        "cle": "article",
        "titre": "Article - Extremes pluviometriques au Sahel senegalais",
        "fichier": "Article_extremes_pluviometriques_Sahel_senegalais_v2 (1).docx",
        "auteur": "Laity Faye",
        "statut": "en preparation",
    },
]

TAILLE_PASSAGE = 180
RECOUVREMENT = 40
MOTS_MINIMUM = 25   # sous ce seuil, un passage n'apprend rien et pollue l'index
VERSION = 1


def construire(inspecter=False):
    passages = []
    documents = []

    for source in CORPUS:
        chemin = SOURCES / source["fichier"]
        if not chemin.exists():
            print("  ABSENT: %s" % chemin)
            continue

        sections = docx.sections(chemin)
        n_avant = len(passages)

        for section in sections:
            chemin_section = " > ".join(section["chemin"]) or "(sans titre)"
            for morceau in texte.decouper(section["paragraphes"],
                                          TAILLE_PASSAGE, RECOUVREMENT):
                if len(texte.mots_bruts(morceau)) < MOTS_MINIMUM:
                    continue
                passages.append({
                    "ordre": len(passages),
                    "document": source["cle"],
                    "section": chemin_section,
                    "texte": " ".join(morceau.split()),
                    "n_mots": len(texte.mots_bruts(morceau)),
                })

        documents.append({
            "cle": source["cle"],
            "titre": source["titre"],
            "auteur": source["auteur"],
            "statut": source["statut"],
            "fichier": source["fichier"],
            "n_sections": len(sections),
            "n_passages": len(passages) - n_avant,
        })
        print("  %-9s %3d sections  %3d passages  (%s)"
              % (source["cle"], len(sections), len(passages) - n_avant,
                 source["fichier"][:45]))

    if not passages:
        print("\nAucun passage: index non ecrit.")
        return None

    index = bm25.construire(passages)
    corpus = {
        "version": VERSION,
        "version_texte": texte.VERSION,
        "construit_le": date.today().isoformat(),
        "documents": documents,
        "passages": passages,
        "index": index,
    }

    print("\n  %d passages, %d termes distincts, %.0f mots par passage en moyenne"
          % (len(passages), len(index["postings"]), index["longueur_moyenne"]))

    if inspecter:
        _inspecter(corpus)
        return corpus

    cible = RACINE / "jarvis" / "knowledge" / "corpus.json.gz"
    with gzip.open(cible, "wt", encoding="utf-8") as flux:
        json.dump(corpus, flux, ensure_ascii=False)
    print("  ecrit: %s (%.0f Ko)" % (cible.relative_to(RACINE),
                                     cible.stat().st_size / 1024))
    return corpus


def _inspecter(corpus):
    """Controle de qualite: sections retenues et essais de recherche."""
    print("\n--- sections indexees ---")
    vues = []
    for passage in corpus["passages"]:
        cle = (passage["document"], passage["section"])
        if cle not in vues:
            vues.append(cle)
    for document, section in vues[:40]:
        print("  [%s] %s" % (document, section[:90]))
    if len(vues) > 40:
        print("  ... %d sections de plus" % (len(vues) - 40))

    print("\n--- essais de recherche ---")
    for requete in ("Pourquoi CHIRPS plutot qu'une autre base de pluie ?",
                    "Comment sont detectes les evenements extremes ?",
                    "Quel est le role du Nino 3.4 ?",
                    "correction de l'autocorrelation AR1",
                    "decoupage de la saison des pluies en phases"):
        resultats = bm25.rechercher(corpus["index"], corpus["passages"], requete, 2)
        print("\n  > %s" % requete)
        for passage, score in resultats:
            extrait, _ = texte.extrait(passage["texte"], 150)
            print("    %.2f [%s] %s" % (score, passage["document"],
                                        passage["section"][:60]))
            print("         %s" % extrait)
        if not resultats:
            print("    (aucun resultat)")


if __name__ == "__main__":
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--inspecter", action="store_true",
                           help="affiche sections et essais sans ecrire l'index")
    arguments = analyseur.parse_args()

    print("Construction de l'index documentaire Jarvis")
    print("Sources: %s\n" % SOURCES)
    construire(inspecter=arguments.inspecter)
