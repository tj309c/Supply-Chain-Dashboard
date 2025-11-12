import pandas as pd
import os
import numpy as np

# --- Configuration ---
INVENTORY_FILE_PATH = "INVENTORY.csv"
REQUIRED_COLUMNS = {
    "Material Number": "sku",
    "POP Actual Stock Qty": "on_hand_qty"
}

def validate_inventory_file(file_path):
    """
    Runs a series of checks on the inventory CSV file to diagnose potential issues.
    """
    print("--- 🕵️ Inventory File Validator ---")
    print(f"Analyzing file: {file_path}\n")

    # 1. Check if the file exists
    if not os.path.isfile(file_path):
        print(f"❌ ERROR: File not found at '{os.path.abspath(file_path)}'.")
        print("Please ensure the INVENTORY.csv file is in the same directory as the script.")
        return

    print(f"✅ SUCCESS: File found at '{os.path.abspath(file_path)}'.")

    # 2. Try to read the file and check for required columns
    try:
        df_raw = pd.read_csv(file_path, low_memory=False, dtype=str) # Read all as string first
        print(f"✅ SUCCESS: Successfully read {len(df_raw)} rows from the CSV.\n")
    except Exception as e:
        print(f"❌ ERROR: Failed to read the CSV file. Error: {e}")
        print("The file might be corrupted or not a valid CSV.")
        return

    # 3. Check for required columns
    print("--- Column Check ---")
    missing_cols = [col for col in REQUIRED_COLUMNS.keys() if col not in df_raw.columns]
    if missing_cols:
        print(f"❌ ERROR: The file is missing the following required columns: {', '.join(missing_cols)}")
        print(f"Available columns are: {df_raw.columns.tolist()}")
        return
    print("✅ SUCCESS: All required columns are present.\n")

    # 4. Analyze the 'POP Actual Stock Qty' column
    print("--- Stock Quantity (on_hand_qty) Analysis ---")
    stock_col = "POP Actual Stock Qty"
    # --- FIX: Remove commas before attempting numeric conversion for the check ---
    df_raw['on_hand_numeric'] = pd.to_numeric(df_raw[stock_col].str.replace(',', '', regex=False), errors='coerce')
    
    null_stock_count = df_raw[stock_col].isnull().sum()
    non_numeric_count = df_raw['on_hand_numeric'].isnull().sum() - null_stock_count

    if null_stock_count > 0:
        print(f"🟡 WARNING: Found {null_stock_count} rows with blank/empty stock quantities.")
    if non_numeric_count > 0:
        print(f"🟡 WARNING: Found {non_numeric_count} rows where stock quantity is not a valid number (e.g., contains text).")
        print("   These will be treated as 0 stock.")
        print("   Sample non-numeric values:")
        print(df_raw[df_raw['on_hand_numeric'].isnull() & df_raw[stock_col].notnull()][stock_col].head())
    
    if null_stock_count == 0 and non_numeric_count == 0:
        print("✅ SUCCESS: All stock quantities are valid numbers or blanks.\n")

    # 5. Analyze the 'Material Number' (SKU) column
    print("--- SKU (Material Number) Analysis ---")
    sku_col = "Material Number"
    null_sku_count = df_raw[sku_col].isnull().sum()
    if null_sku_count > 0:
        print(f"❌ ERROR: Found {null_sku_count} rows with a blank SKU. These rows will be dropped.")
    else:
        print("✅ SUCCESS: No blank SKUs found.\n")

    # --- Data Processing Simulation (mirrors data_loader.py) ---
    df = df_raw[list(REQUIRED_COLUMNS.keys())].rename(columns=REQUIRED_COLUMNS)
    df['sku'] = df['sku'].astype(str).str.strip()
    # --- FIX: Replicate the comma removal logic from the main data loader ---
    df['on_hand_qty'] = pd.to_numeric(df['on_hand_qty'].astype(str).str.replace(',', '', regex=False), errors='coerce').fillna(0)

    # 6. Demonstrate Aggregation Logic
    print("--- Aggregation Logic Example ---")
    sku_counts = df['sku'].value_counts()
    duplicated_skus = sku_counts[sku_counts > 1]

    if not duplicated_skus.empty:
        sample_sku = duplicated_skus.index[0]
        print(f"SKU '{sample_sku}' appears {duplicated_skus.iloc[0]} times (e.g., in different locations).")
        print("The script will sum these quantities.")
        
        sample_df = df[df['sku'] == sample_sku]
        print("\nOriginal rows in INVENTORY.csv:")
        print(sample_df)
        
        total_sum = sample_df['on_hand_qty'].sum()
        print(f"\nCalculated Total for SKU '{sample_sku}': {total_sum:,.0f}\n")
    else:
        print("INFO: No duplicated SKUs found to demonstrate aggregation. Each SKU appears only once.\n")

    # 7. Final Summary
    print("--- Final Processed Summary ---")
    if df.empty:
        print("❌ ERROR: The processed dataframe is empty. No data to display.")
    else:
        # This is the exact logic from data_loader.py
        processed_df = df.groupby('sku', as_index=False)['on_hand_qty'].sum()
        
        total_skus = processed_df['sku'].nunique()
        total_stock = processed_df['on_hand_qty'].sum()

        print(f"Total Unique SKUs Found: {total_skus:,}")
        print(f"Total On-Hand Units Calculated: {total_stock:,.0f}")

        if total_stock == 0:
            print("\n🟡 ADVICE: The total calculated on-hand stock is 0.")
            print("This is the most likely reason the report is empty. Please check the 'POP Actual Stock Qty' column in your file.")
        else:
            print("\n✅ SUCCESS: Inventory data seems valid and contains stock.")
            print("If the report is still empty, the issue is likely with the 'Category' filter in the dashboard.")


if __name__ == "__main__":
    # Check if the INVENTORY.csv file is in the current directory
    if os.path.exists(INVENTORY_FILE_PATH):
        validate_inventory_file(INVENTORY_FILE_PATH)
    else:
        print(f"--- 🕵️ Inventory File Validator ---")
        print(f"❌ ERROR: '{INVENTORY_FILE_PATH}' not found in the current directory.")
        print(f"Please place this script in the same folder as your data files: {os.getcwd()}")