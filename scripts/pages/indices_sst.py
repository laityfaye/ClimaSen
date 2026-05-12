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
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT, card=CARD)

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
    fa, fb = st.columns([2.5, 2], gap="small")
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

    plotly_base(fig_ts, h=310)
    fig_ts.update_layout(
        yaxis=dict(
            title=dict(text="Anomalie SST (degC)", font=dict(size=11, color=MUTED)),
            zeroline=False,
        ),
        xaxis=dict(title=None, rangeslider=dict(visible=False)),
    )
    st.plotly_chart(fig_ts, use_container_width=True, config={
        "displayModeBar": "hover",
        "modeBarButtonsToKeep": ["toImage"],
        "toImageButtonOptions": {
            "format": "png",
            "filename": f"serie_temporelle_sst_{agg_mode.lower()}",
            "scale": 2,
        },
    })

