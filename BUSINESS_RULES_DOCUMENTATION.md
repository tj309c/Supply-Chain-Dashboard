# Business Rules Documentation

Auto-generated documentation of all business rules and field definitions.

**Generated:** 2025-11-21 16:39:38

---

## Data Field Definitions

### INVENTORY.csv

**Description:** Current inventory snapshot with on-hand quantities and pricing

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Material Number | string | True | Unique SKU/Material identifier (SAP Material Code) | inventory_tracking, master_data_join |
| POP Actual Stock Qty | numeric | True | Current on-hand quantity in stock | inventory_value, dio_calculation, stock_out_risk |
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

### On-Time Delivery Flag

**Formula:** `ship_date <= (order_date + 7 days)`

**Description:** Boolean flag indicating if delivery was on-time

**Notes:** Used to calculate on-time delivery percentage

---

## Business Rule Configurations

### Inventory Rules

```python
{'movement_classification': {'fast_moving_days': 30, 'normal_moving_days': 60, 'slow_moving_days': 90, 'very_slow_moving_days': 180}, 'scrap_criteria': {'default_dio_threshold': 730, 'min_dio_threshold': 90, 'max_dio_threshold': 1825, 'include_dead_stock': True}, 'abc_analysis': {'a_class_threshold': 80, 'b_class_threshold': 95, 'use_count_based': False, 'a_class_count_pct': 20, 'b_class_count_pct': 30}, 'stock_out_risk': {'critical_dio': 7, 'warning_dio': 14, 'safe_dio': 30}, 'demand_calculation': {'lookback_months': 12, 'lookback_days': 365, 'sku_market_intro_buffer_days': 60, 'use_sku_age_adjustment': True, 'min_days_for_demand_calc': 30}, 'variable_buckets': {'enabled': True, 'default_boundaries': [30, 60, 90, 180, 365, 730], 'min_boundary': 1, 'max_boundary': 1825, 'bucket_labels_auto': True}, 'snapshot_frequency': {'snapshot_interval': 'monthly', 'retention_months': 24}}
```

### Service Level Rules

```python
{'on_time_delivery': {'standard_lead_time_days': 7, 'target_on_time_percentage': 95.0}, 'performance_thresholds': {'excellent': 95.0, 'good': 90.0, 'fair': 85.0}}
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

