#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <queue>
#include <numeric>

#include "events.hpp"
#include "data_handler.hpp"

// ── Strategy base ─────────────────────────────────────────────────────────────

class Strategy {
public:
    virtual void calculate_signals(const Event& event) = 0;
    virtual ~Strategy() = default;
};

// ── SMA Crossover ─────────────────────────────────────────────────────────────
//
// Long  when fast_ma > slow_ma
// Exit  when fast_ma < slow_ma

class SMACrossStrategy : public Strategy {
public:
    struct TradeRecord {
        std::string date;
        std::string symbol;
        std::string signal; // "BUY" | "SELL"
    };

    SMACrossStrategy(const std::vector<std::string>& symbols,
                     std::queue<Event>& events,
                     DataHandler& data,
                     int fast = 20,
                     int slow = 50)
        : symbols_(symbols), events_(events), data_(data),
          fast_(fast), slow_(slow)
    {
        for (const auto& s : symbols_)
            invested_[s] = false;
    }

    void calculate_signals(const Event& event) override {
        if (!std::holds_alternative<MarketEvent>(event)) return;

        for (const auto& sym : symbols_) {
            auto bars = data_.get_latest_bars(sym, slow_ + 1);
            if (static_cast<int>(bars.size()) < slow_) continue;

            double fast_ma = mean_close(bars, fast_);
            double slow_ma = mean_close(bars, slow_);

            if (fast_ma > slow_ma && !invested_[sym]) {
                events_.push(SignalEvent{ sym, Direction::LONG });
                invested_[sym] = true;
                trade_log_.push_back({ data_.current_date(), sym, "BUY" });

            } else if (fast_ma < slow_ma && invested_[sym]) {
                events_.push(SignalEvent{ sym, Direction::EXIT });
                invested_[sym] = false;
                trade_log_.push_back({ data_.current_date(), sym, "SELL" });
            }
        }
    }

    const std::vector<TradeRecord>& trade_log() const { return trade_log_; }

private:
    std::vector<std::string>        symbols_;
    std::queue<Event>&              events_;
    DataHandler&                    data_;
    int                             fast_, slow_;
    std::unordered_map<std::string, bool> invested_;
    std::vector<TradeRecord>        trade_log_;

    // Mean of the last n closing prices in bars
    static double mean_close(const std::vector<Bar>& bars, int n) {
        int start = static_cast<int>(bars.size()) - n;
        double sum = 0.0;
        for (int i = start; i < static_cast<int>(bars.size()); ++i)
            sum += bars[i].close;
        return sum / n;
    }
};
