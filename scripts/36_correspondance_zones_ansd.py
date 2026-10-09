#!/usr/bin/env python3
"""Correspondance des codes de zone de l'ANSD (SDMX) et des codes de ClimatSen.

L'ANSD identifie ses zones par ses propres codes (liste CL_REF_AREA, lue par le script
35) : SN-KD (region de Kolda), SN-KD-VE (departement de Velingara), SN-KD-VE1-1 (une
commune). ClimatSen utilise les P-codes OCHA (SN07, SN0703) et, pour les communes, le
P-code du departement suivi du nom ANSD (SN0703_BONCONTO). Cette table relie les deux :
un tableau de l'ANSD se joint alors directement aux resultats de ClimatSen.

Rapprochement par nom normalise (sans accents, espaces ni ponctuation) :
  regions et departements : nom identique, puis alias verifies a la main ;
  communes : dans le departement correspondant, nom identique, puis nom approche
  (difflib >= 0,85), puis commune de ClimatSen dont le nom commence par celui de l'ANSD.
La colonne `methode` dit lequel. Une commune de ClimatSen a cheval sur deux departements
y figure deux fois (une fois par departement) : seule celle du departement ANSD est prise.

Entrees : data/raw/ansd/odp/CL_REF_AREA_communes.csv (script 35), resultats publies
          (indices de risque, communes reconstruites du script 34)
Sortie  : data/processed/correspondance_zones_ansd.csv
Usage   : py -3 scripts/36_correspondance_zones_ansd.py
"""
import difflib
import sys
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from donnees_ouvertes.sources import cle, table  # noqa: E402

ZONES_ANSD = RACINE / "data" / "raw" / "ansd" / "odp" / "CL_REF_AREA_communes.csv"
SORTIE = RACINE / "data" / "processed" / "correspondance_zones_ansd.csv"
SEUIL = 0.78

# Nom ANSD -> nom OCHA (normalises), quand l'orthographe differe.
ALIAS_DEPARTEMENTS = {"MALEMHODDAR": "MALEMHODAR", "NIORO": "NIORODURIP",
                      "MEDINAYOROFOULAH": "MEDINAYOROFOULA", "RANEROUFERLO": "RANEROU"}
# Communes verifiees a la main : (departement ANSD, nom ANSD) -> nom ClimatSen.
ALIAS_COMMUNES = {
    ("SN-DK-DD", "DAKARPLATEAU"): "PLATEAU",
    # Le fichier des coordonnees range Diaxay dans le departement de Rufisque.
    ("SN-DK-KM", "JAXAAYPARCELLES"): "DIAXAYPARCELLENIAKOURAP",
}
# Communes du RGPH-5 2023 issues du decoupage d'une commune plus ancienne : elles
# partagent le contour de la commune d'origine.
SCINDEES = {("SN-DK-KM", "KEURMASSARNORD"): "KEURMASSAR",
            ("SN-DK-KM", "KEURMASSARSUD"): "KEURMASSAR"}


def variantes(nom):
    """Cles d'un nom de ClimatSen : le nom entier et, pour « A (B) », A et B
    (le fichier des coordonnees donne souvent l'ancien et le nouveau nom)."""
    k = {cle(nom)}
    if "(" in nom:
        avant, _, apres = nom.partition("(")
        k |= {cle(avant), cle(apres)}
    return k - {""}


def rapprocher_commune(dep_ansd, nom, sous, toutes):
    """sous : communes de ClimatSen du departement correspondant ; toutes : le pays."""
    k = cle(nom)
    index = {v: code for code, n in zip(sous["code"], sous["nom"]) for v in variantes(n)}
    if (dep_ansd, k) in ALIAS_COMMUNES:
        cible = ALIAS_COMMUNES[(dep_ansd, k)]
        trouve = toutes[toutes["nom"].map(cle) == cible]
        if len(trouve) == 1:
            return trouve["code"].iloc[0], "alias"
    if (dep_ansd, k) in SCINDEES and SCINDEES[(dep_ansd, k)] in index:
        return index[SCINDEES[(dep_ansd, k)]], "commune scindee en 2023"
    if k in index:
        return index[k], "nom identique"
    proche = difflib.get_close_matches(k, list(index), n=1, cutoff=SEUIL)
    if proche:
        return index[proche[0]], "nom approche"
    debut = {index[c] for c in index if c.startswith(k) or k.startswith(c)}
    if len(debut) == 1:
        return debut.pop(), "debut du nom"
    # Meme nom, mais rangee dans un autre departement par la reconstruction des
    # contours (decoupage plus ancien du fichier des coordonnees).
    ailleurs = toutes[toutes["nom"].map(cle) == k]
    if len(ailleurs) == 1:
        return ailleurs["code"].iloc[0], "autre departement"
    return None, "non trouvee"


def main():
    z = pd.read_csv(ZONES_ANSD, dtype=str)
    dep = table("departements")
    com = table("communes")

    reg_o = dict(zip(dep["region"].map(cle), dep["code_region"]))
    dep_o = dict(zip(dep["nom"].map(cle), dep["code"]))
    dep_o.update({a: dep_o[o] for a, o in ALIAS_DEPARTEMENTS.items()})
    noms_o = dict(zip(dep["code"], dep["nom"]))
    noms_o.update(dict(zip(dep["code_region"], dep["region"])))

    lignes = []
    for r in z.itertuples():
        if r.niveau == "region":
            code = reg_o.get(cle(r.nom))
            methode = "nom identique" if code else "non trouvee"
        elif r.niveau == "departement":
            code = dep_o.get(cle(r.nom))
            methode = ("alias" if cle(r.nom) in ALIAS_DEPARTEMENTS else "nom identique") \
                if code else "non trouvee"
        else:
            continue
        lignes.append({"code_ansd": r.code, "nom_ansd": r.nom, "niveau": r.niveau,
                       "parent_ansd": r.parent, "code_climatsen": code,
                       "nom_climatsen": noms_o.get(code), "methode": methode})

    dep_ansd = {l["code_ansd"]: l["code_climatsen"] for l in lignes
                if l["niveau"] == "departement"}
    for r in z[z["niveau"] == "commune"].itertuples():
        pcode = dep_ansd.get(r.parent)
        sous = com[com["code_departement"] == pcode]
        code, methode = rapprocher_commune(r.parent, r.nom, sous, com) if pcode \
            else (None, "non trouvee")
        nom = com.loc[com["code"] == code, "nom"].iloc[0] if code else None
        lignes.append({"code_ansd": r.code, "nom_ansd": r.nom, "niveau": "commune",
                       "parent_ansd": r.parent, "code_climatsen": code,
                       "nom_climatsen": nom, "methode": methode})

    t = pd.DataFrame(lignes)
    t.to_csv(SORTIE, index=False, encoding="utf-8")

    print(t.groupby(["niveau", "methode"]).size().to_string())
    for niv in ("region", "departement", "commune"):
        s = t[t["niveau"] == niv]
        print(f"{niv}: {s['code_climatsen'].notna().sum()}/{len(s)} rapproches")
    doublons = t[t["code_climatsen"].notna()].duplicated("code_climatsen", keep=False)
    if doublons.any():
        print("Codes ClimatSen pris deux fois :")
        print(t[t["code_climatsen"].notna()][doublons].to_string(index=False))
    manq = t[t["code_climatsen"].isna()]
    if len(manq):
        print("Non rapproches :")
        print(manq[["code_ansd", "nom_ansd", "parent_ansd"]].to_string(index=False))
    print(f"-> {SORTIE.relative_to(RACINE)}")


if __name__ == "__main__":
    main()
