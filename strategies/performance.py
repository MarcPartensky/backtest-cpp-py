from __future__ import annotations
import numpy as np
import pandas as pd


def compute_performance(equity: pd.Series, initial_capital: float) -> dict:
    returns      = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / initial_capital) - 1
    years        = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr         = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1
    sharpe       = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    rolling_max  = equity.cummax()
    drawdown     = (equity - rolling_max) / rolling_max
    max_dd       = drawdown.min()
    volatility   = returns.std() * np.sqrt(252)
    calmar       = cagr / abs(max_dd) if max_dd != 0 else 0
    return {
        "total_return": total_return,
        "cagr":         cagr,
        "sharpe":       sharpe,
        "max_dd":       max_dd,
        "volatility":   volatility,
        "calmar":       calmar,
        "drawdown":     drawdown,
        "returns":      returns,
    }
