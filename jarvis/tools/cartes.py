"""Outil show_map: cartes a l'ecran de Jarvis.

Meme principe que make_figure (jarvis/tools/graphiques.py): le modele
choisit un TYPE de carte dans une liste fermee et ses parametres; l'outil
calcule la grille a partir des fichiers de la plateforme, depose la
specification dans le magasin de figures, et renvoie au modele un RESUME
chiffre de ce qui est trace. Rien n'est dessine par du code du modele.

Quatre cartes, reprises des modules Clustering et Evenements du dashboard:
  - sst_cluster: motif SST global du centroide d'un cluster K-Means;
  - cluster_senegal: composite sur le Senegal des evenements d'un cluster;
  - evenement: un evenement extreme, n'importe lequel des 1317;
  - frequence_extremes: ou les extremes frappent le plus souvent.

Difference avec le dashboard: le composite de cluster porte ici sur TOUS
les evenements du cluster (grille CHIRPS du jour), la ou la page
Clustering n'en montre que 4 representatifs.
"""
import numpy as np

from .. import cartes
from .common import (PHASES, SOURCE_CLUSTERING, SOURCE_EVENTS, ToolInputError,
                     arrondir, champ_entier, champ_enum, champ_texte,
                     resoudre_phase)

NAME = "show_map"
LABEL = "Préparation d'une carte"
PERMISSION = "public"
DATASETS = ("events",)

TYPES = ["sst_cluster", "cluster_senegal", "evenement", "frequence_extremes"]
VARIABLES = ["precipitation", "anomalie"]
SEUIL = 2.0

DESCRIPTION = (
    "Affiche une CARTE sur l'ecran de l'utilisateur (grand format en mode "
    "J.A.R.V.I.S, sous ta reponse dans la bulle). Types: sst_cluster "
    "(anomalies SST globales 60S-60N du centroide d'un cluster K-Means, avec "
    "les boites des indices: le motif oceanique du cluster; phase et cluster "
    "requis), cluster_senegal (composite sur le Senegal de tous les "
    "evenements d'un cluster: ou il pleut quand l'ocean est dans cette "
    "configuration; phase et cluster requis), evenement (carte d'UN "
    "evenement extreme du catalogue, date AAAA-MM-JJ requise; trouve la date "
    "avec search_extreme_events si besoin), frequence_extremes (part des "
    "jours d'evenement ou chaque pixel depasse 2 sigma, par phase ou toutes "
    "phases). variable: precipitation (mm/jour) ou anomalie (sigma). Le "
    "resultat contient un resume chiffre: commente a partir de lui, pas de "
    "memoire. Utilise-la quand l'utilisateur demande une carte, ou qu'une "
    "question porte sur OU (repartition spatiale, regions touchees, motif "
    "oceanique)."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": TYPES, "description": "Type de carte."},
        "phase": {"type": "string",
                  "enum": PHASES + ["Toutes phases"],
                  "description": "Phase de saison (sst_cluster, cluster_senegal: "
                                 "requise; frequence_extremes: defaut toutes)."},
        "cluster": {"type": "integer", "description": "Numero du cluster K-Means."},
        "date": {"type": "string", "description": "evenement: date AAAA-MM-JJ."},
        "variable": {"type": "string", "enum": VARIABLES,
                     "description": "precipitation (defaut) ou anomalie."},
    },
    "required": ["type"],
}

LIBELLES_PHASE = {
    "Phase_1_debut": "début de saison (mai-juin)",
    "Phase_2_pleine": "pleine saison (juillet-août)",
    "Phase_3_fin": "fin de saison (septembre-octobre)",
    "All_phases": "toutes phases",
}


# =============================================================================
# Outils communs
# =============================================================================
def _phase_cluster(params, requise=True):
    brut = params.get("phase")
    if brut is None:
        if requise:
            raise ToolInputError("Le parametre phase est requis pour ce type de carte.")
        return "All_phases"
    phase = resoudre_phase(brut)
    return "All_phases" if phase == "Toutes phases" else phase


def _liste(grille2d, decimales=2):
    return [[None if np.isnan(v) else round(float(v), decimales) for v in ligne]
            for ligne in grille2d]


def _region_du_point(lon, lat):
    """Region contenant le centre du pixel; a defaut (pixel a cheval sur une
    frontiere ou la cote), celle qui contient un de ses coins."""
    from matplotlib.path import Path
    for dx, dy in ((0, 0), (0.1, 0.1), (-0.1, 0.1), (0.1, -0.1), (-0.1, -0.1)):
        for region in cartes.senegal()["regions"]:
            for anneau in region["anneaux"]:
                if Path(anneau).contains_point((lon + dx, lat + dy)):
                    return region["nom"]
    return None


def _maximum(grille2d):
    """(valeur, lon, lat, region) du pixel maximal."""
    g = cartes.grille()
    if np.all(np.isnan(grille2d)):
        return None
    i, j = np.unravel_index(np.nanargmax(grille2d), grille2d.shape)
    lon, lat = g["lons"][j], g["lats"][i]
    return float(grille2d[i, j]), lon, lat, _region_du_point(lon, lat)


def _moyennes_regionales(grille2d, top=4):
    """Moyenne de la grille par region administrative, les plus fortes."""
    from matplotlib.path import Path
    g = cartes.grille()
    lons, lats = np.meshgrid(g["lons"], g["lats"])
    points = np.column_stack([lons.ravel(), lats.ravel()])
    valeurs = grille2d.ravel()
    sortie = []
    for region in cartes.senegal()["regions"]:
        dedans = np.zeros(len(points), dtype=bool)
        for anneau in region["anneaux"]:
            dedans |= Path(anneau).contains_points(points)
        v = valeurs[dedans]
        v = v[~np.isnan(v)]
        if v.size:
            sortie.append((region["nom"], float(v.mean())))
    sortie.sort(key=lambda t: -t[1])
    return [{"region": nom, "moyenne": arrondir(m, 2)} for nom, m in sortie[:top]]


def _spec_senegal(titre, sous_titre, grille2d, variable, vmax=None, marqueur=None,
                  source=SOURCE_EVENTS):
    g = cartes.grille()
    anomalie = variable == "anomalie"
    if vmax is None:
        haut = float(np.nanpercentile(grille2d, 98)) if not np.all(np.isnan(grille2d)) else 1.0
        vmax = max(haut, 3.0 if anomalie else 5.0)
        # Au-dela de 8 sigma, l'echelle ecraserait tout le reste (le
        # catalogue plafonne l'anomalie a 20).
        vmax = min(vmax, 8.0) if anomalie else vmax
    donnees = {
        "lats": g["lats"], "lons": g["lons"], "valeurs": _liste(grille2d),
        "echelle": "anomalie" if anomalie else "pluie",
        "vmin": 0.0, "vmax": round(float(vmax), 2),
        "seuil": SEUIL if anomalie else None,
        "legende": ("anomalie standardisée (σ), tirets = seuil de 2 σ" if anomalie
                    else "précipitation (mm/jour)"),
        "marqueurs": [marqueur] if marqueur else [],
    }
    return {"genre": "carte_senegal", "titre": titre, "sous_titre": sous_titre,
            "donnees": donnees, "source": source}


def _marqueur(maxi, unite):
    if maxi is None:
        return None
    valeur, lon, lat, _ = maxi
    texte = ("max %s σ" % _virgule(valeur, 1)) if unite == "σ" else \
            ("max %s mm" % _virgule(valeur, 0))
    return {"lon": lon, "lat": lat, "texte": texte}


def _virgule(v, decimales):
    return ("%%.%df" % decimales % v).replace(".", ",")


# =============================================================================
# Types de cartes
# =============================================================================
def _sst_cluster(params, data):
    phase = _phase_cluster(params)
    affect = cartes.evenements_par_cluster(phase)
    clusters = sorted(int(c) for c in affect["cluster"].unique())
    numero = champ_entier(params, "cluster")
    if numero is None or numero not in clusters:
        raise ToolInputError("cluster requis parmi %s pour %s."
                             % (clusters, LIBELLES_PHASE[phase]))
    grilles = cartes.centroides(phase)
    indice = clusters.index(numero)
    z = grilles[indice]
    haut = max(abs(float(np.nanpercentile(z, 2))), abs(float(np.nanpercentile(z, 98))))
    vlim = round(min(max(haut, 0.3), 3.0), 2)
    boites = {nom: arrondir(cartes.moyenne_boite(z, b), 2)
              for nom, b in cartes.BOITES_RESUME.items()}
    tri = sorted((v, k) for k, v in boites.items() if v is not None)
    n = int((affect["cluster"] == numero).sum())
    spec = {
        "genre": "carte_sst",
        "titre": "Motif SST du cluster %d" % numero,
        "sous_titre": "%s · centroïde de %d événements · anomalies 60°S-60°N"
                      % (LIBELLES_PHASE[phase], n),
        "donnees": {"phase": phase, "indice_cluster": indice, "vlim": vlim},
        "source": SOURCE_CLUSTERING,
    }
    resume = {
        "phase": phase, "cluster": numero, "n_evenements": n,
        "anomalie_moyenne_par_boite_degC": boites,
        "boite_la_plus_froide": tri[0][1] if tri else None,
        "boite_la_plus_chaude": tri[-1][1] if tri else None,
        "echelle_couleurs_degC": [-vlim, vlim],
        "rappel": ("un cluster est une configuration oceanique GLOBALE le jour "
                   "des evenements, pas une zone du Senegal; le centroide est "
                   "la moyenne de ces jours"),
    }
    return spec, resume


def _cluster_senegal(params, data):
    phase = _phase_cluster(params)
    variable = champ_enum(params, "variable", VARIABLES, defaut="precipitation")
    affect = cartes.evenements_par_cluster(phase)
    clusters = sorted(int(c) for c in affect["cluster"].unique())
    numero = champ_entier(params, "cluster")
    if numero is None or numero not in clusters:
        raise ToolInputError("cluster requis parmi %s pour %s."
                             % (clusters, LIBELLES_PHASE[phase]))
    dates = [str(d)[:10] for d in affect.loc[affect["cluster"] == numero, "date"]]
    piles = []
    for d in dates:
        try:
            an, pluie = cartes.jour(d)
        except cartes.CarteIndisponible:
            continue
        piles.append(an if variable == "anomalie" else pluie)
    if not piles:
        raise ToolInputError("Aucune grille disponible pour ce cluster.")
    with np.errstate(all="ignore"):
        composite = np.nanmean(np.stack(piles), axis=0)
    unite = "σ" if variable == "anomalie" else "mm"
    maxi = _maximum(composite)
    spec = _spec_senegal(
        "Où il pleut avec le cluster %d" % numero,
        "%s · moyenne de %d événements · %s"
        % (LIBELLES_PHASE[phase], len(piles),
           "anomalie (σ)" if variable == "anomalie" else "précipitation (mm/jour)"),
        composite, variable, marqueur=_marqueur(maxi, unite),
        source=SOURCE_CLUSTERING)
    resume = {
        "phase": phase, "cluster": numero, "n_evenements": len(piles),
        "variable": variable,
        "moyenne_senegal": arrondir(float(np.nanmean(composite)), 2),
        "maximum": {"valeur": arrondir(maxi[0], 2), "region": maxi[3]} if maxi else None,
        "regions_les_plus_touchees": _moyennes_regionales(composite),
        "note": ("composite de TOUS les evenements du cluster; la page "
                 "Clustering du dashboard n'en montre que 4 representatifs"),
    }
    return spec, resume


def _evenement(params, data):
    brut = champ_texte(params, "date", maxi=10)
    if not brut:
        raise ToolInputError("date requise (AAAA-MM-JJ). Utilise search_extreme_events "
                             "pour trouver la date d'un evenement.")
    variable = champ_enum(params, "variable", VARIABLES, defaut="precipitation")
    catalogue = data["events"]
    dates = catalogue["date"].dt.strftime("%Y-%m-%d")
    ligne = catalogue[dates == brut]
    if ligne.empty:
        import pandas as pd
        try:
            cible = pd.Timestamp(brut)
        except ValueError:
            raise ToolInputError("date invalide: %r (format AAAA-MM-JJ)." % brut)
        proches = (catalogue.assign(ecart=(catalogue["date"] - cible).abs())
                   .nsmallest(3, "ecart")["date"].dt.strftime("%Y-%m-%d").tolist())
        raise ToolInputError("Aucun evenement extreme le %s. Evenements les plus "
                             "proches: %s." % (brut, ", ".join(proches)))
    ev = ligne.iloc[0]
    an, pluie = cartes.jour(brut)
    grille2d = an if variable == "anomalie" else pluie
    unite = "σ" if variable == "anomalie" else "mm"
    maxi = _maximum(grille2d)
    libelle = LIBELLES_PHASE.get(ev["phase"], ev["phase"])
    spec = _spec_senegal(
        "Événement du %s" % _date_fr(brut),
        "%s · %s" % (libelle, "anomalie (σ)" if variable == "anomalie"
                     else "précipitation (mm/jour)"),
        grille2d, variable, marqueur=_marqueur(maxi, unite))
    resume = {
        "date": brut, "phase": ev["phase"], "variable": variable,
        "catalogue": {
            "precipitation_max_mm": arrondir(ev["max_precip"], 1),
            "precipitation_moyenne_mm": arrondir(ev["mean_precip"], 1),
            "anomalie_max_sigma": arrondir(ev["max_anomaly"], 2),
            "couverture_pct": arrondir(ev["coverage_percent"], 1),
            "region_du_centroide": ev["centroid_region"],
            "regions_touchees": int(ev["regions_affected"]),
            "rang": int(ev["rank"]),
        },
        "maximum_sur_la_carte": ({"valeur": arrondir(maxi[0], 2), "region": maxi[3]}
                                 if maxi else None),
        "regions_les_plus_touchees": _moyennes_regionales(grille2d),
    }
    return spec, resume


def _frequence_extremes(params, data):
    phase = _phase_cluster(params, requise=False)
    catalogue = data["events"]
    if phase != "All_phases":
        catalogue = catalogue[catalogue["phase"] == phase]
    dates = catalogue["date"].dt.strftime("%Y-%m-%d").tolist()
    g = cartes.grille()
    indices = [g["index"][d] for d in dates if d in g["index"]]
    if not indices:
        raise ToolInputError("Aucun evenement pour cette phase.")
    an = g["anomalies"][indices]
    with np.errstate(all="ignore"):
        part = 100.0 * np.nanmean(an > SEUIL, axis=0)
    part[np.isnan(an).all(axis=0)] = np.nan
    maxi = _maximum(part)
    spec = _spec_senegal(
        "Où les extrêmes frappent le plus",
        "%s · part des %d jours d'événement où le pixel dépasse 2 σ"
        % (LIBELLES_PHASE[phase], len(indices)),
        part, "anomalie", vmax=float(np.nanmax(part)),
        marqueur=({"lon": maxi[1], "lat": maxi[2],
                   "texte": "%s %%" % _virgule(maxi[0], 0)} if maxi else None))
    # Frequence: ni seuil a 2 (ce sont des %), ni legende en sigma.
    spec["donnees"]["seuil"] = None
    spec["donnees"]["legende"] = "part des jours d'événement au-dessus de 2 σ (%)"
    resume = {
        "phase": phase, "n_jours_evenement": len(indices),
        "part_moyenne_pct": arrondir(float(np.nanmean(part)), 1),
        "maximum": {"part_pct": arrondir(maxi[0], 1), "region": maxi[3]} if maxi else None,
        "regions_les_plus_frequentes": _moyennes_regionales(part),
    }
    return spec, resume


MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


def _date_fr(iso):
    a, m, j = iso.split("-")
    return "%d %s %s" % (int(j), MOIS_FR[int(m) - 1], a)


_TYPES = {
    "sst_cluster": _sst_cluster,
    "cluster_senegal": _cluster_senegal,
    "evenement": _evenement,
    "frequence_extremes": _frequence_extremes,
}


def construire(params, data):
    genre = champ_enum(params, "type", TYPES)
    if genre is None:
        raise ToolInputError("Le parametre type est requis. Valeurs acceptees: %s."
                             % ", ".join(TYPES))
    try:
        spec, resume = _TYPES[genre](params, data)
    except cartes.CarteIndisponible as exc:
        raise ToolInputError(str(exc))
    spec["type"] = genre
    return spec, resume


def run(params, data, figures=None, session_id=""):
    if figures is None:
        raise ToolInputError("L'affichage de cartes n'est pas disponible ici.")
    spec, resume = construire(params, data)
    figure = figures.deposer(session_id, spec)
    return {
        "figure_id": figure.id,
        "carte": True,
        "type": spec["type"],
        "titre": spec["titre"],
        "sous_titre": spec["sous_titre"],
        "affichee": True,
        "resume": resume,
        "consigne": ("La carte s'affiche a l'ecran avec son titre. Dis ce qu'elle "
                     "montre d'essentiel (ou, combien, quel contraste), a partir "
                     "du resume, sans la decrire pixel par pixel."),
        "source": spec["source"],
    }
