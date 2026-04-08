from __future__ import annotations
import queue

import pandas as pd

from .events import SignalEvent, FillEvent, OrderEvent, Direction
from .data_handler import DataHandler


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
        mkt  = sum(self.positions[s] * self._current_price(s) for s in self.symbols)
        self.equity.append((date, self.capital + mkt))

    def equity_series(self) -> pd.Series:
        dates, values = zip(*self.equity)
        return pd.Series(values, index=dates, name="equity")
