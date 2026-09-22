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
    return "http://localhost:8000/jarvis"


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

    Defaut "pousse" : le contenu du dashboard se decale pendant que le panneau
    est ouvert. Mesure au navigateur sur la page Evenements (1361x680) :
    129 elements de contenu passaient sous le panneau en mode flottant, 0 en
    mode pousse -- et les graphiques Plotly se redimensionnent proprement, leur
    SVG suivant son conteneur sans rognage.

    JARVIS_WIDGET_MODE=flottant pour revenir au recouvrement classique.
    Sous 1100 px de large, le widget retombe de lui-meme sur le recouvrement :
    decaler de 400 px ecraserait le contenu.
    """
    valeur = os.environ.get("JARVIS_WIDGET_MODE", "pousse").strip().lower()
    return valeur if valeur in ("flottant", "pousse") else "pousse"


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
        import streamlit.components.v1 as components

        from jarvis.widget_html import render_widget

        html = render_widget(api_base=_api_base(), dark_mode=bool(dark_mode),
                             mode=_mode())
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
