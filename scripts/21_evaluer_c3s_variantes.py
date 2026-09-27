#!/usr/bin/env python3
"""Evaluation des variantes de prevision Copernicus C3S pour la veille pre-saison.

PROTOCOLE FIXE AVANT TOUT TELECHARGEMENT (27/09/2026). Toutes les variantes
ci-dessous sont rapportees, quel que soit leur resultat: on ne choisit pas
apres coup celle qui "marche".

Question: une autre facon d'utiliser C3S distingue-t-elle mieux les annees
extremes (veille.annees) que la reference ECMWF, emission avril, JAS
(AUC LOYO 0,59 sur 1981-2016) ?

Modeles: le systeme courant de chacun des 8 centres C3S:
  ecmwf 51, meteo_france 9, ukmo 604, dwd 22, cmcc 35, ncep 2, eccc 4, jma 3.
Periode commune de retro-prevision: 1993-2016 (24 saisons).

Variantes:
  V1  ECMWF seul,    emission avril, juillet-septembre (reference)
  V2  multi-modele,  emission avril, juillet-septembre
  V3  multi-modele,  emission mai,   juillet-septembre
  V4  multi-modele,  emission mai,   aout-octobre
  V5  ECMWF seul,    emission mai,   aout-octobre

Multi-modele: moyenne a poids egaux des anomalies standardisees (z-score sur
1993-2016) de la moyenne d'ensemble de chaque modele. Predicteur unique ->
calibration logistique et competence LOYO de veille.c3s.calibrer (seuil
d'annee extreme reestime sans l'annee testee). Avec 24 saisons (~8 extremes),
un p < 0,05 demande une AUC d'environ 0,75: le test manque de puissance,
et un resultat non significatif ne prouve pas l'absence de signal.

Usage: py -3 scripts/21_evaluer_c3s_variantes.py
Sortie: outputs/veille/evaluation_c3s_variantes.json
"""
import json
import sys
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from veille import DOSSIER_SORTIE  # noqa: E402
from veille import annees as mod_annees  # noqa: E402
from veille import c3s  # noqa: E402
from veille.cube import _chemin_court  # noqa: E402

MODELES = [("ecmwf", "51"), ("meteo_france", "9"), ("ukmo", "604"), ("dwd", "22"),
           ("cmcc", "35"), ("ncep", "2"), ("eccc", "4"), ("jma", "3")]
ANNEES = list(range(1993, 2017))
# emission -> echeances telechargees; puis (emission, saison) -> echeances retenues
TELECHARGE = {4: (4, 5, 6), 5: (3, 4, 5, 6)}
SAISONS = {(4, "JAS"): (4, 5, 6), (5, "JAS"): (3, 4, 5), (5, "ASO"): (4, 5, 6)}
VARIANTES = [
    ("V1", "ECMWF seul, emission avril, juillet-septembre", ["ecmwf"], 4, "JAS"),
    ("V2", "multi-modele, emission avril, juillet-septembre", None, 4, "JAS"),
    ("V3", "multi-modele, emission mai, juillet-septembre", None, 5, "JAS"),
    ("V4", "multi-modele, emission mai, aout-octobre", None, 5, "ASO"),
    ("V5", "ECMWF seul, emission mai, aout-octobre", ["ecmwf"], 5, "ASO"),
]
DOSSIER = c3s.DOSSIER / "variantes"


def fichier(centre, systeme, emission):
    return DOSSIER / ("%s_s%s_emis%02d_1993-2016.nc" % (centre, systeme, emission))


def telecharger(centre, systeme, emission, client):
    f = fichier(centre, systeme, emission)
    if f.is_file() and f.stat().st_size > 0:
        return f
    DOSSIER.mkdir(parents=True, exist_ok=True)
    # Requete construite ici: c3s.requete() ne connait que les systemes de
    # production (ECMWF), elle levait KeyError pour les autres centres.
    r = {"originating_centre": centre, "system": systeme,
         "variable": ["total_precipitation"], "product_type": ["monthly_mean"],
         "year": [str(a) for a in ANNEES], "month": ["%02d" % emission],
         "leadtime_month": [str(e) for e in TELECHARGE[emission]],
         "data_format": "netcdf", "area": c3s.BOITE}
    print("  %s %s emission %02d: telechargement..." % (centre, systeme, emission), flush=True)
    tmp = f.with_suffix(".part")
    client.retrieve(c3s.JEU, r, str(tmp))
    tmp.replace(f)
    return f


def moyennes_annuelles(f, echeances):
    """Moyenne d'ensemble de la pluie sur la boite, par annee d'emission."""
    import xarray as xr
    ds = xr.open_dataset(_chemin_court(f))
    try:
        da = ds["tprate"].sel(forecastMonth=list(echeances))
        poids = np.cos(np.deg2rad(da["latitude"]))
        boite = da.weighted(poids).mean(dim=["latitude", "longitude"])
        par_an = boite.mean(dim=["forecastMonth", "number"], skipna=True)
        annees = [int(str(t)[:4]) for t in ds["forecast_reference_time"].values]
        return dict(zip(annees, (par_an.values.ravel() * 86400000.0).tolist()))
    finally:
        ds.close()


def main():
    client = c3s._client()
    donnees = {}          # (centre, emission, saison) -> {annee: moyenne}
    for centre, systeme in MODELES:
        for emission in TELECHARGE:
            try:
                f = telecharger(centre, systeme, emission, client)
            except Exception as exc:  # un modele absent n'arrete pas l'evaluation
                print("  ! %s %s emission %02d indisponible: %s" % (
                    centre, systeme, emission, str(exc).splitlines()[-1][:120]))
                continue
            for (em, saison), ech in SAISONS.items():
                if em == emission:
                    donnees[(centre, emission, saison)] = moyennes_annuelles(f, ech)

    emp = mod_annees.empreinte()
    resultats = []
    for code, libelle, centres, emission, saison in VARIANTES:
        dispo = [c for c, _ in MODELES if (c, emission, saison) in donnees
                 and (centres is None or c in centres)]
        if not dispo:
            resultats.append({"variante": code, "libelle": libelle, "calculable": False})
            continue
        z = []
        for c in dispo:
            serie = np.array([donnees[(c, emission, saison)].get(a, np.nan) for a in ANNEES])
            z.append((serie - np.nanmean(serie)) / np.nanstd(serie, ddof=1))
        z = np.nanmean(z, axis=0)
        # calibrer() attend des "membres": un vecteur a 1 valeur par annee suffit
        cal = c3s.calibrer({a: np.array([v]) for a, v in zip(ANNEES, z) if np.isfinite(v)}, emp)
        resultats.append({"variante": code, "libelle": libelle, "modeles": dispo,
                          "n_modeles": len(dispo), "competence": cal["competence"],
                          "coefficient": round(cal["coefficient"], 3)})
        comp = cal["competence"]
        print("%s %-48s modeles=%d  AUC=%.2f p=%.3f BSS=%+.2f r=%.2f" % (
            code, libelle, len(dispo), comp["auc"], comp["p_permutation"],
            comp["brier_skill_score"], comp["correlation_pluie_empreinte"]), flush=True)

    sortie = {"protocole": __doc__, "annees": [ANNEES[0], ANNEES[-1]], "resultats": resultats}
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    (DOSSIER_SORTIE / "evaluation_c3s_variantes.json").write_text(
        json.dumps(sortie, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
