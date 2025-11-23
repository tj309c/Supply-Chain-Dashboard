"""
Stockout Prediction Module

Identifies SKUs at risk of going on backorder BEFORE it happens by calculating:
- Daily demand rates from historical deliveries
- Safety stock and reorder points
- Days until stockout
- Stockout risk scoring (Critical/High/Moderate/Low)
- PO coverage gap analysis

Key Features:
- Multiple time window demand calculations (30/60/90 days)
- Statistical safety stock calculation (Z-score based)
- Vendor lead time and reliability integration
- Proactive alerts for critical at-risk items
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st

TODAY = pd.to_datetime(datetime.now().date())

# Service level targets (Z-scores for normal distribution)
SERVICE_LEVEL_TARGETS = {
    95: 1.65,  # 95% service level = Z-score 1.65
    98: 2.05,  # 98% service level = Z-score 2.05
    99: 2.33   # 99% service level = Z-score 2.33
}


@st.cache_data(show_spinner="Predicting stockout risk...")
def predict_stockout_risk(inventory_df, deliveries_df, vendor_pos_df, vendor_performance_df,
                          service_level=95, demand_window_days=90):
    """
    Identify SKUs at risk of stockout before backorders occur

    Args:
        inventory_df: Current inventory levels from load_inventory_data()
        deliveries_df: Historical deliveries (unified) from load_deliveries_unified()
        vendor_pos_df: Vendor PO data from load_vendor_pos()
        vendor_performance_df: Vendor performance metrics from load_vendor_performance()
        service_level: Target service level percentage (95, 98, or 99)
        demand_window_days: Days to look back for demand calculation (default 90)

    Returns:
        tuple: (logs, stockout_risk_df)
        - logs: List of processing messages
        - stockout_risk_df: DataFrame with stockout risk predictions sorted by days_until_stockout
    """
    logs = []
    start_time = datetime.now()
    logs.append("--- Stockout Prediction Engine ---")

    if inventory_df.empty:
        logs.append("WARNING: No inventory data provided")
        return logs, pd.DataFrame()

    if deliveries_df.empty:
        logs.append("WARNING: No delivery data provided - cannot calculate demand")
        return logs, pd.DataFrame()

    logs.append(f"INFO: Analyzing {len(inventory_df)} SKUs for stockout risk")
    logs.append(f"INFO: Target service level: {service_level}%")
    logs.append(f"INFO: Demand window: {demand_window_days} days")

    # ===== STEP 1: Calculate Daily Demand from Deliveries =====
    logs.append("INFO: Calculating daily demand from historical deliveries...")

    # Process deliveries_df: handle both unified format (raw columns) and processed format (renamed columns)
    if 'ship_date' not in deliveries_df.columns:
        # Unified format - need to rename columns
        logs.append("INFO: Processing unified deliveries format (renaming columns)...")
        deliveries_processed = deliveries_df[["Item - SAP Model Code", "Delivery Creation Date: Date", "Deliveries - TOTAL Goods Issue Qty"]].copy()
        deliveries_processed = deliveries_processed.rename(columns={
            "Item - SAP Model Code": "sku",
            "Delivery Creation Date: Date": "ship_date",
            "Deliveries - TOTAL Goods Issue Qty": "units_issued"
        })

        # Convert ship_date to datetime
        deliveries_processed['ship_date'] = pd.to_datetime(deliveries_processed['ship_date'], format='%m/%d/%y', errors='coerce')
        deliveries_processed['units_issued'] = pd.to_numeric(deliveries_processed['units_issued'], errors='coerce').fillna(0)
        deliveries_processed.dropna(subset=['ship_date'], inplace=True)
    else:
        # Already processed format - use as-is
        logs.append("INFO: Using pre-processed deliveries format...")
        deliveries_processed = deliveries_df.copy()

    # Filter deliveries to demand window
    demand_cutoff_date = TODAY - timedelta(days=demand_window_days)
    recent_deliveries = deliveries_processed[
        deliveries_processed['ship_date'] >= demand_cutoff_date
    ].copy()

    logs.append(f"INFO: Found {len(recent_deliveries)} deliveries in last {demand_window_days} days")

    # Calculate demand per SKU
    demand_by_sku = recent_deliveries.groupby('sku').agg({
        'units_issued': ['sum', 'mean', 'std', 'count'],
        'ship_date': ['min', 'max']
    }).reset_index()

    demand_by_sku.columns = ['sku', 'total_units_shipped', 'avg_order_size', 'std_order_size',
                              'order_count', 'first_ship_date', 'last_ship_date']

    # Calculate daily demand rate
    demand_by_sku['days_with_demand'] = (
        pd.to_datetime(demand_by_sku['last_ship_date']) -
        pd.to_datetime(demand_by_sku['first_ship_date'])
    ).dt.days + 1

    demand_by_sku['daily_demand'] = demand_by_sku['total_units_shipped'] / demand_window_days
    demand_by_sku['daily_demand_std'] = demand_by_sku['std_order_size'] / np.sqrt(demand_by_sku['order_count'])
    demand_by_sku['daily_demand_std'] = demand_by_sku['daily_demand_std'].fillna(
        demand_by_sku['daily_demand'] * 0.3  # Assume 30% variability if no std available
    )

    logs.append(f"INFO: Calculated demand for {len(demand_by_sku)} SKUs with historical shipments")

    # ===== STEP 2: Merge Inventory with Demand =====
    logs.append("INFO: Merging inventory data with demand calculations...")

    # Select columns from inventory - category is optional
    inventory_cols = ['sku', 'on_hand_qty', 'in_transit_qty']
    if 'category' in inventory_df.columns:
        inventory_cols.append('category')
        logs.append("INFO: Category column found in inventory data")
    else:
        logs.append("WARNING: Category column not found - stockout analysis will be SKU-level only")

    stockout_risk = pd.merge(
        inventory_df[inventory_cols],
        demand_by_sku[['sku', 'daily_demand', 'daily_demand_std', 'order_count', 'days_with_demand']],
        on='sku',
        how='left'
    )

    # Fill missing demand with 0 (no historical demand)
    stockout_risk['daily_demand'] = stockout_risk['daily_demand'].fillna(0)
    stockout_risk['daily_demand_std'] = stockout_risk['daily_demand_std'].fillna(0)
    stockout_risk['order_count'] = stockout_risk['order_count'].fillna(0)

    # ===== STEP 3: Get Vendor Lead Times =====
    logs.append("INFO: Determining vendor lead times per SKU...")

    # Match SKUs to vendors via open POs
    if not vendor_pos_df.empty:
        # Get primary vendor and lead time per SKU (from most recent PO)
        vendor_lead_times = vendor_pos_df[vendor_pos_df['is_open'] == True].groupby('sku').agg({
            'vendor_name': 'first',
            'po_create_date': 'max'
        }).reset_index()

        # Merge with vendor performance to get avg lead time
        if not vendor_performance_df.empty:
            vendor_lead_times = pd.merge(
                vendor_lead_times,
                vendor_performance_df[['vendor_name', 'avg_actual_lead_time', 'avg_delay_days']],
                on='vendor_name',
                how='left'
            )
        else:
            vendor_lead_times['avg_actual_lead_time'] = 30  # Default 30 days
            vendor_lead_times['avg_delay_days'] = 7  # Default 7 days delay

        stockout_risk = pd.merge(
            stockout_risk,
            vendor_lead_times[['sku', 'vendor_name', 'avg_actual_lead_time', 'avg_delay_days']],
            on='sku',
            how='left'
        )
    else:
        stockout_risk['vendor_name'] = None
        stockout_risk['avg_actual_lead_time'] = 30
        stockout_risk['avg_delay_days'] = 7

    # Fill missing lead times with defaults
    stockout_risk['avg_actual_lead_time'] = stockout_risk['avg_actual_lead_time'].fillna(30)
    stockout_risk['avg_delay_days'] = stockout_risk['avg_delay_days'].fillna(7)

    # ===== STEP 4: Calculate Safety Stock =====
    logs.append("INFO: Calculating safety stock using statistical methods...")

    # Safety Stock = Z-score × √(Avg Lead Time) × StdDev(Daily Demand)
    z_score = SERVICE_LEVEL_TARGETS.get(service_level, 1.65)

    stockout_risk['safety_stock'] = (
        z_score *
        np.sqrt(stockout_risk['avg_actual_lead_time']) *
        stockout_risk['daily_demand_std']
    )

    # Round safety stock to whole units
    stockout_risk['safety_stock'] = stockout_risk['safety_stock'].round(0).astype(int)

    # ===== STEP 5: Calculate Reorder Point =====
    logs.append("INFO: Computing reorder points per SKU...")

    # Reorder Point = (Daily Demand × Lead Time) + Safety Stock
    stockout_risk['reorder_point'] = (
        (stockout_risk['daily_demand'] * stockout_risk['avg_actual_lead_time']) +
        stockout_risk['safety_stock']
    )

    stockout_risk['reorder_point'] = stockout_risk['reorder_point'].round(0).astype(int)

    # ===== STEP 6: Calculate Days Until Stockout =====
    logs.append("INFO: Predicting days until stockout...")

    # Available stock = on_hand + in_transit
    stockout_risk['available_stock'] = stockout_risk['on_hand_qty'] + stockout_risk['in_transit_qty']

    # Days until stockout = Available Stock / Daily Demand
    stockout_risk['days_until_stockout'] = np.where(
        stockout_risk['daily_demand'] > 0,
        stockout_risk['available_stock'] / stockout_risk['daily_demand'],
        np.inf  # Infinite if no demand
    )

    # ===== STEP 7: Calculate Stock Coverage Gap =====
    logs.append("INFO: Analyzing stock coverage vs reorder point...")

    # Gap = Available Stock - Reorder Point (negative = below reorder point)
    stockout_risk['stock_gap'] = stockout_risk['available_stock'] - stockout_risk['reorder_point']

    # Below reorder point flag
    stockout_risk['below_reorder_point'] = stockout_risk['stock_gap'] < 0

    # ===== STEP 8: Check PO Coverage =====
    logs.append("INFO: Checking PO coverage for at-risk SKUs...")

    if not vendor_pos_df.empty:
        # Get total open PO quantity per SKU
        open_po_qty = vendor_pos_df[vendor_pos_df['is_open'] == True].groupby('sku')['open_qty'].sum().reset_index()
        open_po_qty.columns = ['sku', 'po_open_qty']

        stockout_risk = pd.merge(
            stockout_risk,
            open_po_qty,
            on='sku',
            how='left'
        )
        stockout_risk['po_open_qty'] = stockout_risk['po_open_qty'].fillna(0)

        # Has PO coverage flag
        stockout_risk['has_po_coverage'] = stockout_risk['po_open_qty'] > 0

        # Stock with PO = available stock + po open qty
        stockout_risk['stock_with_po'] = stockout_risk['available_stock'] + stockout_risk['po_open_qty']

        # Days until stockout with PO coverage
        stockout_risk['days_until_stockout_with_po'] = np.where(
            stockout_risk['daily_demand'] > 0,
            stockout_risk['stock_with_po'] / stockout_risk['daily_demand'],
            np.inf
        )
    else:
        stockout_risk['po_open_qty'] = 0
        stockout_risk['has_po_coverage'] = False
        stockout_risk['stock_with_po'] = stockout_risk['available_stock']
        stockout_risk['days_until_stockout_with_po'] = stockout_risk['days_until_stockout']

    # ===== STEP 9: Calculate Risk Score =====
    logs.append("INFO: Calculating stockout risk scores...")

    def calculate_risk_level(row):
        """Determine risk level based on days until stockout"""
        days = row['days_until_stockout']

        if days == np.inf or row['daily_demand'] == 0:
            return 'No Demand'
        elif days <= 0:
            return 'Out of Stock'
        elif days <= 7:
            return 'Critical (0-7 days)'
        elif days <= 14:
            return 'High (7-14 days)'
        elif days <= 30:
            return 'Moderate (14-30 days)'
        else:
            return 'Low (30+ days)'

    stockout_risk['risk_level'] = stockout_risk.apply(calculate_risk_level, axis=1)

    # Numeric risk score (0-100, higher = more risk)
    def calculate_risk_score(row):
        """Calculate numeric risk score"""
        days = row['days_until_stockout']

        if days == np.inf or row['daily_demand'] == 0:
            return 0
        elif days <= 0:
            return 100
        elif days <= 7:
            return 90
        elif days <= 14:
            return 70
        elif days <= 30:
            return 50
        elif days <= 60:
            return 30
        else:
            return 10

    stockout_risk['risk_score'] = stockout_risk.apply(calculate_risk_score, axis=1)

    # ===== STEP 10: Flag High-Risk Items =====
    logs.append("INFO: Identifying high-risk items requiring immediate action...")

    # High risk = (Critical or High risk level) AND (below reorder point OR no PO coverage)
    stockout_risk['is_high_risk'] = (
        (stockout_risk['risk_level'].isin(['Critical (0-7 days)', 'High (7-14 days)', 'Out of Stock'])) &
        (stockout_risk['below_reorder_point'] | ~stockout_risk['has_po_coverage'])
    )

    high_risk_count = stockout_risk['is_high_risk'].sum()
    logs.append(f"WARNING: {high_risk_count} high-risk SKUs identified requiring immediate action")

    # ===== STEP 11: Sort and Filter Results =====
    logs.append("INFO: Sorting results by risk priority...")

    # Sort by risk score (highest first), then days until stockout (lowest first)
    stockout_risk = stockout_risk.sort_values(
        ['risk_score', 'days_until_stockout'],
        ascending=[False, True]
    )

    # Count by risk level
    risk_counts = stockout_risk['risk_level'].value_counts()
    for level, count in risk_counts.items():
        logs.append(f"INFO: {count} SKUs at {level} risk")

    # ===== STEP 12: Summary Metrics =====
    total_time = (datetime.now() - start_time).total_seconds()
    logs.append(f"INFO: Stockout prediction completed in {total_time:.2f} seconds")
    logs.append(f"INFO: Analyzed {len(stockout_risk)} SKUs")
    logs.append(f"INFO: {high_risk_count} SKUs require immediate procurement action")

    return logs, stockout_risk


def get_stockout_summary_metrics(stockout_risk_df):
    """
    Calculate summary metrics for stockout risk analysis

    Args:
        stockout_risk_df: Stockout risk dataframe from predict_stockout_risk()

    Returns:
        dict: Summary metrics for display
    """
    if stockout_risk_df.empty:
        return {}

    total_skus = len(stockout_risk_df)

    # Count by risk level
    critical_count = len(stockout_risk_df[stockout_risk_df['risk_level'] == 'Critical (0-7 days)'])
    high_count = len(stockout_risk_df[stockout_risk_df['risk_level'] == 'High (7-14 days)'])
    moderate_count = len(stockout_risk_df[stockout_risk_df['risk_level'] == 'Moderate (14-30 days)'])
    out_of_stock_count = len(stockout_risk_df[stockout_risk_df['risk_level'] == 'Out of Stock'])

    # High-risk items
    high_risk_count = stockout_risk_df['is_high_risk'].sum()

    # Below reorder point
    below_reorder_count = stockout_risk_df['below_reorder_point'].sum()

    # Without PO coverage
    no_po_count = (~stockout_risk_df['has_po_coverage']).sum()

    # Average days until stockout (excluding infinite)
    finite_days = stockout_risk_df[stockout_risk_df['days_until_stockout'] != np.inf]['days_until_stockout']
    avg_days_until_stockout = finite_days.mean() if not finite_days.empty else 0

    return {
        'total_skus': total_skus,
        'critical_count': critical_count,
        'high_count': high_count,
        'moderate_count': moderate_count,
        'out_of_stock_count': out_of_stock_count,
        'high_risk_count': high_risk_count,
        'below_reorder_count': below_reorder_count,
        'no_po_count': no_po_count,
        'avg_days_until_stockout': avg_days_until_stockout
    }


def get_critical_at_risk_items(stockout_risk_df, top_n=20):
    """
    Get the most critical at-risk items

    Args:
        stockout_risk_df: Stockout risk dataframe
        top_n: Number of top items to return

    Returns:
        DataFrame: Critical at-risk items sorted by risk priority
    """
    if stockout_risk_df.empty:
        return pd.DataFrame()

    # Filter to high-risk items
    critical_items = stockout_risk_df[stockout_risk_df['is_high_risk'] == True].copy()

    # Sort by risk score (highest first) and days until stockout (lowest first)
    critical_items = critical_items.sort_values(
        ['risk_score', 'days_until_stockout'],
        ascending=[False, True]
    )

    return critical_items.head(top_n)


def get_reorder_recommendations(stockout_risk_df, risk_threshold='Moderate'):
    """
    Get SKUs that should be reordered now

    Args:
        stockout_risk_df: Stockout risk dataframe
        risk_threshold: Minimum risk level to include ('Critical', 'High', or 'Moderate')

    Returns:
        DataFrame: SKUs recommended for immediate reorder
    """
    if stockout_risk_df.empty:
        return pd.DataFrame()

    # Define risk levels to include based on threshold
    if risk_threshold == 'Critical':
        risk_levels = ['Critical (0-7 days)', 'Out of Stock']
    elif risk_threshold == 'High':
        risk_levels = ['Critical (0-7 days)', 'High (7-14 days)', 'Out of Stock']
    else:  # Moderate
        risk_levels = ['Critical (0-7 days)', 'High (7-14 days)', 'Moderate (14-30 days)', 'Out of Stock']

    # Filter to specified risk levels and below reorder point
    reorder_needed = stockout_risk_df[
        (stockout_risk_df['risk_level'].isin(risk_levels)) &
        (stockout_risk_df['below_reorder_point'] == True)
    ].copy()

    # Calculate recommended order quantity (to reach reorder point + safety buffer)
    reorder_needed['recommended_order_qty'] = (
        reorder_needed['reorder_point'] -
        reorder_needed['available_stock'] +
        (reorder_needed['daily_demand'] * 14)  # 2 weeks buffer
    ).round(0).astype(int)

    # Ensure minimum order quantity of 1
    reorder_needed['recommended_order_qty'] = reorder_needed['recommended_order_qty'].clip(lower=1)

    return reorder_needed.sort_values(['risk_score', 'days_until_stockout'], ascending=[False, True])
