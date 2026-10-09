#!/usr/bin/env python3
"""Shared utilities for the ClimatSen dashboard — loaders, helpers, palette."""
import io
import os
import subprocess
import sys
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import importlib.util as _iutil
HAS_CARTOPY = _iutil.find_spec("cartopy") is not None

# ─── Static palette constants ──────────────────────────────────────────────────
INDIGO  = "#4F46E5"
BLUE    = "#0EA5E9"
EMERALD = "#10B981"
AMBER   = "#F59E0B"
ROSE    = "#F43F5E"
SIDEBAR_BG = "#1D1864"
PHASE_C = {"Phase_1_debut": BLUE, "Phase_2_pleine": INDIGO, "Phase_3_fin": AMBER}
PHASE_L = {"Phase_1_debut": "Début Mai-Jun", "Phase_2_pleine": "Pleine Jul-Août", "Phase_3_fin": "Fin Sep-Oct"}


# --- Fond de carte (sans cle API) --------------------------------------------
# "carto-positron" passe par les tuiles CARTO, qui exigent desormais une cle API
# et renvoient sinon des tuiles filigranees "API KEY REQUIRED".
# Styles utilisables sans cle :
#   "white-bg"        aucun appel reseau, fond blanc (les contours departements
#                     et le trait de cote sont deja dessines depuis les geojson)
#   "esri-gray"       tuiles Esri World Light Gray, rendu proche de positron
#   "open-street-map" tuiles OSM (fond plus charge)
BASEMAP_STYLE = "white-bg"

_ESRI_GRAY_TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
    "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
)


def basemap(center_lat, center_lon, zoom, style=None, dark=False):
    """Configuration de carte MapLibre (layout `map`) sans cle API (voir BASEMAP_STYLE).

    Les traces sont des go.Scattermap / go.Densitymap : go.Scattermapbox a ete
    retire dans Plotly 7 (suivi de revue 28/09/2026, point S1).

    dark=True : fond de la couleur des cartes du theme sombre au lieu du blanc
    (revue 27/09/2026, point 15), toujours sans appel reseau.
    """
    style = style or BASEMAP_STYLE
    center = dict(lat=center_lat, lon=center_lon)
    if style == "white-bg" and dark:
        # Calque plein sous les traces plutot qu'un style MapLibre ecrit a la
        # main : ce dernier levait "Map error." dans le navigateur (constate en
        # production le 29/09/2026 apres le passage a go.Scattermap).
        monde = {"type": "Feature", "properties": {}, "geometry": {
            "type": "Polygon",
            "coordinates": [[[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]]}}
        return dict(
            style="white-bg",
            layers=[dict(sourcetype="geojson", source=monde, type="fill",
                         color="#1E293B", below="traces")],
            center=center, zoom=zoom)
    if style == "esri-gray":
        return dict(
            style="white-bg",
            layers=[dict(
                below="traces",
                sourcetype="raster",
                source=[_ESRI_GRAY_TILES],
                sourceattribution="Esri, HERE, Garmin, FAO, NOAA, USGS",
            )],
            center=center,
            zoom=zoom,
        )
    return dict(style=style, center=center, zoom=zoom)


# Vue par defaut des cartes du Senegal : TOUT le pays, centre sur sa boite
# (12,3-16,7 N / 17,55-11,35 W). Zoom 5,65 : le pays entier tient dans la
# colonne de ~510 px x 440 px (tuiles de 512 px : 2^z >= 510*360/(512*7)).
# Revue de Laity 27/09/2026 : la carte etait centree sur l'evenement (zoom
# 6,2) et coupait Dakar et le nord.
SENEGAL_CENTRE = (14.5, -14.45)
SENEGAL_ZOOM = 5.65

# Plotly zoome de x1,05 par clic sur "+"/"-" (invisible a cette echelle) :
# on retire ces boutons, la molette / le pincement zooment, "Reset view"
# recentre sur le pays.
CARTE_CONFIG = {
    "displayModeBar": True,
    "scrollZoom": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d",
                               "hoverClosestMap", "zoomInMap", "zoomOutMap",
                               "hoverClosestMapbox", "zoomInMapbox", "zoomOutMapbox"],
}


def get_palette(dark_mode: bool) -> dict:
    if dark_mode:
        return dict(BG="#0F172A", CARD="#1E293B", TEXT="#F1F5F9",
                    MUTED="#94A3B8", BORDER="#334155")
    return dict(BG="#F1F5F9", CARD="#FFFFFF", TEXT="#0F172A",
                MUTED="#64748B", BORDER="#E2E8F0")


# ─── BASE path ────────────────────────────────────────────────────────────────
_script_dir = Path(__file__).resolve().parent.parent
BASE = _script_dir if (_script_dir / "data" / "processed").exists() \
    else Path("c:/Users/laity/Desktop/Memoire Master/Memoire/Traitement01")


# ─── Loaders ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_events():
    df = pd.read_csv(BASE / "data/processed/extreme_events_phases_senegal.csv", encoding="utf-8")
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data
def load_telecon():
    files = {
        "Phase_1_debut":  BASE / "outputs/teleconnections/correlations_Phase_1_debut.csv",
        "Phase_2_pleine": BASE / "outputs/teleconnections/correlations_Phase_2_pleine.csv",
        "Phase_3_fin":    BASE / "outputs/teleconnections/correlations_Phase_3_fin.csv",
        "Toutes phases":  BASE / "outputs/teleconnections/correlations_Toutes phases.csv",
    }
    return {k: pd.read_csv(p, encoding="utf-8") for k, p in files.items() if p.exists()}


def _sig_from_p_neff(p) -> str:
    """Etoiles AR1 (memes seuils que _sig() dans 04_teleconnections_analysis)."""
    try:
        if p is None or pd.isna(p):
            return ""
        pv = float(p)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(pv):
        return ""
    if pv < 0.001:
        return "***"
    if pv < 0.01:
        return "**"
    if pv < 0.05:
        return "*"
    return ""


@st.cache_data
def load_sst():
    df = pd.read_csv(
        BASE / "data/raw/climate_indices/daily_indices_all.csv",
        encoding="utf-8",
    )
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data
def load_events_pixels():
    p = BASE / "outputs/specific_events_qgis/all_specific_events_pixels.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")


@st.cache_data
def load_events_summary():
    p = BASE / "outputs/specific_events_qgis/events_summary_statistics.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")


@st.cache_data
def load_cluster_pixels():
    p = BASE / "outputs/cluster_events_qgis/all_cluster_events_combined.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")


@st.cache_data
def load_dept_geojson():
    import json
    p = BASE / "data/geographic/senegal_departments.geojson"
    if not p.exists():
        return None
    with open(str(p), "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Module Vulnerabilite (scripts 26, 27, 28) ────────────────────────────────
# Une seule lecture pour la page Vulnerabilite et l'outil Jarvis
# get_priority_zones : les deux affichent donc les memes chiffres.
VULNERABILITE = BASE / "outputs" / "vulnerabilite"


@st.cache_data(ttl=300)
def load_vulnerabilite():
    """{"departements": DataFrame, "arrondissements": DataFrame ou None,
    "resume": dict, "resume_arrondissements": dict ou None}, ou None si le
    script 26 n'a pas tourne."""
    import json
    dep = VULNERABILITE / "indice_risque_departements.csv"
    if not dep.exists():
        return None

    def _json(nom):
        p = VULNERABILITE / nom
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _csv(chemin):
        return pd.read_csv(chemin, encoding="utf-8") if chemin.exists() else None

    arr = VULNERABILITE / "indice_risque_arrondissements.csv"
    ansd = BASE / "data" / "raw" / "ansd"
    return {
        "departements": pd.read_csv(dep, encoding="utf-8"),
        "arrondissements": _csv(arr),
        "resume": _json("resume.json") or {},
        "resume_arrondissements": _json("resume_arrondissements.json"),
        # Script 29 : sensibilite aux poids et validation contre les inondations.
        "robustesse": _json("robustesse/resume.json"),
        "robustesse_auc": _csv(VULNERABILITE / "robustesse" / "validation_auc_departements.csv"),
        # Transcriptions EHCVM 2021-2022 par region (rapport final ANSD).
        "ehcvm_assainissement": _csv(ansd / "ehcvm_2021-2022_assainissement_par_region.csv"),
        "ehcvm_services": _csv(ansd / "ehcvm_2021-2022_services_chocs_par_region.csv"),
    }


@st.cache_data
def load_contours_simplifies(niveau):
    """Contours alleges (script 28) : niveau "admin2" ou "admin3". None si absent."""
    import json
    p = BASE / "data" / "processed" / ("contours_%s_simplifies.geojson" % niveau)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


EXPOSITION = BASE / "outputs" / "exposition_evenements"


@st.cache_data(ttl=300)
def load_population_touchee():
    """Habitants (RGPH-5 2023) des zones touchees par chaque evenement (script 33).

    DataFrame indexe par la date "AAAA-MM-JJ", ou None si le script n'a pas tourne.
    Lu par la fiche evenement ; a lire aussi par IRIS pour annoncer les memes chiffres.
    """
    p = EXPOSITION / "population_touchee_evenements.csv"
    if not p.exists():
        return None
    t = pd.read_csv(p, encoding="utf-8").set_index("date")
    # Memes pixels, population projetee par l'ANSD pour 2026 et 2030 (script 37).
    proj = EXPOSITION / "population_touchee_projetee.csv"
    if proj.exists():
        q = pd.read_csv(proj, encoding="utf-8").set_index("date")
        t = t.join(q[[c for c in q.columns if c.endswith(("_2026", "_2030"))]])
    return t


def code_commune(adm2_pcode, nom):
    """Identifiant d'une commune, comme l'API ouverte : P-code du departement +
    nom ANSD normalise (SN0101_NGOR)."""
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode()
    return "%s_%s" % (adm2_pcode, re.sub(r"[^A-Z0-9]", "", s.upper()))


@st.cache_data(ttl=300)
def load_saisons_recentes():
    """Saisons recentes (script 40) : (evenements, annees, resume), ou None.

    Evenements depuis 2024 detectes avec la climatologie de reference 1981-2023 ;
    le catalogue de l'etude n'est pas modifie. Colonne `source` : definitif ou
    preliminaire (CHIRPS publie d'abord une version provisoire)."""
    import json
    d = BASE / "outputs" / "saisons_recentes"
    fichiers = [d / "evenements_recents.csv", d / "annees_recentes.csv", d / "resume.json"]
    if not all(f.exists() for f in fichiers):
        return None
    ev = pd.read_csv(fichiers[0], encoding="utf-8", parse_dates=["date"])
    an = pd.read_csv(fichiers[1], encoding="utf-8")
    return ev, an, json.loads(fichiers[2].read_text(encoding="utf-8"))


@st.cache_data(ttl=300)
def load_pauvrete_ansd():
    """Pauvrete par region lue par l'API SDMX de l'ANSD (DF_TX_PAUV, script 35) :
    {P-code de region (SN07): {"taux", "profondeur", "severite"}} pour 2022, plus
    "taux_2011" et "taux_2019". None si les fichiers manquent."""
    odp = BASE / "data" / "raw" / "ansd" / "odp" / "DF_TX_PAUV.csv"
    corr = BASE / "data" / "processed" / "correspondance_zones_ansd.csv"
    if not (odp.exists() and corr.exists()):
        return None
    p = pd.read_csv(odp, sep=None, engine="python", dtype=str)
    c = pd.read_csv(corr, dtype=str)
    region = dict(zip(c.loc[c["niveau"] == "region", "code_ansd"],
                      c.loc[c["niveau"] == "region", "code_climatsen"]))
    noms = {"T_PAUV": "taux", "P_PAUV": "profondeur", "S_PAUV": "severite"}
    out = {}
    for r in p.itertuples():
        pc = region.get(r.REF_AREA)
        if pc is None:
            continue
        cle = noms[r.TX_PAUV] if r.TIME_PERIOD == "2022" else (
            "taux_" + r.TIME_PERIOD if r.TX_PAUV == "T_PAUV" else None)
        if cle:
            out.setdefault(pc, {})[cle] = float(r.OBS_VALUE)
    return out


@st.cache_data(ttl=300)
def load_population_projetee():
    """Population projetee par l'ANSD (2023, 2026, 2030) des departements et
    communes de ClimatSen (script 37, API SDMX de l'ANSD). DataFrame indexe par
    code (SN0703, SN0101_NGOR), ou None si absent."""
    p = EXPOSITION / "population_projetee_zones.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8").set_index("code")


@st.cache_data(ttl=300)
def load_communes_reconstruites():
    """Contours approximatifs des 552 communes et indicateurs RGPH-5 (script 34).

    GeoJSON (dict) ou None si absent.
    """
    import json
    p = BASE / "data" / "processed" / "communes_reconstruites_ansd.geojson"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ─── Short-path helper (handles accented Windows paths for NetCDF4) ───────────
import ctypes as _ctypes
from ctypes import wintypes as _wt


def _short_path(long_path: str) -> str:
    try:
        k32 = _ctypes.windll.kernel32
        k32.GetShortPathNameW.argtypes = [_wt.LPCWSTR, _wt.LPWSTR, _wt.DWORD]
        k32.GetShortPathNameW.restype  = _wt.DWORD
        buf = _ctypes.create_unicode_buffer(512)
        if k32.GetShortPathNameW(long_path, buf, 512) > 0:
            return buf.value
    except Exception:
        pass
    return long_path


# ─── SST day loader via NOAA ERDDAP ──────────────────────────────────────────
_ERDDAP_BASE = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/"
    "ncdcOisst21Agg_LonPM180.nc"
)


@st.cache_data(show_spinner=False)
def load_sst_day(year: int, doy: int):
    """Fetch SST anom (lat 60S-60N) via NOAA ERDDAP. Returns (lats, lons, anom) or (None, None, None)."""
    import requests
    import io
    import xarray as _xr
    from datetime import datetime, timedelta

    date_str = (
        datetime(year, 1, 1) + timedelta(days=doy - 1)
    ).strftime("%Y-%m-%dT12:00:00Z")

    url = (
        _ERDDAP_BASE
        + f"?anom[({date_str}):1:({date_str})]"
        + "[0:1:0]"
        + "[(-60):1:(60)]"
        + "[(-179.875):1:(179.875)]"
    )

    try:
        resp = requests.get(url, timeout=45)
        resp.raise_for_status()
        ds   = _xr.open_dataset(io.BytesIO(resp.content))
        lats = ds["latitude"].values
        lons = ds["longitude"].values
        anom = ds["anom"].values[0, 0]
        ds.close()
        return lats[::4], lons[::4], anom[::4, ::4]
    except Exception:
        return None, None, None


@st.cache_data(show_spinner=False)
def load_sst_centroid(phase: str):
    """Return (n_clusters, 480, 1440) centroid SST array + lat/lon arrays."""
    npy_file = BASE / "outputs/clustering" / phase / f"{phase}_centroids_sst.npy"
    if not npy_file.exists():
        return None, None, None
    sp = _short_path(str(npy_file))
    centroids = np.load(sp)
    n_clust   = centroids.shape[0]
    full_lats = np.linspace(-59.875, 59.875, 480)
    full_lons = np.linspace(-179.875, 179.875, 1440)
    centroids_2d = centroids.reshape(n_clust, 480, 1440)
    return centroids_2d, full_lats, full_lons


@st.cache_data(show_spinner=False)
def _render_centroid_cartopy(z_bytes: bytes, lats_bytes: bytes, lons_bytes: bytes,
                              title: str, vlim: float) -> bytes:
    """Rendu matplotlib/cartopy d'une carte SST centroide. Retourne PNG bytes."""
    z    = np.frombuffer(z_bytes,    dtype=np.float64).reshape(480, 1440)
    lats = np.frombuffer(lats_bytes, dtype=np.float64)
    lons = np.frombuffer(lons_bytes, dtype=np.float64)

    if HAS_CARTOPY:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

    fig = plt.figure(figsize=(14, 5), dpi=150)
    if HAS_CARTOPY:
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
        ax.set_extent([-180, 180, -60, 60], crs=ccrs.PlateCarree())
        im = ax.pcolormesh(
            lons, lats, z,
            cmap="RdBu_r", vmin=-vlim, vmax=vlim,
            transform=ccrs.PlateCarree(),
            rasterized=True,
        )
        ax.add_feature(cfeature.LAND,   facecolor="#D6D6D6", zorder=2)
        ax.add_feature(cfeature.OCEAN,  facecolor="none",    zorder=1)
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor="#555555", zorder=3)
        ax.add_feature(cfeature.BORDERS,   linewidth=0.3, edgecolor="#888888", zorder=3)
        gl = ax.gridlines(draw_labels=True, linewidth=0.4, color="#AAAAAA",
                          linestyle="--", zorder=4)
        gl.top_labels   = False
        gl.right_labels = False
        gl.xlocator = mticker.FixedLocator(range(-180, 181, 30))
        gl.ylocator = mticker.FixedLocator(range(-60, 61, 15))
        gl.xlabel_style = {"size": 9}
        gl.ylabel_style = {"size": 9}
        ax.plot(-17.4, 14.7, marker="*", color=AMBER, markersize=12,
                markeredgecolor="white", markeredgewidth=0.8,
                transform=ccrs.PlateCarree(), zorder=5)
        ax.text(-14.5, 15.5, "Dakar", fontsize=8, color="#0F172A",
                transform=ccrs.PlateCarree(), zorder=5)
    else:
        ax = fig.add_subplot(1, 1, 1)
        im = ax.pcolormesh(lons, lats, z, cmap="RdBu_r", vmin=-vlim, vmax=vlim,
                           rasterized=True)
        ax.set_xlim(-180, 180)
        ax.set_ylim(-60, 60)
        ax.set_xlabel("Longitude", fontsize=9)
        ax.set_ylabel("Latitude",  fontsize=9)
        ax.plot(-17.4, 14.7, marker="*", color=AMBER, markersize=10,
                markeredgecolor="white", markeredgewidth=0.8)

    cbar = fig.colorbar(im, ax=ax, orientation="vertical", pad=0.02,
                        fraction=0.025, aspect=30)
    cbar.set_label("Anomalie SST (degC)", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    ax.set_title(title, fontsize=11, fontweight="bold", color="#0F172A", pad=8)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#C8E6FA")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="#FFFFFF", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


@st.cache_data
def load_clustering():
    phases = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin", "All_phases"]
    out = {}
    for ph in phases:
        d = BASE / "outputs/clustering" / ph
        chars_f   = d / f"{ph}_cluster_characteristics.csv"
        events_f  = d / f"{ph}_events_with_clusters.csv"
        metrics_f = d / f"{ph}_kmeans_evaluation_metrics.json"
        k3_f      = d / f"{ph}_tableau_k_3_methodes.csv"
        k4_f      = d / f"{ph}_tableau_k_4_methodes.csv"
        if not chars_f.exists():
            continue
        import json as _json
        chars  = pd.read_csv(chars_f, encoding="utf-8")
        events = pd.read_csv(events_f, encoding="utf-8")
        events["date"] = pd.to_datetime(events["date"])
        with open(metrics_f, encoding="utf-8") as fh:
            metrics = _json.load(fh)
        k3 = pd.read_csv(k3_f, encoding="utf-8-sig") if k3_f.exists() else None
        k4 = pd.read_csv(k4_f, encoding="utf-8-sig") if k4_f.exists() else None
        out[ph] = {"chars": chars, "events": events, "metrics": metrics, "k3": k3, "k4": k4}
    return out


# ─── Traces géographiques Plotly (côtes + terres) ────────────────────────────
@st.cache_data(show_spinner=False)
def _build_geo_traces():
    if not HAS_CARTOPY:
        return []
    import cartopy.io.shapereader as shpreader
    traces = []

    def _extract_polys(shp_path):
        reader = shpreader.Reader(shp_path)
        xs, ys = [], []
        for geom in reader.geometries():
            polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
            for poly in polys:
                cx, cy = zip(*poly.exterior.coords)
                xs.extend(list(cx) + [None])
                ys.extend(list(cy) + [None])
        # Tableaux NumPy (NaN = coupure, serialise en null) : une liste Python
        # est validee par Plotly point par point, ~3 s par carte (recette
        # 29/09/2026).
        return np.array(xs, dtype=float), np.array(ys, dtype=float)

    try:
        land_shp = shpreader.natural_earth(
            resolution="110m", category="physical", name="land")
        lx, ly = _extract_polys(land_shp)
        traces.append(dict(
            type="scatter", x=lx, y=ly, mode="lines",
            fill="toself", fillcolor="rgba(210,210,210,0.95)",
            line=dict(color="rgba(80,80,80,0.6)", width=0.4),
            showlegend=False, hoverinfo="skip", name="_land",
        ))
    except Exception:
        pass

    try:
        brd_shp = shpreader.natural_earth(
            resolution="110m", category="cultural", name="admin_0_countries")
        bx, by = _extract_polys(brd_shp)
        traces.append(dict(
            type="scatter", x=bx, y=by, mode="lines",
            line=dict(color="rgba(100,100,100,0.45)", width=0.3),
            showlegend=False, hoverinfo="skip", name="_borders",
        ))
    except Exception:
        pass

    return traces


_SST_REGIONS = [
    ("Nino1+2",   -90,    -80,    -10,   0,    False),
    ("Nino3",     -150,   -90,    -5,    5,    False),
    ("Nino3.4",   -170,   -120,   -5,    5,    False),
    ("Nino4",      160,   210,    -5,    5,    True ),
    ("ATL3",       -20,    0,     -3,    3,    False),
    ("TNA",        -55,   -15,     5,   23,    False),
    ("TSA",        -30,    10,   -20,    0,    False),
    ("AMO",        -80,     0,     0,   60,    False),
    ("IOD-W",       50,    70,   -10,   10,    False),
    ("IOD-E",       90,   110,   -10,    0,    False),
    ("IOBM",        40,   100,   -20,   20,    False),
]


@st.cache_data(show_spinner=False)
def _get_region_grid(lats_t, lons_t):
    lats = np.array(lats_t)
    lons = np.array(lons_t)
    names = np.full((len(lats), len(lons)), "", dtype=object)
    for rname, lon0, lon1, lat0, lat1, straddle in _SST_REGIONS:
        lat_mask = (lats >= lat0) & (lats <= lat1)
        if straddle:
            lon_mask = (lons >= lon0) | (lons <= (lon1 - 360))
        else:
            lon_mask = (lons >= lon0) & (lons <= lon1)
        grid_mask = np.ix_(lat_mask, lon_mask)
        existing = names[grid_mask]
        names[grid_mask] = np.where(
            existing == "", rname, existing.astype(str) + " / " + rname
        )
    return names


def _apply_geo_traces(fig):
    for td in _build_geo_traces():
        fig.add_trace(go.Scatter(
            x=td["x"], y=td["y"], mode=td["mode"],
            fill=td.get("fill", "none"),
            fillcolor=td.get("fillcolor", "rgba(0,0,0,0)"),
            line=td["line"],
            showlegend=td["showlegend"],
            hoverinfo=td["hoverinfo"],
            name=td["name"],
        ))


# ─── Nombres au format francais ──────────────────────────────────────────────
# Recette 29/09/2026 : "1,317 evenements" et "0.171" cotoyaient "r = -0,42".
# Partout : virgule decimale, espace fine insecable pour les milliers.
def nb(v, fmt=".1f"):
    """Formate v comme format(v, fmt), a la francaise (1 317 ; -0,42)."""
    return format(v, fmt).replace(",", " ").replace(".", ",")


_plotly_chart_st = st.plotly_chart


def _plotly_chart_fr(fig, *args, **kwargs):
    """st.plotly_chart avec separateurs francais (axes, infobulles) par defaut."""
    try:
        if fig.layout.separators is None:
            fig.update_layout(separators=", ")
    except AttributeError:
        pass
    return _plotly_chart_st(fig, *args, **kwargs)


if getattr(st.plotly_chart, "__name__", "") != "_plotly_chart_fr":
    st.plotly_chart = _plotly_chart_fr


# ─── Visual helpers ───────────────────────────────────────────────────────────
def svg_spark(vals, w=100, h=40, color=INDIGO):
    v = [x for x in vals if pd.notna(x)]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = hi - lo if hi != lo else 1
    PAD = 3
    def pt(i, val):
        x = i / (len(v) - 1) * w
        y = h - PAD - (val - lo) / rng * (h - 2 * PAD)
        return f"{x:.1f},{y:.1f}"
    pts      = " ".join(pt(i, x) for i, x in enumerate(v))
    fill_pts = f"0,{h} {pts} {w},{h}"
    uid = abs(hash(f"{color}{v[0]}{len(v)}")) % 100000
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display:block;overflow:visible">'
        f'<defs><linearGradient id="sg{uid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.3"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{fill_pts}" fill="url(#sg{uid})"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"'
        f' stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def couleur_sur_fond(v, zmin, zmax, colorscale, clair="#FFFFFF", fonce="#0F172A"):
    """Couleur de texte lisible sur la cellule de valeur v (luminance du fond)."""
    from plotly.colors import sample_colorscale
    pos = min(1.0, max(0.0, (float(v) - zmin) / ((zmax - zmin) or 1.0)))
    r, g, b = (float(c) for c in sample_colorscale(colorscale, [pos])[0]
               .strip("rgb()").split(","))
    return fonce if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.55 else clair


def textes_cellules(fig, x, y, textes, z, zmin, zmax, colorscale, size=10,
                    clair="#FFFFFF", fonce="#0F172A"):
    """Chiffres d'une carte de chaleur, lisibles sur toutes les cellules.

    Le contraste automatique de Plotly laissait des chiffres blancs sur les
    cellules claires (+0,01, -0,03) : la couleur est calculee ici cellule par
    cellule d'apres la luminance du fond (suivi de revue 28/09/2026, point 14).
    Trace texte superposee (go.Scatter), sans survol : la carte garde le sien.
    """
    xs, ys, tx, couleurs = [], [], [], []
    for ri, yv in enumerate(y):
        for ci, xv in enumerate(x):
            v, txt = z[ri][ci], textes[ri][ci]
            if v is None or txt in (None, "") or not np.isfinite(v):
                continue
            xs.append(xv); ys.append(yv); tx.append(txt)
            couleurs.append(couleur_sur_fond(v, zmin, zmax, colorscale, clair, fonce))
    fig.add_trace(go.Scatter(x=xs, y=ys, text=tx, mode="text",
                             textfont=dict(size=size, color=couleurs),
                             hoverinfo="skip", showlegend=False))
    return fig


def plotly_base(fig, h=300, muted="#64748B", border="#E2E8F0", text="#0F172A", card="#FFFFFF"):
    fig.update_layout(
        height=h,
        autosize=True,
        margin=dict(l=2, r=2, t=10, b=2),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,sans-serif", size=11, color=muted),
        # automargin : une etiquette longue ("Nino34", "Debut Mai-Jun") agrandit la
        # marge au lieu d'etre coupee (revue 27/09/2026, point 12).
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=11, color=muted),
                   automargin=True),
        yaxis=dict(showgrid=True, gridcolor=border, zeroline=False, tickfont=dict(size=11, color=muted),
                   automargin=True),
        hoverlabel=dict(bgcolor=card, font_color=text, font_size=12, bordercolor=border),
        legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center",
                    bgcolor="rgba(0,0,0,0)", borderwidth=0, font=dict(size=11, color=muted)),
    )
    return fig
