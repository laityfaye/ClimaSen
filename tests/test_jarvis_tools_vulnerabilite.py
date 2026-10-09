"""Outil get_priority_zones, page Vulnerabilite et leur cablage avec Jarvis.

Les tests de l'outil tournent sur un petit jeu synthetique (aucun acces disque) ;
un dernier test verifie sur les vraies sorties que l'outil rend les memes chiffres
que le CSV lu par la page.
"""
import pandas as pd
import pytest

from jarvis.tools import vulnerabilite
from jarvis.tools.common import ToolInputError

COLONNES = dict(
    jours_anomalie_2sigma_an=1.0, jours_50mm_an=0.5, population_2013=1000,
    superficie_km2=100.0, densite_2023_hab_km2=12.0, croissance_2013_2023_pct=20.0,
    pauvres_estimes_2023=300.0, methode_alea="pixels dans le contour",
)


def _dep():
    lignes = [
        # rang, pcode, nom, region, A, E, V, indice, pop, pauvrete
        (1, "SN0703", "Velingara", "Kolda", 0.9, 0.6, 0.9, 0.78, 405149, 62.5),
        (2, "SN1204", "Tambacounda", "Tambacounda", 0.9, 0.5, 0.8, 0.72, 427419, 62.8),
        (36, "SN0103", "Pikine", "Dakar", 0.4, 0.9, 0.1, 0.29, 763377, 9.3),
        (43, "SN0101", "Dakar", "Dakar", 0.4, 1.0, 0.02, 0.20, 1278469, 9.3),
    ]
    t = pd.DataFrame([dict(rang=r, pcode=p, departement=n, region=g, A_alea=a,
                           E_exposition=e, V_vulnerabilite=v, indice_risque=i,
                           population_2023=pop, taux_pauvrete_region_pct=pv, **COLONNES)
                      for r, p, n, g, a, e, v, i, pop, pv in lignes])
    return t


def _arr():
    return pd.DataFrame([dict(
        rang=1, pcode="SN070301", arrondissement="Bonconto", departement="Velingara",
        region="Kolda", A_alea=0.9, E_exposition=0.58, V_vulnerabilite=0.94,
        indice_risque=0.79, population_2023=165314, taux_pauvrete_region_pct=62.5,
        indice_departement=0.78, rang_departement=1, **COLONNES)])


def _data(arr=True, **facultatifs):
    # Jeux facultatifs (API SDMX de l'ANSD, communes) absents par defaut :
    # aucun acces disque.
    d = {"vulnerabilite": {"departements": _dep(), "arrondissements": _arr() if arr else None,
                           "resume": {}, "resume_arrondissements": None},
         "population_projetee": None, "pauvrete_ansd": None, "communes": None}
    d.update(facultatifs)
    return d


def test_classement_par_defaut_par_indice():
    r = vulnerabilite.run({}, _data())
    assert [z["nom"] for z in r["zones"]] == ["Velingara", "Tambacounda", "Pikine", "Dakar"]
    assert r["zones"][0]["indice_risque"] == 0.78
    # Classement : lignes courtes ; les chiffres bruts sont dans la fiche (zone=).
    assert r["zones"][0]["population_2023"] == 405149
    assert "chiffres_bruts" not in r["zones"][0]
    assert "provisoire" in r["statut_vulnerabilite"]
    assert "probabilite" in r["regle_interpretation"]
    for source in ("CHIRPS", "RGPH-5", "EHCVM", "OCHA"):
        assert source in r["sources"]
    assert "donnees_absentes" in r


def test_cinq_zones_par_defaut():
    t = pd.concat([_dep()] * 2, ignore_index=True)
    t["rang"] = range(1, len(t) + 1)
    r = vulnerabilite.run({}, {"vulnerabilite": {"departements": t, "arrondissements": None}})
    assert len(r["zones"]) == 5


def test_classement_par_composante_et_top():
    r = vulnerabilite.run({"component": "exposition", "top": 2}, _data())
    assert [z["nom"] for z in r["zones"]] == ["Dakar", "Pikine"]
    assert r["classe_par"] == "exposition"


def test_composante_dominante():
    z = vulnerabilite.run({"zone": "Pikine"}, _data())["zones"][0]
    assert z["rang_indice"] == 36 and z["sur"] == 4
    assert z["composante_dominante"].startswith("exposition")
    assert z["composante_la_plus_faible"].startswith("vulnerabilite")


def test_zone_sans_accent_et_casse():
    z = vulnerabilite.run({"zone": "pikine"}, _data())["zones"]
    assert len(z) == 1 and z[0]["pcode"] == "SN0103"


def test_filtre_region_garde_les_rangs_nationaux():
    r = vulnerabilite.run({"region": "dakar"}, _data())
    assert [z["rang_indice"] for z in r["zones"]] == [36, 43]
    assert r["region"] == "Dakar"
    assert r["repere_pauvrete_la_plus_basse"]["taux_pauvrete_region_pct"] == 9.3


def test_arrondissements():
    r = vulnerabilite.run({"level": "arrondissement"}, _data())
    z = r["zones"][0]
    assert r["niveau"] == "arrondissements"
    assert z["nom"] == "Bonconto" and z["departement"] == "Velingara"
    # Le rang du departement est dans la fiche complete, pas dans le classement.
    fiche = vulnerabilite.run({"level": "arrondissements", "zone": "Bonconto"},
                              _data())["zones"][0]
    assert fiche["rang_du_departement_sur_46"] == 1


def test_arrondissements_absents():
    with pytest.raises(ToolInputError, match="departements"):
        vulnerabilite.run({"level": "arrondissements"}, _data(arr=False))


@pytest.mark.parametrize("params", [{"level": "communes"}, {"component": "pluie"},
                                    {"top": 50}, {"zone": "Paris"}, {"region": "Bretagne"}])
def test_parametres_invalides(params):
    with pytest.raises(ToolInputError):
        vulnerabilite.run(params, _data())


# --- cablage page / navigation / contexte -----------------------------------
def test_page_context_accepte_les_filtres_vulnerabilite():
    from jarvis import page_context
    propre = page_context.nettoyer({"page": "Vulnerabilite", "filtres": {
        "niveau": "arrondissements", "composante": "alea", "zone": "SN070301"}})
    assert propre["filtres"] == {"niveau": "arrondissements", "composante": "alea",
                                 "zone": "SN070301"}


@pytest.mark.parametrize("zone", ["Pikine", "SN07", "SN0703<script>", "SN07030101", 703])
def test_page_context_refuse_une_zone_qui_n_est_pas_un_pcode(zone):
    from jarvis import page_context
    propre = page_context.nettoyer({"page": "Vulnerabilite", "filtres": {"zone": zone}})
    assert "zone" not in propre["filtres"]


def test_widget_transmet_les_filtres_de_la_page():
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).resolve().parent.parent / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import jarvis_widget
    ctx = jarvis_widget.contexte_page({"nav_page": "Vulnerabilite", "vul_niveau": "departements",
                                       "vul_composante": "indice", "vul_zone": "SN0703"})
    assert ctx == {"page": "Vulnerabilite", "filtres": {
        "niveau": "departements", "composante": "indice", "zone": "SN0703"}}
    nav = jarvis_widget.lire_navigation(
        '{"page": "Vulnerabilite", "filtres": {"niveau": "arrondissements"}}')
    assert nav == {"page": "Vulnerabilite", "filtres": {"vul_niveau": "arrondissements"}}


# --- sur les vraies sorties --------------------------------------------------
def test_l_outil_rend_les_chiffres_du_csv():
    from jarvis.tools import dataset
    try:
        donnees = {"vulnerabilite": dataset.get("vulnerabilite")}
    except dataset.DataUnavailableError:
        pytest.skip("scripts 26/27 non lances")
    csv = donnees["vulnerabilite"]["departements"].sort_values("rang")
    r = vulnerabilite.run({"top": 3}, donnees)
    assert [z["pcode"] for z in r["zones"]] == list(csv["pcode"].head(3))
    for z, (_, ligne) in zip(r["zones"], csv.head(3).iterrows()):
        assert z["indice_risque"] == round(float(ligne["indice_risque"]), 3)
        assert z["population_2023"] == int(ligne["population_2023"])


def _vraies_donnees():
    from jarvis.tools import dataset
    try:
        return {"vulnerabilite": dataset.get("vulnerabilite")}
    except dataset.DataUnavailableError:
        pytest.skip("scripts 26/27 non lances")


def test_fiabilite_lue_dans_le_script_29():
    import json
    from pathlib import Path
    donnees = _vraies_donnees()
    chemin = (Path(__file__).resolve().parent.parent / "outputs" / "vulnerabilite"
              / "robustesse" / "resume.json")
    if not chemin.exists():
        pytest.skip("script 29 non lance")
    attendu = json.loads(chemin.read_text(encoding="utf-8"))
    f = vulnerabilite.run({}, donnees)["fiabilite"]
    val = f["validation_inondations_documentees"]
    assert val["auc_departements_touches_au_moins_une_fois"] == (
        attendu["validation"]["indice_publie"]["au moins une (A)"]["auc"])
    assert set(val["auc_par_composante"]) == {"exposition_seule", "alea_seul",
                                             "vulnerabilite_seule"}
    sens = next(x for x in attendu["sensibilite"] if x["niveau"] == "departements")
    assert f["sensibilite_aux_poids"]["zones_du_top10_communes_a_toutes_les_variantes"] == (
        sens["top10_communs"])


def test_fiche_porte_les_indicateurs_ehcvm_de_la_region():
    r = vulnerabilite.run({"zone": "Pikine"}, _vraies_donnees())
    indic = r.get("indicateurs_region_ehcvm")
    if indic is None:
        pytest.skip("transcriptions EHCVM absentes")
    assert "region" in indic["echelle"]
    assert indic["wc_chasse_eau_pct"] == 89.9   # Tableau VII-11, DAKAR


@pytest.mark.parametrize("params", [{"top": 10}, {"level": "arrondissements", "top": 10},
                                    {"zone": "Pikine"}, {"region": "Dakar"}])
def test_la_reponse_tient_sous_le_plafond(params):
    import json
    from jarvis.tools.registry import MAX_RESULT_CHARS
    r = vulnerabilite.run(params, _vraies_donnees())
    assert len(json.dumps(r, ensure_ascii=False, default=str)) <= MAX_RESULT_CHARS


# --- carte show_map type vulnerabilite (sur les vraies sorties) ---------------
def _carte(params):
    import asyncio
    import json
    from jarvis import figures
    from jarvis.tools import registry
    store = figures.FigureStore()
    r = asyncio.run(registry.execute("show_map", dict(params, type="vulnerabilite"), "public",
                                     contexte={"figures": store, "session_id": "s1"}))
    return r, store, (None if r["is_error"] else json.loads(r["content"]))


@pytest.mark.parametrize("params,n,theme", [({}, 46, "clair"),
                                            ({"level": "arrondissements"}, 125, "hud"),
                                            ({"component": "exposition"}, 46, "sombre")])
def test_carte_vulnerabilite_rendue(params, n, theme):
    from jarvis import figures
    _vraies_donnees()
    r, store, c = _carte(params)
    assert not r["is_error"], r["content"]
    assert c["carte"] and c["resume"]["nombre_de_zones"] == n
    fig = store.obtenir("s1", c["figure_id"])
    assert fig.spec["genre"] == "carte_zones"
    assert figures.rendre(fig.spec, theme)[:4] == b"\x89PNG"
    assert figures.en_csv(fig.spec).count("\n") == n + 1     # entete + une ligne par zone


def test_carte_vulnerabilite_memes_chiffres_que_l_outil():
    donnees = _vraies_donnees()
    _, _, c = _carte({})
    attendu = vulnerabilite.run({}, donnees)["zones"]
    assert [z["nom"] for z in c["resume"]["cinq_plus_fortes"]] == [z["nom"] for z in attendu]
    assert c["resume"]["fiabilite"] == vulnerabilite.run({}, donnees)["fiabilite"]


def test_carte_vulnerabilite_zone_mise_en_evidence():
    _vraies_donnees()
    _, store, c = _carte({"zone": "Pikine"})
    evid = c["resume"]["zones_mises_en_evidence"]
    assert [z["nom"] for z in evid] == ["Pikine"]
    fig = store.obtenir("s1", c["figure_id"])
    assert fig.spec["donnees"]["surligne"] == ["SN0103"]
    r, _, _ = _carte({"zone": "Paris"})
    assert r["is_error"]


# --- complements de l'API SDMX de l'ANSD et communes (scripts 34-37) ----------
def _projection():
    return pd.DataFrame({"code": ["SN0103", "SN0103_MBAO"],
                         "population_2023": [763377, 149456],
                         "population_2026": [808816, 158099],
                         "population_2030": [869693, 170000]}).set_index("code")


def _communes():
    def f(nom, pop, jours, pcode="SN0103"):
        return {"properties": {"commune_ansd": nom, "adm2_pcode": pcode,
                               "population_2023": pop, "densite_hab_km2": 8639.0,
                               "jours_extremes_par_an": jours}}
    return {"features": [f("THIAROYE SUR MER", 61079, 6.05), f("MBAO", 149456, 6.04),
                         f("NGOR", 17706, 6.04, pcode="SN0101")]}


def test_fiche_sans_complements_reste_celle_de_l_indice():
    assert "complements_ansd" not in vulnerabilite.run({"zone": "Pikine"}, _data())


def test_fiche_porte_projection_pauvrete_et_communes():
    pauv = {"SN01": {"taux": 9.3, "profondeur": 1.1, "severite": 0.3,
                     "taux_2011": 26.1, "taux_2019": 9.0}}
    r = vulnerabilite.run({"zone": "Pikine"}, _data(
        population_projetee=_projection(), pauvrete_ansd=pauv, communes=_communes()))
    c = r["complements_ansd"]
    assert c["population_projetee"] == {"2023": 763377, "2026": 808816, "2030": 869693}
    assert c["pauvrete_region"]["profondeur_P1_2022_pct"] == 1.1
    assert c["pauvrete_region"]["taux_P0_2011_pct"] == 26.1
    noms = [x["commune"] for x in c["communes"]["par_population_decroissante"]]
    assert noms == ["Mbao", "Thiaroye Sur Mer"]                # Ngor : autre departement
    assert c["communes"]["par_population_decroissante"][0]["population_2026"] == 158099
    assert "APPROXIMATIFS" in c["communes"]["lecture"]
    assert "PAS dans l'indice" in c["statut"]


def test_arrondissement_renvoie_vers_les_communes_du_departement():
    pauv = {"SN07": {"taux": 62.5, "profondeur": 20.0, "severite": 9.0}}
    r = vulnerabilite.run({"zone": "Bonconto", "level": "arrondissements"},
                          _data(pauvrete_ansd=pauv))
    c = r["complements_ansd"]
    assert "population_projetee" not in c                       # departements seulement
    assert "Velingara" in c["communes"]


def test_vraies_communes_de_pikine():
    d = _vraies_donnees()
    c = vulnerabilite.run({"zone": "Pikine"}, d).get("complements_ansd")
    if not c or "communes" not in c:
        pytest.skip("scripts 34-37 non lances")
    assert c["communes"]["nombre"] >= 10
    assert c["pauvrete_region"]["taux_P0_2022_pct"] == 9.3
