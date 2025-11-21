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
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sys
import os
from io import BytesIO
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import render_page_header, render_kpi_row, render_chart, render_data_table, render_filter_section, render_info_box
from business_rules import (
    BACKORDER_RULES,
    load_alternate_codes_mapping, get_alternate_codes, get_current_code, is_old_code
)

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
    """Define available filters for backorder data"""
    if backorder_data.empty:
        return {}

    return {
        "Category": {
            "type": "multiselect",
            "options": sorted(backorder_data['category'].dropna().unique().tolist()),
            "default": []
        },
        "Customer": {
            "type": "multiselect",
            "options": sorted(backorder_data['customer_name'].dropna().unique().tolist()),
            "default": []
        },
        "Sales Org": {
            "type": "multiselect",
            "options": sorted(backorder_data['sales_org'].dropna().unique().tolist()),
            "default": []
        },
        "Age Range": {
            "type": "slider",
            "min": int(backorder_data['days_on_backorder'].min()),
            "max": int(backorder_data['days_on_backorder'].max()),
            "default": (int(backorder_data['days_on_backorder'].min()), int(backorder_data['days_on_backorder'].max()))
        }
    }

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

def calculate_priority_score(backorder_data):
    """Calculate priority score for backorders based on age, quantity, and customer"""
    if backorder_data.empty:
        return backorder_data

    # Normalize age (0-1 scale)
    max_age = backorder_data['days_on_backorder'].max()
    if max_age > 0:
        backorder_data['age_normalized'] = backorder_data['days_on_backorder'] / max_age
    else:
        backorder_data['age_normalized'] = 0

    # Normalize quantity (0-1 scale)
    max_qty = backorder_data['backorder_qty'].max()
    if max_qty > 0:
        backorder_data['qty_normalized'] = backorder_data['backorder_qty'] / max_qty
    else:
        backorder_data['qty_normalized'] = 0

    # Calculate weighted priority score
    age_weight = BACKORDER_RULES["priority_scoring"]["age_weight"]
    qty_weight = BACKORDER_RULES["priority_scoring"]["quantity_weight"]

    backorder_data['priority_score'] = (
        (backorder_data['age_normalized'] * age_weight) +
        (backorder_data['qty_normalized'] * qty_weight)
    ) * 100

    # Clean up temporary columns
    backorder_data = backorder_data.drop(columns=['age_normalized', 'qty_normalized'])

    return backorder_data

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

    opportunities = []

    for _, bo_row in old_code_backorders.iterrows():
        old_sku = bo_row['sku']
        current_sku = bo_row['current_code']
        backorder_qty = bo_row['backorder_qty']

        # Check if inventory exists on current code
        current_inventory = inventory_with_current[
            inventory_with_current['sku'] == current_sku
        ]

        if not current_inventory.empty:
            available_qty = current_inventory['on_hand_qty'].sum()

            if available_qty > 0:
                opportunities.append({
                    'old_code': old_sku,
                    'current_code': current_sku,
                    'backorder_qty': backorder_qty,
                    'available_qty': available_qty,
                    'can_fulfill': min(backorder_qty, available_qty),
                    'customer': bo_row.get('customer_name', 'Unknown'),
                    'order': bo_row.get('sales_order', 'Unknown'),
                    'days_on_bo': bo_row.get('days_on_backorder', 0),
                    'priority': 'High' if bo_row.get('days_on_backorder', 0) >= 30 else 'Medium'
                })

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


# ===== MAIN RENDER FUNCTION =====

def render_backorder_page(backorder_data, inventory_data=None):
    """Main render function for backorder page"""

    render_page_header(
        "⚠️ Backorder Management",
        "Track and analyze open backorders with aging analysis and priority ranking"
    )

    # Render sidebar settings
    settings = render_backorder_settings_sidebar()

    if backorder_data.empty:
        st.success("✅ No backorders! All orders are fulfilled.")
        return

    # Calculate priority scores
    backorder_data = calculate_priority_score(backorder_data)

    # Calculate metrics
    metrics = calculate_backorder_metrics(backorder_data)

    # Display KPIs
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

    # === ALTERNATE CODE OPPORTUNITIES (if inventory data available) ===
    if inventory_data is not None:
        render_alternate_code_opportunities(filtered_data, inventory_data)
        st.divider()

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

    # === VISUALIZATIONS ===
    st.subheader("📊 Backorder Analysis")

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

    st.divider()

    # === CRITICAL BACKORDERS ===
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

    st.divider()

    # === DETAILED BACKORDER TABLE ===
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

    st.divider()

    # === SUMMARY BY CUSTOMER ===
    with st.expander("📊 Summary by Customer"):
        customer_summary = filtered_data.groupby('customer_name').agg({
            'backorder_qty': 'sum',
            'sales_order': 'count',
            'days_on_backorder': 'mean'
        }).reset_index().sort_values('backorder_qty', ascending=False)

        customer_summary.columns = ['Customer', 'Total Units', 'Order Count', 'Avg Age (days)']
        customer_summary['Avg Age (days)'] = customer_summary['Avg Age (days)'].round(1)

        st.dataframe(customer_summary, use_container_width=True, hide_index=True)

    # === SUMMARY BY SKU ===
    with st.expander("📊 Summary by SKU"):
        sku_summary = filtered_data.groupby(['sku', 'product_name']).agg({
            'backorder_qty': 'sum',
            'sales_order': 'count',
            'days_on_backorder': 'mean'
        }).reset_index().sort_values('backorder_qty', ascending=False)

        sku_summary.columns = ['SKU', 'Product Name', 'Total Units', 'Order Count', 'Avg Age (days)']
        sku_summary['Avg Age (days)'] = sku_summary['Avg Age (days)'].round(1)

        st.dataframe(sku_summary, use_container_width=True, hide_index=True)
