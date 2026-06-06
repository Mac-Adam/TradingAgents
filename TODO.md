# TradingAgents Comprehensive Plan

## 1. Executing trades on real market (with a demo account)
- [x] **a)** Selected Interactive Brokers (IBKR) as the provider for market execution.
- [x] **b)** Allow the agent to make the trade after the decision is made.
- [x] **c)** Give agents knowledge about the current state of the trade (e.g., if propagation on NVDA is done, the manager knows that currently 5% of the portfolio is in NVIDIA).

## 2. Enhance UI
- [x] **a)** Select a framework (either stick with the CLI or get something more advanced, possibly even a website). -> Selected FastAPI + Vite/React + Tailwind
- [ ] **b)** Features / Requirements:
  - [ ] **24/7 Execution & Remote Attach/Detach**: Since the repo is on a remote PC connected via SSH, keep the app running 24/7 with the ability to "attach" and "detach" via SSH.
  - [ ] **Multiple 'runs'**: Ability to run multiple instances of the same (or different) swarms of agents simultaneously to evaluate different models/approaches on the real market demo.
  - [x] **Dashboard Display**: Display current balance of the account, its history, and the current portfolio. → IBKR Virtual Portfolio via SQLite.
  - [x] **Scheduler**: Allow setting propagation schedules. → Task executor with ASAP / scheduled / daily recurrence.
  - [x] **Visual Differentiation**: Ensure PAPER and REAL accounts are distinguished visually. → Red BG for REAL, blue badges for PAPER.

## 3. Enhance the framework
- [ ] **a)** **Ticker Selector**: The swarm currently requires the exact ticker to propagate. Add a "ticker selector" Agent (or swarm of agents) that analyzes the broad market and chooses interesting stocks possibly worth looking into. This would then be propagated by the already existing swarm of agents along with the stocks currently in the portfolio.
- [ ] **b)** **Report Maker**: At the end of each run, add an additional agent (Report Maker) that analyzes the responses and prepares a summary for future agents to use (for example, so that they know why they bought something some time ago).
- [x] **c)** **Wallet View Backend Integration**: 
  - [x] Connect Wallet View to real balance/equity APIs.
  - [x] Connect Wallet View to real active trades APIs.
  - [x] Implement task scheduling and automation bots for the Agent Queue. → `task_executor.py` with sequential worker thread.
  - [x] Implement full execution trace details (LLM/tool payloads) grouped by agent in the task details panel.

## Architectural Notes
- **Task Executor**: `webapp/backend/task_executor.py` runs a single daemon worker thread that processes tasks sequentially across all wallets. Env vars are loaded per-task via `dotenv(override=True)`. This means tasks from different wallets are safe but run one-at-a-time.
- **Task Types**: `task_executor` supports multiple `task_type`s (e.g., `analysis`, `execution`). Both types of tasks can be scheduled immediately (ASAP) or for future execution (Scheduled / Daily Recurrence). The `analysis` task runs the LLM graph and pushes actionable decisions into the `pending_trades` SQLite table. The `execution` task pulls from `pending_trades` to execute batches on IBKR, ensuring scalability and decoupling of analysis and execution. When tasks are recurring, their specific `task_type` is correctly preserved across iterations.
- **Reports**: Saved to `webapp/backend/reports/{run_id}/{TICKER_TIMESTAMP}/` using `cli.main.save_report_to_disk`.
- **IBKR Executor**: Uses `webapp/backend/db.py` to maintain virtual sub-accounts (`ai_portfolios`) since paper IBKR accounts are limited to one per user. Trade orders are tagged via `orderRef` to track which AI placed them.
- **Execution Tracing**: All LLM and tool invocations are traced during graph execution using `TracingCallbackHandler` (defined in [tracing_handler.py](file:///app/TradingAgents/webapp/backend/tracing_handler.py)). Traces are saved in the SQLite `task_traces` table. A 7-day retention cleanup policy runs automatically via `db.cleanup_old_traces` on new task executions.
- **Node Context Wrapping**: Node executions are wrapped by `wrap_node_with_context` in [setup.py](file:///app/TradingAgents/tradingagents/graph/setup.py) to bind the active node name to `CURRENT_NODE_NAME` contextvar. If the node is a LangGraph Runnable (like `ToolNode`), the wrapper calls `.invoke` instead of calling the object directly as a function.
