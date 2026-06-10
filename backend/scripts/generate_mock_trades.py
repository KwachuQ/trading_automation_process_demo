import os
import sqlite3
import random
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

# Headers
TRADES_LIST_HEADER = (
    "Symbol\tTrade Type\tEntry DateTime\tExit DateTime\tEntry Price\tExit Price\t"
    "Trade Quantity\tMax Open Quantity\tMax Closed Quantity\tProfit/Loss (C)\t"
    "Cumulative Profit/Loss (C)\tFlatToFlat Profit/Loss (C)\t"
    "FlatToFlat Max Open Profit (C)\tFlatToFlat Max Open Loss (C)\t"
    "Max Open Profit (C)\tMax Open Loss (C)\tEntry Efficiency\tExit Efficiency\t"
    "Total Efficiency\tCommission (C)\tHigh Price While Open\tLow Price While Open\t"
    "Note\tOpen Position Quantity\tClose Position Quantity\tDuration\tAccount\t"
    "Highest Cumulative P/L (C)\tLowest Cumulative P/L (C)\tMaximum Runup (C)\t"
    "Maximum Drawdown (C)"
)

def _compute_import_hash(trade_dict):
    raw = (
        f"{trade_dict['symbol']}|{trade_dict['entry_datetime']}|"
        f"{trade_dict['exit_datetime']}|{trade_dict['pnl']}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def generate_mock_trades():
    project_root = Path(__file__).resolve().parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    trades_file = data_dir / "TradesList.txt"
    db_path_str = os.getenv("DATABASE_URL", str(data_dir / "trading_automation.db"))
    db_path = Path(db_path_str)
    
    symbols = ["MNQH26", "NQH26", "ESH26", "MESZ26", "CLG26"]
    base_symbols = {"MNQH26": "MNQ", "NQH26": "NQ", "ESH26": "ES", "MESZ26": "MES", "CLG26": "CL"}
    point_values = {"MNQ": 2.0, "NQ": 20.0, "ES": 50.0, "MES": 5.0, "CL": 1000.0}
    tick_sizes = {"MNQ": 0.25, "NQ": 0.25, "ES": 0.25, "MES": 0.25, "CL": 0.01}
    tick_values = {"MNQ": 0.50, "NQ": 5.00, "ES": 12.50, "MES": 1.25, "CL": 10.00}
    commissions = {"MNQ": 0.52, "NQ": 1.18, "ES": 1.18, "MES": 0.52, "CL": 1.18}
    
    setup_tags = ["ML", "MS", "MRL", "MRS", "Breakout", "Pullback"]
    key_indicators = [
        "gamma_regime:positive,vol_regime:expansion,vwap_slope:up",
        "gamma_regime:negative,vol_regime:contraction,vwap_slope:down",
        "gamma_regime:mixed,cd_vs_ma:above MA,entry_quality:A",
        "delta_slope:up,entry_quality:B",
    ]
    scoring_criteria = [
        "Price > VWAP,Vol expansion",
        "Price < VWAP,Vol contraction",
        "Break of HOD,Positive delta",
        "Test of VWAP band 2,Negative delta",
    ]
    
    lines = [TRADES_LIST_HEADER]
    db_trades = []
    
    now = datetime.now()
    
    # Pre-calculate 12 winners and 8 losers to guarantee a Profit Factor around 1.4
    # Expected Gross Profit: 12 * 280 = ~3360
    # Expected Gross Loss: 8 * 300 = ~2400
    # PF = 3360 / 2400 = 1.4
    outcomes = [1] * 12 + [-1] * 8
    random.shuffle(outcomes)
    
    for i in range(20):
        # Generate random trade data
        sym = random.choice(symbols)
        base = base_symbols[sym]
        direction = random.choice(["Long", "Short"])
        qty = random.randint(1, 5)
        
        # Random time within the last 10 days, during NY session roughly
        days_ago = random.randint(0, 10)
        entry_time = now.replace(hour=random.randint(9, 15), minute=random.randint(0, 59), second=0) - timedelta(days=days_ago)
        duration_minutes = random.randint(1, 45)
        exit_time = entry_time + timedelta(minutes=duration_minutes)
        
        entry_price = round(random.uniform(15000, 16000), 2)
        
        is_winner = outcomes[i] == 1
        if is_winner:
            target_pnl = random.uniform(100, 460)  # avg ~280
        else:
            target_pnl = random.uniform(-500, -100) # avg ~300
            
        ticks = target_pnl / (tick_values[base] * qty)
        ticks = round(ticks)
        
        pnl = round(ticks * tick_values[base] * qty, 2)
        
        if direction == "Short":
            price_diff = -ticks * tick_sizes[base]
        else:
            price_diff = ticks * tick_sizes[base]
            
        exit_price = round(entry_price + price_diff, 2)
        
        comm = round(commissions[base] * 2 * qty, 2)
        net_pnl = round(pnl - comm, 2)
        
        max_open_profit = round(max(pnl + random.uniform(0, 50), 0), 2)
        max_open_loss = round(min(pnl - random.uniform(0, 50), 0), 2)
        
        entry_dt_str = entry_time.strftime("%Y-%m-%d  %H:%M:%S.000")
        exit_dt_str = exit_time.strftime("%Y-%m-%d  %H:%M:%S.000")
        
        # TradesList.txt lines (2 lines per trade: Entry then Exit)
        # Entry line
        lines.append(
            f"{sym}\t{direction}\t{entry_dt_str} BP\t{entry_dt_str}\t{entry_price:.2f}\t{entry_price:.2f}\t"
            f"{qty}\t{qty}\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t"
            f"0.00%\t0.00%\t0.00%\t{comm/2:.2f}\t{entry_price:.2f}\t{entry_price:.2f}\t"
            f"Parent order\t{qty}\t0\t00:00:00\t12345\t0.00\t0.00\t0.00\t0.00"
        )
        
        # Exit line (with ' F' marker)
        duration_str = f"00:{duration_minutes:02d}:00"
        lines.append(
            f"{sym}\t{'Short' if direction == 'Long' else 'Long'}\t{exit_dt_str}\t{exit_dt_str} EP\t"
            f"{exit_price:.2f}\t{exit_price:.2f}\t{qty}\t{qty}\t{qty}\t{pnl:.2f}\t{pnl:.2f}\t{pnl:.2f} F\t"
            f"{max_open_profit:.2f}\t{max_open_loss:.2f}\t{max_open_profit:.2f}\t{max_open_loss:.2f}\t"
            f"50.00%\t50.00%\t50.00%\t{comm:.2f}\t0.00\t0.00\tDescriptive Exit\t0\t{qty}\t"
            f"{duration_str}\t12345\t0.00\t0.00\t0.00\t0.00"
        )
        
        # DB trade dict
        trade_dict = {
            "symbol": sym,
            "base_symbol": base,
            "direction": direction,
            "entry_datetime": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_datetime": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": qty,
            "pnl": pnl,
            "commission": comm,
            "net_pnl": net_pnl,
            "max_open_profit": max_open_profit,
            "max_open_loss": max_open_loss,
            "duration_seconds": duration_minutes * 60.0,
            "note": "Descriptive Exit",
            "fill_count": 2,
            "point_value": point_values[base],
            "tick_size": tick_sizes[base],
            "tick_value": tick_values[base],
            "session_date": entry_time.strftime("%Y-%m-%d")
        }
        trade_dict["import_hash"] = _compute_import_hash(trade_dict)
        
        # Random tags
        trade_dict["setup_tag"] = random.choice(setup_tags)
        trade_dict["key_indicators_tags"] = random.choice(key_indicators)
        trade_dict["scoring_criteria_tags"] = random.choice(scoring_criteria)
        trade_dict["setup_rating"] = round(random.uniform(1.0, 5.0), 1)
        trade_dict["additional_tag"] = random.choice(["", "A+", "Tilt", "Revenge", "Good read"])
        trade_dict["comments"] = "Generated mock trade for demo."
        
        db_trades.append(trade_dict)
        
    # Write to TradesList.txt
    with open(trades_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        
    print(f"Generated 20 trades in {trades_file}")
    
    # Initialize DB connection to trading_automation.db
    if not db_path.exists():
        print(f"Database {db_path} does not exist. Creating and initializing schema...")
        from backend.db import init_db, get_connection
        conn = get_connection(str(db_path))
        init_db(conn)
    else:
        conn = sqlite3.connect(str(db_path))
        
    # Seed db with these trades
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tagged_trades")
    
    for t in db_trades:
        cursor.execute(
            '''
            INSERT INTO tagged_trades (
                session_date, symbol, base_symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, quantity, pnl, commission, net_pnl,
                max_open_profit, max_open_loss, duration_seconds, note,
                fill_count, point_value, tick_size, tick_value, import_hash,
                tags_json, tags_auto, setup_tag, key_indicators_tags,
                scoring_criteria_tags, additional_tag, setup_rating, comments, exported_to_dashboard
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                '{}', 1, ?, ?, ?, ?, ?, ?, 1
            )
            ''',
            (
                t["session_date"], t["symbol"], t["base_symbol"], t["direction"], 
                t["entry_datetime"], t["exit_datetime"], t["entry_price"], t["exit_price"], 
                t["quantity"], t["pnl"], t["commission"], t["net_pnl"], 
                t["max_open_profit"], t["max_open_loss"], t["duration_seconds"], t["note"],
                t["fill_count"], t["point_value"], t["tick_size"], t["tick_value"], t["import_hash"],
                t["setup_tag"], t["key_indicators_tags"], t["scoring_criteria_tags"],
                t["additional_tag"], t["setup_rating"], t["comments"]
            )
        )
        
    conn.commit()
    conn.close()
    print("Database seeded with tagged trades successfully.")

if __name__ == "__main__":
    generate_mock_trades()
