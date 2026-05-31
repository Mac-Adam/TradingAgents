from datetime import datetime
from .alpha_vantage_common import _make_api_request, _filter_csv_by_date_range

def get_stock(
    symbol: str,
    curr_date: str,
    lookback_days: int = 90,
) -> str:
    """
    Returns raw daily OHLCV values, adjusted close values, and historical split/dividend events
    filtered to the specified date range.

    Args:
        symbol: The name of the equity. For example: symbol=IBM
        curr_date: Current date in yyyy-mm-dd format
        lookback_days: Number of days of stock data to look back (default 90)

    Returns:
        CSV string containing the daily adjusted time series data filtered to the date range.
    """
    # Parse dates to determine the range
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    from dateutil.relativedelta import relativedelta
    start_dt = curr_dt - relativedelta(days=lookback_days)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = curr_date
    today = datetime.now()

    # Choose outputsize based on whether the requested range is within the latest 100 days
    # Compact returns latest 100 data points, so check if start_date is recent enough
    days_from_today_to_start = (today - start_dt).days
    outputsize = "compact" if days_from_today_to_start < 100 else "full"

    params = {
        "symbol": symbol,
        "outputsize": outputsize,
        "datatype": "csv",
    }

    response = _make_api_request("TIME_SERIES_DAILY_ADJUSTED", params)

    return _filter_csv_by_date_range(response, start_date, end_date)