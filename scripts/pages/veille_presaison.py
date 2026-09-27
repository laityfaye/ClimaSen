"""Page Veille pre-saison: bulletin annuel de niveau de risque d'annee extreme.

Ne calcule rien: lit les bulletins JSON produits hors ligne par
scripts/20_veille_presaison.py (outputs/veille/). Le serveur n'a donc besoin
ni du cube SST ni d'un acces Copernicus.
"""
import html
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE / "scripts"))
sys.path.insert(0, str(RACINE))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dashboard_utils as du
from dashboard_utils import INDIGO

from veille import DOSSIER_SORTIE, INONDATIONS_CONNUES
from veille import artefacts, fiabilite, production
from veille import bulletin as mod_bulletin
from veille.projection import VARIANTES_TESTEES, p_corrige

ICONES = {"faible": "&#9660;", "normal": "&#9679;", "eleve": "&#9650;",
          "tres_eleve": "&#9650;&#9650;", "indetermine": "?"}


@st.cache_data(ttl=300)
def _bulletins():
    return {a: production.lire_bulletin(a) for a in production.bulletins_disponibles()}


@st.cache_data(ttl=300)
def _etat(annee):
    try:
        z, lats, lons, mois = artefacts.charger_etat(annee)
    except artefacts.ArtefactIndisponible:
        return None
    return z, lats, lons, [str(m) for m in mois]


@st.cache_data(ttl=300)
def _carnet():
    return fiabilite.carnet()


@st.cache_data(ttl=300)
def _classement():
    chemin = DOSSIER_SORTIE / "classement_annees.csv"
    return pd.read_csv(chemin) if chemin.is_file() else None


def _pct(p):
    return "n/d" if p is None else "%d %%" % round(100 * p)


def _e(texte):
    return html.escape(str(texte))


def _fr(x, d=2):
    """Nombre a la francaise (0,72)."""
    return ("%%.%df" % d % x).replace(".", ",")


def _tableau(entetes, lignes, TEXT, MUTED, BORDER, CARD, alignes=()):
    """Tableau HTML aux couleurs du theme (st.dataframe reste clair en mode sombre)."""
    th = "".join(
        f'<th style="text-align:{"right" if i in alignes else "left"};padding:8px 10px;'
        f'color:{MUTED};font-weight:600;font-size:0.72rem;border-bottom:1px solid {BORDER}">'
        f'{_e(h)}</th>' for i, h in enumerate(entetes))
    corps = "".join(
        "<tr>" + "".join(
            f'<td style="text-align:{"right" if i in alignes else "left"};padding:7px 10px;'
            f'color:{TEXT};font-size:0.80rem;border-bottom:1px solid {BORDER}">{_e(v)}</td>'
            for i, v in enumerate(ligne)) + "</tr>"
        for ligne in lignes)
    return (f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
            f'overflow-x:auto;margin-top:8px"><table style="width:100%;border-collapse:collapse">'
            f'<thead><tr>{th}</tr></thead><tbody>{corps}</tbody></table></div>')


def run(BG, CARD, TEXT, MUTED, BORDER, dark_mode=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT, card=CARD)

    st.markdown("""
    <div class="pg-hdr"><div>
      <p class="pg-bc">Dashboard &nbsp;/&nbsp; <b>Veille pré-saison</b></p>
      <h1 class="pg-ttl">Veille pré-saison · risque d'année extrême</h1>
      <p class="pg-sub">Bulletin d'avril · prévision Copernicus C3S + état océanique
      novembre-avril projeté sur les configurations du mémoire</p>
    </div></div>
    """, unsafe_allow_html=True)

    bulletins = _bulletins()
    if not bulletins:
        st.info("Aucun bulletin produit. Lancer : py -3 scripts/20_veille_presaison.py --annee <annee>")
        return

    annees = list(bulletins)
    # Jarvis peut demander une saison sans bulletin: on retombe sur la plus recente.
    if st.session_state.get("veille_annee") not in annees:
        st.session_state.pop("veille_annee", None)
    choix = st.selectbox("Saison", annees, index=0, key="veille_annee",
                         format_func=lambda a: "%d%s" % (
                             a, " (rétrospectif)" if bulletins[a].get("verification") else ""))
    b = bulletins[choix]
    n = b["niveau_risque"]
    # Niveau colore seulement si la competence est demontree (veille/bulletin.py).
    pres = b.get("presentation") or mod_bulletin.presentation(n)
    retrospectif = bool(b.get("verification"))

    # ── Calendrier (saison a venir sans prevision) ─────────────────────────
    if pres["mode"] == "indetermine" and not retrospectif:
        st.markdown(
            f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
            f'padding:14px 18px;margin:4px 0 12px 0;color:{TEXT};font-size:0.84rem;'
            f'line-height:1.6">'
            f'<b>Calendrier de la veille pour la saison {choix}</b><br>'
            f'Début décembre {choix - 1} : premier bulletin provisoire (état océanique de '
            f'novembre).<br>'
            f'Chaque début de mois jusqu’en avril : bulletin provisoire mis à jour.<br>'
            f'Mi-avril {choix} : bulletin final, après la prévision Copernicus C3S '
            f'(publiée le 13 avril).<br>'
            f'<span style="color:{MUTED}">En attendant : en moyenne, 1 saison sur 3 est '
            f'extrême.</span></div>', unsafe_allow_html=True)

    # ── Niveau de risque + chiffres clefs ────────────────────────────────────
    c1, c2, c3 = st.columns([1.3, 1, 1], gap="small")
    with c1:
        icone = (f'<span style="color:{pres["couleur"]}">{ICONES.get(n["code"], "")}</span> '
                 if pres["mode"] == "niveau" else "")
        st.markdown(
            f'<div class="kpi" style="border-left:6px solid {pres["couleur"]}">'
            f'<div class="kpi-body">'
            f'<p class="kpi-lbl">{_e(pres["titre"])} · saison {choix}</p>'
            f'<p class="kpi-val" style="color:{TEXT}">{icone}{_e(pres["valeur"])}</p>'
            f'<span class="kpi-tag">{_e(pres["note"])}</span>'
            f'</div></div>', unsafe_allow_html=True)
    c3s = b.get("c3s") or {}
    with c2:
        val = _pct(c3s.get("probabilite_annee_extreme")) if c3s.get("disponible") else "—"
        sub = ("%s · anomalie JAS %+.1f σ" % (c3s["centre"].upper(), c3s["anomalie_standardisee"])
               if c3s.get("disponible") else
               "publiée le 13 avril" if not retrospectif else "non disponible")
        st.markdown(f'<div class="kpi"><div class="kpi-body"><p class="kpi-lbl">Prévision C3S</p>'
                    f'<p class="kpi-val">{val}</p><span class="kpi-tag">{_e(sub)}</span>'
                    f'</div></div>', unsafe_allow_html=True)
    proj = b.get("projection") or {}
    with c3:
        val = _pct(proj.get("probabilite_experimentale")) if proj else "—"
        st.markdown(f'<div class="kpi"><div class="kpi-body">'
                    f'<p class="kpi-lbl">Projection océanique</p>'
                    f'<p class="kpi-val">{val}</p><span class="kpi-tag">expérimentale · '
                    f'ne fixe pas le niveau</span></div></div>', unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown(f'<p class="pnl-ttl">Synthèse</p>', unsafe_allow_html=True)
    st.markdown(f"<p style='color:{TEXT};line-height:1.55'>{_e(b['synthese'])}</p>",
                unsafe_allow_html=True)
    # Saison a venir: ces notes decrivent l'etat normal hors periode de veille,
    # pas une erreur -> ton informatif.
    for a in b.get("avertissements") or []:
        (st.warning if retrospectif else st.info)(a)

    # ── Configurations + analogues ─────────────────────────────────────────
    if proj:
        g, d = st.columns([1.2, 1], gap="medium")
        with g:
            st.markdown('<p class="pnl-ttl">Ressemblance aux configurations du mémoire</p>'
                        '<p class="pnl-sub">Corrélation de motif entre l\'état SST '
                        'novembre-avril (détrendé) et chaque centroïde K-Means · '
                        'axe : corrélation</p>',
                        unsafe_allow_html=True)
            toutes = sorted(proj.get("toutes_configurations") or [],
                            key=lambda c: c["correlation"])
            fig = go.Figure(go.Bar(
                x=[c["correlation"] for c in toutes],
                y=["C%d" % c["configuration"] for c in toutes],
                orientation="h", marker=dict(color=INDIGO, cornerradius=4),
                hovertemplate="<b>%{y}</b> : r = %{x:.2f}<extra></extra>"))
            plotly_base(fig, h=290)
            fig.update_layout(xaxis=dict(zeroline=True, zerolinecolor=MUTED, showgrid=True,
                                         gridcolor=BORDER, tickformat=".2f"),
                              yaxis=dict(showgrid=False), bargap=0.35,
                              margin=dict(l=10, r=14, t=12, b=28), separators=", ")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            top = (proj.get("configurations") or [])[:3]
            if top:
                st.markdown(_tableau(
                    ["Config.", "État", "Corrélation", "Années principales", "Évén. en année extrême"],
                    [["C%d" % c["configuration"], c.get("etat_oceanique") or "—", _fr(c["correlation"]),
                      ", ".join(str(a) for a in c.get("annees_principales", [])) or "—",
                      _pct(c.get("part_evenements_en_annee_extreme"))] for c in top],
                    TEXT, MUTED, BORDER, CARD, alignes=(2, 4)), unsafe_allow_html=True)
        with d:
            st.markdown('<p class="pnl-ttl">Années analogues</p>'
                        '<p class="pnl-sub">Saisons passées dont l\'océan de novembre à avril '
                        'ressemblait le plus</p>', unsafe_allow_html=True)
            st.markdown(_tableau(
                ["Année", "Corrélation", "Saison", "Inondation documentée"],
                [[a["annee"], _fr(a["correlation"]), "extrême" if a["extreme"] else "normale",
                  "oui" if a["inondation_documentee"] else ""]
                 for a in proj.get("analogues") or []],
                TEXT, MUTED, BORDER, CARD, alignes=(1,)), unsafe_allow_html=True)
            cp = b.get("competence_projection") or {}
            lo, pr = cp.get("loyo") or {}, cp.get("prevision_reelle") or {}
            if cp:
                st.markdown(
                    f"<p class='pnl-sub' style='margin-top:14px;color:{TEXT}'>"
                    f"<b>Compétence de la projection</b><br>"
                    f"Année testée exclue : AUC {_fr(lo.get('auc', 0))} "
                    f"(p = {_fr(lo.get('p_permutation', 1), 3)} ; "
                    f"{_fr(p_corrige(lo.get('p_permutation', 1)), 3)} corrigé pour les "
                    f"{len(VARIANTES_TESTEES)} variantes comparées)<br>"
                    f"Prévision réelle (passé seul) : AUC {_fr(pr.get('auc', 0))} "
                    f"(p = {_fr(pr.get('p_permutation', 1), 3)})<br>"
                    f"<span style='color:{MUTED}'>{_e(cp.get('verdict', ''))}. "
                    f"AUC 0,5 = hasard.</span></p>", unsafe_allow_html=True)
                with st.expander("Variantes de projection comparées (fixées avant le test)"):
                    st.markdown(_tableau(
                        ["Variante", "Année exclue : AUC (p)", "Prévision réelle : AUC (p)"],
                        [["%s %s%s" % (v["code"], v["nom"], " (retenue)" if v.get("retenue") else ""),
                          "%s (%s)" % (_fr(v["loyo"]["auc"]), _fr(v["loyo"]["p"], 3)),
                          "%s (%s)" % (_fr(v["prevision_reelle"]["auc"]),
                                       _fr(v["prevision_reelle"]["p"], 2))]
                         for v in VARIANTES_TESTEES],
                        TEXT, MUTED, BORDER, CARD, alignes=(1, 2)), unsafe_allow_html=True)
                    st.caption("Test exploratoire du 26/09/2026, même protocole sans fuite. "
                               "La variante retenue doit être jugée sur son p corrigé "
                               "(× %d) : une comparaison de plusieurs variantes augmente "
                               "la chance d'un bon score dû au hasard." % len(VARIANTES_TESTEES))

    # ── L'ocean de novembre a avril + trajectoire de la veille ────────────
    etat = _etat(choix)
    traj = (proj or {}).get("trajectoire") or []
    if etat is not None:
        z, lats, lons, mois = etat
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.markdown('<p class="pnl-ttl">L\'océan de novembre à avril</p>'
                    '<p class="pnl-sub">Anomalie de température de surface (°C), moyenne de '
                    '%s à %s · bleu : plus froid que la normale · rouge : plus chaud</p>'
                    % (_e(mois[0]), _e(mois[-1])), unsafe_allow_html=True)
        lim = float(max(0.5, min(3.0, abs(pd.Series(z.ravel()).dropna()).quantile(0.98))))
        neutre = BORDER
        fig = go.Figure(go.Heatmap(
            z=z, x=lons, y=lats, zmin=-lim, zmax=lim, zmid=0,
            colorscale=[[0, "#2563EB"], [0.5, neutre], [1, "#DC2626"]],
            colorbar=dict(title=dict(text="°C", font=dict(color=MUTED, size=11)),
                          tickfont=dict(color=MUTED, size=10), thickness=10, len=0.8),
            hovertemplate="%{y:.0f}°, %{x:.0f}° : %{z:+.2f} °C<extra></extra>"))
        plotly_base(fig, h=320)
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=24), separators=", ",
                          xaxis=dict(showgrid=False, ticksuffix="°", range=[-180, 180],
                                     tickvals=list(range(-150, 181, 50)), constrain="domain"),
                          yaxis=dict(showgrid=False, ticksuffix="°", range=[-60, 60],
                                     scaleanchor="x", constrain="domain"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    if len(traj) >= 2:
        st.markdown('<p class="pnl-ttl">Évolution pendant la veille</p>'
                    '<p class="pnl-sub">Indication expérimentale de la projection sur l\'état '
                    'cumulé depuis novembre · étiquette : configuration du mémoire la plus '
                    'proche · les premiers mois sont plus incertains</p>', unsafe_allow_html=True)
        mois_fr = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
                   "sept.", "oct.", "nov.", "déc."]
        etiquettes = ["%s %s" % (mois_fr[int(t["jusqu_a"][5:]) - 1], t["jusqu_a"][:4])
                      for t in traj]
        fig = go.Figure(go.Scatter(
            x=etiquettes, y=[t["probabilite_experimentale"] for t in traj],
            mode="lines+markers+text", line=dict(color=INDIGO, width=2),
            marker=dict(size=9, color=INDIGO),
            text=["C%d" % t["configuration"] for t in traj], textposition="top center",
            textfont=dict(color=TEXT, size=11),
            hovertemplate="jusqu'à fin %{x} : %{y:.0%}<extra></extra>"))
        fig.add_hline(y=1 / 3, line=dict(color=MUTED, width=1, dash="dot"),
                      annotation_text="référence 33 %", annotation_position="bottom left",
                      annotation_font_color=MUTED)
        plotly_base(fig, h=240)
        fig.update_layout(yaxis=dict(tickformat=".0%", range=[0, 1], showgrid=True,
                                     gridcolor=BORDER), separators=", ",
                          xaxis=dict(type="category"),
                          margin=dict(l=10, r=14, t=16, b=24))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Carnet de fiabilite ────────────────────────────────────────────────
    carnet = _carnet()
    if carnet.get("disponible"):
        r = carnet["niveau_de_risque"]
        cpt = r["comptes"]
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        st.markdown('<p class="pnl-ttl">Carnet de fiabilité %d-%d</p>'
                    '<p class="pnl-sub">Ce que les bulletins rétrospectifs auraient annoncé '
                    '(chacun limité à ce qui était connu en avril) face à ce qui est arrivé · '
                    'alerte = probabilité C3S d’au moins 40 %% (niveau calculé « élevé » '
                    'ou plus, jamais affiché tant que la compétence n’est pas démontrée)</p>' % tuple(carnet["periode"]),
                    unsafe_allow_html=True)
        cols = st.columns(4, gap="small")
        tuiles = [("Détections", cpt["détection"], "saisons extrêmes annoncées"),
                  ("Manquées", cpt["manquée"], "saisons extrêmes non annoncées"),
                  ("Fausses alertes", cpt["fausse alerte"], "alerte, saison normale"),
                  ("Taux de détection", _pct(r["taux_detection"]),
                   "AUC %s (0,5 = hasard)" % _fr(r["auc_probabilite_c3s"] or 0))]
        for col, (lbl, val, sub) in zip(cols, tuiles):
            col.markdown(f'<div class="kpi"><div class="kpi-body"><p class="kpi-lbl">{_e(lbl)}</p>'
                         f'<p class="kpi-val">{_e(val)}</p><span class="kpi-tag">{_e(sub)}</span>'
                         f'</div></div>', unsafe_allow_html=True)
        st.markdown(_tableau(
            ["Inondation documentée", "Niveau calculé", "Verdict"],
            [[x["annee"], x["niveau"], x["verdict"]] for x in carnet["inondations_documentees"]],
            TEXT, MUTED, BORDER, CARD), unsafe_allow_html=True)

    # ── Historique: quelles annees ont ete extremes ────────────────────────
    cl = _classement()
    if cl is not None:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        seuil = b["definition"]["seuil"]
        st.markdown('<p class="pnl-ttl">Empreinte des saisons 1981-2023</p>'
                    '<p class="pnl-sub">Somme de l\'étendue de tous les événements extrêmes de la '
                    'saison · au-dessus du trait : année extrême (tiers supérieur) · '
                    '▲ inondation majeure documentée</p>', unsafe_allow_html=True)
        couleurs = [INDIGO if e else MUTED for e in cl["extreme"]]
        fig = go.Figure(go.Bar(
            x=cl["annee"], y=cl["empreinte"], marker=dict(color=couleurs, cornerradius=4),
            customdata=cl[["rang"]].values,
            hovertemplate="<b>%{x}</b><br>empreinte %{y:.0f}<br>rang %{customdata[0]}<extra></extra>"))
        inond = cl[cl["annee"].isin(INONDATIONS_CONNUES)]
        fig.add_trace(go.Scatter(x=inond["annee"], y=inond["empreinte"] + 45, mode="text",
                                 text=["▲"] * len(inond), textfont=dict(color=TEXT, size=11),
                                 hoverinfo="skip", showlegend=False))
        fig.add_hline(y=seuil, line=dict(color=TEXT, width=1, dash="dot"),
                      annotation_text="seuil %.0f" % seuil, annotation_position="top left",
                      annotation_font_color=MUTED)
        plotly_base(fig, h=300)
        fig.update_layout(showlegend=False, bargap=0.25, margin=dict(l=10, r=14, t=12, b=24))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Ce que les bulletins retrospectifs auraient dit ────────────────────
    retro = [bb for bb in bulletins.values() if bb.get("verification") and bb.get("projection")]
    if len(retro) >= 5:
        retro.sort(key=lambda x: x["annee"])
        st.markdown('<p class="pnl-ttl">Bulletins rétrospectifs : ce que la projection '
                    'aurait annoncé</p><p class="pnl-sub">Chaque point n\'utilise que les '
                    'saisons antérieures · plein : saison observée extrême · creux : '
                    'normale</p>', unsafe_allow_html=True)
        fig = go.Figure()
        for extreme, nom, sym in ((True, "saison extrême", "circle"),
                                  (False, "saison normale", "circle-open")):
            sel = [x for x in retro if x["verification"]["extreme_observe"] == extreme]
            fig.add_trace(go.Scatter(
                x=[x["annee"] for x in sel],
                y=[x["projection"]["probabilite_experimentale"] for x in sel],
                mode="markers", name=nom,
                marker=dict(symbol=sym, size=11, color=INDIGO, line=dict(width=2, color=INDIGO)),
                hovertemplate="<b>%{x}</b> : %{y:.0%} annoncé<extra>" + nom + "</extra>"))
        fig.add_hline(y=1 / 3, line=dict(color=MUTED, width=1, dash="dot"),
                      annotation_text="référence 33 %", annotation_position="top left",
                      annotation_font_color=MUTED)
        plotly_base(fig, h=280)
        fig.update_layout(yaxis=dict(tickformat=".0%", range=[0, 1], showgrid=True,
                                     gridcolor=BORDER), separators=", ")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Telechargement ─────────────────────────────────────────────────────
    md = DOSSIER_SORTIE / ("bulletin_%d.md" % choix)
    if md.is_file():
        st.download_button("Télécharger le bulletin (Markdown)", md.read_bytes(),
                           file_name=md.name, mime="text/markdown", key="veille_dl")
    st.caption("Émis le %s · %s" % (b["emis_le"], b["definition"]["mesure"]))
