"""Registre des outils: declaration, filtrage par profil, execution.

Point unique ou un outil devient visible du modele. Trois garanties tenues ici
plutot que dans chaque outil:

  - PERMISSIONS. specs_for() n expose que les outils du profil, et execute()
    revalide la permission. Un outil admin restera donc inexecutable depuis une
    session publique meme si le modele en devine le nom -- le filtrage a
    l affichage seul ne serait pas une securite.
  - ERREURS. Un parametre invalide ne doit pas casser la requete: il revient au
    modele sous forme de tool_result en erreur, que celui-ci peut corriger au
    tour suivant.
  - TAILLE. Un resultat est tronque avant d entrer dans le contexte. Sans
    plafond, un filtre trop large ferait exploser la facture en tokens.
"""
import asyncio
import inspect
import json
import logging
import time

from . import clusters, documents, events, redaction, sst_index, teleconnections
from .common import ToolInputError
from .dataset import DataUnavailableError
from .dataset import load as charger_donnees

log = logging.getLogger("jarvis.tools")

# Un "fournisseur" est un module (outils publics) ou une classe (outils admin
# de jarvis/tools/redaction.py): les deux exposent les memes attributs, donc
# le registre n'a pas a les distinguer.
MODULES = (sst_index, events, teleconnections, clusters, documents) + redaction.OUTILS

MAX_RESULT_CHARS = 6000


class Tool:
    """Un outil: sa declaration pour l API et sa fonction."""

    def __init__(self, module):
        self.name = module.NAME
        self.label = module.LABEL
        self.description = module.DESCRIPTION
        self.schema = module.SCHEMA
        self.permission = module.PERMISSION
        self.datasets = tuple(module.DATASETS)
        self.run = module.run

    def spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


TOOLS = {module.NAME: Tool(module) for module in MODULES}


def _autorise(outil: Tool, profile: str) -> bool:
    if outil.permission == "public":
        return True
    return profile == outil.permission


def specs_for(profile: str = "public") -> list:
    """Declarations d outils visibles par ce profil, ordre stable.

    L ordre compte: il fait partie du prefixe mis en cache cote API. Le
    reordonner invaliderait le cache a chaque demarrage.
    """
    return [outil.spec() for nom, outil in sorted(TOOLS.items())
            if _autorise(outil, profile)]


def label_for(nom: str) -> str:
    outil = TOOLS.get(nom)
    return outil.label if outil else "Consultation des données"


def _erreur(message: str) -> dict:
    return {"content": json.dumps({"erreur": message}, ensure_ascii=False),
            "is_error": True}


def _reduire(charge: dict, max_chars: int) -> str:
    """Serialise en JSON sous un plafond de caracteres.

    Reduit d abord la plus longue liste de la charge, plutot que de couper la
    chaine: un JSON tronque en plein milieu serait illisible pour le modele,
    et pire, partiellement interpretable.
    """
    texte = json.dumps(charge, ensure_ascii=False, default=str)
    if len(texte) <= max_chars:
        return texte

    reduit = dict(charge)
    for _ in range(12):
        listes = [(cle, valeur) for cle, valeur in reduit.items()
                  if isinstance(valeur, list) and len(valeur) > 1]
        if not listes:
            break
        cle, valeur = max(listes, key=lambda item: len(json.dumps(item[1], default=str)))
        reduit[cle] = valeur[: max(1, len(valeur) // 2)]
        reduit["tronque"] = True
        texte = json.dumps(reduit, ensure_ascii=False, default=str)
        if len(texte) <= max_chars:
            return texte
    return texte[:max_chars]


async def execute(nom: str, arguments, profile: str = "public",
                  max_chars: int = MAX_RESULT_CHARS, contexte=None) -> dict:
    """Execute un outil. Ne leve jamais: renvoie toujours un tool_result."""
    debut = time.monotonic()
    outil = TOOLS.get(nom)
    if outil is None:
        log.warning("Outil inconnu demande: %s", nom)
        return _erreur("Outil inconnu: %s. Outils disponibles: %s."
                       % (nom, ", ".join(sorted(TOOLS))))
    if not _autorise(outil, profile):
        # Ne jamais confirmer l existence d un outil hors profil.
        log.warning("Outil %s refuse au profil %s.", nom, profile)
        return _erreur("Outil inconnu: %s." % nom)
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _erreur("Les parametres doivent etre un objet JSON.")

    try:
        donnees = await charger_donnees(outil.datasets)
    except DataUnavailableError as exc:
        log.error("Donnees indisponibles pour %s: %s", nom, exc)
        return _erreur("Les donnees necessaires a cet outil sont "
                       "momentanement indisponibles.")

    # Certains outils ont besoin du contexte de la requete (reglages, session,
    # registre d'actions). On ne passe que ce que la fonction accepte: les
    # outils publics gardent leur signature (params, data) inchangee.
    parametres = inspect.signature(outil.run).parameters
    extra = {cle: valeur for cle, valeur in (contexte or {}).items()
             if cle in parametres}

    try:
        # Les filtres pandas sont rapides mais bloquants: hors boucle.
        resultat = await asyncio.to_thread(outil.run, arguments, donnees, **extra)
    except ToolInputError as exc:
        return _erreur(str(exc))
    except Exception:
        log.exception("Echec de l outil %s", nom)
        return _erreur("Cet outil a rencontre une erreur interne.")

    contenu = _reduire(resultat, max_chars)
    duree_ms = int((time.monotonic() - debut) * 1000)
    log.info("Outil %s execute en %d ms (%d caracteres).", nom, duree_ms, len(contenu))
    return {"content": contenu, "is_error": False, "duration_ms": duree_ms,
            "chars": len(contenu)}
