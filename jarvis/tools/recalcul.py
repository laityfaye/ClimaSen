"""Outil recompute_correlation: recalculer une teleconnexion a la demande.

Repond aux questions que les CSV figes ne couvrent pas: "et sans 2020 ?",
"le signal tient-il sur 1983-2002 ET sur 2003-2023 ?", "repose-t-il sur une
seule annee ?". Le calcul passe par jarvis/analyses.py, donc par les
fonctions memes du script 04: sur la periode complete, le resultat est
identique au CSV.

Aucun code n'est fourni par le modele: il choisit une analyse dans une liste
fermee et ses parametres, bornes ici.
"""
from .. import analyses
from .common import (INDICES, METRIQUES, PHASES_TOUTES, SOURCE_CORRELATIONS,
                     ToolInputError, arrondir, champ_bool, champ_entier,
                     champ_enum, etoiles, resoudre_indice, resoudre_phase)

NAME = "recompute_correlation"
LABEL = "Recalcul d'une corrélation"
PERMISSION = "public"
DATASETS = ()

ANALYSES = ["correlation", "comparer_periodes", "sensibilite_annees"]
LAG_MAX = 12
MAX_EXCLUES = 15

DESCRIPTION = (
    "RECALCULE une correlation indice SST / pluies extremes avec la methode "
    "exacte du script 04 (serie annuelle par phase, detrend lineaire, "
    "Pearson + Spearman, p corrigee AR1). A utiliser quand la question sort "
    "des resultats publies: analysis=correlation avec exclude_years (ex. "
    "'sans 2020') et/ou period [debut, fin]; analysis=comparer_periodes "
    "coupe la serie en deux a split_year et compare les deux moities "
    "(stabilite du signal dans le temps); analysis=sensibilite_annees retire "
    "chaque annee a tour de role et dit quelles annees portent le resultat. "
    "Le resultat donne toujours la valeur de reference (periode complete, "
    "egale au CSV publie) pour comparer. figure=true affiche le nuage de "
    "points annee par annee."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string", "enum": ANALYSES,
                     "description": "Defaut: correlation."},
        "index": {"type": "string", "enum": INDICES, "description": "Indice SST."},
        "phase": {"type": "string", "enum": PHASES_TOUTES,
                  "description": "Phase de saison."},
        "lag": {"type": "integer",
                "description": "Decalage en mois (0 a 12). Le script 04 publie 0 a 5."},
        "metric": {"type": "string", "enum": sorted(METRIQUES),
                   "description": "Metrique de pluie. Defaut: max_precip."},
        "exclude_years": {"type": "array", "items": {"type": "integer"},
                          "description": "Annees a retirer (15 au plus)."},
        "period": {"type": "array", "items": {"type": "integer"},
                   "description": "[annee_debut, annee_fin] dans 1983-2023."},
        "split_year": {"type": "integer",
                       "description": "comparer_periodes: premiere annee de la "
                                      "seconde moitie (defaut 2003)."},
        "figure": {"type": "boolean",
                   "description": "Afficher le nuage de points (defaut false)."},
    },
    "required": ["index", "phase", "lag"],
}

AVERTISSEMENT = ("correlation != causalite; p_neff corrigee AR1; un sous-"
                 "ensemble d'annees a moins de puissance statistique")


def _annees(params):
    debut, fin = analyses.ANNEE_MIN, analyses.ANNEE_MAX
    periode = params.get("period")
    if periode is not None:
        if (not isinstance(periode, (list, tuple)) or len(periode) != 2):
            raise ToolInputError("period doit etre [annee_debut, annee_fin].")
        try:
            debut, fin = int(periode[0]), int(periode[1])
        except (TypeError, ValueError):
            raise ToolInputError("period doit contenir deux annees entieres.")
        if not (analyses.ANNEE_MIN <= debut < fin <= analyses.ANNEE_MAX):
            raise ToolInputError("period doit etre comprise dans %d-%d, debut < fin."
                                 % (analyses.ANNEE_MIN, analyses.ANNEE_MAX))
    exclues = params.get("exclude_years") or []
    if not isinstance(exclues, (list, tuple)) or len(exclues) > MAX_EXCLUES:
        raise ToolInputError("exclude_years: une liste de %d annees au plus." % MAX_EXCLUES)
    try:
        exclues = sorted({int(a) for a in exclues})
    except (TypeError, ValueError):
        raise ToolInputError("exclude_years ne doit contenir que des annees entieres.")
    annees = [a for a in range(debut, fin + 1) if a not in exclues]
    return annees, (debut, fin), exclues


def _resume(r):
    if not r.get("calculable"):
        return {"calculable": False, "n": r.get("n"), "raison": r.get("raison")}
    return {
        "n_annees": r["n"], "n_eff": r["n_eff"],
        "pearson_r": arrondir(r["pearson_r"], 3),
        "p_neff": arrondir(r["pearson_p_neff"], 4),
        "significativite": etoiles(r["pearson_p_neff"]) or "non significatif",
        "spearman_r": arrondir(r["spearman_r"], 3),
        "spearman_p_neff": arrondir(r["spearman_p_neff"], 4),
    }


def _figure(figures, session_id, r, indice, phase, lag, metrique, titre_extra=""):
    if figures is None or not r.get("calculable"):
        return None
    spec = {
        "genre": "nuage", "type": "recompute_correlation",
        "titre": "%s et %s, lag %d mois%s" % (indice, metrique, lag, titre_extra),
        "sous_titre": "%s · %d années · r = %s (après détrend)"
                      % (phase, r["n"], ("%.2f" % r["pearson_r"]).replace(".", ",")),
        # Indice en abscisse (le predicteur), pluie en ordonnee.
        "donnees": {"points": [(a, yi, xi) for a, xi, yi in r["points"]],
                    "x_label": "%s (détrendé, °C)" % indice,
                    "y_label": "%s (détrendé)" % metrique},
        "source": SOURCE_CORRELATIONS,
        "hauteur_pouces": 2.9,
    }
    fig = figures.deposer(session_id, spec)
    return {"figure_id": fig.id, "titre": spec["titre"], "sous_titre": spec["sous_titre"]}


def run(params, data, figures=None, session_id=""):
    analyse = champ_enum(params, "analysis", ANALYSES, defaut="correlation")
    if not params.get("index") or not params.get("phase"):
        raise ToolInputError("index et phase sont requis.")
    indice = resoudre_indice(params["index"])
    phase = resoudre_phase(params["phase"])
    lag = champ_entier(params, "lag", mini=0, maxi=LAG_MAX)
    if lag is None:
        raise ToolInputError("lag est requis (0 a %d mois)." % LAG_MAX)
    metrique = champ_enum(params, "metric", sorted(METRIQUES), defaut="max_precip")
    avec_figure = champ_bool(params, "figure", defaut=False)
    try:
        reference = analyses.correlation(phase, lag, indice, metrique)
    except analyses.AnalyseIndisponible:
        raise ToolInputError("Les donnees du calcul sont indisponibles sur ce serveur.")

    sortie = {
        "analyse": analyse, "indice": indice, "phase": phase, "lag_mois": lag,
        "metrique": metrique,
        "reference_periode_complete": _resume(reference),
        "avertissement": AVERTISSEMENT,
        "source": SOURCE_CORRELATIONS + " -- recalcul avec les fonctions du script 04",
    }

    if analyse == "correlation":
        annees, periode, exclues = _annees(params)
        r = analyses.correlation(phase, lag, indice, metrique, annees)
        sortie.update({"periode": list(periode), "annees_exclues": exclues,
                       "recalcul": _resume(r)})
        if r.get("calculable") and reference.get("calculable"):
            sortie["variation_r"] = arrondir(r["pearson_r"] - reference["pearson_r"], 3)
        if avec_figure:
            sortie["figure"] = _figure(figures, session_id, r, indice, phase, lag,
                                       metrique)
    elif analyse == "comparer_periodes":
        coupe = champ_entier(params, "split_year", mini=analyses.ANNEE_MIN + 10,
                             maxi=analyses.ANNEE_MAX - 9, defaut=2003)
        avant = analyses.correlation(phase, lag, indice, metrique,
                                     range(analyses.ANNEE_MIN, coupe))
        apres = analyses.correlation(phase, lag, indice, metrique,
                                     range(coupe, analyses.ANNEE_MAX + 1))
        ra, rb = _resume(avant), _resume(apres)
        meme_signe = (ra.get("pearson_r") is not None and rb.get("pearson_r") is not None
                      and (ra["pearson_r"] > 0) == (rb["pearson_r"] > 0))
        sortie.update({
            "premiere_periode": dict(ra, periode=[analyses.ANNEE_MIN, coupe - 1]),
            "seconde_periode": dict(rb, periode=[coupe, analyses.ANNEE_MAX]),
            "meme_signe": meme_signe,
            "lecture": ("Un signal stable garde son signe sur les deux moities. Avec "
                        "~20 annees par moitie, la significativite tombe souvent: "
                        "juger d'abord le signe et l'ordre de grandeur de r."),
        })
    else:
        complete, effets = analyses.influence_annuelle(phase, lag, indice, metrique)
        perd = [e for e in effets if reference.get("pearson_p_neff") is not None
                and reference["pearson_p_neff"] < 0.05 and (e["p_neff"] or 1) >= 0.05]
        sortie.update({
            "annees_les_plus_influentes": effets[:6],
            "annees_dont_le_retrait_fait_perdre_la_significativite":
                [e["annee_retiree"] for e in perd],
            "lecture": ("ecart_r = r sans cette annee - r complet. Si retirer une "
                        "seule annee fait perdre la significativite, le resultat "
                        "repose sur elle."),
        })
        if avec_figure:
            sortie["figure"] = _figure(figures, session_id, complete, indice, phase,
                                       lag, metrique)
    return sortie
