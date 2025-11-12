import pandas as pd
import numpy as np
import io
import os
from datetime import datetime

# Import the data loading functions from your project
from data_loader import (
    load_master_data,
    load_orders_item_lookup,
    load_orders_header_lookup, # NEW: Added for correct backorder data loading
    load_backorder_data
)

# --- Configuration ---
# Ensure these file paths are correct relative to where you run the script
ORDERS_FILE_PATH = "ORDERS.csv"
MASTER_DATA_FILE_PATH = "Master Data.csv"

# --- Helper Functions ---

def print_header(title):
    """Prints a formatted header to the console."""
    print("\n" + "="*80)
    print(f"🔬 {title.upper()}")
    print("="*80)

def get_df_info(df):
    """Captures the output of df.info() into a string for printing."""
    if not isinstance(df, pd.DataFrame):
        return "Not a DataFrame."
    buffer = io.StringIO()
    df.info(buf=buffer)
    return buffer.getvalue()

def apply_filters(df, filters):
    """
    A standalone version of the robust apply_filters function from the dashboard.
    """
    if df.empty:
        return df
    
    # Start with a mask that includes all rows
    combined_mask = pd.Series(True, index=df.index)

    print_header("Applying Filters")
    print(f"Starting with {len(df)} rows.")

    for column, value in filters.items():
        if not value or value == "All":
            continue
        
        if column not in df.columns:
            print(f"  - SKIPPING filter for '{column}': Column not found in DataFrame.")
            continue

        if isinstance(value, list):
            # For multiselect, use .isin()
            combined_mask &= df[column].isin(value)
        else:
            # For selectbox, use standard equality
            combined_mask &= (df[column] == value)
        
        print(f"  - Applied filter: '{column}' = {value}.")
            
    return df[combined_mask]


def run_debugger():
    """Main function to run the debugging process."""

    # --- 1. Load Master Data ---
    print_header("Loading Master Data")
    logs, master_data, _, _ = load_master_data(MASTER_DATA_FILE_PATH)
    for log in logs: print(log)
    print(f"Master Data Shape: {master_data.shape}")
    print(get_df_info(master_data))
    print("--- Master Data Head ---")
    print(master_data.head())

    # --- 2. Load Orders Item Lookup ---
    print_header("Loading Orders Item Lookup")
    logs, orders_item_lookup, _, _ = load_orders_item_lookup(ORDERS_FILE_PATH)
    for log in logs: print(log)
    print(f"Orders Item Lookup Shape: {orders_item_lookup.shape}")
    print(get_df_info(orders_item_lookup))
    print("--- Orders Item Lookup Head ---")
    print(orders_item_lookup.head())
    
    # --- 2.5. Load Orders Header Lookup ---
    print_header("Loading Orders Header Lookup")
    logs, orders_header_lookup = load_orders_header_lookup(ORDERS_FILE_PATH)
    for log in logs: print(log)

    # --- 3. Load Backorder Data (BEFORE Filtering) ---
    print_header("Loading Backorder Data (This is the data BEFORE filtering)")
    logs, backorder_data, _, _ = load_backorder_data(orders_item_lookup, orders_header_lookup, master_data)
    for log in logs: print(log)
    
    if backorder_data.empty:
        print("\nERROR: The `load_backorder_data` function returned an empty DataFrame. No backorders found or an error occurred.")
        return

    print(f"Backorder Data Shape: {backorder_data.shape}")
    print(get_df_info(backorder_data))
    print("--- Backorder Data Head (BEFORE filtering) ---")
    print(backorder_data.head())

    # --- 4. Define and Apply Filters ---
    # We will use a specific, hardcoded filter to test the logic.
    # This simulates a user selecting '2024' and 'US20'.
    test_filters = {
        'order_year': 2024,
        'order_month': 'All',
        'customer_name': [],
        'category': [],
        'product_name': [],
        'sales_org': ['US20'],
        'order_type': [],
        'order_reason': []
    }
    print_header("Filter Dictionary being used for this test")
    print(test_filters)

    filtered_backorder_data = apply_filters(backorder_data, test_filters)

    # --- 5. Analyze Filtered Data ---
    print_header("Analysis of Backorder Data AFTER Filtering")
    print(f"Filtered Backorder Data Shape: {filtered_backorder_data.shape}")
    print(get_df_info(filtered_backorder_data))
    print("--- Filtered Backorder Data Head ---")
    print(filtered_backorder_data.head())

    print_header("Summary")
    print(f"Rows in `backorder_data` before filtering: {len(backorder_data)}")
    print(f"Rows in `filtered_backorder_data` after filtering: {len(filtered_backorder_data)}")
    print(f"Total rows removed by filters: {len(backorder_data) - len(filtered_backorder_data)}")

if __name__ == "__main__":
    run_debugger()