"""
Script 14 : Cartes SST des centroides de cluster - visualisation publication.

Pour chaque phase (debut / pleine / fin), genere une figure avec K lignes
(une par cluster) et 2 colonnes :
  - Gauche  : domaine tropical global (-180 a 180, 35S a 35N)
  - Droite  : zoom Atlantique + Afrique de l'Ouest (-60 a 30E, 20S a 40N)

Ameliorations par rapport au script 12 :
  - Boites des indices SST de reference (Nino3.4, ATL3, TNA, TSA, IOD-W/E, IOBM)
    avec valeur moyenne du centroide annotee.
  - Hachurage des anomalies |z| > 0.5 sigma (signal robuste).
  - Panneau par cluster independamment lisible (pas de vignettes miniatures).
  - Colorbar commune horizontale en bas de figure.
  - Style publiable : fond ocean clair, terres grises, cotes, grille lat/lon.

Prerequis : scripts 11 et 12 deja executes (outputs/clustering/).
"""

import sys
import math
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import matplotlib.ticker as mticker
from pathlib import Path
warnings.filterwarnings('ignore')

import cartopy.crs as ccrs
import cartopy.feature as cfeature

sys.path.append(str(Path(__file__).parent.parent))
from src.config.settings import OUTPUT_DIR, VISUALIZATION_DIR

# ============================================================================
# CONFIGURATION
# ============================================================================

CLUSTERING_DIR = OUTPUT_DIR / "clustering"
VIZ_OUT        = VISUALIZATION_DIR / "clustering" / "sst_patterns"
VIZ_OUT.mkdir(parents=True, exist_ok=True)

# Masque terrestre OISST (True = terre, NaN a appliquer avant tracé)
_LAND_MASK_PATH = OUTPUT_DIR.parent / "data" / "processed" / "oisst_land_mask.npy"
LAND_MASK = np.load(_LAND_MASK_PATH) if _LAND_MASK_PATH.exists() else None

PHASES = {
    'Phase_1_debut':  'Debut de saison (Mai-Juin)',
    'Phase_2_pleine': 'Pleine saison (Juillet-Aout)',
    'Phase_3_fin':    'Fin de saison (Septembre-Octobre)',
    'All_phases':     'Toutes phases confondues (1317 evenements)',
}

# Grille OISST v2 : 480 lat x 1440 lon  (60N -> 60S, -180 -> 180)
NLAT, NLON = 480, 1440
LATS = np.linspace(60, -60, NLAT)
LONS = np.linspace(-180, 180, NLON, endpoint=False)

# Couleurs des clusters (jusqu'a 9 pour couvrir All_phases)
CLUSTER_COLORS = [
    '#2196F3', '#FF5722', '#4CAF50', '#9C27B0', '#FF9800', '#00BCD4',
    '#E91E63', '#795548', '#607D8B'
]

# ============================================================================
# BOITES DES INDICES SST
# Format : (lon_min, lon_max, lat_min, lat_max, label, edgecolor)
# Coordonnees standard des indices utilises dans le projet.
# ============================================================================
INDEX_BOXES = {
    'Nino3.4': dict(lon0=-170, lon1=-120, lat0=-5,  lat1=5,   color='#e91e63'),
    'Nino3':   dict(lon0=-150, lon1=-90,  lat0=-5,  lat1=5,   color='#9c27b0'),
    'ATL3':    dict(lon0=-20,  lon1=0,    lat0=-3,  lat1=3,   color='#ff5722'),
    'TNA':     dict(lon0=-55,  lon1=-15,  lat0=5,   lat1=23,  color='#ff9800'),
    'TSA':     dict(lon0=-30,  lon1=10,   lat0=-20, lat1=0,   color='#795548'),
    'IOD-W':   dict(lon0=50,   lon1=70,   lat0=-10, lat1=10,  color='#009688'),
    'IOD-E':   dict(lon0=90,   lon1=110,  lat0=-10, lat1=0,   color='#00bcd4'),
    'IOBM':    dict(lon0=40,   lon1=100,  lat0=-20, lat1=20,  color='#4caf50'),
}

# Domaines de visualisation
DOMAIN_GLOBAL = (-180, 180, -35, 35)   # lon_min, lon_max, lat_min, lat_max
DOMAIN_ATL    = (-60,   30, -20, 40)


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def load_centroids(phase_key: str) -> np.ndarray:
    f = CLUSTERING_DIR / phase_key / f"{phase_key}_centroids_sst.npy"
    return np.load(f).astype(np.float32)


def load_events(phase_key: str) -> pd.DataFrame:
    f = CLUSTERING_DIR / phase_key / f"{phase_key}_events_with_clusters.csv"
    return pd.read_csv(f)


def box_mean(field2d: np.ndarray, lon0, lon1, lat0, lat1) -> float:
    """Moyenne du champ 2D (NLAT x NLON) sur la boite lat/lon specifiee."""
    lat_idx = np.where((LATS >= lat0) & (LATS <= lat1))[0]
    lon_idx = np.where((LONS >= lon0) & (LONS <= lon1))[0]
    if len(lat_idx) == 0 or len(lon_idx) == 0:
        return np.nan
    sub = field2d[np.ix_(lat_idx, lon_idx)]
    return float(np.nanmean(sub))


def draw_index_box(ax, lon0, lon1, lat0, lat1, label, color,
                   val=None, fontsize=7):
    """
    Dessine la boite d'un indice SST sur ax (ccrs.PlateCarree).
    Annote avec le label et la valeur moyenne du centroide si fournie.
    """
    rect = mpatches.FancyBboxPatch(
        (lon0, lat0), lon1 - lon0, lat1 - lat0,
        boxstyle='square,pad=0',
        linewidth=1.4, edgecolor=color, facecolor='none',
        transform=ccrs.PlateCarree(), zorder=9
    )
    ax.add_patch(rect)

    # Annotation au centre superieur de la boite
    cx = (lon0 + lon1) / 2
    cy = lat1

    if val is not None:
        sign = '+' if val >= 0 else ''
        ann_text = f"{label}\n{sign}{val:.2f} degC"
    else:
        ann_text = label

    ax.text(cx, cy + 1.5, ann_text,
            ha='center', va='bottom',
            fontsize=fontsize, color=color, fontweight='bold',
            transform=ccrs.PlateCarree(), zorder=10,
            bbox=dict(facecolor='white', alpha=0.6, edgecolor='none',
                      boxstyle='round,pad=0.1'))


def add_land_overlay(ax):
    """Ajoute LAND + cotes + frontieres APRES les SST pour garantir le masquage."""
    ax.add_feature(cfeature.LAND, facecolor='#d5d5d5', zorder=7)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5, edgecolor='#333333', zorder=8)
    ax.add_feature(
        cfeature.NaturalEarthFeature('cultural', 'admin_0_countries', '110m',
                                     edgecolor='#666666', facecolor='none'),
        linewidth=0.2, zorder=8
    )


def setup_ax(ax, extent, gridlines=True):
    """Configure extent, ocean de fond et grille (sans terre — ajoutee apres SST)."""
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN, facecolor='#e8f4f8', zorder=0)
    if gridlines:
        gl = ax.gridlines(draw_labels=True, dms=False,
                          x_inline=False, y_inline=False,
                          linewidth=0.25, color='gray', alpha=0.4,
                          xlocs=mticker.MultipleLocator(30),
                          ylocs=mticker.MultipleLocator(15),
                          zorder=4)
        gl.top_labels   = False
        gl.right_labels = False
        gl.xlabel_style = {'size': 6}
        gl.ylabel_style = {'size': 6}
        return gl
    return None


# ============================================================================
# FIGURE PRINCIPALE : K lignes x 2 colonnes
# ============================================================================

def plot_phase(phase_key: str, phase_label: str):
    """
    Genere une figure multi-panneaux pour une phase :
      - 1 ligne par cluster
      - Colonne gauche : tropiques globaux (-180/180, 35S/35N)
      - Colonne droite : zoom Atlantique + Afrique Ouest (-60/30E, 20S/40N)
    """
    print(f"\n  Phase : {phase_label}")
    C = load_centroids(phase_key)
    K = C.shape[0]
    df = load_events(phase_key)
    n_per_cluster = df['cluster'].value_counts().sort_index().to_dict()

    grids = [C[k].reshape(NLAT, NLON) for k in range(K)]
    # Masquer les points terrestres (NaN apres reconstruction PCA)
    if LAND_MASK is not None:
        grids = [np.where(LAND_MASK, np.nan, g) for g in grids]

    # Colorbar commune : percentile 97 valeurs absolues (nanpercentile : ignore NaN terre)
    all_abs = np.concatenate([np.abs(g).ravel() for g in grids])
    vmax = float(np.nanpercentile(all_abs, 97))
    vmax = max(vmax, 0.15)
    levels = np.linspace(-vmax, vmax, 41)

    # Mise en page
    proj = ccrs.PlateCarree()
    nrows = K
    ncols = 2
    h_per_row = 3.2   # hauteur en pouces par ligne
    fig = plt.figure(figsize=(20, h_per_row * nrows + 1.5))

    # Grille personnalisee : col 0 plus large que col 1
    from matplotlib.gridspec import GridSpec
    gs = GridSpec(nrows, ncols, figure=fig,
                  width_ratios=[3, 1.6],
                  hspace=0.08, wspace=0.04,
                  left=0.04, right=0.96,
                  top=0.94, bottom=0.10)

    axes_global = []
    axes_atl    = []

    for k in range(K):
        ax_g = fig.add_subplot(gs[k, 0], projection=proj)
        ax_a = fig.add_subplot(gs[k, 1], projection=proj)
        axes_global.append(ax_g)
        axes_atl.append(ax_a)

    im_ref = None  # reference pour la colorbar

    for k in range(K):
        grid = grids[k]
        n_ev = n_per_cluster.get(k, 0)
        color_k = CLUSTER_COLORS[k % len(CLUSTER_COLORS)]

        for col_idx, (ax, extent) in enumerate(
                zip([axes_global[k], axes_atl[k]],
                    [DOMAIN_GLOBAL, DOMAIN_ATL])):

            gl = setup_ax(ax, extent, gridlines=True)
            if col_idx > 0 and gl:
                gl.left_labels = False

            # --- Champ SST rempli ---
            im = ax.contourf(
                LONS, LATS, grid,
                levels=levels,
                cmap='RdBu_r', extend='both',
                transform=proj, zorder=1
            )
            if im_ref is None:
                im_ref = im

            # --- Contours de mise en evidence (±0.5 et ±1.0 degC) ---
            ax.contour(LONS, LATS, grid,
                       levels=[-1.0, -0.5],
                       colors=['#1565c0', '#90caf9'],
                       linewidths=[0.9, 0.5],
                       linestyles=['-', '--'],
                       transform=proj, zorder=5)
            ax.contour(LONS, LATS, grid,
                       levels=[0.5, 1.0],
                       colors=['#ef9a9a', '#b71c1c'],
                       linewidths=[0.5, 0.9],
                       linestyles=['--', '-'],
                       transform=proj, zorder=5)

            # --- Hachurage : anomalie robuste |anomalie| > 0.5 degC ---
            hatch_mask = np.abs(grid) > 0.5
            ax.contourf(LONS, LATS, hatch_mask.astype(float),
                        levels=[0.5, 1.5],
                        colors='none', hatches=['..'],
                        transform=proj, zorder=6)

            # --- Masque continental apres les SST/hachures ---
            add_land_overlay(ax)

            # --- Boites des indices SST (seulement si dans le domaine) ---
            lon_min_d, lon_max_d, lat_min_d, lat_max_d = extent
            for idx_name, box in INDEX_BOXES.items():
                lo0, lo1 = box['lon0'], box['lon1']
                la0, la1 = box['lat0'], box['lat1']
                # Afficher la boite si elle a au moins 30% de surface dans le domaine
                lo0_clip = max(lo0, lon_min_d)
                lo1_clip = min(lo1, lon_max_d)
                la0_clip = max(la0, lat_min_d)
                la1_clip = min(la1, lat_max_d)
                overlap_lon = max(0, lo1_clip - lo0_clip) / (lo1 - lo0)
                overlap_lat = max(0, la1_clip - la0_clip) / (la1 - la0)
                if overlap_lon * overlap_lat < 0.3:
                    continue
                val = box_mean(grid, lo0, lo1, la0, la1)
                draw_index_box(ax, lo0, lo1, la0, la1,
                               idx_name, box['color'],
                               val=val, fontsize=6.5)

            # --- Marqueur Senegal ---
            ax.plot(-14.5, 14.5, marker='*', color='gold', markersize=10,
                    transform=proj, zorder=11,
                    markeredgecolor='black', markeredgewidth=0.7)

        # --- Titre de ligne (cluster) ---
        axes_global[k].set_title(
            f"Cluster {k}  (n={n_ev} evenements)",
            loc='left', fontsize=10, fontweight='bold',
            color=color_k, pad=3
        )
        axes_atl[k].set_title(
            "Zoom Atl. / AO",
            loc='right', fontsize=8, color='#555555', pad=3
        )

    # -------------------------------------------------------------------------
    # Colorbar commune en bas
    # -------------------------------------------------------------------------
    cbar_ax = fig.add_axes([0.15, 0.04, 0.70, 0.018])
    cb = fig.colorbar(im_ref, cax=cbar_ax, orientation='horizontal',
                      extend='both')
    cb.set_label('Anomalie SST (degC, retroprojection PCA)', fontsize=10)
    cb.ax.tick_params(labelsize=8)

    # -------------------------------------------------------------------------
    # Legende globale
    # -------------------------------------------------------------------------
    legend_elems = [
        Line2D([0], [0], marker='*', color='gold', markersize=8,
               markeredgecolor='black', linestyle='None', label='Senegal'),
        Line2D([0], [0], color='#1565c0', linewidth=1.0, label='-1.0 degC'),
        Line2D([0], [0], color='#90caf9', linewidth=0.6, linestyle='--',
               label='-0.5 degC'),
        Line2D([0], [0], color='#ef9a9a', linewidth=0.6, linestyle='--',
               label='+0.5 degC'),
        Line2D([0], [0], color='#b71c1c', linewidth=1.0, label='+1.0 degC'),
        mpatches.Patch(facecolor='none', edgecolor='gray',
                       hatch='..', label='|anomalie| > 0.5 degC'),
    ]
    fig.legend(handles=legend_elems, loc='lower right',
               fontsize=7.5, framealpha=0.9, ncol=2,
               bbox_to_anchor=(0.96, 0.06))

    # -------------------------------------------------------------------------
    # Titre general
    # -------------------------------------------------------------------------
    fig.suptitle(
        f"Patterns SST moyens des clusters K-Means — {phase_label}\n"
        f"Anomalies SST (degC, retroprojection PCA). "
        f"Boites : indices de teleconnexion. "
        f"Hachurage : |anomalie| > 0.5 degC.",
        fontsize=11, fontweight='bold', y=0.98
    )

    outfile = VIZ_OUT / f"{phase_key}_sst_patterns_clusters.png"
    fig.savefig(outfile, dpi=180, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f"    -> {outfile.name}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 65)
    print("SCRIPT 14 - PATTERNS SST PAR CLUSTER (cartes publication)")
    print("=" * 65)
    print(f"Sortie : {VIZ_OUT}")

    for phase_key, phase_label in PHASES.items():
        plot_phase(phase_key, phase_label)

    print("\n" + "=" * 65)
    print("OK Toutes les cartes SST ont ete generees.")
    print(f"   Dossier : {VIZ_OUT}")
    print("=" * 65)
