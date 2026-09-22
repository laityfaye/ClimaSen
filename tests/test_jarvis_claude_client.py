"""ClaudeClient: forme de la requete et traduction des erreurs du SDK.

Le SDK est remplace par un double: aucun appel reseau, aucun cout.
"""
import anthropic
import pytest

from jarvis.claude_client import ClaudeClient, load_system_prompt
from jarvis.errors import UpstreamError


class FakeMessages:
    def __init__(self, error=None):
        self.error = error
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self.error:
            raise self.error
        raise AssertionError("non utilise dans ce test")


class FakeSDK:
    def __init__(self, error=None):
        self.messages = FakeMessages(error)


def make(settings, error=None):
    return ClaudeClient(settings, client=FakeSDK(error))


# --- forme de la requete ------------------------------------------------------
def test_le_modele_suit_le_profil(settings):
    c = make(settings)
    assert c.model_for("public") == settings.model_public
    assert c.model_for("admin") == settings.model_admin


def test_le_prompt_systeme_est_marque_pour_la_mise_en_cache(settings):
    """Sans cache_control, le prefix serait refacture plein tarif a chaque tour."""
    kwargs = make(settings)._request_kwargs([{"role": "user", "content": "x"}], "public")
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["system"][0]["text"].startswith("Tu es")


def test_effort_et_thinking_conformes_a_la_config(settings):
    kwargs = make(settings)._request_kwargs([{"role": "user", "content": "x"}], "public")
    assert kwargs["output_config"] == {"effort": settings.effort_public}
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["max_tokens"] == settings.max_tokens_public


def test_thinking_desactivable(settings):
    settings.thinking_public = "disabled"
    kwargs = make(settings)._request_kwargs([{"role": "user", "content": "x"}], "public")
    assert kwargs["thinking"] == {"type": "disabled"}


def test_le_prompt_n_est_lu_qu_une_fois(settings):
    c = make(settings)
    c.system_for("public")
    c._system_cache["system_public"] = "REMPLACE"
    assert c.system_for("public") == "REMPLACE"


# --- traduction des erreurs SDK ------------------------------------------------
def _response(status):
    import httpx2
    return httpx2.Response(status_code=status, request=httpx2.Request("POST", "http://x"))


@pytest.mark.parametrize("exc,attendu", [
    (anthropic.APIConnectionError(request=None), "upstream_unreachable"),
    (anthropic.APITimeoutError(request=None), "upstream_timeout"),
    (RuntimeError("panne inattendue"), "upstream_error"),
])
@pytest.mark.asyncio
async def test_les_erreurs_sdk_deviennent_des_erreurs_publiques(settings, exc, attendu):
    with pytest.raises(UpstreamError) as info:
        await make(settings, error=exc).complete([{"role": "user", "content": "x"}])
    assert info.value.code == attendu
    assert info.value.status == 502


@pytest.mark.parametrize("cls,attendu", [
    (anthropic.AuthenticationError, "upstream_auth"),
    (anthropic.PermissionDeniedError, "upstream_auth"),
    (anthropic.RateLimitError, "upstream_rate_limited"),
    (anthropic.BadRequestError, "upstream_bad_request"),
])
@pytest.mark.asyncio
async def test_erreurs_de_statut_http(settings, cls, attendu):
    exc = cls("detail interne", response=_response(400), body=None)
    with pytest.raises(UpstreamError) as info:
        await make(settings, error=exc).complete([{"role": "user", "content": "x"}])
    assert info.value.code == attendu


@pytest.mark.asyncio
async def test_aucun_detail_technique_ne_fuit(settings):
    """Un message d'erreur SDK peut contenir des infos d'infrastructure."""
    exc = anthropic.AuthenticationError(
        "invalid x-api-key sk-ant-VRAIE-CLE", response=_response(401), body=None)
    with pytest.raises(UpstreamError) as info:
        await make(settings, error=exc).complete([{"role": "user", "content": "x"}])
    assert "sk-ant" not in info.value.message
    assert "x-api-key" not in info.value.message


@pytest.mark.asyncio
async def test_absence_de_cle_api_ne_tente_aucun_appel(settings):
    settings.anthropic_api_key = ""
    client = ClaudeClient(settings)            # pas de double: client reel
    with pytest.raises(UpstreamError) as info:
        await client.complete([{"role": "user", "content": "x"}])
    assert info.value.code == "upstream_not_configured"


def test_le_prompt_public_pose_les_garde_fous():
    prompt = load_system_prompt("system_public")
    for regle in ["Aucun chiffre sans outil", "causalité", "CLIMAT-SEN"]:
        assert regle in prompt


# --- rattachement a un workspace ------------------------------------------------
class TestWorkspace:
    """Certaines cles API ne sont pas rattachees a un workspace; l organisation
    exige alors l en-tete anthropic-workspace-id, faute de quoi toute requete
    est refusee en 400."""

    def _capture(self, settings, monkeypatch):
        import anthropic

        from jarvis.claude_client import ClaudeClient
        captures = {}

        class FauxSDK:
            def __init__(self, **kwargs):
                captures.update(kwargs)

        monkeypatch.setattr(anthropic, "AsyncAnthropic", FauxSDK)
        ClaudeClient(settings).client      # declenche la construction paresseuse
        return captures

    def test_aucun_entete_quand_non_configure(self, settings, monkeypatch):
        settings.anthropic_workspace_id = ""
        assert self._capture(settings, monkeypatch)["default_headers"] is None

    def test_entete_transmis_quand_configure(self, settings, monkeypatch):
        settings.anthropic_workspace_id = "wrkspc_demo123"
        entetes = self._capture(settings, monkeypatch)["default_headers"]
        assert entetes == {"anthropic-workspace-id": "wrkspc_demo123"}

    def test_les_autres_parametres_restent_intacts(self, settings, monkeypatch):
        settings.anthropic_workspace_id = "wrkspc_demo123"
        capture = self._capture(settings, monkeypatch)
        assert capture["api_key"] == settings.anthropic_api_key
        assert capture["max_retries"] == settings.max_retries
        assert capture["timeout"] == settings.request_timeout_seconds

    @pytest.mark.asyncio
    async def test_le_defaut_de_workspace_est_signale_distinctement(self, settings):
        """Un 400 'workspace' est un probleme de configuration, pas de contenu :
        il doit porter son propre code pour etre diagnosticable dans les logs."""
        import anthropic

        from jarvis.claude_client import ClaudeClient
        exc = anthropic.BadRequestError(
            "This API key is not scoped to a workspace, so this request must "
            "include the anthropic-workspace-id header.",
            response=_response(400), body=None)
        with pytest.raises(UpstreamError) as info:
            await make(settings, error=exc).complete([{"role": "user", "content": "x"}])
        assert info.value.code == "upstream_workspace_required"
        # Le detail technique ne doit pas remonter au visiteur.
        assert "workspace" not in info.value.message.lower()
