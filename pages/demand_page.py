"""
Demand Forecasting Dashboard Page

Displays statistical demand forecasts with interactive visualizations
and SKU-level analysis.
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
    st.title("📈 Demand Forecasting & Analysis")

    # Check if forecast data exists
    if demand_forecast_df.empty:
        st.warning("⚠️ No demand forecasts available. Ensure DELIVERIES.csv has sufficient historical data (minimum 30 days per SKU).")
        return

    # Get summary metrics
    metrics = get_forecast_summary_metrics(demand_forecast_df)

    # ===== HEADER KPIs =====
    st.markdown("### 🎯 Forecast Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="SKUs Forecasted",
            value=f"{metrics.get('total_skus_forecasted', 0):,}"
        )

    with col2:
        total_forecast = metrics.get('total_forecast_demand', 0)
        st.metric(
            label="Total Forecast (90 days)",
            value=f"{total_forecast:,.0f} units"
        )

    with col3:
        avg_mape = metrics.get('avg_mape', np.nan)
        if pd.notna(avg_mape):
            st.metric(
                label="Avg Forecast Accuracy (MAPE)",
                value=f"{avg_mape:.1f}%",
                delta=f"{'Good' if avg_mape < 30 else 'Needs Improvement'}",
                delta_color="normal" if avg_mape < 30 else "inverse"
            )
        else:
            st.metric(
                label="Avg Forecast Accuracy (MAPE)",
                value="N/A",
                help="Insufficient data for backtesting"
            )

    with col4:
        high_conf = metrics.get('high_confidence_count', 0)
        total = metrics.get('total_skus_forecasted', 1)
        conf_pct = (high_conf / total * 100) if total > 0 else 0
        st.metric(
            label="High Confidence Forecasts",
            value=f"{high_conf} ({conf_pct:.0f}%)"
        )

    st.divider()

    # ===== TABBED INTERFACE =====
    tab1, tab2, tab3 = st.tabs([
        "📊 Forecast Summary",
        "🎯 Forecast Accuracy",
        "📈 Demand Trends & Analysis"
    ])

    # ===== TAB 1: Forecast Summary (Merged Overview + SKU-Level Search) =====
    with tab1:
        st.markdown("#### Top 20 SKUs by Forecasted Demand")

        # Top forecasted SKUs table
        top_20 = demand_forecast_df.nlargest(20, 'forecast_total_qty').copy()

        display_cols = [
            'sku', 'forecast_total_qty', 'primary_forecast_daily', 'forecast_confidence',
            'demand_pattern', 'mape', 'forecast_method', 'historical_days'
        ]

        top_20_display = top_20[display_cols].copy()
        top_20_display.columns = [
            'SKU', 'Total Forecast (90d)', 'Daily Forecast', 'Confidence',
            'Demand Pattern', 'MAPE %', 'Method', 'History (days)'
        ]

        # Format numeric columns
        top_20_display['Total Forecast (90d)'] = top_20_display['Total Forecast (90d)'].apply(lambda x: f"{x:,.0f}")
        top_20_display['Daily Forecast'] = top_20_display['Daily Forecast'].apply(lambda x: f"{x:,.1f}")
        top_20_display['MAPE %'] = top_20_display['MAPE %'].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
        )

        st.dataframe(
            top_20_display,
            width='stretch',
            height=400
        )

        # Forecast confidence distribution
        st.markdown("#### Forecast Confidence Distribution")

        col1, col2 = st.columns(2)

        with col1:
            # Confidence pie chart
            confidence_counts = demand_forecast_df['forecast_confidence'].value_counts().reset_index()
            confidence_counts.columns = ['Confidence', 'Count']

            fig_conf = px.pie(
                confidence_counts,
                values='Count',
                names='Confidence',
                title='Forecast Confidence Levels',
                color='Confidence',
                color_discrete_map={
                    'High': '#28a745',
                    'Medium': '#ffc107',
                    'Low': '#fd7e14',
                    'Very Low': '#dc3545'
                }
            )
            fig_conf.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_conf, width='stretch')

        with col2:
            # Demand pattern distribution
            pattern_counts = demand_forecast_df['demand_pattern'].value_counts().reset_index()
            pattern_counts.columns = ['Pattern', 'Count']

            fig_pattern = px.bar(
                pattern_counts.head(8),
                x='Count',
                y='Pattern',
                orientation='h',
                title='Top Demand Patterns',
                color='Count',
                color_continuous_scale='Blues'
            )
            fig_pattern.update_layout(showlegend=False)
            st.plotly_chart(fig_pattern, width='stretch')

        # Forecast method breakdown
        st.markdown("#### Forecast Method Distribution")

        method_counts = demand_forecast_df['forecast_method'].value_counts().reset_index()
        method_counts.columns = ['Method', 'SKU Count']

        col1, col2 = st.columns([1, 2])

        with col1:
            st.dataframe(method_counts, width='stretch', hide_index=True)

        with col2:
            fig_method = px.bar(
                method_counts,
                x='Method',
                y='SKU Count',
                title='Forecasting Methods Used',
                color='SKU Count',
                color_continuous_scale='Greens'
            )
            st.plotly_chart(fig_method, width='stretch')

        # === SKU-LEVEL SEARCH & FILTER (Merged from old Tab 2) ===
        st.divider()
        st.markdown("#### Search & Filter SKU Forecasts")

        # Search and filter controls
        col1, col2, col3 = st.columns(3)

        with col1:
            search_sku = st.text_input("🔍 Search by SKU", placeholder="Enter SKU...")

        with col2:
            confidence_filter = st.multiselect(
                "Filter by Confidence",
                options=['High', 'Medium', 'Low', 'Very Low'],
                default=['High', 'Medium', 'Low', 'Very Low']
            )

        with col3:
            min_forecast = st.number_input(
                "Min Forecast Qty",
                min_value=0,
                value=0,
                step=100
            )

        # Apply filters
        filtered_df = demand_forecast_df.copy()

        if search_sku:
            filtered_df = filtered_df[filtered_df['sku'].str.contains(search_sku, case=False, na=False)]

        if confidence_filter:
            filtered_df = filtered_df[filtered_df['forecast_confidence'].isin(confidence_filter)]

        if min_forecast > 0:
            filtered_df = filtered_df[filtered_df['forecast_total_qty'] >= min_forecast]

        st.markdown(f"**Showing {len(filtered_df)} of {len(demand_forecast_df)} SKUs**")

        # Display filtered forecasts
        display_cols = [
            'sku', 'primary_forecast_daily', 'forecast_total_qty', 'forecast_lower_bound',
            'forecast_upper_bound', 'forecast_confidence', 'forecast_confidence_score',
            'demand_pattern', 'mape', 'demand_cv', 'forecast_method'
        ]

        filtered_display = filtered_df[display_cols].copy()
        filtered_display.columns = [
            'SKU', 'Daily Forecast', 'Total (90d)', 'Lower Bound', 'Upper Bound',
            'Confidence', 'Confidence Score', 'Pattern', 'MAPE %', 'Demand CV %', 'Method'
        ]

        # Format columns
        filtered_display['Daily Forecast'] = filtered_display['Daily Forecast'].apply(lambda x: f"{x:,.1f}")
        filtered_display['Total (90d)'] = filtered_display['Total (90d)'].apply(lambda x: f"{x:,.0f}")
        filtered_display['Lower Bound'] = filtered_display['Lower Bound'].apply(lambda x: f"{x:,.0f}")
        filtered_display['Upper Bound'] = filtered_display['Upper Bound'].apply(lambda x: f"{x:,.0f}")
        filtered_display['Confidence Score'] = filtered_display['Confidence Score'].apply(lambda x: f"{x:.0f}")
        filtered_display['MAPE %'] = filtered_display['MAPE %'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
        filtered_display['Demand CV %'] = filtered_display['Demand CV %'].apply(lambda x: f"{x:.1f}%")

        st.dataframe(
            filtered_display,
            width='stretch',
            height=500
        )

        # Export filtered data
        if not filtered_df.empty:
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Forecast Data (CSV)",
                data=csv,
                file_name=f"demand_forecast_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

    # ===== TAB 2: Forecast Accuracy =====
    with tab2:
        st.markdown("#### Forecast Accuracy Analysis")

        if forecast_accuracy_df.empty:
            st.info("ℹ️ Insufficient historical data for accuracy backtesting. Need at least 60 days per SKU.")
        else:
            # Accuracy summary
            avg_mape = forecast_accuracy_df['mape'].mean()
            median_mape = forecast_accuracy_df['mape'].median()
            avg_mae = forecast_accuracy_df['mae'].mean()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Average MAPE", f"{avg_mape:.1f}%")

            with col2:
                st.metric("Median MAPE", f"{median_mape:.1f}%")

            with col3:
                st.metric("Average MAE", f"{avg_mae:.1f} units")

            st.divider()

            # Best and worst forecasts
            best_forecasts, worst_forecasts = get_forecast_accuracy_rankings(forecast_accuracy_df, top_n=10)

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("##### ✅ Top 10 Most Accurate Forecasts")
                best_display = best_forecasts[['sku', 'mape', 'mae', 'actual_avg_demand', 'forecast_avg_demand']].copy()
                best_display.columns = ['SKU', 'MAPE %', 'MAE', 'Actual Avg', 'Forecast Avg']
                best_display['MAPE %'] = best_display['MAPE %'].apply(lambda x: f"{x:.1f}%")
                best_display['MAE'] = best_display['MAE'].apply(lambda x: f"{x:.1f}")
                best_display['Actual Avg'] = best_display['Actual Avg'].apply(lambda x: f"{x:.1f}")
                best_display['Forecast Avg'] = best_display['Forecast Avg'].apply(lambda x: f"{x:.1f}")
                st.dataframe(best_display, width='stretch', hide_index=True)

            with col2:
                st.markdown("##### ❌ Top 10 Least Accurate Forecasts")
                worst_display = worst_forecasts[['sku', 'mape', 'mae', 'actual_avg_demand', 'forecast_avg_demand']].copy()
                worst_display.columns = ['SKU', 'MAPE %', 'MAE', 'Actual Avg', 'Forecast Avg']
                worst_display['MAPE %'] = worst_display['MAPE %'].apply(lambda x: f"{x:.1f}%")
                worst_display['MAE'] = worst_display['MAE'].apply(lambda x: f"{x:.1f}")
                worst_display['Actual Avg'] = worst_display['Actual Avg'].apply(lambda x: f"{x:.1f}")
                worst_display['Forecast Avg'] = worst_display['Forecast Avg'].apply(lambda x: f"{x:.1f}")
                st.dataframe(worst_display, width='stretch', hide_index=True)

            # MAPE distribution histogram
            st.markdown("#### MAPE Distribution")

            fig_mape = px.histogram(
                forecast_accuracy_df,
                x='mape',
                nbins=30,
                title='Forecast Error Distribution (MAPE)',
                labels={'mape': 'MAPE (%)', 'count': 'Number of SKUs'},
                color_discrete_sequence=['#007bff']
            )
            fig_mape.add_vline(x=avg_mape, line_dash="dash", line_color="red", annotation_text=f"Avg: {avg_mape:.1f}%")
            st.plotly_chart(fig_mape, width='stretch')

        # ===== FORECAST VS ACTUAL COMPARISON (FROM SNAPSHOTS) =====
        st.divider()
        st.markdown("#### Forecast vs Actual Comparison (Historical Snapshots)")

        # Load historical snapshots
        snapshots_df = load_forecast_snapshots()

        if snapshots_df.empty:
            st.info("ℹ️ No historical forecast snapshots found. Save snapshots regularly to track forecast vs actual accuracy over time.")
            st.markdown("**How it works:**")
            st.markdown("1. Save forecast snapshots regularly (recommended: weekly)")
            st.markdown("2. System compares past forecasts against actual deliveries that occurred")
            st.markdown("3. Track forecast accuracy trends and bias over time")
        else:
            # Compare snapshots vs actual
            comparison_df = compare_forecast_vs_actual(snapshots_df, deliveries_df)

            if comparison_df.empty:
                st.warning("⚠️ Snapshot comparison not yet available. Forecast periods haven't ended yet, or no actual deliveries found.")
            else:
                # Calculate bias metrics
                bias_metrics = calculate_forecast_bias(comparison_df)

                # Display bias metrics
                st.markdown("##### Forecast Bias Analysis")

                bias_col1, bias_col2, bias_col3, bias_col4 = st.columns(4)

                with bias_col1:
                    st.metric(
                        "Total Forecast",
                        f"{bias_metrics.get('total_forecast', 0):,.0f} units"
                    )

                with bias_col2:
                    st.metric(
                        "Total Actual",
                        f"{bias_metrics.get('total_actual', 0):,.0f} units"
                    )

                with bias_col3:
                    bias_pct = bias_metrics.get('bias_pct', 0)
                    bias_direction = bias_metrics.get('bias_direction', 'Neutral')
                    st.metric(
                        "Forecast Bias",
                        f"{bias_pct:+.1f}%",
                        delta=bias_direction,
                        delta_color="inverse" if abs(bias_pct) > 10 else "off"
                    )

                with bias_col4:
                    avg_abs_error = bias_metrics.get('avg_abs_error_pct', 0)
                    st.metric(
                        "Avg Absolute Error",
                        f"{avg_abs_error:.1f}%"
                    )

                st.divider()

                # Forecast vs Actual by Snapshot
                st.markdown("##### Forecast vs Actual by Snapshot Date")

                # Aggregate by snapshot date
                snapshot_summary = comparison_df.groupby('snapshot_date').agg({
                    'forecast_total_qty': 'sum',
                    'actual_qty': 'sum',
                    'abs_pct_error': 'mean',
                    'sku': 'count'
                }).reset_index()

                snapshot_summary.columns = ['Snapshot Date', 'Total Forecast', 'Total Actual', 'Avg MAPE %', 'SKU Count']

                # Calculate error
                snapshot_summary['Error %'] = ((snapshot_summary['Total Forecast'] - snapshot_summary['Total Actual']) / snapshot_summary['Total Actual'] * 100).fillna(0)

                # Sort by date
                snapshot_summary = snapshot_summary.sort_values('Snapshot Date')

                # Display table
                snapshot_summary_display = snapshot_summary.copy()
                snapshot_summary_display['Snapshot Date'] = snapshot_summary_display['Snapshot Date'].dt.strftime('%Y-%m-%d')
                snapshot_summary_display['Total Forecast'] = snapshot_summary_display['Total Forecast'].apply(lambda x: f"{x:,.0f}")
                snapshot_summary_display['Total Actual'] = snapshot_summary_display['Total Actual'].apply(lambda x: f"{x:,.0f}")
                snapshot_summary_display['Avg MAPE %'] = snapshot_summary_display['Avg MAPE %'].apply(lambda x: f"{x:.1f}%")
                snapshot_summary_display['Error %'] = snapshot_summary_display['Error %'].apply(lambda x: f"{x:+.1f}%")

                st.dataframe(snapshot_summary_display, width='stretch', hide_index=True)

                # Forecast vs Actual Line Chart
                st.markdown("##### Forecast vs Actual Over Time")

                fig_comparison = go.Figure()

                # Actual line
                fig_comparison.add_trace(go.Scatter(
                    x=snapshot_summary['Snapshot Date'],
                    y=snapshot_summary['Total Actual'],
                    mode='lines+markers',
                    name='Actual Demand',
                    line=dict(color='steelblue', width=3),
                    marker=dict(size=8)
                ))

                # Forecast line
                fig_comparison.add_trace(go.Scatter(
                    x=snapshot_summary['Snapshot Date'],
                    y=snapshot_summary['Total Forecast'],
                    mode='lines+markers',
                    name='Forecasted Demand',
                    line=dict(color='orange', width=3, dash='dot'),
                    marker=dict(size=8)
                ))

                fig_comparison.update_layout(
                    title="Forecast vs Actual Demand - Historical Snapshots",
                    xaxis_title="Snapshot Date",
                    yaxis_title="Demand (Units)",
                    height=400,
                    hovermode='x unified'
                )

                st.plotly_chart(fig_comparison, width='stretch')

                # Forecast Accuracy by Category
                if 'category' in comparison_df.columns:
                    st.divider()
                    st.markdown("##### Forecast Accuracy by Category")

                    category_accuracy = comparison_df.groupby('category').agg({
                        'forecast_total_qty': 'sum',
                        'actual_qty': 'sum',
                        'abs_pct_error': 'mean',
                        'sku': 'count'
                    }).reset_index()

                    category_accuracy.columns = ['Category', 'Total Forecast', 'Total Actual', 'Avg MAPE %', 'SKU Count']

                    # Calculate error
                    category_accuracy['Error %'] = ((category_accuracy['Total Forecast'] - category_accuracy['Total Actual']) / category_accuracy['Total Actual'] * 100).fillna(0)

                    # Sort by MAPE
                    category_accuracy = category_accuracy.sort_values('Avg MAPE %')

                    # Display table
                    category_accuracy_display = category_accuracy.copy()
                    category_accuracy_display['Total Forecast'] = category_accuracy_display['Total Forecast'].apply(lambda x: f"{x:,.0f}")
                    category_accuracy_display['Total Actual'] = category_accuracy_display['Total Actual'].apply(lambda x: f"{x:,.0f}")
                    category_accuracy_display['Avg MAPE %'] = category_accuracy_display['Avg MAPE %'].apply(lambda x: f"{x:.1f}%")
                    category_accuracy_display['Error %'] = category_accuracy_display['Error %'].apply(lambda x: f"{x:+.1f}%")

                    st.dataframe(category_accuracy_display, width='stretch', hide_index=True)

    # ===== TAB 3: Demand Trends & Analysis (Merged Patterns + Visualization) =====
    with tab3:
        st.markdown("#### Demand Pattern Analysis")

        # Volatility analysis
        st.markdown("##### Demand Volatility (Coefficient of Variation)")

        # Classify SKUs by volatility
        demand_forecast_df['volatility_class'] = pd.cut(
            demand_forecast_df['demand_cv'],
            bins=[0, 30, 70, 200],
            labels=['Stable', 'Moderate', 'Volatile']
        )

        volatility_counts = demand_forecast_df['volatility_class'].value_counts().reset_index()
        volatility_counts.columns = ['Volatility', 'SKU Count']

        col1, col2 = st.columns(2)

        with col1:
            st.dataframe(volatility_counts, width='stretch', hide_index=True)

            # Top volatile SKUs
            st.markdown("##### Top 10 Most Volatile SKUs")
            volatile_skus = demand_forecast_df.nlargest(10, 'demand_cv')[['sku', 'demand_cv', 'demand_pattern', 'forecast_confidence']]
            volatile_skus.columns = ['SKU', 'CV %', 'Pattern', 'Forecast Confidence']
            volatile_skus['CV %'] = volatile_skus['CV %'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(volatile_skus, width='stretch', hide_index=True)

        with col2:
            fig_vol = px.pie(
                volatility_counts,
                values='SKU Count',
                names='Volatility',
                title='Volatility Distribution',
                color='Volatility',
                color_discrete_map={'Stable': '#28a745', 'Moderate': '#ffc107', 'Volatile': '#dc3545'}
            )
            st.plotly_chart(fig_vol, width='stretch')

        st.divider()

        # Trend analysis
        st.markdown("##### Demand Trends")

        # Classify trends
        demand_forecast_df['trend_class'] = demand_forecast_df['demand_trend_slope'].apply(
            lambda x: 'Growing' if x > 0.5 else ('Declining' if x < -0.5 else 'Flat')
        )

        trend_counts = demand_forecast_df['trend_class'].value_counts().reset_index()
        trend_counts.columns = ['Trend', 'SKU Count']

        col1, col2 = st.columns(2)

        with col1:
            fig_trend = px.bar(
                trend_counts,
                x='Trend',
                y='SKU Count',
                title='Trend Classification',
                color='SKU Count',
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(fig_trend, width='stretch')

        with col2:
            # Top growing SKUs
            st.markdown("##### Top 10 Fastest Growing SKUs")
            growing_skus = demand_forecast_df.nlargest(10, 'demand_trend_slope')[
                ['sku', 'demand_trend_slope', 'primary_forecast_daily', 'demand_pattern']
            ]
            growing_skus.columns = ['SKU', 'Trend Slope', 'Daily Forecast', 'Pattern']
            growing_skus['Trend Slope'] = growing_skus['Trend Slope'].apply(lambda x: f"{x:.2f}")
            growing_skus['Daily Forecast'] = growing_skus['Daily Forecast'].apply(lambda x: f"{x:.1f}")
            st.dataframe(growing_skus, width='stretch', hide_index=True)

        st.divider()

        # Scatter plot: CV vs Forecast Confidence
        st.markdown("##### Demand Volatility vs Forecast Confidence")

        fig_scatter = px.scatter(
            demand_forecast_df,
            x='demand_cv',
            y='forecast_confidence_score',
            color='forecast_confidence',
            size='forecast_total_qty',
            hover_data=['sku', 'demand_pattern'],
            title='Volatility Impact on Forecast Confidence',
            labels={
                'demand_cv': 'Demand Coefficient of Variation (%)',
                'forecast_confidence_score': 'Confidence Score (0-100)',
                'forecast_confidence': 'Confidence Level'
            },
            color_discrete_map={
                'High': '#28a745',
                'Medium': '#ffc107',
                'Low': '#fd7e14',
                'Very Low': '#dc3545'
            }
        )
        st.plotly_chart(fig_scatter, width='stretch')

        # === HISTORICAL DEMAND & FORECAST VISUALIZATION (Merged from old Tab 5) ===
        st.divider()
        st.markdown("#### Historical Demand & Forecast Projection")

        if daily_demand_df.empty:
            st.warning("⚠️ No historical demand data available for visualization.")
        else:
            # Merge category information into daily demand
            if 'category' in demand_forecast_df.columns:
                # Build column list based on what's available
                mapping_cols = ['sku', 'category']
                if 'sku_description' in demand_forecast_df.columns:
                    mapping_cols.append('sku_description')

                category_mapping = demand_forecast_df[mapping_cols].drop_duplicates()
                daily_demand_with_cat = pd.merge(
                    daily_demand_df,
                    category_mapping,
                    on='sku',
                    how='left'
                )
                daily_demand_with_cat['category'] = daily_demand_with_cat['category'].fillna('Uncategorized')
                if 'sku_description' not in daily_demand_with_cat.columns:
                    daily_demand_with_cat['sku_description'] = 'Unknown'
            else:
                daily_demand_with_cat = daily_demand_df.copy()
                daily_demand_with_cat['category'] = 'Uncategorized'
                daily_demand_with_cat['sku_description'] = 'Unknown'

            # ===== FILTERS =====
            st.markdown("##### Filters & Controls")

            filter_col1, filter_col2, filter_col3 = st.columns(3)

            with filter_col1:
                # Aggregation level toggle
                agg_level = st.radio(
                    "View Level",
                    options=["Category Level", "SKU Level"],
                    index=0,
                    help="Category Level shows aggregated demand by category. SKU Level shows individual SKUs."
                )

            with filter_col2:
                # Category multi-select
                available_categories = sorted(daily_demand_with_cat['category'].unique().tolist())
                selected_categories = st.multiselect(
                    "Filter by Category",
                    options=available_categories,
                    default=available_categories,
                    help="Select categories to display"
                )

            with filter_col3:
                # SKU multi-select (filtered by selected categories)
                if selected_categories:
                    available_skus = daily_demand_with_cat[
                        daily_demand_with_cat['category'].isin(selected_categories)
                    ]['sku'].unique().tolist()
                else:
                    available_skus = daily_demand_with_cat['sku'].unique().tolist()

                # Only show SKU selector if SKU Level is selected
                if agg_level == "SKU Level":
                    selected_skus = st.multiselect(
                        "Filter by SKU",
                        options=sorted(available_skus),
                        default=[],
                        help="Select specific SKUs to display. Leave empty to show all SKUs in selected categories.",
                        key="sku_filter_tab5"
                    )
                else:
                    selected_skus = []

            st.divider()

            # ===== GRAPH CONTROLS =====
            st.markdown("##### Graph Display Options")

            control_col1, control_col2, control_col3, control_col4 = st.columns(4)

            with control_col1:
                show_historical = st.checkbox("Historical Actual Demand", value=True)

            with control_col2:
                show_forecast = st.checkbox("Forecast Projection", value=True)

            with control_col3:
                show_confidence = st.checkbox("Confidence Intervals", value=True)

            with control_col4:
                show_trend = st.checkbox("Trend Line", value=True)

            st.divider()

            # ===== PREPARE DATA FOR VISUALIZATION =====

            # Filter by selected categories
            if selected_categories:
                filtered_demand = daily_demand_with_cat[
                    daily_demand_with_cat['category'].isin(selected_categories)
                ].copy()
            else:
                filtered_demand = daily_demand_with_cat.copy()

            # Check if we have data after filtering
            if filtered_demand.empty:
                st.warning("No data available for selected filters.")
            else:
                # Aggregate based on view level
                if agg_level == "Category Level":
                    # Aggregate by category and date
                    agg_demand = filtered_demand.groupby(['category', 'date']).agg({
                        'demand_qty': 'sum'
                    }).reset_index()

                    # Prepare forecast data by category
                    if 'category' in demand_forecast_df.columns and selected_categories:
                        forecast_by_cat = demand_forecast_df[
                            demand_forecast_df['category'].isin(selected_categories)
                        ].groupby('category').agg({
                            'primary_forecast_daily': 'sum',
                            'forecast_lower_bound': 'sum',
                            'forecast_upper_bound': 'sum',
                            'forecast_horizon_days': 'first'
                        }).reset_index()
                    else:
                        forecast_by_cat = pd.DataFrame()

                else:  # SKU Level
                    # Filter by selected SKUs if any specified
                    if selected_skus:
                        filtered_demand = filtered_demand[filtered_demand['sku'].isin(selected_skus)]

                    agg_demand = filtered_demand.copy()

                    # Get forecast data for selected SKUs
                    if selected_skus:
                        forecast_by_sku = demand_forecast_df[demand_forecast_df['sku'].isin(selected_skus)].copy()
                    elif selected_categories:
                        # Show all SKUs in selected categories (limit to top 20 by demand to avoid clutter)
                        top_skus = filtered_demand.groupby('sku')['demand_qty'].sum().nlargest(20).index.tolist()
                        agg_demand = agg_demand[agg_demand['sku'].isin(top_skus)]
                        forecast_by_sku = demand_forecast_df[demand_forecast_df['sku'].isin(top_skus)].copy()
                    else:
                        forecast_by_sku = demand_forecast_df.copy()

                # ===== CREATE TIME-SERIES CHART =====
                fig = go.Figure()

                if agg_level == "Category Level":
                    # Plot each category as a separate line
                    for category in agg_demand['category'].unique():
                        cat_data = agg_demand[agg_demand['category'] == category].sort_values('date')

                        # Historical demand
                        if show_historical:
                            fig.add_trace(go.Scatter(
                                x=cat_data['date'],
                                y=cat_data['demand_qty'],
                                mode='lines+markers',
                                name=f'{category} (Actual)',
                                line=dict(width=2),
                                marker=dict(size=4),
                                hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Demand: %{y:,.0f} units<extra></extra>'
                            ))

                        # Forecast projection
                        if show_forecast and not forecast_by_cat.empty:
                            cat_forecast = forecast_by_cat[forecast_by_cat['category'] == category]

                            if not cat_forecast.empty:
                                forecast_daily = cat_forecast['primary_forecast_daily'].iloc[0]
                                forecast_horizon = int(cat_forecast['forecast_horizon_days'].iloc[0])
                                last_date = cat_data['date'].max()

                                # Create forecast dates
                                forecast_dates = pd.date_range(start=last_date + timedelta(days=1), periods=forecast_horizon, freq='D')
                                forecast_values = [forecast_daily] * forecast_horizon

                                # Add connecting point
                                forecast_dates_with_last = pd.concat([
                                    pd.Series([last_date]),
                                    pd.Series(forecast_dates)
                                ])
                                forecast_values_with_last = [cat_data['demand_qty'].iloc[-1]] + forecast_values

                                fig.add_trace(go.Scatter(
                                    x=forecast_dates_with_last,
                                    y=forecast_values_with_last,
                                    mode='lines',
                                    name=f'{category} (Forecast)',
                                    line=dict(dash='dash', width=2),
                                    hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Forecast: %{y:,.0f} units<extra></extra>'
                                ))

                                # Confidence intervals
                                if show_confidence:
                                    lower_bound_daily = cat_forecast['forecast_lower_bound'].iloc[0] / forecast_horizon
                                    upper_bound_daily = cat_forecast['forecast_upper_bound'].iloc[0] / forecast_horizon

                                    lower_values = [lower_bound_daily] * forecast_horizon
                                    upper_values = [upper_bound_daily] * forecast_horizon

                                    # Upper bound
                                    fig.add_trace(go.Scatter(
                                        x=forecast_dates,
                                        y=upper_values,
                                        mode='lines',
                                        name=f'{category} (Upper Bound)',
                                        line=dict(width=0),
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))

                                    # Lower bound with fill
                                    fig.add_trace(go.Scatter(
                                        x=forecast_dates,
                                        y=lower_values,
                                        mode='lines',
                                        name=f'{category} (Confidence)',
                                        line=dict(width=0),
                                        fill='tonexty',
                                        fillcolor='rgba(128, 128, 128, 0.2)',
                                        showlegend=True,
                                        hoverinfo='skip'
                                    ))

                        # Trend line
                        if show_trend and len(cat_data) > 2:
                            # Calculate linear regression
                            x_numeric = np.arange(len(cat_data))
                            y_values = cat_data['demand_qty'].values

                            # Fit linear trend
                            z = np.polyfit(x_numeric, y_values, 1)
                            p = np.poly1d(z)
                            trend_values = p(x_numeric)

                            fig.add_trace(go.Scatter(
                                x=cat_data['date'],
                                y=trend_values,
                                mode='lines',
                                name=f'{category} (Trend)',
                                line=dict(dash='dot', width=1),
                                hovertemplate='<b>%{fullData.name}</b><br>Date: %{x|%Y-%m-%d}<br>Trend: %{y:,.0f} units<extra></extra>'
                            ))

                else:  # SKU Level
                    # Plot each SKU as a separate line
                    display_skus = agg_demand['sku'].unique()

                    if len(display_skus) > 20:
                        st.warning(f"⚠️ Showing top 20 SKUs by demand out of {len(display_skus)} SKUs. Use SKU filter to select specific SKUs.")
                        display_skus = display_skus[:20]

                    for sku in display_skus:
                        sku_data = agg_demand[agg_demand['sku'] == sku].sort_values('date')
                        sku_desc = sku_data['sku_description'].iloc[0] if 'sku_description' in sku_data.columns else sku

                        # Historical demand
                        if show_historical:
                            fig.add_trace(go.Scatter(
                                x=sku_data['date'],
                                y=sku_data['demand_qty'],
                                mode='lines+markers',
                                name=f'{sku} (Actual)',
                                line=dict(width=2),
                                marker=dict(size=4),
                                hovertemplate=f'<b>{sku_desc}</b><br>Date: %{{x|%Y-%m-%d}}<br>Demand: %{{y:,.0f}} units<extra></extra>'
                            ))

                        # Forecast projection
                        if show_forecast and agg_level == "SKU Level":
                            sku_forecast = demand_forecast_df[demand_forecast_df['sku'] == sku]

                            if not sku_forecast.empty:
                                forecast_daily = sku_forecast['primary_forecast_daily'].iloc[0]
                                forecast_horizon = int(sku_forecast['forecast_horizon_days'].iloc[0])
                                last_date = sku_data['date'].max()

                                # Create forecast dates
                                forecast_dates = pd.date_range(start=last_date + timedelta(days=1), periods=forecast_horizon, freq='D')
                                forecast_values = [forecast_daily] * forecast_horizon

                                # Add connecting point
                                forecast_dates_with_last = pd.concat([
                                    pd.Series([last_date]),
                                    pd.Series(forecast_dates)
                                ])
                                forecast_values_with_last = [sku_data['demand_qty'].iloc[-1]] + forecast_values

                                fig.add_trace(go.Scatter(
                                    x=forecast_dates_with_last,
                                    y=forecast_values_with_last,
                                    mode='lines',
                                    name=f'{sku} (Forecast)',
                                    line=dict(dash='dash', width=2),
                                    hovertemplate=f'<b>{sku_desc} Forecast</b><br>Date: %{{x|%Y-%m-%d}}<br>Forecast: %{{y:,.0f}} units<extra></extra>'
                                ))

                                # Confidence intervals (only if single SKU selected to avoid clutter)
                                if show_confidence and len(display_skus) <= 5:
                                    lower_bound_daily = sku_forecast['forecast_lower_bound'].iloc[0] / forecast_horizon
                                    upper_bound_daily = sku_forecast['forecast_upper_bound'].iloc[0] / forecast_horizon

                                    lower_values = [lower_bound_daily] * forecast_horizon
                                    upper_values = [upper_bound_daily] * forecast_horizon

                                    # Upper bound
                                    fig.add_trace(go.Scatter(
                                        x=forecast_dates,
                                        y=upper_values,
                                        mode='lines',
                                        name=f'{sku} (Upper)',
                                        line=dict(width=0),
                                        showlegend=False,
                                        hoverinfo='skip'
                                    ))

                                    # Lower bound with fill
                                    fig.add_trace(go.Scatter(
                                        x=forecast_dates,
                                        y=lower_values,
                                        mode='lines',
                                        name=f'{sku} (Confidence)',
                                        line=dict(width=0),
                                        fill='tonexty',
                                        fillcolor='rgba(128, 128, 128, 0.2)',
                                        showlegend=True,
                                        hoverinfo='skip'
                                    ))

                # Update layout
                fig.update_layout(
                    title=f"Demand Forecast - {agg_level}",
                    xaxis_title="Date",
                    yaxis_title="Demand (Units)",
                    height=600,
                    hovermode='x unified',
                    legend=dict(
                        orientation="v",
                        yanchor="top",
                        y=1,
                        xanchor="left",
                        x=1.01
                    )
                )

                st.plotly_chart(fig, use_container_width=True)

                # ===== DEMAND STATISTICS SUMMARY =====
                st.divider()
                st.markdown("##### Demand Statistics")

                stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

                with stat_col1:
                    total_historical_demand = filtered_demand['demand_qty'].sum()
                    st.metric("Total Historical Demand", f"{total_historical_demand:,.0f} units")

                with stat_col2:
                    avg_daily_demand = filtered_demand['demand_qty'].mean()
                    st.metric("Avg Daily Demand", f"{avg_daily_demand:,.1f} units")

                with stat_col3:
                    if agg_level == "Category Level":
                        num_entities = len(filtered_demand['category'].unique())
                        st.metric("Categories Displayed", f"{num_entities}")
                    else:
                        num_entities = len(filtered_demand['sku'].unique())
                        st.metric("SKUs Displayed", f"{num_entities}")

                with stat_col4:
                    date_range_days = (filtered_demand['date'].max() - filtered_demand['date'].min()).days
                    st.metric("Historical Days", f"{date_range_days}")

            # ===== FORECAST SNAPSHOT MANAGEMENT =====
            st.divider()
            st.markdown("##### Forecast Snapshot Management")

            snapshot_col1, snapshot_col2 = st.columns(2)

            with snapshot_col1:
                # Display latest snapshot info
                latest_snapshot_date = get_latest_snapshot_date()

                if latest_snapshot_date:
                    st.info(f"📸 Last snapshot saved: {latest_snapshot_date.strftime('%Y-%m-%d')}")
                else:
                    st.info("📸 No snapshots saved yet.")

            with snapshot_col2:
                # Save snapshot button
                if st.button("💾 Save Forecast Snapshot", help="Save current forecast for future accuracy tracking"):
                    success, filepath, message = save_forecast_snapshot(demand_forecast_df)

                    if success:
                        st.success(message)
                    else:
                        st.error(message)
