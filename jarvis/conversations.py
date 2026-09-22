"""Historique de conversation, cote serveur.

Decision d'architecture: l'historique vit sur le serveur, pas chez le client.
Si le client renvoyait tout le fil a chaque tour, n'importe qui pourrait pousser
200 000 tokens dans une requete et faire exploser la facture. Ici le client
n'envoie qu'un conversation_id et un message; le serveur decide de ce qui part
vers l'API Claude, sous trois plafonds: nombre de tours, taille totale, TTL.

Stockage en memoire pour la Phase 1 (un process, redemarrage = fils perdus,
ce qui est acceptable pour un widget public). Passage a SQLite/Redis documente
dans jarvis/README.md.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .errors import AccessDeniedError, ConversationNotFoundError


@dataclass
class Conversation:
    conversation_id: str
    session_id: str
    profile: str
    created_at: float
    last_used_at: float
    messages: List[dict] = field(default_factory=list)

    def to_public_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "profile": self.profile,
            "created_at": self.created_at,
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in self.messages
                if m["role"] in ("user", "assistant")
            ],
        }


class ConversationStore:
    def __init__(self, ttl_seconds: int, max_turns: int, max_history_chars: int,
                 max_conversations: int = 2000):
        self.ttl_seconds = ttl_seconds
        self.max_turns = max_turns
        self.max_history_chars = max_history_chars
        self.max_conversations = max_conversations
        self._data: Dict[str, Conversation] = {}
        self._lock = threading.Lock()

    # --- cycle de vie --------------------------------------------------------
    def _expired(self, conv: Conversation, now: float) -> bool:
        return (now - conv.last_used_at) > self.ttl_seconds

    def sweep(self) -> int:
        now = time.time()
        with self._lock:
            dead = [k for k, c in self._data.items() if self._expired(c, now)]
            for k in dead:
                del self._data[k]
            # Garde-fou memoire: si ca deborde encore, on jette les plus anciens.
            if len(self._data) > self.max_conversations:
                oldest = sorted(self._data.items(), key=lambda kv: kv[1].last_used_at)
                for k, _ in oldest[: len(self._data) - self.max_conversations]:
                    del self._data[k]
                    dead.append(k)
            return len(dead)

    # --- acces ---------------------------------------------------------------
    def get(self, conversation_id: str, session_id: str) -> Conversation:
        """Recupere un fil en verifiant qu'il appartient bien a cette session."""
        now = time.time()
        with self._lock:
            conv = self._data.get(conversation_id)
            if conv is None or self._expired(conv, now):
                self._data.pop(conversation_id, None)
                raise ConversationNotFoundError()
            if conv.session_id != session_id:
                # On ne dit pas "elle existe mais n'est pas a vous" par hasard:
                # c'est bien un 403, la session est valide mais pas proprietaire.
                raise AccessDeniedError()
            conv.last_used_at = now
            return conv

    def create(self, session_id: str, profile: str) -> Conversation:
        now = time.time()
        conv = Conversation(
            conversation_id=uuid.uuid4().hex,
            session_id=session_id,
            profile=profile,
            created_at=now,
            last_used_at=now,
        )
        with self._lock:
            self._data[conv.conversation_id] = conv
        return conv

    def get_or_create(self, conversation_id: Optional[str], session_id: str,
                      profile: str) -> Conversation:
        """Un id inconnu ou expire redonne un fil neuf plutot qu'une erreur:
        le widget ne doit pas casser parce que le serveur a redemarre."""
        if not conversation_id:
            return self.create(session_id, profile)
        try:
            return self.get(conversation_id, session_id)
        except ConversationNotFoundError:
            return self.create(session_id, profile)
        # AccessDeniedError remonte volontairement: c'est une tentative d'acces.

    # --- ecriture ------------------------------------------------------------
    def append(self, conv: Conversation, role: str, content: str) -> None:
        if role not in ("user", "assistant"):
            raise ValueError("role invalide: %r" % (role,))
        with self._lock:
            conv.messages.append({"role": role, "content": content})
            conv.last_used_at = time.time()
            self._trim_locked(conv)

    def _trim_locked(self, conv: Conversation) -> None:
        """Applique les plafonds, en gardant un historique valide pour l'API.

        Contrainte API: le premier message envoye doit avoir le role 'user'.
        On coupe donc toujours par paires depuis le debut.
        """
        max_messages = self.max_turns * 2
        if len(conv.messages) > max_messages:
            conv.messages = conv.messages[-max_messages:]

        while conv.messages and conv.messages[0]["role"] != "user":
            conv.messages.pop(0)

        def total() -> int:
            return sum(len(m["content"]) for m in conv.messages)

        # On retire par paires tant que l'historique depasse le plafond, mais on
        # garde toujours au moins le dernier tour, sinon la question en cours
        # disparaitrait.
        while total() > self.max_history_chars and len(conv.messages) > 2:
            del conv.messages[0:2]
            while conv.messages and conv.messages[0]["role"] != "user":
                conv.messages.pop(0)

    # --- introspection (sante / tests) --------------------------------------
    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def reset(self) -> None:
        with self._lock:
            self._data.clear()
