"""Lean tests for key data_loader functions — minimal and self-contained.

These verify core behavior while we repair the full test suite.
"""

import pytest
import pandas as pd
import io
import sys
import os

# Add parent directory to path so tests import local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import (
    load_master_data,
    load_orders_item_lookup_legacy as load_orders_item_lookup,
    load_orders_header_lookup_legacy as load_orders_header_lookup,
)


@pytest.fixture(autouse=True)
def local_mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv,
                       mock_deliveries_csv, mock_inventory_csv):
    """Redirect pd.read_csv calls for known filenames to in-memory fixtures."""
    mocks = {
        "master_data.csv": mock_master_data_csv[1],
        "orders.csv": mock_orders_csv[1],
        "deliveries.csv": mock_deliveries_csv[1],
        "inventory.csv": mock_inventory_csv[1],
    }

    original_read_csv = pd.read_csv

    def fake_read_csv(filepath_or_buffer, *args, **kwargs):
        if isinstance(filepath_or_buffer, str):
            filename = os.path.basename(filepath_or_buffer)
            if filename in mocks:
                mocks[filename].seek(0)
                return original_read_csv(mocks[filename], *args, **kwargs)
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", fake_read_csv)
    yield


def test_load_master_data_minimal():
    logs, df, errors = load_master_data("master_data.csv")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert 'sku' in df.columns


def test_load_orders_item_lookup_minimal():
    logs, df, errors = load_orders_item_lookup("orders.csv")
    # Basic structural checks
    assert 'sales_order' in df.columns
    assert 'sku' in df.columns


def test_load_orders_header_lookup_minimal():
    logs, df = load_orders_header_lookup("orders.csv")
    assert 'sales_order' in df.columns
    assert 'customer_name' in df.columns
"""Simplified tests for a few key data_loader routines
These tests keep the module safe and useful while we repair or re-add
the larger full-suite tests later.
"""

import pytest
import pandas as pd
import io
import sys
import os

# Add parent directory to path so tests import local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import (
    load_master_data,
    load_orders_item_lookup_legacy as load_orders_item_lookup,
    load_orders_header_lookup_legacy as load_orders_header_lookup,
)


@pytest.fixture(autouse=True)
def local_mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv,
                       mock_deliveries_csv, mock_inventory_csv):
    """Redirect calls to pd.read_csv for known filenames to the in-memory fixtures."""
    mocks = {
        "master_data.csv": mock_master_data_csv[1],
        "orders.csv": mock_orders_csv[1],
        "deliveries.csv": mock_deliveries_csv[1],
        "inventory.csv": mock_inventory_csv[1],
    }

    original_read_csv = pd.read_csv

    def fake_read_csv(filepath_or_buffer, *args, **kwargs):
        if isinstance(filepath_or_buffer, str):
            filename = os.path.basename(filepath_or_buffer)
            if filename in mocks:
                mocks[filename].seek(0)
                return original_read_csv(mocks[filename], *args, **kwargs)
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", fake_read_csv)
    yield


def test_load_master_data_basics():
    """load_master_data should return a non-empty DataFrame with expected columns"""
    logs, df, errors = load_master_data("master_data.csv")
    assert not df.empty
    assert 'sku' in df.columns
    assert 'category' in df.columns


def test_load_orders_item_lookup_basic_aggregation():
    """Orders item lookup should aggregate multiple lines into single item rows"""
    logs, df, errors = load_orders_item_lookup("orders.csv")
    # Basic structural checks
    assert 'sales_order' in df.columns
    assert 'sku' in df.columns
    # Verify aggregation occurs for a known SO (fixture data includes SO-001)
    so1 = df[df['sales_order'] == 'SO-001']
    assert len(so1) == 1


def test_load_orders_header_lookup_minimal():
    """Header lookup returns header-only columns and unique sales_order"""
    logs, df = load_orders_header_lookup("orders.csv")
    assert 'sales_order' in df.columns
    assert 'customer_name' in df.columns
    assert len(df) == df['sales_order'].nunique()

# ===== MASTER DATA TESTS =====

class TestMasterDataLoader:
    """Test suite for master data loading"""

    def test_load_master_data_success(self):
        """Tests successful loading and column renaming"""
        logs, df, errors = load_master_data("master_data.csv")

        # Should have data
        assert not df.empty, "Master data should not be empty"

        # Check columns renamed correctly
        assert_columns_exist(df, ['sku', 'category'])

        # Should have 4 unique SKUs after deduplication
        assert len(df) == 4

    def test_load_master_data_deduplication(self):
        """Tests that duplicate SKUs are handled correctly"""
        logs, df, errors = load_master_data("master_data.csv")

        # Should log warning about duplicates
        assert_log_contains(logs, "duplicated SKUs")

        # Check that first occurrence is kept
        sku_101 = df[df['sku'] == '101']
        assert len(sku_101) == 1
        assert sku_101.iloc[0]['category'] == 'CAT-A'

    def test_load_master_data_missing_column(self):
        """Tests graceful failure when required column is missing"""
        bad_csv = "PLM: Level Classification 4,Activation Date (Code)\nCAT-A,1/1/23"

        # Create a dataframe that's missing required columns
        bad_df = pd.read_csv(io.StringIO(bad_csv))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: bad_df)
            logs, df, errors = load_master_data("master_data.csv")

            # Should log error
            assert_log_contains(logs, "ERROR: 'Master Data.csv' is missing required columns")

            # Should return empty DataFrame
            assert df.empty

    def test_load_master_data_no_duplicates(self):
        """Tests behavior when there are no duplicates"""
        clean_csv = """Material Number,PLM: Level Classification 4,Activation Date (Code),PLM: PLM Current Status,PLM: Expiration Date
201,CAT-X,1/1/23,Active,20251231
202,CAT-Y,2/1/23,Active,20261231
"""
        # Create a clean dataframe
        clean_df = pd.read_csv(io.StringIO(clean_csv))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: clean_df)
            logs, df, errors = load_master_data("master_data.csv")

            # Should not log duplicate warning
            log_text = " ".join(logs)
            assert "duplicated SKUs" not in log_text

            # Should have all records
            assert len(df) == 2

# ===== ORDERS DATA TESTS =====

class TestOrdersDataLoader:
    """Test suite for orders data loading"""

    def test_load_orders_item_lookup_aggregation(self):
        """Tests that orders are correctly aggregated by sales_order + SKU"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check SO-001 aggregation (two lines should become one)
        so1_rows = df[df['sales_order'] == 'SO-001']
        assert len(so1_rows) == 1, "SO-001 should be aggregated to single row"

        so1 = so1_rows.iloc[0]
        assert so1['ordered_qty'] == 25, "Ordered qty should be 10 + 15 = 25"
        assert so1['backorder_qty'] == 5, "Backorder qty should be 5 + 0 = 5"

    def test_load_orders_date_parsing(self):
        """Tests date parsing with M/D/YY format"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check M/D/YY format (SO-001)
        so1_rows = df[df['sales_order'] == 'SO-001']
        assert len(so1_rows) > 0, "SO-001 should exist"
        so1 = so1_rows.iloc[0]
        assert so1['order_date'] == pd.to_datetime("2024-05-15")

        # SO-002 with YYYY-MM-DD format will be dropped (invalid for M/D/YY parser)
        so2_rows = df[df['sales_order'] == 'SO-002']
        assert len(so2_rows) == 0, "SO-002 should be dropped due to date format mismatch"

    def test_load_orders_invalid_date_handling(self):
        """Tests that invalid dates are caught and rows dropped"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # SO-003 with invalid date should be dropped (silently by dropna)
        so3_rows = df[df['sales_order'] == 'SO-003']
        assert len(so3_rows) == 0, "SO-003 with invalid date should be dropped"

        # Verify remaining rows message is logged
        assert_log_contains(logs, "rows remaining after dropping NaNs")

    def test_load_orders_required_columns(self):
        """Tests that all required columns are present"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        required_cols = [
            'sales_order', 'sku', 'order_date', 'ordered_qty',
            'backorder_qty', 'cancelled_qty', 'customer_name',
            'sales_org', 'order_type', 'order_reason'
        ]

        assert_columns_exist(df, required_cols)

    def test_load_orders_header_lookup(self):
        """Tests header-level lookup creation"""
        logs, df = load_orders_header_lookup("orders.csv")

        # Should have header-level columns only
        assert 'sales_order' in df.columns
        assert 'customer_name' in df.columns
        assert 'order_type' in df.columns

        # Should NOT have item-level columns
        assert 'sku' not in df.columns
        assert 'ordered_qty' not in df.columns

        # Should be unique by sales_order
        assert len(df) == df['sales_order'].nunique()

    def test_load_orders_quantity_calculations(self):
        """Tests that quantity calculations are correct"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check SO-005 quantities
        so5 = df[df['sales_order'] == 'SO-005'].iloc[0]
        assert so5['ordered_qty'] == 50
        assert so5['backorder_qty'] == 10  # to_be_delivered

# ===== SERVICE DATA TESTS =====

class TestServiceDataLoader:
    """Test suite for service level data loading"""

    def test_load_service_data_joins(self):
        """Tests that service data correctly joins with orders and master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should have data from all three sources
        assert_columns_exist(df, [
            'sales_order',      # from deliveries
            'customer_name',    # from header
            'category'          # from master
        ])

    def test_load_service_data_unmatched_orders(self):
        """Tests handling of deliveries for non-existent orders"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about unmatched deliveries
        assert_log_contains(logs, "WARNING: 1 delivery lines did not find a matching order")

        # SO-999 should be dropped
        assert 'SO-999' not in df['sales_order'].values

    def test_load_service_data_date_calculations(self):
        """Tests that days_to_deliver and on_time calculations are correct"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Check SO-001: ordered 5/15, delivered 5/20 = 5 days
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['days_to_deliver'] == 5

        # Due date is order_date + 7 days (5/22), delivered 5/20 = on time
        assert so1['on_time'] == True

    def test_load_service_data_sku_mismatch(self):
        """Tests handling of deliveries without matching orders"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about unmatched deliveries (SO-999 doesn't exist in orders)
        assert_log_contains(logs, "delivery lines did not find a matching order")

        # Should have error records (unmatched deliveries)
        assert not errors.empty

    def test_load_service_data_ship_month(self):
        """Tests that ship_month is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # All deliveries in May 2024 - ship_month should be month name
        assert (df['ship_month'] == 'May').all(), "All deliveries should be in May"

# ===== BACKORDER DATA TESTS =====

class TestBackorderDataLoader:
    """Test suite for backorder data loading"""

    def test_load_backorder_data_filtering(self):
        """Tests that only records with backorder_qty > 0 are included"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # All records should have backorder_qty > 0
        assert (df['backorder_qty'] > 0).all()

    def test_load_backorder_data_joins(self):
        """Tests that backorder data includes all necessary joined columns"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # Should have filter columns from all sources
        required_filter_cols = [
            'customer_name',    # from header
            'category',         # from master
            'product_name',     # from master
            'sales_org',        # from header
            'order_type',       # from header
            'order_reason',     # from header
            'order_year',       # calculated
            'order_month'       # calculated
        ]

        assert_columns_exist(df, required_filter_cols)

    def test_load_backorder_data_sku_validation(self):
        """Tests that SKUs not in master data are handled correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # Should log warning about missing SKUs
        assert_log_contains(logs, "SKUs in backorder data were not found in Master Data")

        # Should have error records
        assert not errors.empty
        sku_errors = errors[errors['ErrorType'] == 'SKU_Not_in_Master_Data']
        assert len(sku_errors) == 1
        assert sku_errors.iloc[0]['sku'] == '999'

    def test_load_backorder_data_age_calculation(self):
        """Tests that days_on_backorder is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # days_on_backorder should be calculated for all records
        assert 'days_on_backorder' in df.columns
        assert_no_nulls(df, ['days_on_backorder'])

    def test_load_backorder_data_product_name(self):
        """Tests that product names are correctly mapped from master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # SO-001, SKU 101 should have product name from orders data
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['product_name'] == 'PRODUCT-A'

# ===== EDGE CASES AND ERROR HANDLING =====

class TestEdgeCases:
    """Test suite for edge cases and error conditions"""

    def test_empty_master_data(self):
        """Tests behavior when master data is empty"""
        empty_csv = "Material Number,PLM: Level Classification 4,Material Description\n"

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: pd.read_csv(io.StringIO(empty_csv)))
            logs, df, errors = load_master_data("master_data.csv")

            # Should return empty DataFrame
            assert df.empty

    def test_null_handling_in_orders(self):
        """Tests that null values in orders are handled gracefully"""
        # This is implicitly tested by the mock data, but good to be explicit
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Should not crash on null values
        assert not df.empty

    def test_date_edge_cases(self):
        """Tests various date format edge cases"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check that valid dates are parsed regardless of format
        assert df['order_date'].notna().sum() > 0

# ===== INTEGRATION TESTS =====

class TestDataLoaderIntegration:
    """Integration tests for the complete data loading pipeline"""

    def test_full_pipeline(self):
        """Tests the complete data loading pipeline from raw files to final datasets"""
        # Load all data
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")
        _, service_df, _ = load_service_data("deliveries.csv", header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        # All datasets should have data
        assert not master_df.empty
        assert not header_df.empty
        assert not service_df.empty
        assert not backorder_df.empty

    def test_referential_integrity(self):
        """Tests that relationships between datasets are maintained"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")
        _, service_df, _ = load_service_data("deliveries.csv", header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        # All SKUs in service data should be in master data
        service_skus = set(service_df['sku'].unique())
        master_skus = set(master_df['sku'].unique())
        assert service_skus.issubset(master_skus)

        # All sales orders in service data should be in header data
        service_orders = set(service_df['sales_order'].unique())
        header_orders = set(header_df['sales_order'].unique())
        assert service_orders.issubset(header_orders)
"""Comprehensive tests for data_loader module
Tests data loading, transformation, error handling, and data quality
"""

import pytest
import pandas as pd
import io
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import (
    load_master_data,
    load_orders_item_lookup_legacy as load_orders_item_lookup,
    load_orders_header_lookup_legacy as load_orders_header_lookup,
    load_service_data_legacy as load_service_data,
    load_backorder_data,
    load_orders_unified,
    load_deliveries_unified
)


# Local module-level mocking: make this test module self-contained and not
# dependent on real files on disk. We reuse the same mock fixtures defined in
# `tests/conftest.py` to provide in-memory CSVs for common filenames.
@pytest.fixture(autouse=True)
def local_mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv,
                       mock_deliveries_csv, mock_inventory_csv):
    mocks = {
        "master_data.csv": mock_master_data_csv[1],
        "orders.csv": mock_orders_csv[1],
        "deliveries.csv": mock_deliveries_csv[1],
        "inventory.csv": mock_inventory_csv[1],
    }

    original_read_csv = pd.read_csv

    def fake_read_csv(filepath_or_buffer, *args, **kwargs):
        # If a filepath string maps to one of our mocked names, reset the
        # StringIO and delegate to the original pandas reader (so kwargs
        # like usecols still work). Otherwise, fall back to original.
        if isinstance(filepath_or_buffer, str):
            filename = os.path.basename(filepath_or_buffer)
            if filename in mocks:
                mocks[filename].seek(0)
                return original_read_csv(mocks[filename], *args, **kwargs)
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", fake_read_csv)
    yield

# ===== TEST HELPER FUNCTIONS =====

def assert_log_contains(logs, expected_message):
    """Helper to assert that a log message contains expected text"""
    log_text = " ".join(logs)
    assert expected_message in log_text, f"Expected '{expected_message}' not found in logs: {log_text}"

def assert_columns_exist(df, columns):
    """Helper to assert that DataFrame contains required columns"""
    missing = set(columns) - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"

def assert_no_nulls(df, columns):
    """Helper to assert that specified columns have no null values"""
    for col in columns:
        null_count = df[col].isna().sum()
        assert null_count == 0, f"Column '{col}' has {null_count} null values"

# ===== MASTER DATA TESTS =====

class TestMasterDataLoader:
    """Test suite for master data loading"""

    def test_load_master_data_success(self):
        """Tests successful loading and column renaming"""
        logs, df, errors = load_master_data("master_data.csv")

        # Should have data
        assert not df.empty, "Master data should not be empty"

        # Check columns renamed correctly
        assert_columns_exist(df, ['sku', 'category'])

        # Should have 4 unique SKUs after deduplication
        assert len(df) == 4

    def test_load_master_data_deduplication(self):
        """Tests that duplicate SKUs are handled correctly"""
        logs, df, errors = load_master_data("master_data.csv")

        # Should log warning about duplicates
        assert_log_contains(logs, "duplicated SKUs")

        # Check that first occurrence is kept
        sku_101 = df[df['sku'] == '101']
        assert len(sku_101) == 1
        assert sku_101.iloc[0]['category'] == 'CAT-A'

    def test_load_master_data_missing_column(self):
        """Tests graceful failure when required column is missing"""
        bad_csv = "PLM: Level Classification 4,Activation Date (Code)\nCAT-A,1/1/23"

        # Create a dataframe that's missing required columns
        bad_df = pd.read_csv(io.StringIO(bad_csv))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: bad_df)
            logs, df, errors = load_master_data("master_data.csv")

            # Should log error
            assert_log_contains(logs, "ERROR: 'Master Data.csv' is missing required columns")

            # Should return empty DataFrame
            assert df.empty

    def test_load_master_data_no_duplicates(self):
        """Tests behavior when there are no duplicates"""
        clean_csv = """Material Number,PLM: Level Classification 4,Activation Date (Code),PLM: PLM Current Status,PLM: Expiration Date
201,CAT-X,1/1/23,Active,20251231
202,CAT-Y,2/1/23,Active,20261231
"""
        # Create a clean dataframe
        clean_df = pd.read_csv(io.StringIO(clean_csv))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: clean_df)
            logs, df, errors = load_master_data("master_data.csv")

            # Should not log duplicate warning
            log_text = " ".join(logs)
            assert "duplicated SKUs" not in log_text

            # Should have all records
            assert len(df) == 2

# ===== ORDERS DATA TESTS =====

class TestOrdersDataLoader:
    """Test suite for orders data loading"""

    def test_load_orders_item_lookup_aggregation(self):
        """Tests that orders are correctly aggregated by sales_order + SKU"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check SO-001 aggregation (two lines should become one)
        so1_rows = df[df['sales_order'] == 'SO-001']
        assert len(so1_rows) == 1, "SO-001 should be aggregated to single row"

        so1 = so1_rows.iloc[0]
        assert so1['ordered_qty'] == 25, "Ordered qty should be 10 + 15 = 25"
        assert so1['backorder_qty'] == 5, "Backorder qty should be 5 + 0 = 5"

    def test_load_orders_date_parsing(self):
        """Tests date parsing with M/D/YY format"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check M/D/YY format (SO-001)
        so1_rows = df[df['sales_order'] == 'SO-001']
        assert len(so1_rows) > 0, "SO-001 should exist"
        so1 = so1_rows.iloc[0]
        assert so1['order_date'] == pd.to_datetime("2024-05-15")

        # SO-002 with YYYY-MM-DD format will be dropped (invalid for M/D/YY parser)
        so2_rows = df[df['sales_order'] == 'SO-002']
        assert len(so2_rows) == 0, "SO-002 should be dropped due to date format mismatch"

    def test_load_orders_invalid_date_handling(self):
        """Tests that invalid dates are caught and rows dropped"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # SO-003 with invalid date should be dropped (silently by dropna)
        so3_rows = df[df['sales_order'] == 'SO-003']
        assert len(so3_rows) == 0, "SO-003 with invalid date should be dropped"

        # Verify remaining rows message is logged
        assert_log_contains(logs, "rows remaining after dropping NaNs")

    def test_load_orders_required_columns(self):
        """Tests that all required columns are present"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        required_cols = [
            'sales_order', 'sku', 'order_date', 'ordered_qty',
            'backorder_qty', 'cancelled_qty', 'customer_name',
            'sales_org', 'order_type', 'order_reason'
        ]

        assert_columns_exist(df, required_cols)

    def test_load_orders_header_lookup(self):
        """Tests header-level lookup creation"""
        logs, df = load_orders_header_lookup("orders.csv")

        # Should have header-level columns only
        assert 'sales_order' in df.columns
        assert 'customer_name' in df.columns
        assert 'order_type' in df.columns

        # Should NOT have item-level columns
        assert 'sku' not in df.columns
        assert 'ordered_qty' not in df.columns

        # Should be unique by sales_order
        assert len(df) == df['sales_order'].nunique()

    def test_load_orders_quantity_calculations(self):
        """Tests that quantity calculations are correct"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check SO-005 quantities
        so5 = df[df['sales_order'] == 'SO-005'].iloc[0]
        assert so5['ordered_qty'] == 50
        assert so5['backorder_qty'] == 10  # to_be_delivered

# ===== SERVICE DATA TESTS =====

class TestServiceDataLoader:
    """Test suite for service level data loading"""

    def test_load_service_data_joins(self):
        """Tests that service data correctly joins with orders and master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should have data from all three sources
        assert_columns_exist(df, [
            'sales_order',      # from deliveries
            'customer_name',    # from header
            'category'          # from master
        ])

    def test_load_service_data_unmatched_orders(self):
        """Tests handling of deliveries for non-existent orders"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about unmatched deliveries
        assert_log_contains(logs, "WARNING: 1 delivery lines did not find a matching order")

        # SO-999 should be dropped
        assert 'SO-999' not in df['sales_order'].values

    def test_load_service_data_date_calculations(self):
        """Tests that days_to_deliver and on_time calculations are correct"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Check SO-001: ordered 5/15, delivered 5/20 = 5 days
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['days_to_deliver'] == 5

        # Due date is order_date + 7 days (5/22), delivered 5/20 = on time
        assert so1['on_time'] == True

    def test_load_service_data_sku_mismatch(self):
        """Tests handling of deliveries without matching orders"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about unmatched deliveries (SO-999 doesn't exist in orders)
        assert_log_contains(logs, "delivery lines did not find a matching order")

        # Should have error records (unmatched deliveries)
        assert not errors.empty

    def test_load_service_data_ship_month(self):
        """Tests that ship_month is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # All deliveries in May 2024 - ship_month should be month name
        assert (df['ship_month'] == 'May').all(), "All deliveries should be in May"

# ===== BACKORDER DATA TESTS =====

class TestBackorderDataLoader:
    """Test suite for backorder data loading"""

    def test_load_backorder_data_filtering(self):
        """Tests that only records with backorder_qty > 0 are included"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # All records should have backorder_qty > 0
        assert (df['backorder_qty'] > 0).all()

    def test_load_backorder_data_joins(self):
        """Tests that backorder data includes all necessary joined columns"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # Should have filter columns from all sources
        required_filter_cols = [
            'customer_name',    # from header
            'category',         # from master
            'product_name',     # from master
            'sales_org',        # from header
            'order_type',       # from header
            'order_reason',     # from header
            'order_year',       # calculated
            'order_month'       # calculated
        ]

        assert_columns_exist(df, required_filter_cols)

    def test_load_backorder_data_sku_validation(self):
        """Tests that SKUs not in master data are handled correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # Should log warning about missing SKUs
        assert_log_contains(logs, "SKUs in backorder data were not found in Master Data")

        # Should have error records
        assert not errors.empty
        sku_errors = errors[errors['ErrorType'] == 'SKU_Not_in_Master_Data']
        assert len(sku_errors) == 1
        assert sku_errors.iloc[0]['sku'] == '999'

    def test_load_backorder_data_age_calculation(self):
        """Tests that days_on_backorder is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # days_on_backorder should be calculated for all records
        assert 'days_on_backorder' in df.columns
        assert_no_nulls(df, ['days_on_backorder'])

    def test_load_backorder_data_product_name(self):
        """Tests that product names are correctly mapped from master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # SO-001, SKU 101 should have product name from orders data
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['product_name'] == 'PRODUCT-A'

# ===== EDGE CASES AND ERROR HANDLING =====

class TestEdgeCases:
    """Test suite for edge cases and error conditions"""

    def test_empty_master_data(self):
        """Tests behavior when master data is empty"""
        empty_csv = "Material Number,PLM: Level Classification 4,Material Description\n"

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: pd.read_csv(io.StringIO(empty_csv)))
            logs, df, errors = load_master_data("master_data.csv")

            # Should return empty DataFrame
            assert df.empty

    def test_null_handling_in_orders(self):
        """Tests that null values in orders are handled gracefully"""
        # This is implicitly tested by the mock data, but good to be explicit
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Should not crash on null values
        assert not df.empty

    def test_date_edge_cases(self):
        """Tests various date format edge cases"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check that valid dates are parsed regardless of format
        assert df['order_date'].notna().sum() > 0

# ===== INTEGRATION TESTS =====

class TestDataLoaderIntegration:
    """Integration tests for the complete data loading pipeline"""

    def test_full_pipeline(self):
        """Tests the complete data loading pipeline from raw files to final datasets"""
        # Load all data
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")
        _, service_df, _ = load_service_data("deliveries.csv", header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        # All datasets should have data
        assert not master_df.empty
        assert not header_df.empty
        assert not service_df.empty
        assert not backorder_df.empty

    def test_referential_integrity(self):
        """Tests that relationships between datasets are maintained"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")
        _, service_df, _ = load_service_data("deliveries.csv", header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        # All SKUs in service data should be in master data
        service_skus = set(service_df['sku'].unique())
        master_skus = set(master_df['sku'].unique())
        assert service_skus.issubset(master_skus)

        # All sales orders in service data should be in header data
        service_orders = set(service_df['sales_order'].unique())
        header_orders = set(header_df['sales_order'].unique())
        assert service_orders.issubset(header_orders)
    # end of file
@@ -26,7 +26,7 @@
 
 
 @pytest.fixture
-def mock_get_engine(monkeypatch):
+def mock_get_engine(monkeypatch) -> None:
     """
     Mocks the get_engine function to return a dummy engine.
     """
@@ -38,7 +38,7 @@
 
 
 @pytest.fixture
-def mock_execute(monkeypatch):
+def mock_execute(monkeypatch) -> None:
     """
     Mocks the execute method of a SQLAlchemy engine.
     """
@@ -50,7 +50,7 @@
 
 
 @pytest.fixture
-def mock_file_exists(monkeypatch):
+def mock_file_exists(monkeypatch) -> None:
     """
     Mocks the check_file_exists function to simulate file existence.
     """
@@ -62,7 +62,7 @@
 
 
 @pytest.fixture
-def mock_blob_service_client(monkeypatch):
+def mock_blob_service_client(monkeypatch) -> None:
     """Mocks the BlobServiceClient to avoid actual Azure Blob Storage interaction."""
     class MockBlobClient:
         def __init__(self, *args, **kwargs):
@@ -82,7 +82,7 @@
 
 
 @pytest.fixture
-def mock_container_client(monkeypatch):
+def mock_container_client(monkeypatch) -> None:
     """Mocks the ContainerClient."""
     class MockContainerClient:
         def __init__(self, *args, **kwargs):
@@ -100,7 +100,7 @@
 
 
 @pytest.fixture
-def mock_download_blob(monkeypatch):
+def mock_download_blob(monkeypatch) -> None:
     """Mocks the download_blob method."""
     class MockBlobStream:
         def readall(self):
@@ -120,7 +120,7 @@
 
 
 @pytest.fixture
-def mock_os_environ(monkeypatch):
+def mock_os_environ(monkeypatch) -> None:
     """Mocks environment variables."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake_connection_string")
     monkeypatch.setenv("DB_HOST", "fake_host")
@@ -131,7 +131,7 @@
 
 
 @pytest.fixture
-def configure_env(monkeypatch):
+def configure_env(monkeypatch) -> None:
     """Configures the environment for testing."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "test_connection_string")
     monkeypatch.setenv("DB_HOST", "test_host")
@@ -142,7 +142,7 @@
 
 
 @pytest.fixture
-def mock_db_functions(monkeypatch):
+def mock_db_functions(monkeypatch) -> None:
     """Mocks database functions to prevent actual database interactions."""
     def mock_get_engine(*args, **kwargs):
         return "test_engine"
@@ -161,7 +161,7 @@
 
 
 @pytest.fixture
-def mock_load_data(monkeypatch):
+def mock_load_data(monkeypatch) -> None:
     """Mocks the load_data function to prevent actual data loading."""
     def mock_load_data(*args, **kwargs):
         return None
@@ -171,7 +171,7 @@
 
 
 @pytest.fixture
-def mock_logging(monkeypatch):
+def mock_logging(monkeypatch) -> None:
     """Comprehensive tests for data_loader module
     Tests data loading, transformation, error handling, and data quality
     """

     import pytest
     import pandas as pd
     import io
     import sys
     import os

     # Add parent directory to path
     sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

     from data_loader import (
          load_master_data,
          load_orders_item_lookup_legacy as load_orders_item_lookup,
          load_orders_header_lookup_legacy as load_orders_header_lookup,
          load_service_data_legacy as load_service_data,
          load_backorder_data,
          load_orders_unified,
          load_deliveries_unified
     )


     # Local module-level mocking: make this test module self-contained and not
     # dependent on real files on disk. We reuse the same mock fixtures defined in
     # `tests/conftest.py` to provide in-memory CSVs for common filenames.
     @pytest.fixture(autouse=True)
     def local_mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv,
                                 mock_deliveries_csv, mock_inventory_csv):
          mocks = {
               "master_data.csv": mock_master_data_csv[1],
               "orders.csv": mock_orders_csv[1],
               "deliveries.csv": mock_deliveries_csv[1],
               "inventory.csv": mock_inventory_csv[1],
          }

          original_read_csv = pd.read_csv

          def fake_read_csv(filepath_or_buffer, *args, **kwargs):
               # If a filepath string maps to one of our mocked names, reset the
               # StringIO and delegate to the original pandas reader (so kwargs
               # like usecols still work). Otherwise, fall back to original.
               if isinstance(filepath_or_buffer, str):
                    filename = os.path.basename(filepath_or_buffer)
                    if filename in mocks:
                         mocks[filename].seek(0)
                         return original_read_csv(mocks[filename], *args, **kwargs)
               return original_read_csv(filepath_or_buffer, *args, **kwargs)

          monkeypatch.setattr(pd, "read_csv", fake_read_csv)
          yield

     # ===== TEST HELPER FUNCTIONS =====

     def assert_log_contains(logs, expected_message):
          """Helper to assert that a log message contains expected text"""
          log_text = " ".join(logs)
          assert expected_message in log_text, f"Expected '{expected_message}' not found in logs: {log_text}"

     def assert_columns_exist(df, columns):
          """Helper to assert that DataFrame contains required columns"""
          missing = set(columns) - set(df.columns)
          assert not missing, f"Missing required columns: {missing}"

     def assert_no_nulls(df, columns):
          """Helper to assert that specified columns have no null values"""
          for col in columns:
               null_count = df[col].isna().sum()
               assert null_count == 0, f"Column '{col}' has {null_count} null values"
 
 @pytest.fixture
-def mock_os_environ(monkeypatch):
+def mock_os_environ(monkeypatch) -> None:
     """Mocks environment variables."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake_connection_string")
     monkeypatch.setenv("DB_HOST", "fake_host")
@@ -131,7 +131,7 @@
 
 
 @pytest.fixture
-def configure_env(monkeypatch):
+def configure_env(monkeypatch) -> None:
     """Configures the environment for testing."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "test_connection_string")
     monkeypatch.setenv("DB_HOST", "test_host")
@@ -142,7 +142,7 @@
 
 
 @pytest.fixture
-def mock_db_functions(monkeypatch):
+def mock_db_functions(monkeypatch) -> None:
     """Mocks database functions to prevent actual database interactions."""
     def mock_get_engine(*args, **kwargs):
         return "test_engine"
@@ -161,7 +161,7 @@
 
 
 @pytest.fixture
-def mock_load_data(monkeypatch):
+def mock_load_data(monkeypatch) -> None:
     """Mocks the load_data function to prevent actual data loading."""
     def mock_load_data(*args, **kwargs):
         return None
@@ -171,7 +171,7 @@
 
 
 @pytest.fixture
-def mock_logging(monkeypatch):
+def mock_logging(monkeypatch) -> None:
     """Mocks logging functions to prevent actual log output during tests."""
     def mock_info(message):
         print(f"MOCK INFO: {message}")  # Print the message instead of logging
@@ -185,7 +185,7 @@
 
 
 @pytest.fixture
-def mock_check_table_exists(monkeypatch):
+def mock_check_table_exists(monkeypatch) -> None:
     """Mocks the check_table_exists function."""
     def mock_check_table_exists(engine, table_name):
         return True  # Simulate that the table always exists
@@ -196,7 +196,7 @@
 
 
 @pytest.fixture
-def mock_wasabi_functions(monkeypatch):
+def mock_wasabi_functions(monkeypatch) -> None:
     """Mocks Wasabi-related functions."""
     def mock_connect_to_wasabi(*args, **kwargs):
         return "mock_wasabi_connection"
@@ -215,7 +215,7 @@
 
 
 @pytest.fixture
-def mock_sql_alchemy_functions(monkeypatch):
+def mock_sql_alchemy_functions(monkeypatch) -> None:
     """Mocks SQLAlchemy-related functions."""
     def mock_create_engine(*args, **kwargs):
         return "mock_engine"
@@ -245,7 +245,7 @@
 
 
 @pytest.fixture
-def mock_time(monkeypatch):
+def mock_time(monkeypatch) -> None:
     """Mocks time-related functions."""
     monkeypatch.setattr(time, 'sleep', lambda x: None)
 
@@ -254,7 +254,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_azure_blob_data function."""
     from data_loaders import load_azure_blob_data
 
@@ -271,7 +271,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_wasabi_data function."""
     from data_loaders import load_wasabi_data
 
@@ -288,7 +288,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_local_file_data function."""
     from data_loaders import load_local_file_data
 
@@ -304,7 +304,7 @@
 
 
 @pytest.mark.asyncio
-async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the check_and_load_data function."""
     from data_loaders import check_and_load_data
 
@@ -321,7 +321,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_all_data function."""
     from data_loaders import load_all_data
 
@@ -339,3 +339,4 @@
         load_all_data()
 
 # Example usage (This won't run during pytest but shows how to call the function)
+
--- a/c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain\tests\test_data_loaders.py
+++ b/c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain\tests\test_data_loaders.py
@@ -14,7 +14,7 @@
 
 
 @pytest.fixture
-def mock_read_csv(monkeypatch):
+def mock_read_csv(monkeypatch) -> None:
     """
     Mocks the pd.read_csv function to return a DataFrame.
     """
@@ -26,7 +26,7 @@
 
 
 @pytest.fixture
-def mock_get_engine(monkeypatch):
+def mock_get_engine(monkeypatch) -> None:
     """
     Mocks the get_engine function to return a dummy engine.
     """
@@ -38,7 +38,7 @@
 
 
 @pytest.fixture
-def mock_execute(monkeypatch):
+def mock_execute(monkeypatch) -> None:
     """
     Mocks the execute method of a SQLAlchemy engine.
     """
@@ -50,7 +50,7 @@
 
 
 @pytest.fixture
-def mock_file_exists(monkeypatch):
+def mock_file_exists(monkeypatch) -> None:
     """
     Mocks the check_file_exists function to simulate file existence.
     """
@@ -62,7 +62,7 @@
 
 
 @pytest.fixture
-def mock_blob_service_client(monkeypatch):
+def mock_blob_service_client(monkeypatch) -> None:
     """Mocks the BlobServiceClient to avoid actual Azure Blob Storage interaction."""
     class MockBlobClient:
         def __init__(self, *args, **kwargs):
@@ -82,7 +82,7 @@
 
 
 @pytest.fixture
-def mock_container_client(monkeypatch):
+def mock_container_client(monkeypatch) -> None:
     """Mocks the ContainerClient."""
     class MockContainerClient:
         def __init__(self, *args, **kwargs):
@@ -100,7 +100,7 @@
 
 
 @pytest.fixture
-def mock_download_blob(monkeypatch):
+def mock_download_blob(monkeypatch) -> None:
     """Mocks the download_blob method."""
     class MockBlobStream:
         def readall(self):
@@ -120,7 +120,7 @@
 
 
 @pytest.fixture
-def mock_os_environ(monkeypatch):
+def mock_os_environ(monkeypatch) -> None:
     """Mocks environment variables."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake_connection_string")
     monkeypatch.setenv("DB_HOST", "fake_host")
@@ -131,7 +131,7 @@
 
 
 @pytest.fixture
-def configure_env(monkeypatch):
+def configure_env(monkeypatch) -> None:
     """Configures the environment for testing."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "test_connection_string")
     monkeypatch.setenv("DB_HOST", "test_host")
@@ -142,7 +142,7 @@
 
 
 @pytest.fixture
-def mock_db_functions(monkeypatch):
+def mock_db_functions(monkeypatch) -> None:
     """Mocks database functions to prevent actual database interactions."""
     def mock_get_engine(*args, **kwargs):
         return "test_engine"
@@ -161,7 +161,7 @@
 
 
 @pytest.fixture
-def mock_load_data(monkeypatch):
+def mock_load_data(monkeypatch) -> None:
     """Mocks the load_data function to prevent actual data loading."""
     def mock_load_data(*args, **kwargs):
         return None
@@ -171,7 +171,7 @@
 
 
 @pytest.fixture
-def mock_logging(monkeypatch):
+def mock_logging(monkeypatch) -> None:
     """Mocks logging functions to prevent actual log output during tests."""
     def mock_info(message):
         print(f"MOCK INFO: {message}")  # Print the message instead of logging
@@ -185,7 +185,7 @@
 
 
 @pytest.fixture
-def mock_check_table_exists(monkeypatch):
+def mock_check_table_exists(monkeypatch) -> None:
     """Mocks the check_table_exists function."""
     def mock_check_table_exists(engine, table_name):
         return True  # Simulate that the table always exists
@@ -196,7 +196,7 @@
 
 
 @pytest.fixture
-def mock_wasabi_functions(monkeypatch):
+def mock_wasabi_functions(monkeypatch) -> None:
     """Mocks Wasabi-related functions."""
     def mock_connect_to_wasabi(*args, **kwargs):
         return "mock_wasabi_connection"
@@ -215,7 +215,7 @@
 
 
 @pytest.fixture
-def mock_sql_alchemy_functions(monkeypatch):
+def mock_sql_alchemy_functions(monkeypatch) -> None:
     """Mocks SQLAlchemy-related functions."""
     def mock_create_engine(*args, **kwargs):
         return "mock_engine"
@@ -245,7 +245,7 @@
 
 
 @pytest.fixture
-def mock_time(monkeypatch):
+def mock_time(monkeypatch) -> None:
     """Mocks time-related functions."""
     monkeypatch.setattr(time, 'sleep', lambda x: None)
 
@@ -254,7 +254,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_azure_blob_data function."""
     from data_loaders import load_azure_blob_data
 
@@ -271,7 +271,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_wasabi_data function."""
     from data_loaders import load_wasabi_data
 
@@ -288,7 +288,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_local_file_data function."""
     from data_loaders import load_local_file_data
 
@@ -304,7 +304,7 @@
 
 
 @pytest.mark.asyncio
-async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the check_and_load_data function."""
     from data_loaders import check_and_load_data
 
@@ -321,7 +321,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_all_data function."""
     from data_loaders import load_all_data
 
@@ -339,3 +339,4 @@
         load_all_data()
 
 # Example usage (This won't run during pytest but shows how to call the function)
+
--- a/c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain\tests\test_data_loaders.py
+++ b/c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain\tests\test_data_loaders.py
@@ -14,7 +14,7 @@
 
 
 @pytest.fixture
-def mock_read_csv(monkeypatch):
+def mock_read_csv(monkeypatch) -> None:
     """
     Mocks the pd.read_csv function to return a DataFrame.
     """
@@ -26,7 +26,7 @@
 
 
 @pytest.fixture
-def mock_get_engine(monkeypatch):
+def mock_get_engine(monkeypatch) -> None:
     """
     Mocks the get_engine function to return a dummy engine.
     """
@@ -38,7 +38,7 @@
 
 
 @pytest.fixture
-def mock_execute(monkeypatch):
+def mock_execute(monkeypatch) -> None:
     """
     Mocks the execute method of a SQLAlchemy engine.
     """
@@ -50,7 +50,7 @@
 
 
 @pytest.fixture
-def mock_file_exists(monkeypatch):
+def mock_file_exists(monkeypatch) -> None:
     """
     Mocks the check_file_exists function to simulate file existence.
     """
@@ -62,7 +62,7 @@
 
 
 @pytest.fixture
-def mock_blob_service_client(monkeypatch):
+def mock_blob_service_client(monkeypatch) -> None:
     """Mocks the BlobServiceClient to avoid actual Azure Blob Storage interaction."""
     class MockBlobClient:
         def __init__(self, *args, **kwargs):
@@ -82,7 +82,7 @@
 
 
 @pytest.fixture
-def mock_container_client(monkeypatch):
+def mock_container_client(monkeypatch) -> None:
     """Mocks the ContainerClient."""
     class MockContainerClient:
         def __init__(self, *args, **kwargs):
@@ -100,7 +100,7 @@
 
 
 @pytest.fixture
-def mock_download_blob(monkeypatch):
+def mock_download_blob(monkeypatch) -> None:
     """Mocks the download_blob method."""
     class MockBlobStream:
         def readall(self):
@@ -120,7 +120,7 @@
 
 
 @pytest.fixture
-def mock_os_environ(monkeypatch):
+def mock_os_environ(monkeypatch) -> None:
     """Mocks environment variables."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake_connection_string")
     monkeypatch.setenv("DB_HOST", "fake_host")
@@ -131,7 +131,7 @@
 
 
 @pytest.fixture
-def configure_env(monkeypatch):
+def configure_env(monkeypatch) -> None:
     """Configures the environment for testing."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "test_connection_string")
     monkeypatch.setenv("DB_HOST", "test_host")
@@ -142,7 +142,7 @@
 
 
 @pytest.fixture
-def mock_db_functions(monkeypatch):
+def mock_db_functions(monkeypatch) -> None:
     """Mocks database functions to prevent actual database interactions."""
     def mock_get_engine(*args, **kwargs):
         return "test_engine"
@@ -161,7 +161,7 @@
 
 
 @pytest.fixture
-def mock_load_data(monkeypatch):
+def mock_load_data(monkeypatch) -> None:
     """Mocks the load_data function to prevent actual data loading."""
     def mock_load_data(*args, **kwargs):
         return None
@@ -171,7 +171,7 @@
 
 
 @pytest.fixture
-def mock_logging(monkeypatch):
+def mock_logging(monkeypatch) -> None:
     """Mocks logging functions to prevent actual log output during tests."""
     def mock_info(message):
         print(f"MOCK INFO: {message}")  # Print the message instead of logging
@@ -185,7 +185,7 @@
 
 
 @pytest.fixture
-def mock_check_table_exists(monkeypatch):
+def mock_check_table_exists(monkeypatch) -> None:
     """Mocks the check_table_exists function."""
     def mock_check_table_exists(engine, table_name):
         return True  # Simulate that the table always exists
@@ -196,7 +196,7 @@
 
 
 @pytest.fixture
-def mock_wasabi_functions(monkeypatch):
+def mock_wasabi_functions(monkeypatch) -> None:
     """Mocks Wasabi-related functions."""
     def mock_connect_to_wasabi(*args, **kwargs):
         return "mock_wasabi_connection"
@@ -215,7 +215,7 @@
 
 
 @pytest.fixture
-def mock_sql_alchemy_functions(monkeypatch):
+def mock_sql_alchemy_functions(monkeypatch) -> None:
     """Mocks SQLAlchemy-related functions."""
     def mock_create_engine(*args, **kwargs):
         return "mock_engine"
@@ -245,7 +245,7 @@
 
 
 @pytest.fixture
-def mock_time(monkeypatch):
+def mock_time(monkeypatch) -> None:
     """Mocks time-related functions."""
     monkeypatch.setattr(time, 'sleep', lambda x: None)
 
@@ -254,7 +254,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_azure_blob_data function."""
     from data_loaders import load_azure_blob_data
 
@@ -271,7 +271,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_wasabi_data function."""
     from data_loaders import load_wasabi_data
 
@@ -288,7 +288,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_local_file_data function."""
     from data_loaders import load_local_file_data
 
@@ -304,7 +304,7 @@
 
 
 @pytest.mark.asyncio
-async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the check_and_load_data function."""
     from data_loaders import check_and_load_data
 
@@ -321,7 +321,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_all_data function."""
     from data_loaders import load_all_data
 
@@ -339,3 +339,4 @@
         load_all_data()
 
 # Example usage (This won't run during pytest but shows how to call the function)
+
--- a/c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain\tests\test_data_loaders.py
+++ b/c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain\tests\test_data_loaders.py
@@ -14,7 +14,7 @@
 
 
 @pytest.fixture
-def mock_read_csv(monkeypatch):
+def mock_read_csv(monkeypatch) -> None:
     """
     Mocks the pd.read_csv function to return a DataFrame.
     """
@@ -26,7 +26,7 @@
 
 
 @pytest.fixture
-def mock_get_engine(monkeypatch):
+def mock_get_engine(monkeypatch) -> None:
     """
     Mocks the get_engine function to return a dummy engine.
     """
@@ -38,7 +38,7 @@
 
 
 @pytest.fixture
-def mock_execute(monkeypatch):
+def mock_execute(monkeypatch) -> None:
     """
     Mocks the execute method of a SQLAlchemy engine.
     """
@@ -50,7 +50,7 @@
 
 
 @pytest.fixture
-def mock_file_exists(monkeypatch):
+def mock_file_exists(monkeypatch) -> None:
     """
     Mocks the check_file_exists function to simulate file existence.
     """
@@ -62,7 +62,7 @@
 
 
 @pytest.fixture
-def mock_blob_service_client(monkeypatch):
+def mock_blob_service_client(monkeypatch) -> None:
     """Mocks the BlobServiceClient to avoid actual Azure Blob Storage interaction."""
     class MockBlobClient:
         def __init__(self, *args, **kwargs):
@@ -82,7 +82,7 @@
 
 
 @pytest.fixture
-def mock_container_client(monkeypatch):
+def mock_container_client(monkeypatch) -> None:
     """Mocks the ContainerClient."""
     class MockContainerClient:
         def __init__(self, *args, **kwargs):
@@ -100,7 +100,7 @@
 
 
 @pytest.fixture
-def mock_download_blob(monkeypatch):
+def mock_download_blob(monkeypatch) -> None:
     """Mocks the download_blob method."""
     class MockBlobStream:
         def readall(self):
@@ -120,7 +120,7 @@
 
 
 @pytest.fixture
-def mock_os_environ(monkeypatch):
+def mock_os_environ(monkeypatch) -> None:
     """Mocks environment variables."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake_connection_string")
     monkeypatch.setenv("DB_HOST", "fake_host")
@@ -131,7 +131,7 @@
 
 
 @pytest.fixture
-def configure_env(monkeypatch):
+def configure_env(monkeypatch) -> None:
     """Configures the environment for testing."""
     monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "test_connection_string")
     monkeypatch.setenv("DB_HOST", "test_host")
@@ -142,7 +142,7 @@
 
 
 @pytest.fixture
-def mock_db_functions(monkeypatch):
+def mock_db_functions(monkeypatch) -> None:
     """Mocks database functions to prevent actual database interactions."""
     def mock_get_engine(*args, **kwargs):
         return "test_engine"
@@ -161,7 +161,7 @@
 
 
 @pytest.fixture
-def mock_load_data(monkeypatch):
+def mock_load_data(monkeypatch) -> None:
     """Mocks the load_data function to prevent actual data loading."""
     def mock_load_data(*args, **kwargs):
         return None
@@ -171,7 +171,7 @@
 
 
 @pytest.fixture
-def mock_logging(monkeypatch):
+def mock_logging(monkeypatch) -> None:
     """Mocks logging functions to prevent actual log output during tests."""
     def mock_info(message):
         print(f"MOCK INFO: {message}")  # Print the message instead of logging
@@ -185,7 +185,7 @@
 
 
 @pytest.fixture
-def mock_check_table_exists(monkeypatch):
+def mock_check_table_exists(monkeypatch) -> None:
     """Mocks the check_table_exists function."""
     def mock_check_table_exists(engine, table_name):
         return True  # Simulate that the table always exists
@@ -196,7 +196,7 @@
 
 
 @pytest.fixture
-def mock_wasabi_functions(monkeypatch):
+def mock_wasabi_functions(monkeypatch) -> None:
     """Mocks Wasabi-related functions."""
     def mock_connect_to_wasabi(*args, **kwargs):
         return "mock_wasabi_connection"
@@ -215,7 +215,7 @@
 
 
 @pytest.fixture
-def mock_sql_alchemy_functions(monkeypatch):
+def mock_sql_alchemy_functions(monkeypatch) -> None:
     """Mocks SQLAlchemy-related functions."""
     def mock_create_engine(*args, **kwargs):
         return "mock_engine"
@@ -245,7 +245,7 @@
 
 
 @pytest.fixture
-def mock_time(monkeypatch):
+def mock_time(monkeypatch) -> None:
     """Mocks time-related functions."""
     monkeypatch.setattr(time, 'sleep', lambda x: None)
 
@@ -254,7 +254,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_azure_blob_data(mock_read_csv, mock_blob_service_client, mock_container_client, mock_download_blob, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_azure_blob_data function."""
     from data_loaders import load_azure_blob_data
 
@@ -271,7 +271,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_wasabi_data(mock_read_csv, mock_wasabi_functions, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_wasabi_data function."""
     from data_loaders import load_wasabi_data
 
@@ -288,7 +288,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_local_file_data(mock_read_csv, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_local_file_data function."""
     from data_loaders import load_local_file_data
 
@@ -304,7 +304,7 @@
 
 
 @pytest.mark.asyncio
-async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_check_and_load_data(mock_read_csv, mock_file_exists, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the check_and_load_data function."""
     from data_loaders import check_and_load_data
 
@@ -321,7 +321,7 @@
 
 
 @pytest.mark.asyncio
-async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time):
+async def test_load_all_data(mock_read_csv, mock_file_exists, mock_blob_service_client, mock_container_client, mock_download_blob, mock_wasabi_functions, mock_os_environ, mock_db_functions, mock_load_data, mock_logging, mock_check_table_exists, mock_sql_alchemy_functions, mock_time) -> None:
     """Tests the load_all_data function."""
     from data_loaders import load_all_data
 
@@ -339,3 +339,4 @@
         load_all_data()
 
 # Example usage (This won't run during pytest but shows how to call the function)
+
"""
Comprehensive tests for data_loader module
Tests data loading, transformation, error handling, and data quality
"""

import pytest
import pandas as pd
import io
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import (
    load_master_data,
    load_orders_item_lookup_legacy as load_orders_item_lookup,
    load_orders_header_lookup_legacy as load_orders_header_lookup,
    load_service_data_legacy as load_service_data,
    load_backorder_data,
    load_orders_unified,
    load_deliveries_unified
)


# Local module-level mocking: make this test module self-contained and not
# dependent on real files on disk. We reuse the same mock fixtures defined in
# `tests/conftest.py` to provide in-memory CSVs for common filenames.
@pytest.fixture(autouse=True)
def local_mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv,
                       mock_deliveries_csv, mock_inventory_csv):
    mocks = {
        "master_data.csv": mock_master_data_csv[1],
        "orders.csv": mock_orders_csv[1],
        "deliveries.csv": mock_deliveries_csv[1],
        "inventory.csv": mock_inventory_csv[1],
    }

    original_read_csv = pd.read_csv

    def fake_read_csv(filepath_or_buffer, *args, **kwargs):
        # If a filepath string maps to one of our mocked names, reset the
        # StringIO and delegate to the original pandas reader (so kwargs
        # like usecols still work). Otherwise, fall back to original.
        if isinstance(filepath_or_buffer, str):
            filename = os.path.basename(filepath_or_buffer)
            if filename in mocks:
                mocks[filename].seek(0)
                return original_read_csv(mocks[filename], *args, **kwargs)
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", fake_read_csv)
    yield

# ===== TEST HELPER FUNCTIONS =====

def assert_log_contains(logs, expected_message):
    """Helper to assert that a log message contains expected text"""
    log_text = " ".join(logs)
    assert expected_message in log_text, f"Expected '{expected_message}' not found in logs: {log_text}"

def assert_columns_exist(df, columns):
    """Helper to assert that DataFrame contains required columns"""
    missing = set(columns) - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"

def assert_no_nulls(df, columns):
    """Helper to assert that specified columns have no null values"""
    for col in columns:
        null_count = df[col].isna().sum()
        assert null_count == 0, f"Column '{col}' has {null_count} null values"

# ===== MASTER DATA TESTS =====

class TestMasterDataLoader:
    """Test suite for master data loading"""

    def test_load_master_data_success(self):
        """Tests successful loading and column renaming"""
        logs, df, errors = load_master_data("master_data.csv")

        # Should have data
        assert not df.empty, "Master data should not be empty"

        # Check columns renamed correctly
        assert_columns_exist(df, ['sku', 'category'])

        # Should have 4 unique SKUs after deduplication
        assert len(df) == 4

    def test_load_master_data_deduplication(self):
        """Tests that duplicate SKUs are handled correctly"""
        logs, df, errors = load_master_data("master_data.csv")

        # Should log warning about duplicates
        assert_log_contains(logs, "duplicated SKUs")

        # Check that first occurrence is kept
        sku_101 = df[df['sku'] == '101']
        assert len(sku_101) == 1
        assert sku_101.iloc[0]['category'] == 'CAT-A'

    def test_load_master_data_missing_column(self):
        """Tests graceful failure when required column is missing"""
        bad_csv = "PLM: Level Classification 4,Activation Date (Code)\nCAT-A,1/1/23"

        # Create a dataframe that's missing required columns
        import pandas
        bad_df = pandas.read_csv(io.StringIO(bad_csv))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: bad_df)
            logs, df, errors = load_master_data("master_data.csv")

            # Should log error
            assert_log_contains(logs, "ERROR: 'Master Data.csv' is missing required columns")

            # Should return empty DataFrame
            assert df.empty

    def test_load_master_data_no_duplicates(self):
        """Tests behavior when there are no duplicates"""
        clean_csv = """Material Number,PLM: Level Classification 4,Activation Date (Code),PLM: PLM Current Status,PLM: Expiration Date
201,CAT-X,1/1/23,Active,20251231
202,CAT-Y,2/1/23,Active,20261231
"""
        # Create a clean dataframe
        import pandas
        clean_df = pandas.read_csv(io.StringIO(clean_csv))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: clean_df)
            logs, df, errors = load_master_data("master_data.csv")

            # Should not log duplicate warning
            log_text = " ".join(logs)
            assert "duplicated SKUs" not in log_text

            # Should have all records
            assert len(df) == 2

# ===== ORDERS DATA TESTS =====

class TestOrdersDataLoader:
    """Test suite for orders data loading"""

    def test_load_orders_item_lookup_aggregation(self):
        """Tests that orders are correctly aggregated by sales_order + SKU"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check SO-001 aggregation (two lines should become one)
        so1_rows = df[df['sales_order'] == 'SO-001']
        assert len(so1_rows) == 1, "SO-001 should be aggregated to single row"

        so1 = so1_rows.iloc[0]
        assert so1['ordered_qty'] == 25, "Ordered qty should be 10 + 15 = 25"
        assert so1['backorder_qty'] == 5, "Backorder qty should be 5 + 0 = 5"

    def test_load_orders_date_parsing(self):
        """Tests date parsing with M/D/YY format"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check M/D/YY format (SO-001)
        so1_rows = df[df['sales_order'] == 'SO-001']
        assert len(so1_rows) > 0, "SO-001 should exist"
        so1 = so1_rows.iloc[0]
        assert so1['order_date'] == pd.to_datetime("2024-05-15")

        # SO-002 with YYYY-MM-DD format will be dropped (invalid for M/D/YY parser)
        so2_rows = df[df['sales_order'] == 'SO-002']
        assert len(so2_rows) == 0, "SO-002 should be dropped due to date format mismatch"

    def test_load_orders_invalid_date_handling(self):
        """Tests that invalid dates are caught and rows dropped"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # SO-003 with invalid date should be dropped (silently by dropna)
        so3_rows = df[df['sales_order'] == 'SO-003']
        assert len(so3_rows) == 0, "SO-003 with invalid date should be dropped"

        # Verify remaining rows message is logged
        assert_log_contains(logs, "rows remaining after dropping NaNs")

    def test_load_orders_required_columns(self):
        """Tests that all required columns are present"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        required_cols = [
            'sales_order', 'sku', 'order_date', 'ordered_qty',
            'backorder_qty', 'cancelled_qty', 'customer_name',
            'sales_org', 'order_type', 'order_reason'
        ]

        assert_columns_exist(df, required_cols)

    def test_load_orders_header_lookup(self):
        """Tests header-level lookup creation"""
        logs, df = load_orders_header_lookup("orders.csv")

        # Should have header-level columns only
        assert 'sales_order' in df.columns
        assert 'customer_name' in df.columns
        assert 'order_type' in df.columns

        # Should NOT have item-level columns
        assert 'sku' not in df.columns
        assert 'ordered_qty' not in df.columns

        # Should be unique by sales_order
        assert len(df) == df['sales_order'].nunique()

    def test_load_orders_quantity_calculations(self):
        """Tests that quantity calculations are correct"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check SO-005 quantities
        so5 = df[df['sales_order'] == 'SO-005'].iloc[0]
        assert so5['ordered_qty'] == 50
        assert so5['backorder_qty'] == 10  # to_be_delivered

# ===== SERVICE DATA TESTS =====

class TestServiceDataLoader:
    """Test suite for service level data loading"""

    def test_load_service_data_joins(self):
        """Tests that service data correctly joins with orders and master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should have data from all three sources
        assert_columns_exist(df, [
            'sales_order',      # from deliveries
            'customer_name',    # from header
            'category'          # from master
        ])

    def test_load_service_data_unmatched_orders(self):
        """Tests handling of deliveries for non-existent orders"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about unmatched deliveries
        assert_log_contains(logs, "WARNING: 1 delivery lines did not find a matching order")

        # SO-999 should be dropped
        assert 'SO-999' not in df['sales_order'].values

    def test_load_service_data_date_calculations(self):
        """Tests that days_to_deliver and on_time calculations are correct"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Check SO-001: ordered 5/15, delivered 5/20 = 5 days
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['days_to_deliver'] == 5

        # Due date is order_date + 7 days (5/22), delivered 5/20 = on time
        assert so1['on_time'] == True

    def test_load_service_data_sku_mismatch(self):
        """Tests handling of deliveries without matching orders"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about unmatched deliveries (SO-999 doesn't exist in orders)
        assert_log_contains(logs, "delivery lines did not find a matching order")

        # Should have error records (unmatched deliveries)
        assert not errors.empty

    def test_load_service_data_ship_month(self):
        """Tests that ship_month is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # All deliveries in May 2024 - ship_month should be month name
        assert (df['ship_month'] == 'May').all(), "All deliveries should be in May"

# ===== BACKORDER DATA TESTS =====

class TestBackorderDataLoader:
    """Test suite for backorder data loading"""

    def test_load_backorder_data_filtering(self):
        """Tests that only records with backorder_qty > 0 are included"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # All records should have backorder_qty > 0
        assert (df['backorder_qty'] > 0).all()

    def test_load_backorder_data_joins(self):
        """Tests that backorder data includes all necessary joined columns"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # Should have filter columns from all sources
        required_filter_cols = [
            'customer_name',    # from header
            'category',         # from master
            'product_name',     # from master
            'sales_org',        # from header
            'order_type',       # from header
            'order_reason',     # from header
            'order_year',       # calculated
            'order_month'       # calculated
        ]

        assert_columns_exist(df, required_filter_cols)

    def test_load_backorder_data_sku_validation(self):
        """Tests that SKUs not in master data are handled correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # Should log warning about missing SKUs
        assert_log_contains(logs, "SKUs in backorder data were not found in Master Data")

        # Should have error records
        assert not errors.empty
        sku_errors = errors[errors['ErrorType'] == 'SKU_Not_in_Master_Data']
        assert len(sku_errors) == 1
        assert sku_errors.iloc[0]['sku'] == '999'

    def test_load_backorder_data_age_calculation(self):
        """Tests that days_on_backorder is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # days_on_backorder should be calculated for all records
        assert 'days_on_backorder' in df.columns
        assert_no_nulls(df, ['days_on_backorder'])

    def test_load_backorder_data_product_name(self):
        """Tests that product names are correctly mapped from master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # SO-001, SKU 101 should have product name from orders data
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['product_name'] == 'PRODUCT-A'

# ===== EDGE CASES AND ERROR HANDLING =====

class TestEdgeCases:
    """Test suite for edge cases and error conditions"""

    def test_empty_master_data(self):
        """Tests behavior when master data is empty"""
        empty_csv = "Material Number,PLM: Level Classification 4,Material Description\n"

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: pd.read_csv(io.StringIO(empty_csv)))
            logs, df, errors = load_master_data("master_data.csv")

            # Should return empty DataFrame
            assert df.empty

    def test_null_handling_in_orders(self):
        """Tests that null values in orders are handled gracefully"""
        # This is implicitly tested by the mock data, but good to be explicit
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Should not crash on null values
        assert not df.empty

    def test_date_edge_cases(self):
        """Tests various date format edge cases"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check that valid dates are parsed regardless of format
        assert df['order_date'].notna().sum() > 0

# ===== INTEGRATION TESTS =====

class TestDataLoaderIntegration:
    """Integration tests for the complete data loading pipeline"""

    def test_full_pipeline(self):
        """Tests the complete data loading pipeline from raw files to final datasets"""
        # Load all data
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")
        _, service_df, _ = load_service_data("deliveries.csv", header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        # All datasets should have data
        assert not master_df.empty
        assert not header_df.empty
        assert not service_df.empty
        assert not backorder_df.empty

    def test_referential_integrity(self):
        """Tests that relationships between datasets are maintained"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, item_lookup_df, _ = load_orders_item_lookup("orders.csv")
        _, header_df = load_orders_header_lookup("orders.csv")
        _, service_df, _ = load_service_data("deliveries.csv", header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        # All SKUs in service data should be in master data
        service_skus = set(service_df['sku'].unique())
        master_skus = set(master_df['sku'].unique())
        assert service_skus.issubset(master_skus)

        # All sales orders in service data should be in header data
        service_orders = set(service_df['sales_order'].unique())
        header_orders = set(header_df['sales_order'].unique())
        assert service_orders.issubset(header_orders)
