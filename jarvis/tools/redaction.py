"""Outils admin sur les documents de recherche (Phase 5).

Trois outils, dont deux en lecture seule et un qui ne fait que PROPOSER:

    list_documents            etat des fichiers sur le disque
    find_in_document          occurrences exactes d'un texte, avec contexte
    propose_document_edit     depose une correction, n'ecrit rien

La difference avec search_documents (public) est essentielle: celui-la
interroge un index fige, ceux-ci lisent les fichiers VIVANTS. Une correction
doit viser le document, pas l'instantane qui en a ete tire -- et apres
modification, l'index est a reconstruire.

propose_document_edit n'ecrit jamais, meme si on le lui demande: il depose une
proposition que l'utilisateur applique d'un clic dans la console. Voir
jarvis/actions.py pour le pourquoi.
"""
from .. import documents
from ..documents import DocumentIntrouvable, RemplacementImpossible
from .common import ToolInputError, champ_entier, champ_texte

PERMISSION = "admin"

RAPPEL_INDEX = (
    "Apres application, l'index documentaire est perime: relancer "
    "scripts/15_build_jarvis_index.py pour que search_documents cite la "
    "version corrigee."
)


# =============================================================================
# list_documents
# =============================================================================
class ListDocuments:
    NAME = "list_documents"
    LABEL = "Etat des documents"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "Etat des documents de recherche sur le disque: cle a utiliser dans "
        "les autres outils, nom de fichier, taille, date de derniere "
        "modification. A appeler avant toute correction, pour verifier quel "
        "document est vise et qu'il est bien present."
    )
    SCHEMA = {"type": "object", "properties": {}, "required": []}

    @staticmethod
    def run(params, data, settings=None):
        return {"documents": documents.catalogue(settings),
                "dossier": str(settings.documents_dir)}


# =============================================================================
# find_in_document
# =============================================================================
class FindInDocument:
    NAME = "find_in_document"
    LABEL = "Recherche dans les documents"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "Cherche un texte EXACT dans un document vivant et renvoie chaque "
        "occurrence avec sa section et son voisinage. Indispensable avant de "
        "proposer une correction: il faut savoir combien de fois la chaine "
        "apparait, et ou. Recherche litterale, sensible a la casse et aux "
        "accents -- ce n'est pas une recherche semantique, utiliser "
        "search_documents pour cela."
    )
    SCHEMA = {
        "type": "object",
        "properties": {
            "document": {"type": "string",
                         "description": "Cle du document (voir list_documents)."},
            "text": {"type": "string",
                     "description": "Texte exact a rechercher."},
            "limit": {"type": "integer",
                      "description": "Nombre d'occurrences renvoyees (1 a 20, defaut 10)."},
        },
        "required": ["document", "text"],
    }

    @staticmethod
    def run(params, data, settings=None):
        cle = champ_texte(params, "document", maxi=60)
        recherche = champ_texte(params, "text", maxi=300)
        limite = champ_entier(params, "limit", mini=1, maxi=20, defaut=10)
        if not cle or not recherche:
            raise ToolInputError("Les parametres document et text sont requis.")
        try:
            trouvees = documents.occurrences(settings, cle, recherche)
        except DocumentIntrouvable as exc:
            raise ToolInputError(str(exc))
        return {
            "document": cle,
            "recherche": recherche,
            "n_occurrences": len(trouvees),
            "occurrences": trouvees[:limite],
            "message": ("Aucune occurrence. Le texte peut etre scinde par une "
                        "mise en forme: essayer une portion plus courte."
                        if not trouvees else None),
        }


# =============================================================================
# propose_document_edit
# =============================================================================
class ProposeDocumentEdit:
    NAME = "propose_document_edit"
    LABEL = "Proposition de correction"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "PROPOSE le remplacement d'un texte exact dans un document. N'ecrit "
        "rien: depose une proposition que l'utilisateur applique lui-meme d'un "
        "clic dans la console, apres avoir vu le detail des changements. "
        "Annonce donc une proposition, jamais une modification faite. "
        "Verifier d'abord avec find_in_document: TOUTES les occurrences du "
        "texte seront remplacees. Une sauvegarde horodatee du document est "
        "ecrite automatiquement au moment de l'application."
    )
    SCHEMA = {
        "type": "object",
        "properties": {
            "document": {"type": "string",
                         "description": "Cle du document (voir list_documents)."},
            "old_text": {"type": "string",
                         "description": "Texte exact a remplacer. Assez long "
                                        "pour etre sans ambiguite, assez court "
                                        "pour tenir dans un seul fragment de "
                                        "mise en forme."},
            "new_text": {"type": "string",
                         "description": "Texte de remplacement."},
            "reason": {"type": "string",
                       "description": "Pourquoi cette correction, en une "
                                      "phrase. Affiche a l'utilisateur avant "
                                      "qu'il approuve."},
        },
        "required": ["document", "old_text", "new_text", "reason"],
    }

    @staticmethod
    def run(params, data, settings=None, session_id=None, registre=None):
        cle = champ_texte(params, "document", maxi=60)
        avant = champ_texte(params, "old_text", maxi=2000)
        apres = params.get("new_text")
        raison = champ_texte(params, "reason", maxi=300)

        if not cle or not avant or apres is None:
            raise ToolInputError(
                "Les parametres document, old_text et new_text sont requis.")
        apres = str(apres)
        if len(apres) > 2000:
            raise ToolInputError("new_text est trop long (2000 caracteres maximum).")
        if not raison:
            raise ToolInputError(
                "Le parametre reason est requis: l'utilisateur doit savoir "
                "pourquoi cette correction lui est proposee.")

        try:
            apercu = documents.previsualiser_remplacement(settings, cle, avant, apres)
        except (DocumentIntrouvable, RemplacementImpossible) as exc:
            raise ToolInputError(str(exc))

        if registre is None or session_id is None:  # pragma: no cover - garde-fou
            raise ToolInputError("Contexte de session absent.")

        action = registre.deposer(
            session_id,
            "document_remplacer",
            "%s : remplacer %r par %r (%d occurrence%s)"
            % (cle, avant[:60], apres[:60], apercu["n_occurrences"],
               "s" if apercu["n_occurrences"] > 1 else ""),
            {"document": cle, "fichier": apercu["fichier"], "raison": raison,
             "avant": avant, "apres": apres,
             "n_occurrences": apercu["n_occurrences"],
             "changements": apercu["changements"][:10]},
            {"document": cle, "avant": avant, "apres": apres},
        )

        return {
            "statut": "proposition_deposee",
            "action_id": action.id,
            "document": cle,
            "n_occurrences": apercu["n_occurrences"],
            "changements": apercu["changements"][:5],
            "expire_dans_s": action.vue_publique()["expire_dans"],
            "message": (
                "Proposition deposee. RIEN n'a ete modifie: elle attend "
                "l'approbation de l'utilisateur dans la console. Annoncer ce "
                "qui sera change et inviter a approuver."
            ),
            "rappel": RAPPEL_INDEX,
        }


OUTILS = (ListDocuments, FindInDocument, ProposeDocumentEdit)
