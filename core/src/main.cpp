/**
 * Event-Driven Backtesting Engine — C++17
 * =========================================
 * Architecture:
 *   DataHandler  →  MarketEvent
 *   Strategy     →  SignalEvent
 *   Portfolio    →  OrderEvent
 *   Broker       →  FillEvent  →  Portfolio::on_fill()
 *
 * Usage:
 *   ./backtest [data_dir] [symbol,...] [fast] [slow] [capital]
 *
 * Example:
 *   ./backtest data AAPL,MSFT 20 50 100000
 */

#include <iostream>
#include <string>
#include <vector>
#include <queue>
#include <sstream>
#include <filesystem>
#include <cstdlib>
#include <yaml-cpp/yaml.h>

#include "events.hpp"
#include "data_handler.hpp"
#include "strategy.hpp"
#include "portfolio.hpp"
#include "broker.hpp"
#include "performance.hpp"
#include "export.hpp"

// ── Helpers ───────────────────────────────────────────────────────────────────

static std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> out;
    std::istringstream ss(s);
    std::string tok;
    while (std::getline(ss, tok, delim))
        if (!tok.empty()) out.push_back(tok);
    return out;
}

static std::string config_path() {
    const char* xdg = std::getenv("XDG_CONFIG_HOME");
    std::string base = xdg ? xdg : (std::string(std::getenv("HOME")) + "/.config");
    return base + "/backtest/config.yml";
}

// ── Main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    // defaults
    std::string data_dir    = "data";
    std::string results_dir = "results";
    std::string sym_str     = "AAPL";
    int         fast        = 20;
    int         slow        = 50;
    double      capital     = 100'000.0;

    // ── Load config ───────────────────────────────────────────────────────────
    try {
        YAML::Node cfg = YAML::LoadFile(config_path());
        if (cfg["data_dir"])    data_dir    = cfg["data_dir"].as<std::string>();
        if (cfg["results_dir"]) results_dir = cfg["results_dir"].as<std::string>();
    } catch (...) {}

    // CLI overrides
    if (argc > 1) data_dir = argv[1];
    if (argc > 2) sym_str  = argv[2];
    if (argc > 3) fast     = std::stoi(argv[3]);
    if (argc > 4) slow     = std::stoi(argv[4]);
    if (argc > 5) capital  = std::stod(argv[5]);

    auto symbols = split(sym_str, ',');

    std::printf("Event-Driven Backtesting Engine\n");
    std::printf("Symbols : %s\n", sym_str.c_str());
    std::printf("SMA     : %d / %d\n", fast, slow);
    std::printf("Capital : $%.0f\n\n", capital);

    // ── Build components ──────────────────────────────────────────────────────
    std::queue<Event> events;

    DataHandler      data     (symbols, data_dir, events);
    SMACrossStrategy strategy (symbols, events, data, fast, slow);
    Portfolio        portfolio(data, events, symbols, capital);
    SimulatedBroker  broker   (data, events);

    // ── Event loop ────────────────────────────────────────────────────────────
    while (data.continue_backtest) {
        data.update_bars();

        while (!events.empty()) {
            Event ev = events.front();
            events.pop();

            std::visit([&](auto&& e) {
                using T = std::decay_t<decltype(e)>;

                if constexpr (std::is_same_v<T, MarketEvent>) {
                    strategy.calculate_signals(ev);
                    portfolio.update_equity();

                } else if constexpr (std::is_same_v<T, SignalEvent>) {
                    portfolio.on_signal(e);

                } else if constexpr (std::is_same_v<T, OrderEvent>) {
                    broker.execute_order(e);

                } else if constexpr (std::is_same_v<T, FillEvent>) {
                    portfolio.on_fill(e);
                }
            }, ev);
        }
    }

    // ── Results ───────────────────────────────────────────────────────────────
    const auto& eq     = portfolio.equity();
    auto        report = compute_performance(eq, capital);
    print_report(report);

    std::filesystem::create_directories(results_dir);
    export_equity_csv(eq,                   results_dir + "/equity.csv");
    export_trades_csv(strategy.trade_log(), results_dir + "/trades.csv");
    export_perf_csv  (report,               results_dir + "/performance.csv");

    std::printf("\nResults exported to %s/\n", results_dir.c_str());

    return 0;
}
