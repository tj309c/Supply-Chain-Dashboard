# Demand Planning Dashboard - User Tutorial

## Overview

The Demand Planning Dashboard provides professional-grade demand forecasting capabilities for SKU-level planning. This tutorial explains how to use the dashboard and understand the forecasting logic behind it.

---

## Quick Start Guide

### 1. Accessing the Dashboard
1. Navigate to the "Demand Planning" page from the sidebar menu
2. Ensure DELIVERIES.csv has been loaded with sufficient historical data

### 2. Understanding the Header KPIs

| Metric | Description |
|--------|-------------|
| **SKUs Forecasted** | Number of SKUs with sufficient data (3+ months) for forecasting |
| **90-Day Forecast** | Total projected demand for the next 90 days across all SKUs |
| **High Confidence** | Percentage of forecasts with high reliability scores |
| **Forecast Accuracy** | Historical accuracy based on backtesting (100% - MAPE) |

---

## Forecasting Methodology

### Moving Average Forecasts

The system generates forecasts using moving averages based on available history:

| History Available | Method Used | Description |
|-------------------|-------------|-------------|
| 90+ days | MA-90 (MA-12M monthly) | Long-term average, most stable |
| 60-89 days | MA-60 (MA-6M monthly) | Medium-term average |
| 30-59 days | MA-30 (MA-3M monthly) | Short-term average |

### Exponential Smoothing

After calculating moving averages, exponential smoothing is applied:
- **Formula**: `Forecast = alpha x Current + (1-alpha) x Previous`
- The alpha parameter determines responsiveness to recent changes

---

## Smoothing Presets

Select a smoothing preset based on your planning needs:

### Conservative (Default for stable products)
- **Z-Score Threshold**: 1.5 (flags ~6.5% as anomalies)
- **Alpha**: 0.1 (heavy smoothing, stable forecasts)
- **Best for**: Mature products with predictable demand

### Balanced (Recommended default)
- **Z-Score Threshold**: 2.0 (flags ~4.4% as anomalies)
- **Alpha**: 0.3 (moderate smoothing)
- **Best for**: Most products, general-purpose forecasting

### Aggressive (For responsive forecasting)
- **Z-Score Threshold**: 3.0 (flags ~2.1% as anomalies)
- **Alpha**: 0.5 (light smoothing, responsive forecasts)
- **Best for**: Fast-moving products, promotions, new launches

---

## Edge Case Handling

The system automatically handles common demand planning challenges:

### 1. New Products (Insufficient Data)
**Situation**: SKUs with fewer than 30 data points

**System Behavior**:
- Anomaly detection is SKIPPED
- Only exponential smoothing is applied
- Forecast uses available data without statistical filtering

**User Action**: Review forecasts for new products more frequently until 30+ data points accumulate.

### 2. Intermittent Demand (Sporadic Orders)
**Situation**: SKUs with Coefficient of Variation (CV) > 150%

**System Behavior**:
- Automatically uses higher Z-threshold (4.0) to avoid over-flagging
- Preserves legitimate demand spikes
- `is_intermittent` flag is set to TRUE

**User Action**: Review intermittent SKUs separately. Consider safety stock strategies.

### 3. High Anomaly Rate (Data Quality Issues)
**Situation**: More than 20% of observations flagged as anomalies

**System Behavior**:
- Warning is generated in the output
- Data is available for Excel export review
- Processing continues with anomalies smoothed

**User Action**: Export and review the raw data. Look for:
- Data entry errors
- Unusual customer ordering patterns
- System issues causing duplicate records

---

## Seasonality Model

The system applies a tiered seasonality approach:

### Tier 1: Individual SKU Profiles (Top 20% by Volume)
- **Criteria**: SKU in top 20% by volume AND 12+ months history
- **Method**: Monthly seasonal indices calculated per SKU
- **Benefits**: Captures SKU-specific seasonal patterns

### Tier 2: Category-Level Profiles (Remaining 80%)
- **Criteria**: All other SKUs
- **Method**: Aggregated category seasonal patterns
- **Benefits**: Provides reasonable seasonality even for new/low-volume SKUs

### Understanding Seasonal Indices
- **Index = 1.0**: Average demand month
- **Index > 1.0**: Above-average demand (e.g., 1.2 = 20% higher)
- **Index < 1.0**: Below-average demand (e.g., 0.8 = 20% lower)

---

## Confidence Scoring

Forecast confidence is calculated based on:

| Factor | Impact on Confidence |
|--------|---------------------|
| High demand variability (CV > 100%) | -30 points |
| Moderate variability (CV 50-100%) | -15 points |
| Limited history (< 90 days) | -20 points |
| Very limited history (< 60 days) | -30 points |
| High forecast error (MAPE > 50%) | -25 points |
| Moderate forecast error (MAPE 30-50%) | -15 points |

### Confidence Levels
| Level | Score Range | Interpretation |
|-------|-------------|----------------|
| High | 70-100 | Reliable forecast, use with confidence |
| Medium | 50-69 | Reasonable forecast, some review recommended |
| Low | 30-49 | Less certain, additional review needed |
| Very Low | 0-29 | Unreliable, consider manual override |

---

## Best Practices

### Daily Operations
1. Review high-volume SKUs with "Low" or "Very Low" confidence
2. Monitor anomaly counts - high counts may indicate data issues
3. Compare forecasts to recent actuals weekly

### Weekly Review
1. Check forecast accuracy metrics
2. Review SKUs with high anomaly percentages
3. Validate seasonality adjustments align with known patterns

### Monthly Planning
1. Save forecast snapshots for historical tracking
2. Compare forecast vs actual for completed periods
3. Adjust smoothing presets if systematic over/under-forecasting observed

---

## Troubleshooting

### "No demand forecasts available"
**Cause**: Insufficient historical data in DELIVERIES.csv
**Solution**: Ensure at least 30 days (or 3 months for monthly view) of data per SKU

### Low forecast accuracy
**Cause**: High demand variability or data quality issues
**Solution**:
1. Try different smoothing presets
2. Review and clean anomalous data points
3. Consider product-level manual adjustments

### Many SKUs with intermittent demand warning
**Cause**: Sparse ordering patterns common in B2B
**Solution**:
1. This is normal behavior - system handles it automatically
2. Consider Croston's method for dedicated intermittent demand forecasting
3. Increase safety stock for intermittent SKUs

---

## Glossary

| Term | Definition |
|------|------------|
| **MAPE** | Mean Absolute Percentage Error - forecast accuracy measure |
| **CV** | Coefficient of Variation - demand variability measure (std/mean x 100) |
| **Z-Score** | Statistical measure of how far a value is from the mean |
| **Alpha (α)** | Exponential smoothing parameter (0-1) |
| **Moving Average** | Average of last N periods of demand |
| **Seasonal Index** | Multiplier representing monthly demand deviation from average |

---

## Technical Reference

For detailed technical documentation, see:
- [BUSINESS_RULES_DOCUMENTATION.md](./BUSINESS_RULES_DOCUMENTATION.md)
- [demand_forecasting.py](../demand_forecasting.py) - source code

---

*Last updated: November 2024*
*POP Supply Chain Dashboard v1.0*
