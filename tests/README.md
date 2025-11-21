# Test Suite Documentation

## Overview

Comprehensive test suite for the POP Supply Chain Dashboard ensuring code quality, data integrity, and application reliability.

## Test Organization

```
tests/
├── README.md                          # This file
├── __init__.py                        # Test package initialization
├── conftest.py                        # Shared fixtures and utilities
├── test_data_loaders_real_data.py    # Data loader tests with real CSV files
├── test_ui_components.py              # UI component tests
├── test_utils.py                      # Utility function tests
├── test_file_loader.py                # File I/O tests
└── test_integration.py                # End-to-end integration tests (future)
```

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_data_loaders_real_data.py
```

### Run Specific Test Class
```bash
pytest tests/test_data_loaders_real_data.py::TestMasterDataLoader
```

### Run Specific Test
```bash
pytest tests/test_data_loaders_real_data.py::TestMasterDataLoader::test_load_master_data_success
```

### Run with Verbose Output
```bash
pytest -v
```

### Run with Coverage Report
```bash
pytest --cov=. --cov-report=html
```

### Run Tests by Marker
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run everything except slow tests
pytest -m "not slow"
```

## Test Categories

### Data Loader Tests (`test_data_loaders_real_data.py`)
- **File Existence**: Verify all required CSV files are present
- **Master Data**: Test SKU loading, deduplication, and data quality
- **Orders Data**: Test order parsing, date handling, and aggregation
- **Service Data**: Test delivery metrics and on-time calculations
- **Backorder Data**: Test backorder filtering and aging calculations
- **Inventory Data**: Test stock level loading and validation
- **Integration**: Test complete pipeline and referential integrity
- **Performance**: Ensure data loads within acceptable timeframes

### UI Component Tests (`test_ui_components.py`)
- **Navigation**: Test menu structure and navigation helpers
- **Formatters**: Test number, currency, percentage, and date formatting
- **Render Functions**: Test UI component rendering (future)

### Utils Tests (`test_utils.py`)
- **Excel Export**: Test data export to Excel format
- **Data Filtering**: Test filter application logic (future)
- **Helper Functions**: Test utility functions (future)

### File Loader Tests (`test_file_loader.py`)
- **Safe CSV Reading**: Test error handling for missing/malformed files
- **Column Selection**: Test reading specific columns
- **Encoding Handling**: Test various file encodings (future)

## Test Fixtures

### Shared Fixtures (`conftest.py`)
- **mock_master_data_csv**: Mock master data for unit testing
- **mock_orders_csv**: Mock orders data with various scenarios
- **mock_deliveries_csv**: Mock delivery data
- **mock_inventory_csv**: Mock inventory data
- **mock_read_csv**: Auto-used fixture that intercepts pd.read_csv calls

### Helper Functions
- `assert_log_contains(logs, message)`: Assert log contains expected message
- `assert_columns_exist(df, columns)`: Assert DataFrame has required columns
- `assert_no_nulls(df, columns)`: Assert columns have no null values
- `assert_dataframe_not_empty(df, message)`: Assert DataFrame has data

## Writing New Tests

### Test Naming Convention
- Test files: `test_<module_name>.py`
- Test classes: `Test<FeatureName>`
- Test functions: `test_<specific_behavior>`

### Example Test Structure
```python
class TestFeatureName:
    """Test suite for feature functionality"""

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
```

### Using Markers
Add markers to categorize tests:
```python
@pytest.mark.unit
def test_simple_function():
    pass

@pytest.mark.integration
def test_full_pipeline():
    pass

@pytest.mark.slow
def test_large_dataset():
    pass
```

## Test Data

### Real Data Tests
Tests in `test_data_loaders_real_data.py` use actual CSV files from the `Data/` directory. Ensure these files exist:
- `Data/Master Data.csv`
- `Data/ORDERS.csv`
- `Data/DELIVERIES.csv`
- `Data/INVENTORY.csv`

### Mock Data Tests
Tests using fixtures can run without real data files. Mock fixtures are defined in `conftest.py`.

## Coverage Goals

- **Data Loaders**: 90%+ coverage
- **UI Components**: 70%+ coverage
- **Utility Functions**: 95%+ coverage
- **Integration Tests**: Cover main workflows

## Continuous Integration

When setting up CI/CD:
1. Install dependencies: `pip install -r requirements.txt`
2. Install test dependencies: `pip install pytest pytest-cov`
3. Run tests: `pytest --cov=. --cov-report=xml`
4. Upload coverage reports to codecov or similar

## Troubleshooting

### Tests Fail Due to Missing Files
Ensure all required CSV files exist in the `Data/` directory.

### Import Errors
Ensure you're running tests from the project root:
```bash
cd c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain
pytest
```

### Streamlit Warnings
Warnings like "missing ScriptRunContext" are normal when testing Streamlit apps outside of `streamlit run`. They can be ignored.

### Slow Tests
Use the `@pytest.mark.slow` marker and run fast tests only:
```bash
pytest -m "not slow"
```

## Future Enhancements

- [ ] Add tests for page modules (`test_pages.py`)
- [ ] Add end-to-end integration tests (`test_integration.py`)
- [ ] Add performance benchmarking tests
- [ ] Add data quality regression tests
- [ ] Set up CI/CD pipeline
- [ ] Add test coverage reporting
- [ ] Add mutation testing

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Testing Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- [Project README](../README.md)
- [Developer Guide](../DEVELOPER_GUIDE.md)

---

**Last Updated**: 2025-11-21
**Maintainer**: POP Supply Chain Development Team
