"""Registre d outils: declarations, permissions, erreurs, plafond de taille.

Aucun acces disque: le chargement des donnees est remplace par les fixtures
synthetiques.
"""
import json

import pytest

from jarvis import tools
from jarvis.tools import registry


@pytest.fixture
def donnees_injectees(monkeypatch, donnees_outils):
    async def _charger(noms):
        return {nom: donnees_outils[nom] for nom in noms}
    monkeypatch.setattr(registry, "charger_donnees", _charger)
    return donnees_outils


# --- declarations ------------------------------------------------------------
def test_les_outils_publics_sont_declares():
    noms = {spec["name"] for spec in tools.specs_for("public")}
    assert noms == {"get_sst_index", "search_extreme_events",
                    "get_teleconnection", "get_risk_cluster",
                    "search_documents", "analyze_teleconnections",
                    "analyze_extreme_events", "get_pipeline_status",
                    "make_figure"}


def test_chaque_declaration_est_complete():
    for spec in tools.specs_for("public"):
        assert spec["description"].strip()
        assert spec["input_schema"]["type"] == "object"
        assert "properties" in spec["input_schema"]


def test_ordre_stable_des_declarations():
    """L ordre fait partie du prefixe mis en cache cote API: le changer a
    chaque demarrage invaliderait le cache."""
    assert tools.specs_for("public") == tools.specs_for("public")
    noms = [spec["name"] for spec in tools.specs_for("public")]
    assert noms == sorted(noms)


def test_un_outil_admin_reste_invisible_du_public(monkeypatch):
    factice = registry.Tool.__new__(registry.Tool)
    factice.name = "outil_admin"
    factice.label = "Outil admin"
    factice.description = "reserve"
    factice.schema = {"type": "object", "properties": {}}
    factice.permission = "admin"
    factice.datasets = ()
    factice.run = lambda params, data: {}
    monkeypatch.setitem(registry.TOOLS, "outil_admin", factice)

    assert "outil_admin" not in {s["name"] for s in tools.specs_for("public")}
    assert "outil_admin" in {s["name"] for s in tools.specs_for("admin")}


@pytest.mark.asyncio
async def test_un_outil_admin_reste_inexecutable_par_le_public(monkeypatch):
    """Le filtrage a l affichage ne suffit pas: le modele peut deviner un nom."""
    appele = []

    factice = registry.Tool.__new__(registry.Tool)
    factice.name = "outil_admin"
    factice.label = "Outil admin"
    factice.description = "reserve"
    factice.schema = {"type": "object", "properties": {}}
    factice.permission = "admin"
    factice.datasets = ()
    factice.run = lambda params, data: appele.append(True)
    monkeypatch.setitem(registry.TOOLS, "outil_admin", factice)

    resultat = await tools.execute("outil_admin", {}, "public")
    assert resultat["is_error"]
    assert appele == []
    # Meme message que pour un outil inexistant: ne jamais confirmer qu un
    # outil existe mais est reserve.
    message = json.loads(resultat["content"])["erreur"]
    assert message.startswith("Outil inconnu")
    assert "refus" not in message.lower() and "permission" not in message.lower()


# --- execution ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_execution_nominale(donnees_injectees):
    resultat = await tools.execute("get_sst_index", {"index": "Nino34"}, "public")
    assert resultat["is_error"] is False
    assert json.loads(resultat["content"])["indice"] == "Nino34"
    assert resultat["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_outil_inconnu_ne_leve_pas(donnees_injectees):
    resultat = await tools.execute("get_weather", {}, "public")
    assert resultat["is_error"]
    assert "Outil inconnu" in json.loads(resultat["content"])["erreur"]


@pytest.mark.asyncio
async def test_parametre_invalide_revient_au_modele(donnees_injectees):
    """Un mauvais parametre doit etre corrigeable, pas fatal."""
    resultat = await tools.execute("get_sst_index", {"index": "ete"}, "public")
    assert resultat["is_error"]
    assert "Valeurs acceptees" in json.loads(resultat["content"])["erreur"]


@pytest.mark.asyncio
async def test_arguments_non_objet(donnees_injectees):
    resultat = await tools.execute("get_sst_index", ["Nino34"], "public")
    assert resultat["is_error"]


@pytest.mark.asyncio
async def test_arguments_absents(donnees_injectees):
    resultat = await tools.execute("get_teleconnection", None, "public")
    assert resultat["is_error"]
    assert "phase" in json.loads(resultat["content"])["erreur"]


@pytest.mark.asyncio
async def test_donnees_indisponibles(monkeypatch):
    async def _echec(noms):
        raise tools.DataUnavailableError("fichier absent")
    monkeypatch.setattr(registry, "charger_donnees", _echec)

    resultat = await tools.execute("get_sst_index", {"index": "Nino34"}, "public")
    assert resultat["is_error"]
    message = json.loads(resultat["content"])["erreur"]
    assert "indisponibles" in message
    assert "fichier absent" not in message  # aucun detail interne ne fuit


@pytest.mark.asyncio
async def test_erreur_interne_ne_fuit_pas(monkeypatch, donnees_injectees):
    def _exploser(params, data):
        raise RuntimeError("chemin/interne/secret.csv")
    monkeypatch.setattr(registry.TOOLS["get_sst_index"], "run", _exploser)

    resultat = await tools.execute("get_sst_index", {"index": "Nino34"}, "public")
    assert resultat["is_error"]
    assert "secret" not in resultat["content"]


# --- plafond de taille -------------------------------------------------------
def test_reduction_sous_le_plafond():
    charge = {"titre": "x", "points": [{"v": i} for i in range(500)]}
    texte = registry._reduire(charge, 400)
    assert len(texte) <= 400
    reduit = json.loads(texte)
    assert reduit["tronque"] is True
    assert len(reduit["points"]) < 500


def test_pas_de_reduction_inutile():
    charge = {"a": 1, "b": [1, 2, 3]}
    assert json.loads(registry._reduire(charge, 6000)) == charge


@pytest.mark.asyncio
async def test_plafond_applique_a_l_execution(donnees_injectees):
    resultat = await tools.execute("search_extreme_events", {}, "public",
                                   max_chars=300)
    assert len(resultat["content"]) <= 300
