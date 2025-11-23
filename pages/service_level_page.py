"""
Service Level Page
Detailed delivery performance tracking and analysis
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os
from datetime import datetime # Import datetime
from scipy.stats import linregress # Import for linear regression
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

    # Year filter (for pages that have ship_year)
    if 'ship_year' in service_data.columns:
        years = ['All'] + sorted(service_data['ship_year'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "Year",
            "options": years,
            "key": "sl_year_filter"
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

    if 'sl_year_filter' in filter_values and filter_values['sl_year_filter'] != 'All':
        filtered = filtered[filtered['ship_year'] == filter_values['sl_year_filter']]

    return filtered

@st.cache_data(show_spinner=False)
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
    """Render Monthly Trends tab content with separate lines for each year"""
    st.subheader("Monthly Performance Trends")

    if 'ship_month' not in filtered_data.columns or 'ship_year' not in filtered_data.columns:
        st.info("No monthly data available")
        return

    monthly = filtered_data.groupby(['ship_year', 'ship_month_num']).agg({
        'on_time': ['sum', 'count'],
        'units_issued': 'sum',
        'days_to_deliver': 'mean'
    }).reset_index()

    monthly.columns = ['year', 'month_num', 'on_time_count', 'total_count', 'total_units', 'avg_days']
    monthly['on_time_pct'] = (monthly['on_time_count'] / monthly['total_count'] * 100)
    monthly = monthly.sort_values(['year', 'month_num'])

    # Create dual-axis chart with separate traces for each year
    fig = go.Figure()

    # Get unique years
    years = sorted(monthly['year'].unique())

    # Color palette for different years
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3B4D61', '#6B9AC4']

    for i, year in enumerate(years):
        year_data = monthly[monthly['year'] == year]
        color = colors[i % len(colors)]

        # Create x-axis labels as "Month Year"
        x_labels = [f"{pd.to_datetime(f'{year}-{month:02d}-01').strftime('%b %Y')}" for month in year_data['month_num']]

        # Add bar trace for total orders
        fig.add_trace(go.Bar(
            x=x_labels,
            y=year_data['total_count'],
            name=f'{year} - Orders',
            marker_color=color,
            opacity=0.7,
            showlegend=True
        ))

        # Add scatter trace for on-time %
        fig.add_trace(go.Scatter(
            x=x_labels,
            y=year_data['on_time_pct'],
            mode='lines+markers',
            name=f'{year} - On-Time %',
            line=dict(color=color, width=3),
            marker=dict(size=8, color=color),
            yaxis='y2',
            showlegend=True
        ))

    # Filter for the last 3 years for the overall trend line
    current_year = datetime.now().year
    three_years_ago = current_year - 2 # Includes current year, and two previous
    trend_data = monthly[monthly['year'] >= three_years_ago]

    # Calculate linear regression for the overall trend if enough data points exist
    if len(trend_data) > 1:
        # Convert month_num and year to a continuous numerical scale for regression
        trend_data['time_index'] = (trend_data['year'] - trend_data['year'].min()) * 12 + (trend_data['month_num'] - 1)

        slope, intercept, r_value, p_value, std_err = linregress(
            trend_data['time_index'], trend_data['on_time_pct']
        )
        trend_line_y = intercept + slope * trend_data['time_index']

        # Generate x_labels for the entire trend_data range
        trend_x_labels = [f"{pd.to_datetime(f'{y}-{m:02d}-01').strftime('%b %Y')}" for y, m in zip(trend_data['year'], trend_data['month_num'])]

        # Add overall trend line
        fig.add_trace(go.Scatter(
            x=trend_x_labels,
            y=trend_line_y,
            mode='lines',
            name='Overall Trend (Last 3 Yrs)',
            line=dict(color='black', width=2, dash='dashdot'),
            showlegend=True,
            yaxis='y2'
        ))

    fig.update_layout(
        xaxis_title="Month",
        yaxis=dict(title="Order Count", side='left'),
        yaxis2=dict(title="On-Time %", overlaying='y', side='right', range=[0, 100]),
        hovermode='x unified',
        legend_title="Year & Metric",
        barmode='group'
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

    # Sort customers by On-Time % (descending), then by Total Orders (descending)
    customer_summary = customer_summary.sort_values(
        by=['On_Time_%', 'Total_Orders'],
        ascending=[False, False]
    )

    # Highlight top 10 customers by On-Time %
    top_customers = customer_summary.head(10)

    # Main table
    st.write("### All Customers")
    render_data_table(customer_summary)

    # Top customers table
    st.write("### Top 10 Customers by On-Time %")
    render_data_table(top_customers)

def render_service_level_page(service_data):
    """Main entry point for Service Level page"""
    st.title("🚚 Service Level Analysis")
    render_page_header("Service Level", "Delivery performance, on-time rates, and cycle times.")

    # Filters
    filters = get_service_level_filters(service_data)
    filter_values = render_filter_section(filters)
    filtered_data = apply_service_filters(service_data, filter_values)

    # KPIs
    metrics = calculate_service_metrics(filtered_data)
    render_kpi_row(metrics)

    # Tabs
    tab1, tab2 = st.tabs(["Monthly Trends", "Customer Performance"])
    with tab1:
        render_monthly_trends_tab(filtered_data)
    with tab2:
        render_customer_performance_tab(filtered_data)