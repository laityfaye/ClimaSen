"""Donnees sources lues par Iris : get_rainfall, get_ocean_state, get_locality,
animation de tout evenement (jarvis/sources.py).

Tests sur les vraies donnees du dossier data/ ; ceux qui demandent un fichier
non versionne (CHIRPS .mat, OISST journalier, cube SST) sont sautes s'il manque,
comme sur le serveur avant telechargement. Le comportement SANS ces fichiers
est teste en pointant les chemins vers un dossier vide.
"""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from jarvis import sources as S
from jarvis.tools import localite, ocean, pluie
from jarvis.tools.common import ToolInputError

AVEC_MAT = S.CHIRPS_MAT.is_file()
AVEC_OISST = (S.OISST_DOSSIER / "sst_day_anom_2010.nc").is_file()


@pytest.fixture(scope="module")
def evenements():
    from jarvis.tools import dataset
    return {"events": dataset.get("events")}


@pytest.fixture
def sans_brut(monkeypatch, tmp_path):
    """Serveur sans fichiers bruts : .mat, OISST et cube absents."""
    monkeypatch.setattr(S, "CHIRPS_MAT", tmp_path / "absent.mat")
    monkeypatch.setattr(S, "OISST_DOSSIER", tmp_path / "SST")
    monkeypatch.setattr(S, "CUBE_SST", tmp_path / "cube.npz")
    for f in (S._mat, S._oisst_annee, S.cube):
        f.cache_clear()
    yield
    for f in (S._mat, S._oisst_annee, S.cube):
        f.cache_clear()


# --- CHIRPS ---------------------------------------------------------------------
@pytest.mark.skipif(not AVEC_MAT, reason="CHIRPS brut absent")
@pytest.mark.parametrize("jour", ["2012-09-28", "1999-08-14", "2005-02-10"])
def test_la_pluie_reconstruite_est_le_chirps_brut(jour):
    """anomalie x ecart-type + climatologie = CHIRPS brut, saison seche comprise."""
    d = date.fromisoformat(jour)
    p, _ = S.pluie_jour_senegal(d)
    g = S.grille_senegal()
    for i in (0, 9, 17):
        for j in (2, 12, 24):
            if g["terre"][i, j]:
                brut, _ = S.pluie_point_afrique_ouest(d, g["lats"][i], g["lons"][j])
                assert p[i, j] == pytest.approx(brut, abs=1e-3)


def test_un_jour_sur_une_region(evenements):
    r = pluie.run({"date": "2012-09-28", "place": "region de Kolda"}, evenements)
    assert r["lieu"].startswith("région de Kolda") and r["pixels_chirps"] > 5
    assert r["au_catalogue_des_extremes"]["oui"] is True
    assert r["anomalie_max_sigma"] > 2 and r["pixels_sup_2sigma"] >= 1


def test_un_jour_sans_evenement(evenements):
    r = pluie.run({"date": "2005-02-10", "place": "Senegal"}, evenements)
    assert r["pluie_moyenne_zone_mm"] == 0.0
    assert r["au_catalogue_des_extremes"] == {"oui": False}


def test_periode_cumul_et_normale(evenements):
    r = pluie.run({"date": "2020-07-01", "date_end": "2020-09-30", "place": "Pikine"},
                  evenements)
    assert r["n_jours"] == 92 and r["cumul_zone_mm"] > 0 and r["cumul_normal_mm"] > 0
    assert "pas forcement dans la zone" in r["evenements_du_catalogue_au_senegal"]["note"]
    assert "plus petite qu'un pixel" in r["methode_zone"]


def test_meme_grille_que_la_carte_d_un_evenement(evenements):
    """La carte show_map couvre toute la boite de detection (pays voisins compris) ;
    la zone "Senegal" ne garde que les pixels dans les frontieres : son maximum
    est inferieur ou egal, et la grille complete redonne celui de la carte."""
    from jarvis.tools import cartes
    _, resume = cartes.construire({"type": "evenement", "date": "2012-09-28"}, evenements)
    carte = resume["maximum_sur_la_carte"]["valeur"]
    p, _ = S.pluie_jour_senegal(date(2012, 9, 28))
    assert float(np.nanmax(p)) == pytest.approx(carte, abs=0.01)
    r = pluie.run({"date": "2012-09-28", "place": "Senegal"}, evenements)
    assert r["pluie_max_pixel_mm"] <= carte + 0.01


def test_lieu_homonyme_dit_lequel_est_retenu(evenements):
    r = pluie.run({"date": "2012-09-28", "place": "Kaolack"}, evenements)
    assert r.get("autres_lieux_du_meme_nom")


@pytest.mark.parametrize("params, message", [
    ({"date": "1979-01-01", "place": "Kolda"}, "hors periode"),
    ({"date": "2012-09-28"}, "place"),
    ({"date": "2012-01-01", "date_end": "2013-06-01", "place": "Kolda"}, "366"),
    ({"date": "2012-09-28", "place": "Zzzzqqq"}, "Lieu inconnu"),
])
def test_demandes_refusees(evenements, params, message):
    with pytest.raises(ToolInputError, match=message):
        pluie.run(params, evenements)


@pytest.mark.skipif(not AVEC_MAT, reason="CHIRPS brut absent")
def test_point_hors_du_senegal(evenements):
    r = pluie.run({"date": "2012-08-01", "date_end": "2012-08-31", "lat": 12.65, "lon": -8.0},
                  evenements)
    assert "hors du Senegal" in r["lieu"] and r["cumul_mm"] > 0


def test_hors_du_senegal_sans_fichier_brut(evenements, sans_brut):
    with pytest.raises(ToolInputError, match="absente de ce serveur"):
        pluie.run({"date": "2012-08-01", "lat": 12.65, "lon": -8.0}, evenements)
    # La grille du Senegal, versionnee, reste disponible.
    assert pluie.run({"date": "2012-08-01", "place": "Kolda"}, evenements)["pixels_chirps"] > 0


# --- OISST ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def indices():
    t = pd.read_csv(S.DATA / "raw" / "climate_indices" / "daily_indices_all.csv",
                    parse_dates=[0])
    return t.set_index(t.columns[0])


@pytest.mark.skipif(not (AVEC_OISST or S.CUBE_SST.is_file()), reason="SST absente")
@pytest.mark.parametrize("zone, mois", [("TNA", "2010-03"), ("Nino34", "2015-12"),
                                        ("ATL3", "2019-06")])
def test_proche_de_l_indice_publie(indices, zone, mois):
    """Meme boite que l'indice publie : ecart de quelques centiemes au plus."""
    r = ocean.run({"date": mois, "zone": zone}, {})
    assert r["anomalie_moyenne_degC"] == pytest.approx(indices[zone][mois].mean(), abs=0.06)
    assert "get_sst_index" in r["valeur_publiee"]


@pytest.mark.skipif(not S.CUBE_SST.is_file(), reason="cube SST absent")
def test_rang_parmi_les_memes_mois():
    r = ocean.run({"date": "2015-12", "zone": "Nino34"}, {})
    c = r["contexte_1983_2023"]
    assert c["rang_du_plus_chaud"] == 1 and c["sur"] == 41


@pytest.mark.skipif(not AVEC_OISST, reason="OISST journalier absent")
def test_un_jour_et_une_boite_libre():
    r = ocean.run({"date": "2012-07-01", "date_end": "2012-07-05",
                   "box": [-20, -10, 10, 20]}, {})
    assert r["resolution"] == "jour" and r["pas_de_temps_moyennes"] == 5
    assert r["anomalie_moyenne_degC"] is not None


def test_dipole_defini():
    if not (AVEC_OISST or S.CUBE_SST.is_file()):
        pytest.skip("SST absente")
    r = ocean.run({"date": "2009-11", "zone": "AMM"}, {})
    assert r["definition"] == "AMM = TNA - TSA"


@pytest.mark.parametrize("params, message", [
    ({"date": "2010-03", "box": [10, -10, 0, 5]}, "box hors domaine"),
    ({"date": "2010-03", "box": [-20, -10, 50, 70]}, "box hors domaine"),
    ({"date": "2010-03"}, "zone ou box"),
    ({"date": "1980-03", "zone": "TNA"}, "1983"),
    ({"date": "2010-03", "date_end": "2010-03-15", "zone": "TNA"}, "meme format"),
    ({"date": "2010-01", "date_end": "2011-06", "zone": "TNA"}, "12 mois"),
])
def test_demandes_ocean_refusees(params, message):
    with pytest.raises(ToolInputError, match=message):
        ocean.run(params, {})


def test_sans_sst_brute_le_dit(sans_brut):
    with pytest.raises(ToolInputError, match="absente de ce serveur"):
        ocean.run({"date": "2012-07-15", "zone": "golfe_de_guinee"}, {})


# --- Animation de tout evenement ------------------------------------------------
@pytest.mark.skipif(not AVEC_OISST, reason="OISST journalier absent")
def test_animation_calculee_identique_a_l_archive():
    from jarvis import cartes
    a = cartes.animations()
    jour = a["dates"][5]
    images, boites = S.animation_evenement(date.fromisoformat(jour))
    np.testing.assert_allclose(boites, a["boites"][a["index"][jour]], atol=1e-4)
    ref = cartes.images_evenement(jour)
    hors_ecretage = np.abs(images) <= 5.0          # archive int8 : +-5,08 degC
    assert np.nanmax(np.abs(images - ref)[hors_ecretage]) <= 0.021
    assert (np.isnan(images) == np.isnan(ref)).all()


def test_animation_hors_archive_sans_sst(evenements, sans_brut):
    from jarvis.tools import animation
    with pytest.raises(ToolInputError, match="seuls les evenements de l'archive"):
        animation.run({"date": "1999-08-14"}, evenements, figures=object(), session_id="s")


def test_animation_date_hors_catalogue(evenements):
    from jarvis.tools import animation
    with pytest.raises(ToolInputError, match="catalogue"):
        animation.run({"date": "1983-03-01"}, evenements, figures=object(), session_id="s")


# --- Localites -----------------------------------------------------------------
def test_localite_population_egale_au_rgph5():
    r = localite.run({"name": "Touba Mosquee"}, {})
    fiche = r["localites"][0]
    loc = pd.read_csv(S.LOCALITES, encoding="utf-8")
    attendu = loc.loc[loc["LOCALITE"] == "TOUBA MOSQUEE", "POPULATION"].iloc[0]
    assert fiche["population_par_recensement"]["2023"] == int(attendu)
    assert fiche["departement"].lower().endswith("backe")


def test_homonymes_signales_et_communes_proches():
    r = localite.run({"name": "Touba"}, {})
    assert r["n_localites_trouvees"] > 1
    assert "Touba Mosquee" in r["communes_au_nom_proche"]
    assert "preciser department" in r["inondations_documentees"]


def test_commune_sans_localite_du_meme_nom():
    r = localite.run({"name": "Thiaroye sur mer"}, {})
    c = r["communes"][0]
    assert c["departement"] == "Pikine" and c["population_par_recensement"]["2023"] > 50000
    assert 2009 in r["inondations_documentees"]["annees"]


def test_inondations_d_un_departement_citent_leur_source():
    r = localite.run({"department": "Pikine"}, {})["inondations_documentees"]
    assert r["annees"] == [2005, 2009, 2012, 2020]
    e = r["evenements_documentes"][0]
    assert e["source"] and e["document"] and e["extrait"]


def test_departement_sans_inondation_documentee_n_affirme_pas_l_absence():
    r = localite.run({"department": "Linguere"}, {})["inondations_documentees"]
    assert r["evenements_documentes"] == [] and "pas une preuve" in r["note"]


def test_localite_inconnue():
    with pytest.raises(ToolInputError, match="Aucune localite"):
        localite.run({"name": "Xyzzzq"}, {})


# --- Plafond de taille ------------------------------------------------------------
@pytest.mark.parametrize("outil, params", [
    (localite, {"name": "Touba"}), (localite, {"department": "Pikine"}),
    (localite, {"name": "Thiaroye sur mer"}),
    (pluie, {"date": "2020-07-01", "date_end": "2020-09-30", "place": "Senegal"}),
])
def test_resultats_sous_le_plafond(evenements, outil, params):
    import json
    from jarvis.tools.registry import MAX_RESULT_CHARS
    r = outil.run(params, evenements)
    assert len(json.dumps(r, ensure_ascii=False, default=str)) <= MAX_RESULT_CHARS


# --- Script 39 : verification des sources sur un serveur -------------------------
def _script39():
    import importlib.util
    from pathlib import Path
    chemin = Path(__file__).resolve().parent.parent / "scripts" / "39_verifier_sources.py"
    spec = importlib.util.spec_from_file_location("verifier_sources", chemin)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_csv_identique_quelle_que_soit_la_fin_de_ligne(tmp_path):
    """Git ecrit les CSV en CRLF sous Windows et en LF sous Linux : meme contenu,
    meme empreinte, sinon le serveur verrait tout fichier versionne 'different'."""
    m = _script39()
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_bytes(b"x,y\r\n1,2\r\n")
    b.write_bytes(b"x,y\n1,2\n")
    assert m.empreinte(a) == m.empreinte(b) and m.taille(a) == m.taille(b)
    c, d = tmp_path / "c.nc", tmp_path / "d.nc"          # binaire : octets exacts
    c.write_bytes(b"\r\n")
    d.write_bytes(b"\n")
    assert m.empreinte(c) != m.empreinte(d)
