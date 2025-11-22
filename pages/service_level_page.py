"""
Service Level Page
Detailed delivery performance tracking and analysis
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import (
    render_page_header, render_kpi_row, render_chart,
    render_data_table, render_filter_section
)

def get_service_level_filters(service_data):
    """Define filters for service level page"""
    if service_data.empty:
        return []

    filters = []

    # Customer filter
    if 'customer_name' in service_data.columns:
        customers = ['All'] + sorted(service_data['customer_name'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "Customer",
            "options": customers,
            "key": "sl_customer_filter"
        })

    # Month filter
    if 'ship_month' in service_data.columns:
        months = ['All'] + sorted(service_data['ship_month'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "Month",
            "options": months,
            "key": "sl_month_filter"
        })

    return filters

def apply_service_filters(service_data, filter_values):
    """
    OPTIMIZATION: Apply selected filters to service data without unnecessary copy.
    Boolean indexing creates new dataframes, so no explicit copy is needed.
    """
    filtered = service_data

    if 'sl_customer_filter' in filter_values and filter_values['sl_customer_filter'] != 'All':
        filtered = filtered[filtered['customer_name'] == filter_values['sl_customer_filter']]

    if 'sl_month_filter' in filter_values and filter_values['sl_month_filter'] != 'All':
        filtered = filtered[filtered['ship_month'] == filter_values['sl_month_filter']]

    return filtered

def calculate_service_metrics(service_data):
    """Calculate service level metrics"""
    if service_data.empty:
        return {}

    total_orders = len(service_data)
    on_time_orders = service_data['on_time'].sum() if 'on_time' in service_data.columns else 0
    on_time_pct = (on_time_orders / total_orders * 100) if total_orders > 0 else 0

    total_units = service_data['units_issued'].sum() if 'units_issued' in service_data.columns else 0
    avg_days = service_data['days_to_deliver'].mean() if 'days_to_deliver' in service_data.columns else 0

    return {
        "On-Time %": {
            "value": f"{on_time_pct:.1f}%",
            "help": f"**Business Logic:** Percentage of orders delivered within 7 days of order creation. On-Time Flag = (Ship Date - Order Date) <= 7 days. Current: {on_time_pct:.1f}% ({on_time_orders:,} of {total_orders:,} orders). Formula: (COUNT(WHERE on_time = TRUE) / COUNT(orders)) × 100"
        },
        "Total Orders": {
            "value": f"{total_orders:,}",
            "help": "**Business Logic:** Count of all order lines with completed deliveries in the selected period. Each line represents a SKU on an order that was shipped. Formula: COUNT(DISTINCT order_line)"
        },
        "Total Units": {
            "value": f"{int(total_units):,}",
            "help": "**Business Logic:** Sum of all units shipped across all deliveries. Represents total volume fulfilled. Formula: SUM(units_issued)"
        },
        "Avg Days to Deliver": {
            "value": f"{avg_days:.1f}",
            "help": f"**Business Logic:** Average cycle time from order creation to shipment. Days to Deliver = Ship Date - Order Date. Current average: {avg_days:.1f} days. Target: ≤7 days (95% on-time). Formula: AVG(ship_date - order_date)"
        }
    }

# ===== TAB-SPECIFIC RENDER FUNCTIONS =====

def render_monthly_trends_tab(filtered_data):
    """Render Monthly Trends tab content"""
    st.subheader("Monthly Performance Trends")

    if 'ship_month' not in filtered_data.columns:
        st.info("No monthly data available")
        return

    monthly = filtered_data.groupby('ship_month').agg({
        'on_time': ['sum', 'count'],
        'units_issued': 'sum',
        'days_to_deliver': 'mean'
    }).reset_index()

    monthly.columns = ['month', 'on_time_count', 'total_count', 'total_units', 'avg_days']
    monthly['on_time_pct'] = (monthly['on_time_count'] / monthly['total_count'] * 100)
    monthly = monthly.sort_values('month')

    # Create dual-axis chart
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=monthly['month'],
        y=monthly['total_count'],
        name='Total Orders',
        marker_color='lightblue',
        yaxis='y'
    ))

    fig.add_trace(go.Scatter(
        x=monthly['month'],
        y=monthly['on_time_pct'],
        name='On-Time %',
        line=dict(color='green', width=3),
        marker=dict(size=8),
        yaxis='y2'
    ))

    fig.update_layout(
        xaxis_title="Month",
        yaxis=dict(title="Order Count", side='left'),
        yaxis2=dict(title="On-Time %", overlaying='y', side='right', range=[0, 100]),
        hovermode='x unified'
    )

    render_chart(fig, height=400)

def render_customer_performance_tab(filtered_data):
    """Render Customer Performance tab content"""
    st.subheader("Customer Performance Breakdown")

    if 'customer_name' not in filtered_data.columns:
        st.info("No customer data available")
        return

    customer_summary = filtered_data.groupby('customer_name').agg({
        'on_time': ['sum', 'count'],
        'units_issued': 'sum',
        'days_to_deliver': 'mean'
    }).reset_index()

    customer_summary.columns = ['Customer', 'On_Time_Count', 'Total_Orders', 'Total_Units', 'Avg_Days']
    customer_summary['On_Time_%'] = (customer_summary['On_Time_Count'] / customer_summary['Total_Orders'] * 100).round(1)

    # Select display columns
    display_cols = ['Customer', 'Total_Orders', 'On_Time_%', 'Total_Units', 'Avg_Days']
    customer_summary = customer_summary[display_cols].sort_values('Total_Orders', ascending=False)

    render_data_table(
        customer_summary,
        max_rows=20,
        downloadable=True,
        download_filename="service_level_by_customer.csv"
    )

def render_detailed_records_tab(filtered_data):
    """Render Detailed Records tab content"""
    st.subheader("Detailed Delivery Records")

    display_columns = ['customer_name', 'ship_month', 'units_issued', 'days_to_deliver', 'on_time']
    available_cols = [col for col in display_columns if col in filtered_data.columns]

    render_data_table(
        filtered_data[available_cols],
        max_rows=100,
        downloadable=True,
        download_filename="service_level_detail.csv"
    )

# ===== MAIN RENDER FUNCTION =====

def render_service_level_page(service_data):
    """Main service level page render function with tabbed interface"""

    # Page header
    render_page_header(
        "Service Level Performance",
        icon="🚚",
        subtitle="Track delivery performance and on-time metrics"
    )

    if service_data.empty:
        st.warning("No service level data available")
        return

    # Render filters
    filters_config = get_service_level_filters(service_data)
    filter_values = render_filter_section(filters_config)

    # Apply filters
    filtered_data = apply_service_filters(service_data, filter_values)

    if filtered_data.empty:
        st.info("No data matches the selected filters")
        return

    # Calculate and display metrics (shown at top level, above tabs)
    metrics = calculate_service_metrics(filtered_data)
    render_kpi_row(metrics)

    st.divider()

    # Tabbed Interface
    tab1, tab2, tab3 = st.tabs([
        "📈 Monthly Trends",
        "👥 Customer Performance",
        "📋 Detailed Records"
    ])

    with tab1:
        render_monthly_trends_tab(filtered_data)

    with tab2:
        render_customer_performance_tab(filtered_data)

    with tab3:
        render_detailed_records_tab(filtered_data)