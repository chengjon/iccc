# iCCC 快速入门指南

iCCC (i-Claude Code CLI) 是一个多智能体编排系统，用于管理和并行运行多个 AI CLI 实例协同完成软件开发任务。

## 目录

- [系统要求](#系统要求)
- [安装](#安装)
- [配置](#配置)
- [快速开始](#快速开始)
- [核心概念](#核心概念)
- [常用命令](#常用命令)
- [示例工作流](#示例工作流)

## 系统要求

- Python 3.12+
- MongoDB 6.0+
- Redis 7.0+
- Git 2.30+
- Anthropic API Key

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/iccc.git
cd iccc
```

### 2. 安装依赖

使用 pip:

```bash
pip install -e .
```

或使用 uv (推荐):

```bash
uv pip install -e .
```

### 3. 安装开发依赖（推荐）

```bash
pip install -e ".[dev]"

# 或使用 uv (更快)
uv pip install -e ".[dev]"
```

### 4. 验证安装

```bash
# 运行测试确保安装正确
python -m pytest tests/ -v --tb=short

# 预期结果: 470 passed, 23 skipped
```

### 5. 启动依赖服务

确保 MongoDB 和 Redis 正在运行:

```bash
# 使用 Docker (推荐)
docker run -d --name mongodb -p 27017:27017 mongo:6
docker run -d --name redis -p 6379:6379 redis:7

# 或使用本地安装的服务
mongod --dbpath /data/db
redis-server
```

## 配置

### 1. 创建配置文件

```bash
cp config.example.yaml config.yaml
```

### 2. 编辑配置

```yaml
# config.yaml
log_level: INFO

mongodb:
  host: localhost
  port: 27017
  database: iccc

redis:
  host: localhost
  port: 6379
  db: 0

anthropic:
  api_key: ${ANTHROPIC_API_KEY}  # 从环境变量读取
  default_model: claude-sonnet-4-20250514

orchestration:
  max_concurrent_agents: 5
  task_timeout: 300
  master_model: opus
```

### 3. 设置环境变量

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

或创建 `.env` 文件:

```env
ANTHROPIC_API_KEY=your-api-key-here
MONGODB_URI=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379
```

## 快速开始

### 1. 初始化项目

```bash
# 在目标项目目录中初始化 iCCC
iccc project init ./my-project --name "My Project"
```

### 2. 创建 Agent

```bash
# 创建一个前端开发 Agent (使用 Haiku 模型)
iccc agent create --name "frontend" --project "My Project" --type frontend --model haiku

# 创建一个后端开发 Agent (使用 Sonnet 模型)
iccc agent create --name "backend" --project "My Project" --type backend --model sonnet

# 创建一个代码审核 Agent (使用 Opus 模型)
iccc agent create --name "reviewer" --project "My Project" --type reviewer --model opus
```

### 3. 创建任务

```bash
# 创建一个编码任务
iccc task create --project "My Project" \
  --description "实现用户登录 API" \
  --type coding \
  --priority 1

# 创建一个代码审核任务
iccc task create --project "My Project" \
  --description "审核登录 API 的安全性" \
  --type review \
  --depends-on <previous-task-id>
```

### 4. 启动编排器

```bash
# 启动主控编排器
iccc orchestrate --project "My Project"
```

### 5. 查看状态

```bash
# 查看项目状态
iccc project status "My Project"

# 查看所有 Agent 状态
iccc agent list --project "My Project"

# 查看任务队列
iccc task list --project "My Project"
```

## 核心概念

### Master CLI (编排器)

- 使用 Claude Opus 模型进行高级推理
- 负责任务分解、调度和冲突仲裁
- 监控所有 Worker Agent 的运行状态

### Worker Agents

| 类型 | 模型 | 职责 |
|------|------|------|
| Frontend | Haiku/Sonnet | 前端开发、UI 组件 |
| Backend | Sonnet | 后端 API、业务逻辑 |
| Testing | Sonnet | 测试编写、质量保证 |
| Reviewer | Opus | 代码审核、安全检查 |
| Docs | Haiku | 文档编写 |

### Git Worktree 隔离

每个 Agent 在独立的 Git Worktree 中工作，避免文件冲突:

```
project/
├── .git/                    # 主仓库
├── src/                     # 主工作目录
└── .worktrees/
    ├── agent-frontend/      # 前端 Agent 工作空间
    ├── agent-backend/       # 后端 Agent 工作空间
    └── agent-testing/       # 测试 Agent 工作空间
```

### 任务状态流转

```
pending → in_progress → review → completed
                ↓
             failed → retry
```

## 常用命令

### 项目管理

```bash
iccc project init <directory>     # 初始化项目
iccc project list                 # 列出所有项目
iccc project status <name>        # 查看项目状态
iccc project archive <name>       # 归档项目
```

### Agent 管理

```bash
iccc agent create                 # 创建 Agent
iccc agent list                   # 列出 Agent
iccc agent status <id>            # 查看 Agent 状态
iccc agent stop <id>              # 停止 Agent
iccc agent logs <id>              # 查看 Agent 日志
```

### 任务管理

```bash
iccc task create                  # 创建任务
iccc task list                    # 列出任务
iccc task status <id>             # 查看任务状态
iccc task cancel <id>             # 取消任务
iccc task retry <id>              # 重试失败任务
```

### 编排控制

```bash
iccc orchestrate                  # 启动编排器
iccc orchestrate --dry-run        # 模拟运行
iccc orchestrate --max-agents 3   # 限制并发 Agent 数
```

### 可观测性

```bash
iccc dashboard                    # 启动 Web Dashboard
iccc events list                  # 查看事件列表
iccc events tail                  # 实时查看事件流
```

## 示例工作流

### 功能开发流程

```bash
# 1. 初始化项目
iccc project init ./my-app --name "MyApp"

# 2. 创建开发团队
iccc agent create --name "dev-lead" --project "MyApp" --type general --model opus
iccc agent create --name "frontend-dev" --project "MyApp" --type frontend --model sonnet
iccc agent create --name "backend-dev" --project "MyApp" --type backend --model sonnet
iccc agent create --name "qa-engineer" --project "MyApp" --type testing --model sonnet

# 3. 提交功能需求
iccc task create --project "MyApp" \
  --description "实现用户认证功能，包括登录、注册、密码重置" \
  --type feature \
  --priority 1

# 4. 启动编排 (Master CLI 会自动分解任务并分配给合适的 Agent)
iccc orchestrate --project "MyApp"

# 5. 监控进度
iccc dashboard
```

### 代码审核流程

```bash
# 创建审核任务
iccc task create --project "MyApp" \
  --description "审核 PR #123: 用户认证功能" \
  --type review \
  --assign-to reviewer

# 查看审核结果
iccc task status <task-id> --full
```

## 开发者指南

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/agents/ -v
python -m pytest tests/queue/ -v
python -m pytest tests/hooks/ -v

# 运行带覆盖率报告
python -m pytest tests/ --cov=iccc --cov-report=term-missing

# 快速测试 (跳过慢速测试)
python -m pytest tests/ -v -m "not slow"
```

### 类型检查

```bash
# 运行 mypy 类型检查
python -m mypy iccc/ --ignore-missing-imports

# 检查特定模块
python -m mypy iccc/agents/ --ignore-missing-imports
python -m mypy iccc/queue/ --ignore-missing-imports
```

### 代码质量

```bash
# 运行 ruff 格式检查
ruff check iccc/

# 自动修复
ruff check iccc/ --fix
```

### 当前测试状态

| 测试类别 | 数量 | 状态 |
|----------|------|------|
| 单元测试 | 450+ | ✅ 通过 |
| 集成测试 | 20+ | ✅ 通过 |
| 总计 | 470 | ✅ 通过 |
| 跳过 | 23 | ⏭️ 需要外部服务 |

### 项目结构

```
iccc/
├── agents/          # Agent 客户端和子代理管理
├── db/              # MongoDB 数据库仓库
├── hooks/           # Claude Hooks 实现
├── isolation/       # Git Worktree 隔离管理
├── locks/           # Redis 分布式文件锁
├── models/          # Pydantic 数据模型
├── observability/   # 事件收集和监控
├── planning/        # 任务规划算法
├── queue/           # Redis 任务队列
└── orchestrator.py  # 主编排器
```

## 下一步

- 阅读 [架构文档](./multi-agent-project-manager.md) 了解系统架构
- 查看 [Claude Hooks 指南](./mastering-claude-hooks-building.md) 学习安全控制
- 参考 [Git Worktrees 指南](./Git_Worktrees_for_AI_Agents.md) 了解隔离机制
- 了解 [可观测性系统](./multi-agent-observability.md) 监控最佳实践

## 常见问题

### Q: 如何处理 Agent 冲突？

A: iCCC 使用 Git Worktree 隔离和 Redis 分布式锁来防止冲突。如果检测到冲突，Master CLI 会自动仲裁。

### Q: 支持哪些 AI CLI？

A: 目前主要支持 Claude Code，未来计划支持 iflow、Gemini、Opencode 等。

### Q: 如何控制成本？

A: 使用 `--model` 参数选择合适的模型。简单任务使用 Haiku，复杂任务使用 Opus。系统会自动进行模型选择优化。

### Q: 如何扩展到多机器？

A: 确保所有机器可以访问同一个 MongoDB 和 Redis 实例，然后在每台机器上运行 Agent。

---

更多文档请参阅 `docs/` 目录。
