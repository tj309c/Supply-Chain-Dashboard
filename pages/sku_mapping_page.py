"""
SKU Mapping & Alternate Codes Page
Displays material code relationships, supersessions, and code transitions
PRIMARY FOCUS: Highlight alternate SKUs on backorder to alert users to update orders to NEW material codes
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

            # Build detail of which codes have inventory (vectorized using to_dict)
            codes_with_inventory = family_inventory[['sku', 'is_old', 'on_hand_qty']].copy()
            codes_with_inventory['value'] = family_inventory.get('stock_value_usd', 0)
            codes_with_inventory = codes_with_inventory.rename(
                columns={'sku': 'code', 'on_hand_qty': 'qty'}
            ).to_dict('records')

            split_inventory.append({
                'current_code': current_code,
                'num_codes_with_inventory': len(family_inventory),
                'total_qty': total_qty,
                'total_value_usd': total_value,
                'codes_detail': codes_with_inventory,
                'all_codes': family_codes
            })

    return pd.DataFrame(split_inventory)


def analyze_old_code_backorders(backorder_data, inventory_data):
    """
    Find ALL backorders on old/alternate codes that need to be updated to new codes.

    This is the PRIMARY analysis - identifies orders placed on obsolete material codes
    that need to be changed to the current/new material code.

    Returns DataFrame with all old code backorders requiring action
    """
    if backorder_data.empty:
        return pd.DataFrame()

    # Normalize codes and identify old code backorders
    backorder_with_current = backorder_data.copy()
    backorder_with_current['current_code'] = backorder_with_current['sku'].apply(get_current_code)
    backorder_with_current['is_old'] = backorder_with_current['sku'].apply(is_old_code)

    # Find ALL backorders on old codes - these ALL need attention
    old_code_backorders = backorder_with_current[backorder_with_current['is_old'] == True].copy()

    if old_code_backorders.empty:
        return pd.DataFrame()

    # Check inventory availability on current code (optional - for prioritization)
    inventory_by_current = {}
    if not inventory_data.empty:
        inventory_with_current = inventory_data.copy()
        inventory_with_current['current_code'] = inventory_with_current['sku'].apply(get_current_code)
        inventory_by_current = inventory_with_current.groupby('current_code')['on_hand_qty'].sum().to_dict()

    # Build the analysis dataframe
    old_code_backorders['new_code'] = old_code_backorders['current_code']
    old_code_backorders['inventory_on_new_code'] = old_code_backorders['current_code'].map(
        lambda x: inventory_by_current.get(x, 0)
    )
    old_code_backorders['can_fulfill_now'] = old_code_backorders.apply(
        lambda row: row['inventory_on_new_code'] >= row['backorder_qty'], axis=1
    )

    # Priority: Critical (60+ days), High (30+ days), Medium (14+ days), Low (<14 days)
    def get_priority(days):
        if days >= 60:
            return 'Critical'
        elif days >= 30:
            return 'High'
        elif days >= 14:
            return 'Medium'
        return 'Low'

    old_code_backorders['priority'] = old_code_backorders['days_on_backorder'].apply(get_priority)

    # Select relevant columns
    result = old_code_backorders[[
        'sku', 'new_code', 'backorder_qty', 'customer_name', 'sales_order',
        'days_on_backorder', 'priority', 'inventory_on_new_code', 'can_fulfill_now'
    ]].rename(columns={
        'sku': 'old_code',
        'customer_name': 'customer',
        'sales_order': 'order_number'
    })

    return result.sort_values(['priority', 'days_on_backorder'],
                               key=lambda x: x.map({'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3})
                               if x.name == 'priority' else -x,
                               ascending=[True, False])


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

    # Vectorized approach: aggregate inventory by SKU, then merge with backorders
    inventory_agg = inventory_with_current.groupby('sku').agg({
        'on_hand_qty': 'sum'
    }).reset_index()
    inventory_agg.columns = ['current_code', 'available_qty_current_code']

    # Merge backorders with inventory availability
    opps_merged = old_code_backorders.merge(
        inventory_agg,
        left_on='current_code',
        right_on='current_code',
        how='inner'
    )

    # Filter to only opportunities with available inventory
    opps_merged = opps_merged[opps_merged['available_qty_current_code'] > 0]

    # Calculate fulfillment quantities and priority
    opps_merged['can_fulfill_qty'] = opps_merged.apply(
        lambda row: min(row['backorder_qty'], row['available_qty_current_code']), axis=1
    )
    opps_merged['priority'] = opps_merged['days_on_backorder'].apply(
        lambda days: 'High' if days >= 30 else 'Medium'
    )

    # Select and rename columns for final opportunities dataframe
    if not opps_merged.empty:
        opportunities = opps_merged[['sku', 'current_code', 'backorder_qty',
                                     'available_qty_current_code', 'can_fulfill_qty',
                                     'customer_name', 'sales_order', 'days_on_backorder',
                                     'priority']].rename(
            columns={
                'sku': 'old_code_backorder',
                'customer_name': 'customer',
                'sales_order': 'order_number'
            }
        ).to_dict('records')

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
        subtitle="Identify orders on OLD material codes that need to be updated to NEW codes"
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

    # ============================================================
    # PRIMARY SECTION: BACKORDERS ON OLD/ALTERNATE CODES
    # This is the main focus - orders that need code updates
    # ============================================================

    old_code_backorders = analyze_old_code_backorders(backorder_data, inventory_data)

    if not old_code_backorders.empty:
        total_orders = len(old_code_backorders)
        total_units = old_code_backorders['backorder_qty'].sum()
        critical_count = len(old_code_backorders[old_code_backorders['priority'] == 'Critical'])
        high_count = len(old_code_backorders[old_code_backorders['priority'] == 'High'])
        can_fulfill_now = len(old_code_backorders[old_code_backorders['can_fulfill_now'] == True])

        # Alert banner for action required
        st.error(f"""
        **ACTION REQUIRED: {total_orders} Orders on OLD Material Codes**

        These backorders are placed on obsolete/superseded SKU codes. **Sales team must update these orders to use the NEW material code.**
        """)

        # Key metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Orders on Old Codes",
                f"{total_orders:,}",
                help="Total backorders placed on obsolete material codes"
            )

        with col2:
            st.metric(
                "Total Units",
                f"{int(total_units):,}",
                help="Total quantity on backorder with old codes"
            )

        with col3:
            delta_text = "URGENT" if (critical_count + high_count) > 0 else None
            st.metric(
                "Critical + High Priority",
                f"{critical_count + high_count:,}",
                delta=delta_text,
                delta_color="inverse" if delta_text else "off",
                help="Critical (60+ days) + High (30+ days) priority orders"
            )

        with col4:
            st.metric(
                "Can Fulfill Immediately",
                f"{can_fulfill_now:,}",
                help="Orders where inventory exists on new code - can ship once code is updated"
            )

        st.divider()

        # === SALES TEAM ACTION CALLOUT ===
        st.markdown("### Sales Team Action Required")

        st.warning("""
        **For each order below, contact the Sales team to:**

        1. Update the material code on the sales order from the **OLD code** to the **NEW code**
        2. Once updated, the order can be fulfilled from available inventory

        **Why this matters:** Orders cannot ship because they reference obsolete material codes. The product exists under the new code.
        """)

        # Priority filter
        priority_filter = st.selectbox(
            "Filter by Priority",
            options=["All", "Critical (60+ days)", "High (30+ days)", "Medium (14+ days)", "Low (<14 days)"],
            index=0
        )

        filtered_data = old_code_backorders.copy()
        if priority_filter != "All":
            priority_map = {
                "Critical (60+ days)": "Critical",
                "High (30+ days)": "High",
                "Medium (14+ days)": "Medium",
                "Low (<14 days)": "Low"
            }
            filtered_data = filtered_data[filtered_data['priority'] == priority_map[priority_filter]]

        # Format display table
        display_df = pd.DataFrame({
            'Priority': filtered_data['priority'],
            'OLD Code (On Order)': filtered_data['old_code'],
            'NEW Code (Update To)': filtered_data['new_code'],
            'Qty': filtered_data['backorder_qty'].astype(int),
            'Customer': filtered_data['customer'],
            'Order #': filtered_data['order_number'],
            'Days on BO': filtered_data['days_on_backorder'].astype(int),
            'Inventory on New Code': filtered_data['inventory_on_new_code'].astype(int),
            'Can Ship Now': filtered_data['can_fulfill_now'].apply(lambda x: "Yes" if x else "No")
        })

        # Color code priority for visual emphasis
        def highlight_priority(val):
            if val == 'Critical':
                return 'background-color: #ff4444; color: white; font-weight: bold'
            elif val == 'High':
                return 'background-color: #ff8800; color: white; font-weight: bold'
            elif val == 'Medium':
                return 'background-color: #ffcc00; color: black'
            return ''

        st.dataframe(
            display_df.style.applymap(highlight_priority, subset=['Priority']),
            use_container_width=True,
            hide_index=True,
            height=400
        )

        # Summary by customer for sales team
        with st.expander("Summary by Customer (for Sales Team)", expanded=False):
            customer_summary = old_code_backorders.groupby('customer').agg({
                'order_number': 'count',
                'backorder_qty': 'sum',
                'days_on_backorder': 'max'
            }).reset_index()
            customer_summary.columns = ['Customer', 'Orders Affected', 'Total Units', 'Max Days on BO']
            customer_summary = customer_summary.sort_values('Total Units', ascending=False)

            st.dataframe(customer_summary, use_container_width=True, hide_index=True)

        # Summary by old code
        with st.expander("Summary by Old Code", expanded=False):
            code_summary = old_code_backorders.groupby(['old_code', 'new_code']).agg({
                'order_number': 'count',
                'backorder_qty': 'sum'
            }).reset_index()
            code_summary.columns = ['Old Code', 'New Code', 'Orders', 'Total Units']
            code_summary = code_summary.sort_values('Total Units', ascending=False)

            st.dataframe(code_summary, use_container_width=True, hide_index=True)

    else:
        st.success("""
        **No backorders on old/alternate codes.**

        All current backorders are on active material codes - no code updates needed.
        """)

    st.divider()

    # ============================================================
    # SECONDARY: Alternate Codes Summary & Reference
    # ============================================================

    with st.expander("Alternate Codes Summary", expanded=False):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "SKU Families",
                f"{summary['total_sku_families']:,}",
                help="Number of SKU families with alternate codes"
            )

        with col2:
            st.metric(
                "Total Old Codes",
                f"{summary['total_old_codes']:,}",
                help="Total obsolete/superseded material codes"
            )

        with col3:
            st.metric(
                "Families with 2 Codes",
                f"{summary['families_with_2_codes']:,}",
                help="SKU families with 1 current + 1 old code"
            )

        with col4:
            st.metric(
                "Families with 3+ Codes",
                f"{summary['families_with_3_codes']:,}",
                help="SKU families with multiple old codes"
            )

    # ============================================================
    # SECONDARY: Inventory Split Analysis (collapsed by default)
    # ============================================================

    with st.expander("Inventory Split Across Codes", expanded=False):
        split_analysis = analyze_inventory_split(inventory_data, alt_codes_mapping)

        if not split_analysis.empty:
            total_split_value = split_analysis['total_value_usd'].sum()
            total_split_families = len(split_analysis)

            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "SKU Families with Split Inventory",
                    f"{total_split_families:,}",
                    help="Families with inventory on multiple codes"
                )
            with col2:
                st.metric(
                    "Total Value of Split Inventory",
                    f"${total_split_value:,.0f}",
                    help="USD value of inventory split across codes"
                )

            display_split = split_analysis.sort_values('total_value_usd', ascending=False).head(20).copy()

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
            st.info("No inventory split detected. All inventory consolidated under one code per family.")

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
        search_button = st.button("🔎 Search", width='stretch')

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
