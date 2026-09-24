"""Outil analyze_extreme_events: statistiques sur le catalogue (Phase 7).

search_extreme_events retrouve des evenements; cet outil en tire des
statistiques, sur le meme catalogue (load_events):

  tendance           les extremes deviennent-ils plus frequents ou plus
                     intenses ? Pente de Sen et test de Mann-Kendall, robustes
                     aux valeurs extremes, plutot qu'une regression lineaire
                     qu'un seul evenement hors norme peut faire basculer.
  comparer_periodes  deux periodes cote a cote, avec un test de Mann-Whitney.
  saisonnalite       repartition par mois et par phase.
  regions            classement des regions par nombre et intensite.

Pour la frequence, les annees SANS evenement comptent pour zero. Les oublier
(ce que ferait un simple groupby) supprimerait precisement les annees calmes et
fabriquerait une tendance.
"""
import numpy as np
import pandas as pd
from scipy import stats

from .common import (PHASES, PHASES_LABELS, PHASES_TOUTES, SOURCE_EVENTS,
                     ToolInputError, arrondir, champ_entier, champ_enum,
                     champ_texte, resoudre_phase)
from .events import _correspond

NAME = "analyze_extreme_events"
LABEL = "Analyse statistique des événements"
PERMISSION = "public"
DATASETS = ("events",)

ANALYSES = ["tendance", "comparer_periodes", "saisonnalite", "regions"]

METRIQUES_EVT = {
    "n_events": "nombre d evenements par an",
    "max_precip": "precipitation maximale moyenne par an (mm)",
    "mean_precip": "precipitation moyenne par an (mm)",
    "coverage_percent": "couverture spatiale moyenne par an (%)",
    "max_anomaly": "anomalie maximale moyenne par an (sigma)",
}

MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre"]

SEUIL = 0.05
LIMITE_MAX = 14

DESCRIPTION = (
    "Statistiques sur le catalogue des evenements de pluies extremes du "
    "Senegal (1981-2023). analysis=tendance: evolution d'annee en annee du "
    "nombre ou de l'intensite des evenements, avec pente de Sen par decennie "
    "et test de Mann-Kendall -- a utiliser pour 'les extremes augmentent-ils'. "
    "analysis=comparer_periodes: deux periodes comparees (frequence, "
    "intensite, test de Mann-Whitney). analysis=saisonnalite: repartition par "
    "mois et par phase. analysis=regions: classement des regions. Filtres "
    "communs: phase, region, year_min, year_max."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {"type": "string", "enum": ANALYSES,
                     "description": "Type d'analyse."},
        "metric": {"type": "string", "enum": sorted(METRIQUES_EVT),
                   "description": "tendance et comparer_periodes: grandeur "
                                  "etudiee. Defaut: n_events (frequence)."},
        "phase": {"type": "string", "enum": PHASES_TOUTES,
                  "description": "Ne garder qu'une phase de saison."},
        "region": {"type": "string",
                   "description": "Ne garder qu'une region (centroide)."},
        "year_min": {"type": "integer", "description": "Premiere annee."},
        "year_max": {"type": "integer", "description": "Derniere annee."},
        "period_1": {"type": "array", "items": {"type": "integer"},
                     "description": "comparer_periodes: [annee_debut, "
                                    "annee_fin] de la premiere periode. "
                                    "Defaut: premiere moitie."},
        "period_2": {"type": "array", "items": {"type": "integer"},
                     "description": "comparer_periodes: seconde periode. "
                                    "Defaut: seconde moitie."},
        "limit": {"type": "integer",
                  "description": "regions: nombre de regions (1 a 14, "
                                 "defaut 8)."},
    },
    "required": ["analysis"],
}


# --- selection commune -------------------------------------------------------
def _filtrer(params, df):
    """Applique les filtres communs. Retourne (selection, annees, filtres)."""
    # Bornes de la PERIODE D'ETUDE, prises avant tout filtre: une region sans
    # evenement avant 1990 doit compter des zeros sur 1981-1989.
    etude_debut, etude_fin = int(df["year"].min()), int(df["year"].max())
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

    annee_min = champ_entier(params, "year_min", mini=1900, maxi=2100)
    annee_max = champ_entier(params, "year_max", mini=1900, maxi=2100)
    debut = annee_min if annee_min is not None else etude_debut
    fin = annee_max if annee_max is not None else etude_fin
    if debut > fin:
        raise ToolInputError("year_min doit etre inferieur ou egal a year_max.")
    df = df[df["year"].between(debut, fin)]
    filtres["annees"] = [debut, fin]
    return df, (debut, fin), filtres


def _serie_annuelle(df, metrique, debut, fin):
    """Serie annuelle; pour la frequence, les annees vides valent 0."""
    annees = pd.Index(range(debut, fin + 1), name="year")
    if metrique == "n_events":
        return df.groupby("year").size().reindex(annees, fill_value=0).astype(float)
    return df.groupby("year")[metrique].mean().reindex(annees)


# --- tendance ------------------------------------------------------------------
def _tendance(params, df, bornes, filtres):
    metrique = champ_enum(params, "metric", sorted(METRIQUES_EVT), defaut="n_events")
    serie = _serie_annuelle(df, metrique, *bornes).dropna()
    if len(serie) < 8:
        return {"analyse": "tendance", "metrique": metrique, "filtres": filtres,
                "message": "Trop peu d'annees exploitables (%d) pour estimer "
                           "une tendance: il en faut au moins 8." % len(serie),
                "source": SOURCE_EVENTS}

    x = serie.index.to_numpy(dtype=float)
    y = serie.to_numpy(dtype=float)
    if np.allclose(y, y[0]):
        pente_sen, tau, p_mk = 0.0, None, None
    else:
        pente_sen = stats.theilslopes(y, x)[0]
        tau, p_mk = stats.kendalltau(x, y)
    moitie = len(serie) // 2
    premiere, seconde = serie.iloc[:moitie], serie.iloc[moitie:]

    if p_mk is None:
        verdict = "aucune variation"
    elif p_mk < SEUIL:
        verdict = ("tendance a la hausse significative" if pente_sen > 0
                   else "tendance a la baisse significative")
    else:
        verdict = "pas de tendance significative"

    return {
        "analyse": "tendance",
        "metrique": metrique,
        "metrique_label": METRIQUES_EVT[metrique],
        "filtres": filtres,
        "n_annees": int(len(serie)),
        "n_evenements": int(len(df)),
        "pente_sen_par_decennie": arrondir(pente_sen * 10, 3),
        "tau_kendall": arrondir(tau, 3),
        "p_mann_kendall": arrondir(p_mk, 4),
        "verdict": verdict,
        "moyenne_premiere_moitie": {
            "annees": [int(premiere.index[0]), int(premiere.index[-1])],
            "valeur": arrondir(premiere.mean(), 2)},
        "moyenne_seconde_moitie": {
            "annees": [int(seconde.index[0]), int(seconde.index[-1])],
            "valeur": arrondir(seconde.mean(), 2)},
        "annee_maximale": {"annee": int(serie.idxmax()),
                           "valeur": arrondir(serie.max(), 2)},
        "serie_annuelle": [[int(a), arrondir(v, 2)] for a, v in serie.items()],
        "limite": ("Mann-Kendall suppose des annees independantes; une "
                   "autocorrelation positive rendrait la p-value trop "
                   "optimiste. Une tendance n'est pas une projection."),
        "source": SOURCE_EVENTS,
    }


# --- comparer_periodes ---------------------------------------------------------
def _periode(params, nom, defaut):
    valeur = params.get(nom)
    if valeur is None:
        return defaut
    if not isinstance(valeur, (list, tuple)) or len(valeur) != 2:
        raise ToolInputError("%s doit etre une liste [annee_debut, annee_fin]." % nom)
    try:
        a, b = int(valeur[0]), int(valeur[1])
    except (TypeError, ValueError):
        raise ToolInputError("%s doit contenir deux annees entieres." % nom)
    if a > b:
        raise ToolInputError("%s: l'annee de debut depasse l'annee de fin." % nom)
    return a, b


def _resume_periode(df, a, b, metrique):
    sous = df[df["year"].between(a, b)]
    n_annees = b - a + 1
    annuelle = _serie_annuelle(sous, metrique, a, b)
    return sous, annuelle, {
        "annees": [a, b],
        "n_annees": n_annees,
        "n_evenements": int(len(sous)),
        "evenements_par_an": arrondir(len(sous) / n_annees, 2),
        "max_precip_moyen_mm": arrondir(sous["max_precip"].mean(), 1),
        "max_precip_median_mm": arrondir(sous["max_precip"].median(), 1),
        "couverture_moyenne_pct": arrondir(sous["coverage_percent"].mean(), 1),
    }


def _comparer(params, df, bornes, filtres):
    metrique = champ_enum(params, "metric", sorted(METRIQUES_EVT), defaut="n_events")
    debut, fin = bornes
    # Meme coupure que tendance: la premiere moitie compte n // 2 annees.
    milieu = debut + (fin - debut + 1) // 2 - 1
    p1 = _periode(params, "period_1", (debut, milieu))
    p2 = _periode(params, "period_2", (milieu + 1, fin))

    sous1, an1, r1 = _resume_periode(df, *p1, metrique)
    sous2, an2, r2 = _resume_periode(df, *p2, metrique)

    # Frequence: on compare les comptes ANNUELS (zeros compris); intensite:
    # on compare les evenements eux-memes.
    if metrique == "n_events":
        a, b = an1.dropna(), an2.dropna()
        objet = "nombre d'evenements par an"
    else:
        a, b = sous1[metrique].dropna(), sous2[metrique].dropna()
        objet = METRIQUES_EVT[metrique].replace(" par an", "") + ", par evenement"
    p = None
    if len(a) >= 3 and len(b) >= 3 and not (np.allclose(a, a.iloc[0])
                                            and np.allclose(b, a.iloc[0])):
        p = float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)

    return {
        "analyse": "comparer_periodes",
        "metrique": metrique,
        "grandeur_testee": objet,
        "filtres": filtres,
        "periode_1": r1,
        "periode_2": r2,
        "p_mann_whitney": arrondir(p, 4),
        "difference_significative": (p < SEUIL) if p is not None else None,
        "limite": "Periodes courtes: un test non significatif n'exclut pas "
                  "une difference reelle, il dit qu'on ne peut pas l'affirmer.",
        "source": SOURCE_EVENTS,
    }


# --- saisonnalite ----------------------------------------------------------------
def _saisonnalite(params, df, bornes, filtres):
    total = int(len(df))
    par_mois = []
    for mois, groupe in df.groupby("month"):
        par_mois.append({
            "mois": MOIS[int(mois) - 1],
            "n_evenements": int(len(groupe)),
            "part_pct": arrondir(100.0 * len(groupe) / total, 1) if total else None,
            "max_precip_moyen_mm": arrondir(groupe["max_precip"].mean(), 1),
        })
    par_phase = []
    for phase in PHASES:
        groupe = df[df["phase"] == phase]
        par_phase.append({
            "phase": phase,
            "phase_label": PHASES_LABELS[phase],
            "n_evenements": int(len(groupe)),
            "part_pct": arrondir(100.0 * len(groupe) / total, 1) if total else None,
            "max_precip_moyen_mm": arrondir(groupe["max_precip"].mean(), 1),
        })
    pic = max(par_mois, key=lambda m: m["n_evenements"]) if par_mois else None
    return {
        "analyse": "saisonnalite",
        "filtres": filtres,
        "n_evenements": total,
        "mois_le_plus_actif": pic["mois"] if pic else None,
        "par_mois": par_mois,
        "par_phase": par_phase,
        "source": SOURCE_EVENTS,
    }


# --- regions -------------------------------------------------------------------
def _regions(params, df, bornes, filtres):
    limite = champ_entier(params, "limit", mini=1, maxi=LIMITE_MAX, defaut=8)
    total = int(len(df))
    lignes = []
    for region, groupe in df.groupby("centroid_region"):
        phase_dominante = groupe["phase"].value_counts().idxmax()
        lignes.append({
            "region": region,
            "n_evenements": int(len(groupe)),
            "part_pct": arrondir(100.0 * len(groupe) / total, 1),
            "max_precip_moyen_mm": arrondir(groupe["max_precip"].mean(), 1),
            "max_precip_record_mm": arrondir(groupe["max_precip"].max(), 1),
            "phase_dominante": PHASES_LABELS.get(phase_dominante, phase_dominante),
        })
    lignes.sort(key=lambda l: -l["n_evenements"])
    return {
        "analyse": "regions",
        "filtres": filtres,
        "n_evenements": total,
        "n_regions": len(lignes),
        "regions": lignes[:limite],
        "precision": ("Region du centroide de l'evenement: un evenement "
                      "etendu touche aussi les regions voisines."),
        "source": SOURCE_EVENTS,
    }


def run(params, data):
    analyse = champ_enum(params, "analysis", ANALYSES)
    if analyse is None:
        raise ToolInputError("Le parametre analysis est requis. Valeurs "
                             "acceptees: %s." % ", ".join(ANALYSES))
    selection, bornes, filtres = _filtrer(params, data["events"])
    return {
        "tendance": _tendance,
        "comparer_periodes": _comparer,
        "saisonnalite": _saisonnalite,
        "regions": _regions,
    }[analyse](params, selection, bornes, filtres)
