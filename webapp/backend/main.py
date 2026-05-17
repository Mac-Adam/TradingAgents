import os
import uuid
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from task_executor import (
    add_task, remove_task, get_tasks_for_run,
    get_history_for_run, get_report_text, get_task_logs,
    start_worker, LIVE_STATES, get_runs, add_run, remove_run
)
import db as _db

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="TradingAgents Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GLOBAL_CONFIGS_DIR = os.path.join(PROJECT_ROOT, "global_configs")
GLOBAL_ENVS_DIR = os.path.join(PROJECT_ROOT, "global_envs")



# ── Env helpers ────────────────────────────────────────────────────────────────

def parse_env_file(env_filename: str) -> dict:
    env_path = os.path.join(GLOBAL_ENVS_DIR, env_filename)
    env_vars: dict = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def get_alpaca_client(env_filename: str):
    from alpaca.trading.client import TradingClient
    env = parse_env_file(env_filename)
    api_key = env.get("ALPACA_API_KEY")
    secret_key = env.get("ALPACA_API_SECRET")
    paper_str = env.get("ALPACA_PAPER", "true").lower()
    paper = paper_str in ("true", "1", "yes")
    if not api_key or not secret_key:
        raise HTTPException(status_code=400, detail="Alpaca credentials not found in env file.")
    return TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)


def resolve_account_type(env_filename: str) -> str:
    env = parse_env_file(env_filename)
    paper_str = env.get("ALPACA_PAPER", "true").lower()
    return "PAPER" if paper_str in ("true", "1", "yes") else "REAL"


# ── Request models ─────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    wallet_name: str
    config_file: str
    env_file: str


class TaskRequest(BaseModel):
    ticker: str
    schedule_mode: str = "asap"  # "asap" or "scheduled"
    scheduled_at: Optional[str] = None  # ISO datetime
    recurrence: Optional[str] = None  # None or "daily:HH:MM"
    task_type: str = "analysis"


# ── Startup: launch worker ────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    import db
    db.init_db()
    start_worker()


# ── Core endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "TradingAgents API is running"}


@app.get("/api/server-time")
def server_time():
    now = datetime.now(timezone.utc)
    return {
        "utc": now.isoformat(),
        "timezone": "UTC",
    }


@app.get("/api/configs")
def list_configs():
    if not os.path.exists(GLOBAL_CONFIGS_DIR):
        return []
    return [f for f in os.listdir(GLOBAL_CONFIGS_DIR) if f.endswith(".json")]


@app.get("/api/envs")
def list_envs():
    if not os.path.exists(GLOBAL_ENVS_DIR):
        return []
    return [f for f in os.listdir(GLOBAL_ENVS_DIR) if f.endswith(".env")]


@app.get("/api/runs")
def list_runs():
    return get_runs()


@app.post("/api/runs")
def create_run(run_req: RunRequest):
    run_id = str(uuid.uuid4())
    account_type = resolve_account_type(run_req.env_file)
    new_run = {
        "id": run_id,
        "wallet_name": run_req.wallet_name,
        "config_file": run_req.config_file,
        "env_file": run_req.env_file,
        "account_type": account_type,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    add_run(new_run)
    return new_run


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    remove_run(run_id)
    return {"status": "ok"}


# ── Alpaca live-data endpoints ─────────────────────────────────────────────────

@app.get("/api/runs/{run_id}/account")
def get_account(run_id: str):
    run = next((r for r in get_runs() if r["id"] == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        env = parse_env_file(run["env_file"])
        if "IB_HOST" in env or "ALPACA_API_KEY" not in env:
            import db
            import yfinance as yf
            portfolio = db.get_ai_portfolio(run_id)
            cash = float(portfolio["cash"])
            
            portfolio_value = cash
            for ticker, qty in portfolio["positions"].items():
                if qty != 0:
                    try:
                        stock = yf.Ticker(ticker)
                        price = float(stock.fast_info['lastPrice'])
                        portfolio_value += qty * price
                    except Exception as e:
                        logging.warning(f"Failed to fetch price for {ticker}: {e}")

            return {
                "equity": portfolio_value,
                "portfolio_value": portfolio_value,
                "cash": cash,
                "buying_power": cash,
                "currency": "USD",
                "account_number": run_id,
                "status": "ACTIVE (IBKR VIRTUAL)",
            }
        
        client = get_alpaca_client(run["env_file"])
        acct = client.get_account()
        return {
            "equity": float(acct.equity),
            "portfolio_value": float(acct.portfolio_value),
            "cash": float(acct.cash),
            "buying_power": float(acct.buying_power),
            "currency": acct.currency,
            "account_number": acct.account_number,
            "status": str(acct.status),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Broker API error: {str(e)}")


@app.get("/api/runs/{run_id}/positions")
def get_positions(run_id: str):
    run = next((r for r in get_runs() if r["id"] == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        env = parse_env_file(run["env_file"])
        if "IB_HOST" in env or "ALPACA_API_KEY" not in env:
            import db
            import yfinance as yf
            portfolio = db.get_ai_portfolio(run_id)
            positions = []
            
            for ticker, qty in portfolio["positions"].items():
                if qty != 0:
                    price = None
                    try:
                        stock = yf.Ticker(ticker)
                        price = float(stock.fast_info['lastPrice'])
                    except Exception as e:
                        logging.warning(f"Failed to fetch price for {ticker}: {e}")
                    
                    market_value = (qty * price) if price is not None else None
                    positions.append({
                        "symbol": ticker,
                        "qty": float(qty),
                        "avg_entry_price": 0.0,
                        "current_price": price,
                        "market_value": market_value,
                        "unrealized_pl": 0.0,
                        "unrealized_plpc": 0.0,
                        "side": "long" if qty > 0 else "short",
                    })
            return positions

        client = get_alpaca_client(run["env_file"])
        positions = client.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price) if p.current_price else None,
                "market_value": float(p.market_value) if p.market_value else None,
                "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else None,
                "unrealized_plpc": float(p.unrealized_plpc) if p.unrealized_plpc else None,
                "side": str(p.side),
            }
            for p in positions
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Broker API error: {str(e)}")


# ── Task queue endpoints ──────────────────────────────────────────────────────

@app.post("/api/runs/{run_id}/tasks")
def create_task(run_id: str, req: TaskRequest):
    run = next((r for r in get_runs() if r["id"] == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    task = add_task(
        run_id=run_id,
        ticker=req.ticker,
        schedule_mode=req.schedule_mode,
        scheduled_at=req.scheduled_at,
        recurrence=req.recurrence,
        task_type=req.task_type,
    )
    return task.to_dict()


@app.get("/api/runs/{run_id}/tasks")
def list_tasks(run_id: str):
    return get_tasks_for_run(run_id)


@app.delete("/api/runs/{run_id}/tasks/{task_id}")
def delete_task(run_id: str, task_id: str):
    import db
    task = db.get_task(task_id)
    if task and task['status'] == "running":
        task['cancel_requested'] = True
        db.update_task(task)
        return {"status": "ok", "message": "Cancellation requested"}
        
    if remove_task(task_id):
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Task not found or not in queued state")


@app.delete("/api/runs/{run_id}/tasks")
def reset_task_queue(run_id: str):
    """Nuclear option: delete ALL tasks for a run (queued, running, stuck, etc)."""
    import db
    db.clear_all_tasks(run_id)
    return {"status": "ok", "message": "All tasks cleared"}


# ── History endpoints ─────────────────────────────────────────────────────────

@app.get("/api/runs/{run_id}/history")
def list_history(run_id: str):
    return get_history_for_run(run_id)


@app.get("/api/runs/{run_id}/history/{history_id}/report")
def get_history_report(run_id: str, history_id: str):
    text = get_report_text(run_id, history_id)
    if text is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": text}


# ── Logs endpoint ───────────────────────────────────────────────────────────

@app.get("/api/tasks/{task_id}/logs")
def task_logs(task_id: str):
    logs = get_task_logs(task_id)
    if logs is None:
        return {"logs": "No logs available yet (task may not have started)."}
    return {"logs": logs}

@app.get("/api/tasks/{task_id}/live")
def task_live_state(task_id: str):
    state = LIVE_STATES.get(task_id)
    if not state:
        return {"agent_status": {}, "messages": []}
    
    # state is a MessageBuffer from cli.main
    return {
        "agent_status": getattr(state, "agent_status", {}),
        "messages": list(getattr(state, "messages", []))
    }
