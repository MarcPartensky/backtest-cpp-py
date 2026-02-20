"""
Event-Driven Backtesting Engine
================================
Single Streamlit entry point — controls everything:
  - Data download (yfinance -> CSV)
  - C++ build (cmake)
  - Engine selection (Python / C++)
  - Backtest execution + visualization
"""

from __future__ import annotations
import os, sys
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

st.markdown(
    """
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
div.stButton > button:disabled { background: #2a2a3a; color: #555; }
</style>
""",
    unsafe_allow_html=True,
)

BG = "#0E1117"
PANEL = "#161B22"
BLUE = "#4C9BE8"
RED = "#E84C4C"
GRAY = "#8B949E"
GRID = "#21262D"
GREEN = "#2ECC71"

CORE_BINARY = "./build/backtest"
RESULTS_DIR = "results"
DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "backtest",
    "data",
)


def _base_layout(**kw) -> dict:
    return dict(
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        font=dict(color=GRAY, size=12),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        legend=dict(bgcolor=PANEL, bordercolor=GRID, borderwidth=1),
        margin=dict(l=50, r=20, t=40, b=40),
        **kw,
    )


def fmt_pct(v: float) -> str:
    return f"{v:.2%}"


def fmt_f(v: float) -> str:
    return f"{v:.2f}"


def data_exists(symbols: list[str]) -> bool:
    return all(os.path.isfile(f"{DATA_DIR}/{s}.csv") for s in symbols)


def binary_exists() -> bool:
    return os.path.isfile(CORE_BINARY)


def load_benchmark(ticker: str, start: str, end: str, ref: float) -> pd.Series | None:
    try:
        raw = yf.download(
            ticker, start=start, end=end, auto_adjust=True, progress=False
        )
        b = raw["Close"].squeeze()
        return b / b.iloc[0] * ref
    except Exception:
        return None


def compute_performance(equity: pd.Series, initial_capital: float) -> dict:
    returns = equity.pct_change().dropna()
    total_ret = (equity.iloc[-1] / initial_capital) - 1
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = drawdown.min()
    vol = returns.std() * np.sqrt(252)
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0
    return dict(
        total_return=total_ret,
        cagr=cagr,
        sharpe=sharpe,
        max_dd=max_dd,
        volatility=vol,
        calmar=calmar,
        drawdown=drawdown,
        returns=returns,
    )


def plot_equity(
    equity: pd.Series, bench: pd.Series | None, trades: pd.DataFrame
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=equity.index, y=equity, name="Strategy", line=dict(color=BLUE, width=2)
        )
    )
    if bench is not None:
        b = bench.reindex(equity.index, method="ffill")
        fig.add_trace(
            go.Scatter(
                x=b.index,
                y=b,
                name="Benchmark",
                line=dict(color=GRAY, width=1.5, dash="dot"),
            )
        )
    if not trades.empty:
        for sig, color, sym in [
            ("BUY", GREEN, "triangle-up"),
            ("SELL", RED, "triangle-down"),
        ]:
            sub = trades[trades["signal"] == sig]
            if sub.empty:
                continue
            yvals = [equity.asof(d) for d in pd.to_datetime(sub["date"])]
            fig.add_trace(
                go.Scatter(
                    x=sub["date"],
                    y=yvals,
                    mode="markers",
                    name=sig,
                    marker=dict(
                        symbol=sym,
                        size=10,
                        color=color,
                        line=dict(color="white", width=1),
                    ),
                )
            )
    fig.update_layout(title="Equity Curve vs Benchmark", **_base_layout())
    return fig


def plot_drawdown(drawdown: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown * 100,
            fill="tozeroy",
            fillcolor="rgba(232,76,76,0.25)",
            line=dict(color=RED, width=1.5),
            name="Drawdown (%)",
        )
    )
    fig.update_layout(title="Drawdown", yaxis_ticksuffix="%", **_base_layout())
    return fig


def plot_rolling_sharpe(returns: pd.Series, window: int = 63) -> go.Figure:
    rs = returns.rolling(window).mean() / returns.rolling(window).std() * np.sqrt(252)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=rs.index,
            y=rs,
            line=dict(color=BLUE, width=1.5),
            name=f"Rolling Sharpe ({window}d)",
        )
    )
    fig.add_hline(y=0, line_color=GRAY, line_dash="dot")
    fig.update_layout(title=f"Rolling Sharpe ({window}-day)", **_base_layout())
    return fig


def plot_returns_dist(returns: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=returns * 100,
            nbinsx=60,
            marker_color=BLUE,
            opacity=0.8,
            name="Daily returns",
        )
    )
    fig.add_vline(x=0, line_color=GRAY, line_dash="dot")
    fig.update_layout(
        title="Daily Returns Distribution",
        xaxis_title="Return (%)",
        yaxis_title="Count",
        **_base_layout(),
    )
    return fig


def render_results(
    equity: pd.Series,
    perf: dict,
    trades: pd.DataFrame,
    bench_ticker: str,
    initial_capital: float,
):
    bench = load_benchmark(
        bench_ticker,
        equity.index[0].strftime("%Y-%m-%d"),
        equity.index[-1].strftime("%Y-%m-%d"),
        equity.iloc[0],
    )
    bench_perf = (
        compute_performance(bench.reindex(equity.index, method="ffill"), equity.iloc[0])
        if bench is not None
        else None
    )

    st.markdown("### Performance Summary")
    cols = st.columns(6)
    kpis = [
        (
            "Total Return",
            fmt_pct(perf["total_return"]),
            (
                fmt_pct(perf["total_return"] - bench_perf["total_return"])
                if bench_perf
                else None
            ),
        ),
        (
            "CAGR",
            fmt_pct(perf["cagr"]),
            fmt_pct(perf["cagr"] - bench_perf["cagr"]) if bench_perf else None,
        ),
        (
            "Sharpe Ratio",
            fmt_f(perf["sharpe"]),
            fmt_f(perf["sharpe"] - bench_perf["sharpe"]) if bench_perf else None,
        ),
        (
            "Max Drawdown",
            fmt_pct(perf["max_dd"]),
            fmt_pct(perf["max_dd"] - bench_perf["max_dd"]) if bench_perf else None,
        ),
        (
            "Volatility",
            fmt_pct(perf["volatility"]),
            (
                fmt_pct(perf["volatility"] - bench_perf["volatility"])
                if bench_perf
                else None
            ),
        ),
        (
            "Calmar Ratio",
            fmt_f(perf["calmar"]),
            fmt_f(perf["calmar"] - bench_perf["calmar"]) if bench_perf else None,
        ),
    ]
    for col, (label, val, delta) in zip(cols, kpis):
        col.metric(label, val, delta)

    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📈 Equity Curve", "📉 Drawdown", "📊 Returns", "📋 Trades"]
    )

    with tab1:
        st.plotly_chart(plot_equity(equity, bench, trades), width="stretch")
    with tab2:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(plot_drawdown(perf["drawdown"]), width="stretch")
        with c2:
            st.plotly_chart(plot_rolling_sharpe(perf["returns"]), width="stretch")
    with tab3:
        st.plotly_chart(plot_returns_dist(perf["returns"]), width="stretch")
    with tab4:
        if not trades.empty:
            df = trades.copy()
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df.columns = [c.capitalize() for c in df.columns]
            st.dataframe(
                df.sort_values("Date", ascending=False),
                width="stretch",
                hide_index=True,
            )
            buys = (df["Signal"] == "BUY").sum()
            sells = (df["Signal"] == "SELL").sum()
            st.caption(f"Total trades: {len(df)} - BUY: {buys} / SELL: {sells}")
        else:
            st.info("No trades generated.")


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📈 Backtester")

    st.markdown("---")
    st.markdown("#### 1. Data")
    raw_symbols = st.text_input("Symbols", value="AAPL, MSFT")
    symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start", value=pd.Timestamp("2015-01-01"))
    with col2:
        end = st.date_input("End", value=pd.Timestamp("2024-01-01"))

    if data_exists(symbols):
        st.success(f"Data ready: {', '.join(symbols)}")
    else:
        missing = [s for s in symbols if not os.path.isfile(f"{DATA_DIR}/{s}.csv")]
        st.warning(f"Missing: {', '.join(missing)}")
    download_btn = st.button("⬇ Download data")

    st.markdown("---")
    st.markdown("#### 2. Engine")
    engine = st.radio(
        "Engine", ["Python  (strategies)", "C++  (core)"], label_visibility="collapsed"
    )
    use_cpp = engine.startswith("C++")

    if use_cpp:
        if binary_exists():
            st.success("Binary ready: `./build/backtest`")
        else:
            st.warning("Binary not built yet.")
        build_btn = st.button("🔨 Build C++ core")
    else:
        build_btn = False

    st.markdown("---")
    st.markdown("#### 3. Strategy")
    fast_window = st.slider("Fast window", 5, 100, 20, step=5)
    slow_window = st.slider("Slow window", 20, 300, 50, step=10)
    if fast_window >= slow_window:
        st.warning("Fast must be < slow.")
    initial_capital = st.number_input(
        "Capital ($)",
        min_value=10_000,
        max_value=10_000_000,
        value=100_000,
        step=10_000,
    )
    benchmark = st.text_input("Benchmark", value="SPY").strip().upper()

    st.markdown("---")
    can_run = (
        data_exists(symbols)
        and fast_window < slow_window
        and (not use_cpp or binary_exists())
    )
    run_btn = st.button("▶ Run backtest", disabled=not can_run)

# ── Main area ─────────────────────────────────────────────────────────────────

st.markdown("# 📈 Event-Driven Backtesting Engine")
st.markdown(
    f"**Engine:** {'C++ core' if use_cpp else 'Python strategies'} - "
    f"**SMA** ({fast_window}/{slow_window}) - "
    f"**Symbols:** {', '.join(symbols)} - "
    f"**Capital:** ${initial_capital:,.0f}"
)
st.markdown("---")

# ── Download ──────────────────────────────────────────────────────────────────

if download_btn:
    cmd = (
        [sys.executable, "scripts/download_data.py"]
        + symbols
        + ["--start", str(start), "--end", str(end), "--outdir", DATA_DIR]
    )
    with st.status("Downloading data...", expanded=True) as status:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        st.code(proc.stdout + proc.stderr, language="bash")
        status.update(
            label="Download complete." if proc.returncode == 0 else "Download failed.",
            state="complete" if proc.returncode == 0 else "error",
        )


# ── Build ─────────────────────────────────────────────────────────────────────

if build_btn:
    with st.status("Building C++ core...", expanded=True) as status:
        cfg = subprocess.run(
            ["cmake", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"],
            capture_output=True,
            text=True,
        )
        bld = subprocess.run(
            ["cmake", "--build", "build", "-j4"], capture_output=True, text=True
        )
        st.code(cfg.stdout + cfg.stderr + bld.stdout + bld.stderr, language="bash")
        ok = cfg.returncode == 0 and bld.returncode == 0
        status.update(
            label="Build complete." if ok else "Build failed.",
            state="complete" if ok else "error",
        )

# ── Idle ──────────────────────────────────────────────────────────────────────

if not run_btn:
    steps = []
    if not data_exists(symbols):
        steps.append("- Click **⬇ Download data**")
    if use_cpp and not binary_exists():
        steps.append("- Click **🔨 Build C++ core**")
    if fast_window >= slow_window:
        steps.append("- Fix fast/slow windows")
    st.info(
        "Ready - click **▶ Run backtest**."
        if not steps
        else "Before running:\n" + "\n".join(steps)
    )
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
    cmd = [
        CORE_BINARY,
        DATA_DIR,
        ",".join(symbols),
        str(fast_window),
        str(slow_window),
        str(int(initial_capital)),
    ]

    with st.status("Running C++ core...", expanded=False) as status:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        status.update(
            label="C++ core finished." if proc.returncode == 0 else "C++ core failed.",
            state="complete" if proc.returncode == 0 else "error",
        )
        if proc.returncode != 0:
            st.code(proc.stderr, language="bash")
            st.stop()

    with st.expander("C++ engine output", expanded=False):
        st.code(proc.stdout, language="bash")

    equity_path = os.path.join(RESULTS_DIR, "equity.csv")
    trades_path = os.path.join(RESULTS_DIR, "trades.csv")
    perf_path = os.path.join(RESULTS_DIR, "performance.csv")

    if not os.path.exists(equity_path):
        st.error(f"No equity.csv in `{RESULTS_DIR}/`.")
        st.stop()

    equity = pd.read_csv(equity_path, index_col="date", parse_dates=True)["equity"]
    trades = pd.read_csv(trades_path) if os.path.exists(trades_path) else pd.DataFrame()
    perf_df = (
        pd.read_csv(perf_path, index_col="metric")
        if os.path.exists(perf_path)
        else None
    )

    def get_metric(name: str) -> float:
        if perf_df is not None and name in perf_df.index:
            return float(perf_df.loc[name, "value"])
        return float("nan")

    returns = equity.pct_change().dropna()
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max

    perf = dict(
        total_return=get_metric("total_return"),
        cagr=get_metric("cagr"),
        sharpe=get_metric("sharpe"),
        max_dd=get_metric("max_drawdown"),
        volatility=get_metric("volatility"),
        calmar=get_metric("calmar"),
        drawdown=drawdown,
        returns=returns,
    )
    render_results(equity, perf, trades, benchmark, initial_capital)
