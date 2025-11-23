"""
UI Components Module
Modular, reusable UI components for the Supply Chain Dashboard
Easy to add, edit, and enhance without touching core logic
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

# ===== UI LAYOUT HELPERS =====

def render_page_header(title, icon="📦", subtitle=None):
    """Render consistent page headers"""
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()

def render_metric_card(label, value, delta=None, help_text=None):
    """Render a metric card with optional delta and help"""
    st.metric(label=label, value=value, delta=delta, help=help_text)

def render_kpi_row(metrics_dict):
    """
    Render a row of KPI metrics

    Args:
        metrics_dict: Dict with format {"Label": {"value": "123", "delta": "+5%", "help": "Help text"}}
    """
    cols = st.columns(len(metrics_dict))
    for idx, (label, data) in enumerate(metrics_dict.items()):
        with cols[idx]:
            # Normalize empty / None metric values so the UI doesn't render blank cards
            raw_value = data.get("value", "N/A")
            if raw_value is None or (isinstance(raw_value, str) and str(raw_value).strip() == ""):
                display_value = "N/A"
            else:
                display_value = raw_value

            st.metric(
                label=label,
                value=display_value,
                delta=data.get("delta"),
                help=data.get("help")
            )

def render_filter_section(filters_config):
    """
    Render a standardized filter section

    Args:
        filters_config: List of dicts with filter definitions
            [{"type": "selectbox", "label": "Customer", "options": [...], "key": "customer_filter"}]

    Returns:
        dict: Dictionary of filter values {key: selected_value}
    """
    filter_values = {}

    st.sidebar.header("🔍 Filters")

    for filter_def in filters_config:
        filter_type = filter_def.get("type", "selectbox")
        label = filter_def.get("label", "Filter")
        options = filter_def.get("options", [])
        key = filter_def.get("key", label.lower().replace(" ", "_"))
        default = filter_def.get("default")

        if filter_type == "selectbox":
            filter_values[key] = st.sidebar.selectbox(label, options, index=0 if default is None else options.index(default), key=key)
        elif filter_type == "multiselect":
            filter_values[key] = st.sidebar.multiselect(label, options, default=default, key=key)
        elif filter_type == "date":
            filter_values[key] = st.sidebar.date_input(label, value=default, key=key)
        elif filter_type == "slider":
            min_val = filter_def.get("min", 0)
            max_val = filter_def.get("max", 100)
            filter_values[key] = st.sidebar.slider(label, min_val, max_val, default or min_val, key=key)

    return filter_values

def render_data_table(df, title=None, max_rows=100, downloadable=True, download_filename="data.csv"):
    """
    Render a data table with optional download

    Args:
        df: Pandas DataFrame
        title: Optional section title
        max_rows: Maximum rows to display
        downloadable: Show download button
        download_filename: Name for downloaded file
    """
    if title:
        st.subheader(title)

    if df.empty:
        st.info("No data available")
        return

    # Display table
    st.dataframe(df.head(max_rows), width='stretch')

    if len(df) > max_rows:
        st.caption(f"Showing first {max_rows} of {len(df)} records")

    # Download button
    if downloadable:
        csv = df.to_csv(index=False).encode('utf-8')
        # Use id() to ensure unique key even if filename is the same
        unique_key = f"download_{download_filename}_{id(df)}"
        st.download_button(
            label="📥 Download Full Data",
            data=csv,
            file_name=download_filename,
            mime="text/csv",
            key=unique_key
        )

def render_chart(fig, title=None, height=400):
    """
    Render a Plotly chart with consistent styling

    Args:
        fig: Plotly figure object
        title: Optional chart title
        height: Chart height in pixels
    """
    if title:
        st.subheader(title)

    # Update layout for consistency
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        template="plotly_white"
    )

    st.plotly_chart(fig, width='stretch')

def render_info_box(message, type="info"):
    """
    Render an info/warning/error box

    Args:
        message: Message to display
        type: "info", "warning", "error", "success"
    """
    if type == "info":
        st.info(message)
    elif type == "warning":
        st.warning(message)
    elif type == "error":
        st.error(message)
    elif type == "success":
        st.success(message)

def render_section_header(title, description=None, collapsible=False):
    """
    Render a section header with optional description

    Args:
        title: Section title
        description: Optional description text
        collapsible: If True, returns an expander context
    """
    if collapsible:
        return st.expander(title, expanded=True)
    else:
        st.subheader(title)
        if description:
            st.caption(description)
        return None

# ===== NAVIGATION HELPERS =====

def get_main_navigation():
    """
    Define main navigation menu structure
    Returns list of menu items with page info
    """
    return [
        {
            "id": "overview",
            "label": "📊 Overview",
            "description": "Executive dashboard with key metrics"
        },
        {
            "id": "service_level",
            "label": "🚚 Service Level",
            "description": "Delivery performance and on-time metrics"
        },
        {
            "id": "backorders",
            "label": "⚠️ Backorders",
            "description": "Backorder tracking and aging analysis"
        },
        {
            "id": "inventory",
            "label": "📦 Inventory",
            "description": "Stock levels and inventory health"
        },
        {
            "id": "forecasting",
            "label": "📈 Forecasting",
            "description": "Demand forecasting and planning"
        },
        {
            "id": "inbound",
            "label": "🚛 Inbound Logistics",
            "description": "Purchase orders and supplier performance"
        },
        {
            "id": "debug",
            "label": "🔧 Debug & Logs",
            "description": "System logs, errors, and diagnostics"
        }
    ]

def render_navigation():
    """
    Render main navigation menu in sidebar
    Returns selected page ID
    """
    st.sidebar.title("🏭 POP Supply Chain")
    st.sidebar.caption("EssilorLuxottica End-to-End Platform")
    st.sidebar.divider()

    menu_items = get_main_navigation()

    # Simple radio button navigation
    selected = st.sidebar.radio(
        "Navigation",
        options=[item["label"] for item in menu_items],
        key="main_nav"
    )

    # Find the selected page ID
    selected_page = next((item for item in menu_items if item["label"] == selected), None)

    if selected_page:
        st.sidebar.caption(selected_page["description"])

    st.sidebar.divider()

    return selected_page["id"] if selected_page else "overview"

# ===== QUICK ACTIONS =====

def render_quick_actions():
    """Render quick action buttons in sidebar"""
    st.sidebar.header("⚡ Quick Actions")

    actions = []

    if st.sidebar.button("🔄 Refresh Data", width='stretch'):
        actions.append("refresh")

    if st.sidebar.button("📥 Export Report", width='stretch'):
        actions.append("export")

    if st.sidebar.button("🔔 View Alerts", width='stretch'):
        actions.append("alerts")

    return actions

# ===== DATA STATUS INDICATOR =====

def render_data_status(data_load_time=None, record_count=None):
    """Render data status indicator"""
    st.sidebar.divider()
    st.sidebar.caption("📊 Data Status")

    if data_load_time:
        st.sidebar.caption(f"Last Updated: {data_load_time.strftime('%H:%M:%S')}")

    if record_count:
        st.sidebar.caption(f"Records: {record_count:,}")

    st.sidebar.success("✓ Data Loaded")

# ===== EMPTY STATE HANDLERS =====

def render_empty_state(message="No data available", action_text=None, action_callback=None):
    """Render empty state with optional action"""
    st.info(f"ℹ️ {message}")
    if action_text and action_callback:
        if st.button(action_text):
            action_callback()

# ===== UTILITY FORMATTERS =====

def format_number(value, format_type="integer"):
    """Format numbers consistently"""
    if value is None:
        return "N/A"

    formats = {
        'integer': '{:,}',
        'currency': '${:,.0f}',
        'percentage': '{:.1f}%',
        'decimal': '{:.2f}'
    }

    try:
        return formats.get(format_type, '{}').format(value)
    except:
        return str(value)

def format_date(date_value, format_str='%Y-%m-%d'):
    """Format dates consistently"""
    if date_value is None:
        return "N/A"

    try:
        if isinstance(date_value, str):
            return date_value
        return date_value.strftime(format_str)
    except:
        return str(date_value)
