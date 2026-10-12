"""Synthese vocale neuronale (voix d'Iris).

La voix du navigateur (speechSynthesis) depend du systeme du visiteur: sous
Windows elle sonne robotique. On synthetise donc cote serveur avec edge-tts,
les voix neuronales Microsoft (comme JARVIS-pro), ici
fr-FR-DeniseNeural, sans cle ni cout.

edge-tts s'appuie sur le service en ligne de Microsoft Edge, sans contrat de
service: il peut changer ou disparaitre. Le widget retombe alors de lui-meme
sur la voix du navigateur -- une panne ici ne rend jamais Iris muette.

Le texte envoye est deja celui qu'on a affiche au visiteur: aucune donnee
nouvelle ne sort du serveur.
"""
import asyncio
import logging
from collections import OrderedDict

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
DELAI_SECONDES = 20.0          # budget total d'un morceau, essais compris
DELAI_ESSAI = 8.0              # un essai bloque au-dela est abandonne

# Le service de Microsoft refuse les connexions simultanees en rafale
# (mesure du 12/10/2026: 20 phrases en parallele -> 9 refus
# WSServerHandshakeError, et la premiere phrase a 6,4 s, au-dela de la garde
# de 5 s du widget, qui passait alors a la voix du navigateur). D'ou une file
# a 2 connexions pour tout le serveur et de nouveaux essais espaces: avec
# eux, 20/20 phrases passent.
CONNEXIONS_MAX = 2
ESSAIS = 3
_file = None                   # asyncio.Semaphore, cree dans la boucle

# Accueil, narration de soutenance: les memes phrases reviennent.
_CACHE_MAX = 64
_cache = OrderedDict()


def disponible(settings) -> bool:
    return bool(settings.tts_enabled and edge_tts is not None)


async def _collecter(texte: str, voix: str, debit: str) -> bytes:
    audio = bytearray()
    flux = edge_tts.Communicate(texte, voice=voix, rate=debit)
    async for morceau in flux.stream():
        if morceau.get("type") == "audio":
            audio.extend(morceau["data"])
    return bytes(audio)


class _Echec(Exception):
    pass


async def _essais(texte: str, voix: str, debit: str) -> bytes:
    global _file
    if _file is None:
        _file = asyncio.Semaphore(CONNEXIONS_MAX)
    derniere = None
    for k in range(ESSAIS):
        if k:
            await asyncio.sleep(0.4 * k)
        try:
            async with _file:
                audio = await asyncio.wait_for(_collecter(texte, voix, debit),
                                               timeout=DELAI_ESSAI)
            if audio:
                return audio
            derniere = "audio vide"
        except asyncio.TimeoutError:
            derniere = "delai"
        except Exception as exc:
            derniere = type(exc).__name__
        log.info("Synthese vocale: essai %d/%d en echec (%s).", k + 1, ESSAIS, derniere)
    raise _Echec(derniere)


async def synthetiser(texte: str, voix: str, debit: str) -> bytes:
    """MP3 de `texte`. Leve UpstreamError si le service ne repond pas."""
    if edge_tts is None:
        raise UpstreamError("Synthese vocale indisponible sur ce serveur.")
    cle = (texte, voix, debit)
    if cle in _cache:
        _cache.move_to_end(cle)
        return _cache[cle]
    try:
        audio = await asyncio.wait_for(_essais(texte, voix, debit),
                                       timeout=DELAI_SECONDES)
    except asyncio.TimeoutError:
        log.warning("Synthese vocale: delai depasse (%d caracteres).", len(texte))
        raise UpstreamError("La synthese vocale ne repond pas.")
    except _Echec as exc:
        log.warning("Synthese vocale en echec apres %d essais: %s", ESSAIS, exc)
        raise UpstreamError("La synthese vocale a echoue.")
    _cache[cle] = audio
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return audio
