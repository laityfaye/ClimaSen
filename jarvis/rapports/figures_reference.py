"""Index des figures de reference (chaine de traitement validee).

Premier recours avant de generer un visuel: une figure deja produite et
relue par la chaine de traitement vaut mieux qu'un recalcul. Les metadonnees
viennent de figures_reference.yaml; une entree dont le fichier manque est
simplement indisponible.
"""
from functools import lru_cache
from pathlib import Path

from ..config import PROJECT_DIR
from .document import Figure

INDEX = Path(__file__).resolve().parent / "figures_reference.yaml"
CHAMPS = ("id", "fichier", "titre", "legende", "unite", "periode", "source", "types")


@lru_cache(maxsize=1)
def _entrees():
    import yaml
    donnees = yaml.safe_load(INDEX.read_text(encoding="utf-8")) or {}
    entrees = {}
    for e in donnees.get("figures", []):
        manquants = [c for c in CHAMPS if not e.get(c)]
        if manquants:
            raise ValueError("figures_reference.yaml: %s incomplet (%s)"
                             % (e.get("id"), ", ".join(manquants)))
        entrees[e["id"]] = e
    return entrees


def disponibles(type_=None) -> list:
    """Figures dont le fichier existe, eventuellement filtrees par type de rapport."""
    return [{"id": e["id"], "titre": e["titre"], "types": e["types"]}
            for e in _entrees().values()
            if (PROJECT_DIR / e["fichier"]).is_file() and (type_ is None or type_ in e["types"])]


def figure(ident) -> Figure:
    e = _entrees().get(ident)
    if e is None:
        raise KeyError("Figure de référence inconnue : %s. Disponibles : %s."
                       % (ident, ", ".join(sorted(_entrees()))))
    chemin = PROJECT_DIR / e["fichier"]
    if not chemin.is_file():
        raise KeyError("Figure de référence absente du serveur : %s." % ident)
    return Figure(png=chemin.read_bytes(), titre=e["titre"], legende=e["legende"],
                  unite=e["unite"], periode=e["periode"], source=e["source"],
                  origine="reference", statut=e.get("statut"))
