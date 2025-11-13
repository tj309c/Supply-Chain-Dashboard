"""
Helper module to read CSV files from either disk or Streamlit uploaded buffers.
"""
import pandas as pd
import os
import streamlit as st


def get_file_source(file_key: str, file_path: str):
    """
    Returns a file-like object or path for reading a CSV.
    
    Priority:
    1. If uploaded file exists in session_state.uploaded_files, use that buffer
    2. Otherwise, use the file_path (disk or env var)
    
    Args:
        file_key: key in st.session_state.uploaded_files (e.g., 'orders', 'deliveries')
        file_path: fallback file path
    
    Returns:
        tuple: (source, is_uploaded) where source is file-like or path, is_uploaded is bool
    """
    uploaded_files = st.session_state.get('uploaded_files', {})
    
    if file_key in uploaded_files:
        # Return the uploaded buffer
        return uploaded_files[file_key], True
    elif os.path.isfile(os.path.abspath(file_path)):
        # Return the file path
        return file_path, False
    else:
        # File not found
        return None, False


def safe_read_csv(file_key: str, file_path: str, **kwargs):
    """
    Safely read a CSV from either uploaded buffer or disk.
    
    Args:
        file_key: key in st.session_state.uploaded_files
        file_path: fallback file path
        **kwargs: passed to pd.read_csv()
    
    Returns:
        pd.DataFrame or raises an exception
    """
    source, is_uploaded = get_file_source(file_key, file_path)
    
    if source is None:
        raise FileNotFoundError(f"File not found: {file_path} (and no uploaded file)")
    
    # pandas.read_csv handles both file paths and file-like objects (BytesIO, etc.)
    return pd.read_csv(source, **kwargs)
