#!/usr/bin/env python3
"""Verifie le rendu Markdown de la console admin, dans un vrai navigateur.

Outil autonome, hors de la suite pytest: il demande Playwright, que la suite
n'exige pas (comme tests/inspect_widget.py).

    py -3 tests/verifier_rendu_admin.py

Deux choses sont verifiees:
  - les formes autorisees par le prompt admin (titres, listes, tableaux,
    blocs de code) sont bien rendues, et non affichees en Markdown brut;
  - le HTML present dans la reponse du modele est ECHAPPE. C'est le point
    sensible: un rendu naif transformerait une reponse en injection.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RACINE = Path(__file__).resolve().parent.parent

ECHANTILLON = """## Matam - 239 evenements

| Phase | n |
|---|---|
| Phase_2_pleine | 119 |
| Phase_3_fin | 95 |

Deux criteres **conjoints** (Memoire, ch. `2.2.2`) :

- critere d intensite : z > +2 sigma
- critere d extension spatiale

1. premier
2. second

```
bloc litteral
```

Texte avec <b>balise</b> & esperluette.
"""

CONTROLES = [
    ("titre rendu",            lambda h: "<h2>" in h),
    ("tableau rendu",          lambda h: "<table>" in h and "<th>" in h),
    ("cellules du tableau",    lambda h: "<td>119</td>" in h),
    ("liste a puces",          lambda h: "<ul>" in h and "<li>" in h),
    ("liste numerotee",        lambda h: "<ol>" in h),
    ("bloc de code",           lambda h: "<pre><code>" in h),
    ("gras",                   lambda h: "<b>conjoints</b>" in h),
    ("code en ligne",          lambda h: "<code>2.2.2</code>" in h),
    ("pas de Markdown brut",   lambda h: "|---|" not in h and "## Matam" not in h),
    ("balise du modele echappee", lambda h: "&lt;b&gt;balise&lt;/b&gt;" in h
                                            and "<b>balise</b>" not in h),
    ("esperluette echappee",   lambda h: "&amp;" in h),
]

INJECTIONS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "| <script>alert(2)</script> | x |\n|---|---|\n| a | b |",
    "## <script>alert(3)</script>",
    "- <img src=x onerror=alert(4)>",
]


def principal():
    from playwright.sync_api import sync_playwright

    html = (RACINE / "jarvis" / "admin" / "admin.html").read_text(encoding="utf-8")
    html = html.replace("__JARVIS_API_BASE__", "/jarvis")

    echecs = 0
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        page = nav.new_page()
        page.set_content(html)

        rendu = page.evaluate("(md) => window.__rendu(md)", ECHANTILLON)
        print("--- formes rendues ---")
        for nom, controle in CONTROLES:
            ok = controle(rendu)
            echecs += 0 if ok else 1
            print("  %-28s %s" % (nom, "ok" if ok else "ECHEC"))

        print("\n--- echappement ---")
        for charge in INJECTIONS:
            sortie = page.evaluate("(md) => window.__rendu(md)", charge)
            # Controle decisif: on injecte reellement le rendu dans un DOM et
            # on compte les elements executables produits.
            #
            # Chercher des sous-chaines dans le rendu ne vaut rien: "onerror="
            # subsiste legitimement en TEXTE apres echappement (seuls < > & et
            # les guillemets sont transformes), ce qui declenchait de fausses
            # alertes. Seul ce que le navigateur fabrique fait foi.
            bilan = page.evaluate("""(h) => {
                const d = document.createElement('div');
                d.innerHTML = h;
                return d.querySelectorAll('script,img,iframe,object,embed,svg,a[href^="javascript:"]').length
                     + d.querySelectorAll('*[onerror],*[onload],*[onclick]').length;
            }""", sortie)
            echecs += 1 if bilan else 0
            print("  %-45s %s" % (charge.split("\n")[0][:45],
                                  "ECHEC (%d element(s))" % bilan if bilan
                                  else "inerte"))
        nav.close()

    print("\n%s" % ("Tout est conforme." if echecs == 0
                    else "%d controle(s) en echec." % echecs))
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
