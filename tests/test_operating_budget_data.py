"""Test Operating Budget data flow from raw data to table rendering."""
import pandas as pd
import numpy as np
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import load_master_data, load_deliveries_unified, load_inbound_data, load_inventory_data


def normalize_sku(sku_value):
    """Normalize SKU format - collapse multiple spaces to single space."""
    if pd.isna(sku_value):
        return ''
    return re.sub(r'\s+', ' ', str(sku_value).strip())


def test_operating_budget_data_flow():
    """Test end-to-end data flow for Operating Budget."""
    print("=" * 60)
    print("TEST: Operating Budget Data Flow")
    print("=" * 60)

    # 1. Load master data
    print("\n1. Loading master data...")
    logs, master_df, _ = load_master_data('Master Data.csv')
    print(f"   Master rows: {len(master_df)}")
    print(f"   Master columns: {list(master_df.columns)}")

    assert 'sku' in master_df.columns, "Master data missing 'sku' column"
    assert 'category' in master_df.columns, "Master data missing 'category' column"

    # Normalize SKU keys for consistent matching
    sku_category_map = {}
    for sku, cat in master_df.set_index('sku')['category'].to_dict().items():
        sku_category_map[normalize_sku(sku)] = cat
    print(f"   SKU-category mappings: {len(sku_category_map)}")

    categories = sorted([c for c in set(sku_category_map.values()) if pd.notna(c)])
    print(f"   Categories: {categories}")

    # 2. Load deliveries data (raw DELIVERIES.csv)
    print("\n2. Loading deliveries data...")
    logs, deliveries_df = load_deliveries_unified('DELIVERIES.csv')
    print(f"   Deliveries rows: {len(deliveries_df)}")
    print(f"   Deliveries columns: {list(deliveries_df.columns)[:10]}...")

    # 3. Test date parsing
    print("\n3. Testing date parsing...")
    date_col = None
    for col in ['Goods Issue Date: Date', 'Delivery Creation Date: Date', 'ship_date']:
        if col in deliveries_df.columns:
            date_col = col
            break
    print(f"   Using date column: {date_col}")

    if date_col:
        df_out = deliveries_df.copy()
        df_out['_date'] = pd.to_datetime(df_out[date_col], format='%m/%d/%y', errors='coerce')
        valid_dates = df_out['_date'].notna().sum()
        print(f"   Valid dates: {valid_dates} / {len(df_out)}")

        df_out = df_out[df_out['_date'].notna()]
        print(f"   Date range: {df_out['_date'].min()} to {df_out['_date'].max()}")

        # Create month column
        df_out['_month'] = df_out['_date'].dt.to_period('M').dt.to_timestamp()
        print(f"   Unique months in data: {df_out['_month'].nunique()}")

        # 4. Generate month range
        print("\n4. Generating month range...")
        today = datetime.now()
        current_month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_month = current_month_start - relativedelta(months=6)
        end_month = current_month_start + relativedelta(months=5)

        months = []
        current = start_month
        while current <= end_month:
            months.append(pd.Timestamp(current))
            current = current + relativedelta(months=1)

        print(f"   Generated months: {months[0]} to {months[-1]}")
        print(f"   Current month: {pd.Timestamp(current_month_start)}")

        # 5. Filter to month range
        print("\n5. Filtering to month range...")
        df_filtered = df_out[(df_out['_month'] >= months[0]) & (df_out['_month'] <= months[-1])]
        print(f"   Rows after filter: {len(df_filtered)}")

        # 6. Map categories
        print("\n6. Mapping categories...")
        sku_col = 'Item - SAP Model Code' if 'Item - SAP Model Code' in df_filtered.columns else 'sku'
        print(f"   Using SKU column: {sku_col}")

        if sku_col in df_filtered.columns:
            df_filtered = df_filtered.copy()
            df_filtered['_sku'] = df_filtered[sku_col].apply(normalize_sku)
            df_filtered['_category'] = df_filtered['_sku'].map(sku_category_map).fillna('Unknown')

            print(f"   Unique SKUs: {df_filtered['_sku'].nunique()}")
            print(f"   Categories found: {df_filtered['_category'].unique()}")
            print(f"   Unknown categories: {(df_filtered['_category'] == 'Unknown').sum()}")

            # 7. Get quantity
            qty_col = 'Deliveries - TOTAL Goods Issue Qty' if 'Deliveries - TOTAL Goods Issue Qty' in df_filtered.columns else 'delivered_qty'
            print(f"\n7. Using quantity column: {qty_col}")

            if qty_col in df_filtered.columns:
                df_filtered['_qty'] = pd.to_numeric(df_filtered[qty_col], errors='coerce').fillna(0)
                print(f"   Total quantity: {df_filtered['_qty'].sum():,.0f}")

                # 8. Aggregate
                print("\n8. Aggregating data...")
                outbound_agg = df_filtered.groupby(['_category', '_month']).agg({
                    '_qty': 'sum'
                }).reset_index()
                outbound_agg.columns = ['category', 'month', 'units']

                print(f"   Aggregated rows: {len(outbound_agg)}")
                print(f"   Total units: {outbound_agg['units'].sum():,.0f}")
                print(f"   Sample data:")
                print(outbound_agg.head(10).to_string())

                # 9. Test mask matching (the core issue!)
                print("\n9. Testing mask matching...")

                # Try each category with each month
                matches_found = 0
                for cat in categories[:3]:  # First 3 categories
                    for m in months[:3]:  # First 3 months
                        mask = (outbound_agg['category'] == cat) & (outbound_agg['month'] == m)
                        if mask.any():
                            val = outbound_agg.loc[mask, 'units'].sum()
                            matches_found += 1
                            print(f"   {cat} @ {m}: {val:,.0f} units")

                print(f"\n   Total matches found: {matches_found}")

                # Debug: Check specific month
                print("\n10. Debug specific month comparison...")
                test_month = months[6]  # Current month
                print(f"   Testing month: {test_month} (type: {type(test_month)})")

                data_months = outbound_agg['month'].unique()
                print(f"   Data months (first 3): {data_months[:3]}")
                print(f"   Data month type: {type(data_months[0])}")

                # Direct comparison test
                if len(data_months) > 0:
                    dm = data_months[0]
                    for gm in months:
                        if dm == gm:
                            print(f"   MATCH: data month {dm} == generated month {gm}")
                            break
                    else:
                        print(f"   NO MATCH FOUND for data month {dm}")
                        print(f"   Data month: {dm}, {type(dm)}, timestamp={dm.value}")

                        # Find closest generated month
                        for gm in months:
                            print(f"   Gen month: {gm}, {type(gm)}, timestamp={gm.value}, equal={dm == gm}")

                return True

    return False


if __name__ == "__main__":
    test_operating_budget_data_flow()
