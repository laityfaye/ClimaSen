"""Cartes de Jarvis: donnees et rendu.

Deux familles, les memes que le module Clustering du dashboard:
  - carte_sst: anomalies SST globales (60S-60N) du centroide d'un cluster
    K-Means, avec les boites des indices et le Senegal;
  - carte_senegal: une grille CHIRPS 0,25 deg sur le Senegal (un evenement,
    un composite de cluster, ou la frequence des extremes).

Donnees: les memes fichiers que le dashboard et le script 01, lus
directement (numpy, pas de loader streamlit). La precipitation d'un jour est
reconstruite par anomalie x ecart-type + climatologie du jour: verifie
egale, au centieme, aux max_precip / max_anomaly / coverage_percent du
catalogue d'evenements.

Fond de carte: jarvis/cartes/fond_carte.json.gz, extrait une fois de Natural
Earth par scripts/16_build_jarvis_fond_carte.py. cartopy n'est pas requis
sur le serveur.

La specification d'une carte SST ne porte PAS la grille (480 x 1440): juste
la phase et le cluster; la grille est relue du cache au rendu. Une carte du
Senegal porte sa grille (18 x 25), petite.
"""
import gzip
import json
import threading
from functools import lru_cache

from ..config import PROJECT_DIR

DOSSIER = PROJECT_DIR
FOND = PROJECT_DIR / "jarvis" / "cartes" / "fond_carte.json.gz"

PHASES = ("Phase_1_debut", "Phase_2_pleine", "Phase_3_fin", "All_phases")

# Boites des indices tracees sur la carte SST (memes bornes que
# scripts/dashboard_utils._SST_REGIONS et le script d'extraction). AMO et
# IOBM, qui couvrent un bassin entier, ne sont pas tracees: elles
# masqueraient tout le reste; leur moyenne figure dans le resume.
BOITES = [
    ("Niño 1+2", -90, -80, -10, 0),
    ("Niño 3.4", -170, -120, -5, 5),
    ("Niño 4", 160, 180, -5, 5),
    ("Niño 4", -180, -150, -5, 5),
    ("ATL3", -20, 0, -3, 3),
    ("TNA", -55, -15, 5, 23),
    ("TSA", -30, 10, -20, 0),
    ("IOD-O", 50, 70, -10, 10),
    ("IOD-E", 90, 110, -10, 0),
]
BOITES_RESUME = {
    "Nino12": [(-90, -80, -10, 0)],
    "Nino3": [(-150, -90, -5, 5)],
    "Nino34": [(-170, -120, -5, 5)],
    "Nino4": [(160, 180, -5, 5), (-180, -150, -5, 5)],
    "ATL3": [(-20, 0, -3, 3)],
    "TNA": [(-55, -15, 5, 23)],
    "TSA": [(-30, 10, -20, 0)],
    "AMO": [(-80, 0, 0, 60)],
    "IOD_ouest": [(50, 70, -10, 10)],
    "IOD_est": [(90, 110, -10, 0)],
    "IOBM": [(40, 100, -20, 20)],
}

DAKAR = (-17.45, 14.69)

# Couleurs des cartes, par theme du widget. Sur fond sombre, le milieu de la
# divergente et le bas des sequentielles se fondent dans le fond: seul ce qui
# s'ecarte de la normale s'allume.
STYLES = {
    "clair": {
        "fond": "#FFFFFF", "ocean": "#EAF2F8", "terre": "#E6E4DF",
        "cote": "#8C8A84", "frontiere": "#B5B3AD", "senegal": "#0B0B0B",
        "regions": "#FFFFFF", "texte": "#0B0B0B", "texte2": "#52514E",
        "grille": "#E0DFDB", "accent": "#EB6834", "halo": "#FFFFFF",
        "boite": "#0B0B0B",
        "sst": ["#184F95", "#6DA7EC", "#F4F3F0", "#EC8A89", "#B83232"],
        "pluie": ["#F3F8FB", "#C6DBEF", "#6BAED6", "#2171B5", "#08306B"],
        "anomalie": ["#FFF7EC", "#FDD49E", "#FC8D59", "#D7301F", "#7F0000"],
        "seuil": "#0B0B0B",
    },
    "sombre": {
        "fond": "#1E293B", "ocean": "#172131", "terre": "#26334A",
        "cote": "#64748B", "frontiere": "#475569", "senegal": "#E2E8F0",
        "regions": "#1E293B", "texte": "#FFFFFF", "texte2": "#C3C2B7",
        "grille": "#2B3850", "accent": "#F59E0B", "halo": "#1E293B",
        "boite": "#E2E8F0",
        "sst": ["#6DA7EC", "#2A5C9E", "#2A3547", "#A33A3A", "#E66767"],
        "pluie": ["#1B2A40", "#1D4E7A", "#2F7FC1", "#6DB6F0", "#D6F0FF"],
        "anomalie": ["#231A33", "#5B2A6E", "#A8406F", "#E8755A", "#FFE3A3"],
        "seuil": "#FFFFFF",
    },
    # Interface J.A.R.V.I.S: noir bleute et cyan (#00E5FF) du widget.
    "hud": {
        "fond": "#07121A", "ocean": "#040C12", "terre": "#16323D",
        "cote": "#2A7A8C", "frontiere": "#17414E", "senegal": "#00E5FF",
        "regions": "#0B3A47", "texte": "#E0F7FF", "texte2": "#7FB8C8",
        "grille": "#0E2530", "accent": "#FFB547", "halo": "#040C12",
        "boite": "#9FEFFF",
        "sst": ["#6DA7EC", "#2A5C9E", "#10222B", "#A33A3A", "#FF7A6B"],
        "pluie": ["#08202B", "#0B4F63", "#0E8FB0", "#35D0F0", "#D8FBFF"],
        "anomalie": ["#0B1A26", "#4A2466", "#A23A7A", "#F06A5A", "#FFE08A"],
        "seuil": "#00E5FF",
    },
}

_verrou = threading.Lock()


class CarteIndisponible(Exception):
    pass


# =============================================================================
# Donnees
# =============================================================================
@lru_cache(maxsize=1)
def fond():
    with gzip.open(FOND, "rt", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def grille():
    """Anomalies quotidiennes + climatologie: tout ce qu'il faut pour
    cartographier n'importe quel jour 1981-2023 sur le Senegal."""
    import numpy as np
    base = DOSSIER / "data" / "processed"
    try:
        z = np.load(base / "standardized_anomalies_senegal.npz", allow_pickle=True)
        c = np.load(base / "climatology_senegal.npz", allow_pickle=True)
    except OSError as exc:
        raise CarteIndisponible("Grilles CHIRPS absentes: %s" % exc)
    dates = [str(d) for d in z["dates"]]
    return {
        "anomalies": z["anomalies"].astype("float32"),
        "index": {d: i for i, d in enumerate(dates)},
        "clim": c["climatology"].astype("float32"),
        "ecart": c["std_dev"].astype("float32"),
        "lats": [float(v) for v in c["lats"]],
        "lons": [float(v) for v in c["lons"]],
    }


def jour(date: str):
    """(anomalie sigma, precipitation mm) d'un jour, grilles 18 x 25."""
    import numpy as np
    g = grille()
    i = g["index"].get(date)
    if i is None:
        raise CarteIndisponible("Date hors de la periode couverte: %s" % date)
    an = g["anomalies"][i]
    doy = _jour_de_l_annee(date)
    pluie = an * g["ecart"][doy] + g["clim"][doy]
    pluie = np.where(np.isnan(an), np.nan, np.maximum(pluie, 0.0))
    return an, pluie


def _jour_de_l_annee(date: str) -> int:
    import datetime
    return datetime.date.fromisoformat(date).timetuple().tm_yday - 1


@lru_cache(maxsize=4)
def centroides(phase: str):
    """(n_clusters, 480, 1440) anomalies SST; 0 sur les terres -> NaN."""
    import numpy as np
    if phase not in PHASES:
        raise CarteIndisponible("Phase inconnue: %s" % phase)
    chemin = DOSSIER / "outputs" / "clustering" / phase / ("%s_centroids_sst.npy" % phase)
    try:
        brut = np.load(chemin)
    except OSError as exc:
        raise CarteIndisponible("Centroides SST absents pour %s: %s" % (phase, exc))
    grille3d = brut.reshape(brut.shape[0], 480, 1440).astype("float32")
    grille3d[grille3d == 0] = np.nan
    return grille3d


def axes_sst():
    import numpy as np
    return np.linspace(-59.875, 59.875, 480), np.linspace(-179.875, 179.875, 1440)


@lru_cache(maxsize=4)
def evenements_par_cluster(phase: str):
    import pandas as pd
    chemin = (DOSSIER / "outputs" / "clustering" / phase
              / ("%s_events_with_clusters.csv" % phase))
    try:
        return pd.read_csv(chemin, encoding="utf-8")
    except OSError as exc:
        raise CarteIndisponible("Affectation des clusters absente: %s" % exc)


@lru_cache(maxsize=1)
def senegal():
    """Contour national (GADM) et regions administratives, en anneaux."""
    geo = DOSSIER / "data" / "geographic"
    try:
        with open(geo / "senegal_boundaries.geojson", encoding="utf-8") as f:
            pays = json.load(f)
        with open(geo / "senegal_regions.geojson", encoding="utf-8") as f:
            regions = json.load(f)
    except OSError as exc:
        raise CarteIndisponible("Contours du Senegal absents: %s" % exc)
    contour = []
    for feat in pays["features"]:
        contour.extend(_simplifier(a) for a in _anneaux_geojson(feat["geometry"]))
    liste = []
    for feat in regions["features"]:
        anneaux = [_simplifier(a) for a in _anneaux_geojson(feat["geometry"])]
        liste.append({"nom": feat["properties"].get("NAME_1", ""),
                      "anneaux": anneaux})
    return {"contour": contour, "regions": liste}


def _simplifier(anneau, pas=0.01):
    """Garde un sommet tous les `pas` degres (~1 km): invisible a l'echelle
    d'une carte nationale, et 60 000 sommets GADM ramenes a quelques
    milliers (le rendu passait de 3,6 s a moins d'une seconde)."""
    garde = [anneau[0]]
    for x, y in anneau[1:-1]:
        px, py = garde[-1]
        if abs(x - px) >= pas or abs(y - py) >= pas:
            garde.append([x, y])
    garde.append(anneau[-1])
    return garde


def _anneaux_geojson(geom):
    t, coords = geom.get("type"), geom.get("coordinates", [])
    polys = coords if t == "MultiPolygon" else ([coords] if t == "Polygon" else [])
    return [anneau for poly in polys for anneau in poly]


def moyenne_boite(grille2d, boites):
    """Moyenne d'une grille SST sur une ou plusieurs boites (lon, lat)."""
    import numpy as np
    lats, lons = axes_sst()
    valeurs = []
    for lon0, lon1, lat0, lat1 in boites:
        mi = (lats >= lat0) & (lats <= lat1)
        mj = (lons >= lon0) & (lons <= lon1)
        valeurs.append(grille2d[np.ix_(mi, mj)].ravel())
    tout = np.concatenate(valeurs)
    tout = tout[~np.isnan(tout)]
    return float(tout.mean()) if tout.size else None


# =============================================================================
# Rendu
# =============================================================================
def _carte_couleurs(stops):
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("jarvis", stops)


def _halo(s):
    import matplotlib.patheffects as pe
    return [pe.withStroke(linewidth=2.2, foreground=s["halo"])]


def _degres(v, axe):
    if axe == "lon":
        return "%d°%s" % (abs(v), "O" if v < 0 else ("E" if v > 0 else ""))
    return "%d°%s" % (abs(v), "S" if v < 0 else ("N" if v > 0 else ""))


def _axes_geo(ax, s, xticks, yticks):
    from matplotlib.ticker import FixedLocator, FuncFormatter
    ax.set_facecolor(s["ocean"])
    for cote in ax.spines.values():
        cote.set_color(s["grille"])
        cote.set_linewidth(0.6)
    ax.xaxis.set_major_locator(FixedLocator(xticks))
    ax.yaxis.set_major_locator(FixedLocator(yticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _degres(v, "lon")))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _degres(v, "lat")))
    ax.tick_params(colors=s["texte2"], length=0, labelsize=6, pad=2)
    ax.grid(True, color=s["grille"], linewidth=0.4, linestyle=(0, (2, 3)))
    ax.set_axisbelow(False)


def _polygones(ax, anneaux, facecolor, edgecolor, linewidth, zorder):
    """Une seule collection, sans recalcul des limites: add_patch par
    polygone recalculait les bornes sommet par sommet (constate: 4 s)."""
    from matplotlib.collections import PolyCollection
    ax.add_collection(PolyCollection(anneaux, closed=True, facecolors=facecolor,
                                     edgecolors=edgecolor, linewidths=linewidth,
                                     zorder=zorder), autolim=False)


def _barre(fig, image, ax, s, legende, horizontale=True, ticks=None):
    barre = fig.colorbar(image, ax=ax, orientation="horizontal" if horizontale else "vertical",
                         fraction=0.045, pad=0.07 if horizontale else 0.02,
                         aspect=45 if horizontale else 25, ticks=ticks)
    barre.outline.set_visible(False)
    barre.ax.tick_params(colors=s["texte2"], length=0, labelsize=6)
    barre.set_label(legende, color=s["texte2"], fontsize=6.5)
    return barre


def dessiner_sst(fig, spec, theme):
    """Anomalies SST du centroide: le motif oceanique d'un cluster."""
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.patches import Rectangle

    s = STYLES.get(theme, STYLES["clair"])
    d = spec["donnees"]
    z = centroides(d["phase"])[d["indice_cluster"]][::2, ::2]
    lats, lons = axes_sst()
    lats, lons = lats[::2], lons[::2]
    vlim = d["vlim"]

    ax = fig.add_axes([0.055, 0.2, 0.92, 0.78])
    _axes_geo(ax, s, range(-150, 181, 30), range(-60, 61, 20))
    image = ax.pcolormesh(lons, lats, z, cmap=_carte_couleurs(s["sst"]),
                          norm=TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim),
                          shading="nearest", rasterized=True, zorder=1)
    _polygones(ax, fond()["terres"], facecolor=s["terre"], edgecolor=s["cote"],
               linewidth=0.35, zorder=2)
    for nom, lon0, lon1, lat0, lat1 in BOITES:
        ax.add_patch(Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0, fill=False,
                               edgecolor=s["boite"], linewidth=0.55,
                               linestyle=(0, (3, 2)), zorder=3, alpha=0.85))
        if lon0 == -180:
            continue                       # Nino 4, deja etiquete a l'ouest
        ax.text(lon0 + 1, lat1 + 1.2, nom, fontsize=5.2, color=s["texte"],
                zorder=4, path_effects=_halo(s))
    ax.plot(*DAKAR, marker="*", markersize=7, color=s["accent"],
            markeredgecolor=s["halo"], markeredgewidth=0.6, zorder=5)
    ax.text(DAKAR[0] + 3, DAKAR[1] + 0.5, "Sénégal", fontsize=5.8, ha="left",
            va="center", color=s["accent"], zorder=5, path_effects=_halo(s))
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 60)
    ax.set_aspect("equal")
    cax = fig.add_axes([0.3, 0.1, 0.4, 0.03])
    barre = fig.colorbar(image, cax=cax, orientation="horizontal")
    barre.outline.set_visible(False)
    barre.ax.tick_params(colors=s["texte2"], length=0, labelsize=6)
    barre.set_label("anomalie de SST (°C)", color=s["texte2"], fontsize=6.5)


def dessiner_senegal(fig, spec, theme):
    """Une grille CHIRPS sur le Senegal, decoupee au contour national."""
    import numpy as np
    from matplotlib.colors import Normalize
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch

    s = STYLES.get(theme, STYLES["clair"])
    d = spec["donnees"]
    valeurs = np.array([[np.nan if v is None else v for v in ligne]
                        for ligne in d["valeurs"]], dtype=float)
    lats, lons = np.array(d["lats"]), np.array(d["lons"])
    lon0, lat0, lon1, lat1 = fond()["emprise_senegal"]

    ax = fig.add_axes([0.07, 0.17, 0.9, 0.8])
    _axes_geo(ax, s, range(-18, -10, 2), range(12, 18, 1))
    # Terre partout, puis l'ocean par-dessus: la cote vient du 10m.
    ax.set_facecolor(s["terre"])
    _polygones(ax, fond()["ocean_ouest_afrique"], facecolor=s["ocean"],
               edgecolor=s["cote"], linewidth=0.5, zorder=1)
    # Pas de frontieres voisines: au 1/110m, elles debordent dans le pays
    # (constate vers Kedougou et Ziguinchor). Le contour GADM suffit.

    sn = senegal()
    sommets, codes = [], []
    for anneau in sn["contour"]:
        sommets.extend(anneau)
        codes.extend([Path.MOVETO] + [Path.LINETO] * (len(anneau) - 2) + [Path.CLOSEPOLY])
    chemin = Path(sommets, codes)
    decoupe = PathPatch(chemin, facecolor="none", edgecolor="none")
    ax.add_patch(decoupe)

    echelle = d["echelle"]
    stops = s["pluie"] if echelle == "pluie" else s["anomalie"]
    carte = _carte_couleurs(stops)
    norme = Normalize(vmin=d["vmin"], vmax=d["vmax"])
    image = ax.pcolormesh(lons, lats, valeurs, cmap=carte, norm=norme,
                          shading="nearest", zorder=3, rasterized=True)
    image.set_clip_path(decoupe)

    if d.get("seuil") is not None and np.nanmax(valeurs) >= d["seuil"]:
        contour = ax.contour(lons, lats, np.nan_to_num(valeurs, nan=0.0),
                             levels=[d["seuil"]], colors=[s["seuil"]],
                             linewidths=0.9, linestyles=[(0, (3, 1.5))], zorder=4)
        for coll in getattr(contour, "collections", [contour]):
            coll.set_clip_path(decoupe)

    for region in sn["regions"]:
        _polygones(ax, region["anneaux"], facecolor="none",
                   edgecolor=s["regions"], linewidth=0.45, zorder=5)
    ax.add_patch(PathPatch(chemin, facecolor="none", edgecolor=s["senegal"],
                           linewidth=1.1, zorder=6))
    for region in sn["regions"]:
        if region["nom"] == "Dakar":
            continue                      # la ville est marquee par l'etoile
        x, y = _centre(region["anneaux"])
        ax.text(x, y, region["nom"], fontsize=5.3, ha="center", va="center",
                color=s["texte"], zorder=7, path_effects=_halo(s), alpha=0.9)

    ax.plot(*DAKAR, marker="*", markersize=6, color=s["accent"],
            markeredgecolor=s["halo"], markeredgewidth=0.5, zorder=8)
    ax.text(DAKAR[0] - 0.12, DAKAR[1] + 0.12, "Dakar", fontsize=5.6, ha="right",
            color=s["accent"], zorder=8, path_effects=_halo(s))
    for m in d.get("marqueurs", []):
        ax.plot(m["lon"], m["lat"], marker="D", markersize=4, color=s["accent"],
                markeredgecolor=s["halo"], markeredgewidth=0.6, zorder=8)
        ax.annotate(m["texte"], (m["lon"], m["lat"]), xytext=(5, 4),
                    textcoords="offset points", fontsize=5.8, color=s["accent"],
                    zorder=9, path_effects=_halo(s))
    ax.text(-15.5, 13.47, "Gambie", fontsize=4.8, color=s["texte2"],
            style="italic", zorder=7, path_effects=_halo(s))
    ax.text(-16.9, 16.75, "Mauritanie", fontsize=5, color=s["texte2"],
            style="italic", zorder=7, path_effects=_halo(s))
    ax.text(-11.4, 14.6, "Mali", fontsize=5, color=s["texte2"], style="italic",
            zorder=7, path_effects=_halo(s))
    ax.text(-13.2, 11.85, "Guinée", fontsize=5, color=s["texte2"],
            style="italic", zorder=7, path_effects=_halo(s))

    ax.set_xlim(lon0, lon1)
    ax.set_ylim(lat0, lat1)
    ax.set_aspect("equal")
    cax = fig.add_axes([0.3, 0.075, 0.4, 0.028])
    barre = fig.colorbar(image, cax=cax, orientation="horizontal")
    barre.outline.set_visible(False)
    barre.ax.tick_params(colors=s["texte2"], length=0, labelsize=6)
    barre.set_label(d["legende"], color=s["texte2"], fontsize=6.5)
    if d.get("seuil") is not None:
        barre.ax.axvline(d["seuil"], color=s["seuil"], linewidth=1.0)


def _centre(anneaux):
    """Centre du plus grand anneau (aire de Gauss): assez juste pour poser
    un nom, sans dependance a shapely."""
    meilleur, aire_max = anneaux[0], -1.0
    for a in anneaux:
        aire = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(a, a[1:])))
        if aire > aire_max:
            meilleur, aire_max = a, aire
    xs = [p[0] for p in meilleur]
    ys = [p[1] for p in meilleur]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def en_lignes_senegal(spec):
    """Vue tableau d'une carte du Senegal: une ligne par pixel valide."""
    d = spec["donnees"]
    lignes = [["latitude", "longitude", d["legende"]]]
    for i, lat in enumerate(d["lats"]):
        for j, lon in enumerate(d["lons"]):
            v = d["valeurs"][i][j]
            if v is not None:
                lignes.append([lat, lon, v])
    return lignes


def en_lignes_sst(spec):
    """Vue tableau d'une carte SST: grille a 2 deg (la grille native ferait
    700 000 lignes)."""
    import numpy as np
    d = spec["donnees"]
    z = centroides(d["phase"])[d["indice_cluster"]]
    lats, lons = axes_sst()
    lignes = [["latitude", "longitude", "anomalie SST (degC)"]]
    for i in range(0, 480, 8):
        for j in range(0, 1440, 8):
            v = z[i, j]
            if not np.isnan(v):
                lignes.append([round(float(lats[i]), 3), round(float(lons[j]), 3),
                               round(float(v), 3)])
    return lignes


# =============================================================================
# Animation SST avant un evenement (scripts/17_build_jarvis_sst_evenements.py)
# =============================================================================
ANIMATION = PROJECT_DIR / "jarvis" / "cartes" / "sst_evenements.npz"


@lru_cache(maxsize=1)
def animations():
    """Archive des evenements animables: images int8, boites, dates."""
    import numpy as np
    try:
        z = np.load(ANIMATION, allow_pickle=False)
    except OSError as exc:
        raise CarteIndisponible("Archive SST des evenements absente: %s" % exc)
    dates = [str(d) for d in z["dates"]]
    return {
        "images": z["images"], "lats": z["lats"], "lons": z["lons"],
        "dates": dates, "index": {d: i for i, d in enumerate(dates)},
        "phases": [str(p) for p in z["phases"]],
        "rangs": [int(r) for r in z["rangs"]],
        "decalages": [int(d) for d in z["decalages"]],
        "echelle": float(z["echelle"]),
        "boites": z["boites"], "noms_boites": [str(n) for n in z["noms_boites"]],
    }


def images_evenement(date):
    """(images degC, NaN sur les terres) de l'evenement: (n_images, lat, lon)."""
    import numpy as np
    a = animations()
    i = a["index"].get(date)
    if i is None:
        raise CarteIndisponible("Evenement non anime: %s" % date)
    brut = a["images"][i].astype("float32")
    brut[a["images"][i] == -128] = np.nan
    return brut / a["echelle"]


def rendre_animation(spec, theme):
    """GIF anime: l'ocean de J-150 au jour de l'evenement.

    Les elements fixes (terres, boites, legende) sont dessines une fois; seule
    la grille change d'une image a l'autre (set_array), sinon le rendu de 11
    images prendrait une dizaine de secondes.
    """
    import io
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.figure import Figure as FigureMpl
    from matplotlib.patches import Rectangle
    from PIL import Image

    s = STYLES.get(theme, STYLES["clair"])
    d = spec["donnees"]
    a = animations()
    images = images_evenement(d["date"])
    vlim = d["vlim"]

    # Bande de 72 x 360 degres: une figure basse, sans marge perdue.
    fig = FigureMpl(figsize=(7.4, 2.35), dpi=130, facecolor=s["fond"])
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0.055, 0.3, 0.93, 0.66])
    _axes_geo(ax, s, range(-150, 181, 30), range(-30, 31, 15))
    maille = ax.pcolormesh(a["lons"], a["lats"], images[0], cmap=_carte_couleurs(s["sst"]),
                           norm=TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim),
                           shading="nearest", zorder=1)
    _polygones(ax, fond()["terres"], facecolor=s["terre"], edgecolor=s["cote"],
               linewidth=0.35, zorder=2)
    for nom, lon0, lon1, lat0, lat1 in BOITES:
        ax.add_patch(Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0, fill=False,
                               edgecolor=s["boite"], linewidth=0.55,
                               linestyle=(0, (3, 2)), zorder=3, alpha=0.85))
        if lon0 != -180:
            ax.text(lon0 + 1, lat1 + 1.2, nom, fontsize=5.2, color=s["texte"],
                    zorder=4, path_effects=_halo(s))
    ax.plot(*DAKAR, marker="*", markersize=8, color=s["accent"],
            markeredgecolor=s["halo"], markeredgewidth=0.6, zorder=5)
    ax.set_xlim(-180, 180)
    ax.set_ylim(float(a["lats"][0]) - 0.5, float(a["lats"][-1]) + 0.5)
    ax.set_aspect("equal")
    cax = fig.add_axes([0.62, 0.17, 0.3, 0.035])
    barre = fig.colorbar(maille, cax=cax, orientation="horizontal")
    barre.outline.set_visible(False)
    barre.ax.tick_params(colors=s["texte2"], length=0, labelsize=6)
    barre.set_label("anomalie de SST (°C)", color=s["texte2"], fontsize=6.5)

    # Frise: ou en est-on entre J-150 et le jour de l'evenement.
    frise = fig.add_axes([0.06, 0.085, 0.46, 0.028])
    frise.set_xlim(a["decalages"][0], 0)
    frise.set_ylim(0, 1)
    frise.axis("off")
    frise.axhspan(0, 1, color=s["grille"])
    avance = frise.add_patch(Rectangle((a["decalages"][0], 0), 0, 1, color=s["accent"]))
    etiquette = fig.text(0.06, 0.14, "", fontsize=8, fontweight="bold", color=s["texte"])

    trames = []
    for k, dec in enumerate(a["decalages"]):
        maille.set_array(images[k].ravel())
        avance.set_width(dec - a["decalages"][0])
        etiquette.set_text("J%s  ·  %s" % ("%+d" % dec if dec else "-0 (jour de l'événement)",
                                           _date_decalee(d["date"], dec)))
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        trames.append(Image.fromarray(rgba[..., :3].copy()).convert(
            "P", palette=Image.ADAPTIVE, colors=255))
    tampon = io.BytesIO()
    durees = [700] * (len(trames) - 1) + [2200]
    trames[0].save(tampon, format="GIF", save_all=True, append_images=trames[1:],
                   duration=durees, loop=0, disposal=1, optimize=False)
    return tampon.getvalue()


def _date_decalee(date, jours):
    import datetime
    return (datetime.date.fromisoformat(date) + datetime.timedelta(days=jours)).isoformat()


def en_lignes_animation(spec):
    """Vue tableau: la moyenne de chaque boite d'indice, image par image."""
    a = animations()
    i = a["index"][spec["donnees"]["date"]]
    lignes = [["jours_avant_evenement", "date"] + ["%s (degC)" % n for n in a["noms_boites"]]]
    for k, dec in enumerate(a["decalages"]):
        lignes.append([dec, _date_decalee(spec["donnees"]["date"], dec)]
                      + [round(float(v), 3) for v in a["boites"][i][k]])
    return lignes
