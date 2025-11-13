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
                
    processed_data = output.getvalue()
    return processed_data