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
    load_orders_item_lookup,
    load_orders_header_lookup,
    load_service_data,
    load_backorder_data
)

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
        assert_log_contains(logs, "WARNING: Found duplicated SKUs")

        # Check that first occurrence is kept
        sku_101 = df[df['sku'] == '101']
        assert len(sku_101) == 1
        assert sku_101.iloc[0]['category'] == 'CAT-A'

    def test_load_master_data_missing_column(self):
        """Tests graceful failure when required column is missing"""
        bad_csv = "PLM: Level Classification 4,Brand\nCAT-A,BRAND-X"

        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: pd.read_csv(io.StringIO(bad_csv)))
            logs, df, errors = load_master_data("master_data.csv")

            # Should log error
            assert_log_contains(logs, "ERROR: 'Master Data.csv' is missing required columns")

            # Should return empty DataFrame
            assert df.empty

    def test_load_master_data_no_duplicates(self):
        """Tests behavior when there are no duplicates"""
        clean_csv = """Material Number,PLM: Level Classification 4,Material Description
201,CAT-X,PRODUCT-X
202,CAT-Y,PRODUCT-Y
"""
        with pytest.MonkeyPatch.context() as m:
            m.setattr(pd, "read_csv", lambda *args, **kwargs: pd.read_csv(io.StringIO(clean_csv)))
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
        """Tests two-pass date parsing for multiple formats"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Check M/D/YY format (SO-001)
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['order_date'] == pd.to_datetime("2024-05-15")

        # Check YYYY-MM-DD format (SO-002)
        so2 = df[df['sales_order'] == 'SO-002'].iloc[0]
        assert so2['order_date'] == pd.to_datetime("2024-05-16")

    def test_load_orders_invalid_date_handling(self):
        """Tests that invalid dates are caught and rows dropped"""
        logs, df, errors = load_orders_item_lookup("orders.csv")

        # Should log error about failed date parsing
        assert_log_contains(logs, "ERROR: 1 order dates failed to parse")

        # SO-003 with invalid date should be dropped
        so3_rows = df[df['sales_order'] == 'SO-003']
        assert len(so3_rows) == 0, "SO-003 with invalid date should be dropped"

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
        """Tests handling of SKUs not in master data"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # Should log warning about SKU mismatches
        assert_log_contains(logs, "WARNING: 1 rows in Service Data have SKUs not found in Master Data")

        # Should have error records
        assert not errors.empty
        sku_errors = errors[errors['ErrorType'] == 'SKU_Not_in_Master_Data']
        assert len(sku_errors) > 0

    def test_load_service_data_ship_month(self):
        """Tests that ship_month is calculated correctly"""
        _, master_df, _ = load_master_data("master_data.csv")
        _, header_df = load_orders_header_lookup("orders.csv")

        logs, df, errors = load_service_data("deliveries.csv", header_df, master_df)

        # All deliveries in May 2024
        assert df['ship_month'].str.startswith('2024-05').all()

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
        assert_log_contains(logs, "WARNING: 1 unique SKUs in backorder data were not found in Master Data")

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

        # SO-001, SKU 101 should have product name from master data
        so1 = df[df['sales_order'] == 'SO-001'].iloc[0]
        assert so1['product_name'] == 'PRODUCT-A-DESC'

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
