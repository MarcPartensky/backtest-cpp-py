"""
Event-driven backtesting engine.

Architecture:
    DataHandler  →  MarketEvent
    Strategy     →  SignalEvent
    Portfolio    →  OrderEvent
    Broker       →  FillEvent  →  Portfolio.update()

Usage:
    python backtest.py
"""

from __future__ import annotations

import queue
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


# ── Events ────────────────────────────────────────────────────────────────────

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


# ── Data Handler ──────────────────────────────────────────────────────────────

class DataHandler:
    """
    Pulls OHLCV from yfinance and streams bars one at a time,
    simulating a live feed.
    """

    def __init__(self, symbols: list[str], start: str, end: str, events: queue.Queue):
        self.symbols  = symbols
        self.events   = events
        self.data     = {}
        self.idx      = 0
        self.continue_backtest = True

        raw = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)
        if len(symbols) == 1:
            raw.columns = pd.MultiIndex.from_product([raw.columns, symbols])
        self.data = raw
        self.dates = self.data.index

    def get_latest_bar(self, symbol: str) -> Optional[pd.Series]:
        if self.idx == 0:
            return None
        row = self.data.iloc[self.idx - 1]
        return row

    def get_latest_bars(self, symbol: str, n: int = 1) -> pd.DataFrame:
        start = max(0, self.idx - n)
        return self.data.iloc[start : self.idx]

    def update_bars(self):
        if self.idx < len(self.dates):
            self.idx += 1
            self.events.put(MarketEvent())
        else:
            self.continue_backtest = False


# ── Strategy ──────────────────────────────────────────────────────────────────

class Strategy(ABC):
    @abstractmethod
    def calculate_signals(self, event: Event) -> None: ...


class SMACrossStrategy(Strategy):
    """
    Classic dual moving average crossover.
    Long when fast MA > slow MA, exit otherwise.
    """

    def __init__(
        self,
        symbols: list[str],
        events: queue.Queue,
        data: DataHandler,
        fast: int = 20,
        slow: int = 50,
    ):
        self.symbols = symbols
        self.events  = events
        self.data    = data
        self.fast    = fast
        self.slow    = slow
        self.invested: dict[str, bool] = {s: False for s in symbols}

    def calculate_signals(self, event: Event) -> None:
        if event.type != EventType.MARKET:
            return

        for symbol in self.symbols:
            bars = self.data.get_latest_bars(symbol, self.slow + 1)
            if len(bars) < self.slow:
                continue

            closes = bars["Close"][symbol].values
            fast_ma = closes[-self.fast :].mean()
            slow_ma = closes[-self.slow :].mean()

            if fast_ma > slow_ma and not self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.LONG))
                self.invested[symbol] = True
            elif fast_ma < slow_ma and self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.EXIT))
                self.invested[symbol] = False


# ── Portfolio ─────────────────────────────────────────────────────────────────

class Portfolio:
    """
    Tracks positions, cash, and equity curve.
    Fixed fractional position sizing.
    """

    def __init__(
        self,
        data: DataHandler,
        events: queue.Queue,
        symbols: list[str],
        initial_capital: float = 100_000.0,
        position_fraction: float = 0.95,
    ):
        self.data       = data
        self.events     = events
        self.symbols    = symbols
        self.capital    = initial_capital
        self.fraction   = position_fraction
        self.positions  = {s: 0 for s in symbols}
        self.equity     = []  # (date, total_equity)

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
        mkt_value = sum(
            self.positions[s] * self._current_price(s) for s in self.symbols
        )
        self.equity.append((date, self.capital + mkt_value))

    def equity_series(self) -> pd.Series:
        dates, values = zip(*self.equity)
        return pd.Series(values, index=dates, name="equity")


# ── Broker (simulated) ────────────────────────────────────────────────────────

class SimulatedBroker:
    """
    Fills orders at next bar's open with flat commission model.
    """

    COMMISSION_RATE = 0.001  # 0.1% per trade

    def __init__(self, data: DataHandler, events: queue.Queue):
        self.data   = data
        self.events = events

    def execute_order(self, event: OrderEvent) -> None:
        bar = self.data.get_latest_bar(event.symbol)
        fill_price = float(bar["Open"][event.symbol])
        commission = fill_price * event.quantity * self.COMMISSION_RATE
        self.events.put(
            FillEvent(event.symbol, event.quantity, event.direction, fill_price, commission)
        )


# ── Performance ───────────────────────────────────────────────────────────────

def performance_report(equity: pd.Series, initial_capital: float) -> dict:
    returns = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / initial_capital) - 1
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1
    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = drawdown.min()
    return {
        "Total return":    f"{total_return:.2%}",
        "CAGR":            f"{cagr:.2%}",
        "Sharpe ratio":    f"{sharpe:.2f}",
        "Max drawdown":    f"{max_dd:.2%}",
        "Volatility ann.": f"{returns.std() * np.sqrt(252):.2%}",
    }


def plot_results(equity: pd.Series, benchmark_ticker: str, start: str, end: str):
    bench_raw = yf.download(benchmark_ticker, start=start, end=end, auto_adjust=True, progress=False)
    bench = bench_raw["Close"].squeeze()
    bench_equity = bench / bench.iloc[0] * equity.iloc[0]
    bench_equity = bench_equity.reindex(equity.index, method="ffill")

    fig = plt.figure(figsize=(14, 9), facecolor="#0E1117")
    gs = gridspec.GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.05)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    for ax in [ax1, ax2, ax3]:
        ax.set_facecolor("#0E1117")
        ax.tick_params(colors="gray")
        ax.spines[:].set_color("#333")

    ax1.plot(equity.index, equity, color="#4C9BE8", lw=1.5, label="Strategy")
    ax1.plot(bench_equity.index, bench_equity, color="#888", lw=1, linestyle="--", label=benchmark_ticker)
    ax1.set_ylabel("Portfolio value ($)", color="gray")
    ax1.legend(facecolor="#0E1117", labelcolor="white")
    ax1.set_title("Equity Curve", color="white", pad=10)
    plt.setp(ax1.get_xticklabels(), visible=False)

    returns = equity.pct_change().dropna()
    ax2.bar(returns.index, returns, color=np.where(returns >= 0, "#4C9BE8", "#E84C4C"), width=1)
    ax2.axhline(0, color="#444", lw=0.5)
    ax2.set_ylabel("Daily return", color="gray")
    plt.setp(ax2.get_xticklabels(), visible=False)

    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    ax3.fill_between(drawdown.index, drawdown, 0, color="#E84C4C", alpha=0.6)
    ax3.set_ylabel("Drawdown", color="gray")

    plt.savefig("backtest_results.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print("Saved: backtest_results.png")


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_backtest(
    symbols:         list[str]  = ["AAPL"],
    start:           str        = "2018-01-01",
    end:             str        = "2024-01-01",
    initial_capital: float      = 100_000.0,
    fast_window:     int        = 20,
    slow_window:     int        = 50,
    benchmark:       str        = "SPY",
):
    events = queue.Queue()

    data      = DataHandler(symbols, start, end, events)
    strategy  = SMACrossStrategy(symbols, events, data, fast_window, slow_window)
    portfolio = Portfolio(data, events, symbols, initial_capital)
    broker    = SimulatedBroker(data, events)

    print(f"Running backtest: {symbols} | {start} → {end}")
    print(f"SMA({fast_window}/{slow_window}) | Capital: ${initial_capital:,.0f}\n")

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
    report = performance_report(equity, initial_capital)

    print("── Performance ──────────────────────────")
    for k, v in report.items():
        print(f"  {k:<20} {v}")
    print("─────────────────────────────────────────\n")

    plot_results(equity, benchmark, start, end)
    return equity, report


if __name__ == "__main__":
    run_backtest(
        symbols=["AAPL", "MSFT"],
        start="2015-01-01",
        end="2024-01-01",
        fast_window=20,
        slow_window=50,
    )
