#pragma once
#include <fstream>
#include <string>
#include <vector>
#include <stdexcept>
#include <iomanip>
#include <sstream>

#include "portfolio.hpp"
#include "strategy.hpp"

// Writes equity curve to CSV for the Python Streamlit visualizer
inline void export_equity_csv(
    const std::vector<Portfolio::EquityPoint>& eq,
    const std::string& path = "results/equity.csv")
{
    std::ofstream f(path);
    if (!f.is_open()) throw std::runtime_error("Cannot write: " + path);
    f << "date,equity\n";
    f << std::fixed << std::setprecision(4);
    for (const auto& p : eq)
        f << p.date << "," << p.value << "\n";
}

// Writes trade log to CSV
inline void export_trades_csv(
    const std::vector<SMACrossStrategy::TradeRecord>& trades,
    const std::string& path = "results/trades.csv")
{
    std::ofstream f(path);
    if (!f.is_open()) throw std::runtime_error("Cannot write: " + path);
    f << "date,symbol,signal\n";
    for (const auto& t : trades)
        f << t.date << "," << t.symbol << "," << t.signal << "\n";
}

// Writes perf summary to CSV (one row, for Python to read)
inline void export_perf_csv(
    const PerfReport& r,
    const std::string& path = "results/performance.csv")
{
    std::ofstream f(path);
    if (!f.is_open()) throw std::runtime_error("Cannot write: " + path);
    f << std::fixed << std::setprecision(6);
    f << "metric,value\n";
    f << "total_return," << r.total_return << "\n";
    f << "cagr,"         << r.cagr         << "\n";
    f << "sharpe,"       << r.sharpe        << "\n";
    f << "max_drawdown," << r.max_drawdown  << "\n";
    f << "volatility,"   << r.volatility    << "\n";
    f << "calmar,"       << r.calmar        << "\n";
}
