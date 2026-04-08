#pragma once
#include <string>
#include <vector>
#include <unordered_map>
#include <queue>
#include <stdexcept>

#include "events.hpp"
#include "data_handler.hpp"

// ── Portfolio ─────────────────────────────────────────────────────────────────
//
// Fixed-fractional position sizing.
// Tracks cash, open positions, and daily equity.

class Portfolio {
public:
    struct EquityPoint {
        std::string date;
        double      value;
    };

    Portfolio(DataHandler& data,
              std::queue<Event>& events,
              const std::vector<std::string>& symbols,
              double initial_capital   = 100'000.0,
              double position_fraction = 0.95)
        : data_(data), events_(events), symbols_(symbols),
          capital_(initial_capital), fraction_(position_fraction),
          initial_capital_(initial_capital)
    {
        for (const auto& s : symbols_)
            positions_[s] = 0;
    }

    void on_signal(const SignalEvent& ev) {
        auto bar = data_.get_latest_bar(ev.symbol);
        if (!bar) return;
        double price = bar->close;

        if (ev.direction == Direction::LONG) {
            int qty = static_cast<int>((capital_ * fraction_) / price);
            if (qty > 0)
                events_.push(OrderEvent{ ev.symbol, qty, Direction::LONG });

        } else { // EXIT
            int qty = positions_[ev.symbol];
            if (qty > 0)
                events_.push(OrderEvent{ ev.symbol, qty, Direction::EXIT });
        }
    }

    void on_fill(const FillEvent& ev) {
        int sign = (ev.direction == Direction::LONG) ? 1 : -1;
        positions_[ev.symbol] += sign * ev.quantity;
        double cost = sign * ev.quantity * ev.fill_price + ev.commission;
        capital_ -= cost;
    }

    void update_equity() {
        if (data_.idx == 0) return;
        double mkt = 0.0;
        for (const auto& sym : symbols_) {
            auto bar = data_.get_latest_bar(sym);
            if (bar) mkt += positions_[sym] * bar->close;
        }
        equity_.push_back({ data_.current_date(), capital_ + mkt });
    }

    const std::vector<EquityPoint>& equity() const { return equity_; }
    double initial_capital() const { return initial_capital_; }

private:
    DataHandler&                          data_;
    std::queue<Event>&                    events_;
    std::vector<std::string>              symbols_;
    double                                capital_;
    double                                fraction_;
    double                                initial_capital_;
    std::unordered_map<std::string, int>  positions_;
    std::vector<EquityPoint>              equity_;
};
