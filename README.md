# 📦 Supply Chain Dashboard

This project is a Streamlit-based web application for visualizing and analyzing supply chain data, focusing on Service Level, Backorders, and Inventory Management.

## How to Run

1.  **Install Dependencies**:
    Open a terminal in the project directory and run the following command to install all required libraries:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run the Dashboard**:
    Execute the following command in your terminal:
    ```bash
    streamlit run dashboard.py
    ```

3.  **View the Dashboard**:
    Open your web browser and navigate to the local URL provided by Streamlit (usually `http://localhost:8501`).

## Troubleshooting Guide

This project includes a suite of standalone Python scripts designed to diagnose common data issues. If the dashboard shows unexpected results (e.g., empty reports, missing data), run the appropriate debugger from your terminal.

---

### Problem: "My Inventory report is empty or shows 0 stock."

**Debugger:** `python inventory_validator.py`

**What it does:**
*   Checks if `INVENTORY.csv` is missing required columns (`Material Number`, `POP Actual Stock Qty`).
*   Verifies that stock quantities are valid numbers and handles comma formatting.
*   Simulates the stock aggregation logic to confirm totals.

---

### Problem: "My Service Level report is empty or missing data."

**Debugger:** `python debug_service_level.py`

**What it does:**
*   Traces a single Sales Order and SKU from `DELIVERIES.csv` through the entire data pipeline.
*   Verifies joins to `ORDERS.csv` and `Master Data.csv`.
*   Shows the exact `order_date`, `ship_date`, and `due_date` calculations.
*   Pinpoints the exact step where a delivery line might be dropped.

**Helper Script:** `python find_delivery_samples.py`
*   Use this first to get a list of valid Sales Order/SKU combinations from your `DELIVERIES.csv` to use in the main service level debugger.

---

### Problem: "My Backorder report is empty, but I know there are backorders."

**Debugger:** `python debug_backorder_loading.py`

**What it does:**
*   Analyzes the join between backordered items in `ORDERS.csv` and the `Master Data.csv`.
*   Explicitly reports how many backordered SKUs could not find a match in the master data, which is the most common reason for this report being empty.

---

### Problem: "I see 'Unknown' for product names or categories on the Backorder report."

**Debugger:** `python debug_unknown_products.py`

**What it does:**
*   Identifies all backordered items.
*   Performs a merge with the master data and generates an Excel report (`unknown_product_name_report.xlsx`) listing every single backordered SKU that does not have a corresponding entry in `Master Data.csv`.