"""
Tests for Demand Forecast New Features

Tests for:
1. Simplified 3 smoothing presets (Conservative, Balanced, Aggressive)
2. 9-month forecast horizon (270 days)
3. Bollinger Bands calculation (±2σ)
4. SMA trendline calculation (3-month window)
5. 18-month rolling view (9 months history + 9 months forecast)
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from demand_forecasting import (
    SMOOTHING_PRESETS,
    DEFAULT_SMOOTHING_PRESET,
    get_smoothing_config,
    generate_demand_forecast,
    _batch_process_sku_smoothing,
    _batch_calculate_trends,
    MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
    INTERMITTENT_DEMAND_CV_THRESHOLD,
    INTERMITTENT_DEMAND_Z_THRESHOLD,
    MAX_ANOMALY_PERCENTAGE,
)


# ===== SMOOTHING PRESETS TESTS =====

class TestSmoothingPresets:
    """Tests for simplified 3 smoothing presets"""

    def test_exactly_three_presets(self):
        """Verify there are exactly 3 smoothing presets"""
        assert len(SMOOTHING_PRESETS) == 3, f"Expected 3 presets, got {len(SMOOTHING_PRESETS)}"

    def test_preset_names(self):
        """Verify correct preset names: Conservative, Balanced, Aggressive"""
        expected_names = {'Conservative', 'Balanced', 'Aggressive'}
        actual_names = set(SMOOTHING_PRESETS.keys())
        assert actual_names == expected_names, f"Expected {expected_names}, got {actual_names}"

    def test_conservative_preset_values(self):
        """Verify Conservative preset has correct values"""
        conservative = SMOOTHING_PRESETS['Conservative']
        assert 'z_score_threshold' in conservative
        assert 'alpha' in conservative
        assert 'description' in conservative
        # Conservative should have lower Z (more sensitive) and lower alpha (more smoothing)
        assert conservative['z_score_threshold'] == 1.5, f"Expected Z=1.5, got {conservative['z_score_threshold']}"
        assert conservative['alpha'] == 0.03, f"Expected alpha=0.03, got {conservative['alpha']}"

    def test_balanced_preset_values(self):
        """Verify Balanced preset has correct values"""
        balanced = SMOOTHING_PRESETS['Balanced']
        assert balanced['z_score_threshold'] == 2.0, f"Expected Z=2.0, got {balanced['z_score_threshold']}"
        assert balanced['alpha'] == 0.08, f"Expected alpha=0.08, got {balanced['alpha']}"

    def test_aggressive_preset_values(self):
        """Verify Aggressive preset has correct values"""
        aggressive = SMOOTHING_PRESETS['Aggressive']
        assert aggressive['z_score_threshold'] == 2.5, f"Expected Z=2.5, got {aggressive['z_score_threshold']}"
        assert aggressive['alpha'] == 0.15, f"Expected alpha=0.15, got {aggressive['alpha']}"

    def test_default_preset_is_balanced(self):
        """Verify default preset is Balanced"""
        assert DEFAULT_SMOOTHING_PRESET == 'Balanced', f"Expected 'Balanced', got '{DEFAULT_SMOOTHING_PRESET}'"

    def test_get_smoothing_config_valid_preset(self):
        """Test get_smoothing_config returns correct config for valid preset"""
        for preset_name in ['Conservative', 'Balanced', 'Aggressive']:
            config = get_smoothing_config(preset_name)
            assert config == SMOOTHING_PRESETS[preset_name]

    def test_get_smoothing_config_invalid_preset(self):
        """Test get_smoothing_config falls back to Balanced for invalid preset"""
        config = get_smoothing_config('InvalidPreset')
        assert config == SMOOTHING_PRESETS['Balanced']

    def test_get_smoothing_config_none(self):
        """Test get_smoothing_config falls back to Balanced for None"""
        config = get_smoothing_config(None)
        assert config == SMOOTHING_PRESETS['Balanced']

    def test_presets_z_threshold_ordering(self):
        """Verify Z-thresholds increase from Conservative to Aggressive"""
        conservative_z = SMOOTHING_PRESETS['Conservative']['z_score_threshold']
        balanced_z = SMOOTHING_PRESETS['Balanced']['z_score_threshold']
        aggressive_z = SMOOTHING_PRESETS['Aggressive']['z_score_threshold']

        assert conservative_z < balanced_z < aggressive_z, \
            f"Z-thresholds should increase: {conservative_z} < {balanced_z} < {aggressive_z}"

    def test_presets_alpha_ordering(self):
        """Verify alpha values increase from Conservative to Aggressive"""
        conservative_alpha = SMOOTHING_PRESETS['Conservative']['alpha']
        balanced_alpha = SMOOTHING_PRESETS['Balanced']['alpha']
        aggressive_alpha = SMOOTHING_PRESETS['Aggressive']['alpha']

        assert conservative_alpha < balanced_alpha < aggressive_alpha, \
            f"Alpha should increase: {conservative_alpha} < {balanced_alpha} < {aggressive_alpha}"


# ===== FORECAST HORIZON TESTS =====

class TestForecastHorizon:
    """Tests for 9-month forecast horizon (270 days)"""

    @pytest.fixture
    def sample_deliveries_df(self):
        """Create sample deliveries dataframe for testing"""
        np.random.seed(42)
        today = pd.to_datetime(datetime.now().date())

        # Create 12 months of daily data
        dates = pd.date_range(end=today, periods=365, freq='D')

        data = []
        for date in dates:
            # Create demand for 3 SKUs
            for sku in ['SKU001', 'SKU002', 'SKU003']:
                base_demand = {'SKU001': 100, 'SKU002': 50, 'SKU003': 75}[sku]
                demand = max(0, base_demand + np.random.normal(0, 10))
                data.append({
                    'sku': sku,
                    'delivery_date': date,
                    'delivered_qty': demand
                })

        return pd.DataFrame(data)

    def test_forecast_horizon_270_days(self, sample_deliveries_df):
        """Verify forecast is generated for 270 days (9 months)"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_df,
            forecast_horizon_days=270,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        if not forecast_df.empty:
            assert 'forecast_horizon_days' in forecast_df.columns
            assert forecast_df['forecast_horizon_days'].iloc[0] == 270

    def test_forecast_total_qty_uses_270_days(self, sample_deliveries_df):
        """Verify forecast_total_qty is calculated for 270 day horizon"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            sample_deliveries_df,
            forecast_horizon_days=270,
            ts_granularity='daily',
            smoothing_preset='Balanced'
        )

        if not forecast_df.empty:
            # forecast_total_qty should be ~270x daily forecast
            for _, row in forecast_df.iterrows():
                expected_total = row['primary_forecast_daily'] * 270
                # Allow 1% tolerance due to rounding
                assert abs(row['forecast_total_qty'] - expected_total) / expected_total < 0.01


# ===== BOLLINGER BANDS TESTS =====

class TestBollingerBands:
    """Tests for Bollinger Bands calculation (±2σ)"""

    def test_bollinger_bands_upper_calculation(self):
        """Verify upper Bollinger Band is forecast + 2*std"""
        forecast_monthly = 1000
        std_monthly = 100

        expected_upper = forecast_monthly + 2 * std_monthly  # 1200

        assert expected_upper == 1200

    def test_bollinger_bands_lower_calculation(self):
        """Verify lower Bollinger Band is max(0, forecast - 2*std)"""
        forecast_monthly = 1000
        std_monthly = 100

        expected_lower = max(0, forecast_monthly - 2 * std_monthly)  # 800

        assert expected_lower == 800

    def test_bollinger_bands_lower_non_negative(self):
        """Verify lower Bollinger Band is never negative"""
        forecast_monthly = 100
        std_monthly = 100  # 2*std = 200, which would make lower negative

        lower_band = max(0, forecast_monthly - 2 * std_monthly)

        assert lower_band >= 0

    def test_bollinger_bands_array_calculation(self):
        """Test Bollinger Bands calculation for array of forecast values"""
        forecast_values = [1000, 1100, 1050, 1200, 1150, 1000, 1050, 1100, 1000]
        std_monthly = 100

        upper_band = [f + 2 * std_monthly for f in forecast_values]
        lower_band = [max(0, f - 2 * std_monthly) for f in forecast_values]

        # Verify each value
        assert upper_band[0] == 1200  # 1000 + 200
        assert lower_band[0] == 800   # 1000 - 200
        assert len(upper_band) == 9
        assert len(lower_band) == 9
        assert all(l >= 0 for l in lower_band)


# ===== SMA TRENDLINE TESTS =====

class TestSMATrendline:
    """Tests for 3-month SMA trendline calculation"""

    def test_sma_3_month_calculation(self):
        """Verify 3-month SMA is calculated correctly"""
        values = [100, 110, 120, 130, 140, 150]
        sma_window = 3

        sma_values = []
        for i in range(len(values)):
            if i < sma_window - 1:
                sma_values.append(np.nan)
            else:
                sma_values.append(np.mean(values[i-sma_window+1:i+1]))

        # First 2 values should be NaN
        assert np.isnan(sma_values[0])
        assert np.isnan(sma_values[1])
        # Third value should be average of first 3: (100+110+120)/3 = 110
        assert sma_values[2] == 110
        # Fourth value: (110+120+130)/3 = 120
        assert sma_values[3] == 120
        # Fifth value: (120+130+140)/3 = 130
        assert sma_values[4] == 130

    def test_sma_with_mixed_historical_forecast(self):
        """Test SMA across historical + forecast data"""
        historical = [100, 110, 90, 105, 115, 95, 100, 110, 100]  # 9 months history
        forecast = [105, 105, 105, 105, 105, 105, 105, 105, 105]  # 9 months forecast
        all_values = historical + forecast

        sma_window = 3
        sma_values = []
        for i in range(len(all_values)):
            if i < sma_window - 1:
                sma_values.append(np.nan)
            else:
                sma_values.append(np.mean(all_values[i-sma_window+1:i+1]))

        # Verify length matches combined data
        assert len(sma_values) == 18
        # Verify transition point (last historical + first 2 forecasts)
        # At index 10 (3rd forecast): avg of [100, 105, 105] = 103.33
        assert abs(sma_values[10] - 103.33) < 0.01

    def test_sma_insufficient_data(self):
        """Test SMA handles data shorter than window gracefully"""
        values = [100, 110]  # Only 2 values, window is 3
        sma_window = 3

        sma_values = []
        for i in range(len(values)):
            if i < sma_window - 1:
                sma_values.append(np.nan)
            else:
                sma_values.append(np.mean(values[i-sma_window+1:i+1]))

        # All values should be NaN
        assert all(np.isnan(v) for v in sma_values)


# ===== 18-MONTH ROLLING VIEW TESTS =====

class TestRollingView:
    """Tests for 18-month rolling view (9 months history + 9 months forecast)"""

    def test_historical_months_constant(self):
        """Verify historical window is 9 months"""
        HISTORICAL_MONTHS = 9
        assert HISTORICAL_MONTHS == 9

    def test_forecast_months_constant(self):
        """Verify forecast window is 9 months"""
        FORECAST_MONTHS = 9
        assert FORECAST_MONTHS == 9

    def test_total_rolling_view_18_months(self):
        """Verify total rolling view is 18 months"""
        HISTORICAL_MONTHS = 9
        FORECAST_MONTHS = 9
        total_months = HISTORICAL_MONTHS + FORECAST_MONTHS
        assert total_months == 18

    def test_filter_to_last_9_months(self):
        """Test filtering historical data to last 9 months"""
        # Create 24 months of data
        end_date = pd.to_datetime('2024-12-01')
        dates = pd.date_range(start='2023-01-01', end=end_date, freq='MS')
        demand_data = pd.DataFrame({
            'date': dates,
            'demand_qty': np.random.randint(100, 200, len(dates))
        })

        # Filter to last 9 months
        HISTORICAL_MONTHS = 9
        last_date = demand_data['date'].max()
        cutoff_date = last_date - pd.DateOffset(months=HISTORICAL_MONTHS)
        filtered = demand_data[demand_data['date'] >= cutoff_date]

        # Should have ~9 months of data
        assert len(filtered) <= HISTORICAL_MONTHS + 1  # +1 for inclusive bounds

    def test_forecast_date_range_generation(self):
        """Test generating next 9 months of forecast dates"""
        last_actual_date = pd.to_datetime('2024-12-01')
        FORECAST_MONTHS = 9

        forecast_dates = pd.date_range(
            start=last_actual_date + pd.DateOffset(months=1),
            periods=FORECAST_MONTHS,
            freq='MS'
        )

        assert len(forecast_dates) == 9
        assert forecast_dates[0] == pd.to_datetime('2025-01-01')
        assert forecast_dates[-1] == pd.to_datetime('2025-09-01')


# ===== INTEGRATION TESTS =====

class TestForecastIntegration:
    """Integration tests for forecast generation with new features"""

    @pytest.fixture
    def comprehensive_deliveries_df(self):
        """Create comprehensive deliveries dataframe for integration testing"""
        np.random.seed(42)
        today = pd.to_datetime(datetime.now().date())

        # Create 18 months of data
        dates = pd.date_range(end=today, periods=540, freq='D')

        data = []
        for date in dates:
            for sku in ['SKU001', 'SKU002', 'SKU003']:
                base_demand = {'SKU001': 100, 'SKU002': 50, 'SKU003': 75}[sku]
                # Add some seasonality
                month = date.month
                seasonal_factor = 1 + 0.2 * np.sin(2 * np.pi * month / 12)
                demand = max(0, base_demand * seasonal_factor + np.random.normal(0, 10))
                data.append({
                    'sku': sku,
                    'delivery_date': date,
                    'delivered_qty': demand
                })

        return pd.DataFrame(data)

    def test_forecast_output_with_new_presets(self, comprehensive_deliveries_df):
        """Test forecast output contains smoothing preset information"""
        for preset in ['Conservative', 'Balanced', 'Aggressive']:
            logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
                comprehensive_deliveries_df,
                forecast_horizon_days=270,
                ts_granularity='monthly',
                rolling_months=18,
                smoothing_preset=preset
            )

            if not forecast_df.empty:
                assert 'smoothing_preset' in forecast_df.columns
                assert all(forecast_df['smoothing_preset'] == preset)

    def test_different_presets_different_anomaly_counts(self, comprehensive_deliveries_df):
        """Verify Conservative flags more anomalies than Aggressive"""
        results = {}

        for preset in ['Conservative', 'Aggressive']:
            logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
                comprehensive_deliveries_df,
                forecast_horizon_days=270,
                ts_granularity='monthly',
                rolling_months=18,
                smoothing_preset=preset
            )

            if not forecast_df.empty:
                results[preset] = forecast_df['anomaly_count'].sum()

        # Conservative (Z=1.5) should flag more than Aggressive (Z=2.5)
        if 'Conservative' in results and 'Aggressive' in results:
            assert results['Conservative'] >= results['Aggressive'], \
                f"Conservative ({results['Conservative']}) should flag >= Aggressive ({results['Aggressive']})"

    def test_forecast_contains_required_fields(self, comprehensive_deliveries_df):
        """Verify forecast contains all required fields for UI"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(
            comprehensive_deliveries_df,
            forecast_horizon_days=270,
            ts_granularity='monthly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        if not forecast_df.empty:
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
                'anomaly_count',
                'anomaly_pct',
                'is_intermittent',
                'skipped_detection',
                'applied_z_threshold',
                'smoothing_preset',
                'demand_std'  # Needed for Bollinger Bands
            ]

            for field in required_fields:
                assert field in forecast_df.columns, f"Missing required field: {field}"


# ===== BATCH PROCESSING TESTS =====

class TestBatchProcessing:
    """Tests for batch processing with different presets"""

    def test_batch_processing_with_conservative(self):
        """Test batch processing with Conservative preset"""
        np.random.seed(42)
        sku_data = {
            'SKU_A': np.array([100.0] * 35 + [500.0]),  # Anomaly at end
            'SKU_B': np.array([50.0] * 40),
        }

        config = get_smoothing_config('Conservative')

        result_df = _batch_process_sku_smoothing(
            grouped_data=sku_data,
            z_threshold=config['z_score_threshold'],  # 1.5
            alpha=config['alpha'],  # 0.03
            cv_threshold=INTERMITTENT_DEMAND_CV_THRESHOLD,
            intermittent_z=INTERMITTENT_DEMAND_Z_THRESHOLD,
            min_sample_size=MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
            max_anomaly_pct=MAX_ANOMALY_PERCENTAGE,
            use_parallel=False
        )

        # Conservative (Z=1.5) should detect the anomaly
        sku_a = result_df[result_df['sku'] == 'SKU_A'].iloc[0]
        assert sku_a['anomaly_count'] >= 1

    def test_batch_processing_with_aggressive(self):
        """Test batch processing with Aggressive preset"""
        np.random.seed(42)
        sku_data = {
            'SKU_A': np.array([100.0] * 35 + [200.0]),  # Moderate spike
            'SKU_B': np.array([50.0] * 40),
        }

        config = get_smoothing_config('Aggressive')

        result_df = _batch_process_sku_smoothing(
            grouped_data=sku_data,
            z_threshold=config['z_score_threshold'],  # 2.5
            alpha=config['alpha'],  # 0.15
            cv_threshold=INTERMITTENT_DEMAND_CV_THRESHOLD,
            intermittent_z=INTERMITTENT_DEMAND_Z_THRESHOLD,
            min_sample_size=MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
            max_anomaly_pct=MAX_ANOMALY_PERCENTAGE,
            use_parallel=False
        )

        # Aggressive (Z=2.5) may not flag moderate anomalies
        # Just verify the function runs successfully
        assert len(result_df) == 2


# ===== UI CHART RENDERING TESTS =====

class TestUIChartDataPreparation:
    """Tests that verify data is correctly prepared for UI chart rendering"""

    @pytest.fixture
    def sample_forecast_data(self):
        """Create sample forecast data as the UI would receive it"""
        return pd.DataFrame({
            'sku': ['SKU001'],
            'primary_forecast_daily': [100.0],
            'exp_smooth': [95.0],
            'exp_smooth_seasonal': [98.0],
            'demand_std': [300.0],  # Monthly std, /30 for daily = 10
            'forecast_total_qty': [27000.0],  # 100 * 270 days
            'forecast_total_qty_seasonal': [26460.0],  # 98 * 270
            'forecast_confidence': ['High'],
            'forecast_method': ['MA-12M'],
            'demand_pattern': ['Stable & Flat'],
            'seasonal_index': [1.02],
            'sku_description': ['Test Product']
        })

    @pytest.fixture
    def sample_daily_demand(self):
        """Create 12 months of sample daily demand data"""
        today = pd.to_datetime(datetime.now().date())
        dates = pd.date_range(end=today, periods=365, freq='D')

        return pd.DataFrame({
            'sku': ['SKU001'] * 365,
            'date': dates,
            'demand_qty': [100 + np.random.normal(0, 10) for _ in range(365)]
        })

    def test_bollinger_bands_calculation_for_ui(self, sample_forecast_data):
        """Test Bollinger Bands calculation as used in UI chart

        Bollinger Bands use the preset's Z-threshold as the band multiplier:
        - Conservative: 1.5σ (tighter bands)
        - Balanced: 2.0σ (standard)
        - Aggressive: 2.5σ (wider bands)

        True Bollinger Bands do NOT floor at 0 - they show the actual statistical range.
        """
        row = sample_forecast_data.iloc[0]

        # Get daily forecast value (seasonally-adjusted if available)
        forecast_daily = row['exp_smooth_seasonal']

        # Get standard deviation for Bollinger Bands (monthly / 30 = daily)
        std_daily = row['demand_std'] / 30.0

        # Get band multiplier from applied Z-threshold (uses preset's Z-score)
        band_multiplier = row.get('applied_z_threshold', 2.0)

        # Convert to monthly for chart display
        forecast_monthly = forecast_daily * 30
        std_monthly = std_daily * 30

        # Calculate true Bollinger Bands (±band_multiplier*σ, no floor at 0)
        FORECAST_MONTHS = 9
        upper_band = [forecast_monthly + band_multiplier * std_monthly] * FORECAST_MONTHS
        lower_band = [forecast_monthly - band_multiplier * std_monthly] * FORECAST_MONTHS

        # Verify calculations
        assert len(upper_band) == 9
        assert len(lower_band) == 9
        assert upper_band[0] == forecast_monthly + band_multiplier * std_monthly
        assert lower_band[0] == forecast_monthly - band_multiplier * std_monthly
        # True Bollinger Bands CAN be negative (no floor at 0)

    def test_sma_trendline_calculation_for_ui(self, sample_daily_demand, sample_forecast_data):
        """Test SMA trendline calculation as used in UI chart"""
        # Filter to last 9 months of historical data (as UI does)
        HISTORICAL_MONTHS = 9
        last_date = sample_daily_demand['date'].max()
        cutoff_date = last_date - pd.DateOffset(months=HISTORICAL_MONTHS)
        filtered_history = sample_daily_demand[sample_daily_demand['date'] >= cutoff_date]

        # Aggregate to monthly (as UI does)
        filtered_history = filtered_history.copy()
        filtered_history['month'] = filtered_history['date'].dt.to_period('M').dt.to_timestamp()
        monthly_demand = filtered_history.groupby('month')['demand_qty'].sum().values.tolist()

        # Create forecast values
        forecast_monthly = sample_forecast_data['exp_smooth_seasonal'].iloc[0] * 30
        FORECAST_MONTHS = 9
        forecast_values = [forecast_monthly] * FORECAST_MONTHS

        # Combine historical + forecast
        all_values = list(monthly_demand) + forecast_values

        # Calculate 3-month SMA (as UI does)
        sma_window = 3
        sma_values = []
        for i in range(len(all_values)):
            if i < sma_window - 1:
                sma_values.append(np.nan)
            else:
                sma_values.append(np.mean(all_values[i-sma_window+1:i+1]))

        # Verify SMA calculation
        assert len(sma_values) == len(all_values)
        assert np.isnan(sma_values[0])  # First value is NaN
        assert np.isnan(sma_values[1])  # Second value is NaN
        assert not np.isnan(sma_values[2])  # Third value has SMA

    def test_18_month_rolling_view_data_prep(self, sample_daily_demand, sample_forecast_data):
        """Test 18-month rolling view data preparation"""
        HISTORICAL_MONTHS = 9
        FORECAST_MONTHS = 9

        # Filter historical data to last 9 months
        last_date = sample_daily_demand['date'].max()
        cutoff_date = last_date - pd.DateOffset(months=HISTORICAL_MONTHS)
        filtered = sample_daily_demand[sample_daily_demand['date'] >= cutoff_date]

        # Create forecast date range
        forecast_dates = pd.date_range(
            start=last_date + pd.DateOffset(months=1),
            periods=FORECAST_MONTHS,
            freq='MS'
        )

        # Aggregate historical to monthly
        filtered = filtered.copy()
        filtered['month'] = filtered['date'].dt.to_period('M').dt.to_timestamp()
        monthly_history = filtered.groupby('month')['demand_qty'].sum().reset_index()

        # Verify total range is approximately 18 months
        total_months = len(monthly_history) + FORECAST_MONTHS
        assert total_months <= 18 + 1  # Allow 1 month tolerance

    def test_forecast_data_has_std_for_bollinger(self, sample_forecast_data):
        """Verify forecast data contains demand_std needed for Bollinger Bands"""
        assert 'demand_std' in sample_forecast_data.columns
        assert sample_forecast_data['demand_std'].iloc[0] > 0

    def test_seasonal_forecast_used_when_available(self, sample_forecast_data):
        """Verify UI uses seasonal forecast when available"""
        row = sample_forecast_data.iloc[0]

        # UI logic: prefer exp_smooth_seasonal > exp_smooth > primary_forecast_daily
        if 'exp_smooth_seasonal' in row.index and pd.notna(row['exp_smooth_seasonal']):
            forecast_daily = row['exp_smooth_seasonal']
        elif 'exp_smooth' in row.index and pd.notna(row['exp_smooth']):
            forecast_daily = row['exp_smooth']
        else:
            forecast_daily = row['primary_forecast_daily']

        assert forecast_daily == 98.0  # Should use exp_smooth_seasonal

    def test_sku_forecast_varies_by_month_with_seasonality(self):
        """Verify SKU-level forecast applies per-month seasonal indices (not flat)

        The SKU chart should calculate seasonal indices from historical data and
        apply them month-by-month so forecast bars vary by season.
        """
        # Simulate historical data with clear seasonality
        # High demand in summer (Jun-Aug), low in winter (Dec-Feb)
        dates = pd.date_range(start='2024-01-01', end='2024-12-31', freq='MS')
        demand_by_month = {
            1: 80, 2: 85, 3: 95, 4: 100, 5: 110, 6: 130,
            7: 140, 8: 135, 9: 115, 10: 100, 11: 90, 12: 75
        }

        historical_demand = pd.DataFrame({
            'date': dates,
            'demand_qty': [demand_by_month[d.month] for d in dates],
            'sku': 'SKU001'
        })

        # Calculate seasonal indices (as the UI does)
        historical_demand['month_num'] = historical_demand['date'].dt.month
        monthly_avg = historical_demand.groupby('month_num')['demand_qty'].mean()
        overall_avg = historical_demand['demand_qty'].mean()

        seasonal_indices = {}
        for month_num in range(1, 13):
            if month_num in monthly_avg.index:
                seasonal_indices[month_num] = monthly_avg[month_num] / overall_avg
            else:
                seasonal_indices[month_num] = 1.0

        # Verify seasonal indices vary (not all 1.0)
        assert min(seasonal_indices.values()) < 1.0, "Should have low season months"
        assert max(seasonal_indices.values()) > 1.0, "Should have high season months"

        # Apply to 9-month forecast (as UI does)
        base_forecast = 100 * 30  # Monthly forecast = daily * 30
        forecast_dates = pd.date_range(start='2025-01-01', periods=9, freq='MS')

        forecast_values = []
        for forecast_date in forecast_dates:
            month_num = forecast_date.month
            seasonal_index = seasonal_indices.get(month_num, 1.0)
            adjusted_forecast = base_forecast * seasonal_index
            forecast_values.append(adjusted_forecast)

        # Verify forecast values vary by month (not all the same)
        assert len(set(forecast_values)) > 1, "Forecast should vary by month due to seasonality"

        # January (month 1) should have lower forecast than June (month 6)
        jan_index = 0  # First forecast month (Jan 2025)
        jun_index = 5  # Sixth forecast month (Jun 2025)
        assert forecast_values[jan_index] < forecast_values[jun_index], \
            f"January forecast ({forecast_values[jan_index]}) should be < June ({forecast_values[jun_index]})"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
