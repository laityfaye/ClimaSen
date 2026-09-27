#!/usr/bin/env python3
"""Fond d'ecran de l'interface J.A.R.V.I.S: planisphere en points, graticule,
balises des indices oceaniques et Senegal.

Genere un SVG compact a partir du fond Natural Earth deja embarque
(jarvis/cartes/fond_carte.json.gz, construit par le script 16) et l'insere
dans jarvis/widget/widget.html entre les marqueurs FOND_HUD. Aucun fichier
externe, aucune requete: le widget reste autonome.

Usage: py -3 scripts/23_build_jarvis_fond_hud.py
"""
import gzip
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
FOND = RACINE / "jarvis" / "cartes" / "fond_carte.json.gz"
WIDGET = RACINE / "jarvis" / "widget" / "widget.html"
DEBUT, FIN = "<!-- FOND_HUD:DEBUT -->", "<!-- FOND_HUD:FIN -->"

LAT_MIN, LAT_MAX = -60, 80          # l'Antarctique n'apporte rien au decor
TOLERANCE = 0.35                     # simplification (degres)
SURFACE_MIN = 1.5                    # ilots plus petits ignores (degres carres)

# Centres des boites d'indices (lon, lat) et libelles (ASCII + entites).
BALISES = [
    ("NI&#209;O 3.4", -145, 0), ("NI&#209;O 1+2", -85, -5), ("NI&#209;O 4", 170, 0),
    ("TNA", -35, 14), ("TSA", -10, -10), ("ATL3", -10, 0), ("AMO", -40, 40),
    ("IOD-O", 60, 0), ("IOD-E", 100, -5),
]
SENEGAL = (-14.5, 14.4)


def _dp(points, tol):
    """Douglas-Peucker (iteratif)."""
    if len(points) < 3:
        return points
    garde = [False] * len(points)
    garde[0] = garde[-1] = True
    pile = [(0, len(points) - 1)]
    while pile:
        a, b = pile.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        n = (dx * dx + dy * dy) ** 0.5 or 1e-9
        loin, idx = 0.0, None
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / n
            if d > loin:
                loin, idx = d, i
        if idx is not None and loin > tol:
            garde[idx] = True
            pile += [(a, idx), (idx, b)]
    return [p for p, g in zip(points, garde) if g]


def _surface(points):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2)
                   in zip(points, points[1:] + points[:1]))) / 2


def _chemin(anneaux):
    morceaux = []
    for anneau in anneaux:
        pts = [(round(x, 1), round(-y, 1)) for x, y in anneau]      # y vers le bas
        if max(-y for _, y in pts) < LAT_MIN or _surface(pts) < SURFACE_MIN:
            continue
        # Anneau ferme (premier point = dernier): Douglas-Peucker n'a pas de
        # segment de reference. On le coupe en deux moities.
        if pts[0] == pts[-1]:
            pts = pts[:-1]
        h = len(pts) // 2
        pts = _dp(pts[:h + 1], TOLERANCE) + _dp(pts[h:] + [pts[0]], TOLERANCE)[1:-1]
        if len(pts) < 4:
            continue
        def f(v):
            return ("%g" % v)
        tete = "M%s %s" % (f(pts[0][0]), f(pts[0][1]))
        corps = "L" + " ".join("%s %s" % (f(x), f(y)) for x, y in pts[1:])
        morceaux.append(tete + corps + "Z")
    return "".join(morceaux)


def svg():
    fond = json.load(gzip.open(FOND, "rt", encoding="utf-8"))
    terres = _chemin(fond["terres"])
    haut, bas = -LAT_MAX, -LAT_MIN
    graticule = "".join("M%d %d V%d" % (lon, haut, bas) for lon in range(-150, 181, 30)) + \
        "".join("M-180 %d H180" % -lat for lat in range(-60, 81, 30))
    balises = []
    for k, (nom, lon, lat) in enumerate(BALISES):
        retard = "%.1fs" % (k * 0.55)
        balises.append(
            '<g class="hf-balise" transform="translate(%g %g)">'
            '<circle class="hf-onde" r="1.2" style="animation-delay:%s"/>'
            '<circle class="hf-point" r=".75"/>'
            # Pres du bord droit, l'etiquette passe a gauche du point.
            '%s</g>' % (lon, -lat, retard,
                        ('<text x="-2.2" y="-1.6" text-anchor="end">%s</text>' if lon > 140
                         else '<text x="2.2" y="-1.6">%s</text>') % nom))
    sx, sy = SENEGAL
    return (
        '<svg id="hud-fond" viewBox="-180 %d 360 %d" preserveAspectRatio="xMidYMid meet" '
        'aria-hidden="true" focusable="false">'
        '<defs>'
        '<pattern id="hf-points" width="1.5" height="1.5" patternUnits="userSpaceOnUse">'
        '<circle cx=".75" cy=".75" r=".34"/></pattern>'
        '<linearGradient id="hf-balayage" x1="0" x2="1" y1="0" y2="0">'
        '<stop offset="0" stop-color="#00E5FF" stop-opacity="0"/>'
        '<stop offset=".85" stop-color="#00E5FF" stop-opacity=".07"/>'
        '<stop offset="1" stop-color="#00E5FF" stop-opacity=".13"/></linearGradient>'
        '</defs>'
        '<path class="hf-graticule" d="%s"/>'
        '<path class="hf-terres" d="%s"/>'
        '<rect class="hf-balayage" x="-200" y="%d" width="40" height="%d"/>'
        '%s'
        '<g class="hf-senegal" transform="translate(%g %g)">'
        '<circle class="hf-onde" r="1.6"/><circle class="hf-point" r="1"/>'
        '<text x="2.6" y="3.8">S&#201;N&#201;GAL</text></g>'
        '</svg>' % (haut, bas - haut, graticule, terres, haut, bas - haut,
                    "".join(balises), sx, -sy))


def main():
    with open(WIDGET, encoding="utf-8", newline="") as f:   # garder les fins de ligne
        contenu = f.read()
    nl = "\r\n" if "\r\n" in contenu else "\n"
    i, j = contenu.index(DEBUT), contenu.index(FIN)
    bloc = svg()
    contenu = contenu[:i] + DEBUT + nl + "  " + bloc + nl + "  " + contenu[j:]
    WIDGET.write_bytes(contenu.encode("utf-8"))
    print("Fond HUD insere: %.1f Ko" % (len(bloc) / 1024))


if __name__ == "__main__":
    main()
