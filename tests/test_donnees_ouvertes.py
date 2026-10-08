"""API ouverte (donnees_ouvertes/), montee sous /api/v1 dans le serveur d'IRIS.

Ces tests lisent les vrais fichiers publies (outputs/, data/processed/) : ce
sont eux que l'API sert, et les chiffres verifies ici sont ceux affiches sur
la plateforme. Ils se sautent si les fichiers manquent.
"""
import csv
import io

import pandas as pd
import pytest

from donnees_ouvertes import sources

pytestmark = pytest.mark.skipif(
    not all(sources.disponible(j) for j in sources.JEUX.values()),
    reason="fichiers de donnees publies absents")

API = "/api/v1"


@pytest.fixture
def api():
    """API seule, sans le serveur d'IRIS, avec un debit illimite."""
    from fastapi.testclient import TestClient

    from donnees_ouvertes import creer_api
    return TestClient(creer_api(capacite=100000, recharge_par_seconde=1000.0))


# --- montage dans le serveur d'IRIS -------------------------------------------

def test_montee_dans_le_serveur_iris(client):
    r = client.get(API + "/")
    assert r.status_code == 200
    assert r.json()["documentation"].endswith("/api/v1/docs")
    # Donnees publiques : lisibles depuis n'importe quel site.
    assert r.headers["access-control-allow-origin"] == "*"
    # Les en-tetes de securite du serveur s'appliquent aussi a l'API.
    assert r.headers["x-content-type-options"] == "nosniff"


def test_documentation_publique_et_csp_assouplie_pour_elle_seule(client):
    r = client.get(API + "/docs")
    assert r.status_code == 200
    assert "cdn.jsdelivr.net" in r.headers["content-security-policy"]
    assert "connect-src 'self' https://cdn.jsdelivr.net" in r.headers["content-security-policy"]
    assert "/api/v1/openapi.json" in r.text
    assert "API ouverte ClimatSen" in client.get(API + "/openapi.json").text
    assert client.get(API + "/openapi.json").status_code == 200
    autre = client.get(API + "/catalogue")
    assert "cdn.jsdelivr.net" not in autre.headers["content-security-policy"]


def test_les_routes_d_iris_ne_bougent_pas(client):
    assert client.get("/jarvis/health").status_code == 200


# --- catalogue ------------------------------------------------------------------

def test_catalogue_annonce_les_cinq_jeux_avec_sources_et_licence(api):
    c = api.get("/catalogue").json()
    assert [j["jeu"] for j in c["jeux"]] == [
        "departements", "arrondissements", "communes", "evenements", "annees"]
    for j in c["jeux"]:
        assert j["sources"] and j["licence"]["nom"]
        assert set(j["liens"]) >= {"json", "csv", "sdmx_csv", "sdmx_json"}
    assert c["jeux"][2]["liens"]["geojson"].endswith("/geo/communes.geojson")


def test_chaque_indicateur_a_une_unite_connue():
    for code, (libelle, unite) in sources.INDICATEURS.items():
        assert unite in sources.UNITES, code
    for j in sources.JEUX.values():
        assert set(j.indicateurs) <= set(sources.INDICATEURS), j.id


# --- donnees --------------------------------------------------------------------

def test_departements_complets_et_classes(api):
    r = api.get("/donnees/departements").json()
    assert r["total"] == 46 and len(r["donnees"]) == 46
    assert [d["rang"] for d in r["donnees"]] == list(range(1, 47))
    assert r["donnees"][0]["code"].startswith("SN")
    assert "avertissement" in r and "AUC" in r["avertissement"]


def test_filtres_region_et_indicateurs(api):
    r = api.get("/donnees/departements",
                params={"region": "Kolda", "indicateurs": "population,indice_risque"}).json()
    assert {d["code_region"] for d in r["donnees"]} == {"SN07"}
    assert len(r["donnees"]) == 3
    assert set(r["unites"]) == {"population", "indice_risque"}
    assert "alea" not in r["donnees"][0]
    assert api.get("/donnees/departements", params={"region": "SN07"}).json()["total"] == 3


def test_communes_identifiants_uniques_et_code_ansd(api):
    r = api.get("/donnees/communes").json()
    codes = [d["code"] for d in r["donnees"]]
    assert len(codes) == 552 == len(set(codes))
    dakar = api.get("/donnees/communes", params={"departement": "SN0101"}).json()["donnees"]
    assert dakar and all(d["code_departement"] == "SN0101" for d in dakar)
    assert all(isinstance(d["code_ansd"], int) for d in dakar)


def test_evenement_du_28_septembre_2012(api):
    e = api.get("/evenements/2012-09-28").json()
    assert e["population_touchee"] == 18069311
    assert e["code_departement_le_plus_touche"] == "SN0203"   # Mbacke
    assert e["rang_population_touchee"] == 1
    assert "sinistr" in e["avertissement"]
    assert "2012-01-15" not in set(sources.table("evenements")["periode"])
    assert api.get("/evenements/2012-01-15").status_code == 404
    assert api.get("/evenements/28-09-2012").status_code == 422


def test_tous_les_departements_les_plus_touches_ont_un_pcode():
    t = sources.table("evenements")
    nommes = t["departement_le_plus_touche"].notna()
    assert t.loc[nommes, "code_departement_le_plus_touche"].notna().all()


def test_filtres_des_evenements(api):
    r = api.get("/donnees/evenements", params={"annee": 2012, "population_min": 5000000,
                                               "tri": "population_touchee"}).json()
    assert r["total"] > 0
    assert all(d["periode"].startswith("2012") for d in r["donnees"])
    pops = [d["population_touchee"] for d in r["donnees"]]
    assert min(pops) >= 5000000 and pops == sorted(pops, reverse=True)
    # Une borne de fin annuelle inclut tous les jours de l'annee.
    fin = api.get("/donnees/evenements", params={"debut": "2012", "fin": "2012"}).json()
    assert "2012-09-28" in [d["periode"] for d in fin["donnees"]]
    assert fin["total"] == api.get("/donnees/evenements", params={"annee": 2012}).json()["total"]


def test_csv_simple(api):
    r = api.get("/donnees/departements", params={"format": "csv"})
    assert r.headers["content-type"].startswith("text/csv")
    lignes = list(csv.DictReader(io.StringIO(r.text)))
    assert len(lignes) == 46 and "indice_risque" in lignes[0]


@pytest.mark.parametrize("params", [
    {"annee": 2000},                       # filtre temporel sur un jeu sans temps
    {"indicateurs": "INCONNU"},
    {"tri": "colonne_absente"},
    {"phase": "Phase_2_pleine"},
])
def test_requetes_invalides_expliquees(api, params):
    r = api.get("/donnees/departements", params=params)
    assert r.status_code == 400
    assert r.json()["erreur"]["message"]


# --- SDMX -----------------------------------------------------------------------

def test_sdmx_csv_reproduit_les_valeurs_publiees(api):
    r = api.get("/sdmx/data/DF_RISQUE_DEPARTEMENTS/A..INDICE_RISQUE", params={"format": "sdmx-csv"})
    assert r.headers["content-type"].startswith("application/vnd.sdmx.data+csv")
    obs = pd.read_csv(io.StringIO(r.text))
    assert list(obs.columns) == ["STRUCTURE", "STRUCTURE_ID", "ACTION", "FREQ", "REF_AREA",
                                 "INDICATOR", "TIME_PERIOD", "OBS_VALUE", "UNIT_MEASURE"]
    assert (obs["STRUCTURE_ID"] == "CLIMATSEN:DF_RISQUE_DEPARTEMENTS(1.0)").all()
    source = pd.read_csv(sources.VULNERABILITE / "indice_risque_departements.csv")
    attendu = dict(zip(source["pcode"], source["indice_risque"]))
    assert dict(zip(obs["REF_AREA"], obs["OBS_VALUE"])) == attendu


def test_sdmx_json_cle_d_observation_decodable(api):
    r = api.get("/sdmx/data/CLIMATSEN,DF_EVENEMENTS,1.0/D.SN.POPULATION_TOUCHEE",
                params={"startPeriod": "2012-09-28", "endPeriod": "2012-09-28"})
    assert r.headers["content-type"].startswith("application/vnd.sdmx.data+json")
    m = r.json()
    dims = m["data"]["structures"][0]["dimensions"]["observation"]
    (cle, valeurs), = m["data"]["dataSets"][0]["observations"].items()
    decode = {d["id"]: d["values"][int(i)] for d, i in zip(dims, cle.split(":"))}
    assert decode["TIME_PERIOD"]["value"] == "2012-09-28"
    assert decode["INDICATOR"]["id"] == "POPULATION_TOUCHEE"
    assert valeurs[0] == 18069311


def test_sdmx_json_toutes_les_valeurs_non_nulles(api):
    m = api.get("/sdmx/data/DF_EXPOSITION_COMMUNES").json()
    t = sources.table("communes")
    attendu = int(t[list(sources.JEUX["communes"].indicateurs)].notna().sum().sum())
    assert len(m["data"]["dataSets"][0]["observations"]) == attendu


def test_sdmx_negociation_par_en_tete_accept(api):
    r = api.get("/sdmx/data/DF_EVENEMENTS_ANNUELS",
                headers={"Accept": "application/vnd.sdmx.data+csv;version=2.0.0"})
    assert r.text.startswith("STRUCTURE,")


def test_sdmx_libelles(api):
    r = api.get("/sdmx/data/DF_EVENEMENTS_ANNUELS/A.SN.NB_EVENEMENTS",
                params={"format": "sdmx-csv", "labels": "both", "startPeriod": "2020"})
    assert "FREQ: Fréquence" in r.text.splitlines()[0]
    assert ",A: Annuelle,SN: Sénégal," in r.text


@pytest.mark.parametrize("chemin, statut", [
    ("/sdmx/data/DF_INCONNU", 404),
    ("/sdmx/data/AUTRE,DF_EVENEMENTS,1.0", 404),
    ("/sdmx/data/DF_EVENEMENTS/D.SN", 400),                   # cle incomplete
    ("/sdmx/data/DF_EVENEMENTS/D.SN.POPULATION_TOUCHEE?startPeriod=2030", 404),
    ("/sdmx/data/DF_EVENEMENTS?startPeriod=12-2012", 400),
    ("/sdmx/codelist/AUTRE/CL_ZONE/1.0", 404),
    ("/sdmx/codelist/CLIMATSEN/CL_ABSENTE/1.0", 404),
])
def test_sdmx_erreurs(api, chemin, statut):
    assert api.get(chemin).status_code == statut


def test_liste_de_codes_des_zones_hierarchique(api):
    m = api.get("/sdmx/codelist/CLIMATSEN/CL_ZONE/1.0").json()
    codes = m["data"]["codelists"][0]["codes"]
    ids = {c["id"] for c in codes}
    assert len(ids) == len(codes)
    niveaux = {}
    for c in codes:
        niveau = c["annotations"][0]["title"]
        niveaux[niveau] = niveaux.get(niveau, 0) + 1
        if c["id"] != "SN":
            assert c["parent"] in ids, c["id"]
    assert niveaux == {"pays": 1, "region": 14, "departement": 46,
                       "arrondissement": 125, "commune": 552}


def test_structure_complete(api):
    d = api.get("/sdmx/structure").json()["data"]
    assert {f["id"] for f in d["dataflows"]} == {j.flux for j in sources.JEUX.values()}
    dims = d["dataStructures"][0]["dataStructureComponents"]["dimensionList"]
    assert [x["id"] for x in dims["dimensions"]] == ["FREQ", "REF_AREA", "INDICATOR"]
    assert dims["timeDimension"]["id"] == "TIME_PERIOD"


# --- contours, debit ------------------------------------------------------------

def test_geojson_avec_indicateurs(api):
    r = api.get("/geo/arrondissements.geojson")
    assert r.headers["content-type"] == "application/geo+json"
    g = r.json()
    assert len(g["features"]) == 125
    p = g["features"][0]["properties"]
    assert p["code"].startswith("SN") and "indice_risque" in p
    assert g["metadata"]["licence"]["nom"]


def test_debit_borne_par_adresse():
    from fastapi.testclient import TestClient

    from donnees_ouvertes import creer_api
    c = TestClient(creer_api(capacite=2, recharge_par_seconde=0.001))
    assert c.get("/").status_code == 200
    assert c.get("/").status_code == 200
    r = c.get("/")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert r.headers["access-control-allow-origin"] == "*"


# --- codes de zone de l'ANSD (Open Data Platform, scripts 35 et 36) -----------

@pytest.mark.skipif(not sources.CORRESPONDANCE.exists(), reason="table du script 36 absente")
def test_codes_ansd_sdmx_sur_toutes_les_zones(api):
    deps = api.get("/donnees/departements").json()["donnees"]
    assert all(d["code_ansd_sdmx"] for d in deps)
    velingara = next(d for d in deps if d["code"] == "SN0703")
    assert velingara["code_ansd_sdmx"] == "SN-KD-VE"
    communes = api.get("/donnees/communes").json()["donnees"]
    assert all(c["code_ansd_sdmx"] for c in communes)
    km = next(c for c in communes if c["code"] == "SN0105_KEURMASSAR")
    assert km["code_ansd_sdmx"] == "SN-DK-KM2-2+SN-DK-KM3-2"      # decoupee en 2023


@pytest.mark.skipif(not sources.CORRESPONDANCE.exists(), reason="table du script 36 absente")
def test_liste_de_codes_porte_le_code_ansd(api):
    codes = api.get("/sdmx/codelist/CLIMATSEN/CL_ZONE/1.0").json()["data"]["codelists"][0]["codes"]
    kolda = next(c for c in codes if c["id"] == "SN07")
    assert {"type": "CODE_ANSD_SDMX", "title": "SN-KD"} in kolda["annotations"]
    avec = [c for c in codes if any(a["type"] == "CODE_ANSD_SDMX" for a in c["annotations"])]
    assert len(avec) == 14 + 46 + 552
