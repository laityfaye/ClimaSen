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


def test_accueil_a_l_entree_seulement_pas_au_remontage():
    """Streamlit remonte l'iframe a chaque interaction (entrer(true)): Jarvis
    ne doit saluer que quand l'utilisateur entre lui-meme."""
    entrer = SOURCE[SOURCE.index("function entrer(sansDemarrage){"):]
    entrer = entrer[:entrer.index("function sortir(){")]
    assert "if(!sansDemarrage){" in entrer and "saluer(false)" in entrer


def test_accueil_par_profil_et_local():
    accueil = SOURCE[SOURCE.index("function texteAccueil("):]
    accueil = accueil[:accueil.index("function saluer(")]
    assert "fetch(" not in accueil                    # aucun appel au modele
    admin, public = accueil.split("return s + \", je suis **Jarvis**")
    # Les capacites admin n'apparaissent pas dans l'accueil public.
    assert "**Code**" in admin and "**Code**" not in public
    assert "approbation" in admin
    assert "**Téléconnexions**" in public


def test_accueil_admin_malgre_le_flux_en_cours():
    """L'elevation arrive pendant le flux (busy): l'accueil admin passe."""
    assert "saluer(true, d.model);" in SOURCE
    assert "if(state.busy && !forcerComplet){ return; }" in SOURCE


def test_voix_active_par_defaut_en_plein_ecran_sauf_refus():
    assert 'recall("voix") !== "0"' in SOURCE
    assert 'if(recall("voix") !== null){ basculerVoix(recall("voix") === "1"); }' in SOURCE


def test_pas_de_sous_titre_quand_jarvis_parle():
    """Choix de Laity: en plein ecran, voix active, le texte ne s'affiche
    pas; la transcription reste accessible, et l'option dans le menu."""
    sous = SOURCE[SOURCE.index("function soustitre(md, fini){"):]
    sous = sous[:sous.index("function plein(){")]
    assert 'el.textContent = sousTitresVisibles() ? texte : "";' in sous
    assert '"TRANSCRIPTION"' in sous
    assert "function sousTitresVisibles(){ return !state.voix || !!state.soustitres; }" in SOURCE
    assert 'data-action="soustitres"' in SOURCE


def test_jarvis_parle_pendant_qu_il_ecrit():
    """La voix demarre des la premiere phrase du flux, pas a la fin."""
    delta = SOURCE[SOURCE.index('} else if(name === "delta"){'):]
    delta = delta[:delta.index('} else if(name === "error"){')]
    assert "alimenterLecture(lecture, target._raw, false);" in delta
    assert "alimenterLecture(lecture, target ? target._raw : \"\", true);" in SOURCE
    # Pas de coupure au milieu d'un nombre ("Nino 3.4", "-0,42").
    assert r"/[.!?;:\n](?=\s)/g" in SOURCE


def test_la_bulle_ouvre_la_petite_fenetre_d_abord():
    """Choix de Laity: la bulle ouvre la petite fenetre; le plein ecran
    J.A.R.V.I.S s'ouvre par son bouton. Echap y ramene a la petite fenetre."""
    fab = SOURCE[SOURCE.index('fab.addEventListener("click"'):]
    fab = fab[:fab.index("});") + 3]
    assert "open();" in fab and "Hud.entrer" not in fab
    assert '$("hud-btn").addEventListener("click", function(){ Hud.entrer(); });' in SOURCE
    assert 'if(recall("hud") === "1"){ Hud.entrer(true); } else { open(false); }' in SOURCE
    assert "else { Hud.sortir(); }" in SOURCE
    # Un seul accueil par ouverture.
    assert "if(!forcerComplet && state.salueCetteOuverture){ return; }" in SOURCE


def test_style_jarvis_reserve_au_plein_ecran():
    """Choix de Laity (26/09/2026): la petite fenetre garde le style
    ClimatSen d'origine; le noir/cyan J.A.R.V.I.S ne vaut qu'en plein ecran."""
    debut = SOURCE.index("INTERFACE J.A.R.V.I.S -- reprise de JARVIS-pro")
    bloc = SOURCE[debut:SOURCE.index("/* ---------- Mode J.A.R.V.I.S plein ecran")]
    assert ':root, html[data-dark="true"], html[data-dark="false"]{' not in bloc
    assert "body.hud{" in bloc
    for ligne in bloc.splitlines():
        if ligne.startswith("  ") and "{" in ligne and not ligne.startswith("   "):
            sel = ligne.strip()
            assert sel.startswith(("body.hud", "#hud-btn")), sel
    # Dans la petite fenetre, l'accueil reprend la carte d'origine.
    assert "if(intro && intro.parentNode){ accueilDansIntro(state.admin); }" in SOURCE
