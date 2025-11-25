# Business Rules Documentation

Auto-generated documentation of all business rules and field definitions.

**Generated:** 2025-11-21 16:39:38

---

## Data Field Definitions

### INVENTORY.csv

**Description:** Inventory snapshots with on-hand quantities and pricing. Contains both current and historical inventory data.

**Important Date Field Clarification:**
- `Current Date`: This is the **data freshness date** (when the file was extracted/refreshed), NOT the snapshot date
- The **actual inventory snapshot date** is determined by the `Snapshot YearWeek` fields below

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Material Number | string | True | Unique SKU/Material identifier (SAP Material Code) | inventory_tracking, master_data_join |
| POP Actual Stock Qty | numeric | True | Current on-hand quantity in stock | inventory_value, dio_calculation, stock_out_risk |
| Current Date | date | False | **Data freshness date** - when this data was extracted/refreshed (format: MM/DD/YY). NOT the inventory snapshot date. | data_freshness_indicator |
| Snapshot YearWeek: Trade Marketing Year | string | True | **Snapshot year** - the trade marketing year when this inventory snapshot was taken | inventory_time_series, historical_analysis |
| Snapshot YearWeek: Trade Marketing Yearmonth | string | True | **Snapshot month** - the trade marketing year-month when this inventory snapshot was taken (e.g., "2024-11") | inventory_time_series, monthly_trends |
| Snapshot YearWeek:Trade Marketing Week of the Year | numeric | True | **Snapshot week** - the trade marketing week of year when this inventory snapshot was taken (1-52) | inventory_time_series, weekly_analysis |
| POP Actual Stock in Transit Qty | numeric | False | Quantity in transit (not yet received) | available_inventory, planning |
| POP Last Purchase: Price in Purch. Currency | numeric | True | Last purchase price per unit (used for inventory valuation) | inventory_value, scrap_value_calculation |
| POP Last Purchase: Currency | string | True | Currency of last purchase price (USD, EUR, etc.) | currency_conversion, inventory_value |

### DELIVERIES.csv

**Description:** Historical shipment/delivery records

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Deliveries Detail - Order Document Number | string | True | Order number (links to ORDERS.csv) | order_join, service_level |
| Item - SAP Model Code | string | True | SKU/Material code for delivered item | demand_calculation, dio_calculation |
| Delivery Creation Date: Date | date | True | Date when shipment was created/shipped (format: MM/DD/YY) | service_level, demand_calculation, historical_trends |
| Goods Issue Date: Date | date | False | Date when goods were issued from the warehouse (format: MM/DD/YY). Preferred for Logistics OTIF. | service_level, logistics_metrics |
| Deliveries - TOTAL Goods Issue Qty | numeric | True | Quantity of units shipped/delivered | demand_calculation, service_level |
| Item - Model Desc | string | False | Product/item description | display, reporting |

### ORDERS.csv

**Description:** Customer orders and backorder tracking

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Orders Detail - Order Document Number | string | True | Unique order number | order_tracking, delivery_join |
| Item - SAP Model Code | string | True | SKU/Material code for ordered item | order_tracking, backorder_analysis |
| Order Creation Date: Date | date | True | Date when order was created (format: MM/DD/YY) | service_level, backorder_aging, demand_analysis |
| Original Customer Name | string | True | Customer who placed the order | customer_analysis, service_level_reporting |
| Item - Model Desc | string | False | Product/item description | display, reporting |
| Sales Organization Code | string | False | Sales org responsible for order | organizational_reporting, filtering |
| Orders - TOTAL Orders Qty | numeric | True | Total quantity ordered | order_tracking, demand_analysis |
| Orders - TOTAL To Be Delivered Qty | numeric | True | Quantity still to be delivered (backorder quantity) | backorder_tracking, fulfillment_analysis |
| Orders - TOTAL Cancelled Qty | numeric | False | Quantity cancelled from order | cancellation_analysis, order_accuracy |
| Reject Reason Desc | string | False | Reason for rejection/cancellation | root_cause_analysis |
| Order Type (SAP) Code | string | False | Type of order (standard, rush, etc.) | order_classification, filtering |
| Order Reason Code | string | False | Reason code for order | order_classification |

### Master Data.csv

**Description:** Product catalog with SKU metadata

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Material Number | string | True | Unique SKU/Material identifier | master_lookup, joins |
| PLM: Level Classification 4 | string | True | Product category/classification | category_analysis, filtering, abc_analysis |
| Activation Date (Code) | date | False | SKU creation/activation date (format: M/D/YY). Used to determine market introduction date for demand calculations. | demand_calculation, sku_age_analysis, new_product_identification |

### DOMESTIC INBOUND.csv

**Description:** Inbound logistics and receipts

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Purchase Order Number | string | True | PO number (links to Vendor POs) | po_tracking, lead_time_calculation |
| Posting Date | date | True | Date when goods were received/posted | lead_time_calculation, receipt_tracking |
| Material Number | string | True | SKU/Material code received | inventory_updates, lead_time_calculation |

### Domestic Vendor POs.csv

**Description:** Purchase orders from vendors

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| SAP Purchase Orders - Purchasing Document Number | string | True | Unique PO number | po_tracking, vendor_performance |
| Order Creation Date - Date | date | True | Date when PO was created | lead_time_calculation, po_aging |
| SAP Material Code | string | True | SKU/Material code ordered | inventory_planning, lead_time_by_sku |

---

## Calculated Fields

### Days Inventory Outstanding

**Formula:** `on_hand_qty / daily_demand`

**Description:** Number of days current inventory will last based on historical demand

**Interpretation:**

- 0: No movement in historical period (dead stock)
- < 30: Fast moving - less than 1 month of supply
- 30-60: Normal moving - 1-2 months of supply
- 60-90: Slow moving - 2-3 months of supply
- 90-180: Very slow moving - 3-6 months of supply
- > 180: Obsolete risk - more than 6 months of supply

**Notes:** Daily demand calculated from last 12 months of deliveries / 365 days

### Daily Demand

**Formula:** `sum(deliveries_since_market_intro) / days_since_market_intro`

**Description:** Average daily demand based on historical shipments since SKU market introduction

**Notes:** Uses DELIVERIES.csv and Master Data.csv (Activation Date). New SKUs (<2 months old) are excluded from demand calculations. Uses actual days active, capped at 365.

### Stock Value

**Formula:** `on_hand_qty * last_purchase_price`

**Description:** Total value of on-hand inventory

**Notes:** Can be converted to USD or EUR for reporting

### Movement Classification

**Formula:** `Based on DIO thresholds (see INVENTORY_RULES)`

**Description:** Classification of inventory movement speed

### Days on Backorder

**Formula:** `today - order_date`

**Description:** Number of days an order has been on backorder

**Notes:** Calculated from order creation date to today

### Days to Deliver

**Formula:** `ship_date - order_date`

**Description:** Number of days from order creation to shipment

**Notes:** Used for service level performance tracking

### On-Time Delivery Flags

We now calculate two separate OTIF (On-Time In-Full / On-Time) measures to capture different parts of the fulfillment chain:

- **Planning OTIF (Order → Shipment)**
	- Formula: `ship_date <= (order_date + 7 days)`
	- Description: Whether the shipment occurred within 7 days of order creation. Ship date is defined as the Goods Issue Date when available, otherwise the Delivery Creation Date.
	- Used for: service level reporting, planning SLAs, customer-facing KPIs

- **Logistics OTIF (Delivery Creation → Goods Issue)**
	- Formula: `goods_issue_date <= (delivery_creation_date + 3 days)`
	- Description: Measures the logistics team's ability to issue goods within 3 days of delivery creation. Only counted where both dates are present.
	- Used for: logistics performance, root-cause, vendor/3PL evaluation

---

## Business Rule Configurations

### Inventory Rules

```python
{'movement_classification': {'fast_moving_days': 30, 'normal_moving_days': 60, 'slow_moving_days': 90, 'very_slow_moving_days': 180}, 'scrap_criteria': {'default_dio_threshold': 730, 'min_dio_threshold': 90, 'max_dio_threshold': 1825, 'include_dead_stock': True}, 'abc_analysis': {'a_class_threshold': 80, 'b_class_threshold': 95, 'use_count_based': False, 'a_class_count_pct': 20, 'b_class_count_pct': 30}, 'stock_out_risk': {'critical_dio': 7, 'warning_dio': 14, 'safe_dio': 30}, 'demand_calculation': {'lookback_months': 12, 'lookback_days': 365, 'sku_market_intro_buffer_days': 60, 'use_sku_age_adjustment': True, 'min_days_for_demand_calc': 30}, 'variable_buckets': {'enabled': True, 'default_boundaries': [30, 60, 90, 180, 365, 730], 'min_boundary': 1, 'max_boundary': 1825, 'bucket_labels_auto': True}, 'snapshot_frequency': {'snapshot_interval': 'monthly', 'retention_months': 24}}
```

### Service Level Rules

```python
{'on_time_delivery': {'standard_lead_time_days': 7, 'target_on_time_percentage': 95.0}, 'performance_thresholds': {'excellent': 95.0, 'good': 90.0, 'fair': 85.0}, 'logistics_on_time_days': 3}
```

### Backorder Rules

```python
{'aging_calculation': {'start_date_field': 'order_date', 'use_order_creation_date': True}, 'aging_buckets': {'buckets': [{'name': '0-7 days', 'min': 0, 'max': 7}, {'name': '8-14 days', 'min': 8, 'max': 14}, {'name': '15-30 days', 'min': 15, 'max': 30}, {'name': '31-60 days', 'min': 31, 'max': 60}, {'name': '60+ days', 'min': 61, 'max': 99999}]}, 'priority_scoring': {'age_weight': 0.4, 'quantity_weight': 0.3, 'customer_tier_weight': 0.3}, 'alerts': {'critical_age_days': 30, 'high_quantity_threshold': 1000}}
```

### Currency Rules

```python
{'base_currency': 'USD', 'supported_currencies': ['USD', 'EUR'], 'conversion_rates': {'USD_to_EUR': 0.9, 'EUR_to_USD': 1.1111111111111112}}
```

### Storage Location Rules

**Description:** Storage location codes and their classifications

| Code | Description | Status | Category | Availability |
|------|-------------|--------|----------|-------------|
| Z401 | POP AIT | Vendor Managed | vendor_managed | external |
| Z303 | ATL PhantomTrans | Missing | missing | unavailable |
| Z109 | POP ATL Whs Sloc | On Hand | on_hand | available |
| Z799 | Com Pool transf | Unknown | unknown | unknown |
| Z101 | DWM Main Storage | On Hand | on_hand | available |
| Z106 | AFA ATL DWM WH | On Hand | on_hand | available |
| Z307 | POP Transit : IT | Incoming from Italy | in_transit | pending |
| Z503 | Write OFF S.ATL | Scrapped | scrapped | unavailable |
| Z308 | POP Transit China | Incoming from China | in_transit | pending |
| Z501 | Scrap Returns | Scrapped | scrapped | unavailable |
| Z402 | POP Ryan Scott | Vendor Managed | vendor_managed | external |
| Z116 | STELLA Stock | On Hand | on_hand | available |

**Category Groupings:**

- **On Hand**: Z109, Z101, Z106, Z116
- **Vendor Managed**: Z401, Z402
- **In Transit**: Z307, Z308
- **Scrapped**: Z503, Z501
- **Missing**: Z303
- **Unknown**: Z799

**Availability Definitions:**

- **Available**: Can be used for order fulfillment
- **Pending**: Expected to arrive, not yet available
- **External**: Managed by vendor, not in direct control
- **Unavailable**: Not available for use
- **Unknown**: Status unclear, needs investigation

### Alternate Codes Rules

**Description:** Material code alternate/supersession mapping rules

```python
{'normalization': {'auto_normalize': True, 'normalize_inventory': True, 'normalize_demand': True, 'normalize_backorders': True, 'default_view': 'aggregated'}, 'display': {'show_alternate_codes': True, 'show_code_transition_dates': False, 'highlight_old_codes': True, 'max_alternates_display': 3}, 'alerts': {'alert_on_old_code_backorders': True, 'alert_on_split_inventory': True, 'alert_on_old_code_orders': True, 'critical_backorder_threshold': 0}, 'business_logic': {'recommend_code_update': True, 'prioritize_old_inventory_first': True, 'track_inventory_by_code': True, 'consolidate_reporting': True}, 'data_quality': {'flag_missing_current_codes': True, 'flag_circular_references': True, 'validate_code_hierarchy': True}}
```

**Alternate Codes Summary:**

- Total SKU Families: 142
- Total Old Codes: 143
- Families with 2 codes: 141
- Families with 3+ codes: 1

**Business Impact:**

- **Inventory Consolidation**: Automatically aggregates inventory across all alternate codes
- **Historical Demand**: Combines demand history from old and current codes for accurate forecasting
- **Backorder Alerts**: Flags backorders on old codes when inventory exists on current code
- **Code Migration**: Recommends updating orders from old codes to current codes
- **Reporting**: All reports consolidate data under current/active material codes

---

## Demand Forecasting Business Logic

### Overview

The demand forecasting module generates statistical forecasts based on historical delivery data. It supports both daily and monthly time-series granularity.

### Key Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Rolling Window | 30 months | Historical data window for monthly forecasting (overrides sidebar filter) |
| Forecast Horizon | 90 days | How far into the future to project demand |
| Min Data Requirement | 3 months (monthly) / 30 days (daily) | Minimum historical data needed per SKU |
| Backtest Split | 80/20 | Train/test split for accuracy calculation |

### Forecast Methods

The system automatically selects the best forecasting method based on data availability:

| Method | Window | Used When |
|--------|--------|-----------|
| MA-3M | 3 months | Less than 6 months of history (monthly granularity) |
| MA-6M | 6 months | 6-11 months of history (monthly granularity) |
| MA-12M | 12 months | 12+ months of history (monthly granularity) |
| MA-30 | 30 days | Less than 60 days of history (daily granularity) |
| MA-60 | 60 days | 60-89 days of history (daily granularity) |
| MA-90 | 90 days | 90+ days of history (daily granularity) |

### Confidence Scoring

Forecasts are assigned confidence levels based on:

- **Historical data availability**: More data = higher confidence
- **Demand variability (CV)**: Lower CV = more predictable = higher confidence
- **Backtest accuracy (MAPE)**: Lower MAPE = more accurate = higher confidence

| Confidence | Score Range | Interpretation |
|------------|-------------|----------------|
| High | 80-100 | Reliable forecast, stable demand pattern |
| Medium | 60-79 | Reasonable forecast, some variability |
| Low | 40-59 | Forecast less certain, review needed |
| Very Low | 0-39 | Unreliable forecast, insufficient data |

### Monthly vs Daily Granularity

When `Rolling 12 Months (monthly)` is selected in the sidebar, the demand page **automatically overrides to 30 months** for better forecasting. The UI displays:

- **Monthly bars** for historical actuals
- **Monthly forecast bars** for projections (next 3 months)
- **Confidence intervals** as error bars

### Important Notes for Developers

1. **Data Filtering**: The RETAIL PERMANENT filter is applied BEFORE demand forecasting, so only retail SKUs are included in forecasts.

2. **SKU Code Normalization**: SKU codes are normalized (uppercase, single spaces) for matching across data sources.

3. **Date Format**: Deliveries use `MM/DD/YY` date format for `Goods Issue Date: Date`.

4. **Empty Forecasts**: If the forecast dataframe is empty, check:
   - Sufficient historical data (minimum 3 months for monthly mode)
   - RETAIL PERMANENT filter matches SKUs in deliveries
   - Date parsing succeeded (no NaT values)

5. **Performance**: Forecasting 500+ SKUs takes ~1-2 seconds with caching. Use the sidebar "Precompute Forecasts" button to warm the cache.

