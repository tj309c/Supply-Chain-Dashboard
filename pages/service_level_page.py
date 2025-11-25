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
    # Planning OTIF: preferred flag is 'planning_on_time' (new). Backwards compatible with 'on_time'.
    if 'planning_on_time' in service_data.columns:
        planning_count = service_data['planning_on_time'].sum()
    else:
        planning_count = service_data['on_time'].sum() if 'on_time' in service_data.columns else 0
    planning_pct = (planning_count / total_orders * 100) if total_orders > 0 else 0

    # Logistics OTIF: counts only where a logistics flag exists (goods issue vs delivery creation)
    logistics_pct = None
    logistics_count = 0
    logistics_available = 0
    if 'logistics_on_time' in service_data.columns:
        logistics_available = service_data['logistics_on_time'].notna().sum()
        logistics_count = service_data['logistics_on_time'].sum()
        logistics_pct = (logistics_count / logistics_available * 100) if logistics_available > 0 else None

    total_units = service_data['units_issued'].sum() if 'units_issued' in service_data.columns else 0
    avg_days = service_data['days_to_deliver'].mean() if 'days_to_deliver' in service_data.columns else 0

    # Build result dictionary with both OTIF metrics
    planning_help = (
        f"**Business Logic:** Planning OTIF = percentage of orders shipped within 7 days of order creation. "
        f"Ship Date is defined as Goods Issue Date when available, otherwise Delivery Creation Date. Current: {planning_pct:.1f}% ({planning_count:,} of {total_orders:,} orders). Formula: (COUNT(WHERE planning_on_time = TRUE) / COUNT(orders)) × 100"
    )

    logistics_help = (
        "**Business Logic:** Logistics OTIF = percentage of deliveries where Goods Issue occurred within 3 days of Delivery Creation. "
        "Only rows with both dates are counted."
    )

    result = {
        "Planning OTIF %": {
            "value": f"{planning_pct:.1f}%",
            "help": planning_help
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

    # Build aggregation dictionary based on available columns
    agg_dict = {
        'units_issued': 'sum',
        'days_to_deliver': 'mean'
    }

    has_planning = 'planning_on_time' in filtered_data.columns
    has_logistics = 'logistics_on_time' in filtered_data.columns
    has_on_time = 'on_time' in filtered_data.columns

    if has_planning:
        agg_dict['planning_on_time'] = ['sum', 'count']
    if has_logistics:
        agg_dict['logistics_on_time'] = ['sum', 'count']
    if has_on_time and not has_planning:
        agg_dict['on_time'] = ['sum', 'count']

    monthly = filtered_data.groupby(['ship_year', 'ship_month_num']).agg(agg_dict).reset_index()

    # Flatten multi-level column names
    new_cols = []
    for col in monthly.columns:
        if isinstance(col, tuple):
            if col[1] == '':
                new_cols.append(col[0])
            else:
                new_cols.append(f"{col[0]}_{col[1]}")
        else:
            new_cols.append(col)
    monthly.columns = new_cols

    # Rename groupby columns
    monthly = monthly.rename(columns={'ship_year': 'year', 'ship_month_num': 'month_num'})

    # Calculate percentages based on available columns
    if has_planning:
        monthly['planning_on_time_pct'] = (monthly['planning_on_time_sum'] / monthly['planning_on_time_count'] * 100)
        monthly = monthly.rename(columns={
            'planning_on_time_count': 'planning_total_count',
            'planning_on_time_sum': 'planning_on_time_count'
        })
    if has_logistics:
        if monthly['logistics_on_time_count'].notna().any():
            monthly['logistics_on_time_pct'] = (monthly['logistics_on_time_sum'] / monthly['logistics_on_time_count'] * 100)
        else:
            monthly['logistics_on_time_pct'] = None
        monthly = monthly.rename(columns={
            'logistics_on_time_count': 'logistics_total_count',
            'logistics_on_time_sum': 'logistics_on_time_count'
        })
    if has_on_time and not has_planning:
        monthly['on_time_pct'] = (monthly['on_time_sum'] / monthly['on_time_count'] * 100)
        monthly = monthly.rename(columns={
            'on_time_count': 'total_count',
            'on_time_sum': 'on_time_count'
        })

    # Rename remaining columns for consistency
    monthly = monthly.rename(columns={
        'units_issued_sum': 'total_units',
        'days_to_deliver_mean': 'avg_days'
    })
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

        # Add bar trace for total orders - use planning_total_count if available, else total_count
        volume_col = 'planning_total_count' if 'planning_total_count' in year_data.columns else 'total_count'
        fig.add_trace(go.Bar(
            x=x_labels,
            y=year_data[volume_col],
            name=f'{year} - Orders',
            marker_color=color,
            opacity=0.7,
            showlegend=True
        ))

        # Add scatter trace(s) for on-time %
        if 'planning_on_time_pct' in year_data.columns:
            fig.add_trace(go.Scatter(
                x=x_labels,
                y=year_data['planning_on_time_pct'],
                mode='lines+markers',
                name=f'{year} - Planning OTIF %',
                line=dict(color=color, width=3),
                marker=dict(size=8, color=color),
                yaxis='y2',
                showlegend=True
            ))
        elif 'on_time_pct' in year_data.columns:
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
    trend_data = monthly[monthly['year'] >= three_years_ago].copy()

    # Determine which on-time percentage column to use for trend
    otif_col = None
    if 'planning_on_time_pct' in trend_data.columns:
        otif_col = 'planning_on_time_pct'
    elif 'on_time_pct' in trend_data.columns:
        otif_col = 'on_time_pct'

    # Calculate linear regression for the overall trend if enough data points exist
    if len(trend_data) > 1 and otif_col is not None:
        # Convert month_num and year to a continuous numerical scale for regression
        trend_data['time_index'] = (trend_data['year'] - trend_data['year'].min()) * 12 + (trend_data['month_num'] - 1)

        slope, intercept, r_value, p_value, std_err = linregress(
            trend_data['time_index'], trend_data[otif_col]
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

    # build aggregation keys for customer summary to include planning/logistics where present
    agg = {
        'units_issued': 'sum',
        'days_to_deliver': 'mean'
    }
    if 'planning_on_time' in filtered_data.columns:
        agg['planning_on_time'] = ['sum', 'count']
    else:
        agg['on_time'] = ['sum', 'count']
    if 'logistics_on_time' in filtered_data.columns:
        agg['logistics_on_time'] = ['sum', 'count']

    customer_summary = filtered_data.groupby('customer_name').agg(agg).reset_index()

    # normalize column names
    cols = list(customer_summary.columns)
    if 'planning_on_time' in filtered_data.columns:
        # e.g., customer, planning_on_time_sum, planning_on_time_count, logistics_on_time_sum, logistics_on_time_count, units_issued, days_to_deliver
        # build readable columns
        name_map = {}
        new_cols = []
        for col in cols:
            if col == 'customer_name':
                new_cols.append('Customer')
            elif col == 'planning_on_time':
                new_cols.extend(['On_Time_Count', 'Total_Orders'])
            elif col == 'logistics_on_time':
                new_cols.extend(['Logistics_On_Time_Count', 'Logistics_Total'])
            elif col == 'units_issued':
                new_cols.append('Total_Units')
            elif col == 'days_to_deliver':
                new_cols.append('Avg_Days')
        customer_summary.columns = new_cols
        # compute percentage
        if 'On_Time_Count' in customer_summary.columns and 'Total_Orders' in customer_summary.columns:
            customer_summary['On_Time_%'] = (customer_summary['On_Time_Count'] / customer_summary['Total_Orders'] * 100).round(1)
    else:
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