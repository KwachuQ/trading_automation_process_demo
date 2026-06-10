import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from backend.db import get_connection, init_db

# --- Mock Data Templates for SC Files ---

VWAP_MULTI_HEADER = (
    "Date,Time,Open,High,Low,Close,Volume,"
    "VWAP,"
    "Upper Band 1,Lower Band 1,"
    "Upper Band 2,Lower Band 2,"
    "Upper Band 3,Lower Band 3,"
    "Upper Band 4,Lower Band 4"
)
VWAP_MULTI_YEARLY_HEADER = VWAP_MULTI_HEADER + ",Difference,Avg"

DAILY_ADR_HEADER = "Date,Time,Open,High,Low,Close,Volume,Avg,ADR"

ONE_MIN_HEADER = "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,Bid Volume,Ask Volume"

ETH_750V_HEADER = (
    "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,"
    "Bid Volume,Ask Volume,ECIVwap,"
    "Top Band 2 of Vwap Standard Deviation,Bottom Band 2 of Vwap Standard Deviation,"
    "Top Band 3 of Vwap Standard Deviation,Bottom Band 3 of Vwap Standard Deviation,"
    "Top Band 4 of Vwap Standard Deviation,Bottom Band 4 of Vwap Standard Deviation,"
    "Vwap extension,Top band 1 extension,Bottom band 1 extension,"
    "Top band 2 extension,Bottom band 2 extension,"
    "Top band 3 extension,Bottom band 3 extension,"
    "Top band 4 extension,Bottom band 4 extension,"
    "Text Display,Avg,Line1,"
    "Open,High,Low,Close,"
    "HA Open,HA Close,"
    "Open,High,Low,Last"
)

RTH_500V_HEADER = (
    "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,"
    "Bid Volume,Ask Volume,ECIVwap,"
    "Top Band 2 of Vwap Standard Deviation,Bottom Band 2 of Vwap Standard Deviation,"
    "Top Band 3 of Vwap Standard Deviation,Bottom Band 3 of Vwap Standard Deviation,"
    "Top Band 4 of Vwap Standard Deviation,Bottom Band 4 of Vwap Standard Deviation,"
    "Vwap extension,Top band 1 extension,Bottom band 1 extension,"
    "Top band 2 extension,Bottom band 2 extension,"
    "Top band 3 extension,Bottom band 3 extension,"
    "Top band 4 extension,Bottom band 4 extension,"
    "Text Display,Avg,"
    "Open,High,Low,Close,"
    "HA Open,HA Close,"
    "Open,High,Low,Last,"
    "Point of Control,Value Area High Value,Value Area Low Value,"
    "Volume Weighted Average Price"
)

RVOL_30MIN_HEADER = (
    "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,"
    "HLC Avg,HL Avg,Bid Volume,Ask Volume,"
    "wVWAP,PW-Hi,PW-Lo,WK-Op,PW-VAH,PW-VAL,WK-Mid,"
    "Relative Volume,Cumulative Volume Ratio,"
    "100%,Single Prints Up (current session),Single Prints Down (current session)"
)

def create_mock_sc_files(data_dir: Path):
    today = datetime.now()
    d_today = today.strftime("%Y-%m-%d")
    d_yest = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    d_2days = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    
    # VWAP MULTI
    vwap_multi_content = f"""{VWAP_MULTI_HEADER}
{d_yest},09:30:00,19800.00,19850.00,19780.00,19820.00,12345,19810.00,19830.00,19790.00,19850.00,19770.00,19870.00,19750.00,19890.00,19730.00
{d_today},09:31:00,19820.00,19860.00,19800.00,19840.00,9800,19815.00,19835.00,19795.00,19855.00,19775.00,19875.00,19755.00,19895.00,19735.00
{d_today},09:32:00,19840.00,19870.00,19820.00,19855.00,8500,19820.00,19840.00,19800.00,19860.00,19780.00,19880.00,19760.00,19900.00,19740.00"""

    vwap_multi_yearly = f"""{VWAP_MULTI_YEARLY_HEADER}
{d_yest},09:30:00,19800.00,19850.00,19780.00,19820.00,12345,19810.00,19830.00,19790.00,19850.00,19770.00,19870.00,19750.00,19890.00,19730.00,10.00,19805.00
{d_today},09:31:00,19820.00,19860.00,19800.00,19840.00,9800,19815.00,19835.00,19795.00,19855.00,19775.00,19875.00,19755.00,19895.00,19735.00,15.00,19810.00
{d_today},09:32:00,19840.00,19870.00,19820.00,19855.00,8500,19820.00,19840.00,19800.00,19860.00,19780.00,19880.00,19760.00,19900.00,19740.00,20.00,19815.00"""

    daily_adr = f"""{DAILY_ADR_HEADER}
{d_2days},00:00:00,19600.00,19720.00,19550.00,19680.00,46000,43000.00,140.00
{d_yest},00:00:00,19700.00,19810.00,19650.00,19750.00,48000,44000.00,145.00
{d_today},00:00:00,19800.00,19900.00,19750.00,19820.00,50000,45000.00,150.00"""

    nq_1min = f"""{ONE_MIN_HEADER}
{d_today},09:30:00,19800.00,19810.00,19795.00,19805.00,500,42,19802.50,19803.33,19802.50,250,250
{d_today},09:31:00,19805.00,19815.00,19800.00,19810.00,480,38,19807.50,19808.33,19807.50,240,240
{d_today},09:32:00,19810.00,19820.00,19805.00,19815.00,520,45,19812.50,19813.33,19812.50,260,260"""

    qqq_1min = f"""{ONE_MIN_HEADER}
{d_today},09:30:00,470.00,471.00,469.80,470.50,1000,80,470.25,470.43,470.40,500,500
{d_today},09:31:00,470.50,471.50,470.20,471.00,980,75,470.75,470.90,470.85,490,490
{d_today},09:32:00,471.00,472.00,470.70,471.50,1020,85,471.25,471.40,471.35,510,510"""

    eth_750v = f"""{ETH_750V_HEADER}
{d_yest},18:00:00,19800.00,19820.00,19790.00,19810.00,300,120,19802.50,19806.67,19805.00,150,150,19805.00,19840.00,19770.00,19860.00,19750.00,19880.00,19730.00,0.50,0.20,0.15,0.30,0.25,0.40,0.35,0.45,0.38,0,43200.00,0,100.00,120.00,80.00,200.00,19808.00,19812.00,19795.00,19820.00,19785.00,19810.00
{d_yest},18:01:00,19810.00,19830.00,19800.00,19815.00,280,110,19811.25,19815.00,19815.00,140,140,19806.00,19841.00,19771.00,19861.00,19751.00,19881.00,19731.00,0.51,0.21,0.16,0.31,0.26,0.41,0.36,0.46,0.39,0,43300.00,0,110.00,130.00,85.00,210.00,19809.00,19813.00,19796.00,19821.00,19786.00,19811.00
{d_today},18:02:00,19815.00,19835.00,19805.00,19820.00,310,130,19818.75,19820.00,19820.00,155,155,19807.00,19842.00,19772.00,19862.00,19752.00,19882.00,19732.00,0.52,0.22,0.17,0.32,0.27,0.42,0.37,0.47,0.40,0,43400.00,0,120.00,140.00,90.00,220.00,19810.00,19814.00,19797.00,19822.00,19787.00,19812.00"""

    rth_500v = f"""{RTH_500V_HEADER}
{d_yest},16:00:00,19800.00,19820.00,19790.00,19810.00,400,150,19802.50,19806.67,19805.00,200,200,19805.00,19840.00,19770.00,19860.00,19750.00,19880.00,19730.00,0.50,0.20,0.15,0.30,0.25,0.40,0.35,0.45,0.38,0,43200.00,-50.00,-40.00,-160.00,-150.00,19808.00,19812.00,19795.00,19820.00,19785.00,19810.00,19800.00,19840.00,19760.00,19805.00
{d_today},16:01:00,19810.00,19825.00,19800.00,19815.00,380,140,19812.50,19813.33,19812.50,190,190,19806.00,19841.00,19771.00,19861.00,19751.00,19881.00,19731.00,0.51,0.21,0.16,0.31,0.26,0.41,0.36,0.46,0.39,0,43100.00,-45.00,-35.00,-155.00,-145.00,19809.00,19813.00,19796.00,19821.00,19786.00,19811.00,19801.00,19841.00,19761.00,19806.00
{d_today},16:02:00,19815.00,19830.00,19805.00,19820.00,420,160,19817.50,19818.33,19817.50,210,210,19807.00,19842.00,19772.00,19862.00,19752.00,19882.00,19732.00,0.52,0.22,0.17,0.32,0.27,0.42,0.37,0.47,0.40,0,43000.00,-40.00,-30.00,-150.00,-140.00,19810.00,19814.00,19797.00,19822.00,19787.00,19812.00,19802.00,19842.00,19762.00,19807.00"""

    rvol_30min = f"""{RVOL_30MIN_HEADER}
{d_today},09:30:00,19800.00,19850.00,19780.00,19820.00,5000,120,19812.50,19817.00,19815.00,2500,2500,19810.00,19900.00,19750.00,19795.00,19880.00,19740.00,19822.00,1.05,1.10,100.00,0.00,0.00
{d_today},10:00:00,19820.00,19860.00,19800.00,19840.00,4800,115,19830.00,19833.33,19830.00,2400,2400,19812.00,19900.00,19750.00,19795.00,19880.00,19740.00,19822.00,1.10,1.15,100.00,0.00,0.00
{d_today},10:30:00,19840.00,19870.00,19820.00,19855.00,5200,130,19846.25,19848.33,19845.00,2600,2600,19815.00,19900.00,19750.00,19795.00,19880.00,19740.00,19822.00,1.15,1.20,100.00,0.00,0.00"""

    files = {
        "nq_1min.txt": nq_1min,
        "qqq_1min.txt": qqq_1min,
        "rth_500v.txt": rth_500v,
        "eth_750v.txt": eth_750v,
        "quarterly_vwap.txt": vwap_multi_content,
        "monthly_vwap.txt": vwap_multi_content,
        "weekly_vwap.txt": vwap_multi_content,
        "daily_adr.txt": daily_adr,
        "yearly_vwap.txt": vwap_multi_yearly,
        "rvol_30min.txt": rvol_30min
    }

    for name, content in files.items():
        (data_dir / name).write_text(content, encoding="utf-8")
        
    print(f"Created 10 mock Sierra Chart .txt files in {data_dir}")

def seed_demo_data():
    project_root = Path(__file__).resolve().parent.parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Create Mock SC Text Files
    create_mock_sc_files(data_dir)
    
    # 2. Database Init
    db_path_str = os.getenv("DATABASE_URL", str(data_dir / "trading_automation.db"))
    db_path = Path(db_path_str)
    
    print(f"Seeding demo database at {db_path}...")
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
    conn = get_connection(str(db_path))
    init_db(conn)
    
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    cursor = conn.cursor()
    
    # 3. Seed Pre-Market Scenarios
    cursor.execute("SELECT COUNT(*) FROM scenarios")
    if cursor.fetchone()[0] == 0:
        print("Inserting mock scenarios...")
        cursor.execute(
            """INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
               VALUES (?, 1, 'ML', 'Price above VWAP, potential short squeeze', 'Previous Day High (PDH)', 'Breaks below IB low')""",
            (today,)
        )
        cursor.execute(
            """INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
               VALUES (?, 2, 'MRS', 'Overextended in high volatility regime', 'VWAP', 'Closes above 5min resistance')""",
            (today,)
        )
    
    # 4. Seed Mock Trades
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
