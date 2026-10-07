#!/usr/bin/env python3
"""Contours approximatifs des communes, reconstruits a partir des localites de l'ANSD.

Il n'existe pas de contour public a jour des communes du Senegal : GADM 4.1 en donne 431
dans un decoupage ancien (licence non commerciale, redistribution interdite) et l'ANSD
n'en publie pas. L'ANSD a en revanche transmis les coordonnees de 16 548 localites
rangees par commune (553 communes, decoupage actuel).

Methode
  1. Diagramme de Voronoi des localites : chaque point du territoire est attribue a la
     localite la plus proche.
  2. Les cellules sont regroupees par commune ANSD, puis decoupees par la frontiere
     nationale (OCHA COD-AB, CC BY-IGO).
  3. Chaque commune recoit son departement actuel (46, OCHA) par la plus grande
     surface commune, et ses noms RGPH-5 2023 par la correspondance du script 33
     (une commune ANSD peut porter plusieurs communes RGPH-5 decoupees depuis, par
     exemple Keur Massar Nord et Sud).
Controle : pour les communes dont le nom existe aussi dans GADM, recouvrement (IoU)
entre le contour reconstruit et le contour GADM, a titre indicatif seulement.

Ce sont des contours APPROXIMATIFS : la limite entre deux communes passe a mi-distance
entre leurs localites voisines, pas sur la limite administrative officielle.

Entrees : data/raw/ansd/ansd_coordonnees_localites.csv,
          outputs/exposition_evenements/correspondance_communes_rgph5_ansd.csv (script 33),
          data/raw/hdx/sen_admin0.geojson, sen_admin2.geojson
Sorties : data/processed/communes_reconstruites_ansd.geojson (+ controle CSV, resume)
Usage   : py -3 scripts/34_communes_reconstruites.py
"""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import voronoi_polygons
from shapely.geometry import MultiPoint, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

RACINE = Path(__file__).resolve().parent.parent
ANSD = RACINE / "data" / "raw" / "ansd"
HDX = RACINE / "data" / "raw" / "hdx"
PROCESSED = RACINE / "data" / "processed"
EXPO = RACINE / "outputs" / "exposition_evenements"
GADM_GEOJSON = RACINE / "data" / "geographic" / "senegal_boundaries"
TOLERANCE_SIMPLIFICATION = 0.002   # degre, environ 200 m


def script33():
    spec = importlib.util.spec_from_file_location(
        "s33", RACINE / "scripts" / "33_population_touchee_evenements.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def charger_geojson(chemin):
    return json.loads(chemin.read_text(encoding="utf-8"))["features"]


def main():
    s33 = script33()
    a = pd.read_csv(ANSD / "ansd_coordonnees_localites.csv", encoding="utf-8")
    a["kd"] = a["DEPARTEMENT"].map(s33.cle)
    a["kc"] = a["COMMUNE"].map(s33.cle)
    pts = a.groupby(["LON", "LAT"], as_index=False).first()   # 2 coordonnees en double

    pays = unary_union([shape(f["geometry"]) for f in charger_geojson(HDX / "sen_admin0.geojson")])
    deps = [(f["properties"]["adm2_name"], f["properties"]["adm2_pcode"],
             f["properties"]["adm1_name"], shape(f["geometry"]))
            for f in charger_geojson(HDX / "sen_admin2.geojson")]

    corr = pd.read_csv(EXPO / "correspondance_communes_rgph5_ansd.csv", encoding="utf-8")
    corr = corr.dropna(subset=["commune_ansd"]).assign(
        kd=lambda d: d["Departement"].map(s33.cle).replace(s33.ALIAS_DEPARTEMENTS))
    noms_rgph = corr.groupby(["kd", "commune_ansd"])["COMMUNE"].apply(
        lambda s: " ; ".join(sorted(set(s))))
    # Repli quand le departement differe entre les deux fichiers (Diaxay : Rufisque cote
    # ANSD, Keur Massar cote RGPH-5) : nom de commune ANSD seul, s'il est unique.
    uniques = corr.groupby("commune_ansd")["kd"].nunique()
    seul_nom = corr[corr["commune_ansd"].isin(uniques[uniques == 1].index)].groupby(
        "commune_ansd")["COMMUNE"].apply(lambda s: " ; ".join(sorted(set(s))))

    # Voronoi DANS chaque departement OCHA (2024) : les communes s'emboitent exactement
    # dans les 46 departements actuels. Une commune dont les localites tombent dans deux
    # departements donne deux morceaux, reunis ensuite en une seule entite.
    from shapely.geometry import Point
    morceaux = {}
    for nom_dep, pcode, region, geom_dep in deps:
        dedans = pts[[geom_dep.contains(Point(x, y)) for x, y in zip(pts["LON"], pts["LAT"])]]
        if dedans.empty:
            continue
        if len(dedans) == 1:
            cell = [geom_dep]
        else:
            cell = list(voronoi_polygons(MultiPoint(list(zip(dedans["LON"], dedans["LAT"]))),
                                         extend_to=geom_dep.envelope.buffer(0.5),
                                         ordered=True).geoms)
        for (kd, kc, nom, dep_ansd, cod), c in zip(
                zip(dedans["kd"], dedans["kc"], dedans["COMMUNE"], dedans["DEPARTEMENT"],
                    dedans["COD_ENTITE"]), cell):
            # Cle departement ANSD + commune : des communes homonymes existent.
            m = morceaux.setdefault((kd, kc), {"nom": nom, "dep_ansd": dep_ansd, "cod": int(cod),
                                         "par_dep": {}, "localites": 0})
            m["par_dep"].setdefault((nom_dep, pcode, region), []).append(c.intersection(geom_dep))
            m["localites"] += 1

    lignes, geoms, cles = [], [], []
    for (kd, kc), m in morceaux.items():
        parts = {d: unary_union(v) for d, v in m["par_dep"].items()}
        poly = unary_union(list(parts.values()))
        if poly.is_empty:
            continue
        d = max(parts, key=lambda k: parts[k].area)
        lignes.append({
            "commune_ansd": m["nom"], "departement_ansd": m["dep_ansd"], "cod_entite": m["cod"],
            "departement": d[0], "adm2_pcode": d[1], "region": d[2],
            "communes_rgph5": noms_rgph.get((kd, kc)) or seul_nom.get(kc, ""),
            "localites": m["localites"],
            "part_dans_departement": round(parts[d].area / poly.area, 3),
            "superficie_km2": None,
        })
        geoms.append(poly)
        cles.append(kc)

    t = pd.DataFrame(lignes)
    # Superficie approchee en km2 (projection equivalente locale).
    from pyproj import Transformer
    from shapely.ops import transform as tr
    vers_utm = Transformer.from_crs("EPSG:4326", "EPSG:32628", always_xy=True).transform
    t["superficie_km2"] = [round(tr(vers_utm, p).area / 1e6, 1) for p in geoms]

    # Controle indicatif contre GADM 4.1 niveau 4 (GeoJSON non versionne : on lit le .shp
    # seulement s'il est lisible sans dependance supplementaire ; sinon controle saute).
    iou = []
    try:
        import shapefile  # pyshp, optionnel
        rg = shapefile.Reader(str(GADM_GEOJSON / "gadm41_SEN_4.shp"), encoding="utf-8")
        gadm = {s33.cle(rec["NAME_4"]): shape(sh.__geo_interface__)
                for rec, sh in zip(rg.records(), rg.shapes())}
        for kc, p in zip(cles, geoms):
            if kc in gadm:
                inter = p.intersection(gadm[kc]).area
                iou.append(inter / p.union(gadm[kc]).area)
    except ImportError:
        pass

    feats = [{"type": "Feature", "properties": {k: (None if pd.isna(v) else v)
                                                  for k, v in r.items()},
              "geometry": mapping(p.simplify(TOLERANCE_SIMPLIFICATION, preserve_topology=True))}
             for r, p in zip(t.to_dict("records"), geoms)]
    sortie = PROCESSED / "communes_reconstruites_ansd.geojson"
    sortie.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                 ensure_ascii=False), encoding="utf-8")
    t.to_csv(EXPO / "communes_reconstruites_controle.csv", index=False, encoding="utf-8")

    resume = {
        "communes": int(len(t)), "localites": int(len(pts)),
        "departements_couverts": int(t["adm2_pcode"].nunique()),
        "superficie_totale_km2": round(float(t["superficie_km2"].sum()), 0),
        "communes_a_cheval_sur_deux_departements_(<90 %)": int((t["part_dans_departement"] < 0.9).sum()),
        "iou_gadm": ({"communes_comparees": len(iou), "mediane": round(float(np.median(iou)), 3),
                      "part_iou_sup_0_5": round(float(np.mean(np.array(iou) > 0.5)), 3)}
                     if iou else "controle GADM non fait (pyshp absent)"),
        "fichier": str(sortie.relative_to(RACINE)).replace("\\", "/"),
        "taille_mo": round(sortie.stat().st_size / 1e6, 2),
        "licence": "derive des coordonnees ANSD et des contours OCHA (CC BY-IGO) ; pas de GADM",
    }
    (EXPO / "communes_reconstruites_resume.json").write_text(
        json.dumps(resume, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resume, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
