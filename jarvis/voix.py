"""Synthese vocale neuronale (voix de Jarvis).

La voix du navigateur (speechSynthesis) depend du systeme du visiteur: sous
Windows elle sonne robotique. On synthetise donc cote serveur avec edge-tts,
les voix neuronales Microsoft deja utilisees par JARVIS-pro
(fr-FR-HenriNeural), sans cle ni cout.

edge-tts s'appuie sur le service en ligne de Microsoft Edge, sans contrat de
service: il peut changer ou disparaitre. Le widget retombe alors de lui-meme
sur la voix du navigateur -- une panne ici ne rend jamais Jarvis muet.

Le texte envoye est deja celui qu'on a affiche au visiteur: aucune donnee
nouvelle ne sort du serveur.
"""
import asyncio
import logging

from .errors import UpstreamError

log = logging.getLogger("jarvis.voix")

try:                                   # dependance optionnelle
    import edge_tts
except ImportError:                    # pragma: no cover - selon l'installation
    edge_tts = None

# Un appel = un morceau de reponse (le widget decoupe par phrases). Borne
# basse: un morceau court demarre plus vite, et le service refuse les textes
# trop longs.
MAX_CHARS = 500
DELAI_SECONDES = 20.0


def disponible(settings) -> bool:
    return bool(settings.tts_enabled and edge_tts is not None)


async def _collecter(texte: str, voix: str, debit: str) -> bytes:
    audio = bytearray()
    flux = edge_tts.Communicate(texte, voice=voix, rate=debit)
    async for morceau in flux.stream():
        if morceau.get("type") == "audio":
            audio.extend(morceau["data"])
    return bytes(audio)


async def synthetiser(texte: str, voix: str, debit: str) -> bytes:
    """MP3 de `texte`. Leve UpstreamError si le service ne repond pas."""
    if edge_tts is None:
        raise UpstreamError("Synthese vocale indisponible sur ce serveur.")
    try:
        audio = await asyncio.wait_for(_collecter(texte, voix, debit),
                                       timeout=DELAI_SECONDES)
    except asyncio.TimeoutError:
        log.warning("Synthese vocale: delai depasse (%d caracteres).", len(texte))
        raise UpstreamError("La synthese vocale ne repond pas.")
    except Exception as exc:
        log.warning("Synthese vocale en echec: %s", type(exc).__name__)
        raise UpstreamError("La synthese vocale a echoue.")
    if not audio:
        raise UpstreamError("La synthese vocale n'a rien produit.")
    return audio
