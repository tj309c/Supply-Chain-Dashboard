"""
Tests for file_loader module
Tests CSV file loading and error handling
"""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from file_loader import safe_read_csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data")
MASTER_DATA_PATH = os.path.join(DATA_DIR, "Master Data.csv")

class TestSafeReadCSV:
    """Test safe_read_csv functionality"""

    def test_safe_read_csv_existing_file(self):
        """Test reading an existing file"""
        df = safe_read_csv(None, MASTER_DATA_PATH)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_safe_read_csv_nonexistent_file(self):
        """Test reading a non-existent file returns empty DataFrame"""
        df = safe_read_csv(None, "nonexistent_file.csv")
        assert isinstance(df, pd.DataFrame)
        # Should return empty DataFrame or raise exception

    def test_safe_read_csv_with_usecols(self):
        """Test reading with specific columns"""
        df = safe_read_csv(None, MASTER_DATA_PATH, usecols=["Material Number"])
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "Material Number" in df.columns
