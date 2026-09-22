"""Jetons de session signes HMAC-SHA256.

Le widget public n'a pas de compte. On lui remet un jeton opaque et signe qui
porte (session_id, profil, date d'emission). Il sert a deux choses:
  1. rattacher une conversation a son emetteur (personne ne lit le fil d'autrui)
  2. donner une cle stable au rate limiting

La signature empeche de forger un session_id: sans le secret serveur, on ne
peut pas fabriquer un jeton accepte. Le profil est DANS le jeton signe, donc un
client ne peut pas s'auto-promouvoir "admin" (prepare la Phase 4).
"""
import base64
import hmac
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from .errors import InvalidSessionError

Profile = Literal["public", "admin"]
VALID_PROFILES = ("public", "admin")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    profile: str
    issued_at: int


def issue_token(secret_key: str, profile: Profile = "public") -> tuple:
    """Retourne (token, SessionInfo)."""
    if profile not in VALID_PROFILES:
        raise ValueError("profil inconnu: %r" % (profile,))
    info = SessionInfo(
        session_id=secrets.token_urlsafe(18),
        profile=profile,
        issued_at=int(time.time()),
    )
    payload = "%s:%s:%d" % (info.session_id, info.profile, info.issued_at)
    body = _b64e(payload.encode("utf-8"))
    sig = _b64e(hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), sha256).digest())
    return "%s.%s" % (body, sig), info


def verify_token(secret_key: str, token: str, ttl_seconds: int) -> SessionInfo:
    """Valide signature puis fraicheur. Leve InvalidSessionError sinon."""
    if not token or not isinstance(token, str) or token.count(".") != 1:
        raise InvalidSessionError()

    body, sig = token.split(".", 1)
    expected = _b64e(hmac.new(secret_key.encode("utf-8"), body.encode("ascii"), sha256).digest())
    # compare_digest: comparaison a temps constant (pas de fuite par timing)
    if not hmac.compare_digest(sig, expected):
        raise InvalidSessionError()

    try:
        session_id, profile, issued_raw = _b64d(body).decode("utf-8").split(":")
        issued_at = int(issued_raw)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        raise InvalidSessionError()

    if profile not in VALID_PROFILES:
        raise InvalidSessionError()
    if time.time() - issued_at > ttl_seconds:
        raise InvalidSessionError("Session expiree. Rechargez la page.")

    return SessionInfo(session_id=session_id, profile=profile, issued_at=issued_at)
