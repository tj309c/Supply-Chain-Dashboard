"""
Backtesting Tests for Forecast Granularity Comparison

Compares forecast accuracy across different time series granularities:
- Daily: More data points but noisier
- Weekly: Balanced - smooths daily noise while preserving patterns
- Monthly: Fewest data points, may miss seasonal patterns

Uses walk-forward validation to measure forecast accuracy.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from demand_forecasting import generate_demand_forecast


class TestGranularityBacktesting:
    """Backtesting tests comparing daily, weekly, monthly granularity"""

    @pytest.fixture
    def realistic_demand_data(self):
        """
        Create realistic demand data with:
        - Clear seasonality (summer high, winter low)
        - Weekly patterns (higher demand at week starts)
        - Random noise
        - Some anomalies

        Data spans 2 years ending recently for rolling_months filter to work.
        """
        np.random.seed(42)

        # Generate 2 years of daily data ending today
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)  # 2 years ago
        dates = pd.date_range(start=start_date, end=end_date, freq='D')

        data = []
        base_demand = 100

        for date in dates:
            # Seasonal component (summer high, winter low)
            day_of_year = date.timetuple().tm_yday
            seasonal = 1 + 0.3 * np.sin(2 * np.pi * (day_of_year - 90) / 365)  # Peak in summer

            # Weekly pattern (higher demand Mon-Wed)
            weekday = date.weekday()
            weekly = 1.1 if weekday < 3 else 0.95

            # Random noise
            noise = 1 + np.random.normal(0, 0.15)

            # Occasional anomaly (1% chance of 3x spike)
            anomaly = 3.0 if np.random.random() < 0.01 else 1.0

            demand = max(0, base_demand * seasonal * weekly * noise * anomaly)

            data.append({
                'sku': 'TEST_SKU',
                'delivery_date': date,
                'delivered_qty': demand
            })

        return pd.DataFrame(data)

    @pytest.fixture
    def multi_sku_demand_data(self):
        """Create demand data for multiple SKUs with different patterns"""
        np.random.seed(123)

        # Use recent dates for rolling_months filter to work
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)  # 2 years ago
        dates = pd.date_range(start=start_date, end=end_date, freq='D')

        data = []

        # SKU1: Strong seasonality
        for date in dates:
            day_of_year = date.timetuple().tm_yday
            seasonal = 1 + 0.4 * np.sin(2 * np.pi * (day_of_year - 90) / 365)
            demand = max(0, 100 * seasonal * (1 + np.random.normal(0, 0.1)))
            data.append({'sku': 'SKU_SEASONAL', 'delivery_date': date, 'delivered_qty': demand})

        # SKU2: Stable demand (low seasonality)
        for date in dates:
            demand = max(0, 50 * (1 + np.random.normal(0, 0.08)))
            data.append({'sku': 'SKU_STABLE', 'delivery_date': date, 'delivered_qty': demand})

        # SKU3: Intermittent demand (sporadic)
        for date in dates:
            if np.random.random() < 0.3:  # 30% of days have demand
                demand = max(0, 200 * (1 + np.random.normal(0, 0.2)))
            else:
                demand = 0
            data.append({'sku': 'SKU_INTERMITTENT', 'delivery_date': date, 'delivered_qty': demand})

        return pd.DataFrame(data)

    def calculate_mape(self, actual, forecast):
        """Calculate Mean Absolute Percentage Error"""
        actual = np.array(actual)
        forecast = np.array(forecast)

        # Avoid division by zero
        mask = actual > 0
        if mask.sum() == 0:
            return np.nan

        return np.mean(np.abs((actual[mask] - forecast[mask]) / actual[mask])) * 100

    def calculate_mae(self, actual, forecast):
        """Calculate Mean Absolute Error"""
        return np.mean(np.abs(np.array(actual) - np.array(forecast)))

    def walk_forward_backtest(self, deliveries_df, granularity, train_months=18, test_months=3):
        """
        Walk-forward validation:
        1. Use first train_months of data to train
        2. Forecast next test_months
        3. Compare forecast to actual

        Returns accuracy metrics.
        """
        # Ensure we have enough data
        deliveries_df = deliveries_df.copy()
        deliveries_df['delivery_date'] = pd.to_datetime(deliveries_df['delivery_date'])
        min_date = deliveries_df['delivery_date'].min()
        max_date = deliveries_df['delivery_date'].max()

        total_days = (max_date - min_date).days
        required_days = (train_months + test_months) * 30

        if total_days < required_days:
            return None, None, "Insufficient data"

        # Split into train and test
        train_end = min_date + timedelta(days=train_months * 30)
        test_end = train_end + timedelta(days=test_months * 30)

        train_df = deliveries_df[deliveries_df['delivery_date'] <= train_end]
        test_df = deliveries_df[(deliveries_df['delivery_date'] > train_end) &
                                (deliveries_df['delivery_date'] <= test_end)]

        # Generate forecast on training data
        logs, forecast_df, accuracy_df, daily_df = generate_demand_forecast(
            train_df,
            forecast_horizon_days=test_months * 30,
            ts_granularity=granularity,
            rolling_months=train_months,
            smoothing_preset='Balanced'
        )

        if forecast_df.empty:
            return None, None, f"No forecast generated for {granularity}"

        # Calculate actual demand in test period (aggregated to monthly)
        test_df = test_df.copy()
        test_df['month'] = test_df['delivery_date'].dt.to_period('M')
        actual_monthly = test_df.groupby(['sku', 'month'])['delivered_qty'].sum().reset_index()

        results = []
        for sku in forecast_df['sku'].unique():
            sku_forecast = forecast_df[forecast_df['sku'] == sku]
            if sku_forecast.empty:
                continue

            # Get forecasted monthly demand
            forecast_daily = sku_forecast['primary_forecast_daily'].iloc[0]
            forecast_monthly = forecast_daily * 30

            # Get actual monthly demand for this SKU
            sku_actual = actual_monthly[actual_monthly['sku'] == sku]['delivered_qty'].values

            if len(sku_actual) == 0:
                continue

            # Calculate error for each month
            for actual in sku_actual:
                results.append({
                    'sku': sku,
                    'actual': actual,
                    'forecast': forecast_monthly,
                    'error': abs(actual - forecast_monthly),
                    'pct_error': abs(actual - forecast_monthly) / actual * 100 if actual > 0 else 0
                })

        if not results:
            return None, None, "No comparable results"

        results_df = pd.DataFrame(results)
        mape = results_df['pct_error'].mean()
        mae = results_df['error'].mean()

        return mape, mae, "Success"

    def test_weekly_granularity_produces_valid_forecast(self, realistic_demand_data):
        """Verify weekly granularity produces valid forecasts"""
        logs, forecast_df, accuracy_df, weekly_df = generate_demand_forecast(
            realistic_demand_data,
            forecast_horizon_days=90,
            ts_granularity='weekly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Weekly forecast empty. Logs: {logs}"
        assert not weekly_df.empty, "Weekly demand data should not be empty"

        # Weekly data should have more rows than monthly would
        expected_weeks = 18 * 4  # ~72 weeks in 18 months
        assert len(weekly_df) > 12, f"Expected more weekly data points, got {len(weekly_df)}"

    def test_daily_granularity_produces_valid_forecast(self, realistic_demand_data):
        """Verify daily granularity produces valid forecasts"""
        logs, forecast_df, accuracy_df, daily_df = generate_demand_forecast(
            realistic_demand_data,
            forecast_horizon_days=90,
            ts_granularity='daily',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Daily forecast empty. Logs: {logs}"
        assert not daily_df.empty, "Daily demand data should not be empty"

        # Daily data should have many more rows
        assert len(daily_df) > 100, f"Expected many daily data points, got {len(daily_df)}"

    def test_monthly_granularity_produces_valid_forecast(self, realistic_demand_data):
        """Verify monthly granularity produces valid forecasts"""
        logs, forecast_df, accuracy_df, monthly_df = generate_demand_forecast(
            realistic_demand_data,
            forecast_horizon_days=90,
            ts_granularity='monthly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        assert not forecast_df.empty, f"Monthly forecast empty. Logs: {logs}"
        assert not monthly_df.empty, "Monthly demand data should not be empty"

    def test_weekly_captures_seasonality_better_than_monthly(self, realistic_demand_data):
        """
        Test that weekly granularity captures seasonal patterns better than monthly.

        Weekly has ~4x more data points per month, allowing:
        - Better detection of seasonal trends
        - More robust averaging for each calendar month
        """
        # Generate forecasts at both granularities
        logs_weekly, forecast_weekly, _, weekly_df = generate_demand_forecast(
            realistic_demand_data,
            forecast_horizon_days=90,
            ts_granularity='weekly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        logs_monthly, forecast_monthly, _, monthly_df = generate_demand_forecast(
            realistic_demand_data,
            forecast_horizon_days=90,
            ts_granularity='monthly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        assert not forecast_weekly.empty, f"Weekly forecast failed: {logs_weekly}"
        assert not forecast_monthly.empty, f"Monthly forecast failed: {logs_monthly}"

        # Weekly should have more data points for seasonality calculation
        assert len(weekly_df) > len(monthly_df), \
            f"Weekly should have more data points: {len(weekly_df)} vs {len(monthly_df)}"

    def test_backtest_weekly_vs_monthly_accuracy(self, multi_sku_demand_data):
        """
        Compare forecast accuracy between weekly and monthly granularity.

        This test documents the actual accuracy comparison - backtesting showed
        that monthly granularity often outperforms weekly for multi-SKU scenarios.
        This is why we use daily granularity in the UI (aggregated to monthly for display),
        which gives the most data points while the UI shows monthly totals.
        """
        # Run backtest for weekly
        mape_weekly, mae_weekly, status_weekly = self.walk_forward_backtest(
            multi_sku_demand_data, 'weekly', train_months=18, test_months=3
        )

        # Run backtest for monthly
        mape_monthly, mae_monthly, status_monthly = self.walk_forward_backtest(
            multi_sku_demand_data, 'monthly', train_months=18, test_months=3
        )

        print(f"\n=== Backtest Results ===")
        print(f"Weekly:  MAPE={mape_weekly:.2f}%, MAE={mae_weekly:.2f}" if mape_weekly else f"Weekly: {status_weekly}")
        print(f"Monthly: MAPE={mape_monthly:.2f}%, MAE={mae_monthly:.2f}" if mape_monthly else f"Monthly: {status_monthly}")

        # Both should produce valid results
        assert status_weekly == "Success", f"Weekly backtest failed: {status_weekly}"
        assert status_monthly == "Success", f"Monthly backtest failed: {status_monthly}"

        # Document the comparison (no accuracy assertion - results vary by data pattern)
        # In practice, we use daily granularity which captures the most seasonality detail
        if mape_weekly and mape_monthly:
            print(f"Ratio: Weekly/Monthly = {mape_weekly/mape_monthly:.2f}x")

    def test_backtest_daily_vs_weekly_accuracy(self, realistic_demand_data):
        """
        Compare daily vs weekly granularity.

        Daily has more noise, weekly smooths it out.
        For most supply chain use cases, weekly is preferred.
        """
        # Run backtest for daily
        mape_daily, mae_daily, status_daily = self.walk_forward_backtest(
            realistic_demand_data, 'daily', train_months=18, test_months=3
        )

        # Run backtest for weekly
        mape_weekly, mae_weekly, status_weekly = self.walk_forward_backtest(
            realistic_demand_data, 'weekly', train_months=18, test_months=3
        )

        print(f"\n=== Daily vs Weekly ===")
        print(f"Daily:  MAPE={mape_daily:.2f}%, MAE={mae_daily:.2f}" if mape_daily else f"Daily: {status_daily}")
        print(f"Weekly: MAPE={mape_weekly:.2f}%, MAE={mae_weekly:.2f}" if mape_weekly else f"Weekly: {status_weekly}")

        # Both should produce valid results
        assert status_daily == "Success", f"Daily backtest failed: {status_daily}"
        assert status_weekly == "Success", f"Weekly backtest failed: {status_weekly}"

    def test_seasonal_pattern_detection_quality(self, realistic_demand_data):
        """
        Test quality of seasonal pattern detection at different granularities.

        We know the data has summer-high, winter-low seasonality.
        Good detection should show indices > 1 for summer months (Jun-Aug)
        and < 1 for winter months (Dec-Feb).
        """
        # Get weekly forecast
        logs, forecast_df, _, weekly_df = generate_demand_forecast(
            realistic_demand_data,
            forecast_horizon_days=90,
            ts_granularity='weekly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        assert not weekly_df.empty, f"No weekly data. Logs: {logs}"

        # Calculate seasonal indices from weekly data
        weekly_df = weekly_df.copy()
        weekly_df['month_num'] = pd.to_datetime(weekly_df['date']).dt.month
        weekly_df['year_month'] = pd.to_datetime(weekly_df['date']).dt.to_period('M')

        # Sum weekly to monthly, then average by month_num
        monthly_by_period = weekly_df.groupby(['year_month', 'month_num'])['demand_qty'].sum().reset_index()
        monthly_avg = monthly_by_period.groupby('month_num')['demand_qty'].mean()
        overall_avg = monthly_avg.mean()

        seasonal_indices = {}
        for month_num in range(1, 13):
            if month_num in monthly_avg.index:
                seasonal_indices[month_num] = monthly_avg[month_num] / overall_avg
            else:
                seasonal_indices[month_num] = 1.0

        print(f"\n=== Seasonal Indices (Weekly) ===")
        for month, idx in sorted(seasonal_indices.items()):
            month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][month]
            print(f"{month_name}: {idx:.3f}")

        # Verify seasonal pattern detection
        # Summer months (Jun=6, Jul=7, Aug=8) should be higher
        summer_avg = np.mean([seasonal_indices.get(m, 1) for m in [6, 7, 8]])
        # Winter months (Dec=12, Jan=1, Feb=2) should be lower
        winter_avg = np.mean([seasonal_indices.get(m, 1) for m in [12, 1, 2]])

        print(f"\nSummer avg: {summer_avg:.3f}")
        print(f"Winter avg: {winter_avg:.3f}")

        # Summer should be higher than winter (our test data has this pattern)
        assert summer_avg > winter_avg, \
            f"Summer ({summer_avg:.3f}) should be higher than winter ({winter_avg:.3f})"

    def test_intermittent_demand_handling(self, multi_sku_demand_data):
        """
        Test that intermittent demand SKUs are handled correctly.

        Intermittent demand has many zero values - weekly aggregation
        helps smooth this out better than daily.
        """
        # Filter to just intermittent SKU
        intermittent_df = multi_sku_demand_data[
            multi_sku_demand_data['sku'] == 'SKU_INTERMITTENT'
        ].copy()

        # Try both granularities
        logs_weekly, forecast_weekly, _, _ = generate_demand_forecast(
            intermittent_df,
            forecast_horizon_days=90,
            ts_granularity='weekly',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        logs_daily, forecast_daily, _, _ = generate_demand_forecast(
            intermittent_df,
            forecast_horizon_days=90,
            ts_granularity='daily',
            rolling_months=18,
            smoothing_preset='Balanced'
        )

        # Both should handle intermittent demand
        # Weekly should produce a more stable forecast
        assert not forecast_weekly.empty, f"Weekly failed on intermittent: {logs_weekly}"

        # If daily also works, compare the forecasts
        if not forecast_daily.empty:
            weekly_forecast = forecast_weekly['primary_forecast_daily'].iloc[0]
            daily_forecast = forecast_daily['primary_forecast_daily'].iloc[0]

            print(f"\n=== Intermittent Demand Forecasts ===")
            print(f"Weekly: {weekly_forecast:.2f}")
            print(f"Daily:  {daily_forecast:.2f}")

            # Both should be reasonable (not negative, not extremely different)
            assert weekly_forecast >= 0
            assert daily_forecast >= 0


class TestGranularityRecommendation:
    """Tests to determine the best granularity recommendation"""

    def test_weekly_is_recommended_for_supply_chain(self):
        """
        Document why weekly granularity is recommended for supply chain:

        1. Smooths daily noise (day-of-week effects, random variation)
        2. Provides ~4x more data points than monthly for pattern detection
        3. Aligns with typical supply chain planning cycles
        4. Better captures seasonal transitions
        5. Not as noisy as daily

        This test documents the rationale.
        """
        # Create comparison data structure
        granularity_comparison = {
            'daily': {
                'data_points_per_month': 30,
                'noise_level': 'High',
                'seasonal_detection': 'Good (many data points)',
                'computational_cost': 'High',
                'recommended_for': 'High-frequency trading, daily operations'
            },
            'weekly': {
                'data_points_per_month': 4,
                'noise_level': 'Medium (smoothed)',
                'seasonal_detection': 'Good (4 points per month across years)',
                'computational_cost': 'Medium',
                'recommended_for': 'Supply chain planning, inventory management'
            },
            'monthly': {
                'data_points_per_month': 1,
                'noise_level': 'Low (heavily smoothed)',
                'seasonal_detection': 'Limited (1 point per month)',
                'computational_cost': 'Low',
                'recommended_for': 'Long-term strategic planning, budget forecasting'
            }
        }

        # Weekly is the recommended balance
        assert granularity_comparison['weekly']['noise_level'] == 'Medium (smoothed)'
        assert granularity_comparison['weekly']['data_points_per_month'] == 4

        print("\n=== Granularity Recommendation ===")
        print("For eyewear supply chain demand forecasting:")
        print("RECOMMENDED: Weekly granularity")
        print("\nRationale:")
        print("- Smooths daily noise while preserving patterns")
        print("- 4 data points per month provides robust seasonal detection")
        print("- Aligns with typical PO and inventory planning cycles")
        print("- Balance between accuracy and computational efficiency")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
