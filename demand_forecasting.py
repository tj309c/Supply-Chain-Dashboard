"""
Demand Forecasting Module

Generates statistical demand forecasts using historical delivery data.
Uses simple, interpretable methods: moving averages and exponential smoothing.

Key Features:
- 30/60/90 day moving average forecasts
- Simple exponential smoothing
- Forecast accuracy metrics (MAPE, MAE, RMSE)
- Demand trend and seasonality detection
- SKU-level and aggregate forecasting
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
import os

TODAY = pd.to_datetime(datetime.now().date())
SNAPSHOT_FOLDER = "data/forecast_snapshots"


@st.cache_data(show_spinner="Generating demand forecasts...")
def generate_demand_forecast(deliveries_df, master_data_df=None, forecast_horizon_days=90):
    """
    Generate demand forecasts using historical delivery data

    Args:
        deliveries_df: Historical deliveries dataframe with columns: sku, delivery_date, delivered_qty
        master_data_df: Master data dataframe with SKU metadata (category, description, etc.)
        forecast_horizon_days: Number of days to forecast ahead (default 90)

    Returns:
        tuple: (logs, forecast_df, accuracy_metrics_df, daily_demand_df)
    """
    logs = []
    start_time = datetime.now()
    logs.append("--- Demand Forecasting Engine ---")

    if deliveries_df.empty:
        logs.append("ERROR: No delivery data provided. Cannot generate forecasts.")
        return logs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ===== STEP 1: Prepare Historical Data =====
    logs.append("INFO: Preparing historical delivery data...")

    # Create working copy
    df = deliveries_df.copy()

    # Handle column name compatibility across different data sources
    # Map various possible column names to standard names
    if 'Delivery Creation Date: Date' in df.columns:
        df['delivery_date'] = df['Delivery Creation Date: Date']
    elif 'ship_date' in df.columns:
        df['delivery_date'] = df['ship_date']

    if 'Deliveries - TOTAL Goods Issue Qty' in df.columns:
        df['delivered_qty'] = pd.to_numeric(df['Deliveries - TOTAL Goods Issue Qty'], errors='coerce').fillna(0)
    elif 'units_issued' in df.columns:
        df['delivered_qty'] = pd.to_numeric(df['units_issued'], errors='coerce').fillna(0)
    else:
        # Fallback: try to convert existing delivered_qty column
        df['delivered_qty'] = pd.to_numeric(df.get('delivered_qty', 0), errors='coerce').fillna(0)

    if 'Item - SAP Model Code' in df.columns:
        df['sku'] = df['Item - SAP Model Code'].astype(str).str.strip()
    elif 'sku' not in df.columns:
        logs.append("ERROR: No SKU column found in deliveries data")
        return logs, pd.DataFrame(), pd.DataFrame()

    # Ensure delivery_date is datetime
    df['delivery_date'] = pd.to_datetime(df['delivery_date'], format='%m/%d/%y', errors='coerce')

    # Filter to valid records (delivered_qty > 0, valid dates)
    df = df[(df['delivered_qty'] > 0) & (df['delivery_date'].notna())]

    # Calculate days from today
    df['days_ago'] = (TODAY - df['delivery_date']).dt.days

    # Use last 365 days of data for forecasting
    historical_window_days = 365
    df = df[df['days_ago'] <= historical_window_days]

    logs.append(f"INFO: Using {len(df)} delivery records from last {historical_window_days} days")
    logs.append(f"INFO: Covering {df['sku'].nunique()} unique SKUs")

    if df.empty:
        logs.append("ERROR: No historical data within time window. Cannot generate forecasts.")
        return logs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ===== STEP 2: Aggregate Daily Demand by SKU =====
    logs.append("INFO: Aggregating daily demand by SKU...")

    # Create daily demand time series per SKU
    daily_demand = df.groupby(['sku', 'delivery_date']).agg({
        'delivered_qty': 'sum'
    }).reset_index()

    daily_demand.columns = ['sku', 'date', 'demand_qty']

    logs.append(f"INFO: Created daily demand series for {daily_demand['sku'].nunique()} SKUs")

    # ===== STEP 3: Calculate Moving Averages (30/60/90 days) =====
    logs.append("INFO: Calculating moving average forecasts...")

    forecasts_list = []

    for sku in daily_demand['sku'].unique():
        sku_data = daily_demand[daily_demand['sku'] == sku].sort_values('date')

        if len(sku_data) < 30:
            # Skip SKUs with insufficient history (need at least 30 days)
            continue

        # Calculate moving averages
        ma_30 = sku_data['demand_qty'].rolling(window=30, min_periods=1).mean().iloc[-1]
        ma_60 = sku_data['demand_qty'].rolling(window=60, min_periods=1).mean().iloc[-1]
        ma_90 = sku_data['demand_qty'].rolling(window=90, min_periods=1).mean().iloc[-1]

        # Calculate exponential smoothing (alpha = 0.3 for smooth forecasts)
        exp_smooth = calculate_exponential_smoothing(sku_data['demand_qty'].values, alpha=0.3)

        # Calculate demand statistics
        total_demand = sku_data['demand_qty'].sum()
        avg_daily_demand = sku_data['demand_qty'].mean()
        std_daily_demand = sku_data['demand_qty'].std()
        demand_cv = (std_daily_demand / avg_daily_demand * 100) if avg_daily_demand > 0 else 0

        # Calculate demand trend (linear regression slope)
        sku_data['day_index'] = range(len(sku_data))
        if len(sku_data) >= 2:
            trend_slope = np.polyfit(sku_data['day_index'], sku_data['demand_qty'], 1)[0]
        else:
            trend_slope = 0

        # Determine forecast method (use most stable MA based on data availability)
        if len(sku_data) >= 90:
            primary_forecast = ma_90
            forecast_method = 'MA-90'
        elif len(sku_data) >= 60:
            primary_forecast = ma_60
            forecast_method = 'MA-60'
        else:
            primary_forecast = ma_30
            forecast_method = 'MA-30'

        # Calculate forecast for horizon (daily forecast * horizon days)
        forecast_total = primary_forecast * forecast_horizon_days

        # Calculate confidence interval (±1 std dev)
        forecast_lower = max(0, (primary_forecast - std_daily_demand) * forecast_horizon_days)
        forecast_upper = (primary_forecast + std_daily_demand) * forecast_horizon_days

        # Classify demand pattern
        demand_pattern = classify_demand_pattern(demand_cv, trend_slope)

        forecasts_list.append({
            'sku': sku,
            'forecast_method': forecast_method,
            'avg_daily_demand': avg_daily_demand,
            'ma_30_daily': ma_30,
            'ma_60_daily': ma_60,
            'ma_90_daily': ma_90,
            'exp_smooth_daily': exp_smooth,
            'primary_forecast_daily': primary_forecast,
            'forecast_total_qty': forecast_total,
            'forecast_lower_bound': forecast_lower,
            'forecast_upper_bound': forecast_upper,
            'forecast_horizon_days': forecast_horizon_days,
            'historical_days': len(sku_data),
            'total_historical_demand': total_demand,
            'demand_std': std_daily_demand,
            'demand_cv': demand_cv,
            'demand_trend_slope': trend_slope,
            'demand_pattern': demand_pattern,
            'last_delivery_date': sku_data['date'].max()
        })

    forecast_df = pd.DataFrame(forecasts_list)

    logs.append(f"INFO: Generated forecasts for {len(forecast_df)} SKUs")

    if forecast_df.empty:
        logs.append("WARNING: No SKUs had sufficient data for forecasting (minimum 30 days required)")
        return logs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ===== STEP 4: Calculate Forecast Accuracy (Backtest) =====
    logs.append("INFO: Calculating forecast accuracy using backtesting...")

    accuracy_list = []

    for sku in forecast_df['sku'].unique():
        sku_data = daily_demand[daily_demand['sku'] == sku].sort_values('date')

        if len(sku_data) < 60:
            # Need at least 60 days for backtesting (30 train + 30 test)
            continue

        # Split into train (first 80%) and test (last 20%)
        split_idx = int(len(sku_data) * 0.8)
        train_data = sku_data.iloc[:split_idx]
        test_data = sku_data.iloc[split_idx:]

        # Calculate forecast on training data
        train_ma_30 = train_data['demand_qty'].rolling(window=30, min_periods=1).mean().iloc[-1]

        # Compare to actual test period demand
        actual_avg = test_data['demand_qty'].mean()
        forecast_avg = train_ma_30

        # Calculate error metrics
        mape = calculate_mape(actual_avg, forecast_avg)
        mae = abs(actual_avg - forecast_avg)
        rmse = np.sqrt((actual_avg - forecast_avg) ** 2)

        accuracy_list.append({
            'sku': sku,
            'actual_avg_demand': actual_avg,
            'forecast_avg_demand': forecast_avg,
            'mape': mape,
            'mae': mae,
            'rmse': rmse,
            'test_period_days': len(test_data)
        })

    accuracy_df = pd.DataFrame(accuracy_list)

    # Merge accuracy back to forecasts
    if not accuracy_df.empty:
        forecast_df = pd.merge(
            forecast_df,
            accuracy_df[['sku', 'mape', 'mae']],
            on='sku',
            how='left'
        )

        avg_mape = accuracy_df['mape'].mean()
        logs.append(f"INFO: Average forecast accuracy (MAPE): {avg_mape:.1f}%")
        logs.append(f"INFO: Backtested {len(accuracy_df)} SKUs")
    else:
        logs.append("WARNING: Insufficient data for accuracy backtesting")
        forecast_df['mape'] = np.nan
        forecast_df['mae'] = np.nan

    # ===== STEP 5: Classify Forecast Confidence =====
    logs.append("INFO: Calculating forecast confidence scores...")

    def calculate_confidence(row):
        """Calculate forecast confidence based on data quality and accuracy"""
        score = 100

        # Penalize high CV (volatile demand)
        if row['demand_cv'] > 100:
            score -= 30
        elif row['demand_cv'] > 50:
            score -= 15

        # Penalize insufficient history
        if row['historical_days'] < 90:
            score -= 20
        elif row['historical_days'] < 60:
            score -= 30

        # Penalize high MAPE (if available)
        if pd.notna(row.get('mape')):
            if row['mape'] > 50:
                score -= 25
            elif row['mape'] > 30:
                score -= 15

        return max(0, score)

    forecast_df['forecast_confidence_score'] = forecast_df.apply(calculate_confidence, axis=1)

    # Classify confidence levels
    conditions = [
        forecast_df['forecast_confidence_score'] >= 70,
        forecast_df['forecast_confidence_score'] >= 50,
        forecast_df['forecast_confidence_score'] >= 30
    ]
    choices = ['High', 'Medium', 'Low']
    forecast_df['forecast_confidence'] = np.select(conditions, choices, default='Very Low')

    confidence_counts = forecast_df['forecast_confidence'].value_counts()
    for conf, count in confidence_counts.items():
        logs.append(f"INFO: {count} SKUs with {conf} confidence forecasts")

    # ===== STEP 6: Join Master Data (Category & Description) =====
    if master_data_df is not None and not master_data_df.empty:
        logs.append("INFO: Joining master data for category and description...")

        # Prepare master data - get category and description
        master_cols = ['sku']

        # Handle different column names for category
        if 'category' in master_data_df.columns:
            master_cols.append('category')
        elif 'PLM: Level Classification 4' in master_data_df.columns:
            master_data_clean = master_data_df.copy()
            master_data_clean['category'] = master_data_df['PLM: Level Classification 4']
            master_cols.append('category')
        else:
            logs.append("WARNING: No category column found in master data")
            master_data_clean = master_data_df.copy()

        # Handle different column names for description
        if 'sku_description' in master_data_df.columns:
            if 'sku_description' not in master_cols:
                master_cols.append('sku_description')
        elif 'Item - Description' in master_data_df.columns:
            if 'master_data_clean' not in locals():
                master_data_clean = master_data_df.copy()
            master_data_clean['sku_description'] = master_data_df['Item - Description']
            if 'sku_description' not in master_cols:
                master_cols.append('sku_description')

        # Prepare clean master data with selected columns
        if 'master_data_clean' not in locals():
            master_data_clean = master_data_df.copy()

        # Ensure SKU column exists and is properly formatted
        if 'Item - SAP Model Code' in master_data_clean.columns:
            master_data_clean['sku'] = master_data_clean['Item - SAP Model Code'].astype(str).str.strip()
        elif 'sku' not in master_data_clean.columns:
            logs.append("WARNING: No SKU column found in master data")
            master_data_clean = None

        if master_data_clean is not None:
            # Check for duplicate SKUs in master data
            sku_counts = master_data_clean['sku'].value_counts()
            duplicates = sku_counts[sku_counts > 1]

            if len(duplicates) > 0:
                logs.append(f"WARNING: Found {len(duplicates)} duplicate SKUs in master data. Using first occurrence.")
                master_data_clean = master_data_clean.drop_duplicates(subset='sku', keep='first')

            # Select only needed columns that exist
            available_cols = [col for col in master_cols if col in master_data_clean.columns]
            master_data_clean = master_data_clean[available_cols]

            # Merge with forecast data
            before_merge_count = len(forecast_df)
            forecast_df = pd.merge(
                forecast_df,
                master_data_clean,
                on='sku',
                how='left'
            )

            after_merge_count = len(forecast_df)

            # Validate merge didn't create duplicates (many-to-one error)
            if after_merge_count != before_merge_count:
                logs.append(f"ERROR: Merge created duplicates! Before: {before_merge_count}, After: {after_merge_count}")
                logs.append("ERROR: This indicates duplicate SKUs in master data. Reverting merge.")
                forecast_df = forecast_df.drop_duplicates(subset='sku', keep='first')

            # Fill missing categories
            if 'category' in forecast_df.columns:
                missing_category_count = forecast_df['category'].isna().sum()
                if missing_category_count > 0:
                    logs.append(f"WARNING: {missing_category_count} SKUs have no category. Assigning 'Uncategorized'.")
                    forecast_df['category'] = forecast_df['category'].fillna('Uncategorized')

                logs.append(f"INFO: Joined {len(forecast_df['category'].unique())} categories from master data")

            if 'sku_description' in forecast_df.columns:
                forecast_df['sku_description'] = forecast_df['sku_description'].fillna('Unknown')
    else:
        logs.append("WARNING: No master data provided. Category and description will not be available.")
        forecast_df['category'] = 'Uncategorized'
        forecast_df['sku_description'] = 'Unknown'

    # Add snapshot date
    forecast_df['snapshot_date'] = TODAY

    # ===== STEP 7: Calculate Summary Metrics =====
    total_time = (datetime.now() - start_time).total_seconds()
    logs.append(f"INFO: Forecast generation completed in {total_time:.2f} seconds")

    total_forecast_demand = forecast_df['forecast_total_qty'].sum()
    logs.append(f"INFO: Total forecasted demand (next {forecast_horizon_days} days): {total_forecast_demand:,.0f} units")

    return logs, forecast_df, accuracy_df, daily_demand


def calculate_exponential_smoothing(values, alpha=0.3):
    """
    Calculate simple exponential smoothing forecast

    Args:
        values: Array of historical values
        alpha: Smoothing factor (0-1), higher = more weight on recent data

    Returns:
        float: Smoothed forecast value
    """
    if len(values) == 0:
        return 0

    smoothed = values[0]
    for value in values[1:]:
        smoothed = alpha * value + (1 - alpha) * smoothed

    return smoothed


def calculate_mape(actual, forecast):
    """
    Calculate Mean Absolute Percentage Error

    Args:
        actual: Actual value
        forecast: Forecasted value

    Returns:
        float: MAPE percentage
    """
    if actual == 0:
        return 100.0 if forecast != 0 else 0.0

    return abs((actual - forecast) / actual) * 100


def classify_demand_pattern(cv, trend_slope):
    """
    Classify demand pattern based on volatility and trend

    Args:
        cv: Coefficient of variation (std/mean * 100)
        trend_slope: Linear trend slope

    Returns:
        str: Demand pattern classification
    """
    # Determine volatility
    if cv < 30:
        volatility = 'Stable'
    elif cv < 70:
        volatility = 'Moderate'
    else:
        volatility = 'Volatile'

    # Determine trend
    if trend_slope > 0.5:
        trend = 'Growing'
    elif trend_slope < -0.5:
        trend = 'Declining'
    else:
        trend = 'Flat'

    return f"{volatility} & {trend}"


def get_forecast_summary_metrics(forecast_df):
    """
    Calculate summary metrics for forecast dashboard

    Args:
        forecast_df: Forecast dataframe from generate_demand_forecast()

    Returns:
        dict: Summary metrics
    """
    if forecast_df.empty:
        return {}

    total_skus = len(forecast_df)
    total_forecast_demand = forecast_df['forecast_total_qty'].sum()
    avg_mape = forecast_df['mape'].mean() if 'mape' in forecast_df.columns else np.nan

    # Confidence breakdown
    high_conf = len(forecast_df[forecast_df['forecast_confidence'] == 'High'])
    medium_conf = len(forecast_df[forecast_df['forecast_confidence'] == 'Medium'])
    low_conf = len(forecast_df[forecast_df['forecast_confidence'] == 'Low'])
    very_low_conf = len(forecast_df[forecast_df['forecast_confidence'] == 'Very Low'])

    # Demand pattern breakdown
    pattern_counts = forecast_df['demand_pattern'].value_counts().to_dict()

    # Top forecasted SKUs
    top_10_skus = forecast_df.nlargest(10, 'forecast_total_qty')[['sku', 'forecast_total_qty']]

    return {
        'total_skus_forecasted': total_skus,
        'total_forecast_demand': total_forecast_demand,
        'avg_mape': avg_mape,
        'high_confidence_count': high_conf,
        'medium_confidence_count': medium_conf,
        'low_confidence_count': low_conf,
        'very_low_confidence_count': very_low_conf,
        'demand_patterns': pattern_counts,
        'top_10_forecast_skus': top_10_skus
    }


def get_sku_forecast_details(forecast_df, sku):
    """
    Get detailed forecast information for a specific SKU

    Args:
        forecast_df: Forecast dataframe
        sku: SKU to retrieve

    Returns:
        dict: Detailed forecast metrics for the SKU
    """
    if forecast_df.empty or sku not in forecast_df['sku'].values:
        return {}

    sku_row = forecast_df[forecast_df['sku'] == sku].iloc[0]

    return {
        'sku': sku,
        'forecast_method': sku_row['forecast_method'],
        'daily_forecast': sku_row['primary_forecast_daily'],
        'total_forecast': sku_row['forecast_total_qty'],
        'forecast_range': (sku_row['forecast_lower_bound'], sku_row['forecast_upper_bound']),
        'confidence': sku_row['forecast_confidence'],
        'confidence_score': sku_row['forecast_confidence_score'],
        'mape': sku_row.get('mape', np.nan),
        'demand_pattern': sku_row['demand_pattern'],
        'historical_days': sku_row['historical_days'],
        'last_delivery': sku_row['last_delivery_date']
    }


def get_forecast_accuracy_rankings(accuracy_df, top_n=20):
    """
    Get best and worst forecasted SKUs by accuracy

    Args:
        accuracy_df: Accuracy metrics dataframe
        top_n: Number of SKUs to return

    Returns:
        tuple: (best_forecasts_df, worst_forecasts_df)
    """
    if accuracy_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    best = accuracy_df.nsmallest(top_n, 'mape')
    worst = accuracy_df.nlargest(top_n, 'mape')

    return best, worst


# ===== FORECAST SNAPSHOT MANAGEMENT =====

def save_forecast_snapshot(forecast_df, snapshot_date=None):
    """
    Save current forecast to CSV snapshot file

    Args:
        forecast_df: Forecast dataframe to save
        snapshot_date: Date for snapshot filename (default: today)

    Returns:
        tuple: (success: bool, filepath: str, message: str)
    """
    if forecast_df.empty:
        return False, "", "Error: Forecast dataframe is empty. Cannot save snapshot."

    # Create snapshot folder if it doesn't exist
    os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)

    # Use provided date or today
    if snapshot_date is None:
        snapshot_date = TODAY

    # Format filename
    filename = f"forecast_snapshot_{snapshot_date.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(SNAPSHOT_FOLDER, filename)

    try:
        # Select columns to save (optimize file size)
        save_cols = [
            'snapshot_date', 'sku', 'sku_description', 'category',
            'primary_forecast_daily', 'forecast_total_qty',
            'forecast_lower_bound', 'forecast_upper_bound',
            'forecast_method', 'forecast_confidence', 'forecast_confidence_score',
            'forecast_horizon_days', 'historical_days', 'mape', 'mae'
        ]

        # Only save columns that exist
        available_cols = [col for col in save_cols if col in forecast_df.columns]
        snapshot_df = forecast_df[available_cols].copy()

        # Save to CSV
        snapshot_df.to_csv(filepath, index=False)

        return True, filepath, f"Snapshot saved successfully to {filepath}"

    except Exception as e:
        return False, "", f"Error saving snapshot: {str(e)}"


def load_forecast_snapshots():
    """
    Load all forecast snapshots from the snapshots folder

    Returns:
        pd.DataFrame: Combined dataframe of all snapshots, or empty DataFrame if none found
    """
    if not os.path.exists(SNAPSHOT_FOLDER):
        return pd.DataFrame()

    # Get all snapshot files
    snapshot_files = [f for f in os.listdir(SNAPSHOT_FOLDER) if f.startswith('forecast_snapshot_') and f.endswith('.csv')]

    if not snapshot_files:
        return pd.DataFrame()

    # Load all snapshots
    snapshots_list = []
    for filename in snapshot_files:
        filepath = os.path.join(SNAPSHOT_FOLDER, filename)
        try:
            df = pd.read_csv(filepath)
            # Ensure snapshot_date is datetime
            if 'snapshot_date' in df.columns:
                df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
            snapshots_list.append(df)
        except Exception as e:
            print(f"Warning: Could not load {filename}: {str(e)}")

    if not snapshots_list:
        return pd.DataFrame()

    # Combine all snapshots
    all_snapshots = pd.concat(snapshots_list, ignore_index=True)
    return all_snapshots


def get_latest_snapshot_date():
    """
    Get the date of the most recent snapshot

    Returns:
        datetime or None: Date of latest snapshot, or None if no snapshots exist
    """
    if not os.path.exists(SNAPSHOT_FOLDER):
        return None

    snapshot_files = [f for f in os.listdir(SNAPSHOT_FOLDER) if f.startswith('forecast_snapshot_') and f.endswith('.csv')]

    if not snapshot_files:
        return None

    # Extract dates from filenames
    dates = []
    for filename in snapshot_files:
        try:
            # Extract date from filename: forecast_snapshot_YYYY-MM-DD.csv
            date_str = filename.replace('forecast_snapshot_', '').replace('.csv', '')
            date = pd.to_datetime(date_str)
            dates.append(date)
        except:
            continue

    if not dates:
        return None

    return max(dates)


def compare_forecast_vs_actual(snapshots_df, deliveries_df):
    """
    Compare historical forecast snapshots against actual deliveries

    Args:
        snapshots_df: DataFrame of historical forecast snapshots
        deliveries_df: DataFrame of actual deliveries

    Returns:
        pd.DataFrame: Comparison dataframe with forecast vs actual metrics
    """
    if snapshots_df.empty or deliveries_df.empty:
        return pd.DataFrame()

    # Prepare deliveries data
    deliveries = deliveries_df.copy()

    # Handle column name compatibility
    if 'Delivery Creation Date: Date' in deliveries.columns:
        deliveries['delivery_date'] = pd.to_datetime(deliveries['Delivery Creation Date: Date'], format='%m/%d/%y', errors='coerce')
    elif 'ship_date' in deliveries.columns:
        deliveries['delivery_date'] = pd.to_datetime(deliveries['ship_date'], errors='coerce')
    elif 'delivery_date' in deliveries.columns:
        deliveries['delivery_date'] = pd.to_datetime(deliveries['delivery_date'], errors='coerce')

    if 'Deliveries - TOTAL Goods Issue Qty' in deliveries.columns:
        deliveries['delivered_qty'] = pd.to_numeric(deliveries['Deliveries - TOTAL Goods Issue Qty'], errors='coerce').fillna(0)
    elif 'units_issued' in deliveries.columns:
        deliveries['delivered_qty'] = pd.to_numeric(deliveries['units_issued'], errors='coerce').fillna(0)
    elif 'delivered_qty' in deliveries.columns:
        deliveries['delivered_qty'] = pd.to_numeric(deliveries['delivered_qty'], errors='coerce').fillna(0)

    if 'Item - SAP Model Code' in deliveries.columns:
        deliveries['sku'] = deliveries['Item - SAP Model Code'].astype(str).str.strip()

    # Filter valid records
    deliveries = deliveries[(deliveries['delivered_qty'] > 0) & (deliveries['delivery_date'].notna())]

    # Aggregate actual demand by SKU and date
    actual_demand = deliveries.groupby(['sku', 'delivery_date']).agg({
        'delivered_qty': 'sum'
    }).reset_index()

    # For each snapshot, calculate the actual demand that occurred during the forecast period
    comparison_list = []

    for snapshot_date in snapshots_df['snapshot_date'].unique():
        snapshot_forecasts = snapshots_df[snapshots_df['snapshot_date'] == snapshot_date]

        # Calculate forecast period end date
        forecast_horizon = snapshot_forecasts['forecast_horizon_days'].iloc[0] if 'forecast_horizon_days' in snapshot_forecasts.columns else 90
        forecast_end_date = snapshot_date + timedelta(days=forecast_horizon)

        # Only compare if enough time has passed (forecast period ended)
        if forecast_end_date > TODAY:
            continue  # Skip snapshots where forecast period hasn't ended yet

        # Get actual demand during forecast period
        actual_in_period = actual_demand[
            (actual_demand['delivery_date'] > snapshot_date) &
            (actual_demand['delivery_date'] <= forecast_end_date)
        ]

        # Aggregate by SKU
        actual_by_sku = actual_in_period.groupby('sku').agg({
            'delivered_qty': 'sum'
        }).reset_index()
        actual_by_sku.columns = ['sku', 'actual_qty']

        # Merge with forecasts
        comparison = pd.merge(
            snapshot_forecasts[['sku', 'category', 'forecast_total_qty', 'forecast_method', 'forecast_confidence']],
            actual_by_sku,
            on='sku',
            how='left'
        )

        comparison['actual_qty'] = comparison['actual_qty'].fillna(0)
        comparison['snapshot_date'] = snapshot_date
        comparison['forecast_period_days'] = forecast_horizon

        # Calculate error metrics
        comparison['error'] = comparison['actual_qty'] - comparison['forecast_total_qty']
        comparison['abs_error'] = comparison['error'].abs()
        comparison['pct_error'] = comparison.apply(
            lambda row: ((row['error'] / row['actual_qty']) * 100) if row['actual_qty'] > 0 else (100 if row['forecast_total_qty'] > 0 else 0),
            axis=1
        )
        comparison['abs_pct_error'] = comparison['pct_error'].abs()

        comparison_list.append(comparison)

    if not comparison_list:
        return pd.DataFrame()

    # Combine all comparisons
    all_comparisons = pd.concat(comparison_list, ignore_index=True)

    return all_comparisons


def calculate_forecast_bias(comparison_df):
    """
    Calculate forecast bias metrics (over/under forecasting)

    Args:
        comparison_df: Comparison dataframe from compare_forecast_vs_actual()

    Returns:
        dict: Bias metrics
    """
    if comparison_df.empty:
        return {}

    total_forecast = comparison_df['forecast_total_qty'].sum()
    total_actual = comparison_df['actual_qty'].sum()

    bias = ((total_forecast - total_actual) / total_actual * 100) if total_actual > 0 else 0

    avg_pct_error = comparison_df['pct_error'].mean()
    avg_abs_pct_error = comparison_df['abs_pct_error'].mean()

    return {
        'total_forecast': total_forecast,
        'total_actual': total_actual,
        'bias_pct': bias,
        'bias_direction': 'Over-forecasting' if bias > 0 else ('Under-forecasting' if bias < 0 else 'Neutral'),
        'avg_error_pct': avg_pct_error,
        'avg_abs_error_pct': avg_abs_pct_error,
        'num_comparisons': len(comparison_df)
    }


def aggregate_demand_by_category(daily_demand_df, category_mapping_df):
    """
    Aggregate SKU-level daily demand to category level

    Args:
        daily_demand_df: Daily demand dataframe with columns: sku, date, demand_qty
        category_mapping_df: Dataframe with sku to category mapping

    Returns:
        pd.DataFrame: Category-level daily demand
    """
    if daily_demand_df.empty:
        return pd.DataFrame()

    # Merge with category mapping
    demand_with_category = pd.merge(
        daily_demand_df,
        category_mapping_df[['sku', 'category']],
        on='sku',
        how='left'
    )

    # Fill missing categories
    demand_with_category['category'] = demand_with_category['category'].fillna('Uncategorized')

    # Aggregate by category and date
    category_demand = demand_with_category.groupby(['category', 'date']).agg({
        'demand_qty': 'sum'
    }).reset_index()

    return category_demand
