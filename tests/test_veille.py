"""Tests de la veille pre-saison (paquet veille/ et outil Jarvis get_seasonal_outlook).

Rien ici ne telecharge ni ne relit les 42 Go d'OISST: C3S est simule par des
jeux xarray synthetiques, le cube par de petites grilles.
"""
import json

import numpy as np
import pandas as pd
import pytest

from veille import INONDATIONS_CONNUES
from veille import annees as mod_annees
from veille import bulletin as mod_bulletin
from veille import c3s as mod_c3s
from veille import cube as mod_cube
from veille import production


# =============================================================================
# Definition d'une annee extreme
# =============================================================================
def test_empreinte_compte_les_annees_sans_evenement():
    ev = pd.DataFrame({"year": [2000, 2000, 2002], "coverage_percent": [10.0, 5.0, 3.0]})
    s = mod_annees.empreinte(ev, debut=2000, fin=2003)
    assert list(s.index) == [2000, 2001, 2002, 2003]
    assert list(s.values) == [15.0, 0.0, 3.0, 0.0]


def test_la_definition_retrouve_les_inondations_documentees():
    """Garde-fou scientifique: si le catalogue change, la definition doit
    toujours classer extremes les annees d'inondations connues."""
    v = mod_annees.verification_definition()
    assert v["inondations_documentees"] == len(INONDATIONS_CONNUES)
    assert v["classees_extremes"] == len(INONDATIONS_CONNUES)
    assert max(v["rangs"].values()) <= 12


def test_seuil_tiers_superieur():
    s = pd.Series(np.arange(1, 10, dtype=float), index=range(2000, 2009))
    assert mod_annees.seuil(s) == pytest.approx(np.quantile(np.arange(1, 10), 2 / 3))
    table, seuil = mod_annees.classement(s)
    assert table["extreme"].sum() == 3


# =============================================================================
# Cube SST
# =============================================================================
def _cube_synthetique(annees=(2000, 2001), n=4, m=6):
    cube = mod_cube.Cube.vide()
    lats, lons = np.linspace(-1, 1, n), np.linspace(0, 5, m)
    for a in annees:
        mois = [(a, k) for k in range(1, 13)]
        champs = [np.full((n, m), (a - 2000) + k / 100, dtype="float32") for k in range(1, 13)]
        champs[0][0, 0] = np.nan
        cube.ajouter(mois, champs, ["%d-07-01" % a], [np.ones((n, m), "float32")], lats, lons)
    return cube


def test_cube_codage_int16_aller_retour():
    x = np.array([[-3.1234, 0.0, np.nan, 12.5]], dtype="float32")
    y = mod_cube._decoder(mod_cube._coder(x))
    assert np.isnan(y[0, 2])
    assert np.allclose(y[0, [0, 1, 3]], [-3.12, 0.0, 12.5], atol=0.006)


def test_cube_fusion_ordonnee_et_remplacement():
    cube = _cube_synthetique((2001, 2000))
    assert cube.mois[0] == (2000, 1) and cube.mois[-1] == (2001, 12)
    assert len(cube.evt_dates) == 2
    # Reextraire 2000 remplace ses mois au lieu de les dupliquer
    n = cube._mensuel.shape
    cube.ajouter([(2000, 3)], [np.zeros(n[1:], "float32")], [], [], cube.lats, cube.lons)
    assert len(cube.mois) == 24
    assert np.allclose(cube.mensuel(2000, 3), 0)


def test_cube_etat_novembre_avril(tmp_path):
    cube = _cube_synthetique((2000, 2001))
    chemin = tmp_path / "cube.npz"
    cube.sauver(chemin)
    cube = mod_cube.Cube.charger(chemin)
    attendu = np.mean([0.11, 0.12, 1.01, 1.02, 1.03, 1.04])
    assert cube.etat(2001)[1, 1] == pytest.approx(attendu, abs=0.01)
    with pytest.raises(mod_cube.CubeIndisponible, match="11/1999"):
        cube.etat(2000)
    assert cube.annees_etat_complet() == [2001]
    # Le pixel manquant d'un seul mois est exclu du masque commun
    assert not cube.pixels_toujours_valides()[0]


def test_cube_absent_message_utile(tmp_path):
    with pytest.raises(mod_cube.CubeIndisponible, match="19_build_sst_cube"):
        mod_cube.Cube.charger(tmp_path / "absent.npz")


# =============================================================================
# Copernicus C3S
# =============================================================================
def _jeu_c3s(membres_mm_jour):
    import xarray as xr
    n = len(membres_mm_jour)
    val = np.array(membres_mm_jour, dtype="float64") / 86400.0 / 1000.0
    data = np.broadcast_to(val[:, None, None, None, None], (n, 1, 3, 2, 2)).copy()
    return xr.Dataset({"tprate": (("number", "forecast_reference_time", "forecastMonth",
                                   "latitude", "longitude"), data)},
                      coords={"latitude": [16.0, 13.0], "longitude": [-17.0, -12.0],
                              "forecastMonth": [4, 5, 6]})


def test_lecture_c3s_membres_en_mm_par_jour():
    v = mod_c3s.pluie_membres(_jeu_c3s([4.0, 5.0, 6.0]))
    assert np.allclose(v, [4.0, 5.0, 6.0])


def test_lecture_c3s_dimensions_inattendues():
    import xarray as xr
    ds = xr.Dataset({"tprate": (("x", "y"), np.zeros((2, 2)))})
    with pytest.raises(mod_c3s.C3SIndisponible):
        mod_c3s.pluie_membres(ds)


def test_requete_c3s_emission_avril_echeances_jas():
    r = mod_c3s.requete(2027)
    assert r["month"] == ["04"] and r["leadtime_month"] == ["4", "5", "6"]
    assert r["year"] == ["2027"] and r["area"] == [17, -18, 12, -11]


def _membres_avec_signal(empreinte, bruit=0.2, graine=1):
    rng = np.random.default_rng(graine)
    z = (empreinte - empreinte.mean()) / empreinte.std()
    return {int(a): 5 + z.loc[a] + rng.normal(0, bruit, 25) for a in empreinte.index}


def test_calibration_c3s_detecte_un_vrai_signal():
    emp = mod_annees.empreinte().loc[1981:2016]
    cal = mod_c3s.calibrer(_membres_avec_signal(emp), emp)
    assert cal["competence"]["auc"] > 0.85
    assert cal["competence"]["p_permutation"] < 0.01
    assert cal["coefficient"] > 0
    humide = mod_c3s.prevoir(np.full(51, 8.0), cal)
    sec = mod_c3s.prevoir(np.full(51, 3.0), cal)
    assert humide["probabilite_annee_extreme"] > 0.8 > 0.2 > sec["probabilite_annee_extreme"]
    assert humide["part_membres_au_dessus_normale"] == 1.0


def test_calibration_c3s_sans_signal_n_est_pas_significative():
    emp = mod_annees.empreinte().loc[1981:2016]
    rng = np.random.default_rng(3)
    bruit = {int(a): rng.normal(5, 1, 25) for a in emp.index}
    cal = mod_c3s.calibrer(bruit, emp)
    assert cal["competence"]["p_permutation"] > 0.05


def test_calibration_c3s_refuse_trop_peu_d_annees():
    emp = mod_annees.empreinte()
    with pytest.raises(mod_c3s.C3SIndisponible):
        mod_c3s.calibrer({2000: np.ones(3), 2001: np.ones(3)}, emp)


def test_env_ne_lit_que_les_variables_cds(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=secret\nCDSAPI_KEY='abc-123'\n", encoding="utf-8")
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mod_c3s.charger_env(env)
    import os
    assert os.environ["CDSAPI_KEY"] == "abc-123"
    assert "ANTHROPIC_API_KEY" not in os.environ


# =============================================================================
# Bulletin
# =============================================================================
@pytest.mark.parametrize("p,code", [(0.05, "faible"), (0.2, "normal"), (0.39, "normal"),
                                    (0.4, "eleve"), (0.6, "tres_eleve"), (1.0, "tres_eleve"),
                                    (None, "indetermine")])
def test_niveaux_de_risque(p, code):
    assert mod_bulletin.niveau(p)[0] == code


COMP_PROJ = {"loyo": {"auc": 0.72, "p_permutation": 0.009, "n": 40},
             "prevision_reelle": {"auc": 0.54, "p_permutation": 0.39, "n": 26},
             "verdict": "signal physique present", "utilisable_seule": False}
PROJ = {"probabilite_experimentale": 0.8,
        "configurations": [{"configuration": 4, "correlation": 0.5,
                            "annees_principales": [2010, 2012], "part_evenements_en_annee_extreme": 0.7}],
        "toutes_configurations": [{"configuration": 4, "correlation": 0.5}],
        "analogues": [{"annee": 2010, "correlation": 0.6, "empreinte": 1152.0, "extreme": True,
                       "inondation_documentee": True}]}


def test_la_projection_ne_fixe_jamais_le_niveau_sans_competence():
    b = mod_bulletin.composer(2027, projection=PROJ, competence_projection=COMP_PROJ)
    assert b["niveau_risque"]["code"] == "indetermine"
    assert b["niveau_risque"]["probabilite_annee_extreme"] is None
    assert "expérimentale" in b["synthese"]
    assert "non déterminé" in b["synthese"]


def test_c3s_fixe_le_niveau_et_la_confiance():
    c3s = {"disponible": True, "probabilite_annee_extreme": 0.65, "anomalie_standardisee": 1.2,
           "part_membres_au_dessus_normale": 0.7, "centre": "ecmwf", "systeme": "51",
           "pluie_jas_mm_jour": 6.1,
           "competence": {"auc": 0.75, "p_permutation": 0.01, "brier_skill_score": 0.12, "n": 36}}
    b = mod_bulletin.composer(2027, projection=PROJ, c3s=c3s, competence_projection=COMP_PROJ)
    n = b["niveau_risque"]
    assert (n["code"], n["source"], n["confiance"]) == ("tres_eleve", "c3s", "moyenne")
    assert mod_bulletin.presentation(n)["mode"] == "niveau"
    assert "TRÈS ÉLEVÉ" in mod_bulletin.markdown(b)
    c3s["competence"]["p_permutation"] = 0.2
    b = mod_bulletin.composer(2027, projection=PROJ, c3s=c3s, competence_projection=COMP_PROJ)
    assert b["niveau_risque"]["confiance"] == "faible"
    md = mod_bulletin.markdown(b)
    assert "ECMWF" in md and "65 %" in md


def test_competence_non_demontree_pas_de_niveau_affiche():
    """Revue 27/09/2026 (V1): confiance faible -> probabilite indicative, jamais un niveau."""
    c3s = {"disponible": True, "probabilite_annee_extreme": 0.65, "anomalie_standardisee": 1.2,
           "part_membres_au_dessus_normale": 0.7, "centre": "ecmwf", "systeme": "51",
           "pluie_jas_mm_jour": 6.1,
           "competence": {"auc": 0.59, "p_permutation": 0.19, "brier_skill_score": 0.03, "n": 36}}
    b = mod_bulletin.composer(2027, projection=PROJ, c3s=c3s, competence_projection=COMP_PROJ)
    pres = mod_bulletin.presentation(b["niveau_risque"])
    assert pres["mode"] == "probabilite" and pres["valeur"] == "65 %"
    assert "non démontrée" in pres["note"]
    md = mod_bulletin.markdown(b)
    assert "TRÈS ÉLEVÉ" not in md and "Probabilité indicative" in md
    assert "très élevé" not in b["synthese"] and "aucun niveau" in b["synthese"]
    from veille import diffusion
    assert "élevé" not in diffusion.sms(b).lower()
    assert "indicative" in diffusion.sms(b)


def test_bulletin_retrospectif_porte_sa_verification():
    b = mod_bulletin.composer(2020, projection=PROJ, competence_projection=COMP_PROJ)
    v = b["verification"]
    assert v["extreme_observe"] is True and v["inondation_documentee"] is True
    assert "Vérification" in b["synthese"]
    json.dumps(b)  # serialisable


def test_bulletin_futur_sans_verification():
    b = mod_bulletin.composer(2027)
    assert "verification" not in b
    assert b["contexte"]["frequence_recente"]["sur"] == 10


# =============================================================================
# Production: lecture des bulletins ecrits
# =============================================================================
def test_bulletins_disponibles_et_lecture(tmp_path, monkeypatch):
    monkeypatch.setattr(production, "DOSSIER_SORTIE", tmp_path)
    assert production.bulletins_disponibles() == []
    for a in (2020, 2027):
        (tmp_path / ("bulletin_%d.json" % a)).write_text(json.dumps({"annee": a}), encoding="utf-8")
    (tmp_path / "bulletin_xx.json").write_text("{}", encoding="utf-8")
    assert production.bulletins_disponibles() == [2027, 2020]
    assert production.lire_bulletin(2020) == {"annee": 2020}


# =============================================================================
# Outil Jarvis
# =============================================================================
@pytest.fixture
def bulletins_simules(monkeypatch):
    b = mod_bulletin.composer(2027, projection=PROJ, competence_projection=COMP_PROJ)
    monkeypatch.setattr(production, "bulletins_disponibles", lambda: [2027, 2020])
    monkeypatch.setattr(production, "lire_bulletin", lambda a: dict(b, annee=a))
    return b


def test_outil_rend_le_plus_recent_avec_sa_regle(bulletins_simules):
    from jarvis.tools import veille as outil
    r = outil.run({}, None)
    assert r["annee"] == 2027
    assert "experimentale" in r["regle_interpretation"]
    assert r["competence_projection"]["prevision_reelle"]["auc"] == 0.54
    assert r["niveau_risque"]["code"] == "indetermine"


def test_outil_annee_sans_bulletin(bulletins_simules):
    from jarvis.tools import veille as outil
    from jarvis.tools.common import ToolInputError
    with pytest.raises(ToolInputError, match="2020, 2027"):
        outil.run({"year": 2015}, None)


def test_outil_enregistre_et_public():
    from jarvis.tools import registry
    noms = {s["name"] for s in registry.specs_for("public")}
    assert "get_seasonal_outlook" in noms


def test_page_veille_connue_de_jarvis():
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).resolve().parent.parent / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import jarvis_widget
    from jarvis import page_context
    from jarvis.tools import navigation
    assert "Veille" in page_context.PAGES
    assert navigation.FILTRES["Veille"] == ("saison",)
    assert jarvis_widget.CLES_CONTEXTE["Veille"] == {"saison": "veille_annee"}
    ctx = jarvis_widget.contexte_page({"nav_page": "Veille", "veille_annee": 2027})
    assert page_context.nettoyer(ctx)["filtres"] == {"saison": 2027}


# =============================================================================
# Familles d'oceans des saisons extremes (descriptif)
# =============================================================================
def _etats_familles(n=400, graine=1):
    """Etats synthetiques: A et B ont chacune un motif propre, le reste du bruit."""
    rng = np.random.default_rng(graine)
    motif_a, motif_b = rng.normal(size=n), rng.normal(size=n)
    etats = {}
    for a in range(1984, 2024):
        x = 0.3 * rng.normal(size=n)
        if a in (1999, 2000, 2012):
            x += motif_a
        elif a in (2005, 2010, 2020):
            x += motif_b
        etats[a] = x
    return etats, motif_a, motif_b, np.ones(n)


def test_familles_sans_fuite():
    from veille import familles
    etats, motif_a, _, w = _etats_familles()
    vus = []

    def etat_de(a):
        vus.append(a)
        return etats[a]

    r = familles.ressemblance(etat_de, list(etats), motif_a, 2005, w)
    assert max(vus) < 2005
    fa, fb = r["familles"]
    assert fa["membres_utilises"] == [1999, 2000]
    assert fb["membres_utilises"] == [] and fb["correlation"] is None
    assert r["plus_proche"] == "A"


def test_familles_reconnait_la_bonne_famille_ou_aucune():
    from veille import familles
    etats, motif_a, motif_b, w = _etats_familles()
    r = familles.ressemblance(etats.get, list(etats), motif_b + 0.2 * motif_a, 2024, w)
    assert r["plus_proche"] == "B"
    assert r["familles"][1]["membres_utilises"] == [2005, 2010, 2020]
    bruit = np.random.default_rng(9).normal(size=motif_a.size)
    r = familles.ressemblance(etats.get, list(etats), bruit, 2024, w)
    assert r["plus_proche"] is None
    assert "aucune" in familles.phrase(r)


def test_familles_trop_peu_d_annees():
    from veille import familles
    etats, motif_a, _, w = _etats_familles()
    r = familles.ressemblance(etats.get, list(etats), motif_a, 1990, w)
    assert all(f["correlation"] is None for f in r["familles"])
    assert familles.phrase(r) is None


FAM = {"seuil": 0.3, "plus_proche": "A", "avertissement": "Ressemblance descriptive : test.",
       "familles": [{"code": "A", "nom": "La Niña et Atlantique tropical frais",
                     "annees": [1999, 2000, 2012], "membres_utilises": [1999, 2000, 2012],
                     "signature": "Niño3.4 −1,2", "correlation": 0.45},
                    {"code": "B", "nom": "Océans chauds partout", "annees": [2005, 2010, 2020],
                     "membres_utilises": [2005, 2010, 2020], "signature": "TNA +1,4",
                     "correlation": -0.1}]}


def test_bulletin_cite_les_familles_sans_prevoir():
    proj = dict(PROJ, familles_extremes=FAM)
    b = mod_bulletin.composer(2027, projection=proj, competence_projection=COMP_PROJ)
    assert "famille A" in b["synthese"] and "1999/2000/2012" in b["synthese"]
    assert "descriptive" in b["synthese"]
    assert b["niveau_risque"]["code"] == "indetermine"
    md = mod_bulletin.markdown(b)
    assert "Familles d'océans des saisons extrêmes" in md and "(la plus proche)" in md
    # Bulletin ancien sans le champ: rien ne casse
    assert "famille" not in mod_bulletin.composer(2027, projection=PROJ)["synthese"]


def test_outil_rend_les_familles(monkeypatch):
    from jarvis.tools import veille as outil
    b = mod_bulletin.composer(2027, projection=dict(PROJ, familles_extremes=FAM),
                              competence_projection=COMP_PROJ)
    monkeypatch.setattr(production, "bulletins_disponibles", lambda: [2027])
    monkeypatch.setattr(production, "lire_bulletin", lambda a: b)
    r = outil.run({}, None)
    assert r["projection"]["familles_extremes"]["plus_proche"] == "A"
    assert "DESCRIPTIVE" in r["regle_interpretation"]


def test_completer_familles_garde_le_bulletin(tmp_path, monkeypatch):
    from veille import familles
    b = mod_bulletin.composer(2020, projection=PROJ, competence_projection=COMP_PROJ)
    b["emis_le"] = "2026-09-27"
    (tmp_path / "bulletin_2020.json").write_text(json.dumps(b), encoding="utf-8")
    monkeypatch.setattr(production, "DOSSIER_SORTIE", tmp_path)

    class CtxFactice:
        class cube:
            @staticmethod
            def mois_etat_manquants(annee):
                return []

        w = np.ones(3)

        def etat(self, annee, partiel=False):
            return np.zeros(3)

    monkeypatch.setattr(production.mod_proj, "Contexte", lambda cube: CtxFactice())
    monkeypatch.setattr(production.Cube, "charger", staticmethod(lambda *a: None))
    monkeypatch.setattr(familles, "preparer_contexte", lambda ctx, annee: None)
    monkeypatch.setattr(familles, "evaluer", lambda prep, champ, annee, w: FAM)
    kits = []
    monkeypatch.setattr(production.artefacts, "completer_kit_familles",
                        lambda annee, prep: kits.append(annee) or False)
    assert production.completer_familles(journal=lambda *_: None) == [2020]
    assert kits == [2020]   # le kit de scenario est aussi complete
    nouveau = json.loads((tmp_path / "bulletin_2020.json").read_text(encoding="utf-8"))
    assert nouveau["emis_le"] == "2026-09-27"
    assert nouveau["projection"]["familles_extremes"]["plus_proche"] == "A"
    assert "famille A" in (tmp_path / "bulletin_2020.md").read_text(encoding="utf-8")


def test_briefing_dit_la_famille_sans_prevoir():
    from jarvis import briefing
    phrase = briefing._familles(FAM)
    assert "type A" in phrase and "1999, 2000 et 2012" in phrase
    assert "pas une prévision" in phrase
    assert "aucun" in briefing._familles(dict(FAM, plus_proche=None))
    assert briefing._familles(None) == ""
    etape = briefing._analogues({"annee": 2027, "projection": dict(PROJ, familles_extremes=FAM)},
                                None, None)
    assert "type A" in etape["narration"]


def test_familles_kit_aller_retour():
    from veille import familles
    etats, motif_a, _, w = _etats_familles()
    prep = familles.preparer(etats.get, list(etats), 2008)
    direct = familles.evaluer(prep, motif_a, 2008, w)
    relu = familles.evaluer(familles.depuis_kit(familles.vers_kit(prep)), motif_a, 2008, w)
    assert [f["membres_utilises"] for f in relu["familles"]] == [[1999, 2000], [2005]]
    for a, b in zip(direct["familles"], relu["familles"]):
        assert abs(a["correlation"] - b["correlation"]) < 0.005
    assert familles.vers_kit(None) == {} and familles.depuis_kit({}) is None


def test_synthese_sans_annee_principale_anterieure():
    """Bulletin 2012: les annees principales de C3 sont toutes posterieures."""
    conf = [dict(PROJ["configurations"][0], annees_principales=[])]
    b = mod_bulletin.composer(2012, projection=dict(PROJ, configurations=conf),
                              competence_projection=COMP_PROJ)
    assert "celle des années ." not in b["synthese"]
    assert "postérieures à la saison" in b["synthese"]
    assert "| C4 | — | 0,50 | — |" in mod_bulletin.markdown(b)
