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
    Main function to trace the inventory data from raw files to the final
    analysis DataFrame, diagnosing issues at each step.
    """
    print_header("Inventory Data Pipeline Debugger")

    # --- Step 1: Load and Validate Raw Inventory Data ---
    print_header("Step 1: Loading `INVENTORY.csv`")
    inv_logs, inventory_df, _ = load_inventory_data(INVENTORY_FILE_PATH)
    for log in inv_logs: print(log)

    if inventory_df.empty:
        print("\n❌ STOPPING: The `load_inventory_data` function failed or returned an empty DataFrame.")
        print("   This is the root cause. Check the logs above for errors related to file reading or column names.")
        return

    total_on_hand_units = inventory_df['on_hand_qty'].sum()
    print(f"\n✅ Initial load successful. Total on-hand units calculated: {total_on_hand_units:,.0f}")

    if total_on_hand_units == 0:
        print("🟡 WARNING: The total on-hand stock is zero. This will result in an empty report.")
        print("   Check the 'POP Actual Stock Qty' column in INVENTORY.csv for non-zero values and ensure they are formatted correctly (e.g., no unexpected text).")

    print("\n--- Sample of Processed Inventory Data (Top 5 by stock) ---")
    print(inventory_df.sort_values(by='on_hand_qty', ascending=False).head().to_string(index=False))

    # --- Step 2: Load Deliveries for Demand Calculation ---
    print_header("Step 2: Loading `DELIVERIES.csv` for Demand Calculation")
    
    try:
        delivery_cols = {
            "Item - SAP Model Code": "sku",
            "Delivery Creation Date: Date": "ship_date",
            "Deliveries - TOTAL Goods Issue Qty": "units_issued"
        }
        deliveries_df = pd.read_csv(DELIVERIES_FILE_PATH, usecols=list(delivery_cols.keys()), low_memory=False)
        deliveries_df = deliveries_df.rename(columns=delivery_cols)
        print(f"✅ Successfully loaded {len(deliveries_df):,} rows from DELIVERIES.csv.")

        # Clean and convert types
        deliveries_df['sku'] = deliveries_df['sku'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
        deliveries_df['units_issued'] = pd.to_numeric(deliveries_df['units_issued'], errors='coerce').fillna(0)
        deliveries_df['ship_date'] = pd.to_datetime(deliveries_df['ship_date'], format='%m/%d/%y', errors='coerce')
        deliveries_df.dropna(subset=['ship_date'], inplace=True)

        # Filter for the last 12 months
        twelve_months_ago = pd.to_datetime('today') - pd.DateOffset(months=12)
        recent_deliveries = deliveries_df[deliveries_df['ship_date'] >= twelve_months_ago]
        print(f"  - Found {len(recent_deliveries):,} delivery rows within the last 12 months.")

        if recent_deliveries.empty:
            print("🟡 WARNING: No delivery data found in the last 12 months. Daily demand for all items will be 0.")
            daily_demand = pd.DataFrame(columns=['sku', 'daily_demand'])
        else:
            # Calculate average daily demand
            daily_demand = recent_deliveries.groupby('sku')['units_issued'].sum() / 365
            daily_demand = daily_demand.reset_index().rename(columns={'units_issued': 'daily_demand'})
            print(f"  - Calculated daily demand for {len(daily_demand)} unique SKUs.")

    except Exception as e:
        print(f"❌ ERROR: Failed to process 'DELIVERIES.csv' for demand calculation: {e}")
        print("   Daily demand and DIO calculations will be skipped.")
        daily_demand = pd.DataFrame(columns=['sku', 'daily_demand'])

    print("\n--- Sample of Calculated Daily Demand (Top 5 by demand) ---")
    print(daily_demand.sort_values(by='daily_demand', ascending=False).head().to_string(index=False))

    # --- Step 3: Merge Demand and Calculate DIO ---
    print_header("Step 3: Merging Inventory with Demand and Calculating DIO")
    analysis_df = pd.merge(inventory_df, daily_demand, on='sku', how='left')
    # Fill NaN in 'daily_demand' for SKUs that had inventory but no sales
    analysis_df['daily_demand'] = analysis_df['daily_demand'].fillna(0)
    print(f"  - After merging, DataFrame has {len(analysis_df):,} rows.")

    # Calculate DIO
    analysis_df['dio'] = np.where(analysis_df['daily_demand'] > 0, analysis_df['on_hand_qty'] / analysis_df['daily_demand'], 0)
    print("✅ Calculated DIO. Where daily demand is 0, DIO is set to 0.")

    print("\n--- Sample of Data After DIO Calculation (Top 5 by DIO) ---")
    print(analysis_df.sort_values(by='dio', ascending=False).head().to_string(index=False))

    # --- Step 4: Load Master Data and Enrich Final DataFrame ---
    print_header("Step 4: Loading `Master Data.csv` and Enriching with Category")
    master_logs, master_data, _ , _ = load_master_data(MASTER_DATA_FILE_PATH)
    for log in master_logs: print(log)

    if master_data.empty:
        print("❌ STOPPING: Master Data is empty. Cannot add category information.")
        final_df = analysis_df
        final_df['category'] = 'Unknown'
    else:
        # Perform the final merge
        final_df = pd.merge(analysis_df, master_data, on='sku', how='left')
        final_df['category'] = final_df['category'].fillna('Unknown')
        print(f"✅ Merged with Master Data. DataFrame now has {len(final_df):,} rows.")

        # Analyze the merge
        missing_category_count = (final_df['category'] == 'Unknown').sum()
        if missing_category_count > 0:
            print(f"🟡 WARNING: {missing_category_count:,} SKUs from inventory did not find a match in Master Data. Their category is set to 'Unknown'.")
            print("   Sample of SKUs with missing category:")
            print(final_df[final_df['category'] == 'Unknown']['sku'].head().to_string(index=False))

    # --- Final Verdict ---
    print_header("Final Verdict")
    if final_df.empty:
        print("❌ The final inventory analysis DataFrame is EMPTY.")
        print("   This is the reason the report is blank. Review the steps above to see where the data was lost.")
    else:
        print(f"✅ The final inventory analysis DataFrame was created successfully with {len(final_df):,} rows.")
        print("   The data appears to be loading correctly.")
        print("\n   If the dashboard report is still empty, the issue is likely with the filters being applied within the Streamlit app itself.")
        print("   Use the enhanced 'Debug Log' tab in the dashboard to see how filters affect the data count.")

    print("\n--- Final DataFrame Sample (Top 5 by on-hand quantity) ---")
    print(final_df.sort_values(by='on_hand_qty', ascending=False).head().to_string(index=False))

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