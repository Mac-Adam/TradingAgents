from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_news(
    ticker: Annotated[str, "ticker symbol of the company"],
    lookback_days: Annotated[int, "number of days of news data to look back (default 7)"] = 7,
) -> str:
    """
    Retrieve news data for a given ticker symbol over a relative time window.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        lookback_days (int): Number of days of news data to look back (default 7)
    Returns:
        str: A formatted string containing news data
    """
    from tradingagents.dataflows.utils import ACTIVE_TRADE_DATE
    from datetime import datetime
    curr_date = ACTIVE_TRADE_DATE.get()
    if not curr_date:
        curr_date = datetime.now().strftime("%Y-%m-%d")
    return route_to_vendor("get_news", ticker, curr_date, lookback_days)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back (default 7)
        limit (int): Maximum number of articles to return (default 5)
    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker)
