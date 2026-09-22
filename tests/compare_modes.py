#!/usr/bin/env python3
"""Compare les deux modes d'affichage du widget Jarvis dans un vrai navigateur.

Mesure, avant puis apres ouverture du panneau :
  - la largeur du bloc principal du dashboard
  - la largeur reelle des graphiques Plotly (leur canvas SVG)
  - le recouvrement eventuel entre le panneau et le contenu

Le point a trancher : en mode "pousse", les graphiques Plotly se
redimensionnent-ils vraiment quand le conteneur retrecit, ou restent-ils a leur
ancienne largeur et se retrouvent-ils rognes ? Un graphique tronque serait pire
qu un panneau qui recouvre.

Usage : py -3 tests/compare_modes.py <url> <etiquette> [--capture prefixe]
"""
import sys
import time
from pathlib import Path

LARGEUR, HAUTEUR = 1361, 680

MESURE = """() => {
    const bloc = document.querySelector(
        '[data-testid="stMainBlockContainer"],[data-testid="stAppViewBlockContainer"],.block-container');
    const graphes = Array.from(document.querySelectorAll('.js-plotly-plot')).map(g => {
        const r = g.getBoundingClientRect();
        const svg = g.querySelector('svg.main-svg');
        return {
            largeurVisible: Math.round(r.width),
            droite: Math.round(r.right),
            largeurSvg: svg ? Math.round(svg.getBoundingClientRect().width) : null,
        };
    });
    const jarvis = Array.from(document.querySelectorAll('iframe'))
        .find(f => (f.srcdoc || '').indexOf('Jarvis CLIMAT-SEN') !== -1);
    const rj = jarvis ? jarvis.getBoundingClientRect() : null;
    const rb = bloc ? bloc.getBoundingClientRect() : null;
    return {
        bloc: rb ? {largeur: Math.round(rb.width), droite: Math.round(rb.right),
                    paddingDroit: getComputedStyle(bloc).paddingRight} : null,
        graphes: graphes,
        panneau: rj ? {x: Math.round(rj.x), y: Math.round(rj.y),
                       w: Math.round(rj.width), h: Math.round(rj.height)} : null,
    };
}"""


def afficher(titre, m):
    print("  --- %s ---" % titre)
    if m["bloc"]:
        print("    bloc principal : largeur %d px, bord droit a %d, padding-right %s"
              % (m["bloc"]["largeur"], m["bloc"]["droite"], m["bloc"]["paddingDroit"]))
    if m["panneau"]:
        p = m["panneau"]
        print("    panneau Jarvis : %dx%d, bord gauche a %d" % (p["w"], p["h"], p["x"]))
    for i, g in enumerate(m["graphes"][:4]):
        print("    graphique %d    : visible %d px, svg %s px, bord droit %d"
              % (i, g["largeurVisible"], g["largeurSvg"], g["droite"]))


def principal():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
    etiquette = sys.argv[2] if len(sys.argv) > 2 else "mode"
    prefixe = None
    if "--capture" in sys.argv:
        prefixe = sys.argv[sys.argv.index("--capture") + 1]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page(viewport={"width": LARGEUR, "height": HAUTEUR})
        print("=== %s : %s ===" % (etiquette.upper(), url))
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        limite = time.time() + 90
        while time.time() < limite:
            pret = page.evaluate("""() => Array.from(document.querySelectorAll('iframe'))
                .some(f => (f.srcdoc || '').indexOf('Jarvis CLIMAT-SEN') !== -1)
                && document.querySelectorAll('.js-plotly-plot').length > 0""")
            if pret:
                break
            time.sleep(1.5)
        time.sleep(3)

        avant = page.evaluate(MESURE)
        afficher("panneau ferme", avant)
        if prefixe:
            page.screenshot(path=prefixe + "_ferme.png")

        cadre = None
        for f in page.frames:
            try:
                if f.locator("#fab").count() > 0:
                    cadre = f
                    break
            except Exception:
                continue
        if cadre is None:
            print("  bouton de la bulle introuvable")
            nav.close()
            return 1

        cadre.locator("#fab").click()
        time.sleep(2.5)          # transition + reflow eventuel de Plotly
        apres = page.evaluate(MESURE)
        afficher("panneau ouvert", apres)
        if prefixe:
            page.screenshot(path=prefixe + "_ouvert.png")

        print("  --- verdict ---")
        if apres["panneau"] and apres["graphes"]:
            # On compare le bord droit du CONTENU reel, pas celui du bloc :
            # le bord du bloc inclut son padding, c est-a-dire justement
            # l espace vide que le mode "pousse" vient de creer. Mesurer le
            # bloc donnait un faux "recouvrement".
            bord_contenu = max((g["droite"] for g in apres["graphes"]
                                if g["largeurVisible"] > 0), default=0)
            chevauche = bord_contenu > apres["panneau"]["x"]
            print("    contenu le plus a droite : %d px | panneau a partir de %d px"
                  % (bord_contenu, apres["panneau"]["x"]))
            print("    recouvrement du contenu : %s"
                  % ("OUI, le panneau masque du contenu" if chevauche
                     else "NON, le contenu a ete decale"))
        if avant["graphes"] and apres["graphes"]:
            a = avant["graphes"][0]
            b = apres["graphes"][0]
            if a["largeurVisible"] == b["largeurVisible"]:
                print("    graphiques : largeur inchangee (%d px)" % b["largeurVisible"])
            else:
                print("    graphiques : %d -> %d px (redimensionnes)"
                      % (a["largeurVisible"], b["largeurVisible"]))
            if b["largeurSvg"] and abs(b["largeurSvg"] - b["largeurVisible"]) > 8:
                print("    ALERTE : le SVG fait %d px pour un conteneur de %d px "
                      "-> graphique ROGNE" % (b["largeurSvg"], b["largeurVisible"]))
            else:
                print("    le SVG suit son conteneur : pas de rognage")
        nav.close()
    return 0


if __name__ == "__main__":
    sys.exit(principal())
