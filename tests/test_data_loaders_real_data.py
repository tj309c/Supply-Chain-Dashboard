"""
Robust Data Integrity & Integration Tests
Checks if real CSV files exist, load correctly, and meet schema requirements.
Safe to run: Will skip tests if data files are missing rather than crashing.
"""

import pytest
import pandas as pd
import sys
import os
import time

# --- 1. SETUP PATHS & IMPORTS ---

# robustly find the project root (assuming this test file is in /tests/)
current_file_path = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file_path))
sys.path.insert(0, project_root)

# Attempt imports - fails gracefully if data_loader.py is missing
try:
    from data_loader import (
        load_master_data,
        load_orders_item_lookup_legacy as load_orders_item_lookup,
        load_orders_header_lookup_legacy as load_orders_header_lookup,
        load_service_data_legacy as load_service_data,
        load_backorder_data,
        load_inventory_data
    )
except ImportError:
    pytest.fail("Could not import 'data_loader'. Check your python path.")

# --- 2. CONFIGURATION & SKIP LOGIC ---

# Data files are in project root, not a Data subdirectory
DATA_DIR = project_root
MASTER_DATA_PATH = os.path.join(DATA_DIR, "Master Data.csv")
ORDERS_PATH = os.path.join(DATA_DIR, "ORDERS.csv")
DELIVERIES_PATH = os.path.join(DATA_DIR, "DELIVERIES.csv")
INVENTORY_PATH = os.path.join(DATA_DIR, "INVENTORY.csv")

# Create markers to skip tests if files are missing (prevents crashes)
requires_master = pytest.mark.skipif(not os.path.exists(MASTER_DATA_PATH), reason="Master Data.csv not found")
requires_orders = pytest.mark.skipif(not os.path.exists(ORDERS_PATH), reason="ORDERS.csv not found")
requires_deliveries = pytest.mark.skipif(not os.path.exists(DELIVERIES_PATH), reason="DELIVERIES.csv not found")
requires_inventory = pytest.mark.skipif(not os.path.exists(INVENTORY_PATH), reason="INVENTORY.csv not found")

# --- 3. HELPER FUNCTIONS ---

def assert_columns_exist(df, columns):
    """Helper to assert that DataFrame contains required columns"""
    missing = set(columns) - set(df.columns)
    assert not missing, f"Missing required columns: {missing}"

def assert_dataframe_not_empty(df, message="DataFrame should not be empty"):
    """Helper to assert DataFrame is not empty"""
    assert not df.empty, message
    assert len(df) > 0, f"{message} - has {len(df)} rows"

# --- 4. TEST SUITES ---

class TestMasterData:
    @requires_master
    def test_load_master_data_schema(self):
        """Validates Master Data loads and has correct columns"""
        logs, df, errors = load_master_data(MASTER_DATA_PATH)
        assert_dataframe_not_empty(df)
        assert_columns_exist(df, ['sku', 'category'])
        assert df['sku'].dtype == 'object', "SKU should be string type"

    @requires_master
    def test_master_data_quality_duplicates(self):
        """Checks for duplicate SKUs in the source file"""
        logs, df, errors = load_master_data(MASTER_DATA_PATH)
        # Check uniqueness after loader deduplication logic
        assert df['sku'].is_unique, "Loader failed to deduplicate SKUs"

class TestOrdersData:
    @requires_orders
    def test_load_orders_schema(self):
        """Validates Orders data structure"""
        logs, df, errors = load_orders_item_lookup(ORDERS_PATH)
        assert_dataframe_not_empty(df)
        required_cols = ['sales_order', 'sku', 'order_date', 'ordered_qty']
        assert_columns_exist(df, required_cols)
        assert pd.api.types.is_datetime64_any_dtype(df['order_date']), "order_date must be datetime"

    @requires_orders
    def test_load_orders_header_schema(self):
        """Validates Header lookup creation"""
        logs, df = load_orders_header_lookup(ORDERS_PATH)
        assert_dataframe_not_empty(df)
        assert df['sales_order'].is_unique, "Headers must be unique by sales_order"

class TestServiceData:
    @requires_orders
    @requires_master
    @requires_deliveries
    def test_load_service_data_integration(self):
        """Tests joining Deliveries + Orders + Master"""
        # Load dependencies
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)
        
        # Load Service
        logs, df, errors = load_service_data(DELIVERIES_PATH, header_df, master_df)
        
        assert_dataframe_not_empty(df)
        required = ['sales_order', 'sku', 'units_issued', 'on_time']
        assert_columns_exist(df, required)
        
        # Logic check: on_time should be boolean
        assert df['on_time'].dtype == 'bool'

class TestBackorderData:
    @requires_orders
    @requires_master
    def test_load_backorder_logic(self):
        """Tests Backorder calculation pipeline"""
        _, master_df, _ = load_master_data(MASTER_DATA_PATH)
        _, item_df, _ = load_orders_item_lookup(ORDERS_PATH)
        _, header_df = load_orders_header_lookup(ORDERS_PATH)

        logs, df, errors = load_backorder_data(item_df, header_df, master_df)
        
        # Note: Backorders might be legitimately empty if company is running perfectly
        if not df.empty:
            assert (df['backorder_qty'] > 0).all(), "Backorder report contained zero/negative quantities"
            assert_columns_exist(df, ['days_on_backorder', 'product_name'])

class TestInventoryData:
    @requires_inventory
    def test_load_inventory_schema(self):
        """Validates Inventory file"""
        logs, df, errors = load_inventory_data(INVENTORY_PATH)
        assert_dataframe_not_empty(df)
        assert_columns_exist(df, ['sku', 'on_hand_qty'])
        assert (df['on_hand_qty'] >= 0).all(), "Found negative inventory levels"

# --- 5. ENTRY POINT ---
if __name__ == "__main__":
    # Allows running this script directly with python
    sys.exit(pytest.main(["-v", __file__]))