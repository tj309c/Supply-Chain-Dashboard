import pandas as pd
import os
import numpy as np

# Import the data loading functions from your project
from data_loader import (
    load_inventory_data,
    load_master_data
)

# --- Configuration ---
INVENTORY_FILE_PATH = "INVENTORY.csv"
DELIVERIES_FILE_PATH = "DELIVERIES.csv"
MASTER_DATA_FILE_PATH = "Master Data.csv"

def print_header(title):
    """Prints a formatted header to the console."""
    bar = "="*80
    print(f"\n{bar}\n🔬 {title.upper()}\n{bar}")

def run_debugger():
    """
    Main function to trace the DIO calculation from raw files to the final
    aggregated table, diagnosing issues at each step.
    """
    print_header("Days of Inventory (DIO) Calculation Debugger")

    # --- Step 1: Load Prerequisite Data ---
    print_header("Step 1: Loading Prerequisite DataFrames")
    
    # Load Inventory
    inv_logs, inventory_df, _ = load_inventory_data(INVENTORY_FILE_PATH)
    for log in inv_logs: print(f"  - {log}")
    if inventory_df.empty:
        print("\n❌ STOPPING: `load_inventory_data` returned an empty DataFrame. Cannot proceed.")
        return
    print(f"✅ Initial inventory loaded successfully with {len(inventory_df):,} SKUs.")
    print(f"   - Total On-Hand Units: {inventory_df['on_hand_qty'].sum():,.0f}")

    # Load Master Data
    master_logs, master_data, _ = load_master_data(MASTER_DATA_FILE_PATH)
    for log in master_logs: print(f"  - {log}")
    if master_data.empty:
        print("\n🟡 WARNING: Master Data is empty. Category information will be 'Unknown'.")

    # --- Step 2: Recreate Demand Calculation ---
    print_header("Step 2: Recreating Daily Demand Calculation")
    try:
        deliveries_df = pd.read_csv(
            DELIVERIES_FILE_PATH, 
            usecols=["Item - SAP Model Code", "Delivery Creation Date: Date", "Deliveries - TOTAL Goods Issue Qty"]
        )
        deliveries_df = deliveries_df.rename(columns={
            "Item - SAP Model Code": "sku",
            "Delivery Creation Date: Date": "ship_date",
            "Deliveries - TOTAL Goods Issue Qty": "units_issued"
        })
        print(f"✅ Successfully loaded {len(deliveries_df):,} rows from DELIVERIES.csv.")

        deliveries_df['units_issued'] = pd.to_numeric(deliveries_df['units_issued'], errors='coerce').fillna(0)
        deliveries_df['ship_date'] = pd.to_datetime(deliveries_df['ship_date'], format='%m/%d/%y', errors='coerce')
        deliveries_df.dropna(subset=['ship_date'], inplace=True)

        twelve_months_ago = pd.to_datetime('today') - pd.DateOffset(months=12)
        recent_deliveries = deliveries_df[deliveries_df['ship_date'] >= twelve_months_ago]
        print(f"  - Found {len(recent_deliveries):,} delivery rows within the last 12 months.")

        if recent_deliveries.empty:
            print("  - 🟡 WARNING: No delivery data in last 12 months. Daily demand will be 0 for all items.")
            daily_demand = pd.DataFrame(columns=['sku', 'daily_demand'])
        else:
            daily_demand = recent_deliveries.groupby('sku')['units_issued'].sum() / 365
            daily_demand = daily_demand.reset_index().rename(columns={'units_issued': 'daily_demand'})
            print(f"  - ✅ Calculated daily demand for {len(daily_demand)} unique SKUs.")

    except Exception as e:
        print(f"❌ STOPPING: Failed to process 'DELIVERIES.csv': {e}")
        return

    print("\n--- Sample of Calculated Daily Demand (Top 5 by demand) ---")
    print(daily_demand.sort_values(by='daily_demand', ascending=False).head().to_string(index=False))

    # --- Step 3: Recreate Per-SKU DIO Calculation ---
    print_header("Step 3: Recreating Per-SKU DIO Calculation")
    
    # This block mirrors the logic in `load_inventory_analysis_data`
    df = pd.merge(inventory_df, daily_demand, on='sku', how='left')
    df['daily_demand'] = df['daily_demand'].fillna(0)
    df['dio'] = np.where(df['daily_demand'] > 0, df['on_hand_qty'] / df['daily_demand'], 0)
    df = pd.merge(df, master_data, on='sku', how='left')
    df['category'] = df['category'].fillna('Unknown')
    
    print("✅ Successfully merged data and calculated per-SKU DIO.")
    if (df['dio'] == 0).all():
        print("❌ CRITICAL ISSUE: All `dio` values are zero at the SKU level.")
        print("   This means either `on_hand_qty` is always zero or `daily_demand` is always zero for all SKUs.")
        print("   Review Steps 1 and 2 to see which of these is the case.")
    else:
        print("✅ SUCCESS: Found non-zero `dio` values at the SKU level.")

    print("\n--- Sample of Per-SKU Data with DIO (Top 5 by DIO) ---")
    print(df.sort_values(by='dio', ascending=False).head().to_string(index=False))

    # --- Step 4: Recreate Dashboard Aggregation Logic ---
    print_header("Step 4: Recreating Dashboard Aggregation (`get_inventory_category_data`)")

    if df.empty:
        print("❌ STOPPING: The intermediate DataFrame is empty. Cannot perform aggregation.")
        return

    # This is the exact logic from the corrected dashboard function
    print("  - Calculating `weighted_dio_sum` (dio * on_hand_qty) for each SKU...")
    df['weighted_dio_sum'] = df['dio'] * df['on_hand_qty']
    
    print("  - Grouping by category and summing `on_hand_qty` and `weighted_dio_sum`...")
    category_agg = df.groupby('category').agg(
        total_on_hand=('on_hand_qty', 'sum'),
        weighted_dio_sum=('weighted_dio_sum', 'sum')
    )
    
    print("  - Calculating final `avg_dio` (weighted_dio_sum / total_on_hand)...")
    category_agg['avg_dio'] = category_agg['weighted_dio_sum'] / category_agg['total_on_hand']
    category_agg['avg_dio'] = category_agg['avg_dio'].fillna(0)

    print("\n--- Final Aggregated Data (as seen in dashboard chart) ---")
    print(category_agg.sort_values(by='total_on_hand', ascending=False).to_string())

    # --- Final Verdict ---
    print_header("Final Verdict")

    if (category_agg['avg_dio'] == 0).all():
        print("❌ DIAGNOSIS: The final `avg_dio` is zero for all categories.")
        
        if (df['dio'] == 0).all():
            print("   - ROOT CAUSE: The `dio` value for every individual SKU was calculated as zero.")
            print("     This is because `daily_demand` was zero for all SKUs with stock.")
        elif (df['weighted_dio_sum'] == 0).all():
            print("   - ROOT CAUSE: The `weighted_dio_sum` (dio * on_hand_qty) is zero for every SKU.")
            print("     This is extremely unusual. It implies that for every single row, either `dio` or `on_hand_qty` is zero.")
            print("     Please inspect the 'Sample of Per-SKU Data' in Step 3 to verify this.")
        else:
            print("   - ROOT CAUSE: An issue occurred during the final aggregation.")
            print("     This could be a data type issue where `total_on_hand` or `weighted_dio_sum` are not numeric, or a logic error in the division.")
            print("     Please review the final aggregated table above.")
    else:
        print("✅ SUCCESS: The DIO calculation pipeline appears to be working correctly in this script.")
        print("   Non-zero `avg_dio` values were calculated.")
        print("\n   If the dashboard is still showing zeros, the problem is likely one of the following:")
        print("     1. A Streamlit caching issue. Click 'Clear Cache & Reload Data' in the dashboard sidebar.")
        print("     2. A filter issue in the dashboard that is not being replicated here.")
        print("     3. An older, incorrect version of the `get_inventory_category_data` function is still in your `dashboard.py` file.")

    print("\n--- Debugger Finished ---")


if __name__ == "__main__":
    # Check that all files exist before proceeding
    required_files = [INVENTORY_FILE_PATH, DELIVERIES_FILE_PATH, MASTER_DATA_FILE_PATH]
    files_ok = True
    for f in required_files:
        if not os.path.exists(f):
            print(f"❌ ERROR: Required file '{f}' not found in the current directory: {os.getcwd()}")
            files_ok = False
    
    if files_ok:
        run_debugger()