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
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               Response, StreamingResponse)

from . import (__version__, actions, auth, code_ops, elevation, figures,
               page_context, page_view, soutenance, tools, voix)
from .tools import dataset as tools_dataset
from .claude_client import ClaudeClient
from .config import Settings, get_settings
from .conversations import ConversationStore
from .errors import (AccessDeniedError, InvalidSessionError, JarvisError,
                     NotFoundError, PayloadTooLargeError, RateLimitedError)
from .logging_conf import log_event, setup_logging
from .models import (AdminLoginRequest, ChatRequest, ChatSyncResponse,
                     ConversationResponse, HealthResponse, SessionResponse,
                     TtsRequest)
from .ratelimit import TokenBucket
from .session import (JetonsRevoques, SessionInfo, issue_token,
                      verify_token)
from .widget_html import render_admin, render_widget

log = logging.getLogger("jarvis.app")

SWEEP_INTERVAL_SECONDS = 300

# Fichier du mode J.A.R.V.I.S plein ecran: l'orbe de la version BUREAU de
# JARVIS-pro (frontend/src/orb.ts) assemblee avec three.js 0.170 (MIT). Liste
# FERMEE: la route ne sert rien d'autre, le nom demande n'est jamais
# transforme en chemin.
DOSSIER_HUD = Path(__file__).resolve().parent / "hud"
FICHIERS_HUD = {"jarvis-orb.js": DOSSIER_HUD / "jarvis-orb.js"}
# Plafond du corps d'une requete. Une question avec trois images de
# graphiques (Phase 9) pese ~1,3 Mo; au-dela, c'est un abus.
MAX_BODY_BYTES = 2_500_000


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
        # Plafonds par ADRESSE, distincts des plafonds par session: un jeton
        # de session s'obtient sans authentification, il ne peut donc pas etre
        # le seul point d'ancrage du debit.
        self.ip_bucket = TokenBucket(
            capacity=settings.rate_limit_ip_capacity,
            refill_per_second=settings.rate_limit_ip_refill_per_second,
        )
        self.admin_ip_bucket = TokenBucket(
            capacity=settings.admin_rate_limit_capacity * 2,
            refill_per_second=settings.admin_rate_limit_refill_per_second * 2,
        )
        # Synthese vocale: par ADRESSE, comme le plafond qu'on ne contourne
        # pas en changeant de session. Seau distinct du chat: une reponse
        # lue a voix haute fait plusieurs appels.
        # Mode soutenance: etapes gratuites (pas de modele), mais chacune
        # lit les donnees et depose une figure. Seau distinct du chat pour ne
        # pas amputer le quota de questions du jury.
        self.soutenance_bucket = TokenBucket(capacity=30, refill_per_second=0.5)
        self.tts_bucket = TokenBucket(
            capacity=settings.tts_rate_limit_capacity,
            refill_per_second=settings.tts_rate_limit_refill_per_second,
        )
        self.revoques = JetonsRevoques()
        # Propositions de modification en attente d'approbation (Phase 5).
        self.actions = actions.RegistreActions(
            ttl_seconds=settings.action_ttl_seconds)
        # Figures produites par make_figure (Phase 8): specifications en
        # memoire, rendues a la demande. Meme duree de vie que les fils.
        self.figures = figures.FigureStore(
            ttl_seconds=settings.conversation_ttl_seconds)
        # Taches lancees apres approbation (Phase 10): une a la fois.
        self.taches = code_ops.Taches(secrets=(
            settings.anthropic_api_key, settings.secret_key,
            getattr(settings, "admin_password_hash", "")))
        self.claude = ClaudeClient(settings)

    def bucket_for(self, profile: str) -> TokenBucket:
        return self.admin_bucket if profile == "admin" else self.bucket

    def ip_bucket_for(self, profile: str) -> TokenBucket:
        return self.admin_ip_bucket if profile == "admin" else self.ip_bucket

    def tool_specs(self, profile: str):
        """Outils exposes au modele pour ce profil, ou None si desactives."""
        if not self.settings.tools_enabled:
            return None
        return tools.specs_for(profile) or None

    def tool_executor(self, profile: str, session_id: str = "",
                      figures_produites=None, navigations=None):
        """Executeur lie au profil ET a la session.

        Les deux sont captures ici, cote serveur: le modele ne peut influencer
        ni l'un ni l'autre en changeant ses arguments. Une proposition deposee
        reste ainsi rattachee a la session qui l'a produite.
        """
        contexte = {"settings": self.settings,
                    "session_id": session_id,
                    "registre": self.actions,
                    "figures": self.figures}

        async def executer(nom, arguments):
            resultat = await tools.execute(
                nom, arguments, profile,
                max_chars=self.settings.tool_result_max_chars,
                contexte=contexte)
            log_event("jarvis.%s" % profile, "tool_call", tool=nom,
                      ok=not resultat.get("is_error"),
                      duration_ms=resultat.get("duration_ms"),
                      chars=resultat.get("chars"))
            if (figures_produites is not None and nom in OUTILS_FIGURES
                    and not resultat.get("is_error")):
                _noter_figure(resultat, figures_produites)
            if (navigations is not None and nom in OUTILS_NAVIGATION
                    and not resultat.get("is_error")):
                _noter_navigation(resultat, navigations)
            return resultat
        return executer


# Outils qui deposent une figure a annoncer au widget.
OUTILS_FIGURES = ("make_figure", "show_map", "recompute_correlation",
                  "animate_sst_event")
# Outil dont le resultat porte une consigne de navigation pour le dashboard.
OUTILS_NAVIGATION = ("navigate_dashboard",)


def _noter_figure(resultat: dict, figures_produites: list) -> None:
    """Releve la figure deposee par make_figure pour l'annoncer au widget.

    Lu dans le RESULTAT de l'outil (produit par notre code), jamais dans le
    texte du modele: un identifiant invente par le modele n'atteint pas le
    widget.
    """
    try:
        charge = json.loads(resultat.get("content") or "{}")
    except ValueError:
        return
    if charge.get("figure_id"):
        figures_produites.append({"id": charge["figure_id"],
                                  "titre": charge.get("titre", ""),
                                  "sous_titre": charge.get("sous_titre", ""),
                                  # Une carte s'affiche en grand dans le HUD.
                                  "carte": bool(charge.get("carte"))})
    # Figure secondaire d'un outil de calcul (recompute_correlation).
    secondaire = charge.get("figure")
    if isinstance(secondaire, dict) and secondaire.get("figure_id"):
        figures_produites.append({"id": secondaire["figure_id"],
                                  "titre": secondaire.get("titre", ""),
                                  "sous_titre": secondaire.get("sous_titre", ""),
                                  "carte": False})


def _noter_navigation(resultat: dict, navigations: list) -> None:
    """Releve la consigne de navigation, deja validee par l'outil.

    Comme pour les figures, on la lit dans le RESULTAT de notre outil, jamais
    dans le texte du modele.
    """
    try:
        charge = json.loads(resultat.get("content") or "{}")
    except ValueError:
        return
    nav = charge.get("navigation")
    if isinstance(nav, dict) and nav.get("page"):
        navigations.append({"page": nav["page"], "filtres": nav.get("filtres") or {}})


class LimiteCorps:
    """Refuse un corps de requete trop gros, en COMPTANT les octets recus.

    Depuis la Phase 9, une question peut porter des images: la limite existe
    donc dans l'application, pas seulement dans nginx (dont la configuration
    serveur autorise 500 Mo pour le dashboard).

    Phase 12: la premiere version ne lisait que l'en-tete Content-Length. Un
    corps envoye en "chunked", sans cet en-tete, passait et etait lu en
    entier en memoire (5 Mo acceptes pour une limite de 2,5 Mo). Intergiciel
    ASGI pur: sans Content-Length, le corps est lu en comptant, jusqu'a la
    limite, puis rejoue a l'application.
    """

    def __init__(self, app, maximum: int):
        self.app = app
        self.maximum = maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        longueur = dict(scope.get("headers") or []).get(b"content-length")
        if longueur is not None:
            try:
                trop_gros = int(longueur) > self.maximum
            except ValueError:
                trop_gros = True
            if trop_gros:
                await self._refuser(send)
            else:
                await self.app(scope, receive, send)
            return

        morceaux, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            corps = message.get("body", b"")
            total += len(corps)
            if total > self.maximum:
                await self._refuser(send)
                return
            morceaux.append(corps)
            if not message.get("more_body"):
                break
        tout = b"".join(morceaux)
        rejoue = False

        async def rejouer():
            nonlocal rejoue
            if not rejoue:
                rejoue = True
                return {"type": "http.request", "body": tout, "more_body": False}
            # Ensuite, on rend la main: la reponse en flux ecoute la
            # deconnexion du client par ce canal.
            return await receive()

        await self.app(scope, rejouer, send)

    @staticmethod
    async def _refuser(send):
        corps = json.dumps({"error": {"code": "payload_too_large",
                                      "message": "Requete trop volumineuse."}}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(corps)).encode())]})
        await send({"type": "http.response.body", "body": corps})


def _sse(event: str, payload: dict) -> str:
    return "event: %s\ndata: %s\n\n" % (event, json.dumps(payload, ensure_ascii=False))


def _client_ip(request: Request, hops: int = 1, proxies=()) -> str:
    """Adresse du client, en ne croyant l'en-tete que lorsqu'il est credible.

    Faille corrigee en Phase 6, verifiee exploitable: l'anti-force brute de
    la connexion admin ne bloquait plus rien des lors que l'attaquant
    changeait d'adresse declaree a chaque essai (12 tentatives, 12 adresses,
    aucun blocage).

    Deux erreurs se cumulaient:

    1. X-Forwarded-For etait cru sur parole. Il est ecrit par le CLIENT, et
       nginx (`$proxy_add_x_forwarded_for`) se contente d'AJOUTER l'adresse
       reelle a la fin sans effacer ce qui precede. L'en-tete ne vaut donc
       que si la requete vient bien de notre proxy: sinon, seule l'adresse
       du pair compte.
    2. La PREMIERE entree etait retenue -- justement celle que le client
       controle. C'est la derniere qui est ecrite par notre nginx.

    `hops` vaut le nombre de proxys de confiance en amont (1 = nginx seul,
    2 si un CDN s'ajoute devant).
    """
    pair = request.client.host if request.client else "unknown"
    if pair not in proxies:
        # Connexion directe: l'en-tete est purement declaratif, on l'ignore.
        return pair
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        adresses = [a.strip() for a in forwarded.split(",") if a.strip()]
        if adresses:
            return adresses[max(0, len(adresses) - max(1, hops))]
    return pair


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
    # Ajoutee AVANT le CORS, donc executee a l'interieur: une reponse 413
    # garde ses en-tetes CORS et le widget peut afficher pourquoi.
    app.add_middleware(LimiteCorps, maximum=MAX_BODY_BYTES)
    app.add_middleware(CORSMiddleware, **cors)

    # --- en-tetes de securite -------------------------------------------------
    # La console affiche du texte produit par un modele, et le widget est
    # injecte dans une page tierce. L'echappement du rendu est la premiere
    # barriere; la CSP est la seconde, celle qui tient encore si la premiere
    # cede un jour. Tout est en ligne dans les deux pages -- aucune ressource
    # externe n'est chargee -- d'ou 'self' avec 'unsafe-inline' pour les
    # styles et scripts embarques, et rien d'autre.
    CSP = ("default-src 'self'; "
           "script-src 'self' 'unsafe-inline'; "
           "style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data:; "
           # Voix neuronale: le MP3 recu par fetch est joue via une URL blob:.
           "media-src 'self' blob:; "
           "connect-src 'self' " + " ".join(settings.origins) + "; "
           "object-src 'none'; base-uri 'none'; form-action 'none'; "
           # Le widget est legitimement dans une iframe Streamlit; la console
           # n'a aucune raison d'etre encadree par qui que ce soit.
           "frame-ancestors 'self' " + " ".join(settings.origins))

    @app.middleware("http")
    async def _entetes_securite(request: Request, call_next):
        reponse = await call_next(request)
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("Referrer-Policy", "no-referrer")
        reponse.headers.setdefault("Content-Security-Policy", CSP)
        if settings.env == "prod":
            # Ne vaut que derriere HTTPS, ce qui est le cas en production.
            reponse.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return reponse

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
        """Deux plafonds INDEPENDANTS, tous deux a franchir.

        La cle combinee "session|ip" utilisee jusqu'en Phase 6 ne tenait pas:
        un jeton de session s'obtient sans authentification, donc en demander
        un neuf a chaque message changeait la cle et remettait le seau a zero
        (verifie: 10 messages, 10 sessions, aucun blocage). Le commentaire
        d'origine affirmait le contraire.

        Desormais l'adresse est un plafond a elle seule -- on ne peut plus s'y
        soustraire en changeant de session -- et la session en est un autre,
        pour qu'un seul visiteur derriere un NAT partage n'epuise pas le
        plafond commun a lui tout seul.
        """
        c = request.app.state.ctx
        ip = _client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies)

        allowed, retry_after = c.ip_bucket_for(session.profile).consume(ip)
        if not allowed:
            log_event("jarvis.%s" % session.profile, "rate_limited",
                      motif="ip", session_id=session.session_id,
                      retry_after=retry_after)
            raise RateLimitedError(retry_after=retry_after)

        allowed, retry_after = c.bucket_for(session.profile).consume(session.session_id)
        if not allowed:
            log_event("jarvis.%s" % session.profile, "rate_limited",
                      motif="session", session_id=session.session_id,
                      retry_after=retry_after)
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
            tts=voix.disponible(c.settings),
        )

    @app.post("/jarvis/api/session", response_model=SessionResponse)
    async def create_session(request: Request, c: AppContext = Depends(ctx)):
        token, info = issue_token(c.settings.secret_key, profile="public")
        log_event("jarvis.public", "session_created",
                  session_id=info.session_id, ip=_client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies))
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
        ip = _client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies)
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
        log_event("jarvis.admin", "logout", ip=_client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies),
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

        ip = _client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies)
        if action.type in ("code_modifier", "tache_executer")                 and not c.settings.code_actions_enabled:
            # L'interrupteur vaut aussi pour les propositions deja deposees.
            raise JarvisError("Les modifications de code et les taches sont "
                              "desactivees sur ce serveur.",
                              code="code_desactive", status=403)
        if action.type in actions.TYPES_ASYNCHRONES:
            return _lancer_tache(c, action, session, ip)

        try:
            resultat = await asyncio.to_thread(actions.executer, c.settings, action)
        except Exception as exc:
            c.actions.marquer(action, actions.REFUSEE, {"erreur": str(exc)})
            log.exception("Echec de l'action %s", action_id)
            log_event("jarvis.admin", "action_echouee", ip=_client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies),
                      session_id=session.session_id, action_id=action_id,
                      type=action.type)
            raise JarvisError(
                "L'action n'a pas pu etre appliquee: %s" % exc,
                code="action_echouee", status=500)

        c.actions.marquer(action, actions.APPLIQUEE, resultat)
        # Piste d'audit: quoi, par qui, avec quel resultat.
        log_event("jarvis.admin", "action_appliquee", ip=_client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies),
                  session_id=session.session_id, action_id=action_id,
                  type=action.type, cible=resultat.get("fichier"),
                  n_occurrences=resultat.get("n_occurrences"),
                  sauvegarde=resultat.get("sauvegarde"))
        return {"statut": "appliquee", "resultat": resultat}

    def _lancer_tache(c: AppContext, action, session: SessionInfo, ip: str) -> dict:
        """Lance une tache approuvee en arriere-plan et rend la main.

        La commande est RECALCULEE a partir de la liste fermee au moment de
        l'approbation: rien de ce que le modele a ecrit n'y entre.
        """
        script = action.payload["script"]
        cible = action.payload.get("cible")
        # pytest sans fichier precis = toute la suite ("tests/").
        cible_tests = cible if script == "pytest" and cible != "tests/" else None
        try:
            tache = code_ops.preparer_tache(script, cible_tests)
        except code_ops.RefusCode as exc:
            c.actions.marquer(action, actions.REFUSEE, {"erreur": str(exc)})
            raise JarvisError(str(exc), code="tache_refusee", status=400)

        def fini(resultat):
            c.actions.marquer(action, actions.TERMINEE if resultat.get("reussi")
                              else actions.ECHOUEE, resultat)
            log_event("jarvis.admin", "tache_terminee", session_id=session.session_id,
                      action_id=action.id, script=tache["cible"],
                      reussi=resultat.get("reussi"), code=resultat.get("code_retour"),
                      duree_s=resultat.get("duree_s"))

        try:
            c.taches.lancer(tache["commande"], c.settings.task_timeout_seconds, fini)
        except code_ops.RefusCode as exc:
            # Une autre tache tourne: la proposition reste approuvable.
            raise JarvisError(str(exc), code="tache_occupee", status=409)
        c.actions.marquer(action, actions.EN_COURS, {"debut": int(time.time())})
        log_event("jarvis.admin", "tache_lancee", ip=ip, session_id=session.session_id,
                  action_id=action.id, script=tache["cible"])
        return {"statut": actions.EN_COURS, "resultat": None}

    @app.post("/jarvis/api/admin/actions/{action_id}/revert")
    async def admin_revert(action_id: str, request: Request,
                           session: SessionInfo = Depends(require_admin),
                           c: AppContext = Depends(ctx)):
        """Retablit le fichier d'avant une modification de code appliquee.

        Route, pas outil: comme l'approbation, l'annulation vient d'un clic.
        Refusee si le fichier a ete retouche depuis, pour ne pas ecraser ce
        travail.
        """
        try:
            action = c.actions.obtenir(session.session_id, action_id)
        except actions.ActionIntrouvable as exc:
            raise JarvisError(str(exc), code="action_introuvable", status=404)
        if action.type != "code_modifier" or action.statut != actions.APPLIQUEE:
            raise JarvisError("Seule une modification de code appliquee peut "
                              "etre annulee.", code="annulation_impossible",
                              status=409)
        try:
            retour = await asyncio.to_thread(code_ops.annuler_modification,
                                             action.resultat)
        except code_ops.RefusCode as exc:
            raise JarvisError(str(exc), code="annulation_refusee", status=409)
        c.actions.marquer(action, actions.ANNULEE, {**action.resultat, **retour})
        log_event("jarvis.admin", "action_annulee",
                  ip=_client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies),
                  session_id=session.session_id, action_id=action_id,
                  cible=action.resultat.get("fichier"))
        return {"statut": actions.ANNULEE, "resultat": retour}

    @app.post("/jarvis/api/admin/actions/{action_id}/reject")
    async def admin_reject(action_id: str, request: Request,
                           session: SessionInfo = Depends(require_admin),
                           c: AppContext = Depends(ctx)):
        try:
            action = c.actions.recuperer(session.session_id, action_id)
        except actions.ActionIntrouvable as exc:
            raise JarvisError(str(exc), code="action_introuvable", status=404)
        c.actions.marquer(action, actions.REFUSEE)
        log_event("jarvis.admin", "action_refusee", ip=_client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies),
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

    async def _tenter_elevation(request: Request, payload: ChatRequest,
                                session: SessionInfo, c: AppContext):
        """Le message est-il le mot de passe admin ? Si oui, eleve la session.

        Appele AVANT le rate limiting, la journalisation, l'historique et tout
        appel a l'API: un mot de passe ne doit emprunter aucun de ces chemins.

        Retourne le dict d'elevation, ou None pour poursuivre normalement. Le
        second membre du couple indique s'il faut taire le texte du message
        dans les journaux (tentative ratee: ce peut etre un mot de passe mal
        tape).
        """
        if session.profile == "admin":
            return None, False
        if not elevation.ressemble_a_un_mot_de_passe(payload.message):
            return None, False

        ip = _client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies)
        autorise, retry_after = c.login_bucket.consume(ip)
        if not autorise:
            # Meme seau que la route de connexion: le champ de saisie ne doit
            # pas offrir un second guichet, plus permissif, pour essayer des
            # mots de passe.
            log_event("jarvis.admin", "elevation_bloquee", ip=ip,
                      retry_after=retry_after)
            raise RateLimitedError(
                retry_after=retry_after,
                message="Trop de tentatives. Reessayez plus tard.")

        valide = await asyncio.to_thread(
            auth.verifier, payload.message, c.settings.admin_password_hash)
        if not valide:
            # Echec: on poursuit comme une question ordinaire, mais sans
            # recopier le texte dans les journaux.
            return None, True

        token, info = issue_token(c.settings.secret_key, profile="admin")
        log_event("jarvis.admin", "elevation_reussie", ip=ip,
                  session_id=info.session_id, depuis=session.session_id)
        return {
            "token": token,
            "session_id": info.session_id,
            "profile": "admin",
            "expires_in": c.settings.admin_session_ttl_seconds,
            "model": c.claude.model_for("admin"),
        }, False

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
        # Le contexte de page accompagne CETTE question vers l'API, mais
        # n'entre pas dans l'historique: _commit n'y ecrit que payload.message.
        contexte = page_context.nettoyer(payload.page_context)
        blocs_vue = page_view.blocs(payload.page_view)
        messages = conv.api_messages() + [
            page_context.message_utilisateur(payload.message, contexte, blocs_vue,
                                             oral=payload.oral)]
        return conv, messages, contexte

    def _commit(c: AppContext, conv, question: str, answer: str,
                figures_produites=None) -> None:
        """N'ecrit dans l'historique qu'une fois une reponse obtenue.

        Si l'appel echoue sans produire un seul caractere, rien n'est ecrit:
        l'utilisateur peut relancer sans se retrouver avec deux questions
        consecutives dans le fil.
        """
        if not answer:
            return
        c.store.append(conv, "user", question)
        c.store.append(conv, "assistant", answer, figures=figures_produites)

    @app.post("/jarvis/api/chat")
    async def chat_stream(request: Request, payload: ChatRequest,
                          session: SessionInfo = Depends(current_session),
                          c: AppContext = Depends(ctx)):
        eleve, taire = await _tenter_elevation(request, payload, session, c)
        if eleve:
            # Le mot de passe s'arrete ici: ni historique, ni journal, ni API.
            async def _flux_elevation():
                yield _sse("elevation", eleve)
                yield _sse("done", {"usage": {}})
            return StreamingResponse(
                _flux_elevation(), media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

        conv, messages, contexte = _prepare(request, payload, session, c)
        preview = (payload.message[: c.settings.log_preview_chars]
                   if c.settings.log_prompts and not taire else None)
        log_event("jarvis.%s" % session.profile, "chat_stream_start",
                  session_id=session.session_id,
                  conversation_id=conv.conversation_id,
                  chars=len(payload.message), question=preview,
                  page=contexte["page"] if contexte else None,
                  vue=page_view.resume_journal(payload.page_view))

        async def generator():
            parts = []
            usage = {}
            outils = []
            produites = []
            annoncees = 0
            navigations = []
            nav_annoncees = 0
            try:
                yield _sse("meta", {"conversation_id": conv.conversation_id,
                                    "model": c.claude.model_for(session.profile)})
                flux = c.claude.stream_reply(
                    messages, session.profile,
                    tools=c.tool_specs(session.profile),
                    executor=c.tool_executor(session.profile, session.session_id,
                                             produites, navigations),
                )
                async for chunk in flux:
                    # Une figure deposee pendant le tour d'outils precedent
                    # est annoncee des le fragment suivant, sans attendre la
                    # fin de la reponse.
                    while annoncees < len(produites):
                        yield _sse("figure", produites[annoncees])
                        annoncees += 1
                    # Idem pour une page du dashboard a ouvrir: elle s'ouvre
                    # pendant que Jarvis commence a en parler.
                    while nav_annoncees < len(navigations):
                        yield _sse("navigation", navigations[nav_annoncees])
                        nav_annoncees += 1
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
                          conversation_id=conv.conversation_id, code=exc.code,
                          detail=exc.detail)
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

            while annoncees < len(produites):
                yield _sse("figure", produites[annoncees])
                annoncees += 1
            while nav_annoncees < len(navigations):
                yield _sse("navigation", navigations[nav_annoncees])
                nav_annoncees += 1
            answer = "".join(parts)
            _commit(c, conv, payload.message, answer, produites)
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
        eleve, _ = await _tenter_elevation(request, payload, session, c)
        if eleve:
            return JSONResponse({"elevation": eleve})

        conv, messages, _ = _prepare(request, payload, session, c)
        produites = []
        navigations = []
        result = await c.claude.complete(
            messages, session.profile,
            tools=c.tool_specs(session.profile),
            executor=c.tool_executor(session.profile, session.session_id,
                                     produites, navigations),
        )
        _commit(c, conv, payload.message, result["text"], produites)
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
            figures=produites,
            navigations=navigations,
        )

    @app.post("/jarvis/api/tts")
    async def tts(request: Request, payload: TtsRequest,
                  session: SessionInfo = Depends(current_session),
                  c: AppContext = Depends(ctx)):
        """MP3 d'un morceau de reponse, voix neuronale (jarvis/voix.py).

        Jeton exige et debit borne: sans cela, la route ferait de ce serveur
        un service de synthese vocale gratuit pour n'importe qui.
        """
        if not voix.disponible(c.settings):
            raise NotFoundError("Synthese vocale desactivee.")
        ip = _client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies)
        allowed, retry_after = c.tts_bucket.consume(ip)
        if not allowed:
            log_event("jarvis.%s" % session.profile, "rate_limited",
                      motif="tts", session_id=session.session_id,
                      retry_after=retry_after)
            raise RateLimitedError(retry_after=retry_after)
        audio = await voix.synthetiser(payload.text, c.settings.tts_voice,
                                       c.settings.tts_rate)
        return Response(audio, media_type="audio/mpeg",
                        headers={"Cache-Control": "no-store"})

    @app.get("/jarvis/api/soutenance")
    async def soutenance_plan(session: SessionInfo = Depends(current_session)):
        """Plan de la presentation guidee: titres des etapes."""
        return {"etapes": soutenance.plan()}

    @app.post("/jarvis/api/soutenance/{numero}")
    async def soutenance_etape(numero: int, request: Request,
                               session: SessionInfo = Depends(current_session),
                               c: AppContext = Depends(ctx)):
        """Une etape, composee a la demande: page a ouvrir, figure deposee
        pour CETTE session, narration chiffree. Aucun appel au modele: rien
        n'est facture, rien ne peut etre invente devant un jury."""
        if not 1 <= numero <= len(soutenance.ETAPES):
            raise NotFoundError("Etape inconnue.")
        ip = _client_ip(request, c.settings.trusted_proxy_hops, c.settings.proxies)
        allowed, retry_after = c.soutenance_bucket.consume(ip)
        if not allowed:
            raise RateLimitedError(retry_after=retry_after)
        try:
            donnees = await tools_dataset.load(soutenance.JEUX)
        except tools_dataset.DataUnavailableError:
            raise NotFoundError("Donnees de la plateforme indisponibles.")
        contenu = await asyncio.to_thread(soutenance.etape, numero, donnees,
                                          c.figures, session.session_id)
        log_event("jarvis.%s" % session.profile, "soutenance_etape",
                  session_id=session.session_id, etape=numero)
        return contenu

    @app.get("/jarvis/api/figures/{figure_id}")
    async def figure(figure_id: str, theme: str = "clair", format: str = "png",
                     session: SessionInfo = Depends(current_session),
                     c: AppContext = Depends(ctx)):
        """Image (ou donnees CSV) d'une figure de CETTE session.

        Pas de balise <img src> possible: le jeton passe en en-tete. Le widget
        telecharge donc l'image par fetch, puis l'affiche.
        """
        if not figure_id.isalnum() or len(figure_id) > 64:
            raise NotFoundError("Figure introuvable.")
        trouvee = c.figures.obtenir(session.session_id, figure_id)
        if trouvee is None:
            raise NotFoundError("Figure introuvable.")
        entetes = {"Cache-Control": "private, max-age=3600"}
        if format == "csv":
            texte = figures.en_csv(trouvee.spec)
            entetes["Content-Disposition"] = (
                'attachment; filename="figure-%s.csv"' % trouvee.spec["type"])
            return Response(texte.encode("utf-8-sig"), media_type="text/csv",
                            headers=entetes)
        image = await asyncio.to_thread(figures.rendu_en_cache, trouvee,
                                        theme if theme in figures.THEMES else "clair")
        # Les animations sont des GIF: le widget lit le type de la reponse.
        type_image = "image/gif" if image[:4] == b"GIF8" else "image/png"
        return Response(image, media_type=type_image, headers=entetes)

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

    @app.get("/jarvis/static/{nom}")
    async def fichier_hud(nom: str):
        """L'orbe 3D (three.js inclus), chargee par le widget a l'entree du
        mode plein ecran seulement: la bulle compacte n'en a pas besoin."""
        chemin = FICHIERS_HUD.get(nom)
        if chemin is None or not chemin.is_file():
            raise NotFoundError("Fichier introuvable.")
        return FileResponse(chemin, media_type="application/javascript",
                            headers={"Cache-Control": "public, max-age=86400"})

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
            app.state.ctx.figures.purger()
        except Exception:
            log.exception("Echec de la purge des conversations")

# Pas d'instance au niveau module: create_app() lit la configuration et ouvre
# les fichiers de log, ce qui n'a rien a faire a l'import. uvicorn la construit
# via --factory (voir jarvis/README.md et deploy/jarvis.service).
