"""Outil make_custom_figure: un visuel qui n'existe pas encore.

Dernier recours, apres make_figure (types fermes) et show_map: le modele
decrit la figure dans une grammaire bornee (jeu du catalogue, filtres,
agregation, marque) et le moteur jarvis/rapports/moteur_figures la valide,
la calcule et la rend. Aucun code n'est fourni par le modele; une demande
statistiquement absurde (moyenne de rangs, nuage de 4 points...) est refusee
avec la raison, que le modele peut corriger.
"""
from ..rapports import moteur_figures
from .common import ToolInputError

NAME = "make_custom_figure"
LABEL = "Construction d'un visuel à la demande"
PERMISSION = "public"
DATASETS = ()


def _catalogue_court():
    return "; ".join("%s (%s)" % (nom, ", ".join(j["colonnes"]))
                     for nom, j in moteur_figures.catalogue()["jeux"].items())


DESCRIPTION = (
    "Construit un GRAPHIQUE, une CARTE ou un TABLEAU qui n'existe pas dans make_figure ni "
    "show_map, a partir des donnees de la plateforme (n'utilise cet outil qu'apres avoir "
    "verifie que make_figure / show_map ne couvrent pas la demande). Grammaire: dataset, "
    "filters [{column, op (=, !=, <, <=, >, >=, in, contains), value}], join {dataset} "
    "(jointures autorisees: departements ou arrondissements avec ehcvm_*, communes avec "
    "arrondissements, evenements avec departements; colonnes jointes nommees "
    "'<jeu>.<colonne>'), mark (barres, barres_horizontales: x categorie + y valeur, ou "
    "group_by + measure (colonne ou 'comptage') + aggregation; courbes: x annee/mois + y, "
    "series optionnel; nuage: x, y, label; boites: group_by + y; carte: y sur departements "
    "ou arrondissements, highlight [noms]; carte_chaleur: correlations seulement, x, series, "
    "y; tableau: columns), aggregation (somme, moyenne, mediane, min, max, comptage: "
    "verifiee selon la nature de la colonne), sort, top, title et caption SANS chiffres. "
    "Titre, unite, periode et source sont ajoutes automatiquement. Jeux et colonnes: %s. "
    "Le resultat porte un resume chiffre: commente a partir de lui seulement."
    % _catalogue_court()
)

SCHEMA = {
    "type": "object",
    "properties": {
        "dataset": {"type": "string", "enum": sorted(moteur_figures.catalogue()["jeux"])},
        "filters": {"type": "array", "items": {"type": "object"}},
        "join": {"type": "object"},
        "mark": {"type": "string", "enum": list(moteur_figures.MARQUES)},
        "x": {"type": "string"}, "y": {"type": "string"}, "series": {"type": "string"},
        "group_by": {"type": "string"}, "measure": {"type": "string"},
        "label": {"type": "string"},
        "aggregation": {"type": "string", "enum": list(moteur_figures.AGREGATIONS)},
        "columns": {"type": "array", "items": {"type": "string"}},
        "highlight": {"type": "array", "items": {"type": "string"}},
        "sort": {"type": "string", "enum": ["asc", "desc"]},
        "top": {"type": "integer"},
        "title": {"type": "string"}, "caption": {"type": "string"},
    },
    "required": ["dataset", "mark"],
}


def run(params, data, figures=None, session_id=""):
    try:
        r = moteur_figures.executer(params)
    except moteur_figures.SpecInvalide as exc:
        raise ToolInputError(str(exc))
    commun = {"titre": r["titre"], "legende": r["legende"], "unite": r["unite"],
              "periode": r["periode"], "source": r["source"], "statut": r["statut"],
              "resume": r["resume"],
              "consigne": "Commente a partir du resume, sans autre chiffre. Rappelle la "
                          "reserve de la legende s'il y en a une (donnee provisoire, "
                          "correlation simple)."}
    if r["genre"] == "tableau":
        commun.update({"tableau": {"colonnes": r["colonnes"], "lignes": r["lignes"]},
                       "affichage": "presente ce tableau en Markdown, tel quel"})
        return commun
    if figures is None:
        raise ToolInputError("L'affichage de figures n'est pas disponible ici.")
    spec = dict(r["spec"])
    spec.update({"type": "make_custom_figure", "titre": r["titre"],
                 "sous_titre": "%s · %s · %s" % (r["unite"], r["periode"], r["source"]),
                 "source": r["source"]})
    figure = figures.deposer(session_id, spec)
    commun.update({"figure_id": figure.id, "carte": spec["genre"] == "carte_zones",
                   "sous_titre": spec["sous_titre"], "affichee": True})
    return commun
