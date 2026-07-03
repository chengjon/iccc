# Quick Start Guide

This guide will help you get iCCC (i-Claude Code CLI) up and running in under 10 minutes. iCCC is a **production-ready** multi-agent orchestration system with enterprise-grade security, observability, and reliability features.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.12+** installed
- **MongoDB 6.0+** running locally or remotely
- **Redis 7.0+** running locally or remotely
- **Git** installed
- **Claude Code CLI** installed (or other supported AI CLIs)

### System Requirements

- OS: Linux, macOS, or Windows with WSL2
- RAM: 4GB minimum, 8GB recommended
- Disk: 2GB free space

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/iccc.git
cd iccc
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- Core dependencies (Litestar, Pydantic, Motor, Redis, etc.)
- Production dependencies (prometheus-client, redis[hiredis])
- Development tools (pytest, mypy, ruff, black)
- Optional packages (Anthropic SDK for AI features)

### 4. Verify Installation

```bash
python -c "import iccc; print(iccc.__version__)"
```

## Service Setup

### MongoDB Setup

#### Option 1: Local MongoDB (Recommended for Development)

**macOS (Homebrew):**
```bash
brew tap mongodb/brew
brew install mongodb-community@6.0
brew services start mongodb-community@6.0
```

**Ubuntu/Debian:**
```bash
sudo apt-get install -y mongodb-org
sudo systemctl start mongod
sudo systemctl enable mongod
```

**Windows:**
Download and install from [MongoDB Download Center](https://www.mongodb.com/try/download/community).

#### Option 2: MongoDB Atlas (Cloud)

1. Create free account at [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create a cluster
3. Get connection string (looks like `mongodb+srv://...`)
4. Whitelist your IP address

#### Verify MongoDB is Running

```bash
# Local MongoDB
mongosh --eval "db.version()"

# MongoDB Atlas
mongosh "your-connection-string" --eval "db.version()"
```

### Redis Setup

#### Option 1: Local Redis

**macOS (Homebrew):**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**Windows:**
Use WSL2 or download from [Redis for Windows](https://github.com/microsoftarchive/redis/releases).

#### Option 2: Redis Cloud

1. Create free account at [Redis Cloud](https://redis.com/try-free/)
2. Create database
3. Get connection details (host, port, password)

#### Verify Redis is Running

```bash
redis-cli ping
# Should return: PONG
```

## Configuration

### 1. Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# MongoDB Configuration
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=iccc_db

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=true

# API Authentication (Required for production)
ICCC_API_KEYS=dev-key-12345,prod-key-67890  # Comma-separated API keys

# Rate Limiting
ICCC_RATE_LIMIT_REQUESTS=1000       # Requests per window
ICCC_RATE_LIMIT_WINDOW=60           # Window in seconds

# Performance & Observability
ICCC_ENABLE_METRICS=true            # Enable Prometheus metrics
ICCC_LOG_SLOW_REQUESTS=true         # Enable slow request logging
ICCC_SLOW_REQUEST_THRESHOLD_MS=1000 # Slow request threshold (ms)

# AI Models (Optional - for Meta-Agent features)
ANTHROPIC_API_KEY=sk-ant-...  # Get from https://console.anthropic.com/

# Agent Configuration
DEFAULT_MODEL_TIER=sonnet
MAX_PARALLEL_AGENTS=5

# File Lock Configuration
FILE_LOCK_TIMEOUT=300  # seconds
FILE_LOCK_RETRY_DELAY=1  # seconds

# Logging & Retention
LOG_LEVEL=INFO
LOG_FILE=logs/iccc.log
ICCC_EVENTS_RETENTION_DAYS=30       # Event retention period
```

### 2. Initialize Database

```bash
# Run database migrations
iccc migrate status
iccc migrate up

# Verify collections were created
mongosh iccc_db --eval "db.getCollectionNames()"
```

Expected output:
```
[ 'projects', 'agents', 'tasks', 'events', 'sessions', 'quality_checks', 'hook_events', 'migration_state' ]
```

### 3. Verify Configuration

```bash
# Run configuration check
python -m iccc.utils.check_config

# Expected output:
# ✓ MongoDB connection: OK
# ✓ Redis connection: OK
# ✓ Environment variables: OK
# ✓ Claude Code CLI: Found
```

## Running Tests

### Run All Tests

```bash
pytest
```

Expected output:
```
======================== test session starts =========================
collected 960+ items

tests/agents/test_meta_agent.py ................            [  3%]
tests/agents/test_subagent.py ......................        [  8%]
tests/agents/test_templates.py ....................         [ 12%]
tests/api/test_agents.py .................                  [ 15%]
tests/api/test_projects.py .................                [ 18%]
tests/api/test_tasks.py .................                   [ 21%]
tests/api/test_auth.py ....................................   [ 26%]
tests/api/test_rate_limiter.py .....................       [ 29%]
tests/api/test_quality_routes.py ............              [ 31%]
tests/api/test_metrics_routes.py .........................  [ 34%]
tests/api/test_middleware_integration.py .................  [ 37%]
tests/hooks/scripts/test_auto_test.py ..........            [ 40%]
tests/hooks/scripts/test_agent_coordinator.py ........      [ 43%]
tests/observability/test_collector.py ........................ [ 47%]
tests/observability/test_storage.py ......................  [ 49%]
tests/db/test_migration_cli.py ...........................   [ 52%]
tests/planning/test_adaptive.py ......................      [ 65%]
tests/planning/test_htn.py ................                 [ 70%]
tests/planning/test_strips.py ................              [ 75%]
tests/utils/test_file_locks.py ..........                   [ 80%]
tests/utils/test_summarizer.py ............                 [ 85%]
...

======================== 950+ passed, 10 skipped in 25.67s =======================
```

### Run Specific Test Suites

```bash
# Test API endpoints
pytest tests/api/

# Test planning systems
pytest tests/planning/

# Test hooks
pytest tests/hooks/

# Test with coverage report
pytest --cov=iccc --cov-report=html
open htmlcov/index.html
```

## Starting the API Server

### Development Mode

```bash
# Start the API server with auto-reload
litestar run --reload

# Or using uvicorn directly
uvicorn iccc.api.app:app --reload --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Production Mode

```bash
# Start with production settings (authentication and rate limiting enabled)
export ICCC_ENABLE_METRICS=true
export ICCC_API_KEYS=prod-key-12345
export ICCC_RATE_LIMIT_REQUESTS=1000

litestar run --host 0.0.0.0 --port 8000 --workers 4
```

## Production Deployment

### 1. Environment Setup

```bash
# Production environment variables
export ANTHROPIC_API_KEY=sk-ant-...
export MONGODB_URL=mongodb://prod-mongo:27017
export REDIS_URL=redis://prod-redis:6379
export ICCC_API_KEYS=prod-key-1,prod-key-2,prod-key-3
export ICCC_RATE_LIMIT_REQUESTS=5000
export ICCC_ENABLE_METRICS=true
export LOG_LEVEL=WARNING
```

### 2. Database Migrations

```bash
# Check migration status
iccc migrate status --mongodb-url $MONGODB_URL

# Run pending migrations
iccc migrate up --mongodb-url $MONGODB_URL
```

### 3. Health Checks

```bash
# Verify all systems operational
curl http://localhost:8000/health
# Expected: {"status":"healthy",...}

# Check metrics system
curl http://localhost:8000/metrics/health
# Expected: {"status":"healthy", "metrics_enabled": true}
```

### 4. Monitoring Setup

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'iccc'
    static_configs:
      - targets: ['iccc-prod:8000']
    metrics_path: '/metrics'
    scrape_interval: 5s
```

### 5. Key Production Metrics

Monitor these metrics in your dashboard:

- **Request Rate**: `rate(iccc_http_requests_total[5m])`
- **Error Rate**: `rate(iccc_http_requests_total{status=~"5.."}[5m])`
- **Latency**: `histogram_quantile(0.95, iccc_http_request_duration_seconds_bucket)`
- **Active Agents**: `iccc_active_agents{status="busy"}`
- **Task Completion**: `rate(iccc_tasks_total{status="completed"}[5m])`
- **Quality Gates**: `iccc_quality_gates_total{status="failed"}`

### Verify API is Running

```bash
# Health check (no authentication required)
curl http://localhost:8000/health

# Expected response:
# {"status":"healthy","timestamp":"2025-12-08T..."}

# Protected endpoint (requires API key)
curl -H "X-API-Key: prod-key-12345" http://localhost:8000/api/v1/projects

# Check rate limiting headers
curl -I http://localhost:8000/api/v1/projects
# X-RateLimit-Limit: 1000
# X-RateLimit-Remaining: 999
# X-RateLimit-Reset: 1701234567

# Prometheus metrics (if enabled)
curl http://localhost:8000/metrics

# API docs
open http://localhost:8000/docs
```

## First Steps

### 1. Create Your First Project

```bash
# Using curl (requires API key in production)
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "X-API-Key: prod-key-12345" \
  -d '{
    "name": "My First Project",
    "directory": "/path/to/project",
    "metadata": {
      "description": "Learning iCCC basics",
      "tech_stack": ["Python", "FastAPI"]
    }
  }'
```

Response:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "My First Project",
  "directory": "/path/to/project",
  "status": "active",
  "created_at": "2025-12-07T10:30:00Z"
}
```

Save the `id` - you'll need it for the next steps.

### 2. Register Your First Agent

```bash
PROJECT_ID="123e4567-e89b-12d3-a456-426614174000"

curl -X POST http://localhost:8000/api/v1/agents \
  -H "Content-Type: application/json" \
  -H "X-API-Key: prod-key-12345" \
  -d '{
    "type": "code-reviewer",
    "specialization": "Python code quality and security",
    "model": "sonnet",
    "status": "idle",
    "worktree_path": "/tmp/iccc-worktrees/agent-1",
    "metadata": {
      "permissions": {
        "read": ["**/*.py"],
        "write": []
      }
    }
  }'
```

Response:
```json
{
  "id": "agent-001",
  "type": "code-reviewer",
  "specialization": "Python code quality and security",
  "model": "sonnet",
  "status": "idle",
  "created_at": "2025-12-07T10:31:00Z"
}
```

### 3. Create Your First Task

```bash
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: prod-key-12345" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "description": "Review all Python files for security issues",
    "task_type": "code_review",
    "assigned_agent_id": "agent-001",
    "metadata": {
      "focus_areas": ["security", "error_handling"],
      "severity_threshold": "medium"
    }
  }'
```

Response:
```json
{
  "id": "task-001",
  "project_id": "123e4567-e89b-12d3-a456-426614174000",
  "description": "Review all Python files for security issues",
  "task_type": "code_review",
  "status": "pending",
  "assigned_agent_id": "agent-001",
  "created_at": "2025-12-07T10:32:00Z"
}
```

### 4. Start Task Execution

```bash
# Update task status to running
curl -X PATCH http://localhost:8000/api/v1/tasks/task-001 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: prod-key-12345" \
  -d '{
    "status": "running"
  }'

# Monitor task progress
curl -H "X-API-Key: prod-key-12345" http://localhost:8000/api/v1/tasks/task-001

# View agent activity
curl -H "X-API-Key: prod-key-12345" http://localhost:8000/api/v1/agents/agent-001

# View project status
curl -H "X-API-Key: prod-key-12345" http://localhost:8000/api/v1/projects/$PROJECT_ID
```

## New: Quality Gates & Observability

### Run Quality Gates

```bash
# Trigger quality gate checks for a project
curl -X POST http://localhost:8000/api/v1/quality/check \
  -H "Content-Type: application/json" \
  -H "X-API-Key: prod-key-12345" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "task_id": "task-001"
  }'

# Check quality gate results
curl -H "X-API-Key: prod-key-12345" \
  http://localhost:8000/api/v1/quality/check/{check_id}
```

### Monitor with Observability

```bash
# Query recent events
curl -H "X-API-Key: prod-key-12345" \
  "http://localhost:8000/api/v1/observability/events?limit=10"

# Get AI-generated summary
curl -H "X-API-Key: prod-key-12345" \
  http://localhost:8000/api/v1/observability/summary

# Real-time WebSocket stream (for dashboards)
wscat -c ws://localhost:8000/api/v1/observability/ws
```

### Prometheus Metrics

```bash
# View all metrics (Prometheus format)
curl http://localhost:8000/metrics

# Key metrics to monitor:
# - iccc_http_requests_total: Request count by method/route/status
# - iccc_http_request_duration_seconds: Request latency
# - iccc_active_agents: Number of agents by status
# - iccc_tasks_total: Task count by status
# - iccc_quality_gates_total: Quality gate results
```

## Using Agent Templates

### List Available Templates

```python
from iccc.agents.subagent import SubagentLoader

loader = SubagentLoader()
templates = loader.list_templates()
print(templates)
# ['code-reviewer', 'frontend-expert', 'backend-expert', 'test-expert']
```

### Create Agent from Template

```python
import asyncio
from pathlib import Path
from iccc.agents.subagent import SubagentLoader

async def create_agent():
    config_path = await SubagentLoader.create_from_template(
        name="security-auditor",
        specialization="security and vulnerability assessment",
        template="code-reviewer",  # Base template
        complexity="complex",  # Use Opus model
        output_dir=Path("configs/agents")
    )
    print(f"Agent config created at: {config_path}")

asyncio.run(create_agent())
```

### Use Meta-Agent for Custom Agents

```python
from iccc.agents.meta_agent import MetaAgent

async def create_custom_agent():
    meta = MetaAgent()

    config = await meta.generate_agent_config(
        name="api-designer",
        specialization="RESTful API design and OpenAPI documentation",
        complexity="moderate",
        custom_requirements="""
        - Must follow OpenAPI 3.1 specification
        - Expertise in FastAPI and Pydantic
        - Focus on API versioning and backward compatibility
        - Include security best practices (OAuth2, rate limiting)
        """
    )

    print(config)

asyncio.run(create_custom_agent())
```

## Using Workflow Templates

### Feature Development Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows/feature-development \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "feature_description": "Add user authentication with JWT tokens",
    "tech_stack": ["FastAPI", "SQLAlchemy", "Redis"],
    "quality_requirements": {
      "test_coverage": 90,
      "security_scan": true,
      "code_review": true
    }
  }'
```

This automatically creates:
1. Planning task (Opus)
2. Backend implementation task (Sonnet)
3. Test writing task (Haiku)
4. Security review task (Sonnet)
5. Documentation task (Haiku)

### Bug Fix Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows/bug-fix \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "'$PROJECT_ID'",
    "bug_description": "API returns 500 error when user email contains special characters",
    "severity": "high",
    "affected_files": ["iccc/api/users.py", "iccc/models/user.py"]
  }'
```

## Adaptive Replanning Example

When tasks fail, iCCC automatically analyzes the failure and adjusts the plan:

```python
from iccc.planning.adaptive import AdaptivePlanner, FailurePattern
from iccc.models.entities import Task, TaskType, ModelTier

async def handle_failure():
    planner = AdaptivePlanner(strips_planner, htn_planner)

    # Simulate a task failure
    task = Task(
        description="Implement user registration API",
        task_type=TaskType.API_IMPLEMENTATION,
        project_id=project_id
    )

    error = Exception("Quality gate failed: test coverage only 65%, required 90%")

    # Analyze failure
    pattern = await planner.analyze_failure(task, error, {})
    print(f"Failure pattern: {pattern}")  # FailurePattern.QUALITY_GATE_FAILED

    # Generate recovery strategy
    failure = TaskFailure(
        task_id=task.id,
        task_type=task.task_type,
        model_used=ModelTier.HAIKU,
        failure_pattern=pattern,
        error_message=str(error),
        attempt_number=1,
        context={}
    )

    strategy = await planner.generate_replan_strategy(failure)
    print(f"Strategy: {strategy.action}")  # "upgrade_model"
    print(f"New model: {strategy.new_model}")  # ModelTier.SONNET

    # Execute replanning
    new_tasks = await planner.replan_task(task, strategy)
    for new_task in new_tasks:
        print(f"New task: {new_task.description}")
```

## Using Hooks for Automation

### Auto-Test Hook

Automatically runs tests when Python/TypeScript files are modified:

```python
# In your Claude Code .claude/hooks/post-tool-use.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from iccc.hooks.scripts.auto_test import main

if __name__ == "__main__":
    main()
```

### Agent Coordinator Hook

Manages file locks and prevents conflicts:

```python
# In your Claude Code .claude/hooks/pre-tool-use.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from iccc.hooks.scripts.agent_coordinator import main

if __name__ == "__main__":
    main()
```

## Troubleshooting

### MongoDB Connection Issues

**Problem:** `pymongo.errors.ServerSelectionTimeoutError`

**Solution:**
```bash
# Check MongoDB is running
systemctl status mongod  # Linux
brew services list | grep mongodb  # macOS

# Check connection string
mongosh "$MONGODB_URL"

# Verify network access (if using Atlas)
# Whitelist your IP in Atlas dashboard
```

### Redis Connection Issues

**Problem:** `redis.exceptions.ConnectionError`

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Check Redis password (if configured)
redis-cli -a your-password ping

# Update .env with correct credentials
REDIS_URL=redis://:password@localhost:6379/0
```

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'iccc'`

**Solution:**
```bash
# Reinstall in editable mode
pip install -e .

# Verify installation
python -c "import iccc; print(iccc.__file__)"
```

### API Server Won't Start

**Problem:** `OSError: [Errno 48] Address already in use`

**Solution:**
```bash
# Find and kill process using port 8000
lsof -ti:8000 | xargs kill -9

# Or use a different port
litestar run --port 8001
```

### Tests Failing

**Problem:** Tests fail with database errors

**Solution:**
```bash
# Ensure MongoDB and Redis are running
systemctl status mongod redis-server

# Clear test database
mongosh iccc_test --eval "db.dropDatabase()"

# Run tests with fresh database
pytest --create-db
```

## Database Migration CLI

iCCC includes a comprehensive migration system for database schema management:

```bash
# List all migrations
iccc migrate list

# Check migration status
iccc migrate status

# Run pending migrations
iccc migrate up

# Create new migration
iccc migrate create add_user_preferences --description "Add user preferences collection"

# Rollback last migration
iccc migrate down

# Dry run (show what would be applied)
iccc migrate up --dry-run
```

## Next Steps

Now that you have iCCC running, explore these topics:

1. **Production Deployment**: Complete production setup with monitoring
   - Read: `docs/technical_debt_completion_report.md`

2. **Multi-Agent Orchestration**: Learn how to coordinate multiple AI agents working in parallel
   - Read: `docs/MULTI_AGENT_GUIDE.md`

3. **Planning Systems**: Understand HTN, STRIPS, and adaptive replanning
   - Read: `docs/PLANNING.md`

4. **Observability**: Master monitoring with events and metrics
   - Read: `docs/prometheus_metrics.md`

5. **Git Worktrees**: Master agent isolation with Git worktrees
   - Read: `docs/WORKTREES.md`

6. **Claude Hooks**: Build custom automation with hooks
   - Read: `docs/HOOKS.md`

7. **REST API**: Integrate iCCC into your applications
   - Explore: `http://localhost:8000/docs`

8. **Advanced Configuration**: Customize model selection, rate limits, and quality gates
   - Read: `docs/CONFIGURATION.md`

## Getting Help

- **Documentation**: Browse `docs/` directory
- **API Reference**: http://localhost:8000/docs
- **Prometheus Metrics**: http://localhost:8000/metrics
- **GitHub Issues**: Report bugs and request features
- **Examples**: Check `examples/` directory for complete use cases

## Production Checklist

Before deploying to production, ensure:

- [ ] MongoDB and Redis are clustered for high availability
- [ ] API keys are configured and secure
- [ ] Rate limiting is enabled with appropriate limits
- [ ] Prometheus metrics are being collected
- [ ] Health checks are configured
- [ ] Log aggregation is set up
- [ ] Database migrations have been run
- [ ] Quality gates are configured for your standards
- [ ] Circuit breakers are configured for external services
- [ ] Monitoring dashboards are created

## Security Best Practices

- Rotate API keys regularly
- Use HTTPS in production
- Implement network segmentation
- Enable audit logging
- Monitor authentication failures
- Set up alerts for unusual activity
- Use Redis AUTH for Redis connections
- Enable MongoDB authentication and encryption

## Common Use Cases

### Parallel Feature Development

```bash
# Create 3 agents for parallel work
# Agent 1: Frontend (React components)
# Agent 2: Backend (API endpoints)
# Agent 3: Tests (unit + integration tests)

# Each agent works in isolated Git worktree
# Redis locks prevent file conflicts
# Master agent coordinates dependencies
```

### Large Codebase Refactoring

```bash
# Use Opus for planning
# Break into 10+ parallel subtasks
# Each subtask handled by Sonnet agent
# Adaptive replanning handles failures
# Final review by code-reviewer agent
```

### Comprehensive Testing

```bash
# Test-expert agent generates tests
# Uses Haiku for cost efficiency
# Achieves 90%+ coverage
# Auto-test hook runs tests on changes
# Quality gates ensure standards
```

Happy coding with iCCC!
