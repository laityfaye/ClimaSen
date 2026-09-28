"""Page Accueil : vitrine de ClimatSen (suivi de revue 28/09/2026, point S3,
option A ; refonte visuelle demandee par Laity le 28/09/2026).

Bandeau anime avec la courbe des saisons, chiffres cles, trois decouvertes
CALCULEES a partir des donnees (jamais ecrites en dur : elles suivent le
catalogue et les correlations du script 04), parcours de la methode, etat de
la veille et une carte cliquable par section.

Le logo de la barre laterale et le premier element du fil d'Ariane menent ici.
Les liens sont des st.page_link : ils changent l'URL sans recharger
l'application, donc la session (administrateur, filtres) est conservee.

Le theme sombre du dashboard force la couleur de tout texte (p, span, div) avec
!important : les regles de cette page sont donc prefixees par des id (#acc-...)
pour l'emporter.
"""
import html
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

RACINE = Path(__file__).resolve().parent.parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# (cle de page, icone Material, accroche, description) dans l'ordre d'affichage.
SECTIONS = (
    ("Evenements", "rainy", "Explorer",
     "Les {n} événements détectés : carte, fiche détaillée et régions les plus touchées."),
    ("Teleconnexions", "hub", "Comprendre",
     "Quels océans, et avec combien de mois d'avance, pèsent sur l'intensité des extrêmes."),
    ("Veille", "notifications", "Anticiper",
     "Le bulletin de risque d'année extrême, avant la saison des pluies."),
    ("Indices SST", "waves", "Observer",
     "Les 11 indices de température de surface de la mer, de 1983 à 2023."),
    ("Clustering", "bubble_chart", "Classer",
     "Les configurations océaniques types présentes les jours d'extrême."),
    ("A propos", "info", "Découvrir",
     "Les données, les limites de la méthode et l'équipe du projet."),
)

NOMS_INDICES = {
    "AMO": "l'Atlantique Nord (AMO)", "AMM": "le dipôle méridien atlantique (AMM)",
    "TNA": "l'Atlantique tropical nord (TNA)", "TSA": "l'Atlantique tropical sud (TSA)",
    "ATL3": "le golfe de Guinée (ATL3)", "Nino12": "le Pacifique est (Niño 1+2)",
    "Nino3": "le Pacifique central-est (Niño 3)", "Nino34": "le Pacifique central (Niño 3.4)",
    "Nino4": "le Pacifique ouest (Niño 4)", "IOD": "le dipôle de l'océan Indien (IOD)",
    "IOBM": "l'océan Indien (IOBM)",
}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def _fr(x, d=2):
    return ("%%.%df" % d % x).replace(".", ",").replace("-", "−")


def _entier(n):
    return f"{int(n):,}".replace(",", " ")


@st.cache_data(ttl=300)
def _etat_veille():
    """(saison, titre, valeur, note) du bulletin le plus recent, ou None."""
    try:
        from veille import production
        from veille import bulletin as mod_bulletin
        annees = production.bulletins_disponibles()
        if not annees:
            return None
        b = production.lire_bulletin(annees[0])
        pres = b.get("presentation") or mod_bulletin.presentation(b["niveau_risque"])
        if pres["mode"] == "indetermine" and not b.get("verification"):
            return (annees[0], pres["titre"], None,
                    "premier bulletin provisoire début décembre %d" % (annees[0] - 1))
        return annees[0], pres["titre"], pres["valeur"], pres["note"]
    except Exception:                              # noqa: BLE001
        return None


@st.cache_data(ttl=600)
def _signal_oceanique():
    """Correlation la plus forte (|r|, p_neff < 0,05) sur max_precip en pleine
    saison, lue dans les sorties du script 04. None si indisponible."""
    try:
        import dashboard_utils as du
        d = du.load_telecon().get("Phase_2_pleine")
        if d is None or d.empty:
            return None
        d = d[(d["metric"] == "max_precip") & (d["pearson_p_neff"] < 0.05)]
        if d.empty:
            return None
        r = d.loc[d["pearson_r"].abs().idxmax()]
        return str(r["index"]), int(r["lag_months"]), float(r["pearson_r"])
    except Exception:                              # noqa: BLE001
        return None


def _courbe_svg(par_an):
    """Courbe animee du nombre d'evenements par saison (SVG en ligne)."""
    annees = list(par_an.index)
    v = par_an.values.astype(float)
    W, H, PX, PY = 560, 210, 14, 26
    vmax = max(v.max(), 1)

    def x(i):
        return PX + i * (W - 2 * PX) / max(len(v) - 1, 1)

    def y(val):
        return H - PY - val / vmax * (H - 2 * PY)

    pts = [(x(i), y(val)) for i, val in enumerate(v)]
    ligne = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    aire = ligne + f" L{pts[-1][0]:.1f},{H - PY} L{pts[0][0]:.1f},{H - PY} Z"
    pente, orig = np.polyfit(np.arange(len(v)), v, 1)
    t0, t1 = y(orig), y(orig + pente * (len(v) - 1))
    i_max = int(np.argmax(v))
    xm, ym = pts[i_max]
    return f"""
<svg viewBox="0 0 {W} {H}" class="acc-courbe" role="img"
     aria-label="Nombre d'événements extrêmes par saison, {annees[0]}-{annees[-1]}">
  <defs>
    <linearGradient id="acc-aire" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#38BDF8" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#38BDF8" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="acc-trait" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#A5B4FC"/><stop offset="100%" stop-color="#38BDF8"/>
    </linearGradient>
  </defs>
  <path d="{aire}" fill="url(#acc-aire)" class="acc-aire"/>
  <path d="{ligne}" fill="none" stroke="url(#acc-trait)" stroke-width="2.6"
        stroke-linejoin="round" stroke-linecap="round" pathLength="1" class="acc-trace"/>
  <line x1="{pts[0][0]:.1f}" y1="{t0:.1f}" x2="{pts[-1][0]:.1f}" y2="{t1:.1f}"
        stroke="#FBBF24" stroke-width="1.6" stroke-dasharray="5 5" class="acc-tendance"/>
  <circle cx="{xm:.1f}" cy="{ym:.1f}" r="5" fill="#FBBF24" class="acc-pic"/>
  <circle cx="{xm:.1f}" cy="{ym:.1f}" r="5" fill="none" stroke="#FBBF24"
          stroke-width="2" class="acc-onde"/>
  <text x="{xm:.1f}" y="{ym - 12:.1f}" text-anchor="middle" class="acc-pic-txt">
    {annees[i_max]} · {int(v[i_max])}</text>
  <text x="{PX}" y="{H - 6}" class="acc-axe">{annees[0]}</text>
  <text x="{W - PX}" y="{H - 6}" text-anchor="end" class="acc-axe">{annees[-1]}</text>
</svg>""", pente * 10


CSS = """
<style>
/* ── Bandeau d'ouverture ─────────────────────────────────────────────── */
.st-key-acc_hero {
  position: relative; overflow: hidden; border-radius: 22px;
  padding: 34px 36px 30px 36px !important; margin: 6px 0 22px 0;
  background:
    radial-gradient(900px 380px at 88% -10%, rgba(56,189,248,.35), transparent 60%),
    radial-gradient(700px 420px at -10% 110%, rgba(129,140,248,.45), transparent 60%),
    linear-gradient(135deg, #0B1026 0%, #1E1B4B 48%, #0C4A6E 100%);
  box-shadow: 0 24px 60px -24px rgba(30,27,75,.65);
}
/* Pluie : fines trainees obliques qui defilent */
.st-key-acc_hero::before {
  content: ""; position: absolute; inset: -40% -10%; pointer-events: none;
  background-image: repeating-linear-gradient(104deg,
      rgba(255,255,255,.10) 0 1px, transparent 1px 26px);
  mask-image: linear-gradient(180deg, transparent, #000 30%, #000 70%, transparent);
  animation: acc-pluie 1.6s linear infinite; opacity: .55;
}
@keyframes acc-pluie { to { transform: translate3d(-26px, 110px, 0); } }
.st-key-acc_hero > * { position: relative; z-index: 1; }

#acc-hero .acc-badge {
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
  border-radius: 99px; background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.16); color: #C7D2FE !important;
  font-size: .72rem; font-weight: 600; letter-spacing: .3px;
  animation: acc-monte .7s ease both;
}
#acc-hero .acc-point {
  width: 7px; height: 7px; border-radius: 50%; background: #34D399;
  box-shadow: 0 0 0 0 rgba(52,211,153,.7); animation: acc-pouls 2s infinite;
}
@keyframes acc-pouls { 70% { box-shadow: 0 0 0 9px rgba(52,211,153,0); }
                       100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); } }
/* Classe pg-ttl aussi : Jarvis repere la page et son titre par .pg-ttl. */
#acc-hero .acc-titre {
  font-size: clamp(1.75rem, 3.3vw, 2.9rem) !important; line-height: 1.08 !important;
  font-weight: 800 !important; letter-spacing: -1.2px; margin: 18px 0 14px 0 !important;
  color: #FFFFFF !important; animation: acc-monte .8s .1s ease both;
}
#acc-hero .acc-degrade {
  background: linear-gradient(90deg, #7DD3FC, #A5B4FC 45%, #F0ABFC);
  -webkit-background-clip: text; background-clip: text;
  color: transparent !important; -webkit-text-fill-color: transparent;
}
#acc-hero p.acc-sous {
  color: #CBD5E1 !important; font-size: 1rem; line-height: 1.6; max-width: 560px;
  margin: 0 0 6px 0; animation: acc-monte .8s .2s ease both;
}
@keyframes acc-monte { from { opacity: 0; transform: translateY(14px); }
                       to { opacity: 1; transform: none; } }

/* Boutons d'appel (st.page_link) */
.st-key-acc_cta { gap: 10px !important; margin-top: 14px; animation: acc-monte .8s .3s ease both; }
.st-key-acc_cta [data-testid="stPageLink"] a {
  padding: 11px 20px !important; border-radius: 12px !important;
  border: 1px solid rgba(255,255,255,.22) !important;
  background: rgba(255,255,255,.08) !important; transition: all .2s ease;
}
/* Le premier bouton est l'appel principal, le second reste en verre depoli. */
.st-key-acc_cta > [data-testid="stElementContainer"]:first-child [data-testid="stPageLink"] a {
  background: linear-gradient(135deg, #6366F1, #0EA5E9) !important; border-color: transparent !important;
  box-shadow: 0 10px 26px -10px rgba(99,102,241,.9);
}
.st-key-acc_cta [data-testid="stPageLink"] a:hover {
  transform: translateY(-2px); background: rgba(255,255,255,.16) !important;
}
.st-key-acc_cta [data-testid="stPageLink"] a p,
.st-key-acc_cta [data-testid="stPageLink"] a span {
  color: #FFFFFF !important; font-weight: 700 !important; font-size: .88rem !important;
}

/* Courbe des saisons */
#acc-courbe .acc-carte-courbe {
  background: rgba(15,23,42,.45); border: 1px solid rgba(255,255,255,.12);
  border-radius: 18px; padding: 16px 16px 8px 16px; backdrop-filter: blur(6px);
  animation: acc-monte .9s .25s ease both;
}
#acc-courbe .acc-leg { color: #CBD5E1 !important; font-size: .74rem; font-weight: 600; margin: 0; }
#acc-courbe .acc-leg b { color: #FFFFFF !important; }
#acc-courbe .acc-leg-bas { color: #94A3B8 !important; font-size: .7rem; margin: 2px 0 0 0; }
#acc-courbe .acc-leg-bas b { color: #FBBF24 !important; }
.acc-courbe { width: 100%; height: auto; display: block; overflow: visible; }
.acc-courbe .acc-trace { stroke-dasharray: 1; stroke-dashoffset: 1;
                         animation: acc-trace 2.4s .4s cubic-bezier(.6,.1,.3,1) forwards; }
@keyframes acc-trace { to { stroke-dashoffset: 0; } }
.acc-courbe .acc-aire, .acc-courbe .acc-tendance, .acc-courbe .acc-pic,
.acc-courbe .acc-pic-txt { opacity: 0; animation: acc-apparait .8s 2.2s ease forwards; }
@keyframes acc-apparait { to { opacity: 1; } }
.acc-courbe .acc-onde { transform-box: fill-box; transform-origin: center; opacity: 0;
                        animation: acc-onde 2s 2.6s ease-out infinite; }
@keyframes acc-onde { 0% { opacity: .9; transform: scale(1); }
                      100% { opacity: 0; transform: scale(3.2); } }
.acc-courbe .acc-pic-txt { fill: #FDE68A; font-size: 12px; font-weight: 700; }
.acc-courbe .acc-axe { fill: #94A3B8; font-size: 11px; }

/* ── Chiffres cles ───────────────────────────────────────────────────── */
#acc-kpi .acc-grille4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
#acc-kpi .acc-kpi {
  background: __CARD__; border: 1px solid __BORDER__; border-radius: 16px; padding: 18px 20px;
  position: relative; overflow: hidden; animation: acc-monte .7s ease both;
}
#acc-kpi .acc-kpi::after {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: var(--c);
}
#acc-kpi .acc-kpi .material-symbols-rounded {
  font-size: 22px; color: var(--c) !important; background: color-mix(in srgb, var(--c) 14%, transparent);
  border-radius: 10px; padding: 7px;
}
#acc-kpi .acc-val {
  font-size: clamp(1.5rem, 2.4vw, 2.1rem); font-weight: 800; letter-spacing: -1px;
  color: __TEXT__ !important; margin: 12px 0 0 0; line-height: 1.1;
}
#acc-kpi .acc-lib { color: __MUTED__ !important; font-size: .78rem; margin: 3px 0 0 0; }

/* ── Titres de section ───────────────────────────────────────────────── */
.acc-surtitre { color: #6366F1 !important; font-size: .72rem !important; font-weight: 800 !important;
                letter-spacing: 1.6px; text-transform: uppercase; margin: 34px 0 4px 0 !important; }
:is(#acc-t1,#acc-t2,#acc-t3) .acc-h2 {
  color: __TEXT__ !important; font-size: clamp(1.2rem, 2vw, 1.6rem) !important;
  font-weight: 800 !important; letter-spacing: -.5px; margin: 0 0 16px 0 !important; padding: 0 !important;
}
:is(#acc-t1,#acc-t2,#acc-t3) .acc-surtitre { color: #6366F1 !important; }

/* ── Decouvertes ─────────────────────────────────────────────────────── */
#acc-ins .acc-grille3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
#acc-ins .acc-ins {
  border-radius: 18px; padding: 22px; position: relative; overflow: hidden;
  background: linear-gradient(160deg, var(--c1), var(--c2));
  box-shadow: 0 16px 36px -22px var(--c2); animation: acc-monte .7s ease both;
  transition: transform .25s ease;
}
#acc-ins .acc-ins:hover { transform: translateY(-4px); }
#acc-ins .acc-ins::after {
  content: ""; position: absolute; right: -40px; top: -40px; width: 140px; height: 140px;
  border-radius: 50%; background: rgba(255,255,255,.10);
}
#acc-ins .acc-ins-chiffre { color: #FFFFFF !important; font-size: 2.3rem; font-weight: 800;
                            letter-spacing: -1.5px; line-height: 1; margin: 0; }
#acc-ins .acc-ins-titre { color: rgba(255,255,255,.92) !important; font-weight: 700;
                          font-size: .92rem; margin: 12px 0 6px 0; }
#acc-ins .acc-ins-txt { color: rgba(255,255,255,.80) !important; font-size: .8rem;
                        line-height: 1.55; margin: 0; }
#acc-ins .acc-ins .material-symbols-rounded { color: rgba(255,255,255,.9) !important;
                                             font-size: 26px; float: right; }

/* ── Methode en trois temps ──────────────────────────────────────────── */
#acc-met .acc-grille3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
                        position: relative; }
#acc-met .acc-etape {
  background: __CARD__; border: 1px solid __BORDER__; border-radius: 16px;
  padding: 20px; position: relative;
}
#acc-met .acc-num {
  width: 34px; height: 34px; border-radius: 10px; display: flex; align-items: center;
  justify-content: center; font-weight: 800; color: #FFFFFF !important;
  background: linear-gradient(135deg, #6366F1, #0EA5E9); margin-bottom: 12px;
}
#acc-met .acc-etape .acc-et-titre { color: __TEXT__ !important; font-size: 1rem !important;
                         font-weight: 800 !important; margin: 0 0 6px 0 !important; padding: 0 !important; }
#acc-met .acc-etape p:not(.acc-et-titre) { color: __MUTED__ !important; font-size: .8rem; line-height: 1.55; margin: 0; }
#acc-met .acc-fleche { position: absolute; right: -14px; top: 30px; z-index: 2;
                       color: #6366F1 !important; font-size: 22px; }

/* ── Veille ──────────────────────────────────────────────────────────── */
#acc-veille .acc-veille {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  background: __CARD__; border: 1px solid __BORDER__; border-radius: 16px; padding: 16px 20px;
  margin-top: 16px;
}
#acc-veille .acc-veille .material-symbols-rounded {
  color: #F59E0B !important; background: rgba(245,158,11,.14); border-radius: 12px;
  padding: 9px; font-size: 24px;
}
#acc-veille .acc-v-titre { color: __TEXT__ !important; font-weight: 800; font-size: .9rem; margin: 0; }
#acc-veille .acc-v-txt { color: __MUTED__ !important; font-size: .8rem; margin: 2px 0 0 0; }
#acc-veille .acc-v-txt b { color: __TEXT__ !important; }

/* ── Cartes de section, cliquables en entier ─────────────────────────── */
[class*="st-key-acc_sec_"] { position: relative; }
[class*="st-key-acc_sec_"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {
  position: absolute !important; inset: 0; z-index: 3; margin: 0 !important;
  width: 100% !important; max-width: none !important; height: 100% !important;
}
[class*="st-key-acc_sec_"] [data-testid="stPageLink"],
[class*="st-key-acc_sec_"] [data-testid="stPageLink"] * {
  width: 100% !important; max-width: none !important; height: 100% !important;
  opacity: 0; cursor: pointer;
}
.acc-sec {
  background: __CARD__; border: 1px solid __BORDER__; border-radius: 18px; padding: 20px;
  height: 100%; min-height: 150px; transition: transform .25s ease, box-shadow .25s ease,
  border-color .25s ease; position: relative; overflow: hidden;
}
[class*="st-key-acc_sec_"]:hover .acc-sec {
  transform: translateY(-5px); border-color: var(--c);
  box-shadow: 0 18px 40px -22px var(--c);
}
.acc-sec .acc-sec-haut { display: flex; align-items: center; justify-content: space-between; }
[class*="st-key-acc_sec_"] .acc-sec .material-symbols-rounded.acc-ic {
  color: var(--c) !important; background: color-mix(in srgb, var(--c) 14%, transparent);
  border-radius: 12px; padding: 9px; font-size: 24px;
}
[class*="st-key-acc_sec_"] .acc-sec .material-symbols-rounded.acc-go {
  color: __MUTED__ !important; font-size: 20px; transition: transform .25s ease, color .25s ease;
}
[class*="st-key-acc_sec_"]:hover .acc-sec .material-symbols-rounded.acc-go {
  color: var(--c) !important; transform: translateX(4px);
}
[class*="st-key-acc_sec_"] .acc-sec .acc-accroche { color: var(--c) !important; font-size: .7rem;
  font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; margin: 14px 0 2px 0; }
[class*="st-key-acc_sec_"] .acc-sec .acc-nom { color: __TEXT__ !important; font-size: 1.05rem;
  font-weight: 800; margin: 0 0 6px 0; }
[class*="st-key-acc_sec_"] .acc-sec .acc-desc { color: __MUTED__ !important; font-size: .8rem;
  line-height: 1.55; margin: 0; }

/* ── Pied ────────────────────────────────────────────────────────────── */
#acc-pied .acc-pied { color: __MUTED__ !important; font-size: .74rem; text-align: center;
                      margin: 30px 0 6px 0; line-height: 1.7; }
#acc-pied .acc-pied b { color: __TEXT__ !important; }

/* ── Petits ecrans ───────────────────────────────────────────────────── */
@media (max-width: 900px) {
  #acc-kpi .acc-grille4 { grid-template-columns: repeat(2, 1fr); }
  #acc-ins .acc-grille3, #acc-met .acc-grille3 { grid-template-columns: 1fr; }
  #acc-met .acc-fleche { display: none; }
  .st-key-acc_hero { padding: 24px 20px 22px 20px !important; }
}
@media (prefers-reduced-motion: reduce) {
  .st-key-acc_hero::before, #acc-hero *, #acc-courbe *, #acc-kpi *, #acc-ins *,
  .acc-courbe * { animation: none !important; opacity: 1 !important; stroke-dashoffset: 0 !important; }
}
</style>
"""


def _md(texte):
    st.markdown(texte, unsafe_allow_html=True)


def run(BG, CARD, TEXT, MUTED, BORDER, df=None, year_range=None, liens=None,
        query_params=None, **kw):
    e = html.escape
    liens = liens or {}
    a0, a1 = year_range or (1981, 2023)
    df = df if df is not None else pd.DataFrame(columns=["year", "month", "phase"])
    n_ev = len(df)
    par_an = df.groupby("year").size().reindex(range(a0, a1 + 1), fill_value=0)

    _md(CSS.replace("__CARD__", CARD).replace("__BORDER__", BORDER)
           .replace("__TEXT__", TEXT).replace("__MUTED__", MUTED))

    # ── 1. Bandeau d'ouverture ──────────────────────────────────────────
    with st.container(key="acc_hero"):
        gauche, droite = st.columns([1.25, 1], gap="large", vertical_alignment="center")
        with gauche:
            _md(f"""
<div id="acc-hero">
  <span class="acc-badge"><span class="acc-point"></span>
    Mémoire de master · Université Iba Der Thiam de Thiès</span>
  <div class="acc-titre pg-ttl">Quand l'océan annonce<br>
    <span class="acc-degrade">les pluies extrêmes</span> du Sénégal</div>
  <p class="acc-sous">{a1 - a0 + 1} saisons de pluie passées au crible du satellite, reliées
    à la température de trois océans. ClimatSen montre où, quand et avec quelle force
    frappent les extrêmes, et ce que les océans en laissaient deviner.</p>
</div>""")
            with st.container(key="acc_cta", horizontal=True):
                for cle, lib, ic in (("Evenements", "Explorer les événements", "arrow_forward"),
                                     ("Teleconnexions", "Voir le lien avec les océans", "hub")):
                    if cle in liens:
                        st.page_link(liens[cle], label=lib, icon=f":material/{ic}:",
                                     query_params=query_params)
        with droite:
            if len(par_an) > 1 and par_an.sum() > 0:
                svg, pente10 = _courbe_svg(par_an)
                _md(f"""
<div id="acc-courbe"><div class="acc-carte-courbe">
  <p class="acc-leg">Événements extrêmes par saison · <b>{a0}–{a1}</b></p>
  {svg}
  <p class="acc-leg-bas">Tendance : <b>{'+' if pente10 >= 0 else ''}{_fr(pente10, 1)}
    événements par décennie</b> · en jaune, la saison record</p>
</div></div>""")

    # ── 2. Chiffres cles ────────────────────────────────────────────────
    kpis = (
        ("rainy", "#6366F1", _entier(n_ev), "jours de pluie extrême détectés"),
        ("calendar_month", "#0EA5E9", f"{a1 - a0 + 1}", f"saisons étudiées, {a0}–{a1}"),
        ("waves", "#10B981", "11", "indices océaniques suivis"),
        ("travel_explore", "#F59E0B", "3", "océans : Atlantique, Pacifique, Indien"),
    )
    cartes = "".join(
        f'<div class="acc-kpi" style="--c:{c};animation-delay:{0.08 * i:.2f}s">'
        f'<span class="material-symbols-rounded">{ic}</span>'
        f'<p class="acc-val">{e(v)}</p><p class="acc-lib">{e(lib)}</p></div>'
        for i, (ic, c, v, lib) in enumerate(kpis))
    _md(f'<div id="acc-kpi"><div class="acc-grille4">{cartes}</div></div>')

    # ── 3. Decouvertes (calculees) ──────────────────────────────────────
    decouvertes = []
    if n_ev:
        an_max = int(par_an.idxmax())
        decouvertes.append((
            "#6366F1", "#312E81", "local_fire_department", str(an_max),
            "La saison record",
            f"{int(par_an.max())} jours d'extrême en {an_max}, contre "
            f"{_fr(par_an.mean(), 0)} en moyenne par saison."))
        par_mois = df["month"].value_counts()
        coeur = par_mois.reindex([7, 8, 9], fill_value=0).sum() / n_ev
        m_max = int(par_mois.idxmax())
        decouvertes.append((
            "#0EA5E9", "#0C4A6E", "water_drop", f"{round(100 * coeur)} %",
            "Le cœur de la saison",
            f"des extrêmes tombent entre juillet et septembre ; {MOIS[m_max - 1]} "
            f"en concentre le plus."))
    sig = _signal_oceanique()
    if sig:
        idx, lag, r = sig
        sens = "moins" if r < 0 else "plus"
        decouvertes.append((
            "#10B981", "#064E3B", "sailing", f"r = {_fr(r)}",
            "Un signal venu de l'océan",
            f"Plus {NOMS_INDICES.get(idx, idx)} est chaud {lag} mois avant, {sens} les "
            f"pluies maximales de juillet-août sont intenses. Une tendance, pas une "
            f"prévision."))
    if decouvertes:
        _md('<div id="acc-t1"><p class="acc-surtitre">Ce que révèlent les données</p>'
            '<div class="acc-h2">Trois choses à savoir avant d\'explorer</div></div>')
        cartes = "".join(
            f'<div class="acc-ins" style="--c1:{c1};--c2:{c2};animation-delay:{0.1 * i:.1f}s">'
            f'<span class="material-symbols-rounded">{ic}</span>'
            f'<p class="acc-ins-chiffre">{e(ch)}</p><p class="acc-ins-titre">{e(t)}</p>'
            f'<p class="acc-ins-txt">{e(txt)}</p></div>'
            for i, (c1, c2, ic, ch, t, txt) in enumerate(decouvertes))
        _md(f'<div id="acc-ins"><div class="acc-grille3">{cartes}</div></div>')

    # ── 4. Methode ──────────────────────────────────────────────────────
    _md('<div id="acc-t2"><p class="acc-surtitre">La démarche</p>'
        '<div class="acc-h2">Détecter, relier, anticiper</div></div>')
    etapes = (
        ("Détecter", "Chaque jour depuis 1981, les pluies satellitaires CHIRPS sont comparées "
                     "à la normale : un extrême, c'est au moins 40 pixels au-delà de +2 écarts-types."),
        ("Relier", "Les extrêmes de chaque phase de la saison sont confrontés à 11 indices de "
                   "température des océans, avec 0 à 5 mois d'avance."),
        ("Anticiper", "Une veille pré-saison traduit ces liens en bulletin indicatif, en "
                      "affichant honnêtement sa compétence réelle."),
    )
    cartes = "".join(
        f'<div class="acc-etape"><div class="acc-num">{i + 1}</div><p class="acc-et-titre">{t}</p><p>{txt}</p>'
        + ('<span class="material-symbols-rounded acc-fleche">chevron_right</span>'
           if i < len(etapes) - 1 else '') + '</div>'
        for i, (t, txt) in enumerate(etapes))
    _md(f'<div id="acc-met"><div class="acc-grille3">{cartes}</div></div>')

    # ── 5. Etat de la veille ────────────────────────────────────────────
    veille = _etat_veille()
    if veille:
        saison, titre, valeur, note = veille
        _md(f'<div id="acc-veille"><div class="acc-veille">'
            f'<span class="material-symbols-rounded">notifications_active</span>'
            f'<div><p class="acc-v-titre">Veille pré-saison {saison}</p>'
            f'<p class="acc-v-txt">{e(titre)}'
            + (f' : <b>{e(valeur)}</b>' if valeur else '')
            + f' · {e(note)}</p></div></div></div>')

    # ── 6. Sections ─────────────────────────────────────────────────────
    _md('<div id="acc-t3"><p class="acc-surtitre">La plateforme</p>'
        '<div class="acc-h2">Par où commencer ?</div></div>')
    couleurs = ("#6366F1", "#10B981", "#F59E0B", "#0EA5E9", "#A855F7", "#64748B")
    cols = st.columns(3, gap="medium")
    for i, (cle, ic, accroche, desc) in enumerate(SECTIONS):
        page = liens.get(cle)
        if page is None:
            continue
        with cols[i % 3], st.container(key=f"acc_sec_{i}"):
            _md(f'<div class="acc-sec" style="--c:{couleurs[i]}">'
                f'<div class="acc-sec-haut">'
                f'<span class="material-symbols-rounded acc-ic">{ic}</span>'
                f'<span class="material-symbols-rounded acc-go">arrow_forward</span></div>'
                f'<p class="acc-accroche">{e(accroche)}</p>'
                f'<p class="acc-nom">{e(page.title)}</p>'
                f'<p class="acc-desc">{e(desc.format(n=_entier(n_ev)))}</p></div>')
            st.page_link(page, label=f"Ouvrir {page.title}", query_params=query_params)

    # ── 7. Pied ─────────────────────────────────────────────────────────
    _md('<div id="acc-pied"><p class="acc-pied">Données : <b>CHIRPS v2.0</b> (pluie, 0,25°) · '
        '<b>NOAA OISST v2</b> (température de surface de la mer) · <b>Copernicus C3S</b> '
        '(prévision saisonnière)<br>Résultats statistiques et descriptifs : ClimatSen ne '
        'remplace pas les bulletins officiels de l\'ANACIM.</p></div>')
