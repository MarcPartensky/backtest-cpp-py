#pragma once
#include <vector>
#include <cmath>
#include <algorithm>
#include <string>
#include <sstream>
#include <iomanip>

#include "portfolio.hpp"

struct PerfReport {
    double total_return;
    double cagr;
    double sharpe;
    double max_drawdown;
    double volatility;
    double calmar;
};

inline PerfReport compute_performance(
    const std::vector<Portfolio::EquityPoint>& eq,
    double initial_capital)
{
    int n = static_cast<int>(eq.size());
    if (n < 2) return {};

    // daily returns
    std::vector<double> rets;
    rets.reserve(n - 1);
    for (int i = 1; i < n; ++i)
        rets.push_back((eq[i].value - eq[i-1].value) / eq[i-1].value);

    double mean_r = 0.0;
    for (double r : rets) mean_r += r;
    mean_r /= rets.size();

    double var = 0.0;
    for (double r : rets) var += (r - mean_r) * (r - mean_r);
    var /= rets.size();
    double std_r = std::sqrt(var);

    double total_return = (eq.back().value / initial_capital) - 1.0;

    // approximate years from bar count (252 trading days/year)
    double years = static_cast<double>(n) / 252.0;
    double cagr  = std::pow(eq.back().value / initial_capital, 1.0 / years) - 1.0;

    double sharpe = (std_r > 0) ? (mean_r / std_r) * std::sqrt(252.0) : 0.0;

    // max drawdown
    double peak = eq[0].value;
    double max_dd = 0.0;
    for (const auto& p : eq) {
        peak = std::max(peak, p.value);
        double dd = (p.value - peak) / peak;
        max_dd = std::min(max_dd, dd);
    }

    double vol    = std_r * std::sqrt(252.0);
    double calmar = (max_dd != 0.0) ? cagr / std::abs(max_dd) : 0.0;

    return { total_return, cagr, sharpe, max_dd, vol, calmar };
}

inline void print_report(const PerfReport& r) {
    auto pct = [](double v) {
        std::ostringstream s;
        s << std::fixed << std::setprecision(2) << v * 100.0 << "%";
        return s.str();
    };
    auto f2 = [](double v) {
        std::ostringstream s;
        s << std::fixed << std::setprecision(2) << v;
        return s.str();
    };

    std::printf("── Performance ──────────────────────────\n");
    std::printf("  %-22s %s\n", "Total return",   pct(r.total_return).c_str());
    std::printf("  %-22s %s\n", "CAGR",           pct(r.cagr).c_str());
    std::printf("  %-22s %s\n", "Sharpe ratio",   f2(r.sharpe).c_str());
    std::printf("  %-22s %s\n", "Max drawdown",   pct(r.max_drawdown).c_str());
    std::printf("  %-22s %s\n", "Volatility ann.", pct(r.volatility).c_str());
    std::printf("  %-22s %s\n", "Calmar ratio",   f2(r.calmar).c_str());
    std::printf("─────────────────────────────────────────\n");
}
