"""Recherche lexicale BM25 sur un index pre-construit.

Pourquoi BM25 plutot que des embeddings: le corpus fait 28 000 mots, soit
~230 passages. Un index inverse tient dans 1 Mo, repond en une fraction de
milliseconde et ne demande ni cle d'API supplementaire, ni modele local (qui
ajouterait des centaines de Mo de RAM a un service qui en occupe deja 187).

Le vocabulaire des questions est celui du texte -- teleconnexion, CHIRPS,
Nino 3.4 -- ce qui est le cas favorable du lexical. Et quand une formulation
echoue, la boucle d'outils permet deja au modele de relancer la recherche avec
d'autres termes: le rattrapage est architectural, pas statistique.

Si le rappel se revelait insuffisant a l'usage, l'ajout d'embeddings ne
toucherait que ce module: la structure de l'index et l'outil resteraient.
"""
import math

from .texte import etendre_requete, normaliser, tokeniser

K1 = 1.5    # saturation de la frequence de terme
B = 0.75    # normalisation par la longueur du passage
BONUS_EXPRESSION = 2.0  # prime quand la requete apparait telle quelle
POIDS_SECTION = 3       # un terme du titre de section compte triple
SEUIL_DOUBLON = 0.75    # recouvrement de vocabulaire au-dela duquel deux
                        # passages sont juges redondants


def jetons_passage(passage: dict) -> list:
    """Jetons indexes: le texte, plus le titre de section pondere.

    Le titre est un signal bien plus sur que le corps du passage: une section
    intitulee "2.2 Methodologie de detection des evenements extremes" traite
    de cela, la ou une conclusion peut citer les memes mots en passant. Sans
    cette ponderation, la conclusion remontait devant la methodologie.
    """
    jetons = tokeniser(passage.get("texte", ""))
    jetons += tokeniser(passage.get("section", "")) * POIDS_SECTION
    return jetons


def construire(passages) -> dict:
    """passages: liste de dicts portant 'texte' et 'section'. Retourne l'index."""
    postings = {}
    longueurs = []
    for i, passage in enumerate(passages):
        jetons = jetons_passage(passage)
        longueurs.append(len(jetons))
        frequences = {}
        for jeton in jetons:
            frequences[jeton] = frequences.get(jeton, 0) + 1
        for jeton, tf in frequences.items():
            postings.setdefault(jeton, []).append([i, tf])
    n = len(passages)
    return {
        "n": n,
        "longueurs": longueurs,
        "longueur_moyenne": (sum(longueurs) / n) if n else 0.0,
        "postings": postings,
    }


def _idf(n: int, df: int) -> float:
    # Forme dite "BM25+ idf": toujours positive, contrairement a la forme
    # classique qui devient negative pour un terme present dans plus de la
    # moitie des passages -- un terme frequent penaliserait alors le score.
    return math.log(1.0 + (n - df + 0.5) / (df + 0.5))


def scorer(index: dict, requete: str) -> dict:
    """Retourne {indice_passage: score} pour les passages touches."""
    jetons = etendre_requete(requete)
    if not jetons:
        return {}
    n = index["n"]
    longueurs = index["longueurs"]
    moyenne = index["longueur_moyenne"] or 1.0
    postings = index["postings"]

    scores = {}
    for jeton in set(jetons):
        liste = postings.get(jeton)
        if not liste:
            continue
        idf = _idf(n, len(liste))
        for indice, tf in liste:
            dl = longueurs[indice] or 1
            denominateur = tf + K1 * (1.0 - B + B * dl / moyenne)
            scores[indice] = scores.get(indice, 0.0) + idf * tf * (K1 + 1.0) / denominateur
    return scores


def _redondant(passage: dict, retenus: list) -> bool:
    """Le memoire et l'article partagent des paragraphes quasi identiques.

    Renvoyer deux fois le meme texte sous deux references gaspille le contexte
    et donne a la reponse l'air de reciter. On garde le mieux classe.
    """
    jetons = set(tokeniser(passage.get("texte", "")))
    if not jetons:
        return False
    for autre in retenus:
        autres_jetons = set(tokeniser(autre.get("texte", "")))
        if not autres_jetons:
            continue
        commun = len(jetons & autres_jetons)
        recouvrement = commun / min(len(jetons), len(autres_jetons))
        if recouvrement >= SEUIL_DOUBLON:
            return True
    return False


def rechercher(index: dict, passages, requete: str, limite: int = 3,
               document: str = None, dedupliquer: bool = True) -> list:
    """Retourne les meilleurs passages: [(passage, score), ...]."""
    scores = scorer(index, requete)
    if not scores:
        return []

    # Prime d'expression exacte: une requete retrouvee mot pour mot vaut mieux
    # qu'une somme de termes disperses dans le passage.
    requete_normalisee = " ".join(normaliser(requete).split())
    if len(requete_normalisee) >= 8:
        for indice in list(scores):
            titre = " ".join(normaliser(passages[indice].get("section", "")).split())
            corps = " ".join(normaliser(passages[indice]["texte"]).split())
            if requete_normalisee in titre:
                # Un titre de section qui contient la requete entiere designe
                # la section dediee au sujet, pas une mention de passage.
                scores[indice] += BONUS_EXPRESSION * 2
            elif requete_normalisee in corps:
                scores[indice] += BONUS_EXPRESSION

    classes = sorted(scores.items(),
                     key=lambda couple: (-couple[1], couple[0]))

    resultats, retenus = [], []
    for indice, score in classes:
        passage = passages[indice]
        if document and passage.get("document") != document:
            continue
        if dedupliquer and _redondant(passage, retenus):
            continue
        resultats.append((passage, score))
        retenus.append(passage)
        if len(resultats) >= limite:
            break
    return resultats
