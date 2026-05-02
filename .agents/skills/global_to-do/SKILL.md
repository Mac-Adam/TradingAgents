---
name: global_to-do
description: Tracks the comprehensive plan of all upcoming features and enhancements. Read the /app/TradingAgents/TODO.md file whenever modifying the codebase to keep future features in mind.
---
# Global To-Do Tracker

When working on this repository, you should always keep the future enhancements in mind. 
A comprehensive list of planned features is stored in `/app/TradingAgents/TODO.md`.

## Instructions
1. Check `/app/TradingAgents/TODO.md` before starting major changes to ensure your architecture allows for these future features.
2. When you implement a feature from the plan, update `/app/TradingAgents/TODO.md` to reflect the progress.
3. Keep future tasks (like multiple swarms, 24/7 runs, real-market trading) in mind so that current code refactoring does not block them.
4. **Always document every architectural decision**: Whenever you make structural changes, add a note to the `TODO.md` or a dedicated architecture document to preserve the context for future AI agents.
5. **Always prioritize scalability**: When adding new features, prioritize scalability and maintainability. Split code into new files and distinct modular components whenever possible to prevent monolithic files.
