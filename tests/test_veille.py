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
    c3s["competence"]["p_permutation"] = 0.2
    b = mod_bulletin.composer(2027, projection=PROJ, c3s=c3s, competence_projection=COMP_PROJ)
    assert b["niveau_risque"]["confiance"] == "faible"
    md = mod_bulletin.markdown(b)
    assert "TRÈS ÉLEVÉ" in md and "ECMWF" in md and "65 %" in md


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
