from __future__ import annotations
import queue

import pandas as pd

from .events import EventType
from .data_handler import DataHandler
from .strategy import SMACrossStrategy
from .portfolio import Portfolio
from .broker import SimulatedBroker
from .performance import compute_performance


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
