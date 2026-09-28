"""Hierarchie etats oceaniques (script 24) -> configurations (script 11).

Tests sur donnees synthetiques pour la logique, et sur les sorties reelles
quand elles existent.
"""
import json

import pandas as pd
import pytest

from veille import etats


def _donnees():
    return {"etats": [
        {"id": 0, "nom": "El Niño", "couleur": "#EF4444", "description": "", "annees": [1997],
         "indices_moyens": {"Nino34": 1.4}, "n_saisons": 3},
        {"id": 1, "nom": "La Niña", "couleur": "#2563EB", "description": "", "annees": [1999],
         "indices_moyens": {"Nino34": -0.6}, "n_saisons": 3}],
        "saisons": [{"annee": 1997, "phase": p, "etat": 0} for p in etats.PHASES]
                   + [{"annee": 1999, "phase": p, "etat": 1} for p in etats.PHASES]}


def _evenements(lignes):
    return pd.DataFrame(lignes, columns=["cluster", "year", "phase"])


def test_rattachement_majoritaire_et_mixte():
    ev = _evenements([(0, 1997, "Phase_2_pleine")] * 9 + [(0, 1999, "Phase_2_pleine")]
                     + [(1, 1999, "Phase_3_fin")] * 5
                     + [(2, 1997, "Phase_1_debut")] * 5 + [(2, 1999, "Phase_1_debut")] * 5)
    h = etats.hierarchie("All_phases", _donnees(), ev)
    assert h["clusters"][0]["etat"] == "El Niño" and h["clusters"][0]["part"] == 0.9
    assert h["clusters"][1]["etat"] == "La Niña"
    # 50/50: sous le seuil de 60 %, le cluster reste "mixte" et n'a pas de parent.
    assert h["clusters"][2]["etat"] == "mixte" and h["clusters"][2]["etat_id"] is None
    parents = {e["nom"]: e["clusters"] for e in h["etats"]}
    assert parents == {"El Niño": [0], "La Niña": [1]}
    assert h["tableau"][2] == {"El Niño": 5, "La Niña": 5}


def test_evenement_hors_saisons_ignore():
    ev = _evenements([(0, 1997, "Phase_2_pleine"), (0, 2050, "Phase_2_pleine")])
    h = etats.hierarchie("All_phases", _donnees(), ev)
    assert h["clusters"][0]["n_evenements"] == 1


def test_etat_de_saison():
    d = _donnees()
    assert etats.etat_de_saison(1999, "Phase_3_fin", d)["nom"] == "La Niña"
    assert etats.etat_de_saison(1950, "Phase_3_fin", d) is None


def test_regle_de_nommage(tmp_path, monkeypatch):
    """Nino 3.4 max -> El Nino, suivant -> Neutre; des deux restants, IOBM le
    plus chaud -> Transition apres El Nino, l'autre -> La Nina."""
    monkeypatch.setattr(etats, "FICHIER", tmp_path / "etats.json")
    dates = {1997: "1997-07-10", 1990: "1990-07-10", 1999: "1999-07-10", 2016: "2016-07-10"}
    ev = pd.DataFrame({"date": list(dates.values()), "year": list(dates),
                       "phase": ["Phase_2_pleine"] * 4})
    ind = pd.DataFrame({"date": list(dates.values()),
                        "Nino34": [2.0, 0.3, -0.6, -0.5], "IOBM": [0.3, 0.0, -0.1, 0.4],
                        "TNA": 0, "TSA": 0, "AMO": 0})
    ev_csv, ind_csv = tmp_path / "ev.csv", tmp_path / "ind.csv"
    ev.to_csv(ev_csv, index=False)
    ind.to_csv(ind_csv, index=False)
    monkeypatch.setattr(etats, "EVENEMENTS", ev_csv)
    monkeypatch.setattr(etats, "INDICES", ind_csv)
    res = {"resultats": {"Toutes_phases": {"methodes": {"kmeans": {"saisons_par_cluster": {
        "0": ["1997-P2"], "1": ["1990-P2"], "2": ["1999-P2"], "3": ["2016-P2"]}}}}}}
    sortie = etats.construire(res)
    noms = {e["id"]: e["nom"] for e in sortie["etats"]}
    assert noms == {0: "El Niño", 1: "Neutre", 2: "La Niña", 3: "Transition après El Niño"}
    assert json.loads((tmp_path / "etats.json").read_text(encoding="utf-8"))["etats"]


def test_hierarchie_reelle_si_disponible():
    try:
        h = etats.hierarchie("All_phases")
    except etats.EtatsIndisponibles:
        pytest.skip("sorties du script 24 ou 11 absentes")
    assert {e["nom"] for e in h["etats"]} == {"El Niño", "La Niña", "Neutre",
                                             "Transition après El Niño"}
    assert h["cramer_v"] > 0.5
    # Chaque cluster rattache l'est a un etat existant.
    ids = {e["id"] for e in h["etats"]}
    assert all(c["etat_id"] in ids or c["etat"] == "mixte" for c in h["clusters"].values())


def test_outil_jarvis_cite_l_etat():
    import asyncio
    from jarvis.tools import registry
    try:
        etats.hierarchie("All_phases")
    except etats.EtatsIndisponibles:
        pytest.skip("sorties absentes")
    r = asyncio.run(registry.execute("get_risk_cluster", {"phase": "Toutes phases"}, "public"))
    c = json.loads(r["content"])
    assert not r["is_error"]
    assert all("etat_oceanique" in p for p in c["clusters"])
    assert len(c["etats_oceaniques"]) == 4 and "robustesse" in c


def test_page_clustering_reste_utilisable_sans_hierarchie():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "vues"))
    import importlib
    page = importlib.import_module("vues.clustering")
    assert page._ligne_etat(None, 3, "#999", "#000") == ""
    h = {"clusters": {3: {"etat": "Neutre", "part": 1.0}},
         "etats": [{"nom": "Neutre", "couleur": "#94A3B8"}]}
    assert "Neutre" in page._ligne_etat(h, 3, "#999", "#000") and "100 %" in page._ligne_etat(h, 3, "#999", "#000")
