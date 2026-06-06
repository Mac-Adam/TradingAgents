---
name: repo-knowledge
description: Instructs the agent to review the repository's hierarchical agent.md documentation before modifying code. Use when exploring or making changes to the TradingAgents codebase.
---

# Repository Knowledge Skill

When you start working on a task in the `TradingAgents` repository, you MUST follow these steps to orient yourself with the codebase structure and conventions:

## When to use this skill

- Use this whenever you are asked to fix a bug, add a feature, or explore the `TradingAgents` codebase.
- This is helpful for avoiding assumptions and understanding the multi-agent architecture and file locations.

## How to use it

1. **Start at the Root**: Read the high-level architecture overview located at `/app/TradingAgents/agent.md`.
2. **Drill Down**: Based on the task, identify the relevant subsystem (`tradingagents`, `cli`, `scripts`, `tests`, `assets`).
3. **Read Local Context**: Read the `agent.md` file located inside the specific subsystem folder you need to work in (e.g., if you are editing core logic, read `/app/TradingAgents/tradingagents/agent.md`).
4. **Follow Conventions**: Adhere to the design patterns and instructions outlined in those documentation files.
5. **Update Context As You Go**: When you introduce new modules, features, database schema changes, or architectural changes, you MUST automatically update the relevant `agent.md` files and `TODO.md` to keep the repository knowledge current without being explicitly asked.

## Database Interaction Rules

When interacting with the backend SQLite database (`/app/TradingAgents/webapp/backend/backend.db`):
- **DO NOT** assume the `sqlite3` CLI tool is available (it may return `command not found`).
- **ALWAYS** use Python scripts or one-liners via `python3 -c "import sqlite3; ..."` to query or modify the database reliably on your first attempt.
- **NEVER** use regex or simple file parsing (like `cat`) to extract data from `.db` or `.json` persistence files.
- **Task Traces**: The SQLite database contains a `task_traces` table storing execution logs of every LLM and tool invocation. Old traces are automatically cleaned up if they are older than 7 days (`db.cleanup_old_traces`).
- If you change the database schema or location, you **MUST** update this skill and the `webapp/agent.md` file immediately to reflect the new structure.

## Multi-Agent Graph Node Wrapping Rules

When extending or adding new nodes to the LangGraph execution flow:
- **ALWAYS** wrap your node function using `wrap_node_with_context(node_name, node_func)` inside [setup.py](file:///app/TradingAgents/tradingagents/graph/setup.py) to bind the node's name to the active `CURRENT_NODE_NAME` context variable.
- This ensures that execution callback tracing correctly maps LLM and tool calls back to their parent agent/analyst in the UI.
- If the node is a LangGraph Runnable (like `ToolNode`), the wrapper calls `.invoke` instead of trying to call it as a python function, preventing `TypeError` errors.
