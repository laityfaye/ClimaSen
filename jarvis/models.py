"""Schemas de requete et de reponse.

La validation Pydantic est la premiere barriere: un message trop long ou vide
est rejete AVANT toute consommation de ressource et tout appel facture.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_MESSAGE_CHARS = 4000  # borne dure du schema; la config peut etre plus basse


class SessionResponse(BaseModel):
    token: str
    session_id: str
    profile: str
    expires_in: int


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: Optional[str] = Field(default=None, max_length=64)

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


class ChatSyncResponse(BaseModel):
    conversation_id: str
    reply: str
    usage: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


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
