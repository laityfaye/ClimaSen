"""Actions en attente d'approbation.

Piece centrale de la Phase 5, et la seule garantie qui tienne.

Le probleme: un outil qui accepterait un parametre `confirmer=true` ne
prouverait rien. C'est le MODELE qui compose les arguments -- il peut mettre
ce drapeau lui-meme, par zele ou parce qu'une instruction bien tournee l'y a
pousse. Une consigne de prompt ne protege pas un fichier.

La reponse: le modele ne peut que DEPOSER une proposition. L'ecriture est
declenchee par une route HTTP distincte, qui exige une session admin et n'est
appelee que par un clic dans la console. Deux chemins separes, deux acteurs
differents: Jarvis propose, l'utilisateur applique, le serveur execute.

Consequence assumee: aucun outil d'action ne modifie quoi que ce soit dans le
tour ou il est appele. C'est exactement l'effet recherche.
"""
import logging
import secrets
import threading
import time

log = logging.getLogger("jarvis.actions")

EN_ATTENTE = "en_attente"
APPLIQUEE = "appliquee"
REFUSEE = "refusee"
EXPIREE = "expiree"
# Phase 10: une tache approuvee tourne en arriere-plan, puis se termine.
EN_COURS = "en_cours"
TERMINEE = "terminee"
ECHOUEE = "echouee"
# Phase 10: une modification de code appliquee puis retablie.
ANNULEE = "annulee"

# Types dont l'execution est lancee en arriere-plan par la route d'approbation.
TYPES_ASYNCHRONES = {"tache_executer"}

TTL_DEFAUT = 1800        # 30 min: une proposition oubliee ne doit pas trainer
MAX_ACTIONS = 100


class ActionIntrouvable(Exception):
    """Identifiant inconnu, deja traite, ou expire."""


class Action:
    def __init__(self, type_action: str, resume: str, details: dict,
                 payload: dict, ttl: int):
        self.id = secrets.token_urlsafe(9)
        self.type = type_action
        self.resume = resume          # une ligne, lisible par un humain
        self.details = details        # ce qui sera montre avant d'approuver
        self.payload = payload        # ce que le serveur executera
        self.cree_le = time.time()
        self.expire_le = self.cree_le + ttl
        self.statut = EN_ATTENTE
        self.resultat = None

    @property
    def expiree(self) -> bool:
        return self.statut == EN_ATTENTE and time.time() > self.expire_le

    def vue_publique(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "resume": self.resume,
            "details": self.details,
            "statut": EXPIREE if self.expiree else self.statut,
            "cree_le": int(self.cree_le),
            "expire_dans": max(0, int(self.expire_le - time.time())),
            "resultat": self.resultat,
        }


class RegistreActions:
    """Propositions en attente, par session admin.

    En memoire: une proposition n'a de sens que dans la conversation qui l'a
    produite, et un redemarrage doit tout annuler plutot que de laisser
    survivre une ecriture approuvable dont plus personne ne se souvient.
    """

    def __init__(self, ttl_seconds: int = TTL_DEFAUT, maximum: int = MAX_ACTIONS):
        self.ttl = ttl_seconds
        self.maximum = maximum
        self._actions = {}            # id -> (session_id, Action)
        self._verrou = threading.Lock()

    def deposer(self, session_id: str, type_action: str, resume: str,
                details: dict, payload: dict) -> Action:
        action = Action(type_action, resume, details, payload, self.ttl)
        with self._verrou:
            self._actions[action.id] = (session_id, action)
            if len(self._actions) > self.maximum:
                self._purger_verrouille()
        log.info("Action deposee: %s (%s)", action.id, type_action)
        return action

    def lister(self, session_id: str) -> list:
        # Piege: _actions est {id: (session_id, action)}. Iterer sur .items()
        # donnait (id, tuple) et comparait l'identifiant d'action a celui de
        # session -- toujours faux, donc aucune proposition n'etait jamais
        # affichee dans la console.
        with self._verrou:
            return [action.vue_publique()
                    for session, action in self._actions.values()
                    if session == session_id]

    def recuperer(self, session_id: str, action_id: str) -> Action:
        """Retourne l'action approuvable, ou leve.

        Le cloisonnement par session est volontaire: une proposition faite
        dans une session ne doit pas pouvoir etre approuvee depuis une autre.
        """
        with self._verrou:
            entree = self._actions.get(action_id)
            if entree is None or entree[0] != session_id:
                raise ActionIntrouvable("Proposition introuvable.")
            _, action = entree
            if action.statut != EN_ATTENTE:
                raise ActionIntrouvable(
                    "Proposition deja traitee (%s)." % action.statut)
            if action.expiree:
                action.statut = EXPIREE
                raise ActionIntrouvable(
                    "Proposition expiree. Redemander a Jarvis.")
            return action

    def obtenir(self, session_id: str, action_id: str) -> Action:
        """L'action de CETTE session, quel que soit son statut (annulation)."""
        with self._verrou:
            entree = self._actions.get(action_id)
            if entree is None or entree[0] != session_id:
                raise ActionIntrouvable("Proposition introuvable.")
            return entree[1]

    def marquer(self, action: Action, statut: str, resultat=None) -> None:
        with self._verrou:
            action.statut = statut
            action.resultat = resultat

    def _purger_verrouille(self) -> None:
        # Une tache en cours ou une modification annulable restent visibles:
        # seules les propositions closes depuis plus d'un TTL sont oubliees.
        limite = time.time() - self.ttl
        perimes = [i for i, (_, a) in self._actions.items()
                   if a.expiree or (a.statut not in (EN_ATTENTE, EN_COURS)
                                    and a.cree_le < limite)]
        for cle in perimes:
            del self._actions[cle]
        if len(self._actions) > self.maximum:
            anciens = sorted(self._actions.items(), key=lambda kv: kv[1][1].cree_le)
            for cle, _ in anciens[: len(self._actions) - self.maximum]:
                del self._actions[cle]

    def purger(self) -> int:
        with self._verrou:
            avant = len(self._actions)
            self._purger_verrouille()
            return avant - len(self._actions)

    def taille(self) -> int:
        with self._verrou:
            return len(self._actions)


# --- execution -----------------------------------------------------------------
# Une action approuvee est executee ICI, cote serveur. Le modele n'intervient
# plus: il ne peut ni choisir le moment, ni modifier la charge entre la
# proposition et l'execution.
def executer(settings, action: Action) -> dict:
    if action.type == "code_modifier":
        from . import code_ops
        return code_ops.appliquer_modification(action.payload)
    if action.type == "document_remplacer":
        from . import documents
        return documents.appliquer_remplacement(
            settings,
            action.payload["document"],
            action.payload["avant"],
            action.payload["apres"],
        )
    raise ActionIntrouvable("Type d'action inconnu: %s" % action.type)
