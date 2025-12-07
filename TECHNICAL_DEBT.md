## Governance Strategy & Roadmap

### Phase 1: Immediate Hygiene (Completed)
1.  **Supplement Type Stubs:** Installed `types-PyYAML`, `types-redis`.
2.  **Incremental Annotation:** Core modules (`iccc/*.py`) are now type-safe.
3.  **MyPy Configuration:** Stubs installed, stricter checking enabled for core.

### Phase 2: Testing & Standardization (1-2 Months) - **Current Focus**
1.  **Boost Coverage:** Target >50% coverage for `agents` and `hooks`. Use `pytest-cov` to identify gaps.
2.  **Containerized Integration Tests:** Introduce `testcontainers` to replace hardcoded external dependencies.
3.  **Configuration Centralization:** Migrate `os.getenv` calls to a Pydantic `config/` module.

### Phase 3: Architectural Evolution (3-6 Months)
1.  **State Persistence:** Move in-memory Orchestrator state to Redis/MongoDB to allow process restarts.
2.  **Process Redundancy:** (If scale demands) Move to a multi-process/cluster model with distributed locks.

### Operational Guidelines
*   **CI Gates:** Add MyPy and Coverage checks to CI.
*   **Linting:** Automate via `ruff` in pre-commit hooks.
*   **Tracking:** Update this document weekly with progress.

## Governance Progress

### Type Safety (Phase 1)

| Module | Status | Remaining Errors | Last Updated | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `iccc/queue/redis_queue.py` | Completed | 0 | 2025-12-06 | Fixed generics and assignments. |
| `iccc/agents/subagent.py` | Completed | 0 | 2025-12-06 | Fixed via `types-PyYAML` stubs. |
| `iccc/agents/client.py` | Completed | 0 | 2025-12-06 | Fixed Redis generic and Anthropic types. |
| `iccc/agents/rate_limiter.py` | Completed | 0 | 2025-12-06 | Fixed Redis generics. |
| `iccc/orchestrator.py` | Completed | 0 | 2025-12-06 | Fixed task generics and typing imports. |
| `iccc/db/repositories.py` | Completed | 0 | 2025-12-06 | Generics added. |
| `iccc/locks/file_lock.py` | Completed | 0 | 2025-12-06 | Generics added. |
| `iccc/isolation/worktree.py` | Completed | 0 | 2025-12-06 | Fixed dict annotations and optional handling. |
| `iccc/agents/rate_limit_handler.py` | Completed | 0 | 2025-12-06 | Fixed Redis generic and Task attribute. |

### Testing & Coverage (Phase 2)

| Module | Current Coverage | Target | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `iccc/agents` | Low | >50% | Pending | Priority target. |
| `iccc/hooks` | Low | >50% | Pending | Priority target. |
| `iccc/config.py` | Low | >80% | Pending | Will be refactored. |