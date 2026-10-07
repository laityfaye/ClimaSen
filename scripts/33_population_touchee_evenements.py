#!/usr/bin/env python3
"""Population touchee par chaque evenement de pluie extreme (RGPH-5 x coordonnees ANSD).

Croise trois sources :
  - le Repertoire des localites (ANSD, RGPH-5 2023) : population et menages par localite,
    sans coordonnees ;
  - les coordonnees geographiques des localites transmises par l'ANSD le 04/10/2026
    (data/raw/ansd/ansd_coordonnees_localites.csv, converti du .xls d'origine) ;
  - les anomalies quotidiennes CHIRPS du script 01 (data/processed).

Etapes
  1. Communes : chaque commune du RGPH-5 est rapprochee d'une commune ANSD du meme
     departement (nom identique, puis nom approche, puis commune decoupee dont le nom
     commence par celui de la commune ANSD, puis alias manuels).
  2. Localites : dans la commune retrouvee, nom identique puis nom approche (difflib
     >= 0,85). Sinon la localite prend le centre de sa commune (moyenne des localites
     ANSD de la commune), ou a defaut celui de son departement. La colonne `precision`
     dit lequel.
  3. Pixel : chaque localite placee est rattachee au pixel CHIRPS 0,25 deg dont le centre
     est le plus proche (a moins d'un demi-pixel).
  4. Evenement : les pixels du jour ou l'anomalie depasse +2 sigma (critere du script 01 ;
     on retrouve exactement `coverage_points` du catalogue pour les 1 317 evenements).
     Population touchee = somme de la population 2023 des localites de ces pixels.

Lecture : population ACTUELLE (2023) des zones touchees par chaque evenement passe. Pour
un evenement de 1985, c'est le nombre d'habitants d'aujourd'hui qui vivent la ou la pluie
a ete extreme, pas le nombre d'habitants de 1985. Seules les localites du Senegal comptent :
les pixels hors du pays (Gambie, Mauritanie...) n'ajoutent personne.

Sorties : outputs/exposition_evenements/ ; data/processed/localites_rgph5_placees.csv
Usage   : py -3 scripts/33_population_touchee_evenements.py
"""
import difflib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
ANSD = RACINE / "data" / "raw" / "ansd"
PROCESSED = RACINE / "data" / "processed"
SORTIE = RACINE / "outputs" / "exposition_evenements"

SEUIL_SIGMA = 2.0
SEUIL_COMMUNE = 0.75
SEUIL_LOCALITE = 0.85
DEMI_PIXEL = 0.125

# Departements du RGPH-5 (2023) -> departement du fichier de coordonnees ANSD (decoupage
# anterieur a 2021 : Keur Massar faisait partie de Pikine).
ALIAS_DEPARTEMENTS = {"KEURMASSAR": "PIKINE", "RANEROUFERLO": "RANEROU",
                      "KOUPENTOUM": "KOUMPENTOUM"}
# Communes dont le nom differe trop pour un rapprochement automatique (verifiees a la main).
ALIAS_COMMUNES = {
    ("DAKAR", "DAKARPLATEAU"): "PLATEAU",
    # Le fichier ANSD donne l'ancien et le nouveau nom : « KEUR MOUSSEU (KEUR MOUSSA) »...
    ("KEURMASSAR", "JAXAAYPARCELLES"): "DIAXAYPARCELLENIAKOURAP",
    ("THIES", "KEURMOUSSA"): "KEURMOUSSEUKEURMOUSSA",
    ("LINGUERE", "THIAMENEPASSE"): "THIAMENEDJOLOFTHIAMENEPASS",
    ("KOUPENTOUM", "BAMBATHIALENE"): "BAMBANDIAYENEBAMBATHIALENE",
}
ROMAINS = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7",
           "VIII": "8", "IX": "9", "X": "10"}


def cle(texte):
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return "".join(ROMAINS.get(m, m) for m in t.split())


def charger():
    r = pd.read_csv(ANSD / "rgph_repertoire_localites_1988-2023.csv", encoding="utf-8-sig")
    r.columns = [c.strip() for c in r.columns]
    r = r[r[r.columns[-1]] == 2023].copy()
    r = r.rename(columns={"QUARTIER_VILLAGE_HAMEAU": "LOCALITE"})
    a = pd.read_csv(ANSD / "ansd_coordonnees_localites.csv", encoding="utf-8")
    for t in (r, a):
        t["kc"] = t["COMMUNE"].map(cle)
        t["kl"] = t["LOCALITE"].map(cle)
    r["kd"] = r["Departement"].map(cle).replace(ALIAS_DEPARTEMENTS)
    a["kd"] = a["DEPARTEMENT"].map(cle)
    return r, a


def rapprocher_communes(r, a):
    communes = r.groupby(["Departement", "COMMUNE", "kd", "kc"], as_index=False)[
        "POPULATION"].sum()
    par_dep = a.groupby("kd")["kc"].apply(lambda s: sorted(set(s))).to_dict()
    toutes = set(a["kc"])
    modes, cibles = [], []
    for _, c in communes.iterrows():
        cand = par_dep.get(c["kd"], [])
        alias = ALIAS_COMMUNES.get((cle(c["Departement"]), c["kc"]))
        if c["kc"] in cand or (c["kc"] in toutes and not cand):
            modes.append("nom identique"); cibles.append(c["kc"])
        elif alias:
            modes.append("alias verifie"); cibles.append(alias)
        else:
            m = difflib.get_close_matches(c["kc"], cand, n=1, cutoff=SEUIL_COMMUNE)
            if m:
                modes.append("nom approche"); cibles.append(m[0])
                continue
            p = [x for x in cand if c["kc"].startswith(x) or x.startswith(c["kc"])]
            if p:
                modes.append("commune decoupee"); cibles.append(p[0])
            else:
                modes.append("aucune"); cibles.append(None)
    communes["mode"] = modes
    communes["commune_ansd"] = cibles
    return communes


def placer_localites(r, a, communes):
    ref = communes.set_index(["Departement", "COMMUNE"])["commune_ansd"]
    r = r.copy()
    r["kc_ansd"] = [ref.get((d, c)) for d, c in zip(r["Departement"], r["COMMUNE"])]
    pts = a.groupby(["kc", "kl"])[["LON", "LAT"]].mean()
    centre_com = a.groupby("kc")[["LON", "LAT"]].mean()
    centre_dep = a.groupby("kd")[["LON", "LAT"]].mean()
    noms = a.groupby("kc")["kl"].apply(lambda s: sorted(set(s))).to_dict()
    lon, lat, prec = [], [], []
    for kd, kc, kl in zip(r["kd"], r["kc_ansd"], r["kl"]):
        if kc is not None and (kc, kl) in pts.index:
            x, y = pts.loc[(kc, kl)]; p = "localite (nom identique)"
        elif kc is not None and (m := difflib.get_close_matches(kl, noms.get(kc, []), n=1,
                                                                 cutoff=SEUIL_LOCALITE)):
            x, y = pts.loc[(kc, m[0])]; p = "localite (nom approche)"
        elif kc is not None and kc in centre_com.index:
            x, y = centre_com.loc[kc]; p = "centre de la commune"
        else:
            x, y = centre_dep.loc[kd]; p = "centre du departement"
        lon.append(float(x)); lat.append(float(y)); prec.append(p)
    r["LON"], r["LAT"], r["precision"] = lon, lat, prec
    return r


def rattacher_pixels(r, lats, lons):
    i = np.abs(r["LAT"].values[:, None] - lats[None, :]).argmin(axis=1)
    j = np.abs(r["LON"].values[:, None] - lons[None, :]).argmin(axis=1)
    dy = np.abs(r["LAT"].values - lats[i])
    dx = np.abs(r["LON"].values - lons[j])
    dans = (dy <= DEMI_PIXEL + 1e-9) & (dx <= DEMI_PIXEL + 1e-9)
    # Bord de grille : la pointe des Almadies (Ngor, Ouakam) depasse le dernier pixel a
    # l'ouest. On rattache au pixel voisin ce qui est a moins d'un pixel du bord.
    bord = ~dans & (dy <= 2 * DEMI_PIXEL + 1e-9) & (dx <= 2 * DEMI_PIXEL + 1e-9)
    r = r.copy()
    r["pix_i"] = np.where(dans | bord, i, -1)
    r["pix_j"] = np.where(dans | bord, j, -1)
    r.loc[bord, "precision"] = r.loc[bord, "precision"] + " ; pixel voisin (bord de grille)"
    return r


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    r, a = charger()
    communes = rapprocher_communes(r, a)
    loc = rattacher_pixels(placer_localites(r, a, communes), *grille())
    pop_tot = float(loc["POPULATION"].sum())

    anom = np.load(PROCESSED / "standardized_anomalies_senegal.npz", allow_pickle=True)
    dates = pd.to_datetime(anom["dates"])
    rang = {d: k for k, d in enumerate(dates)}
    ev = pd.read_csv(PROCESSED / "extreme_events_phases_senegal.csv", parse_dates=["date"])

    dans = loc[loc["pix_i"] >= 0]
    pop_pix = np.zeros(anom["anomalies"].shape[1:])
    men_pix = np.zeros_like(pop_pix)
    np.add.at(pop_pix, (dans["pix_i"], dans["pix_j"]), dans["POPULATION"])
    np.add.at(men_pix, (dans["pix_i"], dans["pix_j"]), dans["MENAGE"])
    # Population par pixel et par departement, pour le departement le plus touche.
    dep_pix = dans.groupby(["Departement", "pix_i", "pix_j"])["POPULATION"].sum()

    lignes, ecarts = [], 0
    for _, e in ev.iterrows():
        masque = anom["anomalies"][rang[e["date"]]] > SEUIL_SIGMA
        ecarts += int(masque.sum() != e["coverage_points"])
        pop = float(pop_pix[masque].sum())
        touches = dep_pix[[bool(masque[i, j]) for _, i, j in dep_pix.index]]
        par_dep = touches.groupby(level=0).sum().sort_values(ascending=False)
        lignes.append({
            "date": e["date"].date().isoformat(), "phase": e["phase"],
            "pixels_extremes": int(masque.sum()), "couverture_pct": e["coverage_percent"],
            "pluie_max_mm": e["max_precip"],
            "population_touchee_2023": int(round(pop)),
            "menages_touches_2023": int(round(float(men_pix[masque].sum()))),
            "part_population_nationale_pct": round(100 * pop / pop_tot, 2),
            "departements_touches": int((par_dep > 0).sum()),
            "departement_le_plus_touche": par_dep.index[0] if len(par_dep) else "",
            "population_departement_le_plus_touche": int(par_dep.iloc[0]) if len(par_dep) else 0,
        })
    t = pd.DataFrame(lignes)
    t.to_csv(SORTIE / "population_touchee_evenements.csv", index=False, encoding="utf-8")

    an = t.assign(annee=pd.to_datetime(t["date"]).dt.year).groupby("annee").agg(
        evenements=("date", "size"),
        personnes_evenements=("population_touchee_2023", "sum"),
        evenement_max=("population_touchee_2023", "max")).reset_index()
    an.to_csv(SORTIE / "population_touchee_par_annee.csv", index=False, encoding="utf-8")

    communes.drop(columns=["kd", "kc"]).to_csv(
        SORTIE / "correspondance_communes_rgph5_ansd.csv", index=False, encoding="utf-8")
    loc[["Region", "Departement", "COMMUNE", "LOCALITE", "MENAGE", "POPULATION", "LON",
         "LAT", "precision", "pix_i", "pix_j"]].to_csv(
        PROCESSED / "localites_rgph5_placees.csv", index=False, encoding="utf-8")

    prec = loc.groupby("precision")["POPULATION"].sum() / pop_tot
    modes = communes.groupby("mode").agg(communes=("COMMUNE", "size"),
                                         population=("POPULATION", "sum"))
    resume = {
        "sources": {"population": "ANSD, RGPH-5 2023, Repertoire des localites",
                    "coordonnees": "ANSD, coordonnees geographiques des localites (04/10/2026)",
                    "pluie": "CHIRPS 0,25 deg, anomalies du script 01"},
        "localites_rgph5_2023": int(len(loc)), "population_2023": int(pop_tot),
        "precision_du_placement_part_population": {k: round(float(v), 4) for k, v in prec.items()},
        "population_hors_grille": int(loc.loc[loc["pix_i"] < 0, "POPULATION"].sum()),
        "communes": {k: {"communes": int(v["communes"]),
                         "part_population": round(float(v["population"] / pop_tot), 4)}
                     for k, v in modes.iterrows()},
        "controle_pixels": {"evenements": int(len(t)), "ecarts_avec_coverage_points": ecarts},
        "lecture": "population 2023 des zones touchees par chaque evenement passe",
        "evenements_les_plus_peuples": t.nlargest(5, "population_touchee_2023")[
            ["date", "population_touchee_2023", "departement_le_plus_touche"]].to_dict("records"),
    }
    (SORTIE / "resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(json.dumps(resume, ensure_ascii=False, indent=2))


def grille():
    clim = np.load(PROCESSED / "climatology_senegal.npz", allow_pickle=True)
    return clim["lats"].astype(float), clim["lons"].astype(float)


if __name__ == "__main__":
    main()
