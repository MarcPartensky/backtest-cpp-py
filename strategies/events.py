from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto


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
