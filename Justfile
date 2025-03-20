# Event-Driven Backtesting Engine
# Usage: just <command>

app:
    uv run streamlit run app.py

# Compile C++ core
build:
    cmake -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build -j4

# Download OHLCV data
download sym="AAPL,MSFT" start="2015-01-01" end="2024-01-01":
    uv run python scripts/download_data.py {{sym}} --start {{start}} --end {{end}}

# Run C++ core directly (CLI)
run-cpp sym="AAPL,MSFT" fast="20" slow="50" capital="100000":
    ./build/backtest data {{sym}} {{fast}} {{slow}} {{capital}}


# Full workflow: download → build → run C++ → launch UI
all sym="AAPL,MSFT":
    just download {{sym}}
    just build
    just run-cpp {{sym}}
    just app

# Clean build artifacts
clean:
    rm -rf build/ results/
