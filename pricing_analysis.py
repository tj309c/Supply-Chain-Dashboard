"""
Pricing Analysis Module
Analyzes vendor pricing, volume discounts, and identifies pricing anomalies
"""

import pandas as pd
import numpy as np
from datetime import datetime
import streamlit as st

TODAY = pd.to_datetime(datetime.now().date())

@st.cache_data(show_spinner="Analyzing pricing and volume discounts...")
def load_pricing_analysis(vendor_pos_df, inbound_df):
    """
    Comprehensive pricing analysis with volume discount scoring

    Analyzes:
    1. Price increases vs historical pricing (with configurable threshold)
    2. Volume-to-price discount relationships per vendor
    3. Cross-vendor pricing comparison for same SKUs
    4. Vendor consistency scoring (erratic discounting detection)
    5. Anomalous purchase flags (high qty + no usage, bad pricing)

    Args:
        vendor_pos_df: Vendor PO dataframe from load_vendor_pos()
        inbound_df: Inbound receipts dataframe from load_inbound_data()

    Returns: logs (list), pricing_analysis_df
    """
    logs = []
    start_time = datetime.now()
    logs.append("--- Pricing Analysis Engine ---")

    if vendor_pos_df.empty:
        logs.append("ERROR: Vendor PO data is empty. Cannot perform pricing analysis.")
        return logs, pd.DataFrame()

    # ===== STEP 1: Prepare Base Data =====
    logs.append("INFO: Preparing pricing data from PO and inbound receipts...")

    # Create comprehensive pricing dataset
    pricing_df = vendor_pos_df.copy()

    # Filter to valid price records (unit_price > 0, ordered_qty > 0)
    pricing_df = pricing_df[(pricing_df['unit_price'] > 0) & (pricing_df['ordered_qty'] > 0)]
    logs.append(f"INFO: {len(pricing_df)} PO lines with valid pricing data.")

    # ===== STEP 2: Historical Price Analysis =====
    logs.append("INFO: Calculating historical price trends per SKU...")

    # Get historical pricing per SKU (last 24 months)
    two_years_ago = TODAY - pd.DateOffset(months=24)
    historical_pricing = pricing_df[pricing_df['po_create_date'] >= two_years_ago].copy()

    # Calculate price statistics per SKU
    price_stats = historical_pricing.groupby('sku').agg({
        'unit_price': ['min', 'max', 'mean', 'median', 'std', 'count'],
        'po_create_date': 'max'  # Most recent PO date
    }).reset_index()

    price_stats.columns = ['sku', 'price_min', 'price_max', 'price_mean', 'price_median',
                           'price_std', 'price_history_count', 'last_po_date']

    # Calculate coefficient of variation (price volatility)
    price_stats['price_cv'] = (price_stats['price_std'] / price_stats['price_mean']) * 100
    price_stats['price_cv'] = price_stats['price_cv'].fillna(0)

    logs.append(f"INFO: Calculated price history for {len(price_stats)} SKUs.")

    # ===== STEP 3: Price Increase Detection =====
    logs.append("INFO: Detecting significant price increases...")

    # Merge current PO pricing with historical stats
    pricing_with_history = pd.merge(
        pricing_df[['po_number', 'sku', 'vendor_name', 'po_create_date', 'unit_price',
                    'ordered_qty', 'open_qty', 'is_open']],
        price_stats,
        on='sku',
        how='left'
    )

    # Calculate price increase % vs historical median
    pricing_with_history['price_increase_pct'] = (
        (pricing_with_history['unit_price'] - pricing_with_history['price_median']) /
        pricing_with_history['price_median'] * 100
    )
    pricing_with_history['price_increase_pct'] = pricing_with_history['price_increase_pct'].fillna(0)

    # ===== STEP 4: Volume-to-Price Discount Analysis =====
    logs.append("INFO: Analyzing volume discount relationships...")

    # For each vendor-SKU combination, analyze quantity vs price correlation
    vendor_sku_pricing = pricing_df.groupby(['vendor_name', 'sku'], group_keys=False).apply(
        lambda x: pd.Series({
            'po_count': len(x),
            'total_qty_ordered': x['ordered_qty'].sum(),
            'avg_unit_price': x['unit_price'].mean(),
            'min_unit_price': x['unit_price'].min(),
            'max_unit_price': x['unit_price'].max(),
            'price_range_pct': ((x['unit_price'].max() - x['unit_price'].min()) /
                                x['unit_price'].mean() * 100) if x['unit_price'].mean() > 0 else 0,
            'avg_order_qty': x['ordered_qty'].mean(),
            'min_order_qty': x['ordered_qty'].min(),
            'max_order_qty': x['ordered_qty'].max(),
            # Volume discount effectiveness score
            'qty_price_correlation': x[['ordered_qty', 'unit_price']].corr().iloc[0, 1] if len(x) >= 3 else np.nan
        }), include_groups=False
    ).reset_index()

    # Score vendors on discount effectiveness
    # Negative correlation = good (higher qty = lower price)
    # Positive correlation = bad (higher qty = higher price)
    vendor_sku_pricing['discount_score'] = vendor_sku_pricing['qty_price_correlation'].apply(
        lambda x: 100 if pd.isna(x) else max(0, (1 - x) * 50)  # Scale -1 to 1 => 100 to 0
    )

    logs.append(f"INFO: Analyzed volume-price relationships for {len(vendor_sku_pricing)} vendor-SKU combinations.")

    # ===== STEP 5: Cross-Vendor Price Comparison =====
    logs.append("INFO: Comparing pricing across vendors for same SKUs...")

    # For SKUs with multiple vendors, compare pricing
    multi_vendor_skus = vendor_sku_pricing.groupby('sku').filter(lambda x: len(x) > 1)

    # Calculate best price per SKU across all vendors
    best_prices = vendor_sku_pricing.groupby('sku')['avg_unit_price'].min().reset_index()
    best_prices.columns = ['sku', 'market_best_price']

    # Merge to get price competitiveness
    vendor_sku_pricing = pd.merge(vendor_sku_pricing, best_prices, on='sku', how='left')
    vendor_sku_pricing['price_premium_pct'] = (
        (vendor_sku_pricing['avg_unit_price'] - vendor_sku_pricing['market_best_price']) /
        vendor_sku_pricing['market_best_price'] * 100
    )
    vendor_sku_pricing['price_premium_pct'] = vendor_sku_pricing['price_premium_pct'].fillna(0)

    # Flag overpriced items (>10% above best market price)
    vendor_sku_pricing['is_overpriced'] = vendor_sku_pricing['price_premium_pct'] > 10

    logs.append(f"INFO: {len(multi_vendor_skus)} SKUs have multiple vendor options for price comparison.")

    # ===== STEP 6: Vendor Discount Consistency Scoring =====
    logs.append("INFO: Scoring vendor discount consistency and reliability...")

    # Group by vendor to calculate overall discount behavior
    vendor_discount_summary = vendor_sku_pricing.groupby('vendor_name').agg({
        'sku': 'nunique',
        'po_count': 'sum',
        'total_qty_ordered': 'sum',
        'discount_score': 'mean',
        'price_range_pct': 'mean',
        'qty_price_correlation': 'mean',
        'is_overpriced': 'sum'
    }).reset_index()

    vendor_discount_summary.columns = [
        'vendor_name', 'unique_skus', 'total_pos', 'total_qty_ordered',
        'avg_discount_score', 'avg_price_variance_pct', 'avg_qty_price_corr',
        'overpriced_items_count'
    ]

    # Calculate vendor consistency score (0-100)
    # Lower price variance = better consistency
    # Higher discount score = better volume discounts
    # Fewer overpriced items = better competitive pricing
    vendor_discount_summary['consistency_score'] = (
        vendor_discount_summary['avg_discount_score'] * 0.4 +  # 40% weight on discount effectiveness
        (100 - vendor_discount_summary['avg_price_variance_pct'].clip(upper=100)) * 0.3 +  # 30% weight on price stability
        (100 - (vendor_discount_summary['overpriced_items_count'] / vendor_discount_summary['unique_skus'] * 100)) * 0.3  # 30% weight on competitive pricing
    )

    # Rank vendors by consistency
    vendor_discount_summary = vendor_discount_summary.sort_values('consistency_score', ascending=False)
    vendor_discount_summary['vendor_rank'] = range(1, len(vendor_discount_summary) + 1)

    # Flag worst offenders (bottom 25%)
    worst_threshold = vendor_discount_summary['consistency_score'].quantile(0.25)
    vendor_discount_summary['is_worst_offender'] = vendor_discount_summary['consistency_score'] <= worst_threshold

    logs.append(f"INFO: Scored {len(vendor_discount_summary)} vendors on discount consistency.")
    logs.append(f"INFO: Identified {vendor_discount_summary['is_worst_offender'].sum()} vendors with poor discount practices.")

    # ===== STEP 7: Merge Back to Main Dataset =====
    logs.append("INFO: Creating comprehensive pricing analysis dataset...")

    # Merge vendor scores back to pricing data
    pricing_analysis = pd.merge(
        pricing_with_history,
        vendor_sku_pricing[['vendor_name', 'sku', 'discount_score', 'price_premium_pct',
                            'is_overpriced', 'qty_price_correlation']],
        on=['vendor_name', 'sku'],
        how='left'
    )

    # Merge vendor summary scores
    pricing_analysis = pd.merge(
        pricing_analysis,
        vendor_discount_summary[['vendor_name', 'consistency_score', 'vendor_rank', 'is_worst_offender']],
        on='vendor_name',
        how='left'
    )

    # ===== STEP 8: Create Time-Bucketed Price Windows =====
    logs.append("INFO: Creating bucketed price history windows...")

    # Calculate price buckets (1 month, 3 months, 6 months, 12 months, 24 months)
    pricing_analysis['months_ago'] = ((TODAY - pricing_analysis['po_create_date']).dt.days / 30).astype(int)

    # Vectorized bucket assignment for performance
    conditions = [
        pricing_analysis['months_ago'] <= 1,
        pricing_analysis['months_ago'] <= 3,
        pricing_analysis['months_ago'] <= 6,
        pricing_analysis['months_ago'] <= 12,
        pricing_analysis['months_ago'] <= 24
    ]
    choices = ['0-1 months', '1-3 months', '3-6 months', '6-12 months', '12-24 months']
    pricing_analysis['price_bucket'] = np.select(conditions, choices, default='24+ months')

    # ===== STEP 9: Anomaly Detection Flags =====
    logs.append("INFO: Flagging anomalous purchases...")

    # Flag 1: High quantity order with no recent usage (requires future integration with demand data)
    # For now, flag large orders as potentially anomalous (>75th percentile)
    qty_threshold = pricing_analysis['ordered_qty'].quantile(0.75)
    pricing_analysis['is_high_qty_order'] = pricing_analysis['ordered_qty'] > qty_threshold

    # Flag 2: Price significantly above historical median (default 20% threshold)
    pricing_analysis['is_price_spike'] = pricing_analysis['price_increase_pct'] > 20

    # Flag 3: Highly volatile pricing from vendor (CV > 25%)
    pricing_analysis['is_volatile_pricing'] = pricing_analysis['price_cv'] > 25

    # Combined anomaly flag
    pricing_analysis['has_anomaly'] = (
        pricing_analysis['is_price_spike'] |
        pricing_analysis['is_overpriced'] |
        pricing_analysis['is_volatile_pricing']
    )

    anomaly_count = pricing_analysis['has_anomaly'].sum()
    logs.append(f"INFO: Flagged {anomaly_count} PO lines with pricing anomalies.")

    # ===== STEP 10: Calculate Summary Metrics =====
    total_analysis_time = (datetime.now() - start_time).total_seconds()
    logs.append(f"INFO: Pricing Analysis completed in {total_analysis_time:.2f} seconds.")
    logs.append(f"INFO: Analyzed {len(pricing_analysis)} PO lines across {pricing_analysis['vendor_name'].nunique()} vendors.")
    logs.append(f"INFO: {len(multi_vendor_skus)} SKUs have competitive pricing options.")

    # Return both the detailed analysis and vendor summary
    return logs, pricing_analysis, vendor_discount_summary


def get_sku_pricing_history(pricing_df, sku, time_window_months=24):
    """
    Get detailed pricing history for a specific SKU

    Args:
        pricing_df: Pricing analysis dataframe from load_pricing_analysis()
        sku: SKU to analyze
        time_window_months: Number of months to look back (default 24)

    Returns: DataFrame with pricing history for the SKU
    """
    cutoff_date = TODAY - pd.DateOffset(months=time_window_months)

    sku_history = pricing_df[
        (pricing_df['sku'] == sku) &
        (pricing_df['po_create_date'] >= cutoff_date)
    ].sort_values('po_create_date')

    return sku_history[['po_create_date', 'vendor_name', 'unit_price', 'ordered_qty',
                        'price_increase_pct', 'discount_score', 'has_anomaly']]


def get_vendor_pricing_comparison(pricing_df, sku):
    """
    Compare pricing across all vendors for a specific SKU

    Args:
        pricing_df: Pricing analysis dataframe from load_pricing_analysis()
        sku: SKU to analyze

    Returns: DataFrame with vendor comparison for the SKU
    """
    sku_vendors = pricing_df[pricing_df['sku'] == sku].groupby('vendor_name').agg({
        'unit_price': ['min', 'mean', 'max', 'count'],
        'ordered_qty': 'sum',
        'discount_score': 'mean',
        'consistency_score': 'first'
    }).reset_index()

    sku_vendors.columns = ['vendor_name', 'price_min', 'price_avg', 'price_max',
                           'po_count', 'total_qty', 'discount_score', 'consistency_score']

    # Rank vendors by average price (best to worst)
    sku_vendors = sku_vendors.sort_values('price_avg')
    sku_vendors['price_rank'] = range(1, len(sku_vendors) + 1)

    # Calculate savings potential vs best price
    best_price = sku_vendors['price_avg'].min()
    sku_vendors['savings_pct'] = ((sku_vendors['price_avg'] - best_price) / best_price * 100)

    return sku_vendors


def get_worst_discount_offenders(vendor_summary_df, top_n=10):
    """
    Get the worst vendors for erratic/poor volume discounting

    Args:
        vendor_summary_df: Vendor discount summary from load_pricing_analysis()
        top_n: Number of worst offenders to return (default 10)

    Returns: DataFrame with worst offenders
    """
    worst_offenders = vendor_summary_df[
        vendor_summary_df['is_worst_offender'] == True
    ].sort_values('consistency_score').head(top_n)

    return worst_offenders[['vendor_name', 'consistency_score', 'avg_discount_score',
                            'avg_price_variance_pct', 'overpriced_items_count', 'vendor_rank']]


def get_price_spike_alerts(pricing_df, threshold_pct=20):
    """
    Get all open POs with significant price spikes above threshold

    Args:
        pricing_df: Pricing analysis dataframe from load_pricing_analysis()
        threshold_pct: Price increase threshold percentage (default 20%)

    Returns: DataFrame with price spike alerts
    """
    alerts = pricing_df[
        (pricing_df['is_open'] == True) &
        (pricing_df['price_increase_pct'] > threshold_pct)
    ].sort_values('price_increase_pct', ascending=False)

    return alerts[['po_number', 'sku', 'vendor_name', 'unit_price', 'price_median',
                   'price_increase_pct', 'ordered_qty', 'open_qty', 'po_create_date']]


def calculate_volume_discount_curve(pricing_df, vendor_name, sku):
    """
    Calculate the volume discount curve for a specific vendor-SKU combination

    Args:
        pricing_df: Pricing analysis dataframe from load_pricing_analysis()
        vendor_name: Vendor to analyze
        sku: SKU to analyze

    Returns: DataFrame with quantity tiers and corresponding prices
    """
    vendor_sku_data = pricing_df[
        (pricing_df['vendor_name'] == vendor_name) &
        (pricing_df['sku'] == sku)
    ].sort_values('ordered_qty')

    if len(vendor_sku_data) < 2:
        return pd.DataFrame()  # Not enough data for curve

    # Group by quantity buckets
    vendor_sku_data['qty_bucket'] = pd.qcut(
        vendor_sku_data['ordered_qty'],
        q=min(5, len(vendor_sku_data)),  # Up to 5 buckets
        duplicates='drop'
    )

    discount_curve = vendor_sku_data.groupby('qty_bucket').agg({
        'ordered_qty': ['min', 'max', 'mean'],
        'unit_price': ['min', 'max', 'mean']
    }).reset_index()

    discount_curve.columns = ['qty_range', 'qty_min', 'qty_max', 'qty_avg',
                              'price_min', 'price_max', 'price_avg']

    # Calculate discount % vs highest price
    max_price = discount_curve['price_avg'].max()
    discount_curve['discount_pct'] = ((max_price - discount_curve['price_avg']) / max_price * 100)

    return discount_curve
