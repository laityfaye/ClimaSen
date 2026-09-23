"""Durcissement (Phase 6): contournements verifies exploitables, puis corriges.

Chaque test de ce fichier correspond a une faille reelle, constatee sur le code
des phases precedentes avant correction. Ils sont ecrits comme des attaques,
pas comme des cas nominaux: c'est la seule maniere de s'assurer qu'une
regression se verrait.
"""
from pathlib import Path

import pytest

from jarvis import auth
from tests.conftest import FakeClaude

MDP = "mot-de-passe-de-test-2026"
COUT_TEST = 2 ** 10
# Pair vu par TestClient. Le declarer de confiance simule le poste de nginx.
PAIR_TEST = "testclient"


def reglages(tmp_path, **extra):
    from jarvis.config import Settings

    base = dict(
        secret_key="k" * 48, env="dev", anthropic_api_key="sk-ant-faux",
        log_dir=str(tmp_path / "logs"),
        admin_password_hash=auth.hacher(MDP, n=COUT_TEST),
        admin_login_max_attempts=3,
        rate_limit_capacity=3, rate_limit_refill_per_minute=0.01,
        rate_limit_ip_capacity=5, rate_limit_ip_refill_per_minute=0.01,
        trusted_proxies="127.0.0.1,::1," + PAIR_TEST,
    )
    base.update(extra)
    s = Settings(**base)
    s.validate_runtime()
    return s


def client_de(settings):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app

    app = create_app(settings)
    c = TestClient(app)
    c.__enter__()
    c.app.state.ctx.claude = FakeClaude()
    return c


@pytest.fixture
def client(tmp_path):
    c = client_de(reglages(tmp_path))
    yield c
    c.__exit__(None, None, None)


def entetes(jeton=None, ip=None):
    h = {}
    if jeton:
        h["X-Jarvis-Session"] = jeton
    if ip:
        h["X-Forwarded-For"] = ip
    return h


# =============================================================================
# Faille 1 : anti-force brute contourne en declarant une adresse differente
# =============================================================================
def test_force_brute_non_contournable_par_entete(client):
    """Constate exploitable avant correction: 12 tentatives, 12 adresses
    declarees, AUCUN blocage.

    nginx utilise $proxy_add_x_forwarded_for, qui CONSERVE l'en-tete du client
    et ajoute l'adresse reelle a la fin. Lire la premiere valeur revenait a
    faire confiance au client.
    """
    codes = [client.post("/jarvis/api/admin/login", json={"password": "faux"},
                         headers=entetes(ip="10.0.0.%d, 203.0.113.9" % i)).status_code
             for i in range(10)]
    assert codes.count(429) >= 6, codes


def test_entete_ignore_hors_proxy_de_confiance(tmp_path):
    """Service joint en direct: X-Forwarded-For n'est que declaratif."""
    c = client_de(reglages(tmp_path, trusted_proxies="127.0.0.1"))
    try:
        codes = [c.post("/jarvis/api/admin/login", json={"password": "faux"},
                        headers=entetes(ip="10.0.0.%d" % i)).status_code
                 for i in range(10)]
        assert codes.count(429) >= 6, codes
    finally:
        c.__exit__(None, None, None)


def test_deux_visiteurs_distincts_ne_se_bloquent_pas(client):
    """Deux visiteurs = deux adresses REELLES differentes, donc deux entrees
    finales differentes dans X-Forwarded-For. Le prefixe declare, lui, est
    ignore: c'est tout l'objet du correctif."""
    for _ in range(4):
        client.post("/jarvis/api/admin/login", json={"password": "faux"},
                    headers=entetes(ip="1.1.1.1, 203.0.113.9"))
    bloque = client.post("/jarvis/api/admin/login", json={"password": "faux"},
                         headers=entetes(ip="1.1.1.1, 203.0.113.9"))
    autre = client.post("/jarvis/api/admin/login", json={"password": "faux"},
                        headers=entetes(ip="2.2.2.2, 198.51.100.7"))
    assert bloque.status_code == 429
    assert autre.status_code == 403


def test_le_blocage_vaut_aussi_pour_le_bon_mot_de_passe(client):
    """Sinon un changement de code de reponse apprendrait a l'attaquant
    qu'il a trouve."""
    for _ in range(4):
        client.post("/jarvis/api/admin/login", json={"password": "faux"},
                    headers=entetes(ip="3.3.3.3, 203.0.113.9"))
    r = client.post("/jarvis/api/admin/login", json={"password": MDP},
                    headers=entetes(ip="3.3.3.3, 203.0.113.9"))
    assert r.status_code == 429


# =============================================================================
# Faille 2 : plafond de debit contourne en changeant de session
# =============================================================================
def test_debit_non_contournable_en_changeant_de_session(client):
    """Constate exploitable avant correction: 10 messages, 10 sessions
    neuves, AUCUN blocage.

    Un jeton de session s'obtient sans authentification: il ne peut donc pas
    etre le seul point d'ancrage du debit.
    """
    codes = []
    for _ in range(10):
        jeton = client.post("/jarvis/api/session").json()["token"]
        codes.append(client.post("/jarvis/api/chat/sync", json={"message": "x"},
                                 headers=entetes(jeton)).status_code)
    assert codes.count(429) >= 4, codes


def test_le_plafond_par_session_reste_actif(client):
    """Deux plafonds independants: celui de la session borne une rafale."""
    jeton = client.post("/jarvis/api/session").json()["token"]
    codes = [client.post("/jarvis/api/chat/sync", json={"message": "x"},
                         headers=entetes(jeton)).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes


def test_usage_normal_preserve(client):
    """Le durcissement ne doit pas gener un visiteur ordinaire."""
    jeton = client.post("/jarvis/api/session").json()["token"]
    codes = [client.post("/jarvis/api/chat/sync", json={"message": "x"},
                         headers=entetes(jeton)).status_code for _ in range(3)]
    assert codes == [200, 200, 200]


def test_motif_du_blocage_journalise(client, tmp_path):
    """Savoir LEQUEL des deux plafonds a bloque, sinon le reglage se fait
    a l'aveugle."""
    jeton = client.post("/jarvis/api/session").json()["token"]
    for _ in range(6):
        client.post("/jarvis/api/chat/sync", json={"message": "x"},
                    headers=entetes(jeton))
    journal = (Path(client.app.state.ctx.settings.log_dir)
               / "public.jsonl").read_text(encoding="utf-8")
    assert "rate_limited" in journal
    assert '"motif"' in journal


# =============================================================================
# Faille 3 : oracle temporel sur un profil admin non configure
# =============================================================================
def test_pas_d_oracle_temporel_sans_mot_de_passe_configure():
    """Repondre instantanement quand aucun hache n'est configure dirait a
    l'attaquant qu'il n'y a rien a chercher ici."""
    import time

    hache = auth.hacher(MDP)          # cout de production, exprès
    debut = time.perf_counter()
    auth.verifier(MDP, "")
    sans_configuration = time.perf_counter() - debut

    debut = time.perf_counter()
    auth.verifier("mauvais-mot-de-passe", hache)
    avec_configuration = time.perf_counter() - debut

    # Les deux doivent couter le meme ordre de grandeur (~100 ms).
    assert sans_configuration > avec_configuration / 3


def test_reponse_identique_configure_ou_non(tmp_path):
    ouvert = client_de(reglages(tmp_path))
    ferme = client_de(reglages(tmp_path / "b", admin_password_hash=""))
    try:
        a = ouvert.post("/jarvis/api/admin/login", json={"password": "faux"})
        b = ferme.post("/jarvis/api/admin/login", json={"password": "faux"})
        assert a.status_code == b.status_code == 403
        assert a.json() == b.json()
    finally:
        ouvert.__exit__(None, None, None)
        ferme.__exit__(None, None, None)


# =============================================================================
# En-tetes de securite
# =============================================================================
@pytest.mark.parametrize("route", ["/jarvis/admin", "/jarvis/widget.html"])
def test_entetes_de_securite_sur_les_pages(client, route):
    r = client.get(route)
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in r.headers
    assert r.headers.get("referrer-policy")


def test_csp_interdit_les_sources_externes(client):
    csp = client.get("/jarvis/admin").headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors" in csp


def test_la_console_reste_hors_des_moteurs_de_recherche(client):
    r = client.get("/jarvis/admin")
    assert "noindex" in r.headers.get("x-robots-tag", "")
    assert r.headers.get("cache-control") == "no-store"
