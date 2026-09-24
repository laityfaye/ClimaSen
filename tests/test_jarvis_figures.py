"""Figures (Phase 8): magasin, rendu, vue CSV, outil make_figure, API.

Le rendu est reellement execute (matplotlib, backend Agg): un PNG valide
est la seule preuve qu'une specification se dessine.
"""
import json
import time

import pytest

from conftest import FakeClaude, sse_events
from jarvis import figures
from jarvis.tools import graphiques
from jarvis.tools import registry
from jarvis.tools.common import ToolInputError

PNG = b"\x89PNG\r\n\x1a\n"
CHAT = "/jarvis/api/chat"
SYNC = "/jarvis/api/chat/sync"


def auth(token):
    return {"X-Jarvis-Session": token}


SPEC_COURBES = {
    "genre": "courbes", "type": "correlation_lags", "titre": "T", "sous_titre": "S",
    "donnees": {"x": [0, 1, 2], "x_categoriel": True, "x_label": "lag",
                "y_label": "r", "ligne_zero": True,
                "series": [{"nom": "AMO", "y": [-0.1, -0.3, None],
                            "marqueurs_pleins": [False, True, False]},
                           {"nom": "TNA", "y": [0.2, 0.1, 0.0]}]},
}
SPEC_BARRES = {
    "genre": "barres", "type": "events_per_year", "titre": "T", "sous_titre": "S",
    "donnees": {"categories": [2000, 2001, 2002], "valeurs": [3, 0, 5],
                "x_label": "annee", "y_label": "n",
                "tendance": {"nom": "tendance", "y": [2.0, 3.0, 4.0]}},
}
SPEC_CARTE = {
    "genre": "carte_chaleur", "type": "correlation_heatmap", "titre": "T",
    "sous_titre": "S", "hauteur_pouces": 3.0,
    "donnees": {"lignes": ["AMO", "TNA"], "colonnes": [0, 1],
                "valeurs": [[-0.4, None], [0.2, 0.1]],
                "etoiles": [["**", ""], ["", ""]], "vmax": 0.6,
                "titre_lignes": "indice", "titre_colonnes": "lag"},
}


# --- magasin ------------------------------------------------------------------------
def test_une_figure_n_est_lisible_que_par_sa_session():
    store = figures.FigureStore()
    fig = store.deposer("session-a", SPEC_BARRES)
    assert store.obtenir("session-a", fig.id) is fig
    assert store.obtenir("session-b", fig.id) is None
    assert store.obtenir("session-a", "inconnu") is None


def test_identifiants_imprevisibles():
    store = figures.FigureStore()
    ids = {store.deposer("s", SPEC_BARRES).id for _ in range(50)}
    assert len(ids) == 50
    assert all(len(i) == 24 and i.isalnum() for i in ids)


def test_expiration(monkeypatch):
    store = figures.FigureStore(ttl_seconds=10)
    fig = store.deposer("s", SPEC_BARRES)
    maintenant = time.time()
    monkeypatch.setattr(figures.time, "time", lambda: maintenant + 11)
    assert store.obtenir("s", fig.id) is None
    assert store.taille() == 0


def test_plafond_par_session_oublie_la_plus_ancienne():
    store = figures.FigureStore(max_par_session=3)
    premieres = [store.deposer("s", SPEC_BARRES) for _ in range(3)]
    store.deposer("s", SPEC_BARRES)
    assert store.obtenir("s", premieres[0].id) is None
    assert store.obtenir("s", premieres[1].id) is not None
    autre = store.deposer("t", SPEC_BARRES)
    assert store.obtenir("t", autre.id) is not None


def test_plafond_global():
    store = figures.FigureStore(maximum=5)
    for i in range(12):
        store.deposer("s%d" % i, SPEC_BARRES)
    assert store.taille() == 5


# --- rendu et CSV ------------------------------------------------------------------
@pytest.mark.parametrize("spec", [SPEC_COURBES, SPEC_BARRES, SPEC_CARTE],
                         ids=["courbes", "barres", "carte"])
@pytest.mark.parametrize("theme", figures.THEMES)
def test_chaque_genre_se_dessine_dans_chaque_theme(spec, theme):
    png = figures.rendre(spec, theme)
    assert png.startswith(PNG)
    assert len(png) > 5000


def test_theme_inconnu_retombe_sur_clair():
    assert figures.rendre(SPEC_BARRES, "fuchsia") == figures.rendre(SPEC_BARRES, "clair")


def test_rendu_mis_en_cache_par_theme():
    store = figures.FigureStore()
    fig = store.deposer("s", SPEC_BARRES)
    clair = figures.rendu_en_cache(fig, "clair")
    assert figures.rendu_en_cache(fig, "clair") is clair
    assert figures.rendu_en_cache(fig, "sombre") != clair


def test_rendus_simultanes():
    """Les outils tournent dans des threads: le rendu doit y survivre."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        pngs = list(pool.map(lambda _: figures.rendre(SPEC_COURBES, "clair"), range(8)))
    assert all(p.startswith(PNG) for p in pngs)


def test_csv_courbes():
    lignes = figures.en_csv(SPEC_COURBES).splitlines()
    assert lignes[0] == "lag,AMO,TNA"
    assert lignes[1] == "0,-0.1,0.2"
    assert lignes[3] == "2,,0.0"


def test_csv_barres_avec_tendance():
    lignes = figures.en_csv(SPEC_BARRES).splitlines()
    assert lignes[0] == "annee,n,tendance"
    assert lignes[2] == "2001,0,3.0"


def test_csv_carte():
    lignes = figures.en_csv(SPEC_CARTE).splitlines()
    assert lignes == ["indice,0,1", "AMO,-0.4,", "TNA,0.2,0.1"]


# --- outil make_figure ------------------------------------------------------------
@pytest.mark.parametrize("params", [
    {"type": "correlation_heatmap", "phase": "pleine"},
    {"type": "correlation_lags", "phase": "Phase_2_pleine", "indices": ["Nino34", "IOD"]},
    {"type": "sst_series", "indices": ["Nino34", "TNA"]},
    {"type": "sst_series", "indices": ["IOD"], "aggregation": "mensuelle"},
    {"type": "events_per_year"},
    {"type": "events_by_month", "phase": "pleine"},
    {"type": "events_by_region"},
    {"type": "cluster_profile", "phase": "pleine", "metric": "max_precip"},
    {"type": "cluster_profile", "phase": "toutes"},
], ids=lambda p: p["type"])
def test_chaque_type_produit_une_specification_dessinable(donnees_outils, params):
    spec, resume = graphiques.construire(params, donnees_outils)
    assert spec["type"] == params["type"]
    assert spec["titre"] and spec["source"]
    assert resume
    assert figures.rendre(spec, "clair").startswith(PNG)
    figures.en_csv(spec)
    json.dumps(resume)


def test_heatmap_resume_et_etoiles(donnees_outils):
    spec, resume = graphiques.construire(
        {"type": "correlation_heatmap", "phase": "pleine"}, donnees_outils)
    assert spec["donnees"]["lignes"] == ["Nino34", "IOD"]
    assert spec["donnees"]["etoiles"][0][0] == "**"      # p_neff 0.004
    assert resume["correlation_la_plus_forte"]["indice"] == "Nino34"


def test_evenements_par_an_comptent_les_annees_vides(donnees_outils):
    spec, resume = graphiques.construire({"type": "events_per_year"}, donnees_outils)
    d = spec["donnees"]
    assert d["categories"][0] == 2001 and d["categories"][-1] == 2012
    assert d["valeurs"][d["categories"].index(2003)] == 0
    assert resume["n_evenements"] == 4


@pytest.mark.parametrize("params, message", [
    ({}, "type est requis"),
    ({"type": "camembert"}, "Valeurs acceptees"),
    ({"type": "correlation_heatmap"}, "phase est requis"),
    ({"type": "correlation_lags", "phase": "pleine"}, "indices est requis"),
    ({"type": "sst_series", "indices": ["AMO", "TNA", "IOD", "Nino3", "Nino4"]},
     "4 indices au plus"),
    ({"type": "sst_series", "indices": ["AMO"]}, "absents"),
    ({"type": "correlation_heatmap", "phase": "debut"}, "Aucune donnee"),
])
def test_parametres_invalides(donnees_outils, params, message):
    with pytest.raises(ToolInputError, match=message):
        graphiques.construire(params, donnees_outils)


def test_run_depose_dans_le_magasin_de_la_session(donnees_outils):
    store = figures.FigureStore()
    res = graphiques.run({"type": "events_by_month"}, donnees_outils,
                         figures=store, session_id="s1")
    assert res["affichee"] is True
    assert store.obtenir("s1", res["figure_id"]) is not None
    assert store.obtenir("s2", res["figure_id"]) is None
    assert "resume" in res and "consigne" in res


def test_run_sans_magasin_refuse(donnees_outils):
    with pytest.raises(ToolInputError, match="pas disponible"):
        graphiques.run({"type": "events_by_month"}, donnees_outils)


def test_make_figure_est_public():
    from jarvis import tools
    assert "make_figure" in {s["name"] for s in tools.specs_for("public")}


# --- de bout en bout par l'API ------------------------------------------------------
@pytest.fixture
def donnees_injectees(monkeypatch, donnees_outils):
    async def _charger(noms):
        return {nom: donnees_outils[nom] for nom in noms}
    monkeypatch.setattr(registry, "charger_donnees", _charger)


@pytest.fixture
def figure_client(client, donnees_injectees):
    client.app.state.ctx.claude = FakeClaude(
        reply="Voici la figure.",
        tool_calls=[("make_figure", {"type": "events_per_year"})])
    client.fake = client.app.state.ctx.claude
    return client


def _figure_du_flux(r):
    evenements = sse_events(r.text)
    return [d for n, d in evenements if n == "figure"], evenements


def test_flux_annonce_la_figure(figure_client, token):
    r = figure_client.post(CHAT, json={"message": "Montre-moi"}, headers=auth(token))
    figs, evenements = _figure_du_flux(r)
    assert len(figs) == 1
    assert figs[0]["titre"].startswith("Événements")
    noms = [n for n, _ in evenements]
    assert noms.index("figure") < noms.index("done")


def test_image_servie_a_sa_session_seulement(figure_client, token):
    r = figure_client.post(CHAT, json={"message": "Montre-moi"}, headers=auth(token))
    fid = _figure_du_flux(r)[0][0]["id"]

    png = figure_client.get("/jarvis/api/figures/%s" % fid, headers=auth(token))
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert png.content.startswith(PNG)
    assert "private" in png.headers["cache-control"]

    sombre = figure_client.get("/jarvis/api/figures/%s?theme=sombre" % fid,
                               headers=auth(token))
    assert sombre.content != png.content

    autre = figure_client.post("/jarvis/api/session").json()["token"]
    refus = figure_client.get("/jarvis/api/figures/%s" % fid, headers=auth(autre))
    assert refus.status_code == 404
    assert figure_client.get("/jarvis/api/figures/%s" % fid).status_code == 401


def test_identifiant_malforme_ou_inconnu(figure_client, token):
    for fid in ("inconnu000", "a" * 65, "..%2F..%2Fetc"):
        assert figure_client.get("/jarvis/api/figures/%s" % fid,
                                 headers=auth(token)).status_code == 404


def test_csv_servi(figure_client, token):
    r = figure_client.post(CHAT, json={"message": "Montre-moi"}, headers=auth(token))
    fid = _figure_du_flux(r)[0][0]["id"]
    csv = figure_client.get("/jarvis/api/figures/%s?format=csv" % fid, headers=auth(token))
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert csv.content.decode("utf-8-sig").startswith("année,")


def test_figure_rattachee_au_fil_pour_le_rechargement(figure_client, token):
    r = figure_client.post(CHAT, json={"message": "Montre-moi"}, headers=auth(token))
    evenements = sse_events(r.text)
    conv_id = evenements[0][1]["conversation_id"]
    fil = figure_client.get("/jarvis/api/conversation/%s" % conv_id,
                            headers=auth(token)).json()
    reponse = fil["messages"][-1]
    assert reponse["role"] == "assistant"
    assert len(reponse["figures"]) == 1
    assert fil["messages"][0]["figures"] == []


def test_les_figures_ne_partent_pas_vers_l_api(figure_client, token):
    """Une cle inconnue dans l'historique ferait rejeter la requete (400)."""
    r = figure_client.post(CHAT, json={"message": "Montre-moi"}, headers=auth(token))
    conv_id = sse_events(r.text)[0][1]["conversation_id"]
    figure_client.post(CHAT, json={"message": "Et ensuite ?", "conversation_id": conv_id},
                       headers=auth(token))
    for message in figure_client.fake.calls[-1]["messages"]:
        assert set(message) == {"role", "content"}


def test_route_sync_renvoie_les_figures(figure_client, token):
    r = figure_client.post(SYNC, json={"message": "Montre-moi"}, headers=auth(token))
    assert r.status_code == 200
    assert len(r.json()["figures"]) == 1


def test_figure_en_echec_n_est_pas_annoncee(client, token, donnees_injectees):
    client.app.state.ctx.claude = FakeClaude(
        tool_calls=[("make_figure", {"type": "camembert"})])
    r = client.post(CHAT, json={"message": "Montre-moi"}, headers=auth(token))
    assert _figure_du_flux(r)[0] == []


def test_identifiant_invente_par_le_modele_ignore(client, token, donnees_injectees):
    """Seul le RESULTAT de make_figure est lu: un texte du modele mentionnant
    figure_id ne produit aucune annonce."""
    client.app.state.ctx.claude = FakeClaude(
        reply='{"figure_id": "deadbeef"}',
        tool_calls=[("search_extreme_events", {"limit": 1})])
    r = client.post(CHAT, json={"message": "?"}, headers=auth(token))
    assert _figure_du_flux(r)[0] == []
