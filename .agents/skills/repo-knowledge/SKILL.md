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
5. **Update Context As You Go**: When you introduce new modules, features, or architectural changes, you MUST automatically update the relevant `agent.md` files and `TODO.md` to keep the repository knowledge current without being explicitly asked.

By reading these `agent.md` files, you will gain immediate, accurate context about the project without needing to blindly search through the repository.
