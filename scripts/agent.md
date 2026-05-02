# Scripts: `scripts`

This directory contains standalone utility scripts for development, maintenance, or specific ad-hoc tasks, separate from the core application or testing suite.

## Key Files

*   **`smoke_structured_output.py`**: A smoke test script verifying that the LLM clients correctly respect structured output constraints (Pydantic schemas) required by the `tradingagents` framework. This is critical because the graph's reliability depends on predictable JSON/structured outputs from the models.

## Usage

These scripts are usually executed directly from the root of the repository, e.g., `python -m scripts.smoke_structured_output`.

If you add a new diagnostic or maintenance tool, place it here rather than polluting the `tradingagents` core or the `cli` folder.
