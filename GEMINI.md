# Gemini Context: iCCC (i-Claude Code CLI)

## Project Overview
iCCC is an intelligent multi-CLI collaboration platform designed to orchestrate multiple AI agents (such as Claude, iflow, and Gemini) to work in parallel on a single codebase. It employs a Master-Worker architecture, utilizing Git Worktree for workspace isolation and Redis for real-time coordination and locking.

## Key Architecture
- **Orchestrator (Brain)**: Utilizes Hierarchical Task Network (HTN) and STRIPS planners to decompose high-level user goals into atomic, executable tasks.
- **Communication Bus**: Redis Streams serves as the backbone for event propagation, task queues, and inter-agent messaging.
- **Isolation Strategy**: Each active agent operates within a dedicated Git Worktree to prevent file conflicts. Concurrent file access is managed via a Redis-based distributed file locking mechanism.
- **Data Persistence**:
  - **MongoDB**: Stores persistent state for Projects, Tasks, and Agents.
  - **SQLite**: Logs high-volume event streams.
  - **Redis**: Handles transient state, task queues, and distributed locks.
- **Interfaces**:
  - **CLI**: The `iccc` command-line tool for direct interaction.
  - **API**: A REST API built with Litestar for external integration and dashboard support.

## Environment Setup

### Prerequisites
- Python 3.12+
- Docker (required for Redis and MongoDB services)
- `uv` (recommended package manager) or `pip`

### Installation
```bash
# Install dependencies using uv (recommended)
uv pip install -e ".[dev]"

# Or using standard pip
pip install -e ".[dev]"
```

### Infrastructure Services
Start the required backing services using Docker:
```bash
# Start MongoDB
docker run -d --name iccc-mongodb -p 27017:27017 mongo:6

# Start Redis
docker run -d --name iccc-redis -p 6379:6379 redis:7
```

### Configuration
Create a `.env` file in the project root with the following keys:
```ini
ANTHROPIC_API_KEY=your_api_key_here
MONGODB_URL=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
```

## Development & Usage

### Core Commands
- **Run API Server**:
  ```bash
  python -m iccc.api.app
  # API Docs available at http://localhost:8000/docs
  ```
- **Run Test Suite**:
  ```bash
  python -m pytest tests/ -v
  ```
- **Static Analysis**:
  ```bash
  mypy iccc/ --ignore-missing-imports
  ruff check .
  ```

### CLI Interaction Examples
- **Initiate Workflow**:
  ```bash
  /iccc/workflow "Implement user login feature"
  ```
- **Planning & Reasoning**:
  ```bash
  /iccc/plan "Design microservices architecture"
  ```
- **Check Templates**:
  ```bash
  python -c "from iccc.agents.subagent import SubagentLoader; print(SubagentLoader.list_templates())"
  ```

## Directory Structure
- `iccc/`: Main application source code.
  - `agents/`: Agent definitions, lifecycle, and sub-agent management.
  - `api/`: REST API implementation (Litestar).
  - `brain/`: Intelligence core (Prompts, HTN/STRIPS planners).
  - `coordination/`: Logic for Git Worktree management and conflict avoidance.
  - `hooks/`: System hooks for automation (Pre/Post tool execution).
  - `queue/`: Redis-backed task queue implementation.
- `tests/`: Comprehensive pytest suite (Unit and Integration).
- `.claude/`: Configuration specific to Claude Code agents (hooks, permissions).
- `.iccc/`: Runtime storage for logs, plans, and state.
- `openspec/`: Authoritative architectural specifications.

## Development Guidelines
- **Code Style**: Strictly adhere to `ruff` and `mypy` strict mode standards.
- **Architectural Integrity**:
  - Always use `FileLockManager` for file I/O to ensure safety across agents.
  - Respect the Git Worktree isolation; do not assume a single working directory.
- **Testing**: New features must include comprehensive tests. The project maintains high test coverage (~95%).
- **Specifications**: Refer to `@/openspec/AGENTS.md` before proposing or implementing significant architectural changes.
