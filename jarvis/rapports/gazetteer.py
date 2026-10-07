"""Resolution des noms de lieux: "Pikine" -> departement SN0103.

Quatre niveaux, tous issus des fichiers de la plateforme:
  - region et departement: indice de risque par departement (script 26);
  - arrondissement: indice par arrondissement (script 27);
  - commune: table de correspondance commune -> arrondissement (RGPH-5,
    553 communes), qui porte la population 2023 de chaque commune.

Plusieurs candidats = ambiguite, a trancher par la question de clarification:
"Kolda" est a la fois une region, un departement et une commune. Le code ne
choisit jamais a la place de l'utilisateur.
"""
import difflib
import threading
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from ..config import PROJECT_DIR
from ..tools.common import normalise

NIVEAUX = ("pays", "region", "departement", "arrondissement", "commune")
LIBELLES_NIVEAU = {"pays": "pays", "region": "région", "departement": "département",
                   "arrondissement": "arrondissement", "commune": "commune"}
CHEMIN_COMMUNES = PROJECT_DIR / "data" / "processed" / "correspondance_communes_arrondissements.csv"

PAYS_CLES = {"senegal", "lesenegal", "national", "nationale", "pays", "toutlesenegal",
             "toutlepays", "ensembledupays", "ensembledusenegal", "touslesdepartements"}
PREFIXES = (
    ("region", ("regionde", "regiondu", "regiond", "region")),
    ("departement", ("departementde", "departementdu", "departementd", "departement")),
    ("arrondissement", ("arrondissementde", "arrondissementdu", "arrondissementd",
                        "arrondissement")),
    ("commune", ("communede", "communedu", "communed", "commune", "villede", "ville")),
)


@dataclass
class Lieu:
    niveau: str
    code: str
    nom: str
    region: str = ""
    departement: str = ""
    arrondissement: str = ""
    pcode_departement: str = ""
    pcode_arrondissement: str = ""
    population_2023: Optional[float] = None

    def libelle(self) -> str:
        if self.niveau == "pays":
            return "Sénégal (ensemble du pays)"
        if self.niveau == "region":
            return "région de %s" % self.nom
        if self.niveau == "departement":
            return "département de %s (région de %s)" % (self.nom, self.region)
        if self.niveau == "arrondissement":
            return "arrondissement de %s (département de %s)" % (self.nom, self.departement)
        return "commune de %s (arrondissement de %s, département de %s)" % (
            self.nom, self.arrondissement, self.departement)

    def avec_article(self) -> str:
        """'le département de Pikine (région de Dakar)', pour les phrases."""
        if self.niveau == "pays":
            return "l'ensemble du Sénégal"
        article = {"region": "la ", "departement": "le ", "arrondissement": "l'",
                   "commune": "la "}[self.niveau]
        return article + self.libelle()

    def vue(self) -> dict:
        return {"niveau": self.niveau, "code": self.code, "nom": self.nom,
                "libelle": self.libelle()}


PAYS = Lieu("pays", "SN", "Sénégal")


@dataclass
class Resolution:
    candidats: List[Lieu] = field(default_factory=list)
    exact: bool = False
    suggestions: List[str] = field(default_factory=list)

    @property
    def unique(self) -> Optional[Lieu]:
        return self.candidats[0] if len(self.candidats) == 1 else None


def _titre(nom) -> str:
    """'DIAMAGUENE SICAP MBAO' -> 'Diamaguene Sicap Mbao' (communes en capitales)."""
    texte = str(nom).strip()
    if texte.isupper():
        return " ".join(m.lower() if m in ("DE", "DU", "DES") else m.capitalize()
                        for m in texte.split())
    return texte


class Gazetteer:
    def __init__(self, departements: pd.DataFrame, arrondissements: Optional[pd.DataFrame] = None,
                 communes: Optional[pd.DataFrame] = None):
        self.lieux: List[Lieu] = [PAYS]
        regions = {}
        for _, r in departements.iterrows():
            regions.setdefault(r["region"], r["pcode"][:4])
            self.lieux.append(Lieu("departement", r["pcode"], r["departement"], region=r["region"],
                                   departement=r["departement"], pcode_departement=r["pcode"]))
        for nom, code in sorted(regions.items()):
            self.lieux.append(Lieu("region", code, nom, region=nom))
        region_du_dep = {r["pcode"]: r["region"] for _, r in departements.iterrows()}
        if arrondissements is not None:
            for _, r in arrondissements.iterrows():
                if not isinstance(r.get("arrondissement"), str):
                    continue
                self.lieux.append(Lieu(
                    "arrondissement", r["pcode"], r["arrondissement"], region=r["region"],
                    departement=r["departement"], arrondissement=r["arrondissement"],
                    pcode_departement=r.get("adm2_pcode") or r["pcode"][:6],
                    pcode_arrondissement=r["pcode"]))
        if communes is not None:
            for _, r in communes.iterrows():
                if not isinstance(r.get("COMMUNE"), str) or not isinstance(r.get("adm3_pcode"), str):
                    continue
                nom = _titre(r["COMMUNE"])
                pop = r.get("population_2023")
                self.lieux.append(Lieu(
                    "commune", "%s:%s" % (r["adm3_pcode"], normalise(nom)), nom,
                    region=region_du_dep.get(r["adm2_pcode"], _titre(r.get("Region", ""))),
                    departement=r.get("adm2_name") or _titre(r.get("Departement", "")),
                    arrondissement=r.get("adm3_name") or "",
                    pcode_departement=r["adm2_pcode"], pcode_arrondissement=r["adm3_pcode"],
                    population_2023=float(pop) if pd.notna(pop) else None))
        self._index = {}
        for lieu in self.lieux:
            self._index.setdefault(normalise(lieu.nom), []).append(lieu)

    def _tri(self, lieux):
        vus, sortie = set(), []
        for lieu in sorted(lieux, key=lambda l: (NIVEAUX.index(l.niveau), l.nom)):
            if lieu.code not in vus:
                vus.add(lieu.code)
                sortie.append(lieu)
        return sortie

    def resoudre(self, texte) -> Resolution:
        cle = normalise(texte)
        if not cle:
            return Resolution()
        if cle in PAYS_CLES:
            return Resolution([PAYS], exact=True)
        niveau_impose = None
        for niveau, prefixes in PREFIXES:
            for prefixe in prefixes:
                if cle.startswith(prefixe) and len(cle) > len(prefixe) + 1:
                    niveau_impose, cle = niveau, cle[len(prefixe):]
                    break
            if niveau_impose:
                break

        def garder(lieux):
            if niveau_impose:
                lieux = [l for l in lieux if l.niveau == niveau_impose]
            return self._tri(lieux)

        exacts = garder(self._index.get(cle, []))
        if exacts:
            return Resolution(exacts, exact=True)
        if len(cle) >= 4:
            partiels = garder([l for k, ls in self._index.items() if k.startswith(cle) for l in ls])
            if partiels:
                return Resolution(partiels[:8])
        proches = difflib.get_close_matches(cle, list(self._index), n=6, cutoff=0.8)
        candidats = garder([l for k in proches for l in self._index[k]])
        if candidats:
            return Resolution(candidats[:8])
        suggestions = difflib.get_close_matches(cle, list(self._index), n=5, cutoff=0.6)
        return Resolution([], suggestions=[self._index[k][0].nom for k in suggestions])

    def par_code(self, code) -> Optional[Lieu]:
        for lieu in self.lieux:
            if lieu.code == code:
                return lieu
        return None

    def communes_de(self, pcode_arrondissement=None, pcode_departement=None) -> List[Lieu]:
        return [l for l in self.lieux if l.niveau == "commune"
                and (pcode_arrondissement is None or l.pcode_arrondissement == pcode_arrondissement)
                and (pcode_departement is None or l.pcode_departement == pcode_departement)]


_verrou = threading.Lock()
_instance = {}


def charger() -> Gazetteer:
    """Gazetteer des vraies donnees (memes tables que la page Vulnerabilite)."""
    with _verrou:
        if "g" not in _instance:
            from ..tools import dataset
            v = dataset.get("vulnerabilite")
            communes = pd.read_csv(CHEMIN_COMMUNES, encoding="utf-8") \
                if CHEMIN_COMMUNES.is_file() else None
            _instance["g"] = Gazetteer(v["departements"], v.get("arrondissements"), communes)
        return _instance["g"]
