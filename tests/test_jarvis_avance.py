"""Capacites avancees de Jarvis: recalcul, analogues, navigation, animation,
comparaison et mode soutenance.

Donnees reelles de la plateforme (comme test_jarvis_cartes): le recalcul doit
redonner EXACTEMENT les correlations publiees par le script 04, sans quoi un
"et sans 2020 ?" comparerait deux methodes au lieu de deux jeux d'annees.
"""
import asyncio
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from jarvis import analyses, cartes, figures, soutenance
from jarvis.tools import dataset, registry
from jarvis.widget_html import WIDGET_FILE

from conftest import sse_events

SOURCE = WIDGET_FILE.read_text(encoding="utf-8")
CSV = Path("outputs/teleconnections")
CHAT = "/jarvis/api/chat"


def _executer(nom, params, store=None):
    store = store or figures.FigureStore()
    r = asyncio.run(registry.execute(nom, params, "public",
                                     contexte={"figures": store, "session_id": "s1"}))
    return r, store


def _charge(r):
    assert not r["is_error"], r["content"]
    return json.loads(r["content"])


# =============================================================================
# Recalcul (jarvis/analyses.py, outil recompute_correlation)
# =============================================================================
@pytest.mark.parametrize("phase", ["Phase_1_debut", "Phase_2_pleine", "Phase_3_fin",
                                   "Toutes phases"])
def test_le_recalcul_redonne_les_correlations_publiees(phase):
    publie = pd.read_csv(CSV / ("correlations_%s.csv" % phase))
    for _, l in publie.sample(12, random_state=3).iterrows():
        r = analyses.correlation(phase, int(l["lag_months"]), l["index"], l["metric"])
        assert r["pearson_r"] == pytest.approx(l["pearson_r"], abs=1e-4)
        assert r["pearson_p_neff"] == pytest.approx(l["pearson_p_neff"], abs=1e-4)
        assert r["spearman_r"] == pytest.approx(l["spearman_r"], abs=1e-4)
        assert r["n"] == l["n"] and r["n_eff"] == l["n_eff"]


def test_exclure_une_annee_la_retire_vraiment():
    complet = analyses.correlation("Phase_2_pleine", 4, "AMO", "max_precip")
    sans = analyses.correlation("Phase_2_pleine", 4, "AMO", "max_precip",
                                [a for a in range(1983, 2024) if a != 2020])
    assert sans["n"] == complet["n"] - 1 and 2020 not in sans["annees"]
    assert sans["pearson_r"] != complet["pearson_r"]


def test_trop_peu_d_annees_n_est_pas_calculable():
    r = analyses.correlation("Phase_2_pleine", 4, "AMO", "max_precip", range(1983, 1990))
    assert r["calculable"] is False


def test_outil_recalcul_donne_la_reference_et_la_variation():
    c = _charge(_executer("recompute_correlation", {
        "index": "AMO", "phase": "pleine", "lag": 4, "exclude_years": [2020]})[0])
    ref = pd.read_csv(CSV / "correlations_Phase_2_pleine.csv")
    ligne = ref[(ref["index"] == "AMO") & (ref["lag_months"] == 4)
                & (ref["metric"] == "max_precip")].iloc[0]
    assert c["reference_periode_complete"]["pearson_r"] == pytest.approx(ligne["pearson_r"], abs=1e-3)
    assert c["recalcul"]["n_annees"] == 40
    assert c["annees_exclues"] == [2020]
    assert "variation_r" in c


def test_outil_recalcul_avec_figure_depose_un_nuage():
    r, store = _executer("recompute_correlation", {
        "index": "TNA", "phase": "Phase_2_pleine", "lag": 3, "figure": True})
    c = _charge(r)
    fig = store.obtenir("s1", c["figure"]["figure_id"])
    assert fig.spec["genre"] == "nuage"
    png = figures.rendre(fig.spec, "hud")
    assert png[:4] == b"\x89PNG"
    assert figures.en_csv(fig.spec).startswith("annee,")


def test_comparer_periodes_et_sensibilite():
    c = _charge(_executer("recompute_correlation", {
        "analysis": "comparer_periodes", "index": "AMO", "phase": "pleine", "lag": 4})[0])
    assert c["premiere_periode"]["periode"] == [1983, 2002]
    assert c["seconde_periode"]["periode"] == [2003, 2023]
    assert isinstance(c["meme_signe"], bool)
    s = _charge(_executer("recompute_correlation", {
        "analysis": "sensibilite_annees", "index": "AMO", "phase": "pleine", "lag": 4})[0])
    assert len(s["annees_les_plus_influentes"]) == 6
    assert isinstance(s["annees_dont_le_retrait_fait_perdre_la_significativite"], list)


@pytest.mark.parametrize("params, message", [
    ({"index": "AMO", "phase": "pleine"}, "lag"),
    ({"index": "AMO", "phase": "pleine", "lag": 40}, "lag"),
    ({"index": "AMO", "phase": "pleine", "lag": 2, "period": [2010, 1990]}, "period"),
    ({"index": "AMO", "phase": "pleine", "lag": 2, "exclude_years": list(range(1983, 2003))},
     "exclude_years"),
    ({"index": "XYZ", "phase": "pleine", "lag": 2}, "Indice"),
])
def test_recalcul_refuse_les_parametres_invalides(params, message):
    r, _ = _executer("recompute_correlation", params)
    assert r["is_error"] and message in r["content"]


# =============================================================================
# Annees analogues
# =============================================================================
def test_analogues_excluent_l_annee_de_reference_et_rapportent_la_competence():
    c = _charge(_executer("find_analog_years", {
        "year": 2020, "phase": "Phase_2_pleine", "indices": "atlantique", "count": 4})[0])
    annees = [a["annee"] for a in c["analogues"]]
    assert len(annees) == 4 and 2020 not in annees
    assert c["indices_utilises"] == ["TNA", "TSA", "ATL3", "AMM", "AMO"]
    distances = [a["distance"] for a in c["analogues"]]
    assert distances == sorted(distances)
    comp = c["competence_de_la_methode"]
    assert comp["calculable"] and "verdict" in comp
    # Verdict coherent avec le chiffre: pas de "pouvoir predictif" sans p < 0,05.
    if comp["p_neff"] >= 0.05:
        assert "N'A PAS" in comp["verdict"]


def test_analogues_refusent_une_annee_hors_periode():
    r, _ = _executer("find_analog_years", {"year": 1970, "phase": "pleine"})
    assert r["is_error"]


# =============================================================================
# Navigation dans le dashboard
# =============================================================================
def test_navigation_ne_garde_que_les_filtres_valides():
    c = _charge(_executer("navigate_dashboard", {
        "page": "Teleconnexions",
        "filters": {"phase": "Phase_2_pleine", "metrique": "max_precip",
                    "inconnu": 1, "type_correlation": "<script>"}})[0])
    assert c["navigation"] == {"page": "Teleconnexions",
                               "filtres": {"phase": "Phase_2_pleine",
                                           "metrique": "max_precip"}}
    assert set(c["filtres_ignores"]) == {"inconnu", "type_correlation"}


def test_la_copie_des_filtres_de_navigation_suit_page_context():
    from jarvis import page_context
    from jarvis.tools import navigation
    assert navigation.PAGES == page_context.PAGES
    assert {p: set(f) for p, f in navigation.FILTRES.items()} == {
        p: set(c) for p, c in page_context.CHAMPS.items()}


def test_le_serveur_demarre_sans_import_circulaire():
    """Import dans un processus neuf, dans l'ordre du serveur (page_context
    d'abord): c'est ainsi que l'import circulaire s'etait revele."""
    import subprocess
    r = subprocess.run([sys.executable, "-c", "import jarvis.page_context; import jarvis.app"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]


def test_navigation_refuse_une_page_inconnue():
    r, _ = _executer("navigate_dashboard", {"page": "Admin"})
    assert r["is_error"]


def test_la_navigation_part_vers_le_widget_en_evenement_sse(client, token):
    client.fake.tool_calls = [("navigate_dashboard",
                               {"page": "Clustering", "filters": {"phase": "Phase_2_pleine"}})]
    r = client.post(CHAT, json={"message": "Ouvre le clustering"},
                    headers={"X-Jarvis-Session": token})
    evenements = sse_events(r.text)
    nav = [d for n, d in evenements if n == "navigation"]
    assert nav == [{"page": "Clustering", "filtres": {"phase": "Phase_2_pleine"}}]


def test_une_navigation_refusee_n_atteint_pas_le_widget(client, token):
    client.fake.tool_calls = [("navigate_dashboard", {"page": "Inconnue"})]
    r = client.post(CHAT, json={"message": "Ouvre"}, headers={"X-Jarvis-Session": token})
    assert not [n for n, _ in sse_events(r.text) if n == "navigation"]


def _jarvis_widget():
    scripts = str(Path("scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import jarvis_widget
    return jarvis_widget


def test_le_dashboard_ne_retient_que_les_cles_declarees():
    jw = _jarvis_widget()
    nav = jw.lire_navigation(json.dumps({
        "page": "Evenements", "n": 1,
        "filtres": {"annees": [1990, 2000], "phases": ["Phase_2_pleine"],
                    "pirate": "x", "evenement_date": {"objet": 1}}}))
    assert nav == {"page": "Evenements",
                   "filtres": {"evt_yr_range": (1990, 2000),
                               "evt_phases_sel": ["Phase_2_pleine"]}}
    # Phase + cluster: la page ne doit pas effacer le cluster demande.
    cl = jw.lire_navigation(json.dumps({"page": "Clustering",
                                        "filtres": {"phase": "Phase_2_pleine", "cluster": 1}}))
    assert cl["filtres"] == {"cl_phase": "Phase_2_pleine", "cl_shared_cluster": 1,
                             "cl_shared_last_phase": "Phase_2_pleine"}
    assert jw.lire_navigation(json.dumps({"page": "Inconnue"})) is None
    assert jw.lire_navigation("pas du json") is None
    assert jw.lire_navigation("x" * 5000) is None
    assert jw.lire_navigation("") is None


def test_le_html_du_widget_ne_change_plus_avec_les_filtres():
    """Sinon Streamlit recharge l'iframe a chaque clic: Jarvis se coupait en
    pleine phrase des qu'il ouvrait lui-meme une page."""
    source = Path("scripts/jarvis_widget.py").read_text(encoding="utf-8")
    assert "page_context=None" in source
    assert 'id="jarvis-page-ctx"' in source
    dash = Path("scripts/dashboard.py").read_text(encoding="utf-8")
    assert dash.index('st.container(key="jarvis_slot")') < dash.index("st.markdown(")
    assert "with _jarvis_slot:" in dash
    assert "appliquer_navigation(st)" in dash


# =============================================================================
# Animation SST
# =============================================================================
def test_archive_d_animation_coherente():
    a = cartes.animations()
    n = len(a["dates"])
    assert n >= 20
    assert a["images"].shape[:2] == (n, len(a["decalages"]))
    assert a["decalages"][0] == -150 and a["decalages"][-1] == 0
    assert a["boites"].shape == (n, len(a["decalages"]), len(a["noms_boites"]))


def test_animation_liste_puis_anime_un_evenement():
    liste = _charge(_executer("animate_sst_event", {})[0])
    assert liste["evenements_animables"]
    r, store = _executer("animate_sst_event", {"phase": "Phase_2_pleine"})
    c = _charge(r)
    assert c["carte"] is True and c["phase"] == "Phase_2_pleine"
    assert "TNA" in c["anomalies_par_boite_degC"]
    fig = store.obtenir("s1", c["figure_id"])
    gif = figures.rendre(fig.spec, "hud")
    assert gif[:4] == b"GIF8"
    assert figures.en_csv(fig.spec).startswith("jours_avant_evenement,date,")


def test_animation_refuse_un_evenement_non_archive():
    r, _ = _executer("animate_sst_event", {"date": "1990-01-01"})
    assert r["is_error"] and "animables" in r["content"]


def test_la_route_des_figures_sert_les_animations_en_gif(client, token):
    client.fake.tool_calls = [("animate_sst_event", {"phase": "Phase_1_debut"})]
    r = client.post(CHAT, json={"message": "Anime"}, headers={"X-Jarvis-Session": token})
    fig = [d for n, d in sse_events(r.text) if n == "figure"][0]
    assert fig["carte"] is True
    img = client.get("/jarvis/api/figures/%s?theme=hud" % fig["id"],
                     headers={"X-Jarvis-Session": token})
    assert img.headers["content-type"] == "image/gif"


# =============================================================================
# Mode soutenance
# =============================================================================
@pytest.fixture(scope="module")
def donnees_soutenance():
    return asyncio.run(dataset.load(soutenance.JEUX))


def test_chaque_etape_se_compose_depuis_les_donnees(donnees_soutenance):
    store = figures.FigureStore()
    for n in range(1, len(soutenance.ETAPES) + 1):
        e = soutenance.etape(n, donnees_soutenance, store, "s1")
        assert e["numero"] == n and e["total"] == len(soutenance.ETAPES)
        assert len(e["narration"]) > 80
        assert "n'est pas disponible" not in e["narration"], e["titre"]
        # Pas d'etoiles lues a voix haute ("asterisque").
        assert "*" not in e["narration"]
        if e["figure"]:
            assert store.obtenir("s1", e["figure"]["id"]) is not None


def test_la_narration_cite_les_vrais_chiffres(donnees_soutenance):
    """Etape 3: la correlation citee est celle du CSV publie, au centieme."""
    e = soutenance.etape(3, donnees_soutenance, figures.FigureStore(), "s1")
    publie = pd.read_csv(CSV / "correlations_Phase_2_pleine.csv")
    sig = publie[(publie["metric"] == "max_precip") & (publie["pearson_p_neff"] < 0.05)]
    meilleure = sig.loc[sig["pearson_r"].abs().idxmax()]
    assert ("%.2f" % meilleure["pearson_r"]).replace(".", ",") in e["narration"]
    assert meilleure["index"] in e["narration"]


def test_routes_soutenance(client, token):
    h = {"X-Jarvis-Session": token}
    plan = client.get("/jarvis/api/soutenance", headers=h).json()["etapes"]
    assert [p["numero"] for p in plan] == list(range(1, len(soutenance.ETAPES) + 1))
    e = client.post("/jarvis/api/soutenance/1", headers=h).json()
    assert e["page"] == "Evenements" and e["narration"]
    img = client.get("/jarvis/api/figures/%s?theme=hud" % e["figure"]["id"], headers=h)
    assert img.status_code == 200
    assert client.post("/jarvis/api/soutenance/99", headers=h).status_code == 404
    assert client.post("/jarvis/api/soutenance/1").status_code in (401, 403)
    # Aucun appel au modele: rien n'est facture pendant une soutenance.
    assert client.fake.calls == []


# =============================================================================
# Widget
# =============================================================================
def _bloc(debut, fin):
    return SOURCE[SOURCE.index(debut):][:SOURCE[SOURCE.index(debut):].index(fin)]


def test_widget_relaie_la_navigation_et_lit_le_contexte_de_la_page():
    assert '} else if(name === "navigation"){' in SOURCE
    assert "Tableau.naviguer(data);" in SOURCE
    assert "var ctxPage = contexteHote();" in SOURCE
    naviguer = _bloc("function naviguer(nav){", "function annoncer(")
    # Champ cache du dashboard, valide comme une frappe (setter natif + keypress).
    assert ".st-key-jarvis_nav_cmd input" in SOURCE
    assert '"keypress"' in naviguer and "HTMLInputElement.prototype" in naviguer


def test_une_question_met_la_soutenance_en_pause():
    ask = _bloc("function ask(text){", "state.busy = true;")
    assert "Soutenance.pause(true);" in ask


def test_deux_cartes_d_une_meme_reponse_s_affichent_cote_a_cote():
    assert "Ecran.comparer(cartesRecues[cartesRecues.length - 2]" in SOURCE
    ecran = _bloc("var Ecran = (function(){", "})();")
    assert "function comparer(a, b)" in ecran and "ec-volet" in ecran


def test_soutenance_n_injecte_pas_de_html_du_serveur():
    """La narration passe par bubble() (Markdown echappe) et textContent."""
    sout = _bloc("var Soutenance = (function(){", "  })();")
    assert "innerHTML = e." not in sout and "innerHTML = plan" not in sout
    assert 'textContent = plan[n - 1].titre' in sout


def test_le_js_du_widget_reste_en_ascii_hors_accueil():
    js = SOURCE[SOURCE.index("<script>"):SOURCE.rindex("</script>")]
    accueil = _bloc("function texteAccueil(", "function saluer(")
    reste = js.replace(accueil, "")
    assert all(ord(c) < 128 for c in reste)
