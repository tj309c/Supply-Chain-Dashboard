"""
Inventory Page - Enhanced
Comprehensive inventory analysis with:
- Slow-moving, obsolescence, and scrap opportunities
- ABC Analysis
- Stock-out risk alerts
- Currency conversion (USD/EUR)
- Adjustable thresholds
- Future-ready for monthly snapshots
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import numpy as np
import sys
import os
from io import BytesIO
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import (
    render_page_header, render_kpi_row, render_chart,
    render_data_table, render_filter_section, render_info_box
)
from business_rules import (
    convert_currency, get_movement_classification, get_stock_out_risk_level,
    get_scrap_threshold, INVENTORY_RULES, CURRENCY_RULES,
    load_alternate_codes_mapping, get_alternate_codes, get_current_code, is_old_code
)

# ===== SETTINGS AND CONFIGURATION =====

def render_inventory_settings_sidebar():
    """Render adjustable settings in sidebar - organized for optimal UX"""

    # === 1. SEARCH & FILTERS (Most frequently used) ===
    st.sidebar.header("🔍 Search & Filters")

    sku_search = st.sidebar.text_input(
        "Search SKU",
        value="",
        key="sku_search",
        placeholder="Enter SKU code...",
        help="Search for specific SKU (partial match supported)"
    )

    currency = st.sidebar.selectbox(
        "Display Currency",
        options=CURRENCY_RULES["supported_currencies"],
        index=0,
        key="inv_currency",
        help="Select currency for all value displays"
    )

    st.sidebar.divider()

    # === 2. ALERT THRESHOLDS (Important operational settings) ===
    st.sidebar.header("⚠️ Alert Thresholds")

    stockout_threshold = st.sidebar.slider(
        "Stock-Out Alert (days)",
        min_value=1,
        max_value=30,
        value=INVENTORY_RULES["stock_out_risk"]["critical_dio"],
        step=1,
        key="stockout_threshold",
        help="Alert when DIO falls below this threshold"
    )

    default_threshold = INVENTORY_RULES["scrap_criteria"]["default_dio_threshold"]
    min_threshold = INVENTORY_RULES["scrap_criteria"]["min_dio_threshold"]
    max_threshold = INVENTORY_RULES["scrap_criteria"]["max_dio_threshold"]

    scrap_threshold = st.sidebar.slider(
        "Scrap Threshold (days)",
        min_value=min_threshold,
        max_value=max_threshold,
        value=default_threshold,
        step=30,
        key="scrap_threshold",
        help=f"Flag items for scrap when DIO exceeds this (Default: {default_threshold//365} years)"
    )

    st.sidebar.divider()

    # === 3. ANALYSIS CONFIGURATION (Advanced settings - collapsed by default) ===
    with st.sidebar.expander("📊 Analysis Configuration", expanded=False):
        st.caption("**ABC Classification Method**")
        abc_method = st.radio(
            "Method",
            options=["Value-Based (80/15/5)", "Count-Based (20/30/50)"],
            index=0,
            key="abc_method",
            help="Value: A=80% of value | Count: A=20% of SKUs",
            label_visibility="collapsed"
        )
        use_count_based = "Count-Based" in abc_method

        st.divider()

        st.caption("**DIO Bucket Boundaries**")
        use_custom_buckets = st.checkbox(
            "Customize Buckets",
            value=False,
            key="use_custom_buckets",
            help="Customize DIO bucket boundaries for charts"
        )

        if use_custom_buckets:
            st.caption("Set bucket boundaries (in days):")
            bucket_30 = st.number_input("Bucket 1", min_value=1, max_value=90, value=30, step=5, key="bucket_30")
            bucket_60 = st.number_input("Bucket 2", min_value=bucket_30+1, max_value=180, value=60, step=5, key="bucket_60")
            bucket_90 = st.number_input("Bucket 3", min_value=bucket_60+1, max_value=270, value=90, step=10, key="bucket_90")
            bucket_180 = st.number_input("Bucket 4", min_value=bucket_90+1, max_value=365, value=180, step=10, key="bucket_180")
            bucket_365 = st.number_input("Bucket 5", min_value=bucket_180+1, max_value=730, value=365, step=30, key="bucket_365")

            dio_buckets = [0, 0.1, bucket_30, bucket_60, bucket_90, bucket_180, bucket_365, float('inf')]
        else:
            dio_buckets = INVENTORY_RULES["variable_buckets"]["default_boundaries"]
            dio_buckets = [0, 0.1] + dio_buckets + [float('inf')]

    st.sidebar.divider()

    # === 4. EXPORT (Action-oriented - at bottom) ===
    st.sidebar.header("📥 Export Data")

    export_section = st.sidebar.selectbox(
        "Select dataset:",
        options=[
            "All Inventory Data",
            "Warehouse Scrap List",
            "Stock-Out Risks",
            "Slow-Moving Items (Top 50)",
            "ABC Class A Items",
            "ABC Class B Items",
            "ABC Class C Items",
            "Dead Stock Items"
        ],
        key="export_section",
        help="Choose which data to export to Excel"
    )

    # Scrap threshold slider (only shown for Warehouse Scrap List)
    scrap_days_threshold = 730  # Default to 2 years
    if export_section == "Warehouse Scrap List":
        scrap_days_threshold = st.sidebar.slider(
            "Scrap Threshold (Days of Supply)",
            min_value=365,
            max_value=1095,
            value=730,
            step=30,
            help="SKUs with inventory exceeding this many days of supply will be marked for potential scrap. Default: 730 days (2 years)"
        )

    st.sidebar.divider()

    return {
        "currency": currency,
        "scrap_threshold": scrap_threshold,
        "stockout_threshold": stockout_threshold,
        "sku_search": sku_search,
        "export_section": export_section,
        "dio_buckets": dio_buckets,
        "use_custom_buckets": use_custom_buckets,
        "use_count_based_abc": use_count_based,
        "scrap_days_threshold": scrap_days_threshold
    }

# ===== EXPORT FUNCTIONS =====

@st.cache_data(show_spinner="Generating Excel export...")
def create_excel_export(data, section_name, currency="USD"):
    """
    Create Excel file with formatted data

    Args:
        data: DataFrame to export
        section_name: Name of the section being exported
        currency: Currency for value columns

    Returns:
        BytesIO object containing Excel file
    """
    output = BytesIO()

    # Create a copy to avoid modifying original
    export_df = data.copy()

    # Special handling for Warehouse Scrap List - export all columns as-is with summary tab
    if section_name == "Warehouse Scrap List":
        # Warehouse scrap list already has formatted column names, export all columns
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book

            # === TAB 1: RAW DATA ===
            # Define professional formats (Luxottica brand colors: blue and white)
            header_format = workbook.add_format({
                'bold': True,
                'font_size': 11,
                'bg_color': '#0066CC',  # Luxottica blue
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True
            })

            date_format = workbook.add_format({
                'num_format': 'mm/dd/yyyy',
                'border': 1
            })

            currency_format = workbook.add_format({
                'num_format': '$#,##0.00',
                'border': 1
            })

            number_format = workbook.add_format({
                'num_format': '#,##0',
                'border': 1
            })

            decimal_format = workbook.add_format({
                'num_format': '#,##0.00',
                'border': 1
            })

            text_format = workbook.add_format({
                'border': 1,
                'align': 'left',
                'valign': 'vcenter'
            })

            # Write data without headers first
            export_df.to_excel(writer, sheet_name="Raw Data", index=False, startrow=1, header=False)
            worksheet = writer.sheets["Raw Data"]

            # Write formatted headers
            for col_idx, col_name in enumerate(export_df.columns):
                worksheet.write(0, col_idx, col_name, header_format)

            # Freeze top row
            worksheet.freeze_panes(1, 0)

            # Add comments/notes to scrap recommendation column headers (cells W-AB)
            scrap_column_comments = {
                'Conservative Scrap Qty': 'CONSERVATIVE APPROACH:\n• SKUs > 3 years old\n• Low demand frequency (≤1 month with demand in last 12 months)\n• Keep 12 months supply as safety stock\n• Excludes SKUs < 1 year old (insufficient data)',
                'Conservative Scrap Value (USD)': 'CONSERVATIVE VALUE:\nUSD value of conservative scrap recommendation\n\nFormula: Conservative Scrap Qty × Last Purchase Price',
                'Medium Scrap Qty': 'MEDIUM APPROACH:\n• SKUs > 2 years old\n• Keep 6 months supply (base)\n• Keep 3 months for Class C/discontinued/superseded SKUs\n• Adjusts for ABC class, PLM status, alternate codes',
                'Medium Scrap Value (USD)': 'MEDIUM VALUE:\nUSD value of medium scrap recommendation\n\nFormula: Medium Scrap Qty × Last Purchase Price',
                'Aggressive Scrap Qty': 'AGGRESSIVE APPROACH:\n• SKUs > 1 year old (base requirement)\n• Keep 3 months supply (base)\n• Keep 2 months for SKUs > 3 years old\n• Keep 1 month for old + Class C/discontinued/superseded\n• Dead stock (no demand) = scrap 100%\n• Logic: Older SKUs have more data → higher confidence',
                'Aggressive Scrap Value (USD)': 'AGGRESSIVE VALUE:\nUSD value of aggressive scrap recommendation\n\nFormula: Aggressive Scrap Qty × Last Purchase Price'
            }

            # Apply column formatting and comments
            date_columns = ['SKU Creation Date', 'Last Inbound Date', 'PLM Expiration Date']
            currency_columns = ['STD Price', 'Total STD Price', 'USD value over 2 Yrs Supply',
                              'Conservative Scrap Value (USD)', 'Medium Scrap Value (USD)', 'Aggressive Scrap Value (USD)']
            number_columns = ['Free Qt', 'Rolling 1 Yr Usage', '# of Months with History', 'Qty over 2 Yrs Supply',
                            'Conservative Scrap Qty', 'Medium Scrap Qty', 'Aggressive Scrap Qty']
            decimal_columns = ['Months of Supply']

            for col_idx, col_name in enumerate(export_df.columns):
                # Set column width
                if col_name in ['Material', 'Alternate Codes']:
                    col_width = 15
                elif col_name in ['Description']:
                    col_width = 35
                elif col_name in ['Storage Location', 'Category', 'Brand']:
                    col_width = 20
                elif col_name in date_columns:
                    col_width = 12
                elif col_name in currency_columns:
                    col_width = 15
                elif col_name in number_columns:
                    col_width = 12
                else:
                    col_width = 14

                # Apply formatting to data rows
                if col_name in date_columns:
                    worksheet.set_column(col_idx, col_idx, col_width, date_format)
                elif col_name in currency_columns:
                    worksheet.set_column(col_idx, col_idx, col_width, currency_format)
                elif col_name.startswith('m_') or col_name in number_columns:
                    worksheet.set_column(col_idx, col_idx, col_width, number_format)
                elif col_name in decimal_columns:
                    worksheet.set_column(col_idx, col_idx, col_width, decimal_format)
                else:
                    worksheet.set_column(col_idx, col_idx, col_width, text_format)

                # Add comments to scrap recommendation columns
                if col_name in scrap_column_comments:
                    worksheet.write_comment(0, col_idx, scrap_column_comments[col_name], {
                        'x_scale': 2.5,
                        'y_scale': 2.5
                    })

            # === TAB 2: EXECUTIVE SUMMARY ===
            summary_sheet = workbook.add_worksheet("Executive Summary")

            # Define formats with Luxottica branding (blue and white)
            summary_title_format = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'bg_color': '#0066CC',  # Luxottica blue
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            summary_header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#0066CC',  # Luxottica blue
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            summary_value_format = workbook.add_format({
                'num_format': '#,##0',
                'border': 1,
                'align': 'right'
            })
            summary_currency_format = workbook.add_format({
                'num_format': '$#,##0',
                'border': 1,
                'align': 'right'
            })

            # Header
            row = 0
            summary_sheet.merge_range(row, 0, row, 6, "WAREHOUSE SCRAP RECOMMENDATIONS - EXECUTIVE SUMMARY", summary_title_format)
            row += 2

            # Section 0: Business Rules Legend
            summary_sheet.merge_range(row, 0, row, 6, "SCRAP RECOMMENDATION BUSINESS RULES", summary_title_format)
            row += 1

            legend_format = workbook.add_format({
                'text_wrap': True,
                'border': 1,
                'align': 'left',
                'valign': 'top'
            })
            legend_header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1,
                'text_wrap': True
            })

            # Conservative
            summary_sheet.write(row, 0, "CONSERVATIVE", legend_header_format)
            summary_sheet.merge_range(row, 1, row, 6,
                "• SKUs > 3 years old\n"
                "• Low demand frequency (≤1 month with demand in last 12 months)\n"
                "• Keep 12 months supply as safety stock\n"
                "• Excludes SKUs < 1 year old (insufficient historical data)\n"
                "• Lowest risk, most cautious approach",
                legend_format)
            row += 1

            # Medium
            summary_sheet.write(row, 0, "MEDIUM", legend_header_format)
            summary_sheet.merge_range(row, 1, row, 6,
                "• SKUs > 2 years old\n"
                "• Keep 6 months supply (base safety stock)\n"
                "• MORE AGGRESSIVE (3 months) for:\n"
                "  - ABC Class C items (low-value)\n"
                "  - Discontinued or expired PLM status\n"
                "  - Superseded SKUs (old alternate codes)\n"
                "• Balanced approach with risk adjustments",
                legend_format)
            row += 1

            # Aggressive
            summary_sheet.write(row, 0, "AGGRESSIVE", legend_header_format)
            summary_sheet.merge_range(row, 1, row, 6,
                "• SKUs > 1 year old (minimum age requirement)\n"
                "• Keep 3 months supply (base safety stock)\n"
                "• VERY AGGRESSIVE (2 months) for SKUs > 3 years old\n"
                "• EXTRA AGGRESSIVE (1 month) for SKUs > 3 years + Class C/discontinued/superseded\n"
                "• Dead stock (no demand) = scrap 100%\n"
                "• Logic: Older SKUs have more data points → higher confidence in recommendations",
                legend_format)
            row += 2

            summary_sheet.set_row(row - 3, 80)  # Conservative row height
            summary_sheet.set_row(row - 2, 90)  # Medium row height
            summary_sheet.set_row(row - 1, 110) # Aggressive row height

            # Section 1: Executive Summary Totals
            summary_sheet.merge_range(row, 0, row, 4, "SUMMARY TOTALS BY SCRAP LEVEL", summary_title_format)
            row += 1

            # Calculate totals
            total_skus = len(export_df)
            conservative_skus = (export_df['Conservative Scrap Qty'] > 0).sum()
            conservative_qty = export_df['Conservative Scrap Qty'].sum()
            conservative_value = export_df['Conservative Scrap Value (USD)'].sum()

            medium_skus = (export_df['Medium Scrap Qty'] > 0).sum()
            medium_qty = export_df['Medium Scrap Qty'].sum()
            medium_value = export_df['Medium Scrap Value (USD)'].sum()

            aggressive_skus = (export_df['Aggressive Scrap Qty'] > 0).sum()
            aggressive_qty = export_df['Aggressive Scrap Qty'].sum()
            aggressive_value = export_df['Aggressive Scrap Value (USD)'].sum()

            # Calculate weighted average months of supply (weighted by inventory value)
            # Formula: Sum(months_of_supply * inventory_value) / Sum(inventory_value)
            if 'Months of Supply' in export_df.columns and 'Total STD Price' in export_df.columns:
                total_inventory_value = export_df['Total STD Price'].sum()
                if total_inventory_value > 0:
                    weighted_mos = (export_df['Months of Supply'] * export_df['Total STD Price']).sum() / total_inventory_value
                else:
                    weighted_mos = 0
            else:
                weighted_mos = 0

            # Write summary table
            summary_sheet.write(row, 0, "Scrap Level", summary_header_format)
            summary_sheet.write(row, 1, "# SKUs with Recommendations", summary_header_format)
            summary_sheet.write(row, 2, "Total Scrap Qty", summary_header_format)
            summary_sheet.write(row, 3, "Total Scrap Value (USD)", summary_header_format)
            summary_sheet.write(row, 4, "Weighted Avg Months of Supply", summary_header_format)
            row += 1

            summary_sheet.write(row, 0, "Conservative", summary_value_format)
            summary_sheet.write(row, 1, conservative_skus, summary_value_format)
            summary_sheet.write(row, 2, conservative_qty, summary_value_format)
            summary_sheet.write(row, 3, conservative_value, summary_currency_format)
            summary_sheet.write(row, 4, round(weighted_mos, 1), summary_value_format)
            row += 1

            summary_sheet.write(row, 0, "Medium", summary_value_format)
            summary_sheet.write(row, 1, medium_skus, summary_value_format)
            summary_sheet.write(row, 2, medium_qty, summary_value_format)
            summary_sheet.write(row, 3, medium_value, summary_currency_format)
            summary_sheet.write(row, 4, round(weighted_mos, 1), summary_value_format)
            row += 1

            summary_sheet.write(row, 0, "Aggressive", summary_value_format)
            summary_sheet.write(row, 1, aggressive_skus, summary_value_format)
            summary_sheet.write(row, 2, aggressive_qty, summary_value_format)
            summary_sheet.write(row, 3, aggressive_value, summary_currency_format)
            summary_sheet.write(row, 4, round(weighted_mos, 1), summary_value_format)
            row += 3

            # Section 2: Top 20 High-Value Scrap Opportunities
            summary_sheet.merge_range(row, 0, row, 6, "TOP 20 HIGH-VALUE SCRAP OPPORTUNITIES (Aggressive)", summary_title_format)
            row += 1

            top_20 = export_df.nlargest(20, 'Aggressive Scrap Value (USD)')[
                ['Material', 'Description', 'Category', 'Free Qt', 'Aggressive Scrap Qty', 'Aggressive Scrap Value (USD)', 'Months of Supply']
            ].copy()

            # Write top 20 header
            for col_idx, col_name in enumerate(top_20.columns):
                summary_sheet.write(row, col_idx, col_name, summary_header_format)
            row += 1

            # Write top 20 data (using itertuples for 100x faster performance)
            for data_row in top_20.itertuples(index=False):
                for col_idx, value in enumerate(data_row):
                    if col_idx in [4, 5]:  # Qty and Value columns
                        summary_sheet.write(row, col_idx, value, summary_currency_format if col_idx == 5 else summary_value_format)
                    else:
                        summary_sheet.write(row, col_idx, value)
                row += 1

            row += 2

            # Section 3: Category Breakdown (if available)
            if 'Category' in export_df.columns and export_df['Category'].notna().any():
                summary_sheet.merge_range(row, 0, row, 6, "SCRAP VALUE BY CATEGORY", summary_title_format)
                row += 1

                category_summary = export_df.groupby('Category').agg({
                    'Material': 'count',
                    'Conservative Scrap Value (USD)': 'sum',
                    'Medium Scrap Value (USD)': 'sum',
                    'Aggressive Scrap Value (USD)': 'sum'
                }).reset_index()
                category_summary.columns = ['Category', '# SKUs', 'Conservative Value', 'Medium Value', 'Aggressive Value']
                category_summary = category_summary.sort_values('Aggressive Value', ascending=False).head(15)

                # Write category header
                for col_idx, col_name in enumerate(category_summary.columns):
                    summary_sheet.write(row, col_idx, col_name, summary_header_format)
                row += 1

                # Write category data (using itertuples for 100x faster performance)
                for data_row in category_summary.itertuples(index=False):
                    for col_idx, value in enumerate(data_row):
                        if col_idx >= 2:  # Value columns
                            summary_sheet.write(row, col_idx, value, summary_currency_format)
                        else:
                            summary_sheet.write(row, col_idx, value, summary_value_format if col_idx == 1 else None)
                    row += 1

            # Auto-adjust column widths for summary sheet
            summary_sheet.set_column(0, 0, 25)
            summary_sheet.set_column(1, 1, 30)
            summary_sheet.set_column(2, 6, 18)

        output.seek(0)
        return output

    # Select relevant columns and format for regular inventory exports
    value_col = f'stock_value_{currency.lower()}'

    columns_to_export = []
    if 'sku' in export_df.columns:
        columns_to_export.append('sku')
    if 'category' in export_df.columns:
        columns_to_export.append('category')
    if 'on_hand_qty' in export_df.columns:
        columns_to_export.append('on_hand_qty')
    if 'in_transit_qty' in export_df.columns:
        columns_to_export.append('in_transit_qty')
    if 'daily_demand' in export_df.columns:
        columns_to_export.append('daily_demand')
    if 'dio' in export_df.columns:
        columns_to_export.append('dio')
    if value_col in export_df.columns:
        columns_to_export.append(value_col)
    if 'movement_class' in export_df.columns:
        columns_to_export.append('movement_class')
    if 'stock_out_risk' in export_df.columns:
        columns_to_export.append('stock_out_risk')
    if 'abc_class' in export_df.columns:
        columns_to_export.append('abc_class')
    if 'last_purchase_price' in export_df.columns:
        columns_to_export.append('last_purchase_price')

    export_df = export_df[columns_to_export]

    # Rename columns for readability
    column_names = {
        'sku': 'SKU',
        'category': 'Category',
        'on_hand_qty': 'On Hand Qty',
        'in_transit_qty': 'In Transit Qty',
        'daily_demand': 'Daily Demand',
        'dio': 'DIO (days)',
        value_col: f'Stock Value ({currency})',
        'movement_class': 'Movement Class',
        'stock_out_risk': 'Stock-Out Risk',
        'abc_class': 'ABC Class',
        'last_purchase_price': 'Last Purchase Price'
    }
    export_df = export_df.rename(columns=column_names)

    # Write to Excel with formatting
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        export_df.to_excel(writer, sheet_name=section_name[:31], index=False)  # Excel sheet name limit is 31 chars

        # Get workbook and worksheet objects
        workbook = writer.book
        worksheet = writer.sheets[section_name[:31]]

        # Add formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })

        # Format header row
        for col_num, value in enumerate(export_df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Auto-fit columns
        for i, col in enumerate(export_df.columns):
            max_len = max(
                export_df[col].astype(str).apply(len).max(),
                len(col)
            ) + 2
            worksheet.set_column(i, i, min(max_len, 50))

    output.seek(0)
    return output

@st.cache_data(ttl=3600, show_spinner="Computing scrap recommendations...")
def prepare_warehouse_scrap_list(inventory_data, scrap_days_threshold, currency):
    """
    Prepare comprehensive warehouse scrap list with 3-level scrap recommendations

    This function implements a data-driven, 3-level scrap recommendation system based on:
    - SKU age (from activation date)
    - Historical demand patterns (monthly and rolling 1-year)
    - ABC classification (calculated from inventory value)
    - PLM status (discontinued/expired items)
    - Alternate code status (superseded SKUs)

    Business Logic (User-Validated):
    - OLDER SKUs with excess inventory = MORE aggressive scrap candidates
      (More data points = higher confidence in overstocking diagnosis)
    - SKUs < 1 year old are EXCLUDED from all scrap recommendations
      (Insufficient historical data for accurate recommendations)

    Scrap Levels:
    1. Conservative: Older SKUs (>3 years) + low demand frequency + keep 12 months supply
    2. Medium: Moderate age SKUs (>2 years) + keep 6 months supply
       - More aggressive (3 months) for Class C, discontinued, or superseded SKUs
    3. Aggressive: Established SKUs (>1 year) + keep 3 months supply
       - Very aggressive (2 months) for SKUs >3 years old
       - Extra aggressive (1 month) for old + Class C/discontinued/superseded SKUs
       - Dead stock (no demand) = scrap everything

    Args:
        inventory_data: Full inventory DataFrame with monthly demand data (last 12 months)
        scrap_days_threshold: Days of supply threshold for legacy "2 years supply" calculation
        currency: Currency for value calculations

    Returns:
        DataFrame with 25 fields (19 original + 6 new scrap recommendation columns):
        - Original 19 fields: Material, Alternate Codes, Storage Location, Description, etc.
        - NEW: Conservative Scrap Qty, Conservative Scrap Value (USD)
        - NEW: Medium Scrap Qty, Medium Scrap Value (USD)
        - NEW: Aggressive Scrap Qty, Aggressive Scrap Value (USD)
    """
    from business_rules import load_alternate_codes_mapping, get_alternate_codes

    # Filter for SKUs with on-hand inventory only
    df = inventory_data[inventory_data['on_hand_qty'] > 0].copy()

    if df.empty:
        return pd.DataFrame()

    # Calculate scrap quantities
    df['scrap_qty'] = df.apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * scrap_days_threshold))
        if row['daily_demand'] > 0 else row['on_hand_qty'],
        axis=1
    )

    # Calculate scrap value in USD
    # Ensure currency column exists
    if 'currency' not in df.columns:
        df['currency'] = 'USD'

    df['scrap_value_usd'] = df.apply(
        lambda row: row['scrap_qty'] * convert_currency(
            row['last_purchase_price'],
            row.get('currency', 'USD'),
            'USD'
        ),
        axis=1
    )

    # Calculate months of supply
    df['months_of_supply'] = df['dio'] / 30

    # ===== 3-LEVEL SCRAP RECOMMENDATION SYSTEM =====
    # Calculate SKU age in days (from activation date to today)
    today = pd.to_datetime(datetime.now().date())
    df['sku_age_days'] = (today - df['activation_date']).dt.days if 'activation_date' in df.columns else 0

    # Calculate last demand date (from deliveries) - placeholder for now, will be populated if data available
    # This will be calculated from the delivery history in a future enhancement

    # Calculate demand frequency metrics
    # The inventory loader now provides last-12-monthly columns named 'm_YYYY_MM'
    # Count how many months had demand > 0
    month_columns = sorted([c for c in df.columns if c.startswith('m_')])
    df['months_with_demand'] = 0
    for m in month_columns:
        df['months_with_demand'] += (df[m] > 0).astype(int)

    # Calculate monthly demand frequency (based on rolling 1yr usage)
    df['avg_monthly_demand'] = df['rolling_1yr_usage'] / 12 if 'rolling_1yr_usage' in df.columns else 0

    # Determine if SKU is superseded (has alternate codes and is old code)
    from business_rules import is_old_code
    df['is_superseded'] = df['sku'].apply(is_old_code)

    # Determine ABC classification (placeholder - this would come from master data or be calculated)
    # For now, we'll use a simple heuristic based on rolling 1yr usage value
    if 'rolling_1yr_usage' in df.columns:
        df['abc_class'] = 'C'  # Default to C
        total_value = (df['on_hand_qty'] * df['last_purchase_price']).sum()
        df['sku_value'] = df['on_hand_qty'] * df['last_purchase_price']
        df_sorted = df.sort_values('sku_value', ascending=False)
        df_sorted['cumulative_pct'] = (df_sorted['sku_value'].cumsum() / total_value * 100)
        df.loc[df_sorted[df_sorted['cumulative_pct'] <= 80].index, 'abc_class'] = 'A'
        df.loc[df_sorted[(df_sorted['cumulative_pct'] > 80) & (df_sorted['cumulative_pct'] <= 95)].index, 'abc_class'] = 'B'

    # Check PLM status for discontinued items
    df['is_discontinued'] = False
    if 'plm_status' in df.columns:
        df['is_discontinued'] = df['plm_status'].str.contains('discontin|expir|obsol', case=False, na=False)

    # ===== CONSERVATIVE SCRAP LEVEL =====
    # Target: Older SKUs (>3 years) + no demand in >12 months + keep 12 months supply
    # Exclude SKUs < 1 year old
    df['conservative_scrap_qty'] = 0
    df['conservative_scrap_value_usd'] = 0.0

    conservative_mask = (
        (df['sku_age_days'] > 365) &  # At least 1 year old
        (df['sku_age_days'] > 1095) &  # Prefer >3 years
        (df['daily_demand'] > 0) &  # Must have demand history
        (df['months_with_demand'] < 2)  # Low demand frequency (< 2 months in last 12)
    )

    # Conservative: Keep 12 months supply (365 days)
    df.loc[conservative_mask, 'conservative_scrap_qty'] = df.loc[conservative_mask].apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * 365)),
        axis=1
    )

    # ===== MEDIUM SCRAP LEVEL =====
    # Target: Moderate age SKUs (>2 years) + minimal demand (>6 months) + keep 6 months supply
    df['medium_scrap_qty'] = 0
    df['medium_scrap_value_usd'] = 0.0

    medium_mask = (
        (df['sku_age_days'] > 365) &  # At least 1 year old
        (df['sku_age_days'] > 730) &  # Prefer >2 years
        (df['daily_demand'] > 0)  # Must have demand history
    )

    # Medium: Keep 6 months supply (180 days)
    df.loc[medium_mask, 'medium_scrap_qty'] = df.loc[medium_mask].apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * 180)),
        axis=1
    )

    # More aggressive for Class C, discontinued, or superseded SKUs
    medium_aggressive_mask = medium_mask & (
        (df['abc_class'] == 'C') |
        (df['is_discontinued']) |
        (df['is_superseded'])
    )
    df.loc[medium_aggressive_mask, 'medium_scrap_qty'] = df.loc[medium_aggressive_mask].apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * 90)),  # Keep only 3 months
        axis=1
    )

    # ===== AGGRESSIVE SCRAP LEVEL =====
    # Target: Established SKUs (>1 year) + older = more aggressive + keep 3 months supply
    # User's corrected logic: OLDER SKUs with excess inventory = MORE aggressive candidates
    df['aggressive_scrap_qty'] = 0
    df['aggressive_scrap_value_usd'] = 0.0

    aggressive_mask = (
        (df['sku_age_days'] > 365) &  # At least 1 year old (sufficient data points)
        (df['daily_demand'] > 0)  # Must have demand history
    )

    # Aggressive: Base keep is 3 months supply (90 days)
    df.loc[aggressive_mask, 'aggressive_scrap_qty'] = df.loc[aggressive_mask].apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * 90)),
        axis=1
    )

    # VERY aggressive for older SKUs (>3 years) with high supply
    # User's insight: More data points = more confidence in overstocking diagnosis
    very_aggressive_mask = aggressive_mask & (df['sku_age_days'] > 1095)  # >3 years
    df.loc[very_aggressive_mask, 'aggressive_scrap_qty'] = df.loc[very_aggressive_mask].apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * 60)),  # Keep only 2 months
        axis=1
    )

    # EXTRA aggressive for Class C, discontinued, or superseded + old SKUs
    extra_aggressive_mask = very_aggressive_mask & (
        (df['abc_class'] == 'C') |
        (df['is_discontinued']) |
        (df['is_superseded'])
    )
    df.loc[extra_aggressive_mask, 'aggressive_scrap_qty'] = df.loc[extra_aggressive_mask].apply(
        lambda row: max(0, row['on_hand_qty'] - (row['daily_demand'] * 30)),  # Keep only 1 month
        axis=1
    )

    # For items with NO demand (dead stock), all levels recommend scrapping everything
    dead_stock_mask = (df['daily_demand'] == 0) & (df['sku_age_days'] > 365)
    df.loc[dead_stock_mask, 'conservative_scrap_qty'] = df.loc[dead_stock_mask, 'on_hand_qty']
    df.loc[dead_stock_mask, 'medium_scrap_qty'] = df.loc[dead_stock_mask, 'on_hand_qty']
    df.loc[dead_stock_mask, 'aggressive_scrap_qty'] = df.loc[dead_stock_mask, 'on_hand_qty']

    # Calculate USD values for each scrap level
    df['conservative_scrap_value_usd'] = df.apply(
        lambda row: row['conservative_scrap_qty'] * convert_currency(
            row['last_purchase_price'],
            row.get('currency', 'USD'),
            'USD'
        ),
        axis=1
    )

    df['medium_scrap_value_usd'] = df.apply(
        lambda row: row['medium_scrap_qty'] * convert_currency(
            row['last_purchase_price'],
            row.get('currency', 'USD'),
            'USD'
        ),
        axis=1
    )

    df['aggressive_scrap_value_usd'] = df.apply(
        lambda row: row['aggressive_scrap_qty'] * convert_currency(
            row['last_purchase_price'],
            row.get('currency', 'USD'),
            'USD'
        ),
        axis=1
    )

    # Get alternate codes for each SKU
    df['alternate_codes'] = df['sku'].apply(
        lambda sku: ', '.join(get_alternate_codes(sku))
        if get_alternate_codes(sku) else ''
    )

    # Build the 25-field export (19 original + 6 new scrap recommendation columns)
    # Handle missing optional columns by creating empty Series with same index
    scrap_list = pd.DataFrame({
        'Material': df['sku'],
        'Alternate Codes': df['alternate_codes']
    })

    # Add optional columns with fallback to empty string or 0
    # Use .get() method on Series or check column existence first
    if 'storage_location' in df.columns:
        scrap_list['Storage Location'] = df['storage_location']
    else:
        scrap_list['Storage Location'] = ''

    if 'product_name' in df.columns:
        scrap_list['Description'] = df['product_name']
    else:
        scrap_list['Description'] = ''

    if 'activation_date' in df.columns:
        scrap_list['SKU Creation Date'] = df['activation_date']
    else:
        scrap_list['SKU Creation Date'] = ''

    if 'plm_status' in df.columns:
        scrap_list['Flag Status (PLM Current Status)'] = df['plm_status']
    else:
        scrap_list['Flag Status (PLM Current Status)'] = ''

    if 'last_inbound_date' in df.columns:
        scrap_list['Last Inbound Date'] = df['last_inbound_date']
    else:
        scrap_list['Last Inbound Date'] = ''

    if 'plm_expiration_date' in df.columns:
        scrap_list['PLM Expiration Date'] = df['plm_expiration_date']
    else:
        scrap_list['PLM Expiration Date'] = ''

    if 'brand' in df.columns:
        scrap_list['Brand'] = df['brand']
    else:
        scrap_list['Brand'] = ''

    if 'category' in df.columns:
        scrap_list['Category'] = df['category']
    else:
        scrap_list['Category'] = ''

    scrap_list['STD Price'] = df['last_purchase_price']
    scrap_list['Total STD Price'] = df['on_hand_qty'] * df['last_purchase_price']
    scrap_list['Free Qt'] = df['on_hand_qty']

    # Append last-12-month monthly demand columns (m_YYYY_MM) and inventory snapshot columns (inv_m_YYYY_MM)
    months_present = sorted([c for c in df.columns if c.startswith('m_') or c.startswith('inv_m_')])
    for c in months_present:
        if c.startswith('inv_m_'):
            # inv_m_YYYY_MM -> display as e.g. 'Inv 2024-01'
            display_name = 'Inv ' + c.replace('inv_m_', '').replace('_', '-')
        else:
            # m_YYYY_MM -> display as 'YYYY-01'
            display_name = c.replace('m_', '').replace('_', '-')
        scrap_list[display_name] = df[c]

    if 'rolling_1yr_usage' in df.columns:
        scrap_list['Rolling 1 Yr Usage'] = df['rolling_1yr_usage']
    else:
        scrap_list['Rolling 1 Yr Usage'] = 0

    if 'months_with_history' in df.columns:
        scrap_list['# of Months with History'] = df['months_with_history']
    else:
        scrap_list['# of Months with History'] = 0
    scrap_list['Months of Supply'] = df['months_of_supply']
    scrap_list['Qty over 2 Yrs Supply'] = df['scrap_qty']
    scrap_list['USD value over 2 Yrs Supply'] = df['scrap_value_usd']
    # NEW: 3-Level Scrap Recommendations
    scrap_list['Conservative Scrap Qty'] = df['conservative_scrap_qty']
    scrap_list['Conservative Scrap Value (USD)'] = df['conservative_scrap_value_usd']
    scrap_list['Medium Scrap Qty'] = df['medium_scrap_qty']
    scrap_list['Medium Scrap Value (USD)'] = df['medium_scrap_value_usd']
    scrap_list['Aggressive Scrap Qty'] = df['aggressive_scrap_qty']
    scrap_list['Aggressive Scrap Value (USD)'] = df['aggressive_scrap_value_usd']

    # Sort by scrap value descending (highest value scrap opportunities first)
    scrap_list = scrap_list.sort_values('USD value over 2 Yrs Supply', ascending=False)

    return scrap_list

@st.cache_data(show_spinner=False)
def prepare_export_data(inventory_data, section, currency, scrap_threshold, scrap_days_threshold=730):
    """
    Prepare data for export based on selected section

    Args:
        inventory_data: Full inventory DataFrame
        section: Selected section name
        currency: Currency for value columns
        scrap_threshold: DIO threshold for scrap candidates
        scrap_days_threshold: Days of supply threshold for warehouse scrap list (default 730 = 2 years)

    Returns:
        Filtered DataFrame
    """
    value_col = f'stock_value_{currency.lower()}'

    if section == "All Inventory Data":
        return inventory_data

    elif section == "Warehouse Scrap List":
        return prepare_warehouse_scrap_list(inventory_data, scrap_days_threshold, currency)

    elif section == "Stock-Out Risks":
        return inventory_data[inventory_data['stock_out_risk'] == 'Critical'].sort_values('dio')

    elif section == "Slow-Moving Items (Top 50)":
        slow_movers = inventory_data[
            inventory_data['movement_class'].isin(['Slow Moving', 'Very Slow Moving', 'Obsolete Risk', 'Dead Stock'])
        ]
        return slow_movers.sort_values(value_col, ascending=False).head(50)

    elif section == "ABC Class A Items":
        return inventory_data[inventory_data['abc_class'] == 'A'].sort_values(value_col, ascending=False)

    elif section == "ABC Class B Items":
        return inventory_data[inventory_data['abc_class'] == 'B'].sort_values(value_col, ascending=False)

    elif section == "ABC Class C Items":
        return inventory_data[inventory_data['abc_class'] == 'C'].sort_values(value_col, ascending=False)

    elif section == "Dead Stock Items":
        return inventory_data[inventory_data['movement_class'] == 'Dead Stock'].sort_values(value_col, ascending=False)

    return inventory_data

# ===== FILTERING =====

def get_inventory_filters(inventory_data):
    """Define filters for inventory page"""
    if inventory_data.empty:
        return []

    filters = []

    # Category filter
    if 'category' in inventory_data.columns:
        categories = ['All'] + sorted(inventory_data['category'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "Category",
            "options": categories,
            "key": "inv_category_filter"
        })

    # Movement classification filter
    if 'movement_class' in inventory_data.columns:
        movement_classes = ['All'] + sorted(inventory_data['movement_class'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "Movement Classification",
            "options": movement_classes,
            "key": "inv_movement_filter"
        })

    # Stock-out risk filter
    if 'stock_out_risk' in inventory_data.columns:
        risk_levels = ['All'] + sorted(inventory_data['stock_out_risk'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "Stock-Out Risk",
            "options": risk_levels,
            "key": "inv_risk_filter"
        })

    # ABC Classification filter
    if 'abc_class' in inventory_data.columns:
        abc_classes = ['All'] + sorted(inventory_data['abc_class'].dropna().unique().tolist())
        filters.append({
            "type": "selectbox",
            "label": "ABC Classification",
            "options": abc_classes,
            "key": "inv_abc_filter"
        })

    # DIO range filter
    filters.append({
        "type": "selectbox",
        "label": "DIO Range",
        "options": ['All', '0-30 days', '31-60 days', '61-90 days', '91-180 days', '180-365 days', '365+ days', 'No Movement'],
        "key": "inv_dio_filter"
    })

    return filters

def apply_inventory_filters(inventory_data, filter_values, settings):
    """Apply selected filters to inventory data"""
    filtered = inventory_data

    if 'inv_category_filter' in filter_values and filter_values['inv_category_filter'] != 'All':
        filtered = filtered[filtered['category'] == filter_values['inv_category_filter']]

    if 'inv_movement_filter' in filter_values and filter_values['inv_movement_filter'] != 'All':
        filtered = filtered[filtered['movement_class'] == filter_values['inv_movement_filter']]

    if 'inv_risk_filter' in filter_values and filter_values['inv_risk_filter'] != 'All':
        filtered = filtered[filtered['stock_out_risk'] == filter_values['inv_risk_filter']]

    if 'inv_abc_filter' in filter_values and filter_values['inv_abc_filter'] != 'All':
        filtered = filtered[filtered['abc_class'] == filter_values['inv_abc_filter']]

    if 'inv_dio_filter' in filter_values and filter_values['inv_dio_filter'] != 'All':
        dio_range = filter_values['inv_dio_filter']
        if dio_range == '0-30 days':
            filtered = filtered[(filtered['dio'] > 0) & (filtered['dio'] <= 30)]
        elif dio_range == '31-60 days':
            filtered = filtered[(filtered['dio'] > 30) & (filtered['dio'] <= 60)]
        elif dio_range == '61-90 days':
            filtered = filtered[(filtered['dio'] > 60) & (filtered['dio'] <= 90)]
        elif dio_range == '91-180 days':
            filtered = filtered[(filtered['dio'] > 90) & (filtered['dio'] <= 180)]
        elif dio_range == '180-365 days':
            filtered = filtered[(filtered['dio'] > 180) & (filtered['dio'] <= 365)]
        elif dio_range == '365+ days':
            filtered = filtered[filtered['dio'] > 365]
        elif dio_range == 'No Movement':
            filtered = filtered[filtered['dio'] == 0]

    # Apply SKU search
    if settings['sku_search']:
        filtered = filtered[filtered['sku'].str.contains(settings['sku_search'], case=False, na=False)]

    return filtered

# ===== ABC ANALYSIS =====

@st.cache_data(show_spinner=False)
def calculate_abc_classification(inventory_data, use_count_based=False):
    """
    Calculate ABC classification based on value or count

    Args:
        inventory_data: DataFrame with inventory data
        use_count_based: If True, use count-based (top 20% of SKUs = A),
                        if False, use value-based (top 80% of value = A)
    """
    if inventory_data.empty or 'stock_value_usd' not in inventory_data.columns:
        return inventory_data

    # Sort by value descending
    sorted_data = inventory_data.sort_values('stock_value_usd', ascending=False).copy()

    if use_count_based:
        # Count-based: Top X% of SKUs by value
        total_skus = len(sorted_data)
        a_count_pct = INVENTORY_RULES["abc_analysis"]["a_class_count_pct"]
        b_count_pct = INVENTORY_RULES["abc_analysis"]["b_class_count_pct"]

        a_cutoff = int(total_skus * a_count_pct / 100)
        b_cutoff = int(total_skus * (a_count_pct + b_count_pct) / 100)

        sorted_data['abc_class'] = 'C'  # Default
        sorted_data.iloc[:a_cutoff, sorted_data.columns.get_loc('abc_class')] = 'A'
        sorted_data.iloc[a_cutoff:b_cutoff, sorted_data.columns.get_loc('abc_class')] = 'B'

    else:
        # Value-based: Top X% of cumulative value
        sorted_data['cumulative_value'] = sorted_data['stock_value_usd'].cumsum()
        total_value = sorted_data['stock_value_usd'].sum()

        if total_value == 0:
            sorted_data['abc_class'] = 'C'
            return sorted_data

        sorted_data['cumulative_pct'] = (sorted_data['cumulative_value'] / total_value) * 100

        # Classify based on cumulative percentage
        a_threshold = INVENTORY_RULES["abc_analysis"]["a_class_threshold"]
        b_threshold = INVENTORY_RULES["abc_analysis"]["b_class_threshold"]

        sorted_data['abc_class'] = 'C'  # Default
        sorted_data.loc[sorted_data['cumulative_pct'] <= a_threshold, 'abc_class'] = 'A'
        sorted_data.loc[(sorted_data['cumulative_pct'] > a_threshold) &
                        (sorted_data['cumulative_pct'] <= b_threshold), 'abc_class'] = 'B'

    return sorted_data

# ===== METRICS CALCULATION =====

@st.cache_data(show_spinner=False)
def calculate_inventory_metrics(inventory_data, currency="USD"):
    """Calculate key inventory metrics"""
    if inventory_data.empty:
        return {}

    # Use currency-specific value column
    value_col = f'stock_value_{currency.lower()}'

    total_units = inventory_data['on_hand_qty'].sum()
    total_skus = len(inventory_data)
    total_value = inventory_data[value_col].sum()

    # Calculate average DIO
    dio_data = inventory_data[inventory_data['dio'] > 0]
    avg_dio = dio_data['dio'].mean() if not dio_data.empty else 0

    # Count slow-moving/obsolete items
    slow_moving_count = len(inventory_data[inventory_data['movement_class'].isin(
        ['Slow Moving', 'Very Slow Moving', 'Obsolete Risk', 'Dead Stock'])])

    # Count stock-out risks
    critical_risk_count = len(inventory_data[inventory_data['stock_out_risk'] == 'Critical'])

    currency_symbol = "$" if currency == "USD" else "€"

    return {
        f"Total Value ({currency})": {
            "value": f"{currency_symbol}{total_value:,.0f}",
            "help": f"**Business Logic:** Sum of (On-Hand Qty × Last Purchase Price) for all SKUs, converted to {currency}. Formula: Σ(stock_qty × unit_price)"
        },
        "Total Units": {
            "value": f"{int(total_units):,}",
            "help": "**Business Logic:** Sum of all on-hand quantities across all SKUs. Represents total physical units in inventory. Formula: Σ(on_hand_qty)"
        },
        "Total SKUs": {
            "value": f"{total_skus:,}",
            "help": "**Business Logic:** Count of unique material numbers (SKUs) with inventory. Each SKU represents a distinct product in the catalog. Formula: COUNT(DISTINCT sku)"
        },
        "Avg DIO": {
            "value": f"{avg_dio:.0f} days",
            "help": f"**Business Logic:** Average Days Inventory Outstanding across SKUs with movement. DIO = On-Hand Qty ÷ Daily Demand. Daily Demand = Last 12 months deliveries ÷ days since market intro (capped at 365). Excludes SKUs with zero demand. Current average: {avg_dio:.1f} days. Formula: AVG(DIO WHERE DIO > 0)"
        },
        "Slow/Obsolete SKUs": {
            "value": f"{slow_moving_count:,}",
            "help": "**Business Logic:** Count of SKUs classified as Slow Moving (DIO 60-90 days), Very Slow (90-180 days), Obsolete Risk (>180 days), or Dead Stock (no movement in 12 months). Based on movement velocity thresholds in business rules. Formula: COUNT(WHERE movement_class IN ['Slow Moving', 'Very Slow Moving', 'Obsolete Risk', 'Dead Stock'])"
        },
        "Stock-Out Risks": {
            "value": f"{critical_risk_count:,}",
            "help": "**Business Logic:** Count of SKUs with Critical stock-out risk (DIO < 7 days). These items may run out within a week based on current demand. Excludes items with zero demand. Formula: COUNT(WHERE DIO < 7 AND DIO > 0)",
            "delta": f"-{critical_risk_count}" if critical_risk_count > 0 else None,
            "delta_color": "inverse"
        }
    }

# ===== VISUALIZATIONS =====

def render_dio_distribution_chart(inventory_data, currency="USD", dio_buckets=None):
    """Render DIO distribution chart with configurable buckets"""
    if inventory_data.empty:
        return None

    value_col = f'stock_value_{currency.lower()}'

    # Use provided buckets or default
    if dio_buckets is None:
        dio_buckets = [0, 0.1, 30, 60, 90, 180, 365, float('inf')]

    # Generate labels dynamically based on bucket boundaries
    labels = []
    for i in range(len(dio_buckets) - 1):
        lower = dio_buckets[i]
        upper = dio_buckets[i + 1]

        if lower == 0 and upper <= 1:
            labels.append('No Movement')
        elif upper == float('inf'):
            labels.append(f'{int(lower)}+ days')
        else:
            labels.append(f'{int(lower)}-{int(upper)} days')

    # Create DIO buckets
    inventory_data['dio_bucket'] = pd.cut(
        inventory_data['dio'],
        bins=dio_buckets,
        labels=labels,
        include_lowest=True
    )

    dio_summary = inventory_data.groupby('dio_bucket', observed=True).agg({
        'on_hand_qty': 'sum',
        value_col: 'sum',
        'sku': 'count'
    }).reset_index()
    dio_summary.columns = ['dio_bucket', 'units', 'value', 'sku_count']

    # Create subplot with two y-axes
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=dio_summary['dio_bucket'],
            y=dio_summary['value'],
            name=f'Inventory Value ({currency})',
            marker_color=['#FF6B6B', '#06D6A0', '#4ECDC4', '#45B7D1', '#FFA07A', '#FF8C42', '#C73E1D']
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=dio_summary['dio_bucket'],
            y=dio_summary['sku_count'],
            name='SKU Count',
            mode='lines+markers',
            line=dict(color='#2C3E50', width=3),
            marker=dict(size=10)
        ),
        secondary_y=True
    )

    currency_symbol = '$' if currency == "USD" else '€'
    fig.update_xaxes(title_text="DIO Range")
    fig.update_yaxes(title_text=f"Inventory Value ({currency_symbol})", secondary_y=False)
    fig.update_yaxes(title_text="Number of SKUs", secondary_y=True)

    fig.update_layout(
        title="Inventory Distribution by DIO",
        hovermode='x unified',
        height=400
    )

    return fig

def render_movement_classification_chart(inventory_data, currency="USD"):
    """Render movement classification pie chart"""
    if inventory_data.empty or 'movement_class' not in inventory_data.columns:
        return None

    value_col = f'stock_value_{currency.lower()}'

    movement_summary = inventory_data.groupby('movement_class').agg({
        value_col: 'sum',
        'sku': 'count'
    }).reset_index()
    movement_summary.columns = ['movement_class', 'value', 'count']

    # Sort by value
    movement_summary = movement_summary.sort_values('value', ascending=False)

    # Define colors for each movement class
    color_map = {
        'Fast Moving': '#06D6A0',
        'Normal Moving': '#4ECDC4',
        'Slow Moving': '#FFD166',
        'Very Slow Moving': '#EF8354',
        'Obsolete Risk': '#F4442E',
        'Dead Stock': '#A71E2C'
    }
    colors = [color_map.get(cat, '#95A5A6') for cat in movement_summary['movement_class']]

    currency_symbol = '$' if currency == "USD" else '€'
    fig = go.Figure(data=[go.Pie(
        labels=movement_summary['movement_class'],
        values=movement_summary['value'],
        marker=dict(colors=colors),
        textposition='inside',
        textinfo='percent+label',
        hovertemplate=f'<b>%{{label}}</b><br>Value: {currency_symbol}%{{value:,.0f}}<br>Percentage: %{{percent}}<extra></extra>'
    )])

    fig.update_layout(
        title="Inventory Value by Movement Classification",
        height=400
    )

    return fig

def render_abc_analysis_chart(inventory_data, currency="USD"):
    """Render ABC analysis Pareto chart"""
    if inventory_data.empty or 'abc_class' not in inventory_data.columns:
        return None

    value_col = f'stock_value_{currency.lower()}'

    abc_summary = inventory_data.groupby('abc_class').agg({
        value_col: 'sum',
        'sku': 'count'
    }).reset_index()
    abc_summary.columns = ['abc_class', 'value', 'sku_count']

    # Ensure proper order
    abc_order = ['A', 'B', 'C']
    abc_summary['abc_class'] = pd.Categorical(abc_summary['abc_class'], categories=abc_order, ordered=True)
    abc_summary = abc_summary.sort_values('abc_class')

    # Calculate percentages
    total_value = abc_summary['value'].sum()
    abc_summary['value_pct'] = (abc_summary['value'] / total_value * 100) if total_value > 0 else 0

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=abc_summary['abc_class'],
            y=abc_summary['value'],
            name=f'Value ({currency})',
            marker_color=['#06D6A0', '#FFA07A', '#FF6B6B'],
            text=abc_summary['value_pct'].apply(lambda x: f'{x:.1f}%'),
            textposition='outside'
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=abc_summary['abc_class'],
            y=abc_summary['sku_count'],
            name='SKU Count',
            mode='lines+markers',
            line=dict(color='#2C3E50', width=3),
            marker=dict(size=12)
        ),
        secondary_y=True
    )

    currency_symbol = '$' if currency == "USD" else '€'
    fig.update_xaxes(title_text="ABC Classification")
    fig.update_yaxes(title_text=f"Inventory Value ({currency_symbol})", secondary_y=False)
    fig.update_yaxes(title_text="Number of SKUs", secondary_y=True)

    fig.update_layout(
        title="ABC Analysis (Pareto)",
        hovermode='x unified',
        height=400
    )

    return fig

def render_category_heatmap(inventory_data, currency="USD"):
    """Render category benchmarking heat map"""
    if inventory_data.empty or 'category' not in inventory_data.columns:
        return None

    value_col = f'stock_value_{currency.lower()}'

    # Calculate metrics by category
    category_summary = inventory_data.groupby('category').agg({
        'dio': 'mean',
        value_col: 'sum',
        'sku': 'count',
        'on_hand_qty': 'sum'
    }).reset_index()

    category_summary.columns = ['category', 'avg_dio', 'total_value', 'sku_count', 'total_units']

    # Add movement class distribution
    movement_dist = inventory_data.groupby(['category', 'movement_class']).size().unstack(fill_value=0)
    if 'Slow Moving' in movement_dist.columns:
        category_summary = category_summary.merge(
            movement_dist[['Slow Moving', 'Very Slow Moving', 'Obsolete Risk', 'Dead Stock']].sum(axis=1).reset_index(name='slow_count'),
            left_on='category',
            right_on='category',
            how='left'
        )
    else:
        category_summary['slow_count'] = 0

    category_summary['slow_pct'] = (category_summary['slow_count'] / category_summary['sku_count'] * 100).round(1)

    # Sort by total value
    category_summary = category_summary.sort_values('total_value', ascending=False).head(20)

    # Create heatmap
    fig = go.Figure(data=go.Heatmap(
        z=[category_summary['avg_dio'].values],
        x=category_summary['category'].values,
        y=['Avg DIO (days)'],
        colorscale='RdYlGn_r',
        text=category_summary['avg_dio'].apply(lambda x: f'{x:.0f}').values,
        texttemplate='%{text}',
        textfont={"size": 10},
        hovertemplate='Category: %{x}<br>Avg DIO: %{z:.0f} days<extra></extra>',
        colorbar=dict(title="DIO (days)")
    ))

    fig.update_layout(
        title="Category Benchmarking - Average DIO Heat Map",
        height=200,
        xaxis_title="Category",
        yaxis_title=""
    )

    return fig

# ===== SCRAP OPPORTUNITY ANALYSIS =====

def render_scrap_opportunity_analysis(inventory_data, currency="USD", scrap_threshold=730):
    """Render scrap opportunity analysis section"""
    if inventory_data.empty:
        return

    st.subheader("💡 Scrap & Obsolescence Opportunities")

    value_col = f'stock_value_{currency.lower()}'
    currency_symbol = '$' if currency == "USD" else '€'

    # Define scrap candidates based on adjustable threshold
    scrap_candidates = inventory_data[
        ((inventory_data['dio'] > scrap_threshold) | (inventory_data['dio'] == 0)) &
        (inventory_data['on_hand_qty'] > 0)
    ].copy()

    if scrap_candidates.empty:
        render_info_box(f"No items identified for scrap consideration based on current criteria (DIO > {scrap_threshold} days or no movement)", type="success")
        return

    scrap_value = scrap_candidates[value_col].sum()
    scrap_units = scrap_candidates['on_hand_qty'].sum()
    scrap_skus = len(scrap_candidates)

    # Display scrap opportunity metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Potential Scrap Value", f"{currency_symbol}{scrap_value:,.0f}",
                  help=f"Total value of items with no movement or DIO > {scrap_threshold} days")
    with col2:
        st.metric("Units to Review", f"{int(scrap_units):,}", help="Total units flagged for scrap review")
    with col3:
        st.metric("SKUs to Review", f"{scrap_skus:,}", help="Number of SKUs flagged for scrap consideration")

    # Category breakdown
    st.markdown("#### Scrap Candidates by Category")
    scrap_by_category = scrap_candidates.groupby('category').agg({
        value_col: 'sum',
        'on_hand_qty': 'sum',
        'sku': 'count'
    }).reset_index().sort_values(value_col, ascending=False)

    scrap_by_category.columns = ['Category', 'Total Value', 'Total Units', 'SKU Count']
    scrap_by_category['Total Value'] = scrap_by_category['Total Value'].apply(lambda x: f"{currency_symbol}{x:,.0f}")
    scrap_by_category['Total Units'] = scrap_by_category['Total Units'].apply(lambda x: f"{int(x):,}")

    st.dataframe(scrap_by_category, hide_index=True, width='stretch')

    # Detailed scrap list
    with st.expander("📋 Detailed Scrap Candidate List", expanded=False):
        scrap_detail = scrap_candidates[['sku', 'category', 'on_hand_qty', 'dio', 'daily_demand', 'last_purchase_price', value_col]].copy()
        scrap_detail = scrap_detail.sort_values(value_col, ascending=False)

        # Format columns
        scrap_detail['dio'] = scrap_detail['dio'].round(0).astype(int)
        scrap_detail['daily_demand'] = scrap_detail['daily_demand'].round(2)
        scrap_detail['last_purchase_price'] = scrap_detail['last_purchase_price'].round(2)
        scrap_detail[value_col] = scrap_detail[value_col].round(2)

        scrap_detail.columns = ['SKU', 'Category', 'On Hand Qty', 'DIO (days)', 'Daily Demand', 'Unit Price', f'Stock Value ({currency})']

        render_data_table(
            scrap_detail,
            max_rows=100
        )

# ===== ALTERNATE CODE ALERTS =====

def render_alternate_code_alerts(inventory_data, currency="USD"):
    """Render alerts for inventory split across alternate codes"""
    if inventory_data.empty:
        return

    st.subheader("🔄 Alternate Code Alerts")

    # Load alternate codes mapping
    alt_codes_mapping = load_alternate_codes_mapping()

    if not alt_codes_mapping['all_codes_by_family']:
        st.info("No alternate codes mapping available")
        return

    value_col = f'stock_value_{currency.lower()}'

    # Analyze inventory split
    inventory_with_current = inventory_data.copy()
    inventory_with_current['current_code'] = inventory_with_current['sku'].apply(get_current_code)
    inventory_with_current['is_old'] = inventory_with_current['sku'].apply(is_old_code)

    # Find SKU families with inventory on multiple codes
    split_inventory = []

    for current_code, family_codes in alt_codes_mapping['all_codes_by_family'].items():
        family_inventory = inventory_with_current[
            inventory_with_current['sku'].isin(family_codes)
        ]

        if len(family_inventory) > 1:  # Inventory exists on multiple codes
            total_qty = family_inventory['on_hand_qty'].sum()
            total_value = family_inventory[value_col].sum()

            # Use to_dict for vectorized conversion instead of iterrows
            codes_detail = family_inventory[['sku', 'is_old', 'on_hand_qty', value_col]].rename(
                columns={'sku': 'code', 'on_hand_qty': 'qty', value_col: 'value'}
            ).to_dict('records')

            split_inventory.append({
                'current_code': current_code,
                'num_codes': len(family_inventory),
                'total_qty': total_qty,
                'total_value': total_value,
                'codes_detail': codes_detail
            })

    if split_inventory:
        split_df = pd.DataFrame(split_inventory)
        total_split_families = len(split_df)
        total_split_value = split_df['total_value'].sum()

        col1, col2 = st.columns(2)
        with col1:
            st.metric(
                "SKU Families with Split Inventory",
                f"{total_split_families:,}",
                delta="⚠️",
                help="SKU families with inventory on both old and current material codes"
            )
        with col2:
            currency_symbol = "$" if currency == "USD" else "€"
            st.metric(
                "Total Value Split",
                f"{currency_symbol}{total_split_value:,.0f}",
                help="Total inventory value split across alternate codes"
            )

        with st.expander("⚠️ View Split Inventory Details", expanded=False):
            st.caption("**Recommendation:** Consolidate inventory by depleting old code inventory first before new code")

            display_split = split_df.sort_values('total_value', ascending=False).head(20).copy()

            display_split['Codes'] = display_split['codes_detail'].apply(
                lambda x: ', '.join([
                    f"{c['code']}{'*' if c['is_old'] else ''} ({int(c['qty'])})"
                    for c in x
                ])
            )

            display_df = pd.DataFrame({
                'Current Code': display_split['current_code'],
                'Split Across': display_split['num_codes'].astype(int),
                'Total Qty': display_split['total_qty'].astype(int),
                'Total Value': display_split['total_value'].apply(lambda x: f"{currency_symbol}{x:,.0f}"),
                'Distribution': display_split['Codes']
            })

            st.dataframe(display_df, hide_index=True, width='stretch')
            st.caption("* indicates old/obsolete code | Priority: Use old code inventory first")

    else:
        st.success("✅ No inventory split detected - all SKU families consolidated under one code")


# ===== STOCK-OUT RISK ANALYSIS =====

def render_stockout_risk_analysis(inventory_data, currency="USD"):
    """Render stock-out risk analysis section"""
    if inventory_data.empty:
        return

    st.subheader("⚠️ Stock-Out Risk Alerts")

    value_col = f'stock_value_{currency.lower()}'

    # Filter for critical and warning risks
    critical_items = inventory_data[inventory_data['stock_out_risk'] == 'Critical'].copy()
    warning_items = inventory_data[inventory_data['stock_out_risk'] == 'Warning'].copy()

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Critical Risk Items", f"{len(critical_items):,}",
                  help="Items with critically low inventory (< 7 days DIO)")

    with col2:
        st.metric("Warning Risk Items", f"{len(warning_items):,}",
                  help="Items with low inventory warning (7-14 days DIO)")

    if not critical_items.empty:
        with st.expander("🔴 Critical Risk Items", expanded=True):
            critical_detail = critical_items[['sku', 'category', 'on_hand_qty', 'dio', 'daily_demand', value_col]].copy()
            critical_detail = critical_detail.sort_values('dio')

            critical_detail['dio'] = critical_detail['dio'].round(1)
            critical_detail['daily_demand'] = critical_detail['daily_demand'].round(2)
            critical_detail[value_col] = critical_detail[value_col].round(2)

            critical_detail.columns = ['SKU', 'Category', 'On Hand Qty', 'DIO (days)', 'Daily Demand', f'Stock Value ({currency})']

            st.dataframe(critical_detail.head(20), hide_index=True, width='stretch')

# ===== TAB-SPECIFIC RENDER FUNCTIONS =====

def render_overview_health_tab(filtered_data, currency, settings):
    """Render Overview & Health tab content"""
    st.subheader("📊 Inventory Health Overview")

    # ABC Analysis & Inventory Health charts
    col1, col2, col3 = st.columns(3)

    with col1:
        abc_chart = render_abc_analysis_chart(filtered_data, currency)
        if abc_chart:
            render_chart(abc_chart, height=350)

    with col2:
        dio_chart = render_dio_distribution_chart(filtered_data, currency, settings['dio_buckets'])
        if dio_chart:
            render_chart(dio_chart, height=350)

    with col3:
        movement_chart = render_movement_classification_chart(filtered_data, currency)
        if movement_chart:
            render_chart(movement_chart, height=350)

    st.divider()

    # --- Inventory History (Monthly Snapshots) ---
    inv_month_cols = sorted([c for c in filtered_data.columns if c.startswith('inv_m_')])
    if inv_month_cols:
        st.markdown("#### 📅 Monthly Inventory Trend")
        st.caption("Historical on-hand inventory levels by month (most recent 12 months)")

        # Show data freshness indicator
        if inv_month_cols:
            most_recent_col = inv_month_cols[-1]
            parts = most_recent_col.replace('inv_m_', '').split('_')
            if len(parts) == 2:
                most_recent_month = pd.Timestamp(year=int(parts[0]), month=int(parts[1]), day=1)
                st.info(f"📊 **Data as of:** {most_recent_month.strftime('%B %Y')}")

        # View mode selection with clearer labels
        col_mode, col_sku = st.columns([1, 2])
        with col_mode:
            mode = st.selectbox(
                "View Mode",
                options=["Total Inventory", "Single SKU"],
                index=0,
                key="inv_hist_mode",
                help="View aggregate totals or drill down to a specific SKU"
            )

        if mode == "Single SKU":
            with col_sku:
                sku_list = sorted(filtered_data['sku'].dropna().unique().tolist())
                selected_sku = st.selectbox(
                    "Select SKU",
                    sku_list,
                    index=0,
                    key="inv_hist_sku",
                    help="Choose a specific SKU to view its inventory history"
                )
        else:
            selected_sku = 'All'

        # Build x-axis from column names
        def col_to_date(col):
            try:
                parts = col.replace('inv_m_', '').split('_')
                return pd.Timestamp(year=int(parts[0]), month=int(parts[1]), day=1)
            except Exception:
                return None

        x = [col_to_date(c) for c in inv_month_cols]

        if selected_sku == 'All':
            y = filtered_data[inv_month_cols].sum(axis=0).values.tolist()
            title = 'Total On-Hand Inventory by Month'
        else:
            row = filtered_data[filtered_data['sku'] == selected_sku]
            if row.empty:
                st.warning('No snapshot history available for selected SKU')
                y = [0] * len(inv_month_cols)
            else:
                y = row[inv_month_cols].iloc[0].astype(float).tolist()
            title = f'On-Hand Inventory: {selected_sku}'

        # Create enhanced chart with area fill and trend indicators
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines+markers',
            name='On Hand',
            fill='tozeroy',
            fillcolor='rgba(46, 134, 171, 0.2)',
            line=dict(color='#2E86AB', width=3),
            marker=dict(size=8, color='#2E86AB')
        ))

        # Add month-over-month change annotation for most recent month
        if len(y) >= 2 and y[-2] != 0:
            mom_change = ((y[-1] - y[-2]) / y[-2]) * 100
            change_color = '#06D6A0' if mom_change >= 0 else '#FF6B6B'
            change_text = f"+{mom_change:.1f}%" if mom_change >= 0 else f"{mom_change:.1f}%"
            fig.add_annotation(
                x=x[-1],
                y=y[-1],
                text=f"MoM: {change_text}",
                showarrow=True,
                arrowhead=2,
                arrowcolor=change_color,
                font=dict(color=change_color, size=12)
            )

        fig.update_layout(
            title=title,
            xaxis_title='Month',
            yaxis_title='On Hand Units',
            template='plotly_white',
            yaxis=dict(tickformat=','),
            hovermode='x unified'
        )
        render_chart(fig, height=350)

        # Summary stats below the chart
        if len(y) >= 2:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Current Month", f"{int(y[-1]):,}" if y[-1] else "N/A")
            with col2:
                st.metric("Previous Month", f"{int(y[-2]):,}" if y[-2] else "N/A")
            with col3:
                if y[-2] != 0:
                    mom_pct = ((y[-1] - y[-2]) / y[-2]) * 100
                    st.metric("MoM Change", f"{mom_pct:+.1f}%", delta=f"{int(y[-1] - y[-2]):,} units")
                else:
                    st.metric("MoM Change", "N/A")
            with col4:
                avg_inv = sum(y) / len(y) if y else 0
                st.metric("12-Month Avg", f"{int(avg_inv):,}")

    # Category Benchmarking
    st.markdown("#### 🏆 Category Benchmarking")
    category_heatmap = render_category_heatmap(filtered_data, currency)
    if category_heatmap:
        render_chart(category_heatmap, height=250)
    else:
        render_info_box("Unable to generate category heatmap", type="info")

def render_alerts_risks_tab(filtered_data, currency):
    """Render Alerts & Risks tab content"""
    st.subheader("⚠️ Inventory Alerts & Risk Management")

    # Alternate Code Alerts
    st.markdown("#### 🔄 Alternate Code Alerts")
    render_alternate_code_alerts(filtered_data, currency)

    st.divider()

    # Stock-Out Risk Alerts
    st.markdown("#### 📉 Stock-Out Risk Alerts")
    render_stockout_risk_analysis(filtered_data, currency)

def render_scrap_opportunities_tab(filtered_data, currency, scrap_threshold):
    """Render Scrap Opportunities tab content"""
    st.subheader("💡 Scrap & Obsolescence Opportunities")

    render_scrap_opportunity_analysis(filtered_data, currency, scrap_threshold)

def render_slow_movers_tab(filtered_data, currency):
    """Render Slow Movers tab content"""
    st.subheader("🐌 Slow-Moving Items Analysis")
    st.caption("Items with low turnover velocity requiring attention for markdown or scrap consideration")

    value_col = f'stock_value_{currency.lower()}'
    currency_symbol = '$' if currency == 'USD' else '€'

    slow_movers = filtered_data[
        filtered_data['movement_class'].isin(['Slow Moving', 'Very Slow Moving', 'Obsolete Risk', 'Dead Stock'])
    ].copy()

    if not slow_movers.empty:
        # Summary metrics at top
        total_slow_value = slow_movers[value_col].sum()
        total_slow_units = slow_movers['on_hand_qty'].sum()
        total_slow_skus = len(slow_movers)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Slow-Moving SKUs", f"{total_slow_skus:,}")
        with col2:
            st.metric("Total Units", f"{int(total_slow_units):,}")
        with col3:
            st.metric("Total Value", f"{currency_symbol}{total_slow_value:,.0f}")
        with col4:
            avg_dio = slow_movers['dio'].mean()
            st.metric("Avg DIO", f"{int(avg_dio):,} days")

        st.divider()

        slow_movers = slow_movers.sort_values(value_col, ascending=False).head(50)

        display_cols = ['sku', 'category', 'abc_class', 'on_hand_qty', 'dio', 'daily_demand',
                       'last_purchase_price', value_col, 'movement_class', 'stock_out_risk']
        available_cols = [col for col in display_cols if col in slow_movers.columns]

        result = slow_movers[available_cols].copy()

        # Apply professional formatting - integers with commas, currency with $
        result['on_hand_qty'] = result['on_hand_qty'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
        result['dio'] = result['dio'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
        result['daily_demand'] = result['daily_demand'].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "N/A")
        result['last_purchase_price'] = result['last_purchase_price'].apply(lambda x: f"{currency_symbol}{x:,.2f}" if pd.notna(x) else "N/A")
        result[value_col] = result[value_col].apply(lambda x: f"{currency_symbol}{x:,.0f}" if pd.notna(x) else "N/A")

        # Rename columns for display
        col_names = {
            'sku': 'SKU',
            'category': 'Category',
            'abc_class': 'ABC Class',
            'on_hand_qty': 'On Hand Qty',
            'dio': 'DIO (days)',
            'daily_demand': 'Daily Demand',
            'last_purchase_price': 'Unit Price',
            value_col: f'Stock Value ({currency})',
            'movement_class': 'Movement Class',
            'stock_out_risk': 'Risk Level'
        }
        result = result.rename(columns=col_names)

        render_data_table(
            result,
            max_rows=50
        )
    else:
        render_info_box("No slow-moving items found in current selection", type="success")

def render_detailed_records_tab(filtered_data, currency):
    """Render Detailed Records tab content"""
    st.subheader("📋 Detailed Inventory Records")
    st.caption("Complete inventory listing with all metrics - click column headers to sort")

    value_col = f'stock_value_{currency.lower()}'
    currency_symbol = '$' if currency == 'USD' else '€'

    display_columns = ['sku', 'category', 'abc_class', 'on_hand_qty', 'in_transit_qty',
                      'daily_demand', 'dio', 'movement_class', 'stock_out_risk',
                      'last_purchase_price', value_col]
    available_cols = [col for col in display_columns if col in filtered_data.columns]

    detail_data = filtered_data[available_cols].copy()

    # Apply professional formatting - integers with commas, currency with $
    if 'on_hand_qty' in detail_data.columns:
        detail_data['on_hand_qty'] = detail_data['on_hand_qty'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
    if 'in_transit_qty' in detail_data.columns:
        detail_data['in_transit_qty'] = detail_data['in_transit_qty'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
    if 'dio' in detail_data.columns:
        detail_data['dio'] = detail_data['dio'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
    if 'daily_demand' in detail_data.columns:
        detail_data['daily_demand'] = detail_data['daily_demand'].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "N/A")
    if 'last_purchase_price' in detail_data.columns:
        detail_data['last_purchase_price'] = detail_data['last_purchase_price'].apply(lambda x: f"{currency_symbol}{x:,.2f}" if pd.notna(x) else "N/A")
    if value_col in detail_data.columns:
        detail_data[value_col] = detail_data[value_col].apply(lambda x: f"{currency_symbol}{x:,.0f}" if pd.notna(x) else "N/A")

    # Rename columns
    col_names = {
        'sku': 'SKU',
        'category': 'Category',
        'abc_class': 'ABC Class',
        'on_hand_qty': 'On Hand',
        'in_transit_qty': 'In Transit',
        'daily_demand': 'Daily Demand',
        'dio': 'DIO (days)',
        'movement_class': 'Movement',
        'stock_out_risk': 'Risk',
        'last_purchase_price': 'Unit Price',
        value_col: f'Value ({currency})'
    }
    detail_data = detail_data.rename(columns=col_names)

    render_data_table(
        detail_data,
        max_rows=100
    )

# ===== MAIN RENDER FUNCTION =====

def render_inventory_page(inventory_data):
    """Main inventory page render function with tabbed interface"""

    # Page header
    render_page_header(
        "Inventory Management",
        icon="📦",
        subtitle="Inventory levels, turnover analysis, slow-moving/obsolescence tracking, and ABC analysis"
    )

    if inventory_data.empty:
        st.warning("No inventory data available")
        return

    # Render settings sidebar
    settings = render_inventory_settings_sidebar()
    currency = settings['currency']
    scrap_threshold = settings['scrap_threshold']

    # Add calculated columns - currency conversion
    # IMPORTANT: Convert from actual purchase currency to target currency
    # Handle cases where currency column might be missing or NaN
    if 'currency' not in inventory_data.columns:
        inventory_data['currency'] = 'USD'
    else:
        inventory_data['currency'] = inventory_data['currency'].fillna('USD')

    inventory_data['stock_value_usd'] = inventory_data.apply(
        lambda row: row['on_hand_qty'] * convert_currency(
            row['last_purchase_price'],
            row['currency'],  # Source currency from data
            'USD'  # Target currency
        ),
        axis=1
    )
    inventory_data['stock_value_eur'] = inventory_data.apply(
        lambda row: row['on_hand_qty'] * convert_currency(
            row['last_purchase_price'],
            row['currency'],  # Source currency from data
            'EUR'  # Target currency
        ),
        axis=1
    )

    # Apply business rules for classification
    inventory_data['movement_class'] = inventory_data['dio'].apply(get_movement_classification)
    inventory_data['stock_out_risk'] = inventory_data['dio'].apply(get_stock_out_risk_level)

    # ABC Classification
    inventory_data = calculate_abc_classification(inventory_data, settings['use_count_based_abc'])

    # Render filters
    filters_config = get_inventory_filters(inventory_data)
    filter_values = render_filter_section(filters_config)

    # Apply filters
    filtered_data = apply_inventory_filters(inventory_data, filter_values, settings)

    if filtered_data.empty:
        st.info("No data matches the selected filters")
        return

    # === EXPORT BUTTON ===
    export_data = prepare_export_data(
        filtered_data,
        settings['export_section'],
        currency,
        scrap_threshold,
        settings['scrap_days_threshold']
    )

    if not export_data.empty:
        excel_file = create_excel_export(export_data, settings['export_section'], currency)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Inventory_{settings['export_section'].replace(' ', '_')}_{timestamp}.xlsx"

        st.sidebar.download_button(
            label="📥 Download Excel",
            data=excel_file,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width='stretch',
            key="download_excel"
        )
        st.sidebar.caption(f"📊 {len(export_data):,} rows ready to export")
    else:
        st.sidebar.info("No data available for selected export option")

    # Calculate and display metrics (shown at top level, above tabs)
    metrics = calculate_inventory_metrics(filtered_data, currency)
    render_kpi_row(metrics)

    st.divider()

    # === SIMPLIFIED 3-TAB INTERFACE ===
    # Tab 1: Health Dashboard (Overview + Alerts combined)
    # Tab 2: Action Items (Scrap + Slow Movers combined)
    # Tab 3: Detailed Records

    tab1, tab2, tab3 = st.tabs([
        "📊 Health Dashboard",
        "⚠️ Action Items",
        "📋 Detailed Records"
    ])

    with tab1:
        # Combined Overview + Alerts
        render_overview_health_tab(filtered_data, currency, settings)

        st.divider()
        st.subheader("🚨 Inventory Alerts")
        render_alerts_risks_tab(filtered_data, currency)

    with tab2:
        # Combined Action Items: Scrap + Slow Movers side by side
        st.subheader("💡 Scrap Opportunities")
        st.caption("Items exceeding scrap threshold - potential write-off candidates")
        render_scrap_opportunities_tab(filtered_data, currency, scrap_threshold)

        st.divider()

        st.subheader("🐌 Slow-Moving Inventory")
        st.caption("Low velocity items requiring markdown or liquidation review")
        render_slow_movers_tab(filtered_data, currency)

    with tab3:
        render_detailed_records_tab(filtered_data, currency)

    # === DATA FRESHNESS FOOTER ===
    st.divider()
    # Show data freshness info
    inv_month_cols = sorted([c for c in inventory_data.columns if c.startswith('inv_m_')])
    if inv_month_cols:
        most_recent_col = inv_month_cols[-1]
        parts = most_recent_col.replace('inv_m_', '').split('_')
        if len(parts) == 2:
            most_recent_month = pd.Timestamp(year=int(parts[0]), month=int(parts[1]), day=1)
            st.caption(f"📅 Inventory data includes monthly snapshots through {most_recent_month.strftime('%B %Y')}")
    st.caption(f"📊 Showing {len(filtered_data):,} SKUs | Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
