#pragma once
#include <string>
#include <variant>

// ── Direction ────────────────────────────────────────────────────────────────

enum class Direction { LONG, EXIT };

inline std::string to_string(Direction d) {
    return d == Direction::LONG ? "BUY" : "SELL";
}

// ── Event types ──────────────────────────────────────────────────────────────

struct MarketEvent {};

struct SignalEvent {
    std::string symbol;
    Direction   direction;
    double      strength = 1.0;
};

struct OrderEvent {
    std::string symbol;
    int         quantity;
    Direction   direction;
};

struct FillEvent {
    std::string symbol;
    int         quantity;
    Direction   direction;
    double      fill_price;
    double      commission;
};

// ── Variant ──────────────────────────────────────────────────────────────────

using Event = std::variant<MarketEvent, SignalEvent, OrderEvent, FillEvent>;
