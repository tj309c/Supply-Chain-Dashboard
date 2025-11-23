"""
Backorder Relief Analysis Module

Matches backorders to vendor purchase orders and calculates expected relief dates
accounting for vendor reliability and historical performance.

Key Features:
- PO-to-backorder matching by SKU
- Vendor-adjusted delivery dates based on historical performance
- Relief confidence scoring (High/Medium/Low)
- Days until relief calculation
- PO coverage gap identification
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st

TODAY = pd.to_datetime(datetime.now().date())


@st.cache_data(show_spinner="Calculating backorder relief dates...")
def calculate_backorder_relief_dates(backorder_df, vendor_pos_df, vendor_performance_df):
    """
    Match backorders to purchase orders and calculate expected relief dates

    Args:
        backorder_df: Backorder data with columns: sales_order, sku, customer_name, backorder_qty, days_on_backorder, order_date
        vendor_pos_df: Vendor PO data with columns: po_number, sku, vendor_name, po_create_date, expected_delivery_date, ordered_qty, open_qty, is_open
        vendor_performance_df: Vendor performance metrics with columns: vendor_name, otif_pct, avg_delay_days, total_receipts

    Returns:
        tuple: (logs, backorder_relief_df)
        - logs: List of processing messages
        - backorder_relief_df: Enhanced backorder dataframe with relief information
    """
    logs = []
    start_time = datetime.now()
    logs.append("--- Backorder Relief Analysis Engine ---")

    if backorder_df.empty:
        logs.append("WARNING: No backorder data provided")
        return logs, pd.DataFrame()

    if vendor_pos_df.empty:
        logs.append("WARNING: No vendor PO data provided - cannot calculate relief dates")
        # Return backorders with no PO coverage flags
        result = backorder_df.copy()
        result['has_po_coverage'] = False
        result['relieving_po_number'] = None
        result['po_expected_delivery'] = None
        result['vendor_name'] = None
        result['vendor_otif_pct'] = 0.0
        result['vendor_avg_delay_days'] = 0
        result['vendor_adjusted_delivery_date'] = None
        result['days_until_relief'] = np.inf
        result['relief_confidence'] = 'No PO'
        return logs, result

    logs.append(f"INFO: Processing {len(backorder_df)} backorders against {len(vendor_pos_df)} PO lines")

    # ===== STEP 1: Prepare Data =====
    logs.append("INFO: Preparing backorder and PO data...")

    # Create working copy
    backorder_relief = backorder_df.copy()

    # Filter to open POs only (not yet fully received)
    open_pos = vendor_pos_df[vendor_pos_df['is_open'] == True].copy()
    logs.append(f"INFO: Found {len(open_pos)} open PO lines")

    # Ensure expected_delivery_date is datetime
    if 'expected_delivery_date' in open_pos.columns:
        open_pos['expected_delivery_date'] = pd.to_datetime(open_pos['expected_delivery_date'], errors='coerce')
    else:
        logs.append("ERROR: No expected_delivery_date in PO data - cannot calculate relief dates without real expected delivery dates")
        logs.append("INFO: Relief analysis requires expected_delivery_date column in vendor PO data")
        # Return empty result - NO FAKE DATA
        result = backorder_df.copy()
        result['has_po_coverage'] = False
        result['relieving_po_number'] = None
        result['po_expected_delivery'] = None
        result['vendor_name'] = None
        result['vendor_otif_pct'] = 0.0
        result['vendor_avg_delay_days'] = 0
        result['vendor_adjusted_delivery_date'] = None
        result['days_until_relief'] = np.inf
        result['relief_confidence'] = 'No PO'
        result['is_high_risk'] = True
        result['relief_bucket'] = 'No PO'
        return logs, result

    # ===== STEP 2: Match Backorders to POs by SKU =====
    logs.append("INFO: Matching backorders to purchase orders by SKU...")

    # Group open POs by SKU and get earliest expected delivery
    po_by_sku = open_pos.groupby('sku').agg({
        'po_number': 'first',  # Take first PO (could be enhanced to prioritize by date)
        'vendor_name': 'first',
        'expected_delivery_date': 'min',  # Earliest expected delivery
        'open_qty': 'sum',  # Total open quantity across all POs for this SKU
        'ordered_qty': 'sum'
    }).reset_index()

    po_by_sku.columns = ['sku', 'relieving_po_number', 'vendor_name', 'po_expected_delivery',
                          'total_open_qty', 'total_ordered_qty']

    logs.append(f"INFO: Found POs for {len(po_by_sku)} unique SKUs")

    # Merge backorders with PO information
    backorder_relief = pd.merge(
        backorder_relief,
        po_by_sku,
        on='sku',
        how='left'
    )

    # Flag whether backorder has PO coverage
    backorder_relief['has_po_coverage'] = backorder_relief['relieving_po_number'].notna()

    po_coverage_count = backorder_relief['has_po_coverage'].sum()
    po_coverage_pct = (po_coverage_count / len(backorder_relief) * 100) if len(backorder_relief) > 0 else 0
    logs.append(f"INFO: {po_coverage_count} of {len(backorder_relief)} backorders ({po_coverage_pct:.1f}%) have PO coverage")

    # ===== STEP 3: Merge Vendor Performance Data =====
    logs.append("INFO: Merging vendor performance metrics...")

    if not vendor_performance_df.empty:
        # Merge vendor performance
        backorder_relief = pd.merge(
            backorder_relief,
            vendor_performance_df[['vendor_name', 'otif_pct', 'avg_delay_days']],
            on='vendor_name',
            how='left'
        )

        # Fill missing vendor performance with defaults (assume poor performance if unknown)
        backorder_relief['vendor_otif_pct'] = backorder_relief['otif_pct'].fillna(50.0)
        backorder_relief['vendor_avg_delay_days'] = backorder_relief['avg_delay_days'].fillna(7)
        backorder_relief = backorder_relief.drop(columns=['otif_pct', 'avg_delay_days'], errors='ignore')
    else:
        logs.append("WARNING: No vendor performance data - using default values")
        backorder_relief['vendor_otif_pct'] = 50.0
        backorder_relief['vendor_avg_delay_days'] = 7

    # ===== STEP 4: Calculate Vendor-Adjusted Delivery Dates =====
    logs.append("INFO: Calculating vendor-adjusted delivery dates...")

    # Adjust expected delivery by vendor's historical delay
    backorder_relief['vendor_adjusted_delivery_date'] = backorder_relief.apply(
        lambda row: row['po_expected_delivery'] + timedelta(days=int(row['vendor_avg_delay_days']))
        if pd.notna(row['po_expected_delivery']) else None,
        axis=1
    )

    # ===== STEP 5: Calculate Days Until Relief =====
    logs.append("INFO: Calculating days until relief...")

    backorder_relief['days_until_relief'] = backorder_relief.apply(
        lambda row: (row['vendor_adjusted_delivery_date'] - TODAY).days
        if pd.notna(row['vendor_adjusted_delivery_date']) else np.inf,
        axis=1
    )

    # ===== STEP 6: Calculate Relief Confidence =====
    logs.append("INFO: Calculating relief confidence scores...")

    def calculate_confidence(row):
        """Calculate relief confidence based on vendor OTIF and PO coverage"""
        if not row['has_po_coverage']:
            return 'No PO'

        otif = row['vendor_otif_pct']

        if otif >= 90:
            return 'High'
        elif otif >= 75:
            return 'Medium'
        else:
            return 'Low'

    backorder_relief['relief_confidence'] = backorder_relief.apply(calculate_confidence, axis=1)

    # Count by confidence level
    confidence_counts = backorder_relief['relief_confidence'].value_counts()
    for conf_level, count in confidence_counts.items():
        logs.append(f"INFO: {count} backorders with {conf_level} confidence relief")

    # ===== STEP 7: Identify High-Risk Backorders =====
    logs.append("INFO: Identifying high-risk backorders...")

    # High risk = No PO OR Low confidence (poor vendor OTIF)
    backorder_relief['is_high_risk'] = (
        (~backorder_relief['has_po_coverage']) |
        (backorder_relief['relief_confidence'] == 'Low')
    )

    high_risk_count = backorder_relief['is_high_risk'].sum()
    logs.append(f"WARNING: {high_risk_count} high-risk backorders identified (no PO or unreliable vendor)")

    # ===== STEP 8: Calculate Relief Time Buckets =====
    logs.append("INFO: Categorizing backorders by relief timeline...")

    def get_relief_bucket(days):
        """Categorize relief timeline into buckets"""
        if pd.isna(days) or np.isinf(days):
            return 'No PO'
        elif days < 0:
            return 'Overdue'
        elif days <= 7:
            return 'This Week'
        elif days <= 30:
            return 'This Month'
        elif days <= 60:
            return 'Next Month'
        else:
            return '60+ Days'

    backorder_relief['relief_bucket'] = backorder_relief['days_until_relief'].apply(get_relief_bucket)

    bucket_counts = backorder_relief['relief_bucket'].value_counts()
    for bucket, count in bucket_counts.items():
        logs.append(f"INFO: {count} backorders relieving in: {bucket}")

    # ===== STEP 9: Calculate Summary Metrics =====
    total_time = (datetime.now() - start_time).total_seconds()
    logs.append(f"INFO: Relief analysis completed in {total_time:.2f} seconds")
    logs.append(f"INFO: Processed {len(backorder_relief)} backorders")
    logs.append(f"INFO: PO Coverage: {po_coverage_pct:.1f}%")

    avg_days_until_relief = backorder_relief[backorder_relief['days_until_relief'] != np.inf]['days_until_relief'].mean()
    if not pd.isna(avg_days_until_relief):
        logs.append(f"INFO: Average days until relief (with PO): {avg_days_until_relief:.1f} days")

    return logs, backorder_relief


def get_relief_summary_metrics(backorder_relief_df):
    """
    Calculate summary metrics for backorder relief analysis

    Args:
        backorder_relief_df: Enhanced backorder dataframe from calculate_backorder_relief_dates()

    Returns:
        dict: Summary metrics for display
    """
    if backorder_relief_df.empty:
        return {}

    total_backorders = len(backorder_relief_df)

    # PO Coverage
    po_coverage_count = backorder_relief_df['has_po_coverage'].sum()
    po_coverage_pct = (po_coverage_count / total_backorders * 100) if total_backorders > 0 else 0

    # Average days until relief (excluding no PO)
    with_po = backorder_relief_df[backorder_relief_df['has_po_coverage'] == True]
    avg_days_until_relief = with_po['days_until_relief'].mean() if not with_po.empty else 0

    # High-risk count
    high_risk_count = backorder_relief_df['is_high_risk'].sum()

    # Relief timeline buckets
    this_week = len(backorder_relief_df[backorder_relief_df['relief_bucket'] == 'This Week'])
    this_month = len(backorder_relief_df[backorder_relief_df['relief_bucket'] == 'This Month'])

    # Confidence breakdown
    high_confidence = len(backorder_relief_df[backorder_relief_df['relief_confidence'] == 'High'])
    medium_confidence = len(backorder_relief_df[backorder_relief_df['relief_confidence'] == 'Medium'])
    low_confidence = len(backorder_relief_df[backorder_relief_df['relief_confidence'] == 'Low'])
    no_po = len(backorder_relief_df[backorder_relief_df['relief_confidence'] == 'No PO'])

    return {
        'total_backorders': total_backorders,
        'po_coverage_count': po_coverage_count,
        'po_coverage_pct': po_coverage_pct,
        'avg_days_until_relief': avg_days_until_relief,
        'high_risk_count': high_risk_count,
        'relief_this_week': this_week,
        'relief_this_month': this_month,
        'high_confidence_count': high_confidence,
        'medium_confidence_count': medium_confidence,
        'low_confidence_count': low_confidence,
        'no_po_count': no_po
    }


def get_critical_gaps(backorder_relief_df, top_n=20):
    """
    Identify critical backorder gaps (no PO coverage or high-risk)

    Args:
        backorder_relief_df: Enhanced backorder dataframe
        top_n: Number of top critical items to return

    Returns:
        DataFrame: Critical backorders sorted by priority
    """
    if backorder_relief_df.empty:
        return pd.DataFrame()

    # Filter to high-risk backorders
    critical = backorder_relief_df[backorder_relief_df['is_high_risk'] == True].copy()

    # Sort by days on backorder (oldest first) and quantity (largest first)
    critical = critical.sort_values(['days_on_backorder', 'backorder_qty'], ascending=[False, False])

    return critical.head(top_n)


def get_relief_timeline_data(backorder_relief_df):
    """
    Prepare data for Gantt-style relief timeline visualization

    Args:
        backorder_relief_df: Enhanced backorder dataframe

    Returns:
        DataFrame: Timeline data for visualization
    """
    if backorder_relief_df.empty:
        return pd.DataFrame()

    # Filter to backorders with PO coverage
    with_po = backorder_relief_df[backorder_relief_df['has_po_coverage'] == True].copy()

    if with_po.empty:
        return pd.DataFrame()

    # Sort by adjusted delivery date
    timeline = with_po.sort_values('vendor_adjusted_delivery_date')

    # Select relevant columns for timeline display
    timeline_data = timeline[[
        'sales_order', 'sku', 'customer_name', 'backorder_qty', 'days_on_backorder',
        'vendor_name', 'relieving_po_number', 'vendor_adjusted_delivery_date',
        'days_until_relief', 'relief_confidence', 'relief_bucket'
    ]].copy()

    return timeline_data
