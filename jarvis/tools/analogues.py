"""Outil find_analog_years: les annees qui ressemblent a une annee donnee.

"Quelles annees passees ressemblent a 2020 cote ocean, et qu'ont-elles
donne ?" L'etat oceanique d'une annee est la moyenne des indices SST sur les
mois qui PRECEDENT la phase (avril-juin pour la pleine saison): on le connait
avant la saison. Les analogues sont les annees les plus proches de cet etat
(distance sur indices standardises).

Garde-fou central: le resultat porte TOUJOURS la competence mesuree de la
methode (validation croisee sur 1983-2023). Une liste d'analogues se lit
spontanement comme une prevision; si la methode n'a pas de pouvoir
predictif, le modele doit le dire, chiffre a l'appui.
"""
from .. import analyses
from .analyse_teleconnexions import BASSINS
from .common import (INDICES, METRIQUES, PHASES, SOURCE_CORRELATIONS,
                     SOURCE_INDICES, ToolInputError, champ_entier, champ_enum,
                     resoudre_indice, resoudre_phase)

NAME = "find_analog_years"
LABEL = "Recherche d'années analogues"
PERMISSION = "public"
DATASETS = ()

JEUX = {"tous": INDICES, "atlantique": BASSINS["Atlantique"],
        "pacifique": BASSINS["Pacifique (ENSO)"], "indien": BASSINS["Ocean Indien"]}

DESCRIPTION = (
    "Trouve les annees ANALOGUES d'une annee de reference (1983-2023): celles "
    "dont l'etat oceanique avant la phase (moyenne des indices SST sur les "
    "mois qui precedent, ex. avril-juin pour la pleine saison) est le plus "
    "proche. Donne pour chacune ce qu'a produit la saison (pluie max, nombre "
    "d'evenements, rang percentile), la moyenne des analogues, la valeur "
    "reelle de l'annee de reference, ET la competence mesuree de la methode "
    "(validation croisee): rapporte-la toujours, c'est elle qui dit si les "
    "analogues ont une valeur predictive. indices: 'tous', 'atlantique', "
    "'pacifique', 'indien', ou une liste d'indices."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "year": {"type": "integer", "description": "Annee de reference (1983-2023)."},
        "phase": {"type": "string", "enum": PHASES, "description": "Phase de saison."},
        "indices": {"description": "'tous' (defaut), 'atlantique', 'pacifique', "
                                   "'indien', ou liste d'indices SST.",
                    "anyOf": [{"type": "string"},
                              {"type": "array", "items": {"type": "string"}}]},
        "count": {"type": "integer", "description": "Nombre d'analogues (3 a 8, defaut 5)."},
        "months_before": {"type": "integer",
                          "description": "Mois precedant la phase pris en compte "
                                         "(1 a 6, defaut 3)."},
        "metric": {"type": "string", "enum": sorted(METRIQUES),
                   "description": "Metrique de bilan. Defaut: max_precip."},
    },
    "required": ["year", "phase"],
}


def _indices(valeur):
    if valeur is None:
        return list(INDICES)
    if isinstance(valeur, str):
        cle = valeur.strip().lower()
        if cle in JEUX:
            return list(JEUX[cle])
        return [resoudre_indice(valeur)]
    if isinstance(valeur, (list, tuple)) and 1 <= len(valeur) <= len(INDICES):
        return sorted({resoudre_indice(v) for v in valeur}, key=INDICES.index)
    raise ToolInputError("indices: 'tous', 'atlantique', 'pacifique', 'indien' "
                         "ou une liste d'indices SST.")


def run(params, data):
    annee = champ_entier(params, "year", mini=analyses.ANNEE_MIN,
                         maxi=analyses.ANNEE_MAX)
    if annee is None:
        raise ToolInputError("year est requis (%d-%d)."
                             % (analyses.ANNEE_MIN, analyses.ANNEE_MAX))
    if not params.get("phase"):
        raise ToolInputError("phase est requise: %s." % ", ".join(PHASES))
    phase = resoudre_phase(params["phase"])
    if phase not in PHASES:
        raise ToolInputError("Choisis une phase precise: %s." % ", ".join(PHASES))
    indices = _indices(params.get("indices"))
    nombre = champ_entier(params, "count", mini=3, maxi=8, defaut=5)
    avant = champ_entier(params, "months_before", mini=1, maxi=6, defaut=3)
    metrique = champ_enum(params, "metric", sorted(METRIQUES), defaut="max_precip")
    try:
        res = analyses.analogues(phase, annee, indices, nombre, avant, metrique)
        comp = analyses.competence_analogues(phase, indices, nombre, avant, metrique)
    except analyses.AnalyseIndisponible as exc:
        raise ToolInputError(str(exc))

    if comp.get("calculable"):
        utile = comp["p_neff"] is not None and comp["p_neff"] < 0.05 and comp["r_prevu_observe"] > 0
        verdict = ("la methode a un pouvoir predictif significatif" if utile else
                   "la methode N'A PAS de pouvoir predictif demontre: les analogues "
                   "decrivent des ressemblances, pas une prevision")
    else:
        verdict = "competence non calculable"
    return {
        "annee_reference": annee, "phase": phase, "metrique": metrique,
        "indices_utilises": indices, "mois_avant_la_phase": avant,
        **res,
        "competence_de_la_methode": dict(comp, verdict=verdict),
        "lecture": ("etat_standardise en ecarts-types (z-score 1983-2023); "
                    "rang_percentile = part des annees ou la metrique etait plus "
                    "faible. Plus la distance est petite, plus l'annee ressemble."),
        "source": SOURCE_INDICES + " ; " + SOURCE_CORRELATIONS,
    }
