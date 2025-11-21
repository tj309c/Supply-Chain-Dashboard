"""
Overview Page - Executive Dashboard
High-level KPIs and summary metrics across all supply chain functions
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import render_page_header, render_kpi_row, render_chart, render_info_box

def calculate_overview_metrics(service_data, backorder_data, inventory_data):
    """Calculate high-level metrics for overview page"""
    metrics = {}

    # Service Level Metrics
    if not service_data.empty:
        total_orders = len(service_data)
        on_time_orders = service_data['on_time'].sum() if 'on_time' in service_data.columns else 0
        on_time_pct = (on_time_orders / total_orders * 100) if total_orders > 0 else 0

        metrics['service_level'] = {
            "value": f"{on_time_pct:.1f}%",
            "delta": None,
            "help": f"**Business Logic:** On-Time Delivery Rate = percentage of orders shipped within 7 days. Current: {on_time_pct:.1f}% ({on_time_orders:,} / {total_orders:,}). Target: 95%. Formula: (COUNT(WHERE on_time = TRUE) / COUNT(orders)) × 100"
        }

        metrics['total_orders'] = {
            "value": f"{total_orders:,}",
            "delta": None,
            "help": "**Business Logic:** Total count of order lines processed (shipped). Each order line is a SKU on a customer order. Formula: COUNT(order_lines)"
        }
    else:
        metrics['service_level'] = {"value": "N/A", "delta": None}
        metrics['total_orders'] = {"value": "N/A", "delta": None}

    # Backorder Metrics
    if not backorder_data.empty:
        total_backorders = backorder_data['backorder_qty'].sum() if 'backorder_qty' in backorder_data.columns else 0
        avg_days_on_bo = backorder_data['days_on_backorder'].mean() if 'days_on_backorder' in backorder_data.columns else 0

        metrics['backorders'] = {
            "value": f"{int(total_backorders):,}",
            "delta": None,
            "help": f"**Business Logic:** Total units awaiting fulfillment across all open backorders. Current: {int(total_backorders):,} units. Formula: SUM(backorder_qty WHERE backorder_qty > 0)"
        }

        metrics['avg_backorder_age'] = {
            "value": f"{avg_days_on_bo:.0f} days",
            "delta": None,
            "help": f"**Business Logic:** Average time backorders have been open. Days on Backorder = Today - Order Creation Date. Current average: {avg_days_on_bo:.1f} days. Formula: AVG(TODAY - order_date)"
        }
    else:
        metrics['backorders'] = {"value": "0", "delta": None}
        metrics['avg_backorder_age'] = {"value": "N/A", "delta": None}

    # Inventory Metrics
    if not inventory_data.empty:
        total_stock = inventory_data['on_hand_qty'].sum() if 'on_hand_qty' in inventory_data.columns else 0

        metrics['inventory_units'] = {
            "value": f"{int(total_stock):,}",
            "delta": None,
            "help": "Total units in inventory"
        }
    else:
        metrics['inventory_units'] = {"value": "N/A", "delta": None}

    return metrics

def render_service_level_chart(service_data):
    """Render service level trend chart"""
    if service_data.empty or 'ship_month' not in service_data.columns:
        return None

    # Group by month
    monthly = service_data.groupby('ship_month').agg({
        'on_time': ['sum', 'count']
    }).reset_index()

    monthly.columns = ['month', 'on_time_count', 'total_count']
    monthly['on_time_pct'] = (monthly['on_time_count'] / monthly['total_count'] * 100)

    # Sort by month
    monthly = monthly.sort_values('month')

    # Create chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=monthly['month'],
        y=monthly['on_time_pct'],
        mode='lines+markers',
        name='On-Time %',
        line=dict(color='#2E86AB', width=3),
        marker=dict(size=8)
    ))

    # Add target line
    fig.add_hline(y=95, line_dash="dash", line_color="green", annotation_text="Target: 95%")

    fig.update_layout(
        title="Service Level Trend",
        xaxis_title="Month",
        yaxis_title="On-Time Delivery %",
        yaxis_range=[0, 100]
    )

    return fig

def render_backorder_chart(backorder_data):
    """Render backorder trend chart"""
    if backorder_data.empty or 'days_on_backorder' not in backorder_data.columns:
        return None

    # Create aging buckets
    backorder_data['age_bucket'] = pd.cut(
        backorder_data['days_on_backorder'],
        bins=[0, 7, 14, 30, 60, float('inf')],
        labels=['0-7 days', '8-14 days', '15-30 days', '31-60 days', '60+ days']
    )

    aging = backorder_data.groupby('age_bucket', observed=True)['backorder_qty'].sum().reset_index()

    # Create chart
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=aging['age_bucket'],
        y=aging['backorder_qty'],
        marker_color=['#06D6A0', '#FFD166', '#EF8354', '#F4442E', '#A71E2C']
    ))

    fig.update_layout(
        title="Backorder Aging Analysis",
        xaxis_title="Age Bucket",
        yaxis_title="Backorder Quantity"
    )

    return fig

def render_overview_page(service_data, backorder_data, inventory_data):
    """Main overview page render function"""

    # Page header
    render_page_header(
        "Executive Overview",
        icon="📊",
        subtitle="Key performance indicators across your end-to-end supply chain"
    )

    # Calculate metrics
    metrics = calculate_overview_metrics(service_data, backorder_data, inventory_data)

    # Render KPI row
    st.subheader("Key Performance Indicators")
    kpi_row_1 = {
        "Service Level": metrics.get('service_level', {}),
        "Total Orders": metrics.get('total_orders', {}),
        "Backorders": metrics.get('backorders', {})
    }
    render_kpi_row(kpi_row_1)

    st.divider()

    kpi_row_2 = {
        "Avg Backorder Age": metrics.get('avg_backorder_age', {}),
        "Inventory Units": metrics.get('inventory_units', {}),
        "": {"value": "", "delta": None}  # Placeholder for future metric
    }
    render_kpi_row(kpi_row_2)

    st.divider()

    # Charts section
    st.subheader("Performance Trends")

    col1, col2 = st.columns(2)

    with col1:
        service_chart = render_service_level_chart(service_data)
        if service_chart:
            render_chart(service_chart, height=350)
        else:
            render_info_box("No service level data available", type="info")

    with col2:
        backorder_chart = render_backorder_chart(backorder_data)
        if backorder_chart:
            render_chart(backorder_chart, height=350)
        else:
            render_info_box("No backorder data available", type="info")

    # Alerts section
    st.divider()
    st.subheader("🔔 Active Alerts")

    alerts = []

    # Check service level
    if not service_data.empty and 'on_time' in service_data.columns:
        on_time_pct = (service_data['on_time'].sum() / len(service_data) * 100)
        if on_time_pct < 90:
            alerts.append(("warning", f"Service level below target: {on_time_pct:.1f}% (Target: 95%)"))

    # Check backorders
    if not backorder_data.empty and 'days_on_backorder' in backorder_data.columns:
        old_backorders = len(backorder_data[backorder_data['days_on_backorder'] > 30])
        if old_backorders > 0:
            alerts.append(("warning", f"{old_backorders} backorders aged over 30 days"))

    if not alerts:
        st.success("✓ All metrics within normal range")
    else:
        for alert_type, message in alerts:
            render_info_box(message, type=alert_type)
