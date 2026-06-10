import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import yfinance as yf

from tradingagents.ticker import Ticker
import db as _db

logger = logging.getLogger(__name__)

def get_performance_data(
    run_ids: List[str],
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None,
    benchmark_symbols: List[str] = ["SPY", "QQQ"]
) -> Dict[str, Any]:
    """
    Calculates performance metrics for multiple runs (wallets) over a timeline.
    Provides comparison vs indices, vs blindly buying and holding, model performance per stock,
    and decision signal correlation stats.
    """
    if not run_ids:
        return {"timeline": [], "runs": {}, "benchmarks": {}, "correlations": {}}

    conn = _db.get_conn()
    
    # 1. Fetch runs details securely
    placeholders = ",".join("?" for _ in run_ids)
    runs_query = f"SELECT id, wallet_name, created_at, initial_cash FROM runs WHERE id IN ({placeholders})"
    runs_rows = conn.execute(runs_query, run_ids).fetchall()
    runs_by_id = {row["id"]: dict(row) for row in runs_rows}

    # If none of the requested runs exist, return empty structure
    if not runs_by_id:
        return {"timeline": [], "runs": {}, "benchmarks": {}, "correlations": {}}

    # 2. Fetch trade ledger entries securely
    ledger_query = f"SELECT * FROM trade_ledger WHERE run_id IN ({placeholders}) ORDER BY timestamp ASC"
    ledger_rows = conn.execute(ledger_query, run_ids).fetchall()
    ledger_entries = [dict(row) for row in ledger_rows]

    # Collect all unique traded tickers
    traded_tickers = {entry["ticker"] for entry in ledger_entries}

    # 3. Determine start and end date of simulation
    min_run_created = None
    for run in runs_by_id.values():
        try:
            created_dt = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            if min_run_created is None or created_dt < min_run_created:
                min_run_created = created_dt
        except Exception:
            pass
            
    if min_run_created is None:
        min_run_created = datetime.now(timezone.utc) - timedelta(days=30)

    min_trade_time = None
    for entry in ledger_entries:
        try:
            trade_dt = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if min_trade_time is None or trade_dt < min_trade_time:
                min_trade_time = trade_dt
        except Exception:
            pass

    overall_start_dt = min_run_created
    if min_trade_time and min_trade_time < overall_start_dt:
        overall_start_dt = min_trade_time

    # Buffer the download start date slightly to ensure we fetch initial prices for fill gaps
    download_start_dt = overall_start_dt - timedelta(days=5)
    download_end_dt = datetime.now(timezone.utc) + timedelta(days=2)

    download_start_str = download_start_dt.strftime("%Y-%m-%d")
    download_end_str = download_end_dt.strftime("%Y-%m-%d")

    # 4. Fetch daily history for tickers and benchmarks
    all_symbols_to_download = list(traded_tickers) + benchmark_symbols
    if "^GSPC" not in all_symbols_to_download:
        all_symbols_to_download.append("^GSPC") # NYSE index for trading days calendar

    prices: Dict[str, Dict[str, float]] = {}
    for symbol in all_symbols_to_download:
        prices[symbol] = {}
        yf_sym = Ticker(symbol).yfinance
        try:
            hist = yf.Ticker(yf_sym).history(start=download_start_str, end=download_end_str)
            for dt, row in hist.iterrows():
                date_str = dt.strftime("%Y-%m-%d")
                prices[symbol][date_str] = float(row["Close"])
        except Exception as e:
            logger.error(f"Failed to fetch history for symbol {symbol} ({yf_sym}): {e}")

    # 5. Build timeline (NYSE trading days where S&P 500 had data)
    raw_timeline = sorted(list(prices.get("^GSPC", {}).keys()))
    if not raw_timeline:
        # Fallback to daily calendar steps if index fetch failed completely
        raw_timeline = []
        curr = overall_start_dt
        today = datetime.now(timezone.utc)
        while curr <= today:
            raw_timeline.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)

    # Filter timeline based on optional start_date and end_date arguments
    timeline = raw_timeline
    if start_date_str:
        timeline = [d for d in timeline if d >= start_date_str]
    if end_date_str:
        timeline = [d for d in timeline if d <= end_date_str]

    if not timeline:
        # If filtered timeline is empty, default to at least containing today
        timeline = [datetime.now(timezone.utc).strftime("%Y-%m-%d")]

    # Helper function to resolve price with robust forward/backward filling
    def get_price_on_date(symbol: str, target_date: str) -> float:
        symbol_prices = prices.get(symbol, {})
        if not symbol_prices:
            # Fallback to trade ledger
            ticker_trades = [e for e in ledger_entries if e["ticker"] == symbol]
            if ticker_trades:
                first_tr = ticker_trades[0]
                return float(first_tr["execution_price"] if first_tr["execution_price"] is not None else first_tr["estimated_price"])
            return 0.0

        if target_date in symbol_prices:
            return symbol_prices[target_date]

        # Find closest date on or before target_date
        sorted_dates = sorted(symbol_prices.keys())
        before_dates = [d for d in sorted_dates if d <= target_date]
        if before_dates:
            return symbol_prices[before_dates[-1]]

        # Fallback to first available price after target_date
        return symbol_prices[sorted_dates[0]]

    # 6. Calculate daily series for each run
    run_results = {}
    for r_id in run_ids:
        run_info = runs_by_id.get(r_id)
        if not run_info:
            continue

        initial_cash = float(run_info.get("initial_cash", 100000.0))
        wallet_name = run_info.get("wallet_name", "Wallet")
        
        # Group ledger entries for this run by date
        run_trades = [e for e in ledger_entries if e["run_id"] == r_id]
        trades_by_date: Dict[str, List[Dict]] = {}
        for entry in run_trades:
            try:
                t_dt = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                d_str = t_dt.strftime("%Y-%m-%d")
                trades_by_date.setdefault(d_str, []).append(entry)
            except Exception:
                pass

        daily_series = []
        current_cash = initial_cash
        current_positions: Dict[str, float] = {}

        for day in raw_timeline:
            # Apply trades on this day
            day_trades = trades_by_date.get(day, [])
            for trade in day_trades:
                price = float(trade["execution_price"] if trade["execution_price"] is not None else trade["estimated_price"])
                qty = float(trade["qty"])
                comm = float(trade.get("commission", 0.0) or 0.0)
                
                current_cash -= (qty * price + comm)
                current_positions[trade["ticker"]] = current_positions.get(trade["ticker"], 0.0) + qty
                
                # Clean up tiny position leftovers from float arithmetic
                if abs(current_positions[trade["ticker"]]) < 1e-5:
                    current_positions.pop(trade["ticker"], None)

            # Calculate portfolio value on this day
            positions_val = 0.0
            positions_breakdown = {}
            for ticker, qty in current_positions.items():
                p = get_price_on_date(ticker, day)
                val = qty * p
                positions_val += val
                positions_breakdown[ticker] = {
                    "qty": qty,
                    "price": p,
                    "value": val
                }

            portfolio_val = current_cash + positions_val
            ret_pct = ((portfolio_val - initial_cash) / initial_cash * 100.0) if initial_cash > 0 else 0.0

            daily_series.append({
                "date": day,
                "portfolio_value": portfolio_val,
                "cash": current_cash,
                "positions_value": positions_val,
                "return_pct": ret_pct,
                "positions": positions_breakdown
            })

        # Calculate Buy and Hold portfolio for this run
        # Buy & hold universe: all tickers ever traded by this run
        run_tickers = sorted(list({t["ticker"] for t in run_trades}))
        bh_series = []
        
        # Find the date of the first trade
        first_trade_day = None
        if run_trades:
            try:
                first_t_dt = datetime.fromisoformat(run_trades[0]["timestamp"].replace("Z", "+00:00"))
                first_trade_day = first_t_dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        if not run_tickers or not first_trade_day:
            # If no trades have happened, buy-and-hold is just cash
            for day in raw_timeline:
                bh_series.append({
                    "date": day,
                    "portfolio_value": initial_cash,
                    "return_pct": 0.0
                })
        else:
            # Allocate initial cash equally among the stock universe on the first trade day
            bh_shares: Dict[str, float] = {}
            alloc_per_stock = initial_cash / len(run_tickers)
            
            for day in raw_timeline:
                if day < first_trade_day:
                    bh_series.append({
                        "date": day,
                        "portfolio_value": initial_cash,
                        "return_pct": 0.0
                    })
                else:
                    # Initialize buy-and-hold shares on the start day
                    if not bh_shares:
                        for ticker in run_tickers:
                            price_start = get_price_on_date(ticker, day)
                            bh_shares[ticker] = (alloc_per_stock / price_start) if price_start > 0 else 0.0

                    val = sum(bh_shares[ticker] * get_price_on_date(ticker, day) for ticker in run_tickers)
                    ret_pct = ((val - initial_cash) / initial_cash * 100.0) if initial_cash > 0 else 0.0
                    bh_series.append({
                        "date": day,
                        "portfolio_value": val,
                        "return_pct": ret_pct
                    })

        # Filter series to timeline range
        daily_series_filtered = [d for d in daily_series if d["date"] in timeline]
        bh_series_filtered = [d for d in bh_series if d["date"] in timeline]

        # Calculate Model Performance Per Stock
        # For each traded ticker, compare model return on it vs buy & hold of that single stock
        stock_performance = {}
        for ticker in run_tickers:
            ticker_trades = [t for t in run_trades if t["ticker"] == ticker]
            if not ticker_trades:
                continue

            try:
                first_tick_dt = datetime.fromisoformat(ticker_trades[0]["timestamp"].replace("Z", "+00:00"))
                first_tick_day = first_tick_dt.strftime("%Y-%m-%d")
            except Exception:
                first_tick_day = timeline[0]

            ticker_timeline = [d for d in raw_timeline if d >= first_tick_day]
            if not ticker_timeline:
                ticker_timeline = [first_tick_day]

            ticker_series = []
            cash_flow = 0.0
            qty = 0.0
            first_price = float(ticker_trades[0]["execution_price"] if ticker_trades[0]["execution_price"] is not None else ticker_trades[0]["estimated_price"])
            first_qty = float(ticker_trades[0]["qty"])
            first_comm = float(ticker_trades[0].get("commission", 0.0) or 0.0)

            # Group ticker trades by day
            ticker_trades_by_day: Dict[str, List[Dict]] = {}
            for t in ticker_trades:
                try:
                    t_dt = datetime.fromisoformat(t["timestamp"].replace("Z", "+00:00"))
                    d_str = t_dt.strftime("%Y-%m-%d")
                    ticker_trades_by_day.setdefault(d_str, []).append(t)
                except Exception:
                    pass

            for day in ticker_timeline:
                day_t_trades = ticker_trades_by_day.get(day, [])
                for t in day_t_trades:
                    p = float(t["execution_price"] if t["execution_price"] is not None else t["estimated_price"])
                    q = float(t["qty"])
                    c = float(t.get("commission", 0.0) or 0.0)
                    cash_flow -= (q * p + c)
                    qty += q

                current_price = get_price_on_date(ticker, day)
                model_value = cash_flow + qty * current_price
                
                # Buy & hold PnL for the same initial purchase quantity
                bh_pnl = first_qty * (current_price - first_price) - first_comm

                ticker_series.append({
                    "date": day,
                    "model_pnl": model_value,
                    "bh_pnl": bh_pnl,
                    "stock_price": current_price
                })

            stock_performance[ticker] = [d for d in ticker_series if d["date"] in timeline]

        run_results[r_id] = {
            "wallet_name": wallet_name,
            "initial_cash": initial_cash,
            "series": daily_series_filtered,
            "buy_and_hold_series": bh_series_filtered,
            "stocks": stock_performance
        }

    # 7. Calculate benchmark metrics normalized to start from first run start date
    # Determine the first trade date across ALL runs to sync benchmarks
    global_first_trade_day = timeline[0]
    for r_id, results in run_results.items():
        # Get start date of series
        if results["series"]:
            first_date = results["series"][0]["date"]
            if first_date < global_first_trade_day:
                global_first_trade_day = first_date

    benchmark_results = {}
    for bench in benchmark_symbols:
        bench_prices = prices.get(bench, {})
        if not bench_prices:
            continue

        start_price = get_price_on_date(bench, global_first_trade_day)
        bench_series = []

        for day in timeline:
            price = get_price_on_date(bench, day)
            # Normalize to 100,000 for standard scale alignment
            val = 100000.0 * (price / start_price) if start_price > 0 else 100000.0
            ret_pct = ((val - 100000.0) / 100000.0 * 100.0)

            bench_series.append({
                "date": day,
                "price": price,
                "value": val,
                "return_pct": ret_pct
            })
        benchmark_results[bench] = bench_series

    # 8. Correlation Analysis of decision signals
    import re
    decisions_query = f"SELECT run_id, ticker, action, rationale, timestamp FROM decision_history WHERE run_id IN ({placeholders}) AND task_type = 'analysis' ORDER BY timestamp ASC"
    decision_rows = conn.execute(decisions_query, run_ids).fetchall()

    # horizon returns storage: {grade: {horizon: [returns]}}
    horizon_returns: Dict[str, Dict[int, List[float]]] = {}
    horizons = [1, 3, 5, 10, 30]
    
    # Store raw points for scatter plot
    scatter_data = []

    for d in decision_rows:
        ticker = d["ticker"]
        action = d["action"]
        rationale = d["rationale"] or ""
        timestamp = d["timestamp"]

        # 8a. Parse decision signal grade (both textual and numeric)
        grade = None
        grade_numeric = None
        
        # Check action for Target Weight
        match = re.search(r"(?:Target Weight|Weight):\s*(-?\d+)", action)
        if match:
            grade = f"Weight: {match.group(1)}"
            grade_numeric = float(match.group(1))
        else:
            # Check rationale for Target Weight
            match = re.search(r"(?:Target Weight|Weight):\s*(-?\d+)", rationale)
            if not match:
                match = re.search(r"\*\*(?:Target Weight|Weight)\*\*:\s*(-?\d+)", rationale)
            
            if match:
                grade = f"Weight: {match.group(1)}"
                grade_numeric = float(match.group(1))
            else:
                # Fallback to basic action words
                action_word = action.strip()
                if "BUY" in action_word.upper() or "LONG" in action_word.upper():
                    grade = "Buy"
                    grade_numeric = 1.0
                elif "SELL" in action_word.upper() or "SHORT" in action_word.upper():
                    grade = "Sell"
                    grade_numeric = -1.0
                elif "HOLD" in action_word.upper():
                    grade = "Hold"
                    grade_numeric = 0.0
                else:
                    grade = action_word[:15]
                    # Try to parse any trailing digits in action as fallback
                    num_match = re.search(r"(-?\d+)", action_word)
                    if num_match:
                        grade_numeric = float(num_match.group(1))
                    else:
                        grade_numeric = 0.0

        if not grade:
            continue

        # 8b. Calculate returns over horizons
        try:
            d_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            d_day = d_dt.strftime("%Y-%m-%d")
        except Exception:
            continue

        p0 = get_price_on_date(ticker, d_day)
        if p0 <= 0:
            continue

        scatter_item = {
            "run_id": d["run_id"],
            "ticker": ticker,
            "date": d_day,
            "grade": grade_numeric,
            "grade_label": grade,
            "returns": {}
        }
        has_any_return = False

        for h in horizons:
            target_dt = d_dt + timedelta(days=h)
            target_day_str = target_dt.strftime("%Y-%m-%d")
            
            # Find closest date in raw NYSE timeline that is >= target_day_str
            future_dates = [dt for dt in raw_timeline if dt >= target_day_str]
            if not future_dates:
                continue
            
            ph_day = future_dates[0]
            ph = get_price_on_date(ticker, ph_day)
            if ph > 0:
                ret = (ph - p0) / p0 * 100.0
                
                horizon_returns.setdefault(grade, {})
                horizon_returns[grade].setdefault(h, []).append(ret)
                
                scatter_item["returns"][f"{h}d"] = ret
                has_any_return = True
        
        if has_any_return:
            scatter_data.append(scatter_item)

    # Summarize correlations stats
    correlation_stats = {}
    for grade, h_data in horizon_returns.items():
        correlation_stats[grade] = {}
        for h, ret_list in h_data.items():
            if not ret_list:
                continue
            avg_ret = sum(ret_list) / len(ret_list)
            pos_ret_count = sum(1 for r in ret_list if r > 0)
            pos_ratio = pos_ret_count / len(ret_list)
            
            correlation_stats[grade][f"{h}d"] = {
                "avg_return": avg_ret,
                "positive_ratio": pos_ratio,
                "count": len(ret_list)
            }

    return {
        "timeline": timeline,
        "runs": run_results,
        "benchmarks": benchmark_results,
        "correlations": correlation_stats,
        "ledger": ledger_entries,
        "scatter_data": scatter_data
    }
