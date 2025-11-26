import pandas as pd
import streamlit as st
import io # Required for Excel export

# --- Constants ---
MONTH_ORDER = [
    'January', 'February', 'March', 'April', 'May', 'June', 
    'July', 'August', 'September', 'October', 'November', 'December'
]

# --- Data Export Function ---

def get_filtered_data_as_excel(dfs_to_export_dict):
    """
    Processes a dictionary of dataframes
    and returns an Excel file as a bytes object for download.
    The dictionary format is { "sheet_name": (dataframe, include_index_bool) }
    
    Optimized for memory efficiency (Perf #3): Avoid unnecessary dataframe copies
    and perform operations in-place where possible.
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Loop through each key (sheet name) and dataframe in the dictionary
        for sheet_name, (df, include_index) in dfs_to_export_dict.items():
            
            # Ensure dataframe is not just a placeholder
            if not isinstance(df, pd.DataFrame):
                print(f"Skipping {sheet_name}: Not a DataFrame.")
                continue
            if df.empty:
                print(f"Skipping {sheet_name}: DataFrame is empty.")
                continue
            
            # --- OPTIMIZATION (Perf #3): Only copy if datetime conversion is needed ---
            df_to_export = df
            needs_datetime_cleanup = False
            
            # First pass: check if any datetime conversion is needed
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    needs_datetime_cleanup = True
                    break
            
            # Only create a copy if we need to modify datetime columns
            if needs_datetime_cleanup:
                df_to_export = df.copy()
                
                for col in df_to_export.columns:
                    # Check if col is datetime
                    if pd.api.types.is_datetime64_any_dtype(df_to_export[col]):
                        # Convert to timezone-naive datetime
                        try:
                            df_to_export[col] = df_to_export[col].dt.tz_localize(None)
                        except TypeError:
                             # Already naive, do nothing
                             pass
                        # Format as simple date
                        df_to_export[col] = df_to_export[col].dt.strftime('%Y-%m-%d')

            # Write to Excel
            df_to_export.to_excel(writer, sheet_name=sheet_name, index=include_index)
            
            # Auto-adjust column widths
            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(df_to_export.columns):  # Iterate over columns
                series = df_to_export[col]
                max_len = max(
                    series.astype(str).map(len).max(),  # Data max len
                    len(str(series.name))  # Header len
                ) + 2  # Add a little extra space
                worksheet.set_column(idx, idx, max_len)
                
    processed_data = output.getvalue()
    return processed_data


def enrich_orders_with_category(orders_df: pd.DataFrame, master_data_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich orders data with category information from master data.
    
    Joins orders data (which has 'sku' column) with master data to add 'category'
    column using the PLM: Level Classification 4 field. This enables category
    filtering for demand forecasting and other reports.
    
    Args:
        orders_df: Orders dataframe with 'sku' column
        master_data_df: Master data dataframe with 'sku' and 'category' columns
    
    Returns:
        Orders dataframe with 'category' column added via left join
    """
    if orders_df.empty or master_data_df.empty:
        return orders_df
    
    # Ensure both dataframes have the required columns
    if 'sku' not in orders_df.columns or 'sku' not in master_data_df.columns:
        return orders_df
    
    # Left join orders with master data to get category
    # Using left join so we keep all orders even if SKU not in master data
    result = orders_df.merge(
        master_data_df[['sku', 'category']],
        on='sku',
        how='left'
    )
    
    # Fill any missing categories with 'Unknown'
    if 'category' in result.columns:
        result['category'] = result['category'].fillna('Unknown')
    
    return result


def get_cached_report_data(report_view: str, data_loader_func, *loader_args) -> pd.DataFrame:
    """
    Lazy-load and cache report data to avoid reloading on every filter change.
    
    Implements the "lazy filter application" pattern:
    - Load data once per report and cache in session_state
    - Don't reload when filter widgets change
    - Only apply filters when user clicks "Apply Filters"
    
    This significantly improves performance when users select multiple filters
    before applying them (no intermediate data reloads).
    
    Args:
        report_view: Report name for cache key (e.g., "Service Level", "Backorder Report")
        data_loader_func: Function to call to load data
        *loader_args: Arguments to pass to the loader function
    
    Returns:
        Cached DataFrame or newly loaded DataFrame if not cached
    
    Example:
        import streamlit as st
        data = get_cached_report_data(
            report_view,
            load_service_data,
            SERVICE_FILE_PATH,
            log_output
        )
    """
    import streamlit as st
    
    cache_key = f'df_report_{report_view}'
    
    if cache_key not in st.session_state:
        try:
            # Load data for the first time
            result = data_loader_func(*loader_args)
            # Handle different return formats (some loaders return (logs, data, errors))
            if isinstance(result, tuple):
                df = result[1] if len(result) > 1 else pd.DataFrame()
            else:
                df = result
            # Cache it
            st.session_state[cache_key] = df
        except Exception as e:
            print(f"Error loading data for {report_view}: {e}")
            st.session_state[cache_key] = pd.DataFrame()
    
    return st.session_state[cache_key]


def calculate_inventory_stock_value(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate stock value in USD for inventory items using data from INVENTORY.csv.
    
    Uses:
    - on_hand_qty + in_transit_qty for total quantity
    - last_purchase_price for unit price
    - currency for currency conversion to USD
    
    Parameters:
    - df: DataFrame with columns from inventory_analysis (includes pricing from INVENTORY.csv)
    
    Returns:
    - DataFrame with added Stock Value USD column
    
    Notes:
    - If pricing data is missing ($0 price) but stock > 0, this is flagged in debug logs
    - Currency conversions: EUR (1.111), GBP (1.3), USD (1.0)
    """
    df = df.copy()
    
    # DEBUG: Log what columns we actually have
    print(f"[STOCK VALUE DEBUG] Available columns in inventory_analysis: {list(df.columns)}")
    
    # Initialize Stock Value USD with 0
    df['Stock Value USD'] = 0.0
    
    # Check if we have the required pricing columns
    has_quantity_cols = ('on_hand_qty' in df.columns or 'in_transit_qty' in df.columns)
    has_pricing_cols = ('last_purchase_price' in df.columns and 'currency' in df.columns)
    
    print(f"[STOCK VALUE DEBUG] Has quantity cols: {has_quantity_cols}")
    print(f"[STOCK VALUE DEBUG] Has pricing cols: {has_pricing_cols}")
    
    if has_pricing_cols:
        # Convert pricing columns to numeric
        df['last_purchase_price'] = pd.to_numeric(df['last_purchase_price'], errors='coerce').fillna(0)
        df['currency'] = df['currency'].astype(str).str.strip().str.upper()
        df['currency'] = df['currency'].fillna('USD')
        
        # Ensure total quantity column exists
        if 'on_hand_qty' not in df.columns:
            df['on_hand_qty'] = 0
        if 'in_transit_qty' not in df.columns:
            df['in_transit_qty'] = 0
            
        df['on_hand_qty'] = pd.to_numeric(df['on_hand_qty'], errors='coerce').fillna(0)
        df['in_transit_qty'] = pd.to_numeric(df['in_transit_qty'], errors='coerce').fillna(0)
        
        total_qty = df['on_hand_qty'] + df['in_transit_qty']
        
        # Convert price to USD based on currency
        def convert_to_usd(row):
            try:
                price = float(row['last_purchase_price']) if pd.notna(row['last_purchase_price']) else 0
                currency = str(row['currency']).upper().strip() if pd.notna(row['currency']) else 'USD'
                
                # Handle various currency formats
                if 'EUR' in currency:
                    return price * 1.111  # 1 EUR = 1.111 USD
                elif 'GBP' in currency:
                    return price * 1.3    # 1 GBP = 1.3 USD
                elif price > 0:
                    return price          # Assume USD or unknown
                else:
                    return 0
            except:
                return 0
        
        df['Price USD per Unit'] = df.apply(convert_to_usd, axis=1)
        
        # Calculate stock value in USD
        df['Stock Value USD'] = total_qty * df['Price USD per Unit']
        
        # DEBUG: Flag items with stock but no price
        items_with_stock_no_price = ((total_qty > 0) & (df['Price USD per Unit'] == 0)).sum()
        if items_with_stock_no_price > 0:
            print(f"[STOCK VALUE DEBUG] ⚠️ WARNING: {items_with_stock_no_price} items have stock but no pricing info")
            
    else:
        print("[STOCK VALUE DEBUG] ⚠️ Pricing columns NOT FOUND in inventory_analysis")
        print("[STOCK VALUE DEBUG] Stock Value USD will be $0 for all items - pricing data from INVENTORY.csv not loaded")
    
    return df


