import pandas as pd
import os

# --- Configuration ---
DELIVERIES_FILE_PATH = "DELIVERIES.csv"
SALES_ORDER_COL = "Deliveries Detail - Order Document Number"
SKU_COL = "Item - SAP Model Code"

def find_samples():
    """
    Reads the DELIVERIES.csv file and prints a sample of valid
    Sales Order and SKU combinations.
    """
    print("--- 🕵️ Finding Sample Delivery Data ---")

    if not os.path.exists(DELIVERIES_FILE_PATH):
        print(f"❌ ERROR: '{DELIVERIES_FILE_PATH}' not found in the current directory: {os.getcwd()}")
        return

    try:
        # Read only the necessary columns for speed and memory efficiency
        df = pd.read_csv(
            DELIVERIES_FILE_PATH,
            usecols=[SALES_ORDER_COL, SKU_COL],
            dtype=str,
            low_memory=False
        ).dropna().drop_duplicates()
        print(f"✅ Successfully read and found {len(df):,} unique combinations in {DELIVERIES_FILE_PATH}.")
    except Exception as e:
        print(f"❌ ERROR: Could not read the file. Please check if the columns '{SALES_ORDER_COL}' and '{SKU_COL}' exist. Error: {e}")
        return

    print("\nHere are 10 sample Sales Order and SKU combinations from your file:")
    print("You can use any of these in the `debug_service_level.py` script.")
    print("-" * 80)
    print(df.head(10).to_string(index=False))
    print("-" * 80)

if __name__ == "__main__":
    find_samples()