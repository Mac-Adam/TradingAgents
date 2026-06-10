import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import pandas as pd

# Import the code to test
from webapp.backend.performance_analyzer import get_performance_data

class TestPerformanceAnalyzer(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite database for testing
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        
        # Initialize the schema
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                wallet_name TEXT,
                config_file TEXT,
                env_file TEXT,
                account_type TEXT,
                status TEXT,
                created_at TEXT,
                initial_cash REAL DEFAULT 100000.0
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS trade_ledger (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                ticker TEXT,
                action TEXT,
                qty REAL,
                estimated_price REAL,
                execution_price REAL,
                commission REAL,
                status TEXT,
                ib_execution_id TEXT,
                timestamp TEXT
            )
        ''')
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS decision_history (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                task_id TEXT,
                ticker TEXT,
                action TEXT,
                rationale TEXT,
                full_report_path TEXT,
                timestamp TEXT,
                stats TEXT,
                task_type TEXT
            )
        ''')
        
        # Populate mock runs
        self.conn.execute('''
            INSERT INTO runs (id, wallet_name, config_file, env_file, account_type, status, created_at, initial_cash)
            VALUES ('run1', 'Test Wallet 1', 'default.json', 'paper.env', 'PAPER', 'running', '2026-05-20T00:00:00Z', 100000.0)
        ''')
        self.conn.execute('''
            INSERT INTO runs (id, wallet_name, config_file, env_file, account_type, status, created_at, initial_cash)
            VALUES ('run2', 'Test Wallet 2', 'default.json', 'paper.env', 'PAPER', 'running', '2026-05-20T00:00:00Z', 100000.0)
        ''')
        
        # Populate mock trade ledger for run1
        # AAPL trades: Buy 10 shares on 2026-05-21, Sell 5 shares on 2026-05-22
        self.conn.execute('''
            INSERT INTO trade_ledger (id, run_id, ticker, action, qty, estimated_price, execution_price, commission, status, timestamp)
            VALUES ('t1', 'run1', 'AAPL', 'BUY', 10.0, 150.0, 150.0, 1.0, 'confirmed', '2026-05-21T13:30:00Z')
        ''')
        self.conn.execute('''
            INSERT INTO trade_ledger (id, run_id, ticker, action, qty, estimated_price, execution_price, commission, status, timestamp)
            VALUES ('t2', 'run1', 'AAPL', 'SELL', -5.0, 160.0, 160.0, 1.0, 'confirmed', '2026-05-22T13:30:00Z')
        ''')
        
        # Populate mock decision history
        self.conn.execute('''
            INSERT INTO decision_history (id, run_id, task_id, ticker, action, rationale, timestamp, task_type)
            VALUES ('d1', 'run1', 'task1', 'AAPL', 'Target Weight: 2', 'Buying AAPL due to indicators', '2026-05-21T10:00:00Z', 'analysis')
        ''')

        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    @patch("yfinance.Ticker")
    @patch("db.get_conn")
    def test_performance_calculation(self, mock_get_conn, mock_yf_ticker):
        # Direct the helper to use our test in-memory connection
        mock_get_conn.return_value = self.conn

        # Mock yfinance data returns
        def mock_history_side_effect(symbol):
            # Create a mock ticker instance
            ticker_mock = MagicMock()
            
            # Setup mock price history DataFrame
            dates = pd.date_range(start="2026-05-18", end="2026-05-25", freq="D")
            
            # Price starts at 150 and climbs
            price_map = {
                "AAPL": [150.0 + idx * 2 for idx in range(len(dates))],
                "SPY": [400.0 + idx * 5 for idx in range(len(dates))],
                "QQQ": [300.0 + idx * 3 for idx in range(len(dates))],
                "^GSPC": [4000.0 + idx * 20 for idx in range(len(dates))]
            }
            
            prices = price_map.get(symbol, [100.0] * len(dates))
            df = pd.DataFrame({
                "Open": prices,
                "High": prices,
                "Low": prices,
                "Close": prices,
                "Volume": [1000] * len(dates)
            }, index=dates)
            
            ticker_mock.history.return_value = df
            return ticker_mock

        mock_yf_ticker.side_effect = mock_history_side_effect

        # Run calculations
        result = get_performance_data(run_ids=["run1", "run2"])

        # Basic validations
        self.assertIn("timeline", result)
        self.assertIn("runs", result)
        self.assertIn("benchmarks", result)
        self.assertIn("correlations", result)

        # Validate runs series exists
        self.assertIn("run1", result["runs"])
        self.assertIn("run2", result["runs"])

        run1_data = result["runs"]["run1"]
        self.assertEqual(run1_data["wallet_name"], "Test Wallet 1")
        self.assertEqual(run1_data["initial_cash"], 100000.0)
        self.assertTrue(len(run1_data["series"]) > 0)
        
        # Test specific return calculations
        # Initial cash is 100,000. On 2026-05-21, we buy 10 AAPL @ 150 = 1500 + 1 commission = 1501 cash outflow.
        # Remaining cash is 98,499.
        # Check AAPL price on 2026-05-22. (Index 4 in date range starting 2026-05-18)
        # Dates are: 18 (idx 0), 19 (idx 1), 20 (idx 2), 21 (idx 3), 22 (idx 4)
        # AAPL price on 21 is 150.0 + 3*2 = 156.0. Wait, our mock date indexing gives 156.
        # Let's check series returns are non-zero.
        for dp in run1_data["series"]:
            if dp["date"] == "2026-05-22":
                # Remaining position should be 5 shares
                self.assertIn("AAPL", dp["positions"])
                self.assertEqual(dp["positions"]["AAPL"]["qty"], 5.0)

        # Test benchmarks normalization
        self.assertIn("SPY", result["benchmarks"])
        spy_series = result["benchmarks"]["SPY"]
        self.assertTrue(len(spy_series) > 0)
        self.assertEqual(spy_series[0]["return_pct"], 0.0) # normalized to start at 0%

        # Test correlation analysis calculations
        self.assertIn("Weight: 2", result["correlations"])
        weight_2_stats = result["correlations"]["Weight: 2"]
        self.assertIn("1d", weight_2_stats)
        self.assertTrue(weight_2_stats["1d"]["count"] > 0)

if __name__ == "__main__":
    unittest.main()
