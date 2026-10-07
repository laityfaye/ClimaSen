"""Registre des faits d'un rapport: la seule source de chiffres.

Un Fait est une valeur lue dans les donnees de la plateforme, avec son unite,
sa source, sa periode et son STATUT:

    observe   mesure ou compte dans les donnees (CHIRPS, RGPH-5...)
    correle   lien statistique (correlation SST / pluies): jamais une prevision
    projete   probabilite ou niveau annonce pour une saison a venir
    methode   parametre de methode (seuil de 2 sigma, nombre de tests...)

Le texte du rapport ne contient pas de chiffres ecrits a la main: il porte
des renvois {{fait:identifiant}}, remplaces ici par la valeur formatee en
francais. Un renvoi vers un fait inconnu est une erreur, pas un blanc.
"""
import csv
import io
import math
import re
from dataclasses import dataclass, field

STATUTS = ("observe", "correle", "projete", "methode")
FORMATS = ("nombre", "entier", "fraction_pct", "pct", "texte", "annee", "date", "signe")

LIBELLES_STATUT = {
    "observe": "Observé",
    "correle": "Corrélé",
    "projete": "Projeté",
    "methode": "Méthode",
}

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

RENVOI = re.compile(r"\{\{\s*fait\s*:\s*([A-Za-z0-9_.\-]+)\s*\}\}")
# Espace insecable: un nombre ne se coupe pas en fin de ligne.
INSECABLE = " "


class FaitInconnu(KeyError):
    """Renvoi {{fait:x}} vers un fait absent du registre."""


class FaitInvalide(ValueError):
    """Fait mal forme (statut, format, valeur non finie)."""


def nombre_fr(valeur, decimales=2):
    """1234567.891 -> '1 234 567,89' (espaces insecables)."""
    texte = "{:,.{d}f}".format(float(valeur), d=max(0, int(decimales)))
    return texte.replace(",", INSECABLE).replace(".", ",")


def date_fr(iso):
    a, m, j = str(iso)[:10].split("-")
    return "%d %s %s" % (int(j), MOIS[int(m) - 1], a)


@dataclass
class Fait:
    id: str
    valeur: object
    libelle: str
    statut: str
    source: str
    periode: str
    unite: str = ""
    format: str = "nombre"
    decimales: int = 2
    suffixe: str = ""

    def __post_init__(self):
        if self.statut not in STATUTS:
            raise FaitInvalide("statut inconnu pour %s: %r" % (self.id, self.statut))
        if self.format not in FORMATS:
            raise FaitInvalide("format inconnu pour %s: %r" % (self.id, self.format))
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", self.id or ""):
            raise FaitInvalide("identifiant invalide: %r" % self.id)
        if not self.source or not self.periode:
            raise FaitInvalide("source et periode obligatoires pour %s" % self.id)
        if self.format not in ("texte", "date"):
            try:
                v = float(self.valeur)
            except (TypeError, ValueError):
                raise FaitInvalide("valeur non numerique pour %s: %r" % (self.id, self.valeur))
            if not math.isfinite(v):
                raise FaitInvalide("valeur non finie pour %s" % self.id)

    def texte(self) -> str:
        """Valeur formatee telle qu'elle apparait dans le rapport."""
        f = self.format
        if f == "texte":
            corps = str(self.valeur)
        elif f == "date":
            corps = date_fr(self.valeur)
        elif f == "annee":
            corps = "%d" % int(self.valeur)
        elif f == "entier":
            corps = nombre_fr(round(float(self.valeur)), 0)
        elif f == "fraction_pct":
            corps = nombre_fr(100 * float(self.valeur), self.decimales) + INSECABLE + "%"
        elif f == "pct":
            corps = nombre_fr(float(self.valeur), self.decimales) + INSECABLE + "%"
        elif f == "signe":
            v = float(self.valeur)
            corps = ("+" if v > 0 else "") + nombre_fr(v, self.decimales)
            corps = corps.replace("-", "−")
        else:
            corps = nombre_fr(float(self.valeur), self.decimales).replace("-", "−")
        return corps + self.suffixe


@dataclass
class RegistreFaits:
    faits: dict = field(default_factory=dict)

    def ajouter(self, id, valeur, libelle, statut, source, periode, **options) -> Fait:
        if id in self.faits:
            raise FaitInvalide("fait en double: %s" % id)
        fait = Fait(id=id, valeur=valeur, libelle=libelle, statut=statut,
                    source=source, periode=periode, **options)
        self.faits[id] = fait
        return fait

    def ajouter_si(self, id, valeur, *args, **options):
        """N'ajoute que si la valeur existe (None, NaN: le fait est absent,
        pas zero). Renvoie le fait ou None."""
        if valeur is None:
            return None
        if not isinstance(valeur, str):
            try:
                if not math.isfinite(float(valeur)):
                    return None
            except (TypeError, ValueError):
                return None
        return self.ajouter(id, valeur, *args, **options)

    def __contains__(self, id):
        return id in self.faits

    def __getitem__(self, id) -> Fait:
        try:
            return self.faits[id]
        except KeyError:
            raise FaitInconnu(id)

    def __iter__(self):
        return iter(self.faits.values())

    def __len__(self):
        return len(self.faits)

    def t(self, id) -> str:
        """Valeur formatee (raccourci pour les gabarits ecrits en Python)."""
        return self[id].texte()

    def renvois(self, texte: str) -> list:
        return RENVOI.findall(texte or "")

    def inconnus(self, texte: str) -> list:
        return [i for i in self.renvois(texte) if i not in self.faits]

    def remplacer(self, texte: str) -> str:
        def sub(m):
            return self[m.group(1)].texte()
        return RENVOI.sub(sub, texte or "")

    def statuts_cites(self, texte: str) -> set:
        return {self.faits[i].statut for i in self.renvois(texte) if i in self.faits}

    def pour_redaction(self) -> list:
        """Ce que voit le modele: identifiant, sens, statut, valeur affichee.

        La valeur est donnee pour qu'il juge (fort, faible, en hausse), pas
        pour qu'il la recopie: la verification refuse un chiffre tape en clair
        qui ne serait pas celui d'un fait.
        """
        return [{"id": f.id, "libelle": f.libelle, "statut": f.statut,
                 "valeur_affichee": f.texte(), "unite": f.unite, "periode": f.periode}
                for f in self.faits.values()]

    def en_csv(self) -> str:
        sortie = io.StringIO()
        ecrivain = csv.writer(sortie, lineterminator="\n")
        ecrivain.writerow(["id", "libelle", "valeur", "valeur_affichee", "unite",
                           "statut", "periode", "source"])
        for f in self.faits.values():
            ecrivain.writerow([f.id, f.libelle, f.valeur, f.texte(), f.unite,
                               f.statut, f.periode, f.source])
        return sortie.getvalue()
