"""Outil search_extreme_events: catalogue des evenements de pluies extremes.

Meme jeu que le module "Evenements" du dashboard
(data/processed/extreme_events_phases_senegal.csv via load_events):
1317 evenements detectes au-dela de 2 sigma sur les anomalies CHIRPS.
"""
from .common import (PHASES_LABELS, PHASES_TOUTES, SOURCE_EVENTS,
                     ToolInputError, arrondir, champ_bool, champ_decimal,
                     champ_entier, champ_enum, champ_texte, jour, normalise,
                     resoudre_phase)

NAME = "search_extreme_events"
LABEL = "Recherche dans le catalogue des evenements"
PERMISSION = "public"
DATASETS = ("events",)

DESCRIPTION = (
    "Recherche dans le catalogue des evenements de pluies extremes detectes "
    "au Senegal sur 1981-2023 (seuil de 2 ecarts-types sur les anomalies "
    "CHIRPS). Permet de filtrer par annee, mois, phase de saison, region ou "
    "departement, et de trier par intensite ou par date. Utilise cet outil "
    "pour toute question sur des evenements passes: combien, quand, ou, "
    "lesquels ont ete les plus intenses."
)

TRIS = ["max_precip", "mean_precip", "coverage_percent", "max_anomaly", "date"]
LIMITE_MAX = 20

SCHEMA = {
    "type": "object",
    "properties": {
        "year": {"type": "integer", "description": "Annee precise (1981-2023)."},
        "year_min": {"type": "integer", "description": "Annee minimale."},
        "year_max": {"type": "integer", "description": "Annee maximale."},
        "month": {"type": "integer", "description": "Mois (1-12)."},
        "phase": {
            "type": "string",
            "enum": PHASES_TOUTES,
            "description": "Phase de la saison des pluies: Phase_1_debut "
                           "(mai-juin), Phase_2_pleine (juillet-aout), "
                           "Phase_3_fin (septembre-octobre).",
        },
        "region": {"type": "string",
                   "description": "Region du centroide de l evenement "
                                  "(Tambacounda, Matam, Kolda, Kedougou...). "
                                  "Accents et casse indifferents."},
        "department": {"type": "string",
                       "description": "Departement du centroide de l evenement."},
        "min_max_precip": {"type": "number",
                           "description": "Precipitation maximale minimale, en mm."},
        "sort_by": {"type": "string", "enum": TRIS,
                    "description": "Critere de tri. Defaut: max_precip."},
        "ascending": {"type": "boolean",
                      "description": "Tri croissant. Defaut: false (les plus "
                                     "intenses ou les plus recents d abord)."},
        "limit": {"type": "integer",
                  "description": "Nombre d evenements detailles a renvoyer "
                                 "(1 a 20, defaut 5). Le total des "
                                 "correspondances est toujours renvoye."},
    },
    "required": [],
}


def _correspond(serie, attendu):
    """Filtre textuel insensible aux accents, a la casse et aux abreviations."""
    cible = normalise(attendu)
    normalisee = serie.fillna("").map(normalise)
    exact = normalisee == cible
    if exact.any():
        return exact
    return normalisee.str.contains(cible, regex=False)


def run(params, data):
    df = data["events"]

    annee = champ_entier(params, "year", mini=1900, maxi=2100)
    annee_min = champ_entier(params, "year_min", mini=1900, maxi=2100)
    annee_max = champ_entier(params, "year_max", mini=1900, maxi=2100)
    mois = champ_entier(params, "month", mini=1, maxi=12)
    phase = params.get("phase")
    phase = resoudre_phase(phase) if phase is not None else None
    region = champ_texte(params, "region")
    departement = champ_texte(params, "department")
    seuil = champ_decimal(params, "min_max_precip")
    tri = champ_enum(params, "sort_by", TRIS, defaut="max_precip")
    croissant = champ_bool(params, "ascending", defaut=False)
    limite = champ_entier(params, "limit", mini=1, maxi=LIMITE_MAX, defaut=5)

    if annee_min is not None and annee_max is not None and annee_min > annee_max:
        raise ToolInputError("year_min (%d) depasse year_max (%d)." % (annee_min, annee_max))

    selection = df
    filtres = {}
    if annee is not None:
        selection = selection[selection["year"] == annee]
        filtres["annee"] = annee
    if annee_min is not None:
        selection = selection[selection["year"] >= annee_min]
        filtres["annee_min"] = annee_min
    if annee_max is not None:
        selection = selection[selection["year"] <= annee_max]
        filtres["annee_max"] = annee_max
    if mois is not None:
        selection = selection[selection["month"] == mois]
        filtres["mois"] = mois
    if phase is not None and phase != "Toutes phases":
        selection = selection[selection["phase"] == phase]
        filtres["phase"] = phase
    if region is not None:
        selection = selection[_correspond(selection["centroid_region"], region)]
        filtres["region"] = region
    if departement is not None:
        selection = selection[_correspond(selection["centroid_department"], departement)]
        filtres["departement"] = departement
    if seuil is not None:
        selection = selection[selection["max_precip"] >= seuil]
        filtres["min_max_precip"] = seuil

    if selection.empty:
        # Pas une erreur: "aucun evenement ne correspond" est une reponse
        # legitime, que le modele doit pouvoir restituer telle quelle.
        return {
            "n_total": 0,
            "filtres": filtres,
            "evenements": [],
            "message": "Aucun evenement extreme ne correspond a ces criteres.",
            "couverture": _couverture(df),
            "source": SOURCE_EVENTS,
        }

    triee = selection.sort_values(tri, ascending=croissant)
    retenus = triee.head(limite)

    evenements = [{
        "date": jour(ligne["date"]),
        "phase": ligne["phase"],
        "phase_label": PHASES_LABELS.get(ligne["phase"], ligne["phase"]),
        "max_precip_mm": arrondir(ligne["max_precip"], 1),
        "mean_precip_mm": arrondir(ligne["mean_precip"], 1),
        "couverture_pct": arrondir(ligne["coverage_percent"], 1),
        "anomalie_max_sigma": arrondir(ligne["max_anomaly"], 2),
        "region_centroide": ligne.get("centroid_region"),
        "departement_centroide": ligne.get("centroid_department"),
        "regions_touchees": int(ligne["regions_affected"]) if "regions_affected" in ligne else None,
    } for _, ligne in retenus.iterrows()]

    top_regions = (selection["centroid_region"].dropna().value_counts().head(5)
                   if "centroid_region" in selection.columns else [])

    return {
        "n_total": int(len(selection)),
        "n_renvoyes": len(evenements),
        "filtres": filtres,
        "tri": {"critere": tri, "croissant": croissant},
        "evenements": evenements,
        "statistiques": {
            "max_precip_moyen_mm": arrondir(selection["max_precip"].mean(), 1),
            "max_precip_maximal_mm": arrondir(selection["max_precip"].max(), 1),
            "couverture_moyenne_pct": arrondir(selection["coverage_percent"].mean(), 1),
            "premiere_date": jour(selection["date"].min()),
            "derniere_date": jour(selection["date"].max()),
            "repartition_par_phase": {
                cle: int(valeur)
                for cle, valeur in selection["phase"].value_counts().items()
            },
            "regions_les_plus_touchees": [
                {"region": nom, "n_evenements": int(compte)}
                for nom, compte in (top_regions.items() if len(top_regions) else [])
            ],
        },
        "couverture": _couverture(df),
        "source": SOURCE_EVENTS,
    }


def _couverture(df):
    return {
        "n_evenements_total": int(len(df)),
        "premiere_date": jour(df["date"].min()),
        "derniere_date": jour(df["date"].max()),
    }
