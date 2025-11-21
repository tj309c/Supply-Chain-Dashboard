"""
Debug & Logs Page
Shows data loading logs, errors, and system diagnostics
"""

import streamlit as st
import pandas as pd
from datetime import datetime


def render_debug_page(debug_info):
    """Render debug and logs page"""

    st.title("🔧 Debug & System Logs")

    if not debug_info:
        st.warning("No debug information available. Data may not have loaded yet.")
        return

    # System Info
    st.header("📊 System Information")
    col1, col2, col3 = st.columns(3)

    with col1:
        load_time = debug_info.get('load_time_str', 'N/A')
        # Handle case where it might be a datetime object
        if hasattr(load_time, 'strftime'):
            load_time = load_time.strftime("%Y-%m-%d %H:%M:%S")
        st.metric("Data Load Time", str(load_time))

    with col2:
        datasets_loaded = len([k for k in debug_info.keys() if k.endswith('_logs')])
        st.metric("Datasets Loaded", datasets_loaded)

    with col3:
        total_errors = sum([len(debug_info.get(f'{k}_errors', [])) for k in ['master', 'service', 'backorder', 'inventory']])
        st.metric("Total Errors", total_errors, delta=None if total_errors == 0 else "⚠️")

    st.divider()

    # Data Loading Logs
    st.header("📋 Data Loading Logs")

    log_sections = {
        "Master Data": "master_logs",
        "Orders (Unified)": "orders_logs",
        "Orders (Item Lookup)": "orders_item_logs",
        "Orders (Header Lookup)": "orders_header_logs",
        "Deliveries (Unified)": "deliveries_logs",
        "Service Data": "service_logs",
        "Backorder Data": "backorder_logs",
        "Inventory Data": "inventory_logs",
        "Inventory Analysis": "analysis_logs"
    }

    for section_name, log_key in log_sections.items():
        if log_key in debug_info and debug_info[log_key]:
            with st.expander(f"📄 {section_name} Logs", expanded=False):
                logs = debug_info[log_key]

                # Categorize logs by type
                info_logs = [log for log in logs if log.startswith("INFO:")]
                warning_logs = [log for log in logs if log.startswith("WARNING:")]
                error_logs = [log for log in logs if log.startswith("ERROR:")]

                # Show summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Info", len(info_logs))
                with col2:
                    st.metric("Warnings", len(warning_logs), delta="⚠️" if len(warning_logs) > 0 else None)
                with col3:
                    st.metric("Errors", len(error_logs), delta="❌" if len(error_logs) > 0 else None)

                # Show logs
                if error_logs:
                    st.error("**Errors:**")
                    for log in error_logs:
                        st.text(log)

                if warning_logs:
                    st.warning("**Warnings:**")
                    for log in warning_logs:
                        st.text(log)

                if info_logs and st.checkbox(f"Show Info logs for {section_name}", key=f"show_info_{log_key}"):
                    st.info("**Info:**")
                    for log in info_logs:
                        st.text(log)

    st.divider()

    # Error Details
    st.header("❌ Error Details")

    error_sections = {
        "Master Data Errors": "master_errors",
        "Service Data Errors": "service_errors",
        "Backorder Data Errors": "backorder_errors",
        "Inventory Data Errors": "inventory_errors"
    }

    has_errors = False
    for section_name, error_key in error_sections.items():
        if error_key in debug_info and debug_info[error_key] is not None and not debug_info[error_key].empty:
            has_errors = True
            with st.expander(f"⚠️ {section_name}", expanded=True):
                st.dataframe(debug_info[error_key], hide_index=True, use_container_width=True)

    if not has_errors:
        st.success("✅ No errors detected in data loading!")

    st.divider()

    # Data Shape Info
    st.header("📐 Data Shape Information")

    shape_info = []
    for key in ['master', 'service', 'backorder', 'inventory', 'inventory_analysis']:
        df_key = f'{key}_df'
        if df_key in debug_info and debug_info[df_key] is not None:
            df = debug_info[df_key]
            shape_info.append({
                'Dataset': key.replace('_', ' ').title(),
                'Rows': len(df),
                'Columns': len(df.columns),
                'Memory (MB)': round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2)
            })

    if shape_info:
        st.dataframe(pd.DataFrame(shape_info), hide_index=True, use_container_width=True)

    st.divider()

    # Column Information
    st.header("📊 Column Information")

    dataset_selector = st.selectbox(
        "Select dataset to inspect:",
        options=['master', 'service', 'backorder', 'inventory', 'inventory_analysis']
    )

    df_key = f'{dataset_selector}_df'
    if df_key in debug_info and debug_info[df_key] is not None:
        df = debug_info[df_key]

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Column Names")
            st.dataframe(pd.DataFrame({'Column': df.columns}), hide_index=True)

        with col2:
            st.subheader("Data Types")
            dtypes_df = pd.DataFrame({
                'Column': df.dtypes.index,
                'Type': df.dtypes.values.astype(str),
                'Non-Null': df.count().values,
                'Null': df.isna().sum().values
            })
            st.dataframe(dtypes_df, hide_index=True)

        # Sample data
        st.subheader("Sample Data (First 5 Rows)")
        st.dataframe(df.head(5), use_container_width=True)
    else:
        st.warning(f"Dataset '{dataset_selector}' not available.")

    st.divider()

    # Cache Information
    st.header("💾 Cache Information")

    st.info("""
    **Cache Settings:**
    - Cache TTL: 3600 seconds (1 hour)
    - Cache Type: Streamlit @st.cache_data
    - Clear Cache: Use the button in the sidebar or re-upload files

    **Performance Optimizations:**
    - ✅ Unified file loading (reads large files once)
    - ✅ Column selection (loads only needed columns)
    - ✅ Streamlit caching (persists data across interactions)
    """)

    # Clear cache button
    if st.button("🗑️ Clear Cache & Reload Data"):
        st.cache_data.clear()
        st.success("Cache cleared! Reloading page...")
        st.rerun()
