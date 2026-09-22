"""Acces aux donnees de la plateforme, pour les outils publics.

Principe: une seule source de verite avec le dashboard. Les outils ne relisent
pas les CSV a leur maniere, ils passent par les loaders de
scripts/dashboard_utils.py -- les memes que les cinq pages Streamlit. Si le
dashboard et Jarvis annoncaient deux chiffres differents pour la meme question,
la plateforme perdrait toute credibilite.

Deux precautions:

1. Import PARESSEUX. dashboard_utils tire streamlit, plotly et matplotlib
   (~3 s). Les charger a l'import de jarvis.tools alourdirait chaque demarrage
   et chaque rechargement d'uvicorn, y compris quand aucun outil n'est appele.
   Le module n'est donc importe qu'au premier besoin reel.

2. Execution HORS boucle d'evenements. Les loaders sont synchrones et lisent le
   disque; appeles directement dans une coroutine ils gelent le serveur pour
   tous les visiteurs. Tout passe par asyncio.to_thread.
"""
import asyncio
import logging
import sys
import threading
from pathlib import Path

log = logging.getLogger("jarvis.tools.dataset")

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"

_import_lock = threading.Lock()
_utils_module = None


class DataUnavailableError(Exception):
    """Un jeu de donnees attendu est absent ou illisible.

    Remontee telle quelle au modele sous forme de tool_result en erreur: mieux
    vaut un "je n'ai pas pu lire cette donnee" qu'un chiffre invente.
    """


def _silence_streamlit() -> None:
    """Coupe le bavardage de streamlit hors de son runtime.

    Appeles hors d'une session Streamlit, les loaders caches emettent
    "No runtime found" et "missing ScriptRunContext" a chaque appel. Le cache
    fonctionne malgre tout (verifie), mais ces lignes noieraient les logs.
    """
    for nom in ("streamlit.runtime.caching.cache_data_api",
                "streamlit.runtime.scriptrunner_utils.script_run_context",
                "streamlit.runtime.state.session_state_proxy"):
        logging.getLogger(nom).setLevel(logging.ERROR)


def _utils():
    global _utils_module
    if _utils_module is not None:
        return _utils_module
    with _import_lock:
        if _utils_module is None:
            try:
                # Streamlit reconfigure ses loggers a l'import: le faire venir
                # en premier, puis le taire, evite trois lignes d'avertissement
                # au demarrage a chaque decorateur de cache rencontre.
                import streamlit  # noqa: F401
            except Exception:
                pass
            _silence_streamlit()
            if str(SCRIPTS_DIR) not in sys.path:
                # dashboard_utils n'est pas un paquet: les pages du dashboard
                # procedent exactement ainsi (voir scripts/pages/*.py).
                sys.path.insert(0, str(SCRIPTS_DIR))
            try:
                import dashboard_utils  # noqa: F401  (import differe volontaire)
            except Exception as exc:  # pragma: no cover - depend de l'install
                log.exception("Import de dashboard_utils impossible.")
                raise DataUnavailableError(str(exc)) from exc
            _silence_streamlit()
            _utils_module = dashboard_utils
    return _utils_module


def _charger(nom_loader: str):
    utils = _utils()
    loader = getattr(utils, nom_loader, None)
    if loader is None:  # pragma: no cover - garde-fou de refactoring
        raise DataUnavailableError("Loader inconnu: %s" % nom_loader)
    try:
        donnees = loader()
    except FileNotFoundError as exc:
        raise DataUnavailableError(str(exc)) from exc
    except Exception as exc:
        log.exception("Echec du loader %s", nom_loader)
        raise DataUnavailableError(str(exc)) from exc
    if donnees is None:
        raise DataUnavailableError("Jeu de donnees absent: %s" % nom_loader)
    return donnees


# Noms logiques utilises par les outils -> loaders du dashboard.
LOADERS = {
    "events":       "load_events",
    "indices":      "load_sst",
    "correlations": "load_telecon",
    "clustering":   "load_clustering",
}


def get(nom: str):
    """Charge un jeu de donnees (bloquant). Utilise par les tests et preload()."""
    if nom not in LOADERS:  # pragma: no cover - garde-fou de refactoring
        raise DataUnavailableError("Jeu de donnees inconnu: %s" % nom)
    return _charger(LOADERS[nom])


async def load(noms) -> dict:
    """Charge plusieurs jeux de donnees sans bloquer la boucle d'evenements."""
    def _bloquant():
        return {nom: get(nom) for nom in noms}
    return await asyncio.to_thread(_bloquant)


def preload() -> None:
    """Prechauffe le cache au demarrage.

    Sans cela le premier visiteur qui declenche un outil paie l'import de
    streamlit et la lecture des CSV, soit 3 a 4 s ajoutees a sa reponse.
    Les echecs sont journalises, jamais propages: un jeu de donnees manquant
    ne doit pas empecher le service de demarrer.
    """
    for nom in LOADERS:
        try:
            get(nom)
        except Exception as exc:
            log.warning("Prechauffement de %s impossible: %s", nom, exc)
    log.info("Donnees de la plateforme prechargees.")
