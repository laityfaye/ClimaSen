"""Collecteurs: les faits et les visuels de chaque type de rapport.

Un collecteur ne lit les donnees que par les chargeurs du dashboard (via les
jeux deja charges par jarvis/tools/dataset.py) ou par les outils publics
d'Iris eux-memes: un rapport, la page et Iris donnent donc les memes chiffres.

Il renvoie une Collecte: registre de faits, visuels, limites a signaler et
une redaction GABARIT complete (phrases ecrites par le code, avec des renvois
{{fait:id}}). Le gabarit sert de base au modele et de repli si sa redaction
echoue a la verification.
"""
import math
from dataclasses import dataclass, field
from typing import List, Tuple

from ... import figures as module_figures
from ..document import Encadre, Figure, Tableau
from ..faits import RegistreFaits, nombre_fr


class CollecteImpossible(Exception):
    """Donnees insuffisantes pour ce rapport (message lisible par l'utilisateur)."""


@dataclass
class Collecte:
    registre: RegistreFaits
    titre: str
    sous_titre: str
    zone: str
    periode: str
    # (section, bloc): Figure, Tableau ou Encadre, dans l'ordre d'affichage.
    visuels: List[Tuple[str, object]] = field(default_factory=list)
    limites: List[str] = field(default_factory=list)
    limites_specifiques: List[str] = field(default_factory=list)
    # section -> [(texte avec renvois, statut)], pour contexte, resume,
    # analyse et conclusions.
    gabarit: dict = field(default_factory=dict)
    recommandations: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    mentions: List[Encadre] = field(default_factory=list)
    # Points d'attention donnes au redacteur (non affiches).
    consignes: List[str] = field(default_factory=list)

    def paragraphe(self, section, texte, statut=None):
        self.gabarit.setdefault(section, []).append((texte, statut))

    def limite(self, *cles):
        for cle in cles:
            if cle not in self.limites:
                self.limites.append(cle)


def figure(spec, titre, legende, unite, periode, source, statut=None, origine="generee"):
    """Rend une spec de jarvis/figures en Figure de rapport (format impression)."""
    png = module_figures.rendre(spec, "clair", impression=True)
    try:
        donnees = module_figures.en_csv(spec)
    except Exception:  # la vue tableau est un plus, pas une condition
        donnees = ""
    return Figure(png=png, titre=titre, legende=legende, unite=unite, periode=periode,
                  source=source, origine=origine, donnees_csv=donnees, statut=statut)


def tableau(colonnes, lignes, titre, legende, unite, periode, source, statut=None):
    return Tableau(colonnes=list(colonnes), lignes=[list(l) for l in lignes], titre=titre,
                   legende=legende, unite=unite, periode=periode, source=source, statut=statut)


def cellule(valeur, decimales=2, suffixe=""):
    """Valeur de tableau formatee en francais; vide si absente."""
    if valeur is None:
        return "—"
    if isinstance(valeur, str):
        return valeur
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return str(valeur)
    if not math.isfinite(v):
        return "—"
    return nombre_fr(v, decimales).replace("-", "−") + suffixe


def fini(valeur):
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None
