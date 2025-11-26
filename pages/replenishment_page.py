"""
Replenishment Planning Page
Suggested order quantities based on:
- Demand forecast (exponential smoothing with anomaly detection & seasonality)
- Current inventory
- Open vendor POs (domestic + international)
- Backorders
- Safety stock calculations (95% service level)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui_components import (
    render_page_header, render_kpi_row, render_chart,
    render_data_table, render_info_box
)

# Import replenishment planning functions
from replenishment_planning import (
    generate_replenishment_plan,
    DEFAULT_SERVICE_LEVEL,
    DEFAULT_LEAD_TIME_DAYS,
    REVIEW_PERIOD_DAYS
)


def render_replenishment_settings_sidebar():
    """Render adjustable settings in sidebar for replenishment planning"""

    st.sidebar.header("🔍 Filters")

    # Vendor filter
    vendor_filter = st.sidebar.text_input(
        "Filter by Vendor",
        value="",
        key="replenishment_vendor_filter",
        placeholder="Enter vendor name...",
        help="Filter results to specific vendor (partial match)"
    )

    # SKU search
    sku_search = st.sidebar.text_input(
        "Search SKU",
        value="",
        key="replenishment_sku_search",
        placeholder="Enter SKU code...",
        help="Search for specific SKU (partial match)"
    )

    st.sidebar.divider()

    # ===== SERVICE LEVEL SETTINGS =====
    st.sidebar.header("⚙️ Planning Parameters")

    service_level = st.sidebar.slider(
        "Service Level (%)",
        min_value=85,
        max_value=99,
        value=95,
        step=1,
        key="replenishment_service_level",
        help="Target service level for safety stock calculation. 95% is standard."
    )

    default_lead_time = st.sidebar.number_input(
        "Default Lead Time (days)",
        min_value=30,
        max_value=180,
        value=73,
        step=15,
        key="replenishment_lead_time",
        help="Default lead time for domestic vendors (73 days median from PO history)"
    )

    review_period = st.sidebar.selectbox(
        "Review Period",
        options=["Weekly (7 days)", "Bi-Weekly (14 days)", "Monthly (30 days)"],
        index=1,  # Default to Bi-Weekly
        key="replenishment_review_period",
        help="How often orders are placed"
    )

    # Parse review period
    if "7 days" in review_period:
        review_days = 7
    elif "14 days" in review_period:
        review_days = 14
    else:
        review_days = 30

    st.sidebar.divider()

    # ===== DISPLAY OPTIONS =====
    with st.sidebar.expander("📊 Display Options", expanded=False):
        show_all_skus = st.checkbox(
            "Show all SKUs (not just below reorder point)",
            value=False,
            key="replenishment_show_all",
            help="By default, only SKUs below reorder point are shown"
        )

        min_order_qty = st.number_input(
            "Minimum Order Qty Filter",
            min_value=0,
            max_value=10000,
            value=0,
            step=100,
            key="replenishment_min_order",
            help="Only show items with suggested order >= this quantity"
        )

        sort_by = st.selectbox(
            "Sort Results By",
            options=["Priority Score (High to Low)", "Suggested Order Value (High to Low)", "Days of Supply (Low to High)", "Vendor"],
            index=0,
            key="replenishment_sort"
        )

    return {
        'vendor_filter': vendor_filter,
        'sku_search': sku_search,
        'service_level': service_level / 100.0,  # Convert to decimal
        'lead_time_days': default_lead_time,
        'review_period_days': review_days,
        'show_all_skus': show_all_skus,
        'min_order_qty': min_order_qty,
        'sort_by': sort_by
    }


def create_vendor_summary_chart(plan_df):
    """Create a bar chart showing order value by vendor"""
    if plan_df.empty:
        return None

    # Aggregate by vendor (column is 'vendor' from replenishment_planning)
    vendor_summary = plan_df.groupby('vendor').agg({
        'suggested_order_qty': 'sum',
        'order_value': 'sum',
        'sku': 'count',
        'priority_score': 'mean'
    }).reset_index()

    vendor_summary.columns = ['Vendor', 'Total Qty', 'Total Value', 'SKU Count', 'Avg Priority']
    vendor_summary = vendor_summary.sort_values('Total Value', ascending=False).head(15)

    fig = px.bar(
        vendor_summary,
        x='Vendor',
        y='Total Value',
        color='Avg Priority',
        color_continuous_scale='RdYlGn_r',
        title='Order Value by Vendor (Top 15)',
        labels={'Total Value': 'Order Value ($)', 'Avg Priority': 'Avg Priority Score'},
        hover_data=['Total Qty', 'SKU Count']
    )

    fig.update_layout(
        xaxis_tickangle=-45,
        showlegend=False,
        height=400
    )

    return fig


def create_priority_distribution_chart(plan_df):
    """Create a histogram of priority scores"""
    if plan_df.empty:
        return None

    fig = px.histogram(
        plan_df,
        x='priority_score',
        nbins=20,
        title='Distribution of Priority Scores',
        labels={'priority_score': 'Priority Score', 'count': 'Number of SKUs'},
        color_discrete_sequence=['#3498db']
    )

    fig.update_layout(
        xaxis_title='Priority Score (Higher = More Urgent)',
        yaxis_title='Number of SKUs',
        height=300
    )

    return fig


def create_days_of_supply_chart(plan_df):
    """Create a scatter plot of days of supply vs suggested order"""
    if plan_df.empty or len(plan_df) > 500:
        return None  # Skip if too many points

    fig = px.scatter(
        plan_df,
        x='days_of_supply',
        y='suggested_order_qty',
        color='priority_score',
        size='order_value',
        hover_data=['sku', 'vendor', 'on_hand_qty', 'daily_demand'],
        title='Days of Supply vs Suggested Order Quantity',
        color_continuous_scale='RdYlGn_r',
        labels={
            'days_of_supply': 'Current Days of Supply',
            'suggested_order_qty': 'Suggested Order Qty',
            'priority_score': 'Priority'
        }
    )

    fig.update_layout(height=400)

    return fig


def format_currency(value):
    """Format a value as currency"""
    if pd.isna(value) or value == 0:
        return "$0"
    return f"${value:,.0f}"


def format_display_dataframe(df: pd.DataFrame, column_rename: dict) -> pd.DataFrame:
    """Format a dataframe for display with proper number formatting.

    Args:
        df: DataFrame to format
        column_rename: Dict mapping old column names to new display names

    Returns:
        Formatted DataFrame ready for display
    """
    display_df = df.rename(columns=column_rename)

    # Define formatting rules by column type
    integer_cols = ['Suggested Qty', 'On Hand', 'Reorder Point', 'Safety Stock',
                    'Open PO Qty', 'Backorders']

    for col in integer_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "0")

    if 'Order Value ($)' in display_df.columns:
        display_df['Order Value ($)'] = display_df['Order Value ($)'].apply(
            lambda x: f"${x:,.0f}" if pd.notna(x) else "$0"
        )

    if 'Priority' in display_df.columns:
        display_df['Priority'] = display_df['Priority'].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else "0"
        )

    if 'Daily Demand' in display_df.columns:
        display_df['Daily Demand'] = display_df['Daily Demand'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) else "0"
        )

    if 'Days of Supply' in display_df.columns:
        display_df['Days of Supply'] = display_df['Days of Supply'].apply(
            lambda x: f"{x:.0f}" if pd.notna(x) and x != float('inf') else "N/A"
        )

    return display_df


def render_replenishment_page(
    inventory_data: pd.DataFrame,
    demand_forecast_data: pd.DataFrame,
    backorder_data: pd.DataFrame,
    vendor_pos_data: pd.DataFrame,
    atl_fulfillment_data: pd.DataFrame,
    master_data: pd.DataFrame,
    lead_time_lookup: dict = None
):
    """
    Main render function for the Replenishment Planning page.

    Args:
        inventory_data: Current inventory levels
        demand_forecast_data: Demand forecast from demand_forecasting.py
        backorder_data: Current backorders
        vendor_pos_data: Open domestic vendor POs
        atl_fulfillment_data: Open international shipments
        master_data: Master data for SKU details
        lead_time_lookup: Optional dict mapping SKU to lead time days
    """

    # Page header
    render_page_header(
        title="Replenishment Planning",
        icon="📋",
        subtitle="Suggested orders based on demand forecast, inventory, and safety stock"
    )

    # Get sidebar settings
    settings = render_replenishment_settings_sidebar()

    # Validate required data
    if inventory_data is None or inventory_data.empty:
        render_info_box("No inventory data available. Please load inventory data.", type="warning")
        return

    if demand_forecast_data is None or demand_forecast_data.empty:
        render_info_box("No demand forecast data available. Please navigate to Demand Forecasting first to generate forecasts.", type="warning")
        return

    # Generate replenishment plan
    with st.spinner("Calculating replenishment plan..."):
        try:
            plan_df = generate_replenishment_plan(
                inventory_df=inventory_data,
                demand_forecast_df=demand_forecast_data,
                backorder_df=backorder_data,
                domestic_po_df=vendor_pos_data,
                international_po_df=atl_fulfillment_data,
                master_df=master_data,
                service_level=settings['service_level'],
                default_lead_time_days=settings['lead_time_days'],
                review_period_days=settings['review_period_days']
            )
        except Exception as e:
            render_info_box(f"Error generating replenishment plan: {str(e)}", type="error")
            st.exception(e)
            return

    if plan_df is None or plan_df.empty:
        render_info_box("No SKUs require replenishment at this time.", type="info")
        return

    # ===== PROMINENT SKU LOOKUP =====
    st.markdown("### 🔍 SKU Lookup")
    lookup_col1, lookup_col2 = st.columns([3, 1])

    with lookup_col1:
        sku_lookup = st.text_input(
            "Enter SKU to check if it needs replenishment:",
            value="",
            key="sku_lookup_main",
            placeholder="Type SKU code here (e.g., Z2NRE23 RE0017)...",
            label_visibility="collapsed"
        )

    with lookup_col2:
        lookup_all_skus = st.checkbox("Search ALL SKUs", value=True,
                                       help="Check to search all SKUs, not just those below reorder point")

    # SKU Lookup Result
    if sku_lookup:
        # Search in full plan_df to show if SKU exists at all
        sku_matches = plan_df[plan_df['sku'].str.contains(sku_lookup, case=False, na=False)]

        if not sku_matches.empty:
            st.markdown("#### SKU Lookup Results")
            for _, row in sku_matches.iterrows():
                sku_name = row['sku']
                suggested_qty = row.get('suggested_order_qty', 0)
                below_rop = row.get('below_reorder_point', False)
                on_hand = row.get('on_hand_qty', 0)
                dos = row.get('days_of_supply', 0)
                reorder_pt = row.get('reorder_point', 0)
                vendor = row.get('vendor', 'Unknown')
                priority = row.get('priority_score', 0)

                if below_rop and suggested_qty > 0:
                    st.success(f"""
                    **✅ {sku_name}** - NEEDS REPLENISHMENT
                    - **Suggested Order Qty:** {suggested_qty:,.0f} units
                    - **On Hand:** {on_hand:,.0f} | **Days of Supply:** {dos:.1f} | **Reorder Point:** {reorder_pt:,.0f}
                    - **Vendor:** {vendor} | **Priority Score:** {priority:.0f}
                    """)
                else:
                    st.info(f"""
                    **ℹ️ {sku_name}** - NO ORDER NEEDED
                    - **On Hand:** {on_hand:,.0f} | **Days of Supply:** {dos:.1f} | **Reorder Point:** {reorder_pt:,.0f}
                    - **Reason:** {'Above reorder point' if not below_rop else 'No suggested quantity'}
                    """)
        else:
            st.warning(f"SKU '{sku_lookup}' not found in the replenishment analysis. This SKU may not have demand forecast data or may not be in the RETAIL PERMANENT category.")

    st.divider()

    # Apply filters FIRST so we can use filtered data for summary
    filtered_df = plan_df.copy()

    # Filter: Only show items below reorder point (unless user wants all)
    if not settings['show_all_skus'] and not lookup_all_skus:
        filtered_df = filtered_df[filtered_df['below_reorder_point'] == True]

    # Filter: Vendor
    if settings['vendor_filter']:
        filtered_df = filtered_df[
            filtered_df['vendor'].str.contains(settings['vendor_filter'], case=False, na=False)
        ]

    # Filter: SKU search (from sidebar)
    if settings['sku_search']:
        filtered_df = filtered_df[
            filtered_df['sku'].str.contains(settings['sku_search'], case=False, na=False)
        ]

    # Filter: Minimum order quantity
    if settings['min_order_qty'] > 0:
        filtered_df = filtered_df[filtered_df['suggested_order_qty'] >= settings['min_order_qty']]

    # ===== GRAND TOTAL SUMMARY BOX (uses filtered data - default is RETAIL PERMANENT) =====
    total_suggested_qty = filtered_df['suggested_order_qty'].sum() if 'suggested_order_qty' in filtered_df.columns else 0
    total_suggested_value = filtered_df['order_value'].sum() if 'order_value' in filtered_df.columns else 0
    total_skus_need_orders = len(filtered_df[filtered_df['below_reorder_point'] == True]) if 'below_reorder_point' in filtered_df.columns else len(filtered_df)

    st.markdown("""
    <div style="background: linear-gradient(135deg, #1e3a5f, #2d5a87); padding: 20px; border-radius: 12px; margin-bottom: 20px;">
        <h2 style="color: white; margin: 0 0 15px 0; text-align: center;">📦 Total Replenishment Summary (RETAIL PERMANENT)</h2>
        <div style="display: flex; justify-content: space-around; flex-wrap: wrap;">
            <div style="text-align: center; padding: 10px 20px;">
                <div style="color: #90cdf4; font-size: 14px; text-transform: uppercase;">Total Units Needed</div>
                <div style="color: white; font-size: 32px; font-weight: bold;">{:,.0f}</div>
            </div>
            <div style="text-align: center; padding: 10px 20px;">
                <div style="color: #90cdf4; font-size: 14px; text-transform: uppercase;">Total Order Value</div>
                <div style="color: white; font-size: 32px; font-weight: bold;">${:,.0f}</div>
            </div>
            <div style="text-align: center; padding: 10px 20px;">
                <div style="color: #90cdf4; font-size: 14px; text-transform: uppercase;">SKUs Need Orders</div>
                <div style="color: white; font-size: 32px; font-weight: bold;">{:,}</div>
            </div>
        </div>
    </div>
    """.format(total_suggested_qty, total_suggested_value, total_skus_need_orders), unsafe_allow_html=True)

    # ===== SUGGESTED ORDERS TABLE (right after summary) =====
    st.subheader("📋 Suggested Orders")

    # Filter out $0 order values and sort by order_value descending
    table_df = filtered_df[filtered_df['order_value'] > 0].copy()
    table_df = table_df.sort_values('order_value', ascending=False)

    # Column configuration for display
    DISPLAY_COLUMNS = [
        'sku', 'product_name', 'vendor', 'suggested_order_qty',
        'order_value', 'priority_score', 'on_hand_qty', 'days_of_supply',
        'reorder_point', 'safety_stock', 'open_po_qty', 'backorder_qty',
        'daily_demand', 'lead_time_days'
    ]

    COLUMN_RENAME = {
        'sku': 'SKU',
        'product_name': 'SKU Description',
        'vendor': 'Vendor',
        'suggested_order_qty': 'Suggested Qty',
        'order_value': 'Order Value ($)',
        'priority_score': 'Priority',
        'on_hand_qty': 'On Hand',
        'days_of_supply': 'Days of Supply',
        'reorder_point': 'Reorder Point',
        'safety_stock': 'Safety Stock',
        'open_po_qty': 'Open PO Qty',
        'backorder_qty': 'Backorders',
        'daily_demand': 'Daily Demand',
        'lead_time_days': 'Lead Time (days)'
    }

    # Filter to available columns and format
    available_cols = [c for c in DISPLAY_COLUMNS if c in table_df.columns]
    display_df = format_display_dataframe(table_df[available_cols].copy(), COLUMN_RENAME)

    # Show count
    st.caption(f"Showing {len(display_df):,} items | Sorted by Order Value (highest first)")

    # Data table with download
    st.dataframe(display_df, use_container_width=True, height=400)

    # Download buttons
    col_dl1, col_dl2, col_dl3 = st.columns([1, 1, 2])

    with col_dl1:
        csv_buffer = BytesIO()
        filtered_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        st.download_button(
            label="📥 Download Full Data (CSV)",
            data=csv_buffer,
            file_name=f"replenishment_plan_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

    st.divider()

    # ===== CHARTS ROW =====
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        vendor_chart = create_vendor_summary_chart(filtered_df)
        if vendor_chart:
            st.plotly_chart(vendor_chart, use_container_width=True)

    with chart_col2:
        priority_chart = create_priority_distribution_chart(filtered_df)
        if priority_chart:
            st.plotly_chart(priority_chart, use_container_width=True)

    # Show filter summary at bottom
    if settings['vendor_filter'] or settings['sku_search'] or settings['min_order_qty'] > 0:
        filter_parts = []
        if settings['vendor_filter']:
            filter_parts.append(f"Vendor: '{settings['vendor_filter']}'")
        if settings['sku_search']:
            filter_parts.append(f"SKU: '{settings['sku_search']}'")
        if settings['min_order_qty'] > 0:
            filter_parts.append(f"Min Qty: {settings['min_order_qty']}")
        st.caption(f"🔍 Active filters: {', '.join(filter_parts)} | Showing {len(filtered_df):,} of {len(plan_df):,} SKUs")


    # ===== VENDOR BREAKDOWN =====
    with st.expander("📊 Vendor Breakdown", expanded=False):
        if 'vendor' in filtered_df.columns:
            # Group by vendor
            vendor_summary = filtered_df.groupby('vendor').agg({
                'suggested_order_qty': 'sum',
                'order_value': 'sum',
                'sku': 'count',
                'priority_score': 'mean',
                'backorder_qty': 'sum'
            }).reset_index()

            vendor_summary.columns = ['Vendor', 'Total Order Qty', 'Total Order Value',
                                      'SKU Count', 'Avg Priority', 'Total Backorders']
            vendor_summary = vendor_summary.sort_values('Total Order Value', ascending=False)

            # Format for display
            vendor_display = vendor_summary.copy()
            vendor_display['Total Order Qty'] = vendor_display['Total Order Qty'].apply(lambda x: f"{x:,.0f}")
            vendor_display['Total Order Value'] = vendor_display['Total Order Value'].apply(lambda x: f"${x:,.0f}")
            vendor_display['Avg Priority'] = vendor_display['Avg Priority'].apply(lambda x: f"{x:.1f}")
            vendor_display['Total Backorders'] = vendor_display['Total Backorders'].apply(lambda x: f"{x:,.0f}")

            st.dataframe(vendor_display, use_container_width=True)

    # ===== METHODOLOGY NOTES =====
    with st.expander("ℹ️ Calculation Methodology", expanded=False):
        st.markdown(f"""
        ### Safety Stock Calculation
        - **Service Level**: {settings['service_level']*100:.0f}% (Z-score: {1.65 if settings['service_level'] == 0.95 else 'varies'})
        - **Formula**: `Safety Stock = Z × σ(demand) × √(Lead Time)`

        ### Reorder Point
        - **Formula**: `Reorder Point = (Daily Demand × Lead Time) + Safety Stock`

        ### Order-Up-To Level (Periodic Review)
        - **Review Period**: {settings['review_period_days']} days
        - **Formula**: `Order-Up-To = Daily Demand × (Lead Time + Review Period) + Safety Stock`

        ### Suggested Order Quantity (Net Requirements Method)
        - **Formula**: `Suggested Order = max(0, Order-Up-To - Available Supply) + Backorders`
        - **Available Supply** = On-Hand + Open PO Qty

        ### Priority Score (0-100)
        Higher scores indicate more urgent need:
        - Days of supply weight: 40%
        - Backorder impact: 30%
        - Demand velocity: 30%

        ### Data Sources
        - **Inventory**: Current on-hand quantities
        - **Demand Forecast**: Exponential smoothing with anomaly detection and seasonal adjustment from Demand Forecasting module
        - **Open POs**: Domestic Vendor POs + ATL Fulfillment (international)
        - **Backorders**: Current backorder quantities
        """)

    # ===== FOOTER INFO =====
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
               f"Lead time default: {settings['lead_time_days']} days | "
               f"Review period: {settings['review_period_days']} days")
