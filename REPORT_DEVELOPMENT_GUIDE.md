# Report Development Guide

## Overview
This guide documents the critical patterns and lessons learned from developing reports in the Supply Chain Dashboard. Use this when creating new reports to avoid common pitfalls.

---

## 🔴 Critical Lesson: Data Structure Mismatch

### The Problem
**Dashboard code expects columns from raw CSV files, but data_loader functions return processed/transformed data with different column names.**

This is the most common source of crashes in new reports.

### Historical Example: Inventory Management Report

**What Happened:**
- Dashboard code referenced columns like: `Material Number`, `Material Description`, `POP Material: POP/Non POP`, `PLM: Level Classification 2 (Attribute D_TMKLVL2CLS)`, etc.
- But `load_inventory_analysis_data()` returns only 5 columns: `sku`, `on_hand_qty`, `daily_demand`, `dio`, `category`
- Result: Crashes when filtering or displaying data

**What We Did to Fix:**
1. ✅ Ran `python3` test to inspect actual columns returned by data_loader function
2. ✅ Updated filter creation to only use columns that actually exist
3. ✅ Added defensive `if column in df.columns` checks before accessing columns
4. ✅ Simplified display table to show only available columns
5. ✅ Updated KPI calculations to use correct column names

---

## 📋 Checklist for Creating New Reports

### Phase 1: Data Exploration (BEFORE writing dashboard code)

- [ ] **Inspect the actual data_loader function output**
  ```python
  from data_loader import load_your_report_data
  logs, df = load_your_report_data()  # or however your function returns data
  print(df.columns.tolist())
  print(df.head())
  print(df.dtypes)
  ```

- [ ] **Document exact column names** - Copy/paste directly from the output above
  
- [ ] **Test each calculation independently**
  ```python
  # Test filters exist
  print(df[column_name].unique())
  
  # Test calculations work
  result = df[column_name].sum()
  ```

- [ ] **Note data types** - Some columns might be object/string when you expect numeric

### Phase 2: Dashboard Code Structure

#### 1. **Filter Creation** (ALWAYS defensive)

**❌ WRONG:**
```python
f_material = create_multiselect_filter("Material:", f_inventory, 'Material Number', "filter_key")
f_category = create_multiselect_filter("Category:", f_inventory, 'category', "filter_cat")
```

**✅ RIGHT:**
```python
# Check column exists before creating filter
f_material = create_multiselect_filter("SKU:", f_inventory, 'sku', "inv_sku") if 'sku' in f_inventory.columns else []
f_category = create_multiselect_filter("Category:", f_inventory, 'category', "inv_category") if 'category' in f_inventory.columns else []
```

#### 2. **Filter Application** (ALWAYS check column existence)

**❌ WRONG:**
```python
if applied_filters.get('material_number'):
    f_data = f_data[f_data['Material Number'].isin(applied_filters['material_number'])]
```

**✅ RIGHT:**
```python
if applied_filters.get('material_number') and 'sku' in f_data.columns:
    f_data = f_data[f_data['sku'].isin(applied_filters['material_number'])]
```

#### 3. **KPI Calculations** (Use actual column names from data_loader)

**❌ WRONG:**
```python
total_on_hand = f_inventory['POP Actual Stock Qty'].sum()
```

**✅ RIGHT:**
```python
total_on_hand = f_inventory['on_hand_qty'].sum() if 'on_hand_qty' in f_inventory.columns else 0
```

#### 4. **Display Tables** (Only include columns that exist)

**❌ WRONG:**
```python
display_cols = ['Material Number', 'Description', 'Price', 'Stock Value']
df_display = f_data[display_cols]
```

**✅ RIGHT:**
```python
display_cols = ['sku', 'category', 'on_hand_qty', 'dio']
df_display = f_data[[col for col in display_cols if col in f_data.columns]]
```

#### 5. **Data Preparation for Charts/Anomalies** (Add computed columns before using)

**Example: Anomaly detection needs 'avg_dio' but it doesn't exist**

```python
# Prepare data with computed column
f_data_for_anomalies = f_data.copy()
if 'on_hand_qty' in f_data_for_anomalies.columns and 'daily_demand' in f_data_for_anomalies.columns:
    f_data_for_anomalies['avg_dio'] = np.where(
        f_data_for_anomalies['daily_demand'] > 0,
        f_data_for_anomalies['on_hand_qty'] / f_data_for_anomalies['daily_demand'],
        0
    )

# NOW use the function that expects 'avg_dio'
anomalies = detect_anomalies(f_data_for_anomalies, sensitivity)
```

---

## 🛡️ Defensive Programming Patterns

### Pattern 1: Safe Column Access
```python
# ALWAYS use this pattern for filter creation
if column_name in df.columns:
    unique_values = get_unique_values(df, column_name)
    selected = st.sidebar.multiselect(label, unique_values, key=key)
else:
    selected = []
    st.sidebar.warning(f"Column '{column_name}' not found in data")
```

### Pattern 2: Safe Filtering
```python
# Check BOTH: filter exists AND column exists
if applied_filters.get('filter_name') and 'actual_column' in df.columns:
    df = df[df['actual_column'].isin(applied_filters['filter_name'])]
```

### Pattern 3: Safe KPI Calculations
```python
# Use .get() for safety, check column exists
total = df['column_name'].sum() if 'column_name' in df.columns else 0
```

### Pattern 4: Safe Aggregations
```python
if not df.empty and all(col in df.columns for col in ['col1', 'col2', 'col3']):
    agg_result = df.groupby('col1').agg({'col2': 'sum', 'col3': 'mean'})
else:
    agg_result = pd.DataFrame()
```

---

## 🧪 Testing Checklist

Before deploying a new report:

- [ ] **Syntax Check**
  ```bash
  python3 -m py_compile dashboard.py
  ```

- [ ] **Data Flow Test** (outside Streamlit)
  ```python
  from data_loader import load_your_data
  df = load_your_data()
  print(f"Shape: {df.shape}")
  print(f"Columns: {df.columns.tolist()}")
  print(f"Sample:\n{df.head()}")
  ```

- [ ] **Filter Creation Test**
  - Verify filters appear in sidebar
  - Verify dropdown shows values from actual data
  - No column not found errors

- [ ] **Filter Application Test**
  - Select filter values
  - Click "Apply Filters"
  - Verify data reduces correctly
  - No crashes

- [ ] **KPI Display Test**
  - Verify all KPI values display
  - Verify calculations are correct
  - No $0 or NaN values when data exists

- [ ] **Chart Rendering Test**
  - Verify charts render without errors
  - Verify data looks correct
  - Check both with and without filters applied

- [ ] **Anomaly Detection Test** (if using)
  - Verify anomaly count displays
  - Verify details expand/collapse
  - Change sensitivity level - verify updates in real-time

- [ ] **Export Test** (if using)
  - Download Excel file
  - Verify columns and data are present

---

## 📚 Key Functions Reference

### Data Loader Functions
Each returns: `(logs, dataframe, [errors])`

```python
from data_loader import load_master_data, load_inventory_data, load_service_data

# Check documentation for exact return format:
logs, df = load_inventory_data(filepath)
logs, df, errors = load_service_data(filepath, orders_header, master_data)
```

### Utility Functions
```python
from utils import (
    calculate_inventory_stock_value,  # Adds Stock Value USD column
    enrich_orders_with_category,      # Joins with master data for category
    get_unique_values,                 # Get sorted unique values (DRY)
    format_dataframe_number            # Format values consistently
)
```

### Dashboard Helper Functions
```python
# Safe filter creation
create_multiselect_filter(label, df, column, key_suffix) -> list

# Data quality checks
get_data_quality_summary(df) -> dict

# Anomaly detection
detect_inventory_anomalies(df, sensitivity) -> dict
```

---

## 🚨 Common Mistakes & Solutions

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Using CSV column names instead of data_loader output | KeyError when filtering | Inspect actual data_loader output columns |
| Not checking if column exists | AttributeError/KeyError crash | Add `if col in df.columns` before access |
| Filters disappear when data is empty | Greyed out filters | Check `if not df.empty` before creating filters |
| Stock values show as $0 | Incorrect calculations | Check price/quantity columns exist and have values |
| Charts fail to render | Missing data or wrong column names | Validate all required columns present before charting |
| Anomaly detection crashes | Data doesn't have expected columns | Add computed columns before calling detection function |

---

## 📝 Example: Complete New Report Setup

```python
# Step 1: Load data with defensive checks
if report_view == "My New Report":
    try:
        from data_loader import load_my_report_data
        logs, my_data = load_my_report_data()
        st.session_state.my_data = my_data
    except Exception as e:
        st.error(f"Error loading my report data: {e}")
        my_data = pd.DataFrame()

# Step 2: Prepare filtered dataset
f_data = my_data.copy() if not my_data.empty else pd.DataFrame()

# Step 3: Create filters (defensive)
if not f_data.empty:
    # Only create filters for columns that exist
    f_column1 = create_multiselect_filter("Column 1:", f_data, 'column1', "key1") if 'column1' in f_data.columns else []
    f_column2 = create_multiselect_filter("Column 2:", f_data, 'column2', "key2") if 'column2' in f_data.columns else []
else:
    f_column1 = []
    f_column2 = []
    st.sidebar.error("No data available")

# Step 4: Apply filters (defensive)
if st.sidebar.button("Apply Filters"):
    if f_column1 and 'column1' in f_data.columns:
        f_data = f_data[f_data['column1'].isin(f_column1)]
    if f_column2 and 'column2' in f_data.columns:
        f_data = f_data[f_data['column2'].isin(f_column2)]

# Step 5: Display KPIs (with defaults)
if not f_data.empty:
    kpi1 = f_data['kpi_column'].sum() if 'kpi_column' in f_data.columns else 0
    st.metric("KPI Label", f"{kpi1:,.2f}")
else:
    st.info("No data to display")

# Step 6: Render charts (with error handling)
try:
    if not f_data.empty:
        # Chart code here
        pass
except KeyError as e:
    st.error(f"Missing column: {e}")
except Exception as e:
    st.error(f"Error rendering chart: {e}")
```

---

## 🔗 Related Files
- `dashboard.py` - Main application (see Inventory Management section as example)
- `data_loader.py` - Data loading functions with correct column names
- `utils.py` - Shared utility functions
- `COMPLETION_SUMMARY.md` - Overall project status

---

## 📞 Questions?
When creating a new report and unsure about column names:
1. Run the data_loader function in Python
2. Print the columns and sample data
3. Update dashboard code to match actual output, not assumptions
4. Use defensive checks everywhere
5. Test outside Streamlit first

**Remember:** The data structure is the source of truth. Your dashboard code must adapt to it, not the other way around.
