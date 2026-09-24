"""Voix et orbe (Phase 11), cote widget.

Deux familles de tests: des regles lues dans le source (ce qui ne doit
jamais changer sans qu'on le decide) et l'execution reelle, sous Node, des
deux fonctions pures de la lecture vocale.
"""
import json
import re
import shutil
import subprocess

import pytest

from jarvis.widget_html import WIDGET_FILE, render_widget

SOURCE = WIDGET_FILE.read_text(encoding="utf-8")


def test_boutons_voix_caches_par_defaut():
    """Affiches seulement si le navigateur sait dicter / lire: un bouton
    inerte serait pire qu'aucun bouton."""
    assert re.search(r'<button id="micro"[^>]*\bhidden\b', SOURCE)
    assert re.search(r'<button class="hclose" id="voix"[^>]*\bhidden\b', SOURCE)
    assert "if(Reconnaissance){" in SOURCE
    assert "if(synthese && window.SpeechSynthesisUtterance){" in SOURCE


def test_le_micro_previent_de_l_envoi_de_l_audio():
    bouton = re.search(r'<button id="micro"[^>]*>', SOURCE).group(0)
    assert "transmettre l'audio" in bouton


def test_l_orbe_respecte_la_reduction_des_animations():
    assert "prefers-reduced-motion: reduce" in SOURCE
    assert "if(!reduit && !lance" in SOURCE           # pas de boucle d'animation
    assert "document.hidden" in SOURCE                # pause onglet cache


def test_aucune_ressource_externe():
    """Aucun CDN: la CSP interdit les ressources externes. three.js n'est
    jamais inline ni charge au demarrage: seulement depuis notre backend, a
    l'entree du mode plein ecran."""
    assert not re.search(r"<script[^>]+src=", SOURCE)
    assert "cdn" not in SOURCE.lower() and "unpkg" not in SOURCE.lower()
    assert 's.src = API + "/static/" + nom;' in SOURCE
    assert len(SOURCE) < 250_000          # three.js (600 Ko) n'est pas embarque


def test_la_lecture_s_arrete_a_la_fermeture_et_a_la_question_suivante():
    fermeture = SOURCE[SOURCE.index("function shut(){"):]
    assert "arreterLecture()" in fermeture[:300]
    question = SOURCE[SOURCE.index("function ask(text){"):]
    assert "arreterLecture()" in question[:300]


def test_widget_rendu_contient_les_deux_orbes():
    html = render_widget()
    assert 'id="orbe-fab"' in html and 'id="orbe-tete"' in html


# --- execution reelle des fonctions pures -----------------------------------------
def _fonction(nom):
    debut = SOURCE.index("  function %s(" % nom)
    fin = SOURCE.index("\n  }\n", debut) + 4
    return SOURCE[debut:fin]


@pytest.fixture(scope="module")
def node():
    chemin = shutil.which("node")
    if not chemin:
        pytest.skip("node absent")
    return chemin


def _executer(node, appels):
    script = "\n".join([_fonction("textePourLecture"), _fonction("langueDe"),
                        "console.log(JSON.stringify([%s]));" % ",".join(appels)])
    sortie = subprocess.run([node, "-e", script], capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


def test_texte_lu_sans_markdown(node):
    md = ("**AMO** au lag 4 : r = -0,42 (`p_neff` = 0,006).\n"
          "- point un\n- point deux\n"
          "| a | b |\n|---|---|\n| 1 | 2 |\n"
          "Voir [le mémoire](https://exemple.sn/m.pdf).\n"
          "```python\nprint('code')\n```")
    (texte,) = _executer(node, ["textePourLecture(%s)" % json.dumps(md)])
    assert "**" not in texte and "`" not in texte and "|" not in texte
    assert "https" not in texte and "print(" not in texte
    assert "AMO au lag 4" in texte and "le mémoire" in texte
    assert "point un" in texte


def test_texte_lu_borne(node):
    (texte,) = _executer(node, ["textePourLecture('mot '.repeat(2000))"])
    assert len(texte) <= 2000


def test_langue_de_la_reponse(node):
    fr, en = _executer(node, [
        "langueDe('La corrélation est négative et les pluies sont moins intenses dans la phase')",
        "langueDe('The correlation is negative and the rainfall is weaker with this index')",
    ])
    assert fr == "fr-FR" and en == "en-US"
