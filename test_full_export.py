"""
Test the full warehouse scrap list export process end-to-end
"""
import pandas as pd
import sys
import os
from io import BytesIO

# Fix encoding for Windows CMD
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dashboard_simple import load_all_data
from pages.inventory_page import prepare_warehouse_scrap_list, create_excel_export

def test_full_export():
    """Test the complete export process"""

    print("=" * 80)
    print("FULL WAREHOUSE SCRAP EXPORT TEST")
    print("=" * 80)

    # Step 1: Load data
    print("\n[1] Loading data...")
    data = load_all_data()
    inventory_data = data['inventory_analysis']
    print(f"✓ Loaded {len(inventory_data)} inventory records")

    # Step 2: Prepare warehouse scrap list
    print("\n[2] Preparing warehouse scrap list...")
    scrap_list = prepare_warehouse_scrap_list(
        inventory_data=inventory_data,
        scrap_days_threshold=730,
        currency='USD'
    )
    print(f"✓ Generated scrap list with {len(scrap_list)} rows and {len(scrap_list.columns)} columns")
    print(f"  Columns: {list(scrap_list.columns)}")

    if scrap_list.empty:
        print("✗ ERROR: Scrap list is empty!")
        return False

    # Step 3: Create Excel export
    print("\n[3] Creating Excel export...")
    try:
        excel_file = create_excel_export(
            data=scrap_list,
            section_name="Warehouse Scrap List",
            currency='USD'
        )
        print(f"✓ Excel file created, size: {excel_file.getbuffer().nbytes} bytes")
    except Exception as e:
        print(f"✗ ERROR creating Excel: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Step 4: Read back the Excel file to verify contents
    print("\n[4] Verifying Excel file contents...")
    try:
        excel_file.seek(0)
        df_readback = pd.read_excel(excel_file, sheet_name=0)

        print(f"✓ Successfully read back Excel file")
        print(f"  Rows: {len(df_readback)}")
        print(f"  Columns: {len(df_readback.columns)}")
        print(f"  Column names: {list(df_readback.columns)}")

        # Count non-empty cells
        total_cells = df_readback.shape[0] * df_readback.shape[1]
        non_empty_cells = df_readback.notna().sum().sum()
        empty_cells = total_cells - non_empty_cells

        print(f"\n  Total cells: {total_cells:,}")
        print(f"  Non-empty cells: {non_empty_cells:,}")
        print(f"  Empty cells: {empty_cells:,}")
        print(f"  Fill rate: {(non_empty_cells/total_cells*100):.1f}%")

        # Show first few rows
        print(f"\n[5] Sample data (first 3 rows):")
        print(df_readback.head(3).to_string())

        # Check key columns for data
        print(f"\n[6] Checking key columns for data:")
        key_columns = ['Material', 'Free Qt', 'Conservative Scrap Qty', 'Medium Scrap Qty', 'Aggressive Scrap Qty']
        for col in key_columns:
            if col in df_readback.columns:
                non_zero = (df_readback[col] != 0).sum() if df_readback[col].dtype in ['int64', 'float64'] else df_readback[col].notna().sum()
                print(f"  {col}: {non_zero} non-zero/non-null values")
            else:
                print(f"  {col}: COLUMN NOT FOUND!")

        # Save to disk for manual inspection
        output_path = "test_warehouse_scrap_export.xlsx"
        with open(output_path, 'wb') as f:
            excel_file.seek(0)
            f.write(excel_file.read())
        print(f"\n✓ Test file saved to: {output_path}")

        if len(df_readback) == 0:
            print("\n✗ PROBLEM: Excel file has 0 rows!")
            return False

        if non_empty_cells == 0:
            print("\n✗ PROBLEM: Excel file has all empty cells!")
            return False

        print("\n" + "=" * 80)
        print("✓ EXPORT TEST PASSED - File contains data")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ ERROR reading Excel file: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_full_export()
    sys.exit(0 if success else 1)
