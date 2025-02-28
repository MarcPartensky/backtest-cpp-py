from __future__ import annotations
import queue
from typing import Optional

import pandas as pd
import yfinance as yf

from .events import MarketEvent


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
