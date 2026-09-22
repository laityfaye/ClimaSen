"""Outil get_risk_cluster: typologie des configurations oceaniques.

Lit outputs/clustering/ (via load_clustering), comme le module "Clustering" du
dashboard.

ATTENTION AU NOM. Ces clusters ne sont PAS des zones geographiques du Senegal:
le K-Means porte sur le champ SST GLOBAL du jour de chaque evenement extreme
(apres ACP). Un cluster est donc une configuration oceanique recurrente, et les
evenements qui lui sont rattaches partagent cet etat de l ocean. Le decoupage
regional renvoye ici est une CONSEQUENCE observee (ou sont tombees les pluies
de ces evenements), jamais la variable de classification. L outil le rappelle
dans chaque reponse: sans cela, le modele presenterait des regimes oceaniques
comme des profils de risque par departement.
"""
from .common import (PHASES_LABELS, PHASES_TOUTES, SOURCE_CLUSTERING,
                     ToolInputError, arrondir, champ_bool, champ_date,
                     champ_entier, jour, resoudre_phase)

NAME = "get_risk_cluster"
LABEL = "Consultation des régimes océaniques"
PERMISSION = "public"
DATASETS = ("clustering", "events")

DESCRIPTION = (
    "Typologie des configurations oceaniques associees aux pluies extremes, "
    "obtenue par K-Means sur les champs de SST globaux du jour de chaque "
    "evenement (module Clustering de la plateforme). Renvoie, pour une phase "
    "de saison, le nombre de regimes retenus, la qualite du regroupement et le "
    "profil de chaque regime: effectif, intensite moyenne des pluies, "
    "couverture spatiale, regions ou ces evenements se sont produits. Peut "
    "aussi indiquer a quel regime appartient l evenement d une date donnee. "
    "Ces regimes decrivent l etat de l ocean, PAS un decoupage geographique du "
    "Senegal."
)

NATURE = (
    "Un cluster est une configuration de temperatures oceaniques globales, pas "
    "une zone du Senegal. Les regions citees indiquent ou sont tombees les "
    "pluies des evenements rattaches a ce regime; elles ne servent pas a "
    "constituer les clusters."
)

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
        "cluster": {"type": "integer",
                    "description": "Numero de regime a detailler. Omettre pour "
                                   "obtenir tous les regimes de la phase."},
        "date": {"type": "string",
                 "description": "Date d un evenement extreme (AAAA-MM-JJ) pour "
                                "savoir a quel regime il appartient."},
        "include_regions": {"type": "boolean",
                            "description": "Joindre les regions ou sont tombees "
                                           "les pluies de chaque regime. "
                                           "Defaut: true."},
    },
    "required": ["phase"],
}

# load_clustering() nomme la phase agregee All_phases, le reste de la
# plateforme dit "Toutes phases".
_CLES_DATASET = {"Toutes phases": "All_phases"}


def _profil(ligne, regions):
    numero = int(ligne["cluster"])
    profil = {
        "cluster": numero,
        "n_evenements": int(ligne["n_events"]),
        "part_pct": arrondir(ligne["percentage"], 1),
        "max_precip_moyen_mm": arrondir(ligne["mean_max_precip"], 1),
        "precip_moyenne_mm": arrondir(ligne["mean_mean_precip"], 1),
        "couverture_moyenne_pct": arrondir(ligne["mean_coverage_percent"], 1),
        "anomalie_max_moyenne_sigma": arrondir(ligne["mean_max_anomaly"], 2),
        "annee_moyenne": int(round(float(ligne["mean_year"]))),
        "mois_moyen": arrondir(ligne["mean_month"], 1),
        "n_annees_concernees": int(ligne["n_years"]),
    }
    if regions is not None:
        profil["regions_principales"] = regions.get(numero, [])
    return profil


def _regions_par_cluster(evenements_clusters, evenements, limite=4):
    """Regions du centroide des evenements de chaque cluster.

    La jointure se fait sur la date: les deux fichiers decrivent les memes
    evenements extremes, le catalogue portant seul la localisation.
    """
    if "centroid_region" not in evenements.columns:
        return {}
    fusion = evenements_clusters.merge(
        evenements[["date", "centroid_region"]], on="date", how="left")
    sortie = {}
    for numero, groupe in fusion.groupby("cluster"):
        comptes = groupe["centroid_region"].dropna().value_counts().head(limite)
        sortie[int(numero)] = [
            {"region": nom, "n_evenements": int(compte)}
            for nom, compte in comptes.items()
        ]
    return sortie


def run(params, data):
    if params.get("phase") is None:
        raise ToolInputError(
            "Le parametre phase est requis. Valeurs acceptees: %s."
            % ", ".join(PHASES_TOUTES)
        )
    phase = resoudre_phase(params["phase"])
    cle = _CLES_DATASET.get(phase, phase)
    clustering = data["clustering"]
    if cle not in clustering:
        raise ToolInputError(
            "Aucun resultat de clustering pour la phase %s. Phases "
            "disponibles: %s." % (phase, ", ".join(sorted(clustering)))
        )

    bloc = clustering[cle]
    chars = bloc["chars"]
    evenements_clusters = bloc["events"]
    metriques = bloc.get("metrics", {}) or {}

    numero = champ_entier(params, "cluster", mini=0)
    date_demandee, _ = champ_date(params, "date")
    avec_regions = champ_bool(params, "include_regions", defaut=True)

    disponibles = sorted(int(c) for c in chars["cluster"].unique())
    if numero is not None and numero not in disponibles:
        raise ToolInputError(
            "Cluster %d inexistant pour la phase %s. Clusters disponibles: %s."
            % (numero, phase, ", ".join(str(c) for c in disponibles))
        )

    regions = _regions_par_cluster(evenements_clusters, data["events"]) \
        if avec_regions else None

    lignes = chars if numero is None else chars[chars["cluster"] == numero]
    profils = [_profil(ligne, regions) for _, ligne in lignes.iterrows()]

    resultat = {
        "phase": phase,
        "phase_label": PHASES_LABELS.get(phase, phase),
        "methode": {
            "k_retenu": int(metriques.get("optimal_k", len(disponibles))),
            "silhouette": arrondir(metriques.get("best_silhouette_score"), 3),
            "n_evenements": int(metriques.get("n_samples", len(evenements_clusters))),
            "n_composantes_acp": metriques.get("n_pca_components"),
            "choix_du_k": metriques.get("decision"),
        },
        "clusters": profils,
        "nature": NATURE,
        "source": SOURCE_CLUSTERING,
    }

    if date_demandee is not None:
        resultat["evenement"] = _evenement(evenements_clusters, date_demandee, phase)
    return resultat


def _evenement(evenements_clusters, date_demandee, phase):
    trouve = evenements_clusters[evenements_clusters["date"] == date_demandee]
    if trouve.empty:
        return {
            "date": jour(date_demandee),
            "trouve": False,
            "message": (
                "Aucun evenement extreme classe a cette date pour la phase %s. "
                "Le clustering ne couvre que les evenements de 1983 a 2023 "
                "(les donnees SST commencent en 1983)." % phase
            ),
        }
    ligne = trouve.iloc[0]
    return {
        "date": jour(ligne["date"]),
        "trouve": True,
        "cluster": int(ligne["cluster"]),
        "max_precip_mm": arrondir(ligne["max_precip"], 1),
        "couverture_pct": arrondir(ligne["coverage_percent"], 1),
        "anomalie_max_sigma": arrondir(ligne["max_anomaly"], 2),
    }
