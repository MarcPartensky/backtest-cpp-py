from __future__ import annotations
import queue
from abc import ABC, abstractmethod

from .events import Event, EventType, SignalEvent, Direction
from .data_handler import DataHandler


class Strategy(ABC):
    @abstractmethod
    def calculate_signals(self, event: Event) -> None: ...


class SMACrossStrategy(Strategy):
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
