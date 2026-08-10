import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import dashboard_utils as du
from dashboard_utils import (
    INDIGO, BLUE, EMERALD, AMBER, ROSE,
    load_telecon, _sig_from_p_neff,
)

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
LAGS_ALL = [0, 1, 2, 3, 4, 5]
IDX_GROUP = {
    "ENSO":             ["Nino12", "Nino3", "Nino34", "Nino4"],
    "Ocean Indien":     ["IOD", "IOBM"],
    "Atlantique Trop.": ["TNA", "TSA", "ATL3", "AMM"],
    "Atlantique Multi": ["AMO"],
}


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT, card=CARD)

    def _CHART_CFG(filename="chart"):
        return {
            "displayModeBar": "hover",
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
            "toImageButtonOptions": {
                "format": "png",
                "filename": filename,
                "scale": 2,
            },
        }

    with st.spinner("Chargement des teleconnexions..."):
        tc_data = load_telecon()

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Teleconnexions</b></p>
        <h1 class="pg-ttl">Teleconnexions SST - Precipitations Extremes</h1>
        <p class="pg-sub">
          Series <b>annuelles</b> (interannuel) &nbsp;&middot;&nbsp;
          Correlations Pearson &amp; Spearman · Correction AR1 (p<sub>neff</sub>)
          &nbsp;&middot;&nbsp; Lags 0-5 mois &nbsp;&middot;&nbsp; 11 indices SST
          &nbsp;&middot;&nbsp; ~41 ans (1983-2023)
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    all_indices = [i for grp in IDX_GROUP.values() for i in grp]

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Heatmaps lag 0 : tous indices x toutes metriques, par phase ─────────
    st.markdown(
        '<p class="pnl-ttl">Heatmaps des correlations au lag 0 - indices x metriques, par phase</p>',
        unsafe_allow_html=True,
    )

    METRIC_SHORT = {
        "max_precip":       "Precip max",
        "mean_precip":      "Precip moy",
        "max_anomaly":      "Anomalie max",
        "coverage_percent": "Couverture %",
        "n_events":         "N evenements",
    }
    metrics_order = list(METRIC_L.keys())
    metrics_labels = [METRIC_SHORT[m] for m in metrics_order]
    phase_keys_lag0 = list(PHASE_TC_L.keys())

    la0a, la0b, la0c, la0d = st.columns([2, 1.5, 1.3, 2], gap="small")
    with la0a:
        lag0_phase_sel = st.selectbox(
            "Phase saisonniere",
            options=phase_keys_lag0,
            format_func=lambda x: PHASE_TC_L[x],
            index=phase_keys_lag0.index("Toutes phases"),
            key="lag0_phase_sel",
        )
    with la0b:
        lag0_type = st.selectbox("Type", ["Pearson", "Spearman"], key="lag0_type")
    with la0c:
        lag0_show_sig = st.checkbox("Sig. seulement", value=False, key="lag0_show_sig")
    with la0d:
        lag0_p_mode = st.radio(
            "Significativite",
            options=["p brute", "p neff (AR1)"],
            index=1,
            horizontal=True,
            key="lag0_p_mode",
            help="p neff (AR1) : corrigee pour l'autocorrelation (Chelton 1983) -- recommandee\n"
                 "p brute : p-value nominale sans correction",
        )
        use_p_brute0 = (lag0_p_mode == "p brute")

    r_col0        = "pearson_r"        if lag0_type == "Pearson" else "spearman_r"
    p_neff_col0   = "pearson_p_neff"   if lag0_type == "Pearson" else "spearman_p_neff"
    p_nom_col0    = "pearson_p"        if lag0_type == "Pearson" else "spearman_p"
    p_active_col0 = p_nom_col0 if use_p_brute0 else p_neff_col0

    if use_p_brute0:
        star_label0 = 'p<sub>brute</sub> (non corrigee)'
        star_color0 = "#60A5FA"
    else:
        star_label0 = 'p<sub>neff</sub> (AR1 Chelton)'
        star_color0 = "#F59E0B"

    st.markdown(
        f'<p class="pnl-sub">'
        f'Lag 0 uniquement &nbsp;&middot;&nbsp; Toutes les metriques &nbsp;&middot;&nbsp; '
        f'Couleur = coefficient r ({lag0_type}) &nbsp;&middot;&nbsp; Etoiles = {star_label0} : '
        f'<b style="color:{star_color0};">*</b> &lt;0,05 &nbsp; '
        f'<b style="color:{star_color0};">**</b> &lt;0,01 &nbsp; '
        f'<b style="color:{star_color0};">***</b> &lt;0,001'
        f'</p>',
        unsafe_allow_html=True,
    )

    def _build_lag0_metric_heatmap(phase_key):
        df_ph = tc_data.get(phase_key, pd.DataFrame())
        df_ph0 = df_ph[df_ph["lag_months"] == 0] if not df_ph.empty else pd.DataFrame()

        z, pnom, p, neff, n = [], [], [], [], []
        for hm_idx in all_indices:
            row_z, row_pnom, row_p, row_neff, row_n = [], [], [], [], []
            for met in metrics_order:
                sub = df_ph0[(df_ph0["index"] == hm_idx) & (df_ph0["metric"] == met)] \
                    if not df_ph0.empty else pd.DataFrame()
                if sub.empty:
                    row_z.append(None); row_pnom.append(None)
                    row_p.append(None); row_neff.append(None); row_n.append(None)
                else:
                    row_z.append(float(sub[r_col0].values[0]))
                    pnom_v = sub[p_nom_col0].values[0] if p_nom_col0 in sub.columns else None
                    row_pnom.append(float(pnom_v) if pnom_v is not None and pd.notna(pnom_v) else None)
                    pv = sub[p_neff_col0].values[0] if p_neff_col0 in sub.columns else None
                    row_p.append(float(pv) if pv is not None and pd.notna(pv) else None)
                    ne = sub["n_eff"].values[0] if "n_eff" in sub.columns else None
                    row_neff.append(float(ne) if ne is not None and pd.notna(ne) else None)
                    nv = sub["n"].values[0] if "n" in sub.columns else None
                    row_n.append(int(nv) if nv is not None and pd.notna(nv) else None)
            z.append(row_z); pnom.append(row_pnom)
            p.append(row_p); neff.append(row_neff); n.append(row_n)

        p_active = pnom if use_p_brute0 else p

        cell_text = [
            [f"{v:+.2f}" if v is not None else "" for v in row]
            for row in z
        ]
        customdata = [
            [
                [
                    f"{pnom[ri][ci]:.4f}" if pnom[ri][ci] is not None else "N/A",
                    f"{p[ri][ci]:.4f}" if p[ri][ci] is not None else "N/A",
                    f"{int(neff[ri][ci])}" if neff[ri][ci] is not None else "N/A",
                    f"{int(n[ri][ci])}" if n[ri][ci] is not None else "N/A",
                ]
                for ci in range(len(metrics_order))
            ]
            for ri in range(len(all_indices))
        ]

        fig = go.Figure(go.Heatmap(
            z=z,
            x=metrics_labels,
            y=all_indices,
            text=cell_text,
            customdata=customdata,
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
                "n (annees) = %{customdata[3]} &nbsp; n_eff = %{customdata[2]}"
                "<extra></extra>"
            ),
        ))

        annotations = []
        for ri, hm_idx in enumerate(all_indices):
            for ci in range(len(metrics_order)):
                p_v = p_active[ri][ci]
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
                    x=metrics_labels[ci],
                    y=hm_idx,
                    text=f"<b>{star_txt}</b>",
                    showarrow=False,
                    xanchor="right",
                    yanchor="bottom",
                    xshift=18,
                    yshift=-2,
                    font=dict(size=15, color="#000000", family="Inter,sans-serif"),
                ))

        for sep in [4, 6, 10]:
            fig.add_hline(y=sep - 0.5, line=dict(color=BORDER, width=1.5, dash="dot"))

        fig.update_layout(
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
        return fig

    hm0_col, top0_col = st.columns([3, 1.3], gap="medium")

    with hm0_col:
        fig_lag0 = _build_lag0_metric_heatmap(lag0_phase_sel)
        st.plotly_chart(
            fig_lag0, use_container_width=True,
            config=_CHART_CFG(f"heatmap_lag0_{lag0_phase_sel}"),
        )

    with top0_col:
        _top0_p_label = "p<sub>neff</sub> (AR1)" if not use_p_brute0 else "p<sub>brute</sub>"
        st.markdown(
            '<p class="pnl-ttl">Top 8 correlations</p>'
            f'<p class="pnl-sub">Lag 0 &nbsp;&middot;&nbsp; {PHASE_TC_L[lag0_phase_sel]} &nbsp;&middot;&nbsp; '
            f'valeurs absolues · toutes metriques · etoiles = {_top0_p_label}</p>',
            unsafe_allow_html=True,
        )

        df_ph0_top = tc_data.get(lag0_phase_sel, pd.DataFrame())
        df_ph0_top = df_ph0_top[df_ph0_top["lag_months"] == 0].copy() if not df_ph0_top.empty else pd.DataFrame()
        if lag0_show_sig and not df_ph0_top.empty:
            if p_active_col0 in df_ph0_top.columns:
                df_ph0_top = df_ph0_top[df_ph0_top[p_active_col0].apply(_sig_from_p_neff).ne("")]
            else:
                df_ph0_top = df_ph0_top.iloc[0:0]
        if not df_ph0_top.empty:
            df_ph0_top = df_ph0_top.assign(abs_r=df_ph0_top[r_col0].abs()).nlargest(8, "abs_r")

        if df_ph0_top.empty:
            st.markdown(
                f'<p style="color:{MUTED};font-size:0.78rem;margin-top:12px;">'
                'Aucun resultat.</p>', unsafe_allow_html=True
            )
        else:
            GRAD_POS = ["#1E3A8A", "#1D4ED8", "#3B82F6", "#93C5FD"]
            GRAD_NEG = ["#7F1D1D", "#B91C1C", "#EF4444", "#FCA5A5"]
            for i, rec in enumerate(df_ph0_top.to_dict("records")):
                idx_name = rec["index"]
                met_lbl  = METRIC_SHORT.get(rec["metric"], rec["metric"])
                r_val    = rec[r_col0]
                is_pos   = r_val >= 0
                bar_clr  = GRAD_POS[min(i, 3)] if is_pos else GRAD_NEG[min(i, 3)]
                bar_w    = int(abs(r_val) / 0.5 * 100)
                r_clr    = "#1D4ED8" if is_pos else "#B91C1C"
                r_str    = f"{r_val:+.3f}"
                badge    = _sig_from_p_neff(rec.get(p_active_col0))
                sig_badge = ""
                if badge:
                    _badge_bg  = "rgba(96,165,250,0.18)"  if use_p_brute0 else "rgba(245,158,11,0.18)"
                    _badge_clr = "#2563EB"                if use_p_brute0 else "#D97706"
                    sig_badge = (
                        f'<span style="font-size:0.63rem;background:{_badge_bg};'
                        f'color:{_badge_clr};border-radius:4px;padding:1px 5px;'
                        f'font-weight:700;">{badge}</span>'
                    )
                st.markdown(
                    f'<div style="padding:7px 0;border-bottom:1px solid {BORDER};">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">'
                    f'<span style="font-size:0.75rem;font-weight:600;color:{TEXT};">'
                    f'{idx_name} &nbsp;<span style="color:{MUTED};font-weight:400;">{met_lbl}</span></span>'
                    f'<div style="display:flex;align-items:center;gap:4px;">'
                    f'{sig_badge}'
                    f'<span style="font-size:0.8rem;font-weight:700;color:{r_clr};">{r_str}</span>'
                    f'</div></div>'
                    f'<div style="background:{BG};border-radius:99px;height:4px;">'
                    f'<div style="width:{bar_w}%;height:4px;border-radius:99px;background:{bar_clr};"></div>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── Filtres inline ─────────────────────────────────────────────────────
    fa, fb, fc, fd, fe = st.columns([2, 2, 1.5, 1.5, 2], gap="small")
    with fa:
        tc_phase = st.selectbox(
            "Phase saisonniere",
            options=list(PHASE_TC_L.keys()),
            format_func=lambda x: PHASE_TC_L[x],
            index=list(PHASE_TC_L.keys()).index("Toutes phases"),
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
        p_mode = st.radio(
            "Significativite",
            options=["p brute", "p neff (AR1)"],
            index=1,
            horizontal=True,
            help="p neff (AR1) : corrigee pour l'autocorrelation (Chelton 1983) -- recommandee\n"
                 "p brute : p-value nominale sans correction",
        )
        use_p_brute = (p_mode == "p brute")

    r_col       = "pearson_r"        if tc_type == "Pearson" else "spearman_r"
    p_neff_col  = "pearson_p_neff"   if tc_type == "Pearson" else "spearman_p_neff"
    p_nom_col   = "pearson_p"        if tc_type == "Pearson" else "spearman_p"
    sig_nom_col = "sig_pearson_nom"  if tc_type == "Pearson" else "sig_spearman_nom"
    p_active_col = p_nom_col if use_p_brute else p_neff_col

    df_tc = tc_data.get(tc_phase, pd.DataFrame())
    if df_tc.empty:
        st.warning("Donnees non disponibles pour cette phase.")
        st.stop()

    df_m = df_tc[df_tc["metric"] == tc_metric].copy()
    lags_shown = LAGS_ALL

    if use_p_brute:
        star_label = 'p<sub>brute</sub> (non corrigee)'
        star_color = "#60A5FA"
    else:
        star_label = 'p<sub>neff</sub> (AR1 Chelton)'
        star_color = "#F59E0B"

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── Heatmap + Top correlations ─────────────────────────────────────────
    hm_col, top_col = st.columns([3, 1.3], gap="medium")

    with hm_col:
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

        z_mat, p_nom_mat, p_mat, neff_mat, n_mat = [], [], [], [], []
        for hm_idx in all_indices:
            row_z, row_pnom, row_p, row_neff, row_n = [], [], [], [], []
            for lag in lags_shown:
                sub = df_m[(df_m["index"] == hm_idx) & (df_m["lag_months"] == lag)]
                if sub.empty:
                    row_z.append(None); row_pnom.append(None)
                    row_p.append(None); row_neff.append(None); row_n.append(None)
                else:
                    row_z.append(float(sub[r_col].values[0]))
                    pnom = sub[p_nom_col].values[0] if p_nom_col in sub.columns else None
                    row_pnom.append(float(pnom) if pnom is not None and pd.notna(pnom) else None)
                    pv = sub[p_neff_col].values[0] if p_neff_col in sub.columns else None
                    row_p.append(float(pv) if pv is not None and pd.notna(pv) else None)
                    ne = sub["n_eff"].values[0] if "n_eff" in sub.columns else None
                    row_neff.append(float(ne) if ne is not None and pd.notna(ne) else None)
                    nv = sub["n"].values[0] if "n" in sub.columns else None
                    row_n.append(int(nv) if nv is not None and pd.notna(nv) else None)
            z_mat.append(row_z); p_nom_mat.append(row_pnom)
            p_mat.append(row_p); neff_mat.append(row_neff); n_mat.append(row_n)

        p_active_mat = p_nom_mat if use_p_brute else p_mat

        cell_text = []
        for ri in range(len(all_indices)):
            row_t = []
            for ci in range(len(lags_shown)):
                r_v = z_mat[ri][ci]
                row_t.append(f"{r_v:+.2f}" if r_v is not None else "")
            cell_text.append(row_t)

        customdata_mat = []
        for ri in range(len(all_indices)):
            row_cd = []
            for ci in range(len(lags_shown)):
                pn = p_nom_mat[ri][ci]
                pe = p_mat[ri][ci]
                ne = neff_mat[ri][ci]
                nv = n_mat[ri][ci]
                row_cd.append([
                    f"{pn:.4f}" if pn is not None else "N/A",
                    f"{pe:.4f}" if pe is not None else "N/A",
                    f"{int(ne)}" if ne is not None else "N/A",
                    f"{int(nv)}" if nv is not None else "N/A",
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
                "n (annees) = %{customdata[3]} &nbsp; n_eff = %{customdata[2]}"
                "<extra></extra>"
            ),
        ))

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
        st.plotly_chart(fig_hm, use_container_width=True, config=_CHART_CFG("heatmap_correlations"))

    # ── Top correlations ───────────────────────────────────────────────────
    with top_col:
        _top_p_label = "p<sub>neff</sub> (AR1)" if not use_p_brute else "p<sub>brute</sub>"
        st.markdown(
            '<p class="pnl-ttl">Top 8 correlations</p>'
            '<p class="pnl-sub">Valeurs absolues · tous lags · '
            f'etoiles = {_top_p_label} sur chaque ligne (comme la heatmap)</p>',
            unsafe_allow_html=True,
        )

        df_top = df_m.copy()
        if show_sig:
            if p_active_col in df_top.columns:
                df_top = df_top[df_top[p_active_col].apply(_sig_from_p_neff).ne("")]
            else:
                df_top = df_top.iloc[0:0]
        df_top = df_top.assign(abs_r=df_top[r_col].abs()).nlargest(8, "abs_r")

        if df_top.empty:
            st.markdown(
                f'<p style="color:{MUTED};font-size:0.78rem;margin-top:12px;">'
                'Aucun resultat.</p>', unsafe_allow_html=True
            )
        else:
            GRAD_POS = ["#1E3A8A", "#1D4ED8", "#3B82F6", "#93C5FD"]
            GRAD_NEG = ["#7F1D1D", "#B91C1C", "#EF4444", "#FCA5A5"]
            for i, rec in enumerate(df_top.to_dict("records")):
                idx_name = rec["index"]
                lag_v    = int(rec["lag_months"])
                r_val    = rec[r_col]
                is_pos   = r_val >= 0
                bar_clr  = GRAD_POS[min(i, 3)] if is_pos else GRAD_NEG[min(i, 3)]
                bar_w    = int(abs(r_val) / 0.5 * 100)
                r_clr    = "#1D4ED8" if is_pos else "#B91C1C"
                r_str    = f"{r_val:+.3f}"
                badge    = _sig_from_p_neff(rec.get(p_active_col))
                sig_badge = ""
                if badge:
                    _badge_bg  = "rgba(96,165,250,0.18)"  if use_p_brute else "rgba(245,158,11,0.18)"
                    _badge_clr = "#2563EB"                if use_p_brute else "#D97706"
                    sig_badge = (
                        f'<span style="font-size:0.63rem;background:{_badge_bg};'
                        f'color:{_badge_clr};border-radius:4px;padding:1px 5px;'
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

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── Profil de correlation par indice ────────────────────────────────────
    # ── Profil de correlation par indice ────────────────────────────────────
    _profil_p_label = "p<sub>neff</sub> (AR1 Chelton)" if not use_p_brute else "p<sub>brute</sub>"
    _profil_star_clr = "#F59E0B" if not use_p_brute else "#60A5FA"
    st.markdown(
        '<p class="pnl-ttl">Profil de correlation par indice (r vs lag)</p>'
        '<p class="pnl-sub">Evolution du coefficient r en fonction du decalage temporel'
        f' &nbsp;&middot;&nbsp; <span style="color:{_profil_star_clr};">&#9733;</span> = significatif '
        f'({_profil_p_label} : 0,05 / 0,01 / 0,001)</p>',
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

        symbols, sizes, texts, hover_extra = [], [], [], []
        _plbl = "p_neff" if not use_p_brute else "p_brute"
        for _, row in sub_idx.iterrows():
            p = row.get(p_active_col, float("nan"))
            if pd.notna(p) and p < 0.001:
                symbols.append("star"); sizes.append(18)
                texts.append("***"); hover_extra.append(f"*** {_plbl}={p:.4f}")
            elif pd.notna(p) and p < 0.01:
                symbols.append("star"); sizes.append(16)
                texts.append("**"); hover_extra.append(f"** {_plbl}={p:.4f}")
            elif pd.notna(p) and p < 0.05:
                symbols.append("star"); sizes.append(14)
                texts.append("*"); hover_extra.append(f"* {_plbl}={p:.4f}")
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
            textfont=dict(size=10, color=BLUE if use_p_brute else AMBER, family="Inter,sans-serif"),
            customdata=hover_extra,
            hovertemplate=(
                f"<b>{idx}</b> · lag %{{x}}m<br>"
                "r = %{y:.3f}%{customdata}<extra></extra>"
            ),
        ))

    fig_line.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
    fig_line.add_hrect(y0=-0.2, y1=0.2, fillcolor="rgba(100,116,139,0.05)",
                       line_width=0)

    plotly_base(fig_line, h=300)
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
    st.plotly_chart(fig_line, use_container_width=True, config=_CHART_CFG("profil_correlation"))


    # ── Serie temporelle SST + Distribution evenements (figure unique) ────

    PHASE_MONTHS_MAP = {
        "Phase_1_debut":  [5, 6],
        "Phase_2_pleine": [7, 8],
        "Phase_3_fin":    [9, 10],
        "Toutes phases":  [5, 6, 7, 8, 9, 10],
    }
    phase_months_map = PHASE_MONTHS_MAP.get(tc_phase, [5, 6, 7, 8, 9, 10])

    STUDIED_MONTHS_DIST = {5: "Mai", 6: "Jun", 7: "Jul", 8: "Aou", 9: "Sep", 10: "Oct"}
    MONTH_CLR_TC = {"Mai": "#7DD3FC", "Jun": "#0EA5E9",
                    "Jul": "#818CF8", "Aou": "#4F46E5",
                    "Sep": "#FCD34D", "Oct": "#F59E0B"}

    # ── Donnees SST (agregation annuelle sur les mois de la phase) ────────
    sst_raw = du.load_sst().copy()
    sst_raw["_month"] = sst_raw["date"].dt.month
    sst_raw["_year"]  = sst_raw["date"].dt.year
    sst_phase_data = sst_raw[sst_raw["_month"].isin(phase_months_map)]
    avail_sst = [i for i in sel_indices if i in sst_phase_data.columns]

    COLORS_TS = [INDIGO, BLUE, AMBER, EMERALD, ROSE,
                 "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#64748B", "#84CC16"]

    sst_annual = pd.DataFrame()
    if avail_sst:
        sst_annual = (
            sst_phase_data
            .groupby("_year")[avail_sst]
            .mean()
            .reset_index()
            .rename(columns={"_year": "year"})
            .sort_values("year")
        )

    # ── Donnees distribution mensuelle (tous les 6 mois, plage d'annees) ──
    evts_all = du.load_events()
    evts_yr  = evts_all[
        (evts_all["year"] >= year_range[0]) & (evts_all["year"] <= year_range[1])
    ]
    pivot_m = (
        evts_yr.groupby(["year", "month"]).size()
        .reset_index(name="n")
        .pivot(index="year", columns="month", values="n")
        .reindex(columns=list(STUDIED_MONTHS_DIST.keys()))
        .fillna(0)
        .astype(int)
    )
    pivot_m.columns = [STUDIED_MONTHS_DIST[m] for m in pivot_m.columns]

    # ── Periode commune SST / evenements ──────────────────────────────────
    sst_years  = set(sst_annual["year"].tolist()) if not sst_annual.empty else set()
    evts_years = set(pivot_m.index.tolist())      if not pivot_m.empty   else set()
    if sst_years and evts_years:
        common_years = sorted(sst_years & evts_years)
        if not sst_annual.empty:
            sst_annual = sst_annual[sst_annual["year"].isin(common_years)]
        if not pivot_m.empty:
            pivot_m = pivot_m[pivot_m.index.isin(common_years)]
    elif sst_years:
        common_years = sorted(sst_years)
    elif evts_years:
        common_years = sorted(evts_years)
    else:
        common_years = []

    # ── Calibrage des plages pour aligner les deux zeros ──────────────────
    import numpy as _np
    if not sst_annual.empty and avail_sst:
        _v = sst_annual[avail_sst].values.flatten()
        sst_ylim = float(_np.nanmax(_np.abs(_v))) * 1.35 or 1.5
    else:
        sst_ylim = 1.5

    _max_evts = float(pivot_m.values.max()) if not pivot_m.empty else 15.0
    # Barres contraintes a ~15 % de la demi-hauteur positive (x2 vs precedent)
    # => echelle SST visuellement x2 superieure aux barres
    evts_ylim = _max_evts / 0.15

    # Ticks seulement jusqu'au vrai max des evenements (pas jusqu'a evts_ylim)
    _max_evts_int = max(1, int(_max_evts))
    _step_t = max(1, round(_max_evts_int / 5))
    _tvals  = list(range(0, _max_evts_int + 1, _step_t))
    if _tvals[-1] != _max_evts_int:
        _tvals.append(_max_evts_int)
    _ttxt = [str(v) for v in _tvals]

    # ── Figure unique, double axe Y superposes au meme zero ───────────────
    fig_cb = go.Figure()

    # Barres (yaxis2, range symetrique => zero au milieu => barres dans la moitie haute)
    for mname in pivot_m.columns:
        fig_cb.add_trace(go.Bar(
            x=pivot_m.index.tolist(),
            y=pivot_m[mname].tolist(),
            name=mname,
            yaxis="y2",
            marker_color=MONTH_CLR_TC[mname],
            marker_line_width=0,
            opacity=0.70,
            hovertemplate=f"<b>{mname}</b> · %{{x}} : %{{y}} evt<extra></extra>",
        ))

    # Lignes SST (yaxis gauche, range symetrique => zero au milieu)
    for ci, idx in enumerate(avail_sst):
        clr = COLORS_TS[ci % len(COLORS_TS)]
        fig_cb.add_trace(go.Scatter(
            x=sst_annual["year"],
            y=sst_annual[idx],
            mode="lines+markers",
            name=idx,
            yaxis="y",
            line=dict(color=clr, width=2),
            marker=dict(size=4, color=clr),
            hovertemplate=(
                f"<b>{idx}</b><br>%{{x}}<br>Anom moy. = %{{y:.3f}} degC<extra></extra>"
            ),
        ))

    # Ligne zero commune (reference climatologique)
    fig_cb.add_hline(y=0, yref="y",
                     line=dict(color=MUTED, width=1.2, dash="dot"))

    fig_cb.update_layout(
        height=400,
        barmode="group",
        bargap=0.15,
        bargroupgap=0.05,
        margin=dict(l=4, r=60, t=28, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter,sans-serif", size=11, color=MUTED),
        hoverlabel=dict(bgcolor=CARD, font_color=TEXT, font_size=12, bordercolor=BORDER),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            font=dict(size=8, color=TEXT), itemwidth=30,
            tracegroupgap=0,
        ),
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=10, color=TEXT),
            dtick=5,
            title=dict(text="Annee", font=dict(size=10, color=MUTED)),
            automargin=True,
        ),
        # Axe SST : symetrique autour de 0 (gauche)
        yaxis=dict(
            title=dict(text="Anom. SST moy. (degC)", font=dict(size=10, color=MUTED)),
            range=[-sst_ylim, sst_ylim],
            zeroline=True, zerolinecolor=BORDER, zerolinewidth=1,
            showgrid=True, gridcolor=BORDER,
            tickfont=dict(size=10, color=MUTED),
            side="left",
        ),
        # Axe evenements : symetrique autour de 0 => zero aligne avec SST (droite)
        yaxis2=dict(
            title=dict(text="N evenements", font=dict(size=10, color=MUTED)),
            range=[-evts_ylim, evts_ylim],
            zeroline=False,
            showgrid=False,
            tickvals=_tvals,
            ticktext=_ttxt,
            tickfont=dict(size=10, color=MUTED),
            side="right",
            overlaying="y",
        ),
    )
    st.markdown(
        '<p class="pnl-ttl">Anomalies SST annuelles &amp; Distribution mensuelle des evenements</p>'
        '<p class="pnl-sub">'
        'Lignes : moyenne annuelle des indices SST selectionnes (mois de la phase) &nbsp;&middot;&nbsp; '
        'Barres : N evenements par mois &nbsp;&middot;&nbsp; '
        'Zero commun aux deux axes</p>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig_cb, use_container_width=True, config=_CHART_CFG("anomalies_sst_evenements"))

    # ── Metriques KPI ──────────────────────────────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    df_all_m = df_m.copy()
    n_tests  = len(df_all_m)
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
        (mk1, "background:rgba(79,70,229,0.13)", "Tests totaux", f"{n_tests}", "t-indigo",
         f"{len(all_indices)} indices x {len(LAGS_ALL)} lags · ~41 pts/phase"),
        (mk2, "background:rgba(16,185,129,0.13)", "Sig. nominale", f"{int(n_sig_nom)}", "t-green",
         "p brute (Pearson/Spearman) sans correction"),
        (mk3, "background:rgba(245,158,11,0.13)", "Sig. AR1 (p_neff)", f"{int(n_sig_ar1)}", "t-amber",
         "p_neff Chelton 1983 · recommande"),
        (mk4, "background:rgba(14,165,233,0.13)", "r max |.|", f"{abs(best_r):.3f}", "t-blue",
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
