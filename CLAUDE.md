<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**iCCC (i-Claude Code CLI)** is a multi-agent orchestration system for managing and running multiple AI CLI instances (Claude Code, iflow, Gemini, Opencode) in parallel to collaboratively complete software development tasks.

**Current State:** ✅ **Core functionality development complete** - All major features implemented and tested (200+ tests, 100% pass rate).

## Architecture

### Multi-Agent Paradigm

```
Master CLI (Orchestrator/Meta-Agent)
    │  Uses Claude Opus 4 for high-level reasoning
    │  AI-powered task decomposition (HTN/STRIPS planning)
    │  Adaptive replanning on failures
    ▼
Redis Message Bus + MongoDB Storage
    │  Task queue, file locks, pub/sub events
    │  Project/Agent/Task persistence
    ▼
Worker Agents (Parallel Execution)
    ├──► Frontend Expert (Sonnet 4) - React/Vue/TypeScript
    ├──► Backend Expert (Sonnet 4) - API/Database/Architecture
    ├──► Test Expert (Haiku 3.5) - TDD/QA/Coverage
    └──► Code Reviewer (Sonnet 4) - Quality/Security/Performance
```

### Key Components

1. **Master Orchestrator** (`iccc/orchestrator.py`):
   - Central intelligence using Claude Opus
   - Task decomposition, assignment, monitoring
   - Conflict resolution and quality gates

2. **Worker Agents** (`iccc/agents/`):
   - Specialized agents with explicit permissions
   - Template-based configuration (`.claude/agents/*.md`)
   - Dynamic creation via Meta-Agent (AI-powered)

3. **Claude Hooks** (`iccc/hooks/scripts/`):
   - `auto_test.py`: Automatic test triggering
   - `agent_coordinator.py`: Redis file locks, event publishing
   - `safety_check.py`: Pre-execution safety validation

4. **Observability** (`iccc/observability/`):
   - Real-time event collection and AI summarization
   - Intelligent sampling (adapts to agent count)
   - Event batching with priority handling

5. **Planning Systems** (`iccc/planning/`):
   - **HTN Planner**: Hierarchical task decomposition
   - **STRIPS Planner**: State-space planning
   - **Adaptive Planner**: Failure detection & replanning
   - **Templates**: Feature/Bug Fix/Refactoring workflows

6. **REST API** (`iccc/api/`):
   - Litestar (ASGI) framework
   - 18+ endpoints for project/agent/task management
   - OpenAPI documentation
   - Pydantic validation

### Model Selection Strategy

- **Haiku 3.5**: Fast, cheap - simple tasks (file operations, test generation)
- **Sonnet 4**: Balanced - general coding, refactoring, code review
- **Opus 4**: Complex architecture, critical work, meta-reasoning

**Intelligent Selection**: 33 TaskType classifications automatically choose optimal model.

## Technology Stack

| Layer | Technology | Status |
|-------|-----------|--------|
| Language | Python 3.12+ | ✅ Implemented |
| API | Litestar (ASGI) | ✅ Implemented |
| Validation | Pydantic V2 | ✅ Implemented |
| Primary DB | MongoDB | ✅ Implemented |
| Queue/Cache | Redis | ✅ Implemented |
| Events DB | SQLite | ✅ Implemented |
| Testing | pytest + pytest-asyncio | ✅ 200+ tests |
| Type Safety | mypy (strict mode) | ✅ All modules |
| Dashboard | Vue.js + WebSockets | 🚧 Planned |
| Desktop App | Dioxus (Rust) | ❌ Not planned |
| Isolation | Git worktrees + File locks | ✅ Implemented |

## Core Data Models

**Implemented in `iccc/models/entities.py`:**

- **Project**: UUID, name, directory, status, metadata, agents[]
- **Agent**: ID, type, model (ModelTier), specialization, status, worktree_path
- **Task**: UUID, project_id, description, task_type (33 types), status, dependencies, assigned_agent_id
- **Session**: UUID, agent_id, messages[], token_usage, model_used
- **HookEvent**: timestamp, session_id, event_type, data (JSON), agent_id

**Enums:**
- `ModelTier`: HAIKU, SONNET, OPUS
- `TaskType`: 33 classifications (FILE_RENAME → ARCHITECTURE_DESIGN)
- `TaskStatus`: PENDING, IN_PROGRESS, COMPLETED, FAILED, BLOCKED
- `ProjectStatus`: ACTIVE, PAUSED, COMPLETED, ARCHIVED
- `AgentStatus`: IDLE, BUSY, ERROR, STOPPED

## REST API Endpoints

**Implemented in `iccc/api/routes/`:**

### Projects (`/projects`)
- `POST /projects` - Create project
- `GET /projects` - List projects
- `GET /projects/{id}` - Get project
- `PUT /projects/{id}` - Update project
- `DELETE /projects/{id}` - Delete project

### Agents (`/agents`)
- `POST /agents` - Register agent
- `GET /agents` - List agents
- `GET /agents/{id}` - Get agent
- `PUT /agents/{id}` - Update agent status
- `POST /agents/{id}/assign` - Assign task

### Tasks (`/tasks`)
- `POST /tasks` - Create task
- `GET /tasks` - List tasks (with filters)
- `GET /tasks/{id}` - Get task
- `PUT /tasks/{id}` - Update task
- `POST /tasks/{id}/complete` - Mark complete

### Observability (`/observability`)
- `GET /observability/events` - Query events
- `GET /observability/summary` - AI-generated summary
- `WS /observability/ws` - Real-time event stream

## Conflict Prevention

**Git Worktree Isolation** (`iccc/isolation/worktree.py`):
```python
# Each agent gets isolated Git worktree
worktree_path = await worktree_manager.create_worktree(
    project_id=project.id,
    agent_id=agent.id,
    branch=f"agent-{agent.id}"
)
```

**Redis Distributed Locks** (`iccc/locks/file_lock.py` + `iccc/hooks/scripts/agent_coordinator.py`):
```python
# PreToolUse Hook: Acquire lock
if tool_name in ["Write", "Edit", "MultiEdit"]:
    acquired = acquire_file_lock(file_path, agent_id, timeout=30)
    if not acquired:
        return 1  # Block execution

# PostToolUse Hook: Release lock
release_file_lock(file_path, agent_id)
```

**Dependency Analysis**:
- Task scheduler respects file dependencies
- Parallel tasks on different files
- Sequential tasks on same files

## Planning Systems

### HTN (Hierarchical Task Network) - `iccc/planning/htn.py`

Decomposes complex tasks into atomic subtasks:

```python
from iccc.planning.htn import HTNPlanner, Method, CompoundTask

method = Method(
    name="implement_feature",
    task_type="feature",
    subtasks=["design", "code", "test", "review"],
    preconditions={"has_spec": True},
    effects={"feature_complete": True}
)

planner = HTNPlanner(methods=[method])
plan = planner.decompose(task, state)
```

### STRIPS - `iccc/planning/strips.py`

State-space planning with preconditions/effects:

```python
from iccc.planning.strips import STRIPSPlanner, Action

action = Action(
    name="run_tests",
    preconditions={"code_complete": True},
    effects={"tests_passed": True}
)

planner = STRIPSPlanner()
plan = planner.plan(initial_state, goal_state, [action])
```

### Adaptive Replanning - `iccc/planning/adaptive.py`

AI-powered failure recovery:

```python
from iccc.planning.adaptive import AdaptivePlanner, FailurePattern

# Detect failure pattern
pattern = await planner.analyze_failure(task, error, context)
# Patterns: QUALITY_GATE_FAILED, TIMEOUT, MODEL_OVERLOAD,
#           DEPENDENCY_CONFLICT, REPEATED_FAILURE, UNKNOWN

# Generate recovery strategy
strategy = await planner.generate_replan_strategy(failure)
# Actions: upgrade_model, redecompose_parallel, downgrade_model,
#          reorder_dependencies, change_approach

# Execute replan
new_tasks = await planner.replan_task(original_task, strategy)
```

### Workflow Templates - `iccc/planning/templates/`

Standardized development workflows:

**Feature Development** (7 atomic tasks):
1. research_and_design
2. update_data_models (if needs_db)
3. write_failing_tests (if use_tdd)
4. implement_core_logic
5. implement_api_endpoints (if needs_api)
6. run_tests_and_fix
7. code_review_and_docs

**Bug Fix** (5 atomic tasks):
1. reproduce_bug
2. root_cause_analysis (if not known)
3. write_failing_test
4. implement_fix
5. verify_fix_and_test

**Refactoring** (5 atomic tasks):
1. ensure_test_coverage
2. identify_and_plan
3. apply_refactoring (incremental, atomic commits)
4. continuous_testing
5. final_verification

## Agent Templates

**Located in `iccc/agents/templates/`:**

### 1. Code Reviewer (`code_reviewer.md`)
- **Specialization**: Code review, quality assurance
- **Model**: Sonnet 4
- **Permissions**: Read-only
- **Checklist**: Style, functionality, security, performance, testing

### 2. Frontend Expert (`frontend_expert.md`)
- **Specialization**: React, Vue, TypeScript
- **Model**: Sonnet 4
- **Features**: Component architecture, accessibility, performance
- **Quality Gates**: typecheck, tests, Lighthouse ≥90

### 3. Backend Expert (`backend_expert.md`)
- **Specialization**: API design, databases, architecture
- **Model**: Sonnet 4
- **Features**: REST/GraphQL, migrations, authentication
- **Quality Gates**: mypy, pytest, security scans, response time <200ms

### 4. Test Expert (`test_expert.md`)
- **Specialization**: TDD, QA, coverage
- **Model**: Haiku 3.5 (cost-optimized)
- **Features**: Testing pyramid (Unit 70%, Integration 20%, E2E 10%)
- **Quality Gates**: Coverage ≥90%, test suite <30s

### Creating Custom Agents

```python
from iccc.agents.meta_agent import generate_agent

# AI generates custom agent configuration
path = await generate_agent(
    name="api-documenter",
    specialization="Generate OpenAPI docs from code",
    complexity="simple"  # Haiku recommended
)
# Creates: .claude/agents/api-documenter.md
```

## Hooks System

**Auto-Test Hook** (`iccc/hooks/scripts/auto_test.py`):
- Triggers on PostToolUse for Write/Edit tools
- TypeScript → `npm run typecheck`
- Python → `mypy <file>`
- Test files → `pytest <file>` or `npm test`

**Agent Coordinator** (`iccc/hooks/scripts/agent_coordinator.py`):
- **PreToolUse**: Acquire Redis lock (blocks if unavailable)
- **PostToolUse**: Release lock
- **SubagentStop**: Publish completion event to Redis pub/sub

**Safety Check** (`iccc/hooks/scripts/safety_check.py`):
- Validates tool parameters
- Blocks dangerous operations
- Enforces file access permissions

## Testing

**Test Statistics:**
- **Total Tests**: 200+
- **Pass Rate**: 100%
- **Coverage Goals**: 90%+ for production code

**Test Structure:**
```
tests/
├── agents/              # 26 tests (94% coverage)
├── api/                 # 20+ tests (integration)
├── hooks/               # 18 tests
├── observability/       # 88 tests
├── planning/
│   ├── templates/       # 32 tests (96-100%)
│   └── adaptive/        # 22 tests (59%)
└── ...
```

**Running Tests:**
```bash
# All tests
python -m pytest tests/ -v

# Specific module
python -m pytest tests/agents/ -v

# With coverage
python -m pytest tests/ --cov=iccc --cov-report=html
```

## Development Workflow

### Adding New Features

1. **Plan**: Use planning templates or create HTN method
2. **Implement**: Follow type safety (mypy strict)
3. **Test**: Write tests first (TDD) or alongside code
4. **Review**: Run code-reviewer agent template
5. **Document**: Update relevant docs

### Code Style

- **Type Hints**: Python 3.12+ syntax (required)
- **Async**: Use `async/await` for I/O operations
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Imports**: Absolute imports (`from iccc.models import ...`)

### Commit Messages

Follow Conventional Commits:
```
feat(agents): Add Meta-Agent AI configuration generator
fix(hooks): Resolve Redis connection timeout in coordinator
test(planning): Add comprehensive adaptive planner tests
docs(readme): Update quick start guide
```

## Documentation Structure

- `README.md` - Project overview, quick start, features
- `CLAUDE.md` - This file (AI assistant guidance)
- `docs/QUICK_START.md` - Detailed getting started guide
- `docs/API.md` - REST API reference
- `docs/ARCHITECTURE.md` - System design deep dive
- `development_document.md` - Complete technical specification

## Key Files to Know

**Core Modules:**
- `iccc/orchestrator.py` - Main orchestration logic
- `iccc/models/entities.py` - Data model definitions
- `iccc/config.py` - Configuration management
- `iccc/api/app.py` - REST API application factory

**Important Scripts:**
- `iccc/hooks/scripts/auto_test.py` - Auto-test trigger
- `iccc/hooks/scripts/agent_coordinator.py` - Multi-agent coordination
- `iccc/agents/meta_agent.py` - AI agent generator

**Testing:**
- `tests/` - All test files (200+ tests)
- `pyproject.toml` - pytest configuration

## Environment Variables

Required for production:
```bash
ANTHROPIC_API_KEY=sk-ant-...        # Claude API key
MONGODB_URL=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
```

Optional:
```bash
LOG_LEVEL=INFO                      # DEBUG, INFO, WARNING, ERROR
AGENT_ID=agent-123                  # For multi-agent setups
ICCC_PROJECT_ROOT=/path/to/project
```

## Status & Roadmap

✅ **Completed:**
- Multi-agent orchestration system
- REST API (18+ endpoints)
- Hooks automation (auto-test, file locks)
- Agent template system (4 presets + Meta-Agent)
- Adaptive replanning (6 failure patterns)
- Workflow templates (Feature/Bug/Refactor)
- 200+ tests with 100% pass rate

🚧 **In Progress:**
- WebSocket real-time dashboard
- CLI command-line tool

📝 **Planned:**
- Complete documentation site
- Production deployment guides
- Performance optimization guides

**Not Planned:**
- Desktop application (Dioxus/Rust)
- Docker deployment configurations

---

**Project Status**: ✅ Core functionality development complete
