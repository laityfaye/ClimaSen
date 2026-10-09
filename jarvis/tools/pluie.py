"""Outil get_rainfall : la pluie CHIRPS de n'importe quel jour ou periode.

Le catalogue (search_extreme_events) ne connait que les 1317 jours
d'evenement. Cet outil lit la grille CHIRPS elle-meme (jarvis/sources.py) :
n'importe quel jour 1981-2023, sur une zone (region, departement,
arrondissement, commune, pays) ou un point. Sur la grille du Senegal la pluie
est exacte (anomalie x ecart-type + climatologie = CHIRPS brut, verifie) ;
hors de cette grille (Afrique de l'Ouest) il faut le CHIRPS brut sur le
serveur, et seule la pluie est disponible (pas d'anomalie).

Moyenne de zone = moyenne simple des pixels de 0,25 deg retenus (meme regle
que l'indice de risque, script 26) : un petit departement urbain tient dans
un seul pixel, partage avec ses voisins.
"""
from datetime import timedelta

import numpy as np

from .. import sources as S
from .common import ToolInputError, arrondir, champ_bool, champ_decimal, champ_texte

NAME = "get_rainfall"
LABEL = "Pluie CHIRPS d'un jour ou d'une période"
PERMISSION = "public"
DATASETS = ("events",)

MAX_JOURS = 366
SEUIL_MM = 50.0

DESCRIPTION = (
    "Pluie CHIRPS de N'IMPORTE QUEL jour ou periode 1981-2023 (pas seulement les jours "
    "d'evenement extreme), sur une zone du Senegal (place = region, departement, "
    "arrondissement, commune ou 'Senegal') ou un point (lat, lon). Un jour : pluie moyenne "
    "de la zone (mm), maximum d'un pixel, anomalie (sigma), pixels au-dela de +2 sigma, et si "
    "le jour figure au catalogue des extremes. Une periode (date_end, 366 jours au plus) : "
    "cumul, cumul normal (climatologie 1981-2023) et ecart, jour le plus pluvieux, jours "
    "avec un pixel >= 50 mm ou > +2 sigma, evenements du catalogue. Hors du Senegal "
    "(Afrique de l'Ouest, 0-30 N, 20 W-20 E) : pluie seule, par lat/lon. map=true (un "
    "jour, zone du Senegal) affiche la carte du jour."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "description": "Jour AAAA-MM-JJ (debut si date_end)."},
        "date_end": {"type": "string", "description": "Fin de periode AAAA-MM-JJ (incluse)."},
        "place": {"type": "string",
                  "description": "Zone du Senegal en toutes lettres (Kolda, Pikine, "
                                 "commune de Mbao, region de Matam, Senegal)."},
        "lat": {"type": "number", "description": "Latitude d'un point (degres)."},
        "lon": {"type": "number", "description": "Longitude d'un point (degres, ouest negatif)."},
        "map": {"type": "boolean", "description": "Afficher la carte du jour (zone du Senegal)."},
    },
    "required": ["date"],
}


def _periode(params):
    try:
        d0 = S._date(champ_texte(params, "date", maxi=10), S.DEBUT_CHIRPS, S.FIN_CHIRPS)
        brut = champ_texte(params, "date_end", maxi=10)
        d1 = S._date(brut, S.DEBUT_CHIRPS, S.FIN_CHIRPS, "date_end") if brut else d0
    except S.DemandeInvalide as exc:
        raise ToolInputError(str(exc))
    if d1 < d0:
        raise ToolInputError("date_end (%s) precede date (%s)." % (d1, d0))
    if (d1 - d0).days + 1 > MAX_JOURS:
        raise ToolInputError("Periode de %d jours au plus." % MAX_JOURS)
    return d0, d1


def _zone(params):
    """(masque, description du lieu, methode) ou ('point', lat, lon)."""
    place = champ_texte(params, "place", maxi=80)
    lat, lon = champ_decimal(params, "lat"), champ_decimal(params, "lon")
    if place:
        from ..rapports import gazetteer
        r = gazetteer.charger().resoudre(place)
        if not r.candidats:
            raise ToolInputError("Lieu inconnu : %r.%s Pour un point, donne lat et lon."
                                 % (place, (" Proches : %s." % ", ".join(r.suggestions))
                                            if r.suggestions else ""))
        if len(r.candidats) > 1 and not r.exact:
            raise ToolInputError("Lieu ambigu : %s. Precise lequel."
                                 % "; ".join(l.libelle() for l in r.candidats[:6]))
        lieu = r.candidats[0]
        masque, methode = S.pixels_du_lieu(lieu)
        z = {"masque": masque, "lieu": lieu.libelle(), "methode": methode}
        if len(r.candidats) > 1:
            # Kaolack = region ET departement : dire lequel a ete retenu.
            z["autres_lieux_du_meme_nom"] = [l.libelle() for l in r.candidats[1:4]]
        return z
    if lat is None or lon is None:
        raise ToolInputError("Donne place (zone du Senegal) ou lat et lon.")
    if S.dans_grille_senegal(lat, lon):
        masque, methode = S.pixel_du_point(lat, lon)
        return {"masque": masque, "lieu": "point (%.3f, %.3f)" % (lat, lon), "methode": methode}
    return {"point": (lat, lon)}


def _hors_senegal(z, d0, d1):
    lat, lon = z["point"]
    valeurs, pixel = [], None
    d = d0
    while d <= d1:
        v, pixel = S.pluie_point_afrique_ouest(d, lat, lon)
        valeurs.append(v)
        d += timedelta(days=1)
    v = np.asarray(valeurs)
    sortie = {"lieu": "point (%.3f, %.3f), hors du Senegal" % (lat, lon),
              "pixel_chirps": {"lat": pixel[0], "lon": pixel[1]},
              "source": S.SOURCE_CHIRPS + ", Afrique de l'Ouest (fichier brut)",
              "limite": "hors de la grille du Senegal : ni anomalie ni climatologie, pluie seule"}
    if d0 == d1:
        sortie.update(date=str(d0), pluie_mm=arrondir(v[0], 1))
    else:
        k = int(np.argmax(v))
        sortie.update(periode=[str(d0), str(d1)], n_jours=len(v), cumul_mm=arrondir(v.sum(), 1),
                      jour_le_plus_pluvieux={"date": str(d0 + timedelta(days=k)),
                                             "pluie_mm": arrondir(v[k], 1)},
                      jours_sup_50mm=int((v >= SEUIL_MM).sum()))
    return sortie


def _evenements(data, d0, d1):
    ev = data.get("events")
    if ev is None:
        return None
    sel = ev[(ev["date"].dt.date >= d0) & (ev["date"].dt.date <= d1)]
    return sel.sort_values("max_precip", ascending=False)


def run(params, data, figures=None, session_id=""):
    d0, d1 = _periode(params)
    try:
        z = _zone(params)
        if "point" in z:
            return _hors_senegal(z, d0, d1)
        m = z["masque"]
        pluies, anoms, clims, jours = [], [], [], []
        d = d0
        while d <= d1:
            p, a = S.pluie_jour_senegal(d)
            pluies.append(p[m]); anoms.append(a[m]); clims.append(S.climatologie_jour(d)[m])
            jours.append(d)
            d += timedelta(days=1)
    except S.SourceAbsente as exc:
        raise ToolInputError("Donnee brute absente de ce serveur : %s" % exc)
    except S.DemandeInvalide as exc:
        raise ToolInputError(str(exc))

    P, A, C = np.stack(pluies), np.stack(anoms), np.stack(clims)   # (jours, pixels)
    moy = np.nanmean(P, axis=1)
    sortie = {"lieu": z["lieu"], "pixels_chirps": int(m.sum()), "methode_zone": z["methode"]}
    if z.get("autres_lieux_du_meme_nom"):
        sortie["autres_lieux_du_meme_nom"] = z["autres_lieux_du_meme_nom"]
    ev = _evenements(data, d0, d1)

    if d0 == d1:
        a = A[0]
        sortie.update({
            "date": str(d0),
            "pluie_moyenne_zone_mm": arrondir(moy[0], 1),
            "pluie_max_pixel_mm": arrondir(np.nanmax(P[0]), 1),
            "normale_du_jour_mm": arrondir(np.nanmean(C[0]), 1),
            "anomalie_moyenne_sigma": arrondir(np.nanmean(a), 2),
            "anomalie_max_sigma": arrondir(np.nanmax(a), 2),
            "pixels_sup_2sigma": int((a > S.SEUIL_SIGMA).sum()),
        })
        if ev is not None:
            sortie["au_catalogue_des_extremes"] = (
                {"oui": True, "rang": int(ev.iloc[0]["rank"]) if "rank" in ev else None,
                 "max_precip_catalogue_mm": arrondir(ev.iloc[0]["max_precip"], 1),
                 "note": "le catalogue juge l'ensemble du Senegal ; la zone peut ne pas etre "
                         "celle du maximum"} if len(ev) else {"oui": False})
        if params.get("map") is True and figures is not None:
            sortie.update(_carte(d0, figures, session_id))
    else:
        cumul, normal = float(np.nansum(moy)), float(np.nansum(np.nanmean(C, axis=1)))
        k = int(np.nanargmax(moy))
        sortie.update({
            "periode": [str(d0), str(d1)], "n_jours": len(jours),
            "cumul_zone_mm": arrondir(cumul, 1),
            "cumul_normal_mm": arrondir(normal, 1),
            "ecart_a_la_normale_pct": arrondir((cumul / normal - 1) * 100, 0) if normal > 0 else None,
            "jour_le_plus_pluvieux": {"date": str(jours[k]), "pluie_moyenne_zone_mm": arrondir(moy[k], 1)},
            "jours_avec_un_pixel_sup_50mm": int((np.nanmax(P, axis=1) >= SEUIL_MM).sum()),
            "jours_avec_un_pixel_sup_2sigma": int((np.nanmax(A, axis=1) > S.SEUIL_SIGMA).sum()),
        })
        if ev is not None:
            sortie["evenements_du_catalogue_au_senegal"] = {
                "n": int(len(ev)),
                "note": "jours d'evenement extreme sur l'ensemble du Senegal pendant la "
                        "periode, pas forcement dans la zone",
                "plus_intenses": [{"date": str(r["date"].date()), "max_precip_mm": arrondir(r["max_precip"], 1)}
                                  for _, r in ev.head(5).iterrows()]}
        if params.get("map") is True:
            sortie["carte"] = "carte disponible pour un jour seulement"
    sortie["normale"] = "climatologie CHIRPS 1981-2023 du meme jour de l'annee"
    sortie["source"] = S.SOURCE_CHIRPS
    return sortie


def _carte(d, figures, session_id):
    """Carte du jour sur le Senegal, meme rendu que show_map evenement."""
    from .cartes import _marqueur, _maximum, _spec_senegal, _date_fr
    pluie, _ = S.pluie_jour_senegal(d)
    maxi = _maximum(pluie)
    spec = _spec_senegal("Pluie du %s" % _date_fr(str(d)), "précipitation (mm/jour)",
                         pluie, "precipitation", marqueur=_marqueur(maxi, "mm"),
                         source=S.SOURCE_CHIRPS)
    spec["type"] = "get_rainfall"
    fig = figures.deposer(session_id, spec)
    return {"figure_id": fig.id, "carte_affichee": True}
