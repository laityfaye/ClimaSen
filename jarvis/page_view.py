"""Vue du dashboard jointe a une question (Phase 9).

Quand l'utilisateur demande d'interpreter ce qu'il voit, le widget capture la
page ouverte: son titre, ses indicateurs cles, et pour chaque graphique Plotly
son titre, un RESUME de ses donnees (lu dans l'objet Plotly lui-meme) et son
IMAGE (Plotly.toImage). Claude recoit les deux: l'image pour ce que voit
l'utilisateur (echelles, couleurs, ce qui saute aux yeux), les donnees pour
les chiffres exacts. Il peut ainsi signaler un affichage trompeur, ce qu'une
image seule ou des donnees seules ne permettraient pas.

Comme le contexte de page, la vue vient du navigateur: donnee non fiable.
  - Tailles bornees par le schema (Pydantic), images comprises.
  - Images: PNG uniquement, verifie sur les octets (signature et en-tete
    IHDR), dimensions plafonnees. Un "PNG" qui n'en est pas un est ecarte.
  - Le texte est balise <vue_dashboard>; le prompt systeme dit que ce bloc
    decrit un ecran et ne contient jamais de consigne.
  - Rien de tout cela n'entre dans l'historique.
"""
import base64
import binascii
import struct
from typing import List, Optional

from pydantic import BaseModel, Field

MAX_GRAPHIQUES = 4
MAX_IMAGES = 3
MAX_IMAGE_B64 = 400_000          # ~300 Ko de PNG
MAX_COTE_PX = 2000
MAX_RESUME_CHARS = 6000

PREFIXE_DATA = "data:image/png;base64,"
SIGNATURE_PNG = b"\x89PNG\r\n\x1a\n"


class Indicateur(BaseModel):
    libelle: str = Field(max_length=80)
    valeur: str = Field(max_length=40)


class Graphique(BaseModel):
    titre: str = Field(default="", max_length=200)
    sous_titre: str = Field(default="", max_length=300)
    resume: str = Field(default="", max_length=MAX_RESUME_CHARS)
    image: Optional[str] = Field(default=None,
                                 max_length=MAX_IMAGE_B64 + len(PREFIXE_DATA))


class VueDashboard(BaseModel):
    page_titre: str = Field(default="", max_length=200)
    indicateurs: List[Indicateur] = Field(default_factory=list, max_length=12)
    graphiques: List[Graphique] = Field(default_factory=list,
                                        max_length=MAX_GRAPHIQUES)


def png_valide(image: Optional[str]):
    """Base64 du PNG si l'image en est vraiment un, de taille raisonnable.

    Retourne None sinon: une image douteuse est ignoree, jamais bloquante.
    """
    if not image:
        return None
    donnees = image[len(PREFIXE_DATA):] if image.startswith(PREFIXE_DATA) else image
    try:
        octets = base64.b64decode(donnees, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(octets) < 33 or not octets.startswith(SIGNATURE_PNG):
        return None
    # Premier bloc d'un PNG: IHDR, largeur et hauteur sur 4 octets chacune.
    if octets[12:16] != b"IHDR":
        return None
    largeur, hauteur = struct.unpack(">II", octets[16:24])
    if not (0 < largeur <= MAX_COTE_PX and 0 < hauteur <= MAX_COTE_PX):
        return None
    return donnees


def _neutre(texte: str) -> str:
    """Chevrons neutralises: un titre contenant '</vue_dashboard>' ne doit
    pas pouvoir clore le bloc et se faire passer pour autre chose (Phase 12)."""
    return texte.replace("<", "\u2039").replace(">", "\u203a")


def _texte(vue: VueDashboard) -> str:
    lignes = ["<vue_dashboard>"]
    if vue.page_titre:
        lignes.append("Page : %s" % _neutre(vue.page_titre))
    if vue.indicateurs:
        lignes.append("Indicateurs affiches :")
        for ind in vue.indicateurs:
            lignes.append("- %s : %s" % (_neutre(ind.libelle), _neutre(ind.valeur)))
    for rang, g in enumerate(vue.graphiques, 1):
        titre = _neutre(g.titre) or "(sans titre)"
        lignes.append("Graphique %d : %s" % (rang, titre))
        if g.sous_titre:
            lignes.append("  %s" % _neutre(g.sous_titre))
        if g.resume:
            lignes.append("  Donnees tracees : %s" % _neutre(g.resume))
    lignes.append("</vue_dashboard>")
    return "\n".join(lignes)


def blocs(vue: Optional[VueDashboard]) -> list:
    """Blocs de contenu a placer avant la question: texte, puis images.

    Chaque image est precedee d'un court libelle pour que le modele sache
    a quel graphique elle correspond.
    """
    if vue is None or not (vue.page_titre or vue.indicateurs or vue.graphiques):
        return []
    contenu = [{"type": "text", "text": _texte(vue)}]
    images = 0
    for rang, g in enumerate(vue.graphiques, 1):
        if images >= MAX_IMAGES:
            break
        donnees = png_valide(g.image)
        if donnees is None:
            continue
        contenu.append({"type": "text",
                        "text": "Image du graphique %d (%s) :"
                                % (rang, _neutre(g.titre) or "sans titre")})
        contenu.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": donnees}})
        images += 1
    return contenu


def resume_journal(vue: Optional[VueDashboard]) -> Optional[dict]:
    """Ce que l'on journalise d'une vue: des comptes, jamais le contenu."""
    if vue is None:
        return None
    return {"graphiques": len(vue.graphiques),
            "images": sum(1 for g in vue.graphiques if png_valide(g.image)),
            "indicateurs": len(vue.indicateurs)}
