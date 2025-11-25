import pytest
import pandas as pd

import dashboard_simple as app


def make_deliveries():
    # Minimal provenance: a single SKU with a few daily records
    return pd.DataFrame({
        'Item - SAP Model Code': ['SKU1', 'SKU1', 'SKU1'],
        'Delivery Creation Date: Date': ['5/01/24', '6/01/24', '7/01/24'],
        'Deliveries - TOTAL Goods Issue Qty': [10, 15, 5]
    })


def make_master():
    return pd.DataFrame([{'Material Number':'SKU1', 'PLM: Level Classification 4':'RETAIL PERMANENT'}])


def test_dashboard_wrapper_passes_rolling12(monkeypatch):
    """Ensure the dashboard wrapper forwards Rolling 12 months -> monthly + rolling_months=12"""

    calls = {}

    def fake_generate(deliveries_df, master_data_df=None, forecast_horizon_days=90, ts_granularity='daily', rolling_months=None):
        calls['ts_granularity'] = ts_granularity
        calls['rolling_months'] = rolling_months
        return [], pd.DataFrame([{'sku':'SKU1'}]), pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(app, 'generate_demand_forecast', fake_generate)

    # Call the module-level wrapper with ts_mode matching the UI label
    logs, f_df, a_df, ts_df = app.compute_forecast_wrapper(make_deliveries(), make_master(), 90, ts_mode='Rolling 12 months (monthly)')

    assert calls['ts_granularity'] == 'monthly'
    assert calls['rolling_months'] == 12
