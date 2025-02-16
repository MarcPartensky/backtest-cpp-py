"""
Event-Driven Backtesting Engine
================================
Single Streamlit entry point.
Sidebar lets you choose between:
  - Python engine  (strategies package, runs inline)
  - C++ core       (compiled binary, reads results/*.csv)
"""

from __future__ import annotations
import os
import subprocess
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Event-Driven Backtester",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
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
div.stButton > button {
    background: #4C9BE8; color: white; border: none;
    border-radius: 6px; padding: 0.5rem 1.4rem;
    font-weight: 600; width: 100%;
}
div.stButton > button:hover { background: #3A82D0; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

BG    = "#0E1117"
PANEL = "#161B22"
BLUE  = "#4C9BE8"
RED   = "#E84C4C"
GRAY  = "#8B949E"
GRID  = "#21262D"
GREEN = "#2ECC71"

CORE_BINARY = "./build/backtest"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_layout(**kw) -> dict:
    return dict(
        plot_bgcolor=BG, paper_bgcolor=BG,
        font=dict(color=GRAY, size=12),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        legend=dict(bgcolor=PANEL, bordercolor=GRID, borderwidth=1),
        margin=dict(l=50, r=20, t=40, b=40), **kw,
    )

def fmt_pct(v: float) -> str: return f"{v:.2%}"
def fmt_f(v: float)   -> str: return f"{v:.2f}"

def load_benchmark(ticker: str, start: str, end: str, ref_value: float) -> pd.Series | None:
    try:
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
        bench = raw["Close"].squeeze()
        return (bench / bench.iloc[0] * ref_value)
    except Exception:
        return None

def compute_performance(equity: pd.Series, initial_capital: float) -> dict:
    returns     = equity.pct_change().dropna()
    total_ret   = (equity.iloc[-1] / initial_capital) - 1
    years       = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr        = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1
    sharpe      = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    rolling_max = equity.cummax()
    drawdown    = (equity - rolling_max) / rolling_max
    max_dd      = drawdown.min()
    vol         = returns.std() * np.sqrt(252)
    calmar      = cagr / abs(max_dd) if max_dd != 0 else 0
    return dict(total_return=total_ret, cagr=cagr, sharpe=sharpe,
                max_dd=max_dd, volatility=vol, calmar=calmar,
                drawdown=drawdown, returns=returns)

# ── Plots (shared by both engines) ───────────────────────────────────────────

def plot_equity(equity: pd.Series, bench: pd.Series | None, trades: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity.index, y=equity,
        name="Strategy", line=dict(color=BLUE, width=2)))
    if bench is not None:
        b = bench.reindex(equity.index, method="ffill")
        fig.add_trace(go.Scatter(x=b.index, y=b,
            name="Benchmark", line=dict(color=GRAY, width=1.5, dash="dot")))
    if not trades.empty:
        for sig, color, sym in [("BUY", GREEN, "triangle-up"), ("SELL", RED, "triangle-down")]:
            sub = trades[trades["signal"] == sig]
            if sub.empty: continue
            yvals = [equity.asof(d) for d in pd.to_datetime(sub["date"])]
            fig.add_trace(go.Scatter(x=sub["date"], y=yvals, mode="markers", name=sig,
                marker=dict(symbol=sym, size=10, color=color,
                            line=dict(color="white", width=1))))
    fig.update_layout(title="Equity Curve vs Benchmark", **_base_layout())
    return fig

def plot_drawdown(drawdown: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown * 100,
        fill="tozeroy", fillcolor="rgba(232,76,76,0.25)",
        line=dict(color=RED, width=1.5), name="Drawdown (%)"))
    fig.update_layout(title="Drawdown", yaxis_ticksuffix="%", **_base_layout())
    return fig

def plot_rolling_sharpe(returns: pd.Series, window: int = 63) -> go.Figure:
    rs = returns.rolling(window).mean() / returns.rolling(window).std() * np.sqrt(252)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rs.index, y=rs,
        line=dict(color=BLUE, width=1.5), name=f"Rolling Sharpe ({window}d)"))
    fig.add_hline(y=0, line_color=GRAY, line_dash="dot")
    fig.update_layout(title=f"Rolling Sharpe ({window}-day)", **_base_layout())
    return fig

def plot_returns_dist(returns: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=returns * 100, nbinsx=60,
        marker_color=BLUE, opacity=0.8, name="Daily returns"))
    fig.add_vline(x=0, line_color=GRAY, line_dash="dot")
    fig.update_layout(title="Daily Returns Distribution",
        xaxis_title="Return (%)", yaxis_title="Count", **_base_layout())
    return fig

def render_results(equity: pd.Series, perf: dict, trades: pd.DataFrame,
                   bench_ticker: str, initial_capital: float):
    start_str = equity.index[0].strftime("%Y-%m-%d")
    end_str   = equity.index[-1].strftime("%Y-%m-%d")
    bench = load_benchmark(bench_ticker, start_str, end_str, equity.iloc[0])

    # KPIs
    st.markdown("### Performance Summary")
    bench_perf = compute_performance(bench.reindex(equity.index, method="ffill"), equity.iloc[0]) \
                 if bench is not None else None

    cols = st.columns(6)
    kpis = [
        ("Total Return", fmt_pct(perf["total_return"]),
         fmt_pct(perf["total_return"] - bench_perf["total_return"]) if bench_perf else None),
        ("CAGR",         fmt_pct(perf["cagr"]),
         fmt_pct(perf["cagr"] - bench_perf["cagr"]) if bench_perf else None),
        ("Sharpe Ratio", fmt_f(perf["sharpe"]),
         fmt_f(perf["sharpe"] - bench_perf["sharpe"]) if bench_perf else None),
        ("Max Drawdown", fmt_pct(perf["max_dd"]),
         fmt_pct(perf["max_dd"] - bench_perf["max_dd"]) if bench_perf else None),
        ("Volatility",   fmt_pct(perf["volatility"]),
         fmt_pct(perf["volatility"] - bench_perf["volatility"]) if bench_perf else None),
        ("Calmar Ratio", fmt_f(perf["calmar"]),
         fmt_f(perf["calmar"] - bench_perf["calmar"]) if bench_perf else None),
    ]
    for col, (label, val, delta) in zip(cols, kpis):
        col.metric(label, val, delta)

    st.markdown("---")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Equity Curve", "📉 Drawdown", "📊 Returns", "📋 Trades"])

    with tab1:
        st.plotly_chart(plot_equity(equity, bench, trades), width='stretch')

    with tab2:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(plot_drawdown(perf["drawdown"]), width='stretch')
        with c2:
            st.plotly_chart(plot_rolling_sharpe(perf["returns"]), width='stretch')

    with tab3:
        st.plotly_chart(plot_returns_dist(perf["returns"]), width='stretch')

    with tab4:
        if not trades.empty:
            df = trades.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df.columns = [c.capitalize() for c in df.columns]
            st.dataframe(df.sort_values("Date", ascending=False),
                         width='stretch', hide_index=True)
            buys  = (df["Signal"] == "BUY").sum()
            sells = (df["Signal"] == "SELL").sum()
            st.caption(f"Total trades: {len(df)} - BUY: {buys} / SELL: {sells}")
        else:
            st.info("No trades generated.")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📈 Backtester")
    st.markdown("---")

    engine = st.radio("Engine", ["Python  (strategies)", "C++  (core)"],
                      help="Python runs inline. C++ requires a compiled binary.")
    use_cpp = engine.startswith("C++")

    st.markdown("---")
    st.markdown("#### Data")
    raw_symbols = st.text_input("Symbols", value="AAPL, MSFT")
    symbols     = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
    col1, col2  = st.columns(2)
    with col1:
        start = st.date_input("Start", value=pd.Timestamp("2015-01-01"))
    with col2:
        end   = st.date_input("End",   value=pd.Timestamp("2024-01-01"))

    st.markdown("#### Strategy - SMA Crossover")
    fast_window = st.slider("Fast window", 5,  100, 20, step=5)
    slow_window = st.slider("Slow window", 20, 300, 50, step=10)
    if fast_window >= slow_window:
        st.warning("Fast window must be < slow window.")

    st.markdown("#### Portfolio")
    initial_capital = st.number_input("Capital ($)", min_value=10_000,
                                      max_value=10_000_000, value=100_000, step=10_000)
    benchmark = st.text_input("Benchmark", value="SPY").strip().upper()

    if use_cpp:
        st.markdown("#### C++ binary")
        binary_path = st.text_input("Binary path", value=CORE_BINARY)
        data_dir    = st.text_input("Data dir",    value="data")
        results_dir = st.text_input("Results dir", value="results")
        binary_ok   = os.path.isfile(binary_path)
        if not binary_ok:
            st.error(f"Binary not found: `{binary_path}`")
            st.code("cmake -B build -DCMAKE_BUILD_TYPE=Release\ncmake --build build -j4",
                    language="bash")

    st.markdown("---")
    run_btn = st.button(
        "▶ Run backtest",
        disabled=(fast_window >= slow_window) or (use_cpp and not binary_ok)
    )

    # architecture note
    if use_cpp:
        st.markdown("""
        <div style='margin-top:1rem;font-size:0.72rem;color:#555;line-height:1.7'>
        <b style='color:#8B949E'>core/ (C++17)</b><br>
        std::variant + std::visit<br>
        fills at next bar open<br>
        exports results/*.csv
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='margin-top:1rem;font-size:0.72rem;color:#555;line-height:1.7'>
        <b style='color:#8B949E'>strategies/ (Python)</b><br>
        queue.Queue dispatch<br>
        yfinance data feed<br>
        runs inline
        </div>""", unsafe_allow_html=True)

# ── Main area ─────────────────────────────────────────────────────────────────

engine_label = "C++ core" if use_cpp else "Python strategies"
st.markdown("# 📈 Event-Driven Backtesting Engine")
st.markdown(
    f"**Engine:** {engine_label} - "
    f"**SMA** ({fast_window}/{slow_window}) - "
    f"**Symbols:** {', '.join(symbols)} - "
    f"**Capital:** ${initial_capital:,.0f}"
)
st.markdown("---")

if not run_btn:
    st.info("Configure parameters in the sidebar, then click **▶ Run backtest**.")
    st.stop()

# ── Python engine ─────────────────────────────────────────────────────────────

if not use_cpp:
    try:
        from strategies import run_backtest
        equity, perf, trade_log = run_backtest(
            symbols, str(start), str(end), initial_capital, fast_window, slow_window
        )
        trades = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()
    except Exception as e:
        st.error(f"Python engine error: {e}")
        st.stop()

    render_results(equity, perf, trades, benchmark, initial_capital)

# ── C++ engine ────────────────────────────────────────────────────────────────

else:
    sym_arg = ",".join(symbols)
    cmd = [binary_path, data_dir, sym_arg,
           str(fast_window), str(slow_window), str(int(initial_capital))]

    st.code(" ".join(cmd), language="bash")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        st.error("C++ engine timed out after 120s.")
        st.stop()
    except FileNotFoundError:
        st.error(f"Binary not found: `{binary_path}`")
        st.stop()

    if proc.returncode != 0:
        st.error("C++ engine failed.")
        st.code(proc.stderr, language="bash")
        st.stop()

    # show C++ stdout (perf table)
    with st.expander("C++ engine output", expanded=False):
        st.code(proc.stdout, language="bash")

    # load results
    equity_path = os.path.join(results_dir, "equity.csv")
    trades_path = os.path.join(results_dir, "trades.csv")
    perf_path   = os.path.join(results_dir, "performance.csv")

    if not os.path.exists(equity_path):
        st.error(f"No equity.csv found in `{results_dir}/`.")
        st.stop()

    equity  = pd.read_csv(equity_path, index_col="date", parse_dates=True)["equity"]
    trades  = pd.read_csv(trades_path) if os.path.exists(trades_path) else pd.DataFrame()
    perf_df = pd.read_csv(perf_path, index_col="metric") if os.path.exists(perf_path) else None

    def get_metric(name: str) -> float:
        if perf_df is not None and name in perf_df.index:
            return float(perf_df.loc[name, "value"])
        return float("nan")

    returns     = equity.pct_change().dropna()
    rolling_max = equity.cummax()
    drawdown    = (equity - rolling_max) / rolling_max

    perf = dict(
        total_return = get_metric("total_return"),
        cagr         = get_metric("cagr"),
        sharpe       = get_metric("sharpe"),
        max_dd       = get_metric("max_drawdown"),
        volatility   = get_metric("volatility"),
        calmar       = get_metric("calmar"),
        drawdown     = drawdown,
        returns      = returns,
    )

    render_results(equity, perf, trades, benchmark, initial_capital)
