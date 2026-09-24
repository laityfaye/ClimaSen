"""Integration: les outils lisent bien les VRAIES donnees de la plateforme.

Les autres tests d outils travaillent sur des donnees synthetiques. Celui-ci
verifie le seul point qu ils ne peuvent pas couvrir: que les loaders du
dashboard renvoient les colonnes attendues et que Jarvis annonce les memes
chiffres que le dashboard.

Se saute tout seul si les donnees ou streamlit sont absents (poste de
developpement sans le jeu complet, integration continue).
"""
import json
from pathlib import Path

import pytest

from jarvis import tools

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FICHIERS = {
    "events":       "data/processed/extreme_events_phases_senegal.csv",
    "indices":      "data/raw/climate_indices/daily_indices_all.csv",
    "correlations": "outputs/teleconnections/correlations_Phase_2_pleine.csv",
    "clustering":   "outputs/clustering/Phase_2_pleine/"
                    "Phase_2_pleine_cluster_characteristics.csv",
}

manquants = [nom for nom, chemin in FICHIERS.items()
             if not (PROJECT_ROOT / chemin).exists()]

pytestmark = pytest.mark.skipif(
    bool(manquants),
    reason="Donnees absentes: %s" % ", ".join(manquants),
)


async def lancer(nom, **params):
    resultat = await tools.execute(nom, params, "public")
    assert not resultat["is_error"], resultat["content"]
    return json.loads(resultat["content"])


@pytest.mark.asyncio
async def test_indices_reels():
    donnees = await lancer("get_sst_index", index="Nino34", date="2012")
    assert donnees["periode"]["debut"] == "2012-01-01"
    assert donnees["periode"]["n_jours"] == 366
    assert -5 < donnees["resume"]["moyenne"] < 5


@pytest.mark.asyncio
async def test_catalogue_reel():
    donnees = await lancer("search_extreme_events", limit=3)
    assert donnees["n_total"] == 1317          # taille connue du catalogue
    assert donnees["n_renvoyes"] == 3
    assert donnees["evenements"][0]["max_precip_mm"] > 0


@pytest.mark.asyncio
async def test_correlations_reelles():
    """Les 6 lags x 11 indices du script 04 doivent tous etre lisibles."""
    donnees = await lancer("get_teleconnection", phase="Phase_2_pleine")
    assert donnees["n_resultats"] == 66
    for ligne in donnees["correlations"]:
        assert -1 <= ligne["pearson_r"] <= 1
        assert 0 <= ligne["p_neff"] <= 1


@pytest.mark.asyncio
async def test_clustering_reel():
    donnees = await lancer("get_risk_cluster", phase="Phase_2_pleine")
    assert donnees["clusters"]
    assert donnees["methode"]["k_retenu"] == len(donnees["clusters"])
    # La jointure des regions passe par les dates des deux fichiers.
    assert donnees["clusters"][0]["regions_principales"]


@pytest.mark.asyncio
async def test_taille_des_resultats_bornee():
    """Un resultat qui deborde ferait exploser le cout en tokens."""
    for nom, params in (("get_sst_index", {"index": "Nino34"}),
                        ("search_extreme_events", {"limit": 20}),
                        ("get_teleconnection", {"phase": "Toutes phases"}),
                        ("get_risk_cluster", {"phase": "Toutes phases"})):
        resultat = await tools.execute(nom, params, "public")
        assert len(resultat["content"]) <= tools.MAX_RESULT_CHARS


# --- Phase 7: outils d'analyse ----------------------------------------------------
@pytest.mark.asyncio
async def test_bilan_significativite_reel():
    """Le script 04 teste 66 combinaisons par phase et par metrique."""
    donnees = await lancer("analyze_teleconnections",
                           analysis="bilan_significativite")
    phases = {p["phase"]: p for p in donnees["phases"]}
    assert set(phases) == {"Phase_1_debut", "Phase_2_pleine", "Phase_3_fin"}
    for bloc in phases.values():
        assert bloc["n_tests"] == 66
        assert bloc["attendues_par_hasard"] == pytest.approx(3.3)


@pytest.mark.asyncio
async def test_robustesse_reelle():
    donnees = await lancer("analyze_teleconnections", analysis="robustesse",
                           phase="Phase_2_pleine")
    assert donnees["n_candidates"] >= 1
    assert donnees["correlations"][0]["verdict"] in ("robuste", "moderee", "fragile")


@pytest.mark.asyncio
async def test_tendance_reelle_couvre_toute_la_periode():
    donnees = await lancer("analyze_extreme_events", analysis="tendance")
    assert donnees["n_evenements"] == 1317
    assert donnees["filtres"]["annees"] == [1981, 2023]
    assert donnees["n_annees"] == 43


@pytest.mark.asyncio
async def test_statut_pipeline_reel():
    donnees = await lancer("get_pipeline_status")
    ids = {e["etape"] for e in donnees["etapes"]}
    assert {"01", "04", "11"} <= ids
    assert sum(donnees["resume"].values()) == donnees["n_etapes"]
