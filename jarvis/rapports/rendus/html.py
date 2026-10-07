"""Rendu HTML d'un Rapport (Jinja2, echappement automatique).

Page autonome: styles et images en ligne, aucune ressource externe. C'est
aussi la source du PDF (rendus/pdf.py), d'ou la feuille de style d'impression
(@page A4).
"""
import base64
from functools import lru_cache
from pathlib import Path

from ..document import Encadre, Figure, LIBELLES_ORIGINE, Liste, Paragraphe, Tableau
from ..faits import LIBELLES_STATUT

GABARITS = Path(__file__).resolve().parent.parent / "gabarits"


@lru_cache(maxsize=1)
def _environnement():
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    return Environment(loader=FileSystemLoader(str(GABARITS)),
                       autoescape=select_autoescape(["html", "j2"]),
                       trim_blocks=True, lstrip_blocks=True)


def empreintes(rapport) -> set:
    """Textes qui identifient chaque bloc (comparaison entre deux versions)."""
    vus = set()
    for s in rapport.dans_l_ordre():
        for b in s.blocs:
            if isinstance(b, Paragraphe):
                vus.add(b.texte)
            elif isinstance(b, Liste):
                vus.update(b.elements)
            elif isinstance(b, Encadre):
                vus.add(b.texte)
            elif isinstance(b, (Figure, Tableau)):
                vus.add("visuel:" + b.titre)
    return vus


def _bloc(b, modifies=None):
    neuf = modifies is not None
    if isinstance(b, Paragraphe):
        return {"kind": "p", "texte": b.texte, "statut": b.statut,
                "modifie": neuf and b.texte in modifies}
    if isinstance(b, Liste):
        return {"kind": "liste", "elements": b.elements, "ordonnee": b.ordonnee,
                "modifies": [neuf and e in modifies for e in b.elements]}
    if isinstance(b, Encadre):
        return {"kind": "encadre", "texte": b.texte, "genre": b.genre, "titre": b.titre,
                "modifie": neuf and b.texte in modifies}
    if isinstance(b, Figure):
        return {"kind": "figure", "png64": base64.b64encode(b.png).decode("ascii"),
                "titre": b.titre, "legende": b.legende, "unite": b.unite,
                "periode": b.periode, "source": b.source, "statut": b.statut,
                "numero": b.numero, "origine_libelle": LIBELLES_ORIGINE[b.origine],
                "modifie": neuf and ("visuel:" + b.titre) in modifies}
    if isinstance(b, Tableau):
        return {"kind": "tableau", "colonnes": b.colonnes, "lignes": b.lignes,
                "titre": b.titre, "legende": b.legende, "unite": b.unite,
                "periode": b.periode, "source": b.source, "statut": b.statut,
                "numero": b.numero, "modifie": neuf and ("visuel:" + b.titre) in modifies}
    raise TypeError(type(b).__name__)


def en_html(rapport, modifies=None) -> str:
    """HTML du rapport. modifies (ensemble d'empreintes): rendu d'APERCU, ou les
    blocs absents de la version precedente sont surlignes. Les fichiers
    exportes sont toujours rendus sans."""
    sections = [{"cle": s.cle, "titre": s.titre,
                 "blocs": [_bloc(b, modifies) for b in s.blocs]}
                for s in rapport.dans_l_ordre()]
    return _environnement().get_template("rapport.html.j2").render(
        m=rapport.meta, sections=sections, statuts=LIBELLES_STATUT,
        apercu=modifies is not None)
