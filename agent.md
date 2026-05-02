# TradingAgents - Repository Overview

**TradingAgents** is a multi-agent LLM financial trading framework designed to mirror the dynamics of real-world trading firms. By deploying specialized LLM-powered agents (analysts, researchers, risk management, portfolio manager, and traders), the platform collaboratively evaluates market conditions and informs trading decisions.

## Directory Map

This repository is structured into several key components. For deeper context, an `agent.md` file is provided within each major subfolder detailing its specific role and internals.

*   **`tradingagents/`**: The core package and engine of the framework. It houses the LLM clients, trading graphs (LangGraph workflows), dataflows (AlphaVantage, Yahoo Finance, etc.), and the specific agent implementations (analysts, managers, researchers, trader). **Start here if you are modifying core trading logic or adding new agents.** -> *See `tradingagents/agent.md`*
*   **`cli/`**: The Command Line Interface logic. Contains the interactive prompt for running analyses and the output handling mechanisms. -> *See `cli/agent.md`*
*   **`scripts/`**: Utility and maintenance scripts (e.g., smoke testing the structured outputs). -> *See `scripts/agent.md`*
*   **`tests/`**: The test suite covering signal processing, memory logs, model validation, and structured outputs. -> *See `tests/agent.md`*
*   **`assets/`**: Static resources like architectural diagrams and sample output screenshots. -> *See `assets/agent.md`*

## Key Entry Points

*   **`main.py`**: A minimal entry point in the root that delegates to the CLI or programmatic run logic.
*   **`tradingagents.graph.trading_graph.TradingAgentsGraph`**: The primary Python class for initializing the multi-agent graph programmatically.

## Development Workflows

When working in this repository:
1.  **Check Context**: If you are entering a new module, read its local `agent.md`.
2.  **Configurations**: Check `.env` files and `tradingagents/default_config.py` for API keys and default behaviors (LLM provider, models, debate rounds).
3.  **Checkpoints**: Remember that the framework supports checkpoint resuming (saving state via SQLite) and a persistent decision log. Be mindful of these mechanisms when changing the flow or adding new nodes in the graph.
