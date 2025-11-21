import pytest
import pandas as pd
from pandas.testing import assert_frame_equal
import io
import sys
import os
from datetime import datetime

# Add the project root to the Python path to allow imports from the main directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_loader import (
    load_master_data,
    load_orders_item_lookup,
    load_orders_header_lookup,
    load_service_data,
    load_backorder_data
)

# --- Fixtures for reusable mock data ---

@pytest.fixture
def mock_master_data_csv():
    """Creates a mock CSV for master data with a duplicate SKU."""
    csv_data = """Material Number,PLM: Level Classification 4,Material Description
101,CAT-A,PRODUCT-A-DESC
102,CAT-A,PRODUCT-B-DESC
103,CAT-B,PRODUCT-C-DESC
101,CAT-A,PRODUCT-A-DESC-UPDATED
"""
    return "master_data.csv", io.StringIO(csv_data)

@pytest.fixture
def mock_orders_csv():
    """Creates a mock CSV for orders data with various data quality issues."""
    csv_data = (
        "Orders Detail - Order Document Number,Item - SAP Model Code,Order Creation Date: Date,Original Customer Name,Sales Organization Code,Item - Model Desc,Orders - TOTAL Orders Qty,Orders - TOTAL To Be Delivered Qty,Orders - TOTAL Cancelled Qty,Reject Reason Desc,Order Type (SAP) Code,Order Reason Code\n"
        # Standard M/D/YY format
        "SO-001,101,5/15/24,CUSTOMER-1,US20,PRODUCT-A,10,5,0,,TYPE-1,REASON-1\n"
        # Alternative YYYY-MM-DD format for the two-pass parser to catch
        "SO-002,102,2024-05-16,CUSTOMER-2,US20,PRODUCT-B,20,0,5,REASON-X,TYPE-2,REASON-2\n"
        # Bad date format
        "SO-003,103,INVALID-DATE,CUSTOMER-1,EU10,PRODUCT-C,30,0,0,,TYPE-1,REASON-1\n"
        # Line to be aggregated for SO-001
        "SO-001,101,5/15/24,CUSTOMER-1,US20,PRODUCT-A,15,0,0,,TYPE-1,REASON-1\n"
        # SKU not in master data (999) - will be dropped from backorder/service
        "SO-004,999,5/17/24,CUSTOMER-3,US20,PRODUCT-X,5,5,0,,TYPE-1,REASON-1\n"
    )
    return "orders.csv", io.StringIO(csv_data)

@pytest.fixture
def mock_deliveries_csv():
    """Creates a mock CSV for deliveries data."""
    csv_data = (
        # Delivery for SO-001
        "Deliveries Detail - Order Document Number,Item - SAP Model Code,Delivery Creation Date: Date,Deliveries - TOTAL Goods Issue Qty,Item - Model Desc\n"
        # Delivery for SO-001
        "SO-001,101,5/20/24,20,PRODUCT-A\n"
        # Delivery for an order that doesn't exist in our mock orders file
        "SO-999,999,5/21/24,100,PRODUCT-Z\n"
    )
    return "deliveries.csv", io.StringIO(csv_data)



@pytest.fixture(autouse=True)
def mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv, mock_deliveries_csv):
    """
    This fixture intercepts all calls to pd.read_csv and returns the appropriate
    in-memory mock CSV instead of reading from the disk.
    """
    # Store mocks in a dictionary
    mocks = {
        "master_data.csv": mock_master_data_csv[1],
        "orders.csv": mock_orders_csv[1],
        "deliveries.csv": mock_deliveries_csv[1]
    }

    # Keep a reference to the original read_csv
    original_read_csv = pd.read_csv

    def new_read_csv(filepath_or_buffer, *args, **kwargs):
        # Find the base name of the file path
        filename = os.path.basename(filepath_or_buffer)
        if filename in mocks:
            # If it's a mock, reset the stream and use it
            mocks[filename].seek(0)
            return original_read_csv(mocks[filename], *args, **kwargs)
        # Otherwise, call the original function (for safety, though not expected in tests)
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    # Replace the pandas read_csv function with our new one for the duration of the tests
    monkeypatch.setattr(pd, "read_csv", new_read_csv)


# --- Unit Tests ---

def test_load_master_data():
    """Tests that master data loads, renames columns, and handles duplicates."""
    logs, df, errors = load_master_data("master_data.csv")
    
    assert "WARNING: Found duplicated SKUs" in " ".join(logs)
    assert len(df) == 3 # Should drop the duplicate SKU '101'
    assert list(df.columns) == ['sku', 'category']
    assert df[df['sku'] == '101'].iloc[0]['category'] == 'CAT-A'

def test_load_orders_item_lookup_aggregation_and_dates():
    """
    Tests that orders are correctly aggregated and that the two-pass
    date parsing works for both M/D/YY and YYYY-MM-DD formats.
    """
    logs, df, errors = load_orders_item_lookup("orders.csv")

    # Check that the bad date was caught and dropped
    assert "ERROR: 1 order dates failed to parse" in " ".join(logs)
    assert len(df) == 2 # SO-003 with bad date should be dropped

    # Check aggregation of SO-001. It should be a single row.
    so1_row = df[df['sales_order'] == 'SO-001'].iloc[0]
    assert so1_row['ordered_qty'] == 25 # 10 + 15
    assert so1_row['backorder_qty'] == 5 # 5 + 0

    # Check date parsing
    assert so1_row['order_date'] == pd.to_datetime("2024-05-15")
    so2_row = df[df['sales_order'] == 'SO-002'].iloc[0]
    assert so2_row['order_date'] == pd.to_datetime("2024-05-16")

def test_load_orders_header_lookup():
    """Tests that the header-level lookup is created correctly."""
    logs, df = load_orders_header_lookup("orders.csv")

    assert len(df) == 2 # SO-003 with bad date should be dropped
    assert 'sales_order' in df.columns
    assert 'customer_name' in df.columns
    assert 'order_type' in df.columns
    # Check that item-specific columns are NOT present
    assert 'sku' not in df.columns
    assert 'ordered_qty' not in df.columns

def test_load_service_data_joins_and_calcs():
    """
    Tests that service data correctly joins with header data and that
    calculations like `days_to_deliver` are correct.
    """
    _, master_df, _ = load_master_data("master_data.csv")
    _, header_df = load_orders_header_lookup("orders.csv")

    logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

    # Check that the unmatched delivery (SO-999) was dropped
    assert "WARNING: 1 delivery lines did not find a matching order" in " ".join(logs)
    assert len(df) == 1
    assert df.iloc[0]['sales_order'] == 'SO-001'

    # Check calculations
    # Order date: 2024-05-15, Ship date: 2024-05-20
    assert df.iloc[0]['days_to_deliver'] == 5
    # Due date is order date + 7 days (2024-05-22). Shipped on 5/20, so it's on time
    assert df.iloc[0]['on_time'] == True

    # Check that columns from all 3 sources are present
    assert 'customer_name' in df.columns # from header
    assert 'units_issued' in df.columns # from delivery
    assert 'category' in df.columns # from master

def test_load_backorder_data_columns():
    """
    Tests that the backorder data loader correctly includes all columns
    needed for filtering in the dashboard and handles aggregation.
    """
    _, master_df, _ = load_master_data("master_data.csv")
    _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
    _, header_df = load_orders_header_lookup("orders.csv")

    logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

    # SO-001 has backorder_qty > 0 (5 units)
    # SO-004 has backorder_qty > 0 (5 units) but SKU 999 is not in master data, so it should be dropped.
    assert len(df) == 1
    assert df.iloc[0]['sales_order'] == 'SO-001'
    assert df.iloc[0]['product_name'] == 'PRODUCT-A-DESC'

    # Check for all columns used in the backorder report filters
    required_filter_cols = [
        'customer_name', 'category', 'product_name', 
        'sales_org', 'order_type', 'order_reason', 'order_year', 'order_month'
    ]
    for col in required_filter_cols:
        assert col in df.columns, f"Column '{col}' is missing from backorder_data"

    # Check error reporting for SKU not in master data
    assert "WARNING: 1 unique SKUs in backorder data were not found in Master Data" in " ".join(logs)
    assert not errors.empty
    assert len(errors) == 1
    assert errors.iloc[0]['sku'] == '999'
    assert errors.iloc[0]['ErrorType'] == 'SKU_Not_in_Master_Data'

def test_load_service_data_sku_mismatch():
    """
    Tests that the backorder data loader correctly includes all columns
    needed for filtering in the dashboard.
    """
    _, master_df, _ = load_master_data("master_data.csv")
    _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
    _, header_df = load_orders_header_lookup("orders.csv")

    # Mock deliveries with an SKU not in master data (SO-999, SKU 999)
    # The mock_deliveries_csv fixture already has SO-999, SKU 999

    logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

    # SO-001, SKU 101 should be present. SO-999, SKU 999 should be dropped.
    assert len(df) == 1
    assert df.iloc[0]['sales_order'] == 'SO-001'
    assert df.iloc[0]['sku'] == '101'
    assert df.iloc[0]['product_name'] == 'PRODUCT-A-DESC'

    # Check error reporting for SKU not in master data
    assert "WARNING: 1 rows in Service Data have SKUs not found in Master Data" in " ".join(logs)
    assert not errors.empty
    # There should be two errors: one for unmatched delivery, one for SKU not in master
    assert len(errors) == 2
    # Check the SKU_Not_in_Master_Data error
    sku_error = errors[errors['ErrorType'] == 'SKU_Not_in_Master_Data']
    assert not sku_error.empty
    assert sku_error.iloc[0]['sku'] == '999'
    assert sku_error.iloc[0]['ErrorType'] == 'SKU_Not_in_Master_Data'


def test_load_master_data_missing_column():
    """Tests graceful failure when a required column is missing."""
    bad_csv = "PLM: Level Classification 4,Brand\nCAT-A,BRAND-X"
    # Override the mock for this one test
    with pytest.MonkeyPatch.context() as m:
        m.setattr(pd, "read_csv", lambda *args, **kwargs: pd.read_csv(io.StringIO(bad_csv)))
        logs, df, _ = load_master_data("master_data.csv")
        assert "ERROR: 'Master Data.csv' is missing required columns: Material Number" in " ".join(logs)
        assert df.empty