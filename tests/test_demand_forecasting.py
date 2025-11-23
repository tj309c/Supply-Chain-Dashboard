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
