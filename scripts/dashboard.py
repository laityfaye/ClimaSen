#!/usr/bin/env python3
"""
Dashboard Pro - Precipitations Extremes Senegal
Usage: streamlit run scripts/dashboard.py
"""
import io
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    HAS_CARTOPY = True
except ImportError:
    HAS_CARTOPY = False

# ─── Config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SenRain · Dashboard",
    page_icon="🌧",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

@st.cache_data
def load_sst():
    df = pd.read_csv(
        BASE / "data/raw/climate_indices/daily_indices_all.csv",
        encoding="utf-8",
    )
    df["date"] = pd.to_datetime(df["date"])
    return df

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
    """Return (n_clusters, 480, 1440) centroid SST array + lat/lon arrays."""
    npy_file = BASE / "outputs/clustering" / phase / f"{phase}_centroids_sst.npy"
    if not npy_file.exists():
        return None, None, None
    sp = _short_path(str(npy_file))
    centroids = np.load(sp)           # (n_clust, 691200)
    n_clust   = centroids.shape[0]
    full_lats = np.linspace(-59.875, 59.875, 480)
    full_lons = np.linspace(-179.875, 179.875, 1440)
    centroids_2d = centroids.reshape(n_clust, 480, 1440)
    # downsample 4x
    centroids_ds = centroids_2d[:, ::4, ::4]
    return centroids_ds, full_lats[::4], full_lons[::4]

@st.cache_data
def load_clustering():
    phases = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]
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


df         = load_events()
tc_data    = load_telecon()
sst_raw    = load_sst()
clust_data = load_clustering()

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
        yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False, tickfont=dict(size=11, color=MUTED)),
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
/* Cacher header, decoration, menu, tous les boutons sidebar */
[data-testid="stDecoration"],
[data-testid="stToolbar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
button[kind="header"] {{
    display: none !important;
}}
#MainMenu {{ display: none !important; }}
footer {{ display: none !important; }}

/* Forcer la sidebar toujours ouverte (grand ecran) */
@media (min-width: 769px) {{
    section[data-testid="stSidebar"] {{
        transform: none !important;
        display: block !important;
        visibility: visible !important;
        left: 0 !important;
        min-width: 260px !important;
        max-width: 260px !important;
        overflow: hidden !important;
    }}
}}
/* Sidebar collapsable sur mobile */
@media (max-width: 768px) {{
    section[data-testid="stSidebar"] {{
        min-width: 200px !important;
        max-width: 80vw !important;
    }}
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {{
        display: flex !important;
    }}
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
.t-indigo {{ background:#EEF2FF; color:{INDIGO}; }}
.t-blue   {{ background:#E0F2FE; color:#0284C7; }}
.t-green  {{ background:#DCFCE7; color:#059669; }}
.t-amber  {{ background:#FEF3C7; color:#D97706; }}

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

/* ══════════════════════════════
   RESPONSIVE — typographie fluide
   ══════════════════════════════ */
.kpi-val  {{ font-size: clamp(1.1rem, 1.6vw, 1.7rem) !important; }}
.pg-ttl   {{ font-size: clamp(0.9rem, 1.4vw, 1.3rem) !important; }}
.kpi-lbl  {{ font-size: clamp(0.60rem, 0.65vw, 0.69rem) !important; }}
.pnl-ttl  {{ font-size: clamp(0.78rem, 0.9vw, 0.88rem) !important; }}
.pnl-sub  {{ font-size: clamp(0.63rem, 0.72vw, 0.71rem) !important; }}
.chip     {{ font-size: clamp(0.62rem, 0.72vw, 0.71rem) !important; }}

/* Padding principal adaptatif */
[data-testid="stAppViewContainer"] > .main {{
    padding: 0 clamp(8px, 2vw, 28px) 40px clamp(8px, 2vw, 28px) !important;
}}

/* Transition de page — fade-in du contenu principal */
@keyframes pgFadeIn {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0);   }}
}}
[data-testid="stMainBlockContainer"] > div > div {{
    animation: pgFadeIn 0.18s ease-out;
}}

/* KPI : masquer sparkline si peu de place */
@media (max-width: 900px) {{
    .kpi-spark {{ display: none !important; }}
    .kpi {{ padding: 14px 15px !important; }}
}}
/* Header en colonne sur petit ecran */
@media (max-width: 700px) {{
    .pg-hdr {{
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 8px !important;
    }}
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
/* Masque tout texte brut dans l'icone toggle (arrow_down, expand_more...) */
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

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:

    # Section label
    st.markdown(
        '<p style="color:#FFFFFF;font-size:0.62rem;font-weight:700;'
        'letter-spacing:1.3px;text-transform:uppercase;'
        'padding:0 14px;margin:0 0 6px 0;">ClimatSen</p>',
        unsafe_allow_html=True,
    )

    # Navigation
    page = st.radio(
        label="nav",
        options=["Evenements", "Teleconnexions", "Indices SST", "Clustering", "Pipeline"],
        format_func=lambda x: {
            "Evenements":     "📊   Evenements",
            "Teleconnexions": "🔗   Teleconnexions",
            "Indices SST":    "🌊   Indices SST",
            "Clustering":     "🗂   Clustering",
            "Pipeline":       "⚙️   Pipeline",
        }[x],
        label_visibility="collapsed",
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
    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown(f"""
        <div class="pg-hdr">
          <div>
            <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Evenements</b></p>
            <h1 class="pg-ttl">Evenements de Precipitation Extreme</h1>
            <p class="pg-sub">
              Detection CHIRPS &nbsp;&middot;&nbsp; Seuil &gt;2&sigma;
              &nbsp;&middot;&nbsp; Senegal {year_range[0]}&ndash;{year_range[1]}
            </p>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;padding-bottom:4px;">
            <span style="font-size:0.69rem;font-weight:500;color:{MUTED};
                         background:{CARD};border:1px solid {BORDER};
                         border-radius:7px;padding:4px 10px;">📡 CHIRPS 0.05&deg;</span>
            <span style="font-size:0.69rem;font-weight:500;color:{MUTED};
                         background:{CARD};border:1px solid {BORDER};
                         border-radius:7px;padding:4px 10px;">
              🗓 {year_range[1]-year_range[0]+1} ans</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with hc2:
        st.markdown("<div style='height:50px'></div>", unsafe_allow_html=True)
        st.download_button(
            "⬇ Exporter CSV",
            data=dff.to_csv(index=False).encode("utf-8"),
            file_name="evenements_senegal.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    if is_mobile or is_tablet:
        c1, c2 = st.columns(2, gap="small")
        c3, c4 = st.columns(2, gap="small")
    else:
        c1, c2, c3, c4 = st.columns(4, gap="small")

    _sm = is_mobile or is_tablet
    kpi_data = [
        (c1, "📊", f"background:#EEF2FF",
         "Total" if _sm else "Total Evenements",
         f"{n_total:,}", "t-indigo", "📅",
         f"{year_range[0]}-{year_range[1]}",
         sp_n, INDIGO),
        (c2, "🗺️", "background:#E0F2FE",
         "Couverture" if _sm else "Couverture Moyenne",
         f"{avg_cov:.1f}%", "t-blue", "↑",
         "Spatiale" if _sm else "Extension spatiale",
         sp_cov, BLUE),
        (c3, "⚡", "background:#FEF3C7",
         "Precip." if _sm else "Precip. Moyenne",
         f"{avg_prec:.1f} mm", "t-amber", "🌧",
         "Intensite" if _sm else "Intensite extremes",
         sp_prec, AMBER),
        (c4, "📈", "background:#DCFCE7",
         "Anomalie" if _sm else "Anomalie Moyenne",
         f"{avg_anom:.1f}\u03c3", "t-green", "↑",
         "Climatologie" if _sm else "vs climatologie",
         sp_anom, EMERALD),
    ]
    for col, icon, icon_bg, lbl, val, tag_cls, t_icon, t_txt, spark, clr in kpi_data:
        sp_html = svg_spark([x for x in spark if pd.notna(x)], color=clr)
        col.markdown(f"""
        <div class="kpi">
          <div class="kpi-body">
            <div class="kpi-icon" style="{icon_bg}">{icon}</div>
            <p class="kpi-lbl">{lbl}</p>
            <p class="kpi-val">{val}</p>
            <span class="kpi-tag {tag_cls}">{t_icon} {t_txt}</span>
          </div>
          <div class="kpi-spark">{sp_html}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

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
            '<p class="pnl-sub">Evenements par mois · toutes annees confondues</p>',
            unsafe_allow_html=True,
        )
        MNAMES = {1:"Jan",2:"Fev",3:"Mar",4:"Avr",5:"Mai",6:"Jun",
                  7:"Jul",8:"Aou",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        by_m = dff.groupby("month").size().reset_index(name="n")
        by_m["mois"] = by_m["month"].map(MNAMES)

        fig_m = go.Figure(go.Bar(
            x=by_m["mois"], y=by_m["n"],
            marker=dict(
                color=by_m["n"],
                colorscale=[[0,"#C7D2FE"],[0.5,INDIGO],[1,"#3730A3"]],
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
        plotly_base(fig_m, h=200 if is_mobile else 235)
        fig_m.update_layout(showlegend=False, bargap=0.28)
        st.plotly_chart(fig_m, use_container_width=True, config={"displayModeBar": False})

    with bc2:
       
        st.markdown(
            '<p class="pnl-ttl">Top Regions Touchees</p>'
            '<p class="pnl-sub">Classement des 8 premieres regions par frequence</p>',
            unsafe_allow_html=True,
        )
        top = (dff["centroid_region"]
               .value_counts().head(8)
               .reset_index()
               .rename(columns={"centroid_region": "region", "count": "n"}))
        max_n = top["n"].max()
        GRAD  = ["#4F46E5","#6366F1","#818CF8","#A5B4FC",
                 "#C7D2FE","#DDE3FD","#EEF2FF","#F5F3FF"]

        for i, row in top.iterrows():
            bar_w = 100 * row["n"] / max_n
            pct   = 100 * row["n"] / n_total
            st.markdown(f"""
            <div class="rg-row">
              <span class="rg-rk">#{i+1}</span>
              <span class="rg-nm">{row['region']}</span>
              <div class="rg-bg">
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
          Correlations Pearson &amp; Spearman · Correction AR1 + FDR
          &nbsp;&middot;&nbsp; Lags 0-12 mois · 11 indices SST
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Filtres inline ─────────────────────────────────────────────────────
    fa, fb, fc, fd = st.columns([2, 2, 1.5, 1.5], gap="small")
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

    r_col   = "pearson_r"   if tc_type == "Pearson" else "spearman_r"
    sig_col = "sig_pearson" if tc_type == "Pearson" else "sig_spearman"

    df_tc = tc_data.get(tc_phase, pd.DataFrame())
    if df_tc.empty:
        st.warning("Donnees non disponibles pour cette phase.")
        st.stop()

    df_m = df_tc[df_tc["metric"] == tc_metric].copy()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Heatmap + Top correlations ─────────────────────────────────────────
    hm_col, top_col = st.columns([3, 1.3], gap="medium")

    with hm_col:
        st.markdown(
            '<p class="pnl-ttl">Heatmap des correlations par indice et lag</p>'
            '<p class="pnl-sub">Couleur = coefficient r · etoile = sig. nominale (p&lt;0.05) · '
            'double etoile = sig. apres correction FDR</p>',
            unsafe_allow_html=True,
        )

        # Construire matrice : indices (y) x lags (x)
        all_indices = [idx for grp in IDX_GROUP.values() for idx in grp]
        lags_shown  = LAGS_ALL

        z_mat  = []
        text_m = []
        for idx in all_indices:
            row_z, row_t = [], []
            for lag in lags_shown:
                sub = df_m[(df_m["index"] == idx) & (df_m["lag_months"] == lag)]
                if sub.empty:
                    row_z.append(None)
                    row_t.append("")
                else:
                    r = sub[r_col].values[0]
                    s = sub[sig_col].values[0] if sig_col in sub.columns else ""
                    row_z.append(r)
                    if pd.notna(s) and str(s).strip() in ("*", "**"):
                        row_t.append(str(s).strip())
                    else:
                        row_t.append("")
            z_mat.append(row_z)
            text_m.append(row_t)

        fig_hm = go.Figure(go.Heatmap(
            z=z_mat,
            x=[f"Lag {l}m" for l in lags_shown],
            y=all_indices,
            text=text_m,
            texttemplate="%{text}",
            textfont=dict(size=13, color="white"),
            colorscale=[
                [0.0,  "#C2410C"],
                [0.25, "#FB923C"],
                [0.45, "#FEF3C7"],
                [0.5,  "#F8FAFC"],
                [0.55, "#BAE6FD"],
                [0.75, "#0EA5E9"],
                [1.0,  "#1E3A8A"],
            ],
            zmid=0,
            zmin=-0.5, zmax=0.5,
            colorbar=dict(
                title=dict(text="r", side="right"),
                thickness=12,
                len=0.9,
                tickfont=dict(size=10, color=MUTED),
                outlinewidth=0,
            ),
            hovertemplate=(
                "<b>%{y}</b> · %{x}<br>"
                "r = %{z:.3f}<extra></extra>"
            ),
        ))

        # Lignes de separation des groupes
        group_sep = [4, 6, 10]  # apres Nino4, IOBM, AMM
        for sep in group_sep:
            fig_hm.add_hline(
                y=sep - 0.5,
                line=dict(color=BORDER, width=1.5, dash="dot"),
            )

        fig_hm.update_layout(
            height=340,
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
        )
        st.plotly_chart(fig_hm, use_container_width=True, config={"displayModeBar": False})

    # ── Top correlations ───────────────────────────────────────────────────
    with top_col:
        st.markdown(
            '<p class="pnl-ttl">Top 8 correlations</p>'
            '<p class="pnl-sub">Valeurs absolues · tous lags</p>',
            unsafe_allow_html=True,
        )

        df_top = df_m.copy()
        if show_sig:
            df_top = df_top[df_top[sig_col].notna() & (df_top[sig_col] != "")]
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
                sv       = rec.get(sig_col, "")
                sig_badge = ""
                if pd.notna(sv) and str(sv).strip() in ("*", "**"):
                    sig_badge = (
                        '<span style="font-size:0.63rem;background:#FEF3C7;'
                        'color:#92400E;border-radius:4px;padding:1px 5px;'
                        f'font-weight:700;">{str(sv).strip()}</span>'
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
            '<p class="pnl-sub">Evolution du coefficient r en fonction du decalage temporel</p>',
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
            sub_idx = df_m[df_m["index"] == idx].sort_values("lag_months")
            if sub_idx.empty:
                continue
            clr = COLORS_LINE[ci % len(COLORS_LINE)]
            fig_line.add_trace(go.Scatter(
                x=sub_idx["lag_months"],
                y=sub_idx[r_col],
                mode="lines+markers",
                name=idx,
                line=dict(color=clr, width=2),
                marker=dict(size=6, color=clr, symbol="circle"),
                hovertemplate=f"<b>{idx}</b> · lag %{{x}}m : r=%{{y:.3f}}<extra></extra>",
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
            '<p class="pnl-sub">Meilleur lag par indice (|r| max)</p>',
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
            sig_v  = best.get(sig_col, "")
            rows_synth.append((idx, r_val, lag_v, sig_v))

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

        for idx, r_val, lag_v, sig_v in rows_synth:
            is_pos = r_val >= 0
            r_clr  = "#1D4ED8" if is_pos else "#B91C1C"
            sig_html = ""
            if pd.notna(sig_v) and str(sig_v).strip() in ("*", "**"):
                sig_html = (
                    f'<span style="font-size:0.7rem;color:#92400E;'
                    f'font-weight:700;">{str(sig_v).strip()}</span>'
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
          <b style="color:{TEXT};">Niveaux de significativite</b><br>
          * &nbsp;= p &lt; 0.05 (nominale)<br>
          ** = p &lt; 0.05 (FDR Benjamini-Hochberg)<br>
          n_eff = correction AR1 (Chelton 1983)
        </div>
        """, unsafe_allow_html=True)

    # ── Metriques KPI ──────────────────────────────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    df_all_m = df_m.copy()
    n_tests   = len(df_all_m)
    n_sig_nom = df_all_m[sig_col].notna().sum() if sig_col in df_all_m else 0
    n_sig_fdr = df_all_m[
        df_all_m[sig_col].isin(["**"])
    ].shape[0] if sig_col in df_all_m.columns else 0
    best_row = df_all_m.loc[df_all_m[r_col].abs().idxmax()] if not df_all_m.empty else None
    best_r   = best_row[r_col] if best_row is not None else 0

    mk1, mk2, mk3, mk4 = st.columns(4, gap="small")
    kpi_tc = [
        (mk1, "background:#EEF2FF", "Tests totaux", f"{n_tests}", "t-indigo",
         f"{len(all_indices)} indices x {len(LAGS_ALL)} lags"),
        (mk2, "background:#DCFCE7", "Sig. nominale", f"{int(n_sig_nom)}", "t-green",
         "p < 0.05 sans correction"),
        (mk3, "background:#FEF3C7", "Sig. FDR", f"{int(n_sig_fdr)}", "t-amber",
         "Apres Benjamini-Hochberg"),
        (mk4, "background:#E0F2FE", "r max |.| ", f"{abs(best_r):.3f}", "t-blue",
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
        (k1, "background:#EEF2FF", primary, f"{pv_last:+.3f}", "t-indigo",
         "Derniere valeur", svg_spark(pv.values[-60:].tolist(), color=INDIGO)),
        (k2, "background:#E0F2FE", "Moyenne", f"{pv_mean:+.3f}", "t-blue",
         f"std = {pv_std:.3f}", svg_spark(
             sst.set_index("date")[primary].resample("YS").mean().values.tolist(),
             color=BLUE)),
        (k3, "background:#DCFCE7", "Phase +", f"{pct_pos:.0f}%", "t-green",
         "Temps en phase positive", None),
        (k4, "background:#FEF3C7", "Phase -", f"{100-pct_pos:.0f}%", "t-amber",
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
                xaxis=dict(title="k (nb clusters)", gridcolor="#F1F5F9", tickmode="linear"),
                yaxis=dict(title="Inertie", gridcolor="#F1F5F9"),
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
                xaxis=dict(title="k", gridcolor="#F1F5F9", tickmode="linear"),
                yaxis=dict(title=dict(text="Silhouette", font=dict(color=EMERALD)), gridcolor="#F1F5F9"),
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
                xaxis=dict(title="Cluster", gridcolor="#F1F5F9"),
                yaxis=dict(title=sel_metric, gridcolor="#F1F5F9"),
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
                xaxis=dict(title="Couverture moyenne (%)", gridcolor="#F1F5F9"),
                yaxis=dict(title="Precip max moyenne (mm)", gridcolor="#F1F5F9"),
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
                xaxis=dict(title="Annee", gridcolor="#F1F5F9", dtick=5),
                yaxis=dict(title="Nb evenements", gridcolor="#F1F5F9"),
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
                xaxis=dict(title="Mois", gridcolor="#F1F5F9"),
                yaxis=dict(title="Nb evenements", gridcolor="#F1F5F9"),
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
          (centroide) ou pour un evenement individuel.</p>
        """, unsafe_allow_html=True)

        sst_view = st.radio(
            "Vue SST",
            ["Centroide du cluster", "Evenement individuel"],
            horizontal=True,
            key="cl_sst_view",
            label_visibility="collapsed",
        )

        # ── load centroids ───────────────────────────────────────────────────
        cent_arr, cent_lats, cent_lons = load_sst_centroid(sel_phase)

        if sst_view == "Centroide du cluster":
            # Cluster selector
            cl_ids_sorted = sorted(events["cluster"].unique())
            sel_cl = st.selectbox(
                "Cluster",
                options=cl_ids_sorted,
                format_func=lambda x: f"Cluster {x}  ({int(chars[chars['cluster']==x]['n_events'].values[0])} evt)",
                key="cl_sst_clid",
            )

            if cent_arr is not None:
                clust_idx = cl_ids_sorted.index(sel_cl)
                z = cent_arr[clust_idx] if clust_idx < cent_arr.shape[0] else cent_arr[0]
                vlim = max(abs(float(np.nanpercentile(z, 2))), abs(float(np.nanpercentile(z, 98))))
                vlim = min(vlim, 3.0)

                _rg_cent = _get_region_grid(tuple(cent_lats), tuple(cent_lons))
                fig_sst = go.Figure(go.Heatmap(
                    z=z, x=cent_lons, y=cent_lats,
                    colorscale="RdBu_r", zmin=-vlim, zmax=vlim,
                    zsmooth="best",
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
                    xaxis=dict(title="Longitude", gridcolor="#F1F5F9", dtick=30,
                               range=[-180, 180]),
                    yaxis=dict(title="Latitude", gridcolor="#F1F5F9", dtick=15,
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

        else:  # Evenement individuel
            cl_ids_sorted = sorted(events["cluster"].unique())
            sel_cl_ev = st.selectbox(
                "Filtrer par cluster",
                options=["Tous"] + [str(c) for c in cl_ids_sorted],
                key="cl_sst_ev_cl",
            )
            ev_sub = events if sel_cl_ev == "Tous" else events[events["cluster"] == int(sel_cl_ev)]
            ev_sub = ev_sub.sort_values("date").reset_index(drop=True)

            ev_options = ev_sub["date"].dt.strftime("%Y-%m-%d").tolist()
            if not ev_options:
                st.warning("Aucun evenement disponible pour ce filtre.")
            else:
                sel_ev_date = st.selectbox(
                    "Evenement (date)",
                    options=ev_options,
                    key="cl_sst_ev_date",
                )
                ev_row = ev_sub[ev_sub["date"] == pd.Timestamp(sel_ev_date)].iloc[0]
                ev_year = int(ev_row["year"])
                ev_doy  = int(ev_row["day_of_year"])
                ev_cl   = int(ev_row["cluster"])
                ev_phase= str(ev_row.get("phase", sel_phase))

                with st.spinner(f"Chargement SST {sel_ev_date}..."):
                    lats_ev, lons_ev, anom_ev = load_sst_day(ev_year, ev_doy)

                if anom_ev is not None:
                    vlim_ev = max(abs(float(np.nanpercentile(anom_ev, 2))), abs(float(np.nanpercentile(anom_ev, 98))))
                    vlim_ev = min(vlim_ev, 3.0)

                    mp_val  = ev_row.get("max_precip", float("nan"))
                    cov_val = ev_row.get("coverage_percent", float("nan"))
                    mp_str  = f"{mp_val:.1f} mm" if not np.isnan(mp_val) else "-"
                    cov_str = f"{cov_val:.1f}%" if not np.isnan(cov_val) else "-"

                    _rg_ev = _get_region_grid(tuple(lats_ev), tuple(lons_ev))
                    fig_ev = go.Figure(go.Heatmap(
                        z=anom_ev, x=lons_ev, y=lats_ev,
                        colorscale="RdBu_r", zmin=-vlim_ev, zmax=vlim_ev,
                        zsmooth="best",
                        customdata=_rg_ev,
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
                    _apply_geo_traces(fig_ev)
                    fig_ev.add_trace(go.Scatter(
                        x=[-17.4], y=[14.7], mode="markers",
                        marker=dict(symbol="star", size=14, color=AMBER,
                                    line=dict(width=1.5, color="white")),
                        name="Senegal (Dakar)",
                        hovertemplate="Dakar<br>17.4W  14.7N<extra></extra>",
                    ))
                    fig_ev.update_layout(
                        title=dict(
                            text=(
                                f"SST Anomalie  -  {sel_ev_date}"
                                f"  |  Cluster {ev_cl}"
                                f"  |  Precip max: {mp_str}"
                                f"  |  Couverture: {cov_str}"
                            ),
                            font=dict(size=12, color=TEXT), x=0, pad=dict(l=0),
                        ),
                        xaxis=dict(title="Longitude", gridcolor="#F1F5F9", dtick=30,
                                   range=[-180, 180]),
                        yaxis=dict(title="Latitude", gridcolor="#F1F5F9", dtick=15,
                                   range=[-60, 60]),
                        plot_bgcolor=CARD, paper_bgcolor=CARD,
                        font=dict(color=TEXT, size=11),
                        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
                        margin=dict(l=10, r=10, t=48, b=10),
                        height=520,
                    )
                    st.markdown(
                        f'<div style="background:{CARD};border:1px solid {BORDER};'
                        f'border-radius:14px;padding:16px 20px 8px 20px;'
                        f'margin-bottom:16px;">',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(fig_ev, use_container_width=True, key="cl_sst_ev_map",
                                    config={"toImageButtonOptions": {"scale": 3, "format": "png"}})
                    st.markdown("</div>", unsafe_allow_html=True)

                    # Comparison with centroid
                    if cent_arr is not None:
                        with st.expander("Comparer avec le centroide du cluster", expanded=False):
                            cl_ids_all = sorted(events["cluster"].unique())
                            ci = cl_ids_all.index(ev_cl) if ev_cl in cl_ids_all else 0
                            z_cent = cent_arr[ci] if ci < cent_arr.shape[0] else cent_arr[0]
                            vlim_c = max(abs(float(np.nanpercentile(z_cent, 2))), abs(float(np.nanpercentile(z_cent, 98))))
                            vlim_c = min(vlim_c, 3.0)
                            # diff map
                            diff = anom_ev - z_cent
                            vlim_d = max(abs(float(np.nanpercentile(diff, 5))), abs(float(np.nanpercentile(diff, 95))))
                            vlim_d = min(vlim_d, 2.5)

                            c1, c2 = st.columns(2)
                            _rg_cmp = _get_region_grid(
                                tuple(cent_lats), tuple(cent_lons))

                            def _small_sst_fig(z_data, rg, lats, lons,
                                               title, vlim, key, suffix):
                                f = go.Figure(go.Heatmap(
                                    z=z_data, x=lons, y=lats,
                                    colorscale="RdBu_r", zmin=-vlim, zmax=vlim,
                                    zsmooth="best",
                                    customdata=rg,
                                    colorbar=dict(
                                        len=0.7, thickness=12,
                                        title=dict(text="degC", side="right"),
                                    ),
                                    hovertemplate=(
                                        "Lon: %{x:.2f}  Lat: %{y:.2f}<br>"
                                        f"{suffix}: <b>%{{z:.3f}} degC</b><br>"
                                        "Region: %{customdata}<extra></extra>"
                                    ),
                                ))
                                _apply_geo_traces(f)
                                f.update_layout(
                                    title=dict(text=title,
                                               font=dict(size=12, color=TEXT), x=0),
                                    xaxis=dict(dtick=60, range=[-180, 180]),
                                    yaxis=dict(dtick=30, range=[-60, 60]),
                                    plot_bgcolor=CARD, paper_bgcolor=CARD,
                                    font=dict(color=TEXT, size=10),
                                    margin=dict(l=10, r=10, t=40, b=10),
                                    height=310,
                                )
                                st.plotly_chart(f, use_container_width=True, key=key)

                            with c1:
                                _small_sst_fig(
                                    z_cent, _rg_cmp, cent_lats, cent_lons,
                                    f"Centroide cluster {ev_cl}", vlim_c,
                                    key="cl_cent_cmp", suffix="Anomalie SST",
                                )
                            with c2:
                                _small_sst_fig(
                                    diff, _rg_cmp, cent_lats, cent_lons,
                                    "Difference (evt - centroide)", vlim_d,
                                    key="cl_diff_cmp", suffix="Difference",
                                )
                else:
                    st.warning(f"Fichier SST non disponible pour l'annee {ev_year}.")

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
        }

        pub_tabs = st.tabs([PHASE_LABELS_PUB[p] for p in ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]])
        for tab_pub, ph_key in zip(pub_tabs, ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]):
            with tab_pub:
                img_path = SST_PAT_DIR / f"{ph_key}_sst_patterns_clusters.png"
                if img_path.exists():
                    st.image(str(img_path), use_container_width=True)
                else:
                    st.info(
                        f"Image non disponible pour {PHASE_LABELS_PUB[ph_key]}. "
                        f"Executez le script 14 pour generer les cartes."
                    )


# =============================================================================
# PAGE PIPELINE
# =============================================================================
if page == "Pipeline":
    import subprocess
    import sys
    import tempfile
    import shutil
    import requests as _req  # noqa: F401

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
    .step-card-top:hover {{ background:#FAFBFF; }}
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
    .sbadge-ok   {{ background:#D1FAE5;color:#065F46; }}
    .sbadge-miss {{ background:#FEE2E2;color:#991B1B; }}
    .sbadge-info {{ background:#EDE9FE;color:#5B21B6; }}
    .sbadge-warn {{ background:#FEF3C7;color:#92400E; }}
    /* ─ Export pills ─ */
    .step-card-exports {{
        border-top:1px solid {BORDER};background:#FAFBFF;
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
    .sz-ok   {{color:#065F46;background:#D1FAE5;padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    .sz-warn {{color:#92400E;background:#FEF3C7;padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    .sz-big  {{color:#991B1B;background:#FEE2E2;padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
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

    # ── Onglets ───────────────────────────────────────────────────────────────
    tab_chirps, tab_pipeline = st.tabs([
        "  Donnees CHIRPS",
        "  Pipeline d\'analyse",
    ])

    # =========================================================================
    # ONGLET 1 — CHIRPS
    # =========================================================================
    with tab_chirps:

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

        # ── Bouton lancement ──────────────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
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
                f"Source : CHC UCSB &mdash; CHIRPS v2.0 Africa Daily 0.25&deg;. "
                f"Telechargement annee par annee en streaming, decoupage bbox automatique.</p>",
                unsafe_allow_html=True,
            )

        # ── Logique de telechargement ─────────────────────────────────────────
        if launch_download:
            if dl_year_end < dl_year_start:
                st.error("L\'annee de fin doit etre >= a l\'annee de debut.")
            elif bb_lat_max <= bb_lat_min or bb_lon_max <= bb_lon_min:
                st.error("Bounding box invalide (lat/lon min >= max).")
            else:
                try:
                    import xarray as _xr
                    import h5py as _h5py

                    CHIRPS_URL = (
                        "https://data.chc.ucsb.edu/products/CHIRPS-2.0/"
                        "africa_daily/netcdf/p25/chirps-v2.0.{year}.days_p25.nc"
                    )

                    out_path   = BASE / "data" / "raw" / dl_out_name
                    years      = list(range(dl_year_start, dl_year_end + 1))
                    n_years    = len(years)
                    all_precip = []
                    lats_ref   = lons_ref = None
                    log_lines  = []

                    prog_bar   = st.progress(0, text="Initialisation...")
                    status_box = st.empty()
                    year_log   = st.empty()

                    tmp_dir = Path(tempfile.mkdtemp(prefix="chirps_dl_"))
                    try:
                        for idx, year in enumerate(years):
                            pct_base = int(idx / n_years * 88)
                            url      = CHIRPS_URL.format(year=year)

                            prog_bar.progress(
                                pct_base,
                                text=f"Telechargement {year}  ({idx+1}/{n_years})"
                            )
                            status_box.info(f"Connexion au serveur CHC UCSB : annee **{year}**")

                            tmp_nc = tmp_dir / f"chirps_{year}.nc"
                            try:
                                resp = _req.get(url, stream=True, timeout=180)
                                resp.raise_for_status()
                                total_bytes = int(resp.headers.get("content-length", 0))
                                downloaded  = 0
                                with open(tmp_nc, "wb") as fh:
                                    for chunk in resp.iter_content(chunk_size=2 * 1024 * 1024):
                                        fh.write(chunk)
                                        downloaded += len(chunk)
                                        if total_bytes:
                                            sub_pct = pct_base + int(
                                                downloaded / total_bytes * (88 / n_years) * 0.75
                                            )
                                            prog_bar.progress(
                                                min(sub_pct, 87),
                                                text=(
                                                    f"{year} : {downloaded/1e6:.0f} / "
                                                    f"{total_bytes/1e6:.0f} MB "
                                                    f"({100*downloaded/total_bytes:.0f}%)"
                                                ),
                                            )
                            except Exception as e_dl:
                                log_lines.append(f"[ERREUR] {year} : {e_dl}")
                                st.warning(f"Annee {year} ignoree (erreur reseau : {e_dl})")
                                continue

                            # Decoupage bbox
                            prog_bar.progress(
                                min(pct_base + int(88 / n_years * 0.85), 87),
                                text=f"Decoupage bbox pour {year}...",
                            )
                            try:
                                ds = _xr.open_dataset(str(tmp_nc))
                                ds_clip = ds.sel(
                                    latitude=slice(bb_lat_min, bb_lat_max),
                                    longitude=slice(bb_lon_min, bb_lon_max),
                                )
                                pr_arr = ds_clip["precip"].values
                                pr_arr = np.where(pr_arr < -9000, np.nan, pr_arr)
                                if lats_ref is None:
                                    lats_ref = ds_clip["latitude"].values
                                    lons_ref = ds_clip["longitude"].values
                                all_precip.append(pr_arr)
                                ds.close()
                                log_lines.append(
                                    f"[OK] {year} : {pr_arr.shape[0]} jours, "
                                    f"grille {pr_arr.shape[1]}x{pr_arr.shape[2]}"
                                )
                                year_log.markdown(
                                    f"<p style='font-size:0.75rem;color:{EMERALD};'>"
                                    f"[OK] {year} — {pr_arr.shape[0]} jours, "
                                    f"{pr_arr.shape[1]}x{pr_arr.shape[2]} pixels</p>",
                                    unsafe_allow_html=True,
                                )
                            except Exception as e_xr:
                                log_lines.append(f"[ERREUR decoupage] {year} : {e_xr}")
                                st.warning(f"Erreur lecture NetCDF {year} : {e_xr}")

                            try:
                                tmp_nc.unlink()
                            except Exception:
                                pass

                        # Concatenation
                        if not all_precip:
                            st.error(
                                "Aucune donnee recuperee. "
                                "Verifiez la connexion reseau et la plage d\'annees."
                            )
                        else:
                            status_box.info("Concatenation de toutes les annees...")
                            prog_bar.progress(90, text="Concatenation des annees...")
                            precip_full = np.concatenate(all_precip, axis=0)
                            log_lines.append(
                                f"[CONCAT] {precip_full.shape[0]} jours total, "
                                f"grille {lats_ref.shape[0]}x{lons_ref.shape[0]}"
                            )

                            prog_bar.progress(94, text=f"Sauvegarde HDF5 : {out_path.name}...")
                            status_box.info(f"Ecriture du fichier : `{out_path.name}`")
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            with _h5py.File(str(out_path), "w") as hf:
                                hf.create_dataset(
                                    "precip",
                                    data=precip_full.astype(np.float32),
                                    compression="gzip",
                                    compression_opts=4,
                                    chunks=True,
                                )
                                hf.create_dataset("latitude",  data=lats_ref.astype(np.float64))
                                hf.create_dataset("longitude", data=lons_ref.astype(np.float64))
                                hf.attrs["source"]     = "CHIRPS v2.0 Africa Daily 0.25deg"
                                hf.attrs["year_start"] = dl_year_start
                                hf.attrs["year_end"]   = dl_year_end
                                hf.attrs["lat_min"]    = float(bb_lat_min)
                                hf.attrs["lat_max"]    = float(bb_lat_max)
                                hf.attrs["lon_min"]    = float(bb_lon_min)
                                hf.attrs["lon_max"]    = float(bb_lon_max)
                                hf.attrs["n_days"]     = int(precip_full.shape[0])
                                hf.attrs["created_by"] = "SenRain Dashboard"

                            prog_bar.progress(100, text="Termine !")
                            status_box.empty()
                            year_log.empty()

                            file_mb = out_path.stat().st_size / 1e6
                            st.success(
                                f"Fichier cree avec succes : **data/raw/{dl_out_name}**  "
                                f"({precip_full.shape[0]} jours &bull; "
                                f"{lats_ref.shape[0]}x{lons_ref.shape[0]} pixels &bull; "
                                f"{file_mb:.0f} MB)"
                            )
                            st.balloons()

                            st.info(
                                f"Prochaine etape : dans `src/config/settings.py`, "
                                f"mettez `CHIRPS_FILENAME = \"{dl_out_name}\"` "
                                f"puis relancez le pipeline."
                            )

                            with st.expander("Journal complet du telechargement"):
                                st.code("\n".join(log_lines), language="text")

                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

                except ImportError as e_imp:
                    st.error(
                        f"Dependance manquante : `{e_imp}`. "
                        f"Installez avec : `pip install xarray h5py`"
                    )

    # =========================================================================
    # ONGLET 2 — PIPELINE D'ANALYSE
    # =========================================================================
    with tab_pipeline:
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
            "data":    ("Donnees",  "#0EA5E9"),   # BLUE
            "figure":  ("Figures",  "#10B981"),   # EMERALD
            "report":  ("Rapports", "#F59E0B"),   # AMBER
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
                "desc": "Correlations mensuelles SST x precipitations — detrend, AR1, FDR",
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
                    "data": [
                        # Phase 1
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_cluster_characteristics.csv",
                         "label": "Phase 1 — Caracteristiques clusters"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_events_with_clusters.csv",
                         "label": "Phase 1 — Evenements + clusters"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_tableau_k_3_methodes.csv",
                         "label": "Phase 1 — Tableau k=3"},
                        {"path": "outputs/clustering/Phase_1_debut/Phase_1_debut_tableau_k_4_methodes.csv",
                         "label": "Phase 1 — Tableau k=4"},
                        # Phase 2
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_cluster_characteristics.csv",
                         "label": "Phase 2 — Caracteristiques clusters"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_events_with_clusters.csv",
                         "label": "Phase 2 — Evenements + clusters"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_tableau_k_3_methodes.csv",
                         "label": "Phase 2 — Tableau k=3"},
                        {"path": "outputs/clustering/Phase_2_pleine/Phase_2_pleine_tableau_k_4_methodes.csv",
                         "label": "Phase 2 — Tableau k=4"},
                        # Phase 3
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_cluster_characteristics.csv",
                         "label": "Phase 3 — Caracteristiques clusters"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_events_with_clusters.csv",
                         "label": "Phase 3 — Evenements + clusters"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_tableau_k_3_methodes.csv",
                         "label": "Phase 3 — Tableau k=3"},
                        {"path": "outputs/clustering/Phase_3_fin/Phase_3_fin_tableau_k_4_methodes.csv",
                         "label": "Phase 3 — Tableau k=4"},
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
            for grp_key in ("data", "figure", "report"):
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

