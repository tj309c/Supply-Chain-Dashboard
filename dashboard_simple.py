"""
EssilorLuxottica POP Supply Chain Dashboard
Simplified, modular UI for easy enhancement and maintenance
"""

import streamlit as st
import pandas as pd
import sys
import os
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
)

# Import UI components
from ui_components import (
    render_info_box
)

# Import page modules
from pages.overview_page import render_overview_page
from pages.service_level_page import render_service_level_page
from pages.inventory_page import render_inventory_page
from pages.backorder_page import render_backorder_page
from pages.debug_page import render_debug_page

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

@st.cache_data(ttl=3600)
def load_all_data():
    """Load all data sources with caching using optimized unified pattern"""
    try:
        # Define file paths
        MASTER_DATA_PATH = "Master Data.csv"
        ORDERS_PATH = "ORDERS.csv"
        DELIVERIES_PATH = "DELIVERIES.csv"
        INVENTORY_PATH = "INVENTORY.csv"

        # Load master data
        logs_master, master_data_df, errors_master = load_master_data(MASTER_DATA_PATH, file_key='master')

        # Load orders data using unified pattern (read once)
        logs_orders, orders_unified_df = load_orders_unified(ORDERS_PATH, file_key='orders')

        # Process orders data for item and header lookups
        logs_item, orders_item_df, errors_item = load_orders_item_lookup(orders_unified_df)
        logs_header, orders_header_df = load_orders_header_lookup(orders_unified_df)

        # Load deliveries data using unified pattern (read once)
        logs_deliveries, deliveries_unified_df = load_deliveries_unified(DELIVERIES_PATH, file_key='deliveries')

        # Load service data
        logs_service, service_data_df, errors_service = load_service_data(
            deliveries_unified_df,
            orders_header_df,
            master_data_df
        )

        # Load backorder data
        logs_backorder, backorder_data_df, errors_backorder = load_backorder_data(
            orders_item_df,
            orders_header_df,
            master_data_df
        )

        # Load inventory data
        logs_inventory, inventory_data_df, errors_inventory = load_inventory_data(INVENTORY_PATH, file_key='inventory')

        # Load inventory analysis data
        logs_analysis, inventory_analysis_df = load_inventory_analysis_data(
            inventory_data_df,
            deliveries_unified_df,
            master_data_df
        )

        return {
            # Data
            'master': master_data_df,
            'service': service_data_df,
            'backorder': backorder_data_df,
            'inventory': inventory_data_df,
            'inventory_analysis': inventory_analysis_df,
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
        }
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

# ===== MAIN APPLICATION =====

def main():
    """Main application entry point"""

    # Sidebar header
    st.sidebar.title("🏭 POP Supply Chain")
    st.sidebar.caption("EssilorLuxottica Platform")
    st.sidebar.divider()

    # Simple selectbox navigation
    pages = {
        "📊 Overview": "overview",
        "🚚 Service Level": "service_level",
        "⚠️ Backorders": "backorders",
        "📦 Inventory": "inventory",
        "📈 Forecasting": "forecasting",
        "🚛 Inbound Logistics": "inbound",
        "🔧 Debug & Logs": "debug"
    }

    selected_label = st.sidebar.selectbox("Navigate to:", list(pages.keys()))
    selected_page = pages[selected_label]

    st.sidebar.divider()

    # Load data
    with st.spinner("Loading data..."):
        data = load_all_data()

    if data is None:
        st.error("Failed to load data. Please check your data files.")
        st.stop()

    # Data status in sidebar
    st.sidebar.caption("📊 Data Status")
    st.sidebar.caption(f"Last Updated: {data['load_time'].strftime('%H:%M:%S')}")
    total_records = len(data['service']) + len(data['backorder']) + len(data['inventory'])
    st.sidebar.caption(f"Records: {total_records:,}")

    st.sidebar.divider()

    # Quick actions
    st.sidebar.header("⚡ Quick Actions")
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # Route to selected page
    if selected_page == "overview":
        render_overview_page(
            service_data=data['service'],
            backorder_data=data['backorder'],
            inventory_data=data['inventory']
        )

    elif selected_page == "service_level":
        render_service_level_page(service_data=data['service'])

    elif selected_page == "backorders":
        render_backorder_page(backorder_data=data['backorder'])

    elif selected_page == "inventory":
        render_inventory_page(inventory_data=data['inventory_analysis'])

    elif selected_page == "forecasting":
        st.title("📈 Forecasting")
        st.info("Forecasting page coming soon - easy to add!")

    elif selected_page == "inbound":
        st.title("🚛 Inbound Logistics")
        st.info("Inbound logistics page coming soon - easy to add!")

    elif selected_page == "debug":
        render_debug_page(debug_info=data)

    # Footer
    st.sidebar.divider()
    st.sidebar.caption("© 2025 EssilorLuxottica")
    st.sidebar.caption("POP Supply Chain Platform v2.0")

if __name__ == "__main__":
    main()
