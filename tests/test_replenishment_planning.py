import pandas as pd
import pytest

from replenishment_planning import generate_replenishment_plan


def make_minimal_inputs():
    # Master data with a retail permanent SKU (so demand included)
    master_df = pd.DataFrame({'sku': ['SKU1'], 'category': ['RETAIL PERMANENT']})

    # Inventory: some on hand and in-transit
    inventory_df = pd.DataFrame({
        'sku': ['SKU1'],
        'on_hand_qty': [10],
        'in_transit_qty': [5],
        'last_purchase_price': [2.5]
    })

    # Demand forecast: small daily demand
    demand_df = pd.DataFrame({
        'sku': ['SKU1'],
        'primary_forecast_daily': [1.0],
        'demand_std': [0.2]
    })

    # No backorders
    backorder_df = pd.DataFrame({'sku': [], 'backorder_qty': []})

    # Domestic PO: empty
    domestic_po_df = pd.DataFrame({'sku': [], 'open_qty': []})

    # International PO: empty
    international_po_df = pd.DataFrame({'sku': [], 'open_qty': []})

    return inventory_df, demand_df, backorder_df, domestic_po_df, international_po_df, master_df


def test_generate_replenishment_plan_runs_no_error():
    inv, demand, bo, dom_po, intl_po, master = make_minimal_inputs()

    plan_df = generate_replenishment_plan(
        inventory_df=inv,
        demand_forecast_df=demand,
        backorder_df=bo,
        domestic_po_df=dom_po,
        international_po_df=intl_po,
        master_df=master,
        service_level=0.95,
        default_lead_time_days=73,
        review_period_days=14
    )

    # The function should return a DataFrame (possibly empty)
    assert isinstance(plan_df, pd.DataFrame)

    # Columns should include expected keys if non-empty
    if not plan_df.empty:
        for col in ['sku', 'reorder_point', 'in_transit_qty', 'open_po_qty', 'suggested_order_qty']:
            assert col in plan_df.columns
