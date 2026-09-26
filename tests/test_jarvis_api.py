"""Tests de bout en bout sur l'application FastAPI, client Claude mocke."""
import pytest

from conftest import FakeClaude, sse_events

CHAT = "/jarvis/api/chat"
SYNC = "/jarvis/api/chat/sync"


def auth(token):
    return {"X-Jarvis-Session": token}


# --- sante -------------------------------------------------------------------
def test_health_repond_ok_quand_configure(client):
    r = client.get("/jarvis/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model"] == "claude-sonnet-5"
    assert body["configured"] is True


def test_health_signale_degrade_sans_cle(settings, fake_claude):
    """Le widget s'appuie sur ce champ pour afficher son mode degrade."""
    from fastapi.testclient import TestClient

    from jarvis.app import create_app
    settings.anthropic_api_key = ""
    with TestClient(create_app(settings)) as c:
        body = c.get("/jarvis/health").json()
    assert body["status"] == "degraded"
    assert body["configured"] is False


def test_health_ne_divulgue_aucun_secret(client):
    dump = client.get("/jarvis/health").text.lower()
    assert "sk-ant" not in dump
    assert "secret" not in dump


# --- sessions ----------------------------------------------------------------
def test_session_delivre_un_jeton_public(client):
    body = client.post("/jarvis/api/session").json()
    assert body["profile"] == "public"
    assert body["token"].count(".") == 1


def test_chat_sans_jeton_est_refuse(client):
    assert client.post(CHAT, json={"message": "bonjour"}).status_code == 401


def test_chat_avec_jeton_falsifie_est_refuse(client, token):
    r = client.post(CHAT, json={"message": "bonjour"},
                    headers=auth(token[:-3] + "zzz"))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_session"


def test_profil_admin_ne_peut_pas_etre_force(client, settings):
    """Phase 4 anticipee: forger un jeton admin sans le secret est impossible."""
    import base64

    from jarvis.session import issue_token
    _, info = issue_token(settings.secret_key, "public")
    forged = base64.urlsafe_b64encode(
        ("%s:admin:%d" % (info.session_id, info.issued_at)).encode()
    ).decode().rstrip("=") + ".signaturebidon"
    assert client.post(CHAT, json={"message": "hi"},
                       headers=auth(forged)).status_code == 401


# --- validation d'entree -----------------------------------------------------
@pytest.mark.parametrize("payload", [
    {"message": ""},
    {"message": "   "},
    {"message": "x" * 5000},
    {"message": "ok", "conversation_id": "../../etc/passwd"},
    {},
])
def test_charges_invalides_rejetees_avant_tout_appel_api(client, token, payload):
    r = client.post(CHAT, json=payload, headers=auth(token))
    assert r.status_code == 422
    assert client.fake.calls == []   # aucun appel facture


def test_message_trop_long_pour_la_config(client, token):
    """Le schema plafonne a 4000, la config de ce test a 500."""
    r = client.post(CHAT, json={"message": "m" * 600}, headers=auth(token))
    assert r.status_code == 413
    assert client.fake.calls == []


# --- streaming ----------------------------------------------------------------
def test_flux_complet(client, token):
    r = client.post(CHAT, json={"message": "Bonjour Jarvis"}, headers=auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-accel-buffering"] == "no"

    events = sse_events(r.text)
    noms = [n for n, _ in events]
    assert noms[0] == "meta"
    assert noms[-1] == "done"
    assert "delta" in noms

    texte = "".join(d["text"] for n, d in events if n == "delta")
    assert texte == "Bonjour, je suis Jarvis."
    assert events[-1][1]["usage"]["output_tokens"] == 30


def test_la_conversation_se_poursuit(client, token):
    first = sse_events(
        client.post(CHAT, json={"message": "Question 1"}, headers=auth(token)).text
    )
    conv_id = first[0][1]["conversation_id"]

    client.post(CHAT, json={"message": "Question 2", "conversation_id": conv_id},
                headers=auth(token))

    envoye = client.fake.calls[-1]["messages"]
    assert [m["content"] for m in envoye] == [
        "Question 1", "Bonjour, je suis Jarvis.", "Question 2",
    ]


def test_le_fil_d_un_autre_visiteur_est_inaccessible(client, token):
    conv_id = sse_events(
        client.post(CHAT, json={"message": "prive"}, headers=auth(token)).text
    )[0][1]["conversation_id"]

    autre = client.post("/jarvis/api/session").json()["token"]
    r = client.post(CHAT, json={"message": "je regarde", "conversation_id": conv_id},
                    headers=auth(autre))
    assert r.status_code == 403


def test_relecture_de_la_conversation(client, token):
    conv_id = sse_events(
        client.post(CHAT, json={"message": "Bonjour"}, headers=auth(token)).text
    )[0][1]["conversation_id"]

    body = client.get("/jarvis/api/conversation/" + conv_id, headers=auth(token)).json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "Bonjour"


def test_relecture_refusee_a_un_tiers(client, token):
    conv_id = sse_events(
        client.post(CHAT, json={"message": "Bonjour"}, headers=auth(token)).text
    )[0][1]["conversation_id"]
    autre = client.post("/jarvis/api/session").json()["token"]
    assert client.get("/jarvis/api/conversation/" + conv_id,
                      headers=auth(autre)).status_code == 403


# --- erreurs en amont ---------------------------------------------------------
def test_panne_api_devient_un_evenement_erreur_propre(client, token):
    """La traduction des exceptions SDK est testee dans
    test_jarvis_claude_client.py; ici on verifie que l'erreur deja traduite
    ressort en evenement SSE propre, sans detail technique."""
    from jarvis.errors import UpstreamError
    client.app.state.ctx.claude = FakeClaude(error=UpstreamError(
        "L'assistant est injoignable pour le moment. Reessayez dans un instant.",
        code="upstream_unreachable"))
    events = sse_events(
        client.post(CHAT, json={"message": "test"}, headers=auth(token)).text)
    noms = [n for n, _ in events]
    assert "error" in noms and "done" not in noms

    erreur = [d for n, d in events if n == "error"][0]
    assert erreur["code"] == "upstream_unreachable"
    # Aucun detail technique ne doit remonter au visiteur.
    assert "Traceback" not in erreur["message"]
    assert "anthropic" not in erreur["message"].lower()


def test_echec_en_cours_de_flux_conserve_le_partiel(client, token):
    from jarvis.errors import UpstreamError
    client.app.state.ctx.claude = FakeClaude(
        reply="un deux trois quatre", error=UpstreamError(), fail_after=2)

    events = sse_events(
        client.post(CHAT, json={"message": "test"}, headers=auth(token)).text)
    conv_id = events[0][1]["conversation_id"]
    assert "error" in [n for n, _ in events]

    relu = client.get("/jarvis/api/conversation/" + conv_id, headers=auth(token)).json()
    assert relu["messages"][-1]["content"] == "un deux "


def test_echec_immediat_n_ecrit_rien_dans_le_fil(client, token):
    """L'utilisateur doit pouvoir relancer sans polluer l'historique."""
    from jarvis.errors import UpstreamError
    client.app.state.ctx.claude = FakeClaude(error=UpstreamError())
    conv_id = sse_events(
        client.post(CHAT, json={"message": "test"}, headers=auth(token)).text
    )[0][1]["conversation_id"]

    relu = client.get("/jarvis/api/conversation/" + conv_id, headers=auth(token)).json()
    assert relu["messages"] == []


# --- rate limiting ------------------------------------------------------------
def test_limitation_de_debit(client, token):
    """Capacite 5 dans la config de test."""
    codes = [client.post(CHAT, json={"message": "msg %d" % i},
                         headers=auth(token)).status_code for i in range(7)]
    assert codes[:5] == [200] * 5
    assert 429 in codes[5:]

    r = client.post(CHAT, json={"message": "encore"}, headers=auth(token))
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert r.json()["error"]["code"] == "rate_limited"


# --- route non streamee -------------------------------------------------------
def test_chat_sync(client, token):
    body = client.post(SYNC, json={"message": "Bonjour"}, headers=auth(token)).json()
    assert body["reply"] == "Bonjour, je suis Jarvis."
    assert body["usage"]["output_tokens"] == 30


def test_chat_sync_sans_jeton(client):
    assert client.post(SYNC, json={"message": "hi"}).status_code == 401


# --- widget -------------------------------------------------------------------
def test_widget_est_servi_sans_placeholder(client):
    html = client.get("/jarvis/widget.html").text
    assert "__JARVIS_API_BASE__" not in html
    assert "__JARVIS_DARK__" not in html
    assert "sk-ant" not in html


# --- prompt systeme -----------------------------------------------------------
def test_le_prompt_systeme_interdit_l_invention_de_chiffres():
    """Phase 2: la regle n est plus "pas de chiffres" mais "pas de chiffre
    sans outil". Le garde-fou doit rester explicite, sans quoi le modele
    completerait de memoire les valeurs qu un outil ne lui donne pas."""
    from jarvis.claude_client import load_system_prompt
    prompt = load_system_prompt("system_public")
    assert "Aucun chiffre sans outil" in prompt
    assert "appel d'outil" in prompt
    assert "CLIMAT-SEN" in prompt


def test_le_prompt_systeme_declare_les_quatre_outils():
    from jarvis.claude_client import load_system_prompt
    from jarvis import tools
    prompt = load_system_prompt("system_public")
    for spec in tools.specs_for("public"):
        assert spec["name"] in prompt


def test_le_prompt_systeme_impose_la_langue_de_la_question():
    """Regression : la consigne vivait dans la section Style, en fin de prompt,
    et etait ignoree - une question en anglais recevait une reponse en francais.
    Elle est desormais une regle absolue."""
    from jarvis.claude_client import load_system_prompt
    prompt = load_system_prompt("system_public")
    assert "**Réponds toujours dans la langue de la question.**" in prompt
    regles = prompt.split("## Règles absolues")[1].split("## Style")[0]
    assert "langue de la question" in regles


# --- widget : non-regression sur la mise en page du dashboard ------------------
def test_le_widget_ne_touche_aucun_conteneur_parent():
    """Regression : une version du widget remontait trois niveaux de parents
    pour y forcer height:0, afin de ne pas reserver de place dans le flux.
    Trois niveaux au-dessus de l iframe se trouve stVerticalBlock, le conteneur
    de tout le contenu de la page : le dashboard disparaissait.

    Le widget ne doit styler que sa propre iframe. La place dans le flux est
    neutralisee cote Python, en publiant le composant avec une hauteur de 0.
    """
    from jarvis.widget_html import WIDGET_FILE
    source = WIDGET_FILE.read_text(encoding="utf-8")
    for interdit in ("parentElement", "parentNode.style", "ownerDocument.body.style"):
        assert interdit not in source, (
            "le widget manipule le DOM parent via %r" % interdit)


def test_le_composant_a_une_hauteur_de_repli_visible():
    """Arbitrage assume : une hauteur de 0 ne reserve aucune place dans le
    flux, mais rend la bulle INVISIBLE si l epinglage en position:fixed echoue
    cote navigateur -- sans le moindre message. Un widget invisible est pire
    qu un espace de 76 px en bas de page."""
    import re
    from pathlib import Path
    source = Path("scripts/jarvis_widget.py").read_text(encoding="utf-8")
    appel = re.search(r"components\.html\((.*?)\)", source, re.S)
    assert appel, "appel a components.html introuvable"
    assert "height=HAUTEUR_REPLIEE" in appel.group(1)
    assert "HAUTEUR_REPLIEE = 76" in source


def test_le_widget_s_epingle_en_position_fixe():
    from jarvis.widget_html import WIDGET_FILE
    source = WIDGET_FILE.read_text(encoding="utf-8")
    assert '"position": "fixed"' in source
    # Un filet de securite doit exister si l epinglage echoue (ancetre creant
    # un bloc conteneur) : sinon la bulle serait invisible, hauteur 0 cote flux.
    assert "verifierVisibilite" in source
    assert "setFrameHeight" in source


def test_le_javascript_du_widget_est_syntaxiquement_valide():
    """Une erreur de syntaxe tuerait le widget en silence : l iframe se charge,
    aucun script ne s execute, la bulle n apparait jamais et rien ne le signale.
    """
    import re
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node absent : validation de syntaxe JS impossible")

    from jarvis.widget_html import render_widget
    html = render_widget("/jarvis", True)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "aucun bloc script dans le widget"

    for i, code in enumerate(scripts):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / ("bloc_%d.js" % i)
            f.write_text(code, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)],
                               capture_output=True, text=True)
            assert r.returncode == 0, "bloc %d invalide :\n%s" % (i, r.stderr)


def test_le_widget_peut_etre_coupe_par_variable_d_environnement(monkeypatch):
    """Arret d urgence : si la bulle perturbe la mise en page en production,
    on doit pouvoir la retirer sans redeployer de code."""
    import sys
    sys.path.insert(0, "scripts")
    import jarvis_widget

    monkeypatch.setenv("JARVIS_WIDGET", "off")
    assert jarvis_widget.est_active() is False
    assert jarvis_widget.render() is False      # n appelle meme pas Streamlit

    for valeur in ("on", "1", "true", ""):
        monkeypatch.setenv("JARVIS_WIDGET", valeur)
        assert jarvis_widget.est_active() is True
    monkeypatch.delenv("JARVIS_WIDGET")
    assert jarvis_widget.est_active() is True


# --- widget : dimensionnement et persistance ----------------------------------
def test_le_panneau_s_adapte_a_la_hauteur_de_la_fenetre():
    """Regression : une hauteur figee de 620 px occupait 91 % d un ecran de
    portable (680 px), donnant l impression que le dashboard etait masque."""
    from jarvis.widget_html import WIDGET_FILE
    source = WIDGET_FILE.read_text(encoding="utf-8")
    assert "function hauteurPanneau()" in source
    assert "window.innerHeight" in source
    assert "H_OPEN = 620" not in source


def test_l_ouverture_du_panneau_survit_aux_reexecutions_streamlit():
    """Streamlit reexecute son script a chaque interaction et remonte l iframe.
    Sans persistance, un clic sur un onglet du dashboard refermait le panneau
    et faisait disparaitre la conversation de l ecran."""
    from jarvis.widget_html import WIDGET_FILE
    source = WIDGET_FILE.read_text(encoding="utf-8")
    assert 'remember("open"' in source
    assert 'recall("open")' in source


@pytest.mark.parametrize("demande,attendu", [
    ("flottant", "flottant"),
    ("pousse", "pousse"),
    ("POUSSE", "flottant"),        # la casse est normalisee par _mode(), pas ici
    ("inconnu", "flottant"),
    ("", "flottant"),
])
def test_mode_d_affichage_valide(demande, attendu):
    """render_widget sert aussi le widget en autonome, hors Streamlit, ou il n
    y a aucun conteneur a decaler : son repli est donc "flottant". Le defaut
    "pousse" appartient a l injection Streamlit (_mode dans jarvis_widget.py)."""
    from jarvis.widget_html import render_widget
    html = render_widget("/jarvis", True, demande)
    assert ('MODE  = "%s"' % attendu) in html


def test_le_mode_pousse_ne_modifie_que_la_marge():
    """Garde-fou : le mode "pousse" touche au DOM parent, il ne doit y ecrire
    QUE padding-right, sur une cible explicite, et savoir revenir en arriere."""
    from jarvis.widget_html import WIDGET_FILE
    source = WIDGET_FILE.read_text(encoding="utf-8")
    fonction = source.split("function pousser(")[1].split("\n  }")[0]
    assert "paddingRight" in fonction
    for interdit in ("height", "display", "position", "overflow", "remove()"):
        assert interdit not in fonction, (
            "le mode pousse modifie %r sur le DOM parent" % interdit)


def test_le_mode_par_defaut_recouvre_sans_deplacer(monkeypatch):
    """La carte se superpose au dashboard sans rien deplacer.

    Le defaut a longtemps ete "pousse" sur la foi d une mesure (129 elements
    de contenu passaient sous le panneau en flottant, 0 en pousse). L argument
    est tombe quand la carte est devenue redimensionnable : c est
    l utilisateur qui decide de la place qu elle prend, et voir la mise en
    page se reorganiser a chaque ouverture derange davantage qu un coin
    masque.
    """
    import sys
    sys.path.insert(0, "scripts")
    import jarvis_widget

    monkeypatch.delenv("JARVIS_WIDGET_MODE", raising=False)
    assert jarvis_widget._mode() == "flottant"


def test_le_mode_pousse_reste_disponible(monkeypatch):
    import sys
    sys.path.insert(0, "scripts")
    import jarvis_widget

    monkeypatch.setenv("JARVIS_WIDGET_MODE", "pousse")
    assert jarvis_widget._mode() == "pousse"
    monkeypatch.setenv("JARVIS_WIDGET_MODE", "flottant")
    assert jarvis_widget._mode() == "flottant"
    # Valeur invalide : on retombe sur le defaut, qui recouvre sans deplacer.
    monkeypatch.setenv("JARVIS_WIDGET_MODE", "nimporte quoi")
    assert jarvis_widget._mode() == "flottant"


def test_la_poussee_est_desactivee_sur_ecran_etroit():
    """Decaler de 400 px sur un ecran de 900 px ecraserait le contenu : le
    widget doit retomber sur le recouvrement."""
    from jarvis.widget_html import WIDGET_FILE
    source = WIDGET_FILE.read_text(encoding="utf-8")
    assert "LARGEUR_MINI_POUSSEE" in source
    assert "vue().w < LARGEUR_MINI_POUSSEE" in source


@pytest.mark.parametrize("scenario", ["replie", "ouvert", "fenetre_ouvert",
                                      "mobile_replie", "mobile_ouvert"])
def test_le_widget_s_affiche_reellement(scenario, tmp_path):
    """Execute le JavaScript du widget dans un DOM simule (tests/widget_harness.js).

    Reproduit la seule situation qui compte : un script qui tourne DANS une
    iframe, dont les dimensions propres n ont rien a voir avec celles de la
    page hote. Le widget confondait les deux : il comparait la position de la
    bulle dans la page (~572 px) a la hauteur de sa propre iframe (76 px),
    concluait "hors ecran", effacait le style de la bulle -- et la bulle
    disparaissait.

    Ce harnais echoue sur la version fautive et passe sur la version corrigee.
    """
    import re
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node absent : execution du widget impossible")

    harnais = Path("tests/widget_harness.js")
    assert harnais.exists(), "harnais de test du widget introuvable"

    from jarvis.widget_html import render_widget
    html = render_widget("/jarvis", True, "flottant")
    script = re.search(r"<script>(.*?)</script>", html, re.S)
    assert script, "aucun bloc script dans le widget"

    fichier = tmp_path / "widget.js"
    fichier.write_text(script.group(1), encoding="utf-8")

    args = [node, str(harnais), str(fichier)]
    if scenario.endswith("ouvert"):
        args.append("ouvert")
    if scenario.startswith("fenetre"):
        args.append("fenetre")
    if scenario.startswith("mobile"):
        args.append("mobile")
    r = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "\n" + r.stdout + r.stderr
