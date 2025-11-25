"""
Tests for demand forecasting module
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demand_forecasting import generate_demand_forecast


@pytest.fixture
def sample_deliveries_df():
    """Create sample deliveries data for testing"""
    today = pd.to_datetime(datetime.now().date())
    dates = []
    skus = []
    qtys = []

    # Generate 120 days of historical data for 3 SKUs
    for days_ago in range(120, 0, -1):
        date = today - timedelta(days=days_ago)

        # SKU001: Stable demand (avg 100 units/day, low volatility)
        skus.append('SKU001')
        dates.append(date)
        qtys.append(np.random.normal(100, 10))

        # SKU002: Volatile demand (avg 50 units/day, high volatility)
        skus.append('SKU002')
        dates.append(date)
        qtys.append(np.random.normal(50, 25))

        # SKU003: Growing demand (starts at 30, grows to 80)
        skus.append('SKU003')
        dates.append(date)
        growth_factor = (120 - days_ago) / 120  # 0 to 1
        qtys.append(30 + (50 * growth_factor) + np.random.normal(0, 5))

    return pd.DataFrame({
        'sku': skus,
        'delivery_date': dates,
        'delivered_qty': qtys
    })


class TestDemandForecasting:
    """Test demand forecasting functionality"""

    def test_generate_forecast_returns_tuple(self, sample_deliveries_df):
        """Test that generate_demand_forecast returns a tuple of 4 elements"""
        result = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90)
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_generate_forecast_returns_dataframes(self, sample_deliveries_df):
        """Test that forecast returns logs, forecast_df, accuracy_df, and daily_demand_df"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90)

        assert isinstance(logs, list)
        assert isinstance(forecast_df, pd.DataFrame)
        assert isinstance(accuracy_df, pd.DataFrame)

    def test_forecast_not_empty(self, sample_deliveries_df):
        """Test that forecast generates results for sample data"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90)

        assert not forecast_df.empty, "Forecast DataFrame should not be empty"
        assert len(forecast_df) > 0, "Should generate forecasts for at least one SKU"

    def test_forecast_has_required_columns(self, sample_deliveries_df):
        """Test that forecast DataFrame has required columns"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90)

        required_columns = ['sku', 'forecast_method', 'primary_forecast_daily', 'forecast_total_qty',
                          'forecast_confidence', 'demand_pattern']

        for col in required_columns:
            assert col in forecast_df.columns, f"Missing required column: {col}"

    def test_forecast_for_all_skus(self, sample_deliveries_df):
        """Test that forecast is generated for all unique SKUs"""
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90)

        original_skus = sample_deliveries_df['sku'].nunique()
        forecast_skus = len(forecast_df)

        assert forecast_skus == original_skus, f"Expected {original_skus} SKUs, got {forecast_skus}"

    def test_forecast_empty_dataframe(self):
        """Test forecast with empty DataFrame"""
        empty_df = pd.DataFrame(columns=['sku', 'delivery_date', 'delivered_qty'])
        logs, forecast_df, accuracy_df, daily_demand_df = generate_demand_forecast(empty_df, forecast_horizon_days=90)

        assert isinstance(forecast_df, pd.DataFrame)
        # Empty input should result in empty or minimal output

    def test_forecast_horizon_parameter(self, sample_deliveries_df):
        """Test that forecast horizon parameter works"""
        logs_30, forecast_30, accuracy_30, daily_demand_30 = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=30)
        logs_90, forecast_90, accuracy_90, daily_demand_90 = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90)

        assert isinstance(forecast_30, pd.DataFrame)
        assert isinstance(forecast_90, pd.DataFrame)

    def test_monthly_aggregation(self, sample_deliveries_df):
        """When requesting monthly granularity, daily_demand_df should be aggregated to months"""
        logs, forecast_df, accuracy_df, monthly_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90, ts_granularity='monthly')

        assert isinstance(monthly_df, pd.DataFrame)
        # Dates should be month starts (day == 1) - check at least one record exists
        if not monthly_df.empty:
            assert (monthly_df['date'].dt.day == 1).any(), "Monthly series 'date' should align to month starts"

    def test_rolling_12_months_preload(self, sample_deliveries_df):
        """Request monthly granularity limited to last 12 months and ensure returned series respects window"""
        logs, forecast_df, accuracy_df, monthly_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90, ts_granularity='monthly', rolling_months=12)

        assert isinstance(monthly_df, pd.DataFrame)
        if not monthly_df.empty:
            # compute month span in months between min and max
            min_date = monthly_df['date'].min()
            max_date = monthly_df['date'].max()
            month_span = (max_date.year - min_date.year) * 12 + (max_date.month - min_date.month) + 1
            assert month_span <= 12, f"Monthly DF should cover max 12 months but covers {month_span}"

    def test_rolling_months_anchor_today(self, sample_deliveries_df):
        """When rolling_months is used, the earliest included month should be anchored to TODAY."""
        logs, forecast_df, accuracy_df, monthly_df = generate_demand_forecast(sample_deliveries_df, forecast_horizon_days=90, ts_granularity='monthly', rolling_months=6)

        # If the function returned data, the min date should be >= (TODAY - months + 1 month start)
        if not monthly_df.empty:
            min_date = monthly_df['date'].min()
            today = pd.to_datetime(datetime.now().date())
            expected_earliest = (today - pd.DateOffset(months=5)).replace(day=1)
            assert min_date >= expected_earliest, f"min_date {min_date} should be >= {expected_earliest}" 
