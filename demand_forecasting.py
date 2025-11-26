"""
Demand Forecasting Module

Generates statistical demand forecasts using historical delivery data.
Uses simple, interpretable methods: moving averages and exponential smoothing.

Key Features:
- 30/60/90 day moving average forecasts
- Simple exponential smoothing with anomaly detection
- Forecast accuracy metrics (MAPE, MAE, RMSE)
- Demand trend and seasonality detection
- SKU-level and aggregate forecasting
- Configurable smoothing presets (Conservative, Balanced, Aggressive)

Performance Optimizations:
- Numba JIT compilation for numeric operations (5-10x speedup)
- Batch vectorization to minimize groupby.apply() calls
- Parallel processing with joblib for multi-core execution
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st
import os

# Performance optimization imports
try:
    from numba import jit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    # Fallback decorator that does nothing
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    prange = range

try:
    from joblib import Parallel, delayed
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

TODAY = pd.to_datetime(datetime.now().date())
SNAPSHOT_FOLDER = "data/forecast_snapshots"


# ===== EDGE CASE HANDLING CONSTANTS =====
# Professional demand planner safeguards for anomaly detection

# Minimum sample size: Require 30+ data points before applying anomaly detection
# Rationale: Z-score statistics require sufficient sample size for validity
MIN_ANOMALY_DETECTION_SAMPLE_SIZE = 30

# Maximum anomaly percentage: If more than 20% of data is flagged as anomalies,
# the data pattern may not be suitable for Z-score detection
MAX_ANOMALY_PERCENTAGE = 0.20

# Intermittent demand threshold: SKUs with CV > 150% are classified as intermittent
# These require special handling with higher Z-thresholds
INTERMITTENT_DEMAND_CV_THRESHOLD = 150

# Higher Z-threshold for intermittent demand to avoid over-flagging zeros/spikes
INTERMITTENT_DEMAND_Z_THRESHOLD = 4.0

# Minimum months of history required for individual SKU seasonality profiles
MIN_MONTHS_FOR_SEASONALITY = 12


# ===== SMOOTHING PRESETS CONFIGURATION =====
# Simplified to 3 presets aligned with seasonal planning cycles
# For 9-month lead time supply chains with seasonal demand patterns

SMOOTHING_PRESETS = {
    'Conservative': {
        'z_score_threshold': 1.5,   # Flags ~6.5% as anomalies
        'alpha': 0.03,              # ~33 period effective window (~12 months for monthly data)
        'description': 'Heavy smoothing for stable, predictable items. Uses ~12 months of history.'
    },
    'Balanced': {
        'z_score_threshold': 2.0,   # Flags ~4.4% as anomalies
        'alpha': 0.08,              # ~12 period effective window (~6 months for monthly data)
        'description': 'Moderate smoothing for typical demand patterns. Recommended default.'
    },
    'Aggressive': {
        'z_score_threshold': 2.5,   # Flags ~3% as anomalies
        'alpha': 0.15,              # ~7 period effective window (~3 months for monthly data)
        'description': 'Lighter smoothing for trending or volatile items. Responds faster to changes.'
    }
}

DEFAULT_SMOOTHING_PRESET = 'Balanced'


# ===== NUMBA JIT-COMPILED FUNCTIONS FOR SPEED =====
# These functions are optimized for numerical computation using JIT compilation

@jit(nopython=True, cache=True)
def _exp_smooth_jit(values: np.ndarray, alpha: float) -> float:
    """JIT-compiled exponential smoothing - 5-10x faster than pure Python"""
    if len(values) == 0:
        return 0.0
    smoothed = values[0]
    for i in range(1, len(values)):
        smoothed = alpha * values[i] + (1.0 - alpha) * smoothed
    return smoothed


@jit(nopython=True, cache=True)
def _detect_anomalies_jit(values: np.ndarray, z_threshold: float) -> tuple:
    """
    JIT-compiled anomaly detection - returns (is_anomaly_array, count, mean, std, cv)
    """
    n = len(values)
    is_anomaly = np.zeros(n, dtype=np.bool_)

    if n < 3:
        return is_anomaly, 0, 0.0, 0.0, 0.0

    # Calculate mean and std
    mean = 0.0
    for i in range(n):
        mean += values[i]
    mean /= n

    variance = 0.0
    for i in range(n):
        diff = values[i] - mean
        variance += diff * diff
    variance /= n
    std = np.sqrt(variance)

    if std == 0:
        return is_anomaly, 0, mean, std, 0.0

    # Calculate CV
    cv = (std / mean * 100.0) if mean > 0 else 0.0

    # Detect anomalies
    count = 0
    for i in range(n):
        z_score = abs((values[i] - mean) / std)
        if z_score > z_threshold:
            is_anomaly[i] = True
            count += 1

    return is_anomaly, count, mean, std, cv


@jit(nopython=True, cache=True)
def _smooth_anomalies_median_jit(values: np.ndarray, is_anomaly: np.ndarray) -> np.ndarray:
    """JIT-compiled anomaly smoothing using median replacement"""
    result = values.copy()
    n = len(values)

    # Count non-anomalies and collect their values
    non_anomaly_count = 0
    for i in range(n):
        if not is_anomaly[i]:
            non_anomaly_count += 1

    if non_anomaly_count == 0:
        return result

    # Collect non-anomaly values
    non_anomaly_values = np.empty(non_anomaly_count, dtype=np.float64)
    idx = 0
    for i in range(n):
        if not is_anomaly[i]:
            non_anomaly_values[idx] = values[i]
            idx += 1

    # Calculate median
    sorted_vals = np.sort(non_anomaly_values)
    if non_anomaly_count % 2 == 0:
        median = (sorted_vals[non_anomaly_count // 2 - 1] + sorted_vals[non_anomaly_count // 2]) / 2
    else:
        median = sorted_vals[non_anomaly_count // 2]

    # Replace anomalies with median
    for i in range(n):
        if is_anomaly[i]:
            result[i] = median

    return result


@jit(nopython=True, cache=True)
def _calculate_trend_jit(values: np.ndarray) -> float:
    """JIT-compiled linear trend calculation (slope of best fit line)"""
    n = len(values)
    if n < 2:
        return 0.0

    # Simple linear regression slope
    sum_x = 0.0
    sum_y = 0.0
    sum_xy = 0.0
    sum_xx = 0.0

    for i in range(n):
        x = float(i)
        y = values[i]
        sum_x += x
        sum_y += y
        sum_xy += x * y
        sum_xx += x * x

    denominator = n * sum_xx - sum_x * sum_x
    if abs(denominator) < 1e-10:
        return 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope


def _process_single_sku_smoothing(sku_values: np.ndarray, z_threshold: float, alpha: float,
                                   cv_threshold: float, intermittent_z: float,
                                   min_sample_size: int, max_anomaly_pct: float) -> dict:
    """
    Process smoothing for a single SKU with all edge case handling.
    Optimized to use JIT-compiled functions internally.
    """
    n = len(sku_values)
    warnings = []

    # Edge case 1: Minimum sample size
    if n < min_sample_size:
        # Skip anomaly detection, just apply exp smoothing
        smoothed = _exp_smooth_jit(sku_values.astype(np.float64), alpha) if n > 0 else 0.0
        return {
            'exp_smooth': smoothed,
            'anomaly_count': 0,
            'anomaly_pct': 0.0,
            'is_intermittent': False,
            'skipped_detection': True,
            'applied_z_threshold': z_threshold,
            'warnings': f"Insufficient data ({n} points). Minimum {min_sample_size} required."
        }

    # Run JIT anomaly detection to get CV
    is_anomaly, count, mean, std, cv = _detect_anomalies_jit(sku_values.astype(np.float64), z_threshold)

    # Edge case 2: Intermittent demand (CV > threshold)
    is_intermittent = cv > cv_threshold
    effective_z = intermittent_z if is_intermittent else z_threshold

    # Re-run detection with adjusted threshold if intermittent
    if is_intermittent:
        is_anomaly, count, mean, std, cv = _detect_anomalies_jit(sku_values.astype(np.float64), effective_z)
        warnings.append(f"Intermittent demand (CV={cv:.0f}%). Using Z={effective_z}.")

    anomaly_pct = count / n if n > 0 else 0.0

    # Edge case 3: High anomaly rate warning
    if anomaly_pct > max_anomaly_pct:
        warnings.append(f"High anomaly rate ({anomaly_pct*100:.1f}% > {max_anomaly_pct*100:.0f}%).")

    # Smooth anomalies and apply exp smoothing
    cleaned = _smooth_anomalies_median_jit(sku_values.astype(np.float64), is_anomaly)
    smoothed = _exp_smooth_jit(cleaned, alpha)

    return {
        'exp_smooth': smoothed,
        'anomaly_count': int(count),
        'anomaly_pct': anomaly_pct,
        'is_intermittent': is_intermittent,
        'skipped_detection': False,
        'applied_z_threshold': effective_z,
        'warnings': ','.join(warnings) if warnings else ''
    }


def _batch_process_sku_smoothing(grouped_data: dict, z_threshold: float, alpha: float,
                                  cv_threshold: float, intermittent_z: float,
                                  min_sample_size: int, max_anomaly_pct: float,
                                  use_parallel: bool = True) -> pd.DataFrame:
    """
    Batch process all SKUs with optional parallel execution.

    Args:
        grouped_data: Dict of {sku: values_array}
        Other params: Smoothing configuration
        use_parallel: Whether to use joblib parallel processing

    Returns:
        DataFrame with columns: sku, exp_smooth, anomaly_count, anomaly_pct,
                               is_intermittent, skipped_detection, applied_z_threshold, warnings
    """
    skus = list(grouped_data.keys())

    if use_parallel and JOBLIB_AVAILABLE and len(skus) > 50:
        # Use parallel processing for large datasets
        n_jobs = min(4, len(skus) // 50)  # Limit to 4 cores, only parallelize if worth it
        results = Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_process_single_sku_smoothing)(
                grouped_data[sku], z_threshold, alpha, cv_threshold,
                intermittent_z, min_sample_size, max_anomaly_pct
            ) for sku in skus
        )
    else:
        # Sequential processing
        results = [
            _process_single_sku_smoothing(
                grouped_data[sku], z_threshold, alpha, cv_threshold,
                intermittent_z, min_sample_size, max_anomaly_pct
            ) for sku in skus
        ]

    # Build DataFrame from results
    df = pd.DataFrame(results)
    df['sku'] = skus
    return df[['sku', 'exp_smooth', 'anomaly_count', 'anomaly_pct',
               'is_intermittent', 'skipped_detection', 'applied_z_threshold', 'warnings']]


def _batch_calculate_trends(grouped_data: dict, use_parallel: bool = True) -> pd.DataFrame:
    """
    Batch calculate trend slopes for all SKUs.

    Args:
        grouped_data: Dict of {sku: values_array}
        use_parallel: Whether to use joblib parallel processing

    Returns:
        DataFrame with columns: sku, demand_trend_slope
    """
    skus = list(grouped_data.keys())

    if use_parallel and JOBLIB_AVAILABLE and len(skus) > 50:
        n_jobs = min(4, len(skus) // 50)
        slopes = Parallel(n_jobs=n_jobs, prefer="threads")(
            delayed(_calculate_trend_jit)(grouped_data[sku].astype(np.float64)) for sku in skus
        )
    else:
        slopes = [_calculate_trend_jit(grouped_data[sku].astype(np.float64)) for sku in skus]

    return pd.DataFrame({'sku': skus, 'demand_trend_slope': slopes})


def get_smoothing_config(preset_name: str = None) -> dict:
    """
    Get smoothing configuration for the specified preset.

    Args:
        preset_name: One of 'Conservative', 'Balanced', 'Aggressive'.
                    Defaults to 'Balanced' if not specified or invalid.

    Returns:
        dict: Configuration with z_score_threshold, alpha, and description
    """
    if preset_name is None or preset_name not in SMOOTHING_PRESETS:
        preset_name = DEFAULT_SMOOTHING_PRESET
    return SMOOTHING_PRESETS[preset_name].copy()


def detect_anomalies(values: np.ndarray, z_threshold: float = 2.0,
                     check_intermittent: bool = True) -> dict:
    """
    Detect anomalies in a time series using Z-score method with edge case handling.

    Edge case handling (professional demand planner safeguards):
    1. Minimum sample size: Skip anomaly detection if < 30 data points
    2. Intermittent demand: Use higher Z-threshold (4.0) for CV > 150%
    3. Anomaly cap: Flag warning if > 20% of data are anomalies

    Args:
        values: Array of numerical values (e.g., daily demand quantities)
        z_threshold: Z-score threshold above which values are flagged as anomalies
        check_intermittent: Whether to apply intermittent demand handling (default True)

    Returns:
        dict: {
            'is_anomaly': Boolean array where True indicates an anomaly,
            'anomaly_count': Number of anomalies detected,
            'anomaly_pct': Percentage of data flagged as anomalies,
            'warnings': List of warning messages,
            'applied_z_threshold': The actual Z-threshold used,
            'is_intermittent': Whether intermittent demand handling was applied,
            'skipped_detection': Whether anomaly detection was skipped
        }
    """
    result = {
        'is_anomaly': np.zeros(len(values), dtype=bool),
        'anomaly_count': 0,
        'anomaly_pct': 0.0,
        'warnings': [],
        'applied_z_threshold': z_threshold,
        'is_intermittent': False,
        'skipped_detection': False
    }

    # Edge case 1: Minimum sample size check
    if len(values) < MIN_ANOMALY_DETECTION_SAMPLE_SIZE:
        result['skipped_detection'] = True
        result['warnings'].append(
            f"Insufficient data ({len(values)} points). Minimum {MIN_ANOMALY_DETECTION_SAMPLE_SIZE} required for anomaly detection."
        )
        return result

    if len(values) < 3:
        result['skipped_detection'] = True
        return result

    mean = np.mean(values)
    std = np.std(values)

    if std == 0:
        return result

    # Edge case 2: Check for intermittent demand (CV > 150%)
    cv = (std / mean * 100) if mean > 0 else 0

    effective_z_threshold = z_threshold
    if check_intermittent and cv > INTERMITTENT_DEMAND_CV_THRESHOLD:
        result['is_intermittent'] = True
        effective_z_threshold = INTERMITTENT_DEMAND_Z_THRESHOLD
        result['applied_z_threshold'] = effective_z_threshold
        result['warnings'].append(
            f"Intermittent demand detected (CV={cv:.0f}%). Using higher Z-threshold ({effective_z_threshold}) to avoid over-flagging."
        )

    z_scores = np.abs((values - mean) / std)
    is_anomaly = z_scores > effective_z_threshold

    result['is_anomaly'] = is_anomaly
    result['anomaly_count'] = int(is_anomaly.sum())
    result['anomaly_pct'] = result['anomaly_count'] / len(values) if len(values) > 0 else 0

    # Edge case 3: Anomaly cap warning (> 20%)
    if result['anomaly_pct'] > MAX_ANOMALY_PERCENTAGE:
        result['warnings'].append(
            f"High anomaly rate ({result['anomaly_pct']*100:.1f}% > {MAX_ANOMALY_PERCENTAGE*100:.0f}% threshold). "
            f"Review data for systematic issues. Export available for detailed analysis."
        )

    return result


def detect_anomalies_simple(values: np.ndarray, z_threshold: float = 2.0) -> np.ndarray:
    """
    Simple anomaly detection returning only boolean array (for backward compatibility).

    Args:
        values: Array of numerical values
        z_threshold: Z-score threshold

    Returns:
        np.ndarray: Boolean array where True indicates an anomaly
    """
    result = detect_anomalies(values, z_threshold, check_intermittent=False)
    return result['is_anomaly']


def smooth_anomalies(values: np.ndarray, is_anomaly: np.ndarray, method: str = 'median') -> np.ndarray:
    """
    Replace anomalous values with smoothed values.

    Args:
        values: Original array of values
        is_anomaly: Boolean array indicating which values are anomalies
        method: Smoothing method - 'median' (replace with median) or 'neighbor' (average of neighbors)

    Returns:
        np.ndarray: Array with anomalies replaced by smoothed values
    """
    smoothed = values.copy()

    if not is_anomaly.any():
        return smoothed

    if method == 'median':
        # Replace anomalies with median of non-anomalous values
        non_anomaly_values = values[~is_anomaly]
        if len(non_anomaly_values) > 0:
            replacement = np.median(non_anomaly_values)
            smoothed[is_anomaly] = replacement
    elif method == 'neighbor':
        # Replace anomalies with average of nearest non-anomaly neighbors
        anomaly_indices = np.where(is_anomaly)[0]
        for idx in anomaly_indices:
            # Find nearest non-anomaly neighbors
            left_val = None
            right_val = None
            for i in range(idx - 1, -1, -1):
                if not is_anomaly[i]:
                    left_val = values[i]
                    break
            for i in range(idx + 1, len(values)):
                if not is_anomaly[i]:
                    right_val = values[i]
                    break

            if left_val is not None and right_val is not None:
                smoothed[idx] = (left_val + right_val) / 2
            elif left_val is not None:
                smoothed[idx] = left_val
            elif right_val is not None:
                smoothed[idx] = right_val
            # If no neighbors found, leave original value

    return smoothed


def apply_demand_smoothing(values: np.ndarray, preset: str = 'Balanced') -> dict:
    """
    Apply two-step demand smoothing: detect anomalies, then apply exponential smoothing.

    Includes professional demand planner edge case handling:
    1. Minimum sample size (30+) check before anomaly detection
    2. Intermittent demand handling (CV > 150% uses Z=4.0)
    3. High anomaly percentage (> 20%) warnings

    Args:
        values: Array of demand values (chronologically ordered)
        preset: Smoothing preset - 'Conservative', 'Balanced', or 'Aggressive'

    Returns:
        dict: {
            'smoothed_forecast': Final smoothed forecast value,
            'anomaly_count': Number of anomalies detected,
            'anomaly_pct': Percentage of values flagged as anomalies,
            'config': Configuration used,
            'warnings': List of warning messages (edge case indicators),
            'is_intermittent': Whether intermittent demand handling was applied,
            'skipped_detection': Whether anomaly detection was skipped,
            'applied_z_threshold': The actual Z-threshold used
        }
    """
    config = get_smoothing_config(preset)

    result = {
        'smoothed_forecast': 0,
        'anomaly_count': 0,
        'anomaly_pct': 0.0,
        'config': config,
        'warnings': [],
        'is_intermittent': False,
        'skipped_detection': False,
        'applied_z_threshold': config['z_score_threshold']
    }

    if len(values) == 0:
        return result

    # Step 1: Detect anomalies using Z-score with edge case handling
    detection_result = detect_anomalies(
        values,
        z_threshold=config['z_score_threshold'],
        check_intermittent=True
    )

    result['anomaly_count'] = detection_result['anomaly_count']
    result['anomaly_pct'] = detection_result['anomaly_pct']
    result['warnings'] = detection_result['warnings']
    result['is_intermittent'] = detection_result['is_intermittent']
    result['skipped_detection'] = detection_result['skipped_detection']
    result['applied_z_threshold'] = detection_result['applied_z_threshold']

    # Step 2: Smooth out anomalies (replace with median of non-anomalies)
    # If detection was skipped, no anomalies to smooth
    if detection_result['skipped_detection']:
        cleaned_values = values.copy()
    else:
        cleaned_values = smooth_anomalies(values, detection_result['is_anomaly'], method='median')

    # Step 3: Apply exponential smoothing to cleaned data
    smoothed_forecast = calculate_exponential_smoothing(cleaned_values, alpha=config['alpha'])
    result['smoothed_forecast'] = smoothed_forecast

    return result


def apply_demand_smoothing_simple(values: np.ndarray, preset: str = 'Balanced') -> tuple:
    """
    Simple version of apply_demand_smoothing for backward compatibility.

    Args:
        values: Array of demand values
        preset: Smoothing preset

    Returns:
        tuple: (smoothed_forecast, anomaly_count, smoothing_config)
    """
    result = apply_demand_smoothing(values, preset)
    return result['smoothed_forecast'], result['anomaly_count'], result['config']


@st.cache_data(show_spinner="Generating demand forecasts...")
def generate_demand_forecast(deliveries_df, master_data_df=None, forecast_horizon_days=90,
                             ts_granularity: str = 'daily', rolling_months: int | None = None,
                             smoothing_preset: str = 'Balanced'):
    """
    Generate demand forecasts using historical delivery data

    Args:
        deliveries_df: Historical deliveries dataframe with columns: sku, delivery_date, delivered_qty
        master_data_df: Master data dataframe with SKU metadata (category, description, etc.)
        forecast_horizon_days: Number of days to forecast ahead (default 90)
        ts_granularity: Time series granularity - 'daily' or 'monthly'
        rolling_months: Restrict data to last N months
        smoothing_preset: Anomaly smoothing preset - 'Conservative', 'Balanced', or 'Aggressive'
                         (default: 'Balanced')

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
    # prefer Goods Issue Date where present; otherwise fall back to Delivery Creation Date or ship_date
    if 'Goods Issue Date: Date' in df.columns:
        df['delivery_date'] = df['Goods Issue Date: Date']
    elif 'Delivery Creation Date: Date' in df.columns:
        df['delivery_date'] = df['Delivery Creation Date: Date']
    elif 'Ship Date: Date' in df.columns:
        df['delivery_date'] = df['Ship Date: Date']
    elif 'ship_date' in df.columns:
        df['delivery_date'] = df['ship_date']
    elif 'delivery_date' not in df.columns:
        logs.append("ERROR: No delivery date column found in deliveries data")
        return logs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    if 'Deliveries - TOTAL Goods Issue Qty' in df.columns:
        df['delivered_qty'] = pd.to_numeric(df['Deliveries - TOTAL Goods Issue Qty'], errors='coerce').fillna(0)
    elif 'units_issued' in df.columns:
        df['delivered_qty'] = pd.to_numeric(df['units_issued'], errors='coerce').fillna(0)
    else:
        # Fallback: try to convert existing delivered_qty column or use 0
        if 'delivered_qty' in df.columns:
            df['delivered_qty'] = pd.to_numeric(df['delivered_qty'], errors='coerce').fillna(0)
        else:
            df['delivered_qty'] = 0

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

    # ===== STEP 2: Aggregate Daily Demand by SKU (base time series) =====
    logs.append("INFO: Aggregating daily demand by SKU...")

    # Create daily demand time series per SKU
    daily_demand = df.groupby(['sku', 'delivery_date']).agg({'delivered_qty': 'sum'}).reset_index()
    daily_demand.columns = ['sku', 'date', 'demand_qty']

    # Keep a copy of the pure daily series for downstream analysis; we'll transform
    # into monthly aggregation if requested by ts_granularity.
    base_daily = daily_demand.copy()

    # If the caller requested a monthly time series, aggregate daily demand to months.
    if str(ts_granularity).lower() in ['monthly', 'rolling_monthly', 'rolling_12', 'rolling_12_months']:
        logs.append("INFO: Aggregating daily series to monthly buckets for time-series view.")
        # Convert date to period month and standardize to month-start timestamp
        daily_demand['month'] = daily_demand['date'].dt.to_period('M').dt.to_timestamp()
        daily_monthly = daily_demand.groupby(['sku', 'month'], as_index=False).agg({'demand_qty': 'sum'})
        daily_monthly.columns = ['sku', 'date', 'demand_qty']

        # If rolling_months requested, restrict to the recent window
        if rolling_months and rolling_months > 0:
            # Use the application TODAY as the window anchor so 'rolling 12 months'
            # is always relative to current date/time (more intuitive for users)
            max_date = TODAY
            # compute earliest month to keep using today's month as the endpoint
            earliest = (max_date - pd.DateOffset(months=rolling_months - 1)).replace(day=1)
            daily_monthly = daily_monthly[daily_monthly['date'] >= earliest]
            logs.append(f"INFO: Restricting monthly series to last {rolling_months} months (>= {earliest.date()}).")

        # Use monthly aggregated series as 'daily_demand' return value
        daily_demand = daily_monthly.copy()
    else:
        # Optionally, if daily is returned and rolling_months is provided, we can restrict
        # daily series to last N months (rolling_months) if requested.
        if rolling_months and rolling_months > 0:
            max_date = base_daily['date'].max()
            earliest = (max_date - pd.DateOffset(months=rolling_months - 1)).replace(day=1)
            # keep records within the rolling months window
            daily_demand = base_daily[base_daily['date'] >= earliest]
            logs.append(f"INFO: Restricting daily series to last {rolling_months} months (>= {earliest.date()}).")

    logs.append(f"INFO: Created daily demand series for {daily_demand['sku'].nunique()} SKUs")

    # ===== STEP 3: Calculate Moving Averages =====
    # Adjust thresholds and windows based on granularity
    is_monthly = str(ts_granularity).lower() in ['monthly', 'rolling_monthly', 'rolling_12', 'rolling_12_months']

    if is_monthly:
        # For monthly data: need 3 months minimum, use 3/6/12 month windows
        min_periods_required = 3
        ma_short_window = 3
        ma_medium_window = 6
        ma_long_window = 12
        ma_short_label = 'MA-3M'
        ma_medium_label = 'MA-6M'
        ma_long_label = 'MA-12M'
        logs.append("INFO: Using monthly forecast windows (3/6/12 months)...")
    else:
        # For daily data: need 30 days minimum, use 30/60/90 day windows
        min_periods_required = 30
        ma_short_window = 30
        ma_medium_window = 60
        ma_long_window = 90
        ma_short_label = 'MA-30'
        ma_medium_label = 'MA-60'
        ma_long_label = 'MA-90'
        logs.append("INFO: Using daily forecast windows (30/60/90 days)...")

    # PERFORMANCE: Vectorized forecast calculation using groupby operations
    # This is 5-20x faster than looping through each SKU individually

    # Sort once for all operations
    daily_demand_sorted = daily_demand.sort_values(['sku', 'date'])

    # Pre-calculate rolling MAs for all SKUs at once using groupby transform
    daily_demand_sorted['ma_short_rolling'] = daily_demand_sorted.groupby('sku')['demand_qty'].transform(
        lambda x: x.rolling(window=ma_short_window, min_periods=1).mean()
    )
    daily_demand_sorted['ma_medium_rolling'] = daily_demand_sorted.groupby('sku')['demand_qty'].transform(
        lambda x: x.rolling(window=ma_medium_window, min_periods=1).mean()
    )
    daily_demand_sorted['ma_long_rolling'] = daily_demand_sorted.groupby('sku')['demand_qty'].transform(
        lambda x: x.rolling(window=ma_long_window, min_periods=1).mean()
    )

    # Get last values per SKU (the final MA values we need)
    last_values = daily_demand_sorted.groupby('sku').agg({
        'ma_short_rolling': 'last',
        'ma_medium_rolling': 'last',
        'ma_long_rolling': 'last',
        'demand_qty': ['sum', 'mean', 'std', 'count'],
        'date': 'max'
    })

    # Flatten multi-level columns
    last_values.columns = ['ma_short', 'ma_medium', 'ma_long', 'total_demand',
                           'avg_period_demand', 'std_period_demand', 'period_count', 'last_date']
    last_values = last_values.reset_index()

    # Filter SKUs with insufficient history
    last_values = last_values[last_values['period_count'] >= min_periods_required]

    if last_values.empty:
        min_req_label = "3 months" if is_monthly else "30 days"
        logs.append(f"WARNING: No SKUs had sufficient data for forecasting (minimum {min_req_label} required)")
        return logs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Calculate CV vectorized
    last_values['demand_cv'] = np.where(
        last_values['avg_period_demand'] > 0,
        last_values['std_period_demand'] / last_values['avg_period_demand'] * 100,
        0
    )

    # ===== OPTIMIZED: Batch processing with JIT compilation =====
    # Pre-extract all SKU demand arrays once (avoid repeated groupby)
    logs.append("INFO: Using optimized batch processing with JIT compilation...")
    sku_demand_dict = {sku: grp['demand_qty'].values for sku, grp in daily_demand_sorted.groupby('sku')}

    # Calculate trend slopes using batch processing with JIT-compiled functions
    trend_slopes = _batch_calculate_trends(sku_demand_dict, use_parallel=JOBLIB_AVAILABLE)
    last_values = last_values.merge(trend_slopes, on='sku', how='left')
    last_values['demand_trend_slope'] = pd.to_numeric(last_values['demand_trend_slope'], errors='coerce').fillna(0)

    # Calculate exponential smoothing per SKU with anomaly detection
    # Uses the smoothing_preset parameter to configure anomaly detection and smoothing
    smoothing_config = get_smoothing_config(smoothing_preset)
    logs.append(f"INFO: Using '{smoothing_preset}' smoothing preset (Z-threshold: {smoothing_config['z_score_threshold']}, Alpha: {smoothing_config['alpha']})")

    # Batch process all SKUs with JIT-compiled functions + optional parallel execution
    exp_smooths = _batch_process_sku_smoothing(
        grouped_data=sku_demand_dict,
        z_threshold=smoothing_config['z_score_threshold'],
        alpha=smoothing_config['alpha'],
        cv_threshold=INTERMITTENT_DEMAND_CV_THRESHOLD,
        intermittent_z=INTERMITTENT_DEMAND_Z_THRESHOLD,
        min_sample_size=MIN_ANOMALY_DETECTION_SAMPLE_SIZE,
        max_anomaly_pct=MAX_ANOMALY_PERCENTAGE,
        use_parallel=JOBLIB_AVAILABLE
    )
    last_values = last_values.merge(exp_smooths, on='sku', how='left')

    # Log anomaly statistics
    total_anomalies = last_values['anomaly_count'].sum()
    skus_with_anomalies = (last_values['anomaly_count'] > 0).sum()
    skus_skipped_detection = last_values['skipped_detection'].sum() if 'skipped_detection' in last_values.columns else 0
    skus_intermittent = last_values['is_intermittent'].sum() if 'is_intermittent' in last_values.columns else 0
    skus_high_anomaly_pct = (last_values['anomaly_pct'] > MAX_ANOMALY_PERCENTAGE).sum() if 'anomaly_pct' in last_values.columns else 0

    logs.append(f"INFO: Detected {int(total_anomalies)} anomalies across {skus_with_anomalies} SKUs")

    # Log edge case handling statistics
    if skus_skipped_detection > 0:
        logs.append(f"INFO: Skipped anomaly detection for {int(skus_skipped_detection)} SKUs (insufficient data < {MIN_ANOMALY_DETECTION_SAMPLE_SIZE} points)")
    if skus_intermittent > 0:
        logs.append(f"INFO: Applied intermittent demand handling for {int(skus_intermittent)} SKUs (CV > {INTERMITTENT_DEMAND_CV_THRESHOLD}%)")
    if skus_high_anomaly_pct > 0:
        logs.append(f"WARNING: {int(skus_high_anomaly_pct)} SKUs have high anomaly rates (> {MAX_ANOMALY_PERCENTAGE*100:.0f}%). Review recommended.")

    # Determine forecast method vectorized
    last_values['forecast_method'] = np.where(
        last_values['period_count'] >= ma_long_window, ma_long_label,
        np.where(last_values['period_count'] >= ma_medium_window, ma_medium_label, ma_short_label)
    )

    last_values['primary_forecast'] = np.where(
        last_values['period_count'] >= ma_long_window, last_values['ma_long'],
        np.where(last_values['period_count'] >= ma_medium_window, last_values['ma_medium'], last_values['ma_short'])
    )

    # Convert to daily equivalent and calculate forecast totals
    if is_monthly:
        last_values['avg_daily_demand'] = last_values['primary_forecast'] / 30.0
        last_values['std_daily'] = last_values['std_period_demand'] / 30.0
        # Also convert exp_smooth to daily equivalent for monthly data
        last_values['exp_smooth_daily'] = last_values['exp_smooth'] / 30.0
    else:
        last_values['avg_daily_demand'] = last_values['primary_forecast']
        last_values['std_daily'] = last_values['std_period_demand']
        # For daily data, exp_smooth is already daily
        last_values['exp_smooth_daily'] = last_values['exp_smooth']

    last_values['forecast_total_qty'] = last_values['avg_daily_demand'] * forecast_horizon_days

    # Confidence bounds
    last_values['forecast_lower_bound'] = np.maximum(
        0, (last_values['avg_daily_demand'] - last_values['std_daily']) * forecast_horizon_days
    )
    last_values['forecast_upper_bound'] = (last_values['avg_daily_demand'] + last_values['std_daily']) * forecast_horizon_days

    # Classify demand pattern vectorized
    last_values['demand_pattern'] = last_values.apply(
        lambda row: classify_demand_pattern(row['demand_cv'], row['demand_trend_slope']), axis=1
    )

    # Build final forecast dataframe
    forecast_df = pd.DataFrame({
        'sku': last_values['sku'],
        'forecast_method': last_values['forecast_method'],
        'avg_daily_demand': last_values['avg_daily_demand'],
        'ma_short': last_values['ma_short'],
        'ma_medium': last_values['ma_medium'],
        'ma_long': last_values['ma_long'],
        'exp_smooth': last_values['exp_smooth_daily'],  # Use daily-converted value
        'primary_forecast_daily': last_values['avg_daily_demand'],
        'forecast_total_qty': last_values['forecast_total_qty'],
        'forecast_lower_bound': last_values['forecast_lower_bound'],
        'forecast_upper_bound': last_values['forecast_upper_bound'],
        'forecast_horizon_days': forecast_horizon_days,
        'historical_days': last_values['period_count'],
        'total_historical_demand': last_values['total_demand'],
        'demand_std': last_values['std_period_demand'],
        'demand_cv': last_values['demand_cv'],
        'demand_trend_slope': last_values['demand_trend_slope'],
        'demand_pattern': last_values['demand_pattern'],
        'last_delivery_date': last_values['last_date'],
        'anomaly_count': last_values['anomaly_count'],
        'anomaly_pct': last_values['anomaly_pct'],
        'is_intermittent': last_values['is_intermittent'],
        'skipped_detection': last_values['skipped_detection'],
        'applied_z_threshold': last_values['applied_z_threshold'],
        'smoothing_preset': smoothing_preset
    })

    # Build warnings dataframe from the merged data for UI export capability
    if 'warnings' in last_values.columns:
        warnings_data = []
        for _, row in last_values[last_values['warnings'] != ''].iterrows():
            sku = row['sku']
            for warning in row['warnings'].split(','):
                if warning.strip():
                    warnings_data.append({'sku': sku, 'warning': warning.strip()})
        warnings_df = pd.DataFrame(warnings_data) if warnings_data else pd.DataFrame(columns=['sku', 'warning'])
    else:
        warnings_df = pd.DataFrame(columns=['sku', 'warning'])

    logs.append(f"INFO: Generated forecasts for {len(forecast_df)} SKUs")

    if forecast_df.empty:
        min_req_label = "3 months" if is_monthly else "30 days"
        logs.append(f"WARNING: No SKUs had sufficient data for forecasting (minimum {min_req_label} required)")
        return logs, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ===== STEP 4: Calculate Forecast Accuracy (Backtest) =====
    logs.append("INFO: Calculating forecast accuracy using backtesting...")

    # Adjust backtesting threshold based on granularity
    backtest_min_periods = 6 if is_monthly else 60  # 6 months or 60 days

    # PERFORMANCE: Vectorized accuracy calculation using groupby
    def calculate_accuracy_for_group(group):
        if len(group) < backtest_min_periods:
            return None
        group = group.sort_values('date')
        split_idx = int(len(group) * 0.8)
        train_data = group.iloc[:split_idx]
        test_data = group.iloc[split_idx:]
        train_ma = train_data['demand_qty'].rolling(window=ma_short_window, min_periods=1).mean().iloc[-1]
        actual_avg = test_data['demand_qty'].mean()
        mape = calculate_mape(actual_avg, train_ma)
        return pd.Series({
            'actual_avg_demand': actual_avg,
            'forecast_avg_demand': train_ma,
            'mape': mape,
            'mae': abs(actual_avg - train_ma),
            'rmse': np.sqrt((actual_avg - train_ma) ** 2),
            'test_period_days': len(test_data)
        })

    # Filter to SKUs in forecast
    forecast_skus = set(forecast_df['sku'].unique())
    daily_demand_filtered = daily_demand[daily_demand['sku'].isin(forecast_skus)]

    accuracy_results = daily_demand_filtered.groupby('sku').apply(calculate_accuracy_for_group)
    accuracy_df = accuracy_results.dropna().reset_index()

    if accuracy_df.empty or 'sku' not in accuracy_df.columns:
        accuracy_df = pd.DataFrame(columns=['sku', 'actual_avg_demand', 'forecast_avg_demand', 'mape', 'mae', 'rmse', 'test_period_days'])

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
        elif 'Material Number' in master_data_clean.columns:
            master_data_clean['sku'] = master_data_clean['Material Number'].astype(str).str.strip()
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

    # ===== STEP 7: Build Seasonality Model and Apply Adjustments =====
    logs.append("INFO: Building seasonality model...")

    # Build category mapping for seasonality model
    if 'category' in forecast_df.columns:
        category_mapping_df = forecast_df[['sku', 'category']].drop_duplicates()
    else:
        category_mapping_df = pd.DataFrame({'sku': forecast_df['sku'], 'category': 'Uncategorized'})

    # Build the seasonality model using daily_demand time series
    seasonality_model = build_seasonality_model(
        daily_demand_df=daily_demand,
        category_mapping_df=category_mapping_df,
        top_volume_pct=TOP_SKU_PERCENTAGE,
        min_months=MIN_MONTHS_FOR_INDIVIDUAL_SEASONALITY
    )

    model_stats = seasonality_model.get('model_stats', {})
    logs.append(f"INFO: Seasonality model built - {model_stats.get('skus_with_individual_profiles', 0)} SKUs with individual profiles, "
                f"{model_stats.get('skus_using_category_profiles', 0)} using category profiles")

    # Calculate seasonal indices for each SKU for the next 3 months
    # and apply seasonal adjustment to the exp_smooth forecast
    from datetime import datetime as dt
    current_month = dt.now().month

    # Get seasonal indices for next 3 months and calculate average adjustment
    def get_avg_seasonal_index(sku):
        """Get average seasonal index for next 3 months"""
        indices = []
        for i in range(3):
            month = ((current_month - 1 + i) % 12) + 1  # Next 3 months (1-12)
            idx = get_seasonal_index_for_sku(seasonality_model, sku, month)
            indices.append(idx)
        return np.mean(indices) if indices else 1.0

    # Apply seasonal adjustment to each SKU
    forecast_df['seasonal_index'] = forecast_df['sku'].apply(get_avg_seasonal_index)
    forecast_df['profile_type'] = forecast_df['sku'].apply(
        lambda sku: seasonality_model.get('sku_to_profile_type', {}).get(sku, 'category')
    )

    # Create seasonally-adjusted exp_smooth forecast
    forecast_df['exp_smooth_seasonal'] = forecast_df['exp_smooth'] * forecast_df['seasonal_index']

    # Update forecast_total_qty to use seasonally-adjusted exp_smooth
    forecast_df['forecast_total_qty_seasonal'] = forecast_df['exp_smooth_seasonal'] * forecast_horizon_days

    logs.append(f"INFO: Applied seasonal adjustments - avg index range: {forecast_df['seasonal_index'].min():.2f} to {forecast_df['seasonal_index'].max():.2f}")

    # ===== STEP 8: Calculate Summary Metrics =====
    total_time = (datetime.now() - start_time).total_seconds()
    logs.append(f"INFO: Forecast generation completed in {total_time:.2f} seconds")

    total_forecast_demand = forecast_df['forecast_total_qty'].sum()
    total_seasonal_demand = forecast_df['forecast_total_qty_seasonal'].sum()
    logs.append(f"INFO: Total forecasted demand (next {forecast_horizon_days} days): {total_forecast_demand:,.0f} units (base), {total_seasonal_demand:,.0f} units (seasonal)")

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

    os.makedirs(SNAPSHOT_FOLDER, exist_ok=True)

    if snapshot_date is None:
        snapshot_date = TODAY

    filename = f"forecast_snapshot_{snapshot_date.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(SNAPSHOT_FOLDER, filename)

    try:
        save_cols = [
            'snapshot_date', 'sku', 'sku_description', 'category',
            'primary_forecast_daily', 'forecast_total_qty',
            'forecast_lower_bound', 'forecast_upper_bound',
            'forecast_method', 'forecast_confidence', 'forecast_confidence_score',
            'forecast_horizon_days', 'historical_days', 'mape', 'mae'
        ]

        available_cols = [col for col in save_cols if col in forecast_df.columns]
        snapshot_df = forecast_df[available_cols].copy()
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

    snapshot_files = [f for f in os.listdir(SNAPSHOT_FOLDER) if f.startswith('forecast_snapshot_') and f.endswith('.csv')]

    if not snapshot_files:
        return pd.DataFrame()

    snapshots_list = []
    for filename in snapshot_files:
        filepath = os.path.join(SNAPSHOT_FOLDER, filename)
        try:
            df = pd.read_csv(filepath)
            if 'snapshot_date' in df.columns:
                df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])
            snapshots_list.append(df)
        except Exception as e:
            print(f"Warning: Could not load {filename}: {str(e)}")

    if not snapshots_list:
        return pd.DataFrame()

    return pd.concat(snapshots_list, ignore_index=True)


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

    dates = []
    for filename in snapshot_files:
        try:
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

    deliveries = deliveries_df.copy()

    if 'Goods Issue Date: Date' in deliveries.columns:
        deliveries['delivery_date'] = pd.to_datetime(deliveries['Goods Issue Date: Date'], format='%m/%d/%y', errors='coerce')
    elif 'Delivery Creation Date: Date' in deliveries.columns:
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

    deliveries = deliveries[(deliveries['delivered_qty'] > 0) & (deliveries['delivery_date'].notna())]

    actual_demand = deliveries.groupby(['sku', 'delivery_date']).agg({
        'delivered_qty': 'sum'
    }).reset_index()

    comparison_list = []

    for snapshot_date in snapshots_df['snapshot_date'].unique():
        snapshot_forecasts = snapshots_df[snapshots_df['snapshot_date'] == snapshot_date]

        forecast_horizon = snapshot_forecasts['forecast_horizon_days'].iloc[0] if 'forecast_horizon_days' in snapshot_forecasts.columns else 90
        forecast_end_date = snapshot_date + timedelta(days=forecast_horizon)

        if forecast_end_date > TODAY:
            continue

        actual_in_period = actual_demand[
            (actual_demand['delivery_date'] > snapshot_date) &
            (actual_demand['delivery_date'] <= forecast_end_date)
        ]

        actual_by_sku = actual_in_period.groupby('sku').agg({
            'delivered_qty': 'sum'
        }).reset_index()
        actual_by_sku.columns = ['sku', 'actual_qty']

        comparison = pd.merge(
            snapshot_forecasts[['sku', 'category', 'forecast_total_qty', 'forecast_method', 'forecast_confidence']],
            actual_by_sku,
            on='sku',
            how='left'
        )

        comparison['actual_qty'] = comparison['actual_qty'].fillna(0)
        comparison['snapshot_date'] = snapshot_date
        comparison['forecast_period_days'] = forecast_horizon

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

    return pd.concat(comparison_list, ignore_index=True)


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

    return {
        'total_forecast': total_forecast,
        'total_actual': total_actual,
        'bias_pct': bias,
        'bias_direction': 'Over-forecasting' if bias > 0 else ('Under-forecasting' if bias < 0 else 'Neutral'),
        'avg_error_pct': comparison_df['pct_error'].mean(),
        'avg_abs_error_pct': comparison_df['abs_pct_error'].mean(),
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

    demand_with_category = pd.merge(
        daily_demand_df,
        category_mapping_df[['sku', 'category']],
        on='sku',
        how='left'
    )

    demand_with_category['category'] = demand_with_category['category'].fillna('Uncategorized')

    return demand_with_category.groupby(['category', 'date']).agg({
        'demand_qty': 'sum'
    }).reset_index()


# ===== SEASONALITY MODEL =====
# Professional demand planner seasonality handling:
# - Top 20% SKUs by volume get individual seasonality profiles
# - Remaining 80% use category-level seasonality profiles
# - Minimum 12 months of history required for individual profiles
# - Uses monthly indices approach (12 values per profile)

# Seasonality model constants
TOP_SKU_PERCENTAGE = 0.20  # Top 20% by volume get individual profiles
MIN_MONTHS_FOR_INDIVIDUAL_SEASONALITY = 12  # Minimum months for individual SKU profiles


def calculate_monthly_seasonal_indices(demand_series: pd.DataFrame) -> dict:
    """
    Calculate monthly seasonal indices from historical demand data.

    The seasonal index represents how much each month deviates from the average.
    Index > 1.0 = higher than average demand, Index < 1.0 = lower than average.

    Args:
        demand_series: DataFrame with columns 'date' and 'demand_qty'

    Returns:
        dict: {
            'indices': dict mapping month (1-12) to seasonal index,
            'has_full_year': bool indicating if all 12 months have data,
            'months_with_data': int count of months with data
        }
    """
    if demand_series.empty:
        return {
            'indices': {m: 1.0 for m in range(1, 13)},
            'has_full_year': False,
            'months_with_data': 0
        }

    df = demand_series.copy()
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.month

    # Calculate average demand per month
    monthly_avg = df.groupby('month')['demand_qty'].mean()

    # Calculate overall average
    overall_avg = df['demand_qty'].mean()

    if overall_avg == 0:
        return {
            'indices': {m: 1.0 for m in range(1, 13)},
            'has_full_year': False,
            'months_with_data': 0
        }

    # Calculate seasonal indices (month average / overall average)
    indices = {}
    for month in range(1, 13):
        if month in monthly_avg.index:
            indices[month] = monthly_avg[month] / overall_avg
        else:
            indices[month] = 1.0  # Default to neutral if no data for month

    return {
        'indices': indices,
        'has_full_year': len(monthly_avg) == 12,
        'months_with_data': len(monthly_avg)
    }


def identify_top_volume_skus(daily_demand_df: pd.DataFrame, top_pct: float = TOP_SKU_PERCENTAGE) -> list:
    """
    Identify top SKUs by total volume for individual seasonality profiles.

    Args:
        daily_demand_df: DataFrame with columns 'sku', 'date', 'demand_qty'
        top_pct: Percentage of SKUs to classify as top volume (default 20%)

    Returns:
        list: SKU codes in the top volume tier
    """
    if daily_demand_df.empty:
        return []

    # Calculate total volume per SKU
    sku_volumes = daily_demand_df.groupby('sku')['demand_qty'].sum().sort_values(ascending=False)

    # Get top N% SKUs
    n_top = max(1, int(len(sku_volumes) * top_pct))
    top_skus = sku_volumes.head(n_top).index.tolist()

    return top_skus


def calculate_category_seasonal_profiles(daily_demand_df: pd.DataFrame,
                                          category_mapping_df: pd.DataFrame) -> dict:
    """
    Calculate category-level seasonal profiles.

    Args:
        daily_demand_df: DataFrame with columns 'sku', 'date', 'demand_qty'
        category_mapping_df: DataFrame with columns 'sku', 'category'

    Returns:
        dict: {category: seasonal_indices_dict}
    """
    if daily_demand_df.empty:
        return {}

    # Merge category information
    demand_with_category = pd.merge(
        daily_demand_df,
        category_mapping_df[['sku', 'category']],
        on='sku',
        how='left'
    )
    demand_with_category['category'] = demand_with_category['category'].fillna('Uncategorized')

    # Aggregate to category level
    category_demand = demand_with_category.groupby(['category', 'date']).agg({
        'demand_qty': 'sum'
    }).reset_index()

    # Calculate seasonal indices per category
    category_profiles = {}
    for category in category_demand['category'].unique():
        cat_data = category_demand[category_demand['category'] == category][['date', 'demand_qty']]
        profile = calculate_monthly_seasonal_indices(cat_data)
        category_profiles[category] = profile

    return category_profiles


def calculate_sku_seasonal_profiles(daily_demand_df: pd.DataFrame,
                                     top_skus: list,
                                     min_months: int = MIN_MONTHS_FOR_INDIVIDUAL_SEASONALITY) -> dict:
    """
    Calculate individual seasonal profiles for top-volume SKUs.

    Args:
        daily_demand_df: DataFrame with columns 'sku', 'date', 'demand_qty'
        top_skus: List of SKU codes that qualify for individual profiles
        min_months: Minimum months of data required for individual profile

    Returns:
        dict: {
            'profiles': {sku: seasonal_indices_dict},
            'skus_with_profiles': list of SKUs that got individual profiles,
            'skus_insufficient_history': list of SKUs that didn't have enough history
        }
    """
    if daily_demand_df.empty or not top_skus:
        return {
            'profiles': {},
            'skus_with_profiles': [],
            'skus_insufficient_history': []
        }

    profiles = {}
    skus_with_profiles = []
    skus_insufficient_history = []

    for sku in top_skus:
        sku_data = daily_demand_df[daily_demand_df['sku'] == sku][['date', 'demand_qty']]

        if sku_data.empty:
            skus_insufficient_history.append(sku)
            continue

        # Check months of history
        sku_data_copy = sku_data.copy()
        sku_data_copy['date'] = pd.to_datetime(sku_data_copy['date'])
        sku_data_copy['year_month'] = sku_data_copy['date'].dt.to_period('M')
        months_of_history = sku_data_copy['year_month'].nunique()

        if months_of_history >= min_months:
            profile = calculate_monthly_seasonal_indices(sku_data)
            profiles[sku] = profile
            skus_with_profiles.append(sku)
        else:
            skus_insufficient_history.append(sku)

    return {
        'profiles': profiles,
        'skus_with_profiles': skus_with_profiles,
        'skus_insufficient_history': skus_insufficient_history
    }


def build_seasonality_model(daily_demand_df: pd.DataFrame,
                             category_mapping_df: pd.DataFrame,
                             top_volume_pct: float = TOP_SKU_PERCENTAGE,
                             min_months: int = MIN_MONTHS_FOR_INDIVIDUAL_SEASONALITY) -> dict:
    """
    Build complete seasonality model with tiered approach:
    - Top 20% SKUs by volume: Individual seasonality profiles (if 12+ months data)
    - Remaining SKUs: Category-level seasonality profiles

    Args:
        daily_demand_df: DataFrame with columns 'sku', 'date', 'demand_qty'
        category_mapping_df: DataFrame with columns 'sku', 'category'
        top_volume_pct: Percentage of SKUs to give individual profiles
        min_months: Minimum months required for individual profiles

    Returns:
        dict: {
            'sku_profiles': {sku: seasonal_indices_dict} for top SKUs with enough data,
            'category_profiles': {category: seasonal_indices_dict},
            'sku_to_profile_type': {sku: 'individual' | 'category'},
            'sku_to_category': {sku: category_name},
            'model_stats': {
                'total_skus': int,
                'top_volume_skus': int,
                'skus_with_individual_profiles': int,
                'skus_using_category_profiles': int,
                'categories': int
            }
        }
    """
    if daily_demand_df.empty:
        return {
            'sku_profiles': {},
            'category_profiles': {},
            'sku_to_profile_type': {},
            'sku_to_category': {},
            'model_stats': {
                'total_skus': 0,
                'top_volume_skus': 0,
                'skus_with_individual_profiles': 0,
                'skus_using_category_profiles': 0,
                'categories': 0
            }
        }

    # Step 1: Identify top volume SKUs
    top_skus = identify_top_volume_skus(daily_demand_df, top_volume_pct)

    # Step 2: Calculate individual profiles for top SKUs with sufficient history
    sku_result = calculate_sku_seasonal_profiles(daily_demand_df, top_skus, min_months)

    # Step 3: Calculate category-level profiles for all categories
    category_profiles = calculate_category_seasonal_profiles(daily_demand_df, category_mapping_df)

    # Step 4: Build SKU-to-category mapping
    sku_to_category = {}
    if not category_mapping_df.empty:
        sku_cat_map = category_mapping_df.set_index('sku')['category'].to_dict()
        sku_to_category = {str(k): str(v) for k, v in sku_cat_map.items()}

    # Step 5: Determine profile type for each SKU
    all_skus = daily_demand_df['sku'].unique()
    sku_to_profile_type = {}

    for sku in all_skus:
        if sku in sku_result['skus_with_profiles']:
            sku_to_profile_type[sku] = 'individual'
        else:
            sku_to_profile_type[sku] = 'category'

    # Build model stats
    model_stats = {
        'total_skus': len(all_skus),
        'top_volume_skus': len(top_skus),
        'skus_with_individual_profiles': len(sku_result['skus_with_profiles']),
        'skus_using_category_profiles': len(all_skus) - len(sku_result['skus_with_profiles']),
        'categories': len(category_profiles)
    }

    return {
        'sku_profiles': sku_result['profiles'],
        'category_profiles': category_profiles,
        'sku_to_profile_type': sku_to_profile_type,
        'sku_to_category': sku_to_category,
        'model_stats': model_stats
    }


def get_seasonal_index_for_sku(seasonality_model: dict, sku: str, month: int) -> float:
    """
    Get the seasonal index for a specific SKU and month.

    Args:
        seasonality_model: Output from build_seasonality_model()
        sku: SKU code
        month: Month number (1-12)

    Returns:
        float: Seasonal index (1.0 = average, >1.0 = above average, <1.0 = below average)
    """
    if not seasonality_model or not sku:
        return 1.0

    profile_type = seasonality_model.get('sku_to_profile_type', {}).get(sku, 'category')

    if profile_type == 'individual':
        # Use individual SKU profile
        sku_profile = seasonality_model.get('sku_profiles', {}).get(sku, {})
        indices = sku_profile.get('indices', {})
        return indices.get(month, 1.0)
    else:
        # Use category profile
        category = seasonality_model.get('sku_to_category', {}).get(sku, 'Uncategorized')
        cat_profile = seasonality_model.get('category_profiles', {}).get(category, {})
        indices = cat_profile.get('indices', {})
        return indices.get(month, 1.0)


def apply_seasonal_adjustment(base_forecast: float, seasonal_index: float) -> float:
    """
    Apply seasonal adjustment to a base forecast.

    Args:
        base_forecast: Base forecast value (deseasonalized average)
        seasonal_index: Seasonal index for the target period

    Returns:
        float: Seasonally adjusted forecast
    """
    return base_forecast * seasonal_index


def get_seasonality_summary(seasonality_model: dict) -> str:
    """
    Get a human-readable summary of the seasonality model.

    Args:
        seasonality_model: Output from build_seasonality_model()

    Returns:
        str: Summary text
    """
    if not seasonality_model:
        return "No seasonality model available."

    stats = seasonality_model.get('model_stats', {})

    summary = f"""Seasonality Model Summary:
- Total SKUs analyzed: {stats.get('total_skus', 0)}
- Top volume SKUs (top {TOP_SKU_PERCENTAGE*100:.0f}%): {stats.get('top_volume_skus', 0)}
- SKUs with individual profiles: {stats.get('skus_with_individual_profiles', 0)}
- SKUs using category profiles: {stats.get('skus_using_category_profiles', 0)}
- Categories: {stats.get('categories', 0)}
"""
    return summary
