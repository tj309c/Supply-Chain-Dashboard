import pandas as pd
import os

# Import the data loading functions from your project
from data_loader import (
    load_master_data,
    load_orders_item_lookup,
    load_orders_header_lookup
)

# --- Configuration ---
ORDERS_FILE_PATH = "ORDERS.csv"
MASTER_DATA_FILE_PATH = "Master Data.csv"

def print_header(title):
    """Prints a formatted header to the console."""
    print("\n" + "="*80)
    print(f"🔬 {title.upper()}")
    print("="*80)

def run_debugger():
    """
    Main function to trace the creation of the backorder_data DataFrame
    and diagnose where data is being lost.
    """
    print_header("Backorder Data Loading Debugger")

    # --- 1. Load all base data sources ---
    print("\n--- Step 1: Loading Prerequisite Data ---")
    _, master_data, _, _ = load_master_data(MASTER_DATA_FILE_PATH)
    if master_data.empty:
        print("❌ ERROR: Failed to load Master Data. Aborting.")
        return
    print(f"✅ Master Data loaded with {len(master_data):,} unique SKUs.")

    _, orders_item_lookup, _, _ = load_orders_item_lookup(ORDERS_FILE_PATH)
    if orders_item_lookup.empty:
        print("❌ ERROR: Failed to load Orders Item Lookup. Aborting.")
        return
    print(f"✅ Orders Item Lookup loaded with {len(orders_item_lookup):,} aggregated rows.")

    _, orders_header_lookup = load_orders_header_lookup(ORDERS_FILE_PATH)
    if orders_header_lookup.empty:
        print("❌ ERROR: Failed to load Orders Header Lookup. Aborting.")
        return
    print(f"✅ Orders Header Lookup loaded with {len(orders_header_lookup):,} unique orders.")

    # --- 2. Recreate the backorder_data creation process step-by-step ---
    print_header("Step-by-Step Analysis of `backorder_data` Creation")

    # Step 2.1: Filter for items with backorder_qty > 0
    df = orders_item_lookup[orders_item_lookup['backorder_qty'] > 0].copy()
    print(f"Step 2.1: Filtering for `backorder_qty > 0`")
    print(f"  - Rows remaining: {len(df):,}")
    if df.empty:
        print("\n❌ STOPPING: No rows in 'ORDERS.csv' have a `backorder_qty` greater than 0.")
        print("  This is the root cause. The final DataFrame is empty because there are no backorders to begin with.")
        return

    # Step 2.2: Merge with Order Headers to get authoritative order_date
    header_cols_to_drop = ['order_date']
    df.drop(columns=header_cols_to_drop, inplace=True, errors='ignore')
    header_subset = orders_header_lookup[['sales_order', 'order_date']]
    df = pd.merge(df, header_subset, on='sales_order', how='left')
    print(f"\nStep 2.2: Merging with Order Headers to get `order_date`")
    print(f"  - Rows remaining: {len(df):,}")

    # Step 2.3: Merge with Master Data to get `category`
    master_data_subset = master_data[['sku', 'category']]
    df = pd.merge(df, master_data_subset, on='sku', how='left')
    print(f"\nStep 2.3: Merging with Master Data to get `category`")
    print(f"  - Rows remaining: {len(df):,}")

    # Step 2.4: Analyze the result of the master data merge (CRITICAL STEP)
    missing_category_mask = df['category'].isna()
    num_missing = missing_category_mask.sum()
    print(f"\nStep 2.4: Analyzing the Master Data join result")
    print(f"  - Found {num_missing:,} rows that did NOT have a matching SKU in Master Data.")

    if num_missing == len(df):
        print("\n❌ STOPPING: 100% of the backordered items could not find a matching SKU in the Master Data.")
        print("  This is the root cause. The next step removes all these rows, resulting in an empty table.")
        print("  ADVICE: Check for data type mismatches between 'Item - SAP Model Code' in ORDERS.csv and 'Material Number' in Master Data.csv. Ensure both are treated as strings.")
        
        # --- NEW: Show sample SKUs for visual comparison ---
        print("\n" + "-"*80)
        print("🔍 To help diagnose, here is a sample of SKUs from each source file:")
        
        sample_size = 15
        print(f"\nSample of the first {sample_size} SKUs from backordered items (ORDERS.csv):")
        print(df['sku'].dropna().head(sample_size).to_string(index=False))
        print(f"\nSample of the first {sample_size} SKUs from Master Data (Master Data.csv):")
        print(master_data['sku'].dropna().head(sample_size).to_string(index=False))
        print("-" * 80)
        return
    elif num_missing > 0:
        print(f"  - These {num_missing:,} rows will be dropped in the next step.")

    # Step 2.5: Drop rows where the master data lookup failed
    rows_before_drop = len(df)
    df.dropna(subset=['category'], inplace=True)
    rows_after_drop = len(df)
    print(f"\nStep 2.5: Dropping rows with no matching Master Data")
    print(f"  - Rows before drop: {rows_before_drop:,}")
    print(f"  - Rows after drop:  {rows_after_drop:,}")

    if df.empty:
        print("\n❌ STOPPING: The DataFrame is now empty after dropping items with no category.")
        print("  This confirms the data loss is due to missing master data for all backordered SKUs.")
        return

    # --- 3. Final Summary ---
    print_header("Debugger Finished")
    initial_candidates = len(orders_item_lookup[orders_item_lookup['backorder_qty'] > 0])
    final_rows = len(df)
    print(f"Initial backorder candidates: {initial_candidates:,}")
    print(f"Final rows in `backorder_data`: {final_rows:,}")
    print(f"Total rows lost during loading: {initial_candidates - final_rows:,}")

if __name__ == "__main__":
    run_debugger()