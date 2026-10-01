"""Page Accueil : vitrine de ClimatSen (suivi de revue 28/09/2026, point S3,
option A ; refonte visuelle demandee par Laity le 28/09/2026).

Bandeau anime avec la courbe des saisons, chiffres cles, trois decouvertes
CALCULEES a partir des donnees (jamais ecrites en dur : elles suivent le
catalogue et les correlations du script 04), parcours de la methode en quatre
temps (detecter, relier, localiser, anticiper), etat de la veille et une carte
cliquable par section, dont le module Vulnerabilite (01/10/2026).

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
import streamlit.components.v1 as components

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
    ("Vulnerabilite", "shield", "Protéger",
     "Où le risque est le plus fort : aléa, population et pauvreté croisés pour les "
     "46 départements et 125 arrondissements."),
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


WIDGET = RACINE / "jarvis" / "widget" / "widget.html"
GLOBE = Path(__file__).resolve().parent / "globe_accueil.html"
# Memes balises que le fond HUD de Jarvis (scripts/23_build_jarvis_fond_hud.py).
BALISES_GLOBE = [("NINO 3.4", -145, 0), ("NINO 1+2", -85, -5), ("TNA", -35, 14),
                 ("ATL3", -10, 0), ("TSA", -10, -10), ("AMO", -40, 40),
                 ("IOD", 75, -2)]


@st.cache_data
def _fond_hud():
    """Planisphere en points du mode J.A.R.V.I.S, repris tel quel du widget
    (entre les marqueurs FOND_HUD). Chaine vide si introuvable."""
    try:
        txt = WIDGET.read_text(encoding="utf-8")
        a = txt.index("<!-- FOND_HUD:DEBUT -->") + len("<!-- FOND_HUD:DEBUT -->")
        b = txt.index("<!-- FOND_HUD:FIN -->")
        return txt[a:b].strip().replace('id="hud-fond"', 'id="acc-fond"')
    except (OSError, ValueError):
        return ""


@st.cache_data
def _points_terres(pas=1.9):
    """Points repartis uniformement sur les terres (lon, lat), pour le globe.
    Espacement ~constant sur la sphere : le pas en longitude grandit avec la
    latitude."""
    import gzip
    import json
    from matplotlib.path import Path as Chemin
    try:
        with gzip.open(RACINE / "jarvis" / "cartes" / "fond_carte.json.gz", "rt",
                       encoding="utf-8") as f:
            terres = json.load(f)["terres"]
    except (OSError, KeyError, ValueError):
        return []
    grille = []
    for lat in np.arange(-56, 80, pas):
        n = max(1, int(360 * np.cos(np.radians(lat)) / pas))
        for lon in np.linspace(-180, 180, n, endpoint=False):
            grille.append((lon, lat))
    grille = np.array(grille)
    dedans = np.zeros(len(grille), bool)
    for anneau in terres:
        a = np.asarray(anneau)
        if len(a) < 4:
            continue
        (x0, y0), (x1, y1) = a.min(0), a.max(0)
        sel = ((grille[:, 0] >= x0) & (grille[:, 0] <= x1)
               & (grille[:, 1] >= y0) & (grille[:, 1] <= y1) & ~dedans)
        if sel.any():
            dedans[np.flatnonzero(sel)[Chemin(a).contains_points(grille[sel])]] = True
    return [[round(float(x), 1), round(float(y), 1)] for x, y in grille[dedans]]


def _globe_html():
    import json
    return (GLOBE.read_text(encoding="utf-8")
            .replace("__TERRES__", json.dumps(_points_terres(), separators=(",", ":")))
            .replace("__BALISES__", json.dumps(BALISES_GLOBE)))


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
/* ── Bandeau d'ouverture : fond du mode J.A.R.V.I.S + globe 3D ──────── */
.st-key-acc_hero {
  position: relative; overflow: hidden; border-radius: 22px;
  padding: 38px 40px 34px 40px !important; margin: 6px 0 22px 0; min-height: 470px;
  justify-content: center;
  background:
    radial-gradient(620px 420px at 74% 50%, rgba(0,229,255,.10), transparent 70%),
    radial-gradient(ellipse at 50% 45%, #041018 0%, #020406 70%);
  border: 1px solid rgba(0,229,255,.22);
  box-shadow: 0 24px 60px -24px rgba(0,229,255,.28), inset 0 0 80px rgba(0,229,255,.05);
}
/* Grille HUD (48 px, comme .hud-grille du widget) */
.st-key-acc_hero::before {
  content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .5;
  background-image: linear-gradient(rgba(0,229,255,.05) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(0,229,255,.05) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at 50% 50%, #000 40%, transparent 95%);
}
/* Crochets d'angle HUD */
.st-key-acc_hero::after {
  content: ""; position: absolute; inset: 12px; pointer-events: none; z-index: 2;
  --c: rgba(0,229,255,.6);
  background:
    linear-gradient(var(--c),var(--c)) top left / 22px 1.5px no-repeat,
    linear-gradient(var(--c),var(--c)) top left / 1.5px 22px no-repeat,
    linear-gradient(var(--c),var(--c)) top right / 22px 1.5px no-repeat,
    linear-gradient(var(--c),var(--c)) top right / 1.5px 22px no-repeat,
    linear-gradient(var(--c),var(--c)) bottom left / 22px 1.5px no-repeat,
    linear-gradient(var(--c),var(--c)) bottom left / 1.5px 22px no-repeat,
    linear-gradient(var(--c),var(--c)) bottom right / 22px 1.5px no-repeat,
    linear-gradient(var(--c),var(--c)) bottom right / 1.5px 22px no-repeat;
}
.st-key-acc_hero > * { position: relative; z-index: 1; }
/* Calques de fond : planisphere HUD puis globe (iframe), sous le contenu.
   Streamlit 1.54 enveloppe chaque conteneur dans un stLayoutWrapper. */
.st-key-acc_hero > :has(> .st-key-acc_fond), .st-key-acc_hero > :has(> .st-key-acc_globe) {
  position: absolute !important; inset: 0; z-index: 0; pointer-events: none;
  margin: 0 !important; width: 100% !important; height: 100% !important;
}
:is(.st-key-acc_fond, .st-key-acc_globe), :is(.st-key-acc_fond, .st-key-acc_globe) * {
  width: 100% !important; height: 100% !important; }
.st-key-acc_globe iframe { border: 0 !important; background: transparent !important;
                           color-scheme: normal; animation: acc-globe 1.6s ease both; }
@keyframes acc-globe { from { opacity: 0; transform: scale(.94); } to { opacity: 1; transform: none; } }
#acc-fond { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .55;
            animation: hf-apparition 2.4s ease both; }
#acc-fond .hf-graticule { fill: none; stroke: rgba(0,229,255,.06); stroke-width: .6;
                          vector-effect: non-scaling-stroke; }
#acc-fond .hf-terres { fill: url(#hf-points); stroke: rgba(0,229,255,.16); stroke-width: .7;
                       vector-effect: non-scaling-stroke; }
#acc-fond pattern circle { fill: rgba(0,229,255,.28); }
#acc-fond .hf-balayage { fill: url(#hf-balayage); animation: hf-balayage 16s linear infinite; }
#acc-fond text, #acc-fond .hf-point, #acc-fond .hf-onde { display: none; }
/* Texte centre a gauche, courbe calee en bas a droite pour laisser le
   globe (et le Senegal) visibles au-dessus. */
.st-key-acc_hero [data-testid="stColumn"]:has(#acc-courbe) {
  margin-top: auto !important; margin-bottom: 0 !important; }
#acc-courbe { max-width: 340px; margin-left: auto; }
@keyframes hf-apparition { from { opacity: 0; } to { opacity: .55; } }
@keyframes hf-balayage { from { transform: translateX(0); } to { transform: translateX(420px); } }

#acc-hero .acc-badge {
  display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
  border-radius: 99px; background: rgba(0,229,255,.06);
  border: 1px solid rgba(0,229,255,.30); color: #A5F3FC !important;
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
  background: linear-gradient(90deg, #22D3EE, #A5B4FC 50%, #F0ABFC);
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
  border: 1px solid rgba(0,229,255,.35) !important;
  background: rgba(2,12,18,.55) !important; backdrop-filter: blur(6px); transition: all .2s ease;
}
/* Le premier bouton est l'appel principal, le second reste en verre depoli. */
.st-key-acc_cta > [data-testid="stElementContainer"]:first-child [data-testid="stPageLink"] a {
  background: linear-gradient(135deg, #0891B2, #6366F1) !important; border-color: rgba(0,229,255,.5) !important;
  box-shadow: 0 0 22px -6px rgba(0,229,255,.75);
}
.st-key-acc_cta [data-testid="stPageLink"] a:hover {
  transform: translateY(-2px); background: rgba(0,229,255,.14) !important;
  box-shadow: 0 0 24px -6px rgba(0,229,255,.8);
}
.st-key-acc_cta [data-testid="stPageLink"] a p,
.st-key-acc_cta [data-testid="stPageLink"] a span {
  color: #FFFFFF !important; font-weight: 700 !important; font-size: .88rem !important;
}

/* Courbe des saisons */
#acc-courbe .acc-carte-courbe {
  background: rgba(2,10,16,.62); border: 1px solid rgba(0,229,255,.25);
  border-radius: 14px; padding: 12px 14px 6px 14px; backdrop-filter: blur(8px);
  box-shadow: 0 18px 40px -20px rgba(0,0,0,.8);
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

/* ── Methode en quatre temps ──────────────────────────────────────────── */
#acc-met .acc-grille-met { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px;
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
[class*="st-key-acc_sec_"] { position: relative; margin-bottom: 16px; }
/* Meme taille pour toutes les cartes : chaque colonne s'etire sur la hauteur de sa
   rangee, et la carte remplit toute la chaine colonne > bloc > texte. La hauteur
   minimale (plus longue description a 4 colonnes) aligne aussi les deux rangees. */
.st-key-acc_sections [data-testid="stHorizontalBlock"] { align-items: stretch !important; }
.st-key-acc_sections [data-testid="stColumn"] { display: flex; flex-direction: column; }
.st-key-acc_sections [data-testid="stColumn"] > [data-testid="stVerticalBlock"],
.st-key-acc_sections [data-testid="stColumn"] > div > [data-testid="stVerticalBlock"] {
  flex: 1 1 auto; height: 100%;
}
[class*="st-key-acc_sec_"] { flex: 1 1 auto; height: calc(100% - 16px); }
[class*="st-key-acc_sec_"] [data-testid="stElementContainer"]:has(.acc-sec),
[class*="st-key-acc_sec_"] [data-testid="stElementContainer"]:has(.acc-sec) [data-testid="stMarkdown"],
[class*="st-key-acc_sec_"] [data-testid="stElementContainer"]:has(.acc-sec) [data-testid="stMarkdownContainer"] {
  height: 100%;
}
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
  height: 100%; min-height: 268px; box-sizing: border-box; transition: transform .25s ease, box-shadow .25s ease,
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
@media (max-width: 1200px) {
  #acc-met .acc-grille-met { grid-template-columns: repeat(2, 1fr); }
  #acc-met .acc-fleche { display: none; }
  /* Cartes de section : 2 par rangee au lieu de 4 */
  .st-key-acc_sections [data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 1rem; }
  .st-key-acc_sections [data-testid="stColumn"] { flex: 1 1 calc(50% - 1rem) !important;
                                                  min-width: calc(50% - 1rem) !important; }
}
@media (max-width: 900px) {
  #acc-kpi .acc-grille4 { grid-template-columns: repeat(2, 1fr); }
  #acc-ins .acc-grille3, #acc-met .acc-grille-met { grid-template-columns: 1fr; }
  #acc-met .acc-fleche { display: none; }
  .st-key-acc_hero { padding: 24px 20px 22px 20px !important; }
}
@media (prefers-reduced-motion: reduce) {
  #acc-fond, #acc-fond *, .st-key-acc_globe iframe, #acc-hero *, #acc-courbe *, #acc-kpi *, #acc-ins *,
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
        fond = _fond_hud()
        if fond:
            with st.container(key="acc_fond"):
                _md(fond)
        with st.container(key="acc_globe"):
            components.html(_globe_html(), height=470)
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
    frappent les extrêmes, qui y est exposé, et ce que les océans en laissaient
    deviner.</p>
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
        '<div class="acc-h2">Détecter, relier, localiser, anticiper</div></div>')
    etapes = (
        ("Détecter", "Chaque jour depuis 1981, les pluies satellitaires CHIRPS sont comparées "
                     "à la normale : un extrême, c'est au moins 40 pixels au-delà de +2 écarts-types."),
        ("Relier", "Les extrêmes de chaque phase de la saison sont confrontés à 11 indices de "
                   "température des océans, avec 0 à 5 mois d'avance."),
        ("Localiser", "Un indice de risque croise la fréquence des extrêmes (CHIRPS), la "
                      "population (ANSD RGPH-5) et la pauvreté (ANSD EHCVM), département par "
                      "département. Vulnérabilité encore provisoire."),
        ("Anticiper", "Une veille pré-saison traduit ces liens en bulletin indicatif, en "
                      "affichant honnêtement sa compétence réelle."),
    )
    cartes = "".join(
        f'<div class="acc-etape"><div class="acc-num">{i + 1}</div><p class="acc-et-titre">{t}</p><p>{txt}</p>'
        + ('<span class="material-symbols-rounded acc-fleche">chevron_right</span>'
           if i < len(etapes) - 1 else '') + '</div>'
        for i, (t, txt) in enumerate(etapes))
    _md(f'<div id="acc-met"><div class="acc-grille-met">{cartes}</div></div>')

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
    # La couleur suit la section (et non sa position) : ajouter une section ne
    # repeint pas les autres.
    couleurs = {"Evenements": "#6366F1", "Teleconnexions": "#10B981", "Veille": "#F59E0B",
                "Vulnerabilite": "#F43F5E", "Indices SST": "#0EA5E9",
                "Clustering": "#A855F7", "A propos": "#64748B"}
    n_cols = 4
    sections = [(i, s) for i, s in enumerate(SECTIONS) if s[0] in liens]
    # Une rangee de colonnes par ligne de cartes : les cartes restent alignees.
    with st.container(key="acc_sections"):
        for debut in range(0, len(sections), n_cols):
            cols = st.columns(n_cols, gap="medium")
            for col, (i, (cle, ic, accroche, desc)) in zip(cols, sections[debut:debut + n_cols]):
                page = liens[cle]
                with col, st.container(key=f"acc_sec_{i}"):
                    _md(f'<div class="acc-sec" style="--c:{couleurs.get(cle, "#64748B")}">'
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
        '(prévision saisonnière) · <b>ANSD</b> (RGPH-5 2023, EHCVM 2021-2022) · '
        '<b>OCHA COD-AB</b> (limites administratives)<br>Résultats statistiques et descriptifs : ClimatSen ne '
        'remplace pas les bulletins officiels de l\'ANACIM.</p></div>')
