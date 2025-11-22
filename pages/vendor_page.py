"""
Vendor & Procurement Dashboard
Tabbed interface for PO Management, Vendor Performance, Pricing Analysis, and more
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import render_page_header, render_kpi_row, render_chart, render_info_box, render_data_table
from business_rules import CURRENCY_RULES

# ===== SHARED UTILITY FUNCTIONS =====

def calculate_vendor_metrics(po_data, vendor_performance):
    """Calculate high-level vendor and PO metrics"""
    metrics = {}

    if not po_data.empty:
        # Open PO Metrics
        open_pos = po_data[po_data['is_open'] == True] if 'is_open' in po_data.columns else po_data
        total_open_pos = len(open_pos)
        total_open_value = open_pos['po_value'].sum() if 'po_value' in open_pos.columns else 0
        total_open_qty = open_pos['open_qty'].sum() if 'open_qty' in open_pos.columns else 0

        # At-risk POs (delivery within 7 days or overdue)
        at_risk_pos = 0
        if 'days_to_delivery' in open_pos.columns:
            at_risk_pos = len(open_pos[open_pos['days_to_delivery'] <= 7])

        # Average PO age
        avg_po_age = open_pos['po_age_days'].mean() if 'po_age_days' in open_pos.columns else 0

        metrics['total_open_pos'] = {
            "value": f"{total_open_pos:,}",
            "delta": None,
            "help": f"**Business Logic:** Total count of open purchase orders with outstanding quantity. Current: {total_open_pos:,} POs. Formula: COUNT(WHERE open_qty > 0)"
        }

        metrics['open_po_value'] = {
            "value": f"${total_open_value:,.0f}",
            "delta": None,
            "help": f"**Business Logic:** Total value of open purchase orders. Current: ${total_open_value:,.0f}. Formula: SUM(po_value WHERE is_open = TRUE)"
        }

        metrics['open_po_qty'] = {
            "value": f"{int(total_open_qty):,}",
            "delta": None,
            "help": f"**Business Logic:** Total units on open purchase orders awaiting receipt. Current: {int(total_open_qty):,} units. Formula: SUM(open_qty)"
        }

        metrics['at_risk_pos'] = {
            "value": f"{at_risk_pos:,}",
            "delta": None,
            "help": f"**Business Logic:** Purchase orders due within 7 days or overdue. Current: {at_risk_pos:,} POs. Formula: COUNT(WHERE days_to_delivery <= 7)"
        }

        metrics['avg_po_age'] = {
            "value": f"{avg_po_age:.0f} days",
            "delta": None,
            "help": f"**Business Logic:** Average age of open purchase orders. Current: {avg_po_age:.1f} days. Formula: AVG(TODAY - po_create_date WHERE is_open = TRUE)"
        }

    else:
        metrics['total_open_pos'] = {"value": "N/A", "delta": None}
        metrics['open_po_value'] = {"value": "N/A", "delta": None}
        metrics['open_po_qty'] = {"value": "N/A", "delta": None}
        metrics['at_risk_pos'] = {"value": "N/A", "delta": None}
        metrics['avg_po_age'] = {"value": "N/A", "delta": None}

    # Vendor Performance Metrics
    if not vendor_performance.empty:
        total_vendors = len(vendor_performance)
        avg_vendor_score = vendor_performance['vendor_score'].mean() if 'vendor_score' in vendor_performance.columns else 0
        top_vendor = vendor_performance.iloc[0]['vendor_name'] if 'vendor_name' in vendor_performance.columns else "N/A"

        metrics['total_vendors'] = {
            "value": f"{total_vendors:,}",
            "delta": None,
            "help": f"**Business Logic:** Total count of active vendors with purchase orders. Current: {total_vendors:,} vendors. Formula: COUNT(DISTINCT vendor_name)"
        }

        metrics['avg_vendor_score'] = {
            "value": f"{avg_vendor_score:.1f}",
            "delta": None,
            "help": f"**Business Logic:** Average vendor performance score (0-100 scale). Weighted: OTIF 40%, Fill Rate 30%, Lead Time 30%. Current: {avg_vendor_score:.1f}. Formula: AVG(vendor_score)"
        }

        metrics['top_vendor'] = {
            "value": top_vendor,
            "delta": None,
            "help": f"**Business Logic:** Highest scoring vendor based on composite performance metrics. Current: {top_vendor}"
        }

    else:
        metrics['total_vendors'] = {"value": "N/A", "delta": None}
        metrics['avg_vendor_score'] = {"value": "N/A", "delta": None}
        metrics['top_vendor'] = {"value": "N/A", "delta": None}

    return metrics


# ===== TAB 1: OPEN POs =====

def render_po_aging_chart(po_data):
    """Render PO aging distribution chart"""
    if po_data.empty or 'po_age_days' not in po_data.columns:
        return None

    # Filter to open POs
    open_pos = po_data[po_data['is_open'] == True] if 'is_open' in po_data.columns else po_data

    if open_pos.empty:
        return None

    # Create aging buckets
    open_pos_copy = open_pos.copy()
    open_pos_copy['age_bucket'] = pd.cut(
        open_pos_copy['po_age_days'],
        bins=[0, 7, 14, 30, 60, 90, float('inf')],
        labels=['0-7 days', '8-14 days', '15-30 days', '31-60 days', '61-90 days', '90+ days']
    )

    aging = open_pos_copy.groupby('age_bucket', observed=True).agg({
        'po_number': 'count',
        'po_value': 'sum'
    }).reset_index()
    aging.columns = ['age_bucket', 'po_count', 'total_value']

    # Create chart
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=aging['age_bucket'],
            y=aging['po_count'],
            name='PO Count',
            marker_color=['#06D6A0', '#06D6A0', '#FFD166', '#EF8354', '#F4442E', '#A71E2C']
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=aging['age_bucket'],
            y=aging['total_value'],
            name='Total Value',
            mode='lines+markers',
            line=dict(color='#2E86AB', width=3),
            marker=dict(size=8)
        ),
        secondary_y=True
    )

    fig.update_layout(
        title="Open PO Aging Analysis",
        xaxis_title="PO Age",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    fig.update_yaxes(title_text="PO Count", secondary_y=False)
    fig.update_yaxes(title_text="Total Value ($)", secondary_y=True)

    return fig


def render_open_po_table(po_data):
    """Render open PO data table with filters"""
    if po_data.empty:
        render_info_box("No open purchase orders available", type="info")
        return

    # Filter to open POs
    open_pos = po_data[po_data['is_open'] == True].copy() if 'is_open' in po_data.columns else po_data.copy()

    if open_pos.empty:
        render_info_box("No open purchase orders", type="success")
        return

    st.subheader(f"Open Purchase Orders ({len(open_pos):,} POs)")

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Vendor filter
        vendors = ['All'] + sorted(open_pos['vendor_name'].unique().tolist()) if 'vendor_name' in open_pos.columns else ['All']
        selected_vendor = st.selectbox("Filter by Vendor", vendors, key="vendor_filter")

    with col2:
        # Status filter (based on days to delivery)
        status_options = ['All', 'Overdue', 'Due Soon (< 7 days)', 'On Track']
        selected_status = st.selectbox("Filter by Status", status_options, key="status_filter")

    with col3:
        # Age filter
        age_options = ['All', '0-30 days', '31-60 days', '61-90 days', '90+ days']
        selected_age = st.selectbox("Filter by Age", age_options, key="age_filter")

    with col4:
        # Search by PO or SKU
        search_term = st.text_input("Search PO/SKU", key="search_filter")

    # Apply filters
    filtered_pos = open_pos.copy()

    if selected_vendor != 'All' and 'vendor_name' in filtered_pos.columns:
        filtered_pos = filtered_pos[filtered_pos['vendor_name'] == selected_vendor]

    if selected_status != 'All' and 'days_to_delivery' in filtered_pos.columns:
        if selected_status == 'Overdue':
            filtered_pos = filtered_pos[filtered_pos['days_to_delivery'] < 0]
        elif selected_status == 'Due Soon (< 7 days)':
            filtered_pos = filtered_pos[(filtered_pos['days_to_delivery'] >= 0) & (filtered_pos['days_to_delivery'] <= 7)]
        elif selected_status == 'On Track':
            filtered_pos = filtered_pos[filtered_pos['days_to_delivery'] > 7]

    if selected_age != 'All' and 'po_age_days' in filtered_pos.columns:
        if selected_age == '0-30 days':
            filtered_pos = filtered_pos[filtered_pos['po_age_days'] <= 30]
        elif selected_age == '31-60 days':
            filtered_pos = filtered_pos[(filtered_pos['po_age_days'] > 30) & (filtered_pos['po_age_days'] <= 60)]
        elif selected_age == '61-90 days':
            filtered_pos = filtered_pos[(filtered_pos['po_age_days'] > 60) & (filtered_pos['po_age_days'] <= 90)]
        elif selected_age == '90+ days':
            filtered_pos = filtered_pos[filtered_pos['po_age_days'] > 90]

    if search_term:
        mask = (
            (filtered_pos['po_number'].astype(str).str.contains(search_term, case=False, na=False)) |
            (filtered_pos['sku'].astype(str).str.contains(search_term, case=False, na=False) if 'sku' in filtered_pos.columns else False)
        )
        filtered_pos = filtered_pos[mask]

    # Display count
    st.caption(f"Showing {len(filtered_pos):,} of {len(open_pos):,} open POs")

    # Select columns to display
    display_cols = []
    col_rename = {}

    if 'po_number' in filtered_pos.columns:
        display_cols.append('po_number')
        col_rename['po_number'] = 'PO Number'
    if 'vendor_name' in filtered_pos.columns:
        display_cols.append('vendor_name')
        col_rename['vendor_name'] = 'Vendor'
    if 'sku' in filtered_pos.columns:
        display_cols.append('sku')
        col_rename['sku'] = 'SKU'
    if 'product_description' in filtered_pos.columns:
        display_cols.append('product_description')
        col_rename['product_description'] = 'Product'
    if 'ordered_qty' in filtered_pos.columns:
        display_cols.append('ordered_qty')
        col_rename['ordered_qty'] = 'Ordered'
    if 'open_qty' in filtered_pos.columns:
        display_cols.append('open_qty')
        col_rename['open_qty'] = 'Open Qty'
    if 'po_value' in filtered_pos.columns:
        display_cols.append('po_value')
        col_rename['po_value'] = 'Value'
    if 'po_create_date' in filtered_pos.columns:
        display_cols.append('po_create_date')
        col_rename['po_create_date'] = 'Created'
    if 'expected_delivery_date' in filtered_pos.columns:
        display_cols.append('expected_delivery_date')
        col_rename['expected_delivery_date'] = 'Expected Delivery'
    if 'days_to_delivery' in filtered_pos.columns:
        display_cols.append('days_to_delivery')
        col_rename['days_to_delivery'] = 'Days Until Delivery'
    if 'po_age_days' in filtered_pos.columns:
        display_cols.append('po_age_days')
        col_rename['po_age_days'] = 'Age (Days)'

    # Create display dataframe
    if display_cols:
        display_df = filtered_pos[display_cols].copy()
        display_df = display_df.rename(columns=col_rename)

        # Format numeric columns
        if 'Value' in display_df.columns:
            display_df['Value'] = display_df['Value'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "")
        if 'Ordered' in display_df.columns:
            display_df['Ordered'] = display_df['Ordered'].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "")
        if 'Open Qty' in display_df.columns:
            display_df['Open Qty'] = display_df['Open Qty'].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "")

        # Color code days until delivery
        def highlight_delivery(row):
            if 'Days Until Delivery' in row.index and pd.notnull(row['Days Until Delivery']):
                days = row['Days Until Delivery']
                if days < 0:
                    return ['background-color: #F4442E; color: white'] * len(row)  # Red for overdue
                elif days <= 7:
                    return ['background-color: #FFD166'] * len(row)  # Yellow for due soon
            return [''] * len(row)

        styled_df = display_df.style.apply(highlight_delivery, axis=1)

        st.dataframe(
            styled_df,
            hide_index=True,
            use_container_width=True,
            height=500
        )

        # Export button
        csv = filtered_pos.to_csv(index=False)
        st.download_button(
            label="📥 Export to CSV",
            data=csv,
            file_name=f"open_pos_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True
        )


def render_open_pos_tab(po_data):
    """Render Open POs tab content"""
    st.subheader("Open Purchase Orders Dashboard")

    # PO Aging Chart
    po_aging_chart = render_po_aging_chart(po_data)
    if po_aging_chart:
        render_chart(po_aging_chart, height=400)
    else:
        render_info_box("No PO aging data available", type="info")

    st.divider()

    # Open PO Table
    render_open_po_table(po_data)


# ===== TAB 2: VENDOR PERFORMANCE =====

def render_vendor_score_chart(vendor_performance):
    """Render vendor performance scorecard"""
    if vendor_performance.empty or 'vendor_score' not in vendor_performance.columns:
        return None

    # Take top 10 vendors by score
    top_vendors = vendor_performance.head(10)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=top_vendors['vendor_name'],
        x=top_vendors['vendor_score'],
        orientation='h',
        marker_color=top_vendors['vendor_score'].apply(
            lambda score: '#06D6A0' if score >= 90 else '#FFD166' if score >= 75 else '#F4442E'
        ),
        text=top_vendors['vendor_score'].round(1),
        textposition='outside'
    ))

    # Add reference lines
    fig.add_vline(x=90, line_dash="dash", line_color="green", annotation_text="Excellent: 90+")
    fig.add_vline(x=75, line_dash="dash", line_color="orange", annotation_text="Acceptable: 75+")

    fig.update_layout(
        title="Top 10 Vendor Performance Scores",
        xaxis_title="Vendor Score (0-100)",
        yaxis_title="Vendor",
        xaxis_range=[0, 105],
        height=400
    )

    return fig


def render_vendor_performance_tab(vendor_performance):
    """Render Vendor Performance tab content"""
    st.subheader("Vendor Performance Scorecard")

    if vendor_performance.empty:
        render_info_box("No vendor performance data available", type="info")
        return

    # Vendor Score Chart
    vendor_score_chart = render_vendor_score_chart(vendor_performance)
    if vendor_score_chart:
        render_chart(vendor_score_chart, height=400)
    else:
        render_info_box("No vendor performance data available", type="info")

    st.divider()

    # Vendor Performance Details Table
    st.subheader("All Vendors - Detailed Metrics")

    # Select columns to display
    display_cols = []
    col_rename = {}

    if 'vendor_name' in vendor_performance.columns:
        display_cols.append('vendor_name')
        col_rename['vendor_name'] = 'Vendor'
    if 'vendor_score' in vendor_performance.columns:
        display_cols.append('vendor_score')
        col_rename['vendor_score'] = 'Score'
    if 'po_count' in vendor_performance.columns:
        display_cols.append('po_count')
        col_rename['po_count'] = 'POs'
    if 'otif_pct' in vendor_performance.columns:
        display_cols.append('otif_pct')
        col_rename['otif_pct'] = 'OTIF %'
    if 'avg_fill_rate' in vendor_performance.columns:
        display_cols.append('avg_fill_rate')
        col_rename['avg_fill_rate'] = 'Fill Rate %'
    if 'avg_actual_lead_time' in vendor_performance.columns:
        display_cols.append('avg_actual_lead_time')
        col_rename['avg_actual_lead_time'] = 'Avg Lead Time'
    if 'avg_lead_time_variance' in vendor_performance.columns:
        display_cols.append('avg_lead_time_variance')
        col_rename['avg_lead_time_variance'] = 'Lead Time Variance'
    if 'total_value' in vendor_performance.columns:
        display_cols.append('total_value')
        col_rename['total_value'] = 'Total Value'

    if display_cols:
        vendor_display = vendor_performance[display_cols].copy()
        vendor_display = vendor_display.rename(columns=col_rename)

        # Format columns
        if 'Score' in vendor_display.columns:
            vendor_display['Score'] = vendor_display['Score'].apply(lambda x: f"{x:.1f}" if pd.notnull(x) else "")
        if 'OTIF %' in vendor_display.columns:
            vendor_display['OTIF %'] = vendor_display['OTIF %'].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")
        if 'Fill Rate %' in vendor_display.columns:
            vendor_display['Fill Rate %'] = vendor_display['Fill Rate %'].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "")
        if 'Avg Lead Time' in vendor_display.columns:
            vendor_display['Avg Lead Time'] = vendor_display['Avg Lead Time'].apply(lambda x: f"{x:.0f} days" if pd.notnull(x) else "")
        if 'Lead Time Variance' in vendor_display.columns:
            vendor_display['Lead Time Variance'] = vendor_display['Lead Time Variance'].apply(lambda x: f"{x:+.0f} days" if pd.notnull(x) else "")
        if 'Total Value' in vendor_display.columns:
            vendor_display['Total Value'] = vendor_display['Total Value'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "")

        st.dataframe(
            vendor_display,
            hide_index=True,
            use_container_width=True,
            height=500
        )


# ===== TAB 3: PRICING ANALYSIS =====

def render_pricing_analysis_tab(pricing_analysis, vendor_discount_summary):
    """Render Pricing Analysis tab content with volume discount scoring"""
    st.subheader("Pricing Intelligence & Volume Discount Analysis")

    if pricing_analysis is None or pricing_analysis.empty:
        render_info_box("No pricing analysis data available. Ensure vendor PO and inbound data is loaded.", type="warning")
        return

    if vendor_discount_summary is None or vendor_discount_summary.empty:
        render_info_box("No vendor discount summary available.", type="warning")
        return

    # ===== SECTION 1: USER CONTROLS & FILTERS =====
    st.markdown("### Analysis Controls")
    col1, col2, col3 = st.columns(3)

    with col1:
        # Price increase threshold slider (default 20%)
        price_threshold = st.slider(
            "Price Increase Threshold (%)",
            min_value=0,
            max_value=100,
            value=20,
            step=5,
            help="Flag items with price increases above this percentage vs historical median"
        )

    with col2:
        # Historical pricing window slider (months)
        time_window = st.slider(
            "Historical Window (months)",
            min_value=3,
            max_value=24,
            value=12,
            step=3,
            help="Time period for historical price analysis"
        )

    with col3:
        # Price bucket selector for data visualization
        price_bucket_options = ['All Time Periods'] + sorted(pricing_analysis['price_bucket'].unique().tolist())
        selected_bucket = st.selectbox(
            "Price Time Bucket",
            options=price_bucket_options,
            help="Filter data by time bucket for trend analysis"
        )

    st.divider()

    # Filter data based on user selections
    filtered_pricing = pricing_analysis.copy()

    # Apply time bucket filter
    if selected_bucket != 'All Time Periods':
        filtered_pricing = filtered_pricing[filtered_pricing['price_bucket'] == selected_bucket]

    # Recalculate price spike flags with user threshold
    filtered_pricing['is_price_spike_user'] = filtered_pricing['price_increase_pct'] > price_threshold

    # ===== SECTION 2: KEY PRICING METRICS =====
    st.markdown("### Key Pricing Metrics")

    total_pos = len(filtered_pricing)
    price_spikes = filtered_pricing['is_price_spike_user'].sum()
    overpriced_items = filtered_pricing['is_overpriced'].sum()
    anomalies = filtered_pricing['has_anomaly'].sum()
    worst_offenders = vendor_discount_summary['is_worst_offender'].sum()

    kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5 = st.columns(5)

    with kpi_col1:
        st.metric(
            "Total POs Analyzed",
            f"{total_pos:,}",
            help="Total purchase orders in current analysis"
        )

    with kpi_col2:
        spike_pct = (price_spikes / total_pos * 100) if total_pos > 0 else 0
        st.metric(
            "Price Spikes",
            f"{price_spikes:,}",
            delta=f"{spike_pct:.1f}%",
            help=f"POs with price increase >{price_threshold}% vs historical median"
        )

    with kpi_col3:
        overprice_pct = (overpriced_items / total_pos * 100) if total_pos > 0 else 0
        st.metric(
            "Overpriced Items",
            f"{overpriced_items:,}",
            delta=f"{overprice_pct:.1f}%",
            help="POs priced >10% above best market price for same SKU"
        )

    with kpi_col4:
        anomaly_pct = (anomalies / total_pos * 100) if total_pos > 0 else 0
        st.metric(
            "Pricing Anomalies",
            f"{anomalies:,}",
            delta=f"{anomaly_pct:.1f}%",
            help="POs flagged with any pricing anomaly (spikes, overpriced, volatile)"
        )

    with kpi_col5:
        st.metric(
            "Worst Discount Vendors",
            f"{worst_offenders:,}",
            help="Vendors in bottom 25% for discount consistency and effectiveness"
        )

    st.divider()

    # ===== SECTION 3: VENDOR DISCOUNT CONSISTENCY SCORECARD =====
    st.markdown("### 🎯 Vendor Discount Scorecard")
    st.caption("Ranking vendors by discount effectiveness, price consistency, and competitive pricing")

    # Sort by consistency score
    scorecard = vendor_discount_summary.sort_values('consistency_score', ascending=False).head(20)

    # Color code vendors
    def color_score(val):
        if val >= 75:
            return 'background-color: #d4edda'  # Green for good
        elif val >= 50:
            return 'background-color: #fff3cd'  # Yellow for average
        else:
            return 'background-color: #f8d7da'  # Red for poor

    # Display scorecard
    scorecard_display = scorecard[['vendor_name', 'consistency_score', 'avg_discount_score',
                                    'avg_price_variance_pct', 'overpriced_items_count', 'vendor_rank']].copy()
    scorecard_display.columns = ['Vendor', 'Consistency Score', 'Discount Effectiveness',
                                  'Price Variance %', 'Overpriced Items', 'Rank']
    scorecard_display['Consistency Score'] = scorecard_display['Consistency Score'].round(1)
    scorecard_display['Discount Effectiveness'] = scorecard_display['Discount Effectiveness'].round(1)
    scorecard_display['Price Variance %'] = scorecard_display['Price Variance %'].round(1)

    st.dataframe(
        scorecard_display.style.applymap(color_score, subset=['Consistency Score']),
        use_container_width=True
    )

    st.divider()

    # ===== SECTION 4: WORST OFFENDERS - ERRATIC DISCOUNTING =====
    st.markdown("### ⚠️ Worst Offenders: Erratic or Poor Discounting")
    st.caption("Vendors with inconsistent volume discounts, high price variance, or poor competitive pricing")

    worst_vendors = vendor_discount_summary[vendor_discount_summary['is_worst_offender'] == True].sort_values('consistency_score')

    if not worst_vendors.empty:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Vendor Discount Issues")
            worst_display = worst_vendors[['vendor_name', 'consistency_score', 'avg_qty_price_corr',
                                           'avg_price_variance_pct']].copy()
            worst_display.columns = ['Vendor', 'Score', 'Qty-Price Correlation', 'Price Variance %']
            worst_display['Score'] = worst_display['Score'].round(1)
            worst_display['Qty-Price Correlation'] = worst_display['Qty-Price Correlation'].round(2)
            worst_display['Price Variance %'] = worst_display['Price Variance %'].round(1)

            st.dataframe(worst_display, use_container_width=True)

        with col2:
            st.markdown("#### Vendor Comparison Chart")
            # Bar chart showing consistency scores
            fig = go.Figure()
            fig.add_trace(go.Bar(
                y=worst_vendors['vendor_name'].head(10),
                x=worst_vendors['consistency_score'].head(10),
                orientation='h',
                marker_color='#dc3545',
                text=worst_vendors['consistency_score'].head(10).round(1),
                textposition='auto'
            ))
            fig.update_layout(
                title="Bottom 10 Vendors by Consistency Score",
                xaxis_title="Consistency Score (0-100)",
                yaxis_title="Vendor",
                height=400
            )
            render_chart(fig, height=400)
    else:
        st.info("No vendors flagged as worst offenders in current data.")

    st.divider()

    # ===== SECTION 5: PRICE SPIKE ALERTS =====
    st.markdown(f"### 🚨 Price Spike Alerts (>{price_threshold}% increase)")
    st.caption("Open POs with significant price increases vs historical pricing")

    price_spike_alerts = filtered_pricing[
        (filtered_pricing['is_open'] == True) &
        (filtered_pricing['is_price_spike_user'] == True)
    ].sort_values('price_increase_pct', ascending=False).head(50)

    if not price_spike_alerts.empty:
        alert_display = price_spike_alerts[['po_number', 'sku', 'vendor_name', 'unit_price',
                                             'price_median', 'price_increase_pct', 'ordered_qty']].copy()
        alert_display.columns = ['PO Number', 'SKU', 'Vendor', 'Current Price', 'Historical Median',
                                  'Price Increase %', 'Order Qty']
        alert_display['Current Price'] = alert_display['Current Price'].round(2)
        alert_display['Historical Median'] = alert_display['Historical Median'].round(2)
        alert_display['Price Increase %'] = alert_display['Price Increase %'].round(1)

        render_data_table(alert_display, max_rows=50, downloadable=True, download_filename="price_spike_alerts.csv")
    else:
        st.info(f"No open POs with price increases >{price_threshold}%")

    st.divider()

    # ===== SECTION 6: VOLUME DISCOUNT EFFECTIVENESS =====
    st.markdown("### 📊 Volume Discount Analysis")
    st.caption("Analyzing vendor-to-vendor discount effectiveness for the same SKUs")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Best Volume Discounters")
        st.caption("Vendors with strongest negative qty-price correlation (higher qty = lower price)")

        best_discounters = vendor_discount_summary.sort_values('avg_discount_score', ascending=False).head(10)
        best_display = best_discounters[['vendor_name', 'avg_discount_score', 'avg_qty_price_corr']].copy()
        best_display.columns = ['Vendor', 'Discount Score', 'Qty-Price Correlation']
        best_display['Discount Score'] = best_display['Discount Score'].round(1)
        best_display['Qty-Price Correlation'] = best_display['Qty-Price Correlation'].round(2)

        st.dataframe(best_display, use_container_width=True)

    with col2:
        st.markdown("#### Worst Volume Discounters")
        st.caption("Vendors with weak or positive qty-price correlation")

        worst_discounters = vendor_discount_summary.sort_values('avg_discount_score').head(10)
        worst_disc_display = worst_discounters[['vendor_name', 'avg_discount_score', 'avg_qty_price_corr']].copy()
        worst_disc_display.columns = ['Vendor', 'Discount Score', 'Qty-Price Correlation']
        worst_disc_display['Discount Score'] = worst_disc_display['Discount Score'].round(1)
        worst_disc_display['Qty-Price Correlation'] = worst_disc_display['Qty-Price Correlation'].round(2)

        st.dataframe(worst_disc_display, use_container_width=True)

    st.divider()

    # ===== SECTION 7: PRICE COMPETITIVENESS - MULTI-VENDOR SKUs =====
    st.markdown("### 💡 Price Competitiveness: Multi-Vendor SKUs")
    st.caption("SKUs available from multiple vendors - compare pricing and identify savings opportunities")

    # Find SKUs with multiple vendors
    multi_vendor_skus = filtered_pricing.groupby('sku')['vendor_name'].nunique()
    multi_vendor_skus = multi_vendor_skus[multi_vendor_skus > 1].sort_values(ascending=False)

    if not multi_vendor_skus.empty:
        st.markdown(f"**{len(multi_vendor_skus):,} SKUs** available from multiple vendors")

        # Show top opportunities for vendor switching
        st.markdown("#### Top Savings Opportunities")

        # Calculate potential savings per SKU
        savings_opps = []
        for sku in multi_vendor_skus.head(20).index:
            sku_data = filtered_pricing[filtered_pricing['sku'] == sku]
            best_price = sku_data['unit_price'].min()
            worst_price = sku_data['unit_price'].max()
            savings_pct = ((worst_price - best_price) / best_price * 100) if best_price > 0 else 0

            best_vendor = sku_data[sku_data['unit_price'] == best_price]['vendor_name'].iloc[0]
            worst_vendor = sku_data[sku_data['unit_price'] == worst_price]['vendor_name'].iloc[0]

            savings_opps.append({
                'SKU': sku,
                'Vendor Count': len(sku_data['vendor_name'].unique()),
                'Best Price': best_price,
                'Best Vendor': best_vendor,
                'Worst Price': worst_price,
                'Worst Vendor': worst_vendor,
                'Savings %': savings_pct
            })

        savings_df = pd.DataFrame(savings_opps).sort_values('Savings %', ascending=False)
        savings_df['Best Price'] = savings_df['Best Price'].round(2)
        savings_df['Worst Price'] = savings_df['Worst Price'].round(2)
        savings_df['Savings %'] = savings_df['Savings %'].round(1)

        render_data_table(savings_df, max_rows=20, downloadable=True, download_filename="vendor_savings_opportunities.csv")
    else:
        st.info("No SKUs with multiple vendor options found in current data.")

    st.divider()

    # ===== SECTION 8: PRICING ANOMALIES SUMMARY =====
    st.markdown("### 🔍 Pricing Anomalies Summary")
    st.caption("Comprehensive view of all flagged pricing issues")

    anomaly_summary = filtered_pricing[filtered_pricing['has_anomaly'] == True].copy()

    if not anomaly_summary.empty:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Anomaly Breakdown")
            anomaly_counts = pd.DataFrame({
                'Anomaly Type': ['Price Spikes', 'Overpriced Items', 'Volatile Pricing'],
                'Count': [
                    anomaly_summary['is_price_spike'].sum(),
                    anomaly_summary['is_overpriced'].sum(),
                    anomaly_summary['is_volatile_pricing'].sum()
                ]
            })

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=anomaly_counts['Anomaly Type'],
                y=anomaly_counts['Count'],
                marker_color=['#dc3545', '#fd7e14', '#ffc107'],
                text=anomaly_counts['Count'],
                textposition='auto'
            ))
            fig.update_layout(
                title="Anomaly Type Distribution",
                xaxis_title="Anomaly Type",
                yaxis_title="Count",
                height=350
            )
            render_chart(fig, height=350)

        with col2:
            st.markdown("#### Top Anomalous Vendors")
            vendor_anomalies = anomaly_summary.groupby('vendor_name').size().sort_values(ascending=False).head(10)

            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                y=vendor_anomalies.index,
                x=vendor_anomalies.values,
                orientation='h',
                marker_color='#6c757d',
                text=vendor_anomalies.values,
                textposition='auto'
            ))
            fig2.update_layout(
                title="Vendors with Most Anomalies",
                xaxis_title="Anomaly Count",
                yaxis_title="Vendor",
                height=350
            )
            render_chart(fig2, height=350)

        st.markdown("#### Detailed Anomaly Records")
        anomaly_detail = anomaly_summary[['po_number', 'sku', 'vendor_name', 'unit_price',
                                           'is_price_spike', 'is_overpriced', 'is_volatile_pricing',
                                           'price_increase_pct']].head(100).copy()
        anomaly_detail.columns = ['PO Number', 'SKU', 'Vendor', 'Unit Price', 'Price Spike',
                                    'Overpriced', 'Volatile', 'Price Increase %']
        anomaly_detail['Unit Price'] = anomaly_detail['Unit Price'].round(2)
        anomaly_detail['Price Increase %'] = anomaly_detail['Price Increase %'].round(1)

        render_data_table(anomaly_detail, max_rows=100, downloadable=True, download_filename="pricing_anomalies.csv")
    else:
        st.success("No pricing anomalies detected in current dataset!")

    st.divider()

    # ===== SECTION 9: PRICE ELASTICITY ANALYSIS =====
    st.markdown("### 📈 Price Elasticity Analysis")
    st.caption("Visualize how unit price changes with order quantity - compare vendors and products")

    # Vendor selector for elasticity analysis
    col1, col2 = st.columns(2)

    with col1:
        available_vendors = sorted(filtered_pricing['vendor_name'].unique().tolist())
        selected_vendors_elast = st.multiselect(
            "Select Vendors to Compare",
            options=available_vendors,
            default=available_vendors[:min(3, len(available_vendors))],
            help="Compare price elasticity across vendors"
        )

    with col2:
        # SKU selector (optional - if empty, show vendor's full portfolio)
        available_skus = sorted(filtered_pricing['sku'].unique().tolist())
        selected_sku_elast = st.selectbox(
            "Filter by SKU (optional)",
            options=['All SKUs'] + available_skus,
            help="Analyze a specific SKU or view vendor's full portfolio"
        )

    if selected_vendors_elast:
        # Filter data for selected vendors
        elasticity_data = filtered_pricing[filtered_pricing['vendor_name'].isin(selected_vendors_elast)].copy()

        if selected_sku_elast != 'All SKUs':
            elasticity_data = elasticity_data[elasticity_data['sku'] == selected_sku_elast]

        if not elasticity_data.empty:
            st.markdown("#### Price vs. Quantity Relationship")

            # Create scatter plot showing price elasticity
            fig = go.Figure()

            for vendor in selected_vendors_elast:
                vendor_data = elasticity_data[elasticity_data['vendor_name'] == vendor]
                if not vendor_data.empty:
                    fig.add_trace(go.Scatter(
                        x=vendor_data['ordered_qty'],
                        y=vendor_data['unit_price'],
                        mode='markers',
                        name=vendor,
                        marker=dict(size=8, opacity=0.6),
                        text=[f"SKU: {sku}<br>Qty: {qty:,.0f}<br>Price: ${price:.2f}<br>PO: {po}"
                              for sku, qty, price, po in zip(vendor_data['sku'], vendor_data['ordered_qty'],
                                                              vendor_data['unit_price'], vendor_data['po_number'])],
                        hovertemplate='%{text}<extra></extra>'
                    ))

            fig.update_layout(
                title="Price Elasticity: Quantity vs. Unit Price",
                xaxis_title="Order Quantity",
                yaxis_title="Unit Price ($)",
                hovermode='closest',
                height=500,
                showlegend=True
            )

            render_chart(fig, height=500)

            st.caption("**Interpretation:** Points trending downward-right indicate good volume discounts (higher qty = lower price). Flat or upward trends indicate poor/no volume discounting.")

            # Show elasticity summary table
            st.markdown("#### Elasticity Summary by Vendor")

            elasticity_summary = []
            for vendor in selected_vendors_elast:
                vendor_data = elasticity_data[elasticity_data['vendor_name'] == vendor]
                if len(vendor_data) >= 2:
                    # Calculate correlation coefficient
                    corr = vendor_data[['ordered_qty', 'unit_price']].corr().iloc[0, 1]

                    # Calculate price range
                    price_range = vendor_data['unit_price'].max() - vendor_data['unit_price'].min()
                    price_range_pct = (price_range / vendor_data['unit_price'].mean() * 100) if vendor_data['unit_price'].mean() > 0 else 0

                    elasticity_summary.append({
                        'Vendor': vendor,
                        'Data Points': len(vendor_data),
                        'Qty-Price Correlation': corr,
                        'Price Range': f"${price_range:.2f}",
                        'Price Range %': f"{price_range_pct:.1f}%",
                        'Elasticity Assessment': 'Good Discounting' if corr < -0.3 else ('Poor Discounting' if corr > 0 else 'Neutral')
                    })

            if elasticity_summary:
                elasticity_df = pd.DataFrame(elasticity_summary)
                st.dataframe(elasticity_df, use_container_width=True)
            else:
                st.info("Not enough data points to calculate elasticity for selected vendors.")

        else:
            st.warning("No data available for selected filters.")
    else:
        st.info("Select at least one vendor to analyze price elasticity.")


# ===== TAB 4: AT-RISK POs =====

def render_at_risk_pos_tab(po_data):
    """Render At-Risk POs tab content"""
    st.subheader("At-Risk Purchase Orders")

    if po_data.empty:
        render_info_box("No purchase order data available", type="info")
        return

    # Filter to at-risk POs
    open_pos = po_data[po_data['is_open'] == True] if 'is_open' in po_data.columns else po_data

    if 'days_to_delivery' not in open_pos.columns:
        render_info_box("Delivery date information not available", type="warning")
        return

    # At-risk criteria: overdue or due within 7 days
    at_risk_pos = open_pos[open_pos['days_to_delivery'] <= 7].copy()

    if at_risk_pos.empty:
        st.success("✓ No at-risk purchase orders - all POs on track!")
        return

    st.warning(f"⚠️ {len(at_risk_pos):,} purchase orders require attention")

    # Categorize by urgency
    overdue = at_risk_pos[at_risk_pos['days_to_delivery'] < 0]
    due_soon = at_risk_pos[(at_risk_pos['days_to_delivery'] >= 0) & (at_risk_pos['days_to_delivery'] <= 7)]

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Overdue POs", f"{len(overdue):,}", help="POs past expected delivery date")
    with col2:
        st.metric("Due Within 7 Days", f"{len(due_soon):,}", help="POs approaching delivery deadline")

    st.divider()

    # Display at-risk POs table
    if not at_risk_pos.empty:
        # Select columns to display
        display_cols = []
        col_rename = {}

        if 'po_number' in at_risk_pos.columns:
            display_cols.append('po_number')
            col_rename['po_number'] = 'PO Number'
        if 'vendor_name' in at_risk_pos.columns:
            display_cols.append('vendor_name')
            col_rename['vendor_name'] = 'Vendor'
        if 'sku' in at_risk_pos.columns:
            display_cols.append('sku')
            col_rename['sku'] = 'SKU'
        if 'open_qty' in at_risk_pos.columns:
            display_cols.append('open_qty')
            col_rename['open_qty'] = 'Open Qty'
        if 'po_value' in at_risk_pos.columns:
            display_cols.append('po_value')
            col_rename['po_value'] = 'Value'
        if 'expected_delivery_date' in at_risk_pos.columns:
            display_cols.append('expected_delivery_date')
            col_rename['expected_delivery_date'] = 'Expected Delivery'
        if 'days_to_delivery' in at_risk_pos.columns:
            display_cols.append('days_to_delivery')
            col_rename['days_to_delivery'] = 'Days Until Delivery'
        if 'po_age_days' in at_risk_pos.columns:
            display_cols.append('po_age_days')
            col_rename['po_age_days'] = 'PO Age (Days)'

        if display_cols:
            display_df = at_risk_pos[display_cols].copy()
            display_df = display_df.rename(columns=col_rename)

            # Format numeric columns
            if 'Value' in display_df.columns:
                display_df['Value'] = display_df['Value'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "")
            if 'Open Qty' in display_df.columns:
                display_df['Open Qty'] = display_df['Open Qty'].apply(lambda x: f"{int(x):,}" if pd.notnull(x) else "")

            # Sort by urgency (most urgent first)
            display_df = display_df.sort_values('Days Until Delivery')

            # Color code by urgency
            def highlight_urgency(row):
                if 'Days Until Delivery' in row.index and pd.notnull(row['Days Until Delivery']):
                    days = row['Days Until Delivery']
                    if days < 0:
                        return ['background-color: #F4442E; color: white'] * len(row)  # Red for overdue
                    elif days <= 7:
                        return ['background-color: #FFD166'] * len(row)  # Yellow for due soon
                return [''] * len(row)

            styled_df = display_df.style.apply(highlight_urgency, axis=1)

            st.dataframe(
                styled_df,
                hide_index=True,
                use_container_width=True,
                height=500
            )


# ===== MAIN VENDOR PAGE WITH TABS =====

def render_vendor_page(po_data, vendor_performance, pricing_analysis=None, vendor_discount_summary=None):
    """Main vendor page render function with tabbed interface"""

    # Page header
    render_page_header(
        "Vendor & Procurement Dashboard",
        icon="🏭",
        subtitle="Open PO management, vendor performance tracking, pricing intelligence, and procurement analytics"
    )

    # Calculate metrics
    metrics = calculate_vendor_metrics(po_data, vendor_performance)

    # Render KPI rows
    st.subheader("Key Procurement Metrics")

    # Row 1: Open PO Overview
    kpi_row_1 = {
        "Open POs": metrics.get('total_open_pos', {}),
        "Open PO Value": metrics.get('open_po_value', {}),
        "Open PO Qty": metrics.get('open_po_qty', {})
    }
    render_kpi_row(kpi_row_1)

    st.divider()

    # Row 2: PO Health & Vendor Performance
    kpi_row_2 = {
        "At-Risk POs": metrics.get('at_risk_pos', {}),
        "Avg PO Age": metrics.get('avg_po_age', {}),
        "Active Vendors": metrics.get('total_vendors', {})
    }
    render_kpi_row(kpi_row_2)

    st.divider()

    # Tabbed Interface
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Open POs",
        "📊 Vendor Performance",
        "💰 Pricing Analysis",
        "⚠️ At-Risk POs"
    ])

    with tab1:
        render_open_pos_tab(po_data)

    with tab2:
        render_vendor_performance_tab(vendor_performance)

    with tab3:
        render_pricing_analysis_tab(pricing_analysis, vendor_discount_summary)

    with tab4:
        render_at_risk_pos_tab(po_data)
