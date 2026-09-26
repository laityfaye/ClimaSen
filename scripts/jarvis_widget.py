#!/usr/bin/env python3
"""Injection de la bulle Jarvis dans le dashboard Streamlit.

Contrat de ce module: il ne doit JAMAIS faire tomber une page. Toute erreur
(backend absent, fichier manquant, version de Streamlit inattendue) est avalee
et le dashboard continue exactement comme avant.

Le widget vit dans une iframe de composant Streamlit. Pourquoi pas st.markdown:
Streamlit n'execute pas les balises <script> injectees en markdown. L'iframe de
composant, elle, execute son JavaScript normalement.
"""
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _api_base() -> str:
    """Base d'URL du backend Jarvis, vue depuis le navigateur.

    En production, widget et backend sont derriere le meme nginx: une base
    relative suffit. En local, Streamlit ecoute sur 8501 et Jarvis sur 8000,
    donc il faut une base absolue (sinon requete vers le mauvais port).
    """
    explicit = os.environ.get("JARVIS_WIDGET_API_BASE")
    if explicit:
        return explicit.rstrip("/")
    if os.environ.get("JARVIS_ENV", "dev") == "prod":
        return "/jarvis"
    # 8010 et non 8000 en local: JARVIS-pro, l'assistant de bureau de Laity,
    # occupe deja le port 8000. La bulle interrogeait alors JARVIS-pro, qui
    # repondait 404, et s'affichait "hors ligne" (constate le 24/09/2026).
    return "http://localhost:8010/jarvis"


HAUTEUR_REPLIEE = 76      # doit correspondre a H_SHUT dans widget.html


def est_active() -> bool:
    """Interrupteur d arret d urgence.

    JARVIS_WIDGET=off desactive la bulle sans toucher au code, le temps de
    diagnostiquer un probleme d affichage. Le dashboard redevient exactement
    ce qu il etait avant Jarvis.
    """
    return os.environ.get("JARVIS_WIDGET", "on").strip().lower() not in (
        "off", "0", "false", "no")


def _mode() -> str:
    """Mode d affichage du panneau.

    Defaut "flottant" : la carte se superpose au dashboard sans rien deplacer.

    Le defaut a longtemps ete "pousse", sur la foi d'une mesure : sur la page
    Evenements en 1361x680, 129 elements de contenu passaient sous le panneau
    en flottant, 0 en pousse. L'argument ne tient plus depuis que la carte est
    redimensionnable : c'est l'utilisateur qui decide de la place qu'elle
    prend, et voir la mise en page du dashboard se reorganiser a chaque
    ouverture est plus derangeant qu'un coin masque.

    JARVIS_WIDGET_MODE=pousse retablit le decalage. Sous 1100 px de large, ce
    mode retombe de lui-meme sur le recouvrement : decaler de 400 px
    ecraserait le contenu.
    """
    valeur = os.environ.get("JARVIS_WIDGET_MODE", "flottant").strip().lower()
    return valeur if valeur in ("flottant", "pousse") else "flottant"


# Contexte de page (Phase 7): quelle cle de st.session_state porte quel
# filtre, page par page. Les noms de gauche sont ceux qu'accepte le serveur
# (jarvis/page_context.py, CHAMPS): un champ ajoute ici sans y etre declare
# serait ignore cote serveur, jamais transmis au modele.
CLES_CONTEXTE = {
    "Evenements": {
        "annees": "evt_yr_range",
        "phases": "evt_phases_sel",
        "evenement_date": "jarvis_evt_date",
    },
    "Indices SST": {
        "indices": "sst_sel_idx",
        "agregation": "sst_agg_mode",
    },
    "Teleconnexions": {
        "phase": "tc_phase",
        "metrique": "tc_metric",
        "type_correlation": "tc_type",
        "significatives_seulement": "tc_show_sig",
        "p_value": "tc_p_mode",
        "phase_lag0": "lag0_phase_sel",
        "indices_series": "tc_sel_indices",
    },
    "Clustering": {
        "phase": "cl_phase",
        "cluster": "cl_shared_cluster",
        "metrique_barres": "cl_metric_bar",
    },
    "Pipeline": {
        "onglet": "pip_tab",
    },
}


def _simple(valeur):
    """Ramene une valeur de session a un type JSON natif.

    Les selecteurs Streamlit renvoient des numpy.int64 (identifiants de
    cluster), des tuples (curseurs a deux bornes): json.dumps refuserait les
    premiers et le serveur n'accepte que des listes pour les seconds.
    """
    if hasattr(valeur, "item") and not isinstance(valeur, (list, tuple, dict)):
        try:
            return valeur.item()
        except Exception:                          # noqa: BLE001
            return valeur
    if isinstance(valeur, (list, tuple)):
        return [_simple(v) for v in valeur]
    return valeur


def contexte_page(etat) -> dict:
    """Page ouverte et filtres regles, lus dans st.session_state.

    Ne leve jamais: sans contexte, Jarvis repond quand meme, simplement sans
    savoir ce que l'utilisateur regarde.
    """
    try:
        page = etat.get("nav_page")
        cles = CLES_CONTEXTE.get(page)
        if cles is None:
            return None
        filtres = {}
        for champ, cle in cles.items():
            if cle in etat:
                filtres[champ] = _simple(etat[cle])
        return {"page": page, "filtres": filtres}
    except Exception:                              # noqa: BLE001
        return None


# =============================================================================
# Pilotage du dashboard par Jarvis (outil navigate_dashboard, mode soutenance)
# =============================================================================
# Le widget ecrit la consigne (JSON) dans un champ de saisie cache de la page
# et la valide: Streamlit reexecute le script, et appliquer_navigation() regle
# la page et les filtres AVANT que les pages ne creent leurs selecteurs
# (Streamlit interdit de modifier la valeur d'un selecteur deja affiche).
#
# Pourquoi pas l'URL (?jarvis_nav=...): une fois qu'un parametre a ete ecrit
# par l'application (?dm= du mode sombre), Streamlit ne relit plus l'adresse
# du navigateur a la reexecution -- la consigne etait perdue (constate dans
# le code de Streamlit 1.54, getQueryString).
CLE_COMMANDE = "jarvis_nav_cmd"
MAX_NAVIGATION = 2000

# Cles de session a accompagner. La page Clustering remet le cluster a zero
# des que la phase change (cl_shared_last_phase != phase): une consigne qui
# regle phase ET cluster verrait son cluster efface. On note donc la phase
# comme deja vue (constate en test de bout en bout).
ACCOMPAGNEMENTS = {("Clustering", "phase"): "cl_shared_last_phase"}


def _valeur_admise(valeur):
    """Types simples seulement: la consigne vient de l'URL, donc de
    n'importe qui (elle ne touche que la session de ce navigateur)."""
    if isinstance(valeur, bool) or valeur is None:
        return True
    if isinstance(valeur, (int, float)):
        return True
    if isinstance(valeur, str):
        return len(valeur) <= 40
    if isinstance(valeur, list):
        return len(valeur) <= 12 and all(
            isinstance(v, (str, int, float)) and not isinstance(v, bool)
            and (not isinstance(v, str) or len(v) <= 40) for v in valeur)
    return False


def lire_navigation(brut):
    """{"page", "filtres": {cle_session: valeur}} ou None.

    Seuls les filtres declares dans CLES_CONTEXTE pour la page sont retenus;
    le reste est ignore. Pure: testable sans Streamlit.
    """
    import json
    if not brut or len(brut) > MAX_NAVIGATION:
        return None
    try:
        demande = json.loads(brut)
    except ValueError:
        return None
    if not isinstance(demande, dict):
        return None
    page = demande.get("page")
    if page not in CLES_CONTEXTE:
        return None
    filtres = demande.get("filtres") or {}
    if not isinstance(filtres, dict):
        filtres = {}
    reglages = {}
    for champ, valeur in filtres.items():
        cle = CLES_CONTEXTE[page].get(champ)
        if cle is None or not _valeur_admise(valeur):
            continue
        # Les curseurs a deux bornes attendent un tuple.
        reglages[cle] = tuple(valeur) if champ == "annees" else valeur
        compagnon = ACCOMPAGNEMENTS.get((page, champ))
        if compagnon and "cluster" in filtres:
            reglages[compagnon] = valeur
    return {"page": page, "filtres": reglages}


def appliquer_navigation(st) -> bool:
    """A appeler tot dans dashboard.py, avant la barre laterale et les pages."""
    try:
        brut = st.session_state.get(CLE_COMMANDE)
        if not brut:
            return False
        # Vide avant la creation du champ: la meme consigne pourra repartir.
        st.session_state[CLE_COMMANDE] = ""
        consigne = lire_navigation(brut)
        if consigne is None:
            return False
        st.session_state["nav_page"] = consigne["page"]
        for cle, valeur in consigne["filtres"].items():
            st.session_state[cle] = valeur
        return True
    except Exception:                              # noqa: BLE001
        return False


def _contexte_cache(st, contexte) -> None:
    """Contexte de page dans un element cache de la page hote.

    Le widget le lit au moment de chaque question. Il n'est plus inscrit dans
    le HTML du composant: ce HTML change alors a chaque filtre, et Streamlit
    RECHARGEAIT l'iframe a chaque clic -- Jarvis s'interrompait en pleine
    phrase des qu'il ouvrait lui-meme une page.
    """
    import html as html_mod
    import json
    texte = html_mod.escape(json.dumps(contexte, ensure_ascii=True)) if contexte else ""
    st.markdown('<div id="jarvis-page-ctx" hidden>%s</div>' % texte,
                unsafe_allow_html=True)


derniere_erreur = None


def render(dark_mode: bool = True) -> bool:
    """Affiche la bulle. Retourne True si l'injection a reussi.

    En cas d echec, l exception est conservee dans `derniere_erreur` au lieu
    d etre perdue : un widget qui ne s affiche pas sans laisser de trace est
    indiagnosticable.
    """
    global derniere_erreur
    if not est_active():
        return False
    try:
        import streamlit as st
        import streamlit.components.v1 as components

        from jarvis.widget_html import render_widget

        # HTML identique d'une execution a l'autre (pas de contexte dedans):
        # l'iframe n'est pas rechargee quand on change de page ou de filtre.
        html = render_widget(api_base=_api_base(), dark_mode=bool(dark_mode),
                             mode=_mode(), page_context=None)
        # Hauteur de la bulle repliee, et non 0.
        #
        # Arbitrage : avec 0, le composant ne reserve aucune place dans le flux,
        # mais si l epinglage en position:fixed echoue cote navigateur, l iframe
        # reste haute de 0 px et la bulle est INVISIBLE, sans le moindre
        # message. Un widget invisible est bien pire qu un espace de 76 px en
        # bas de page. On garde donc une hauteur qui fonctionne meme sans
        # JavaScript, et l epinglage n est plus qu une amelioration.
        components.html(html, height=HAUTEUR_REPLIEE, scrolling=False)
        _contexte_cache(st, contexte_page(st.session_state))
        # Champ cache ou le widget depose ses consignes de navigation.
        st.text_input("jarvis", key=CLE_COMMANDE, label_visibility="collapsed")
        # Emplacement sans hauteur ni ecart: il est en tete de page. Surtout
        # PAS de position:fixed ici: un ancetre fixe forme un contexte
        # d'empilement, l'iframe (z-index 2147483000) y serait enfermee et la
        # barre laterale de Streamlit passait DEVANT Jarvis (constate).
        st.markdown(
            "<style>.st-key-%s{display:none!important}"
            ".st-key-jarvis_slot,div:has(>.st-key-jarvis_slot){max-height:0!important;"
            "min-height:0!important;overflow:visible!important;gap:0!important}"
            "div:has(>.st-key-jarvis_slot){margin-bottom:-1rem!important}"
            "</style>" % CLE_COMMANDE, unsafe_allow_html=True)
        derniere_erreur = None
        return True
    except Exception as exc:                      # noqa: BLE001
        import traceback
        derniere_erreur = traceback.format_exc()
        print("[Jarvis] echec de l injection du widget :")
        print(derniere_erreur)
        return False
