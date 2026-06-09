import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from backend.db import get_connection, init_db

def seed_demo_data():
    project_root = Path(__file__).resolve().parent.parent.parent
    db_path_str = os.getenv("DATABASE_URL", str(project_root / "data" / "trading_automation.db"))
    db_path = Path(db_path_str)
    
    print(f"Seeding demo database at {db_path}...")
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
    conn = get_connection(str(db_path))
    
    # This creates tables and seeds the feature store (regimes and scoring criteria)
    init_db(conn)
    
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    cursor = conn.cursor()
    
    # 1. Seed Pre-Market Scenarios
    cursor.execute("SELECT COUNT(*) FROM scenarios")
    if cursor.fetchone()[0] == 0:
        print("Inserting mock scenarios...")
        cursor.execute(
            """INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
               VALUES (?, 1, 'Long Breakout', 'Price above VWAP, potential short squeeze', 'Previous Day High (PDH)', 'Breaks below IB low')""",
            (today,)
        )
        cursor.execute(
            """INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
               VALUES (?, 2, 'Mean Reversion Short', 'Overextended in high volatility regime', 'VWAP', 'Closes above 5min resistance')""",
            (today,)
        )
    
    # 2. Seed Mock Trades
    cursor.execute("SELECT COUNT(*) FROM tagged_trades")
    if cursor.fetchone()[0] == 0:
        print("Inserting mock trades...")
        trades = [
            (today, "NQM26", "Long", f"{today} 09:35:00", f"{today} 09:40:00", 18500.25, 18510.50, 2, 410.0, 405.0, 1, '{"setup": "Breakout", "regime": "Trending up"}', 1, "Demo trade 1"),
            (today, "NQM26", "Short", f"{today} 10:15:00", f"{today} 10:25:00", 18550.00, 18535.50, 1, 290.0, 287.50, 1, '{"setup": "Reversal", "regime": "Trending down"}', 1, "Demo trade 2"),
            (yesterday, "QQQ", "Long", f"{yesterday} 14:00:00", f"{yesterday} 14:30:00", 450.50, 448.00, 10, -250.0, -255.0, 1, '{"setup": "Pullback", "regime": "Neutral"}', 1, "Demo trade 3 (loss)")
        ]
        
        cursor.executemany(
            """INSERT INTO tagged_trades 
               (session_date, symbol, direction, entry_datetime, exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl, tags_auto, tags_json, exported_to_dashboard, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            trades
        )
        
    conn.commit()
    conn.close()
    print("Demo data seeded successfully!")

if __name__ == "__main__":
    seed_demo_data()
