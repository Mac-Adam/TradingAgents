from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    lookback_days: Annotated[int, "number of days of stock data to look back (default 90)"] = 90,
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol over a relative time window.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        lookback_days (int): Number of days of stock data to look back (default 90)
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol.
    """
    from tradingagents.dataflows.utils import ACTIVE_TRADE_DATE
    from datetime import datetime
    curr_date = ACTIVE_TRADE_DATE.get()
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")
    return route_to_vendor("get_stock_data", symbol, curr_date, lookback_days)
