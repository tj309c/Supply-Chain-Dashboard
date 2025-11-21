# EssilorLuxottica POP Supply Chain Dashboard

> Comprehensive End-to-End Supply Chain Analytics Platform

## Overview

This project delivers a production-ready supply chain analytics dashboard for **EssilorLuxottica's Point-of-Purchase (POP) Supply Chain**. The platform provides real-time visibility across the entire supply chain lifecycle—from vendor purchase orders and inbound logistics to inventory management, order fulfillment, and delivery performance.

Built with Python and Streamlit, this dashboard empowers supply chain stakeholders to monitor key performance indicators (KPIs), identify bottlenecks, and make data-driven decisions across the end-to-end POP supply chain network.

## 🎯 Project Goals

- **Unified Visibility**: Single source of truth for POP supply chain operations
- **Real-Time Analytics**: Live tracking of service levels, backorders, and inventory positions
- **Performance Monitoring**: End-to-end KPI tracking from procurement to delivery
- **Data-Driven Decision Making**: Actionable insights for supply chain optimization
- **Scalable Architecture**: Modular design supporting future enhancements

## 🏗️ Architecture

### Core Components

```
├── dashboard.py           # Main Streamlit application entry point
├── data_loader.py        # Data ingestion and transformation pipeline
├── file_loader.py        # CSV file handling and validation
├── utils.py              # Shared utilities and helper functions
├── test_data_loader.py   # Unit tests for data loading logic
└── inventory_validator.py # Data quality validation tools
```

### Data Sources

The dashboard integrates multiple data streams:

- **ORDERS.csv**: Customer orders and backorder tracking
- **DELIVERIES.csv**: Shipment and delivery records
- **INVENTORY.csv**: Real-time stock levels across distribution centers
- **Master Data.csv**: Product catalog with SKU metadata
- **DOMESTIC INBOUND.csv**: Inbound logistics and receiving data
- **Domestic Vendor POs.csv**: Purchase order tracking

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip package manager

### Installation

1. **Clone the repository**
   ```bash
   cd c:\Users\603506\Desktop\Trevor_Python\POP_Supply_Chain
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify data files**

   Ensure all required CSV files are present in the `Data/` directory or root folder.

4. **Launch the dashboard**
   ```bash
   streamlit run dashboard.py
   ```

5. **Access the application**

   Open your browser to `http://localhost:8501`

## 📊 Features

## 🪟 Windows startup helpers (optional)

For Windows users there are two helper scripts in the repo to simplify running the dashboard and managing virtual environments:

- `start_dashboard.bat` – CMD helper for quick runs.
   - Install requirements:
      ```cmd
      start_dashboard.bat install
      ```
   - Run dashboard (headless):
      ```cmd
      start_dashboard.bat
      ```
   - Run in dev mode (not headless):
      ```cmd
      start_dashboard.bat dev
      ```

- `start_dashboard.ps1` – PowerShell helper with venv/conda support. Examples (use ExecutionPolicy Bypass for one-off runs):
   - Install requirements:
      ```powershell
      pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Install
      ```
   - Run (headless):
      ```powershell
      pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run
      ```
   - Auto-create and use a local `.venv` (installing requirements into it):
      ```powershell
      pwsh -ExecutionPolicy Bypass -File .\start_dashboard.ps1 -Action Run -AutoActivateVenv
      ```

Notes:
- `-ExecutionPolicy Bypass` lets you run the script even when PowerShell's policy blocks unsigned scripts (one-off only).
- Both helpers export environment variables used by the app. You can override data paths via `ORDERS_FILE_PATH`, `DELIVERIES_FILE_PATH`, `MASTER_DATA_FILE_PATH`, `INVENTORY_FILE_PATH`.

Developer batch helper
----------------------

We also provide a dedicated developer CMD helper `start_dashboard_dev.bat` that is focused on local development and convenience. Its behaviour:

- Creates and activates a local `.venv` (if one does not exist) when you run `install`.
- Installs `requirements.txt` into `.venv`.
- Activates `.venv` if present and launches Streamlit in dev mode (opens browser / not headless).

Examples:

```cmd
REM Create .venv and install requirements
start_dashboard_dev.bat install

REM Run development server (uses .venv if present)
start_dashboard_dev.bat

REM Run with a named conda env instead
start_dashboard_dev.bat conda=devenv

REM Override paths inline
start_dashboard_dev.bat env ORDERS=data\ORDERS.csv MASTER="C:\custom\Master Data.csv"
```

### 1. Service Level Analytics
- On-time delivery performance tracking
- Order cycle time analysis
- Customer delivery commitment monitoring
- Historical trend visualization

### 2. Backorder Management
- Real-time backorder visibility by SKU
- Aging analysis of open backorders
- Product category breakdown
- Root cause identification

### 3. Inventory Intelligence
- Current stock levels across all locations
- Inventory turnover metrics
- Stock-out risk analysis
- Replenishment recommendations

### 4. Inbound Logistics
- Vendor PO tracking
- Receipt performance monitoring
- Lead time analysis
- Supplier performance metrics

## 🛠️ Development

### Technology Stack

- **Frontend**: Streamlit (interactive web UI)
- **Data Processing**: Pandas (ETL and analytics)
- **Visualization**: Plotly (interactive charts)
- **Numerical Computing**: NumPy
- **Export**: XlsxWriter (Excel report generation)

### Project Structure

```
POP_Supply_Chain/
│
├── Data/                 # Source data files (CSV)
├── dashboard.py          # Main application
├── data_loader.py        # ETL pipeline
├── file_loader.py        # File I/O operations
├── utils.py              # Helper functions
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

### Adding New Features

1. **Data Integration**: Extend `data_loader.py` to incorporate new data sources
2. **UI Components**: Add new pages/sections in `dashboard.py`
3. **Metrics**: Implement calculation logic in `utils.py`
4. **Validation**: Update `inventory_validator.py` for new data quality checks

## 🔍 Debugging & Troubleshooting

The project includes diagnostic tools for data quality issues:

### Inventory Issues

**Problem**: Empty inventory reports or zero stock quantities

**Solution**:
```bash
python inventory_validator.py
```

Validates:
- Required columns presence
- Data type consistency
- Stock quantity calculations
- Aggregation logic

### Service Level Issues

**Problem**: Missing or incomplete service level data

**Solution**:
```bash
python debug_service_level.py
```

Traces:
- Order-to-delivery lifecycle
- Data join operations
- Date calculation logic
- Record filtering criteria

**Helper**:
```bash
python find_delivery_samples.py
```
Generates sample Sales Order/SKU combinations for testing.

### Backorder Issues

**Problem**: Backorder report empty despite known backorders

**Solution**:
```bash
python debug_backorder_loading.py
```

Analyzes:
- Order-to-master data joins
- Unmatched SKU identification
- Data completeness

### Unknown Products

**Problem**: "Unknown" product names in backorder reports

**Solution**:
```bash
python debug_unknown_products.py
```

Generates `unknown_product_name_report.xlsx` with:
- Unmatched SKU list
- Missing master data entries
- Data quality issues

## 🧪 Testing

Run the test suite:
```bash
python test_data_loader.py
```

Tests cover:
- Data loading functionality
- Transformation logic
- Edge case handling
- Error conditions

## 📈 Performance Considerations

- **Large Datasets**: The application handles multi-million row datasets efficiently using Pandas optimizations
- **Caching**: Streamlit's `@st.cache_data` decorator minimizes redundant data loading
- **Memory Management**: Chunked processing for large CSV files
- **Response Time**: Dashboard loads in < 5 seconds for typical data volumes

## 🔐 Data Privacy & Security

- All data processing occurs locally—no external data transmission
- CSV files should be stored securely with appropriate access controls
- Sensitive data fields should be masked in production deployments
- Follow EssilorLuxottica data governance policies

## 🚧 Roadmap

Future enhancements planned:
- [ ] Database integration (SQL Server/PostgreSQL)
- [ ] Real-time data refresh capabilities
- [ ] Advanced forecasting models
- [ ] User authentication and role-based access
- [ ] Export functionality for all reports
- [ ] Mobile-responsive design
- [ ] API endpoints for system integration

## 📝 Contributing

### Development Workflow

1. Create feature branch from `main`
2. Implement changes with appropriate tests
3. Validate data quality with debug tools
4. Submit pull request with description

### Code Standards

- Follow PEP 8 Python style guidelines
- Document functions with docstrings
- Add type hints where applicable
- Write unit tests for new features

## 📞 Support

For issues, questions, or feature requests:
- Create an issue in the project repository
- Contact the supply chain analytics team
- Reference EssilorLuxottica internal documentation

## 📄 License

Internal use only - EssilorLuxottica proprietary.

---

**Built for EssilorLuxottica POP Supply Chain Operations**
*Empowering data-driven supply chain excellence*
