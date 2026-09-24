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

        html = render_widget(api_base=_api_base(), dark_mode=bool(dark_mode),
                             mode=_mode(),
                             page_context=contexte_page(st.session_state))
        # Hauteur de la bulle repliee, et non 0.
        #
        # Arbitrage : avec 0, le composant ne reserve aucune place dans le flux,
        # mais si l epinglage en position:fixed echoue cote navigateur, l iframe
        # reste haute de 0 px et la bulle est INVISIBLE, sans le moindre
        # message. Un widget invisible est bien pire qu un espace de 76 px en
        # bas de page. On garde donc une hauteur qui fonctionne meme sans
        # JavaScript, et l epinglage n est plus qu une amelioration.
        components.html(html, height=HAUTEUR_REPLIEE, scrolling=False)
        derniere_erreur = None
        return True
    except Exception as exc:                      # noqa: BLE001
        import traceback
        derniere_erreur = traceback.format_exc()
        print("[Jarvis] echec de l injection du widget :")
        print(derniere_erreur)
        return False
