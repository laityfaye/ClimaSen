#!/usr/bin/env python3
"""Page Evenements — SenRain Dashboard."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import dashboard_utils as du
from dashboard_utils import (
    INDIGO, BLUE, EMERALD, AMBER, ROSE, PHASE_C, PHASE_L, BASE,
    load_events_pixels, load_events_summary, load_dept_geojson, svg_spark,
)


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT, card=CARD)

    n_total  = len(dff)
    avg_cov  = dff["coverage_percent"].mean()
    avg_prec = dff["max_precip"].mean()
    avg_anom = dff["max_anomaly"].mean()

    all_yrs  = list(range(year_range[0], year_range[1] + 1))
    yr_n    = dff.groupby("year").size()
    yr_cov  = dff.groupby("year")["coverage_percent"].mean()
    yr_prec = dff.groupby("year")["max_precip"].mean()
    yr_anom = dff.groupby("year")["max_anomaly"].mean()
    sp_n    = [yr_n.get(y, 0)            for y in all_yrs]
    sp_cov  = [yr_cov.get(y, np.nan)     for y in all_yrs]
    sp_prec = [yr_prec.get(y, np.nan)    for y in all_yrs]
    sp_anom = [yr_anom.get(y, np.nan)    for y in all_yrs]

    # ── Header ────────────────────────────────────────────────────────────────
    _n_total_fmt = f"{n_total:,}".replace(",", " ")

    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.markdown(f"""
        <div class="pg-hdr">
          <div>
            <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Evenements</b></p>
            <h1 class="pg-ttl">Ev&eacute;nements de Pr&eacute;cipitation Extr&ecirc;me</h1>
            <p class="pg-sub">
              S&eacute;n&eacute;gal &nbsp;&middot;&nbsp; CHIRPS 0.05&deg;
              &nbsp;&middot;&nbsp; {year_range[0]}&ndash;{year_range[1]}
            </p>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;padding-bottom:4px;margin-top:10px;">
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:#7C3AED;
                         background:rgba(124,58,237,0.13);border-radius:8px;padding:5px 12px;">
              &#128208; Anomalie &gt; 2&#963;</span>
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:#0284C7;
                         background:rgba(2,132,199,0.13);border-radius:8px;padding:5px 12px;">
              &#9726; 40&nbsp;pixels&nbsp;min.</span>
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:#D97706;
                         background:rgba(217,119,6,0.13);border-radius:8px;padding:5px 12px;">
              &#127783; 5&nbsp;mm&nbsp;min.</span>
            <span class="evt-badge" style="font-size:0.70rem;font-weight:600;color:{INDIGO};
                         background:rgba(79,70,229,0.13);border-radius:8px;padding:5px 12px;">
              &#128202; {_n_total_fmt}&nbsp;&eacute;v&eacute;nements</span>
          </div>
        </div>
        """, unsafe_allow_html=True)
    with hc2:
        st.markdown("<div style='height:56px'></div>", unsafe_allow_html=True)
        st.download_button(
            "Exporter CSV",
            data=dff.to_csv(index=False).encode("utf-8"),
            file_name="evenements_senegal.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # ── Cartographie des evenements specifiques ───────────────────────────────
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

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
      <span class="sec-hdr-sub" style="font-size:0.67rem;color:{MUTED};white-space:nowrap;">
        6 ev&eacute;nements &middot; plus/moins intense, grande/petite couverture &amp; anomalie
      </span>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Chargement des cartes..."):
        _ev_pixels  = load_events_pixels()
        _ev_summary = load_events_summary()
        _dept_geo   = load_dept_geojson()

    if _ev_pixels is None or len(_ev_pixels) == 0:
        st.info(
            "Donnees cartographiques non disponibles. "
            "Executer le script 03_filter_events_for_qgis.py pour generer les fichiers de pixels."
        )
    else:
        _dates = sorted(_ev_pixels["event_date"].unique().tolist())
        _crit_map = (
            _ev_pixels.groupby("event_date")["selection_criterion"].first().to_dict()
            if "selection_criterion" in _ev_pixels.columns
            else {}
        )

        _CRIT_FR = {
            "plus_intense":           "Plus intense",
            "moins_intense":          "Moins intense",
            "plus_grande_couverture": "Plus grande couverture",
            "plus_petite_couverture": "Plus petite couverture",
            "plus_grande_anomalie":   "Plus grande anomalie",
            "plus_petite_anomalie":   "Plus petite anomalie",
            "selection_manuelle":     "Selection manuelle",
        }
        _CRIT_COLORS = {
            "plus_intense":           (ROSE,      "rgba(244,63,94,0.13)"),
            "moins_intense":          (EMERALD,   "rgba(16,185,129,0.13)"),
            "plus_grande_couverture": (INDIGO,    "rgba(79,70,229,0.13)"),
            "plus_petite_couverture": (BLUE,      "rgba(14,165,233,0.13)"),
            "plus_grande_anomalie":   (AMBER,     "rgba(245,158,11,0.13)"),
            "plus_petite_anomalie":   ("#6B7280", "rgba(107,114,128,0.13)"),
        }

        def _fmt_event(d):
            raw = _crit_map.get(d, "")
            parts = [_CRIT_FR.get(c.strip(), c.strip()) for c in raw.split("+")]
            label = " + ".join(parts) if parts and raw else ""
            return f"{d}  [{label}]" if label else d

        def _get_crit0(d):
            raw = _crit_map.get(d, "")
            return raw.split("+")[0].strip() if raw else ""

        # ── Selecteur + navigation ────────────────────────────────────────────
        if "carto_nav_idx" not in st.session_state:
            st.session_state["carto_nav_idx"] = 0
        _idx_cur = min(st.session_state["carto_nav_idx"], len(_dates) - 1)

        _sel_col, _prev_col, _ctr_col, _next_col = st.columns(
            [7, 1, 1.2, 1], gap="small"
        )
        with _prev_col:
            if st.button("←", key="ev_prev", disabled=_idx_cur <= 0,
                         use_container_width=True):
                st.session_state["carto_nav_idx"] = max(0, _idx_cur - 1)
                st.rerun()
        with _sel_col:
            _sel_date = st.selectbox(
                "Evenement selectionne",
                options=_dates,
                index=_idx_cur,
                format_func=_fmt_event,
                label_visibility="collapsed",
            )
            _sel_idx = _dates.index(_sel_date) if _sel_date in _dates else _idx_cur
            if _sel_idx != _idx_cur:
                st.session_state["carto_nav_idx"] = _sel_idx
                _idx_cur = _sel_idx
        with _ctr_col:
            st.markdown(
                f'<div style="text-align:center;padding:8px 0;'
                f'font-size:0.75rem;font-weight:700;color:{MUTED};">'
                f'{_idx_cur + 1}&nbsp;/&nbsp;{len(_dates)}</div>',
                unsafe_allow_html=True,
            )
        with _next_col:
            if st.button("→", key="ev_next",
                         disabled=_idx_cur >= len(_dates) - 1,
                         use_container_width=True):
                st.session_state["carto_nav_idx"] = min(len(_dates) - 1, _idx_cur + 1)
                st.rerun()

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # -- Pre-filtrage boundary Senegal (une seule fois pour tous les events) -----
        from matplotlib.path import Path as _MplPath

        def _build_paths(geojson):
            paths = []
            for feat in geojson.get("features", []):
                geom   = feat.get("geometry", {})
                gtype  = geom.get("type", "")
                coords = geom.get("coordinates", [])
                if gtype == "MultiPolygon":
                    for poly in coords:
                        if poly and poly[0]:
                            paths.append(_MplPath(np.array(poly[0])))
                elif gtype == "Polygon":
                    if coords and coords[0]:
                        paths.append(_MplPath(np.array(coords[0])))
            return paths

        _bounds_geo = load_dept_geojson()
        _bounds_path = BASE / "data/geographic/senegal_boundaries.geojson"
        if _bounds_path.exists():
            import json as _json
            with open(str(_bounds_path), "r", encoding="utf-8") as _bf:
                _bounds_geo = _json.load(_bf)

        _ev_pixels_sn = _ev_pixels.copy()
        _boundary_paths = []
        if _bounds_geo is not None and len(_ev_pixels_sn) > 0:
            _boundary_paths = _build_paths(_bounds_geo)
            if _boundary_paths:
                _pts_sn = np.column_stack([
                    _ev_pixels_sn["longitude"].values,
                    _ev_pixels_sn["latitude"].values,
                ])
                _inside_sn = np.zeros(len(_pts_sn), dtype=bool)
                for _bp in _boundary_paths:
                    _inside_sn |= _bp.contains_points(_pts_sn)
                _ev_pixels_sn = _ev_pixels_sn[_inside_sn].reset_index(drop=True)

        # ── Mini-cards apercu (6 evenements) ─────────────────────────────────
        if _ev_summary is not None and len(_ev_summary) > 0 and len(_dates) > 0:
            _ncols = min(6, len(_dates))
            _mini_cols = st.columns(_ncols, gap="small")

            # Precip/anomaly max : pixels filtres aux frontieres Senegal (coherent fiche)
            _pmax_by_date = (
                _ev_pixels_sn[_ev_pixels_sn["precipitation_mm"] > 0]
                .groupby("event_date")["precipitation_mm"].max()
                .to_dict()
            )
            _amax_by_date = (
                _ev_pixels_sn.groupby("event_date")["anomaly_standardized"].max()
                .to_dict()
            )

            # CSS : bouton invisible positionne par-dessus chaque card
            st.markdown("""
            <style>
            div[data-testid="stVerticalBlock"]
              .element-container:has(.mini-ev-card) + div {
                margin-top: -108px !important;
                height: 108px !important;
            }
            div[data-testid="stVerticalBlock"]
              .element-container:has(.mini-ev-card) + div button {
                width: 100% !important;
                height: 108px !important;
                opacity: 0 !important;
                cursor: pointer !important;
                border: none !important;
                background: transparent !important;
                padding: 0 !important;
            }
            </style>
            """, unsafe_allow_html=True)

            for _i_m, (_col_m, _d) in enumerate(zip(_mini_cols, _dates)):
                _row_m = _ev_summary[_ev_summary["event_date"] == _d]
                _c0 = _get_crit0(_d)
                _fg, _bg = _CRIT_COLORS.get(_c0, (INDIGO, "rgba(79,70,229,0.13)"))
                _ph = _row_m.iloc[0]["season_phase"] if not _row_m.empty else ""
                _pmax = (
                    f"{_pmax_by_date[_d]:.0f}" if _d in _pmax_by_date
                    else (f"{_row_m.iloc[0]['precip_max']:.0f}" if not _row_m.empty else "-")
                )
                _amax = (
                    f"{_amax_by_date[_d]:.1f}" if _d in _amax_by_date
                    else (f"{_row_m.iloc[0]['anomaly_max']:.1f}" if not _row_m.empty else "-")
                )
                _is_sel = (_d == _sel_date)
                _border = f"2px solid {INDIGO}" if _is_sel else f"1px solid {BORDER}"
                _shadow = "box-shadow:0 3px 12px rgba(79,70,229,0.18);" if _is_sel else ""
                _bg_card = "rgba(79,70,229,0.12)" if _is_sel else CARD
                _ph_short = (
                    "P1 Debut" if "debut" in _ph
                    else "P2 Pleine" if "pleine" in _ph
                    else "P3 Fin" if "fin" in _ph
                    else _ph
                )
                with _col_m:
                    st.markdown(f"""
                    <div class="mini-ev-card" style="background:{_bg_card};border:{_border};
                                border-radius:10px;padding:10px 10px 9px 10px;{_shadow}
                                cursor:pointer;transition:box-shadow 0.15s;">
                      <div style="background:{_bg};border-radius:5px;padding:2px 6px;
                                  margin-bottom:7px;display:inline-block;max-width:100%;">
                        <span class="mini-ev-crit" style="font-size:0.69rem;font-weight:700;
                                     color:{_fg};white-space:nowrap;display:block;">
                          {_CRIT_FR.get(_c0, _c0)}</span>
                      </div>
                      <p style="margin:0;font-size:0.77rem;font-weight:700;
                                color:{TEXT};line-height:1.2">{_d}</p>
                      <p style="margin:3px 0 0 0;font-size:0.72rem;color:{MUTED}">
                        {_pmax} mm &nbsp;&middot;&nbsp; {_amax} &#963;
                      </p>
                      <p style="margin:4px 0 0 0;font-size:0.69rem;color:{MUTED}">{_ph_short}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button("", key=f"ev_mini_{_i_m}", use_container_width=True):
                        st.session_state["carto_nav_idx"] = _i_m
                        st.rerun()

        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

        # _ev_pixels_sn est deja filtre aux frontieres Senegal (pre-calcule plus haut)
        _ev_sel = _ev_pixels_sn[_ev_pixels_sn["event_date"] == _sel_date].copy()
        _ev_sel = _ev_sel[_ev_sel["precipitation_mm"] > 0].reset_index(drop=True)

        # -- Jointure spatiale : departement pour chaque pixel --------------------
        _depts_ev = [""] * len(_ev_sel)
        if _dept_geo is not None and len(_ev_sel) > 0:
            _pts_all = np.column_stack([
                _ev_sel["longitude"].values,
                _ev_sel["latitude"].values,
            ])
            for _feat in _dept_geo.get("features", []):
                _dname = _feat.get("properties", {}).get("NAME_2", "")
                _geom  = _feat.get("geometry", {})
                _gtype = _geom.get("type", "")
                _coords = _geom.get("coordinates", [])
                _polys  = []
                if _gtype == "MultiPolygon":
                    for _poly in _coords:
                        if _poly and _poly[0]:
                            _polys.append(_MplPath(np.array(_poly[0])))
                elif _gtype == "Polygon":
                    if _coords and _coords[0]:
                        _polys.append(_MplPath(np.array(_coords[0])))
                for _pp in _polys:
                    _mask = _pp.contains_points(_pts_all)
                    for _idx in np.where(_mask)[0]:
                        _depts_ev[_idx] = _dname

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        # -- Infrastructure cartes ------------------------------------------------
        _margin = dict(l=0, r=0, t=28, b=0)

        def _make_boundary_trace(geojson, width=1.4, color="rgba(30,30,30,0.70)"):
            lons_b, lats_b = [], []
            for feat in geojson.get("features", []):
                geom   = feat.get("geometry", {})
                gtype  = geom.get("type", "")
                coords = geom.get("coordinates", [])
                rings  = []
                if gtype == "Polygon":
                    rings = coords
                elif gtype == "MultiPolygon":
                    for poly in coords:
                        rings.extend(poly)
                for ring in rings:
                    for x, y in ring:
                        lons_b.append(x)
                        lats_b.append(y)
                    lons_b.append(None)
                    lats_b.append(None)
            return go.Scattermapbox(
                lat=lats_b, lon=lons_b,
                mode="lines",
                line=dict(width=width, color=color),
                hoverinfo="none",
                showlegend=False,
            )

        def _make_hover_trace(lats, lons, texts):
            return go.Scattermapbox(
                lat=lats, lon=lons,
                mode="markers",
                marker=dict(size=10, opacity=0, color="rgba(0,0,0,0)"),
                text=texts,
                hovertemplate="%{text}<extra></extra>",
                showlegend=False,
            )

        _lats_ev  = _ev_sel["latitude"].tolist()
        _lons_ev  = _ev_sel["longitude"].tolist()
        _prec_ev  = _ev_sel["precipitation_mm"].tolist()
        _anom_ev  = _ev_sel["anomaly_standardized"].tolist()

        _hover_txt = [
            f"<b>{r['precipitation_mm']:.1f} mm</b> &nbsp;|&nbsp; "
            f"{r['anomaly_standardized']:.1f}<br>"
            f"Region : {r['region']}<br>"
            f"Categorie : {r['intensity_category']}"
            for _, r in _ev_sel.iterrows()
        ]

        # Centroide pondere par precipitation depuis _ev_sel
        # (pixels deja filtres aux frontieres Senegal + precip > 0 => coherent avec la carte)
        _ctr_lat, _ctr_lon = 14.5, -14.5
        if len(_ev_sel) > 0:
            _w     = _ev_sel["precipitation_mm"].values
            _w_sum = float(_w.sum())
            if _w_sum > 0:
                _ctr_lat = float(np.average(_ev_sel["latitude"].values,  weights=_w))
                _ctr_lon = float(np.average(_ev_sel["longitude"].values, weights=_w))

        _title_map = (
            f"<b>{_sel_date}</b> · "
            f"{_fmt_event(_sel_date).split('[')[-1].replace(']','').strip()}"
        )

        _density_radius = 20

        _regs_ev = _ev_sel["region"].tolist()
        _cats_ev = _ev_sel["intensity_category"].tolist()

        _cd_prec = [
            [f"{a:+.1f}", rg, ct, la, lo, dp, f"{p:.1f}"]
            for a, rg, ct, la, lo, dp, p
            in zip(_anom_ev, _regs_ev, _cats_ev, _lats_ev, _lons_ev, _depts_ev, _prec_ev)
        ]
        _cd_anom = [
            [f"{p:.1f}", rg, ct, la, lo, dp, f"{a:+.1f}"]
            for p, rg, ct, la, lo, dp, a
            in zip(_prec_ev, _regs_ev, _cats_ev, _lats_ev, _lons_ev, _depts_ev, _anom_ev)
        ]

        _p_max = float(np.percentile(_prec_ev, 99)) if _prec_ev else 50.0
        _p_min = max(0.0, float(np.percentile(_prec_ev, 1)) if _prec_ev else 0.0)
        _a_abs = max(
            abs(float(np.percentile(_anom_ev, 2))) if _anom_ev else 3.0,
            abs(float(np.percentile(_anom_ev, 98))) if _anom_ev else 3.0,
            2.5,
        )

        _CS_PREC = [
            [0.00, "#FFFFFF"], [0.04, "#FFF9C4"], [0.14, "#FFEB3B"],
            [0.30, "#FF9800"], [0.55, "#F44336"], [0.80, "#9C27B0"],
            [1.00, "#1A237E"],
        ]

        _CS_ANOM = [
            [0.00, "#053061"], [0.12, "#2166AC"], [0.26, "#74ADD1"],
            [0.42, "#D1E5F0"], [0.50, "#FFFFFF"],
            [0.58, "#FDDBC7"], [0.74, "#F4A582"],
            [0.88, "#D6604D"], [1.00, "#67001F"],
        ]

        _bmap = dict(
            style="carto-positron",
            center=dict(lat=_ctr_lat, lon=_ctr_lon),
            zoom=6.2,
        )
        _mgn = dict(l=0, r=0, t=0, b=0)

        # Pixel avec precipitation maximale
        _mx_idx = int(np.argmax(_prec_ev)) if _prec_ev else None
        _mx_lat = _lats_ev[_mx_idx] if _mx_idx is not None else None
        _mx_lon = _lons_ev[_mx_idx] if _mx_idx is not None else None
        _mx_val = _prec_ev[_mx_idx] if _mx_idx is not None else None

        def _add_overlays(fig):
            # Frontieres departements (trait fin)
            if _dept_geo is not None:
                fig.add_trace(_make_boundary_trace(
                    _dept_geo, width=0.6, color="rgba(30,41,59,0.28)"
                ))
            # Contour national Senegal (trait epais)
            if _bounds_geo is not None:
                fig.add_trace(_make_boundary_trace(
                    _bounds_geo, width=2.0, color="rgba(15,23,42,0.72)"
                ))
            # Marqueur pixel maximum : halo + point central
            if _mx_lat is not None:
                fig.add_trace(go.Scattermapbox(
                    lat=[_mx_lat], lon=[_mx_lon], mode="markers",
                    marker=dict(size=26, color="#F59E0B", opacity=0.18),
                    hoverinfo="skip", showlegend=False,
                ))
                fig.add_trace(go.Scattermapbox(
                    lat=[_mx_lat], lon=[_mx_lon], mode="markers",
                    marker=dict(size=16, color="#FBBF24", opacity=0.85),
                    hoverinfo="skip", showlegend=False,
                ))
                fig.add_trace(go.Scattermapbox(
                    lat=[_mx_lat], lon=[_mx_lon], mode="markers",
                    marker=dict(size=7, color="#FFFFFF", opacity=1.0),
                    hovertemplate=(
                        f"<b>Maximum : {_mx_val:.1f} mm</b><br>"
                        f"{_mx_lat:.3f}N  {abs(_mx_lon):.3f}W"
                        "<extra></extra>"
                    ),
                    showlegend=False,
                ))
            # Centroide : effet radar 3 anneaux
            fig.add_trace(go.Scattermapbox(
                lat=[_ctr_lat], lon=[_ctr_lon], mode="markers",
                marker=dict(size=34, color=ROSE, opacity=0.10),
                hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scattermapbox(
                lat=[_ctr_lat], lon=[_ctr_lon], mode="markers",
                marker=dict(size=22, color=ROSE, opacity=0.22),
                hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scattermapbox(
                lat=[_ctr_lat], lon=[_ctr_lon], mode="markers",
                marker=dict(size=13, color="white", opacity=0.92),
                hoverinfo="skip", showlegend=False,
            ))
            fig.add_trace(go.Scattermapbox(
                lat=[_ctr_lat], lon=[_ctr_lon], mode="markers",
                marker=dict(size=8, color=ROSE, opacity=1.0),
                hovertemplate=(
                    "<b>Centre de gravite</b><br>"
                    f"{_ctr_lat:.3f}N  {abs(_ctr_lon):.3f}W"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

        _mmap1, _minfo = st.columns([5, 4], gap="medium")

        # ── Cartes : Precipitations + Anomalie (tabs) ──────────────────────────
        with _mmap1:
            _c0_hdr = _get_crit0(_sel_date)
            _fg_hdr, _ = _CRIT_COLORS.get(_c0_hdr, (INDIGO, ""))
            _crit_hdr  = _CRIT_FR.get(_c0_hdr, "")
            _mx_lbl = f"{_mx_val:.0f} mm" if _mx_val is not None else "-"

            # Variable pixel sizes proportional to precipitation intensity
            _szs = [
                max(6, min(18, 6 + 12 * (p - _p_min) / max(_p_max - _p_min, 1.0)))
                for p in _prec_ev
            ]

            _tab_p, _tab_a = st.tabs(["☁ Précipitations (mm)", "⚡ Anomalies (σ)"])

            # --- Onglet 1 : Precipitations ---
            with _tab_p:
                st.markdown(f"""
                <div style="display:flex;align-items:center;justify-content:space-between;
                            margin-bottom:6px;flex-wrap:wrap;gap:6px;">
                  <span class="pnl-ttl" style="margin:0">&#127783;&nbsp;
                    Précipitation (mm) &mdash;
                    <b style="color:{_fg_hdr}">{_sel_date}</b>
                    <span style="font-weight:400;color:{MUTED};font-size:0.72rem">
                      &nbsp;{_crit_hdr}</span></span>
                  <span style="display:flex;gap:10px;font-size:0.68rem;color:{MUTED};
                               align-items:center;flex-wrap:wrap;">
                    <span>
                      <span style="display:inline-block;width:10px;height:10px;
                                   border-radius:50%;background:{ROSE};
                                   vertical-align:middle;margin-right:3px;"></span>
                      Centre de gravité</span>
                    <span>
                      <span style="display:inline-block;width:10px;height:10px;
                                   border-radius:50%;background:#FBBF24;
                                   vertical-align:middle;margin-right:3px;"></span>
                      Maximum ({_mx_lbl})</span>
                  </span>
                </div>
                """, unsafe_allow_html=True)

                with st.spinner("Chargement..."):
                    _fig1 = go.Figure()
                    _fig1.add_trace(go.Densitymapbox(
                        lat=_lats_ev, lon=_lons_ev,
                        z=_prec_ev,
                        radius=18,
                        colorscale=_CS_PREC,
                        zmin=_p_min, zmax=_p_max,
                        opacity=0.22,
                        showscale=False,
                        hoverinfo="skip",
                    ))
                    _fig1.add_trace(go.Scattermapbox(
                        lat=_lats_ev, lon=_lons_ev,
                        mode="markers",
                        marker=dict(
                            size=_szs,
                            color=_prec_ev,
                            colorscale=_CS_PREC,
                            cmin=_p_min, cmax=_p_max,
                            opacity=0.88,
                            colorbar=dict(
                                title=dict(text="mm",
                                           font=dict(size=11, color=MUTED)),
                                thickness=14, len=0.72, x=1.01, y=0.5,
                                tickfont=dict(size=10, color=MUTED),
                                outlinewidth=0,
                                bgcolor="rgba(255,255,255,0.80)",
                                borderwidth=0, nticks=6,
                            ),
                        ),
                        customdata=_cd_prec,
                        hovertemplate=(
                            "<b>%{customdata[6]} mm</b>"
                            " | %{customdata[0]} σ<br>"
                            "Département : <b>%{customdata[5]}</b><br>"
                            "Région : %{customdata[1]}<br>"
                            "Catégorie : <b>%{customdata[2]}</b>"
                            "<extra></extra>"
                        ),
                        showlegend=False,
                    ))
                    _add_overlays(_fig1)
                    _fig1.update_layout(
                        mapbox=_bmap, margin=_mgn, height=440,
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(
                        _fig1, use_container_width=True,
                        config={
                            "displayModeBar": True,
                            "modeBarButtonsToRemove": [
                                "lasso2d", "select2d", "autoScale2d",
                                "hoverClosestMapbox",
                            ],
                            "displaylogo": False,
                            "toImageButtonOptions": {
                                "format": "png",
                                "filename": f"precip_{_sel_date}",
                            },
                        },
                    )

            # --- Onglet 2 : Anomalies ---
            with _tab_a:
                _anom_ext = max(
                    abs(float(np.percentile(_anom_ev, 2))),
                    abs(float(np.percentile(_anom_ev, 98))),
                    2.5,
                ) if _anom_ev else 3.0

                _szs_a = [
                    max(6, min(18, 6 + 12 * (abs(a) / max(_anom_ext, 0.1))))
                    for a in _anom_ev
                ]

                st.markdown(f"""
                <div style="display:flex;align-items:center;justify-content:space-between;
                            margin-bottom:6px;flex-wrap:wrap;gap:6px;">
                  <span class="pnl-ttl" style="margin:0">&#9889;&nbsp;
                    Anomalie standardisée (&sigma;) &mdash;
                    <b style="color:{_fg_hdr}">{_sel_date}</b>
                    <span style="font-weight:400;color:{MUTED};font-size:0.72rem">
                      &nbsp;{_crit_hdr}</span></span>
                  <span style="font-size:0.68rem;color:{MUTED};">
                    Écart à la normale climatologique</span>
                </div>
                """, unsafe_allow_html=True)

                with st.spinner("Chargement..."):
                    _fig2 = go.Figure()
                    _fig2.add_trace(go.Scattermapbox(
                        lat=_lats_ev, lon=_lons_ev,
                        mode="markers",
                        marker=dict(
                            size=_szs_a,
                            color=_anom_ev,
                            colorscale=_CS_ANOM,
                            cmin=-_anom_ext, cmax=_anom_ext,
                            opacity=0.88,
                            colorbar=dict(
                                title=dict(text="σ",
                                           font=dict(size=11, color=MUTED)),
                                thickness=14, len=0.72, x=1.01, y=0.5,
                                tickfont=dict(size=10, color=MUTED),
                                outlinewidth=0,
                                bgcolor="rgba(255,255,255,0.80)",
                                borderwidth=0, nticks=6,
                            ),
                        ),
                        customdata=_cd_anom,
                        hovertemplate=(
                            "<b>%{customdata[6]} σ</b>"
                            " | %{customdata[0]} mm<br>"
                            "Département : <b>%{customdata[5]}</b><br>"
                            "Région : %{customdata[1]}<br>"
                            "Catégorie : <b>%{customdata[2]}</b>"
                            "<extra></extra>"
                        ),
                        showlegend=False,
                    ))
                    _add_overlays(_fig2)
                    _fig2.update_layout(
                        mapbox=_bmap, margin=_mgn, height=440,
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(
                        _fig2, use_container_width=True,
                        config={
                            "displayModeBar": True,
                            "modeBarButtonsToRemove": [
                                "lasso2d", "select2d", "autoScale2d",
                                "hoverClosestMapbox",
                            ],
                            "displaylogo": False,
                            "toImageButtonOptions": {
                                "format": "png",
                                "filename": f"anom_{_sel_date}",
                            },
                        },
                    )

        # ── Panneau d'information de l'evenement ──────────────────────────────
        with _minfo:
            st.markdown(
                '<p class="pnl-ttl" style="margin-bottom:8px">'
                '&#128203; Fiche evenement</p>',
                unsafe_allow_html=True,
            )

            if len(_ev_sel) > 0:
                _reg_stats = (
                    _ev_sel.groupby("region")["precipitation_mm"]
                    .agg(max_p="max", mean_p="mean", n="count")
                    .sort_values("max_p", ascending=False)
                )
                _top_reg      = _reg_stats.index[0] if len(_reg_stats) else "-"
                _top_reg_max  = float(_reg_stats.iloc[0]["max_p"]) if len(_reg_stats) else 0
                _top_reg_mean = float(_reg_stats.iloc[0]["mean_p"]) if len(_reg_stats) else 0
            else:
                _top_reg, _top_reg_max, _top_reg_mean = "-", 0, 0

            if _ev_summary is not None:
                _row_inf = _ev_summary[_ev_summary["event_date"] == _sel_date]
                _ri = _row_inf.iloc[0] if not _row_inf.empty else None
            else:
                _ri = None

            def _sv(key, fmt=None, default="-"):
                if _ri is None:
                    return default
                v = _ri.get(key, None)
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return default
                return fmt.format(v) if fmt else str(v)

            # Stats calculees sur _ev_sel (deja filtre aux frontieres Senegal)
            # pour etre coherentes avec ce qui est affiche sur la carte
            if len(_ev_sel) > 0:
                _pmax_v    = f"{_ev_sel['precipitation_mm'].max():.1f}"
                _pmoy_v    = f"{_ev_sel['precipitation_mm'].mean():.1f}"
                _amax_v    = f"{_ev_sel['anomaly_standardized'].max():.1f}"
                _amoy_v    = f"{_ev_sel['anomaly_standardized'].mean():.1f}"
                _ext_n_v   = int((_ev_sel["anomaly_standardized"] > 2.0).sum())
                _ext_pct_v = _ext_n_v / len(_ev_sel) * 100
            else:
                _pmax_v    = _sv("precip_max",    "{:.1f}")
                _pmoy_v    = _sv("precip_mean",   "{:.1f}")
                _amax_v    = _sv("anomaly_max",   "{:.1f}")
                _amoy_v    = _sv("anomaly_mean",  "{:.1f}")
                _ext_pct_v = float(_sv("extreme_percentage", "{}", "0"))
            _mregion_v = _top_reg  # calculee depuis _ev_sel, coherent avec la carte
            _etype_v   = _sv("event_type")
            _extent_v  = _sv("spatial_extent")
            _ilevel_v  = _sv("intensity_level")
            _ph_raw    = _sv("season_phase", default="")
            _PHASE_FR2 = {
                "Phase_1_debut":  "Phase 1 &mdash; D&eacute;but (Mai-Juin)",
                "Phase_2_pleine": "Phase 2 &mdash; Pleine (Juil-Ao&ucirc;t)",
                "Phase_3_fin":    "Phase 3 &mdash; Fin (Sep-Oct)",
            }
            _ph_lbl  = _PHASE_FR2.get(_ph_raw, _ph_raw)
            _ph_clr  = PHASE_C.get(_ph_raw, MUTED)
            _c0_inf  = _get_crit0(_sel_date)
            _cr_fg2, _cr_bg2 = _CRIT_COLORS.get(_c0_inf, (INDIGO, "rgba(79,70,229,0.13)"))
            _cr_lbl2 = _CRIT_FR.get(_c0_inf, _c0_inf)

            def _pbar(pct, color, bg=BORDER):
                w = min(max(float(pct), 0), 100)
                return (
                    f'<div style="height:6px;background:{bg};border-radius:99px;'
                    f'margin-top:4px;overflow:hidden;">'
                    f'<div style="width:{w:.1f}%;height:100%;background:{color};'
                    f'border-radius:99px;"></div></div>'
                )

            def _mrow(label, value, unit="", color=TEXT):
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

            def _section(title, icon, color):
                return (
                    f'<div style="display:flex;align-items:center;gap:7px;'
                    f'margin:14px 0 6px 0;">'
                    f'<div style="width:3px;height:14px;background:{color};'
                    f'border-radius:2px;flex-shrink:0"></div>'
                    f'<span style="font-size:0.72rem;font-weight:700;color:{MUTED};'
                    f'text-transform:uppercase;letter-spacing:0.06em">'
                    f'{icon}&nbsp;{title}</span></div>'
                )

            _html_header = (
                f'<div style="border-bottom:3px solid {_cr_fg2};'
                f'padding:14px 16px 12px 16px;background:{_cr_bg2};">'
                f'<div style="display:flex;align-items:flex-start;'
                f'justify-content:space-between;gap:8px;">'
                f'<div>'
                f'<p style="margin:0 0 2px 0;font-size:0.72rem;font-weight:700;'
                f'color:{_cr_fg2};text-transform:uppercase;letter-spacing:0.07em">'
                f'{_cr_lbl2}</p>'
                f'<p style="margin:0 0 6px 0;font-size:1.05rem;font-weight:800;'
                f'color:{TEXT};line-height:1.2">{_sel_date}</p>'
                f'</div>'
                f'<span style="background:{CARD};color:{MUTED};font-size:0.72rem;'
                f'font-weight:600;border-radius:6px;padding:3px 9px;'
                f'white-space:nowrap;border:1px solid {BORDER}">{_etype_v}</span>'
                f'</div>'
                f'<span style="background:{_ph_clr}22;color:{_ph_clr};font-size:0.72rem;'
                f'font-weight:700;border-radius:6px;padding:3px 9px;display:inline-block">'
                f'{_ph_lbl}</span>'
                f'</div>'
            )
            _html_body = (
                f'<div style="padding:8px 16px 16px 16px;">'
                + _mrow("Pr&#233;cip. max", _pmax_v, "mm", BLUE)
                + _mrow("Pr&#233;cip. moyenne", _pmoy_v, "mm")
                + _mrow("Anomalie max", _amax_v, "&#963;", "#7C3AED")
                + _mrow("Anomalie moyenne", _amoy_v, "&#963;")
                + f'<div style="padding:7px 0 4px 0;border-bottom:1px solid {BORDER};">'
                + f'<div style="display:flex;justify-content:space-between;'
                + f'align-items:baseline;margin-bottom:3px;">'
                + f'<span style="font-size:0.75rem;color:{MUTED}">Couverture spatiale</span>'
                + f'<span style="font-size:0.85rem;font-weight:700;color:{AMBER}">{_ext_pct_v:.1f}%</span>'
                + f'</div>' + _pbar(_ext_pct_v, AMBER) + f'</div>'
                + _mrow("R&#233;gion principale", _mregion_v)
                + f'<div style="padding:5px 0;border-bottom:1px solid {BORDER};">'
                + f'<div style="display:flex;justify-content:space-between;'
                + f'align-items:baseline;margin-bottom:3px;">'
                + f'<span style="font-size:0.75rem;color:{MUTED}">R&#233;gion la plus intense</span>'
                + f'<span style="font-size:0.85rem;font-weight:700;color:{ROSE}">{_top_reg}</span>'
                + f'</div>'
                + f'<div style="font-size:0.72rem;color:{MUTED};">'
                + f'max {_top_reg_max:.1f} mm &nbsp;&#183;&nbsp; moy. {_top_reg_mean:.1f} mm</div>'
                + f'</div>'
                + _section("Classification", "&#127981;", EMERALD)
                + f'<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:5px;">'
                + f'<span style="background:{BG};color:{MUTED};font-size:0.72rem;'
                + f'font-weight:600;border-radius:6px;padding:3px 9px;'
                + f'border:1px solid {BORDER}">{_extent_v}</span>'
                + f'<span style="background:{BG};color:{MUTED};font-size:0.72rem;'
                + f'font-weight:600;border-radius:6px;padding:3px 9px;'
                + f'border:1px solid {BORDER}">{_ilevel_v}</span>'
                + f'</div>'
                + f'</div>'
            )
            _html_card = (
                f'<div style="background:{CARD};border:1px solid {BORDER};'
                f'border-radius:14px;overflow:hidden;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.05);">'
                + _html_header + _html_body +
                f'</div>'
            )
            st.html(_html_card)

    # ── Separateur section analyses ───────────────────────────────────────────
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:12px;margin:28px 0 18px 0;">
      <div style="height:2px;width:28px;background:linear-gradient(90deg,{INDIGO},{BLUE});
                  border-radius:99px;flex-shrink:0;"></div>
      <span style="font-size:0.70rem;font-weight:700;color:{MUTED};text-transform:uppercase;
                   letter-spacing:0.08em;white-space:nowrap">Analyse temporelle &amp; distribution</span>
      <div style="height:1px;flex:1;background:{BORDER};"></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Filtres ───────────────────────────────────────────────────────────────
    _yr_min  = int(df["year"].min())
    _yr_max  = int(df["year"].max())
    _ph_dflt = ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]

    # State pre-read: session state is updated before rerun, so badge is always current
    _yr_cur = st.session_state.get("evt_yr_range",   (_yr_min, _yr_max))
    _ph_cur = st.session_state.get("evt_phases_sel", _ph_dflt)
    _ph_cur = _ph_cur if _ph_cur else _ph_dflt

    _n_cur   = int(df[df["year"].between(*_yr_cur) & df["phase"].isin(_ph_cur)].shape[0])
    _pct_c   = 100.0 * _n_cur / len(df) if len(df) else 100.0
    _active  = (_yr_cur != (_yr_min, _yr_max)) or (set(_ph_cur) != set(_ph_dflt))
    _bdg_clr = ROSE  if _active else INDIGO
    _bdg_bg  = "rgba(244,63,94,0.10)"  if _active else "rgba(79,70,229,0.10)"
    _bot_bdr = f"2px solid {ROSE}"     if _active else f"1px solid {BORDER}"
    _pct_str = f"&nbsp;&middot;&nbsp;{_pct_c:.0f}%" if _active else ""

    _pills = "".join(
        f'<span style="font-size:0.67rem;font-weight:600;color:{PHASE_C.get(p, MUTED)};'
        f'background:{PHASE_C.get(p, MUTED)}1A;border-radius:6px;'
        f'padding:2px 8px;white-space:nowrap;">'
        f'{PHASE_L.get(p, p)}</span>'
        for p in _ph_cur
    )

    st.markdown(f"""
    <div style="background:{CARD};border:1px solid {BORDER};border-bottom:{_bot_bdr};
                border-radius:12px;padding:11px 16px 12px 16px;margin-bottom:3px;
                box-shadow:0 1px 3px rgba(0,0,0,0.04),0 2px 8px rgba(0,0,0,0.03);
                transition:border-bottom 0.2s;">
      <div style="display:flex;align-items:center;gap:9px;flex-wrap:wrap;">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
             stroke="{INDIGO}" stroke-width="2.5" stroke-linecap="round"
             stroke-linejoin="round" style="flex-shrink:0;opacity:.9">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
        </svg>
        <span style="font-size:0.63rem;font-weight:700;color:{MUTED};
                     text-transform:uppercase;letter-spacing:0.10em;">Filtres</span>
        <div style="width:1px;height:14px;background:{BORDER};flex-shrink:0;"></div>
        <span style="font-size:0.70rem;font-weight:500;color:{TEXT};white-space:nowrap;">
          {_yr_cur[0]}&nbsp;&ndash;&nbsp;{_yr_cur[1]}
        </span>
        <div style="display:flex;gap:4px;flex-wrap:wrap;">{_pills}</div>
        <div style="flex:1;min-width:16px;height:1px;background:{BORDER};"></div>
        <span style="font-size:0.70rem;font-weight:600;color:{_bdg_clr};
              background:{_bdg_bg};border-radius:20px;padding:3px 12px;white-space:nowrap;">
          {_n_cur:,}&nbsp;&eacute;v&eacute;nements{_pct_str}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    _fc1, _fc2, _fc_rst = st.columns([5, 4, 1], gap="small")
    with _fc1:
        _yr = st.slider(
            "Periode",
            min_value=_yr_min,
            max_value=_yr_max,
            value=(_yr_min, _yr_max),
            key="evt_yr_range",
        )
    with _fc2:
        _ph_sel = st.multiselect(
            "Phases",
            options=_ph_dflt,
            default=_ph_dflt,
            format_func=lambda x: PHASE_L[x],
            key="evt_phases_sel",
        )
    with _fc_rst:
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        if st.button(
            "Reset",
            key="evt_reset_btn",
            help="Reinitialiser les filtres",
            use_container_width=True,
            disabled=not _active,
        ):
            st.session_state.pop("evt_yr_range",   None)
            st.session_state.pop("evt_phases_sel", None)
            st.rerun()

    _ph_active = _ph_sel if _ph_sel else _ph_dflt
    dff        = df[df["year"].between(*_yr) & df["phase"].isin(_ph_active)].copy()
    n_total    = len(dff)
    year_range = _yr

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Graphique principal + Donut ───────────────────────────────────────────
    if is_mobile:
        lc, rc = st.container(), st.container()
    elif is_tablet:
        lc, rc = st.columns([2, 1], gap="medium")
    else:
        lc, rc = st.columns([2.4, 1], gap="medium")

    with lc:

        hh, hs = st.columns([3, 1])
        with hh:
            st.markdown(
                '<p class="pnl-ttl">Evolution annuelle des evenements extremes</p>'
                '<p class="pnl-sub">Nombre d\'evenements par annee · decompose par phase saisonniere</p>',
                unsafe_allow_html=True,
            )
        with hs:
            view = st.selectbox("vue", ["Empile", "Groupe", "Total"],
                                label_visibility="collapsed")

        by_yr_df   = dff.groupby("year").size().reset_index(name="n")
        avg_yr_n   = by_yr_df["n"].mean()
        max_yr_row = by_yr_df.loc[by_yr_df["n"].idxmax()]
        min_yr_row = by_yr_df.loc[by_yr_df["n"].idxmin()]
        slope      = np.polyfit(by_yr_df["year"], by_yr_df["n"], 1)[0]

        st.markdown(f"""
        <div class="chips">
          <div class="chip">Moy. annuelle &nbsp;<b>{avg_yr_n:.0f} evt/an</b></div>
          <div class="chip">Record &nbsp;<b>{int(max_yr_row['year'])} — {int(max_yr_row['n'])} evt</b></div>
          <div class="chip">Annee calme &nbsp;<b>{int(min_yr_row['year'])} — {int(min_yr_row['n'])} evt</b></div>
          <div class="chip">Tendance &nbsp;<b>{"+" if slope>=0 else ""}{slope:.2f} evt/an</b></div>
        </div>
        """, unsafe_allow_html=True)

        by_yp = dff.groupby(["year", "phase"]).size().reset_index(name="n")
        fig   = go.Figure()

        if view == "Total":
            tot = by_yp.groupby("year")["n"].sum().reset_index()
            fig.add_trace(go.Bar(
                x=tot["year"], y=tot["n"],
                marker_color=INDIGO, marker_line_width=0,
                hovertemplate="<b>%{x}</b> : %{y} evenements<extra></extra>",
                showlegend=False,
            ))
        else:
            bmode = "stack" if view == "Empile" else "group"
            for ph in ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"]:
                sub = by_yp[by_yp["phase"] == ph]
                fig.add_trace(go.Bar(
                    x=sub["year"], y=sub["n"],
                    name=PHASE_L[ph],
                    marker_color=PHASE_C[ph], marker_line_width=0,
                    hovertemplate=f"<b>{PHASE_L[ph]}</b> · %{{x}}: %{{y}} evt<extra></extra>",
                ))
            fig.update_layout(barmode=bmode)

        plotly_base(fig, h=220 if is_mobile else (260 if is_tablet else 295))
        fig.update_layout(
            bargap=0.2,
            legend=dict(font=dict(color=TEXT)),
        )
        _CHART_CFG = {
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d",
                                       "hoverCompareCartesian", "hoverClosestCartesian"],
            "toImageButtonOptions": {"format": "png", "scale": 2},
        }
        st.plotly_chart(fig, use_container_width=True, config=dict(_CHART_CFG,
            toImageButtonOptions={"format": "png", "scale": 2,
                                  "filename": "evolution_annuelle"}))

    # ── Donut ─────────────────────────────────────────────────────────────────
    with rc:
        st.markdown(
            '<p class="pnl-ttl">Repartition par Phase</p>'
            '<p class="pnl-sub">Distribution des 3 phases saisonnieres</p>',
            unsafe_allow_html=True,
        )

        ph_order = ["Phase_2_pleine", "Phase_3_fin", "Phase_1_debut"]
        ph_cnt   = {p: len(dff[dff["phase"] == p]) for p in ph_order}

        fig_d = go.Figure(go.Pie(
            labels=[PHASE_L[p] for p in ph_order],
            values=[ph_cnt[p]  for p in ph_order],
            hole=0.66,
            marker=dict(
                colors=[PHASE_C[p] for p in ph_order],
                line=dict(color="white", width=2.5),
            ),
            textinfo="none", sort=False,
            hovertemplate="<b>%{label}</b><br>%{value} evt (%{percent})<extra></extra>",
        ))
        fig_d.add_annotation(
            text=f"<b>{n_total}</b>", x=0.5, y=0.58,
            font=dict(size=22, color=TEXT, family="Inter"), showarrow=False,
        )
        fig_d.add_annotation(
            text="evenements", x=0.5, y=0.41,
            font=dict(size=10, color=MUTED, family="Inter"), showarrow=False,
        )
        fig_d.update_layout(
            height=210, showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_d, use_container_width=True, config=dict(_CHART_CFG,
            toImageButtonOptions={"format": "png", "scale": 2,
                                  "filename": "repartition_phases"}))

        for ph in ph_order:
            n   = ph_cnt[ph]
            pct = 100 * n / n_total if n_total else 0
            st.markdown(f"""
            <div class="leg-row">
              <div class="leg-dot" style="background:{PHASE_C[ph]}"></div>
              <span class="leg-lbl">{PHASE_L[ph]}</span>
              <span class="leg-pct">{pct:.0f}%</span>
              <b class="leg-val">{n}</b>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── Ligne basse ────────────────────────────────────────────────────────────
    if is_mobile:
        bc1, bc2 = st.container(), st.container()
    else:
        bc1, bc2 = st.columns(2, gap="medium")

    with bc1:
        st.markdown(
            '<p class="pnl-ttl">Distribution mensuelle</p>'
            '<p class="pnl-sub">Nombre d\'&eacute;v&eacute;nements par ann&eacute;e et par mois</p>',
            unsafe_allow_html=True,
        )
        STUDIED_MONTHS = {5:"Mai", 6:"Jun", 7:"Jul", 8:"Aou", 9:"Sep", 10:"Oct"}
        MONTH_COLORS = {
            "Mai": "#7DD3FC", "Jun": "#0EA5E9",
            "Jul": "#818CF8", "Aou": "#4F46E5",
            "Sep": "#FCD34D", "Oct": "#F59E0B",
        }

        pivot_m = (
            dff.groupby(["year", "month"]).size()
            .reset_index(name="n")
            .pivot(index="year", columns="month", values="n")
            .reindex(columns=list(STUDIED_MONTHS.keys()))
            .fillna(0)
            .astype(int)
        )
        pivot_m.columns = [STUDIED_MONTHS[m] for m in pivot_m.columns]

        fig_m = go.Figure()
        for mname in pivot_m.columns:
            fig_m.add_trace(go.Bar(
                x=pivot_m.index.tolist(),
                y=pivot_m[mname].tolist(),
                name=mname,
                marker_color=MONTH_COLORS[mname],
                marker_line_width=0,
                hovertemplate=f"<b>{mname}</b> · %{{x}} : %{{y}} evt<extra></extra>",
            ))
        plotly_base(fig_m, h=300 if is_mobile else 340)
        fig_m.update_layout(
            barmode="group",
            bargap=0.15,
            bargroupgap=0.05,
            margin=dict(l=2, r=2, t=10, b=40),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.01,
                xanchor="left", x=0,
                font=dict(size=10, color=TEXT),
                itemwidth=30,
            ),
            xaxis=dict(tickfont=dict(size=10, color=TEXT), dtick=5, automargin=True),
            yaxis=dict(tickfont=dict(size=10, color=MUTED)),
        )
        st.plotly_chart(fig_m, use_container_width=True, config=dict(_CHART_CFG,
            toImageButtonOptions={"format": "png", "scale": 2,
                                  "filename": "distribution_mensuelle"}))

    with bc2:
        st.markdown(
            '<p class="pnl-ttl">Top R&eacute;gions Touch&eacute;es</p>'
            '<p class="pnl-sub">Classement des 8 premi&egrave;res r&eacute;gions'
            ' &middot; sparkline tendance</p>',
            unsafe_allow_html=True,
        )
        top = (dff["centroid_region"]
               .value_counts().head(8)
               .reset_index()
               .rename(columns={"centroid_region": "region", "count": "n"}))
        max_n = top["n"].max()
        GRAD  = ["#4F46E5","#6366F1","#818CF8","#A5B4FC",
                 "#C7D2FE","#DDE3FD","#EEF2FF","#F5F3FF"]

        _rg_yr = (
            dff.groupby(["centroid_region", "year"])
            .size()
            .reset_index(name="n_yr")
        )
        _rg_allyrs = list(range(max(year_range[0], year_range[1] - 9),
                                year_range[1] + 1))

        for i, row in top.iterrows():
            bar_w = 100 * row["n"] / max_n
            pct   = 100 * row["n"] / n_total
            _rg_sub = _rg_yr[_rg_yr["centroid_region"] == row["region"]]
            _rg_sp  = [
                int(_rg_sub[_rg_sub["year"] == y]["n_yr"].values[0])
                if y in _rg_sub["year"].values else 0
                for y in _rg_allyrs
            ]
            _sp_svg = svg_spark(_rg_sp, w=60, h=22, color=GRAD[min(i, 7)])
            st.markdown(f"""
            <div class="rg-row" style="align-items:center;">
              <span class="rg-rk">#{i+1}</span>
              <span class="rg-nm">{row['region']}</span>
              <div style="flex-shrink:0;width:60px;opacity:0.85">{_sp_svg}</div>
              <div class="rg-bg" style="margin-left:6px;">
                <div class="rg-bar"
                     style="width:{bar_w:.0f}%;background:{GRAD[min(i,7)]}"></div>
              </div>
              <span class="rg-n">{row['n']}</span>
              <span class="rg-pct">{pct:.1f}%</span>
            </div>
            """, unsafe_allow_html=True)
