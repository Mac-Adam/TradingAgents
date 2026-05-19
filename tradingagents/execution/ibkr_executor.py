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
            yf_ticker = ticker.replace('.', '-')
            stock = yf.Ticker(yf_ticker)
            return float(stock.fast_info['lastPrice'])
        except Exception as e:
            logger.error(f"Error fetching current price for {ticker} via yfinance: {e}")
            return None

    def _normalize_positions(self, positions):
        normalized = {}
        for ticker, val in positions.items():
            if ticker.startswith("_"):
                continue
            if isinstance(val, dict):
                normalized[ticker] = {
                    "qty": float(val.get("qty", 0.0)),
                    "avg_entry_price": float(val.get("avg_entry_price", 0.0))
                }
        return normalized

    def _rebuild_portfolio_from_ledger(self, ai_id):
        """
        Rebuilds the virtual portfolio positions and cash from the ledger of trades.
        Optimized to use a checkpoint state to avoid O(N) replay computation from the beginning.
        """
        # Fetch all ledger entries sorted by timestamp ascending
        ledger_entries = db.get_ledger_entries(ai_id)
        ledger_entries.sort(key=lambda x: x.get("timestamp", ""))
        
        # Find index of first estimated trade
        first_est_idx = -1
        for idx, entry in enumerate(ledger_entries):
            if entry["status"] == "estimated":
                first_est_idx = idx
                break
                
        # Determine the target checkpoint entry
        new_checkpoint_ledger_id = None
        if first_est_idx == -1:
            # All trades are confirmed, checkpoint can be up to the last trade
            if ledger_entries:
                new_checkpoint_ledger_id = ledger_entries[-1]["id"]
        elif first_est_idx > 0:
            # Checkpoint can be up to the trade before the first estimated trade
            new_checkpoint_ledger_id = ledger_entries[first_est_idx - 1]["id"]
            
        # Load the checkpoint state
        checkpoint = db.get_ai_portfolio(f"{ai_id}_checkpoint")
        checkpoint_cash = float(checkpoint.get("cash", 100000.0))
        checkpoint_positions = self._normalize_positions(checkpoint.get("positions", {}))
        last_ledger_id = checkpoint.get("positions", {}).get("_last_ledger_id")
        
        # Remove metadata key from positions copy if present
        checkpoint_positions.pop("_last_ledger_id", None)
        
        # Align replay start index
        replay_start_idx = 0
        if last_ledger_id:
            for idx, entry in enumerate(ledger_entries):
                if entry["id"] == last_ledger_id:
                    replay_start_idx = idx + 1
                    break
                    
        cash = checkpoint_cash
        positions = {k: v.copy() for k, v in checkpoint_positions.items()}
        
        logger.info(f"[{ai_id}] Replay starting from index {replay_start_idx}/{len(ledger_entries)} (using checkpoint: {last_ledger_id})")
        
        for i in range(replay_start_idx, len(ledger_entries)):
            entry = ledger_entries[i]
            qty_change = float(entry["qty"])
            status = entry["status"]
            
            if status == "confirmed":
                price = float(entry["execution_price"])
                commission = float(entry.get("commission", 0.0) or 0.0)
            else:
                price = float(entry["estimated_price"])
                commission = 0.0
                
            # Apply to cash
            cash -= (qty_change * price + commission)
            
            # Apply to positions
            ticker = entry["ticker"]
            pos_info = positions.get(ticker, {"qty": 0.0, "avg_entry_price": 0.0})
            current_qty = pos_info["qty"]
            current_avg = pos_info["avg_entry_price"]
            
            new_qty = current_qty + qty_change
            if new_qty == 0:
                new_avg = 0.0
            elif current_qty == 0:
                new_avg = price
            elif (current_qty > 0 and new_qty < 0) or (current_qty < 0 and new_qty > 0):
                # Reversal
                new_avg = price
            elif (current_qty >= 0 and qty_change > 0) or (current_qty <= 0 and qty_change < 0):
                # Increasing position
                new_avg = (current_qty * current_avg + qty_change * price) / new_qty
            else:
                # Decreasing position
                new_avg = current_avg
                
            if new_qty == 0:
                positions.pop(ticker, None)
            else:
                positions[ticker] = {
                    "qty": new_qty,
                    "avg_entry_price": new_avg
                }
                
            # If we reached the target checkpoint entry, save it
            if new_checkpoint_ledger_id and entry["id"] == new_checkpoint_ledger_id:
                checkpoint_positions_to_save = {k: v.copy() for k, v in positions.items()}
                checkpoint_positions_to_save["_last_ledger_id"] = new_checkpoint_ledger_id
                db.save_ai_portfolio(f"{ai_id}_checkpoint", cash, checkpoint_positions_to_save)
                logger.info(f"[{ai_id}] Saved new portfolio checkpoint at ledger entry {new_checkpoint_ledger_id}")
                
        # Save the current final state
        db.save_ai_portfolio(ai_id, cash, positions)
        logger.info(f"[{ai_id}] Rebuilt portfolio from ledger: cash={cash}, positions={positions}")

    def calculate_net_worth(self, ai_id):
        portfolio = db.get_ai_portfolio(ai_id)
        net_worth = portfolio["cash"]
        normalized_positions = self._normalize_positions(portfolio["positions"])
        for ticker, info in normalized_positions.items():
            qty = info["qty"]
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
        portfolio["positions"] = self._normalize_positions(portfolio["positions"])
        
        # Calculate target weights
        target_weights = {}
        for trade in trades_list:
            decision = trade.get('decision', '')
            match = re.search(r"Target Weight:\s*(-?\d+)", decision)
            if not match:
                match = re.search(r"\*\*Target Weight\*\*:\s*(-?\d+)", decision)
            if match:
                target_weights[trade['ticker']] = float(match.group(1)) / 100.0

        net_worth = self.calculate_net_worth(ai_id)
        sum_abs_weights = sum(abs(w) for w in target_weights.values())

        success_tickers = []
        import uuid
        from datetime import datetime, timezone

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
                    
                pos_info = portfolio["positions"].get(ticker, {"qty": 0.0, "avg_entry_price": 0.0})
                current_qty = pos_info["qty"]
                current_value = current_qty * current_price
                
                value_to_trade = target_value - current_value
                shares_to_trade = value_to_trade / current_price

                abs_shares_raw = abs(shares_to_trade)
                abs_shares = math.floor(abs_shares_raw)

                if abs_shares < 1:
                    logger.info(f"[{ai_id}] Target for {ticker} requires < 1 share change ({shares_to_trade}). Skipping execution.")
                    success_tickers.append(ticker)
                    continue

                action = 'BUY' if shares_to_trade > 0 else 'SELL'
                
                ib_ticker = ticker.replace('.', ' ').replace('-', ' ')
                contract = Stock(ib_ticker, 'SMART', 'USD')
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
                    
                    # Record in ledger as estimated trade
                    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    db.add_ledger_entry({
                        "id": str(uuid.uuid4()),
                        "run_id": ai_id,
                        "ticker": ticker,
                        "action": action,
                        "qty": actual_shares_signed,
                        "estimated_price": current_price,
                        "execution_price": None,
                        "commission": 0.0,
                        "status": "estimated",
                        "ib_execution_id": None,
                        "timestamp": now_iso
                    })
                    
                    success_tickers.append(ticker)
                    logger.info(f"[{ai_id}] Successfully placed {action} {abs_shares} {ticker} (recorded in ledger as estimated)")
                else:
                    logger.warning(f"[{ai_id}] Order for {ticker} failed with status: {trade.orderStatus.status}")
            
            # Rebuild virtual portfolio from ledger if at least one order was placed
            if success_tickers:
                self._rebuild_portfolio_from_ledger(ai_id)
                logger.info(f"[{ai_id}] Virtual portfolio rebuilt from ledger for: {success_tickers}")
            else:
                logger.warning(f"[{ai_id}] No orders accepted by IBKR — virtual portfolio NOT changed.")
            return success_tickers

        except Exception as e:
            logger.error(f"[{ai_id}] Error executing IBKR batch trades: {e}")
            raise e
        finally:
            if self.ib.isConnected():
                self.ib.disconnect()
        return []

    def reconcile_portfolio(self, ai_id):
        """
        Connects to IBKR, retrieves fills, matches them to estimated ledger entries,
        reconciles them, and rebuilds the virtual portfolio.
        """
        try:
            if not self.ib.isConnected():
                self.ib.connect(self.host, self.port, clientId=self.client_id)
            
            fills = self.ib.fills()
            logger.info(f"[{ai_id}] Fetched {len(fills)} total fills from IBKR")
            
            ai_fills = [f for f in fills if f.execution.orderRef == ai_id]
            logger.info(f"[{ai_id}] Found {len(ai_fills)} fills matching orderRef={ai_id}")
            
            reconciled_count = 0
            for fill in ai_fills:
                exec_id = fill.execution.execId
                ticker = fill.contract.symbol
                
                # Check if this execution is already in the ledger
                existing = db.get_ledger_entry_by_execution_id(exec_id)
                if existing:
                    continue
                
                qty = float(fill.execution.shares)
                side = fill.execution.side  # 'BOT' or 'SLD'
                price = float(fill.execution.price)
                commission = float(fill.commissionReport.commission) if fill.commissionReport else 0.0
                
                qty_change = qty if side == 'BOT' else -qty
                
                # Find matching estimated ledger entry
                est_entry = db.find_matching_estimated_trade(ai_id, ticker, qty_change)
                
                exec_time_str = fill.execution.time.isoformat() if hasattr(fill.execution.time, 'isoformat') else str(fill.execution.time)
                if est_entry:
                    # Update existing estimated entry
                    db.update_ledger_entry(
                        est_entry["id"],
                        status="confirmed",
                        execution_price=price,
                        commission=commission,
                        ib_execution_id=exec_id,
                        timestamp=exec_time_str
                    )
                    logger.info(f"[{ai_id}] Reconciled estimated trade {est_entry['id']} for {ticker} with actual fill price {price}")
                else:
                    # Add new ledger entry directly
                    import uuid
                    db.add_ledger_entry({
                        "id": str(uuid.uuid4()),
                        "run_id": ai_id,
                        "ticker": ticker,
                        "action": "BUY" if side == 'BOT' else "SELL",
                        "qty": qty_change,
                        "estimated_price": price,
                        "execution_price": price,
                        "commission": commission,
                        "status": "confirmed",
                        "ib_execution_id": exec_id,
                        "timestamp": exec_time_str
                    })
                    logger.info(f"[{ai_id}] Created new ledger entry for direct fill: {ticker} {qty_change} shares @ {price}")
                
                reconciled_count += 1
            
            # Rebuild virtual portfolio from scratch
            self._rebuild_portfolio_from_ledger(ai_id)
            return reconciled_count
            
        except Exception as e:
            logger.error(f"[{ai_id}] Error in reconcile_portfolio: {e}")
            raise e
        finally:
            if self.ib.isConnected():
                self.ib.disconnect()
        return []
