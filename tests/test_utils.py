"""
Tests for utils module
Tests utility functions and Excel export functionality
"""

import pytest
import pandas as pd
import sys
import os
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import get_filtered_data_as_excel

class TestExcelExport:
    """Test Excel export functionality"""

    def test_get_filtered_data_as_excel_returns_bytes(self):
        """Test that Excel export returns bytes"""
        df = pd.DataFrame({
            'col1': [1, 2, 3],
            'col2': ['a', 'b', 'c']
        })

        # Function now takes dictionary: {"sheet_name": (dataframe, include_index)}
        result = get_filtered_data_as_excel({"Test Sheet": (df, False)})
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_get_filtered_data_as_excel_empty_dataframe(self):
        """Test Excel export with empty DataFrame"""
        df = pd.DataFrame()
        # Function now takes dictionary: {"sheet_name": (dataframe, include_index)}
        result = get_filtered_data_as_excel({"Empty Sheet": (df, False)})
        assert isinstance(result, bytes)

    def test_get_filtered_data_as_excel_large_dataframe(self):
        """Test Excel export with larger DataFrame"""
        df = pd.DataFrame({
            'col1': range(1000),
            'col2': ['value'] * 1000
        })

        # Function now takes dictionary: {"sheet_name": (dataframe, include_index)}
        result = get_filtered_data_as_excel({"Large Sheet": (df, False)})
        assert isinstance(result, bytes)
        assert len(result) > 0
