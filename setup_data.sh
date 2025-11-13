#!/bin/bash
# setup_data.sh - Helper script to set environment variables and run Streamlit
# Usage: bash setup_data.sh /path/to/data/folder

if [ -z "$1" ]; then
    echo "Usage: bash setup_data.sh /path/to/data/folder"
    echo ""
    echo "Example:"
    echo "  bash setup_data.sh ~/my-supply-chain-data"
    echo ""
    echo "This will:"
    echo "  1. Check for ORDERS.csv, DELIVERIES.csv, Master Data.csv, INVENTORY.csv"
    echo "  2. Set environment variables to point to those files"
    echo "  3. Start Streamlit"
    exit 1
fi

DATA_FOLDER="$1"

# Verify folder exists
if [ ! -d "$DATA_FOLDER" ]; then
    echo "ERROR: Folder not found: $DATA_FOLDER"
    exit 1
fi

# Check for required files
echo "Checking for CSV files in: $DATA_FOLDER"
MISSING=0

if [ ! -f "$DATA_FOLDER/ORDERS.csv" ]; then
    echo "  ✗ ORDERS.csv NOT FOUND"
    MISSING=$((MISSING + 1))
else
    echo "  ✓ ORDERS.csv found"
fi

if [ ! -f "$DATA_FOLDER/DELIVERIES.csv" ]; then
    echo "  ✗ DELIVERIES.csv NOT FOUND"
    MISSING=$((MISSING + 1))
else
    echo "  ✓ DELIVERIES.csv found"
fi

if [ ! -f "$DATA_FOLDER/Master Data.csv" ]; then
    echo "  ✗ Master Data.csv NOT FOUND"
    MISSING=$((MISSING + 1))
else
    echo "  ✓ Master Data.csv found"
fi

if [ ! -f "$DATA_FOLDER/INVENTORY.csv" ]; then
    echo "  ✗ INVENTORY.csv NOT FOUND"
    MISSING=$((MISSING + 1))
else
    echo "  ✓ INVENTORY.csv found"
fi

if [ $MISSING -gt 0 ]; then
    echo ""
    echo "ERROR: $MISSING file(s) missing. Cannot proceed."
    exit 1
fi

echo ""
echo "All files found! Starting Streamlit..."
echo ""

# Set environment variables and run Streamlit
export ORDERS_FILE_PATH="$DATA_FOLDER/ORDERS.csv"
export DELIVERIES_FILE_PATH="$DATA_FOLDER/DELIVERIES.csv"
export MASTER_DATA_FILE_PATH="$DATA_FOLDER/Master Data.csv"
export INVENTORY_FILE_PATH="$DATA_FOLDER/INVENTORY.csv"

echo "Environment variables set:"
echo "  ORDERS_FILE_PATH=$ORDERS_FILE_PATH"
echo "  DELIVERIES_FILE_PATH=$DELIVERIES_FILE_PATH"
echo "  MASTER_DATA_FILE_PATH=$MASTER_DATA_FILE_PATH"
echo "  INVENTORY_FILE_PATH=$INVENTORY_FILE_PATH"
echo ""

python -m streamlit run dashboard.py
