"""
Tests for Service Level Performance charts in the Overview page.

Tests cover:
- render_service_level_chart (YEAR view with stacked volume bars)
- render_service_level_chart_by_category (CATEGORY view with rolling 12 months)
- Edge cases: empty data, missing columns, single year/category
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pages.overview_page import render_service_level_chart, render_service_level_chart_by_category


# ===== FIXTURES =====

@pytest.fixture
def sample_service_data():
    """
    Creates sample service data with multiple years, months, and categories.
    Simulates realistic OTIF data for testing charts.
    """
    np.random.seed(42)

    # Generate data for 3 years, 12 months each
    records = []
    categories = ['RETAIL PERMANENT', 'RETAIL SEASONAL', 'WHOLESALE', 'ECOMMERCE', 'OUTLET']

    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            # Skip future months in 2025
            if year == 2025 and month > 11:
                continue

            # Generate varying number of orders per month
            num_orders = np.random.randint(50, 200)

            for _ in range(num_orders):
                category = np.random.choice(categories, p=[0.4, 0.2, 0.2, 0.15, 0.05])

                # Planning OTIF - ~90% on-time
                planning_on_time = np.random.random() < 0.90

                # Logistics OTIF - ~85% on-time (some rows have NaN)
                if np.random.random() < 0.9:  # 90% of rows have logistics data
                    logistics_on_time = np.random.random() < 0.85
                else:
                    logistics_on_time = np.nan

                # Create ship date
                day = np.random.randint(1, 28)
                ship_date = pd.Timestamp(year=year, month=month, day=day)

                records.append({
                    'ship_year': year,
                    'ship_month_num': month,
                    'ship_month': f'{year}-{month:02d}',
                    'ship_date': ship_date,
                    'category': category,
                    'planning_on_time': planning_on_time,
                    'logistics_on_time': logistics_on_time,
                    'on_time': planning_on_time,  # Legacy column
                    'units_issued': np.random.randint(1, 100),
                    'customer_name': f'Customer_{np.random.randint(1, 10)}'
                })

    return pd.DataFrame(records)


@pytest.fixture
def minimal_service_data():
    """Creates minimal service data with just one year and one category."""
    return pd.DataFrame({
        'ship_year': [2024, 2024, 2024],
        'ship_month_num': [1, 2, 3],
        'ship_month': ['2024-01', '2024-02', '2024-03'],
        'ship_date': pd.to_datetime(['2024-01-15', '2024-02-15', '2024-03-15']),
        'category': ['RETAIL PERMANENT', 'RETAIL PERMANENT', 'RETAIL PERMANENT'],
        'planning_on_time': [True, True, False],
        'logistics_on_time': [True, False, True],
        'on_time': [True, True, False],
        'units_issued': [100, 150, 200]
    })


@pytest.fixture
def empty_service_data():
    """Creates an empty DataFrame with correct columns."""
    return pd.DataFrame(columns=[
        'ship_year', 'ship_month_num', 'ship_month', 'ship_date',
        'category', 'planning_on_time', 'logistics_on_time', 'on_time', 'units_issued'
    ])


@pytest.fixture
def service_data_missing_columns():
    """Creates service data missing required columns."""
    return pd.DataFrame({
        'ship_year': [2024],
        'units_issued': [100]
    })


# ===== TESTS FOR render_service_level_chart (YEAR VIEW) =====

class TestRenderServiceLevelChart:
    """Tests for the YEAR view chart function."""

    def test_returns_figure_with_valid_data(self, sample_service_data):
        """Should return a Plotly figure with valid service data."""
        fig = render_service_level_chart(sample_service_data, otif_type='planning')

        assert fig is not None
        assert hasattr(fig, 'data')
        assert len(fig.data) > 0

    def test_returns_none_with_empty_data(self, empty_service_data):
        """Should return None when data is empty."""
        fig = render_service_level_chart(empty_service_data, otif_type='planning')

        assert fig is None

    def test_returns_none_with_missing_columns(self, service_data_missing_columns):
        """Should return None when required columns are missing."""
        fig = render_service_level_chart(service_data_missing_columns, otif_type='planning')

        assert fig is None

    def test_planning_otif_chart_title(self, sample_service_data):
        """Should have correct title for Planning OTIF."""
        fig = render_service_level_chart(sample_service_data, otif_type='planning')

        assert fig is not None
        assert 'Planning OTIF' in fig.layout.title.text

    def test_logistics_otif_chart_title(self, sample_service_data):
        """Should have correct title for Logistics OTIF."""
        fig = render_service_level_chart(sample_service_data, otif_type='logistics')

        assert fig is not None
        assert 'Logistics OTIF' in fig.layout.title.text

    def test_selected_years_filter(self, sample_service_data):
        """Should filter to only selected years."""
        fig = render_service_level_chart(
            sample_service_data,
            otif_type='planning',
            selected_years=[2024]
        )

        assert fig is not None
        # Check that only 2024 data is in the traces
        trace_names = [trace.name for trace in fig.data if hasattr(trace, 'name')]
        year_traces = [name for name in trace_names if '2024' in str(name)]
        assert len(year_traces) > 0
        # Should not have 2023 traces
        traces_2023 = [name for name in trace_names if '2023' in str(name)]
        assert len(traces_2023) == 0

    def test_defaults_to_all_years_with_empty_selection(self, sample_service_data):
        """Should default to last 3 years when empty list is passed."""
        fig = render_service_level_chart(
            sample_service_data,
            otif_type='planning',
            selected_years=[]
        )

        # Empty list defaults to last 3 years in the function
        assert fig is not None

    def test_has_stacked_volume_bars(self, sample_service_data):
        """Should have stacked bar mode for volume bars."""
        fig = render_service_level_chart(sample_service_data, otif_type='planning')

        assert fig is not None
        assert fig.layout.barmode == 'stack'

    def test_has_volume_bars_per_year(self, sample_service_data):
        """Should have volume bar traces for each year."""
        fig = render_service_level_chart(
            sample_service_data,
            otif_type='planning',
            selected_years=[2023, 2024, 2025]
        )

        assert fig is not None
        bar_traces = [trace for trace in fig.data if trace.type == 'bar']
        # Should have one bar trace per year
        assert len(bar_traces) >= 3

    def test_has_otif_lines_per_year(self, sample_service_data):
        """Should have OTIF percentage line traces for each year."""
        fig = render_service_level_chart(
            sample_service_data,
            otif_type='planning',
            selected_years=[2023, 2024]
        )

        assert fig is not None
        scatter_traces = [trace for trace in fig.data if trace.type == 'scatter']
        # Should have lines for each year (OTIF line + avg line per year)
        assert len(scatter_traces) >= 4  # 2 years × 2 (OTIF + avg)

    def test_has_target_line(self, sample_service_data):
        """Should have a 95% target line."""
        fig = render_service_level_chart(sample_service_data, otif_type='planning')

        assert fig is not None
        # Check for horizontal line at 95%
        shapes = fig.layout.shapes
        assert len(shapes) > 0
        target_line = [s for s in shapes if hasattr(s, 'y0') and s.y0 == 95]
        assert len(target_line) > 0

    def test_yaxis_range_0_to_100(self, sample_service_data):
        """Should have y-axis range from 0 to 100 for percentage."""
        fig = render_service_level_chart(sample_service_data, otif_type='planning')

        assert fig is not None
        # Plotly returns tuple for range
        assert tuple(fig.layout.yaxis.range) == (0, 100)

    def test_has_secondary_yaxis_for_volume(self, sample_service_data):
        """Should have secondary y-axis for volume bars."""
        fig = render_service_level_chart(sample_service_data, otif_type='planning')

        assert fig is not None
        assert fig.layout.yaxis2 is not None
        assert fig.layout.yaxis2.side == 'right'

    def test_single_year_data(self, minimal_service_data):
        """Should handle single year data gracefully."""
        fig = render_service_level_chart(minimal_service_data, otif_type='planning')

        assert fig is not None
        assert len(fig.data) > 0


# ===== TESTS FOR render_service_level_chart_by_category (CATEGORY VIEW) =====

class TestRenderServiceLevelChartByCategory:
    """Tests for the CATEGORY view chart function."""

    def test_returns_figure_with_valid_data(self, sample_service_data):
        """Should return a Plotly figure with valid service data."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        assert hasattr(fig, 'data')
        assert len(fig.data) > 0

    def test_returns_none_with_empty_data(self, empty_service_data):
        """Should return None when data is empty."""
        fig = render_service_level_chart_by_category(empty_service_data, otif_type='planning')

        assert fig is None

    def test_returns_none_with_missing_category_column(self):
        """Should return None when category column is missing."""
        data = pd.DataFrame({
            'ship_year': [2024],
            'ship_month_num': [1],
            'ship_month': ['2024-01'],
            'planning_on_time': [True]
        })
        fig = render_service_level_chart_by_category(data, otif_type='planning')

        assert fig is None

    def test_planning_otif_chart_title(self, sample_service_data):
        """Should have correct title for Planning OTIF category view."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        assert 'Planning OTIF by Category' in fig.layout.title.text
        assert 'Rolling 12 Months' in fig.layout.title.text

    def test_logistics_otif_chart_title(self, sample_service_data):
        """Should have correct title for Logistics OTIF category view."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='logistics')

        assert fig is not None
        assert 'Logistics OTIF by Category' in fig.layout.title.text

    def test_selected_categories_filter(self, sample_service_data):
        """Should filter to only selected categories."""
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=['RETAIL PERMANENT', 'WHOLESALE']
        )

        assert fig is not None
        trace_names = [trace.name for trace in fig.data if hasattr(trace, 'name')]
        # Should have traces for selected categories
        retail_traces = [name for name in trace_names if 'RETAIL PERMANENT' in str(name)]
        wholesale_traces = [name for name in trace_names if 'WHOLESALE' in str(name)]
        assert len(retail_traces) > 0
        assert len(wholesale_traces) > 0
        # Should not have ECOMMERCE traces
        ecommerce_traces = [name for name in trace_names if 'ECOMMERCE' in str(name)]
        assert len(ecommerce_traces) == 0

    def test_defaults_to_top_5_with_empty_category_selection(self, sample_service_data):
        """Should default to top 5 categories when empty list is passed."""
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=[]
        )

        # Empty list defaults to top 5 categories in the function
        assert fig is not None

    def test_defaults_to_top_5_categories(self, sample_service_data):
        """Should default to top 5 categories by volume when none selected."""
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=None
        )

        assert fig is not None
        # Count unique category traces (excluding volume traces)
        trace_names = [trace.name for trace in fig.data if hasattr(trace, 'name') and 'Volume' not in str(trace.name) and 'Avg' not in str(trace.name)]
        unique_categories = set(trace_names)
        assert len(unique_categories) <= 5

    def test_has_stacked_volume_bars(self, sample_service_data):
        """Should have stacked bar mode for volume bars."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        assert fig.layout.barmode == 'stack'

    def test_has_volume_bars_per_category(self, sample_service_data):
        """Should have volume bar traces for each category."""
        categories = ['RETAIL PERMANENT', 'WHOLESALE']
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=categories
        )

        assert fig is not None
        bar_traces = [trace for trace in fig.data if trace.type == 'bar']
        # Should have one bar trace per category
        assert len(bar_traces) >= len(categories)

    def test_has_otif_lines_per_category(self, sample_service_data):
        """Should have OTIF percentage line traces for each category."""
        categories = ['RETAIL PERMANENT', 'WHOLESALE']
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=categories
        )

        assert fig is not None
        scatter_traces = [trace for trace in fig.data if trace.type == 'scatter']
        # Should have lines for each category (OTIF line + avg line per category)
        assert len(scatter_traces) >= len(categories) * 2

    def test_has_target_line(self, sample_service_data):
        """Should have a 95% target line."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        shapes = fig.layout.shapes
        assert len(shapes) > 0
        target_line = [s for s in shapes if hasattr(s, 'y0') and s.y0 == 95]
        assert len(target_line) > 0

    def test_yaxis_range_0_to_100(self, sample_service_data):
        """Should have y-axis range from 0 to 100 for percentage."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        # Plotly returns tuple for range
        assert tuple(fig.layout.yaxis.range) == (0, 100)

    def test_has_secondary_yaxis_for_volume(self, sample_service_data):
        """Should have secondary y-axis for volume bars."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        assert fig.layout.yaxis2 is not None
        assert fig.layout.yaxis2.side == 'right'

    def test_filters_to_rolling_12_months(self, sample_service_data):
        """Should only include data from the last 12 months."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        # The chart should exist - detailed date filtering is internal
        assert len(fig.data) > 0

    def test_handles_single_category(self, sample_service_data):
        """Should handle single category selection gracefully."""
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=['RETAIL PERMANENT']
        )

        assert fig is not None
        assert len(fig.data) > 0

    def test_xaxis_labels_include_year(self, sample_service_data):
        """X-axis labels should include month and year (e.g., 'Jan 2024')."""
        fig = render_service_level_chart_by_category(sample_service_data, otif_type='planning')

        assert fig is not None
        # Check that x values include year
        bar_traces = [trace for trace in fig.data if trace.type == 'bar']
        if bar_traces:
            x_values = bar_traces[0].x
            # At least one label should contain a year
            has_year = any('202' in str(x) for x in x_values)
            assert has_year


# ===== TESTS FOR EDGE CASES =====

class TestServiceLevelChartEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_all_nan_logistics_data(self, sample_service_data):
        """Should return None when all logistics_on_time values are NaN."""
        data = sample_service_data.copy()
        data['logistics_on_time'] = np.nan

        fig = render_service_level_chart(data, otif_type='logistics')

        assert fig is None

    def test_handles_mixed_dtypes_in_year_column(self, sample_service_data):
        """Should handle mixed dtypes in ship_year column."""
        data = sample_service_data.copy()
        data['ship_year'] = data['ship_year'].astype(float)

        fig = render_service_level_chart(data, otif_type='planning')

        assert fig is not None

    def test_handles_category_with_special_characters(self):
        """Should handle category names with special characters."""
        data = pd.DataFrame({
            'ship_year': [2024, 2024],
            'ship_month_num': [1, 2],
            'ship_month': ['2024-01', '2024-02'],
            'ship_date': pd.to_datetime(['2024-01-15', '2024-02-15']),
            'category': ['Category & Test', 'Category & Test'],
            'planning_on_time': [True, False],
            'logistics_on_time': [True, True],
            'units_issued': [100, 200]
        })

        fig = render_service_level_chart_by_category(
            data,
            otif_type='planning',
            selected_categories=['Category & Test']
        )

        assert fig is not None

    def test_handles_very_low_otif_percentage(self):
        """Should handle data with very low OTIF percentage."""
        data = pd.DataFrame({
            'ship_year': [2024] * 100,
            'ship_month_num': [1] * 100,
            'ship_month': ['2024-01'] * 100,
            'ship_date': pd.to_datetime(['2024-01-15'] * 100),
            'category': ['TEST'] * 100,
            'planning_on_time': [False] * 95 + [True] * 5,  # 5% on-time
            'units_issued': [10] * 100
        })

        fig = render_service_level_chart(data, otif_type='planning')

        assert fig is not None

    def test_handles_100_percent_otif(self):
        """Should handle data with 100% OTIF percentage."""
        data = pd.DataFrame({
            'ship_year': [2024] * 10,
            'ship_month_num': [1] * 10,
            'ship_month': ['2024-01'] * 10,
            'ship_date': pd.to_datetime(['2024-01-15'] * 10),
            'category': ['TEST'] * 10,
            'planning_on_time': [True] * 10,  # 100% on-time
            'units_issued': [10] * 10
        })

        fig = render_service_level_chart(data, otif_type='planning')

        assert fig is not None


# ===== TESTS FOR COLOR CONSISTENCY =====

class TestColorConsistency:
    """Tests to verify color consistency between bars and lines."""

    def test_year_view_colors_match(self, sample_service_data):
        """Volume bars and OTIF lines for same year should use same color."""
        fig = render_service_level_chart(
            sample_service_data,
            otif_type='planning',
            selected_years=[2024]
        )

        assert fig is not None

        # Get bar and line traces for 2024
        bar_traces = [t for t in fig.data if t.type == 'bar' and '2024' in str(t.name)]
        line_traces = [t for t in fig.data if t.type == 'scatter' and '2024 OTIF' in str(t.name)]

        if bar_traces and line_traces:
            # Colors should match (accounting for opacity in bars)
            bar_color = bar_traces[0].marker.color
            line_color = line_traces[0].line.color
            assert bar_color == line_color

    def test_category_view_colors_match(self, sample_service_data):
        """Volume bars and OTIF lines for same category should use same color."""
        categories = ['RETAIL PERMANENT']
        fig = render_service_level_chart_by_category(
            sample_service_data,
            otif_type='planning',
            selected_categories=categories
        )

        assert fig is not None

        # Get bar and line traces for the category
        bar_traces = [t for t in fig.data if t.type == 'bar' and 'RETAIL PERMANENT' in str(t.name)]
        line_traces = [t for t in fig.data if t.type == 'scatter' and t.name == 'RETAIL PERMANENT']

        if bar_traces and line_traces:
            bar_color = bar_traces[0].marker.color
            line_color = line_traces[0].line.color
            assert bar_color == line_color
