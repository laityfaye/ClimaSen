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
LAGS_ALL = [0, 1, 2, 3, 6, 9, 12]
IDX_GROUP = {
    "ENSO":             ["Nino12", "Nino3", "Nino34", "Nino4"],
    "Ocean Indien":     ["IOD", "IOBM"],
    "Atlantique Trop.": ["TNA", "TSA", "ATL3", "AMM"],
    "Atlantique Multi": ["AMO"],
}


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT)

    with st.spinner("Chargement des teleconnexions..."):
        tc_data = load_telecon()

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

    r_col       = "pearson_r"        if tc_type == "Pearson" else "spearman_r"
    p_neff_col  = "pearson_p_neff"   if tc_type == "Pearson" else "spearman_p_neff"
    p_nom_col   = "pearson_p"        if tc_type == "Pearson" else "spearman_p"
    sig_nom_col = "sig_pearson_nom"  if tc_type == "Pearson" else "sig_spearman_nom"

    df_tc = tc_data.get(tc_phase, pd.DataFrame())
    if df_tc.empty:
        st.warning("Donnees non disponibles pour cette phase.")
        st.stop()

    df_m = df_tc[df_tc["metric"] == tc_metric].copy()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    all_indices = [i for grp in IDX_GROUP.values() for i in grp]
    lags_shown  = LAGS_ALL

    # ── Heatmap + Top correlations ─────────────────────────────────────────
    hm_col, top_col = st.columns([3, 1.3], gap="medium")

    with hm_col:
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

        z_mat, p_nom_mat, p_mat, neff_mat = [], [], [], []
        for hm_idx in all_indices:
            row_z, row_pnom, row_p, row_neff = [], [], [], []
            for lag in lags_shown:
                sub = df_m[(df_m["index"] == hm_idx) & (df_m["lag_months"] == lag)]
                if sub.empty:
                    row_z.append(None); row_pnom.append(None)
                    row_p.append(None); row_neff.append(None)
                else:
                    row_z.append(float(sub[r_col].values[0]))
                    pnom = sub[p_nom_col].values[0] if p_nom_col in sub.columns else None
                    row_pnom.append(float(pnom) if pnom is not None and pd.notna(pnom) else None)
                    pv = sub[p_neff_col].values[0] if p_neff_col in sub.columns else None
                    row_p.append(float(pv) if pv is not None and pd.notna(pv) else None)
                    ne = sub["n_eff"].values[0] if "n_eff" in sub.columns else None
                    row_neff.append(float(ne) if ne is not None and pd.notna(ne) else None)
            z_mat.append(row_z); p_nom_mat.append(row_pnom)
            p_mat.append(row_p); neff_mat.append(row_neff)

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

        rows_synth = []
        for idx in all_indices:
            sub_idx = df_m[df_m["index"] == idx].copy()
            if sub_idx.empty:
                continue
            best = sub_idx.loc[sub_idx[r_col].abs().idxmax()]
            r_val = best[r_col]
            lag_v = int(best["lag_months"])
            pnb   = best[p_neff_col] if p_neff_col in best.index else float("nan")
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
            is_pos   = r_val >= 0
            r_clr    = "#1D4ED8" if is_pos else "#B91C1C"
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
         f"{len(all_indices)} indices x {len(LAGS_ALL)} lags"),
        (mk2, "background:rgba(16,185,129,0.13)", "Sig. nominale", f"{int(n_sig_nom)}", "t-green",
         "p brut (Pearson/Spearman), sans FDR"),
        (mk3, "background:rgba(245,158,11,0.13)", "Sig. AR1 (p_neff)", f"{int(n_sig_ar1)}", "t-amber",
         "Etoiles sur p_neff (Chelton 1983)"),
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
