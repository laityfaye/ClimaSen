#!/usr/bin/env python3
"""
Dashboard Pro - Precipitations Extremes Senegal
Usage: streamlit run scripts/dashboard.py
"""
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

# ─── Config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SenRain · Dashboard",
    page_icon="🌧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Anti-FOUC : applique le fond sombre immediatement depuis l'URL ──────────
# Evite le flash blanc lors d'une navigation ou d'un rafraichissement en mode sombre.
# Le script lit ?dm=1 dans l'URL et injecte la couleur de fond avant tout rendu.
st.markdown("""
<script>
(function () {
  try {
    if (new URLSearchParams(window.location.search).get('dm') === '1') {
      var s = document.createElement('style');
      s.id = 'dm-preload';
      s.textContent =
        'html,body,[data-testid="stApp"],' +
        '[data-testid="stAppViewContainer"],' +
        '[data-testid="stAppViewContainer"]>.main,' +
        '[data-testid="stMainBlockContainer"],' +
        '.block-container{background:#0F172A!important;color:#F1F5F9!important}';
      (document.head || document.documentElement).appendChild(s);
    }
  } catch (e) {}
})();
</script>
""", unsafe_allow_html=True)

# ─── Palette ─────────────────────────────────────────────────────────────────
INDIGO  = "#4F46E5"
BLUE    = "#0EA5E9"
EMERALD = "#10B981"
AMBER   = "#F59E0B"
ROSE    = "#F43F5E"
BG      = "#F1F5F9"
CARD    = "#FFFFFF"
TEXT    = "#0F172A"
MUTED   = "#64748B"
BORDER  = "#E2E8F0"
SIDEBAR_BG = "#1D1864"

PHASE_C = {"Phase_1_debut": BLUE, "Phase_2_pleine": INDIGO, "Phase_3_fin": AMBER}
PHASE_L = {"Phase_1_debut": "Debut Mai-Jun", "Phase_2_pleine": "Pleine Jul-Aou", "Phase_3_fin": "Fin Sep-Oct"}

# ─── Dark mode state ─────────────────────────────────────────────────────────
# Priorite : session_state (navigation interne) > query_params (refresh/nouvel onglet)
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = (st.query_params.get("dm", "0") == "1")

# ─── Page transition state ────────────────────────────────────────────────────
if "prev_page" not in st.session_state:
    st.session_state.prev_page = None
if "page_loading" not in st.session_state:
    st.session_state.page_loading = False

# Palette dynamique (light / dark)
if st.session_state.dark_mode:
    BG    = "#0F172A"
    CARD  = "#1E293B"
    TEXT  = "#F1F5F9"
    MUTED = "#94A3B8"
    BORDER = "#334155"
else:
    BG    = "#F1F5F9"
    CARD  = "#FFFFFF"
    TEXT  = "#0F172A"
    MUTED = "#64748B"
    BORDER = "#E2E8F0"

# ─── Data ────────────────────────────────────────────────────────────────────
# BASE = chemin absolu local (dev) ou relatif au script (deploy)
_script_dir = Path(__file__).resolve().parent.parent  # remonte de scripts/ vers Traitement01/
BASE = _script_dir if (_script_dir / "data" / "processed").exists() \
    else Path("c:/Users/laity/Desktop/Mémoire Master/Mémoire/Traitement01")

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
    """Charge les pixels des evenements specifiques pour cartographie."""
    p = BASE / "outputs/specific_events_qgis/all_specific_events_pixels.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")

@st.cache_data
def load_events_summary():
    """Charge le resume statistique des evenements specifiques."""
    p = BASE / "outputs/specific_events_qgis/events_summary_statistics.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")

@st.cache_data
def load_cluster_pixels():
    """Charge les pixels des evenements representatifs par cluster."""
    p = BASE / "outputs/cluster_events_qgis/all_cluster_events_combined.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")

@st.cache_data
def load_dept_geojson():
    """Charge le GeoJSON des departements du Senegal."""
    import json
    p = BASE / "data/geographic/senegal_departments.geojson"
    if not p.exists():
        return None
    with open(str(p), "r", encoding="utf-8") as f:
        return json.load(f)

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

# ─── SST day loader via NOAA ERDDAP (zero stockage local) ────────────────────
# Source : OISST v2.1 — coastwatch.pfeg.noaa.gov/erddap
# Dataset : ncdcOisst21Agg_LonPM180 (1981-09-01 a aujourd'hui, 0.25 deg)
_ERDDAP_BASE = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/"
    "ncdcOisst21Agg_LonPM180.nc"
)

@st.cache_data(show_spinner=False)
def load_sst_day(year: int, doy: int):
    """Fetch SST anom (lat 60S-60N) pour un jour donne via NOAA ERDDAP OISST v2.1.
    Retourne (lats, lons, anom) downsamples 4x (~120x360), ou (None, None, None).
    """
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
        anom = ds["anom"].values[0, 0]  # (nlat, nlon)
        ds.close()
        # downsample 4x -> ~120x360 pour rendu rapide (identique a l'ancienne logique)
        return lats[::4], lons[::4], anom[::4, ::4]
    except Exception:
        return None, None, None

@st.cache_data(show_spinner=False)
def load_sst_centroid(phase: str):
    """Return (n_clusters, 480, 1440) centroid SST array + lat/lon arrays (pleine resolution)."""
    npy_file = BASE / "outputs/clustering" / phase / f"{phase}_centroids_sst.npy"
    if not npy_file.exists():
        return None, None, None
    sp = _short_path(str(npy_file))
    centroids = np.load(sp)           # (n_clust, 691200)
    n_clust   = centroids.shape[0]
    full_lats = np.linspace(-59.875, 59.875, 480)
    full_lons = np.linspace(-179.875, 179.875, 1440)
    centroids_2d = centroids.reshape(n_clust, 480, 1440)
    return centroids_2d, full_lats, full_lons


@st.cache_data(show_spinner=False)
def _render_centroid_cartopy(z_bytes: bytes, lats_bytes: bytes, lons_bytes: bytes,
                              title: str, vlim: float) -> bytes:
    """
    Rendu matplotlib/cartopy haute resolution d'une carte SST centroide.
    Retourne un buffer PNG (bytes) pour st.image.
    Les tableaux sont passes serialises (bytes) pour la compatibilite cache.
    """
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
        # Etoile Senegal (Dakar)
        ax.plot(-17.4, 14.7, marker="*", color=AMBER, markersize=12,
                markeredgecolor="white", markeredgewidth=0.8,
                transform=ccrs.PlateCarree(), zorder=5)
        ax.text(-14.5, 15.5, "Dakar", fontsize=8, color=TEXT,
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

    ax.set_title(title, fontsize=11, fontweight="bold", color=TEXT, pad=8)
    fig.patch.set_facecolor(CARD)
    ax.set_facecolor("#C8E6FA")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=CARD, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

@st.cache_data
def load_clustering():
    phases = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin", "All_phases"]
    out = {}
    for ph in phases:
        d = BASE / "outputs/clustering" / ph
        chars_f  = d / f"{ph}_cluster_characteristics.csv"
        events_f = d / f"{ph}_events_with_clusters.csv"
        metrics_f= d / f"{ph}_kmeans_evaluation_metrics.json"
        k3_f     = d / f"{ph}_tableau_k_3_methodes.csv"
        k4_f     = d / f"{ph}_tableau_k_4_methodes.csv"
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

# ─── Traces géographiques Plotly (côtes + terres) depuis cartopy shapefiles ──
@st.cache_data(show_spinner=False)
def _build_geo_traces():
    """
    Charge les polygones terre (fill gris) et frontières (lignes)
    depuis Natural Earth via cartopy.io.shapereader.
    Retourne une liste de dicts de traces Plotly (serialisable pour cache).
    Appelé une seule fois grace au cache.
    """
    if not HAS_CARTOPY:
        return []
    import cartopy.io.shapereader as shpreader
    traces = []

    def _extract_polys(shp_path):
        """Extrait x/y avec separateurs None depuis un shapefile polygones."""
        reader = shpreader.Reader(shp_path)
        xs, ys = [], []
        for geom in reader.geometries():
            polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
            for poly in polys:
                cx, cy = zip(*poly.exterior.coords)
                xs.extend(list(cx) + [None])
                ys.extend(list(cy) + [None])
        return xs, ys

    # Remplissage terre (gris clair, masque les NaN blancs)
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

    # Frontières pays (lignes fines)
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


# Définitions géographiques des régions SST (boites standard NOAA/IOBM)
_SST_REGIONS = [
    # (nom,       lon_min, lon_max, lat_min, lat_max, straddle_dateline)
    ("Nino1+2",   -90,    -80,    -10,   0,    False),
    ("Nino3",     -150,   -90,    -5,    5,    False),
    ("Nino3.4",   -170,   -120,   -5,    5,    False),
    ("Nino4",      160,   210,    -5,    5,    True ),  # 160E - 150W
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
    """
    Pour chaque point (lat, lon) retourne le nom de la region SST
    (ou chaine vide). lats_t/lons_t sont des tuples pour hashabilite.
    """
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
    """Ajoute les traces geo (terre + frontieres) a une figure Plotly."""
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


with st.spinner("Chargement des donnees en cours..."):
    df = load_events()

# ─── Viewport : detectable uniquement via CSS (media queries deja en place) ───
# Les colonnes Streamlit se stackent automatiquement via les regles CSS < 640px.
is_mobile = False
is_tablet = False

# ─── Helpers ─────────────────────────────────────────────────────────────────
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

def plotly_base(fig, h=300):
    fig.update_layout(
        height=h,
        autosize=True,
        margin=dict(l=2, r=2, t=10, b=2),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,sans-serif", size=11, color=MUTED),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=11, color=MUTED)),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False, tickfont=dict(size=11, color=MUTED)),
        hoverlabel=dict(bgcolor=TEXT, font_color="white", font_size=12, bordercolor=TEXT),
        legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center",
                    bgcolor="rgba(0,0,0,0)", borderwidth=0, font=dict(size=11)),
    )
    return fig

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── Reset ── */
*, html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif !important;
}}
[data-testid="stAppViewContainer"] > .main {{
    background: {BG} !important;
    padding: 0 28px 40px 28px !important;
}}
[data-testid="stAppViewContainer"] > .main > div:first-child {{
    padding-top: 0 !important;
    margin-top: 0 !important;
}}
.block-container, [data-testid="stMainBlockContainer"] {{
    padding-top: 0 !important;
}}
/* Header : supprime completement */
[data-testid="stHeader"] {{
    display: none !important;
}}
/* Cacher header, decoration, menu */
[data-testid="stDecoration"],
[data-testid="stToolbar"],
button[kind="header"] {{
    display: none !important;
}}
#MainMenu {{ display: none !important; }}
footer {{ display: none !important; }}

/* Sidebar collapsable (grand ecran + mobile) */
section[data-testid="stSidebar"] {{
    min-width: 260px !important;
    max-width: 260px !important;
}}
@media (max-width: 768px) {{
    section[data-testid="stSidebar"] {{
        min-width: 200px !important;
        max-width: 80vw !important;
    }}
}}

/* Bouton fermer/ouvrir sidebar : style adapte au fond sombre */
[data-testid="stSidebarCollapseButton"] {{
    background: rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
}}
[data-testid="stSidebarCollapseButton"]:hover {{
    background: rgba(255,255,255,0.15) !important;
}}
[data-testid="stSidebarCollapseButton"] svg {{
    fill: #C4C9E8 !important;
}}
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {{
    background: {SIDEBAR_BG} !important;
    border-radius: 0 8px 8px 0 !important;
}}
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="collapsedControl"] svg {{
    fill: #C4C9E8 !important;
}}

/* ════════════════════════════════
   SIDEBAR — approche minimaliste
   ════════════════════════════════ */
section[data-testid="stSidebar"] {{
    background: {SIDEBAR_BG} !important;
    padding-top: 0 !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
    background: {SIDEBAR_BG} !important;
    padding-top: 0 !important;
}}
section[data-testid="stSidebar"] > div > div:first-child,
section[data-testid="stSidebar"] > div > div > div:first-child,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    padding-top: 0 !important;
    margin-top: 0 !important;
}}
section[data-testid="stSidebar"] > div:first-child > div:first-child {{
    margin-top: -3rem !important;
}}

/* Tout le texte sidebar en gris clair par defaut */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div {{
    color: #94A3CB;
}}

/* HR */
section[data-testid="stSidebar"] hr {{
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.08) !important;
    margin: 6px 0 !important;
}}

/* ── Bouton dark mode dans sidebar ── */
section[data-testid="stSidebar"] [data-testid="stButton"] button {{
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #C4C9E8 !important;
    font-size: 1rem !important;
    padding: 2px 0 !important;
    line-height: 1 !important;
    min-height: 28px !important;
    transition: background 0.15s !important;
}}
section[data-testid="stSidebar"] [data-testid="stButton"] button:hover {{
    background: rgba(255,255,255,0.14) !important;
}}

/* ── Radio transforme en nav ── */
/* Cacher le label "nav" du groupe (stWidgetLabel) */
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stWidgetLabel"] {{
    display: none !important;
}}
/* Chaque option : cibler uniquement les labels dans le radiogroup */
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio-group"] label,
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label {{
    display: flex !important;
    align-items: center !important;
    padding: 9px 13px !important;
    margin: 1px 8px !important;
    border-radius: 9px !important;
    border-left: 3px solid transparent !important;
    cursor: pointer !important;
    transition: background 0.15s, color 0.15s !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #7A83B8 !important;
    background: transparent !important;
    width: calc(100% - 16px) !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio-group"] label:hover,
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:hover {{
    background: rgba(255,255,255,0.06) !important;
    color: #C4C9E8 !important;
}}
/* Cacher le cercle radio */
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] {{
    display: none !important;
}}
/* Option selectionnee */
section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio-group"] label:has(input:checked),
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {{
    background: rgba(79,70,229,0.2) !important;
    color: #FFFFFF !important;
    border-left: 3px solid {INDIGO} !important;
}}

/* ── Slider sidebar ── */
section[data-testid="stSidebar"] [data-testid="stSlider"] label,
section[data-testid="stSidebar"] [data-testid="stSlider"] p {{
    color: #7A83B8 !important;
    font-size: 0.78rem !important;
}}
section[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"] {{
    background: {INDIGO} !important;
    border-color: {INDIGO} !important;
}}

/* ── Multiselect sidebar ── */
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] label {{
    color: #7A83B8 !important;
    font-size: 0.78rem !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] > div:first-child {{
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
}}
section[data-testid="stSidebar"] [data-baseweb="tag"] {{
    background: rgba(79,70,229,0.3) !important;
    border-radius: 5px !important;
}}
section[data-testid="stSidebar"] [data-baseweb="tag"] span {{
    color: #C4C9E8 !important;
    font-size: 0.72rem !important;
}}

/* ══════════════════════════════
   MAIN CONTENT
   ══════════════════════════════ */
/* Cards */
.card {{
    background: {CARD};
    border-radius: 14px;
    border: 1px solid {BORDER};
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.05);
    padding: 20px 22px;
}}

/* KPI */
.kpi {{
    background: {CARD};
    border-radius: 14px;
    border: 1px solid {BORDER};
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.05);
    padding: 18px 20px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    transition: box-shadow 0.2s;
}}
.kpi:hover {{
    box-shadow: 0 4px 8px rgba(0,0,0,0.07), 0 12px 30px rgba(79,70,229,0.1);
}}
.kpi-body  {{ flex: 1; min-width: 0; }}
.kpi-spark {{ flex-shrink: 0; padding-top: 4px; }}
.kpi-icon  {{
    width: 38px; height: 38px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; margin-bottom: 12px;
}}
.kpi-lbl {{
    font-size: 0.69rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.8px;
    color: {MUTED}; margin: 0 0 4px 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.kpi-val {{
    font-size: 1.7rem; font-weight: 800; color: {TEXT};
    line-height: 1; margin: 0 0 10px 0;
    white-space: nowrap;
}}
.kpi-tag {{
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 0.68rem; font-weight: 600;
    padding: 3px 8px; border-radius: 99px;
    white-space: nowrap;
}}
.t-indigo {{ background: rgba(79,70,229,0.12);  color:{INDIGO}; }}
.t-blue   {{ background: rgba(14,165,233,0.12); color:#0284C7; }}
.t-green  {{ background: rgba(16,185,129,0.12); color:#059669; }}
.t-amber  {{ background: rgba(245,158,11,0.12); color:#D97706; }}

/* Remove Streamlit column container visual artifacts */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}}
[data-testid="stColumn"] > div {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}}

/* Page header */
.pg-hdr {{
    padding: 16px 0 14px 0;
    border-bottom: 1px solid {BORDER};
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}}
.pg-bc  {{ font-size: 0.69rem; color: {MUTED}; margin: 0 0 3px 0; }}
.pg-bc b {{ color: {INDIGO}; }}
.pg-ttl {{ font-size: 1.3rem; font-weight: 800; color: {TEXT}; margin: 0; }}
.pg-sub {{ font-size: 0.74rem; color: {MUTED}; margin: 4px 0 0 0; }}

/* Panel */
.pnl-ttl {{ font-size: 0.88rem; font-weight: 700; color: {TEXT}; margin: 0; }}
.pnl-sub {{ font-size: 0.71rem; color: {MUTED}; margin: 2px 0 12px 0; }}

/* Chips */
.chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }}
.chip {{
    background: {BG}; border: 1px solid {BORDER};
    border-radius: 7px; padding: 4px 10px;
    font-size: 0.71rem; color: {MUTED};
}}
.chip b {{ color: {TEXT}; font-weight: 700; }}

/* Donut legend */
.leg-row {{
    display: flex; align-items: center;
    padding: 8px 0; border-bottom: 1px solid {BORDER};
}}
.leg-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
.leg-lbl {{ flex: 1; font-size: 0.79rem; color: {TEXT}; margin-left: 9px; }}
.leg-pct {{ font-size: 0.71rem; color: {MUTED}; margin-right: 10px; }}
.leg-val {{ font-size: 0.82rem; font-weight: 700; color: {TEXT}; }}

/* Region row */
.rg-row {{
    display: flex; align-items: center; gap: 8px;
    padding: 8px 0; border-bottom: 1px solid {BORDER};
}}
.rg-rk  {{ font-size: 0.67rem; font-weight: 700; color: {MUTED}; width: 16px; text-align: right; }}
.rg-nm  {{ flex: 1; font-size: 0.8rem; font-weight: 500; color: {TEXT}; }}
.rg-bg  {{ width: 78px; height: 5px; background: {BG}; border-radius: 99px; overflow: hidden; }}
.rg-bar {{ height: 5px; border-radius: 99px; }}
.rg-n   {{ font-size: 0.78rem; font-weight: 700; color: {TEXT}; width: 32px; text-align: right; }}
.rg-pct {{ font-size: 0.67rem; color: {MUTED}; width: 30px; }}

/* Bouton download */
[data-testid="stDownloadButton"] button {{
    background: {INDIGO} !important;
    color: white !important;
    border: none !important;
    border-radius: 9px !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    padding: 8px 18px !important;
    white-space: nowrap !important;
    min-width: fit-content !important;
    width: 100% !important;
}}
[data-testid="stDownloadButton"] button:hover {{
    opacity: 0.86 !important;
}}

/* Selectbox */
[data-baseweb="select"] > div {{
    border-radius: 9px !important;
    border-color: {BORDER} !important;
    font-size: 0.8rem !important;
    background: {CARD} !important;
}}

/* ══════════════════════════════════════════════════════════
   RESPONSIVE — typographie fluide (WCAG AA : min 12px = 0.75rem)
   ══════════════════════════════════════════════════════════ */
.kpi-val  {{ font-size: clamp(1.1rem,  1.6vw, 1.7rem)  !important; }}
.pg-ttl   {{ font-size: clamp(1.0rem,  1.4vw, 1.3rem)  !important; }}
.kpi-lbl  {{ font-size: clamp(0.68rem, 0.78vw, 0.80rem) !important; }}
.pnl-ttl  {{ font-size: clamp(0.80rem, 0.9vw,  0.88rem) !important; }}
.pnl-sub  {{ font-size: clamp(0.70rem, 0.78vw, 0.78rem) !important; }}
.chip     {{ font-size: clamp(0.68rem, 0.78vw, 0.78rem) !important; }}

/* ── Protection overflow horizontal (tous ecrans) ── */
html, body {{
    overflow-x: hidden !important;
}}
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMainBlockContainer"],
.block-container {{
    max-width: 100% !important;
    overflow-x: hidden !important;
}}

/* Toggle carte : style pill */
[data-testid="stRadio"][key="map_mode_radio"] [data-baseweb="radio-group"] {{
    gap: 0 !important;
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 3px;
    display: inline-flex;
    flex-wrap: wrap;
}}
[data-testid="stRadio"][key="map_mode_radio"] label {{
    border-radius: 6px !important;
    padding: 5px 14px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: {MUTED} !important;
    transition: background 0.15s !important;
    margin: 0 !important;
}}
[data-testid="stRadio"][key="map_mode_radio"] label:has(input:checked) {{
    background: {CARD} !important;
    color: {INDIGO} !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
}}

/* Padding principal adaptatif (clamp couvre mobile->desktop) */
[data-testid="stAppViewContainer"] > .main {{
    padding: 0 clamp(8px, 2vw, 28px) 40px clamp(8px, 2vw, 28px) !important;
}}

/* Region row : supporte sparkline inline */
.rg-row {{
    gap: 6px !important;
}}

/* Transition de page — fade-in du contenu principal */
@keyframes pgFadeIn {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0);   }}
}}
[data-testid="stMainBlockContainer"] > div > div {{
    animation: pgFadeIn 0.18s ease-out;
}}

/* ══════════════════════════════════════════════════════════
   RESPONSIVE — Grand ecran (>1400px)
   ══════════════════════════════════════════════════════════ */
@media (min-width: 1400px) {{
    [data-testid="stAppViewContainer"] > .main {{
        padding: 0 40px 40px 40px !important;
    }}
}}

/* ══════════════════════════════════════════════════════════
   RESPONSIVE — Tablette (640px – 1024px)
   ══════════════════════════════════════════════════════════ */
@media (min-width: 640px) and (max-width: 1024px) {{
    /* Sidebar un peu plus etroite */
    section[data-testid="stSidebar"] {{
        min-width: 220px !important;
        max-width: 220px !important;
    }}
    /* KPI rows 4-col -> 2x2 */
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="stColumn"] {{
        width: 50% !important;
        min-width: 50% !important;
        flex: 0 0 50% !important;
    }}
    /* Masquer sparkline sur tablette */
    .kpi-spark {{ display: none !important; }}
    .kpi {{ padding: 14px 15px !important; }}
    /* Header : passe en colonne sous 1024px */
    .pg-hdr {{
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 8px !important;
    }}
    /* Titre et sous-titre page */
    .pg-ttl {{ font-size: clamp(0.82rem, 1.1vw, 0.98rem) !important; }}
    .pg-sub {{ font-size: 0.64rem !important; }}
    /* Badges header evenements : taille reduite */
    .evt-badge {{
        font-size: 0.60rem !important;
        padding: 3px 7px !important;
    }}
    /* Mini-cards evenements : padding et fonts reduits */
    .mini-ev-card {{
        padding: 6px 6px 5px 6px !important;
    }}
    /* Critere dans mini-card : taille reduite + retour a la ligne autorise */
    .mini-ev-crit {{
        font-size: 0.58rem !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
        line-height: 1.3 !important;
    }}
    /* Sous-titre section divider : taille reduite + masque si debordement */
    .sec-hdr-sub {{
        font-size: 0.60rem !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        max-width: 200px !important;
    }}
    /* Graphiques Plotly : hauteur moderee */
    [data-testid="stPlotlyChart"] > div {{
        min-height: 0 !important;
    }}
}}

/* ══════════════════════════════════════════════════════════
   RESPONSIVE — Petit ecran bureau (1024px – 1280px)
   ══════════════════════════════════════════════════════════ */
@media (min-width: 1024px) and (max-width: 1280px) {{
    /* Titre et sous-titre page */
    .pg-ttl {{ font-size: clamp(0.90rem, 1.2vw, 1.10rem) !important; }}
    .pg-sub {{ font-size: 0.67rem !important; }}
    /* Badges header evenements : taille legerement reduite */
    .evt-badge {{
        font-size: 0.64rem !important;
        padding: 4px 9px !important;
    }}
    /* Mini-cards evenements : padding reduit */
    .mini-ev-card {{
        padding: 8px 8px 7px 8px !important;
    }}
    /* Critere dans mini-card : taille reduite + retour a la ligne autorise */
    .mini-ev-crit {{
        font-size: 0.61rem !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
        line-height: 1.3 !important;
    }}
    /* Sous-titre section divider : taille reduite */
    .sec-hdr-sub {{
        font-size: 0.62rem !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        max-width: 260px !important;
    }}
    /* Titres panneaux : legerement reduits */
    .pnl-ttl {{ font-size: clamp(0.78rem, 0.85vw, 0.84rem) !important; }}
}}

/* ══════════════════════════════════════════════════════════
   RESPONSIVE — Mobile (<640px)
   ══════════════════════════════════════════════════════════ */
@media (max-width: 640px) {{
    /* Tout empiler verticalement */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        width: 100% !important;
        flex: none !important;
        min-width: 100% !important;
    }}
    /* KPI en grille 2x2 */
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="stColumn"] {{
        width: 50% !important;
        min-width: 50% !important;
        flex: 0 0 50% !important;
    }}
    /* Mini-cartes evenements : 2 par ligne */
    [data-testid="stHorizontalBlock"]:has(.mini-ev-card) > [data-testid="stColumn"] {{
        width: 50% !important;
        min-width: 50% !important;
        flex: 0 0 50% !important;
    }}
    /* Sparklines masquees */
    .kpi-spark {{ display: none !important; }}
    .kpi {{ padding: 12px 13px !important; }}
    /* Valeur KPI un peu plus petite */
    .kpi-val {{ font-size: 1.15rem !important; }}
    /* Header en colonne */
    .pg-hdr {{
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 8px !important;
    }}
    /* Chips : taille reduite */
    .chip {{ font-size: 0.68rem !important; padding: 3px 7px !important; }}
    /* Reduire la hauteur des graphiques Plotly */
    [data-testid="stPlotlyChart"] > div {{
        min-height: 0 !important;
    }}
    /* Datatable : scroll horizontal interne autorise */
    [data-testid="stDataFrame"] {{
        overflow-x: auto !important;
    }}
    /* Cards : padding reduit */
    .card {{ padding: 14px 15px !important; }}
    /* Leg-row : retrait des colonnes de largeur fixe */
    .rg-bg {{ width: 50px !important; }}
}}

/* ══════════════════════════════════════════════════════════
   RESPONSIVE — Tres petit mobile (<420px)
   ══════════════════════════════════════════════════════════ */
@media (max-width: 420px) {{
    /* KPI en 1 colonne sur tres petit ecran */
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="stColumn"] {{
        width: 100% !important;
        min-width: 100% !important;
        flex: 0 0 100% !important;
    }}
    .kpi-val {{ font-size: 1.05rem !important; }}
    .pg-ttl  {{ font-size: 0.95rem !important; }}
    .pnl-ttl {{ font-size: 0.80rem !important; }}
    /* Sidebar masquee par defaut sur tres petit mobile */
    section[data-testid="stSidebar"] {{
        min-width: 0 !important;
        max-width: 75vw !important;
    }}
}}

/* ── Masquer sparkline et reduire padding sous 900px ── */
@media (max-width: 900px) {{
    .kpi-spark {{ display: none !important; }}
    .kpi {{ padding: 14px 15px !important; }}
}}

/* ── Expander : corrige icone Material affichee en texte brut ── */
[data-testid="stExpander"] summary {{
    display: flex !important;
    align-items: center !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    cursor: pointer !important;
    gap: 6px !important;
}}
[data-testid="stExpanderToggleIcon"],
[data-testid="stExpander"] summary > span:first-child {{
    font-size: 0 !important;
    line-height: 0 !important;
    color: transparent !important;
    width: 20px !important;
    height: 20px !important;
    flex-shrink: 0 !important;
}}
[data-testid="stExpanderToggleIcon"] svg,
[data-testid="stExpander"] summary > span:first-child svg {{
    width: 20px !important;
    height: 20px !important;
    color: #6B7280 !important;
    display: block !important;
}}
</style>
""", unsafe_allow_html=True)

# ─── Dark mode CSS complet (elements natifs Streamlit) ───────────────────────
if st.session_state.dark_mode:
    st.markdown(f"""
<style>
/* ── Fond racine ── */
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
[data-testid="stMainBlockContainer"],
.block-container {{
    background: {BG} !important;
}}

/* ── Tout le texte principal ── */
[data-testid="stApp"] p,
[data-testid="stApp"] span:not([data-baseweb="tag"] span):not(section[data-testid="stSidebar"] span),
[data-testid="stApp"] label,
[data-testid="stApp"] h1,
[data-testid="stApp"] h2,
[data-testid="stApp"] h3,
[data-testid="stApp"] h4,
[data-testid="stApp"] h5,
[data-testid="stApp"] div:not(section[data-testid="stSidebar"] div),
[data-testid="stApp"] li {{
    color: {TEXT} !important;
}}

/* ── Labels widgets (hors sidebar) ── */
[data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] p,
[data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] span,
[data-testid="stMainBlockContainer"] label {{
    color: {MUTED} !important;
}}

/* ── Inputs / Textareas ── */
[data-testid="stMainBlockContainer"] [data-baseweb="input"] > div,
[data-testid="stMainBlockContainer"] [data-baseweb="textarea"] > div,
[data-testid="stMainBlockContainer"] [data-baseweb="base-input"] {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}
[data-testid="stMainBlockContainer"] input,
[data-testid="stMainBlockContainer"] textarea {{
    background: {CARD} !important;
    color: {TEXT} !important;
}}

/* ── Selectbox / Multiselect (contenu principal) ── */
[data-testid="stMainBlockContainer"] [data-baseweb="select"] > div:first-child {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
}}
[data-baseweb="popover"] li {{
    background: {CARD} !important;
    color: {TEXT} !important;
}}
[data-baseweb="popover"] li:hover {{
    background: rgba(79,70,229,0.15) !important;
}}

/* ── Slider ── */
[data-testid="stMainBlockContainer"] [data-baseweb="slider"] [data-testid="stSliderTrack"] {{
    background: {BORDER} !important;
}}

/* ── Expanders ── */
[data-testid="stExpander"],
[data-testid="stExpander"] summary,
[data-testid="stExpander"] > div {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: {BG} !important;
    border-bottom-color: {BORDER} !important;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    background: transparent !important;
    color: {MUTED} !important;
}}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {{
    color: {INDIGO} !important;
}}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {{
    background: {BG} !important;
}}

/* ── Dataframe / Table ── */
[data-testid="stDataFrame"] iframe,
.stDataFrame {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
}}

/* ── Metrics ── */
[data-testid="stMetric"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
}}
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"] {{
    color: {TEXT} !important;
}}
[data-testid="stMetricDelta"] {{
    color: {MUTED} !important;
}}

/* ── Info / Warning / Error boxes ── */
[data-testid="stInfo"],
[data-testid="stWarning"],
[data-testid="stError"],
[data-testid="stSuccess"] {{
    background: rgba(79,70,229,0.1) !important;
    border-color: rgba(79,70,229,0.3) !important;
    color: {TEXT} !important;
}}

/* ── Badges de tags (adaptes mode sombre) ── */
.t-indigo {{ background: rgba(79,70,229,0.2) !important; color: #A5B4FC !important; }}
.t-blue   {{ background: rgba(14,165,233,0.2) !important; color: #7DD3FC !important; }}
.t-green  {{ background: rgba(16,185,129,0.2) !important; color: #6EE7B7 !important; }}
.t-amber  {{ background: rgba(245,158,11,0.2) !important; color: #FCD34D !important; }}

/* ── Plotly chart container ── */
[data-testid="stPlotlyChart"] {{
    background: {CARD} !important;
    border-radius: 14px !important;
    border: 1px solid {BORDER} !important;
}}

/* ── Boutons natifs (contenu principal) ── */
[data-testid="stMainBlockContainer"] [data-testid="stButton"] button,
[data-testid="stMainBlockContainer"] [data-baseweb="button"] {{
    background: {CARD} !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
}}
[data-testid="stMainBlockContainer"] [data-testid="stButton"] button:hover,
[data-testid="stMainBlockContainer"] [data-baseweb="button"]:hover {{
    background: rgba(79,70,229,0.15) !important;
    border-color: {INDIGO} !important;
    color: {TEXT} !important;
}}
[data-testid="stMainBlockContainer"] [data-testid="stButton"] button:disabled,
[data-testid="stMainBlockContainer"] [data-testid="stButton"] button[disabled] {{
    background: rgba(255,255,255,0.04) !important;
    border-color: {BORDER} !important;
    color: {MUTED} !important;
    opacity: 0.5 !important;
}}

/* ── Scrollbar ── */
* {{
    scrollbar-color: {BORDER} {BG} !important;
}}
::-webkit-scrollbar-track {{ background: {BG} !important; }}
::-webkit-scrollbar-thumb {{ background: {BORDER} !important; border-radius: 4px !important; }}

/* ── Page loading bar ── */
#page-loader {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    z-index: 99999;
    background: transparent;
    pointer-events: none;
}}
#page-loader .bar {{
    height: 3px;
    width: 0%;
    background: linear-gradient(90deg, {INDIGO}, {BLUE}, {EMERALD});
    border-radius: 0 2px 2px 0;
    box-shadow: 0 0 8px rgba(79, 70, 229, 0.6);
    animation: loader-progress 0.9s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}}
@keyframes loader-progress {{
    0%   {{ width: 0%;   opacity: 1; }}
    70%  {{ width: 85%;  opacity: 1; }}
    100% {{ width: 100%; opacity: 0; }}
}}
#page-loader .pulse {{
    position: fixed;
    top: 6px;
    right: 16px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: {INDIGO};
    animation: loader-pulse 0.9s ease-out forwards;
}}
@keyframes loader-pulse {{
    0%   {{ opacity: 1; transform: scale(1); }}
    100% {{ opacity: 0; transform: scale(2); }}
}}
</style>
""", unsafe_allow_html=True)

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:

    # Header : logo + bouton mode sombre
    _moon = "🌙" if not st.session_state.dark_mode else "☀️"
    _mode_lbl = "Mode clair" if st.session_state.dark_mode else "Mode sombre"
    _hdr_cols = st.columns([3, 1])
    with _hdr_cols[0]:
        st.markdown(
            '<p style="color:#FFFFFF;font-size:0.62rem;font-weight:700;'
            'letter-spacing:1.3px;text-transform:uppercase;'
            'padding:4px 0 0 2px;margin:0;">ClimatSen</p>',
            unsafe_allow_html=True,
        )
    with _hdr_cols[1]:
        if st.button(_moon, key="toggle_dark", help=_mode_lbl, use_container_width=True):
            st.session_state.dark_mode = not st.session_state.dark_mode
            # Persiste la preference dans l'URL pour survivre aux rafraichissements
            st.query_params["dm"] = "1" if st.session_state.dark_mode else "0"
            st.rerun()

    # Navigation
    page = st.radio(
        label="nav",
        options=["Evenements", "Indices SST", "Teleconnexions", "Clustering", "Pipeline"],
        format_func=lambda x: {
            "Evenements":     "📊   Evenements",
            "Teleconnexions": "🔗   Teleconnexions",
            "Indices SST":    "🌊   Indices SST",
            "Clustering":     "🗂   Clustering",
            "Pipeline":       "⚙️   Pipeline",
        }[x],
        label_visibility="collapsed",
        key="nav_page",
    )

    st.markdown("---")

    # Filtres
    st.markdown(
        '<p style="color:#FFFFFF;font-size:0.62rem;font-weight:700;'
        'letter-spacing:1.3px;text-transform:uppercase;'
        'padding:0 14px;margin:4px 0 10px 0;">FILTRES</p>',
        unsafe_allow_html=True,
    )

    year_range = st.slider(
        "Periode",
        min_value=int(df["year"].min()),
        max_value=int(df["year"].max()),
        value=(1981, 2023),
    )
    phases_sel = st.multiselect(
        "Phases",
        options=["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"],
        default=["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"],
        format_func=lambda x: PHASE_L[x],
    )

    st.markdown("---")

    # Profil
    st.markdown(f"""
    <div style="padding:8px 12px 22px 12px;">
      <div style="display:flex;align-items:center;gap:10px;
                  background:rgba(255,255,255,0.05);
                  border:1px solid rgba(255,255,255,0.07);
                  border-radius:10px;padding:10px 12px;">
        <div style="width:32px;height:32px;border-radius:50%;flex-shrink:0;
                    background:linear-gradient(135deg,{INDIGO},{BLUE});
                    display:flex;align-items:center;justify-content:center;
                    font-size:0.8rem;font-weight:800;color:white;">LF</div>
        <div>
          <div style="color:#E2E8F0;font-size:0.79rem;font-weight:600;">
            Laity FAYE</div>
          <div style="color:#E2E8F0;font-size:0.66rem;margin-top:1px;">
            UIDT · 2026</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ─── Indicateur de chargement lors du changement de page ─────────────────────
_page_changed = (st.session_state.prev_page != page)
if _page_changed:
    st.session_state.prev_page = page
    st.markdown(
        '<div id="page-loader"><div class="bar"></div><div class="pulse"></div></div>',
        unsafe_allow_html=True,
    )

# ─── Données filtrées ─────────────────────────────────────────────────────────
active_phases = phases_sel if phases_sel else ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]
dff = df[df["year"].between(*year_range) & df["phase"].isin(active_phases)].copy()


# ═════════════════════════════════════════════════════════════════════════════
# PAGE EVENEMENTS
# ═════════════════════════════════════════════════════════════════════════════
if page == "Evenements":

    n_total  = len(dff)
    avg_cov  = dff["coverage_percent"].mean()
    avg_prec = dff["max_precip"].mean()
    avg_anom = dff["max_anomaly"].mean()

    all_yrs  = list(range(year_range[0], year_range[1] + 1))
    yr_n    = dff.groupby("year").size()
    yr_cov  = dff.groupby("year")["coverage_percent"].mean()
    yr_prec = dff.groupby("year")["max_precip"].mean()
    yr_anom = dff.groupby("year")["max_anomaly"].mean()
    sp_n    = [yr_n.get(y, 0)            for y in all_yrs]
    sp_cov  = [yr_cov.get(y, np.nan)     for y in all_yrs]
    sp_prec = [yr_prec.get(y, np.nan)    for y in all_yrs]
    sp_anom = [yr_anom.get(y, np.nan)    for y in all_yrs]

    # ── Header ────────────────────────────────────────────────────────────────
    _n_total_fmt = f"{n_total:,}".replace(",", "\u202f")  # espace fine fr

    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown(f"""
        <div class="pg-hdr">
          <div>
            <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Evenements</b></p>
            <h1 class="pg-ttl">Ev&eacute;nements de Pr&eacute;cipitation Extr&ecirc;me</h1>
            <p class="pg-sub">
              S&eacute;n&eacute;gal &nbsp;&middot;&nbsp; CHIRPS 0.05&deg;
              &nbsp;&middot;&nbsp; {year_range[0]}&ndash;{year_range[1]}
            </p>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;padding-bottom:4px;margin-top:10px;">
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:#7C3AED;
                         background:rgba(124,58,237,0.13);border-radius:8px;padding:5px 12px;">
              &#128208; Anomalie &gt; 2&#963;</span>
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:#0284C7;
                         background:rgba(2,132,199,0.13);border-radius:8px;padding:5px 12px;">
              &#9726; 40&nbsp;pixels&nbsp;min.</span>
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:#D97706;
                         background:rgba(217,119,6,0.13);border-radius:8px;padding:5px 12px;">
              &#127783; 5&nbsp;mm&nbsp;min.</span>
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:{INDIGO};
                         background:rgba(79,70,229,0.13);border-radius:8px;padding:5px 12px;">
              &#128202; {_n_total_fmt}&nbsp;&eacute;v&eacute;nements</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with hc2:
        st.markdown("<div style='height:56px'></div>", unsafe_allow_html=True)
        st.download_button(
            "Exporter CSV",
            data=dff.to_csv(index=False).encode("utf-8"),
            file_name="evenements_senegal.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # ── Cartographie des evenements specifiques ───────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
      <div style="height:2px;width:28px;
                  background:linear-gradient(90deg,{INDIGO},{BLUE});
                  border-radius:99px;flex-shrink:0;"></div>
      <span style="font-size:0.70rem;font-weight:700;color:{MUTED};
                   text-transform:uppercase;letter-spacing:0.08em;white-space:nowrap">
        Analyse spatiale &mdash; Cartographie
      </span>
      <div style="height:1px;flex:1;background:{BORDER};"></div>
      <span class="sec-hdr-sub" style="font-size:0.67rem;color:{MUTED};white-space:nowrap;">
        6 ev&eacute;nements &middot; plus/moins intense, grande/petite couverture &amp; anomalie
      </span>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement des cartes..."):
        _ev_pixels  = load_events_pixels()
        _ev_summary = load_events_summary()
        _dept_geo   = load_dept_geojson()

    if _ev_pixels is None or len(_ev_pixels) == 0:
        st.info(
            "Donnees cartographiques non disponibles. "
            "Executer le script 03_filter_events_for_qgis.py pour generer les fichiers de pixels."
        )
    else:
        _dates = sorted(_ev_pixels["event_date"].unique().tolist())
        _crit_map = (
            _ev_pixels.groupby("event_date")["selection_criterion"].first().to_dict()
            if "selection_criterion" in _ev_pixels.columns
            else {}
        )

        _CRIT_FR = {
            "plus_intense":           "Plus intense",
            "moins_intense":          "Moins intense",
            "plus_grande_couverture": "Plus grande couverture",
            "plus_petite_couverture": "Plus petite couverture",
            "plus_grande_anomalie":   "Plus grande anomalie",
            "plus_petite_anomalie":   "Plus petite anomalie",
            "selection_manuelle":     "Selection manuelle",
        }
        _CRIT_COLORS = {
            "plus_intense":           (ROSE,      "rgba(244,63,94,0.13)"),
            "moins_intense":          (EMERALD,   "rgba(16,185,129,0.13)"),
            "plus_grande_couverture": (INDIGO,    "rgba(79,70,229,0.13)"),
            "plus_petite_couverture": (BLUE,      "rgba(14,165,233,0.13)"),
            "plus_grande_anomalie":   (AMBER,     "rgba(245,158,11,0.13)"),
            "plus_petite_anomalie":   ("#6B7280", "rgba(107,114,128,0.13)"),
        }

        def _fmt_event(d):
            raw = _crit_map.get(d, "")
            parts = [_CRIT_FR.get(c.strip(), c.strip()) for c in raw.split("+")]
            label = " + ".join(parts) if parts and raw else ""
            return f"{d}  [{label}]" if label else d

        def _get_crit0(d):
            raw = _crit_map.get(d, "")
            return raw.split("+")[0].strip() if raw else ""

        # ── Selecteur + navigation ────────────────────────────────────────────
        # Etat de navigation separe du key du widget (evite StreamlitAPIException)
        if "carto_nav_idx" not in st.session_state:
            st.session_state["carto_nav_idx"] = 0
        _idx_cur = min(st.session_state["carto_nav_idx"], len(_dates) - 1)

        _sel_col, _prev_col, _ctr_col, _next_col = st.columns(
            [7, 1, 1.2, 1], gap="small"
        )
        with _prev_col:
            if st.button("\u2190", key="ev_prev", disabled=_idx_cur <= 0,
                         use_container_width=True):
                st.session_state["carto_nav_idx"] = max(0, _idx_cur - 1)
                st.rerun()
        with _sel_col:
            _sel_date = st.selectbox(
                "Evenement selectionne",
                options=_dates,
                index=_idx_cur,
                format_func=_fmt_event,
                label_visibility="collapsed",
            )
            # Synchroniser l'index si l'utilisateur change via le selectbox
            _sel_idx = _dates.index(_sel_date) if _sel_date in _dates else _idx_cur
            if _sel_idx != _idx_cur:
                st.session_state["carto_nav_idx"] = _sel_idx
                _idx_cur = _sel_idx
        with _ctr_col:
            st.markdown(
                f'<div style="text-align:center;padding:8px 0;'
                f'font-size:0.75rem;font-weight:700;color:{MUTED};">'
                f'{_idx_cur + 1}&nbsp;/&nbsp;{len(_dates)}</div>',
                unsafe_allow_html=True,
            )
        with _next_col:
            if st.button("\u2192", key="ev_next",
                         disabled=_idx_cur >= len(_dates) - 1,
                         use_container_width=True):
                st.session_state["carto_nav_idx"] = min(len(_dates) - 1, _idx_cur + 1)
                st.rerun()

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # ── Mini-cards apercu (6 evenements) ─────────────────────────────────
        if _ev_summary is not None and len(_ev_summary) > 0 and len(_dates) > 0:
            _ncols = min(6, len(_dates))
            _mini_cols = st.columns(_ncols, gap="small")
            for _col_m, _d in zip(_mini_cols, _dates):
                _row_m = _ev_summary[_ev_summary["event_date"] == _d]
                _c0 = _get_crit0(_d)
                _fg, _bg = _CRIT_COLORS.get(_c0, (INDIGO, "rgba(79,70,229,0.13)"))
                _ph = _row_m.iloc[0]["season_phase"] if not _row_m.empty else ""
                _pmax = f"{_row_m.iloc[0]['precip_max']:.0f}" if not _row_m.empty else "-"
                _amax = f"{_row_m.iloc[0]['anomaly_max']:.1f}" if not _row_m.empty else "-"
                _is_sel = (_d == _sel_date)
                _border = f"2px solid {INDIGO}" if _is_sel else f"1px solid {BORDER}"
                _shadow = "box-shadow:0 3px 12px rgba(79,70,229,0.18);" if _is_sel else ""
                _bg_card = "rgba(79,70,229,0.12)" if _is_sel else CARD
                _ph_short = (
                    "P1 Debut" if "debut" in _ph
                    else "P2 Pleine" if "pleine" in _ph
                    else "P3 Fin" if "fin" in _ph
                    else _ph
                )
                _col_m.markdown(f"""
                <div class="mini-ev-card" style="background:{_bg_card};border:{_border};border-radius:10px;
                            padding:10px 10px 9px 10px;{_shadow}cursor:pointer;
                            transition:box-shadow 0.15s;">
                  <div style="background:{_bg};border-radius:5px;padding:2px 6px;
                              margin-bottom:7px;display:inline-block;max-width:100%;">
                    <span class="mini-ev-crit" style="font-size:0.69rem;font-weight:700;color:{_fg};
                                 white-space:nowrap;display:block;">{_CRIT_FR.get(_c0, _c0)}</span>
                  </div>
                  <p style="margin:0;font-size:0.77rem;font-weight:700;
                            color:{TEXT};line-height:1.2">{_d}</p>
                  <p style="margin:3px 0 0 0;font-size:0.72rem;color:{MUTED}">
                    {_pmax} mm &nbsp;&middot;&nbsp; {_amax} &#963;
                  </p>
                  <p style="margin:4px 0 0 0;font-size:0.69rem;color:{MUTED}">{_ph_short}</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        _ev_sel = _ev_pixels[_ev_pixels["event_date"] == _sel_date].copy()

        # -- Filtrage geometrique : pixels a l'interieur du Senegal uniquement --
        if _dept_geo is not None and len(_ev_sel) > 0:
            from matplotlib.path import Path as _MplPath

            def _build_paths(geojson):
                paths = []
                for feat in geojson.get("features", []):
                    geom = feat.get("geometry", {})
                    gtype = geom.get("type", "")
                    coords = geom.get("coordinates", [])
                    if gtype == "MultiPolygon":
                        for poly in coords:
                            if poly and poly[0]:
                                paths.append(_MplPath(np.array(poly[0])))
                    elif gtype == "Polygon":
                        if coords and coords[0]:
                            paths.append(_MplPath(np.array(coords[0])))
                return paths

            _bounds_geo = load_dept_geojson()
            _bounds_path = BASE / "data/geographic/senegal_boundaries.geojson"
            if _bounds_path.exists():
                import json as _json
                with open(str(_bounds_path), "r", encoding="utf-8") as _bf:
                    _bounds_geo = _json.load(_bf)

            if _bounds_geo is not None:
                _boundary_paths = _build_paths(_bounds_geo)
                if _boundary_paths:
                    _pts = np.column_stack([
                        _ev_sel["longitude"].values,
                        _ev_sel["latitude"].values,
                    ])
                    _inside = np.zeros(len(_pts), dtype=bool)
                    for _bp in _boundary_paths:
                        _inside |= _bp.contains_points(_pts)
                    _ev_sel = _ev_sel[_inside].reset_index(drop=True)

        # -- Jointure spatiale : departement pour chaque pixel --------------------
        _depts_ev = [""] * len(_ev_sel)
        if _dept_geo is not None and len(_ev_sel) > 0:
            from matplotlib.path import Path as _MplPath2
            _pts_all = np.column_stack([
                _ev_sel["longitude"].values,
                _ev_sel["latitude"].values,
            ])
            for _feat in _dept_geo.get("features", []):
                _dname = _feat.get("properties", {}).get("NAME_2", "")
                _geom  = _feat.get("geometry", {})
                _gtype = _geom.get("type", "")
                _coords = _geom.get("coordinates", [])
                _polys  = []
                if _gtype == "MultiPolygon":
                    for _poly in _coords:
                        if _poly and _poly[0]:
                            _polys.append(_MplPath2(np.array(_poly[0])))
                elif _gtype == "Polygon":
                    if _coords and _coords[0]:
                        _polys.append(_MplPath2(np.array(_coords[0])))
                for _pp in _polys:
                    _mask = _pp.contains_points(_pts_all)
                    for _idx in np.where(_mask)[0]:
                        _depts_ev[_idx] = _dname

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        # -- Infrastructure cartes ------------------------------------------------
        # Approche Densitymapbox : interpolation par noyau gaussien
        # => surface lisse sans rectangles visibles (comme une carte SIG professionnelle)
        _map_base = dict(
            style="open-street-map",
            center=dict(lat=14.5, lon=-14.5),
            zoom=5,
        )
        _margin = dict(l=0, r=0, t=28, b=0)

        # Contours des departements en trace Scattermapbox (au-dessus de la heatmap)
        def _make_boundary_trace(geojson, width=1.4, color="rgba(30,30,30,0.70)"):
            lons_b, lats_b = [], []
            for feat in geojson.get("features", []):
                geom   = feat.get("geometry", {})
                gtype  = geom.get("type", "")
                coords = geom.get("coordinates", [])
                rings  = []
                if gtype == "Polygon":
                    rings = coords
                elif gtype == "MultiPolygon":
                    for poly in coords:
                        rings.extend(poly)
                for ring in rings:
                    for x, y in ring:
                        lons_b.append(x)
                        lats_b.append(y)
                    lons_b.append(None)
                    lats_b.append(None)
            return go.Scattermapbox(
                lat=lats_b, lon=lons_b,
                mode="lines",
                line=dict(width=width, color=color),
                hoverinfo="none",
                showlegend=False,
            )

        # Couche hover invisible : valeurs exactes au survol de chaque pixel
        def _make_hover_trace(lats, lons, texts):
            return go.Scattermapbox(
                lat=lats, lon=lons,
                mode="markers",
                marker=dict(size=10, opacity=0, color="rgba(0,0,0,0)"),
                text=texts,
                hovertemplate="%{text}<extra></extra>",
                showlegend=False,
            )

        _lats_ev  = _ev_sel["latitude"].tolist()
        _lons_ev  = _ev_sel["longitude"].tolist()
        _prec_ev  = _ev_sel["precipitation_mm"].tolist()
        _anom_ev  = _ev_sel["anomaly_standardized"].tolist()

        _hover_txt = [
            f"<b>{r['precipitation_mm']:.1f} mm</b> &nbsp;|&nbsp; "
            f"{r['anomaly_standardized']:.1f}<br>"
            f"Region : {r['region']}<br>"
            f"Categorie : {r['intensity_category']}"
            for _, r in _ev_sel.iterrows()
        ]

        # Centroide depuis summary, sinon moyenne des pixels
        _ctr_lat = float(_ev_sel["latitude"].mean()) if len(_ev_sel) else 14.5
        _ctr_lon = float(_ev_sel["longitude"].mean()) if len(_ev_sel) else -14.5
        if _ev_summary is not None and len(_ev_summary) > 0:
            _row_ctr = _ev_summary[_ev_summary["event_date"] == _sel_date]
            if (not _row_ctr.empty
                    and "centroid_lat" in _row_ctr.columns
                    and "centroid_lon" in _row_ctr.columns):
                _ctr_lat = float(_row_ctr.iloc[0]["centroid_lat"])
                _ctr_lon = float(_row_ctr.iloc[0]["centroid_lon"])

        _title_map = (
            f"<b>{_sel_date}</b> \u00b7 "
            f"{_fmt_event(_sel_date).split('[')[-1].replace(']','').strip()}"
        )

        # radius Densitymapbox : ~0.25 deg a zoom 5 ≈ 20 px
        # Ajuste selon la plage des donnees pour une interpolation naturelle
        _density_radius = 20

        # -- Deux cartes scientifiques cote a cote + Fiche evenement ----------

        # Grille CHIRPS exacte : chaque pixel = polygone 0.05 deg x 0.05 deg
        _HALF_PX = 0.025
        _pixel_geo = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": str(i),
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [lo - _HALF_PX, la - _HALF_PX],
                            [lo + _HALF_PX, la - _HALF_PX],
                            [lo + _HALF_PX, la + _HALF_PX],
                            [lo - _HALF_PX, la + _HALF_PX],
                            [lo - _HALF_PX, la - _HALF_PX],
                        ]]
                    },
                    "properties": {"id": i},
                }
                for i, (la, lo) in enumerate(zip(_lats_ev, _lons_ev))
            ],
        }
        _ids_px  = [str(i) for i in range(len(_lats_ev))]
        _regs_ev = _ev_sel["region"].tolist()
        _cats_ev = _ev_sel["intensity_category"].tolist()

        # customdata[0]=valeur_croisee (str formate), [1]=region, [2]=categorie,
        # [3]=lat, [4]=lon, [5]=departement, [6]=valeur_principale (str formate)
        # Valeurs pre-formatees en Python car Scattermapbox n'applique pas :.Nf sur customdata
        _cd_prec = [
            [f"{a:+.1f}", rg, ct, la, lo, dp, f"{p:.1f}"]
            for a, rg, ct, la, lo, dp, p
            in zip(_anom_ev, _regs_ev, _cats_ev, _lats_ev, _lons_ev, _depts_ev, _prec_ev)
        ]
        _cd_anom = [
            [f"{p:.1f}", rg, ct, la, lo, dp, f"{a:+.1f}"]
            for p, rg, ct, la, lo, dp, a
            in zip(_prec_ev, _regs_ev, _cats_ev, _lats_ev, _lons_ev, _depts_ev, _anom_ev)
        ]

        # Bornes adaptatives (robustesse aux outliers)
        _p_max = float(np.percentile(_prec_ev, 99)) if _prec_ev else 50.0
        _p_min = max(0.0, float(np.percentile(_prec_ev, 1)) if _prec_ev else 0.0)
        _a_abs = max(
            abs(float(np.percentile(_anom_ev, 2))) if _anom_ev else 3.0,
            abs(float(np.percentile(_anom_ev, 98))) if _anom_ev else 3.0,
            2.5,
        )

        # Colorscale precipitation : WMO Sahel
        # blanc -> jaune pale -> jaune vif -> orange -> rouge -> violet -> indigo
        _CS_PREC = [
            [0.00, "#FFFFFF"], [0.04, "#FFF9C4"], [0.14, "#FFEB3B"],
            [0.30, "#FF9800"], [0.55, "#F44336"], [0.80, "#9C27B0"],
            [1.00, "#1A237E"],
        ]

        # Colorscale anomalie : RdBu_r IPCC, divergente centree sur 0
        _CS_ANOM = [
            [0.00, "#053061"], [0.12, "#2166AC"], [0.26, "#74ADD1"],
            [0.42, "#D1E5F0"], [0.50, "#FFFFFF"],
            [0.58, "#FDDBC7"], [0.74, "#F4A582"],
            [0.88, "#D6604D"], [1.00, "#67001F"],
        ]

        # Basemap neutre scientifique
        _bmap = dict(
            style="carto-positron",
            center=dict(lat=_ctr_lat, lon=_ctr_lon),
            zoom=5.5,
        )
        _mgn = dict(l=0, r=0, t=36, b=0)

        def _add_overlays(fig):
            """Departements + centroide (cercle anneau)."""
            if _dept_geo is not None:
                fig.add_trace(_make_boundary_trace(
                    _dept_geo, width=0.8, color="rgba(15,23,42,0.45)"
                ))
            # Centroide : deux marqueurs superposes (grand blanc + petit rose)
            # pour simuler un anneau sans marker.line (non supporte Scattermapbox)
            fig.add_trace(go.Scattermapbox(
                lat=[_ctr_lat], lon=[_ctr_lon],
                mode="markers",
                marker=dict(size=18, color="white", opacity=0.9),
                hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scattermapbox(
                lat=[_ctr_lat], lon=[_ctr_lon],
                mode="markers",
                marker=dict(size=12, color=ROSE, opacity=0.95),
                hovertemplate=(
                    f"<b>Centroide</b><br>"
                    f"{_ctr_lat:.1f}\u00b0N\u00a0"
                    f"{abs(_ctr_lon):.1f}\u00b0W"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

        _mmap1, _minfo = st.columns([5, 4], gap="medium")

        # ── Carte 1 : Precipitations (mm) — Choroplethmapbox CHIRPS 0.05 deg ──
        with _mmap1:
            st.markdown(
                '<p class="pnl-ttl" style="margin-bottom:4px">'
                '&#127783; Pr\u00e9cipitation (mm)</p>',
                unsafe_allow_html=True,
            )
            with st.spinner("Chargement de la carte des precipitations..."):
                _fig1 = go.Figure()
                _fig1.add_trace(go.Choroplethmapbox(
                    geojson=_pixel_geo,
                    locations=_ids_px,
                    z=_prec_ev,
                    colorscale=_CS_PREC,
                    zmin=_p_min, zmax=_p_max,
                    marker=dict(
                        opacity=0.87,
                        line=dict(width=0.4, color="rgba(255,255,255,0.12)"),
                    ),
                    colorbar=dict(
                        title=dict(text="mm", font=dict(size=11, color=MUTED)),
                        thickness=12, len=0.82, x=1.01,
                        tickfont=dict(size=10, color=MUTED),
                        outlinewidth=0,
                    ),
                    hoverinfo="skip",
                ))
                # Couche points invisibles pour hover fluide (plus rapide que polygones)
                _fig1.add_trace(go.Scattermapbox(
                    lat=_lats_ev, lon=_lons_ev,
                    mode="markers",
                    marker=dict(size=8, opacity=0, color="rgba(0,0,0,0)"),
                    customdata=_cd_prec,
                    hovertemplate=(
                        "<b>%{customdata[6]} mm</b>\u00a0|\u00a0%{customdata[0]}<br>"
                        "D\u00e9partement\u00a0: <b>%{customdata[5]}</b><br>"
                        "R\u00e9gion\u00a0: %{customdata[1]}<br>"
                        "Cat\u00e9gorie\u00a0: <b>%{customdata[2]}</b>"
                        "<extra></extra>"
                    ),
                    showlegend=False,
                ))
                _add_overlays(_fig1)
                _fig1.update_layout(
                    mapbox=_bmap, margin=_mgn, height=430,
                    plot_bgcolor=CARD, paper_bgcolor=CARD,
                    title=dict(
                        text=f"<b>{_sel_date}</b>\u00b7 Pr\u00e9cipitations",
                        font=dict(size=10, color=MUTED), x=0, pad=dict(l=4),
                    ),
                )
                st.plotly_chart(
                    _fig1, use_container_width=True,
                    config={
                        "displayModeBar": True,
                        "modeBarButtonsToRemove": [
                            "lasso2d", "select2d", "autoScale2d",
                            "hoverClosestMapbox",
                        ],
                        "displaylogo": False,
                        "toImageButtonOptions": {
                            "format": "png",
                            "filename": f"precip_{_sel_date}",
                        },
                    },
                )

        # ── Panneau d'information de l'evenement ──────────────────────────────
        with _minfo:
            st.markdown(
                '<p class="pnl-ttl" style="margin-bottom:8px">'
                '&#128203; Fiche evenement</p>',
                unsafe_allow_html=True,
            )

            # Calcul region la plus intense depuis les pixels
            if len(_ev_sel) > 0:
                _reg_stats = (
                    _ev_sel.groupby("region")["precipitation_mm"]
                    .agg(max_p="max", mean_p="mean", n="count")
                    .sort_values("max_p", ascending=False)
                )
                _top_reg      = _reg_stats.index[0] if len(_reg_stats) else "-"
                _top_reg_max  = float(_reg_stats.iloc[0]["max_p"]) if len(_reg_stats) else 0
                _top_reg_mean = float(_reg_stats.iloc[0]["mean_p"]) if len(_reg_stats) else 0
            else:
                _top_reg, _top_reg_max, _top_reg_mean = "-", 0, 0

            # Extraction des stats depuis summary
            if _ev_summary is not None:
                _row_inf = _ev_summary[_ev_summary["event_date"] == _sel_date]
                _ri = _row_inf.iloc[0] if not _row_inf.empty else None
            else:
                _ri = None

            def _sv(key, fmt=None, default="-"):
                if _ri is None:
                    return default
                v = _ri.get(key, None)
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return default
                return fmt.format(v) if fmt else str(v)

            _pmax_v    = _sv("precip_max",    "{:.1f}")
            _pmoy_v    = _sv("precip_mean",   "{:.1f}")
            _amax_v    = _sv("anomaly_max",   "{:.1f}")
            _amoy_v    = _sv("anomaly_mean",  "{:.1f}")
            _ext_pct_v = float(_sv("extreme_percentage", "{}", "0"))
            _mregion_v = _sv("main_region")
            _etype_v   = _sv("event_type")
            _extent_v  = _sv("spatial_extent")
            _ilevel_v  = _sv("intensity_level")
            _ph_raw    = _sv("season_phase", default="")
            _PHASE_FR2 = {
                "Phase_1_debut":  "Phase 1 &mdash; D&eacute;but (Mai-Juin)",
                "Phase_2_pleine": "Phase 2 &mdash; Pleine (Juil-Ao&ucirc;t)",
                "Phase_3_fin":    "Phase 3 &mdash; Fin (Sep-Oct)",
            }
            _ph_lbl  = _PHASE_FR2.get(_ph_raw, _ph_raw)
            _ph_clr  = PHASE_C.get(_ph_raw, MUTED)
            _c0_inf  = _get_crit0(_sel_date)
            _cr_fg2, _cr_bg2 = _CRIT_COLORS.get(_c0_inf, (INDIGO, "rgba(79,70,229,0.13)"))
            _cr_lbl2 = _CRIT_FR.get(_c0_inf, _c0_inf)

            # Barres de progression inline
            def _pbar(pct, color, bg=BORDER):
                w = min(max(float(pct), 0), 100)
                return (
                    f'<div style="height:6px;background:{bg};border-radius:99px;'
                    f'margin-top:4px;overflow:hidden;">'
                    f'<div style="width:{w:.1f}%;height:100%;background:{color};'
                    f'border-radius:99px;"></div></div>'
                )

            # Ligne metrique compacte (fonts WCAG AA : min 0.75rem)
            def _mrow(label, value, unit="", color=TEXT):
                return (
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:baseline;padding:6px 0;'
                    f'border-bottom:1px solid {BORDER};">'
                    f'<span style="font-size:0.75rem;color:{MUTED}">{label}</span>'
                    f'<span style="font-size:0.85rem;font-weight:700;color:{color}">'
                    f'{value}'
                    f'<span style="font-size:0.72rem;font-weight:500;color:{MUTED};'
                    f'margin-left:2px">{unit}</span></span></div>'
                )

            def _section(title, icon, color):
                return (
                    f'<div style="display:flex;align-items:center;gap:7px;'
                    f'margin:14px 0 6px 0;">'
                    f'<div style="width:3px;height:14px;background:{color};'
                    f'border-radius:2px;flex-shrink:0"></div>'
                    f'<span style="font-size:0.72rem;font-weight:700;color:{MUTED};'
                    f'text-transform:uppercase;letter-spacing:0.06em">'
                    f'{icon}&nbsp;{title}</span></div>'
                )

            # Header de la carte : accent couleur du critere, pas de gradient lourd
            _html_header = (
                f'<div style="border-bottom:3px solid {_cr_fg2};'
                f'padding:14px 16px 12px 16px;background:{_cr_bg2};">'
                f'<div style="display:flex;align-items:flex-start;'
                f'justify-content:space-between;gap:8px;">'
                f'<div>'
                f'<p style="margin:0 0 2px 0;font-size:0.72rem;font-weight:700;'
                f'color:{_cr_fg2};text-transform:uppercase;letter-spacing:0.07em">'
                f'{_cr_lbl2}</p>'
                f'<p style="margin:0 0 6px 0;font-size:1.05rem;font-weight:800;'
                f'color:{TEXT};line-height:1.2">{_sel_date}</p>'
                f'</div>'
                f'<span style="background:{CARD};color:{MUTED};font-size:0.72rem;'
                f'font-weight:600;border-radius:6px;padding:3px 9px;'
                f'white-space:nowrap;border:1px solid {BORDER}">{_etype_v}</span>'
                f'</div>'
                f'<span style="background:{_ph_clr}22;color:{_ph_clr};font-size:0.72rem;'
                f'font-weight:700;border-radius:6px;padding:3px 9px;display:inline-block">'
                f'{_ph_lbl}</span>'
                f'</div>'
            )
            _html_body = (
                f'<div style="padding:8px 16px 16px 16px;">'
                + _mrow("Pr&#233;cip. max", _pmax_v, "mm", BLUE)
                + _mrow("Pr&#233;cip. moyenne", _pmoy_v, "mm")
                + _mrow("Anomalie max", _amax_v, "&#963;", "#7C3AED")
                + _mrow("Anomalie moyenne", _amoy_v, "&#963;")
                + f'<div style="padding:7px 0 4px 0;border-bottom:1px solid {BORDER};">'
                + f'<div style="display:flex;justify-content:space-between;'
                + f'align-items:baseline;margin-bottom:3px;">'
                + f'<span style="font-size:0.75rem;color:{MUTED}">Couverture spatiale</span>'
                + f'<span style="font-size:0.85rem;font-weight:700;color:{AMBER}">{_ext_pct_v:.1f}%</span>'
                + f'</div>' + _pbar(_ext_pct_v, AMBER) + f'</div>'
                + _mrow("R&#233;gion principale", _mregion_v)
                + f'<div style="padding:5px 0;border-bottom:1px solid {BORDER};">'
                + f'<div style="display:flex;justify-content:space-between;'
                + f'align-items:baseline;margin-bottom:3px;">'
                + f'<span style="font-size:0.75rem;color:{MUTED}">R&#233;gion la plus intense</span>'
                + f'<span style="font-size:0.85rem;font-weight:700;color:{ROSE}">{_top_reg}</span>'
                + f'</div>'
                + f'<div style="font-size:0.72rem;color:{MUTED};">'
                + f'max {_top_reg_max:.1f} mm &nbsp;&#183;&nbsp; moy. {_top_reg_mean:.1f} mm</div>'
                + f'</div>'
                + _section("Classification", "&#127981;", EMERALD)
                + f'<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:5px;">'
                + f'<span style="background:{BG};color:{MUTED};font-size:0.72rem;'
                + f'font-weight:600;border-radius:6px;padding:3px 9px;'
                + f'border:1px solid {BORDER}">{_extent_v}</span>'
                + f'<span style="background:{BG};color:{MUTED};font-size:0.72rem;'
                + f'font-weight:600;border-radius:6px;padding:3px 9px;'
                + f'border:1px solid {BORDER}">{_ilevel_v}</span>'
                + f'</div>'
                + f'</div>'
            )
            _html_card = (
                f'<div style="background:{CARD};border:1px solid {BORDER};'
                f'border-radius:14px;overflow:hidden;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.05);">'
                + _html_header + _html_body +
                f'</div>'
            )
            st.html(_html_card)

    # ── Separateur section analyses ───────────────────────────────────────────
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;margin:28px 0 18px 0;">
      <div style="height:2px;width:28px;background:linear-gradient(90deg,{INDIGO},{BLUE});
                  border-radius:99px;flex-shrink:0;"></div>
      <span style="font-size:0.70rem;font-weight:700;color:{MUTED};text-transform:uppercase;
                   letter-spacing:0.08em;white-space:nowrap">Analyse temporelle &amp; distribution</span>
      <div style="height:1px;flex:1;background:{BORDER};"></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Graphique principal + Donut ───────────────────────────────────────────
    if is_mobile:
        lc, rc = st.container(), st.container()
    elif is_tablet:
        lc, rc = st.columns([2, 1], gap="medium")
    else:
        lc, rc = st.columns([2.4, 1], gap="medium")

    with lc:

        hh, hs = st.columns([3, 1])
        with hh:
            st.markdown(
                '<p class="pnl-ttl">Evolution annuelle des evenements extremes</p>'
                '<p class="pnl-sub">Nombre d\'evenements par annee · decompose par phase saisonniere</p>',
                unsafe_allow_html=True,
            )
        with hs:
            view = st.selectbox("vue", ["Empile", "Groupe", "Total"],
                                label_visibility="collapsed")

        by_yr_df   = dff.groupby("year").size().reset_index(name="n")
        avg_yr_n   = by_yr_df["n"].mean()
        max_yr_row = by_yr_df.loc[by_yr_df["n"].idxmax()]
        min_yr_row = by_yr_df.loc[by_yr_df["n"].idxmin()]
        slope      = np.polyfit(by_yr_df["year"], by_yr_df["n"], 1)[0]

        st.markdown(f"""
        <div class="chips">
          <div class="chip">Moy. annuelle &nbsp;<b>{avg_yr_n:.0f} evt/an</b></div>
          <div class="chip">Record &nbsp;<b>{int(max_yr_row['year'])} — {int(max_yr_row['n'])} evt</b></div>
          <div class="chip">Annee calme &nbsp;<b>{int(min_yr_row['year'])} — {int(min_yr_row['n'])} evt</b></div>
          <div class="chip">Tendance &nbsp;<b>{"+" if slope>=0 else ""}{slope:.2f} evt/an</b></div>
        </div>
        """, unsafe_allow_html=True)

        by_yp = dff.groupby(["year", "phase"]).size().reset_index(name="n")
        fig   = go.Figure()

        if view == "Total":
            tot = by_yp.groupby("year")["n"].sum().reset_index()
            fig.add_trace(go.Bar(
                x=tot["year"], y=tot["n"],
                marker_color=INDIGO, marker_line_width=0,
                hovertemplate="<b>%{x}</b> : %{y} evenements<extra></extra>",
                showlegend=False,
            ))
            z = np.polyfit(tot["year"], tot["n"], 1)
            fig.add_trace(go.Scatter(
                x=tot["year"], y=np.poly1d(z)(tot["year"]),
                mode="lines", name="Tendance",
                line=dict(color=ROSE, width=2, dash="dot"),
            ))
        else:
            bmode = "stack" if view == "Empile" else "group"
            for ph in ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]:
                sub = by_yp[by_yp["phase"] == ph]
                fig.add_trace(go.Bar(
                    x=sub["year"], y=sub["n"],
                    name=PHASE_L[ph],
                    marker_color=PHASE_C[ph], marker_line_width=0,
                    hovertemplate=f"<b>{PHASE_L[ph]}</b> · %{{x}}: %{{y}} evt<extra></extra>",
                ))
            fig.update_layout(barmode=bmode)
            tot = by_yp.groupby("year")["n"].sum().reset_index()
            z   = np.polyfit(tot["year"], tot["n"], 1)
            fig.add_trace(go.Scatter(
                x=tot["year"], y=np.poly1d(z)(tot["year"]),
                mode="lines", name="Tendance",
                line=dict(color=TEXT, width=1.6, dash="dot"),
            ))

        plotly_base(fig, h=220 if is_mobile else (260 if is_tablet else 295))
        fig.update_layout(bargap=0.2)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Donut ─────────────────────────────────────────────────────────────────
    with rc:
        st.markdown(
            '<p class="pnl-ttl">Repartition par Phase</p>'
            '<p class="pnl-sub">Distribution des 3 phases saisonnieres</p>',
            unsafe_allow_html=True,
        )

        ph_order = ["Phase_2_pleine", "Phase_3_fin", "Phase_1_debut"]
        ph_cnt   = {p: len(dff[dff["phase"] == p]) for p in ph_order}

        fig_d = go.Figure(go.Pie(
            labels=[PHASE_L[p] for p in ph_order],
            values=[ph_cnt[p]  for p in ph_order],
            hole=0.66,
            marker=dict(
                colors=[PHASE_C[p] for p in ph_order],
                line=dict(color="white", width=2.5),
            ),
            textinfo="none", sort=False,
            hovertemplate="<b>%{label}</b><br>%{value} evt (%{percent})<extra></extra>",
        ))
        fig_d.add_annotation(
            text=f"<b>{n_total}</b>", x=0.5, y=0.58,
            font=dict(size=22, color=TEXT, family="Inter"), showarrow=False,
        )
        fig_d.add_annotation(
            text="evenements", x=0.5, y=0.41,
            font=dict(size=10, color=MUTED, family="Inter"), showarrow=False,
        )
        fig_d.update_layout(
            height=210, showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_d, use_container_width=True, config={"displayModeBar": False})

        for ph in ph_order:
            n   = ph_cnt[ph]
            pct = 100 * n / n_total if n_total else 0
            st.markdown(f"""
            <div class="leg-row">
              <div class="leg-dot" style="background:{PHASE_C[ph]}"></div>
              <span class="leg-lbl">{PHASE_L[ph]}</span>
              <span class="leg-pct">{pct:.0f}%</span>
              <b class="leg-val">{n}</b>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Ligne basse ────────────────────────────────────────────────────────────
    if is_mobile:
        bc1, bc2 = st.container(), st.container()
    else:
        bc1, bc2 = st.columns(2, gap="medium")

    with bc1:
        st.markdown(
            '<p class="pnl-ttl">Distribution mensuelle</p>'
            '<p class="pnl-sub">Evenements par mois &middot; phases color&eacute;es</p>',
            unsafe_allow_html=True,
        )
        MNAMES = {1:"Jan",2:"Fev",3:"Mar",4:"Avr",5:"Mai",6:"Jun",
                  7:"Jul",8:"Aou",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        # Couleur par mois selon la phase (Mai-Jun=P1, Jul-Aou=P2, Sep-Oct=P3)
        _MONTH_PHASE_CLR = {
            1: MUTED,  2: MUTED,  3: MUTED,  4: MUTED,
            5: BLUE,   6: BLUE,
            7: INDIGO, 8: INDIGO,
            9: AMBER,  10: AMBER,
            11: MUTED, 12: MUTED,
        }
        by_m = dff.groupby("month").size().reset_index(name="n")
        by_m["mois"]  = by_m["month"].map(MNAMES)
        by_m["color"] = by_m["month"].map(_MONTH_PHASE_CLR)

        fig_m = go.Figure(go.Bar(
            x=by_m["mois"], y=by_m["n"],
            marker=dict(
                color=by_m["color"],
                line=dict(width=0),
            ),
            hovertemplate="<b>%{x}</b> : %{y} evenements<extra></extra>",
        ))
        avg_m = by_m["n"].mean()
        fig_m.add_hline(
            y=avg_m, line=dict(color=ROSE, width=1.4, dash="dot"),
            annotation_text=f"  moy {avg_m:.0f}",
            annotation_font=dict(size=10, color=ROSE),
            annotation_position="top right",
        )
        # Annotations de phases en bas du graphique
        _ph_annots = [
            ("P1", "Mai-Jun",  5.0,  BLUE),
            ("P2", "Jul-Aou",  7.0,  INDIGO),
            ("P3", "Sep-Oct",  9.0,  AMBER),
        ]
        for _pa_code, _, _pa_x, _pa_clr in _ph_annots:
            fig_m.add_annotation(
                x=MNAMES[int(_pa_x)], y=0,
                text=f"<b>{_pa_code}</b>",
                font=dict(size=9, color=_pa_clr),
                showarrow=False, yref="paper", yanchor="top",
                yshift=-14,
            )
        plotly_base(fig_m, h=200 if is_mobile else 245)
        fig_m.update_layout(showlegend=False, bargap=0.28,
                            margin=dict(l=2, r=2, t=10, b=28))
        st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": False})

    with bc2:
        st.markdown(
            '<p class="pnl-ttl">Top R&eacute;gions Touch&eacute;es</p>'
            '<p class="pnl-sub">Classement des 8 premi&egrave;res r&eacute;gions'
            ' &middot; sparkline tendance</p>',
            unsafe_allow_html=True,
        )
        top = (dff["centroid_region"]
               .value_counts().head(8)
               .reset_index()
               .rename(columns={"centroid_region": "region", "count": "n"}))
        max_n = top["n"].max()
        GRAD  = ["#4F46E5","#6366F1","#818CF8","#A5B4FC",
                 "#C7D2FE","#DDE3FD","#EEF2FF","#F5F3FF"]

        # Sparkline par region : n evenements par annee (derniers 10 ans)
        _rg_yr = (
            dff.groupby(["centroid_region", "year"])
            .size()
            .reset_index(name="n_yr")
        )
        _rg_allyrs = list(range(max(year_range[0], year_range[1] - 9),
                                year_range[1] + 1))

        for i, row in top.iterrows():
            bar_w = 100 * row["n"] / max_n
            pct   = 100 * row["n"] / n_total
            # sparkline tendance (10 dernieres annees)
            _rg_sub = _rg_yr[_rg_yr["centroid_region"] == row["region"]]
            _rg_sp  = [
                int(_rg_sub[_rg_sub["year"] == y]["n_yr"].values[0])
                if y in _rg_sub["year"].values else 0
                for y in _rg_allyrs
            ]
            _sp_svg = svg_spark(_rg_sp, w=60, h=22, color=GRAD[min(i, 7)])
            st.markdown(f"""
            <div class="rg-row" style="align-items:center;">
              <span class="rg-rk">#{i+1}</span>
              <span class="rg-nm">{row['region']}</span>
              <div style="flex-shrink:0;width:60px;opacity:0.85">{_sp_svg}</div>
              <div class="rg-bg" style="margin-left:6px;">
                <div class="rg-bar"
                     style="width:{bar_w:.0f}%;background:{GRAD[min(i,7)]}"></div>
              </div>
              <span class="rg-n">{row['n']}</span>
              <span class="rg-pct">{pct:.1f}%</span>
            </div>
            """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE TELECONNEXIONS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Teleconnexions":

    with st.spinner("Chargement des teleconnexions..."):
        tc_data = load_telecon()

    PHASE_TC_L = {
        "Phase_1_debut":  "Phase 1 - Debut (Mai-Jun)",
        "Phase_2_pleine": "Phase 2 - Pleine (Jul-Aou)",
        "Phase_3_fin":    "Phase 3 - Fin (Sep-Oct)",
        "Toutes phases":  "Toutes les phases",
    }
    METRIC_L = {
        "max_precip":       "Precipitation max (mm)",
        "mean_precip":      "Precipitation moyenne (mm)",
        "max_anomaly":      "Anomalie max (sigma)",
        "coverage_percent": "Couverture spatiale (%)",
        "n_events":         "Nombre d'evenements",
    }
    LAGS_ALL = [0, 1, 2, 3, 6, 9, 12]

    IDX_GROUP = {
        "ENSO":             ["Nino12", "Nino3", "Nino34", "Nino4"],
        "Ocean Indien":     ["IOD", "IOBM"],
        "Atlantique Trop.": ["TNA", "TSA", "ATL3", "AMM"],
        "Atlantique Multi": ["AMO"],
    }

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Teleconnexions</b></p>
        <h1 class="pg-ttl">Teleconnexions SST - Precipitations Extremes</h1>
        <p class="pg-sub">
          Correlations Pearson &amp; Spearman · Correction AR1 (p<sub>neff</sub>)
          &nbsp;&middot;&nbsp; Lags 0-12 mois · 11 indices SST
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Filtres inline ─────────────────────────────────────────────────────
    fa, fb, fc, fd, fe = st.columns([2, 2, 1.5, 1.5, 2], gap="small")
    with fa:
        tc_phase = st.selectbox(
            "Phase saisonniere",
            options=list(PHASE_TC_L.keys()),
            format_func=lambda x: PHASE_TC_L[x],
        )
    with fb:
        tc_metric = st.selectbox(
            "Metrique",
            options=list(METRIC_L.keys()),
            format_func=lambda x: METRIC_L[x],
        )
    with fc:
        tc_type = st.selectbox("Type", ["Pearson", "Spearman"])
    with fd:
        show_sig = st.checkbox("Sig. seulement", value=False)
    with fe:
        use_p_brute = st.checkbox("Etoiles p brute", value=False,
                                  help="Coche : etoiles basees sur p_value brute (non corrigee AR1)\n"
                                       "Decochez : etoiles basees sur p_neff (corrige autocorrelation AR1)")

    r_col       = "pearson_r"   if tc_type == "Pearson" else "spearman_r"
    sig_col     = "sig_pearson" if tc_type == "Pearson" else "sig_spearman"
    p_neff_col  = "pearson_p_neff" if tc_type == "Pearson" else "spearman_p_neff"
    p_nom_col   = "pearson_p"      if tc_type == "Pearson" else "spearman_p"
    sig_nom_col = "sig_pearson_nom" if tc_type == "Pearson" else "sig_spearman_nom"

    df_tc = tc_data.get(tc_phase, pd.DataFrame())
    if df_tc.empty:
        st.warning("Donnees non disponibles pour cette phase.")
        st.stop()

    df_m = df_tc[df_tc["metric"] == tc_metric].copy()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Heatmap + Top correlations ─────────────────────────────────────────
    hm_col, top_col = st.columns([3, 1.3], gap="medium")

    with hm_col:
        # Sous-titre dynamique selon le mode etoiles choisi
        if use_p_brute:
            star_label = 'p<sub>brute</sub> (non corrigee)'
            star_color = "#60A5FA"
        else:
            star_label = 'p<sub>neff</sub> (AR1 Chelton)'
            star_color = "#F59E0B"
        st.markdown(
            '<p class="pnl-ttl">Heatmap des correlations par indice et lag</p>'
            f'<p class="pnl-sub">'
            f'Couleur = coefficient r &nbsp;&middot;&nbsp; Etoiles = {star_label} : '
            f'<b style="color:{star_color};">*</b> &lt;0,05 &nbsp; '
            f'<b style="color:{star_color};">**</b> &lt;0,01 &nbsp; '
            f'<b style="color:{star_color};">***</b> &lt;0,001'
            f'</p>',
            unsafe_allow_html=True,
        )

        all_indices = [i for grp in IDX_GROUP.values() for i in grp]
        lags_shown  = LAGS_ALL

        # Matrices r, p_nom (brute), p_neff (AR1) et n_eff
        z_mat, p_nom_mat, p_mat, neff_mat = [], [], [], []
        for hm_idx in all_indices:
            row_z, row_pnom, row_p, row_neff = [], [], [], []
            for lag in lags_shown:
                sub = df_m[(df_m["index"] == hm_idx) & (df_m["lag_months"] == lag)]
                if sub.empty:
                    row_z.append(None)
                    row_pnom.append(None)
                    row_p.append(None)
                    row_neff.append(None)
                else:
                    row_z.append(float(sub[r_col].values[0]))
                    pnom = sub[p_nom_col].values[0] if p_nom_col in sub.columns else None
                    row_pnom.append(float(pnom) if pnom is not None and pd.notna(pnom) else None)
                    pv = sub[p_neff_col].values[0] if p_neff_col in sub.columns else None
                    row_p.append(float(pv) if pv is not None and pd.notna(pv) else None)
                    ne = sub["n_eff"].values[0] if "n_eff" in sub.columns else None
                    row_neff.append(float(ne) if ne is not None and pd.notna(ne) else None)
            z_mat.append(row_z)
            p_nom_mat.append(row_pnom)
            p_mat.append(row_p)
            neff_mat.append(row_neff)

        # Matrice active pour les etoiles selon le checkbox
        p_active_mat = p_nom_mat if use_p_brute else p_mat

        # Valeur r dans chaque cellule
        cell_text = []
        for ri in range(len(all_indices)):
            row_t = []
            for ci in range(len(lags_shown)):
                r_v = z_mat[ri][ci]
                row_t.append(f"{r_v:+.2f}" if r_v is not None else "")
            cell_text.append(row_t)

        # Customdata : [p_nom, p_neff, n_eff] pour le hover
        customdata_mat = []
        for ri in range(len(all_indices)):
            row_cd = []
            for ci in range(len(lags_shown)):
                pn  = p_nom_mat[ri][ci]
                pe  = p_mat[ri][ci]
                ne  = neff_mat[ri][ci]
                row_cd.append([
                    f"{pn:.4f}" if pn is not None else "N/A",
                    f"{pe:.4f}" if pe is not None else "N/A",
                    f"{int(ne)}" if ne is not None else "N/A",
                ])
            customdata_mat.append(row_cd)

        x_labels = [f"Lag {l}m" for l in lags_shown]

        fig_hm = go.Figure(go.Heatmap(
            z=z_mat,
            x=x_labels,
            y=all_indices,
            text=cell_text,
            customdata=customdata_mat,
            texttemplate="%{text}",
            textfont=dict(size=10, color="white"),
            colorscale=[
                [0.0,  "#7F1D1D"],
                [0.2,  "#C2410C"],
                [0.4,  "#FB923C"],
                [0.48, "#FED7AA"],
                [0.5,  "#F8FAFC"],
                [0.52, "#BAE6FD"],
                [0.6,  "#0EA5E9"],
                [0.8,  "#1D4ED8"],
                [1.0,  "#1E3A8A"],
            ],
            zmid=0,
            zmin=-0.5, zmax=0.5,
            colorbar=dict(
                title=dict(text="r", side="right", font=dict(size=11, color=MUTED)),
                thickness=12, len=0.85,
                tickvals=[-0.4, -0.2, 0, 0.2, 0.4],
                ticktext=["-0.4", "-0.2", "0", "0.2", "0.4"],
                tickfont=dict(size=10, color=MUTED),
                outlinewidth=0,
            ),
            hovertemplate=(
                "<b>%{y}</b> · %{x}<br>"
                "r = %{z:.3f}<br>"
                "p brute = %{customdata[0]}<br>"
                "p_neff (AR1) = %{customdata[1]}<br>"
                "n_eff = %{customdata[2]}"
                "<extra></extra>"
            ),
        ))

        # Annotations etoiles basees sur la matrice active
        annotations = []
        for ri, hm_idx in enumerate(all_indices):
            for ci, lag in enumerate(lags_shown):
                p_v = p_active_mat[ri][ci]
                if p_v is None or pd.isna(p_v):
                    continue
                if p_v < 0.001:
                    star_txt = "***"
                elif p_v < 0.01:
                    star_txt = "**"
                elif p_v < 0.05:
                    star_txt = "*"
                else:
                    continue
                annotations.append(dict(
                    x=x_labels[ci],
                    y=hm_idx,
                    text=f"<b>{star_txt}</b>",
                    showarrow=False,
                    xanchor="right",
                    yanchor="bottom",
                    xshift=18,
                    yshift=-2,
                    font=dict(size=15, color="#000000", family="Inter,sans-serif"),
                ))

        # Lignes de separation des groupes
        for sep in [4, 6, 10]:
            fig_hm.add_hline(
                y=sep - 0.5,
                line=dict(color=BORDER, width=1.5, dash="dot"),
            )

        fig_hm.update_layout(
            height=380,
            margin=dict(l=0, r=0, t=4, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter,sans-serif", size=11, color=MUTED),
            xaxis=dict(
                side="top",
                tickfont=dict(size=11, color=MUTED),
                showgrid=False, zeroline=False,
            ),
            yaxis=dict(
                tickfont=dict(size=11, color=TEXT),
                showgrid=False, zeroline=False,
                autorange="reversed",
            ),
            annotations=annotations,
        )
        st.plotly_chart(fig_hm, use_container_width=True, config={"displayModeBar": False})

    # ── Top correlations ───────────────────────────────────────────────────
    with top_col:
        st.markdown(
            '<p class="pnl-ttl">Top 8 correlations</p>'
            '<p class="pnl-sub">Valeurs absolues · tous lags · '
            'etoiles = p<sub>neff</sub> sur chaque ligne (comme la heatmap)</p>',
            unsafe_allow_html=True,
        )

        df_top = df_m.copy()
        if show_sig:
            if p_neff_col in df_top.columns:
                df_top = df_top[df_top[p_neff_col].apply(_sig_from_p_neff).ne("")]
            else:
                df_top = df_top.iloc[0:0]
        df_top = df_top.assign(abs_r=df_top[r_col].abs()).nlargest(8, "abs_r")

        if df_top.empty:
            st.markdown(
                f'<p style="color:{MUTED};font-size:0.78rem;margin-top:12px;">'
                'Aucun resultat.</p>', unsafe_allow_html=True
            )
        else:
            GRAD_POS = ["#1E3A8A","#1D4ED8","#3B82F6","#93C5FD"]
            GRAD_NEG = ["#7F1D1D","#B91C1C","#EF4444","#FCA5A5"]
            for i, rec in enumerate(df_top.to_dict("records")):
                idx_name = rec["index"]
                lag_v    = int(rec["lag_months"])
                r_val    = rec[r_col]
                is_pos   = r_val >= 0
                bar_clr  = GRAD_POS[min(i, 3)] if is_pos else GRAD_NEG[min(i, 3)]
                bar_w    = int(abs(r_val) / 0.5 * 100)
                r_clr    = "#1D4ED8" if is_pos else "#B91C1C"
                r_str    = f"{r_val:+.3f}"
                badge    = _sig_from_p_neff(rec.get(p_neff_col))
                sig_badge = ""
                if badge:
                    sig_badge = (
                        '<span style="font-size:0.63rem;background:rgba(245,158,11,0.18);'
                        'color:#D97706;border-radius:4px;padding:1px 5px;'
                        f'font-weight:700;">{badge}</span>'
                    )
                st.markdown(
                    f'<div style="padding:7px 0;border-bottom:1px solid {BORDER};">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">'
                    f'<span style="font-size:0.75rem;font-weight:600;color:{TEXT};">'
                    f'{idx_name} &nbsp;<span style="color:{MUTED};font-weight:400;">lag {lag_v}m</span></span>'
                    f'<div style="display:flex;align-items:center;gap:4px;">'
                    f'{sig_badge}'
                    f'<span style="font-size:0.8rem;font-weight:700;color:{r_clr};">{r_str}</span>'
                    f'</div></div>'
                    f'<div style="background:{BG};border-radius:99px;height:4px;">'
                    f'<div style="width:{bar_w}%;height:4px;border-radius:99px;background:{bar_clr};"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Profil de correlation par indice ────────────────────────────────────
    lc2, rc2 = st.columns([1.8, 1], gap="medium")

    with lc2:
        st.markdown(
            '<p class="pnl-ttl">Profil de correlation par indice (r vs lag)</p>'
            '<p class="pnl-sub">Evolution du coefficient r en fonction du decalage temporel'
            ' &nbsp;&middot;&nbsp; <span style="color:#F59E0B;">&#9733;</span> = significatif '
            '(p<sub>neff</sub> : 0,05 / 0,01 / 0,001)</p>',
            unsafe_allow_html=True,
        )

        sel_indices = st.multiselect(
            "Indices a afficher",
            options=all_indices,
            default=["Nino34", "IOBM", "AMO", "TNA"],
            label_visibility="collapsed",
        )

        fig_line = go.Figure()
        COLORS_LINE = [INDIGO, BLUE, AMBER, EMERALD, ROSE,
                       "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#64748B", "#84CC16"]

        for ci, idx in enumerate(sel_indices):
            sub_idx = df_m[df_m["index"] == idx].sort_values("lag_months").reset_index(drop=True)
            if sub_idx.empty:
                continue
            clr = COLORS_LINE[ci % len(COLORS_LINE)]

            # Symbole et taille par point selon p_neff (aligne sur sig_*)
            symbols, sizes, texts, hover_extra = [], [], [], []
            for _, row in sub_idx.iterrows():
                p = row.get(p_neff_col, float("nan"))
                if pd.notna(p) and p < 0.001:
                    symbols.append("star"); sizes.append(18)
                    texts.append("***"); hover_extra.append(f"*** p_neff={p:.4f}")
                elif pd.notna(p) and p < 0.01:
                    symbols.append("star"); sizes.append(16)
                    texts.append("**"); hover_extra.append(f"** p_neff={p:.4f}")
                elif pd.notna(p) and p < 0.05:
                    symbols.append("star"); sizes.append(14)
                    texts.append("*"); hover_extra.append(f"* p_neff={p:.4f}")
                else:
                    symbols.append("circle"); sizes.append(6)
                    texts.append(""); hover_extra.append("")

            has_sig = any(s == "star" for s in symbols)
            fig_line.add_trace(go.Scatter(
                x=sub_idx["lag_months"].tolist(),
                y=sub_idx[r_col].tolist(),
                mode="lines+markers+text" if has_sig else "lines+markers",
                name=idx,
                line=dict(color=clr, width=2),
                marker=dict(
                    size=sizes,
                    color=clr,
                    symbol=symbols,
                    line=dict(color="white", width=1),
                ),
                text=texts if has_sig else None,
                textposition="top center",
                textfont=dict(size=10, color=AMBER, family="Inter,sans-serif"),
                customdata=hover_extra,
                hovertemplate=(
                    f"<b>{idx}</b> · lag %{{x}}m<br>"
                    "r = %{y:.3f}%{customdata}<extra></extra>"
                ),
            ))

        fig_line.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
        fig_line.add_hrect(y0=-0.2, y1=0.2, fillcolor="rgba(100,116,139,0.05)",
                           line_width=0)

        plotly_base(fig_line, h=260)
        fig_line.update_layout(
            xaxis=dict(
                tickvals=LAGS_ALL,
                ticktext=[f"{l}m" for l in LAGS_ALL],
                title=dict(text="Decalage (mois)", font=dict(size=11, color=MUTED)),
            ),
            yaxis=dict(
                title=dict(text="r", font=dict(size=11, color=MUTED)),
                zeroline=True, zerolinecolor=BORDER, zerolinewidth=1,
                range=[-0.6, 0.6],
            ),
        )
        st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})

    with rc2:
        st.markdown(
            '<p class="pnl-ttl">Tableau de synthese</p>'
            '<p class="pnl-sub">Meilleur lag par indice (|r| max) · '
            'Sig = p<sub>neff</sub> sur cette ligne (pas sur un autre lag)</p>',
            unsafe_allow_html=True,
        )

        # Tableau : pour chaque indice, meilleur lag
        rows_synth = []
        for idx in all_indices:
            sub_idx = df_m[df_m["index"] == idx].copy()
            if sub_idx.empty:
                continue
            best = sub_idx.loc[sub_idx[r_col].abs().idxmax()]
            r_val  = best[r_col]
            lag_v  = int(best["lag_months"])
            pnb    = best[p_neff_col] if p_neff_col in best.index else float("nan")
            rows_synth.append((idx, r_val, lag_v, pnb))

        rows_synth.sort(key=lambda x: abs(x[1]), reverse=True)

        st.markdown(f"""
        <div style="background:{BG};border-radius:8px;padding:6px 10px;
                    margin-bottom:10px;display:flex;font-size:0.67rem;
                    font-weight:700;color:{MUTED};text-transform:uppercase;
                    letter-spacing:0.6px;">
          <span style="flex:1.2;">Indice</span>
          <span style="width:50px;text-align:center;">Lag</span>
          <span style="width:60px;text-align:right;">r max</span>
          <span style="width:30px;text-align:center;">Sig</span>
        </div>
        """, unsafe_allow_html=True)

        for idx, r_val, lag_v, p_neff_row in rows_synth:
            is_pos = r_val >= 0
            r_clr  = "#1D4ED8" if is_pos else "#B91C1C"
            sig_disp = _sig_from_p_neff(p_neff_row)
            sig_html = ""
            if sig_disp:
                sig_html = (
                    f'<span style="font-size:0.7rem;color:#92400E;'
                    f'font-weight:700;">{sig_disp}</span>'
                )
            bar_pct = int(abs(r_val) / 0.5 * 100)
            st.markdown(f"""
            <div style="padding:6px 0;border-bottom:1px solid {BORDER};">
              <div style="display:flex;align-items:center;">
                <span style="flex:1.2;font-size:0.78rem;font-weight:600;
                             color:{TEXT};">{idx}</span>
                <span style="width:50px;text-align:center;font-size:0.72rem;
                             color:{MUTED};">lag {lag_v}m</span>
                <span style="width:60px;text-align:right;font-size:0.8rem;
                             font-weight:700;color:{r_clr};">{r_val:+.3f}</span>
                <span style="width:30px;text-align:center;">{sig_html}</span>
              </div>
              <div style="background:{BG};border-radius:99px;height:3px;
                          margin-top:4px;margin-left:0;">
                <div style="width:{bar_pct}%;height:3px;border-radius:99px;
                            background:{'#3B82F6' if is_pos else '#EF4444'};"></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # Legende significance
        st.markdown(f"""
        <div style="margin-top:12px;padding:8px 10px;background:{BG};
                    border-radius:8px;font-size:0.68rem;color:{MUTED};
                    line-height:1.8;">
          <b style="color:{TEXT};">Significativite (correction AR1)</b><br>
          p<sub>neff</sub> = p-value apres degres de liberte effectifs (Chelton 1983).<br>
          * &lt; 0,05 &nbsp; ** &lt; 0,01 &nbsp; *** &lt; 0,001<br>
          <i>Sig. nominale</i> : p brut (sans AR1), voir KPI ci-dessous.
        </div>
        """, unsafe_allow_html=True)

    # ── Metriques KPI ──────────────────────────────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    df_all_m = df_m.copy()
    n_tests   = len(df_all_m)
    _s_nom = (
        df_all_m[sig_nom_col].fillna("").astype(str).str.strip().ne("")
        if sig_nom_col in df_all_m.columns
        else pd.Series([False] * len(df_all_m))
    )
    n_sig_nom = int(_s_nom.sum())
    if p_neff_col in df_all_m.columns and not df_all_m.empty:
        n_sig_ar1 = int(df_all_m[p_neff_col].apply(_sig_from_p_neff).ne("").sum())
    else:
        n_sig_ar1 = 0
    best_row = df_all_m.loc[df_all_m[r_col].abs().idxmax()] if not df_all_m.empty else None
    best_r   = best_row[r_col] if best_row is not None else 0

    mk1, mk2, mk3, mk4 = st.columns(4, gap="small")
    kpi_tc = [
        (mk1, f"background:rgba(79,70,229,0.13)", "Tests totaux", f"{n_tests}", "t-indigo",
         f"{len(all_indices)} indices x {len(LAGS_ALL)} lags"),
        (mk2, f"background:rgba(16,185,129,0.13)", "Sig. nominale", f"{int(n_sig_nom)}", "t-green",
         "p brut (Pearson/Spearman), sans FDR"),
        (mk3, f"background:rgba(245,158,11,0.13)", "Sig. AR1 (p_neff)", f"{int(n_sig_ar1)}", "t-amber",
         "Etoiles sur p_neff (Chelton 1983)"),
        (mk4, f"background:rgba(14,165,233,0.13)", "r max |.| ", f"{abs(best_r):.3f}", "t-blue",
         f"{best_row['index']} lag {int(best_row['lag_months'])}m" if best_row is not None else ""),
    ]
    for col, icon_bg, lbl, val, tag_cls, sub in kpi_tc:
        col.markdown(f"""
        <div class="kpi" style="padding:14px 16px;">
          <div class="kpi-body">
            <p class="kpi-lbl">{lbl}</p>
            <p class="kpi-val">{val}</p>
            <span class="kpi-tag {tag_cls}">{sub}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE INDICES SST
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Indices SST":

    with st.spinner("Chargement des indices SST..."):
        sst_raw = load_sst()

    SST_INDICES = ["Nino12", "Nino3", "Nino34", "Nino4",
                   "IOD", "IOBM", "TNA", "TSA", "ATL3", "AMM", "AMO"]
    SST_GROUPS = {
        "ENSO":             ["Nino12", "Nino3", "Nino34", "Nino4"],
        "Ocean Indien":     ["IOD", "IOBM"],
        "Atlantique Trop.": ["TNA", "TSA", "ATL3", "AMM"],
        "Atlantique Multi.":["AMO"],
    }
    SST_COLORS = {
        "Nino12": "#EF4444", "Nino3": "#F97316", "Nino34": "#F59E0B",
        "Nino4":  "#84CC16", "IOD":   "#10B981", "IOBM":   "#14B8A6",
        "TNA":    "#0EA5E9", "TSA":   "#3B82F6",  "ATL3":  "#6366F1",
        "AMM":    "#8B5CF6", "AMO":   "#EC4899",
    }

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Indices SST</b></p>
        <h1 class="pg-ttl">Indices de Temperature de Surface (SST)</h1>
        <p class="pg-sub">Series temporelles journalieres · OISST v2 · 1983-2023 · 11 indices</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Filtres inline ─────────────────────────────────────────────────────
    fa, fb, fc = st.columns([2.5, 2, 1.5], gap="small")
    with fa:
        sel_idx = st.multiselect(
            "Indices",
            options=SST_INDICES,
            default=["Nino34", "IOBM", "AMO"],
            label_visibility="visible",
        )
        if not sel_idx:
            sel_idx = ["Nino34"]
    with fb:
        agg_mode = st.selectbox(
            "Agregation", ["Mensuelle", "Annuelle", "Journaliere"],
        )
    with fc:
        show_events_overlay = st.checkbox("Overlay evenements", value=True)

    primary = sel_idx[0]

    # Filtrage par periode (slider global sidebar)
    sst = sst_raw[
        sst_raw["date"].dt.year.between(year_range[0], year_range[1])
    ].copy()

    # Agregation
    if agg_mode == "Mensuelle":
        sst_agg = sst.set_index("date")[SST_INDICES].resample("MS").mean().reset_index()
    elif agg_mode == "Annuelle":
        sst_agg = sst.set_index("date")[SST_INDICES].resample("YS").mean().reset_index()
    else:
        sst_agg = sst.copy()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── KPI du premier indice ──────────────────────────────────────────────
    pv = sst[primary]
    pv_last = pv.iloc[-1]
    pv_mean = pv.mean()
    pv_std  = pv.std()
    pct_pos = 100 * (pv > 0).mean()

    k1, k2, k3, k4 = st.columns(4, gap="small")
    kpi_sst = [
        (k1, f"background:rgba(79,70,229,0.13)", primary, f"{pv_last:+.3f}", "t-indigo",
         "Derniere valeur", svg_spark(pv.values[-60:].tolist(), color=INDIGO)),
        (k2, f"background:rgba(14,165,233,0.13)", "Moyenne", f"{pv_mean:+.3f}", "t-blue",
         f"std = {pv_std:.3f}", svg_spark(
             sst.set_index("date")[primary].resample("YS").mean().values.tolist(),
             color=BLUE)),
        (k3, f"background:rgba(16,185,129,0.13)", "Phase +", f"{pct_pos:.0f}%", "t-green",
         "Temps en phase positive", None),
        (k4, f"background:rgba(245,158,11,0.13)", "Phase -", f"{100-pct_pos:.0f}%", "t-amber",
         "Temps en phase negative", None),
    ]
    for col, icon_bg, lbl, val, tag_cls, sub, sp in kpi_sst:
        sp_html = sp if sp else ""
        col.markdown(
            f'<div class="kpi">'
            f'<div class="kpi-body">'
            f'<div class="kpi-icon" style="{icon_bg}">&#127754;</div>'
            f'<p class="kpi-lbl">{lbl}</p>'
            f'<p class="kpi-val">{val}</p>'
            f'<span class="kpi-tag {tag_cls}">{sub}</span>'
            f'</div>'
            f'<div class="kpi-spark">{sp_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ── Serie temporelle principale ────────────────────────────────────────
    st.markdown(
        f'<p class="pnl-ttl">Serie temporelle · {agg_mode}</p>'
        f'<p class="pnl-sub">Anomalies SST · ligne zero = climatologie de reference</p>',
        unsafe_allow_html=True,
    )

    fig_ts = go.Figure()

    # Zone +/- 0.5 neutre (gris)
    fig_ts.add_hrect(
        y0=-0.5, y1=0.5,
        fillcolor="rgba(100,116,139,0.06)", line_width=0,
    )
    fig_ts.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))

    # Traces pour chaque indice
    for idx_name in sel_idx:
        clr = SST_COLORS.get(idx_name, INDIGO)
        fig_ts.add_trace(go.Scatter(
            x=sst_agg["date"],
            y=sst_agg[idx_name],
            mode="lines",
            name=idx_name,
            line=dict(color=clr, width=1.8 if len(sel_idx) > 1 else 2),
            hovertemplate=f"<b>{idx_name}</b> %{{x|%b %Y}}: %{{y:.3f}}<extra></extra>",
        ))

    # Overlay evenements extremes (barres verticales en bas)
    if show_events_overlay:
        evt_yr = dff[dff["year"].between(year_range[0], year_range[1])].copy()
        if not evt_yr.empty:
            if agg_mode == "Mensuelle":
                evt_m = evt_yr.groupby(
                    evt_yr["date"].dt.to_period("M")
                ).size().reset_index(name="n")
                evt_m["date"] = evt_m["date"].dt.to_timestamp()
                y_min = sst_agg[sel_idx].min().min()
                scale = abs(y_min) * 0.4 if y_min != 0 else 0.3
                fig_ts.add_trace(go.Bar(
                    x=evt_m["date"],
                    y=[-scale * min(n / evt_m["n"].max(), 1) for n in evt_m["n"]],
                    name="Evenements",
                    marker_color="rgba(244,63,94,0.35)",
                    marker_line_width=0,
                    hovertemplate="<b>Evenements</b> %{x|%b %Y}: %{customdata} evt<extra></extra>",
                    customdata=evt_m["n"].values,
                    showlegend=True,
                ))
            elif agg_mode == "Annuelle":
                evt_a = evt_yr.groupby("year").size().reset_index(name="n")
                evt_a["date"] = pd.to_datetime(evt_a["year"].astype(str))
                y_min = sst_agg[sel_idx].min().min()
                scale = abs(y_min) * 0.4 if y_min != 0 else 0.3
                fig_ts.add_trace(go.Bar(
                    x=evt_a["date"],
                    y=[-scale * min(n / evt_a["n"].max(), 1) for n in evt_a["n"]],
                    name="Evenements",
                    marker_color="rgba(244,63,94,0.35)",
                    marker_line_width=0,
                    hovertemplate="<b>Evenements</b> %{x|%Y}: %{customdata} evt<extra></extra>",
                    customdata=evt_a["n"].values,
                    showlegend=True,
                ))

    plotly_base(fig_ts, h=310)
    fig_ts.update_layout(
        yaxis=dict(
            title=dict(text="Anomalie SST (degC)", font=dict(size=11, color=MUTED)),
            zeroline=False,
        ),
        xaxis=dict(
            title=None,
            rangeslider=dict(visible=False),
        ),
        barmode="overlay",
    )
    st.plotly_chart(fig_ts, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ── Distribution + Cycle saisonnier ────────────────────────────────────
    dc1, dc2 = st.columns(2, gap="medium")

    with dc1:
        st.markdown(
            f'<p class="pnl-ttl">Distribution de {primary}</p>'
            f'<p class="pnl-sub">Histogramme des anomalies · phases positive / negative</p>',
            unsafe_allow_html=True,
        )
        clr_p = SST_COLORS.get(primary, INDIGO)
        vals_p = sst[primary].values

        fig_hist = go.Figure()
        # Partie negative
        fig_hist.add_trace(go.Histogram(
            x=vals_p[vals_p < 0],
            nbinsx=40,
            name="Phase -",
            marker_color="rgba(239,68,68,0.6)",
            marker_line_width=0,
            hovertemplate="[%{x:.2f}] : %{y} jours<extra></extra>",
        ))
        # Partie positive
        fig_hist.add_trace(go.Histogram(
            x=vals_p[vals_p >= 0],
            nbinsx=40,
            name="Phase +",
            marker_color="rgba(59,130,246,0.6)",
            marker_line_width=0,
            hovertemplate="[%{x:.2f}] : %{y} jours<extra></extra>",
        ))
        fig_hist.add_vline(
            x=float(np.mean(vals_p)),
            line=dict(color=clr_p, width=1.5, dash="dot"),
            annotation_text=f" moy {np.mean(vals_p):+.2f}",
            annotation_font=dict(size=10, color=clr_p),
        )
        plotly_base(fig_hist, h=240)
        fig_hist.update_layout(
            barmode="overlay",
            xaxis=dict(title=dict(text="Anomalie (degC)", font=dict(size=11, color=MUTED))),
            yaxis=dict(title=dict(text="Nb jours", font=dict(size=11, color=MUTED))),
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

    with dc2:
        st.markdown(
            f'<p class="pnl-ttl">Cycle saisonnier de {primary}</p>'
            f'<p class="pnl-sub">Anomalie mensuelle moyenne · plage interquartile</p>',
            unsafe_allow_html=True,
        )
        clr_p = SST_COLORS.get(primary, INDIGO)
        sst_m = sst.copy()
        sst_m["month"] = sst_m["date"].dt.month
        MNAMES = ["Jan","Fev","Mar","Avr","Mai","Jun",
                  "Jul","Aou","Sep","Oct","Nov","Dec"]
        seasonal = sst_m.groupby("month")[primary].agg(
            ["mean", lambda x: x.quantile(0.25), lambda x: x.quantile(0.75)]
        ).reset_index()
        seasonal.columns = ["month", "mean", "q25", "q75"]
        seasonal["mname"] = seasonal["month"].apply(lambda m: MNAMES[m - 1])

        fig_sea = go.Figure()
        fig_sea.add_trace(go.Scatter(
            x=seasonal["mname"], y=seasonal["q75"],
            mode="lines", line=dict(width=0),
            showlegend=False, hoverinfo="skip",
        ))
        fig_sea.add_trace(go.Scatter(
            x=seasonal["mname"], y=seasonal["q25"],
            fill="tonexty",
            fillcolor=f"rgba({int(clr_p[1:3],16)},{int(clr_p[3:5],16)},{int(clr_p[5:7],16)},0.15)",
            mode="lines", line=dict(width=0),
            name="IQR", hoverinfo="skip",
        ))
        fig_sea.add_trace(go.Scatter(
            x=seasonal["mname"], y=seasonal["mean"],
            mode="lines+markers",
            name=primary,
            line=dict(color=clr_p, width=2.5),
            marker=dict(size=6, color=clr_p),
            hovertemplate="<b>%{x}</b>: %{y:.3f}<extra></extra>",
        ))
        fig_sea.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
        plotly_base(fig_sea, h=240)
        fig_sea.update_layout(
            xaxis=dict(tickfont=dict(size=11)),
            yaxis=dict(title=dict(text="Anomalie moy. (degC)", font=dict(size=11, color=MUTED))),
        )
        st.plotly_chart(fig_sea, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    # ── Heatmap annee x mois ───────────────────────────────────────────────
    st.markdown(
        f'<p class="pnl-ttl">Heatmap annee x mois · {primary}</p>'
        f'<p class="pnl-sub">Anomalie SST mensuelle moyenne par annee</p>',
        unsafe_allow_html=True,
    )
    sst_hm = sst.copy()
    sst_hm["year"]  = sst_hm["date"].dt.year
    sst_hm["month"] = sst_hm["date"].dt.month
    pivot = sst_hm.groupby(["year", "month"])[primary].mean().unstack(level=1)
    pivot.columns = ["Jan","Fev","Mar","Avr","Mai","Jun",
                     "Jul","Aou","Sep","Oct","Nov","Dec"]

    clr_p = SST_COLORS.get(primary, INDIGO)
    r_hex, g_hex, b_hex = int(clr_p[1:3],16), int(clr_p[3:5],16), int(clr_p[5:7],16)

    fig_hm2 = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[
            [0.0,  "#7F1D1D"],
            [0.35, "#EF4444"],
            [0.48, "#FEF3C7"],
            [0.5,  "#F8FAFC"],
            [0.52, "#BAE6FD"],
            [0.65, f"rgb({r_hex},{g_hex},{b_hex})"],
            [1.0,  "#1E3A8A"],
        ],
        zmid=0,
        colorbar=dict(thickness=12, outlinewidth=0,
                      tickfont=dict(size=10, color=MUTED)),
        hovertemplate="<b>%{y} · %{x}</b><br>%{z:.3f} degC<extra></extra>",
    ))
    fig_hm2.update_layout(
        height=340,
        margin=dict(l=0, r=0, t=4, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,sans-serif", size=11, color=MUTED),
        xaxis=dict(tickfont=dict(size=11, color=MUTED), showgrid=False),
        yaxis=dict(tickfont=dict(size=11, color=TEXT), showgrid=False,
                   autorange="reversed"),
    )
    st.plotly_chart(fig_hm2, use_container_width=True, config={"displayModeBar": False})


# ═════════════════════════════════════════════════════════════════════════════
# PAGE A VENIR — CLUSTERING
# ═════════════════════════════════════════════════════════════════════════════
elif page == "Clustering":

    with st.spinner("Chargement des donnees de clustering..."):
        clust_data = load_clustering()

    # ── header ──────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Clustering</b></p>
        <h1 class="pg-ttl">Clustering KMeans SST</h1>
        <p class="pg-sub">Patterns SST associes aux evenements extremes · selection du k optimal</p>
      </div>
    </div>""", unsafe_allow_html=True)

    if not clust_data:
        st.warning("Donnees de clustering non disponibles.")
    else:
        # ── selectors ───────────────────────────────────────────────────────
        PHASE_LABELS_CL = {
            "Phase_1_debut":  "Debut saison  (Mai-Jun)",
            "Phase_2_pleine": "Pleine saison (Jul-Aou)",
            "Phase_3_fin":    "Fin saison    (Sep-Oct)",
            "All_phases":     "Toutes phases confondues",
        }
        sel_phase = st.selectbox(
            "Phase",
            options=list(clust_data.keys()),
            format_func=lambda x: PHASE_LABELS_CL.get(x, x),
            key="cl_phase",
        )
        cdata   = clust_data[sel_phase]
        chars   = cdata["chars"]
        events  = cdata["events"]
        metrics = cdata["metrics"]

        # ── Panneau : relancer le clustering avec K personnalise ─────────────
        for _k in ("show_cluster_rerun", "cluster_result", "cluster_stderr"):
            if _k not in st.session_state:
                st.session_state[_k] = False if _k == "show_cluster_rerun" else None

        btn_label = "Masquer le panneau" if st.session_state["show_cluster_rerun"] else "Relancer le clustering avec un K personnalise"
        if st.button(btn_label, key="btn_cluster_rerun"):
            st.session_state["show_cluster_rerun"] = not st.session_state["show_cluster_rerun"]
            st.session_state["cluster_result"] = None
            st.rerun()

        if st.session_state["show_cluster_rerun"]:
            st.markdown(
                f'<p style="font-size:0.78rem;color:{MUTED};margin:0 0 12px 0;">'
                "Definissez le nombre de clusters K pour chaque phase, puis lancez le script. "
                "Les resultats seront recharges automatiquement.</p>",
                unsafe_allow_html=True,
            )

            # Recuperer les k actuels par phase comme valeurs par defaut
            def _current_k(ph):
                d = clust_data.get(ph, {})
                m = d.get("metrics", {})
                return int(m.get("optimal_k", m.get("k_elbow", 6)) or 6)

            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            with col_k1:
                k_p1 = st.number_input(
                    "Phase 1 - Debut (Mai-Jun)",
                    min_value=2, max_value=15,
                    value=_current_k("Phase_1_debut"),
                    step=1, key="ck_p1",
                )
            with col_k2:
                k_p2 = st.number_input(
                    "Phase 2 - Pleine (Jul-Aou)",
                    min_value=2, max_value=15,
                    value=_current_k("Phase_2_pleine"),
                    step=1, key="ck_p2",
                )
            with col_k3:
                k_p3 = st.number_input(
                    "Phase 3 - Fin (Sep-Oct)",
                    min_value=2, max_value=15,
                    value=_current_k("Phase_3_fin"),
                    step=1, key="ck_p3",
                )
            with col_k4:
                k_all = st.number_input(
                    "All phases",
                    min_value=2, max_value=20,
                    value=_current_k("All_phases"),
                    step=1, key="ck_all",
                )

            col_opt, col_btn = st.columns([2, 1])
            with col_opt:
                mode_opt = st.radio(
                    "Phases a relancer",
                    ["Toutes les phases + All_phases", "Par phase uniquement", "All_phases uniquement"],
                    horizontal=True, key="ck_mode",
                )
            with col_btn:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                run_clicked = st.button(
                    "Lancer le clustering",
                    type="primary", use_container_width=True, key="ck_run",
                )

            # Affichage du resultat persistant (survit aux reruns)
            if st.session_state["cluster_result"] == "success":
                st.success("Clustering termine avec succes ! Les resultats affiches sont mis a jour.")
                if st.button("Fermer ce message", key="btn_reload_cl"):
                    st.session_state["cluster_result"] = None
                    st.rerun()
            elif st.session_state["cluster_result"] == "error":
                st.error("Le script a rencontre une erreur.")
                st.code(st.session_state["cluster_stderr"] or "Pas de message d'erreur.")
            elif st.session_state["cluster_result"] == "timeout":
                st.error("Timeout depasse (30 min). Le calcul est peut-etre trop long.")

            if run_clicked:
                # Utilise 11b_kmeans_rerun_fast.py si les donnees PCA existent,
                # sinon repli sur le script complet 11_kmeans_sst_analysis.py
                fast_script  = BASE / "scripts" / "11b_kmeans_rerun_fast.py"
                full_script  = BASE / "scripts" / "11_kmeans_sst_analysis.py"

                def _pca_exists(ph):
                    return (BASE / "outputs" / "clustering" / ph / f"{ph}_kmeans_input_pca.csv").exists()

                phases_needed = []
                if mode_opt != "All_phases uniquement":
                    phases_needed += ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]
                if mode_opt != "Par phase uniquement":
                    phases_needed += ["All_phases"]

                use_fast = all(_pca_exists(ph) for ph in phases_needed) and fast_script.exists()
                script_path = fast_script if use_fast else full_script

                cmd = [sys.executable, str(script_path)]

                if mode_opt == "Par phase uniquement":
                    cmd += ["--by-phase"]
                elif mode_opt == "All_phases uniquement":
                    cmd += ["--global"]

                cmd += [f"--k-phase1={int(k_p1)}", f"--k-phase2={int(k_p2)}", f"--k-phase3={int(k_p3)}"]
                if mode_opt != "Par phase uniquement":
                    cmd += [f"--k-all={int(k_all)}"]

                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"

                spinner_msg = (
                    "Clustering en cours... (mode rapide - quelques secondes)"
                    if use_fast else
                    "Clustering en cours... (mode complet - peut prendre plusieurs minutes)"
                )
                with st.spinner(spinner_msg):
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            env=env,
                            cwd=str(BASE), timeout=1800,
                        )
                        if result.returncode == 0:
                            load_clustering.clear()
                            st.session_state["cluster_result"] = "success"
                        else:
                            st.session_state["cluster_result"] = "error"
                            st.session_state["cluster_stderr"] = (result.stderr or "") + "\n" + (result.stdout or "")
                    except subprocess.TimeoutExpired:
                        st.session_state["cluster_result"] = "timeout"
                    except Exception as exc:
                        st.session_state["cluster_result"] = "error"
                        st.session_state["cluster_stderr"] = str(exc)
                st.rerun()

        # ── KPI row  ─────────────────────────────────────────────────────────
        n_ev      = len(events)
        k_opt     = metrics.get("optimal_k", metrics.get("k_elbow", "?"))
        sil_best  = metrics.get("best_silhouette_score", None)
        k_sil     = metrics.get("k_silhouette", "?")
        sil_str   = f"{sil_best:.3f}" if sil_best is not None else "—"
        n_clust   = chars["cluster"].nunique()

        kpi_items = [
            ("&#128202;", "Evenements", str(n_ev), "cette phase"),
            ("&#127981;", "k optimal", str(k_opt), "methode coude"),
            ("&#128200;", "Silhouette max", sil_str, f"k={k_sil}"),
            ("&#127987;", "Clusters utilises", str(n_clust), "dans ce graphe"),
        ]
        cols_kpi = st.columns(4)
        for col, (ico, label, val, sub) in zip(cols_kpi, kpi_items):
            with col:
                st.markdown(
                    f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:14px;'
                    f'padding:18px 20px;">'
                    f'<div style="font-size:1.5rem;">{ico}</div>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:6px 0 2px 0;text-transform:uppercase;'
                    f'letter-spacing:.05em;">{label}</p>'
                    f'<p style="font-size:1.6rem;font-weight:800;color:{TEXT};margin:0;">{val}</p>'
                    f'<p style="font-size:0.7rem;color:{MUTED};margin:2px 0 0 0;">{sub}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

        # ── row 1 : elbow + silhouette curves  ──────────────────────────────
        col_el, col_si = st.columns(2)

        k_range = metrics.get("k_range", [])
        inertias = metrics.get("inertias", [])
        silhouettes = metrics.get("silhouette_scores", [])
        db_scores = metrics.get("davies_bouldin_scores", [])

        with col_el:
            
            fig_el = go.Figure()
            fig_el.add_trace(go.Scatter(
                x=k_range, y=inertias, mode="lines+markers",
                line=dict(color=INDIGO, width=2.5),
                marker=dict(size=7, color=INDIGO),
                name="Inertie",
            ))
            if k_opt in k_range:
                idx_opt = k_range.index(k_opt)
                fig_el.add_vline(
                    x=k_opt, line_dash="dash", line_color=ROSE, line_width=1.5,
                    annotation_text=f"k={k_opt} (coude)",
                    annotation_font_color=ROSE,
                    annotation_position="top right",
                )
            fig_el.update_layout(
                title=dict(text="Courbe d'inertie (methode du coude)", font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
                xaxis=dict(title="k (nb clusters)", gridcolor=BORDER, tickmode="linear"),
                yaxis=dict(title="Inertie", gridcolor=BORDER),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                margin=dict(l=10, r=10, t=44, b=10),
                height=280,
            )
            st.plotly_chart(fig_el, use_container_width=True, key="cl_elbow")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_si:
            
            fig_si = go.Figure()
            fig_si.add_trace(go.Scatter(
                x=k_range, y=silhouettes, mode="lines+markers",
                line=dict(color=EMERALD, width=2.5),
                marker=dict(size=7, color=EMERALD),
                name="Silhouette",
            ))
            fig_si.add_trace(go.Scatter(
                x=k_range, y=db_scores, mode="lines+markers",
                line=dict(color=AMBER, width=2, dash="dot"),
                marker=dict(size=6, color=AMBER),
                name="Davies-Bouldin",
                yaxis="y2",
            ))
            fig_si.update_layout(
                title=dict(text="Silhouette et Davies-Bouldin vs k", font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
                xaxis=dict(title="k", gridcolor=BORDER, tickmode="linear"),
                yaxis=dict(title=dict(text="Silhouette", font=dict(color=EMERALD)), gridcolor=BORDER),
                yaxis2=dict(title=dict(text="Davies-Bouldin", font=dict(color=AMBER)), overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.08, x=0),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                margin=dict(l=10, r=10, t=44, b=10),
                height=280,
            )
            st.plotly_chart(fig_si, use_container_width=True, key="cl_silhouette")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── row 2 : cluster profiles  ────────────────────────────────────────
        st.markdown(
            f'<h3 style="font-size:0.85rem;font-weight:700;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin:4px 0 10px 2px;">Profils des clusters</h3>',
            unsafe_allow_html=True,
        )

        # Sort chars by cluster id for consistent colors
        chars_s = chars.sort_values("cluster").reset_index(drop=True)
        cl_ids  = chars_s["cluster"].tolist()
        cl_colors = [INDIGO, BLUE, EMERALD, AMBER, ROSE, "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#6366F1"]

        col_bar, col_scat = st.columns(2)

        with col_bar:
           
            metrics_bar = {
                "Nb evenements": "n_events",
                "Precip max moy (mm)": "mean_max_precip",
                "Couverture (%)": "mean_coverage_percent",
                "Anomalie max moy": "mean_max_anomaly",
            }
            sel_metric = st.selectbox(
                "Metrique",
                options=list(metrics_bar.keys()),
                key="cl_metric_bar",
                label_visibility="collapsed",
            )
            col_key = metrics_bar[sel_metric]
            fig_bar = go.Figure()
            for i, (cid, row) in enumerate(zip(cl_ids, chars_s.itertuples())):
                val = getattr(row, col_key)
                fig_bar.add_trace(go.Bar(
                    x=[f"C{cid}"],
                    y=[val],
                    name=f"Cluster {cid}",
                    marker_color=cl_colors[i % len(cl_colors)],
                    showlegend=True,
                ))
            fig_bar.update_layout(
                title=dict(text=sel_metric + " par cluster", font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
                xaxis=dict(title="Cluster", gridcolor=BORDER),
                yaxis=dict(title=sel_metric, gridcolor=BORDER),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                showlegend=False,
                margin=dict(l=10, r=10, t=44, b=10),
                height=300,
            )
            st.plotly_chart(fig_bar, use_container_width=True, key="cl_bar_metric")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_scat:
            
            # scatter: mean_max_precip vs mean_coverage_percent, size=n_events
            fig_sc = go.Figure()
            for i, row in enumerate(chars_s.itertuples()):
                cid = row.cluster
                fig_sc.add_trace(go.Scatter(
                    x=[row.mean_coverage_percent],
                    y=[row.mean_max_precip],
                    mode="markers+text",
                    marker=dict(
                        size=max(12, min(50, row.n_events * 0.4)),
                        color=cl_colors[i % len(cl_colors)],
                        opacity=0.85,
                        line=dict(width=1.5, color="white"),
                    ),
                    text=[f"C{cid}<br>n={row.n_events}"],
                    textposition="top center",
                    textfont=dict(size=10),
                    name=f"Cluster {cid}",
                    showlegend=True,
                ))
            fig_sc.update_layout(
                title=dict(text="Couverture vs Intensite (taille = nb evt)", font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
                xaxis=dict(title="Couverture moyenne (%)", gridcolor=BORDER),
                yaxis=dict(title="Precip max moyenne (mm)", gridcolor=BORDER),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                legend=dict(orientation="h", y=-0.15, x=0),
                margin=dict(l=10, r=10, t=44, b=10),
                height=300,
            )
            st.plotly_chart(fig_sc, use_container_width=True, key="cl_scatter")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── row 3 : temporal distribution of clusters  ───────────────────────
        st.markdown(
            f'<h3 style="font-size:0.85rem;font-weight:700;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin:4px 0 10px 2px;">Distribution temporelle des clusters</h3>',
            unsafe_allow_html=True,
        )

        col_yr, col_mo = st.columns(2)

        with col_yr:
           
            yr_cl = events.groupby(["year", "cluster"]).size().reset_index(name="n")
            fig_yr = go.Figure()
            for i, cid in enumerate(sorted(events["cluster"].unique())):
                sub = yr_cl[yr_cl["cluster"] == cid]
                fig_yr.add_trace(go.Bar(
                    x=sub["year"], y=sub["n"],
                    name=f"C{cid}",
                    marker_color=cl_colors[i % len(cl_colors)],
                ))
            fig_yr.update_layout(
                barmode="stack",
                title=dict(text="Evenements par annee et cluster", font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
                xaxis=dict(title="Annee", gridcolor=BORDER, dtick=5),
                yaxis=dict(title="Nb evenements", gridcolor=BORDER),
                legend=dict(orientation="h", y=1.08, x=0),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                margin=dict(l=10, r=10, t=44, b=10),
                height=300,
            )
            st.plotly_chart(fig_yr, use_container_width=True, key="cl_yr")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_mo:
            
            mo_cl = events.groupby(["month", "cluster"]).size().reset_index(name="n")
            month_names = {5:"Mai",6:"Juin",7:"Juil",8:"Aout",9:"Sep",10:"Oct"}
            mo_cl["month_lbl"] = mo_cl["month"].map(lambda m: month_names.get(m, str(m)))
            fig_mo = go.Figure()
            for i, cid in enumerate(sorted(events["cluster"].unique())):
                sub = mo_cl[mo_cl["cluster"] == cid].sort_values("month")
                fig_mo.add_trace(go.Bar(
                    x=sub["month_lbl"], y=sub["n"],
                    name=f"C{cid}",
                    marker_color=cl_colors[i % len(cl_colors)],
                ))
            fig_mo.update_layout(
                barmode="group",
                title=dict(text="Evenements par mois et cluster", font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
                xaxis=dict(title="Mois", gridcolor=BORDER),
                yaxis=dict(title="Nb evenements", gridcolor=BORDER),
                legend=dict(orientation="h", y=1.08, x=0),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                margin=dict(l=10, r=10, t=44, b=10),
                height=300,
            )
            st.plotly_chart(fig_mo, use_container_width=True, key="cl_mo")
            st.markdown("</div>", unsafe_allow_html=True)

        # ── row 4 : per-cluster summary cards ───────────────────────────────
        st.markdown(
            f'<h3 style="font-size:0.85rem;font-weight:700;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin:4px 0 10px 2px;">Resume par cluster</h3>',
            unsafe_allow_html=True,
        )
        n_c = len(chars_s)
        card_cols = st.columns(min(n_c, 5))
        for i, row in enumerate(chars_s.itertuples()):
            with card_cols[i % len(card_cols)]:
                cid   = row.cluster
                color = cl_colors[i % len(cl_colors)]
                pct   = f"{row.percentage:.1f}%"
                mp    = f"{row.mean_max_precip:.1f} mm"
                cov   = f"{row.mean_coverage_percent:.1f}%"
                anom  = f"{row.mean_max_anomaly:.1f}"
                st.markdown(
                    f'<div style="background:{CARD};border:2px solid {color};border-radius:14px;'
                    f'padding:16px 18px;margin-bottom:12px;">'
                    f'<p style="font-size:0.8rem;font-weight:800;color:{color};margin:0 0 8px 0;">'
                    f'Cluster {cid} &nbsp;<span style="font-weight:500;color:{MUTED};">({pct})</span></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:0;">Evenements : <b style="color:{TEXT};">{row.n_events}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Precip max : <b style="color:{TEXT};">{mp}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Couverture : <b style="color:{TEXT};">{cov}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Anomalie max : <b style="color:{TEXT};">{anom}</b></p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # ════════════════════════════════════════════════════════════════════
        # SST SPATIAL PATTERNS
        # ════════════════════════════════════════════════════════════════════
        st.markdown(f"""
        <div style="border-top:2px solid {BORDER};margin:24px 0 18px 0;"></div>
        <h2 style="font-size:1.05rem;font-weight:800;color:{TEXT};margin:0 0 6px 0;">
          Cartes SST — Patterns spatiaux</h2>
        <p style="font-size:0.78rem;color:{MUTED};margin:0 0 16px 0;">
          Visualisation des anomalies SST globales (60S-60N) pour chaque cluster
          (centroide).</p>
        """, unsafe_allow_html=True)

        # ── Selecteur de cluster partage (SST Patterns + Cartographie) ─────────
        cl_ids_sorted = sorted(events["cluster"].unique())
        if st.session_state.get("cl_shared_last_phase") != sel_phase:
            st.session_state["cl_shared_last_phase"] = sel_phase
            st.session_state.pop("cl_shared_cluster", None)
        sel_cl_shared = st.selectbox(
            "Cluster",
            options=cl_ids_sorted,
            format_func=lambda x: f"Cluster {x}",
            key="cl_shared_cluster",
        )

        # ── load centroids ───────────────────────────────────────────────────
        cent_arr, cent_lats, cent_lons = load_sst_centroid(sel_phase)

        sel_cl = sel_cl_shared

        if cent_arr is not None:
            clust_idx = cl_ids_sorted.index(sel_cl)
            z_full = cent_arr[clust_idx] if clust_idx < cent_arr.shape[0] else cent_arr[0]
            vlim = max(abs(float(np.nanpercentile(z_full, 2))),
                       abs(float(np.nanpercentile(z_full, 98))))
            vlim = min(vlim, 3.0)

            # Downsample 2x uniquement pour le rendu Plotly (performance browser)
            z        = z_full[::2, ::2]
            lats_ds  = cent_lats[::2]
            lons_ds  = cent_lons[::2]

            _rg_cent = _get_region_grid(tuple(lats_ds), tuple(lons_ds))
            fig_sst = go.Figure(go.Heatmap(
                z=z, x=lons_ds, y=lats_ds,
                colorscale="RdBu_r", zmin=-vlim, zmax=vlim,
                zsmooth=False,
                customdata=_rg_cent,
                colorbar=dict(
                    title=dict(text="Anomalie SST (degC)", side="right"),
                    len=0.75, thickness=14,
                ),
                hovertemplate=(
                    "Lon: %{x:.2f}  Lat: %{y:.2f}<br>"
                    "Anomalie SST: <b>%{z:.3f} degC</b><br>"
                    "Region: %{customdata}<extra></extra>"
                ),
            ))
            _apply_geo_traces(fig_sst)
            fig_sst.add_trace(go.Scatter(
                x=[-17.4], y=[14.7], mode="markers",
                marker=dict(symbol="star", size=14, color=AMBER,
                            line=dict(width=1.5, color="white")),
                name="Senegal (Dakar)",
                hovertemplate="Dakar<br>17.4W  14.7N<extra></extra>",
            ))
            fig_sst.update_layout(
                title=dict(
                    text=(f"Centroide SST  -  {PHASE_LABELS_CL.get(sel_phase, sel_phase)}"
                          f"  |  Cluster {sel_cl}"),
                    font=dict(size=13, color=TEXT), x=0, pad=dict(l=0),
                ),
                xaxis=dict(title="Longitude", gridcolor=BORDER, dtick=30,
                           range=[-180, 180]),
                yaxis=dict(title="Latitude", gridcolor=BORDER, dtick=15,
                           range=[-60, 60]),
                plot_bgcolor=CARD, paper_bgcolor=CARD,
                font=dict(color=TEXT, size=11),
                legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
                margin=dict(l=10, r=10, t=48, b=10),
                height=520,
            )
            st.plotly_chart(fig_sst, use_container_width=True, key="cl_sst_cent_map",
                            config={"toImageButtonOptions": {"scale": 3, "format": "png"}})
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("Fichier centroide non disponible pour cette phase.")


        # ════════════════════════════════════════════════════════════════════
        # ANALYSE SPATIALE — CARTOGRAPHIE PAR CLUSTER
        # ════════════════════════════════════════════════════════════════════
        st.markdown(
            f'<div style="border-top:2px solid {BORDER};margin:32px 0 18px 0;"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
          <div style="height:2px;width:28px;
                      background:linear-gradient(90deg,{INDIGO},{BLUE});
                      border-radius:99px;flex-shrink:0;"></div>
          <span style="font-size:0.70rem;font-weight:700;color:{MUTED};
                       text-transform:uppercase;letter-spacing:0.08em;white-space:nowrap">
            Analyse spatiale &mdash; Cartographie
          </span>
          <div style="height:1px;flex:1;background:{BORDER};"></div>
          <span style="font-size:0.67rem;color:{MUTED};white-space:nowrap;">
            4 &eacute;v&eacute;nements repr&eacute;sentatifs par cluster
            &middot; plus/moins intense &middot; grande/petite couverture
          </span>
        </div>
        """, unsafe_allow_html=True)

        _cl_px_all = load_cluster_pixels()

        if _cl_px_all is None or len(_cl_px_all) == 0:
            st.info(
                "Donnees cartographiques non disponibles. "
                "Executer le script 03c_filter_events_by_cluster_for_qgis.py pour generer les fichiers de pixels."
            )
        else:
            # ── Filtrage par phase selectionnee ──────────────────────────────
            _cl_px_ph = _cl_px_all[_cl_px_all["phase"] == sel_phase].copy()

            if len(_cl_px_ph) == 0:
                st.info(
                    f"Aucun pixel disponible pour {PHASE_LABELS_CL.get(sel_phase, sel_phase)}. "
                    "Relancer le script 03c_filter_events_by_cluster_for_qgis.py."
                )
            else:
                # Utilise le cluster partage avec les sections SST Patterns
                _cl_carto_sel = sel_cl_shared

                # Reset navigation si le cluster ou la phase a change
                _cl_nav_key = f"{sel_phase}_{_cl_carto_sel}"
                if st.session_state.get("cl_carto_last_navkey") != _cl_nav_key:
                    st.session_state["cl_carto_last_navkey"] = _cl_nav_key
                    st.session_state["cl_carto_nav"] = 0
                    st.session_state["cl_carto_crit"] = None

                _cl_px_c = _cl_px_ph[_cl_px_ph["cluster"] == _cl_carto_sel].copy()

                # Ordre fixe des criteres
                _CRIT_ORDER = ["plus_intense", "moins_intense",
                               "plus_grande_couverture", "plus_petite_couverture"]
                _cl_crit_avail = [c for c in _CRIT_ORDER if c in _cl_px_c["criterion"].unique()]
                _cl_crit_avail += [c for c in _cl_px_c["criterion"].unique() if c not in _CRIT_ORDER]

                _CRIT_FR_CL = {
                    "plus_intense":           "Plus intense",
                    "moins_intense":          "Moins intense",
                    "plus_grande_couverture": "Grande couverture",
                    "plus_petite_couverture": "Petite couverture",
                }
                _CRIT_CLR_CL = {
                    "plus_intense":           (ROSE,      "rgba(244,63,94,0.13)"),
                    "moins_intense":          (EMERALD,   "rgba(16,185,129,0.13)"),
                    "plus_grande_couverture": (INDIGO,    "rgba(79,70,229,0.13)"),
                    "plus_petite_couverture": (BLUE,      "rgba(14,165,233,0.13)"),
                }

                # ── Navigation ───────────────────────────────────────────────
                if "cl_carto_nav" not in st.session_state:
                    st.session_state["cl_carto_nav"] = 0
                _cl_nav = min(st.session_state["cl_carto_nav"], len(_cl_crit_avail) - 1)

                # Initialisation de cl_carto_crit si absent ou reset
                if not st.session_state.get("cl_carto_crit") and _cl_crit_avail:
                    st.session_state["cl_carto_crit"] = _cl_crit_avail[_cl_nav]

                _cl_scol, _cl_pcol, _cl_ccol, _cl_ncol = st.columns(
                    [7, 1, 1.2, 1], gap="small"
                )
                with _cl_pcol:
                    if st.button("←", key="cl_carto_prev",
                                 disabled=_cl_nav <= 0, use_container_width=True):
                        _new_nav = max(0, _cl_nav - 1)
                        st.session_state["cl_carto_nav"] = _new_nav
                        st.session_state["cl_carto_crit"] = _cl_crit_avail[_new_nav]
                        st.rerun()
                with _cl_scol:
                    _cl_sel_crit = st.selectbox(
                        "Critere",
                        options=_cl_crit_avail,
                        format_func=lambda c: _CRIT_FR_CL.get(c, c),
                        label_visibility="collapsed",
                        key="cl_carto_crit",
                    )
                    # Sync nav depuis le selectbox (sélection directe par l'utilisateur)
                    _cl_crit_idx = (
                        _cl_crit_avail.index(_cl_sel_crit)
                        if _cl_sel_crit in _cl_crit_avail else _cl_nav
                    )
                    if _cl_crit_idx != _cl_nav:
                        st.session_state["cl_carto_nav"] = _cl_crit_idx
                        _cl_nav = _cl_crit_idx
                with _cl_ccol:
                    st.markdown(
                        f'<div style="text-align:center;padding:8px 0;'
                        f'font-size:0.75rem;font-weight:700;color:{MUTED};">'
                        f'{_cl_nav + 1}&nbsp;/&nbsp;{len(_cl_crit_avail)}</div>',
                        unsafe_allow_html=True,
                    )
                with _cl_ncol:
                    if st.button("→", key="cl_carto_next",
                                 disabled=_cl_nav >= len(_cl_crit_avail) - 1,
                                 use_container_width=True):
                        _new_nav = min(len(_cl_crit_avail) - 1, _cl_nav + 1)
                        st.session_state["cl_carto_nav"] = _new_nav
                        st.session_state["cl_carto_crit"] = _cl_crit_avail[_new_nav]
                        st.rerun()

                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

                # ── Mini-cards (4 criteres) ──────────────────────────────────
                _cl_mc_cols = st.columns(min(4, len(_cl_crit_avail)), gap="small")
                for _cl_mc, _cl_c in zip(_cl_mc_cols, _cl_crit_avail):
                    _cl_sub = _cl_px_c[_cl_px_c["criterion"] == _cl_c]
                    _cl_fg, _cl_bgc = _CRIT_CLR_CL.get(_cl_c, (INDIGO, "rgba(79,70,229,0.13)"))
                    _cl_d   = _cl_sub["event_date"].iloc[0] if len(_cl_sub) > 0 else "-"
                    _cl_mp  = f"{_cl_sub['precipitation_mm'].max():.0f}" if len(_cl_sub) > 0 else "-"
                    _cl_am  = f"{_cl_sub['anomaly_standardized'].max():.1f}" if len(_cl_sub) > 0 else "-"
                    _cl_phs = _cl_sub["season_phase"].iloc[0] if len(_cl_sub) > 0 else ""
                    _cl_phshort = (
                        "P1 Debut"  if "debut"  in _cl_phs else
                        "P2 Pleine" if "pleine" in _cl_phs else
                        "P3 Fin"    if "fin"    in _cl_phs else _cl_phs
                    )
                    _cl_is_sel = (_cl_c == _cl_sel_crit)
                    _cl_mc.markdown(f"""
                    <div style="background:{'rgba(79,70,229,0.12)' if _cl_is_sel else CARD};
                                border:{'2px solid ' + INDIGO if _cl_is_sel else '1px solid ' + BORDER};
                                border-radius:10px;padding:10px 10px 9px 10px;
                                {'box-shadow:0 3px 12px rgba(79,70,229,0.18);' if _cl_is_sel else ''}">
                      <div style="background:{_cl_bgc};border-radius:5px;padding:2px 6px;
                                  margin-bottom:7px;display:inline-block;max-width:100%;">
                        <span style="font-size:0.69rem;font-weight:700;color:{_cl_fg};
                                     white-space:nowrap;display:block;">
                          {_CRIT_FR_CL.get(_cl_c, _cl_c)}
                        </span>
                      </div>
                      <p style="margin:0;font-size:0.77rem;font-weight:700;
                                color:{TEXT};line-height:1.2">{_cl_d}</p>
                      <p style="margin:3px 0 0 0;font-size:0.72rem;color:{MUTED}">
                        {_cl_mp} mm &nbsp;&middot;&nbsp; {_cl_am} &#963;</p>
                      <p style="margin:4px 0 0 0;font-size:0.69rem;color:{MUTED}">{_cl_phshort}</p>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

                # ── Pixels du critere selectionne ────────────────────────────
                _cl_ev = _cl_px_c[_cl_px_c["criterion"] == _cl_sel_crit].copy()
                _cl_date = _cl_ev["event_date"].iloc[0] if len(_cl_ev) > 0 else ""
                _cl_fg0, _cl_bgcrit = _CRIT_CLR_CL.get(_cl_sel_crit, (INDIGO, "rgba(79,70,229,0.13)"))
                _cl_lbl = _CRIT_FR_CL.get(_cl_sel_crit, _cl_sel_crit)

                # Filtrage geometrique (contour Senegal)
                _cl_dept_geo = load_dept_geojson()
                _cl_bounds_path = BASE / "data/geographic/senegal_boundaries.geojson"
                if _cl_bounds_path.exists() and len(_cl_ev) > 0:
                    import json as _json_cl
                    from matplotlib.path import Path as _MplPathCl
                    with open(str(_cl_bounds_path), "r", encoding="utf-8") as _bfcl:
                        _cl_bounds_geo = _json_cl.load(_bfcl)
                    _cl_bp_list = []
                    for _feat_cl in _cl_bounds_geo.get("features", []):
                        _geom_cl = _feat_cl.get("geometry", {})
                        _gtype_cl = _geom_cl.get("type", "")
                        _coords_cl = _geom_cl.get("coordinates", [])
                        if _gtype_cl == "MultiPolygon":
                            for _poly_cl in _coords_cl:
                                if _poly_cl and _poly_cl[0]:
                                    _cl_bp_list.append(_MplPathCl(np.array(_poly_cl[0])))
                        elif _gtype_cl == "Polygon":
                            if _coords_cl and _coords_cl[0]:
                                _cl_bp_list.append(_MplPathCl(np.array(_coords_cl[0])))
                    if _cl_bp_list:
                        _cl_pts = np.column_stack([
                            _cl_ev["longitude"].values, _cl_ev["latitude"].values
                        ])
                        _cl_ins = np.zeros(len(_cl_pts), dtype=bool)
                        for _cl_bp in _cl_bp_list:
                            _cl_ins |= _cl_bp.contains_points(_cl_pts)
                        _cl_ev = _cl_ev[_cl_ins].reset_index(drop=True)

                # Jointure departement
                _cl_depts = [""] * len(_cl_ev)
                if _cl_dept_geo is not None and len(_cl_ev) > 0:
                    from matplotlib.path import Path as _MplPathCl2
                    _cl_pts_all = np.column_stack([
                        _cl_ev["longitude"].values, _cl_ev["latitude"].values
                    ])
                    for _feat_d in _cl_dept_geo.get("features", []):
                        _dname = _feat_d.get("properties", {}).get("NAME_2", "")
                        _geom_d = _feat_d.get("geometry", {})
                        _gtype_d = _geom_d.get("type", "")
                        _coords_d = _geom_d.get("coordinates", [])
                        _polys_d = []
                        if _gtype_d == "MultiPolygon":
                            for _poly_d in _coords_d:
                                if _poly_d and _poly_d[0]:
                                    _polys_d.append(_MplPathCl2(np.array(_poly_d[0])))
                        elif _gtype_d == "Polygon":
                            if _coords_d and _coords_d[0]:
                                _polys_d.append(_MplPathCl2(np.array(_coords_d[0])))
                        for _pp_d in _polys_d:
                            _mask_d = _pp_d.contains_points(_cl_pts_all)
                            for _ix_d in np.where(_mask_d)[0]:
                                _cl_depts[_ix_d] = _dname

                if len(_cl_ev) == 0:
                    st.info("Aucun pixel disponible pour ce critere.")
                else:
                    _cl_lats = _cl_ev["latitude"].tolist()
                    _cl_lons = _cl_ev["longitude"].tolist()
                    _cl_prec = _cl_ev["precipitation_mm"].tolist()
                    _cl_anom = _cl_ev["anomaly_standardized"].tolist()
                    _cl_regs = _cl_ev["region"].tolist()
                    _cl_cats = _cl_ev["intensity_category"].tolist()

                    # GeoJSON pixels CHIRPS (0.05 deg)
                    _cl_HALF = 0.025
                    _cl_px_geo = {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature", "id": str(i),
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [[
                                        [lo - _cl_HALF, la - _cl_HALF],
                                        [lo + _cl_HALF, la - _cl_HALF],
                                        [lo + _cl_HALF, la + _cl_HALF],
                                        [lo - _cl_HALF, la + _cl_HALF],
                                        [lo - _cl_HALF, la - _cl_HALF],
                                    ]]
                                },
                                "properties": {"id": i},
                            }
                            for i, (la, lo) in enumerate(zip(_cl_lats, _cl_lons))
                        ],
                    }
                    _cl_ids_px = [str(i) for i in range(len(_cl_lats))]

                    # customdata : [valeur_croisee, region, categorie, lat, lon, dept, valeur_principale]
                    _cl_cd_prec = [
                        [f"{a:+.1f}", rg, ct, la, lo, dp, f"{p:.1f}"]
                        for a, rg, ct, la, lo, dp, p
                        in zip(_cl_anom, _cl_regs, _cl_cats,
                               _cl_lats, _cl_lons, _cl_depts, _cl_prec)
                    ]
                    _cl_cd_anom = [
                        [f"{p:.1f}", rg, ct, la, lo, dp, f"{a:+.1f}"]
                        for p, rg, ct, la, lo, dp, a
                        in zip(_cl_prec, _cl_regs, _cl_cats,
                               _cl_lats, _cl_lons, _cl_depts, _cl_anom)
                    ]

                    # Bornes adaptatives
                    _cl_p_max = float(np.percentile(_cl_prec, 99))
                    _cl_p_min = max(0.0, float(np.percentile(_cl_prec, 1)))
                    _cl_a_abs = max(
                        abs(float(np.percentile(_cl_anom, 2))),
                        abs(float(np.percentile(_cl_anom, 98))),
                        2.5,
                    )

                    _cl_ctr_lat = float(_cl_ev["latitude"].mean())
                    _cl_ctr_lon = float(_cl_ev["longitude"].mean())

                    _CS_PREC_CL = [
                        [0.00, "#FFFFFF"], [0.04, "#FFF9C4"], [0.14, "#FFEB3B"],
                        [0.30, "#FF9800"], [0.55, "#F44336"], [0.80, "#9C27B0"],
                        [1.00, "#1A237E"],
                    ]
                    _CS_ANOM_CL = [
                        [0.00, "#053061"], [0.12, "#2166AC"], [0.26, "#74ADD1"],
                        [0.42, "#D1E5F0"], [0.50, "#FFFFFF"],
                        [0.58, "#FDDBC7"], [0.74, "#F4A582"],
                        [0.88, "#D6604D"], [1.00, "#67001F"],
                    ]

                    _cl_bmap = dict(
                        style="carto-positron",
                        center=dict(lat=_cl_ctr_lat, lon=_cl_ctr_lon),
                        zoom=5.5,
                    )
                    _cl_mgn = dict(l=0, r=0, t=36, b=0)

                    # Overlays : contours departements + centroide
                    def _cl_add_overlays(fig):
                        if _cl_dept_geo is not None:
                            _lo_b, _la_b = [], []
                            for _fbt in _cl_dept_geo.get("features", []):
                                _gbm = _fbt.get("geometry", {})
                                _rings = []
                                if _gbm.get("type") == "Polygon":
                                    _rings = _gbm.get("coordinates", [])
                                elif _gbm.get("type") == "MultiPolygon":
                                    for _pb in _gbm.get("coordinates", []):
                                        _rings.extend(_pb)
                                for _rng in _rings:
                                    for _xb, _yb in _rng:
                                        _lo_b.append(_xb)
                                        _la_b.append(_yb)
                                    _lo_b.append(None)
                                    _la_b.append(None)
                            fig.add_trace(go.Scattermapbox(
                                lat=_la_b, lon=_lo_b, mode="lines",
                                line=dict(width=0.8, color="rgba(15,23,42,0.45)"),
                                hoverinfo="none", showlegend=False,
                            ))
                        fig.add_trace(go.Scattermapbox(
                            lat=[_cl_ctr_lat], lon=[_cl_ctr_lon], mode="markers",
                            marker=dict(size=18, color="white", opacity=0.9),
                            hoverinfo="skip", showlegend=False,
                        ))
                        fig.add_trace(go.Scattermapbox(
                            lat=[_cl_ctr_lat], lon=[_cl_ctr_lon], mode="markers",
                            marker=dict(size=12, color=ROSE, opacity=0.95),
                            hovertemplate=(
                                f"<b>Centroide</b><br>"
                                f"{_cl_ctr_lat:.1f}°N {abs(_cl_ctr_lon):.1f}°W"
                                "<extra></extra>"
                            ),
                            showlegend=False,
                        ))

                    _cl_map_col, _cl_info_col = st.columns([5, 4], gap="medium")

                    # ── Carte Precipitations ─────────────────────────────────
                    with _cl_map_col:
                        st.markdown(
                            '<p class="pnl-ttl" style="margin-bottom:4px">'
                            '&#127783; Précipitation (mm)</p>',
                            unsafe_allow_html=True,
                        )
                        with st.spinner("Chargement de la carte..."):
                            _cl_fig1 = go.Figure()
                            _cl_fig1.add_trace(go.Choroplethmapbox(
                                geojson=_cl_px_geo,
                                locations=_cl_ids_px,
                                z=_cl_prec,
                                colorscale=_CS_PREC_CL,
                                zmin=_cl_p_min, zmax=_cl_p_max,
                                marker=dict(
                                    opacity=0.87,
                                    line=dict(width=0.4, color="rgba(255,255,255,0.12)"),
                                ),
                                colorbar=dict(
                                    title=dict(text="mm", font=dict(size=11, color=MUTED)),
                                    thickness=12, len=0.82, x=1.01,
                                    tickfont=dict(size=10, color=MUTED),
                                    outlinewidth=0,
                                ),
                                hoverinfo="skip",
                            ))
                            _cl_fig1.add_trace(go.Scattermapbox(
                                lat=_cl_lats, lon=_cl_lons, mode="markers",
                                marker=dict(size=8, opacity=0, color="rgba(0,0,0,0)"),
                                customdata=_cl_cd_prec,
                                hovertemplate=(
                                    "<b>%{customdata[6]} mm</b> | %{customdata[0]}σ<br>"
                                    "Département : <b>%{customdata[5]}</b><br>"
                                    "Région : %{customdata[1]}<br>"
                                    "Catégorie : <b>%{customdata[2]}</b>"
                                    "<extra></extra>"
                                ),
                                showlegend=False,
                            ))
                            _cl_add_overlays(_cl_fig1)
                            _cl_fig1.update_layout(
                                mapbox=_cl_bmap, margin=_cl_mgn, height=430,
                                plot_bgcolor=CARD, paper_bgcolor=CARD,
                                title=dict(
                                    text=(
                                        f"<b>{_cl_date}</b> · {_cl_lbl}"
                                        f" · Cluster {_cl_carto_sel}"
                                    ),
                                    font=dict(size=10, color=MUTED), x=0, pad=dict(l=4),
                                ),
                            )
                            st.plotly_chart(
                                _cl_fig1, use_container_width=True,
                                key="cl_carto_map1",
                                config={
                                    "displayModeBar": True,
                                    "modeBarButtonsToRemove": [
                                        "lasso2d", "select2d", "autoScale2d",
                                        "hoverClosestMapbox",
                                    ],
                                    "displaylogo": False,
                                    "toImageButtonOptions": {
                                        "format": "png",
                                        "filename": (
                                            f"cluster{_cl_carto_sel}"
                                            f"_{_cl_sel_crit}_{_cl_date}"
                                        ),
                                    },
                                },
                            )

                    # ── Fiche evenement ──────────────────────────────────────
                    with _cl_info_col:
                        st.markdown(
                            '<p class="pnl-ttl" style="margin-bottom:8px">'
                            '&#128203; Fiche &eacute;v&eacute;nement</p>',
                            unsafe_allow_html=True,
                        )

                        _cl_reg_stats = (
                            _cl_ev.groupby("region")["precipitation_mm"]
                            .agg(max_p="max", mean_p="mean")
                            .sort_values("max_p", ascending=False)
                        )
                        _cl_top_reg     = _cl_reg_stats.index[0] if len(_cl_reg_stats) else "-"
                        _cl_top_max     = float(_cl_reg_stats.iloc[0]["max_p"]) if len(_cl_reg_stats) else 0
                        _cl_top_moy     = float(_cl_reg_stats.iloc[0]["mean_p"]) if len(_cl_reg_stats) else 0

                        _cl_pmax_v  = f"{_cl_ev['precipitation_mm'].max():.1f}"
                        _cl_pmoy_v  = f"{_cl_ev['precipitation_mm'].mean():.1f}"
                        _cl_amax_v  = f"{_cl_ev['anomaly_standardized'].max():.1f}"
                        _cl_amoy_v  = f"{_cl_ev['anomaly_standardized'].mean():.1f}"
                        _cl_ext_n   = int((_cl_ev["anomaly_standardized"] > 2.0).sum())
                        _cl_ext_pct = _cl_ext_n / len(_cl_ev) * 100
                        _cl_ph_raw  = _cl_ev["season_phase"].iloc[0] if len(_cl_ev) > 0 else ""
                        _PHASE_FR_CL2 = {
                            "Phase_1_debut":  "Phase 1 &mdash; D&eacute;but (Mai-Juin)",
                            "Phase_2_pleine": "Phase 2 &mdash; Pleine (Juil-Ao&ucirc;t)",
                            "Phase_3_fin":    "Phase 3 &mdash; Fin (Sep-Oct)",
                        }
                        _cl_ph_lbl  = _PHASE_FR_CL2.get(_cl_ph_raw, _cl_ph_raw)
                        _cl_ph_clr  = PHASE_C.get(_cl_ph_raw, MUTED)

                        def _cl_pbar(pct, color, bg=BORDER):
                            w = min(max(float(pct), 0), 100)
                            return (
                                f'<div style="height:6px;background:{bg};border-radius:99px;'
                                f'margin-top:4px;overflow:hidden;">'
                                f'<div style="width:{w:.1f}%;height:100%;background:{color};'
                                f'border-radius:99px;"></div></div>'
                            )

                        def _cl_mrow(label, value, unit="", color=TEXT):
                            return (
                                f'<div style="display:flex;justify-content:space-between;'
                                f'align-items:baseline;padding:6px 0;'
                                f'border-bottom:1px solid {BORDER};">'
                                f'<span style="font-size:0.75rem;color:{MUTED}">{label}</span>'
                                f'<span style="font-size:0.85rem;font-weight:700;color:{color}">'
                                f'{value}'
                                f'<span style="font-size:0.72rem;font-weight:500;color:{MUTED};'
                                f'margin-left:2px">{unit}</span></span></div>'
                            )

                        _cl_html_hdr = (
                            f'<div style="border-bottom:3px solid {_cl_fg0};'
                            f'padding:14px 16px 12px 16px;background:{_cl_bgcrit};">'
                            f'<div style="display:flex;align-items:flex-start;'
                            f'justify-content:space-between;gap:8px;">'
                            f'<div>'
                            f'<p style="margin:0 0 2px 0;font-size:0.72rem;font-weight:700;'
                            f'color:{_cl_fg0};text-transform:uppercase;letter-spacing:0.07em">'
                            f'Cluster {_cl_carto_sel} &nbsp;&middot;&nbsp; {_cl_lbl}</p>'
                            f'<p style="margin:0 0 6px 0;font-size:1.05rem;font-weight:800;'
                            f'color:{TEXT};line-height:1.2">{_cl_date}</p>'
                            f'</div>'
                            f'</div>'
                            f'<span style="background:{_cl_ph_clr}22;color:{_cl_ph_clr};'
                            f'font-size:0.72rem;font-weight:700;border-radius:6px;'
                            f'padding:3px 9px;display:inline-block">'
                            f'{_cl_ph_lbl}</span>'
                            f'</div>'
                        )
                        _cl_html_body = (
                            f'<div style="padding:8px 16px 16px 16px;">'
                            + _cl_mrow("Pr&#233;cip. max",      _cl_pmax_v, "mm", BLUE)
                            + _cl_mrow("Pr&#233;cip. moyenne",  _cl_pmoy_v, "mm")
                            + _cl_mrow("Anomalie max",          _cl_amax_v, "&#963;", "#7C3AED")
                            + _cl_mrow("Anomalie moyenne",      _cl_amoy_v, "&#963;")
                            + f'<div style="padding:7px 0 4px 0;border-bottom:1px solid {BORDER};">'
                            + f'<div style="display:flex;justify-content:space-between;'
                            + f'align-items:baseline;margin-bottom:3px;">'
                            + f'<span style="font-size:0.75rem;color:{MUTED}">'
                            + f'Pixels extr&ecirc;mes (&gt;2&#963;)</span>'
                            + f'<span style="font-size:0.85rem;font-weight:700;color:{AMBER}">'
                            + f'{_cl_ext_pct:.1f}%&nbsp;({_cl_ext_n}&nbsp;px)</span>'
                            + f'</div>' + _cl_pbar(_cl_ext_pct, AMBER) + f'</div>'
                            + _cl_mrow("R&#233;gion principale", _cl_top_reg)
                            + f'<div style="padding:5px 0;border-bottom:1px solid {BORDER};">'
                            + f'<div style="display:flex;justify-content:space-between;'
                            + f'align-items:baseline;margin-bottom:3px;">'
                            + f'<span style="font-size:0.75rem;color:{MUTED}">'
                            + f'R&#233;gion la plus intense</span>'
                            + f'<span style="font-size:0.85rem;font-weight:700;color:{ROSE}">'
                            + f'{_cl_top_reg}</span></div>'
                            + f'<div style="font-size:0.72rem;color:{MUTED};">'
                            + f'max {_cl_top_max:.1f}&nbsp;mm &nbsp;&#183;&nbsp;'
                            + f' moy.&nbsp;{_cl_top_moy:.1f}&nbsp;mm</div>'
                            + f'</div>'
                            + f'<div style="padding:8px 0 0 0;">'
                            + f'<span style="font-size:0.72rem;color:{MUTED};">'
                            + f'Total pixels&nbsp;: {len(_cl_ev)}</span></div>'
                            + f'</div>'
                        )
                        st.html(
                            f'<div style="background:{CARD};border:1px solid {BORDER};'
                            f'border-radius:14px;overflow:hidden;'
                            f'box-shadow:0 1px 3px rgba(0,0,0,0.04),'
                            f'0 4px 16px rgba(0,0,0,0.05);">'
                            + _cl_html_hdr + _cl_html_body
                            + f'</div>'
                        )


        # ════════════════════════════════════════════════════════════════════
        # CARTES PUBLICATION QUALITE (script 14 - cartopy)
        # ════════════════════════════════════════════════════════════════════
        st.markdown(f"""
        <div style="border-top:2px solid {BORDER};margin:24px 0 18px 0;"></div>
        <h2 style="font-size:1.05rem;font-weight:800;color:{TEXT};margin:0 0 6px 0;">
          Cartes SST — Qualite publication (cartopy)</h2>
        <p style="font-size:0.78rem;color:{MUTED};margin:0 0 16px 0;">
          Figures multi-panneaux generees par le script 14 : anomalies SST globales
          (tropiques) et zoom Atlantique / Afrique de l'Ouest pour chaque cluster.
          Hachurage des anomalies |z| > 0.5 sigma (signal robuste).</p>
        """, unsafe_allow_html=True)

        SST_PAT_DIR = BASE / "outputs/visualizations/clustering/sst_patterns"
        PHASE_LABELS_PUB = {
            "Phase_1_debut":  "Phase 1 - Debut (Mai-Juin)",
            "Phase_2_pleine": "Phase 2 - Pleine (Juillet-Aout)",
            "Phase_3_fin":    "Phase 3 - Fin (Septembre-Octobre)",
            "All_phases":     "Toutes phases confondues",
        }

        # Affiche directement l'image correspondant a la phase selectionnee
        img_path = SST_PAT_DIR / f"{sel_phase}_sst_patterns_clusters.png"
        if img_path.exists():
            st.image(str(img_path), use_container_width=True)
        else:
            st.info(
                f"Image non disponible pour {PHASE_LABELS_PUB.get(sel_phase, sel_phase)}. "
                f"Executez le script 14 pour generer les cartes."
            )

# =============================================================================
# PAGE PIPELINE
# =============================================================================
if page == "Pipeline":
    import subprocess
    import sys
    import time
    import shutil

    SCRIPTS_DIR = BASE / "scripts"

    # ── CSS pipeline ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <style>
    /* ─ Sections ─ */
    .pip-section {{
        background:{CARD};border:1px solid {BORDER};
        border-radius:16px;padding:24px 28px;margin-bottom:16px;
    }}
    .pip-section-title {{
        font-size:0.7rem;font-weight:700;color:{MUTED};
        text-transform:uppercase;letter-spacing:1.2px;
        margin:0 0 16px 0;display:flex;align-items:center;gap:8px;
    }}
    /* ─ Bbox visual ─ */
    .bbox-vis {{
        background:linear-gradient(135deg,{INDIGO}12,{BLUE}08);
        border:1px solid {INDIGO}40;border-radius:12px;
        padding:16px 20px;
    }}
    .bbox-pill {{
        display:inline-flex;align-items:center;gap:6px;
        background:{CARD};border:1px solid {BORDER};border-radius:8px;
        padding:6px 12px;font-size:0.78rem;font-weight:600;
        color:{TEXT};margin:3px;
    }}
    .bbox-pill span {{ color:{INDIGO};font-weight:700; }}
    /* ─ Step card ─ */
    .step-card {{
        background:{CARD};border:1px solid {BORDER};
        border-radius:14px;margin-bottom:10px;overflow:hidden;
    }}
    .step-card-top {{
        display:flex;align-items:flex-start;gap:14px;
        padding:16px 20px;
    }}
    .step-card-top:hover {{ background:{"rgba(255,255,255,0.05)" if st.session_state.dark_mode else "#FAFBFF"}; }}
    .step-num {{
        width:34px;height:34px;border-radius:50%;flex-shrink:0;
        display:flex;align-items:center;justify-content:center;
        font-size:0.78rem;font-weight:800;color:#fff;margin-top:1px;
    }}
    .step-info {{ flex:1;min-width:0; }}
    .step-label {{
        font-size:0.86rem;font-weight:700;color:{TEXT};margin:0 0 3px 0;
    }}
    .step-desc {{
        font-size:0.75rem;color:{MUTED};margin:0 0 8px 0;line-height:1.5;
    }}
    .step-badges {{ display:flex;gap:5px;flex-wrap:wrap; }}
    .sbadge {{
        font-size:0.63rem;font-weight:700;padding:3px 8px;border-radius:20px;
        white-space:nowrap;letter-spacing:.5px;text-transform:uppercase;
    }}
    .sbadge-ok   {{ background:rgba(16,185,129,0.15);color:#059669; }}
    .sbadge-miss {{ background:rgba(239,68,68,0.15);color:#DC2626; }}
    .sbadge-info {{ background:rgba(124,58,237,0.15);color:#7C3AED; }}
    .sbadge-warn {{ background:rgba(245,158,11,0.15);color:#D97706; }}
    /* ─ Export pills ─ */
    .step-card-exports {{
        border-top:1px solid {BORDER};background:{BG};
        padding:10px 20px 12px 68px;
    }}
    .exp-label {{
        font-size:0.65rem;font-weight:700;color:{MUTED};
        text-transform:uppercase;letter-spacing:.8px;margin:0 0 8px 0;
    }}
    /* ─ Progress bar pipeline ─ */
    .pip-progress-track {{
        background:{BORDER};border-radius:99px;height:6px;
        overflow:hidden;margin:8px 0 4px 0;
    }}
    .pip-progress-fill {{
        height:100%;border-radius:99px;
        background:linear-gradient(90deg,{INDIGO},{BLUE});
        transition:width .4s ease;
    }}
    /* ─ Run hero ─ */
    .run-hero {{
        background:linear-gradient(135deg,{INDIGO} 0%,{BLUE} 100%);
        border-radius:16px;padding:24px 28px;margin-bottom:4px;
    }}
    .run-hero h3 {{
        color:#fff;font-size:1.1rem;font-weight:800;margin:0 0 4px 0;
    }}
    .run-hero p {{
        color:rgba(255,255,255,.75);font-size:0.8rem;margin:0;
    }}
    /* ─ Category label ─ */
    .cat-label {{
        font-size:0.68rem;font-weight:800;letter-spacing:1.4px;
        text-transform:uppercase;padding:0 0 8px 0;
        border-bottom:2px solid currentColor;margin:20px 0 10px 0;
        display:inline-block;
    }}
    /* ─ Size badges ─ */
    .sz-ok   {{color:#059669;background:rgba(16,185,129,0.15);padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    .sz-warn {{color:#D97706;background:rgba(245,158,11,0.15);padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    .sz-big  {{color:#DC2626;background:rgba(239,68,68,0.15);padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    </style>
    """, unsafe_allow_html=True)

    # ── Header ───────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Pipeline</b></p>
        <h1 class="pg-ttl">Pipeline d\'Analyse</h1>
        <p class="pg-sub">
          Telechargement CHIRPS &nbsp;&middot;&nbsp;
          Detection &nbsp;&middot;&nbsp;
          Teleconnexions &nbsp;&middot;&nbsp;
          Clustering &nbsp;&middot;&nbsp;
          Export
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Navigation onglets ────────────────────────────────────────────────────
    if "pip_tab" not in st.session_state:
        st.session_state.pip_tab = "Pipeline d'analyse"

    TAB_ICONS = {
        "Donnees CHIRPS":    "&#9729;",
        "Pipeline d'analyse":"&#9654;",
        "Donnees SST":       "&#127754;",
    }
    TAB_NAMES = ["Donnees CHIRPS", "Pipeline d'analyse", "Donnees SST"]

    _cur_tab = st.session_state.pip_tab

    # CSS injecte une seule fois : restyle les boutons de navigation
    st.markdown(f"""
    <style>
    /* Barre de navigation Pipeline */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div > div[data-testid="stVerticalBlockBorderWrapper"] {{
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
    }}
    .pip-tab-bar {{
        display: flex;
        gap: 0;
        background: {CARD};
        border: 1.5px solid {BORDER};
        border-radius: 14px;
        padding: 5px;
        margin-bottom: 24px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }}
    .pip-tab-item {{
        flex: 1;
        border-radius: 10px;
        padding: 11px 8px;
        text-align: center;
        cursor: pointer;
        transition: all .18s ease;
        border: none;
        background: transparent;
        color: {MUTED};
        text-decoration: none;
    }}
    .pip-tab-item.active {{
        background: linear-gradient(135deg, {INDIGO} 0%, {BLUE} 100%);
        color: #fff;
        box-shadow: 0 3px 10px {INDIGO}55;
    }}
    .pip-tab-item:hover:not(.active) {{
        background: {INDIGO}10;
        color: {INDIGO};
    }}
    .pip-tab-icon {{
        font-size: 1.15rem;
        display: block;
        margin-bottom: 3px;
    }}
    .pip-tab-label {{
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: .2px;
        display: block;
    }}
    </style>
    """, unsafe_allow_html=True)

    nav_c1, nav_c2, nav_c3 = st.columns(3)
    for col, name in zip([nav_c1, nav_c2, nav_c3], TAB_NAMES):
        is_active = _cur_tab == name
        with col:
            # Label avec marqueur "ACTIF" visible
            if is_active:
                btn_label = f"{TAB_ICONS[name]}  {name}"
            else:
                btn_label = f"{TAB_ICONS[name]}  {name}"
            if st.button(
                btn_label,
                key=f"pip_nav_{name}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.pip_tab = name
                _cur_tab = name
                st.rerun()
            # Indicateur visuel sous le bouton actif
            if is_active:
                st.markdown(
                    f"<div style='height:4px;background:linear-gradient(90deg,{INDIGO},{BLUE});"
                    f"border-radius:2px;margin-top:-12px;margin-bottom:4px'></div>"
                    f"<div style='text-align:center;font-size:0.65rem;font-weight:800;"
                    f"color:{INDIGO};letter-spacing:1.2px;text-transform:uppercase;"
                    f"margin-bottom:6px'>&#9650; actif</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)

    st.markdown(
        f"<div style='height:2px;background:linear-gradient(90deg,{INDIGO}40,{BLUE}40);"
        f"border-radius:2px;margin-bottom:22px'></div>",
        unsafe_allow_html=True,
    )

    _show_chirps   = (_cur_tab == "Donnees CHIRPS")
    _show_pipeline = (_cur_tab == "Pipeline d'analyse")
    _show_sst      = (_cur_tab == "Donnees SST")

    # =========================================================================
    # ONGLET 1 — CHIRPS
    # =========================================================================
    if _show_chirps:

        PRESETS = {
            "Senegal":       dict(lat_min=12.0,  lat_max=17.0,  lon_min=-17.6, lon_max=-11.3,
                                  flag="SN", desc="12-17 N / 17.6-11.3 W"),
            "Afrique Ouest": dict(lat_min=4.0,   lat_max=24.0,  lon_min=-18.0, lon_max=16.0,
                                  flag="WA", desc="4-24 N / 18 W-16 E"),
            "Sahel":         dict(lat_min=10.0,  lat_max=20.0,  lon_min=-18.0, lon_max=40.0,
                                  flag="SH", desc="10-20 N / 18 W-40 E"),
            "Afrique":       dict(lat_min=-35.0, lat_max=37.5,  lon_min=-18.0, lon_max=52.0,
                                  flag="AF", desc="35 S-37.5 N / 18 W-52 E"),
        }

        if "chirps_preset" not in st.session_state:
            st.session_state.chirps_preset = "Afrique Ouest"
            _p0 = PRESETS["Afrique Ouest"]
            for _k, _v in [("bb_lat_min", _p0["lat_min"]), ("bb_lat_max", _p0["lat_max"]),
                            ("bb_lon_min", _p0["lon_min"]), ("bb_lon_max", _p0["lon_max"])]:
                st.session_state[_k] = float(_v)

        # ── Zone geographique ─────────────────────────────────────────────────
        st.markdown(
            "<p class='pip-section-title'>Zone geographique</p>",
            unsafe_allow_html=True,
        )

        preset_cols = st.columns(len(PRESETS))
        for i, (pname, pvals) in enumerate(PRESETS.items()):
            with preset_cols[i]:
                is_active = st.session_state.chirps_preset == pname
                flag_txt  = pvals["flag"]
                desc_txt  = pvals["desc"]
                if st.button(
                    f"{flag_txt}  {pname}",
                    key=f"preset_{pname}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                    help=desc_txt,
                ):
                    st.session_state.chirps_preset = pname
                    for _k, _fk in [("bb_lat_min","lat_min"),("bb_lat_max","lat_max"),
                                     ("bb_lon_min","lon_min"),("bb_lon_max","lon_max")]:
                        st.session_state[_k] = float(pvals[_fk])
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # 4 champs bbox — coin SW / coin NE
        inp_c1, inp_c2, inp_c3, inp_c4 = st.columns(4)
        with inp_c1:
            bb_lat_min = st.number_input("Lat min (S)", min_value=-35.0, max_value=37.0,
                                          step=0.25, key="bb_lat_min", format="%.2f")
        with inp_c2:
            bb_lat_max = st.number_input("Lat max (N)", min_value=-35.0, max_value=37.0,
                                          step=0.25, key="bb_lat_max", format="%.2f")
        with inp_c3:
            bb_lon_min = st.number_input("Lon min (W)", min_value=-18.0, max_value=52.0,
                                          step=0.25, key="bb_lon_min", format="%.2f")
        with inp_c4:
            bb_lon_max = st.number_input("Lon max (E)", min_value=-18.0, max_value=52.0,
                                          step=0.25, key="bb_lon_max", format="%.2f")

        # Résumé visuel bbox
        dlat = max(0.0, bb_lat_max - bb_lat_min)
        dlon = max(0.0, bb_lon_max - bb_lon_min)
        nlat = max(0, int(round(dlat / 0.25)))
        nlon = max(0, int(round(dlon / 0.25)))
        n_pix = nlat * nlon
        st.markdown(
            f"<div class='bbox-vis'>"
            f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:10px;'>"
            f"  <span class='bbox-pill'>Lat <span>{bb_lat_min:.2f}&deg; &rarr; {bb_lat_max:.2f}&deg; N</span></span>"
            f"  <span class='bbox-pill'>Lon <span>{bb_lon_min:.2f}&deg; &rarr; {bb_lon_max:.2f}&deg;</span></span>"
            f"  <span class='bbox-pill'>Hauteur <span>{dlat:.2f}&deg; &bull; {nlat} px</span></span>"
            f"  <span class='bbox-pill'>Largeur <span>{dlon:.2f}&deg; &bull; {nlon} px</span></span>"
            f"  <span class='bbox-pill'>Grille <span>{nlat} x {nlon} = {n_pix:,} px/jour</span></span>"
            f"</div>"
            f"<div style='font-family:monospace;font-size:0.72rem;color:{MUTED};line-height:1.7;'>"
            f"NW ({bb_lat_max:.2f}N, {bb_lon_min:.2f}) &mdash;&mdash;&mdash;"
            f" NE ({bb_lat_max:.2f}N, {bb_lon_max:.2f})<br>"
            f"SW ({bb_lat_min:.2f}N, {bb_lon_min:.2f}) &mdash;&mdash;&mdash;"
            f" SE ({bb_lat_min:.2f}N, {bb_lon_max:.2f})"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Periode + Fichier ─────────────────────────────────────────────────
        st.markdown(
            "<p class='pip-section-title'>Periode et fichier de sortie</p>",
            unsafe_allow_html=True,
        )

        pr_c1, pr_c2, pr_c3 = st.columns([3, 3, 4])

        with pr_c1:
            yr_range = st.slider(
                "Periode",
                min_value=1981, max_value=2025,
                value=(1981, 2023),
                key="dl_yr_range",
            )
            dl_year_start, dl_year_end = yr_range
            n_years_dl  = max(0, dl_year_end - dl_year_start + 1)
            est_size_mb = n_years_dl * 120
            sz_cls = "sz-ok" if est_size_mb < 500 else ("sz-warn" if est_size_mb < 2000 else "sz-big")
            est_gb  = est_size_mb / 1024
            st.markdown(
                f"<div style='margin-top:4px;display:flex;gap:8px;align-items:center;'>"
                f"<span style='font-weight:700;color:{TEXT};'>{dl_year_start} &ndash; {dl_year_end}</span>"
                f"<span class='{sz_cls}'>{n_years_dl} ans &bull; ~{est_gb:.1f} GB</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with pr_c2:
            default_out_name = f"chirps_WA_{dl_year_start}_{dl_year_end}_dayly.mat"
            dl_out_name = st.text_input(
                "Nom du fichier .mat",
                value=default_out_name,
                key="dl_out_name",
            )
            out_path_preview = BASE / "data" / "raw" / dl_out_name
            exists_already   = out_path_preview.exists()
            ex_tag = (
                "<span class='sbadge sbadge-warn'>Sera ecrase</span>"
                if exists_already else
                "<span class='sbadge sbadge-info'>Nouveau</span>"
            )
            st.markdown(
                f"<p style='font-size:0.71rem;color:{MUTED};margin:4px 0 0 0;'>"
                f"<code>data/raw/{dl_out_name}</code> {ex_tag}</p>",
                unsafe_allow_html=True,
            )

        with pr_c3:
            st.markdown(
                "<p style='font-size:0.72rem;font-weight:700;color:" + MUTED +
                ";text-transform:uppercase;letter-spacing:1px;margin:0 0 6px 0;'>"
                "Fichiers .mat existants</p>",
                unsafe_allow_html=True,
            )
            existing_mats = sorted((BASE / "data" / "raw").glob("*.mat"))
            if existing_mats:
                for mf in existing_mats:
                    sz_mb = mf.stat().st_size / 1e6
                    is_cur = mf.name == dl_out_name
                    bullet = ">" if is_cur else "-"
                    color  = INDIGO if is_cur else MUTED
                    st.markdown(
                        f"<p style='font-size:0.72rem;color:{color};margin:2px 0;"
                        f"font-weight:{'700' if is_cur else '400'};'>"
                        f"{bullet} <code>{mf.name}</code>"
                        f"<span style='color:{EMERALD};margin-left:6px;'>{sz_mb:.0f} MB</span></p>",
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("Aucun fichier .mat dans data/raw/")

        # ── Helpers statut CHIRPS ────────────────────────────────────────────
        import json as _json_ch
        CHIRPS_STATUS_FILE = BASE / "data" / "raw" / ".download_chirps_status.json"
        CHIRPS_CANCEL_FILE = BASE / "data" / "raw" / ".cancel_chirps"
        CHIRPS_DL_SCRIPT   = BASE / "scripts" / "download_chirps.py"

        def _read_chirps_status():
            try:
                return _json_ch.loads(CHIRPS_STATUS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return None

        def _chirps_running():
            pid = st.session_state.get("chirps_dl_pid")
            if not pid:
                return False
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

        chirps_status = _read_chirps_status()
        chirps_is_running = _chirps_running()

        # ── Affichage progression ────────────────────────────────────────────
        if chirps_status:
            ch_state    = chirps_status.get("state", "")
            ch_done     = chirps_status.get("done", 0)
            ch_total    = chirps_status.get("total", 0)
            ch_year     = chirps_status.get("current_year")
            ch_pct      = chirps_status.get("current_pct", 0)
            ch_phase    = chirps_status.get("phase", "")
            ch_errors   = chirps_status.get("errors", [])
            ch_output   = chirps_status.get("output", "")
            overall_pct = int(ch_done / ch_total * 100) if ch_total > 0 else 100

            if ch_state == "running":
                st_html = f'<span style="color:#F59E0B;font-weight:700;">En cours</span>'
            elif ch_state == "done":
                st_html = f'<span style="color:#22C55E;font-weight:700;">Termine</span>'
            elif ch_state == "cancelled":
                st_html = f'<span style="color:#EF4444;font-weight:700;">Annule</span>'
            elif ch_state == "error":
                st_html = f'<span style="color:#EF4444;font-weight:700;">Erreur</span>'
            else:
                st_html = f'<span style="color:{MUTED};">{ch_state}</span>'

            phase_label = {
                "telechargement": "Telechargement",
                "decoupage":      "Decoupage bbox",
                "sauvegarde":     "Sauvegarde HDF5",
            }.get(ch_phase, ch_phase)

            st.markdown(f"""
            <div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;
                        padding:16px 20px;margin-bottom:14px;">
              <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:0.82rem;font-weight:600;color:{TEXT};">
                  Statut : {st_html}
                  {"&nbsp;<span style='color:" + MUTED + ";font-weight:400;font-size:0.75rem;'>" + phase_label + "</span>" if ch_year else ""}
                </span>
                <span style="font-size:0.78rem;color:{MUTED};">
                  {ch_done}/{ch_total} annees &nbsp;|&nbsp; {ch_output}
                </span>
              </div>
              <div style="background:{BORDER};border-radius:99px;height:7px;overflow:hidden;margin-bottom:8px;">
                <div style="width:{overall_pct}%;height:100%;border-radius:99px;
                            background:linear-gradient(90deg,{INDIGO},{BLUE});"></div>
              </div>
              {"<p style='font-size:0.75rem;color:" + MUTED + ";margin:0;'>Annee en cours : <b>" + str(ch_year) + "</b> — " + str(ch_pct) + "%</p>" if ch_year else ""}
              {"<p style='font-size:0.72rem;color:#EF4444;margin:6px 0 0 0;'>" + str(len(ch_errors)) + " erreur(s) : " + ", ".join(str(e["year"]) for e in ch_errors) + "</p>" if ch_errors else ""}
              <p style="font-size:0.68rem;color:{MUTED};margin:6px 0 0 0;">
                Derniere mise a jour : {chirps_status.get("updated_at", "")}
              </p>
              {"<p style='font-size:0.78rem;color:#22C55E;margin:8px 0 0 0;font-weight:600;'>" + str(chirps_status.get('n_days','')) + " jours &bull; " + str(chirps_status.get('n_lat','')) + "x" + str(chirps_status.get('n_lon','')) + " pixels &bull; " + str(chirps_status.get('size_mb','')) + " Mo</p>" if ch_state == "done" else ""}
            </div>
            """, unsafe_allow_html=True)

        # ── Bouton lancement / annulation ────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)

        if chirps_is_running:
            col_ref, col_can = st.columns([1, 1])
            with col_ref:
                if st.button("Actualiser la progression", key="btn_chirps_refresh"):
                    st.rerun()
            with col_can:
                if st.button("Annuler le telechargement", key="btn_chirps_cancel"):
                    CHIRPS_CANCEL_FILE.touch()
                    st.warning("Signal d'annulation envoye. Arret apres l'annee en cours.")
                    st.rerun()
            # Auto-refresh
            time.sleep(3)
            st.rerun()
        else:
            btn_c1, btn_c2 = st.columns([2, 5])
            with btn_c1:
                launch_download = st.button(
                    "Telecharger les donnees CHIRPS",
                    key="btn_chirps_dl",
                    type="primary",
                    use_container_width=True,
                )
            with btn_c2:
                st.markdown(
                    f"<p style='font-size:0.74rem;color:{MUTED};padding-top:10px;'>"
                    f"Source : CHC UCSB &mdash; CHIRPS v2.0 Global Daily 0.25&deg;. "
                    f"Telechargement annee par annee avec reprise automatique, "
                    f"decoupage bbox et sauvegarde HDF5.</p>",
                    unsafe_allow_html=True,
                )

            if launch_download:
                if dl_year_end < dl_year_start:
                    st.error("L\'annee de fin doit etre >= a l\'annee de debut.")
                elif bb_lat_max <= bb_lat_min or bb_lon_max <= bb_lon_min:
                    st.error("Bounding box invalide (lat/lon min >= max).")
                else:
                    CHIRPS_CANCEL_FILE.unlink(missing_ok=True)
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    proc = subprocess.Popen(
                        [sys.executable, str(CHIRPS_DL_SCRIPT),
                         f"--year-start={int(dl_year_start)}",
                         f"--year-end={int(dl_year_end)}",
                         f"--lat-min={bb_lat_min}",
                         f"--lat-max={bb_lat_max}",
                         f"--lon-min={bb_lon_min}",
                         f"--lon-max={bb_lon_max}",
                         f"--output={dl_out_name}"],
                        cwd=str(BASE), env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    st.session_state["chirps_dl_pid"] = proc.pid
                    st.info(f"Telechargement lance (PID {proc.pid}).")
                    time.sleep(1)
                    st.rerun()

    # =========================================================================
    # ONGLET 2 — PIPELINE D'ANALYSE
    # =========================================================================
    if _show_pipeline:
        import io as _io
        import zipfile as _zf

        _FMT_MIME = {
            "csv":  "text/csv",
            "png":  "image/png",
            "txt":  "text/plain",
            "json": "application/json",
            "zip":  "application/zip",
        }
        _GRP_LABEL = {
            "input":   ("Donnees d'entree K-Means", "#8B5CF6"),  # VIOLET
            "data":    ("Donnees de sortie",  "#0EA5E9"),         # BLUE
            "figure":  ("Figures",  "#10B981"),                   # EMERALD
            "report":  ("Rapports", "#F59E0B"),                   # AMBER
        }

        def _make_zip(paths):
            """Cree un ZIP en memoire a partir d\'une liste de Path."""
            buf = _io.BytesIO()
            with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as zf:
                for p in paths:
                    zf.write(p, p.name)
            buf.seek(0)
            return buf.read()

        # Chaque export a : path, label, fmt, group (data/figure/report)
        # fmt special "zip_glob" : path = dossier, label = nom du zip
        PIPELINE_STEPS = [
            {
                "id": "01", "num": 1,
                "label": "Detection des evenements extremes",
                "script": "01_detection_extremes.py",
                "desc": "Detection CHIRPS >2 sigma avec clustering spatio-temporel",
                "category": "Detection", "color": BLUE,
                "outputs": ["data/processed/extreme_events_phases_senegal.csv"],
                "exports": {
                    "data": [
                        {"path": "data/processed/extreme_events_phases_senegal.csv",
                         "label": "Evenements extremes + phases"},
                        {"path": "data/processed/spatial_metrics_detailed.csv",
                         "label": "Metriques spatiales detaillees"},
                    ],
                    "report": [
                        {"path": "data/processed/phase_statistics_summary.json",
                         "label": "Statistiques par phase", "fmt": "json"},
                        {"path": "outputs/reports/detection_report.txt",
                         "label": "Rapport de detection", "fmt": "txt"},
                    ],
                },
            },
            {
                "id": "02", "num": 2,
                "label": "Distribution annuelle",
                "script": "02_distribution_annuelle.py",
                "desc": "Visualisation de la distribution annuelle par phase",
                "category": "Detection", "color": BLUE,
                "outputs": [
                    "outputs/visualizations/Distribution/02_distribution_annuelle_phases.png",
                ],
                "exports": {
                    "figure": [
                        {"path": "outputs/visualizations/Distribution/02_distribution_annuelle_phases.png",
                         "label": "Distribution annuelle par phase"},
                    ],
                },
            },
            {
                "id": "03", "num": 3,
                "label": "Filtrage et export QGIS",
                "script": "03_filter_events_for_qgis.py",
                "desc": "Export des evenements filtres pour visualisation cartographique",
                "category": "Export", "color": EMERALD,
                "outputs": ["outputs/exports/extreme_events_comprehensive.csv"],
                "exports": {
                    "data": [
                        {"path": "outputs/exports/extreme_events_comprehensive.csv",
                         "label": "Evenements complets (tous champs)"},
                        {"path": "outputs/specific_events_qgis/events_summary_statistics.csv",
                         "label": "Statistiques de synthese"},
                        {"path": "outputs/specific_events_qgis/events_centroids.csv",
                         "label": "Centroides des evenements"},
                        {"path": "outputs/specific_events_qgis/all_specific_events_pixels.csv",
                         "label": "Pixels — evenements specifiques"},
                    ],
                    "report": [
                        {"path": "outputs/specific_events_qgis/metadata.json",
                         "label": "Metadonnees QGIS", "fmt": "json"},
                    ],
                },
            },
            {
                "id": "03b", "num": 4,
                "label": "Separation par phase de saison",
                "script": "03b_split_events_by_phase.py",
                "desc": "Split Debut (Mai-Juin) / Pleine (Jul-Aou) / Fin (Sep-Oct)",
                "category": "Export", "color": EMERALD,
                "outputs": ["outputs/exports/extreme_events_phase_1_debut.csv"],
                "exports": {
                    "data": [
                        {"path": "outputs/exports/extreme_events_phase_1_debut.csv",
                         "label": "Phase 1 — Debut (Mai-Juin)"},
                        {"path": "outputs/exports/extreme_events_phase_2_pleine.csv",
                         "label": "Phase 2 — Pleine (Jul-Aou)"},
                        {"path": "outputs/exports/extreme_events_phase_3_fin.csv",
                         "label": "Phase 3 — Fin (Sep-Oct)"},
                    ],
                },
            },
            {
                "id": "sst", "num": 5,
                "label": "Extraction des indices SST journaliers",
                "script": "extract_daily_indices_from_sst.py",
                "desc": "Nino12, Nino3, Nino34, Nino4, IOD, IOBM, TNA, TSA, ATL3, AMM, AMO",
                "category": "SST", "color": INDIGO,
                "outputs": ["data/raw/climate_indices/daily_indices_all.csv"],
                "exports": {
                    "data": [
                        {"path": "data/raw/climate_indices/daily_indices_all.csv",
                         "label": "Tous les indices (fichier unique)"},
                        {"path": "data/raw/climate_indices/daily_Nino12.csv",  "label": "Nino 1+2"},
                        {"path": "data/raw/climate_indices/daily_Nino3.csv",   "label": "Nino 3"},
                        {"path": "data/raw/climate_indices/daily_Nino34.csv",  "label": "Nino 3.4"},
                        {"path": "data/raw/climate_indices/daily_Nino4.csv",   "label": "Nino 4"},
                        {"path": "data/raw/climate_indices/daily_IOD.csv",     "label": "IOD"},
                        {"path": "data/raw/climate_indices/daily_IOBM.csv",    "label": "IOBM"},
                        {"path": "data/raw/climate_indices/daily_TNA.csv",     "label": "TNA"},
                        {"path": "data/raw/climate_indices/daily_TSA.csv",     "label": "TSA"},
                        {"path": "data/raw/climate_indices/daily_ATL3.csv",    "label": "ATL3"},
                        {"path": "data/raw/climate_indices/daily_AMM.csv",     "label": "AMM"},
                        {"path": "data/raw/climate_indices/daily_AMO.csv",     "label": "AMO"},
                    ],
                },
            },
            {
                "id": "04", "num": 6,
                "label": "Teleconnexions (script principal)",
                "script": "04_teleconnections_analysis.py",
                "desc": "Correlations mensuelles SST x precipitations — detrend, AR1 (p_neff)",
                "category": "Teleconnexions", "color": ROSE,
                "outputs": [
                    "outputs/teleconnections/correlations_Phase_1_debut.csv",
                    "outputs/teleconnections/correlations_Phase_2_pleine.csv",
                    "outputs/teleconnections/correlations_Phase_3_fin.csv",
                ],
                "exports": {
                    "data": [
                        {"path": "outputs/teleconnections/correlations_Phase_1_debut.csv",
                         "label": "Correlations — Phase 1 Debut"},
                        {"path": "outputs/teleconnections/correlations_Phase_2_pleine.csv",
                         "label": "Correlations — Phase 2 Pleine"},
                        {"path": "outputs/teleconnections/correlations_Phase_3_fin.csv",
                         "label": "Correlations — Phase 3 Fin"},
                        {"path": "outputs/teleconnections/correlations_Toutes phases.csv",
                         "label": "Correlations — Toutes phases"},
                    ],
                    "figure": [
                        {"path": "outputs/teleconnections/visualizations/synthese_correlations.png",
                         "label": "Synthese des correlations"},
                        # ZIP de toutes les figures teleconnexions
                        {"path": "outputs/teleconnections/visualizations",
                         "label": "Toutes les figures (ZIP)",
                         "fmt": "zip_glob", "glob": "*.png",
                         "zip_name": "teleconnexions_figures.zip"},
                    ],
                    "report": [
                        {"path": "outputs/teleconnections/rapport_teleconnections.txt",
                         "label": "Rapport teleconnexions", "fmt": "txt"},
                    ],
                },
            },
            {
                "id": "11", "num": 7,
                "label": "Clustering KMeans SST",
                "script": "11_kmeans_sst_analysis.py",
                "desc": "KMeans sur les patterns SST globaux par phase de saison",
                "category": "Clustering", "color": AMBER,
                "outputs": [
                    "outputs/clustering/Phase_1_debut/Phase_1_debut_cluster_characteristics.csv",
                ],
                "exports": {
                    "input": [
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_kmeans_input_pca.csv",
                         "label": "P1 · Matrice PCA"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_pca_explained_variance.csv",
                         "label": "P1 · Variance PCA"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_kmeans_input_pca.csv",
                         "label": "P2 · Matrice PCA"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_pca_explained_variance.csv",
                         "label": "P2 · Variance PCA"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_kmeans_input_pca.csv",
                         "label": "P3 · Matrice PCA"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_pca_explained_variance.csv",
                         "label": "P3 · Variance PCA"},
                        {"path": "outputs/clustering/All_phases/All_phases_kmeans_input_pca.csv",
                         "label": "All · Matrice PCA"},
                        {"path": "outputs/clustering/All_phases/All_phases_pca_explained_variance.csv",
                         "label": "All · Variance PCA"},
                    ],
                    "data": [
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_cluster_characteristics.csv",
                         "label": "P1 · Caracteristiques"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_events_with_clusters.csv",
                         "label": "P1 · Evenements"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_tableau_k_3_methodes.csv",
                         "label": "P1 · Tableau k (3 meth.)"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_tableau_k_4_methodes.csv",
                         "label": "P1 · Tableau k (4 meth.)"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_cluster_characteristics.csv",
                         "label": "P2 · Caracteristiques"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_events_with_clusters.csv",
                         "label": "P2 · Evenements"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_tableau_k_3_methodes.csv",
                         "label": "P2 · Tableau k (3 meth.)"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_tableau_k_4_methodes.csv",
                         "label": "P2 · Tableau k (4 meth.)"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_cluster_characteristics.csv",
                         "label": "P3 · Caracteristiques"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_events_with_clusters.csv",
                         "label": "P3 · Evenements"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_tableau_k_3_methodes.csv",
                         "label": "P3 · Tableau k (3 meth.)"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_tableau_k_4_methodes.csv",
                         "label": "P3 · Tableau k (4 meth.)"},
                        {"path": "outputs/clustering/All_phases/All_phases_cluster_characteristics.csv",
                         "label": "All · Caracteristiques"},
                        {"path": "outputs/clustering/All_phases/All_phases_events_with_clusters.csv",
                         "label": "All · Evenements"},
                        {"path": "outputs/clustering/All_phases/All_phases_tableau_k_3_methodes.csv",
                         "label": "All · Tableau k (3 meth.)"},
                    ],
                    "report": [
                        {"path": "outputs/clustering/rapport_kmeans_sst.txt",
                         "label": "Rapport KMeans SST global", "fmt": "txt"},
                    ],
                },
            },
            {
                "id": "14", "num": 8,
                "label": "Cartes SST — Cartopy",
                "script": "14_sst_patterns_cartopy.py",
                "desc": "Figures publication : anomalies SST globales par cluster",
                "category": "Visualisation", "color": EMERALD,
                "outputs": [
                    "outputs/visualizations/clustering/sst_patterns/Phase_1_debut_sst_patterns_clusters.png",
                ],
                "exports": {
                    "figure": [
                        {"path": "outputs/visualizations/clustering/sst_patterns/Phase_1_debut_sst_patterns_clusters.png",
                         "label": "Carte SST — Phase 1 Debut"},
                        {"path": "outputs/visualizations/clustering/sst_patterns/Phase_2_pleine_sst_patterns_clusters.png",
                         "label": "Carte SST — Phase 2 Pleine"},
                        {"path": "outputs/visualizations/clustering/sst_patterns/Phase_3_fin_sst_patterns_clusters.png",
                         "label": "Carte SST — Phase 3 Fin"},
                        # ZIP des 3 figures publication
                        {"path": "outputs/visualizations/clustering/sst_patterns",
                         "label": "Toutes les cartes SST (ZIP)",
                         "fmt": "zip_glob", "glob": "*.png",
                         "zip_name": "cartes_sst_publication.zip"},
                    ],
                },
            },
        ]

        def run_script(script_path):
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd=str(BASE),
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            combined = result.stdout + (
                "\n" + result.stderr if result.stderr.strip() else ""
            )
            return result.returncode, combined.strip()

        def output_status(step):
            """Retourne (ok: bool, label: str) selon l\'existence des sorties."""
            outs = step.get("outputs", [])
            if not outs:
                return None, "N/A"
            all_ok = all((BASE / o).exists() for o in outs)
            return all_ok, "Sorties presentes" if all_ok else "Non execute"

        def render_exports(step):
            """Affiche les boutons de telechargement groupes par type (data/figure/report)."""
            exp_groups = step.get("exports", {})
            if not exp_groups:
                return
            has_any = False
            for grp_key in ("input", "data", "figure", "report"):
                if grp_key not in exp_groups:
                    continue
                grp_label, grp_color = _GRP_LABEL[grp_key]
                avail = []
                for e in exp_groups[grp_key]:
                    ep = BASE / e["path"]
                    if e.get("fmt") == "zip_glob":
                        if ep.is_dir():
                            matched = list(ep.glob(e.get("glob", "*")))
                            if matched:
                                avail.append((e, ep, matched))
                    elif ep.exists():
                        avail.append((e, ep, None))
                if not avail:
                    continue
                if not has_any:
                    st.markdown("<div class='step-card-exports'>", unsafe_allow_html=True)
                    has_any = True
                st.markdown(
                    f"<p class='exp-grp-label' style='color:{grp_color};margin:6px 0 4px 0;"
                    f"font-size:0.72rem;font-weight:700;letter-spacing:.06em;"
                    f"text-transform:uppercase;'>&#9632; {grp_label}</p>",
                    unsafe_allow_html=True,
                )
                cols_per_row = 3
                for i in range(0, len(avail), cols_per_row):
                    row = avail[i:i + cols_per_row]
                    dl_cols = st.columns(cols_per_row)
                    for col_idx, (col, (e, ep, matched)) in enumerate(zip(dl_cols, row)):
                        with col:
                            fmt = e.get("fmt", "csv")
                            dl_key = f"dl_{step['id']}_{grp_key}_{i + col_idx}"
                            if fmt == "zip_glob":
                                zip_name = e.get("zip_name", "export.zip")
                                zip_bytes = _make_zip(matched)
                                zip_mb = len(zip_bytes) / 1e6
                                st.download_button(
                                    label=f"ZIP  {e['label']} ({zip_mb:.1f} MB)",
                                    data=zip_bytes,
                                    file_name=zip_name,
                                    mime="application/zip",
                                    key=dl_key,
                                    use_container_width=True,
                                )
                            else:
                                file_mb = ep.stat().st_size / 1e6
                                mime = _FMT_MIME.get(fmt, "application/octet-stream")
                                fmt_icon = _FMT_ICON.get(fmt, fmt.upper())
                                with open(ep, "rb") as fh:
                                    file_bytes_dl = fh.read()
                                st.download_button(
                                    label=f"{fmt_icon}  {e['label']} ({file_mb:.1f} MB)",
                                    data=file_bytes_dl,
                                    file_name=ep.name,
                                    mime=mime,
                                    key=dl_key,
                                    use_container_width=True,
                                )
            if has_any:
                st.markdown("</div>", unsafe_allow_html=True)


        # ── Statistiques de progression ───────────────────────────────────────
        _n_done = sum(
            1 for s in PIPELINE_STEPS
            if s.get("outputs") and all((BASE / o).exists() for o in s["outputs"])
        )
        _n_total = len(PIPELINE_STEPS)
        _pct_done = int(_n_done / _n_total * 100) if _n_total else 0

        # ── Bloc hero Run All ─────────────────────────────────────────────────
        st.markdown(f"""
        <div class="run-hero">
          <div style='flex:1;'>
            <h3>Executer le pipeline complet</h3>
            <p>
              {_n_total} etapes &nbsp;&middot;&nbsp;
              Detection &rarr; SST &rarr; Teleconnexions &rarr; Clustering &rarr; Visualisation
            </p>
          </div>
          <div style='text-align:right;margin-left:24px;flex-shrink:0;'>
            <div style='font-size:1.6rem;font-weight:800;color:#fff;line-height:1;'>{_n_done}/{_n_total}</div>
            <div style='font-size:0.72rem;color:rgba(255,255,255,.7);margin-top:2px;'>etapes executees</div>
            <div style='background:rgba(255,255,255,.2);border-radius:99px;height:5px;margin-top:8px;width:90px;'>
              <div style='background:#fff;border-radius:99px;height:5px;width:{_pct_done}%;'></div>
            </div>
          </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        run_all = st.button(
            "Lancer le pipeline complet",
            key="btn_run_all",
            type="primary",
            use_container_width=True,
        )

        if run_all:
            overall_bar = st.progress(0, text="Demarrage...")
            all_ok = True
            results_container = st.container()
            for i, step in enumerate(PIPELINE_STEPS):
                script_path = SCRIPTS_DIR / step["script"]
                overall_bar.progress(
                    int(i / len(PIPELINE_STEPS) * 100),
                    text=f"Etape {step['num']}/{len(PIPELINE_STEPS)} : {step['label']}",
                )
                if not script_path.exists():
                    with results_container:
                        st.warning(f"Script introuvable : `{step['script']}`")
                    all_ok = False
                    continue
                with st.spinner(f"Etape {step['num']} — {step['label']}..."):
                    rc, out = run_script(script_path)
                with results_container:
                    if rc == 0:
                        st.success(f"Etape {step['num']} terminee : {step['label']}")
                    else:
                        st.error(f"Etape {step['num']} en echec : {step['label']} (code {rc})")
                        with st.expander("Voir la sortie d\'erreur"):
                            st.code(out or "(vide)", language="text")
                        all_ok = False

            overall_bar.progress(100, text="Pipeline termine")
            if all_ok:
                st.balloons()
                st.success(
                    "Pipeline complet execute avec succes ! "
                    "Rechargez les autres pages pour voir les nouveaux resultats."
                )
            else:
                st.warning(
                    "Pipeline termine avec des erreurs. "
                    "Verifiez les etapes marquees ci-dessus."
                )
            st.cache_data.clear()

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Etapes individuelles ──────────────────────────────────────────────
        _FMT_ICON = {"csv": "CSV", "png": "PNG", "txt": "TXT", "json": "JSON"}
        CAT_META  = {
            "Detection":      {"icon": "radar",        "color": BLUE},
            "Export":         {"icon": "share",        "color": EMERALD},
            "SST":            {"icon": "water",        "color": INDIGO},
            "Teleconnexions": {"icon": "hub",          "color": ROSE},
            "Clustering":     {"icon": "scatter_plot", "color": AMBER},
            "Visualisation":  {"icon": "image",        "color": EMERALD},
        }
        CAT_ORDER = ["Detection", "Export", "SST", "Teleconnexions", "Clustering", "Visualisation"]
        steps_by_cat = {}
        for s in PIPELINE_STEPS:
            steps_by_cat.setdefault(s["category"], []).append(s)

        for cat in CAT_ORDER:
            if cat not in steps_by_cat:
                continue
            cat_steps  = steps_by_cat[cat]
            cat_color  = CAT_META.get(cat, {}).get("color", MUTED)
            cat_done   = sum(1 for s in cat_steps if output_status(s)[0])
            cat_total  = len(cat_steps)

            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;margin:22px 0 10px 0;'>"
                f"  <span class='cat-label' style='color:{cat_color};border-color:{cat_color};'>"
                f"    {cat}"
                f"  </span>"
                f"  <span style='font-size:0.72rem;color:{MUTED};'>"
                f"    {cat_done}/{cat_total} execute{'s' if cat_done>1 else ''}"
                f"  </span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            for step in cat_steps:
                script_path = SCRIPTS_DIR / step["script"]
                sc_exists   = script_path.exists()
                out_ok, _   = output_status(step)
                step_color  = step["color"]
                step_num    = step["num"]
                step_label  = step["label"]
                step_desc   = step["desc"]

                # Badges d'état
                if out_ok is True:
                    status_badge = "<span class='sbadge sbadge-ok'>Sorties presentes</span>"
                elif out_ok is False:
                    status_badge = "<span class='sbadge sbadge-miss'>Non execute</span>"
                else:
                    status_badge = ""

                script_badge = (
                    f"<span class='sbadge sbadge-info'>{step['script']}</span>"
                    if sc_exists else
                    "<span class='sbadge sbadge-miss'>Script introuvable</span>"
                )

                # Exports disponibles pour le badge (groupes par type)
                _exp_groups_badge = step.get("exports", {})
                n_exp = 0
                for _grp_items in _exp_groups_badge.values():
                    for _e in _grp_items:
                        _ep = BASE / _e["path"]
                        if _e.get("fmt") == "zip_glob":
                            if _ep.is_dir() and list(_ep.glob(_e.get("glob", "*"))):
                                n_exp += 1
                        elif _ep.exists():
                            n_exp += 1

                            if _ep.is_dir() and list(_ep.glob(_e.get("glob", "*"))):
                                n_exp += 1
                        elif _ep.exists():
                            n_exp += 1


                # ── Card top (info) ───────────────────────────────────────────
                left_col, btn_col = st.columns([7, 2])
                with left_col:
                    st.markdown(
                        f"<div class='step-card-top'>"
                        f"  <div class='step-num' style='background:{step_color};'>{step_num}</div>"
                        f"  <div class='step-info'>"
                        f"    <p class='step-label'>{step_label}</p>"
                        f"    <p class='step-desc'>{step_desc}</p>"
                        f"    <div class='step-badges'>"
                        f"      {script_badge} {status_badge}"
                        f"      {'<span class=\"sbadge sbadge-ok\">' + str(n_exp) + ' fichier' + ('s' if n_exp>1 else '') + ' exportable' + ('s' if n_exp>1 else '') + '</span>' if n_exp else ''}"
                        f"    </div>"
                        f"  </div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with btn_col:
                    btn_key = f"run_{step['id']}"
                    st.markdown("<div style='padding:14px 0 0 0;'>", unsafe_allow_html=True)
                    if sc_exists:
                        clicked = st.button("Executer", key=btn_key,
                                            use_container_width=True, type="secondary")
                    else:
                        clicked = False
                        st.button("Introuvable", key=btn_key,
                                  disabled=True, use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                # Execution et résultat en pleine largeur
                if clicked:
                    with st.spinner(f"Execution de l'etape {step_num}..."):
                        rc, out = run_script(script_path)
                    if rc == 0:
                        st.markdown(
                            f"<div style='background:#f0fdf4;border:1px solid #86efac;"
                            f"border-radius:8px;padding:10px 16px;margin:8px 0;"
                            f"display:flex;align-items:center;gap:10px;'>"
                            f"  <span style='font-size:1.1rem;'>OK</span>"
                            f"  <span style='color:#166534;font-weight:600;'>"
                            f"    Etape {step_num} executee avec succes</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<div style='background:#fef2f2;border:1px solid #fca5a5;"
                            f"border-radius:8px;padding:10px 16px;margin:8px 0;"
                            f"display:flex;align-items:center;gap:10px;'>"
                            f"  <span style='font-size:1.1rem;'>Erreur</span>"
                            f"  <span style='color:#991b1b;font-weight:600;'>"
                            f"    Etape {step_num} — Echec (code {rc})</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    if out:
                        toggle_key = f"show_out_{step['id']}"
                        if toggle_key not in st.session_state:
                            st.session_state[toggle_key] = True
                        label_btn = "Masquer la sortie" if st.session_state[toggle_key] else "Voir la sortie"
                        if st.button(label_btn, key=f"btn_out_{step['id']}"):
                            st.session_state[toggle_key] = not st.session_state[toggle_key]
                            st.rerun()
                        if st.session_state[toggle_key]:
                            st.code(out, language="text")
                    st.cache_data.clear()

                # -- Section exports groupee par type --
                render_exports(step)

    # =========================================================================
    # ONGLET 3 — DONNEES SST
    # =========================================================================
    if _show_sst:
        import json as _json
        import signal

        SST_DIR     = BASE / "data" / "raw" / "SST"
        STATUS_FILE = SST_DIR / ".download_status.json"
        CANCEL_FILE = SST_DIR / ".cancel"
        DL_SCRIPT   = BASE / "scripts" / "download_sst_noaa.py"
        SST_DIR.mkdir(parents=True, exist_ok=True)

        # ── Helpers ──────────────────────────────────────────────────────────
        def _read_status():
            try:
                return _json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return None

        def _sst_files():
            return sorted(f for f in SST_DIR.glob("*.nc") if not f.name.startswith("."))

        def _dl_running():
            pid = st.session_state.get("sst_dl_pid")
            if not pid:
                return False
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

        # ── Etat courant ─────────────────────────────────────────────────────
        sst_files_present = _sst_files()
        total_size_gb     = sum(f.stat().st_size for f in sst_files_present) / 1e9
        dl_status         = _read_status()
        is_running        = _dl_running()

        # ── Header statut ─────────────────────────────────────────────────────
        n_present = len(sst_files_present)
        n_total   = 41
        pct_ready = int(n_present / n_total * 100)
        bar_color = "#22C55E" if n_present == n_total else INDIGO

        st.markdown(f"""
        <div style="background:{CARD};border:1px solid {BORDER};border-radius:14px;
                    padding:20px 24px;margin-bottom:20px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <span style="font-size:0.85rem;font-weight:700;color:{TEXT};">
              Fichiers SST (OISST v2 &nbsp;1983-2023)
            </span>
            <span style="font-size:0.82rem;color:{MUTED};">
              {n_present} / {n_total} &nbsp;|&nbsp; {total_size_gb:.1f} Go
            </span>
          </div>
          <div style="background:{BORDER};border-radius:99px;height:8px;overflow:hidden;">
            <div style="width:{pct_ready}%;height:100%;border-radius:99px;
                        background:{bar_color};transition:width .4s;"></div>
          </div>
          <p style="font-size:0.72rem;color:{MUTED};margin:6px 0 0 0;">
            {pct_ready}% des fichiers presents
          </p>
        </div>
        """, unsafe_allow_html=True)

        # ── Section telechargement NOAA ───────────────────────────────────────
        st.markdown(
            "<p class='pip-section-title'>Telecharger depuis NOAA</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="font-size:0.78rem;color:{MUTED};margin:0 0 14px 0;">'
            "Le serveur telecharge directement les donnees OISST v2 depuis <b>NOAA PSL</b>. "
            "Le telechargement reprend automatiquement en cas de coupure. "
            "Seuls les fichiers manquants sont telecharges.</p>",
            unsafe_allow_html=True,
        )

        # Affichage de la progression si telechargement en cours ou termine
        if dl_status:
            state       = dl_status.get("state", "")
            done        = dl_status.get("done", 0)
            to_dl       = dl_status.get("to_download", 0)
            cur_year    = dl_status.get("current_year")
            cur_pct     = dl_status.get("current_pct", 0)
            errors_dl   = dl_status.get("errors", [])
            already     = dl_status.get("already", 0)

            overall_pct = int(done / to_dl * 100) if to_dl > 0 else 100

            if state == "running":
                status_html = f'<span style="color:#F59E0B;font-weight:700;">En cours</span>'
            elif state == "done":
                status_html = f'<span style="color:#22C55E;font-weight:700;">Termine</span>'
            elif state == "cancelled":
                status_html = f'<span style="color:#EF4444;font-weight:700;">Annule</span>'
            else:
                status_html = f'<span style="color:{MUTED};">{state}</span>'

            st.markdown(f"""
            <div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;
                        padding:16px 20px;margin-bottom:14px;">
              <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:0.82rem;font-weight:600;color:{TEXT};">
                  Statut : {status_html}
                </span>
                <span style="font-size:0.78rem;color:{MUTED};">
                  {done}/{to_dl} telecharges &nbsp;({already} deja presents)
                </span>
              </div>
              <div style="background:{BORDER};border-radius:99px;height:7px;overflow:hidden;margin-bottom:8px;">
                <div style="width:{overall_pct}%;height:100%;border-radius:99px;
                            background:linear-gradient(90deg,{INDIGO},{BLUE});"></div>
              </div>
              {"<p style='font-size:0.75rem;color:" + MUTED + ";margin:0;'>Fichier en cours : <b>" + str(cur_year) + "</b> — " + str(cur_pct) + "%</p>" if cur_year else ""}
              {"<p style='font-size:0.72rem;color:#EF4444;margin:6px 0 0 0;'>" + str(len(errors_dl)) + " erreur(s) : " + ", ".join(str(e["year"]) for e in errors_dl) + "</p>" if errors_dl else ""}
              <p style="font-size:0.68rem;color:{MUTED};margin:6px 0 0 0;">
                Derniere mise a jour : {dl_status.get("updated_at", "")}
              </p>
            </div>
            """, unsafe_allow_html=True)

        # Boutons selon l'etat
        if is_running:
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button("Actualiser la progression", key="btn_sst_refresh"):
                    st.rerun()
            with col_b:
                if st.button("Annuler le telechargement", key="btn_sst_cancel"):
                    CANCEL_FILE.touch()
                    st.warning("Signal d'annulation envoye. Le telechargement s'arretera apres le fichier en cours.")
                    st.rerun()
        else:
            col_yr1, col_yr2, col_dl = st.columns([1, 1, 2])
            with col_yr1:
                yr_start = st.number_input("Annee debut", min_value=1981, max_value=2023,
                                           value=1983, step=1, key="sst_yr_start")
            with col_yr2:
                yr_end = st.number_input("Annee fin", min_value=1983, max_value=2023,
                                         value=2023, step=1, key="sst_yr_end")
            with col_dl:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Telecharger depuis NOAA", type="primary",
                             use_container_width=True, key="btn_sst_dl"):
                    CANCEL_FILE.unlink(missing_ok=True)
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"
                    env["PYTHONUTF8"] = "1"
                    proc = subprocess.Popen(
                        [sys.executable, str(DL_SCRIPT),
                         f"--year-start={int(yr_start)}",
                         f"--year-end={int(yr_end)}"],
                        cwd=str(BASE), env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    st.session_state["sst_dl_pid"] = proc.pid
                    st.info(f"Telechargement lance (PID {proc.pid}). Actualisez pour suivre la progression.")
                    time.sleep(1)
                    st.rerun()

        # Auto-refresh pendant le telechargement
        if is_running:
            time.sleep(3)
            st.rerun()

        # ── Liste des fichiers presents ───────────────────────────────────────
        st.markdown(
            "<p class='pip-section-title' style='margin-top:24px;'>Fichiers presents</p>",
            unsafe_allow_html=True,
        )

        if sst_files_present:
            rows_html = ""
            for f in sst_files_present:
                size_mb = f.stat().st_size / 1e6
                is_tmp  = f.suffix == ".tmp"
                color   = MUTED if is_tmp else TEXT
                rows_html += (
                    f"<div style='display:flex;justify-content:space-between;"
                    f"padding:5px 12px;border-bottom:1px solid {BORDER};font-size:0.78rem;'>"
                    f"<span style='color:{color};'>{f.name}</span>"
                    f"<span style='color:{MUTED};'>{size_mb:.0f} Mo</span>"
                    f"</div>"
                )
            st.markdown(
                f"<div style='border:1px solid {BORDER};border-radius:10px;"
                f"overflow:hidden;max-height:320px;overflow-y:auto;'>{rows_html}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Aucun fichier SST present.")

        # ── Suppression ───────────────────────────────────────────────────────
        if sst_files_present and not is_running:
            st.markdown(
                "<p class='pip-section-title' style='margin-top:24px;'>"
                "Liberer l\'espace disque</p>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<p style="font-size:0.78rem;color:{MUTED};margin:0 0 12px 0;">'
                f"Supprimez les {n_present} fichiers SST ({total_size_gb:.1f} Go) "
                "une fois le clustering termine.</p>",
                unsafe_allow_html=True,
            )
            if "confirm_delete_sst" not in st.session_state:
                st.session_state["confirm_delete_sst"] = False

            if not st.session_state["confirm_delete_sst"]:
                if st.button("Supprimer les fichiers SST", key="btn_del_sst_ask"):
                    st.session_state["confirm_delete_sst"] = True
                    st.rerun()
            else:
                st.warning(
                    f"Supprimer {n_present} fichier(s) ({total_size_gb:.1f} Go) ? "
                    "Cette action est irreversible."
                )
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Oui, supprimer", type="primary", key="btn_del_sst_confirm"):
                        deleted, errs = 0, []
                        for f in sst_files_present:
                            try:
                                f.unlink()
                                deleted += 1
                            except Exception as ex:
                                errs.append(f"{f.name}: {ex}")
                        STATUS_FILE.unlink(missing_ok=True)
                        st.session_state["confirm_delete_sst"] = False
                        if errs:
                            st.error(f"{deleted} supprime(s), {len(errs)} erreur(s).")
                        else:
                            st.success(f"{deleted} fichier(s) supprimes. Espace libere.")
                        st.rerun()
                with col_no:
                    if st.button("Annuler", key="btn_del_sst_cancel"):
                        st.session_state["confirm_delete_sst"] = False
                        st.rerun()
