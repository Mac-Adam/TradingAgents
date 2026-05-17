import math
import os
import json
import logging
import re
import yfinance as yf
from ib_insync import IB, Stock, MarketOrder

from webapp.backend import db

logger = logging.getLogger(__name__)

class IBKRExecutor:
    def __init__(self, host=None, port=None, client_id=1):
        self.host = host or os.getenv("IB_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("IB_PORT", "7497"))
        self.client_id = client_id
        self.ib = IB()

    def _get_current_price(self, ticker):
        try:
            stock = yf.Ticker(ticker)
            return float(stock.fast_info['lastPrice'])
        except Exception as e:
            logger.error(f"Error fetching current price for {ticker} via yfinance: {e}")
            return None

    def calculate_net_worth(self, ai_id):
        portfolio = db.get_ai_portfolio(ai_id)
        net_worth = portfolio["cash"]
        for ticker, qty in portfolio["positions"].items():
            if qty != 0:
                price = self._get_current_price(ticker)
                if price is not None:
                    net_worth += qty * price
        return net_worth

    def batch_execute(self, trades_list):
        """
        Expects a list of dicts: [{'ai_id': 'bot1', 'ticker': 'AAPL', 'decision': '...'}, ...]
        Calculates relative weights across all requested trades and executes them.
        Returns a list of tickers that were successfully sent to IBKR.
        """
        if not trades_list:
            return []

        ai_id = trades_list[0]['ai_id']
        portfolio = db.get_ai_portfolio(ai_id)
        net_worth = self.calculate_net_worth(ai_id)
        
        # Parse all weights from trades_list
        target_weights = {}
        for trade in trades_list:
            match = re.search(r"\*\*Target Weight\*\*:\s*(-?\d+)", trade['decision'])
            if match:
                target_weights[trade['ticker']] = float(match.group(1))
            else:
                logger.warning(f"[{ai_id}] Could not parse Target Weight for {trade['ticker']}.")
                target_weights[trade['ticker']] = 0.0

        sum_abs_weights = sum(abs(w) for w in target_weights.values())
        success_tickers = []
        
        # Connect to IBKR
        try:
            if not self.ib.isConnected():
                self.ib.connect(self.host, self.port, clientId=self.client_id)

            all_tickers = set(portfolio["positions"].keys()).union(set(target_weights.keys()))
            
            for ticker in all_tickers:
                weight = target_weights.get(ticker, 0.0)
                
                if sum_abs_weights > 0:
                    relative_weight = weight / sum_abs_weights
                else:
                    relative_weight = 0.0
                    
                target_value = relative_weight * net_worth
                current_price = self._get_current_price(ticker)
                
                if current_price is None or current_price == 0:
                    logger.warning(f"[{ai_id}] Could not get price for {ticker}. Skipping.")
                    continue
                    
                current_qty = portfolio["positions"].get(ticker, 0.0)
                current_value = current_qty * current_price
                
                value_to_trade = target_value - current_value
                shares_to_trade = value_to_trade / current_price

                abs_shares_raw = abs(shares_to_trade)
                abs_shares = math.floor(abs_shares_raw)

                if abs_shares < 1:
                    continue

                action = 'BUY' if shares_to_trade > 0 else 'SELL'
                
                contract = Stock(ticker, 'SMART', 'USD')
                self.ib.qualifyContracts(contract)

                order = MarketOrder(action, abs_shares, tif='OPG')
                order.orderRef = ai_id

                trade = self.ib.placeOrder(contract, order)
                
                max_wait = 2.0
                waited = 0.0
                
                while trade.orderStatus.status in ('ApiPending', 'PendingSubmit') and waited < max_wait:
                    self.ib.sleep(0.1) 
                    waited += 0.1

                current_status = trade.orderStatus.status

                # Now evaluate the resolved status
                if current_status in ('Submitted', 'PreSubmitted', 'Filled'):
                    actual_shares_signed = abs_shares if action == 'BUY' else -abs_shares
                    actual_value_traded = actual_shares_signed * current_price

                    portfolio["positions"][ticker] = current_qty + actual_shares_signed
                    portfolio["cash"] -= actual_value_traded
                    success_tickers.append(ticker)
                    logger.info(f"[{ai_id}] Successfully placed {action} {abs_shares} {ticker}")
                else:
                    logger.warning(f"[{ai_id}] Order for {ticker} failed with status: {trade.orderStatus.status}")
            
            # Only persist virtual portfolio if at least one order was accepted by IBKR
            if success_tickers:
                db.save_ai_portfolio(ai_id, portfolio["cash"], portfolio["positions"])
                logger.info(f"[{ai_id}] Virtual portfolio updated for: {success_tickers}")
            else:
                logger.warning(f"[{ai_id}] No orders accepted by IBKR — virtual portfolio NOT changed.")
            return success_tickers

        except Exception as e:
            logger.error(f"[{ai_id}] Error executing IBKR batch trades: {e}")
            raise e
        finally:
            if self.ib.isConnected():
                self.ib.disconnect()
        return []  # fallback if exception before return
