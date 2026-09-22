#!/usr/bin/env python3
"""Tests de src/visualization/teleconnections_plots.py.

Un module de graphiques se teste sur ce qui est verifiable : le fichier est-il
produit, non vide, et la memoire matplotlib est-elle liberee. On ne verifie pas
l esthetique.

Deux points de vigilance guident ces tests :

1. create_all_visualizations_corrected() enveloppe chaque graphique dans un
   try/except qui se contente d afficher la trace. Un graphique casse ne fait
   donc pas echouer l appel : il manque juste un fichier, sans bruit. D ou le
   test qui compte les quatre fichiers attendus.

2. Les figures non fermees s accumulent en memoire. Sur une serie de graphiques
   cela finit par saturer ; on verifie qu aucune figure ne reste ouverte.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")           # avant tout import du module teste
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.visualization.teleconnections_plots import (  # noqa: E402
    TeleconnectionsVisualizer, TeleconnectionsVisualizerCorrected)

GRAPHIQUES = [
    "plot_lag_correlations_corrected",
    "plot_phase_correlations_corrected",
    "plot_enso_analysis_corrected",
    "plot_teleconnections_summary_corrected",
]


@pytest.fixture
def viz(analyseur_avec_resultats):
    plt.close("all")
    return TeleconnectionsVisualizerCorrected(analyseur_avec_resultats)


@pytest.fixture
def viz_leger(analyseur_avec_resultats):
    """Meme visualisateur en basse resolution.

    Le rendu a 300 dpi coute plusieurs secondes par figure. Pour les tests qui
    portent sur la mecanique (fuite de figures, creation de repertoire,
    delegation) et non sur la qualite du rendu, 72 dpi suffit et divise le
    temps de la suite par trois."""
    plt.close("all")
    v = TeleconnectionsVisualizerCorrected(analyseur_avec_resultats)
    v.dpi = 72
    return v


def png_valide(chemin: Path) -> bool:
    """Verifie la signature PNG plutot que la seule existence du fichier."""
    if not chemin.exists() or chemin.stat().st_size == 0:
        return False
    with open(chemin, "rb") as f:
        return f.read(8) == b"\x89PNG\r\n\x1a\n"


# =============================================================================
# Configuration
# =============================================================================

class TestConfiguration:
    def test_couleurs_par_indice(self, viz):
        for indice in ("IOD", "Nino34", "TNA"):
            assert viz.colors[indice].startswith("#")

    def test_couleurs_toutes_distinctes(self, viz):
        """Deux indices de meme couleur rendraient les graphiques illisibles."""
        assert len(set(viz.colors.values())) == len(viz.colors)

    def test_parametres_de_rendu(self, viz):
        assert viz.dpi >= 150            # qualite publication
        assert len(viz.fig_size) == 2

    def test_l_analyseur_est_conserve(self, viz, analyseur_avec_resultats):
        assert viz.analyzer is analyseur_avec_resultats


# =============================================================================
# Production des graphiques
# =============================================================================

class TestProductionDesGraphiques:
    @pytest.mark.parametrize("methode", GRAPHIQUES)
    def test_chaque_graphique_produit_un_png(self, viz, tmp_path, methode):
        sortie = tmp_path / (methode + ".png")
        getattr(viz, methode)(str(sortie))
        assert png_valide(sortie), "%s n a pas produit de PNG exploitable" % methode

    @pytest.mark.parametrize("methode", GRAPHIQUES)
    def test_aucune_figure_ne_reste_ouverte(self, viz_leger, tmp_path, methode):
        """Une figure oubliee est une fuite memoire : sur une boucle de
        production, matplotlib finit par avertir puis saturer."""
        plt.close("all")
        getattr(viz_leger, methode)(str(tmp_path / "x.png"))
        assert plt.get_fignums() == [], (
            "%s laisse %d figure(s) ouverte(s)" % (methode, len(plt.get_fignums())))

    def test_les_quatre_graphiques_sont_produits(self, viz, tmp_path):
        """create_all avale les exceptions graphique par graphique : si l un
        casse, il manque simplement un fichier. Ce test rend cet echec visible."""
        crees = viz.create_all_visualizations_corrected(str(tmp_path))
        pngs = sorted(p.name for p in tmp_path.glob("*.png"))
        assert len(crees) == 4, "graphiques produits : %s" % pngs
        assert len(pngs) == 4
        for png in tmp_path.glob("*.png"):
            assert png_valide(png)

    def test_le_repertoire_est_cree_si_absent(self, viz_leger, tmp_path):
        cible = tmp_path / "sous" / "dossier" / "inexistant"
        viz_leger.create_all_visualizations_corrected(str(cible))
        assert cible.is_dir()

    def test_create_all_ne_laisse_pas_de_figures(self, viz_leger, tmp_path):
        plt.close("all")
        viz_leger.create_all_visualizations_corrected(str(tmp_path))
        assert plt.get_fignums() == []


# =============================================================================
# Robustesse : analyseur sans resultats
# =============================================================================

class TestSansResultats:
    @pytest.fixture
    def viz_vide(self):
        from src.analysis.teleconnections import TeleconnectionsAnalyzer
        plt.close("all")
        return TeleconnectionsVisualizerCorrected(TeleconnectionsAnalyzer())

    @pytest.mark.parametrize("methode", GRAPHIQUES)
    def test_pas_d_exception_sans_donnees(self, viz_vide, tmp_path, methode):
        """Un analyseur vierge ne doit pas faire planter la generation : le
        module doit sortir proprement."""
        getattr(viz_vide, methode)(str(tmp_path / "vide.png"))

    @pytest.mark.parametrize("methode", GRAPHIQUES)
    def test_aucune_figure_ouverte_sans_donnees(self, viz_vide, tmp_path, methode):
        plt.close("all")
        getattr(viz_vide, methode)(str(tmp_path / "vide.png"))
        assert plt.get_fignums() == []

    def test_create_all_sans_donnees_ne_plante_pas(self, viz_vide, tmp_path):
        crees = viz_vide.create_all_visualizations_corrected(str(tmp_path))
        assert isinstance(crees, list)


# =============================================================================
# Classe de compatibilite
# =============================================================================

class TestCompatibiliteAncienneInterface:
    @pytest.fixture
    def ancien(self, analyseur_avec_resultats):
        plt.close("all")
        v = TeleconnectionsVisualizer(analyseur_avec_resultats)
        v.dpi = 72
        return v

    def test_heritage(self, ancien):
        assert isinstance(ancien, TeleconnectionsVisualizerCorrected)

    @pytest.mark.parametrize("ancien_nom,nouveau_nom", [
        ("plot_lag_correlations", "plot_lag_correlations_corrected"),
        ("plot_phase_correlations", "plot_phase_correlations_corrected"),
        ("plot_enso_analysis", "plot_enso_analysis_corrected"),
        ("plot_teleconnections_summary", "plot_teleconnections_summary_corrected"),
    ])
    def test_les_anciens_noms_delegue_aux_nouveaux(self, ancien, tmp_path,
                                                   ancien_nom, nouveau_nom, monkeypatch):
        appels = []
        monkeypatch.setattr(ancien, nouveau_nom,
                            lambda f: appels.append(f))
        getattr(ancien, ancien_nom)("cible.png")
        assert appels == ["cible.png"]

    def test_create_all_delegue(self, ancien, tmp_path):
        crees = ancien.create_all_visualizations(str(tmp_path))
        assert len(crees) == 4
