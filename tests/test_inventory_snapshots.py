import pandas as pd
import os
import sys

# Add project root to path
current_file_path = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file_path))
sys.path.insert(0, project_root)

from data_loader import load_inventory_analysis_data, load_deliveries_unified, load_master_data, TODAY

# Real file paths
DELIVERIES_PATH = os.path.join(project_root, "DELIVERIES.csv")
MASTER_DATA_PATH = os.path.join(project_root, "Master Data.csv")


def test_inventory_analysis_builds_monthly_inventory_pivot():
    """
    Test that load_inventory_analysis_data correctly builds inv_m_YYYY_MM columns
    when given inventory snapshot data with 'Current Date' column.
    """
    # Load real deliveries and master data to get valid SKUs
    _logs, deliveries_df = load_deliveries_unified(DELIVERIES_PATH)
    _logs, master_df, _ = load_master_data(MASTER_DATA_PATH)

    # Get some real SKUs from the deliveries data
    if deliveries_df.empty or 'Item - SAP Model Code' not in deliveries_df.columns:
        # If no deliveries, skip the test
        import pytest
        pytest.skip("No deliveries data available for test")

    real_skus = deliveries_df['Item - SAP Model Code'].dropna().unique()[:2].tolist()
    if len(real_skus) < 2:
        import pytest
        pytest.skip("Not enough SKUs in deliveries data for test")

    # Build a small time-series-style inventory dataframe with snapshot rows for 3 months
    # using REAL SKUs from the deliveries data
    latest_month = TODAY.replace(day=1)
    months = [(latest_month - pd.DateOffset(months=i)) for i in range(3)]

    rows = []
    for sku in real_skus:
        for i, m in enumerate(months):
            rows.append({'sku': sku, 'on_hand_qty': 100*(i+1), 'Current Date': m.strftime('%m/%d/%y')})

    inv_df = pd.DataFrame(rows)

    logs, analysis_df = load_inventory_analysis_data(inv_df, deliveries_df, master_df)

    # Expect inventory time-series columns like inv_m_YYYY_MM for the last months
    inv_month_cols = [c for c in analysis_df.columns if c.startswith('inv_m_')]
    assert len(inv_month_cols) >= 1, f"Expected inventory monthly columns, found: {inv_month_cols}. Logs: {logs}"

    # DIO should still be present and numeric
    assert 'dio' in analysis_df.columns
    assert pd.api.types.is_numeric_dtype(analysis_df['dio'])
