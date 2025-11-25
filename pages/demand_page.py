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
    compare_forecast_vs_actual, calculate_forecast_bias, aggregate_demand_by_category
)


def show_demand_page(deliveries_df, demand_forecast_df, forecast_accuracy_df, master_data_df, daily_demand_df):
    """
    Display demand forecasting dashboard with forecasts, accuracy, and patterns

    Args:
        deliveries_df: Historical deliveries dataframe
        demand_forecast_df: Forecast dataframe from generate_demand_forecast()
        forecast_accuracy_df: Accuracy metrics dataframe from generate_demand_forecast()
        master_data_df: Master data dataframe with SKU metadata
        daily_demand_df: Daily demand time series dataframe (sku, date, demand_qty)
    """
    st.title("📈 Demand Planning & Forecasting")

    # Check if forecast data exists
    if demand_forecast_df.empty:
        st.warning("⚠️ No demand forecasts available. Ensure DELIVERIES.csv has sufficient historical data (minimum 3 months per SKU for monthly view).")
        return

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
            label="90-Day Forecast",
            value=f"{total_forecast:,.0f}",
            help="Total forecasted demand for next 90 days"
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
        sku_options = demand_forecast_df.sort_values('forecast_total_qty', ascending=False)['sku'].tolist()

        selected_sku = st.selectbox(
            "🔍 Select SKU to View Forecast",
            options=['-- Select a SKU --'] + sku_options,
            index=0,
            help="Choose a SKU to see its historical demand and future forecast"
        )

    with filter_col2:
        # Quick stats for selected SKU
        if selected_sku and selected_sku != '-- Select a SKU --':
            sku_forecast = demand_forecast_df[demand_forecast_df['sku'] == selected_sku]
            if not sku_forecast.empty:
                st.metric(
                    "Daily Forecast",
                    f"{sku_forecast['primary_forecast_daily'].iloc[0]:.1f} units",
                    help="Predicted average daily demand"
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
    """Render time-series chart for a specific SKU showing actuals and forecast"""

    # Get historical data for selected SKU
    sku_history = daily_demand_df[daily_demand_df['sku'] == selected_sku].sort_values('date')
    sku_forecast = demand_forecast_df[demand_forecast_df['sku'] == selected_sku]

    if sku_history.empty:
        st.warning(f"No historical data available for SKU: {selected_sku}")
        return

    # Detect if data is monthly (dates are 1st of month) vs daily
    is_monthly = False
    if len(sku_history) >= 2:
        date_diffs = sku_history['date'].diff().dropna().dt.days
        avg_diff = date_diffs.mean()
        is_monthly = avg_diff > 20  # If avg gap > 20 days, it's monthly data

    fig = go.Figure()

    # Historical actual demand - solid blue line with bars for monthly
    if is_monthly:
        fig.add_trace(go.Bar(
            x=sku_history['date'],
            y=sku_history['demand_qty'],
            name='Actual Demand (Monthly)',
            marker_color='#1f77b4',
            opacity=0.7,
            hovertemplate='<b>Actual</b><br>Month: %{x|%b %Y}<br>Demand: %{y:,.0f} units<extra></extra>'
        ))
    else:
        fig.add_trace(go.Scatter(
            x=sku_history['date'],
            y=sku_history['demand_qty'],
            mode='lines+markers',
            name='Actual Demand',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=4),
            hovertemplate='<b>Actual</b><br>Date: %{x|%Y-%m-%d}<br>Demand: %{y:,.0f} units<extra></extra>'
        ))

    # Forecast projection
    if not sku_forecast.empty:
        forecast_daily = sku_forecast['primary_forecast_daily'].iloc[0]
        forecast_horizon = int(sku_forecast['forecast_horizon_days'].iloc[0])
        last_date = sku_history['date'].max()

        if is_monthly:
            # For monthly data: project 3 months of monthly forecasts
            # Convert daily forecast to monthly (multiply by ~30)
            forecast_monthly = forecast_daily * 30

            # Get confidence bounds as monthly values (90-day totals / 3 = monthly)
            forecast_lower_monthly = sku_forecast['forecast_lower_bound'].iloc[0] / 3
            forecast_upper_monthly = sku_forecast['forecast_upper_bound'].iloc[0] / 3

            # Ensure error bar values are non-negative
            error_upper = max(0, forecast_upper_monthly - forecast_monthly)
            error_lower = max(0, forecast_monthly - forecast_lower_monthly)

            # Create next 3 months
            forecast_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=3, freq='MS')
            forecast_values = [forecast_monthly] * 3

            # Forecast bars
            fig.add_trace(go.Bar(
                x=forecast_dates,
                y=forecast_values,
                name='Forecast (Monthly)',
                marker_color='#ff7f0e',
                opacity=0.7,
                hovertemplate='<b>Forecast</b><br>Month: %{x|%b %Y}<br>Forecast: %{y:,.0f} units<extra></extra>'
            ))

            # Confidence interval as error bars (only show if meaningful)
            if error_upper > 0 or error_lower > 0:
                fig.add_trace(go.Scatter(
                    x=forecast_dates,
                    y=forecast_values,
                    mode='markers',
                    marker=dict(size=0),
                    error_y=dict(
                        type='data',
                        symmetric=False,
                        array=[error_upper] * 3,
                        arrayminus=[error_lower] * 3,
                        color='rgba(255, 127, 14, 0.5)',
                        thickness=2,
                        width=10
                    ),
                    name='Confidence Range',
                    showlegend=True,
                    hoverinfo='skip'
                ))
            # Vertical line removed - visual separation provided by bar color difference

        else:
            # For daily data: project daily forecasts
            forecast_lower = sku_forecast['forecast_lower_bound'].iloc[0] / forecast_horizon
            forecast_upper = sku_forecast['forecast_upper_bound'].iloc[0] / forecast_horizon

            # Create forecast dates (next 90 days)
            forecast_dates = pd.date_range(start=last_date + timedelta(days=1), periods=forecast_horizon, freq='D')
            forecast_values = [forecast_daily] * forecast_horizon

            # Connect from last actual point
            connect_dates = pd.concat([pd.Series([last_date]), pd.Series(forecast_dates)])
            connect_values = [sku_history['demand_qty'].iloc[-1]] + forecast_values

            # Forecast line
            fig.add_trace(go.Scatter(
                x=connect_dates,
                y=connect_values,
                mode='lines',
                name='Forecast',
                line=dict(color='#ff7f0e', width=2, dash='dash'),
                hovertemplate='<b>Forecast</b><br>Date: %{x|%Y-%m-%d}<br>Forecast: %{y:,.1f} units<extra></extra>'
            ))

            # Confidence interval - shaded area
            upper_values = [forecast_upper] * forecast_horizon
            lower_values = [forecast_lower] * forecast_horizon

            fig.add_trace(go.Scatter(
                x=forecast_dates,
                y=upper_values,
                mode='lines',
                line=dict(width=0),
                showlegend=False,
                hoverinfo='skip'
            ))

            fig.add_trace(go.Scatter(
                x=forecast_dates,
                y=lower_values,
                mode='lines',
                line=dict(width=0),
                fill='tonexty',
                fillcolor='rgba(255, 127, 14, 0.2)',
                name='Confidence Interval',
                hoverinfo='skip'
            ))
            # Vertical line removed - visual separation provided by line color/style difference

    # Layout
    period_label = "Month" if is_monthly else "Date"
    fig.update_layout(
        title=f"Demand Forecast: {selected_sku}",
        xaxis_title=period_label,
        yaxis_title="Demand (Units)",
        height=450,
        hovermode='x unified',
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    # SKU Details card
    if not sku_forecast.empty:
        row = sku_forecast.iloc[0]
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("90-Day Total", f"{row['forecast_total_qty']:,.0f} units")
        with col2:
            st.metric("Confidence", row['forecast_confidence'])
        with col3:
            st.metric("Method", row['forecast_method'])
        with col4:
            pattern = row.get('demand_pattern', 'Unknown')
            st.metric("Pattern", pattern)


def _render_aggregate_chart(daily_demand_df, demand_forecast_df):
    """Render aggregate demand chart when no SKU is selected"""

    if daily_demand_df.empty:
        st.info("Select a SKU above to view its forecast, or upload historical delivery data.")
        return

    # Aggregate by date
    agg_demand = daily_demand_df.groupby('date').agg({'demand_qty': 'sum'}).reset_index()
    agg_demand = agg_demand.sort_values('date')

    # Detect if data is monthly
    is_monthly = False
    if len(agg_demand) >= 2:
        date_diffs = agg_demand['date'].diff().dropna().dt.days
        avg_diff = date_diffs.mean()
        is_monthly = avg_diff > 20

    fig = go.Figure()

    # Historical aggregate demand
    if is_monthly:
        fig.add_trace(go.Bar(
            x=agg_demand['date'],
            y=agg_demand['demand_qty'],
            name='Total Demand (Monthly)',
            marker_color='#1f77b4',
            opacity=0.7,
            hovertemplate='<b>Total Demand</b><br>Month: %{x|%b %Y}<br>Demand: %{y:,.0f} units<extra></extra>'
        ))
    else:
        fig.add_trace(go.Scatter(
            x=agg_demand['date'],
            y=agg_demand['demand_qty'],
            mode='lines',
            name='Total Demand (All SKUs)',
            line=dict(color='#1f77b4', width=2),
            fill='tozeroy',
            fillcolor='rgba(31, 119, 180, 0.1)',
            hovertemplate='<b>Total Demand</b><br>Date: %{x|%Y-%m-%d}<br>Demand: %{y:,.0f} units<extra></extra>'
        ))

    # Add aggregate forecast
    if not demand_forecast_df.empty:
        total_daily_forecast = demand_forecast_df['primary_forecast_daily'].sum()
        last_date = agg_demand['date'].max()

        if is_monthly:
            # Convert to monthly forecast
            total_monthly_forecast = total_daily_forecast * 30

            # Create next 3 months
            forecast_dates = pd.date_range(start=last_date + pd.DateOffset(months=1), periods=3, freq='MS')
            forecast_values = [total_monthly_forecast] * 3

            fig.add_trace(go.Bar(
                x=forecast_dates,
                y=forecast_values,
                name='Total Forecast (Monthly)',
                marker_color='#ff7f0e',
                opacity=0.7,
                hovertemplate='<b>Forecast</b><br>Month: %{x|%b %Y}<br>Forecast: %{y:,.0f} units<extra></extra>'
            ))
            # Vertical line removed - visual separation provided by bar color difference
        else:
            forecast_horizon = 90
            forecast_dates = pd.date_range(start=last_date + timedelta(days=1), periods=forecast_horizon, freq='D')
            forecast_values = [total_daily_forecast] * forecast_horizon

            fig.add_trace(go.Scatter(
                x=forecast_dates,
                y=forecast_values,
                mode='lines',
                name='Total Forecast',
                line=dict(color='#ff7f0e', width=2, dash='dash'),
                hovertemplate='<b>Forecast</b><br>Date: %{x|%Y-%m-%d}<br>Forecast: %{y:,.0f} units<extra></extra>'
            ))
            # Vertical line removed - visual separation provided by line color/style difference

    period_label = "Month" if is_monthly else "Date"
    fig.update_layout(
        title="Aggregate Demand Overview (All SKUs)",
        xaxis_title=period_label,
        yaxis_title="Total Demand (Units)",
        height=400,
        hovermode='x unified',
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        )
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption("💡 Select a specific SKU above to view detailed forecast with confidence intervals")


def _render_forecast_table(demand_forecast_df):
    """Render searchable forecast table"""

    st.markdown("#### SKU Forecast Summary")

    # Search and filter
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_term = st.text_input("🔍 Search SKU", placeholder="Type to filter...", key="forecast_search")

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
        filtered_df = filtered_df[filtered_df['sku'].str.contains(search_term, case=False, na=False)]

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

    # Display table
    display_cols = ['sku', 'primary_forecast_daily', 'forecast_total_qty', 'forecast_confidence',
                    'demand_pattern', 'forecast_method', 'historical_days']

    if all(col in filtered_df.columns for col in display_cols):
        display_df = filtered_df[display_cols].copy()
        display_df.columns = ['SKU', 'Daily Forecast', '90-Day Total', 'Confidence',
                              'Pattern', 'Method', 'History (periods)']

        # Format numbers
        display_df['Daily Forecast'] = display_df['Daily Forecast'].apply(lambda x: f"{x:,.1f}")
        display_df['90-Day Total'] = display_df['90-Day Total'].apply(lambda x: f"{x:,.0f}")

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
