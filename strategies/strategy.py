from __future__ import annotations
import queue
from abc import ABC, abstractmethod

import numpy as np

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
        self.symbols = symbols
        self.events = events
        self.data = data
        self.fast = fast
        self.slow = slow
        self.invested = {s: False for s in symbols}
        self.trade_log: list[dict] = []

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
            date = self.data.dates[self.data.idx - 1]

            if fast_ma > slow_ma and not self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.LONG))
                self.invested[symbol] = True
                self.trade_log.append({"date": date, "symbol": symbol, "signal": "BUY"})
            elif fast_ma < slow_ma and self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.EXIT))
                self.invested[symbol] = False
                self.trade_log.append(
                    {"date": date, "symbol": symbol, "signal": "SELL"}
                )


class SMACrossWithStopLoss(SMACrossStrategy):
    """SMA Crossover + stop-loss dynamique basé sur l'ATR.

    On sort de position si le prix clôture sous entry_price - atr_mult * ATR(atr_window),
    sans attendre le croisement inverse.
    """

    def __init__(
        self,
        symbols: list[str],
        events: queue.Queue,
        data: DataHandler,
        fast: int = 20,
        slow: int = 50,
        atr_window: int = 14,
        atr_mult: float = 2.0,
    ):
        super().__init__(symbols, events, data, fast, slow)
        self.atr_window = atr_window
        self.atr_mult = atr_mult
        self.stop_price = {s: None for s in symbols}

    def _atr(self, bars, symbol: str) -> float:
        highs = bars["High"][symbol].values[-self.atr_window :]
        lows = bars["Low"][symbol].values[-self.atr_window :]
        return float((highs - lows).mean())

    def calculate_signals(self, event: Event) -> None:
        if event.type != EventType.MARKET:
            return
        for symbol in self.symbols:
            bars = self.data.get_latest_bars(
                symbol, max(self.slow, self.atr_window) + 1
            )
            if len(bars) < self.slow:
                continue
            closes = bars["Close"][symbol].values
            fast_ma = closes[-self.fast :].mean()
            slow_ma = closes[-self.slow :].mean()
            price = closes[-1]
            date = self.data.dates[self.data.idx - 1]
            atr = self._atr(bars, symbol)

            # stop-loss en priorité
            if self.invested[symbol] and self.stop_price[symbol] is not None:
                if price < self.stop_price[symbol]:
                    self.events.put(SignalEvent(symbol, Direction.EXIT))
                    self.invested[symbol] = False
                    self.stop_price[symbol] = None
                    self.trade_log.append(
                        {"date": date, "symbol": symbol, "signal": "STOP"}
                    )
                    continue

            if fast_ma > slow_ma and not self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.LONG))
                self.invested[symbol] = True
                self.stop_price[symbol] = price - self.atr_mult * atr
                self.trade_log.append({"date": date, "symbol": symbol, "signal": "BUY"})
            elif fast_ma < slow_ma and self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.EXIT))
                self.invested[symbol] = False
                self.stop_price[symbol] = None
                self.trade_log.append(
                    {"date": date, "symbol": symbol, "signal": "SELL"}
                )


class SMACrossWithTrendFilter(SMACrossWithStopLoss):
    """SMA Crossover + stop-loss ATR + filtre de tendance longue (SMA200).

    On n'entre LONG que si le prix est au-dessus de sa SMA sur trend_window jours,
    ce qui évite d'acheter en marché baissier.
    """

    def __init__(
        self,
        symbols: list[str],
        events: queue.Queue,
        data: DataHandler,
        fast: int = 20,
        slow: int = 50,
        atr_window: int = 14,
        atr_mult: float = 2.0,
        trend_window: int = 200,
    ):
        super().__init__(symbols, events, data, fast, slow, atr_window, atr_mult)
        self.trend_window = trend_window

    def calculate_signals(self, event: Event) -> None:
        if event.type != EventType.MARKET:
            return
        for symbol in self.symbols:
            n_bars = max(self.slow, self.atr_window, self.trend_window) + 1
            bars = self.data.get_latest_bars(symbol, n_bars)
            if len(bars) < self.slow:
                continue
            closes = bars["Close"][symbol].values
            fast_ma = closes[-self.fast :].mean()
            slow_ma = closes[-self.slow :].mean()
            price = closes[-1]
            date = self.data.dates[self.data.idx - 1]
            atr = self._atr(bars, symbol)

            trend_ma = (
                closes[-self.trend_window :].mean()
                if len(closes) >= self.trend_window
                else None
            )
            in_uptrend = trend_ma is None or price > trend_ma

            # stop-loss en priorité
            if self.invested[symbol] and self.stop_price[symbol] is not None:
                if price < self.stop_price[symbol]:
                    self.events.put(SignalEvent(symbol, Direction.EXIT))
                    self.invested[symbol] = False
                    self.stop_price[symbol] = None
                    self.trade_log.append(
                        {"date": date, "symbol": symbol, "signal": "STOP"}
                    )
                    continue

            if fast_ma > slow_ma and not self.invested[symbol] and in_uptrend:
                self.events.put(SignalEvent(symbol, Direction.LONG))
                self.invested[symbol] = True
                self.stop_price[symbol] = price - self.atr_mult * atr
                self.trade_log.append({"date": date, "symbol": symbol, "signal": "BUY"})
            elif (fast_ma < slow_ma or not in_uptrend) and self.invested[symbol]:
                self.events.put(SignalEvent(symbol, Direction.EXIT))
                self.invested[symbol] = False
                self.stop_price[symbol] = None
                self.trade_log.append(
                    {"date": date, "symbol": symbol, "signal": "SELL"}
                )
