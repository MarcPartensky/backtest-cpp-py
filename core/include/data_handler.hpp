#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <queue>
#include <optional>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <algorithm>

#include "bar.hpp"
#include "events.hpp"

// ── DataHandler ───────────────────────────────────────────────────────────────
//
// Reads one CSV per symbol from data/<SYMBOL>.csv (columns: date,open,high,low,close,volume)
// and streams bars one at a time, publishing a MarketEvent per bar.

class DataHandler {
public:
    std::vector<std::string>        symbols;
    bool                            continue_backtest = true;
    std::size_t                     idx = 0;

    DataHandler(const std::vector<std::string>& syms,
                const std::string& data_dir,
                std::queue<Event>& events)
        : symbols(syms), events_(events)
    {
        for (const auto& sym : symbols) {
            auto bars = load_csv(data_dir + "/" + sym + ".csv");
            if (bars.empty())
                throw std::runtime_error("No data for " + sym);
            data_[sym] = std::move(bars);
        }
        // all symbols share the same date index (from first symbol)
        dates_.reserve(data_[symbols[0]].size());
        for (const auto& b : data_[symbols[0]])
            dates_.push_back(b.date);
    }

    // Returns bar at idx-1 (latest streamed bar)
    std::optional<Bar> get_latest_bar(const std::string& sym) const {
        if (idx == 0) return std::nullopt;
        return data_.at(sym)[idx - 1];
    }

    // Returns last n bars up to current idx
    std::vector<Bar> get_latest_bars(const std::string& sym, std::size_t n) const {
        std::size_t start = (idx > n) ? idx - n : 0;
        const auto& v = data_.at(sym);
        return { v.begin() + start, v.begin() + idx };
    }

    const std::string& current_date() const { return dates_[idx - 1]; }
    const std::vector<std::string>& dates() const { return dates_; }

    void update_bars() {
        if (idx < dates_.size()) {
            ++idx;
            events_.push(MarketEvent{});
        } else {
            continue_backtest = false;
        }
    }

private:
    std::unordered_map<std::string, std::vector<Bar>> data_;
    std::vector<std::string>                          dates_;
    std::queue<Event>&                                events_;

    static std::vector<Bar> load_csv(const std::string& path) {
        std::ifstream f(path);
        if (!f.is_open())
            throw std::runtime_error("Cannot open: " + path);

        std::vector<Bar> bars;
        std::string line;
        std::getline(f, line); // skip header

        while (std::getline(f, line)) {
            if (line.empty()) continue;
            std::istringstream ss(line);
            std::string tok;
            Bar b;
            std::getline(ss, b.date,  ',');
            std::getline(ss, tok,     ','); b.open   = std::stod(tok);
            std::getline(ss, tok,     ','); b.high   = std::stod(tok);
            std::getline(ss, tok,     ','); b.low    = std::stod(tok);
            std::getline(ss, tok,     ','); b.close  = std::stod(tok);
            std::getline(ss, tok,     ','); b.volume = std::stol(tok);
            bars.push_back(b);
        }
        return bars;
    }
};
