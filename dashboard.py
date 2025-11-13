import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import io
from datetime import datetime
import time

# Import modularized functions
from data_loader import (
    load_master_data,
    load_orders_item_lookup, # <-- RENAMED
    load_orders_header_lookup,
    load_service_data,
    load_backorder_data, # <-- NEW
    load_inventory_data,
    load_inventory_analysis_data
)
from utils import get_filtered_data_as_excel

# ===== CONSTANTS & CONFIGURATION =====
# (Org #1: Extract Constants - Magic numbers centralized for easy tuning)

# UI/Layout Constants
CHART_HEIGHT_SMALL = 400
CHART_HEIGHT_LARGE = 500
CHART_MARGIN = dict(l=20, r=20, t=40, b=20)
MAX_DISPLAY_RECORDS = 10
COLUMNS_DEFAULT = 3

# Data & Caching Constants
CACHE_TIMEOUT_SECONDS = 3600  # 1 hour (moved here for consistency)
SECONDARY_Y_AXIS_COLOR = 'red'

# Format Constants (Org #2: DRY - Format Strings)
FORMATS = {
    'currency': '{:,.0f}',           # e.g., 1,234,567
    'percentage': '{:.1f}%',         # e.g., 99.5%
    'decimal_1': '{:.1f}',           # e.g., 12.5
    'integer': '{:,}',               # e.g., 1,234
}

# Debug Tab Column Requirements (Org #4: Debug Tab - Column Definitions)
DEBUG_COLUMNS = {
    'service_data': ["units_issued", "on_time", "days_to_deliver", "customer_name", "ship_month"],
    'service_customer_data': ["total_units", "on_time_pct", "avg_days"],
    'service_monthly_data': ["ship_month", "total_units", "on_time_pct", "avg_days"],
    'backorder_data': ["backorder_qty", "days_on_backorder", "customer_name", "product_name"],
    'backorder_customer_data': ["total_bo_qty", "avg_days_on_bo"],
    'backorder_item_data': ["product_name", "total_bo_qty", "avg_days_on_bo"],
    'inventory_data': ["on_hand_qty", "daily_demand", "category"],
    'inventory_category_data': ["total_on_hand", "avg_dio"],
}

# --- Page Configuration ---
st.set_page_config(
    page_title="Supply Chain Dashboard",
    page_icon="📦",
    layout="wide"
)

# --- File Paths ---
# Support both environment variables and local/relative paths
# Set env vars to override defaults: e.g., export ORDERS_FILE_PATH="/path/to/ORDERS.csv"
ORDERS_FILE_PATH = os.environ.get("ORDERS_FILE_PATH", "data/ORDERS.csv")
DELIVERIES_FILE_PATH = os.environ.get("DELIVERIES_FILE_PATH", "data/DELIVERIES.csv")
MASTER_DATA_FILE_PATH = os.environ.get("MASTER_DATA_FILE_PATH", "data/Master Data.csv")
INVENTORY_FILE_PATH = os.environ.get("INVENTORY_FILE_PATH", "data/INVENTORY.csv")

# === FILE CHECKER & UPLOADER ===
# Check that all files exist; if missing, offer upload fallback
file_paths = {
    "Orders": ORDERS_FILE_PATH,
    "Deliveries": DELIVERIES_FILE_PATH,
    "Master Data": MASTER_DATA_FILE_PATH,
    "Inventory": INVENTORY_FILE_PATH
}

with st.sidebar.expander("File Status & Upload", expanded=True): 
    all_files_found = True
    missing_files = {}

    for file_label, file_path in file_paths.items():
        abs_path = os.path.abspath(file_path)
        if os.path.isfile(abs_path):
            st.success(f"✓ Found {file_label} file") 
        else:
            st.warning(f"✗ NOT FOUND: {file_label} file") 
            st.caption(f"Expected at: {abs_path}")
            all_files_found = False
            missing_files[file_label] = file_path

# Initialize session state for uploaded files
if 'uploaded_files' not in st.session_state:
    st.session_state.uploaded_files = {}

if not all_files_found:
    st.warning("**One or more data files are missing.**")
    st.info("**Option 1: Upload files below** (temporary, for this session)")
    st.info("**Option 2: Set environment variables** before running Streamlit:")
    st.code("""
export ORDERS_FILE_PATH="/path/to/ORDERS.csv"
export DELIVERIES_FILE_PATH="/path/to/DELIVERIES.csv"
export MASTER_DATA_FILE_PATH="/path/to/Master Data.csv"
export INVENTORY_FILE_PATH="/path/to/INVENTORY.csv"
    """, language="bash")
    
    st.divider()
    st.subheader("Upload Files")
    
    # Add custom CSS/JS to disable client-side file size validation
    st.markdown("""
    <style>
    /* Override Streamlit's default file upload size limits */
    input[type="file"] {
        max-upload-size: 1073741824 !important;  /* 1 GB */
    }
    </style>
    """, unsafe_allow_html=True)
    
    # File upload widgets with custom label to indicate size
    st.markdown("**Max file size: 1 GB**")
    
    # File upload widgets
    uploaded_orders = st.file_uploader("Upload ORDERS.csv", type="csv", key="orders_upload", help="Max 1 GB")
    uploaded_deliveries = st.file_uploader("Upload DELIVERIES.csv", type="csv", key="deliveries_upload", help="Max 1 GB")
    uploaded_master = st.file_uploader("Upload Master Data.csv", type="csv", key="master_upload", help="Max 1 GB")
    uploaded_inventory = st.file_uploader("Upload INVENTORY.csv", type="csv", key="inventory_upload", help="Max 1 GB")
    
    # Store uploaded files in session state
    if uploaded_orders:
        st.session_state.uploaded_files['orders'] = uploaded_orders
    if uploaded_deliveries:
        st.session_state.uploaded_files['deliveries'] = uploaded_deliveries
    if uploaded_master:
        st.session_state.uploaded_files['master'] = uploaded_master
    if uploaded_inventory:
        st.session_state.uploaded_files['inventory'] = uploaded_inventory
    
    # Check if all required files are now available (either on disk or uploaded)
    files_available = (
        (os.path.isfile(os.path.abspath(ORDERS_FILE_PATH)) or 'orders' in st.session_state.uploaded_files) and
        (os.path.isfile(os.path.abspath(DELIVERIES_FILE_PATH)) or 'deliveries' in st.session_state.uploaded_files) and
        (os.path.isfile(os.path.abspath(MASTER_DATA_FILE_PATH)) or 'master' in st.session_state.uploaded_files) and
        (os.path.isfile(os.path.abspath(INVENTORY_FILE_PATH)) or 'inventory' in st.session_state.uploaded_files)
    )
    
    if not files_available:
        st.error("All data files are required. Please upload missing files or set environment variables.")
        st.stop()

# === Data Loading with Caching ===
# By decorating these functions with st.cache_data, Streamlit will only run them
# once. On subsequent runs (e.g., when a user changes a filter), Streamlit
# will return the cached data instead of re-reading the files from disk.

@st.cache_data
def get_master_data(path):
    return load_master_data(path, file_key='master')

@st.cache_data
def get_orders_item_lookup(path):
    return load_orders_item_lookup(path, file_key='orders')

@st.cache_data
def get_orders_header_lookup(path):
    return load_orders_header_lookup(path, file_key='orders')

@st.cache_data
def get_service_data(deliveries_path, _orders_header_lookup, _master_data):
    return load_service_data(deliveries_path, _orders_header_lookup, _master_data, file_key='deliveries')

@st.cache_data
def get_backorder_data(_orders_item_lookup, _orders_header_lookup, _master_data):
    return load_backorder_data(_orders_item_lookup, _orders_header_lookup, _master_data)

@st.cache_data
def get_inventory_data(path):
    return load_inventory_data(path, file_key='inventory')

@st.cache_data
def get_inventory_analysis_data(_inventory_data, deliveries_path, _master_data):
    return load_inventory_analysis_data(_inventory_data, deliveries_path, _master_data, file_key='deliveries')
    
# === NEW: State-based Data Loading ===
def load_all_data():
    """
    Clears the cache and loads all data from source files into st.session_state.
    This provides a reliable, stateful way to manage data loading.
    """
    with st.spinner("Clearing cache and loading fresh data... This may take a moment."):
        st.cache_data.clear() # Clear the function-level cache
        
        st.session_state.debug_logs = []
        st.session_state.error_reports = {}

        log_msgs_master, master_data, master_errors = get_master_data(MASTER_DATA_FILE_PATH)
        st.session_state.debug_logs.extend(log_msgs_master)
        if not master_errors.empty: st.session_state.error_reports["Master_Data_Errors"] = (master_errors, True)

        log_msgs_orders_item, orders_item_lookup, orders_item_errors = get_orders_item_lookup(ORDERS_FILE_PATH)
        st.session_state.debug_logs.extend(log_msgs_orders_item)
        if not orders_item_errors.empty: st.session_state.error_reports["Order_Date_Errors"] = (orders_item_errors, True)

        log_msgs_orders_header, orders_header_lookup = get_orders_header_lookup(ORDERS_FILE_PATH)
        st.session_state.debug_logs.extend(log_msgs_orders_header)

        log_msgs_service, service_data, service_errors = get_service_data(DELIVERIES_FILE_PATH, orders_header_lookup, master_data)
        st.session_state.debug_logs.extend(log_msgs_service)
        if not service_errors.empty: st.session_state.error_reports["Service_Data_Errors"] = (service_errors, True)

        log_msgs_backorder, backorder_data, backorder_errors = get_backorder_data(orders_item_lookup, orders_header_lookup, master_data)
        st.session_state.debug_logs.extend(log_msgs_backorder)
        if not backorder_errors.empty: st.session_state.error_reports["Backorder_Errors"] = (backorder_errors, True)

        log_msgs_inv, inventory_data, inv_errors = get_inventory_data(INVENTORY_FILE_PATH)
        st.session_state.debug_logs.extend(log_msgs_inv)
        # if not inv_errors.empty: ... # Add error handling if needed

        log_msgs_inv_analysis, inventory_analysis_data = get_inventory_analysis_data(inventory_data, DELIVERIES_FILE_PATH, master_data)
        st.session_state.debug_logs.extend(log_msgs_inv_analysis)
        # if not inv_analysis_errors.empty: ... # Add error handling if needed

        # Store the final dataframes in session state
        st.session_state.master_data = master_data
        st.session_state.service_data = service_data
        st.session_state.backorder_data = backorder_data
        st.session_state.inventory_analysis_data = inventory_analysis_data
        st.session_state.data_loaded = True
        st.success("Data loaded successfully!")
        st.session_state.last_load_time = time.time() # Store the timestamp of the successful load
        time.sleep(1) # Give user time to see the success message

# === Main App UI ===
st.title("📦 Supply Chain Dashboard")
st.info(f"Data loaded. Today is {datetime.now().strftime('%A, %B %d, %Y')}.")

# --- NEW: Improved Cache Management ---
st.sidebar.info("Data is cached for performance.")
if st.sidebar.button("Clear Cache & Reload Data"):
    # Set a flag to reload data, which will be caught on the next script run
    st.session_state.data_loaded = False
    st.rerun() # Rerun the script to trigger the loading logic
    
st.sidebar.header("Select Report")

# --- NEW: Automatic Cache Invalidation Logic ---
if 'last_load_time' in st.session_state:
    elapsed_time = time.time() - st.session_state.last_load_time
    if elapsed_time > CACHE_TIMEOUT_SECONDS:
        st.session_state.data_loaded = False
        # This message will briefly appear in the sidebar when a reload is triggered
        st.sidebar.info(f"Data automatically refreshed after {int(CACHE_TIMEOUT_SECONDS/60)} minutes.")
        time.sleep(2) # Give user a moment to see the message

# --- NEW: Initialize data on first run or after a reload request ---
if 'data_loaded' not in st.session_state or not st.session_state.get('data_loaded'):
    load_all_data()

# --- NEW: Initialize report-specific filter states and caches ---
if f'active_filters_Service Level' not in st.session_state:
    st.session_state[f'active_filters_Service Level'] = {}
if f'active_filters_Backorder Report' not in st.session_state:
    st.session_state[f'active_filters_Backorder Report'] = {}
if f'active_filters_Inventory Management' not in st.session_state:
    st.session_state[f'active_filters_Inventory Management'] = {}

# --- NEW: Initialize performance caches per report (Perf #1, #2, #4) ---
# Year-month map cache (per report)
if 'cached_year_month_map_Service Level' not in st.session_state:
    st.session_state['cached_year_month_map_Service Level'] = {}
if 'cached_year_month_map_Backorder Report' not in st.session_state:
    st.session_state['cached_year_month_map_Backorder Report'] = {}

# Debug tab aggregation cache (Perf #1)
if 'cached_debug_aggregations' not in st.session_state:
    st.session_state['cached_debug_aggregations'] = {}

# Filter state comparison cache (Perf #4) - per report
if 'cached_filter_state_Service Level' not in st.session_state:
    st.session_state['cached_filter_state_Service Level'] = None
if 'cached_filter_state_Backorder Report' not in st.session_state:
    st.session_state['cached_filter_state_Backorder Report'] = None
if 'cached_filter_changed_Service Level' not in st.session_state:
    st.session_state['cached_filter_changed_Service Level'] = False
if 'cached_filter_changed_Backorder Report' not in st.session_state:
    st.session_state['cached_filter_changed_Backorder Report'] = False

# Track the last active report to clear caches when switching (Perf #2, #4)
if 'last_active_report' not in st.session_state:
    st.session_state['last_active_report'] = None

# --- NEW: Use data from session state as the primary source ---
master_data = st.session_state.get('master_data', pd.DataFrame())
service_data = st.session_state.get('service_data', pd.DataFrame())
backorder_data = st.session_state.get('backorder_data', pd.DataFrame())
inventory_analysis_data = st.session_state.get('inventory_analysis_data', pd.DataFrame())
debug_logs = st.session_state.get('debug_logs', [])

# --- Stop if no data at all (MOVED HERE) ---
if service_data.empty and backorder_data.empty:
    st.error("All data loaders failed to return data. Please check file contents and column names.")
    # Display logs even if we stop
    st.header("Debug Log")
    for msg in debug_logs:
        if "ERROR" in msg or "ADVICE" in msg:
            st.error(msg)
        elif "WARNING" in msg:
            st.warning(msg)
        else:
            st.info(msg)
    st.stop()


# --- Report Selection ---
report_view = st.sidebar.radio(
    "Choose a report to view:",
    ("Service Level", "Backorder Report", "Inventory Management")
)

# --- NEW: Auto-clear caches when switching reports (Perf #2, #4) ---
if st.session_state.get('last_active_report') != report_view:
    # Clear the year-month map cache for this report
    st.session_state[f'cached_year_month_map_{report_view}'] = {}
    # Clear the filter state cache for this report
    st.session_state[f'cached_filter_state_{report_view}'] = None
    st.session_state[f'cached_filter_changed_{report_view}'] = False
    # Update the last active report
    st.session_state['last_active_report'] = report_view

# === Caching for KPI Calculations ===
# By caching the main KPI calculations, the dashboard will feel more responsive
# when switching between radio buttons within a tab.

def get_service_kpis(_f_service):
    if _f_service.empty:
        return 0, 0, 0
    on_time_pct = _f_service['on_time'].mean() * 100
    avg_days = _f_service['days_to_deliver'].mean()
    total_units = _f_service['units_issued'].sum()
    return total_units, on_time_pct, avg_days

def get_backorder_kpis(_f_backorder):
    if _f_backorder.empty:
        return 0, 0, 0
    total_bo_qty = _f_backorder['backorder_qty'].sum()
    # Use a weighted average for days on backorder to match the main KPI
    avg_bo_days = np.average(_f_backorder['days_on_backorder'], weights=_f_backorder['backorder_qty']) if total_bo_qty > 0 else 0
    unique_orders = _f_backorder['sales_order'].nunique()
    return total_bo_qty, avg_bo_days, unique_orders

def get_inventory_kpis(_f_inventory):
    if _f_inventory.empty:
        return 0, 0
    
    total_on_hand = _f_inventory['on_hand_qty'].sum()
    total_daily_demand = _f_inventory['daily_demand'].sum()
    
    # --- FIX: Use top-down DIO calculation for the main KPI ---
    avg_dio = total_on_hand / total_daily_demand if total_daily_demand > 0 else 0
    return total_on_hand, avg_dio


# === Caching for Aggregated Chart Data ===
# This second layer of caching stores the results of the groupby operations.
# It makes the dashboard feel instantaneous when switching between tabs or KPIs
# because the expensive aggregations don't need to be re-calculated.

def get_service_customer_data(_f_service):
    cust_svc = _f_service.groupby('customer_name').agg(
        total_units=('units_issued', 'sum'),
        on_time_pct=('on_time', 'mean'),
        avg_days=('days_to_deliver', 'mean')
    ).sort_values(by='total_units', ascending=False).head(10)
    cust_svc['on_time_pct'] *= 100
    return cust_svc

def get_service_monthly_data(_f_service):
    month_svc = _f_service.groupby(['ship_month_num', 'ship_month']).agg(
        total_units=('units_issued', 'sum'),
        on_time_pct=('on_time', 'mean'),
        avg_days=('days_to_deliver', 'mean')
    ).sort_index().reset_index()
    month_svc['on_time_pct'] *= 100
    return month_svc

def get_backorder_customer_data(_f_backorder):
    if _f_backorder.empty:
        return pd.DataFrame()
    
    def weighted_avg(x):
        weights = _f_backorder.loc[x.index, 'backorder_qty']
        return np.average(x, weights=weights) if weights.sum() > 0 else x.mean()

    return _f_backorder.groupby('customer_name').agg(
        total_bo_qty=('backorder_qty', 'sum'),
        avg_days_on_bo=('days_on_backorder', weighted_avg)
    ).sort_values(by='total_bo_qty', ascending=False).head(10)

def get_backorder_item_data(_f_backorder):
    """Aggregates backorder data by item for the chart and table."""
    if _f_backorder.empty:
        return pd.DataFrame()

    def weighted_avg(x):
        weights = _f_backorder.loc[x.index, 'backorder_qty']
        return np.average(x, weights=weights) if weights.sum() > 0 else x.mean()

    item_bo = _f_backorder.groupby(['sku', 'product_name']).agg(
        total_bo_qty=('backorder_qty', 'sum'), 
        avg_days_on_bo=('days_on_backorder', weighted_avg)
    ).sort_values(by='total_bo_qty', ascending=False).head(10)
    return item_bo.reset_index()

def get_inventory_category_data(df):
    """Aggregates inventory data by category for the chart."""
    if df.empty:
        return pd.DataFrame()
    
    # --- FIX: Implement top-down DIO calculation as requested ---
    # First, group by category and get the SUM of stock and the SUM of demand.
    category_agg = df.groupby('category').agg(
        total_on_hand=('on_hand_qty', 'sum'),
        total_daily_demand=('daily_demand', 'sum')
    )
    
    # Then, perform the division on the aggregated totals.
    # This is the "top-down" approach: Total Stock / Total Daily Demand.
    category_agg['avg_dio'] = np.where(
        category_agg['total_daily_demand'] > 0,
        category_agg['total_on_hand'] / category_agg['total_daily_demand'],
        0  # Set DIO to 0 if there is no demand to avoid division by zero.
    )
    return category_agg.sort_values(by='total_on_hand', ascending=False)


# --- REFACTORED: Apply Filters to Dataframes ---
def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Applies a dictionary of filters to a dataframe efficiently.
    It builds a single boolean mask and applies it once.
    """
    if df.empty:
        return df
    
    # Start with a mask that includes all rows
    combined_mask = pd.Series(True, index=df.index)

    for column, value in filters.items():
        if not value or value == "All":
            continue  # Skip if filter is not set
        
        if column not in df.columns:
            continue  # Skip if the dataframe doesn't have this column

        if isinstance(value, list):
            # For multiselect, use .isin()
            combined_mask &= df[column].isin(value)
        else:
            # For selectbox, use standard equality
            combined_mask &= (df[column] == value)

    return df[combined_mask]

# --- Helper function to safely get unique values ---
def get_unique_values(df, column):
    if not df.empty and column in df.columns:
        return sorted(list(df[df[column] != 'Unknown'][column].astype(str).unique()))
    return []

# --- Org #2: Helper function for consistent DataFrame formatting ---
def format_dataframe_number(value, format_type='currency'):
    """Apply consistent number formatting to dataframe values."""
    fmt = FORMATS.get(format_type, FORMATS['decimal_1'])
    return fmt

def create_dataframe_format_dict(columns, format_types):
    """
    Create a format dictionary for dataframe styling.
    
    Args:
        columns: List of column names to format
        format_types: Dict mapping column names to format type keys (from FORMATS)
    
    Returns:
        Dict ready for df.style.format()
    """
    return {col: FORMATS.get(format_types.get(col, 'decimal_1')) 
            for col in columns if col in format_types}

# --- Org #3: Helper function for multiselect filter widgets ---
def create_multiselect_filter(label, df, column, key_suffix):
    """
    Create a multiselect filter widget with consistent styling.
    
    Args:
        label: Display label for the filter
        df: Source dataframe
        column: Column name to get unique values from
        key_suffix: Unique key suffix for widget identification
    
    Returns:
        List of selected values (empty list if none selected)
    """
    return st.sidebar.multiselect(
        label,
        get_unique_values(df, column),
        key=key_suffix
    )

# --- NEW: Conditional Filters based on Report View ---
st.sidebar.header("Filters")

if report_view == "Inventory Management":
    # --- Inventory-specific filters ---
    st.sidebar.info("This report shows the current inventory snapshot and has no filters.")
    f_inventory = inventory_analysis_data
    
    # Set other filtered dataframes to their unfiltered state so the app doesn't break
    f_service = service_data
    f_backorder = backorder_data

else:
    # --- Global Filters for Service and Backorder Reports ---
    # --- NEW: Determine the correct source dataframe for filters ---
    if report_view == "Service Level":
        filter_source_df = service_data
    elif report_view == "Backorder Report":
        filter_source_df = backorder_data
    else:
        filter_source_df = pd.DataFrame()

    # --- NEW: Generate filter options on-the-fly from the correct source (with caching - Perf #2) ---
    all_years = []
    year_month_map = {}
    
    # Check if we have a cached year-month map for this report
    cached_map = st.session_state.get(f'cached_year_month_map_{report_view}', {})
    if cached_map and not filter_source_df.empty and 'order_date' in filter_source_df.columns:
        # Use cached map
        year_month_map = cached_map
        all_years = sorted(list(year_month_map.keys()), reverse=True)
    elif not filter_source_df.empty and 'order_date' in filter_source_df.columns:
        # Build and cache the year-month map
        all_years = sorted(list(filter_source_df['order_date'].dt.year.dropna().astype(int).unique()), reverse=True)
        date_df = filter_source_df[['order_date']].dropna().drop_duplicates()
        date_df['year'] = date_df['order_date'].dt.year
        date_df['month_name'] = date_df['order_date'].dt.month_name()
        date_df['month_num'] = date_df['order_date'].dt.month
        year_month_map = date_df.groupby('year')[['month_num', 'month_name']].apply(lambda x: x.drop_duplicates().sort_values('month_num')['month_name'].tolist()).to_dict()
        # Cache it for next time
        st.session_state[f'cached_year_month_map_{report_view}'] = year_month_map

    f_year = st.sidebar.selectbox("Select Order Year:", ["All"] + all_years, key="year")

    sorted_months = []
    if f_year != "All" and f_year in year_month_map:
        sorted_months = year_month_map[f_year]
    else:
        all_months = set()
        for months in year_month_map.values():
            all_months.update(months)
        sorted_months = sorted(list(all_months), key=lambda m: pd.to_datetime(m, format='%B').month)
    f_month = st.sidebar.selectbox("Select Order Month:", ["All"] + list(sorted_months), key="month")

    # --- Org #3: Use helper function for consistent multiselect widgets ---
    f_customer = create_multiselect_filter("Select Customer(s):", filter_source_df, 'customer_name', "customer")
    f_material = create_multiselect_filter("Select Material(s):", filter_source_df, 'product_name', "material")
    f_category = create_multiselect_filter("Select Category:", filter_source_df, 'category', "category")
    f_sales_org = create_multiselect_filter("Select Sales Org(s):", filter_source_df, 'sales_org', "sales_org")
    f_order_type = create_multiselect_filter("Select Order Type(s):", filter_source_df, 'order_type', "order_type")

    # --- FIX: Order Reason is an outbound metric (ORDERS.csv/DELIVERIES.csv only) ---
    # Should NEVER be considered for Inventory reports. Only show for Backorder reports.
    f_order_reason = []
    if report_view == "Backorder Report":
        f_order_reason = st.sidebar.multiselect("Select Order Reason(s):", get_unique_values(filter_source_df, 'order_reason'), key="order_reason")

    if st.sidebar.button("Apply Filters", use_container_width=True, type="primary"):
        # Store filters in a report-specific key
        st.session_state[f'active_filters_{report_view}'] = {
            'order_year': f_year,
            'order_month': f_month,
            'customer_name': f_customer,
            'category': f_category,
            'product_name': f_material,
            'sales_org': f_sales_org,
            'order_type': f_order_type,
            'order_reason': f_order_reason if 'f_order_reason' in locals() else []
        }

# === Tabbed Interface ===
tab_service, tab_debug = st.tabs([
    f"{report_view}", 
    "Debug Log" 
])

if report_view == "Service Level":
    # --- Apply filters for THIS view ---
    active_filters = st.session_state.get(f'active_filters_{report_view}', {})
    f_service = apply_filters(service_data, active_filters)

    # --- Set other dataframes to their unfiltered state ---
    f_backorder = backorder_data
    f_inventory = inventory_analysis_data

    # --- Tab 1: Service Level ---
    with tab_service:
        # --- UPDATED: Show a message if filters have changed but not been applied (with caching - Perf #4) ---
        # We create a dictionary from the current widget state to compare (only if not in inventory view)
        if report_view != "Inventory Management":
            current_widget_state = {
                'order_year': f_year, 'order_month': f_month, 'customer_name': f_customer,
                'category': f_category, 'product_name': f_material, 'sales_org': f_sales_org,
                'order_type': f_order_type, 'order_reason': [] # No order reason on service
            }
            active_filters = st.session_state.get(f'active_filters_{report_view}', {})
            
            # Check cache (Perf #4: avoid redundant dictionary comparisons)
            if current_widget_state != active_filters:
                st.session_state[f'cached_filter_changed_{report_view}'] = True
                st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the report.")
            else:
                st.session_state[f'cached_filter_changed_{report_view}'] = False

        st.header("Service Level Performance (Shipped Orders)")
        dfs_to_export = {} # Initialize here
        if f_service.empty:
            st.warning("No shipped (service) data matches your filters.")
        else:
            # --- Export Button for this view ---
            service_cust_export = get_service_customer_data(f_service)
            dfs_to_export["Service_Customer_Top10"] = (service_cust_export, True)
            dfs_to_export["Service_Monthly"] = (get_service_monthly_data(f_service), True)
            dfs_to_export["Service_Raw_Filtered"] = (f_service, False)

            # --- Main Page Content ---
            kpi_choice = st.radio(
                "Select Service KPI:",
                options=["On-Time %", "Avg. Days to Deliver"],
                horizontal=True,
                key='service_kpi_radio'
            )
            total_units, on_time_pct, avg_days = get_service_kpis(f_service)
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Total Units Issued", f"{total_units:,.0f}")
            kpi2.metric("On-Time (OT) %", f"{on_time_pct:.1f}%")
            kpi3.metric("Avg. Days to Deliver", f"{avg_days:.1f} days")
            
            st.divider()
            
            if kpi_choice == "On-Time %":
                kpi_col, kpi_name, y_range = 'on_time_pct', 'On-Time %', [0, 100]
            else:
                kpi_col, kpi_name, y_range = 'avg_days', 'Avg. Days', None

            col1, col2 = st.columns(2)
            with col1:
                st.subheader(f"Units & {kpi_name} by Customer (Top 10)")
                cust_svc = pd.DataFrame()
                try:
                    cust_svc = get_service_customer_data(f_service)
                    if cust_svc.empty:
                        st.warning("No customer data available for charting.")
                    else:
                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Bar(x=cust_svc.index, y=cust_svc['total_units'], name="Units Issued"), secondary_y=False)
                        fig.add_trace(go.Scatter(x=cust_svc.index, y=cust_svc[kpi_col], name=kpi_name, mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                        fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN)
                        fig.update_yaxes(title_text="Units Issued", secondary_y=False)
                        fig.update_yaxes(title_text=kpi_name, secondary_y=True, range=y_range)
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error generating customer chart: {e}")
                
                if not cust_svc.empty:
                    st.dataframe(cust_svc.style.format({
                        'total_units': FORMATS['currency'], 
                        'on_time_pct': FORMATS['percentage'], 
                        'avg_days': FORMATS['decimal_1']
                    }), use_container_width=True)

            with col2:
                st.subheader(f"Monthly Units & {kpi_name}")
                month_svc = pd.DataFrame()
                try:
                    month_svc = get_service_monthly_data(f_service)
                    if month_svc.empty:
                        st.warning("No monthly data available for charting.")
                    else:
                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Bar(x=month_svc['ship_month'], y=month_svc['total_units'], name="Units Issued"), secondary_y=False)
                        fig.add_trace(go.Scatter(x=month_svc['ship_month'], y=month_svc[kpi_col], name=kpi_name, mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                        fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN)
                        fig.update_yaxes(title_text="Units Issued", secondary_y=False)
                        fig.update_yaxes(title_text=kpi_name, secondary_y=True, range=y_range)
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error generating monthly chart: {e}")
                
                if not month_svc.empty:
                    st.dataframe(month_svc[['ship_month', 'total_units', 'on_time_pct', 'avg_days']].style.format({
                        'total_units': FORMATS['currency'], 
                        'on_time_pct': FORMATS['percentage'], 
                        'avg_days': FORMATS['decimal_1']
                    }), use_container_width=True, hide_index=True)

elif report_view == "Backorder Report":
    # --- Apply filters for THIS view ---
    active_filters = st.session_state.get(f'active_filters_{report_view}', {})
    f_backorder = apply_filters(backorder_data, active_filters)

    # --- Set other dataframes to their unfiltered state ---
    f_service = service_data
    f_inventory = inventory_analysis_data

    with tab_service:
        # --- UPDATED: Show a message if filters have changed but not been applied (with caching - Perf #4) ---
        if report_view != "Inventory Management":
            current_widget_state = {
                'order_year': f_year, 'order_month': f_month, 'customer_name': f_customer,
                'category': f_category, 'product_name': f_material, 'sales_org': f_sales_org,
                'order_type': f_order_type, 'order_reason': f_order_reason  # Safe: f_order_reason defined for all reports
            }
            active_filters = st.session_state.get(f'active_filters_{report_view}', {})
            
            # Check cache (Perf #4: avoid redundant dictionary comparisons)
            if current_widget_state != active_filters:
                st.session_state[f'cached_filter_changed_{report_view}'] = True
                st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the report.")
            else:
                st.session_state[f'cached_filter_changed_{report_view}'] = False

        st.header("Backorder Analysis (Unfulfilled Orders)")
        dfs_to_export = {} # Initialize here
        if f_backorder.empty:
            st.warning("No backorder (unfulfilled) data matches your filters.")
        else:
            # --- Export Button for this view ---
            dfs_to_export["Backorder_Customer_Top10"] = (get_backorder_customer_data(f_backorder), True)
            dfs_to_export["Backorder_Item_Top10"] = (get_backorder_item_data(f_backorder), False)
            dfs_to_export["Backorder_Raw_Filtered"] = (f_backorder, False)

            # --- Main Page Content ---
            total_bo_qty, avg_bo_days, unique_orders = get_backorder_kpis(f_backorder)
            
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Total Backorder Qty", f"{total_bo_qty:,.0f} units")
            kpi2.metric("Avg. Days on Backorder", f"{avg_bo_days:.1f} days")
            kpi3.metric("Total Sales Orders on BO", f"{unique_orders:,}")
            
            st.divider()
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Backorder Qty by Customer (Top 10)")
                cust_bo = pd.DataFrame()
                try:
                    cust_bo = get_backorder_customer_data(f_backorder)
                    if cust_bo.empty:
                        st.warning("No customer data available for charting.")
                    else:
                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Bar(x=cust_bo.index, y=cust_bo['total_bo_qty'], name="Backorder Qty"), secondary_y=False)
                        fig.add_trace(go.Scatter(x=cust_bo.index, y=cust_bo['avg_days_on_bo'], name="Avg. Days on BO", mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                        fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN)
                        fig.update_yaxes(title_text="Backorder Qty", secondary_y=False)
                        fig.update_yaxes(title_text="Avg. Days on BO", secondary_y=True)
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error generating customer chart: {e}")
                
                if not cust_bo.empty:
                    st.dataframe(cust_bo.style.format({
                        'total_bo_qty': FORMATS['currency'], 
                        'avg_days_on_bo': FORMATS['decimal_1']
                    }), use_container_width=True)

            with col2: # --- NEW: Add a chart for the item data ---
                st.subheader("Backorder Qty by Item (Top 10)")
                item_bo_chart = pd.DataFrame()
                try:
                    item_bo_chart = get_backorder_item_data(f_backorder)
                    if item_bo_chart.empty:
                        st.warning("No item data available for charting.")
                    else:
                        fig = go.Figure(go.Bar(x=item_bo_chart['product_name'], y=item_bo_chart['total_bo_qty']))
                        fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN, yaxis_title="Backorder Qty")
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Error generating item chart: {e}")

                if not item_bo_chart.empty:
                    st.dataframe(item_bo_chart.set_index(['sku', 'product_name']).style.format({
                        'total_bo_qty': FORMATS['currency'], 
                        'avg_days_on_bo': FORMATS['decimal_1']
                    }), use_container_width=True)

elif report_view == "Inventory Management":
    # --- Apply filters for THIS view ---
    active_filters = st.session_state.get(f'active_filters_{report_view}', {})
    f_inventory = apply_filters(inventory_analysis_data, active_filters)

    # --- Set other dataframes to their unfiltered state ---
    f_service = service_data
    f_backorder = backorder_data

    with tab_service:
        # Note: Filters like year, month, customer, etc., may not apply to a simple inventory snapshot.
        # The filtering logic is kept for consistency, but may result in an empty set if the inventory data lacks those columns.
        st.header("Inventory Position")
        dfs_to_export = {} # Initialize here
        if f_inventory.empty:
            st.warning("No inventory data available.")
        else:
            # --- Export Button for this view ---
            inv_cat_export = get_inventory_category_data(f_inventory)
            dfs_to_export["Inventory_by_Category"] = (inv_cat_export, True)
            dfs_to_export["Inventory_Raw_Filtered"] = (f_inventory, False)

            # --- Main Page Content ---
            total_on_hand, avg_dio = get_inventory_kpis(f_inventory)
            
            kpi1, kpi2 = st.columns(2)
            kpi1.metric("Total On-Hand Stock", f"{total_on_hand:,.0f} units")
            kpi2.metric("Weighted Avg. DIO", f"{avg_dio:.1f} days")
            
            st.divider()
            
            st.subheader("On-Hand Stock & DIO by Category")
            inv_by_cat = pd.DataFrame()
            try:
                inv_by_cat = get_inventory_category_data(f_inventory)
                if inv_by_cat.empty:
                    st.warning("No inventory category data available for charting.")
                else:
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    fig.add_trace(go.Bar(x=inv_by_cat.index, y=inv_by_cat['total_on_hand'], name="On-Hand Stock"), secondary_y=False)
                    fig.add_trace(go.Scatter(x=inv_by_cat.index, y=inv_by_cat['avg_dio'], name="Avg. DIO", mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                    
                    fig.update_layout(height=CHART_HEIGHT_LARGE, margin=CHART_MARGIN)
                    fig.update_yaxes(title_text="On-Hand Stock (Units)", secondary_y=False)
                    fig.update_yaxes(title_text="Avg. Days of Inventory (DIO)", secondary_y=True)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Error generating inventory chart: {e}")
            
            if not inv_by_cat.empty:
                st.dataframe(inv_by_cat.style.format({
                    'total_on_hand': FORMATS['currency'], 
                    'avg_dio': FORMATS['decimal_1']
                }), use_container_width=True)


# --- Tab 6: Debug Log ---
with tab_debug:
    st.header("Data Loader Debug Log")
    error_reports = st.session_state.get('error_reports', {})

    if error_reports:
        st.error("Actionable data quality issues were found during loading.")
        try:
            error_excel_data = get_filtered_data_as_excel(error_reports)
            st.download_button(
                label="Download Data Quality Report (Errors & Mismatches)",
                data=error_excel_data,
                file_name="Data_Quality_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
            )
        except Exception as e:
            st.error("An error occurred while generating the Error Report.")
            st.exception(e)
        st.divider()
    else:
        st.success("No data quality errors or mismatches found.")
        st.divider()

    st.header("🕵️ Line/Bar Graph Debugger")
    st.info("This section checks for common issues that prevent line/bar graphs from rendering.")

    def check_graph_df(df, name, required_cols):
        issues = []
        if df.empty:
            issues.append(f"❌ {name} dataframe is EMPTY.")
        for col in required_cols:
            if col not in df.columns:
                issues.append(f"❌ Column '{col}' missing in {name}.")
        if not issues:
            issues.append(f"✅ {name} dataframe OK for graphing.")
        return issues

    # --- Org #4: Use DEBUG_COLUMNS constants for maintainability ---
    # Service Level Graphs
    st.subheader("Service Level Graphs")
    for issue in check_graph_df(service_data, "service_data", DEBUG_COLUMNS['service_data']):
        st.write(issue)
    
    # Cache service customer data
    if 'service_customer_debug' not in st.session_state['cached_debug_aggregations']:
        st.session_state['cached_debug_aggregations']['service_customer_debug'] = get_service_customer_data(service_data)
    for issue in check_graph_df(st.session_state['cached_debug_aggregations']['service_customer_debug'], "service_customer_data", DEBUG_COLUMNS['service_customer_data']):
        st.write(issue)
    
    # Cache service monthly data
    if 'service_monthly_debug' not in st.session_state['cached_debug_aggregations']:
        st.session_state['cached_debug_aggregations']['service_monthly_debug'] = get_service_monthly_data(service_data)
    for issue in check_graph_df(st.session_state['cached_debug_aggregations']['service_monthly_debug'], "service_monthly_data", DEBUG_COLUMNS['service_monthly_data']):
        st.write(issue)

    # Backorder Graphs
    st.subheader("Backorder Graphs")
    for issue in check_graph_df(backorder_data, "backorder_data", DEBUG_COLUMNS['backorder_data']):
        st.write(issue)
    
    # Cache backorder customer data
    if 'backorder_customer_debug' not in st.session_state['cached_debug_aggregations']:
        st.session_state['cached_debug_aggregations']['backorder_customer_debug'] = get_backorder_customer_data(backorder_data)
    for issue in check_graph_df(st.session_state['cached_debug_aggregations']['backorder_customer_debug'], "backorder_customer_data", DEBUG_COLUMNS['backorder_customer_data']):
        st.write(issue)
    
    # Cache backorder item data
    if 'backorder_item_debug' not in st.session_state['cached_debug_aggregations']:
        st.session_state['cached_debug_aggregations']['backorder_item_debug'] = get_backorder_item_data(backorder_data)
    for issue in check_graph_df(st.session_state['cached_debug_aggregations']['backorder_item_debug'], "backorder_item_data", DEBUG_COLUMNS['backorder_item_data']):
        st.write(issue)

    # Inventory Graphs
    st.subheader("Inventory Graphs")
    for issue in check_graph_df(inventory_analysis_data, "inventory_analysis_data", DEBUG_COLUMNS['inventory_data']):
        st.write(issue)
    
    # Cache inventory category data
    if 'inventory_category_debug' not in st.session_state['cached_debug_aggregations']:
        st.session_state['cached_debug_aggregations']['inventory_category_debug'] = get_inventory_category_data(inventory_analysis_data)
    for issue in check_graph_df(st.session_state['cached_debug_aggregations']['inventory_category_debug'], "inventory_category_data", DEBUG_COLUMNS['inventory_category_data']):
        st.write(issue)

    st.divider()

    st.subheader("Loader Log Messages")
    action_logs = [msg for msg in debug_logs if msg.startswith(("ERROR", "ADVICE", "WARNING"))]
    info_logs = [msg for msg in debug_logs if msg.startswith("INFO")]
    other_logs = [msg for msg in debug_logs if not msg.startswith(("ERROR", "ADVICE", "WARNING", "INFO"))]
    for msg in action_logs:
        if "ERROR" in msg or "ADVICE" in msg:
            st.error(msg)
        elif "WARNING" in msg:
            st.warning(msg)
    with st.expander("Show Full Info Log (Timings, Row Counts)"):
        for msg in other_logs: 
            st.info(msg)
        for msg in info_logs:
            st.info(msg)

# --- Sidebar Export Section ---
st.sidebar.divider()
st.sidebar.header("Download Filtered Data")

# --- FIX: Add the download button logic that was missing ---
if 'dfs_to_export' in locals() and dfs_to_export:
    try:
        excel_data = get_filtered_data_as_excel(dfs_to_export)
        st.sidebar.download_button(
            label="📥 Download as Excel",
            data=excel_data,
            file_name=f"Filtered_Supply_Chain_Data_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
    except Exception as e:
        st.sidebar.error("Failed to generate Excel file.")
        print(f"Excel generation error: {e}") # For terminal debugging
else:
    st.sidebar.info("No data available to download for the current filter selection.")