"""Page Veille pre-saison: bulletin annuel de niveau de risque d'annee extreme.

Ne calcule rien: lit les bulletins JSON produits hors ligne par
scripts/20_veille_presaison.py (outputs/veille/). Le serveur n'a donc besoin
ni du cube SST ni d'un acces Copernicus.

Organisation de la page:
  1. barre de saison (choix + statut du bulletin);
  2. bandeau du verdict (jauge face a la reference 33 %, issue observee ou
     calendrier, conduite a tenir) et chiffres clefs;
  3. lecture du bulletin: une carte par approche (veille.bulletin.synthese_parties);
  4. onglets: signaux de la saison, ocean nov.-avr., fiabilite, historique;
  5. diffusion (Markdown, Word, message court).
"""
import html
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE / "scripts"))
sys.path.insert(0, str(RACINE))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dashboard_utils as du
from dashboard_utils import AMBER, BLUE, EMERALD, INDIGO, ROSE

from veille import DOSSIER_SORTIE, INONDATIONS_CONNUES
from veille import artefacts, fiabilite, production
from veille import bulletin as mod_bulletin
from veille import diffusion
from veille.projection import VARIANTES_TESTEES, p_corrige

ICONES = {"faible": "&#9660;", "normal": "&#9679;", "eleve": "&#9650;",
          "tres_eleve": "&#9650;&#9650;", "indetermine": "?"}

# Une carte par approche de la synthese: (titre, icone Material, couleur,
# nature, prefixe du texte a retirer car redondant avec le titre). Le contexte
# (saisons recentes) n'a pas de carte: la tuile "Saisons recentes" le donne deja.
APPROCHES = {
    "c3s": ("Prévision Copernicus C3S", "satellite_alt", BLUE, "officielle", ""),
    "configuration": ("Configuration du mémoire", "hub", INDIGO, "descriptive", ""),
    "analogues": ("Années analogues", "history", INDIGO, "descriptive",
                  "Années les plus ressemblantes : "),
    "familles": ("Familles d'océans extrêmes", "waves", INDIGO, "descriptive",
                 "Familles d'océans des saisons extrêmes : "),
    "projection": ("Projection expérimentale", "science", AMBER, "expérimentale", ""),
    "verification": ("Vérification", "fact_check", EMERALD, "observé", "Vérification : "),
}
NATURES = {"officielle": BLUE, "descriptive": INDIGO, "expérimentale": AMBER,
           "contexte": "#64748B", "observé": EMERALD}
VERDICTS = {"détection": (EMERALD, "check_circle"), "manquée": (ROSE, "cancel"),
            "fausse alerte": (AMBER, "error"), "calme confirmé": ("#64748B", "check")}
MOIS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
           "sept.", "oct.", "nov.", "déc."]

CSS = """
<style>
/* ── Barre de saison ─────────────────────────────────────────────────── */
.vp-chips { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end;
            align-items: center; min-height: 40px; }
.vp-chip { display: inline-flex; align-items: center; gap: 5px; font-size: .72rem;
           font-weight: 600; padding: 5px 11px; border-radius: 999px; line-height: 1;
           border: 1px solid __BORDER__; background: __CARD__; color: __MUTED__ !important; }
.vp-chip.vp-c { color: var(--c) !important; border-color: color-mix(in srgb, var(--c) 35%, transparent);
                background: color-mix(in srgb, var(--c) 11%, transparent); }
.vp-chip .material-symbols-rounded { font-size: 15px; }

/* ── Bandeau du verdict ──────────────────────────────────────────────── */
.vp-hero { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
           background: __CARD__; border: 1px solid __BORDER__; border-radius: 18px;
           overflow: hidden; position: relative; margin: 6px 0 16px 0;
           box-shadow: 0 1px 3px rgba(0,0,0,.04), 0 18px 40px -28px rgba(79,70,229,.45);
           animation: vp-monte .6s ease both; }
.vp-hero::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
                   background: var(--acc); }
.vp-hero-main { padding: 24px 28px 22px 32px;
                background: radial-gradient(120% 150% at 0% 0%,
                            color-mix(in srgb, var(--acc) 13%, transparent), transparent 62%); }
.vp-eyebrow { font-size: .68rem !important; font-weight: 700; letter-spacing: 1.3px;
              text-transform: uppercase; color: __MUTED__ !important; margin: 0 !important; }
.vp-big { font-size: clamp(2.3rem, 4.2vw, 3.3rem); font-weight: 800; letter-spacing: -1.5px;
          line-height: 1.05; color: __TEXT__ !important; margin: 8px 0 2px 0; }
.vp-big .vp-ico { color: var(--acc); font-size: .7em; margin-right: 6px; }
.vp-big small { font-size: .9rem; font-weight: 600; letter-spacing: 0; margin-left: 10px;
                color: __MUTED__ !important; }
.vp-lead { font-size: .86rem !important; line-height: 1.6; color: __TEXT__ !important;
           margin: 14px 0 0 0 !important; max-width: 64ch; }
.vp-gauge { position: relative; height: 10px; border-radius: 999px; max-width: 560px;
            background: color-mix(in srgb, __MUTED__ 20%, transparent); margin: 16px 0 26px 0; }
.vp-gauge-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px;
                 background: linear-gradient(90deg, color-mix(in srgb, var(--acc) 45%, transparent), var(--acc));
                 animation: vp-pousse 1s .15s cubic-bezier(.3,.7,.3,1) both; transform-origin: left; }
.vp-gauge-ref { position: absolute; top: -5px; bottom: -5px; width: 2px; border-radius: 2px;
                background: __TEXT__; }
.vp-gauge-ref span { position: absolute; top: 21px; left: 50%; transform: translateX(-50%);
                     font-size: .66rem; font-weight: 600; white-space: nowrap; color: __MUTED__ !important; }
.vp-gauge-bornes { position: absolute; top: 16px; width: 100%; display: flex;
                   justify-content: space-between; font-size: .62rem; color: __MUTED__ !important; }
.vp-hero-side { padding: 22px 24px; border-left: 1px solid __BORDER__; display: flex;
                flex-direction: column; gap: 18px;
                background: color-mix(in srgb, __BG__ 40%, __CARD__); }
.vp-side-ttl { display: flex; align-items: center; gap: 6px; font-size: .68rem !important;
               font-weight: 700; letter-spacing: 1.1px; text-transform: uppercase;
               color: __MUTED__ !important; margin: 0 0 8px 0 !important; }
.vp-side-ttl .material-symbols-rounded { font-size: 16px; }
.vp-side-txt { font-size: .82rem !important; line-height: 1.55; color: __TEXT__ !important;
               margin: 0 !important; }
.vp-side-txt b { color: __TEXT__ !important; }
.vp-issue { display: inline-flex; align-items: center; gap: 7px; font-weight: 800;
            font-size: .95rem; padding: 7px 13px; border-radius: 10px; margin-bottom: 8px;
            color: var(--c) !important; background: color-mix(in srgb, var(--c) 13%, transparent); }
.vp-issue .material-symbols-rounded { font-size: 19px; }

/* Calendrier de la veille (saison a venir) */
.vp-steps { display: flex; flex-direction: column; gap: 11px; }
.vp-step { display: grid; grid-template-columns: 26px 1fr; gap: 11px; align-items: start; }
.vp-dot { width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center;
          justify-content: center; font-size: .72rem; font-weight: 800;
          color: #4F46E5 !important; background: rgba(79,70,229,.13); }
.vp-step.vp-on .vp-dot { color: #FFFFFF !important; background: #4F46E5;
                         box-shadow: 0 0 0 4px rgba(79,70,229,.18); }
.vp-step p { margin: 0 !important; font-size: .8rem !important; line-height: 1.45;
             color: __TEXT__ !important; }
.vp-step p small { color: __MUTED__ !important; font-size: .72rem; }

/* ── Titres de section ───────────────────────────────────────────────── */
.vp-sec { margin: 30px 0 12px 0; }
.vp-sec-ttl { font-size: 1.02rem !important; font-weight: 800 !important; letter-spacing: -.2px;
              color: __TEXT__ !important; margin: 0 !important; display: flex; align-items: center; gap: 8px; }
.vp-sec-ttl .material-symbols-rounded { color: #6366F1 !important; font-size: 20px; }
.vp-sec-sub { font-size: .76rem !important; color: __MUTED__ !important; margin: 3px 0 0 0 !important; }

/* ── Cartes d'approche ───────────────────────────────────────────────── */
.vp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 14px; }
.vp-card { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px;
           padding: 16px 18px; position: relative; overflow: hidden;
           transition: transform .2s ease, box-shadow .2s ease; animation: vp-monte .5s ease both; }
.vp-card:hover { transform: translateY(-2px);
                 box-shadow: 0 12px 28px -16px color-mix(in srgb, var(--c) 70%, transparent); }
.vp-card::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px;
                  background: var(--c); opacity: .8; }
.vp-card-hd { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.vp-ic { font-size: 20px !important; color: var(--c) !important; border-radius: 10px; padding: 7px;
         background: color-mix(in srgb, var(--c) 14%, transparent); }
.vp-card-ttl { flex: 1; font-weight: 700; font-size: .86rem !important; margin: 0 !important;
               color: __TEXT__ !important; }
.vp-tag { font-size: .6rem; font-weight: 800; text-transform: uppercase; letter-spacing: .7px;
          padding: 3px 8px; border-radius: 999px; white-space: nowrap;
          color: var(--t) !important; background: color-mix(in srgb, var(--t) 13%, transparent); }
.vp-card-txt { font-size: .81rem !important; line-height: 1.6; margin: 0 !important;
               color: __TEXT__ !important; opacity: .93; }

/* Notes (avertissements du bulletin) */
.vp-notes { display: flex; gap: 12px; margin-top: 14px; padding: 12px 16px; border-radius: 12px;
            border: 1px dashed color-mix(in srgb, var(--c) 55%, transparent);
            background: color-mix(in srgb, var(--c) 6%, transparent); }
.vp-notes > .material-symbols-rounded { color: var(--c) !important; font-size: 20px; }
.vp-notes ul { margin: 0; padding-left: 16px; }
.vp-notes li { font-size: .77rem; line-height: 1.55; color: __TEXT__ !important; margin: 0 0 3px 0; }

/* ── Listes (analogues) ──────────────────────────────────────────────── */
.vp-list { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px; overflow: hidden; }
.vp-row { display: grid; grid-template-columns: 50px minmax(60px, 1fr) 44px auto 22px;
          gap: 12px; align-items: center; padding: 11px 16px; border-bottom: 1px solid __BORDER__; }
.vp-row:last-child { border-bottom: none; }
.vp-row:hover { background: color-mix(in srgb, #6366F1 5%, transparent); }
.vp-yr { font-weight: 800; font-size: .92rem; color: __TEXT__ !important; }
.vp-meter { height: 6px; border-radius: 999px; position: relative; overflow: hidden;
            background: color-mix(in srgb, __MUTED__ 18%, transparent); }
.vp-meter > i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px;
                background: var(--c, #6366F1); }
.vp-num { font-size: .78rem; font-variant-numeric: tabular-nums; text-align: right;
          color: __MUTED__ !important; }
.vp-pill { font-size: .66rem; font-weight: 700; padding: 3px 9px; border-radius: 999px;
           white-space: nowrap; color: var(--c) !important;
           background: color-mix(in srgb, var(--c) 13%, transparent); }
.vp-drop { font-size: 18px !important; color: #0EA5E9 !important; }

/* ── Familles d'oceans ───────────────────────────────────────────────── */
.vp-fams { display: grid; gap: 10px; }
.vp-fam { display: grid; grid-template-columns: 40px 1fr auto; gap: 12px; align-items: center;
          background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px; padding: 13px 16px; }
.vp-fam.vp-proche { border-color: #6366F1; box-shadow: 0 0 0 3px rgba(99,102,241,.14); }
.vp-fam-code { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center;
               justify-content: center; font-weight: 800; font-size: 1.05rem; color: #FFFFFF !important;
               background: linear-gradient(135deg, #6366F1, #0EA5E9); }
.vp-fam-nom { font-weight: 700; font-size: .84rem; color: __TEXT__ !important; margin: 0 !important; }
.vp-fam-det { font-size: .72rem !important; color: __MUTED__ !important; margin: 2px 0 0 0 !important;
              line-height: 1.45; }
.vp-fam-r { text-align: right; }
.vp-fam-r b { display: block; font-size: 1.15rem; font-weight: 800; color: __TEXT__ !important;
              font-variant-numeric: tabular-nums; }
.vp-fam-r span { font-size: .64rem; color: __MUTED__ !important; }
.vp-legende { font-size: .72rem !important; color: __MUTED__ !important; margin: 8px 2px 0 2px !important;
              line-height: 1.5; }

/* ── Tableau ─────────────────────────────────────────────────────────── */
.vp-tab { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px;
          overflow-x: auto; margin-top: 10px; }
.vp-tab table { width: 100%; border-collapse: collapse; }
.vp-tab th { padding: 9px 12px; font-size: .66rem; font-weight: 700; text-transform: uppercase;
             letter-spacing: .6px; color: __MUTED__ !important; border-bottom: 1px solid __BORDER__;
             background: color-mix(in srgb, __MUTED__ 7%, transparent); }
.vp-tab td { padding: 9px 12px; font-size: .8rem; color: __TEXT__ !important;
             border-bottom: 1px solid __BORDER__; }
.vp-tab tr:last-child td { border-bottom: none; }
.vp-tab tbody tr:hover td { background: color-mix(in srgb, #6366F1 5%, transparent); }

/* ── Competence, inondations ─────────────────────────────────────────── */
.vp-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.vp-stat { background: __CARD__; border: 1px solid __BORDER__; border-radius: 14px; padding: 14px 16px; }
.vp-stat-lbl { font-size: .68rem !important; font-weight: 700; text-transform: uppercase;
               letter-spacing: .8px; color: __MUTED__ !important; margin: 0 !important; }
.vp-stat-val { font-size: 1.5rem; font-weight: 800; color: __TEXT__ !important; margin: 4px 0 8px 0;
               font-variant-numeric: tabular-nums; }
.vp-stat-val small { font-size: .74rem; font-weight: 600; color: __MUTED__ !important; margin-left: 6px; }
.vp-auc { position: relative; height: 8px; border-radius: 999px;
          background: linear-gradient(90deg, color-mix(in srgb, __MUTED__ 25%, transparent),
                      color-mix(in srgb, #10B981 45%, transparent)); }
.vp-auc i { position: absolute; top: -4px; width: 4px; height: 16px; border-radius: 3px;
            background: __TEXT__; transform: translateX(-50%); }
.vp-auc-b { display: flex; justify-content: space-between; font-size: .62rem;
            color: __MUTED__ !important; margin-top: 4px; }
.vp-inond { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.vp-inond .vp-chip { font-size: .76rem; padding: 6px 12px; }

/* ── Vide ────────────────────────────────────────────────────────────── */
.vp-vide { display: flex; gap: 14px; align-items: center; background: __CARD__;
           border: 1px dashed __BORDER__; border-radius: 14px; padding: 22px; margin-top: 6px; }
.vp-vide .material-symbols-rounded { font-size: 28px; color: __MUTED__ !important; }
.vp-vide p { margin: 0 !important; font-size: .82rem !important; color: __MUTED__ !important; line-height: 1.55; }
.vp-vide b { color: __TEXT__ !important; }

/* ── Diffusion ─ (st.code reste clair en mode sombre: on le recolore) */
.st-key-veille_sms pre {
  background: __CARD__ !important; border: 1px solid __BORDER__ !important; border-radius: 12px !important; }
.st-key-veille_sms code, .st-key-veille_sms code * { color: __TEXT__ !important; background: transparent !important;
  font-family: 'Inter', sans-serif !important; font-size: .8rem !important; line-height: 1.55 !important; }
/* ───────────────────────────────────────────────────────── */
.vp-dl { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.vp-dl .material-symbols-rounded { font-size: 20px; color: var(--c) !important; border-radius: 10px;
                                   padding: 7px; background: color-mix(in srgb, var(--c) 14%, transparent); }
.vp-dl p { margin: 0 !important; font-size: .84rem !important; font-weight: 700; color: __TEXT__ !important; }
.vp-dl small { display: block; font-size: .7rem; font-weight: 500; color: __MUTED__ !important; }

@keyframes vp-monte { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes vp-pousse { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) {
  .vp-hero, .vp-card, .vp-gauge-fill { animation: none !important; }
}
@media (max-width: 900px) {
  .vp-hero { grid-template-columns: 1fr; }
  .vp-hero-side { border-left: none; border-top: 1px solid __BORDER__; }
  .vp-chips { justify-content: flex-start; }
}
@media (max-width: 520px) {
  .vp-hero-main { padding: 20px 18px 18px 22px; }
  .vp-row { grid-template-columns: 44px 1fr auto 20px; }
  .vp-row .vp-num { display: none; }
}
</style>
"""


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


@st.cache_data(ttl=300, show_spinner=False)
def _docx(annee, emis_le):
    """Document Word du bulletin (emis_le dans la cle: un bulletin re-emis est regenere)."""
    b = production.lire_bulletin(annee)
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "bulletin.docx"
        diffusion.docx(b, chemin)
        return chemin.read_bytes()


def _pct(p):
    return "n/d" if p is None else "%d %%" % round(100 * p)


def _e(texte):
    return html.escape(str(texte))


def _fr(x, d=2):
    """Nombre a la francaise (0,72)."""
    return ("%%.%df" % d % x).replace(".", ",")


def _md(texte):
    st.markdown(texte, unsafe_allow_html=True)


def _ic(nom, cls=""):
    return f'<span class="material-symbols-rounded {cls}">{nom}</span>'


def _section(icone, titre, sous_titre=""):
    _md(f'<div class="vp-sec"><p class="vp-sec-ttl">{_ic(icone)}{_e(titre)}</p>'
        + (f'<p class="vp-sec-sub">{sous_titre}</p>' if sous_titre else "") + '</div>')


def _vide(icone, titre, texte):
    _md(f'<div class="vp-vide">{_ic(icone)}<p><b>{_e(titre)}</b><br>{_e(texte)}</p></div>')


def _tableau(entetes, lignes, alignes=()):
    """Tableau HTML aux couleurs du theme (st.dataframe reste clair en mode sombre)."""
    def al(i):
        return "right" if i in alignes else "left"
    th = "".join(f'<th style="text-align:{al(i)}">{_e(h)}</th>' for i, h in enumerate(entetes))
    corps = "".join("<tr>" + "".join(f'<td style="text-align:{al(i)}">{_e(v)}</td>'
                                     for i, v in enumerate(ligne)) + "</tr>" for ligne in lignes)
    return (f'<div class="vp-tab"><table><thead><tr>{th}</tr></thead>'
            f'<tbody>{corps}</tbody></table></div>')


def _sans_prefixe(texte, prefixe):
    if prefixe and texte.startswith(prefixe):
        texte = texte[len(prefixe):]
        return texte[:1].upper() + texte[1:]
    return texte


# =============================================================================
# Bandeau du verdict
# =============================================================================
def _calendrier(choix):
    """Etapes de la veille pour une saison a venir; l'etape en cours est marquee."""
    aujourd_hui = pd.Timestamp.today()
    etapes = [
        (pd.Timestamp(choix - 1, 12, 1), "Début décembre %d" % (choix - 1),
         "premier bulletin provisoire (état océanique de novembre)"),
        (pd.Timestamp(choix, 1, 1), "Chaque début de mois jusqu'en avril",
         "bulletin provisoire mis à jour"),
        (pd.Timestamp(choix, 4, 13), "Mi-avril %d" % choix,
         "bulletin final, après la prévision Copernicus C3S (publiée le 13 avril)"),
    ]
    en_cours = max([i for i, (d, _, _) in enumerate(etapes) if aujourd_hui >= d], default=-1)
    return "".join(
        f'<div class="vp-step{" vp-on" if i == en_cours else ""}"><span class="vp-dot">{i + 1}</span>'
        f'<p><b>{_e(quand)}</b><br><small>{_e(quoi)}</small></p></div>'
        for i, (_, quand, quoi) in enumerate(etapes))


def _bandeau(b, pres, parties, rang_sur):
    n = b["niveau_risque"]
    annee = b["annee"]
    v = b.get("verification")
    p = n.get("probabilite_annee_extreme")
    acc = pres["couleur"] if pres["mode"] == "niveau" else (INDIGO if p is not None else "#64748B")

    # Valeur principale + jauge face a la reference 33 %.
    if pres["mode"] == "niveau":
        grand = (f'<span class="vp-ico">{ICONES.get(n["code"], "")}</span>{_e(pres["valeur"])}'
                 f'<small>probabilité {_pct(p)}</small>')
    elif pres["mode"] == "probabilite":
        grand = f'{_e(pres["valeur"])}<small>référence 33 %</small>'
    else:
        grand = 'En attente<small>pas encore de prévision</small>'
    ref = 100 * b["contexte"]["base_climatologique"]
    jauge = ""
    if p is not None:
        jauge = (f'<div class="vp-gauge" role="img" aria-label="Probabilité {_pct(p)}, référence 33 %">'
                 f'<div class="vp-gauge-fill" style="width:{100 * p:.1f}%"></div>'
                 f'<div class="vp-gauge-ref" style="left:{ref:.1f}%"><span>réf. {ref:.0f} %</span></div>'
                 f'<div class="vp-gauge-bornes"><span>0 %</span><span>100 %</span></div></div>')
    verdict = next((t for k, t in parties if k == "verdict"), "")

    principal = (f'<div class="vp-hero-main">'
                 f'<p class="vp-eyebrow">Saison {annee} · {_e(pres["titre"])}</p>'
                 f'<div class="vp-big">{grand}</div>{jauge}'
                 f'<p class="vp-lead">{_e(verdict)}</p></div>')

    # Cote: issue observee (retrospectif) ou calendrier (a venir), puis conduite a tenir.
    cote = []
    if v:
        c, ic, lib = ((ROSE, "flood", "Saison extrême") if v["extreme_observe"]
                      else (EMERALD, "check_circle", "Saison normale"))
        cote.append(
            f'<div><p class="vp-side-ttl">{_ic("fact_check")}Ce qui s\'est passé</p>'
            f'<span class="vp-issue" style="--c:{c}">{_ic(ic)}{lib}</span>'
            f'<p class="vp-side-txt">Rang <b>{v["rang"]}</b>{" sur %d" % rang_sur if rang_sur else ""} '
            f'· empreinte <b>{v["empreinte_observee"]:.0f}</b> (seuil {v.get("seuil", 0):.0f})'
            + (' · <b>inondations documentées</b>' if v["inondation_documentee"] else '')
            + '</p></div>')
    elif pres["mode"] == "indetermine":
        cote.append(f'<div><p class="vp-side-ttl">{_ic("event")}Calendrier de la veille</p>'
                    f'<div class="vp-steps">{_calendrier(annee)}</div></div>')
    cote.append(f'<div><p class="vp-side-ttl">{_ic("shield")}Conduite à tenir</p>'
                f'<p class="vp-side-txt">{_e(diffusion.conseil(b))}</p></div>')

    _md(f'<div class="vp-hero" style="--acc:{acc}">{principal}'
        f'<div class="vp-hero-side">{"".join(cote)}</div></div>')


def _chiffres_clefs(b, retrospectif):
    c3s = b.get("c3s") or {}
    proj = b.get("projection") or {}
    fr = b["contexte"].get("frequence_recente") or {}
    tuiles = [
        ("satellite_alt", BLUE, "Prévision C3S",
         _pct(c3s.get("probabilite_annee_extreme")) if c3s.get("disponible") else "—",
         ("%s · anomalie JAS %s σ" % (c3s["centre"].upper(),
                                      ("%+.1f" % (round(c3s["anomalie_standardisee"], 1) + 0.0))
                                      .replace(".", ","))
          if c3s.get("disponible") else
          "publiée le 13 avril" if not retrospectif else "non disponible"), "t-blue"),
        ("science", AMBER, "Projection océanique",
         _pct(proj.get("probabilite_experimentale")) if proj else "—",
         "expérimentale · ne fixe pas le niveau", "t-amber"),
        ("timeline", INDIGO, "Saisons récentes",
         ("%d / %d" % (fr["extremes"], fr["sur"])) if fr.get("sur") else "—",
         ("extrêmes en %d-%d · réf. 1 sur 3" % tuple(fr["annees"])) if fr.get("sur") else "",
         "t-indigo"),
    ]
    for col, (ic, c, lbl, val, sub, tag) in zip(st.columns(3, gap="small"), tuiles):
        col.markdown(
            f'<div class="kpi"><div class="kpi-body">'
            f'<div class="kpi-icon" style="background:{c}22;color:{c}">{_ic(ic)}</div>'
            f'<p class="kpi-lbl">{_e(lbl)}</p><p class="kpi-val">{_e(val)}</p>'
            f'<span class="kpi-tag {tag}">{_e(sub)}</span></div></div>', unsafe_allow_html=True)


def _lecture(b, parties, retrospectif):
    cartes = []
    for cle, texte in parties:
        if cle not in APPROCHES:
            continue
        titre, ic, c, nature, prefixe = APPROCHES[cle]
        if cle == "verification":
            c = ROSE if b["verification"]["extreme_observe"] else EMERALD
        cartes.append(
            f'<div class="vp-card" style="--c:{c}"><div class="vp-card-hd">'
            f'{_ic(ic, "vp-ic")}<p class="vp-card-ttl">{_e(titre)}</p>'
            f'<span class="vp-tag" style="--t:{NATURES[nature]}">{_e(nature)}</span></div>'
            f'<p class="vp-card-txt">{_e(_sans_prefixe(texte, prefixe))}</p></div>')
    if cartes:
        _section("menu_book", "Lecture du bulletin",
                 "Une carte par approche · <b>officielle</b> : prévision Copernicus C3S · "
                 "<b>descriptive</b> : ressemblance sans valeur de prévision démontrée · "
                 "<b>expérimentale</b> : ne fixe pas le niveau")
        _md(f'<div class="vp-grid">{"".join(cartes)}</div>')
    # Saison a venir: ces notes decrivent l'etat normal hors periode de veille,
    # pas une erreur -> ton informatif.
    notes = b.get("avertissements") or []
    if notes:
        c = AMBER if retrospectif else BLUE
        _md(f'<div class="vp-notes" style="--c:{c}">{_ic("info")}<ul>'
            + "".join(f"<li>{_e(a)}</li>" for a in notes) + '</ul></div>')


# =============================================================================
# Onglets
# =============================================================================
def _onglet_signaux(proj, plotly_base, TEXT, MUTED, BORDER):
    if not proj:
        _vide("cloud_off", "Projection océanique indisponible pour cette saison",
              "L'état de l'océan de novembre à avril n'est pas encore complet : les "
              "configurations, analogues et familles apparaîtront avec le premier bulletin "
              "provisoire.")
        return
    g, d = st.columns([1.15, 1], gap="large")
    with g:
        _section("hub", "Ressemblance aux configurations du mémoire",
                 "Corrélation de motif entre l'état SST novembre-avril (détrendé) et chaque "
                 "centroïde K-Means · en couleur : la plus proche")
        toutes = sorted(proj.get("toutes_configurations") or [], key=lambda c: c["correlation"])
        if toutes:
            meilleure = max(toutes, key=lambda c: c["correlation"])["configuration"]
            fig = go.Figure(go.Bar(
                x=[c["correlation"] for c in toutes],
                y=["C%d" % c["configuration"] for c in toutes],
                orientation="h",
                marker=dict(color=[INDIGO if c["configuration"] == meilleure else MUTED
                                   for c in toutes],
                            opacity=[1 if c["configuration"] == meilleure else .45 for c in toutes],
                            cornerradius=4),
                text=[_fr(c["correlation"]) for c in toutes], textposition="outside",
                textfont=dict(color=MUTED, size=10), cliponaxis=False,
                hovertemplate="<b>%{y}</b> : r = %{x:.2f}<extra></extra>"))
            plotly_base(fig, h=300)
            fig.update_layout(xaxis=dict(zeroline=True, zerolinecolor=MUTED, showgrid=True,
                                         gridcolor=BORDER, tickformat=".2f"),
                              yaxis=dict(showgrid=False), bargap=0.32,
                              margin=dict(l=10, r=30, t=8, b=24), separators=", ")
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        top = (proj.get("configurations") or [])[:3]
        if top:
            _md(_tableau(
                ["Config.", "État", "r", "Années principales", "Évén. en année extrême"],
                [["C%d" % c["configuration"], c.get("etat_oceanique") or "—", _fr(c["correlation"]),
                  ", ".join(str(a) for a in c.get("annees_principales", [])) or "—",
                  _pct(c.get("part_evenements_en_annee_extreme"))] for c in top],
                alignes=(2, 4)))
    with d:
        ana = proj.get("analogues") or []
        if ana:
            _section("history", "Années analogues",
                     "Saisons passées dont l'océan de novembre à avril ressemblait le plus")
            lignes = []
            for a in ana:
                c = ROSE if a["extreme"] else "#64748B"
                larg = max(0.0, min(1.0, a["correlation"])) * 100
                lignes.append(
                    f'<div class="vp-row"><span class="vp-yr">{a["annee"]}</span>'
                    f'<div class="vp-meter" title="corrélation {_fr(a["correlation"])}">'
                    f'<i style="width:{larg:.0f}%"></i></div>'
                    f'<span class="vp-num">{_fr(a["correlation"])}</span>'
                    f'<span class="vp-pill" style="--c:{c}">{"extrême" if a["extreme"] else "normale"}</span>'
                    + (_ic("water_drop", "vp-drop") if a["inondation_documentee"] else "<span></span>")
                    + '</div>')
            _md(f'<div class="vp-list">{"".join(lignes)}</div>'
                f'<p class="vp-legende">Barre : corrélation de motif · '
                f'{_ic("water_drop", "vp-drop")} inondation documentée</p>')
        fam = proj.get("familles_extremes") or {}
        if fam.get("familles"):
            _section("waves", "Familles d'océans des saisons extrêmes",
                     "Ressemblance au composite de chaque famille (membres antérieurs à la "
                     "saison) · au-dessus de %s : ressemblance nette" % _fr(fam.get("seuil", 0.3)))
            cartes = []
            for f in fam["familles"]:
                proche = f["code"] == fam.get("plus_proche")
                r = f.get("correlation")
                cartes.append(
                    f'<div class="vp-fam{" vp-proche" if proche else ""}">'
                    f'<span class="vp-fam-code">{_e(f["code"])}</span><div>'
                    f'<p class="vp-fam-nom">{_e(f["nom"])}'
                    + (' <span class="vp-pill" style="--c:#6366F1">la plus proche</span>' if proche else '')
                    + f'</p><p class="vp-fam-det">Saisons : '
                    f'{_e(", ".join(str(a) for a in f["membres_utilises"]) or "pas encore observée")}'
                    f'<br>{_e(f["signature"])}</p></div>'
                    f'<div class="vp-fam-r"><b>{_fr(r) if r is not None else "—"}</b>'
                    f'<span>corrélation</span></div></div>')
            _md(f'<div class="vp-fams">{"".join(cartes)}</div>'
                f'<p class="vp-legende">{_e(fam.get("avertissement", ""))}</p>')


def _onglet_ocean(choix, proj, plotly_base, TEXT, MUTED, BORDER):
    etat = _etat(choix)
    traj = (proj or {}).get("trajectoire") or []
    if etat is None and len(traj) < 2:
        _vide("public_off", "Pas encore d'état océanique pour cette saison",
              "La carte des anomalies de novembre à avril et l'évolution de la projection "
              "s'afficheront dès que les premiers mois seront disponibles.")
        return
    if etat is not None:
        z, lats, lons, mois = etat
        _section("public", "L'océan de novembre à avril",
                 "Anomalie de température de surface (°C), moyenne de %s à %s · "
                 "<span style='color:#2563EB'>bleu</span> : plus froid que la normale · "
                 "<span style='color:#DC2626'>rouge</span> : plus chaud"
                 % (_e(mois[0]), _e(mois[-1])))
        lim = float(max(0.5, min(3.0, abs(pd.Series(z.ravel()).dropna()).quantile(0.98))))
        fig = go.Figure(go.Heatmap(
            z=z, x=lons, y=lats, zmin=-lim, zmax=lim, zmid=0,
            colorscale=[[0, "#2563EB"], [0.5, BORDER], [1, "#DC2626"]],
            colorbar=dict(title=dict(text="°C", font=dict(color=MUTED, size=11)),
                          tickfont=dict(color=MUTED, size=10), thickness=10, len=0.8),
            hovertemplate="%{y:.0f}°, %{x:.0f}° : %{z:+.2f} °C<extra></extra>"))
        plotly_base(fig, h=340)
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=24), separators=", ",
                          xaxis=dict(showgrid=False, ticksuffix="°", range=[-180, 180],
                                     tickvals=list(range(-150, 181, 50)), constrain="domain"),
                          yaxis=dict(showgrid=False, ticksuffix="°", range=[-60, 60],
                                     scaleanchor="x", constrain="domain"))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    if len(traj) >= 2:
        _section("trending_up", "Évolution pendant la veille",
                 "Indication expérimentale de la projection sur l'état cumulé depuis novembre · "
                 "étiquette : configuration du mémoire la plus proche · les premiers mois sont "
                 "plus incertains")
        etiquettes = ["%s %s" % (MOIS_FR[int(t["jusqu_a"][5:]) - 1], t["jusqu_a"][:4]) for t in traj]
        fig = go.Figure(go.Scatter(
            x=etiquettes, y=[t["probabilite_experimentale"] for t in traj],
            mode="lines+markers+text", line=dict(color=AMBER, width=2.5, shape="spline"),
            fill="tozeroy", fillcolor="rgba(245,158,11,0.10)",
            marker=dict(size=9, color=AMBER, line=dict(width=2, color=TEXT)),
            text=["C%d" % t["configuration"] for t in traj], textposition="top center",
            textfont=dict(color=TEXT, size=11),
            hovertemplate="jusqu'à fin %{x} : %{y:.0%}<extra></extra>"))
        fig.add_hline(y=1 / 3, line=dict(color=MUTED, width=1, dash="dot"),
                      annotation_text="référence 33 %", annotation_position="bottom left",
                      annotation_font_color=MUTED)
        plotly_base(fig, h=250)
        fig.update_layout(yaxis=dict(tickformat=".0%", range=[0, 1], showgrid=True,
                                     gridcolor=BORDER), separators=", ",
                          xaxis=dict(type="category"), margin=dict(l=10, r=14, t=16, b=24))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _jauge_auc(auc):
    """Position de l'AUC sur 0,5 (hasard) -> 1 (parfait)."""
    pos = max(0.0, min(1.0, (auc - 0.5) / 0.5)) * 100
    return (f'<div class="vp-auc"><i style="left:{pos:.0f}%"></i></div>'
            f'<div class="vp-auc-b"><span>0,5 hasard</span><span>1 parfait</span></div>')


def _onglet_fiabilite(b, bulletins, choix, plotly_base, TEXT, MUTED, BORDER):
    carnet = _carnet()
    if carnet.get("disponible"):
        r = carnet["niveau_de_risque"]
        cpt = r["comptes"]
        _section("verified", "Carnet de fiabilité %d-%d" % tuple(carnet["periode"]),
                 "Ce que les bulletins rétrospectifs auraient annoncé (chacun limité à ce qui "
                 "était connu en avril) face à ce qui est arrivé · alerte = probabilité C3S "
                 "d'au moins 40 % (niveau calculé « élevé » ou plus, jamais affiché tant que la "
                 "compétence n'est pas démontrée)")
        tuiles = [("check_circle", EMERALD, "Détections", cpt["détection"],
                   "saisons extrêmes annoncées", "t-green"),
                  ("cancel", ROSE, "Manquées", cpt["manquée"],
                   "saisons extrêmes non annoncées", "t-amber"),
                  ("error", AMBER, "Fausses alertes", cpt["fausse alerte"],
                   "alerte, saison normale", "t-amber"),
                  ("percent", INDIGO, "Taux de détection", _pct(r["taux_detection"]),
                   "AUC %s (0,5 = hasard)" % _fr(r["auc_probabilite_c3s"] or 0), "t-indigo")]
        for col, (ic, c, lbl, val, sub, tag) in zip(st.columns(4, gap="small"), tuiles):
            col.markdown(
                f'<div class="kpi"><div class="kpi-body">'
                f'<div class="kpi-icon" style="background:{c}22;color:{c}">{_ic(ic)}</div>'
                f'<p class="kpi-lbl">{_e(lbl)}</p><p class="kpi-val">{_e(val)}</p>'
                f'<span class="kpi-tag {tag}">{_e(sub)}</span></div></div>',
                unsafe_allow_html=True)
        inond = carnet.get("inondations_documentees") or []
        if inond:
            _md('<p class="vp-legende" style="margin-top:16px !important"><b>Inondations '
                'documentées</b> : ce que le niveau calculé aurait donné</p>')
            _md('<div class="vp-inond">' + "".join(
                f'<span class="vp-chip vp-c" style="--c:{VERDICTS.get(x["verdict"], (MUTED, ""))[0]}"'
                f' title="niveau calculé : {_e(x["niveau"])}">'
                f'{_ic(VERDICTS.get(x["verdict"], (MUTED, "circle"))[1])}'
                f'<b>{x["annee"]}</b>&nbsp;{_e(x["verdict"])} · {_e(x["niveau"])}</span>'
                for x in inond) + '</div>')

    cp = b.get("competence_projection") or {}
    lo, pr = cp.get("loyo") or {}, cp.get("prevision_reelle") or {}
    if cp:
        _section("science", "Compétence de la projection océanique",
                 _e(cp.get("verdict", "")) + ". AUC 0,5 = hasard.")
        _md(
            '<div class="vp-stats">'
            f'<div class="vp-stat"><p class="vp-stat-lbl">Année testée exclue</p>'
            f'<p class="vp-stat-val">AUC {_fr(lo.get("auc", 0))}<small>p = '
            f'{_fr(lo.get("p_permutation", 1), 3)} · {_fr(p_corrige(lo.get("p_permutation", 1)), 3)} '
            f'corrigé ({len(VARIANTES_TESTEES)} variantes)</small></p>{_jauge_auc(lo.get("auc", 0.5))}</div>'
            f'<div class="vp-stat"><p class="vp-stat-lbl">Prévision réelle (passé seul)</p>'
            f'<p class="vp-stat-val">AUC {_fr(pr.get("auc", 0))}<small>p = '
            f'{_fr(pr.get("p_permutation", 1), 3)}</small></p>{_jauge_auc(pr.get("auc", 0.5))}</div>'
            '</div>')
        with st.expander("Variantes de projection comparées (fixées avant le test)"):
            _md(_tableau(
                ["Variante", "Année exclue : AUC (p)", "Prévision réelle : AUC (p)"],
                [["%s %s%s" % (v["code"], v["nom"], " (retenue)" if v.get("retenue") else ""),
                  "%s (%s)" % (_fr(v["loyo"]["auc"]), _fr(v["loyo"]["p"], 3)),
                  "%s (%s)" % (_fr(v["prevision_reelle"]["auc"]), _fr(v["prevision_reelle"]["p"], 2))]
                 for v in VARIANTES_TESTEES], alignes=(1, 2)))
            st.caption("Test exploratoire du 26/09/2026, même protocole sans fuite. "
                       "La variante retenue doit être jugée sur son p corrigé "
                       "(× %d) : une comparaison de plusieurs variantes augmente "
                       "la chance d'un bon score dû au hasard." % len(VARIANTES_TESTEES))

    # Ce que les bulletins retrospectifs auraient dit (saison choisie entouree).
    retro = sorted((bb for bb in bulletins.values()
                    if bb.get("verification") and bb.get("projection")), key=lambda x: x["annee"])
    if len(retro) >= 5:
        _section("query_stats", "Bulletins rétrospectifs : ce que la projection aurait annoncé",
                 "Chaque point n'utilise que les saisons antérieures · plein : saison observée "
                 "extrême · creux : normale · entouré : saison affichée")
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
        ici = next((x for x in retro if x["annee"] == choix), None)
        if ici:
            fig.add_trace(go.Scatter(
                x=[choix], y=[ici["projection"]["probabilite_experimentale"]], mode="markers",
                marker=dict(symbol="circle-open", size=24, color=AMBER, line=dict(width=2.5)),
                hoverinfo="skip", showlegend=False))
        fig.add_hline(y=1 / 3, line=dict(color=MUTED, width=1, dash="dot"),
                      annotation_text="référence 33 %", annotation_position="top left",
                      annotation_font_color=MUTED)
        plotly_base(fig, h=290)
        fig.update_layout(yaxis=dict(tickformat=".0%", range=[0, 1], showgrid=True,
                                     gridcolor=BORDER), separators=", ")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _onglet_historique(b, choix, plotly_base, TEXT, MUTED, BORDER):
    cl = _classement()
    if cl is None:
        _vide("bar_chart", "Classement des saisons indisponible",
              "Lancer scripts/20_veille_presaison.py pour produire classement_annees.csv.")
        return
    seuil = b["definition"]["seuil"]
    _section("bar_chart", "Empreinte des saisons %d-%d" % (cl["annee"].min(), cl["annee"].max()),
             "Somme de l'étendue de tous les événements extrêmes de la saison · "
             "<span style='color:#4F46E5'><b>indigo</b></span> : année extrême (tiers supérieur, "
             "au-dessus du trait) · <span style='color:#F59E0B'><b>ambre</b></span> : saison "
             "affichée · ▲ inondation majeure documentée")
    couleurs = [AMBER if a == choix else (INDIGO if e else MUTED)
                for a, e in zip(cl["annee"], cl["extreme"])]
    fig = go.Figure(go.Bar(
        x=cl["annee"], y=cl["empreinte"],
        marker=dict(color=couleurs, cornerradius=4,
                    opacity=[1 if (a == choix or e) else .55 for a, e in zip(cl["annee"], cl["extreme"])]),
        customdata=cl[["rang"]].values,
        hovertemplate="<b>%{x}</b><br>empreinte %{y:.0f}<br>rang %{customdata[0]}<extra></extra>"))
    inond = cl[cl["annee"].isin(INONDATIONS_CONNUES)]
    fig.add_trace(go.Scatter(x=inond["annee"], y=inond["empreinte"] + 45, mode="text",
                             text=["▲"] * len(inond), textfont=dict(color=TEXT, size=11),
                             hoverinfo="skip", showlegend=False))
    fig.add_hline(y=seuil, line=dict(color=TEXT, width=1, dash="dot"),
                  annotation_text="seuil %.0f" % seuil, annotation_position="top left",
                  annotation_font_color=MUTED)
    plotly_base(fig, h=320)
    fig.update_layout(showlegend=False, bargap=0.25, margin=dict(l=10, r=14, t=12, b=24))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(b["definition"]["mesure"])


# =============================================================================
# Diffusion
# =============================================================================
def _diffusion(b, choix):
    _section("campaign", "Diffuser ce bulletin",
             "Versions composées par le code à partir des chiffres du bulletin, sans "
             "reformulation")
    c1, c2, c3 = st.columns([1, 1, 1.6], gap="medium")
    with c1:
        _md(f'<div class="vp-dl" style="--c:{INDIGO}">{_ic("description")}'
            '<p>Bulletin complet<small>Markdown, tous les tableaux</small></p></div>')
        md = DOSSIER_SORTIE / ("bulletin_%d.md" % choix)
        if md.is_file():
            st.download_button("Télécharger (.md)", md.read_bytes(), file_name=md.name,
                               mime="text/markdown", key="veille_dl", icon=":material/download:",
                               width="stretch")
        else:
            st.caption("Fichier Markdown non produit pour cette saison.")
    with c2:
        _md(f'<div class="vp-dl" style="--c:{BLUE}">{_ic("article")}'
            '<p>Document Word<small>formel, avec la fiabilité</small></p></div>')
        try:
            donnees = _docx(choix, b["emis_le"])
        except Exception:  # python-docx absent ou bulletin incomplet: pas de bouton
            donnees = None
        if donnees:
            st.download_button("Télécharger (.docx)", donnees,
                               file_name="veille_%d.docx" % choix, key="veille_dl_docx",
                               mime="application/vnd.openxmlformats-officedocument."
                                    "wordprocessingml.document",
                               icon=":material/download:", width="stretch")
        else:
            st.caption("Document Word indisponible sur ce serveur.")
    with c3:
        texte = diffusion.sms(b)
        _md(f'<div class="vp-dl" style="--c:{EMERALD}">{_ic("sms")}'
            f'<p>Message court<small>SMS / WhatsApp · {len(texte)} / {diffusion.MAX_SMS} '
            'caractères · bouton de copie à droite</small></p></div>')
        with st.container(key="veille_sms"):
            st.code(texte, language=None, wrap_lines=True)


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
      <h1 class="pg-ttl">Veille pré-saison · risque d'année extrême</h1>
      <p class="pg-sub">Bulletin d'avril · prévision Copernicus C3S + état océanique
      novembre-avril projeté sur les configurations du mémoire</p>
    </div></div>
    """)

    bulletins = _bulletins()
    if not bulletins:
        _vide("notifications_off", "Aucun bulletin produit",
              "Lancer : py -3 scripts/20_veille_presaison.py --annee <annee>")
        return

    annees = list(bulletins)
    # Jarvis peut demander une saison sans bulletin: on retombe sur la plus recente.
    if st.session_state.get("veille_annee") not in annees:
        st.session_state.pop("veille_annee", None)

    # ── Barre de saison ─────────────────────────────────────────────────
    gauche, droite = st.columns([1, 2.4], gap="medium", vertical_alignment="bottom")
    with gauche:
        choix = st.selectbox("Saison", annees, index=0, key="veille_annee",
                             format_func=lambda a: "%d%s" % (
                                 a, " · rétrospectif" if bulletins[a].get("verification")
                                 else " · à venir" if a == max(annees) else ""))
    b = bulletins[choix]
    # Niveau colore seulement si la competence est demontree (veille/bulletin.py).
    pres = b.get("presentation") or mod_bulletin.presentation(b["niveau_risque"])
    retrospectif = bool(b.get("verification"))
    parties = mod_bulletin.synthese_parties(b)
    with droite:
        statut = {"complet": ("Bulletin final", EMERALD, "task_alt"),
                  "partiel": ("Bulletin provisoire", AMBER, "pending")}.get(
                      b.get("statut"), (str(b.get("statut", "")), MUTED, "info"))
        chips = [f'<span class="vp-chip vp-c" style="--c:{statut[1]}">{_ic(statut[2])}{_e(statut[0])}</span>']
        if retrospectif:
            chips.append(f'<span class="vp-chip vp-c" style="--c:{INDIGO}">{_ic("history")}'
                         'Rétrospectif · limité à ce qui était connu en avril</span>')
        chips.append(f'<span class="vp-chip">{_ic("calendar_today")}Émis le {_e(b["emis_le"])}</span>')
        _md(f'<div class="vp-chips">{"".join(chips)}</div>')

    # ── Verdict + chiffres clefs + lecture ──────────────────────────────
    cl = _classement()
    _bandeau(b, pres, parties, len(cl) if cl is not None else None)
    _chiffres_clefs(b, retrospectif)
    _lecture(b, parties, retrospectif)

    # ── Detail par onglets ──────────────────────────────────────────────
    _section("dashboard", "Détail", "Les données derrière chaque approche")
    # Pas d'icone :material/...: ici: le reset de police du dashboard l'afficherait en texte.
    t1, t2, t3, t4 = st.tabs(["Signaux de la saison", "Océan nov.-avr.", "Fiabilité",
                              "Historique 1981-2023"])
    proj = b.get("projection") or {}
    with t1:
        _onglet_signaux(proj, plotly_base, TEXT, MUTED, BORDER)
    with t2:
        _onglet_ocean(choix, proj, plotly_base, TEXT, MUTED, BORDER)
    with t3:
        _onglet_fiabilite(b, bulletins, choix, plotly_base, TEXT, MUTED, BORDER)
    with t4:
        _onglet_historique(b, choix, plotly_base, TEXT, MUTED, BORDER)

    _diffusion(b, choix)
    st.caption("Émis le %s · %s · ce bulletin ne remplace pas les prévisions et alertes de "
               "l'ANACIM" % (b["emis_le"], b["definition"]["mesure"]))
