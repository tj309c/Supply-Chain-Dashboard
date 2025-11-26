"""
Date Validation Tests for CSV Data Files

Detects date format misalignments, unparseable dates, and provides
debugging information for data quality issues.
"""

import pytest
import pandas as pd
import os
import sys
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# Setup paths
current_file_path = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(current_file_path))
sys.path.insert(0, project_root)

# --- 1. DATE VALIDATION UTILITIES ---

@dataclass
class DateValidationResult:
    """Results from validating a date column"""
    column_name: str
    total_rows: int
    original_nulls: int
    parse_failures: int
    failed_samples: List[str]
    detected_format: Optional[str]
    ambiguous_dates: int  # Dates that could be valid in multiple formats
    warning_message: Optional[str]


def detect_date_format(series: pd.Series) -> Tuple[str, float]:
    """
    Attempt to detect the date format in a series.
    Returns (format_string, success_rate)
    """
    # Common date formats to try
    formats = [
        ('%m/%d/%Y', 'MM/DD/YYYY (US)'),
        ('%d/%m/%Y', 'DD/MM/YYYY (EU)'),
        ('%Y-%m-%d', 'YYYY-MM-DD (ISO)'),
        ('%m-%d-%Y', 'MM-DD-YYYY'),
        ('%d-%m-%Y', 'DD-MM-YYYY'),
        ('%Y/%m/%d', 'YYYY/MM/DD'),
        ('%m/%d/%y', 'MM/DD/YY (US short)'),
        ('%d/%m/%y', 'DD/MM/YY (EU short)'),
    ]

    best_format = None
    best_success = 0.0

    non_null = series.dropna()
    if len(non_null) == 0:
        return None, 0.0

    for fmt, name in formats:
        try:
            parsed = pd.to_datetime(non_null, format=fmt, errors='coerce')
            success_rate = parsed.notna().sum() / len(non_null)
            if success_rate > best_success:
                best_success = success_rate
                best_format = name
        except Exception:
            continue

    return best_format, best_success


def find_ambiguous_dates(series: pd.Series) -> List[str]:
    """
    Find dates that could be valid in multiple formats (e.g., 03/04/2024 could be
    March 4 or April 3).
    """
    ambiguous = []
    for val in series.dropna().unique():
        val_str = str(val).strip()
        if '/' in val_str or '-' in val_str:
            parts = val_str.replace('-', '/').split('/')
            if len(parts) >= 2:
                try:
                    first, second = int(parts[0]), int(parts[1])
                    # Ambiguous if both parts could be month or day
                    if 1 <= first <= 12 and 1 <= second <= 12 and first != second:
                        ambiguous.append(val_str)
                except ValueError:
                    pass
    return ambiguous[:10]  # Return up to 10 examples


def validate_date_column(df: pd.DataFrame, column_name: str,
                        expected_format: str = None) -> DateValidationResult:
    """
    Validate a date column and return detailed results.

    Args:
        df: DataFrame containing the column
        column_name: Name of the date column
        expected_format: Expected format string (e.g., '%m/%d/%Y')

    Returns:
        DateValidationResult with validation details
    """
    if column_name not in df.columns:
        return DateValidationResult(
            column_name=column_name,
            total_rows=len(df),
            original_nulls=len(df),
            parse_failures=0,
            failed_samples=[],
            detected_format=None,
            ambiguous_dates=0,
            warning_message=f"Column '{column_name}' not found in DataFrame"
        )

    col = df[column_name]
    total_rows = len(col)
    original_nulls = col.isna().sum()

    # Try to parse with expected format or auto-detect
    if expected_format:
        parsed = pd.to_datetime(col, format=expected_format, errors='coerce')
    else:
        parsed = pd.to_datetime(col, errors='coerce')

    parse_failures = parsed.isna().sum() - original_nulls

    # Get failed samples
    failed_mask = parsed.isna() & col.notna()
    failed_samples = col[failed_mask].astype(str).head(10).tolist()

    # Detect format
    detected_format, success_rate = detect_date_format(col)

    # Find ambiguous dates
    ambiguous = find_ambiguous_dates(col)

    # Generate warning if needed
    warning = None
    if parse_failures > 0:
        warning = f"Found {parse_failures} dates that failed to parse"
    elif len(ambiguous) > 0:
        warning = f"Found {len(ambiguous)} ambiguous dates (could be MM/DD or DD/MM)"

    return DateValidationResult(
        column_name=column_name,
        total_rows=total_rows,
        original_nulls=original_nulls,
        parse_failures=parse_failures,
        failed_samples=failed_samples,
        detected_format=detected_format,
        ambiguous_dates=len(ambiguous),
        warning_message=warning
    )


def validate_csv_dates(csv_path: str, date_columns: List[str],
                      encoding: str = 'utf-8') -> Dict[str, DateValidationResult]:
    """
    Validate multiple date columns in a CSV file.

    Args:
        csv_path: Path to CSV file
        date_columns: List of column names that should contain dates
        encoding: File encoding

    Returns:
        Dictionary of column_name -> DateValidationResult
    """
    results = {}

    try:
        df = pd.read_csv(csv_path, encoding=encoding, low_memory=False)
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding='latin-1', low_memory=False)
    except Exception as e:
        # Return error results for all columns
        for col in date_columns:
            results[col] = DateValidationResult(
                column_name=col,
                total_rows=0,
                original_nulls=0,
                parse_failures=0,
                failed_samples=[],
                detected_format=None,
                ambiguous_dates=0,
                warning_message=f"Failed to load CSV: {e}"
            )
        return results

    for col in date_columns:
        results[col] = validate_date_column(df, col)

    return results


def print_validation_report(results: Dict[str, DateValidationResult]) -> str:
    """Generate a formatted validation report"""
    lines = ["=" * 60, "DATE VALIDATION REPORT", "=" * 60]

    for col_name, result in results.items():
        lines.append(f"\n--- {result.column_name} ---")
        lines.append(f"Total rows: {result.total_rows}")
        lines.append(f"Original nulls: {result.original_nulls}")
        lines.append(f"Parse failures: {result.parse_failures}")
        lines.append(f"Detected format: {result.detected_format or 'Unknown'}")
        lines.append(f"Ambiguous dates: {result.ambiguous_dates}")

        if result.warning_message:
            lines.append(f"⚠️  WARNING: {result.warning_message}")

        if result.failed_samples:
            lines.append(f"Failed samples: {result.failed_samples[:5]}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# --- 2. TEST DATA CONFIGURATION ---

DATA_DIR = project_root
ATL_PATH = os.path.join(DATA_DIR, "ATL_FULLFILLMENT.csv")
DELIVERIES_PATH = os.path.join(DATA_DIR, "DELIVERIES.csv")
ORDERS_PATH = os.path.join(DATA_DIR, "ORDERS.csv")

# Skip markers for missing files
requires_atl = pytest.mark.skipif(
    not os.path.exists(ATL_PATH),
    reason="ATL_FULLFILLMENT.csv not found"
)
requires_deliveries = pytest.mark.skipif(
    not os.path.exists(DELIVERIES_PATH),
    reason="DELIVERIES.csv not found"
)
requires_orders = pytest.mark.skipif(
    not os.path.exists(ORDERS_PATH),
    reason="ORDERS.csv not found"
)


# --- 3. TEST CASES ---

class TestATLFulfillmentDates:
    """Tests for ATL_FULLFILLMENT.csv date validation"""

    ATL_DATE_COLUMNS = [
        'Order Date',
        'Goods Issue Date',
        'Delivery Creation Date',
        'Pick Up Date',
        'Ship Date',
        'TGT Delivery Date DC',
        'Delivery Date DC',
        'MAX US DelDate'
    ]

    @requires_atl
    def test_atl_date_columns_exist(self):
        """Verify expected date columns exist in ATL file"""
        df = pd.read_csv(ATL_PATH, encoding='latin-1', low_memory=False, nrows=1)

        # Core date columns that must exist
        core_columns = ['Order Date', 'Goods Issue Date', 'Delivery Creation Date']
        missing = [c for c in core_columns if c not in df.columns]

        assert not missing, f"Missing core date columns: {missing}"

    @requires_atl
    def test_atl_core_dates_parse_correctly(self):
        """Verify core date columns parse without errors"""
        results = validate_csv_dates(
            ATL_PATH,
            ['Order Date', 'Goods Issue Date', 'Delivery Creation Date'],
            encoding='latin-1'
        )

        for col_name, result in results.items():
            # Allow placeholder values like "tbd" or "NO"
            assert result.parse_failures <= 5, \
                f"Column '{col_name}' has {result.parse_failures} parse failures: {result.failed_samples}"

    @requires_atl
    def test_atl_date_format_consistency(self):
        """Verify all dates use consistent format (MM/DD/YYYY)"""
        df = pd.read_csv(ATL_PATH, encoding='latin-1', low_memory=False)

        # Check that Order Date uses MM/DD/YYYY format
        order_dates = df['Order Date'].dropna().head(100)

        # If a date like "11/10/2024" parses as November 10, format is MM/DD/YYYY
        # Try parsing with US format
        us_parsed = pd.to_datetime(order_dates, format='%m/%d/%Y', errors='coerce')
        us_success = us_parsed.notna().sum()

        # Try parsing with EU format
        eu_parsed = pd.to_datetime(order_dates, format='%d/%m/%Y', errors='coerce')
        eu_success = eu_parsed.notna().sum()

        # Report detected format
        if us_success > eu_success:
            detected = 'MM/DD/YYYY (US)'
        elif eu_success > us_success:
            detected = 'DD/MM/YYYY (EU)'
        else:
            detected = 'AMBIGUOUS'

        print(f"\nDetected date format: {detected}")
        print(f"US format success: {us_success}/{len(order_dates)}")
        print(f"EU format success: {eu_success}/{len(order_dates)}")

        # Both should parse well, but we expect US format based on sample
        assert us_success >= len(order_dates) * 0.95, \
            f"Expected MM/DD/YYYY format but only {us_success}/{len(order_dates)} parsed"

    @requires_atl
    def test_atl_order_dates_reasonable_range(self):
        """Verify Order Dates are within a reasonable range (not impossibly far in future)"""
        df = pd.read_csv(ATL_PATH, encoding='latin-1', low_memory=False)
        order_dates = pd.to_datetime(df['Order Date'], errors='coerce')

        today = pd.Timestamp.now()
        # Orders more than 6 months in future are suspicious (data entry error)
        unreasonable_dates = order_dates[order_dates > today + pd.Timedelta(days=180)]

        # Report but don't fail - future orders can be legitimate advance planning
        if len(unreasonable_dates) > 0:
            print(f"\nINFO: Found {len(unreasonable_dates)} orders > 6 months in future (may be advance planning)")

        # Only fail if dates are impossibly far in future (likely data error)
        impossible_dates = order_dates[order_dates > today + pd.Timedelta(days=365)]
        assert len(impossible_dates) == 0, \
            f"Found {len(impossible_dates)} order dates more than 1 year in the future - likely data error"

    @requires_atl
    def test_atl_date_validation_report(self):
        """Generate full validation report for debugging"""
        results = validate_csv_dates(ATL_PATH, self.ATL_DATE_COLUMNS, encoding='latin-1')
        report = print_validation_report(results)
        print(report)

        # Count total issues
        total_failures = sum(r.parse_failures for r in results.values())
        total_warnings = sum(1 for r in results.values() if r.warning_message)

        print(f"\nTotal parse failures: {total_failures}")
        print(f"Columns with warnings: {total_warnings}")


class TestDeliveriesDates:
    """Tests for DELIVERIES.csv date validation"""

    @requires_deliveries
    def test_deliveries_date_columns_parse(self):
        """Verify key date columns in deliveries parse correctly"""
        date_columns = [
            'Goods Issue Date: Date',
            'Delivery Creation Date: Date'
        ]

        results = validate_csv_dates(DELIVERIES_PATH, date_columns)

        for col_name, result in results.items():
            assert result.parse_failures == 0, \
                f"Column '{col_name}' has {result.parse_failures} parse failures"


class TestOrdersDates:
    """Tests for ORDERS.csv date validation"""

    @requires_orders
    def test_orders_date_columns_parse(self):
        """Verify key date columns in orders parse correctly"""
        date_columns = [
            'Document Date (Document Date)'
        ]

        results = validate_csv_dates(ORDERS_PATH, date_columns)

        for col_name, result in results.items():
            # Some placeholder values allowed
            assert result.parse_failures <= 10, \
                f"Column '{col_name}' has {result.parse_failures} parse failures"


class TestDateValidationUtilities:
    """Unit tests for the date validation utilities themselves"""

    def test_detect_us_date_format(self):
        """Test detection of US date format"""
        series = pd.Series(['01/15/2024', '12/25/2024', '06/04/2024'])
        fmt, rate = detect_date_format(series)
        assert 'US' in fmt or 'MM/DD' in fmt
        assert rate > 0.9

    def test_detect_eu_date_format(self):
        """Test detection of EU date format"""
        series = pd.Series(['15/01/2024', '25/12/2024', '04/06/2024'])
        fmt, rate = detect_date_format(series)
        assert 'EU' in fmt or 'DD/MM' in fmt
        assert rate > 0.9

    def test_detect_iso_date_format(self):
        """Test detection of ISO date format"""
        series = pd.Series(['2024-01-15', '2024-12-25', '2024-06-04'])
        fmt, rate = detect_date_format(series)
        assert 'ISO' in fmt or 'YYYY-MM-DD' in fmt
        assert rate > 0.9

    def test_find_ambiguous_dates(self):
        """Test finding ambiguous dates"""
        series = pd.Series(['03/04/2024', '01/05/2024', '15/01/2024'])
        ambiguous = find_ambiguous_dates(series)
        # 03/04 and 01/05 are ambiguous, 15/01 is not
        assert '03/04/2024' in ambiguous
        assert '01/05/2024' in ambiguous
        assert '15/01/2024' not in ambiguous

    def test_validate_date_column_with_failures(self):
        """Test validation with parse failures"""
        df = pd.DataFrame({
            'date_col': ['2024-01-15', 'invalid', 'tbd', '2024-03-20']
        })
        result = validate_date_column(df, 'date_col')

        assert result.total_rows == 4
        assert result.parse_failures == 2  # 'invalid' and 'tbd'
        assert 'invalid' in result.failed_samples or 'tbd' in result.failed_samples


# --- 4. ENTRY POINT ---

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
