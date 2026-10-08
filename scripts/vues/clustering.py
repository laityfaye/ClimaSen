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
import admin_gate
from dashboard_utils import (
    INDIGO, BLUE, EMERALD, AMBER, ROSE, PHASE_C, BASE, nb,
    load_clustering, load_cluster_pixels, load_dept_geojson,
    load_sst_centroid, _get_region_grid, _apply_geo_traces,
)

# Hierarchie etats oceaniques -> configurations (veille/etats.py): facultative,
# la page reste utilisable sans les sorties du script 24.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    from veille import etats as _etats
except Exception:                                 # noqa: BLE001
    _etats = None


def _ligne_etat(hier, cid, muted, text):
    """Ligne 'État : La Nina (91 %)' d'une carte de cluster (vide sans hierarchie)."""
    if not hier or int(cid) not in hier["clusters"]:
        return ""
    c = hier["clusters"][int(cid)]
    coul = next((e["couleur"] for e in hier["etats"] if e["nom"] == c["etat"]), muted)
    return (f'<p style="font-size:0.72rem;color:{muted};margin:6px 0 0 0;">État&nbsp;: '
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background:{coul};margin-right:4px;"></span>'
            f'<b style="color:{text};">{c["etat"]}</b> ({int(round(100 * c["part"]))} %)</p>')


# En cache : ~3 s par affichage sinon (import scipy + V de Cramer, recette
# 29/09/2026). La page Pipeline vide st.cache_data apres un recalcul.
@st.cache_data(show_spinner=False)
def _hierarchie(phase, events):
    if _etats is None:
        return None
    try:
        return _etats.hierarchie(phase, evenements=events[["cluster", "year", "phase"]])
    except Exception:                             # noqa: BLE001
        return None


# ─── Donnees des cartes, en cache (page a 17 s, audit 08/10/2026) ────────────
# Plotly valide les listes Python point par point (~3,5 s pour les 61 748
# points des contours) ; les tableaux NumPy passent d'un bloc. NaN = coupure
# de ligne entre deux anneaux.
@st.cache_data(show_spinner=False)
def _contours_departements():
    geo = load_dept_geojson()
    if geo is None:
        return None
    from shapely.geometry import shape
    lo, la = [], []
    for feat in geo.get("features", []):
        # ~0,002 deg (200 m) : invisible a l'echelle du pays, 5 a 10 fois
        # moins de points envoyes au navigateur.
        geom = shape(feat["geometry"]).simplify(0.002, preserve_topology=True)
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            for ring in [poly.exterior, *poly.interiors]:
                x, y = ring.coords.xy
                lo.extend(x); lo.append(np.nan)
                la.extend(y); la.append(np.nan)
    return np.array(lo, dtype=float), np.array(la, dtype=float)


@st.cache_data(show_spinner=False)
def _composite_cluster(phase, cluster):
    """Composite des pixels d'un cluster dans les frontieres du Senegal.

    Retourne (statut, donnees) : statut 'aucune_donnee', 'phase_vide',
    'cluster_vide' ou 'ok'.
    """
    px_all = load_cluster_pixels()
    if px_all is None or len(px_all) == 0:
        return "aucune_donnee", None
    px_ph = px_all[px_all["phase"] == phase]
    if len(px_ph) == 0:
        return "phase_vide", None
    px_c = px_ph[px_ph["cluster"] == cluster]

    bounds_path = BASE / "data/geographic/senegal_boundaries.geojson"
    if bounds_path.exists() and len(px_c) > 0:
        import json as _json_cl
        from matplotlib.path import Path as _MplPathCl
        with open(str(bounds_path), "r", encoding="utf-8") as fh:
            bounds_geo = _json_cl.load(fh)
        paths = []
        for feat in bounds_geo.get("features", []):
            geom = feat.get("geometry", {})
            gtype, coords = geom.get("type", ""), geom.get("coordinates", [])
            if gtype == "MultiPolygon":
                paths += [_MplPathCl(np.array(p[0])) for p in coords if p and p[0]]
            elif gtype == "Polygon" and coords and coords[0]:
                paths.append(_MplPathCl(np.array(coords[0])))
        if paths:
            pts = np.column_stack([px_c["longitude"].values, px_c["latitude"].values])
            ins = np.zeros(len(pts), dtype=bool)
            for p in paths:
                ins |= p.contains_points(pts)
            px_c = px_c[ins]

    px_c = px_c[px_c["precipitation_mm"] > 0].reset_index(drop=True)
    if len(px_c) == 0:
        return "cluster_vide", None

    comp = (
        px_c.groupby(["latitude", "longitude"], as_index=False)
        .agg(
            precipitation_mm=("precipitation_mm", "mean"),
            anomaly_standardized=("anomaly_standardized", "mean"),
            region=("region", "first"),
        )
    )
    prec = comp["precipitation_mm"].to_numpy(dtype=float)
    lats = comp["latitude"].to_numpy(dtype=float)
    lons = comp["longitude"].to_numpy(dtype=float)
    w_sum = float(prec.sum())
    if w_sum > 0:
        ctr_lat = float(np.average(lats, weights=prec))
        ctr_lon = float(np.average(lons, weights=prec))
    else:
        ctr_lat, ctr_lon = float(lats.mean()), float(lons.mean())
    # Infobulles pre-formatees, en chaines de largeur fixe (copie memoire
    # directe, contrairement a une liste de listes).
    custom = np.column_stack([
        [nb(a, "+.1f") for a in comp["anomaly_standardized"]],
        comp["region"].astype(str).to_numpy(),
        [nb(p, ".1f") for p in prec],
    ]).astype(str)
    reg_stats = (
        px_c.groupby("region")["precipitation_mm"]
        .agg(max_p="max", mean_p="mean", n_px="count")
        .sort_values("mean_p", ascending=False)
        .head(6)
    )
    return "ok", {
        "lats": lats, "lons": lons, "prec": prec, "custom": custom,
        "p_min": max(0.0, float(np.percentile(prec, 1))),
        "p_max": float(np.percentile(prec, 99)),
        "ctr_lat": ctr_lat, "ctr_lon": ctr_lon, "reg_stats": reg_stats,
    }


# Largeur maximale d'une image Streamlit (MAXIMUM_CONTENT_WIDTH) : au-dela,
# st.image redimensionne et re-encode le PNG a chaque affichage (~1 s et
# ~2 Mo envoyes pour la figure de 2422 px du script 14).
_LARGEUR_IMAGE = 1460


@st.cache_data(show_spinner=False)
def _image_publication(chemin, mtime):
    """Figure du script 14 reduite a la largeur d'affichage, en JPEG."""
    import io
    from PIL import Image
    im = Image.open(chemin)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        fond = Image.new("RGB", im.size, (255, 255, 255))
        fond.paste(im, mask=im.split()[-1])
        im = fond
    if im.width > _LARGEUR_IMAGE:
        im = im.resize((_LARGEUR_IMAGE, round(im.height * _LARGEUR_IMAGE / im.width)),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()


PHASE_LABELS_CL = {
    "Phase_1_debut":  "Début saison  (Mai-Jun)",
    "Phase_2_pleine": "Pleine saison (Jul-Août)",
    "Phase_3_fin":    "Fin saison    (Sep-Oct)",
    "All_phases":     "Toutes phases confondues",
}


def run(BG, CARD, TEXT, MUTED, BORDER, dff, df, year_range, phases_sel,
        is_mobile=False, is_tablet=False, **kw):

    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div class="pg-hdr">
      <div>
        <h1 class="pg-ttl">Clustering KMeans SST</h1>
        <p class="pg-sub">Configurations océaniques du jour de chaque événement extrême · choix du nombre de configurations</p>
      </div>
    </div>""", unsafe_allow_html=True)

    with st.spinner("Chargement des données de clustering..."):
        clust_data = load_clustering()

    if not clust_data:
        st.warning("Données de clustering non disponibles.")
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

    # Relance = execution d'un script sur le serveur : administrateur seul.
    if not admin_gate.est_admin():
        st.session_state["show_cluster_rerun"] = False
    btn_label = (
        "Masquer le panneau" if st.session_state["show_cluster_rerun"]
        else "Relancer le clustering avec un K personnalise"
    )
    if admin_gate.est_admin() and st.button(btn_label, key="btn_cluster_rerun"):
        st.session_state["show_cluster_rerun"] = not st.session_state["show_cluster_rerun"]
        st.session_state["cluster_result"] = None
        st.rerun()

    if st.session_state["show_cluster_rerun"]:
        st.markdown(
            f'<p style="font-size:0.78rem;color:{MUTED};margin:0 0 12px 0;">'
            "Definissez le nombre de clusters K pour chaque phase, puis lancez le script. "
            "Les résultats seront rechargés automatiquement.</p>",
            unsafe_allow_html=True,
        )

        def _current_k(ph):
            d = clust_data.get(ph, {})
            m = d.get("metrics", {})
            return int(m.get("optimal_k", m.get("k_elbow", 6)) or 6)

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            k_p1 = st.number_input(
                "Phase 1 - Début (Mai-Jun)", min_value=2, max_value=15,
                value=_current_k("Phase_1_debut"), step=1, key="ck_p1",
            )
        with col_k2:
            k_p2 = st.number_input(
                "Phase 2 - Pleine (Jul-Août)", min_value=2, max_value=15,
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
            st.success("Clustering terminé avec succès ! Les résultats affichés sont mis à jour.")
            if st.button("Fermer ce message", key="btn_reload_cl"):
                st.session_state["cluster_result"] = None
                st.rerun()
        elif st.session_state["cluster_result"] == "error":
            st.error("Le script a rencontre une erreur.")
            st.code(st.session_state["cluster_stderr"] or "Pas de message d'erreur.")
        elif st.session_state["cluster_result"] == "timeout":
            st.error("Timeout depasse (30 min). Le calcul est peut-etre trop long.")

        if run_clicked and admin_gate.exiger_admin():
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
    sil_str  = f"{nb(sil_best, '.3f')}" if sil_best is not None else "-"
    n_clust  = chars["cluster"].nunique()

    # Icones Material Symbols (police chargee par dashboard.py), dans le carre
    # teinte .kpi-icon des autres pages, a la place des emojis.
    kpi_items = [
        ("rainy",        BLUE,    "Événements",     str(n_ev),   "cette phase"),
        ("tune",         INDIGO,  "k retenu",       str(k_opt),  "coude + interprétabilité"),
        ("monitoring",   EMERALD, "Silhouette max", sil_str,     f"k={k_sil}"),
        ("bubble_chart", AMBER,   "Clusters",       str(n_clust), "dans ce graphe"),
    ]
    # Les regles globales de dashboard.py ("[data-testid=stApp] span", div...)
    # forcent le texte en blanc avec !important, et Streamlit retire un color
    # !important en ligne : une classe par icone, classes repetees pour
    # l'emporter en specificite.
    st.markdown('<style>' + ''.join(
        f'[data-testid="stApp"] .kpi-clu .kpi-icon span.ic-clu-{i}.ic-clu-{i}.ic-clu-{i}'
        f'{{color:{coul} !important;-webkit-text-fill-color:{coul} !important;}}'
        for i, (_ico, coul, *_r) in enumerate(kpi_items)) + '</style>',
        unsafe_allow_html=True)
    cols_kpi = st.columns(4)
    for i_kpi, (col, (ico, coul, label, val, sub)) in enumerate(zip(cols_kpi, kpi_items)):
        with col:
            st.markdown(
                # kpi-clu : reperee par le CSS telephone (grille 2x2)
                f'<div class="kpi-clu" style="background:{CARD};border:1px solid {BORDER};border-radius:14px;'
                f'padding:18px 20px;">'
                f'<div class="kpi-icon" style="background:{coul}22;color:{coul};margin-bottom:0;">'
                f'<span class="material-symbols-rounded ic-clu-{i_kpi}" translate="no" '
                f'style="font-size:1.3rem;">{ico}</span></div>'
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
                annotation_text=f"k={k_opt} (retenu)",
                annotation_font_color=ROSE, annotation_position="top right",
            )
        fig_el.update_layout(
            title=dict(text="Courbe d'inertie (méthode du coude)",
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
            legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center",
                        traceorder="normal", font=dict(color=TEXT, size=11),
                        title=dict(text="")),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=10, t=44, b=10), height=300,
        )
        st.plotly_chart(fig_si, use_container_width=True, key="cl_silhouette")

    # Revue 27/09/2026 (point 03): les courbes ne designent pas un k optimal.
    sil_k = dict(zip(k_range, silhouettes)) if k_range and silhouettes else {}
    sil_retenu = sil_k.get(k_opt)
    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
        f'padding:12px 16px;margin:2px 0 14px 0;font-size:0.78rem;color:{TEXT};line-height:1.55;">'
        f'<b>Comment k a été choisi.</b> La courbe d&#39;inertie n&#39;a pas de coude net et la '
        f'silhouette augmente avec k (maximum {sil_str} a k = {k_sil}) : aucune valeur de k '
        f'n&#39;est statistiquement optimale, et des silhouettes inférieures à 0,2 indiquent des '
        f'groupes faiblement separes. k = {k_opt}'
        + (f' (silhouette {nb(sil_retenu, ".3f")})' if isinstance(sil_retenu, (int, float)) else '') +
        f' est un choix d&#39;<b>interprétabilité</b> : assez de configurations pour distinguer '
        f'les grands états océaniques, des effectifs suffisants par cluster pour des composites '
        f'lisibles. Les clusters sont a lire comme une typologie descriptive, pas comme des '
        f'regimes nettement separes ; la stabilite est controlee par l&#39;analyse saisonnière '
        f'(script 24, états océaniques ci-dessous).</div>',
        unsafe_allow_html=True)

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
            "Nb événements":       "n_events",
            "Precip max moy (mm)": "mean_max_precip",
            "Couverture (%)":      "mean_coverage_percent",
            "Anomalie max moy":    "mean_max_anomaly",
        }
        sel_metric = st.selectbox(
            "Métrique", options=list(metrics_bar.keys()),
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
        # Etiquette placee du cote oppose au voisin le plus proche (evite C0 sur C3).
        _nx = chars_s["mean_coverage_percent"].to_numpy(dtype=float)
        _ny = chars_s["mean_max_precip"].to_numpy(dtype=float)
        _nx = (_nx - _nx.min()) / (np.ptp(_nx) or 1.0)
        _ny = (_ny - _ny.min()) / (np.ptp(_ny) or 1.0)

        def _pos_etiquette(i):
            if len(_nx) < 2:
                return "top center"
            d = np.hypot(_nx - _nx[i], _ny - _ny[i])
            d[i] = np.inf
            j = int(np.argmin(d))
            if d[j] > 0.18:
                return "top center"
            vert = "bottom" if _ny[j] >= _ny[i] else "top"
            hor = "left" if _nx[j] >= _nx[i] else "right"
            return f"{vert} {hor}"

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
                text=[f"C{cid} (n={row.n_events})"],
                textposition=_pos_etiquette(i),
                textfont=dict(size=11, color=TEXT), cliponaxis=False,
                name=f"Cluster {cid}", showlegend=False,
                hovertemplate=(f"<b>Cluster {cid}</b><br>n = {row.n_events}<br>"
                               "couverture %{x:.1f} %<br>precip max %{y:.1f} mm<extra></extra>"),
            ))
        fig_sc.update_layout(
            title=dict(text="Couverture vs Intensité (taille = nb evt)",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Couverture moyenne (%)", gridcolor=BORDER),
            yaxis=dict(title="Précip. max moyenne (mm)", gridcolor=BORDER),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=30, t=60, b=10), height=320,
        )
        # Marge autour des bulles: les etiquettes du bord ne sont plus coupees.
        _xs = chars_s["mean_coverage_percent"]; _ys = chars_s["mean_max_precip"]
        _dx = max(1.0, float(_xs.max() - _xs.min()) * 0.15)
        _dy = max(1.0, float(_ys.max() - _ys.min()) * 0.20)
        fig_sc.update_layout(xaxis_range=[float(_xs.min()) - _dx, float(_xs.max()) + _dx],
                             yaxis_range=[float(_ys.min()) - _dy, float(_ys.max()) + _dy])
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
                name=f"Cluster {cid}", marker_color=cl_colors[i % len(cl_colors)],
            ))
        fig_yr.update_layout(
            barmode="stack",
            title=dict(text="Événements par année et cluster",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Année", gridcolor=BORDER, dtick=5),
            yaxis=dict(title="Nb événements", gridcolor=BORDER),
            legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center",
                        traceorder="normal", font=dict(color=TEXT, size=11),
                        title=dict(text="")),
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
                name=f"Cluster {cid}", marker_color=cl_colors[i % len(cl_colors)],
            ))
        fig_mo.update_layout(
            barmode="group",
            title=dict(text="Événements par mois et cluster",
                       font=dict(size=13, color=TEXT), x=0, pad=dict(l=0)),
            xaxis=dict(title="Mois", gridcolor=BORDER),
            yaxis=dict(title="Nb événements", gridcolor=BORDER),
            legend=dict(orientation="h", y=-0.28, x=0.5, xanchor="center",
                        traceorder="normal", font=dict(color=TEXT, size=11),
                        title=dict(text="")),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            margin=dict(l=10, r=10, t=44, b=10), height=300,
        )
        st.plotly_chart(fig_mo, use_container_width=True, key="cl_mo")

    # ── Hierarchie : etats oceaniques -> configurations ──────────────────
    hier = _hierarchie(sel_phase, events)
    if hier:
        st.markdown(
            f'<h3 style="font-size:0.85rem;font-weight:700;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin:4px 0 4px 2px;">États océaniques &rarr; configurations</h3>'
            f'<p style="font-size:0.74rem;color:{MUTED};margin:0 0 10px 2px;">'
            f'Niveau 1 : 4 états saisonniers robustes (composites par saison, significatifs face au '
            f'hasard, script 24). Niveau 2 : les clusters d&#39;événements ci-dessous, rattachés à l&#39;état '
            f'ou tombent au moins {int(100 * hier["seuil_rattachement"])} % de leurs événements. '
            f'V de Cramer = {hier["cramer_v"]} (1 = emboitement parfait).</p>',
            unsafe_allow_html=True)
        cols_e = st.columns(len(hier["etats"]))
        for col, e in zip(cols_e, hier["etats"]):
            enfants = ", ".join("C%d" % k for k in e["clusters"]) or "&mdash;"
            annees = ", ".join(str(a) for a in e["annees"][:8]) + (" &hellip;" if len(e["annees"]) > 8 else "")
            col.markdown(
                f'<div style="background:{CARD};border:1px solid {BORDER};border-top:4px solid {e["couleur"]};'
                f'border-radius:14px;padding:14px 16px;height:100%;">'
                f'<p style="font-size:0.85rem;font-weight:800;color:{TEXT};margin:0;">{e["nom"]}</p>'
                f'<p style="font-size:0.7rem;color:{MUTED};margin:4px 0 8px 0;line-height:1.4;">{e["description"]}</p>'
                f'<p style="font-size:0.72rem;color:{MUTED};margin:0;">Configurations : '
                f'<b style="color:{TEXT};">{enfants}</b></p>'
                f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Événements : '
                f'<b style="color:{TEXT};">{e["n_evenements"]}</b> &middot; Nino 3.4 : '
                f'<b style="color:{TEXT};">{nb(e["indices_moyens"]["Nino34"], "+.2f")}</b></p>'
                f'<p style="font-size:0.68rem;color:{MUTED};margin:4px 0 0 0;">{annees}</p>'
                f'</div>', unsafe_allow_html=True)
        # Repartition des evenements de chaque cluster entre les etats
        noms_e = [e["nom"] for e in hier["etats"]]
        coul_e = {e["nom"]: e["couleur"] for e in hier["etats"]}
        ks = sorted(hier["tableau"])
        fig_h = go.Figure()
        for nom in noms_e:
            fig_h.add_trace(go.Bar(
                y=["C%d" % k for k in ks], x=[hier["tableau"][k].get(nom, 0) for k in ks],
                name=nom, orientation="h", marker=dict(color=coul_e[nom], line=dict(width=1, color=CARD)),
                hovertemplate="<b>%{y}</b> : %{x} événements en " + nom + "<extra></extra>"))
        fig_h.update_layout(
            barmode="stack", height=max(220, 34 * len(ks) + 90),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, size=11), margin=dict(l=10, r=10, t=10, b=10),
            # Couleur explicite : sinon la legende prend la couleur du theme
            # Streamlit (texte sombre sur fond sombre, recette 29/09/2026).
            legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center",
                        traceorder="normal", font=dict(color=TEXT, size=11)),
            xaxis=dict(title="événements", gridcolor=BORDER), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_h, use_container_width=True, config={"displayModeBar": False},
                        key="cl_hierarchie")

    # ── Row 4 : per-cluster summary cards ────────────────────────────────
    st.markdown(
        f'<h3 style="font-size:0.85rem;font-weight:700;color:{MUTED};text-transform:uppercase;'
        f'letter-spacing:.07em;margin:4px 0 10px 2px;">Résumé par cluster</h3>',
        unsafe_allow_html=True,
    )
    selected_cl = st.session_state.get("cl_shared_cluster")
    n_c = len(chars_s)
    card_cols = st.columns(min(n_c, 5))
    for i, row in enumerate(chars_s.itertuples()):
        with card_cols[i % len(card_cols)]:
            cid    = row.cluster
            color  = cl_colors[i % len(cl_colors)]
            pct    = f"{nb(row.percentage, '.1f')}%"
            mp     = f"{nb(row.mean_max_precip, '.1f')} mm"
            cov    = f"{nb(row.mean_coverage_percent, '.1f')}%"
            anom   = f"{nb(row.mean_max_anomaly, '.1f')}"
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
            # Conteneur a cle: le style ne vise QUE la carte. L'ancien selecteur
            # (stVerticalBlock:has(.mk-cl-X)) attrapait aussi le bloc principal
            # de la page; son z-index:1 y creait un contexte d'empilement qui
            # enfermait l'iframe Jarvis, et la barre laterale passait devant.
            with st.container(key=f"cl_card_box_{cid}"):
                st.markdown(
                    f'<style>'
                    f'.st-key-cl_card_box_{cid}'
                    f'{{position:relative !important;z-index:1 !important;'
                    f'cursor:pointer !important;}}'
                    f'.st-key-cl_card_box_{cid}:hover .cl-card-{cid}'
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
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:0;">Événements&nbsp;: <b style="color:{TEXT};">{row.n_events}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Precip moy.&nbsp;: <b style="color:{TEXT};">{mp}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Couverture moy.&nbsp;: <b style="color:{TEXT};">{cov}</b></p>'
                    f'<p style="font-size:0.72rem;color:{MUTED};margin:2px 0;">Anomalie moy.&nbsp;: <b style="color:{TEXT};">{anom}</b></p>'
                    f'{_ligne_etat(hier, cid, MUTED, TEXT)}'
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

        # Pas de 0,75 deg (480 x 160 cellules) : a 520 px de haut, une cellule
        # fait encore ~2 px ; le pas de 0,5 deg envoyait 2,25 fois plus de
        # donnees pour un rendu identique.
        z       = z_full[::3, ::3]
        lats_ds = cent_lats[::3]
        lons_ds = cent_lons[::3]

        # Chaines de largeur fixe : un tableau 'object' est recopie chaine par
        # chaine par Plotly (~2 s), celui-ci d'un bloc.
        _rg_cent = _get_region_grid(tuple(lats_ds), tuple(lons_ds)).astype(str)
        fig_sst = go.Figure(go.Heatmap(
            z=z, x=lons_ds, y=lats_ds,
            colorscale="RdBu_r", zmin=-vlim, zmax=vlim, zsmooth=False,
            customdata=_rg_cent,
            colorbar=dict(
                title=dict(text="Anomalie SST (°C)", side="right"),
                len=0.75, thickness=14,
            ),
            hovertemplate=(
                "Lon: %{x:.2f}  Lat: %{y:.2f}<br>"
                "Anomalie SST: <b>%{z:.3f} °C</b><br>"
                "Région: %{customdata}<extra></extra>"
            ),
        ))
        _apply_geo_traces(fig_sst)
        fig_sst.add_trace(go.Scatter(
            x=[-17.4], y=[14.7], mode="markers",
            marker=dict(symbol="star", size=14, color=AMBER,
                        line=dict(width=1.5, color="white")),
            name="Sénégal (Dakar)",
            hovertemplate="Dakar<br>17.4W  14.7N<extra></extra>",
        ))
        fig_sst.update_layout(
            title=dict(
                text=(f"Centroïde SST  -  {PHASE_LABELS_CL.get(sel_phase, sel_phase)}"
                      f"  |  Cluster {sel_cl}"),
                font=dict(size=13, color=TEXT), x=0, pad=dict(l=0),
            ),
            xaxis=dict(title="Longitude", gridcolor=BORDER, dtick=30, range=[-180, 180]),
            yaxis=dict(title="Latitude",  gridcolor=BORDER, dtick=15, range=[-60, 60]),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(color=TEXT, size=11),
            legend=dict(x=0.01, y=0.99, bgcolor=CARD, font=dict(color=TEXT)),
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
      Précipitation moyenne composite sur le Sénégal (tous événements représentatifs
      du cluster).</p>
    """, unsafe_allow_html=True)

    _cl_statut, _cl_d = _composite_cluster(sel_phase, sel_cl_shared)
    _cl_carto_sel = sel_cl_shared

    if _cl_statut == "aucune_donnee":
        st.info(
            "Données cartographiques non disponibles. "
            "Executer le script 03c_filter_events_by_cluster_for_qgis.py pour generer les fichiers de pixels."
        )
    elif _cl_statut == "phase_vide":
        st.info(
            f"Aucun pixel disponible pour {PHASE_LABELS_CL.get(sel_phase, sel_phase)}. "
            "Relancer le script 03c_filter_events_by_cluster_for_qgis.py."
        )
    elif _cl_statut == "cluster_vide":
        st.info("Aucun pixel disponible pour ce cluster.")
    else:
        _cl_reg_stats = _cl_d["reg_stats"]
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

            _cl_bmap = du.basemap(*du.SENEGAL_CENTRE, du.SENEGAL_ZOOM,
                                  dark=bool(kw.get("dark_mode", False)))

            _cl_fig_comp = go.Figure()

            # Contours departements (fond, dessines avant les pixels)
            _cl_contours = _contours_departements()
            if _cl_contours is not None:
                _lo_b, _la_b = _cl_contours
                _cl_fig_comp.add_trace(go.Scattermap(
                    lat=_la_b, lon=_lo_b, mode="lines",
                    line=dict(width=1.1, color=("rgba(226,232,240,0.35)"
                                                if kw.get("dark_mode") else
                                                "rgba(30,27,75,0.35)")),
                    hoverinfo="none", showlegend=False,
                ))

            # Pixels precipitation (halo blanc pour lisibilite)
            _cl_fig_comp.add_trace(go.Scattermap(
                lat=_cl_d["lats"], lon=_cl_d["lons"],
                mode="markers",
                marker=dict(size=11, color="white", opacity=0.30),
                hoverinfo="skip", showlegend=False,
            ))
            _cl_fig_comp.add_trace(go.Scattermap(
                lat=_cl_d["lats"], lon=_cl_d["lons"],
                mode="markers",
                marker=dict(
                    size=9,
                    color=_cl_d["prec"],
                    colorscale=_CS_PREC_CL,
                    cmin=_cl_d["p_min"], cmax=_cl_d["p_max"],
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
                customdata=_cl_d["custom"],
                hovertemplate=(
                    "<b>%{customdata[2]} mm</b> moy. &nbsp;|&nbsp; %{customdata[0]}&sigma;<br>"
                    "<span style='color:#64748b'>Région : %{customdata[1]}</span>"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

            # Centroide de precipitation
            _cl_fig_comp.add_trace(go.Scattermap(
                lat=[_cl_d["ctr_lat"]], lon=[_cl_d["ctr_lon"]], mode="markers",
                marker=dict(size=20, color="white", opacity=0.85),
                hoverinfo="skip", showlegend=False,
            ))
            _cl_fig_comp.add_trace(go.Scattermap(
                lat=[_cl_d["ctr_lat"]], lon=[_cl_d["ctr_lon"]], mode="markers",
                marker=dict(
                    size=13, color=_cl_cl_color, opacity=1.0,
                    symbol="circle",
                ),
                hovertemplate=(
                    f"<b>Barycentre C{_cl_carto_sel}</b><br>"
                    f"{nb(_cl_d['ctr_lat'], '.2f')}N  {nb(abs(_cl_d['ctr_lon']), '.2f')}W"
                    "<extra></extra>"
                ),
                showlegend=False,
            ))

            _cl_fig_comp.update_layout(
                map=_cl_bmap,
                margin=dict(l=0, r=0, t=0, b=0),
                height=500,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor=CARD,
            )
            with st.spinner("Chargement de la carte..."):
                st.plotly_chart(
                    _cl_fig_comp, use_container_width=True, key="cl_carto_composite",
                    config=dict(du.CARTE_CONFIG, toImageButtonOptions={
                        "format": "png",
                        "filename": f"cluster{_cl_carto_sel}_{sel_phase}_composite",
                        "scale": 3,
                    }),
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
                f'Régions les plus arrosées &nbsp;'
                f'<span style="font-weight:400;text-transform:none;'
                f'letter-spacing:0;">(précip. moyenne)</span></p>',
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
                    f'color:{BLUE};">{nb(_rrow["mean_p"], ".1f")} mm</span>'
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
      Cartes SST — Qualité publication (cartopy)</h2>
    <p style="font-size:0.78rem;color:{MUTED};margin:0 0 16px 0;">
      Figures multi-panneaux générées par le script 14 : anomalies SST globales
      (tropiques) et zoom Atlantique / Afrique de l'Ouest pour chaque cluster.
      Hachurage des anomalies |z| &gt; 0.5 sigma (signal robuste).</p>
    """, unsafe_allow_html=True)

    SST_PAT_DIR = BASE / "outputs/visualizations/clustering/sst_patterns"
    PHASE_LABELS_PUB = {
        "Phase_1_debut":  "Phase 1 - Début (Mai-Juin)",
        "Phase_2_pleine": "Phase 2 - Pleine (Juillet-Aout)",
        "Phase_3_fin":    "Phase 3 - Fin (Septembre-Octobre)",
        "All_phases":     "Toutes phases confondues",
    }

    img_path = SST_PAT_DIR / f"{sel_phase}_sst_patterns_clusters.png"
    if img_path.exists():
        # La figure doit venir du MEME clustering que la page (revue 27/09/2026,
        # point 02): on compare k et effectifs a la fiche ecrite par le script 14.
        effectifs_page = {str(int(c)): int(n)
                          for c, n in events["cluster"].value_counts().sort_index().items()}
        meta = None
        try:
            import json as _json
            meta = _json.loads(img_path.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if meta and meta.get("effectifs") == effectifs_page:
            st.caption(f"k = {meta['k']} · figure générée le {meta.get('genere_le', '?')} "
                       f"à partir du clustering affiché sur cette page.")
            st.image(_image_publication(str(img_path), img_path.stat().st_mtime),
                     use_container_width=True)
        elif meta:
            st.warning(
                f"Figure non affichée : elle provient d'un autre clustering "
                f"(k = {meta.get('k')}, {meta.get('genere_le', '?')}) que celui de la page "
                f"(k = {len(effectifs_page)}). Relancer l'étape 14 du pipeline.")
        else:
            st.warning("Figure non affichée : son origine (k, date) est inconnue. "
                       "Relancer l'étape 14 du pipeline pour la regenerer.")
    else:
        st.info(
            f"Image non disponible pour {PHASE_LABELS_PUB.get(sel_phase, sel_phase)}. "
            f"Executez le script 14 pour generer les cartes."
        )
