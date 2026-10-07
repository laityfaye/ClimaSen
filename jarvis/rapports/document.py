"""Modele de document d'un rapport: une structure, trois rendus.

Le HTML, le PDF et le Word sont produits a partir de CE modele, jamais l'un
de l'autre: une conversion HTML -> Word donne toujours un document mediocre,
et deux chaines distinctes finiraient par diverger.

Structure FIXE, imposee ici et non par le gabarit:

    contexte       Titre et contexte
    resume         Resume executif
    methodologie   Methodologie et sources
    analyse        Analyse
    conclusions    Conclusions et recommandations operationnelles
    annexes        Annexes: limites et tracabilite

Un visuel (Figure, Tableau) sans titre, legende, unite, periode ou source est
refuse A LA CONSTRUCTION: on ne compte pas sur une relecture pour l'attraper.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .faits import STATUTS

SECTIONS = (
    ("contexte", "Titre et contexte"),
    ("resume", "Résumé exécutif"),
    ("methodologie", "Méthodologie et sources"),
    ("analyse", "Analyse"),
    ("conclusions", "Conclusions et recommandations opérationnelles"),
    ("annexes", "Annexes : limites et traçabilité"),
)
CLES_SECTIONS = tuple(c for c, _ in SECTIONS)
GENRES_ENCADRE = ("limite", "avertissement", "officiel", "hypothese", "information")
ORIGINES_FIGURE = ("generee", "reference", "a_la_demande")
LIBELLES_ORIGINE = {
    "generee": "Figure calculée par la plateforme pour ce rapport",
    "reference": "Figure de référence (chaîne de traitement validée)",
    "a_la_demande": "Figure générée à la demande à partir des données de la plateforme",
}


class DocumentInvalide(ValueError):
    """Bloc incomplet ou structure non conforme."""


def _exiger(objet, champs):
    manquants = [c for c in champs if not str(getattr(objet, c, "") or "").strip()]
    if manquants:
        raise DocumentInvalide("%s incomplet (%s): %s" % (
            type(objet).__name__, getattr(objet, "titre", "?"), ", ".join(manquants)))


@dataclass
class Paragraphe:
    texte: str
    statut: Optional[str] = None      # observe / correle / projete / methode / None

    def __post_init__(self):
        if self.statut is not None and self.statut not in STATUTS:
            raise DocumentInvalide("statut de paragraphe inconnu: %r" % self.statut)
        if not (self.texte or "").strip():
            raise DocumentInvalide("paragraphe vide")


@dataclass
class Liste:
    elements: List[str]
    ordonnee: bool = False

    def __post_init__(self):
        self.elements = [e for e in self.elements if (e or "").strip()]
        if not self.elements:
            raise DocumentInvalide("liste vide")


@dataclass
class Encadre:
    texte: str
    genre: str = "information"
    titre: str = ""

    def __post_init__(self):
        if self.genre not in GENRES_ENCADRE:
            raise DocumentInvalide("genre d'encadre inconnu: %r" % self.genre)
        if not (self.texte or "").strip():
            raise DocumentInvalide("encadre vide")


@dataclass
class Figure:
    png: bytes
    titre: str
    legende: str
    unite: str
    periode: str
    source: str
    origine: str = "generee"
    donnees_csv: str = ""
    statut: Optional[str] = None
    numero: int = 0

    def __post_init__(self):
        _exiger(self, ("titre", "legende", "unite", "periode", "source"))
        if not self.png or self.png[:4] not in (b"\x89PNG", b"GIF8"):
            raise DocumentInvalide("Figure %r: image PNG absente ou invalide" % self.titre)
        if self.origine not in ORIGINES_FIGURE:
            raise DocumentInvalide("origine de figure inconnue: %r" % self.origine)


@dataclass
class Tableau:
    colonnes: List[str]
    lignes: List[list]
    titre: str
    legende: str
    unite: str
    periode: str
    source: str
    statut: Optional[str] = None
    numero: int = 0

    def __post_init__(self):
        _exiger(self, ("titre", "legende", "unite", "periode", "source"))
        if not self.colonnes:
            raise DocumentInvalide("Tableau %r sans colonnes" % self.titre)
        if not self.lignes:
            raise DocumentInvalide("Tableau %r vide" % self.titre)
        for ligne in self.lignes:
            if len(ligne) != len(self.colonnes):
                raise DocumentInvalide("Tableau %r: ligne de %d cellules pour %d colonnes"
                                       % (self.titre, len(ligne), len(self.colonnes)))


@dataclass
class Section:
    cle: str
    titre: str
    blocs: list = field(default_factory=list)


@dataclass
class Meta:
    id: str
    type: str
    titre: str
    sous_titre: str
    genere_le: str              # ISO, heure de Dakar (UTC)
    version_donnees: str
    commit: str
    redaction: str              # "ia" ou "gabarit"
    modele: str                 # modele de redaction, ou "aucun"
    public: str
    zone: str
    periode: str
    hypotheses: List[str] = field(default_factory=list)
    spec: dict = field(default_factory=dict)
    version: int = 1                         # version du rapport (modifications)


class Rapport:
    def __init__(self, meta: Meta):
        self.meta = meta
        self.sections = {cle: Section(cle, titre) for cle, titre in SECTIONS}

    def ajouter(self, cle: str, bloc) -> None:
        if cle not in self.sections:
            raise DocumentInvalide("section inconnue: %r" % cle)
        if not isinstance(bloc, (Paragraphe, Liste, Encadre, Figure, Tableau)):
            raise DocumentInvalide("bloc de type inconnu: %r" % type(bloc).__name__)
        self.sections[cle].blocs.append(bloc)

    def dans_l_ordre(self):
        return [self.sections[c] for c in CLES_SECTIONS]

    def figures(self):
        return [b for s in self.dans_l_ordre() for b in s.blocs if isinstance(b, Figure)]

    def tableaux(self):
        return [b for s in self.dans_l_ordre() for b in s.blocs if isinstance(b, Tableau)]

    def finaliser(self) -> "Rapport":
        """Numerote figures et tableaux, puis verifie la structure."""
        for i, f in enumerate(self.figures(), 1):
            f.numero = i
        for i, t in enumerate(self.tableaux(), 1):
            t.numero = i
        vides = [s.titre for s in self.dans_l_ordre() if not s.blocs]
        if vides:
            raise DocumentInvalide("sections vides: %s" % ", ".join(vides))
        return self

    def textes(self):
        """Tout le texte du rapport (verification de fidelite des nombres)."""
        morceaux = [self.meta.titre, self.meta.sous_titre]
        for s in self.dans_l_ordre():
            for b in s.blocs:
                if isinstance(b, Paragraphe):
                    morceaux.append(b.texte)
                elif isinstance(b, Liste):
                    morceaux.extend(b.elements)
                elif isinstance(b, Encadre):
                    morceaux.extend([b.titre, b.texte])
                elif isinstance(b, (Figure, Tableau)):
                    morceaux.extend([b.titre, b.legende, b.unite, b.periode, b.source])
                    if isinstance(b, Tableau):
                        morceaux.extend(str(c) for ligne in b.lignes for c in ligne)
        return [m for m in morceaux if m]
