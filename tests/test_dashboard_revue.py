"""Garde-fous des corrections de la revue du 27/09/2026 (dashboard ClimatSen)."""
import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

ACTIONS = ("Exécuter", "Lancer", "Télécharger", "Supprimer", "Relancer")


def _app(page, **etat):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(RACINE / "scripts" / "dashboard.py"), default_timeout=240)
    at.session_state["nav_page"] = page
    for k, v in etat.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _boutons_action(at):
    return [b.label for b in at.button if any(m in b.label for m in ACTIONS)]


@pytest.fixture(autouse=True)
def _sans_widget(monkeypatch):
    monkeypatch.setenv("JARVIS_WIDGET", "off")
    # Journaux Streamlit tus pendant ces tests seulement : d'autres tests
    # (securite Jarvis) verifient des messages de journal.
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


# --- Point 01 : actions serveur reservees a l'administrateur -------------------
@pytest.mark.parametrize("onglet", ["Données CHIRPS", "Pipeline d'analyse", "Données SST"])
def test_pipeline_sans_session_admin_aucun_bouton_d_action(onglet):
    at = _app("Pipeline", pip_tab=onglet)
    assert _boutons_action(at) == []


def test_pipeline_avec_session_admin_boutons_disponibles():
    at = _app("Pipeline", pip_tab="Pipeline d'analyse", climatsen_admin=True)
    labels = _boutons_action(at)
    assert "Lancer le pipeline complet" in labels and "Exécuter" in labels


def test_clustering_relance_reservee_a_l_admin():
    assert _boutons_action(_app("Clustering")) == []
    assert any("Relancer" in l for l in _boutons_action(_app("Clustering", climatsen_admin=True)))


def test_mot_de_passe_faux_refuse(monkeypatch):
    import admin_gate
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD_HASH", "")
    assert admin_gate._verifier("nimporte") is False


# --- Point 13 : exports du pipeline --------------------------------------------
def _pipeline():
    spec = importlib.util.spec_from_file_location("pipeline_page", RACINE / "scripts/vues/pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_format_deduit_de_l_extension_et_tailles_lisibles():
    p = _pipeline()
    assert p._fmt_export({"path": "a/b/figure.png"}) == "png"
    assert p._fmt_export({"path": "a/b.csv"}) == "csv"
    assert p._fmt_export({"path": "a/b.png", "fmt": "zip_glob"}) == "zip_glob"
    assert p._taille(940) == "940 o"
    assert p._taille(12 * 1024) == "12 Ko"
    assert p._taille(int(3.4 * 1024 ** 2)) == "3,4 Mo"


def test_aucune_figure_etiquetee_csv():
    p = _pipeline()
    for step in p.PIPELINE_STEPS:
        for e in step.get("exports", {}).get("figure", []):
            assert p._fmt_export(e) in ("png", "zip_glob"), (step["id"], e)


# --- Point 02 : figures cartopy issues du clustering affiche --------------------
def test_fiches_des_figures_cartopy_concordent_avec_le_clustering():
    import pandas as pd
    dossier = RACINE / "outputs/visualizations/clustering/sst_patterns"
    for phase in ("Phase_1_debut", "Phase_2_pleine", "Phase_3_fin", "All_phases"):
        fiche = dossier / f"{phase}_sst_patterns_clusters.json"
        if not fiche.exists():
            pytest.skip("figures cartopy non generees")
        meta = json.loads(fiche.read_text(encoding="utf-8"))
        ev = pd.read_csv(RACINE / f"outputs/clustering/{phase}/{phase}_events_with_clusters.csv")
        attendu = {str(int(c)): int(n) for c, n in ev["cluster"].value_counts().sort_index().items()}
        assert meta["effectifs"] == attendu, phase
        assert meta["k"] == len(attendu)


# --- Suivi du 28/09 : navigation (S3), dependances (S1), cartes de chaleur (14) --
def test_accueil_est_la_page_par_defaut():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(RACINE / "scripts" / "dashboard.py"), default_timeout=240)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["nav_page"] == "Accueil"


@pytest.mark.parametrize("page", ["Evenements", "Indices SST", "Teleconnexions", "Veille",
                                  "Vulnerabilite", "A propos"])
def test_page_demandee_en_session_est_rejointe(page):
    # Menu lateral, Jarvis (navigate_dashboard) : la page demandee en session est
    # rejointe par st.switch_page, qui met aussi l'URL a jour.
    assert _app(page).session_state["nav_page"] == page


def test_pas_de_dossier_pages_a_cote_du_script_principal():
    # Un dossier scripts/pages/ reactive l'ancien mode multipage de Streamlit
    # ("Page not found" au premier visiteur apres redemarrage).
    assert not (RACINE / "scripts" / "pages").exists()


def test_aucune_trace_mapbox():
    # go.Scattermapbox / go.Densitymapbox ont ete retires dans Plotly 7.
    for f in (RACINE / "scripts").rglob("*.py"):
        texte = f.read_text(encoding="utf-8", errors="ignore")
        assert "Scattermapbox(" not in texte and "Densitymapbox(" not in texte, f.name


def test_requirements_racine_complets():
    req = (RACINE / "requirements.txt").read_text(encoding="utf-8")
    assert "python-docx" in req
    assert "plotly>=5.24" in req


def test_chiffres_des_cartes_de_chaleur_lisibles():
    import dashboard_utils as du
    echelle = [[0, "#7F1D1D"], [0.5, "#F8FAFC"], [1, "#1E3A8A"]]
    assert du.couleur_sur_fond(0.0, -0.5, 0.5, echelle) == "#0F172A"   # cellule claire
    assert du.couleur_sur_fond(0.5, -0.5, 0.5, echelle) == "#FFFFFF"   # cellule foncee
    assert du.couleur_sur_fond(-0.5, -0.5, 0.5, echelle) == "#FFFFFF"
