"""Outil make_figure: graphiques a la demande (Phase 8).

Le modele ne dessine rien et n'ecrit aucun code: il choisit un TYPE de figure
dans une liste fermee et ses parametres. L'outil calcule les donnees a partir
des memes loaders que le dashboard, depose la specification dans le magasin
de figures (jarvis/figures.py) et renvoie au modele un RESUME chiffre de ce
qui est trace, pour qu'il puisse commenter la figure sans rien inventer.

Liste fermee plutot que code genere: un graphique libre supposerait
d'executer du code produit par le modele sur le serveur, pour un gain
minime. Les sept types couvrent les cinq modules du dashboard.
"""
from scipy import stats

from .analyse_evenements import MOIS, _serie_annuelle
from .common import (INDICES, METRIQUES, PHASES_TOUTES,
                     SOURCE_CLUSTERING, SOURCE_CORRELATIONS, SOURCE_EVENTS,
                     SOURCE_INDICES, ToolInputError, arrondir, champ_entier,
                     champ_enum, champ_texte, etoiles, resoudre_indice,
                     resoudre_phase)
from .events import _correspond

NAME = "make_figure"
LABEL = "Préparation d'une figure"
PERMISSION = "public"
DATASETS = ("correlations", "indices", "events", "clustering")

TYPES = ["correlation_heatmap", "correlation_lags", "sst_series",
         "events_per_year", "events_by_month", "events_by_region",
         "cluster_profile"]

MAX_INDICES = 4
LAGS = list(range(6))

METRIQUES_CLUSTER = {
    "n_events": ("n_events", "nombre d'événements"),
    "max_precip": ("mean_max_precip", "précipitation max moyenne (mm)"),
    "coverage_percent": ("mean_coverage_percent", "couverture moyenne (%)"),
    "max_anomaly": ("mean_max_anomaly", "anomalie max moyenne (σ)"),
}

DESCRIPTION = (
    "Produit une figure affichee a l'utilisateur sous ta reponse. Types: "
    "correlation_heatmap (carte indices x lags d'une phase, etoiles = "
    "significativite AR1), correlation_lags (r en fonction du lag pour 1 a 4 "
    "indices), sst_series (serie mensuelle ou annuelle de 1 a 4 indices SST), "
    "events_per_year (evenements extremes par an, avec tendance de Sen), "
    "events_by_month (saisonnalite), events_by_region (classement des "
    "regions), cluster_profile (profil des clusters K-Means d'une phase). "
    "Utilise-la quand une image aide vraiment: tendance, comparaison, "
    "vue d'ensemble d'une phase. Le resultat contient un resume chiffre de "
    "ce qui est trace: commente a partir de ce resume, pas de memoire."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": TYPES, "description": "Type de figure."},
        "phase": {"type": "string", "enum": PHASES_TOUTES + ["All_phases"],
                  "description": "Phase de saison (requise pour les "
                                 "correlations et les clusters)."},
        "indices": {"type": "array", "items": {"type": "string", "enum": INDICES},
                    "description": "1 a 4 indices SST (correlation_lags, "
                                   "sst_series)."},
        "metric": {"type": "string",
                   "description": "Correlations: max_precip (defaut), "
                                  "mean_precip, max_anomaly, "
                                  "coverage_percent, n_events. Clusters: "
                                  "n_events (defaut), max_precip, "
                                  "coverage_percent, max_anomaly."},
        "region": {"type": "string",
                   "description": "Filtre region (figures d'evenements)."},
        "year_min": {"type": "integer", "description": "Premiere annee."},
        "year_max": {"type": "integer", "description": "Derniere annee."},
        "aggregation": {"type": "string", "enum": ["mensuelle", "annuelle"],
                        "description": "sst_series: pas de temps. Defaut: "
                                       "annuelle."},
        "limit": {"type": "integer",
                  "description": "events_by_region: nombre de regions "
                                 "(1 a 14, defaut 10)."},
    },
    "required": ["type"],
}


# --- utilitaires ---------------------------------------------------------------
def _phase_requise(params, data_cle, disponibles):
    if not params.get("phase"):
        raise ToolInputError("Le parametre phase est requis pour ce type. "
                             "Valeurs acceptees: %s." % ", ".join(sorted(disponibles)))
    brut = params["phase"]
    phase = "All_phases" if str(brut).lower().replace(" ", "_") == "all_phases" \
        else resoudre_phase(brut)
    if data_cle == "clustering" and phase == "Toutes phases":
        phase = "All_phases"
    if data_cle == "correlations" and phase == "All_phases":
        phase = "Toutes phases"
    if phase not in disponibles:
        raise ToolInputError("Aucune donnee pour la phase %s. Phases "
                             "disponibles: %s." % (phase, ", ".join(sorted(disponibles))))
    return phase


def _indices(params, obligatoire=True):
    brut = params.get("indices") or []
    if isinstance(brut, str):
        brut = [brut]
    if not isinstance(brut, list):
        raise ToolInputError("indices doit etre une liste d'indices SST.")
    if obligatoire and not brut:
        raise ToolInputError("Le parametre indices est requis (1 a %d parmi: %s)."
                             % (MAX_INDICES, ", ".join(INDICES)))
    if len(brut) > MAX_INDICES:
        raise ToolInputError("%d indices au plus par figure: au-dela, les "
                             "couleurs ne se distinguent plus." % MAX_INDICES)
    vus = []
    for valeur in brut:
        indice = resoudre_indice(valeur)
        if indice not in vus:
            vus.append(indice)
    return vus


# Libelles AFFICHES a l'utilisateur (sous-titres). Ceux de common.py restent
# en ASCII telegraphique: ils sont lus par le modele, pas par un visiteur.
PHASES_AFFICHAGE = {
    "Phase_1_debut": "début de saison (mai-juin)",
    "Phase_2_pleine": "pleine saison (juillet-août)",
    "Phase_3_fin": "fin de saison (septembre-octobre)",
    "Toutes phases": "toutes phases",
    "All_phases": "toutes phases",
}
METRIQUES_AFFICHAGE = {
    "max_precip": "précipitation maximale",
    "mean_precip": "précipitation moyenne",
    "max_anomaly": "anomalie maximale",
    "coverage_percent": "couverture spatiale",
    "n_events": "nombre d'événements",
}


def _metrique_correlation(params):
    return champ_enum(params, "metric", sorted(METRIQUES), defaut="max_precip")


def _libelle_phase(phase):
    return PHASES_AFFICHAGE.get(phase, phase)


# --- types ----------------------------------------------------------------------
def _correlation_heatmap(params, data):
    phase = _phase_requise(params, "correlations", data["correlations"])
    metrique = _metrique_correlation(params)
    df = data["correlations"][phase]
    df = df[df["metric"] == metrique]
    if df.empty:
        raise ToolInputError("Aucune correlation pour cette metrique.")
    lignes = [i for i in INDICES if i in set(df["index"])]
    valeurs, marques = [], []
    for indice in lignes:
        sous = df[df["index"] == indice].set_index("lag_months")
        valeurs.append([arrondir(sous["pearson_r"].get(lag), 3) for lag in LAGS])
        marques.append([etoiles(sous["pearson_p_neff"].get(lag)) for lag in LAGS])
    meilleure = df.loc[df["pearson_r"].abs().idxmax()]
    n_sig = int((df["pearson_p_neff"] < 0.05).sum())
    spec = {
        "genre": "carte_chaleur",
        "titre": "Corrélations indices SST / pluies extrêmes",
        "sous_titre": "%s · %s · r de Pearson, étoiles = p_neff (AR1)"
                      % (_libelle_phase(phase), METRIQUES_AFFICHAGE[metrique]),
        "hauteur_pouces": 3.3,
        "donnees": {"lignes": lignes, "colonnes": LAGS, "valeurs": valeurs,
                    "etoiles": marques, "vmax": 0.6,
                    "titre_lignes": "indice", "titre_colonnes": "décalage (mois)",
                    "legende_couleur": "r de Pearson"},
    }
    resume = {
        "phase": phase, "metrique": metrique,
        "n_cellules": len(lignes) * len(LAGS),
        "n_significatives_p_neff": n_sig,
        "correlation_la_plus_forte": {
            "indice": meilleure["index"], "lag_mois": int(meilleure["lag_months"]),
            "pearson_r": arrondir(meilleure["pearson_r"], 3),
            "p_neff": arrondir(meilleure["pearson_p_neff"], 4)},
        "echelle_couleur": "bleu = r negatif, rouge = r positif, bornee a +/-0.6",
    }
    return spec, resume, SOURCE_CORRELATIONS


def _correlation_lags(params, data):
    phase = _phase_requise(params, "correlations", data["correlations"])
    metrique = _metrique_correlation(params)
    indices = _indices(params)
    df = data["correlations"][phase]
    df = df[df["metric"] == metrique]
    series, resume_series = [], []
    for indice in indices:
        sous = df[df["index"] == indice].set_index("lag_months")
        if sous.empty:
            continue
        r = [arrondir(sous["pearson_r"].get(lag), 3) for lag in LAGS]
        sig = [bool(sous["pearson_p_neff"].get(lag, 1) < 0.05) for lag in LAGS]
        series.append({"nom": indice, "y": r, "marqueurs_pleins": sig})
        meilleur = max(range(len(LAGS)), key=lambda k: abs(r[k] or 0))
        resume_series.append({"indice": indice, "meilleur_lag": LAGS[meilleur],
                              "r": r[meilleur],
                              "lags_significatifs": [l for l, s in zip(LAGS, sig) if s]})
    if not series:
        raise ToolInputError("Aucune correlation pour ces indices.")
    spec = {
        "genre": "courbes",
        "titre": "Corrélation selon le décalage",
        "sous_titre": "%s · %s · point plein = significatif (p_neff < 0,05)"
                      % (_libelle_phase(phase), METRIQUES_AFFICHAGE[metrique]),
        "donnees": {"x": LAGS, "x_categoriel": True, "x_label": "décalage (mois)",
                    "y_label": "r de Pearson", "series": series,
                    "ligne_zero": True},
    }
    return spec, {"phase": phase, "metrique": metrique,
                  "series": resume_series}, SOURCE_CORRELATIONS


def _sst_series(params, data):
    indices = _indices(params)
    agregation = champ_enum(params, "aggregation", ["mensuelle", "annuelle"],
                            defaut="annuelle")
    df = data["indices"]
    manquants = [i for i in indices if i not in df.columns]
    if manquants:
        raise ToolInputError("Indices absents des donnees: %s." % ", ".join(manquants))
    annee_min = champ_entier(params, "year_min", mini=1900, maxi=2100)
    annee_max = champ_entier(params, "year_max", mini=1900, maxi=2100)
    dates = df["date"]
    if annee_min is not None:
        df = df[dates.dt.year >= annee_min]
    if annee_max is not None:
        df = df[df["date"].dt.year <= annee_max]
    if df.empty:
        raise ToolInputError("Aucune valeur d'indice sur cette periode.")
    frequence = "MS" if agregation == "mensuelle" else "YS"
    agrege = df.set_index("date")[indices].resample(frequence).mean()
    if agregation == "mensuelle" and len(agrege) > 360:
        raise ToolInputError("Serie mensuelle trop longue (%d mois): restreins "
                             "la periode a 30 ans ou passe en annuelle."
                             % len(agrege))
    x = [d.strftime("%Y-%m") if agregation == "mensuelle" else int(d.year)
         for d in agrege.index]
    series, resume = [], []
    for indice in indices:
        valeurs = [arrondir(v, 3) for v in agrege[indice]]
        series.append({"nom": indice, "y": valeurs})
        propre = agrege[indice].dropna()
        resume.append({"indice": indice,
                       "moyenne": arrondir(propre.mean(), 3),
                       "maximum": {"date": str(x[list(agrege.index).index(propre.idxmax())]),
                                   "valeur": arrondir(propre.max(), 3)},
                       "minimum": {"date": str(x[list(agrege.index).index(propre.idxmin())]),
                                   "valeur": arrondir(propre.min(), 3)}})
    spec = {
        "genre": "courbes",
        "titre": "Anomalies SST",
        "sous_titre": "moyenne %s, de %s à %s · écart à la climatologie"
                      % (agregation, x[0], x[-1]),
        "donnees": {"x": x, "x_categoriel": agregation == "mensuelle",
                    "x_label": "", "y_label": "anomalie (°C)",
                    "series": series, "ligne_zero": True},
    }
    if agregation == "mensuelle":
        # Une etiquette par an au plus, sinon les dates se chevauchent.
        spec["donnees"]["x_categoriel"] = False
        spec["donnees"]["x"] = [int(v[:4]) + (int(v[5:]) - 1) / 12.0 for v in x]
        spec["donnees"]["x_label"] = "année"
    return spec, {"agregation": agregation, "periode": [x[0], x[-1]],
                  "series": resume}, SOURCE_INDICES


def _filtrer_evenements(params, df):
    filtres = {}
    if params.get("phase"):
        phase = resoudre_phase(params["phase"])
        if phase != "Toutes phases":
            df = df[df["phase"] == phase]
            filtres["phase"] = phase
    region = champ_texte(params, "region", maxi=60)
    if region:
        df = df[_correspond(df["centroid_region"], region)]
        filtres["region"] = region
    return df, filtres


def _suffixe(filtres):
    morceaux = []
    if "phase" in filtres:
        morceaux.append(_libelle_phase(filtres["phase"]))
    if "region" in filtres:
        morceaux.append("région %s" % filtres["region"])
    return (" · " + ", ".join(morceaux)) if morceaux else ""


def _events_per_year(params, data):
    tout = data["events"]
    debut = champ_entier(params, "year_min", mini=1900, maxi=2100) or int(tout["year"].min())
    fin = champ_entier(params, "year_max", mini=1900, maxi=2100) or int(tout["year"].max())
    if debut > fin:
        raise ToolInputError("year_min doit etre inferieur ou egal a year_max.")
    df, filtres = _filtrer_evenements(params, tout)
    df = df[df["year"].between(debut, fin)]
    serie = _serie_annuelle(df, "n_events", debut, fin)
    annees = [int(a) for a in serie.index]
    valeurs = [int(v) for v in serie.values]
    tendance, pente, p = None, None, None
    if len(annees) >= 8 and len(set(valeurs)) > 1:
        pente, ordonnee = stats.theilslopes(valeurs, annees)[:2]
        p = stats.kendalltau(annees, valeurs)[1]
        tendance = {"nom": "tendance (pente de Sen)",
                    "y": [round(ordonnee + pente * a, 2) for a in annees]}
    spec = {
        "genre": "barres",
        "titre": "Événements extrêmes par an",
        "sous_titre": "%d-%d%s" % (debut, fin, _suffixe(filtres)),
        "donnees": {"categories": annees, "valeurs": valeurs,
                    "x_label": "année", "y_label": "nombre d'événements",
                    "tendance": tendance},
    }
    maxi = max(range(len(valeurs)), key=lambda k: valeurs[k]) if valeurs else None
    resume = {"filtres": filtres, "periode": [debut, fin],
              "n_evenements": int(sum(valeurs)),
              "annee_record": ({"annee": annees[maxi], "n": valeurs[maxi]}
                               if maxi is not None else None),
              "annees_sans_evenement": int(sum(1 for v in valeurs if v == 0)),
              "pente_sen_par_decennie": arrondir(pente * 10, 3) if pente is not None else None,
              "p_mann_kendall": arrondir(p, 4)}
    return spec, resume, SOURCE_EVENTS


def _events_by_month(params, data):
    df, filtres = _filtrer_evenements(params, data["events"])
    comptes = df.groupby("month").size()
    mois = [m for m in range(1, 13) if comptes.get(m, 0) > 0] or [5, 6, 7, 8, 9, 10]
    valeurs = [int(comptes.get(m, 0)) for m in mois]
    spec = {
        "genre": "barres",
        "titre": "Saisonnalité des événements extrêmes",
        "sous_titre": "nombre d'événements par mois%s" % _suffixe(filtres),
        "donnees": {"categories": [MOIS[m - 1][:4] for m in mois],
                    "valeurs": valeurs, "x_label": "mois",
                    "y_label": "nombre d'événements"},
    }
    total = sum(valeurs)
    return spec, {"filtres": filtres, "n_evenements": total,
                  "par_mois": {MOIS[m - 1]: v for m, v in zip(mois, valeurs)}}, SOURCE_EVENTS


def _events_by_region(params, data):
    df, filtres = _filtrer_evenements(params, data["events"])
    limite = champ_entier(params, "limit", mini=1, maxi=14, defaut=10)
    comptes = df.groupby("centroid_region").size().sort_values(ascending=False)
    comptes = comptes.head(limite)
    if comptes.empty:
        raise ToolInputError("Aucun evenement pour ces filtres.")
    spec = {
        "genre": "barres",
        "titre": "Événements extrêmes par région",
        "sous_titre": "région du centroïde%s" % _suffixe(filtres),
        "hauteur_pouces": max(1.8, 0.24 * len(comptes) + 0.6),
        "donnees": {"categories": list(comptes.index),
                    "valeurs": [int(v) for v in comptes.values],
                    "x_label": "région", "y_label": "nombre d'événements",
                    "horizontal": True},
    }
    return spec, {"filtres": filtres, "total_filtre": int(len(df)),
                  "regions": {r: int(v) for r, v in comptes.items()}}, SOURCE_EVENTS


def _cluster_profile(params, data):
    phase = _phase_requise(params, "clustering", data["clustering"])
    cle = champ_enum(params, "metric", sorted(METRIQUES_CLUSTER), defaut="n_events")
    colonne, libelle = METRIQUES_CLUSTER[cle]
    chars = data["clustering"][phase]["chars"].sort_values("cluster")
    valeurs = [arrondir(v, 2) for v in chars[colonne]]
    spec = {
        "genre": "barres",
        "titre": "Profil des clusters K-Means",
        "sous_titre": "%s · %s" % (_libelle_phase(phase), libelle),
        "donnees": {"categories": ["C%d" % int(c) for c in chars["cluster"]],
                    "valeurs": valeurs, "x_label": "cluster",
                    "y_label": libelle},
    }
    return spec, {"phase": phase, "metrique": cle,
                  "clusters": {"C%d" % int(c): v for c, v in zip(chars["cluster"], valeurs)},
                  "rappel": "cluster = configuration oceanique globale, pas une zone"}, \
        SOURCE_CLUSTERING


_TYPES = {
    "correlation_heatmap": _correlation_heatmap,
    "correlation_lags": _correlation_lags,
    "sst_series": _sst_series,
    "events_per_year": _events_per_year,
    "events_by_month": _events_by_month,
    "events_by_region": _events_by_region,
    "cluster_profile": _cluster_profile,
}


def construire(params, data):
    """Specification + resume, sans magasin: utilise par run() et les tests."""
    genre = champ_enum(params, "type", TYPES)
    if genre is None:
        raise ToolInputError("Le parametre type est requis. Valeurs acceptees: %s."
                             % ", ".join(TYPES))
    spec, resume, source = _TYPES[genre](params, data)
    spec["type"] = genre
    spec["source"] = source
    return spec, resume


def run(params, data, figures=None, session_id=""):
    if figures is None:
        raise ToolInputError("L'affichage de figures n'est pas disponible ici.")
    spec, resume = construire(params, data)
    figure = figures.deposer(session_id, spec)
    return {
        "figure_id": figure.id,
        "type": spec["type"],
        "titre": spec["titre"],
        "sous_titre": spec["sous_titre"],
        "affichee": True,
        "resume": resume,
        "consigne": ("La figure s'affiche sous ta reponse, avec son titre. "
                     "Ne la decris pas point par point: dis ce qu'elle montre "
                     "d'essentiel, a partir du resume ci-dessus."),
        "source": spec["source"],
    }
