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

### Inbound_DB.csv (Consolidated Inbound)

**Description:** Consolidated historical receipt records from **both domestic AND international vendors**. This is the **PRIMARY source** for all vendor service level metrics. Replaces the legacy `DOMESTIC INBOUND.csv` file.

**Data Characteristics:**
- Date Range: 2023-01-01 to present
- Contains ~172,000+ rows of receipt history
- All monetary values in EUR (Group Currency)
- Filtered to Plant US03 (Atlanta) only

#### Domestic vs International Classification

| Field | Value | Meaning |
|-------|-------|---------|
| `*Purchase Orders IC Flag` | **NO** | Domestic supplier (external vendor) |
| `*Purchase Orders IC Flag` | **YES** | International/Intercompany (Luxottica Italy, Hong Kong) |
| `*Purchase Order Origin` | `SUPPLIER` | Domestic US vendors |
| `*Purchase Order Origin` | `LUXOTTICA GROUP SPA` | International - Italy |
| `*Purchase Order Origin` | `LUXOTTICA HONG KONG SERVICES LTD` | International - China/HK |

#### Key Fields

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Plant: Code | string | True | Plant code (filter to **US03** only) | plant_filtering |
| Material Number | string | True | SKU/Material code received | inventory_updates, sku_tracking |
| Material Description | string | False | Product description | display, reporting |
| Vendor: Code | string | True | SAP vendor code | vendor_identification |
| Vendor: Name | string | True | Vendor name | vendor_performance |
| Purchase Order Number | string | True | PO number | po_tracking |
| Purchase Order Date | date | True | PO creation date (format: YYYYMMDD) | lead_time_calculation |
| Scheduled Delivery Date | date | True | Expected delivery date (format: YYYYMMDD) | on_time_calculation |
| Date | date | True | **Receipt date** - when goods were received (format: YYYYMMDD) | receipt_tracking |
| *Purchase Orders IC Flag | string | True | Intercompany flag: NO=Domestic, YES=International | vendor_classification |
| *Purchase Order Origin | string | True | Origin: SUPPLIER, LUXOTTICA GROUP SPA, or LUXOTTICA HONG KONG | vendor_classification |
| POP Purchase Order quantity | numeric | True | Ordered quantity | fill_rate_calculation |
| POP Good Receipts Quantity | numeric | True | Received quantity | receipt_tracking, fill_rate |

#### Pre-Calculated On-Time Delivery Buckets

These fields are **pre-calculated in the source data** - use them directly instead of calculating from dates:

| Field Name | Description | Used For |
|------------|-------------|----------|
| POP Good Receipts on Time Quantity | Units received on or before scheduled date | otif_calculation |
| POP Good Receipts Within 2 Days Quantity | Units received 1-2 days late | delay_analysis |
| POP Good Receipts Delay 3-5 Days Quantity | Units received 3-5 days late | delay_analysis |
| POP Good Receipts Delay 6-10 Days Quantity | Units received 6-10 days late | delay_analysis |
| POP Good Receipts Over 10 Days Quantity | Units received 10+ days late | delay_analysis |

#### Value Fields (EUR - Group Currency)

| Field Name | Description | Currency |
|------------|-------------|----------|
| POP Purchase Order Net Value in Group Currency | PO value | EUR |
| POP Good Receipts Amount (@Purchase Document Price in Group Currency) | Receipt value | EUR |

**Note:** Use the global currency selector in the sidebar to convert EUR values to USD. Default conversion rate: 1 EUR = 1.08 USD.

#### Open PO Quantities

| Field Name | Description |
|------------|-------------|
| POP Purchase Order Open Quantity | Remaining quantity not yet received |
| POP Purchase Order Open On Time Quantity | Open qty still within schedule |
| POP Purchase Order Open Overdue Quantity | Open qty past scheduled date |

**Critical Usage Notes:**
- **Always filter to `Plant: Code = 'US03'`** - other plants may appear in future
- Use `*Purchase Orders IC Flag` to distinguish domestic (NO) vs international (YES) vendors
- Use pre-calculated on-time fields for performance - do NOT recalculate from dates
- Fill Rate = `POP Good Receipts Quantity / POP Purchase Order quantity * 100`
- On-Time % = `POP Good Receipts on Time Quantity / POP Good Receipts Quantity * 100`

### ~~DOMESTIC INBOUND.csv~~ (REMOVED)

**⚠️ REMOVED:** This file has been replaced by `Inbound_DB.csv`. The new file includes both domestic and international vendors with pre-calculated on-time metrics. All references to `DOMESTIC INBOUND.csv` should now use `Inbound_DB.csv`.

### Domestic Vendor POs.csv

**Description:** Snapshot of **currently open** purchase orders from domestic vendors. Use for open PO tracking ONLY.

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| SAP Purchase Orders - Purchasing Document Number | string | True | Unique PO number | po_tracking, vendor_performance |
| Order Creation Date - Date | date | True | Date when PO was created (format: M/D/YY) | lead_time_calculation, po_aging |
| Last Requested Delivery Date - Date | date | False | Requested delivery date | expected_delivery |
| Last Confirmed Delivery Date - Date | date | False | Vendor confirmed delivery date | expected_delivery |
| SAP Material Code | string | True | SKU/Material code ordered | inventory_planning, lead_time_by_sku |
| Model Desc | string | False | Product description | display, reporting |
| SAP Supplier - Supplier Description | string | True | Vendor name | vendor_performance, filtering |
| SAP Supplier - Country Key | string | False | Vendor country code | vendor_analysis |
| SAP Supplier - City | string | False | Vendor city | vendor_analysis |
| SAP Purchase Orders - Status | string | False | PO status (RI=Received, etc.) | status_tracking |
| Supplier Payment Terms | string | False | Payment terms code | vendor_terms |
| SAP Purchase Orders - Document Currency Net Value | numeric | True | Total PO line value | po_value_analysis |
| SAP Purchase Orders - Document Currency Net Price | numeric | True | Unit price | pricing_analysis |
| SAP Purchase Orders - Ordered Quantity | numeric | True | Quantity ordered | order_tracking |
| SAP Purchase Orders - Received Quantity | numeric | True | Quantity received to date (for this PO snapshot) | open_po_tracking |
| SAP Purchase Orders - Open Quantity | numeric | True | Remaining open quantity | open_po_tracking |

**Critical Usage Notes:**
- This file is a **point-in-time snapshot** of currently open POs
- Historical/closed POs are **NOT included** in this file
- **DO NOT use for vendor service level calculations** - use `Inbound_DB.csv` instead
- The "Received Quantity" field shows what's been received for these specific open POs, but does NOT represent complete vendor performance history
- Use ONLY for: Open PO tracking, PO aging, At-risk PO alerts, Pricing analysis

**Why Not Use for Fill Rate?**
When you join this file with Inbound_DB.csv, most historical POs won't match because they've already been received and removed from this file. This produces artificially low fill rates (e.g., 1% instead of the true vendor performance).

### ATL_FULLFILLMENT.csv

**Description:** Snapshot of **currently open/in-transit** international vendor orders (primarily from Italy and China). This file is for **open PO tracking ONLY** - it does NOT contain historical/completed shipments.

**⚠️ CRITICAL DATA LIMITATIONS:**
- This file contains ONLY current open orders from international vendors
- Rows with `ON TIME TRANSIT = 'DELIVERED'` should be **EXCLUDED** from all views
- **NO historical inbound data** is available for international vendors
- **CANNOT calculate vendor fill rate** - no historical order/receipt data exists

| Field Name | Data Type | Required | Description | Used For |
|------------|-----------|----------|-------------|----------|
| Sales Ord | string | True | Sales order number (used as PO reference) | po_tracking |
| SAP Item Material Code | string | True | SKU/Material code | sku_tracking |
| Model Desc | string | False | Product description | display, reporting |
| Storage Ship From | string | True | Origin location/vendor (e.g., CN VENDOR, BONZAI) | vendor_identification |
| Ship From Country | string | True | Origin country code (CN, IT, etc.) | vendor_country_analysis |
| Order Date | date | True | Date order was placed (format: MM/DD/YYYY - US format) | order_tracking |
| TOTAL Order Qty | numeric | **DO NOT USE** | ~~Original quantity ordered~~ **This field contains duplicate/inaccurate data and should NEVER be used.** (Note: column has leading/trailing spaces in CSV) | **EXCLUDED** |
| TOTAL Good Issue Qty | numeric | True | **Expected quantity to receive** from international vendor. This is the quantity we expect to arrive. (Note: column has leading/trailing spaces in CSV) | in_transit_calculation, open_po_tracking |
| ON TIME TRANSIT | string | True | Delivery status: DELIVERED, ON TIME, ON DELAY. **Filter OUT 'DELIVERED' rows.** | status_filtering |
| Transp Mode | string | False | Transportation mode (SEA, AIR) | logistics_analysis |
| Carrier Name | string | False | Shipping carrier | carrier_analysis |

#### ATL Date Fields (Shipment Timeline)

The following date fields track the international shipment journey from vendor to DC:

| Field Name | Data Type | Description | Stage |
|------------|-----------|-------------|-------|
| Order Date | date | Date order was placed with international vendor | 1. Order |
| Ship Date | date | Date goods **left the international vendor** | 2. Vendor Ship |
| ETA PORT | date | **Expected** arrival date at US shipping port | 3. Port (Expected) |
| ATA Port | date | **Actual** arrival date at US shipping port | 3. Port (Actual) |
| TGT Delivery Date DC | date | **Expected/Target** delivery date to our distribution center | 4. DC (Expected) |
| Delivery Date DC | date | **Actual** date goods arrived/showed up at our DC | 4. DC (Actual Arrival) |
| Good Receipt DC | date | **Actual** date goods were **putaway** in our DC (inventory available) | 5. DC (Putaway Complete) |

**Shipment Timeline Diagram:**
```
Order Date → Ship Date → ETA PORT → ATA Port → TGT Delivery DC → Delivery Date DC → Good Receipt DC
   (1)         (2)         (3a)       (3b)          (4a)              (4b)              (5)
 Ordered    Left Vendor  Expected   Arrived at   Expected at      Arrived at       Putaway in
            Facility     at Port    US Port      Our DC           Our DC           DC (Available)
```

**Key Distinctions:**
- **Delivery Date DC** = When goods physically showed up at DC dock
- **Good Receipt DC** = When goods were putaway and available in inventory (may be 1-3 days after arrival)
- **TGT Delivery Date DC** = Original expected delivery date (used for on-time calculations)

#### ATL Fulfillment Business Rules

**⚠️ IMPORTANT: This file is for OPEN PO tracking only. Exclude all DELIVERED rows.**

**Data Filtering (MANDATORY):**
- **ALWAYS filter out** rows where `ON TIME TRANSIT = 'DELIVERED'`
- Only include rows where status is 'ON TIME' or 'ON DELAY' (in-transit shipments)
- Filter: `ON TIME TRANSIT != 'DELIVERED' AND TOTAL Good Issue Qty > 0`

**Status Values:**
| Status | Meaning | Include in Views? |
|--------|---------|-------------------|
| DELIVERED | Already received - **EXCLUDE from all views** | **NO - EXCLUDE** |
| ON TIME | In transit, on schedule to meet TGT Delivery Date DC | Yes |
| ON DELAY | In transit, but delayed past TGT Delivery Date DC | Yes |

**Quantity Field (Simplified):**

| Calculated Field | Formula | Description |
|-----------------|---------|-------------|
| open_qty / in_transit_qty | `TOTAL Good Issue Qty` | Quantity expected to arrive from international vendor |

**⚠️ DO NOT CALCULATE:**
- ~~Fill Rate~~ - No historical order data available
- ~~On-Time Delivery %~~ - No historical receipt data available (will be added with International Inbound file)
- ~~Received Qty~~ - DELIVERED rows are excluded

**Replenishment Planning Integration:**
- In-transit international shipments are added to `available_supply` when calculating suggested order quantities
- This prevents over-ordering for SKUs with shipments already en route
- Formula: `available_supply = on_hand_qty + in_transit_qty + open_domestic_po_qty + open_international_qty`

**Expected Arrival Estimation (for in-transit shipments):**
- Use `TGT Delivery Date DC` as the expected arrival date for planning purposes
- If `TGT Delivery Date DC` has passed but not delivered, shipment is considered delayed

---

## Vendor & Procurement Dashboard Views

The Vendor & Procurement Dashboard supports two distinct views to separate domestic and international vendor management:

### Domestic View

**Data Sources:**
- `Domestic Vendor POs.csv` - Purchase orders from US-based vendors
- `Inbound_DB.csv` - Receipt/inbound records for all vendors (domestic + international)

**Features Available:**
- Open PO tracking with full value information
- Vendor performance scoring (OTIF, Fill Rate, Lead Time)
- Pricing analysis and volume discount scoring
- At-risk PO alerts

**Key Metrics:**
- Unit prices and PO values from SAP
- Lead time calculations from PO date to receipt date
- Vendor payment terms

### International View

**Data Sources:**
- `ATL_FULLFILLMENT.csv` - Open/in-transit international shipment tracking only

**Features Available:**
- Open PO tracking (in-transit shipments only)
- At-risk shipment alerts (delayed shipments)
- Expected arrival dates

**⚠️ Limitations (No Historical Data):**
- **NO vendor fill rate** - No historical order/receipt data available
- **NO on-time delivery %** - Requires historical receipt data (future: International Inbound file)
- **No pricing data** - ATL fulfillment does not include unit prices or PO values
- **No volume discount analysis** - Requires pricing data
- **DELIVERED rows are excluded** - File only shows open/in-transit shipments

**Key Differences:**
| Aspect | Domestic | International |
|--------|----------|---------------|
| Data Type | Open POs + Historical Receipts | Open POs ONLY (no history) |
| PO Value | Available (SAP currency) | Not available |
| Unit Price | Available | Not available |
| Fill Rate | Available (from Inbound_DB.csv) | Available (from Inbound_DB.csv) |
| On-Time % | Available | **NOT available** (pending Int'l Inbound file) |
| Vendor Name | SAP Supplier Description | Storage Ship From (origin) |
| Date Format | M/D/YY | MM/DD/YYYY (US format) |

---

## Executive Overview - Vendor Service Level KPIs

The Executive Overview page displays key vendor performance metrics for both domestic and international vendors. All metrics are now sourced from `Inbound_DB.csv`.

### Consolidated Vendor KPIs (from Inbound_DB.csv)

**Data Source:** `Inbound_DB.csv` (consolidated domestic + international inbound receipts)

| KPI | Formula | Description | Available For |
|-----|---------|-------------|---------------|
| **Fill Rate** | `SUM(POP Good Receipts Quantity) / SUM(POP Purchase Order quantity) * 100` | Percentage of ordered quantity received | Domestic + International |
| **On-Time Delivery %** | `SUM(POP Good Receipts on Time Quantity) / SUM(POP Good Receipts Quantity) * 100` | Percentage of units received on or before scheduled date | Domestic + International |
| **Units Received** | `SUM(POP Good Receipts Quantity)` | Total units received from vendors | Domestic + International |
| **PO Value** | `SUM(POP Purchase Order Net Value in Group Currency)` | Total PO value in EUR | Domestic + International |

### Filtering by Vendor Type

To filter metrics by domestic vs international vendors:

| Filter | Field | Value |
|--------|-------|-------|
| **Domestic Only** | `*Purchase Orders IC Flag` | `= 'NO'` |
| **International Only** | `*Purchase Orders IC Flag` | `= 'YES'` |
| **Italy (Luxottica)** | `*Purchase Order Origin` | `= 'LUXOTTICA GROUP SPA'` |
| **China/HK** | `*Purchase Order Origin` | `= 'LUXOTTICA HONG KONG SERVICES LTD'` |
| **External Suppliers** | `*Purchase Order Origin` | `= 'SUPPLIER'` |

### International In-Transit Tracking (from ATL_FULLFILLMENT.csv)

The `ATL_FULLFILLMENT.csv` file is still used for **real-time in-transit tracking** of international shipments:

| KPI | Status | Notes |
|-----|--------|-------|
| **Int'l In-Transit Qty** | ✅ AVAILABLE | Total quantity currently in transit from international vendors |
| **Delayed Shipments** | ✅ AVAILABLE | Shipments past their TGT Delivery Date DC |

**Note:** `ATL_FULLFILLMENT.csv` is for **open PO tracking only**. Historical receipt data is now in `Inbound_DB.csv`.

---

## Executive Overview - Operating Budget (OTB)

The Executive Overview page includes an Operating Budget tab that provides a standard buyer/planner OTB (Open-to-Buy) view of supply chain activity.

### Overview

The Operating Budget tab displays a rolling 12-month view of:
- **Past 6 months:** Historical actuals
- **Current month:** Month-to-date actuals
- **Future 5 months:** Placeholder for budget forecasts (to be added)

### Data Sections

| Section | Source Data | Description |
|---------|-------------|-------------|
| **OUTBOUND** | `DELIVERIES.csv` | Units/value shipped to customers |
| **INBOUND** | `Inbound_DB.csv` | Units/value received from vendors |
| **INVENTORY** | `INVENTORY.csv` | Current inventory snapshot (ending balance) |

### View Options

| Option | Description |
|--------|-------------|
| **Units vs Value Toggle** | Switch between quantity view and monetary value view |
| **Currency Selection** | Display values in USD (default) or EUR via sidebar global currency selector |
| **Time Aggregation** | Monthly, Quarterly, or YTD views |

### Currency Conversion Rules

The Operating Budget respects the following currency rules from `CURRENCY_RULES`:

| Source Currency | Target: USD | Target: EUR |
|-----------------|-------------|-------------|
| **Group Currency (EUR)** | Convert using `EUR_to_USD` rate (1.08) | No conversion |
| **Plant/Local Currency (USD)** | No conversion | Convert using `USD_to_EUR` rate (0.93) |

**Currency field identification:**
- `POP Last Purchase: Currency` contains "GROUP" → Source is EUR
- `POP Last Purchase: Currency` contains "PLANT" or "LOCAL" → Source is USD

### Aggregation by Category

All sections aggregate data by product category (from `PLM: Level Classification 4` in Master Data):
- Each row represents one category
- Columns show monthly values (past 6 + current + future 5)
- **Total row** shows sum across all categories

### Future Enhancements

The following features are planned for future development:
- **Inventory Turns:** Calculated from COGS / Average Inventory
- **Days Inventory Outstanding (DIO):** By category
- **Open-to-Buy (OTB):** Budget remaining = Budget - Committed - On Order
- **Plan vs Actual Variance:** Compare actuals to budget plan
- **Budget File Integration:** Import forecast budget for future months

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

### Demand Anomaly Detection and Smoothing

The forecasting engine includes a two-step demand smoothing process to handle statistical anomalies from SKU, customer, or order-level outliers.

#### How It Works

1. **Anomaly Detection (Step 1)**: Uses Z-score method to identify demand values that are statistically abnormal
   - Calculates mean and standard deviation of historical demand per SKU
   - Flags values where |Z-score| exceeds the configured threshold
   - Higher thresholds = fewer anomalies flagged

2. **Anomaly Smoothing (Step 2)**: Replaces detected anomalies with the median of non-anomalous values
   - Preserves the underlying demand pattern while removing spikes/drops
   - Uses median (robust to outliers) rather than mean

3. **Exponential Smoothing (Step 3)**: Applies exponential smoothing to the cleaned data
   - Lower alpha = more weight on historical data (smoother forecast)
   - Higher alpha = more weight on recent data (responsive forecast)

#### Smoothing Presets

Three preset configurations are available, with **Balanced** as the default:

| Preset | Z-Score Threshold | Alpha (α) | % Flagged | Use Case |
|--------|------------------|-----------|-----------|----------|
| **Conservative** | 1.5 | 0.1 | ~6.5% | Stable demand planning, risk-averse forecasting |
| **Balanced** | 2.0 | 0.3 | ~4.4% | Recommended default for most scenarios |
| **Aggressive** | 3.0 | 0.5 | ~2.1% | Responsive forecasting, fast-moving products |

#### Configuration Details

**Z-Score Thresholds** (based on analysis of actual demand data):
- Your data has **median CV of 101%** (high volatility)
- Z-score 99th percentile is 4.08 (significant outliers exist)
- Thresholds calibrated to flag appropriate percentage of observations

**Exponential Smoothing Formula**:
```
Forecast_t = α × Actual_t + (1-α) × Forecast_{t-1}
```

Where α (alpha) controls responsiveness:
- α = 0.1 → 10% weight on current, 90% on history
- α = 0.3 → 30% weight on current, 70% on history
- α = 0.5 → 50% weight on current, 50% on history

#### Output Fields

The forecast output includes these fields:

| Field | Description |
|-------|-------------|
| `anomaly_count` | Number of demand observations flagged as anomalies for this SKU |
| `anomaly_pct` | Percentage of observations flagged as anomalies |
| `is_intermittent` | Whether intermittent demand handling was applied |
| `skipped_detection` | Whether anomaly detection was skipped due to insufficient data |
| `applied_z_threshold` | The actual Z-threshold used (may differ from preset for intermittent demand) |
| `smoothing_preset` | The preset used ('Conservative', 'Balanced', or 'Aggressive') |
| `exp_smooth` | Exponentially smoothed forecast value |

### Professional Edge Case Handling

The demand forecasting engine includes professional-grade safeguards for edge cases commonly encountered by demand planners.

#### 1. Minimum Sample Size (30+ Data Points)

**Rule**: Anomaly detection is skipped if fewer than 30 data points are available.

**Rationale**: Z-score statistics require sufficient sample size for statistical validity. With too few observations, the mean and standard deviation estimates are unreliable.

**Behavior**:
- If data points < 30: Anomaly detection is skipped, only exponential smoothing is applied
- A warning is logged: "Insufficient data (N points). Minimum 30 required for anomaly detection."
- The `skipped_detection` field is set to `True` in the output

**Configuration**: `MIN_ANOMALY_DETECTION_SAMPLE_SIZE = 30`

#### 2. Maximum Anomaly Percentage (20% Cap)

**Rule**: If more than 20% of data is flagged as anomalies, a warning is generated for user review.

**Rationale**: When a large portion of data appears anomalous, it may indicate:
- Systematic data quality issues
- Fundamental demand pattern changes
- Inappropriate Z-threshold for this SKU's demand pattern

**Behavior**:
- If anomaly_pct > 20%: A warning is logged and stored in the `warnings` field
- The UI can display this warning and allow export to Excel for detailed review
- Processing continues with the flagged anomalies replaced

**Configuration**: `MAX_ANOMALY_PERCENTAGE = 0.20`

#### 3. Intermittent Demand Handling (CV > 150%)

**Rule**: SKUs with coefficient of variation (CV) > 150% are classified as intermittent demand and receive special handling.

**Rationale**: Intermittent demand (sparse, irregular orders) has a different statistical profile than regular demand. Standard Z-score thresholds would over-flag legitimate spikes as anomalies.

**Behavior**:
- CV is calculated as (standard deviation / mean) × 100
- If CV > 150%: The Z-threshold is automatically increased to 4.0
- A warning is logged: "Intermittent demand detected (CV=X%). Using higher Z-threshold (4.0)."
- The `is_intermittent` field is set to `True` in the output

**Configuration**:
- `INTERMITTENT_DEMAND_CV_THRESHOLD = 150`
- `INTERMITTENT_DEMAND_Z_THRESHOLD = 4.0`

### Seasonality Model

The forecasting engine includes a tiered seasonality model that applies different approaches based on SKU volume and data availability.

#### Tiered Approach

| Tier | Criteria | Seasonality Method |
|------|----------|-------------------|
| **Top 20% by Volume** | SKU total volume in top 20% AND 12+ months history | Individual SKU seasonality profile |
| **Remaining 80%** | All other SKUs | Category-level seasonality profile |

#### How Seasonality Profiles Work

1. **Monthly Seasonal Indices**: Each profile consists of 12 monthly indices (one per calendar month)
2. **Index Interpretation**:
   - Index = 1.0 → Average demand
   - Index > 1.0 → Above-average demand (e.g., 1.2 = 20% above average)
   - Index < 1.0 → Below-average demand (e.g., 0.8 = 20% below average)

3. **Calculation Method**:
   - Monthly Index = (Average demand in month) / (Overall average demand)
   - Missing months default to 1.0 (neutral)

#### Individual vs Category Profiles

**Individual SKU Profiles** (Top 20% by volume with 12+ months history):
- Capture SKU-specific seasonal patterns
- More accurate for high-volume SKUs with unique seasonality
- Require substantial history to be reliable

**Category-Level Profiles** (Remaining 80%):
- Use aggregated demand within each category
- Provide reasonable seasonality even for new or low-volume SKUs
- More robust with limited individual SKU history

#### Configuration Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `TOP_SKU_PERCENTAGE` | 0.20 | Top 20% by volume get individual profiles |
| `MIN_MONTHS_FOR_INDIVIDUAL_SEASONALITY` | 12 | Minimum months of history for individual profiles |

#### Seasonality Functions

| Function | Purpose |
|----------|---------|
| `build_seasonality_model()` | Creates complete seasonality model with all profiles |
| `get_seasonal_index_for_sku()` | Returns the seasonal index for a specific SKU and month |
| `apply_seasonal_adjustment()` | Multiplies base forecast by seasonal index |
| `get_seasonality_summary()` | Returns human-readable summary of the model |

