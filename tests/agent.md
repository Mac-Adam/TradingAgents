# Test Suite: `tests`

This directory contains the automated tests (pytest) ensuring the correctness and stability of the TradingAgents framework.

## Test Categories

*   **`test_checkpoint_resume.py`**: Validates the LangGraph SQLite checkpointer. Ensures that interrupted workflows can resume from the last successful node without repeating earlier steps.
*   **`test_google_api_key.py` / `test_model_validation.py`**: Tests for configuration and API key loading validation, especially checking that `model_catalog` correctly parses provided configurations.
*   **`test_memory_log.py`**: Tests the persistent decision log mechanism. Verifies that trading decisions are written correctly and that past reflections are properly injected into the context of future runs.
*   **`test_signal_processing.py`**: Validates the logic in the technical/fundamental signal handlers, ensuring the math and logic behind trading signals are correct.
*   **`test_structured_agents.py`**: Tests that agents properly initialize and their outputs conform to the strict Pydantic schemas.
*   **`test_ticker_symbol_handling.py`**: Verifies handling of edge cases in stock ticker symbols.
*   **`test_relative_tools.py`**: Verifies calculations of lookback windows and context-based trade date resolution for stock/news dataflows.
*   **`test_execution_tracing.py`**: Verifies langchain model/tool execution tracing context logic, callback triggers, database logging, 7-day retention cleanup, and Runnable node context wrapping.
*   **`conftest.py`**: Defines standard pytest fixtures, mocked responses, or test configurations used across the test suite.

## Running Tests

To run the full suite:
```bash
pytest tests/
```

When contributing new features to `tradingagents/`, always ensure accompanying unit tests are added here.
