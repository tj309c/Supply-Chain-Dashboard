import pandas as pd
import os
import numpy as np

# Import the data loading functions from your project
from data_loader import (
    load_master_data,
    load_orders_header_lookup,
    load_service_data
)

# --- Configuration ---
ORDERS_FILE_PATH = "ORDERS.csv"
DELIVERIES_FILE_PATH = "DELIVERIES.csv"
MASTER_DATA_FILE_PATH = "Master Data.csv"

def print_header(title):
    """Prints a formatted header to the console."""
    bar = "="*80
    print(f"\n{bar}\n🔬 {title.upper()}\n{bar}")

def run_debugger():
    """
    Main function to trace a single delivery line through the service level
    calculation process.
    """
    print_header("Service Level Data Loading Debugger")

    # --- 1. Define the record to investigate ---
    #
    # ★★★ EDIT THIS SECTION to define your investigation ★★★
    #
    # Provide a Sales Order and SKU from a delivery you want to trace.
    # The script will find this specific item in DELIVERIES.csv and follow it.
    #
    TRACE_SALES_ORDER = '0179066866' # Example from test data
    TRACE_SKU = 'ZCHBO20     BO0001'            # Example from test data
    #
    # ★★★ END OF EDITABLE SECTION ★★★
    #

    # --- NEW: Clean the trace variables to prevent whitespace issues ---
    TRACE_SALES_ORDER = TRACE_SALES_ORDER.strip()
    TRACE_SKU = TRACE_SKU.strip().replace(r'\s+', ' ', regex=True)


    print(f"Targeting delivery for Sales Order: '{TRACE_SALES_ORDER}' and SKU: '{TRACE_SKU}'\n")

    # --- 2. Load all necessary data sources ---
    print_header("Step 1: Loading Prerequisite DataFrames")
    
    # Load Master Data
    _, master_data, _, _ = load_master_data(MASTER_DATA_FILE_PATH)
    if master_data.empty:
        print("❌ ERROR: Failed to load Master Data. Aborting.")
        return
    print(f"✅ Master Data loaded with {len(master_data):,} unique SKUs.")

    # Load Order Headers
    _, orders_header_lookup = load_orders_header_lookup(ORDERS_FILE_PATH)
    if orders_header_lookup.empty:
        print("❌ ERROR: Failed to load Orders Header Lookup. Aborting.")
        return
    print(f"✅ Orders Header Lookup loaded with {len(orders_header_lookup):,} unique orders.")

    # Load Raw Deliveries
    try:
        delivery_cols = {
            "Deliveries Detail - Order Document Number": "sales_order",
            "Item - SAP Model Code": "sku",
            "Delivery Creation Date: Date": "ship_date",
            "Deliveries - TOTAL Goods Issue Qty": "units_issued"
        }
        raw_deliveries_df = pd.read_csv(DELIVERIES_FILE_PATH, usecols=list(delivery_cols.keys()), dtype=str)
        raw_deliveries_df.rename(columns=delivery_cols, inplace=True)
        print(f"✅ Raw Deliveries loaded with {len(raw_deliveries_df):,} rows.")
    except Exception as e:
        print(f"❌ ERROR: Failed to read DELIVERIES.csv: {e}")
        return

    # --- 3. Trace the Delivery Line ---
    print_header(f"Step 2: Finding the Target Delivery in '{DELIVERIES_FILE_PATH}'")
    
    # Clean the SKU and Sales Order for matching
    raw_deliveries_df['sku'] = raw_deliveries_df['sku'].str.strip().str.replace(r'\s+', ' ', regex=True)
    raw_deliveries_df['sales_order'] = raw_deliveries_df['sales_order'].str.strip()

    target_delivery_lines = raw_deliveries_df[
        (raw_deliveries_df['sales_order'] == TRACE_SALES_ORDER) &
        (raw_deliveries_df['sku'] == TRACE_SKU)
    ]

    if target_delivery_lines.empty:
        # --- NEW: Enhanced failure analysis ---
        print(f"❌ FAILED: Could not find any delivery lines for Order '{TRACE_SALES_ORDER}' and SKU '{TRACE_SKU}' in {DELIVERIES_FILE_PATH}.")
        print("\n--- Deeper Analysis ---")
        
        # Check if the Sales Order exists at all
        order_exists = TRACE_SALES_ORDER in raw_deliveries_df['sales_order'].unique()
        if order_exists:
            print(f"✅ The Sales Order '{TRACE_SALES_ORDER}' exists in DELIVERIES.csv.")
            # Show SKUs associated with this order
            associated_skus = raw_deliveries_df[raw_deliveries_df['sales_order'] == TRACE_SALES_ORDER]['sku'].unique()
            print(f"   - It is associated with the following SKUs (sample): {list(associated_skus[:5])}")
        else:
            print(f"❌ The Sales Order '{TRACE_SALES_ORDER}' was NOT found anywhere in DELIVERIES.csv.")

        # Check if the SKU exists at all
        sku_exists = TRACE_SKU in raw_deliveries_df['sku'].unique()
        if sku_exists:
            print(f"✅ The SKU '{TRACE_SKU}' exists in DELIVERIES.csv.")
            associated_orders = raw_deliveries_df[raw_deliveries_df['sku'] == TRACE_SKU]['sales_order'].unique()
            print(f"   - It is associated with the following Sales Orders (sample): {list(associated_orders[:5])}")
        else:
            print(f"❌ The SKU '{TRACE_SKU}' was NOT found anywhere in DELIVERIES.csv.")
        print("\nADVICE: Please edit the TRACE_SALES_ORDER and TRACE_SKU variables in this script to a valid combination found in your data and run again.")
        return

    print(f"Found {len(target_delivery_lines)} raw delivery line(s) for this item:")
    print(target_delivery_lines.to_string(index=False))

    # --- 4. Simulate the Aggregation Step ---
    print_header("Step 3: Simulating the Aggregation Logic from `load_service_data`")
    # The main app groups by order/SKU and takes the LATEST ship date and SUM of units.
    aggregated_delivery = target_delivery_lines.groupby(['sales_order', 'sku'], as_index=False).agg(
        ship_date_raw=('ship_date', 'max'),
        units_issued=('units_issued', lambda x: pd.to_numeric(x, errors='coerce').sum())
    )
    print("Aggregated Result (using latest ship date and sum of units):")
    print(aggregated_delivery.to_string(index=False))
    
    ship_date_raw = aggregated_delivery.iloc[0]['ship_date_raw']
    ship_date = pd.to_datetime(ship_date_raw, errors='coerce')
    print(f"\nParsed Ship Date: {ship_date.strftime('%Y-%m-%d') if pd.notna(ship_date) else 'PARSE FAILED'}")
    if pd.isna(ship_date):
        print(f"❌ STOPPING: The ship date '{ship_date_raw}' could not be parsed. This row would be dropped.")
        return

    # --- 5. Trace the Order Header Join ---
    print_header("Step 4: Tracing the Join to Order Headers")
    target_order_header = orders_header_lookup[orders_header_lookup['sales_order'] == TRACE_SALES_ORDER]

    if target_order_header.empty:
        print(f"❌ STOPPING: No matching order header found for '{TRACE_SALES_ORDER}' in the processed Orders data.")
        print("This is a common data mismatch. The delivery line would be dropped at this step.")
        return
    
    print("✅ Found matching order header:")
    print(target_order_header.to_string(index=False))
    order_date = target_order_header.iloc[0]['order_date']
    print(f"\nRetrieved Order Date: {order_date.strftime('%Y-%m-%d')}")

    # --- 6. Trace the Master Data Join ---
    print_header("Step 5: Tracing the Join to Master Data")
    target_master_record = master_data[master_data['sku'] == TRACE_SKU]

    if target_master_record.empty:
        print(f"🟡 WARNING: No matching record found for SKU '{TRACE_SKU}' in Master Data.")
        print("The delivery line would still be included, but its 'category' would be 'Unknown'.")
        category = 'Unknown'
    else:
        print("✅ Found matching master data record:")
        print(target_master_record.to_string(index=False))
        category = target_master_record.iloc[0]['category']
        print(f"\nRetrieved Category: '{category}'")

    # --- 7. Simulate Final Calculations & Verdict ---
    print_header("Step 6: Final Calculation and Verdict")
    
    # Business logic from `load_service_data`
    days_to_deliver = (ship_date - order_date).days
    due_date = order_date + pd.to_timedelta(7, unit='D')
    on_time = ship_date <= due_date

    print("--- Final Calculated Values ---")
    print(f"  Ship Date:        {ship_date.strftime('%Y-%m-%d')}")
    print(f"  Order Date:       {order_date.strftime('%Y-%m-%d')}")
    print(f"  Due Date (calc):  {due_date.strftime('%Y-%m-%d')} (Order Date + 7 days)")
    print(f"  Days to Deliver:  {days_to_deliver}")
    print(f"  On-Time (calc):   {on_time}")
    print("-----------------------------")

    print("\n✅ VERDICT: This delivery line item would successfully be processed and included in the final `service_data` DataFrame.")
    print("If you are not seeing it in the dashboard, the issue is likely due to the filters you have applied.")
    print("Use the 'Debug Log' tab in the dashboard to see how filters affect the data count.")


if __name__ == "__main__":
    # Check that all files exist before proceeding
    required_files = [ORDERS_FILE_PATH, DELIVERIES_FILE_PATH, MASTER_DATA_FILE_PATH]
    files_ok = True
    for f in required_files:
        if not os.path.exists(f):
            print(f"❌ ERROR: Required file '{f}' not found in the current directory: {os.getcwd()}")
            files_ok = False
    
    if files_ok:
        run_debugger()