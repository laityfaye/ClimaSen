"""Visuels a la demande (grammaire bornee) et figures de reference.

Chaque specification valide est reellement calculee ET dessinee (PNG); chaque
specification invalide est refusee avec un message qui dit pourquoi.
"""
import pandas as pd
import pytest

from jarvis import figures
from jarvis.rapports import figures_reference, moteur_figures as M
from jarvis.rapports.document import Figure, Tableau
from jarvis.tools import figures_libres
from jarvis.tools.common import ToolInputError

VALIDES = [
    {"dataset": "departements", "mark": "barres_horizontales", "x": "departement",
     "y": "population_2023", "sort": "desc", "top": 10},
    {"dataset": "departements", "mark": "barres", "group_by": "region",
     "measure": "population_2023", "aggregation": "somme"},
    {"dataset": "departements", "mark": "barres", "group_by": "region",
     "measure": "indice_risque", "aggregation": "mediane"},
    {"dataset": "departements", "mark": "barres_horizontales", "group_by": "region",
     "measure": "comptage"},
    {"dataset": "departements", "mark": "carte", "y": "densite_2023_hab_km2",
     "highlight": ["Pikine"]},
    {"dataset": "arrondissements", "mark": "carte", "y": "jours_50mm_an"},
    {"dataset": "departements", "mark": "nuage", "x": "jours_anomalie_2sigma_an",
     "y": "population_2023", "label": "departement"},
    {"dataset": "arrondissements", "mark": "boites", "group_by": "region",
     "y": "jours_anomalie_2sigma_an",
     "filters": [{"column": "region", "op": "in", "value": ["Kolda", "Tambacounda"]}]},
    {"dataset": "departements", "mark": "tableau",
     "columns": ["departement", "region", "indice_risque", "population_2023"],
     "y": "indice_risque", "sort": "desc", "top": 8},
    {"dataset": "evenements", "mark": "barres", "group_by": "year", "measure": "comptage",
     "filters": [{"column": "max_intensity_region", "op": "=", "value": "Kedougou"}]},
    {"dataset": "evenements", "mark": "courbes", "x": "year", "y": "max_precip",
     "aggregation": "max"},
    {"dataset": "evenements", "mark": "courbes", "x": "year", "y": "coverage_percent",
     "series": "phase", "aggregation": "moyenne"},
    {"dataset": "evenements", "mark": "boites", "group_by": "phase", "y": "max_precip"},
    {"dataset": "evenements", "mark": "barres", "group_by": "month", "measure": "max_precip",
     "aggregation": "mediane", "filters": [{"column": "year", "op": ">=", "value": 2000}]},
    {"dataset": "correlations", "mark": "carte_chaleur", "x": "lag_months", "series": "index",
     "y": "spearman_r", "filters": [{"column": "phase", "op": "=", "value": "Phase_2_pleine"},
                                    {"column": "metric", "op": "=", "value": "n_events"}]},
    {"dataset": "correlations", "mark": "courbes", "x": "lag_months", "y": "pearson_r",
     "series": "index",
     "filters": [{"column": "phase", "op": "=", "value": "Phase_1_debut"},
                 {"column": "metric", "op": "=", "value": "max_precip"},
                 {"column": "index", "op": "in", "value": ["TSA", "ATL3", "AMM"]}]},
    {"dataset": "indices_sst_annuels", "mark": "courbes", "x": "annee", "y": "Nino34"},
    {"dataset": "indices_sst_annuels", "mark": "nuage", "x": "TNA", "y": "TSA",
     "label": "annee"},
    {"dataset": "communes", "mark": "barres_horizontales", "x": "COMMUNE",
     "y": "population_2023", "filters": [{"column": "Departement", "op": "=",
                                          "value": "Pikine"}], "sort": "desc"},
    {"dataset": "departements", "mark": "nuage", "join": {"dataset": "ehcvm_services"},
     "x": "ehcvm_services.acces_electricite_menages_pct", "y": "indice_risque",
     "label": "departement"},
    {"dataset": "communes", "mark": "barres_horizontales", "join": {"dataset": "arrondissements"},
     "group_by": "adm3_name", "measure": "population_2023", "aggregation": "somme",
     "filters": [{"column": "Region", "op": "=", "value": "Dakar"}], "top": 12},
    {"dataset": "ehcvm_pauvrete", "mark": "barres_horizontales", "x": "region",
     "y": "taux_pauvrete_p0_pct", "title": "Pauvreté par région en 2021-2022"},
    # Jeux du 07-09/10/2026 : habitants touches, communes, projections de l'ANSD.
    {"dataset": "habitants_evenements", "mark": "courbes", "x": "annee",
     "y": "population_touchee_2023", "aggregation": "mediane"},
    {"dataset": "habitants_evenements", "mark": "tableau",
     "columns": ["annee", "mois", "population_touchee_2023", "departement_le_plus_touche"],
     "y": "population_touchee_2023", "sort": "desc", "top": 10},
    {"dataset": "communes_exposition", "mark": "barres_horizontales", "x": "commune_ansd",
     "y": "jours_extremes_par_an", "filters": [{"column": "departement", "op": "=",
                                                "value": "Pikine"}], "sort": "desc"},
    {"dataset": "departements", "mark": "tableau", "join": {"dataset": "population_projetee"},
     "columns": ["departement", "population_2023", "population_projetee.population_2030"],
     "y": "population_projetee.population_2030", "sort": "desc", "top": 10},
]


@pytest.mark.parametrize("spec", VALIDES, ids=lambda s: "%s-%s" % (s["dataset"], s["mark"]))
def test_specification_valide_calculee_et_dessinee(spec):
    r = M.executer(spec)
    assert r["titre"] and r["legende"] and r["unite"] and r["periode"] and r["source"]
    if r["genre"] == "tableau":
        assert r["lignes"] and len(r["colonnes"]) == len(spec["columns"])
        return
    png = figures.rendre(r["spec"], "clair", impression=True)
    assert png[:4] == b"\x89PNG"
    figures.en_csv(dict(r["spec"], titre="t"))


INVALIDES = [
    ({"dataset": "secret", "mark": "barres"}, "dataset inconnu"),
    ({"dataset": "departements", "mark": "camembert"}, "mark inconnu"),
    ({"dataset": "departements", "mark": "barres", "group_by": "region",
      "measure": "indice_risque", "aggregation": "moyenne"}, "moyenne de rangs"),
    ({"dataset": "departements", "mark": "barres", "group_by": "region",
      "measure": "densite_2023_hab_km2", "aggregation": "somme"}, "additionne pas des taux"),
    ({"dataset": "evenements", "mark": "barres", "group_by": "phase",
      "measure": "max_precip", "aggregation": "somme"}, "intensites"),
    ({"dataset": "departements", "mark": "barres", "x": "departement", "y": "mot_de_passe"},
     "Colonne inconnue"),
    ({"dataset": "evenements", "mark": "carte", "y": "max_precip"}, "Carte impossible"),
    ({"dataset": "departements", "mark": "carte_chaleur", "x": "region", "series": "departement",
      "y": "indice_risque"}, "reservee aux correlations"),
    ({"dataset": "departements", "mark": "nuage", "x": "jours_50mm_an", "y": "indice_risque",
      "filters": [{"column": "region", "op": "=", "value": "Dakar"}]}, "au moins 10"),
    ({"dataset": "departements", "mark": "boites", "group_by": "region",
      "y": "jours_50mm_an", "filters": [{"column": "region", "op": "in",
                                         "value": ["Kolda", "Dakar"]}]}, "moins de 5"),
    ({"dataset": "departements", "mark": "boites", "group_by": "departement",
      "y": "jours_50mm_an"}, "12 au plus"),
    ({"dataset": "departements", "mark": "barres", "x": "departement", "y": "population_2023",
      "title": "Pikine compte 999 999 habitants"}, "aucun chiffre"),
    ({"dataset": "departements", "mark": "barres", "x": "region", "y": "population_2023"},
     "Plusieurs lignes"),
    ({"dataset": "evenements", "mark": "barres", "join": {"dataset": "ehcvm_services"},
      "x": "phase", "y": "max_precip"}, "non autorisee"),
    ({"dataset": "departements", "mark": "barres", "x": "departement", "y": "population_2023",
      "filters": [{"column": "region", "op": "=", "value": "Atlantide"}]}, "Aucune ligne"),
    ({"dataset": "departements", "mark": "barres", "x": "departement", "y": "population_2023",
      "filters": [{"column": "region", "op": ">", "value": 3}]}, "Comparaison"),
    ({"dataset": "correlations", "mark": "carte_chaleur", "x": "lag_months", "series": "index",
      "y": "pearson_r"}, "Plusieurs valeurs par case"),
    ({"dataset": "correlations", "mark": "barres", "group_by": "index",
      "measure": "pearson_p_neff", "aggregation": "moyenne"}, "p-values"),
]


@pytest.mark.parametrize("spec, message", INVALIDES, ids=[m for _, m in INVALIDES])
def test_specification_invalide_refusee_avec_la_raison(spec, message):
    with pytest.raises(M.SpecInvalide) as exc:
        M.executer(spec)
    assert message.lower() in str(exc.value).lower()


def test_valeurs_egales_aux_donnees():
    r = M.executer({"dataset": "departements", "mark": "barres", "group_by": "region",
                    "measure": "population_2023", "aggregation": "somme"})
    dep = pd.read_csv("outputs/vulnerabilite/indice_risque_departements.csv")
    attendu = dep.groupby("region")["population_2023"].sum()
    d = r["spec"]["donnees"]
    for cat, val in zip(d["categories"], d["valeurs"]):
        assert val == pytest.approx(attendu[cat])
    assert d["valeurs"] == sorted(d["valeurs"], reverse=True)


def test_jointure_affiche_son_taux_d_appariement():
    r = M.executer(VALIDES[19])
    assert r["resume"]["appariement"]["taux"] == 1.0
    assert "appariées" in r["legende"]


def test_donnee_provisoire_signalee():
    r = M.executer({"dataset": "departements", "mark": "carte", "y": "V_vulnerabilite"})
    assert "provisoire" in r["legende"]


def test_nuage_porte_sa_reserve():
    r = M.executer(VALIDES[6])
    assert "non corrigée" in r["legende"] and r["statut"] == "correle"
    assert -1 <= r["resume"]["pearson_r"] <= 1


def test_periode_suit_le_filtre_d_annees():
    r = M.executer(VALIDES[13])
    assert r["periode"] == "2000-2023"


def test_pour_rapport():
    bloc, resume = M.pour_rapport(VALIDES[0])
    assert isinstance(bloc, Figure) and bloc.origine == "a_la_demande"
    bloc, _ = M.pour_rapport(VALIDES[8])
    assert isinstance(bloc, Tableau)


# --- outil make_custom_figure --------------------------------------------------------
def test_outil_depose_une_figure():
    store = figures.FigureStore()
    r = figures_libres.run(VALIDES[0], {}, figures=store, session_id="s")
    assert store.obtenir("s", r["figure_id"]) is not None
    assert r["resume"]["lignes_retenues"] == 46


def test_outil_tableau_sans_figure():
    r = figures_libres.run(VALIDES[8], {}, figures=None, session_id="s")
    assert "tableau" in r and len(r["tableau"]["lignes"]) == 8


def test_outil_refus_devient_erreur_lisible():
    with pytest.raises(ToolInputError) as exc:
        figures_libres.run(INVALIDES[2][0], {}, figures=figures.FigureStore(), session_id="s")
    assert "rangs" in str(exc.value)


# --- figures de reference ----------------------------------------------------------
def test_figures_de_reference_toutes_disponibles():
    ids = {e["id"] for e in figures_reference.disponibles()}
    assert ids == set(figures_reference._entrees())
    assert {e["id"] for e in figures_reference.disponibles("vulnerabilite")} >= {
        "validation_inondations", "sensibilite_departements"}


def test_figure_de_reference_complete():
    f = figures_reference.figure("synthese_correlations")
    assert f.origine == "reference" and f.png[:4] == b"\x89PNG"
    with pytest.raises(KeyError):
        figures_reference.figure("inconnue")


def test_habitants_par_evenement_egaux_au_script_33():
    r = M.executer({"dataset": "habitants_evenements", "mark": "tableau",
                    "columns": ["annee", "population_touchee_2023"],
                    "y": "population_touchee_2023", "sort": "desc", "top": 1})
    attendu = pd.read_csv("outputs/exposition_evenements/population_touchee_evenements.csv")
    assert r["lignes"][0][0] in (2012, "2012")
    assert str(int(attendu["population_touchee_2023"].max())) in         str(r["lignes"][0][1]).replace(" ", "").replace(" ", "").replace(" ", "")


def test_habitants_ne_s_additionnent_pas_entre_evenements():
    """Une meme personne compte une fois par evenement : la somme serait trompeuse."""
    with pytest.raises(M.SpecInvalide):
        M.executer({"dataset": "habitants_evenements", "mark": "barres", "group_by": "annee",
                    "measure": "population_touchee_2023", "aggregation": "somme"})
