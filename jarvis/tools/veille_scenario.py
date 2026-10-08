"""Outil explore_ocean_scenario: "et si l'ocean etait different ?"

Perturbe l'etat oceanique novembre-avril d'un bulletin (+/- x degC,
uniforme dans une ou plusieurs boites d'indices) et recalcule ce que la
projection en dirait: probabilite experimentale, configuration du memoire la
plus proche, annees analogues, famille d'oceans des saisons extremes. Calcul en numpy pur sur le kit du bulletin
(veille.artefacts), quelques millisecondes, aucun code du modele.

Garde-fou: c'est une EXPLORATION DE SENSIBILITE de la methode, pas une
prevision. La projection elle-meme n'a pas de competence demontree en
prevision reelle; le resultat le rappelle toujours.
"""
from .common import ToolInputError, champ_entier

NAME = "explore_ocean_scenario"
LABEL = "Exploration d'un scénario océanique"
PERMISSION = "public"
DATASETS = ()

MAX_DELTA = 2.0

DESCRIPTION = (
    "SCENARIO 'ET SI' de la veille pre-saison: perturbe l'etat oceanique "
    "novembre-avril d'un bulletin (changes: {boite: delta en degC, entre -2 et "
    "+2}) et montre ce qui change dans la projection: probabilite "
    "experimentale, configuration du memoire la plus proche, annees "
    "analogues, ressemblance aux familles d'oceans des saisons extremes (A: "
    "1999/2000/2012, B: 2005/2010/2020; descriptif). Boites: TNA, TSA, ATL3, AMO, Nino34, Nino12, Nino4, "
    "IOD_ouest, IOD_est, IOBM. Exemple: 'et si l'Atlantique tropical nord "
    "etait 0,5 degC plus chaud ?' -> changes {TNA: 0.5}. year: saison du "
    "bulletin (defaut: la plus recente qui a un kit). Presente TOUJOURS le "
    "resultat comme une exploration de sensibilite de la methode, jamais "
    "comme une prevision."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "changes": {"type": "object",
                    "description": "{boite: delta degC}, ex. {\"TNA\": 0.5, \"Nino34\": -1}.",
                    "additionalProperties": {"type": "number"}},
        "year": {"type": "integer", "description": "Saison du bulletin (defaut: la plus recente)."},
    },
    "required": ["changes"],
}


def _annees_avec_kit():
    from veille import artefacts
    if not artefacts.DOSSIER_KITS.is_dir():
        return []
    annees = []
    for f in artefacts.DOSSIER_KITS.glob("kit_*.npz"):
        try:
            annees.append(int(f.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return sorted(annees)


def run(params, data):
    from veille import artefacts

    changes = params.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise ToolInputError("changes est requis: {boite: delta}, ex. {\"TNA\": 0.5}.")
    deltas = {}
    for nom, v in changes.items():
        if nom not in artefacts.BOITES_SCENARIO:
            raise ToolInputError("Boite inconnue: %r. Valeurs: %s."
                                 % (nom, ", ".join(artefacts.BOITES_SCENARIO)))
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ToolInputError("Le delta de %s doit etre un nombre (degC)." % nom)
        if abs(v) > MAX_DELTA:
            raise ToolInputError("Delta de %s hors bornes: %+.1f degC (maximum %.0f)."
                                 % (nom, v, MAX_DELTA))
        deltas[nom] = v

    dispo = _annees_avec_kit()
    if not dispo:
        raise ToolInputError("Aucun kit de scenario n'a ete produit "
                             "(scripts/20_veille_presaison.py --kit).")
    annee = champ_entier(params, "year", mini=1984, maxi=2100)
    par_defaut = annee is None
    if par_defaut:
        annee = dispo[-1]
    if annee not in dispo:
        raise ToolInputError("Pas de kit de scenario pour %d. Saisons disponibles: %s."
                             % (annee, ", ".join(str(a) for a in dispo)))

    kit = artefacts.charger_kit(annee)
    avant = artefacts.projeter(kit, kit["etat"].astype("float64"))
    etat, pixels = artefacts.perturber(kit, deltas)
    apres = artefacts.projeter(kit, etat)

    def top(r):
        k = max(r["ressemblance_memoire"], key=r["ressemblance_memoire"].get)
        return {"configuration": k, "correlation": round(r["ressemblance_memoire"][k], 3)}

    def ana(r):
        return [{"annee": a, "correlation": round(c, 3)} for a, c in r["analogues"]]

    def fam(r):
        f = r.get("familles_extremes")
        if not f:
            return None
        return {"plus_proche": f["plus_proche"], "seuil": f["seuil"],
                "familles": [{"code": x["code"], "nom": x["nom"],
                              "membres_utilises": x["membres_utilises"],
                              "correlation": x["correlation"]} for x in f["familles"]]}

    pa, pb = avant["probabilite_experimentale"], apres["probabilite_experimentale"]
    sortie = {
        "saison": annee,
        "perturbation_degC": deltas,
        "zones": {k: artefacts.LIBELLES_BOITES[k] for k in deltas},
        "pixels_modifies": pixels,
        "avant": {"probabilite_experimentale": round(pa, 3), "configuration": top(avant),
                  "analogues": ana(avant)},
        "apres": {"probabilite_experimentale": round(pb, 3), "configuration": top(apres),
                  "analogues": ana(apres)},
        "variation_probabilite_points": round(100 * (pb - pa), 1),
        "ressemblances_apres": {str(k): round(v, 3)
                                for k, v in apres["ressemblance_memoire"].items()},
        "garde_fou": ("Exploration de SENSIBILITE de la methode de projection, pas une "
                      "prevision: la projection n'a pas de competence demontree en "
                      "prevision reelle (AUC ~0,53). Une perturbation uniforme dans une "
                      "boite est une simplification: l'ocean reel ne change pas ainsi."),
        "source": "Kit de scenario du bulletin %d (veille pre-saison ClimatSen)" % annee,
    }
    fa, fb = fam(avant), fam(apres)
    if fa is not None:
        sortie["avant"]["familles_extremes"] = fa
        sortie["apres"]["familles_extremes"] = fb
        sortie["changement_famille"] = fa["plus_proche"] != fb["plus_proche"]
        sortie["garde_fou"] += (" La ressemblance aux familles d'oceans extremes est "
                                "descriptive: changer de famille ne rend pas la saison "
                                "plus ou moins extreme.")
    else:
        sortie["familles_extremes"] = ("non disponible pour ce kit (produit avant l'ajout des "
                                       "familles; relancer 20_veille_presaison.py --familles)")
    if par_defaut:
        # Sans annee demandee, on part du kit le plus recent: ce n'est pas
        # forcement la saison a venir (son ocean n'est peut-etre pas observe).
        sortie["attention"] = ("Aucune saison demandee: scenario applique a l'ocean de la "
                               "saison %d, la plus recente disponible. Dis-le a "
                               "l'utilisateur." % annee)
    return sortie
