import pandas as pd
import pytest

import dashboard_simple as app


def make_master_df(rows):
    return pd.DataFrame(rows)


def make_orders_unified(rows):
    return pd.DataFrame(rows)


def make_deliveries_unified(rows):
    return pd.DataFrame(rows)


def make_inventory_df(rows):
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def patch_loaders(monkeypatch):
    """Monkeypatch all loader functions used by load_all_data with lightweight stubs."""

    # Default minimal responses - tests will override via monkeypatch.setattr when needed
    monkeypatch.setattr(app, 'load_orders_item_lookup', lambda df: ([], pd.DataFrame([{'sales_order':'SO-1','sku':'A 1'}]), pd.DataFrame()))
    monkeypatch.setattr(app, 'load_orders_header_lookup', lambda df: ([], pd.DataFrame([{'sales_order':'SO-1','order_date':'5/15/24'}])) )
    monkeypatch.setattr(app, 'load_service_data', lambda deliveries, headers, master: ([], pd.DataFrame([{'sales_order':'SO-1','sku':'A 1','category':'RETAIL PERMANENT'}]), pd.DataFrame()))
    monkeypatch.setattr(app, 'load_backorder_data', lambda *args, **kwargs: ([], pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(app, 'load_inventory_data', lambda path, file_key=None: ([], pd.DataFrame([{'sku':'A 1','POP Actual Stock Qty':10}]), pd.DataFrame()))
    monkeypatch.setattr(app, 'load_inventory_analysis_data', lambda *args, **kwargs: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'load_vendor_pos', lambda path, file_key=None: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'load_inbound_data', lambda path, file_key=None: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'load_vendor_performance', lambda *args, **kwargs: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'load_stockout_prediction', lambda *args, **kwargs: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'load_pricing_analysis', lambda *args, **kwargs: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'load_backorder_relief', lambda *args, **kwargs: ([], pd.DataFrame()))
    monkeypatch.setattr(app, 'create_sku_description_lookup', lambda **kwargs: {})

    yield


def test_retail_filter_matches(monkeypatch):
    """When master contains RETAIL PERMANENT SKU and orders use different spacing/casing, filter should match after normalization."""

    # Prepare master with 'RETAIL PERMANENT' SKU formatted with spaces
    master_rows = [{'sku':'A 1', 'category':'RETAIL PERMANENT'}]
    orders_rows = [{'Item - SAP Model Code':'  A   1  ', 'Orders Detail - Order Document Number':'SO-1', 'Order Creation Date: Date':'5/15/24'}]
    deliveries_rows = [{'Item - SAP Model Code':'A 1', 'Deliveries Detail - Order Document Number':'SO-1', 'Delivery Creation Date: Date':'5/20/24', 'Deliveries - TOTAL Goods Issue Qty':20}]

    monkeypatch.setattr(app, 'load_master_data', lambda path, file_key='master': ([], make_master_df(master_rows), pd.DataFrame()))
    monkeypatch.setattr(app, 'load_orders_unified', lambda path, file_key='orders': ([], make_orders_unified(orders_rows)))
    monkeypatch.setattr(app, 'load_deliveries_unified', lambda path, file_key='deliveries': ([], make_deliveries_unified(deliveries_rows)))

    data = app.load_all_data(_progress_callback=None, retail_only=True)

    # Retail mode should be applied and count should equal 1
    assert data['retail_mode_applied'] is True
    assert data['retail_mode_fallbacked'] is False
    assert data['retail_sku_count'] == 1


def test_retail_filter_fallback(monkeypatch):
    """When master contains RETAIL PERMANENT SKUs that don't match order/delivery SKUs, filtering should fallback to full dataset."""

    # Master with retail sku X-100 but orders and deliveries use Y-200
    master_rows = [{'sku':'X-100', 'category':'RETAIL PERMANENT'}]
    orders_rows = [{'Item - SAP Model Code':'Y-200', 'Orders Detail - Order Document Number':'SO-1', 'Order Creation Date: Date':'5/15/24'}]
    deliveries_rows = [{'Item - SAP Model Code':'Y-200', 'Deliveries Detail - Order Document Number':'SO-1', 'Delivery Creation Date: Date':'5/20/24', 'Deliveries - TOTAL Goods Issue Qty':20}]

    monkeypatch.setattr(app, 'load_master_data', lambda path, file_key='master': ([], make_master_df(master_rows), pd.DataFrame()))
    monkeypatch.setattr(app, 'load_orders_unified', lambda path, file_key='orders': ([], make_orders_unified(orders_rows)))
    monkeypatch.setattr(app, 'load_deliveries_unified', lambda path, file_key='deliveries': ([], make_deliveries_unified(deliveries_rows)))

    data = app.load_all_data(_progress_callback=None, retail_only=True)

    # In this case the normalized matching will remove rows, so load_all_data should have fallen back
    assert data['retail_mode_applied'] is False
    assert data['retail_mode_fallbacked'] is True
    assert data['retail_sku_count'] == 1
