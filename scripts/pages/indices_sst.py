import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import dashboard_utils as du
from dashboard_utils import (
    INDIGO, BLUE, EMERALD, AMBER, ROSE,
    load_sst, svg_spark,
)

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


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT)

    with st.spinner("Chargement des indices SST..."):
        sst_raw = load_sst()

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

    sst = sst_raw[
        sst_raw["date"].dt.year.between(year_range[0], year_range[1])
    ].copy()

    if agg_mode == "Mensuelle":
        sst_agg = sst.set_index("date")[SST_INDICES].resample("MS").mean().reset_index()
    elif agg_mode == "Annuelle":
        sst_agg = sst.set_index("date")[SST_INDICES].resample("YS").mean().reset_index()
    else:
        sst_agg = sst.copy()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── KPI du premier indice ──────────────────────────────────────────────
    pv      = sst[primary]
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
    fig_ts.add_hrect(y0=-0.5, y1=0.5, fillcolor="rgba(100,116,139,0.06)", line_width=0)
    fig_ts.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))

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
        xaxis=dict(title=None, rangeslider=dict(visible=False)),
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
        clr_p  = SST_COLORS.get(primary, INDIGO)
        vals_p = sst[primary].values

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=vals_p[vals_p < 0], nbinsx=40, name="Phase -",
            marker_color="rgba(239,68,68,0.6)", marker_line_width=0,
            hovertemplate="[%{x:.2f}] : %{y} jours<extra></extra>",
        ))
        fig_hist.add_trace(go.Histogram(
            x=vals_p[vals_p >= 0], nbinsx=40, name="Phase +",
            marker_color="rgba(59,130,246,0.6)", marker_line_width=0,
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
        clr_p  = SST_COLORS.get(primary, INDIGO)
        sst_m  = sst.copy()
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

    clr_p  = SST_COLORS.get(primary, INDIGO)
    r_hex  = int(clr_p[1:3], 16)
    g_hex  = int(clr_p[3:5], 16)
    b_hex  = int(clr_p[5:7], 16)

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
