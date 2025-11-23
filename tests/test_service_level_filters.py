"""
Tests for service_level_page filters
"""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.service_level_page import get_service_level_filters, apply_service_filters


def make_sample_service_df():
    return pd.DataFrame([
        {"customer_name": "A", "ship_month": "Jan", "ship_month_num": 1, "ship_year": 2023, "on_time": 1, "units_issued": 10, "days_to_deliver": 3},
        {"customer_name": "B", "ship_month": "Feb", "ship_month_num": 2, "ship_year": 2024, "on_time": 0, "units_issued": 5, "days_to_deliver": 8},
        {"customer_name": "A", "ship_month": "Mar", "ship_month_num": 3, "ship_year": 2024, "on_time": 1, "units_issued": 2, "days_to_deliver": 6},
    ])


def test_get_service_level_filters_includes_year():
    df = make_sample_service_df()
    filters = get_service_level_filters(df)

    # There should be a Filter entry with label 'Year'
    labels = [f.get('label') for f in filters]
    assert 'Year' in labels


def test_apply_service_filters_filters_by_year():
    df = make_sample_service_df()

    # Apply filter to only include 2024
    fv = {'sl_year_filter': 2024}
    filtered = apply_service_filters(df, fv)
    assert not filtered.empty
    assert set(filtered['ship_year'].unique()) == {2024}
