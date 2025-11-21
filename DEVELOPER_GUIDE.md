# Developer Guide - POP Supply Chain Platform

## Quick Start

### Running the Application

**New Simplified UI (Recommended)**:
```bash
streamlit run dashboard_simple.py
```

**Original UI (Legacy)**:
```bash
streamlit run dashboard.py
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_data_loaders.py

# Run with coverage
pytest --cov=. --cov-report=html

# Run with verbose output
pytest -v
```

---

## Project Structure

```
POP_Supply_Chain/
│
├── dashboard_simple.py       # NEW: Simplified main application
├── dashboard.py              # LEGACY: Original dashboard (complex)
│
├── data_loader.py            # Data loading and transformation
├── file_loader.py            # File I/O utilities
├── utils.py                  # Shared utility functions
│
├── ui_components.py          # NEW: Reusable UI components
│
├── pages/                    # NEW: Modular page components
│   ├── overview_page.py      # Executive dashboard
│   ├── service_level_page.py # Service level analytics
│   ├── (more pages to add)   # Backorder, Inventory, etc.
│
├── tests/                    # NEW: Organized test suite
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures and utilities
│   └── test_data_loaders.py  # Data loader tests
│
├── Data/                     # Source CSV files
│   ├── ORDERS.csv
│   ├── DELIVERIES.csv
│   ├── INVENTORY.csv
│   └── Master Data.csv
│
├── README.md                 # User-facing documentation
├── PROJECT_PLAN.md           # Development roadmap
└── DEVELOPER_GUIDE.md        # This file
```

---

## Adding New Features

### 1. Adding a New Page/Module

**Step 1**: Create the page file
```python
# pages/new_module_page.py

import streamlit as st
import pandas as pd
from ui_components import (
    render_page_header,
    render_kpi_row,
    render_chart,
    render_data_table
)

def render_new_module_page(data):
    """Main render function for new module"""

    # Page header
    render_page_header(
        "New Module",
        icon="🎯",
        subtitle="Description of what this module does"
    )

    # Calculate metrics
    metrics = calculate_metrics(data)

    # Render KPIs
    render_kpi_row(metrics)

    # Add charts, tables, etc.
    # ...

def calculate_metrics(data):
    """Calculate KPIs for this module"""
    return {
        "Metric 1": {"value": "123", "help": "Help text"},
        "Metric 2": {"value": "456", "help": "Help text"}
    }
```

**Step 2**: Register in navigation (`ui_components.py`)
```python
def get_main_navigation():
    return [
        # ... existing items ...
        {
            "id": "new_module",
            "label": "🎯 New Module",
            "description": "Description of new module"
        }
    ]
```

**Step 3**: Add route in main dashboard (`dashboard_simple.py`)
```python
# Import your new page
from pages.new_module_page import render_new_module_page

# Add routing logic
elif selected_page == "new_module":
    render_new_module_page(data=data['some_data'])
```

**Done!** Your new module is now accessible from the navigation.

---

### 2. Adding a New Data Source

**Step 1**: Add data loader function (`data_loader.py`)
```python
@st.cache_data(ttl=3600)
def load_new_data_source():
    """
    Load and transform new data source

    Returns:
        logs: List of log messages
        df: Transformed DataFrame
        errors: DataFrame of errors
        metadata: Dict of metadata
    """
    logs = []
    errors = pd.DataFrame()

    try:
        # Load the CSV
        df = pd.read_csv("data/NEW_DATA.csv")

        logs.append(f"INFO: Loaded {len(df)} rows from NEW_DATA.csv")

        # Transform data
        df = df.rename(columns={
            'OldColumn': 'new_column',
            # ... more renames
        })

        # Data quality checks
        if df.empty:
            logs.append("WARNING: NEW_DATA.csv is empty")

        # Return results
        return logs, df, errors, {'record_count': len(df)}

    except Exception as e:
        logs.append(f"ERROR: Failed to load NEW_DATA.csv: {str(e)}")
        return logs, pd.DataFrame(), errors, {}
```

**Step 2**: Add to main data loading (`dashboard_simple.py`)
```python
@st.cache_data(ttl=3600)
def load_all_data():
    try:
        # ... existing loaders ...
        new_data = load_new_data_source()

        return {
            # ... existing data ...
            'new_data': new_data,
            'load_time': datetime.now()
        }
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return None
```

**Step 3**: Add tests (`tests/test_data_loaders.py`)
```python
class TestNewDataLoader:
    def test_load_new_data_source_success(self):
        logs, df, errors, _ = load_new_data_source()
        assert not df.empty
        assert 'new_column' in df.columns
```

---

### 3. Adding a New UI Component

**Add to `ui_components.py`**:
```python
def render_your_new_component(param1, param2):
    """
    Description of what this component does

    Args:
        param1: Description
        param2: Description

    Returns:
        Whatever it returns (if applicable)
    """
    # Implementation
    st.subheader("Your Component")
    # ... component logic
```

**Use in pages**:
```python
from ui_components import render_your_new_component

# In your page
render_your_new_component(param1="value", param2="value")
```

---

### 4. Adding Filters to a Page

**Use the built-in filter system**:
```python
def get_filters_config(data):
    """Define filters for this page"""
    return [
        {
            "type": "selectbox",
            "label": "Category",
            "options": ['All'] + list(data['category'].unique()),
            "key": "category_filter"
        },
        {
            "type": "multiselect",
            "label": "Customers",
            "options": list(data['customer'].unique()),
            "key": "customer_filter",
            "default": []
        },
        {
            "type": "date",
            "label": "Start Date",
            "key": "start_date_filter",
            "default": datetime.now() - timedelta(days=30)
        },
        {
            "type": "slider",
            "label": "Min Quantity",
            "min": 0,
            "max": 1000,
            "key": "min_qty_filter",
            "default": 0
        }
    ]

def render_my_page(data):
    # Render filters
    filters = render_filter_section(get_filters_config(data))

    # Apply filters
    filtered_data = data.copy()
    if filters['category_filter'] != 'All':
        filtered_data = filtered_data[
            filtered_data['category'] == filters['category_filter']
        ]

    # Use filtered data
    render_data_table(filtered_data)
```

---

## Code Style Guidelines

### 1. Python Code Style
- Follow PEP 8
- Use type hints where appropriate
- Document functions with docstrings
- Keep functions focused and small (< 50 lines)
- Use meaningful variable names

**Example**:
```python
def calculate_service_level(
    deliveries: pd.DataFrame,
    orders: pd.DataFrame
) -> dict:
    """
    Calculate service level metrics

    Args:
        deliveries: DataFrame with delivery records
        orders: DataFrame with order records

    Returns:
        Dictionary with service level metrics
    """
    # Implementation
    pass
```

### 2. Streamlit UI Patterns

**Good**:
```python
# Clear structure
render_page_header("Title", subtitle="Description")

# Use helper functions
metrics = calculate_metrics(data)
render_kpi_row(metrics)

# Organize with columns
col1, col2 = st.columns(2)
with col1:
    render_chart(fig1)
with col2:
    render_chart(fig2)
```

**Avoid**:
```python
# Don't mix business logic and UI
st.title("Title")
value = data['column'].sum()  # Calculate inline
st.metric("Label", value)  # Directly render

# Don't repeat code
st.metric("Metric 1", val1)
st.metric("Metric 2", val2)
st.metric("Metric 3", val3)
# Instead, use render_kpi_row() with a dict
```

### 3. Data Loading Patterns

**Always return tuple**:
```python
def load_data():
    logs = []
    errors = pd.DataFrame()

    # ... load and process ...

    return logs, df, errors, metadata
```

**Use caching**:
```python
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_expensive_data():
    # ... expensive operation ...
    return data
```

**Error handling**:
```python
try:
    df = pd.read_csv(filepath)
    logs.append(f"INFO: Loaded {len(df)} rows")
except FileNotFoundError:
    logs.append(f"ERROR: File not found: {filepath}")
    return logs, pd.DataFrame(), errors, {}
except Exception as e:
    logs.append(f"ERROR: Unexpected error: {str(e)}")
    return logs, pd.DataFrame(), errors, {}
```

---

## Testing Guidelines

### 1. Test Structure

**File naming**: `test_<module_name>.py`

**Test class organization**:
```python
class TestModuleName:
    """Test suite for module functionality"""

    def test_basic_functionality(self):
        """Tests basic happy path"""
        # Arrange
        data = create_test_data()

        # Act
        result = function_under_test(data)

        # Assert
        assert result is not None
        assert len(result) > 0

    def test_edge_case(self):
        """Tests specific edge case"""
        # Test implementation
        pass

    def test_error_handling(self):
        """Tests error conditions"""
        with pytest.raises(ValueError):
            function_under_test(invalid_data)
```

### 2. Using Fixtures

**Use shared fixtures from `conftest.py`**:
```python
def test_with_mock_data(mock_master_data_csv):
    """Use fixture in your test"""
    logs, df, _, _ = load_master_data("master_data.csv")
    assert not df.empty
```

**Create test-specific fixtures**:
```python
@pytest.fixture
def custom_test_data():
    """Fixture for specific test needs"""
    return pd.DataFrame({
        'col1': [1, 2, 3],
        'col2': ['a', 'b', 'c']
    })

def test_something(custom_test_data):
    result = process(custom_test_data)
    assert result == expected
```

### 3. Test Coverage Goals

- **Data loaders**: 90%+ coverage
- **UI components**: 70%+ coverage (UI is harder to test)
- **Business logic**: 95%+ coverage
- **Integration tests**: Cover main workflows

### 4. Deprecation / regression guard tests

We include a small pytest regression test `test_no_use_container_width.py` which fails if the deprecated Streamlit argument `use_container_width` appears anywhere in the repo. This prevents accidental re-introduction of the old API — please update to `width='stretch'` or `width='content'` when modifying UI code.

---

## Performance Optimization

### 1. Data Loading
- Use `@st.cache_data` for expensive operations
- Load only required columns: `pd.read_csv(file, usecols=['col1', 'col2'])`
- Use chunking for large files: `pd.read_csv(file, chunksize=10000)`

### 2. UI Rendering
- Use `st.dataframe()` for large tables (more efficient than `st.table()`)
- Limit displayed rows with `df.head(100)`
 - Use `width='stretch'` for responsive layouts (replaces deprecated `use_container_width=True`).
     For fixed/content width use `width='content'` (replaces `use_container_width=False`).
- Avoid unnecessary reruns with `st.cache_data`

### 3. Filtering
- Filter early in the pipeline
- Use pandas efficiently: `df.loc[]` not `df.iterrows()`
- Cache filtered results when possible

---

## Debugging Tips

### 1. Data Issues
Use the debug tools:
```bash
python inventory_validator.py       # Check inventory data
python debug_service_level.py       # Trace service level issues
python debug_backorder_loading.py   # Check backorder data
python debug_unknown_products.py    # Find missing master data
```

### 2. UI Issues
Add debug info:
```python
# Show data structure
with st.expander("Debug: Data Info"):
    st.write(f"Shape: {df.shape}")
    st.write(f"Columns: {df.columns.tolist()}")
    st.dataframe(df.head())
```

### 3. Performance Issues
Profile your code:
```python
import time

start = time.time()
result = expensive_function()
st.write(f"Took {time.time() - start:.2f} seconds")
```

---

## Deployment Checklist

Before deploying to production:

- [ ] All tests passing (`pytest`)
- [ ] Code follows style guidelines
- [ ] No hardcoded file paths (use environment variables)
- [ ] Error handling for all data loads
- [ ] Performance validated (< 5 sec load time)
- [ ] User documentation updated
- [ ] Sample data available for testing
- [ ] Backup of production data
- [ ] Rollback plan documented

---

## Common Patterns

### Pattern: Page with Filters
```python
def render_page_with_filters(data):
    render_page_header("Title", icon="📊")

    # Define and render filters
    filters = render_filter_section(get_filters_config(data))

    # Apply filters
    filtered = apply_filters(data, filters)

    # Show metrics
    metrics = calculate_metrics(filtered)
    render_kpi_row(metrics)

    # Show details
    render_data_table(filtered)
```

### Pattern: Chart + Table
```python
def render_analysis_section(data):
    st.subheader("Analysis")

    # Chart
    fig = create_chart(data)
    render_chart(fig, height=400)

    st.divider()

    # Summary table
    summary = data.groupby('category').sum()
    render_data_table(summary, downloadable=True)
```

### Pattern: KPI Cards
```python
def render_kpis(data):
    metrics = {
        "Total": {
            "value": f"{len(data):,}",
            "help": "Total records"
        },
        "Average": {
            "value": f"{data['value'].mean():.1f}",
            "delta": "+5%",
            "help": "Average value"
        }
    }
    render_kpi_row(metrics)
```

---

## Getting Help

1. **Check the documentation**: README.md, PROJECT_PLAN.md, this file
2. **Review examples**: Look at existing pages like `service_level_page.py`
3. **Run tests**: Tests serve as examples of how to use functions
4. **Debug tools**: Use the included debug scripts
5. **Ask questions**: Document your questions and findings

---

## Contributing

When adding new features:

1. **Plan first**: Update PROJECT_PLAN.md with your approach
2. **Write tests**: TDD approach recommended
3. **Implement**: Follow code style guidelines
4. **Document**: Update this guide if you add patterns
5. **Review**: Test thoroughly before merging

---

**Happy Coding! Let's build an amazing supply chain platform together!** 🚀
