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

# ─── Logo (assets/branding, genere par generer_logo.py) ──────────────────────
_MARQUE = Path(__file__).resolve().parent.parent / "assets" / "branding"


def _logo_uri(nom):
    """Fichier du logo en URI data: (ni serveur de fichiers statiques ni
    police a charger : le texte des SVG est deja en traces)."""
    import base64
    try:
        donnees = (_MARQUE / nom).read_bytes()
    except OSError:
        return ""
    return "data:image/svg+xml;base64," + base64.b64encode(donnees).decode("ascii")


# ─── Config ──────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ClimatSen · Précipitations extrêmes au Sénégal",
    page_icon=str(_MARQUE / "favicon-180.png") if (_MARQUE / "favicon-180.png").exists() else "🌧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Emplacement de Jarvis ───────────────────────────────────────────────────
# PREMIER element de la page, donc a une position stable d'une execution a
# l'autre: Streamlit conserve alors l'iframe au lieu de la recharger quand on
# change de page. Rempli en fin de script (voir JARVIS plus bas).
try:
    _jarvis_slot = st.container(key="jarvis_slot")
except TypeError:  # Streamlit sans parametre key
    _jarvis_slot = st.container()

# ─── Langue de la page ───────────────────────────────────────────────────────
# Streamlit declare <html lang="en"> : Chrome propose alors de "traduire" la
# page et traduit aussi les noms des icones Material (rainy -> pluvieux,
# home -> maison), qui s'affichent en texte. On declare la page en francais et
# on marque chaque icone translate="no". Un <script> dans st.markdown n'est
# pas execute : il faut un composant (iframe de meme origine) qui agit sur la
# page parente. Place ici, en deuxieme position, pour rester stable entre les
# executions (pas de rechargement a chaque changement de page).
import streamlit.components.v1 as _components
st.markdown("<style>.st-key-langue_fr{display:none !important}</style>",
            unsafe_allow_html=True)
with st.container(key="langue_fr"):
    _components.html("""<script>
(function () {
  var d;
  try { d = window.parent.document; } catch (e) { return; }
  if (!d) return;
  // Un observateur laisse par une iframe precedente meurt avec elle : on le
  // remplace au lieu de s'en remettre a un drapeau.
  if (d.__langueFr) { try { d.__langueFr.disconnect(); } catch (e) {} }
  d.documentElement.lang = "fr";
  var ICONES = '.material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"]';
  function marque(racine) {
    if (!racine || !racine.querySelectorAll) return;
    racine.querySelectorAll(ICONES).forEach(function (el) {
      if (el.getAttribute("translate") !== "no") {
        el.setAttribute("translate", "no");
        el.classList.add("notranslate");
      }
    });
  }
  marque(d);
  d.__langueFr = new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      var n = muts[i].addedNodes;
      for (var j = 0; j < n.length; j++) {
        if (n[j].nodeType === 1) {
          if (n[j].matches && n[j].matches(ICONES)) marque(n[j].parentNode);
          else marque(n[j]);
        }
      }
    }
    if (d.documentElement.lang !== "fr") d.documentElement.lang = "fr";
  });
  d.__langueFr.observe(d.body, { childList: true, subtree: true });
})();
</script>""", height=0)

# ─── Anti-FOUC + Splash (injecte fond ET ecran de chargement immediatement) ───
# S'execute des la premiere connexion WebSocket, avant tout autre rendu Python.
# Utilise sessionStorage pour n'afficher le splash qu'au premier chargement de l'onglet.
st.markdown("""
<script>
(function () {
  try {
    var dm  = new URLSearchParams(window.location.search).get('dm') === '1';
    var BG     = dm ? '#0F172A' : '#F1F5F9';
    var TEXT   = dm ? '#F1F5F9' : '#0F172A';
    var MUTED  = dm ? '#94A3B8' : '#64748B';
    var BORDER = dm ? '#334155' : '#E2E8F0';

    /* 1. Fond immediat (evite flash blanc / flash clair->sombre) */
    var bg = document.createElement('style');
    bg.id  = 'fouc-bg';
    bg.textContent =
      'html,body,[data-testid="stApp"],' +
      '[data-testid="stAppViewContainer"],' +
      '[data-testid="stAppViewContainer"]>.main,' +
      '[data-testid="stMainBlockContainer"],' +
      '.block-container{background:' + BG + '!important;color:' + TEXT + '!important}';
    (document.head || document.documentElement).appendChild(bg);

    /* 2. Splash — seulement si pas encore montre dans cet onglet */
    if (!sessionStorage.getItem('spl-shown')) {
      sessionStorage.setItem('spl-shown', '1');

      var css = document.createElement('style');
      css.textContent = [
        '#pg-fouc-splash{position:fixed;inset:0;z-index:999999;background:' + BG + ';',
        'display:flex;align-items:center;justify-content:center;',
        'font-family:Inter,sans-serif;pointer-events:none;',
        'animation:spl-out 0.45s ease-in 1.5s forwards}',
        '.spl-inner{display:flex;flex-direction:column;align-items:center;gap:14px;',
        'animation:spl-in 0.42s cubic-bezier(.34,1.3,.64,1) .05s both}',
        '.spl-logo{height:150px;width:auto;display:block}',
        '.spl-bwrap{width:160px;height:3px;background:' + BORDER + ';',
        'border-radius:99px;overflow:hidden;margin-top:10px;animation:spl-up .38s ease .30s both}',
        '.spl-bar{height:3px;width:0;',
        'background:' + (dm ? '#38BDF8' : '#0284C7') + ';',
        'border-radius:99px;animation:spl-grow 1.1s cubic-bezier(.4,0,.2,1) .35s forwards}',
        '.spl-hint{color:' + MUTED + ';font-size:.68rem;opacity:.72;margin-top:-2px;',
        'animation:spl-up .38s ease .38s both}',
        '@keyframes spl-in{from{opacity:0;transform:scale(.86)}to{opacity:1;transform:scale(1)}}',
        '@keyframes spl-up{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}',
        '@keyframes spl-grow{from{width:0}to{width:100%}}',
        '@keyframes spl-out{from{opacity:1}to{opacity:0}}'
      ].join('');
      (document.head || document.documentElement).appendChild(css);

      var el = document.createElement('div');
      el.id  = 'pg-fouc-splash';
      el.innerHTML =
        '<div class="spl-inner">' +
        '<img class="spl-logo" alt="ClimatSen, pluies extrêmes au Sénégal" src="' +
        (dm ? '__LOGO_NUIT__' : '__LOGO_CLAIR__') + '">' +
        '<div class="spl-bwrap"><div class="spl-bar"></div></div>' +
        '<div class="spl-hint">Chargement des données...</div>' +
        '</div>';

      var inject = function () {
        if (document.body) { document.body.appendChild(el); }
        else { document.addEventListener('DOMContentLoaded', function () { document.body.appendChild(el); }); }
      };
      inject();
    }
  } catch (e) {}
})();
</script>
""".replace("__LOGO_NUIT__", _logo_uri("logo-vertical-nuit.svg"))
   .replace("__LOGO_CLAIR__", _logo_uri("logo-vertical.svg")), unsafe_allow_html=True)

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
SIDEBAR_BG = "#13123B"

PHASE_C = {"Phase_1_debut": BLUE, "Phase_2_pleine": INDIGO, "Phase_3_fin": AMBER}
PHASE_L = {"Phase_1_debut": "Début Mai-Jun", "Phase_2_pleine": "Pleine Jul-Août", "Phase_3_fin": "Fin Sep-Oct"}

# ─── Dark mode state ─────────────────────────────────────────────────────────
# Priorite : session_state (navigation interne) > query_params (refresh/nouvel onglet)
# Mode sombre par defaut : seul ?dm=0 (bascule explicite vers le mode clair)
# force le theme clair.
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = (st.query_params.get("dm", "1") != "0")

# ─── Page transition state ────────────────────────────────────────────────────
# Page et filtres demandes par Jarvis (outil navigate_dashboard): appliques
# avant la barre laterale et les pages, qui creent leurs selecteurs.
try:
    import jarvis_widget as _jarvis_nav
    _jarvis_nav.appliquer_navigation(st)
except Exception:
    pass

# ─── Navigation : une adresse par page ───────────────────────────────────────
# Suivi de revue 28/09/2026, point S3 : la page courante etait gardee en
# session seulement (lien non partageable, Retour et actualisation inoperants).
# st.navigation donne a chaque page son URL (/evenements, /veille-pre-saison...)
# sans recharger l'application : la session (administrateur, filtres) survit.
# Le menu lateral personnalise reste ; le menu par defaut est masque.
# Cle (1er element) = celle qu'utilisent Jarvis et st.session_state["nav_page"].
_NAV = [
    ("Accueil",        "Accueil",           "home",          "accueil"),
    ("Evenements",     "Événements",        "rainy",         "evenements"),
    ("Indices SST",    "Indices SST",       "waves",         "indices-sst"),
    ("Teleconnexions", "Téléconnexions",    "hub",           "teleconnexions"),
    ("Clustering",     "Clustering",        "bubble_chart",  "clustering"),
    ("Veille",         "Veille pré-saison", "notifications", "veille-pre-saison"),
    ("Vulnerabilite",  "Vulnérabilité",     "shield",        "vulnerabilite"),
    ("Pipeline",       "Pipeline",          "settings",      "pipeline"),
    ("A propos",       "À propos",          "info",          "a-propos"),
]


def _afficher_page():
    """Rendu de la page courante (appele par st.navigation, en fin de script)."""
    _dispatch_page(page)


_ST_PAGES = {
    _k: st.Page(_afficher_page, title=_lbl, icon=f":material/{_ic}:",
                url_path=_url, default=(_k == "Accueil"))
    for _k, _lbl, _ic, _url in _NAV
}
_nav = st.navigation(list(_ST_PAGES.values()), position="hidden")
_cle_url = next((_k for _k, _p in _ST_PAGES.items()
                 if _p is _nav or _p.url_path == _nav.url_path), "Accueil")

# L'URL fait foi quand elle a change depuis l'execution precedente (lien,
# Retour, actualisation) ; sinon une page demandee en session (menu, Jarvis,
# tests) est rejointe par st.switch_page, qui met l'URL a jour.
_url_prec = st.session_state.get("_nav_url")
_voulue = st.session_state.get("nav_page")
if (_url_prec is not None and _cle_url != _url_prec) or _voulue not in _ST_PAGES:
    _voulue = _cle_url
st.session_state["nav_page"] = _voulue
st.session_state["_nav_url"] = _voulue
# Liens et changements de page transportent le theme (?dm=) : sans lui, une
# actualisation en theme clair repasserait en sombre. Le passer au lien plutot
# que de le reecrire apres coup evite une entree d'historique en double
# (Retour devait etre clique deux fois).
_DM_QP = {"dm": "1" if st.session_state.dark_mode else "0"}
if _voulue != _cle_url:
    st.switch_page(_ST_PAGES[_voulue], query_params=_DM_QP)
if "prev_page" not in st.session_state:
    st.session_state.prev_page = None
if "page_loading" not in st.session_state:
    st.session_state.page_loading = False

# ─── Sidebar mobile (off-canvas, ferme par defaut sous 768px) ────────────────
if "mobile_sidebar_open" not in st.session_state:
    st.session_state.mobile_sidebar_open = False

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
    """Charge les pixels des événements specifiques pour cartographie."""
    p = BASE / "outputs/specific_events_qgis/all_specific_events_pixels.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")

@st.cache_data
def load_events_summary():
    """Charge le resume statistique des événements specifiques."""
    p = BASE / "outputs/specific_events_qgis/events_summary_statistics.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")

@st.cache_data
def load_cluster_pixels():
    """Charge les pixels des événements representatifs par cluster."""
    p = BASE / "outputs/cluster_events_qgis/all_cluster_events_combined.csv"
    if not p.exists():
        return None
    return pd.read_csv(p, encoding="utf-8")

@st.cache_data
def load_dept_geojson():
    """Charge le GeoJSON des departements du Sénégal."""
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


with st.spinner("Chargement des données en cours..."):
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
        hoverlabel=dict(bgcolor=CARD, font_color=TEXT, font_size=12, bordercolor=BORDER),
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
/* Le reset ci-dessus ne doit pas toucher la police des icones Material. */
[data-testid="stIconMaterial"], .material-symbols-rounded {{
    font-family: "Material Symbols Rounded" !important;
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
    /* Marge basse reservee a la bulle Jarvis (revue 27/09/2026, point 09) :
       elle ne recouvre plus le bas du contenu. */
    padding-bottom: 110px !important;
}}
@media (max-width: 768px) {{
    /* Le bouton menu fixe (40 px, coin haut gauche) ne recouvre plus le titre. */
    .block-container, [data-testid="stMainBlockContainer"] {{
        padding-top: 56px !important;
    }}
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

/* Masquer la navigation auto-generee par Streamlit depuis le dossier pages/ */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"],
section[data-testid="stSidebar"] > div:first-child > div > ul {{
    display: none !important;
}}

/* ═══════════════════════════════════════════
   SIDEBAR — Redesign complet
   ═══════════════════════════════════════════ */

/* Base — sidebar toujours visible */
section[data-testid="stSidebar"] {{
    background: {SIDEBAR_BG} !important;
    min-width: 272px !important;
    max-width: 272px !important;
    width: 272px !important;
    border-right: 1px solid rgba(99,102,241,0.10) !important;
    overflow-x: hidden !important;
    transform: none !important;
    visibility: visible !important;
    display: block !important;
    margin-left: 0 !important;
    left: 0 !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
    background: {SIDEBAR_BG} !important;
    padding: 0 !important;
    overflow-x: hidden !important;
}}
section[data-testid="stSidebar"] > div > div:first-child,
section[data-testid="stSidebar"] > div > div > div:first-child,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{
    padding: 0 14px !important;
    margin-top: 0 !important;
}}
section[data-testid="stSidebar"] > div:first-child > div:first-child {{
    margin-top: -3rem !important;
}}
@media (max-width: 768px) {{
    section[data-testid="stSidebar"] {{
        min-width: 200px !important;
        max-width: 82vw !important;
    }}
}}

/* Texte par defaut */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div {{ color: #8892C8; }}

/* HR */
section[data-testid="stSidebar"] hr {{
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.07) !important;
    margin: 2px 0 !important;
}}

/* Sidebar fixe : tous les boutons collapse/expand caches */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {{
    display: none !important;
}}

/* ── Bouton hamburger (menu mobile) : cache sur desktop ── */
.st-key-mobile_menu_btn {{
    display: none !important;
}}
@media (max-width: 768px) {{
    .st-key-mobile_menu_btn {{
        display: block !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        z-index: 100000 !important;
        width: 40px !important;
        height: 40px !important;
        margin: 0 !important;
        padding: 0 !important;
        pointer-events: auto !important;
    }}
    .st-key-mobile_menu_btn button {{
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 40px !important;
        height: 40px !important;
        min-width: 40px !important;
        min-height: 40px !important;
        border-radius: 10px !important;
        background: {SIDEBAR_BG} !important;
        color: #FFFFFF !important;
        border: none !important;
        font-size: 1.1rem !important;
        line-height: 1 !important;
        padding: 0 !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.3) !important;
        opacity: 1 !important;
    }}
}}

/* ── Icone dark-mode (dans stHorizontalBlock = colonnes) ── */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
  [data-testid="stButton"] button {{
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 8px !important;
    color: #A8B4E8 !important;
    font-size: 1rem !important;
    padding: 3px 0 !important;
    min-height: 32px !important;
    width: 36px !important;
    line-height: 1 !important;
    transition: background 0.15s, color 0.15s !important;
    text-align: center !important;
    box-shadow: none !important;
}}
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
  [data-testid="stButton"] button:hover {{
    background: rgba(255,255,255,0.14) !important;
    color: #FFFFFF !important;
}}

/* ── Section label ── */
.sb-sec-label {{
    color: #F0F2F5 !important;
    font-size: 0.61rem;
    font-weight: 700;
    letter-spacing: 1.7px;
    text-transform: uppercase;
    margin: 14px 2px 5px 2px;
    display: block;
}}

/* ── Nav item ACTIF (div HTML) ── */
.nav-item-active {{
    display: flex;
    align-items: center;
    gap: 9px;
    background: rgba(99,102,241,0.14);
    border-left: 3px solid #6366F1;
    border-radius: 0 10px 10px 0;
    padding: 10px 14px 10px 11px;
    margin: 1px -14px;
    color: #FFFFFF !important;
    font-weight: 600;
    font-size: 0.875rem;
    line-height: 1.4;
    cursor: default;
    user-select: none;
    box-sizing: border-box;
}}
.nav-icon {{ font-size: 1.15rem; flex-shrink: 0; opacity: 0.9; width: 1.25rem;
             text-align: center; line-height: 1; }}
.nav-icon.material-symbols-rounded {{
    font-family: "Material Symbols Rounded" !important;
    font-weight: 400; font-style: normal; letter-spacing: normal;
    text-transform: none; white-space: nowrap; direction: ltr;
    -webkit-font-feature-settings: "liga"; font-feature-settings: "liga";
}}
/* Meme taille de texte pour les boutons du menu que pour l'element actif. */
section[data-testid="stSidebar"] [data-testid="stButton"] > button p {{
    font-size: 0.875rem !important;
    line-height: 1.4 !important;
}}
section[data-testid="stSidebar"] [data-testid="stButton"] > button [data-testid="stIconMaterial"] {{
    font-size: 1.15rem !important;
    width: 1.25rem !important;
}}

/* ── Nav boutons INACTIFS ── */
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div
  > [data-testid="stButton"] {{
    margin: 1px -14px !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div
  > [data-testid="stButton"] > button {{
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
    padding: 10px 14px !important;
    border-radius: 0 10px 10px 0 !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    width: 100% !important;
    background: transparent !important;
    border: none !important;
    color: #8892C8 !important;
    transition: background 0.15s, color 0.15s !important;
    box-shadow: none !important;
    line-height: 1.4 !important;
    margin: 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div
  > [data-testid="stButton"] > button > div {{
    justify-content: flex-start !important;
    width: 100% !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div
  > [data-testid="stButton"] > button p {{
    text-align: left !important;
    margin: 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div
  > [data-testid="stButton"] > button:hover {{
    background: rgba(255,255,255,0.05) !important;
    color: #C4CFE8 !important;
}}

/* ── Slider ── */
section[data-testid="stSidebar"] [data-testid="stSlider"] label,
section[data-testid="stSidebar"] [data-testid="stSlider"] p {{
    color: #FFFFFF !important;
    font-size: 0.61rem !important;
    font-weight: 700 !important;
    letter-spacing: 1.4px !important;
    text-transform: uppercase !important;
}}
section[data-testid="stSidebar"] [data-baseweb="slider"] [role="slider"] {{
    background: #6366F1 !important;
    border-color: #6366F1 !important;
}}

/* ── Multiselect ── */
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] label {{
    color: #FFFFFF !important;
    font-size: 0.61rem !important;
    font-weight: 700 !important;
    letter-spacing: 1.4px !important;
    text-transform: uppercase !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] > div:first-child {{
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
}}
section[data-testid="stSidebar"] [data-baseweb="tag"] {{
    background: rgba(99,102,241,0.22) !important;
    border-radius: 6px !important;
}}
section[data-testid="stSidebar"] [data-baseweb="tag"] span {{
    color: #A8B4E8 !important;
    font-size: 0.72rem !important;
}}

/* ── Profil card ── */
.sb-profile {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 11px;
    margin: 6px 0 20px 0;
}}
.sb-avatar {{
    width: 34px; height: 34px;
    border-radius: 50%;
    background: linear-gradient(135deg, #6366F1, #0EA5E9);
    display: flex; align-items: center; justify-content: center;
    font-size: 0.78rem; font-weight: 800; color: white;
    flex-shrink: 0;
}}
.sb-username {{ color: #D4DBF0 !important; font-size: 0.8rem; font-weight: 600; line-height: 1.2; }}
.sb-usersub  {{ color: #F0F2F5 !important; font-size: 0.66rem; margin-top: 3px; }}

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
    /* Carte etroite : la mini-courbe passe sous le texte au lieu de l'ecraser. */
    flex-wrap: wrap; row-gap: 8px;
    transition: box-shadow 0.2s;
}}
.kpi:hover {{
    box-shadow: 0 4px 8px rgba(0,0,0,0.07), 0 12px 30px rgba(79,70,229,0.1);
}}
.kpi-body  {{ flex: 1; min-width: 110px; }}
/* Une rangee de chiffres cles (une carte .kpi par colonne) : toutes les cartes
   prennent la hauteur de la plus haute, meme quand une etiquette passe a la ligne. */
/* Chaine flex (et non des hauteurs en %) : Streamlit insere un niveau sans hauteur
   entre stMarkdown et stMarkdownContainer, ou un height: 100% s'effondre. */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .kpi) {{ align-items: stretch !important; }}
[data-testid="stColumn"]:has(.kpi) {{ display: flex !important; flex-direction: column; }}
[data-testid="stColumn"]:has(.kpi) > [data-testid="stVerticalBlock"],
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] .kpi),
[data-testid="stMarkdown"]:has(.kpi),
[data-testid="stMarkdown"]:has(.kpi) > div,
[data-testid="stMarkdownContainer"]:has(> .kpi) {{
    flex: 1 1 auto; display: flex !important; flex-direction: column;
}}
[data-testid="stMarkdownContainer"] > .kpi {{ flex: 1 1 auto; }}
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
    padding: 3px 8px; border-radius: 12px;
    /* Un libelle long passe a la ligne au lieu de deborder de la carte
       (Teleconnexions : "p brute (Pearson/Spearman) sans correction"). */
    white-space: normal; max-width: 100%; box-sizing: border-box;
    line-height: 1.3;
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

/* Blocs sans rendu (feuilles de style, script anti-flash, contexte Jarvis
   cache, indicateur de chargement fixe) : hors du flux, sinon chacun ajoute
   l'ecart vertical de la colonne (~15 px) - 70 px vides en haut de chaque
   page. Leur contenu reste actif (une balise style s'applique toujours). */
[data-testid="stMainBlockContainer"] [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"]):has([data-testid="stMarkdownContainer"] > :is(style, script, link, [hidden], #page-loader)):not(:has([data-testid="stMarkdownContainer"] > :not(style, script, link, [hidden], #page-loader))) {{
    position: absolute !important;
}}
@media (min-width: 769px) {{
    [data-testid="stMainBlockContainer"] {{ padding-top: 18px !important; }}
}}

/* Fil d'Ariane et logo cliquables (suivi de revue 28/09/2026, S3) */
.st-key-fil_ariane {{ margin: 6px 0 -18px 0; gap: 6px !important; }}
.st-key-fil_ariane [data-testid="stPageLink"] a {{
    padding: 0 !important; min-height: 0 !important; background: transparent !important;
}}
.st-key-fil_ariane [data-testid="stPageLink"] a p,
.st-key-fil_ariane [data-testid="stPageLink"] a span {{
    font-size: 0.69rem !important; color: {MUTED} !important;
    text-decoration: underline; text-underline-offset: 2px;
}}
.st-key-fil_ariane [data-testid="stPageLink"] a:hover p {{ color: {INDIGO} !important; }}
.st-key-fil_ariane .pg-bc {{ margin: 0; }}
.st-key-cs_logo {{ position: relative; }}
.st-key-cs_logo [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {{
    position: absolute !important; inset: 0; z-index: 2; margin: 0 !important;
    width: 100% !important; max-width: none !important; height: 100% !important;
}}
.st-key-cs_logo [data-testid="stPageLink"],
.st-key-cs_logo [data-testid="stPageLink"] * {{
    width: 100% !important; max-width: none !important; height: 100% !important;
    opacity: 0; cursor: pointer;
}}
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

/* Hierarchie : un libelle de filtre ne doit pas etre plus gros qu'un titre
   de section (.pnl-ttl 0.88rem) - revue 27/09/2026, point 11. */
[data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"] p {{
    font-size: 0.76rem !important;
}}
[data-testid="stMainBlockContainer"] [data-testid="stCheckbox"] label p,
[data-testid="stMainBlockContainer"] [data-testid="stRadio"] label p {{
    font-size: 0.80rem !important;
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
/* Espace reserve en haut pour ne pas chevaucher le bouton hamburger */
@media (max-width: 768px) {{
    [data-testid="stAppViewContainer"] > .main {{
        padding-top: 56px !important;
    }}
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
    /* Mini-cartes evenements : 3 par ligne (evite les 6 cartes ecrasees) */
    [data-testid="stHorizontalBlock"]:has(.mini-ev-card) > [data-testid="stColumn"] {{
        width: 33.333% !important;
        min-width: 33.333% !important;
        flex: 0 0 33.333% !important;
    }}
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
   RESPONSIVE — Petit ecran bureau (1024px – 1440px)
   ══════════════════════════════════════════════════════════ */
@media (min-width: 1024px) and (max-width: 1440px) {{
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

    /* Ecran 13 pouces : tout le texte est en rem -> on reduit la base
       typographique pour que les cartes cessent de deborder. */
    html {{ font-size: 14.5px !important; }}

    /* Les colonnes flex doivent pouvoir retrecir sous leur contenu
       (sinon le contenu long pousse la ligne hors de l'ecran). */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        min-width: 0 !important;
    }}

    /* Textes longs : coupure autorisee plutot que debordement */
    .pnl-ttl, .pnl-sub, .rg-nm, .leg-lbl {{
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }}
    .evt-badge, .chip {{
        white-space: normal !important;
        overflow-wrap: break-word !important;
    }}

    /* Tableaux / graphiques : jamais plus larges que leur colonne */
    [data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{
        max-width: 100% !important;
    }}
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
    /* Mini-cartes evenements : badge/texte compacts + retour a la ligne autorise */
    .mini-ev-card {{
        padding: 8px 8px 7px 8px !important;
    }}
    .mini-ev-crit {{
        font-size: 0.60rem !important;
        white-space: normal !important;
        overflow-wrap: break-word !important;
        line-height: 1.25 !important;
    }}
    /* Sparklines masquees */
    .kpi-spark {{ display: none !important; }}
    .kpi {{ padding: 12px 13px !important; }}
    /* Marge basse : le bas de page defile au-dessus de la bulle Jarvis
       epinglee en bas a droite (recette 29/09/2026). */
    [data-testid="stMainBlockContainer"] {{ padding-bottom: 84px !important; }}
    /* Titres de cartes sur deux lignes plutot que tronques
       ("PAS ENCORE DE PREV...", recette 29/09/2026) */
    .kpi-lbl {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.3 !important;
        overflow-wrap: break-word !important;
    }}
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
    /* Mini-cartes evenements : 1 par ligne sur tres petit ecran */
    [data-testid="stHorizontalBlock"]:has(.mini-ev-card) > [data-testid="stColumn"] {{
        width: 100% !important;
        min-width: 100% !important;
        flex: 0 0 100% !important;
    }}
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

/* ══════════════════════════════════════════════════════════
   TELEPHONE (<640px) : organisation des pages
   Place APRES les regles ci-dessus, qu'il corrige :
   - la regle "<420px" remettait KPI et mini-cartes sur UNE colonne,
     or la plupart des telephones font 360-414 px : 4 KPI empiles
     occupaient deux ecrans ;
   - les colonnes a 50 % ignoraient l'ecart entre colonnes (gap) : la
     seconde carte passait a la ligne, d'ou une colonne unique la aussi.
   ══════════════════════════════════════════════════════════ */
@media (max-width: 640px) {{
    /* KPI et mini-cartes evenements : 2 par ligne, ecart compris.
       Streamlit pose une marge de -1rem sous chaque bloc de texte : les
       cartes KPI mordaient sur la rangee suivante, d'ou l'ecart vertical
       de 26 px (10 px visibles). */
    [data-testid="stHorizontalBlock"]:has(.kpi),
    [data-testid="stHorizontalBlock"]:has(.kpi-clu),
    [data-testid="stHorizontalBlock"]:has(.mini-ev-card) {{
        flex-wrap: wrap !important;
        gap: 10px !important;
    }}
    [data-testid="stHorizontalBlock"]:has(.kpi),
    [data-testid="stHorizontalBlock"]:has(.kpi-clu) {{ row-gap: 26px !important; }}
    [data-testid="stHorizontalBlock"]:has(.kpi) > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"]:has(.kpi-clu) > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"]:has(.mini-ev-card) > [data-testid="stColumn"] {{
        width: calc(50% - 5px) !important;
        min-width: calc(50% - 5px) !important;
        flex: 0 0 calc(50% - 5px) !important;
    }}
    .kpi {{ padding: 11px 12px !important; }}
    .kpi-val {{ font-size: 1.05rem !important; }}
    .kpi-tag {{ white-space: normal !important; line-height: 1.3 !important; }}
    .kpi-clu {{ padding: 11px 12px !important; }}
    .kpi-clu > div:first-child {{ font-size: 1.15rem !important; }}
    .kpi-clu p:nth-of-type(2) {{ font-size: 1.2rem !important; }}

    /* Rangees de filtres (3 colonnes et plus : Teleconnexions) : 2 par
       ligne au lieu de 4-5 widgets empiles sur toute la hauteur. */
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)):has([data-testid="stSelectbox"]):not(:has([data-testid="stPlotlyChart"])):not(:has(.st-key-ev_prev)) {{
        flex-wrap: wrap !important;
        gap: 4px 10px !important;
    }}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)):has([data-testid="stSelectbox"]):not(:has([data-testid="stPlotlyChart"])):not(:has(.st-key-ev_prev)) > [data-testid="stColumn"] {{
        width: calc(50% - 5px) !important;
        min-width: calc(50% - 5px) !important;
        flex: 0 0 calc(50% - 5px) !important;
    }}
    /* Phase + metrique des Teleconnexions : libelles longs, pleine largeur ;
       la 3e colonne (vide) ne prend pas de place. Classe repetee : doit
       l'emporter sur la regle generique ci-dessus (specificite 0,7,0). */
    .st-key-tc_filtres.st-key-tc_filtres.st-key-tc_filtres.st-key-tc_filtres.st-key-tc_filtres.st-key-tc_filtres [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        width: 100% !important; min-width: 100% !important; flex: 0 0 100% !important;
    }}
    .st-key-tc_filtres [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {{
        display: none !important;
    }}

    /* Navigation des evenements cartographies : selecteur sur toute la
       largeur, puis  <-  1/6  ->  sur UNE ligne (et non trois). */
    [data-testid="stHorizontalBlock"]:has(.st-key-ev_prev) {{
        flex-wrap: wrap !important;
        gap: 8px !important;
    }}
    [data-testid="stHorizontalBlock"]:has(.st-key-ev_prev) > [data-testid="stColumn"] {{
        width: calc(33.333% - 6px) !important;
        min-width: calc(33.333% - 6px) !important;
        flex: 0 0 calc(33.333% - 6px) !important;
    }}
    [data-testid="stHorizontalBlock"]:has(.st-key-ev_prev) > [data-testid="stColumn"]:first-child {{
        width: 100% !important;
        min-width: 100% !important;
        flex: 0 0 100% !important;
    }}

    /* Vide d'alignement de l'en-tete, inutile une fois les colonnes empilees */
    [data-testid="stElementContainer"]:has(.hdr-spacer) {{ display: none !important; }}

    /* Barre d'outils Plotly : au doigt elle ne sert guere et recouvrait
       titres et legendes. Le zoom au pincement reste disponible. */
    .modebar-container {{ display: none !important; }}

    /* Boutons (telechargements du Pipeline) : texte sur plusieurs lignes
       plutot que hors de l'ecran. */
    [data-testid="stDownloadButton"] button,
    [data-testid="stButton"] button {{
        white-space: normal !important;
        height: auto !important;
        min-height: 2.5rem !important;
    }}
    [data-testid="stDownloadButton"] button p,
    [data-testid="stButton"] button p {{
        white-space: normal !important;
        overflow-wrap: anywhere !important;
    }}

    /* Sous-titre des separateurs de section : il poussait la ligne a
       700 px de large. Le titre suffit sur petit ecran. */
    .sec-hdr-sub {{ display: none !important; }}

    /* Top regions : "46.7 %" se coupait en deux lignes */
    .rg-pct {{ width: auto !important; white-space: nowrap !important; }}
    .rg-nm  {{ min-width: 0 !important; overflow: hidden !important; text-overflow: ellipsis !important; }}

    /* Rien ne doit elargir la page au-dela de l'ecran */
    [data-testid="stMain"] {{ overflow-x: hidden !important; }}
}}

/* ── Filtres section Evenements ── */
/* Labels slider + multiselect en uppercase compact */
[data-testid="stMainBlockContainer"] [data-testid="stSlider"] label p,
[data-testid="stMainBlockContainer"] [data-testid="stMultiSelect"] label p {{
    font-size: 0.63rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.09em !important;
    color: {MUTED} !important;
    margin-bottom: 4px !important;
}}
/* Bouton Reset : style discret, rouge quand actif */
div[data-testid="stButton"]:has(button[data-testid*="evt_reset"]) button,
button[key="evt_reset_btn"] {{
    background: transparent !important;
    border: 1px solid {BORDER} !important;
    color: {MUTED} !important;
    border-radius: 8px !important;
    font-size: 0.74rem !important;
    font-weight: 600 !important;
    transition: background 0.15s, color 0.15s, border-color 0.15s !important;
}}
div[data-testid="stButton"]:has(button[data-testid*="evt_reset"]) button:not(:disabled):hover {{
    background: rgba(244,63,94,0.08) !important;
    border-color: {ROSE} !important;
    color: {ROSE} !important;
}}
/* Tags phases dans multiselect : taille et espacement */
[data-testid="stMainBlockContainer"] [data-baseweb="tag"] {{
    border-radius: 6px !important;
    font-size: 0.70rem !important;
}}

/* ── Expander : l'icone Material garde sa police (regle stIconMaterial plus
   haut) ; ne plus masquer le 1er span, qui porte aussi le libelle. ── */
[data-testid="stExpander"] summary {{
    display: flex !important;
    align-items: center !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    cursor: pointer !important;
    gap: 6px !important;
}}
[data-testid="stExpander"] summary p {{
    color: {TEXT} !important;
    font-size: 0.82rem !important;
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
/* Champ de saisie d'un select : fond transparent. Selon la version de
   Streamlit, il est pose en absolu par-dessus la 1re etiquette d'un
   multiselect ; un fond opaque la coupait ("ino34", recette 29/09/2026). */
[data-testid="stMainBlockContainer"] [data-baseweb="select"] input {{
    background: transparent !important;
}}

/* ── Selectbox / Multiselect (contenu principal) ── */
[data-testid="stMainBlockContainer"] [data-baseweb="select"] > div:first-child {{
    background: {CARD} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}
/* Icones chevron / fleche d'ouverture en mode sombre */
[data-testid="stMainBlockContainer"] [data-baseweb="select"] svg {{
    fill: {TEXT} !important;
    color: {TEXT} !important;
    opacity: 0.85 !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] svg {{
    fill: #C4CFE8 !important;
    color: #C4CFE8 !important;
    opacity: 0.85 !important;
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

# ─── Menu mobile (bouton hamburger + sidebar en tiroir) ───────────────────────
_menu_icon = "✕" if st.session_state.mobile_sidebar_open else "☰"
if st.button(_menu_icon, key="mobile_menu_btn", help="Menu"):
    st.session_state.mobile_sidebar_open = not st.session_state.mobile_sidebar_open
    st.rerun()

if st.session_state.mobile_sidebar_open:
    st.markdown("""
    <style>
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            height: 100vh !important;
            z-index: 99998 !important;
            box-shadow: 6px 0 28px rgba(0,0,0,0.35) !important;
        }
        [data-testid="stAppViewContainer"] > .main {
            pointer-events: none !important;
            opacity: 0.35 !important;
        }
        .st-key-mobile_menu_btn,
        .st-key-mobile_menu_btn button {
            pointer-events: auto !important;
            opacity: 1 !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
    @media (max-width: 768px) {
        section[data-testid="stSidebar"] {
            display: none !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:

    # ── Header : brand (col large) + icone dark mode (col etroite) ────────────
    _moon     = "☀" if st.session_state.dark_mode else "🌙"
    _mode_lbl = "Mode clair" if st.session_state.dark_mode else "Mode sombre"

    _hdr_c = st.columns([6, 1])
    # Logo cliquable : un st.page_link transparent recouvre le bloc (lien
    # interne, la session est conservee) - suivi de revue 28/09/2026, S3.
    with _hdr_c[0], st.container(key="cs_logo"):
        st.page_link(_ST_PAGES["Accueil"], label="Accueil ClimatSen", query_params=_DM_QP)
        # Barre laterale indigo nuit : logo court (sans signature, illisible a
        # cette taille), version "nuit".
        st.markdown(f"""
        <div style="padding:22px 0 16px 0;">
          <img src="{_logo_uri('logo-court-nuit.svg')}"
               alt="ClimatSen, pluies extrêmes au Sénégal"
               style="display:block;height:34px;width:auto;max-width:100%;">
        </div>
        """, unsafe_allow_html=True)
    with _hdr_c[1]:
        st.markdown('<div style="padding-top:20px"></div>', unsafe_allow_html=True)
        if st.button(_moon, key="toggle_dark", help=_mode_lbl, use_container_width=True):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.query_params["dm"] = "1" if st.session_state.dark_mode else "0"
            st.rerun()

    st.markdown("---")

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown('<span class="sb-sec-label">Menu</span>', unsafe_allow_html=True)

    # Icones Material (une seule famille, monochromes) et libelles accentues ;
    # _NAV est defini avec la navigation (haut du script). Revue 27/09/2026,
    # points 17-19.
    for _pg_key, _pg_label, _icon, _url in _NAV:
        if st.session_state["nav_page"] == _pg_key:
            st.markdown(
                f'<div class="nav-item-active">'
                f'<span class="nav-icon material-symbols-rounded">{_icon}</span>{_pg_label}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            if st.button(
                _pg_label,
                icon=f":material/{_icon}:",
                key=f"nav_{_pg_key}",
                use_container_width=True,
            ):
                st.session_state["nav_page"] = _pg_key
                st.session_state["_nav_url"] = _pg_key
                st.session_state.mobile_sidebar_open = False
                st.switch_page(_ST_PAGES[_pg_key], query_params=_DM_QP)

    page = st.session_state["nav_page"]

year_range = (int(df["year"].min()), int(df["year"].max()))
phases_sel = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]

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



# =============================================================================
# DISPATCH PAGE MODULES
# =============================================================================
import sys as _sys
# Dossier "vues" et non "pages" : un dossier pages/ a cote du script principal
# active l'ancien mode multipage de Streamlit, qui affichait "Page not found"
# au premier visiteur apres un redemarrage sur /indices-sst, /accueil...
# C'est le dossier PARENT (scripts/) qui doit etre dans sys.path pour
# "import vues.xxx", quel que soit le repertoire de lancement.
_scripts_dir = str(__import__('pathlib').Path(__file__).resolve().parent)
if _scripts_dir not in _sys.path:
    _sys.path.insert(0, _scripts_dir)
import vues.accueil        as _pg_accueil
import vues.evenements     as _pg_evenements
import vues.teleconnexions as _pg_teleconnexions
import vues.indices_sst    as _pg_indices_sst
import vues.clustering     as _pg_clustering
import vues.pipeline       as _pg_pipeline
import vues.veille_presaison as _pg_veille
import vues.vulnerabilite  as _pg_vulnerabilite
import vues.a_propos       as _pg_a_propos

_page_kw = dict(
    BG=BG, CARD=CARD, TEXT=TEXT, MUTED=MUTED, BORDER=BORDER,
    dff=dff, df=df, year_range=year_range, phases_sel=phases_sel,
    dark_mode=st.session_state.dark_mode,
)

_LIBELLES = {_k: _lbl for _k, _lbl, _ic, _url in _NAV}


def _dispatch_page(page):
    # Fil d'Ariane : "Accueil" est un lien interne (suivi de revue 28/09, S3).
    if page != "Accueil":
        with st.container(key="fil_ariane", horizontal=True, gap="small",
                          vertical_alignment="center"):
            st.page_link(_ST_PAGES["Accueil"], label="Accueil", query_params=_DM_QP)
            st.markdown(f'<span class="pg-bc">/&nbsp; <b>{_LIBELLES[page]}</b></span>',
                        unsafe_allow_html=True)
    if page == "Accueil":
        _pg_accueil.run(**_page_kw, liens=_ST_PAGES, query_params=_DM_QP)
    elif page == "Evenements":
        _pg_evenements.run(**_page_kw)
    elif page == "Teleconnexions":
        _pg_teleconnexions.run(**_page_kw)
    elif page == "Indices SST":
        _pg_indices_sst.run(**_page_kw)
    elif page == "Clustering":
        _pg_clustering.run(**_page_kw)
    elif page == "Pipeline":
        _pg_pipeline.run(**_page_kw)
    elif page == "Veille":
        _pg_veille.run(**_page_kw)
    elif page == "Vulnerabilite":
        _pg_vulnerabilite.run(**_page_kw)
    elif page == "A propos":
        _pg_a_propos.run(**_page_kw)


_nav.run()

# =============================================================================
# JARVIS - bulle d'assistant (Phase 1)
# =============================================================================
# Isole volontairement dans un try/except: une indisponibilite du backend Jarvis
# ne doit jamais empecher le dashboard de s'afficher.
try:
    import jarvis_widget as _jarvis
    with _jarvis_slot:
        _ok_jarvis = _jarvis.render(dark_mode=st.session_state.dark_mode)
    if not _ok_jarvis:
        # L echec est trace dans la console du serveur, jamais affiche au
        # visiteur : le dashboard doit rester intact quoi qu il arrive.
        if _jarvis.derniere_erreur:
            print("[Jarvis] widget non affiche (voir trace ci-dessus)")
except Exception as _exc_jarvis:
    import traceback as _tb_jarvis
    print("[Jarvis] erreur a l import du widget :")
    _tb_jarvis.print_exc()
