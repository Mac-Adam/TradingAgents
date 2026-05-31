import unittest

import pytest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.ticker import Ticker


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_ticker_class_normalization_and_formats(self):
        t1 = Ticker("BRK.B")
        t2 = Ticker("BRK B")
        t3 = Ticker("brk-b")
        t4 = Ticker("AAPL")
        
        self.assertEqual(t1.canonical, "BRK.B")
        self.assertEqual(t2.canonical, "BRK.B")
        self.assertEqual(t3.canonical, "BRK.B")
        self.assertEqual(t4.canonical, "AAPL")
        
        self.assertEqual(t1.yfinance, "BRK-B")
        self.assertEqual(t1.ibkr, "BRK B")
        
        self.assertEqual(str(t1), "BRK.B")
        
        self.assertEqual(t1, t2)
        self.assertEqual(t1, "BRK B")
        self.assertEqual(t1, "BRK-B")
        self.assertEqual(t4, "aapl")
        self.assertNotEqual(t1, t4)


if __name__ == "__main__":
    unittest.main()

