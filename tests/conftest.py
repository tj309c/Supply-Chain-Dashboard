"""
Pytest configuration and shared fixtures for all tests
Centralized mock data and utilities
"""

import pytest
import pandas as pd
import io
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# ===== SHARED MOCK DATA FIXTURES =====

@pytest.fixture
def mock_master_data_csv():
    """
    Creates mock master data CSV with:
    - Multiple SKUs and categories
    - Duplicate SKU to test deduplication
    - Various product descriptions
    - Activation dates and PLM fields
    """
    csv_data = """Material Number,PLM: Level Classification 4,Activation Date (Code),PLM: PLM Current Status,PLM: Expiration Date
101,CAT-A,1/1/23,Active,20251231
102,CAT-A,2/1/23,Active,20261231
103,CAT-B,3/1/23,Active,20271231
104,CAT-C,4/1/23,Active,20281231
101,CAT-A,1/1/23,Active,20251231
"""
    return "master_data.csv", io.StringIO(csv_data)

@pytest.fixture
def mock_orders_csv():
    """
    Creates mock orders CSV with various scenarios:
    - Standard M/D/YY date format
    - Alternative YYYY-MM-DD date format
    - Invalid date format (should be handled gracefully)
    - Multiple lines for same order (test aggregation)
    - SKU not in master data (test error handling)
    - Different order types and reasons
    """
    csv_data = (
        "Orders Detail - Order Document Number,Item - SAP Model Code,Order Creation Date: Date,"
        "Original Customer Name,Sales Organization Code,Item - Model Desc,Orders - TOTAL Orders Qty,"
        "Orders - TOTAL To Be Delivered Qty,Orders - TOTAL Cancelled Qty,Reject Reason Desc,"
        "Order Type (SAP) Code,Order Reason Code\n"
        # Standard order
        "SO-001,101,5/15/24,CUSTOMER-1,US20,PRODUCT-A,10,5,0,,TYPE-1,REASON-1\n"
        # Alternative date format
        "SO-002,102,2024-05-16,CUSTOMER-2,US20,PRODUCT-B,20,0,5,REASON-X,TYPE-2,REASON-2\n"
        # Bad date format
        "SO-003,103,INVALID-DATE,CUSTOMER-1,EU10,PRODUCT-C,30,0,0,,TYPE-1,REASON-1\n"
        # Additional line for SO-001 (test aggregation)
        "SO-001,101,5/15/24,CUSTOMER-1,US20,PRODUCT-A,15,0,0,,TYPE-1,REASON-1\n"
        # SKU not in master data
        "SO-004,999,5/17/24,CUSTOMER-3,US20,PRODUCT-X,5,5,0,,TYPE-1,REASON-1\n"
        # Order with backorder
        "SO-005,104,5/18/24,CUSTOMER-2,US20,PRODUCT-D,50,10,0,,TYPE-1,REASON-1\n"
    )
    return "orders.csv", io.StringIO(csv_data)

@pytest.fixture
def mock_deliveries_csv():
    """
    Creates mock deliveries CSV with:
    - Valid delivery for existing order
    - Delivery for non-existent order (test error handling)
    - Multiple delivery dates
    """
    csv_data = (
        "Deliveries Detail - Order Document Number,Item - SAP Model Code,"
        "Delivery Creation Date: Date,Deliveries - TOTAL Goods Issue Qty,Item - Model Desc\n"
        # Delivery for SO-001
        "SO-001,101,5/20/24,20,PRODUCT-A\n"
        # Delivery for SO-005
        "SO-005,104,5/25/24,15,PRODUCT-D\n"
        # Delivery for non-existent order
        "SO-999,999,5/21/24,100,PRODUCT-Z\n"
    )
    return "deliveries.csv", io.StringIO(csv_data)

@pytest.fixture
def mock_inventory_csv():
    """
    Creates mock inventory CSV for testing inventory analysis
    """
    csv_data = """Material Number,POP Actual Stock Qty,POP Actual Stock in Transit Qty,POP Last Purchase: Price in Purch. Currency,POP Last Purchase: Currency,Storage Location: Code,Material Description,Brand,POP Last Purchase: Date
101,1000,100,50.00,USD,WH01,PRODUCT-A,BRAND-A,1/1/24
102,500,50,75.00,USD,WH01,PRODUCT-B,BRAND-A,2/1/24
103,2500,250,25.00,EUR,WH02,PRODUCT-C,BRAND-B,3/1/24
104,750,75,100.00,GBP,WH01,PRODUCT-D,BRAND-C,4/1/24
"""
    return "inventory.csv", io.StringIO(csv_data)

# ===== MOCK CSV READER FIXTURE =====

@pytest.fixture(autouse=True)
def mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv,
                   mock_deliveries_csv, mock_inventory_csv):
    """
    Auto-used fixture that intercepts all pd.read_csv calls and returns
    appropriate mock data. This allows tests to run without real CSV files.

    The fixture maps filenames to mock data streams.
    """
    # Store all mocks in a dictionary
    mocks = {
        "master_data.csv": mock_master_data_csv[1],
        "orders.csv": mock_orders_csv[1],
        "deliveries.csv": mock_deliveries_csv[1],
        "inventory.csv": mock_inventory_csv[1],
    }

    # Keep reference to original read_csv
    original_read_csv = pd.read_csv

    def new_read_csv(filepath_or_buffer, *args, **kwargs):
        """
        Replacement read_csv that checks if file is a mock,
        otherwise falls back to original function
        """
        # Extract filename from path
        if isinstance(filepath_or_buffer, str):
            filename = os.path.basename(filepath_or_buffer)
            if filename in mocks:
                # Reset stream position and return mock data
                mocks[filename].seek(0)
                return original_read_csv(mocks[filename], *args, **kwargs)

        # Fall back to original for non-mocked files
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    # Replace pandas read_csv for duration of test session
    monkeypatch.setattr(pd, "read_csv", new_read_csv)

# ===== HELPER FIXTURES =====

@pytest.fixture
def sample_dataframe():
    """Returns a simple DataFrame for general testing"""
    return pd.DataFrame({
        'id': [1, 2, 3],
        'value': [10, 20, 30],
        'category': ['A', 'B', 'A']
    })

@pytest.fixture
def empty_dataframe():
    """Returns an empty DataFrame"""
    return pd.DataFrame()

# ===== UTILITY FUNCTIONS FOR TESTS =====

def assert_log_contains(logs, expected_message):
    """
    Helper to assert that a log message contains expected text

    Args:
        logs: List of log messages
        expected_message: Text expected to be in one of the logs
    """
    log_text = " ".join(logs)
    assert expected_message in log_text, f"Expected '{expected_message}' not found in logs: {log_text}"

def assert_columns_exist(df, columns):
    """
    Helper to assert that DataFrame contains required columns

    Args:
        df: Pandas DataFrame
        columns: List of column names that should exist
    """
    missing = set(columns) - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"

def assert_no_nulls(df, columns):
    """
    Helper to assert that specified columns have no null values

    Args:
        df: Pandas DataFrame
        columns: List of column names to check
    """
    for col in columns:
        null_count = df[col].isna().sum()
        assert null_count == 0, f"Column '{col}' has {null_count} null values"
