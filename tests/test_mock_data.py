from __future__ import annotations

import os
from pathlib import Path
import pytest

from backend.config import load_config
from backend.ingestion.sc_parser import parse_sc_file, SchemaType, detect_schema
from backend.review.trade_importer import parse_sierra_trades

def test_mock_data_files_exist_and_parse(tmp_path):
    """
    Test that the project root contains a config.toml that points to the correct data folder
    and that all mock data files defined in it exist and parse successfully.
    """
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config" / "config.toml"
    
    # Check if config.toml exists
    assert config_path.exists(), "config.toml should exist"
    
    # Temporarily change cwd to project root so relative paths work
    original_cwd = os.getcwd()
    os.chdir(project_root)
    try:
        cfg = load_config(str(config_path))
        sc = cfg.sierra_chart
        
        # Test SC export files
        data_dir = Path(sc.data_dir)
        files_to_check = [
            sc.nq_1min,
            sc.rth_500v,
            sc.eth_750v,
            sc.quarterly_vwap,
            sc.monthly_vwap,
            sc.weekly_vwap,
            sc.daily_adr,
            sc.yearly_vwap,
            sc.qqq_1min,
            sc.rvol_30min,
        ]
        
        for file_name in files_to_check:
            file_path = data_dir / file_name
            assert file_path.exists(), f"Mock file missing: {file_path}"
            # Let the parser auto-detect the schema or parse it
            schema = detect_schema(str(file_path))
            df = parse_sc_file(str(file_path), schema)
            assert not df.empty, f"Parsed empty DataFrame from {file_name}"
            
        # Test TradesList mock data
        trades_dir = Path(sc.saved_trade_activity_dir)
        trades_file = trades_dir / sc.trades_list_file
        assert trades_file.exists(), f"Mock trade list missing: {trades_file}"
        
        trades = parse_sierra_trades(str(trades_file))
        assert len(trades) > 0, "No trades parsed from the mock TradesList file"
        
    finally:
        os.chdir(original_cwd)
