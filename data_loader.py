import pandas as pd
from datetime import datetime
import numpy as np
import warnings
import time # <-- Import time for performance tracking
import streamlit as st
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
        # time-of-day fields (Eastern Time) — optional
        "Deliveries Dates - Delivery Creation Time",
        "Deliveries Dates - Goods Issue Time",
        "Goods Issue Date: Date",  # NEW field - prefer goods issue if present
        "Delivery Creation Date: Date",
        "Deliveries - TOTAL Goods Issue Qty",
        "Item - Model Desc"
    ]

    try:
        # Attempt to read only the required columns first (fast-path). Some files may not include the optional
        # 'Goods Issue Date: Date' field, so if usecols fails, fall back to reading the full file and selecting
        # the available columns.
        try:
            df = safe_read_csv(file_key, deliveries_path, usecols=all_delivery_cols, low_memory=False)
            logs.append(f"INFO: Loaded {len(df)} rows from DELIVERIES.csv (unified read - selected cols).")
        except Exception:
            logs.append("WARN: Could not read deliveries with strict usecols — falling back to permissive read.")
            df = safe_read_csv(file_key, deliveries_path, low_memory=False)
            # Only keep columns we care about (if present)
            df = df[[c for c in all_delivery_cols if c in df.columns]]
            logs.append(f"INFO: Loaded {len(df)} rows from DELIVERIES.csv (unified read - fallback).")
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
        # --- UPDATED: Load SKU, Category, Activation Date, and PLM fields ---
        cols_to_load = [
            "Material Number",
            "PLM: Level Classification 4",
            "Activation Date (Code)",
            "PLM: PLM Current Status",
            "PLM: Expiration Date"
        ]
        df = safe_read_csv(file_key, master_data_path, usecols=cols_to_load, low_memory=False)
        logs.append(f"INFO: Found and loaded {len(df)} rows from Master Data.")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'Master Data.csv': {e}")
        return logs, pd.DataFrame(), pd.DataFrame()

    # --- UPDATED: Load SKU, Category, Activation Date, and PLM fields ---
    master_cols = {
        "Material Number": "sku",
        "PLM: Level Classification 4": "category",
        "Activation Date (Code)": "activation_date",
        "PLM: PLM Current Status": "plm_status",
        "PLM: Expiration Date": "plm_expiration_date"
    }
    if not check_columns(df, master_cols.keys(), "Master Data.csv", logs):
        return logs, pd.DataFrame(), pd.DataFrame()

    duplicates = df[df.duplicated(subset=['Material Number'], keep=False)]
    if not duplicates.empty:
        logs.append(f"WARNING: Found {len(duplicates)} duplicated SKUs in Master Data. Keeping first instance.")
        error_df = pd.concat([error_df, duplicates])

    df = df[list(master_cols.keys())].rename(columns=master_cols)

    str_cols = ['sku', 'category', 'plm_status']
    for col in str_cols:
        df[col] = clean_string_column(df[col])

    # --- NEW: Parse activation date ---
    logs.append("INFO: Parsing SKU Activation Dates with explicit format '%m/%d/%y'...")
    df['activation_date'] = pd.to_datetime(df['activation_date'], format='%m/%d/%y', errors='coerce')
    activation_date_nulls = df['activation_date'].isna().sum()
    if activation_date_nulls > 0:
        logs.append(f"WARNING: {activation_date_nulls} SKUs have missing/invalid activation dates. These will use full 365-day divisor for demand calculation.")

    # --- NEW: Parse PLM expiration date ---
    logs.append("INFO: Parsing PLM Expiration Dates...")
    df['plm_expiration_date'] = pd.to_datetime(df['plm_expiration_date'], format='%Y%m%d', errors='coerce')
    plm_exp_nulls = df['plm_expiration_date'].isna().sum()
    if plm_exp_nulls > 0:
        logs.append(f"INFO: {plm_exp_nulls} SKUs have missing/invalid PLM expiration dates.")

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
    # .str.replace(r'\\s+', ' ', regex=True) replaces multiple internal spaces with a single space.
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

    # OPTIMIZATION #3: Convert categorical columns to category dtype for memory savings
    categorical_cols = ['sales_org', 'customer_name', 'product_name', 'reject_reason', 'order_type', 'order_reason']
    for col in categorical_cols:
        if col in df_agg.columns:
            df_agg[col] = df_agg[col].astype('category')
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
    
    # OPTIMIZATION #3: Convert categorical columns to category dtype for memory savings
    categorical_cols = ['customer_name', 'order_type', 'order_reason', 'sales_org']
    for col in categorical_cols:
        if col in df_agg.columns:
            df_agg[col] = df_agg[col].astype('category')
    
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

    # Support both 'Goods Issue Date: Date' (prefer) and 'Delivery Creation Date: Date' (fallback)
    # Keep both raw columns so we can compute separate KPIs (Planning OTIF vs Logistics OTIF).
    # Define required and optional delivery columns
    required_cols = [
        "Deliveries Detail - Order Document Number",
        "Item - SAP Model Code",
        "Delivery Creation Date: Date",
        "Deliveries - TOTAL Goods Issue Qty",
        "Item - Model Desc"
    ]

    optional_cols = ["Goods Issue Date: Date"]

    # Validate that required columns exist
    if not check_columns(deliveries_df_unified, required_cols, "DELIVERIES.csv", logs):
        return logs, pd.DataFrame(), pd.DataFrame()

    # Build a mapping for any of the columns we actually have
    delivery_cols = {
        "Deliveries Detail - Order Document Number": "sales_order",
        "Item - SAP Model Code": "sku",
        "Delivery Creation Date: Date": "delivery_creation_date_raw",
        "Deliveries - TOTAL Goods Issue Qty": "units_issued",
        "Item - Model Desc": "product_name"
    }
    # include optional goods issue column and optional time columns if present
    if 'Goods Issue Date: Date' in deliveries_df_unified.columns:
        delivery_cols['Goods Issue Date: Date'] = 'goods_issue_date_raw'
    if 'Deliveries Dates - Goods Issue Time' in deliveries_df_unified.columns:
        delivery_cols['Deliveries Dates - Goods Issue Time'] = 'goods_issue_time_raw'
    if 'Deliveries Dates - Delivery Creation Time' in deliveries_df_unified.columns:
        delivery_cols['Deliveries Dates - Delivery Creation Time'] = 'delivery_creation_time_raw'

    # Only select the columns that actually exist in the loaded dataframe
    select_cols = [c for c in delivery_cols.keys() if c in deliveries_df_unified.columns]
    df = deliveries_df_unified[select_cols].copy().rename(columns=delivery_cols)

    # --- FIX: Clean SKU column to ensure consistent string type for joins ---
    df['sku'] = clean_string_column(df['sku'])

    df['units_issued'] = pd.to_numeric(df['units_issued'], errors='coerce').fillna(0)
    # --- NEW: Clean product name from source ---
    df['product_name'] = clean_string_column(df['product_name'])

    
    # --- UPDATED: Parse any available date columns early so ship_date exists for aggregation ---
    # Parse goods_issue_date_raw and delivery_creation_date_raw if present
    # --- Parse date + optional time and localize to US/Eastern if present ---
    # Use combined parsing when both date and time exist, otherwise fall back to date-only.
    tz = 'US/Eastern'

    # Helper function to parse combined date+time into tz-aware datetime
    def parse_date_and_time(date_series, time_series=None):
        # result series
        res = pd.Series(index=date_series.index, dtype='datetime64[ns]')

        if time_series is not None and time_series.name in df.columns:
            # parse when both date and time available
            mask = date_series.notna() & time_series.notna()
            combined = date_series.loc[mask].astype(str).str.strip() + ' ' + time_series.loc[mask].astype(str).str.strip()
            # Parse combined date+time into a naive datetime (local time). Avoid tz-localization here
            # to keep arithmetic compatible with other naive date columns.
            parsed = pd.to_datetime(combined, format='%m/%d/%y %H:%M:%S', errors='coerce')
            res.loc[mask] = parsed

        # Convert obvious sentinel markers into NaT BEFORE parsing
        # Business rule: some sources use '1/1/2000' to mean "no date / placeholder" — treat as null
        try:
            # Treat string sentinel forms as nulls
            str_series = date_series.astype(str).str.strip()
            sentinel_mask = str_series.isin(['1/1/2000', '01/01/2000', '2000-01-01'])
            # Also treat actual datetime values equal to 2000-01-01 as sentinel
            if pd.api.types.is_datetime64_any_dtype(date_series) or pd.api.types.is_datetime64tz_dtype(date_series):
                sentinel_mask = sentinel_mask | ((date_series.dt.year == 2000) & (date_series.dt.month == 1) & (date_series.dt.day == 1))
            # Set sentinel entries to NaN so parse step will leave them as NaT
            if sentinel_mask.any():
                date_series = date_series.astype(object).where(~sentinel_mask, pd.NA)
        except Exception:
            # Be defensive - if anything goes wrong keep original series
            pass

        # fall back to date-only parsing for remaining rows
        remaining = res.isna() & date_series.notna()
        if remaining.any():
            parsed_dates = pd.to_datetime(date_series.loc[remaining], format='%m/%d/%y', errors='coerce')
            res.loc[remaining] = parsed_dates

        # convert dtype to datetime64[ns]
        if not pd.api.types.is_datetime64_any_dtype(res):
            res = pd.to_datetime(res)
        return res

    df['goods_issue_date'] = parse_date_and_time(df.get('goods_issue_date_raw', pd.Series(pd.NaT)), df.get('goods_issue_time_raw'))
    # Treat sentinel date 1/1/2000 as a null goods issue date (meaning goods issue hasn't occurred)
    try:
        sentinel = pd.Timestamp(year=2000, month=1, day=1)
        # Mark rows that came from sentinel (preserve info) then null them out
        df['goods_issue_was_sentinel'] = False
        # If parsed equals sentinel OR raw text explicitly contains 2000 (e.g. '1/1/2000'), treat as sentinel
        raw_series = df.get('goods_issue_date_raw', pd.Series(dtype=str))
        # Regex: allow 1/1/2000, 01/01/2000, 1/1/00, 01/01/00
        raw_sentinel_mask = raw_series.fillna('').astype(str).str.strip().str.match(r'^(0?1)/(0?1)/(2000|00)$')
        parsed_sentinel_mask = df['goods_issue_date'].notna() & (df['goods_issue_date'].dt.normalize() == sentinel)
        mask_sentinel = raw_sentinel_mask | parsed_sentinel_mask
        if mask_sentinel.any():
            df.loc[mask_sentinel, 'goods_issue_was_sentinel'] = True
            df.loc[mask_sentinel, 'goods_issue_date'] = pd.NaT
    except Exception:
        # If anything goes wrong, don't break the loader
        df['goods_issue_was_sentinel'] = False
    df['delivery_creation_date'] = parse_date_and_time(df.get('delivery_creation_date_raw', pd.Series(pd.NaT)), df.get('delivery_creation_time_raw'))

    # Determine primary ship_date (prefer goods_issue, otherwise delivery_creation)
    df['ship_date'] = df['goods_issue_date'].fillna(df['delivery_creation_date'])

    # --- NEW LOGIC: Aggregate deliveries by order and item ---
    # This addresses user request #3 for a faster, order-item-centric view.
    logs.append("INFO: Aggregating multiple deliveries for the same order item.")
    df = df.groupby(['sales_order', 'sku'], as_index=False).agg(
        ship_date=('ship_date', 'max'), # Use the LATEST ship date for the service calc
        units_issued=('units_issued', 'sum'), # Use the SUM of all shipped units
        goods_issue_date=('goods_issue_date', 'max'),
        delivery_creation_date=('delivery_creation_date', 'max')
    )
    logs.append(f"INFO: {len(df)} unique order-item shipments after aggregation.")


    # --- The rest of the logic proceeds with the aggregated data ---
    # After aggregation we should already have parsed goods_issue_date and delivery_creation_date
    
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
    # At this point goods_issue_date and delivery_creation_date were parsed prior to aggregation
    # and preserved by taking the latest dates per order-item. ship_date already exists from aggregation.

    ship_date_fail_mask = df['ship_date'].isna()
    ship_date_nulls = ship_date_fail_mask.sum()
    if ship_date_nulls > 0:
        logs.append(f"ERROR: {ship_date_nulls} ship dates failed to parse (became NaT).")
        logs.append("ADVICE: This is likely due to blank dates or mixed/bad text formats in the Goods Issue Date or Delivery Creation Date columns.")
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
            # If column is already categorical, ensure 'Unknown' is a valid category
            if pd.api.types.is_categorical_dtype(df[col]):
                df[col] = df[col].cat.add_categories(['Unknown']).fillna('Unknown')
            else:
                df[col] = df[col].fillna('Unknown')
    df['days_to_deliver'] = (df['ship_date'] - df['order_date']).dt.days
    df['days_to_deliver'] = df['days_to_deliver'].clip(lower=0)
    
    # --- UPDATED BUSINESS LOGIC: Due date is 7 days after the order date (Planning OTIF). ---
    df['due_date'] = df['order_date'] + pd.to_timedelta(7, unit='D')
    # PLANNING OTIF: Shipment (goods_issue or ship_date fallback) within 7 days of order creation
    df['planning_on_time'] = df['ship_date'] <= df['due_date']

    # If goods_issue_date was the sentinel (means goods haven't been issued yet),
    # treat the sentinel as missing and evaluate lateness using today's date as the decision point.
    # If today is greater than due_date (order_date + 7 days) we mark planning as late (False)
    if 'goods_issue_was_sentinel' in df.columns:
        sentinel_planning_mask = df['goods_issue_was_sentinel'] & (df['due_date'] < TODAY)
        if sentinel_planning_mask.any():
            df.loc[sentinel_planning_mask, 'planning_on_time'] = False
            df.loc[sentinel_planning_mask, 'planning_late_due_to_missing_goods_issue'] = True
        else:
            df['planning_late_due_to_missing_goods_issue'] = False

    # LOGISTICS OTIF: Goods must be issued within 3 days of delivery creation
    # (requires both dates - if missing, mark False). If goods_issue_date was the sentinel
    # that means it's missing; in that case we treat it as not on time and consider it late
    # if TODAY is greater than delivery_creation_date + 3 days.
    df['delivery_plus_3'] = df['delivery_creation_date'] + pd.to_timedelta(3, unit='D')
    df['logistics_on_time'] = False
    valid_logistics_mask = df['goods_issue_date'].notna() & df['delivery_plus_3'].notna()
    df.loc[valid_logistics_mask, 'logistics_on_time'] = (
        df.loc[valid_logistics_mask, 'goods_issue_date'] <= df.loc[valid_logistics_mask, 'delivery_plus_3']
    )
    # For rows where goods_issue date was sentinel (missing), check if it's late vs delivery creation
    if 'goods_issue_was_sentinel' in df.columns:
        sentinel_logistics_mask = df['goods_issue_was_sentinel'] & df['delivery_plus_3'].notna()
        if sentinel_logistics_mask.any():
            # mark logistics as False (not on time) and separate flag for lateness
            df.loc[sentinel_logistics_mask, 'logistics_on_time'] = False
            df.loc[sentinel_logistics_mask, 'logistics_late_due_to_missing_goods_issue'] = (df.loc[sentinel_logistics_mask, 'delivery_plus_3'] < TODAY)
        else:
            df['logistics_late_due_to_missing_goods_issue'] = False

    # Backwards compatibility: keep 'on_time' column representing Planning OTIF
    df['on_time'] = df['planning_on_time']
    
    # --- UPDATED: Create BOTH Order and Ship date parts ---
    df['order_year'] = df['order_date'].dt.year
    df['order_month'] = df['order_date'].dt.month_name()
    df['order_month_num'] = df['order_date'].dt.month

    # OPTIMIZATION: Convert categorical text columns to category dtype for memory savings
    categorical_cols = ['sales_org', 'customer_name', 'order_type', 'order_reason', 'product_name', 'category', 'order_month']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')
    
    df['ship_year'] = df['ship_date'].dt.year
    df['ship_month'] = df['ship_date'].dt.month_name()
    df['ship_month_num'] = df['ship_date'].dt.month
    
    # OPTIMIZATION: Convert several text columns to categorical dtype to reduce memory
    categorical_cols = ['sales_org', 'customer_name', 'order_type', 'order_reason', 'product_name', 'category', 'order_month', 'ship_month']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')
    
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
            if pd.api.types.is_categorical_dtype(df[col]):
                df[col] = df[col].cat.add_categories(['Unknown']).fillna('Unknown')
            else:
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

    IMPORTANT: Filters to the MOST RECENT snapshot only using the
    'Snapshot YearWeek: Trade Marketing Yearmonth' column.
    The 'Current Date' column is the data freshness date, NOT the snapshot date.

    Args:
        inventory_path: file path (used if no uploaded file exists)
        file_key: session state key for uploaded file (default 'inventory')

    Returns: logs (list), dataframe, error_dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Inventory Snapshot Loader ---")

    # --- UPDATED: Load stock quantities, pricing columns, snapshot dates, AND descriptive fields ---
    inventory_cols = {
        "Material Number": "sku",
        "POP Actual Stock Qty": "on_hand_qty",
        "POP Actual Stock in Transit Qty": "in_transit_qty",
        "POP Last Purchase: Price in Purch. Currency": "last_purchase_price",
        "POP Last Purchase: Currency": "currency",
        "Storage Location: Code": "storage_location",
        "Material Description": "product_name",
        "Brand": "brand",
        "POP Last Purchase: Date": "last_inbound_date",
        # Snapshot date fields - used to filter to most recent snapshot
        "Snapshot YearWeek: Trade Marketing Year": "snapshot_year",
        "Snapshot YearWeek: Trade Marketing Yearmonth": "snapshot_yearmonth",
        "Snapshot YearWeek:Trade Marketing Week of the Year": "snapshot_week"
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

    # --- FILTER TO MOST RECENT SNAPSHOT ---
    # The snapshot_yearmonth field (e.g., "2024-11") determines when the inventory was captured
    # We only want the most recent snapshot to avoid double-counting inventory
    if 'snapshot_yearmonth' in df.columns:
        # Get unique snapshot periods and find the most recent
        df['snapshot_yearmonth'] = df['snapshot_yearmonth'].astype(str).str.strip()
        unique_snapshots = df['snapshot_yearmonth'].dropna().unique()
        if len(unique_snapshots) > 0:
            # Sort snapshots (they should be in YYYY-MM format or similar sortable format)
            sorted_snapshots = sorted([s for s in unique_snapshots if s and s != 'nan'], reverse=True)
            if sorted_snapshots:
                most_recent_snapshot = sorted_snapshots[0]
                rows_before = len(df)
                df = df[df['snapshot_yearmonth'] == most_recent_snapshot]
                logs.append(f"INFO: Filtered to most recent inventory snapshot: {most_recent_snapshot}")
                logs.append(f"INFO: Retained {len(df)} rows from {rows_before} total (excluded {rows_before - len(df)} rows from older snapshots)")
            else:
                logs.append("WARN: No valid snapshot_yearmonth values found, using all data.")
        else:
            logs.append("WARN: snapshot_yearmonth column is empty, using all data.")
    else:
        logs.append("WARN: snapshot_yearmonth column not found, using all data.")

    # --- OPTIMIZATION: Use vectorized numeric conversion ---
    df['on_hand_qty'] = safe_numeric_column(df['on_hand_qty'], remove_commas=True)
    df['in_transit_qty'] = safe_numeric_column(df['in_transit_qty'], remove_commas=True)
    df['last_purchase_price'] = safe_numeric_column(df['last_purchase_price'], remove_commas=True)

    df['currency'] = df['currency'].astype(str).str.strip().str.upper()
    df['currency'] = df['currency'].fillna('USD')

    # Clean storage_location column
    df['storage_location'] = df['storage_location'].astype(str).str.strip()
    df['storage_location'] = df['storage_location'].replace(['nan', 'None', ''], pd.NA)

    # Clean descriptive fields
    df['product_name'] = df['product_name'].astype(str).str.strip()
    df['product_name'] = df['product_name'].replace(['nan', 'None', ''], pd.NA)

    df['brand'] = df['brand'].astype(str).str.strip()
    df['brand'] = df['brand'].replace(['nan', 'None', ''], pd.NA)

    # Parse last_inbound_date
    df['last_inbound_date'] = pd.to_datetime(df['last_inbound_date'], errors='coerce')

    # --- NEW: Aggregate stock by SKU ---
    # The inventory file can have multiple rows for the same SKU (e.g., in different storage locations).
    # We must sum quantities and take the first pricing info (prices should be the same per SKU).
    # For storage_location, concatenate unique non-null values with " | " separator
    # For descriptive fields (product_name, brand), take first non-null value
    # For last_inbound_date, take the most recent (max) date
    rows_before_agg = len(df)

    # OPTIMIZATION: Use lambda instead of named function for faster aggregation
    df = df.groupby('sku', as_index=False).agg({
        'on_hand_qty': 'sum',
        'in_transit_qty': 'sum',
        'last_purchase_price': 'first',  # Take first price (should be same per SKU)
        'currency': 'first',  # Take first currency (should be same per SKU)
        'storage_location': lambda x: ' | '.join(sorted(x.dropna().unique())) if len(x.dropna().unique()) > 0 else '',
        'product_name': 'first',  # Take first non-null product name
        'brand': 'first',  # Take first non-null brand
        'last_inbound_date': 'max'  # Take most recent inbound date
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
        # Prefer 'Goods Issue Date: Date' if present, otherwise fall back to 'Delivery Creation Date: Date'
        date_col = 'Goods Issue Date: Date' if 'Goods Issue Date: Date' in deliveries_df_unified.columns else 'Delivery Creation Date: Date'
        deliveries_df = deliveries_df_unified[["Item - SAP Model Code", date_col, "Deliveries - TOTAL Goods Issue Qty"]].copy()
        deliveries_df = deliveries_df.rename(columns={
            "Item - SAP Model Code": "sku",
            date_col: "ship_date",
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

        # Keep only necessary columns for merging
        daily_demand = daily_demand[['sku', 'daily_demand']]

        # --- NEW: Calculate Monthly Demand (Last 12 months rolling) ---
        logs.append("INFO: Calculating monthly demand (rolling last 12 months)...")

        # Anchor rolling 12 months to application TODAY (inclusive)
        latest_month = TODAY.replace(day=1)  # month-start for current month
        earliest_month = (latest_month - pd.DateOffset(months=11)).replace(day=1)

        logs.append(f"INFO: Monthly window: {earliest_month.date()} -> {TODAY.date()} (12 months)")

        # Create month period column for each delivery
        monthly_data = deliveries_df[(deliveries_df['ship_date'] >= earliest_month) & (deliveries_df['ship_date'] <= TODAY)].copy()
        monthly_data['month'] = monthly_data['ship_date'].dt.to_period('M').dt.to_timestamp()

        # Single groupby + pivot for last 12 months (sku x month)
        monthly_pivot = monthly_data.groupby(['sku', 'month'], observed=True)['units_issued'].sum().reset_index()
        monthly_pivot = monthly_pivot.pivot(index='sku', columns='month', values='units_issued').reset_index()

        # Ensure we have all 12 months in the pivot with consistent column names
        # Note: earliest_month + DateOffset already returns a Timestamp, no need for .to_timestamp()
        months = [(earliest_month + pd.DateOffset(months=i)) for i in range(12)]
        month_cols = []
        for m in months:
            col_name = f"m_{m.year}_{m.month:02d}"
            month_cols.append(col_name)
            if m in monthly_pivot.columns:
                # rename timestamp column to friendly column name
                monthly_pivot = monthly_pivot.rename(columns={m: col_name})
            elif col_name not in monthly_pivot.columns:
                monthly_pivot[col_name] = 0

        # Fill any remaining NaNs with 0
        monthly_pivot = monthly_pivot.fillna(0)

        # Rolling 1-year usage (sum of last 12 months) - reuse total_demand which was computed using recent_deliveries
        rolling_1yr = total_demand.rename(columns={'total_units_issued': 'rolling_1yr_usage'})

        # --- NEW: Calculate # of Months with History ---
        # For each SKU, count how many months have had any demand since activation
        logs.append("INFO: Calculating months with demand history since SKU activation...")

        # Merge with activation dates
        deliveries_with_activation = pd.merge(deliveries_df, sku_activation[['sku', 'activation_date']], on='sku', how='left')

        # Only count deliveries after activation date
        deliveries_with_activation = deliveries_with_activation[
            (deliveries_with_activation['ship_date'] >= deliveries_with_activation['activation_date']) |
            (deliveries_with_activation['activation_date'].isna())
        ]

        # Assign each delivery to a month period
        deliveries_with_activation['month_year'] = deliveries_with_activation['ship_date'].dt.to_period('M')

        # Count unique months with demand per SKU
        months_with_history = deliveries_with_activation.groupby('sku')['month_year'].nunique().reset_index()
        months_with_history = months_with_history.rename(columns={'month_year': 'months_with_history'})

        logs.append(f"INFO: Calculated months with history for {len(months_with_history)} SKUs.")

    except Exception as e:
        logs.append(f"ERROR: Failed to process 'DELIVERIES.csv' for demand calculation: {e}")
        return logs, pd.DataFrame()

    # 2. Merge demand with inventory and calculate DIO
    # If inventory_df contains time-series snapshot rows (has 'Current Date'),
    # compute a monthly inventory pivot for the last 12 months and merge as inv_m_YYYY_MM columns.
    inv_month_cols = []
    try:
        if 'Current Date' in inventory_df.columns:
            logs.append("INFO: Inventory snapshots detected; building monthly inventory time-series columns (inv_m_YYYY_MM)...")
            # Parse Current Date and ensure on_hand_qty column exists
            inv_hist = inventory_df.copy()
            inv_hist['current_date_parsed'] = pd.to_datetime(inv_hist['Current Date'], errors='coerce')
            # Keep only rows with a date and non-null sku
            inv_hist['sku'] = clean_string_column(inv_hist.get('sku', inv_hist.get('Material Number', pd.Series(dtype=str))))
            inv_hist = inv_hist.dropna(subset=['sku', 'current_date_parsed'])

            # Create month period and pivot last 12 months
            latest_month = TODAY.replace(day=1)
            earliest_month = (latest_month - pd.DateOffset(months=11)).replace(day=1)
            inv_hist_recent = inv_hist[(inv_hist['current_date_parsed'] >= earliest_month) & (inv_hist['current_date_parsed'] <= TODAY)].copy()
            if not inv_hist_recent.empty and 'on_hand_qty' in inv_hist_recent.columns:
                inv_hist_recent['month'] = inv_hist_recent['current_date_parsed'].dt.to_period('M').dt.to_timestamp()
                inv_pivot = inv_hist_recent.groupby(['sku', 'month'], observed=True)['on_hand_qty'].sum().reset_index()
                inv_pivot = inv_pivot.pivot(index='sku', columns='month', values='on_hand_qty').reset_index()

                # Generate month timestamps for the last 12 months
                # earliest_month is already a Timestamp, so we just add DateOffset (no need for .to_timestamp())
                months = [(earliest_month + pd.DateOffset(months=i)) for i in range(12)]
                for m in months:
                    col_name = f"inv_m_{m.year}_{m.month:02d}"
                    inv_month_cols.append(col_name)
                    if m in inv_pivot.columns:
                        inv_pivot = inv_pivot.rename(columns={m: col_name})
                    elif col_name not in inv_pivot.columns:
                        inv_pivot[col_name] = 0

                inv_pivot = inv_pivot.fillna(0)

                # Merge inventory monthly pivot into a current-inventory summary below
            else:
                logs.append("INFO: No recent inventory snapshot rows were found for monthly inventory pivot.")
                inv_pivot = pd.DataFrame()
        else:
            inv_pivot = pd.DataFrame()
    except Exception as e:
        logs.append(f"WARN: Failed to build inventory monthly pivot from snapshots: {e}")
        inv_pivot = pd.DataFrame()

    # Use aggregated / latest snapshot per SKU for main inventory metrics
    # If the passed inventory_df appears to be time-series (multiple snapshots), pick the latest snapshot per sku
    if 'Current Date' in inventory_df.columns:
        inv_for_merge = inventory_df.copy()
        inv_for_merge['current_date_parsed'] = pd.to_datetime(inv_for_merge['Current Date'], errors='coerce')
        inv_for_merge['sku'] = clean_string_column(inv_for_merge.get('sku', inv_for_merge.get('Material Number', pd.Series(dtype=str))))
        # choose latest snapshot per sku
        inv_for_merge = inv_for_merge.sort_values(['sku', 'current_date_parsed']).groupby('sku', as_index=False).last()
    else:
        inv_for_merge = inventory_df.copy()

    df = pd.merge(inv_for_merge, daily_demand, on='sku', how='left')

    # Merge monthly demand pivot (last 12 months)
    df = pd.merge(df, monthly_pivot, on='sku', how='left')
    # Merge inventory monthly pivot (if built)
    if not inv_pivot.empty:
        df = pd.merge(df, inv_pivot, on='sku', how='left')
    df = pd.merge(df, rolling_1yr, on='sku', how='left')
    df = pd.merge(df, months_with_history, on='sku', how='left')

    # Fill NaN values with 0 for all demand columns
    df['daily_demand'] = df['daily_demand'].fillna(0)
    # Fill monthly columns with 0 if missing
    for _mc in month_cols:
        if _mc in df.columns:
            df[_mc] = df[_mc].fillna(0)
    df['rolling_1yr_usage'] = df['rolling_1yr_usage'].fillna(0)
    df['months_with_history'] = df['months_with_history'].fillna(0).astype(int)
    
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
    
    # OPTIMIZATION #3: Convert categorical columns to category dtype for memory savings (50-90% reduction)
    categorical_cols = ['category', 'storage_location', 'product_name', 'brand', 'currency', 'plm_status']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')
    
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
        
        # Build lookup dictionary (using itertuples for 100x faster performance)
        lead_time_lookup = {
            row.sku: {
                'lead_time_days': int(row.lead_time_with_safety),
                'vendor_count': int(row.po_count),
                'median_base': int(row.median_lead_time)
            }
            for row in lead_times_by_sku.itertuples()
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


# ===== VENDOR & PROCUREMENT DATA LOADERS =====

@st.cache_data(ttl=3600, show_spinner="Loading vendor purchase orders...")
def load_vendor_pos(po_path, file_key='vendor_pos'):
    """
    Load vendor purchase order data from Domestic Vendor POs.csv

    Args:
        po_path: Path to Domestic Vendor POs.csv
        file_key: Session state key for uploaded file

    Returns: logs (list), dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Vendor Purchase Orders Loader ---")

    # Define column mapping
    po_cols = {
        "SAP Purchase Orders - Purchasing Document Number": "po_number",
        "Order Creation Date - Date": "po_create_date",
        "Last Requested Delivery Date - Date": "requested_delivery_date",
        "Last Confirmed Delivery Date - Date": "confirmed_delivery_date",
        "SAP Material Code": "sku",
        "Model Desc": "product_description",
        "SAP Supplier - Supplier Description": "vendor_name",
        "SAP Supplier - Country Key": "vendor_country",
        "SAP Supplier - City": "vendor_city",
        "SAP Purchase Orders - Status": "po_status",
        "Supplier Payment Terms": "payment_terms",
        "SAP Purchase Orders - Document Currency Net Value": "po_value",
        "SAP Purchase Orders - Document Currency Net Price": "unit_price",
        "SAP Purchase Orders - Ordered Quantity": "ordered_qty",
        "SAP Purchase Orders - Received Quantity": "received_qty",
        "SAP Purchase Orders - Open Quantity": "open_qty"
    }

    try:
        df = safe_read_csv(file_key, po_path, usecols=list(po_cols.keys()), low_memory=False)
        logs.append(f"INFO: Found and loaded {len(df)} rows from Domestic Vendor POs.csv.")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'Domestic Vendor POs.csv'. Error: {e}")
        return logs, pd.DataFrame()

    if not check_columns(df, po_cols.keys(), "Domestic Vendor POs.csv", logs):
        return logs, pd.DataFrame()

    # Rename columns
    df = df.rename(columns=po_cols)

    # Clean SKU column
    df['sku'] = clean_string_column(df['sku'])

    # Clean vendor name
    df['vendor_name'] = df['vendor_name'].astype(str).str.strip()
    df['vendor_name'] = df['vendor_name'].replace(['nan', 'None', ''], 'Unknown Vendor')

    # Clean PO number
    df['po_number'] = df['po_number'].astype(str).str.strip()

    # Parse dates
    df['po_create_date'] = pd.to_datetime(df['po_create_date'], format='%m/%d/%y', errors='coerce')
    df['requested_delivery_date'] = pd.to_datetime(df['requested_delivery_date'], format='%m/%d/%y', errors='coerce')
    df['confirmed_delivery_date'] = pd.to_datetime(df['confirmed_delivery_date'], format='%m/%d/%y', errors='coerce')

    # Use confirmed delivery if available, otherwise requested
    df['expected_delivery_date'] = df['confirmed_delivery_date'].fillna(df['requested_delivery_date'])

    # Convert numeric columns
    df['ordered_qty'] = safe_numeric_column(df['ordered_qty'], remove_commas=True)
    df['received_qty'] = safe_numeric_column(df['received_qty'], remove_commas=True)
    df['open_qty'] = safe_numeric_column(df['open_qty'], remove_commas=True)
    df['po_value'] = safe_numeric_column(df['po_value'], remove_commas=True)
    df['unit_price'] = safe_numeric_column(df['unit_price'], remove_commas=True)

    # Clean status
    df['po_status'] = df['po_status'].astype(str).str.strip()
    df['po_status'] = df['po_status'].replace(['nan', 'None', ''], 'Unknown')

    # Calculate PO age (days since creation)
    today = pd.Timestamp.now()
    df['po_age_days'] = (today - df['po_create_date']).dt.days

    # Calculate days to delivery (negative = overdue)
    df['days_to_delivery'] = (df['expected_delivery_date'] - today).dt.days

    # Determine if PO is open (has open quantity > 0)
    df['is_open'] = df['open_qty'] > 0

    # Calculate fill rate
    df['fill_rate'] = df.apply(
        lambda row: (row['received_qty'] / row['ordered_qty'] * 100) if row['ordered_qty'] > 0 else 0,
        axis=1
    )

    # OPTIMIZATION: Convert repeat text columns to category dtype for memory savings
    categorical_cols = ['vendor_name', 'vendor_country', 'vendor_city', 'po_status', 'payment_terms', 'product_description']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')

    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Vendor PO Loader finished in {total_time:.2f} seconds.")
    logs.append(f"INFO: Loaded {len(df)} PO line items from {df['vendor_name'].nunique()} vendors.")
    logs.append(f"INFO: {df['is_open'].sum()} open PO lines, {(~df['is_open']).sum()} closed/received.")

    return logs, df


@st.cache_data(ttl=3600, show_spinner="Loading inbound receipts...")
def load_inbound_data(inbound_path, file_key='inbound'):
    """
    Load inbound receipt data from DOMESTIC INBOUND.csv

    Args:
        inbound_path: Path to DOMESTIC INBOUND.csv
        file_key: Session state key for uploaded file

    Returns: logs (list), dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Inbound Receipts Loader ---")

    # Define column mapping
    inbound_cols = {
        "Purchase Order Number": "po_number",
        "Posting Date": "receipt_date",
        "Material Number": "sku",
        "Material Description": "product_description",
        "PLM: Level Classification 4 (Attribute D_TMKLVL4CLS)": "category",
        "POP Good Receipts Quantity": "received_qty",
        "POP Good Receipts Amount (@Purchase Document Price in Document Currency)": "receipt_value"
    }

    try:
        df = safe_read_csv(file_key, inbound_path, usecols=list(inbound_cols.keys()), low_memory=False)
        logs.append(f"INFO: Found and loaded {len(df)} rows from DOMESTIC INBOUND.csv.")
    except Exception as e:
        logs.append(f"ERROR: Failed to read 'DOMESTIC INBOUND.csv'. Error: {e}")
        return logs, pd.DataFrame()

    if not check_columns(df, inbound_cols.keys(), "DOMESTIC INBOUND.csv", logs):
        return logs, pd.DataFrame()

    # Rename columns
    df = df.rename(columns=inbound_cols)

    # Clean columns
    df['sku'] = clean_string_column(df['sku'])
    df['po_number'] = df['po_number'].astype(str).str.strip()
    df['category'] = df['category'].astype(str).str.strip()
    df['category'] = df['category'].replace(['nan', 'None', ''], 'Unknown')

    # Parse receipt date
    df['receipt_date'] = pd.to_datetime(df['receipt_date'], format='%m/%d/%y', errors='coerce')

    # Convert numeric columns
    df['received_qty'] = safe_numeric_column(df['received_qty'], remove_commas=True)
    df['receipt_value'] = safe_numeric_column(df['receipt_value'], remove_commas=True)

    # Calculate receipt age
    today = pd.Timestamp.now()
    df['receipt_age_days'] = (today - df['receipt_date']).dt.days

    # OPTIMIZATION: Convert repeat text columns to category dtype for memory savings
    categorical_cols = ['category', 'product_description']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')

    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Inbound Receipts Loader finished in {total_time:.2f} seconds.")
    logs.append(f"INFO: Loaded {len(df)} receipt records for {df['po_number'].nunique()} unique POs.")

    return logs, df


def load_vendor_performance(po_df, inbound_df):
    """
    Calculate vendor performance metrics by joining POs with receipts

    Args:
        po_df: Vendor PO dataframe from load_vendor_pos()
        inbound_df: Inbound receipts dataframe from load_inbound_data()

    Returns: logs (list), vendor performance dataframe
    """
    logs = []
    start_time = time.time()
    logs.append("--- Vendor Performance Calculator ---")

    if po_df.empty:
        logs.append("ERROR: PO dataframe is empty. Cannot calculate vendor performance.")
        return logs, pd.DataFrame()

    # Join POs with receipts to calculate lead time
    if not inbound_df.empty:
        # Merge on po_number and sku
        merged = po_df.merge(
            inbound_df[['po_number', 'sku', 'receipt_date', 'received_qty']],
            on=['po_number', 'sku'],
            how='left',
            suffixes=('', '_receipt')
        )

        # Calculate actual lead time (receipt date - PO create date)
        merged['actual_lead_time_days'] = (merged['receipt_date'] - merged['po_create_date']).dt.days

        # Calculate planned lead time (expected delivery - PO create date)
        merged['planned_lead_time_days'] = (merged['expected_delivery_date'] - merged['po_create_date']).dt.days

        # Lead time variance
        merged['lead_time_variance_days'] = merged['actual_lead_time_days'] - merged['planned_lead_time_days']

        # On-time delivery (delivered by expected date)
        merged['on_time_delivery'] = merged['receipt_date'] <= merged['expected_delivery_date']
    else:
        logs.append("WARN: No inbound receipt data available. Lead time metrics will be limited.")
        merged = po_df.copy()
        merged['actual_lead_time_days'] = None
        merged['on_time_delivery'] = None

    # Group by vendor to calculate performance metrics
    vendor_perf = merged.groupby('vendor_name', observed=True).agg({
        'po_number': 'nunique',                          # Number of POs
        'ordered_qty': 'sum',                            # Total ordered quantity
        'received_qty': 'sum',                           # Total received quantity
        'open_qty': 'sum',                               # Total open quantity
        'po_value': 'sum',                               # Total PO value
        'on_time_delivery': 'mean',                      # On-time delivery %
        'actual_lead_time_days': 'mean',                 # Average actual lead time
        'planned_lead_time_days': 'mean',                # Average planned lead time
        'lead_time_variance_days': 'mean',               # Average lead time variance
        'fill_rate': 'mean'                              # Average fill rate
    }).reset_index()

    # Rename columns for clarity
    vendor_perf.columns = [
        'vendor_name', 'po_count', 'total_ordered_qty', 'total_received_qty',
        'total_open_qty', 'total_po_value', 'otif_pct', 'avg_actual_lead_time',
        'avg_planned_lead_time', 'avg_lead_time_variance', 'avg_fill_rate'
    ]

    # Convert OTIF to percentage
    vendor_perf['otif_pct'] = vendor_perf['otif_pct'] * 100

    # Calculate average delay days (positive = late, negative = early)
    # Use lead time variance as proxy for delay
    vendor_perf['avg_delay_days'] = vendor_perf['avg_lead_time_variance'].fillna(0).clip(lower=0)

    # Calculate composite vendor score (simple weighted average for now)
    # OTIF (40%), Fill Rate (30%), Lead Time Consistency (30%)
    vendor_perf['vendor_score'] = (
        vendor_perf['otif_pct'] * 0.4 +
        vendor_perf['avg_fill_rate'] * 0.3 +
        (100 - abs(vendor_perf['avg_lead_time_variance'].fillna(0)) / vendor_perf['avg_planned_lead_time'].fillna(1) * 100) * 0.3
    )

    # Rank vendors
    vendor_perf = vendor_perf.sort_values('vendor_score', ascending=False)
    vendor_perf['vendor_rank'] = range(1, len(vendor_perf) + 1)

    end_time = time.time()
    total_time = end_time - start_time
    logs.append(f"INFO: Vendor Performance Calculator finished in {total_time:.2f} seconds.")
    logs.append(f"INFO: Calculated performance for {len(vendor_perf)} vendors.")

    return logs, vendor_perf


def load_backorder_relief(backorder_df, vendor_pos_df, vendor_performance_df):
    """
    Calculate backorder relief dates by matching to vendor POs

    Args:
        backorder_df: Backorder data from load_backorder_data()
        vendor_pos_df: Vendor PO data from load_vendor_pos()
        vendor_performance_df: Vendor performance metrics from load_vendor_performance()

    Returns:
        tuple: (logs, backorder_relief_df)
        - logs: List of processing messages
        - backorder_relief_df: Enhanced backorder data with relief information
    """
    from backorder_relief_analysis import calculate_backorder_relief_dates

    logs, backorder_relief_df = calculate_backorder_relief_dates(
        backorder_df,
        vendor_pos_df,
        vendor_performance_df
    )

    return logs, backorder_relief_df


def load_stockout_prediction(inventory_df, deliveries_df, vendor_pos_df, vendor_performance_df):
    """
    Calculate stockout risk predictions for all SKUs

    Args:
        inventory_df: Current inventory from load_inventory_data()
        deliveries_df: Historical deliveries from load_deliveries_unified()
        vendor_pos_df: Vendor POs from load_vendor_pos()
        vendor_performance_df: Vendor performance from load_vendor_performance()

    Returns:
        tuple: (logs, stockout_risk_df)
        - logs: List of processing messages
        - stockout_risk_df: Enhanced inventory data with stockout risk predictions
    """
    from stockout_prediction import predict_stockout_risk

    logs, stockout_risk_df = predict_stockout_risk(
        inventory_df,
        deliveries_df,
        vendor_pos_df,
        vendor_performance_df,
        service_level=95,
        demand_window_days=90
    )

    return logs, stockout_risk_df


# === SKU DESCRIPTION LOOKUP FUNCTIONS ===
# Centralized functions for adding product descriptions to tables across all dashboard pages

@st.cache_data(show_spinner=False)
def create_sku_description_lookup(orders_item_lookup_df=None, inventory_df=None,
                                   vendor_pos_df=None, deliveries_df=None, inbound_df=None):
    """
    Create a unified SKU → description lookup dictionary.

    Priority order (first non-null description wins):
    1. ORDERS.csv (most complete for backordered items) → product_name
    2. INVENTORY.csv (current product catalog) → product_name
    3. DELIVERIES.csv (historical shipping records) → product_name
    4. Vendor POs (procurement records) → product_description
    5. INBOUND.csv (receiving records) → product_description

    Args:
        orders_item_lookup_df: Orders data with product_name column
        inventory_df: Inventory data with product_name column
        vendor_pos_df: Vendor PO data with product_description column
        deliveries_df: Deliveries data with product_name column
        inbound_df: Inbound data with product_description column

    Returns:
        dict: {sku: description} mapping for fast O(1) lookups
    """
    sku_lookup = {}

    # Priority 1: Orders (best source for active SKUs with backorders)
    if orders_item_lookup_df is not None and not orders_item_lookup_df.empty:
        if 'sku' in orders_item_lookup_df.columns and 'product_name' in orders_item_lookup_df.columns:
            # Use itertuples for 100x faster iteration vs iterrows
            for row in orders_item_lookup_df[['sku', 'product_name']].drop_duplicates('sku').itertuples(index=False):
                if pd.notna(row.product_name) and row.product_name != 'Unknown' and row.product_name != '':
                    sku_lookup[row.sku] = row.product_name

    # Priority 2: Inventory (current catalog)
    if inventory_df is not None and not inventory_df.empty:
        if 'sku' in inventory_df.columns and 'product_name' in inventory_df.columns:
            for row in inventory_df[['sku', 'product_name']].drop_duplicates('sku').itertuples(index=False):
                if row.sku not in sku_lookup and pd.notna(row.product_name) and row.product_name != '':
                    sku_lookup[row.sku] = row.product_name

    # Priority 3: Deliveries (historical shipping)
    if deliveries_df is not None and not deliveries_df.empty:
        if 'sku' in deliveries_df.columns and 'product_name' in deliveries_df.columns:
            for row in deliveries_df[['sku', 'product_name']].drop_duplicates('sku').itertuples(index=False):
                if row.sku not in sku_lookup and pd.notna(row.product_name) and row.product_name != 'Unknown' and row.product_name != '':
                    sku_lookup[row.sku] = row.product_name

    # Priority 4: Vendor POs (procurement)
    if vendor_pos_df is not None and not vendor_pos_df.empty:
        if 'sku' in vendor_pos_df.columns and 'product_description' in vendor_pos_df.columns:
            for row in vendor_pos_df[['sku', 'product_description']].drop_duplicates('sku').itertuples(index=False):
                if row.sku not in sku_lookup and pd.notna(row.product_description) and row.product_description != '':
                    sku_lookup[row.sku] = row.product_description

    # Priority 5: Inbound (receiving records)
    if inbound_df is not None and not inbound_df.empty:
        if 'sku' in inbound_df.columns and 'product_description' in inbound_df.columns:
            for row in inbound_df[['sku', 'product_description']].drop_duplicates('sku').itertuples(index=False):
                if row.sku not in sku_lookup and pd.notna(row.product_description) and row.product_description != '':
                    sku_lookup[row.sku] = row.product_description

    return sku_lookup


def add_sku_descriptions(df, sku_column='sku', sku_lookup=None, description_column='product_description'):
    """
    Add SKU descriptions to any dataframe with a SKU column.

    Args:
        df: DataFrame with SKU column
        sku_column: Name of SKU column (default 'sku')
        sku_lookup: Pre-built SKU lookup dict (from create_sku_description_lookup)
        description_column: Name for the new description column (default 'product_description')

    Returns:
        DataFrame with added description column (inserted after SKU column for readability)
    """
    if df is None or df.empty or sku_lookup is None:
        return df

    if sku_column not in df.columns:
        return df

    # Add description column using vectorized map (fast O(1) lookups!)
    df = df.copy()
    df[description_column] = df[sku_column].map(sku_lookup).fillna('Description Not Available')

    # Reorder columns to put description right after SKU for readability
    # Get column list
    cols = df.columns.tolist()

    # Find index of SKU column
    sku_idx = cols.index(sku_column)

    # Remove description from its current position (at end)
    cols.remove(description_column)

    # Insert description right after SKU
    cols.insert(sku_idx + 1, description_column)

    # Reorder dataframe
    df = df[cols]

    return df


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