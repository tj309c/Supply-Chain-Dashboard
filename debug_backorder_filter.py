import pandas as pd
import os

# Import the data loading functions from your project
from data_loader import (
    load_master_data,
    load_orders_item_lookup,
    load_orders_header_lookup,
    load_backorder_data
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
    Main function to load backorder data and apply filters one by one
    to see where the data is being lost.
    """
    print_header("Backorder Filter Debugger")

    # --- 1. Load all necessary data sources ---
    print("[1/4] Loading Master Data...")
    _, master_data, _, _ = load_master_data(MASTER_DATA_FILE_PATH)
    if master_data.empty:
        print("❌ ERROR: Failed to load Master Data. Aborting.")
        return
    print(f"✅ Master Data loaded with {len(master_data):,} rows.")

    print("\n[2/4] Loading Orders Item Lookup...")
    _, orders_item_lookup, _, _ = load_orders_item_lookup(ORDERS_FILE_PATH)
    if orders_item_lookup.empty:
        print("❌ ERROR: Failed to load Orders Item Lookup. Aborting.")
        return
    print(f"✅ Orders Item Lookup loaded with {len(orders_item_lookup):,} rows.")

    # --- NEW: Pre-analysis before calling the main backorder loader ---
    print_header("Pre-Analysis of Backorder Data Sources")
    backorder_candidates = orders_item_lookup[orders_item_lookup['backorder_qty'] > 0]
    print(f"Found {len(backorder_candidates):,} rows in ORDERS.csv with backorder_qty > 0.")

    if backorder_candidates.empty:
        print("✅ This is the root cause. No items are marked as being on backorder in the source file.")
        return

    master_skus = set(master_data['sku'].unique())
    candidate_skus = set(backorder_candidates['sku'].unique())
    matching_skus = candidate_skus.intersection(master_skus)
    
    print(f"Found {len(candidate_skus):,} unique SKUs among these backorder candidates.")
    print(f"Found {len(matching_skus):,} of those SKUs that have a match in Master Data.")

    if not matching_skus:
        print("❌ This is likely the root cause. None of the SKUs for backordered items could be found in your Master Data file.")
        print("Since the logic removes items without master data, the final table becomes empty.")
        print("ADVICE: Run the `sku_validator.py` script to get a list of the missing SKUs.")
        return

    print("\n[3/4] Loading Orders Header Lookup...")
    _, orders_header_lookup = load_orders_header_lookup(ORDERS_FILE_PATH)
    if orders_header_lookup.empty:
        print("❌ ERROR: Failed to load Orders Header Lookup. Aborting.")
        return

    print("\n[4/4] Loading Backorder Data...")
    _, backorder_data, _, _ = load_backorder_data(orders_item_lookup, orders_header_lookup, master_data)
    if backorder_data.empty:
        print("❌ ERROR: The `load_backorder_data` function returned an empty DataFrame. No backorders found or an error occurred during loading.")
        return

    # --- 2. Define the filters you are using in the dashboard ---
    #
    # ★★★ EDIT THIS SECTION to match the filters you applied in the dashboard ★★★
    #
    test_filters = {
        'order_year': 2024,
        'order_month': 'All',
        'customer_name': [], # Example: ['CUSTOMER-1']
        'category': [],
        'product_name': [],
        'sales_org': [], # Example: ['US20']
        'order_type': [],
        'order_reason': []
    }
    print_header("Filters to be Tested")
    for key, value in test_filters.items():
        if value and value != 'All':
            print(f"  - {key}: {value}")

    # --- 3. Apply filters one by one ---
    print_header("Iterative Filter Application")
    
    df = backorder_data.copy()
    print(f"Starting with {len(df):,} rows in the raw `backorder_data` table.")

    for column, value in test_filters.items():
        # Skip filters that are not set
        if not value or value == "All":
            continue

        rows_before = len(df)
        
        # Apply a single filter
        if isinstance(value, list):
            df = df[df[column].isin(value)]
        else:
            df = df[df[column] == value]
            
        rows_after = len(df)
        
        print(f"\nApplying filter: '{column}' = {value}")
        print(f"  - Rows before: {rows_before:,}")
        print(f"  - Rows after:  {rows_after:,}")
        
        if rows_after == 0:
            print(f"\n❌ STOPPING: Data count dropped to zero after applying the '{column}' filter.")
            print("This is likely the filter causing the issue.")
            print("Check for data type mismatches or whitespace issues for this column and value.")
            return

    print_header("Debugger Finished")
    print(f"✅ SUCCESS: After all filters, {len(df):,} rows remain.")

if __name__ == "__main__":
    run_debugger()