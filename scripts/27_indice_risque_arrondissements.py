#!/usr/bin/env python3
"""Indice de risque pluies extremes par arrondissement (125 contours OCHA/HDX admin3).

Meme methode que la version departementale (script 26), dont on reutilise les fonctions :
  A = rangs centiles de jours_anomalie_2sigma et jours_50mm (CHIRPS, mai-octobre) ;
  E = rangs centiles de la population RGPH-5 2023 et de la densite (population / area_sqkm) ;
  V = rangs centiles de la pauvrete EHCVM de la region et de la croissance 2013 -> 2023
      (PROVISOIRE, en attendant les donnees d'habitat RGPH-5) ;
  indice = (A x E x V)^(1/3), rangs centiles calcules sur les 125 arrondissements.

Correspondance RGPH-5 -> arrondissement HDX (une ligne par commune 2023), regles dans l'ordre :
  1. nom_arrondissement : COM_ARRT_VILLE est un arrondissement HDX du meme departement,
     apres normalisation cle() et la table ALIAS_ARRONDISSEMENTS (orthographes) ;
  2. departement_un_seul_arrondissement : Guediawaye, Saint-Louis, Ranerou ;
  3. commune_gadm_dans_contour : communes des "villes" (Dakar, Pikine, Rufisque, Thies...) ;
     point interieur du polygone de la commune GADM 4.1 niveau 4, situe dans un contour
     HDX admin3 du meme departement ;
  4. chef_lieu_hdx : communes urbaines hors arrondissement qui sont chefs-lieux ;
     point OCHA sen_admincapitals, situe dans un contour HDX du meme departement ;
  5. point_osm : autres communes urbaines ; point OpenStreetMap (Nominatim, ODbL) enregistre
     une fois dans data/raw/osm/communes_urbaines_osm.csv (option --osm), situe dans un
     contour HDX du meme departement.
  Les points des regles 4 et 5 sont croises quand les deux existent (desaccords listes).
Le recensement 2013 est rattache aux arrondissements 2023 : localite de meme nom (unique
dans le departement les deux annees), sinon commune de meme nom, sinon arrondissement
majoritaire des localites deja rattachees de la meme commune 2013. Keur Massar est
reconstitue comme dans le script 26 (REAFFECTATION_2013).

Entrees : data/raw/ansd, data/raw/hdx (admin3, admincapitals), data/raw/osm,
          data/geographic/senegal_boundaries/gadm41_SEN_4.shp, data/processed (CHIRPS)
Sorties : data/processed/correspondance_communes_arrondissements.csv (2023)
          data/processed/correspondance_2013_arrondissements.csv
          data/processed/correspondance_cas_non_resolus.csv
          outputs/vulnerabilite/indice_risque_arrondissements.csv, resume_arrondissements.json

Usage : py -3 scripts/27_indice_risque_arrondissements.py [--osm]
        (--osm : interroge Nominatim pour les communes urbaines sans point, 1 requete/s)
"""
import argparse
import importlib.util
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "indice26", RACINE / "scripts" / "26_indice_risque_departements.py")
s26 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(s26)
cle, centile, combine = s26.cle, s26.centile, s26.combine

ANSD, HDX, PROCESSED, SORTIE = s26.ANSD, s26.HDX, s26.PROCESSED, s26.SORTIE
GADM4 = RACINE / "data" / "geographic" / "senegal_boundaries" / "gadm41_SEN_4.shp"
OSM = RACINE / "data" / "raw" / "osm" / "communes_urbaines_osm.csv"

# (departement, COM_ARRT_VILLE RGPH-5) -> adm3_name HDX, apres cle(). Variantes
# d'orthographe d'un meme arrondissement, verifiees une a une (meme departement,
# communes coherentes avec GADM 4.1 niveau 3).
ALIAS_ARRONDISSEMENTS = {
    ("BAKEL", "BELE"): "BELLE",
    ("BAKEL", "MOUDERY"): "MOUDERI",
    ("BIGNONA", "TENGHORI"): "TANGHORI",
    ("BOUNKILING", "BOGHAL"): "BOGAL",
    ("DAGANA", "NDIAYE"): "NDIAYENGENT",
    ("FATICK", "FIMELA"): "FIMLA",
    ("FATICK", "NDIOP"): "NDIOB",
    ("FATICK", "TATTAGUINE"): "TATAGUINE",
    ("FOUNDIOUGNE", "TOUBACOUTA"): "TOUBAKOUTA",
    ("GOUDIRY", "BOYNGUELBAMBA"): "BOUINGUELBAMBA",
    ("GOUDIRY", "DIANKEMAKHA"): "DIANKEMAKAN",
    ("GOUDIRY", "KOULOR"): "KOULAR",
    ("KAFFRINE", "GNIBY"): "GNIBI",
    ("KANEL", "WOUROSIDY"): "OUROSIDI",
    ("KEBEMER", "DAROUMOUHTY"): "DAROUMOUSTY",
    ("KEBEMER", "SAGATTA"): "SAGATAGETH",
    ("KEDOUGOU", "FONGOLIMBI"): "FONGOLEMBI",
    ("KOUMPENTOUM", "BAMBATHIALENE"): "BAMBATIALENE",
    ("KOUMPENTOUM", "KOUTHIABAWOLOF"): "KOUTIABAWOLOF",
    ("KOUNGHEUL", "MISSIRAHWADENE"): "MISSIRAWADENE",
    ("LINGUERE", "SAGATTADJOLOF"): "SAGATADIOLOF",
    ("LOUGA", "COKI"): "KOKI",
    ("NIORODURIP", "PAOSKOTO"): "PAOSCOTO",
    ("NIORODURIP", "WACKNGOUNA"): "WAKNGOUNA",
    ("OUSSOUYE", "LOUDIAOUOLOF"): "LOUDIAWOLOF",
    ("PODOR", "GAMADJISARE"): "GAMADJISARRE",
    ("PODOR", "THILEBOUBACAR"): "THILLEBOUBAKAR",
    ("SALEMATA", "DAKATELY"): "DAKATELI",
    ("TAMBACOUNDA", "MAKACOLIBANTANG"): "MAKACOUTIBANTANG",
    ("TAMBACOUNDA", "MISSIRAH"): "MISSIRA",
    ("THIES", "NOTTO"): "NOTO",
}

# Commune RGPH-5 2023 -> NAME_4 GADM (apres cle()), pour les communes des "villes".
ALIAS_COMMUNES_GADM = {
    "DAKARPLATEAU": "PLATEAU",
    "GUEULETAPEEFASSCOLOBANE": "GUEULETAPEECOLOBANEFASS",
    "DALIFORT": "DALIFORD",
    "THIAROYESURMER": "THIAROYEMER",
    "TIVAOUANEDIACKSAO": "DIACKSAO",
    "PIKINENORD": "PIKINESUD",  # renommee entre 2013 et 2023 : voir verification en sortie
    "RUFISQUENORD": "RUFISQUECENTRENORD",
}

# Commune 2013 (departement 2023, commune 2013 sans "COM.") -> commune 2023, apres cle().
ALIAS_COMMUNES_2013 = {
    ("KEURMASSAR", "JAXAAYPARCELLENIAKOULRAP"): "JAXAAYPARCELLES",
    ("KANEL", "HAMADYOUNARE"): "HAMADYHOUNARE",
    ("KANEL", "WAOUNDE"): "OUAOUNDE",
}

# Nom du point sen_admincapitals (apres cle()) -> commune RGPH-5 quand ils different.
ALIAS_CHEFS_LIEUX = {
    "MALEMEHODDAR": "MALEMHODDAR",
    "NIORODURIP": "NIORO",
    "GUINGUENEO": "GUINGUINEO",
}

# Requete Nominatim quand le nom RGPH-5 ne suffit pas.
REQUETE_OSM = {
    "JOALFADHIOUTH": "Joal-Fadiouth",
    "THIONCKESSYL": "Thionck Essyl",
    "RICHARDTOLL": "Richard-Toll",
    "MEKHE": "Meckhe",  # nom de la localite dans OSM ; "Mekhe" renvoie un lac homonyme
}

AGENT_OSM = "CLIMAT-SEN-hackathon-ANSD-2026/1.0"
# Types Nominatim acceptes : une agglomeration, jamais une region, un departement ou un lac.
TYPES_OSM = {"city", "town", "village", "municipality", "suburb"}


def arrondissements_hdx():
    a = gpd.read_file(HDX / "sen_admin3.geojson")
    # SN010404 (Rufisque) est nomme "N/A" dans HDX ; il contient Bargny et Sendou. On
    # garde le P-code, avec un nom qui ne soit pas lu comme valeur manquante.
    a.loc[a["adm3_name"] == "N/A", "adm3_name"] = "Sans nom HDX (N/A)"
    a["kd"] = a["adm2_name"].map(cle)
    a["ka"] = a["adm3_name"].map(cle)
    return a


def repertoire():
    d = pd.read_csv(ANSD / "rgph_repertoire_localites_1988-2023.csv", encoding="utf-8-sig")
    d.columns = [c.strip() for c in d.columns]
    d = d.rename(columns={d.columns[-1]: "annee"})
    d["kd"] = d["Departement"].map(cle).replace(s26.ALIAS_DEPARTEMENTS)
    d["ka"] = d["COM_ARRT_VILLE"].map(cle)
    d["kc"] = d["COMMUNE"].map(cle)
    d["kl"] = d["QUARTIER_VILLAGE_HAMEAU"].map(cle)
    return d


def communes_2023(d):
    return (d[d["annee"] == 2023]
            .groupby(["Region", "Departement", "COM_ARRT_VILLE", "COMMUNE", "kd", "ka", "kc"])
            .agg(population_2023=("POPULATION", "sum"), menages_2023=("MENAGE", "sum"))
            .reset_index())




TOLERANCE_KM = 5.0
CRS_METRIQUE = "EPSG:32628"  # UTM 28N, pour les distances


def localiser(pt, a3, kd):
    """(pcode, distance_km) : contour HDX du departement kd contenant le point ; sinon
    l'arrondissement le plus proche de ce departement s'il est a moins de TOLERANCE_KM
    (ecart de trace entre sources) ; sinon (None, distance)."""
    sous = a3[a3["kd"] == kd]
    dedans = sous[sous.contains(pt)]
    if len(dedans):
        return dedans["adm3_pcode"].iloc[0], 0.0
    ptm = gpd.GeoSeries([pt], crs=a3.crs).to_crs(CRS_METRIQUE).iloc[0]
    dist = sous.to_crs(CRS_METRIQUE).distance(ptm) / 1000
    j = dist.idxmin()
    if dist[j] <= TOLERANCE_KM:
        return sous.loc[j, "adm3_pcode"], float(dist[j])
    return None, float(dist[j])


def communes_urbaines(u, a3):
    """Communes 2023 hors arrondissement HDX (communes urbaines et communes des villes)."""
    noms = set(zip(a3["kd"], a3["ka"]))
    k = [(kd, ALIAS_ARRONDISSEMENTS.get((kd, ka), ka)) for kd, ka in zip(u["kd"], u["ka"])]
    return u[[x not in noms for x in k]]


def telecharger_osm(u, a3):
    """Point Nominatim de chaque commune urbaine hors arrondissement (sans les villes)."""
    cand = communes_urbaines(u, a3)
    cand = cand[~cand["COM_ARRT_VILLE"].str.upper().str.startswith("VILLE DE")]
    lignes = []
    for _, r in cand.iterrows():
        requete = REQUETE_OSM.get(r["kc"], r["COMMUNE"].title())
        url = ("https://nominatim.openstreetmap.org/search?"
               + urllib.parse.urlencode({"q": f"{requete}, Senegal", "format": "json",
                                         "limit": 5, "countrycodes": "sn"}))
        req = urllib.request.Request(url, headers={"User-Agent": AGENT_OSM})
        with urllib.request.urlopen(req, timeout=30) as rep:
            res = json.loads(rep.read().decode("utf-8"))
        time.sleep(1.1)
        # Premier resultat de type agglomeration localisable dans le departement.
        choix, dist, ecartes = None, np.nan, []
        for x in res:
            pt = Point(float(x["lon"]), float(x["lat"]))
            if x.get("addresstype") not in TYPES_OSM:
                ecartes.append(str(x.get("addresstype")))
                continue
            pcode, km = localiser(pt, a3, r["kd"])
            if pcode is None:
                ecartes.append(f"{x.get('addresstype')} a {km:.1f} km du departement")
                continue
            choix, dist = x, km
            break
        lignes.append({
            "departement": r["Departement"], "commune": r["COMMUNE"], "kd": r["kd"],
            "kc": r["kc"], "requete": requete, "n_resultats": len(res),
            "lat": float(choix["lat"]) if choix else np.nan,
            "lon": float(choix["lon"]) if choix else np.nan,
            "osm_type": choix["osm_type"] if choix else "",
            "osm_id": choix["osm_id"] if choix else "",
            "addresstype": choix.get("addresstype") if choix else "",
            "display_name": choix["display_name"] if choix else "",
            "distance_contour_km": round(dist, 2),
            "resultats_ecartes": " ; ".join(ecartes),
            "date_requete": date.today().isoformat(),
            "source": "OpenStreetMap contributors, Nominatim, ODbL 1.0",
        })
        print(f"  {r['COMMUNE']:28s} -> {lignes[-1]['display_name'][:70]}")
    OSM.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lignes).to_csv(OSM, index=False, encoding="utf-8")
    print(f"{len(lignes)} communes -> {OSM}")


def correspondance_2023(u, a3):
    noms = {(kd, ka): p for kd, ka, p in zip(a3["kd"], a3["ka"], a3["adm3_pcode"])}
    par_dep = a3.groupby("kd")["adm3_pcode"].agg(list)
    un_seul = {kd: v[0] for kd, v in par_dep.items() if len(v) == 1}

    g4 = gpd.read_file(GADM4)
    gadm = {(cle(a), cle(b)): geom.representative_point()
            for a, b, geom in zip(g4["NAME_2"], g4["NAME_4"], g4.geometry)}

    chefs = {}
    for _, c in gpd.read_file(HDX / "sen_admincapitals.geojson").iterrows():
        kd = s26.ALIAS_DEPARTEMENTS.get(cle(c["adm2_name"]), cle(c["adm2_name"]))
        kc = cle(c["name"])
        chefs[(kd, ALIAS_CHEFS_LIEUX.get(kc, kc))] = c.geometry

    osm = {}
    if OSM.exists():
        o = pd.read_csv(OSM, encoding="utf-8").dropna(subset=["lat", "lon"])
        osm = {(kd, kc): Point(lon, lat)
               for kd, kc, lon, lat in zip(o["kd"], o["kc"], o["lon"], o["lat"])}

    def point(source, pt, kd):
        pcode, km = localiser(pt, a3, kd)
        detail = f"{source} ({pt.x:.4f}, {pt.y:.4f})"
        if pcode and km > 0:
            detail += f", hors contour : arrondissement le plus proche a {km:.1f} km"
        return pcode, detail

    res = []
    for _, r in u.iterrows():
        kd, ka, kc = r["kd"], r["ka"], r["kc"]
        ka_hdx = ALIAS_ARRONDISSEMENTS.get((kd, ka), ka)
        kg = ALIAS_COMMUNES_GADM.get(kc, kc)
        pc_chef = point("sen_admincapitals", chefs[(kd, kc)], kd) if (kd, kc) in chefs else (None, "")
        pc_osm = point("OSM", osm[(kd, kc)], kd) if (kd, kc) in osm else (None, "")
        if (kd, ka_hdx) in noms:
            p, methode = noms[(kd, ka_hdx)], "nom_arrondissement"
            detail = f"alias {ka} -> {ka_hdx}" if ka_hdx != ka else "nom identique"
        elif kd in un_seul:
            p, methode, detail = un_seul[kd], "departement_un_seul_arrondissement", ""
        elif (kd, kg) in gadm:
            p, detail = point(f"GADM 4.1 commune {kg}", gadm[(kd, kg)], kd)
            methode = "commune_gadm_dans_contour"
        elif pc_chef[0]:
            (p, detail), methode = pc_chef, "chef_lieu_hdx"
        elif pc_osm[0]:
            (p, detail), methode = pc_osm, "point_osm"
        else:
            p, methode, detail = None, "non_resolu", "aucun point ni nom d'arrondissement"
        controle = ""
        if pc_chef[0] and pc_osm[0]:
            controle = ("accord" if pc_chef[0] == pc_osm[0]
                        else f"DESACCORD chef-lieu {pc_chef[0]} / OSM {pc_osm[0]}")
        res.append({"adm3_pcode": p, "methode": methode if p else "non_resolu",
                    "detail": detail, "controle_chef_lieu_osm": controle})
    out = pd.concat([u.reset_index(drop=True), pd.DataFrame(res)], axis=1)
    return out.merge(a3[["adm3_pcode", "adm3_name", "adm2_pcode", "adm2_name"]],
                     on="adm3_pcode", how="left")


def correspondance_2013(d, c23, a3):
    """Rattache chaque localite du recensement 2013 a un arrondissement 2023."""
    x = d[d["annee"] == 2013].copy()
    paires = pd.Series(list(zip(x["kd"], x["kc"])), index=x.index)
    cible = paires.map(s26.REAFFECTATION_2013)
    x.loc[cible.notna(), "kd"] = cible[cible.notna()]
    x["kc13"] = x["COMMUNE"].str.replace(r"^\s*COM\s*\.\s*", "", regex=True).map(cle)
    x["kc13"] = [ALIAS_COMMUNES_2013.get((kd, kc), kc) for kd, kc in zip(x["kd"], x["kc13"])]
    x["adm3_pcode"], x["methode"] = None, "non_resolu"

    def appliquer(cles, table, nom):
        m = pd.Series(list(cles), index=x.index).map(table)
        sel = x["adm3_pcode"].isna() & m.notna()
        x.loc[sel, "adm3_pcode"] = m[sel]
        x.loc[sel, "methode"] = nom

    # 1. Localite de meme nom, unique dans son departement en 2013 comme en 2023.
    l23 = d[d["annee"] == 2023].merge(c23[["kd", "ka", "kc", "adm3_pcode"]],
                                      on=["kd", "ka", "kc"], how="left")
    l23 = l23[~l23.duplicated(["kd", "kl"], keep=False)]
    loc23 = l23.set_index(["kd", "kl"])["adm3_pcode"].dropna()
    unique13 = ~x.duplicated(["kd", "kl"], keep=False)
    appliquer([k if u else None for k, u in zip(zip(x["kd"], x["kl"]), unique13)],
              loc23, "localite")
    # 2. Commune de meme nom en 2023, contenue dans un seul arrondissement.
    com23 = c23.dropna(subset=["adm3_pcode"]).groupby(["kd", "kc"])["adm3_pcode"]
    com23 = com23.agg(lambda s: s.iloc[0] if s.nunique() == 1 else None).dropna()
    appliquer(zip(x["kd"], x["kc13"]), com23, "commune")
    # 3. Arrondissement majoritaire (population 2013) des localites deja rattachees de la
    #    meme commune 2013.
    maj = (x.dropna(subset=["adm3_pcode"])
           .groupby(["kd", "kc13", "adm3_pcode"])["POPULATION"].sum().reset_index()
           .sort_values("POPULATION").drop_duplicates(["kd", "kc13"], keep="last")
           .set_index(["kd", "kc13"])["adm3_pcode"])
    appliquer(zip(x["kd"], x["kc13"]), maj, "majorite_commune_2013")
    # 4. Nom d'arrondissement 2013 (memes alias qu'en 2023).
    noms = {(kd, ka): p for kd, ka, p in zip(a3["kd"], a3["ka"], a3["adm3_pcode"])}
    appliquer([(kd, ALIAS_ARRONDISSEMENTS.get((kd, ka), ka)) for kd, ka in zip(x["kd"], x["ka"])],
              noms, "nom_arrondissement")
    return x


def table_arrondissements(a3, c23, x13, px):
    t = a3[["adm3_pcode", "adm3_name", "adm2_pcode", "adm2_name", "adm1_name",
            "area_sqkm", "geometry"]].copy()
    t = t.rename(columns={"adm3_pcode": "pcode", "adm3_name": "arrondissement",
                          "adm2_name": "departement", "adm1_name": "region",
                          "area_sqkm": "superficie_km2", "geometry": "geometrie"})
    g23 = c23.groupby("adm3_pcode").agg(population_2023=("population_2023", "sum"),
                                        menages_2023=("menages_2023", "sum"),
                                        n_communes_2023=("COMMUNE", "size"))
    g13 = x13.groupby("adm3_pcode")["POPULATION"].sum().rename("population_2013")
    t = t.join(g23, on="pcode").join(g13, on="pcode")
    t["taux_pauvrete_region_pct"] = t["region"].map(cle).map(s26.pauvrete_region())
    t = t.merge(s26.alea_par_departement(t, px), on="pcode")
    t["croissance_2013_2023_pct"] = (t["population_2023"] / t["population_2013"] - 1) * 100
    t["densite_2023_hab_km2"] = t["population_2023"] / t["superficie_km2"]
    t["pauvres_estimes_2023"] = t["population_2023"] * t["taux_pauvrete_region_pct"] / 100
    return t


def par_methode(df, pop):
    return {m: {"lignes": int(len(g)), "population": int(g[pop].sum()),
                "part_pct": round(100 * g[pop].sum() / df[pop].sum(), 3)}
            for m, g in df.groupby("methode")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", action="store_true",
                    help="interroger Nominatim et enregistrer data/raw/osm/")
    args = ap.parse_args()

    a3 = arrondissements_hdx()
    d = repertoire()
    u = communes_2023(d)
    if args.osm:
        telecharger_osm(u, a3)
    c23 = correspondance_2023(u, a3)
    x13 = correspondance_2013(d, c23, a3)

    # Un rattachement ne doit jamais changer de departement.
    kd_pcode = a3.set_index("adm3_pcode")["kd"]
    for nom, tab in (("2023", c23), ("2013", x13)):
        dep = tab["adm3_pcode"].map(kd_pcode)
        if (dep.notna() & (dep != tab["kd"])).any():
            raise SystemExit(f"{nom} : rattachement hors du departement RGPH-5")

    tot23, tot13 = c23["population_2023"].sum(), x13["POPULATION"].sum()
    ok23 = c23.loc[c23["adm3_pcode"].notna(), "population_2023"].sum()
    ok13 = x13.loc[x13["adm3_pcode"].notna(), "POPULATION"].sum()

    px = s26.alea_par_pixel()
    t = table_arrondissements(a3, c23, x13, px)

    # Controle : les sommes par departement retombent sur la version departementale.
    dep26 = pd.read_csv(SORTIE / "indice_risque_departements.csv", encoding="utf-8")
    somme = t.groupby("adm2_pcode")[["population_2013", "population_2023"]].sum()
    ctrl = dep26.set_index("pcode")[["departement", "population_2013", "population_2023"]].join(
        somme, rsuffix="_arr")
    ctrl["ecart_2013"] = ctrl["population_2013_arr"] - ctrl["population_2013"]
    ctrl["ecart_2023"] = ctrl["population_2023_arr"] - ctrl["population_2023"]

    # Indice : meme methode que le script 26 ; rangs centiles sur les arrondissements
    # peuples en 2013 et 2023 (sinon ni densite ni croissance).
    ok = (t["population_2023"] > 0) & (t["population_2013"] > 0)
    s = t[ok].copy()
    s["A_alea"] = combine(s["jours_anomalie_2sigma_an"], s["jours_50mm_an"])
    s["E_exposition"] = combine(s["population_2023"], s["densite_2023_hab_km2"])
    s["V_vulnerabilite"] = combine(s["taux_pauvrete_region_pct"], s["croissance_2013_2023_pct"])
    s["indice_risque"] = (s["A_alea"] * s["E_exposition"] * s["V_vulnerabilite"]) ** (1 / 3)
    s["indice_moyenne_simple"] = s[["A_alea", "E_exposition", "V_vulnerabilite"]].mean(axis=1)
    s["rang"] = s["indice_risque"].rank(ascending=False, method="min")
    t = t.drop(columns="geometrie").merge(
        s[["pcode", "A_alea", "E_exposition", "V_vulnerabilite", "indice_risque",
           "indice_moyenne_simple", "rang"]], on="pcode", how="left")
    t["rang_dans_departement"] = t.groupby("adm2_pcode")["indice_risque"].rank(
        ascending=False, method="min")
    t = t.merge(dep26[["pcode", "indice_risque", "rang"]].rename(columns={
        "pcode": "adm2_pcode", "indice_risque": "indice_departement",
        "rang": "rang_departement"}), on="adm2_pcode", how="left")

    colonnes = [
        "rang", "pcode", "arrondissement", "departement", "region", "adm2_pcode",
        "n_communes_2023", "population_2013", "population_2023", "croissance_2013_2023_pct",
        "menages_2023", "superficie_km2", "densite_2023_hab_km2", "taux_pauvrete_region_pct",
        "pauvres_estimes_2023", "n_pixels", "methode_alea",
        "jours_anomalie_2sigma_an", "jours_50mm_an",
        "A_alea", "E_exposition", "V_vulnerabilite", "indice_risque", "indice_moyenne_simple",
        "rang_dans_departement", "indice_departement", "rang_departement",
    ]
    t = t.sort_values(["rang", "pcode"])[colonnes]

    PROCESSED.mkdir(parents=True, exist_ok=True)
    SORTIE.mkdir(parents=True, exist_ok=True)
    c23[["Region", "Departement", "COM_ARRT_VILLE", "COMMUNE", "population_2023",
         "menages_2023", "adm3_pcode", "adm3_name", "adm2_pcode", "adm2_name", "methode",
         "detail", "controle_chef_lieu_osm"]].to_csv(
        PROCESSED / "correspondance_communes_arrondissements.csv", index=False, encoding="utf-8")
    c13 = (x13.groupby(["Region", "Departement", "kd", "COM_ARRT_VILLE", "COMMUNE",
                        "adm3_pcode", "methode"], dropna=False)
           .agg(localites=("POPULATION", "size"), population_2013=("POPULATION", "sum"))
           .reset_index().rename(columns={"kd": "departement_2023"}))
    c13.to_csv(PROCESSED / "correspondance_2013_arrondissements.csv", index=False,
               encoding="utf-8")
    non23 = c23[c23["adm3_pcode"].isna()].assign(
        annee=2023, population=lambda f: f["population_2023"])
    non13 = c13[c13["adm3_pcode"].isna()].assign(
        annee=2013, population=lambda f: f["population_2013"], detail="")
    approx = c23[c23["detail"].str.contains("hors contour", na=False)].assign(
        annee=2023, population=lambda f: f["population_2023"],
        methode=lambda f: "approche : " + f["methode"])
    cas = pd.concat([non23, non13, approx], ignore_index=True)[[
        "annee", "Region", "Departement", "COM_ARRT_VILLE", "COMMUNE", "population",
        "methode", "detail"]]
    cas.to_csv(PROCESSED / "correspondance_cas_non_resolus.csv", index=False, encoding="utf-8")
    t.round(4).to_csv(SORTIE / "indice_risque_arrondissements.csv", index=False,
                      encoding="utf-8")

    resume = {
        "echelle": "125 arrondissements OCHA COD-AB admin3 (v02, 2024)",
        "arrondissements": int(len(t)),
        "arrondissements_indice_calcule": int(t["indice_risque"].notna().sum()),
        "arrondissements_sans_indice": t.loc[t["indice_risque"].isna(), [
            "pcode", "arrondissement", "departement", "population_2013", "population_2023"]
        ].to_dict("records"),
        "couverture_population": {
            "2023": {"rattachee": int(ok23), "totale": int(tot23),
                     "part_pct": round(100 * ok23 / tot23, 4)},
            "2013": {"rattachee": int(ok13), "totale": int(tot13),
                     "part_pct": round(100 * ok13 / tot13, 4)},
        },
        "methodes_2023": par_methode(c23, "population_2023"),
        "methodes_2013": par_methode(x13, "POPULATION"),
        "controle_chef_lieu_osm": c23["controle_chef_lieu_osm"].replace("", np.nan)
                                  .dropna().value_counts().to_dict(),
        "cas_approches_hors_contour": approx[["COMMUNE", "detail"]].to_dict("records"),
        "controle_sommes_departements": {
            "ecart_max_abs_2013": float(ctrl["ecart_2013"].abs().max()),
            "ecart_max_abs_2023": float(ctrl["ecart_2023"].abs().max()),
            "departements_en_ecart": ctrl[(ctrl["ecart_2013"] != 0) | (ctrl["ecart_2023"] != 0)]
                                     ["departement"].tolist(),
        },
        "arrondissements_pixel_le_plus_proche": t.loc[
            t["methode_alea"] == "pixel terrestre le plus proche",
            ["arrondissement", "departement", "superficie_km2"]].round(1).to_dict("records"),
        "periode_alea": px["periode"], "mois": list(s26.MOIS_SAISON),
        "normalisation": "rang centile sur les arrondissements peuples ; composante a deux "
                         "indicateurs = moyenne de leurs rangs centiles, remise en rang centile",
        "indice": "(A x E x V)^(1/3)",
        "composantes": {
            "alea": ["jours_anomalie_2sigma_an", "jours_50mm_an"],
            "exposition": ["population_2023", "densite_2023_hab_km2"],
            "vulnerabilite": ["taux_pauvrete_region_pct", "croissance_2013_2023_pct"],
        },
        "vulnerabilite_statut": "provisoire en attendant les donnees d'habitat RGPH-5 ; la "
                                "pauvrete est regionale (EHCVM), identique pour tous les "
                                "arrondissements d'une region",
        "sources": {
            "alea": "CHIRPS 0,25 deg via data/processed (scripts 01)",
            "population": "ANSD, RGPH 2013 et RGPH-5 2023, Repertoire des localites",
            "pauvrete": "ANSD, EHCVM 2021-2022, Tableau III-2 (region)",
            "contours_superficies_chefs_lieux": "OCHA COD-AB Senegal v02 (2024), CC BY-IGO",
            "communes_des_villes": "GADM 4.1 niveau 4 (data/geographic)",
            "communes_urbaines_sans_chef_lieu": "OpenStreetMap contributors (Nominatim), "
                                                "ODbL 1.0, data/raw/osm/communes_urbaines_osm.csv",
        },
        "top10": t.head(10)[["rang", "arrondissement", "departement", "indice_risque"]]
                 .round(3).to_dict("records"),
    }
    (SORTIE / "resume_arrondissements.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"Couverture 2023 : {ok23:,.0f} / {tot23:,.0f} ({100 * ok23 / tot23:.4f} %)")
    print(f"Couverture 2013 : {ok13:,.0f} / {tot13:,.0f} ({100 * ok13 / tot13:.4f} %)")
    c = resume["controle_sommes_departements"]
    print(f"Ecart max aux sommes departementales : 2013 {c['ecart_max_abs_2013']:.0f}, "
          f"2023 {c['ecart_max_abs_2023']:.0f}")
    print(f"{len(t)} arrondissements -> {SORTIE / 'indice_risque_arrondissements.csv'}")


if __name__ == "__main__":
    main()
