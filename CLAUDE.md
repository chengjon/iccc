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

**Current State:** ✅ **Production Ready** - All technical debt eliminated, enterprise-grade security, observability, and reliability features implemented (960+ tests, 95% pass rate).

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

1. **Worktree Manager** (`iccc/coordination/worktree_manager.py`):
   - Git Worktree 自动化管理
   - 任务分配与进度追踪
   - 多 CLI 协作的 README 模板生成
   - 进度报告自动生成
   - 分支合并与 Worktree 清理
   - Redis 事件发布集成

2. **Master Orchestrator** (`iccc/orchestrator.py`):
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
   - MongoDB event storage with 30-day retention
   - WebSocket streaming for live updates
   - Prometheus metrics collection (50+ metrics)
   - Intelligent sampling (adapts to agent count)
   - Event batching with priority handling

5. **Planning Systems** (`iccc/planning/`):
   - **HTN Planner**: Hierarchical task decomposition
   - **STRIPS Planner**: State-space planning
   - **Adaptive Planner**: Failure detection & replanning
   - **Templates**: Feature/Bug Fix/Refactoring workflows

6. **REST API** (`iccc/api/`):
   - Litestar (ASGI) framework
   - 22+ endpoints for project/agent/task/quality management
   - 5-layer middleware stack (Request ID → Logging → Performance → Rate Limit → Auth)
   - API key authentication with Redis rate limiting
   - OpenAPI documentation with Pydantic V2 validation
   - Quality gate endpoints for CI/CD integration
   - Prometheus metrics endpoint

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
- `GET /observability/events` - Query events with filtering
- `GET /observability/summary` - AI-generated summary
- `WS /observability/ws` - Real-time event stream

### Quality Gates (`/quality`)
- `POST /quality/check` - Run quality gates for a project
- `GET /quality/check/{id}` - Get quality check results
- `GET /quality/checks` - List all quality checks
- `GET /quality/gates` - Get available quality gates

### Metrics (`/metrics`)
- `GET /metrics` - Prometheus metrics endpoint
- `GET /metrics/health` - Metrics system health check

### Worktree (`iccc/coordination/worktree_manager.py`)

**任务管理**:
```python
from iccc.coordination.worktree_manager import WorktreeManager, TaskInfo

manager = WorktreeManager("/path/to/project")

task = TaskInfo(
    task_id="feature-auth-001",
    description="实现用户认证系统",
    acceptance_criteria=["实现登录功能", "实现注册功能"],
    priority="high",
    estimated_hours=8
)
worktree_path = await manager.create_worktree_with_task("auth-worker", task)
```

**进度追踪**:
```python
await manager.update_task_progress("auth-worker", progress=50, status="running")
report = await manager.generate_progress_report()
```

**合并与清理**:
```python
results = await manager.merge_all_branches_to_main()
await manager.cleanup_all_worktrees()
```

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
- **Total Tests**: 980+
- **Pass Rate**: 95%+
- **Coverage**: 40%+ overall
- **Coverage Goals**: 90%+ for production code

**Test Structure:**
```
tests/
├── coordination/        # Worktree 管理测试 (12 tests)
├── agents/              # 26 tests (94% coverage)
├── api/                 # 80+ tests (integration)
│   ├── test_auth.py             # 42 tests (API authentication)
│   ├── test_rate_limiter.py     # 21 tests (rate limiting)
│   ├── test_quality_routes.py   # 13 tests (quality gates)
│   ├── test_metrics_routes.py   # 16 tests (Prometheus)
│   └── test_middleware_integration.py # 21 tests
├── hooks/               # 18 tests
├── observability/       # 104 tests
│   ├── test_storage.py          # 16 tests (event storage)
│   └── test_collector.py        # 35 tests (event collection)
├── db/                  # 7 tests (migration CLI)
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
- `IFLOW.md` - iFlow CLI 上下文和用户偏好
- `docs/QUICK_START.md` - Detailed getting started guide
- `docs/API.md` - REST API reference
- `docs/MULTI_CLI_WORKTREE_MANAGEMENT.md` - Git Worktree 多 CLI 协作管理指南
- `docs/ARCHITECTURE.md` - System design deep dive
- `development_document.md` - Complete technical specification

## Key Files to Know

**Core Modules:**
- `iccc/orchestrator.py` - Main orchestration logic
- `iccc/coordination/worktree_manager.py` - Git Worktree 多 CLI 协作管理
- `iccc/models/entities.py` - Data model definitions
- `iccc/config.py` - Configuration management
- `iccc/api/app.py` - REST API application factory

**Important Scripts:**
- `iccc/hooks/scripts/auto_test.py` - Auto-test trigger
- `iccc/hooks/scripts/agent_coordinator.py` - Multi-agent coordination
- `iccc/agents/meta_agent.py` - AI agent generator
- `bin/create_worktrees.sh` - Worktree 批量创建
- `bin/monitor_worktrees.sh` - Worktree 状态监控
- `bin/merge_and_cleanup.sh` - 分支合并与清理

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

Security & Performance:
```bash
ICCC_API_KEYS=key1,key2,key3        # API keys for authentication
ICCC_RATE_LIMIT_REQUESTS=1000       # Rate limit requests per window
ICCC_RATE_LIMIT_WINDOW=60           # Rate limit window in seconds
ICCC_ENABLE_METRICS=true            # Enable Prometheus metrics
```

Optional:
```bash
LOG_LEVEL=INFO                      # DEBUG, INFO, WARNING, ERROR
AGENT_ID=agent-123                  # For multi-agent setups
ICCC_PROJECT_ROOT=/path/to/project
ICCC_LOG_SLOW_REQUESTS=true         # Enable slow request logging
ICCC_SLOW_REQUEST_THRESHOLD_MS=1000 # Slow request threshold
ICCC_EVENTS_RETENTION_DAYS=30       # Event retention period
```

## Status & Roadmap

✅ **Completed:**
- Multi-agent orchestration system
- REST API (22+ endpoints) with full middleware stack
- Production-grade security (API auth + rate limiting)
- Complete observability (events + metrics + tracing)
- Quality gates with CI/CD integration
- Database migration CLI (5 commands)
- Hooks automation (auto-test, file locks)
- Agent template system (4 presets + Meta-Agent)
- Adaptive replanning (6 failure patterns)
- Workflow templates (Feature/Bug/Refactor)
- Git Worktree 多 CLI 协作管理 (完整实现)
- 980+ tests with 95% pass rate
- Technical debt elimination (8/8 tasks)

🚧 **In Progress:**
- WebSocket real-time dashboard (UI layer only)
- Production deployment documentation

📝 **Planned:**
- Grafana dashboard templates
- Performance optimization guides
- Advanced alerting rules

**Not Planned:**
- Desktop application (Dioxus/Rust)
- Docker deployment configurations

---

**Project Status**: ✅ **PRODUCTION READY** - Deploy immediately
