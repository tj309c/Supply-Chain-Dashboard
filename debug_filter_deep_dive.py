import pandas as pd
import numpy as np
import os
from datetime import datetime

# Import the data loading functions from your project
from data_loader import (
    load_master_data,
    load_orders_item_lookup,
    load_orders_header_lookup, # <-- This was missing
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
    Main function to perform a deep dive into a specific filter combination
    and diagnose unexpected data relationships.
    """
    print_header("Filter Deep Dive Debugger")

    # --- 1. Define the filter and customer to investigate ---
    #
    # ★★★ EDIT THIS SECTION to define your investigation ★★★
    #
    PRIMARY_FILTER_COLUMN = 'sales_org'
    PRIMARY_FILTER_VALUE = ['US20']
    
    UNEXPECTED_CUSTOMER = 'MATCO'
    #
    # ★★★ END OF EDITABLE SECTION ★★★
    #

    print(f"Investigating why customer '{UNEXPECTED_CUSTOMER}' appears when filtering for {PRIMARY_FILTER_COLUMN} = {PRIMARY_FILTER_VALUE}")

    # --- 2. Load all necessary data sources ---
    print_header("Step 1: Loading All Prerequisite Data")
    _, master_data, _, _ = load_master_data(MASTER_DATA_FILE_PATH)
    _, orders_item_lookup, _, _ = load_orders_item_lookup(ORDERS_FILE_PATH)
    _, orders_header_lookup = load_orders_header_lookup(ORDERS_FILE_PATH)
    _, backorder_data, _, _ = load_backorder_data(orders_item_lookup, orders_header_lookup, master_data)

    if backorder_data.empty:
        print("❌ ERROR: The `backorder_data` DataFrame is empty. Cannot proceed with debugging.")
        return
    print(f"✅ Backorder Data loaded successfully with {len(backorder_data):,} rows.")

    # --- 3. Apply the primary filter ---
    print_header(f"Step 2: Applying Primary Filter: `{PRIMARY_FILTER_COLUMN}` = {PRIMARY_FILTER_VALUE}")
    
    rows_before = len(backorder_data)

    # --- FIX: Make filter application more robust ---
    # Handle both single values and lists of values
    if isinstance(PRIMARY_FILTER_VALUE, list):
        filtered_df = backorder_data[backorder_data[PRIMARY_FILTER_COLUMN].isin(PRIMARY_FILTER_VALUE)].copy()
    else: # Handle a single string/int value
        filtered_df = backorder_data[backorder_data[PRIMARY_FILTER_COLUMN] == PRIMARY_FILTER_VALUE].copy()
    rows_after = len(filtered_df)

    print(f"  - Rows before filter: {rows_before:,}")
    print(f"  - Rows after filter:  {rows_after:,}")

    if filtered_df.empty:
        print("\n❌ STOPPING: No data remains after applying the primary filter. The unexpected customer cannot be present.")
        return

    # --- 4. Deep Dive Analysis of the Filtered Data ---
    print_header("Step 3: Deep Dive Analysis of Filtered Data")

    # List all unique customers found within the filtered data
    customers_in_filtered_data = sorted(list(filtered_df['customer_name'].unique()))
    print(f"Found {len(customers_in_filtered_data)} unique customers within the filtered data.")
    
    is_customer_present = UNEXPECTED_CUSTOMER in customers_in_filtered_data
    
    if is_customer_present:
        print(f"  - ✅ CONFIRMED: The customer '{UNEXPECTED_CUSTOMER}' IS PRESENT in the data filtered for {PRIMARY_FILTER_VALUE}.")
    else:
        print(f"  - ✅ SUCCESS: The customer '{UNEXPECTED_CUSTOMER}' was NOT found in the data filtered for {PRIMARY_FILTER_VALUE}.")
        print("\n" + "-"*80)
        print("  DIAGNOSIS: The data on disk is CORRECT. The discrepancy you see in the dashboard is almost certainly due to Streamlit's cache.")
        print("  This script reads files fresh every time; the dashboard uses a saved (stale) version of the data for speed.")
        print("\n  SOLUTION: In the dashboard's sidebar, click the [Clear Cache & Reload Data] button, then re-apply your filters.")
        print("-"*80)
        return

    # --- 5. Find the "Smoking Gun" Records ---
    print_header(f"Step 4: Isolating Records for '{UNEXPECTED_CUSTOMER}' in '{PRIMARY_FILTER_VALUE}'")

    problematic_records = filtered_df[filtered_df['customer_name'] == UNEXPECTED_CUSTOMER]

    print(f"Found {len(problematic_records)} specific record(s) where customer is '{UNEXPECTED_CUSTOMER}'.")
    print("These are the exact rows from `ORDERS.csv` (after processing) that cause this issue:")
    
    # Define columns to display for clarity
    display_cols = [
        'sales_order', 'sku', 'product_name', 'backorder_qty', 
        'sales_org', 'customer_name', 'order_date'
    ]
    display_cols = [col for col in display_cols if col in problematic_records.columns]
    
    print(problematic_records[display_cols].to_string(index=False))

    # --- 6. Replicate Dashboard Chart Aggregation ---
    print_header("Step 5: Replicating Dashboard Chart Aggregation")
    print("This step mimics the `get_backorder_customer_data` function from the dashboard.")

    def weighted_avg(x, weights_df):
        """Helper for weighted average calculation."""
        weights = weights_df.loc[x.index, 'backorder_qty']
        return np.average(x, weights=weights) if weights.sum() > 0 else x.mean()

    # This is the same logic as in dashboard.py
    chart_data = filtered_df.groupby('customer_name').agg(
        total_bo_qty=('backorder_qty', 'sum'),
        avg_days_on_bo=('days_on_backorder', lambda x: weighted_avg(x, filtered_df))
    ).sort_values(by='total_bo_qty', ascending=False)

    customers_in_chart_data = chart_data.index.tolist()
    is_customer_in_chart = UNEXPECTED_CUSTOMER in customers_in_chart_data

    if is_customer_in_chart:
        print(f"  - ⚠️ DISCREPANCY FOUND: The customer '{UNEXPECTED_CUSTOMER}' APPEARS in the aggregated chart data.")
    else:
        print(f"  - ✅ CONSISTENT: The customer '{UNEXPECTED_CUSTOMER}' does NOT appear in the aggregated chart data.")
        print(f"  - This strongly suggests the issue is in the dashboard's cache, not the data logic.")
        print(f"  - ADVICE: In the dashboard sidebar, click 'Clear Cache & Reload Data' and then 'Apply Filters' again.")

    # --- 7. Export Evidence to Excel ---
    print_header("Step 6: Exporting Evidence to Excel")
    output_filename = f"filter_deep_dive_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        print(f"Saving detailed analysis to '{output_filename}'...")
        with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
            # Sheet 1: The specific problematic records
            problematic_records.to_excel(writer, sheet_name='Problematic_Records', index=False)
            
            # Sheet 2: All data that was filtered for the primary value (e.g., all US20 data)
            filtered_df.to_excel(writer, sheet_name=f'All_Data_for_{PRIMARY_FILTER_VALUE[0]}', index=False)
            
            # Sheet 3: A list of all customers found within the filtered data
            pd.DataFrame(customers_in_filtered_data, columns=['Customer_Name']).to_excel(writer, sheet_name='All_Customers_in_Filter', index=False)
            
            # Sheet 4: The data aggregated for the chart
            chart_data.to_excel(writer, sheet_name='Chart_Aggregation_Data', index=True)

        print(f"✅ Report saved successfully to {os.path.abspath(output_filename)}")
    except Exception as e:
        print(f"❌ ERROR: Failed to save Excel report. Error: {e}")

    print("\n--- Debugger Finished ---")

if __name__ == "__main__":
    run_debugger()