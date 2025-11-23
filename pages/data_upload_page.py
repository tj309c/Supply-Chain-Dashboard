"""
Data Upload & Management Page
Allow users to upload their own data files with validation and template export
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys
from io import BytesIO

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ui_components import render_page_header, render_info_box

# ===== FILE CONFIGURATIONS =====

FILE_CONFIGS = {
    "ORDERS.csv": {
        "display_name": "Orders Data",
        "required": True,
        "description": "Customer orders and backorder tracking",
        "required_columns": [
            "Orders Detail - Order Document Number",
            "Item - SAP Model Code",
            "Order Creation Date: Date",
            "Original Customer Name",
            "Orders - TOTAL Orders Qty",
            "Orders - TOTAL To Be Delivered Qty",
            "Orders - TOTAL Cancelled Qty"
        ],
        "sample_data": {
            "Orders Detail - Order Document Number": ["SO12345", "SO12346"],
            "Item - SAP Model Code": ["Z99RE23     RE0051", "ZECRE23     RE0007"],
            "Order Creation Date: Date": ["1/15/24", "2/20/24"],
            "Original Customer Name": ["Customer A", "Customer B"],
            "Orders - TOTAL Orders Qty": [100, 50],
            "Orders - TOTAL To Be Delivered Qty": [25, 10],
            "Orders - TOTAL Cancelled Qty": [0, 0]
        }
    },
    "DELIVERIES.csv": {
        "display_name": "Deliveries Data",
        "required": True,
        "description": "Shipment and delivery records",
        "required_columns": [
            "Deliveries Detail - Order Document Number",
            "Item - SAP Model Code",
            "Delivery Creation Date: Date",
            "Deliveries - TOTAL Goods Issue Qty"
        ],
        "sample_data": {
            "Deliveries Detail - Order Document Number": ["SO12345", "SO12346"],
            "Item - SAP Model Code": ["Z99RE23     RE0051", "ZECRE23     RE0007"],
            "Delivery Creation Date: Date": ["1/20/24", "2/25/24"],
            "Deliveries - TOTAL Goods Issue Qty": [75, 40]
        }
    },
    "INVENTORY.csv": {
        "display_name": "Inventory Data",
        "required": True,
        "description": "Real-time stock levels",
        "required_columns": [
            "Storage Location",
            "Material Number",
            "Free Qt",
            "Last Purchase Price"
        ],
        "sample_data": {
            "Storage Location": ["Z109", "Z101"],
            "Material Number": ["Z99RE23     RE0051", "ZECRE23     RE0007"],
            "Free Qt": [500, 250],
            "Last Purchase Price": [12.50, 25.00]
        }
    },
    "Master Data.csv": {
        "display_name": "Master Data",
        "required": True,
        "description": "Product catalog with SKU metadata",
        "required_columns": [
            "Material Number",
            "PLM: Level Classification 4",
            "Activation Date (Code)",
            "PLM: PLM Current Status",
            "PLM: Expiration Date"
        ],
        "sample_data": {
            "Material Number": ["Z99RE23     RE0051", "ZECRE23     RE0007"],
            "PLM: Level Classification 4": ["Category A", "Category B"],
            "Activation Date (Code)": ["1/1/23", "6/15/23"],
            "PLM: PLM Current Status": ["Active", "Active"],
            "PLM: Expiration Date": ["20251231", "20261231"]
        }
    },
    "ALTERNATE_CODES.csv": {
        "display_name": "Alternate Codes",
        "required": False,
        "description": "SKU alternate/legacy code mappings",
        "required_columns": [
            "SAP Material Current",
            "SAP Material Last Old Code",
            "SAP Material Original Code"
        ],
        "sample_data": {
            "SAP Material Current": ["Z99RE23     RE0051", "ZECRE23     RE0007"],
            "SAP Material Last Old Code": ["ZRBRE23     RE0015", "ZECRI21     RI0024"],
            "SAP Material Original Code": ["", ""]
        }
    }
}

# ===== VALIDATION FUNCTIONS =====

def validate_file(df, file_name):
    """
    Validate uploaded file against expected schema

    Returns:
        (is_valid, errors_list)
    """
    errors = []
    config = FILE_CONFIGS.get(file_name)

    if not config:
        return False, [f"Unknown file type: {file_name}"]

    # Check required columns
    required_cols = config["required_columns"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")

    # File-specific validations
    if file_name == "ORDERS.csv" and not errors:
        # Check for duplicates
        if 'Orders Detail - Order Document Number' in df.columns and 'Item - SAP Model Code' in df.columns:
            duplicates = df.duplicated(subset=['Orders Detail - Order Document Number', 'Item - SAP Model Code'])
            if duplicates.any():
                errors.append(f"Found {duplicates.sum()} duplicate order line items")

        # Check numeric fields
        numeric_cols = ['Orders - TOTAL Orders Qty', 'Orders - TOTAL To Be Delivered Qty', 'Orders - TOTAL Cancelled Qty']
        for col in numeric_cols:
            if col in df.columns:
                try:
                    pd.to_numeric(df[col], errors='raise')
                except:
                    errors.append(f"Column '{col}' contains non-numeric values")

    elif file_name == "DELIVERIES.csv" and not errors:
        # Check numeric fields
        if 'Deliveries - TOTAL Goods Issue Qty' in df.columns:
            try:
                pd.to_numeric(df['Deliveries - TOTAL Goods Issue Qty'], errors='raise')
            except:
                errors.append("'Deliveries - TOTAL Goods Issue Qty' contains non-numeric values")

    elif file_name == "INVENTORY.csv" and not errors:
        # Check for negative quantities
        if 'Free Qt' in df.columns:
            try:
                qty = pd.to_numeric(df['Free Qt'], errors='coerce')
                if (qty < 0).any():
                    errors.append("Found negative quantities in 'Free Qt'")
            except:
                errors.append("'Free Qt' contains non-numeric values")

        # Check for duplicates
        if 'Storage Location' in df.columns and 'Material Number' in df.columns:
            duplicates = df.duplicated(subset=['Storage Location', 'Material Number'])
            if duplicates.any():
                errors.append(f"Found {duplicates.sum()} duplicate SKU+Location combinations")

    elif file_name == "Master Data.csv" and not errors:
        # Check for duplicate Material Numbers
        if 'Material Number' in df.columns:
            duplicates = df.duplicated(subset=['Material Number'])
            if duplicates.any():
                errors.append(f"Found {duplicates.sum()} duplicate Material Numbers")

    elif file_name == "ALTERNATE_CODES.csv" and not errors:
        # Check that current code is not blank
        if 'SAP Material Current' in df.columns:
            blanks = df['SAP Material Current'].isna() | (df['SAP Material Current'].str.strip() == '')
            if blanks.any():
                errors.append(f"Found {blanks.sum()} rows with blank current codes")

    is_valid = len(errors) == 0
    return is_valid, errors


def create_template(file_name):
    """Create a CSV template for download"""
    config = FILE_CONFIGS.get(file_name)

    if not config:
        return None

    # Create DataFrame with sample data
    df = pd.DataFrame(config["sample_data"])

    # Add instruction row as first row (commented)
    instruction_row = {col: f"<{col.split(' ')[-1]}>" for col in df.columns}
    instruction_df = pd.DataFrame([instruction_row])

    # Combine
    template_df = pd.concat([instruction_df, df], ignore_index=True)

    # Convert to CSV
    output = BytesIO()
    template_df.to_csv(output, index=False)
    output.seek(0)

    return output


# ===== MAIN RENDER FUNCTION =====

def render_data_upload_page():
    """Main data upload page render function"""

    render_page_header(
        "Data Upload & Management",
        icon="📤",
        subtitle="Upload your own data files with validation and template export"
    )

    # Initialize session state for upload tracking
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = {}

    if 'upload_history' not in st.session_state:
        st.session_state.upload_history = []

    # === INSTRUCTIONS ===
    with st.expander("📖 Instructions", expanded=False):
        st.markdown("""
        **How to Upload Data:**

        1. **Download Template**: Click the "Download Template" button for each file type
        2. **Fill Template**: Open the template in Excel and replace sample data with your data
        3. **Upload File**: Click "Browse files" to upload your completed file
        4. **Validate**: The system will automatically validate your data
        5. **Refresh**: Click "Refresh Data" in the sidebar to reload the dashboard with your data

        **Important Notes:**
        - Required files must be uploaded for the dashboard to work
        - Optional files enhance functionality but are not required
        - All dates should follow the format shown in templates
        - Do not modify column headers in the templates
        - File size limit: 200MB per file
        """)

    st.divider()

    # === REQUIRED FILES SECTION ===
    st.subheader("📥 Required Data Files")
    st.caption("All required files must be uploaded for the dashboard to function")

    required_files = {k: v for k, v in FILE_CONFIGS.items() if v["required"]}

    for file_name, config in required_files.items():
        with st.expander(f"{'✅' if file_name in st.session_state.uploaded_files else '⭕'} {config['display_name']}", expanded=True):
            st.caption(config["description"])

            col1, col2 = st.columns([3, 1])

            with col1:
                uploaded_file = st.file_uploader(
                    f"Upload {file_name}",
                    type=['csv'],
                    key=f"upload_{file_name}",
                    label_visibility="collapsed"
                )

            with col2:
                # Template download button
                template = create_template(file_name)
                if template:
                    st.download_button(
                        label="📥 Template",
                        data=template,
                        file_name=f"TEMPLATE_{file_name}",
                        mime="text/csv",
                        width='stretch'
                    )

            # Process uploaded file
            if uploaded_file is not None:
                try:
                    # Read file
                    df = pd.read_csv(uploaded_file)

                    # Validate
                    is_valid, errors = validate_file(df, file_name)

                    if is_valid:
                        # Store in session state
                        st.session_state.uploaded_files[file_name] = {
                            'data': df,
                            'timestamp': datetime.now(),
                            'rows': len(df),
                            'status': 'valid'
                        }

                        # Add to history
                        st.session_state.upload_history.append({
                            'file': file_name,
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'status': 'Success',
                            'rows': len(df)
                        })

                        st.success(f"✅ File validated successfully! Loaded {len(df):,} rows")

                            with st.expander("Preview Data (first 5 rows)", expanded=False):
                                st.dataframe(df.head(), width='stretch')

                    else:
                        st.error("❌ Validation failed:")
                        for error in errors:
                            st.error(f"  • {error}")

                        # Add to history
                        st.session_state.upload_history.append({
                            'file': file_name,
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'status': 'Failed',
                            'rows': 0
                        })

                except Exception as e:
                    st.error(f"❌ Error reading file: {str(e)}")

            # Show current status
            elif file_name in st.session_state.uploaded_files:
                file_info = st.session_state.uploaded_files[file_name]
                st.info(f"ℹ️ Currently loaded: {file_info['rows']:,} rows (uploaded {file_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')})")

    st.divider()

    # === OPTIONAL FILES SECTION ===
    st.subheader("📦 Optional Data Files")
    st.caption("Optional files that enhance dashboard functionality")

    optional_files = {k: v for k, v in FILE_CONFIGS.items() if not v["required"]}

    for file_name, config in optional_files.items():
        with st.expander(f"{'✅' if file_name in st.session_state.uploaded_files else '⭕'} {config['display_name']}", expanded=False):
            st.caption(config["description"])

            col1, col2 = st.columns([3, 1])

            with col1:
                uploaded_file = st.file_uploader(
                    f"Upload {file_name}",
                    type=['csv'],
                    key=f"upload_{file_name}",
                    label_visibility="collapsed"
                )

            with col2:
                # Template download button
                template = create_template(file_name)
                if template:
                    st.download_button(
                        label="📥 Template",
                        data=template,
                        file_name=f"TEMPLATE_{file_name}",
                        mime="text/csv",
                        width='stretch'
                    )

            # Process uploaded file (same logic as required files)
            if uploaded_file is not None:
                try:
                    df = pd.read_csv(uploaded_file)
                    is_valid, errors = validate_file(df, file_name)

                    if is_valid:
                        st.session_state.uploaded_files[file_name] = {
                            'data': df,
                            'timestamp': datetime.now(),
                            'rows': len(df),
                            'status': 'valid'
                        }

                        st.session_state.upload_history.append({
                            'file': file_name,
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'status': 'Success',
                            'rows': len(df)
                        })

                        st.success(f"✅ File validated successfully! Loaded {len(df):,} rows")

                        with st.expander("Preview Data (first 5 rows)", expanded=False):
                               st.dataframe(df.head(), width='stretch')

                    else:
                        st.error("❌ Validation failed:")
                        for error in errors:
                            st.error(f"  • {error}")

                        st.session_state.upload_history.append({
                            'file': file_name,
                            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            'status': 'Failed',
                            'rows': 0
                        })

                except Exception as e:
                    st.error(f"❌ Error reading file: {str(e)}")

            elif file_name in st.session_state.uploaded_files:
                file_info = st.session_state.uploaded_files[file_name]
                st.info(f"ℹ️ Currently loaded: {file_info['rows']:,} rows (uploaded {file_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')})")

    st.divider()

    # === DATA STATUS DASHBOARD ===
    st.subheader("📊 Data Status")

    if st.session_state.uploaded_files:
        status_data = []
        for file_name, file_info in st.session_state.uploaded_files.items():
            status_data.append({
                'File': FILE_CONFIGS[file_name]['display_name'],
                'Rows': f"{file_info['rows']:,}",
                'Last Updated': file_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                'Status': '✅ Valid'
            })

        status_df = pd.DataFrame(status_data)
        st.dataframe(status_df, hide_index=True, width='stretch')
    else:
        st.info("No files uploaded yet")

    st.divider()

    # === ACTIONS ===
    st.subheader("⚙️ Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
            if st.button("🔄 Refresh Dashboard", width='stretch', help="Clear cache and reload dashboard with uploaded data"):
            st.cache_data.clear()
            st.success("✅ Cache cleared! Navigate to any page to see your uploaded data.")

    with col2:
            if st.button("🗑️ Clear All Uploads", width='stretch', help="Remove all uploaded files"):
            st.session_state.uploaded_files = {}
            st.success("✅ All uploads cleared!")
            st.rerun()

    with col3:
            if st.button("📥 Download All Templates", width='stretch', help="Download all templates as a ZIP"):
            st.info("Feature coming soon: Bulk template download")

    st.divider()

    # === UPLOAD HISTORY ===
    st.subheader("📜 Upload History")
    st.caption("Last 10 upload attempts")

    if st.session_state.upload_history:
        history_df = pd.DataFrame(st.session_state.upload_history[-10:])
        history_df = history_df[['timestamp', 'file', 'status', 'rows']]
        history_df.columns = ['Timestamp', 'File', 'Status', 'Rows']
            st.dataframe(history_df, hide_index=True, width='stretch')
    else:
        st.info("No upload history yet")

    # === FOOTER NOTES ===
    st.divider()
    st.caption("**Note:** Uploaded data is stored in session state and will be cleared when the browser session ends. For permanent data changes, update the source CSV files in the project directory.")
