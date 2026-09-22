"""Outil get_teleconnection: correlations indices SST / pluies extremes.

Lit les CSV produits par scripts/04_teleconnections_analysis.py
(outputs/teleconnections/correlations_*.csv via load_telecon) -- les memes que
le module "Teleconnexions" du dashboard.

Deux precisions que l outil renvoie systematiquement, parce que les omettre
rendrait les chiffres trompeurs:
  - la p-value citee est corrigee de l autocorrelation (AR1, n_eff), la
    p-value nominale surestimerait la significativite sur des series annuelles;
  - une correlation n est pas une causalite, et ces resultats portent sur
    l INTENSITE des extremes, pas sur le cumul saisonnier.
"""
from .common import (INDICES, INDICES_LABELS, METRIQUES, PHASES_LABELS,
                     PHASES_TOUTES, SOURCE_CORRELATIONS, ToolInputError,
                     arrondir, champ_bool, champ_entier, champ_enum, etoiles,
                     resoudre_indice, resoudre_phase)

NAME = "get_teleconnection"
LABEL = "Consultation des téléconnexions"
PERMISSION = "public"
DATASETS = ("correlations",)

DESCRIPTION = (
    "Correlations entre un indice SST et les pluies extremes du Senegal, par "
    "phase de saison et par decalage temporel (lag) de 0 a 5 mois. Renvoie le "
    "coefficient de Pearson, celui de Spearman, la p-value corrigee de "
    "l autocorrelation AR1 et la taille d echantillon effective. Utilise cet "
    "outil pour toute question sur le lien entre un indice oceanique et les "
    "pluies extremes, sur le meilleur decalage predictif, ou sur les indices "
    "les plus significatifs d une phase."
)

LIMITE_MAX = 20
LAG_MAX = 5

SCHEMA = {
    "type": "object",
    "properties": {
        "phase": {
            "type": "string",
            "enum": PHASES_TOUTES,
            "description": "Phase de la saison des pluies: Phase_1_debut "
                           "(mai-juin), Phase_2_pleine (juillet-aout), "
                           "Phase_3_fin (septembre-octobre), ou Toutes phases.",
        },
        "index": {"type": "string", "enum": INDICES,
                  "description": "Indice SST. Omettre pour comparer tous les "
                                 "indices entre eux."},
        "metric": {"type": "string", "enum": sorted(METRIQUES),
                   "description": "Metrique de pluie extreme correlee. Defaut: "
                                  "max_precip (intensite maximale mensuelle)."},
        "lag": {"type": "integer",
                "description": "Decalage en mois entre l indice SST et la pluie "
                               "(0 a 5). Omettre pour obtenir tous les lags."},
        "only_significant": {"type": "boolean",
                             "description": "Ne garder que les correlations "
                                            "significatives (p_neff < 0.05). "
                                            "Defaut: false."},
        "limit": {"type": "integer",
                  "description": "Nombre de lignes renvoyees (1 a 20, defaut 8)."},
    },
    "required": ["phase"],
}

AVERTISSEMENT = (
    "Une correlation n est pas une preuve de causalite et ne constitue pas une "
    "prevision. La p-value citee (p_neff) est corrigee de l autocorrelation "
    "AR1; aucune correction de tests multiples n est appliquee."
)


def run(params, data):
    if params.get("phase") is None:
        raise ToolInputError(
            "Le parametre phase est requis. Valeurs acceptees: %s."
            % ", ".join(PHASES_TOUTES)
        )
    phase = resoudre_phase(params["phase"])
    if phase not in data["correlations"]:
        raise ToolInputError(
            "Aucun resultat de correlation pour la phase %s. Phases "
            "disponibles: %s." % (phase, ", ".join(sorted(data["correlations"])))
        )
    df = data["correlations"][phase]

    indice = resoudre_indice(params["index"]) if params.get("index") else None
    metrique = champ_enum(params, "metric", sorted(METRIQUES), defaut="max_precip")
    lag = champ_entier(params, "lag", mini=0, maxi=LAG_MAX)
    seulement_sig = champ_bool(params, "only_significant", defaut=False)
    limite = champ_entier(params, "limit", mini=1, maxi=LIMITE_MAX, defaut=8)

    selection = df[df["metric"] == metrique]
    if indice is not None:
        selection = selection[selection["index"] == indice]
    if lag is not None:
        selection = selection[selection["lag_months"] == lag]

    n_avant_filtre_sig = int(len(selection))
    if seulement_sig:
        selection = selection[selection["pearson_p_neff"] < 0.05]

    if selection.empty:
        return {
            "phase": phase,
            "phase_label": PHASES_LABELS.get(phase, phase),
            "metrique": metrique,
            "correlations": [],
            "message": (
                "Aucune correlation significative (p_neff < 0.05) pour ces "
                "criteres, sur %d resultats examines." % n_avant_filtre_sig
                if seulement_sig else
                "Aucun resultat ne correspond a ces criteres."
            ),
            "avertissement": AVERTISSEMENT,
            "source": SOURCE_CORRELATIONS,
        }

    if indice is not None and lag is None:
        # Un seul indice sur tous les lags: l ordre chronologique se lit mieux
        # qu un classement par intensite.
        triee = selection.sort_values("lag_months")
    else:
        triee = selection.reindex(
            selection["pearson_r"].abs().sort_values(ascending=False).index
        )
    retenues = triee.head(limite)

    lignes = [{
        "indice": ligne["index"],
        "indice_description": INDICES_LABELS.get(ligne["index"], ligne["index"]),
        "lag_mois": int(ligne["lag_months"]),
        "pearson_r": arrondir(ligne["pearson_r"], 3),
        "p_neff": arrondir(ligne["pearson_p_neff"], 4),
        "significativite": etoiles(ligne["pearson_p_neff"]) or "non significatif",
        "spearman_r": arrondir(ligne["spearman_r"], 3),
        "spearman_p_neff": arrondir(ligne["spearman_p_neff"], 4),
        "n": int(ligne["n"]),
        "n_eff": arrondir(ligne["n_eff"], 1),
    } for _, ligne in retenues.iterrows()]

    significatives = selection[selection["pearson_p_neff"] < 0.05]
    meilleure = selection.loc[selection["pearson_r"].abs().idxmax()]

    return {
        "phase": phase,
        "phase_label": PHASES_LABELS.get(phase, phase),
        "metrique": metrique,
        "metrique_label": METRIQUES.get(metrique, metrique),
        "filtres": {"indice": indice, "lag_mois": lag,
                    "seulement_significatives": seulement_sig},
        "n_resultats": int(len(selection)),
        "n_renvoyes": len(lignes),
        "n_significatives": int(len(significatives)),
        "correlation_la_plus_forte": {
            "indice": meilleure["index"],
            "lag_mois": int(meilleure["lag_months"]),
            "pearson_r": arrondir(meilleure["pearson_r"], 3),
            "p_neff": arrondir(meilleure["pearson_p_neff"], 4),
            "significativite": etoiles(meilleure["pearson_p_neff"]) or "non significatif",
        },
        "correlations": lignes,
        "lecture": (
            "Un r negatif signifie qu un indice eleve va de pair avec des "
            "pluies extremes moins intenses. Le lag est le nombre de mois "
            "entre la mesure de l indice et la pluie: un lag de 3 mois signifie "
            "que l indice est mesure 3 mois avant."
        ),
        "avertissement": AVERTISSEMENT,
        "source": SOURCE_CORRELATIONS,
    }
