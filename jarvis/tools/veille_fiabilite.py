"""Outil get_bulletin_reliability: le carnet de fiabilite de la veille pre-saison.

"Le bulletin s'est-il trompe en 2020 ?", "combien de fausses alertes ?",
"compare 2020 et 2021": confronte les bulletins retrospectifs (chacun
n'utilise que ce qui etait connu en avril de son annee) a ce qui s'est
reellement passe. Lecture seule, rien n'est recalcule.
"""
from .common import ToolInputError, champ_entier

NAME = "get_bulletin_reliability"
LABEL = "Carnet de fiabilité de la veille"
PERMISSION = "public"
DATASETS = ()

DESCRIPTION = (
    "CARNET DE FIABILITE de la veille pre-saison: ce que les bulletins "
    "retrospectifs (1998-2023, chacun limite a ce qui etait connu en avril) "
    "auraient annonce, confronte a la realite CHIRPS. Sans parametre: bilan "
    "global (detections, fausses alertes, saisons extremes manquees, taux de "
    "detection, AUC, Brier, sort de chaque inondation documentee). year: le "
    "detail d'une saison ('le bulletin s'est-il trompe en 2020 ?'). "
    "compare_years: deux saisons cote a cote. A utiliser pour toute question "
    "sur la fiabilite, la credibilite ou les erreurs passees du bulletin; "
    "cite les chiffres, y compris les echecs."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "year": {"type": "integer", "description": "Detail d'une saison verifiee."},
        "compare_years": {"type": "array", "items": {"type": "integer"},
                          "description": "Deux saisons a comparer, ex. [2020, 2021]."},
    },
}


def run(params, data):
    from veille import fiabilite

    comparer = params.get("compare_years")
    if comparer is not None:
        if not isinstance(comparer, list) or len(comparer) != 2:
            raise ToolInputError("compare_years attend exactement deux annees, ex. [2020, 2021].")
        try:
            a, b = (int(x) for x in comparer)
        except (TypeError, ValueError):
            raise ToolInputError("compare_years: deux annees entieres.")
        return {"comparaison": fiabilite.comparer(a, b),
                "source": "Bulletins de veille pre-saison ClimatSen"}

    carnet = fiabilite.carnet()
    if not carnet.get("disponible"):
        raise ToolInputError("Aucun bulletin retrospectif verifie n'est disponible.")
    annee = champ_entier(params, "year", mini=1981, maxi=2100)
    if annee is not None:
        ligne = fiabilite.saison(annee)
        if ligne is None:
            raise ToolInputError("Pas de bulletin verifie pour %d (periode %d-%d)."
                                 % (annee, carnet["periode"][0], carnet["periode"][1]))
        return {"saison": ligne, "bilan_global": carnet["niveau_de_risque"],
                "lecture": carnet["lecture"],
                "source": "Bulletins de veille pre-saison ClimatSen"}
    sortie = dict(carnet)
    sortie.pop("saisons")          # le detail annee par annee: parametre year
    sortie["source"] = "Bulletins de veille pre-saison ClimatSen"
    return sortie
