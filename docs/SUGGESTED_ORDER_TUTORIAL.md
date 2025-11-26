# Suggested Order Dashboard - User Tutorial

## Overview

The Suggested Order (Replenishment Planning) Dashboard calculates recommended purchase quantities using Net Requirements Planning (MRP) methodology. This tutorial explains how to use the dashboard and understand the ordering logic behind it.

---

## Quick Start Guide

### 1. Accessing the Dashboard
1. Navigate to the "Replenishment Planning" page from the sidebar menu
2. Ensure required data files are loaded:
   - DELIVERIES.csv (for demand history)
   - INVENTORY.csv (for current stock levels)
   - Domestic Vendor POs.csv (for incoming supply)

### 2. Understanding the Header KPIs

| Metric | Description |
|--------|-------------|
| **SKUs to Order** | Number of SKUs with suggested order quantities > 0 |
| **Total Suggested Qty** | Sum of all recommended order quantities |
| **Total Order Value** | Estimated cost based on unit costs |
| **High Priority SKUs** | SKUs with critical stock situations |

---

## How Suggested Orders Are Calculated

### The Net Requirements Formula

```
Suggested Order = Order-Up-To Level - Available Supply + Backorders
```

Where:
- **Order-Up-To Level** = Lead Time Demand + Safety Stock
- **Available Supply** = Current Inventory + Open PO Quantities
- **Backorders** = Outstanding customer orders not yet fulfilled

### Step-by-Step Calculation

1. **Calculate Average Daily Demand**
   - Uses historical deliveries from Demand Planning module
   - Based on smoothed, anomaly-adjusted demand

2. **Calculate Lead Time Demand**
   - Lead Time Demand = Daily Demand x Lead Time Days
   - Lead time sourced from PO history or uses 90-day default

3. **Calculate Safety Stock**
   - Formula: `Safety Stock = Z-score x Demand_Std x sqrt(Lead_Time)`
   - Protects against demand variability during replenishment

4. **Determine Order-Up-To Level**
   - Order-Up-To = Lead Time Demand + Safety Stock
   - Covers expected demand plus safety buffer

5. **Calculate Net Requirements**
   - Net = Order-Up-To - (Inventory + Open POs) + Backorders
   - If Net > 0, a suggested order is generated

---

## Service Level and Safety Stock

### Service Level Settings

| Service Level | Z-Score | Protection Level |
|---------------|---------|------------------|
| 90% | 1.28 | Good - acceptable for most SKUs |
| **95%** (Default) | 1.65 | Standard - recommended baseline |
| 98% | 2.05 | High - for critical products |
| 99% | 2.33 | Very High - for strategic inventory |

### Safety Stock Interpretation

Safety stock provides a buffer against:
- Demand variability (unexpected spikes)
- Supply variability (late deliveries)
- Forecast errors

**Higher safety stock = Lower stockout risk, Higher inventory cost**

---

## Connection to Demand Planning

The Suggested Order dashboard directly uses outputs from Demand Planning:

| Demand Planning Output | Used For |
|------------------------|----------|
| `avg_daily_demand` | Lead time demand calculation |
| `demand_std` | Safety stock calculation |
| `demand_cv` | Identifying intermittent demand |
| `anomaly_count` | Data quality awareness |
| Seasonal indices | Seasonally-adjusted forecasts |

### Impact of Smoothing Presets

Your Demand Planning smoothing preset affects Suggested Orders:

| Preset | Effect on Demand Forecast | Effect on Suggested Orders |
|--------|---------------------------|----------------------------|
| **Conservative** | Lower, more stable forecasts | More conservative order quantities |
| **Balanced** | Moderate forecasts | Standard order quantities |
| **Aggressive** | Higher, responsive forecasts | Larger order quantities |

---

## Edge Case Handling

### 1. New Products (No Demand History)
**Situation**: SKU not in Demand Planning output

**System Behavior**:
- Uses default demand assumptions or manual override
- Higher safety stock applied due to uncertainty

**User Action**: Monitor new product inventory closely. Adjust manually as demand pattern emerges.

### 2. Intermittent Demand SKUs
**Situation**: SKUs flagged as `is_intermittent = True` in Demand Planning

**System Behavior**:
- Standard calculations apply but demand forecast is more volatile
- Safety stock may appear high relative to average demand

**User Action**: Consider:
- Higher safety stock levels for intermittent items
- More frequent manual review
- Alternative methods (Croston's method) for very sporadic items

### 3. Long Lead Time Items
**Situation**: Lead time > 60 days

**System Behavior**:
- Lead time demand calculation covers extended period
- Safety stock scales with sqrt(lead_time)

**User Action**:
- Review forecasts further out
- Consider splitting orders for large quantities
- Account for seasonal patterns within lead time

### 4. High Demand Variability
**Situation**: SKUs with CV > 100%

**System Behavior**:
- Higher safety stock automatically calculated
- Warning flags in Demand Planning output

**User Action**:
- Review root causes of variability
- Consider inventory policies (min/max vs ROP)
- Evaluate service level appropriateness

---

## Understanding the Output Table

### Key Columns

| Column | Description |
|--------|-------------|
| **SKU** | Product identifier |
| **Vendor** | Supplier for this item |
| **Suggested Qty** | Recommended order quantity |
| **Avg Daily Demand** | From Demand Planning (smoothed) |
| **Lead Time Days** | Actual or estimated lead time |
| **Safety Stock** | Calculated buffer quantity |
| **Order-Up-To** | Target inventory level |
| **Current Inventory** | On-hand quantity |
| **Open PO Qty** | Pending incoming supply |
| **Net Requirement** | Order-Up-To - Available + Backorders |
| **Priority** | Based on days of supply remaining |

### Priority Levels

| Priority | Days of Supply | Action |
|----------|----------------|--------|
| **Critical** | < 7 days | Order immediately |
| **High** | 7-14 days | Order this week |
| **Medium** | 14-30 days | Order this cycle |
| **Low** | > 30 days | Monitor, order as needed |

---

## Seasonal Adjustments

When seasonality is applied:

1. **Lead Time Demand** uses seasonal indices for months within lead time
2. **Safety Stock** accounts for seasonal demand variability
3. **Order-Up-To** reflects expected seasonal patterns

### Example

For a SKU with:
- Average daily demand: 100 units
- December seasonal index: 1.4 (40% above average)
- Lead time: 30 days spanning December

**Seasonal Adjustment**:
- Base lead time demand: 100 x 30 = 3,000 units
- Seasonally adjusted: 100 x 30 x 1.4 = 4,200 units

---

## Best Practices

### Daily Operations
1. Review "Critical" priority SKUs daily
2. Export and share suggested orders with purchasing team
3. Validate unusually large suggested quantities

### Weekly Planning
1. Review full suggested order list
2. Compare suggested vs actual orders placed
3. Adjust for known promotions or events

### Monthly Review
1. Analyze order accuracy (suggested vs needed)
2. Review safety stock levels vs actual stockouts
3. Adjust service levels if over/under stocking observed

---

## Troubleshooting

### "No suggested orders generated"
**Possible Causes**:
1. Inventory levels sufficient
2. Open POs cover requirements
3. No demand forecast available

**Solution**: Check inventory and PO data are loaded and current.

### Suggested quantities seem too high
**Possible Causes**:
1. Long lead times
2. High demand variability
3. Conservative service level

**Solution**:
1. Verify lead time accuracy
2. Review demand smoothing preset
3. Consider reducing service level

### SKU not appearing in suggestions
**Possible Causes**:
1. SKU filtered out by category/retail filter
2. Insufficient demand history
3. Adequate inventory position

**Solution**: Check filters and verify SKU has demand history.

---

## Glossary

| Term | Definition |
|------|------------|
| **MRP** | Material Requirements Planning - systematic ordering approach |
| **Safety Stock** | Buffer inventory to protect against variability |
| **Lead Time** | Time from order placement to receipt |
| **Order-Up-To Level** | Target inventory level when ordering |
| **Net Requirement** | Quantity needed after accounting for supply |
| **Service Level** | Probability of not stocking out (e.g., 95%) |
| **Reorder Point** | Inventory level that triggers a new order |
| **Days of Supply** | Current inventory / average daily demand |

---

## Technical Reference

For detailed technical documentation, see:
- [BUSINESS_RULES_DOCUMENTATION.md](./BUSINESS_RULES_DOCUMENTATION.md)
- [replenishment_planning.py](../replenishment_planning.py) - source code
- [demand_forecasting.py](../demand_forecasting.py) - demand forecast source

---

*Last updated: November 2024*
*POP Supply Chain Dashboard v1.0*
