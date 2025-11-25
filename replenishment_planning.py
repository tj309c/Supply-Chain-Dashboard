"""
Replenishment Planning Module
=============================
Professional demand planning module for calculating suggested orders using
Net Requirements Planning (MRP) methodology.

Key Features:
- Safety stock calculation using Z-score method (95% service level)
- Bi-monthly (14-day) review period
- Combines domestic and international POs for complete supply visibility
- Net Requirements = Order-Up-To Level - Available Supply + Backorders
- Grouped by vendor, sorted by priority and cost

Author: POP Supply Chain Team
Version: 1.0
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Optional

# ===== CONSTANTS =====

# Service level Z-scores for safety stock calculation
SERVICE_LEVEL_Z_SCORES = {
    90: 1.28,
    95: 1.65,  # Default - standard service level
    98: 2.05,
    99: 2.33
}

# Default parameters
DEFAULT_SERVICE_LEVEL = 95
DEFAULT_LEAD_TIME_DAYS = 90  # Conservative default when no PO history
REVIEW_PERIOD_DAYS = 14  # Bi-monthly review cycle
SAFETY_STOCK_BUFFER_DAYS = 5  # Additional buffer added to lead time


def normalize_sku(sku_value) -> str:
    """
    Normalize a SKU string by:
    1. Converting to uppercase
    2. Stripping leading/trailing whitespace
    3. Collapsing multiple internal whitespace to single space

    This ensures consistent SKU matching across different data sources
    that may have varying whitespace formatting.

    Args:
        sku_value: SKU string to normalize

    Returns:
        Normalized SKU string
    """
    if pd.isna(sku_value):
        return ''
    return re.sub(r'\s+', ' ', str(sku_value).strip().upper())


def normalize_sku_series(series: pd.Series) -> pd.Series:
    """
    Normalize a pandas Series of SKU values.

    Args:
        series: Pandas Series containing SKU strings

    Returns:
        Series with normalized SKU strings
    """
    return series.astype(str).str.strip().str.upper().apply(lambda x: re.sub(r'\s+', ' ', x))


def calculate_safety_stock(
    daily_demand: float,
    demand_std: float,
    lead_time_days: float,
    service_level: int = DEFAULT_SERVICE_LEVEL
) -> float:
    """
    Calculate safety stock using the Z-score method.

    Formula: Safety Stock = Z-score * std_demand * sqrt(lead_time)

    This provides statistical protection against demand variability
    during the lead time period.

    Args:
        daily_demand: Average daily demand (units/day)
        demand_std: Standard deviation of daily demand
        lead_time_days: Supplier lead time in days
        service_level: Target service level (90, 95, 98, or 99)

    Returns:
        Safety stock quantity in units
    """
    if daily_demand <= 0 or demand_std <= 0 or lead_time_days <= 0:
        return 0

    z_score = SERVICE_LEVEL_Z_SCORES.get(service_level, SERVICE_LEVEL_Z_SCORES[95])

    # Safety stock formula: Z * sigma * sqrt(LT)
    # This accounts for demand variability over the lead time period
    safety_stock = z_score * demand_std * np.sqrt(lead_time_days)

    return max(0, round(safety_stock, 0))


def calculate_reorder_point(
    daily_demand: float,
    lead_time_days: float,
    safety_stock: float
) -> float:
    """
    Calculate the reorder point (ROP).

    Formula: ROP = (Daily Demand * Lead Time) + Safety Stock

    When inventory drops below ROP, an order should be placed.

    Args:
        daily_demand: Average daily demand (units/day)
        lead_time_days: Supplier lead time in days
        safety_stock: Pre-calculated safety stock

    Returns:
        Reorder point in units
    """
    if daily_demand <= 0:
        return safety_stock

    demand_during_lead_time = daily_demand * lead_time_days
    reorder_point = demand_during_lead_time + safety_stock

    return max(0, round(reorder_point, 0))


def calculate_order_up_to_level(
    daily_demand: float,
    lead_time_days: float,
    review_period_days: float,
    safety_stock: float
) -> float:
    """
    Calculate the Order-Up-To Level (S) for periodic review system.

    Formula: S = (Lead Time + Review Period) * Daily Demand + Safety Stock

    This is the target inventory level when placing an order.

    Args:
        daily_demand: Average daily demand (units/day)
        lead_time_days: Supplier lead time in days
        review_period_days: Time between order reviews (14 days for bi-monthly)
        safety_stock: Pre-calculated safety stock

    Returns:
        Order-up-to level in units
    """
    if daily_demand <= 0:
        return safety_stock

    # Cover demand during lead time + review period
    coverage_days = lead_time_days + review_period_days
    demand_coverage = daily_demand * coverage_days
    order_up_to = demand_coverage + safety_stock

    return max(0, round(order_up_to, 0))


def calculate_suggested_order(
    order_up_to_level: float,
    on_hand_qty: float,
    in_transit_qty: float,
    open_po_qty: float,
    backorder_qty: float
) -> float:
    """
    Calculate suggested order quantity using Net Requirements method.

    Formula:
    Available Supply = On Hand + In Transit + Open POs
    Net Requirement = max(0, Order-Up-To Level - Available Supply)
    Suggested Order = Net Requirement + Backorders

    Backorders are added ON TOP because they represent committed customer
    demand that must be fulfilled beyond normal replenishment.

    Args:
        order_up_to_level: Target inventory level
        on_hand_qty: Current inventory on hand
        in_transit_qty: Inventory in transit (not yet received)
        open_po_qty: Quantity on open purchase orders
        backorder_qty: Outstanding customer backorder quantity

    Returns:
        Suggested order quantity in units
    """
    # Calculate available supply
    available_supply = on_hand_qty + in_transit_qty + open_po_qty

    # Net requirement (how much we're short of target)
    net_requirement = max(0, order_up_to_level - available_supply)

    # Add backorders on top (committed customer demand)
    suggested_order = net_requirement + backorder_qty

    return max(0, round(suggested_order, 0))


def calculate_priority_score(
    days_of_supply: float,
    backorder_qty: float,
    daily_demand: float
) -> float:
    """
    Calculate priority score for ordering (higher = more urgent).

    Factors:
    - Days of supply (lower = higher priority)
    - Backorder quantity (higher = higher priority)
    - Demand velocity (higher daily demand = higher priority)

    Args:
        days_of_supply: Current inventory coverage in days
        backorder_qty: Outstanding backorder quantity
        daily_demand: Average daily demand

    Returns:
        Priority score (0-100, higher = more urgent)
    """
    score = 0

    # Days of supply factor (0-40 points)
    # < 7 days = 40 points, 7-14 = 30, 14-30 = 20, 30-60 = 10, 60+ = 0
    if days_of_supply < 7:
        score += 40
    elif days_of_supply < 14:
        score += 30
    elif days_of_supply < 30:
        score += 20
    elif days_of_supply < 60:
        score += 10

    # Backorder factor (0-40 points)
    if backorder_qty > 0:
        # Scale based on backorder quantity relative to daily demand
        if daily_demand > 0:
            backorder_days = backorder_qty / daily_demand
            if backorder_days > 30:
                score += 40
            elif backorder_days > 14:
                score += 30
            elif backorder_days > 7:
                score += 20
            else:
                score += 10
        else:
            score += 20  # Has backorders but no demand history

    # Demand velocity factor (0-20 points)
    if daily_demand > 10:
        score += 20
    elif daily_demand > 5:
        score += 15
    elif daily_demand > 1:
        score += 10
    elif daily_demand > 0:
        score += 5

    return min(100, score)


def generate_replenishment_plan(
    inventory_df: pd.DataFrame,
    demand_forecast_df: pd.DataFrame,
    backorder_df: pd.DataFrame,
    domestic_po_df: pd.DataFrame,
    international_po_df: pd.DataFrame,
    master_df: pd.DataFrame,
    service_level: float = DEFAULT_SERVICE_LEVEL / 100.0,
    default_lead_time_days: int = DEFAULT_LEAD_TIME_DAYS,
    review_period_days: int = REVIEW_PERIOD_DAYS
) -> pd.DataFrame:
    """
    Generate comprehensive replenishment plan for all SKUs.

    This is the main entry point for replenishment planning.

    Args:
        inventory_df: Current inventory data (on_hand_qty, in_transit_qty)
        demand_forecast_df: Demand forecast with daily_demand and std
        backorder_df: Customer backorder data
        domestic_po_df: Domestic vendor PO data
        international_po_df: International fulfillment PO data (ATL)
        master_df: Master data for vendor lookup and category filter
        service_level: Target service level as decimal (default 0.95 for 95%)
        default_lead_time_days: Default lead time when no PO history (default 90)
        review_period_days: Review period in days (default 14 for bi-monthly)

    Returns:
        DataFrame with replenishment plan
    """
    logs = []
    logs.append("INFO: Starting replenishment planning calculation...")

    # ===== STEP 1: Filter for RETAIL PERMANENT category =====
    logs.append("INFO: Filtering for RETAIL PERMANENT category...")

    retail_permanent_skus = set()
    if not master_df.empty:
        # Look for category column
        category_col = None
        for col in ['category', 'Category', 'Product Category', 'product_category']:
            if col in master_df.columns:
                category_col = col
                break

        if category_col:
            retail_mask = master_df[category_col].str.upper().str.contains('RETAIL', na=False)
            permanent_mask = master_df[category_col].str.upper().str.contains('PERMANENT', na=False)

            # Get SKU column
            sku_col = None
            for col in ['sku', 'SKU', 'Material Number', 'SAP Material Code']:
                if col in master_df.columns:
                    sku_col = col
                    break

            if sku_col:
                retail_permanent_skus = set(
                    normalize_sku_series(master_df[retail_mask | permanent_mask][sku_col])
                )
                logs.append(f"INFO: Found {len(retail_permanent_skus)} RETAIL PERMANENT SKUs in master data")

    # ===== STEP 2: Get demand forecast data =====
    logs.append("INFO: Processing demand forecast data...")

    if demand_forecast_df.empty:
        logs.append("WARNING: No demand forecast data available")
        return pd.DataFrame()

    # Normalize SKU column (collapse multiple whitespace to single space)
    demand_df = demand_forecast_df.copy()
    if 'sku' in demand_df.columns:
        demand_df['sku'] = normalize_sku_series(demand_df['sku'])

    # Filter for retail permanent if we have the list
    if retail_permanent_skus:
        demand_df = demand_df[demand_df['sku'].isin(retail_permanent_skus)]
        logs.append(f"INFO: Filtered to {len(demand_df)} RETAIL PERMANENT SKUs with demand data")

    if demand_df.empty:
        logs.append("WARNING: No RETAIL PERMANENT SKUs found in demand forecast")
        return pd.DataFrame()

    # ===== STEP 3: Get current inventory =====
    logs.append("INFO: Processing inventory data...")

    inv_df = inventory_df.copy() if not inventory_df.empty else pd.DataFrame()
    if not inv_df.empty and 'sku' in inv_df.columns:
        inv_df['sku'] = normalize_sku_series(inv_df['sku'])
        # Build aggregation dict dynamically based on available columns
        agg_dict = {'on_hand_qty': 'sum'}
        if 'in_transit_qty' in inv_df.columns:
            agg_dict['in_transit_qty'] = 'sum'
        if 'last_purchase_price' in inv_df.columns:
            agg_dict['last_purchase_price'] = 'first'  # Take first price per SKU
        inv_df = inv_df.groupby('sku').agg(agg_dict).reset_index()
        # Ensure in_transit_qty column exists
        if 'in_transit_qty' not in inv_df.columns:
            inv_df['in_transit_qty'] = 0
        # Ensure last_purchase_price column exists
        if 'last_purchase_price' not in inv_df.columns:
            inv_df['last_purchase_price'] = 0

    # ===== STEP 4: Get backorder data =====
    logs.append("INFO: Processing backorder data...")

    backorder_summary = pd.DataFrame()
    if not backorder_df.empty and 'sku' in backorder_df.columns:
        bo_df = backorder_df.copy()
        bo_df['sku'] = normalize_sku_series(bo_df['sku'])

        # Aggregate backorders by SKU
        backorder_summary = bo_df.groupby('sku').agg({
            'backorder_qty': 'sum'
        }).reset_index()
        logs.append(f"INFO: Found {len(backorder_summary)} SKUs with backorders")

    # ===== STEP 5: Get open PO data (domestic + international) =====
    logs.append("INFO: Processing open PO data...")

    open_po_summary = pd.DataFrame()

    # Process domestic POs
    domestic_open = pd.DataFrame()
    if not domestic_po_df.empty:
        dom_df = domestic_po_df.copy()

        # Find SKU column
        sku_col = None
        for col in ['sku', 'SAP Material Code', 'Material Number']:
            if col in dom_df.columns:
                sku_col = col
                break

        # Find open qty column
        qty_col = None
        for col in ['open_qty', 'expected_qty', 'Open Quantity', 'SAP Purchase Orders - Open Quantity']:
            if col in dom_df.columns:
                qty_col = col
                break

        if sku_col and qty_col:
            dom_df['sku'] = normalize_sku_series(dom_df[sku_col])
            dom_df['open_qty'] = pd.to_numeric(dom_df[qty_col], errors='coerce').fillna(0)

            # Filter for open POs only
            if 'is_open' in dom_df.columns:
                dom_df = dom_df[dom_df['is_open'] == True]
            elif qty_col:
                dom_df = dom_df[dom_df['open_qty'] > 0]

            domestic_open = dom_df.groupby('sku').agg({
                'open_qty': 'sum'
            }).reset_index()
            domestic_open['source'] = 'Domestic'
            logs.append(f"INFO: Found {len(domestic_open)} SKUs with open domestic POs")

    # Process international POs (ATL Fulfillment)
    intl_open = pd.DataFrame()
    if not international_po_df.empty:
        intl_df = international_po_df.copy()

        # SKU column is 'SAP Item Material Code'
        if 'SAP Item Material Code' in intl_df.columns:
            intl_df['sku'] = normalize_sku_series(intl_df['SAP Item Material Code'])

        # Qty column is ' TOTAL Good Issue Qty ' (note spaces)
        qty_col = None
        for col in intl_df.columns:
            if 'good issue' in col.lower() and 'qty' in col.lower():
                qty_col = col
                break

        # Status column is 'ON TIME TRANSIT'
        if qty_col and 'ON TIME TRANSIT' in intl_df.columns:
            intl_df['open_qty'] = pd.to_numeric(intl_df[qty_col], errors='coerce').fillna(0)

            # Filter for non-delivered (ON TIME or ON DELAY = still in transit)
            intl_df = intl_df[
                (intl_df['ON TIME TRANSIT'] != 'DELIVERED') &
                (intl_df['open_qty'] > 0)
            ]

            if not intl_df.empty:
                intl_open = intl_df.groupby('sku').agg({
                    'open_qty': 'sum'
                }).reset_index()
                intl_open['source'] = 'International'
                logs.append(f"INFO: Found {len(intl_open)} SKUs with open international shipments")

    # Combine domestic and international
    if not domestic_open.empty or not intl_open.empty:
        combined_pos = pd.concat([domestic_open, intl_open], ignore_index=True)
        open_po_summary = combined_pos.groupby('sku').agg({
            'open_qty': 'sum'
        }).reset_index()

    # ===== STEP 6: Calculate lead times =====
    logs.append("INFO: Calculating lead times...")

    # For now, use default lead time. Future enhancement: calculate from PO history
    # TODO: Calculate actual lead times from domestic PO + inbound receipt dates

    # ===== STEP 7: Build replenishment plan =====
    logs.append("INFO: Building replenishment plan...")

    # PERFORMANCE: Pre-build lookup dictionaries to avoid DataFrame filtering in loop
    # This is 10-50x faster than filtering DataFrames for each SKU

    # Inventory lookup: sku -> (on_hand, in_transit, unit_cost)
    inv_lookup = {}
    if not inv_df.empty:
        in_transit_col = 'in_transit_qty' if 'in_transit_qty' in inv_df.columns else None
        cost_col = 'last_purchase_price' if 'last_purchase_price' in inv_df.columns else None
        for _, r in inv_df.iterrows():
            inv_lookup[r['sku']] = (
                r.get('on_hand_qty', 0),
                r.get(in_transit_col, 0) if in_transit_col else 0,
                r.get(cost_col, 0) if cost_col else 0
            )

    # Backorder lookup: sku -> backorder_qty
    bo_lookup = {}
    if not backorder_summary.empty:
        bo_lookup = dict(zip(backorder_summary['sku'], backorder_summary['backorder_qty']))

    # Open PO lookup: sku -> open_qty
    po_lookup = {}
    if not open_po_summary.empty:
        po_lookup = dict(zip(open_po_summary['sku'], open_po_summary['open_qty']))

    # Build vendor/product lookup from ORIGINAL inventory_df (before aggregation)
    # This has the vendor and product_name columns
    vendor_product_lookup = {}
    if not inventory_df.empty:
        inv_orig = inventory_df.copy()
        # Find vendor column
        vendor_col = None
        for col in ['POP Last Purchase: Vendor Name', 'vendor', 'Vendor', 'Supplier', 'vendor_name']:
            if col in inv_orig.columns:
                vendor_col = col
                break
        # Find product name column
        name_col = None
        for col in ['product_name', 'Product Name', 'Material Description', 'description']:
            if col in inv_orig.columns:
                name_col = col
                break
        # Find SKU column
        sku_col = None
        for col in ['sku', 'SKU', 'Material Number']:
            if col in inv_orig.columns:
                sku_col = col
                break

        if sku_col:
            inv_orig['_norm_sku'] = normalize_sku_series(inv_orig[sku_col])
            for _, r in inv_orig.drop_duplicates('_norm_sku').iterrows():
                norm_sku = r['_norm_sku']
                vendor = r.get(vendor_col, 'Unknown') if vendor_col else 'Unknown'
                product = r.get(name_col, '') if name_col else ''
                # Clean up vendor - replace NaN with Unknown
                if pd.isna(vendor) or str(vendor).strip() == '':
                    vendor = 'Unknown'
                vendor_product_lookup[norm_sku] = (vendor, product)

    # Master data lookup as fallback: sku -> (vendor, product_name)
    master_lookup = {}
    if not master_df.empty:
        sku_col = None
        vendor_col = None
        name_col = None
        for col in ['sku', 'SKU', 'Material Number', 'SAP Material Code']:
            if col in master_df.columns:
                sku_col = col
                break
        for col in ['POP Last Purchase: Vendor Name', 'vendor', 'Vendor', 'Supplier', 'vendor_name']:
            if col in master_df.columns:
                vendor_col = col
                break
        for col in ['product_name', 'Product Name', 'Material Description', 'description']:
            if col in master_df.columns:
                name_col = col
                break

        if sku_col:
            # Normalize master SKUs once
            master_df_temp = master_df.copy()
            master_df_temp['_norm_sku'] = normalize_sku_series(master_df_temp[sku_col])
            for _, r in master_df_temp.iterrows():
                norm_sku = r['_norm_sku']
                master_lookup[norm_sku] = (
                    r.get(vendor_col, 'Unknown') if vendor_col else 'Unknown',
                    r.get(name_col, '') if name_col else ''
                )

    plan_list = []
    z_score = SERVICE_LEVEL_Z_SCORES.get(service_level, SERVICE_LEVEL_Z_SCORES[95])
    service_level_int = int(service_level * 100) if service_level < 1 else int(service_level)
    lead_time = default_lead_time_days

    # Use itertuples for faster iteration (3-5x faster than iterrows)
    for row in demand_df.itertuples(index=False):
        sku = row.sku

        # Get demand data from named tuple
        daily_demand = getattr(row, 'primary_forecast_daily', None) or getattr(row, 'avg_daily_demand', 0) or 0
        demand_std = getattr(row, 'demand_std', 0) or 0

        # Convert monthly std to daily if needed (for monthly data)
        if demand_std > daily_demand * 10:  # Likely monthly std
            demand_std = demand_std / 30.0

        # Get inventory from lookup (O(1) instead of O(n))
        inv_data = inv_lookup.get(sku, (0, 0, 0))
        on_hand, in_transit, unit_cost = inv_data

        # Get backorders from lookup
        backorder_qty = bo_lookup.get(sku, 0)

        # Get open POs from lookup
        open_po_qty = po_lookup.get(sku, 0)

        # Calculate safety stock
        safety_stock = calculate_safety_stock(
            daily_demand, demand_std, lead_time, service_level_int
        )

        # Calculate reorder point
        reorder_point = calculate_reorder_point(daily_demand, lead_time, safety_stock)

        # Calculate order-up-to level
        order_up_to = calculate_order_up_to_level(
            daily_demand, lead_time, review_period_days, safety_stock
        )

        # Calculate available supply
        available_supply = on_hand + in_transit + open_po_qty

        # Calculate days of supply
        days_of_supply = available_supply / daily_demand if daily_demand > 0 else 999

        # Check if below reorder point
        below_rop = available_supply < reorder_point

        # Calculate suggested order (only if below ROP)
        if below_rop:
            suggested_order = calculate_suggested_order(
                order_up_to, on_hand, in_transit, open_po_qty, backorder_qty
            )
        else:
            suggested_order = 0

        # Calculate priority score
        priority = calculate_priority_score(days_of_supply, backorder_qty, daily_demand)

        # Get vendor and product name - prefer inventory lookup, fallback to master
        vendor, product_name = vendor_product_lookup.get(sku, ('Unknown', ''))

        # Fallback to master data if vendor still Unknown
        if vendor == 'Unknown':
            master_data = master_lookup.get(sku, ('Unknown', ''))
            if master_data[0] != 'Unknown':
                vendor = master_data[0]
            if not product_name and master_data[1]:
                product_name = master_data[1]

        # Use product_name from demand row if available
        row_product_name = getattr(row, 'product_name', None)
        if row_product_name:
            product_name = row_product_name

        plan_list.append({
            'sku': sku,
            'product_name': product_name,
            'vendor': vendor,
            'daily_demand': round(daily_demand, 2),
            'demand_std': round(demand_std, 2),
            'lead_time_days': lead_time,
            'safety_stock': safety_stock,
            'reorder_point': reorder_point,
            'order_up_to_level': order_up_to,
            'on_hand_qty': on_hand,
            'in_transit_qty': in_transit,
            'open_po_qty': open_po_qty,
            'available_supply': available_supply,
            'backorder_qty': backorder_qty,
            'days_of_supply': round(days_of_supply, 1),
            'below_reorder_point': below_rop,
            'suggested_order_qty': suggested_order,
            'unit_cost': unit_cost,
            'order_value': suggested_order * unit_cost if unit_cost > 0 else 0,
            'priority_score': priority
        })

    plan_df = pd.DataFrame(plan_list)

    # Filter to only SKUs below reorder point (per requirements)
    plan_df = plan_df[plan_df['below_reorder_point'] == True]

    # Sort by vendor, then priority (descending), then order value (descending)
    plan_df = plan_df.sort_values(
        by=['vendor', 'priority_score', 'order_value'],
        ascending=[True, False, False]
    )

    logs.append(f"INFO: Generated replenishment plan for {len(plan_df)} SKUs below reorder point")

    # Summary statistics
    total_units = plan_df['suggested_order_qty'].sum()
    total_value = plan_df['order_value'].sum()
    total_skus_with_backorders = (plan_df['backorder_qty'] > 0).sum()

    logs.append(f"INFO: Total suggested order: {total_units:,.0f} units")
    logs.append(f"INFO: Total order value: ${total_value:,.0f}")
    logs.append(f"INFO: SKUs with active backorders: {total_skus_with_backorders}")

    return plan_df


def get_replenishment_summary_by_vendor(plan_df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarize replenishment plan by vendor.

    Args:
        plan_df: Full replenishment plan DataFrame

    Returns:
        DataFrame with vendor-level summary
    """
    if plan_df.empty:
        return pd.DataFrame()

    summary = plan_df.groupby('vendor').agg({
        'sku': 'count',
        'suggested_order_qty': 'sum',
        'order_value': 'sum',
        'backorder_qty': 'sum',
        'priority_score': 'mean'
    }).reset_index()

    summary.columns = ['Vendor', 'SKU Count', 'Total Units', 'Total Value', 'Backorder Units', 'Avg Priority']
    summary = summary.sort_values('Total Value', ascending=False)

    return summary


def get_critical_replenishment_items(plan_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    Get the most critical items that need immediate attention.

    Args:
        plan_df: Full replenishment plan DataFrame
        top_n: Number of top items to return

    Returns:
        DataFrame with top critical items
    """
    if plan_df.empty:
        return pd.DataFrame()

    # Filter for high priority items
    critical = plan_df[plan_df['priority_score'] >= 50].copy()

    # Sort by priority, then by days of supply
    critical = critical.sort_values(
        by=['priority_score', 'days_of_supply'],
        ascending=[False, True]
    )

    return critical.head(top_n)
