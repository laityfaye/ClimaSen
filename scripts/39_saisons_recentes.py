#!/usr/bin/env python3
"""Saisons recentes : pluies extremes depuis 2024, comparees a la reference 1981-2023.

Le catalogue de l'etude (1 317 evenements, 1981-2023) et tous les resultats qui en
decoulent restent INCHANGES. Les annees recentes sont traitees comme le fait l'OMM
avec une periode de reference fixe : leurs anomalies sont calculees avec la
climatologie 1981-2023 deja enregistree (moyenne et ecart-type de chaque jour de
l'annee), puis le meme detecteur s'applique. Recalculer la climatologie sur une
nouvelle periode changerait au contraire tous les resultats de 1981-2023.

Methode, identique a celle du catalogue (verifiee : 2023 retraitee redonne les
memes anomalies au bit pres et les 34 memes evenements) :
  1. CHIRPS v2.0, pluie journaliere 0,25 deg : fichier annuel definitif quand il
     existe, sinon fichiers mensuels PRELIMINAIRES (publies quelques jours apres la
     pluie, remplaces ensuite par la version definitive) ;
  2. extraction de la grille de l'etude (18 x 25 pixels) ;
  3. anomalies : src.analysis.climatology.calculate_standardized_anomalies_robust ;
  4. detection : src.analysis.detection.ExtremeEventDetector (> +2 ecarts-types,
     >= 40 pixels, >= 5 mm, >= 5 % de couverture) ; seuls les mois de mai a octobre
     sont gardes, comme dans le catalogue ;
  5. habitants de la zone touchee : population de l'annee de l'evenement, projetee
     par l'ANSD (script 37, API SDMX de l'ANSD), memes pixels que le script 33.

Les NetCDF CHIRPS (~80 Mo par an) sont gardes en cache hors du depot
(data/raw/chirps_recent/, ignore par git) ; seule la grille de l'etude est versionnee.

Sorties : data/processed/saisons_recentes.npz (pluie et anomalies, grille de l'etude)
          outputs/saisons_recentes/evenements_recents.csv
          outputs/saisons_recentes/annees_recentes.csv
          outputs/saisons_recentes/resume.json
Usage   : py -3 scripts/39_saisons_recentes.py [--annee-debut 2024]
"""
import argparse
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "src"))
from src.analysis.climatology import calculate_standardized_anomalies_robust  # noqa: E402
from src.analysis.detection import ExtremeEventDetector  # noqa: E402

PROCESSED = RACINE / "data" / "processed"
CACHE = RACINE / "data" / "raw" / "chirps_recent"
SORTIE = RACINE / "outputs" / "saisons_recentes"
CHC = "https://data.chc.ucsb.edu/products/CHIRPS-2.0"
DEFINITIF = CHC + "/global_daily/netcdf/p25/chirps-v2.0.{a}.days_p25.nc"
PRELIM = CHC + "/prelim/global_daily/netcdf/p25/chirps-v2.0.{a}.{m:02d}.days_p25.nc"
SEUIL_SIGMA = 2.0          # critere du script 01 (et du script 33)
MOIS_SAISON = range(5, 11)  # mai a octobre : les trois phases du catalogue
PHASES = {5: "Phase_1_debut", 6: "Phase_1_debut", 7: "Phase_2_pleine",
          8: "Phase_2_pleine", 9: "Phase_3_fin", 10: "Phase_3_fin"}


def maintenant():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def telecharger(url, dest, essais=4):
    """Telecharge `url` dans `dest` (cache) ; False si le fichier n'existe pas (404)."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    for k in range(essais):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ClimatSen/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                while True:
                    bloc = r.read(1 << 20)
                    if not bloc:
                        break
                    f.write(bloc)
            tmp.replace(dest)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if k == essais - 1:
                raise
        except Exception:                           # noqa: BLE001
            if k == essais - 1:
                raise
        time.sleep(5 * (k + 1))
    return False


def extraire(chemin, lats, lons):
    """Grille de l'etude extraite d'un NetCDF CHIRPS : (pluie, dates)."""
    import xarray as xr
    with xr.open_dataset(chemin) as ds:
        p = ds["precip"].sel(latitude=lats, longitude=lons, method="nearest")
        dates = pd.to_datetime(p["time"].values)
        arr = p.values.astype(np.float64)
    arr = np.where(arr < -9000, np.nan, arr)
    garder = ~np.isnan(arr).all(axis=(1, 2))         # jours pas encore publies
    return arr[garder], dates[garder]


def pluie_annee(annee, lats, lons):
    """Pluie de l'annee : fichier definitif, complete par les mois preliminaires
    qui suivent sa derniere date. Renvoie (pluie, dates, source par jour)."""
    morceaux, sources = [], []
    fin = None
    f_def = CACHE / f"chirps-v2.0.{annee}.days_p25.nc"
    if telecharger(DEFINITIF.format(a=annee), f_def):
        arr, d = extraire(f_def, lats, lons)
        if len(d):
            morceaux.append((arr, d))
            sources += ["definitif"] * len(d)
            fin = d[-1]
    for m in range(1, 13):
        if fin is not None and (annee, m) <= (fin.year, fin.month):
            continue
        if date(annee, m, 1) > date.today():
            break
        f_pre = CACHE / f"prelim-{annee}-{m:02d}.nc"
        if f_pre.exists():
            f_pre.unlink()                          # le preliminaire s'enrichit : relire
        if not telecharger(PRELIM.format(a=annee, m=m), f_pre):
            continue
        arr, d = extraire(f_pre, lats, lons)
        if len(d):
            morceaux.append((arr, d))
            sources += ["preliminaire"] * len(d)
    if not morceaux:
        return None, None, None
    arr = np.concatenate([a for a, _ in morceaux])
    dates = pd.DatetimeIndex(np.concatenate([d.values for _, d in morceaux]))
    return arr, dates, np.array(sources)


def script37():
    spec = importlib.util.spec_from_file_location(
        "exposition_projetee", RACINE / "scripts" / "37_exposition_projetee.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--annee-debut", type=int, default=2024)
    args = ap.parse_args()

    clim = np.load(PROCESSED / "climatology_senegal.npz", allow_pickle=True)
    lats, lons = clim["lats"].astype(float), clim["lons"].astype(float)
    annees = list(range(args.annee_debut, date.today().year + 1))

    pluies, anoms, dates, sources = [], [], [], []
    for a in annees:
        print(f"{a} ...")
        arr, d, src = pluie_annee(a, lats, lons)
        if arr is None:
            print("   aucune donnee publiee")
            continue
        an = calculate_standardized_anomalies_robust(arr, list(d.to_pydatetime()),
                                                      clim["climatology"], clim["std_dev"])
        pluies.append(arr)
        anoms.append(an)
        dates.append(d)
        sources.append(src)
        print(f"   {d[0].date()} -> {d[-1].date()} ({(src == 'preliminaire').sum()} jours preliminaires)")
    pluie = np.concatenate(pluies)
    anom = np.concatenate(anoms)
    jours = pd.DatetimeIndex(np.concatenate([d.values for d in dates]))
    source = np.concatenate(sources)
    np.savez_compressed(PROCESSED / "saisons_recentes.npz",
                        pluie=pluie.astype(np.float32), anomalies=anom.astype(np.float32),
                        dates=np.array([str(d.date()) for d in jours]), source=source,
                        lats=lats, lons=lons)

    # Detection, comme le catalogue : meme detecteur, mois de mai a octobre.
    ev = ExtremeEventDetector().detect_events(pluie, anom, list(jours.to_pydatetime()), lats, lons)
    ev = ev.reset_index()
    ev = ev.rename(columns={ev.columns[0]: "date"})         # l'index des dates, quel que soit son nom
    ev["date"] = pd.to_datetime(ev["date"])
    ev = ev[ev["date"].dt.month.isin(MOIS_SAISON)].copy()
    ev["phase"] = ev["date"].dt.month.map(PHASES)
    ev["year"], ev["month"] = ev["date"].dt.year, ev["date"].dt.month
    rang_jour = {d: k for k, d in enumerate(jours)}
    ev["source"] = [source[rang_jour[d]] for d in ev["date"]]

    # Habitants de la zone touchee, population de l'annee de l'evenement (ANSD).
    s37 = script37()
    loc, _, _, _ = s37.localites_projetees(tuple(sorted({2023} | {a for a in annees if a <= 2030})))
    dans = loc[loc["pix_i"] >= 0]
    pop_pix = {}
    for a in annees:
        col = f"POP_{min(a, 2030)}"
        pop_pix[a] = np.zeros(pluie.shape[1:])
        np.add.at(pop_pix[a], (dans["pix_i"], dans["pix_j"]), dans[col])
    pop_nat = {a: float(dans[f"POP_{min(a, 2030)}"].sum()) for a in annees}
    touches, parts, pix = [], [], []
    for d in ev["date"]:
        masque = anom[rang_jour[d]] > SEUIL_SIGMA
        n = float(pop_pix[d.year][masque].sum())
        touches.append(int(round(n)))
        parts.append(round(100 * n / pop_nat[d.year], 2))
        pix.append(int(masque.sum()))
    ev["population_touchee"] = touches
    ev["annee_population"] = [min(a, 2030) for a in ev["year"]]
    ev["part_population_nationale_pct"] = parts
    if not (np.array(pix) == ev["coverage_points"].to_numpy()).all():
        raise SystemExit("Masque des habitants different de la couverture detectee")

    colonnes = ["date", "phase", "source", "coverage_points", "coverage_percent",
                "max_precip", "mean_precip", "max_anomaly", "mean_anomaly",
                "centroid_lat", "centroid_lon", "population_touchee", "annee_population",
                "part_population_nationale_pct"]
    ev = ev.sort_values("date")[[c for c in colonnes if c in ev.columns]]
    SORTIE.mkdir(parents=True, exist_ok=True)
    ev.assign(date=ev["date"].dt.date).to_csv(SORTIE / "evenements_recents.csv",
                                              index=False, encoding="utf-8")

    # Comparaison a la reference 1981-2023 (catalogue de l'etude).
    cat = pd.read_csv(PROCESSED / "extreme_events_phases_senegal.csv", parse_dates=["date"])
    ref = cat.groupby(cat["date"].dt.year).size().reindex(range(1981, 2024), fill_value=0)
    lignes = []
    for a in annees:
        e = ev[ev["date"].dt.year == a]
        jours_a = jours[jours.year == a]
        if not len(jours_a):
            continue
        fin = jours_a.max()
        complete = fin >= pd.Timestamp(a, 10, 31)
        # Meme fenetre (1er janvier -> derniere date) pour les annees de reference.
        ref_fen = cat[cat["date"].dt.dayofyear <= fin.dayofyear].groupby(
            cat["date"].dt.year).size().reindex(range(1981, 2024), fill_value=0)
        n = len(e)
        lignes.append({
            "annee": a, "jusqu_au": str(fin.date()), "saison_complete": bool(complete),
            "jours_preliminaires": int((source[jours.year == a] == "preliminaire").sum()),
            "evenements": n,
            "reference_meme_periode_moyenne": round(float(ref_fen.mean()), 1),
            "rang_sur_44_meme_periode": int((ref_fen > n).sum()) + 1,
            "phase_1": int((e["phase"] == "Phase_1_debut").sum()),
            "phase_2": int((e["phase"] == "Phase_2_pleine").sum()),
            "phase_3": int((e["phase"] == "Phase_3_fin").sum()),
            "population_touchee_mediane": int(e["population_touchee"].median()) if n else 0,
            "population_touchee_max": int(e["population_touchee"].max()) if n else 0,
        })
    t = pd.DataFrame(lignes)
    t.to_csv(SORTIE / "annees_recentes.csv", index=False, encoding="utf-8")

    resume = {
        "calcule_le": maintenant(),
        "methode": "climatologie de reference 1981-2023 (fixe), detecteur du catalogue, "
                   "mois de mai a octobre",
        "source": "CHIRPS v2.0 0,25 deg (UCSB Climate Hazards Center) : annuel definitif, "
                  "complete par les mensuels preliminaires",
        "population": "ANSD, projections 2023-2030 par commune (API SDMX), localites RGPH-5",
        "reference_1981_2023": {"evenements_par_an_moyenne": round(float(ref.mean()), 1),
                                "minimum": int(ref.min()), "maximum": int(ref.max())},
        "annees": lignes,
    }
    (SORTIE / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(t.to_string(index=False))


if __name__ == "__main__":
    main()
