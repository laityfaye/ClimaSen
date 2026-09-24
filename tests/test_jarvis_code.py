"""Code et taches (Phase 10): regles de lecture/ecriture, modification,
annulation, taches, outils et routes.

Les operations sur les fichiers portent sur un projet TEMPORAIRE: PROJECT_DIR
de jarvis.code_ops est redirige vers tmp_path, aucun fichier du vrai depot
n'est touche.
"""
import json
import sys
import time

import pytest

from jarvis import actions, code_ops
from jarvis.code_ops import RefusCode
from jarvis.tools import code as outils_code
from jarvis.tools.common import ToolInputError

CHAT = "/jarvis/api/chat"


@pytest.fixture
def projet(tmp_path, monkeypatch):
    for dossier in ("scripts/pages", "src", "tests", "jarvis", "deploy",
                    "data/raw", ".git", "venv"):
        (tmp_path / dossier).mkdir(parents=True)
    (tmp_path / "scripts/04_analyse.py").write_text(
        "SEUIL = 0.05\n\n\ndef f(x):\n    return x * 2\n", encoding="utf-8")
    (tmp_path / "scripts/pages/page.py").write_text("A = 1\nA = 1\n", encoding="utf-8")
    (tmp_path / "jarvis/app.py").write_text("SECRET = 1\n", encoding="utf-8")
    (tmp_path / "deploy/nginx.conf").write_text("server {}\n", encoding="utf-8")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-x\n", encoding="utf-8")
    (tmp_path / "data/raw/gros.csv").write_text("a\n", encoding="utf-8")
    (tmp_path / "scripts/credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tests/test_exemple.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    monkeypatch.setattr(code_ops, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(code_ops, "DOSSIER_JARVIS", tmp_path / ".jarvis")
    monkeypatch.setattr(code_ops, "SAUVEGARDES", tmp_path / ".jarvis" / "sauvegardes")
    return tmp_path


# --- lecture ---------------------------------------------------------------------
def test_lire_un_fichier_avec_numeros_de_ligne(projet):
    res = code_ops.lire("scripts/04_analyse.py")
    assert res["lignes_totales"] == 5
    assert res["contenu"].splitlines()[0] == "    1  SEUIL = 0.05"
    assert res["modifiable_par_jarvis"] is True


def test_lire_par_tranches(projet):
    (projet / "scripts/long.py").write_text("\n".join("x%d = %d" % (i, i) for i in range(900)),
                                            encoding="utf-8")
    res = code_ops.lire("scripts/long.py")
    assert res["debut"] == 1 and res["suite"] is True
    assert len(res["contenu"]) <= code_ops.MAX_CARACTERES_LUS + 50
    suite = code_ops.lire("scripts/long.py", res["fin"] + 1)
    assert suite["debut"] == res["fin"] + 1


@pytest.mark.parametrize("chemin", [
    ".env", "../secret.txt", "/etc/passwd", "C:/Windows/win.ini",
    ".git/config", "venv/lib.py", "data/raw/gros.csv",
    "scripts/credentials.json", "scripts/../../dehors.py",
])
def test_lectures_interdites(projet, chemin):
    with pytest.raises(RefusCode):
        code_ops.lire(chemin)


def test_jarvis_lisible_mais_pas_modifiable(projet):
    assert code_ops.lire("jarvis/app.py")["modifiable_par_jarvis"] is False


def test_lister_masque_les_interdits(projet):
    noms = {e["nom"] for e in code_ops.lister("")["entrees"]}
    assert "scripts/" in noms and "jarvis/" in noms
    assert not noms & {".git/", "venv/", ".env"}
    assert {e["nom"] for e in code_ops.lister("scripts")["entrees"]} >= {"04_analyse.py", "pages/"}


def test_chercher(projet):
    res = code_ops.chercher("SEUIL")
    assert res["resultats"][0] == {"fichier": "scripts/04_analyse.py", "ligne": 1,
                                   "texte": "SEUIL = 0.05"}


def test_chercher_ne_fouille_pas_les_secrets(projet):
    assert code_ops.chercher("ANTHROPIC_API_KEY")["resultats"] == []


def test_motif_invalide_traite_comme_texte(projet):
    assert code_ops.chercher("return x *")["resultats"][0]["ligne"] == 5


# --- preparation d'une modification -----------------------------------------------
def test_preparer_un_remplacement(projet):
    prep = code_ops.preparer_modification("scripts/04_analyse.py",
                                          "SEUIL = 0.05", "SEUIL = 0.01")
    assert prep["mode"] == "remplacement"
    assert "-SEUIL = 0.05" in prep["diff"] and "+SEUIL = 0.01" in prep["diff"]
    assert prep["lignes_ajoutees"] == 1 and prep["lignes_retirees"] == 1
    # Rien n'est ecrit a la preparation.
    assert (projet / "scripts/04_analyse.py").read_text().startswith("SEUIL = 0.05")


def test_preparer_une_creation(projet):
    prep = code_ops.preparer_modification("tests/test_nouveau.py", "",
                                          "def test_x():\n    pass\n")
    assert prep["mode"] == "creation" and prep["empreinte_avant"] is None
    assert not (projet / "tests/test_nouveau.py").exists()


@pytest.mark.parametrize("chemin", [
    "jarvis/app.py", "deploy/nginx.conf", ".env", "requirements.txt",
    "scripts/jarvis_widget.py", "scripts/outil.exe", "../dehors.py",
])
def test_ecritures_interdites(projet, chemin):
    with pytest.raises(RefusCode):
        code_ops.preparer_modification(chemin, "", "x = 1\n")


def test_code_qui_ne_compile_pas_refuse(projet):
    with pytest.raises(RefusCode, match="ne compile pas"):
        code_ops.preparer_modification("scripts/04_analyse.py",
                                       "return x * 2", "return x *")


def test_texte_ambigu_refuse(projet):
    with pytest.raises(RefusCode, match="2 fois"):
        code_ops.preparer_modification("scripts/pages/page.py", "A = 1", "A = 2")
    prep = code_ops.preparer_modification("scripts/pages/page.py", "A = 1", "A = 2",
                                          toutes=True)
    assert prep["contenu"] == "A = 2\nA = 2\n"


@pytest.mark.parametrize("ancien, nouveau, message", [
    ("INTROUVABLE", "x", "introuvable"),
    ("SEUIL = 0.05", "SEUIL = 0.05", "ne change rien"),
    ("", "x = 1\n", "existe deja"),
])
def test_autres_refus(projet, ancien, nouveau, message):
    with pytest.raises(RefusCode, match=message):
        code_ops.preparer_modification("scripts/04_analyse.py", ancien, nouveau)


# --- application et annulation ------------------------------------------------------
def test_appliquer_puis_annuler(projet):
    prep = code_ops.preparer_modification("scripts/04_analyse.py",
                                          "SEUIL = 0.05", "SEUIL = 0.01")
    res = code_ops.appliquer_modification(prep)
    fichier = projet / "scripts/04_analyse.py"
    assert fichier.read_text().startswith("SEUIL = 0.01")
    assert (projet / res["sauvegarde"]).read_text().startswith("SEUIL = 0.05")
    assert res["sauvegarde"].startswith(".jarvis/sauvegardes/")

    code_ops.annuler_modification(res)
    assert fichier.read_text().startswith("SEUIL = 0.05")


def test_fichier_modifie_entre_proposition_et_approbation(projet):
    prep = code_ops.preparer_modification("scripts/04_analyse.py",
                                          "SEUIL = 0.05", "SEUIL = 0.01")
    (projet / "scripts/04_analyse.py").write_text("SEUIL = 0.05\n# retouche\n")
    with pytest.raises(RefusCode, match="a change"):
        code_ops.appliquer_modification(prep)
    assert "retouche" in (projet / "scripts/04_analyse.py").read_text()


def test_annulation_refusee_si_retouche_depuis(projet):
    prep = code_ops.preparer_modification("scripts/04_analyse.py",
                                          "SEUIL = 0.05", "SEUIL = 0.01")
    res = code_ops.appliquer_modification(prep)
    (projet / "scripts/04_analyse.py").write_text("travail de Laity\n")
    with pytest.raises(RefusCode, match="modifie depuis"):
        code_ops.annuler_modification(res)
    assert (projet / "scripts/04_analyse.py").read_text() == "travail de Laity\n"


def test_creation_puis_annulation_supprime(projet):
    prep = code_ops.preparer_modification("tests/test_nouveau.py", "", "X = 1\n")
    res = code_ops.appliquer_modification(prep)
    assert (projet / "tests/test_nouveau.py").exists() and res["sauvegarde"] is None
    code_ops.annuler_modification(res)
    assert not (projet / "tests/test_nouveau.py").exists()


def test_payload_revalide_a_l_application(projet):
    """Un payload trafique (chemin interdit) est refuse meme approuve."""
    with pytest.raises(RefusCode):
        code_ops.appliquer_modification({"fichier": "jarvis/app.py", "contenu": "x=1\n",
                                         "empreinte_avant": None})
    with pytest.raises(RefusCode, match="ne compile pas"):
        code_ops.appliquer_modification({"fichier": "scripts/n.py", "contenu": "def (",
                                         "empreinte_avant": None})


# --- taches ------------------------------------------------------------------------------
def test_preparer_tache_pytest(projet):
    t = code_ops.preparer_tache("pytest", "tests/test_exemple.py")
    assert t["commande"][-1] == "tests/test_exemple.py"
    assert code_ops.preparer_tache("pytest")["cible"] == "tests/"


@pytest.mark.parametrize("script, cible", [
    ("rm -rf /", None), ("pytest", "../evil.py"), ("pytest", "tests/conftest.py"),
    ("pytest", "tests/test_absent.py"), ("pytest", "tests/test_x.py; rm -rf ."),
])
def test_taches_refusees(projet, script, cible, monkeypatch):
    monkeypatch.setattr(code_ops, "scripts_autorises",
                        lambda: {"04_analyse.py": "Analyse"})
    with pytest.raises(RefusCode):
        code_ops.preparer_tache(script, cible)


def test_script_du_pipeline_autorise(projet, monkeypatch):
    monkeypatch.setattr(code_ops, "scripts_autorises",
                        lambda: {"04_analyse.py": "Analyse"})
    t = code_ops.preparer_tache("04_analyse.py")
    assert t["commande"][1:] == ["scripts/04_analyse.py"]


def test_environnement_sans_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("JARVIS_SECRET_KEY", "k" * 48)
    monkeypatch.setenv("CHEMIN_UTILE", "ok")
    env = code_ops._environnement()
    assert "ANTHROPIC_API_KEY" not in env and "JARVIS_SECRET_KEY" not in env
    assert env["CHEMIN_UTILE"] == "ok" and env["MPLBACKEND"] == "Agg"


def test_une_tache_a_la_fois_et_resultat(projet):
    taches = code_ops.Taches()
    fin = []
    lente = [sys.executable, "-c", "import time; time.sleep(1); print('fini')"]
    taches.lancer(lente, 30, fin.append)
    with pytest.raises(RefusCode, match="deja en cours"):
        taches.lancer(lente, 30, fin.append)
    for _ in range(100):
        if fin:
            break
        time.sleep(0.1)
    assert fin[0]["reussi"] is True and "fini" in fin[0]["sortie_fin"]
    assert not taches.occupe()


def test_tache_trop_longue_interrompue(projet):
    taches = code_ops.Taches()
    fin = []
    taches.lancer([sys.executable, "-c", "import time; time.sleep(10)"], 1, fin.append)
    for _ in range(100):
        if fin:
            break
        time.sleep(0.1)
    assert fin[0]["reussi"] is False and "Delai depasse" in fin[0]["erreur"]


# --- outils ---------------------------------------------------------------------------------
def test_outils_de_code_reserves_a_l_admin():
    from jarvis import tools
    publics = {s["name"] for s in tools.specs_for("public")}
    admins = {s["name"] for s in tools.specs_for("admin")}
    nouveaux = {"read_code", "propose_code_edit", "propose_task", "get_task_status"}
    assert not publics & nouveaux
    assert nouveaux <= admins


def test_outil_propose_ne_modifie_rien(projet, settings):
    registre = actions.RegistreActions()
    res = outils_code.ProposeCodeEdit.run(
        {"path": "scripts/04_analyse.py", "old_text": "SEUIL = 0.05",
         "new_text": "SEUIL = 0.01", "reason": "Seuil plus strict"},
        {}, settings=settings, session_id="s", registre=registre)
    assert res["statut"] == "proposition_deposee"
    assert (projet / "scripts/04_analyse.py").read_text().startswith("SEUIL = 0.05")
    vue = registre.lister("s")[0]
    assert vue["type"] == "code_modifier" and "+SEUIL = 0.01" in vue["details"]["diff"]
    # Le contenu complet reste cote serveur, hors de la vue envoyee au client.
    assert "contenu" not in json.dumps(vue["details"])


def test_outil_refus_remonte_au_modele(projet, settings):
    with pytest.raises(ToolInputError, match="seuls scripts/"):
        outils_code.ProposeCodeEdit.run(
            {"path": "jarvis/app.py", "old_text": "SECRET = 1", "new_text": "SECRET = 2",
             "reason": "test"}, {}, settings=settings, session_id="s",
            registre=actions.RegistreActions())


def test_interrupteur_coupe_les_propositions(projet, settings):
    settings.code_actions_enabled = False
    with pytest.raises(ToolInputError, match="desactivees"):
        outils_code.ProposeTask.run({"script": "pytest", "reason": "r"}, {},
                                    settings=settings, session_id="s",
                                    registre=actions.RegistreActions())


def test_read_code_outil(projet):
    res = outils_code.ReadCode.run({"action": "chercher", "pattern": "def f"}, {})
    assert res["resultats"][0]["ligne"] == 4
    with pytest.raises(ToolInputError):
        outils_code.ReadCode.run({"action": "lire", "path": ".env"}, {})


def test_get_task_status_masque_le_diff(settings):
    registre = actions.RegistreActions()
    registre.deposer("s", "code_modifier", "r", {"diff": "gros diff", "fichier": "f"}, {})
    res = outils_code.GetTaskStatus.run({}, {}, session_id="s", registre=registre)
    assert res["n"] == 1 and "diff" not in res["propositions"][0]["details"]
    assert outils_code.GetTaskStatus.run({}, {}, session_id="autre",
                                         registre=registre)["n"] == 0


# --- routes -----------------------------------------------------------------------------------
def _admin(client):
    from jarvis.session import issue_token
    token, info = issue_token(client.settings.secret_key, profile="admin")
    return {"X-Jarvis-Session": token}, info.session_id


def test_approuver_puis_annuler_par_les_routes(client, projet):
    entetes, sid = _admin(client)
    ctx = client.app.state.ctx
    outils_code.ProposeCodeEdit.run(
        {"path": "scripts/04_analyse.py", "old_text": "SEUIL = 0.05",
         "new_text": "SEUIL = 0.01", "reason": "r"},
        {}, settings=client.settings, session_id=sid, registre=ctx.actions)
    aid = ctx.actions.lister(sid)[0]["id"]

    r = client.post("/jarvis/api/admin/actions/%s/approve" % aid, headers=entetes)
    assert r.status_code == 200 and r.json()["statut"] == "appliquee"
    assert (projet / "scripts/04_analyse.py").read_text().startswith("SEUIL = 0.01")

    r = client.post("/jarvis/api/admin/actions/%s/revert" % aid, headers=entetes)
    assert r.status_code == 200 and r.json()["statut"] == "annulee"
    assert (projet / "scripts/04_analyse.py").read_text().startswith("SEUIL = 0.05")

    # Deux annulations de suite: la seconde est refusee.
    assert client.post("/jarvis/api/admin/actions/%s/revert" % aid,
                       headers=entetes).status_code == 409


def test_annulation_reservee_a_la_session_admin(client, projet):
    entetes, sid = _admin(client)
    ctx = client.app.state.ctx
    outils_code.ProposeCodeEdit.run(
        {"path": "scripts/04_analyse.py", "old_text": "SEUIL = 0.05",
         "new_text": "SEUIL = 0.01", "reason": "r"},
        {}, settings=client.settings, session_id=sid, registre=ctx.actions)
    aid = ctx.actions.lister(sid)[0]["id"]
    client.post("/jarvis/api/admin/actions/%s/approve" % aid, headers=entetes)

    autre, _ = _admin(client)
    assert client.post("/jarvis/api/admin/actions/%s/revert" % aid,
                       headers=autre).status_code == 404
    public = client.post("/jarvis/api/session").json()["token"]
    assert client.post("/jarvis/api/admin/actions/%s/revert" % aid,
                       headers={"X-Jarvis-Session": public}).status_code == 403


def test_tache_lancee_en_arriere_plan(client, projet, monkeypatch):
    entetes, sid = _admin(client)
    ctx = client.app.state.ctx
    outils_code.ProposeTask.run({"script": "pytest", "test_file": "tests/test_exemple.py",
                                 "reason": "verifier"}, {}, settings=client.settings,
                                session_id=sid, registre=ctx.actions)
    aid = ctx.actions.lister(sid)[0]["id"]
    r = client.post("/jarvis/api/admin/actions/%s/approve" % aid, headers=entetes)
    assert r.status_code == 200 and r.json()["statut"] == "en_cours"
    for _ in range(300):
        vue = ctx.actions.lister(sid)[0]
        if vue["statut"] != "en_cours":
            break
        time.sleep(0.1)
    assert vue["statut"] == "terminee", vue
    assert vue["resultat"]["reussi"] is True and "1 passed" in vue["resultat"]["sortie_fin"]


def test_interrupteur_vaut_aussi_a_l_approbation(client, projet):
    entetes, sid = _admin(client)
    ctx = client.app.state.ctx
    outils_code.ProposeCodeEdit.run(
        {"path": "scripts/04_analyse.py", "old_text": "SEUIL = 0.05",
         "new_text": "SEUIL = 0.01", "reason": "r"},
        {}, settings=client.settings, session_id=sid, registre=ctx.actions)
    aid = ctx.actions.lister(sid)[0]["id"]
    client.settings.code_actions_enabled = False
    r = client.post("/jarvis/api/admin/actions/%s/approve" % aid, headers=entetes)
    assert r.status_code == 403
    assert (projet / "scripts/04_analyse.py").read_text().startswith("SEUIL = 0.05")


def test_prompt_admin_decrit_les_outils_de_code():
    from jarvis.claude_client import load_system_prompt
    prompt = load_system_prompt("system_admin")
    for nom in ("read_code", "propose_code_edit", "propose_task", "get_task_status"):
        assert nom in prompt


def test_admin_a_plus_de_tours_d_outils(settings):
    from jarvis.claude_client import ClaudeClient
    c = ClaudeClient(settings)
    assert c._tours_max("admin") > c._tours_max("public")
