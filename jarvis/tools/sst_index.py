"""Outil get_sst_index: valeurs des indices de temperature de surface oceanique.

Lit la meme serie que le module "Indices SST" du dashboard
(data/raw/climate_indices/daily_indices_all.csv via load_sst).
"""
import pandas as pd

from .common import (INDICES, INDICES_LABELS, SOURCE_INDICES, ToolInputError,
                     arrondir, champ_date, champ_enum, jour, resoudre_indice)

NAME = "get_sst_index"
LABEL = "Lecture des indices SST"
PERMISSION = "public"
DATASETS = ("indices",)

DESCRIPTION = (
    "Valeurs d un indice de temperature de surface de la mer (SST) sur la "
    "periode 1983-2023: moyenne, extremes dates, et serie mensuelle ou "
    "annuelle. Utilise cet outil des qu une valeur chiffree d indice est "
    "demandee (etat du Nino, anomalie de l Atlantique, evolution d un indice "
    "sur une periode). Les valeurs sont des ANOMALIES en degres Celsius par "
    "rapport a la climatologie, pas des temperatures absolues."
)

PAS = ["mensuelle", "annuelle"]
MAX_POINTS = 24

SCHEMA = {
    "type": "object",
    "properties": {
        "index": {
            "type": "string",
            "enum": INDICES,
            "description": "Indice SST. Nino12, Nino3, Nino34, Nino4 pour ENSO "
                           "(Pacifique); IOD et IOBM pour l ocean Indien; TNA, "
                           "TSA, ATL3, AMM, AMO pour l Atlantique.",
        },
        "date": {
            "type": "string",
            "description": "Valeur a une date precise. Format AAAA-MM-JJ, "
                           "AAAA-MM (moyenne du mois) ou AAAA (moyenne de "
                           "l annee). Exclusif avec start/end.",
        },
        "start": {"type": "string",
                  "description": "Debut de periode (AAAA-MM-JJ, AAAA-MM ou AAAA). "
                                 "Defaut: debut de la couverture (1983)."},
        "end": {"type": "string",
                "description": "Fin de periode (AAAA-MM-JJ, AAAA-MM ou AAAA). "
                               "Defaut: fin de la couverture (2023)."},
        "aggregation": {"type": "string", "enum": PAS,
                        "description": "Pas de la serie retournee. Defaut: mensuelle. "
                                       "Bascule automatiquement en annuelle au-dela "
                                       "de 24 points."},
    },
    "required": ["index"],
}


def _borne(valeur, precision, fin=False):
    """Convertit une date partielle en borne de periode.

    'AAAA' en borne de fin doit couvrir jusqu au 31 decembre, pas s arreter au
    1er janvier: sans cela une demande sur '2012' ne renverrait qu un jour.
    """
    if valeur is None:
        return None
    if not fin:
        return valeur
    if precision == "annee":
        return valeur + pd.offsets.YearEnd(0)
    if precision == "mois":
        return valeur + pd.offsets.MonthEnd(0)
    return valeur


def run(params, data):
    df = data["indices"]
    indice = resoudre_indice(params.get("index"))
    if indice not in df.columns:
        raise ToolInputError(
            "Indice %s absent du fichier de donnees. Indices disponibles: %s."
            % (indice, ", ".join(c for c in df.columns if c != "date"))
        )

    pas = champ_enum(params, "aggregation", PAS, defaut="mensuelle")
    date_exacte, precision_exacte = champ_date(params, "date")
    debut, precision_debut = champ_date(params, "start")
    fin, precision_fin = champ_date(params, "end")

    if date_exacte is not None:
        debut = date_exacte
        fin = _borne(date_exacte, precision_exacte, fin=True)
    else:
        debut = _borne(debut, precision_debut)
        fin = _borne(fin, precision_fin, fin=True)

    serie = df[["date", indice]].dropna().sort_values("date")
    couverture = (jour(serie["date"].min()), jour(serie["date"].max()))

    if debut is not None:
        serie = serie[serie["date"] >= debut]
    if fin is not None:
        serie = serie[serie["date"] <= fin]

    if serie.empty:
        raise ToolInputError(
            "Aucune donnee pour %s sur la periode demandee. La couverture "
            "disponible va du %s au %s." % (indice, couverture[0], couverture[1])
        )

    valeurs = serie[indice]
    ligne_min = serie.loc[valeurs.idxmin()]
    ligne_max = serie.loc[valeurs.idxmax()]
    derniere = serie.iloc[-1]

    notes = []
    if date_exacte is None and (debut is None or fin is None):
        notes.append("Periode par defaut: toute la couverture disponible.")

    groupes = serie.set_index("date")[indice]
    if pas == "mensuelle":
        agrege = groupes.resample("MS")
        if len(agrege.mean().dropna()) > MAX_POINTS:
            pas = "annuelle"
            notes.append(
                "Serie renvoyee au pas annuel: la periode demandee depasse "
                "%d mois." % MAX_POINTS
            )
    if pas == "annuelle":
        agrege = groupes.resample("YS")

    moyennes = agrege.mean().dropna()
    effectifs = agrege.count()
    gabarit = "%Y-%m" if pas == "mensuelle" else "%Y"
    points = [
        {"periode": horodate.strftime(gabarit),
         "valeur": arrondir(valeur, 3),
         "n_jours": int(effectifs.get(horodate, 0))}
        for horodate, valeur in moyennes.items()
    ]

    resultat = {
        "indice": indice,
        "description": INDICES_LABELS.get(indice, indice),
        "unite": "anomalie de SST en degres Celsius",
        "periode": {
            "debut": jour(serie["date"].min()),
            "fin": jour(serie["date"].max()),
            "n_jours": int(len(serie)),
        },
        "resume": {
            "moyenne": arrondir(valeurs.mean(), 3),
            "ecart_type": arrondir(valeurs.std(), 3),
            "minimum": {"valeur": arrondir(ligne_min[indice], 3),
                        "date": jour(ligne_min["date"])},
            "maximum": {"valeur": arrondir(ligne_max[indice], 3),
                        "date": jour(ligne_max["date"])},
            "derniere_valeur": {"valeur": arrondir(derniere[indice], 3),
                                "date": jour(derniere["date"])},
        },
        "serie": {"pas": pas, "points": points},
        "couverture_disponible": {"debut": couverture[0], "fin": couverture[1]},
        "source": SOURCE_INDICES,
    }
    if notes:
        resultat["note"] = " ".join(notes)
    return resultat
