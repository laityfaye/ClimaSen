"""Jarvis et la veille pre-saison: cartes, briefing, fiabilite, veille mensuelle,
diffusion, scenarios.

Les tests s'appuient sur les bulletins reels de outputs/veille/ (produits par
scripts/20_veille_presaison.py) quand ils existent, et sur des donnees
synthetiques pour tout ce qui ecrit ou calcule.
"""
import asyncio
import json

import numpy as np
import pytest

from jarvis import actions, briefing, figures
from jarvis.tools import registry
from jarvis.widget_html import WIDGET_FILE

from conftest import sse_events
from veille import artefacts, diffusion, fiabilite, production

SOURCE = WIDGET_FILE.read_text(encoding="utf-8")
CHAT = "/jarvis/api/chat"


def _executer(nom, params, profil="public", **contexte):
    store = contexte.pop("store", None) or figures.FigureStore()
    ctx = {"figures": store, "session_id": "s1"}
    ctx.update(contexte)
    r = asyncio.run(registry.execute(nom, params, profil, contexte=ctx))
    return r, store


def _charge(r):
    assert not r["is_error"], r["content"]
    return json.loads(r["content"])


def _bulletin(annee=2031, extreme=None, niveau=("eleve", "Élevé", 0.5), projection=True):
    b = {
        "annee": annee, "emis_le": "2031-04-28", "statut": "complet",
        "niveau_risque": {"code": niveau[0], "libelle": niveau[1],
                          "probabilite_annee_extreme": niveau[2], "couleur": "#F59E0B",
                          "source": "c3s", "confiance": "faible"},
        "c3s": {"disponible": True, "anomalie_standardisee": 0.8, "centre": "ecmwf",
                "systeme": "51", "part_membres_au_dessus_normale": 0.6,
                "probabilite_annee_extreme": niveau[2], "pluie_jas_mm_jour": 4.1,
                "competence": {"auc": 0.59, "p_permutation": 0.19, "n": 36,
                               "brier_skill_score": 0.03}},
        "projection": ({
            "probabilite_experimentale": 0.42,
            "configurations": [{"configuration": 4, "correlation": 0.5,
                                "annees_principales": [2010, 2012],
                                "part_evenements_en_annee_extreme": 0.7}],
            "analogues": [{"annee": 2010, "correlation": 0.6, "extreme": True,
                           "inondation_documentee": True, "empreinte": 1152.0},
                          {"annee": 2011, "correlation": 0.5, "extreme": False,
                           "inondation_documentee": False, "empreinte": 550.0}],
            "trajectoire": [
                {"jusqu_a": "2030-11", "n_mois": 1, "probabilite_experimentale": 0.3,
                 "configuration": 2, "correlation": 0.3},
                {"jusqu_a": "2031-04", "n_mois": 6, "probabilite_experimentale": 0.42,
                 "configuration": 4, "correlation": 0.5}],
        } if projection else None),
        "synthese": "Saison 2031 : risque élevé.",
        "avertissements": [] if projection else ["Projection océanique indisponible : manque 11/2030."],
        "definition": {"seuil": 746.0},
        "contexte": {"base_climatologique": 0.333},
    }
    if extreme is not None:
        b["verification"] = {"extreme_observe": extreme, "inondation_documentee": extreme,
                             "rang": 3 if extreme else 30, "empreinte_observee": 1000.0,
                             "seuil": 746.0}
    return b


@pytest.fixture
def bulletins_synthetiques(monkeypatch):
    """Quatre saisons verifiees: detection, fausse alerte, manquee, calme."""
    jeu = {
        2001: _bulletin(2001, True, ("eleve", "Élevé", 0.55)),
        2002: _bulletin(2002, False, ("tres_eleve", "Très élevé", 0.7)),
        2003: _bulletin(2003, True, ("normal", "Normal", 0.3)),
        2004: _bulletin(2004, False, ("faible", "Faible", 0.1)),
        2031: _bulletin(2031),
    }
    monkeypatch.setattr(production, "bulletins_disponibles", lambda: sorted(jeu, reverse=True))
    monkeypatch.setattr(production, "lire_bulletin", lambda a: jeu.get(int(a)))
    return jeu


# =============================================================================
# 3. Carnet de fiabilite
# =============================================================================
def test_carnet_compte_detections_fausses_alertes_manquees(bulletins_synthetiques):
    c = fiabilite.carnet()
    assert c["n_saisons"] == 4 and c["periode"] == [2001, 2004]
    r = c["niveau_de_risque"]
    assert r["comptes"] == {"détection": 1, "fausse alerte": 1, "manquée": 1,
                            "calme confirmé": 1}
    assert r["taux_detection"] == 0.5 and r["part_fausses_alertes"] == 0.5
    assert c["fausses_alertes"] == [2002]
    assert {x["annee"]: x["verdict"] for x in c["inondations_documentees"]} == {
        2001: "détection", 2003: "manquée"}


def test_auc_du_carnet():
    assert fiabilite._auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert fiabilite._auc([1, 0], [0.3, 0.3]) == 0.5
    assert fiabilite._auc([1, 1], [0.3, 0.4]) is None


def test_outil_fiabilite_bilan_saison_et_comparaison(bulletins_synthetiques):
    bilan = _charge(_executer("get_bulletin_reliability", {})[0])
    assert "saisons" not in bilan and bilan["niveau_de_risque"]["comptes"]["manquée"] == 1
    une = _charge(_executer("get_bulletin_reliability", {"year": 2003})[0])
    assert une["saison"]["verdict"] == "manquée"
    comp = _charge(_executer("get_bulletin_reliability", {"compare_years": [2001, 2002]})[0])
    assert set(comp["comparaison"]) == {"2001", "2002"}
    r, _ = _executer("get_bulletin_reliability", {"year": 1990})
    assert r["is_error"]
    r, _ = _executer("get_bulletin_reliability", {"compare_years": [2001]})
    assert r["is_error"]


def test_carnet_reel_si_les_bulletins_existent():
    c = fiabilite.carnet()
    if not c.get("disponible"):
        pytest.skip("bulletins retrospectifs non produits")
    r = c["niveau_de_risque"]
    assert sum(r["comptes"].values()) == r["n_saisons_avec_niveau"]
    assert len(c["inondations_documentees"]) == 8


# =============================================================================
# 6. Scenarios
# =============================================================================
def _kit_synthetique(tmp_path, monkeypatch, annee=2031):
    """Grille 4 x 6 (lats -30..30, lons -180..120), 3 configurations."""
    lats = np.array([-30.0, -10.0, 10.0, 30.0], dtype="float32")
    lons = np.array([-180.0, -120.0, -60.0, -30.0, 0.0, 120.0], dtype="float32")
    masque = np.ones(24, dtype=bool)
    rng = np.random.default_rng(0)
    cent = rng.normal(size=(3, 24))
    monkeypatch.setattr(artefacts, "DOSSIER_KITS", tmp_path)
    np.savez_compressed(
        tmp_path / ("kit_%d.npz" % annee), annee=np.int32(annee), masque=masque,
        lats=lats, lons=lons, etat=cent[0].astype("float32"), ybar=np.float64(2000),
        pente=np.zeros(24, "float32"), w=np.ones(24, "float32"),
        centroides=cent.astype("float16"), centroides_memoire=cent.astype("float16"),
        coef=np.array([2.0, -1.0, 0.0]), intercept=np.float64(-0.5),
        annees_candidates=np.array([1999, 2000], "int32"),
        etats_candidats=cent[:2].astype("float16"))
    return artefacts.charger_kit(annee)


def test_perturbation_nulle_ne_change_rien(tmp_path, monkeypatch):
    kit = _kit_synthetique(tmp_path, monkeypatch)
    etat, pixels = artefacts.perturber(kit, {})
    assert np.allclose(etat, kit["etat"]) and pixels == {}
    r = artefacts.projeter(kit, etat)
    assert max(r["ressemblance_memoire"], key=r["ressemblance_memoire"].get) == 0
    assert r["analogues"][0][0] == 1999


def test_perturbation_ne_touche_que_sa_boite(tmp_path, monkeypatch):
    kit = _kit_synthetique(tmp_path, monkeypatch)
    etat, pixels = artefacts.perturber(kit, {"TNA": 1.0})
    # TNA = 55-15 O, 5-23 N: seul le point (10 N, 30 O) y tombe.
    assert pixels == {"TNA": 1}
    diff = etat - kit["etat"]
    assert np.isclose(diff.sum(), 1.0) and np.count_nonzero(diff) == 1


def test_outil_scenario(tmp_path, monkeypatch):
    _kit_synthetique(tmp_path, monkeypatch)
    c = _charge(_executer("explore_ocean_scenario", {"changes": {"TNA": 1.5, "Nino34": -1}})[0])
    assert c["saison"] == 2031 and c["perturbation_degC"] == {"TNA": 1.5, "Nino34": -1.0}
    assert "pas une prevision" in c["garde_fou"]
    assert "2031" in c["attention"]          # saison par defaut: signalee
    c = _charge(_executer("explore_ocean_scenario", {"changes": {"TNA": 1}, "year": 2031})[0])
    assert "attention" not in c
    assert set(c["avant"]) == {"probabilite_experimentale", "configuration", "analogues"}
    for params, message in (({"changes": {"Mediterranee": 1}}, "Boite inconnue"),
                            ({"changes": {"TNA": 3}}, "hors bornes"),
                            ({"changes": {}}, "changes est requis"),
                            ({"changes": {"TNA": 1}, "year": 1990}, "Pas de kit")):
        r, _ = _executer("explore_ocean_scenario", params)
        assert r["is_error"] and message in r["content"], (params, r["content"])


def test_outil_scenario_avec_familles(tmp_path, monkeypatch):
    from veille import familles
    kit = _kit_synthetique(tmp_path, monkeypatch)
    cent = kit["centroides"].astype("float64")
    prep = {"ybar": 2000.0, "pente": np.zeros(24), "membres": {"A": [1999, 2000], "B": []},
            "composites": {"A": cent[0], "B": None}}
    assert artefacts.completer_kit_familles(2031, prep)
    assert not artefacts.completer_kit_familles(1990, prep)
    kit = artefacts.charger_kit(2031)
    r = artefacts.projeter(kit, kit["etat"].astype("float64"))
    fam = r["familles_extremes"]
    assert fam["plus_proche"] == "A" and fam["familles"][0]["correlation"] > 0.99
    assert fam["familles"][1]["correlation"] is None   # famille pas encore observee
    # Le reste de la projection ne bouge pas quand on ajoute les familles
    assert r["analogues"][0][0] == 1999
    c = _charge(_executer("explore_ocean_scenario", {"changes": {"TNA": 1.5}, "year": 2031})[0])
    assert c["avant"]["familles_extremes"]["plus_proche"] == "A"
    assert "changement_famille" in c and "descriptive" in c["garde_fou"]


def test_outil_scenario_kit_ancien_sans_familles(tmp_path, monkeypatch):
    _kit_synthetique(tmp_path, monkeypatch)
    c = _charge(_executer("explore_ocean_scenario", {"changes": {"TNA": 1}, "year": 2031})[0])
    assert "--familles" in c["familles_extremes"]


def test_kit_reel_reproduit_les_familles_du_bulletin():
    try:
        kit = artefacts.charger_kit(2022)
    except artefacts.ArtefactIndisponible:
        pytest.skip("kit 2022 non produit")
    fam = (production.lire_bulletin(2022)["projection"] or {}).get("familles_extremes")
    r = artefacts.projeter(kit, kit["etat"].astype("float64"))
    if not fam or "familles_extremes" not in r:
        pytest.skip("familles pas encore ajoutees (20_veille_presaison.py --familles)")
    assert r["familles_extremes"]["plus_proche"] == fam["plus_proche"]
    for a, b in zip(r["familles_extremes"]["familles"], fam["familles"]):
        assert a["membres_utilises"] == b["membres_utilises"]
        if b["correlation"] is not None:
            assert abs(a["correlation"] - b["correlation"]) < 0.005


def test_kit_reel_reproduit_le_bulletin():
    try:
        kit = artefacts.charger_kit(2022)
    except artefacts.ArtefactIndisponible:
        pytest.skip("kit 2022 non produit")
    b = production.lire_bulletin(2022)
    r = artefacts.projeter(kit, kit["etat"].astype("float64"))
    assert round(r["probabilite_experimentale"], 3) == b["projection"]["probabilite_experimentale"]
    assert [a for a, _ in r["analogues"]] == [a["annee"] for a in b["projection"]["analogues"]]


# =============================================================================
# 2. Cartes de l'etat oceanique
# =============================================================================
def test_etat_sauve_puis_relu(tmp_path, monkeypatch):
    monkeypatch.setattr(artefacts, "DOSSIER_ETATS", tmp_path)
    champ = np.full((120, 360), 0.5)
    champ[:10] = np.nan
    artefacts.sauver_etat(2031, champ, np.linspace(-59.5, 59.5, 120),
                          np.linspace(-179.5, 179.5, 360), [(2030, 11), (2031, 4)])
    z, lats, lons, mois = artefacts.charger_etat(2031)
    assert z.shape == (60, 180) and np.isnan(z[0, 0]) and np.isclose(z[30, 30], 0.5)
    assert mois == ["2030-11", "2031-04"] and lats[0] == pytest.approx(-59.0)
    assert artefacts.moyenne_boites(z, lats, lons, artefacts.BOITES_SCENARIO["TNA"]) == 0.5


def test_carte_etat_oceanique_reelle_et_rendue():
    try:
        artefacts.charger_etat(2022)
    except artefacts.ArtefactIndisponible:
        pytest.skip("etat 2022 non produit")
    c, store = _executer("show_map", {"type": "etat_oceanique", "year": 2022})
    c = _charge(c)
    assert c["carte"] and c["resume"]["saison"] == 2022
    assert c["resume"]["pour_comparer"].startswith("show_map type sst_cluster")
    fig = store.obtenir("s1", c["figure_id"])
    png = figures.rendre(fig.spec, "hud")
    assert png[:4] == b"\x89PNG"
    assert figures.en_csv(fig.spec).count("\n") > 1000
    r, _ = _executer("show_map", {"type": "etat_oceanique", "year": 1950})
    assert r["is_error"]


# =============================================================================
# 1. Briefing vocal
# =============================================================================
def test_briefing_complet_avec_projection(bulletins_synthetiques, monkeypatch):
    # La carte de l'etat n'existe pas pour 2031: l'etape 2 doit se replier.
    store = figures.FigureStore()
    p = briefing.plan(2031)
    assert p["annee"] == 2031 and len(p["etapes"]) == len(briefing.ETAPES)
    for n in range(1, len(briefing.ETAPES) + 1):
        e = briefing.etape(n, 2031, store, "s1")
        assert e["numero"] == n and e["narration"] and e["page"] == "Veille"
        assert e["filtres"] == {"saison": 2031}
    # Competence non demontree (confiance faible): probabilite indicative, aucun niveau.
    narr = briefing.etape(1, 2031, store, "s1")["narration"]
    assert "indicative" in narr and "élevé" not in narr
    assert "configuration 4" in briefing.etape(3, 2031, store, "s1")["narration"]
    assert "la 2, puis la 4" in briefing.etape(4, 2031, store, "s1")["narration"]
    assert "2010" in briefing.etape(5, 2031, store, "s1")["narration"]
    assert "ANACIM" in briefing.etape(8, 2031, store, "s1")["narration"]


def test_briefing_sans_projection_dit_pourquoi(bulletins_synthetiques):
    bulletins_synthetiques[2031] = _bulletin(2031, projection=False)
    e = briefing.etape(2, 2031, figures.FigureStore(), "s1")
    assert "manque 11/2030" in e["narration"] and e["figure"] is None


def test_briefing_etape_hors_bornes(bulletins_synthetiques):
    assert briefing.etape(0, 2031, figures.FigureStore(), "s1") is None
    assert briefing.etape(99, 2031, figures.FigureStore(), "s1") is None


def test_routes_briefing(client, token):
    h = {"X-Jarvis-Session": token}
    plan = client.get("/jarvis/api/briefing", headers=h)
    if plan.status_code == 404:
        pytest.skip("aucun bulletin produit")
    annee = plan.json()["annee"]
    e = client.post("/jarvis/api/briefing/1?annee=%d" % annee, headers=h).json()
    assert e["page"] == "Veille" and e["narration"] and e["annee"] == annee
    assert client.post("/jarvis/api/briefing/99", headers=h).status_code == 404
    assert client.get("/jarvis/api/briefing?annee=1950", headers=h).status_code == 404
    assert client.post("/jarvis/api/briefing/1").status_code in (401, 403)
    assert client.fake.calls == []


def test_outil_briefing_part_vers_le_widget(client, token, bulletins_synthetiques):
    client.fake.tool_calls = [("present_bulletin_briefing", {"year": 2001})]
    r = client.post(CHAT, json={"message": "Presente le bulletin 2001"},
                    headers={"X-Jarvis-Session": token})
    nav = [d for n, d in sse_events(r.text) if n == "navigation"]
    assert nav == [{"presentation": {"programme": "briefing", "annee": 2001}}]


def test_outil_briefing_refuse_une_saison_sans_bulletin(bulletins_synthetiques):
    r, _ = _executer("present_bulletin_briefing", {"year": 1990})
    assert r["is_error"]


def test_une_presentation_inconnue_n_atteint_pas_le_widget():
    from jarvis.app import _noter_navigation
    nav = []
    _noter_navigation({"content": json.dumps({"presentation": {"programme": "rm -rf"}})}, nav)
    _noter_navigation({"content": json.dumps({"presentation": {"programme": "briefing",
                                                               "annee": "2027; x"}})}, nav)
    assert nav == [{"presentation": {"programme": "briefing", "annee": None}}]


def test_widget_joue_le_briefing():
    assert 'data-action="briefing"' in SOURCE
    assert 'Soutenance.demarrer(1, {chemin: "briefing"' in SOURCE
    assert "presentationDemandee = data.presentation" in SOURCE
    moteur = SOURCE[SOURCE.index("var Soutenance = (function(){"):]
    moteur = moteur[:moteur.index("  })();")]
    assert 'fetch(url(), {headers: headers()})' in moteur
    assert 'fetch(url("/" + n)' in moteur
    assert "/api/soutenance/" not in moteur      # plus d'URL en dur


# =============================================================================
# 4. Veille mensuelle
# =============================================================================
def test_mois_de_veille_ecoules():
    import datetime as dt
    import importlib.util
    from pathlib import Path
    chemin = Path(__file__).resolve().parent.parent / "scripts" / "22_veille_mensuelle.py"
    spec = importlib.util.spec_from_file_location("s22", chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.mois_ecoules(2027, dt.date(2026, 9, 27)) == []
    assert m.mois_ecoules(2027, dt.date(2027, 2, 3)) == [(2026, 11), (2026, 12), (2027, 1)]
    assert len(m.mois_ecoules(2027, dt.date(2027, 5, 2))) == 6


def test_etapes_de_veille_dans_le_pipeline_mais_pas_le_pipeline_complet():
    from jarvis import code_ops
    from jarvis.tools.dataset import get
    etapes = {e["id"]: e for e in get("pipeline")["steps"]}
    for i in ("19", "20", "21", "22"):
        assert etapes[i]["veille"] is True
    assert "22_veille_mensuelle.py" in code_ops.scripts_autorises()
    assert not etapes["04"].get("veille")


# =============================================================================
# 5. Diffusion
# =============================================================================
def test_formats_diffusables(tmp_path, bulletins_synthetiques):
    b = bulletins_synthetiques[2031]
    sms = diffusion.sms(b)
    assert len(sms) <= diffusion.MAX_SMS and "indicative" in sms and "ANACIM" in sms
    assert "ÉLEVÉ" not in sms.upper()
    assert "50 %" in sms
    res = diffusion.resume(b)
    assert diffusion.CONSEILS["indicatif"] in res and "Fiabilité" in res
    assert diffusion.CONSEILS["eleve"] not in res
    diffusion.docx(b, tmp_path / "b.docx")
    assert (tmp_path / "b.docx").stat().st_size > 10000


def test_sms_jamais_trop_long(bulletins_synthetiques):
    b = dict(bulletins_synthetiques[2031])
    b["niveau_risque"] = dict(b["niveau_risque"], libelle="X" * 400, confiance="moyenne")
    assert len(diffusion.sms(b)) == diffusion.MAX_SMS


def test_diffusion_propose_sans_ecrire_puis_ecrit_apres_approbation(
        tmp_path, monkeypatch, bulletins_synthetiques):
    monkeypatch.setattr(diffusion, "DOSSIER", tmp_path / "diffusion")
    monkeypatch.setattr(diffusion, "DOSSIER_SORTIE", tmp_path / "outputs" / "veille")
    registre = actions.RegistreActions()
    r, _ = _executer("draft_bulletin_release", {"year": 2031}, profil="admin",
                     registre=registre)
    c = _charge(r)
    assert c["statut"] == "proposition_deposee" and len(c["sms"]) <= 320
    assert not (tmp_path / "diffusion").exists()          # rien d'ecrit
    action = registre.recuperer("s1", c["action_id"])
    assert action.type == "veille_diffusion" and action.payload == {"annee": 2031}
    # Ce que le serveur execute apres le clic d'approbation:
    monkeypatch.setattr(diffusion, "DOSSIER_SORTIE", tmp_path / "a" / "b")
    resultat = actions.executer(None, action)
    assert len(resultat["fichiers"]) == 3
    assert (tmp_path / "diffusion" / "veille_2031.docx").is_file()


def test_diffusion_reservee_a_l_admin():
    r, _ = _executer("draft_bulletin_release", {})
    assert r["is_error"]


# =============================================================================
# Comparaison de cartes a l'ecran (27/09/2026)
# =============================================================================
def test_comparaison_demandee_dans_une_question_suivante(client, token):
    """show_map(compare_with_displayed) -> evenement figure avec comparer=true."""
    client.fake.tool_calls = [("show_map", {"type": "frequence_extremes",
                                            "compare_with_displayed": True})]
    r = client.post(CHAT, json={"message": "Compare-la avec la carte affichee"},
                    headers={"X-Jarvis-Session": token})
    figs = [d for n, d in sse_events(r.text) if n == "figure"]
    assert len(figs) == 1 and figs[0]["carte"] and figs[0]["comparer"] is True
    client.fake.tool_calls = [("show_map", {"type": "frequence_extremes"})]
    r = client.post(CHAT, json={"message": "Une carte"}, headers={"X-Jarvis-Session": token})
    figs = [d for n, d in sse_events(r.text) if n == "figure"]
    assert figs[0]["comparer"] is False
    # Seul un vrai booleen compte: le modele ne glisse pas une chaine.
    client.fake.tool_calls = [("show_map", {"type": "frequence_extremes",
                                            "compare_with_displayed": "oui"})]
    r = client.post(CHAT, json={"message": "x"}, headers={"X-Jarvis-Session": token})
    assert [d for n, d in sse_events(r.text) if n == "figure"][0]["comparer"] is False


def test_widget_compare_avec_la_carte_affichee_sans_image_orpheline():
    assert "if(data.comparer){ Ecran.comparerAvecCourante(data); }" in SOURCE
    ecran = SOURCE[SOURCE.index("var Ecran = (function(){"):]
    ecran = ecran[:ecran.index("  })();")]
    # Garde-fou par jeton de rendu, pas par index (meme index en mode seul
    # et en comparaison: l'image de la carte seule s'inserait dans le duo).
    assert "var jeton = ++rendu;" in ecran
    assert "courant !== i" not in ecran and "jeton !== courant" not in ecran
    assert ecran.count("if(jeton !== rendu){ return; }") == 3
