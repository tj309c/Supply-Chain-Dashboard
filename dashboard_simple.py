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
from pages.forecast_page import render_forecast_page
from pages.debug_page import render_debug_page
from pages.demand_page import show_demand_page

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

def load_all_data(_progress_callback=None):
    """Load all data sources with caching using optimized unified pattern

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

        # Load master data (10%)
        update_progress(0.10, "Loading master data...")
        logs_master, master_data_df, errors_master = load_master_data(MASTER_DATA_PATH, file_key='master')

        # Load orders data using unified pattern (read once) (25%)
        update_progress(0.25, "Loading orders data...")
        logs_orders, orders_unified_df = load_orders_unified(ORDERS_PATH, file_key='orders')

        # Process orders data for item and header lookups (35%)
        update_progress(0.35, "Processing order details...")
        logs_item, orders_item_df, errors_item = load_orders_item_lookup(orders_unified_df)
        logs_header, orders_header_df = load_orders_header_lookup(orders_unified_df)

        # Load deliveries data using unified pattern (read once) (50%)
        update_progress(0.50, "Loading deliveries data...")
        logs_deliveries, deliveries_unified_df = load_deliveries_unified(DELIVERIES_PATH, file_key='deliveries')

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

        # Load inbound receipt data (89%)
        update_progress(0.89, "Loading inbound receipts...")
        logs_inbound, inbound_df = load_inbound_data(INBOUND_PATH, file_key='inbound')

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
        logs_pricing, pricing_analysis_df, vendor_discount_summary_df = load_pricing_analysis(vendor_pos_df, inbound_df)

        # Calculate backorder relief dates (97%)
        update_progress(0.97, "Calculating backorder relief dates...")
        logs_relief, backorder_relief_df = load_backorder_relief(backorder_data_df, vendor_pos_df, vendor_performance_df)

        # Generate demand forecasts (99%)
        update_progress(0.99, "Generating demand forecasts...")
        logs_demand, demand_forecast_df, demand_accuracy_df = generate_demand_forecast(deliveries_unified_df, forecast_horizon_days=90)

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
            'inbound': inbound_df,
            'vendor_performance': vendor_performance_df,
            'pricing_analysis': pricing_analysis_df,
            'vendor_discount_summary': vendor_discount_summary_df,
            'demand_forecast': demand_forecast_df,
            'demand_accuracy': demand_accuracy_df,
            'deliveries': deliveries_unified_df,  # Add deliveries data for demand-based calculations
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
        }
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

# ===== MAIN APPLICATION =====

def main():
    """Main application entry point"""

    # ===== SIDEBAR: HEADER =====
    st.sidebar.title("🏭 POP Supply Chain")
    st.sidebar.caption("EssilorLuxottica Platform v2.0")
    st.sidebar.divider()

    # ===== SIDEBAR: NAVIGATION =====
    st.sidebar.header("📍 Navigation")

    # Organize pages into logical groups
    core_pages = {
        "📊 Overview": "overview",
        "🚚 Service Level": "service_level",
        "⚠️ Backorders": "backorders",
        "📦 Inventory": "inventory",
        "🏭 Vendor & Procurement": "vendor",
        "📈 Demand Forecasting": "demand",
        "🔄 SKU Mapping": "sku_mapping"
    }

    future_pages = {
        "📊 Old Forecasting": "forecasting",
        "🚛 Inbound Logistics": "inbound"
    }

    utility_pages = {
        "📤 Data Management": "data_upload",
        "🔧 Debug & Logs": "debug"
    }

    # Combine all pages for selectbox
    all_pages = {**core_pages, **future_pages, **utility_pages}

    selected_label = st.sidebar.selectbox(
        "Select Page",
        options=list(all_pages.keys()),
        help="Navigate between different supply chain modules",
        label_visibility="collapsed"
    )
    selected_page = all_pages[selected_label]

    st.sidebar.divider()

    # ===== SIDEBAR: DATA LOADING =====
    # Load data with progress indicator
    progress_bar = st.sidebar.progress(0)
    progress_text = st.sidebar.empty()

    def update_loading_progress(progress, message):
        """Update progress bar and text during data loading"""
        progress_bar.progress(progress)
        progress_text.text(message)

    data = load_all_data(_progress_callback=update_loading_progress)

    # Clear progress indicators
    progress_bar.empty()
    progress_text.empty()

    if data is None:
        st.error("Failed to load data. Please check your data files.")
        st.stop()

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
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True, help="Clear cache and reload all data from source files"):
        st.cache_data.clear()
        st.rerun()

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
        show_demand_page(
            deliveries_df=data['deliveries'],
            demand_forecast_df=data['demand_forecast'],
            forecast_accuracy_df=data['demand_accuracy']
        )

    elif selected_page == "forecasting":
        render_forecast_page(orders_data=None, deliveries_data=None, master_data=None)

    elif selected_page == "inbound":
        render_inbound_page(inbound_data=None)

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
