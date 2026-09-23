"""Boucle d outils du client Claude et cablage HTTP.

Le SDK Anthropic n est jamais joint: un faux client restitue des reponses
pre-ecrites, dont des tours stop_reason="tool_use".
"""
import json

import pytest

from jarvis.claude_client import ClaudeClient
from tests.conftest import sse_events


# --- doubles du SDK ----------------------------------------------------------
class BlocTexte:
    type = "text"

    def __init__(self, text):
        self.text = text


class BlocOutil:
    type = "tool_use"

    def __init__(self, nom, arguments, identifiant="tu_1"):
        self.name = nom
        self.input = arguments
        self.id = identifiant


class BlocReflexion:
    type = "thinking"

    def __init__(self, texte="reflexion", signature="sig"):
        self.thinking = texte
        self.signature = signature


class Usage:
    def __init__(self, entree=100, sortie=20):
        self.input_tokens = entree
        self.output_tokens = sortie
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class Reponse:
    def __init__(self, content, stop_reason="end_turn", usage=None):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage or Usage()


class FluxFactice:
    def __init__(self, reponse):
        self._reponse = reponse

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def _generer():
            for bloc in self._reponse.content:
                if getattr(bloc, "type", None) == "text":
                    yield bloc.text
        return _generer()

    async def get_final_message(self):
        return self._reponse


class MessagesFactices:
    def __init__(self, reponses):
        self._reponses = list(reponses)
        self.appels = []

    def _suivante(self, kwargs):
        self.appels.append(kwargs)
        return self._reponses.pop(0) if self._reponses else Reponse([BlocTexte("fin")])

    def stream(self, **kwargs):
        return FluxFactice(self._suivante(kwargs))

    async def create(self, **kwargs):
        return self._suivante(kwargs)


class SdkFactice:
    def __init__(self, reponses):
        self.messages = MessagesFactices(reponses)


def clienter(settings, reponses):
    sdk = SdkFactice(reponses)
    return ClaudeClient(settings, client=sdk), sdk


OUTILS = [{"name": "get_sst_index", "description": "x",
           "input_schema": {"type": "object", "properties": {}}}]


def executeur(journal):
    async def executer(nom, arguments):
        journal.append((nom, arguments))
        return {"content": json.dumps({"indice": nom}), "is_error": False}
    return executer


async def collecter(flux):
    textes, evenements, final = [], [], None
    async for element in flux:
        if isinstance(element, dict):
            if element.get("type") == "tools":
                evenements.append(element)
            else:
                final = element
        else:
            textes.append(element)
    return "".join(textes), evenements, final


# --- boucle en streaming -----------------------------------------------------
@pytest.mark.asyncio
async def test_un_tour_d_outil_puis_reponse(settings):
    journal = []
    claude, sdk = clienter(settings, [
        Reponse([BlocOutil("get_sst_index", {"index": "Nino34"})],
                stop_reason="tool_use"),
        Reponse([BlocTexte("L indice vaut 0,3.")]),
    ])
    texte, evenements, final = await collecter(claude.stream_reply(
        [{"role": "user", "content": "et le Nino ?"}],
        tools=OUTILS, executor=executeur(journal)))

    assert journal == [("get_sst_index", {"index": "Nino34"})]
    assert texte == "L indice vaut 0,3."
    assert evenements[0]["calls"][0]["name"] == "get_sst_index"
    assert final["tools_used"] == ["get_sst_index"]
    assert len(sdk.messages.appels) == 2


@pytest.mark.asyncio
async def test_le_resultat_est_renvoye_au_modele(settings):
    claude, sdk = clienter(settings, [
        Reponse([BlocTexte("Je regarde."),
                 BlocOutil("get_sst_index", {"index": "IOD"}, "tu_42")],
                stop_reason="tool_use"),
        Reponse([BlocTexte("Voila.")]),
    ])
    await collecter(claude.stream_reply([{"role": "user", "content": "IOD ?"}],
                                        tools=OUTILS, executor=executeur([])))

    second_appel = sdk.messages.appels[1]["messages"]
    assert second_appel[-2]["role"] == "assistant"
    assert second_appel[-1]["role"] == "user"
    resultat = second_appel[-1]["content"][0]
    assert resultat["type"] == "tool_result"
    assert resultat["tool_use_id"] == "tu_42"
    assert resultat["is_error"] is False


@pytest.mark.asyncio
async def test_les_blocs_de_reflexion_sont_repris(settings):
    """L API refuse un tour d assistant dont la reflexion a ete amputee."""
    claude, sdk = clienter(settings, [
        Reponse([BlocReflexion(), BlocOutil("get_sst_index", {})],
                stop_reason="tool_use"),
        Reponse([BlocTexte("ok")]),
    ])
    await collecter(claude.stream_reply([{"role": "user", "content": "?"}],
                                        tools=OUTILS, executor=executeur([])))

    blocs = sdk.messages.appels[1]["messages"][-2]["content"]
    assert blocs[0] == {"type": "thinking", "thinking": "reflexion", "signature": "sig"}


@pytest.mark.asyncio
async def test_usage_cumule_sur_tous_les_tours(settings):
    """Ne compter que le dernier appel sous-estimerait le cout mesure."""
    claude, _ = clienter(settings, [
        Reponse([BlocOutil("get_sst_index", {})], stop_reason="tool_use",
                usage=Usage(100, 20)),
        Reponse([BlocTexte("ok")], usage=Usage(300, 40)),
    ])
    _, _, final = await collecter(claude.stream_reply(
        [{"role": "user", "content": "?"}], tools=OUTILS, executor=executeur([])))

    assert final["usage"]["input_tokens"] == 400
    assert final["usage"]["output_tokens"] == 60


@pytest.mark.asyncio
async def test_plafond_de_tours_puis_reponse_forcee(settings):
    """Au dernier tour, les outils sont retires: le modele doit conclure."""
    settings.max_tool_rounds = 2
    journal = []
    claude, sdk = clienter(settings, [
        Reponse([BlocOutil("get_sst_index", {})], stop_reason="tool_use"),
        Reponse([BlocOutil("get_sst_index", {})], stop_reason="tool_use"),
        Reponse([BlocOutil("get_sst_index", {})], stop_reason="tool_use"),
        Reponse([BlocTexte("jamais atteint")]),
    ])
    await collecter(claude.stream_reply([{"role": "user", "content": "?"}],
                                        tools=OUTILS, executor=executeur(journal)))

    assert len(journal) == 2                      # deux executions, pas trois
    assert len(sdk.messages.appels) == 3          # dont un appel final
    assert "tools" not in sdk.messages.appels[-1]  # sans outils


@pytest.mark.asyncio
async def test_sans_executeur_aucun_outil_n_est_declare(settings):
    claude, sdk = clienter(settings, [Reponse([BlocTexte("bonjour")])])
    await collecter(claude.stream_reply([{"role": "user", "content": "?"}]))
    assert "tools" not in sdk.messages.appels[0]


@pytest.mark.asyncio
async def test_cache_pose_sur_le_system(settings):
    """L ordre du prefixe est tools puis system: une seule cesure suffit."""
    claude, sdk = clienter(settings, [Reponse([BlocTexte("ok")])])
    await collecter(claude.stream_reply([{"role": "user", "content": "?"}],
                                        tools=OUTILS, executor=executeur([])))
    systeme = sdk.messages.appels[0]["system"][0]
    assert systeme["cache_control"] == {"type": "ephemeral"}


# --- boucle non streamee -----------------------------------------------------
@pytest.mark.asyncio
async def test_complete_execute_aussi_les_outils(settings):
    journal = []
    claude, _ = clienter(settings, [
        Reponse([BlocOutil("get_sst_index", {"index": "TNA"})],
                stop_reason="tool_use"),
        Reponse([BlocTexte("Reponse finale.")]),
    ])
    resultat = await claude.complete([{"role": "user", "content": "?"}],
                                     tools=OUTILS, executor=executeur(journal))
    assert journal == [("get_sst_index", {"index": "TNA"})]
    assert resultat["text"] == "Reponse finale."
    assert resultat["tools_used"] == ["get_sst_index"]


# --- cablage HTTP ------------------------------------------------------------
def test_les_outils_sont_transmis_au_modele(client, token):
    client.post("/jarvis/api/chat/sync", json={"message": "bonjour"},
                headers={"X-Jarvis-Session": token})
    noms = {spec["name"] for spec in client.fake.tools_seen}
    assert "get_teleconnection" in noms


def test_evenement_sse_pendant_la_lecture(client, token):
    """Sans ce signal, l utilisateur croit le widget bloque."""
    client.fake.tool_calls = [("get_sst_index", {"index": "Nino34"})]
    reponse = client.post("/jarvis/api/chat", json={"message": "le Nino ?"},
                          headers={"X-Jarvis-Session": token})
    evenements = sse_events(reponse.text)
    outils = [donnees for nom, donnees in evenements if nom == "tool"]
    assert outils and outils[0]["name"] == "get_sst_index"
    assert outils[0]["label"] == "Lecture des indices SST"


def test_outils_desactivables(settings, fake_claude):
    """Interrupteur de repli: Jarvis reste utilisable sans acces aux donnees."""
    from fastapi.testclient import TestClient

    from jarvis.app import create_app

    settings.tools_enabled = False
    with TestClient(create_app(settings)) as client:
        client.app.state.ctx.claude = fake_claude
        jeton = client.post("/jarvis/api/session").json()["token"]
        client.post("/jarvis/api/chat/sync", json={"message": "bonjour"},
                    headers={"X-Jarvis-Session": jeton})
        assert fake_claude.tools_seen is None
        assert client.get("/jarvis/health").json()["tools"] == 0


def test_health_annonce_les_outils(client):
    from jarvis import tools as module_outils
    attendu = len(module_outils.specs_for("public"))
    assert client.get("/jarvis/health").json()["tools"] == attendu


def test_le_profil_vient_du_serveur(client, token, monkeypatch):
    """Le profil est capture cote serveur, pas dicte par les arguments."""
    from jarvis import tools as module_outils

    vus = []

    async def _executer(nom, arguments, profile, max_chars=0, contexte=None):
        vus.append(profile)
        return {"content": "{}", "is_error": False}

    monkeypatch.setattr(module_outils, "execute", _executer)
    client.fake.tool_calls = [("get_sst_index", {"index": "Nino34",
                                                 "profile": "admin"})]
    client.post("/jarvis/api/chat/sync", json={"message": "?"},
                headers={"X-Jarvis-Session": token})
    assert vus == ["public"]
