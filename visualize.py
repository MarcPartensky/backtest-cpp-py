#!/usr/bin/env python3
"""
Streamlit visualizer for the C++ backtesting engine.

Reads:  results/equity.csv
        results/trades.csv
        results/performance.csv

Usage:
    streamlit run scripts/visualize.py
"""

import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="C++ Backtester — Results",
    page_icon="⚡",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background-color: #0E1117; }
section[data-testid="stSidebar"] { background-color: #161B22; }
div[data-testid="metric-container"] {
    background: #161B22; border: 1px solid #30363D;
    border-radius: 8px; padding: 14px 18px;
}
div[data-testid="metric-container"] label { color: #8B949E !important; font-size: 0.78rem; }
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color: #E6EDF3 !important; font-size: 1.4rem; font-weight: 600;
}
h1, h2, h3 { color: #E6EDF3 !important; }
button[data-baseweb="tab"] { color: #8B949E; }
button[data-baseweb="tab"][aria-selected="true"] { color: #4C9BE8 !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

BG   = "#0E1117"
PANEL= "#161B22"
BLUE = "#4C9BE8"
RED  = "#E84C4C"
GRAY = "#8B949E"
GRID = "#21262D"
GREEN= "#2ECC71"

def _base_layout(**kw):
    return dict(
        plot_bgcolor=BG, paper_bgcolor=BG,
        font=dict(color=GRAY, size=12),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        legend=dict(bgcolor=PANEL, bordercolor=GRID, borderwidth=1),
        margin=dict(l=50, r=20, t=40, b=40), **kw,
    )

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚡ C++ Backtester")
    st.markdown("---")
    results_dir = st.text_input("Results directory", value="results")
    benchmark   = st.text_input("Benchmark ticker",  value="SPY").strip().upper()
    st.markdown("---")
    st.markdown("""
    <div style='font-size:0.75rem; color:#555; line-height:1.8'>
    <b style='color:#8B949E'>Workflow</b><br>
    1. <code>python scripts/download_data.py AAPL MSFT</code><br>
    2. <code>cmake -B build && cmake --build build</code><br>
    3. <code>./build/backtest data AAPL,MSFT 20 50</code><br>
    4. <code>streamlit run scripts/visualize.py</code>
    </div>
    """, unsafe_allow_html=True)

# ── Load results ──────────────────────────────────────────────────────────────

st.markdown("# ⚡ Event-Driven Backtester — C++ Engine")
st.markdown("---")

equity_path = os.path.join(results_dir, "equity.csv")
trades_path = os.path.join(results_dir, "trades.csv")
perf_path   = os.path.join(results_dir, "performance.csv")

if not os.path.exists(equity_path):
    st.warning(f"No results found in `{results_dir}/`. Run the C++ engine first.")
    st.code(
        "cmake -B build && cmake --build build -j4\n"
        "./build/backtest data AAPL,MSFT 20 50 100000",
        language="bash"
    )
    st.stop()

equity = pd.read_csv(equity_path, index_col="date", parse_dates=True)["equity"]
trades = pd.read_csv(trades_path, parse_dates=["date"]) if os.path.exists(trades_path) else pd.DataFrame()
perf_df= pd.read_csv(perf_path,  index_col="metric")   if os.path.exists(perf_path)   else None

# ── Benchmark ─────────────────────────────────────────────────────────────────

try:
    start_str = equity.index[0].strftime("%Y-%m-%d")
    end_str   = equity.index[-1].strftime("%Y-%m-%d")
    bench_raw = yf.download(benchmark, start=start_str, end=end_str,
                            auto_adjust=True, progress=False)
    bench     = bench_raw["Close"].squeeze()
    bench_eq  = bench / bench.iloc[0] * equity.iloc[0]
    bench_eq  = bench_eq.reindex(equity.index, method="ffill")
    bench_ok  = True
except Exception:
    bench_ok  = False

# ── Derived metrics ───────────────────────────────────────────────────────────

def get_metric(name: str) -> float:
    if perf_df is not None and name in perf_df.index:
        return float(perf_df.loc[name, "value"])
    return float("nan")

returns     = equity.pct_change().dropna()
rolling_max = equity.cummax()
drawdown    = (equity - rolling_max) / rolling_max

# ── KPI cards ─────────────────────────────────────────────────────────────────

st.markdown("### Performance Summary")
c = st.columns(6)
kpis = [
    ("Total Return",    f"{get_metric('total_return'):.2%}"),
    ("CAGR",            f"{get_metric('cagr'):.2%}"),
    ("Sharpe Ratio",    f"{get_metric('sharpe'):.2f}"),
    ("Max Drawdown",    f"{get_metric('max_drawdown'):.2%}"),
    ("Volatility",      f"{get_metric('volatility'):.2%}"),
    ("Calmar Ratio",    f"{get_metric('calmar'):.2f}"),
]
for col, (label, val) in zip(c, kpis):
    col.metric(label, val)

st.markdown("---")

# ── Plots ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(["📈 Equity Curve", "📉 Drawdown", "📊 Returns", "📋 Trades"])

with tab1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity.index, y=equity,
        name="Strategy", line=dict(color=BLUE, width=2)))
    if bench_ok:
        fig.add_trace(go.Scatter(x=bench_eq.index, y=bench_eq,
            name=benchmark, line=dict(color=GRAY, width=1.5, dash="dot")))

    if not trades.empty:
        for sig, color, sym in [("BUY", GREEN, "triangle-up"), ("SELL", RED, "triangle-down")]:
            sub = trades[trades["signal"] == sig]
            if sub.empty: continue
            yvals = [equity.asof(d) for d in sub["date"]]
            fig.add_trace(go.Scatter(x=sub["date"], y=yvals, mode="markers",
                name=sig, marker=dict(symbol=sym, size=10, color=color,
                line=dict(color="white", width=1))))

    fig.update_layout(title="Equity Curve vs Benchmark", **_base_layout())
    st.plotly_chart(fig, width='stretch')

with tab2:
    col1, col2 = st.columns([3, 2])
    with col1:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=drawdown.index, y=drawdown * 100,
            fill="tozeroy", fillcolor="rgba(232,76,76,0.25)",
            line=dict(color=RED, width=1.5), name="Drawdown (%)"))
        fig2.update_layout(title="Drawdown", yaxis_ticksuffix="%", **_base_layout())
        st.plotly_chart(fig2, width='stretch')
    with col2:
        rs = returns.rolling(63).mean() / returns.rolling(63).std() * np.sqrt(252)
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=rs.index, y=rs,
            line=dict(color=BLUE, width=1.5), name="Rolling Sharpe (63d)"))
        fig3.add_hline(y=0, line_color=GRAY, line_dash="dot")
        fig3.update_layout(title="Rolling Sharpe (63-day)", **_base_layout())
        st.plotly_chart(fig3, width='stretch')

with tab3:
    fig4 = go.Figure()
    fig4.add_trace(go.Histogram(x=returns * 100, nbinsx=60,
        marker_color=BLUE, opacity=0.8, name="Daily returns"))
    fig4.add_vline(x=0, line_color=GRAY, line_dash="dot")
    fig4.update_layout(title="Daily Returns Distribution",
        xaxis_title="Return (%)", yaxis_title="Count", **_base_layout())
    st.plotly_chart(fig4, width='stretch')

with tab4:
    if not trades.empty:
        df = trades.copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        df.columns = [c.capitalize() for c in df.columns]
        st.dataframe(df.sort_values("Date", ascending=False),
                     width='stretch', hide_index=True)
        buys  = (df["Signal"] == "BUY").sum()
        sells = (df["Signal"] == "SELL").sum()
        st.caption(f"Total trades: {len(df)} - BUY: {buys} / SELL: {sells}")
    else:
        st.info("No trades file found.")
