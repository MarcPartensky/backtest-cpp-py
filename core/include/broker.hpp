#pragma once
#include <queue>
#include "events.hpp"
#include "data_handler.hpp"

// ── SimulatedBroker ───────────────────────────────────────────────────────────
//
// Fills at the open of the current bar (next bar in practice since
// the signal fires at close). Commission: 0.1% flat.

class SimulatedBroker {
public:
    static constexpr double COMMISSION_RATE = 0.001;

    SimulatedBroker(DataHandler& data, std::queue<Event>& events)
        : data_(data), events_(events) {}

    void execute_order(const OrderEvent& ev) {
        auto bar = data_.get_latest_bar(ev.symbol);
        if (!bar) return;

        double fill_price = bar->open;
        double commission = fill_price * ev.quantity * COMMISSION_RATE;
        events_.push(FillEvent{
            ev.symbol, ev.quantity, ev.direction, fill_price, commission
        });
    }

private:
    DataHandler&       data_;
    std::queue<Event>& events_;
};
