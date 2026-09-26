"""
Script 16 : fond de carte embarque pour les cartes de Jarvis.

Jarvis dessine ses cartes sur le serveur, ou cartopy n'est pas installe (et
ou il ne pourrait pas telecharger Natural Earth). On extrait donc UNE FOIS,
sur le poste de developpement, les contours utiles, simplifies et arrondis,
dans un petit fichier versionne : jarvis/cartes/fond_carte.json.gz.

Contenu :
  - terres : continents du monde (Natural Earth 110m), pour la carte SST
    globale 60S-60N ;
  - ocean_ouest_afrique : ocean (Natural Earth 10m) decoupe autour du
    Senegal, pour une cote precise sur les cartes nationales ;
  - frontieres_ouest_afrique : frontieres des pays voisins (110m), en trait
    discret.

Natural Earth est dans le domaine public.

Usage : py -3 scripts/16_build_jarvis_fond_carte.py
"""
import gzip
import json
from pathlib import Path

import cartopy.io.shapereader as shpreader
from shapely.geometry import box

BASE = Path(__file__).resolve().parent.parent
SORTIE = BASE / "jarvis" / "cartes" / "fond_carte.json.gz"
VERSION = 1

# Emprise des cartes nationales (un peu plus large que la grille CHIRPS).
EMPRISE_SN = (-18.2, 11.6, -10.8, 17.2)     # lon_min, lat_min, lon_max, lat_max


def _anneaux(geom, tolerance, decimales):
    """Anneaux exterieurs (et trous) simplifies, en listes [[lon, lat], ...]."""
    geom = geom.simplify(tolerance, preserve_topology=True)
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    sortie = []
    for poly in polys:
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        for anneau in [poly.exterior] + list(poly.interiors):
            pts = [[round(x, decimales), round(y, decimales)] for x, y in anneau.coords]
            if len(pts) >= 4:
                sortie.append(pts)
    return sortie


def _lignes(geom, tolerance, decimales):
    geom = geom.simplify(tolerance, preserve_topology=True)
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    sortie = []
    for part in parts:
        if part.geom_type == "Polygon":
            coords = part.exterior.coords
        elif part.geom_type == "LineString":
            coords = part.coords
        else:
            continue
        pts = [[round(x, decimales), round(y, decimales)] for x, y in coords]
        if len(pts) >= 2:
            sortie.append(pts)
    return sortie


def main():
    terres = []
    for geom in shpreader.Reader(shpreader.natural_earth(
            resolution="110m", category="physical", name="land")).geometries():
        terres.extend(_anneaux(geom, 0.15, 2))

    cadre = box(*EMPRISE_SN).buffer(0.5)
    ocean = []
    for geom in shpreader.Reader(shpreader.natural_earth(
            resolution="10m", category="physical", name="ocean")).geometries():
        morceau = geom.intersection(cadre)
        if not morceau.is_empty:
            ocean.extend(_anneaux(morceau, 0.01, 3))

    frontieres = []
    for rec in shpreader.Reader(shpreader.natural_earth(
            resolution="110m", category="cultural", name="admin_0_countries")).records():
        if rec.attributes.get("ADM0_A3") == "SEN":
            continue                       # contour precis GADM, cote Jarvis
        morceau = rec.geometry.boundary.intersection(cadre)
        if not morceau.is_empty:
            frontieres.extend(_lignes(morceau, 0.01, 3))

    donnees = {"version": VERSION, "source": "Natural Earth (domaine public)",
               "emprise_senegal": EMPRISE_SN, "terres": terres,
               "ocean_ouest_afrique": ocean,
               "frontieres_ouest_afrique": frontieres}
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(SORTIE, "wt", encoding="utf-8") as f:
        json.dump(donnees, f, separators=(",", ":"))
    print("Ecrit %s (%d octets) : %d anneaux de terres, %d d'ocean, %d frontieres"
          % (SORTIE.relative_to(BASE), SORTIE.stat().st_size, len(terres),
             len(ocean), len(frontieres)))


if __name__ == "__main__":
    main()
