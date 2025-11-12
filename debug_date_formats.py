import pandas as pd
import os
from collections import defaultdict

# --- Configuration ---
FILES_AND_COLUMNS = {
    "ORDERS.csv": "Order Creation Date: Date",
    "DELIVERIES.csv": "Delivery Creation Date: Date"
}

# A list of common date formats to test against.
COMMON_DATE_FORMATS = [
    '%m/%d/%y',        # 05/15/24
    '%m/%d/%Y',        # 05/15/2024
    '%Y-%m-%d',        # 2024-05-15
    '%d-%b-%y',        # 15-May-24
    '%Y%m%d',          # 20240515
    '%m-%d-%Y',        # 05-15-2024
    '%d/%m/%Y',        # 15/05/2024
    '%d/%m/%y',        # 15/05/24
    '%b %d, %Y',       # May 15, 2024
    # Formats with time components
    '%Y-%m-%d %H:%M:%S', # 2024-05-15 14:30:00
    '%m/%d/%Y %H:%M',    # 05/15/2024 14:30
]

def print_header(title):
    """Prints a formatted header to the console."""
    bar = "="*80
    print(f"\n{bar}\n🔬 {title.upper()}\n{bar}")

def analyze_date_column(file_path, column_name):
    """
    Analyzes a specific date column in a file to identify all present date formats.
    """
    print_header(f"Analyzing '{column_name}' in '{file_path}'")

    # 1. Check if the file exists
    if not os.path.isfile(file_path):
        print(f"❌ ERROR: File not found at '{os.path.abspath(file_path)}'.")
        return

    # 2. Load the specific column as a string to prevent auto-parsing
    try:
        df = pd.read_csv(file_path, usecols=[column_name], dtype=str, low_memory=False)
        # Drop rows where the date is missing to focus on actual values
        unique_dates = df[column_name].dropna().unique()
        print(f"✅ Found {len(unique_dates):,} unique non-empty date strings to analyze.")
    except ValueError:
        print(f"❌ ERROR: Column '{column_name}' not found in '{file_path}'.")
        return
    except Exception as e:
        print(f"❌ ERROR: Failed to read the CSV file. Error: {e}")
        return

    if len(unique_dates) == 0:
        print("🟡 INFO: No date values found in this column.")
        return

    # 3. Attempt to parse each unique date with our list of formats
    format_counts = defaultdict(int)
    unparseable_dates = set()

    for date_str in unique_dates:
        parsed = False
        for fmt in COMMON_DATE_FORMATS:
            try:
                pd.to_datetime(date_str, format=fmt)
                format_counts[fmt] += 1
                parsed = True
                break # Move to the next date string once a format works
            except (ValueError, TypeError):
                continue # Try the next format
        
        if not parsed:
            unparseable_dates.add(date_str)

    # 4. Report the findings
    print("\n--- Format Analysis Results ---")
    if not format_counts:
        print("❌ No unique date strings could be parsed by any of the common formats.")
    else:
        print("Detected the following date formats in your data:")
        # Sort by the number of unique dates matched, descending
        sorted_formats = sorted(format_counts.items(), key=lambda item: item[1], reverse=True)
        for fmt, count in sorted_formats:
            percentage = (count / len(unique_dates)) * 100
            print(f"  - Format: {fmt:<18} | Matched {count:>5,} unique date strings ({percentage:.1f}%)")

    if unparseable_dates:
        print("\n" + "-"*80)
        print(f"⚠️ WARNING: Found {len(unparseable_dates)} unique date strings that could NOT be parsed with any known format.")
        print("   These are the values causing the 'Could not infer format' warning and slowing down the data loading.")
        print("   Sample of unparseable dates:")
        for i, bad_date in enumerate(list(unparseable_dates)[:10]):
            print(f"     - '{bad_date}'")
        if len(unparseable_dates) > 10:
            print("     - ... (and more)")
        print("-" * 80)
    else:
        print("\n✅ SUCCESS: All unique date strings were successfully parsed by the formats listed above.")

    # 5. Provide a recommendation
    print("\n--- Recommendation ---")
    if not unparseable_dates and len(format_counts) == 1:
        recommended_format = list(format_counts.keys())[0]
        print(f"✅ All dates use a single format. For maximum performance, update `data_loader.py` to use:")
        print(f"   pd.to_datetime(df['your_date_column'], format='{recommended_format}', errors='coerce')")
    elif not unparseable_dates and len(format_counts) > 1:
        print("🟡 Multiple consistent date formats were found. The current two-pass strategy in `data_loader.py` is a good approach.")
        print("   To optimize further, ensure the most common format is used in the first pass.")
        most_common_format = sorted_formats[0][0]
        print(f"   RECOMMENDED first-pass format: '{most_common_format}'")
    elif unparseable_dates:
        print("❌ Action Required: Unparseable dates were found.")
        print("   You must either:")
        print("   1. Correct the listed problematic dates in the source CSV file(s).")
        print("   2. Or, if they represent a valid but unlisted format, add that format string to this script and re-run.")


def run_all_analyses():
    """
    Iterates through the configured files and columns and runs the analysis.
    """
    print_header("Date Format Consistency Debugger")
    print("This script will analyze all date columns to identify inconsistencies.")

    for file, column in FILES_AND_COLUMNS.items():
        analyze_date_column(file, column)

    print("\n--- Debugger Finished ---")


if __name__ == "__main__":
    run_all_analyses()