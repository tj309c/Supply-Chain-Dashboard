"""
Test script for demand forecasting module
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from demand_forecasting import generate_demand_forecast

# Create sample deliveries data
print("Creating sample delivery data...")

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

deliveries_df = pd.DataFrame({
    'sku': skus,
    'delivery_date': dates,
    'delivered_qty': qtys
})

print(f"Created {len(deliveries_df)} delivery records")
print(f"Date range: {deliveries_df['delivery_date'].min()} to {deliveries_df['delivery_date'].max()}")
print(f"SKUs: {deliveries_df['sku'].nunique()}")

# Test forecast generation
print("\nGenerating forecasts...")
logs, forecast_df, accuracy_df = generate_demand_forecast(deliveries_df, forecast_horizon_days=90)

# Print logs
print("\n=== FORECAST GENERATION LOGS ===")
for log in logs:
    print(log)

# Validate results
print("\n=== FORECAST VALIDATION ===")
if not forecast_df.empty:
    print(f"SUCCESS: Generated forecasts for {len(forecast_df)} SKUs")
    print(f"Forecast columns: {len(forecast_df.columns)}")
    print(f"\nForecast Summary:")
    print(forecast_df[['sku', 'forecast_method', 'primary_forecast_daily', 'forecast_total_qty',
                        'forecast_confidence', 'demand_pattern']].to_string())

    if not accuracy_df.empty:
        print(f"\nAccuracy metrics calculated for {len(accuracy_df)} SKUs")
        print(f"\nAccuracy Summary:")
        print(accuracy_df[['sku', 'mape', 'mae']].to_string())
    else:
        print("\nNo accuracy metrics (expected for short history)")
else:
    print("ERROR: No forecasts generated")

print("\n=== TEST COMPLETE ===")
