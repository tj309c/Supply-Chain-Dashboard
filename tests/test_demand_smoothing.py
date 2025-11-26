"""
Tests for Demand Anomaly Detection and Smoothing

Tests the new smoothing functionality including:
- Smoothing preset configuration
- Z-score based anomaly detection with edge case handling
- Anomaly smoothing methods
- Full demand smoothing pipeline
- Integration with forecast generation
- Edge case handling (minimum sample size, intermittent demand, anomaly cap)
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Import the functions to test
from demand_forecasting import (
    SMOOTHING_PRESETS,
    DEFAULT_SMOOTHING_PRESET,
    MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
    MAX_ANOMALY_PERCENTAGE,
    INTERMITTENT_DEMAND_CV_THRESHOLD,
    INTERMITTENT_DEMAND_Z_THRESHOLD,
    get_smoothing_config,
    detect_anomalies,
    detect_anomalies_simple,
    smooth_anomalies,
    apply_demand_smoothing,
    apply_demand_smoothing_simple,
    calculate_exponential_smoothing,
    generate_demand_forecast
)


class TestSmoothingPresets:
    """Tests for smoothing preset configuration"""

    def test_default_preset_is_balanced(self):
        """Default smoothing preset should be 'Balanced'"""
        assert DEFAULT_SMOOTHING_PRESET == 'Balanced'

    def test_all_presets_exist(self):
        """All presets should be defined (3 presets: Conservative, Balanced, Aggressive)"""
        expected_presets = ['Conservative', 'Balanced', 'Aggressive']
        for preset in expected_presets:
            assert preset in SMOOTHING_PRESETS
        assert len(SMOOTHING_PRESETS) == 3

    def test_preset_has_required_keys(self):
        """Each preset should have z_score_threshold, alpha, and description"""
        required_keys = ['z_score_threshold', 'alpha', 'description']
        for preset_name, config in SMOOTHING_PRESETS.items():
            for key in required_keys:
                assert key in config, f"Preset '{preset_name}' missing key '{key}'"

    def test_conservative_has_lowest_threshold(self):
        """Conservative should flag more anomalies (lower Z threshold)"""
        assert SMOOTHING_PRESETS['Conservative']['z_score_threshold'] < SMOOTHING_PRESETS['Balanced']['z_score_threshold']
        assert SMOOTHING_PRESETS['Balanced']['z_score_threshold'] < SMOOTHING_PRESETS['Aggressive']['z_score_threshold']

    def test_conservative_has_lowest_alpha(self):
        """Conservative should have heaviest smoothing (lower alpha)"""
        assert SMOOTHING_PRESETS['Conservative']['alpha'] < SMOOTHING_PRESETS['Balanced']['alpha']
        assert SMOOTHING_PRESETS['Balanced']['alpha'] < SMOOTHING_PRESETS['Aggressive']['alpha']

    def test_alpha_values_in_valid_range(self):
        """Alpha values should be between 0 and 1"""
        for preset_name, config in SMOOTHING_PRESETS.items():
            assert 0 < config['alpha'] < 1, f"Preset '{preset_name}' has invalid alpha"

    def test_z_score_thresholds_positive(self):
        """Z-score thresholds should be positive"""
        for preset_name, config in SMOOTHING_PRESETS.items():
            assert config['z_score_threshold'] > 0, f"Preset '{preset_name}' has invalid threshold"


class TestGetSmoothingConfig:
    """Tests for get_smoothing_config function"""

    def test_returns_dict(self):
        """Should return a dictionary"""
        config = get_smoothing_config('Balanced')
        assert isinstance(config, dict)

    def test_valid_preset_returns_config(self):
        """Valid preset name should return its configuration"""
        config = get_smoothing_config('Conservative')
        assert config['z_score_threshold'] == 1.5
        assert config['alpha'] == 0.03

    def test_invalid_preset_returns_default(self):
        """Invalid preset name should return default (Balanced)"""
        config = get_smoothing_config('InvalidPreset')
        assert config['z_score_threshold'] == SMOOTHING_PRESETS['Balanced']['z_score_threshold']
        assert config['alpha'] == SMOOTHING_PRESETS['Balanced']['alpha']

    def test_none_preset_returns_default(self):
        """None preset should return default (Balanced)"""
        config = get_smoothing_config(None)
        assert config['z_score_threshold'] == SMOOTHING_PRESETS['Balanced']['z_score_threshold']

    def test_returns_copy_not_reference(self):
        """Should return a copy, not the original dict"""
        config = get_smoothing_config('Balanced')
        config['alpha'] = 999
        # Original should be unchanged
        assert SMOOTHING_PRESETS['Balanced']['alpha'] != 999


class TestDetectAnomalies:
    """Tests for detect_anomalies function - now returns dict with edge case handling"""

    def test_returns_dict_with_required_keys(self):
        """Should return a dict with all required keys"""
        # Need 30+ values to avoid skipping detection
        values = np.array([1, 2, 3, 4, 5] * 10)
        result = detect_anomalies(values, z_threshold=2.0)
        assert isinstance(result, dict)
        assert 'is_anomaly' in result
        assert 'anomaly_count' in result
        assert 'anomaly_pct' in result
        assert 'warnings' in result
        assert 'is_intermittent' in result
        assert 'skipped_detection' in result

    def test_same_length_as_input(self):
        """is_anomaly array should be same length as input"""
        values = np.array([1, 2, 3, 100, 5, 6, 7] * 5)  # 35 values
        result = detect_anomalies(values, z_threshold=2.0)
        assert len(result['is_anomaly']) == len(values)

    def test_detects_obvious_outlier(self):
        """Should detect an obvious outlier when sample size is sufficient"""
        # Need 30+ values for anomaly detection
        values = np.array([10] * 30 + [1000] + [10] * 5)
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['is_anomaly'][30] == True  # The outlier at index 30
        assert result['anomaly_count'] >= 1

    def test_no_anomalies_in_uniform_data(self):
        """Uniform data should have no anomalies"""
        values = np.array([5] * 50)
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['anomaly_count'] == 0

    def test_short_array_skips_detection(self):
        """Arrays below MIN_SAMPLE_SIZE should skip detection"""
        values = np.array([1, 100])
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['skipped_detection'] == True
        assert result['anomaly_count'] == 0
        assert len(result['warnings']) > 0

    def test_lower_threshold_flags_more(self):
        """Lower threshold should flag more anomalies"""
        # 40 values with variation
        values = np.array([10, 11, 9, 10, 15, 10, 9, 11, 12, 8] * 4)
        result_low = detect_anomalies(values, z_threshold=1.0, check_intermittent=False)
        result_high = detect_anomalies(values, z_threshold=3.0, check_intermittent=False)
        assert result_low['anomaly_count'] >= result_high['anomaly_count']

    def test_handles_zero_std(self):
        """Should handle zero standard deviation gracefully"""
        values = np.array([5] * 50)  # All same value, std=0
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['anomaly_count'] == 0

    def test_detects_both_high_and_low_outliers(self):
        """Should detect both high and low outliers"""
        # 35 normal values + 2 outliers
        values = np.array([10] * 35 + [1000, 0.001])
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['anomaly_count'] >= 1


class TestDetectAnomaliesEdgeCases:
    """Tests for edge case handling in detect_anomalies"""

    def test_minimum_sample_size_enforced(self):
        """Should skip detection when sample size < MIN_ANOMALY_DETECTION_SAMPLE_SIZE"""
        values = np.array([10] * 20 + [1000])  # 21 values < 30
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['skipped_detection'] == True
        assert 'Insufficient data' in result['warnings'][0]

    def test_intermittent_demand_uses_higher_threshold(self):
        """Should use higher Z-threshold for intermittent demand (CV > 150%)"""
        # Create intermittent demand pattern (many zeros + occasional large values)
        values = np.array([0] * 25 + [100, 0, 0, 0, 200, 0, 0, 0, 0, 300])  # 35 values, high CV
        result = detect_anomalies(values, z_threshold=2.0, check_intermittent=True)
        if result['is_intermittent']:
            assert result['applied_z_threshold'] == INTERMITTENT_DEMAND_Z_THRESHOLD
            assert any('Intermittent demand' in w for w in result['warnings'])

    def test_high_anomaly_rate_warning(self):
        """Should warn when anomaly rate exceeds MAX_ANOMALY_PERCENTAGE"""
        # Create data with >20% anomalies - alternate normal and extreme values
        normal_values = [10] * 25
        outlier_values = [1000] * 10  # >28% anomalies
        values = np.array(normal_values + outlier_values)
        result = detect_anomalies(values, z_threshold=1.5, check_intermittent=False)
        if result['anomaly_pct'] > MAX_ANOMALY_PERCENTAGE:
            assert any('High anomaly rate' in w for w in result['warnings'])

    def test_simple_function_returns_array(self):
        """detect_anomalies_simple should return just the boolean array"""
        values = np.array([10] * 35)
        result = detect_anomalies_simple(values, z_threshold=2.0)
        assert isinstance(result, np.ndarray)
        assert result.dtype == bool


class TestSmoothAnomalies:
    """Tests for smooth_anomalies function"""

    def test_returns_array_same_length(self):
        """Should return array of same length"""
        values = np.array([1, 2, 100, 4, 5])
        is_anomaly = np.array([False, False, True, False, False])
        result = smooth_anomalies(values, is_anomaly)
        assert len(result) == len(values)

    def test_no_change_when_no_anomalies(self):
        """Should not modify values when no anomalies"""
        values = np.array([1, 2, 3, 4, 5])
        is_anomaly = np.array([False, False, False, False, False])
        result = smooth_anomalies(values, is_anomaly)
        np.testing.assert_array_equal(result, values)

    def test_replaces_anomaly_with_median(self):
        """Should replace anomaly with median of non-anomalous values"""
        values = np.array([10.0, 10.0, 100.0, 10.0, 10.0])
        is_anomaly = np.array([False, False, True, False, False])
        result = smooth_anomalies(values, is_anomaly, method='median')
        # Median of [10, 10, 10, 10] is 10
        assert result[2] == 10.0

    def test_non_anomaly_values_unchanged(self):
        """Non-anomaly values should remain unchanged"""
        values = np.array([10.0, 20.0, 100.0, 30.0, 40.0])
        is_anomaly = np.array([False, False, True, False, False])
        result = smooth_anomalies(values, is_anomaly)
        assert result[0] == 10.0
        assert result[1] == 20.0
        assert result[3] == 30.0
        assert result[4] == 40.0

    def test_neighbor_method_uses_neighbors(self):
        """Neighbor method should use average of nearest neighbors"""
        values = np.array([10.0, 20.0, 100.0, 30.0, 40.0])
        is_anomaly = np.array([False, False, True, False, False])
        result = smooth_anomalies(values, is_anomaly, method='neighbor')
        # Index 2 should be average of index 1 (20) and index 3 (30)
        assert result[2] == 25.0


class TestApplyDemandSmoothing:
    """Tests for apply_demand_smoothing function - now returns dict"""

    def test_returns_dict_with_required_keys(self):
        """Should return dict with all required keys"""
        values = np.array([10, 11, 12, 100, 10, 11] * 6)  # 36 values
        result = apply_demand_smoothing(values, preset='Balanced')
        assert isinstance(result, dict)
        assert 'smoothed_forecast' in result
        assert 'anomaly_count' in result
        assert 'anomaly_pct' in result
        assert 'config' in result
        assert 'warnings' in result
        assert 'is_intermittent' in result
        assert 'skipped_detection' in result

    def test_smoothed_forecast_is_numeric(self):
        """smoothed_forecast should be a numeric value"""
        values = np.array([10, 11, 12, 100, 10, 11] * 6)
        result = apply_demand_smoothing(values, preset='Balanced')
        assert isinstance(result['smoothed_forecast'], (int, float, np.number))

    def test_anomaly_count_is_integer(self):
        """anomaly_count should be an integer"""
        values = np.array([10, 11, 12, 100, 10, 11] * 6)
        result = apply_demand_smoothing(values, preset='Balanced')
        assert isinstance(result['anomaly_count'], int)

    def test_config_is_dict(self):
        """config should be a dict with threshold and alpha"""
        values = np.array([10, 11, 12, 100, 10, 11] * 6)
        result = apply_demand_smoothing(values, preset='Balanced')
        assert isinstance(result['config'], dict)
        assert 'z_score_threshold' in result['config']
        assert 'alpha' in result['config']

    def test_empty_array_returns_zero(self):
        """Empty array should return 0 forecast and 0 anomalies"""
        values = np.array([])
        result = apply_demand_smoothing(values)
        assert result['smoothed_forecast'] == 0
        assert result['anomaly_count'] == 0

    def test_different_presets_give_different_configs(self):
        """Different presets should have different alpha values"""
        values = np.array([10] * 35 + [100])

        result_conservative = apply_demand_smoothing(values, preset='Conservative')
        result_aggressive = apply_demand_smoothing(values, preset='Aggressive')

        # Conservative should use lower alpha (heavier smoothing)
        assert result_conservative['config']['alpha'] < result_aggressive['config']['alpha']

    def test_detects_anomaly_in_data_with_outlier(self):
        """Should detect at least one anomaly in data with clear outlier"""
        values = np.array([10] * 35 + [1000])
        result = apply_demand_smoothing(values, preset='Balanced')
        assert result['anomaly_count'] >= 1

    def test_simple_function_returns_tuple(self):
        """apply_demand_smoothing_simple should return tuple for backward compatibility"""
        values = np.array([10] * 35)
        result = apply_demand_smoothing_simple(values, preset='Balanced')
        assert isinstance(result, tuple)
        assert len(result) == 3


class TestIntegrationWithForecast:
    """Integration tests for smoothing with forecast generation"""

    @pytest.fixture
    def sample_deliveries(self):
        """Create sample delivery data for testing - requires 30+ days for daily mode"""
        np.random.seed(42)
        # Need at least 30 days of data for daily mode to generate forecasts
        # Use recent dates relative to TODAY
        from demand_forecasting import TODAY
        end_date = TODAY
        start_date = TODAY - timedelta(days=120)  # 120 days of history
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        skus = ['SKU001', 'SKU002', 'SKU003']

        records = []
        for sku in skus:
            for date in dates:
                # Normal demand with occasional outliers
                qty = np.random.poisson(100) if np.random.random() > 0.05 else np.random.poisson(100) * 10
                records.append({
                    'Item - SAP Model Code': sku,
                    'Goods Issue Date: Date': date.strftime('%m/%d/%y'),
                    'Deliveries - TOTAL Goods Issue Qty': qty
                })

        return pd.DataFrame(records)

    def test_forecast_includes_anomaly_count(self, sample_deliveries):
        """Forecast output should include anomaly_count column"""
        _, forecast_df, _, _ = generate_demand_forecast(
            sample_deliveries,
            smoothing_preset='Balanced'
        )
        assert 'anomaly_count' in forecast_df.columns

    def test_forecast_includes_smoothing_preset(self, sample_deliveries):
        """Forecast output should include smoothing_preset column"""
        _, forecast_df, _, _ = generate_demand_forecast(
            sample_deliveries,
            smoothing_preset='Aggressive'
        )
        assert 'smoothing_preset' in forecast_df.columns
        assert forecast_df['smoothing_preset'].iloc[0] == 'Aggressive'

    def test_all_presets_work_with_forecast(self, sample_deliveries):
        """All three presets should work without errors"""
        for preset in ['Conservative', 'Balanced', 'Aggressive']:
            logs, forecast_df, _, _ = generate_demand_forecast(
                sample_deliveries,
                smoothing_preset=preset
            )
            assert not forecast_df.empty, f"Forecast empty for preset {preset}"

    def test_smoothing_logged(self, sample_deliveries):
        """Smoothing info should appear in logs"""
        logs, _, _, _ = generate_demand_forecast(
            sample_deliveries,
            smoothing_preset='Balanced'
        )

        # Check that smoothing-related info is logged
        smoothing_logs = [log for log in logs if 'smoothing' in log.lower() or 'anomal' in log.lower()]
        assert len(smoothing_logs) >= 1, "No smoothing info in logs"

    def test_invalid_preset_uses_default(self, sample_deliveries):
        """Invalid preset should fall back to default (Balanced)"""
        _, forecast_df, _, _ = generate_demand_forecast(
            sample_deliveries,
            smoothing_preset='InvalidPreset'
        )
        # Should complete without error and use Balanced
        assert not forecast_df.empty


class TestExponentialSmoothing:
    """Tests for the exponential smoothing calculation"""

    def test_single_value(self):
        """Single value should return that value"""
        values = np.array([100.0])
        result = calculate_exponential_smoothing(values, alpha=0.3)
        assert result == 100.0

    def test_empty_array(self):
        """Empty array should return 0"""
        values = np.array([])
        result = calculate_exponential_smoothing(values, alpha=0.3)
        assert result == 0

    def test_higher_alpha_responds_faster(self):
        """Higher alpha should respond faster to recent changes"""
        # Data that increases then drops
        values = np.array([10, 10, 10, 10, 50, 50, 50, 50])

        result_low_alpha = calculate_exponential_smoothing(values, alpha=0.1)
        result_high_alpha = calculate_exponential_smoothing(values, alpha=0.9)

        # Higher alpha should be closer to the recent values (50)
        assert result_high_alpha > result_low_alpha

    def test_alpha_boundaries(self):
        """Test behavior at alpha boundaries"""
        values = np.array([10, 20, 30, 40, 50])

        # Very low alpha - should be close to first value
        result_low = calculate_exponential_smoothing(values, alpha=0.01)

        # Very high alpha - should be close to last value
        result_high = calculate_exponential_smoothing(values, alpha=0.99)

        assert result_low < result_high  # Low alpha biases toward history


class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_all_same_values(self):
        """Data with all same values should have no anomalies"""
        values = np.array([50] * 100)
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['anomaly_count'] == 0

    def test_two_values_only(self):
        """Two values should skip detection (below minimum sample size)"""
        values = np.array([10, 1000])
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['skipped_detection'] == True
        assert result['anomaly_count'] == 0

    def test_negative_values(self):
        """Should handle negative values (though unusual for demand)"""
        values = np.array([-10] * 35 + [-100])
        result = detect_anomalies(values, z_threshold=2.0)
        assert isinstance(result['is_anomaly'], np.ndarray)

    def test_very_large_values(self):
        """Should handle very large values"""
        # Need 30+ data points for anomaly detection
        values = np.array([1e9] * 35 + [1e12])
        result = detect_anomalies(values, z_threshold=2.0)
        # Should detect the 1e12 as an outlier at index 35
        assert result['is_anomaly'][35] == True

    def test_float_precision(self):
        """Should handle floating point precision"""
        values = np.array([0.001] * 35 + [0.1])
        result = detect_anomalies(values, z_threshold=2.0)
        assert result['is_anomaly'][35] == True  # 0.1 is an outlier relative to 0.001


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
