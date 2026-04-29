import sys
import os
import subprocess
import time
import io as _io
import json as _json
import zipfile as _zf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import dashboard_utils as du
from dashboard_utils import INDIGO, BLUE, EMERALD, AMBER, ROSE, BASE

SCRIPTS_DIR = BASE / "scripts"

_FMT_MIME = {
    "csv":  "text/csv",
    "png":  "image/png",
    "txt":  "text/plain",
    "json": "application/json",
    "zip":  "application/zip",
}
_FMT_ICON = {"csv": "CSV", "png": "PNG", "txt": "TXT", "json": "JSON"}
_GRP_LABEL = {
    "input":  ("Donnees d'entree K-Means", "#8B5CF6"),
    "data":   ("Donnees de sortie",        "#0EA5E9"),
    "figure": ("Figures",                  "#10B981"),
    "report": ("Rapports",                 "#F59E0B"),
}

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
        "outputs": ["outputs/visualizations/Distribution/02_distribution_annuelle_phases.png"],
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
        "outputs": ["outputs/clustering/Phase_1_debut/Phase_1_debut_cluster_characteristics.csv"],
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
                {"path": "outputs/visualizations/clustering/sst_patterns",
                 "label": "Toutes les cartes SST (ZIP)",
                 "fmt": "zip_glob", "glob": "*.png",
                 "zip_name": "cartes_sst_publication.zip"},
            ],
        },
    },
]


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    dark_mode = kw.get("dark_mode", False)

    # ── CSS pipeline ──────────────────────────────────────────────────────
    st.markdown(f"""
    <style>
    .pip-section {{
        background:{CARD};border:1px solid {BORDER};
        border-radius:16px;padding:24px 28px;margin-bottom:16px;
    }}
    .pip-section-title {{
        font-size:0.7rem;font-weight:700;color:{MUTED};
        text-transform:uppercase;letter-spacing:1.2px;
        margin:0 0 16px 0;display:flex;align-items:center;gap:8px;
    }}
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
    .step-card {{
        background:{CARD};border:1px solid {BORDER};
        border-radius:14px;margin-bottom:10px;overflow:hidden;
    }}
    .step-card-top {{
        display:flex;align-items:flex-start;gap:14px;
        padding:16px 20px;
    }}
    .step-card-top:hover {{ background:{"rgba(255,255,255,0.05)" if dark_mode else "#FAFBFF"}; }}
    .step-num {{
        width:34px;height:34px;border-radius:50%;flex-shrink:0;
        display:flex;align-items:center;justify-content:center;
        font-size:0.78rem;font-weight:800;color:#fff;margin-top:1px;
    }}
    .step-info {{ flex:1;min-width:0; }}
    .step-label {{ font-size:0.86rem;font-weight:700;color:{TEXT};margin:0 0 3px 0; }}
    .step-desc  {{ font-size:0.75rem;color:{MUTED};margin:0 0 8px 0;line-height:1.5; }}
    .step-badges {{ display:flex;gap:5px;flex-wrap:wrap; }}
    .sbadge {{
        font-size:0.63rem;font-weight:700;padding:3px 8px;border-radius:20px;
        white-space:nowrap;letter-spacing:.5px;text-transform:uppercase;
    }}
    .sbadge-ok   {{ background:rgba(16,185,129,0.15);color:#059669; }}
    .sbadge-miss {{ background:rgba(239,68,68,0.15);color:#DC2626; }}
    .sbadge-info {{ background:rgba(124,58,237,0.15);color:#7C3AED; }}
    .sbadge-warn {{ background:rgba(245,158,11,0.15);color:#D97706; }}
    .step-card-exports {{
        border-top:1px solid {BORDER};background:{BG};
        padding:10px 20px 12px 68px;
    }}
    .exp-label {{
        font-size:0.65rem;font-weight:700;color:{MUTED};
        text-transform:uppercase;letter-spacing:.8px;margin:0 0 8px 0;
    }}
    .pip-progress-track {{
        background:{BORDER};border-radius:99px;height:6px;
        overflow:hidden;margin:8px 0 4px 0;
    }}
    .pip-progress-fill {{
        height:100%;border-radius:99px;
        background:linear-gradient(90deg,{INDIGO},{BLUE});
        transition:width .4s ease;
    }}
    .run-hero {{
        background:linear-gradient(135deg,{INDIGO} 0%,{BLUE} 100%);
        border-radius:16px;padding:24px 28px;margin-bottom:4px;
    }}
    .run-hero h3 {{ color:#fff;font-size:1.1rem;font-weight:800;margin:0 0 4px 0; }}
    .run-hero p  {{ color:rgba(255,255,255,.75);font-size:0.8rem;margin:0; }}
    .cat-label {{
        font-size:0.68rem;font-weight:800;letter-spacing:1.4px;
        text-transform:uppercase;padding:0 0 8px 0;
        border-bottom:2px solid currentColor;margin:20px 0 10px 0;
        display:inline-block;
    }}
    .sz-ok   {{color:#059669;background:rgba(16,185,129,0.15);padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    .sz-warn {{color:#D97706;background:rgba(245,158,11,0.15);padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    .sz-big  {{color:#DC2626;background:rgba(239,68,68,0.15);padding:4px 10px;border-radius:20px;font-size:0.71rem;font-weight:700;display:inline-block;}}
    </style>
    """, unsafe_allow_html=True)

    # ── Header ────────────────────────────────────────────────────────────
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

    # ── Navigation onglets ────────────────────────────────────────────────
    if "pip_tab" not in st.session_state:
        st.session_state.pip_tab = "Pipeline d'analyse"

    TAB_ICONS = {
        "Donnees CHIRPS":    "&#9729;",
        "Pipeline d'analyse":"&#9654;",
        "Donnees SST":       "&#127754;",
    }
    TAB_NAMES = ["Donnees CHIRPS", "Pipeline d'analyse", "Donnees SST"]
    _cur_tab  = st.session_state.pip_tab

    st.markdown(f"""
    <style>
    .pip-tab-bar {{
        display:flex;gap:0;background:{CARD};border:1.5px solid {BORDER};
        border-radius:14px;padding:5px;margin-bottom:24px;
        box-shadow:0 1px 4px rgba(0,0,0,0.06);
    }}
    .pip-tab-item {{
        flex:1;border-radius:10px;padding:11px 8px;text-align:center;
        cursor:pointer;transition:all .18s ease;border:none;
        background:transparent;color:{MUTED};text-decoration:none;
    }}
    .pip-tab-item.active {{
        background:linear-gradient(135deg,{INDIGO} 0%,{BLUE} 100%);
        color:#fff;box-shadow:0 3px 10px {INDIGO}55;
    }}
    .pip-tab-item:hover:not(.active) {{ background:{INDIGO}10;color:{INDIGO}; }}
    .pip-tab-icon {{ font-size:1.15rem;display:block;margin-bottom:3px; }}
    .pip-tab-label {{ font-size:0.8rem;font-weight:700;letter-spacing:.2px;display:block; }}
    </style>
    """, unsafe_allow_html=True)

    nav_c1, nav_c2, nav_c3 = st.columns(3)
    for col, name in zip([nav_c1, nav_c2, nav_c3], TAB_NAMES):
        is_active = _cur_tab == name
        with col:
            if st.button(
                f"{TAB_ICONS[name]}  {name}",
                key=f"pip_nav_{name}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.pip_tab = name
                _cur_tab = name
                st.rerun()
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

        st.markdown("<p class='pip-section-title'>Zone geographique</p>", unsafe_allow_html=True)

        preset_cols = st.columns(len(PRESETS))
        for i, (pname, pvals) in enumerate(PRESETS.items()):
            with preset_cols[i]:
                is_active_p = st.session_state.chirps_preset == pname
                if st.button(
                    f"{pvals['flag']}  {pname}",
                    key=f"preset_{pname}",
                    use_container_width=True,
                    type="primary" if is_active_p else "secondary",
                    help=pvals["desc"],
                ):
                    st.session_state.chirps_preset = pname
                    for _k, _fk in [("bb_lat_min","lat_min"),("bb_lat_max","lat_max"),
                                     ("bb_lon_min","lon_min"),("bb_lon_max","lon_max")]:
                        st.session_state[_k] = float(pvals[_fk])
                    st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

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
            f"</div></div>",
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p class='pip-section-title'>Periode et fichier de sortie</p>",
                    unsafe_allow_html=True)

        pr_c1, pr_c2, pr_c3 = st.columns([3, 3, 4])
        with pr_c1:
            yr_range = st.slider("Periode", min_value=1981, max_value=2025,
                                  value=(1981, 2023), key="dl_yr_range")
            dl_year_start, dl_year_end = yr_range
            n_years_dl  = max(0, dl_year_end - dl_year_start + 1)
            est_size_mb = n_years_dl * 120
            sz_cls = "sz-ok" if est_size_mb < 500 else ("sz-warn" if est_size_mb < 2000 else "sz-big")
            est_gb = est_size_mb / 1024
            st.markdown(
                f"<div style='margin-top:4px;display:flex;gap:8px;align-items:center;'>"
                f"<span style='font-weight:700;color:{TEXT};'>{dl_year_start} &ndash; {dl_year_end}</span>"
                f"<span class='{sz_cls}'>{n_years_dl} ans &bull; ~{est_gb:.1f} GB</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with pr_c2:
            default_out_name = f"chirps_WA_{dl_year_start}_{dl_year_end}_dayly.mat"
            dl_out_name = st.text_input("Nom du fichier .mat", value=default_out_name,
                                         key="dl_out_name")
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

        CHIRPS_STATUS_FILE = BASE / "data" / "raw" / ".download_chirps_status.json"
        CHIRPS_CANCEL_FILE = BASE / "data" / "raw" / ".cancel_chirps"
        CHIRPS_DL_SCRIPT   = BASE / "scripts" / "download_chirps.py"

        def _read_chirps_status():
            try:
                return _json.loads(CHIRPS_STATUS_FILE.read_text(encoding="utf-8"))
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

        chirps_status     = _read_chirps_status()
        chirps_is_running = _chirps_running()

        if chirps_status:
            ch_state  = chirps_status.get("state", "")
            ch_done   = chirps_status.get("done", 0)
            ch_total  = chirps_status.get("total", 0)
            ch_year   = chirps_status.get("current_year")
            ch_pct    = chirps_status.get("current_pct", 0)
            ch_phase  = chirps_status.get("phase", "")
            ch_errors = chirps_status.get("errors", [])
            ch_output = chirps_status.get("output", "")
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
            time.sleep(3)
            st.rerun()
        else:
            btn_c1, btn_c2 = st.columns([2, 5])
            with btn_c1:
                launch_download = st.button(
                    "Telecharger les donnees CHIRPS", key="btn_chirps_dl",
                    type="primary", use_container_width=True,
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
                    st.error("L'annee de fin doit etre >= a l'annee de debut.")
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
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    st.session_state["chirps_dl_pid"] = proc.pid
                    st.info(f"Telechargement lance (PID {proc.pid}).")
                    time.sleep(1)
                    st.rerun()

    # =========================================================================
    # ONGLET 2 — PIPELINE D'ANALYSE
    # =========================================================================
    if _show_pipeline:

        def _make_zip(paths):
            buf = _io.BytesIO()
            with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as zf:
                for p in paths:
                    zf.write(p, p.name)
            buf.seek(0)
            return buf.read()

        def run_script(script_path):
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True, text=True,
                cwd=str(BASE), encoding="utf-8", errors="replace", env=env,
            )
            combined = result.stdout + ("\n" + result.stderr if result.stderr.strip() else "")
            return result.returncode, combined.strip()

        def output_status(step):
            outs = step.get("outputs", [])
            if not outs:
                return None, "N/A"
            all_ok = all((BASE / o).exists() for o in outs)
            return all_ok, "Sorties presentes" if all_ok else "Non execute"

        def render_exports(step):
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
                            fmt    = e.get("fmt", "csv")
                            dl_key = f"dl_{step['id']}_{grp_key}_{i + col_idx}"
                            if fmt == "zip_glob":
                                zip_name  = e.get("zip_name", "export.zip")
                                zip_bytes = _make_zip(matched)
                                zip_mb    = len(zip_bytes) / 1e6
                                st.download_button(
                                    label=f"ZIP  {e['label']} ({zip_mb:.1f} MB)",
                                    data=zip_bytes, file_name=zip_name,
                                    mime="application/zip", key=dl_key,
                                    use_container_width=True,
                                )
                            else:
                                file_mb = ep.stat().st_size / 1e6
                                mime    = _FMT_MIME.get(fmt, "application/octet-stream")
                                fmt_icon = _FMT_ICON.get(fmt, fmt.upper())
                                with open(ep, "rb") as fh:
                                    file_bytes_dl = fh.read()
                                st.download_button(
                                    label=f"{fmt_icon}  {e['label']} ({file_mb:.1f} MB)",
                                    data=file_bytes_dl, file_name=ep.name,
                                    mime=mime, key=dl_key, use_container_width=True,
                                )
            if has_any:
                st.markdown("</div>", unsafe_allow_html=True)

        _n_done  = sum(
            1 for s in PIPELINE_STEPS
            if s.get("outputs") and all((BASE / o).exists() for o in s["outputs"])
        )
        _n_total = len(PIPELINE_STEPS)
        _pct_done = int(_n_done / _n_total * 100) if _n_total else 0

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
        """, unsafe_allow_html=True)

        run_all = st.button("Lancer le pipeline complet", key="btn_run_all",
                             type="primary", use_container_width=True)

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
                        with st.expander("Voir la sortie d'erreur"):
                            st.code(out or "(vide)", language="text")
                        all_ok = False
            overall_bar.progress(100, text="Pipeline termine")
            if all_ok:
                st.balloons()
                st.success("Pipeline complet execute avec succes ! Rechargez les autres pages pour voir les nouveaux resultats.")
            else:
                st.warning("Pipeline termine avec des erreurs. Verifiez les etapes marquees ci-dessus.")
            st.cache_data.clear()

        st.markdown("<br>", unsafe_allow_html=True)

        CAT_META  = {
            "Detection":      {"color": BLUE},
            "Export":         {"color": EMERALD},
            "SST":            {"color": INDIGO},
            "Teleconnexions": {"color": ROSE},
            "Clustering":     {"color": AMBER},
            "Visualisation":  {"color": EMERALD},
        }
        CAT_ORDER = ["Detection", "Export", "SST", "Teleconnexions", "Clustering", "Visualisation"]
        steps_by_cat = {}
        for s in PIPELINE_STEPS:
            steps_by_cat.setdefault(s["category"], []).append(s)

        for cat in CAT_ORDER:
            if cat not in steps_by_cat:
                continue
            cat_steps = steps_by_cat[cat]
            cat_color = CAT_META.get(cat, {}).get("color", MUTED)
            cat_done  = sum(1 for s in cat_steps if output_status(s)[0])
            cat_total = len(cat_steps)

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

                if clicked:
                    with st.spinner(f"Execution de l'etape {step_num}..."):
                        rc, out = run_script(script_path)
                    if rc == 0:
                        st.markdown(
                            f"<div style='background:#f0fdf4;border:1px solid #86efac;"
                            f"border-radius:8px;padding:10px 16px;margin:8px 0;'>"
                            f"  <span style='color:#166534;font-weight:600;'>"
                            f"    Etape {step_num} executee avec succes</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f"<div style='background:#fef2f2;border:1px solid #fca5a5;"
                            f"border-radius:8px;padding:10px 16px;margin:8px 0;'>"
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

                render_exports(step)

    # =========================================================================
    # ONGLET 3 — DONNEES SST
    # =========================================================================
    if _show_sst:
        SST_DIR     = BASE / "data" / "raw" / "SST"
        STATUS_FILE = SST_DIR / ".download_status.json"
        CANCEL_FILE = SST_DIR / ".cancel"
        DL_SCRIPT   = BASE / "scripts" / "download_sst_noaa.py"
        SST_DIR.mkdir(parents=True, exist_ok=True)

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

        sst_files_present = _sst_files()
        total_size_gb     = sum(f.stat().st_size for f in sst_files_present) / 1e9
        dl_status         = _read_status()
        is_running        = _dl_running()

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

        st.markdown("<p class='pip-section-title'>Telecharger depuis NOAA</p>",
                    unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-size:0.78rem;color:{MUTED};margin:0 0 14px 0;">'
            "Le serveur telecharge directement les donnees OISST v2 depuis <b>NOAA PSL</b>. "
            "Le telechargement reprend automatiquement en cas de coupure. "
            "Seuls les fichiers manquants sont telecharges.</p>",
            unsafe_allow_html=True,
        )

        if dl_status:
            state     = dl_status.get("state", "")
            done      = dl_status.get("done", 0)
            to_dl     = dl_status.get("to_download", 0)
            cur_year  = dl_status.get("current_year")
            cur_pct   = dl_status.get("current_pct", 0)
            errors_dl = dl_status.get("errors", [])
            already   = dl_status.get("already", 0)
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
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    st.session_state["sst_dl_pid"] = proc.pid
                    st.info(f"Telechargement lance (PID {proc.pid}). Actualisez pour suivre la progression.")
                    time.sleep(1)
                    st.rerun()

        if is_running:
            time.sleep(3)
            st.rerun()

        st.markdown("<p class='pip-section-title' style='margin-top:24px;'>Fichiers presents</p>",
                    unsafe_allow_html=True)
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

        if sst_files_present and not is_running:
            st.markdown(
                "<p class='pip-section-title' style='margin-top:24px;'>Liberer l'espace disque</p>",
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
