"""Briques partagees par les outils: validation, vocabulaire, formatage.

La validation est volontairement manuelle plutot que confiee a Pydantic: les
messages d'erreur partent vers le MODELE, pas vers un developpeur. Un message
francais qui enonce les valeurs acceptees ("phase inconnue: 'ete'. Valeurs
acceptees: ...") permet a Claude de se corriger au tour suivant, la ou une
trace de validation anglaise le laisserait tourner en rond.
"""
import math
import unicodedata

import pandas as pd


class ToolInputError(ValueError):
    """Parametre invalide. Devient un tool_result en erreur, pas une 500."""


# --- vocabulaire de la plateforme -------------------------------------------
INDICES = ["Nino12", "Nino3", "Nino34", "Nino4", "IOD", "IOBM",
           "TNA", "TSA", "ATL3", "AMM", "AMO"]

INDICES_LABELS = {
    "Nino12": "Nino 1+2 (Pacifique est, cote sud-americaine)",
    "Nino3":  "Nino 3 (Pacifique equatorial est)",
    "Nino34": "Nino 3.4 (indice ENSO de reference)",
    "Nino4":  "Nino 4 (Pacifique equatorial ouest)",
    "IOD":    "Dipole de l ocean Indien (ouest moins est)",
    "IOBM":   "Mode de bassin de l ocean Indien",
    "TNA":    "Atlantique tropical nord",
    "TSA":    "Atlantique tropical sud",
    "ATL3":   "Atlantique equatorial (langue d eau froide)",
    "AMM":    "Mode meridien atlantique (TNA moins TSA)",
    "AMO":    "Oscillation multidecennale atlantique",
}

PHASES = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]
PHASES_TOUTES = PHASES + ["Toutes phases"]

PHASES_LABELS = {
    "Phase_1_debut":  "debut de saison (mai-juin)",
    "Phase_2_pleine": "pleine saison (juillet-aout)",
    "Phase_3_fin":    "fin de saison (septembre-octobre)",
    "Toutes phases":  "toutes phases confondues",
    "All_phases":     "toutes phases confondues",
}

METRIQUES = {
    "max_precip":       "precipitation maximale mensuelle (mm)",
    "mean_precip":      "precipitation moyenne (mm)",
    "max_anomaly":      "anomalie maximale moyenne (sigma)",
    "coverage_percent": "couverture spatiale moyenne (%)",
    "n_events":         "nombre d evenements extremes",
}

SOURCE_INDICES = "OISST v2 (NOAA), anomalies journalieres, 1983-2023"
SOURCE_EVENTS = "CHIRPS 1981-2023, evenements superieurs a 2 sigma sur le Senegal"
SOURCE_CORRELATIONS = (
    "Correlations annuelles par phase (1983-2023), p-values corrigees de "
    "l autocorrelation AR1 (n_eff, Chelton 1983)"
)
SOURCE_CLUSTERING = (
    "K-Means sur les champs SST globaux (OISST v2) du jour de chaque "
    "evenement extreme, apres reduction par ACP"
)


def normalise(texte) -> str:
    """Minuscules sans accents ni ponctuation.

    Permet de faire correspondre 'Kedougou' et 'Kedougou', 'Nino 3.4' et
    'nino34': le modele ne tape pas toujours la forme exacte du fichier.
    """
    if texte is None:
        return ""
    brut = unicodedata.normalize("NFKD", str(texte))
    sans_accents = "".join(c for c in brut if not unicodedata.combining(c))
    return "".join(c for c in sans_accents.lower() if c.isalnum())


_INDICES_PAR_CLE = {normalise(i): i for i in INDICES}
_INDICES_PAR_CLE.update({
    "nino1":      "Nino12",
    "nino2":      "Nino12",
    "nino1plus2": "Nino12",
    "enso":       "Nino34",
    "nino":       "Nino34",
    "dmi":        "IOD",
    "atl":        "ATL3",
})

_PHASES_PAR_CLE = {normalise(p): p for p in PHASES_TOUTES}
_PHASES_PAR_CLE.update({
    "1": "Phase_1_debut", "phase1": "Phase_1_debut", "debut": "Phase_1_debut",
    "debutdesaison": "Phase_1_debut", "mai": "Phase_1_debut",
    "juin": "Phase_1_debut", "maijuin": "Phase_1_debut",
    "2": "Phase_2_pleine", "phase2": "Phase_2_pleine", "pleine": "Phase_2_pleine",
    "pleinesaison": "Phase_2_pleine", "juillet": "Phase_2_pleine",
    "aout": "Phase_2_pleine", "juilletaout": "Phase_2_pleine",
    "3": "Phase_3_fin", "phase3": "Phase_3_fin", "fin": "Phase_3_fin",
    "findesaison": "Phase_3_fin", "septembre": "Phase_3_fin",
    "octobre": "Phase_3_fin", "septembreoctobre": "Phase_3_fin",
    "toutes": "Toutes phases", "toutesphases": "Toutes phases",
    "allphases": "Toutes phases", "all": "Toutes phases",
})


def resoudre_indice(valeur) -> str:
    cle = normalise(valeur)
    if cle in _INDICES_PAR_CLE:
        return _INDICES_PAR_CLE[cle]
    raise ToolInputError(
        "Indice SST inconnu: %r. Valeurs acceptees: %s."
        % (valeur, ", ".join(INDICES))
    )


def resoudre_phase(valeur) -> str:
    cle = normalise(valeur)
    if cle in _PHASES_PAR_CLE:
        return _PHASES_PAR_CLE[cle]
    raise ToolInputError(
        "Phase inconnue: %r. Valeurs acceptees: %s."
        % (valeur, ", ".join(PHASES_TOUTES))
    )


# --- validation de champs ----------------------------------------------------
def champ_entier(params, nom, mini=None, maxi=None, defaut=None):
    valeur = params.get(nom, defaut)
    if valeur is None:
        return None
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        raise ToolInputError("%s doit etre un nombre entier (recu: %r)." % (nom, valeur))
    if mini is not None and entier < mini:
        raise ToolInputError(
            "%s doit etre superieur ou egal a %d (recu: %d)." % (nom, mini, entier))
    if maxi is not None and entier > maxi:
        raise ToolInputError(
            "%s doit etre inferieur ou egal a %d (recu: %d)." % (nom, maxi, entier))
    return entier


def champ_decimal(params, nom, defaut=None):
    valeur = params.get(nom, defaut)
    if valeur is None:
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        raise ToolInputError("%s doit etre un nombre (recu: %r)." % (nom, valeur))


def champ_bool(params, nom, defaut=False):
    valeur = params.get(nom, defaut)
    if isinstance(valeur, bool):
        return valeur
    if valeur is None:
        return defaut
    if isinstance(valeur, str):
        if normalise(valeur) in ("true", "vrai", "oui", "1"):
            return True
        if normalise(valeur) in ("false", "faux", "non", "0"):
            return False
    raise ToolInputError("%s doit valoir true ou false (recu: %r)." % (nom, valeur))


def champ_enum(params, nom, valeurs, defaut=None):
    valeur = params.get(nom, defaut)
    if valeur is None:
        return None
    cle = normalise(valeur)
    table = {normalise(v): v for v in valeurs}
    if cle not in table:
        raise ToolInputError(
            "%s inconnu: %r. Valeurs acceptees: %s." % (nom, valeur, ", ".join(valeurs))
        )
    return table[cle]


def champ_texte(params, nom, maxi=80, defaut=None):
    valeur = params.get(nom, defaut)
    if valeur is None:
        return None
    texte = str(valeur).strip()
    if not texte:
        return None
    if len(texte) > maxi:
        raise ToolInputError("%s est trop long (%d caracteres maximum)." % (nom, maxi))
    return texte


def champ_date(params, nom, defaut=None):
    """Accepte AAAA, AAAA-MM ou AAAA-MM-JJ. Retourne (Timestamp, precision)."""
    valeur = params.get(nom, defaut)
    if valeur is None:
        return None, None
    texte = str(valeur).strip()
    for gabarit, precision in (("%Y-%m-%d", "jour"), ("%Y-%m", "mois"), ("%Y", "annee")):
        try:
            return pd.to_datetime(texte, format=gabarit), precision
        except (ValueError, TypeError):
            continue
    raise ToolInputError(
        "%s doit etre une date au format AAAA-MM-JJ, AAAA-MM ou AAAA (recu: %r)."
        % (nom, valeur)
    )


# --- formatage ---------------------------------------------------------------
def arrondir(valeur, decimales=3):
    """Float compatible JSON: NaN et infinis deviennent None.

    json.dumps ecrirait sinon NaN, qui n est pas du JSON valide et que le
    modele lirait comme un chiffre.
    """
    if valeur is None:
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(nombre):
        return None
    return round(nombre, decimales)


def jour(valeur):
    if valeur is None or pd.isna(valeur):
        return None
    return pd.Timestamp(valeur).strftime("%Y-%m-%d")


def etoiles(p_value) -> str:
    """Memes seuils que _sig() du script 04 et du dashboard."""
    p = arrondir(p_value, 10)
    if p is None:
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""
