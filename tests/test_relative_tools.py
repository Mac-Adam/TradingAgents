import unittest
from unittest.mock import patch, MagicMock
import pytest
from datetime import datetime
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows.y_finance import get_YFin_data_online
from tradingagents.dataflows.yfinance_news import get_news_yfinance
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.news_data_tools import get_news
from tradingagents.dataflows.utils import ACTIVE_TRADE_DATE


@pytest.mark.unit
class RelativeToolsTests(unittest.TestCase):
    @patch("yfinance.Ticker")
    def test_get_yfin_data_online_calculates_correct_dates(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker
        
        # Mock empty DataFrame that has necessary properties so to_csv() and clean works
        import pandas as pd
        mock_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        mock_df.index = pd.to_datetime([])
        mock_ticker.history.return_value = mock_df
        
        # Call the refactored function
        get_YFin_data_online("AAPL", "2026-05-29", 90)
        
        # Check dates passed to history
        curr_dt = datetime.strptime("2026-05-29", "%Y-%m-%d")
        expected_start = (curr_dt - relativedelta(days=90)).strftime("%Y-%m-%d")
        expected_end = "2026-05-29"
        
        mock_ticker.history.assert_called_once_with(start=expected_start, end=expected_end)
        
    @patch("yfinance.Ticker")
    def test_get_news_yfinance_filters_by_correct_dates(self, mock_ticker_class):
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker
        mock_ticker.get_news.return_value = [
            {
                "content": {
                    "title": "Test Title",
                    "summary": "Test Summary",
                    "pubDate": "2026-05-28T12:00:00Z",
                    "provider": {"displayName": "Test Provider"}
                }
            }
        ]
        
        # Call news function
        res = get_news_yfinance("AAPL", "2026-05-29", 7)
        
        # Check that the news article is retrieved and not filtered out
        self.assertIn("Test Title", res)

    @patch("tradingagents.agents.utils.core_stock_tools.route_to_vendor")
    def test_get_stock_data_resolves_context_date(self, mock_route):
        # Set context date
        token = ACTIVE_TRADE_DATE.set("2026-05-29")
        try:
            get_stock_data("AAPL", 90)
            mock_route.assert_called_once_with("get_stock_data", "AAPL", "2026-05-29", 90)
        finally:
            ACTIVE_TRADE_DATE.reset(token)

    @patch("tradingagents.agents.utils.news_data_tools.route_to_vendor")
    def test_get_news_resolves_context_date(self, mock_route):
        # Set context date
        token = ACTIVE_TRADE_DATE.set("2026-05-29")
        try:
            get_news("AAPL", 7)
            mock_route.assert_called_once_with("get_news", "AAPL", "2026-05-29", 7)
        finally:
            ACTIVE_TRADE_DATE.reset(token)


if __name__ == "__main__":
    unittest.main()
