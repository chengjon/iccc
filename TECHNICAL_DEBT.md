# Technical Debt Report

**Last Updated:** 2025-12-10
**Status:** Resolved / Maintenance Mode

## 1. Critical Breakages (Resolved)

The architectural refactoring (Brain Engine + Role-Based Queues) is now stable and fully tested.

### A. Fixed Test Suite (Completed)
*   [x] **Redis Queue Tests**: Updated to match dynamic keys (`iccc:tasks:pending:{role}`).
*   [x] **Orchestrator Tests**: Updated assertions for task decomposition and fixed mock injection.
*   [x] **Import Errors**: Resolved conflict between `iccc/config.py` and `iccc/config/__init__.py`.

### B. New Feature Coverage (Completed)
*   [x] **Brain Engine**: Added `tests/brain/test_engine.py` covering cycle logic and prompts.
*   [x] **CLI Commands**: Added `tests/test_cli.py` covering `brain cycle` and `task import`.
*   [x] **Role Logic**: Added `tests/core/test_role_logic.py` covering role assignment rules.

## 2. Implementation Fragility (Resolved)

### A. Markdown Parsing (Fixed)
*   **Location**: `iccc/parsers/markdown_parser.py`
*   **Action**: Implemented robust regex parsing with JSON fallback.
*   **Status**: Tests passing (`tests/parsers/test_markdown_parser.py`).

### B. Stubbed Spec Parsers
*   **Location**: `iccc/core/specs.py`
*   **Issue**: `IdeasSpec.parse_requirements` and `MainTaskSpec.parse_tasks` are stubs.
*   **Risk**: Low. Direct use of `MarkdownTaskParser` by Brain Engine mitigates this for now.
*   **Status**: Pending future cleanup.

## 3. Configuration & Hardcoding

### A. Hardcoded Roles (Resolved)
*   **Action**: Usage of `RoleType` Enum is now enforced in new code and tests.
*   **Status**: Clean.

### B. Legacy Artifacts
*   **Location**: `iccc/agents/templates/`
*   **Issue**: Potentially redundant.
*   **Action**: Requires audit before deletion.

## Roadmap

1.  **Phase 2.1 - 2.3 (Stabilization)**: **COMPLETED**
2.  **Phase 3 (Cleanup)**:
    *   Audit and remove legacy `iccc/agents/templates/` if unused.
    *   Implement remaining stubs in `iccc/core/specs.py`.
    *   Enforce `pre-commit` hooks for linting.