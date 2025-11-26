"""
Overview Page - Executive Dashboard
High-level KPIs and summary metrics across all supply chain functions
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import render_page_header, render_kpi_row, render_chart, render_info_box, render_data_table
from business_rules import CURRENCY_RULES
from data_loader import load_deliveries_unified, load_inbound_data, load_master_data, load_inventory_data


# ===== OPERATING BUDGET FUNCTIONS =====

def normalize_sku(sku_value):
    """
    Normalize SKU format to handle inconsistent spacing.
    SKUs have format: PREFIX     SUFFIX (with variable spaces between).
    This normalizes to single space for consistent matching.
    """
    import re
    if pd.isna(sku_value):
        return ''
    # Convert to string, strip outer whitespace, collapse multiple spaces to single
    return re.sub(r'\s+', ' ', str(sku_value).strip())


@st.cache_data(show_spinner="Preparing Operating Budget data...", ttl=300)
def prepare_operating_budget_data(deliveries_data, inbound_data, inventory_data, master_data, display_currency='USD'):
    """
    Prepare aggregated operating budget data by category and month.
    Returns data for OUTBOUND, INBOUND, and INVENTORY sections.

    Args:
        deliveries_data: DELIVERIES.csv for outbound (shipments)
        inbound_data: Inbound_DB.csv for inbound (receipts)
        inventory_data: Inventory analysis data for ending balance
        master_data: Master data for category lookup
        display_currency: 'USD' or 'EUR'

    Returns:
        dict with 'outbound', 'inbound', 'inventory' DataFrames aggregated by category/month
    """
    result = {
        'outbound': pd.DataFrame(),
        'inbound': pd.DataFrame(),
        'inventory': pd.DataFrame(),
        'months': [],
        'categories': []
    }

    # Get currency conversion rate
    eur_to_usd = CURRENCY_RULES.get('conversion_rates', {}).get('EUR_to_USD', 1.08)

    # Generate month range: past 6 months + current + future 5 months
    today = datetime.now()
    # Normalize to midnight to match data timestamps
    current_month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_month = current_month_start - relativedelta(months=6)
    end_month = current_month_start + relativedelta(months=5)

    # Create list of months (all normalized to midnight, as pd.Timestamp for comparison)
    months = []
    current = start_month
    while current <= end_month:
        months.append(pd.Timestamp(current))
        current = current + relativedelta(months=1)
    result['months'] = months

    # Build SKU to category mapping from master data
    # Normalize SKUs to handle inconsistent spacing (1 vs 5 spaces between prefix/suffix)
    sku_category_map = {}
    if not master_data.empty:
        if 'sku' in master_data.columns and 'category' in master_data.columns:
            # Normalize SKU keys for consistent matching
            normalized_map = {}
            for sku, cat in master_data.set_index('sku')['category'].to_dict().items():
                normalized_map[normalize_sku(sku)] = cat
            sku_category_map = normalized_map
        elif 'Material Number' in master_data.columns and 'PLM: Level Classification 4' in master_data.columns:
            master_data_copy = master_data.copy()
            master_data_copy['sku'] = master_data_copy['Material Number'].astype(str).str.strip()
            master_data_copy['category'] = master_data_copy['PLM: Level Classification 4']
            sku_category_map = master_data_copy.set_index('sku')['category'].to_dict()

    # Get all categories
    all_categories = set(sku_category_map.values()) if sku_category_map else set()
    all_categories.discard(np.nan)
    all_categories.discard(None)
    all_categories.discard('')
    result['categories'] = sorted([c for c in all_categories if pd.notna(c)])

    # ===== OUTBOUND (Deliveries/Shipments) =====
    if not deliveries_data.empty:
        df_out = deliveries_data.copy()

        # Get date column
        date_col = None
        for col in ['Goods Issue Date: Date', 'Delivery Creation Date: Date', 'ship_date', 'delivery_date']:
            if col in df_out.columns:
                date_col = col
                break

        if date_col:
            df_out['_date'] = pd.to_datetime(df_out[date_col], format='%m/%d/%y', errors='coerce')
            df_out = df_out[df_out['_date'].notna()]
            df_out['_month'] = df_out['_date'].dt.to_period('M').dt.to_timestamp()

            # Filter to only include months in our range
            df_out = df_out[(df_out['_month'] >= months[0]) & (df_out['_month'] <= months[-1])]

            # Get SKU column and normalize for consistent matching
            sku_col = 'Item - SAP Model Code' if 'Item - SAP Model Code' in df_out.columns else 'sku'
            if sku_col in df_out.columns:
                df_out['_sku'] = df_out[sku_col].apply(normalize_sku)
                df_out['_category'] = df_out['_sku'].map(sku_category_map).fillna('Unknown')
            else:
                df_out['_category'] = 'Unknown'

            # Get quantity
            qty_col = 'Deliveries - TOTAL Goods Issue Qty' if 'Deliveries - TOTAL Goods Issue Qty' in df_out.columns else 'delivered_qty'
            if qty_col in df_out.columns:
                df_out['_qty'] = pd.to_numeric(df_out[qty_col], errors='coerce').fillna(0)
            else:
                df_out['_qty'] = 0

            # Calculate value - need to join with inventory for price
            # For now, aggregate quantities; value calculation requires price data
            df_out['_value'] = 0  # Placeholder - will need price data

            # Aggregate by category and month
            outbound_agg = df_out.groupby(['_category', '_month']).agg({
                '_qty': 'sum',
                '_value': 'sum'
            }).reset_index()
            outbound_agg.columns = ['category', 'month', 'units', 'value']
            result['outbound'] = outbound_agg

    # ===== INBOUND (Receipts) =====
    if not inbound_data.empty:
        df_in = inbound_data.copy()

        # Get receipt date - Inbound_DB uses YYYYMMDD format
        date_col = None
        for col in ['Date', 'receipt_date']:
            if col in df_in.columns:
                date_col = col
                break

        if date_col:
            # Try YYYYMMDD format first, then fall back to other formats
            df_in['_date'] = pd.to_datetime(df_in[date_col], format='%Y%m%d', errors='coerce')
            if df_in['_date'].isna().all():
                df_in['_date'] = pd.to_datetime(df_in[date_col], errors='coerce')

            df_in = df_in[df_in['_date'].notna()]
            df_in['_month'] = df_in['_date'].dt.to_period('M').dt.to_timestamp()

            # Filter to only include months in our range
            df_in = df_in[(df_in['_month'] >= months[0]) & (df_in['_month'] <= months[-1])]

            # Get SKU column and normalize for consistent matching
            sku_col = 'Material Number' if 'Material Number' in df_in.columns else 'sku'
            if sku_col in df_in.columns:
                df_in['_sku'] = df_in[sku_col].apply(normalize_sku)
                df_in['_category'] = df_in['_sku'].map(sku_category_map).fillna('Unknown')
            else:
                df_in['_category'] = 'Unknown'

            # Get received quantity
            qty_col = 'POP Good Receipts Quantity' if 'POP Good Receipts Quantity' in df_in.columns else 'received_qty'
            if qty_col in df_in.columns:
                df_in['_qty'] = pd.to_numeric(df_in[qty_col], errors='coerce').fillna(0)
            else:
                df_in['_qty'] = 0

            # Get value - Inbound_DB has EUR values in Group Currency
            value_col = 'POP Good Receipts Amount (@Purchase Document Price in Group Currency)'
            if value_col in df_in.columns:
                df_in['_value_eur'] = pd.to_numeric(df_in[value_col], errors='coerce').fillna(0)
                # Convert to display currency
                if display_currency == 'USD':
                    df_in['_value'] = df_in['_value_eur'] * eur_to_usd
                else:
                    df_in['_value'] = df_in['_value_eur']
            else:
                df_in['_value'] = 0

            # Aggregate by category and month
            inbound_agg = df_in.groupby(['_category', '_month']).agg({
                '_qty': 'sum',
                '_value': 'sum'
            }).reset_index()
            inbound_agg.columns = ['category', 'month', 'units', 'value']
            result['inbound'] = inbound_agg

    # ===== INVENTORY (Ending Balance by Month) =====
    # Current inventory snapshot - show for current month only
    if not inventory_data.empty:
        df_inv = inventory_data.copy()

        # Get category - handle Categorical type by converting to string first
        if 'category' in df_inv.columns:
            df_inv['_category'] = df_inv['category'].astype(str).replace('nan', 'Unknown').fillna('Unknown')
        else:
            df_inv['_category'] = 'Unknown'

        # Get on-hand qty
        qty_col = 'on_hand_qty' if 'on_hand_qty' in df_inv.columns else None
        if qty_col:
            df_inv['_qty'] = pd.to_numeric(df_inv[qty_col], errors='coerce').fillna(0)
        else:
            df_inv['_qty'] = 0

        # Get value - check for price and currency
        if 'on_hand_qty' in df_inv.columns and 'last_purchase_price' in df_inv.columns:
            df_inv['_value_orig'] = df_inv['on_hand_qty'] * df_inv['last_purchase_price']

            # Check currency - "Group Currency" = EUR, "Plant Currency" or "Local" = USD
            if 'currency' in df_inv.columns:
                # Convert based on currency
                def convert_value(row):
                    if row.get('currency') == 'EUR':
                        return row['_value_orig'] * eur_to_usd if display_currency == 'USD' else row['_value_orig']
                    else:  # Already USD
                        return row['_value_orig'] if display_currency == 'USD' else row['_value_orig'] / eur_to_usd
                df_inv['_value'] = df_inv.apply(convert_value, axis=1)
            else:
                df_inv['_value'] = df_inv['_value_orig']
        else:
            df_inv['_value'] = 0

        # Aggregate by category (current month snapshot)
        inventory_agg = df_inv.groupby('_category').agg({
            '_qty': 'sum',
            '_value': 'sum'
        }).reset_index()
        inventory_agg.columns = ['category', 'units', 'value']
        inventory_agg['month'] = pd.Timestamp(current_month_start)
        result['inventory'] = inventory_agg

    return result


def render_operating_budget_table(budget_data, view_mode='units', display_currency='USD', time_view='monthly'):
    """
    Render the Operating Budget table in OTB format.

    Args:
        budget_data: Dict from prepare_operating_budget_data()
        view_mode: 'units' or 'value'
        display_currency: 'USD' or 'EUR'
        time_view: 'monthly', 'quarterly', 'ytd'
    """
    months = budget_data.get('months', [])
    categories = budget_data.get('categories', [])
    outbound = budget_data.get('outbound', pd.DataFrame())
    inbound = budget_data.get('inbound', pd.DataFrame())
    inventory = budget_data.get('inventory', pd.DataFrame())

    if not months or not categories:
        render_info_box("No data available for Operating Budget. Ensure deliveries and master data are loaded.", type="info")
        return

    # Create month labels
    today = datetime.now()
    # Normalize to midnight and convert to pd.Timestamp for comparison
    current_month = pd.Timestamp(today.replace(day=1, hour=0, minute=0, second=0, microsecond=0))

    def format_month(m):
        """Format month with indicator for current/past/future"""
        label = m.strftime('%b %Y')
        if m == current_month:
            return f"**{label}**"
        return label

    month_labels = [format_month(m) for m in months]

    # Value column name
    value_col = 'units' if view_mode == 'units' else 'value'
    currency_symbol = '$' if display_currency == 'USD' else '€'

    # Helper to format values
    def format_value(val, is_value=False):
        if pd.isna(val) or val == 0:
            return '-'
        if is_value:
            return f"{currency_symbol}{val:,.0f}"
        return f"{val:,.0f}"

    # Build the table data
    table_rows = []

    # ===== OUTBOUND SECTION =====
    table_rows.append({'section': 'OUTBOUND (Shipments)', 'category': '', **{m.strftime('%Y-%m'): '' for m in months}, 'total': ''})

    outbound_totals = {m.strftime('%Y-%m'): 0 for m in months}
    for cat in categories:
        row = {'section': '', 'category': cat}
        row_total = 0
        for m in months:
            if not outbound.empty:
                mask = (outbound['category'] == cat) & (outbound['month'] == m)
                val = outbound.loc[mask, value_col].sum() if mask.any() else 0
            else:
                val = 0
            row[m.strftime('%Y-%m')] = val
            row_total += val
            outbound_totals[m.strftime('%Y-%m')] += val
        row['total'] = row_total
        table_rows.append(row)

    # Outbound subtotal
    table_rows.append({
        'section': '',
        'category': '**Outbound Total**',
        **{k: v for k, v in outbound_totals.items()},
        'total': sum(outbound_totals.values())
    })

    # ===== INBOUND SECTION =====
    table_rows.append({'section': 'INBOUND (Receipts)', 'category': '', **{m.strftime('%Y-%m'): '' for m in months}, 'total': ''})

    inbound_totals = {m.strftime('%Y-%m'): 0 for m in months}
    for cat in categories:
        row = {'section': '', 'category': cat}
        row_total = 0
        for m in months:
            if not inbound.empty:
                mask = (inbound['category'] == cat) & (inbound['month'] == m)
                val = inbound.loc[mask, value_col].sum() if mask.any() else 0
            else:
                val = 0
            row[m.strftime('%Y-%m')] = val
            row_total += val
            inbound_totals[m.strftime('%Y-%m')] += val
        row['total'] = row_total
        table_rows.append(row)

    # Inbound subtotal
    table_rows.append({
        'section': '',
        'category': '**Inbound Total**',
        **{k: v for k, v in inbound_totals.items()},
        'total': sum(inbound_totals.values())
    })

    # ===== INVENTORY SECTION =====
    table_rows.append({'section': 'INVENTORY (Ending Balance)', 'category': '', **{m.strftime('%Y-%m'): '' for m in months}, 'total': ''})

    inventory_totals = {m.strftime('%Y-%m'): 0 for m in months}
    for cat in categories:
        row = {'section': '', 'category': cat}
        row_total = 0
        for m in months:
            # Inventory is only available for current month
            if m == current_month and not inventory.empty:
                mask = (inventory['category'] == cat)
                val = inventory.loc[mask, value_col].sum() if mask.any() else 0
            else:
                val = 0  # Future months blank, past months would need historical snapshots
            row[m.strftime('%Y-%m')] = val
            if m == current_month:
                row_total = val  # Only count current month for inventory
                inventory_totals[m.strftime('%Y-%m')] += val
        row['total'] = row_total
        table_rows.append(row)

    # Inventory subtotal
    table_rows.append({
        'section': '',
        'category': '**Inventory Total**',
        **{k: v for k, v in inventory_totals.items()},
        'total': sum(inventory_totals.values())
    })

    # Convert to DataFrame
    df = pd.DataFrame(table_rows)

    # Format numeric columns - ensure all values are strings for Arrow compatibility
    is_value_view = view_mode == 'value'
    for col in df.columns:
        if col not in ['section', 'category']:
            # Apply format_value to numeric types, then convert entire column to string
            df[col] = df[col].apply(lambda x: format_value(x, is_value_view) if isinstance(x, (int, float, np.integer, np.floating)) else x)
            # Ensure all values are strings for Arrow serialization
            df[col] = df[col].astype(str)

    # Rename columns for display
    column_mapping = {'section': 'Section', 'category': 'Category', 'total': 'Total'}
    for m in months:
        column_mapping[m.strftime('%Y-%m')] = format_month(m)
    df = df.rename(columns=column_mapping)

    # Display the table
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        height=600
    )

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

    # Add stacked volume bars (one segment per year, stacked to show total)
    for i, year in enumerate(years):
        year_data = monthly[monthly['year'] == year].sort_values('month_num')
        color = colors[i % len(colors)]

        fig.add_trace(go.Bar(
            x=year_data['month_num'].tolist(),
            y=year_data['total_count'].tolist(),
            name=f'{year} Volume',
            marker=dict(color=color, opacity=0.4),
            yaxis='y2',
            hovertemplate=f'<b>{year}</b><br>%{{text}}: %{{y:,.0f}} orders<extra></extra>',
            text=[month_names[m-1] for m in year_data['month_num']],
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
        barmode='stack',
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


def render_service_level_chart_by_category(service_data, otif_type='planning', selected_categories=None):
    """Render service level trend chart with separate lines for each category (rolling 12 months).

    X-axis shows the last 12 months of data, with each category as a separate colored line.
    Volume bars show total volume across all categories per month.

    Args:
        service_data: DataFrame with service level data
        otif_type: 'planning' for Planning OTIF (ship within 7 days of order)
                   'logistics' for Logistics OTIF (goods issue within 3 days of delivery creation)
        selected_categories: List of categories to include in the chart. If None, shows top 5 by volume.

    Business Rules:
        - Planning OTIF: ship_date <= order_date + 7 days
        - Logistics OTIF: goods_issue_date <= delivery_creation_date + 3 days
    """
    if service_data.empty or 'ship_month' not in service_data.columns or 'category' not in service_data.columns:
        return None

    # Select the appropriate on-time column based on OTIF type
    if otif_type == 'logistics':
        otif_col = 'logistics_on_time'
        chart_title = "Logistics OTIF by Category (Rolling 12 Months)"
        y_axis_title = "Logistics OTIF %"
    else:
        # Default to planning OTIF
        otif_col = 'planning_on_time' if 'planning_on_time' in service_data.columns else 'on_time'
        chart_title = "Planning OTIF by Category (Rolling 12 Months)"
        y_axis_title = "Planning OTIF %"

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

    # Filter to rolling 12 months
    if 'ship_date' in chart_data.columns:
        max_date = chart_data['ship_date'].max()
        min_date = max_date - pd.DateOffset(months=12)
        chart_data = chart_data[(chart_data['ship_date'] >= min_date) & (chart_data['ship_date'] <= max_date)]
    elif 'ship_year' in chart_data.columns and 'ship_month_num' in chart_data.columns:
        # Fallback: use ship_year and ship_month_num to filter
        from datetime import datetime
        current_date = datetime.now()
        # Create a year-month integer for comparison
        chart_data['year_month'] = chart_data['ship_year'] * 100 + chart_data['ship_month_num']
        current_year_month = current_date.year * 100 + current_date.month
        min_year_month = (current_date.year - 1) * 100 + current_date.month
        chart_data = chart_data[(chart_data['year_month'] >= min_year_month) & (chart_data['year_month'] <= current_year_month)]

    if chart_data.empty:
        return None

    # Get categories - use selected or default to top 5 by volume
    if selected_categories is not None and len(selected_categories) > 0:
        categories = selected_categories
    else:
        # Get top 5 categories by volume
        category_volumes = chart_data.groupby('category', observed=True).size().sort_values(ascending=False)
        categories = category_volumes.head(5).index.tolist()

    if not categories:
        return None

    # Filter to selected categories
    chart_data = chart_data[chart_data['category'].isin(categories)]

    if chart_data.empty:
        return None

    # Create year_month key for grouping
    if 'ship_year' in chart_data.columns and 'ship_month_num' in chart_data.columns:
        chart_data['year_month_key'] = chart_data['ship_year'].astype(int) * 100 + chart_data['ship_month_num'].astype(int)
    elif 'ship_date' in chart_data.columns:
        chart_data['year_month_key'] = chart_data['ship_date'].dt.year * 100 + chart_data['ship_date'].dt.month

    # Group by category and year_month
    monthly_by_cat = chart_data.groupby(['category', 'year_month_key'], observed=True).agg({
        otif_col: ['sum', 'count']
    }).reset_index()

    monthly_by_cat.columns = ['category', 'year_month_key', 'on_time_count', 'total_count']
    monthly_by_cat['on_time_pct'] = (monthly_by_cat['on_time_count'] / monthly_by_cat['total_count'] * 100)

    # Sort by year_month
    monthly_by_cat = monthly_by_cat.sort_values('year_month_key')

    # Create chart
    fig = go.Figure()

    # Color palette for different categories
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#3B4D61', '#6B9AC4', '#06D6A0', '#7CB518', '#FFD166', '#EF8354']

    # Month names for labels
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # Get unique year_months for x-axis
    unique_year_months = sorted(monthly_by_cat['year_month_key'].unique())

    # Create x-axis labels (e.g., "Jan 2024")
    def year_month_to_label(ym):
        year = ym // 100
        month = ym % 100
        return f"{month_names[month-1]} {year}"

    x_labels = [year_month_to_label(ym) for ym in unique_year_months]

    # Add stacked volume bars (one segment per category, stacked to show total)
    for i, category in enumerate(categories):
        cat_data = monthly_by_cat[monthly_by_cat['category'] == category].sort_values('year_month_key')
        color = colors[i % len(colors)]

        # Map year_month to x labels for this category
        cat_x_labels = [year_month_to_label(ym) for ym in cat_data['year_month_key']]

        fig.add_trace(go.Bar(
            x=cat_x_labels,
            y=cat_data['total_count'].tolist(),
            name=f'{category} Volume',
            marker=dict(color=color, opacity=0.4),
            yaxis='y2',
            hovertemplate=f'<b>{category}</b><br>%{{x}}: %{{y:,.0f}} orders<extra></extra>',
            showlegend=True
        ))

    # Calculate overall average OTIF for each category
    category_avg = chart_data.groupby('category', observed=True).agg({
        otif_col: ['sum', 'count']
    }).reset_index()
    category_avg.columns = ['category', 'on_time_count', 'total_count']
    category_avg['avg_on_time_pct'] = (category_avg['on_time_count'] / category_avg['total_count'] * 100)

    # Add OTIF percentage lines for each category
    for i, category in enumerate(categories):
        cat_data = monthly_by_cat[monthly_by_cat['category'] == category].sort_values('year_month_key')
        color = colors[i % len(colors)]

        # Map year_month to x labels
        cat_x_labels = [year_month_to_label(ym) for ym in cat_data['year_month_key']]
        y_values = cat_data['on_time_pct'].tolist()

        # Add monthly trend line
        fig.add_trace(go.Scatter(
            x=cat_x_labels,
            y=y_values,
            mode='lines+markers',
            name=f'{category}',
            line=dict(color=color, width=3),
            marker=dict(size=8, color=color),
            hovertemplate=f'<b>{category}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>'
        ))

        # Add category average as horizontal line
        if len(category_avg[category_avg['category'] == category]) > 0:
            cat_avg_pct = category_avg[category_avg['category'] == category]['avg_on_time_pct'].values[0]
            fig.add_trace(go.Scatter(
                x=[x_labels[0], x_labels[-1]],
                y=[cat_avg_pct, cat_avg_pct],
                mode='lines',
                name=f'{category} Avg ({cat_avg_pct:.1f}%)',
                line=dict(color=color, width=2, dash='dot'),
                showlegend=True,
                hovertemplate=f'{category} Average: {cat_avg_pct:.1f}%<extra></extra>'
            ))

    # Add target line (95% for both OTIF types per business rules)
    fig.add_hline(y=95, line_dash="dash", line_color="green", annotation_text="Target: 95%")

    fig.update_layout(
        title=chart_title,
        xaxis_title="Month",
        yaxis_title=y_axis_title,
        yaxis_range=[0, 100],
        legend_title="Category",
        barmode='stack',
        xaxis=dict(
            tickangle=-45
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

def render_overview_page(service_data, backorder_data, inventory_data,
                         vendor_performance_data=None, international_vendor_performance_data=None,
                         international_vendor_pos_data=None, inbound_data=None,
                         deliveries_data=None, master_data=None, display_currency='USD'):
    """Main overview page render function

    Args:
        service_data: Service level data (order fulfillment OTIF)
        backorder_data: Backorder tracking data
        inventory_data: Inventory analysis data with DIO calculations
        vendor_performance_data: Domestic vendor performance metrics (optional) - NOT used for fill rate
        international_vendor_performance_data: International vendor performance metrics (optional)
        international_vendor_pos_data: Raw international vendor PO data for on-time calculation (optional)
        inbound_data: Inbound_DB.csv data - SOLE source for vendor service level KPIs (domestic + international)
        deliveries_data: DELIVERIES.csv data for Operating Budget (outbound)
        master_data: Master Data.csv for category lookup
        display_currency: 'USD' or 'EUR' for currency display
    """
    # Handle None values
    if vendor_performance_data is None:
        vendor_performance_data = pd.DataFrame()
    if international_vendor_performance_data is None:
        international_vendor_performance_data = pd.DataFrame()
    if international_vendor_pos_data is None:
        international_vendor_pos_data = pd.DataFrame()
    if inbound_data is None:
        inbound_data = pd.DataFrame()
    if deliveries_data is None:
        deliveries_data = pd.DataFrame()
    if master_data is None:
        master_data = pd.DataFrame()

    # Page header
    render_page_header(
        "Executive Overview",
        icon="📊",
        subtitle="Key performance indicators across your end-to-end supply chain"
    )

    # Create tabs for Executive Overview
    tab_dashboard, tab_operating_budget = st.tabs(["📊 Dashboard", "💰 Operating Budget"])

    # ===== TAB 1: DASHBOARD (existing content) =====
    with tab_dashboard:
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

            # Vendor Service Level sub-section
            st.markdown("---")
            st.markdown("###### 🚚 Vendor Service Level")

            # Calculate Vendor Service Level KPIs from Inbound_DB.csv (consolidated domestic + international)
            # Source: Inbound_DB.csv - contains pre-calculated on-time delivery metrics
            if not inbound_data.empty and 'received_qty' in inbound_data.columns:
                # Filter to domestic vendors (IC Flag = NO)
                has_domestic_flag = 'is_domestic' in inbound_data.columns
                domestic_data = inbound_data[inbound_data['is_domestic'] == True] if has_domestic_flag else inbound_data
                international_data = inbound_data[inbound_data['is_international'] == True] if has_domestic_flag else pd.DataFrame()

                # --- DOMESTIC VENDOR KPIs ---
                # Fill Rate: Aggregate by PO to get ordered vs received, excluding not-yet-due open POs
                # On-Time %: Use pre-calculated on_time_qty from receipt rows
                if not domestic_data.empty:
                    today = pd.Timestamp.now()

                    # Aggregate by PO to get totals
                    dom_po_summary = domestic_data.groupby('po_number').agg({
                        'ordered_qty': 'sum',
                        'received_qty': 'sum',
                        'on_time_qty': 'sum',
                        'scheduled_delivery_date': 'max'
                    }).reset_index()

                    # Closed POs (have receipts) + Overdue open POs (past due but no receipt)
                    closed_pos = dom_po_summary[dom_po_summary['received_qty'] > 0]
                    open_pos = dom_po_summary[dom_po_summary['received_qty'] == 0]
                    overdue_open = open_pos[open_pos['scheduled_delivery_date'] < today]

                    # Fill Rate = received / (closed + overdue ordered)
                    dom_ordered = closed_pos['ordered_qty'].sum() + overdue_open['ordered_qty'].sum()
                    dom_received = closed_pos['received_qty'].sum()
                    dom_on_time = closed_pos['on_time_qty'].sum()
                    dom_unique_pos = len(closed_pos) + len(overdue_open)

                    # Domestic Fill Rate (capped at 100% - vendors sometimes over-ship)
                    dom_fill_rate = (dom_received / dom_ordered * 100) if dom_ordered > 0 else 0
                    dom_fill_rate = min(dom_fill_rate, 100.0)  # Cap at 100%
                    st.metric(
                        label="Domestic Fill Rate",
                        value=f"{dom_fill_rate:.1f}%",
                        help=f"**Domestic vendor fill rate.** {dom_received:,.0f} received / {dom_ordered:,.0f} ordered. {len(closed_pos):,} closed POs + {len(overdue_open):,} overdue. Source: Inbound_DB.csv"
                    )

                    # Domestic On-Time % (from receipt data only)
                    dom_on_time_pct = (dom_on_time / dom_received * 100) if dom_received > 0 else 0
                    st.metric(
                        label="Domestic On-Time %",
                        value=f"{dom_on_time_pct:.1f}%",
                        help=f"**Domestic vendor on-time delivery.** {dom_on_time:,.0f} on-time / {dom_received:,.0f} received = {dom_on_time_pct:.1f}%. Source: Inbound_DB.csv"
                    )
                else:
                    st.metric(label="Domestic Fill Rate", value="N/A", help="No domestic vendor data available")
                    st.metric(label="Domestic On-Time %", value="N/A", help="No domestic vendor data available")

                # --- INTERNATIONAL VENDOR KPIs ---
                # Use pre-calculated fields from source data (more reliable than date comparisons)
                # The international data has many historical ORDER rows without matching RECEIPT rows
                if not international_data.empty:
                    # Use pre-calculated open_overdue_qty if available (from source system)
                    has_open_overdue = 'open_overdue_qty' in international_data.columns

                    # Sum totals from all rows (receipts + orders with open qty)
                    intl_ordered = international_data['ordered_qty'].sum()
                    intl_received = international_data['received_qty'].sum()
                    intl_on_time = international_data['on_time_qty'].sum()
                    intl_open_overdue = international_data['open_overdue_qty'].sum() if has_open_overdue else 0

                    # Unique POs with receipts
                    intl_pos_with_receipts = international_data[international_data['received_qty'] > 0]['po_number'].nunique()
                    intl_pos_with_overdue = international_data[international_data['open_overdue_qty'] > 0]['po_number'].nunique() if has_open_overdue else 0

                    # Fill Rate = received / (received + overdue open), capped at 100%
                    # This measures what % of due orders have been fulfilled
                    intl_fillable = intl_received + intl_open_overdue
                    intl_fill_rate = (intl_received / intl_fillable * 100) if intl_fillable > 0 else 0
                    intl_fill_rate = min(intl_fill_rate, 100.0)  # Cap at 100%
                    st.metric(
                        label="Int'l Fill Rate",
                        value=f"{intl_fill_rate:.1f}%",
                        help=f"**International vendor fill rate.** {intl_received:,.0f} received / {intl_fillable:,.0f} due. {intl_pos_with_receipts:,} POs with receipts, {intl_open_overdue:,.0f} units overdue. Source: Inbound_DB.csv"
                    )

                    # International On-Time %
                    intl_on_time_pct = (intl_on_time / intl_received * 100) if intl_received > 0 else 0
                    st.metric(
                        label="Int'l On-Time %",
                        value=f"{intl_on_time_pct:.1f}%",
                        help=f"**International vendor on-time delivery.** {intl_on_time:,.0f} on-time / {intl_received:,.0f} received = {intl_on_time_pct:.1f}%. Source: Inbound_DB.csv"
                    )
                else:
                    st.metric(label="Int'l Fill Rate", value="N/A", help="No international vendor data in Inbound_DB.csv")
                    st.metric(label="Int'l On-Time %", value="N/A", help="No international vendor data in Inbound_DB.csv")
            else:
                st.metric(label="Domestic Fill Rate", value="N/A", help="No inbound receipt data available")
                st.metric(label="Domestic On-Time %", value="N/A", help="No inbound receipt data available")
                st.metric(label="Int'l Fill Rate", value="N/A", help="No inbound receipt data available")
                st.metric(label="Int'l On-Time %", value="N/A", help="No inbound receipt data available")

            # International In-Transit Quantity (from ATL_FULLFILLMENT.csv - open POs only)
            if not international_vendor_pos_data.empty:
                if 'in_transit_qty' in international_vendor_pos_data.columns:
                    total_in_transit = international_vendor_pos_data['in_transit_qty'].sum()
                    num_shipments = len(international_vendor_pos_data)
                    st.metric(
                        label="Int'l In-Transit Units",
                        value=f"{total_in_transit:,.0f}",
                        help=f"**{num_shipments:,}** open shipments currently in transit from international vendors. Source: ATL_FULLFILLMENT.csv"
                    )
                elif 'open_qty' in international_vendor_pos_data.columns:
                    total_open = international_vendor_pos_data['open_qty'].sum()
                    num_shipments = len(international_vendor_pos_data)
                    st.metric(
                        label="Int'l In-Transit Units",
                        value=f"{total_open:,.0f}",
                        help=f"**{num_shipments:,}** open shipments currently in transit from international vendors. Source: ATL_FULLFILLMENT.csv"
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

        # Use preset years (last 3 years in data) - no user selection needed
        selected_years = None
        if not service_data.empty and 'ship_year' in service_data.columns:
            all_years_in_data = sorted(service_data['ship_year'].dropna().unique())
            # Use last 3 years by default
            selected_years = [int(y) for y in all_years_in_data[-3:]] if len(all_years_in_data) > 3 else [int(y) for y in all_years_in_data]

        # Planning OTIF Chart
        planning_chart = render_service_level_chart(service_data, otif_type='planning', selected_years=selected_years)
        if planning_chart:
            render_chart(planning_chart, height=350)
        else:
            render_info_box("No Planning OTIF data available", type="info")

        # Logistics OTIF Chart
        logistics_chart = render_service_level_chart(service_data, otif_type='logistics', selected_years=selected_years)
        if logistics_chart:
            render_chart(logistics_chart, height=350)
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

    # ===== TAB 2: OPERATING BUDGET =====
    with tab_operating_budget:
        st.markdown("### Operating Budget (OTB View)")
        st.caption("Rolling 12-month view: Past 6 months + Current Month + Future 5 months")

        # View mode toggle: Units vs Value
        view_col1, view_col2, view_col3 = st.columns([1, 1, 2])
        with view_col1:
            view_mode = st.radio(
                "View By",
                options=['units', 'value'],
                format_func=lambda x: 'Units' if x == 'units' else f'Value ({display_currency})',
                horizontal=True,
                key="operating_budget_view_mode"
            )

        with view_col2:
            time_view = st.selectbox(
                "Time Aggregation",
                options=['monthly', 'quarterly', 'ytd'],
                format_func=lambda x: {'monthly': 'Monthly', 'quarterly': 'Quarterly', 'ytd': 'YTD'}[x],
                key="operating_budget_time_view"
            )

        # Prepare budget data
        budget_data = prepare_operating_budget_data(
            deliveries_data=deliveries_data,
            inbound_data=inbound_data,
            inventory_data=inventory_data,
            master_data=master_data,
            display_currency=display_currency
        )

        # Render the OTB table
        if budget_data and budget_data.get('categories'):
            render_operating_budget_table(
                budget_data=budget_data,
                view_mode=view_mode,
                display_currency=display_currency,
                time_view=time_view
            )

            # Summary metrics
            st.divider()
            st.markdown("#### Summary Metrics")

            summary_cols = st.columns(3)

            with summary_cols[0]:
                # Total Outbound
                if not budget_data.get('outbound', pd.DataFrame()).empty:
                    total_outbound = budget_data['outbound']['units'].sum() if view_mode == 'units' else budget_data['outbound']['value'].sum()
                    label = f"Total Outbound ({'Units' if view_mode == 'units' else display_currency})"
                    if view_mode == 'value':
                        st.metric(label, f"{'$' if display_currency == 'USD' else '€'}{total_outbound:,.0f}")
                    else:
                        st.metric(label, f"{total_outbound:,.0f}")
                else:
                    st.metric("Total Outbound", "No data")

            with summary_cols[1]:
                # Total Inbound
                if not budget_data.get('inbound', pd.DataFrame()).empty:
                    total_inbound = budget_data['inbound']['units'].sum() if view_mode == 'units' else budget_data['inbound']['value'].sum()
                    label = f"Total Inbound ({'Units' if view_mode == 'units' else display_currency})"
                    if view_mode == 'value':
                        st.metric(label, f"{'$' if display_currency == 'USD' else '€'}{total_inbound:,.0f}")
                    else:
                        st.metric(label, f"{total_inbound:,.0f}")
                else:
                    st.metric("Total Inbound", "No data")

            with summary_cols[2]:
                # Current Inventory
                if not budget_data.get('inventory', pd.DataFrame()).empty:
                    total_inventory = budget_data['inventory']['units'].sum() if view_mode == 'units' else budget_data['inventory']['value'].sum()
                    label = f"Current Inventory ({'Units' if view_mode == 'units' else display_currency})"
                    if view_mode == 'value':
                        st.metric(label, f"{'$' if display_currency == 'USD' else '€'}{total_inventory:,.0f}")
                    else:
                        st.metric(label, f"{total_inventory:,.0f}")
                else:
                    st.metric("Current Inventory", "No data")

            # Future features placeholder
            with st.expander("📋 Future Enhancements", expanded=False):
                st.markdown("""
                **Coming Soon:**
                - Inventory Turns calculation
                - Days Inventory Outstanding (DIO) by category
                - Open-to-Buy (OTB) calculation
                - Plan vs Actual variance analysis
                - Budget file integration for future month forecasts
                """)
        else:
            render_info_box(
                "No data available for Operating Budget. Ensure deliveries, inbound, and master data files are loaded.",
                type="info"
            )
