#!/usr/bin/env python3
"""
Download OHLCV data from yfinance and save as CSV for the C++ engine.

Usage:
    python scripts/download_data.py AAPL MSFT --start 2015-01-01 --end 2024-01-01
    python scripts/download_data.py AAPL,MSFT --start 2015-01-01 --end 2024-01-01
"""

import argparse
import os
import yfinance as yf
import pandas as pd


def download(symbols: list[str], start: str, end: str, out_dir: str = "data"):
    os.makedirs(out_dir, exist_ok=True)

    # download all at once (one request)
    raw = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)

    for sym in symbols:
        print(f"Downloading {sym}...")

        if len(symbols) == 1:
            df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
        else:
            # multi-symbol: yfinance returns MultiIndex columns (field, symbol)
            df = raw.xs(sym, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]].copy()

        if df.empty:
            print(f"  WARNING: no data for {sym}")
            continue

        df.index.name = "date"
        df.columns    = ["open", "high", "low", "close", "volume"]
        df["volume"]  = df["volume"].astype(int)

        path = os.path.join(out_dir, f"{sym}.csv")
        df.to_csv(path)
        print(f"  Saved {len(df)} bars -> {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--start",  default="2015-01-01")
    parser.add_argument("--end",    default="2024-01-01")
    parser.add_argument("--outdir", default="data")
    args = parser.parse_args()

    # handle both "AAPL MSFT" and "AAPL,MSFT"
    symbols = []
    for tok in args.symbols:
        symbols.extend(s.strip().upper() for s in tok.split(",") if s.strip())

    download(symbols, args.start, args.end, args.outdir)
    print("Done.")
