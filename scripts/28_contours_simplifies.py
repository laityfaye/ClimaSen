#!/usr/bin/env python3
"""Contours alleges des departements et arrondissements pour la page Vulnerabilite.

Les GeoJSON OCHA/HDX (COD-AB Senegal v02, 2024, CC BY-IGO) pesent 11 et 14 Mo :
trop pour etre lus et envoyes au navigateur a chaque affichage. On les simplifie
une fois ici.

Methode : shapely.coverage_simplify (Visvalingam-Whyatt sur une couverture), qui
simplifie chaque frontiere commune une seule fois : deux zones voisines gardent
exactement la meme limite, sans trou ni chevauchement (une simplification polygone
par polygone en creerait). Coordonnees arrondies a 1e-4 degre (~11 m).

Controles affiches : poids, nombre de sommets, ecart de surface par zone.

Entrees : data/raw/hdx/sen_admin2.geojson, sen_admin3.geojson
Sorties : data/processed/contours_admin2_simplifies.geojson (46 departements)
          data/processed/contours_admin3_simplifies.geojson (125 arrondissements)

Usage : py -3 scripts/28_contours_simplifies.py [--tolerance 0.002]
"""
import argparse
import json
from pathlib import Path

import geopandas as gpd
import shapely

RACINE = Path(__file__).resolve().parent.parent
HDX = RACINE / "data" / "raw" / "hdx"
SORTIE = RACINE / "data" / "processed"
CRS_METRIQUE = "EPSG:32628"  # UTM 28N, pour comparer les surfaces

NIVEAUX = {
    "admin2": ("sen_admin2.geojson", {"adm2_pcode": "pcode", "adm2_name": "nom",
                                      "adm1_name": "region"}),
    "admin3": ("sen_admin3.geojson", {"adm3_pcode": "pcode", "adm3_name": "nom",
                                      "adm2_pcode": "adm2_pcode", "adm2_name": "departement",
                                      "adm1_name": "region"}),
}


def sommets(geoms):
    return int(sum(shapely.get_num_coordinates(g) for g in geoms))


def simplifier(niveau, tolerance):
    fichier, colonnes = NIVEAUX[niveau]
    g = gpd.read_file(HDX / fichier)
    # Meme nom que dans le script 27 : "N/A" serait relu comme valeur manquante.
    if "adm3_name" in g:
        g.loc[g["adm3_name"] == "N/A", "adm3_name"] = "Sans nom HDX (N/A)"
    origine = g.geometry.values
    simple = shapely.coverage_simplify(origine, tolerance)
    simple = shapely.set_precision(simple, 1e-4)
    simple = shapely.make_valid(simple)
    out = gpd.GeoDataFrame(g[list(colonnes)].rename(columns=colonnes), geometry=simple,
                           crs=g.crs)

    surf0 = gpd.GeoSeries(origine, crs=g.crs).to_crs(CRS_METRIQUE).area
    surf1 = out.geometry.to_crs(CRS_METRIQUE).area
    ecart = ((surf1 - surf0).abs() / surf0 * 100)
    chemin = SORTIE / ("contours_%s_simplifies.geojson" % niveau)
    geo = json.loads(out.to_json(drop_id=True))
    geo["source"] = ("OCHA COD-AB Senegal v02 (2024), CC BY-IGO ; simplifie par "
                     "scripts/28_contours_simplifies.py (coverage_simplify, tolerance "
                     "%s deg)" % tolerance)
    chemin.write_text(json.dumps(geo, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    print("%s : %d zones, %d -> %d sommets, %.1f Mo -> %.2f Mo, ecart de surface "
          "median %.2f %%, max %.2f %% (%s)" % (
              niveau, len(out), sommets(origine), sommets(simple),
              (HDX / fichier).stat().st_size / 1e6, chemin.stat().st_size / 1e6,
              ecart.median(), ecart.max(), out.loc[ecart.idxmax(), "nom"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance", type=float, default=0.002,
                    help="tolerance de simplification en degres (defaut 0.002, ~220 m)")
    args = ap.parse_args()
    SORTIE.mkdir(parents=True, exist_ok=True)
    for niveau in NIVEAUX:
        simplifier(niveau, args.tolerance)


if __name__ == "__main__":
    main()
