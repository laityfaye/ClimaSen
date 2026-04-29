#!/usr/bin/env python3
"""Shared utilities for the SenRain Dashboard — loaders, helpers, palette."""
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
PHASE_L = {"Phase_1_debut": "Debut Mai-Jun", "Phase_2_pleine": "Pleine Jul-Aou", "Phase_3_fin": "Fin Sep-Oct"}


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
        return xs, ys

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


def plotly_base(fig, h=300, muted="#64748B", border="#E2E8F0", text="#0F172A"):
    fig.update_layout(
        height=h,
        autosize=True,
        margin=dict(l=2, r=2, t=10, b=2),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,sans-serif", size=11, color=muted),
        xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=11, color=muted)),
        yaxis=dict(showgrid=True, gridcolor=border, zeroline=False, tickfont=dict(size=11, color=muted)),
        hoverlabel=dict(bgcolor=text, font_color="white", font_size=12, bordercolor=text),
        legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center",
                    bgcolor="rgba(0,0,0,0)", borderwidth=0, font=dict(size=11)),
    )
    return fig
