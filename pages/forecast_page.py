"""
Demand Forecasting Page
Forecast future demand, identify trends, and support inventory planning
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from business_rules import INVENTORY_RULES

# ===== PAGE CONFIGURATION =====

def render_forecast_page(orders_data=None, deliveries_data=None, master_data=None):
    """
    Render the demand forecasting page

    Args:
        orders_data: DataFrame with historical orders
        deliveries_data: DataFrame with historical deliveries (demand proxy)
        master_data: DataFrame with product master data
    """

    st.title("📈 Demand Forecasting")
    st.caption("Forecast future demand, identify trends, and support inventory planning")

    # ===== COMING SOON MESSAGE =====
    st.info("""
    **Demand Forecasting Module - Coming Soon!**

    This module will provide predictive analytics to forecast future demand and support proactive inventory planning.
    """)

    # ===== PLANNED FEATURES SECTION =====
    st.divider()
    st.subheader("📋 Planned Features")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📊 Historical Demand Analysis**")
        st.markdown("""
        - Historical demand trends by SKU and category
        - Monthly, weekly, and daily demand patterns
        - Year-over-year comparisons
        - Demand variability metrics (CV, std dev)
        - Growth rate calculations
        """)

        st.markdown("**📈 Forecasting Methods**")
        st.markdown("""
        - Simple Moving Average (SMA)
        - Weighted Moving Average (WMA)
        - Exponential Smoothing (ES)
        - Holt-Winters (seasonal ES)
        - ARIMA models (advanced)
        - Machine Learning models (Prophet, LSTM) - optional
        """)

    with col2:
        st.markdown("**🎯 Forecast Accuracy & Validation**")
        st.markdown("""
        - Forecast vs actual comparison
        - Mean Absolute Error (MAE)
        - Mean Absolute Percentage Error (MAPE)
        - Root Mean Square Error (RMSE)
        - Bias tracking (over/under forecasting)
        - Model selection and tuning
        """)

        st.markdown("**🔗 Integration & Actions**")
        st.markdown("""
        - Feed forecasts into inventory planning
        - Generate procurement recommendations
        - Identify new product ramp patterns
        - Alert on demand spikes or drops
        - Support capacity planning
        """)

    # ===== DATA STRUCTURE SECTION =====
    st.divider()
    st.subheader("📁 Required Data Sources")

    st.markdown("""
    **Primary Data Files:**
    1. **DELIVERIES.csv** - Historical shipment data (demand proxy)
       - Delivery Date, Material Number, Quantity Shipped
       - Used to calculate actual historical demand

    2. **ORDERS.csv** - Customer order history
       - Order Date, Material Number, Order Quantity
       - Used for demand signal and backorder analysis

    **Supporting Data:**
    - **Master Data.csv** - Product categories and attributes
    - **INVENTORY.csv** - Current stock levels for planning
    - **Domestic Vendor POs.csv** - Lead times for planning horizon

    **Calculation Logic:**
    - Historical Demand = Sum(Delivered Qty) by SKU by Period
    - Forecast Horizon = Lead Time + Safety Buffer (e.g., 90 days)
    - Forecast = Apply selected method to historical demand
    """)

    # ===== MOCKUP VISUALIZATIONS =====
    st.divider()
    st.subheader("📊 Planned Visualizations")

    # Generate sample data for visualizations
    dates = pd.date_range(start='2024-01-01', end='2025-03-31', freq='MS')
    np.random.seed(42)

    # Historical demand with trend and seasonality
    trend = np.linspace(100, 150, len(dates))
    seasonality = 20 * np.sin(np.arange(len(dates)) * 2 * np.pi / 12)
    noise = np.random.normal(0, 10, len(dates))
    historical = trend + seasonality + noise

    # Future forecast (last 3 months)
    forecast = historical.copy()
    forecast[-3:] = np.nan

    forecast_trend = np.linspace(150, 160, 3)
    forecast_seasonality = 20 * np.sin(np.arange(len(dates)-3, len(dates)) * 2 * np.pi / 12)
    forecast[-3:] = forecast_trend + forecast_seasonality

    # Create sample dataframe
    sample_forecast_data = pd.DataFrame({
        'Date': dates,
        'Historical Demand': historical,
        'Forecast': forecast
    })

    # Demand Forecast Chart
    fig_forecast = go.Figure()

    # Historical data
    fig_forecast.add_trace(go.Scatter(
        x=sample_forecast_data['Date'][:len(dates)-3],
        y=sample_forecast_data['Historical Demand'][:len(dates)-3],
        mode='lines+markers',
        name='Historical Demand',
        line=dict(color='steelblue', width=2),
        marker=dict(size=6)
    ))

    # Forecast data
    fig_forecast.add_trace(go.Scatter(
        x=sample_forecast_data['Date'][len(dates)-4:],
        y=sample_forecast_data['Forecast'][len(dates)-4:],
        mode='lines+markers',
        name='Forecasted Demand',
        line=dict(color='orange', width=2, dash='dash'),
        marker=dict(size=6)
    ))

    # Confidence interval (sample)
    upper_bound = sample_forecast_data['Forecast'][len(dates)-3:] * 1.15
    lower_bound = sample_forecast_data['Forecast'][len(dates)-3:] * 0.85

    fig_forecast.add_trace(go.Scatter(
        x=sample_forecast_data['Date'][len(dates)-3:],
        y=upper_bound,
        mode='lines',
        name='Upper Bound (85% CI)',
        line=dict(width=0),
        showlegend=True
    ))

    fig_forecast.add_trace(go.Scatter(
        x=sample_forecast_data['Date'][len(dates)-3:],
        y=lower_bound,
        mode='lines',
        name='Lower Bound (85% CI)',
        line=dict(width=0),
        fillcolor='rgba(255, 165, 0, 0.2)',
        fill='tonexty',
        showlegend=True
    ))

    fig_forecast.update_layout(
        title="Demand Forecast - Sample SKU (3-Month Projection)",
        xaxis_title="Month",
        yaxis_title="Demand (Units)",
        height=500,
        hovermode='x unified'
    )

    st.plotly_chart(fig_forecast, use_container_width=True)

    # Second row of charts
    col1, col2 = st.columns(2)

    with col1:
        # Forecast Accuracy by Method
        sample_methods = ['SMA-3', 'SMA-6', 'Exp Smoothing', 'Holt-Winters']
        sample_mape = [12.5, 10.8, 8.3, 7.2]

        fig_accuracy = go.Figure()
        fig_accuracy.add_trace(go.Bar(
            x=sample_methods,
            y=sample_mape,
            marker_color=['red' if x > 10 else 'orange' if x > 8 else 'green' for x in sample_mape],
            text=[f"{x:.1f}%" for x in sample_mape],
            textposition='outside'
        ))
        fig_accuracy.update_layout(
            title="Forecast Accuracy by Method (Sample)",
            xaxis_title="Forecasting Method",
            yaxis_title="MAPE (%)",
            yaxis_range=[0, 15],
            height=400
        )
        st.plotly_chart(fig_accuracy, use_container_width=True)

    with col2:
        # Demand Variability by Category
        sample_categories = ['Cat A', 'Cat B', 'Cat C', 'Cat D', 'Cat E']
        sample_cv = [0.25, 0.42, 0.18, 0.55, 0.31]

        fig_variability = go.Figure()
        fig_variability.add_trace(go.Bar(
            x=sample_categories,
            y=sample_cv,
            marker_color=['green' if x < 0.3 else 'orange' if x < 0.5 else 'red' for x in sample_cv],
            text=[f"{x:.2f}" for x in sample_cv],
            textposition='outside'
        ))
        fig_variability.update_layout(
            title="Demand Variability by Category (CV)",
            xaxis_title="Product Category",
            yaxis_title="Coefficient of Variation",
            yaxis_range=[0, 0.7],
            height=400
        )
        st.plotly_chart(fig_variability, use_container_width=True)

    # Forecast vs Actual Comparison
    st.divider()

    # Generate sample forecast vs actual data (last 6 months)
    past_dates = pd.date_range(start='2024-08-01', end='2025-01-31', freq='MS')
    past_actual = [120, 135, 142, 128, 145, 150]
    past_forecast = [118, 130, 145, 125, 140, 155]

    sample_comparison = pd.DataFrame({
        'Month': past_dates.strftime('%Y-%m'),
        'Actual': past_actual,
        'Forecast': past_forecast,
        'Error %': [(a-f)/a*100 for a, f in zip(past_actual, past_forecast)]
    })

    fig_comparison = go.Figure()

    fig_comparison.add_trace(go.Scatter(
        x=sample_comparison['Month'],
        y=sample_comparison['Actual'],
        mode='lines+markers',
        name='Actual Demand',
        line=dict(color='steelblue', width=3),
        marker=dict(size=8)
    ))

    fig_comparison.add_trace(go.Scatter(
        x=sample_comparison['Month'],
        y=sample_comparison['Forecast'],
        mode='lines+markers',
        name='Forecasted Demand',
        line=dict(color='orange', width=3, dash='dot'),
        marker=dict(size=8)
    ))

    fig_comparison.update_layout(
        title="Forecast vs Actual - Last 6 Months (Sample)",
        xaxis_title="Month",
        yaxis_title="Demand (Units)",
        height=400,
        hovermode='x unified'
    )

    st.plotly_chart(fig_comparison, use_container_width=True)

    # ===== SAMPLE KPI LAYOUT =====
    st.divider()
    st.subheader("📈 Forecast Performance Indicators (Sample)")

    kpi_cols = st.columns(6)

    sample_kpis = [
        {"label": "Avg MAPE", "value": "8.5%", "help": "Mean Absolute Percentage Error - lower is better (target <10%)"},
        {"label": "Avg MAE", "value": "12 units", "help": "Mean Absolute Error - average forecast deviation"},
        {"label": "Bias", "value": "+2.3%", "help": "Forecast bias - positive means over-forecasting"},
        {"label": "Forecast Accuracy", "value": "91.5%", "help": "Percentage accuracy (100% - MAPE)"},
        {"label": "SKUs Tracked", "value": "1,245", "help": "Number of SKUs with active forecasts"},
        {"label": "Forecast Horizon", "value": "90 days", "help": "Time period covered by current forecasts"}
    ]

    for idx, kpi in enumerate(sample_kpis):
        with kpi_cols[idx]:
            st.metric(
                label=kpi["label"],
                value=kpi["value"],
                help=kpi["help"]
            )

    # ===== SAMPLE FORECAST TABLE =====
    st.divider()
    st.subheader("📋 SKU Forecast Summary (Sample Data)")

    # Create sample SKU forecast data
    sample_sku_forecast = pd.DataFrame({
        'Material Number': ['MAT-001', 'MAT-002', 'MAT-003', 'MAT-004', 'MAT-005'],
        'Description': ['Product A', 'Product B', 'Product C', 'Product D', 'Product E'],
        'Category': ['Cat A', 'Cat B', 'Cat A', 'Cat C', 'Cat B'],
        'Historical Avg (30d)': [120, 85, 200, 45, 110],
        'Forecast (Next 30d)': [125, 80, 215, 42, 115],
        'Change': ['+4.2%', '-5.9%', '+7.5%', '-6.7%', '+4.5%'],
        'Confidence': ['High', 'Medium', 'High', 'Low', 'Medium'],
        'MAPE': ['6.2%', '12.5%', '5.8%', '18.3%', '9.7%']
    })

    st.dataframe(
        sample_sku_forecast,
        use_container_width=True,
        hide_index=True
    )

    # ===== FORECASTING METHODS EXPLANATION =====
    st.divider()

    with st.expander("📚 Forecasting Methods Explained"):
        st.markdown("""
        **Simple Moving Average (SMA)**
        - Average of last N periods
        - Best for stable demand with no trend
        - Easy to understand and implement
        - Example: SMA-3 = (Month1 + Month2 + Month3) / 3

        **Weighted Moving Average (WMA)**
        - Recent periods weighted more heavily
        - Better for demand with slight trend
        - More responsive than SMA

        **Exponential Smoothing (ES)**
        - Weights decrease exponentially for older data
        - Good for data with trend but no seasonality
        - Formula: Forecast = α × Actual + (1-α) × Previous Forecast

        **Holt-Winters Method**
        - Accounts for trend AND seasonality
        - Best for products with seasonal patterns
        - Three components: level, trend, seasonal

        **ARIMA (AutoRegressive Integrated Moving Average)**
        - Advanced statistical method
        - Good for complex patterns
        - Requires more historical data
        - Best for long-term forecasting

        **Machine Learning (Prophet, LSTM)**
        - Can handle multiple variables
        - Learns complex patterns automatically
        - Requires significant historical data
        - Best for products with promotional impacts
        """)

    # ===== IMPLEMENTATION ROADMAP =====
    st.divider()
    st.subheader("🗓️ Implementation Roadmap")

    roadmap_col1, roadmap_col2 = st.columns(2)

    with roadmap_col1:
        st.markdown("**Phase 1: Foundation (Weeks 1-2)**")
        st.markdown("""
        - [ ] Build historical demand aggregation pipeline
        - [ ] Calculate demand by SKU by period (daily, weekly, monthly)
        - [ ] Implement demand variability metrics (CV, std dev)
        - [ ] Create historical trend visualization
        - [ ] Add basic filtering (SKU, category, date range)
        """)

        st.markdown("**Phase 2: Basic Forecasting (Weeks 3-4)**")
        st.markdown("""
        - [ ] Implement Simple Moving Average (SMA)
        - [ ] Implement Exponential Smoothing (ES)
        - [ ] Add forecast horizon selector
        - [ ] Build forecast visualization
        - [ ] Create forecast export functionality
        """)

    with roadmap_col2:
        st.markdown("**Phase 3: Advanced Methods (Weeks 5-6)**")
        st.markdown("""
        - [ ] Implement Holt-Winters (seasonal ES)
        - [ ] Add ARIMA models
        - [ ] Build forecast accuracy tracking
        - [ ] Implement model comparison and selection
        - [ ] Add confidence intervals
        """)

        st.markdown("**Phase 4: Integration & Actions (Weeks 7-8)**")
        st.markdown("""
        - [ ] Feed forecasts into inventory planning
        - [ ] Generate procurement recommendations
        - [ ] Link to inbound PO creation
        - [ ] Build forecast-based alerts
        - [ ] Create executive forecast dashboard
        """)

    # ===== TECHNICAL NOTES =====
    st.divider()

    with st.expander("🔧 Technical Implementation Notes"):
        st.markdown("""
        **Data Pipeline:**
        1. Load DELIVERIES.csv and aggregate by SKU and time period
        2. Calculate historical demand = SUM(delivered_qty) by period
        3. Join with Master Data for product attributes
        4. Calculate demand statistics (mean, std, CV)
        5. Apply forecasting model(s) to generate predictions

        **Key Calculations:**
        - Historical Demand = SUM(Delivered Qty) per period
        - Moving Average = SUM(Last N Periods) / N
        - Coefficient of Variation = Std Dev / Mean
        - MAPE = AVG(|Actual - Forecast| / Actual) × 100
        - MAE = AVG(|Actual - Forecast|)
        - Bias = AVG(Forecast - Actual) / AVG(Actual) × 100

        **Forecast Horizon Guidelines:**
        - Short-term: 30-60 days (tactical planning)
        - Medium-term: 60-120 days (inventory planning)
        - Long-term: 120+ days (capacity planning)

        **Model Selection Criteria:**
        - Stable demand, no trend/seasonality → SMA
        - Trending demand, no seasonality → Exponential Smoothing
        - Seasonal patterns → Holt-Winters
        - Complex patterns → ARIMA or ML

        **Integration Requirements:**
        - Inventory module: Use forecast for reorder point calculations
        - Inbound module: Generate PO recommendations based on forecast
        - Backorder module: Identify forecast vs backorder mismatches
        - Alert system: Notify on significant demand changes
        """)

    # ===== BUSINESS VALUE =====
    st.divider()

    with st.expander("💡 Business Value & Use Cases"):
        st.markdown("""
        **Key Benefits:**
        - **Reduce Stockouts**: Proactive ordering based on predicted demand
        - **Optimize Inventory**: Right-size stock levels to minimize holding costs
        - **Improve Service Levels**: Ensure product availability when customers need it
        - **Better Negotiations**: Plan purchases in advance for better supplier terms
        - **Capacity Planning**: Anticipate warehouse and labor needs

        **Use Cases:**
        1. **New Product Introduction**: Predict ramp-up demand for new SKUs
        2. **Seasonal Planning**: Prepare for peak seasons (holidays, etc.)
        3. **Promotion Planning**: Forecast demand impact of promotions
        4. **Phase-Out Management**: Identify declining products for clearance
        5. **Supplier Negotiation**: Show forecasted volumes for contract discussions
        6. **Capacity Planning**: Anticipate warehouse space and labor needs
        7. **Budget Planning**: Forecast purchasing spend for financial planning

        **Success Metrics:**
        - Forecast Accuracy (MAPE) < 10% for A-class items
        - Stockout reduction by 30%+
        - Inventory holding cost reduction by 15%+
        - Service level improvement to >95%
        - Reduced expedited shipping costs
        """)

    # ===== FOOTER =====
    st.divider()
    st.caption("This page is a placeholder. Full implementation coming soon with historical demand analysis and forecasting algorithms.")


# ===== HELPER FUNCTIONS (For Future Implementation) =====

def calculate_historical_demand(deliveries_data, period='M'):
    """
    Calculate historical demand by SKU by period

    Args:
        deliveries_data: DataFrame with delivery records
        period: Time period for aggregation ('D'=daily, 'W'=weekly, 'M'=monthly)

    Returns:
        DataFrame with historical demand by SKU by period
    """
    # TODO: Implement when data sources are available
    pass


def forecast_simple_moving_average(historical_demand, n_periods=3, horizon=3):
    """
    Generate forecast using Simple Moving Average

    Args:
        historical_demand: Series with historical demand values
        n_periods: Number of periods to average
        horizon: Number of periods to forecast ahead

    Returns:
        Series with forecasted values
    """
    # TODO: Implement SMA algorithm
    pass


def forecast_exponential_smoothing(historical_demand, alpha=0.3, horizon=3):
    """
    Generate forecast using Exponential Smoothing

    Args:
        historical_demand: Series with historical demand values
        alpha: Smoothing parameter (0-1)
        horizon: Number of periods to forecast ahead

    Returns:
        Series with forecasted values
    """
    # TODO: Implement ES algorithm
    pass


def calculate_forecast_accuracy(actual, forecast):
    """
    Calculate forecast accuracy metrics (MAPE, MAE, RMSE, Bias)

    Args:
        actual: Series with actual demand values
        forecast: Series with forecasted values

    Returns:
        Dictionary with accuracy metrics
    """
    # TODO: Implement accuracy calculations
    pass


def identify_demand_trend(historical_demand):
    """
    Identify if demand is trending up, down, or stable

    Args:
        historical_demand: Series with historical demand values

    Returns:
        String: 'increasing', 'decreasing', or 'stable'
    """
    # TODO: Implement trend detection (linear regression slope)
    pass


def detect_seasonality(historical_demand, period=12):
    """
    Detect if demand has seasonal patterns

    Args:
        historical_demand: Series with historical demand values
        period: Seasonal period (12 for monthly data)

    Returns:
        Boolean indicating presence of seasonality
    """
    # TODO: Implement seasonality detection (autocorrelation)
    pass
