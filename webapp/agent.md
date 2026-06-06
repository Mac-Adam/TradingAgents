# Webapp & Backend Package: `webapp`

This directory handles the user interface, backend scheduling, execution management, and data persistence for multiple concurrent AI wallets/runs.

## Architecture & Subfolders

*   **`backend/`**: Contains the API server and task execution daemon.
    *   `main.py`: The FastAPI application that handles web requests and interacts with `db.py`. Exposes GET `/api/tasks/{task_id}/traces` for execution tracing.
    *   `db.py`: SQLite-backed persistence layer. Stores definitions for `runs`, `tasks`, `decision_history`, `ai_portfolios`, `pending_trades`, and `task_traces` (all LLM and tool trace calls).
    *   `tracing_handler.py`: Contains `TracingCallbackHandler` which tracks langchain model and tool callback start/end/error events.
    *   `task_executor.py`: A daemon worker thread that processes tasks sequentially. It supports multiple `task_type`s (e.g., `analysis` for LLM propagation, `execution` for batch trade execution). Runs 7-day automated trace record cleanup (`db.cleanup_old_traces`) on task execution.
    *   `reports/`: Directory where generated markdown reports for each analysis are saved.

## Workflows

1. **Analysis Task**: The user queues an `analysis` task. The worker runs `TradingAgentsGraph`, which performs the multi-agent debate and eventually adds an actionable decision to the `pending_trades` table.
2. **Execution Task**: A separate `execution` task is queued (usually automatically or on a schedule) to aggregate the results. The worker pulls all unexecuted decisions from `pending_trades`, uses `IBKRExecutor` to calculate sub-account sizing based on the virtual portfolio, queues MOO trades on IBKR, and clears the pending ledger.
3. **Execution Tracing**: During task run, individual agent nodes trace their LLM inputs, LLM outputs, and tool calls. Users can inspect these in real-time or historically via the **Details** tab on the frontend task modal, which queries the traces API.

## Interacting with the Database

If you need to query or modify the `backend.db` file during troubleshooting:
- Use python one-liners (e.g. `python3 -c "import sqlite3; ..."`) as the `sqlite3` CLI is often missing.
- Ensure any schema changes made in `db.py` are reflected in this documentation and the `repo-knowledge` skill.
