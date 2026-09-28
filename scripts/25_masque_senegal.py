#!/usr/bin/env python3
"""Mesure de l'effet d'un masque aux frontieres du Senegal sur la detection.

Suivi de revue 28/09/2026, point S2 : le script 01 detecte les evenements sur
la BOITE 12,3-16,7 N / 17,55-11,35 W (18 x 25 pixels CHIRPS a 0,25 deg), qui
contient toute la Gambie et une partie de la Mauritanie, du Mali, de la Guinee
et de la Guinee-Bissau. Ce script refait la detection avec les memes criteres
(src/analysis/detection.py) :
    - anomalie standardisee > +2 sigma,
    - au moins 40 pixels au-dessus du seuil,
    - precipitation max >= 5 mm dans la zone extreme,
    - saison des pluies (mai-octobre),
d'abord sur la boite (controle : doit retrouver le catalogue de production),
puis sur les seuls pixels dont le centre est au Senegal, avec deux variantes du
seuil de pixels :
    - "masque_40"   : 40 pixels, comme aujourd'hui (plus exigeant, le pays a
                      moins de pixels que la boite),
    - "masque_prop" : seuil ramene a la meme FRACTION du domaine (40/450).

Le catalogue de production (data/processed/extreme_events_phases_senegal.csv)
N'EST PAS modifie : le choix de basculer releve du memoire.

Sorties (outputs/masque_senegal/) :
    comparaison_evenements.csv   un jour par ligne detecte dans au moins une variante
    series_annuelles.csv         max_precip annuel par phase, boite vs masque
    resume.json                  chiffres cles
    masque_pixels.png            pixels de la boite, au Senegal ou non

Usage : py -3 scripts/25_masque_senegal.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath

RACINE = Path(__file__).resolve().parent.parent
FICHIER_CHIRPS = RACINE / "data/raw/chirps_WA_1981_2023_dayly.mat"
FICHIER_ANOM = RACINE / "data/processed/standardized_anomalies_senegal.npz"
FICHIER_CLIM = RACINE / "data/processed/climatology_senegal.npz"
FICHIER_CATALOGUE = RACINE / "data/processed/extreme_events_phases_senegal.csv"
FICHIER_FRONTIERE = RACINE / "data/geographic/senegal_boundaries.geojson"
SORTIE = RACINE / "outputs/masque_senegal"

BOITE = {"lat_min": 12.3, "lat_max": 16.7, "lon_min": -17.55, "lon_max": -11.35}
SEUIL_ANOMALIE = 2.0
MIN_PIXELS = 40
MIN_PRECIP = 5.0
PHASES = {5: "Phase_1_debut", 6: "Phase_1_debut", 7: "Phase_2_pleine",
          8: "Phase_2_pleine", 9: "Phase_3_fin", 10: "Phase_3_fin"}


def charger_precip():
    """Precipitation sur la boite, comme OptimizedChirpsLoader du script 01."""
    with h5py.File(FICHIER_CHIRPS, "r") as f:
        lat = np.array(f["latitude"]).flatten()
        lon = np.array(f["longitude"]).flatten()
        m_lat = (lat >= BOITE["lat_min"]) & (lat <= BOITE["lat_max"])
        m_lon = (lon >= BOITE["lon_min"]) & (lon <= BOITE["lon_max"])
        ds = f["precip"]
        blocs = []
        for d in range(0, ds.shape[0], 365):
            bloc = ds[d:d + 365, :, :].astype(np.float32)
            blocs.append(bloc[:, m_lat, :][:, :, m_lon])
    precip = np.concatenate(blocs, axis=0)
    dates = [datetime(1981, 1, 1) + timedelta(days=i) for i in range(precip.shape[0])]
    return precip, dates, lat[m_lat], lon[m_lon]


def masque_pays(lats, lons):
    """True pour les pixels dont le centre est dans le Senegal (GADM)."""
    with open(FICHIER_FRONTIERE, encoding="utf-8") as fh:
        geo = json.load(fh)
    anneaux = []
    for feat in geo["features"]:
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        anneaux += [MplPath(np.asarray(p[0])) for p in polys if p and p[0]]
    lon2, lat2 = np.meshgrid(lons, lats)
    pts = np.column_stack([lon2.ravel(), lat2.ravel()])
    dedans = np.zeros(len(pts), dtype=bool)
    for a in anneaux:
        dedans |= a.contains_points(pts)
    return dedans.reshape(len(lats), len(lons))


def detecter(precip, anom, dates, domaine, min_pixels):
    """Criteres de src/analysis/detection.py sur le domaine donne (masque 2D).
    Saison des pluies seulement (mai-octobre), comme le catalogue."""
    n_dom = int(domaine.sum())
    lignes = []
    for i, d in enumerate(dates):
        if d.month not in PHASES:
            continue
        ext = (anom[i] > SEUIL_ANOMALIE) & ~np.isnan(anom[i]) & domaine
        n = int(ext.sum())
        if n < min_pixels:
            continue
        p = precip[i][ext]
        pmax = np.nanmax(p)
        if np.isnan(pmax) or pmax < MIN_PRECIP:
            continue
        lignes.append({"date": d.strftime("%Y-%m-%d"), "max_precip": float(pmax),
                       "mean_precip": float(np.nanmean(p)),
                       "coverage_points": n, "coverage_percent": 100.0 * n / n_dom})
    return pd.DataFrame(lignes).set_index("date")


def series_annuelles(df):
    """max_precip annuel par phase (agregation du script 04 : max sur la phase)."""
    d = df.copy()
    dt = pd.to_datetime(d.index)
    d["year"], d["phase"] = dt.year, dt.month.map(PHASES)
    d = d.dropna(subset=["phase"])
    return d.groupby(["phase", "year"])["max_precip"].max()


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    print("Chargement CHIRPS (boite)...")
    precip, dates, lats, lons = charger_precip()
    anom = np.load(FICHIER_ANOM, allow_pickle=True)["anomalies"]
    clim = np.load(FICHIER_CLIM, allow_pickle=True)
    if anom.shape != precip.shape:
        sys.exit("Anomalies %s et precipitation %s de formes differentes."
                 % (anom.shape, precip.shape))
    if not (np.allclose(clim["lats"], lats) and np.allclose(clim["lons"], lons)):
        sys.exit("Grille de la climatologie differente de celle de la boite.")

    boite = np.ones((len(lats), len(lons)), dtype=bool)
    pays = masque_pays(lats, lons)
    n_boite, n_pays = int(boite.sum()), int(pays.sum())
    seuil_prop = int(round(MIN_PIXELS * n_pays / n_boite))
    print("Pixels : boite %d, Senegal %d (%.0f %%) ; seuil proportionnel %d"
          % (n_boite, n_pays, 100 * n_pays / n_boite, seuil_prop))

    variantes = {
        "boite": detecter(precip, anom, dates, boite, MIN_PIXELS),
        "masque_40": detecter(precip, anom, dates, pays, MIN_PIXELS),
        "masque_prop": detecter(precip, anom, dates, pays, seuil_prop),
    }

    # Controle : la boite doit retrouver le catalogue de production.
    cat = pd.read_csv(FICHIER_CATALOGUE, encoding="utf-8")
    dates_cat = set(cat["date"].astype(str).str[:10])
    dates_boite = set(variantes["boite"].index)
    controle = {"catalogue": len(dates_cat), "boite_recalculee": len(dates_boite),
                "communs": len(dates_cat & dates_boite)}
    print("Controle boite vs catalogue :", controle)

    # Tableau jour par jour
    toutes = sorted(set().union(*[set(v.index) for v in variantes.values()]))
    comp = pd.DataFrame(index=pd.Index(toutes, name="date"))
    for nom, v in variantes.items():
        comp["detecte_" + nom] = comp.index.isin(v.index)
        for col in ("max_precip", "coverage_percent"):
            comp[col + "_" + nom] = v[col].reindex(comp.index)
    comp.to_csv(SORTIE / "comparaison_evenements.csv", encoding="utf-8")

    # Series annuelles par phase (entree des teleconnexions) : boite vs masque.
    s_boite = series_annuelles(variantes["boite"])
    resume_phases = {}
    series = {"boite": s_boite}
    for nom in ("masque_40", "masque_prop"):
        s = series_annuelles(variantes[nom])
        series[nom] = s
        par_phase = {}
        for ph in sorted(set(PHASES.values())):
            a = s_boite.get(ph, pd.Series(dtype=float))
            b = s.get(ph, pd.Series(dtype=float))
            j = pd.concat([a, b], axis=1, keys=["boite", nom]).dropna()
            par_phase[ph] = {
                "annees_communes": int(len(j)),
                "r_max_precip_annuel": round(float(j.corr().iloc[0, 1]), 3) if len(j) > 2 else None,
            }
        resume_phases[nom] = par_phase
    pd.DataFrame(series).to_csv(SORTIE / "series_annuelles.csv", encoding="utf-8")

    b = variantes["boite"]
    resume = {
        "date_calcul": datetime.now().strftime("%Y-%m-%d"),
        "pixels": {"boite": n_boite, "senegal": n_pays, "hors_senegal": n_boite - n_pays},
        "seuils_pixels": {"boite": MIN_PIXELS, "masque_40": MIN_PIXELS,
                          "masque_prop": seuil_prop},
        "controle_catalogue": controle,
        "variantes": {},
        "series_annuelles_vs_boite": resume_phases,
    }
    for nom, v in variantes.items():
        communs = b.index.intersection(v.index)
        d_max = (v.loc[communs, "max_precip"] - b.loc[communs, "max_precip"])
        resume["variantes"][nom] = {
            "evenements": int(len(v)),
            "communs_avec_boite": int(len(communs)),
            "perdus_vs_boite": int(len(b.index.difference(v.index))),
            "nouveaux_vs_boite": int(len(v.index.difference(b.index))),
            "max_precip_change_sur_communs": int((d_max.abs() > 1e-6).sum()),
            "max_precip_ecart_median_mm": round(float(d_max.median()), 2) if len(d_max) else None,
        }
    with open(SORTIE / "resume.json", "w", encoding="utf-8") as fh:
        json.dump(resume, fh, indent=2, ensure_ascii=False)

    # Carte des pixels
    fig, ax = plt.subplots(figsize=(7, 5), dpi=130)
    lon2, lat2 = np.meshgrid(lons, lats)
    ax.scatter(lon2[pays], lat2[pays], s=22, c="#4F46E5", label="Senegal (%d)" % n_pays)
    ax.scatter(lon2[~pays], lat2[~pays], s=22, c="#F59E0B",
               label="hors Senegal (%d)" % (n_boite - n_pays))
    with open(FICHIER_FRONTIERE, encoding="utf-8") as fh:
        geo = json.load(fh)
    for feat in geo["features"]:
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for p in polys:
            xy = np.asarray(p[0])
            ax.plot(xy[:, 0], xy[:, 1], color="#0F172A", lw=0.8)
    ax.set_title("Pixels CHIRPS de la boite de detection")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", fontsize=8); ax.set_aspect("equal")
    fig.tight_layout(); fig.savefig(SORTIE / "masque_pixels.png"); plt.close(fig)

    print(json.dumps(resume, indent=2, ensure_ascii=True))
    print("Sorties :", SORTIE)


if __name__ == "__main__":
    main()
