"""Elevation de session depuis le champ de saisie (interface unique).

Le mot de passe emprunte le chemin d'un message ordinaire -- chemin qui
journalise, archive et transmet a l'API Anthropic. Ces tests verifient qu'il
en sort AVANT chacune de ces etapes, et que le raccourci n'ouvre pas un second
guichet plus permissif que la route de connexion.
"""
from pathlib import Path

import pytest

from jarvis import auth, elevation
from tests.conftest import FakeClaude, sse_events

MDP = "mon-mot-de-passe-secret-2026"
COUT_TEST = 2 ** 10


@pytest.fixture
def client_eleve(tmp_path):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app
    from jarvis.config import Settings

    s = Settings(secret_key="k" * 48, env="dev",
                 anthropic_api_key="sk-ant-faux",
                 log_dir=str(tmp_path / "logs"),
                 admin_password_hash=auth.hacher(MDP, n=COUT_TEST),
                 admin_login_max_attempts=3,
                 trusted_proxies="127.0.0.1,::1,testclient")
    s.validate_runtime()
    app = create_app(s)
    with TestClient(app) as c:
        c.app.state.ctx.claude = FakeClaude()
        c.settings = s
        yield c


def jeton_public(client):
    return client.post("/jarvis/api/session").json()["token"]


def entetes(jeton, ip=None):
    h = {"X-Jarvis-Session": jeton}
    if ip:
        h["X-Forwarded-For"] = ip
    return h


# --- detection ----------------------------------------------------------------
@pytest.mark.parametrize("message", [
    "Quelle est la correlation la plus forte ?",
    "combien d evenements en 2012",
    "CHIRPS",                      # trop court
    "",
    "   ",
    "teleconnexions?",             # question d'un seul mot
    "a" * 300,                     # au-dela du plafond
])
def test_messages_qui_ne_sont_pas_des_tentatives(message):
    """Verifier chaque message couterait 100 ms de scrypt: un deni de service
    a bon marche. Seul ce qui RESSEMBLE a un mot de passe est examine."""
    assert elevation.ressemble_a_un_mot_de_passe(message) is False


@pytest.mark.parametrize("message", [
    "mon-mot-de-passe-secret-2026",
    "Xk9!vbQ2zLmT",
    "unmotdepasselong",
])
def test_messages_examines(message):
    assert elevation.ressemble_a_un_mot_de_passe(message) is True


# --- elevation ----------------------------------------------------------------
def test_le_mot_de_passe_eleve_la_session_en_streaming(client_eleve):
    jeton = jeton_public(client_eleve)
    r = client_eleve.post("/jarvis/api/chat", json={"message": MDP},
                          headers=entetes(jeton))
    evenements = dict(sse_events(r.text))
    assert "elevation" in evenements
    assert evenements["elevation"]["profile"] == "admin"
    assert evenements["elevation"]["token"]


def test_le_mot_de_passe_eleve_la_session_en_sync(client_eleve):
    jeton = jeton_public(client_eleve)
    r = client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                          headers=entetes(jeton))
    assert r.json()["elevation"]["profile"] == "admin"


def test_le_nouveau_jeton_ouvre_les_routes_admin(client_eleve):
    jeton = jeton_public(client_eleve)
    eleve = client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                              headers=entetes(jeton)).json()["elevation"]
    r = client_eleve.get("/jarvis/api/admin/me",
                         headers=entetes(eleve["token"]))
    assert r.status_code == 200
    assert r.json()["profile"] == "admin"


def test_l_ancien_jeton_reste_public(client_eleve):
    """L'elevation emet un NOUVEAU jeton; l'ancien ne doit pas devenir admin."""
    jeton = jeton_public(client_eleve)
    client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                      headers=entetes(jeton))
    assert client_eleve.get("/jarvis/api/admin/me",
                            headers=entetes(jeton)).status_code == 403


# --- le secret ne fuit nulle part ---------------------------------------------
def test_le_mot_de_passe_n_est_pas_journalise(client_eleve):
    jeton = jeton_public(client_eleve)
    client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                      headers=entetes(jeton))
    dossier = Path(client_eleve.settings.log_dir)
    journaux = "".join(f.read_text(encoding="utf-8") for f in dossier.glob("*.jsonl"))
    assert MDP not in journaux
    assert "elevation_reussie" in journaux


def test_le_mot_de_passe_n_est_pas_transmis_au_modele(client_eleve):
    jeton = jeton_public(client_eleve)
    client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                      headers=entetes(jeton))
    assert not any(MDP in str(appel) for appel in client_eleve.app.state.ctx.claude.calls)


def test_le_mot_de_passe_n_entre_pas_dans_l_historique(client_eleve):
    jeton = jeton_public(client_eleve)
    client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                      headers=entetes(jeton))
    assert client_eleve.app.state.ctx.store.size() == 0


def test_une_tentative_ratee_ne_recopie_pas_le_texte(client_eleve):
    """Un mot de passe mal tape ne doit pas finir dans les journaux."""
    jeton = jeton_public(client_eleve)
    client_eleve.post("/jarvis/api/chat", json={"message": "presque-le-bon-mdp"},
                      headers=entetes(jeton))
    journaux = "".join(f.read_text(encoding="utf-8")
                       for f in Path(client_eleve.settings.log_dir).glob("*.jsonl"))
    assert "presque-le-bon-mdp" not in journaux


# --- le raccourci n'ouvre pas un second guichet --------------------------------
def test_les_tentatives_par_le_champ_sont_plafonnees(client_eleve):
    """Sans cela, le champ de saisie offrirait un guichet plus permissif que
    la route de connexion pour essayer des mots de passe."""
    jeton = jeton_public(client_eleve)
    codes = [client_eleve.post("/jarvis/api/chat/sync",
                               json={"message": "tentative-numero-%d" % i},
                               headers=entetes(jeton, "9.9.9.9")).status_code
             for i in range(6)]
    assert 429 in codes


def test_le_plafond_est_partage_avec_la_route_de_connexion(client_eleve):
    jeton = jeton_public(client_eleve)
    for i in range(3):
        client_eleve.post("/jarvis/api/chat/sync",
                          json={"message": "tentative-numero-%d" % i},
                          headers=entetes(jeton, "8.8.8.8"))
    r = client_eleve.post("/jarvis/api/admin/login", json={"password": "faux"},
                          headers={"X-Forwarded-For": "8.8.8.8"})
    assert r.status_code == 429


def test_une_question_ordinaire_ne_consomme_pas_le_plafond(client_eleve):
    jeton = jeton_public(client_eleve)
    for _ in range(5):
        client_eleve.post("/jarvis/api/chat/sync",
                          json={"message": "Quelle est la correlation la plus forte ?"},
                          headers=entetes(jeton, "7.7.7.7"))
    r = client_eleve.post("/jarvis/api/admin/login", json={"password": "faux"},
                          headers={"X-Forwarded-For": "7.7.7.7"})
    assert r.status_code == 403        # refuse, mais pas bloque


def test_une_session_deja_admin_n_est_pas_reexaminee(client_eleve):
    """Inutile de hacher: un admin qui tape un mot isole pose une question."""
    jeton = jeton_public(client_eleve)
    eleve = client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                              headers=entetes(jeton)).json()["elevation"]
    r = client_eleve.post("/jarvis/api/chat/sync", json={"message": MDP},
                          headers=entetes(eleve["token"]))
    assert "reply" in r.json()
