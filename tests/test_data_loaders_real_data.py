"""
Comprehensive tests for data_loader module using real data files
Tests data loading, transformation, error handling, and data quality with actual CSV files
"""

import pytest
import pandas as pd
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import (
    load_master_data,
    load_orders_item_lookup,
    load_orders_header_lookup,
    load_service_data,
    load_backorder_data,
    load_inventory_data
)

# ===== FILE PATH CONFIGURATION =====

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data")

MASTER_DATA_PATH = os.path.join(DATA_DIR, "Master Data.csv")
ORDERS_PATH = os.path.join(DATA_DIR, "ORDERS.csv")
DELIVERIES_PATH = os.path.join(DATA_DIR, "DELIVERIES.csv")
INVENTORY_PATH = os.path.join(DATA_DIR, "INVENTORY.csv")

# ===== TEST HELPER FUNCTIONS =====

def assert_log_contains(logs, expected_message):
    """Helper to assert that a log message contains expected text"""
    log_text = " ".join(logs)
    assert expected_message in log_text, f"Expected '{expected_message}' not found in logs"

def assert_columns_exist(df, columns):
    """Helper to assert that DataFrame contains required columns"""
    missing = set(columns) - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"

def assert_no_nulls(df, columns):
    """Helper to assert that specified columns have no null values"""
    for col in columns:
        null_count = df[col].isna().sum()
        assert null_count == 0, f"Column '{col}' has {null_count} null values"

def assert_dataframe_not_empty(df, message="DataFrame should not be empty"):
    """Helper to assert DataFrame is not empty"""
    assert not df.empty, message
    assert len(df) > 0, f"{message} - has {len(df)} rows"

# ===== FILE EXISTENCE TESTS =====

class TestDataFilesExist:
    """Verify that all required data files exist"""

    def test_master_data_file_exists(self):
        """Test that Master Data.csv exists"""
        assert os.path.exists(MASTER_DATA_PATH), f"Master Data file not found at {MASTER_DATA_PATH}"

    def test_orders_file_exists(self):
        """Test that ORDERS.csv exists"""
        assert os.path.exists(ORDERS_PATH), f"Orders file not found at {ORDERS_PATH}"

    def test_deliveries_file_exists(self):
        """Test that DELIVERIES.csv exists"""
        assert os.path.exists(DELIVERIES_PATH), f"Deliveries file not found at {DELIVERIES_PATH}"

    def test_inventory_file_exists(self):
        """Test that INVENTORY.csv exists"""
        assert os.path.exists(INVENTORY_PATH), f"Inventory file not found at {INVENTORY_PATH}"

# ===== MASTER DATA TESTS =====

class TestMasterDataLoader:
    """Test suite for master data loading with real files"""

    def test_load_master_data_success(self):
        """Tests successful loading and basic structure"""
        logs, df, errors = load_master_data(MASTER_DATA_PATH)

        # Should have data
        assert_dataframe_not_empty(df, "Master data should not be empty")

        # Check columns renamed correctly
        assert_columns_exist(df, ['sku', 'category'])

        # SKU should be string
        assert df['sku'].dtype == 'object', "SKU should be string type"

        # No empty SKUs
        assert (df['sku'].notna()).all(), "Should not have null SKUs"

    def test_master_data_unique_skus(self):
        """Tests that SKUs are unique after deduplication"""
        logs, df, errors = load_master_data(MASTER_DATA_PATH)

        # Check for duplicates
        sku_counts = df['sku'].value_counts()
        duplicates = sku_counts[sku_counts > 1]

        assert len(duplicates) == 0, f"Found duplicate SKUs: {duplicates.index.tolist()}"

    def test_master_data_categories(self):
        """Tests that categories are present"""
        logs, df, errors = load_master_data(MASTER_DATA_PATH)

        # Should have categories
        assert df['category'].notna().sum() > 0, "Should have some categories"

    def test_master_data_performance(self):
        """Tests that master data loads in reasonable time"""
        import time

        start = time.time()
        logs, df, errors = load_master_data(MASTER_DATA_PATH)
        elapsed = time.time() - start

        assert elapsed < 5.0, f"Master data load took {elapsed:.2f}s, should be < 5s"

# ===== ORDERS DATA TESTS =====

class TestOrdersDataLoader:
    """Test suite for orders data loading with real files"""

    def test_load_orders_item_lookup_success(self):
        """Tests successful loading of orders item lookup"""
        logs, df, errors = load_orders_item_lookup(ORDERS_PATH)

        # Should have data
        assert_dataframe_not_empty(df, "Orders data should not be empty")

        # Check required columns
        required_cols = [
            'sales_order', 'sku', 'order_date', 'ordered_qty',
            'backorder_qty', 'cancelled_qty'
        ]
        assert_columns_exist(df, required_cols)

    def test_orders_dates_parsed(self):
        """Tests that order dates are properly parsed"""
        logs, df, errors = load_orders_item_lookup(ORDERS_PATH)

        # order_date should be datetime
        assert pd.api.types.is_datetime64_any_dtype(df['order_date']), "order_date should be datetime type"

        # Should have valid dates
        assert df['order_date'].notna().sum() > 0, "Should have some valid dates"

    def test_orders_quantities_numeric(self):
        """Tests that quantity fields are numeric"""
        logs, df, errors = load_orders_item_lookup(ORDERS_PATH)

        # Quantities should be numeric
        assert pd.api.types.is_numeric_dtype(df['ordered_qty']), "ordered_qty should be numeric"
        assert pd.api.types.is_numeric_dtype(df['backorder_qty']), "backorder_qty should be numeric"
        assert pd.api.types.is_numeric_dtype(df['cancelled_qty']), "cancelled_qty should be numeric"

        # Should be non-negative
        assert (df['ordered_qty'] >= 0).all(), "ordered_qty should be non-negative"
        assert (df['backorder_qty'] >= 0).all(), "backorder_qty should be non-negative"
        assert (df['cancelled_qty'] >= 0).all(), "cancelled_qty should be non-negative"

    def test_orders_header_lookup_unique(self):
        """Tests that header lookup is unique by sales_order"""
        logs, header_df = load_orders_header_lookup(ORDERS_PATH)

        # Should have data
        assert_dataframe_not_empty(header_df, "Orders header data should not be empty")

        # Should be unique by sales_order
        assert header_df['sales_order'].is_unique, "Header should be unique by sales_order"

    def test_orders_has_customer_info(self):
        """Tests that orders have customer information"""
        logs, df, errors = load_orders_item_lookup(ORDERS_PATH)

        # Should have customer_name
        assert 'customer_name' in df.columns, "Should have customer_name column"
        assert df['customer_name'].notna().sum() > 0, "Should have some customer names"

# ===== SERVICE DATA TESTS =====

class TestServiceDataLoader:
    """Test suite for service level data loading with real files"""

    def test_load_service_data_success(self):
        """Tests successful loading of service data"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_service_data(DELIVERIES_PATH, header_df, master_df)

        # Should have data
        assert_dataframe_not_empty(df, "Service data should not be empty")

    def test_service_data_has_required_columns(self):
        """Tests that service data has all required columns"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_service_data(DELIVERIES_PATH, header_df, master_df)

        required_cols = [
            'sales_order', 'sku', 'customer_name',
            'units_issued', 'days_to_deliver', 'on_time', 'ship_month'
        ]
        assert_columns_exist(df, required_cols)

    def test_service_data_on_time_calculation(self):
        """Tests that on_time is a boolean field"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_service_data(DELIVERIES_PATH, header_df, master_df)

        # on_time should be boolean
        assert df['on_time'].dtype == 'bool', "on_time should be boolean type"

    def test_service_data_days_to_deliver_positive(self):
        """Tests that days_to_deliver is non-negative"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_service_data(DELIVERIES_PATH, header_df, master_df)

        # days_to_deliver should be non-negative
        assert (df['days_to_deliver'] >= 0).all(), "days_to_deliver should be non-negative"

    def test_service_data_ship_month_format(self):
        """Tests that ship_month is properly formatted"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_service_data(DELIVERIES_PATH, header_df, master_df)

        # ship_month should be in YYYY-MM format
        assert df['ship_month'].str.match(r'^\d{4}-\d{2}$').all(), "ship_month should be YYYY-MM format"

# ===== BACKORDER DATA TESTS =====

class TestBackorderDataLoader:
    """Test suite for backorder data loading with real files"""

    def test_load_backorder_data_success(self):
        """Tests successful loading of backorder data"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_lookup_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        # May be empty if no backorders, but should load successfully
        assert df is not None, "Backorder data should be returned"

    def test_backorder_data_only_positive_quantities(self):
        """Tests that backorder data only includes positive backorder quantities"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_lookup_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        if not df.empty:
            # All backorder_qty should be > 0
            assert (df['backorder_qty'] > 0).all(), "All backorder quantities should be positive"

    def test_backorder_data_has_required_columns(self):
        """Tests that backorder data has all required columns"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_lookup_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        if not df.empty:
            required_cols = [
                'sales_order', 'sku', 'customer_name',
                'backorder_qty', 'days_on_backorder', 'product_name',
                'category', 'order_type'
            ]
            assert_columns_exist(df, required_cols)

    def test_backorder_data_days_on_backorder(self):
        """Tests that days_on_backorder is calculated"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_lookup_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_backorder_data(item_lookup_df, header_df, master_df)

        if not df.empty:
            # days_on_backorder should be non-negative
            assert (df['days_on_backorder'] >= 0).all(), "days_on_backorder should be non-negative"

# ===== INVENTORY DATA TESTS =====

class TestInventoryDataLoader:
    """Test suite for inventory data loading with real files"""

    def test_load_inventory_data_success(self):
        """Tests successful loading of inventory data"""
        logs, df, errors = load_inventory_data(INVENTORY_PATH)

        # Should have data
        assert_dataframe_not_empty(df, "Inventory data should not be empty")

    def test_inventory_data_has_required_columns(self):
        """Tests that inventory data has required columns"""
        logs, df, errors = load_inventory_data(INVENTORY_PATH)

        required_cols = ['sku', 'on_hand_qty']
        assert_columns_exist(df, required_cols)

    def test_inventory_quantities_non_negative(self):
        """Tests that inventory quantities are non-negative"""
        logs, df, errors = load_inventory_data(INVENTORY_PATH)

        # on_hand_qty should be non-negative
        assert (df['on_hand_qty'] >= 0).all(), "on_hand_qty should be non-negative"

    def test_inventory_skus_present(self):
        """Tests that inventory has SKU information"""
        logs, df, errors = load_inventory_data(INVENTORY_PATH)

        # Should have SKUs
        assert df['sku'].notna().sum() > 0, "Should have some SKUs"

# ===== INTEGRATION TESTS =====

class TestDataLoaderIntegration:
    """Integration tests for the complete data loading pipeline"""

    def test_full_pipeline_loads_all_data(self):
        """Tests that the complete data loading pipeline works"""
        # Load all data sources
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_lookup_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)
        _, service_df, _ = load_service_data(DELIVERIES_PATH, header_df, master_df)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)
        _, inventory_df, _ = load_inventory_data(INVENTORY_PATH)

        # All datasets should load successfully
        assert_dataframe_not_empty(master_df, "Master data should load")
        assert_dataframe_not_empty(item_lookup_df, "Orders item lookup should load")
        assert_dataframe_not_empty(header_df, "Orders header should load")
        assert_dataframe_not_empty(service_df, "Service data should load")
        # backorder_df may be empty
        assert_dataframe_not_empty(inventory_df, "Inventory data should load")

    def test_referential_integrity_service_to_master(self):
        """Tests that all SKUs in service data exist in master data"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)
        _, service_df, _ = load_service_data(DELIVERIES_PATH, header_df, master_df)

        if not service_df.empty:
            # All SKUs in service should be in master
            service_skus = set(service_df['sku'].unique())
            master_skus = set(master_df['sku'].unique())
            missing_skus = service_skus - master_skus

            assert len(missing_skus) == 0, f"Found SKUs in service data not in master: {missing_skus}"

    def test_referential_integrity_backorder_to_master(self):
        """Tests that all SKUs in backorder data exist in master data"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_lookup_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)
        _, backorder_df, _ = load_backorder_data(item_lookup_df, header_df, master_df)

        if not backorder_df.empty:
            # All SKUs in backorder should be in master
            backorder_skus = set(backorder_df['sku'].unique())
            master_skus = set(master_df['sku'].unique())
            missing_skus = backorder_skus - master_skus

            assert len(missing_skus) == 0, f"Found SKUs in backorder data not in master: {missing_skus}"

    def test_data_quality_no_empty_customer_names(self):
        """Tests that critical fields like customer_name are not empty"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)
        _, service_df, _ = load_service_data(DELIVERIES_PATH, header_df, master_df)

        if not service_df.empty:
            # customer_name should not be null
            null_count = service_df['customer_name'].isna().sum()
            total_count = len(service_df)
            null_pct = (null_count / total_count * 100) if total_count > 0 else 0

            assert null_pct < 5.0, f"{null_pct:.1f}% of service records have null customer_name"

# ===== PERFORMANCE TESTS =====

class TestDataLoaderPerformance:
    """Performance tests to ensure data loads in reasonable time"""

    def test_all_data_loads_within_time_limit(self):
        """Tests that all data loads within acceptable time"""
        import time

        start = time.time()

        # Load all data
        load_master_data(MASTER_DATA_PATH)
        load_orders_item_lookup(ORDERS_PATH)
        load_orders_header_lookup(ORDERS_PATH)
        load_inventory_data(INVENTORY_PATH)

        elapsed = time.time() - start

        # Should load all data in under 30 seconds
        assert elapsed < 30.0, f"All data loading took {elapsed:.2f}s, should be < 30s"
