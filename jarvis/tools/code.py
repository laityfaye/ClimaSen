"""Outils admin sur le code et les taches (Phase 10).

    read_code            lister un dossier, lire un fichier, chercher un motif
    propose_code_edit    depose une modification de code, n'ecrit rien
    propose_task         depose l'execution d'un script du pipeline ou de tests
    get_task_status      etat des propositions de la session (dont les taches)

Comme propose_document_edit, les deux outils "propose_" ne font que DEPOSER:
l'ecriture ou l'execution part de POST /api/admin/actions/{id}/approve, une
route qui n'est pas un outil. Voir jarvis/actions.py et jarvis/code_ops.py.
"""
from .. import code_ops
from ..code_ops import RefusCode
from .common import ToolInputError, champ_bool, champ_entier, champ_enum, champ_texte

PERMISSION = "admin"


def _refus(exc: RefusCode):
    return ToolInputError(str(exc))


def _actions_actives(settings):
    if settings is not None and not getattr(settings, "code_actions_enabled", True):
        raise ToolInputError("Les modifications de code et l'execution de taches "
                             "sont desactivees sur ce serveur "
                             "(JARVIS_CODE_ACTIONS_ENABLED=false).")


# =============================================================================
class ReadCode:
    NAME = "read_code"
    LABEL = "Lecture du code"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "Lit le code du projet ClimatSen (lecture seule). action=lister: "
        "contenu d'un dossier (dossier vide = racine). action=lire: lignes "
        "numerotees d'un fichier (par tranches; 'suite' dit s'il en reste). "
        "action=chercher: motif (texte ou expression reguliere) dans les "
        "fichiers, avec numeros de ligne. A utiliser AVANT toute proposition "
        "de modification, pour citer le texte exact a remplacer. Secrets, "
        "environnements et donnees brutes ne sont pas lisibles."
    )
    SCHEMA = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["lister", "lire", "chercher"]},
            "path": {"type": "string",
                     "description": "Fichier ou dossier, relatif a la racine "
                                    "du projet (ex: scripts/pages/pipeline.py)."},
            "start_line": {"type": "integer", "description": "lire: premiere ligne."},
            "end_line": {"type": "integer", "description": "lire: derniere ligne."},
            "pattern": {"type": "string", "description": "chercher: motif."},
        },
        "required": ["action"],
    }

    @staticmethod
    def run(params, data):
        action = champ_enum(params, "action", ["lister", "lire", "chercher"])
        chemin = champ_texte(params, "path", maxi=300)
        try:
            if action == "lister":
                return code_ops.lister(chemin or "")
            if action == "lire":
                if not chemin:
                    raise ToolInputError("Le parametre path est requis pour lire.")
                return code_ops.lire(chemin,
                                     champ_entier(params, "start_line", mini=1, defaut=1),
                                     champ_entier(params, "end_line", mini=1))
            if action == "chercher":
                motif = champ_texte(params, "pattern", maxi=200)
                if not motif:
                    raise ToolInputError("Le parametre pattern est requis pour chercher.")
                return code_ops.chercher(motif, chemin or "")
        except RefusCode as exc:
            raise _refus(exc)
        raise ToolInputError("Le parametre action est requis: lister, lire ou chercher.")


# =============================================================================
class ProposeCodeEdit:
    NAME = "propose_code_edit"
    LABEL = "Proposition de modification du code"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "PROPOSE une modification d'un fichier de scripts/, src/ ou tests/ "
        "(remplacement d'un texte exact, ou creation d'un fichier avec "
        "old_text vide). N'ECRIT RIEN: la modification, avec son diff, attend "
        "que Laity l'approuve d'un clic. Le code Python est compile avant "
        "d'etre propose: une erreur de syntaxe est refusee. Lire d'abord le "
        "fichier avec read_code et copier old_text exactement, sans les "
        "numeros de ligne. jarvis/, deploy/ et les fichiers de configuration "
        "ne sont pas modifiables."
    )
    SCHEMA = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Fichier a modifier ou creer."},
            "old_text": {"type": "string",
                         "description": "Texte exact a remplacer (vide pour "
                                        "creer un fichier). Doit etre unique "
                                        "dans le fichier, sauf replace_all."},
            "new_text": {"type": "string", "description": "Nouveau texte."},
            "replace_all": {"type": "boolean",
                            "description": "Remplacer toutes les occurrences. "
                                           "Defaut: false."},
            "reason": {"type": "string",
                       "description": "Pourquoi, en une ou deux phrases. "
                                      "Affiche a Laity avant qu'il approuve."},
        },
        "required": ["path", "old_text", "new_text", "reason"],
    }

    @staticmethod
    def run(params, data, settings=None, session_id=None, registre=None):
        _actions_actives(settings)
        chemin = champ_texte(params, "path", maxi=300)
        raison = champ_texte(params, "reason", maxi=400)
        if not chemin:
            raise ToolInputError("Le parametre path est requis.")
        if not raison:
            raise ToolInputError("Le parametre reason est requis: Laity doit "
                                 "savoir pourquoi avant d'approuver.")
        ancien = params.get("old_text") or ""
        nouveau = params.get("new_text")
        if not isinstance(ancien, str) or not isinstance(nouveau, str):
            raise ToolInputError("old_text et new_text doivent etre du texte.")
        try:
            prep = code_ops.preparer_modification(
                chemin, ancien, nouveau, champ_bool(params, "replace_all", defaut=False))
        except RefusCode as exc:
            raise _refus(exc)
        if registre is None or session_id is None:  # pragma: no cover
            raise ToolInputError("Contexte de session absent.")

        action = registre.deposer(
            session_id, "code_modifier",
            "%s : %s (+%d / -%d lignes)" % (prep["fichier"], prep["mode"],
                                            prep["lignes_ajoutees"],
                                            prep["lignes_retirees"]),
            {"fichier": prep["fichier"], "mode": prep["mode"], "raison": raison,
             "diff": prep["diff"], "diff_tronque": prep["diff_tronque"],
             "lignes_ajoutees": prep["lignes_ajoutees"],
             "lignes_retirees": prep["lignes_retirees"],
             "occurrences": prep["occurrences"]},
            {"fichier": prep["fichier"], "mode": prep["mode"],
             "contenu": prep["contenu"],
             "empreinte_avant": prep["empreinte_avant"],
             "lignes_ajoutees": prep["lignes_ajoutees"],
             "lignes_retirees": prep["lignes_retirees"]},
        )
        return {
            "statut": "proposition_deposee",
            "action_id": action.id,
            "fichier": prep["fichier"],
            "mode": prep["mode"],
            "lignes_ajoutees": prep["lignes_ajoutees"],
            "lignes_retirees": prep["lignes_retirees"],
            "compilation": "ok" if prep["fichier"].endswith(".py") else "sans objet",
            "message": ("Proposition deposee. RIEN n'a ete modifie: le diff "
                        "attend l'approbation de Laity sous ta reponse. "
                        "Resume ce qui change et pourquoi; propose ensuite de "
                        "lancer les tests concernes avec propose_task."),
        }


# =============================================================================
class ProposeTask:
    NAME = "propose_task"
    LABEL = "Proposition d'exécution"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "PROPOSE d'executer une tache sur le serveur: un script du pipeline "
        "(ex: 04_teleconnections_analysis.py, 11_kmeans_sst_analysis.py, "
        "14_sst_patterns_cartopy.py) ou les tests (script=pytest, avec "
        "test_file optionnel: tests/test_xxx.py). N'EXECUTE RIEN: la tache "
        "attend l'approbation de Laity, puis tourne en arriere-plan, une a la "
        "fois, avec un delai maximal. Suivre son avancement avec "
        "get_task_status. Utile apres une modification de code, ou quand "
        "get_pipeline_status signale une etape a relancer."
    )
    SCHEMA = {
        "type": "object",
        "properties": {
            "script": {"type": "string",
                       "description": "Nom du script du pipeline, ou 'pytest'."},
            "test_file": {"type": "string",
                          "description": "pytest: fichier tests/test_xxx.py. "
                                         "Omettre pour toute la suite (~3 min)."},
            "reason": {"type": "string", "description": "Pourquoi lancer cette tache."},
        },
        "required": ["script", "reason"],
    }

    @staticmethod
    def run(params, data, settings=None, session_id=None, registre=None):
        _actions_actives(settings)
        script = champ_texte(params, "script", maxi=80)
        raison = champ_texte(params, "reason", maxi=400)
        if not script or not raison:
            raise ToolInputError("Les parametres script et reason sont requis.")
        try:
            tache = code_ops.preparer_tache(script, champ_texte(params, "test_file", maxi=120))
        except RefusCode as exc:
            raise _refus(exc)
        if registre is None or session_id is None:  # pragma: no cover
            raise ToolInputError("Contexte de session absent.")
        delai = getattr(settings, "task_timeout_seconds", 1800) if settings else 1800
        action = registre.deposer(
            session_id, "tache_executer",
            "Executer %s" % tache["cible"],
            {"script": tache["script"], "cible": tache["cible"],
             "libelle": tache["libelle"], "raison": raison, "delai_max_s": delai},
            {"script": tache["script"], "cible": tache["cible"]},
        )
        return {"statut": "proposition_deposee", "action_id": action.id,
                "tache": tache["libelle"], "cible": tache["cible"],
                "message": ("Proposition deposee. RIEN n'a ete lance: la tache "
                            "attend l'approbation de Laity. Une fois lancee, "
                            "get_task_status donne son resultat.")}


# =============================================================================
class GetTaskStatus:
    NAME = "get_task_status"
    LABEL = "Suivi des propositions"
    PERMISSION = PERMISSION
    DATASETS = ()
    DESCRIPTION = (
        "Etat des propositions de cette session: en attente, en cours "
        "(taches), appliquee, refusee, annulee, avec le resultat (code "
        "retour, duree et fin de sortie d'une tache; fichier et sauvegarde "
        "d'une modification). A utiliser quand Laity demande si une analyse "
        "est terminee ou ce qu'a donne une execution."
    )
    SCHEMA = {"type": "object",
              "properties": {"action_id": {"type": "string",
                                           "description": "Une proposition "
                                                          "precise; omettre "
                                                          "pour toutes."}},
              "required": []}

    @staticmethod
    def run(params, data, session_id=None, registre=None):
        if registre is None or session_id is None:  # pragma: no cover
            raise ToolInputError("Contexte de session absent.")
        cible = champ_texte(params, "action_id", maxi=40)
        vues = registre.lister(session_id)
        if cible:
            vues = [v for v in vues if v["id"] == cible]
            if not vues:
                raise ToolInputError("Proposition inconnue dans cette session: %s" % cible)
        propres = []
        for v in vues[-12:]:
            details = dict(v.get("details") or {})
            details.pop("diff", None)       # deja vu par Laity, inutile ici
            propres.append({"id": v["id"], "type": v["type"], "resume": v["resume"],
                            "statut": v["statut"], "details": details,
                            "resultat": v.get("resultat")})
        return {"propositions": propres, "n": len(propres)}


OUTILS = (ReadCode, ProposeCodeEdit, ProposeTask, GetTaskStatus)
