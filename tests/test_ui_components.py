"""
Tests for ui_components module
Tests UI helper functions and formatters
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui_components import (
    get_main_navigation,
    format_number,
    format_date
)
from datetime import datetime

class TestNavigation:
    """Test navigation helpers"""

    def test_get_main_navigation_returns_list(self):
        """Test that main navigation returns a list"""
        nav = get_main_navigation()
        assert isinstance(nav, list)
        assert len(nav) > 0

    def test_navigation_items_have_required_fields(self):
        """Test that each nav item has id, label, description"""
        nav = get_main_navigation()
        for item in nav:
            assert 'id' in item
            assert 'label' in item
            assert 'description' in item

    def test_navigation_ids_are_unique(self):
        """Test that navigation IDs are unique"""
        nav = get_main_navigation()
        ids = [item['id'] for item in nav]
        assert len(ids) == len(set(ids)), "Navigation IDs should be unique"

class TestFormatters:
    """Test formatting utility functions"""

    def test_format_number_integer(self):
        """Test integer formatting"""
        assert format_number(1000, 'integer') == '1,000'
        assert format_number(1234567, 'integer') == '1,234,567'

    def test_format_number_currency(self):
        """Test currency formatting"""
        result = format_number(1000, 'currency')
        assert '$' in result
        assert '1,000' in result

    def test_format_number_percentage(self):
        """Test percentage formatting"""
        result = format_number(95.5, 'percentage')
        assert '%' in result
        assert '95.5' in result

    def test_format_number_decimal(self):
        """Test decimal formatting"""
        result = format_number(12.5, 'decimal')
        assert '12.5' in result or '12.50' in result

    def test_format_number_none(self):
        """Test that None returns N/A"""
        assert format_number(None, 'integer') == 'N/A'

    def test_format_date_datetime(self):
        """Test date formatting with datetime object"""
        dt = datetime(2024, 5, 15)
        result = format_date(dt)
        assert '2024' in result
        assert '05' in result
        assert '15' in result

    def test_format_date_none(self):
        """Test that None returns N/A"""
        assert format_date(None) == 'N/A'
