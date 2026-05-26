# Event-Driven Backtesting Engine

Backtesting engine implemented in two languages with a unified Streamlit interface.
The Python implementation serves as a readable reference; the C++17 core handles
performance-critical runs over long historical series.

```
DataHandler  →  MarketEvent
Strategy     →  SignalEvent
Portfolio    →  OrderEvent
Broker       →  FillEvent  →  Portfolio::update()
```

---

## Why event-driven?

The standard alternative — vectorized backtesting — applies a strategy across an
entire price series at once. This introduces **look-ahead bias**: the strategy can
inadvertently use future information when computing signals, producing results that
are impossible to replicate in live trading.

An event-driven engine eliminates this by processing time strictly forward. Each
bar arrives as a `MarketEvent`, the strategy reacts with a `SignalEvent`, the
portfolio converts it to an `OrderEvent`, and the broker returns a `FillEvent`.
No component can reference data beyond its current position in the queue.

---

## Financial background

### SMA Crossover

The baseline strategy uses two Simple Moving Averages with windows `fast < slow`.

- **Entry:** go long when the fast SMA crosses above the slow SMA — the short-term
  trend accelerating relative to the long-term trend is interpreted as bullish momentum
- **Exit:** close the position when the fast SMA crosses back below the slow SMA

```
fast_ma = mean(Close[-fast:])
slow_ma = mean(Close[-slow:])

signal = LONG  if fast_ma > slow_ma and not invested
signal = EXIT  if fast_ma < slow_ma and invested
```

This is a **trend-following** strategy: it profits in trending markets and
underperforms in mean-reverting or choppy regimes. The SMA windows control the
sensitivity/lag trade-off.

### ATR Stop-Loss

The `SMACrossWithStopLoss` extension adds a dynamic stop-loss derived from the
**Average True Range (ATR)**, a measure of recent realised volatility:

```
ATR(n) = mean(High - Low) over the last n bars   [simplified]

stop_price = entry_price - atr_mult × ATR(atr_window)
```

The stop-loss exits the position if the price closes below `stop_price`, regardless
of the SMA crossover signal. This limits drawdown in fast-moving adverse markets
without waiting for the slower crossover signal to flip.

The parameter `atr_mult` controls the tightness of the stop: a larger multiplier
tolerates more volatility before exiting; a smaller one cuts losses earlier at the
cost of more false exits.

### Trend Filter (SMA 200)

The `SMACrossWithTrendFilter` extension adds a **long-term trend filter**: a long
entry is only allowed if the current price is above its 200-period moving average,
a classic proxy for a bull market regime.

```
trend_ma = mean(Close[-trend_window:])
in_uptrend = price > trend_ma

entry condition: fast_ma > slow_ma AND in_uptrend
```

This avoids buying into crossovers that occur in a broader downtrend, which
historically tend to produce poor risk-adjusted returns. The exit condition is
also extended: the position is closed if either the SMA crossover reverses **or**
the price falls back below the trend MA.

---

## Performance metrics

All metrics are computed on the equity curve and benchmarked against a configurable
index (default: SPY).

### CAGR — Compound Annual Growth Rate

$$\text{CAGR} = \left(\frac{V_{\text{final}}}{V_{\text{initial}}}\right)^{\frac{1}{n}} - 1$$

where $n$ is the number of years. Measures the annualised return as if growth had
been perfectly smooth, making strategies of different durations comparable.

### Sharpe Ratio

$$\text{Sharpe} = \frac{R_p - R_f}{\sigma_p} \times \sqrt{252}$$

where $R_p$ is the mean daily return, $R_f$ the daily risk-free rate, and $\sigma_p$
the standard deviation of daily returns. Penalises both upside and downside
volatility symmetrically.

### Maximum Drawdown

$$\text{MDD} = \min_{t} \frac{V_t - \max_{s \leq t} V_s}{\max_{s \leq t} V_s}$$

The worst peak-to-trough decline over the entire period. Measures the worst
realised loss an investor would have experienced before recovery.

### Calmar Ratio

$$\text{Calmar} = \frac{\text{CAGR}}{|\text{MDD}|}$$

Return per unit of maximum drawdown. Unlike the Sharpe ratio, it uses the
worst-case historical loss as the risk denominator, which is more intuitive for
strategies where tail events dominate the risk profile.

---

## Architecture

```
backtest/
├── core/                   ← C++17 engine (performance-critical)
│   ├── include/
│   │   ├── events.hpp      # std::variant<MarketEvent, SignalEvent, OrderEvent, FillEvent>
│   │   ├── bar.hpp         # OHLCV struct
│   │   ├── data_handler.hpp
│   │   ├── strategy.hpp    # Strategy base + SMACrossStrategy
│   │   ├── portfolio.hpp
│   │   ├── broker.hpp      # fill at open, 0.1% flat commission
│   │   ├── performance.hpp # Sharpe, CAGR, Max DD, Calmar
│   │   └── export.hpp      # CSV export
│   └── src/
│       └── main.cpp
│
├── strategies/             ← Python engine (reference implementation)
│   ├── events.py           # dataclasses: MarketEvent, SignalEvent, OrderEvent, FillEvent
│   ├── data_handler.py     # yfinance, sequential bar streaming
│   ├── strategy.py         # SMACross, SMACrossWithStopLoss, SMACrossWithTrendFilter
│   ├── portfolio.py        # position sizing, equity tracking
│   ├── broker.py           # simulated execution at open + commission
│   ├── performance.py      # metrics computation
│   └── runner.py           # event loop
│
├── app.py                  ← Streamlit, single entry point
├── scripts/
│   └── download_data.py
├── CMakeLists.txt
├── Justfile
└── pyproject.toml
```

### Dual implementation

| | Python `strategies/` | C++17 `core/` |
|---|---|---|
| Event dispatch | `queue.Queue` + `if/elif` | `std::queue` + `std::visit` |
| Event types | `dataclasses` | `std::variant` |
| Data source | yfinance live | pre-downloaded CSV |
| Output | inline Streamlit | `results/*.csv` |
| Use case | rapid prototyping, strategy development | long-period backtest, performance runs |

The Python implementation is intentionally the reference: readable, easy to extend
with new strategies. The C++ core mirrors the same event loop and is invoked as a
subprocess from the Streamlit app, writing results to CSV for the UI to consume.

---

## Quickstart

### Option 1 — Run on host

```bash
# 1. Download data
just download AAPL,MSFT
# or: python scripts/download_data.py AAPL MSFT --start 2015-01-01 --end 2024-01-01

# 2. Build C++ core
just build
# or: cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j4

# 3. Launch UI
just app
# or: streamlit run app.py

# Full workflow in one command
just all AAPL,MSFT
```

### Option 2 — Docker

```bash
docker compose up --build
```

Open `http://localhost:8501`. The `data/` and `results/` directories are mounted
as local volumes — data and results persist across container restarts.

---

## Limitations and extensions

The current implementation makes several simplifying assumptions that a production
system would address:

- **Execution model:** fills at next open with flat 0.1% commission. No slippage,
  no partial fills, no market impact.
- **Position sizing:** fixed fraction of capital per trade. No Kelly criterion or
  volatility-scaled sizing.
- **Data:** daily OHLCV only. No tick data, no intraday resolution.
- **Strategy universe:** single-asset or independent multi-asset. No cross-asset
  correlation or portfolio-level risk constraints.

Planned extensions: transaction cost modelling with market impact, volatility-scaled
position sizing, walk-forward optimisation to avoid in-sample overfitting.
