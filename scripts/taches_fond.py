"""Taches longues du pipeline en arriere-plan (page Pipeline).

Le bouton "Executer" d'une etape lance le script en BLOQUANT la page
(run_script) : acceptable pour quelques secondes, pas pour le cube SST (~7 min)
ni pour la veille, qui telecharge depuis NOAA et Copernicus. Ici, le script
part dans un processus detache (scripts/lancer_tache.py) qui tient lui-meme son
etat ; la page relit cet etat et le journal, sans jamais bloquer.

Une seule tache "lourde" a la fois sur le serveur (cube, veille) : deux
lectures concurrentes des 42 Go d'OISST satureraient le disque.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "outputs" / "taches"
LANCEUR = RACINE / "scripts" / "lancer_tache.py"
# Au-dela, une tache "en_cours" dont l'etat n'est plus rafraichi a ete
# interrompue (le lanceur ecrit toutes les 5 s).
SILENCE_MAX_S = 60

LIBELLES = {"en_cours": "En cours", "termine": "Terminé", "erreur": "En erreur",
            "annule": "Annulé", "interrompu": "Interrompu"}


def processus_vivant(pid):
    """Le processus `pid` tourne-t-il encore ? Sans jamais le toucher.

    os.kill(pid, 0) est un simple test sous Linux, mais sous Windows il appelle
    TerminateProcess : il TUE le processus qu'il devait observer (cas des
    telechargements CHIRPS / OISST lances depuis la page Pipeline).
    """
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))    # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == 259          # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    # Un enfant de Streamlit qui a fini reste "zombie" tant que personne ne le
    # recolte, et os.kill(pid, 0) le voit vivant : la page Pipeline restait alors
    # bloquee sur "en cours" (relance toutes les 3 s) apres un telechargement
    # CHIRPS termine. waitpid le recolte s'il est a nous.
    try:
        fini, _ = os.waitpid(int(pid), os.WNOHANG)
        return fini == 0
    except ChildProcessError:
        pass                   # pas notre enfant : simple test d'existence
    except OSError:
        return False
    try:
        os.kill(int(pid), 0)
    except PermissionError:
        return True            # existe, mais appartient a un autre utilisateur
    except OSError:
        return False
    return True


def _lire(nom):
    p = DOSSIER / (nom + ".json")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def etat(nom):
    """Etat de la tache, ou None si elle n'a jamais tourne."""
    e = _lire(nom)
    if not e:
        return None
    if e.get("etat") == "en_cours":
        try:
            vu = datetime.fromisoformat(e["vu_le"])
            silence = (datetime.now(timezone.utc) - vu).total_seconds()
        except (KeyError, ValueError):
            silence = SILENCE_MAX_S + 1
        if silence > SILENCE_MAX_S:
            e["etat"] = "interrompu"
    e["active"] = e.get("etat") == "en_cours"
    return e


def active(nom):
    e = etat(nom)
    return bool(e and e["active"])


def taches_actives(noms):
    return [n for n in noms if active(n)]


def journal(nom, n=14):
    p = DOSSIER / (nom + ".log")
    try:
        lignes = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lignes[-n:])


def lancer_chaine(nom, scripts):
    """Lance des scripts dans l'ordre, arret a la premiere erreur ; False si
    la chaine tourne deja."""
    return lancer(nom, "--chaine", list(scripts))


def lancer(nom, script, arguments=()):
    """Lance la tache ; False si elle tourne deja."""
    if active(nom):
        return False
    DOSSIER.mkdir(parents=True, exist_ok=True)
    options = {}
    if os.name == "nt":
        options["creationflags"] = (subprocess.DETACHED_PROCESS
                                    | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        options["start_new_session"] = True   # survit au redemarrage de la session
    subprocess.Popen([sys.executable, str(LANCEUR), nom, script] + [str(a) for a in arguments],
                     cwd=str(RACINE), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **options)
    return True


def annuler(nom):
    (DOSSIER / (nom + ".annuler")).touch()


def _date(iso):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso).astimezone()
        return d.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def suivi(nom, cle):
    """Bloc Streamlit : etat, journal, Annuler (administrateur seulement) ; se
    rafraichit seul pendant l'execution (fragment), sans recharger la page."""
    import streamlit as st
    import admin_gate

    @st.fragment(run_every=3 if active(nom) else None)
    def _bloc():
        e = etat(nom)
        if not e:
            return
        libelle = LIBELLES.get(e["etat"], e["etat"])
        texte = "**%s** · lancé le %s" % (libelle, _date(e.get("debut")))
        if e.get("fin"):
            texte += " · fini le %s" % _date(e["fin"])
        if e["etat"] == "interrompu":
            texte += " · le processus ne répond plus (serveur redémarré ?)"
        st.markdown(texte)
        etapes = e.get("etapes")
        if etapes:
            faites = sum(1 for x in etapes if x["etat"] == "termine")
            courante = e.get("etape_courante") or 0
            if e["active"] and courante:
                st.progress(faites / len(etapes),
                            text="Étape %d/%d : %s" % (courante, len(etapes),
                                                       etapes[courante - 1]["script"]))
            marques = {"termine": "✓", "erreur": "✗", "annule": "–", "en_cours": "…",
                       "en_attente": "·", "non_lance": "·"}
            st.caption("  ".join("%s %s" % (marques.get(x["etat"], "·"), x["script"].split("_")[0])
                                 for x in etapes))
            echec = next((x for x in etapes if x["etat"] == "erreur"), None)
            if echec:
                st.markdown("Arrêt à **%s** (code %s) : les étapes suivantes n'ont pas été "
                            "lancées." % (echec["script"], echec.get("code")))
        log = journal(nom)
        if log:
            st.code(log, language="text")
        suivie = "%s_suivie" % cle
        if e["active"]:
            st.session_state[suivie] = True
            if admin_gate.est_admin() and st.button("Annuler", key="%s_annuler" % cle)                     and admin_gate.exiger_admin():
                annuler(nom)
                st.toast("Arrêt demandé : la tâche s'arrête dans quelques secondes.")
        elif st.session_state.pop(suivie, False):
            # Fin observee pendant le suivi : recharger toute la page (etat des
            # sorties, et arret du rafraichissement du fragment).
            st.rerun(scope="app")
    _bloc()
