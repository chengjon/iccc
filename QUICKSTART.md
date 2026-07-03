# iCCC 快速开始指南 (Quick Start)

欢迎使用 **iCCC (Intelligent Collaborative Coding Co-pilot)** —— 下一代智能多智能体协作开发平台。

iCCC 采用独特的 **"三层金字塔架构"** (Brain -> Manager -> Worker) 和 **"规格驱动开发"** (Spec-Driven Development) 模式，通过 Markdown 文档驱动全自动化的软件开发流程。

---

## 1. 项目概述

iCCC 不仅仅是一个代码生成工具，它是一个完整的**虚拟软件开发团队**。

### 核心特性
- 🧠 **Brain Engine**: 负责深度思考、需求分析和顶层规划 (Powered by Claude Opus)。
- 👔 **Manager Agents**: 负责任务拆解、代码审查和质量把控 (Powered by Claude Sonnet)。
- 👷 **Worker Agents**: 负责具体的代码实现和测试 (Powered by Claude Haiku/Sonnet)。
- 📄 **文档即状态**: 使用 `IDEAS.md`, `INSTITUTION.md`, `MAINTASK.md` 作为共享内存。
- 🛡️ **安全隔离**: 基于 Git Worktrees 和文件锁的独立工作区。

---

## 2. 环境准备

在开始之前，请确保您的环境满足以下要求：

### 基础环境
- **操作系统**: Linux (推荐) or macOS
- **Python**: 3.12 或更高版本
- **Git**: 2.20+

### 依赖服务
- **Redis**: 用于任务队列和分布式锁 (v6.0+)
- **MongoDB**: 用于持久化存储项目和 Agent 状态 (v5.0+)

### API 密钥
- **Anthropic API Key**: 用于驱动 Claude 模型。

---

## 3. 安装步骤

### 3.1 克隆仓库
```bash
git clone https://github.com/your-org/iccc.git
cd iccc
```

### 3.2 创建虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.3 安装依赖
```bash
pip install -e .
```

### 3.4 配置环境变量
复制示例配置文件并填入您的 API 密钥：
```bash
cp .env.example .env
# 编辑 .env 文件，填入:
# ANTHROPIC_API_KEY=sk-ant-...
# REDIS_URL=redis://localhost:6379/0
# MONGODB_URL=mongodb://localhost:27017
```

---

## 4. 基本用法：规格驱动开发流程

iCCC 的核心工作流遵循 **Think -> Spec -> Code -> Review** 的循环。

### 步骤 1: 初始化项目
在目标目录中初始化 iCCC：
```bash
# 在当前目录初始化
python -m iccc.cli project init . --name "MyNewProject"
```

### 步骤 2: 提出需求 (The Brain Cycle)
不需要手动创建任务，直接告诉 Brain 您想要什么。Brain 会分析需求并生成 `MAINTASK.md`。

```bash
# 运行 Brain Cycle
python -m iccc.cli brain cycle --request "实现用户登录功能，使用 JWT，需要包含单元测试"
```
*此时，根目录下会生成/更新 `IDEAS.md` (需求) 和 `MAINTASK.md` (计划)。*

### 步骤 3: 导入与分发任务
确认 `MAINTASK.md` 无误后，将计划导入系统。系统会自动将任务分发给 Worker 和 Manager。

```bash
python -m iccc.cli task import --project "MyNewProject"
```

### 步骤 4: 启动编排器
启动系统，Agent 开始自动工作：
```bash
python -m iccc.cli start --project "MyNewProject"
```

### 步骤 5: 监控进度
使用 Tmux 仪表板查看实时状态（强烈推荐）：
```bash
./dashboard/tmux_dashboard.sh
```

---

## 5. 状态流转说明

系统内部自动执行以下闭环：

1.  **Pending**: 任务在队列中等待。
2.  **In Progress**: **Worker** 领取任务，在独立 Git 分支中编码。
3.  **Review Needed**: Worker 完成编码，提交本地 Commit，请求审查。
4.  **In Progress (Manager)**: **Manager** 领取审查任务，检查代码质量。
    *   *如果通过*: 任务标记为 **Completed**，代码准备合并。
    *   *如果拒绝*: 状态变为 **Changes Requested**，退回给 Worker。
5.  **Changes Requested**: Worker 收到反馈，修正代码，再次提交。

---

## 6. 配置说明

核心配置文件位于 `.config/` 目录下：

*   **`roles.json`**: 定义 Agent 的角色、权限和使用的模型。
*   **`quality_gates.json`**: 定义代码审查的自动化规则（Lint, Test 覆盖率等）。
*   **`agent-limits.json`**: 控制并发数量和 Token 消耗上限。

---

## 7. 故障排查

### 常见问题

**Q1: Redis 连接失败？**
*   检查 `.env` 中的 `REDIS_URL`。
*   确保 Redis 服务已启动 (`systemctl status redis` 或 `docker ps`)。

**Q2: 任务一直处于 Pending 状态？**
*   检查 `python -m iccc.cli start` 是否正在运行。
*   检查仪表板中的 Queue 长度。
*   确认是否有空闲的 Agent (状态为 IDLE)。

**Q3: Brain 生成的计划不符合预期？**
*   手动修改 `IDEAS.md` 补充细节。
*   再次运行 `python -m iccc.cli brain cycle` 进行重新规划。

**Q4: 日志在哪里？**
*   系统日志: `.iccc/.logs/app.log`
*   错误日志: `.iccc/.logs/error.log`

---

## 8. 贡献指南

我们欢迎社区贡献！

1.  **Fork** 本仓库。
2.  **创建分支**: `git checkout -b feature/amazing-feature`。
3.  **开发与测试**:
    *   请确保通过所有单元测试：`pytest`
    *   遵循 PEP 8 编码规范。
4.  **提交 PR**: 描述您的更改和动机。

---

> **提示**: 在开发过程中，请始终遵循 **"先思考，后行动"** 的原则。如有疑问，请查阅 `docs/` 目录下的详细架构文档。