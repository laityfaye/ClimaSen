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
    selected_cl = st.session_state.get("cl_shared_cluster")
    n_c = len(chars_s)
    card_cols = st.columns(min(n_c, 5))
    for i, row in enumerate(chars_s.itertuples()):
        with card_cols[i % len(card_cols)]:
            cid    = row.cluster
            color  = cl_colors[i % len(cl_colors)]
            pct    = f"{row.percentage:.1f}%"
            mp     = f"{row.mean_max_precip:.1f} mm"
            cov    = f"{row.mean_coverage_percent:.1f}%"
            anom   = f"{row.mean_max_anomaly:.1f}"
            is_sel = (selected_cl == cid)
            b_w    = "3px" if is_sel else "2px"
            bg     = (f"linear-gradient(135deg,{color}28 0%,{color}0d 100%)"
                      if is_sel else CARD)
            glow   = (f"0 0 0 2px {color},0 6px 28px {color}77"
                      if is_sel else "none")
            badge  = (f'<span style="position:absolute;top:10px;right:10px;'
                      f'background:{color};color:#0d1117;font-size:0.58rem;'
                      f'font-weight:800;padding:2px 8px;border-radius:20px;'
                      f'letter-spacing:.06em;text-transform:uppercase;">Actif</span>'
                      if is_sel else "")
            with st.container():
                st.markdown(
                    f'<style>'
                    f'[data-testid="stVerticalBlock"]:has(.mk-cl-{cid})'
                    f':not(:has(>[data-testid="stVerticalBlock"]))'
                    f'{{position:relative !important;z-index:1 !important;'
                    f'cursor:pointer !important;}}'
                    f'[data-testid="stVerticalBlock"]:has(.mk-cl-{cid})'
                    f':not(:has(>[data-testid="stVerticalBlock"])):hover .cl-card-{cid}'
                    f'{{transform:translateY(-2px) !important;'
                    f'box-shadow:0 8px 24px rgba(0,0,0,.5) !important;}}'
                    f'*:has(>[data-testid="stMarkdown"] .mk-cl-{cid})'
                    f'+*:has([data-testid="stButton"])'
                    f'{{position:absolute !important;'
                    f'top:0 !important;left:0 !important;'
                    f'right:0 !important;bottom:0 !important;'
                    f'z-index:2 !important;}}'
                    f'*:has(>[data-testid="stMarkdown"] .mk-cl-{cid})'
                    f'+*:has([data-testid="stButton"]) button'
                    f'{{position:absolute !important;'
                    f'top:0 !important;left:0 !important;'
                    f'right:0 !important;bottom:0 !important;'
                    f'opacity:0 !important;cursor:pointer !important;}}'
                    f'</style>'
                    f'<span class="mk-cl-{cid}" style="display:none;"></span>'
                    f'<div class="cl-card-{cid}" style="background:{bg};'
                    f'border:{b_w} solid {color};border-radius:14px;'
                    f'padding:16px 18px;margin-bottom:4px;position:relative;'
                    f'transition:transform .13s ease,box-shadow .13s ease;'
                    f'box-shadow:{glow};">'
                    f'{badge}'
                    f'<p style="font-size:0.8rem;font-weight:800;color:{color};margin:0 0 8px 0;">'
                    f'Cluster {cid}&nbsp;'
                    f'<span style="font-weight:500;color:{MUTED};">({pct})</span></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:0;">Evenements&nbsp;: <b style="color:{TEXT};">{row.n_events}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Precip moy.&nbsp;: <b style="color:{TEXT};">{mp}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Couverture moy.&nbsp;: <b style="color:{TEXT};">{cov}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Anomalie moy.&nbsp;: <b style="color:{TEXT};">{anom}</b></p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(" ", key=f"cl_card_{cid}", use_container_width=True):
                    st.session_state["cl_shared_cluster"] = cid
                    st.rerun()

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
    st.markdown(f"""
    <div style="border-top:2px solid {BORDER};margin:32px 0 18px 0;"></div>
    <h2 style="font-size:1.05rem;font-weight:800;color:{TEXT};margin:0 0 6px 0;">
      Analyse spatiale &mdash; Cartographie</h2>
    <p style="font-size:0.78rem;color:{MUTED};margin:0 0 16px 0;">
      Precipitation moyenne composite sur le Senegal (tous evenements representatifs
      du cluster).</p>
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
            _cl_px_c = _cl_px_ph[_cl_px_ph["cluster"] == _cl_carto_sel].copy()

            _cl_dept_geo    = load_dept_geojson()
            _cl_bounds_path = BASE / "data/geographic/senegal_boundaries.geojson"

            # ── Filtrage frontiere Senegal ─────────────────────────────
            if _cl_bounds_path.exists() and len(_cl_px_c) > 0:
                import json as _json_cl
                from matplotlib.path import Path as _MplPathCl
                with open(str(_cl_bounds_path), "r", encoding="utf-8") as _bfcl:
                    _cl_bounds_geo = _json_cl.load(_bfcl)
                _cl_bp_list = []
                for _feat_cl in _cl_bounds_geo.get("features", []):
                    _geom_cl   = _feat_cl.get("geometry", {})
                    _gtype_cl  = _geom_cl.get("type", "")
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
                        _cl_px_c["longitude"].values, _cl_px_c["latitude"].values
                    ])
                    _cl_ins = np.zeros(len(_cl_pts), dtype=bool)
                    for _cl_bp in _cl_bp_list:
                        _cl_ins |= _cl_bp.contains_points(_cl_pts)
                    _cl_px_c = _cl_px_c[_cl_ins].reset_index(drop=True)

            _cl_px_c = _cl_px_c[_cl_px_c["precipitation_mm"] > 0].reset_index(drop=True)

            if len(_cl_px_c) == 0:
                st.info("Aucun pixel disponible pour ce cluster.")
            else:
                # ── Composite : moyenne par cellule lat/lon ────────────
                _cl_comp = (
                    _cl_px_c
                    .groupby(["latitude", "longitude"], as_index=False)
                    .agg(
                        precipitation_mm=("precipitation_mm", "mean"),
                        anomaly_standardized=("anomaly_standardized", "mean"),
                        region=("region", "first"),
                        intensity_category=("intensity_category", "first"),
                    )
                )

                _cl_lats = _cl_comp["latitude"].tolist()
                _cl_lons = _cl_comp["longitude"].tolist()
                _cl_prec = _cl_comp["precipitation_mm"].tolist()
                _cl_anom = _cl_comp["anomaly_standardized"].tolist()
                _cl_regs = _cl_comp["region"].tolist()

                _cl_p_max = float(np.percentile(_cl_prec, 99))
                _cl_p_min = max(0.0, float(np.percentile(_cl_prec, 1)))

                _w_ctr = _cl_comp["precipitation_mm"].values
                _w_sum = float(_w_ctr.sum())
                if _w_sum > 0:
                    _cl_ctr_lat = float(np.average(_cl_comp["latitude"].values,  weights=_w_ctr))
                    _cl_ctr_lon = float(np.average(_cl_comp["longitude"].values, weights=_w_ctr))
                else:
                    _cl_ctr_lat = float(_cl_comp["latitude"].mean())
                    _cl_ctr_lon = float(_cl_comp["longitude"].mean())

                # ── Statistiques regionales (depuis pixels bruts, pas le composite) ──
                _cl_reg_stats = (
                    _cl_px_c.groupby("region")["precipitation_mm"]
                    .agg(max_p="max", mean_p="mean", n_px="count")
                    .sort_values("mean_p", ascending=False)
                    .head(6)
                )
                _cl_reg_top = _cl_reg_stats.index[0] if len(_cl_reg_stats) else "-"

                _cl_cl_color   = cl_colors[
                    cl_ids_sorted.index(_cl_carto_sel) % len(cl_colors)
                    if _cl_carto_sel in cl_ids_sorted else 0
                ]

                # ── Layout 2/3 carte  +  1/3 stats ────────────────────
                _cl_col_map, _cl_col_stat = st.columns([2, 1], gap="medium")

                with _cl_col_map:
                    _CS_PREC_CL = [
                        [0.00, "#f0f9ff"], [0.06, "#bae6fd"], [0.18, "#38bdf8"],
                        [0.35, "#0ea5e9"], [0.55, "#f97316"], [0.75, "#ef4444"],
                        [0.90, "#7c3aed"], [1.00, "#1e1b4b"],
                    ]

                    _cl_bmap = dict(
                        style="carto-positron",
                        center=dict(lat=_cl_ctr_lat, lon=_cl_ctr_lon),
                        zoom=6.2,
                    )

                    _cl_fig_comp = go.Figure()

                    # Contours departements (fond, dessines avant les pixels)
                    if _cl_dept_geo is not None:
                        _lo_b, _la_b = [], []
                        for _fbt in _cl_dept_geo.get("features", []):
                            _gbm   = _fbt.get("geometry", {})
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
                        _cl_fig_comp.add_trace(go.Scattermapbox(
                            lat=_la_b, lon=_lo_b, mode="lines",
                            line=dict(width=1.1, color="rgba(30,27,75,0.35)"),
                            hoverinfo="none", showlegend=False,
                        ))

                    # Pixels precipitation (halo blanc pour lisibilite)
                    _cl_fig_comp.add_trace(go.Scattermapbox(
                        lat=_cl_lats, lon=_cl_lons,
                        mode="markers",
                        marker=dict(size=11, color="white", opacity=0.30),
                        hoverinfo="skip", showlegend=False,
                    ))
                    _cl_fig_comp.add_trace(go.Scattermapbox(
                        lat=_cl_lats, lon=_cl_lons,
                        mode="markers",
                        marker=dict(
                            size=9,
                            color=_cl_prec,
                            colorscale=_CS_PREC_CL,
                            cmin=_cl_p_min, cmax=_cl_p_max,
                            opacity=0.92,
                            colorbar=dict(
                                title=dict(
                                    text="mm moy.",
                                    font=dict(size=10, color=MUTED),
                                ),
                                thickness=11, len=0.70,
                                x=1.01, xanchor="left",
                                y=0.5, yanchor="middle",
                                tickfont=dict(size=9, color=MUTED),
                                outlinewidth=0,
                                bgcolor="rgba(255,255,255,0.0)",
                            ),
                        ),
                        customdata=[[f"{a:+.1f}", rg, f"{p:.1f}"]
                                    for a, rg, p in zip(_cl_anom, _cl_regs, _cl_prec)],
                        hovertemplate=(
                            "<b>%{customdata[2]} mm</b> moy. &nbsp;|&nbsp; %{customdata[0]}&sigma;<br>"
                            "<span style='color:#64748b'>Region : %{customdata[1]}</span>"
                            "<extra></extra>"
                        ),
                        showlegend=False,
                    ))

                    # Centroide de precipitation
                    _cl_fig_comp.add_trace(go.Scattermapbox(
                        lat=[_cl_ctr_lat], lon=[_cl_ctr_lon], mode="markers",
                        marker=dict(size=20, color="white", opacity=0.85),
                        hoverinfo="skip", showlegend=False,
                    ))
                    _cl_fig_comp.add_trace(go.Scattermapbox(
                        lat=[_cl_ctr_lat], lon=[_cl_ctr_lon], mode="markers",
                        marker=dict(
                            size=13, color=_cl_cl_color, opacity=1.0,
                            symbol="circle",
                        ),
                        hovertemplate=(
                            f"<b>Barycentre C{_cl_carto_sel}</b><br>"
                            f"{_cl_ctr_lat:.2f}N  {abs(_cl_ctr_lon):.2f}W"
                            "<extra></extra>"
                        ),
                        showlegend=False,
                    ))

                    _cl_fig_comp.update_layout(
                        mapbox=_cl_bmap,
                        margin=dict(l=0, r=0, t=0, b=0),
                        height=500,
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor=CARD,
                    )
                    with st.spinner("Chargement de la carte..."):
                        st.plotly_chart(
                            _cl_fig_comp, use_container_width=True, key="cl_carto_composite",
                            config={
                                "displayModeBar": True,
                                "modeBarButtonsToRemove": [
                                    "lasso2d", "select2d", "autoScale2d",
                                    "hoverClosestMapbox",
                                ],
                                "displaylogo": False,
                                "toImageButtonOptions": {
                                    "format": "png",
                                    "filename": f"cluster{_cl_carto_sel}_{sel_phase}_composite",
                                    "scale": 3,
                                },
                            },
                        )

                # ── Panneau statistiques (1/3) ─────────────────────────
                with _cl_col_stat:

                    def _sp_bar(pct, color):
                        w = min(max(float(pct), 0), 100)
                        return (
                            f'<div style="height:6px;background:{BORDER};border-radius:99px;'
                            f'margin-top:6px;overflow:hidden;">'
                            f'<div style="width:{w:.1f}%;height:100%;background:{color};'
                            f'border-radius:99px;"></div></div>'
                        )

                    # En-tete cluster
                    st.markdown(
                        f'<div style="background:{_cl_cl_color}18;border-left:3px solid '
                        f'{_cl_cl_color};border-radius:0 10px 10px 0;padding:10px 14px;'
                        f'margin-bottom:18px;">'
                        f'<p style="margin:0;font-size:0.68rem;font-weight:700;color:{_cl_cl_color};'
                        f'text-transform:uppercase;letter-spacing:.07em;">Cluster {_cl_carto_sel}</p>'
                        f'<p style="margin:2px 0 0 0;font-size:0.78rem;color:{MUTED};">'
                        f'{PHASE_LABELS_CL.get(sel_phase, sel_phase)}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Top regions
                    st.markdown(
                        f'<p style="margin:0 0 10px 0;font-size:0.70rem;font-weight:700;'
                        f'color:{MUTED};text-transform:uppercase;letter-spacing:.05em;">'
                        f'Regions les plus arrosees &nbsp;'
                        f'<span style="font-weight:400;text-transform:none;'
                        f'letter-spacing:0;">(precip. moyenne)</span></p>',
                        unsafe_allow_html=True,
                    )
                    _cl_reg_ref = float(_cl_reg_stats["mean_p"].max()) if len(_cl_reg_stats) else 1.0
                    for _rname, _rrow in _cl_reg_stats.iterrows():
                        _rpct = float(_rrow["mean_p"]) / _cl_reg_ref * 100
                        _is_top = (_rname == _cl_reg_top)
                        st.markdown(
                            f'<div style="margin-bottom:12px;">'
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:baseline;">'
                            f'<span style="font-size:0.76rem;'
                            f'font-weight:{"700" if _is_top else "400"};'
                            f'color:{TEXT if _is_top else MUTED};'
                            f'white-space:nowrap;overflow:hidden;'
                            f'text-overflow:ellipsis;max-width:65%;">{_rname}</span>'
                            f'<span style="font-size:0.74rem;font-weight:700;'
                            f'color:{BLUE};">{_rrow["mean_p"]:.1f} mm</span>'
                            f'</div>'
                            + _sp_bar(_rpct, INDIGO if _is_top else BLUE)
                            + f'</div>',
                            unsafe_allow_html=True,
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
