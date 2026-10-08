"""Page Vulnerabilite : indice de risque de pluies extremes par zone.

Ne calcule rien : lit les sorties des scripts 26 (46 departements) et 27
(125 arrondissements), et les contours alleges du script 28, par les chargeurs
de dashboard_utils que lit aussi l'outil Jarvis get_priority_zones. La page et
Jarvis affichent donc les memes chiffres.

Indice = (Alea x Exposition x Vulnerabilite)^(1/3), chaque composante en rang
centile (0 = plus faible, 1 = plus fort). La vulnerabilite est PROVISOIRE
(pauvrete EHCVM regionale + croissance demographique 2013-2023) en attendant
les donnees d'habitat du RGPH-5 : la page le dit partout ou elle l'affiche.

Organisation : barre de commandes (niveau, composante, zone), chiffres clefs,
carte + fiche de la zone, classement (top 10 / tableau complet), communes,
methode-sources-limites.

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
from dashboard_utils import AMBER, INDIGO

NIVEAUX = {"departements": "Départements (46)", "arrondissements": "Arrondissements (125)"}
# cle -> (colonne, libelle, libelle court)
COMPOSANTES = {
    "indice": ("indice_risque", "Indice de risque", "Indice"),
    "alea": ("A_alea", "Aléa (pluies extrêmes)", "Aléa"),
    "exposition": ("E_exposition", "Exposition (population, densité)", "Exposition"),
    "vulnerabilite": ("V_vulnerabilite", "Vulnérabilité (provisoire)", "Vulnérabilité"),
}
# Couleur et icone de chaque composante (fiche, classement, tableau).
STYLE_COMP = {
    "indice": (INDIGO, "crisis_alert"),
    "alea": ("#0EA5E9", "rainy"),
    "exposition": ("#A855F7", "groups"),
    "vulnerabilite": (AMBER, "home_repair_service"),
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

CSS = """
<style>
/* ── Niveau en pastilles ─────────────────────────────────────────────── */
.st-key-vul_niveau [data-baseweb="radio-group"] {
  gap: 0 !important; background: __BG__; border: 1px solid __BORDER__; border-radius: 10px;
  padding: 3px; display: inline-flex; flex-wrap: wrap; }
.st-key-vul_niveau label { border-radius: 8px !important; padding: 6px 14px !important;
  margin: 0 !important; transition: background .15s; }
.st-key-vul_niveau label > div:first-child { display: none !important; }
.st-key-vul_niveau label p { font-size: .78rem !important; font-weight: 600 !important;
  color: __MUTED__ !important; }
.st-key-vul_niveau label:has(input:checked) { background: __CARD__ !important;
  box-shadow: 0 1px 4px rgba(0,0,0,.12) !important; }
.st-key-vul_niveau label:has(input:checked) p { color: #4F46E5 !important; }

/* ── Avertissement provisoire ────────────────────────────────────────── */
.vu-alerte { display: flex; gap: 12px; align-items: flex-start; padding: 12px 16px;
  border-radius: 12px; margin: 8px 0 14px 0;
  border: 1px solid color-mix(in srgb, #F59E0B 40%, transparent);
  background: color-mix(in srgb, #F59E0B 8%, transparent); }
.vu-alerte .material-symbols-rounded { color: #F59E0B !important; font-size: 21px; }
.vu-alerte p { margin: 0 !important; font-size: .8rem !important; line-height: 1.55;
  color: __TEXT__ !important; }

/* ── Titres de section ───────────────────────────────────────────────── */
.vu-sec { margin: 30px 0 12px 0; }
.vu-sec-ttl { font-size: 1.02rem !important; font-weight: 800 !important; letter-spacing: -.2px;
  color: __TEXT__ !important; margin: 0 !important; display: flex; align-items: center; gap: 8px; }
.vu-sec-ttl .material-symbols-rounded { color: #6366F1 !important; font-size: 20px; }
.vu-sec-sub { font-size: .76rem !important; color: __MUTED__ !important; margin: 3px 0 0 0 !important; }

/* ── Fiche de la zone ────────────────────────────────────────────────── */
.vu-fiche { background: __CARD__; border: 1px solid __BORDER__; border-radius: 18px;
  overflow: hidden; animation: vu-monte .5s ease both;
  box-shadow: 0 1px 3px rgba(0,0,0,.04), 0 18px 40px -30px rgba(79,70,229,.5); }
.vu-fiche-hd { display: flex; gap: 18px; align-items: center; padding: 20px 22px 16px 22px;
  background: radial-gradient(130% 160% at 0% 0%, rgba(79,70,229,.14), transparent 60%); }
.vu-anneau { --p: 50; width: 92px; height: 92px; border-radius: 50%; flex-shrink: 0;
  display: grid; place-items: center;
  background: conic-gradient(#4F46E5 calc(var(--p) * 1%),
              color-mix(in srgb, __MUTED__ 20%, transparent) 0); }
.vu-anneau > div { width: 72px; height: 72px; border-radius: 50%; background: __CARD__;
  display: flex; flex-direction: column; align-items: center; justify-content: center; }
.vu-anneau b { font-size: 1.3rem; font-weight: 800; color: __TEXT__ !important; line-height: 1; }
.vu-anneau span { font-size: .58rem; color: __MUTED__ !important; text-transform: uppercase;
  letter-spacing: .6px; margin-top: 3px; }
.vu-nom { font-size: 1.35rem !important; font-weight: 800 !important; letter-spacing: -.4px;
  color: __TEXT__ !important; margin: 0 !important; line-height: 1.15; }
.vu-cadre { font-size: .74rem !important; color: __MUTED__ !important; margin: 3px 0 8px 0 !important; }
.vu-rang { display: inline-flex; align-items: center; gap: 5px; font-size: .74rem; font-weight: 700;
  padding: 4px 10px; border-radius: 999px; color: var(--c) !important;
  background: color-mix(in srgb, var(--c) 13%, transparent); }
.vu-rang .material-symbols-rounded { font-size: 15px; }
.vu-comps { padding: 4px 22px 16px 22px; display: grid; gap: 14px; }
.vu-comp { display: grid; grid-template-columns: 34px 1fr; gap: 12px; align-items: start; }
.vu-comp > .material-symbols-rounded { font-size: 18px; color: var(--c) !important; border-radius: 10px;
  padding: 7px; background: color-mix(in srgb, var(--c) 14%, transparent); }
.vu-comp-hd { display: flex; justify-content: space-between; align-items: baseline;
  font-size: .8rem; font-weight: 700; color: __TEXT__ !important; }
.vu-comp-hd b { font-size: .95rem; font-variant-numeric: tabular-nums; color: __TEXT__ !important; }
.vu-jauge { height: 8px; border-radius: 999px; margin: 6px 0 4px 0; overflow: hidden;
  background: color-mix(in srgb, __MUTED__ 18%, transparent); }
.vu-jauge > i { display: block; height: 100%; border-radius: 999px; background: var(--c);
  animation: vu-pousse .9s .1s cubic-bezier(.3,.7,.3,1) both; transform-origin: left; }
.vu-comp small { display: block; font-size: .68rem; line-height: 1.45; color: __MUTED__ !important; }
.vu-lecture { margin: 0 22px 18px 22px; padding: 10px 13px; border-radius: 10px; font-size: .78rem;
  line-height: 1.5; color: __TEXT__ !important; border: 1px dashed __BORDER__;
  background: color-mix(in srgb, __MUTED__ 6%, transparent); }
.vu-lecture b { color: __TEXT__ !important; }

/* Indicateurs de la zone */
.vu-dl { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px; margin-top: 12px;
  overflow: hidden; }
.vu-dl-row { display: grid; grid-template-columns: 1fr auto; gap: 2px 12px; padding: 10px 16px;
  border-bottom: 1px solid __BORDER__; }
.vu-dl-row:last-child { border-bottom: none; }
.vu-dl-row span { font-size: .78rem; color: __TEXT__ !important; }
.vu-dl-row b { font-size: .84rem; text-align: right; font-variant-numeric: tabular-nums;
  color: __TEXT__ !important; }
.vu-dl-row small { grid-column: 1 / -1; font-size: .66rem; color: __MUTED__ !important; }
.vu-note { font-size: .72rem !important; color: __MUTED__ !important; margin: 8px 2px 0 2px !important;
  line-height: 1.5; }

/* ── Tableau complet ─────────────────────────────────────────────────── */
.vu-tab { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px; overflow: auto;
  margin-top: 6px; }
.vu-tab table { width: 100%; border-collapse: collapse; }
.vu-tab th { position: sticky; top: 0; z-index: 1; padding: 9px 11px; font-size: .64rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .6px; white-space: nowrap; color: __MUTED__ !important;
  background: __CARD__; border-bottom: 1px solid __BORDER__; }
.vu-tab td { padding: 8px 11px; font-size: .79rem; white-space: nowrap; color: __TEXT__ !important;
  border-bottom: 1px solid __BORDER__; font-variant-numeric: tabular-nums; }
.vu-tab tbody tr:hover td { background: color-mix(in srgb, #6366F1 6%, transparent); }
.vu-tab tr.vu-sel td { background: color-mix(in srgb, #F59E0B 16%, transparent) !important; }
.vu-tab tr.vu-sel td:first-child { box-shadow: inset 3px 0 0 #F59E0B; }
.vu-mini { display: inline-flex; align-items: center; gap: 7px; }
.vu-mini i { display: inline-block; width: 46px; height: 5px; border-radius: 999px; position: relative;
  background: color-mix(in srgb, __MUTED__ 20%, transparent); overflow: hidden; }
.vu-mini i::after { content: ""; position: absolute; inset: 0 auto 0 0; width: var(--w);
  border-radius: 999px; background: var(--c); }

/* ── Methode, sources, limites ───────────────────────────────────────── */
.vu-grid3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.vu-card { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px; padding: 16px 18px;
  position: relative; overflow: hidden; }
.vu-card::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px;
  background: var(--c); opacity: .85; }
.vu-card-hd { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.vu-card-hd .material-symbols-rounded { font-size: 19px; color: var(--c) !important; border-radius: 10px;
  padding: 7px; background: color-mix(in srgb, var(--c) 14%, transparent); }
.vu-card-hd p { margin: 0 !important; font-weight: 800; font-size: .9rem !important;
  color: __TEXT__ !important; }
.vu-card ul { margin: 0; padding-left: 16px; }
.vu-card li, .vu-card p.vu-txt { font-size: .78rem !important; line-height: 1.6;
  color: __TEXT__ !important; margin: 0 0 6px 0 !important; }
.vu-card li b, .vu-card p.vu-txt b { color: __TEXT__ !important; }
.vu-formule { font-size: .95rem; font-weight: 800; text-align: center; padding: 10px; border-radius: 10px;
  margin-bottom: 10px; color: __TEXT__ !important; background: color-mix(in srgb, #4F46E5 9%, transparent); }

@keyframes vu-monte { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes vu-pousse { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) { .vu-fiche, .vu-jauge > i { animation: none !important; } }
@media (max-width: 520px) {
  .vu-fiche-hd { padding: 18px 16px 14px 16px; gap: 14px; }
  .vu-anneau { width: 78px; height: 78px; } .vu-anneau > div { width: 60px; height: 60px; }
  .vu-comps { padding: 4px 16px 14px 16px; } .vu-lecture { margin: 0 16px 16px 16px; }
}
</style>
"""


def _e(texte):
    return html.escape(str(texte))


def _fr(x, d=2):
    try:
        return ("%%.%df" % d % float(x)).replace(".", ",").replace("-", "−")
    except (TypeError, ValueError):
        return "n/d"


def _entier(n):
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "n/d"


def _md(texte):
    st.markdown(texte, unsafe_allow_html=True)


def _ic(nom):
    return f'<span class="material-symbols-rounded">{nom}</span>'


def _section(icone, titre, sous_titre=""):
    _md(f'<div class="vu-sec"><p class="vu-sec-ttl">{_ic(icone)}{_e(titre)}</p>'
        + (f'<p class="vu-sec-sub">{sous_titre}</p>' if sous_titre else "") + '</div>')


def _part(x):
    """Valeur 0-1 en pourcentage de largeur (NaN -> 0)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if x != x else max(0.0, min(1.0, x)) * 100


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
        # Contour de la zone choisie : trace transparente au trait epais (ambre,
        # la couleur de la zone choisie partout sur la page).
        fig.add_trace(go.Choroplethmap(
            geojson=geo, featureidkey="properties.pcode", locations=sel["pcode"],
            z=[0], colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
            showscale=False, marker=dict(line=dict(width=3.5, color=AMBER)),
            hoverinfo="skip"))
    fig.update_layout(map=du.basemap(*du.SENEGAL_CENTRE, du.SENEGAL_ZOOM, dark=dark_mode),
                      margin=dict(l=0, r=0, t=0, b=0), height=500,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=CARD, font_color=TEXT, font_size=12),
                      clickmode="event+select")
    return fig


# =============================================================================
# Fiche de la zone
# =============================================================================
def _fiche(z, t, niveau):
    n = len(t)
    rang = int(z["rang"]) if z["rang"] == z["rang"] else None
    if rang is not None and rang <= max(3, round(n * 0.1)):
        c_rang, ic_rang, lib_rang = "#F43F5E", "priority_high", "parmi les plus exposées"
    elif rang is not None and rang <= n // 3:
        c_rang, ic_rang, lib_rang = AMBER, "trending_up", "tiers supérieur"
    else:
        c_rang, ic_rang, lib_rang = "#64748B", "remove", "hors du tiers supérieur"
    cadre = ("Arrondissement de %s · %s" % (z["departement"], z["region"])
             if niveau == "arrondissements" else "Département · région de %s" % z["region"])

    comps = [
        ("alea", "Aléa", z["A_alea"], "%s j/an > 2σ · %s j/an ≥ 50 mm · %s" % (
            _fr(z["jours_anomalie_2sigma_an"]), _fr(z["jours_50mm_an"]), SRC_ALEA)),
        ("exposition", "Exposition", z["E_exposition"], "%s hab. · %s hab/km² · %s" % (
            _entier(z["population_2023"]), _entier(z["densite_2023_hab_km2"]), SRC_POP)),
        ("vulnerabilite", "Vulnérabilité (provisoire)", z["V_vulnerabilite"],
         "pauvreté %s %% (région) · croissance %s %% en 10 ans" % (
             _fr(z["taux_pauvrete_region_pct"], 1), _fr(z["croissance_2013_2023_pct"], 1))),
    ]
    barres = "".join(
        f'<div class="vu-comp" style="--c:{STYLE_COMP[k][0]}">{_ic(STYLE_COMP[k][1])}<div>'
        f'<div class="vu-comp-hd"><span>{_e(lib)}</span><b>{_fr(val)}</b></div>'
        f'<div class="vu-jauge"><i style="width:{_part(val):.0f}%"></i></div>'
        f'<small>{_e(note)}</small></div></div>'
        for k, lib, val, note in comps)
    # Ce qui tire l'indice : la moyenne geometrique est surtout sensible a la plus faible.
    valides = [(lib.split(" (")[0], float(val)) for _, lib, val, _ in comps if val == val]
    lecture = ""
    if len(valides) == 3:
        fort = max(valides, key=lambda x: x[1])
        faible = min(valides, key=lambda x: x[1])
        lecture = (f'<div class="vu-lecture">Composante la plus forte : <b>{_e(fort[0])}</b> '
                   f'({_fr(fort[1])}) · la plus faible : <b>{_e(faible[0])}</b> '
                   f'({_fr(faible[1])}), celle qui pèse le plus sur l\'indice (moyenne '
                   f'géométrique).</div>')
    _md(f'<div class="vu-fiche"><div class="vu-fiche-hd">'
        f'<div class="vu-anneau" style="--p:{_part(z["indice_risque"]):.0f}"><div>'
        f'<b>{_fr(z["indice_risque"])}</b><span>indice</span></div></div>'
        f'<div><p class="vu-nom">{_e(z["nom"])}</p>'
        f'<p class="vu-cadre">{_e(cadre)} · P-code {_e(z["pcode"])}</p>'
        f'<span class="vu-rang" style="--c:{c_rang}">{_ic(ic_rang)}Rang {_entier(z["rang"])} / {n}'
        f' · {_e(lib_rang)}</span></div></div>'
        f'<div class="vu-comps">{barres}</div>{lecture}</div>')

    lignes = [
        ("Population 2023", _entier(z["population_2023"]), SRC_POP),
        ("Population 2013", _entier(z["population_2013"]), SRC_POP13),
        ("Superficie", "%s km²" % _entier(z["superficie_km2"]), SRC_CONTOURS.split(",")[0]),
        ("Pauvreté (région)", "%s %%" % _fr(z["taux_pauvrete_region_pct"], 1), SRC_PAUV),
        ("Pauvres estimés", _entier(z["pauvres_estimes_2023"]), "population × taux régional"),
    ]
    # API SDMX de l'ANSD (Open Data Platform, scripts 35 a 37) : population projetee
    # (departements) ; profondeur et severite de la pauvrete, qui disent a quel point
    # les pauvres le sont. Elles n'entrent pas dans l'indice.
    proj = du.load_population_projetee()
    if niveau == "departements" and proj is not None and z["pcode"] in proj.index:
        lignes.insert(1, ("Population 2026 (projection)",
                          _entier(proj.loc[z["pcode"], "population_2026"]),
                          "ANSD, projections 2023-2030, API SDMX"))
    pauv = (du.load_pauvrete_ansd() or {}).get(str(z["pcode"])[:4])
    if pauv and "profondeur" in pauv:
        i = next(k for k, l in enumerate(lignes) if l[0] == "Pauvres estimés")
        lignes[i:i] = [
            ("Profondeur de la pauvreté (région)", "%s %%" % _fr(pauv["profondeur"], 1),
             "ANSD, EHCVM 2021-22, API SDMX"),
            ("Sévérité de la pauvreté (région)", "%s %%" % _fr(pauv["severite"], 1),
             "ANSD, EHCVM 2021-22, API SDMX"),
        ]
        if "taux_2011" in pauv:
            lignes.insert(i + 2, ("Taux de pauvreté 2011 → 2019 → 2022 (région)",
                                  " → ".join("%s %%" % _fr(pauv[k], 1) for k in
                                             ("taux_2011", "taux_2019", "taux"))
                                  if "taux_2019" in pauv else "%s %%" % _fr(pauv["taux_2011"], 1),
                                  "ANSD, ESPS 2011 et EHCVM, API SDMX"))
    if niveau == "arrondissements" and "indice_departement" in z:
        lignes.append(("Indice du département", "%s (rang %s / 46)" % (
            _fr(z["indice_departement"]), _entier(z["rang_departement"])), "script 26"))
    _md('<div class="vu-dl">' + "".join(
        f'<div class="vu-dl-row"><span>{_e(a)}</span><b>{_e(b)}</b><small>{_e(c)}</small></div>'
        for a, b, c in lignes) + '</div>')
    if str(z.get("methode_alea", "")).startswith("pixel terrestre"):
        _md('<p class="vu-note">Zone plus petite qu\'un pixel CHIRPS (0,25°, ~770 km²) : '
            'l\'aléa est celui du pixel terrestre le plus proche, partagé avec ses voisines.</p>')


# =============================================================================
# Classement
# =============================================================================
def _mini(val, cle):
    return (f'<span class="vu-mini"><i style="--w:{_part(val):.0f}%;--c:{STYLE_COMP[cle][0]}">'
            f'</i>{_fr(val)}</span>')


def _top10(t, colonne, libelle, cle_comp, zone, plotly_base, TEXT, BORDER):
    top = t.sort_values(colonne, ascending=False).head(10).iloc[::-1]
    c = STYLE_COMP[cle_comp][0]
    couleurs = [AMBER if p == zone else c for p in top["pcode"]]
    fig = go.Figure(go.Bar(
        x=top[colonne], y=top["nom"] + " (" + top["region"].astype(str) + ")",
        orientation="h", marker=dict(color=couleurs, cornerradius=5),
        text=top[colonne].map(_fr), textposition="outside",
        textfont=dict(color=TEXT, size=11), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>" + _e(libelle) + " : %{x:.2f}<extra></extra>"))
    plotly_base(fig, h=360)
    fig.update_layout(xaxis=dict(range=[0, 1.12], showgrid=True, gridcolor=BORDER,
                                 tickformat=".2f"), yaxis=dict(showgrid=False),
                      bargap=0.32, margin=dict(l=10, r=30, t=8, b=24), separators=", ")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="vul_top10")
    if zone not in set(top["pcode"]):
        rg = int(t.sort_values(colonne, ascending=False)["pcode"].tolist().index(zone)) + 1
        _md(f'<p class="vu-note">La zone choisie est au rang {rg} / {len(t)} pour cette '
            f'composante (en ambre quand elle figure dans le top 10).</p>')


def _tableau_complet(t, niveau, zone):
    t1, t2, _ = st.columns([1.2, 1, 2], gap="small", vertical_alignment="bottom")
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
    n_texte = 4 if niveau == "arrondissements" else 3
    th = "".join(f'<th style="text-align:{"left" if 0 < i < n_texte else "right"}">{_e(h)}</th>'
                 for i, h in enumerate(entetes))
    corps = []
    for _, r in tt.iterrows():
        cellules = ([_e(_entier(r["rang"])), "<b>%s</b>" % _e(r["nom"])]
                    + ([_e(r["departement"])] if niveau == "arrondissements" else [])
                    + [_e(r["region"]), _mini(r["indice_risque"], "indice"),
                       _mini(r["A_alea"], "alea"), _mini(r["E_exposition"], "exposition"),
                       _mini(r["V_vulnerabilite"], "vulnerabilite"),
                       _e(_entier(r["population_2023"])), _e(_entier(r["densite_2023_hab_km2"])),
                       "%s %%" % _fr(r["croissance_2013_2023_pct"], 1),
                       "%s %%" % _fr(r["taux_pauvrete_region_pct"], 1)])
        corps.append(f'<tr class="{"vu-sel" if r["pcode"] == zone else ""}">' + "".join(
            f'<td style="text-align:{"left" if 0 < i < n_texte else "right"}">{v}</td>'
            for i, v in enumerate(cellules)) + "</tr>")
    _md(f'<div class="vu-tab" style="max-height:460px"><table><thead><tr>{th}</tr></thead>'
        f'<tbody>{"".join(corps)}</tbody></table></div>')
    st.caption("\\* Vulnérabilité provisoire. Ligne en ambre : zone choisie. Les mini-barres "
               "donnent le rang centile (0 à 1).")
    fichier = ("indice_risque_departements.csv" if niveau == "departements"
               else "indice_risque_arrondissements.csv")
    st.download_button("Télécharger le tableau (CSV)",
                       (du.VULNERABILITE / fichier).read_bytes(), file_name=fichier,
                       mime="text/csv", key="vul_dl", icon=":material/download:")


# =============================================================================
# Communes
# =============================================================================
INDICATEURS_COMMUNES = {
    # cle -> (libelle, unite, echelle logarithmique)
    "population_2023": ("Population 2023", "hab.", True),
    "population_2026": ("Population 2026 (projection ANSD)", "hab.", True),
    "densite_hab_km2": ("Densité 2023", "hab./km²", True),
    "jours_extremes_par_an": ("Jours de pluie extrême par an", "jours/an", False),
}
VUES_COMMUNES = {"senegal": ("Sénégal", du.SENEGAL_CENTRE, du.SENEGAL_ZOOM),
                 "dakar": ("Région de Dakar", (14.76, -17.33), 9.4)}


def _communes(dark_mode, TEXT, MUTED, CARD, BORDER):
    """Carte des 552 communes actuelles (script 34) : contours APPROXIMATIFS reconstruits
    a partir des coordonnees des localites transmises par l'ANSD, indicateurs RGPH-5."""
    import numpy as np
    import pandas as pd
    geo = du.load_communes_reconstruites()
    if geo is None:
        return
    lignes = []
    for k, f in enumerate(geo["features"]):
        f["properties"]["id_com"] = k        # identifiant stable pour Plotly
        lignes.append(f["properties"])
    c = pd.DataFrame(lignes)
    # Population projetee par l'ANSD pour 2026 (API SDMX de l'ANSD, script 37).
    proj = du.load_population_projetee()
    codes = [du.code_commune(a, n) for a, n in zip(c["adm2_pcode"], c["commune_ansd"])]
    c["population_2026"] = (pd.Series(codes, index=c.index).map(proj["population_2026"])
                            if proj is not None else np.nan)

    _section("location_city", "Les %d communes" % len(c),
             "Contours approximatifs reconstruits à partir des coordonnées des localités "
             "transmises par l'ANSD · population ANSD RGPH-5 2023 et projection 2026 "
             "(API SDMX de l'ANSD) · pluie CHIRPS 1981-2023")
    c1, c2 = st.columns([1.3, 1], gap="small", vertical_alignment="bottom")
    with c1:
        cle = st.selectbox("Indicateur", list(INDICATEURS_COMMUNES), key="vul_com_indic",
                           format_func=lambda k: INDICATEURS_COMMUNES[k][0])
    with c2:
        vue = st.radio("Vue", list(VUES_COMMUNES), key="vul_com_vue", horizontal=True,
                       format_func=lambda k: VUES_COMMUNES[k][0])
    libelle, unite, log = INDICATEURS_COMMUNES[cle]
    val = pd.to_numeric(c[cle], errors="coerce")
    z = np.log10(val.clip(lower=1)) if log else val
    if log:
        ticks = [10 ** p for p in range(int(np.floor(z.min())), int(np.ceil(z.max())) + 1)]
        barre = dict(tickvals=[np.log10(t) for t in ticks],
                     ticktext=[f"{t:,}".replace(",", " ") for t in ticks])
    else:
        barre = {}
    noms = c["communes_rgph5"].fillna("").where(c["communes_rgph5"].fillna("") != "",
                                                 c["commune_ansd"])
    custom = list(zip(noms.str.title(), c["departement"],
                      c["population_2023"].map(_entier), c["densite_hab_km2"].map(
                          lambda x: _fr(x, 0)), c["jours_extremes_par_an"].map(_fr),
                      c["population_2026"].map(lambda x: _entier(x) if pd.notna(x) else "n.d.")))
    echelle = ECHELLE_SOMBRE if dark_mode else ECHELLE_CLAIRE
    fig = go.Figure(go.Choroplethmap(
        geojson=geo, featureidkey="properties.id_com", locations=c["id_com"], z=z,
        colorscale=echelle, marker=dict(line=dict(width=0.3, color=CARD), opacity=0.9),
        customdata=custom,
        hovertemplate=("<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                       "Population 2023 : %{customdata[2]}<br>"
                       "Population 2026 (projection ANSD) : %{customdata[5]}<br>"
                       "Densité : %{customdata[3]} hab./km²<br>"
                       "Pluie extrême : %{customdata[4]} jours/an<extra></extra>"),
        colorbar=dict(title=dict(text=_e(unite), font=dict(size=10, color=MUTED)),
                      thickness=12, len=0.7, tickfont=dict(size=10, color=MUTED),
                      outlinewidth=0, **barre),
    ))
    _, centre, zoom = VUES_COMMUNES[vue]
    fig.update_layout(map=du.basemap(*centre, zoom, dark=dark_mode),
                      margin=dict(l=0, r=0, t=0, b=0), height=480,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=CARD, font_color=TEXT, font_size=12))
    st.plotly_chart(fig, width="stretch", key="vul_carte_communes",
                    config={"displaylogo": False})
    st.caption("Les limites entre communes passent à mi-distance des localités voisines : "
               "elles sont approximatives, pas officielles (aucun contour officiel à jour "
               "n'est diffusé en données ouvertes). Jours de pluie extrême : moyenne vécue "
               "par les habitants de la commune, pixels CHIRPS de 27 km environ.")


# =============================================================================
# Methode, sources, limites
# =============================================================================
def _methode(v, t, niveau):
    r_dep = v.get("resume") or {}
    r_arr = v.get("resume_arrondissements") or {}
    n_pixel = (len(r_arr.get("arrondissements_pixel_le_plus_proche") or [])
               if niveau == "arrondissements"
               else len(r_dep.get("departements_pixel_le_plus_proche") or []))
    couverture = (r_arr.get("couverture_population") or {}).get("2023", {}).get("part_pct")
    pauv_dakar = t.loc[t["region"] == "Dakar", "taux_pauvrete_region_pct"].min()

    methode = (
        '<div class="vu-formule">Indice = (A × E × V)<sup>1/3</sup></div>'
        '<ul><li><b>Moyenne géométrique</b> : une zone ne ressort que si elle cumule aléa, '
        'exposition et vulnérabilité ; une composante très faible suffit à la faire baisser.</li>'
        '<li><b>Rang centile</b> sur les zones du niveau (0 = plus faible, 1 = plus fort), '
        'robuste aux valeurs extrêmes (Dakar, Touba). Une composante à deux indicateurs est la '
        'moyenne de leurs rangs centiles, remise en rang centile.</li>'
        f'<li><b>Aléa (A)</b> : jours par an où l\'anomalie dépasse +2σ et jours ≥ 50 mm, '
        f'mai-octobre {_e(r_dep.get("periode_alea", "1981-2023"))} (CHIRPS 0,25°).</li>'
        '<li><b>Exposition (E)</b> : population et densité 2023 (ANSD RGPH-5 ; superficie OCHA).</li>'
        '<li><b>Vulnérabilité (V), provisoire</b> : pauvreté P0 de la région (ANSD EHCVM '
        '2021-2022) et croissance de la population 2013-2023 (ANSD RGPH), indicateur '
        'd\'urbanisation rapide.</li></ul>')
    sources = (
        '<ul><li>ANSD, RGPH-5 2023 et RGPH 2013, Répertoire des localités</li>'
        '<li>ANSD, EHCVM 2021-2022, Rapport final, Tableau III-2</li>'
        f'<li>{_e(SRC_CONTOURS)}</li>'
        '<li>CHIRPS v2 (UCSB Climate Hazards Center), 1981-2023</li>'
        + ('<li>Rattachement des communes aux arrondissements : GADM 4.1 et © OpenStreetMap '
           '(ODbL), couverture de la population %s %%</li>' % _fr(couverture, 1)
           if niveau == "arrondissements" and couverture is not None else '')
        + '</ul>')
    limites = (
        '<ul><li>La vulnérabilité est provisoire, en attendant les données d\'habitat du RGPH-5 '
        '(logement, assainissement).</li>'
        '<li>La pauvreté n\'est connue qu\'à l\'échelle régionale : toutes les zones d\'une '
        'région ont la même valeur, ce qui place les zones de la région de Dakar '
        f'({_fr(pauv_dakar, 1)} %, le taux le plus bas) au plus bas de la vulnérabilité.</li>'
        '<li>La croissance 2013-2023 repère l\'urbanisation récente (Rufisque, Keur Massar), '
        'pas les quartiers inondables plus anciens : Pikine et Guédiawaye restent bas, '
        'contrairement aux inondations de 2005, 2009, 2012 et 2020. Les poids n\'ont pas été '
        'ajustés pour corriger ce classement.</li>'
        f'<li>{n_pixel} zones sont plus petites qu\'un pixel CHIRPS : leur aléa est celui du '
        'pixel terrestre le plus proche.</li>'
        '<li>L\'indice classe les zones entre elles ; il ne mesure ni une probabilité ni des '
        'dégâts.</li></ul>')
    cartes = [("functions", INDIGO, "Méthode", methode),
              ("menu_book", "#0EA5E9", "Sources", sources),
              ("report", AMBER, "Limites", limites)]
    _section("science", "Méthode, sources et limites")
    _md('<div class="vu-grid3">' + "".join(
        f'<div class="vu-card" style="--c:{c}"><div class="vu-card-hd">{_ic(ic)}<p>{_e(titre)}</p>'
        f'</div>{corps}</div>' for ic, c, titre, corps in cartes) + '</div>')


# =============================================================================
# Page
# =============================================================================
def run(BG, CARD, TEXT, MUTED, BORDER, dark_mode=False, **kw):

    def plotly_base(fig, h=300):
        return du.plotly_base(fig, h, muted=MUTED, border=BORDER, text=TEXT, card=CARD)

    _md(CSS.replace("__CARD__", CARD).replace("__BORDER__", BORDER).replace("__TEXT__", TEXT)
           .replace("__MUTED__", MUTED).replace("__BG__", BG))
    _md("""
    <div class="pg-hdr"><div>
      <h1 class="pg-ttl">Vulnérabilité · où les pluies extrêmes font le plus de dégâts</h1>
      <p class="pg-sub">Indice de risque = (Aléa × Exposition × Vulnérabilité)<sup>1/3</sup>
      · CHIRPS, ANSD RGPH-5 et EHCVM, contours OCHA</p>
    </div></div>
    """)

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

    # ── Barre de commandes ──────────────────────────────────────────────────
    c1, c2, c3 = st.columns([1.15, 1.1, 1.4], gap="small", vertical_alignment="bottom")
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

    _md(f'<div class="vu-alerte">{_ic("warning")}<p><b>Vulnérabilité provisoire.</b> Elle '
        'combine la pauvreté EHCVM, connue seulement par région (même valeur pour toutes les '
        'zones d\'une région), et la croissance de la population 2013-2023. Elle sera remplacée '
        'par les données d\'habitat du RGPH-5. L\'indice classe les zones entre elles : ce '
        'n\'est ni une probabilité ni un nombre de sinistrés.</p></div>')

    # ── Chiffres clefs ──────────────────────────────────────────────────────
    tete = t.iloc[0]
    type_zone = NIVEAUX[niveau].split(" (")[0].lower()
    tuiles = [
        ("crisis_alert", "#F43F5E", "Indice le plus élevé", tete["nom"],
         "%s · indice %s" % (tete.get("region", ""), _fr(tete["indice_risque"])), "t-amber"),
        ("map", INDIGO, "Zones classées", str(len(t)), type_zone + " · contours OCHA", "t-indigo"),
        ("groups", "#A855F7", "Population couverte", _entier(t["population_2023"].sum()),
         "ANSD, RGPH-5 2023", "t-indigo"),
        ("my_location", AMBER, "Zone choisie", z["nom"],
         "rang %s / %d · indice %s" % (_entier(z["rang"]), len(t), _fr(z["indice_risque"])),
         "t-amber"),
    ]
    for col, (ic, c, lbl, val, sub, tag) in zip(st.columns(4, gap="small"), tuiles):
        col.markdown(
            f'<div class="kpi"><div class="kpi-body">'
            f'<div class="kpi-icon" style="background:{c}22;color:{c}">{_ic(ic)}</div>'
            f'<p class="kpi-lbl">{_e(lbl)}</p><p class="kpi-val">{_e(val)}</p>'
            f'<span class="kpi-tag {tag}">{_e(sub)}</span></div></div>', unsafe_allow_html=True)

    # ── Carte + fiche de la zone ────────────────────────────────────────────
    g, d = st.columns([1.45, 1], gap="large")
    with g:
        _section(STYLE_COMP[cle_comp][1], "%s · %s" % (libelle, NIVEAUX[niveau]),
                 "Rang centile parmi les zones du niveau : 0 = plus faible, 1 = plus fort · "
                 "<b>cliquer sur une zone</b> pour afficher sa fiche · contour ambre : zone "
                 "choisie")
        geo = du.load_contours_simplifies("admin2" if niveau == "departements" else "admin3")
        if geo is None:
            st.info("Contours absents. Lancer : py -3 scripts/28_contours_simplifies.py")
        else:
            fig = _carte(t, geo, colonne, libelle, zone, dark_mode, TEXT, MUTED, CARD)
            st.plotly_chart(fig, width="stretch", key="vul_carte",
                            on_select="rerun", selection_mode="points",
                            config=dict(du.CARTE_CONFIG, toImageButtonOptions={
                                "format": "png", "filename": "vulnerabilite_%s_%s" % (
                                    niveau, cle_comp)}))
            st.caption("Molette ou pincement : zoom · glisser : déplacer · ⌂ : revenir au "
                       "Sénégal entier · Contours : " + SRC_CONTOURS)
    with d:
        _section("pin_drop", "Fiche de la zone")
        _fiche(z, t, niveau)

    # ── Classement ──────────────────────────────────────────────────────────
    _section("leaderboard", "Classement",
             "%s · rang centile (0 à 1) parmi les %d %s" % (_e(libelle), len(t), _e(type_zone)))
    o1, o2 = st.tabs(["Les 10 zones où %s" % TITRES_TOP[cle_comp], "Tableau complet"])
    with o1:
        _top10(t, colonne, libelle, cle_comp, zone, plotly_base, TEXT, BORDER)
    with o2:
        _tableau_complet(t, niveau, zone)

    # ── Communes : contours reconstruits a partir des localites de l'ANSD ───
    _communes(dark_mode, TEXT, MUTED, CARD, BORDER)

    # ── Methode, sources, limites ───────────────────────────────────────────
    _methode(v, t, niveau)
