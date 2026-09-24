"""Configuration Jarvis - tout vient de l'environnement, rien n'est code en dur.

Regle non negociable: aucune cle API, aucun secret dans le code ni dans git.
Voir .env.example pour la liste complete des variables.
"""
import secrets
import warnings
from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import ConfigurationError

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=str(PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # Sans cela, un champ porteur d'alias (anthropic_api_key) ne peut etre
        # renseigne QUE par son alias: Settings(anthropic_api_key=...) serait
        # silencieusement ignore. Piege verifie par les tests.
        populate_by_name=True,
    )

    # --- Secrets (jamais de valeur par defaut utilisable en production) ------
    # Lu sous ANTHROPIC_API_KEY (nom standard du SDK), pas JARVIS_*.
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    # Requis uniquement si la cle API n est pas rattachee a un workspace :
    # l organisation renvoie alors un 400 demandant l en-tete
    # anthropic-workspace-id. Une cle scopee a un workspace rend ce champ inutile.
    anthropic_workspace_id: str = Field(default="", alias="ANTHROPIC_WORKSPACE_ID")
    secret_key: str = ""

    env: Literal["dev", "prod"] = "dev"

    # --- Modeles -------------------------------------------------------------
    model_public: str = "claude-sonnet-5"
    model_admin: str = "claude-opus-5"
    effort_public: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    thinking_public: Literal["adaptive", "disabled"] = "adaptive"
    max_tokens_public: int = 2048

    # --- Robustesse appels API ----------------------------------------------
    request_timeout_seconds: float = 60.0
    max_retries: int = 2

    # --- Outils (Phase 2) -----------------------------------------------------
    # tools_enabled=False rend Jarvis aveugle aux donnees sans rien casser:
    # interrupteur de repli si un jeu de donnees devient illisible en production.
    tools_enabled: bool = True
    # Nombre de tours d'outils autorises avant de forcer une reponse en texte.
    # Chaque tour est un appel API supplementaire: c'est le garde-fou de cout.
    max_tool_rounds: int = 3
    # Profil admin (Phase 10): travailler sur le code demande d'enchainer
    # lister, lire, chercher, proposer. Trois tours n'y suffisent pas.
    max_tool_rounds_admin: int = 8
    # Plafond de taille d'un resultat d'outil injecte dans le contexte.
    tool_result_max_chars: int = 6000
    # Prechauffe les loaders au demarrage (3 a 4 s) pour que le premier
    # visiteur ne paie pas l'import de streamlit et la lecture des CSV.
    tools_preload: bool = True
    # --- Code et taches (Phase 10) ---------------------------------------------
    # Interrupteur des outils qui MODIFIENT le code ou LANCENT des scripts
    # (toujours sous approbation). La lecture du code reste possible.
    code_actions_enabled: bool = True
    # Delai maximal d'une tache (script du pipeline ou tests), en secondes.
    task_timeout_seconds: int = 1800

    # --- Profil admin (Phase 4) ----------------------------------------------
    # Seul le HACHE est stocke (voir jarvis/auth.py). Vide = profil admin
    # ferme: la route de connexion repond alors comme a un mauvais mot de
    # passe, sans reveler que rien n'est configure.
    admin_password_hash: str = ""
    # Session admin courte: elle ouvre des actions sensibles, contrairement au
    # jeton public qui ne donne acces qu'a de la lecture anonyme.
    admin_session_ttl_seconds: int = 28800    # 8 h
    # Anti-force brute sur la connexion, par IP.
    admin_login_max_attempts: int = 5
    admin_login_window_seconds: int = 900     # 15 min
    # Debit admin: plus large que le public, mais PAS illimite. Le profil
    # admin tourne sur Opus, une boucle accidentelle couterait cher.
    admin_rate_limit_capacity: int = 30
    admin_rate_limit_refill_per_minute: float = 20.0

    # --- Documents de recherche (Phase 5) -------------------------------------
    # Les sources vivent HORS du depot: dossier personnel, non versionne. Le
    # serveur de production n'y a pas acces, et c'est voulu -- les outils de
    # redaction sont reserves au poste de Laity.
    documents_dir: str = str(PROJECT_DIR.parent / "recherche" / "Rédaction")
    documents_memoire: str = "Mémoire_VERSION_FINALE (1).docx"
    documents_article: str = "Article_extremes_pluviometriques_Sahel_senegalais_v2 (1).docx"
    # Duree de vie d'une proposition de modification non approuvee.
    action_ttl_seconds: int = 1800            # 30 min

    # --- Plafonds conversation (protection cout et contexte) ----------------
    session_ttl_seconds: int = 86400          # 24 h
    conversation_ttl_seconds: int = 7200      # 2 h d'inactivite
    max_turns: int = 20                       # paires user/assistant conservees
    max_message_chars: int = 4000
    max_history_chars: int = 60000
    max_conversations: int = 2000             # garde-fou memoire

    # --- Rate limiting public ------------------------------------------------
    # Deux plafonds independants, tous deux a franchir (voir enforce_rate_limit).
    rate_limit_capacity: int = 12             # par SESSION: rafale autorisee
    rate_limit_refill_per_minute: float = 6.0 # par SESSION: regime permanent
    # Par ADRESSE: plus large, pour ne pas penaliser un NAT partage, mais
    # fini -- c'est ce plafond qu'on ne peut pas contourner en changeant de
    # session, un jeton s'obtenant sans authentification.
    rate_limit_ip_capacity: int = 40
    rate_limit_ip_refill_per_minute: float = 20.0
    # Nombre de proxys de confiance devant le service (1 = nginx seul).
    # Sert a lire X-Forwarded-For depuis la DROITE: les entrees de gauche sont
    # celles que le client a pu ecrire lui-meme.
    trusted_proxy_hops: int = 1
    # Adresses dont on accepte X-Forwarded-For. Hors de cette liste,
    # l'en-tete est ignore et seule l'adresse du pair compte: un client
    # qui joint le service en direct ne doit pas pouvoir declarer qui il est.
    trusted_proxies: str = "127.0.0.1,::1"

    # --- Reseau / logs --------------------------------------------------------
    allowed_origins: str = "http://localhost:8501,http://127.0.0.1:8501"
    log_dir: str = str(PROJECT_DIR / "outputs" / "jarvis_logs")
    log_prompts: bool = True                  # extrait tronque des questions
    log_preview_chars: int = 200

    @field_validator("max_turns", "max_message_chars", "max_history_chars",
                     "tool_result_max_chars", "rate_limit_ip_capacity",
                     "trusted_proxy_hops")
    @classmethod
    def _positive(cls, v):
        if v <= 0:
            raise ValueError("doit etre strictement positif")
        return v

    @property
    def proxies(self) -> set:
        return {p.strip() for p in self.trusted_proxies.split(",") if p.strip()}

    @property
    def origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def rate_limit_refill_per_second(self) -> float:
        return self.rate_limit_refill_per_minute / 60.0

    @property
    def rate_limit_ip_refill_per_second(self) -> float:
        return self.rate_limit_ip_refill_per_minute / 60.0

    @property
    def admin_rate_limit_refill_per_second(self) -> float:
        return self.admin_rate_limit_refill_per_minute / 60.0

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_password_hash)

    @property
    def documents(self) -> dict:
        """Cle logique -> nom de fichier. Les outils ne manipulent que des
        cles: un chemin libre venu du modele serait une traversee de
        repertoire en puissance."""
        return {"memoire": self.documents_memoire,
                "article": self.documents_article}

    def ttl_for(self, profile: str) -> int:
        return self.admin_session_ttl_seconds if profile == "admin" \
            else self.session_ttl_seconds

    def validate_admin_hash(self) -> None:
        """Rejette un hache admin mal forme AU DEMARRAGE.

        Sans ce controle, une faute de frappe dans le .env ne se verrait qu'a
        la premiere tentative de connexion, sous la forme d'un refus
        indistinguable d'un mauvais mot de passe: Laity chercherait son erreur
        du mauvais cote.
        """
        if not self.admin_password_hash:
            return
        from .auth import _decoder
        try:
            _decoder(self.admin_password_hash)
        except (ValueError, TypeError) as exc:
            raise ConfigurationError(
                "JARVIS_ADMIN_PASSWORD_HASH est mal forme (%s). Le regenerer "
                "avec: py -3 -m jarvis.auth" % exc
            ) from exc

    def validate_runtime(self) -> None:
        """Verifie les secrets au demarrage. Strict en prod, tolerant en dev."""
        self.validate_admin_hash()
        if self.env == "prod":
            if not self.anthropic_api_key:
                raise ConfigurationError("ANTHROPIC_API_KEY manquant.")
            if not self.secret_key or len(self.secret_key) < 32:
                raise ConfigurationError(
                    "JARVIS_SECRET_KEY manquant ou trop court (32 caracteres minimum)."
                )
        elif not self.secret_key:
            # Dev seulement: cle ephemere, les sessions ne survivent pas a un restart.
            self.secret_key = secrets.token_urlsafe(48)
            warnings.warn(
                "JARVIS_SECRET_KEY absent: cle ephemere generee (dev uniquement).",
                RuntimeWarning,
                stacklevel=2,
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.validate_runtime()
    return s
