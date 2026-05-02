# Core Package: `tradingagents`

This directory is the heart of the TradingAgents framework. It defines the multi-agent architecture, the data pipelines, the graph logic, and the interactions with LLM APIs.

## Architecture & Subfolders

*   **`agents/`**: Contains the implementations of the specialized roles.
    *   `analysts/`: Fundamental, News, Sentiment, and Technical analysts.
    *   `researchers/`: Bullish and bearish researchers for structured debate.
    *   `risk_mgmt/`: Risk management agents evaluating portfolio risk.
    *   `managers/`: Portfolio managers responsible for the final trading decisions.
    *   `trader/`: Trader agents synthesizing insights into an action.
    *   `schemas.py`: Pydantic models standardizing the output structures from the agents.
*   **`dataflows/`**: Modules handling data retrieval and normalization.
    *   Handles data from AlphaVantage (fundamentals, indicators, news, stock data) and Yahoo Finance (yfinance).
    *   `interface.py` & `stockstats_utils.py`: Abstractions and utilities for financial math and data presentation.
*   **`graph/`**: The LangGraph implementation mapping the workflow of the agents.
    *   `trading_graph.py`: The `TradingAgentsGraph` class that initializes and runs the `propagate()` flow.
    *   `checkpointer.py`: Logic for saving and resuming the state (SQLite checkpointer).
    *   `conditional_logic.py` / `propagation.py` / `reflection.py`: Logic controlling how the state moves between the agents.
*   **`llm_clients/`**: Adapters for different LLM providers (OpenAI, Google, Anthropic, DeepSeek, xAI, OpenRouter, Azure, Ollama). Uses a Factory pattern (`factory.py`) to instantiate clients based on config.
    *   `model_catalog.py`: Defines supported models and their context window limits.

## How to make changes

1.  **Adding a new Agent**: Add the new agent definition to the `agents/` folder. Update the state machine in `graph/trading_graph.py` to route to the new agent. Ensure outputs are structured via Pydantic in `schemas.py`.
2.  **Adding a new LLM Provider**: Create a new client extending `base_client.py` in `llm_clients/`. Register it in `factory.py` and add supported models to `model_catalog.py`.
3.  **Adding a new Data Source**: Create a fetcher in `dataflows/` and integrate its output into the context provided to the analysts.

## Default Configurations
Check `default_config.py` for default values for LLM providers, debate rounds, caching, and persistence behaviors.
