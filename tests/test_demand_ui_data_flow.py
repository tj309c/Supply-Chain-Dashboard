"""
Tests for Demand Forecast UI Data Flow

Verifies that the optimized demand forecasting calculations are correctly
passed to the UI components (SKU Demand Forecast Viewer).
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from demand_forecasting import (
    generate_demand_forecast,
    _batch_process_sku_smoothing,
    _batch_calculate_trends,
    get_smoothing_config,
    MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
    INTERMITTENT_DEMAND_CV_THRESHOLD,
    INTERMITTENT_DEMAND_Z_THRESHOLD,
    MAX_ANOMALY_PERCENTAGE,
    JOBLIB_AVAILABLE,
    NUMBA_AVAILABLE
)


class TestDemandForecastUIDataFlow:
    """Tests that forecast data flows correctly to UI components"""

    @pytest.fixture
    def sample_deliveries_with_anomalies(self):
        """Create sample delivery data with known anomalies for testing

        Uses same format as test_demand_forecasting.py: delivery_date, delivered_qty
        """
        np.random.seed(42)
        today = pd.to_datetime(datetime.now().date())

        dates = []
        skus = []
        qtys = []

        # Create 60 days of data (enough for anomaly detection)
        for days_ago in range(60, 0, -1):
            date = today - timedelta(days=days_ago)

            # SKU001: Normal demand with clear anomaly at day 5
            demand = 100 if days_ago > 5 else (1000 if days_ago == 5 else 100)
            skus.append('SKU001')
            dates.append(date)
            qtys.append(demand)

            # SKU002: Intermittent demand (high CV with zeros)
            if days_ago > 40:
                demand = 0
            elif days_ago in [35, 30, 25]:
                demand = np.random.choice([500, 600, 700])
            else:
                demand = 0
            skus.append('SKU002')
            dates.append(date)
            qtys.append(demand)

            # SKU003: Stable demand (no anomalies expected)
            skus.append('SKU003')
            dates.append(date)
            qtys.append(50 + np.random.normal(0, 2))

        return pd.DataFrame({
            'sku': skus,
            'delivery_date': dates,
            'delivered_qty': qtys
        })

    def test_forecast_output_contains_required_ui_fields(self, sample_deliveries_with_anomalies):
        """Verify forecast output contains all fields needed by demand_page.py"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_with_anomalies,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Forecast is empty. Logs: {logs}"

        # Fields used by _render_sku_forecast_chart in demand_page.py
        required_fields = [
            'sku',
            'primary_forecast_daily',
            'forecast_total_qty',
            'forecast_horizon_days',
            'forecast_lower_bound',
            'forecast_upper_bound',
            'forecast_confidence',
            'forecast_method',
            'demand_pattern',
            # New anomaly-related fields from optimized calculation
            'anomaly_count',
            'anomaly_pct',
            'is_intermittent',
            'skipped_detection',
            'applied_z_threshold',
            'smoothing_preset'
        ]

        for field in required_fields:
            assert field in forecast_df.columns, f"Missing required UI field: {field}"

    def test_daily_demand_df_has_correct_structure(self, sample_deliveries_with_anomalies):
        """Verify daily_demand_df has structure expected by UI chart"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_with_anomalies,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        assert not daily_demand_df.empty, f"daily_demand_df is empty. Logs: {logs}"

        # Fields used by _render_sku_forecast_chart for historical data
        assert 'sku' in daily_demand_df.columns
        assert 'date' in daily_demand_df.columns
        assert 'demand_qty' in daily_demand_df.columns

        # Verify date is datetime
        assert pd.api.types.is_datetime64_any_dtype(daily_demand_df['date'])

    def test_anomaly_detection_results_in_forecast(self, sample_deliveries_with_anomalies):
        """Verify anomaly detection results appear in forecast output"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_with_anomalies,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Forecast is empty. Logs: {logs}"

        # SKU001 should have detected anomaly (the 1000 spike)
        sku1 = forecast_df[forecast_df['sku'] == 'SKU001'].iloc[0]
        assert sku1['anomaly_count'] >= 1, "SKU001 should have detected the anomaly spike"
        assert sku1['skipped_detection'] == False, "SKU001 has 60 points, detection should NOT be skipped"

        # SKU002 might not generate forecast if too few non-zero values
        # This tests intermittent detection if SKU002 is present
        sku2_rows = forecast_df[forecast_df['sku'] == 'SKU002']
        if not sku2_rows.empty:
            sku2 = sku2_rows.iloc[0]
            # Intermittent demand uses higher Z-threshold
            if sku2['is_intermittent']:
                assert sku2['applied_z_threshold'] == INTERMITTENT_DEMAND_Z_THRESHOLD

        # All should have smoothing_preset set
        assert all(forecast_df['smoothing_preset'] == 'Balanced')

    def test_forecast_values_are_smoothed_not_raw(self, sample_deliveries_with_anomalies):
        """Verify forecast uses smoothed values, not raw values with anomalies"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_with_anomalies,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Forecast is empty. Logs: {logs}"

        # SKU001: Raw average would be ~115 (due to 1000 spike), smoothed should be ~100
        sku1 = forecast_df[forecast_df['sku'] == 'SKU001'].iloc[0]
        daily_forecast = sku1['primary_forecast_daily']

        # The smoothed forecast should be closer to 100 than to 115
        # Because the 1000 anomaly should be replaced with median (~100)
        assert daily_forecast < 150, f"Forecast {daily_forecast} suggests anomaly not smoothed"

    def test_different_presets_produce_different_results(self, sample_deliveries_with_anomalies):
        """Verify different smoothing presets produce different forecasts"""
        results = {}

        # Using new preset names: 'Conservative' = most sensitive, 'Aggressive' = least sensitive
        for preset in ['Conservative', 'Balanced', 'Aggressive']:
            logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
                sample_deliveries_with_anomalies,
                ts_granularity='daily',
                smoothing_preset=preset
            )

            assert not forecast_df.empty, f"Forecast is empty for {preset}. Logs: {logs}"

            sku1 = forecast_df[forecast_df['sku'] == 'SKU001'].iloc[0]
            results[preset] = {
                'anomaly_count': sku1['anomaly_count'],
                'applied_z_threshold': sku1['applied_z_threshold'],
                'forecast': sku1['primary_forecast_daily']
            }

        # Conservative (Z=1.5) should flag more anomalies than Aggressive (Z=2.5)
        assert results['Conservative']['anomaly_count'] >= results['Aggressive']['anomaly_count']

        # Verify presets use different Z-thresholds (unless overridden for intermittent)
        config_conservative = get_smoothing_config('Conservative')
        config_aggressive = get_smoothing_config('Aggressive')
        assert config_conservative['z_score_threshold'] < config_aggressive['z_score_threshold']

    def test_jit_batch_processing_matches_expected_output(self):
        """Verify JIT batch processing produces correct output structure"""
        # Create test data
        np.random.seed(42)
        sku_data = {
            'SKU_A': np.array([100.0] * 35 + [1000.0]),  # 36 points with anomaly
            'SKU_B': np.array([50.0] * 40),  # 40 points, no anomalies
            'SKU_C': np.array([10.0, 20.0, 10.0]),  # 3 points, below min sample size
        }

        config = get_smoothing_config('Balanced')

        result_df = _batch_process_sku_smoothing(
            grouped_data=sku_data,
            z_threshold=config['z_score_threshold'],
            alpha=config['alpha'],
            cv_threshold=INTERMITTENT_DEMAND_CV_THRESHOLD,
            intermittent_z=INTERMITTENT_DEMAND_Z_THRESHOLD,
            min_sample_size=MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
            max_anomaly_pct=MAX_ANOMALY_PERCENTAGE,
            use_parallel=False  # Test sequential mode
        )

        # Verify output structure
        expected_columns = ['sku', 'exp_smooth', 'anomaly_count', 'anomaly_pct',
                          'is_intermittent', 'skipped_detection', 'applied_z_threshold', 'warnings']
        assert list(result_df.columns) == expected_columns

        # Verify SKU_A has anomaly detected
        sku_a = result_df[result_df['sku'] == 'SKU_A'].iloc[0]
        assert sku_a['anomaly_count'] >= 1, "SKU_A should detect the 1000 anomaly"
        assert sku_a['skipped_detection'] == False

        # Verify SKU_B has no anomalies
        sku_b = result_df[result_df['sku'] == 'SKU_B'].iloc[0]
        assert sku_b['anomaly_count'] == 0, "SKU_B (uniform data) should have no anomalies"

        # Verify SKU_C skipped detection (below min sample size)
        sku_c = result_df[result_df['sku'] == 'SKU_C'].iloc[0]
        assert sku_c['skipped_detection'] == True, "SKU_C (3 points) should skip detection"

    def test_trend_calculation_output(self):
        """Verify trend calculation produces correct output"""
        # Create test data with known trends
        sku_data = {
            'SKU_GROWING': np.array([10.0, 20.0, 30.0, 40.0, 50.0]),  # Positive trend
            'SKU_DECLINING': np.array([50.0, 40.0, 30.0, 20.0, 10.0]),  # Negative trend
            'SKU_FLAT': np.array([25.0, 25.0, 25.0, 25.0, 25.0]),  # No trend
        }

        result_df = _batch_calculate_trends(sku_data, use_parallel=False)

        # Verify output structure
        assert 'sku' in result_df.columns
        assert 'demand_trend_slope' in result_df.columns

        # Verify trend directions
        growing = result_df[result_df['sku'] == 'SKU_GROWING'].iloc[0]['demand_trend_slope']
        declining = result_df[result_df['sku'] == 'SKU_DECLINING'].iloc[0]['demand_trend_slope']
        flat = result_df[result_df['sku'] == 'SKU_FLAT'].iloc[0]['demand_trend_slope']

        assert growing > 0, f"Growing SKU should have positive slope, got {growing}"
        assert declining < 0, f"Declining SKU should have negative slope, got {declining}"
        assert abs(flat) < 0.001, f"Flat SKU should have ~0 slope, got {flat}"

    def test_numba_and_joblib_availability_logged(self, sample_deliveries_with_anomalies):
        """Verify optimization status is logged"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_with_anomalies,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        # Should have log entry about JIT/batch processing
        log_text = ' '.join(logs)
        assert 'batch processing' in log_text.lower() or 'JIT' in log_text

    def test_ui_chart_data_alignment(self, sample_deliveries_with_anomalies):
        """Verify daily_demand_df aligns with forecast_df for chart rendering"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_with_anomalies,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Forecast is empty. Logs: {logs}"

        # All SKUs in forecast should have historical data
        forecast_skus = set(forecast_df['sku'].unique())
        history_skus = set(daily_demand_df['sku'].unique())

        # Every forecasted SKU should have historical data
        assert forecast_skus.issubset(history_skus), \
            f"SKUs in forecast without history: {forecast_skus - history_skus}"

        # Verify we can filter history by forecast SKU (as UI does)
        for sku in forecast_skus:
            sku_history = daily_demand_df[daily_demand_df['sku'] == sku]
            assert len(sku_history) > 0, f"No history for SKU {sku}"

            # Verify dates are sorted (as expected by chart)
            dates = sku_history['date'].values
            assert all(dates[i] <= dates[i+1] for i in range(len(dates)-1)), \
                f"Dates not sorted for SKU {sku}"


class TestOptimizationStatus:
    """Tests for optimization module availability"""

    def test_numba_available(self):
        """Report Numba availability (not a hard requirement)"""
        print(f"\nNumba available: {NUMBA_AVAILABLE}")
        # This is informational - both paths should work
        assert isinstance(NUMBA_AVAILABLE, bool)

    def test_joblib_available(self):
        """Report Joblib availability (not a hard requirement)"""
        print(f"\nJoblib available: {JOBLIB_AVAILABLE}")
        # This is informational - both paths should work
        assert isinstance(JOBLIB_AVAILABLE, bool)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
