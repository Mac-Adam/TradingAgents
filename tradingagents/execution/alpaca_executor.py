import os
import re
import logging
import math
import yfinance as yf
from tradingagents.dataflows.stockstats_utils import StockstatsUtils
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

logger = logging.getLogger(__name__)

class AlpacaExecutor:
    def __init__(self):
        api_key = os.getenv("ALPACA_API_KEY")
        api_secret = os.getenv("ALPACA_API_SECRET")
        paper = os.getenv("ALPACA_PAPER", "True").lower() == "true"
        
        if not api_key or not api_secret:
            logger.warning("Alpaca API keys not found in environment. Trades will not be executed.")
            self.client = None
        else:
            self.client = TradingClient(api_key, api_secret, paper=paper)

    def get_portfolio_state(self) -> str:
        """Returns a string description of the current portfolio state."""
        if not self.client:
            return "Portfolio state unavailable (Alpaca keys missing)."
            
        try:
            account = self.client.get_account()
            positions = self.client.get_all_positions()
            
            buying_power = float(account.buying_power)
            equity = float(account.equity)
            
            state_lines = [
                f"Total Equity: ${equity:.2f}",
                f"Available Buying Power: ${buying_power:.2f}",
                "Current Positions:"
            ]
            
            if not positions:
                state_lines.append("- No open positions.")
            else:
                for p in positions:
                    state_lines.append(f"- {p.symbol}: {p.qty} shares (Market Value: ${float(p.market_value):.2f}, Unrealized P/L: ${float(p.unrealized_pl):.2f})")
                    
            return "\n".join(state_lines)
        except Exception as e:
            logger.error(f"Error fetching Alpaca portfolio state: {e}")
            return "Error fetching portfolio state."

    def execute_trade(self, ticker: str, final_trade_decision: str):
        """Parse the Portfolio Manager's decision and execute on Alpaca."""
        if not self.client:
            logger.warning("Cannot execute trade: Alpaca client not initialized.")
            return

        # Parse Target Weight from final_trade_decision markdown
        # e.g. "**Target Weight**: 5%" or "-5%"
        match = re.search(r"\*\*Target Weight\*\*:\s*(-?\d+)%", final_trade_decision)
        if not match:
            logger.warning("Could not parse Target Weight from final_trade_decision. No trade executed.")
            return
            
        target_weight_percentage = int(match.group(1))
        target_weight = target_weight_percentage / 100.0
        logger.info(f"Parsed Target Weight for {ticker}: {target_weight_percentage}%")
        
        try:
            account = self.client.get_account()
            total_equity = float(account.equity)
            target_value = total_equity * target_weight
            
            try:
                position = self.client.get_open_position(ticker)
                current_value = float(position.market_value)
                current_qty = float(position.qty)
                if "short" in str(position.side).lower():
                    current_value = -current_value
                    current_qty = -current_qty
            except Exception as e:
                # Alpaca API throws an exception if position is not found
                current_value = 0.0
                current_qty = 0.0
                
            # Fetch current stock price to calculate whole shares
            try:
                sanitized_ticker = StockstatsUtils.sanitize_yf_ticker(ticker)
                stock = yf.Ticker(sanitized_ticker)
                current_price = stock.fast_info['lastPrice']
            except Exception as e:
                logger.error(f"Error fetching current price for {ticker} via yfinance: {e}")
                return
                
            # Calculate total shares to trade and the direction
            target_qty = round(target_value / current_price)
            total_shares_to_trade = abs(target_qty - current_qty)
            side = OrderSide.BUY if target_qty > current_qty else OrderSide.SELL
            
            if total_shares_to_trade == 0:
                logger.info(f"Target weight already met for {ticker} (Target Qty: {target_qty}). No trade executed.")
                return

            # Determine if we need to chunk the orders
            # Restriction: Alpaca sometimes caps orders at the current physical quantity during off-hours.
            if current_qty != 0:
                chunk_size = abs(current_qty)
                shares_remaining = total_shares_to_trade
                
                logger.info(f"Executing trade for {ticker} in chunks of {chunk_size} (Total: {total_shares_to_trade} shares {side.name})")
                
                while shares_remaining > 0:
                    this_qty = min(shares_remaining, chunk_size)
                    order_data = MarketOrderRequest(
                        symbol=ticker,
                        qty=this_qty,
                        side=side,
                        time_in_force=TimeInForce.DAY
                    )
                    order = self.client.submit_order(order_data=order_data)
                    logger.info(f"Submitted chunk: {side.name} {this_qty} shares. Order ID: {order.id}")
    
                    shares_remaining -= this_qty
            else:
                # No existing position, submit full order in one go
                order_data = MarketOrderRequest(
                    symbol=ticker,
                    qty=total_shares_to_trade,
                    side=side,
                    time_in_force=TimeInForce.DAY
                )
                order = self.client.submit_order(order_data=order_data)
                logger.info(f"Executed {side.name} order for {ticker}: {total_shares_to_trade} shares to reach {target_weight_percentage}% weight. Order ID: {order.id}")
                
        except Exception as e:
            logger.error(f"Error executing Alpaca trade for {ticker}: {e}")
