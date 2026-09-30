#!/usr/bin/env python3
"""Indice de risque pluies extremes par departement (module Vulnerabilite).

Decisions du 30/09/2026 (voir la page de synchronisation) :
  1. echelle : les 46 departements (contours OCHA/HDX 2024, Keur Massar compris) ;
  2. chaque composante ramenee entre 0 et 1 sur les 46 departements, puis combinee ;
  3. alea : pas seulement les anomalies > 2 sigma, on ajoute une intensite absolue
     (jours >= 50 mm), pour ne pas sous-estimer Dakar et sa banlieue.

Composantes
  Alea (A)          : grille CHIRPS 0,25 deg, 1981-2023, mai-octobre.
                      - jours_anomalie_2sigma : jours par an ou l'anomalie standardisee
                        depasse +2 sigma (definition du memoire, a l'echelle du pixel) ;
                      - jours_50mm : jours par an ou la pluie reconstituee atteint 50 mm.
                      Pluie reconstituee = climatologie + anomalie x ecart-type
                      (anomalies plafonnees a +/-20 sigma par le script 01).
                      Un departement prend la moyenne des pixels dont le centre est dans
                      son contour ; s'il n'en contient aucun (Dakar, Pikine, Guediawaye,
                      Keur Massar...), le pixel terrestre le plus proche de son centre.
  Exposition (E)    : population RGPH-5 2023 (Repertoire des localites, ANSD).
  Vulnerabilite (V) : taux de pauvrete EHCVM 2021-2022 de la region (ANSD) ; meme valeur
                      pour tous les departements d'une region, faute de donnee plus fine.

Normalisation : rang centile sur les 46 departements (0 = plus faible, 1 = plus fort),
robuste aux valeurs extremes (la population de Mbacke ou de Dakar ecraserait un min-max).
Indice principal : moyenne geometrique (A x E x V)^(1/3), qui garde l'ordre du produit
A x E x V du dossier tout en restant entre 0 et 1. Variante publiee : moyenne simple.

Entrees : data/processed/standardized_anomalies_senegal.npz, climatology_senegal.npz,
          data/raw/ansd/*.csv, data/raw/hdx/sen_admin2.geojson
Sortie  : outputs/vulnerabilite/indice_risque_departements.csv (+ resume.json)

Usage : py -3 scripts/26_indice_risque_departements.py
"""
import json
import unicodedata
import re
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

RACINE = Path(__file__).resolve().parent.parent
PROCESSED = RACINE / "data" / "processed"
ANSD = RACINE / "data" / "raw" / "ansd"
HDX = RACINE / "data" / "raw" / "hdx"
SORTIE = RACINE / "outputs" / "vulnerabilite"

MOIS_SAISON = (5, 6, 7, 8, 9, 10)
SEUIL_SIGMA = 2.0
SEUIL_MM = 50.0

# RGPH-5 (Repertoire des localites) -> HDX adm2_name, apres normalisation.
ALIAS_DEPARTEMENTS = {
    "KOUPENTOUM": "KOUMPENTOUM",
    "MALEMHODDAR": "MALEMHODAR",
    "MEDINAYOROFOULAH": "MEDINAYOROFOULA",
    "NIORO": "NIORODURIP",
    "RANEROUFERLO": "RANEROU",
}


def cle(texte):
    """Nom normalise : sans accent, majuscules, lettres et chiffres seulement."""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", t)


def departements_hdx():
    geo = json.loads((HDX / "sen_admin2.geojson").read_text(encoding="utf-8"))
    lignes = []
    for f in geo["features"]:
        p = f["properties"]
        lignes.append({
            "pcode": p["adm2_pcode"], "departement": p["adm2_name"],
            "region": p["adm1_name"], "superficie_km2": p.get("area_sqkm"),
            "geometrie": shape(f["geometry"]),
        })
    return pd.DataFrame(lignes)


def population_rgph():
    d = pd.read_csv(ANSD / "rgph_repertoire_localites_1988-2023.csv", encoding="utf-8-sig")
    d.columns = [c.strip() for c in d.columns]
    annee = d.columns[-1]
    d["cle"] = d["Departement"].map(cle).replace(ALIAS_DEPARTEMENTS)
    pop = d[d[annee].isin([2013, 2023])].pivot_table(
        index="cle", columns=annee, values="POPULATION", aggfunc="sum")
    men = d[d[annee] == 2023].groupby("cle")["MENAGE"].sum()
    out = pd.DataFrame({
        "population_2013": pop.get(2013), "population_2023": pop.get(2023),
        "menages_2023": men,
    })
    return out


def pauvrete_region():
    p = pd.read_csv(ANSD / "ehcvm_2021-2022_pauvrete_par_region.csv")
    return p.assign(cle_region=p["region"].map(cle)).set_index("cle_region")["taux_pauvrete_p0_pct"]


def alea_par_pixel():
    anom = np.load(PROCESSED / "standardized_anomalies_senegal.npz", allow_pickle=True)
    clim = np.load(PROCESSED / "climatology_senegal.npz", allow_pickle=True)
    dates = pd.to_datetime(anom["dates"])
    a = anom["anomalies"]
    saison = dates.month.isin(MOIS_SAISON)
    a, dates = a[saison], dates[saison]
    doy = dates.dayofyear.values - 1
    pluie = np.clip(clim["climatology"][doy] + a * clim["std_dev"][doy], 0, None)
    n_ans = dates.year.nunique()
    # CHIRPS ne couvre que les terres : en mer, climatologie et anomalies valent 0.
    terre = clim["climatology"].sum(axis=0) > 0
    return {
        "lats": clim["lats"], "lons": clim["lons"], "terre": terre,
        "jours_anomalie_2sigma": (a > SEUIL_SIGMA).sum(axis=0) / n_ans,
        "jours_50mm": (pluie >= SEUIL_MM).sum(axis=0) / n_ans,
        "periode": f"{dates.year.min()}-{dates.year.max()}",
    }


def alea_par_departement(dep, px):
    lats, lons = px["lats"], px["lons"]
    centres = [(i, j, Point(float(lons[j]), float(lats[i])))
               for i in range(lats.size) for j in range(lons.size)]
    lignes = []
    for _, r in dep.iterrows():
        g = r["geometrie"]
        dedans = [(i, j) for i, j, pt in centres if px["terre"][i, j] and g.contains(pt)]
        methode = "pixels dans le contour"
        if not dedans:
            # Petit departement (Dakar et sa banlieue) : pixel terrestre le plus proche.
            c = g.centroid
            terrestres = [(i, j, pt) for i, j, pt in centres if px["terre"][i, j]]
            i, j, _ = min(terrestres, key=lambda x: x[2].distance(c))
            dedans, methode = [(i, j)], "pixel terrestre le plus proche"
        ii, jj = zip(*dedans)
        lignes.append({
            "pcode": r["pcode"], "n_pixels": len(dedans), "methode_alea": methode,
            "jours_anomalie_2sigma_an": float(px["jours_anomalie_2sigma"][ii, jj].mean()),
            "jours_50mm_an": float(px["jours_50mm"][ii, jj].mean()),
        })
    return pd.DataFrame(lignes)


def centile(s):
    return s.rank(pct=True, method="average")


def main():
    dep = departements_hdx()
    dep["cle"] = dep["departement"].map(cle)
    dep["cle_region"] = dep["region"].map(cle)

    pop = population_rgph()
    manquants = sorted(set(dep["cle"]) - set(pop.index))
    if manquants:
        raise SystemExit(f"Departements HDX sans population RGPH-5 : {manquants}")
    t = dep.join(pop, on="cle")
    t["taux_pauvrete_region_pct"] = t["cle_region"].map(pauvrete_region())
    if t["taux_pauvrete_region_pct"].isna().any():
        raise SystemExit("Region sans taux de pauvrete : "
                         f"{sorted(t.loc[t['taux_pauvrete_region_pct'].isna(), 'region'])}")

    px = alea_par_pixel()
    t = t.merge(alea_par_departement(dep, px), on="pcode")

    t["croissance_2013_2023_pct"] = (t["population_2023"] / t["population_2013"] - 1) * 100
    t["densite_2023_hab_km2"] = t["population_2023"] / t["superficie_km2"]
    t["pauvres_estimes_2023"] = t["population_2023"] * t["taux_pauvrete_region_pct"] / 100

    t["A_alea"] = (centile(t["jours_anomalie_2sigma_an"]) + centile(t["jours_50mm_an"])) / 2
    t["A_alea"] = centile(t["A_alea"])
    t["E_exposition"] = centile(t["population_2023"])
    t["V_vulnerabilite"] = centile(t["taux_pauvrete_region_pct"])
    t["indice_risque"] = (t["A_alea"] * t["E_exposition"] * t["V_vulnerabilite"]) ** (1 / 3)
    t["indice_moyenne_simple"] = t[["A_alea", "E_exposition", "V_vulnerabilite"]].mean(axis=1)
    t["rang"] = t["indice_risque"].rank(ascending=False, method="min").astype(int)

    colonnes = [
        "rang", "pcode", "departement", "region",
        "population_2013", "population_2023", "croissance_2013_2023_pct", "menages_2023",
        "superficie_km2", "densite_2023_hab_km2", "taux_pauvrete_region_pct",
        "pauvres_estimes_2023", "n_pixels", "methode_alea",
        "jours_anomalie_2sigma_an", "jours_50mm_an",
        "A_alea", "E_exposition", "V_vulnerabilite", "indice_risque", "indice_moyenne_simple",
    ]
    t = t.sort_values("rang")[colonnes]
    SORTIE.mkdir(parents=True, exist_ok=True)
    t.round(4).to_csv(SORTIE / "indice_risque_departements.csv", index=False, encoding="utf-8")

    resume = {
        "periode_alea": px["periode"], "mois": list(MOIS_SAISON),
        "seuils": {"anomalie_sigma": SEUIL_SIGMA, "pluie_mm": SEUIL_MM},
        "departements": int(len(t)),
        "population_2023_totale": int(t["population_2023"].sum()),
        "departements_pixel_le_plus_proche": t.loc[
            t["methode_alea"] == "pixel terrestre le plus proche", "departement"].tolist(),
        "pixels_terrestres": int(px["terre"].sum()),
        "normalisation": "rang centile sur les 46 departements",
        "indice": "(A x E x V)^(1/3)",
        "sources": {
            "alea": "CHIRPS 0,25 deg via data/processed (scripts 01)",
            "exposition": "ANSD, RGPH-5 2023, Repertoire des localites",
            "vulnerabilite": "ANSD, EHCVM 2021-2022, Tableau III-2 (region)",
            "contours": "OCHA COD-AB Senegal v02 (2024), CC BY-IGO",
        },
        "top10": t.head(10)[["rang", "departement", "indice_risque"]].round(3).to_dict("records"),
    }
    (SORTIE / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(f"{len(t)} departements -> {SORTIE / 'indice_risque_departements.csv'}")
    print(t.head(15)[["rang", "departement", "region", "population_2023",
                      "jours_anomalie_2sigma_an", "jours_50mm_an", "taux_pauvrete_region_pct",
                      "indice_risque"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
