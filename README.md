# backtest

Event-driven backtesting engine built from scratch. Simulates realistic order execution with a clean separation between data, signal generation, portfolio management, and trade execution.

## Architecture

```
DataHandler  ──► MarketEvent
Strategy     ──► SignalEvent
Portfolio    ──► OrderEvent
Broker       ──► FillEvent ──► Portfolio.update()
```

Each component communicates only through a shared event queue — the same pattern used in production trading systems.

## Features

- **Event-driven loop** — no look-ahead bias, bars are streamed one at a time
- **yfinance integration** — pulls any ticker available on Yahoo Finance
- **SMA crossover strategy** — fast/slow moving average with configurable windows
- **Fixed fractional sizing** — invests a fixed fraction of available capital per trade
- **Simulated broker** — fills at next bar open + flat commission model (0.1%)
- **Performance metrics** — Total return, CAGR, Sharpe ratio, Max drawdown, Annualised volatility
- **Result plot** — equity curve vs benchmark, daily returns bar chart, drawdown chart

## Usage

```bash
pip install -r requirements.txt
python backtest.py
```

Or import and configure programmatically:

```python
from backtest import run_backtest

equity, report = run_backtest(
    symbols=["AAPL", "NVDA", "MSFT"],
    start="2018-01-01",
    end="2024-01-01",
    fast_window=10,
    slow_window=30,
    initial_capital=50_000,
    benchmark="SPY",
)
```

## Extending

To add a new strategy, subclass `Strategy` and implement `calculate_signals`:

```python
class MyStrategy(Strategy):
    def calculate_signals(self, event: Event) -> None:
        if event.type != EventType.MARKET:
            return
        # analyse bars, emit SignalEvent(symbol, Direction.LONG / EXIT)
```

## Output

```
── Performance ──────────────────────────
  Total return         +87.43%
  CAGR                 +9.12%
  Sharpe ratio         0.74
  Max drawdown         -23.18%
  Volatility ann.      14.32%
─────────────────────────────────────────
```

Saves `backtest_results.png` with three panels: equity curve, daily returns, drawdown.
