"""
Event-Driven Backtesting Engine — Streamlit UI
===============================================
Architecture:
    DataHandler  →  MarketEvent
    Strategy     →  SignalEvent
    Portfolio    →  OrderEvent
    Broker       →  FillEvent  →  Portfolio.update()
"""

from __future__ import annotations

import queue
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Event-Driven Backtester",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* ── global background ── */
    .stApp { background-color: #0E1117; }
    section[data-testid="stSidebar"] { background-color: #161B22; }

    /* ── metric cards ── */
    div[data-testid="metric-container"] {
        background: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 14px 18px;
    }
    div[data-testid="metric-container"] label { color: #8B949E !important; font-size: 0.78rem; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #E6EDF3 !important; font-size: 1.4rem; font-weight: 600;
    }

    /* ── section titles ── */
    h1, h2, h3 { color: #E6EDF3 !important; }

    /* ── tab labels ── */
    button[data-baseweb="tab"] { color: #8B949E; font-size: 0.9rem; }
    button[data-baseweb="tab"][aria-selected="true"] { color: #4C9BE8 !important; }

    /* ── run button ── */
    div.stButton > button {
        background: #4C9BE8; color: white; border: none;
        border-radius: 6px; padding: 0.5rem 1.4rem;
        font-weight: 600; width: 100%; font-size: 0.95rem;
    }
    div.stButton > button:hover { background: #3A82D0; }

    /* ── dataframe ── */
    div[data-testid="stDataFrame"] { border: 1px solid #30363D; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────────────────────────

class EventType(Enum):
    MARKET = auto()
    SIGNAL = auto()
    ORDER  = auto()
    FILL   = auto()


class Direction(Enum):
    LONG  = "LONG"
    SHORT = "SHORT"
    EXIT  = "EXIT"


@dataclass
class Event:
    type: EventType


@dataclass
class MarketEvent(Event):
    type: EventType = field(default=EventType.MARKET, init=False)


@dataclass
class SignalEvent(Event):
    symbol:    str
    direction: Direction
    strength:  float = 1.0
    type: EventType = field(default=EventType.SIGNAL, init=False)


@dataclass
class OrderEvent(Event):
    symbol:    str
    quantity:  int
    direction: Direction
    type: EventType = field(default=EventType.ORDER, init=False)


@dataclass
class FillEvent(Event):
    symbol:     str
    quantity:   int
    direction:  Direction
    fill_price: float
    commission: float
    type: EventType = field(default=EventType.FILL, init=False)


# ─────────────────────────────────────────────────────────────────────────────
# Data Handler
# ─────────────────────────────────────────────────────────────────────────────

class DataHandler:
    def __init__(self, symbols: list[str], start: str, end: str, events: queue.Queue):
        self.symbols = symbols
        self.events  = events
        self.idx     = 0
        self.continue_backtest = True

        raw = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)
        if len(symbols) == 1:
            raw.columns = pd.MultiIndex.from_product([raw.columns, symbols])
        self.data  = raw
        self.dates = self.data.index

    def get_latest_bar(self, symbol: str) -> Optional[pd.Series]:
        if self.idx == 0:
            return None
        return self.data.iloc[self.idx - 1]

    def get_latest_bars(self, symbol: str, n: int = 1) -> pd.DataFrame:
        start = max(0, self.idx - n)
        return self.data.iloc[start : self.idx]

    def update_bars(self):
        if self.idx < len(self.dates):
            self.idx += 1
            self.events.put(MarketEvent())
        else:
            self.continue_backtest = False


# ─────────────────────────────────────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────────────────────────────────────

class Strategy(ABC):
    @abstractmethod
    def calculate_signals(self, event: Event) -> None: ...


class SMACrossStrategy(Strategy):
    """Long when fast MA > slow MA, exit otherwise."""

    def __init__(
        self,
        symbols: list[str],
        events: queue.Queue,
        data: DataHandler,
        fast: int = 20,
        slow: int = 50,
    ):
        self.symbols   = symbols
        self.events    = events
        self.data      = data
        self.fast      = fast
        self.slow      = slow
        self.invested  = {s: False for s in symbols}
        self.trade_log: list[dict] = []

    def calculate_signals(self, event: Event) -> None:
        if event.type != EventType.MARKET:
            return
        for symbol in self.symbols:
            bars = self.data.get_latest_bars(symbol, self.slow + 1)
            if len(bars) < self.slow:
                continue
            closes  = bars["Close"][symbol].values
            fast_ma = closes[-self.fast:].mean()
            slow_ma = closes[-self.slow:].mean()
            date    = self.data.dates[self.data.idx - 1]

            if fast_ma > slow_ma and not self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.LONG))
                self.invested[symbol] = True
                self.trade_log.append({"date": date, "symbol": symbol, "signal": "BUY"})
            elif fast_ma < slow_ma and self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.EXIT))
                self.invested[symbol] = False
                self.trade_log.append({"date": date, "symbol": symbol, "signal": "SELL"})


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────────────────────────

class Portfolio:
    def __init__(
        self,
        data: DataHandler,
        events: queue.Queue,
        symbols: list[str],
        initial_capital: float = 100_000.0,
        position_fraction: float = 0.95,
    ):
        self.data      = data
        self.events    = events
        self.symbols   = symbols
        self.capital   = initial_capital
        self.fraction  = position_fraction
        self.positions = {s: 0 for s in symbols}
        self.equity: list[tuple] = []

    def _current_price(self, symbol: str) -> float:
        bar = self.data.get_latest_bar(symbol)
        return float(bar["Close"][symbol])

    def on_signal(self, event: SignalEvent) -> None:
        price = self._current_price(event.symbol)
        if event.direction == Direction.LONG:
            qty = int((self.capital * self.fraction) / price)
            if qty > 0:
                self.events.put(OrderEvent(event.symbol, qty, Direction.LONG))
        elif event.direction == Direction.EXIT:
            qty = self.positions[event.symbol]
            if qty > 0:
                self.events.put(OrderEvent(event.symbol, qty, Direction.EXIT))

    def on_fill(self, event: FillEvent) -> None:
        sign = 1 if event.direction == Direction.LONG else -1
        self.positions[event.symbol] += sign * event.quantity
        cost = sign * event.quantity * event.fill_price + event.commission
        self.capital -= cost

    def update_equity(self) -> None:
        if self.data.idx == 0:
            return
        date = self.data.dates[self.data.idx - 1]
        mkt_value = sum(self.positions[s] * self._current_price(s) for s in self.symbols)
        self.equity.append((date, self.capital + mkt_value))

    def equity_series(self) -> pd.Series:
        dates, values = zip(*self.equity)
        return pd.Series(values, index=dates, name="equity")


# ─────────────────────────────────────────────────────────────────────────────
# Broker
# ─────────────────────────────────────────────────────────────────────────────

class SimulatedBroker:
    COMMISSION_RATE = 0.001

    def __init__(self, data: DataHandler, events: queue.Queue):
        self.data   = data
        self.events = events

    def execute_order(self, event: OrderEvent) -> None:
        bar        = self.data.get_latest_bar(event.symbol)
        fill_price = float(bar["Open"][event.symbol])
        commission = fill_price * event.quantity * self.COMMISSION_RATE
        self.events.put(FillEvent(event.symbol, event.quantity, event.direction, fill_price, commission))


# ─────────────────────────────────────────────────────────────────────────────
# Performance
# ─────────────────────────────────────────────────────────────────────────────

def compute_performance(equity: pd.Series, initial_capital: float) -> dict:
    returns      = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / initial_capital) - 1
    years        = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr         = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1
    sharpe       = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    rolling_max  = equity.cummax()
    drawdown     = (equity - rolling_max) / rolling_max
    max_dd       = drawdown.min()
    volatility   = returns.std() * np.sqrt(252)
    calmar       = cagr / abs(max_dd) if max_dd != 0 else 0
    return {
        "total_return": total_return,
        "cagr":         cagr,
        "sharpe":       sharpe,
        "max_dd":       max_dd,
        "volatility":   volatility,
        "calmar":       calmar,
        "drawdown":     drawdown,
        "returns":      returns,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backtest runner
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(
    symbols: list[str],
    start: str,
    end: str,
    initial_capital: float,
    fast_window: int,
    slow_window: int,
) -> tuple[pd.Series, dict, list[dict]]:
    events    = queue.Queue()
    data      = DataHandler(symbols, start, end, events)
    strategy  = SMACrossStrategy(symbols, events, data, fast_window, slow_window)
    portfolio = Portfolio(data, events, symbols, initial_capital)
    broker    = SimulatedBroker(data, events)

    while data.continue_backtest:
        data.update_bars()
        while not events.empty():
            event = events.get()
            if event.type == EventType.MARKET:
                strategy.calculate_signals(event)
                portfolio.update_equity()
            elif event.type == EventType.SIGNAL:
                portfolio.on_signal(event)
            elif event.type == EventType.ORDER:
                broker.execute_order(event)
            elif event.type == EventType.FILL:
                portfolio.on_fill(event)

    equity = portfolio.equity_series()
    perf   = compute_performance(equity, initial_capital)
    return equity, perf, strategy.trade_log


# ─────────────────────────────────────────────────────────────────────────────
# Plots
# ─────────────────────────────────────────────────────────────────────────────

BG    = "#0E1117"
PANEL = "#161B22"
BLUE  = "#4C9BE8"
RED   = "#E84C4C"
GRAY  = "#8B949E"
GRID  = "#21262D"


def _base_layout(**kwargs) -> dict:
    return dict(
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        font=dict(color=GRAY, size=12),
        xaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor=GRID, zeroline=False),
        legend=dict(bgcolor=PANEL, bordercolor=GRID, borderwidth=1),
        margin=dict(l=50, r=20, t=40, b=40),
        **kwargs,
    )


def plot_equity(equity: pd.Series, bench_equity: pd.Series, trade_log: list[dict]) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity.index, y=equity,
        name="Strategy", line=dict(color=BLUE, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=bench_equity.index, y=bench_equity,
        name="Benchmark", line=dict(color=GRAY, width=1.5, dash="dot"),
    ))

    # trade markers
    df_trades = pd.DataFrame(trade_log)
    if not df_trades.empty:
        for signal, color, sym in [("BUY", "#2ECC71", "triangle-up"), ("SELL", RED, "triangle-down")]:
            mask = df_trades["signal"] == signal
            sub  = df_trades[mask]
            if sub.empty:
                continue
            # match equity value at trade date
            yvals = [equity.asof(d) if d in equity.index or d > equity.index[0] else None for d in sub["date"]]
            fig.add_trace(go.Scatter(
                x=sub["date"], y=yvals,
                mode="markers",
                name=signal,
                marker=dict(symbol=sym, size=10, color=color, line=dict(color="white", width=1)),
            ))

    fig.update_layout(title="Equity Curve vs Benchmark", **_base_layout())
    return fig


def plot_drawdown(drawdown: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown.index, y=drawdown * 100,
        fill="tozeroy", fillcolor="rgba(232,76,76,0.25)",
        line=dict(color=RED, width=1.5),
        name="Drawdown (%)",
    ))
    fig.update_layout(title="Drawdown", yaxis_ticksuffix="%", **_base_layout())
    return fig


def plot_returns_dist(returns: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=returns * 100,
        nbinsx=60,
        marker_color=BLUE,
        opacity=0.8,
        name="Daily returns",
    ))
    fig.add_vline(x=0, line_color=GRAY, line_dash="dot")
    fig.update_layout(
        title="Daily Returns Distribution",
        xaxis_title="Return (%)",
        yaxis_title="Count",
        **_base_layout(),
    )
    return fig


def plot_rolling_sharpe(returns: pd.Series, window: int = 63) -> go.Figure:
    rs = returns.rolling(window).mean() / returns.rolling(window).std() * np.sqrt(252)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rs.index, y=rs,
        line=dict(color=BLUE, width=1.5),
        name=f"Rolling Sharpe ({window}d)",
    ))
    fig.add_hline(y=0, line_color=GRAY, line_dash="dot")
    fig.update_layout(title=f"Rolling Sharpe Ratio ({window}-day)", **_base_layout())
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Parameters")
    st.markdown("---")

    raw_symbols = st.text_input(
        "Symbols (comma-separated)",
        value="AAPL, MSFT",
        help="e.g. AAPL, MSFT, GOOGL",
    )
    symbols = [s.strip().upper() for s in raw_symbols.split(",") if s.strip()]

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start date", value=pd.Timestamp("2015-01-01"))
    with col2:
        end = st.date_input("End date", value=pd.Timestamp("2024-01-01"))

    st.markdown("#### Strategy - SMA Crossover")
    fast_window = st.slider("Fast window", 5, 100, 20, step=5)
    slow_window = st.slider("Slow window", 20, 300, 50, step=10)
    if fast_window >= slow_window:
        st.warning("Fast window must be < slow window.")

    st.markdown("#### Portfolio")
    initial_capital = st.number_input(
        "Initial capital ($)", min_value=10_000, max_value=10_000_000,
        value=100_000, step=10_000,
    )
    benchmark = st.text_input("Benchmark ticker", value="SPY").strip().upper()

    st.markdown("---")
    run_btn = st.button("▶ Run backtest", disabled=(fast_window >= slow_window))

    st.markdown(
        """
        <div style='margin-top:2rem; font-size:0.75rem; color:#555; line-height:1.6'>
        <b style='color:#8B949E'>Architecture</b><br>
        DataHandler → MarketEvent<br>
        Strategy → SignalEvent<br>
        Portfolio → OrderEvent<br>
        Broker → FillEvent
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main area
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("# 📈 Event-Driven Backtesting Engine")
st.markdown(
    f"**SMA Crossover** ({fast_window}/{slow_window}) — "
    f"**Symbols:** {', '.join(symbols)} — "
    f"**Capital:** ${initial_capital:,.0f}"
)
st.markdown("---")

# ── Run ──────────────────────────────────────────────────────────────────────
if not run_btn:
    st.info("Configure parameters in the sidebar, then click **▶ Run backtest**.")
else:
    try:
        equity, perf, trade_log = run_backtest(
            symbols, str(start), str(end),
            initial_capital, fast_window, slow_window,
        )
    except Exception as e:
        st.error(f"Backtest failed: {e}")
        st.stop()

    # benchmark
    bench_raw    = yf.download(benchmark, start=str(start), end=str(end), auto_adjust=True, progress=False)
    bench_close  = bench_raw["Close"].squeeze()
    bench_equity = bench_close / bench_close.iloc[0] * equity.iloc[0]
    bench_equity = bench_equity.reindex(equity.index, method="ffill")

    # benchmark perf
    bench_perf = compute_performance(bench_equity, equity.iloc[0])

    # ── KPI cards ────────────────────────────────────────────────────────────
    st.markdown("### Performance Summary")

    def fmt_pct(v): return f"{v:.2%}"
    def fmt_f(v):   return f"{v:.2f}"

    cols = st.columns(6)
    metrics = [
        ("Total Return", fmt_pct(perf["total_return"]), fmt_pct(perf["total_return"] - bench_perf["total_return"])),
        ("CAGR",         fmt_pct(perf["cagr"]),         fmt_pct(perf["cagr"] - bench_perf["cagr"])),
        ("Sharpe Ratio", fmt_f(perf["sharpe"]),         fmt_f(perf["sharpe"] - bench_perf["sharpe"])),
        ("Max Drawdown", fmt_pct(perf["max_dd"]),       fmt_pct(perf["max_dd"] - bench_perf["max_dd"])),
        ("Volatility",   fmt_pct(perf["volatility"]),   fmt_pct(perf["volatility"] - bench_perf["volatility"])),
        ("Calmar Ratio", fmt_f(perf["calmar"]),         fmt_f(perf["calmar"] - bench_perf["calmar"])),
    ]
    for col, (label, val, delta) in zip(cols, metrics):
        col.metric(label, val, delta)

    st.markdown("---")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Equity Curve", "📉 Drawdown", "📊 Returns", "📋 Trades"])

    with tab1:
        st.plotly_chart(plot_equity(equity, bench_equity, trade_log), width='stretch')

    with tab2:
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(plot_drawdown(perf["drawdown"]), width='stretch')
        with c2:
            st.plotly_chart(plot_rolling_sharpe(perf["returns"]), width='stretch')

    with tab3:
        st.plotly_chart(plot_returns_dist(perf["returns"]), width='stretch')

    with tab4:
        if trade_log:
            df_log = pd.DataFrame(trade_log)
            df_log["date"] = pd.to_datetime(df_log["date"]).dt.strftime("%Y-%m-%d")
            df_log.columns = ["Date", "Symbol", "Signal"]
            st.dataframe(
                df_log.sort_values("Date", ascending=False),
                width='stretch',
                hide_index=True,
            )
            st.caption(f"Total trades: {len(df_log)} - BUY: {(df_log['Signal']=='BUY').sum()} / SELL: {(df_log['Signal']=='SELL').sum()}")
        else:
            st.info("No trades generated.")
