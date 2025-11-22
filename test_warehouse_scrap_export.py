"""
Test script to diagnose warehouse scrap list export issues
"""
import pandas as pd
import sys
import os
from datetime import datetime, timedelta

# Fix encoding for Windows CMD
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dashboard_simple import load_all_data
from pages.inventory_page import prepare_warehouse_scrap_list

def test_warehouse_scrap_export():
    """Test the warehouse scrap list export with real data"""

    print("=" * 80)
    print("WAREHOUSE SCRAP LIST EXPORT DIAGNOSTIC TEST")
    print("=" * 80)

    # Step 1: Load data
    print("\n[STEP 1] Loading data...")
    try:
        data = load_all_data()
        print(f"✓ Data loaded successfully")
        print(f"  - Data keys: {list(data.keys())}")
    except Exception as e:
        print(f"✗ ERROR loading data: {e}")
        return False

    # Step 2: Check inventory_analysis data
    print("\n[STEP 2] Checking inventory_analysis data...")
    if 'inventory_analysis' not in data:
        print(f"✗ ERROR: 'inventory_analysis' not found in data")
        return False

    inventory_data = data['inventory_analysis']
    print(f"✓ inventory_analysis found")
    print(f"  - Shape: {inventory_data.shape}")
    print(f"  - Columns: {list(inventory_data.columns)[:10]}... ({len(inventory_data.columns)} total)")

    # Check for required columns
    required_cols = ['sku', 'on_hand_qty', 'daily_demand', 'dio', 'last_purchase_price']
    missing_cols = [col for col in required_cols if col not in inventory_data.columns]
    if missing_cols:
        print(f"✗ ERROR: Missing required columns: {missing_cols}")
        return False
    print(f"✓ All required columns present")

    # Check for items with inventory
    items_with_inventory = inventory_data[inventory_data['on_hand_qty'] > 0]
    print(f"  - Total SKUs: {len(inventory_data)}")
    print(f"  - SKUs with inventory (on_hand_qty > 0): {len(items_with_inventory)}")

    if len(items_with_inventory) == 0:
        print(f"✗ ERROR: No SKUs have inventory! Cannot generate scrap list.")
        return False

    # Step 3: Check activation_date column (critical for SKU age calculation)
    print("\n[STEP 3] Checking activation_date column...")
    if 'activation_date' not in inventory_data.columns:
        print(f"⚠ WARNING: 'activation_date' column not found - SKU age will be 0")
        print(f"  Available date columns: {[col for col in inventory_data.columns if 'date' in col.lower()]}")
    else:
        print(f"✓ 'activation_date' column found")
        # Check if it's already datetime
        if pd.api.types.is_datetime64_any_dtype(inventory_data['activation_date']):
            print(f"  - Data type: datetime")
            valid_dates = inventory_data['activation_date'].notna().sum()
            print(f"  - Valid dates: {valid_dates}/{len(inventory_data)}")
            if valid_dates > 0:
                min_date = inventory_data['activation_date'].min()
                max_date = inventory_data['activation_date'].max()
                print(f"  - Date range: {min_date} to {max_date}")

                # Calculate SKU ages
                today = pd.to_datetime(datetime.now().date())
                ages = (today - inventory_data.loc[inventory_data['activation_date'].notna(), 'activation_date']).dt.days
                skus_over_1yr = (ages > 365).sum()
                skus_over_2yr = (ages > 730).sum()
                skus_over_3yr = (ages > 1095).sum()
                print(f"  - SKUs > 1 year old: {skus_over_1yr}")
                print(f"  - SKUs > 2 years old: {skus_over_2yr}")
                print(f"  - SKUs > 3 years old: {skus_over_3yr}")

                if skus_over_1yr == 0:
                    print(f"⚠ WARNING: No SKUs are > 1 year old - all will be excluded from scrap recommendations!")
        else:
            print(f"  - Data type: {inventory_data['activation_date'].dtype}")
            print(f"  ⚠ WARNING: activation_date is not datetime type - conversion may fail")

    # Step 4: Check quarterly demand columns
    print("\n[STEP 4] Checking quarterly demand columns...")
    quarterly_cols = ['q1_demand', 'q2_demand', 'q3_demand', 'q4_demand']
    available_q_cols = [col for col in quarterly_cols if col in inventory_data.columns]
    missing_q_cols = [col for col in quarterly_cols if col not in inventory_data.columns]

    if missing_q_cols:
        print(f"⚠ WARNING: Missing quarterly columns: {missing_q_cols}")
    if available_q_cols:
        print(f"✓ Found quarterly columns: {available_q_cols}")
    else:
        print(f"⚠ WARNING: No quarterly demand columns found - demand frequency will be 0")

    # Step 5: Test prepare_warehouse_scrap_list function
    print("\n[STEP 5] Testing prepare_warehouse_scrap_list() function...")
    try:
        scrap_list = prepare_warehouse_scrap_list(
            inventory_data=inventory_data,
            scrap_days_threshold=730,
            currency='USD'
        )
        print(f"✓ Function executed successfully")
        print(f"  - Result shape: {scrap_list.shape}")
        print(f"  - Result columns: {list(scrap_list.columns)}")

        if scrap_list.empty:
            print(f"\n✗ PROBLEM IDENTIFIED: Scrap list is EMPTY!")
            print(f"\nDIAGNOSTIC ANALYSIS:")

            # Debug: Check filtering conditions
            print(f"\n  Checking filtering conditions in prepare_warehouse_scrap_list():")
            print(f"  1. Items with inventory: {len(items_with_inventory)}")

            # Check activation_date conversion
            if 'activation_date' in inventory_data.columns:
                df_test = items_with_inventory.copy()
                today = pd.to_datetime(datetime.now().date())
                try:
                    df_test['sku_age_days'] = (today - df_test['activation_date']).dt.days
                    print(f"  2. SKU age calculation successful")
                    print(f"     - Min age: {df_test['sku_age_days'].min()} days")
                    print(f"     - Max age: {df_test['sku_age_days'].max()} days")
                    print(f"     - Median age: {df_test['sku_age_days'].median()} days")
                except Exception as e:
                    print(f"  2. ✗ SKU age calculation FAILED: {e}")

            return False
        else:
            print(f"✓ Scrap list generated with {len(scrap_list)} rows")

            # Check for 3-level recommendation columns
            scrap_cols = [
                'Conservative Scrap Qty', 'Conservative Scrap Value (USD)',
                'Medium Scrap Qty', 'Medium Scrap Value (USD)',
                'Aggressive Scrap Qty', 'Aggressive Scrap Value (USD)'
            ]
            missing_scrap_cols = [col for col in scrap_cols if col not in scrap_list.columns]
            if missing_scrap_cols:
                print(f"  ✗ Missing scrap recommendation columns: {missing_scrap_cols}")
            else:
                print(f"  ✓ All 6 scrap recommendation columns present")

                # Check if recommendations have values
                for col in scrap_cols:
                    non_zero = (scrap_list[col] > 0).sum()
                    print(f"    - {col}: {non_zero} non-zero values")

    except Exception as e:
        print(f"✗ ERROR in prepare_warehouse_scrap_list(): {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 6: Sample the results
    print("\n[STEP 6] Sample results:")
    if not scrap_list.empty:
        print(f"\nFirst 3 rows:")
        print(scrap_list.head(3).to_string())

        print(f"\nColumn summary:")
        for col in scrap_list.columns:
            if scrap_list[col].dtype in ['int64', 'float64']:
                print(f"  {col}: min={scrap_list[col].min()}, max={scrap_list[col].max()}, mean={scrap_list[col].mean():.2f}")

    print("\n" + "=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)
    return True

if __name__ == "__main__":
    success = test_warehouse_scrap_export()
    sys.exit(0 if success else 1)
