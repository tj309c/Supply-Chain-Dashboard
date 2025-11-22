"""
Quick verification test for inventory value calculation fix
Tests that the new calculation in overview_page.py works correctly
"""

import pandas as pd
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pages.overview_page import calculate_overview_metrics
from business_rules import CURRENCY_RULES

def test_inventory_value_calculation():
    """Test that inventory value is calculated correctly from on_hand_qty and last_purchase_price"""

    # Create sample inventory data with USD and EUR currencies
    inventory_data = pd.DataFrame({
        'sku': ['SKU001', 'SKU002', 'SKU003', 'SKU004'],
        'on_hand_qty': [100, 50, 200, 75],
        'last_purchase_price': [10.0, 25.0, 5.0, 100.0],
        'currency': ['USD', 'USD', 'EUR', 'EUR']
    })

    # Create empty dataframes for service and backorder
    service_data = pd.DataFrame()
    backorder_data = pd.DataFrame()

    # Calculate metrics
    metrics = calculate_overview_metrics(service_data, backorder_data, inventory_data)

    # Get the inventory value
    inventory_value_str = metrics['inventory_value']['value']

    # Extract numeric value (remove $ and commas)
    inventory_value = float(inventory_value_str.replace('$', '').replace(',', ''))

    # Calculate expected value manually
    # SKU001: 100 * 10.0 = 1000 USD
    # SKU002: 50 * 25.0 = 1250 USD
    # SKU003: 200 * 5.0 = 1000 EUR = 1000 * 1.09 = 1090 USD
    # SKU004: 75 * 100.0 = 7500 EUR = 7500 * 1.09 = 8175 USD
    # Total = 1000 + 1250 + 1090 + 8175 = 11515 USD

    eur_to_usd = CURRENCY_RULES['conversion_rates']['EUR_to_USD']
    expected_value = (100 * 10.0) + (50 * 25.0) + (200 * 5.0 * eur_to_usd) + (75 * 100.0 * eur_to_usd)

    print(f"\nInventory Value Calculation Test:")
    print(f"Expected: ${expected_value:,.2f}")
    print(f"Actual:   ${inventory_value:,.2f}")
    print(f"EUR to USD rate: {eur_to_usd}")

    # Check if values match (allow for rounding differences since metric display rounds to integers)
    assert abs(inventory_value - expected_value) < 1.0, f"Value mismatch! Expected ${expected_value:,.2f}, got ${inventory_value:,.2f}"

    print("[PASS] Test PASSED - Inventory value calculated correctly!")

    return True

def test_inventory_value_with_missing_columns():
    """Test that function handles missing columns gracefully"""

    # Create inventory data without price columns
    inventory_data = pd.DataFrame({
        'sku': ['SKU001', 'SKU002'],
        'on_hand_qty': [100, 50]
        # Missing: last_purchase_price and currency
    })

    service_data = pd.DataFrame()
    backorder_data = pd.DataFrame()

    # Calculate metrics
    metrics = calculate_overview_metrics(service_data, backorder_data, inventory_data)

    # Should return $0
    inventory_value_str = metrics['inventory_value']['value']
    inventory_value = float(inventory_value_str.replace('$', '').replace(',', ''))

    print(f"\nMissing Columns Test:")
    print(f"Expected: $0.00")
    print(f"Actual:   ${inventory_value:,.2f}")

    assert inventory_value == 0, f"Expected $0, got ${inventory_value:,.2f}"

    print("[PASS] Test PASSED - Handles missing columns gracefully!")

    return True

def test_data_relationships():
    """Test that all data relationships are preserved"""

    # Create complete test data
    inventory_data = pd.DataFrame({
        'sku': ['SKU001', 'SKU002'],
        'on_hand_qty': [100, 50],
        'last_purchase_price': [10.0, 25.0],
        'currency': ['USD', 'EUR'],
        'dio': [45, 60]
    })

    service_data = pd.DataFrame({
        'sales_order': ['SO001', 'SO002'],
        'on_time': [True, False],
        'ship_month': ['2024-01', '2024-01']
    })

    backorder_data = pd.DataFrame({
        'sku': ['SKU003'],
        'backorder_qty': [25],
        'days_on_backorder': [15]
    })

    # Calculate metrics
    metrics = calculate_overview_metrics(service_data, backorder_data, inventory_data)

    print(f"\nData Relationships Test:")
    print(f"Service Level: {metrics['service_level']['value']}")
    print(f"Total Orders: {metrics['total_orders']['value']}")
    print(f"Backorders: {metrics['backorders']['value']}")
    print(f"Inventory Value: {metrics['inventory_value']['value']}")
    print(f"Inventory Units: {metrics['inventory_units']['value']}")
    print(f"Avg DIO: {metrics['avg_dio']['value']}")

    # Verify all metrics are populated
    assert metrics['service_level']['value'] != 'N/A', "Service level should be calculated"
    assert metrics['total_orders']['value'] != 'N/A', "Total orders should be calculated"
    assert metrics['backorders']['value'] != '0', "Backorders should be calculated"
    assert metrics['inventory_value']['value'] != '$0', "Inventory value should be calculated"
    assert metrics['inventory_units']['value'] != 'N/A', "Inventory units should be calculated"
    assert metrics['avg_dio']['value'] != 'N/A', "Avg DIO should be calculated"

    print("[PASS] Test PASSED - All data relationships preserved!")

    return True

if __name__ == "__main__":
    print("=" * 80)
    print("INVENTORY VALUE FIX - VERIFICATION TESTS")
    print("=" * 80)

    try:
        test_inventory_value_calculation()
        test_inventory_value_with_missing_columns()
        test_data_relationships()

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED!")
        print("The inventory value fix is working correctly and data relationships are intact.")
        print("=" * 80)

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
