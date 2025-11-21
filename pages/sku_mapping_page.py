"""
SKU Mapping & Alternate Codes Page
Displays material code relationships, supersessions, and code transitions
Helps identify inventory split across old/new codes and backorder opportunities
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui_components import (
    render_page_header, render_kpi_row, render_chart,
    render_data_table, render_filter_section, render_info_box
)
from business_rules import (
    load_alternate_codes_mapping, get_alternate_codes, get_current_code,
    is_old_code, has_alternate_codes, get_alternate_codes_summary,
    ALTERNATE_CODES_RULES
)

# ===== HELPER FUNCTIONS =====

def analyze_inventory_split(inventory_data, alt_codes_mapping):
    """
    Analyze inventory split across alternate codes

    Returns DataFrame with SKU families that have inventory on multiple codes
    """
    if inventory_data.empty:
        return pd.DataFrame()

    # Group inventory by current code (normalize all codes)
    inventory_with_current = inventory_data.copy()
    inventory_with_current['current_code'] = inventory_with_current['sku'].apply(get_current_code)
    inventory_with_current['is_old'] = inventory_with_current['sku'].apply(is_old_code)

    # Find SKU families with inventory on multiple codes
    split_inventory = []

    for current_code, family_codes in alt_codes_mapping['all_codes_by_family'].items():
        # Get inventory for all codes in this family
        family_inventory = inventory_with_current[
            inventory_with_current['sku'].isin(family_codes)
        ]

        if len(family_inventory) > 1:  # Inventory exists on multiple codes
            total_qty = family_inventory['on_hand_qty'].sum()
            total_value = family_inventory.get('stock_value_usd', pd.Series([0])).sum()

            # Build detail of which codes have inventory
            codes_with_inventory = []
            for _, row in family_inventory.iterrows():
                codes_with_inventory.append({
                    'code': row['sku'],
                    'is_old': row['is_old'],
                    'qty': row['on_hand_qty'],
                    'value': row.get('stock_value_usd', 0)
                })

            split_inventory.append({
                'current_code': current_code,
                'num_codes_with_inventory': len(family_inventory),
                'total_qty': total_qty,
                'total_value_usd': total_value,
                'codes_detail': codes_with_inventory,
                'all_codes': family_codes
            })

    return pd.DataFrame(split_inventory)


def analyze_backorder_opportunities(backorder_data, inventory_data, alt_codes_mapping):
    """
    Find backorders on old codes where inventory exists on current code

    Returns DataFrame with backorder opportunities
    """
    if backorder_data.empty or inventory_data.empty:
        return pd.DataFrame()

    opportunities = []

    # Normalize codes
    backorder_with_current = backorder_data.copy()
    backorder_with_current['current_code'] = backorder_with_current['sku'].apply(get_current_code)
    backorder_with_current['is_old'] = backorder_with_current['sku'].apply(is_old_code)

    inventory_with_current = inventory_data.copy()
    inventory_with_current['current_code'] = inventory_with_current['sku'].apply(get_current_code)

    # Find old code backorders
    old_code_backorders = backorder_with_current[backorder_with_current['is_old'] == True]

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
                    'old_code_backorder': old_sku,
                    'current_code': current_sku,
                    'backorder_qty': backorder_qty,
                    'available_qty_current_code': available_qty,
                    'can_fulfill_qty': min(backorder_qty, available_qty),
                    'customer': bo_row.get('customer_name', 'Unknown'),
                    'order_number': bo_row.get('sales_order', 'Unknown'),
                    'days_on_backorder': bo_row.get('days_on_backorder', 0),
                    'priority': 'High' if bo_row.get('days_on_backorder', 0) >= 30 else 'Medium'
                })

    return pd.DataFrame(opportunities)


def get_code_family_details(sku, alt_codes_mapping, inventory_data, backorder_data):
    """Get detailed information about a SKU code family"""
    current_code = get_current_code(sku)
    all_codes = get_alternate_codes(sku)

    details = {
        'current_code': current_code,
        'all_codes': all_codes,
        'num_codes': len(all_codes),
        'inventory_summary': [],
        'backorder_summary': []
    }

    # Get inventory for each code
    if not inventory_data.empty:
        for code in all_codes:
            inv = inventory_data[inventory_data['sku'] == code]
            if not inv.empty:
                details['inventory_summary'].append({
                    'code': code,
                    'qty': inv['on_hand_qty'].sum(),
                    'value': inv.get('stock_value_usd', pd.Series([0])).sum(),
                    'is_current': code == current_code
                })

    # Get backorders for each code
    if not backorder_data.empty:
        for code in all_codes:
            bo = backorder_data[backorder_data['sku'] == code]
            if not bo.empty:
                details['backorder_summary'].append({
                    'code': code,
                    'qty': bo['backorder_qty'].sum(),
                    'num_orders': len(bo),
                    'is_current': code == current_code
                })

    return details


# ===== MAIN RENDER FUNCTION =====

def render_sku_mapping_page(inventory_data, backorder_data):
    """Main SKU mapping page render function"""

    # Page header
    render_page_header(
        "SKU Mapping & Alternate Codes",
        icon="🔄",
        subtitle="Material code relationships, supersessions, and code transition tracking"
    )

    # Load alternate codes mapping
    alt_codes_mapping = load_alternate_codes_mapping()
    summary = get_alternate_codes_summary()

    # Check if alternate codes are loaded
    if summary['total_sku_families'] == 0:
        render_info_box(
            "No alternate codes mapping file found. Please ensure ALTERNATE_CODES.csv is in the project directory.",
            type="warning"
        )
        return

    # Display summary metrics
    st.subheader("📊 Alternate Codes Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "SKU Families",
            f"{summary['total_sku_families']:,}",
            help="Number of SKU families with alternate codes. Each family has 1 current code + 1 or more old codes."
        )

    with col2:
        st.metric(
            "Total Old Codes",
            f"{summary['total_old_codes']:,}",
            help="Total number of obsolete/superseded material codes"
        )

    with col3:
        st.metric(
            "Families with 2 Codes",
            f"{summary['families_with_2_codes']:,}",
            help="SKU families with exactly 2 codes (1 current + 1 old)"
        )

    with col4:
        st.metric(
            "Families with 3+ Codes",
            f"{summary['families_with_3_codes']:,}",
            help="SKU families with 3 or more codes (1 current + 2+ old)"
        )

    st.divider()

    # === INVENTORY SPLIT ANALYSIS ===
    st.subheader("📦 Inventory Split Across Codes")

    split_analysis = analyze_inventory_split(inventory_data, alt_codes_mapping)

    if not split_analysis.empty:
        total_split_value = split_analysis['total_value_usd'].sum()
        total_split_families = len(split_analysis)

        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "SKU Families with Split Inventory",
                f"{total_split_families:,}",
                help="Number of SKU families with inventory on multiple material codes"
            )
        with col2:
            st.metric(
                "Total Value of Split Inventory",
                f"${total_split_value:,.0f}",
                help="Total USD value of inventory split across alternate codes"
            )

        # Display top split inventory
        st.markdown("#### Top 20 SKU Families with Split Inventory")

        display_split = split_analysis.sort_values('total_value_usd', ascending=False).head(20).copy()

        # Format for display
        display_split['Codes Detail'] = display_split['codes_detail'].apply(
            lambda x: ', '.join([
                f"{c['code']}{'*' if c['is_old'] else ''} ({c['qty']} units)"
                for c in x
            ])
        )

        display_df = pd.DataFrame({
            'Current Code': display_split['current_code'],
            'Num Codes': display_split['num_codes_with_inventory'],
            'Total Qty': display_split['total_qty'],
            'Total Value (USD)': display_split['total_value_usd'].apply(lambda x: f"${x:,.0f}"),
            'Distribution': display_split['Codes Detail']
        })

        render_data_table(display_df, max_rows=20)
        st.caption("* indicates old/obsolete code")

    else:
        render_info_box(
            "No inventory split detected. All SKU families have inventory consolidated under one code.",
            type="success"
        )

    st.divider()

    # === BACKORDER OPPORTUNITIES ===
    st.subheader("⚠️ Backorder Fulfillment Opportunities")
    st.caption("Old code backorders that can be fulfilled with current code inventory")

    opportunities = analyze_backorder_opportunities(backorder_data, inventory_data, alt_codes_mapping)

    if not opportunities.empty:
        total_opportunities = len(opportunities)
        total_fulfillable_units = opportunities['can_fulfill_qty'].sum()
        high_priority = len(opportunities[opportunities['priority'] == 'High'])

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Total Opportunities",
                f"{total_opportunities:,}",
                help="Number of backorders on old codes that can be fulfilled with current code inventory"
            )

        with col2:
            st.metric(
                "Fulfillable Units",
                f"{int(total_fulfillable_units):,}",
                help="Total units that can be fulfilled by switching to current code"
            )

        with col3:
            st.metric(
                "High Priority (30+ days)",
                f"{high_priority:,}",
                delta="⚠️" if high_priority > 0 else None,
                help="Backorders aged 30+ days that can be fulfilled immediately"
            )

        # Display opportunities
        st.markdown("#### Backorder Fulfillment Recommendations")

        display_opps = opportunities.sort_values('days_on_backorder', ascending=False).copy()

        display_df = pd.DataFrame({
            'Priority': display_opps['priority'],
            'Old Code (Backorder)': display_opps['old_code_backorder'],
            'Current Code (Inventory)': display_opps['current_code'],
            'Backorder Qty': display_opps['backorder_qty'].astype(int),
            'Available Qty': display_opps['available_qty_current_code'].astype(int),
            'Can Fulfill': display_opps['can_fulfill_qty'].astype(int),
            'Days on BO': display_opps['days_on_backorder'].astype(int),
            'Customer': display_opps['customer'],
            'Order #': display_opps['order_number']
        })

        render_data_table(display_df, max_rows=50)

        # Action recommendations
        with st.expander("📋 Recommended Actions", expanded=True):
            st.markdown("""
            **Steps to fulfill these backorders:**

            1. **Update Order Material Code**: Change the material code on the sales order from old code to current code
            2. **Verify Inventory Availability**: Confirm current code inventory is not allocated to other orders
            3. **Process Fulfillment**: Release order for picking and shipping
            4. **Prioritize by Age**: Start with backorders aged 30+ days (High Priority)
            5. **Utilize Old Inventory First**: Per business rules, deplete old code inventory before using new code

            **Business Value:**
            - Reduce backorder age and improve customer satisfaction
            - Free up warehouse space by depleting obsolete SKU inventory
            - Improve inventory turnover and reduce holding costs
            """)

    else:
        render_info_box(
            "No backorder opportunities found. All backorders are on current codes or no inventory available.",
            type="info"
        )

    st.divider()

    # === CODE LOOKUP TOOL ===
    st.subheader("🔍 SKU Code Lookup")
    st.caption("Search for a specific SKU to view its code family and relationships")

    col1, col2 = st.columns([3, 1])

    with col1:
        search_sku = st.text_input(
            "Enter SKU Code",
            value="",
            placeholder="Enter any material code (current or old)...",
            key="sku_search"
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        search_button = st.button("🔎 Search", use_container_width=True)

    if search_button and search_sku:
        # Check if SKU exists in mapping
        all_codes = get_alternate_codes(search_sku)

        if len(all_codes) == 1 and all_codes[0] == search_sku:
            # No alternates found
            st.info(f"No alternate codes found for **{search_sku}**. This SKU has no code transitions.")
        else:
            # Display code family
            current_code = get_current_code(search_sku)
            is_old = is_old_code(search_sku)

            st.success(f"**Code Family Found:** {len(all_codes)} codes in this family")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Searched Code:** `{search_sku}`")
                st.markdown(f"**Status:** {'🔴 Old/Obsolete' if is_old else '✅ Current/Active'}")

            with col2:
                st.markdown(f"**Current Code:** `{current_code}`")
                st.markdown(f"**Total Codes in Family:** {len(all_codes)}")

            # Show all codes
            st.markdown("**All Codes in Family:**")
            codes_list = []
            for code in all_codes:
                status = "✅ Current" if code == current_code else "🔴 Old"
                codes_list.append(f"- `{code}` {status}")

            st.markdown('\n'.join(codes_list))

            # Get detailed inventory/backorder info
            details = get_code_family_details(search_sku, alt_codes_mapping, inventory_data, backorder_data)

            if details['inventory_summary']:
                st.markdown("**Inventory by Code:**")
                inv_df = pd.DataFrame(details['inventory_summary'])
                inv_df['Status'] = inv_df['is_current'].apply(lambda x: '✅ Current' if x else '🔴 Old')
                inv_df['Qty'] = inv_df['qty'].astype(int)
                inv_df['Value (USD)'] = inv_df['value'].apply(lambda x: f"${x:,.0f}")
                st.dataframe(inv_df[['code', 'Status', 'Qty', 'Value (USD)']], hide_index=True)

            if details['backorder_summary']:
                st.markdown("**Backorders by Code:**")
                bo_df = pd.DataFrame(details['backorder_summary'])
                bo_df['Status'] = bo_df['is_current'].apply(lambda x: '✅ Current' if x else '🔴 Old')
                bo_df['Qty'] = bo_df['qty'].astype(int)
                bo_df['Orders'] = bo_df['num_orders'].astype(int)
                st.dataframe(bo_df[['code', 'Status', 'Qty', 'Orders']], hide_index=True)

    st.divider()

    # === ALL CODE FAMILIES TABLE ===
    st.subheader("📋 All SKU Code Families")

    with st.expander("View All Alternate Code Mappings", expanded=False):
        all_families = []

        for current_code, family_codes in alt_codes_mapping['all_codes_by_family'].items():
            old_codes = [c for c in family_codes if c != current_code]
            all_families.append({
                'Current Code': current_code,
                'Old Code(s)': ', '.join(old_codes),
                'Total Codes': len(family_codes)
            })

        families_df = pd.DataFrame(all_families).sort_values('Current Code')

        st.caption(f"Showing {len(families_df)} SKU families with alternate codes")
        render_data_table(families_df, max_rows=100)

    # === BUSINESS RULES REFERENCE ===
    st.divider()
    st.subheader("📖 Business Rules Reference")

    with st.expander("View Alternate Codes Business Rules", expanded=False):
        rules = ALTERNATE_CODES_RULES

        st.markdown("**Normalization Rules:**")
        for key, value in rules['normalization'].items():
            st.markdown(f"- **{key.replace('_', ' ').title()}**: `{value}`")

        st.markdown("\n**Alert Rules:**")
        for key, value in rules['alerts'].items():
            st.markdown(f"- **{key.replace('_', ' ').title()}**: `{value}`")

        st.markdown("\n**Business Logic:**")
        for key, value in rules['business_logic'].items():
            st.markdown(f"- **{key.replace('_', ' ').title()}**: `{value}`")
