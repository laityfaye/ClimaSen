#!/usr/bin/env python3
"""Archive SST des evenements extremes pour l'animation de Jarvis.

Les 41 fichiers OISST (42 Go) ne sont pas sur le serveur. Ce script en
extrait, une fois, ce qu'il faut pour animer l'evolution de l'ocean pendant
les 5 mois qui precedent les evenements les plus intenses: c'est l'echelle
des teleconnexions trouvees par le script 04 (lags 3 a 5 mois).

Pour chaque evenement retenu (les N premiers du catalogue par phase, selon
la colonne rank):
  - 11 images, de J-150 a J0 tous les 15 jours; chaque image est la moyenne
    des 5 jours qui s'achevent a sa date (lisse le bruit journalier);
  - domaine 36 S - 36 N, tout le tour du globe, grille de 1 deg (moyenne de
    blocs 4 x 4 de la grille OISST a 0,25 deg);
  - anomalie en int8 (pas de 0,04 degC, -128 = terre ou donnee absente);
  - moyenne de chaque boite d'indice (grille pleine resolution), qui sert au
    resume chiffre donne au modele.

Sortie: jarvis/cartes/sst_evenements.npz (~ quelques Mo).

Usage:
    py -3 scripts/17_build_jarvis_sst_evenements.py [--par-phase 10]
"""
import argparse
import ctypes
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from jarvis.cartes import BOITES_RESUME  # noqa: E402

EVENEMENTS = RACINE / "data" / "processed" / "extreme_events_phases_senegal.csv"
SST = RACINE / "data" / "raw" / "SST"
SORTIE = RACINE / "jarvis" / "cartes" / "sst_evenements.npz"

DECALAGES = list(range(-150, 1, 15))     # 11 images
JOURS_MOYENNE = 5
LAT_MAX = 36.0
BLOC = 4                                 # 0,25 deg x 4 = 1 deg
ECHELLE = 25.0                           # int8: 1 unite = 0,04 degC
EPOQUE = pd.Timestamp("1800-01-01")


def chemin_court(p: Path) -> str:
    """netCDF4 ne sait pas ouvrir un chemin accentue sous Windows."""
    if os.name != "nt":
        return str(p)
    tampon = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(p), tampon, 1024)
    return tampon.value or str(p)


class Lecteur:
    """Ouvre les fichiers annuels a la demande et garde les dates decodees."""

    def __init__(self):
        import xarray as xr
        self.xr = xr
        self.ouverts = {}

    def fichier(self, annee):
        if annee not in self.ouverts:
            chemin = SST / ("sst_day_anom_%d.nc" % annee)
            if not chemin.is_file():
                self.ouverts[annee] = None
            else:
                ds = self.xr.open_dataset(chemin_court(chemin), decode_times=False)
                # 1983-1989 couvrent tout le globe (720 latitudes), les annees
                # suivantes 60S-60N (480): on ramene tout a 60S-60N.
                anom = ds["anom"].sel(lat=slice(-60, 60))
                jours = (EPOQUE + pd.to_timedelta(ds["time"].values, unit="D")).normalize()
                self.ouverts[annee] = (anom, {d: i for i, d in enumerate(jours)})
        return self.ouverts[annee]

    def jour(self, date):
        f = self.fichier(date.year)
        if f is None:
            return None
        anom, index = f
        i = index.get(date.normalize())
        if i is None:
            return None
        return anom.isel(time=i).values.astype("float32")

    def axes(self):
        for f in self.ouverts.values():
            if f is not None:
                return f[0]["lat"].values, f[0]["lon"].values
        raise RuntimeError("Aucun fichier SST ouvert.")


def moyenne_boites(grille, lats, lons):
    sortie = []
    for boites in BOITES_RESUME.values():
        vals = []
        for lon0, lon1, lat0, lat1 in boites:
            mi = (lats >= lat0) & (lats <= lat1)
            mj = (lons >= lon0) & (lons <= lon1)
            vals.append(grille[np.ix_(mi, mj)].ravel())
        tout = np.concatenate(vals)
        tout = tout[np.isfinite(tout)]
        sortie.append(float(tout.mean()) if tout.size else np.nan)
    return sortie


def reduire(grille, lats):
    """Domaine 36S-36N puis blocs 4 x 4 (moyenne des pixels d'ocean)."""
    garde = (lats > -LAT_MAX) & (lats < LAT_MAX)
    g = grille[garde]
    n, m = g.shape[0] // BLOC * BLOC, g.shape[1] // BLOC * BLOC
    g = g[:n, :m].reshape(n // BLOC, BLOC, m // BLOC, BLOC)
    with np.errstate(all="ignore"):
        moy = np.nanmean(g, axis=(1, 3))
    return moy


def main():
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--par-phase", type=int, default=10,
                         help="evenements retenus par phase (defaut 10)")
    args = parseur.parse_args()

    cat = pd.read_csv(EVENEMENTS, parse_dates=["date"])
    debut_sst = pd.Timestamp("1983-01-01") - pd.Timedelta(days=DECALAGES[0] - JOURS_MOYENNE)
    cat = cat[cat["date"] >= debut_sst]
    retenus = (cat.sort_values("rank").groupby("phase", group_keys=False)
               .head(args.par_phase).sort_values("date"))
    print("Evenements retenus: %d" % len(retenus))

    lecteur = Lecteur()
    images, boites, dates, gardes = [], [], [], []
    for _, ev in retenus.iterrows():
        pile, pile_boites, complet = [], [], True
        for dec in DECALAGES:
            fin = ev["date"] + pd.Timedelta(days=dec)
            jours = [lecteur.jour(fin - pd.Timedelta(days=k)) for k in range(JOURS_MOYENNE)]
            jours = [j for j in jours if j is not None]
            if not jours:
                complet = False
                break
            with np.errstate(all="ignore"):
                moy = np.nanmean(np.stack(jours), axis=0)
            lats, lons = lecteur.axes()
            pile_boites.append(moyenne_boites(moy, lats, lons))
            pile.append(reduire(moy, lats))
        if not complet:
            print("  ignore (SST incomplete): %s" % ev["date"].date())
            continue
        q = np.clip(np.round(np.stack(pile) * ECHELLE), -127, 127)
        q[~np.isfinite(np.stack(pile))] = -128
        images.append(q.astype("int8"))
        boites.append(pile_boites)
        dates.append(ev["date"].strftime("%Y-%m-%d"))
        gardes.append(ev)
        print("  %s  %-15s rang %d" % (dates[-1], ev["phase"], ev["rank"]))

    lats, lons = lecteur.axes()
    garde = (lats > -LAT_MAX) & (lats < LAT_MAX)
    la = lats[garde]
    la = la[: la.size // BLOC * BLOC].reshape(-1, BLOC).mean(axis=1)
    lo = lons[: lons.size // BLOC * BLOC].reshape(-1, BLOC).mean(axis=1)
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        SORTIE,
        images=np.stack(images), lats=la.astype("float32"), lons=lo.astype("float32"),
        dates=np.array(dates), phases=np.array([g["phase"] for g in gardes]),
        rangs=np.array([int(g["rank"]) for g in gardes]),
        decalages=np.array(DECALAGES), echelle=np.array(ECHELLE),
        boites=np.array(boites, dtype="float32"),
        noms_boites=np.array(list(BOITES_RESUME)),
    )
    print("Ecrit: %s (%.1f Mo)" % (SORTIE, SORTIE.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
