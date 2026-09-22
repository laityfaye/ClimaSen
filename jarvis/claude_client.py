"""Enveloppe autour du SDK Anthropic.

Isole tout ce qui touche a l'API Claude derriere une interface reduite, pour
trois raisons:
  - les tests mockent cette classe, jamais le SDK en profondeur
  - le choix du modele suit le profil (public/admin), en un seul endroit
  - les exceptions du SDK sont traduites en messages publics surs

Mise en cache du prompt: le bloc system porte cache_control ephemeral. Le
prefixe est identique d'une requete a l'autre, donc facture ~10% apres le
premier appel. C'est le principal levier de cout du profil public. L'ordre du
prefixe est tools -> system -> messages: la cesure posee sur system couvre donc
AUSSI les definitions d'outils, sans second point de cache a declarer.

Phase 2: boucle d'outils. Quand le modele repond stop_reason="tool_use", les
outils demandes sont executes et leurs resultats renvoyes dans un nouvel appel,
jusqu'a une reponse en texte ou jusqu'au plafond de tours.
"""
import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator, List, Optional

import anthropic

from .errors import UpstreamError

log = logging.getLogger("jarvis.claude")

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_system_prompt(name: str = "system_public") -> str:
    path = PROMPTS_DIR / (name + ".md")
    return path.read_text(encoding="utf-8").strip()


def _translate(exc: Exception) -> UpstreamError:
    """Traduit une exception SDK en erreur publique.

    Le message technique part dans les logs, jamais vers le client: il peut
    contenir des details d'infrastructure.
    """
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        log.error("Cle API Anthropic refusee ou sans permissions.")
        return UpstreamError(
            "L'assistant n'est pas correctement configure. Contactez l'administrateur.",
            code="upstream_auth",
        )
    if isinstance(exc, anthropic.RateLimitError):
        log.warning("Quota API Anthropic atteint (429).")
        return UpstreamError(
            "L'assistant recoit trop de demandes. Reessayez dans une minute.",
            code="upstream_rate_limited",
        )
    if isinstance(exc, anthropic.APITimeoutError):
        log.warning("Delai depasse sur l'API Anthropic.")
        return UpstreamError(
            "La reponse a mis trop de temps. Reformulez ou reessayez.",
            code="upstream_timeout",
        )
    if isinstance(exc, anthropic.APIConnectionError):
        log.warning("Connexion impossible a l'API Anthropic: %s", exc)
        return UpstreamError(
            "L'assistant est injoignable pour le moment. Reessayez dans un instant.",
            code="upstream_unreachable",
        )
    if isinstance(exc, anthropic.BadRequestError):
        log.error("Requete refusee par l'API Anthropic: %s", exc)
        if "workspace" in str(exc).lower():
            # Erreur de configuration, pas de contenu : on la distingue pour
            # que l administrateur sache quoi corriger.
            log.error(
                "La cle API n est pas rattachee a un workspace. "
                "Renseignez ANTHROPIC_WORKSPACE_ID dans .env, ou utilisez une "
                "cle API scopee a un workspace."
            )
            return UpstreamError(
                "L'assistant n'est pas correctement configure. "
                "Contactez l'administrateur.",
                code="upstream_workspace_required",
            )
        return UpstreamError(
            "Cette demande n'a pas pu etre traitee.",
            code="upstream_bad_request",
        )
    if isinstance(exc, anthropic.APIStatusError):
        log.error("Erreur API Anthropic %s: %s", getattr(exc, "status_code", "?"), exc)
        return UpstreamError(code="upstream_error")

    log.exception("Erreur inattendue lors de l'appel a l'API Claude.")
    return UpstreamError(code="upstream_error")


def _usage_dict(message) -> dict:
    usage = getattr(message, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def _cumuler_usage(total: dict, ajout: dict) -> dict:
    """Somme les compteurs de tous les tours d'outils.

    Sans cela, public.jsonl ne consignerait que le dernier appel et le cout
    mesure serait sous-estime d'un facteur egal au nombre de tours.
    """
    for cle, valeur in (ajout or {}).items():
        total[cle] = total.get(cle, 0) + (valeur or 0)
    return total


def _serialiser_blocs(contenu) -> list:
    """Convertit les blocs d'une reponse en blocs renvoyables a l'API.

    Les blocs thinking doivent etre repris tels quels, signature comprise:
    l'API refuse un tour d'assistant dont la reflexion a ete amputee alors
    qu'il contient un tool_use.
    """
    blocs = []
    for bloc in contenu:
        type_bloc = getattr(bloc, "type", None)
        if type_bloc == "text":
            texte = getattr(bloc, "text", "")
            if texte.strip():
                blocs.append({"type": "text", "text": texte})
        elif type_bloc == "tool_use":
            blocs.append({"type": "tool_use", "id": bloc.id,
                          "name": bloc.name, "input": bloc.input})
        elif type_bloc == "thinking":
            blocs.append({"type": "thinking", "thinking": bloc.thinking,
                          "signature": getattr(bloc, "signature", None)})
        elif type_bloc == "redacted_thinking":
            blocs.append({"type": "redacted_thinking", "data": bloc.data})
    return blocs


def _blocs_outils(message) -> list:
    return [bloc for bloc in getattr(message, "content", [])
            if getattr(bloc, "type", None) == "tool_use"]


class ClaudeClient:
    def __init__(self, settings, client: Optional[object] = None):
        self.settings = settings
        self._client = client  # injectable pour les tests
        self._system_cache = {}

    @property
    def client(self):
        if self._client is None:
            if not self.settings.anthropic_api_key:
                raise UpstreamError(
                    "L'assistant n'est pas configure (cle API absente).",
                    code="upstream_not_configured",
                )
            entetes = {}
            workspace = getattr(self.settings, "anthropic_workspace_id", "")
            if workspace:
                # Une cle API non scopee exige cet en-tete, sinon l organisation
                # repond 400 "not scoped to a workspace".
                entetes["anthropic-workspace-id"] = workspace
            self._client = anthropic.AsyncAnthropic(
                api_key=self.settings.anthropic_api_key,
                timeout=self.settings.request_timeout_seconds,
                # Le SDK reessaie seul 429 / 5xx / erreurs reseau, backoff exponentiel.
                max_retries=self.settings.max_retries,
                default_headers=entetes or None,
            )
        return self._client

    # --- configuration de la requete ----------------------------------------
    def model_for(self, profile: str) -> str:
        if profile == "admin":
            return self.settings.model_admin
        return self.settings.model_public

    def system_for(self, profile: str) -> str:
        name = "system_public"  # le prompt admin arrive en Phase 4
        if name not in self._system_cache:
            self._system_cache[name] = load_system_prompt(name)
        return self._system_cache[name]

    def _request_kwargs(self, messages: List[dict], profile: str,
                        tools: Optional[List[dict]] = None) -> dict:
        thinking = {"type": "adaptive"}
        if self.settings.thinking_public != "adaptive":
            thinking = {"type": "disabled"}
        kwargs = {
            "model": self.model_for(profile),
            "max_tokens": self.settings.max_tokens_public,
            "system": [{
                "type": "text",
                "text": self.system_for(profile),
                "cache_control": {"type": "ephemeral"},
            }],
            "messages": messages,
            "output_config": {"effort": self.settings.effort_public},
            "thinking": thinking,
        }
        if tools:
            kwargs["tools"] = tools
        return kwargs

    # --- boucle d'outils ------------------------------------------------------
    async def _executer_outils(self, blocs, executor) -> list:
        """Execute les outils demandes et compose le tour "user" de retour.

        Les appels partent en parallele: le modele en demande parfois deux d'un
        coup (un indice et une correlation), et les enchainer doublerait
        l'attente pour rien.
        """
        resultats = await asyncio.gather(
            *[executor(bloc.name, bloc.input) for bloc in blocs]
        )
        contenu = []
        for bloc, resultat in zip(blocs, resultats):
            contenu.append({
                "type": "tool_result",
                "tool_use_id": bloc.id,
                "content": resultat.get("content", ""),
                "is_error": bool(resultat.get("is_error")),
            })
        return contenu

    # --- appels --------------------------------------------------------------
    async def stream_reply(self, messages: List[dict], profile: str = "public",
                           tools: Optional[List[dict]] = None,
                           executor=None) -> AsyncIterator[object]:
        """Diffuse la reponse fragment par fragment, outils compris.

        Produit:
          - des chaines de texte, au fil de la generation;
          - des dict {"type": "tools", "calls": [...]} juste avant d'executer
            des outils, pour que l'interface puisse le signaler;
          - un dernier dict portant l'usage cumule et le stop_reason.
        """
        conversation = list(messages)
        usage_total = {}
        outils_appeles = []
        stop_reason = None
        tours_max = self.settings.max_tool_rounds if (tools and executor) else 0

        for tour in range(tours_max + 1):
            # Au dernier tour on retire les outils: le modele doit conclure en
            # texte plutot que de redemander une lecture qu'on n'executerait pas.
            outils_du_tour = tools if (tools and executor and tour < tours_max) else None
            kwargs = self._request_kwargs(conversation, profile, tools=outils_du_tour)
            final = None
            try:
                async with self.client.messages.stream(**kwargs) as stream:
                    async for chunk in stream.text_stream:
                        yield chunk
                    final = await stream.get_final_message()
            except UpstreamError:
                raise
            except Exception as exc:
                raise _translate(exc) from exc

            _cumuler_usage(usage_total, _usage_dict(final))
            stop_reason = getattr(final, "stop_reason", None)

            blocs = _blocs_outils(final) if outils_du_tour else []
            if stop_reason != "tool_use" or not blocs:
                break

            yield {"type": "tools",
                   "calls": [{"name": b.name, "id": b.id} for b in blocs]}
            outils_appeles.extend(b.name for b in blocs)

            conversation.append({"role": "assistant",
                                 "content": _serialiser_blocs(final.content)})
            conversation.append({"role": "user",
                                 "content": await self._executer_outils(blocs, executor)})

        yield {
            "type": "done",
            "usage": usage_total,
            "stop_reason": stop_reason,
            "tools_used": outils_appeles,
        }

    async def complete(self, messages: List[dict], profile: str = "public",
                       tools: Optional[List[dict]] = None,
                       executor=None) -> dict:
        """Version non streamee: repli du widget et chemin de test."""
        conversation = list(messages)
        usage_total = {}
        outils_appeles = []
        textes = []
        stop_reason = None
        tours_max = self.settings.max_tool_rounds if (tools and executor) else 0

        for tour in range(tours_max + 1):
            outils_du_tour = tools if (tools and executor and tour < tours_max) else None
            kwargs = self._request_kwargs(conversation, profile, tools=outils_du_tour)
            try:
                response = await self.client.messages.create(**kwargs)
            except UpstreamError:
                raise
            except Exception as exc:
                raise _translate(exc) from exc

            _cumuler_usage(usage_total, _usage_dict(response))
            stop_reason = getattr(response, "stop_reason", None)
            textes.extend(bloc.text for bloc in response.content
                          if getattr(bloc, "type", None) == "text")

            blocs = _blocs_outils(response) if outils_du_tour else []
            if stop_reason != "tool_use" or not blocs:
                break

            outils_appeles.extend(bloc.name for bloc in blocs)
            conversation.append({"role": "assistant",
                                 "content": _serialiser_blocs(response.content)})
            conversation.append({"role": "user",
                                 "content": await self._executer_outils(blocs, executor)})

        return {
            "text": "".join(textes),
            "usage": usage_total,
            "stop_reason": stop_reason,
            "tools_used": outils_appeles,
        }
