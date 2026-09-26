"""Outil animate_sst_event: l'ocean pendant les 5 mois avant un evenement.

Le script 04 trouve ses correlations les plus fortes aux lags 3 a 5 mois:
l'ocean "prepare" la saison des mois a l'avance. Cette animation le montre
pour un evenement donne: anomalies de SST de J-150 au jour J, tous les 15
jours, sur la bande 36 S - 36 N.

Seuls les evenements de l'archive (scripts/17_build_jarvis_sst_evenements.py,
les plus intenses de chaque phase) sont animables: les 42 Go de SST brute ne
sont pas sur le serveur. Le resume donne au modele la moyenne de chaque
boite d'indice au debut et a la fin: il commente a partir de ces chiffres.
"""
from .. import cartes
from .common import (PHASES, SOURCE_INDICES, ToolInputError, arrondir,
                     champ_texte, resoudre_phase)

NAME = "animate_sst_event"
LABEL = "Animation de l'océan avant un événement"
PERMISSION = "public"
DATASETS = ()

DESCRIPTION = (
    "Affiche une ANIMATION des anomalies de temperature de surface de la mer "
    "(36S-36N) pendant les 150 jours qui precedent un evenement extreme, une "
    "image tous les 15 jours: on voit l'ocean evoluer avant la pluie. Seuls "
    "les ~30 evenements les plus intenses (10 par phase) sont animables: "
    "donne une date AAAA-MM-JJ, ou une phase seule pour le plus intense de "
    "cette phase, ou rien pour la liste. Le resume donne l'evolution de "
    "chaque boite d'indice (debut -> fin): commente a partir de lui."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Date AAAA-MM-JJ de l'evenement."},
        "phase": {"type": "string", "enum": PHASES,
                  "description": "Sans date: le plus intense de la phase."},
    },
}


def _catalogue():
    a = cartes.animations()
    return [{"date": d, "phase": p, "rang_catalogue": r}
            for d, p, r in zip(a["dates"], a["phases"], a["rangs"])]


def _choisir(params):
    a = cartes.animations()
    date = champ_texte(params, "date", maxi=10)
    if date:
        if date not in a["index"]:
            raise ToolInputError(
                "Pas d'animation pour le %s. Evenements animables: %s."
                % (date, ", ".join(sorted(a["dates"]))))
        return date
    if params.get("phase"):
        phase = resoudre_phase(params["phase"])
        candidats = [(r, d) for d, p, r in zip(a["dates"], a["phases"], a["rangs"])
                     if p == phase]
        if not candidats:
            raise ToolInputError("Aucun evenement animable pour %s." % phase)
        return min(candidats)[1]
    return None


def run(params, data, figures=None, session_id=""):
    try:
        date = _choisir(params)
    except cartes.CarteIndisponible as exc:
        raise ToolInputError(str(exc))
    if date is None:
        return {"evenements_animables": _catalogue(),
                "consigne": "Propose un evenement de cette liste, ou choisis-en un."}
    if figures is None:
        raise ToolInputError("L'affichage d'animations n'est pas disponible ici.")

    import numpy as np
    a = cartes.animations()
    i = a["index"][date]
    images = cartes.images_evenement(date)
    haut = float(np.nanpercentile(np.abs(images), 98))
    vlim = round(min(max(haut, 0.8), 3.0), 2)
    phase = a["phases"][i]
    spec = {
        "genre": "animation_sst", "type": "animate_sst_event",
        "titre": "L'océan avant l'événement du %s" % date,
        "sous_titre": "anomalies de SST · J-150 → J0, une image tous les 15 jours · %s"
                      % phase,
        "donnees": {"date": date, "vlim": vlim},
        "source": SOURCE_INDICES,
    }
    fig = figures.deposer(session_id, spec)
    boites = a["boites"][i]
    evolution = {}
    for k, nom in enumerate(a["noms_boites"]):
        debut, fin = float(boites[0][k]), float(boites[-1][k])
        evolution[nom] = {"J-150": arrondir(debut, 2), "J0": arrondir(fin, 2),
                          "variation": arrondir(fin - debut, 2)}
    rechauffe = sorted(evolution, key=lambda n: -(evolution[n]["variation"] or 0))
    return {
        "figure_id": fig.id, "carte": True,
        "titre": spec["titre"], "sous_titre": spec["sous_titre"],
        "date": date, "phase": phase, "rang_catalogue": a["rangs"][i],
        "echelle_couleurs_degC": [-vlim, vlim],
        "anomalies_par_boite_degC": evolution,
        "plus_fort_rechauffement": rechauffe[0],
        "plus_fort_refroidissement": rechauffe[-1],
        "rappel": ("un seul evenement ne prouve rien: les correlations du script "
                   "04 portent sur 41 annees; cette animation illustre, elle ne "
                   "demontre pas"),
        "consigne": ("L'animation s'affiche en grand et tourne en boucle. Dis ce "
                     "qui change dans l'ocean entre J-150 et J0, a partir des "
                     "chiffres par boite."),
        "source": SOURCE_INDICES,
    }
