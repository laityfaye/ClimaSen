"""Lecture et modification des documents de recherche (.docx).

Travaille sur les FICHIERS REELS, contrairement a jarvis/knowledge/ qui
interroge un index fige. La distinction est essentielle: une correction doit
viser le document, pas l'instantane qui en a ete tire.

Trois precautions, imposees ici et non dans le prompt:

1. Seuls les noeuds de TEXTE (<w:t>) sont modifies. Un remplacement sur le XML
   entier toucherait aussi les attributs de mise en page -- Word y stocke des
   largeurs en twips, ou "560" est une valeur courante.
2. Une sauvegarde horodatee est ecrite avant toute modification.
3. Toutes les autres entrees de l'archive sont recopiees a l'octet pres: un
   .docx est un zip, le reconstruire de travers corromprait le fichier.

Ce module n'expose aucune fonction qui ecrive sans qu'on le lui demande
explicitement: `appliquer_remplacement` est le seul point d'ecriture, et il
n'est appele que par une action approuvee (voir jarvis/actions.py).
"""
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .knowledge import docx

MOTIF_TEXTE = re.compile(r"(<w:t[^>]*>)([^<]*)(</w:t>)")
SUFFIXE_SAUVEGARDE = ".avant-jarvis-%s.docx"
MAX_OCCURRENCES = 50


class DocumentIntrouvable(Exception):
    """Cle de document inconnue ou fichier absent."""


class RemplacementImpossible(Exception):
    """Le texte cherche est absent, ou trop frequent pour etre remplace sans
    risque d'atteindre des passages non voulus."""


def _dossier(settings) -> Path:
    return Path(settings.documents_dir)


def catalogue(settings) -> list:
    """Documents connus, avec leur etat sur le disque."""
    sortie = []
    for cle, nom in settings.documents.items():
        chemin = _dossier(settings) / nom
        entree = {"cle": cle, "fichier": nom, "present": chemin.exists()}
        if chemin.exists():
            info = chemin.stat()
            entree["taille_ko"] = round(info.st_size / 1024)
            entree["modifie_le"] = datetime.fromtimestamp(
                info.st_mtime).strftime("%Y-%m-%d %H:%M")
        sortie.append(entree)
    return sortie


def chemin_document(settings, cle: str) -> Path:
    nom = settings.documents.get(cle)
    if nom is None:
        raise DocumentIntrouvable(
            "Document inconnu: %r. Documents disponibles: %s."
            % (cle, ", ".join(sorted(settings.documents)))
        )
    chemin = _dossier(settings) / nom
    if not chemin.exists():
        raise DocumentIntrouvable(
            "Fichier absent sur le disque: %s" % nom
        )
    return chemin


def sections(settings, cle: str) -> list:
    """Sections du document vivant: [{'chemin', 'texte', 'n_mots'}]."""
    chemin = chemin_document(settings, cle)
    sortie = []
    for section in docx.sections(chemin):
        texte = " ".join(" ".join(section["paragraphes"]).split())
        sortie.append({
            "section": " > ".join(section["chemin"]) or "(sans titre)",
            "texte": texte,
            "n_mots": len(texte.split()),
        })
    return sortie


def occurrences(settings, cle: str, recherche: str, contexte: int = 90) -> list:
    """Occurrences d'un texte exact, avec leur section et leur voisinage."""
    trouvees = []
    for section in sections(settings, cle):
        depart = 0
        texte = section["texte"]
        while True:
            i = texte.find(recherche, depart)
            if i == -1:
                break
            trouvees.append({
                "section": section["section"],
                "avant": texte[max(0, i - contexte):i],
                "texte": recherche,
                "apres": texte[i + len(recherche):i + len(recherche) + contexte],
            })
            depart = i + len(recherche)
            if len(trouvees) >= MAX_OCCURRENCES:
                return trouvees
    return trouvees


def _lire_archive(chemin: Path):
    with zipfile.ZipFile(chemin) as archive:
        return [(info, archive.read(info.filename)) for info in archive.infolist()]


def previsualiser_remplacement(settings, cle: str, avant: str, apres: str) -> dict:
    """Calcule ce que ferait le remplacement, SANS rien ecrire."""
    if not avant:
        raise RemplacementImpossible("Le texte a remplacer ne peut pas etre vide.")
    if avant == apres:
        raise RemplacementImpossible("Le texte de remplacement est identique.")

    chemin = chemin_document(settings, cle)
    entrees = _lire_archive(chemin)
    xml = next(c for i, c in entrees if i.filename == "word/document.xml").decode("utf-8")

    changements = []

    def _remplacer(correspondance):
        ouvrant, contenu, fermant = correspondance.groups()
        if avant not in contenu:
            return correspondance.group(0)
        modifie = contenu.replace(avant, apres)
        changements.append({"avant": contenu, "apres": modifie})
        return ouvrant + modifie + fermant

    MOTIF_TEXTE.sub(_remplacer, xml)

    if not changements:
        # Le cas le plus courant: Word a coupe la phrase en plusieurs runs
        # (une correction, un changement de police). Le dire explicitement
        # evite de chercher une faute de frappe qui n'existe pas.
        raise RemplacementImpossible(
            "Texte introuvable dans un seul fragment de %s. Il peut etre "
            "scinde par une mise en forme: essayer une portion plus courte, "
            "sans espace ni ponctuation aux extremites." % cle
        )
    if len(changements) > MAX_OCCURRENCES:
        raise RemplacementImpossible(
            "%d occurrences trouvees: trop pour un remplacement sur, "
            "preciser le texte recherche." % len(changements)
        )
    return {"document": cle, "fichier": chemin.name,
            "n_occurrences": len(changements), "changements": changements}


def appliquer_remplacement(settings, cle: str, avant: str, apres: str) -> dict:
    """Ecrit le remplacement. SEUL point d'ecriture du module.

    N'est appele que depuis une action approuvee par l'utilisateur.
    """
    apercu = previsualiser_remplacement(settings, cle, avant, apres)
    chemin = chemin_document(settings, cle)
    entrees = _lire_archive(chemin)

    xml = next(c for i, c in entrees if i.filename == "word/document.xml").decode("utf-8")

    def _remplacer(correspondance):
        ouvrant, contenu, fermant = correspondance.groups()
        return ouvrant + contenu.replace(avant, apres) + fermant

    xml_corrige = MOTIF_TEXTE.sub(_remplacer, xml)

    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    sauvegarde = chemin.with_name(chemin.stem + SUFFIXE_SAUVEGARDE % horodatage)
    shutil.copy2(chemin, sauvegarde)

    # Ecriture dans un fichier temporaire puis remplacement atomique: une
    # interruption en cours d'ecriture laisserait sinon un .docx tronque.
    temporaire = chemin.with_suffix(".docx.tmp")
    with zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as sortie:
        for info, contenu in entrees:
            if info.filename == "word/document.xml":
                contenu = xml_corrige.encode("utf-8")
            sortie.writestr(info, contenu)
    temporaire.replace(chemin)

    return {"document": cle, "fichier": chemin.name,
            "n_occurrences": apercu["n_occurrences"],
            "sauvegarde": sauvegarde.name,
            "changements": apercu["changements"]}
