"""Logs structures JSON, avec separation trafic public / actions admin.

Deux fichiers distincts parce que ce sont deux publics differents: public.jsonl
sert a mesurer l'usage et le cout, admin.jsonl est une piste d'audit (qui a
declenche quel outil, avec quels parametres, pour quel resultat - Phase 5).

Une ligne JSON par evenement: directement exploitable en pandas.
"""
import json
import logging
import logging.handlers
import time
from pathlib import Path

_SENSITIVE = ("api_key", "anthropic_api_key", "token", "secret", "secret_key",
              # Phase 4: la connexion admin manipule un mot de passe. Aucun de
              # ces champs ne doit pouvoir atterrir dans un fichier de log,
              # meme par un appel maladroit a log_event().
              "password", "passwd", "mot_de_passe", "motdepasse", "hash",
              "credential", "authorization")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            for key, value in extra.items():
                if any(s in key.lower() for s in _SENSITIVE):
                    continue  # jamais de secret dans les logs
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _file_handler(path: Path) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        str(path), maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    return handler


def setup_logging(log_dir: str, level: int = logging.INFO) -> None:
    base = Path(log_dir)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger("jarvis")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.propagate = False

    for name, filename in (("jarvis.public", "public.jsonl"),
                           ("jarvis.admin", "admin.jsonl")):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.handlers.clear()
        logger.addHandler(_file_handler(base / filename))
        logger.propagate = True  # remonte aussi sur la console via jarvis


def log_event(logger_name: str, message: str, **context) -> None:
    logging.getLogger(logger_name).info(message, extra={"context": context})
