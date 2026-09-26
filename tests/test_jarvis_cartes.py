"""Cartes de Jarvis (outil show_map, rendu, ecran du widget).

Donnees reelles de la plateforme: les cartes lisent les memes fichiers que
le dashboard et le script 01. Les tests verifient d'abord que ce qui est
trace concorde avec le catalogue des evenements.
"""
import asyncio
import json

import numpy as np
import pytest

from jarvis import cartes, figures
from jarvis.tools import cartes as outil
from jarvis.tools import dataset, registry
from jarvis.widget_html import WIDGET_FILE

SOURCE = WIDGET_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def data():
    return {"events": dataset.get("events")}


def _executer(params, store=None):
    store = store or figures.FigureStore()
    r = asyncio.run(registry.execute("show_map", params, "public",
                                     contexte={"figures": store, "session_id": "s1"}))
    return r, store


# --- donnees ---------------------------------------------------------------------
def test_la_grille_reconstruit_exactement_le_catalogue(data):
    """Pluie = anomalie x ecart-type + climatologie: egale au catalogue."""
    for _, ev in data["events"].sample(25, random_state=1).iterrows():
        an, pluie = cartes.jour(ev["date"].strftime("%Y-%m-%d"))
        assert np.nanmax(pluie) == pytest.approx(ev["max_precip"], abs=0.01)
        assert np.nanmax(an) == pytest.approx(ev["max_anomaly"], abs=0.001)


def test_le_fond_de_carte_est_embarque():
    f = cartes.fond()
    assert f["version"] == 1 and len(f["terres"]) > 50
    assert f["ocean_ouest_afrique"]


# --- outil ------------------------------------------------------------------------
def test_carte_d_un_evenement(data):
    spec, resume = outil.construire({"type": "evenement", "date": "2012-09-28",
                                     "variable": "anomalie"}, data)
    assert spec["genre"] == "carte_senegal"
    assert resume["catalogue"]["anomalie_max_sigma"] == 8.14
    assert resume["maximum_sur_la_carte"]["valeur"] == pytest.approx(8.14, abs=0.01)
    assert spec["donnees"]["seuil"] == 2.0          # contour a 2 sigma


def test_date_sans_evenement_propose_les_plus_proches(data):
    from jarvis.tools.common import ToolInputError
    with pytest.raises(ToolInputError, match="plus proches"):
        outil.construire({"type": "evenement", "date": "2012-01-15"}, data)


def test_motif_sst_resume_les_boites(data):
    spec, resume = outil.construire({"type": "sst_cluster", "phase": "Phase_2_pleine",
                                     "cluster": 2}, data)
    assert spec["genre"] == "carte_sst"
    assert "grille" not in json.dumps(spec)          # la grille n'est pas stockee
    assert set(resume["anomalie_moyenne_par_boite_degC"]) >= {"Nino34", "TNA", "AMO"}
    assert "pas une zone" in resume["rappel"]


def test_cluster_inconnu_liste_les_clusters_valides(data):
    from jarvis.tools.common import ToolInputError
    with pytest.raises(ToolInputError, match=r"\[0, 1, 2"):
        outil.construire({"type": "sst_cluster", "phase": "Phase_2_pleine",
                          "cluster": 42}, data)


def test_composite_de_cluster_porte_sur_tous_ses_evenements(data):
    affect = cartes.evenements_par_cluster("Phase_2_pleine")
    n = int((affect["cluster"] == 2).sum())
    _, resume = outil.construire({"type": "cluster_senegal", "phase": "Phase_2_pleine",
                                  "cluster": 2}, data)
    assert resume["n_evenements"] == n > 4


def test_frequence_des_extremes_en_pourcentage(data):
    spec, resume = outil.construire({"type": "frequence_extremes",
                                     "phase": "Phase_2_pleine"}, data)
    assert 0 < resume["part_moyenne_pct"] < 100
    assert spec["donnees"]["seuil"] is None          # des %, pas des sigma


def test_show_map_depose_une_carte_annoncee_au_widget():
    r, store = _executer({"type": "evenement", "date": "2012-09-28"})
    assert not r["is_error"]
    charge = json.loads(r["content"])
    assert charge["carte"] is True
    fig = store.obtenir("s1", charge["figure_id"])
    assert fig.vue_publique()["carte"] is True


def test_executeur_annonce_la_carte_avec_son_drapeau():
    from jarvis.app import _noter_figure
    produites = []
    _noter_figure({"content": json.dumps({"figure_id": "abc", "titre": "t",
                                          "carte": True})}, produites)
    assert produites[0]["carte"] is True


# --- rendu ------------------------------------------------------------------------
@pytest.mark.parametrize("params", [
    {"type": "sst_cluster", "phase": "Phase_2_pleine", "cluster": 2},
    {"type": "evenement", "date": "2012-09-28"},
    {"type": "frequence_extremes"},
])
@pytest.mark.parametrize("theme", ["hud", "clair"])
def test_rendu_png_et_csv(params, theme):
    r, store = _executer(params)
    fig = store.obtenir("s1", json.loads(r["content"])["figure_id"])
    png = figures.rendre(fig.spec, theme)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 50_000
    assert figures.en_csv(fig.spec).startswith("latitude,longitude,")


# --- ecran du widget ---------------------------------------------------------------
def test_la_carte_s_affiche_des_son_arrivee_dans_le_hud():
    figure = SOURCE[SOURCE.index('} else if(name === "figure"){'):]
    figure = figure[:figure.index('} else if(name === "tool"){')]
    assert "if(data.carte && Hud.actif()){ Ecran.afficher(data); }" in figure


def test_ecran_se_ferme_avec_echap_et_a_la_sortie():
    assert "else if(Ecran.ouvert()){ Ecran.fermer(); }" in SOURCE
    sortir = SOURCE[SOURCE.index("function sortir(){"):]
    assert "Ecran.fermer();" in sortir[:300]


def test_ecran_n_affiche_que_du_texte_et_nos_images():
    ecran = SOURCE[SOURCE.index("var Ecran = (function(){"):]
    ecran = ecran[:ecran.index("})();")]
    assert "innerHTML = \"\"" in ecran and ".innerHTML = ref" not in ecran
    assert "textContent = ref.titre" in ecran
