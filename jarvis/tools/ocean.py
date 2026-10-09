"""Outil get_ocean_state : l'ocean (anomalie de SST) a n'importe quelle date.

get_sst_index donne les 11 indices publies du projet (extraction du script
d'indices). Cet outil lit les CHAMPS eux-memes (jarvis/sources.py) : un jour
(fichiers OISST journaliers, 0,25 deg) ou un mois (cube mensuel a 1 deg, a
defaut les fichiers journaliers), sur une boite d'indice, une zone nommee ou
une boite libre, avec le rang de la valeur parmi les memes mois 1983-2023 et,
sur demande, la carte mondiale.

Moyenne ponderee par cos(latitude), pixels d'ocean seulement. Pour la valeur
PUBLIEE d'un indice (celle des correlations), get_sst_index fait foi : les
deux peuvent differer de quelques centiemes (ponderation, grille).
"""
from datetime import date as Date
from datetime import timedelta

import numpy as np

from .. import cartes
from .. import sources as S
from .common import ToolInputError, arrondir, champ_texte

NAME = "get_ocean_state"
LABEL = "État de l'océan à une date"
PERMISSION = "public"
DATASETS = ()

# Zones nommees hors indices : (lon0, lon1, lat0, lat1), definition ClimatSen.
ZONES_NOMMEES = {
    "golfe_de_guinee": [(-15, 10, -5, 5)],
    "upwelling_senegalo_mauritanien": [(-20, -16, 12, 22)],
    "atlantique_equatorial": [(-40, 10, -5, 5)],
    "mediterranee": [(-5, 36, 30, 45)],
}
DIPOLES = {"IOD": ("IOD_ouest", "IOD_est"), "AMM": ("TNA", "TSA")}
ZONES = sorted(list(cartes.BOITES_RESUME) + list(DIPOLES) + list(ZONES_NOMMEES))
MAX_MOIS = 12
MAX_JOURS = 31

DESCRIPTION = (
    "Etat de l'ocean (anomalie de temperature de surface, degC) a N'IMPORTE QUELLE date "
    "1983-2023 : un jour (date AAAA-MM-JJ, champ OISST journalier) ou un mois (AAAA-MM), ou "
    "une periode (date_end : 12 mois ou 31 jours au plus). Zone : boite d'un indice (Nino34, "
    "TNA, ATL3, AMO, IOD = ouest - est, AMM = TNA - TSA...), zone nommee (golfe_de_guinee, "
    "upwelling_senegalo_mauritanien, atlantique_equatorial, mediterranee) ou boite libre "
    "(box = [lon_min, lon_max, lat_min, lat_max], 60S-60N). Donne la moyenne, le rang de la "
    "valeur parmi les memes mois 1983-2023 (pour un mois), et map=true affiche la carte "
    "mondiale. Pour la valeur PUBLIEE d'un indice (celle des correlations), get_sst_index "
    "fait foi."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Jour AAAA-MM-JJ ou mois AAAA-MM."},
        "date_end": {"type": "string", "description": "Fin de periode, meme format."},
        "zone": {"type": "string", "enum": ZONES, "description": "Boite d'indice ou zone nommee."},
        "box": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
                "description": "Boite libre [lon_min, lon_max, lat_min, lat_max] en degres."},
        "map": {"type": "boolean", "description": "Afficher la carte mondiale."},
    },
    "required": ["date"],
}


def _granularite(texte, nom):
    texte = (texte or "").strip()
    try:
        if len(texte) == 7:
            a, m = texte.split("-")
            d = Date(int(a), int(m), 1)
            return "mois", d
        return "jour", S._date(texte, S.DEBUT_OISST, S.FIN_OISST, nom)
    except (ValueError, S.DemandeInvalide) as exc:
        raise ToolInputError("%s invalide : %r (AAAA-MM-JJ ou AAAA-MM, 1983-2023). %s"
                             % (nom, texte, exc if isinstance(exc, S.DemandeInvalide) else ""))


def _boites(params):
    box = params.get("box")
    if box is not None:
        try:
            lon0, lon1, lat0, lat1 = (float(v) for v in box)
        except (TypeError, ValueError):
            raise ToolInputError("box = [lon_min, lon_max, lat_min, lat_max] en nombres.")
        if not (-180 <= lon0 < lon1 <= 180 and -60 <= lat0 < lat1 <= 60):
            raise ToolInputError("box hors domaine : longitudes -180..180 croissantes, "
                                 "latitudes -60..60 croissantes.")
        return "boite libre", {"zone": [(lon0, lon1, lat0, lat1)]}
    zone = params.get("zone")
    if zone in DIPOLES:
        ouest, est = DIPOLES[zone]
        return zone, {"+": cartes.BOITES_RESUME[ouest], "-": cartes.BOITES_RESUME[est]}
    if zone in cartes.BOITES_RESUME:
        return zone, {"zone": cartes.BOITES_RESUME[zone]}
    if zone in ZONES_NOMMEES:
        return zone, {"zone": ZONES_NOMMEES[zone]}
    raise ToolInputError("zone ou box requis. Zones : %s." % ", ".join(ZONES))


def _valeur(champ, lats, lons, boites):
    if "+" in boites:
        a, _ = S.moyenne_boite(champ, lats, lons, boites["+"])
        b, _ = S.moyenne_boite(champ, lats, lons, boites["-"])
        return None if a is None or b is None else a - b
    v, _ = S.moyenne_boite(champ, lats, lons, boites["zone"])
    return v


def _mois_de(d0, d1):
    out, d = [], d0
    while d <= d1:
        out.append((d.year, d.month))
        d = Date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def _champ(gran, d0, d1):
    """(champ moyen a 1 deg, lats, lons, source, n pas de temps)."""
    import warnings
    champs = []
    if gran == "mois":
        mois = _mois_de(d0, d1)
        if len(mois) > MAX_MOIS:
            raise ToolInputError("Periode de %d mois au plus." % MAX_MOIS)
        for a, m in mois:
            z, la, lo, src = S.sst_mois(a, m)
            champs.append(z)
    else:
        n = (d1 - d0).days + 1
        if n > MAX_JOURS:
            raise ToolInputError("Periode de %d jours au plus (prendre des mois au-dela)."
                                 % MAX_JOURS)
        d = d0
        while d <= d1:
            z, la0, lo0 = S.sst_jour(d)
            z, la, lo = S.reduire_1deg(z, la0, lo0)
            champs.append(z)
            d += timedelta(days=1)
        src = S.SOURCE_OISST
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(np.stack(champs), axis=0), la, lo, src, len(champs)


def _rang(gran, d0, d1, boites, valeur):
    """Rang de la valeur parmi les memes mois de chaque annee 1983-2023 (cube)."""
    if gran != "mois" or valeur is None:
        return None
    try:
        c = S.cube()
    except S.SourceAbsente:
        return None
    mois = _mois_de(d0, d1)
    decal = [(a - mois[0][0], m) for a, m in mois]
    serie = {}
    for annee in range(1983, 2024):
        cibles = [(annee + da, m) for da, m in decal]
        if all(c.a_le_mois(a, m) for a, m in cibles):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")      # pixels de terre : moyenne vide
                champ = np.nanmean(np.stack([c.mensuel(a, m) for a, m in cibles]), axis=0)
            v = _valeur(champ, c.lats, c.lons, boites)
            if v is not None:
                serie[annee] = v
    if len(serie) < 10 or mois[0][0] not in serie:
        return None
    tri = sorted(serie, key=lambda a: -serie[a])
    return {"rang_du_plus_chaud": tri.index(mois[0][0]) + 1, "sur": len(serie),
            "annees_les_plus_chaudes": [{"annee": a, "anomalie_degC": arrondir(serie[a], 2)}
                                        for a in tri[:3]],
            "annees_les_plus_froides": [{"annee": a, "anomalie_degC": arrondir(serie[a], 2)}
                                        for a in tri[-3:][::-1]],
            "note": "anomalies brutes : le rechauffement de fond place les annees recentes en tete"}


def run(params, data, figures=None, session_id=""):
    gran, d0 = _granularite(champ_texte(params, "date", maxi=10), "date")
    fin = champ_texte(params, "date_end", maxi=10)
    gran1, d1 = _granularite(fin, "date_end") if fin else (gran, d0)
    if gran1 != gran:
        raise ToolInputError("date et date_end doivent avoir le meme format.")
    if d1 < d0:
        raise ToolInputError("date_end precede date.")
    if gran == "mois" and not (S.DEBUT_OISST <= d0 and d1 <= S.FIN_OISST):
        raise ToolInputError("Mois disponibles de 1983-01 a 2023-12.")
    nom, boites = _boites(params)
    try:
        champ, la, lo, src, n = _champ(gran, d0, d1)
    except S.SourceAbsente as exc:
        raise ToolInputError("Donnee brute absente de ce serveur : %s" % exc)
    except S.DemandeInvalide as exc:
        raise ToolInputError(str(exc))
    valeur = _valeur(champ, la, lo, boites)
    periode = (d0.isoformat() if gran == "jour" else d0.strftime("%Y-%m"))
    if d1 != d0:
        periode += " a " + (d1.isoformat() if gran == "jour" else d1.strftime("%Y-%m"))
    sortie = {
        "zone": nom, "boites_degres": {k: v for k, v in boites.items()},
        "periode": periode, "resolution": "jour" if gran == "jour" else "mois",
        "pas_de_temps_moyennes": n,
        "anomalie_moyenne_degC": arrondir(valeur, 2),
        "lecture": "anomalie par rapport a la climatologie OISST (pas une temperature)",
    }
    if nom in DIPOLES:
        sortie["definition"] = "%s = %s - %s" % (nom, *DIPOLES[nom])
    rang = _rang(gran, d0, d1, boites, valeur)
    if rang:
        sortie["contexte_1983_2023"] = rang
    if nom in cartes.BOITES_RESUME or nom in DIPOLES:
        sortie["valeur_publiee"] = "get_sst_index donne la valeur de l'indice utilisee par les correlations"
    if params.get("map") is True and figures is not None:
        sortie.update(_carte(champ, la, lo, periode, src, figures, session_id))
    sortie["source"] = src
    return sortie


def _carte(champ, la, lo, periode, src, figures, session_id):
    haut = max(abs(float(np.nanpercentile(champ, 2))), abs(float(np.nanpercentile(champ, 98))))
    vlim = round(min(max(haut, 0.5), 3.0), 2)
    spec = {
        "genre": "carte_sst", "type": "get_ocean_state",
        "titre": "L'océan, %s" % periode,
        "sous_titre": "anomalie de SST · 60°S-60°N · 1°",
        "donnees": {"grille": [[None if not np.isfinite(v) else round(float(v), 2) for v in ligne]
                               for ligne in champ],
                    "lats": [round(float(v), 2) for v in la],
                    "lons": [round(float(v), 2) for v in lo], "vlim": vlim},
        "source": src,
    }
    fig = figures.deposer(session_id, spec)
    return {"figure_id": fig.id, "carte_affichee": True, "echelle_couleurs_degC": [-vlim, vlim]}
