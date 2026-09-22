"""Lecture de .docx par la bibliotheque standard.

Un .docx est une archive zip contenant du XML: zipfile + ElementTree suffisent.
Aucune dependance n'est ajoutee, ni au depot, ni au serveur -- qui de toute
facon ne lira jamais de .docx, l'index etant construit hors ligne.

Ce qui compte ici n'est pas le texte brut mais la STRUCTURE: les styles de
titre permettent de rattacher chaque passage a sa section
("2. Donnees et methodologie > 2.3 NOAA OISST v2"), et c'est cette reference
qui permettra a Jarvis de citer au lieu d'affirmer.
"""
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Styles Word a ignorer: entrees de table des matieres et de table des
# illustrations. Sans ce filtre, l'index se remplirait de listes de titres
# sans contenu, qui remonteraient en tete sur toute recherche thematique.
STYLES_IGNORES = ("TM", "Tabledesillustrations", "TOC", "Index")

# Prefixes de styles de titre (Word francais: Titre1..9; anglais: Heading1..9).
STYLES_TITRES = ("Titre", "Heading")

# Sections liminaires sans contenu scientifique exploitable.
SECTIONS_LIMINAIRES = {
    "dedicaces", "dedicace", "remerciements", "sommaire", "table des matieres",
    "liste des figures", "liste des tableaux", "table des illustrations",
    "page des sigles et abreviations", "sigles et abreviations",
}


def _style(paragraphe) -> str:
    proprietes = paragraphe.find(W + "pPr")
    if proprietes is None:
        return ""
    style = proprietes.find(W + "pStyle")
    return style.get(W + "val", "") if style is not None else ""


def _texte(paragraphe) -> str:
    return "".join(n.text or "" for n in paragraphe.iter(W + "t")).strip()


def niveau_titre(style: str):
    """Retourne le niveau (1, 2, 3...) si le style est un titre, sinon None."""
    for prefixe in STYLES_TITRES:
        if style.startswith(prefixe):
            reste = style[len(prefixe):]
            if reste.isdigit():
                return int(reste)
            if not reste:
                return 1
    return None


def lire_paragraphes(chemin) -> list:
    """Retourne [(style, texte), ...] dans l'ordre du document."""
    with zipfile.ZipFile(str(chemin)) as archive:
        racine = ET.fromstring(archive.read("word/document.xml"))
    paragraphes = []
    for noeud in racine.iter(W + "p"):
        texte = _texte(noeud)
        if texte:
            paragraphes.append((_style(noeud), texte))
    return paragraphes


def sections(chemin) -> list:
    """Decoupe un .docx en sections: [{'chemin': [...], 'paragraphes': [...]}].

    Le chemin de section est la pile des titres courants, ce qui donne une
    reference lisible par un humain dans la reponse de Jarvis.
    """
    pile = []
    resultat = []
    courant = {"chemin": [], "paragraphes": []}

    for style, texte in lire_paragraphes(chemin):
        if any(style.startswith(prefixe) for prefixe in STYLES_IGNORES):
            continue

        niveau = niveau_titre(style)
        if niveau is not None:
            if courant["paragraphes"]:
                resultat.append(courant)
            pile = pile[: niveau - 1]
            pile.append(texte)
            courant = {"chemin": list(pile), "paragraphes": []}
            continue

        courant["paragraphes"].append(texte)

    if courant["paragraphes"]:
        resultat.append(courant)

    return [s for s in resultat if not _est_liminaire(s["chemin"])]


def _est_liminaire(chemin_section) -> bool:
    if not chemin_section:
        return False
    import unicodedata
    titre = chemin_section[0]
    brut = unicodedata.normalize("NFKD", titre)
    sans = "".join(c for c in brut if not unicodedata.combining(c)).lower().strip()
    return sans in SECTIONS_LIMINAIRES
