import pandas as pd
import os
from datetime import datetime

# Import the data loading functions from your project
from data_loader import (
    load_master_data,
    load_orders_item_lookup
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
    Main function to identify backordered items with 'Unknown' product names.
    """
    print_header("Debugger for 'Unknown' Product Names on Backorder Report")

    # --- 1. Load Master Data and Orders ---
    print("[1/3] Loading Master Data...")
    _, master_data, _, _ = load_master_data(MASTER_DATA_FILE_PATH)
    if master_data.empty:
        print("❌ ERROR: Failed to load Master Data. Aborting.")
        return

    print("[2/3] Loading Orders Item Data...")
    _, orders_item_lookup, _, _ = load_orders_item_lookup(ORDERS_FILE_PATH)
    if orders_item_lookup.empty:
        print("❌ ERROR: Failed to load Orders data. Aborting.")
        return

    # --- 2. Isolate Backordered Items and Find Missing SKUs ---
    print("[3/3] Analyzing backordered items...")
    
    # Get only the rows that are on backorder
    backordered_items = orders_item_lookup[orders_item_lookup['backorder_qty'] > 0].copy()
    if backordered_items.empty:
        print("✅ SUCCESS: No items are currently on backorder. No 'Unknown' names to report.")
        return

    # --- NEW: Report on data types to help diagnose mismatches ---
    print_header("Data Type Analysis")
    print(f"Data type of 'sku' column from ORDERS.csv: {orders_item_lookup['sku'].dtype}")
    print(f"Data type of 'sku' column from Master Data.csv: {master_data['sku'].dtype}")
    print("NOTE: For a successful join, these data types should ideally both be 'object' (string).")

    # --- NEW: Create a DataFrame for the data type diagnostics ---
    diagnostics_data = {
        'Source File': ['ORDERS.csv', 'Master Data.csv'],
        'Original SKU Column': ['Item - SAP Model Code', 'Material Number'],
        'Data Type in DataFrame': [str(orders_item_lookup['sku'].dtype), str(master_data['sku'].dtype)]
    }
    diagnostics_df = pd.DataFrame(diagnostics_data)

    # --- NEW: Perform a left merge to explicitly find items without a match ---
    # The `indicator=True` adds a column named '_merge' that tells us the source of each row.
    merged_df = pd.merge(
        backordered_items,
        master_data,
        on='sku',
        how='left',
        indicator=True
    )
    
    # Filter for rows that only exist in the 'left' DataFrame (backordered_items),
    # meaning they did not find a match in the master data.
    missing_details_df = merged_df[merged_df['_merge'] == 'left_only'].copy()

    # --- 3. Report the Findings ---
    print_header("Analysis Report")

    if missing_details_df.empty:
        print("✅ SUCCESS: All SKUs for backordered items were found in the Master Data file.")
        print("This means any 'Unknown' product names are likely due to other data quality issues (e.g., blank product descriptions in Master Data).")
    else:
        print(f"⚠️ WARNING: Found {len(missing_details_df)} backordered items with SKUs that are MISSING from the Master Data file.")
        print("These items will appear with an 'Unknown' product name in the dashboard.")
        
        print("\n--- Details of Backordered Items with Missing Master Data ---")
        # --- UPDATED: Display all requested columns for the detailed report ---
        display_cols = [
            'sales_order', 'sku', 'order_date', 'order_date_raw',
            'ordered_qty', 'backorder_qty', 'cancelled_qty',
            'customer_name', 'sales_org', 'reject_reason',
            'order_type', 'order_reason',
            'category', 'product_name', '_merge'
        ]
        
        # Ensure all display_cols are actually present in missing_details_df
        # This handles cases where some columns might not exist due to earlier filtering/merging
        display_cols = [col for col in display_cols if col in missing_details_df.columns]

        # Fill NaN values in the product_name, brand, category for display clarity
        # as these are the ones that would be 'Unknown' in the dashboard
        missing_details_df['product_name'] = missing_details_df['product_name'].fillna('Unknown')
        missing_details_df['category'] = missing_details_df['category'].fillna('Unknown')
        print(missing_details_df[display_cols].to_string(index=False))

        # Save the detailed report to an Excel file
        output_filename = f"unknown_product_name_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        try:
            print(f"\nSaving this detailed report to '{output_filename}'...")
            # --- NEW: Use ExcelWriter to save multiple sheets ---
            with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
                missing_details_df.to_excel(writer, sheet_name='Missing_SKU_Details', index=False)
                diagnostics_df.to_excel(writer, sheet_name='DataType_Analysis', index=False)

            print(f"✅ Report saved successfully to {os.path.abspath(output_filename)}")
        except Exception as e:
            print(f"❌ ERROR: Failed to save Excel report. Error: {e}")

    print("\n--- Debugger Finished ---")

if __name__ == "__main__":
    run_debugger()