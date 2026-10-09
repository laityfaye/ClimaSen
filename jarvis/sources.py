"""Lecture des donnees SOURCES du dossier data/ par les outils d'Iris.

Iris ne lit jamais un fichier a sa maniere : tout passe par ce module, en
lecture seule, sur une liste fermee de fichiers. Chaque fonction lit le
STRICT necessaire (un jour d'un fichier annuel OISST de 1,5 Go, un jour du
cube CHIRPS), jamais un fichier entier en memoire.

Sources et presence attendue :
  - CHIRPS, grille du Senegal (18 x 25 pixels de 0,25 deg, 1981-2023) :
    data/processed/standardized_anomalies_senegal.npz + climatology_senegal.npz,
    VERSIONNES, donc toujours la. pluie = anomalie x ecart-type + climatologie
    redonne le CHIRPS brut a l'identique (verifie le 09/10/2026, ecart 0,0 mm,
    saison seche comprise).
  - CHIRPS brut Afrique de l'Ouest (0-30 N, 20 W-20 E) :
    data/raw/chirps_WA_1981_2023_dayly.mat, NON versionne (290 Mo) : seulement
    utile hors de la grille du Senegal.
  - OISST v2 journalier : data/raw/SST/sst_day_anom_AAAA.nc, NON versionnes
    (42 Go) ; a defaut, le cube mensuel a 1 deg (data/processed/sst_cube_1deg.npz,
    NON versionne, reconstruit par le script 19).
  - ANSD : repertoire des localites (RGPH 1988, 2002, 2013, 2023) et localites
    RGPH-5 placees (script 33), versionnes.
  - Inondations documentees 2005-2020 (data/raw/inondations), versionnees.

Une source absente leve SourceAbsente avec un message qu'Iris peut dire tel
quel : "donnee brute absente de ce serveur".
"""
import os
import threading
from datetime import date as Date
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
DATA = RACINE / "data"

CHIRPS_MAT = DATA / "raw" / "chirps_WA_1981_2023_dayly.mat"
OISST_DOSSIER = DATA / "raw" / "SST"
C3S_DOSSIER = DATA / "raw" / "c3s"
CUBE_SST = DATA / "processed" / "sst_cube_1deg.npz"
ANOMALIES = DATA / "processed" / "standardized_anomalies_senegal.npz"
CLIMATOLOGIE = DATA / "processed" / "climatology_senegal.npz"
REPERTOIRE = DATA / "raw" / "ansd" / "rgph_repertoire_localites_1988-2023.csv"
LOCALITES = DATA / "processed" / "localites_rgph5_placees.csv"
INONDATIONS = DATA / "raw" / "inondations" / "zones_touchees_2005_2009_2012_2020.csv"
CONTOURS = {"departements": DATA / "processed" / "contours_admin2_simplifies.geojson",
            "arrondissements": DATA / "processed" / "contours_admin3_simplifies.geojson"}

DEBUT_CHIRPS = Date(1981, 1, 1)
FIN_CHIRPS = Date(2023, 12, 31)
DEBUT_OISST = Date(1983, 1, 1)
FIN_OISST = Date(2023, 12, 31)
EPOQUE_OISST = Date(1800, 1, 1)
SEUIL_SIGMA = 2.0

SOURCE_CHIRPS = "CHIRPS v2.0 (Climate Hazards Center), pluie journaliere 0,25 deg"
SOURCE_OISST = "NOAA OISST v2, anomalies journalieres de SST 0,25 deg"
SOURCE_CUBE = "NOAA OISST v2, moyennes mensuelles ramenees a 1 deg (cube du script 19)"
SOURCE_REPERTOIRE = "ANSD, repertoire des localites (RGPH 1988, 2002, 2013, 2023)"
SOURCE_LOCALITES = "ANSD RGPH-5 2023 et coordonnees des localites (script 33)"


class SourceAbsente(Exception):
    """Fichier source absent de ce serveur (message destine a l'utilisateur)."""


class DemandeInvalide(Exception):
    """Parametre hors domaine (date, zone, boite)."""


def _chemin_court(p: Path) -> str:
    """netCDF4 et h5py n'ouvrent pas les chemins accentues sous Windows."""
    if os.name != "nt":
        return str(p)
    import ctypes
    tampon = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(p), tampon, 1024)
    return tampon.value or str(p)


def _fichiers_oisst():
    return sorted(OISST_DOSSIER.glob("sst_day_anom_*.nc")) if OISST_DOSSIER.is_dir() else []


def disponibilite() -> dict:
    """Ce que ce serveur possede, source par source (pour Iris et le script 39)."""
    oisst = _fichiers_oisst()
    annees = sorted(int(p.stem[-4:]) for p in oisst)
    return {
        "chirps_senegal": ANOMALIES.is_file() and CLIMATOLOGIE.is_file(),
        "chirps_afrique_ouest": CHIRPS_MAT.is_file(),
        "oisst_journalier": {"annees": len(annees),
                             "premiere": annees[0] if annees else None,
                             "derniere": annees[-1] if annees else None},
        "cube_sst_mensuel": CUBE_SST.is_file(),
        "c3s": len(list(C3S_DOSSIER.glob("*.nc"))) if C3S_DOSSIER.is_dir() else 0,
        "repertoire_localites": REPERTOIRE.is_file(),
        "localites_placees": LOCALITES.is_file(),
        "inondations_documentees": INONDATIONS.is_file(),
    }


def _date(texte, mini, maxi, nom="date"):
    try:
        d = Date.fromisoformat(str(texte))
    except ValueError:
        raise DemandeInvalide("%s invalide : %r (format AAAA-MM-JJ)." % (nom, texte))
    if not mini <= d <= maxi:
        raise DemandeInvalide("%s hors periode : %s (donnees du %s au %s)."
                              % (nom, d, mini, maxi))
    return d


# =============================================================================
# CHIRPS
# =============================================================================
@lru_cache(maxsize=1)
def grille_senegal():
    """Anomalies (jours, 18, 25), climatologie et ecart-type (366, 18, 25)."""
    if not (ANOMALIES.is_file() and CLIMATOLOGIE.is_file()):
        raise SourceAbsente("Grilles CHIRPS du Senegal absentes de ce serveur.")
    z = np.load(ANOMALIES, allow_pickle=True)
    c = np.load(CLIMATOLOGIE, allow_pickle=True)
    clim = c["climatology"].astype("float32")
    return {
        "anomalies": z["anomalies"].astype("float32"),
        "debut": Date.fromisoformat(str(z["dates"][0])),
        "clim": clim, "ecart": c["std_dev"].astype("float32"),
        "lats": c["lats"].astype("float64"), "lons": c["lons"].astype("float64"),
        # CHIRPS ne couvre que les terres : en mer la climatologie vaut 0.
        "terre": clim.sum(axis=0) > 0,
    }


def _indice_jour(g, d):
    return (d - g["debut"]).days


def pluie_jour_senegal(d):
    """(pluie mm, anomalie sigma) sur la grille du Senegal pour le jour d."""
    g = grille_senegal()
    k = _indice_jour(g, d)
    if not 0 <= k < g["anomalies"].shape[0]:
        raise DemandeInvalide("Jour hors de la grille CHIRPS : %s." % d)
    an = g["anomalies"][k]
    doy = d.timetuple().tm_yday - 1
    pluie = np.maximum(an * g["ecart"][doy] + g["clim"][doy], 0.0)
    pluie = np.where(g["terre"], pluie, np.nan)
    an = np.where(g["terre"], an, np.nan)
    return pluie, an


def climatologie_jour(d):
    g = grille_senegal()
    return np.where(g["terre"], g["clim"][d.timetuple().tm_yday - 1], np.nan)


_verrou_mat = threading.Lock()


@lru_cache(maxsize=1)
def _mat():
    if not CHIRPS_MAT.is_file():
        raise SourceAbsente("CHIRPS brut d'Afrique de l'Ouest absent de ce serveur "
                            "(data/raw/chirps_WA_1981_2023_dayly.mat) : seule la grille du "
                            "Senegal est disponible.")
    import h5py
    f = h5py.File(_chemin_court(CHIRPS_MAT), "r")
    return f, f["latitude"][0].astype("float64"), f["longitude"][0].astype("float64")


def pluie_point_afrique_ouest(d, lat, lon):
    """Pluie (mm) du pixel CHIRPS brut le plus proche, hors grille du Senegal."""
    f, lats, lons = _mat()
    if not (lats[0] - 0.125 <= lat <= lats[-1] + 0.125 and lons[0] - 0.125 <= lon <= lons[-1] + 0.125):
        raise DemandeInvalide("Point hors de la couverture CHIRPS disponible (0-30 N, 20 W-20 E).")
    i, j = int(np.argmin(abs(lats - lat))), int(np.argmin(abs(lons - lon)))
    k = (d - DEBUT_CHIRPS).days
    with _verrou_mat:   # h5py n'est pas sur entre threads
        v = float(f["precip"][k, i, j])
    return v, (float(lats[i]), float(lons[j]))


def dans_grille_senegal(lat, lon):
    g = grille_senegal()
    return (g["lats"][0] - 0.125 <= lat <= g["lats"][-1] + 0.125
            and g["lons"][0] - 0.125 <= lon <= g["lons"][-1] + 0.125)


# =============================================================================
# Zones -> pixels de la grille du Senegal
# =============================================================================
@lru_cache(maxsize=2)
def _contours(niveau):
    import json
    p = CONTOURS[niveau]
    if not p.is_file():
        raise SourceAbsente("Contours %s absents de ce serveur." % niveau)
    return json.loads(p.read_text(encoding="utf-8"))["features"]


def _anneaux(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    return [poly[0] for poly in geom["coordinates"]]


def _pixels_dans(anneaux):
    """Pixels terrestres dont le centre est dans le contour ; a defaut, le
    pixel terrestre le plus proche du centre (meme regle que le script 26)."""
    from matplotlib.path import Path as Chemin
    g = grille_senegal()
    lo, la = np.meshgrid(g["lons"], g["lats"])
    points = np.column_stack([lo.ravel(), la.ravel()])
    dedans = np.zeros(points.shape[0], bool)
    for a in anneaux:
        dedans |= Chemin(np.asarray(a)).contains_points(points)
    masque = dedans.reshape(lo.shape) & g["terre"]
    if masque.any():
        return masque, "pixels dont le centre est dans le contour"
    tous = np.concatenate([np.asarray(a) for a in anneaux])
    cx, cy = tous[:, 0].mean(), tous[:, 1].mean()
    d2 = np.where(g["terre"], (lo - cx) ** 2 + (la - cy) ** 2, np.inf)
    i, j = np.unravel_index(int(np.argmin(d2)), d2.shape)
    masque = np.zeros_like(g["terre"])
    masque[i, j] = True
    return masque, "zone plus petite qu'un pixel : pixel terrestre le plus proche"


def _par_pcode(niveau, pcodes):
    feats = [f for f in _contours(niveau) if f["properties"].get("pcode") in pcodes]
    if not feats:
        raise DemandeInvalide("Contour introuvable pour %s." % ", ".join(sorted(pcodes)))
    anneaux = [a for f in feats for a in _anneaux(f["geometry"])]
    return _pixels_dans(anneaux)


def pixels_du_lieu(lieu):
    """Masque (18, 25) des pixels d'un Lieu du gazetteer des rapports."""
    if lieu.niveau == "pays":
        pcodes = {f["properties"]["pcode"] for f in _contours("departements")}
        return _par_pcode("departements", pcodes)
    if lieu.niveau == "region":
        pcodes = {f["properties"]["pcode"] for f in _contours("departements")
                  if str(f["properties"]["pcode"]).startswith(lieu.code)}
        return _par_pcode("departements", pcodes)
    if lieu.niveau == "departement":
        return _par_pcode("departements", {lieu.code})
    if lieu.niveau == "arrondissement":
        return _par_pcode("arrondissements", {lieu.code})
    # Commune : pixels ou vivent ses habitants (localites RGPH-5 placees).
    loc = localites_placees()
    sel = loc[(loc["COMMUNE"].map(_cle) == _cle(lieu.nom))
              & (loc["Departement"].map(_cle) == _cle(lieu.departement))]
    if sel.empty:
        return _par_pcode("arrondissements", {lieu.pcode_arrondissement})
    g = grille_senegal()
    masque = np.zeros_like(g["terre"])
    masque[sel["pix_i"].astype(int), sel["pix_j"].astype(int)] = True
    return masque, "pixels des localites de la commune (%d localites)" % len(sel)


def pixel_du_point(lat, lon):
    g = grille_senegal()
    lo, la = np.meshgrid(g["lons"], g["lats"])
    d2 = np.where(g["terre"], (lo - lon) ** 2 + (la - lat) ** 2, np.inf)
    i, j = np.unravel_index(int(np.argmin(d2)), d2.shape)
    masque = np.zeros_like(g["terre"])
    masque[i, j] = True
    return masque, "pixel terrestre le plus proche du point (%.3f, %.3f)" % (
        g["lats"][i], g["lons"][j])


# =============================================================================
# OISST
# =============================================================================
_verrou_oisst = threading.Lock()


@lru_cache(maxsize=3)
def _oisst_annee(annee):
    chemin = OISST_DOSSIER / ("sst_day_anom_%d.nc" % annee)
    if not chemin.is_file():
        raise SourceAbsente("SST journaliere %d absente de ce serveur (data/raw/SST/%s)."
                            % (annee, chemin.name))
    import netCDF4
    ds = netCDF4.Dataset(_chemin_court(chemin))
    lats = np.asarray(ds["lat"][:], dtype="float64")
    garde = np.where((lats >= -60) & (lats <= 60))[0]   # 1983-1989 : globe entier
    jours = np.asarray(ds["time"][:], dtype="int64")
    index = {(EPOQUE_OISST + timedelta(days=int(t))): k for k, t in enumerate(jours)}
    return ds, garde, lats[garde], np.asarray(ds["lon"][:], dtype="float64"), index


def sst_jour(d):
    """(anomalie degC (lat, lon) 60S-60N a 0,25 deg, lats, lons) du jour d."""
    if not DEBUT_OISST <= d <= FIN_OISST:
        raise DemandeInvalide("SST disponible du %s au %s." % (DEBUT_OISST, FIN_OISST))
    ds, garde, lats, lons, index = _oisst_annee(d.year)
    k = index.get(d)
    if k is None:
        raise SourceAbsente("Jour %s absent du fichier SST %d." % (d, d.year))
    with _verrou_oisst:
        brut = ds["anom"][k, int(garde[0]):int(garde[-1]) + 1, :]
    z = np.ma.filled(brut.astype("float32"), np.nan)
    return z, lats, lons


def reduire_1deg(z, lats, lons):
    """Blocs 4 x 4 (0,25 -> 1 deg), moyenne des pixels d'ocean."""
    n, m = z.shape[0] // 4 * 4, z.shape[1] // 4 * 4
    b = z[:n, :m].reshape(n // 4, 4, m // 4, 4)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            moy = np.nanmean(b, axis=(1, 3))
    return (moy, lats[:n].reshape(-1, 4).mean(1), lons[:m].reshape(-1, 4).mean(1))


@lru_cache(maxsize=1)
def cube():
    if not CUBE_SST.is_file():
        raise SourceAbsente("Cube SST mensuel absent de ce serveur (a reconstruire par "
                            "scripts/19_build_sst_cube.py apres telechargement d'OISST).")
    from veille.cube import Cube
    return Cube.charger(CUBE_SST)


def sst_mois(annee, mois):
    """(anomalie degC a 1 deg, lats, lons, source) du mois : cube, sinon OISST."""
    try:
        c = cube()
        if c.a_le_mois(annee, mois):
            return c.mensuel(annee, mois), c.lats, c.lons, SOURCE_CUBE
    except SourceAbsente:
        pass
    d = Date(annee, mois, 1)
    jours = []
    while d.month == mois:
        z, lats, lons = sst_jour(d)
        jours.append(reduire_1deg(z, lats, lons)[0])
        d += timedelta(days=1)
    _, la, lo = reduire_1deg(z, lats, lons)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(np.stack(jours), axis=0), la, lo, SOURCE_OISST


DECALAGES_ANIMATION = list(range(-150, 1, 15))   # memes images que le script 17
JOURS_MOYENNE = 5
LAT_ANIMATION = 36.0


def animation_evenement(d):
    """Images (11, 72, 360) degC et moyennes par boite (11, 11) de J-150 a J0,
    calculees comme l'archive du script 17 (moyenne de 5 jours, 36S-36N, 1 deg)."""
    import warnings
    from .cartes import BOITES_RESUME
    debut = d + timedelta(days=DECALAGES_ANIMATION[0] - JOURS_MOYENNE + 1)
    if debut < DEBUT_OISST:
        raise DemandeInvalide("Il faut 150 jours de SST avant l'evenement : premier jour "
                              "animable %s." % (DEBUT_OISST + timedelta(days=154)))
    images, boites = [], []
    for dec in DECALAGES_ANIMATION:
        fin = d + timedelta(days=dec)
        jours = [sst_jour(fin - timedelta(days=k)) for k in range(JOURS_MOYENNE)]
        z0, lats, lons = jours[0]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            moy = np.nanmean(np.stack([j[0] for j in jours]), axis=0)
        boites.append([moyenne_boite_simple(moy, lats, lons, b)
                       for b in BOITES_RESUME.values()])
        garde = (lats > -LAT_ANIMATION) & (lats < LAT_ANIMATION)
        images.append(reduire_1deg(moy[garde], lats[garde], lons)[0])
    return np.stack(images).astype("float32"), np.asarray(boites, dtype="float32")


def moyenne_boite_simple(z, lats, lons, boites):
    """Moyenne non ponderee : celle du script 17 (archive des animations)."""
    vals = []
    for lon0, lon1, lat0, lat1 in boites:
        mi = (lats >= lat0) & (lats <= lat1)
        mj = (lons >= lon0) & (lons <= lon1)
        vals.append(z[np.ix_(mi, mj)].ravel())
    v = np.concatenate(vals)
    v = v[np.isfinite(v)]
    return float(v.mean()) if v.size else np.nan


def moyenne_boite(z, lats, lons, boites):
    """Moyenne ponderee par cos(lat) sur une ou plusieurs boites (lon0, lon1, lat0, lat1)."""
    vals, poids = [], []
    for lon0, lon1, lat0, lat1 in boites:
        mi = (lats >= lat0) & (lats <= lat1)
        mj = (lons >= lon0) & (lons <= lon1)
        bloc = z[np.ix_(mi, mj)]
        w = np.repeat(np.cos(np.radians(lats[mi]))[:, None], bloc.shape[1], axis=1)
        ok = np.isfinite(bloc)
        vals.append(bloc[ok])
        poids.append(w[ok])
    v, w = np.concatenate(vals), np.concatenate(poids)
    if v.size == 0:
        return None, 0
    return float(np.sum(v * w) / np.sum(w)), int(v.size)


# =============================================================================
# ANSD : localites et inondations documentees
# =============================================================================
def _cle(texte):
    from .tools.common import normalise
    return normalise(str(texte))


@lru_cache(maxsize=1)
def repertoire():
    if not REPERTOIRE.is_file():
        raise SourceAbsente("Repertoire des localites de l'ANSD absent de ce serveur.")
    t = pd.read_csv(REPERTOIRE, encoding="utf-8", low_memory=False)
    t = t.rename(columns={c: "Annee" for c in t.columns if c.startswith("Ann")})
    t["cle"] = t["QUARTIER_VILLAGE_HAMEAU"].map(_cle)
    return t


@lru_cache(maxsize=1)
def localites_placees():
    if not LOCALITES.is_file():
        raise SourceAbsente("Localites RGPH-5 placees absentes de ce serveur (script 33).")
    t = pd.read_csv(LOCALITES, encoding="utf-8")
    t["cle"] = t["LOCALITE"].map(_cle)
    return t


@lru_cache(maxsize=1)
def inondations():
    if not INONDATIONS.is_file():
        raise SourceAbsente("Inventaire des inondations documentees absent de ce serveur.")
    t = pd.read_csv(INONDATIONS, encoding="utf-8")
    t["cle"] = t["departement"].map(_cle)
    return t
