#!/usr/bin/env python3
"""Alea d'inondation urbaine : part du bati situe en terrain bas.

Applique a la lettre outputs/vulnerabilite/alea_urbain/PROTOCOLE.md (commit 8a6800d,
fixe avant tout telechargement et tout calcul). Aucun parametre de ce script ne doit
etre change pour ameliorer un resultat : toute modification passe par le protocole.

Donnees (telechargees si absentes, non versionnees) :
  data/raw/copernicus_dem/  Copernicus DEM GLO-30, tuiles de 1 deg (bucket public AWS)
  data/raw/ghsl/            GHSL GHS-BUILT-S E2020 R2023A, 100 m, Mollweide, tuiles R8_C17, R7_C17
Definitions (protocole, section 3) :
  grille de travail = grille GHSL 100 m ; altitude ramenee par moyenne ;
  terrain bas = altitude <= moyenne d'une fenetre de 21 x 21 cellules - 1 m (TPI <= -1 m) ;
  U = surface batie en terrain bas / surface batie totale du departement ;
  U_abs = surface batie en terrain bas (km2) ; cellule rattachee par son centre.
Tests (protocole, section 4), memes AUC et bootstrap que le script 29 :
  T1 AUC de U, critere : borne basse de l'IC 95 % > 0,5 ;
  T2 logit touche ~ rang(population) + rang(U), rapport de vraisemblance sur U,
     critere : p < 0,05 et coefficient de U positif ;
  T3 AUC de U_abs ; T4 AUC de (rang(U) x E)^(1/2), E = exposition du script 26.

Sorties : outputs/vulnerabilite/alea_urbain/
Usage   : py -3 scripts/32_alea_urbain.py
"""
import importlib.util
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import requests
import statsmodels.api as sm
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from scipy.ndimage import uniform_filter
from scipy.stats import chi2
from shapely.geometry import shape
from shapely.ops import transform as transformer_geom

RACINE = Path(__file__).resolve().parent.parent
DEM_DIR = RACINE / "data" / "raw" / "copernicus_dem"
GHSL_DIR = RACINE / "data" / "raw" / "ghsl"
HDX = RACINE / "data" / "raw" / "hdx"
VULN = RACINE / "outputs" / "vulnerabilite"
SORTIE = VULN / "alea_urbain"
INVENTAIRE = RACINE / "data" / "raw" / "inondations" / "zones_touchees_2005_2009_2012_2020.csv"

# Protocole, section 3 (figes).
FENETRE = 21
SEUIL_M = -1.0
# Protocole, section 6 (sensibilite, pour information).
SENSIBILITE = [(11, -1.0), (41, -1.0), (21, -0.5), (21, -2.0)]

# Senegal, avec une marge pour que la fenetre du TPI ne soit pas tronquee au bord.
BBOX = (-17.75, 12.15, -11.15, 16.85)
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif")
# R8_C17 couvre le Senegal jusqu'a environ 16,3 deg N ; R7_C17 couvre l'extreme nord (Podor).
GHSL_TUILES = ("GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0_R8_C17",
               "GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100_V1_0_R7_C17")
GHSL_URL_MODELE = ("https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
                   "GHS_BUILT_S_GLOBE_R2023A/GHS_BUILT_S_E2020_GLOBE_R2023A_54009_100/"
                   "V1-0/tiles/%s.zip")


def charger_script29():
    spec = importlib.util.spec_from_file_location(
        "robustesse", RACINE / "scripts" / "29_robustesse_indice.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def telecharger(url, chemin):
    if chemin.exists():
        return True
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_suffix(chemin.suffix + ".part")
    for essai in range(1, 6):
        try:
            r = requests.get(url, stream=True, timeout=120)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for bloc in r.iter_content(1 << 20):
                    f.write(bloc)
            tmp.replace(chemin)
            return True
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError,
                requests.Timeout) as exc:
            print("  coupure reseau sur %s (essai %d/5) : %s" % (chemin.name, essai,
                                                              type(exc).__name__))
            time.sleep(5 * essai)
    raise SystemExit("Telechargement impossible apres 5 essais : %s" % url)


def tuiles_dem():
    chemins = []
    for lat in range(int(np.floor(BBOX[1])), int(np.ceil(BBOX[3]))):
        for lon in range(int(np.floor(BBOX[0])), int(np.ceil(BBOX[2]))):
            n = "Copernicus_DSM_COG_10_N%02d_00_W%03d_00_DEM" % (lat, -lon)
            chemin = DEM_DIR / (n + ".tif")
            if telecharger(DEM_URL.format(n=n), chemin):
                chemins.append(chemin)
    return chemins


def tuile_ghsl(nom):
    zip_p = GHSL_DIR / (nom + ".zip")
    telecharger(GHSL_URL_MODELE % nom, zip_p)
    tif_p = GHSL_DIR / (nom + ".tif")
    if not tif_p.exists():
        with zipfile.ZipFile(zip_p) as z:
            membre = [m for m in z.namelist() if m.endswith(".tif")][0]
            tif_p.write_bytes(z.read(membre))
    return tif_p


def grille_ghsl():
    """Grille de 100 m alignee sur GHSL et couvrant BBOX, remplie par copie des tuiles.

    Lire une fenetre qui deborde d'une tuile renvoie une image rognee dont le
    geo-referencement ne correspond plus : on construit donc la grille d'abord, puis on
    y recopie chaque tuile (meme projection, meme pas de 100 m, plus proche voisin).
    """
    chemins = [tuile_ghsl(n) for n in GHSL_TUILES]
    with rasterio.open(chemins[0]) as src:
        crs = src.crs
    vers = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    bord_lon = np.r_[np.linspace(BBOX[0], BBOX[2], 50), np.full(50, BBOX[2]),
                     np.linspace(BBOX[2], BBOX[0], 50), np.full(50, BBOX[0])]
    bord_lat = np.r_[np.full(50, BBOX[1]), np.linspace(BBOX[1], BBOX[3], 50),
                     np.full(50, BBOX[3]), np.linspace(BBOX[3], BBOX[1], 50)]
    xs, ys = vers.transform(bord_lon, bord_lat)
    x0, x1 = np.floor(min(xs) / 100) * 100, np.ceil(max(xs) / 100) * 100
    y0, y1 = np.floor(min(ys) / 100) * 100, np.ceil(max(ys) / 100) * 100
    transform = from_origin(x0, y1, 100, 100)
    forme = (int(round((y1 - y0) / 100)), int(round((x1 - x0) / 100)))
    bati = np.zeros(forme, dtype="float64")
    for c in chemins:
        with rasterio.open(c) as src:
            tmp = np.full(forme, np.nan, dtype="float64")
            reproject(source=rasterio.band(src, 1), destination=tmp,
                      src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                      dst_transform=transform, dst_crs=crs, dst_nodata=np.nan,
                      resampling=Resampling.nearest)
        ok = ~np.isnan(tmp)
        bati[ok] = tmp[ok]
    bati = np.clip(bati, 0, 10000)
    return bati, transform, crs


def altitude_sur_grille(chemins, forme, transform, crs):
    alt = np.full(forme, np.nan, dtype="float32")
    for c in chemins:
        with rasterio.open(c) as src:
            tmp = np.full(forme, np.nan, dtype="float32")
            reproject(source=rasterio.band(src, 1), destination=tmp,
                      src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                      dst_transform=transform, dst_crs=crs, dst_nodata=np.nan,
                      resampling=Resampling.average)
        ok = ~np.isnan(tmp)
        alt[ok] = tmp[ok]
    return alt


def tpi(alt, fenetre):
    """Altitude moins la moyenne de la fenetre carree, sans compter les cellules vides."""
    valide = ~np.isnan(alt)
    somme = uniform_filter(np.where(valide, alt, 0.0).astype("float64"), size=fenetre,
                           mode="constant")
    poids = uniform_filter(valide.astype("float64"), size=fenetre, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        moyenne = somme / poids
    return np.where(valide, alt - moyenne, np.nan)


def zones(geojson, champ_code, champ_nom, forme, transform, crs):
    geo = json.loads(geojson.read_text(encoding="utf-8"))
    vers = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    lignes, formes = [], []
    for k, f in enumerate(geo["features"], start=1):
        p = f["properties"]
        lignes.append({"id": k, "pcode": p[champ_code], "nom": p[champ_nom],
                       "departement": p.get("adm2_name"), "region": p.get("adm1_name")})
        formes.append((transformer_geom(vers, shape(f["geometry"])), k))
    etiquettes = rasterize(formes, out_shape=forme, transform=transform, fill=0,
                           all_touched=False, dtype="int32")
    return pd.DataFrame(lignes), etiquettes


def mesures(etiquettes, ids, bati, bas):
    n = int(ids.max()) + 1
    plat = etiquettes.ravel()
    tot = np.bincount(plat, weights=bati.ravel(), minlength=n)
    en_bas = np.bincount(plat, weights=(bati * bas).ravel(), minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        part = en_bas / tot
    return part[ids], en_bas[ids] / 1e6, tot[ids] / 1e6


def rang(s):
    return s.rank(pct=True, method="average")


def test_t2(y, pop, u):
    x0 = sm.add_constant(pd.DataFrame({"rang_population": rang(pop)}))
    x1 = sm.add_constant(pd.DataFrame({"rang_population": rang(pop), "rang_U": rang(u)}))
    m0 = sm.Logit(y.astype(float), x0).fit(disp=0)
    m1 = sm.Logit(y.astype(float), x1).fit(disp=0)
    lr = 2 * (m1.llf - m0.llf)
    return {"coef_rang_U": round(float(m1.params["rang_U"]), 3),
            "lr": round(float(lr), 3), "p": round(float(chi2.sf(lr, 1)), 4),
            "coef_rang_population": round(float(m1.params["rang_population"]), 3)}


def main():
    r29 = charger_script29()
    SORTIE.mkdir(parents=True, exist_ok=True)

    print("Telechargement / lecture des donnees...")
    bati, transform, crs = grille_ghsl()
    chemins = tuiles_dem()
    alt = altitude_sur_grille(chemins, bati.shape, transform, crs)
    print("  grille %d x %d cellules de 100 m, %d tuiles DEM" % (bati.shape[0], bati.shape[1],
                                                                  len(chemins)))

    dep, etiq_dep = zones(HDX / "sen_admin2.geojson", "adm2_pcode", "adm2_name",
                          bati.shape, transform, crs)
    arr, etiq_arr = zones(HDX / "sen_admin3.geojson", "adm3_pcode", "adm3_name",
                          bati.shape, transform, crs)

    def calculer(fenetre, seuil):
        bas = (tpi(alt, fenetre) <= seuil).astype("float64")
        return bas

    # Garde-fou : chaque zone doit avoir des cellules, du bati et une altitude.
    for nom_niveau, t_z, etiq in (("departements", dep, etiq_dep),
                                  ("arrondissements", arr, etiq_arr)):
        n_cel = np.bincount(etiq.ravel(), minlength=int(t_z["id"].max()) + 1)[t_z["id"]]
        n_bati = np.bincount(etiq.ravel(), weights=bati.ravel(),
                             minlength=int(t_z["id"].max()) + 1)[t_z["id"]]
        vides = t_z.loc[(n_cel == 0) | (n_bati == 0), "nom"].tolist()
        if vides:
            raise SystemExit("%s sans cellule ou sans bati : %s" % (nom_niveau, vides))
    if np.isnan(alt[etiq_dep > 0]).any():
        raise SystemExit("Cellules du Senegal sans altitude : %d" % int(
            np.isnan(alt[etiq_dep > 0]).sum()))

    bas = calculer(FENETRE, SEUIL_M)
    dep["U"], dep["U_abs_km2"], dep["bati_km2"] = mesures(etiq_dep, dep["id"].values, bati, bas)
    arr["U"], arr["U_abs_km2"], arr["bati_km2"] = mesures(etiq_arr, arr["id"].values, bati, bas)

    indice = pd.read_csv(VULN / "indice_risque_departements.csv", encoding="utf-8")
    dep = dep.merge(indice[["pcode", "population_2023", "E_exposition", "indice_risque"]],
                    on="pcode", how="left")
    if dep["population_2023"].isna().any():
        raise SystemExit("Departements sans population : %s" % dep.loc[
            dep["population_2023"].isna(), "nom"].tolist())

    inv = pd.read_csv(INVENTAIRE, encoding="utf-8")
    touches = set(inv[inv["certitude"] == "A"]["departement"])
    inconnus = sorted(touches - set(dep["nom"]))
    if inconnus:
        raise SystemExit("Departements de l'inventaire absents des contours : %s" % inconnus)
    dep["touche_A"] = dep["nom"].isin(touches)
    t, nt = dep[dep["touche_A"]], dep[~dep["touche_A"]]

    rng = np.random.default_rng(r29.GRAINE)
    res = {"protocole": "outputs/vulnerabilite/alea_urbain/PROTOCOLE.md (commit 8a6800d)",
           "n_departements": int(len(dep)), "n_touches_A": int(dep["touche_A"].sum()),
           "bootstrap": r29.N_BOOT, "graine": r29.GRAINE}

    a, lo, hi, p = r29.auc_ic(t["U"], nt["U"], rng)
    res["T1"] = {"auc": round(a, 3), "ic95": [round(lo, 3), round(hi, 3)],
                 "p_mann_whitney": round(p, 4), "critere_satisfait": bool(lo > 0.5)}
    res["T2"] = test_t2(dep["touche_A"], dep["population_2023"], dep["U"])
    res["T2"]["critere_satisfait"] = bool(res["T2"]["p"] < 0.05 and res["T2"]["coef_rang_U"] > 0)
    a, lo, hi, p = r29.auc_ic(t["U_abs_km2"], nt["U_abs_km2"], rng)
    res["T3_U_abs"] = {"auc": round(a, 3), "ic95": [round(lo, 3), round(hi, 3)]}
    score = np.sqrt(rang(dep["U"]) * dep["E_exposition"])
    a, lo, hi, p = r29.auc_ic(score[dep["touche_A"]], score[~dep["touche_A"]], rng)
    res["T4_U_x_E"] = {"auc": round(a, 3), "ic95": [round(lo, 3), round(hi, 3)]}
    a, lo, hi, p = r29.auc_ic(t["population_2023"], nt["population_2023"], rng)
    res["reference_population"] = {"auc": round(a, 3), "ic95": [round(lo, 3), round(hi, 3)]}

    if res["T1"]["critere_satisfait"] and res["T2"]["critere_satisfait"]:
        res["decision"] = ("T1 et T2 satisfaits : U entre comme alea d'inondation urbaine "
                           "dans un second indice (protocole, section 5).")
    elif res["T1"]["critere_satisfait"]:
        res["decision"] = ("Seul T1 est satisfait : U est publie comme indicateur descriptif, "
                           "sans apport demontre au-dela de la population.")
    else:
        res["decision"] = "T1 non satisfait : piste testee et ecartee, resultat publie tel quel."

    sens = []
    for fen, seuil in SENSIBILITE:
        b = calculer(fen, seuil)
        u, _, _ = mesures(etiq_dep, dep["id"].values, bati, b)
        u = pd.Series(u, index=dep.index)
        a, lo, hi, _ = r29.auc_ic(u[dep["touche_A"]], u[~dep["touche_A"]], rng)
        sens.append({"fenetre": fen, "seuil_m": seuil, "auc": round(a, 3),
                     "ic95": [round(lo, 3), round(hi, 3)]})
    res["sensibilite_pour_information"] = sens
    res["couverture"] = {
        "cellules_sans_altitude_dans_le_pays": int(np.isnan(alt[etiq_dep > 0]).sum()),
        "bati_total_km2": round(float(dep["bati_km2"].sum()), 1),
        "part_nationale_du_bati_en_terrain_bas": round(
            float(dep["U_abs_km2"].sum() / dep["bati_km2"].sum()), 4),
    }

    cols = ["pcode", "nom", "region", "touche_A", "population_2023", "bati_km2",
            "U_abs_km2", "U", "E_exposition", "indice_risque"]
    dep.sort_values("U", ascending=False)[cols].round(4).to_csv(
        SORTIE / "alea_urbain_departements.csv", index=False, encoding="utf-8")
    arr.sort_values("U", ascending=False)[
        ["pcode", "nom", "departement", "region", "bati_km2", "U_abs_km2", "U"]].round(4).to_csv(
        SORTIE / "alea_urbain_arrondissements.csv", index=False, encoding="utf-8")
    (SORTIE / "resultats.json").write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
