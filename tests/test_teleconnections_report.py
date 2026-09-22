#!/usr/bin/env python3
"""Tests de src/reports/teleconnections_report.py.

Un generateur de rapports se teste sur trois choses : le fichier est produit et
relisible, les sections attendues y figurent, et les interpretations
automatiques disent bien ce que les chiffres disent.

La derniere est la plus importante : c est ce texte qui serait repris dans un
memoire. Une phrase qui qualifie de "tres forte" une correlation faible est une
erreur scientifique, pas une coquille.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.reports.teleconnections_report import (  # noqa: E402
    TeleconnectionsReportGenerator, TeleconnectionsReportGeneratorCorrected)


@pytest.fixture
def rapporteur(analyseur_avec_resultats):
    return TeleconnectionsReportGeneratorCorrected(analyseur_avec_resultats)


@pytest.fixture
def rapporteur_fort(analyseur_signal_fort):
    """Rapporteur sur le jeu a signal fort : des correlations survivent au FDR,
    donc les tableaux et sections ont reellement du contenu a verifier."""
    return TeleconnectionsReportGeneratorCorrected(analyseur_signal_fort)


@pytest.fixture
def rapporteur_vide():
    from src.analysis.teleconnections import TeleconnectionsAnalyzer
    return TeleconnectionsReportGeneratorCorrected(TeleconnectionsAnalyzer())


# =============================================================================
# Analyse des patterns
# =============================================================================

class TestPatterns:
    def test_structure_complete(self, rapporteur):
        patterns = rapporteur.analyze_correlation_patterns_corrected()
        for cle in ("strongest_teleconnection", "best_physical_validation",
                    "most_consistent_index", "phase_preferences",
                    "seasonal_patterns", "significance_summary",
                    "physical_validation_summary", "methodological_quality"):
            assert cle in patterns

    def test_sans_resultats_structure_conservee(self, rapporteur_vide):
        """Un analyseur vierge doit renvoyer le squelette, pas lever."""
        patterns = rapporteur_vide.analyze_correlation_patterns_corrected()
        assert patterns["strongest_teleconnection"] is None
        assert patterns["phase_preferences"] == {}

    def test_la_plus_forte_teleconnexion_est_celle_injectee(self, rapporteur_fort):
        """Sur le jeu a signal fort, le lien Nino34 -> intensite a 3 mois est
        le seul present : le rapport doit le designer comme la teleconnexion
        la plus forte, au bon indice et au bon decalage."""
        from conftest import INDICE_PILOTE, LAG_INJECTE

        plus_forte = rapporteur_fort.analyze_correlation_patterns_corrected()[
            "strongest_teleconnection"]
        assert plus_forte is not None
        assert plus_forte["index"] == INDICE_PILOTE
        assert plus_forte["lag"] == LAG_INJECTE
        assert plus_forte["correlation"] > 0.9
        assert plus_forte["is_physical_optimal"]


# =============================================================================
# Interpretation automatique des correlations
# =============================================================================

class TestInterpretation:
    def test_correlation_non_calculable(self, rapporteur_vide):
        for corr, p in [(np.nan, 0.01), (0.5, np.nan), (np.nan, np.nan)]:
            texte = rapporteur_vide.interpret_correlations_climatological(corr, p)
            assert "non calculable" in texte

    @pytest.mark.parametrize("r,attendu", [
        (0.45, "très forte"),
        (0.30, "forte"),
        (0.18, "modérée"),
        (0.12, "faible"),
        (0.05, "très faible"),
    ])
    def test_bandes_de_force(self, rapporteur_vide, r, attendu):
        texte = rapporteur_vide.interpret_correlations_climatological(r, 0.01)
        assert attendu in texte

    def test_les_seuils_different_de_ceux_de_l_analyseur(self, rapporteur_vide):
        """Caracterisation d une incoherence entre modules, a connaitre avant
        de citer ces textes.

        L analyseur classe sur |r| >= 0.6 / 0.4 / 0.25 / 0.15 ; le rapport
        classe sur 0.4 / 0.25 / 0.15 / 0.10. Un meme r = 0.45 est donc
        'Forte' pour l analyseur et 'tres forte (climatologiquement
        exceptionnelle)' pour le rapport."""
        from src.analysis.teleconnections import TeleconnectionsAnalyzer
        from conftest import paire_correlee

        x, y = paire_correlee(0.45)
        cote_analyseur = TeleconnectionsAnalyzer(
            min_observations=30).calculate_correlation_robust(
                pd.Series(x), pd.Series(y))["strength"]
        cote_rapport = rapporteur_vide.interpret_correlations_climatological(0.45, 0.01)

        assert cote_analyseur.startswith("Forte")
        assert "très forte" in cote_rapport

    def test_direction_du_lien(self, rapporteur_vide):
        assert "positive" in rapporteur_vide.interpret_correlations_climatological(0.5, 0.01)
        assert "négative" in rapporteur_vide.interpret_correlations_climatological(-0.5, 0.01)

    @pytest.mark.parametrize("p,attendu", [
        (0.0001, "très hautement significative"),
        (0.005, "hautement significative"),
        (0.03, "significative"),
        (0.4, "non significative"),
    ])
    def test_niveaux_de_significativite(self, rapporteur_vide, p, attendu):
        texte = rapporteur_vide.interpret_correlations_climatological(0.3, p)
        assert attendu in texte

    def test_une_correlation_non_significative_n_est_pas_presentee_comme_acquise(
            self, rapporteur_vide):
        """Verification de non-regression sur le risque de sur-affirmation :
        p = 0.4 doit produire 'non significative', pas 'significative' seul."""
        texte = rapporteur_vide.interpret_correlations_climatological(0.45, 0.4)
        assert "non significative" in texte

    def test_la_variance_expliquee_est_reportee(self, rapporteur_vide):
        texte = rapporteur_vide.interpret_correlations_climatological(0.5, 0.01, 25.0)
        assert "25.0" in texte and "variance" in texte

    def test_le_lag_physique_est_signale(self, rapporteur_vide):
        optimal = rapporteur_vide.interpret_correlations_climatological(
            0.5, 0.01, 25.0, is_physical_optimal=True)
        non_optimal = rapporteur_vide.interpret_correlations_climatological(
            0.5, 0.01, 25.0, is_physical_optimal=False)
        assert "cohérent" in optimal
        assert "non optimal" in non_optimal


# =============================================================================
# Sections redigees
# =============================================================================

class TestSectionsRedigees:
    @pytest.mark.parametrize("methode", [
        "generate_executive_summary_corrected",
        "generate_detailed_results_section_corrected",
        "generate_methodology_section_corrected",
    ])
    def test_chaque_section_produit_du_texte(self, rapporteur, methode):
        texte = getattr(rapporteur, methode)()
        assert isinstance(texte, str)
        assert len(texte) > 200

    def test_la_methodologie_documente_les_corrections(self, rapporteur):
        """La section methodologie doit mentionner les choix qui rendent les
        resultats defendables."""
        texte = rapporteur.generate_methodology_section_corrected().lower()
        assert "fdr" in texte or "tests multiples" in texte
        assert "stationnar" in texte

    @pytest.mark.parametrize("methode", [
        "generate_executive_summary_corrected",
        "generate_detailed_results_section_corrected",
    ])
    def test_les_sections_tiennent_sans_resultats(self, rapporteur_vide, methode):
        assert isinstance(getattr(rapporteur_vide, methode)(), str)


# =============================================================================
# Fichiers produits
# =============================================================================

class TestFichiersProduits:
    def test_rapport_complet(self, rapporteur, tmp_path):
        cible = tmp_path / "rapport.md"
        rapporteur.generate_complete_report_corrected(str(cible))
        assert cible.exists() and cible.stat().st_size > 0
        contenu = cible.read_text(encoding="utf-8")
        assert len(contenu) > 500

    def test_le_rapport_est_bien_en_utf8(self, rapporteur, tmp_path):
        """Le texte contient des accents et des symboles : un rapport ecrit en
        cp1252 serait illisible ailleurs."""
        cible = tmp_path / "rapport.md"
        rapporteur.generate_complete_report_corrected(str(cible))
        contenu = cible.read_text(encoding="utf-8")
        assert any(c in contenu for c in "éèêàûô")

    def test_rapport_json_valide(self, rapporteur, tmp_path):
        """Point de fragilite connu : les resultats contiennent des types numpy
        (np.bool_, np.float64) que json ne sait pas serialiser nativement."""
        cible = tmp_path / "rapport.json"
        rapporteur.generate_json_report_corrected(str(cible))
        assert cible.exists(), "aucun fichier JSON produit"
        donnees = json.loads(cible.read_text(encoding="utf-8"))
        assert isinstance(donnees, dict) and donnees

    def test_export_excel(self, rapporteur, tmp_path):
        cible = tmp_path / "resume.xlsx"
        rapporteur.export_summary_excel_corrected(str(cible))
        assert cible.exists() and cible.stat().st_size > 0
        feuilles = pd.read_excel(cible, sheet_name=None)
        assert len(feuilles) >= 1


# =============================================================================
# Tableau de synthese
# =============================================================================

class TestTableauDeSynthese:
    COLONNES = ["Type", "Indice", "Métrique", "Phase/Lag", "Corrélation",
                "P-value", "Variance_Expliquée", "Validation_Physique",
                "Pertinence_Climatologique", "N_obs"]

    def test_colonnes(self, rapporteur):
        assert list(rapporteur.generate_summary_table_corrected().columns) == self.COLONNES

    def test_memes_colonnes_quand_vide(self, rapporteur_vide):
        """Le code aval (export Excel) indexe ces colonnes : elles doivent
        exister meme sans une seule correlation retenue."""
        table = rapporteur_vide.generate_summary_table_corrected()
        assert table.empty
        assert list(table.columns) == self.COLONNES

    def test_seules_les_correlations_corrigees_significatives_sont_retenues(
            self, rapporteur_fort):
        """Le tableau de synthese est ce qu on lit en premier : il ne doit
        contenir que ce qui survit a la correction FDR."""
        table = rapporteur_fort.generate_summary_table_corrected()
        assert not table.empty
        assert (table["P-value"] <= 0.05).all()
        assert table["Corrélation"].between(-1, 1).all()

    def test_le_tableau_ne_retient_que_l_indice_porteur_du_signal(
            self, rapporteur_fort):
        """IOD et TNA sont du bruit : ils ne doivent pas apparaitre."""
        from conftest import INDICE_PILOTE
        table = rapporteur_fort.generate_summary_table_corrected()
        assert set(table["Indice"]) == {INDICE_PILOTE}

    def test_tri_par_variance_expliquee(self, rapporteur_fort):
        table = rapporteur_fort.generate_summary_table_corrected()
        assert len(table) >= 2
        valeurs = table["Variance_Expliquée"].tolist()
        assert valeurs == sorted(valeurs, reverse=True)

    def test_export_excel_avec_contenu_reel(self, rapporteur_fort, tmp_path):
        cible = tmp_path / "resume_fort.xlsx"
        rapporteur_fort.export_summary_excel_corrected(str(cible))
        feuilles = pd.read_excel(cible, sheet_name=None)
        assert any(not f.empty for f in feuilles.values())


# =============================================================================
# Classe de compatibilite
# =============================================================================

class TestCompatibiliteAncienneInterface:
    @pytest.fixture
    def ancien(self, analyseur_avec_resultats):
        return TeleconnectionsReportGenerator(analyseur_avec_resultats)

    def test_heritage(self, ancien):
        assert isinstance(ancien, TeleconnectionsReportGeneratorCorrected)

    @pytest.mark.parametrize("ancien_nom,nouveau_nom", [
        ("analyze_correlation_patterns", "analyze_correlation_patterns_corrected"),
        ("generate_executive_summary", "generate_executive_summary_corrected"),
        ("generate_detailed_results_section", "generate_detailed_results_section_corrected"),
        ("generate_summary_table", "generate_summary_table_corrected"),
    ])
    def test_les_anciens_noms_delegue_aux_nouveaux(self, ancien, ancien_nom,
                                                   nouveau_nom, monkeypatch):
        sentinelle = object()
        monkeypatch.setattr(ancien, nouveau_nom, lambda: sentinelle)
        assert getattr(ancien, ancien_nom)() is sentinelle

    def test_generation_de_fichiers_par_l_ancienne_interface(self, ancien, tmp_path):
        ancien.generate_complete_report(str(tmp_path / "r.md"))
        ancien.generate_json_report(str(tmp_path / "r.json"))
        assert (tmp_path / "r.md").exists()
        assert (tmp_path / "r.json").exists()
