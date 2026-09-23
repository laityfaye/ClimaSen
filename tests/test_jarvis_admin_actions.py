"""Routes d'approbation: le seul chemin par lequel une ecriture peut arriver.

Ce que ces tests verrouillent:
  - le modele depose, il n'applique pas;
  - seule une session admin peut approuver, et seulement SES propositions;
  - une proposition n'est ni rejouable, ni approuvable apres expiration;
  - toute application laisse une trace d'audit.
"""
import zipfile
from pathlib import Path

import pytest

from jarvis import auth
from tests.conftest import FakeClaude
from tests.test_jarvis_documents import fabriquer_docx

MDP = "mot-de-passe-de-test-2026"


@pytest.fixture
def client_docs(tmp_path):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app
    from jarvis.config import Settings

    dossier = tmp_path / "docs"
    dossier.mkdir()
    fabriquer_docx(dossier / "memoire.docx", [
        ("Titre1", "Chapitre 2"),
        ("", "La grille compte 450 points au total."),
    ])
    fabriquer_docx(dossier / "article.docx", [("Titre1", "1. Intro"), ("", "Texte.")])

    s = Settings(secret_key="k" * 48, env="dev",
                 anthropic_api_key="sk-ant-faux",
                 log_dir=str(tmp_path / "logs"),
                 admin_password_hash=auth.hacher(MDP, n=2 ** 10),
                 documents_dir=str(dossier),
                 documents_memoire="memoire.docx",
                 documents_article="article.docx")
    s.validate_runtime()
    app = create_app(s)
    with TestClient(app) as c:
        c.app.state.ctx.claude = FakeClaude()
        c.settings = s
        c.dossier = dossier
        yield c


def entetes(jeton):
    return {"X-Jarvis-Session": jeton}


def jeton_admin(client):
    return client.post("/jarvis/api/admin/login",
                       json={"password": MDP}).json()["token"]


def deposer_via_outil(client, jeton, avant="450 points", apres="460 points"):
    """Depose une proposition comme le ferait le modele, via l'executeur reel."""
    import asyncio

    contexte = client.app.state.ctx
    session_id = client.get("/jarvis/api/admin/me",
                            headers=entetes(jeton)).json()["session_id"]
    executeur = contexte.tool_executor("admin", session_id)
    resultat = asyncio.run(
        executeur("propose_document_edit",
                  {"document": "memoire", "old_text": avant,
                   "new_text": apres, "reason": "coherence avec les donnees"}))
    assert not resultat["is_error"], resultat["content"]
    import json
    return json.loads(resultat["content"])["action_id"]


# --- listing ------------------------------------------------------------------
def test_liste_vide_au_depart(client_docs):
    jeton = jeton_admin(client_docs)
    r = client_docs.get("/jarvis/api/admin/actions", headers=entetes(jeton))
    assert r.status_code == 200
    assert r.json()["actions"] == []


def test_la_proposition_apparait_dans_la_liste(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    liste = client_docs.get("/jarvis/api/admin/actions",
                            headers=entetes(jeton)).json()["actions"]
    assert [a["id"] for a in liste] == [action_id]
    assert liste[0]["statut"] == "en_attente"
    assert "coherence avec les donnees" in liste[0]["details"]["raison"]


def test_le_fichier_n_est_pas_touche_par_le_depot(client_docs):
    jeton = jeton_admin(client_docs)
    avant = (client_docs.dossier / "memoire.docx").read_bytes()
    deposer_via_outil(client_docs, jeton)
    assert (client_docs.dossier / "memoire.docx").read_bytes() == avant


# --- approbation --------------------------------------------------------------
def test_approbation_applique_et_sauvegarde(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    r = client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                         headers=entetes(jeton))
    assert r.status_code == 200
    resultat = r.json()["resultat"]
    assert resultat["n_occurrences"] == 1
    assert (client_docs.dossier / resultat["sauvegarde"]).exists()
    with zipfile.ZipFile(client_docs.dossier / "memoire.docx") as z:
        assert z.testzip() is None
        assert b"460 points" in z.read("word/document.xml")


def test_refus_ne_modifie_rien(client_docs):
    jeton = jeton_admin(client_docs)
    avant = (client_docs.dossier / "memoire.docx").read_bytes()
    action_id = deposer_via_outil(client_docs, jeton)
    r = client_docs.post("/jarvis/api/admin/actions/%s/reject" % action_id,
                         headers=entetes(jeton))
    assert r.status_code == 200
    assert (client_docs.dossier / "memoire.docx").read_bytes() == avant


def test_pas_de_double_application(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    assert client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                            headers=entetes(jeton)).status_code == 200
    r = client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                         headers=entetes(jeton))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "action_introuvable"


def test_identifiant_inconnu(client_docs):
    jeton = jeton_admin(client_docs)
    r = client_docs.post("/jarvis/api/admin/actions/inconnu/approve",
                         headers=entetes(jeton))
    assert r.status_code == 404


# --- cloisonnement ------------------------------------------------------------
def test_une_session_publique_ne_peut_pas_approuver(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    public = client_docs.post("/jarvis/api/session").json()["token"]
    r = client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                         headers=entetes(public))
    assert r.status_code == 403
    with zipfile.ZipFile(client_docs.dossier / "memoire.docx") as z:
        assert b"450 points" in z.read("word/document.xml")


def test_sans_jeton_aucune_approbation(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    assert client_docs.post(
        "/jarvis/api/admin/actions/%s/approve" % action_id).status_code == 401


def test_une_autre_session_admin_ne_peut_pas_approuver(client_docs):
    """Deux consoles ouvertes: la proposition faite dans l'une ne doit pas
    etre approuvable depuis l'autre."""
    jeton_a = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton_a)
    jeton_b = jeton_admin(client_docs)
    r = client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                         headers=entetes(jeton_b))
    assert r.status_code == 404
    assert client_docs.get("/jarvis/api/admin/actions",
                           headers=entetes(jeton_b)).json()["actions"] == []


def test_jeton_revoque_ne_peut_plus_approuver(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    client_docs.post("/jarvis/api/admin/logout", headers=entetes(jeton))
    assert client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                            headers=entetes(jeton)).status_code == 401


# --- audit --------------------------------------------------------------------
def test_application_tracee(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    client_docs.post("/jarvis/api/admin/actions/%s/approve" % action_id,
                     headers=entetes(jeton))
    journal = (Path(client_docs.settings.log_dir) / "admin.jsonl").read_text(encoding="utf-8")
    assert "action_appliquee" in journal
    assert action_id in journal
    assert "memoire.docx" in journal


def test_refus_trace(client_docs):
    jeton = jeton_admin(client_docs)
    action_id = deposer_via_outil(client_docs, jeton)
    client_docs.post("/jarvis/api/admin/actions/%s/reject" % action_id,
                     headers=entetes(jeton))
    journal = (Path(client_docs.settings.log_dir) / "admin.jsonl").read_text(encoding="utf-8")
    assert "action_refusee" in journal
