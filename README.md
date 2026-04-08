# Event-Driven Backtesting Engine

Event-driven backtesting engine implemented in two languages with a unified Streamlit interface.

```
DataHandler  →  MarketEvent
Strategy     →  SignalEvent
Portfolio    →  OrderEvent
Broker       →  FillEvent  →  Portfolio::update()
```

![screenshot](screenshot.png)

## Structure

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
│   ├── events.py
│   ├── data_handler.py
│   ├── strategy.py
│   ├── portfolio.py
│   ├── broker.py
│   ├── performance.py
│   └── runner.py
│
├── app.py                  ← Streamlit, single entry point
├── scripts/
│   └── download_data.py
├── CMakeLists.txt
├── Justfile
└── pyproject.toml
```

## Option 1 : Run on host directly

### 1. Download data
```bash
just download AAPL,MSFT
# or: python scripts/download_data.py AAPL MSFT --start 2015-01-01 --end 2024-01-01
```

### 2. Build C++ core
```bash
just build
# or: cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j4
```

### 3. Launch the UI (you could just run this and skip step 1 and 2)
```bash
just app
# or: streamlit run app.py
```

Select the engine in the sidebar: **Python strategies** (runs inline) or **C++ core** (subprocess + CSV).

### Full workflow in one command
```bash
just all AAPL,MSFT
```

## Option 2 : Use Docker

```bash
docker compose up --build
```

Open `http://localhost:8501`. The `data/` and `results/` directories are mounted as local volumes — data and results persist across container restarts.

## Engines

| | Python `strategies/` | C++ `core/` |
|---|---|---|
| Dispatch | `queue.Queue` + `if/elif` | `std::queue` + `std::visit` |
| Events | dataclasses | `std::variant` |
| Data | yfinance live | pre-downloaded CSV |
| Output | inline Streamlit | `results/*.csv` |
| Use case | rapid prototyping | long-period backtest |

## Metrics

Total Return / CAGR / Sharpe Ratio / Max Drawdown / Annualised Volatility / Calmar Ratio — all compared against a configurable benchmark (default: SPY).
