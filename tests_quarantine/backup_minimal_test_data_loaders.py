"""Minimal tests for data_loader (fresh clean copy)."""

import pytest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import (
    load_master_data,
    load_orders_item_lookup_legacy as load_orders_item_lookup,
    load_orders_header_lookup_legacy as load_orders_header_lookup,
)


@pytest.fixture(autouse=True)
def local_mock_read_csv(monkeypatch, mock_master_data_csv, mock_orders_csv, mock_deliveries_csv, mock_inventory_csv):
    mocks = {
        'master_data.csv': mock_master_data_csv[1],
        'orders.csv': mock_orders_csv[1],
        'deliveries.csv': mock_deliveries_csv[1],
        'inventory.csv': mock_inventory_csv[1],
    }

    original = pd.read_csv

    def fake(path, *args, **kwargs):
        if isinstance(path, str) and os.path.basename(path) in mocks:
            mocks[os.path.basename(path)].seek(0)
            return original(mocks[os.path.basename(path)], *args, **kwargs)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(pd, 'read_csv', fake)
    yield


def test_master_data_loads_non_empty():
    logs, df, errs = load_master_data('master_data.csv')
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_orders_item_lookup_basic():
    logs, df, errs = load_orders_item_lookup('orders.csv')
    assert 'sales_order' in df.columns
    assert 'sku' in df.columns


def test_orders_header_lookup_basic():
    logs, df = load_orders_header_lookup('orders.csv')
    assert 'sales_order' in df.columns
    assert 'customer_name' in df.columns
