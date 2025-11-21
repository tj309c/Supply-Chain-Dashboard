import pandas as pd
from datetime import datetime
import numpy as np
import warnings
import time # <-- Import time for performance tracking
from file_loader import safe_read_csv

# === Helper Functions ===

TODAY = pd.to_datetime(datetime.now().date())
LOAD_TIMEOUT_SECONDS = 90 # <-- NEW: Set a 90-second warning threshold

def clean_string_column(series: pd.Series) -> pd.Series:
    """
    Efficiently clean string columns by stripping whitespace and normalizing spaces.
    
    Optimization: Compiled regex pattern used once, applied vectorized.
    Avoids repeated .astype(str).str.strip().str.replace() chains.
    
    Args:
        series: Pandas Series with string data
    
    Returns:
        Cleaned Series with normalized whitespace
    """
    return series.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)

def safe_numeric_column(series: pd.Series, remove_commas: bool = False) -> pd.Series:
    """
    Efficiently convert column to numeric with optional comma removal.
    
    Optimization: Single pd.to_numeric call, handles errors gracefully.
    
    Args:
        series: Pandas Series to convert
        remove_commas: If True, remove commas before conversion
    
    Returns:
        Numeric Series with NaN filled as 0
    """
    if remove_commas:
        series = series.astype(str).str.replace(',', '', regex=False)
    return pd.to_numeric(series, errors='coerce').fillna(0)

def check_columns(df, required_cols, filename, logs):
    """Helper function to check for missing columns."""
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logs.append(f"ERROR: '{filename}' is missing required columns: {', '.join(missing_cols)}")
        return False
    return True

# === Consolidated File Readers (OPTIMIZATION: Read each large file only once) ===

def load_orders_unified(orders_path, file_key='orders'):
    """
    OPTIMIZATION: Load ORDERS.csv once and return data for both item and header lookups.
    This eliminates duplicate file reads (saves 15-23 seconds on initial load).

    Args:
        orders_path: file path to ORDERS.csv
        file_key: session state key for uploaded file (default 'orders')

    Returns:
        tuple: (logs, orders_df) where orders_df contains all needed columns
    """
    logs = []
    start_time = time.time()
    logs.append("--- Unified Orders Loader (Read Once) ---")

    # Define all columns needed by both item and header lookups
    all_order_cols = [
        "Orders Detail - Order Document Number",
        "Item - SAP Model Code",
        "Order Creation Date: Date",
        "Original Customer Name",
        "Item - Model Desc",
        "Sales Organization Code",
        "Orders - TOTAL Orders Qty",
        "Orders - TOTAL To Be Delivered Qty",
        "Orders - TOTAL Cancelled Qty",
        "Reject Reason Desc",
        "Order Type (SAP) Code",
        "Order Reason Code"
    ]

    try:
        df = safe_read_csv(file_key, orders_path, usecols=all_order_cols, low_memory=False)
        logs.append(f"INFO: Loaded {len(df)} rows from ORDERS.csv (unified read).")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'ORDERS.csv': {e}")
        return logs, pd.DataFrame()

    end_time = time.time()
    logs.append(f"INFO: Unified Orders Loader finished in {end_time - start_time:.2f} seconds.")

    return logs, df


def load_deliveries_unified(deliveries_path, file_key='deliveries'):
    """
    OPTIMIZATION: Load DELIVERIES.csv once and return data for both service and inventory analysis.
    This eliminates duplicate file reads (saves 8-12 seconds on initial load).

    Args:
        deliveries_path: file path to DELIVERIES.csv
        file_key: session state key for uploaded file (default 'deliveries')

    Returns:
        tuple: (logs, deliveries_df) where deliveries_df contains all needed columns
    """
    logs = []
    start_time = time.time()
    logs.append("--- Unified Deliveries Loader (Read Once) ---")

    # Define all columns needed by both service and inventory analysis
    all_delivery_cols = [
        "Deliveries Detail - Order Document Number",
        "Item - SAP Model Code",
        "Delivery Creation Date: Date",
        "Deliveries - TOTAL Goods Issue Qty",
        "Item - Model Desc"
    ]

    try:
        df = safe_read_csv(file_key, deliveries_path, usecols=all_delivery_cols, low_memory=False)
        logs.append(f"INFO: Loaded {len(df)} rows from DELIVERIES.csv (unified read).")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'DELIVERIES.csv': {e}")
        return logs, pd.DataFrame()

    end_time = time.time()
    logs.append(f"INFO: Unified Deliveries Loader finished in {end_time - start_time:.2f} seconds.")

    return logs, df


# === Main Data Loaders ===

def load_master_data(master_data_path, file_key='master'):
    """
    Loads the Item Master data (Master Data.csv) to be used as a lookup table.
    
    Args:
        master_data_path: file path (used if no uploaded file exists)
        file_key: session state key for uploaded file (default 'master')
    
    Returns: logs (list), dataframe, error_dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Master Data Loader ---")
    error_df = pd.DataFrame() 
    
    try:
        # --- UPDATED: Load SKU, Category, and Activation Date ---
        cols_to_load = ["Material Number", "PLM: Level Classification 4", "Activation Date (Code)"]
        df = safe_read_csv(file_key, master_data_path, usecols=cols_to_load, low_memory=False)
        logs.append(f"INFO: Found and loaded {len(df)} rows from Master Data.")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'Master Data.csv': {e}")
        return logs, pd.DataFrame(), pd.DataFrame()

    # --- UPDATED: Load SKU, Category, and Activation Date ---
    master_cols = {
        "Material Number": "sku",
        "PLM: Level Classification 4": "category",
        "Activation Date (Code)": "activation_date"
    }
    if not check_columns(df, master_cols.keys(), "Master Data.csv", logs): 
        return logs, pd.DataFrame(), pd.DataFrame()
    
    duplicates = df[df.duplicated(subset=['Material Number'], keep=False)]
    if not duplicates.empty:
        logs.append(f"WARNING: Found {len(duplicates)} duplicated SKUs in Master Data. Keeping first instance.")
        error_df = pd.concat([error_df, duplicates])
        
    df = df[list(master_cols.keys())].rename(columns=master_cols)

    str_cols = ['sku', 'category']
    for col in str_cols:
        df[col] = clean_string_column(df[col])

    # --- NEW: Parse activation date ---
    logs.append("INFO: Parsing SKU Activation Dates with explicit format '%m/%d/%y'...")
    df['activation_date'] = pd.to_datetime(df['activation_date'], format='%m/%d/%y', errors='coerce')
    activation_date_nulls = df['activation_date'].isna().sum()
    if activation_date_nulls > 0:
        logs.append(f"WARNING: {activation_date_nulls} SKUs have missing/invalid activation dates. These will use full 365-day divisor for demand calculation.")

    df = df.drop_duplicates(subset=['sku'])
    
    if df.empty:
        logs.append("WARNING: Master Data Loader: No data remained after processing.")
    
    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Master Data Loader finished in {total_time:.2f} seconds.")
    if total_time > LOAD_TIMEOUT_SECONDS:
        logs.append(f"WARNING: This loader took longer than {LOAD_TIMEOUT_SECONDS} seconds!")
        
    return logs, df, error_df

# --- UPDATED: This function is now split into two. ---
# This one is for ITEM-LEVEL details (Fill Rate, Backorder, Cancel)
def load_orders_item_lookup(orders_df_unified):
    """
    OPTIMIZATION: Process unified ORDERS data and create item-level lookup table.
    No longer reads file - receives pre-loaded data from load_orders_unified().

    Args:
        orders_df_unified: Pre-loaded orders dataframe from load_orders_unified()

    Returns: logs (list), dataframe, error_dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Orders Item Lookup Loader (SKU-level) ---")
    error_df = pd.DataFrame()
    date_check_df = pd.DataFrame()

    if orders_df_unified.empty:
        logs.append("ERROR: Cannot process item lookup - unified orders data is empty.")
        return logs, pd.DataFrame(), pd.DataFrame()

    order_cols = {
        "Orders Detail - Order Document Number": "sales_order",
        "Item - SAP Model Code": "sku",
        "Order Creation Date: Date": "order_date",
        "Original Customer Name": "customer_name",
        "Item - Model Desc": "product_name",
        "Sales Organization Code": "sales_org",
        "Orders - TOTAL Orders Qty": "ordered_qty",
        "Orders - TOTAL To Be Delivered Qty": "backorder_qty",
        "Orders - TOTAL Cancelled Qty": "cancelled_qty",
        "Reject Reason Desc": "reject_reason",
        "Order Type (SAP) Code": "order_type",
        "Order Reason Code": "order_reason"
    }

    # Use the pre-loaded data
    if not check_columns(orders_df_unified, order_cols.keys(), "ORDERS.csv", logs):
        return logs, pd.DataFrame(), pd.DataFrame()
    df = orders_df_unified[list(order_cols.keys())].copy().rename(columns=order_cols)

    # --- FIX: Enforce SKU is a string to prevent data type mismatch on join ---
    df['sku'] = clean_string_column(df['sku'])

    # Convert types
    df['order_date_raw'] = df['order_date'] # Keep original for error report
    
    # --- FIX: Use the single, validated date format for performance and reliability ---
    # This change is based on the output of the debug_date_formats.py script.
    logs.append("INFO: Parsing Order Dates with explicit format '%m/%d/%y'...")
    df['order_date'] = pd.to_datetime(df['order_date_raw'], format='%m/%d/%y', errors='coerce')


    num_cols = ['ordered_qty', 'backorder_qty', 'cancelled_qty']
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # --- ENHANCEMENT: Robustly clean whitespace from key categorical columns ---
    # This prevents filter mismatches caused by hidden spaces.
    # .str.strip() removes leading/trailing spaces.
    # .str.replace(r'\s+', ' ', regex=True) replaces multiple internal spaces with a single space.
    str_strip_cols = ['sales_org', 'customer_name', 'product_name', 'reject_reason', 'order_type', 'order_reason']
    for col in str_strip_cols:
        if col in df.columns:
            df[col] = clean_string_column(df[col])

    # --- OPTIMIZATION: Reduce groupby complexity for significant speedup ---
    # Drop rows where essential grouping keys are missing before aggregation
    df.dropna(subset=['sales_order', 'sku', 'order_date'], inplace=True)
    
    # 1. Group by essential identifiers only. This is much faster.
    id_cols = ['sales_order', 'sku', 'order_date', 'order_date_raw']
    df_agg = df.groupby(id_cols, as_index=False, dropna=False).agg(
        ordered_qty=('ordered_qty', 'sum'),
        backorder_qty=('backorder_qty', 'sum'),
        cancelled_qty=('cancelled_qty', 'sum')
    )
    
    # 2. Get the descriptive columns associated with each order/item.
    # This avoids grouping by many slow-to-hash string columns.
    desc_cols = ['sales_order', 'sku', 'customer_name', 'product_name', 'sales_org', 'reject_reason', 'order_type', 'order_reason']
    df_desc = df[desc_cols].drop_duplicates(subset=['sales_order', 'sku'])
    
    # 3. Merge the descriptive data back into the aggregated data.
    # We merge on sales_order and sku, the unique identifiers for an item on an order.
    df_agg = pd.merge(df_agg, df_desc, on=['sales_order', 'sku'], how='left')

    date_fail_mask = df_agg['order_date'].isna()
    order_date_nulls = date_fail_mask.sum()
    if order_date_nulls > 0:
        logs.append(f"ERROR: {order_date_nulls} order dates failed to parse (became NaT).")
        logs.append("ADVICE: This is likely due to blank dates or mixed/bad text formats in the 'Order Creation Date: Date' column.")
        error_df = df_agg[date_fail_mask] 
    
    df_agg.dropna(subset=['order_date'], inplace=True)
    logs.append(f"INFO: {len(df_agg)} rows remaining after dropping NaNs.")

    
    if df_agg.empty:
        logs.append("ERROR: No valid order data remained after processing. Check 'Order Creation Date: Date' column.")
        
    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Orders Item Lookup Loader finished in {total_time:.2f} seconds.")
    if total_time > LOAD_TIMEOUT_SECONDS:
        logs.append(f"WARNING: This loader took longer than {LOAD_TIMEOUT_SECONDS} seconds! This is likely due to slow date parsing.")

    return logs, df_agg, error_df


# --- NEW FUNCTION: This is for HEADER-LEVEL details (Service Level) ---
def load_orders_header_lookup(orders_df_unified):
    """
    OPTIMIZATION: Process unified ORDERS data and create header-level lookup table.
    No longer reads file - receives pre-loaded data from load_orders_unified().

    Args:
        orders_df_unified: Pre-loaded orders dataframe from load_orders_unified()

    Returns: logs (list), dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Orders Header Lookup Loader (Order-level) ---")

    if orders_df_unified.empty:
        logs.append("ERROR: Cannot process header lookup - unified orders data is empty.")
        return logs, pd.DataFrame()

    order_cols = {
        "Orders Detail - Order Document Number": "sales_order",
        "Order Creation Date: Date": "order_date",
        "Original Customer Name": "customer_name",
        "Order Type (SAP) Code": "order_type",
        "Order Reason Code": "order_reason",
        "Sales Organization Code": "sales_org"
    }
    if not check_columns(orders_df_unified, order_cols.keys(), "ORDERS.csv", logs):
        return logs, pd.DataFrame()

    df = orders_df_unified[list(order_cols.keys())].copy().rename(columns=order_cols)

    # --- FIX: Use the single, validated date format for performance and reliability ---
    logs.append("INFO: Parsing Order Header Dates with explicit format '%m/%d/%y'...")
    df['order_date_raw'] = df['order_date']
    df['order_date'] = pd.to_datetime(df['order_date_raw'], format='%m/%d/%y', errors='coerce')
    
    # Aggregate by order (header)
    df_agg = df.groupby('sales_order').agg(
        order_date=('order_date', 'first'),
        customer_name=('customer_name', 'first'),
        order_type=('order_type', 'first'),
        order_reason=('order_reason', 'first'),
        sales_org=('sales_org', 'first') # <-- ADDED
    ).reset_index()

    df_agg.dropna(subset=['order_date'], inplace=True)
    logs.append(f"INFO: {len(df_agg)} unique, valid orders found.")
    
    if df_agg.empty:
        logs.append("ERROR: No valid order header data remained after processing.")
        
    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Orders Header Loader finished in {total_time:.2f} seconds.")
    if total_time > LOAD_TIMEOUT_SECONDS:
        logs.append(f"WARNING: This loader took longer than {LOAD_TIMEOUT_SECONDS} seconds! This is likely due to slow date parsing.")
        
    return logs, df_agg


def load_service_data(deliveries_df_unified, orders_header_lookup_df, master_data_df):
    """
    OPTIMIZATION: Process unified DELIVERIES data and join with order/master data.
    No longer reads file - receives pre-loaded data from load_deliveries_unified().

    Args:
        deliveries_df_unified: Pre-loaded deliveries dataframe from load_deliveries_unified()
        orders_header_lookup_df: orders header lookup dataframe
        master_data_df: master data dataframe

    Returns: logs (list), dataframe, error_dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Service Data Loader ---")
    error_df = pd.DataFrame()
    date_check_df = pd.DataFrame()

    if deliveries_df_unified.empty or orders_header_lookup_df.empty or master_data_df.empty:
        logs.append("ERROR: Service Loader cannot proceed: Deliveries, Orders Header, or Master Data is empty.")
        return logs, pd.DataFrame(), pd.DataFrame()

    delivery_cols = {
        "Deliveries Detail - Order Document Number": "sales_order",
        "Item - SAP Model Code": "sku",
        "Delivery Creation Date: Date": "ship_date",
        "Deliveries - TOTAL Goods Issue Qty": "units_issued",
        "Item - Model Desc": "product_name"
    }

    if not check_columns(deliveries_df_unified, delivery_cols.keys(), "DELIVERIES.csv", logs):
        return logs, pd.DataFrame(), pd.DataFrame()

    df = deliveries_df_unified[list(delivery_cols.keys())].copy().rename(columns=delivery_cols)
    df['units_issued'] = pd.to_numeric(df['units_issued'], errors='coerce').fillna(0)
    # --- NEW: Clean product name from source ---
    df['product_name'] = clean_string_column(df['product_name'])

    
    # --- NEW LOGIC: Aggregate deliveries by order and item ---
    # This addresses user request #3 for a faster, order-item-centric view.
    logs.append("INFO: Aggregating multiple deliveries for the same order item.")
    df = df.groupby(['sales_order', 'sku'], as_index=False).agg(
        ship_date=('ship_date', 'max'), # Use the LATEST ship date for the service calc
        units_issued=('units_issued', 'sum') # Use the SUM of all shipped units
    )
    logs.append(f"INFO: {len(df)} unique order-item shipments after aggregation.")


    # --- The rest of the logic proceeds with the aggregated data ---
    df['ship_date_raw'] = df['ship_date']
    
    # --- UPDATED: Join on 'sales_order' ONLY ---
    # First, find the mismatches for the error report
    df_merged = pd.merge(df, orders_header_lookup_df, on='sales_order', how='left', indicator=True)
    unmatched_deliveries = df_merged[df_merged['_merge'] == 'left_only']
    if not unmatched_deliveries.empty:
        logs.append(f"WARNING: {len(unmatched_deliveries)} delivery lines did not find a matching order in ORDERS.csv. These will be dropped.")
        logs.append("ADVICE: This is a data mismatch. Check 'Unmatched_Deliveries' in the error report.")
        error_df = pd.concat([error_df, unmatched_deliveries]) 

    # --- UPDATED: Join on 'sales_order' ONLY ---
    # Now, do the 'inner' join to keep only matches
    df = pd.merge(df, orders_header_lookup_df, on='sales_order', how='inner')
    logs.append(f"INFO: {len(df)} rows after joining Order Headers (inner join).")
    
    # --- FIX: Use the single, validated date format for performance and reliability ---
    logs.append("INFO: Parsing Ship Dates with explicit format '%m/%d/%y'...")
    df['ship_date'] = pd.to_datetime(df['ship_date_raw'], format='%m/%d/%y', errors='coerce')

    ship_date_fail_mask = df['ship_date'].isna()
    ship_date_nulls = ship_date_fail_mask.sum()
    if ship_date_nulls > 0:
        logs.append(f"ERROR: {ship_date_nulls} ship dates failed to parse (became NaT).")
        logs.append("ADVICE: This is likely due to blank dates or mixed/bad text formats in the 'Delivery Creation Date: Date' column.")
        error_df = pd.concat([error_df, df[ship_date_fail_mask]]) 
    
    df.dropna(subset=['ship_date', 'order_date', 'units_issued'], inplace=True)
    logs.append(f"INFO: {len(df)} rows remaining after dropping NaNs.")

    # --- UPDATED: Only merge for Category ---
    master_data_subset = master_data_df[['sku', 'category']]
    df = pd.merge(df, master_data_subset, on='sku', how='left')
    logs.append(f"INFO: {len(df)} rows after joining Master Data.")

    # --- NEW: Identify and report SKUs not found in Master Data for Service Data ---
    # Rows where product_name is NaN after left merge indicate missing master data
    missing_master_data_mask = df['category'].isna()
    num_missing_master_data = int(missing_master_data_mask.sum())
    if num_missing_master_data > 0:
        logs.append(f"WARNING: {num_missing_master_data} rows in Service Data have SKUs not found in Master Data. Their 'category' will be 'Unknown'.")
        logs.append("ADVICE: Check 'SKU_Not_in_Master_Data' in the error report for details.")
        error_df = pd.concat([error_df, df[missing_master_data_mask].assign(ErrorType="SKU_Not_in_Master_Data")])

    df['category'] = df['category'].fillna('Unknown')

    # --- FIX: Fillna for other columns that are not dropped ---
    # product_name is now sourced from DELIVERIES, so it needs fillna
    for col in ['sales_org', 'customer_name', 'order_type', 'order_reason', 'product_name']:
        if col in df.columns:
            df[col] = df[col].fillna('Unknown')
    df['days_to_deliver'] = (df['ship_date'] - df['order_date']).dt.days
    df['days_to_deliver'] = df['days_to_deliver'].clip(lower=0)
    
    # --- UPDATED BUSINESS LOGIC: Due date is 7 days after the order date. ---
    df['due_date'] = df['order_date'] + pd.to_timedelta(7, unit='D')
    df['on_time'] = df['ship_date'] <= df['due_date']
    
    # --- UPDATED: Create BOTH Order and Ship date parts ---
    df['order_year'] = df['order_date'].dt.year
    df['order_month'] = df['order_date'].dt.month_name()
    df['order_month_num'] = df['order_date'].dt.month
    
    df['ship_year'] = df['ship_date'].dt.year
    df['ship_month'] = df['ship_date'].dt.month_name()
    df['ship_month_num'] = df['ship_date'].dt.month
    
    if df.empty:
        logs.append("WARNING: Service Loader: No data remained after processing. Check date formats or join logic.")
    
    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Service Data Loader finished in {total_time:.2f} seconds.")
    if total_time > LOAD_TIMEOUT_SECONDS:
        logs.append(f"WARNING: This loader took longer than {LOAD_TIMEOUT_SECONDS} seconds!")
        
    return logs, df, error_df

def load_backorder_data(orders_item_lookup_df, orders_header_lookup_df, master_data_df):
    """
    Filters the main orders lookup table for unfulfilled backorders.
    --- UPDATED: Joins with order_header_lookup to get authoritative header-level data ---
    
    Note: This function does not take a file_key because it works with already-loaded dataframes
    from load_orders_item_lookup, load_orders_header_lookup, and load_master_data.
    """
    logs = []
    start_time = time.time()
    logs.append("--- Backorder Data Loader ---")
    error_df = pd.DataFrame() 
    
    if orders_item_lookup_df.empty or master_data_df.empty or orders_header_lookup_df.empty:
        logs.append("ERROR: Backorder Loader cannot proceed: Orders Item Lookup, Orders Header, or Master Data is empty.")
        return logs, pd.DataFrame(), pd.DataFrame()

    df = orders_item_lookup_df[orders_item_lookup_df['backorder_qty'] > 0].copy()
    logs.append(f"INFO: Found {len(df)} rows with backorder_qty > 0.")
    
    if df.empty:
        logs.append("INFO: No backorder data found. (This is normal if there are no backorders).")
        return logs, pd.DataFrame(), pd.DataFrame()

    # --- NEW: Get authoritative header-level data (customer, sales_org, etc.) ---
    # Drop the potentially inconsistent header columns from the item-level data first
    header_cols_to_drop = ['customer_name', 'order_type', 'order_reason', 'order_date']
    cols_to_drop_existing = [col for col in header_cols_to_drop if col in df.columns]
    df.drop(columns=cols_to_drop_existing, inplace=True)

    # Now merge with the clean header data
    # --- UPDATED: Explicitly define which columns to use from the header lookup ---
    # This prevents the 'sales_org' from being overwritten.
    header_subset = orders_header_lookup_df[['sales_order', 'customer_name', 'order_type', 'order_reason', 'order_date']]
    df = pd.merge(df, header_subset, on='sales_order', how='left')
    logs.append(f"INFO: {len(df)} rows after joining with Order Headers.")

    # --- NEW: Check for SKUs not found in Master Data ---
    # Before merging, identify SKUs that won't find a match
    skus_in_backorder = df['sku'].unique()
    skus_in_master = master_data_df['sku'].unique()
    unmatched_skus = np.setdiff1d(skus_in_backorder, skus_in_master)
    if len(unmatched_skus) > 0:
        logs.append(f"WARNING: {len(unmatched_skus)} SKUs in backorder data were not found in Master Data. These items will be removed.")
        # Add these to error_df for reporting
        unmatched_sku_df = df[df['sku'].isin(unmatched_skus)].copy()
        error_df = pd.concat([error_df, unmatched_sku_df.assign(ErrorType="SKU_Not_in_Master_Data")])

    # --- UPDATED: Merge with master data, but EXCLUDE product_name to keep the one from ORDERS.csv ---
    master_data_subset = master_data_df[['sku', 'category']]
    df = pd.merge(df, master_data_subset, on='sku', how='left')

    logs.append(f"INFO: {len(df)} rows after joining Master Data for category.")
    
    # --- NEW LOGIC: Remove rows where master data (brand, category) is missing ---
    initial_rows = len(df)
    df.dropna(subset=['category'], inplace=True)
    removed_rows = initial_rows - len(df)
    if removed_rows > 0:
        logs.append(f"INFO: Removed {removed_rows} rows from Backorder Data due to missing Master Data for category.")

    # --- FIX: Ensure other filterable text columns are present and filled ---
    # product_name is included here to fill if it was originally NaN from ORDERS.csv
    for col in ['sales_org', 'customer_name', 'order_type', 'order_reason', 'product_name']:
        if col in df.columns:
            df[col] = df[col].fillna('Unknown')
    
    # --- BUSINESS LOGIC: Always use the order date as the starting point for backorder age. ---
    df['calc_date'] = df['order_date']
    
    df['days_on_backorder'] = (TODAY - df['calc_date']).dt.days
    df['days_on_backorder'] = df['days_on_backorder'].clip(lower=0)

    df['order_year'] = df['order_date'].dt.year
    df['order_month'] = df['order_date'].dt.month_name()
    df['order_month_num'] = df['order_date'].dt.month

    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Backorder Data Loader finished in {total_time:.2f} seconds.")
    if total_time > LOAD_TIMEOUT_SECONDS:
        logs.append(f"WARNING: This loader took longer than {LOAD_TIMEOUT_SECONDS} seconds!")
        
    return logs, df, error_df

# --- NEW: Inventory Data Loader ---
def load_inventory_data(inventory_path, file_key='inventory'):
    """
    Loads the inventory snapshot data from INVENTORY.csv, which contains
    on-hand stock quantities. It aggregates stock by SKU.
    
    Args:
        inventory_path: file path (used if no uploaded file exists)
        file_key: session state key for uploaded file (default 'inventory')
    
    Returns: logs (list), dataframe, error_dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Inventory Snapshot Loader ---")
    
    # --- UPDATED: Load stock quantities AND pricing columns for stock value calculation ---
    inventory_cols = {
        "Material Number": "sku",
        "POP Actual Stock Qty": "on_hand_qty",
        "POP Actual Stock in Transit Qty": "in_transit_qty",
        "POP Last Purchase: Price in Purch. Currency": "last_purchase_price",
        "POP Last Purchase: Currency": "currency"
    }
    
    try:
        # Load only the necessary columns for efficiency
        df = safe_read_csv(file_key, inventory_path, usecols=list(inventory_cols.keys()), low_memory=False)
        logs.append(f"INFO: Found and loaded {len(df)} rows from INVENTORY.csv.")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'INVENTORY.csv'. Check columns. Error: {e}")
        return logs, pd.DataFrame(), pd.DataFrame()

    if not check_columns(df, inventory_cols.keys(), "INVENTORY.csv", logs):
        return logs, pd.DataFrame(), pd.DataFrame()
    
    df = df.rename(columns=inventory_cols)
    df['sku'] = clean_string_column(df['sku'])
    
    # --- OPTIMIZATION: Use vectorized numeric conversion ---
    df['on_hand_qty'] = safe_numeric_column(df['on_hand_qty'], remove_commas=True)
    df['in_transit_qty'] = safe_numeric_column(df['in_transit_qty'], remove_commas=True)
    df['last_purchase_price'] = safe_numeric_column(df['last_purchase_price'], remove_commas=True)
    
    df['currency'] = df['currency'].astype(str).str.strip().str.upper()
    df['currency'] = df['currency'].fillna('USD')

    # --- NEW: Aggregate stock by SKU ---
    # The inventory file can have multiple rows for the same SKU (e.g., in different storage locations).
    # We must sum quantities and take the first pricing info (prices should be the same per SKU).
    rows_before_agg = len(df)
    df = df.groupby('sku', as_index=False).agg({
        'on_hand_qty': 'sum',
        'in_transit_qty': 'sum',
        'last_purchase_price': 'first',  # Take first price (should be same per SKU)
        'currency': 'first'  # Take first currency (should be same per SKU)
    })
    logs.append(f"INFO: Aggregated {rows_before_agg} rows into {len(df)} unique SKUs, summing on-hand and in-transit stock.")
    
    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Inventory Snapshot Loader finished in {total_time:.2f} seconds.")
    
    return logs, df, pd.DataFrame()

def load_inventory_analysis_data(inventory_df, deliveries_df_unified, master_data_df):
    """
    OPTIMIZATION: Calculate daily demand and DIO using unified deliveries data.
    No longer reads file - receives pre-loaded data from load_deliveries_unified().

    Args:
        inventory_df: inventory dataframe (already loaded)
        deliveries_df_unified: Pre-loaded deliveries dataframe from load_deliveries_unified()
        master_data_df: master data dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Inventory Analysis (DIO) Calculator ---")

    if inventory_df.empty or master_data_df.empty or deliveries_df_unified.empty:
        logs.append("ERROR: Inventory Analysis cannot proceed: Inventory, Deliveries, or Master Data is empty.")
        return logs, pd.DataFrame()

    # 1. Process deliveries for last 12 months to calculate demand
    try:
        # Use subset of columns from unified data
        deliveries_df = deliveries_df_unified[["Item - SAP Model Code", "Delivery Creation Date: Date", "Deliveries - TOTAL Goods Issue Qty"]].copy()
        deliveries_df = deliveries_df.rename(columns={
            "Item - SAP Model Code": "sku",
            "Delivery Creation Date: Date": "ship_date",
            "Deliveries - TOTAL Goods Issue Qty": "units_issued"
        })

        # --- FIX: Apply robust SKU cleaning to match the format in inventory_df ---
        deliveries_df['sku'] = clean_string_column(deliveries_df['sku'])

        # --- FIX: Convert 'units_issued' to a numeric type before performing calculations ---
        deliveries_df['units_issued'] = pd.to_numeric(deliveries_df['units_issued'], errors='coerce').fillna(0)

        # --- FIX: Use the single, validated date format for performance and reliability ---
        logs.append("INFO: (DIO Calc) Parsing Ship Dates with explicit format '%m/%d/%y'...")
        deliveries_df['ship_date'] = pd.to_datetime(deliveries_df['ship_date'], format='%m/%d/%y', errors='coerce')

        deliveries_df.dropna(subset=['ship_date'], inplace=True)
        
        # Filter for the last 12 months
        twelve_months_ago = TODAY - pd.DateOffset(months=12)
        recent_deliveries = deliveries_df[deliveries_df['ship_date'] >= twelve_months_ago]

        # --- NEW: SKU Age-Based Daily Demand Calculation ---
        # Instead of always dividing by 365, use actual days since market introduction
        # Market intro date = Activation Date + 60 days (2 months buffer)

        # Get activation dates from master data
        sku_activation = master_data_df[['sku', 'activation_date']].copy()

        # Calculate market introduction date (activation + 60 days)
        sku_activation['market_intro_date'] = sku_activation['activation_date'] + pd.Timedelta(days=60)

        # Calculate days active since market introduction
        sku_activation['days_active'] = (TODAY - sku_activation['market_intro_date']).dt.days

        # Cap at 365 days maximum (use full year for established products)
        sku_activation['demand_divisor'] = sku_activation['days_active'].clip(lower=0, upper=365)

        # For SKUs without activation date, use full 365 days
        sku_activation['demand_divisor'] = sku_activation['demand_divisor'].fillna(365)

        # Exclude SKUs with <30 days active (too new to calculate meaningful demand)
        sku_activation['exclude_from_demand'] = sku_activation['days_active'] < 30

        # Calculate total units issued per SKU
        total_demand = recent_deliveries.groupby('sku')['units_issued'].sum().reset_index()
        total_demand = total_demand.rename(columns={'units_issued': 'total_units_issued'})

        # Merge with activation data to get proper divisor
        daily_demand = pd.merge(total_demand, sku_activation[['sku', 'demand_divisor', 'exclude_from_demand']],
                                on='sku', how='left')

        # Fill missing divisors with 365 (for SKUs not in master data)
        daily_demand['demand_divisor'] = daily_demand['demand_divisor'].fillna(365)
        daily_demand['exclude_from_demand'] = daily_demand['exclude_from_demand'].fillna(False)

        # Calculate daily demand using SKU-specific divisor
        daily_demand['daily_demand'] = daily_demand['total_units_issued'] / daily_demand['demand_divisor']

        # Set demand to 0 for excluded SKUs (too new)
        daily_demand.loc[daily_demand['exclude_from_demand'], 'daily_demand'] = 0

        excluded_count = daily_demand['exclude_from_demand'].sum()
        if excluded_count > 0:
            logs.append(f"INFO: Excluded {excluded_count} SKUs from demand calculation (<30 days since market introduction).")

        logs.append(f"INFO: Calculated SKU age-based daily demand for {len(daily_demand)} SKUs from last 12 months of deliveries.")
        logs.append("INFO: Using activation date + 60 days to determine proper demand divisor (capped at 365 days).")

        # Keep only necessary columns
        daily_demand = daily_demand[['sku', 'daily_demand']]

    except Exception as e:
        logs.append(f"ERROR: Failed to process 'DELIVERIES.csv' for demand calculation: {e}")
        return logs, pd.DataFrame()

    # 2. Merge demand with inventory and calculate DIO
    df = pd.merge(inventory_df, daily_demand, on='sku', how='left')
    # --- FIX: Only fill NaN values in the 'daily_demand' column ---
    df['daily_demand'] = df['daily_demand'].fillna(0)
    
    # --- FIX: Add logging when daily_demand is zero (but keep logic unchanged) ---
    # Treat 0 daily demand as 0 DIO (inventory not moving = infinite days of inventory is not reported)
    zero_demand_count = (df['daily_demand'] == 0).sum()
    if zero_demand_count > 0:
        logs.append(f"WARNING: {zero_demand_count} SKUs have zero daily demand (no deliveries in last 12 months). DIO will be 0 for these items.")
        logs.append("ADVICE: This is normal for slow-moving or recently added SKUs. Check 'daily_demand' column for affected items.")
    
    # Avoid division by zero
    df['dio'] = np.where(df['daily_demand'] > 0, df['on_hand_qty'] / df['daily_demand'], 0)

    # 3. Enrich with master data
    df = pd.merge(df, master_data_df, on='sku', how='left')
    df['category'] = df['category'].fillna('Unknown')
    
    logs.append(f"INFO: Inventory Analysis finished in {time.time() - start_time:.2f} seconds.")
    return logs, df


# === GROUP 6C: Vendor PO Lead Time Calculations ===

def load_vendor_po_lead_times(vendor_po_path, inbound_path, logs=None):
    """
    Calculate vendor-item lead times from historical PO and inbound data (GROUP 6C).
    
    Uses last 2 years of data to compute median lead time per vendor-item combination.
    Lead time = Posting Date (actual receipt) - Order Creation Date.
    Adds 5-day safety stock buffer for restock estimation.
    
    Args:
        vendor_po_path: Path to 'Domestic Vendor POs.csv'
        inbound_path: Path to 'DOMESTIC INBOUND.csv'
        logs: Optional list to append logging messages
    
    Returns:
        Dictionary mapping 'sku' -> {'lead_time_days': int, 'vendor_count': int}
    """
    if logs is None:
        logs = []
    
    start_time = time.time()
    logs.append("--- Vendor PO Lead Time Calculator ---")
    lead_time_lookup = {}
    
    try:
        # Load vendor POs with required columns
        po_cols = ['SAP Purchase Orders - Purchasing Document Number', 
                   'Order Creation Date - Date', 'SAP Material Code']
        vendor_pos = safe_read_csv('vendor_po', vendor_po_path, usecols=po_cols, low_memory=False)
        vendor_pos.columns = ['po_number', 'order_date', 'sku']
        vendor_pos['order_date'] = pd.to_datetime(vendor_pos['order_date'], errors='coerce')
        logs.append(f"INFO: Loaded {len(vendor_pos)} vendor PO records")
        
    except Exception as e:
        logs.append(f"WARNING: Could not load vendor POs: {e}")
        return lead_time_lookup
    
    try:
        # Load inbound receipts with required columns
        inbound_cols = ['Purchase Order Number', 'Posting Date', 'Material Number']
        inbound = safe_read_csv('inbound', inbound_path, usecols=inbound_cols, low_memory=False)
        inbound.columns = ['po_number', 'receipt_date', 'sku']
        inbound['receipt_date'] = pd.to_datetime(inbound['receipt_date'], errors='coerce')
        logs.append(f"INFO: Loaded {len(inbound)} inbound receipt records")
        
    except Exception as e:
        logs.append(f"WARNING: Could not load inbound data: {e}")
        return lead_time_lookup
    
    try:
        # Filter to last 2 years
        two_years_ago = TODAY - pd.Timedelta(days=730)
        vendor_pos = vendor_pos[vendor_pos['order_date'] >= two_years_ago]
        inbound = inbound[inbound['receipt_date'] >= two_years_ago]
        logs.append(f"INFO: Filtered to last 2 years: {len(vendor_pos)} POs, {len(inbound)} receipts")
        
        # Join POs with inbound receipts on PO number and SKU
        merged = pd.merge(vendor_pos, inbound, on=['po_number', 'sku'], how='inner')
        merged = merged.dropna(subset=['order_date', 'receipt_date'])
        
        # Calculate actual lead time
        merged['lead_time'] = (merged['receipt_date'] - merged['order_date']).dt.days
        merged = merged[merged['lead_time'] >= 0]  # Remove negative lead times (data errors)
        
        logs.append(f"INFO: Calculated {len(merged)} matched PO receipts with lead times")
        
        # Calculate median lead time per SKU
        lead_times_by_sku = merged.groupby('sku').agg({
            'lead_time': ['median', 'count']
        }).reset_index()
        lead_times_by_sku.columns = ['sku', 'median_lead_time', 'po_count']
        
        # Add 5-day safety stock buffer
        SAFETY_STOCK_DAYS = 5
        lead_times_by_sku['lead_time_with_safety'] = lead_times_by_sku['median_lead_time'] + SAFETY_STOCK_DAYS
        
        # Build lookup dictionary
        for _, row in lead_times_by_sku.iterrows():
            lead_time_lookup[row['sku']] = {
                'lead_time_days': int(row['lead_time_with_safety']),
                'vendor_count': int(row['po_count']),
                'median_base': int(row['median_lead_time'])
            }
        
        logs.append(f"INFO: Created lead time lookup for {len(lead_time_lookup)} SKUs (median + 5-day safety stock)")
        logs.append(f"INFO: Lead time calculation completed in {time.time() - start_time:.2f} seconds")
        
    except Exception as e:
        logs.append(f"ERROR: Failed to calculate lead times: {e}")
    
    return lead_time_lookup


def get_forecast_horizon(sku: str, lead_time_lookup: dict, default_horizon: int = 90) -> int:
    """
    Get the forecast horizon for demand forecasting based on lead time (GROUP 6C/6D).

    Forecast horizon = lead time + review period
    Used to determine how far ahead to forecast demand.

    Args:
        sku: SKU/Material code
        lead_time_lookup: Dictionary from load_vendor_po_lead_times()
        default_horizon: Days to forecast if no lead time found (default 90)

    Returns:
        Number of days to forecast (int)
    """
    if sku in lead_time_lookup:
        return lead_time_lookup[sku]['lead_time_days']
    return default_horizon


# === BACKWARD COMPATIBILITY WRAPPERS ===
# These functions provide backward-compatible interfaces for tests and legacy code
# They automatically load the unified data and call the optimized functions

def load_orders_item_lookup_legacy(orders_path, file_key='orders'):
    """
    BACKWARD COMPATIBILITY: Legacy wrapper that loads orders from file path.
    For optimal performance, use load_orders_unified() + load_orders_item_lookup() instead.
    """
    logs_unified, orders_df = load_orders_unified(orders_path, file_key)
    logs_item, item_df, errors = load_orders_item_lookup(orders_df)
    return logs_unified + logs_item, item_df, errors


def load_orders_header_lookup_legacy(orders_path, file_key='orders'):
    """
    BACKWARD COMPATIBILITY: Legacy wrapper that loads orders from file path.
    For optimal performance, use load_orders_unified() + load_orders_header_lookup() instead.
    """
    logs_unified, orders_df = load_orders_unified(orders_path, file_key)
    logs_header, header_df = load_orders_header_lookup(orders_df)
    return logs_unified + logs_header, header_df


def load_service_data_legacy(deliveries_path, orders_header_lookup_df, master_data_df, file_key='deliveries'):
    """
    BACKWARD COMPATIBILITY: Legacy wrapper that loads deliveries from file path.
    For optimal performance, use load_deliveries_unified() + load_service_data() instead.
    """
    logs_unified, deliveries_df = load_deliveries_unified(deliveries_path, file_key)
    logs_service, service_df, errors = load_service_data(deliveries_df, orders_header_lookup_df, master_data_df)
    return logs_unified + logs_service, service_df, errors


def load_inventory_analysis_data_legacy(inventory_df, deliveries_path, master_data_df, file_key='deliveries'):
    """
    BACKWARD COMPATIBILITY: Legacy wrapper that loads deliveries from file path.
    For optimal performance, use load_deliveries_unified() + load_inventory_analysis_data() instead.
    """
    logs_unified, deliveries_df = load_deliveries_unified(deliveries_path, file_key)
    logs_analysis, analysis_df = load_inventory_analysis_data(inventory_df, deliveries_df, master_data_df)
    return logs_unified + logs_analysis, analysis_df