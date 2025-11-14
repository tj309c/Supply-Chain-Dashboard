# Filter Optimization Strategy

## Problem
Currently, every filter widget change triggers a full Streamlit rerun, causing:
- Data to reload on each filter selection
- Expensive calculations to rerun
- Slow user experience when selecting multiple filters
- Poor UX when trying to build complex filter combinations

## Solution: Lazy Filter Application
Apply filters ONLY when user explicitly clicks "Apply Filters" button.

### Implementation Pattern

```
1. Load full data once → Cache it
2. Display filter widgets (no data changes on selection)
3. When "Apply Filters" clicked:
   - Apply all filter criteria to cached data
   - Recalculate visualizations
   - Show results
```

### Benefits
✅ **Performance**: No data reloads on filter selection
✅ **UX**: Users can select multiple filters before applying
✅ **Predictability**: Changes only visible after explicit action
✅ **Efficiency**: Single calculation vs multiple intermediate calculations

### Implementation Details

For Demand Forecasting Report:
1. Load orders data → store in session_state with unique key per report
2. Collect filter selections → store in session_state (NOT applied yet)
3. On "Apply Filters" click:
   - Retrieve cached orders data
   - Apply all filters at once
   - Recalculate forecast
   - Update visualizations

### Current Scope
- **Demand Forecasting**: IMPLEMENTED (lazy filter application)
- **Service Level Report**: FUTURE (can be applied if needed)
- **Backorder Report**: FUTURE (can be applied if needed)
- **Inventory Management**: FUTURE (can be applied if needed)

### Session State Keys Used
- `df_orders_demand_forecasting`: Cached orders data (loaded once)
- `active_filters_📈 Demand Forecasting`: Current filter selections (applied on button click)

### Technical Notes
- Use `st.session_state` to persist data across reruns
- Only reload data if file paths change or cache is explicitly cleared
- Apply filters in one pass using `apply_filters()` function
- Show visual indicator of which filters are active vs. pending
