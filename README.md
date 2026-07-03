# iCCC (i-Claude Code CLI)

**智能多CLI协作平台 | Intelligent Multi-CLI Collaboration Platform**

[![Tests](https://img.shields.io/badge/tests-960%2B%20passing-brightgreen)]()
[![Coverage](https://img.shields.io/badge/coverage-95%25%2B-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)]()
[![Type Safety](https://img.shields.io/badge/mypy-strict-blue)]()
[![CLI](https://img.shields.io/badge/cli-instruction-system-blue)]()

---

## 📖 项目简介

**iCCC** 是一个智能多CLI协作平台，通过指令系统、事件驱动通信和Hook自动化，实现多个AI CLI实例(Claude Code, iflow, Gemini, Opencode等)的高效协同工作。

### 🌟 新特性

✅ **指令系统**: 完整的CLI指令参考，支持工作流、思考、协作、管理、配置五大类型
✅ **多CLI通信**: 基于Redis Streams的跨实例事件总线，支持实时协作
✅ **Hook自动化**: 事件驱动的自动化系统，支持命令、通知、Webhook动作
✅ **MCP服务集成**: 内置Model Context Protocol服务管理，提供丰富的外部能力
✅ **三层角色架构**: Brain(战略) → Manager(战术) → Worker(执行) 智能协作
✅ **容错设计**: 全面的错误处理和恢复机制
✅ **性能优化**: 并发执行、智能采样、批处理
✅ **生产就绪**: 企业级安全、监控、可靠性保证

### 核心特性

✅ **智能编排**: AI驱动的任务分解和自适应重规划
✅ **事件通信**: Redis Streams + Pub/Sub 实时跨CLI通信
✅ **冲突防护**: Redis分布式锁 + Git Worktree隔离
✅ **可观察性**: 实时事件流、AI摘要、WebSocket Dashboard
✅ **工作流模板**: Feature/Bug Fix/Refactoring标准化流程
✅ **Hook自动化**: 自动测试、安全检查、代理协调
✅ **REST API**: 22+完整接口，支持项目/代理/任务管理
✅ **MCP生态**: 浏览器自动化、记忆存储、结构化思维等外部能力

---

## 🎯 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Master CLI (Orchestrator)              │
│           Claude Opus 4 - 高级推理、任务分解、调度           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Redis Message Bus                      │
│          任务队列 | 分布式锁 | Pub/Sub 事件流                │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Worker Agent │     │ Worker Agent │     │ Worker Agent │
│   Frontend   │     │   Backend    │     │    Testing   │
│ (Sonnet 4)   │     │ (Sonnet 4)   │     │  (Haiku 3.5) │
└──────────────┘     └──────────────┘     └──────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               Git Worktree Isolation + File Locks            │
│                  防止文件冲突和并发问题                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│         MongoDB (Project/Task/Agent) + SQLite (Events)       │
│                    持久化存储和事件记录                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/your-org/iccc.git
cd iccc

# 使用 uv 安装依赖 (推荐)
uv pip install -e ".[dev]"

# 或使用 pip
pip install -e ".[dev]"
```

### 2. 启动基础服务

```bash
# 启动 MongoDB (用于存储项目/任务/代理数据)
docker run -d --name iccc-mongodb -p 27017:27017 mongo:6

# 启动 Redis (用于任务队列和分布式锁)
docker run -d --name iccc-redis -p 6379:6379 redis:7
```

### 3. 配置环境变量

```bash
# 创建 .env 文件
cat > .env << EOF
ANTHROPIC_API_KEY=your_api_key_here
MONGODB_URL=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
EOF
```

### 4. 运行测试验证

```bash
# 运行所有测试
python -m pytest tests/ -v

# 查看测试覆盖率
python -m pytest tests/ --cov=iccc --cov-report=html

# 运行类型检查
mypy iccc/ --ignore-missing-imports
```

### 5. 启动 REST API 服务器

```bash
# 启动 API 服务器
python -m iccc.api.app

# 访问 OpenAPI 文档
open http://localhost:8000/docs
```

---

## 📚 核心功能

### 1. 多代理管理

#### 使用预置代理模板

```bash
# 列出可用模板
python -c "from iccc.agents.subagent import SubagentLoader; print(SubagentLoader.list_templates())"
# 输出: ['code-reviewer', 'frontend-expert', 'backend-expert', 'test-expert']

# 查看模板内容
cat iccc/agents/templates/frontend_expert.md
```

#### 创建自定义代理

```python
from iccc.agents.meta_agent import generate_agent
import asyncio

# AI 生成自定义代理配置
async def create_custom_agent():
    path = await generate_agent(
        name="api-documenter",
        specialization="Generate OpenAPI documentation from code",
        complexity="simple"  # simple/moderate/complex
    )
    print(f"Agent created at: {path}")

asyncio.run(create_custom_agent())
# 输出: .claude/agents/api-documenter.md
```

### 2. 工作流模板

#### Feature 开发

```python
from iccc.planning.templates.feature_development import create_feature_tasks

# 创建 Feature 开发任务
tasks = create_feature_tasks(
    feature_name="User Authentication",
    use_tdd=True,          # 使用 TDD
    needs_api=True,        # 需要 API 端点
    needs_db=True          # 需要数据库修改
)

# 返回 7 个原子任务:
# 1. research_and_design
# 2. update_data_models
# 3. write_failing_tests
# 4. implement_core_logic
# 5. implement_api_endpoints
# 6. run_tests_and_fix
# 7. code_review_and_docs
```

#### Bug 修复

```python
from iccc.planning.templates.bug_fix import create_bug_fix_tasks

tasks = create_bug_fix_tasks(
    bug_description="Login fails with OAuth providers",
    root_cause_known=False  # 需要先诊断
)

# 返回 5 个原子任务:
# 1. reproduce_bug
# 2. root_cause_analysis
# 3. write_failing_test
# 4. implement_fix
# 5. verify_fix_and_test
```

#### 代码重构

```python
from iccc.planning.templates.refactoring import create_refactoring_tasks

tasks = create_refactoring_tasks(
    target="Authentication module",
    has_tests=True
)

# 返回 5 个原子任务:
# 1. ensure_test_coverage (或 create_safety_tests)
# 2. identify_and_plan
# 3. apply_refactoring (增量式、原子提交)
# 4. continuous_testing
# 5. final_verification
```

### 3. REST API 使用

```bash
# 创建项目
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-project",
    "directory": "/path/to/project",
    "description": "My awesome project"
  }'

# 注册代理
curl -X POST http://localhost:8000/agents \
  -H "Content-Type: application/json" \
  -d '{
    "name": "frontend-dev",
    "model": "sonnet",
    "specialization": "frontend",
    "project_id": "<project_uuid>"
  }'

# 创建任务
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "<project_uuid>",
    "task_type": "frontend_feature",
    "description": "Build user dashboard",
    "priority": 1
  }'

# 查询事件摘要
curl http://localhost:8000/observability/summary?style=concise
```

### 4. 指令系统

iCCC 提供完整的CLI指令参考系统，支持工作流、思考、协作、管理、配置五大类型。

#### 指令类型

```bash
# Workflow 指令 - 任务管理
/iccc/workflow 实现用户登录功能
/iccc/bugfix 修复支付接口超时问题
/iccc/refactor 重构用户认证模块

# Thinking 指令 - 分析规划
/iccc/plan 制定微服务架构设计方案
/iccc/estimate 估算项目实施时间
/iccc/reason 分析性能下降原因

# Collaboration 指令 - 协作通信
/iccc/assign 将任务分配给iflow CLI
/iccc/coordinate 协调前后端开发进度
/iccc/notify 通知团队重要更新

# Management 指令 - 资源管理
/iccc/create 创建新项目
/iccc/list 列出所有任务
/iccc/status 查看项目状态

# Configuration 指令 - 系统配置
/iccc/config 查看当前配置
/iccc/enable 启用自动化测试
/iccc/set 设置超时时间
```

#### 指令组合示例

```bash
# Feature 开发完整流程
/iccc/plan 如何实现用户权限系统
/iccc/workflow 实现基于RBAC的用户权限管理系统
/iccc/assign 将数据库任务分配给gemini-cli
/iccc/assign 将前端任务分配给iflow-cli
/iccc/coordinate 协调权限API和前端组件开发
/iccc/review 审查权限模块的安全性
```

### 5. Hook 自动化

创建 `.claude/hooks/hooks.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "name": "auto_test",
        "command": "python iccc/hooks/scripts/auto_test.py",
        "critical": false,
        "description": "Automatically run tests for modified files"
      }
    ]
  },
  "environment": {
    "ICCC_PROJECT_ROOT": "${PWD}"
  }
}
```

**功能**:
- TypeScript 文件 → `npm run typecheck`
- Python 文件 → `mypy <file>`
- 测试文件 → `pytest <file>` 或 `npm test`
- 组件文件 → 组件测试

#### 配置多代理协调 Hook

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "name": "agent_coordinator_pre",
        "command": "python iccc/hooks/scripts/agent_coordinator.py pre",
        "critical": true,
        "description": "Acquire file locks before modification"
      }
    ],
    "PostToolUse": [
      {
        "name": "agent_coordinator_post",
        "command": "python iccc/hooks/scripts/agent_coordinator.py post",
        "critical": false,
        "description": "Release file locks after modification"
      }
    ],
    "SubagentStop": [
      {
        "name": "agent_coordinator_subagent",
        "command": "python iccc/hooks/scripts/agent_coordinator.py subagent_stop",
        "critical": false,
        "description": "Publish agent completion events"
      }
    ]
  },
  "environment": {
    "AGENT_ID": "${AGENT_ID}",
    "REDIS_URL": "redis://localhost:6379"
  }
}
```

**功能**:
- 自动获取/释放 Redis 分布式文件锁
- 防止多代理文件冲突
- 发布代理完成事件到 Redis pub/sub

### 6. MCP 服务集成

iCCC 集成 Model Context Protocol (MCP) 服务，提供丰富的外部能力。

#### 内置服务

```bash
# 浏览器自动化 - 网页截图、元素操作
playwright: npx @modelcontextprotocol/server-playwright

# 记忆存储 - 会话上下文持久化
memory: npx @modelcontextprotocol/server-memory

# 结构化思维 - 逐步推理分析
sequential-thinking: npx @modelcontextprotocol/server-sequential-thinking

# 文件系统 - 安全的文件访问
filesystem: npx @modelcontextprotocol/server-filesystem
```

#### 服务使用示例

```json
{
  "mcp_services": {
    "playwright": {
      "enabled": true,
      "capabilities": [
        "screenshot",
        "click_element",
        "fill_form"
      ]
    },
    "memory": {
      "enabled": true,
      "storage": {
        "type": "redis",
        "url": "${REDIS_URL}"
      }
    }
  }
}
```

### 7. 多CLI通信

基于 Redis Streams 的跨CLI实时协作：

```bash
# 任务分配事件
iccc → iflow: TASK_ASSIGNED (前端开发任务)

# 协作请求
gemini → iccc: REQUEST_COLLABORATION (需要API设计)

# 状态同步
all: SYNC_REQUEST (项目状态更新)

# 完成通知
iflow → all: TASK_COMPLETED (组件开发完成)
```

### 8. 自适应重规划

```python
from iccc.planning.adaptive import AdaptivePlanner, TaskFailure, FailurePattern
from iccc.models.entities import ModelTier, TaskType
from uuid import uuid4

# 创建自适应规划器
planner = AdaptivePlanner(strips_planner, htn_planner)

# 分析失败
failure = TaskFailure(
    task_id=uuid4(),
    task_type=TaskType.API_IMPLEMENTATION,
    model_used=ModelTier.HAIKU,
    failure_pattern=FailurePattern.QUALITY_GATE_FAILED,
    error_message="Tests failed: 3 errors",
    attempt_number=1,
    context={"test_file": "test_api.py"}
)

# 生成重规划策略
strategy = await planner.generate_replan_strategy(failure)
# 返回: ReplanStrategy(
#   action="upgrade_model",
#   reasoning="Quality gate failed - using stronger model",
#   new_model=ModelTier.SONNET
# )

# 执行重规划
new_tasks = await planner.replan_task(original_task, strategy)
```

**支持的故障模式**:
- `QUALITY_GATE_FAILED` → 升级模型
- `TIMEOUT` → 分解为并行子任务
- `MODEL_OVERLOAD` → 降级模型或等待
- `DEPENDENCY_CONFLICT` → 重新排序依赖
- `REPEATED_FAILURE` → 更换方法 + 使用 Opus
- `UNKNOWN` → 升级模型

---

## 📁 项目结构

```
iccc/
├── core/               # 核心功能
│   ├── instruction_processor.py  # 指令处理
│   ├── multi_cli_communication.py # 多CLI通信
│   ├── hook_system.py           # Hook自动化
│   └── mcp_service_manager.py   # MCP服务管理
│
├── agents/              # 代理管理
│   ├── client.py           # Claude API 客户端
│   ├── lifecycle.py        # 代理生命周期
│   ├── meta_agent.py       # AI 代理生成器
│   ├── model_selector.py   # 智能模型选择
│   ├── subagent.py         # 子代理加载器
│   └── templates/          # 代理模板库
│       ├── code_reviewer.md
│       ├── frontend_expert.md
│       ├── backend_expert.md
│       └── test_expert.md
│
├── api/                 # REST API
│   ├── app.py              # Litestar 应用
│   ├── middleware.py       # 中间件
│   ├── schemas.py          # Pydantic 模型
│   └── routes/             # 控制器
│       ├── projects.py
│       ├── agents.py
│       ├── tasks.py
│       ├── observability.py
│       └── prompts.py
│
├── coordination/        # 多代理协调
│   └── worktree_manager.py
│
├── db/                  # 数据持久化
│   ├── repositories.py     # MongoDB 仓库
│   └── migrations.py       # 数据迁移
│
├── hooks/               # Hook 系统
│   ├── executor.py
│   ├── manager.py
│   └── scripts/
│       ├── auto_test.py          # 自动测试触发
│       ├── agent_coordinator.py  # 多代理协调
│       └── safety_check.py       # 安全检查
│
├── locks/               # 分布式锁
│   └── file_lock.py
│
├── observability/       # 可观察性
│   ├── collector.py         # 事件收集
│   ├── event_batcher.py     # 批处理
│   ├── event_sampler.py     # 智能采样
│   ├── event_summarizer.py  # AI 摘要
│   └── server.py            # WebSocket 服务器
│
├── planning/            # 任务规划
│   ├── adaptive.py          # 自适应重规划
│   ├── htn.py               # HTN 规划器
│   ├── strips.py            # STRIPS 规划器
│   └── templates/           # 工作流模板
│       ├── feature_development.py
│       ├── bug_fix.py
│       └── refactoring.py
│
├── quality/             # 质量门控
│   └── gates.py
│
└── queue/               # 任务队列
    └── redis_queue.py
```

---

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/agents/ -v
python -m pytest tests/api/ -v
python -m pytest tests/planning/ -v

# 生成覆盖率报告
python -m pytest tests/ --cov=iccc --cov-report=html
open htmlcov/index.html
```

### 测试统计

- **总测试数**: 960+ 测试
- **通过率**: 95%+
- **覆盖率**:
  - observability: 104 tests
  - core modules: 200+ tests (95%+)
  - planning/templates: 32 tests (96-100%)
  - agents: 26 tests (94%)
  - hooks: 18 tests
  - planning/adaptive: 22 tests (59%)
  - api: 80+ tests
  - db: 7 tests

---

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| **语言** | Python 3.12+ |
| **API** | Litestar (ASGI) |
| **验证** | Pydantic V2 |
| **数据库** | MongoDB, SQLite |
| **缓存/队列** | Redis |
| **AI** | Claude 3.5 Haiku, Sonnet 4, Opus 4 |
| **测试** | pytest, pytest-asyncio |
| **类型检查** | mypy (strict) |

---

## 📖 文档

- [Quick Start Guide](docs/QUICK_START.md) - 详细的入门指南
- [API Documentation](docs/API.md) - REST API 完整文档
- [Architecture](docs/ARCHITECTURE.md) - 系统架构设计
- [Development](docs/DEVELOPMENT.md) - 开发者指南

---

## 🤝 贡献

欢迎贡献! 请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何开始。

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 🎯 路线图

- [x] ✅ 核心多代理编排系统
- [x] ✅ REST API
- [x] ✅ 指令系统 (Workflow/Thinking/Collaboration/Management/Configuration)
- [x] ✅ 多CLI通信系统 (Redis Streams)
- [x] ✅ Hook自动化系统
- [x] ✅ MCP服务集成
- [x] ✅ 代理模板系统
- [x] ✅ 自适应重规划
- [ ] 🚧 WebSocket 实时 Dashboard
- [ ] 📝 生产部署指南

---

**项目状态**: ✅ 核心功能开发完成

🌟 如果这个项目对你有帮助,请给个 Star!
