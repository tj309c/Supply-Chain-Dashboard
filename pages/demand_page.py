"""
Demand Forecasting Dashboard Page

Professional demand planning interface with SKU-level forecast visualization,
historical actuals vs forecast comparison, and accuracy analytics.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Import demand forecasting utilities
from demand_forecasting import (
    get_forecast_summary_metrics, get_sku_forecast_details, get_forecast_accuracy_rankings,
    save_forecast_snapshot, load_forecast_snapshots, get_latest_snapshot_date,
    compare_forecast_vs_actual, calculate_forecast_bias, aggregate_demand_by_category,
    build_seasonality_model, get_seasonal_index_for_sku,
    generate_demand_forecast, SMOOTHING_PRESETS
)


def show_demand_page(deliveries_df, demand_forecast_df, forecast_accuracy_df, master_data_df, daily_demand_df):
    """
    Display demand forecasting dashboard with forecasts, accuracy, and patterns

    Args:
        deliveries_df: Historical deliveries dataframe
        demand_forecast_df: Forecast dataframe from generate_demand_forecast() - can be empty, will compute here
        forecast_accuracy_df: Accuracy metrics dataframe from generate_demand_forecast()
        master_data_df: Master data dataframe with SKU metadata
        daily_demand_df: Daily demand time series dataframe (sku, date, demand_qty)
    """
    st.title("📈 Demand Planning & Forecasting")

    # DEBUG: Print to console for troubleshooting
    print(f"[DEMAND PAGE DEBUG] deliveries_df type: {type(deliveries_df)}, empty: {deliveries_df.empty if hasattr(deliveries_df, 'empty') else 'N/A'}")
    if hasattr(deliveries_df, 'shape'):
        print(f"[DEMAND PAGE DEBUG] deliveries_df shape: {deliveries_df.shape}")

    # Check if we have deliveries data first
    if deliveries_df.empty:
        st.warning("⚠️ No deliveries data available. Please ensure DELIVERIES.csv is loaded.")
        print("[DEMAND PAGE DEBUG] Early return - deliveries_df is empty")
        return

    # Debug: show deliveries data shape
    st.caption(f"📊 Deliveries data: {len(deliveries_df):,} rows | Master data: {len(master_data_df):,} rows")

    # ===== SMOOTHING PRESET SELECTOR (only on this page) =====
    st.markdown("### ⚙️ Forecast Settings")
    settings_col1, settings_col2 = st.columns([2, 3])

    with settings_col1:
        smoothing_options = list(SMOOTHING_PRESETS.keys())
        # Default to 'Balanced' - moderate smoothing for typical demand patterns
        default_idx = smoothing_options.index('Balanced') if 'Balanced' in smoothing_options else 1

        selected_smoothing = st.selectbox(
            "Smoothing Preset",
            options=smoothing_options,
            index=default_idx,
            key="demand_smoothing_preset",
            help="Controls how much historical data influences the forecast. 'Conservative' uses ~12 months, 'Balanced' uses ~6 months, 'Aggressive' uses ~3 months."
        )

    with settings_col2:
        # Show preset description
        preset_info = SMOOTHING_PRESETS.get(selected_smoothing, {})
        alpha = preset_info.get('alpha', 0.1)
        effective_periods = int(2 / alpha) if alpha > 0 else 10
        st.info(f"**{selected_smoothing}**: {preset_info.get('description', '')} (α={alpha}, ~{effective_periods} period window)")

    st.divider()

    # ===== COMPUTE FORECAST WITH SELECTED SMOOTHING PRESET =====
    # Cached computation - pass dataframes directly so cache can access them
    # Forecast horizon: 9 months (270 days) to match typical eyewear supply chain lead times
    FORECAST_HORIZON_DAYS = 270
    FORECAST_HORIZON_MONTHS = 9
    HISTORICAL_MONTHS = 9  # Show 9 months of history for 18-month rolling view

    @st.cache_data(ttl=3600, show_spinner="Computing demand forecasts...")
    def _compute_demand_forecast_cached(_deliveries_df, _master_data_df, smoothing_preset):
        """Compute forecast with caching based on data and smoothing preset

        Uses daily granularity for forecasting (most data points for seasonality)
        and aggregates to monthly for display.
        """
        try:
            logs, forecast_df, accuracy_df, daily_df = generate_demand_forecast(
                _deliveries_df,
                master_data_df=_master_data_df,
                forecast_horizon_days=FORECAST_HORIZON_DAYS,
                ts_granularity='daily',  # Daily for best seasonality detection
                rolling_months=30,
                smoothing_preset=smoothing_preset
            )
            return forecast_df, accuracy_df, daily_df
        except Exception as e:
            st.error(f"Error computing demand forecast: {e}")
            import traceback
            st.error(traceback.format_exc())
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Compute or retrieve cached forecast (pass dataframes directly)
    print(f"[DEMAND PAGE DEBUG] demand_forecast_df.empty before compute: {demand_forecast_df.empty}")
    if demand_forecast_df.empty:
        print(f"[DEMAND PAGE DEBUG] Computing forecast with preset: {selected_smoothing}")
        demand_forecast_df, forecast_accuracy_df, daily_demand_df = _compute_demand_forecast_cached(
            deliveries_df, master_data_df, selected_smoothing
        )
        print(f"[DEMAND PAGE DEBUG] After compute - forecast shape: {demand_forecast_df.shape if hasattr(demand_forecast_df, 'shape') else 'N/A'}")

    # Check if forecast data exists after computation
    if demand_forecast_df.empty:
        print("[DEMAND PAGE DEBUG] Forecast is EMPTY after computation")
        st.warning("⚠️ No demand forecasts available. Ensure DELIVERIES.csv has sufficient historical data (minimum 3 months per SKU for monthly view).")
        return

    print(f"[DEMAND PAGE DEBUG] SUCCESS - forecast has {len(demand_forecast_df)} rows")

    # Get summary metrics
    metrics = get_forecast_summary_metrics(demand_forecast_df)

    # ===== HEADER KPIs - Clean 4-column layout =====
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="SKUs Forecasted",
            value=f"{metrics.get('total_skus_forecasted', 0):,}",
            help="Number of SKUs with sufficient data for forecasting"
        )

    with col2:
        total_forecast = metrics.get('total_forecast_demand', 0)
        st.metric(
            label="9-Month Forecast",
            value=f"{total_forecast:,.0f}",
            help="Total forecasted demand for next 9 months (270 days)"
        )

    with col3:
        high_conf = metrics.get('high_confidence_count', 0)
        total = metrics.get('total_skus_forecasted', 1)
        conf_pct = (high_conf / total * 100) if total > 0 else 0
        st.metric(
            label="High Confidence",
            value=f"{conf_pct:.0f}%",
            help="Percentage of SKUs with high confidence forecasts"
        )

    with col4:
        avg_mape = metrics.get('avg_mape', np.nan)
        if pd.notna(avg_mape):
            accuracy = 100 - min(avg_mape, 100)
            st.metric(
                label="Forecast Accuracy",
                value=f"{accuracy:.0f}%",
                help=f"Based on MAPE of {avg_mape:.1f}%"
            )
        else:
            st.metric(
                label="Forecast Accuracy",
                value="N/A",
                help="Insufficient data for backtesting"
            )

    st.divider()

    # ===== MAIN CONTENT: TIME-SERIES GRAPH AT TOP =====
    st.markdown("### 📊 SKU Demand Forecast Viewer")

    # Merge category info if available
    daily_demand_with_meta = daily_demand_df.copy()
    if not daily_demand_df.empty:
        # Add category and description from forecast df
        if 'category' in demand_forecast_df.columns:
            mapping_cols = ['sku']
            if 'category' in demand_forecast_df.columns:
                mapping_cols.append('category')
            if 'sku_description' in demand_forecast_df.columns:
                mapping_cols.append('sku_description')

            sku_meta = demand_forecast_df[mapping_cols].drop_duplicates()
            daily_demand_with_meta = pd.merge(daily_demand_df, sku_meta, on='sku', how='left')
            daily_demand_with_meta['category'] = daily_demand_with_meta.get('category', 'Uncategorized').fillna('Uncategorized')
        else:
            daily_demand_with_meta['category'] = 'Uncategorized'

    # ===== SKU SELECTOR - Prominent at top =====
    filter_col1, filter_col2 = st.columns([2, 1])

    with filter_col1:
        # Get list of SKUs with forecasts, sorted by total forecast demand
        # Build SKU options with descriptions for better usability
        sorted_df = demand_forecast_df.sort_values('forecast_total_qty', ascending=False)

        # Create display labels with SKU + Description
        if 'sku_description' in sorted_df.columns:
            sku_display_options = []
            sku_value_map = {}
            for _, row in sorted_df.iterrows():
                sku = row['sku']
                desc = row.get('sku_description', '')
                if pd.notna(desc) and desc != 'Unknown' and desc != '':
                    display_label = f"{sku} - {desc[:50]}{'...' if len(str(desc)) > 50 else ''}"
                else:
                    display_label = sku
                sku_display_options.append(display_label)
                sku_value_map[display_label] = sku
        else:
            sku_display_options = sorted_df['sku'].tolist()
            sku_value_map = {sku: sku for sku in sku_display_options}

        selected_display = st.selectbox(
            "🔍 Select SKU to View Forecast",
            options=['-- Select a SKU --'] + sku_display_options,
            index=0,
            help="Choose a SKU to see its historical demand and future forecast"
        )

        # Map display label back to actual SKU value
        if selected_display == '-- Select a SKU --':
            selected_sku = '-- Select a SKU --'
        else:
            selected_sku = sku_value_map.get(selected_display, selected_display)

    with filter_col2:
        # Quick stats for selected SKU
        if selected_sku and selected_sku != '-- Select a SKU --':
            sku_forecast = demand_forecast_df[demand_forecast_df['sku'] == selected_sku]
            if not sku_forecast.empty:
                # Use seasonally-adjusted exp smooth if available, otherwise exp_smooth, otherwise primary
                if 'exp_smooth_seasonal' in sku_forecast.columns and pd.notna(sku_forecast['exp_smooth_seasonal'].iloc[0]):
                    display_forecast = sku_forecast['exp_smooth_seasonal'].iloc[0]
                    seasonal_idx = sku_forecast['seasonal_index'].iloc[0] if 'seasonal_index' in sku_forecast.columns else 1.0
                    forecast_label = "Seasonal Forecast"
                    help_text = f"Exp smoothing with seasonal adjustment (index: {seasonal_idx:.2f})"
                elif 'exp_smooth' in sku_forecast.columns and pd.notna(sku_forecast['exp_smooth'].iloc[0]):
                    display_forecast = sku_forecast['exp_smooth'].iloc[0]
                    forecast_label = "Exp Smooth Forecast"
                    help_text = "Exponential smoothing forecast (anomaly-adjusted)"
                else:
                    display_forecast = sku_forecast['primary_forecast_daily'].iloc[0]
                    forecast_label = "Daily Forecast"
                    help_text = "Moving average forecast"
                st.metric(
                    forecast_label,
                    f"{display_forecast:.1f} units",
                    help=help_text
                )

    # ===== TIME-SERIES CHART =====
    if selected_sku and selected_sku != '-- Select a SKU --':
        _render_sku_forecast_chart(selected_sku, daily_demand_with_meta, demand_forecast_df)
    else:
        # Show aggregate view when no SKU selected
        _render_aggregate_chart(daily_demand_with_meta, demand_forecast_df)

    st.divider()

    # ===== TABBED INTERFACE - Streamlined =====
    tab1, tab2, tab3 = st.tabs([
        "📋 Forecast Table",
        "📈 Analytics & Patterns",
        "🎯 Accuracy Tracking"
    ])

    # ===== TAB 1: Forecast Table =====
    with tab1:
        _render_forecast_table(demand_forecast_df)

    # ===== TAB 2: Analytics & Patterns =====
    with tab2:
        _render_analytics_tab(demand_forecast_df)

    # ===== TAB 3: Accuracy Tracking =====
    with tab3:
        _render_accuracy_tab(forecast_accuracy_df, deliveries_df, demand_forecast_df)


def _render_sku_forecast_chart(selected_sku, daily_demand_df, demand_forecast_df):
    """
    Render 18-month rolling time-series chart for a specific SKU.
    Shows 9 months of historical actuals + 9 months of forecast.
    Includes Bollinger Bands and SMA trendline.
    """
    # Constants for 18-month rolling view
    HISTORICAL_MONTHS = 9
    FORECAST_MONTHS = 9

    # Get historical data for selected SKU (daily granularity from forecasting)
    sku_history_daily = daily_demand_df[daily_demand_df['sku'] == selected_sku].sort_values('date')
    sku_forecast = demand_forecast_df[demand_forecast_df['sku'] == selected_sku]

    if sku_history_daily.empty:
        st.warning(f"No historical data available for SKU: {selected_sku}")
        return

    # Get SKU description for display
    sku_description = ""
    if not sku_forecast.empty and 'sku_description' in sku_forecast.columns:
        sku_description = sku_forecast['sku_description'].iloc[0]
        if pd.isna(sku_description) or sku_description == 'Unknown':
            sku_description = ""

    # Display SKU header with description
    if sku_description:
        st.markdown(f"**{selected_sku}** - {sku_description}")

    # Aggregate daily data to monthly for display
    sku_history_daily_copy = sku_history_daily.copy()
    sku_history_daily_copy['month'] = pd.to_datetime(sku_history_daily_copy['date']).dt.to_period('M').dt.to_timestamp()
    sku_history = sku_history_daily_copy.groupby('month').agg({'demand_qty': 'sum'}).reset_index()
    sku_history.columns = ['date', 'demand_qty']

    # Filter to last 9 months of historical data
    last_date = sku_history['date'].max()
    cutoff_date = last_date - pd.DateOffset(months=HISTORICAL_MONTHS)
    sku_history_filtered = sku_history[sku_history['date'] >= cutoff_date]

    fig = go.Figure()

    # ===== HISTORICAL ACTUAL DEMAND (Monthly Bars) =====
    fig.add_trace(go.Bar(
        x=sku_history_filtered['date'],
        y=sku_history_filtered['demand_qty'],
        name='Actual Demand',
        marker_color='#1f77b4',
        opacity=0.8,
        hovertemplate='<b>Actual</b><br>Month: %{x|%b %Y}<br>Demand: %{y:,.0f} units<extra></extra>'
    ))

    # ===== FORECAST PROJECTION (9 months) =====
    if not sku_forecast.empty:
        # Get daily forecast value (seasonally-adjusted if available)
        if 'exp_smooth_seasonal' in sku_forecast.columns and pd.notna(sku_forecast['exp_smooth_seasonal'].iloc[0]):
            forecast_daily = sku_forecast['exp_smooth_seasonal'].iloc[0]
        elif 'exp_smooth' in sku_forecast.columns and pd.notna(sku_forecast['exp_smooth'].iloc[0]):
            forecast_daily = sku_forecast['exp_smooth'].iloc[0]
        else:
            forecast_daily = sku_forecast['primary_forecast_daily'].iloc[0]

        # Get standard deviation for Bollinger Bands
        std_daily = sku_forecast['demand_std'].iloc[0] / 30.0 if 'demand_std' in sku_forecast.columns else forecast_daily * 0.2

        # Get Bollinger Band width from applied Z-threshold (uses preset's Z-score)
        # This makes band width consistent with anomaly detection sensitivity
        band_multiplier = sku_forecast['applied_z_threshold'].iloc[0] if 'applied_z_threshold' in sku_forecast.columns else 2.0

        # Convert daily forecast to monthly
        forecast_monthly = forecast_daily * 30
        std_monthly = std_daily * 30

        # Create next 9 months of forecast dates
        forecast_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=FORECAST_MONTHS, freq='MS')

        # Calculate seasonal indices from DAILY historical data (most data points = best seasonality)
        # Use ALL historical daily data to capture full seasonality patterns
        sku_history_for_seasonal = sku_history_daily_copy.copy()
        sku_history_for_seasonal['month_num'] = pd.to_datetime(sku_history_for_seasonal['date']).dt.month

        # Aggregate daily to monthly per month_num to get average monthly demand for each calendar month
        # This gives us multiple data points per month (from multiple years)
        monthly_totals = sku_history_for_seasonal.copy()
        monthly_totals['year_month'] = pd.to_datetime(monthly_totals['date']).dt.to_period('M')
        monthly_by_period = monthly_totals.groupby(['year_month', 'month_num'])['demand_qty'].sum().reset_index()

        # Now average across years for each month_num
        monthly_avg = monthly_by_period.groupby('month_num')['demand_qty'].mean()
        overall_avg = monthly_avg.mean() if len(monthly_avg) > 0 else 1

        # Build seasonal indices for each month
        seasonal_indices = {}
        for month_num in range(1, 13):
            if month_num in monthly_avg.index and overall_avg > 0:
                seasonal_indices[month_num] = monthly_avg[month_num] / overall_avg
            else:
                seasonal_indices[month_num] = 1.0

        # Calculate monthly forecast values with per-month seasonal adjustment
        forecast_values = []
        upper_band = []
        lower_band = []

        for forecast_date in forecast_dates:
            month_num = forecast_date.month
            seasonal_index = seasonal_indices.get(month_num, 1.0)
            adjusted_forecast = forecast_monthly * seasonal_index
            forecast_values.append(adjusted_forecast)
            # Bollinger Bands using preset's Z-threshold with 0 floor (can't have negative demand)
            upper_band.append(adjusted_forecast + band_multiplier * std_monthly)
            lower_band.append(max(0, adjusted_forecast - band_multiplier * std_monthly))

        # ===== FORECAST BARS =====
        fig.add_trace(go.Bar(
            x=forecast_dates,
            y=forecast_values,
            name='Forecast',
            marker_color='#ff7f0e',
            opacity=0.8,
            hovertemplate='<b>Forecast</b><br>Month: %{x|%b %Y}<br>Forecast: %{y:,.0f} units<extra></extra>'
        ))

        # ===== BOLLINGER BANDS (Upper) =====
        fig.add_trace(go.Scatter(
            x=forecast_dates,
            y=upper_band,
            mode='lines',
            name=f'Upper Band (+{band_multiplier}σ)',
            line=dict(color='rgba(255, 127, 14, 0.5)', width=1, dash='dash'),
            hovertemplate='<b>Upper Band</b><br>Month: %{x|%b %Y}<br>Value: %{y:,.0f} units<extra></extra>'
        ))

        # ===== BOLLINGER BANDS (Lower) =====
        fig.add_trace(go.Scatter(
            x=forecast_dates,
            y=lower_band,
            mode='lines',
            name=f'Lower Band (-{band_multiplier}σ)',
            line=dict(color='rgba(255, 127, 14, 0.5)', width=1, dash='dash'),
            fill='tonexty',
            fillcolor='rgba(255, 127, 14, 0.1)',
            hovertemplate='<b>Lower Band</b><br>Month: %{x|%b %Y}<br>Value: %{y:,.0f} units<extra></extra>'
        ))

        # ===== SMA TRENDLINE (across historical + forecast) =====
        # Combine historical and forecast for trendline
        all_dates = list(sku_history_filtered['date']) + list(forecast_dates)
        all_values = list(sku_history_filtered['demand_qty']) + forecast_values

        # Calculate 3-month SMA for trendline
        sma_window = 3
        if len(all_values) >= sma_window:
            sma_values = []
            for i in range(len(all_values)):
                if i < sma_window - 1:
                    sma_values.append(np.nan)
                else:
                    sma_values.append(np.mean(all_values[i-sma_window+1:i+1]))

            fig.add_trace(go.Scatter(
                x=all_dates,
                y=sma_values,
                mode='lines',
                name='3-Month SMA',
                line=dict(color='#2ca02c', width=2),
                hovertemplate='<b>SMA (3-mo)</b><br>Month: %{x|%b %Y}<br>Value: %{y:,.0f} units<extra></extra>'
            ))

    # Layout
    chart_title = f"18-Month Rolling Forecast: {selected_sku}"
    if sku_description:
        chart_title = f"18-Month Rolling Forecast: {selected_sku} - {sku_description}"

    fig.update_layout(
        title=chart_title,
        xaxis_title="Month",
        yaxis_title="Demand (Units)",
        height=500,
        hovermode='x unified',
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        # Add vertical line to separate actuals from forecast
        shapes=[dict(
            type='line',
            x0=last_date + pd.DateOffset(days=15),  # Midpoint between last actual and first forecast
            x1=last_date + pd.DateOffset(days=15),
            y0=0,
            y1=1,
            yref='paper',
            line=dict(color='gray', width=1, dash='dot')
        )]
    )

    st.plotly_chart(fig, use_container_width=True)

    # SKU Details card
    if not sku_forecast.empty:
        row = sku_forecast.iloc[0]
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            # Use seasonally-adjusted total if available
            if 'forecast_total_qty_seasonal' in row.index and pd.notna(row['forecast_total_qty_seasonal']):
                total_qty = row['forecast_total_qty_seasonal']
            else:
                total_qty = row['forecast_total_qty']
            st.metric("9-Month Total", f"{total_qty:,.0f} units")
        with col2:
            st.metric("Confidence", row['forecast_confidence'])
        with col3:
            # Show exp smoothing method if seasonal is available
            if 'exp_smooth_seasonal' in row.index and pd.notna(row['exp_smooth_seasonal']):
                method = "Exp Smooth + Seasonal"
            elif 'exp_smooth' in row.index and pd.notna(row['exp_smooth']):
                method = "Exp Smooth"
            else:
                method = row['forecast_method']
            st.metric("Method", method)
        with col4:
            pattern = row.get('demand_pattern', 'Unknown')
            st.metric("Pattern", pattern)


def _render_aggregate_chart(daily_demand_df, demand_forecast_df):
    """
    Render 18-month rolling aggregate demand chart when no SKU is selected.
    Shows 9 months of historical actuals + 9 months of forecast.

    Data comes in daily granularity and is aggregated to monthly for display.
    """
    # Constants for 18-month rolling view
    HISTORICAL_MONTHS = 9
    FORECAST_MONTHS = 9

    if daily_demand_df.empty:
        st.info("Select a SKU above to view its forecast, or upload historical delivery data.")
        return

    # Aggregate daily data to monthly for display
    daily_demand = daily_demand_df.copy()
    daily_demand['month'] = pd.to_datetime(daily_demand['date']).dt.to_period('M').dt.to_timestamp()
    agg_demand = daily_demand.groupby('month').agg({'demand_qty': 'sum'}).reset_index()
    agg_demand.columns = ['date', 'demand_qty']
    agg_demand = agg_demand.sort_values('date')

    # Filter to last 9 months
    last_date = agg_demand['date'].max()
    cutoff_date = last_date - pd.DateOffset(months=HISTORICAL_MONTHS)
    agg_demand_filtered = agg_demand[agg_demand['date'] >= cutoff_date]

    fig = go.Figure()

    # ===== HISTORICAL AGGREGATE DEMAND (Monthly Bars) =====
    fig.add_trace(go.Bar(
        x=agg_demand_filtered['date'],
        y=agg_demand_filtered['demand_qty'],
        name='Actual Demand',
        marker_color='#1f77b4',
        opacity=0.8,
        hovertemplate='<b>Actual</b><br>Month: %{x|%b %Y}<br>Demand: %{y:,.0f} units<extra></extra>'
    ))

    # ===== FORECAST PROJECTION (9 months) =====
    if not demand_forecast_df.empty:
        # Get total daily forecast across all SKUs
        if 'exp_smooth_seasonal' in demand_forecast_df.columns:
            seasonal_sum = demand_forecast_df['exp_smooth_seasonal'].sum()
            total_daily_forecast = seasonal_sum if pd.notna(seasonal_sum) and seasonal_sum > 0 else demand_forecast_df['primary_forecast_daily'].sum()
        elif 'exp_smooth' in demand_forecast_df.columns:
            exp_smooth_sum = demand_forecast_df['exp_smooth'].sum()
            total_daily_forecast = exp_smooth_sum if pd.notna(exp_smooth_sum) and exp_smooth_sum > 0 else demand_forecast_df['primary_forecast_daily'].sum()
        else:
            total_daily_forecast = demand_forecast_df['primary_forecast_daily'].sum()

        # Get aggregate standard deviation for Bollinger Bands
        if 'demand_std' in demand_forecast_df.columns:
            total_std_daily = demand_forecast_df['demand_std'].sum() / 30.0
        else:
            total_std_daily = total_daily_forecast * 0.2

        # Get average Bollinger Band multiplier from applied Z-thresholds
        # Uses preset's Z-score for consistent band width
        if 'applied_z_threshold' in demand_forecast_df.columns:
            band_multiplier = demand_forecast_df['applied_z_threshold'].mean()
        else:
            band_multiplier = 2.0

        # Convert to monthly
        base_monthly_forecast = total_daily_forecast * 30
        std_monthly = total_std_daily * 30

        # Calculate seasonal indices from ALL daily historical data (not just filtered)
        # This gives multiple data points per month for better seasonality detection
        daily_for_seasonal = daily_demand.copy()
        daily_for_seasonal['month_num'] = pd.to_datetime(daily_for_seasonal['date']).dt.month
        daily_for_seasonal['year_month'] = pd.to_datetime(daily_for_seasonal['date']).dt.to_period('M')

        # Sum daily to monthly per period, then average across years for each month_num
        monthly_by_period = daily_for_seasonal.groupby(['year_month', 'month_num'])['demand_qty'].sum().reset_index()
        monthly_avg = monthly_by_period.groupby('month_num')['demand_qty'].mean()
        overall_avg = monthly_avg.mean() if len(monthly_avg) > 0 else 1

        seasonal_indices = {}
        for month_num in range(1, 13):
            if month_num in monthly_avg.index and overall_avg > 0:
                seasonal_indices[month_num] = monthly_avg[month_num] / overall_avg
            else:
                seasonal_indices[month_num] = 1.0

        # Create next 9 months with seasonal adjustments
        forecast_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=FORECAST_MONTHS, freq='MS')
        forecast_values = []
        upper_band = []
        lower_band = []

        for forecast_date in forecast_dates:
            month_num = forecast_date.month
            seasonal_index = seasonal_indices.get(month_num, 1.0)
            adjusted_forecast = base_monthly_forecast * seasonal_index
            forecast_values.append(adjusted_forecast)
            # Bollinger Bands using preset's Z-threshold with 0 floor (can't have negative demand)
            upper_band.append(adjusted_forecast + band_multiplier * std_monthly)
            lower_band.append(max(0, adjusted_forecast - band_multiplier * std_monthly))

        # ===== FORECAST BARS =====
        fig.add_trace(go.Bar(
            x=forecast_dates,
            y=forecast_values,
            name='Forecast',
            marker_color='#ff7f0e',
            opacity=0.8,
            hovertemplate='<b>Forecast</b><br>Month: %{x|%b %Y}<br>Forecast: %{y:,.0f} units<extra></extra>'
        ))

        # ===== BOLLINGER BANDS =====
        fig.add_trace(go.Scatter(
            x=forecast_dates,
            y=upper_band,
            mode='lines',
            name=f'Upper Band (+{band_multiplier:.1f}σ)',
            line=dict(color='rgba(255, 127, 14, 0.5)', width=1, dash='dash'),
            hovertemplate='<b>Upper Band</b><br>Month: %{x|%b %Y}<br>Value: %{y:,.0f} units<extra></extra>'
        ))

        fig.add_trace(go.Scatter(
            x=forecast_dates,
            y=lower_band,
            mode='lines',
            name=f'Lower Band (-{band_multiplier:.1f}σ)',
            line=dict(color='rgba(255, 127, 14, 0.5)', width=1, dash='dash'),
            fill='tonexty',
            fillcolor='rgba(255, 127, 14, 0.1)',
            hovertemplate='<b>Lower Band</b><br>Month: %{x|%b %Y}<br>Value: %{y:,.0f} units<extra></extra>'
        ))

        # ===== SMA TRENDLINE =====
        all_dates = list(agg_demand_filtered['date']) + list(forecast_dates)
        all_values = list(agg_demand_filtered['demand_qty']) + forecast_values

        sma_window = 3
        if len(all_values) >= sma_window:
            sma_values = []
            for i in range(len(all_values)):
                if i < sma_window - 1:
                    sma_values.append(np.nan)
                else:
                    sma_values.append(np.mean(all_values[i-sma_window+1:i+1]))

            fig.add_trace(go.Scatter(
                x=all_dates,
                y=sma_values,
                mode='lines',
                name='3-Month SMA',
                line=dict(color='#2ca02c', width=2),
                hovertemplate='<b>SMA (3-mo)</b><br>Month: %{x|%b %Y}<br>Value: %{y:,.0f} units<extra></extra>'
            ))

    fig.update_layout(
        title="18-Month Rolling Demand Overview (All SKUs)",
        xaxis_title="Month",
        yaxis_title="Total Demand (Units)",
        height=450,
        hovermode='x unified',
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        shapes=[dict(
            type='line',
            x0=last_date + pd.DateOffset(days=15),
            x1=last_date + pd.DateOffset(days=15),
            y0=0,
            y1=1,
            yref='paper',
            line=dict(color='gray', width=1, dash='dot')
        )]
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption("💡 18-month rolling view: 9 months actuals + 9 months forecast with Bollinger Bands. Select a SKU above for detailed view.")


def _render_forecast_table(demand_forecast_df):
    """Render searchable forecast table"""

    st.markdown("#### SKU Forecast Summary")

    # Search and filter
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_term = st.text_input("🔍 Search SKU or Description", placeholder="Type to filter...", key="forecast_search")

    with col2:
        confidence_filter = st.multiselect(
            "Confidence",
            options=['High', 'Medium', 'Low', 'Very Low'],
            default=['High', 'Medium', 'Low', 'Very Low'],
            key="confidence_filter"
        )

    with col3:
        sort_by = st.selectbox(
            "Sort by",
            options=['Forecast (High to Low)', 'Forecast (Low to High)', 'Confidence', 'SKU'],
            key="sort_filter"
        )

    # Apply filters
    filtered_df = demand_forecast_df.copy()

    if search_term:
        # Search both SKU and description (if available)
        sku_match = filtered_df['sku'].str.contains(search_term, case=False, na=False)
        if 'sku_description' in filtered_df.columns:
            desc_match = filtered_df['sku_description'].str.contains(search_term, case=False, na=False)
            filtered_df = filtered_df[sku_match | desc_match]
        else:
            filtered_df = filtered_df[sku_match]

    if confidence_filter:
        filtered_df = filtered_df[filtered_df['forecast_confidence'].isin(confidence_filter)]

    # Apply sorting
    if sort_by == 'Forecast (High to Low)':
        filtered_df = filtered_df.sort_values('forecast_total_qty', ascending=False)
    elif sort_by == 'Forecast (Low to High)':
        filtered_df = filtered_df.sort_values('forecast_total_qty', ascending=True)
    elif sort_by == 'Confidence':
        conf_order = {'High': 0, 'Medium': 1, 'Low': 2, 'Very Low': 3}
        filtered_df['_conf_sort'] = filtered_df['forecast_confidence'].map(conf_order)
        filtered_df = filtered_df.sort_values('_conf_sort').drop('_conf_sort', axis=1)
    else:
        filtered_df = filtered_df.sort_values('sku')

    st.caption(f"Showing {len(filtered_df)} of {len(demand_forecast_df)} SKUs")

    # Display table - include SKU Description and Seasonal Forecast
    # Build display columns dynamically based on what's available
    display_cols = ['sku']
    col_names = ['SKU']

    # Always add description if available
    if 'sku_description' in filtered_df.columns:
        display_cols.append('sku_description')
        col_names.append('Description')

    # Add seasonal index if available
    if 'seasonal_index' in filtered_df.columns:
        display_cols.append('seasonal_index')
        col_names.append('Seas. Idx')

    # Use seasonally-adjusted forecast if available, otherwise fall back to base forecast
    if 'forecast_total_qty_seasonal' in filtered_df.columns:
        display_cols.extend(['exp_smooth_seasonal', 'forecast_total_qty_seasonal', 'forecast_confidence',
                             'demand_pattern', 'historical_days'])
        col_names.extend(['Daily Forecast', '9-Month Total', 'Confidence',
                          'Pattern', 'History (periods)'])
    else:
        display_cols.extend(['primary_forecast_daily', 'forecast_total_qty', 'forecast_confidence',
                             'demand_pattern', 'historical_days'])
        col_names.extend(['Daily Forecast', '9-Month Total', 'Confidence',
                          'Pattern', 'History (periods)'])

    # Filter to available columns
    available_cols = [col for col in display_cols if col in filtered_df.columns]
    available_names = [col_names[i] for i, col in enumerate(display_cols) if col in filtered_df.columns]

    if available_cols:
        display_df = filtered_df[available_cols].copy()
        display_df.columns = available_names

        # Format numbers
        if 'Daily Forecast' in display_df.columns:
            display_df['Daily Forecast'] = display_df['Daily Forecast'].apply(lambda x: f"{x:,.1f}" if pd.notna(x) else "N/A")
        if 'Seas. Idx' in display_df.columns:
            display_df['Seas. Idx'] = display_df['Seas. Idx'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "1.00")
        if '9-Month Total' in display_df.columns:
            display_df['9-Month Total'] = display_df['9-Month Total'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "N/A")

        st.dataframe(display_df, use_container_width=True, height=400, hide_index=True)

    # Export button
    if not filtered_df.empty:
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Export to CSV",
            data=csv,
            file_name=f"demand_forecast_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )


def _render_analytics_tab(demand_forecast_df):
    """Render analytics and patterns tab"""

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Confidence Distribution")

        confidence_counts = demand_forecast_df['forecast_confidence'].value_counts().reset_index()
        confidence_counts.columns = ['Confidence', 'Count']

        fig = px.pie(
            confidence_counts,
            values='Count',
            names='Confidence',
            color='Confidence',
            color_discrete_map={
                'High': '#28a745',
                'Medium': '#ffc107',
                'Low': '#fd7e14',
                'Very Low': '#dc3545'
            }
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Forecast Methods")

        method_counts = demand_forecast_df['forecast_method'].value_counts().reset_index()
        method_counts.columns = ['Method', 'SKU Count']

        fig = px.bar(
            method_counts,
            x='Method',
            y='SKU Count',
            color='SKU Count',
            color_continuous_scale='Blues'
        )
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.markdown("#### Demand Patterns")

    col1, col2 = st.columns(2)

    with col1:
        # Volatility classification
        demand_forecast_df['volatility_class'] = pd.cut(
            demand_forecast_df['demand_cv'],
            bins=[0, 30, 70, float('inf')],
            labels=['Stable', 'Moderate', 'Volatile']
        )

        vol_counts = demand_forecast_df['volatility_class'].value_counts().reset_index()
        vol_counts.columns = ['Volatility', 'Count']

        fig = px.pie(
            vol_counts,
            values='Count',
            names='Volatility',
            color='Volatility',
            color_discrete_map={'Stable': '#28a745', 'Moderate': '#ffc107', 'Volatile': '#dc3545'}
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(title='Demand Volatility', showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Trend classification
        demand_forecast_df['trend_class'] = demand_forecast_df['demand_trend_slope'].apply(
            lambda x: 'Growing' if x > 0.5 else ('Declining' if x < -0.5 else 'Flat')
        )

        trend_counts = demand_forecast_df['trend_class'].value_counts().reset_index()
        trend_counts.columns = ['Trend', 'Count']

        fig = px.bar(
            trend_counts,
            x='Trend',
            y='Count',
            color='Trend',
            color_discrete_map={'Growing': '#28a745', 'Flat': '#6c757d', 'Declining': '#dc3545'}
        )
        fig.update_layout(title='Demand Trends', showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

    # Top growing and declining SKUs
    st.markdown("#### Top Movers")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**🔼 Top 5 Growing SKUs**")
        growing = demand_forecast_df.nlargest(5, 'demand_trend_slope')[['sku', 'demand_trend_slope', 'primary_forecast_daily']]
        growing.columns = ['SKU', 'Trend', 'Daily Forecast']
        growing['Trend'] = growing['Trend'].apply(lambda x: f"+{x:.2f}")
        growing['Daily Forecast'] = growing['Daily Forecast'].apply(lambda x: f"{x:.1f}")
        st.dataframe(growing, use_container_width=True, hide_index=True)

    with col2:
        st.markdown("**🔽 Top 5 Declining SKUs**")
        declining = demand_forecast_df.nsmallest(5, 'demand_trend_slope')[['sku', 'demand_trend_slope', 'primary_forecast_daily']]
        declining.columns = ['SKU', 'Trend', 'Daily Forecast']
        declining['Trend'] = declining['Trend'].apply(lambda x: f"{x:.2f}")
        declining['Daily Forecast'] = declining['Daily Forecast'].apply(lambda x: f"{x:.1f}")
        st.dataframe(declining, use_container_width=True, hide_index=True)


def _render_accuracy_tab(forecast_accuracy_df, deliveries_df, demand_forecast_df):
    """Render accuracy tracking tab"""

    if forecast_accuracy_df.empty:
        st.info("ℹ️ Insufficient historical data for accuracy backtesting. Need at least 6 months of data per SKU.")
    else:
        # Accuracy summary metrics
        col1, col2, col3 = st.columns(3)

        with col1:
            avg_mape = forecast_accuracy_df['mape'].mean()
            st.metric("Average MAPE", f"{avg_mape:.1f}%")

        with col2:
            median_mape = forecast_accuracy_df['mape'].median()
            st.metric("Median MAPE", f"{median_mape:.1f}%")

        with col3:
            avg_mae = forecast_accuracy_df['mae'].mean()
            st.metric("Average MAE", f"{avg_mae:.1f} units")

        st.divider()

        # Best and worst performers
        col1, col2 = st.columns(2)

        best_forecasts, worst_forecasts = get_forecast_accuracy_rankings(forecast_accuracy_df, top_n=5)

        with col1:
            st.markdown("**✅ Most Accurate Forecasts**")
            if not best_forecasts.empty:
                best_display = best_forecasts[['sku', 'mape', 'mae']].copy()
                best_display.columns = ['SKU', 'MAPE %', 'MAE']
                best_display['MAPE %'] = best_display['MAPE %'].apply(lambda x: f"{x:.1f}%")
                best_display['MAE'] = best_display['MAE'].apply(lambda x: f"{x:.1f}")
                st.dataframe(best_display, use_container_width=True, hide_index=True)

        with col2:
            st.markdown("**❌ Least Accurate Forecasts**")
            if not worst_forecasts.empty:
                worst_display = worst_forecasts[['sku', 'mape', 'mae']].copy()
                worst_display.columns = ['SKU', 'MAPE %', 'MAE']
                worst_display['MAPE %'] = worst_display['MAPE %'].apply(lambda x: f"{x:.1f}%")
                worst_display['MAE'] = worst_display['MAE'].apply(lambda x: f"{x:.1f}")
                st.dataframe(worst_display, use_container_width=True, hide_index=True)

        # MAPE distribution
        st.markdown("#### Error Distribution")

        fig = px.histogram(
            forecast_accuracy_df,
            x='mape',
            nbins=20,
            labels={'mape': 'MAPE (%)', 'count': 'Number of SKUs'},
            color_discrete_sequence=['#1f77b4']
        )
        # Add average line without annotation to avoid potential plotly issues
        fig.add_shape(
            type="line",
            x0=avg_mape, x1=avg_mape,
            y0=0, y1=1,
            yref="paper",
            line=dict(color="red", width=2, dash="dash")
        )
        # Add annotation separately
        fig.add_annotation(
            x=avg_mape, y=1, yref="paper",
            text=f"Avg: {avg_mape:.1f}%",
            showarrow=False,
            yshift=10
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    # Snapshot management
    st.divider()
    st.markdown("#### Forecast Snapshot Management")

    col1, col2 = st.columns(2)

    with col1:
        latest_snapshot = get_latest_snapshot_date()
        if latest_snapshot:
            st.info(f"📸 Last snapshot: {latest_snapshot.strftime('%Y-%m-%d')}")
        else:
            st.info("📸 No snapshots saved yet")

    with col2:
        if st.button("💾 Save Current Forecast", help="Save snapshot for future accuracy tracking"):
            success, filepath, message = save_forecast_snapshot(demand_forecast_df)
            if success:
                st.success(message)
            else:
                st.error(message)
