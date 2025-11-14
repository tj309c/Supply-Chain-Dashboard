# Lazy Filter Loading Implementation

## Overview
Implemented lazy filter loading pattern across all 4 dashboard reports (Service Level, Backorder, Inventory Management, Demand Forecasting) to prevent data reloads on every filter widget change.

## Problem Statement
Previously, whenever a user selected a different filter value (year, customer, product, etc.), the report would immediately re-render with the new data. This caused:
- Slow UI responsiveness on large datasets
- Unnecessary data processing
- Poor user experience when selecting multiple filters

## Solution: Lazy Filter Loading Pattern

### How It Works
1. **Data Loading**: Initial data load happens globally (service_data, backorder_data, inventory_analysis_data, orders_data)
2. **Widget Changes**: User changes filter selections in sidebar → **NO data reload occurs**
3. **Filter Application**: User clicks "Apply Filters" button → Data is filtered and report updates
4. **State Tracking**: 
   - `applied_filters_{report_view}` = Last saved filter state (what's currently rendered)
   - `active_filters_{report_view}` = Used for comparison to detect changes
   - If user changes filters, a message shows: "You have changed the filters. Click 'Apply Filters' in the sidebar to update the report."

### Key Implementation Details

#### 1. New Function: `get_lazy_filtered_data()`
Located in dashboard.py (~line 1191)

```python
def get_lazy_filtered_data(raw_df, report_view, f_year, f_month, f_customer, 
                           f_category, f_material, f_sales_org, f_order_type, 
                           f_order_reason=None) -> tuple:
    """
    Returns (filtered_dataframe, has_pending_filters)
    
    Logic:
    - Builds current widget state dictionary
    - Compares against applied_filters_{report_view}
    - If match: applies filters and returns (filtered_df, False)
    - If mismatch: returns (raw_df, True) with pending flag
    """
```

#### 2. Apply Filters Button Update
When "Apply Filters" is clicked:
```python
filter_dict = {
    'order_year': f_year,
    'order_month': f_month,
    'customer_name': f_customer,
    'category': f_category,
    'product_name': f_material,
    'sales_org': f_sales_org,
    'order_type': f_order_type,
    'order_reason': f_order_reason
}
# Save applied state (for rendering) and active state (for comparison)
st.session_state[f'applied_filters_{report_view}'] = filter_dict
st.session_state[f'active_filters_{report_view}'] = filter_dict
```

#### 3. Report-by-Report Updates

**Service Level Report** (line ~1776):
```python
f_service, has_pending_filters = get_lazy_filtered_data(
    service_data, report_view, 
    f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type
)
if has_pending_filters:
    st.info("You have changed the filters. Click 'Apply Filters' in the sidebar to update the report.")
```

**Backorder Report** (line ~1902):
```python
f_backorder, has_pending_filters = get_lazy_filtered_data(
    backorder_data, report_view, 
    f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type, f_order_reason
)
```

**Inventory Management** (line ~2010):
```python
f_inventory, has_pending_filters = get_lazy_filtered_data(
    inventory_analysis_data, report_view, 
    f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type
)
```

**Demand Forecasting** (line ~1600):
```python
orders_data_filtered, has_pending_filters = get_lazy_filtered_data(
    orders_data, report_view,
    f_year, f_month, f_customer, f_category, f_material, f_sales_org, f_order_type
)
# Then use orders_data_filtered for forecasting instead of orders_data
```

## Data Isolation Maintained
Each report uses its own `applied_filters_{report_view}` key:
- Service Level: `applied_filters_Service Level`
- Backorder: `applied_filters_Backorder Report`
- Inventory: `applied_filters_Inventory Management`
- Demand Forecasting: `applied_filters_📈 Demand Forecasting`

This ensures filters in one report do NOT affect other reports' data.

## Benefits
✅ **Performance**: No data reloads on filter widget changes  
✅ **Responsiveness**: UI responds instantly to filter selections  
✅ **User Control**: User can batch multiple filter changes before applying  
✅ **Isolation**: Each report's filters are independent  
✅ **Consistency**: Same pattern applied across all 4 reports  
✅ **Transparency**: Clear message when filters have pending changes  

## Testing Checklist
- [x] Python syntax validation passed
- [x] All 4 reports use lazy loading
- [x] Applied Filters button saves filter state
- [x] Pending filter message displays when filters differ
- [ ] Test locally: Change filters → no data reload
- [ ] Test locally: Click Apply Filters → data updates
- [ ] Test locally: Switch between reports → filters isolated
- [ ] Test locally: Demand Forecasting enrichment works with lazy loading

## Files Modified
- `dashboard.py`: Added `get_lazy_filtered_data()` function and updated all 4 reports
- No changes needed to `data_loader.py` or `utils.py`

## Rollback Instructions
If needed, run: `git checkout dashboard.py`

## Notes
- All filter widget variables (f_year, f_month, etc.) are passed as parameters to avoid global scope issues
- The function handles both single-select (year, month) and multi-select (customer, category, etc.) filters
- Empty lists `[]` and "All" values are treated as "no filter applied"
