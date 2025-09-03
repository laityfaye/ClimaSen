#!/usr/bin/env python3
# tests/test_teleconnections.py
"""
Tests unitaires pour le module d'analyse des téléconnexions.

Assure la qualité et la robustesse du code scientifique.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import tempfile
import json

# Imports du module à tester
from src.analysis.teleconnections import (
    TeleconnectionsAnalyzer, LagCorrelationAnalyzer, SeasonalTeleconnectionAnalyzer,
    TimeSeriesData, CorrelationResult, TeleconnectionConfig, CorrelationType,
    TeleconnectionsError, quick_teleconnection_analysis
)
from src.visualization.teleconnections_plots import TeleconnectionsVisualizer
from src.reports.teleconnections_report import TeleconnectionsReporter


class TestTimeSeriesData:
    """Tests pour la classe TimeSeriesData."""
    
    def test_valid_timeseries_creation(self):
        """Test création valide d'une série temporelle."""
        dates = pd.date_range('2020-01', '2020-12', freq='MS')
        values = np.random.randn(len(dates))
        series = pd.Series(values, index=dates)
        
        ts_data = TimeSeriesData(series, "test_series")
        
        assert ts_data.name == "test_series"
        assert len(ts_data.data) == 12
        assert isinstance(ts_data.data.index, pd.DatetimeIndex)
    
    def test_invalid_data_type(self):
        """Test validation avec type de données invalide."""
        with pytest.raises(TeleconnectionsError):
            TimeSeriesData([1, 2, 3], "invalid")
    
    def test_invalid_index_type(self):
        """Test validation avec index non-datetime."""
        series = pd.Series([1, 2, 3], index=[0, 1, 2])
        
        with pytest.raises(TeleconnectionsError):
            TimeSeriesData(series, "invalid_index")
    
    def test_shift_lag(self):
        """Test application d'un décalage temporel."""
        dates = pd.date_range('2020-01', '2020-06', freq='MS')
        values = [1, 2, 3, 4, 5, 6]
        series = pd.Series(values, index=dates)
        
        ts_data = TimeSeriesData(series, "original")
        shifted = ts_data.shift_lag(2)
        
        assert shifted.name == "original_lag2"
        # Vérifier que les 2 premières valeurs sont NaN après décalage
        assert pd.isna(shifted.data.iloc[0])
        assert pd.isna(shifted.data.iloc[1])
        assert shifted.data.iloc[2] == 1  # Valeur décalée
    
    def test_filter_season(self):
        """Test filtrage par saison."""
        dates = pd.date_range('2020-01', '2020-12', freq='MS')
        values = np.arange(1, 13)
        series = pd.Series(values, index=dates)
        
        ts_data = TimeSeriesData(series, "full_year")
        filtered = ts_data.filter_season([5, 6, 7])  # Mai, Juin, Juillet
        
        assert len(filtered.data) == 3
        assert filtered.data.iloc[0] == 5  # Mai = valeur 5
        assert filtered.data.iloc[1] == 6  # Juin = valeur 6
        assert filtered.data.iloc[2] == 7  # Juillet = valeur 7
    
    def test_align_with(self):
        """Test alignement de deux séries."""
        dates1 = pd.date_range('2020-01', '2020-06', freq='MS')
        dates2 = pd.date_range('2020-03', '2020-08', freq='MS')
        
        series1 = pd.Series(np.arange(6), index=dates1)
        series2 = pd.Series(np.arange(10, 16), index=dates2)
        
        ts1 = TimeSeriesData(series1, "series1")
        ts2 = TimeSeriesData(series2, "series2")
        
        aligned1, aligned2 = ts1.align_with(ts2)
        
        # Vérifier l'intersection (Mars à Juin = 4 mois)
        assert len(aligned1.data) == 4
        assert len(aligned2.data) == 4
        assert aligned1.data.index.equals(aligned2.data.index)
    
    def test_align_no_overlap(self):
        """Test alignement sans chevauchement."""
        dates1 = pd.date_range('2020-01', '2020-03', freq='MS')
        dates2 = pd.date_range('2020-06', '2020-08', freq='MS')
        
        series1 = pd.Series([1, 2, 3], index=dates1)
        series2 = pd.Series([4, 5, 6], index=dates2)
        
        ts1 = TimeSeriesData(series1, "series1")
        ts2 = TimeSeriesData(series2, "series2")
        
        with pytest.raises(TeleconnectionsError):
            ts1.align_with(ts2)


class TestCorrelationResult:
    """Tests pour la classe CorrelationResult."""
    
    def test_significant_correlation(self):
        """Test corrélation significative."""
        result = CorrelationResult(
            correlation=0.65,
            p_value=0.01,
            n_observations=50,
            lag=3
        )
        
        assert result.significant is True
        assert result.correlation == 0.65
        assert result.lag == 3
    
    def test_non_significant_correlation(self):
        """Test corrélation non significative."""
        result = CorrelationResult(
            correlation=0.15,
            p_value=0.3,
            n_observations=30,
            lag=1
        )
        
        assert result.significant is False
    
    def test_explicit_significance(self):
        """Test avec significativité explicite."""
        result = CorrelationResult(
            correlation=0.25,
            p_value=0.08,
            n_observations=40,
            lag=2,
            significant=True  # Forcé
        )
        
        assert result.significant is True


class TestLagCorrelationAnalyzer:
    """Tests pour l'analyseur de corrélations avec décalages."""
    
    @pytest.fixture
    def sample_data(self):
        """Données d'exemple pour les tests."""
        np.random.seed(42)
        dates = pd.date_range('2000-01', '2020-12', freq='MS')
        
        # Événements avec plus d'activité en saison des pluies
        events = np.random.poisson(0.3, len(dates))
        rainy_mask = pd.Series(dates).dt.month.isin([6, 7, 8, 9])
        events[rainy_mask] += np.random.poisson(1.2, rainy_mask.sum())
        
        # Indice climatique avec corrélation artificielle lag=2
        index_values = np.random.normal(0, 1, len(dates))
        
        # Introduire corrélation avec lag=2
        for i in range(2, len(events)):
            index_values[i-2] += 0.5 * events[i]
        
        events_ts = TimeSeriesData(pd.Series(events, index=dates), "events")
        index_ts = TimeSeriesData(pd.Series(index_values, index=dates), "climate_index")
        
        return events_ts, index_ts
    
    def test_calculate_correlation_valid(self, sample_data):
        """Test calcul corrélation valide."""
        events_ts, index_ts = sample_data
        
        config = TeleconnectionConfig(max_lag=5, min_observations=20)
        analyzer = LagCorrelationAnalyzer(config)
        
        result = analyzer.calculate_correlation(events_ts, index_ts, lag=2)
        
        assert result is not None
        assert isinstance(result, CorrelationResult)
        assert result.lag == 2
        assert result.n_observations >= 20
        assert -1 <= result.correlation <= 1
        assert 0 <= result.p_value <= 1
    
    def test_calculate_correlation_insufficient_data(self):
        """Test avec données insuffisantes."""
        # Données très courtes
        dates = pd.date_range('2020-01', '2020-03', freq='MS')
        events = pd.Series([1, 0, 2], index=dates)
        index_vals = pd.Series([0.5, -0.2, 0.8], index=dates)
        
        events_ts = TimeSeriesData(events, "events")
        index_ts = TimeSeriesData(index_vals, "index")
        
        config = TeleconnectionConfig(min_observations=24)
        analyzer = LagCorrelationAnalyzer(config)
        
        result = analyzer.calculate_correlation(events_ts, index_ts, lag=1)
        
        assert result is None
    
    def test_analyze_lag_range(self, sample_data):
        """Test analyse sur gamme de décalages."""
        events_ts, index_ts = sample_data
        
        config = TeleconnectionConfig(max_lag=4, min_observations=20)
        analyzer = LagCorrelationAnalyzer(config)
        
        results = analyzer.analyze_lag_range(events_ts, index_ts)
        
        assert isinstance(results, dict)
        assert 0 in results  # Lag 0 doit être présent
        assert len(results) <= 5  # Max 5 lags (0-4)
        
        for lag, result in results.items():
            assert isinstance(result, CorrelationResult)
            assert result.lag == lag
    
    def test_find_optimal_lag(self, sample_data):
        """Test identification du lag optimal."""
        events_ts, index_ts = sample_data
        
        config = TeleconnectionConfig(max_lag=4)
        analyzer = LagCorrelationAnalyzer(config)
        
        lag_results = analyzer.analyze_lag_range(events_ts, index_ts)
        optimal = analyzer.find_optimal_lag(lag_results)
        
        assert optimal is not None
        assert isinstance(optimal, CorrelationResult)
        # Le lag optimal devrait être 2 (corrélation artificielle)
        assert optimal.lag == 2
    
    def test_find_optimal_lag_empty(self):
        """Test avec résultats vides."""
        config = TeleconnectionConfig()
        analyzer = LagCorrelationAnalyzer(config)
        
        optimal = analyzer.find_optimal_lag({})
        assert optimal is None


class TestSeasonalTeleconnectionAnalyzer:
    """Tests pour l'analyseur saisonnier."""
    
    @pytest.fixture
    def seasonal_data(self):
        """Données avec pattern saisonnier."""
        dates = pd.date_range('2010-01', '2020-12', freq='MS')
        
        # Événements concentrés en saison des pluies
        events = np.zeros(len(dates))
        for i, date in enumerate(dates):
            if date.month in [6, 7, 8, 9]:  # Saison des pluies
                events[i] = np.random.poisson(2)
            else:
                events[i] = np.random.poisson(0.2)
        
        # Indice avec corrélation saisonnière
        index_values = np.random.normal(0, 1, len(dates))
        
        events_ts = TimeSeriesData(pd.Series(events, index=dates), "events")
        index_ts = TimeSeriesData(pd.Series(index_values, index=dates), "index")
        
        return events_ts, index_ts
    
    def test_analyze_phase(self, seasonal_data):
        """Test analyse d'une phase spécifique."""
        events_ts, index_ts = seasonal_data
        
        config = TeleconnectionConfig(min_observations=10)
        lag_analyzer = LagCorrelationAnalyzer(config)
        seasonal_analyzer = SeasonalTeleconnectionAnalyzer(lag_analyzer)
        
        # Analyser la phase pleine saison (Juillet-Août)
        result = seasonal_analyzer.analyze_phase(
            events_ts, index_ts, [7, 8], optimal_lag=1
        )
        
        # Avec suffisamment de données, devrait retourner un résultat
        assert result is not None
        assert isinstance(result, CorrelationResult)
    
    def test_analyze_all_phases(self, seasonal_data):
        """Test analyse de toutes les phases."""
        events_ts, index_ts = seasonal_data
        
        config = TeleconnectionConfig(min_observations=10)
        lag_analyzer = LagCorrelationAnalyzer(config)
        seasonal_analyzer = SeasonalTeleconnectionAnalyzer(lag_analyzer)
        
        results = seasonal_analyzer.analyze_all_phases(
            events_ts, index_ts, optimal_lag=1
        )
        
        assert isinstance(results, dict)
        # Devrait avoir des résultats pour les 3 phases
        expected_phases = ['phase_1_debut', 'phase_2_pleine', 'phase_3_fin']
        
        for phase in expected_phases:
            if phase in results:
                assert isinstance(results[phase], CorrelationResult)


class TestTeleconnectionsAnalyzer:
    """Tests pour l'orchestrateur principal."""
    
    @pytest.fixture
    def sample_files(self):
        """Crée des fichiers temporaires pour les tests."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Fichier d'événements
            dates = pd.date_range('2010-01', '2020-12', freq='MS')
            events = pd.Series(np.random.poisson(0.5, len(dates)), index=dates)
            events_file = temp_path / "events.csv"
            events.to_csv(events_file, header=True)
            
            # Fichier d'indices
            indices_df = pd.DataFrame({
                'IOD': np.random.normal(0, 1, len(dates)),
                'Nino34': np.random.normal(0, 0.8, len(dates)),
                'TNA': np.random.normal(0, 0.6, len(dates))
            }, index=dates)
            indices_file = temp_path / "indices.csv"
            indices_df.to_csv(indices_file)
            
            yield events_file, indices_file
    
    def test_load_events_data_from_file(self, sample_files):
        """Test chargement d'événements depuis fichier."""
        events_file, _ = sample_files
        
        analyzer = TeleconnectionsAnalyzer()
        analyzer.load_events_data(events_file)
        
        assert analyzer.events_data is not None
        assert analyzer.events_data.name == "extreme_events"
        assert len(analyzer.events_data.data) > 0
    
    def test_load_events_data_from_series(self):
        """Test chargement d'événements depuis Series."""
        dates = pd.date_range('2015-01', '2020-12', freq='MS')
        events = pd.Series(np.random.poisson(0.8, len(dates)), index=dates)
        
        analyzer = TeleconnectionsAnalyzer()
        analyzer.load_events_data(events)
        
        assert analyzer.events_data is not None
        assert len(analyzer.events_data.data) == len(events)
    
    def test_load_climate_indices_from_file(self, sample_files):
        """Test chargement d'indices depuis fichier."""
        _, indices_file = sample_files
        
        analyzer = TeleconnectionsAnalyzer()
        analyzer.load_climate_indices(indices_file)
        
        assert len(analyzer.indices_data) == 3
        assert 'IOD' in analyzer.indices_data
        assert 'Nino34' in analyzer.indices_data
        assert 'TNA' in analyzer.indices_data
    
    def test_run_complete_analysis(self, sample_files):
        """Test analyse complète."""
        events_file, indices_file = sample_files
        
        analyzer = TeleconnectionsAnalyzer()
        results = analyzer.run_complete_analysis(events_file, indices_file)
        
        assert results['status'] == 'success'
        assert 'summary' in results
        assert 'lag_results' in results
        assert 'optimal_lags' in results
        assert 'seasonal_results' in results
        
        # Vérifier que les analyses ont été effectuées
        assert len(analyzer.lag_results) > 0
        assert len(analyzer.optimal_lags) > 0
    
    def test_get_summary_statistics(self, sample_files):
        """Test génération des statistiques de résumé."""
        events_file, indices_file = sample_files
        
        analyzer = TeleconnectionsAnalyzer()
        analyzer.run_complete_analysis(events_file, indices_file)
        
        summary = analyzer.get_summary_statistics()
        
        assert 'indices_analyzed' in summary
        assert 'significant_teleconnections' in summary
        assert 'analysis_period' in summary
        assert summary['indices_analyzed'] == 3


class TestQuickFunctions:
    """Tests pour les fonctions de convenance."""
    
    def test_quick_teleconnection_analysis(self):
        """Test analyse rapide."""
        np.random.seed(123)
        
        # Données synthétiques
        dates = pd.date_range('2000-01', '2020-12', freq='MS')
        events = pd.Series(np.random.poisson(0.6, len(dates)), index=dates)
        
        indices_df = pd.DataFrame({
            'IOD': np.random.normal(0, 1, len(dates)),
            'Nino34': np.random.normal(0, 0.8, len(dates))
        }, index=dates)
        
        results = quick_teleconnection_analysis(events, indices_df, max_lag=3)
        
        assert isinstance(results, dict)
        assert 'IOD' in results
        assert 'Nino34' in results
        
        for index_name, result in results.items():
            assert 'correlation' in result
            assert 'lag' in result
            assert 'significant' in result
            assert isinstance(result['correlation'], float)
            assert isinstance(result['lag'], int)
            assert isinstance(result['significant'], bool)


class TestTeleconnectionsVisualizer:
    """Tests pour le module de visualisation."""
    
    @pytest.fixture
    def mock_analyzer(self):
        """Analyseur avec résultats mockés."""
        analyzer = TeleconnectionsAnalyzer()
        
        # Mock des résultats de lag
        analyzer.lag_results = {
            'IOD': {
                0: CorrelationResult(0.15, 0.3, 100, 0),
                1: CorrelationResult(0.25, 0.15, 98, 1),
                2: CorrelationResult(0.45, 0.01, 96, 2)
            },
            'Nino34': {
                0: CorrelationResult(-0.12, 0.4, 100, 0),
                1: CorrelationResult(-0.35, 0.02, 98, 1),
                2: CorrelationResult(-0.28, 0.08, 96, 2)
            }
        }
        
        # Mock des lags optimaux
        analyzer.optimal_lags = {
            'IOD': CorrelationResult(0.45, 0.01, 96, 2),
            'Nino34': CorrelationResult(-0.35, 0.02, 98, 1)
        }
        
        # Mock des résultats saisonniers
        analyzer.seasonal_results = {
            'IOD': {
                'phase_1_debut': CorrelationResult(0.32, 0.04, 25, 2),
                'phase_2_pleine': CorrelationResult(0.51, 0.007, 28, 2)
            },
            'Nino34': {
                'phase_1_debut': CorrelationResult(-0.28, 0.08, 25, 1),
                'phase_2_pleine': CorrelationResult(-0.42, 0.015, 28, 1)
            }
        }
        
        return analyzer
    
    def test_create_correlation_heatmap(self, mock_analyzer):
        """Test création heatmap."""
        with tempfile.TemporaryDirectory() as temp_dir:
            visualizer = TeleconnectionsVisualizer(Path(temp_dir))
            
            output_path = visualizer.create_correlation_heatmap(
                mock_analyzer.lag_results,
                title="Test Heatmap"
            )
            
            assert Path(output_path).exists()
            assert Path(output_path).suffix == '.png'
    
    def test_create_optimal_lags_plot(self, mock_analyzer):
        """Test graphique lags optimaux."""
        with tempfile.TemporaryDirectory() as temp_dir:
            visualizer = TeleconnectionsVisualizer(Path(temp_dir))
            
            output_path = visualizer.create_optimal_lags_plot(
                mock_analyzer.optimal_lags,
                title="Test Optimal Lags"
            )
            
            assert Path(output_path).exists()
            assert Path(output_path).suffix == '.png'
    
    def test_create_seasonal_comparison(self, mock_analyzer):
        """Test comparaison saisonnière."""
        with tempfile.TemporaryDirectory() as temp_dir:
            visualizer = TeleconnectionsVisualizer(Path(temp_dir))
            
            output_path = visualizer.create_seasonal_comparison(
                mock_analyzer.seasonal_results,
                title="Test Seasonal"
            )
            
            assert Path(output_path).exists()
            assert Path(output_path).suffix == '.png'
    
    def test_generate_all_plots(self, mock_analyzer):
        """Test génération de tous les graphiques."""
        with tempfile.TemporaryDirectory() as temp_dir:
            visualizer = TeleconnectionsVisualizer(Path(temp_dir))
            
            generated_files = visualizer.generate_all_plots(mock_analyzer)
            
            assert len(generated_files) > 0
            for file_path in generated_files:
                if file_path:  # Filtrer les chaînes vides
                    assert Path(file_path).exists()


class TestTeleconnectionsReporter:
    """Tests pour le module de rapports."""
    
    @pytest.fixture
    def mock_analyzer_with_data(self):
        """Analyseur avec données pour rapports."""
        analyzer = TeleconnectionsAnalyzer()
        
        # Mock des données basiques
        dates = pd.date_range('2010-01', '2020-12', freq='MS')
        events = pd.Series(np.random.poisson(0.5, len(dates)), index=dates)
        analyzer.events_data = TimeSeriesData(events, "extreme_events")
        
        indices_data = {
            'IOD': TimeSeriesData(pd.Series(np.random.normal(0, 1, len(dates)), index=dates), 'IOD'),
            'Nino34': TimeSeriesData(pd.Series(np.random.normal(0, 0.8, len(dates)), index=dates), 'Nino34')
        }
        analyzer.indices_data = indices_data
        
        # Mock des résultats
        analyzer.optimal_lags = {
            'IOD': CorrelationResult(0.45, 0.01, 96, 2),
            'Nino34': CorrelationResult(-0.35, 0.02, 98, 1)
        }
        
        analyzer.seasonal_results = {
            'IOD': {
                'phase_2_pleine': CorrelationResult(0.51, 0.007, 28, 2)
            }
        }
        
        return analyzer
    
    def test_generate_complete_report(self, mock_analyzer_with_data):
        """Test génération rapport complet."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = TeleconnectionsReporter(Path(temp_dir))
            
            report_path = reporter.generate_complete_report(mock_analyzer_with_data)
            
            assert Path(report_path).exists()
            
            # Vérifier le contenu
            with open(report_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            assert 'TÉLÉCONNEXIONS CLIMATIQUES' in content.upper()
            assert 'RÉSULTATS' in content.upper()
            assert 'IOD' in content
            assert 'Nino34' in content
    
    def test_generate_summary_report(self, mock_analyzer_with_data):
        """Test génération rapport de résumé."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = TeleconnectionsReporter(Path(temp_dir))
            
            summary_path = reporter.generate_summary_report(mock_analyzer_with_data)
            
            assert Path(summary_path).exists()
            
            with open(summary_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            assert 'RÉSUMÉ' in content.upper()
            assert len(content) < 2000  # Résumé doit être concis
    
    def test_export_json_results(self, mock_analyzer_with_data):
        """Test export JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = TeleconnectionsReporter(Path(temp_dir))
            
            json_path = reporter.export_json_results(mock_analyzer_with_data)
            
            assert Path(json_path).exists()
            
            # Vérifier la structure JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            assert 'metadata' in data
            assert 'summary' in data
            assert 'results' in data
            assert 'optimal_lags' in data['results']
            assert 'seasonal_analysis' in data['results']
    
    def test_create_executive_summary_managers(self, mock_analyzer_with_data):
        """Test résumé pour managers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = TeleconnectionsReporter(Path(temp_dir))
            
            exec_path = reporter.create_executive_summary(
                mock_analyzer_with_data, 'managers'
            )
            
            assert Path(exec_path).exists()
            
            with open(exec_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            assert 'EXÉCUTIF' in content.upper()
            assert 'IMPACT OPÉRATIONNEL' in content.upper()
            assert 'BUDGET' in content.upper()
    
    def test_generate_all_reports(self, mock_analyzer_with_data):
        """Test génération de tous les rapports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = TeleconnectionsReporter(Path(temp_dir))
            
            generated_files = reporter.generate_all_reports(mock_analyzer_with_data)
            
            assert 'complete_report' in generated_files
            assert 'summary_report' in generated_files
            assert 'json_results' in generated_files
            assert 'executive_researchers' in generated_files
            assert 'executive_managers' in generated_files
            assert 'executive_operators' in generated_files
            
            # Vérifier que tous les fichiers existent
            for file_path in generated_files.values():
                assert Path(file_path).exists()


class TestIntegration:
    """Tests d'intégration pour le workflow complet."""
    
    def test_complete_workflow_with_synthetic_data(self):
        """Test workflow complet avec données synthétiques."""
        np.random.seed(456)
        
        # Créer données synthétiques réalistes
        dates = pd.date_range('2000-01', '2020-12', freq='MS')
        n_months = len(dates)
        
        # Événements avec saisonnalité
        events = np.random.poisson(0.3, n_months)
        for i, date in enumerate(dates):
            if date.month in [6, 7, 8, 9]:  # Saison des pluies
                events[i] += np.random.poisson(1.0)
        
        events_series = pd.Series(events, index=dates)
        
        # Indices avec téléconnexions artificielles
        iod = np.random.normal(0, 1, n_months)
        nino34 = np.random.normal(0, 0.8, n_months)
        
        # Introduire corrélation IOD avec lag=3
        for i in range(3, n_months):
            iod[i-3] += 0.4 * (events[i] - events.mean()) / events.std()
        
        indices_df = pd.DataFrame({
            'IOD': iod,
            'Nino34': nino34
        }, index=dates)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Analyser
            config = TeleconnectionConfig(max_lag=6, min_observations=20)
            analyzer = TeleconnectionsAnalyzer(config)
            
            results = analyzer.run_complete_analysis(events_series, indices_df)
            
            # Vérifications
            assert results['status'] == 'success'
            assert results['summary']['indices_analyzed'] == 2
            
            # Le lag optimal pour IOD devrait être proche de 3
            if 'IOD' in analyzer.optimal_lags:
                optimal_iod = analyzer.optimal_lags['IOD']
                assert 2 <= optimal_iod.lag <= 4  # Tolérance
                assert optimal_iod.correlation > 0.2  # Corrélation notable
            
            # Générer visualisations
            visualizer = TeleconnectionsVisualizer(temp_path / "plots")
            plot_files = visualizer.generate_all_plots(analyzer)
            assert len(plot_files) > 0
            
            # Générer rapports
            reporter = TeleconnectionsReporter(temp_path / "reports")
            report_files = reporter.generate_all_reports(analyzer)
            assert len(report_files) > 0
            
            # Vérifier que les fichiers principaux existent
            assert Path(report_files['complete_report']).exists()
            assert Path(report_files['json_results']).exists()
    
    def test_error_handling_invalid_data(self):
        """Test gestion d'erreurs avec données invalides."""
        analyzer = TeleconnectionsAnalyzer()
        
        # Test avec fichier inexistant
        results = analyzer.run_complete_analysis(
            "nonexistent_events.csv",
            "nonexistent_indices.csv"
        )
        
        assert results['status'] == 'error'
        assert 'message' in results
    
    def test_performance_with_large_dataset(self):
        """Test performance avec dataset volumineux."""
        np.random.seed(789)
        
        # Dataset plus volumineux (50 ans)
        dates = pd.date_range('1970-01', '2020-12', freq='MS')
        n_months = len(dates)
        
        events = pd.Series(np.random.poisson(0.5, n_months), index=dates)
        
        indices_df = pd.DataFrame({
            'IOD': np.random.normal(0, 1, n_months),
            'Nino34': np.random.normal(0, 0.8, n_months),
            'TNA': np.random.normal(0, 0.6, n_months),
            'AMO': np.random.normal(0, 0.4, n_months)
        }, index=dates)
        
        # Mesurer le temps d'exécution
        start_time = datetime.now()
        
        analyzer = TeleconnectionsAnalyzer()
        results = analyzer.run_complete_analysis(events, indices_df)
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        # Vérifications
        assert results['status'] == 'success'
        assert execution_time < 60  # Moins de 60 secondes
        assert results['summary']['indices_analyzed'] == 4
        
        print(f"Temps d'exécution pour 50 ans de données: {execution_time:.2f}s")


class TestEdgeCases:
    """Tests des cas limites et edge cases."""
    
    def test_single_observation(self):
        """Test avec une seule observation."""
        dates = pd.date_range('2020-01', '2020-01', freq='MS')
        events = pd.Series([1], index=dates)
        indices = pd.DataFrame({'IOD': [0.5]}, index=dates)
        
        analyzer = TeleconnectionsAnalyzer()
        results = analyzer.run_complete_analysis(events, indices)
        
        # Devrait gérer gracieusement les données insuffisantes
        assert results['status'] == 'success'
        assert results['summary']['significant_teleconnections'] == 0
    
    def test_all_nan_values(self):
        """Test avec toutes valeurs NaN."""
        dates = pd.date_range('2020-01', '2020-12', freq='MS')
        events = pd.Series([np.nan] * 12, index=dates)
        indices = pd.DataFrame({'IOD': [np.nan] * 12}, index=dates)
        
        analyzer = TeleconnectionsAnalyzer()
        results = analyzer.run_complete_analysis(events, indices)
        
        assert results['status'] == 'success'
        assert len(analyzer.optimal_lags) == 0
    
    def test_perfect_correlation(self):
        """Test avec corrélation parfaite."""
        dates = pd.date_range('2000-01', '2020-12', freq='MS')
        events = pd.Series(np.random.randn(len(dates)), index=dates)
        
        # Créer corrélation parfaite avec lag=1
        perfect_index = events.shift(1).fillna(0)
        indices = pd.DataFrame({'Perfect': perfect_index}, index=dates)
        
        analyzer = TeleconnectionsAnalyzer()
        results = analyzer.run_complete_analysis(events, indices)
        
        assert results['status'] == 'success'
        
        if 'Perfect' in analyzer.optimal_lags:
            optimal = analyzer.optimal_lags['Perfect']
            assert abs(optimal.correlation) > 0.95  # Quasi-parfait
            assert optimal.lag == 1
    
    def test_zero_variance_data(self):
        """Test avec données de variance nulle."""
        dates = pd.date_range('2020-01', '2020-12', freq='MS')
        events = pd.Series([1] * 12, index=dates)  # Variance nulle
        indices = pd.DataFrame({'Constant': [0.5] * 12}, index=dates)
        
        analyzer = TeleconnectionsAnalyzer()
        results = analyzer.run_complete_analysis(events, indices)
        
        # Doit gérer les données constantes
        assert results['status'] == 'success'


# ============================================================================
# CONFIGURATION DES TESTS
# ============================================================================

@pytest.fixture(scope="session")
def test_data_directory():
    """Répertoire pour les données de test."""
    test_dir = Path("tests/data")
    test_dir.mkdir(exist_ok=True)
    return test_dir


def pytest_configure(config):
    """Configuration pytest."""
    # Supprimer les warnings matplotlib dans les tests
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
    warnings.filterwarnings("ignore", category=FutureWarning)


# ============================================================================
# HELPERS POUR LES TESTS
# ============================================================================

def create_realistic_teleconnection_data(
    start_date: str = '2000-01',
    end_date: str = '2020-12',
    correlation_strength: float = 0.4,
    lag_months: int = 3,
    noise_level: float = 0.3
) -> tuple:
    """
    Crée des données réalistes avec téléconnexion contrôlée.
    
    Args:
        start_date: Date de début
        end_date: Date de fin
        correlation_strength: Force de la corrélation (-1 à 1)
        lag_months: Décalage en mois
        noise_level: Niveau de bruit (0 à 1)
        
    Returns:
        Tuple (events_series, indices_dataframe)
    """
    dates = pd.date_range(start_date, end_date, freq='MS')
    n_months = len(dates)
    
    # Base des événements avec saisonnalité
    base_events = np.random.poisson(0.5, n_months)
    for i, date in enumerate(dates):
        if date.month in [6, 7, 8, 9]:  # Saison des pluies
            base_events[i] += np.random.poisson(1.2)
    
    # Indice climatique de base
    base_index = np.random.normal(0, 1, n_months)
    
    # Introduire téléconnexion avec lag
    teleconnected_index = base_index.copy()
    for i in range(lag_months, n_months):
        signal = correlation_strength * (base_events[i] - np.mean(base_events))
        teleconnected_index[i - lag_months] += signal
    
    # Ajouter du bruit
    teleconnected_index += np.random.normal(0, noise_level, n_months)
    
    events_series = pd.Series(base_events, index=dates)
    indices_df = pd.DataFrame({
        'TestIndex': teleconnected_index,
        'NoiseIndex': np.random.normal(0, 1, n_months)  # Indice sans corrélation
    }, index=dates)
    
    return events_series, indices_df


def assert_correlation_result_valid(result: CorrelationResult):
    """Valide qu'un CorrelationResult est cohérent."""
    assert -1 <= result.correlation <= 1
    assert 0 <= result.p_value <= 1
    assert result.n_observations > 0
    assert result.lag >= 0
    assert isinstance(result.significant, bool)


if __name__ == "__main__":
    print("=== TESTS UNITAIRES TÉLÉCONNEXIONS ===")
    print("Exécution:")
    print("  pytest tests/test_teleconnections.py -v")
    print("  pytest tests/test_teleconnections.py::TestLagCorrelationAnalyzer -v")
    print("  pytest tests/test_teleconnections.py --cov=src.analysis.teleconnections")
    print()
    print("Coverage:")
    print("  pytest --cov=src --cov-report=html")
    print()
    print("Classes testées:")
    print("  • TimeSeriesData")
    print("  • CorrelationResult") 
    print("  • LagCorrelationAnalyzer")
    print("  • SeasonalTeleconnectionAnalyzer")
    print("  • TeleconnectionsAnalyzer")
    print("  • TeleconnectionsVisualizer")
    print("  • TeleconnectionsReporter")
    print("  • Workflow complet d'intégration")
    print("=======================================")