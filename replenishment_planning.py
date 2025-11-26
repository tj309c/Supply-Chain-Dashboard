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
DEFAULT_LEAD_TIME_DAYS = 73  # Domestic median lead time
DEFAULT_DOMESTIC_LEAD_TIME = 73  # Domestic vendor median lead time (from PO analysis)
DEFAULT_INTERNATIONAL_LEAD_TIME = 114  # International vendor median lead time (from ATL analysis)
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


def calculate_vendor_lead_times(
    domestic_po_df: pd.DataFrame,
    international_po_df: pd.DataFrame
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Calculate per-vendor average lead times from PO history.

    Uses the date difference between order creation and requested delivery
    for domestic POs, and order date to ETA for international.

    Args:
        domestic_po_df: Domestic vendor PO data
        international_po_df: International (ATL) fulfillment data

    Returns:
        Tuple of (vendor_lead_times dict, sku_lead_times dict)
        - vendor_lead_times: {vendor_name: avg_lead_time_days}
        - sku_lead_times: {sku: avg_lead_time_days}
    """
    vendor_lead_times = {}
    sku_lead_times = {}

    # Process domestic POs
    if not domestic_po_df.empty:
        dom_df = domestic_po_df.copy()

        # Find required columns
        sku_col = None
        for col in ['sku', 'SAP Material Code', 'Material Number']:
            if col in dom_df.columns:
                sku_col = col
                break

        vendor_col = None
        for col in ['vendor_name', 'SAP Supplier - Supplier Description', 'Vendor', 'Supplier']:
            if col in dom_df.columns:
                vendor_col = col
                break

        # Find date columns for lead time calculation
        order_date_col = None
        for col in ['Order Creation Date', 'order_date', 'Created On', 'SAP Purchase Orders - Created On']:
            if col in dom_df.columns:
                order_date_col = col
                break

        delivery_date_col = None
        for col in ['Requested Delivery Date', 'requested_delivery_date', 'Req. Delivery Date']:
            if col in dom_df.columns:
                delivery_date_col = col
                break

        if sku_col and vendor_col and order_date_col and delivery_date_col:
            # Calculate lead time for each PO line
            dom_df['_sku'] = normalize_sku_series(dom_df[sku_col])
            dom_df['_vendor'] = dom_df[vendor_col].fillna('Unknown').astype(str).str.strip()

            # Parse dates
            dom_df['_order_date'] = pd.to_datetime(dom_df[order_date_col], errors='coerce')
            dom_df['_delivery_date'] = pd.to_datetime(dom_df[delivery_date_col], errors='coerce')

            # Calculate lead time in days
            dom_df['_lead_time'] = (dom_df['_delivery_date'] - dom_df['_order_date']).dt.days

            # Filter valid lead times (positive and reasonable: 1-365 days)
            valid_lt = dom_df[(dom_df['_lead_time'] > 0) & (dom_df['_lead_time'] <= 365)]

            if not valid_lt.empty:
                # Per-vendor average
                vendor_avg = valid_lt.groupby('_vendor')['_lead_time'].median()
                vendor_lead_times = vendor_avg.to_dict()

                # Per-SKU average
                sku_avg = valid_lt.groupby('_sku')['_lead_time'].median()
                sku_lead_times = sku_avg.to_dict()

    # Process international POs (ATL data)
    if not international_po_df.empty:
        intl_df = international_po_df.copy()

        # Find required columns
        sku_col = None
        for col in ['sku', 'SAP Item Material Code']:
            if col in intl_df.columns:
                sku_col = col
                break

        vendor_col = None
        for col in ['vendor_name', 'Shipping Factory Name', 'Factory']:
            if col in intl_df.columns:
                vendor_col = col
                break

        # ATL has Order Date and ETA DC
        order_date_col = None
        for col in ['Order Date', 'order_date']:
            if col in intl_df.columns:
                order_date_col = col
                break

        eta_col = None
        for col in ['ETA DC', 'eta_dc', 'Expected Delivery']:
            if col in intl_df.columns:
                eta_col = col
                break

        if sku_col and vendor_col and order_date_col and eta_col:
            intl_df['_sku'] = normalize_sku_series(intl_df[sku_col])
            intl_df['_vendor'] = intl_df[vendor_col].fillna('Unknown').astype(str).str.strip()

            intl_df['_order_date'] = pd.to_datetime(intl_df[order_date_col], errors='coerce')
            intl_df['_eta_date'] = pd.to_datetime(intl_df[eta_col], errors='coerce')

            intl_df['_lead_time'] = (intl_df['_eta_date'] - intl_df['_order_date']).dt.days

            valid_lt = intl_df[(intl_df['_lead_time'] > 0) & (intl_df['_lead_time'] <= 365)]

            if not valid_lt.empty:
                # Add international vendors (with suffix to differentiate)
                intl_vendor_avg = valid_lt.groupby('_vendor')['_lead_time'].median()
                for vendor, lt in intl_vendor_avg.items():
                    vendor_lead_times[f"{vendor} (International)"] = lt

                # Add international SKUs to sku_lead_times (if not already present)
                intl_sku_avg = valid_lt.groupby('_sku')['_lead_time'].median()
                for sku, lt in intl_sku_avg.items():
                    if sku not in sku_lead_times:
                        sku_lead_times[sku] = lt

    return vendor_lead_times, sku_lead_times


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
        default_lead_time_days: Default lead time for planning horizon (default 90)
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
    # Note: ATL data is pre-processed by load_atl_fulfillment() which already:
    #   - Filters for non-delivered shipments
    #   - Aggregates by SKU
    #   - Has columns: sku, open_qty, expected_delivery_date, vendor_name, status
    intl_open = pd.DataFrame()
    if not international_po_df.empty:
        intl_df = international_po_df.copy()

        # Check if data is pre-processed (has 'sku' and 'open_qty')
        if 'sku' in intl_df.columns and 'open_qty' in intl_df.columns:
            # Data is already processed by load_atl_fulfillment
            intl_df['sku'] = normalize_sku_series(intl_df['sku'])
            intl_df['open_qty'] = pd.to_numeric(intl_df['open_qty'], errors='coerce').fillna(0)

            # Already filtered for open shipments, just aggregate by SKU
            intl_open = intl_df.groupby('sku').agg({
                'open_qty': 'sum'
            }).reset_index()
            intl_open['source'] = 'International'
            logs.append(f"INFO: Found {len(intl_open)} SKUs with {intl_open['open_qty'].sum():,.0f} units in international transit")
        else:
            # Fallback for raw ATL data (legacy support)
            sku_col = 'SAP Item Material Code' if 'SAP Item Material Code' in intl_df.columns else None
            qty_col = None
            for col in intl_df.columns:
                if 'good issue' in col.lower() and 'qty' in col.lower():
                    qty_col = col
                    break

            if sku_col and qty_col and 'ON TIME TRANSIT' in intl_df.columns:
                intl_df['sku'] = normalize_sku_series(intl_df[sku_col])
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
                    logs.append(f"INFO: Found {len(intl_open)} SKUs with open international shipments (raw data)")

    # Combine domestic and international
    if not domestic_open.empty or not intl_open.empty:
        combined_pos = pd.concat([domestic_open, intl_open], ignore_index=True)
        open_po_summary = combined_pos.groupby('sku').agg({
            'open_qty': 'sum'
        }).reset_index()

    # ===== STEP 6: Calculate lead times (cascading: SKU → Vendor → Overall) =====
    logs.append("INFO: Calculating lead times from PO history...")

    # Calculate per-vendor and per-SKU lead times from PO data
    vendor_lead_times, sku_lead_times = calculate_vendor_lead_times(
        domestic_po_df, international_po_df
    )
    logs.append(f"INFO: Calculated lead times for {len(vendor_lead_times)} vendors and {len(sku_lead_times)} SKUs")

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

    # ===== BUILD VENDOR LOOKUP (cascading priority) =====
    # Priority 1: Domestic Vendor POs (100% vendor coverage for SKUs with POs)
    # Priority 2: Master Data (26% coverage but more SKUs)
    # Priority 3: Inventory data (fallback)

    # Priority 1: Vendor PO lookup - most accurate for SKUs with active POs
    vendor_po_lookup = {}
    if not domestic_po_df.empty:
        po_df_temp = domestic_po_df.copy()
        # Find SKU column
        sku_col = None
        for col in ['sku', 'SAP Material Code', 'Material Number']:
            if col in po_df_temp.columns:
                sku_col = col
                break
        # Find vendor column
        vendor_col = None
        for col in ['vendor_name', 'SAP Supplier - Supplier Description', 'Vendor', 'Supplier']:
            if col in po_df_temp.columns:
                vendor_col = col
                break

        if sku_col and vendor_col:
            po_df_temp['_norm_sku'] = normalize_sku_series(po_df_temp[sku_col])
            # Get unique SKU -> vendor mapping (use most recent or most common)
            for _, r in po_df_temp.drop_duplicates('_norm_sku').iterrows():
                norm_sku = r['_norm_sku']
                vendor = r.get(vendor_col, 'Unknown')
                if pd.isna(vendor) or str(vendor).strip() in ['', 'nan', 'None']:
                    vendor = 'Unknown'
                else:
                    vendor = str(vendor).strip()
                if vendor != 'Unknown':
                    vendor_po_lookup[norm_sku] = vendor
            logs.append(f"INFO: Built vendor lookup from PO data: {len(vendor_po_lookup)} SKUs with vendor names")

    # Priority 2: Master data lookup
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
        for col in ['product_name', 'Product Name', 'Material Description', 'description', 'sku_description']:
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

    # Use itertuples for faster iteration (3-5x faster than iterrows)
    for row in demand_df.itertuples(index=False):
        sku = row.sku

        # Get demand data from named tuple
        # Priority: exp_smooth_seasonal (best) > exp_smooth > primary_forecast_daily > avg_daily_demand
        daily_demand = (
            getattr(row, 'exp_smooth_seasonal', None) or
            getattr(row, 'exp_smooth', None) or
            getattr(row, 'primary_forecast_daily', None) or
            getattr(row, 'avg_daily_demand', 0) or 0
        )
        demand_std = getattr(row, 'demand_std', 0) or 0

        # Convert monthly std to daily if needed (for monthly data)
        if demand_std > daily_demand * 10:  # Likely monthly std
            demand_std = demand_std / 30.0

        # Get inventory from lookup (O(1) instead of O(n))
        # inv_lookup stores (on_hand, in_transit_qty, unit_cost)
        inv_data = inv_lookup.get(sku, (0, 0, 0))
        on_hand, in_transit, unit_cost = inv_data

        # Get backorders from lookup
        backorder_qty = bo_lookup.get(sku, 0)

        # Get open POs from lookup (includes both domestic + international)
        # This represents all incoming supply (open orders not yet received)
        open_po_qty = po_lookup.get(sku, 0)

        # ===== CASCADING LEAD TIME: SKU → Vendor → Overall (domestic 73 / intl 114) =====
        # Get vendor first (needed for vendor-level lead time lookup)
        vendor = vendor_po_lookup.get(sku, None)
        if not vendor:
            master_data = master_lookup.get(sku, ('Unknown', ''))
            vendor = master_data[0] if master_data[0] != 'Unknown' else 'Unknown'

        # Determine lead time using cascade:
        # 1. Per-SKU lead time (if available from PO history)
        # 2. Per-Vendor lead time (if available)
        # 3. Overall fallback (domestic 73 / international 114)
        lead_time = None

        # Priority 1: Per-SKU lead time
        if sku in sku_lead_times:
            lead_time = sku_lead_times[sku]

        # Priority 2: Per-Vendor lead time
        if lead_time is None and vendor and vendor != 'Unknown':
            if vendor in vendor_lead_times:
                lead_time = vendor_lead_times[vendor]
            # Also check international variant
            elif f"{vendor} (International)" in vendor_lead_times:
                lead_time = vendor_lead_times[f"{vendor} (International)"]

        # Priority 3: Overall fallback based on source
        if lead_time is None:
            # Check if SKU has international PO (use 114) or domestic (use 73)
            # For now, use default (which is 73 for domestic)
            lead_time = default_lead_time_days

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
        # Formula: On Hand + Open POs (domestic + international)
        # Note: We use open_po_qty which is the sum of open domestic vendor POs
        # and open international shipments (ATL). We do NOT add inventory in_transit
        # separately as that could double-count with the open POs.
        available_supply = on_hand + open_po_qty

        # Calculate days of supply
        days_of_supply = available_supply / daily_demand if daily_demand > 0 else 999

        # Check if below reorder point
        below_rop = available_supply < reorder_point

        # Calculate suggested order (only if below ROP)
        if below_rop:
            # Pass 0 for in_transit since we're using open_po_qty from vendor POs
            suggested_order = calculate_suggested_order(
                order_up_to, on_hand, 0, open_po_qty, backorder_qty
            )
        else:
            suggested_order = 0

        # Calculate priority score
        priority = calculate_priority_score(days_of_supply, backorder_qty, daily_demand)

        # Get vendor using cascading priority:
        # 1. Vendor PO data (most accurate for SKUs with active POs)
        # 2. Master data (broader coverage)
        vendor = vendor_po_lookup.get(sku, None)

        if not vendor:
            # Fallback to master data
            master_data = master_lookup.get(sku, ('Unknown', ''))
            vendor = master_data[0] if master_data[0] != 'Unknown' else 'Unknown'

        # Get product name from master data
        product_name = ''
        master_data = master_lookup.get(sku, ('Unknown', ''))
        if master_data[1]:
            product_name = master_data[1]

        # Use product_name or sku_description from demand row if available (overrides master)
        row_product_name = getattr(row, 'product_name', None) or getattr(row, 'sku_description', None)
        if row_product_name and str(row_product_name) not in ['', 'nan', 'None', 'Unknown']:
            product_name = str(row_product_name)

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
            # Keep the actual in-transit quantity for display, but when
            # calculating suggested orders we intentionally pass 0 to
            # calculate_suggested_order to avoid double-counting open PO lines.
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
