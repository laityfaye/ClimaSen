"""Rendu du widget.

Module volontairement sans dependance a FastAPI: scripts/jarvis_widget.py
l'importe depuis le process Streamlit, qui n'a aucune raison de charger le
backend.
"""
from functools import lru_cache
from pathlib import Path

WIDGET_FILE = Path(__file__).resolve().parent / "widget" / "widget.html"


@lru_cache(maxsize=1)
def _template() -> str:
    return WIDGET_FILE.read_text(encoding="utf-8")


MODES = ("flottant", "pousse")


def render_widget(api_base: str = "/jarvis", dark_mode: bool = True,
                  mode: str = "flottant") -> str:
    """Injecte la base d'API, le theme et le mode d'affichage dans le gabarit.

    api_base ne doit jamais se terminer par un slash: le widget concatene
    directement "/api/chat".

    mode:
      "flottant" (defaut) le panneau se superpose a la page, comme une bulle
                 de chat classique. Dimensionne pour ne jamais occuper plus de
                 la moitie basse de l ecran.
      "pousse"   le bloc principal du dashboard recoit une marge a droite
                 pendant que le panneau est ouvert: plus aucun recouvrement,
                 au prix d une reorganisation de la page (les graphiques
                 Plotly se redimensionnent).
    """
    base = (api_base or "/jarvis").rstrip("/")
    if mode not in MODES:
        mode = "flottant"
    return (_template()
            .replace("__JARVIS_API_BASE__", base)
            .replace("__JARVIS_DARK__", "true" if dark_mode else "false")
            .replace("__JARVIS_MODE__", mode))
