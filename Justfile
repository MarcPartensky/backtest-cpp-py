run:
    uv run python backtest.py

help:
    just --list

install:
    uv sync

lint:
    uv run ruff check backtest.py

fmt:
    uv run ruff format backtest.py

clean:
    rm -f backtest_results.png
    find . -name "__pycache__" -exec rm -rf {} +
