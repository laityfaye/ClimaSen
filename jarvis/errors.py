"""Erreurs applicatives Jarvis.

Chaque erreur porte:
  - code    : identifiant stable, expose au client (utilisable par le widget)
  - status  : code HTTP
  - message : texte en francais, sur pour un affichage public

Aucune erreur ne doit laisser fuir de detail interne (chemin, trace, cle API).
"""


class JarvisError(Exception):
    code = "internal_error"
    status = 500
    message = "Une erreur interne est survenue."
    # Precision technique destinee AU JOURNAL uniquement, jamais au client.
    detail = None

    def __init__(self, message=None, code=None, status=None):
        super().__init__(message or self.message)
        if message:
            self.message = message
        if code:
            self.code = code
        if status:
            self.status = status

    def to_dict(self):
        return {"error": {"code": self.code, "message": self.message}}


class ConfigurationError(JarvisError):
    code = "configuration_error"
    status = 500
    message = "Le service est mal configure."


class InvalidSessionError(JarvisError):
    code = "invalid_session"
    status = 401
    message = "Session invalide ou expiree. Rechargez la page."


class AccessDeniedError(JarvisError):
    code = "access_denied"
    status = 403
    message = "Acces refuse a cette conversation."


class ConversationNotFoundError(JarvisError):
    code = "conversation_not_found"
    status = 404
    message = "Conversation introuvable ou expiree."


class NotFoundError(JarvisError):
    """Ressource inconnue, expiree ou d'une autre session: meme reponse dans
    les trois cas, pour ne pas confirmer l'existence d'un identifiant."""
    code = "not_found"
    status = 404
    message = "Ressource introuvable."


class RateLimitedError(JarvisError):
    code = "rate_limited"
    status = 429
    message = "Trop de messages envoyes. Patientez quelques instants."

    def __init__(self, retry_after=30, **kwargs):
        super().__init__(**kwargs)
        self.retry_after = int(retry_after)


class PayloadTooLargeError(JarvisError):
    code = "payload_too_large"
    status = 413
    message = "Message trop long."


class UpstreamError(JarvisError):
    """Echec de l'appel a l'API Claude, deja traduit en message public."""

    code = "upstream_error"
    status = 502
    message = "L'assistant est momentanement indisponible. Reessayez dans un instant."
