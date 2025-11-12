import pandas as pd
import os
import numpy as np

# Import the data loading functions from your project
from data_loader import (
    load_inventory_data,
    load_inventory_analysis_data,
    load_master_data
)

# --- Configuration ---
INVENTORY_FILE_PATH = "INVENTORY.csv"
DELIVERIES_FILE_PATH = "DELIVERIES.csv"
MASTER_DATA_FILE_PATH = "Master Data.csv"

SKU_COL_RAW = "Material Number"
ON_HAND_COL_RAW = "POP Actual Stock Qty"

def print_header(title):
    """Prints a formatted header to the console."""
    bar = "="*80
    print(f"\n{bar}\n🔬 {title.upper()}\n{bar}")

def check_column_exists(df, col_name, df_name):
    """Checks for column existence and prints a clear pass/fail message."""
    if col_name in df.columns:
        print(f"✅ SUCCESS: Column '{col_name}' exists in the '{df_name}' DataFrame.")
        return True
    else:
        print(f"❌ FAILED: Column '{col_name}' is MISSING from the '{df_name}' DataFrame.")
        print(f"   Available columns are: {df.columns.tolist()}")
        return False

def run_debugger():
    """
    Main function to trace the `on_hand_qty` data from raw file to final
    analysis DataFrame, diagnosing issues at each step.
    """
    print_header("On-Hand Quantity (on_hand_qty) Pipeline Debugger")

    # --- Step 1: Raw File and Column Validation ---
    print_header("Step 1: Raw `INVENTORY.csv` File Inspection")
    if not os.path.isfile(INVENTORY_FILE_PATH):
        print(f"❌ STOPPING: File not found at '{os.path.abspath(INVENTORY_FILE_PATH)}'.")
        return

    try:
        raw_df = pd.read_csv(INVENTORY_FILE_PATH, low_memory=False, dtype=str)
        print(f"✅ Successfully read {len(raw_df):,} rows from the raw CSV.")
    except Exception as e:
        print(f"❌ STOPPING: Failed to read the CSV file. Error: {e}")
        return

    if ON_HAND_COL_RAW not in raw_df.columns:
        print(f"\n❌ STOPPING: The required raw column '{ON_HAND_COL_RAW}' was not found in INVENTORY.csv.")
        print(f"   Available columns are: {raw_df.columns.tolist()}")
        return
    print(f"✅ SUCCESS: Found required raw column '{ON_HAND_COL_RAW}'.")

    # Analyze the raw column for non-numeric issues (beyond just commas)
    temp_series = raw_df[ON_HAND_COL_RAW].astype(str).str.replace(',', '', regex=False)
    non_numeric_mask = pd.to_numeric(temp_series, errors='coerce').isna()
    problematic_values = raw_df.loc[non_numeric_mask, ON_HAND_COL_RAW].dropna().unique()

    if len(problematic_values) > 0:
        print(f"🟡 WARNING: Found {len(problematic_values)} unique non-numeric values in '{ON_HAND_COL_RAW}' that will be treated as 0.")
        print(f"   Sample problematic values: {list(problematic_values[:5])}")
    else:
        print("✅ SUCCESS: All values in the raw stock column appear to be numeric (or blank).")

    # --- Step 2: Run `load_inventory_data` ---
    print_header("Step 2: Processing with `load_inventory_data`")
    inv_logs, inventory_df, _ = load_inventory_data(INVENTORY_FILE_PATH)
    for log in inv_logs: print(log)

    if inventory_df.empty:
        print("\n❌ STOPPING: The `load_inventory_data` function returned an empty DataFrame.")
        print("   This is a critical failure. Check logs above for file reading or column name errors.")
        return

    if not check_column_exists(inventory_df, 'on_hand_qty', 'inventory_df'):
        print("\n❌ STOPPING: The `on_hand_qty` column was lost during the initial load and aggregation.")
        return

    total_on_hand = inventory_df['on_hand_qty'].sum()
    print(f"\n✅ `load_inventory_data` successful. Total on-hand units: {total_on_hand:,.0f}")
    if total_on_hand == 0:
        print("🟡 WARNING: Total on-hand stock is zero. The final report will be empty or show all zeros.")

    # --- Step 3: Run `load_inventory_analysis_data` ---
    print_header("Step 3: Processing with `load_inventory_analysis_data`")
    
    # Load prerequisites for the function
    print("  - Loading prerequisites (Master Data)...")
    master_logs, master_data, _ = load_master_data(MASTER_DATA_FILE_PATH)
    for log in master_logs: print(f"    {log}")
    if master_data.empty:
        print("  - 🟡 WARNING: Master Data is empty. Category information will be missing.")

    print("\n  - Calling `load_inventory_analysis_data`...")
    analysis_logs, final_inventory_df = load_inventory_analysis_data(
        inventory_df, DELIVERIES_FILE_PATH, master_data
    )
    for log in analysis_logs: print(f"    {log}")

    if final_inventory_df.empty:
        print("\n❌ STOPPING: The `load_inventory_analysis_data` function returned an empty DataFrame.")
        print("   This suggests data was lost during the demand calculation or master data merge.")
        return

    # --- Step 4: Final DataFrame Inspection ---
    print_header("Step 4: Final DataFrame Inspection")
    
    print("This is the final `inventory_analysis_data` DataFrame that is sent to the dashboard.")
    
    if not check_column_exists(final_inventory_df, 'on_hand_qty', 'final_inventory_df'):
        print("\n❌ CRITICAL FAILURE: The 'on_hand_qty' column was lost during the `load_inventory_analysis_data` step.")
        print("   This is the reason for the `KeyError` in the dashboard.")
        print("   ADVICE: Review the merge and `fillna` logic in `load_inventory_analysis_data` in `data_loader.py`.")
        print("   The `.fillna(0)` might be too broad and affecting the wrong columns.")
        return

    # Check data type
    if pd.api.types.is_numeric_dtype(final_inventory_df['on_hand_qty']):
        print("✅ SUCCESS: The 'on_hand_qty' column has a numeric data type.")
    else:
        print(f"❌ FAILED: The 'on_hand_qty' column has a non-numeric data type: {final_inventory_df['on_hand_qty'].dtype}")
        print("   This will cause calculation errors.")
        return

    final_total_on_hand = final_inventory_df['on_hand_qty'].sum()
    print(f"✅ SUCCESS: The final total on-hand quantity is {final_total_on_hand:,.0f}.")

    if total_on_hand != final_total_on_hand:
        print(f"🟡 WARNING: The total on-hand quantity changed during the analysis step.")
        print(f"   - Before: {total_on_hand:,.0f}")
        print(f"   - After:  {final_total_on_hand:,.0f}")
        print("   This indicates that some rows may have been dropped or values altered unexpectedly.")

    # --- Final Verdict ---
    print_header("Final Verdict")
    print("✅ The `debug_on_hand_qty.py` script confirms that the `on_hand_qty` column is being correctly processed and is present in the final DataFrame.")
    print("\nIf the dashboard report is still empty, the problem lies in the `dashboard.py` script itself.")
    print("Specifically, check the following in `dashboard.py`:")
    print("  1. The `apply_filters` function: Is it incorrectly filtering the inventory data based on filters from other reports (like 'order_year')?")
    print("  2. The report display logic: Is the code block for the 'Inventory Management' report correctly accessing the `f_inventory` DataFrame?")

    print("\n--- Final DataFrame Sample (Top 5 by on-hand quantity) ---")
    print(final_inventory_df.sort_values(by='on_hand_qty', ascending=False).head().to_string(index=False))

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