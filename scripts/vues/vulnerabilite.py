"""Page Vulnerabilite : indice de risque de pluies extremes par zone.

Ne calcule rien : lit les sorties des scripts 26 (46 departements) et 27
(125 arrondissements), et les contours alleges du script 28, par les chargeurs
de dashboard_utils que lit aussi l'outil Jarvis get_priority_zones. La page et
Jarvis affichent donc les memes chiffres.

Indice = (Alea x Exposition x Vulnerabilite)^(1/3), chaque composante en rang
centile (0 = plus faible, 1 = plus fort). La vulnerabilite est PROVISOIRE
(pauvrete EHCVM regionale + croissance demographique 2013-2023) en attendant
les donnees d'habitat du RGPH-5 : la page le dit partout ou elle l'affiche.

Carte : un clic sur une zone la selectionne (meme effet que le selecteur).
"""
import html
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

import plotly.graph_objects as go
import streamlit as st

import dashboard_utils as du

NIVEAUX = {"departements": "Départements (46)", "arrondissements": "Arrondissements (125)"}
# cle -> (colonne, libelle, libelle court)
COMPOSANTES = {
    "indice": ("indice_risque", "Indice de risque", "Indice"),
    "alea": ("A_alea", "Aléa (pluies extrêmes)", "Aléa"),
    "exposition": ("E_exposition", "Exposition (population, densité)", "Exposition"),
    "vulnerabilite": ("V_vulnerabilite", "Vulnérabilité (provisoire)", "Vulnérabilité"),
}
TRIS = {
    "rang": ("rang", True, "Rang de l'indice"),
    "alea": ("A_alea", False, "Aléa"),
    "exposition": ("E_exposition", False, "Exposition"),
    "vulnerabilite": ("V_vulnerabilite", False, "Vulnérabilité"),
    "population": ("population_2023", False, "Population 2023"),
    "densite": ("densite_2023_hab_km2", False, "Densité"),
    "croissance": ("croissance_2013_2023_pct", False, "Croissance 2013-2023"),
    "nom": ("nom", True, "Nom"),
}
# Rampe sequentielle bleue (une teinte, du clair au fonce) ; en mode sombre les
# faibles valeurs se fondent dans le fond et les fortes ressortent en clair.
ECHELLE_CLAIRE = [[0, "#CDE2FB"], [0.25, "#86B6EF"], [0.5, "#3987E5"],
                  [0.75, "#1C5CAB"], [1, "#0D366B"]]
ECHELLE_SOMBRE = [[0, "#184F95"], [0.33, "#2A78D6"], [0.66, "#6DA7EC"], [1, "#CDE2FB"]]
BARRE = "#2A78D6"

TITRES_TOP = {
    "indice": "l'indice de risque est le plus élevé",
    "alea": "l'aléa est le plus fort",
    "exposition": "l'exposition est la plus forte",
    "vulnerabilite": "la vulnérabilité (provisoire) est la plus forte",
}
SRC_ALEA = "CHIRPS 1981-2023, mai-octobre"
SRC_POP = "ANSD, RGPH-5 2023 (Répertoire des localités)"
SRC_POP13 = "ANSD, RGPH 2013 et RGPH-5 2023"
SRC_PAUV = "ANSD, EHCVM 2021-2022, Tableau III-2 (région)"
SRC_CONTOURS = "OCHA COD-AB Sénégal v02 (2024), CC BY-IGO"


def _e(texte):
    return html.escape(str(texte))


def _fr(x, d=2):
    try:
        return ("%%.%df" % d % float(x)).replace(".", ",").replace("-", "−")
    except (TypeError, ValueError):
        return "n/d"


def _entier(n):
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "n/d"


@st.cache_data(ttl=300)
def _table(niveau):
    """Table du niveau avec une colonne 'nom' commune, ou None."""
    v = du.load_vulnerabilite()
    if v is None:
        return None
    t = v["departements"] if niveau == "departements" else v["arrondissements"]
    if t is None:
        return None
    t = t.copy()
    t["nom"] = t["departement"] if niveau == "departements" else t["arrondissement"]
    t["nom"] = t["nom"].fillna("Sans nom")
    return t.sort_values("rang").reset_index(drop=True)


def _selection_carte(pcodes):
    """Un clic sur la carte choisit la zone (avant la creation du selecteur)."""
    evt = st.session_state.get("vul_carte")
    try:
        pts = evt["selection"]["points"] if evt else []
    except (KeyError, TypeError):
        pts = []
    if not pts:
        return
    p = pts[0]
    loc = p.get("location") or (p.get("customdata") or [None])[0]
    signature = (st.session_state.get("vul_niveau"), loc)
    if loc in pcodes and signature != st.session_state.get("_vul_clic_vu"):
        st.session_state["_vul_clic_vu"] = signature
        st.session_state["vul_zone"] = loc


def _tableau(entetes, lignes, TEXT, MUTED, BORDER, CARD, alignes=(), hauteur=None,
             surligne=None):
    """Tableau HTML aux couleurs du theme (st.dataframe reste clair en mode sombre)."""
    th = "".join(
        f'<th style="position:sticky;top:0;background:{CARD};'
        f'text-align:{"right" if i in alignes else "left"};padding:8px 10px;'
        f'color:{MUTED};font-weight:600;font-size:0.72rem;border-bottom:1px solid {BORDER}">'
        f'{_e(h)}</th>' for i, h in enumerate(entetes))
    corps = []
    for k, ligne in enumerate(lignes):
        fond = "background:rgba(42,120,214,0.14);" if surligne is not None and k == surligne else ""
        corps.append("<tr style='%s'>" % fond + "".join(
            f'<td style="text-align:{"right" if i in alignes else "left"};padding:6px 10px;'
            f'color:{TEXT};font-size:0.80rem;border-bottom:1px solid {BORDER};'
            f'{"white-space:nowrap" if hauteur else ""}">{_e(v)}</td>'
            for i, v in enumerate(ligne)) + "</tr>")
    limite = f"max-height:{hauteur}px;overflow-y:auto;" if hauteur else ""
    return (f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
            f'overflow-x:auto;{limite}margin-top:8px"><table style="width:100%;'
            f'border-collapse:collapse"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(corps)}</tbody></table></div>')


def _barre(libelle, valeur, note, TEXT, MUTED, BORDER):
    """Une composante (0-1) en barre horizontale, valeur ecrite a cote."""
    largeur = max(0.0, min(1.0, float(valeur))) * 100 if valeur == valeur else 0
    return (f'<div style="margin:8px 0 2px 0;display:flex;justify-content:space-between;'
            f'font-size:0.78rem;color:{TEXT}"><span>{_e(libelle)}</span>'
            f'<b>{_fr(valeur)}</b></div>'
            f'<div style="height:8px;border-radius:4px;background:{BORDER}">'
            f'<div style="width:{largeur:.0f}%;height:8px;border-radius:4px;'
            f'background:{BARRE}"></div></div>'
            f'<div style="font-size:0.68rem;color:{MUTED};margin-top:2px">{_e(note)}</div>')


def _carte(t, geo, colonne, libelle, zone, dark_mode, TEXT, MUTED, CARD):
    echelle = ECHELLE_SOMBRE if dark_mode else ECHELLE_CLAIRE
    rang = t["rang"].map(lambda r: "%d" % r if r == r else "n/d")
    custom = list(zip(t["pcode"], t["nom"], t.get("region", t["nom"]),
                      t[colonne].map(_fr), rang, t["population_2023"].map(_entier)))
    fig = go.Figure(go.Choroplethmap(
        geojson=geo, featureidkey="properties.pcode", locations=t["pcode"],
        z=t[colonne], zmin=0, zmax=1, colorscale=echelle,
        marker=dict(line=dict(width=0.6, color=CARD), opacity=0.92),
        customdata=custom,
        hovertemplate=("<b>%{customdata[1]}</b> (%{customdata[2]})<br>"
                       + _e(libelle) + " : <b>%{customdata[3]}</b><br>"
                       "Rang de l'indice : %{customdata[4]} / " + str(len(t)) + "<br>"
                       "Population 2023 : %{customdata[5]}<extra></extra>"),
        colorbar=dict(title=dict(text="0 = faible<br>1 = fort", font=dict(size=10, color=MUTED)),
                      thickness=12, len=0.7, tickvals=[0, 0.25, 0.5, 0.75, 1],
                      ticktext=["0", "0,25", "0,5", "0,75", "1"],
                      tickfont=dict(size=10, color=MUTED), outlinewidth=0),
    ))
    sel = t[t["pcode"] == zone]
    if len(sel):
        # Contour de la zone choisie : trace transparente au trait epais.
        fig.add_trace(go.Choroplethmap(
            geojson=geo, featureidkey="properties.pcode", locations=sel["pcode"],
            z=[0], colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale=False, marker=dict(line=dict(width=3, color=TEXT)),
            hoverinfo="skip"))
    fig.update_layout(map=du.basemap(*du.SENEGAL_CENTRE, du.SENEGAL_ZOOM, dark=dark_mode),
                      margin=dict(l=0, r=0, t=0, b=0), height=460,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=CARD, font_color=TEXT, font_size=12),
                      clickmode="event+select")
    return fig


def run(BG, CARD, TEXT, MUTED, BORDER, dark_mode=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT, card=CARD)

    st.markdown("""
    <div class="pg-hdr"><div>
      <h1 class="pg-ttl">Vulnérabilité · où les pluies extrêmes font le plus de dégâts</h1>
      <p class="pg-sub">Indice de risque = (Aléa × Exposition × Vulnérabilité)<sup>1/3</sup>
      · CHIRPS, ANSD RGPH-5 et EHCVM, contours OCHA</p>
    </div></div>
    """, unsafe_allow_html=True)

    v = du.load_vulnerabilite()
    if v is None:
        st.info("Indice non calculé. Lancer : py -3 scripts/26_indice_risque_departements.py")
        return

    niveaux = [n for n in NIVEAUX if _table(n) is not None]
    # Niveau inconnu (arrondissements non calcules, consigne Jarvis) : le premier.
    if st.session_state.get("vul_niveau") not in niveaux:
        st.session_state["vul_niveau"] = niveaux[0]
    if st.session_state.get("vul_composante") not in COMPOSANTES:
        st.session_state["vul_composante"] = "indice"
    t = _table(st.session_state["vul_niveau"])
    pcodes = list(t["pcode"])
    _selection_carte(pcodes)
    if st.session_state.get("vul_zone") not in pcodes:
        st.session_state["vul_zone"] = pcodes[0]

    # ── Selecteurs (une ligne au-dessus de la carte) ────────────────────────
    c1, c2, c3 = st.columns([1, 1.2, 1.4], gap="small")
    with c1:
        niveau = st.radio("Niveau", niveaux, key="vul_niveau", horizontal=True,
                          format_func=NIVEAUX.get)
    with c2:
        cle_comp = st.selectbox("Composante affichée", list(COMPOSANTES), key="vul_composante",
                                format_func=lambda k: COMPOSANTES[k][1])
    noms = dict(zip(t["pcode"], t["nom"] + " · rang " + t["rang"].astype("Int64").astype(str)))
    with c3:
        zone = st.selectbox("Zone", pcodes, key="vul_zone", format_func=noms.get)
    colonne, libelle, court = COMPOSANTES[cle_comp]
    z = t[t["pcode"] == zone].iloc[0]

    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-left:4px solid '
        f'#F59E0B;border-radius:10px;padding:10px 14px;margin:6px 0 10px 0;color:{TEXT};'
        f'font-size:0.80rem;line-height:1.5"><b>Vulnérabilité provisoire.</b> Elle combine '
        f'la pauvreté EHCVM, connue seulement par région (même valeur pour toutes les zones '
        f'd\'une région), et la croissance de la population 2013-2023. Elle sera remplacée '
        f'par les données d\'habitat du RGPH-5. L\'indice classe les zones entre elles : '
        f'ce n\'est ni une probabilité ni un nombre de sinistrés.</div>',
        unsafe_allow_html=True)

    # ── Chiffres clefs ──────────────────────────────────────────────────────
    tete = t.iloc[0]
    tuiles = [
        ("Indice le plus élevé", tete["nom"], "%s · indice %s" % (
            tete.get("region", ""), _fr(tete["indice_risque"]))),
        ("Zones classées", str(len(t)), NIVEAUX[niveau].split(" (")[0].lower()
         + " · contours OCHA"),
        ("Population couverte", _entier(t["population_2023"].sum()), SRC_POP),
    ]
    for col, (lbl, val, sub) in zip(st.columns(3, gap="small"), tuiles):
        col.markdown(f'<div class="kpi"><div class="kpi-body"><p class="kpi-lbl">{_e(lbl)}</p>'
                     f'<p class="kpi-val">{_e(val)}</p><span class="kpi-tag">{_e(sub)}</span>'
                     f'</div></div>', unsafe_allow_html=True)
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Carte + fiche de la zone ────────────────────────────────────────────
    g, d = st.columns([1.45, 1], gap="medium")
    with g:
        st.markdown(f'<p class="pnl-ttl">{_e(libelle)} · {_e(NIVEAUX[niveau])}</p>'
                    '<p class="pnl-sub">Rang centile parmi les zones du niveau : 0 = plus '
                    'faible, 1 = plus fort · cliquer sur une zone pour sa fiche</p>',
                    unsafe_allow_html=True)
        geo = du.load_contours_simplifies("admin2" if niveau == "departements" else "admin3")
        if geo is None:
            st.info("Contours absents. Lancer : py -3 scripts/28_contours_simplifies.py")
        else:
            fig = _carte(t, geo, colonne, libelle, zone, dark_mode, TEXT, MUTED, CARD)
            st.plotly_chart(fig, use_container_width=True, key="vul_carte",
                            on_select="rerun", selection_mode="points",
                            config=dict(du.CARTE_CONFIG, toImageButtonOptions={
                                "format": "png", "filename": "vulnerabilite_%s_%s" % (
                                    niveau, cle_comp)}))
            st.caption("Molette ou pincement : zoom · glisser : déplacer · ⌂ : revenir au "
                       "Sénégal entier · Contours : " + SRC_CONTOURS)

    with d:
        cadre = ("Arrondissement de %s · %s" % (z["departement"], z["region"])
                 if niveau == "arrondissements" else "Département · région de %s" % z["region"])
        st.markdown(
            f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
            f'padding:14px 16px">'
            f'<div style="font-size:1.05rem;font-weight:700;color:{TEXT}">{_e(z["nom"])}</div>'
            f'<div style="font-size:0.74rem;color:{MUTED}">{_e(cadre)} · P-code {_e(z["pcode"])}</div>'
            f'<div style="display:flex;gap:18px;margin:10px 0 4px 0;color:{TEXT}">'
            f'<div><div style="font-size:0.68rem;color:{MUTED}">Indice de risque</div>'
            f'<div style="font-size:1.5rem;font-weight:700">{_fr(z["indice_risque"])}</div></div>'
            f'<div><div style="font-size:0.68rem;color:{MUTED}">Rang</div>'
            f'<div style="font-size:1.5rem;font-weight:700">{_entier(z["rang"])}'
            f'<span style="font-size:0.8rem;color:{MUTED}"> / {len(t)}</span></div></div></div>'
            + _barre("Aléa", z["A_alea"], "%s j/an > 2σ · %s j/an ≥ 50 mm · %s" % (
                _fr(z["jours_anomalie_2sigma_an"]), _fr(z["jours_50mm_an"]), SRC_ALEA),
                TEXT, MUTED, BORDER)
            + _barre("Exposition", z["E_exposition"], "%s hab. · %s hab/km² · %s" % (
                _entier(z["population_2023"]), _entier(z["densite_2023_hab_km2"]), SRC_POP),
                TEXT, MUTED, BORDER)
            + _barre("Vulnérabilité (provisoire)", z["V_vulnerabilite"],
                     "pauvreté %s %% (région) · croissance %s %% en 10 ans" % (
                         _fr(z["taux_pauvrete_region_pct"], 1),
                         _fr(z["croissance_2013_2023_pct"], 1)), TEXT, MUTED, BORDER)
            + '</div>', unsafe_allow_html=True)
        lignes = [
            ["Population 2023", _entier(z["population_2023"]), SRC_POP],
            ["Population 2013", _entier(z["population_2013"]), SRC_POP13],
            ["Superficie", "%s km²" % _entier(z["superficie_km2"]), SRC_CONTOURS.split(",")[0]],
            ["Pauvreté (région)", "%s %%" % _fr(z["taux_pauvrete_region_pct"], 1), SRC_PAUV],
            ["Pauvres estimés", _entier(z["pauvres_estimes_2023"]),
             "population × taux régional"],
        ]
        if niveau == "arrondissements" and "indice_departement" in z:
            lignes.append(["Indice du département", "%s (rang %s / 46)" % (
                _fr(z["indice_departement"]), _entier(z["rang_departement"])), "script 26"])
        st.markdown(_tableau(["Indicateur", "Valeur", "Source"], lignes,
                             TEXT, MUTED, BORDER, CARD, alignes=(1,)), unsafe_allow_html=True)
        if str(z.get("methode_alea", "")).startswith("pixel terrestre"):
            st.caption("Zone plus petite qu'un pixel CHIRPS (0,25°, ~770 km²) : l'aléa est "
                       "celui du pixel terrestre le plus proche, partagé avec ses voisines.")

    # ── Classement ──────────────────────────────────────────────────────────
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    top = t.sort_values(colonne, ascending=False).head(10).iloc[::-1]
    st.markdown(f'<p class="pnl-ttl">Les 10 zones où {_e(TITRES_TOP[cle_comp])}</p>'
                f'<p class="pnl-sub">{_e(libelle)} · rang centile (0 à 1) parmi les '
                f'{len(t)} {_e(NIVEAUX[niveau].split(" (")[0].lower())}</p>',
                unsafe_allow_html=True)
    fig = go.Figure(go.Bar(
        x=top[colonne], y=top["nom"] + " (" + top["region"].astype(str) + ")",
        orientation="h", marker=dict(color=BARRE, cornerradius=4),
        text=top[colonne].map(_fr), textposition="outside",
        textfont=dict(color=TEXT, size=11), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>" + _e(libelle) + " : %{x:.2f}<extra></extra>"))
    plotly_base(fig, h=340)
    fig.update_layout(xaxis=dict(range=[0, 1.12], showgrid=True, gridcolor=BORDER,
                                 tickformat=".2f"), yaxis=dict(showgrid=False),
                      bargap=0.35, margin=dict(l=10, r=30, t=8, b=24), separators=", ")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False},
                    key="vul_top10")

    st.markdown('<p class="pnl-ttl">Tableau complet</p>'
                '<p class="pnl-sub">Composantes en rang centile (0 à 1) · population '
                'ANSD RGPH-5 2023 · pauvreté ANSD EHCVM 2021-2022 (région)</p>',
                unsafe_allow_html=True)
    t1, t2, _ = st.columns([1.2, 1, 2], gap="small")
    with t1:
        tri = st.selectbox("Trier par", list(TRIS), key="vul_tri",
                           format_func=lambda k: TRIS[k][2])
    with t2:
        inverse = st.toggle("Ordre inverse", key="vul_tri_inverse")
    col_tri, croissant, _ = TRIS[tri]
    tt = t.sort_values(col_tri, ascending=croissant != inverse, na_position="last")
    entetes = ["Rang", "Zone"] + (["Département"] if niveau == "arrondissements" else []) + [
        "Région", "Indice", "Aléa", "Expo.", "Vuln.*", "Population 2023", "hab/km²",
        "Croiss. 13-23", "Pauvreté rég."]
    lignes = []
    for _, r in tt.iterrows():
        lignes.append(
            [_entier(r["rang"]), r["nom"]]
            + ([r["departement"]] if niveau == "arrondissements" else [])
            + [r["region"], _fr(r["indice_risque"]), _fr(r["A_alea"]), _fr(r["E_exposition"]),
               _fr(r["V_vulnerabilite"]), _entier(r["population_2023"]),
               _entier(r["densite_2023_hab_km2"]),
               "%s %%" % _fr(r["croissance_2013_2023_pct"], 1),
               "%s %%" % _fr(r["taux_pauvrete_region_pct"], 1)])
    surligne = next((k for k, p in enumerate(tt["pcode"]) if p == zone), None)
    n_col = len(entetes)
    st.markdown(_tableau(entetes, lignes, TEXT, MUTED, BORDER, CARD,
                         alignes=tuple(range(n_col - 8, n_col)) + (0,), hauteur=420,
                         surligne=surligne), unsafe_allow_html=True)
    st.caption("\\* Vulnérabilité provisoire. Ligne surlignée : zone choisie.")
    fichier = ("indice_risque_departements.csv" if niveau == "departements"
               else "indice_risque_arrondissements.csv")
    st.download_button("Télécharger le tableau (CSV)",
                       (du.VULNERABILITE / fichier).read_bytes(), file_name=fichier,
                       mime="text/csv", key="vul_dl")

    # ── Methode, sources, limites ───────────────────────────────────────────
    r_dep = v.get("resume") or {}
    r_arr = v.get("resume_arrondissements") or {}
    n_pixel = (len(r_arr.get("arrondissements_pixel_le_plus_proche") or [])
               if niveau == "arrondissements"
               else len(r_dep.get("departements_pixel_le_plus_proche") or []))
    couverture = (r_arr.get("couverture_population") or {}).get("2023", {}).get("part_pct")
    pauv_dakar = t.loc[t["region"] == "Dakar", "taux_pauvrete_region_pct"].min()
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
        f'padding:14px 18px;color:{TEXT};font-size:0.82rem;line-height:1.6">'
        f'<p class="pnl-ttl" style="margin:0 0 6px 0">Méthode</p>'
        f'<b>Indice de risque = (A × E × V)<sup>1/3</sup></b>, moyenne géométrique : une zone '
        f'ne ressort que si elle cumule aléa, exposition et vulnérabilité ; une composante '
        f'très faible suffit à la faire baisser.<br>'
        f'<b>Normalisation en rang centile</b> sur les zones du niveau (0 = plus faible, '
        f'1 = plus fort), robuste aux valeurs extrêmes (Dakar, Touba). Une composante à deux '
        f'indicateurs est la moyenne de leurs rangs centiles, remise en rang centile.<br>'
        f'<b>Aléa (A)</b> : jours par an où l\'anomalie dépasse +2σ et jours ≥ 50 mm, '
        f'mai-octobre {_e(r_dep.get("periode_alea", "1981-2023"))} (CHIRPS 0,25°).<br>'
        f'<b>Exposition (E)</b> : population et densité 2023 (ANSD RGPH-5 ; superficie OCHA).<br>'
        f'<b>Vulnérabilité (V), provisoire</b> : pauvreté P0 de la région (ANSD EHCVM '
        f'2021-2022) et croissance de la population 2013-2023 (ANSD RGPH), indicateur '
        f'd\'urbanisation rapide.<br>'
        f'<p class="pnl-ttl" style="margin:12px 0 6px 0">Sources</p>'
        f'ANSD, RGPH-5 2023 et RGPH 2013, Répertoire des localités · ANSD, EHCVM 2021-2022, '
        f'Rapport final, Tableau III-2 · {SRC_CONTOURS} · CHIRPS v2 (UCSB Climate Hazards '
        f'Center), 1981-2023'
        + (' · rattachement des communes aux arrondissements : GADM 4.1 et © OpenStreetMap '
           '(ODbL), couverture de la population %s %%' % _fr(couverture, 1)
           if niveau == "arrondissements" and couverture is not None else '')
        + f'<p class="pnl-ttl" style="margin:12px 0 6px 0">Limites</p>'
        f'• La vulnérabilité est provisoire, en attendant les données d\'habitat du RGPH-5 '
        f'(logement, assainissement).<br>'
        f'• La pauvreté n\'est connue qu\'à l\'échelle régionale : toutes les zones d\'une '
        f'région ont la même valeur, ce qui place les zones de la région de Dakar '
        f'({_fr(pauv_dakar, 1)} %, le taux le plus bas) au plus bas de la vulnérabilité.<br>'
        f'• La croissance 2013-2023 repère l\'urbanisation récente (Rufisque, Keur Massar), '
        f'pas les quartiers inondables plus anciens : Pikine et Guédiawaye restent bas, '
        f'contrairement aux inondations de 2005, 2009, 2012 et 2020. Les poids n\'ont pas '
        f'été ajustés pour corriger ce classement.<br>'
        f'• {n_pixel} zones sont plus petites qu\'un pixel CHIRPS : leur aléa est celui du '
        f'pixel terrestre le plus proche.<br>'
        f'• L\'indice classe les zones entre elles ; il ne mesure ni une probabilité ni '
        f'des dégâts.</div>', unsafe_allow_html=True)
