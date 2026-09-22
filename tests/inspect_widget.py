#!/usr/bin/env python3
"""Inspection du widget Jarvis dans un vrai navigateur (Playwright).

Ouvre le dashboard, attend son rendu, puis rapporte ce qui est REELLEMENT
affiche : l iframe du composant existe-t-elle, ou est-elle placee, quelle est
sa taille, la bulle est-elle cliquable, et que dit la console du navigateur.

Usage :
    py -3 tests/inspect_widget.py [url] [--capture chemin.png] [--ouvrir]

    --ouvrir  clique sur la bulle et mesure le panneau deployé.

Sortie : un rapport lisible, plus un code de sortie non nul si la bulle est
introuvable ou invisible.
"""
import sys
import time
from pathlib import Path

URL = "http://localhost:8501"
LARGEUR, HAUTEUR = 1361, 680


def principal():
    args = sys.argv[1:]
    url = next((a for a in args if a.startswith("http")), URL)
    capture = None
    if "--capture" in args:
        capture = args[args.index("--capture") + 1]
    ouvrir = "--ouvrir" in args

    from playwright.sync_api import sync_playwright

    messages = []
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch()
        page = navigateur.new_page(viewport={"width": LARGEUR, "height": HAUTEUR})
        page.on("console", lambda m: messages.append((m.type, m.text)))
        page.on("pageerror", lambda e: messages.append(("pageerror", str(e))))

        print("Ouverture de %s ..." % url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # Streamlit n execute le script qu une fois la WebSocket etablie, et le
        # composant est le DERNIER element rendu : sur un dashboard lourd, cela
        # peut prendre des dizaines de secondes. On attend donc l apparition de
        # l iframe plutot qu une duree fixe -- une attente trop courte donnait
        # un faux negatif "aucune iframe".
        limite = time.time() + 90
        vue_jarvis = False
        while time.time() < limite:
            vue_jarvis = page.evaluate("""() => Array.from(
                document.querySelectorAll('iframe')).some(
                f => (f.srcdoc || '').indexOf('Jarvis CLIMAT-SEN') !== -1)""")
            if vue_jarvis:
                break
            time.sleep(1.5)
        attente = round(90 - (limite - time.time()), 1)
        print("  iframe Jarvis %s apres %.1f s"
              % ("detectee" if vue_jarvis else "toujours absente", attente))
        time.sleep(2)   # laisser le script du widget s executer

        print("\n=== IFRAMES PRESENTES DANS LA PAGE ===")
        iframes = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('iframe')).map((f, i) => {
                const r = f.getBoundingClientRect();
                const cs = getComputedStyle(f);
                return {
                    index: i,
                    title: f.title || '',
                    hauteurAttribut: f.getAttribute('height'),
                    position: cs.position,
                    display: cs.display,
                    visibility: cs.visibility,
                    zIndex: cs.zIndex,
                    rect: {x: Math.round(r.x), y: Math.round(r.y),
                           w: Math.round(r.width), h: Math.round(r.height)},
                    estJarvis: (f.srcdoc || '').indexOf('Jarvis CLIMAT-SEN') !== -1,
                };
            });
        }""")
        for f in iframes:
            marque = "  <-- JARVIS" if f["estJarvis"] else ""
            print("  [%d] %-12s attr height=%-5s %s  %dx%d a (%d,%d)  z=%s%s"
                  % (f["index"], f["title"], f["hauteurAttribut"], f["position"],
                     f["rect"]["w"], f["rect"]["h"], f["rect"]["x"], f["rect"]["y"],
                     f["zIndex"], marque))
        if not iframes:
            print("  aucune iframe dans la page")

        jarvis = next((f for f in iframes if f["estJarvis"]), None)

        print("\n=== CONSOLE DU NAVIGATEUR (lignes Jarvis) ===")
        lignes_jarvis = [t for (n, t) in messages if "[Jarvis]" in t]
        for t in lignes_jarvis:
            print("  " + t)
        if not lignes_jarvis:
            print("  aucune trace [Jarvis] : le script du widget ne s est pas execute")

        erreurs = [t for (n, t) in messages if n in ("error", "pageerror")
                   and "theme.sidebar" not in t]
        if erreurs:
            print("\n=== ERREURS JAVASCRIPT (hors theme Streamlit) ===")
            for t in erreurs[:10]:
                print("  " + t[:200])

        verdict = 0
        print("\n=== VERDICT ===")
        if jarvis is None:
            print("  ECHEC : aucune iframe Jarvis dans la page.")
            verdict = 1
        else:
            r = jarvis["rect"]
            visible = (r["w"] > 20 and r["h"] > 20
                       and jarvis["display"] != "none"
                       and jarvis["visibility"] != "hidden")
            print("  iframe Jarvis trouvee : %dx%d a (%d,%d), position %s"
                  % (r["w"], r["h"], r["x"], r["y"], jarvis["position"]))
            if not visible:
                print("  ECHEC : la bulle n a pas de surface affichable.")
                verdict = 1
            else:
                dans_ecran = (0 <= r["x"] < LARGEUR and 0 <= r["y"] < HAUTEUR)
                print("  visible a l ecran : %s" % ("oui" if dans_ecran else
                                                    "NON (hors du cadre)"))
                if not dans_ecran:
                    verdict = 1

        if ouvrir and jarvis is not None and verdict == 0:
            print("\n=== OUVERTURE DU PANNEAU ===")
            cadre = page.frames[[i for i, f in enumerate(page.frames)][0]]
            cible = None
            for f in page.frames:
                try:
                    if f.locator("#fab").count() > 0:
                        cible = f
                        break
                except Exception:
                    continue
            if cible is None:
                print("  bouton introuvable dans les iframes")
            else:
                cible.locator("#fab").click()
                time.sleep(1.2)
                apres = page.evaluate("""() => {
                    const f = Array.from(document.querySelectorAll('iframe'))
                        .find(x => (x.srcdoc || '').indexOf('Jarvis CLIMAT-SEN') !== -1);
                    const r = f.getBoundingClientRect();
                    return {w: Math.round(r.width), h: Math.round(r.height),
                            x: Math.round(r.x), y: Math.round(r.y)};
                }""")
                print("  panneau ouvert : %dx%d a (%d,%d)  -> %d%% de la hauteur de page"
                      % (apres["w"], apres["h"], apres["x"], apres["y"],
                         round(apres["h"] / HAUTEUR * 100)))

        if capture:
            Path(capture).parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=capture)
            print("\nCapture enregistree : %s" % capture)

        navigateur.close()

    return verdict


if __name__ == "__main__":
    sys.exit(principal())
