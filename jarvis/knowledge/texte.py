"""Traitement du texte francais: normalisation, tokenisation, decoupage.

Fonctions pures, sans dependance au format source ni au moteur de recherche:
elles se testent sur des chaines, et le constructeur d'index comme le moteur de
recherche appliquent EXACTEMENT le meme traitement. C'est la condition pour
qu'une requete retrouve les passages: une divergence d'un seul caractere entre
les deux cotes rendrait l'index muet.
"""
import re
import unicodedata

# Version du traitement de texte. L'index embarque la valeur en vigueur au
# moment de sa construction: toute evolution de la tokenisation ou des racines
# rend l'index precedent incompatible -- les jetons stockes ne correspondraient
# plus a ceux calcules a la recherche, et la recherche renverrait des passages
# faux SANS la moindre erreur. Incrementer a chaque changement.
VERSION = 2

# Mots vides francais. Liste volontairement courte: on indexe un corpus
# scientifique, ou "modele", "donnee" ou "resultat" sont porteurs de sens.
# Ne sont retires que les mots grammaticaux, qui n'apportent rien au score et
# gonflent l'index.
MOTS_VIDES = {
    "a", "afin", "ai", "aient", "ainsi", "alors", "au", "aucun", "aussi",
    "autre", "autres", "aux", "avaient", "avait", "avec", "avoir", "car",
    "ce", "cela", "celle", "celles", "celui", "ces", "cet", "cette", "ceux",
    "chaque", "comme", "dans", "de", "des", "donc", "dont", "du", "elle",
    "elles", "en", "entre", "est", "et", "etaient", "etait", "etant", "ete",
    "etre", "eu", "il", "ils", "je", "la", "le", "les", "leur", "leurs",
    "lors", "lui", "ma", "mais", "me", "meme", "mes", "moins", "mon", "ne",
    "ni", "nos", "notre", "nous", "on", "ont", "ou", "par", "pas", "peu",
    "peut", "plus", "pour", "pourquoi", "qu", "quand", "que", "quel",
    "quelle", "quelles", "quels", "qui", "sa", "sans", "se", "sera", "ses",
    "si", "sol", "son", "sont", "sous", "sur", "ta", "te", "tes", "toi",
    "ton", "tous", "tout", "toute", "toutes", "tres", "tu", "un", "une",
    "vos", "votre", "vous", "y", "the", "of", "and", "in", "to", "is",
    # Mots de discours: frequents dans une question posee en langage naturel,
    # absents de toute intention thematique. Sans eux dans cette liste, deux
    # mots creux d'une question peuvent l'emporter sur le seul terme precis
    # qu'elle contient (constate sur "Pourquoi CHIRPS plutot qu'une autre
    # base de pluie ?", qui remontait un passage sur le signal atlantique).
    "plutot", "explique", "expliquer", "dire", "dis", "parle", "parler",
    "comment", "combien", "quoi", "est-ce", "peux", "peut-on", "veux",
    "montre", "montrer", "donne", "donner", "sait", "savoir", "concerne",
}

# Synonymes du domaine, appliques a la REQUETE seulement.
# Le corpus est scientifique et dit "precipitations" la ou un visiteur ecrit
# "pluie": sans cette table, "pluie" ne touche aucun passage (df=0, verifie).
# Table volontairement courte et verifiable: chaque entree est un synonyme
# reel, pas une association d'idees, qui n'ajouterait que du bruit.
SYNONYMES = {
    "pluie": ["precipitation"],
    "precipitation": ["pluie"],
    "pluviometrie": ["precipitation"],
    "lag": ["decalage"],
    "decalage": ["lag"],
    "sst": ["temperature", "oceanique"],
    "enso": ["nino"],
    "nino": ["enso"],
    "cluster": ["classification", "kmean"],
    "kmean": ["cluster", "classification"],
    "regroupement": ["classification", "cluster"],
    "seuil": ["sigma"],
    # Paires morphologiques que la desuffixation ne rapproche pas
    # ("detecte" et "detection" n'ont pas la meme racine tronquee), et qui
    # portent des questions centrales de la plateforme.
    "detecte": ["detection"],
    "detection": ["detecte"],
    "classifie": ["classification"],
    "classification": ["classifie"],
    "correle": ["correlation"],
    "correlation": ["correle"],
    "carte": ["spatiale", "cartographie"],
}

_SEPARATEURS = re.compile(r"[^a-z0-9]+")


def sans_accents(texte: str) -> str:
    brut = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in brut if not unicodedata.combining(c))


def normaliser(texte: str) -> str:
    """Minuscules, sans accents. Les chiffres sont conserves.

    'Nino 3.4' et 'CHIRPS' doivent rester trouvables: une normalisation qui
    supprimerait les nombres rendrait la moitie du corpus muette.
    """
    return sans_accents(str(texte or "")).lower()


def racine(mot: str) -> str:
    """Desuffixation minimale: pluriels et feminins courants.

    Volontairement timide: seule la marque du pluriel est retiree. Une regle
    plus large cassait l invariant qui fait tout marcher -- un mot et son
    pluriel DOIVENT donner la meme racine. La regle "es" produisait ainsi
    "plui" pour "pluies" mais "pluie" pour "pluie", et "pluie" ne retrouvait
    alors aucun passage.
    """
    if len(mot) <= 4:
        return mot
    for suffixe in ("s", "x"):
        if mot.endswith(suffixe) and len(mot) - len(suffixe) >= 4:
            return mot[: -len(suffixe)]
    return mot


def tokeniser(texte: str, garder_vides: bool = False) -> list:
    """Texte -> liste de racines indexables.

    Les chiffres isoles sont CONSERVES, contrairement aux lettres isolees:
    sans eux, "Nino 3.4", "Nino 3" et "Nino 4" deviendraient le meme jeton
    "nino" et la recherche ne saurait plus les distinguer.
    """
    mots = [m for m in _SEPARATEURS.split(normaliser(texte)) if m]
    return [racine(m) for m in mots
            if garder_vides or (m not in MOTS_VIDES
                                and (len(m) > 1 or m.isdigit()))]


def etendre_requete(requete: str) -> list:
    """Jetons de la requete, enrichis des synonymes du domaine.

    N'est JAMAIS applique au corpus: etendre les deux cotes ferait converger
    des passages qui n'ont en commun qu'un synonyme.
    """
    jetons = tokeniser(requete)
    etendus = list(jetons)
    for jeton in jetons:
        for synonyme in SYNONYMES.get(jeton, ()):
            racine_synonyme = racine(normaliser(synonyme))
            if racine_synonyme not in etendus:
                etendus.append(racine_synonyme)
    return etendus


def mots_bruts(texte: str) -> list:
    """Decoupage en mots d'affichage (accents et casse conserves)."""
    return str(texte or "").split()


def decouper(paragraphes, taille=180, recouvrement=40):
    """Regroupe des paragraphes en passages de ~`taille` mots.

    Le recouvrement evite qu'une phrase coupee en deux ne soit retrouvable
    dans aucun des deux passages. Un paragraphe plus long que `taille` n'est
    jamais scinde en son milieu: on prefere un passage un peu long a une
    phrase amputee.
    """
    passages, courant, n_mots = [], [], 0
    for para in paragraphes:
        mots = len(mots_bruts(para))
        if courant and n_mots + mots > taille:
            passages.append(" ".join(courant))
            # Repartir sur la fin du passage precedent, pas sur rien.
            queue, compte = [], 0
            for texte in reversed(courant):
                compte += len(mots_bruts(texte))
                queue.insert(0, texte)
                if compte >= recouvrement:
                    break
            courant, n_mots = list(queue), compte
        courant.append(para)
        n_mots += mots
    if courant:
        passages.append(" ".join(courant))
    return passages


def extrait(texte: str, maxi: int) -> tuple:
    """Tronque proprement a `maxi` caracteres, sur une frontiere de mot.

    Retourne (extrait, tronque). Couper en plein milieu d'un mot donnerait
    l'impression d'une donnee corrompue dans la bulle de chat.
    """
    texte = " ".join(str(texte or "").split())
    if len(texte) <= maxi:
        return texte, False
    coupe = texte[:maxi]
    espace = coupe.rfind(" ")
    if espace > maxi * 0.6:
        coupe = coupe[:espace]
    return coupe.rstrip(" ,;:") + " [...]", True
