"""Cube SST compact: ce qu'il faut garder des 42 Go d'OISST pour la veille.

Grille 1 deg, 60S-60N (120 x 360), moyenne des blocs 4 x 4 de la grille
OISST a 0,25 deg (pixels d'ocean seulement). Deux contenus:
  - les moyennes MENSUELLES de l'anomalie (etat novembre-avril);
  - le champ du JOUR de chaque evenement extreme (reproduction des
    configurations du memoire).
Stockage en int16, pas de 0,01 degC, -32768 = terre ou donnee absente.

L'extraction est incrementale: ajouter 2024 ne relit que le fichier 2024.
Une annee en cours (fichier NOAA partiel) est prise telle quelle: ses mois
absents sont simplement absents du cube.
"""
import ctypes
import os
import warnings

import numpy as np
import pandas as pd

from . import CUBE_SST, EVENEMENTS, MOIS_ETAT, RACINE

DOSSIER_OISST = RACINE / "data" / "raw" / "SST"
EPOQUE = pd.Timestamp("1800-01-01")
BLOC = 4
ECHELLE = 100.0
VIDE = -32768


class CubeIndisponible(Exception):
    """Cube absent ou mois manquants pour l'etat demande."""


def _chemin_court(p):
    """netCDF4 n'ouvre pas les chemins accentues sous Windows."""
    if os.name != "nt":
        return str(p)
    tampon = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(p), tampon, 1024)
    return tampon.value or str(p)


def reduire(pile):
    """(t, 480, 1440) a 0,25 deg -> (t, 120, 360) a 1 deg."""
    t, n, m = pile.shape
    blocs = pile.reshape(t, n // BLOC, BLOC, m // BLOC, BLOC)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.nanmean(blocs, axis=(2, 4)).astype("float32")


def _coder(x):
    q = np.round(np.asarray(x, dtype="float64") * ECHELLE)
    q = np.clip(q, -32767, 32767)
    q[~np.isfinite(np.asarray(x, dtype="float64"))] = VIDE
    return q.astype("int16")


def _decoder(q):
    x = q.astype("float32") / ECHELLE
    x[q == VIDE] = np.nan
    return x


def extraire_annee(annee, dates_evenements, journal=print):
    """Lit un fichier OISST annuel: (mois, champs mensuels, dates evt, champs evt, lats, lons)."""
    import xarray as xr

    chemin = DOSSIER_OISST / ("sst_day_anom_%d.nc" % annee)
    if not chemin.is_file():
        raise CubeIndisponible("Fichier OISST absent: %s" % chemin.name)
    ds = xr.open_dataset(_chemin_court(chemin), decode_times=False)
    try:
        # 1983-1989 couvrent le globe (720 latitudes), la suite 60S-60N: on
        # ramene tout a 60S-60N, comme le script 11.
        anom = ds["anom"].sel(lat=slice(-60, 60))
        if anom.sizes["lat"] != 480 or anom.sizes["lon"] != 1440:
            raise CubeIndisponible("Grille inattendue en %d: %s" % (annee, dict(anom.sizes)))
        jours = pd.DatetimeIndex((EPOQUE + pd.to_timedelta(ds["time"].values, unit="D")).normalize())
        lats = anom["lat"].values.reshape(-1, BLOC).mean(1)
        lons = anom["lon"].values.reshape(-1, BLOC).mean(1)
        mois, mensuel, evt_dates, evt = [], [], [], []
        for m in range(1, 13):
            idx = np.where(jours.month == m)[0]
            if idx.size == 0:
                continue
            brut = anom.isel(time=slice(idx[0], idx[-1] + 1)).values
            if brut.ndim == 4:
                brut = brut[:, 0]
            red = reduire(brut.astype("float32"))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mensuel.append(np.nanmean(red, axis=0))
            mois.append((annee, m))
            for k, d in enumerate(jours[idx[0]:idx[-1] + 1]):
                if d in dates_evenements:
                    evt.append(red[k])
                    evt_dates.append(d.strftime("%Y-%m-%d"))
        journal("  %d: %d mois, %d evenements" % (annee, len(mois), len(evt)))
        return mois, mensuel, evt_dates, evt, lats, lons
    finally:
        ds.close()


class Cube:
    """Cube charge en memoire (decode en float32 a la demande)."""

    def __init__(self, mois, mensuel, evt_dates, evt, lats, lons):
        self.mois = [tuple(int(v) for v in m) for m in mois]
        self._mensuel = mensuel
        self.evt_dates = pd.to_datetime(np.asarray(evt_dates))
        self._evt = evt
        self.lats = np.asarray(lats, dtype="float32")
        self.lons = np.asarray(lons, dtype="float32")
        self._index = {m: i for i, m in enumerate(self.mois)}

    @classmethod
    def charger(cls, chemin=CUBE_SST):
        if not chemin.is_file():
            raise CubeIndisponible(
                "Cube SST absent (%s). Le construire: py -3 scripts/19_build_sst_cube.py"
                % chemin.name)
        z = np.load(chemin)
        return cls(z["mois"], z["mensuel"], z["evt_dates"], z["evt"], z["lats"], z["lons"])

    def sauver(self, chemin=CUBE_SST):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(chemin, mois=np.array(self.mois, dtype="int16"),
                            mensuel=self._mensuel, evt_dates=np.array(
                                [d.strftime("%Y-%m-%d") for d in self.evt_dates]),
                            evt=self._evt, lats=self.lats, lons=self.lons)

    # -- acces --------------------------------------------------------------
    def a_le_mois(self, annee, mois):
        return (annee, mois) in self._index

    def mensuel(self, annee, mois):
        i = self._index.get((annee, mois))
        if i is None:
            raise CubeIndisponible("Mois absent du cube: %02d/%d" % (mois, annee))
        return _decoder(self._mensuel[i])

    def evenements(self):
        return _decoder(self._evt)

    def pixels_toujours_valides(self):
        """Pixels (aplatis) renseignes dans TOUS les mois du cube."""
        return (self._mensuel.reshape(len(self.mois), -1) != VIDE).all(0)

    def dernier_mois(self):
        return max(self.mois) if self.mois else None

    def mois_etat(self, annee):
        """Les 6 mois (nov n-1 .. avr n) de l'etat de l'annee `annee`."""
        return [(annee + da, m) for da, m in MOIS_ETAT]

    def mois_etat_manquants(self, annee):
        return [(a, m) for a, m in self.mois_etat(annee) if not self.a_le_mois(a, m)]

    def etats_mensuels(self, annee):
        return [self.mensuel(a, m) for a, m in self.mois_etat(annee)]

    def etat(self, annee):
        """Anomalie moyenne novembre (n-1) - avril (n)."""
        manquants = self.mois_etat_manquants(annee)
        if manquants:
            raise CubeIndisponible(
                "Etat novembre-avril incomplet pour %d: manque %s" % (
                    annee, ", ".join("%02d/%d" % (m, a) for a, m in manquants)))
        return np.mean(self.etats_mensuels(annee), axis=0)

    def annees_etat_complet(self):
        annees = sorted({a for a, _ in self.mois})
        return [a for a in annees if not self.mois_etat_manquants(a)]

    # -- construction -------------------------------------------------------
    def ajouter(self, mois, mensuel, evt_dates, evt, lats, lons):
        """Fusionne une annee extraite (remplace les mois deja presents)."""
        if len(self.mois) and (not np.allclose(lats, self.lats) or not np.allclose(lons, self.lons)):
            raise CubeIndisponible("Grille differente de celle du cube.")
        neufs = set(mois)
        garde = [i for i, m in enumerate(self.mois) if m not in neufs]
        tous_mois = [self.mois[i] for i in garde] + list(mois)
        blocs = ([self._mensuel[garde]] if garde else []) + \
                ([_coder(np.stack(mensuel))] if mensuel else [])
        ordre = np.argsort([a * 100 + m for a, m in tous_mois])
        self.mois = [tous_mois[i] for i in ordre]
        self._mensuel = np.concatenate(blocs)[ordre] if blocs else np.zeros((0, len(lats), len(lons)), "int16")
        # Evenements: meme logique, cle = date
        neuves = set(evt_dates)
        garde_e = [i for i, d in enumerate(self.evt_dates.strftime("%Y-%m-%d")) if d not in neuves]
        dates = [self.evt_dates[i].strftime("%Y-%m-%d") for i in garde_e] + list(evt_dates)
        blocs_e = ([self._evt[garde_e]] if garde_e else []) + ([_coder(np.stack(evt))] if evt else [])
        ordre_e = np.argsort(dates)
        self.evt_dates = pd.to_datetime(np.array(dates)[ordre_e]) if dates else pd.DatetimeIndex([])
        self._evt = np.concatenate(blocs_e)[ordre_e] if blocs_e else np.zeros((0, len(lats), len(lons)), "int16")
        self.lats, self.lons = np.asarray(lats, "float32"), np.asarray(lons, "float32")
        self._index = {m: i for i, m in enumerate(self.mois)}

    @classmethod
    def vide(cls):
        return cls([], np.zeros((0, 120, 360), "int16"), [], np.zeros((0, 120, 360), "int16"),
                   np.zeros(120, "float32"), np.zeros(360, "float32"))


def dates_evenements():
    cat = pd.read_csv(EVENEMENTS, usecols=["date"], parse_dates=["date"])
    return set(cat["date"].dt.normalize())


def construire(annees, chemin=CUBE_SST, journal=print):
    """Ajoute (ou remplace) des annees dans le cube, puis le sauve."""
    cube = Cube.charger(chemin) if chemin.is_file() else Cube.vide()
    dates = dates_evenements()
    annees = list(annees)
    for i, annee in enumerate(annees, 1):
        cube.ajouter(*extraire_annee(annee, dates, journal))
        # Sauvegarde reguliere: une coupure ne perd que les dernieres annees.
        if i % 5 == 0 or i == len(annees):
            cube.sauver(chemin)
    return cube
