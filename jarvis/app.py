"""Application FastAPI - backend Jarvis CLIMAT-SEN.

Toutes les routes sont prefixees /jarvis pour que le chemin soit identique en
local (http://localhost:8000/jarvis/health) et derriere nginx
(https://climatsen.innosft.com/jarvis/health). Aucune reecriture d'URL a gerer.

Deux profils circulent dans le jeton signe: "public" (widget anonyme, lecture
seule) et "admin" (Laity, apres authentification par mot de passe). Le profil
determine le modele, le prompt systeme, les outils exposes, le debit autorise
et le fichier de journal.
"""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import __version__, actions, auth, tools
from .claude_client import ClaudeClient
from .config import Settings, get_settings
from .conversations import ConversationStore
from .errors import (AccessDeniedError, InvalidSessionError, JarvisError,
                     PayloadTooLargeError, RateLimitedError)
from .logging_conf import log_event, setup_logging
from .models import (AdminLoginRequest, ChatRequest, ChatSyncResponse,
                     ConversationResponse, HealthResponse, SessionResponse)
from .ratelimit import TokenBucket
from .session import (JetonsRevoques, SessionInfo, issue_token,
                      verify_token)
from .widget_html import render_admin, render_widget

log = logging.getLogger("jarvis.app")

SWEEP_INTERVAL_SECONDS = 300


class AppContext:
    """Dependances du service, regroupees pour etre remplacables en test."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ConversationStore(
            ttl_seconds=settings.conversation_ttl_seconds,
            max_turns=settings.max_turns,
            max_history_chars=settings.max_history_chars,
            max_conversations=settings.max_conversations,
        )
        self.bucket = TokenBucket(
            capacity=settings.rate_limit_capacity,
            refill_per_second=settings.rate_limit_refill_per_second,
        )
        # Debit admin separe: un plafond commun ferait qu'un afflux de
        # visiteurs bloque l'administrateur, et inversement.
        self.admin_bucket = TokenBucket(
            capacity=settings.admin_rate_limit_capacity,
            refill_per_second=settings.admin_rate_limit_refill_per_second,
        )
        # Anti-force brute sur la connexion, par IP. Un seau qui se remplit
        # tres lentement: 5 essais, puis un seul toutes les 3 minutes.
        self.login_bucket = TokenBucket(
            capacity=settings.admin_login_max_attempts,
            refill_per_second=(settings.admin_login_max_attempts
                               / max(1.0, float(settings.admin_login_window_seconds))),
        )
        self.revoques = JetonsRevoques()
        # Propositions de modification en attente d'approbation (Phase 5).
        self.actions = actions.RegistreActions(
            ttl_seconds=settings.action_ttl_seconds)
        self.claude = ClaudeClient(settings)

    def bucket_for(self, profile: str) -> TokenBucket:
        return self.admin_bucket if profile == "admin" else self.bucket

    def tool_specs(self, profile: str):
        """Outils exposes au modele pour ce profil, ou None si desactives."""
        if not self.settings.tools_enabled:
            return None
        return tools.specs_for(profile) or None

    def tool_executor(self, profile: str, session_id: str = ""):
        """Executeur lie au profil ET a la session.

        Les deux sont captures ici, cote serveur: le modele ne peut influencer
        ni l'un ni l'autre en changeant ses arguments. Une proposition deposee
        reste ainsi rattachee a la session qui l'a produite.
        """
        contexte = {"settings": self.settings,
                    "session_id": session_id,
                    "registre": self.actions}

        async def executer(nom, arguments):
            resultat = await tools.execute(
                nom, arguments, profile,
                max_chars=self.settings.tool_result_max_chars,
                contexte=contexte)
            log_event("jarvis.%s" % profile, "tool_call", tool=nom,
                      ok=not resultat.get("is_error"),
                      duration_ms=resultat.get("duration_ms"),
                      chars=resultat.get("chars"))
            return resultat
        return executer


def _sse(event: str, payload: dict) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(payload, ensure_ascii=False))


def _client_ip(request: Request) -> str:
    # nginx transmet X-Forwarded-For; on ne garde que la premiere adresse.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = AppContext(settings)
        sweeper = asyncio.create_task(_sweep_loop(app))
        if settings.tools_enabled and settings.tools_preload:
            # En tache de fond: le service doit repondre a /health tout de
            # suite, meme si la lecture des CSV prend quelques secondes.
            asyncio.create_task(asyncio.to_thread(tools.preload))
        log.info("Jarvis %s demarre (env=%s, modele=%s, outils=%s)",
                 __version__, settings.env, settings.model_public,
                 "actifs" if settings.tools_enabled else "desactives")
        try:
            yield
        finally:
            sweeper.cancel()
            try:
                await sweeper
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="Jarvis CLIMAT-SEN",
        version=__version__,
        docs_url="/jarvis/docs" if settings.env == "dev" else None,
        openapi_url="/jarvis/openapi.json" if settings.env == "dev" else None,
        lifespan=lifespan,
    )

    # En production, widget et backend sont derriere le meme nginx : le CORS ne
    # sert a rien. Il ne compte qu en developpement, ou Streamlit et Jarvis
    # ecoutent sur deux ports differents -- et ou figer une liste de ports est
    # une source de pannes silencieuses : le navigateur bloque la requete, le
    # widget affiche seulement "hors ligne". On accepte donc n importe quel
    # port local en dev, et la liste explicite en production.
    cors = {
        "allow_credentials": False,
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-Jarvis-Session"],
    }
    if settings.env == "dev":
        cors["allow_origin_regex"] = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        cors["allow_origins"] = settings.origins
    else:
        cors["allow_origins"] = settings.origins
    app.add_middleware(CORSMiddleware, **cors)

    # --- gestion d'erreurs ---------------------------------------------------
    @app.exception_handler(JarvisError)
    async def _jarvis_error(request: Request, exc: JarvisError):
        headers = {}
        if isinstance(exc, RateLimitedError):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(status_code=exc.status, content=exc.to_dict(), headers=headers)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # La trace part dans les logs, jamais vers le client.
        log.exception("Erreur non geree sur %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error",
                               "message": "Une erreur interne est survenue."}},
        )

    # --- dependances ---------------------------------------------------------
    def ctx(request: Request) -> AppContext:
        return request.app.state.ctx

    def current_session(
        request: Request,
        x_jarvis_session: str = Header(default=""),
    ) -> SessionInfo:
        c = request.app.state.ctx
        # Le TTL depend du profil ANNONCE par le jeton, mais la signature est
        # verifiee d'abord: un jeton forge "admin" est rejete avant d'atteindre
        # cette ligne. On lit donc le profil en deux temps, avec le TTL le plus
        # long, puis on revalide avec le TTL du profil reellement signe.
        info = verify_token(c.settings.secret_key, x_jarvis_session,
                            max(c.settings.session_ttl_seconds,
                                c.settings.admin_session_ttl_seconds))
        ttl = c.settings.ttl_for(info.profile)
        info = verify_token(c.settings.secret_key, x_jarvis_session, ttl)
        if c.revoques.est_revoque(info.session_id):
            # Deconnexion explicite: le jeton reste cryptographiquement valide
            # jusqu'a son echeance, seule cette liste le neutralise.
            raise InvalidSessionError("Session fermee. Reconnectez-vous.")
        return info

    def require_admin(session: SessionInfo = Depends(current_session)) -> SessionInfo:
        if session.profile != "admin":
            raise AccessDeniedError()
        return session

    def enforce_rate_limit(request: Request, session: SessionInfo) -> None:
        c = request.app.state.ctx
        # Cle combinee: changer de session ne suffit pas a repartir a zero,
        # et une IP partagee (NAT) ne penalise pas tout le monde d'un coup.
        key = "%s|%s" % (session.session_id, _client_ip(request))
        allowed, retry_after = c.bucket_for(session.profile).consume(key)
        if not allowed:
            log_event("jarvis.%s" % session.profile, "rate_limited",
                      session_id=session.session_id, retry_after=retry_after)
            raise RateLimitedError(retry_after=retry_after)

    # --- routes ---------------------------------------------------------------
    @app.get("/jarvis/health", response_model=HealthResponse)
    async def health(c: AppContext = Depends(ctx)):
        configured = bool(c.settings.anthropic_api_key)
        return HealthResponse(
            status="ok" if configured else "degraded",
            version=__version__,
            model=c.settings.model_public,
            configured=configured,
            env=c.settings.env,
            tools=len(c.tool_specs("public") or []),
        )

    @app.post("/jarvis/api/session", response_model=SessionResponse)
    async def create_session(request: Request, c: AppContext = Depends(ctx)):
        token, info = issue_token(c.settings.secret_key, profile="public")
        log_event("jarvis.public", "session_created",
                  session_id=info.session_id, ip=_client_ip(request))
        return SessionResponse(
            token=token,
            session_id=info.session_id,
            profile=info.profile,
            expires_in=c.settings.session_ttl_seconds,
        )

    # --- profil administrateur (Phase 4) --------------------------------------
    @app.post("/jarvis/api/admin/login", response_model=SessionResponse)
    async def admin_login(request: Request, payload: AdminLoginRequest,
                          c: AppContext = Depends(ctx)):
        """Ouvre une session admin. Echoue de la meme maniere dans tous les cas.

        Trois situations donnent la MEME reponse: mot de passe faux, profil
        admin non configure, trop d'essais. Distinguer les deux premieres
        indiquerait a un attaquant si la cible existe; distinguer la troisieme
        lui dirait quand reessayer.
        """
        ip = _client_ip(request)
        autorise, retry_after = c.login_bucket.consume(ip)
        if not autorise:
            log_event("jarvis.admin", "login_bloque", ip=ip, retry_after=retry_after)
            raise RateLimitedError(
                retry_after=retry_after,
                message="Trop de tentatives. Reessayez plus tard.",
            )

        # scrypt bloque ~100 ms: hors de la boucle d'evenements, sinon chaque
        # tentative gele le service pour tout le monde -- ce qui est aussi le
        # levier d'un deni de service a tres bas cout.
        valide = await asyncio.to_thread(
            auth.verifier, payload.password, c.settings.admin_password_hash)

        if not valide:
            log_event("jarvis.admin", "login_refuse", ip=ip,
                      configure=c.settings.admin_enabled)
            raise AccessDeniedError("Identifiants invalides.")

        token, info = issue_token(c.settings.secret_key, profile="admin")
        log_event("jarvis.admin", "login_reussi", ip=ip, session_id=info.session_id)
        return SessionResponse(
            token=token,
            session_id=info.session_id,
            profile=info.profile,
            expires_in=c.settings.admin_session_ttl_seconds,
        )

    @app.post("/jarvis/api/admin/logout")
    async def admin_logout(request: Request,
                           session: SessionInfo = Depends(require_admin),
                           c: AppContext = Depends(ctx)):
        c.revoques.revoquer(session.session_id, c.settings.admin_session_ttl_seconds)
        log_event("jarvis.admin", "logout", ip=_client_ip(request),
                  session_id=session.session_id)
        return {"status": "ok"}

    @app.get("/jarvis/api/admin/me", response_model=SessionResponse)
    async def admin_me(session: SessionInfo = Depends(require_admin),
                       c: AppContext = Depends(ctx)):
        """Verifie qu'une session admin est toujours ouverte.

        La console s'en sert au chargement pour savoir si elle doit afficher
        le formulaire ou le fil de conversation. Ne renvoie JAMAIS le jeton:
        le client possede deja le sien.
        """
        ecoule = int(time.time()) - session.issued_at
        return SessionResponse(
            token="",
            session_id=session.session_id,
            profile=session.profile,
            expires_in=max(0, c.settings.admin_session_ttl_seconds - ecoule),
        )

    # --- propositions de modification (Phase 5) -------------------------------
    @app.get("/jarvis/api/admin/actions")
    async def admin_actions(session: SessionInfo = Depends(require_admin),
                            c: AppContext = Depends(ctx)):
        """Propositions deposees par Jarvis dans CETTE session."""
        return {"actions": c.actions.lister(session.session_id)}

    @app.post("/jarvis/api/admin/actions/{action_id}/approve")
    async def admin_approve(action_id: str, request: Request,
                            session: SessionInfo = Depends(require_admin),
                            c: AppContext = Depends(ctx)):
        """Applique une proposition. SEUL chemin d'ecriture du service.

        Le modele ne peut pas appeler cette route: elle n'est pas un outil,
        elle exige une session admin et elle est declenchee par un clic dans
        la console. Jarvis propose, l'utilisateur approuve, le serveur ecrit.
        """
        try:
            action = c.actions.recuperer(session.session_id, action_id)
        except actions.ActionIntrouvable as exc:
            raise JarvisError(str(exc), code="action_introuvable", status=404)

        try:
            resultat = await asyncio.to_thread(actions.executer, c.settings, action)
        except Exception as exc:
            c.actions.marquer(action, actions.REFUSEE, {"erreur": str(exc)})
            log.exception("Echec de l'action %s", action_id)
            log_event("jarvis.admin", "action_echouee", ip=_client_ip(request),
                      session_id=session.session_id, action_id=action_id,
                      type=action.type)
            raise JarvisError(
                "L'action n'a pas pu etre appliquee: %s" % exc,
                code="action_echouee", status=500)

        c.actions.marquer(action, actions.APPLIQUEE, resultat)
        # Piste d'audit: quoi, par qui, avec quel resultat.
        log_event("jarvis.admin", "action_appliquee", ip=_client_ip(request),
                  session_id=session.session_id, action_id=action_id,
                  type=action.type, cible=resultat.get("fichier"),
                  n_occurrences=resultat.get("n_occurrences"),
                  sauvegarde=resultat.get("sauvegarde"))
        return {"statut": "appliquee", "resultat": resultat}

    @app.post("/jarvis/api/admin/actions/{action_id}/reject")
    async def admin_reject(action_id: str, request: Request,
                           session: SessionInfo = Depends(require_admin),
                           c: AppContext = Depends(ctx)):
        try:
            action = c.actions.recuperer(session.session_id, action_id)
        except actions.ActionIntrouvable as exc:
            raise JarvisError(str(exc), code="action_introuvable", status=404)
        c.actions.marquer(action, actions.REFUSEE)
        log_event("jarvis.admin", "action_refusee", ip=_client_ip(request),
                  session_id=session.session_id, action_id=action_id,
                  type=action.type)
        return {"statut": "refusee"}

    @app.get("/jarvis/api/conversation/{conversation_id}",
             response_model=ConversationResponse)
    async def read_conversation(conversation_id: str,
                                session: SessionInfo = Depends(current_session),
                                c: AppContext = Depends(ctx)):
        """Le widget rappelle cette route apres un remontage d'iframe.

        Streamlit reexecute son script a chaque interaction, ce qui remonte
        l'iframe du composant: sans cette route, le fil disparaitrait a l'ecran.
        """
        conv = c.store.get(conversation_id, session.session_id)
        return ConversationResponse(**conv.to_public_dict())

    def _prepare(request: Request, payload: ChatRequest, session: SessionInfo,
                 c: AppContext):
        """Controles communs aux deux routes de chat, avant tout appel facture."""
        if len(payload.message) > c.settings.max_message_chars:
            raise PayloadTooLargeError(
                "Message trop long (%d caracteres maximum)."
                % c.settings.max_message_chars
            )
        enforce_rate_limit(request, session)
        conv = c.store.get_or_create(payload.conversation_id,
                                     session.session_id, session.profile)
        messages = list(conv.messages) + [{"role": "user", "content": payload.message}]
        return conv, messages

    def _commit(c: AppContext, conv, question: str, answer: str) -> None:
        """N'ecrit dans l'historique qu'une fois une reponse obtenue.

        Si l'appel echoue sans produire un seul caractere, rien n'est ecrit:
        l'utilisateur peut relancer sans se retrouver avec deux questions
        consecutives dans le fil.
        """
        if not answer:
            return
        c.store.append(conv, "user", question)
        c.store.append(conv, "assistant", answer)

    @app.post("/jarvis/api/chat")
    async def chat_stream(request: Request, payload: ChatRequest,
                          session: SessionInfo = Depends(current_session),
                          c: AppContext = Depends(ctx)):
        conv, messages = _prepare(request, payload, session, c)
        preview = payload.message[: c.settings.log_preview_chars] if c.settings.log_prompts else None
        log_event("jarvis.%s" % session.profile, "chat_stream_start",
                  session_id=session.session_id,
                  conversation_id=conv.conversation_id,
                  chars=len(payload.message), question=preview)

        async def generator():
            parts = []
            usage = {}
            outils = []
            try:
                yield _sse("meta", {"conversation_id": conv.conversation_id,
                                    "model": c.claude.model_for(session.profile)})
                flux = c.claude.stream_reply(
                    messages, session.profile,
                    tools=c.tool_specs(session.profile),
                    executor=c.tool_executor(session.profile, session.session_id),
                )
                async for chunk in flux:
                    if isinstance(chunk, dict):
                        if chunk.get("type") == "tools":
                            # Sans ce signal, l'utilisateur voit plusieurs
                            # secondes de silence pendant la lecture des
                            # donnees et croit le widget bloque.
                            for appel in chunk.get("calls", []):
                                outils.append(appel["name"])
                                yield _sse("tool", {
                                    "name": appel["name"],
                                    "label": tools.label_for(appel["name"]),
                                })
                            continue
                        usage = chunk.get("usage", {})
                        continue
                    parts.append(chunk)
                    yield _sse("delta", {"text": chunk})
            except JarvisError as exc:
                # Le flux HTTP a deja commence: impossible de changer le statut,
                # l'erreur passe donc par un evenement SSE.
                _commit(c, conv, payload.message, "".join(parts))
                log_event("jarvis.%s" % session.profile, "chat_stream_error",
                          session_id=session.session_id,
                          conversation_id=conv.conversation_id, code=exc.code)
                yield _sse("error", {"code": exc.code, "message": exc.message})
                return
            except asyncio.CancelledError:
                # Onglet ferme en cours de reponse: on garde le partiel.
                _commit(c, conv, payload.message, "".join(parts))
                raise
            except Exception:
                _commit(c, conv, payload.message, "".join(parts))
                log.exception("Echec du streaming")
                yield _sse("error", {"code": "internal_error",
                                     "message": "Une erreur interne est survenue."})
                return

            answer = "".join(parts)
            _commit(c, conv, payload.message, answer)
            log_event("jarvis.%s" % session.profile, "chat_stream_done",
                      session_id=session.session_id,
                      conversation_id=conv.conversation_id,
                      reply_chars=len(answer), tools=outils or None, **usage)
            yield _sse("done", {"conversation_id": conv.conversation_id, "usage": usage})

        return StreamingResponse(
            generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                # Desactive la bufferisation nginx meme si la conf l'oublie:
                # sans cela le SSE arrive d'un bloc a la fin.
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/jarvis/api/chat/sync", response_model=ChatSyncResponse)
    async def chat_sync(request: Request, payload: ChatRequest,
                        session: SessionInfo = Depends(current_session),
                        c: AppContext = Depends(ctx)):
        conv, messages = _prepare(request, payload, session, c)
        result = await c.claude.complete(
            messages, session.profile,
            tools=c.tool_specs(session.profile),
            executor=c.tool_executor(session.profile, session.session_id),
        )
        _commit(c, conv, payload.message, result["text"])
        log_event("jarvis.%s" % session.profile, "chat_sync_done",
                  session_id=session.session_id,
                  conversation_id=conv.conversation_id,
                  reply_chars=len(result["text"]),
                  tools=result.get("tools_used") or None,
                  **result.get("usage", {}))
        return ChatSyncResponse(
            conversation_id=conv.conversation_id,
            reply=result["text"],
            usage=result.get("usage", {}),
        )

    @app.get("/jarvis/admin", response_class=HTMLResponse)
    async def admin_console(c: AppContext = Depends(ctx)):
        """Console d'administration. La page elle-meme n'est pas un secret.

        Elle ne contient aucune donnee: tout passe par les routes d'API, qui
        exigent un jeton admin. La proteger par mot de passe n'ajouterait rien,
        et empecherait d'afficher un formulaire de connexion.

        En-tetes: pas d'indexation, pas de mise en cache -- une console
        d'administration n'a rien a faire dans un moteur de recherche ni dans
        le cache d'un navigateur partage.
        """
        return HTMLResponse(
            render_admin(api_base="/jarvis"),
            headers={"X-Robots-Tag": "noindex, nofollow",
                     "Cache-Control": "no-store"},
        )

    @app.get("/jarvis/widget.html", response_class=HTMLResponse)
    async def widget(dark: int = 1, c: AppContext = Depends(ctx)):
        """Sert le widget en autonome (meme origine -> base d'API relative).

        Dans Streamlit le widget est injecte en srcdoc avec une base absolue,
        voir scripts/jarvis_widget.py.
        """
        return HTMLResponse(render_widget(api_base="/jarvis", dark_mode=bool(dark)))

    return app


async def _sweep_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
        try:
            removed = app.state.ctx.store.sweep()
            if removed:
                log.info("Purge: %d conversation(s) expiree(s).", removed)
            # Une session revoquee n'a plus a etre retenue une fois son jeton
            # expire de lui-meme: la liste ne grandit donc pas sans fin.
            app.state.ctx.revoques.purger()
            app.state.ctx.actions.purger()
        except Exception:
            log.exception("Echec de la purge des conversations")

# Pas d'instance au niveau module: create_app() lit la configuration et ouvre
# les fichiers de log, ce qui n'a rien a faire a l'import. uvicorn la construit
# via --factory (voir jarvis/README.md et deploy/jarvis.service).
