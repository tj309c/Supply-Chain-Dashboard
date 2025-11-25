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
from ui_components import render_page_header, render_kpi_row, render_chart, render_info_box, render_data_table
from business_rules import CURRENCY_RULES

@st.cache_data(show_spinner=False)
def calculate_overview_metrics(service_data, backorder_data, inventory_data):
    """Calculate high-level metrics for overview page"""
    metrics = {}

    # Service Level Metrics
    if not service_data.empty:
        total_orders = len(service_data)

        # Planning OTIF
        if 'planning_on_time' in service_data.columns:
            planning_count = service_data['planning_on_time'].sum()
        else:
            planning_count = service_data['on_time'].sum() if 'on_time' in service_data.columns else 0
        planning_pct = (planning_count / total_orders * 100) if total_orders > 0 else 0

        # Logistics OTIF: compute only over rows that have the logistics flag available
        logistics_pct = None
        if 'logistics_on_time' in service_data.columns:
            logistics_available = service_data['logistics_on_time'].notna().sum()
            logistics_count = service_data['logistics_on_time'].sum()
            logistics_pct = (logistics_count / logistics_available * 100) if logistics_available > 0 else None

        metrics['service_level'] = {
            "value": f"{planning_pct:.1f}%",
            "delta": None,
            "help": f"**Business Logic:** Planning OTIF = percentage of orders shipped within 7 days of order creation. Current: {planning_pct:.1f}% ({planning_count:,} / {total_orders:,}). Target: 95%."
        }

        metrics['logistics_otif'] = {
            "value": f"{logistics_pct:.1f}%" if logistics_pct is not None else "N/A",
            "delta": None,
            "help": "**Business Logic:** Logistics OTIF = % of deliveries where Goods Issue occurred within 3 days of delivery creation (counted only where both dates exist)."
        }

        metrics['total_orders'] = {
            "value": f"{total_orders:,}",
            "delta": None,
            "help": "**Business Logic:** Total count of order lines processed (shipped). Each order line is a SKU on a customer order. Formula: COUNT(order_lines)"
        }
    else:
        metrics['service_level'] = {"value": "N/A", "delta": None, "help": "No service data available"}
        metrics['logistics_otif'] = {"value": "N/A", "delta": None, "help": "No service data available"}
        metrics['total_orders'] = {"value": "N/A", "delta": None, "help": "No service data available"}

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

        # Calculate inventory value in USD
        # Formula: on_hand_qty × last_purchase_price × currency_conversion_rate
        if 'on_hand_qty' in inventory_data.columns and 'last_purchase_price' in inventory_data.columns:
            # Create a copy to avoid SettingWithCopyWarning
            inv_calc = inventory_data[['on_hand_qty', 'last_purchase_price', 'currency']].copy()

            # Calculate value in original currency
            inv_calc['value_orig_currency'] = inv_calc['on_hand_qty'] * inv_calc['last_purchase_price']

            # Convert to USD based on currency
            inv_calc['value_usd'] = inv_calc.apply(
                lambda row: row['value_orig_currency'] * CURRENCY_RULES['conversion_rates'].get('EUR_to_USD', 1.0)
                if row['currency'] == 'EUR'
                else row['value_orig_currency'],
                axis=1
            )

            total_value_usd = inv_calc['value_usd'].sum()
        else:
            total_value_usd = 0

        # Calculate TOTAL DIO (aggregate level for the filtered category)
        # Formula: Total On-Hand Qty / Total Daily Demand
        # This gives a single DIO representing the entire filtered dataset (e.g., RETAIL PERMANENT)
        # Much more meaningful than averaging individual SKU DIOs
        total_dio = None
        total_dio_details = {}

        if 'daily_demand' in inventory_data.columns and 'on_hand_qty' in inventory_data.columns:
            # Sum all on-hand inventory
            total_on_hand = inventory_data['on_hand_qty'].sum()

            # Sum all daily demand (only from SKUs with positive demand)
            total_daily_demand = inventory_data[inventory_data['daily_demand'] > 0]['daily_demand'].sum()

            # Count SKUs with demand vs without
            skus_with_demand = (inventory_data['daily_demand'] > 0).sum()
            skus_without_demand = (inventory_data['daily_demand'] == 0).sum() if 'daily_demand' in inventory_data.columns else 0

            if total_daily_demand > 0:
                total_dio = total_on_hand / total_daily_demand

                # Capture details for the help tooltip
                total_dio_details = {
                    'total_on_hand': total_on_hand,
                    'total_daily_demand': total_daily_demand,
                    'skus_with_demand': skus_with_demand,
                    'skus_without_demand': skus_without_demand,
                    'total_skus': len(inventory_data)
                }

        # Count critical stock situations
        critical_stock = 0
        if 'stock_risk' in inventory_data.columns:
            critical_stock = len(inventory_data[inventory_data['stock_risk'] == 'Critical'])
        elif 'dio' in inventory_data.columns:
            # Critical = DIO < 30 days AND has demand (DIO > 0)
            critical_stock = len(inventory_data[(inventory_data['dio'] > 0) & (inventory_data['dio'] < 30)])

        metrics['inventory_units'] = {
            "value": f"{int(total_stock):,}",
            "delta": None,
            "help": f"**Business Logic:** Total units currently on-hand across all SKUs in all warehouse locations. Current: {int(total_stock):,} units. Formula: SUM(on_hand_qty)"
        }

        metrics['inventory_value'] = {
            "value": f"${total_value_usd:,.0f}",
            "delta": None,
            "help": f"**Business Logic:** Total inventory value in USD. Calculated as: SUM(on_hand_qty × last_purchase_price × EUR_to_USD_rate). Current: ${total_value_usd:,.0f}"
        }

        if total_dio is not None:
            # Build detailed help text explaining exactly how the calculation works
            help_text = (
                f"**Total Days Inventory Outstanding (DIO)**\n\n"
                f"**What it measures:** How many days of sales your total inventory represents at the aggregate level. "
                f"This is calculated using the sum of all inventory divided by the sum of all daily demand.\n\n"
                f"**Formula:**\n"
                f"```\n"
                f"Total DIO = Total On-Hand Qty / Total Daily Demand\n"
                f"```\n\n"
                f"**Current Calculation (filtered data):**\n"
                f"- Total On-Hand Units: {total_dio_details.get('total_on_hand', 0):,.0f}\n"
                f"- Total Daily Demand: {total_dio_details.get('total_daily_demand', 0):,.1f} units/day\n"
                f"- Total DIO: {total_dio:.0f} days\n\n"
                f"**SKU Coverage:**\n"
                f"- SKUs with demand: {total_dio_details.get('skus_with_demand', 0):,}\n"
                f"- SKUs without demand: {total_dio_details.get('skus_without_demand', 0):,}\n"
                f"- Total SKUs: {total_dio_details.get('total_skus', 0):,}\n\n"
                f"**Target:** 60-90 days\n\n"
                f"**Why aggregate DIO?** This metric represents the total category performance. "
                f"It answers: 'If we stopped receiving inventory today, how many days could we fulfill demand?'"
            )
            metrics['total_dio'] = {
                "value": f"{total_dio:.0f} days",
                "delta": None,
                "help": help_text
            }
        else:
            metrics['total_dio'] = {"value": "N/A", "delta": None, "help": "No DIO data available. Requires inventory with on_hand_qty and daily_demand > 0."}

        metrics['critical_stock'] = {
            "value": f"{critical_stock:,}",
            "delta": None,
            "help": f"**Business Logic:** Count of SKUs with critical stock-out risk (DIO < 30 days). Current: {critical_stock:,} SKUs. Formula: COUNT(WHERE dio < 30)"
        }
    else:
        metrics['inventory_units'] = {"value": "N/A", "delta": None}
        metrics['inventory_value'] = {"value": "N/A", "delta": None}
        metrics['total_dio'] = {"value": "N/A", "delta": None}
        metrics['critical_stock'] = {"value": "N/A", "delta": None}

    return metrics

def render_service_level_chart(service_data, otif_type='planning', selected_years=None):
    """Render service level trend chart with separate lines for each year.

    X-axis shows months 1-12 (Jan-Dec), with each year as a separate colored line
    overlaid on the same month positions for easy year-over-year comparison.

    Args:
        service_data: DataFrame with service level data
        otif_type: 'planning' for Planning OTIF (ship within 7 days of order)
                   'logistics' for Logistics OTIF (goods issue within 3 days of delivery creation)
        selected_years: List of years to include in the chart. If None, shows last 3 years.

    Business Rules:
        - Planning OTIF: ship_date <= order_date + 7 days
        - Logistics OTIF: goods_issue_date <= delivery_creation_date + 3 days
    """
    if service_data.empty or 'ship_month' not in service_data.columns or 'ship_year' not in service_data.columns:
        return None

    # Select the appropriate on-time column based on OTIF type
    if otif_type == 'logistics':
        otif_col = 'logistics_on_time'
        chart_title = "Logistics OTIF Trend by Year"
        y_axis_title = "Logistics OTIF %"
        help_text = "Goods Issue within 3 days of Delivery Creation"
    else:
        # Default to planning OTIF
        otif_col = 'planning_on_time' if 'planning_on_time' in service_data.columns else 'on_time'
        chart_title = "Planning OTIF Trend by Year"
        y_axis_title = "Planning OTIF %"
        help_text = "Shipment within 7 days of Order Creation"

    # Check if the required column exists
    if otif_col not in service_data.columns:
        return None

    # For logistics OTIF, filter to only rows where the flag is available (not NaN)
    if otif_type == 'logistics':
        chart_data = service_data[service_data[otif_col].notna()].copy()
        if chart_data.empty:
            return None
    else:
        chart_data = service_data.copy()

    # Group by year and month
    monthly = chart_data.groupby(['ship_year', 'ship_month_num'], observed=True).agg({
        otif_col: ['sum', 'count']
    }).reset_index()

    monthly.columns = ['year', 'month_num', 'on_time_count', 'total_count']
    monthly['on_time_pct'] = (monthly['on_time_count'] / monthly['total_count'] * 100)

    # Sort by year and month
    monthly = monthly.sort_values(['year', 'month_num'])

    # Calculate overall on-time % for each year
    yearly_avg = chart_data.groupby('ship_year', observed=True).agg({
        otif_col: ['sum', 'count']
    }).reset_index()
    yearly_avg.columns = ['year', 'on_time_count', 'total_count']
    yearly_avg['avg_on_time_pct'] = (yearly_avg['on_time_count'] / yearly_avg['total_count'] * 100)

    # Create chart with separate traces for each year
    fig = go.Figure()

    # Get unique years from data
    all_years = sorted(monthly['year'].unique())

    # Use selected_years if provided, otherwise default to last 3 years
    if selected_years is not None and len(selected_years) > 0:
        years = [y for y in all_years if y in selected_years]
    else:
        years = all_years[-3:] if len(all_years) > 3 else all_years

    # If no years match after filtering, return None
    if not years:
        return None

    # Filter monthly data to only include selected years
    monthly = monthly[monthly['year'].isin(years)]
    yearly_avg = yearly_avg[yearly_avg['year'].isin(years)]

    # Color palette for different years
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3B4D61', '#6B9AC4']

    # Month names for x-axis (1-12)
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # First add volume bars (so they appear behind the lines)
    for i, year in enumerate(years):
        year_data = monthly[monthly['year'] == year].sort_values('month_num')
        color = colors[i % len(colors)]

        x_values = year_data['month_num'].tolist()
        volume_values = year_data['total_count'].tolist()

        # Add volume bars on secondary y-axis
        fig.add_trace(go.Bar(
            x=x_values,
            y=volume_values,
            name=f'{year} Volume',
            marker=dict(color=color, opacity=0.3),
            yaxis='y2',
            hovertemplate=f'<b>{year}</b><br>%{{text}}: %{{y:,.0f}} orders<extra></extra>',
            text=[month_names[m-1] for m in x_values],
            showlegend=True
        ))

    # Then add OTIF percentage lines (on top of bars)
    for i, year in enumerate(years):
        year_data = monthly[monthly['year'] == year].sort_values('month_num')
        color = colors[i % len(colors)]

        # Use month number (1-12) as x-axis position, with month name labels
        x_values = year_data['month_num'].tolist()
        y_values = year_data['on_time_pct'].tolist()

        # Add monthly trend line
        fig.add_trace(go.Scatter(
            x=x_values,
            y=y_values,
            mode='lines+markers',
            name=f'{year} OTIF',
            line=dict(color=color, width=3),
            marker=dict(size=8, color=color),
            hovertemplate=f'<b>{year}</b><br>%{{text}}: %{{y:.1f}}%<extra></extra>',
            text=[month_names[m-1] for m in x_values]
        ))

        # Add year average as horizontal line spanning all 12 months
        if len(yearly_avg[yearly_avg['year'] == year]) > 0:
            year_avg_pct = yearly_avg[yearly_avg['year'] == year]['avg_on_time_pct'].values[0]
            fig.add_trace(go.Scatter(
                x=[1, 12],
                y=[year_avg_pct, year_avg_pct],
                mode='lines',
                name=f'{year} Avg ({year_avg_pct:.1f}%)',
                line=dict(color=color, width=2, dash='dot'),
                showlegend=True,
                hovertemplate=f'{year} Average: {year_avg_pct:.1f}%<extra></extra>'
            ))

    # Add target line (95% for both OTIF types per business rules)
    fig.add_hline(y=95, line_dash="dash", line_color="green", annotation_text="Target: 95%")

    fig.update_layout(
        title=chart_title,
        xaxis_title="Month",
        yaxis_title=y_axis_title,
        yaxis_range=[0, 100],
        legend_title="Legend",
        barmode='group',
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(1, 13)),
            ticktext=month_names,
            range=[0.5, 12.5]
        ),
        yaxis2=dict(
            title="Order Volume",
            overlaying='y',
            side='right',
            showgrid=False,
            rangemode='tozero'
        )
    )

    return fig

def calculate_dio_buckets_weighted(inventory_data):
    """Calculate value-weighted DIO breakdown by turn ratio buckets.

    Turn Ratio Buckets (industry standard):
    - Excellent (DIO < 30): High velocity, turns >12x per year
    - Good (30-60): Healthy turnover, turns 6-12x per year
    - Average (60-90): Standard performance, turns 4-6x per year
    - Slow (90-180): Below target, turns 2-4x per year
    - Very Slow (180-365): At risk, turns 1-2x per year
    - Dead Stock (>365): Potential write-off, turns <1x per year

    Returns:
        DataFrame with bucket analysis, or None if insufficient data
    """
    DIO_CAP = 365  # Cap for display purposes

    if inventory_data.empty:
        return None

    required_cols = ['dio', 'on_hand_qty', 'last_purchase_price']
    if not all(col in inventory_data.columns for col in required_cols):
        return None

    # Filter to SKUs with positive DIO (those with actual demand)
    active_inv = inventory_data[inventory_data['dio'] > 0].copy()

    if active_inv.empty:
        return None

    # Calculate value in USD for each SKU
    active_inv['sku_value'] = active_inv['on_hand_qty'] * active_inv['last_purchase_price']
    if 'currency' in active_inv.columns:
        active_inv['sku_value_usd'] = active_inv.apply(
            lambda row: row['sku_value'] * CURRENCY_RULES['conversion_rates'].get('EUR_to_USD', 1.0)
            if row['currency'] == 'EUR' else row['sku_value'],
            axis=1
        )
    else:
        active_inv['sku_value_usd'] = active_inv['sku_value']

    # Define turn ratio buckets
    bucket_bins = [0, 30, 60, 90, 180, 365, float('inf')]
    bucket_labels = ['Excellent (<30)', 'Good (30-60)', 'Average (60-90)',
                     'Slow (90-180)', 'Very Slow (180-365)', 'Dead Stock (>365)']

    active_inv['dio_bucket'] = pd.cut(
        active_inv['dio'],
        bins=bucket_bins,
        labels=bucket_labels,
        right=True
    )

    # Calculate weighted DIO and value for each bucket
    bucket_analysis = active_inv.groupby('dio_bucket', observed=True).agg({
        'sku_value_usd': 'sum',
        'on_hand_qty': 'sum',
        'dio': lambda x: x.count()  # SKU count
    }).reset_index()

    bucket_analysis.columns = ['Bucket', 'Value ($)', 'Units', 'SKU Count']

    # Calculate weighted DIO for each bucket
    weighted_dios = []
    for bucket in bucket_labels:
        bucket_data = active_inv[active_inv['dio_bucket'] == bucket]
        if not bucket_data.empty and bucket_data['sku_value_usd'].sum() > 0:
            # Cap DIO at 365 for the weighted calculation
            capped_dio = bucket_data['dio'].clip(upper=DIO_CAP)
            weighted_dio = (capped_dio * bucket_data['sku_value_usd']).sum() / bucket_data['sku_value_usd'].sum()
            weighted_dios.append(weighted_dio)
        else:
            weighted_dios.append(0)

    # Add weighted DIO column
    bucket_analysis['Weighted DIO'] = weighted_dios

    # Calculate percentage of total value
    total_value = bucket_analysis['Value ($)'].sum()
    bucket_analysis['% of Value'] = (bucket_analysis['Value ($)'] / total_value * 100) if total_value > 0 else 0

    # Sort by bucket order
    bucket_order = {label: i for i, label in enumerate(bucket_labels)}
    bucket_analysis['sort_order'] = bucket_analysis['Bucket'].map(bucket_order)
    bucket_analysis = bucket_analysis.sort_values('sort_order').drop('sort_order', axis=1)

    return bucket_analysis


def render_dio_bucket_chart(bucket_data):
    """Render a horizontal bar chart showing value distribution by DIO bucket"""
    if bucket_data is None or bucket_data.empty:
        return None

    # Colors from healthy (green) to concerning (red)
    colors = ['#06D6A0', '#7CB518', '#FFD166', '#EF8354', '#F4442E', '#A71E2C']

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=bucket_data['Bucket'],
        x=bucket_data['Value ($)'],
        orientation='h',
        marker_color=colors[:len(bucket_data)],
        text=[f"${v:,.0f} ({p:.1f}%)" for v, p in zip(bucket_data['Value ($)'], bucket_data['% of Value'])],
        textposition='auto',
        hovertemplate=(
            '<b>%{y}</b><br>' +
            'Value: $%{x:,.0f}<br>' +
            'SKUs: %{customdata[0]:,}<br>' +
            'Units: %{customdata[1]:,}<br>' +
            'Weighted DIO: %{customdata[2]:.0f} days<extra></extra>'
        ),
        customdata=list(zip(bucket_data['SKU Count'], bucket_data['Units'], bucket_data['Weighted DIO']))
    ))

    fig.update_layout(
        title="Inventory Value by Turn Ratio (DIO Buckets)",
        xaxis_title="Inventory Value (USD)",
        yaxis_title="DIO Bucket",
        yaxis=dict(categoryorder='array', categoryarray=list(reversed(bucket_data['Bucket'].tolist()))),
        height=350
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

    # === ACTION REQUIRED SUMMARY ===
    # Show top priorities that need attention
    action_items = []

    # Check for critical backorders
    if not backorder_data.empty:
        critical_bo = backorder_data[backorder_data['days_on_backorder'] > 30]
        if len(critical_bo) > 0:
            total_critical_units = int(critical_bo['backorder_qty'].sum())
            action_items.append({
                "icon": "🚨",
                "title": f"{len(critical_bo):,} Critical Backorders",
                "detail": f"{total_critical_units:,} units aged >30 days",
                "page": "backorders"
            })

    # Check for low service level
    if not service_data.empty:
        if 'planning_on_time' in service_data.columns:
            otif_pct = (service_data['planning_on_time'].sum() / len(service_data) * 100)
        else:
            otif_pct = (service_data['on_time'].sum() / len(service_data) * 100) if 'on_time' in service_data.columns else 100
        if otif_pct < 90:
            action_items.append({
                "icon": "📉",
                "title": f"Service Level Below Target",
                "detail": f"OTIF at {otif_pct:.1f}% (target: 95%)",
                "page": "service_level"
            })

    # Check for critical inventory
    if not inventory_data.empty and 'stock_out_risk' in inventory_data.columns:
        critical_inv = inventory_data[inventory_data['stock_out_risk'] == 'Critical']
        if len(critical_inv) > 0:
            action_items.append({
                "icon": "⚠️",
                "title": f"{len(critical_inv):,} SKUs at Stock-Out Risk",
                "detail": "Low inventory coverage items",
                "page": "inventory"
            })

    # Check for dead stock
    if not inventory_data.empty and 'dio' in inventory_data.columns:
        dead_stock = inventory_data[inventory_data['dio'] > 365]
        if len(dead_stock) > 0:
            if 'stock_value_usd' in dead_stock.columns:
                dead_value = dead_stock['stock_value_usd'].sum()
                action_items.append({
                    "icon": "💀",
                    "title": f"{len(dead_stock):,} Dead Stock SKUs",
                    "detail": f"${dead_value:,.0f} tied up in obsolete inventory",
                    "page": "inventory"
                })

    # Display action items if any exist
    if action_items:
        st.markdown("### 🎯 Action Required")
        action_cols = st.columns(min(len(action_items), 4))
        for i, item in enumerate(action_items[:4]):  # Max 4 items
            with action_cols[i]:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #ff6b6b22, #ff6b6b11); border-left: 4px solid #ff6b6b; padding: 12px; border-radius: 8px; margin-bottom: 10px;">
                    <div style="font-size: 24px;">{item['icon']}</div>
                    <div style="font-weight: bold; font-size: 14px;">{item['title']}</div>
                    <div style="font-size: 12px; color: #666;">{item['detail']}</div>
                </div>
                """, unsafe_allow_html=True)
        st.divider()

    # === KPI DASHBOARD ===
    # Professional 3-column layout with grouped metrics

    # Top row: 3 equal columns for the main KPI categories
    col1, col2, col3 = st.columns(3)

    # Column 1: Service Level Performance
    with col1:
        st.markdown("##### 📦 Service Level")
        st.metric(
            label="Planning OTIF",
            value=metrics.get('service_level', {}).get('value', 'N/A'),
            delta=metrics.get('service_level', {}).get('delta'),
            help=metrics.get('service_level', {}).get('help', '')
        )
        st.metric(
            label="Logistics OTIF",
            value=metrics.get('logistics_otif', {}).get('value', 'N/A'),
            delta=metrics.get('logistics_otif', {}).get('delta'),
            help=metrics.get('logistics_otif', {}).get('help', '')
        )
        st.metric(
            label="Orders Shipped",
            value=metrics.get('total_orders', {}).get('value', 'N/A'),
            delta=metrics.get('total_orders', {}).get('delta'),
            help=metrics.get('total_orders', {}).get('help', '')
        )

    # Column 2: Inventory Health
    with col2:
        st.markdown("##### 📊 Inventory Health")
        st.metric(
            label="Inventory Value",
            value=metrics.get('inventory_value', {}).get('value', 'N/A'),
            delta=metrics.get('inventory_value', {}).get('delta'),
            help=metrics.get('inventory_value', {}).get('help', '')
        )
        st.metric(
            label="Inventory Units",
            value=metrics.get('inventory_units', {}).get('value', 'N/A'),
            delta=metrics.get('inventory_units', {}).get('delta'),
            help=metrics.get('inventory_units', {}).get('help', '')
        )
        st.metric(
            label="Total DIO",
            value=metrics.get('total_dio', {}).get('value', 'N/A'),
            delta=metrics.get('total_dio', {}).get('delta'),
            help=metrics.get('total_dio', {}).get('help', '')
        )

    # Column 3: Backorders & Risk
    with col3:
        st.markdown("##### ⚠️ Backorders & Risk")
        st.metric(
            label="Backorder Units",
            value=metrics.get('backorders', {}).get('value', 'N/A'),
            delta=metrics.get('backorders', {}).get('delta'),
            help=metrics.get('backorders', {}).get('help', '')
        )
        st.metric(
            label="Avg Backorder Age",
            value=metrics.get('avg_backorder_age', {}).get('value', 'N/A'),
            delta=metrics.get('avg_backorder_age', {}).get('delta'),
            help=metrics.get('avg_backorder_age', {}).get('help', '')
        )
        st.metric(
            label="Critical Stock SKUs",
            value=metrics.get('critical_stock', {}).get('value', 'N/A'),
            delta=metrics.get('critical_stock', {}).get('delta'),
            help=metrics.get('critical_stock', {}).get('help', '')
        )

    st.divider()

    # Charts section
    st.subheader("Performance Trends")

    # Service Level Charts - Planning OTIF and Logistics OTIF stacked vertically
    st.markdown("#### Service Level Performance")
    st.caption("**Planning OTIF:** Shipment within 7 days of Order Creation | **Logistics OTIF:** Goods Issue within 3 days of Delivery Creation")

    # Year filter bubbles for Service Level charts
    available_years = []
    if not service_data.empty and 'ship_year' in service_data.columns:
        all_years_in_data = sorted(service_data['ship_year'].dropna().unique())
        # Convert to integers for display and show last 3 years
        available_years = [int(y) for y in all_years_in_data[-3:]] if len(all_years_in_data) > 3 else [int(y) for y in all_years_in_data]

    if available_years:
        # Year filter row with clear labeling
        filter_col1, filter_col2 = st.columns([1, 4])
        with filter_col1:
            st.markdown("**Select Years:**")
        with filter_col2:
            selected_years = st.multiselect(
                "Filter by Year",
                options=available_years,
                default=available_years,  # All years selected by default
                key="service_level_year_filter",
                help="Select which years to display in the charts below",
                label_visibility="collapsed"
            )
    else:
        selected_years = None

    # Planning OTIF Chart
    planning_chart = render_service_level_chart(service_data, otif_type='planning', selected_years=selected_years)
    if planning_chart:
        render_chart(planning_chart, height=350)
    else:
        if selected_years is not None and len(selected_years) == 0:
            render_info_box("Please select at least one year to view the chart", type="info")
        else:
            render_info_box("No Planning OTIF data available", type="info")

    # Logistics OTIF Chart
    logistics_chart = render_service_level_chart(service_data, otif_type='logistics', selected_years=selected_years)
    if logistics_chart:
        render_chart(logistics_chart, height=350)
    else:
        if selected_years is not None and len(selected_years) == 0:
            render_info_box("Please select at least one year to view the chart", type="info")
        else:
            render_info_box("No Logistics OTIF data available (requires Goods Issue Date)", type="info")

    st.divider()

    # Inventory Turn Ratio Analysis (Value-Weighted DIO Buckets)
    st.markdown("#### Inventory Turn Ratio Analysis")
    st.caption("Value-weighted DIO breakdown by turn ratio bucket - shows where your inventory dollars are tied up")

    # Debug: Check if required columns exist
    required_cols = ['dio', 'on_hand_qty', 'last_purchase_price']
    missing_cols = [col for col in required_cols if col not in inventory_data.columns]
    if missing_cols:
        render_info_box(f"Missing columns for DIO bucket analysis: {missing_cols}", type="warning")
    else:
        # Check how many SKUs have DIO > 0
        dio_positive_count = (inventory_data['dio'] > 0).sum() if 'dio' in inventory_data.columns else 0
        if dio_positive_count == 0:
            render_info_box("No SKUs with positive DIO found. This may indicate no demand data in the last 12 months.", type="info")

    dio_bucket_data = calculate_dio_buckets_weighted(inventory_data)
    if dio_bucket_data is not None and not dio_bucket_data.empty:
        # Chart showing value distribution
        dio_chart = render_dio_bucket_chart(dio_bucket_data)
        if dio_chart:
            render_chart(dio_chart, height=350)

        # Detailed table in expander
        with st.expander("📊 Detailed Turn Ratio Breakdown", expanded=False):
            st.markdown("""
**Turn Ratio Buckets Explained:**
- **Excellent (<30 days):** High velocity items, turns >12x/year
- **Good (30-60 days):** Healthy turnover, turns 6-12x/year
- **Average (60-90 days):** Standard performance, turns 4-6x/year
- **Slow (90-180 days):** Below target, turns 2-4x/year
- **Very Slow (180-365 days):** At risk, turns 1-2x/year
- **Dead Stock (>365 days):** Potential write-off candidate, turns <1x/year
            """)

            # Format the table for display
            display_df = dio_bucket_data.copy()
            display_df['Value ($)'] = display_df['Value ($)'].apply(lambda x: f"${x:,.0f}")
            display_df['Units'] = display_df['Units'].apply(lambda x: f"{int(x):,}")
            display_df['SKU Count'] = display_df['SKU Count'].apply(lambda x: f"{int(x):,}")
            display_df['Weighted DIO'] = display_df['Weighted DIO'].apply(lambda x: f"{x:.0f} days")
            display_df['% of Value'] = display_df['% of Value'].apply(lambda x: f"{x:.1f}%")

            st.dataframe(
                display_df,
                hide_index=True,
                width='stretch'
            )

            # Key insight
            slow_plus_dead = dio_bucket_data[dio_bucket_data['Bucket'].isin(['Slow (90-180)', 'Very Slow (180-365)', 'Dead Stock (>365)'])]['% of Value'].sum()
            if slow_plus_dead > 20:
                render_info_box(
                    f"⚠️ {slow_plus_dead:.1f}% of inventory value is in slow-moving or dead stock (DIO > 90 days). Consider markdown or liquidation strategies.",
                    type="warning"
                )
    else:
        render_info_box("No inventory turn ratio data available", type="info")

    st.divider()

    # Backorder Chart
    st.markdown("#### Backorder Analysis")
    col3, col4 = st.columns(2)

    with col3:
        backorder_chart = render_backorder_chart(backorder_data)
        if backorder_chart:
            render_chart(backorder_chart, height=350)
        else:
            render_info_box("No backorder data available", type="info")

    with col4:
        # Add a placeholder for future chart or summary stats
        if not backorder_data.empty and 'backorder_qty' in backorder_data.columns:
            total_bo_units = int(backorder_data['backorder_qty'].sum())
            total_bo_lines = len(backorder_data)
            avg_age = backorder_data['days_on_backorder'].mean() if 'days_on_backorder' in backorder_data.columns else 0
            st.markdown("**Backorder Summary**")
            st.metric("Total Backorder Units", f"{total_bo_units:,}")
            st.metric("Total Backorder Lines", f"{total_bo_lines:,}")
            st.metric("Average Age", f"{avg_age:.0f} days")
        else:
            render_info_box("No backorder summary available", type="info")

    # Alerts and Details section
    st.divider()
    st.subheader("🔔 Active Alerts & Key Issues")

    alerts = []

    # Check service level
    if not service_data.empty:
        # Use planning_on_time (preferred) otherwise legacy on_time
        if 'planning_on_time' in service_data.columns:
            on_time_pct = (service_data['planning_on_time'].sum() / len(service_data) * 100)
        elif 'on_time' in service_data.columns:
            on_time_pct = (service_data['on_time'].sum() / len(service_data) * 100)
        else:
            on_time_pct = None

        if on_time_pct is not None and on_time_pct < 90:
            alerts.append(("warning", f"Service level below target: {on_time_pct:.1f}% (Target: 95%)"))

    # Check backorders
    if not backorder_data.empty and 'days_on_backorder' in backorder_data.columns:
        old_backorders = len(backorder_data[backorder_data['days_on_backorder'] > 30])
        if old_backorders > 0:
            alerts.append(("warning", f"{old_backorders} backorders aged over 30 days"))

    # Check critical stock
    if not inventory_data.empty:
        if 'stock_out_risk' in inventory_data.columns:
            critical_skus = len(inventory_data[inventory_data['stock_out_risk'] == 'Critical'])
        elif 'dio' in inventory_data.columns:
            critical_skus = len(inventory_data[inventory_data['dio'] < 30])
        else:
            critical_skus = 0

        if critical_skus > 0:
            alerts.append(("error", f"{critical_skus} SKUs at critical stock-out risk (DIO < 30 days)"))

    if not alerts:
        st.success("✓ All metrics within normal range")
    else:
        for alert_type, message in alerts:
            render_info_box(message, type=alert_type)

    # Details sections
    st.divider()

    # Top Backorder Customers
    if not backorder_data.empty and 'customer_name' in backorder_data.columns and 'backorder_qty' in backorder_data.columns:
        with st.expander("📋 Top 10 Backorder Customers", expanded=False):
            # Aggregate by customer: Total Units, Total Value, # SKUs, Avg Days on Backorder
            agg_dict = {
                'backorder_qty': 'sum',
                'sku': 'nunique',
                'days_on_backorder': 'mean'
            }

            # Calculate value if price available
            bo_data = backorder_data.copy()
            if 'last_purchase_price' in bo_data.columns:
                bo_data['backorder_value'] = bo_data['backorder_qty'] * bo_data['last_purchase_price']
                # Apply currency conversion if needed
                if 'currency' in bo_data.columns:
                    bo_data['backorder_value_usd'] = bo_data.apply(
                        lambda row: row['backorder_value'] * CURRENCY_RULES['conversion_rates'].get('EUR_to_USD', 1.0)
                        if row['currency'] == 'EUR' else row['backorder_value'],
                        axis=1
                    )
                else:
                    bo_data['backorder_value_usd'] = bo_data['backorder_value']
                agg_dict['backorder_value_usd'] = 'sum'

            customer_backorders = bo_data.groupby('customer_name', observed=True).agg(agg_dict).reset_index()

            # Rename columns
            col_names = {'customer_name': 'Customer', 'backorder_qty': 'Total Units', 'sku': '# SKUs', 'days_on_backorder': 'Avg Days on BO'}
            if 'backorder_value_usd' in customer_backorders.columns:
                col_names['backorder_value_usd'] = 'Total Value'
            customer_backorders = customer_backorders.rename(columns=col_names)

            # Sort by Total Units descending
            customer_backorders = customer_backorders.sort_values('Total Units', ascending=False).head(10)

            # Format for display
            customer_backorders['Total Units'] = customer_backorders['Total Units'].apply(lambda x: f"{int(x):,}")
            customer_backorders['# SKUs'] = customer_backorders['# SKUs'].apply(lambda x: f"{int(x):,}")
            customer_backorders['Avg Days on BO'] = customer_backorders['Avg Days on BO'].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
            if 'Total Value' in customer_backorders.columns:
                customer_backorders['Total Value'] = customer_backorders['Total Value'].apply(lambda x: f"${x:,.0f}")
                # Reorder columns
                customer_backorders = customer_backorders[['Customer', 'Total Units', 'Total Value', '# SKUs', 'Avg Days on BO']]
            else:
                customer_backorders = customer_backorders[['Customer', 'Total Units', '# SKUs', 'Avg Days on BO']]

            st.dataframe(
                customer_backorders,
                hide_index=True,
                width='stretch'
            )

    # Critical Stock SKUs
    if not inventory_data.empty and critical_skus > 0:
        with st.expander(f"⚠️ Critical Stock SKUs ({critical_skus} items)", expanded=False):
            if 'stock_out_risk' in inventory_data.columns:
                critical_items = inventory_data[inventory_data['stock_out_risk'] == 'Critical'].copy()
            elif 'dio' in inventory_data.columns:
                critical_items = inventory_data[inventory_data['dio'] < 30].copy()
            else:
                critical_items = pd.DataFrame()

            if not critical_items.empty:
                # Build display dataframe with requested columns: SKU, Category, SKU Description
                display_data = {}

                if 'sku' in critical_items.columns:
                    display_data['SKU'] = critical_items['sku']

                if 'category' in critical_items.columns:
                    display_data['Category'] = critical_items['category']

                # SKU Description (product_name field)
                if 'product_name' in critical_items.columns:
                    display_data['SKU Description'] = critical_items['product_name']

                # Add DIO for context (sorted by this)
                if 'dio' in critical_items.columns:
                    display_data['DIO (Days)'] = critical_items['dio'].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")

                # Add on-hand qty for context
                if 'on_hand_qty' in critical_items.columns:
                    display_data['On Hand Qty'] = critical_items['on_hand_qty'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")

                if display_data:
                    critical_display = pd.DataFrame(display_data)
                    # Sort by DIO ascending (most critical first)
                    if 'dio' in critical_items.columns:
                        critical_display['_sort_dio'] = critical_items['dio'].values
                        critical_display = critical_display.sort_values('_sort_dio').drop('_sort_dio', axis=1)
                    critical_display = critical_display.head(20)

                    st.dataframe(
                        critical_display,
                        hide_index=True,
                        width='stretch'
                    )
