"""
Task executor module for TradingAgents dashboard.

Manages a global task queue across all wallets, runs TradingAgentsGraph
sequentially in a background daemon thread, and persists reports + decision
history.
"""

import io
import json
import os
import sys
import threading
import time
import logging
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Union

logger = logging.getLogger(__name__)

# ── Ensure the project root is importable ──────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

GLOBAL_CONFIGS_DIR = os.path.join(PROJECT_ROOT, "global_configs")
GLOBAL_ENVS_DIR = os.path.join(PROJECT_ROOT, "global_envs")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "webapp", "backend", "reports")


# ── Data models ────────────────────────────────────────────────────────────────

@dataclass
class TaskRecord:
    id: str
    run_id: str  # Which wallet/run owns this task
    ticker: str
    status: str = "queued"  # queued | running | completed | failed
    created_at: str = ""
    scheduled_at: Optional[str] = None  # ISO datetime, None = ASAP
    recurrence: Optional[str] = None  # None or "daily:HH:MM"
    report_path: Optional[str] = None
    error: Optional[str] = None
    decision: Optional[str] = None  # e.g. "Buy", "Sell", "Hold"
    stats: Optional[Dict] = None
    cancel_requested: bool = False
    task_type: str = "analysis"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionRecord:
    id: str
    run_id: str
    task_id: str
    ticker: str
    action: str  # Buy / Sell / Hold / Overweight / Underweight / FAILED
    rationale: str  # The final_trade_decision text (truncated for list)
    full_report_path: Optional[str] = None
    timestamp: str = ""
    stats: Optional[Dict] = None
    task_type: str = "analysis"

    def to_dict(self) -> dict:
        return asdict(self)


# ── Persistent Stores ──────────────────────────────────────────────────────────

import db

LIVE_STATES: Dict[str, Any] = {}  # Store cli.main.MessageBuffer per active task
_lock = threading.Lock()

def get_runs() -> List[Dict]:
    return db.get_runs()

def add_run(run: Dict):
    db.add_run(run)

def remove_run(run_id: str):
    db.remove_run(run_id)


def add_task(
    run_id: str,
    ticker: str,
    schedule_mode: str = "asap",
    scheduled_at: Optional[str] = None,
    recurrence: Optional[str] = None,
    task_type: str = "analysis",
) -> TaskRecord:
    """Add a task to the global queue."""
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    sched = None
    if schedule_mode == "scheduled" and scheduled_at:
        sched = scheduled_at
    # For recurring tasks submitted as ASAP, the first run is immediate
    # and the recurrence will clone the next one after completion.

    task = TaskRecord(
        id=task_id,
        run_id=run_id,
        ticker=ticker.upper().strip(),
        status="queued",
        created_at=now,
        scheduled_at=sched,
        recurrence=recurrence if schedule_mode == "scheduled" else None,
        task_type=task_type,
    )
    db.add_task(task.to_dict())
    return task


def remove_task(task_id: str) -> bool:
    """Remove a task if it's still queued."""
    return db.remove_task(task_id)


def get_tasks_for_run(run_id: str) -> List[dict]:
    """Return tasks for a wallet, newest first."""
    return db.get_tasks_for_run(run_id)


def get_history_for_run(run_id: str) -> List[dict]:
    """Return decision history for a wallet, newest first."""
    return db.get_history_for_run(run_id)


def get_report_text(run_id: str, history_id: str) -> Optional[str]:
    """Read the complete_report.md for a specific history entry."""
    entry = db.get_history_entry(history_id)
    if not entry or not entry.get('full_report_path'):
        return None
    report_file = Path(entry['full_report_path'])
    if report_file.exists():
        return report_file.read_text(encoding="utf-8")
    return None


def get_task_logs(task_id: str) -> Optional[str]:
    """Return captured logs for a task."""
    return db.get_task_logs(task_id)


# ── Worker ─────────────────────────────────────────────────────────────────────

def _get_next_task() -> Optional[TaskRecord]:
    """Pick the oldest task that is ready to run, atomically."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    task_dict = db.claim_next_task(now_iso)
    if task_dict:
        return TaskRecord(**task_dict)
    return None


def _load_config_for_run(run: dict) -> dict:
    """Build a merged config from DEFAULT_CONFIG + the wallet's JSON config."""
    from tradingagents.default_config import DEFAULT_CONFIG
    config = DEFAULT_CONFIG.copy()
    config_path = os.path.join(GLOBAL_CONFIGS_DIR, run.get("config_file", "default.json"))
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            overrides = json.load(f)
            config.update(overrides)
    return config


def _load_env_for_run(run: dict):
    """Load the wallet's .env file into the process environment."""
    from dotenv import load_dotenv
    env_path = os.path.join(GLOBAL_ENVS_DIR, run.get("env_file", ""))
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)


def _execute_task(task: TaskRecord):
    """Run TradingAgentsGraph.propagate for a single task, capturing all logs."""
    # ── Set up per-task log capture ────────────────────────────────
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.DEBUG)
    log_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    ))
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)

    def _save_logs():
        """Flush captured logs into TASK_LOGS."""
        log_handler.flush()
        db.save_task_logs(task.id, log_stream.getvalue())
        root_logger.removeHandler(log_handler)

    # Find the owning run
    run = next((r for r in get_runs() if r["id"] == task.run_id), None)
    if not run:
        task.status = "failed"
        task.error = "Wallet/run not found"
        logger.error("Task %s: wallet/run %s not found", task.id, task.run_id)
        _save_logs()
        _push_failed_to_history(task)
        return

    logger.info("Task %s: executing %s for wallet %s", task.id, task.ticker, run["wallet_name"])
    logger.info("Task %s: config_file=%s  env_file=%s", task.id, run.get("config_file"), run.get("env_file"))

    # Load env
    _load_env_for_run(run)

    # Build config
    config = _load_config_for_run(run)
    logger.info("Task %s: llm_provider=%s  deep=%s  quick=%s  backend_url=%s",
                task.id, config.get("llm_provider"), config.get("deep_think_llm"),
                config.get("quick_think_llm"), config.get("backend_url"))

    if getattr(task, "task_type", "analysis") == "bookkeeping":
        try:
            logger.info("Task %s: Running Bookkeeper for wallet %s", task.id, run["wallet_name"])
            import asyncio
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            from tradingagents.execution.ibkr_executor import IBKRExecutor
            executor = IBKRExecutor()
            
            reconciled_count = executor.reconcile_portfolio(run["id"])
            summary = f"Reconciled {reconciled_count} trades from IBKR executions"
            
            task.status = "completed"
            task.decision = summary
            logger.info("Task %s: %s", task.id, summary)
            history_entry = DecisionRecord(
                id=str(uuid.uuid4()),
                run_id=task.run_id,
                task_id=task.id,
                ticker="PORTFOLIO",
                action="Bookkeeping",
                rationale=summary,
                full_report_path=None,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                stats=None,
                task_type="bookkeeping",
            )
            db.add_decision(history_entry.to_dict())
            db.delete_task_force(task.id)
        except Exception as e:
            tb = traceback.format_exc()
            task.status = "failed"
            task.error = f"{type(e).__name__}: {str(e)}"
            logger.error("Task %s bookkeeping FAILED: %s\n%s", task.id, e, tb)
            _push_failed_to_history(task)
        finally:
            _save_logs()
        return

    if getattr(task, "task_type", "analysis") == "execution":
        try:
            logger.info("Task %s: Running standalone Trade Executor for wallet %s", task.id, run["wallet_name"])
            # ib_insync requires an asyncio event loop at import time (eventkit)
            import asyncio
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            from tradingagents.execution.ibkr_executor import IBKRExecutor
            executor = IBKRExecutor()
            
            # Fetch the pending trades for this run
            pending = db.get_pending_trades(run["id"])
            if not pending:
                logger.info("Task %s: No pending trades found", task.id)
                task.status = "completed"
                task.decision = "No trades pending"
                history_entry = DecisionRecord(
                    id=str(uuid.uuid4()),
                    run_id=task.run_id,
                    task_id=task.id,
                    ticker="PORTFOLIO",
                    action="No trades pending",
                    rationale="No pending trades found for this portfolio.",
                    full_report_path=None,
                    timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    stats=None,
                    task_type="execution",
                )
                db.add_decision(history_entry.to_dict())
                db.delete_task_force(task.id)
                return

            trades_to_make = []
            trade_ids_to_clear = []
            for entry in pending:
                decision = entry.get("decision", "")
                if "Target Weight" in decision:
                    trades_to_make.append({
                        "ai_id": run["id"], # Using run_id as the unique AI identifier
                        "ticker": entry["ticker"],
                        "decision": decision
                    })
                    trade_ids_to_clear.append(entry["id"])
            
            if trades_to_make:
                accepted_tickers = executor.batch_execute(trades_to_make) or []

                # Only clear pending trades for orders IBKR actually accepted.
                # Rejected orders remain in pending_trades for the next execution attempt.
                accepted_ids = [
                    entry["id"]
                    for entry in pending
                    if entry["ticker"] in accepted_tickers
                ]
                if accepted_ids:
                    db.clear_pending_trades(run["id"], accepted_ids)

                rejected_count = len(trades_to_make) - len(accepted_tickers)
                summary = f"Accepted {len(accepted_tickers)}/{len(trades_to_make)} orders"
                if rejected_count > 0:
                    summary += f" ({rejected_count} rejected by IBKR)"
            else:
                summary = "No trades to execute"

            task.status = "completed"
            task.decision = summary
            logger.info("Task %s: %s", task.id, summary)
            history_entry = DecisionRecord(
                id=str(uuid.uuid4()),
                run_id=task.run_id,
                task_id=task.id,
                ticker="PORTFOLIO",
                action=summary,
                rationale=summary,
                full_report_path=None,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                stats=None,
                task_type="execution",
            )
            db.add_decision(history_entry.to_dict())
            db.delete_task_force(task.id)
        except Exception as e:
            tb = traceback.format_exc()
            task.status = "failed"
            task.error = f"{type(e).__name__}: {str(e)}"
            logger.error("Task %s execution FAILED: %s\n%s", task.id, e, tb)
            _push_failed_to_history(task)
        finally:
            _save_logs()
        return

    # Cleanup old traces (past week retention)
    try:
        db.cleanup_old_traces(days=7)
    except Exception as e:
        logger.warning("Failed to cleanup old task traces: %s", e)

    trade_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Use all analysts (maxed-out run)
    selected_analysts = ["market", "social", "news", "fundamentals"]

    from cli.stats_handler import StatsCallbackHandler
    stats_handler = StatsCallbackHandler()

    from tracing_handler import TracingCallbackHandler
    tracing_handler = TracingCallbackHandler(task.id, run["id"])

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from cli.main import MessageBuffer, classify_message_type, update_analyst_statuses, save_report_to_disk
        from langchain_core.callbacks import BaseCallbackHandler
        
        class CancelCallbackHandler(BaseCallbackHandler):
            def on_llm_start(self, *args, **kwargs):
                db_t = db.get_task(task.id)
                if db_t and db_t.get('cancel_requested'):
                    raise Exception("Task canceled by user")
            def on_tool_start(self, *args, **kwargs):
                db_t = db.get_task(task.id)
                if db_t and db_t.get('cancel_requested'):
                    raise Exception("Task canceled by user")

        cancel_handler = CancelCallbackHandler()

        logger.info("Task %s: initializing TradingAgentsGraph...", task.id)
        graph = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            config=config,
            debug=True,
            callbacks=[stats_handler, cancel_handler, tracing_handler],
        )
        
        # We must set these properties on the graph since we are bypassing propagate()
        graph.ticker = task.ticker
        graph.trade_date = trade_date

        message_buffer = MessageBuffer()
        message_buffer.init_for_analysis(selected_analysts)
        with _lock:
            LIVE_STATES[task.id] = message_buffer

        logger.info("Task %s: starting stream for %s on %s", task.id, task.ticker, trade_date)
        
        # Resolve pending memory-log entries
        graph._resolve_pending_entries(task.ticker)
        
        past_context = graph.memory_log.get_past_context(task.ticker)
        init_agent_state = graph.propagator.create_initial_state(
            task.ticker, trade_date, past_context=past_context
        )
        args = graph.propagator.get_graph_args(callbacks=[stats_handler, cancel_handler, tracing_handler])

        trace = []
        for chunk in graph.graph.stream(init_agent_state, **args):
            db_t = db.get_task(task.id)
            if db_t and db_t.get('cancel_requested'):
                raise Exception("Task canceled by user")
            
            trace.append(chunk)
            
            # Update message buffer
            for message in chunk.get("messages", []):
                msg_id = getattr(message, "id", None)
                if msg_id is not None:
                    if msg_id in message_buffer._processed_message_ids:
                        continue
                    message_buffer._processed_message_ids.add(msg_id)

                msg_type, content = classify_message_type(message)
                if content and content.strip():
                    message_buffer.add_message(msg_type, content)

                if hasattr(message, "tool_calls") and message.tool_calls:
                    for tool_call in message.tool_calls:
                        if isinstance(tool_call, dict):
                            message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                        else:
                            message_buffer.add_tool_call(tool_call.name, tool_call.args)

            # Update analyst statuses
            update_analyst_statuses(message_buffer, chunk)

            # Research Team
            if chunk.get("investment_debate_state"):
                debate_state = chunk["investment_debate_state"]
                bull_hist = debate_state.get("bull_history", "").strip()
                bear_hist = debate_state.get("bear_history", "").strip()
                judge = debate_state.get("judge_decision", "").strip()
                if bull_hist or bear_hist:
                    message_buffer.update_agent_status("Bull Researcher", "in_progress")
                    message_buffer.update_agent_status("Bear Researcher", "in_progress")
                    message_buffer.update_agent_status("Research Manager", "in_progress")
                if judge:
                    message_buffer.update_agent_status("Bull Researcher", "completed")
                    message_buffer.update_agent_status("Bear Researcher", "completed")
                    message_buffer.update_agent_status("Research Manager", "completed")
                    message_buffer.update_agent_status("Trader", "in_progress")

            # Trading Team
            if chunk.get("trader_investment_plan"):
                if message_buffer.agent_status.get("Trader") != "completed":
                    message_buffer.update_agent_status("Trader", "completed")
                    message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

            # Risk Team
            if chunk.get("risk_debate_state"):
                risk_state = chunk["risk_debate_state"]
                agg_hist = risk_state.get("aggressive_history", "").strip()
                con_hist = risk_state.get("conservative_history", "").strip()
                neu_hist = risk_state.get("neutral_history", "").strip()
                judge = risk_state.get("judge_decision", "").strip()
                if agg_hist:
                    if message_buffer.agent_status.get("Aggressive Analyst") != "completed":
                        message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
                if con_hist:
                    if message_buffer.agent_status.get("Conservative Analyst") != "completed":
                        message_buffer.update_agent_status("Conservative Analyst", "in_progress")
                if neu_hist:
                    if message_buffer.agent_status.get("Neutral Analyst") != "completed":
                        message_buffer.update_agent_status("Neutral Analyst", "in_progress")
                if judge:
                    if message_buffer.agent_status.get("Portfolio Manager") != "completed":
                        message_buffer.update_agent_status("Portfolio Manager", "in_progress")
                        message_buffer.update_agent_status("Aggressive Analyst", "completed")
                        message_buffer.update_agent_status("Conservative Analyst", "completed")
                        message_buffer.update_agent_status("Neutral Analyst", "completed")
                        message_buffer.update_agent_status("Portfolio Manager", "completed")

        if not trace:
            raise Exception("Graph executed with no chunks")
        
        final_state = trace[-1]
        decision = final_state.get("final_trade_decision", "Hold")
        
        # Complete propagate side-effects
        graph.curr_state = final_state
        graph._log_state(trade_date, final_state)
        graph.memory_log.store_decision(task.ticker, trade_date, decision)

        stats = stats_handler.get_stats()
        task.stats = stats

        # Save report
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_dir = Path(REPORTS_DIR) / task.run_id / f"{task.ticker}_{timestamp_str}"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = save_report_to_disk(final_state, task.ticker, report_dir)

        # Extract Target Weight
        import re
        action_val = "Hold"
        if isinstance(decision, str):
            match = re.search(r"\*\*Target Weight\*\*:\s*(-?\d+)", decision)
            if match:
                action_val = f"Target Weight: {match.group(1)}"
                # Add to pending trades since we have an actionable target
                db.add_pending_trade(task.run_id, task.ticker, decision)
            else:
                action_val = "Completed"
        else:
            action_val = str(decision)

        # Extract rationale snippet
        rationale_full = final_state.get("final_trade_decision", "No rationale available.")
        rationale_snippet = rationale_full[:300] + ("..." if len(rationale_full) > 300 else "")

        # Record decision
        history_entry = DecisionRecord(
            id=str(uuid.uuid4()),
            run_id=task.run_id,
            task_id=task.id,
            ticker=task.ticker,
            action=action_val,
            rationale=rationale_snippet,
            full_report_path=str(report_file),
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            stats=stats,
            task_type="analysis",
        )
        db.add_decision(history_entry.to_dict())
        db.delete_task_force(task.id)

        task.status = "completed"
        task.decision = history_entry.action
        task.report_path = str(report_file)

        logger.info("Task %s: completed — decision=%s", task.id, task.decision)

    except Exception as e:
        tb = traceback.format_exc()
        task.status = "failed"
        task.error = f"{type(e).__name__}: {str(e)}"
        logger.error("Task %s FAILED: %s\n%s", task.id, e, tb)
        _push_failed_to_history(task)

    finally:
        _save_logs()


def _push_failed_to_history(task: TaskRecord):
    """Create a FAILED history entry so the user can see it in Decision History."""
    history_entry = DecisionRecord(
        id=str(uuid.uuid4()),
        run_id=task.run_id,
        task_id=task.id,
        ticker=task.ticker,
        action="FAILED",
        rationale=task.error or "Unknown error",
        full_report_path=None,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        stats=task.stats,
        task_type=getattr(task, 'task_type', 'analysis'),
    )
    db.add_decision(history_entry.to_dict())
    db.delete_task_force(task.id)


def _is_market_day(date: datetime) -> bool:
    """Return True if `date` (UTC, naive) falls on a NYSE trading day."""
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar('NYSE')
        date_str = date.strftime('%Y-%m-%d')
        schedule = nyse.schedule(start_date=date_str, end_date=date_str)
        return not schedule.empty
    except Exception as e:
        logger.warning("Market calendar check failed (%s); falling back to weekday check", e)
        return date.weekday() < 5  # Mon–Fri fallback


def _next_market_day(after: datetime, target_hour: int, target_minute: int) -> datetime:
    """Return the next NYSE trading day at the given UTC time, starting from `after`."""
    # Ensure after is aware UTC
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    candidate = after.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    # Advance until we land on a NYSE trading day
    while not _is_market_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def _handle_recurrence(task: TaskRecord):
    """If the task has a recurrence, schedule the next occurrence on a trading day."""
    if not task.recurrence:
        return
    # Parse "daily:HH:MM"
    parts = task.recurrence.split(":")
    if len(parts) == 3 and parts[0] == "daily":
        try:
            hour = int(parts[1])
            minute = int(parts[2])
            now = datetime.now(timezone.utc)
            next_run = _next_market_day(now, hour, minute)

            add_task(
                run_id=task.run_id,
                ticker=task.ticker,
                schedule_mode="scheduled",
                scheduled_at=next_run.isoformat().replace("+00:00", "Z"),
                recurrence=task.recurrence,
                task_type=task.task_type,
            )
            logger.info("Task %s: scheduled next recurrence at %s (next market day)", task.id, next_run.isoformat())
        except (ValueError, IndexError) as e:
            logger.warning("Failed to parse recurrence '%s': %s", task.recurrence, e)


def _worker_thread_func(task: TaskRecord):
    try:
        _execute_task(task)
    finally:
        # Handle recurrence for completed tasks
        if task.status == "completed":
            _handle_recurrence(task)

def _worker_loop():
    """
    Main worker loop. Runs in a daemon thread.
    """
    logger.info("Task executor worker started")
    while True:
        task = _get_next_task()
        if task is None:
            time.sleep(5)
            continue

        # Spawn a thread to execute this task concurrently
        t = threading.Thread(target=_worker_thread_func, args=(task,), daemon=True)
        t.start()

        # Small cooldown between tasks
        time.sleep(1)


def start_worker():
    """Start the background worker thread."""
    t = threading.Thread(target=_worker_loop, daemon=True)
    t.start()
    logger.info("Task executor worker thread launched")
    return t
