"""Fixtures partagees des tests Jarvis.

Regle: aucun test ne doit joindre l'API Anthropic. Le client Claude est
systematiquement remplace par un faux, injecte dans le contexte applicatif.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def settings(tmp_path):
    from jarvis.config import Settings
    s = Settings(
        secret_key="k" * 48,
        env="dev",
        anthropic_api_key="sk-ant-faux-pour-les-tests",
        log_dir=str(tmp_path / "logs"),
        conversation_ttl_seconds=60,
        max_turns=5,
        max_message_chars=500,
        max_history_chars=2000,
        rate_limit_capacity=5,
        rate_limit_refill_per_minute=60.0,
    )
    s.validate_runtime()
    return s


class FakeClaude:
    """Double du ClaudeClient: repond sans reseau, ou leve a la demande.

    tool_calls simule un tour d'outils: [(nom, arguments), ...]. Le double
    appelle reellement l'executeur fourni par l'application, ce qui permet de
    verifier le cablage complet (filtrage par profil, evenement SSE, journal)
    sans joindre l'API.
    """

    def __init__(self, reply="Bonjour, je suis Jarvis.", error=None,
                 fail_after=None, tool_calls=None):
        self.reply = reply
        self.error = error            # exception levee d'emblee
        self.fail_after = fail_after  # nb de fragments avant echec en cours de flux
        self.tool_calls = tool_calls or []
        self.calls = []
        self.tool_results = []
        self.tools_seen = None

    def model_for(self, profile):
        return "claude-opus-5" if profile == "admin" else "claude-sonnet-5"

    async def _jouer_outils(self, executor):
        resultats = []
        for nom, arguments in self.tool_calls:
            resultats.append(await executor(nom, arguments))
        self.tool_results.extend(resultats)
        return resultats

    async def stream_reply(self, messages, profile="public", tools=None,
                           executor=None):
        self.calls.append({"messages": list(messages), "profile": profile,
                           "tools": tools})
        self.tools_seen = tools
        if self.error and self.fail_after is None:
            raise self.error
        if self.tool_calls and executor is not None:
            yield {"type": "tools",
                   "calls": [{"name": nom, "id": "tu_%d" % i}
                             for i, (nom, _) in enumerate(self.tool_calls)]}
            await self._jouer_outils(executor)
        chunks = self.reply.split(" ")
        for i, word in enumerate(chunks):
            if self.fail_after is not None and i >= self.fail_after:
                raise self.error
            yield word + (" " if i < len(chunks) - 1 else "")
        yield {"type": "done",
               "usage": {"input_tokens": 120, "output_tokens": 30,
                         "cache_read_input_tokens": 0,
                         "cache_creation_input_tokens": 0},
               "stop_reason": "end_turn",
               "tools_used": [nom for nom, _ in self.tool_calls]}

    async def complete(self, messages, profile="public", tools=None,
                       executor=None):
        self.calls.append({"messages": list(messages), "profile": profile,
                           "tools": tools})
        self.tools_seen = tools
        if self.error:
            raise self.error
        if self.tool_calls and executor is not None:
            await self._jouer_outils(executor)
        return {"text": self.reply,
                "usage": {"input_tokens": 120, "output_tokens": 30},
                "stop_reason": "end_turn",
                "tools_used": [nom for nom, _ in self.tool_calls]}


@pytest.fixture
def fake_claude():
    return FakeClaude()


@pytest.fixture
def client(settings, fake_claude):
    from fastapi.testclient import TestClient

    from jarvis.app import create_app

    app = create_app(settings)
    with TestClient(app) as c:
        c.app.state.ctx.claude = fake_claude
        c.fake = fake_claude
        c.settings = settings
        yield c


@pytest.fixture
def token(client):
    return client.post("/jarvis/api/session").json()["token"]


def sse_events(text):
    """Decoupe un flux SSE brut en liste de (nom, donnees)."""
    import json
    out = []
    for block in text.split("\n\n"):
        name, data = None, ""
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if name and data:
            out.append((name, json.loads(data)))
    return out


# =============================================================================
# Fixtures des modules de teleconnexions (src/analysis, src/visualization,
# src/reports). Donnees synthetiques : aucun acces aux donnees reelles, aucune
# dependance a l ordre d execution.
# =============================================================================

def paire_correlee(r_cible, n=120, seed=0):
    """Deux series dont la correlation de Pearson vaut EXACTEMENT r_cible.

    Construction par orthogonalisation de Gram-Schmidt : y = r*x + sqrt(1-r^2)*z
    avec z orthogonal a x. Permet de tester les seuils de classification sans
    dependre d un tirage aleatoire.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    z = rng.normal(size=n)
    x = (x - x.mean()) / x.std()
    z = z - (z @ x) / (x @ x) * x
    z = (z - z.mean()) / z.std()
    y = r_cible * x + np.sqrt(1.0 - r_cible ** 2) * z
    return x, y


def donnees_synthetiques(seed=42):
    """Evenements extremes + indices climatiques mensuels, 1990-2012.

    L intensite des evenements depend de Nino34 avec 3 mois de decalage, ce qui
    correspond au lag physique optimal declare par l analyseur pour cet indice.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    mois = pd.date_range("1990-01-01", "2012-12-01", freq="MS")
    n = len(mois)

    nino = np.zeros(n)
    for i in range(1, n):
        nino[i] = 0.8 * nino[i - 1] + rng.normal(scale=0.5)

    indices = pd.DataFrame({
        "Nino34": nino,
        "IOD":    rng.normal(size=n) * 0.4,
        "TNA":    np.sin(np.arange(n) / 6.0) * 0.5 + rng.normal(size=n) * 0.2,
    }, index=mois)

    lignes = []
    for i, d in enumerate(mois):
        if d.month not in (7, 8, 9):
            continue
        k = max(1, int(2 + nino[max(0, i - 3)] * 1.5 + rng.normal()))
        for _ in range(k):
            lignes.append({
                "date": d + pd.Timedelta(days=int(rng.integers(0, 28))),
                "year": d.year, "month": d.month,
                "phase": {7: "Phase_2_pleine", 8: "Phase_2_pleine",
                          9: "Phase_3_fin"}[d.month],
                "max_precip": 40 + nino[max(0, i - 3)] * 8 + rng.normal(scale=5),
            })
    return pd.DataFrame(lignes), indices


@pytest.fixture
def analyseur():
    """Analyseur charge en donnees, sans analyse lancee."""
    import sys
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.analysis.teleconnections import TeleconnectionsAnalyzer

    events, indices = donnees_synthetiques()
    a = TeleconnectionsAnalyzer(min_observations=30)
    a.extreme_events = events
    a.climate_indices = indices
    return a


@pytest.fixture(scope="module")
def analyseur_avec_resultats():
    """Analyseur dont l analyse complete a tourne (~1 s).

    Portee module : le calcul est partage par tous les tests du fichier, les
    resultats ne sont lus que en lecture.
    """
    import sys
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.analysis.teleconnections import TeleconnectionsAnalyzer

    events, indices = donnees_synthetiques()
    a = TeleconnectionsAnalyzer(min_observations=30)
    a.extreme_events = events
    a.climate_indices = indices
    a.analyze_teleconnections_with_physical_lags(max_lag=6, verbose=False)
    a.analyze_seasonal_teleconnections_corrected()
    return a


def donnees_signal_fort(seed=7):
    """Variante a signal fort, pour les tests qui ont besoin de correlations
    reellement significatives (tableaux de synthese, rapports).

    Difference avec donnees_synthetiques() : des evenements TOUS les mois, et
    non seulement en saison des pluies. Dans le jeu saisonnier, les mois hors
    saison sont remplis de zeros par le module ; ces zeros dominent la serie et
    noient le signal, au point qu aucune correlation ne ressort. Ici le lien
    Nino34 -> intensite, avec 3 mois de decalage, est present sur toute la
    serie et doit etre retrouve par l analyse.
    """
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    mois = pd.date_range("1990-01-01", "2012-12-01", freq="MS")
    n = len(mois)

    nino = np.zeros(n)
    for i in range(1, n):
        nino[i] = 0.7 * nino[i - 1] + rng.normal(scale=0.6)

    indices = pd.DataFrame({
        "Nino34": nino,
        "IOD":    rng.normal(size=n) * 0.4,
        "TNA":    rng.normal(size=n) * 0.4,
    }, index=mois)

    lignes = []
    for i, d in enumerate(mois):
        pilote = nino[max(0, i - 3)]          # decalage injecte : 3 mois
        for _ in range(max(1, int(round(3 + pilote * 1.2)))):
            lignes.append({
                "date": d + pd.Timedelta(days=int(rng.integers(0, 27))),
                "year": d.year, "month": d.month,
                "phase": "Phase_2_pleine" if d.month in (7, 8) else "Phase_3_fin",
                "max_precip": 40 + pilote * 12 + rng.normal(scale=2),
            })
    return pd.DataFrame(lignes), indices


LAG_INJECTE = 3
INDICE_PILOTE = "Nino34"


@pytest.fixture(scope="module")
def analyseur_signal_fort():
    """Analyseur dont l analyse a tourne sur le jeu a signal fort."""
    import sys
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.analysis.teleconnections import TeleconnectionsAnalyzer

    events, indices = donnees_signal_fort()
    a = TeleconnectionsAnalyzer(min_observations=30)
    a.extreme_events = events
    a.climate_indices = indices
    a.analyze_teleconnections_with_physical_lags(max_lag=6, verbose=False)
    return a


# =============================================================================
# Fixtures des outils Jarvis (Phase 2).
#
# Donnees SYNTHETIQUES: les tests d outils ne doivent dependre ni des CSV du
# depot, ni de streamlit, ni de l ordre d execution. Les vraies donnees ne sont
# lues que par le test d integration, qui se saute tout seul si elles manquent.
# =============================================================================

@pytest.fixture
def jeu_indices():
    import numpy as np
    import pandas as pd
    dates = pd.date_range("1983-01-01", "1985-12-31", freq="D")
    n = len(dates)
    rampe = np.linspace(-1.5, 1.5, n)
    return pd.DataFrame({
        "date":   dates,
        "Nino34": rampe,
        "Nino3":  rampe * 0.5,
        "IOD":    -rampe,
        "TNA":    np.zeros(n) + 0.25,
    })


@pytest.fixture
def jeu_events():
    import pandas as pd
    lignes = [
        ("2001-05-20", "Phase_1_debut",  30.0, 12.0, 15.0, 4.0, "Kedougou",    "Salemata"),
        ("2005-07-11", "Phase_2_pleine", 80.0, 40.0, 55.0, 9.0, "Tambacounda", "Koumpentoum"),
        ("2005-08-03", "Phase_2_pleine", 45.0, 20.0, 30.0, 5.0, "Matam",       "Kanel"),
        ("2012-09-28", "Phase_3_fin",    60.0, 25.0, 42.0, 7.0, "Tambacounda", "Koumpentoum"),
    ]
    df = pd.DataFrame(lignes, columns=[
        "date", "phase", "max_precip", "mean_precip", "coverage_percent",
        "max_anomaly", "centroid_region", "centroid_department"])
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["regions_affected"] = [2, 8, 4, 6]
    return df


@pytest.fixture
def jeu_correlations():
    import pandas as pd
    lignes = []
    for lag in range(6):
        for indice, r, p in (("Nino34", -0.31 + lag * 0.02, 0.004 + lag * 0.02),
                             ("IOD",    0.12 + lag * 0.01,  0.40)):
            lignes.append({
                "metric": "max_precip", "index": indice, "lag_months": lag,
                "pearson_r": r, "pearson_p": p / 2, "pearson_p_neff": p,
                "spearman_r": r * 0.9, "spearman_p": p / 2,
                "spearman_p_neff": p * 1.1, "n": 41, "n_eff": 33.0,
            })
    lignes.append({
        "metric": "n_events", "index": "Nino34", "lag_months": 0,
        "pearson_r": 0.05, "pearson_p": 0.7, "pearson_p_neff": 0.7,
        "spearman_r": 0.04, "spearman_p": 0.7, "spearman_p_neff": 0.7,
        "n": 41, "n_eff": 40.0,
    })
    df = pd.DataFrame(lignes)
    return {"Phase_2_pleine": df, "Toutes phases": df}


@pytest.fixture
def jeu_clustering(jeu_events):
    import pandas as pd
    chars = pd.DataFrame([
        {"cluster": 0, "n_events": 2, "percentage": 50.0, "mean_year": 2005.0,
         "mean_month": 7.5, "mean_max_precip": 62.5, "mean_mean_precip": 30.0,
         "mean_coverage_percent": 42.5, "mean_max_anomaly": 7.0, "n_years": 2},
        {"cluster": 1, "n_events": 2, "percentage": 50.0, "mean_year": 2006.5,
         "mean_month": 8.0, "mean_max_precip": 45.0, "mean_mean_precip": 20.0,
         "mean_coverage_percent": 30.0, "mean_max_anomaly": 5.0, "n_years": 2},
    ])
    evenements = jeu_events[["date", "phase", "max_precip",
                             "coverage_percent", "max_anomaly"]].copy()
    evenements["cluster"] = [0, 0, 1, 1]
    metriques = {"optimal_k": 2, "best_silhouette_score": 0.13,
                 "n_samples": 4, "n_pca_components": 3,
                 "decision": "k=2 retenu (test)"}
    bloc = {"chars": chars, "events": evenements, "metrics": metriques}
    return {"Phase_2_pleine": bloc, "All_phases": bloc}


@pytest.fixture
def donnees_outils(jeu_indices, jeu_events, jeu_correlations, jeu_clustering):
    return {"indices": jeu_indices, "events": jeu_events,
            "correlations": jeu_correlations, "clustering": jeu_clustering}
