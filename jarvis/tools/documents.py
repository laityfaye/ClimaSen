"""Outil search_documents: recherche dans le memoire et l'article (Phase 3).

Complement des quatre outils de donnees: ceux-la disent COMBIEN, celui-ci dit
POURQUOI et COMMENT -- choix de CHIRPS, seuil de detection, correction AR1,
interpretation des resultats.

Chaque passage est rendu avec sa reference de section, pour que Jarvis cite au
lieu d'affirmer. L'extrait est plafonne: le memoire n'est pas publie et le
widget est public.
"""
from ..knowledge import bm25
from ..knowledge.texte import extrait as tronquer
from .common import ToolInputError, arrondir, champ_entier, champ_enum, champ_texte

NAME = "search_documents"
LABEL = "Consultation du mémoire et de l’article"
PERMISSION = "public"
DATASETS = ("knowledge",)

DESCRIPTION = (
    "Recherche des passages dans le memoire de master et l article "
    "scientifique qui fondent la plateforme. A utiliser pour toute question "
    "de METHODE, de JUSTIFICATION ou d INTERPRETATION: pourquoi le produit "
    "CHIRPS a ete retenu, comment les evenements extremes sont detectes, "
    "pourquoi la saison est decoupee en trois phases, ce que signifie la "
    "correction AR1, comment les resultats sont interpretes. "
    "IMPORTANT: passe des MOTS-CLES, pas la question complete de "
    "l utilisateur. 'CHIRPS choix donnees precipitation' fonctionne, "
    "'Pourquoi avez-vous choisi CHIRPS plutot qu autre chose ?' beaucoup "
    "moins bien. Pour un chiffre de resultat, utilise les outils de donnees: "
    "ils lisent les valeurs a jour, le texte peut citer un calcul anterieur."
)

EXTRAIT_MAX = 600   # caracteres par passage
LIMITE_MAX = 5

SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Mots-cles a rechercher (2 a 8 termes). Les "
                           "synonymes courants du domaine sont geres: 'pluie' "
                           "retrouve 'precipitations', 'lag' retrouve "
                           "'decalage'.",
        },
        "document": {
            "type": "string",
            "enum": ["memoire", "article"],
            "description": "Restreindre a un document. Omettre pour chercher "
                           "dans les deux (recommande).",
        },
        "limit": {
            "type": "integer",
            "description": "Nombre de passages renvoyes (1 a 5, defaut 3).",
        },
    },
    "required": ["query"],
}

NOTE = (
    "Cite le document et la section quand tu utilises un passage. Ces textes "
    "expliquent la demarche; pour une valeur chiffree a jour, utilise les "
    "outils de donnees."
)


def run(params, data):
    corpus = data["knowledge"]
    passages = corpus["passages"]
    index = corpus["index"]

    requete = champ_texte(params, "query", maxi=200)
    if not requete:
        raise ToolInputError(
            "Le parametre query est requis: donne 2 a 8 mots-cles decrivant "
            "ce que tu cherches."
        )
    document = champ_enum(params, "document", ["memoire", "article"])
    limite = champ_entier(params, "limit", mini=1, maxi=LIMITE_MAX, defaut=3)

    titres = {d["cle"]: d["titre"] for d in corpus["documents"]}
    resultats = bm25.rechercher(index, passages, requete, limite, document)

    if not resultats:
        return {
            "requete": requete,
            "n_resultats": 0,
            "passages": [],
            "message": (
                "Aucun passage ne correspond a ces mots-cles. Reformule avec "
                "d autres termes, ou dis que le document ne traite pas ce point."
            ),
            "documents_disponibles": _catalogue(corpus),
            "note": NOTE,
        }

    trouves = []
    for passage, score in resultats:
        texte_extrait, tronque = tronquer(passage["texte"], EXTRAIT_MAX)
        trouves.append({
            "document": passage["document"],
            "document_titre": titres.get(passage["document"], passage["document"]),
            "section": passage["section"],
            "citation": "%s, %s" % (
                "Memoire" if passage["document"] == "memoire" else "Article",
                passage["section"],
            ),
            "extrait": texte_extrait,
            "extrait_tronque": tronque,
            "score": arrondir(score, 2),
        })

    return {
        "requete": requete,
        "filtre_document": document,
        "n_resultats": len(trouves),
        "passages": trouves,
        "documents_disponibles": _catalogue(corpus),
        "note": NOTE,
    }


def _catalogue(corpus):
    return [{"cle": d["cle"], "titre": d["titre"], "auteur": d["auteur"],
             "n_passages": d["n_passages"]}
            for d in corpus["documents"]]
