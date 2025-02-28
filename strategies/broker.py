from __future__ import annotations
import queue

from .events import OrderEvent, FillEvent, Direction
from .data_handler import DataHandler


class SimulatedBroker:
    COMMISSION_RATE = 0.001

    def __init__(self, data: DataHandler, events: queue.Queue):
        self.data   = data
        self.events = events

    def execute_order(self, event: OrderEvent) -> None:
        bar        = self.data.get_latest_bar(event.symbol)
        fill_price = float(bar["Open"][event.symbol])
        commission = fill_price * event.quantity * self.COMMISSION_RATE
        self.events.put(
            FillEvent(event.symbol, event.quantity, event.direction, fill_price, commission)
        )
