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


def test_la_bulle_ouvre_le_plein_ecran_directement():
    """Choix de Laity (27/09/2026): la bulle ouvre directement le plein ecran
    J.A.R.V.I.S; il s'y rouvre apres une reexecution Streamlit, et Echap,
    une fois ecrans et panneaux refermes, ferme Jarvis."""
    fab = SOURCE[SOURCE.index('fab.addEventListener("click"'):]
    fab = fab[:fab.index("});") + 3]
    assert "Hud.entrer()" in fab
    remontage = SOURCE[SOURCE.index('if(recall("open") === "1"){'):]
    remontage = remontage[:300]
    assert "Hud.entrer(true);" in remontage
    # La miniature n'existe que pendant une analyse : jamais restauree (28/09/2026).
    assert "Analyse.colonne(true)" not in remontage
    echap = SOURCE[SOURCE.index('if(e.key !== "Escape"){ return; }'):]
    echap = echap[:echap.index("});")]
    lignes = [l.strip() for l in echap.splitlines()]
    soutenance = lignes.index("else if(Soutenance.visible()){ Soutenance.quitter(); }")
    assert lignes[soutenance + 1] == "else { shut(); }"


def test_accueil_plein_ecran_par_tuiles():
    """A l'ouverture, quatre tuiles autour de l'orbe disent ce que Jarvis sait
    faire et lancent un exemple; elles s'effacent a la premiere question et
    ne masquent jamais une carte, un briefing, le menu ou la transcription."""
    bloc = SOURCE[SOURCE.index('<div id="hud-accueil" hidden>'):]
    fin = bloc.index("</button>", bloc.index('data-action="briefing"'))
    bloc = bloc[:fin]
    tuiles = bloc.count('class="ha-tuile"')
    assert tuiles == 4
    assert bloc.count("data-q=") == 3 and 'data-action="briefing"' in bloc
    for titre in ("COMPRENDRE", "VOIR", "ANTICIPER", "PR&Eacute;SENTER"):
        assert titre in bloc
    # Affichees a l'entree seulement si aucune question n'a ete posee.
    assert 'accueil(!log.querySelector(".msg.user"));' in SOURCE
    # Effacees par toute question, qu'elle vienne d'une tuile ou non.
    ask = SOURCE[SOURCE.index("function ask(text){"):][:200]
    assert "Hud.accueil(false)" in ask
    for etat in ("hud-ecran", "hud-transcription", "hud-menu-ouvert", "soutenance", "hud-boot"):
        assert "body.hud.%s #hud-accueil" % etat in SOURCE
    # Style limite au plein ecran: la petite fenetre n'est pas touchee.
    css = SOURCE[SOURCE.index("<style>"):SOURCE.index("</style>")]
    style = [l.strip() for l in css.splitlines() if "#hud-accueil" in l and "{" in l]
    assert style and all(l.startswith(("body.hud", "@media")) for l in style), style


def test_fond_d_ecran_du_hud():
    """Planisphere en points genere par scripts/23 (27/09/2026): present,
    autonome (aucune ressource externe), sous l'orbe, sans animation pour
    qui demande moins de mouvement."""
    debut = SOURCE.index("<!-- FOND_HUD:DEBUT -->")
    fond = SOURCE[debut:SOURCE.index("<!-- FOND_HUD:FIN -->")]
    assert '<svg id="hud-fond"' in fond and 'aria-hidden="true"' in fond
    assert fond.count('class="hf-balise"') == 9 and "S&#201;N&#201;GAL" in fond
    assert len(fond) > 15000                      # le trait des cotes est bien la
    assert "http" not in fond and "href" not in fond
    # Avant l'orbe dans le DOM: il est peint dessous.
    assert debut < SOURCE.index('<canvas id="hud-orbe"')
    css = SOURCE[SOURCE.index("<style>"):SOURCE.index("</style>")]
    assert "@media (prefers-reduced-motion:reduce)" in css
    assert "body.hud.hud-accueil-visible #hud-fond text{opacity:0}" in css


def test_analyse_de_page_visible():
    """Demande de Laity (27/09/2026): quand Jarvis analyse la page, on voit ce
    qu'il analyse. J.A.R.V.I.S en miniature (la page reste visible), cadres
    numerotes sur les graphiques lus, retires a la question suivante."""
    assert "var Analyse = (function(){" in SOURCE
    # la capture retient les elements reellement lus, puis les encadre
    assert "Analyse.retenir(graphes, kpisLus);" in SOURCE
    joindre = SOURCE[SOURCE.index("function joindreVue(body, text){"):]
    joindre = joindre[:joindre.index("function typing(")]
    assert "Analyse.debut();" in joindre
    # l'interface J.A.R.V.I.S reste, en miniature ; bouton pour revenir au plein ecran
    debut = SOURCE[SOURCE.index("    function debut(){"):]
    debut = debut[:debut.index("    function repos(){")]
    assert "if(!Hud.actif()){ Hud.entrer(true); }" in debut and "Hud.sortir()" not in debut
    assert 'id="analyse-agrandir"' in SOURCE and "body.hud.analyse #hud{" in SOURCE
    assert "premier.scrollIntoView(" in debut
    entrer = SOURCE[SOURCE.index("function entrer(sansDemarrage){"):]
    assert entrer[:200].count("Analyse.fin();") == 1
    # cadres: elements ajoutes au body de l'hote, sans evenements souris,
    # sous l'iframe (z-index 2147483000)
    assert "pointer-events:none;z-index:2147482000" in SOURCE
    # nouvelle question : cadres effaces, colonne gardee ; fermeture : tout retire
    assert "Analyse.fin(true);" in SOURCE
    shut = SOURCE[SOURCE.index("  function shut(){"):]
    assert "Analyse.fin();" in shut[:120]
    # cadrer() place la colonne avant le plein ecran
    cadrer = SOURCE[SOURCE.index("  function cadrer(){"):]
    cadrer = cadrer[:cadrer.index("  function setHeight(")]
    assert cadrer.index('classList.contains("analyse")') < cadrer.index("if(pleinEcranVoulu()){")
