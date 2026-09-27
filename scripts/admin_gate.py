"""Verrou administrateur du dashboard ClimatSen.

Les actions qui lancent un processus ou modifient des fichiers sur le serveur
(pipeline, telechargements, suppression SST, relance du clustering) ne sont
proposees QUE dans une session deverrouillee par le mot de passe administrateur
de Jarvis (meme hache scrypt, JARVIS_ADMIN_PASSWORD_HASH dans .env).

Streamlit s'execute cote serveur : un bouton qui n'est pas rendu ne peut pas
etre declenche par le navigateur. On verifie malgre tout `est_admin()` au
moment de l'execution (exiger_admin), pour qu'un futur appel oublie derriere
un bouton visible ne suffise pas a lancer un script.
"""
import os
import sys
import time
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CLE_SESSION = "climatsen_admin"
_CLE_ECHECS = "climatsen_admin_echecs"
MAX_ECHECS = 5          # par session, ensuite formulaire bloque
DELAI_ECHEC_S = 1.0     # ralentit l'essai en serie (en plus du cout scrypt)


def _hache_stocke() -> str:
    """Hache admin : variable d'environnement, sinon .env du projet."""
    val = os.environ.get("JARVIS_ADMIN_PASSWORD_HASH", "").strip()
    if val:
        return val
    env = _PROJECT_ROOT / ".env"
    try:
        for ligne in env.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne.startswith("JARVIS_ADMIN_PASSWORD_HASH="):
                return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _verifier(mot_de_passe: str) -> bool:
    try:
        from jarvis.auth import verifier
    except Exception:
        return False
    return verifier(mot_de_passe, _hache_stocke())


def est_admin() -> bool:
    return bool(st.session_state.get(_CLE_SESSION, False))


def exiger_admin() -> bool:
    """A appeler juste avant toute execution. Affiche un refus si besoin."""
    if est_admin():
        return True
    st.error("Action réservée à l'administrateur.")
    return False


def deconnecter() -> None:
    st.session_state[_CLE_SESSION] = False


def formulaire_connexion(MUTED: str, cle: str = "admin") -> None:
    """Petit formulaire de deverrouillage, ou etat + bouton de deconnexion."""
    if est_admin():
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown(
                f"<p style='font-size:0.78rem;color:{MUTED};margin:8px 0;'>"
                "Session administrateur active : les actions d'execution sont "
                "disponibles.</p>",
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("Verrouiller", key=f"{cle}_logout", use_container_width=True):
                deconnecter()
                st.rerun()
        return

    echecs = int(st.session_state.get(_CLE_ECHECS, 0))
    with st.expander("Administration"):
        st.markdown(
            f"<p style='font-size:0.78rem;color:{MUTED};margin:0 0 8px 0;'>"
            "Les actions qui s'executent sur le serveur (pipeline, "
            "telechargements, suppression de fichiers, relance du clustering) "
            "sont reservees a l'administrateur.</p>",
            unsafe_allow_html=True,
        )
        if echecs >= MAX_ECHECS:
            st.warning("Trop d'essais. Rechargez la page pour reessayer.")
            return
        with st.form(key=f"{cle}_form", clear_on_submit=True):
            mdp = st.text_input("Mot de passe administrateur", type="password",
                                key=f"{cle}_pwd")
            ok = st.form_submit_button("Deverrouiller")
        if ok:
            if _verifier(mdp):
                st.session_state[_CLE_SESSION] = True
                st.session_state[_CLE_ECHECS] = 0
                st.rerun()
            else:
                time.sleep(DELAI_ECHEC_S)
                st.session_state[_CLE_ECHECS] = echecs + 1
                st.error("Mot de passe incorrect.")
