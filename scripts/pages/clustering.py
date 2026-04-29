import sys
import os
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import dashboard_utils as du
from dashboard_utils import (
    INDIGO, BLUE, EMERALD, AMBER, ROSE, PHASE_C, BASE,
    load_clustering, load_cluster_pixels, load_dept_geojson,
    load_sst_centroid, _get_region_grid, _apply_geo_traces,
)

PHASE_LABELS_CL = {
    "Phase_1_debut":  "Debut saison  (Mai-Jun)",
    "Phase_2_pleine": "Pleine saison (Jul-Aou)",
    "Phase_3_fin":    "Fin saison    (Sep-Oct)",
    "All_phases":     "Toutes phases confondues",
}


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Clustering</b></p>
        <h1 class="pg-ttl">Clustering KMeans SST</h1>
        <p class="pg-sub">Patterns SST associes aux evenements extremes · selection du k optimal</p>
      </div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Chargement des donnees de clustering..."):
        clust_data = load_clustering()

    if not clust_data:
        st.warning("Donnees de clustering non disponibles.")
        return

    # ── selectors ─────────────────────────────────────────────────────────
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

    # ── Panneau : relancer le clustering ──────────────────────────────────
    for _k in ("show_cluster_rerun", "cluster_result", "cluster_stderr"):
        if _k not in st.session_state:
            st.session_state[_k] = False if _k == "show_cluster_rerun" else None

    btn_label = (
        "Masquer le panneau" if st.session_state["show_cluster_rerun"]
        else "Relancer le clustering avec un K personnalise"
    )
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

        def _current_k(ph):
            d = clust_data.get(ph, {})
            m = d.get("metrics", {})
            return int(m.get("optimal_k", m.get("k_elbow", 6)) or 6)

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            k_p1 = st.number_input(
                "Phase 1 - Debut (Mai-Jun)", min_value=2, max_value=15,
                value=_current_k("Phase_1_debut"), step=1, key="ck_p1",
            )
        with col_k2:
            k_p2 = st.number_input(
                "Phase 2 - Pleine (Jul-Aou)", min_value=2, max_value=15,
                value=_current_k("Phase_2_pleine"), step=1, key="ck_p2",
            )
        with col_k3:
            k_p3 = st.number_input(
                "Phase 3 - Fin (Sep-Oct)", min_value=2, max_value=15,
                value=_current_k("Phase_3_fin"), step=1, key="ck_p3",
            )
        with col_k4:
            k_all = st.number_input(
                "All phases", min_value=2, max_value=20,
                value=_current_k("All_phases"), step=1, key="ck_all",
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
                "Lancer le clustering", type="primary",
                use_container_width=True, key="ck_run",
            )

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
            fast_script = BASE / "scripts" / "11b_kmeans_rerun_fast.py"
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
                        cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        env=env, cwd=str(BASE), timeout=1800,
                    )
                    if result.returncode == 0:
                        load_clustering.clear()
                        st.session_state["cluster_result"] = "success"
                    else:
                        st.session_state["cluster_result"] = "error"
                        st.session_state["cluster_stderr"] = (
                            (result.stderr or "") + "\n" + (result.stdout or "")
                        )
                except subprocess.TimeoutExpired:
                    st.session_state["cluster_result"] = "timeout"
                except Exception as exc:
                    st.session_state["cluster_result"] = "error"
                    st.session_state["cluster_stderr"] = str(exc)
            st.rerun()

    # ── KPI row ───────────────────────────────────────────────────────────
    n_ev     = len(events)
    k_opt    = metrics.get("optimal_k", metrics.get("k_elbow", "?"))
    sil_best = metrics.get("best_silhouette_score", None)
    k_sil    = metrics.get("k_silhouette", "?")
    sil_str  = f"{sil_best:.3f}" if sil_best is not None else "-"
    n_clust  = chars["cluster"].nunique()

    kpi_items = [
        ("&#128202;", "Evenements",     str(n_ev),   "cette phase"),
        ("&#127981;", "k optimal",      str(k_opt),  "methode coude"),
        ("&#128200;", "Silhouette max", sil_str,     f"k={k_sil}"),
        ("&#127987;", "Clusters",       str(n_clust), "dans ce graphe"),
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

    # ── Row 1 : elbow + silhouette curves ────────────────────────────────
    col_el, col_si = st.columns(2)
    k_range    = metrics.get("k_range", [])
    inertias   = metrics.get("inertias", [])
    silhouettes = metrics.get("silhouette_scores", [])
    db_scores  = metrics.get("davies_bouldin_scores", [])

    with col_el:
        fig_el = go.Figure()
        fig_el.add_trace(go.Scatter(
            x=k_range, y=inertias, mode="lines+markers",
            line=dict(color=INDIGO, width=2.5),
            marker=dict(size=7, color=INDIGO), name="Inertie",
        ))
        if k_opt in k_range:
            fig_el.add_vline(
                x=k_opt, line_dash="dash", line_color=ROSE, line_width=1.5,
                annotation_text=f"k={k_opt} (coude)",
                annotation_font_color=ROSE, annotation_position="top right",
            )
        fig_el.update_layout(
            title=dict(text="Courbe d'inertie (methode du coude)",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="k (nb clusters)", gridcolor=BORDER, tickmode="linear"),
            yaxis=dict(title="Inertie", gridcolor=BORDER),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=10, t=44, b=10), height=280,
        )
        st.plotly_chart(fig_el, use_container_width=True, key="cl_elbow")

    with col_si:
        fig_si = go.Figure()
        fig_si.add_trace(go.Scatter(
            x=k_range, y=silhouettes, mode="lines+markers",
            line=dict(color=EMERALD, width=2.5),
            marker=dict(size=7, color=EMERALD), name="Silhouette",
        ))
        fig_si.add_trace(go.Scatter(
            x=k_range, y=db_scores, mode="lines+markers",
            line=dict(color=AMBER, width=2, dash="dot"),
            marker=dict(size=6, color=AMBER), name="Davies-Bouldin",
            yaxis="y2",
        ))
        fig_si.update_layout(
            title=dict(text="Silhouette et Davies-Bouldin vs k",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="k", gridcolor=BORDER, tickmode="linear"),
            yaxis=dict(title=dict(text="Silhouette", font=dict(color=EMERALD)), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="Davies-Bouldin", font=dict(color=AMBER)),
                        overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", y=1.08, x=0),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=10, t=44, b=10), height=280,
        )
        st.plotly_chart(fig_si, use_container_width=True, key="cl_silhouette")

    # ── Row 2 : cluster profiles ──────────────────────────────────────────
    st.markdown(
        f'<h3 style="font-size:0.85rem;font-weight:700;color:{MUTED};text-transform:uppercase;'
        f'letter-spacing:.07em;margin:4px 0 10px 2px;">Profils des clusters</h3>',
        unsafe_allow_html=True,
    )

    chars_s   = chars.sort_values("cluster").reset_index(drop=True)
    cl_ids    = chars_s["cluster"].tolist()
    cl_colors = [INDIGO, BLUE, EMERALD, AMBER, ROSE,
                 "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#6366F1"]

    col_bar, col_scat = st.columns(2)

    with col_bar:
        metrics_bar = {
            "Nb evenements":       "n_events",
            "Precip max moy (mm)": "mean_max_precip",
            "Couverture (%)":      "mean_coverage_percent",
            "Anomalie max moy":    "mean_max_anomaly",
        }
        sel_metric = st.selectbox(
            "Metrique", options=list(metrics_bar.keys()),
            key="cl_metric_bar", label_visibility="collapsed",
        )
        col_key = metrics_bar[sel_metric]
        fig_bar = go.Figure()
        for i, (cid, row) in enumerate(zip(cl_ids, chars_s.itertuples())):
            val = getattr(row, col_key)
            fig_bar.add_trace(go.Bar(
                x=[f"C{cid}"], y=[val], name=f"Cluster {cid}",
                marker_color=cl_colors[i % len(cl_colors)], showlegend=True,
            ))
        fig_bar.update_layout(
            title=dict(text=sel_metric + " par cluster",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Cluster", gridcolor=BORDER),
            yaxis=dict(title=sel_metric, gridcolor=BORDER),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            showlegend=False, margin=dict(l=10, r=10, t=44, b=10), height=300,
        )
        st.plotly_chart(fig_bar, use_container_width=True, key="cl_bar_metric")

    with col_scat:
        fig_sc = go.Figure()
        for i, row in enumerate(chars_s.itertuples()):
            cid = row.cluster
            fig_sc.add_trace(go.Scatter(
                x=[row.mean_coverage_percent], y=[row.mean_max_precip],
                mode="markers+text",
                marker=dict(
                    size=max(12, min(50, row.n_events * 0.4)),
                    color=cl_colors[i % len(cl_colors)], opacity=0.85,
                    line=dict(width=1.5, color="white"),
                ),
                text=[f"C{cid}<br>n={row.n_events}"],
                textposition="top center", textfont=dict(size=10),
                name=f"Cluster {cid}", showlegend=True,
            ))
        fig_sc.update_layout(
            title=dict(text="Couverture vs Intensite (taille = nb evt)",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Couverture moyenne (%)", gridcolor=BORDER),
            yaxis=dict(title="Precip max moyenne (mm)", gridcolor=BORDER),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            legend=dict(orientation="h", y=-0.15, x=0),
            margin=dict(l=10, r=10, t=44, b=10), height=300,
        )
        st.plotly_chart(fig_sc, use_container_width=True, key="cl_scatter")

    # ── Row 3 : temporal distribution ─────────────────────────────────────
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
                name=f"C{cid}", marker_color=cl_colors[i % len(cl_colors)],
            ))
        fig_yr.update_layout(
            barmode="stack",
            title=dict(text="Evenements par annee et cluster",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Annee", gridcolor=BORDER, dtick=5),
            yaxis=dict(title="Nb evenements", gridcolor=BORDER),
            legend=dict(orientation="h", y=1.08, x=0),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=10, t=44, b=10), height=300,
        )
        st.plotly_chart(fig_yr, use_container_width=True, key="cl_yr")

    with col_mo:
        mo_cl = events.groupby(["month", "cluster"]).size().reset_index(name="n")
        month_names = {5:"Mai", 6:"Juin", 7:"Juil", 8:"Aout", 9:"Sep", 10:"Oct"}
        mo_cl["month_lbl"] = mo_cl["month"].map(lambda m: month_names.get(m, str(m)))
        fig_mo = go.Figure()
        for i, cid in enumerate(sorted(events["cluster"].unique())):
            sub = mo_cl[mo_cl["cluster"] == cid].sort_values("month")
            fig_mo.add_trace(go.Bar(
                x=sub["month_lbl"], y=sub["n"],
                name=f"C{cid}", marker_color=cl_colors[i % len(cl_colors)],
            ))
        fig_mo.update_layout(
            barmode="group",
            title=dict(text="Evenements par mois et cluster",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Mois", gridcolor=BORDER),
            yaxis=dict(title="Nb evenements", gridcolor=BORDER),
            legend=dict(orientation="h", y=1.08, x=0),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=10, t=44, b=10), height=300,
        )
        st.plotly_chart(fig_mo, use_container_width=True, key="cl_mo")

    # ── Row 4 : per-cluster summary cards ────────────────────────────────
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

    cl_ids_sorted = sorted(events["cluster"].unique())
    if st.session_state.get("cl_shared_last_phase") != sel_phase:
        st.session_state["cl_shared_last_phase"] = sel_phase
        st.session_state.pop("cl_shared_cluster", None)
    sel_cl_shared = st.selectbox(
        "Cluster", options=cl_ids_sorted,
        format_func=lambda x: f"Cluster {x}", key="cl_shared_cluster",
    )

    cent_arr, cent_lats, cent_lons = load_sst_centroid(sel_phase)
    sel_cl = sel_cl_shared

    if cent_arr is not None:
        clust_idx = cl_ids_sorted.index(sel_cl)
        z_full = cent_arr[clust_idx] if clust_idx < cent_arr.shape[0] else cent_arr[0]
        vlim = max(abs(float(np.nanpercentile(z_full, 2))),
                   abs(float(np.nanpercentile(z_full, 98))))
        vlim = min(vlim, 3.0)

        z       = z_full[::2, ::2]
        lats_ds = cent_lats[::2]
        lons_ds = cent_lons[::2]

        _rg_cent = _get_region_grid(tuple(lats_ds), tuple(lons_ds))
        fig_sst = go.Figure(go.Heatmap(
            z=z, x=lons_ds, y=lats_ds,
            colorscale="RdBu_r", zmin=-vlim, zmax=vlim, zsmooth=False,
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
            xaxis=dict(title="Longitude", gridcolor=BORDER, dtick=30, range=[-180, 180]),
            yaxis=dict(title="Latitude",  gridcolor=BORDER, dtick=15, range=[-60, 60]),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.85)"),
            margin=dict(l=10, r=10, t=48, b=10), height=520,
        )
        st.plotly_chart(fig_sst, use_container_width=True, key="cl_sst_cent_map",
                        config={"toImageButtonOptions": {"scale": 3, "format": "png"}})
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
        _cl_px_ph = _cl_px_all[_cl_px_all["phase"] == sel_phase].copy()

        if len(_cl_px_ph) == 0:
            st.info(
                f"Aucun pixel disponible pour {PHASE_LABELS_CL.get(sel_phase, sel_phase)}. "
                "Relancer le script 03c_filter_events_by_cluster_for_qgis.py."
            )
        else:
            _cl_carto_sel = sel_cl_shared
            _cl_nav_key = f"{sel_phase}_{_cl_carto_sel}"
            if st.session_state.get("cl_carto_last_navkey") != _cl_nav_key:
                st.session_state["cl_carto_last_navkey"] = _cl_nav_key
                st.session_state["cl_carto_nav"] = 0
                st.session_state["cl_carto_crit"] = None

            _cl_px_c = _cl_px_ph[_cl_px_ph["cluster"] == _cl_carto_sel].copy()

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
                "plus_intense":           (ROSE,   "rgba(244,63,94,0.13)"),
                "moins_intense":          (EMERALD, "rgba(16,185,129,0.13)"),
                "plus_grande_couverture": (INDIGO,  "rgba(79,70,229,0.13)"),
                "plus_petite_couverture": (BLUE,    "rgba(14,165,233,0.13)"),
            }

            if "cl_carto_nav" not in st.session_state:
                st.session_state["cl_carto_nav"] = 0
            _cl_nav = min(st.session_state["cl_carto_nav"], len(_cl_crit_avail) - 1)

            if not st.session_state.get("cl_carto_crit") and _cl_crit_avail:
                st.session_state["cl_carto_crit"] = _cl_crit_avail[_cl_nav]

            _cl_scol, _cl_pcol, _cl_ccol, _cl_ncol = st.columns([7, 1, 1.2, 1], gap="small")
            with _cl_pcol:
                if st.button("←", key="cl_carto_prev",
                             disabled=_cl_nav <= 0, use_container_width=True):
                    _new_nav = max(0, _cl_nav - 1)
                    st.session_state["cl_carto_nav"] = _new_nav
                    st.session_state["cl_carto_crit"] = _cl_crit_avail[_new_nav]
                    st.rerun()
            with _cl_scol:
                _cl_sel_crit = st.selectbox(
                    "Critere", options=_cl_crit_avail,
                    format_func=lambda c: _CRIT_FR_CL.get(c, c),
                    label_visibility="collapsed", key="cl_carto_crit",
                )
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

            # ── Mini-cards (4 criteres) ────────────────────────────────
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

            # ── Pixels du critere selectionne ──────────────────────────
            _cl_ev      = _cl_px_c[_cl_px_c["criterion"] == _cl_sel_crit].copy()
            _cl_date    = _cl_ev["event_date"].iloc[0] if len(_cl_ev) > 0 else ""
            _cl_fg0, _cl_bgcrit = _CRIT_CLR_CL.get(_cl_sel_crit, (INDIGO, "rgba(79,70,229,0.13)"))
            _cl_lbl     = _CRIT_FR_CL.get(_cl_sel_crit, _cl_sel_crit)

            _cl_dept_geo    = load_dept_geojson()
            _cl_bounds_path = BASE / "data/geographic/senegal_boundaries.geojson"
            if _cl_bounds_path.exists() and len(_cl_ev) > 0:
                import json as _json_cl
                from matplotlib.path import Path as _MplPathCl
                with open(str(_cl_bounds_path), "r", encoding="utf-8") as _bfcl:
                    _cl_bounds_geo = _json_cl.load(_bfcl)
                _cl_bp_list = []
                for _feat_cl in _cl_bounds_geo.get("features", []):
                    _geom_cl  = _feat_cl.get("geometry", {})
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

            _cl_depts = [""] * len(_cl_ev)
            if _cl_dept_geo is not None and len(_cl_ev) > 0:
                from matplotlib.path import Path as _MplPathCl2
                _cl_pts_all = np.column_stack([
                    _cl_ev["longitude"].values, _cl_ev["latitude"].values
                ])
                for _feat_d in _cl_dept_geo.get("features", []):
                    _dname   = _feat_d.get("properties", {}).get("NAME_2", "")
                    _geom_d  = _feat_d.get("geometry", {})
                    _gtype_d = _geom_d.get("type", "")
                    _coords_d = _geom_d.get("coordinates", [])
                    _polys_d  = []
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

                _cl_cd_prec = [
                    [f"{a:+.1f}", rg, ct, la, lo, dp, f"{p:.1f}"]
                    for a, rg, ct, la, lo, dp, p
                    in zip(_cl_anom, _cl_regs, _cl_cats,
                           _cl_lats, _cl_lons, _cl_depts, _cl_prec)
                ]

                _cl_p_max = float(np.percentile(_cl_prec, 99))
                _cl_p_min = max(0.0, float(np.percentile(_cl_prec, 1)))

                _cl_ctr_lat = float(_cl_ev["latitude"].mean())
                _cl_ctr_lon = float(_cl_ev["longitude"].mean())

                _CS_PREC_CL = [
                    [0.00, "#FFFFFF"], [0.04, "#FFF9C4"], [0.14, "#FFEB3B"],
                    [0.30, "#FF9800"], [0.55, "#F44336"], [0.80, "#9C27B0"],
                    [1.00, "#1A237E"],
                ]

                _cl_bmap = dict(
                    style="carto-positron",
                    center=dict(lat=_cl_ctr_lat, lon=_cl_ctr_lon),
                    zoom=5.5,
                )
                _cl_mgn = dict(l=0, r=0, t=36, b=0)

                def _cl_add_overlays(fig):
                    if _cl_dept_geo is not None:
                        _lo_b, _la_b = [], []
                        for _fbt in _cl_dept_geo.get("features", []):
                            _gbm  = _fbt.get("geometry", {})
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
                            f"{_cl_ctr_lat:.1f}N {abs(_cl_ctr_lon):.1f}W"
                            "<extra></extra>"
                        ),
                        showlegend=False,
                    ))

                _cl_map_col, _cl_info_col = st.columns([5, 4], gap="medium")

                with _cl_map_col:
                    st.markdown(
                        '<p class="pnl-ttl" style="margin-bottom:4px">'
                        '&#127783; Precipitation (mm)</p>',
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
                            marker=dict(opacity=0.87,
                                        line=dict(width=0.4, color="rgba(255,255,255,0.12)")),
                            colorbar=dict(
                                title=dict(text="mm", font=dict(size=11, color=MUTED)),
                                thickness=12, len=0.82, x=1.01,
                                tickfont=dict(size=10, color=MUTED), outlinewidth=0,
                            ),
                            hoverinfo="skip",
                        ))
                        _cl_fig1.add_trace(go.Scattermapbox(
                            lat=_cl_lats, lon=_cl_lons, mode="markers",
                            marker=dict(size=8, opacity=0, color="rgba(0,0,0,0)"),
                            customdata=_cl_cd_prec,
                            hovertemplate=(
                                "<b>%{customdata[6]} mm</b> | %{customdata[0]}sigma<br>"
                                "Departement : <b>%{customdata[5]}</b><br>"
                                "Region : %{customdata[1]}<br>"
                                "Categorie : <b>%{customdata[2]}</b>"
                                "<extra></extra>"
                            ),
                            showlegend=False,
                        ))
                        _cl_add_overlays(_cl_fig1)
                        _cl_fig1.update_layout(
                            mapbox=_cl_bmap, margin=_cl_mgn, height=430,
                            plot_bgcolor=CARD, paper_bgcolor=CARD,
                            title=dict(
                                text=(f"<b>{_cl_date}</b> · {_cl_lbl} · Cluster {_cl_carto_sel}"),
                                font=dict(size=10, color=MUTED), x=0, pad=dict(l=4),
                            ),
                        )
                        st.plotly_chart(
                            _cl_fig1, use_container_width=True, key="cl_carto_map1",
                            config={
                                "displayModeBar": True,
                                "modeBarButtonsToRemove": [
                                    "lasso2d", "select2d", "autoScale2d", "hoverClosestMapbox",
                                ],
                                "displaylogo": False,
                                "toImageButtonOptions": {
                                    "format": "png",
                                    "filename": f"cluster{_cl_carto_sel}_{_cl_sel_crit}_{_cl_date}",
                                },
                            },
                        )

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
                    _cl_top_reg = _cl_reg_stats.index[0] if len(_cl_reg_stats) else "-"
                    _cl_top_max = float(_cl_reg_stats.iloc[0]["max_p"]) if len(_cl_reg_stats) else 0
                    _cl_top_moy = float(_cl_reg_stats.iloc[0]["mean_p"]) if len(_cl_reg_stats) else 0

                    _cl_pmax_v = f"{_cl_ev['precipitation_mm'].max():.1f}"
                    _cl_pmoy_v = f"{_cl_ev['precipitation_mm'].mean():.1f}"
                    _cl_amax_v = f"{_cl_ev['anomaly_standardized'].max():.1f}"
                    _cl_amoy_v = f"{_cl_ev['anomaly_standardized'].mean():.1f}"
                    _cl_ext_n  = int((_cl_ev["anomaly_standardized"] > 2.0).sum())
                    _cl_ext_pct = _cl_ext_n / len(_cl_ev) * 100
                    _cl_ph_raw  = _cl_ev["season_phase"].iloc[0] if len(_cl_ev) > 0 else ""
                    _PHASE_FR_CL2 = {
                        "Phase_1_debut":  "Phase 1 &mdash; D&eacute;but (Mai-Juin)",
                        "Phase_2_pleine": "Phase 2 &mdash; Pleine (Juil-Ao&ucirc;t)",
                        "Phase_3_fin":    "Phase 3 &mdash; Fin (Sep-Oct)",
                    }
                    _cl_ph_lbl = _PHASE_FR_CL2.get(_cl_ph_raw, _cl_ph_raw)
                    _cl_ph_clr = PHASE_C.get(_cl_ph_raw, MUTED)

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
                        f'</div></div>'
                        f'<span style="background:{_cl_ph_clr}22;color:{_cl_ph_clr};'
                        f'font-size:0.72rem;font-weight:700;border-radius:6px;'
                        f'padding:3px 9px;display:inline-block">'
                        f'{_cl_ph_lbl}</span>'
                        f'</div>'
                    )
                    _cl_html_body = (
                        f'<div style="padding:8px 16px 16px 16px;">'
                        + _cl_mrow("Pr&#233;cip. max",     _cl_pmax_v, "mm", BLUE)
                        + _cl_mrow("Pr&#233;cip. moyenne", _cl_pmoy_v, "mm")
                        + _cl_mrow("Anomalie max",         _cl_amax_v, "&#963;", "#7C3AED")
                        + _cl_mrow("Anomalie moyenne",     _cl_amoy_v, "&#963;")
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
    # CARTES PUBLICATION QUALITE (cartopy)
    # ════════════════════════════════════════════════════════════════════
    st.markdown(f"""
    <div style="border-top:2px solid {BORDER};margin:24px 0 18px 0;"></div>
    <h2 style="font-size:1.05rem;font-weight:800;color:{TEXT};margin:0 0 6px 0;">
      Cartes SST — Qualite publication (cartopy)</h2>
    <p style="font-size:0.78rem;color:{MUTED};margin:0 0 16px 0;">
      Figures multi-panneaux generees par le script 14 : anomalies SST globales
      (tropiques) et zoom Atlantique / Afrique de l'Ouest pour chaque cluster.
      Hachurage des anomalies |z| &gt; 0.5 sigma (signal robuste).</p>
    """, unsafe_allow_html=True)

    SST_PAT_DIR = BASE / "outputs/visualizations/clustering/sst_patterns"
    PHASE_LABELS_PUB = {
        "Phase_1_debut":  "Phase 1 - Debut (Mai-Juin)",
        "Phase_2_pleine": "Phase 2 - Pleine (Juillet-Aout)",
        "Phase_3_fin":    "Phase 3 - Fin (Septembre-Octobre)",
        "All_phases":     "Toutes phases confondues",
    }

    img_path = SST_PAT_DIR / f"{sel_phase}_sst_patterns_clusters.png"
    if img_path.exists():
        st.image(str(img_path), use_container_width=True)
    else:
        st.info(
            f"Image non disponible pour {PHASE_LABELS_PUB.get(sel_phase, sel_phase)}. "
            f"Executez le script 14 pour generer les cartes."
        )
