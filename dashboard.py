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
    load_inventory_analysis_data,
    load_vendor_po_lead_times,  # <-- GROUP 6C
    get_forecast_horizon  # <-- GROUP 6C/6D
)
from utils import get_filtered_data_as_excel, get_filtered_data_as_excel_with_metadata

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

# Anomaly Detection Thresholds (GROUP 6B) - 3 Sensitivity Levels
ANOMALY_THRESHOLDS = {
    'Conservative': {  # Strictest - catch more issues
        'service_min_ontime_pct': 90,
        'service_max_days_deliver': 7,
        'service_customer_underperformance': 5,  # % below average
        'backorder_max_days': 20,
        'backorder_qty_spike_threshold': 30,  # % above average
        'inventory_max_dio': 45,
        'inventory_min_days_supply': 7,
    },
    'Normal': {  # Default - balanced
        'service_min_ontime_pct': 85,
        'service_max_days_deliver': 10,
        'service_customer_underperformance': 10,
        'backorder_max_days': 30,
        'backorder_qty_spike_threshold': 50,
        'inventory_max_dio': 60,
        'inventory_min_days_supply': 5,
    },
    'Aggressive': {  # Lenient - catch only critical issues
        'service_min_ontime_pct': 75,
        'service_max_days_deliver': 15,
        'service_customer_underperformance': 15,
        'backorder_max_days': 45,
        'backorder_qty_spike_threshold': 75,
        'inventory_max_dio': 90,
        'inventory_min_days_supply': 3,
    }
}

# --- Page Configuration ---
st.set_page_config(
    page_title="Supply Chain Dashboard",
    page_icon="📦",
    layout="wide"
)

# --- Mobile Responsive CSS Styling (GROUP 5E) ---
st.markdown("""
    <style>
        /* General responsive improvements */
        @media (max-width: 768px) {
            /* Stack columns on mobile */
            .stColumns > [data-testid="column"] {
                width: 100% !important;
                margin-bottom: 1rem;
            }
            
            /* Collapsible sections for better mobile UX */
            .streamlit-expanderHeader {
                padding: 0.5rem;
                font-size: 0.9rem;
            }
            
            /* Reduce padding and margins on mobile */
            .stMetric {
                padding: 0.5rem 0.25rem;
            }
            
            /* Improve button touch targets */
            .stButton > button {
                width: 100%;
                min-height: 44px;
                font-size: 1rem;
            }
            
            /* Stack selectboxes vertically on mobile */
            .stSelectbox {
                margin-bottom: 1rem;
            }
            
            /* Better chart responsiveness */
            .plotly {
                height: auto !important;
            }
        }
        
        @media (max-width: 480px) {
            /* Extra small devices */
            .stMetric {
                padding: 0.25rem;
                font-size: 0.85rem;
            }
            
            h1, h2 {
                font-size: 1.25rem;
            }
            
            .stTabs [data-baseweb="tab-list"] button {
                font-size: 0.8rem;
                padding: 0.5rem;
            }
        }
        
        /* Touch-friendly improvements across all devices */
        .stButton > button, .stDownloadButton > button {
            min-height: 40px;
            touch-action: manipulation;
        }
        
        /* Better spacing for filters on mobile */
        .stSidebar .stButton > button {
            width: 100%;
        }
        
        /* Improve table scrolling on mobile */
        .stDataFrame {
            width: 100% !important;
            overflow-x: auto;
        }
    </style>
""", unsafe_allow_html=True)

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

        # --- GROUP 6C: Load vendor PO lead times ---
        lead_time_lookup = load_vendor_po_lead_times(
            "data/Domestic Vendor POs.csv",
            "data/DOMESTIC INBOUND.csv",
            logs=st.session_state.debug_logs
        )
        st.session_state.lead_time_lookup = lead_time_lookup

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
    ("Service Level", "Backorder Report", "Inventory Management", "📈 Demand Forecasting")
)

# --- ENHANCED: Clear ALL caches and reset filters when switching reports ---
if st.session_state.get('last_active_report') != report_view:
    # Clear the year-month map cache for this report
    st.session_state[f'cached_year_month_map_{report_view}'] = {}
    # Clear the filter state cache for this report
    st.session_state[f'cached_filter_state_{report_view}'] = None
    st.session_state[f'cached_filter_changed_{report_view}'] = False
    
    # ENHANCED: Also clear the debug aggregations cache (GROUP 2 optimization)
    st.session_state['cached_debug_aggregations'] = {}
    
    # ENHANCED: Clear active filters for the NEW report to prevent filter carry-over
    # This ensures each report starts with a clean slate (no residual filters from other reports)
    st.session_state[f'active_filters_{report_view}'] = {}
    
    # Update the last active report
    st.session_state['last_active_report'] = report_view
    
    # ENHANCED: Show user feedback about the report switch (confirms cache clear to user)
    st.success(f"✨ Switched to {report_view} (filters reset, cache cleared)")

# === Caching for KPI Calculations ===
# By caching the main KPI calculations, the dashboard will feel more responsive
# when switching between radio buttons within a tab.

# ===== KPI FUNCTIONS & HELPERS =====

def display_kpis_mobile_friendly(kpi_data: dict, columns: int = 3) -> None:
    """
    Display KPIs in a mobile-responsive way using Streamlit columns.
    On mobile devices, automatically stacks vertically via CSS.
    
    Args:
        kpi_data: Dictionary with structure {label: value}
        columns: Number of columns to use (default 3 for desktop)
    """
    cols = st.columns(columns)
    for idx, (label, value) in enumerate(kpi_data.items()):
        cols[idx % columns].metric(label, value)


def calculate_trend(current_value: float, previous_value: float, metric_type: str = 'number') -> tuple[str, str]:
    """
    Calculate trend indicator and percentage change for KPI monitoring.
    
    Compares current vs previous period to show improvement/decline.
    Trends are direction-aware (higher is better for On-Time %, lower is better for DIO).
    
    Args:
        current_value: Current period metric value
        previous_value: Previous period metric value
        metric_type: Type of metric ('percentage', 'inventory', 'backorder', 'time') 
                     determines trend direction interpretation
    
    Returns:
        Tuple of (trend_symbol, percentage_change_text)
        Example: ('📈', '+5.2% from last period') or ('📉', '-3.1% from last period')
    """
    if previous_value == 0:
        return '—', 'No prior data'
    
    pct_change = ((current_value - previous_value) / abs(previous_value)) * 100
    
    # Determine if trend is good or bad based on metric type
    if metric_type == 'percentage':  # Higher is better (On-Time %)
        if pct_change > 1:
            trend_symbol = '📈'
        elif pct_change < -1:
            trend_symbol = '📉'
        else:
            trend_symbol = '➡️'
    elif metric_type == 'backorder':  # Lower is better (Days on BO)
        if pct_change < -1:
            trend_symbol = '📈'  # Improvement
        elif pct_change > 1:
            trend_symbol = '📉'  # Deterioration
        else:
            trend_symbol = '➡️'
    elif metric_type == 'inventory':  # Lower DIO is better
        if pct_change < -1:
            trend_symbol = '📈'  # Improvement
        elif pct_change > 1:
            trend_symbol = '📉'  # Deterioration
        else:
            trend_symbol = '➡️'
    else:  # Default: higher is better
        if pct_change > 1:
            trend_symbol = '📈'
        elif pct_change < -1:
            trend_symbol = '📉'
        else:
            trend_symbol = '➡️'
    
    change_text = f"{abs(pct_change):+.1f}%" if abs(pct_change) >= 0.1 else 'No change'
    return trend_symbol, change_text


def get_month_over_month_kpis(df: pd.DataFrame, current_year_month: str, previous_year_month: str, 
                              metric_columns: list) -> dict:
    """
    Calculate month-over-month KPI comparison for trend analysis (GROUP 6A).
    
    Filters data for current and previous month, then computes specified metrics
    for trend comparison.
    
    Args:
        df: Dataframe with 'year_month' column (e.g., '2024-01')
        current_year_month: Current period (e.g., '2024-01')
        previous_year_month: Previous period (e.g., '2023-12')
        metric_columns: List of metric column names to aggregate
    
    Returns:
        Dictionary with {metric_name: {'current': val, 'previous': val, 'trend': emoji, 'change': percent_str}}
    """
    result = {}
    
    current_data = df[df.get('year_month', '') == current_year_month]
    previous_data = df[df.get('year_month', '') == previous_year_month]
    
    for metric in metric_columns:
        if metric in current_data.columns:
            current_val = current_data[metric].sum() if metric in ['units_issued', 'on_time', 'backorder_qty'] else current_data[metric].mean()
            previous_val = previous_data[metric].sum() if metric in ['units_issued', 'on_time', 'backorder_qty'] else previous_data[metric].mean()
            
            trend_symbol, change_text = calculate_trend(current_val, previous_val, metric_type='percentage' if 'pct' in metric else 'number')
            result[metric] = {
                'current': current_val,
                'previous': previous_val,
                'trend': trend_symbol,
                'change': change_text
            }
    
    return result


def detect_service_anomalies(df: pd.DataFrame, sensitivity: str = 'Normal') -> dict:
    """
    Detect service level anomalies based on sensitivity level (GROUP 6B).
    
    Flags issues like: low on-time %, delivery delays, customer underperformance.
    
    Args:
        df: Service data dataframe with columns: 'on_time', 'days_to_deliver', 'customer_name'
        sensitivity: 'Conservative', 'Normal', or 'Aggressive'
    
    Returns:
        Dictionary with anomaly counts and details
    """
    thresholds = ANOMALY_THRESHOLDS.get(sensitivity, ANOMALY_THRESHOLDS['Normal'])
    anomalies = {'count': 0, 'details': [], 'critical': 0}
    
    if df.empty:
        return anomalies
    
    # Check overall on-time percentage
    overall_ontime_pct = (df['on_time'].sum() / len(df) * 100) if len(df) > 0 else 0
    if overall_ontime_pct < thresholds['service_min_ontime_pct']:
        anomalies['count'] += 1
        anomalies['critical'] += 1
        anomalies['details'].append(f"🚨 On-Time % is {overall_ontime_pct:.1f}% (threshold: {thresholds['service_min_ontime_pct']}%)")
    
    # Check for delivery delays
    avg_days = df['days_to_deliver'].mean() if len(df) > 0 else 0
    if avg_days > thresholds['service_max_days_deliver']:
        anomalies['count'] += 1
        anomalies['critical'] += 1
        anomalies['details'].append(f"🚨 Avg Delivery Time is {avg_days:.1f} days (threshold: {thresholds['service_max_days_deliver']} days)")
    
    # Check for underperforming customers
    if 'customer_name' in df.columns:
        customer_ontime = df.groupby('customer_name')['on_time'].apply(lambda x: x.mean() * 100 if len(x) > 0 else 0)
        avg_customer_ontime = customer_ontime.mean()
        underperformers = customer_ontime[customer_ontime < (avg_customer_ontime - thresholds['service_customer_underperformance'])]
        if len(underperformers) > 0:
            anomalies['count'] += len(underperformers)
            for customer, pct in underperformers.head(5).items():
                anomalies['details'].append(f"⚠️ Customer '{customer}' on-time: {pct:.1f}%")
    
    return anomalies


def detect_backorder_anomalies(df: pd.DataFrame, sensitivity: str = 'Normal') -> dict:
    """
    Detect backorder anomalies (GROUP 6B).
    
    Flags issues like: aged backorders, quantity spikes.
    
    Args:
        df: Backorder data dataframe with columns: 'days_on_backorder', 'backorder_qty'
        sensitivity: 'Conservative', 'Normal', or 'Aggressive'
    
    Returns:
        Dictionary with anomaly counts and details
    """
    thresholds = ANOMALY_THRESHOLDS.get(sensitivity, ANOMALY_THRESHOLDS['Normal'])
    anomalies = {'count': 0, 'details': [], 'critical': 0}
    
    if df.empty:
        return anomalies
    
    # Check for aged backorders
    aged_bo = df[df['days_on_backorder'] > thresholds['backorder_max_days']]
    if len(aged_bo) > 0:
        anomalies['count'] += len(aged_bo)
        anomalies['critical'] += len(aged_bo)
        anomalies['details'].append(f"🚨 {len(aged_bo)} items stuck on BO for >{thresholds['backorder_max_days']} days")
    
    # Check for backorder quantity spikes
    avg_qty = df['backorder_qty'].mean()
    qty_spike_threshold = avg_qty * (1 + thresholds['backorder_qty_spike_threshold'] / 100)
    spiked_items = df[df['backorder_qty'] > qty_spike_threshold]
    if len(spiked_items) > 0:
        anomalies['count'] += len(spiked_items)
        anomalies['details'].append(f"⚠️ {len(spiked_items)} items with abnormal BO quantities")
    
    return anomalies


def detect_inventory_anomalies(df: pd.DataFrame, sensitivity: str = 'Normal') -> dict:
    """
    Detect inventory anomalies (GROUP 6B).
    
    Flags issues like: slow-moving stock, stock-out risk.
    
    Args:
        df: Inventory data dataframe with columns: 'avg_dio', 'on_hand_qty', 'daily_demand'
        sensitivity: 'Conservative', 'Normal', or 'Aggressive'
    
    Returns:
        Dictionary with anomaly counts and details
    """
    thresholds = ANOMALY_THRESHOLDS.get(sensitivity, ANOMALY_THRESHOLDS['Normal'])
    anomalies = {'count': 0, 'details': [], 'critical': 0}
    
    if df.empty:
        return anomalies
    
    # Check for excess stock (high DIO)
    if 'avg_dio' in df.columns:
        excess_stock = df[df['avg_dio'] > thresholds['inventory_max_dio']]
        if len(excess_stock) > 0:
            anomalies['count'] += len(excess_stock)
            anomalies['details'].append(f"⚠️ {len(excess_stock)} items with DIO > {thresholds['inventory_max_dio']} days (slow movers)")
    
    # Check for stock-out risk (low days of supply)
    if 'on_hand_qty' in df.columns and 'daily_demand' in df.columns:
        df_temp = df[df['daily_demand'] > 0].copy()
        df_temp['days_supply'] = df_temp['on_hand_qty'] / df_temp['daily_demand']
        low_stock = df_temp[df_temp['days_supply'] < thresholds['inventory_min_days_supply']]
        if len(low_stock) > 0:
            anomalies['count'] += len(low_stock)
            anomalies['critical'] += len(low_stock)
            anomalies['details'].append(f"🚨 {len(low_stock)} items with <{thresholds['inventory_min_days_supply']} days supply (stock-out risk)")
    
    return anomalies


def get_service_kpis(_f_service: pd.DataFrame) -> tuple[float, float, float]:
    """
    Calculate key performance indicators for Service Level report.
    
    Computes the total units issued, on-time delivery percentage, and average 
    days to deliver from filtered service data.
    
    Args:
        _f_service: Filtered service data dataframe with columns: 
                   'units_issued', 'on_time', 'days_to_deliver'
    
    Returns:
        Tuple of (total_units, on_time_pct, avg_days_to_deliver)
    """
    if _f_service.empty:
        return 0, 0, 0
    on_time_pct = _f_service['on_time'].mean() * 100
    avg_days = _f_service['days_to_deliver'].mean()
    total_units = _f_service['units_issued'].sum()
    return total_units, on_time_pct, avg_days

def get_backorder_kpis(_f_backorder: pd.DataFrame) -> tuple[float, float, int]:
    """
    Calculate key performance indicators for Backorder Report.
    
    Computes total backorder quantity, weighted average days on backorder, 
    and count of unique sales orders with backorders.
    
    Args:
        _f_backorder: Filtered backorder data dataframe with columns:
                     'backorder_qty', 'days_on_backorder', 'sales_order'
    
    Returns:
        Tuple of (total_bo_qty, weighted_avg_days_on_bo, unique_orders)
    """
    if _f_backorder.empty:
        return 0, 0, 0
    total_bo_qty = _f_backorder['backorder_qty'].sum()
    # Use a weighted average for days on backorder to match the main KPI
    avg_bo_days = np.average(_f_backorder['days_on_backorder'], weights=_f_backorder['backorder_qty']) if total_bo_qty > 0 else 0
    unique_orders = _f_backorder['sales_order'].nunique()
    return total_bo_qty, avg_bo_days, unique_orders

def get_inventory_kpis(_f_inventory: pd.DataFrame) -> tuple[float, float]:
    """
    Calculate key performance indicators for Inventory Management report.
    
    Computes total on-hand stock and weighted average Days of Inventory (DIO)
    using top-down calculation: Total On-Hand / Total Daily Demand.
    
    Args:
        _f_inventory: Filtered inventory data dataframe with columns:
                     'on_hand_qty', 'daily_demand'
    
    Returns:
        Tuple of (total_on_hand_qty, weighted_avg_dio_days)
    """
    if _f_inventory.empty:
        return 0, 0
    
    total_on_hand = _f_inventory['on_hand_qty'].sum()
    total_daily_demand = _f_inventory['daily_demand'].sum()
    
    # --- FIX: Use top-down DIO calculation for the main KPI ---
    avg_dio = total_on_hand / total_daily_demand if total_daily_demand > 0 else 0
    return total_on_hand, avg_dio


# === GROUP 6C: Predictive Insights ===

def estimate_bo_resolution_date(days_on_backorder: float, lead_time_lookup: dict, 
                                 sku: str = None, default_horizon: int = 90) -> dict:
    """
    Estimate when backorder will be resolved based on vendor lead time (GROUP 6C).
    
    Uses historical PO lead times to forecast when BO item will be back in stock.
    Accounts for days already on backorder + remaining lead time.
    
    Args:
        days_on_backorder: Current days the item has been on BO
        lead_time_lookup: Dictionary of SKU -> lead_time_days from vendor POs
        sku: Material code (used to look up lead time)
        default_horizon: Days to assume if no lead time found (90 days)
    
    Returns:
        Dictionary with: {'estimated_days_to_resolve': int, 'confidence': str, 'based_on': str}
    """
    if sku and sku in lead_time_lookup:
        lead_time_days = lead_time_lookup[sku]['lead_time_days']
        po_count = lead_time_lookup[sku]['vendor_count']
        confidence = 'High' if po_count >= 5 else 'Medium' if po_count >= 2 else 'Low'
        based_on = f"Based on {po_count} historical POs"
    else:
        lead_time_days = default_horizon
        confidence = 'Low'
        based_on = "Default estimate (no PO history)"
    
    # Days remaining = lead time (already includes safety stock)
    days_remaining = max(0, lead_time_days - int(days_on_backorder))
    
    return {
        'estimated_days_to_resolve': days_remaining,
        'confidence': confidence,
        'based_on': based_on,
        'lead_time_base': lead_time_days
    }


def forecast_dio_trend(current_dio: float, recent_demand_trend: str = 'stable') -> dict:
    """
    Forecast DIO trend based on current demand patterns (GROUP 6C).
    
    Simple method: Compare recent vs historical demand to predict DIO direction.
    If demand increasing -> DIO will decrease (faster turnover)
    If demand decreasing -> DIO will increase (slower turnover)
    
    Args:
        current_dio: Current Days of Inventory
        recent_demand_trend: 'increasing', 'decreasing', or 'stable'
    
    Returns:
        Dictionary with: {'forecasted_dio_direction': str, 'action': str, 'rationale': str}
    """
    if recent_demand_trend == 'increasing':
        direction = '📉 Decreasing'
        action = '✅ Positive - Inventory turning over faster'
        rationale = 'Higher demand = faster inventory consumption'
    elif recent_demand_trend == 'decreasing':
        direction = '📈 Increasing'
        action = '⚠️ Monitor - Stock may accumulate'
        rationale = 'Lower demand = slower inventory turnover'
    else:
        direction = '➡️ Stable'
        action = '✅ Maintained - Current DIO expected to hold'
        rationale = 'Stable demand = stable inventory levels'
    
    return {
        'forecasted_dio_direction': direction,
        'action': action,
        'rationale': rationale
    }


# === GROUP 6D: Demand Forecasting ===

def calculate_demand_forecast(orders_df: pd.DataFrame, ma_window_days: int = 120, 
                              forecast_horizon_days: int = 90, group_by: str = 'all') -> pd.DataFrame:
    """
    Calculate demand forecast using moving average method (GROUP 6D).
    
    Uses configurable time windows (60/120/240/360 days) to calculate moving average,
    then extrapolates forward based on forecast horizon (lead time + safety stock).
    Includes confidence band (±1 std dev) around forecast to show uncertainty range.
    
    Args:
        orders_df: Orders dataframe with 'order_date' and 'ORDER_QTY' columns
        ma_window_days: Moving average window (60, 120, 240, or 360 days)
        forecast_horizon_days: How many days ahead to forecast (based on lead time)
        group_by: 'all' (overall), 'category', 'customer_name', or 'sales_org'
    
    Returns:
        Dictionary with forecast data including confidence bands
    """
    if orders_df.empty:
        return pd.DataFrame()
    
    # Ensure date column is datetime
    orders_df = orders_df.copy()
    orders_df['order_date'] = pd.to_datetime(orders_df['order_date'], errors='coerce')
    orders_df = orders_df.dropna(subset=['order_date'])
    
    # Calculate daily demand
    daily_demand = orders_df.groupby('order_date')['ORDER_QTY'].sum().reset_index()
    daily_demand.columns = ['date', 'daily_qty']
    daily_demand = daily_demand.sort_values('date')
    
    # Calculate moving average
    daily_demand['ma'] = daily_demand['daily_qty'].rolling(window=ma_window_days, min_periods=1).mean()
    
    # Calculate volatility (standard deviation) from recent data for confidence bands
    recent_residuals = (daily_demand['daily_qty'] - daily_demand['ma']).iloc[-ma_window_days:] if len(daily_demand) >= ma_window_days else (daily_demand['daily_qty'] - daily_demand['ma'])
    volatility = recent_residuals.std() if len(recent_residuals) > 1 else daily_demand['daily_qty'].std() * 0.2
    
    # Get latest MA value as baseline for forecast
    latest_ma = daily_demand['ma'].iloc[-1] if len(daily_demand) > 0 else 0
    
    # Calculate trend (simple: compare recent vs older MA)
    recent_ma = daily_demand['ma'].iloc[-30:].mean() if len(daily_demand) >= 30 else latest_ma
    older_ma = daily_demand['ma'].iloc[:-30].mean() if len(daily_demand) > 30 else latest_ma
    trend_pct = ((recent_ma - older_ma) / abs(older_ma)) * 100 if older_ma > 0 else 0
    
    # Create forecast dates
    last_date = daily_demand['date'].max()
    forecast_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_horizon_days, freq='D')
    
    # Simple linear forecast (maintain recent trend)
    trend_multiplier = 1 + (trend_pct / 100)
    forecast_qty = [latest_ma * trend_multiplier] * forecast_horizon_days
    
    # Create confidence bands (±1 std dev = ~68% confidence interval)
    forecast_upper = [latest_ma * trend_multiplier + volatility] * forecast_horizon_days
    forecast_lower = [max(0, latest_ma * trend_multiplier - volatility)] * forecast_horizon_days
    
    # Create forecast dataframe
    forecast_df = pd.DataFrame({
        'date': forecast_dates,
        'daily_qty': forecast_qty,
        'ma': forecast_qty,
        'upper_band': forecast_upper,
        'lower_band': forecast_lower,
        'type': 'forecast'
    })
    
    # Add historical marker and bands (for smooth chart transition)
    daily_demand['type'] = 'historical'
    daily_demand['upper_band'] = daily_demand['daily_qty']
    daily_demand['lower_band'] = daily_demand['daily_qty']
    
    # Combine
    combined = pd.concat([daily_demand, forecast_df], ignore_index=True)
    
    return {
        'data': combined,
        'latest_daily_avg': latest_ma,
        'trend': 'Increasing' if trend_pct > 1 else 'Decreasing' if trend_pct < -1 else 'Stable',
        'trend_pct': trend_pct,
        'ma_window': ma_window_days,
        'forecast_horizon': forecast_horizon_days,
        'volatility': volatility
    }


def aggregate_forecast_by_dimension(orders_df: pd.DataFrame, ma_window_days: int = 120,
                                    dimension: str = 'category') -> pd.DataFrame:
    """
    Aggregate demand forecast by dimension (Category/Customer/Sales Org) (GROUP 6D).
    
    Groups orders by specified dimension and calculates separate moving averages
    for each group to show demand patterns by business segment.
    
    Args:
        orders_df: Orders dataframe
        ma_window_days: Moving average window days
        dimension: 'category', 'customer_name', or 'sales_org'
    
    Returns:
        DataFrame with forecast grouped by dimension
    """
    if orders_df.empty or dimension not in orders_df.columns:
        return pd.DataFrame()
    
    orders_df = orders_df.copy()
    orders_df['order_date'] = pd.to_datetime(orders_df['order_date'], errors='coerce')
    
    # Group by dimension and date
    grouped = orders_df.groupby(['order_date', dimension])['ORDER_QTY'].sum().reset_index()
    grouped.columns = ['date', dimension, 'qty']
    grouped = grouped.sort_values(['date', dimension])
    
    # Calculate MA for each dimension group
    grouped['ma'] = grouped.groupby(dimension)['qty'].transform(
        lambda x: x.rolling(window=ma_window_days, min_periods=1).mean()
    )
    
    # Get top 10 by total demand
    top_dimensions = grouped.groupby(dimension)['qty'].sum().nlargest(10).index
    grouped = grouped[grouped[dimension].isin(top_dimensions)]
    
    return grouped


def remove_demand_anomalies(daily_demand_df: pd.DataFrame, sensitivity: str = 'Normal') -> pd.DataFrame:
    """
    Remove statistical anomalies (outliers) from daily demand data (GROUP 6D Enhancement).
    
    Uses interquartile range (IQR) method to identify and remove non-recurring demand spikes/drops.
    Anomalies are replaced with interpolated values based on surrounding data.
    
    Args:
        daily_demand_df: DataFrame with 'date' and 'daily_qty' columns
        sensitivity: 'Aggressive' (only extreme outliers), 'Normal' (balanced), or 'Conservative' (more removal)
    
    Returns:
        DataFrame with anomalies removed and interpolated
    """
    if daily_demand_df.empty or 'daily_qty' not in daily_demand_df.columns:
        return daily_demand_df
    
    df = daily_demand_df.copy()
    
    # Define IQR multipliers for each sensitivity level
    # Higher multiplier = fewer anomalies removed (only extreme outliers)
    # Lower multiplier = more anomalies removed (catches more deviations)
    iqr_multipliers = {
        'Aggressive': 3.0,      # Only remove extreme outliers (3× IQR)
        'Normal': 1.5,          # Balanced (1.5× IQR) - default
        'Conservative': 0.75    # Remove more deviations (0.75× IQR)
    }
    
    multiplier = iqr_multipliers.get(sensitivity, 1.5)
    
    # Calculate quartiles and IQR
    Q1 = df['daily_qty'].quantile(0.25)
    Q3 = df['daily_qty'].quantile(0.75)
    IQR = Q3 - Q1
    
    # Define outlier bounds
    lower_bound = Q1 - (multiplier * IQR)
    upper_bound = Q3 + (multiplier * IQR)
    
    # Mark anomalies
    anomaly_mask = (df['daily_qty'] < lower_bound) | (df['daily_qty'] > upper_bound)
    anomaly_count = anomaly_mask.sum()
    
    # Replace anomalies with NaN for interpolation
    df.loc[anomaly_mask, 'daily_qty'] = np.nan
    
    # Interpolate missing values (linear interpolation preserves trend)
    df['daily_qty'] = df['daily_qty'].interpolate(method='linear', limit_direction='both')
    
    # Store metadata for user feedback
    df.attrs['anomalies_removed'] = anomaly_count
    df.attrs['bounds'] = {'lower': lower_bound, 'upper': upper_bound}
    
    return df


# === Caching for Aggregated Chart Data ===
# This second layer of caching stores the results of the groupby operations.
# It makes the dashboard feel instantaneous when switching between tabs or KPIs
# because the expensive aggregations don't need to be re-calculated.

def get_service_customer_data(_f_service: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate service data by customer (top 10 by units).
    
    Groups filtered service data by customer and calculates total units,
    on-time percentage, and average days to deliver. Returns top 10 customers.
    
    Args:
        _f_service: Filtered service data dataframe
    
    Returns:
        DataFrame indexed by customer_name with columns: 
        total_units, on_time_pct, avg_days (sorted by units desc)
    """
    cust_svc = _f_service.groupby('customer_name').agg(
        total_units=('units_issued', 'sum'),
        on_time_pct=('on_time', 'mean'),
        avg_days=('days_to_deliver', 'mean')
    ).sort_values(by='total_units', ascending=False).head(10)
    cust_svc['on_time_pct'] *= 100
    return cust_svc

def get_service_monthly_data(_f_service: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate service data by month.
    
    Groups filtered service data by month and calculates total units,
    on-time percentage, and average days to deliver.
    
    Args:
        _f_service: Filtered service data dataframe with columns:
                   'ship_month_num', 'ship_month', 'units_issued', 'on_time', 'days_to_deliver'
    
    Returns:
        DataFrame with columns: ship_month_num, ship_month, total_units, 
        on_time_pct, avg_days (sorted by month)
    """
    month_svc = _f_service.groupby(['ship_month_num', 'ship_month']).agg(
        total_units=('units_issued', 'sum'),
        on_time_pct=('on_time', 'mean'),
        avg_days=('days_to_deliver', 'mean')
    ).sort_index().reset_index()
    month_svc['on_time_pct'] *= 100
    return month_svc

def get_backorder_customer_data(_f_backorder: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate backorder data by customer (top 10 by backorder qty).
    
    Groups filtered backorder data by customer and calculates total backorder
    quantity and weighted average days on backorder. Returns top 10 customers.
    
    Args:
        _f_backorder: Filtered backorder data dataframe with columns:
                     'customer_name', 'backorder_qty', 'days_on_backorder'
    
    Returns:
        DataFrame indexed by customer_name with columns:
        total_bo_qty, avg_days_on_bo (sorted by qty desc)
    """
    if _f_backorder.empty:
        return pd.DataFrame()
    
    def weighted_avg(x):
        weights = _f_backorder.loc[x.index, 'backorder_qty']
        return np.average(x, weights=weights) if weights.sum() > 0 else x.mean()

    return _f_backorder.groupby('customer_name').agg(
        total_bo_qty=('backorder_qty', 'sum'),
        avg_days_on_bo=('days_on_backorder', weighted_avg)
    ).sort_values(by='total_bo_qty', ascending=False).head(10)

def get_backorder_item_data(_f_backorder: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate backorder data by item/SKU (top 10 by backorder qty).
    
    Groups filtered backorder data by SKU and product name, calculating total
    backorder quantity and weighted average days on backorder. Returns top 10 items.
    
    Args:
        _f_backorder: Filtered backorder data dataframe with columns:
                     'sku', 'product_name', 'backorder_qty', 'days_on_backorder'
    
    Returns:
        DataFrame with columns: sku, product_name, total_bo_qty, avg_days_on_bo
        (sorted by total_bo_qty desc)
    """
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

def get_inventory_category_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate inventory data by category for the chart.
    
    Groups inventory data by category and calculates total on-hand stock
    and Days of Inventory (DIO) using top-down calculation method:
    DIO = Total On-Hand Qty / Total Daily Demand (per category).
    
    Args:
        df: Inventory data dataframe with columns:
           'category', 'on_hand_qty', 'daily_demand'
    
    Returns:
        DataFrame indexed by category with columns:
        total_on_hand, total_daily_demand, avg_dio (sorted by on_hand desc)
    """
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
    Apply a dictionary of filters to a dataframe efficiently.
    
    Builds a single boolean mask from all filters and applies it once,
    rather than filtering sequentially. Supports both multiselect (list) 
    and single select (string) filters.
    
    Args:
        df: Source dataframe to filter
        filters: Dict mapping column names to filter values.
                For multiselect: value should be a list (uses .isin())
                For single select: value should be a string (uses equality)
    
    Returns:
        Filtered dataframe with only rows matching all filter criteria
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

# --- LAZY FILTER LOADING: Cache filtered data separately from raw data ---
def get_lazy_filtered_data(raw_df: pd.DataFrame, report_view: str, 
                           f_year, f_month, f_customer, f_category, f_material, 
                           f_sales_org, f_order_type, f_order_reason=None) -> tuple:
    """
    Implement lazy filter loading pattern to avoid data reloads on filter widget changes.
    
    Strategy:
    - Stores applied_filters_{report_view} = filters last time "Apply Filters" button was clicked
    - Compares current widget state to applied_filters
    - If different, returns raw_df and shows message
    - If same, returns filtered_df
    
    Args:
        raw_df: Unfiltered data for this report
        report_view: Report name (e.g., "Service Level", "Backorder Report")
        f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type, f_order_reason: Current widget values
    
    Returns:
        Tuple of (dataframe_to_display, bool_indicating_pending_filters)
    """
    if f_order_reason is None:
        f_order_reason = []
    
    # Get the filters that were actually applied (saved on button click)
    applied_filters = st.session_state.get(f'applied_filters_{report_view}', {})
    
    # Build current widget state
    current_widget_state = {
        'order_year': f_year,
        'order_month': f_month,
        'customer_name': f_customer,
        'category': f_category,
        'product_name': f_material,
        'sales_org': f_sales_org,
        'order_type': f_order_type,
        'order_reason': f_order_reason,
    }
    
    # Check if user has made changes to filters since last apply
    filters_match = (current_widget_state == applied_filters)
    
    if filters_match and applied_filters:
        # Use previously applied filters - no refresh on screen
        return apply_filters(raw_df, applied_filters), False
    else:
        # Show unfiltered data until user clicks Apply Filters
        # has_pending = True if user has made filter changes OR had filters before
        has_pending = bool(applied_filters) or any(
            v for v in current_widget_state.values() 
            if v and v != 'All' and v != []
        )
        return raw_df, has_pending

# --- Helper function to safely get unique values ---
def get_unique_values(df: pd.DataFrame, column: str) -> list:
    """
    Get sorted list of unique values from a dataframe column.
    
    Retrieves unique values from the specified column, excluding 'Unknown'
    values, and returns them sorted alphabetically as strings.
    
    Args:
        df: Source dataframe
        column: Column name to extract unique values from
    
    Returns:
        Sorted list of unique values (excluding 'Unknown')
    """
    if not df.empty and column in df.columns:
        return sorted(list(df[df[column] != 'Unknown'][column].astype(str).unique()))
    return []

# --- Org #2: Helper function for consistent DataFrame formatting ---
def format_dataframe_number(value: float, format_type: str = 'currency') -> str:
    """
    Apply consistent number formatting to dataframe values.
    
    Returns the format string for the specified format type from the
    centralized FORMATS dictionary.
    
    Args:
        value: Numeric value to format (used for type indication)
        format_type: Format type key from FORMATS dict.
                    Options: 'currency', 'percentage', 'decimal_1', 'integer'
    
    Returns:
        Format string (e.g., '{:,.0f}' for currency)
    """
    fmt = FORMATS.get(format_type, FORMATS['decimal_1'])
    return fmt

def create_dataframe_format_dict(columns: list, format_types: dict) -> dict:
    """
    Create a format dictionary for dataframe styling.
    
    Builds a dictionary mapping column names to format strings from the
    centralized FORMATS dictionary. Used with df.style.format().
    
    Args:
        columns: List of column names to format
        format_types: Dict mapping column names to format type keys 
                     (from FORMATS dict). Options: 'currency', 'percentage', 
                     'decimal_1', 'integer'
    
    Returns:
        Dict ready for df.style.format() 
        (e.g., {'total_units': '{:,.0f}', 'pct': '{:.1f}%'})
    """
    return {col: FORMATS.get(format_types.get(col, 'decimal_1')) 
            for col in columns if col in format_types}

# --- Org #3: Helper function for multiselect filter widgets ---
def create_multiselect_filter(label: str, df: pd.DataFrame, column: str, 
                              key_suffix: str) -> list:
    """
    Create a multiselect filter widget with consistent styling.
    
    DRY helper that standardizes multiselect filter creation across the
    dashboard. Automatically extracts unique values from the specified
    column and renders them in the sidebar.
    
    Args:
        label: Display label for the filter widget
        df: Source dataframe to extract unique values from
        column: Column name to get unique values from
        key_suffix: Unique key suffix for widget identification.
                   Used by Streamlit to maintain widget state.
    
    Returns:
        List of selected values from the multiselect widget.
        Returns empty list if user hasn't selected anything.
    """
    return st.sidebar.multiselect(
        label,
        get_unique_values(df, column),
        key=key_suffix
    )

# --- GROUP 4D: Better error messaging and validation helper ---
def get_data_quality_summary(df: pd.DataFrame) -> dict:
    """
    Generate a data quality summary for validation and error reporting.
    
    Analyzes a dataframe for common data quality issues including missing
    values, empty dataframes, and data type issues.
    
    Args:
        df: Dataframe to analyze
    
    Returns:
        Dict with keys: 'is_empty', 'row_count', 'null_counts', 'issues'
    """
    if df.empty:
        return {'is_empty': True, 'row_count': 0, 'null_counts': {}, 'issues': ['Dataframe is empty']}
    
    null_counts = df.isnull().sum()
    issues = []
    
    # Check for columns with all null values
    for col in df.columns:
        if null_counts[col] == len(df):
            issues.append(f"Column '{col}' is completely empty")
        elif null_counts[col] > len(df) * 0.5:
            issues.append(f"Column '{col}' is {null_counts[col]/len(df)*100:.0f}% empty")
    
    return {
        'is_empty': False,
        'row_count': len(df),
        'null_counts': null_counts[null_counts > 0].to_dict(),
        'issues': issues
    }

# --- GROUP 4C: Better empty state messaging helper ---
def show_empty_state_message(report_name: str, filter_count: int = 0) -> None:
    """
    Display a helpful empty state message with suggestions.
    
    Args:
        report_name: Name of the report (e.g., 'Service Level')
        filter_count: Number of active filters
    """
    if filter_count > 0:
        st.warning("❌ No data matches your filter criteria.\\n\\n**Suggestion:** Try clearing filters or adjusting your selections.", icon="⚠️")
    else:
        st.error(f"❌ No {report_name} data available in the dataset.", icon="🚫")
        st.info("💡 **Troubleshooting:** Check the Debug Log tab for data quality issues.")

# --- NEW: Conditional Filters based on Report View ---
st.sidebar.header("Filters")

# --- GROUP 4B: Clear All Filters button with tooltip ---
if st.sidebar.button("🔄 Reset All Filters", use_container_width=True, help="Clear all filter selections and return to full dataset"):
    st.session_state[f'active_filters_{report_view}'] = {}
    st.rerun()

st.sidebar.divider()

# --- GROUP 6B: Anomaly Detection Sensitivity Level ---
anomaly_sensitivity = st.sidebar.selectbox(
    "🔍 Anomaly Sensitivity",
    options=["Conservative 🔒", "Normal ⚙️", "Aggressive 🚀"],
    index=1,
    help="Conservative: Catch more issues | Normal: Balanced (default) | Aggressive: Only critical issues"
)
# Extract sensitivity level name
sensitivity_level = anomaly_sensitivity.split()[0]

st.sidebar.divider()

if report_view == "Inventory Management":
    # --- Inventory-specific filters: Material attributes and Category attributes ---
    st.sidebar.info("📦 Filter inventory by item and category attributes. Ordered by: Material → Category → Alphabetical")
    f_inventory = inventory_analysis_data
    
    # Set other filtered dataframes to their unfiltered state so the app doesn't break
    f_service = service_data
    f_backorder = backorder_data
    
    # Initialize filter variables for Inventory (only material + category attributes)
    f_year = "All"
    f_month = "All"
    f_customer = []
    f_sales_org = []
    f_order_type = []
    f_order_reason = []
    
    # --- Material Attribute Filters (ordered by material attributes first) ---
    f_material = create_multiselect_filter("Material Number:", inventory_analysis_data, 'Material Number', "inv_mat_num")
    f_material_desc = create_multiselect_filter("Material Description:", inventory_analysis_data, 'Material Description', "inv_mat_desc")
    f_pop_material = create_multiselect_filter("POP Material (POP/Non-POP):", inventory_analysis_data, 'POP Material: POP/Non POP', "inv_pop_material")
    f_plm_level2 = create_multiselect_filter("PLM Level 2 (Wholesale/Retail):", inventory_analysis_data, 'PLM: Level Classification 2 (Attribute D_TMKLVL2CLS)', "inv_plm_l2")
    f_expiration = create_multiselect_filter("Expiration Flag:", inventory_analysis_data, 'POP Calculated Attributes: Expiration Flag', "inv_exp_flag")
    f_vendor = create_multiselect_filter("Vendor Name:", inventory_analysis_data, 'POP Last Purchase: Vendor Name', "inv_vendor")
    
    # --- Category Attribute Filters (ordered after material) ---
    f_category = create_multiselect_filter("Category:", inventory_analysis_data, 'category', "inv_category")
    f_stock_category = create_multiselect_filter("Stock Category Description:", inventory_analysis_data, 'Stock Category: Description', "inv_stock_cat")
    
    # Apply inventory-specific filters
    if st.sidebar.button("Apply Filters", use_container_width=True, type="primary"):
        filter_dict = {
            'order_year': "All",
            'order_month': "All",
            'customer_name': [],
            'category': f_category,
            'product_name': [],
            'sales_org': [],
            'order_type': [],
            'order_reason': [],
            'material_number': f_material,
            'material_description': f_material_desc,
            'pop_material': f_pop_material,
            'plm_level2': f_plm_level2,
            'expiration_flag': f_expiration,
            'vendor_name': f_vendor,
            'stock_category': f_stock_category
        }
        st.session_state[f'applied_filters_{report_view}'] = filter_dict
        st.session_state[f'active_filters_{report_view}'] = filter_dict
        st.success("✅ Inventory filters applied!")

else:
    # --- Global Filters for Service and Backorder Reports ---
    # --- NEW: Determine the correct source dataframe for filters ---
    if report_view == "Service Level":
        filter_source_df = service_data
    elif report_view == "Backorder Report":
        filter_source_df = backorder_data
    elif report_view == "📈 Demand Forecasting":
        # For Demand Forecasting, use orders data enriched with category from master data
        try:
            from data_loader import load_orders_item_lookup, load_master_data
            from utils import enrich_orders_with_category
            
            filter_source_df = load_orders_item_lookup(ORDERS_FILE_PATH)[1]  # Get the dataframe part
            
            # Enrich with category ONLY for this report's filter source
            master_data = load_master_data(MASTER_DATA_FILE_PATH)[1]
            if not master_data.empty:
                filter_source_df = enrich_orders_with_category(filter_source_df, master_data)
        except Exception as e:
            st.warning(f"Could not load orders data for filters: {e}")
            filter_source_df = pd.DataFrame()
    else:
        filter_source_df = pd.DataFrame()

    # --- NEW: Generate filter options on-the-fly from the correct source (with caching - Perf #2) ---
    # Year/Month filters only for Service Level and Backorder (not Demand Forecasting)
    all_years = []
    year_month_map = {}
    
    if report_view != "📈 Demand Forecasting":
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
    else:
        # Demand Forecasting uses all historical data for better trend calculation
        f_year = "All"
        f_month = "All"
        st.sidebar.info("📈 Demand Forecasting uses all historical data for accurate trend analysis. Filter by Customer, Category, or Product instead.")

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
        # Store BOTH the applied filters (for comparison) AND widget values (for current state)
        # applied_filters = last saved state (what is currently rendered)
        # active_filters = widget values saved for lazy loading comparison
        filter_dict = {
            'order_year': f_year,
            'order_month': f_month,
            'customer_name': f_customer,
            'category': f_category,
            'product_name': f_material,
            'sales_org': f_sales_org,
            'order_type': f_order_type,
            'order_reason': f_order_reason if 'f_order_reason' in locals() else []
        }
        st.session_state[f'applied_filters_{report_view}'] = filter_dict  # Filters currently rendered
        st.session_state[f'active_filters_{report_view}'] = filter_dict   # Filters to compare against

# === GROUP 6D: Demand Forecasting Report ===
if report_view == "📈 Demand Forecasting":
    """
    === BUSINESS LOGIC (GROUP 6D) ===
    DATA SOURCES:
    - ORDERS.csv: ALL customer orders (shipped + open/pending)
      → Primary source for demand forecasting (historical demand signal)
      → Columns: order_date (header-level), ordered_qty (line-level)
    - DELIVERIES.csv: ALL outbound shipments from warehouse
      → Used for service level metrics, not forecasting
    - backorder_data: Derived data showing open/unshipped quantities
      → Used for backorder reporting, NOT for demand forecasting
    
    FORECASTING APPROACH:
    1. Source: Use ORDERS.csv (all orders) as demand signal
    2. Method: Moving average (60/120/240/360 days) + trend extrapolation
    3. Horizon: Dynamic based on vendor lead times, fallback to 90 days
    4. Result: Historical + Forecasted daily demand with trend analysis
    """
    
    st.header("📈 Demand Forecasting & Planning")
    st.markdown("Forecast future demand based on historical order trends and vendor lead times.")
    
    # Get lead time lookup
    lead_time_lookup = st.session_state.get('lead_time_lookup', {})
    
    # Initialize forecast_df BEFORE try-except to prevent undefined variable errors
    forecast_df = pd.DataFrame()
    
    # Configuration options in sidebar
    col_forecast_1, col_forecast_2, col_forecast_3 = st.columns(3)
    
    with col_forecast_1:
        ma_window = st.selectbox(
            "📊 Moving Average Window",
            options=[60, 120, 240, 360],
            index=1,
            help="Use 60 days for short-term trend, 360 for long-term"
        )
    
    with col_forecast_2:
        group_dimension = st.selectbox(
            "📂 Group By",
            options=['Overall', 'Category', 'Customer', 'Sales Org'],
            help="View demand by different business dimensions"
        )
    
    with col_forecast_3:
        auto_horizon = st.checkbox(
            "🎯 Auto Horizon",
            value=True,
            help="Use vendor lead times for forecast horizon"
        )
    
    # --- NEW: Anomaly Removal Settings (Statistical Outlier Detection) ---
    st.divider()
    st.subheader("📊 Data Cleaning & Anomaly Removal")
    st.markdown("Remove statistical anomalies (one-time spikes/drops) from forecast")
    
    col_anom_1, col_anom_2 = st.columns(2)
    
    with col_anom_1:
        remove_anomalies = st.checkbox(
            "🔍 Remove Statistical Anomalies",
            value=False,
            help="Filter out non-recurring demand spikes/drops based on statistical deviation"
        )
    
    with col_anom_2:
        if remove_anomalies:
            anomaly_sensitivity = st.selectbox(
                "📈 Sensitivity Level",
                options=['Aggressive 🚀', 'Normal ⚙️', 'Conservative 🔒'],
                index=1,
                help="Aggressive: Remove extreme outliers only | Normal: Balanced | Conservative: Remove more deviations"
            )
        else:
            anomaly_sensitivity = None
    # Note: Sourced from ORDERS.csv via load_orders_item_lookup in load_all_data()
    orders_item_data = st.session_state.get('master_data', pd.DataFrame())  # This gets populated during data load
    
    # Since we need the full orders data with order dates, load it from session if available
    # Otherwise fall back to showing a message
    try:
        # Try to get orders data - this is aggregated order-level data with order_date and ordered_qty
        # Re-load from source if not in session state
        from data_loader import load_orders_item_lookup, load_master_data
        from utils import enrich_orders_with_category
        
        orders_data = load_orders_item_lookup(ORDERS_FILE_PATH)[1]  # Get the dataframe part
        
        # Load master data to enrich orders with category information
        master_data = load_master_data(MASTER_DATA_FILE_PATH)[1]  # Get the dataframe part
        
        # Enrich orders with category from master data (required for category filtering)
        if not master_data.empty:
            orders_data = enrich_orders_with_category(orders_data, master_data)
        
        if orders_data.empty:
            st.warning("No orders data available for forecasting.")
        else:
            try:
                # --- LAZY FILTER LOADING: Apply filters only when "Apply Filters" is clicked ---
                orders_data_filtered, has_pending_filters = get_lazy_filtered_data(
                    orders_data, report_view,
                    f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type
                )
                
                # Show active filters indicator
                active_filter_count = len([v for v in st.session_state.get(f'applied_filters_{report_view}', {}).values() 
                                          if v and v != 'All' and v != []])
                if active_filter_count > 0:
                    st.info(f"📊 Forecast filtered by {active_filter_count} criterion/criteria - Click 'Apply Filters' to change")
                
                if has_pending_filters:
                    st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the forecast.")
                
                if orders_data_filtered.empty:
                    st.warning("⚠️ No orders match the selected filters. Try adjusting your filter selections.")
                else:
                    # Determine forecast horizon
                    if auto_horizon:
                        avg_lead_time = np.mean([v['lead_time_days'] for v in lead_time_lookup.values()]) if lead_time_lookup else 90
                        forecast_horizon = int(avg_lead_time)
                    else:
                        forecast_horizon = 90
                    
                    # Prepare orders data for forecasting (ensure column names match calculate_demand_forecast expectations)
                    # Expected columns: order_date, ORDER_QTY (or ordered_qty from load_orders_item_lookup)
                    if 'ordered_qty' in orders_data_filtered.columns and 'order_date' in orders_data_filtered.columns:
                        # Rename for compatibility with calculate_demand_forecast function
                        forecast_input = orders_data_filtered[['order_date', 'ordered_qty']].copy()
                        forecast_input.columns = ['order_date', 'ORDER_QTY']
                        
                        forecast_result = calculate_demand_forecast(
                            forecast_input,
                            ma_window_days=ma_window,
                            forecast_horizon_days=forecast_horizon,
                            group_by=group_dimension.lower()
                        )
                        
                        if isinstance(forecast_result, dict):
                            forecast_df = forecast_result['data']
                            
                            # --- Apply anomaly removal if enabled ---
                            if remove_anomalies and anomaly_sensitivity:
                                try:
                                    # Extract sensitivity level (remove emoji for function call)
                                    sensitivity_level = anomaly_sensitivity.split()[0]  # Gets 'Aggressive', 'Normal', or 'Conservative'
                                    
                                    # Get historical data only (don't modify forecast)
                                    historical_data = forecast_df[forecast_df['type'] == 'historical'].copy()
                                    forecast_data_part = forecast_df[forecast_df['type'] == 'forecast'].copy()
                                    
                                    # Check if historical data exists and has required columns
                                    if not historical_data.empty and 'daily_qty' in historical_data.columns:
                                        # Apply anomaly removal to historical data
                                        historical_cleaned = remove_demand_anomalies(historical_data, sensitivity=sensitivity_level)
                                        
                                        # Recalculate metrics with cleaned data
                                        anomalies_found = historical_cleaned.attrs.get('anomalies_removed', 0)
                                        bounds = historical_cleaned.attrs.get('bounds', {})
                                        
                                        # Show anomaly removal info
                                        if anomalies_found > 0:
                                            st.info(f"✅ Removed {anomalies_found} statistical anomalies ({sensitivity_level} sensitivity)")
                                            with st.expander("📊 Anomaly Details"):
                                                sensitivity_idx = {'Aggressive': 0, 'Normal': 1, 'Conservative': 2}.get(sensitivity_level, 1)
                                                multiplier_map = ['3.0×', '1.5×', '0.75×']
                                                st.write(f"**Lower Bound:** {bounds.get('lower', 'N/A'):.0f} units")
                                                st.write(f"**Upper Bound:** {bounds.get('upper', 'N/A'):.0f} units")
                                                st.write(f"**Method:** Interquartile Range (IQR) with {multiplier_map[sensitivity_idx]} multiplier")
                                        
                                        # Rebuild forecast_df with cleaned historical data
                                        forecast_df = pd.concat([historical_cleaned, forecast_data_part], ignore_index=True)
                                    else:
                                        st.warning("⚠️ Could not apply anomaly removal: insufficient historical data")
                                except Exception as e:
                                    st.error(f"❌ Error removing anomalies: {str(e)}")
                                    # Continue with unfiltered forecast
                            
                            st.metric("Avg Daily Demand (Moving Avg)", f"{forecast_result['latest_daily_avg']:.0f} units/day")
                            st.metric("Trend", f"{forecast_result['trend']} ({forecast_result['trend_pct']:+.1f}%)")
                            st.metric("Forecast Horizon", f"{forecast_result['forecast_horizon']} days")
                            
                            st.divider()
                            
                            # Plot forecast
                            st.subheader("Demand Trend & Forecast (with Confidence Band)")
                            
                            # Prepare data for visualization
                            historical = forecast_df[forecast_df['type'] == 'historical'].tail(365)
                            forecast_data = forecast_df[forecast_df['type'] == 'forecast']
                            
                            if not historical.empty and not forecast_data.empty:
                                fig = go.Figure()
                                
                                # Add historical demand
                                fig.add_trace(go.Scatter(
                                    x=historical['date'],
                                    y=historical['daily_qty'],
                                    name='Historical Demand',
                                    mode='lines',
                                    line=dict(color='blue', width=2)
                                ))
                                
                                # Add historical moving average
                                fig.add_trace(go.Scatter(
                                    x=historical['date'],
                                    y=historical['ma'],
                                    name=f'Moving Avg ({ma_window}d)',
                                    mode='lines',
                                    line=dict(color='green', width=2, dash='dash')
                                ))
                                
                                # Add forecast line
                                fig.add_trace(go.Scatter(
                                    x=forecast_data['date'],
                                    y=forecast_data['daily_qty'],
                                    name='Forecast',
                                    mode='lines',
                                    line=dict(color='orange', width=2, dash='dot')
                                ))
                                
                                # Add upper confidence band
                                fig.add_trace(go.Scatter(
                                    x=forecast_data['date'],
                                    y=forecast_data['upper_band'],
                                    name='Upper Band (+1σ)',
                                    mode='lines',
                                    line=dict(width=0),
                                    showlegend=False
                                ))
                                
                                # Add lower confidence band and fill between
                                fig.add_trace(go.Scatter(
                                    x=forecast_data['date'],
                                    y=forecast_data['lower_band'],
                                    name='Confidence Band (±1σ)',
                                    mode='lines',
                                    line=dict(width=0),
                                    fillcolor='rgba(255, 165, 0, 0.15)',
                                    fill='tonexty'
                                ))
                                
                                fig.update_layout(height=CHART_HEIGHT_LARGE, hovermode='x unified', margin=CHART_MARGIN)
                                fig.update_xaxes(title_text="Date")
                                fig.update_yaxes(title_text="Daily Demand (Units)")
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Show forecast summary with volatility
                                st.subheader("Forecast Summary")
                                col_summary_1, col_summary_2, col_summary_3, col_summary_4 = st.columns(4)
                                recent_avg = historical['daily_qty'].tail(30).mean()
                                historical_avg = historical['daily_qty'].mean()
                                forecast_avg = forecast_data['daily_qty'].mean()
                                volatility = forecast_result.get('volatility', 0)
                                
                                with col_summary_1:
                                    st.metric("Recent Avg (30d)", f"{recent_avg:.0f}", f"{((recent_avg/historical_avg - 1)*100):+.1f}%")
                                with col_summary_2:
                                    st.metric("Historical Avg", f"{historical_avg:.0f}")
                                with col_summary_3:
                                    st.metric("Forecast Avg", f"{forecast_avg:.0f}")
                                with col_summary_4:
                                    st.metric("Volatility (±σ)", f"{volatility:.0f} units")
                            else:
                                st.warning("Insufficient data to generate forecast visualization.")

                        else:
                            st.warning("Forecast calculation did not return expected data structure.")
                    else:
                        st.error("Orders data missing required columns (order_date, ordered_qty).")
                    
            except Exception as e:
                st.error(f"Error generating forecast: {str(e)[:150]}")
                st.info("Check the Debug Log for data quality issues.")
                st.write(f"Details: {str(e)}")
    
    except Exception as e:
        st.error(f"Error loading orders data: {str(e)[:150]}")
        st.info("Unable to load ORDERS.csv for forecasting.")
    
    # Export options - only show if forecast was successfully calculated
    st.divider()
    st.subheader("Export Forecast Data")
    if not forecast_df.empty:
        export_dict = {'Demand_Forecast': (forecast_df, False)}
        try:
            excel_export = get_filtered_data_as_excel(export_dict)
            st.download_button(
                label="📥 Download Forecast as Excel",
                data=excel_export,
                file_name=f"Demand_Forecast_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
            )
        except Exception as e:
            st.warning(f"Could not generate export: {e}")
    else:
        st.info("Run the forecast above to enable data export.")

else:
    # === Tabbed Interface for standard reports ===
    tab_service, tab_debug = st.tabs([
        f"{report_view}", 
        "Debug Log" 
    ])


if report_view == "Service Level":
    # --- LAZY FILTER LOADING: Apply filters only when "Apply Filters" is clicked ---
    f_service, has_pending_filters = get_lazy_filtered_data(
        service_data, report_view, 
        f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type
    )

    # --- Set other dataframes to their unfiltered state ---
    f_backorder = backorder_data
    f_inventory = inventory_analysis_data

    # --- Tab 1: Service Level ---
    with tab_service:
        # Show message if filters have been changed but not applied
        if has_pending_filters:
            st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the report.")

        st.header("Service Level Performance (Shipped Orders)")
        dfs_to_export = {} # Initialize here
        if f_service.empty:
            active_filter_count = len([v for v in st.session_state.get(f'active_filters_{report_view}', {}).values() if v and v != 'All'])
            show_empty_state_message("Service Level", active_filter_count)
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
            
            # --- GROUP 6B: Display Service Level Anomalies ---
            service_anomalies = detect_service_anomalies(f_service, sensitivity_level)
            if service_anomalies['count'] > 0:
                col_anom_left, col_anom_right = st.columns([1, 3])
                with col_anom_left:
                    st.metric("🚨 Issues Detected", service_anomalies['count'])
                with col_anom_right:
                    with st.expander(f"View {service_anomalies['count']} Anomalies"):
                        for detail in service_anomalies['details']:
                            st.write(detail)
            
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
                        st.warning("❌ No customer data available for charting. Check your filters or the Debug Log for data quality issues.")
                    else:
                        # Validate required columns before rendering
                        required_cols = ['total_units', kpi_col]
                        missing_cols = [col for col in required_cols if col not in cust_svc.columns]
                        if missing_cols:
                            st.error(f"❌ Missing required data columns: {', '.join(missing_cols)}")
                        else:
                            fig = make_subplots(specs=[[{"secondary_y": True}]])
                            fig.add_trace(go.Bar(x=cust_svc.index, y=cust_svc['total_units'], name="Units Issued"), secondary_y=False)
                            fig.add_trace(go.Scatter(x=cust_svc.index, y=cust_svc[kpi_col], name=kpi_name, mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                            fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN)
                            fig.update_yaxes(title_text="Units Issued", secondary_y=False)
                            fig.update_yaxes(title_text=kpi_name, secondary_y=True, range=y_range)
                            st.plotly_chart(fig, use_container_width=True)
                except KeyError as e:
                    st.error(f"❌ Missing data column in customer analysis: {str(e)[:50]}")
                except Exception as e:
                    st.error(f"❌ Error generating customer chart: {str(e)[:100]}")
                
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
                        st.warning("❌ No monthly data available for charting. Check your filters or the Debug Log for data quality issues.")
                    else:
                        # Validate required columns before rendering
                        required_cols = ['ship_month', 'total_units', kpi_col]
                        missing_cols = [col for col in required_cols if col not in month_svc.columns]
                        if missing_cols:
                            st.error(f"❌ Missing required data columns: {', '.join(missing_cols)}")
                        else:
                            fig = make_subplots(specs=[[{"secondary_y": True}]])
                            fig.add_trace(go.Bar(x=month_svc['ship_month'], y=month_svc['total_units'], name="Units Issued"), secondary_y=False)
                            fig.add_trace(go.Scatter(x=month_svc['ship_month'], y=month_svc[kpi_col], name=kpi_name, mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                            fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN)
                            fig.update_yaxes(title_text="Units Issued", secondary_y=False)
                            fig.update_yaxes(title_text=kpi_name, secondary_y=True, range=y_range)
                            st.plotly_chart(fig, use_container_width=True)
                except KeyError as e:
                    st.error(f"❌ Missing data column in monthly analysis: {str(e)[:50]}")
                except Exception as e:
                    st.error(f"❌ Error generating monthly chart: {str(e)[:100]}")
                
                if not month_svc.empty:
                    st.dataframe(month_svc[['ship_month', 'total_units', 'on_time_pct', 'avg_days']].style.format({
                        'total_units': FORMATS['currency'], 
                        'on_time_pct': FORMATS['percentage'], 
                        'avg_days': FORMATS['decimal_1']
                    }), use_container_width=True, hide_index=True)

elif report_view == "Backorder Report":
    # --- LAZY FILTER LOADING: Apply filters only when "Apply Filters" is clicked ---
    f_backorder, has_pending_filters = get_lazy_filtered_data(
        backorder_data, report_view, 
        f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type, f_order_reason
    )

    # --- Set other dataframes to their unfiltered state ---
    f_service = service_data
    f_inventory = inventory_analysis_data

    with tab_service:
        # Show message if filters have been changed but not applied
        if has_pending_filters:
            st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the report.")

        st.header("Backorder Analysis (Unfulfilled Orders)")

        dfs_to_export = {} # Initialize here
        if f_backorder.empty:
            active_filter_count = len([v for v in st.session_state.get(f'active_filters_{report_view}', {}).values() if v and v != 'All'])
            show_empty_state_message("Backorder", active_filter_count)
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
            
            # --- GROUP 6B: Display Backorder Anomalies ---
            backorder_anomalies = detect_backorder_anomalies(f_backorder, sensitivity_level)
            if backorder_anomalies['count'] > 0:
                col_anom_left, col_anom_right = st.columns([1, 3])
                with col_anom_left:
                    st.metric("🚨 Issues Detected", backorder_anomalies['count'])
                with col_anom_right:
                    with st.expander(f"View {backorder_anomalies['count']} Anomalies"):
                        for detail in backorder_anomalies['details']:
                            st.write(detail)
            
            st.divider()
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Backorder Qty by Customer (Top 10)")
                cust_bo = pd.DataFrame()
                try:
                    cust_bo = get_backorder_customer_data(f_backorder)
                    if cust_bo.empty:
                        st.warning("❌ No customer backorder data available. Check your filters or the Debug Log for data quality issues.")
                    else:
                        # Validate required columns before rendering
                        required_cols = ['total_bo_qty', 'avg_days_on_bo']
                        missing_cols = [col for col in required_cols if col not in cust_bo.columns]
                        if missing_cols:
                            st.error(f"❌ Missing required data columns: {', '.join(missing_cols)}")
                        else:
                            fig = make_subplots(specs=[[{"secondary_y": True}]])
                            fig.add_trace(go.Bar(x=cust_bo.index, y=cust_bo['total_bo_qty'], name="Backorder Qty"), secondary_y=False)
                            fig.add_trace(go.Scatter(x=cust_bo.index, y=cust_bo['avg_days_on_bo'], name="Avg. Days on BO", mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                            fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN)
                            fig.update_yaxes(title_text="Backorder Qty", secondary_y=False)
                            fig.update_yaxes(title_text="Avg. Days on BO", secondary_y=True)
                            st.plotly_chart(fig, use_container_width=True)
                except KeyError as e:
                    st.error(f"❌ Missing data column in backorder customer analysis: {str(e)[:50]}")
                except Exception as e:
                    st.error(f"❌ Error generating customer backorder chart: {str(e)[:100]}")
                
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
                        st.warning("❌ No item backorder data available. Check your filters or the Debug Log for data quality issues.")
                    else:
                        # Validate required columns before rendering
                        required_cols = ['product_name', 'total_bo_qty']
                        missing_cols = [col for col in required_cols if col not in item_bo_chart.columns]
                        if missing_cols:
                            st.error(f"❌ Missing required data columns: {', '.join(missing_cols)}")
                        else:
                            fig = go.Figure(go.Bar(x=item_bo_chart['product_name'], y=item_bo_chart['total_bo_qty']))
                            fig.update_layout(height=CHART_HEIGHT_SMALL, margin=CHART_MARGIN, yaxis_title="Backorder Qty")
                            st.plotly_chart(fig, use_container_width=True)
                except KeyError as e:
                    st.error(f"❌ Missing data column in backorder item analysis: {str(e)[:50]}")
                except Exception as e:
                    st.error(f"❌ Error generating backorder item chart: {str(e)[:100]}")

                if not item_bo_chart.empty:
                    st.dataframe(item_bo_chart.set_index(['sku', 'product_name']).style.format({
                        'total_bo_qty': FORMATS['currency'], 
                        'avg_days_on_bo': FORMATS['decimal_1']
                    }), use_container_width=True)

elif report_view == "Inventory Management":
    # --- Apply inventory-specific filters (all material + category attributes) ---
    from utils import calculate_inventory_stock_value
    
    f_inventory = inventory_analysis_data.copy()
    
    # Get applied filters
    applied_filters = st.session_state.get(f'applied_filters_{report_view}', {})
    
    # Apply material attribute filters
    if applied_filters.get('material_number'):
        f_inventory = f_inventory[f_inventory['Material Number'].isin(applied_filters['material_number'])]
    
    if applied_filters.get('material_description'):
        f_inventory = f_inventory[f_inventory['Material Description'].isin(applied_filters['material_description'])]
    
    if applied_filters.get('pop_material'):
        f_inventory = f_inventory[f_inventory['POP Material: POP/Non POP'].isin(applied_filters['pop_material'])]
    
    if applied_filters.get('plm_level2'):
        f_inventory = f_inventory[f_inventory['PLM: Level Classification 2 (Attribute D_TMKLVL2CLS)'].isin(applied_filters['plm_level2'])]
    
    if applied_filters.get('expiration_flag'):
        f_inventory = f_inventory[f_inventory['POP Calculated Attributes: Expiration Flag'].isin(applied_filters['expiration_flag'])]
    
    if applied_filters.get('vendor_name'):
        f_inventory = f_inventory[f_inventory['POP Last Purchase: Vendor Name'].isin(applied_filters['vendor_name'])]
    
    # Apply category attribute filters
    if applied_filters.get('category'):
        f_inventory = f_inventory[f_inventory['category'].isin(applied_filters['category'])]
    
    if applied_filters.get('stock_category'):
        f_inventory = f_inventory[f_inventory['Stock Category: Description'].isin(applied_filters['stock_category'])]
    
    # Calculate stock values
    f_inventory = calculate_inventory_stock_value(f_inventory)
    
    # --- Set other dataframes to their unfiltered state ---
    f_service = service_data
    f_backorder = backorder_data
    
    # Check if filters have been changed but not applied
    has_pending_filters = applied_filters != {
        'order_year': "All",
        'order_month': "All",
        'customer_name': [],
        'category': [],
        'product_name': [],
        'sales_org': [],
        'order_type': [],
        'order_reason': [],
        'material_number': [],
        'material_description': [],
        'pop_material': [],
        'plm_level2': [],
        'expiration_flag': [],
        'vendor_name': [],
        'stock_category': []
    }

    with tab_service:
        # Show message if filters have been changed but not applied
        if has_pending_filters:
            st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the report.")
            
        st.header("Inventory Position")

        dfs_to_export = {} # Initialize here
        if f_inventory.empty:
            st.error("❌ No inventory data available.", icon="🚫")
            st.info("💡 **Troubleshooting:** Check that INVENTORY.csv is loaded and contains data.")
        else:
            # --- Export Button for this view ---
            inv_cat_export = get_inventory_category_data(f_inventory)
            dfs_to_export["Inventory_by_Category"] = (inv_cat_export, True)
            dfs_to_export["Inventory_Raw_Filtered"] = (f_inventory, False)

            # --- Main Page Content: KPI Metrics ---
            total_on_hand = f_inventory['POP Actual Stock Qty'].sum() if 'POP Actual Stock Qty' in f_inventory.columns else 0
            total_in_transit = f_inventory['POP Actual Stock in Transit Qty'].sum() if 'POP Actual Stock in Transit Qty' in f_inventory.columns else 0
            total_stock_value_usd = f_inventory['Stock Value USD'].sum() if 'Stock Value USD' in f_inventory.columns else 0
            avg_dio = get_inventory_kpis(f_inventory)[1] if not f_inventory.empty else 0
            
            # Display KPIs in 2x2 grid for better aesthetics
            kpi_cols = st.columns(4)
            with kpi_cols[0]:
                st.metric("💰 Total Stock Value", f"${total_stock_value_usd:,.2f}")
            with kpi_cols[1]:
                st.metric("📦 On-Hand Qty", f"{total_on_hand:,.0f}")
            with kpi_cols[2]:
                st.metric("🚚 In-Transit Qty", f"{total_in_transit:,.0f}")
            with kpi_cols[3]:
                st.metric("📊 Weighted Avg. DIO", f"{avg_dio:.1f} days")
            
            # --- GROUP 6B: Display Inventory Anomalies ---
            inventory_anomalies = detect_inventory_anomalies(f_inventory, sensitivity_level)
            if inventory_anomalies['count'] > 0:
                col_anom_left, col_anom_right = st.columns([1, 3])
                with col_anom_left:
                    st.metric("🚨 Issues Detected", inventory_anomalies['count'])
                with col_anom_right:
                    with st.expander(f"View {inventory_anomalies['count']} Anomalies"):
                        for detail in inventory_anomalies['details']:
                            st.write(detail)
            
            st.divider()
            
            st.subheader("On-Hand Stock & DIO by Category")
            inv_by_cat = pd.DataFrame()
            try:
                inv_by_cat = get_inventory_category_data(f_inventory)
                if inv_by_cat.empty:
                    st.warning("❌ No inventory category data available. Check your filters or the Debug Log for data quality issues.")
                else:
                    # Validate required columns before rendering
                    required_cols = ['total_on_hand', 'avg_dio']
                    missing_cols = [col for col in required_cols if col not in inv_by_cat.columns]
                    if missing_cols:
                        st.error(f"❌ Missing required data columns: {', '.join(missing_cols)}")
                    else:
                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        fig.add_trace(go.Bar(x=inv_by_cat.index, y=inv_by_cat['total_on_hand'], name="On-Hand Stock"), secondary_y=False)
                        fig.add_trace(go.Scatter(x=inv_by_cat.index, y=inv_by_cat['avg_dio'], name="Avg. DIO", mode='lines+markers', line=dict(color=SECONDARY_Y_AXIS_COLOR)), secondary_y=True)
                        
                        fig.update_layout(height=CHART_HEIGHT_LARGE, margin=CHART_MARGIN)
                        fig.update_yaxes(title_text="On-Hand Stock (Units)", secondary_y=False)
                        fig.update_yaxes(title_text="Avg. Days of Inventory (DIO)", secondary_y=True)
                        st.plotly_chart(fig, use_container_width=True)
            except KeyError as e:
                st.error(f"❌ Missing data column in inventory analysis: {str(e)[:50]}")
            except Exception as e:
                st.error(f"❌ Error generating inventory chart: {str(e)[:100]}")
            
            if not inv_by_cat.empty:
                st.dataframe(inv_by_cat.style.format({
                    'total_on_hand': FORMATS['currency'], 
                    'avg_dio': FORMATS['decimal_1']
                }), use_container_width=True)
            
            # --- Detailed Inventory Table with Stock Value ---
            st.divider()
            st.subheader("📋 Inventory Detail")
            
            # Prepare display columns with clean formatting
            display_cols = [
                'Material Number', 'Material Description', 'category', 'Stock Category: Description',
                'POP Material: POP/Non POP', 'PLM: Level Classification 2 (Attribute D_TMKLVL2CLS)',
                'POP Calculated Attributes: Expiration Flag', 'POP Last Purchase: Vendor Name',
                'POP Actual Stock Qty', 'POP Actual Stock in Transit Qty', 'Stock Value USD'
            ]
            
            # Only include columns that exist
            available_cols = [col for col in display_cols if col in f_inventory.columns]
            inventory_display = f_inventory[available_cols].copy()
            
            # Format the table for display
            format_dict = {}
            for col in inventory_display.columns:
                col_lower = str(col).lower()
                if 'qty' in col_lower or 'quantity' in col_lower:
                    format_dict[col] = '{:,.0f}'  # Format with thousands separator, no decimals
                elif 'stock value' in col_lower or 'price' in col_lower:
                    format_dict[col] = '${:,.2f}'  # Format as currency
            
            st.dataframe(inventory_display.style.format(format_dict), use_container_width=True)


# --- Tab 6: Debug Log (Only for standard reports, not Demand Forecasting) ---
# Debug tab is only created for Service Level, Backorder Report, and Inventory Management
# Demand Forecasting has its own separate error handling
if report_view != "📈 Demand Forecasting":
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

        def check_graph_df(df: pd.DataFrame, name: str, required_cols: list) -> list:
            """
            Validate a dataframe for graph rendering.
            
            Checks if a dataframe is empty and if all required columns are
            present. Used by the Debug Tab to identify data issues.
            
            Args:
                df: Dataframe to validate
                name: Display name for the dataframe (used in error messages)
                required_cols: List of column names that must be present
            
            Returns:
                List of validation messages (issues or success)
            """
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

# Add export options
export_with_metadata = st.sidebar.checkbox("Include Filter Summary Sheet", value=True, help="Adds an 'Export Info' sheet with filter criteria and timestamp")

# --- FIX: Add the download button logic that was missing ---
if 'dfs_to_export' in locals() and dfs_to_export:
    try:
        # Build metadata if requested
        metadata = None
        if export_with_metadata:
            active_filters = st.session_state.get(f'applied_filters_{report_view}', {})
            metadata = {
                'Report': report_view,
                'Export Date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Total Records': sum(len(df) for df, _ in dfs_to_export.values() if isinstance(df, pd.DataFrame)),
                'Active Filters': str(active_filters) if active_filters else 'None',
            }
        
        # Generate Excel with enhanced formatting
        excel_data = get_filtered_data_as_excel_with_metadata(
            dfs_to_export,
            metadata_dict=metadata,
            formatting_config={'enable_formatting': True}
        )
        st.sidebar.download_button(
            label="📥 Download as Excel",
            data=excel_data,
            file_name=f"Filtered_Supply_Chain_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheet.sheet"
        )
        
        # Show export summary
        with st.sidebar.expander("ℹ️ Export Info"):
            st.caption(f"**Report:** {report_view}")
            st.caption(f"**Records:** {sum(len(df) for df, _ in dfs_to_export.values() if isinstance(df, pd.DataFrame))} rows across {len(dfs_to_export)} sheets")
            st.caption(f"**Includes:** Filter summary, formatted numbers, and optimized layout")
            
    except Exception as e:
        st.sidebar.error("Failed to generate Excel file.")
        print(f"Excel generation error: {e}") # For terminal debugging
else:
    st.sidebar.info("No data available to download for the current filter selection.")