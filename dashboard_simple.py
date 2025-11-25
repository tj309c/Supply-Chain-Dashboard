"""
EssilorLuxottica POP Supply Chain Dashboard
Simplified, modular UI for easy enhancement and maintenance
"""

import streamlit as st
import pandas as pd
import sys
import os
import importlib
from datetime import datetime
import pytz

# Import data loaders
from data_loader import (
    load_master_data,
    load_orders_unified,
    load_orders_item_lookup,
    load_orders_header_lookup,
    load_deliveries_unified,
    load_service_data,
    load_backorder_data,
    load_inventory_data,
    load_inventory_analysis_data,
    load_vendor_pos,
    load_inbound_data,
    load_vendor_performance,
    load_backorder_relief,
    load_stockout_prediction,
    create_sku_description_lookup,
    load_atl_fulfillment,
)

# Import pricing analysis
from pricing_analysis import load_pricing_analysis

# Import demand forecasting
from demand_forecasting import generate_demand_forecast

# Import UI components
from ui_components import (
    render_info_box
)

# Import page modules
from pages.overview_page import render_overview_page
from pages.service_level_page import render_service_level_page
from pages.inventory_page import render_inventory_page
from pages.backorder_page import render_backorder_page
from pages.sku_mapping_page import render_sku_mapping_page
from pages.vendor_page import render_vendor_page
from pages.data_upload_page import render_data_upload_page
from pages.inbound_page import render_inbound_page
from pages.debug_page import render_debug_page
from pages.demand_page import show_demand_page
from pages.replenishment_page import render_replenishment_page

# ===== PAGE CONFIGURATION =====
st.set_page_config(
    page_title="POP Supply Chain Dashboard",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== CUSTOM CSS =====
st.markdown("""
    <style>
        /* Overall zoom level - 70% of normal size */
        .main .block-container {
            zoom: 0.7;
        }

        /* Clean, professional styling */
        .main {
            padding: 1rem;
        }

        /* Improve metric cards */
        [data-testid="stMetric"] {
            background-color: #f8f9fa;
            padding: 1rem;
            border-radius: 0.5rem;
            border: 1px solid #e9ecef;
        }

        /* Reduce metric font size slightly */
        [data-testid="stMetric"] > div > div > div {
            font-size: 18px !important;
        }

        /* Better table styling */
        .dataframe {
            font-size: 0.9rem;
        }

        /* Hide automatic Streamlit page navigation */
        [data-testid="stSidebarNav"] {
            display: none;
        }

        /* Mobile responsive */
        @media (max-width: 768px) {
            .stColumns > [data-testid="column"] {
                width: 100% !important;
                margin-bottom: 1rem;
            }
        }
    </style>
""", unsafe_allow_html=True)

# ===== DATA LOADING =====
# Remove caching from load_all_data to fix CacheReplayClosureError

def load_all_data(_progress_callback=None, retail_only=True):
    """Load all data sources with optimized unified pattern

    Args:
        _progress_callback: Optional callback function to report loading progress (underscore prefix = not hashed)
    """
    def update_progress(step, message):
        """Helper to update progress if callback provided"""
        if _progress_callback:
            _progress_callback(step, message)

    try:
        # Define file paths
        MASTER_DATA_PATH = "Master Data.csv"
        ORDERS_PATH = "ORDERS.csv"
        DELIVERIES_PATH = "DELIVERIES.csv"
        INVENTORY_PATH = "INVENTORY.csv"
        VENDOR_POS_PATH = "Domestic Vendor POs.csv"
        INBOUND_PATH = "DOMESTIC INBOUND.csv"
        ATL_FULFILLMENT_PATH = "ATL_FULLFILLMENT.csv"

        # Load master data (10%)
        update_progress(0.10, "Loading master data...")
        logs_master, master_data_df, errors_master = load_master_data(MASTER_DATA_PATH, file_key='master')

        # Load orders data using unified pattern (read once) (25%)
        update_progress(0.25, "Loading orders data...")
        logs_orders, orders_unified_df = load_orders_unified(ORDERS_PATH, file_key='orders')

        # If retail-only mode is enabled, build a whitelist of SKUs from master data
        # and filter the unified order/delivery sets early to reduce downstream processing.
        # NOTE: We normalize SKU strings (trim + collapse whitespace + uppercase) to
        # avoid mismatches caused by formatting differences across files.
        retail_skus = set()
        retail_mode_fallbacked = False
        retail_mode_applied = False
        retail_sku_count = 0
        def _normalize_skus(series):
            return series.astype(str).str.strip().str.replace(r"\s+", " ", regex=True).str.upper()

        if retail_only and not master_data_df.empty and 'category' in master_data_df.columns:
            retail_mask = master_data_df['category'].astype(str).str.strip().str.upper() == 'RETAIL PERMANENT'
            master_retail_skus = master_data_df.loc[retail_mask, 'sku'].astype(str).tolist()
            # create a normalized set for comparison
            retail_skus = set(_normalize_skus(pd.Series(master_retail_skus)).tolist())
            retail_sku_count = len(retail_skus)
            if retail_sku_count > 0:
                logs_orders.append(f"INFO: RETAIL PERMANENT mode enabled - filtering using {retail_sku_count} SKUs (normalized matching).")

        # Process orders data for item and header lookups (35%)
        update_progress(0.35, "Processing order details...")
        # If retail_only is active and retail_skus is populated, filter unified file first
        # Normalize order SKUs on the fly for robust matching.
        if retail_only and retail_skus:
            # Keep original copy in case the filter removes everything (we'll fall back)
            _orders_original = orders_unified_df
            orders_norm = _normalize_skus(orders_unified_df['Item - SAP Model Code'])
            orders_unified_df = orders_unified_df[orders_norm.isin(retail_skus)]

        logs_item, orders_item_df, errors_item = load_orders_item_lookup(orders_unified_df)
        logs_header, orders_header_df = load_orders_header_lookup(orders_unified_df)

        # Load deliveries data using unified pattern (read once) (50%)
        update_progress(0.50, "Loading deliveries data...")
        logs_deliveries, deliveries_unified_df = load_deliveries_unified(DELIVERIES_PATH, file_key='deliveries')
        if retail_only and retail_skus:
            # Keep original copy for fallback
            _deliveries_original = deliveries_unified_df
            deliveries_norm = _normalize_skus(deliveries_unified_df['Item - SAP Model Code'])
            deliveries_unified_df = deliveries_unified_df[deliveries_norm.isin(retail_skus)]

        # Load service data (65%)
        update_progress(0.65, "Calculating service levels...")
        logs_service, service_data_df, errors_service = load_service_data(
            deliveries_unified_df,
            orders_header_df,
            master_data_df
        )

        # Load backorder data (75%)
        update_progress(0.75, "Analyzing backorders...")
        logs_backorder, backorder_data_df, errors_backorder = load_backorder_data(
            orders_item_df,
            orders_header_df,
            master_data_df
        )

        # Load inventory data (85%)
        update_progress(0.85, "Loading inventory snapshot...")
        logs_inventory, inventory_data_df, errors_inventory = load_inventory_data(INVENTORY_PATH, file_key='inventory')
        if retail_only and retail_skus:
            _inventory_original = inventory_data_df
            inventory_norm = _normalize_skus(inventory_data_df['sku']) if 'sku' in inventory_data_df.columns else pd.Series(dtype=str)
            inventory_data_df = inventory_data_df[inventory_norm.isin(retail_skus)]

        # Load inventory analysis data (85%)
        update_progress(0.85, "Computing inventory analytics...")
        logs_analysis, inventory_analysis_df = load_inventory_analysis_data(
            inventory_data_df,
            deliveries_unified_df,
            master_data_df
        )

        # Load vendor PO data (87%)
        update_progress(0.87, "Loading vendor purchase orders...")
        logs_vendor_pos, vendor_pos_df = load_vendor_pos(VENDOR_POS_PATH, file_key='vendor_pos')
        if retail_only and retail_skus:
            if 'sku' in vendor_pos_df.columns:
                _vendor_pos_original = vendor_pos_df
                vendor_norm = _normalize_skus(vendor_pos_df['sku'])
                vendor_pos_df = vendor_pos_df[vendor_norm.isin(retail_skus)]

        # Load inbound receipt data (89%)
        update_progress(0.89, "Loading inbound receipts...")
        logs_inbound, inbound_df = load_inbound_data(INBOUND_PATH, file_key='inbound')
        if retail_only and retail_skus:
            if 'sku' in inbound_df.columns:
                _inbound_original = inbound_df
                inbound_norm = _normalize_skus(inbound_df['sku'])
                inbound_df = inbound_df[inbound_norm.isin(retail_skus)]

        # Load ATL fulfillment data for international shipments (90%)
        update_progress(0.90, "Loading international shipments...")
        try:
            logs_atl, atl_fulfillment_df = load_atl_fulfillment(
                ATL_FULFILLMENT_PATH,
                master_df=master_data_df,
                file_key='atl_fulfillment'
            )
            if retail_only and retail_skus:
                if 'sku' in atl_fulfillment_df.columns:
                    _atl_original = atl_fulfillment_df
                    atl_norm = _normalize_skus(atl_fulfillment_df['sku'])
                    atl_fulfillment_df = atl_fulfillment_df[atl_norm.isin(retail_skus)]
        except Exception as e:
            logs_atl = [f"WARNING: Could not load ATL_FULLFILLMENT.csv: {e}"]
            atl_fulfillment_df = pd.DataFrame()

        # If retail_only filtering removed rows from one or more primary sources,
        # restore each affected source individually (falls back to original copy where available).
        # This prevents a single-source dropout (e.g., inventory) from showing N/A across the UI.
        if retail_only and retail_skus:
            # Track whether any per-source fallback occurred
            local_fallbacks = []

            if '_orders_original' in locals() and orders_unified_df.empty and len(_orders_original) > 0:
                logs_orders.append("WARNING: RETAIL-only filtering removed all rows from orders; restoring full ORDERS dataset for analysis.")
                orders_unified_df = _orders_original
                local_fallbacks.append('orders')

            if '_deliveries_original' in locals() and deliveries_unified_df.empty and len(_deliveries_original) > 0:
                logs_deliveries.append("WARNING: RETAIL-only filtering removed all rows from deliveries; restoring full DELIVERIES dataset for analysis.")
                deliveries_unified_df = _deliveries_original
                local_fallbacks.append('deliveries')

            if '_inventory_original' in locals() and inventory_data_df.empty and len(_inventory_original) > 0:
                logs_inventory.append("WARNING: RETAIL-only filtering removed all rows from inventory; restoring full INVENTORY dataset for analysis.")
                inventory_data_df = _inventory_original
                local_fallbacks.append('inventory')

            # Also restore vendor_pos/inbound if they were filtered to empty
            if '_vendor_pos_original' in locals() and vendor_pos_df.empty and len(_vendor_pos_original) > 0:
                logs_vendor_pos.append("WARNING: RETAIL-only filtering removed all rows from vendor POs; restoring full Vendor PO dataset.")
                vendor_pos_df = _vendor_pos_original
                local_fallbacks.append('vendor_pos')

            if '_inbound_original' in locals() and inbound_df.empty and len(_inbound_original) > 0:
                logs_inbound.append("WARNING: RETAIL-only filtering removed all rows from inbound receipts; restoring full inbound dataset.")
                inbound_df = _inbound_original
                local_fallbacks.append('inbound')

            # If we restored at least one source, note that a fallback occurred;
            # otherwise, if no originals available but datasets are empty, warn and disable retail mode.
            if local_fallbacks:
                # If any per-source fallbacks occurred we consider that a fallback scenario and
                # do not consider retail mode 'applied' globally (keeps behavior consistent)
                retail_mode_fallbacked = True
                retail_mode_applied = False
            else:
                # fallback to full dataset if all were filtered away (previous behavior)
                total_filtered_rows = sum([
                    len(orders_unified_df) if 'orders_unified_df' in locals() else 0,
                    len(deliveries_unified_df) if 'deliveries_unified_df' in locals() else 0,
                    len(inventory_data_df) if 'inventory_data_df' in locals() else 0
                ])
                if total_filtered_rows == 0:
                    logs_orders.append("WARNING: RETAIL-only filtering removed all rows in orders/deliveries/inventory — falling back to full dataset.")
                    if '_orders_original' in locals():
                        orders_unified_df = _orders_original
                    if '_deliveries_original' in locals():
                        deliveries_unified_df = _deliveries_original
                    if '_inventory_original' in locals():
                        inventory_data_df = _inventory_original
                    if '_vendor_pos_original' in locals():
                        vendor_pos_df = _vendor_pos_original
                    if '_inbound_original' in locals():
                        inbound_df = _inbound_original
                    retail_mode_fallbacked = True
                    retail_mode_applied = False
                else:
                    retail_mode_applied = True

        # Calculate vendor performance (91%)
        update_progress(0.91, "Calculating vendor performance...")
        logs_vendor_perf, vendor_performance_df = load_vendor_performance(vendor_pos_df, inbound_df)

        # Calculate stockout risk predictions (93%)
        update_progress(0.93, "Predicting stockout risk...")
        logs_stockout, stockout_risk_df = load_stockout_prediction(
            inventory_data_df,
            deliveries_unified_df,
            vendor_pos_df,
            vendor_performance_df
        )

        # Calculate pricing analysis (95%)
        update_progress(0.95, "Analyzing pricing and volume discounts...")
        pricing_data = load_pricing_analysis(vendor_pos_df, inbound_df)
        if len(pricing_data) == 3:
            logs_pricing, pricing_analysis_df, vendor_discount_summary_df = pricing_data
        else:
            logs_pricing, pricing_analysis_df = pricing_data
            vendor_discount_summary_df = pd.DataFrame() # Assign a default empty DataFrame

        # Calculate backorder relief dates (97%)
        update_progress(0.97, "Calculating backorder relief dates...")
        logs_relief, backorder_relief_df = load_backorder_relief(backorder_data_df, vendor_pos_df, vendor_performance_df)

        # -- LAZY DEMAND FORECASTING --
        # Demand forecasting is expensive and used less frequently. We defer running
        # `generate_demand_forecast` until the user explicitly opens the Demand page.
        # Here we return empty dataframes/placeholders that will be filled on demand.
        logs_demand, demand_forecast_df, demand_accuracy_df, daily_demand_df = [], pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Create SKU description lookup (99.5%)
        update_progress(0.995, "Building SKU description lookup...")
        sku_lookup = create_sku_description_lookup(
            orders_item_lookup_df=orders_item_df,
            inventory_df=inventory_data_df,
            vendor_pos_df=vendor_pos_df,
            deliveries_df=deliveries_unified_df,
            inbound_df=inbound_df
        )

        # Finalizing (100%)
        update_progress(1.0, "Ready!")

        return {
            # Data
            'master': master_data_df,
            'service': service_data_df,
            'backorder': backorder_data_df,
            'backorder_relief': backorder_relief_df,
            'inventory': inventory_data_df,
            'inventory_analysis': inventory_analysis_df,
            'stockout_risk': stockout_risk_df,
            'vendor_pos': vendor_pos_df,
            'atl_fulfillment': atl_fulfillment_df,
            'inbound': inbound_df,
            'vendor_performance': vendor_performance_df,
            'pricing_analysis': pricing_analysis_df,
            'vendor_discount_summary': vendor_discount_summary_df,
            'demand_forecast': demand_forecast_df,
            'demand_accuracy': demand_accuracy_df,
            'daily_demand': daily_demand_df,  # Daily demand time series for visualization
            'deliveries': deliveries_unified_df,  # Add deliveries data for demand-based calculations
            'orders_item_lookup': orders_item_df,  # Add orders item lookup for SKU descriptions
            'sku_lookup': sku_lookup,  # SKU description lookup dictionary
            'load_time': datetime.now(),
            'load_time_str': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

            # Debug info - Logs
            'master_logs': logs_master,
            'orders_logs': logs_orders,
            'orders_item_logs': logs_item,
            'orders_header_logs': logs_header,
            'deliveries_logs': logs_deliveries,
            'service_logs': logs_service,
            'backorder_logs': logs_backorder,
            'inventory_logs': logs_inventory,
            'analysis_logs': logs_analysis,
            'vendor_pos_logs': logs_vendor_pos,
            'inbound_logs': logs_inbound,
            'vendor_perf_logs': logs_vendor_perf,
            'stockout_logs': logs_stockout,
            'pricing_logs': logs_pricing,
            'relief_logs': logs_relief,
            'demand_logs': logs_demand,

            # Debug info - Errors
            'master_errors': errors_master,
            'service_errors': errors_service,
            'backorder_errors': errors_backorder,
            'inventory_errors': errors_inventory,

            # Debug info - DataFrames (for inspection)
            'master_df': master_data_df,
            'service_df': service_data_df,
            'backorder_df': backorder_data_df,
            'inventory_df': inventory_data_df,
            'inventory_analysis_df': inventory_analysis_df,
            'stockout_risk_df': stockout_risk_df,
            'vendor_pos_df': vendor_pos_df,
            'inbound_df': inbound_df,
            'vendor_performance_df': vendor_performance_df,
            'pricing_analysis_df': pricing_analysis_df,
            'vendor_discount_summary_df': vendor_discount_summary_df,
            'demand_forecast_df': demand_forecast_df,
            'demand_accuracy_df': demand_accuracy_df,
            'retail_mode_applied': retail_mode_applied,
            'retail_mode_fallbacked': retail_mode_fallbacked,
            'retail_sku_count': retail_sku_count,
        }
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None


def compute_forecast_wrapper(deliveries_df, master_df, horizon_days=90, ts_mode='Daily'):
    """Module-level helper that maps UI time-series selection to the forecasting API.

    Kept at module-level so tests and the UI can call the same mapping logic.
    """
    if ts_mode == 'Daily' or str(ts_mode).lower() == 'daily':
        return generate_demand_forecast(deliveries_df, master_data_df=master_df, forecast_horizon_days=horizon_days, ts_granularity='daily', rolling_months=None)
    if ts_mode == 'Monthly' or str(ts_mode).lower() == 'monthly':
        return generate_demand_forecast(deliveries_df, master_data_df=master_df, forecast_horizon_days=horizon_days, ts_granularity='monthly', rolling_months=None)
    # Handle 30-month rolling window for demand forecasting
    if 'rolling 30' in str(ts_mode).lower() or ts_mode == 'Rolling 30 months (monthly)':
        return generate_demand_forecast(deliveries_df, master_data_df=master_df, forecast_horizon_days=horizon_days, ts_granularity='monthly', rolling_months=30)
    # Any other value -> treat as rolling 12 months monthly by default
    return generate_demand_forecast(deliveries_df, master_data_df=master_df, forecast_horizon_days=horizon_days, ts_granularity='monthly', rolling_months=12)

# ===== MAIN APPLICATION =====

def main():
    """Main application entry point"""

    # ===== SIDEBAR: HEADER =====
    st.sidebar.title("🏭 POP Supply Chain")
    st.sidebar.caption("EssilorLuxottica Platform v2.0")
    st.sidebar.divider()

    # ===== SIDEBAR: NAVIGATION =====
    # Single selectbox for clean, unified page selection

    # All navigable pages in a flat list
    page_options = [
        "📊 Overview",
        "🚚 Service Level",
        "⚠️ Backorders",
        "📦 Inventory",
        "🏭 Vendor & Procurement",
        "📈 Demand Forecasting",
        "📋 Replenishment Planning",
        "🔄 SKU Mapping",
        "📤 Data Management"
    ]

    # Map display names to page keys
    page_map = {
        "📊 Overview": "overview",
        "🚚 Service Level": "service_level",
        "⚠️ Backorders": "backorders",
        "📦 Inventory": "inventory",
        "🏭 Vendor & Procurement": "vendor",
        "📈 Demand Forecasting": "demand",
        "📋 Replenishment Planning": "replenishment",
        "🔄 SKU Mapping": "sku_mapping",
        "📤 Data Management": "data_upload"
    }

    # Single selectbox for page navigation
    selected_label = st.sidebar.selectbox(
        "Navigate to",
        options=page_options,
        index=0,  # Default to Overview
        key="main_nav"
    )

    selected_page = page_map.get(selected_label, "overview")

    # Debug option (separate checkbox)
    if st.sidebar.checkbox("🔧 Debug Mode", value=False, key="show_debug"):
        selected_page = "debug"

    st.sidebar.divider()

    # ===== SIDEBAR: GLOBAL SETTINGS =====
    st.sidebar.markdown("**⚙️ Data Settings**")

    # Load data with progress indicator
    progress_bar = st.sidebar.progress(0)
    progress_text = st.sidebar.empty()

    def update_loading_progress(progress, message):
        """Update progress bar and text during data loading"""
        progress_bar.progress(progress)
        progress_text.text(message)

    # Sidebar toggle: restrict data to RETAIL PERMANENT SKUs (95% common case) to reduce load time
    retail_only = st.sidebar.checkbox(
        "RETAIL PERMANENT only",
        value=True,
        help="Load only RETAIL PERMANENT SKUs (faster). Uncheck for full dataset."
    )

    # Time period - simplified
    use_rolling_12 = st.sidebar.checkbox(
        "Rolling 12 Months",
        value=True,
        help="Show last 12 months. Uncheck to select a specific year."
    )

    # Year selector - only show when Rolling 12 Months is NOT selected
    current_year = datetime.now().year
    if not use_rolling_12:
        year_options = [str(y) for y in range(current_year - 2, current_year + 1)]
        selected_year = st.sidebar.selectbox(
            "Year",
            options=year_options,
            index=len(year_options) - 1,
            help="Filter to specific calendar year"
        )
    else:
        selected_year = str(current_year)

    # Determine time_series_mode based on selections
    if use_rolling_12:
        time_series_mode = 'Rolling 12 months (monthly)'
    else:
        time_series_mode = 'Monthly'

    # Store selected year in session state for use by pages
    st.session_state['selected_year'] = int(selected_year)
    st.session_state['use_rolling_12'] = use_rolling_12

    # Cached, on-demand forecast computation used by the Demand page and for pre-warming
    @st.cache_data(ttl=3600, show_spinner="Computing demand forecasts...")
    def _compute_demand_forecast(deliveries_df, master_df, horizon_days=90, ts_mode='daily'):
        try:
            # Convert selection to arguments for forecasting function
            return compute_forecast_wrapper(deliveries_df, master_df, horizon_days, ts_mode=ts_mode)
        except Exception as e:
            # Ensure the cached function always returns the same shape
            return [], pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # If retail_only mode is active we show a persistent banner explaining scope of results
    if retail_only:
        st.sidebar.markdown("---")
        st.sidebar.info("RETAIL PERMANENT mode is ON — the dashboard is loading and showing only SKUs classified as **RETAIL PERMANENT**. Toggle off to view the full dataset.")

    data = load_all_data(_progress_callback=update_loading_progress, retail_only=retail_only)

    # Clear progress indicators
    progress_bar.empty()
    progress_text.empty()

    if data is None:
        st.error("Failed to load data. Please check your data files.")
        st.stop()

    # If load_all_data reported the retail filter was fallbacked, surface a clear warning
    if data.get('retail_mode_fallbacked'):
        st.warning("RETAIL-only filter did not match any rows in your data and was automatically disabled. The dashboard is showing the full dataset.")

    # ===== SIDEBAR: SYSTEM STATUS =====
    st.sidebar.header("📊 System Status")

    # Calculate metrics
    total_records = len(data['service']) + len(data['backorder']) + len(data['inventory'])

    # Display status as metrics for better visibility
    col1, col2 = st.sidebar.columns(2)
    with col1:
        st.metric(
            label="Last Updated",
            value=data['load_time'].strftime('%H:%M'),
            help="Time when data was last loaded from source files"
        )
    with col2:
        st.metric(
            label="Total Records",
            value=f"{total_records:,}",
            help="Combined count of service, backorder, and inventory records"
        )

    st.sidebar.divider()

    # ===== SIDEBAR: QUICK ACTIONS =====
    st.sidebar.header("⚡ Quick Actions")
    if st.sidebar.button("🔄 Refresh Data", width='stretch', help="Clear cache and reload all data from source files"):
        st.cache_data.clear()
        st.rerun()

    # Precompute retail forecasts (warm cache) - only shown when retail_only mode is used
    if retail_only:
        if st.sidebar.button("⚡ Precompute Retail Forecasts (warm cache)", help="Prime the demand forecast cache for RETAIL PERMANENT SKUs"):
            # Gather input data
            master_df = data.get('master_df', pd.DataFrame())
            deliveries_df = data.get('deliveries', pd.DataFrame())

            # Identify retail SKUs (normalize SKUs for robust matching)
            retail_skus = set()
            if not master_df.empty and 'category' in master_df.columns:
                retail_mask = master_df['category'].astype(str).str.strip().str.upper() == 'RETAIL PERMANENT'
                if retail_mask.any():
                    retail_skus = set(master_df.loc[retail_mask, 'sku'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True).str.upper().tolist())

            if deliveries_df.empty or len(retail_skus) == 0:
                st.sidebar.warning("No deliveries or no RETAIL PERMANENT SKUs found to precompute.")
            else:
                # Filter deliveries to the retail SKUs
                dlv_norm = deliveries_df['Item - SAP Model Code'].astype(str).str.strip().str.replace(r'\s+', ' ', regex=True).str.upper()
                dlv = deliveries_df[dlv_norm.isin(list(retail_skus))].copy()
                # Convert columns to expected names for the forecast function
                dlv = dlv.rename(columns={
                    'Item - SAP Model Code': 'sku',
                    'Delivery Creation Date: Date': 'ship_date',
                    'Goods Issue Date: Date': 'ship_date',
                    'Deliveries - TOTAL Goods Issue Qty': 'units_issued'
                })

                # Filter master to retail skus
                mdf = master_df[master_df['sku'].isin(list(retail_skus))].copy()

                start_time = datetime.now()
                with st.sidebar.spinner('Precomputing retail forecasts (this may take a while)...'):
                    logs_p, f_df, acc_df, daily_df = _compute_demand_forecast(dlv, mdf, 90, ts_mode=time_series_mode)
                elapsed = (datetime.now() - start_time).total_seconds()

                if isinstance(f_df, pd.DataFrame) and not f_df.empty:
                    st.sidebar.success(f"Retail forecasts computed & cached for {len(f_df)} SKUs in {elapsed:.1f}s")
                    # Store into session_state for quick access if required
                    st.session_state['retail_forecast_cached'] = (logs_p, f_df, acc_df, daily_df)
                else:
                    st.sidebar.error("Retail precompute completed but no forecast rows were produced.")

    # Display dashboard time in EST
    est = pytz.timezone('US/Eastern')
    est_time = datetime.now(est)
    st.markdown(f"<div style='font-size:16px; color:gray;'>Dashboard Time (EST): {est_time.strftime('%Y-%m-%d %H:%M:%S')}</div>", unsafe_allow_html=True)

    # Route to selected page
    if selected_page == "overview":
        render_overview_page(
            service_data=data['service'],
            backorder_data=data['backorder'],
            inventory_data=data['inventory_analysis']  # Use inventory_analysis to get DIO calculations
        )

    elif selected_page == "service_level":
        render_service_level_page(service_data=data['service'])

    elif selected_page == "backorders":
        render_backorder_page(
            backorder_data=data['backorder'],
            backorder_relief_data=data['backorder_relief'],
            stockout_risk_data=data['stockout_risk'],
            inventory_data=data['inventory'],
            deliveries_data=data['deliveries']  # Pass real deliveries data - NO FAKE DATA
        )

    elif selected_page == "inventory":
        render_inventory_page(inventory_data=data['inventory_analysis'])

    elif selected_page == "sku_mapping":
        render_sku_mapping_page(inventory_data=data['inventory'], backorder_data=data['backorder'])

    elif selected_page == "vendor":
        render_vendor_page(
            po_data=data['vendor_pos'],
            vendor_performance=data['vendor_performance'],
            pricing_analysis=data['pricing_analysis'],
            vendor_discount_summary=data['vendor_discount_summary']
        )

    elif selected_page == "demand":
        # Lazily compute or fetch cached demand forecast data only when user navigates to this page
        @st.cache_data(ttl=3600, show_spinner="Computing demand forecasts...")
        def _compute_demand_forecast(deliveries_df, master_df, horizon_days=90, ts_mode='daily'):
            try:
                return compute_forecast_wrapper(deliveries_df, master_df, horizon_days, ts_mode=ts_mode)
            except Exception as e:
                st.error(f"Error computing demand forecast: {e}")
                return [], pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # For demand forecasting, always use 30 months of data for better forecast accuracy
        # (more historical data = better moving averages and trend analysis)
        demand_ts_mode = 'Rolling 30 months (monthly)'
        st.info("📊 **Demand Forecasting uses 30 months of historical data** for more accurate forecasts (overrides the sidebar filter).")

        # Compute on demand (will use cache if run within TTL)
        logs_demand, demand_forecast_df, demand_accuracy_df, daily_demand_df = _compute_demand_forecast(
            data['deliveries'], data.get('master_df', pd.DataFrame()), 90, ts_mode=demand_ts_mode
        )

        show_demand_page(
            deliveries_df=data['deliveries'],
            demand_forecast_df=demand_forecast_df,
            forecast_accuracy_df=demand_accuracy_df,
            master_data_df=data.get('master_df', pd.DataFrame()),
            daily_demand_df=daily_demand_df
        )

    elif selected_page == "replenishment":
        # Replenishment planning needs demand forecast data
        # Compute demand forecast if not already available
        @st.cache_data(ttl=3600, show_spinner="Computing demand forecasts for replenishment...")
        def _compute_demand_for_replenishment(deliveries_df, master_df, horizon_days=90):
            try:
                return compute_forecast_wrapper(deliveries_df, master_df, horizon_days, ts_mode='Rolling 30 months (monthly)')
            except Exception as e:
                st.warning(f"Could not compute demand forecast: {e}")
                return [], pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Get demand forecast (use cached if available)
        _, demand_forecast_df, _, _ = _compute_demand_for_replenishment(
            data['deliveries'], data.get('master_df', pd.DataFrame()), 90
        )

        render_replenishment_page(
            inventory_data=data['inventory_analysis'],
            demand_forecast_data=demand_forecast_df,
            backorder_data=data['backorder'],
            vendor_pos_data=data['vendor_pos'],
            atl_fulfillment_data=data.get('atl_fulfillment', pd.DataFrame()),
            master_data=data.get('master_df', pd.DataFrame())
        )

    elif selected_page == "data_upload":
        render_data_upload_page()

    elif selected_page == "debug":
        render_debug_page(debug_info=data)

    # Footer
    st.sidebar.divider()
    st.sidebar.caption("© 2025 EssilorLuxottica")
    st.sidebar.caption("POP Supply Chain Platform v2.0")

if __name__ == "__main__":
    main()
