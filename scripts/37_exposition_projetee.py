#!/usr/bin/env python3
"""Exposition aux pluies extremes avec la population projetee par l'ANSD (2026, 2030).

Le script 33 compte les habitants RECENSES en 2023 dans les pixels de chaque evenement.
Ce script refait le meme compte avec la population PROJETEE par l'ANSD pour l'annee en
cours (2026) et pour 2030 : combien d'habitants vivent aujourd'hui, et vivront, la ou la
pluie a deja ete extreme.

Methode
  1. Projections de l'ANSD par commune (DF_PROJ_POP_2050_COM, lu par son API SDMX,
     script 35) : facteur de croissance de chaque commune = population de l'annee /
     population 2023 de la meme serie.
  2. Chaque commune du Repertoire des localites (RGPH-5) est rapprochee de sa commune
     ANSD (meme departement, nom identique puis approche). Chaque localite recoit le
     facteur de sa commune ; a defaut, celui de son departement (DF_PROJ_POP_2050_DEP).
  3. Population projetee par pixel, puis meme masque que le script 33 (anomalie > +2
     ecarts-types le jour de l'evenement).
Hypothese : la croissance est uniforme a l'interieur d'une commune (la projection de
l'ANSD s'arrete a la commune).

Entrees : data/raw/ansd/odp/ (script 35), data/processed/localites_rgph5_placees.csv
          (script 33), anomalies CHIRPS (script 01), correspondance du script 36
Sorties : outputs/exposition_evenements/population_touchee_projetee.csv
          outputs/exposition_evenements/population_projetee_zones.csv
          outputs/exposition_evenements/resume_projection.json
Usage   : py -3 scripts/37_exposition_projetee.py
"""
import difflib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from donnees_ouvertes.sources import cle  # noqa: E402

ODP = RACINE / "data" / "raw" / "ansd" / "odp"
PROCESSED = RACINE / "data" / "processed"
SORTIE = RACINE / "outputs" / "exposition_evenements"
ANNEES = (2026, 2030)
SEUIL_SIGMA = 2.0          # critere du script 01, comme le script 33
SEUIL_NOM = 0.85

# Departements du Repertoire (RGPH-5) dont le nom differe dans la liste de l'ANSD.
ALIAS_DEPARTEMENTS = {"KOUPENTOUM": "KOUMPENTOUM", "MALEMHODAR": "MALEMHODDAR"}


def series(fichier):
    """Projection SDMX -> tableau zone x annee."""
    p = pd.read_csv(ODP / fichier, sep=None, engine="python", dtype=str)
    p["OBS_VALUE"] = p["OBS_VALUE"].astype(float)
    return p.pivot_table(index="REF_AREA", columns="TIME_PERIOD", values="OBS_VALUE",
                         aggfunc="first")


def localites_projetees(annees=ANNEES):
    """Localites placees (script 33) avec leur population projetee par l'ANSD :
    une colonne POP_<annee> par annee demandee (2023 a 2030). Renvoie aussi la
    correspondance commune RGPH-5 -> commune ANSD et les series de projection.
    Reutilisee par le script 40 (saisons recentes)."""
    zones = pd.read_csv(ODP / "CL_REF_AREA_communes.csv", dtype=str)
    nom = dict(zip(zones["code"], zones["nom"]))
    com = series("DF_PROJ_POP_2050_COM.csv")
    dep = series("DF_PROJ_POP_2050_DEP.csv")
    facteur_com = {a: com[str(a)] / com["2023"] for a in annees}
    facteur_dep = {a: dep[str(a)] / dep["2023"] for a in annees}

    # Communes ANSD par departement (noms normalises).
    par_dep = {}
    for code in com.index:
        par_dep.setdefault(cle(nom[code[:8]]), {})[cle(nom[code])] = code
    dep_code = {cle(nom[c]): c for c in dep.index}

    loc = pd.read_csv(PROCESSED / "localites_rgph5_placees.csv")
    rgph = loc.groupby(["Departement", "COMMUNE"])["POPULATION"].sum().reset_index()
    lignes = []
    for r in rgph.itertuples():
        kd = cle(r.Departement)
        kd = ALIAS_DEPARTEMENTS.get(kd, kd)
        cands = par_dep.get(kd, {})
        kc = cle(r.COMMUNE)
        if kc in cands:
            code, mode = cands[kc], "nom identique"
        else:
            proche = difflib.get_close_matches(kc, list(cands), n=1, cutoff=SEUIL_NOM)
            code, mode = (cands[proche[0]], "nom approche") if proche else (None, "departement")
        lignes.append({"Departement": r.Departement, "COMMUNE": r.COMMUNE,
                       "code_ansd": code, "code_dep_ansd": dep_code.get(kd), "mode": mode,
                       "population_2023_repertoire": r.POPULATION,
                       "population_2023_projection": com.loc[code, "2023"] if code else np.nan})
    corr = pd.DataFrame(lignes)
    loc = loc.merge(corr[["Departement", "COMMUNE", "code_ansd", "code_dep_ansd", "mode"]],
                    on=["Departement", "COMMUNE"], how="left")
    for a in annees:
        f = loc["code_ansd"].map(facteur_com[a])
        f = f.fillna(loc["code_dep_ansd"].map(facteur_dep[a]))
        loc[f"POP_{a}"] = loc["POPULATION"] * f.fillna(1.0)
    return loc, corr, com, dep


def main():
    loc, corr, com, dep = localites_projetees(ANNEES)

    anom = np.load(PROCESSED / "standardized_anomalies_senegal.npz", allow_pickle=True)
    dates = pd.to_datetime(anom["dates"])
    rang = {d: k for k, d in enumerate(dates)}
    ev = pd.read_csv(PROCESSED / "extreme_events_phases_senegal.csv", parse_dates=["date"])
    dans = loc[loc["pix_i"] >= 0]
    # Charge une seule fois : chaque acces a anom["anomalies"] relit et
    # decompresse tout le tableau (56 Mo), 1 317 fois dans la boucle (13 min).
    anomalies = anom["anomalies"]
    forme = anomalies.shape[1:]
    pix = {}
    for c in ["POPULATION"] + [f"POP_{a}" for a in ANNEES]:
        pix[c] = np.zeros(forme)
        np.add.at(pix[c], (dans["pix_i"], dans["pix_j"]), dans[c])

    tot = {c: float(loc[c].sum()) for c in pix}
    sorties = []
    for e in ev.itertuples():
        masque = anomalies[rang[e.date]] > SEUIL_SIGMA
        ligne = {"date": e.date.date().isoformat(),
                 "population_touchee_2023": int(round(float(pix["POPULATION"][masque].sum())))}
        for a in ANNEES:
            v = float(pix[f"POP_{a}"][masque].sum())
            ligne[f"population_touchee_{a}"] = int(round(v))
        ligne["part_population_nationale_2026_pct"] = round(
            100 * ligne["population_touchee_2026"] / tot["POP_2026"], 2)
        sorties.append(ligne)
    t = pd.DataFrame(sorties)
    SORTIE.mkdir(parents=True, exist_ok=True)
    t.to_csv(SORTIE / "population_touchee_projetee.csv", index=False, encoding="utf-8")

    # Population projetee des zones de ClimatSen (correspondance du script 36).
    cz = pd.read_csv(PROCESSED / "correspondance_zones_ansd.csv", dtype=str)
    cz = cz[cz["niveau"].isin(["departement", "commune"])].dropna(subset=["code_climatsen"])
    proj = pd.concat([com, dep])
    zl = []
    for code_cs, g in cz.groupby("code_climatsen"):
        codes = [c for c in g["code_ansd"] if c in proj.index]
        if not codes:
            continue
        ligne = {"code": code_cs, "niveau": g["niveau"].iloc[0],
                 "code_ansd_sdmx": "+".join(sorted(codes))}
        for a in (2023,) + ANNEES:
            ligne[f"population_{a}"] = int(round(proj.loc[codes, str(a)].sum()))
        zl.append(ligne)
    pz = pd.DataFrame(zl)
    pz.to_csv(SORTIE / "population_projetee_zones.csv", index=False, encoding="utf-8")

    ecart = (corr["population_2023_projection"] / corr["population_2023_repertoire"] - 1).abs()
    resume = {
        "sources": {"projections": "ANSD, DF_PROJ_POP_2050_COM et _DEP, API SDMX (script 35)",
                    "localites": "ANSD, RGPH-5 2023, Repertoire des localites (script 33)"},
        "hypothese": "croissance uniforme a l'interieur de chaque commune",
        "population_nationale": {"2023_repertoire": int(tot["POPULATION"]),
                                 **{str(a): int(tot[f"POP_{a}"]) for a in ANNEES}},
        "rapprochement_communes": corr.groupby("mode")["population_2023_repertoire"].agg(
            ["size", "sum"]).rename(columns={"size": "communes", "sum": "population"})
            .astype(int).to_dict("index"),
        "ecart_median_projection_2023_vs_repertoire_pct": round(100 * float(ecart.median()), 2),
        "population_touchee": {str(a): {"mediane": int(t[f"population_touchee_{a}"].median()),
                                        "maximum": int(t[f"population_touchee_{a}"].max())}
                               for a in (2023,) + ANNEES},
        "zones": {"communes": int((pz["niveau"] == "commune").sum()),
                  "departements": int((pz["niveau"] == "departement").sum())},
    }
    (SORTIE / "resume_projection.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resume, ensure_ascii=False, indent=2))
    non = corr[corr["mode"] == "departement"]
    if len(non):
        print("Communes sans projection propre (facteur du departement) :")
        print(non[["Departement", "COMMUNE", "population_2023_repertoire"]].to_string(index=False))


if __name__ == "__main__":
    main()
