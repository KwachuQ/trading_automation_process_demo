"""Statistics and chart-data computation for the trading dashboard.

Operates on lists of trade dictionaries (as returned by the database
layer) rather than on raw DataFrames, keeping the dependency graph
minimal.
"""

from __future__ import annotations

from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Duration bucket definitions (seconds)
# ---------------------------------------------------------------------------

DURATION_BUCKETS = [
    (0, 15, "Under 15 sec"),
    (15, 45, "15-45 sec"),
    (45, 60, "45 sec - 1 min"),
    (60, 120, "1 min - 2 min"),
    (120, 300, "2 min - 5 min"),
    (300, 600, "5 min - 10 min"),
    (600, 1800, "10 min - 30 min"),
    (1800, 3600, "30 min - 1 hour"),
    (3600, 7200, "1 hour - 2 hours"),
    (7200, 14400, "2 hours - 4 hours"),
    (14400, float("inf"), "4 hours and up"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_day(dt_str: str) -> str:
    """Extract YYYY-MM-DD from a datetime string."""
    if not dt_str:
        return ""
    return dt_str.split(" ")[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_stats(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics from a list of trade dicts.

    Returns a dictionary matching the shape expected by the frontend's
    ``useTradeStats`` hook and the ``Dashboard`` component.
    """
    total_trades = len(trades)
    if total_trades == 0:
        return _empty_stats()

    total_pnl = 0.0
    total_fees = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    win_count = 0
    loss_count = 0
    best_trade = float("-inf")
    worst_trade = float("inf")
    total_duration = 0.0

    for t in trades:
        pnl = t.get("net_pnl", t.get("pnl", 0.0)) or 0.0
        fees = t.get("commission", 0.0) or 0.0
        dur = t.get("duration_seconds", 0.0) or 0.0

        total_pnl += pnl
        total_fees += fees
        total_duration += dur

        if pnl > 0:
            win_count += 1
            gross_profit += pnl
        else:
            loss_count += 1
            gross_loss += abs(pnl)

        if pnl > best_trade:
            best_trade = pnl
        if pnl < worst_trade:
            worst_trade = pnl

    # Derived metrics
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (
        (gross_profit / gross_loss) if gross_loss > 0
        else (0.0 if gross_profit == 0 else float("inf"))
    )
    avg_win = gross_profit / win_count if win_count > 0 else 0.0
    avg_loss = -(gross_loss / loss_count) if loss_count > 0 else 0.0
    expected_value = total_pnl / total_trades if total_trades > 0 else 0.0
    avg_duration = total_duration / total_trades if total_trades > 0 else 0.0

    # Direction breakdown
    longs = sum(
        1 for t in trades
        if (t.get("direction") or "").lower() in ("long", "buy")
    )
    shorts = sum(
        1 for t in trades
        if (t.get("direction") or "").lower() in ("short", "sell")
    )

    # Daily aggregation
    daily_map: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        day = _extract_day(t.get("entry_datetime", ""))
        if not day:
            continue
        if day not in daily_map:
            daily_map[day] = {"DailyPnL": 0.0, "TradeCount": 0, "WinCount": 0}
        pnl = t.get("net_pnl", t.get("pnl", 0.0)) or 0.0
        daily_map[day]["DailyPnL"] += pnl
        daily_map[day]["TradeCount"] += 1
        if pnl > 0:
            daily_map[day]["WinCount"] += 1

    sorted_days = sorted(daily_map.keys())
    daily_pnls = [daily_map[d]["DailyPnL"] for d in sorted_days]

    best_day = max(daily_pnls) if daily_pnls else 0.0
    worst_day = min(daily_pnls) if daily_pnls else 0.0
    winning_days = sum(1 for p in daily_pnls if p > 0)
    day_win_rate = (
        (winning_days / len(daily_pnls) * 100) if daily_pnls else 0.0
    )
    most_active = (
        max(daily_map[d]["TradeCount"] for d in daily_map) if daily_map
        else 0
    )

    if best_trade == float("-inf"):
        best_trade = 0.0
    if worst_trade == float("inf"):
        worst_trade = 0.0

    return {
        "summary": {
            "total_pnl": round(total_pnl, 2),
            "gross_pnl": round(total_pnl + total_fees, 2),
            "total_fees": round(total_fees, 2),
            "win_rate": round(win_rate, 2),
            "total_trades": total_trades,
            "profit_factor": round(profit_factor, 2)
            if profit_factor != float("inf") else 999.99,
            "expected_value": round(expected_value, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "best_trade_net": round(best_trade, 2),
            "worst_trade_net": round(worst_trade, 2),
            "commission_per_trade": round(
                total_fees / total_trades if total_trades > 0 else 0.0, 2,
            ),
        },
        "duration": {
            "avg_duration": round(avg_duration, 2),
            "avg_win_duration": round(
                _avg_duration_filtered(trades, lambda p: p > 0), 2
            ),
            "avg_loss_duration": round(
                _avg_duration_filtered(trades, lambda p: p <= 0), 2
            ),
        },
        "daily": {
            "day_win_rate": round(day_win_rate, 2),
            "best_day": round(best_day, 2),
            "worst_day": round(worst_day, 2),
            "most_active_day_trades": most_active,
            "best_day_pct_total": round(
                (best_day / total_pnl * 100) if total_pnl > 0 else 0.0, 2
            ),
        },
        "direction": {
            "long_pct": round(
                (longs / total_trades * 100) if total_trades > 0 else 0.0, 2
            ),
            "short_pct": round(
                (shorts / total_trades * 100) if total_trades > 0 else 0.0, 2
            ),
        },
    }


def prepare_charts_data(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Prepare chart-ready data structures from trade dicts.

    Returns daily P/L series, duration distribution, and duration scatter.
    """
    # Daily P/L with cumulative
    daily_map: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        day = _extract_day(t.get("entry_datetime", ""))
        if not day:
            continue
        pnl = t.get("net_pnl", t.get("pnl", 0.0)) or 0.0
        if day not in daily_map:
            daily_map[day] = {"Date": day, "DailyPnL": 0.0, "TradeCount": 0}
        daily_map[day]["DailyPnL"] += pnl
        daily_map[day]["TradeCount"] += 1

    sorted_days = sorted(daily_map.values(), key=lambda d: d["Date"])
    cumulative = 0.0
    for day_data in sorted_days:
        cumulative += day_data["DailyPnL"]
        day_data["DailyPnL"] = round(day_data["DailyPnL"], 2)
        day_data["CumulativePnL"] = round(cumulative, 2)

    # Duration distribution
    distribution = []
    for min_sec, max_sec, label in DURATION_BUCKETS:
        subset = [
            t for t in trades
            if min_sec <= (t.get("duration_seconds", 0) or 0) < max_sec
        ]
        count = len(subset)
        if count > 0:
            wins = sum(
                1 for t in subset
                if (t.get("net_pnl", t.get("pnl", 0)) or 0) > 0
            )
            win_rate = round((wins / count) * 100, 1)
        else:
            win_rate = 0.0
        distribution.append({
            "range": label,
            "count": count,
            "win_rate": win_rate,
        })

    # Duration scatter
    scatter = [
        {
            "Duration": t.get("duration_seconds", 0) or 0,
            "NetPnL": t.get("net_pnl", t.get("pnl", 0)) or 0,
        }
        for t in trades
        if 0 < (t.get("duration_seconds", 0) or 0) < 86400
    ]

    return {
        "daily_pnl": sorted_days,
        "duration_distribution": distribution,
        "duration_scatter": scatter,
    }


def compute_stats_by_tag(
    trades: List[Dict[str, Any]],
    tag_column: str,
) -> Dict[str, Dict[str, Any]]:
    """Group trades by unique values in the specified tag column, then compute stats for each group."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        val = t.get(tag_column)
        if val is None:
            val = ""
        val_str = str(val).strip()
        if not val_str:
            val_str = "unclassified"
        if val_str not in groups:
            groups[val_str] = []
        groups[val_str].append(t)

    result = {}
    for tag_val, group_trades in groups.items():
        result[tag_val] = compute_stats(group_trades)
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _avg_duration_filtered(trades: List[Dict[str, Any]], predicate: Any) -> float:
    """Calculate average duration for trades matching a P/L predicate."""
    total = 0.0
    count = 0
    for t in trades:
        pnl = t.get("net_pnl", t.get("pnl", 0.0)) or 0.0
        if predicate(pnl):
            total += t.get("duration_seconds", 0.0) or 0.0
            count += 1
    return total / count if count > 0 else 0.0


def _empty_stats() -> Dict[str, Any]:
    """Return a zeroed-out stats structure."""
    return {
        "summary": {
            "total_pnl": 0.0,
            "gross_pnl": 0.0,
            "total_fees": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "profit_factor": 0.0,
            "expected_value": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "best_trade_net": 0.0,
            "worst_trade_net": 0.0,
            "commission_per_trade": 0.0,
        },
        "duration": {
            "avg_duration": 0.0,
            "avg_win_duration": 0.0,
            "avg_loss_duration": 0.0,
        },
        "daily": {
            "day_win_rate": 0.0,
            "best_day": 0.0,
            "worst_day": 0.0,
            "most_active_day_trades": 0,
            "best_day_pct_total": 0.0,
        },
        "direction": {"long_pct": 0.0, "short_pct": 0.0},
    }
