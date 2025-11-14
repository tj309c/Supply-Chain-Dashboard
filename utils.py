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


def get_filtered_data_as_excel_with_metadata(dfs_to_export_dict, metadata_dict=None, formatting_config=None):
    """
    Enhanced export function that includes metadata sheet with filter criteria and formatting options.
    
    Args:
        dfs_to_export_dict: Dictionary of {sheet_name: (dataframe, include_index)}
        metadata_dict: Optional dict with export metadata like filters, report name, timestamp
        formatting_config: Optional dict with formatting options (currency_columns, decimal_columns, etc.)
    
    Returns:
        Bytes object containing formatted Excel file
    """
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Define formats for currency, percentages, and decimals
        currency_fmt = workbook.add_format({'num_format': '$#,##0.00', 'font_size': 10})
        percentage_fmt = workbook.add_format({'num_format': '0.0%', 'font_size': 10})
        decimal_fmt = workbook.add_format({'num_format': '0.00', 'font_size': 10})
        integer_fmt = workbook.add_format({'num_format': '#,##0', 'font_size': 10})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        metadata_header_fmt = workbook.add_format({'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 'font_size': 12})
        metadata_label_fmt = workbook.add_format({'bold': True, 'bg_color': '#E7E6E6'})
        
        # Add metadata sheet if provided
        if metadata_dict:
            metadata_df = pd.DataFrame([
                {'Item': k, 'Value': str(v)} 
                for k, v in metadata_dict.items()
            ])
            metadata_df.to_excel(writer, sheet_name='Export Info', index=False)
            
            # Format metadata sheet
            metadata_ws = writer.sheets['Export Info']
            metadata_ws.set_column(0, 0, 25)  # Item column
            metadata_ws.set_column(1, 1, 50)  # Value column
            
            # Apply formatting to metadata sheet
            for row_num, row_data in enumerate(metadata_df.values, 1):
                metadata_ws.write(row_num, 0, row_data[0], metadata_label_fmt)
        
        # Process each data sheet
        for sheet_name, (df, include_index) in dfs_to_export_dict.items():
            if not isinstance(df, pd.DataFrame):
                print(f"Skipping {sheet_name}: Not a DataFrame.")
                continue
            if df.empty:
                print(f"Skipping {sheet_name}: DataFrame is empty.")
                continue
            
            # Handle datetime columns
            df_to_export = df
            needs_datetime_cleanup = False
            
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    needs_datetime_cleanup = True
                    break
            
            if needs_datetime_cleanup:
                df_to_export = df.copy()
                for col in df_to_export.columns:
                    if pd.api.types.is_datetime64_any_dtype(df_to_export[col]):
                        try:
                            df_to_export[col] = df_to_export[col].dt.tz_localize(None)
                        except TypeError:
                            pass
                        df_to_export[col] = df_to_export[col].dt.strftime('%Y-%m-%d')
            
            # Write to Excel
            df_to_export.to_excel(writer, sheet_name=sheet_name, index=include_index)
            
            # Auto-adjust column widths
            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(df_to_export.columns):
                series = df_to_export[col]
                max_len = max(
                    series.astype(str).map(len).max(),
                    len(str(series.name))
                ) + 2
                worksheet.set_column(idx, idx, max_len)
                
                # Apply formatting based on column names and config
                if formatting_config:
                    col_lower = str(col).lower()
                    
                    # Check for currency columns
                    if any(term in col_lower for term in ['qty', 'amount', 'cost', 'price', 'total', 'units']):
                        if 'currency' not in col_lower:  # Avoid double-formatting percentages
                            for row in range(1, len(df_to_export) + 1):
                                try:
                                    val = worksheet.table[row][idx].value if hasattr(worksheet, 'table') else None
                                    # Apply integer format for quantity columns
                                    if any(t in col_lower for t in ['qty', 'units', 'quantity']):
                                        worksheet.write(row, idx, val, integer_fmt)
                                except:
                                    pass
                    
                    # Check for percentage columns
                    if 'pct' in col_lower or 'percent' in col_lower or '%' in str(col):
                        for row in range(1, len(df_to_export) + 1):
                            try:
                                val = worksheet.table[row][idx].value if hasattr(worksheet, 'table') else None
                            except:
                                pass
    
    processed_data = output.getvalue()
    return processed_data