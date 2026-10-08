"""Genere les fichiers du logo de ClimatSen (symbole + logotype).

Le symbole est la goutte-grille : une goutte de pluie faite de pixels de la
grille CHIRPS (0,25 deg), dont un seul est ambre, celui ou la pluie depasse
+2 ecarts-types. Le texte est converti en traces : les SVG s'affichent a
l'identique sans les polices installees.

Usage (les polices ne sont pas versionnees, licence OFL, Google Fonts) :
    python assets/branding/generer_logo.py --polices <dossier>
avec dans <dossier> : SpaceGrotesk.ttf (variable, wght) et IBMPlexSans.ttf
(variable, wdth et wght), telechargees depuis github.com/google/fonts.
"""
import argparse
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image, ImageDraw

ICI = Path(__file__).resolve().parent

# --- couleurs (voir README.md) -------------------------------------------------
NUIT = "#1D1864"      # indigo nuit, couleur principale
PLUIE = "#0284C7"     # bleu pluie sur fond clair
PLUIE_D = "#38BDF8"   # bleu pluie sur fond sombre
EXT = "#D97706"       # ambre extreme sur fond clair
EXT_D = "#FBBF24"     # ambre extreme sur fond sombre
GRIS = "#5B6474"      # signature sur fond clair
BRUME = "#C7CBF0"     # signature sur fond sombre
ENCRE = "#0F172A"     # version une couleur

VARIANTES = {
    "clair": dict(goutte=PLUIE, extreme=EXT, nom=NUIT, sen=PLUIE, signature=GRIS),
    "nuit": dict(goutte=PLUIE_D, extreme=EXT_D, nom="#FFFFFF", sen=PLUIE_D, signature=BRUME),
    "mono": dict(goutte=ENCRE, extreme=ENCRE, nom=ENCRE, sen=ENCRE, signature=ENCRE),
    "blanc": dict(goutte="#FFFFFF", extreme="#FFFFFF", nom="#FFFFFF", sen="#FFFFFF", signature="#FFFFFF"),
}

# --- goutte-grille : 7 colonnes x 9 lignes, pas de 12, pixel de 10 ------------
GOUTTE = [(3, 3), (3, 3), (2, 4), (1, 5), (1, 5), (0, 6), (0, 6), (1, 5), (2, 4)]
EXTREME = (5, 4)                     # (ligne, colonne) du pixel ambre
PAS, PIXEL, ARRONDI = 12, 10, 1.5
LARGEUR_G, HAUTEUR_G = 7 * PAS - 2, 9 * PAS - 2     # 82 x 106

NOM_TAILLE = 0.62        # taille du nom, en hauteur de goutte
SIG_TAILLE = 0.17
NOM_APPROCHE = -0.03     # interlettrage, en em
SIG_APPROCHE = 0.08
ECART_SYMBOLE = 0.32     # entre goutte et texte
ECART_LIGNES = 0.16      # entre nom et signature
SIGNATURE = "PLUIES EXTRÊMES · SÉNÉGAL"


def pixels():
    for r, (a, b) in enumerate(GOUTTE):
        for c in range(a, b + 1):
            yield r, c, (r, c) == EXTREME


def goutte_svg(v, x=0.0, y=0.0, echelle=1.0):
    out = []
    for r, c, ext in pixels():
        px, py = x + c * PAS * echelle, y + r * PAS * echelle
        if ext and v["extreme"] == v["goutte"]:
            # Version une couleur : le pixel extreme reste visible, evide.
            t = 1.6 * echelle
            out.append('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="none" '
                       'stroke="%s" stroke-width="%g"/>' % (
                           round(px + t / 2, 2), round(py + t / 2, 2),
                           round(PIXEL * echelle - t, 2), round(PIXEL * echelle - t, 2),
                           round(ARRONDI * echelle, 2), v["goutte"], round(t, 2)))
            continue
        out.append('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s"/>' % (
            round(px, 2), round(py, 2),
            round(PIXEL * echelle, 2), round(PIXEL * echelle, 2), round(ARRONDI * echelle, 2),
            v["extreme"] if ext else v["goutte"]))
    return "".join(out)


class Police:
    def __init__(self, chemin, axes):
        f = TTFont(chemin)
        self.f = instancer.instantiateVariableFont(f, axes)
        self.upm = self.f["head"].unitsPerEm
        self.cmap = self.f.getBestCmap()
        self.glyphes = self.f.getGlyphSet()
        self.hmtx = self.f["hmtx"]
        self.cap = self.f["OS/2"].sCapHeight

    def trace(self, texte, taille, approche, x0=0.0, ligne=0.0):
        """Chemin SVG du texte, ligne de base en y=ligne. Renvoie (d, largeur)."""
        s = taille / self.upm
        x = x0
        morceaux = []
        for i, ch in enumerate(texte):
            nom = self.cmap[ord(ch)]
            pen = SVGPathPen(self.glyphes)
            self.glyphes[nom].draw(TransformPen(pen, (s, 0, 0, -s, x, ligne)))
            d = pen.getCommands()
            if d:
                morceaux.append(d)
            x += self.hmtx[nom][0] * s
            if i < len(texte) - 1:
                x += approche * taille
        return " ".join(morceaux), x - x0

    def hauteur_cap(self, taille):
        return self.cap * taille / self.upm


def arrondir(d):
    import re
    return re.sub(r"-?\d+\.\d+", lambda m: ("%.2f" % float(m.group())).rstrip("0").rstrip("."), d)


def logo_horizontal(grotesk, plex, v, avec_signature=True):
    h = HAUTEUR_G
    tn, ts = NOM_TAILLE * h, SIG_TAILLE * h
    x_txt = LARGEUR_G + ECART_SYMBOLE * h
    cap_n, cap_s = grotesk.hauteur_cap(tn), plex.hauteur_cap(ts)
    bloc = cap_n + (ECART_LIGNES * h + cap_s if avec_signature else 0)
    y_nom = (h - bloc) / 2 + cap_n
    d1, l1 = grotesk.trace("Climat", tn, NOM_APPROCHE, x_txt, y_nom)
    d2, l2 = grotesk.trace("Sen", tn, NOM_APPROCHE, x_txt + l1 + NOM_APPROCHE * tn, y_nom)
    parties = [goutte_svg(v),
               '<path fill="%s" d="%s"/>' % (v["nom"], arrondir(d1)),
               '<path fill="%s" d="%s"/>' % (v["sen"], arrondir(d2))]
    largeur = x_txt + l1 + NOM_APPROCHE * tn + l2
    if avec_signature:
        d3, l3 = plex.trace(SIGNATURE, ts, SIG_APPROCHE, x_txt, y_nom + ECART_LIGNES * h + cap_s)
        parties.append('<path fill="%s" d="%s"/>' % (v["signature"], arrondir(d3)))
        largeur = max(largeur, x_txt + l3)
    return parties, largeur, h


def logo_vertical(grotesk, plex, v):
    h = HAUTEUR_G
    tn, ts = 0.48 * h, 0.13 * h
    _, l1 = grotesk.trace("Climat", tn, NOM_APPROCHE)
    _, l2 = grotesk.trace("Sen", tn, NOM_APPROCHE)
    _, l3 = plex.trace(SIGNATURE, ts, SIG_APPROCHE)
    ln = l1 + NOM_APPROCHE * tn + l2
    largeur = max(ln, l3, LARGEUR_G)
    y_nom = h + 0.22 * h + grotesk.hauteur_cap(tn)
    y_sig = y_nom + 0.18 * h + plex.hauteur_cap(ts)
    x_n = (largeur - ln) / 2
    d1, _ = grotesk.trace("Climat", tn, NOM_APPROCHE, x_n, y_nom)
    d2, _ = grotesk.trace("Sen", tn, NOM_APPROCHE, x_n + l1 + NOM_APPROCHE * tn, y_nom)
    d3, _ = plex.trace(SIGNATURE, ts, SIG_APPROCHE, (largeur - l3) / 2, y_sig)
    parties = [goutte_svg(v, (largeur - LARGEUR_G) / 2, 0),
               '<path fill="%s" d="%s"/>' % (v["nom"], arrondir(d1)),
               '<path fill="%s" d="%s"/>' % (v["sen"], arrondir(d2)),
               '<path fill="%s" d="%s"/>' % (v["signature"], arrondir(d3))]
    return parties, largeur, y_sig + 0.04 * h


def svg(parties, largeur, hauteur, titre, marge=0.0, fond=None):
    w, h = largeur + 2 * marge, hauteur + 2 * marge
    corps = "".join(parties)
    if marge:
        corps = '<g transform="translate(%g %g)">%s</g>' % (marge, marge, corps)
    if fond:
        corps = '<rect width="%g" height="%g" rx="%g" fill="%s"/>' % (
            round(w, 2), round(h, 2), round(min(w, h) * 0.22, 2), fond) + corps
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" role="img" aria-label="%s">'
            '<title>%s</title>%s</svg>\n' % (round(w, 2), round(h, 2), titre, titre, corps))


def icone_png(chemin, taille):
    """Favicon : goutte nuit sur tuile indigo, dessinee pixel par pixel."""
    sur = 8                                   # sur-echantillonnage, puis reduction
    T = taille * sur
    img = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, T - 1, T - 1], radius=round(T * 0.22), fill=NUIT)
    zone = T * 0.70
    e = zone / HAUTEUR_G
    x0 = (T - LARGEUR_G * e) / 2
    y0 = (T - HAUTEUR_G * e) / 2
    for r, c, ext in pixels():
        x, y = x0 + c * PAS * e, y0 + r * PAS * e
        d.rounded_rectangle([x, y, x + PIXEL * e, y + PIXEL * e], radius=ARRONDI * e,
                            fill=EXT_D if ext else PLUIE_D)
    img.resize((taille, taille), Image.LANCZOS).save(chemin)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--polices", required=True, type=Path)
    a = ap.parse_args()
    grotesk = Police(a.polices / "SpaceGrotesk.ttf", {"wght": 700})
    plex = Police(a.polices / "IBMPlexSans.ttf", {"wght": 500, "wdth": 100})

    nom = "ClimatSen"
    fichiers = {}
    for var in ("clair", "nuit", "mono", "blanc"):
        v = VARIANTES[var]
        suffixe = "" if var == "clair" else "-" + var
        fichiers["symbole%s.svg" % suffixe] = svg([goutte_svg(v)], LARGEUR_G, HAUTEUR_G, nom)
        p, w, h = logo_horizontal(grotesk, plex, v)
        fichiers["logo-horizontal%s.svg" % suffixe] = svg(p, w, h, nom + ", pluies extrêmes au Sénégal")
        p, w, h = logo_horizontal(grotesk, plex, v, avec_signature=False)
        fichiers["logo-court%s.svg" % suffixe] = svg(p, w, h, nom)
        if var in ("clair", "nuit"):
            p, w, h = logo_vertical(grotesk, plex, v)
            fichiers["logo-vertical%s.svg" % suffixe] = svg(p, w, h, nom + ", pluies extrêmes au Sénégal")
    # Favicon : tuile carree indigo, goutte sur 70 % de la hauteur (comme les PNG).
    T = HAUTEUR_G / 0.70
    fichiers["favicon.svg"] = svg(
        ['<rect width="%g" height="%g" rx="%g" fill="%s"/>' % (round(T, 2), round(T, 2), round(T * 0.22, 2), NUIT),
         goutte_svg(VARIANTES["nuit"], (T - LARGEUR_G) / 2, (T - HAUTEUR_G) / 2)],
        T, T, nom)
    for n, contenu in fichiers.items():
        (ICI / n).write_text(contenu, encoding="utf-8")
    for t in (32, 180, 512):
        icone_png(ICI / ("favicon-%d.png" % t), t)
    print("%d SVG, 3 PNG dans %s" % (len(fichiers), ICI))


if __name__ == "__main__":
    main()
