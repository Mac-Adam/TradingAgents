import sqlite3
import json
import os
import threading
from typing import Dict, List, Optional, Any

from tradingagents.ticker import Ticker

DB_PATH = os.path.join(os.path.dirname(__file__), "backend.db")
_db_lock = threading.Lock()

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    wallet_name TEXT,
                    config_file TEXT,
                    env_file TEXT,
                    account_type TEXT,
                    status TEXT,
                    created_at TEXT,
                    initial_cash REAL DEFAULT 100000.0
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    ticker TEXT,
                    status TEXT,
                    created_at TEXT,
                    scheduled_at TEXT,
                    recurrence TEXT,
                    report_path TEXT,
                    error TEXT,
                    decision TEXT,
                    stats TEXT,
                    cancel_requested INTEGER DEFAULT 0
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS decision_history (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    task_id TEXT,
                    ticker TEXT,
                    action TEXT,
                    rationale TEXT,
                    full_report_path TEXT,
                    timestamp TEXT,
                    stats TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS task_logs (
                    task_id TEXT PRIMARY KEY,
                    logs TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ai_portfolios (
                    ai_id TEXT PRIMARY KEY,
                    cash REAL,
                    positions TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_trades (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    ticker TEXT,
                    decision TEXT,
                    created_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trade_ledger (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    ticker TEXT,
                    action TEXT,
                    qty REAL,
                    estimated_price REAL,
                    execution_price REAL,
                    commission REAL,
                    status TEXT,
                    ib_execution_id TEXT,
                    timestamp TEXT
                )
            ''')
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'analysis'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE decision_history ADD COLUMN task_type TEXT DEFAULT 'analysis'")
            except sqlite3.OperationalError:
                pass
            conn.commit()

# --- RUNS ---
def get_runs() -> List[Dict]:
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows]

def add_run(run: Dict):
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO runs (id, wallet_name, config_file, env_file, account_type, status, created_at, initial_cash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (run['id'], run['wallet_name'], run['config_file'], run['env_file'], run['account_type'], run['status'], run['created_at'], run.get('initial_cash', 100000.0)))
            conn.commit()

def remove_run(run_id: str):
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()

# --- TASKS ---
def get_tasks_for_run(run_id: str) -> List[Dict]:
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE run_id = ? ORDER BY created_at DESC", (run_id,)).fetchall()
            tasks = []
            for r in rows:
                d = dict(r)
                d['stats'] = json.loads(d['stats']) if d['stats'] else None
                d['cancel_requested'] = bool(d['cancel_requested'])
                tasks.append(d)
            return tasks

def add_task(task_dict: Dict):
    stats_str = json.dumps(task_dict.get('stats')) if task_dict.get('stats') else None
    task_type = task_dict.get('task_type', 'analysis')
    ticker = Ticker(task_dict['ticker']).canonical
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO tasks (id, run_id, ticker, status, created_at, scheduled_at, recurrence, report_path, error, decision, stats, cancel_requested, task_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (task_dict['id'], task_dict['run_id'], ticker, task_dict['status'],
                  task_dict['created_at'], task_dict['scheduled_at'], task_dict['recurrence'],
                  task_dict['report_path'], task_dict['error'], task_dict['decision'], stats_str,
                  int(task_dict.get('cancel_requested', False)), task_type))
            conn.commit()

def update_task(task_dict: Dict):
    stats_str = json.dumps(task_dict.get('stats')) if task_dict.get('stats') else None
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                UPDATE tasks 
                SET status = ?, scheduled_at = ?, recurrence = ?, report_path = ?, error = ?, decision = ?, stats = ?, cancel_requested = ?
                WHERE id = ?
            ''', (task_dict['status'], task_dict['scheduled_at'], task_dict['recurrence'],
                  task_dict['report_path'], task_dict['error'], task_dict['decision'], stats_str,
                  int(task_dict.get('cancel_requested', False)), task_dict['id']))
            conn.commit()

def get_task(task_id: str) -> Optional[Dict]:
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                d = dict(row)
                d['stats'] = json.loads(d['stats']) if d['stats'] else None
                d['cancel_requested'] = bool(d['cancel_requested'])
                return d
            return None

def remove_task(task_id: str) -> bool:
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row and row['status'] == 'queued':
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                return True
            return False

def get_queued_tasks() -> List[Dict]:
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE status = 'queued' ORDER BY created_at ASC").fetchall()
            tasks = []
            for r in rows:
                d = dict(r)
                d['stats'] = json.loads(d['stats']) if d['stats'] else None
                d['cancel_requested'] = bool(d['cancel_requested'])
                tasks.append(d)
            return tasks

def delete_task_force(task_id: str):
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()

def clear_all_tasks(run_id: str):
    with _db_lock:
        with get_conn() as conn:
            conn.execute("DELETE FROM tasks WHERE run_id = ?", (run_id,))
            conn.commit()

def claim_next_task(now_iso: str) -> Optional[Dict]:
    """Atomically find the next ready task and mark it as 'running'."""
    with _db_lock:
        with get_conn() as conn:
            # Find the oldest task that is ready to run
            # Ready = status is 'queued' AND (no schedule OR schedule time reached)
            query = """
                SELECT id FROM tasks 
                WHERE status = 'queued' 
                  AND (scheduled_at IS NULL OR scheduled_at <= ?)
                  AND run_id NOT IN (
                      SELECT run_id FROM tasks WHERE status = 'running'
                  )
                ORDER BY created_at ASC
                LIMIT 1
            """
            row = conn.execute(query, (now_iso,)).fetchone()
            if not row:
                return None
            
            task_id = row['id']
            conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task_id,))
            conn.commit()
            
            # Re-fetch the full task to return to executor
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            d = dict(row)
            d['stats'] = json.loads(d['stats']) if d['stats'] else None
            d['cancel_requested'] = bool(d['cancel_requested'])
            return d

# --- HISTORY ---
def add_decision(decision: Dict):
    stats_str = json.dumps(decision.get('stats')) if decision.get('stats') else None
    task_type = decision.get('task_type', 'analysis')
    ticker = Ticker(decision['ticker']).canonical
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO decision_history (id, run_id, task_id, ticker, action, rationale, full_report_path, timestamp, stats, task_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (decision['id'], decision['run_id'], decision['task_id'], ticker,
                  decision['action'], decision['rationale'], decision['full_report_path'],
                  decision['timestamp'], stats_str, task_type))
            conn.commit()

def get_history_for_run(run_id: str) -> List[Dict]:
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM decision_history WHERE run_id = ? ORDER BY timestamp DESC", (run_id,)).fetchall()
            history = []
            for r in rows:
                d = dict(r)
                d['stats'] = json.loads(d['stats']) if d['stats'] else None
                history.append(d)
            return history

def get_history_entry(history_id: str) -> Optional[Dict]:
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM decision_history WHERE id = ?", (history_id,)).fetchone()
            if row:
                d = dict(row)
                d['stats'] = json.loads(d['stats']) if d['stats'] else None
                return d
            return None

# --- LOGS ---
def save_task_logs(task_id: str, logs: str):
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO task_logs (task_id, logs) VALUES (?, ?)
                ON CONFLICT(task_id) DO UPDATE SET logs = excluded.logs
            ''', (task_id, logs))
            conn.commit()

def get_task_logs(task_id: str) -> Optional[str]:
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute("SELECT logs FROM task_logs WHERE task_id = ?", (task_id,)).fetchone()
            if row:
                return row['logs']
            return None

# --- AI PORTFOLIOS ---
def get_ai_portfolio(ai_id: str) -> Dict:
    run_id = ai_id
    if ai_id.endswith("_checkpoint"):
        run_id = ai_id[:-11]
        
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM ai_portfolios WHERE ai_id = ?", (ai_id,)).fetchone()
            if row:
                return {
                    "cash": row["cash"],
                    "positions": json.loads(row["positions"])
                }
            
            # Fetch initial_cash from the run record
            initial_cash = 100000.0
            run_row = conn.execute("SELECT initial_cash FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run_row and run_row["initial_cash"] is not None:
                initial_cash = float(run_row["initial_cash"])
                
            return {
                "cash": initial_cash,
                "positions": {}
            }

def save_ai_portfolio(ai_id: str, cash: float, positions: Dict):
    normalized_positions = {}
    for k, v in positions.items():
        if k.startswith("_"):
            normalized_positions[k] = v
        else:
            normalized_positions[Ticker(k).canonical] = v
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO ai_portfolios (ai_id, cash, positions)
                VALUES (?, ?, ?)
                ON CONFLICT(ai_id) DO UPDATE SET
                    cash = excluded.cash,
                    positions = excluded.positions
            ''', (ai_id, cash, json.dumps(normalized_positions)))
            conn.commit()

# --- PENDING TRADES ---
def add_pending_trade(run_id: str, ticker: str, decision: str):
    import uuid
    from datetime import datetime, timezone
    trade_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ticker_canonical = Ticker(ticker).canonical
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO pending_trades (id, run_id, ticker, decision, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (trade_id, run_id, ticker_canonical, decision, now_iso))
            conn.commit()

def get_pending_trades(run_id: str) -> List[Dict]:
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM pending_trades WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
            return [dict(row) for row in rows]

def clear_pending_trades(run_id: str, ids: List[str] = None):
    with _db_lock:
        with get_conn() as conn:
            if ids:
                placeholders = ','.join('?' * len(ids))
                conn.execute(f"DELETE FROM pending_trades WHERE run_id = ? AND id IN ({placeholders})", [run_id] + ids)
            else:
                conn.execute("DELETE FROM pending_trades WHERE run_id = ?", (run_id,))
            conn.commit()

# --- TRADE LEDGER ---
def add_ledger_entry(entry: Dict):
    ticker = Ticker(entry["ticker"]).canonical
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                INSERT INTO trade_ledger (id, run_id, ticker, action, qty, estimated_price, execution_price, commission, status, ib_execution_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry["id"],
                entry["run_id"],
                ticker,
                entry["action"],
                float(entry["qty"]),
                float(entry["estimated_price"]),
                float(entry["execution_price"]) if entry.get("execution_price") is not None else None,
                float(entry.get("commission", 0.0) or 0.0),
                entry["status"],
                entry.get("ib_execution_id"),
                entry["timestamp"]
            ))
            conn.commit()

def get_ledger_entries(run_id: str) -> List[Dict]:
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM trade_ledger WHERE run_id = ? ORDER BY timestamp ASC", (run_id,)).fetchall()
            return [dict(row) for row in rows]

def get_ledger_entry_by_execution_id(exec_id: str) -> Optional[Dict]:
    with _db_lock:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM trade_ledger WHERE ib_execution_id = ?", (exec_id,)).fetchone()
            if row:
                return dict(row)
            return None

def find_matching_estimated_trade(run_id: str, ticker: str, qty_change: float) -> Optional[Dict]:
    ticker_canonical = Ticker(ticker).canonical
    with _db_lock:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM trade_ledger WHERE run_id = ? AND ticker = ? AND status = 'estimated' ORDER BY timestamp ASC", (run_id, ticker_canonical)).fetchall()
            for row in rows:
                row_qty = float(row["qty"])
                if (row_qty > 0 and qty_change > 0) or (row_qty < 0 and qty_change < 0):
                    return dict(row)
            return None

def update_ledger_entry(entry_id: str, status: str, execution_price: float, commission: float, ib_execution_id: str, timestamp: str):
    with _db_lock:
        with get_conn() as conn:
            conn.execute('''
                UPDATE trade_ledger
                SET status = ?, execution_price = ?, commission = ?, ib_execution_id = ?, timestamp = ?
                WHERE id = ?
            ''', (status, execution_price, commission, ib_execution_id, timestamp, entry_id))
            conn.commit()
