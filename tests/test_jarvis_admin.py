"""Profil administrateur: connexion, session, cloisonnement des profils.

Aucun appel a l'API Anthropic: le client Claude est remplace par FakeClaude.
Le cout scrypt est reduit (n=2**10) pour que la suite reste rapide; la logique
testee est identique a celle de production, le parametre etant porte par le
hache.
"""
import json
from pathlib import Path

import pytest

from jarvis import auth
from tests.conftest import FakeClaude, sse_events

MDP = "mot-de-passe-de-test-2026"
COUT_TEST = 2 ** 10


@pytest.fixture
def settings_admin(tmp_path):
    from jarvis.config import Settings
    s = Settings(
        secret_key="k" * 48,
        env="dev",
        anthropic_api_key="sk-ant-faux-pour-les-tests",
        log_dir=str(tmp_path / "logs"),
        admin_password_hash=auth.hacher(MDP, n=COUT_TEST),
        admin_session_ttl_seconds=3600,
        admin_login_max_attempts=3,
        admin_login_window_seconds=900,
        rate_limit_capacity=5,
        rate_limit_refill_per_minute=60.0,
    )
    s.validate_runtime()
    return s


@pytest.fixture
def client_admin(settings_admin):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app

    faux = FakeClaude()
    app = create_app(settings_admin)
    with TestClient(app) as c:
        c.app.state.ctx.claude = faux
        c.fake = faux
        c.settings = settings_admin
        yield c


def connecter(client, mot_de_passe=MDP):
    return client.post("/jarvis/api/admin/login", json={"password": mot_de_passe})


def entetes(jeton):
    return {"X-Jarvis-Session": jeton}


# --- connexion ----------------------------------------------------------------
def test_connexion_reussie(client_admin):
    r = connecter(client_admin)
    assert r.status_code == 200
    corps = r.json()
    assert corps["profile"] == "admin"
    assert corps["token"]
    assert corps["expires_in"] == 3600


def test_mot_de_passe_faux_refuse(client_admin):
    r = connecter(client_admin, "ce-n-est-pas-le-bon")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "access_denied"


def test_profil_admin_non_configure_repond_comme_un_mauvais_mot_de_passe(tmp_path):
    """Distinguer les deux cas dirait a un attaquant si la cible existe."""
    from fastapi.testclient import TestClient

    from jarvis.app import create_app
    from jarvis.config import Settings

    s = Settings(secret_key="k" * 48, env="dev",
                 anthropic_api_key="sk-ant-faux",
                 log_dir=str(tmp_path / "logs"),
                 admin_password_hash="")
    s.validate_runtime()
    with TestClient(create_app(s)) as c:
        r = c.post("/jarvis/api/admin/login", json={"password": MDP})
        assert r.status_code == 403
        assert r.json()["error"]["message"] == "Identifiants invalides."


def test_message_identique_quel_que_soit_l_echec(client_admin, tmp_path):
    a = connecter(client_admin, "mauvais-mot-de-passe-1").json()["error"]
    b = connecter(client_admin, "mauvais-mot-de-passe-2").json()["error"]
    assert a == b


def test_mot_de_passe_vide_rejete_par_le_schema(client_admin):
    assert client_admin.post("/jarvis/api/admin/login",
                             json={"password": ""}).status_code == 422


def test_mot_de_passe_demesure_rejete_par_le_schema(client_admin):
    """Champ non borne = deni de service a bon marche: scrypt travaille sur
    ce que le client envoie."""
    r = client_admin.post("/jarvis/api/admin/login", json={"password": "x" * 5000})
    assert r.status_code == 422


def test_force_brute_bloquee(client_admin):
    """Trois essais autorises, le quatrieme est refuse sans meme hacher."""
    for _ in range(3):
        assert connecter(client_admin, "faux").status_code == 403
    r = connecter(client_admin, "faux")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # Et le blocage vaut aussi pour le BON mot de passe: sinon un attaquant
    # saurait qu'il a trouve, au changement de code de reponse.
    assert connecter(client_admin, MDP).status_code == 429


def test_le_mot_de_passe_n_apparait_jamais_dans_les_logs(client_admin, settings_admin):
    connecter(client_admin, "un-mot-de-passe-tres-reconnaissable")
    connecter(client_admin)
    journal = Path(settings_admin.log_dir) / "admin.jsonl"
    contenu = journal.read_text(encoding="utf-8")
    assert "un-mot-de-passe-tres-reconnaissable" not in contenu
    assert MDP not in contenu
    assert "login_refuse" in contenu and "login_reussi" in contenu


def test_le_jeton_n_apparait_pas_dans_les_logs(client_admin, settings_admin):
    jeton = connecter(client_admin).json()["token"]
    journal = Path(settings_admin.log_dir) / "admin.jsonl"
    assert jeton not in journal.read_text(encoding="utf-8")


# --- session ------------------------------------------------------------------
def test_me_renvoie_la_session(client_admin):
    jeton = connecter(client_admin).json()["token"]
    r = client_admin.get("/jarvis/api/admin/me", headers=entetes(jeton))
    assert r.status_code == 200
    assert r.json()["profile"] == "admin"
    assert r.json()["token"] == ""     # ne renvoie jamais le jeton


def test_deconnexion_ferme_vraiment_la_session(client_admin):
    """Un jeton HMAC reste valide jusqu'a son echeance: sans liste de
    revocation, se deconnecter ne fermerait rien."""
    jeton = connecter(client_admin).json()["token"]
    assert client_admin.post("/jarvis/api/admin/logout",
                             headers=entetes(jeton)).status_code == 200
    r = client_admin.get("/jarvis/api/admin/me", headers=entetes(jeton))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_session"


def test_jeton_revoque_refuse_aussi_sur_le_chat(client_admin):
    jeton = connecter(client_admin).json()["token"]
    client_admin.post("/jarvis/api/admin/logout", headers=entetes(jeton))
    r = client_admin.post("/jarvis/api/chat/sync", json={"message": "bonjour"},
                          headers=entetes(jeton))
    assert r.status_code == 401


def test_session_admin_expiree(client_admin, monkeypatch):
    import jarvis.session as session_mod

    jeton = connecter(client_admin).json()["token"]
    faux_temps = session_mod.time.time() + 3601
    monkeypatch.setattr(session_mod.time, "time", lambda: faux_temps)
    assert client_admin.get("/jarvis/api/admin/me",
                            headers=entetes(jeton)).status_code == 401


def test_la_session_publique_garde_son_propre_ttl(client_admin, monkeypatch):
    """Le TTL admin est court; il ne doit pas raccourcir la session publique."""
    import jarvis.session as session_mod

    jeton = client_admin.post("/jarvis/api/session").json()["token"]
    faux_temps = session_mod.time.time() + 7200   # au-dela du TTL admin
    monkeypatch.setattr(session_mod.time, "time", lambda: faux_temps)
    r = client_admin.post("/jarvis/api/chat/sync", json={"message": "bonjour"},
                          headers=entetes(jeton))
    assert r.status_code == 200


# --- cloisonnement des profils ------------------------------------------------
def test_jeton_public_refuse_sur_les_routes_admin(client_admin):
    jeton = client_admin.post("/jarvis/api/session").json()["token"]
    for methode, route in (("get", "/jarvis/api/admin/me"),
                           ("post", "/jarvis/api/admin/logout")):
        r = getattr(client_admin, methode)(route, headers=entetes(jeton))
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "access_denied"


def test_aucun_jeton_sur_les_routes_admin(client_admin):
    assert client_admin.get("/jarvis/api/admin/me").status_code == 401


def test_jeton_admin_forge_rejete(client_admin):
    """Sans le secret serveur, on ne peut pas se declarer admin."""
    import base64

    charge = base64.urlsafe_b64encode(b"idfactice:admin:99999999999").decode().rstrip("=")
    for faux in (charge + ".signaturebidon", charge, charge + "."):
        r = client_admin.get("/jarvis/api/admin/me", headers=entetes(faux))
        assert r.status_code == 401


def test_jeton_public_modifie_en_admin_rejete(client_admin):
    """On reprend un jeton public valide et on change le profil dans la
    charge: la signature ne correspond plus."""
    import base64

    jeton = client_admin.post("/jarvis/api/session").json()["token"]
    corps, signature = jeton.split(".")
    pad = "=" * (-len(corps) % 4)
    clair = base64.urlsafe_b64decode(corps + pad).decode()
    trafique = clair.replace(":public:", ":admin:")
    nouveau = base64.urlsafe_b64encode(trafique.encode()).decode().rstrip("=")
    r = client_admin.get("/jarvis/api/admin/me",
                         headers=entetes(nouveau + "." + signature))
    assert r.status_code == 401


# --- effets du profil ---------------------------------------------------------
def test_le_chat_admin_utilise_le_modele_admin(client_admin):
    jeton = connecter(client_admin).json()["token"]
    r = client_admin.post("/jarvis/api/chat", json={"message": "bonjour"},
                          headers=entetes(jeton))
    meta = dict(sse_events(r.text))["meta"]
    assert meta["model"] == "claude-opus-5"


def test_le_chat_public_reste_sur_le_modele_public(client_admin):
    jeton = client_admin.post("/jarvis/api/session").json()["token"]
    r = client_admin.post("/jarvis/api/chat", json={"message": "bonjour"},
                          headers=entetes(jeton))
    assert dict(sse_events(r.text))["meta"]["model"] == "claude-sonnet-5"


def test_le_profil_admin_choisit_le_prompt_admin(settings_admin):
    from jarvis.claude_client import ClaudeClient

    client = ClaudeClient(settings_admin)
    public = client.system_for("public")
    admin = client.system_for("admin")
    assert public != admin
    assert "session administrateur" in admin
    assert "Laity" in admin


def test_les_debits_public_et_admin_sont_separes(client_admin):
    """Un afflux de visiteurs ne doit pas bloquer l'administrateur."""
    jeton_public = client_admin.post("/jarvis/api/session").json()["token"]
    for _ in range(5):
        client_admin.post("/jarvis/api/chat/sync", json={"message": "x"},
                          headers=entetes(jeton_public))
    bloque = client_admin.post("/jarvis/api/chat/sync", json={"message": "x"},
                               headers=entetes(jeton_public))
    assert bloque.status_code == 429

    jeton_admin = connecter(client_admin).json()["token"]
    r = client_admin.post("/jarvis/api/chat/sync", json={"message": "x"},
                          headers=entetes(jeton_admin))
    assert r.status_code == 200


def test_les_echanges_admin_vont_dans_le_journal_admin(client_admin, settings_admin):
    jeton = connecter(client_admin).json()["token"]
    client_admin.post("/jarvis/api/chat/sync", json={"message": "bonjour"},
                      headers=entetes(jeton))
    admin_log = (Path(settings_admin.log_dir) / "admin.jsonl").read_text(encoding="utf-8")
    public_log = (Path(settings_admin.log_dir) / "public.jsonl").read_text(encoding="utf-8")
    assert "chat_sync_done" in admin_log
    assert "chat_sync_done" not in public_log


# --- console ------------------------------------------------------------------
def test_console_servie(client_admin):
    r = client_admin.get("/jarvis/admin")
    assert r.status_code == 200
    assert "console administrateur" in r.text


def test_console_sans_secret_ni_placeholder(client_admin):
    r = client_admin.get("/jarvis/admin")
    assert "__JARVIS_API_BASE__" not in r.text
    assert "sk-ant" not in r.text
    assert "scrypt$" not in r.text


def test_console_non_indexable_et_non_mise_en_cache(client_admin):
    r = client_admin.get("/jarvis/admin")
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert r.headers.get("cache-control") == "no-store"


# --- configuration ------------------------------------------------------------
def test_hache_mal_forme_refuse_au_demarrage(tmp_path):
    """Sinon la faute de frappe ne se verrait qu'a la premiere connexion,
    sous la forme d'un refus indistinguable d'un mauvais mot de passe."""
    from jarvis.config import Settings
    from jarvis.errors import ConfigurationError

    s = Settings(secret_key="k" * 48, env="dev", anthropic_api_key="x",
                 log_dir=str(tmp_path), admin_password_hash="scrypt$pas$un$hache")
    with pytest.raises(ConfigurationError):
        s.validate_runtime()
