"""Contexte de page transmis par le widget (Phase 7).

Le widget joint a chaque question ce que l'utilisateur a sous les yeux: la page
du dashboard ouverte et les filtres qu'il y a regles. Jarvis peut alors
resoudre "ce graphique", "cette phase", "l'evenement affiche" sans faire
repeter la question.

Ce contexte vient du NAVIGATEUR, donc de n'importe qui: il est traite comme
une donnee non fiable, au meme titre qu'un message. Trois consequences:

  - LISTE FERMEE. Seuls les champs declares ci-dessous, pour la page declaree,
    sont retenus. Tout le reste est ignore sans erreur: un widget d'une version
    anterieure ne doit pas faire echouer la question.
  - AUCUN TEXTE LIBRE. Chaque valeur est une enumeration, un entier borne, un
    booleen ou une date au format fixe. Une chaine arbitraire serait un canal
    d'injection de consignes vers le modele ("ignore tes regles et...").
  - PLAFOND DE TAILLE, applique par le schema de requete avant toute lecture.

Le contexte n'entre jamais dans l'historique de conversation: il decrit
l'ecran au moment de CETTE question, et le filtre aura change a la suivante.
"""
import re

from .tools.common import INDICES, METRIQUES, PHASES, PHASES_TOUTES

PAGES = ("Evenements", "Indices SST", "Teleconnexions", "Clustering", "Pipeline")

MAX_CONTEXT_CHARS = 2000

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --- validateurs: renvoient la valeur nettoyee, ou None si elle est rejetee --
def _enum(valeurs):
    def valider(v):
        return v if isinstance(v, str) and v in valeurs else None
    return valider


def _entier(mini, maxi):
    def valider(v):
        if isinstance(v, bool) or not isinstance(v, int):
            return None
        return v if mini <= v <= maxi else None
    return valider


def _booleen(v):
    return v if isinstance(v, bool) else None


def _date(v):
    return v if isinstance(v, str) and _DATE.match(v) else None


def _liste(valider_element, maxi):
    def valider(v):
        if not isinstance(v, (list, tuple)) or len(v) > maxi:
            return None
        propres = [valider_element(e) for e in v]
        if any(e is None for e in propres):
            return None
        return propres
    return valider


def _intervalle(mini, maxi):
    borne = _entier(mini, maxi)

    def valider(v):
        if not isinstance(v, (list, tuple)) or len(v) != 2:
            return None
        a, b = borne(v[0]), borne(v[1])
        if a is None or b is None or a > b:
            return None
        return [a, b]
    return valider


# --- champs admis, page par page --------------------------------------------
# Le libelle (2e element) est ce que lit le modele: il dit ce que represente le
# filtre, pas le nom technique de la cle Streamlit.
CHAMPS = {
    "Evenements": {
        "annees": (_intervalle(1900, 2100), "periode affichee"),
        "phases": (_liste(_enum(PHASES), 3), "phases affichees"),
        "evenement_date": (_date, "evenement selectionne sur la carte"),
    },
    "Indices SST": {
        "indices": (_liste(_enum(INDICES), len(INDICES)), "indices affiches"),
        "agregation": (_enum(("Mensuelle", "Annuelle", "Journaliere")),
                       "agregation temporelle"),
    },
    "Teleconnexions": {
        "phase": (_enum(PHASES_TOUTES), "phase de la carte de correlations"),
        "metrique": (_enum(tuple(METRIQUES)), "metrique de pluie"),
        "type_correlation": (_enum(("Pearson", "Spearman")), "coefficient"),
        "significatives_seulement": (_booleen, "filtre significatives seulement"),
        "p_value": (_enum(("p brute", "p neff (AR1)")), "p-value utilisee"),
        "phase_lag0": (_enum(PHASES_TOUTES), "phase du tableau lag 0"),
        "indices_series": (_liste(_enum(INDICES), len(INDICES)),
                           "indices traces dans les series"),
    },
    "Clustering": {
        "phase": (_enum(tuple(PHASES) + ("All_phases",)), "phase analysee"),
        "cluster": (_entier(0, 30), "cluster selectionne"),
        "metrique_barres": (_enum(("Nb evenements", "Precip max moy (mm)",
                                   "Couverture (%)", "Anomalie max moy")),
                            "metrique du diagramme en barres"),
    },
    "Pipeline": {
        "onglet": (_enum(("Donnees CHIRPS", "Pipeline d'analyse", "Donnees SST")),
                   "onglet ouvert"),
    },
}


def nettoyer(brut):
    """Ne garde du contexte recu que ce qui est declare et valide.

    Retourne {"page": ..., "filtres": {...}} ou None si rien d'exploitable.
    Ne leve jamais: un contexte douteux ne doit pas empecher de repondre.
    """
    if not isinstance(brut, dict):
        return None
    page = brut.get("page")
    if page not in CHAMPS:
        return None
    filtres_recus = brut.get("filtres")
    if not isinstance(filtres_recus, dict):
        filtres_recus = {}

    filtres = {}
    for nom, (valider, _) in CHAMPS[page].items():
        if nom not in filtres_recus:
            continue
        valeur = valider(filtres_recus[nom])
        if valeur is not None:
            filtres[nom] = valeur
    return {"page": page, "filtres": filtres}


def _formater_valeur(v) -> str:
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, list):
        return ", ".join(str(e) for e in v) if v else "aucun"
    return str(v)


def formater(contexte) -> str:
    """Bloc de texte joint a la question, a destination du modele.

    Balise explicite: le prompt systeme precise que ce bloc DECRIT l'ecran et
    ne contient jamais de consigne.
    """
    page = contexte["page"]
    lignes = ["<contexte_dashboard>", "Page ouverte : %s" % page]
    for nom, valeur in contexte["filtres"].items():
        libelle = CHAMPS[page][nom][1]
        lignes.append("- %s : %s" % (libelle, _formater_valeur(valeur)))
    lignes.append("</contexte_dashboard>")
    return "\n".join(lignes)


# Texte FIXE, ecrit ici: le client ne fait que demander le mode (un booleen),
# il ne peut rien glisser dans ce bloc.
# Les regles du style oral sont dans le prompt systeme (partie en cache).
CONSIGNE_ORALE = (
    "<mode_oral>\n"
    "La reponse sera lue a voix haute par ta voix de synthese.\n"
    "</mode_oral>")


def message_utilisateur(question: str, contexte, blocs_vue=(),
                        oral: bool = False) -> dict:
    """Tour "user" envoye a l'API: contexte, vue capturee, puis la question.

    Des blocs distincts plutot qu'une concatenation: la question reste
    intacte, et c'est elle seule qui entre dans l'historique. La question
    vient en DERNIER, apres les images, ce que recommande l'API pour les
    requetes multimodales.
    """
    blocs = []
    if oral:
        blocs.append({"type": "text", "text": CONSIGNE_ORALE})
    if contexte:
        blocs.append({"type": "text", "text": formater(contexte)})
    blocs.extend(blocs_vue or ())
    if not blocs:
        return {"role": "user", "content": question}
    blocs.append({"type": "text", "text": question})
    return {"role": "user", "content": blocs}
