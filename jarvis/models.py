"""Schemas de requete et de reponse.

La validation Pydantic est la premiere barriere: un message trop long ou vide
est rejete AVANT toute consommation de ressource et tout appel facture.
"""
import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .page_view import VueDashboard

MAX_MESSAGE_CHARS = 4000  # borne dure du schema; la config peut etre plus basse
MAX_PAGE_CONTEXT_CHARS = 2000  # voir jarvis/page_context.py


class SessionResponse(BaseModel):
    token: str
    session_id: str
    profile: str
    expires_in: int


class AdminLoginRequest(BaseModel):
    # Borne haute large mais finie: scrypt travaille sur ce que le client
    # envoie, un champ non borne offrirait un deni de service a bon marche.
    password: str = Field(min_length=1, max_length=256)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    # Ce que l'utilisateur a sous les yeux dans le dashboard (Phase 7). Le
    # contenu est filtre par jarvis.page_context; ici on ne borne que la
    # taille, pour qu'un client ne puisse pas faire parser un objet enorme.
    page_context: Optional[Dict[str, Any]] = None
    # Capture de la page (Phase 9): titres, indicateurs, donnees et images
    # des graphiques. Bornee champ par champ par VueDashboard.
    page_view: Optional[VueDashboard] = None

    @field_validator("page_context")
    @classmethod
    def _borne_contexte(cls, v):
        if v is None:
            return None
        if len(json.dumps(v, default=str)) > MAX_PAGE_CONTEXT_CHARS:
            raise ValueError("Contexte de page trop volumineux.")
        return v

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Le message ne peut pas etre vide.")
        return v

    @field_validator("conversation_id")
    @classmethod
    def _clean_id(cls, v):
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not v.isalnum():
            raise ValueError("conversation_id invalide.")
        return v


class FigureRef(BaseModel):
    id: str
    titre: str = ""
    sous_titre: str = ""


class ChatSyncResponse(BaseModel):
    conversation_id: str
    reply: str
    usage: dict = Field(default_factory=dict)
    figures: List[FigureRef] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    figures: List[FigureRef] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    conversation_id: str
    profile: str
    messages: List[ChatMessage]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    model: str
    configured: bool
    env: str
    tools: int = 0
