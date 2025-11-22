"""
Backorder Management Page
Comprehensive backorder tracking with:
- Aging analysis and visualization
- Customer and SKU breakdowns
- Priority ranking
- Category analysis
- Export functionality
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import render_page_header, render_kpi_row, render_chart, render_data_table, render_filter_section, render_info_box, render_metric_card
from business_rules import (
    BACKORDER_RULES,
    load_alternate_codes_mapping, get_alternate_codes, get_current_code, is_old_code
)

# ===== HELPER FUNCTIONS =====

@st.cache_data(show_spinner=False)
def process_deliveries_data(deliveries_df):
    """
    Process deliveries data - handle both unified format and processed format.
    Returns deliveries with 'ship_date', 'units_issued', 'sku', 'customer_name' columns.
    CACHED for performance - called multiple times per page load.

    Args:
        deliveries_df: Either unified format (raw columns) or processed format

    Returns:
        Processed deliveries DataFrame
    """
    if deliveries_df is None or deliveries_df.empty:
        return pd.DataFrame()

    # Check if already processed (has 'ship_date' column)
    if 'ship_date' in deliveries_df.columns:
        return deliveries_df

    # Unified format - need to process
    # Rename columns from unified format
    required_cols = ["Item - SAP Model Code", "Delivery Creation Date: Date", "Deliveries - TOTAL Goods Issue Qty"]

    # Check if we have the required columns
    if not all(col in deliveries_df.columns for col in required_cols):
        # Return empty if columns don't match
        return pd.DataFrame()

    # Use list comprehension for column selection (faster)
    cols_to_select = required_cols.copy()
    if "Customer Name - SHIP TO" in deliveries_df.columns:
        cols_to_select.append("Customer Name - SHIP TO")

    processed = deliveries_df[cols_to_select].copy()

    # Rename columns
    processed = processed.rename(columns={
        "Item - SAP Model Code": "sku",
        "Delivery Creation Date: Date": "ship_date",
        "Deliveries - TOTAL Goods Issue Qty": "units_issued",
        "Customer Name - SHIP TO": "customer_name"
    })

    # Convert types (vectorized operations)
    processed['ship_date'] = pd.to_datetime(processed['ship_date'], format='%m/%d/%y', errors='coerce')
    processed['units_issued'] = pd.to_numeric(processed['units_issued'], errors='coerce').fillna(0)
    processed.dropna(subset=['ship_date'], inplace=True)

    return processed

# ===== SETTINGS AND CONFIGURATION =====

def render_backorder_settings_sidebar():
    """Render sidebar settings for backorder page"""

    st.sidebar.header("🔍 Search & Filters")

    # Customer search
    customer_search = st.sidebar.text_input(
        "Search Customer",
        value="",
        key="customer_search",
        placeholder="Enter customer name...",
        help="Search for specific customer"
    )

    # SKU search
    sku_search = st.sidebar.text_input(
        "Search SKU",
        value="",
        key="sku_search_backorder",
        placeholder="Enter SKU code...",
        help="Search for specific SKU"
    )

    st.sidebar.divider()

    # === PRIORITY SETTINGS ===
    st.sidebar.header("⚠️ Priority Settings")

    critical_age = st.sidebar.slider(
        "Critical Age (days)",
        min_value=7,
        max_value=90,
        value=BACKORDER_RULES["alerts"]["critical_age_days"],
        step=1,
        key="critical_age",
        help="Orders older than this are marked critical"
    )

    high_qty_threshold = st.sidebar.number_input(
        "High Quantity Threshold",
        min_value=100,
        max_value=10000,
        value=BACKORDER_RULES["alerts"]["high_quantity_threshold"],
        step=100,
        key="high_qty",
        help="Orders with quantity above this are flagged"
    )

    st.sidebar.divider()

    # === EXPORT ===
    st.sidebar.header("📥 Export Data")

    export_section = st.sidebar.selectbox(
        "Select dataset:",
        options=[
            "All Backorders",
            "Critical Age Backorders",
            "High Quantity Backorders",
            "Top 50 by Quantity",
            "By Customer",
            "By SKU",
            "By Category"
        ],
        key="backorder_export_section"
    )

    st.sidebar.divider()

    return {
        "customer_search": customer_search,
        "sku_search": sku_search,
        "critical_age": critical_age,
        "high_qty_threshold": high_qty_threshold,
        "export_section": export_section
    }

# ===== EXPORT FUNCTIONS =====

@st.cache_data(show_spinner="Generating Excel export...")
def create_backorder_excel_export(data, section_name):
    """Create formatted Excel export for backorder data"""
    output = BytesIO()
    export_df = data.copy()

    # Select relevant columns
    columns_to_export = [
        'sales_order', 'sku', 'product_name', 'customer_name', 'backorder_qty',
        'days_on_backorder', 'order_date', 'category', 'sales_org',
        'order_type', 'priority_score'
    ]
    columns_to_export = [col for col in columns_to_export if col in export_df.columns]

    export_df = export_df[columns_to_export]

    # Write to Excel with formatting
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, sheet_name=section_name[:31], index=False)

        workbook = writer.book
        worksheet = writer.sheets[section_name[:31]]

        # Header format
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#FF6B6B',
            'font_color': 'white',
            'border': 1
        })

        # Write headers
        for col_num, value in enumerate(export_df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Auto-fit columns
        for i, col in enumerate(export_df.columns):
            max_len = max(export_df[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet.set_column(i, i, min(max_len, 50))

    output.seek(0)
    return output

@st.cache_data(show_spinner=False)
def prepare_backorder_export_data(data, section, settings):
    """Prepare data based on export section selection"""
    if section == "All Backorders":
        return data
    elif section == "Critical Age Backorders":
        return data[data['days_on_backorder'] >= settings['critical_age']]
    elif section == "High Quantity Backorders":
        return data[data['backorder_qty'] >= settings['high_qty_threshold']]
    elif section == "Top 50 by Quantity":
        return data.nlargest(50, 'backorder_qty')
    elif section == "By Customer":
        return data.sort_values(['customer_name', 'days_on_backorder'], ascending=[True, False])
    elif section == "By SKU":
        return data.sort_values(['sku', 'days_on_backorder'], ascending=[True, False])
    elif section == "By Category":
        return data.sort_values(['category', 'days_on_backorder'], ascending=[True, False])
    return data

# ===== METRICS CALCULATION =====

@st.cache_data(show_spinner=False)
def calculate_backorder_metrics(backorder_data):
    """Calculate key backorder metrics"""
    if backorder_data.empty:
        return {}

    total_orders = len(backorder_data)
    total_units = backorder_data['backorder_qty'].sum()
    unique_skus = backorder_data['sku'].nunique()
    unique_customers = backorder_data['customer_name'].nunique()

    # Average age
    avg_age = backorder_data['days_on_backorder'].mean()

    # Critical orders (>30 days)
    critical_orders = len(backorder_data[backorder_data['days_on_backorder'] >= 30])

    return {
        "total_orders": total_orders,
        "total_units": total_units,
        "unique_skus": unique_skus,
        "unique_customers": unique_customers,
        "avg_age": avg_age,
        "critical_orders": critical_orders
    }

# ===== VISUALIZATIONS =====

def render_aging_distribution_chart(backorder_data):
    """Render backorder aging distribution"""
    if backorder_data.empty:
        return None

    # Create aging buckets based on business rules
    buckets = BACKORDER_RULES["aging_buckets"]["buckets"]
    labels = [bucket["name"] for bucket in buckets]

    # Create bins from buckets
    bins = [bucket["min"] for bucket in buckets] + [buckets[-1]["max"]]
    backorder_data['age_bucket'] = pd.cut(
        backorder_data['days_on_backorder'],
        bins=bins,
        labels=labels,
        include_lowest=True
    )

    aging_summary = backorder_data.groupby('age_bucket', observed=True).agg({
        'backorder_qty': 'sum',
        'sales_order': 'count'
    }).reset_index()
    aging_summary.columns = ['age_bucket', 'units', 'order_count']

    # Create subplot with two y-axes
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=aging_summary['age_bucket'],
            y=aging_summary['units'],
            name='Units on Backorder',
            marker_color=['#06D6A0', '#4ECDC4', '#FFD166', '#FF8C42', '#FF6B6B']
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=aging_summary['age_bucket'],
            y=aging_summary['order_count'],
            name='Number of Orders',
            mode='lines+markers',
            line=dict(color='#2C3E50', width=3),
            marker=dict(size=10)
        ),
        secondary_y=True
    )

    fig.update_xaxes(title_text="Backorder Age")
    fig.update_yaxes(title_text="Units on Backorder", secondary_y=False)
    fig.update_yaxes(title_text="Number of Orders", secondary_y=True)

    fig.update_layout(
        title="Backorder Aging Distribution",
        hovermode='x unified',
        height=400
    )

    return fig

def render_top_customers_chart(backorder_data):
    """Render top customers by backorder quantity"""
    if backorder_data.empty:
        return None

    customer_summary = backorder_data.groupby('customer_name').agg({
        'backorder_qty': 'sum',
        'sales_order': 'count'
    }).reset_index().sort_values('backorder_qty', ascending=False).head(10)

    customer_summary.columns = ['customer', 'units', 'orders']

    fig = go.Figure(data=[
        go.Bar(
            x=customer_summary['units'],
            y=customer_summary['customer'],
            orientation='h',
            marker_color='#FF6B6B',
            text=customer_summary['units'],
            textposition='auto'
        )
    ])

    fig.update_layout(
        title="Top 10 Customers by Backorder Quantity",
        xaxis_title="Units on Backorder",
        yaxis_title="Customer",
        height=400
    )

    return fig

def render_category_breakdown_chart(backorder_data):
    """Render backorder breakdown by category"""
    if backorder_data.empty or 'category' not in backorder_data.columns:
        return None

    category_summary = backorder_data.groupby('category').agg({
        'backorder_qty': 'sum',
        'sales_order': 'count'
    }).reset_index().sort_values('backorder_qty', ascending=False).head(15)

    category_summary.columns = ['category', 'units', 'orders']

    fig = px.pie(
        category_summary,
        values='units',
        names='category',
        title='Backorder Distribution by Category',
        hole=0.4
    )

    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.update_layout(height=400)

    return fig

# ===== FILTERS =====

def get_backorder_filters(backorder_data):
    """Define available filters for backorder data - returns list format for render_filter_section"""
    if backorder_data.empty:
        return []

    return [
        {
            "label": "Category",
            "key": "Category",
            "type": "multiselect",
            "options": sorted(backorder_data['category'].dropna().unique().tolist()),
            "default": []
        },
        {
            "label": "Customer",
            "key": "Customer",
            "type": "multiselect",
            "options": sorted(backorder_data['customer_name'].dropna().unique().tolist()),
            "default": []
        },
        {
            "label": "Sales Org",
            "key": "Sales Org",
            "type": "multiselect",
            "options": sorted(backorder_data['sales_org'].dropna().unique().tolist()),
            "default": []
        },
        {
            "label": "Age Range",
            "key": "Age Range",
            "type": "slider",
            "min": int(backorder_data['days_on_backorder'].min()),
            "max": int(backorder_data['days_on_backorder'].max()),
            "default": (int(backorder_data['days_on_backorder'].min()), int(backorder_data['days_on_backorder'].max()))
        }
    ]

def apply_backorder_filters(backorder_data, filter_values, settings):
    """Apply selected filters to backorder data"""
    filtered = backorder_data.copy()

    # Customer search
    if settings['customer_search']:
        filtered = filtered[filtered['customer_name'].str.contains(settings['customer_search'], case=False, na=False)]

    # SKU search
    if settings['sku_search']:
        filtered = filtered[filtered['sku'].str.contains(settings['sku_search'], case=False, na=False)]

    # Category filter
    if filter_values.get("Category"):
        filtered = filtered[filtered['category'].isin(filter_values["Category"])]

    # Customer filter
    if filter_values.get("Customer"):
        filtered = filtered[filtered['customer_name'].isin(filter_values["Customer"])]

    # Sales Org filter
    if filter_values.get("Sales Org"):
        filtered = filtered[filtered['sales_org'].isin(filter_values["Sales Org"])]

    # Age range filter
    if filter_values.get("Age Range"):
        min_age, max_age = filter_values["Age Range"]
        filtered = filtered[(filtered['days_on_backorder'] >= min_age) & (filtered['days_on_backorder'] <= max_age)]

    return filtered

# ===== PRIORITY SCORING =====

@st.cache_data(show_spinner=False)
def calculate_priority_score(backorder_data, backorder_relief_data=None):
    """
    Calculate enhanced multi-factor priority score for backorders

    Enhanced Priority Formula (Week 3):
    - Age: 20% (older backorders = higher priority)
    - Quantity: 15% (larger quantities = higher priority)
    - Vendor Reliability: 20% (unreliable vendors = higher priority)
    - Days Until Relief: 25% (longer wait = higher priority)
    - Customer Value: 10% (placeholder - data not available yet)
    - Product Margin: 10% (placeholder - data not available yet)

    Args:
        backorder_data: Backorder dataframe with columns: sku, backorder_qty, days_on_backorder
        backorder_relief_data: Optional relief data from backorder_relief_analysis with vendor OTIF and days_until_relief

    Returns:
        backorder_data with 'priority_score' column (0-100 scale)
    """
    if backorder_data.empty:
        return backorder_data

    # Create working copy to avoid modifying original
    bo_data = backorder_data.copy()

    # ===== FACTOR 1: Age (20% weight) =====
    max_age = bo_data['days_on_backorder'].max()
    if max_age > 0:
        bo_data['age_normalized'] = bo_data['days_on_backorder'] / max_age
    else:
        bo_data['age_normalized'] = 0

    # ===== FACTOR 2: Quantity (15% weight) =====
    max_qty = bo_data['backorder_qty'].max()
    if max_qty > 0:
        bo_data['qty_normalized'] = bo_data['backorder_qty'] / max_qty
    else:
        bo_data['qty_normalized'] = 0

    # ===== FACTOR 3: Vendor Reliability (20% weight) =====
    # Score based on vendor OTIF from backorder_relief_data
    # No PO = 100 (highest priority), <75% OTIF = 80, 75-90% OTIF = 50, >90% OTIF = 20
    if backorder_relief_data is not None and not backorder_relief_data.empty and 'vendor_otif_pct' in backorder_relief_data.columns:
        # Merge vendor OTIF data
        relief_subset = backorder_relief_data[['sales_order', 'sku', 'vendor_otif_pct', 'has_po_coverage']].copy()
        bo_data = bo_data.merge(relief_subset, on=['sales_order', 'sku'], how='left', suffixes=('', '_relief'))

        # Calculate vendor reliability score (0-100, normalized to 0-1)
        def calc_vendor_score(row):
            if pd.isna(row.get('has_po_coverage')) or not row.get('has_po_coverage'):
                return 1.0  # No PO = max priority
            otif = row.get('vendor_otif_pct', 50)
            if otif >= 90:
                return 0.2  # Reliable vendor = low priority
            elif otif >= 75:
                return 0.5  # Medium reliability
            elif otif >= 0:
                return 0.8  # Unreliable vendor = high priority
            else:
                return 1.0  # No data = max priority

        bo_data['vendor_reliability_normalized'] = bo_data.apply(calc_vendor_score, axis=1)
    else:
        # No relief data available - assume medium priority for all
        bo_data['vendor_reliability_normalized'] = 0.5

    # ===== FACTOR 4: Days Until Relief (25% weight) =====
    # Longer wait = higher priority. No PO = 100, >60 days = 80, 30-60 days = 60, 7-30 days = 40, <7 days = 20
    if backorder_relief_data is not None and not backorder_relief_data.empty and 'days_until_relief' in backorder_relief_data.columns:
        # Merge days until relief (may already be merged above)
        if 'days_until_relief' not in bo_data.columns:
            relief_subset = backorder_relief_data[['sales_order', 'sku', 'days_until_relief', 'has_po_coverage']].copy()
            bo_data = bo_data.merge(relief_subset, on=['sales_order', 'sku'], how='left', suffixes=('', '_relief2'))

        # Calculate days until relief score (0-100, normalized to 0-1)
        def calc_relief_score(row):
            import numpy as np
            days = row.get('days_until_relief', np.inf)
            if pd.isna(days) or np.isinf(days):
                return 1.0  # No PO = max priority
            elif days > 60:
                return 0.8  # Long wait = high priority
            elif days > 30:
                return 0.6  # Medium wait
            elif days > 7:
                return 0.4  # Short wait
            else:
                return 0.2  # Very short wait = low priority

        bo_data['days_until_relief_normalized'] = bo_data.apply(calc_relief_score, axis=1)
    else:
        # No relief data available - assume medium priority for all
        bo_data['days_until_relief_normalized'] = 0.5

    # ===== FACTOR 5: Customer Value (10% weight) - PLACEHOLDER =====
    # Data not available yet - assume medium priority for all
    bo_data['customer_value_normalized'] = 0.5

    # ===== FACTOR 6: Product Margin (10% weight) - PLACEHOLDER =====
    # Data not available yet - assume medium priority for all
    bo_data['product_margin_normalized'] = 0.5

    # ===== CALCULATE WEIGHTED PRIORITY SCORE =====
    # Enhanced formula with updated weights
    bo_data['priority_score'] = (
        (bo_data['age_normalized'] * 0.20) +  # Age: 20%
        (bo_data['qty_normalized'] * 0.15) +  # Quantity: 15%
        (bo_data['vendor_reliability_normalized'] * 0.20) +  # Vendor Reliability: 20%
        (bo_data['days_until_relief_normalized'] * 0.25) +  # Days Until Relief: 25%
        (bo_data['customer_value_normalized'] * 0.10) +  # Customer Value: 10%
        (bo_data['product_margin_normalized'] * 0.10)  # Product Margin: 10%
    ) * 100  # Scale to 0-100

    # Clean up temporary columns
    temp_cols = [
        'age_normalized', 'qty_normalized', 'vendor_reliability_normalized',
        'days_until_relief_normalized', 'customer_value_normalized', 'product_margin_normalized',
        'vendor_otif_pct', 'has_po_coverage', 'days_until_relief'
    ]
    bo_data = bo_data.drop(columns=[col for col in temp_cols if col in bo_data.columns], errors='ignore')

    return bo_data

# ===== ROOT CAUSE ANALYSIS =====

@st.cache_data(show_spinner=False)
def categorize_root_causes(backorder_data, backorder_relief_data=None, deliveries_data=None):
    """
    Categorize backorders by root cause (Week 3 Priority 4)

    Root Cause Categories:
    1. Insufficient PO Coverage - No open PO for SKU
    2. Vendor Delay - PO exists but vendor late vs expected delivery
    3. Demand Spike - Recent demand >50% above historical avg
    4. Poor Forecasting - SKU has recurring backorders
    5. Long Vendor Lead Time - Vendor lead time >60 days
    6. Safety Stock Too Low - Stockout despite PO coverage (demand variability)

    Args:
        backorder_data: Backorder dataframe
        backorder_relief_data: Relief data with PO and vendor information
        deliveries_data: Historical deliveries for demand spike detection

    Returns:
        backorder_data with 'root_cause' and 'recommended_action' columns
    """
    if backorder_data.empty:
        return backorder_data

    bo_data = backorder_data.copy()

    # Initialize columns
    bo_data['root_cause'] = 'Unknown'
    bo_data['recommended_action'] = 'Review manually'

    # If no relief data, default to insufficient PO coverage
    if backorder_relief_data is None or backorder_relief_data.empty:
        bo_data['root_cause'] = 'Insufficient PO Coverage'
        bo_data['recommended_action'] = 'Create PO immediately'
        return bo_data

    # Merge relief data to get PO coverage and vendor info
    relief_subset = backorder_relief_data[['sales_order', 'sku', 'has_po_coverage',
                                            'days_until_relief', 'vendor_avg_delay_days']].copy()
    bo_data = bo_data.merge(relief_subset, on=['sales_order', 'sku'], how='left', suffixes=('', '_relief'))

    # CATEGORY 1: Insufficient PO Coverage
    no_po_mask = (bo_data['has_po_coverage'].fillna(False) == False)
    bo_data.loc[no_po_mask, 'root_cause'] = 'Insufficient PO Coverage'
    bo_data.loc[no_po_mask, 'recommended_action'] = 'Create PO immediately'

    # CATEGORY 2: Vendor Delay (PO exists but delayed)
    # Days until relief > 60 days OR vendor has high avg delay
    vendor_delay_mask = (
        (bo_data['has_po_coverage'] == True) &
        ((bo_data['days_until_relief'] > 60) | (bo_data['vendor_avg_delay_days'] > 15))
    )
    bo_data.loc[vendor_delay_mask, 'root_cause'] = 'Vendor Delay'
    bo_data.loc[vendor_delay_mask, 'recommended_action'] = 'Escalate with vendor, consider backup supplier'

    # CATEGORY 3: Demand Spike
    # Would require deliveries data - for now, placeholder
    # In future: check if recent demand > 1.5x historical avg
    if deliveries_data is not None and not deliveries_data.empty:
        # Placeholder for demand spike detection
        # demand_spike_mask = calculate_demand_spike(bo_data, deliveries_data)
        # bo_data.loc[demand_spike_mask, 'root_cause'] = 'Demand Spike'
        # bo_data.loc[demand_spike_mask, 'recommended_action'] = 'Review forecast, increase safety stock'
        pass

    # CATEGORY 4: Poor Forecasting
    # Check if SKU has recurring backorders (appears multiple times in backorder_data)
    sku_counts = bo_data.groupby('sku').size()
    recurring_skus = sku_counts[sku_counts >= 3].index
    poor_forecast_mask = bo_data['sku'].isin(recurring_skus) & (bo_data['root_cause'] == 'Unknown')
    bo_data.loc[poor_forecast_mask, 'root_cause'] = 'Poor Forecasting'
    bo_data.loc[poor_forecast_mask, 'recommended_action'] = 'Adjust reorder point, review demand model'

    # CATEGORY 5: Long Vendor Lead Time
    # Days until relief > 60 days (but not vendor delay)
    long_lead_mask = (
        (bo_data['has_po_coverage'] == True) &
        (bo_data['days_until_relief'] > 60) &
        (bo_data['vendor_avg_delay_days'] <= 15) &
        (bo_data['root_cause'] == 'Unknown')
    )
    bo_data.loc[long_lead_mask, 'root_cause'] = 'Long Vendor Lead Time'
    bo_data.loc[long_lead_mask, 'recommended_action'] = 'Find faster supplier, increase order frequency'

    # CATEGORY 6: Safety Stock Too Low
    # Has PO coverage but still on backorder (catch-all for remaining cases with PO)
    safety_stock_mask = (
        (bo_data['has_po_coverage'] == True) &
        (bo_data['root_cause'] == 'Unknown')
    )
    bo_data.loc[safety_stock_mask, 'root_cause'] = 'Safety Stock Too Low'
    bo_data.loc[safety_stock_mask, 'recommended_action'] = 'Recalculate safety stock with higher service level'

    # Clean up temporary columns
    temp_cols = ['has_po_coverage', 'days_until_relief', 'vendor_avg_delay_days']
    bo_data = bo_data.drop(columns=[col for col in temp_cols if col in bo_data.columns], errors='ignore')

    return bo_data


# ===== DEMAND-BASED INSIGHTS (Week 4 Priority 5) =====

@st.cache_data(show_spinner=False)
def calculate_demand_based_insights(backorder_data, deliveries_data=None):
    """
    Calculate demand-based insights for backorders (Week 4 Priority 5)

    Metrics:
    - Days of Demand Backordered = Backorder Qty / Daily Demand
    - Lost Sales Risk = Days on Backorder × Daily Demand × Cancel Probability
    - Customer Impact Score = Total Demand + Number SKUs + Total Days on BO
    - SKU Criticality = Customers Affected + Order Frequency + Demand Trend

    Args:
        backorder_data: Backorder dataframe
        deliveries_data: Historical delivery data for demand calculation

    Returns:
        Enhanced backorder dataframe with demand-based metrics
    """
    if backorder_data.empty:
        return backorder_data

    bo_data = backorder_data.copy()

    # ===== CALCULATE DAILY DEMAND FROM HISTORICAL DELIVERIES =====
    if deliveries_data is not None and not deliveries_data.empty:
        # Process deliveries data (handles both unified and processed formats)
        deliveries_processed = process_deliveries_data(deliveries_data)

        if not deliveries_processed.empty:
            # Calculate daily demand over last 90 days per SKU
            deliveries_90d = deliveries_processed[
                deliveries_processed['ship_date'] >= (pd.Timestamp.now() - pd.Timedelta(days=90))
            ].copy()

            daily_demand = deliveries_90d.groupby('sku').agg({
                'units_issued': 'sum'
            }).reset_index()

            daily_demand['daily_demand'] = daily_demand['units_issued'] / 90
            daily_demand = daily_demand[['sku', 'daily_demand']]

            # Merge with backorder data
            bo_data = bo_data.merge(daily_demand, on='sku', how='left')
            bo_data['daily_demand'] = bo_data['daily_demand'].fillna(0)
        else:
            bo_data['daily_demand'] = 0
    else:
        # NO FAKE DATA - Cannot calculate demand-based metrics without real deliveries data
        bo_data['daily_demand'] = 0

    # ===== METRIC 1: Days of Demand Backordered =====
    # Vectorized calculation for performance
    bo_data['days_of_demand_backordered'] = np.where(
        bo_data['daily_demand'] > 0,
        bo_data['backorder_qty'] / bo_data['daily_demand'],
        0
    )

    # ===== METRIC 2: Lost Sales Risk =====
    # Vectorized cancel probability calculation for performance
    # 0-7 days: 5%, 8-14: 10%, 15-30: 20%, 31-60: 40%, 61+: 60%
    conditions = [
        bo_data['days_on_backorder'] <= 7,
        bo_data['days_on_backorder'] <= 14,
        bo_data['days_on_backorder'] <= 30,
        bo_data['days_on_backorder'] <= 60
    ]
    choices = [0.05, 0.10, 0.20, 0.40]
    bo_data['cancel_probability'] = np.select(conditions, choices, default=0.60)
    bo_data['lost_sales_risk'] = (
        bo_data['days_on_backorder'] *
        bo_data['daily_demand'] *
        bo_data['cancel_probability']
    )

    return bo_data


@st.cache_data(show_spinner=False)
def calculate_customer_impact_score(backorder_data, deliveries_data=None):
    """
    Calculate customer impact scores (Week 4 Priority 5)

    Customer Impact = (
        Total Demand (90 days) +
        Number SKUs on Backorder +
        Total Days on Backorder
    )

    Returns:
        DataFrame with customer impact scores
    """
    if backorder_data.empty:
        return pd.DataFrame()

    # Group by customer
    customer_impact = backorder_data.groupby('customer_name').agg({
        'sku': 'nunique',  # Number of unique SKUs on backorder
        'days_on_backorder': 'sum',  # Total days on backorder
        'backorder_qty': 'sum',  # Total backorder quantity
        'sales_order': 'count'  # Number of backorder lines
    }).reset_index()

    customer_impact.columns = ['customer_name', 'skus_on_backorder', 'total_days_on_backorder',
                                'total_backorder_qty', 'backorder_lines']

    # Add 90-day demand if deliveries data available
    if deliveries_data is not None and not deliveries_data.empty:
        # Process deliveries data (handles both unified and processed formats)
        deliveries_processed = process_deliveries_data(deliveries_data)

        if not deliveries_processed.empty and 'customer_name' in deliveries_processed.columns:
            deliveries_90d = deliveries_processed[
                deliveries_processed['ship_date'] >= (pd.Timestamp.now() - pd.Timedelta(days=90))
            ].copy()

            customer_demand = deliveries_90d.groupby('customer_name').agg({
                'units_issued': 'sum'
            }).reset_index()
            customer_demand.columns = ['customer_name', 'total_demand_90d']

            customer_impact = customer_impact.merge(customer_demand, on='customer_name', how='left')
            customer_impact['total_demand_90d'] = customer_impact['total_demand_90d'].fillna(0)
        else:
            customer_impact['total_demand_90d'] = 0
    else:
        # NO FAKE DATA - Cannot calculate 90d demand without real deliveries data
        customer_impact['total_demand_90d'] = 0

    # Calculate Customer Impact Score (normalized components)
    max_demand = customer_impact['total_demand_90d'].max() if customer_impact['total_demand_90d'].max() > 0 else 1
    max_skus = customer_impact['skus_on_backorder'].max() if customer_impact['skus_on_backorder'].max() > 0 else 1
    max_days = customer_impact['total_days_on_backorder'].max() if customer_impact['total_days_on_backorder'].max() > 0 else 1

    customer_impact['customer_impact_score'] = (
        (customer_impact['total_demand_90d'] / max_demand * 40) +
        (customer_impact['skus_on_backorder'] / max_skus * 30) +
        (customer_impact['total_days_on_backorder'] / max_days * 30)
    )

    # Sort by impact score
    customer_impact = customer_impact.sort_values('customer_impact_score', ascending=False)

    return customer_impact


@st.cache_data(show_spinner=False)
def calculate_sku_criticality(backorder_data, deliveries_data=None):
    """
    Calculate SKU criticality scores (Week 4 Priority 5)

    SKU Criticality = (
        Number Customers Affected +
        Order Frequency (orders/month) +
        Demand Trend Coefficient
    )

    Returns:
        DataFrame with SKU criticality scores
    """
    if backorder_data.empty:
        return pd.DataFrame()

    # Group by SKU
    sku_criticality = backorder_data.groupby('sku').agg({
        'customer_name': 'nunique',  # Number of customers affected
        'sales_order': 'count',  # Number of backorder orders
        'backorder_qty': 'sum',  # Total backorder quantity
        'days_on_backorder': 'mean'  # Average days on backorder
    }).reset_index()

    sku_criticality.columns = ['sku', 'customers_affected', 'backorder_orders',
                                'total_backorder_qty', 'avg_days_on_backorder']

    # Calculate order frequency and demand trend from deliveries data if available
    if deliveries_data is not None and not deliveries_data.empty:
        # Process deliveries data (handles both unified and processed formats)
        deliveries_processed = process_deliveries_data(deliveries_data)

        if not deliveries_processed.empty:
            # Calculate order frequency from historical deliveries (last 90 days)
            deliveries_90d = deliveries_processed[
                deliveries_processed['ship_date'] >= (pd.Timestamp.now() - pd.Timedelta(days=90))
            ].copy()

            sku_frequency = deliveries_90d.groupby('sku').agg({
                'ship_date': 'nunique'  # Number of unique delivery days
            }).reset_index()
            sku_frequency.columns = ['sku', 'order_frequency']
            sku_frequency['order_frequency'] = sku_frequency['order_frequency'] / 3  # Convert to orders per month

            sku_criticality = sku_criticality.merge(sku_frequency, on='sku', how='left')
            sku_criticality['order_frequency'] = sku_criticality['order_frequency'].fillna(0)

            # Calculate demand trend (growth rate over 90 days)
            # Split into first 45 days vs last 45 days
            mid_date = pd.Timestamp.now() - pd.Timedelta(days=45)
            deliveries_90d['period'] = deliveries_90d['ship_date'].apply(
                lambda x: 'recent' if x >= mid_date else 'earlier'
            )

            trend_data = deliveries_90d.groupby(['sku', 'period']).agg({
                'units_issued': 'sum'
            }).reset_index().pivot(index='sku', columns='period', values='units_issued').reset_index()

            # Calculate trend coefficient (recent demand / earlier demand)
            trend_data['demand_trend'] = trend_data.apply(
                lambda row: row['recent'] / row['earlier'] if 'earlier' in trend_data.columns and row.get('earlier', 0) > 0 else 1.0,
                axis=1
            )

            sku_criticality = sku_criticality.merge(trend_data[['sku', 'demand_trend']], on='sku', how='left')
            sku_criticality['demand_trend'] = sku_criticality['demand_trend'].fillna(1.0)
        else:
            sku_criticality['order_frequency'] = 0
            sku_criticality['demand_trend'] = 1.0
    else:
        # NO FAKE DATA - Cannot calculate order frequency and demand trend without real deliveries data
        # Criticality score will only be based on customers affected
        sku_criticality['order_frequency'] = 0
        sku_criticality['demand_trend'] = 0

    # Calculate SKU Criticality Score (normalized components)
    max_customers = sku_criticality['customers_affected'].max() if sku_criticality['customers_affected'].max() > 0 else 1
    max_frequency = sku_criticality['order_frequency'].max() if sku_criticality['order_frequency'].max() > 0 else 1

    # If no real data available, weight customers_affected at 100%
    if deliveries_data is None or deliveries_data.empty:
        sku_criticality['sku_criticality_score'] = (
            sku_criticality['customers_affected'] / max_customers * 100
        )
    else:
        sku_criticality['sku_criticality_score'] = (
            (sku_criticality['customers_affected'] / max_customers * 50) +
            (sku_criticality['order_frequency'] / max_frequency * 30) +
            (sku_criticality['demand_trend'] * 20)
        )

    # Sort by criticality score
    sku_criticality = sku_criticality.sort_values('sku_criticality_score', ascending=False)

    return sku_criticality


# ===== ALTERNATE CODE OPPORTUNITIES =====

def render_alternate_code_opportunities(backorder_data, inventory_data):
    """Alert for backorders on old codes where inventory exists on current code"""
    if backorder_data.empty or inventory_data.empty:
        return

    st.subheader("🔄 Alternate Code Fulfillment Opportunities")

    # Load alternate codes mapping
    alt_codes_mapping = load_alternate_codes_mapping()

    if not alt_codes_mapping['all_codes_by_family']:
        st.info("No alternate codes mapping available")
        return

    # Normalize codes
    backorder_with_current = backorder_data.copy()
    backorder_with_current['current_code'] = backorder_with_current['sku'].apply(get_current_code)
    backorder_with_current['is_old'] = backorder_with_current['sku'].apply(is_old_code)

    inventory_with_current = inventory_data.copy()
    inventory_with_current['current_code'] = inventory_with_current['sku'].apply(get_current_code)

    # Find old code backorders
    old_code_backorders = backorder_with_current[backorder_with_current['is_old'] == True]

    # Vectorized approach: aggregate inventory by SKU, then merge with backorders
    inventory_agg = inventory_with_current.groupby('sku').agg({
        'on_hand_qty': 'sum'
    }).reset_index()
    inventory_agg.columns = ['current_code', 'available_qty']

    # Merge backorders with inventory availability
    opps_merged = old_code_backorders.merge(
        inventory_agg,
        left_on='current_code',
        right_on='current_code',
        how='inner'
    )

    # Filter to only opportunities with available inventory
    opps_merged = opps_merged[opps_merged['available_qty'] > 0]

    # Calculate fulfillment quantities and priority
    opps_merged['can_fulfill'] = opps_merged.apply(
        lambda row: min(row['backorder_qty'], row['available_qty']), axis=1
    )
    opps_merged['priority'] = opps_merged['days_on_backorder'].apply(
        lambda days: 'High' if days >= 30 else 'Medium'
    )

    # Select and rename columns for final opportunities dataframe
    opportunities = []
    if not opps_merged.empty:
        opportunities = opps_merged[['sku', 'current_code', 'backorder_qty', 'available_qty',
                                     'can_fulfill', 'customer_name', 'sales_order',
                                     'days_on_backorder', 'priority']].rename(
            columns={
                'sku': 'old_code',
                'customer_name': 'customer',
                'sales_order': 'order',
                'days_on_backorder': 'days_on_bo'
            }
        ).to_dict('records')

    if opportunities:
        opps_df = pd.DataFrame(opportunities)
        total_opps = len(opps_df)
        total_fulfillable = opps_df['can_fulfill'].sum()
        high_priority = len(opps_df[opps_df['priority'] == 'High'])

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Fulfillment Opportunities",
                f"{total_opps:,}",
                delta="⚠️",
                help="Backorders on old codes that can be fulfilled with current code inventory"
            )

        with col2:
            st.metric(
                "Units Can Fulfill",
                f"{int(total_fulfillable):,}",
                help="Total units that can be fulfilled by switching to current code"
            )

        with col3:
            st.metric(
                "High Priority (30+ days)",
                f"{high_priority:,}",
                delta="❌" if high_priority > 0 else None,
                help="Critical backorders aged 30+ days"
            )

        with st.expander("⚠️ View Fulfillment Opportunities", expanded=True):
            st.caption("**Action:** Update order material code from old to current code to fulfill with available inventory")

            display_df = opps_df.sort_values('days_on_bo', ascending=False).copy()

            display_table = pd.DataFrame({
                'Priority': display_df['priority'],
                'Old Code (BO)': display_df['old_code'],
                'Current Code (Inv)': display_df['current_code'],
                'BO Qty': display_df['backorder_qty'].astype(int),
                'Available': display_df['available_qty'].astype(int),
                'Can Fulfill': display_df['can_fulfill'].astype(int),
                'Days on BO': display_df['days_on_bo'].astype(int),
                'Customer': display_df['customer'],
                'Order': display_df['order']
            })

            st.dataframe(display_table, hide_index=True, use_container_width=True)

            st.caption("**Business Rule:** Prioritize using old code inventory first before new code inventory")

    else:
        st.success("✅ No old code backorder opportunities - all backorders are on current codes or no inventory available")


# ===== TAB-SPECIFIC RENDER FUNCTIONS =====

def render_relief_timeline_tab(backorder_relief_data, relief_metrics):
    """Render Relief Timeline & PO Tracking tab content"""
    import plotly.express as px
    import plotly.graph_objects as go
    from backorder_relief_analysis import get_critical_gaps, get_relief_timeline_data

    st.subheader("PO Relief Timeline & Vendor Tracking")

    if backorder_relief_data.empty:
        st.info("No backorder relief data available")
        return

    # Top-level relief metrics
    st.markdown("### Relief Overview")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        render_metric_card(
            label="This Week",
            value=f"{relief_metrics.get('relief_this_week', 0):,}",
            help_text="Backorders expected to be relieved within 7 days"
        )

    with col2:
        render_metric_card(
            label="This Month",
            value=f"{relief_metrics.get('relief_this_month', 0):,}",
            help_text="Backorders expected to be relieved within 30 days"
        )

    with col3:
        render_metric_card(
            label="High Confidence",
            value=f"{relief_metrics.get('high_confidence_count', 0):,}",
            help_text="Backorders with reliable vendors (OTIF ≥ 90%)"
        )

    with col4:
        render_metric_card(
            label="No PO Coverage",
            value=f"{relief_metrics.get('no_po_count', 0):,}",
            help_text="Backorders without matching purchase orders"
        )

    st.divider()

    # Relief Bucket Distribution
    st.markdown("### Relief Timeline Distribution")

    bucket_counts = backorder_relief_data['relief_bucket'].value_counts()
    bucket_order = ['Overdue', 'This Week', 'This Month', 'Next Month', '60+ Days', 'No PO']
    bucket_counts = bucket_counts.reindex(bucket_order, fill_value=0)

    # Create bar chart for relief buckets
    fig_buckets = go.Figure()
    colors = ['#dc3545', '#28a745', '#17a2b8', '#ffc107', '#6c757d', '#f8f9fa']

    fig_buckets.add_trace(go.Bar(
        x=bucket_counts.index,
        y=bucket_counts.values,
        marker_color=colors,
        text=bucket_counts.values,
        textposition='auto',
    ))

    fig_buckets.update_layout(
        title="Backorders by Expected Relief Timeline",
        xaxis_title="Relief Timeline",
        yaxis_title="Number of Backorders",
        height=350,
        showlegend=False
    )

    st.plotly_chart(fig_buckets, use_container_width=True)

    st.divider()

    # Relief Confidence Distribution
    st.markdown("### Relief Confidence Analysis")

    col1, col2 = st.columns(2)

    with col1:
        # Confidence pie chart
        confidence_counts = backorder_relief_data['relief_confidence'].value_counts()
        fig_confidence = px.pie(
            values=confidence_counts.values,
            names=confidence_counts.index,
            title="Relief Confidence Breakdown",
            color=confidence_counts.index,
            color_discrete_map={
                'High': '#28a745',
                'Medium': '#ffc107',
                'Low': '#dc3545',
                'No PO': '#6c757d'
            }
        )
        fig_confidence.update_layout(height=350)
        st.plotly_chart(fig_confidence, use_container_width=True)

    with col2:
        # Vendor OTIF distribution for backorders with PO coverage
        with_po = backorder_relief_data[backorder_relief_data['has_po_coverage'] == True]
        if not with_po.empty:
            fig_otif = px.histogram(
                with_po,
                x='vendor_otif_pct',
                nbins=20,
                title="Vendor OTIF Distribution (Backorders with PO)",
                labels={'vendor_otif_pct': 'Vendor OTIF %', 'count': 'Number of Backorders'}
            )
            fig_otif.update_layout(height=350)
            st.plotly_chart(fig_otif, use_container_width=True)
        else:
            st.info("No backorders with PO coverage")

    st.divider()

    # Critical Gaps - Backorders without PO or with unreliable vendors
    st.markdown("### 🚨 Critical Gaps - Immediate Action Required")

    critical_gaps = get_critical_gaps(backorder_relief_data, top_n=20)

    if not critical_gaps.empty:
        st.caption(f"Showing top {len(critical_gaps)} critical backorders requiring procurement attention")

        display_cols = {
            'sales_order': 'Sales Order',
            'sku': 'SKU',
            'customer_name': 'Customer',
            'backorder_qty': 'BO Qty',
            'days_on_backorder': 'Days Old',
            'has_po_coverage': 'Has PO',
            'vendor_name': 'Vendor',
            'vendor_otif_pct': 'Vendor OTIF %',
            'relief_confidence': 'Confidence',
            'days_until_relief': 'Days to Relief'
        }

        # Select and format columns
        display_df = critical_gaps[[col for col in display_cols.keys() if col in critical_gaps.columns]].copy()
        display_df.columns = [display_cols[col] for col in display_df.columns]

        # Format numeric columns
        if 'Vendor OTIF %' in display_df.columns:
            display_df['Vendor OTIF %'] = display_df['Vendor OTIF %'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")

        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No critical gaps - all backorders have reliable PO coverage")

    st.divider()

    # Relief Timeline - Gantt-style view
    st.markdown("### 📅 Expected Relief Timeline (Next 60 Days)")

    timeline_data = get_relief_timeline_data(backorder_relief_data)

    if not timeline_data.empty:
        # Filter to next 60 days only
        timeline_60 = timeline_data[
            (timeline_data['days_until_relief'] >= 0) &
            (timeline_data['days_until_relief'] <= 60)
        ].head(50)  # Limit to top 50 for readability

        if not timeline_60.empty:
            st.caption(f"Showing next {len(timeline_60)} backorders expected to be relieved in the next 60 days")

            # Create Gantt-style chart
            fig_gantt = px.scatter(
                timeline_60,
                x='vendor_adjusted_delivery_date',
                y='sku',
                size='backorder_qty',
                color='relief_confidence',
                hover_data=['sales_order', 'customer_name', 'vendor_name', 'days_until_relief'],
                title="Expected Relief Dates by SKU",
                color_discrete_map={
                    'High': '#28a745',
                    'Medium': '#ffc107',
                    'Low': '#dc3545'
                }
            )

            fig_gantt.update_layout(
                height=max(400, len(timeline_60) * 15),
                yaxis={'categoryorder': 'total ascending'}
            )

            st.plotly_chart(fig_gantt, use_container_width=True)

            # Detailed table
            st.markdown("#### Detailed Relief Schedule")

            display_timeline_cols = {
                'vendor_adjusted_delivery_date': 'Expected Relief Date',
                'days_until_relief': 'Days Until Relief',
                'sku': 'SKU',
                'sales_order': 'Sales Order',
                'customer_name': 'Customer',
                'backorder_qty': 'BO Qty',
                'vendor_name': 'Vendor',
                'relieving_po_number': 'PO Number',
                'relief_confidence': 'Confidence'
            }

            timeline_display = timeline_60[[col for col in display_timeline_cols.keys() if col in timeline_60.columns]].copy()
            timeline_display.columns = [display_timeline_cols[col] for col in timeline_display.columns]

            # Format date column
            if 'Expected Relief Date' in timeline_display.columns:
                timeline_display['Expected Relief Date'] = pd.to_datetime(timeline_display['Expected Relief Date']).dt.strftime('%Y-%m-%d')

            st.dataframe(timeline_display, use_container_width=True, hide_index=True)
        else:
            st.info("No backorders expected to be relieved in the next 60 days")
    else:
        st.info("No relief timeline data available (no backorders with PO coverage)")


def render_overview_analysis_tab(filtered_data):
    """Render Overview & Analysis tab content"""
    st.subheader("Backorder Analysis Overview")

    # Visualizations
    col1, col2, col3 = st.columns(3)

    with col1:
        aging_chart = render_aging_distribution_chart(filtered_data)
        if aging_chart:
            render_chart(aging_chart, height=350)

    with col2:
        customer_chart = render_top_customers_chart(filtered_data)
        if customer_chart:
            render_chart(customer_chart, height=350)

    with col3:
        category_chart = render_category_breakdown_chart(filtered_data)
        if category_chart:
            render_chart(category_chart, height=350)

    # Root Cause Analysis Section (Week 3 Priority 4)
    st.divider()

    with st.expander("🔍 Root Cause Analysis", expanded=True):
        st.caption("Categorize backorders by root cause to identify systemic issues and prioritize actions")

        if 'root_cause' not in filtered_data.columns:
            st.info("Root cause data not available - ensure backorder relief analysis is loaded")
        else:
            # Root Cause Distribution
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Root Cause Distribution")
                root_cause_counts = filtered_data['root_cause'].value_counts()

                # Color mapping for root causes
                color_map = {
                    'Insufficient PO Coverage': '#dc3545',  # Red
                    'Vendor Delay': '#fd7e14',  # Orange
                    'Demand Spike': '#ffc107',  # Yellow
                    'Poor Forecasting': '#17a2b8',  # Cyan
                    'Long Vendor Lead Time': '#6c757d',  # Gray
                    'Safety Stock Too Low': '#20c997',  # Teal
                    'Unknown': '#f8f9fa'  # Light gray
                }

                colors_list = [color_map.get(cause, '#6c757d') for cause in root_cause_counts.index]

                fig_pie = go.Figure(data=[go.Pie(
                    labels=root_cause_counts.index,
                    values=root_cause_counts.values,
                    marker=dict(colors=colors_list),
                    textinfo='label+percent',
                    hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percent: %{percent}<extra></extra>'
                )])

                fig_pie.update_layout(
                    title="Backorders by Root Cause",
                    height=400,
                    showlegend=True
                )

                st.plotly_chart(fig_pie, use_container_width=True)

            with col2:
                st.markdown("### Top SKUs by Root Cause")

                # Get most common root cause
                if not root_cause_counts.empty:
                    top_cause = root_cause_counts.index[0]
                    top_cause_data = filtered_data[filtered_data['root_cause'] == top_cause]

                    # Get top 10 SKUs for this root cause
                    top_skus = top_cause_data.groupby('sku').agg({
                        'backorder_qty': 'sum',
                        'sales_order': 'count',
                        'days_on_backorder': 'mean'
                    }).reset_index().sort_values('backorder_qty', ascending=False).head(10)

                    top_skus.columns = ['SKU', 'Total Qty', 'Orders', 'Avg Days']
                    top_skus['Avg Days'] = top_skus['Avg Days'].round(1)

                    st.markdown(f"**Root Cause: {top_cause}**")
                    st.dataframe(top_skus, use_container_width=True, hide_index=True)

            # Root Cause Recommendations
            st.divider()
            st.markdown("### Recommended Actions by Root Cause")

            col1, col2, col3 = st.columns(3)

            with col1:
                insufficient_po = len(filtered_data[filtered_data['root_cause'] == 'Insufficient PO Coverage'])
                st.metric("Insufficient PO Coverage", f"{insufficient_po:,}",
                         help="Create PO immediately for these backorders")

            with col2:
                vendor_delay = len(filtered_data[filtered_data['root_cause'] == 'Vendor Delay'])
                st.metric("Vendor Delay", f"{vendor_delay:,}",
                         help="Escalate with vendor, consider backup supplier")

            with col3:
                poor_forecast = len(filtered_data[filtered_data['root_cause'] == 'Poor Forecasting'])
                st.metric("Poor Forecasting", f"{poor_forecast:,}",
                         help="Adjust reorder point, review demand model")

    # Customer Impact Analysis Section (Week 4 Priority 5)
    st.divider()

    with st.expander("👥 Customer Impact Analysis", expanded=False):
        st.caption("Identify customers most affected by backorders and prioritize customer service actions")

        # Get customer impact data (passed from main render function)
        if 'customer_impact_data' in st.session_state and not st.session_state.customer_impact_data.empty:
            customer_impact = st.session_state.customer_impact_data

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Top 10 Most Impacted Customers")

                # Display top 10 customers
                top_customers = customer_impact.head(10)

                display_table = pd.DataFrame({
                    'Customer': top_customers['customer_name'],
                    'Impact Score': top_customers['customer_impact_score'].round(1),
                    'SKUs on BO': top_customers['skus_on_backorder'].astype(int),
                    'Total Days': top_customers['total_days_on_backorder'].astype(int),
                    'BO Lines': top_customers['backorder_lines'].astype(int),
                    '90d Demand': top_customers['total_demand_90d'].astype(int)
                })

                st.dataframe(display_table, use_container_width=True, hide_index=True)

            with col2:
                st.markdown("### Customer Impact Metrics")

                # Calculate summary metrics
                total_customers_impacted = len(customer_impact)
                high_impact_customers = len(customer_impact[customer_impact['customer_impact_score'] >= 70])
                avg_skus_per_customer = customer_impact['skus_on_backorder'].mean()

                col_a, col_b = st.columns(2)

                with col_a:
                    st.metric(
                        "Total Customers Impacted",
                        f"{total_customers_impacted:,}",
                        help="Number of unique customers with backorders"
                    )
                    st.metric(
                        "Avg SKUs per Customer",
                        f"{avg_skus_per_customer:.1f}",
                        help="Average number of different SKUs on backorder per customer"
                    )

                with col_b:
                    st.metric(
                        "High Impact Customers",
                        f"{high_impact_customers:,}",
                        delta="⚠️" if high_impact_customers > 0 else None,
                        help="Customers with impact score >= 70 (require immediate attention)"
                    )
        else:
            st.info("Customer impact data not available - ensure calculations are running")

    # SKU Criticality Analysis Section (Week 4 Priority 5)
    st.divider()

    with st.expander("📦 SKU Criticality Analysis", expanded=False):
        st.caption("Identify most critical SKUs based on customer impact and order frequency")

        if 'sku_criticality_data' in st.session_state and not st.session_state.sku_criticality_data.empty:
            sku_criticality = st.session_state.sku_criticality_data

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Top 10 Most Critical SKUs")

                # Display top 10 SKUs
                top_skus = sku_criticality.head(10)

                display_table = pd.DataFrame({
                    'SKU': top_skus['sku'],
                    'Criticality Score': top_skus['sku_criticality_score'].round(1),
                    'Customers Affected': top_skus['customers_affected'].astype(int),
                    'BO Orders': top_skus['backorder_orders'].astype(int),
                    'Total BO Qty': top_skus['total_backorder_qty'].astype(int),
                    'Avg Days on BO': top_skus['avg_days_on_backorder'].round(1)
                })

                st.dataframe(display_table, use_container_width=True, hide_index=True)

            with col2:
                st.markdown("### SKU Criticality Metrics")

                # Calculate summary metrics
                total_critical_skus = len(sku_criticality)
                high_criticality_skus = len(sku_criticality[sku_criticality['sku_criticality_score'] >= 70])
                multi_customer_skus = len(sku_criticality[sku_criticality['customers_affected'] > 1])

                col_a, col_b = st.columns(2)

                with col_a:
                    st.metric(
                        "Total SKUs on Backorder",
                        f"{total_critical_skus:,}",
                        help="Number of unique SKUs currently on backorder"
                    )
                    st.metric(
                        "Multi-Customer SKUs",
                        f"{multi_customer_skus:,}",
                        delta="⚠️" if multi_customer_skus > 10 else None,
                        help="SKUs affecting multiple customers (high priority for procurement)"
                    )

                with col_b:
                    st.metric(
                        "High Criticality SKUs",
                        f"{high_criticality_skus:,}",
                        delta="❌" if high_criticality_skus > 0 else None,
                        help="SKUs with criticality score >= 70 (expedite procurement)"
                    )
        else:
            st.info("SKU criticality data not available - ensure calculations are running")

def render_critical_backorders_tab(filtered_data):
    """Render Critical Backorders tab content"""
    st.subheader("🚨 Critical Backorders (Highest Priority)")

    critical_backorders = filtered_data.nlargest(20, 'priority_score')

    if not critical_backorders.empty:
        display_cols = [
            'sales_order', 'sku', 'product_name', 'customer_name', 'backorder_qty',
            'days_on_backorder', 'category', 'priority_score', 'order_date'
        ]
        display_cols = [col for col in display_cols if col in critical_backorders.columns]

        render_data_table(
            critical_backorders[display_cols],
            title="Top 20 Priority Backorders",
            height=400
        )
    else:
        st.info("No critical backorders")

def render_all_backorders_tab(filtered_data):
    """Render All Backorders tab content"""
    st.subheader("📋 All Backorders (Filtered)")

    display_cols = [
        'sales_order', 'sku', 'product_name', 'customer_name', 'backorder_qty',
        'days_on_backorder', 'category', 'sales_org', 'order_type', 'priority_score', 'order_date'
    ]
    display_cols = [col for col in display_cols if col in filtered_data.columns]

    # Sort by priority score descending
    filtered_data_sorted = filtered_data.sort_values('priority_score', ascending=False)

    render_data_table(
        filtered_data_sorted[display_cols],
        title=f"All Backorders ({len(filtered_data):,} orders)",
        height=500
    )

def render_summaries_tab(filtered_data):
    """Render Summaries tab content"""
    st.subheader("📊 Backorder Summaries")

    # Summary by Customer
    st.markdown("#### By Customer")
    customer_summary = filtered_data.groupby('customer_name').agg({
        'backorder_qty': 'sum',
        'sales_order': 'count',
        'days_on_backorder': 'mean'
    }).reset_index().sort_values('backorder_qty', ascending=False)

    customer_summary.columns = ['Customer', 'Total Units', 'Order Count', 'Avg Age (days)']
    customer_summary['Avg Age (days)'] = customer_summary['Avg Age (days)'].round(1)

    st.dataframe(customer_summary, use_container_width=True, hide_index=True)

    st.divider()

    # Summary by SKU
    st.markdown("#### By SKU")
    sku_summary = filtered_data.groupby(['sku', 'product_name']).agg({
        'backorder_qty': 'sum',
        'sales_order': 'count',
        'days_on_backorder': 'mean'
    }).reset_index().sort_values('backorder_qty', ascending=False)

    sku_summary.columns = ['SKU', 'Product Name', 'Total Units', 'Order Count', 'Avg Age (days)']
    sku_summary['Avg Age (days)'] = sku_summary['Avg Age (days)'].round(1)

    st.dataframe(sku_summary, use_container_width=True, hide_index=True)

def render_fulfillment_opportunities_tab(filtered_data, inventory_data):
    """Render Fulfillment Opportunities tab content"""
    st.subheader("🔄 Alternate Code Fulfillment Opportunities")

    if inventory_data is None or inventory_data.empty:
        st.info("Inventory data not available for fulfillment opportunity analysis")
        return

    render_alternate_code_opportunities(filtered_data, inventory_data)

# ===== STOCKOUT RISK TAB =====

def render_stockout_risk_tab(stockout_risk_data):
    """Render stockout risk prediction tab

    Args:
        stockout_risk_data: DataFrame with stockout risk predictions
    """
    st.header("⚠️ At-Risk Stockout Prediction")
    st.caption("Proactive backorder prevention: identify SKUs likely to go on backorder BEFORE it happens")

    if stockout_risk_data.empty:
        st.info("No stock outout risk data available")
        return

    # Import helper functions
    from stockout_prediction import get_stockout_summary_metrics, get_critical_at_risk_items, get_reorder_recommendations

    # Calculate summary metrics
    metrics = get_stockout_summary_metrics(stockout_risk_data)

    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Critical Risk", f"{metrics.get('critical_count', 0)}",
                 help="SKUs with 0-7 days until stockout")
    with col2:
        st.metric("High Risk", f"{metrics.get('high_count', 0)}",
                 help="SKUs with 7-14 days until stockout")
    with col3:
        st.metric("Out of Stock", f"{metrics.get('out_of_stock_count', 0)}",
                 help="SKUs currently out of stock with demand")
    with col4:
        st.metric("No PO Coverage", f"{metrics.get('no_po_count', 0)}",
                 help="High-risk SKUs without purchase orders")

    st.divider()

    # Critical at-risk items table
    st.subheader("🔴 Critical At-Risk Items (Immediate Action Required)")
    critical_items = get_critical_at_risk_items(stockout_risk_data, top_n=20)

    if not critical_items.empty:
        display_cols = ['sku', 'on_hand_qty', 'daily_demand', 'days_until_stockout',
                       'risk_level', 'reorder_point', 'safety_stock', 'has_po_coverage']
        st.dataframe(critical_items[display_cols], use_container_width=True, height=400)
    else:
        st.success("No critical at-risk items found!")

    st.divider()

    # Reorder recommendations
    st.subheader("📋 Reorder Recommendations")
    reorder_recs = get_reorder_recommendations(stockout_risk_data, risk_threshold='Moderate')

    if not reorder_recs.empty:
        display_cols = ['sku', 'risk_level', 'days_until_stockout', 'on_hand_qty',
                       'reorder_point', 'recommended_order_qty', 'has_po_coverage']
        st.dataframe(reorder_recs[display_cols], use_container_width=True, height=400)

        st.caption(f"Showing {len(reorder_recs)} SKUs that should be reordered (risk level: Moderate or higher)")
    else:
        st.success("No reorder recommendations at this time!")

# ===== MAIN RENDER FUNCTION =====

def render_backorder_page(backorder_data, backorder_relief_data=None, stockout_risk_data=None, inventory_data=None, deliveries_data=None):
    """Main render function for backorder page with tabbed interface

    Args:
        backorder_data: Base backorder dataframe
        backorder_relief_data: Enhanced backorder data with PO relief information
        stockout_risk_data: Stockout risk prediction data
        inventory_data: Inventory data for alternate code fulfillment analysis
        deliveries_data: Historical deliveries data for demand-based calculations
    """

    render_page_header(
        "Backorder Management",
        icon="⚠️",
        subtitle="Track and analyze open backorders with aging analysis, priority ranking, and PO relief tracking"
    )

    # Render sidebar settings
    settings = render_backorder_settings_sidebar()

    if backorder_data.empty:
        st.success("✅ No backorders! All orders are fulfilled.")
        return

    # Calculate enhanced priority scores (with vendor reliability and relief timeline factors)
    backorder_data = calculate_priority_score(backorder_data, backorder_relief_data)

    # Categorize root causes (Week 3 Priority 4)
    backorder_data = categorize_root_causes(backorder_data, backorder_relief_data)

    # Calculate demand-based insights (Week 4 Priority 5)
    backorder_data = calculate_demand_based_insights(backorder_data, deliveries_data=deliveries_data)

    # Calculate customer impact and SKU criticality (Week 4 Priority 5)
    customer_impact_data = calculate_customer_impact_score(backorder_data, deliveries_data=deliveries_data)
    sku_criticality_data = calculate_sku_criticality(backorder_data, deliveries_data=deliveries_data)

    # Store in session state for visualization access
    st.session_state.customer_impact_data = customer_impact_data
    st.session_state.sku_criticality_data = sku_criticality_data

    # Calculate metrics
    metrics = calculate_backorder_metrics(backorder_data)

    # Calculate relief metrics if available
    relief_metrics = {}
    if backorder_relief_data is not None and not backorder_relief_data.empty:
        from backorder_relief_analysis import get_relief_summary_metrics
        relief_metrics = get_relief_summary_metrics(backorder_relief_data)

    # Display KPIs (shown at top level, above tabs)
    kpi_data = {
        "Total Orders": {
            "value": f"{metrics['total_orders']:,}",
            "delta": None,
            "help": "**Business Logic:** Count of distinct sales orders with unfulfilled backorder quantity. Formula: COUNT(DISTINCT sales_order WHERE backorder_qty > 0)"
        },
        "Total Units": {
            "value": f"{metrics['total_units']:,}",
            "delta": None,
            "help": "**Business Logic:** Sum of all backorder quantities across all open orders. Represents total units awaiting fulfillment. Formula: SUM(backorder_qty)"
        },
        "Unique SKUs": {
            "value": f"{metrics['unique_skus']:,}",
            "delta": None,
            "help": "**Business Logic:** Count of distinct material numbers (SKUs) on backorder. Shows how many different products have unfulfilled demand. Formula: COUNT(DISTINCT sku WHERE backorder_qty > 0)"
        },
        "Unique Customers": {
            "value": f"{metrics['unique_customers']:,}",
            "delta": None,
            "help": "**Business Logic:** Count of distinct customers with open backorders. Indicates breadth of backorder impact. Formula: COUNT(DISTINCT customer_name WHERE backorder_qty > 0)"
        },
        "Avg Age (days)": {
            "value": f"{metrics['avg_age']:.1f}",
            "delta": "⚠️" if metrics['avg_age'] > 30 else None,
            "help": f"**Business Logic:** Average time backorders have been open. Days on Backorder = Today - Order Creation Date. Current average: {metrics['avg_age']:.1f} days. Formula: AVG(days_on_backorder) = AVG(TODAY - order_date)"
        },
        "Critical Orders": {
            "value": f"{metrics['critical_orders']:,}",
            "delta": "❌" if metrics['critical_orders'] > 0 else None,
            "help": f"**Business Logic:** Count of orders on backorder for more than 30 days (critical threshold). These require immediate attention. Formula: COUNT(WHERE days_on_backorder >= 30)"
        }
    }

    # Add demand-based metrics (Week 4 Priority 5)
    if 'days_on_backorder' in backorder_data.columns and 'customer_name' in backorder_data.columns:
        # Customer-Days Lost = sum of (1 customer × days on backorder for each backorder line)
        customer_days_lost = backorder_data['days_on_backorder'].sum()

        # Backorder as % of Monthly Demand (using daily demand × 30)
        if 'daily_demand' in backorder_data.columns and 'backorder_qty' in backorder_data.columns:
            monthly_demand = (backorder_data['daily_demand'] * 30).sum()
            total_backorder_qty = backorder_data['backorder_qty'].sum()
            backorder_pct_demand = (total_backorder_qty / monthly_demand * 100) if monthly_demand > 0 else 0
        else:
            backorder_pct_demand = 0

        # Customers with Multiple Backorders
        customer_counts = backorder_data['customer_name'].value_counts()
        customers_multiple_bo = len(customer_counts[customer_counts > 1])

        kpi_data["Customer-Days Lost"] = {
            "value": f"{customer_days_lost:,.0f}",
            "delta": "⚠️" if customer_days_lost > 500 else None,
            "help": f"**Business Logic:** Total impact measured in customer-days. Sum of days each backorder has been open. Represents cumulative customer wait time. Formula: SUM(days_on_backorder)"
        }
        kpi_data["BO % Monthly Demand"] = {
            "value": f"{backorder_pct_demand:.1f}%",
            "delta": "⚠️" if backorder_pct_demand > 10 else None,
            "help": f"**Business Logic:** Backorder quantity as percentage of estimated monthly demand. Shows severity relative to normal demand levels. Formula: (SUM(backorder_qty) / SUM(daily_demand × 30)) × 100"
        }
        kpi_data["Multiple BO Customers"] = {
            "value": f"{customers_multiple_bo:,}",
            "delta": "⚠️" if customers_multiple_bo > 5 else None,
            "help": f"**Business Logic:** Count of customers with more than one backorder. Indicates breadth of customer dissatisfaction. Formula: COUNT(DISTINCT customer_name WHERE backorder_count > 1)"
        }

    # Add relief metrics if available
    if relief_metrics:
        kpi_data["PO Coverage"] = {
            "value": f"{relief_metrics['po_coverage_pct']:.1f}%",
            "delta": "✅" if relief_metrics['po_coverage_pct'] >= 80 else "⚠️",
            "help": f"**Business Logic:** Percentage of backorders with matching vendor POs. Indicates supply chain responsiveness. {relief_metrics['po_coverage_count']} of {relief_metrics['total_backorders']} backorders have PO coverage. Formula: (COUNT(backorders WITH open PO) / COUNT(total backorders)) * 100"
        }
        kpi_data["Avg Days to Relief"] = {
            "value": f"{relief_metrics['avg_days_until_relief']:.1f}",
            "delta": "⚠️" if relief_metrics['avg_days_until_relief'] > 30 else None,
            "help": f"**Business Logic:** Average days until backorders are expected to be fulfilled based on vendor-adjusted PO delivery dates. Only includes backorders with PO coverage. Formula: AVG(vendor_adjusted_delivery_date - TODAY) WHERE has_po_coverage = TRUE"
        }
        kpi_data["High-Risk"] = {
            "value": f"{relief_metrics['high_risk_count']:,}",
            "delta": "❌" if relief_metrics['high_risk_count'] > 0 else None,
            "help": f"**Business Logic:** Backorders with no PO coverage OR unreliable vendor (OTIF < 75%). These require immediate procurement action. Formula: COUNT(WHERE has_po_coverage = FALSE OR vendor_otif_pct < 75)"
        }

    render_kpi_row(kpi_data)

    st.divider()

    # Render filters
    filters_config = get_backorder_filters(backorder_data)
    filter_values = render_filter_section(filters_config)

    # Apply filters
    filtered_data = apply_backorder_filters(backorder_data, filter_values, settings)

    if filtered_data.empty:
        st.info("No backorders match the selected filters")
        return

    st.caption(f"Showing {len(filtered_data):,} of {len(backorder_data):,} backorders")

    # Export button
    export_data = prepare_backorder_export_data(filtered_data, settings['export_section'], settings)
    if not export_data.empty:
        excel_file = create_backorder_excel_export(export_data, settings['export_section'])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Backorders_{settings['export_section'].replace(' ', '_')}_{timestamp}.xlsx"

        st.sidebar.download_button(
            label="📥 Download Excel",
            data=excel_file,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.sidebar.caption(f"📊 {len(export_data):,} rows ready to export")

    st.divider()

    # Tabbed Interface
    tabs_list = [
        "📊 Overview & Analysis",
        "🚨 Critical Backorders",
        "📋 All Backorders",
        "📈 Summaries",
        "🔄 Fulfillment Opportunities"
    ]

    # Add Relief Timeline tab if relief data is available
    has_relief_tab = backorder_relief_data is not None and not backorder_relief_data.empty
    has_stockout_tab = stockout_risk_data is not None and not stockout_risk_data.empty

    if has_relief_tab:
        tabs_list.insert(1, "📅 Relief Timeline & PO Tracking")
    if has_stockout_tab:
        # Insert stockout tab after relief tab (if exists) or after overview
        insert_pos = 2 if has_relief_tab else 1
        tabs_list.insert(insert_pos, "⚠️ At-Risk Stockout Prediction")

    # Create tabs based on how many we have
    if has_relief_tab and has_stockout_tab:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tabs_list)
    elif has_relief_tab or has_stockout_tab:
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tabs_list)
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs(tabs_list)

    # Render tabs dynamically based on available data
    tab_idx = 0

    with tab1:
        render_overview_analysis_tab(filtered_data)
        tab_idx += 1

    # Relief Timeline tab (conditional)
    if has_relief_tab:
        with eval(f"tab{tab_idx + 1}"):
            # Apply same filters to relief data
            if 'sku' in filter_values and filter_values['sku']:
                filtered_relief_data = backorder_relief_data[backorder_relief_data['sku'].isin(filter_values['sku'])]
            else:
                filtered_relief_data = backorder_relief_data.copy()
            render_relief_timeline_tab(filtered_relief_data, relief_metrics)
        tab_idx += 1

    # Stockout Risk tab (conditional)
    if has_stockout_tab:
        with eval(f"tab{tab_idx + 1}"):
            render_stockout_risk_tab(stockout_risk_data)
        tab_idx += 1

    # Remaining tabs (always present)
    with eval(f"tab{tab_idx + 1}"):
        render_critical_backorders_tab(filtered_data)
        tab_idx += 1

    with eval(f"tab{tab_idx + 1}"):
        render_all_backorders_tab(filtered_data)
        tab_idx += 1

    with eval(f"tab{tab_idx + 1}"):
        render_summaries_tab(filtered_data)
        tab_idx += 1

    with eval(f"tab{tab_idx + 1}"):
        render_fulfillment_opportunities_tab(filtered_data, inventory_data)
