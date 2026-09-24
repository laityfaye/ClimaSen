"""Interface J.A.R.V.I.S (reprise de JARVIS-pro): route statique, theme des
figures, structure du mode plein ecran."""
import re

import pytest

from jarvis import figures
from jarvis.widget_html import WIDGET_FILE

SOURCE = WIDGET_FILE.read_text(encoding="utf-8")


# --- fichier de l'orbe 3D ---------------------------------------------------------
def test_orbe_servie(client):
    r = client.get("/jarvis/static/jarvis-orb.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    assert "max-age" in r.headers["cache-control"]
    assert "window.createOrb" in r.text or "createOrb" in r.text


@pytest.mark.parametrize("nom", ["three.min.js", "orb.js", "app.js", "..%2Fapp.py",
                                 "..%2F..%2F.env", "widget.html", "JARVIS-ORB.JS"])
def test_route_statique_a_liste_fermee(client, nom):
    assert client.get("/jarvis/static/%s" % nom).status_code == 404


def test_orbe_de_la_version_bureau_avec_three_170_et_sa_licence():
    from jarvis.app import FICHIERS_HUD
    orbe = FICHIERS_HUD["jarvis-orb.js"].read_text(encoding="utf-8")
    assert "SPDX-License-Identifier: MIT" in orbe          # licence de three.js
    assert '"170"' in orbe                                  # three.js r170
    assert "frontend/src/orb.ts" in orbe[:600]              # provenance declaree
    assert "localStorage" not in orbe and "WebSocket(" not in orbe


def test_un_seul_fichier_charge_par_le_widget():
    assert 'script("jarvis-orb.js")' in SOURCE
    assert "three.min.js" not in SOURCE


# --- theme des figures ---------------------------------------------------------------
def test_theme_hud_des_figures(client):
    spec = {"genre": "barres", "type": "events_by_month", "titre": "T", "sous_titre": "S",
            "donnees": {"categories": ["mai", "juin"], "valeurs": [3, 5],
                        "x_label": "mois", "y_label": "n"}}
    png = figures.rendre(spec, "hud")
    assert png.startswith(b"\x89PNG") and png != figures.rendre(spec, "sombre")
    assert "hud" in figures.THEMES
    assert '"?theme=hud"' in SOURCE


# --- structure du mode plein ecran --------------------------------------------------------
@pytest.mark.parametrize("ident", ["hud", "hud-orbe", "hud-menu-btn", "hud-menu",
                                   "hud-horloge", "hud-micro", "hud-stop", "hud-continu",
                                   "hud-boot", "hud-btn"])
def test_elements_du_hud_presents(ident):
    assert 'id="%s"' % ident in SOURCE


def test_ecran_de_demarrage_sans_faux_online():
    """Chaque ligne de l'ecran de demarrage reflete un etat reel."""
    bloc = SOURCE[SOURCE.index("var modules = ["):SOURCE.index("liste.innerHTML")]
    for ligne in re.findall(r'\["([A-Z_0-9]+)", ([^\]]+)\]', bloc):
        assert "?" in ligne[1], ligne       # toujours une condition, jamais un OK fige


def test_plein_ecran_ne_style_que_notre_iframe():
    bloc = SOURCE[SOURCE.index("function pleinEcran(oui)"):SOURCE.index("function majMenu()")]
    assert "frame.style" in bloc
    assert "parent.document" not in bloc


def test_ecoute_continue_exige_le_mot_d_appel():
    assert "bjarvis" in SOURCE
    bloc = SOURCE[SOURCE.index("if(state.continu){"):]
    assert "ask(m[1].trim())" in bloc[:600]


def test_stop_interrompt_voix_ecoute_et_reponse():
    bloc = SOURCE[SOURCE.index("function arreterTout()"):]
    bloc = bloc[:bloc.index("\n  }\n")]            # fin de la fonction
    for appel in ("arreterLecture()", "reco.abort()", "state.requete.abort()"):
        assert appel in bloc
