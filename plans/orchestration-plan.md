---
title: Hermes + iCCC + Ruflo 多 CLI 标准化开发流水线方案
created: 2026-07-03
tags: [hermes, iccc, ruflo, multi-cli, orchestration]
---

# Hermes + iCCC + Ruflo 多 CLI 标准化开发流水线方案

> 设计文档 v1 — 待审批后实施

---

## 一、问题与目标

### 现状

- 你有多个 CLI 工具（Hermes、Claude Code、OpenCode），各自独立工作
- 已搭建 ruflo MCP 作为工具总线（337 tools，full profile）
- iCCC 仓库已有完整的多 CLI 协作架构设计（HTN 规划、Redis 事件总线、Worktree 管理）
- 但缺乏一个标准化的、可重复的开发流程：从**指令 → 分解 → 分配 → 开发 → 审核 → 合并**的全自动流水线

### 目标

建立以 **Hermes 为大脑、iCCC 为架构底座、Ruflo 为通信总线**的标准化开发流水线：

1. 开发者在 Hermes 下达指令
2. Hermes 自动分解任务、建 worktree、通过 Ruflo 分派
3. 各 CLI（Claude Code / OpenCode / 更多）在各自 worktree 中并行开发
4. Hermes 监控进度、自动触发依赖任务
5. 审核通过后自动合并

---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        你（开发者 / 最终决策者）                      │
│              在 Hermes 下达一条指令                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Hermes（大脑 / 编排层）                        │
│                                                                     │
│  1. 指令接收 → HTN 任务分解（LLM 驱动）                               │
│  2. Git Worktree 创建（代码隔离）                                     │
│  3. 通过 Ruflo 分派任务                                               │
│  4. 轮询监控 + 自动触发依赖任务                                       │
│  5. 审核 + 合并到主分支                                               │
└──────────┬──────────────────────────────┬────────────────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────┐          ┌────────────────────────┐
│  iCCC 架构底座    │          │  Ruflo MCP 通信总线     │
│  (设计参考/模板)   │          │  (337 tools)            │
│                  │          │                         │
│  - HTN 分解模式   │          │  task_create  (分派)    │
│  - Worktree 管理  │          │  task_assign (分配)     │
│  - 角色模板       │          │  task_list   (查询)    │
│  - 质量门禁       │          │  task_complete (完成)   │
│                  │          │  task_status (状态)     │
│                  │          │  task_summary (汇总)    │
│                  │          │                         │
│                  │          │  workflow_*  (依赖编排)  │
│                  │          │  memory_*    (状态共享)  │
│                  │          │  agent_*     (Agent)    │
└──────────────────┘          └────────────────────────┘
           │                              │
           └──────────────┬───────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
    ┌──────────────────┐   ┌──────────────────┐
    │  Worktree A       │   │  Worktree B       │
    │  branch:feature/  │   │  branch:feature/  │
    │  kdj-formula      │   │  kdj-test         │
    │                   │   │                   │
    │  Claude Code      │   │  OpenCode         │
    │  (或任何 CLI)     │   │  (或任何 CLI)     │
    └──────────────────┘   └──────────────────┘
```

### 各组件职责

| 组件 | 角色 | 职责范围 |
|------|------|---------|
| **Hermes** | 大脑 | 接收指令、LLM 任务分解、监控进度、审核合并、做最终决策 |
| **iCCC** | 架构底座 | 提供 HTN/STRIPS 规划模式、Worktree 管理脚本、角色模板、质量门禁定义 |
| **Ruflo** | 通信总线 | 任务队列（task_*）、依赖编排（workflow_*）、跨 worker 状态共享（memory_*）、进度广播 |
| **Git Worktree** | 代码隔离 | 每个子任务独享一个 worktree，完全独立分支，互不干扰 |
| **Worker CLI** | 执行者 | Claude Code / OpenCode / 其他 — 在自己的 worktree 中完成指派的任务 |

---

## 三、五步流水线详解

### 步骤 1：任务分解（HTN 风格，LLM 驱动）

Hermes 接收一条自然语言指令，利用 LLM 能力进行 HTN 风格的分层分解：

**输入**：
```
"开发一个涨停板选股函数，包含测试和性能优化"
```

**输出**（Hermes 自动生成）：
```json
[
  {
    "id": "task-001",
    "type": "feature",
    "desc": "实现 filter_limit_up() 函数",
    "branch": "feature/limit-up-formula",
    "assigned": "claude-code",
    "deps": [],
    "wt_dir": "wt-limit-up",
    "ac": ["函数签名正确", "涨停逻辑覆盖主板/ST/新股", "回测通过"]
  },
  {
    "id": "task-002",
    "type": "test",
    "desc": "写 pytest 测试（22个用例）",
    "branch": "feature/limit-up-test",
    "assigned": "opencode",
    "deps": ["task-001"],
    "wt_dir": "wt-limit-up-test",
    "ac": ["正常涨停覆盖", "ST 5%覆盖", "新股首日覆盖", "全部通过"]
  },
  {
    "id": "task-003",
    "type": "review",
    "desc": "审核代码，合并到 main",
    "branch": "main",
    "assigned": "hermes",
    "deps": ["task-001", "task-002"],
    "wt_dir": "",
    "ac": ["无回归", "代码规范检查通过"]
  }
]
```

**关键设计**：
- 分解由 Hermes 的 LLM 能力完成（不依赖 iCCC 的 HTN 代码，避免 MongoDB 依赖冲突）
- 每个子任务有明确的 `deps`（依赖关系）、`ac`（验收标准）、`assigned`（分派人）
- 任务粒度控制在 "一个 CLI 一次会话可完成" 的级别

### 步骤 2：Git Worktree 创建

对每个需要开发环境的子任务创建独立的 worktree：

```bash
git worktree add ../wt-limit-up feature/limit-up-formula
git worktree add ../wt-limit-up-test feature/limit-up-test
```

每个 worktree 内自动写入 `TASK.md` 说明文件：

```markdown
# 任务: 实现 filter_limit_up() 函数

- Assigned: claude-code
- Branch: feature/limit-up-formula
- Priority: high
- Dependencies: 无

## 验收标准
- [ ] 函数签名正确
- [ ] 涨停逻辑覆盖主板/ST/新股
- [ ] 回测通过
```

### 步骤 3：Ruflo Task 分派

通过 Ruflo 的 `task_*` 工具创建任务并分配：

| Ruflo 操作 | 作用 |
|-----------|------|
| `task_create` | 在 ruflo 中注册一个子任务 |
| `task_assign` | 将任务分配给指定 worker |
| 标签 | `type`, `priority`, `tags` 用于过滤和排序 |

Worker CLI 通过 Ruflo 查询自己的待办：

```bash
curl -s http://localhost:3010/rpc ... | task_list(assignedTo="claude-code")
```

### 步骤 4：监控与桥接

Hermes 定期轮询 Ruflo `task_summary`，自动推进流水线：

```
轮询循环:
  对每个子任务:
    task_status(taskId=xxx).status
    
    如果 status == "completed":
      标记为完成
      检查依赖该任务的子任务是否全部就绪
      如果是 → 自动通知该 worker "你的前置任务已完成，可以开始了"
    
    如果 status == "failed" 或长时间无响应:
      通知开发者介入
```

**Ruflo 在两个 worker 之间的桥接作用**：

```
Worker A (Claude Code)            Worker B (OpenCode)
       │                               │
       │  task_complete(task-001)       │
       ├───────────────────────────────►│  Ruflo task_list → 看到 task-002 就绪
       │                               │
       │                               │  开始工作
       │                               │  task_complete(task-002)
       │◄──────────────────────────────┤
       │                               │
Hermes: 检测到两者完成 → 进入审核步骤
```

### 步骤 5：审核与合并

1. Hermes 列出各 worktree 的 `git diff --stat main`
2. 展示变更摘要给开发者
3. 开发者审批后，自动 `git merge --no-ff` 到 main
4. 可选：删除已合并的 worktree

---

## 四、Ruflo 在流水线中的核心价值

### 4.1 任务队列（worker 间通信）

Ruflo 的 `task_*` 工具是 worker 之间的**共享任务公告板**：

| 阶段 | 谁操作 | Ruflo 调用 |
|------|--------|-----------|
| 分派 | Hermes | `task_create` + `task_assign` |
| 查询 | Worker A | `task_list(assignedTo="claude-code")` |
| 完成 | Worker A | `task_complete(taskId=xxx)` |
| 通知 | Hermes | 轮询 `task_status`，发现完成 → 通知 Worker B |
| 查询 | Worker B | `task_list` 看到就绪的任务 |
| 完成 | Worker B | `task_complete(taskId=yyy)` |
| 汇总 | Hermes | `task_summary` 确认全部完成 |

### 4.2 依赖编排（workflow 工具）

Ruflo 的 `workflow_*` 工具可以定义带依赖关系的流水线：

```json
{
  "steps": [
    {"name": "写代码",   "depends_on": []},
    {"name": "写测试",   "depends_on": ["写代码"]},
    {"name": "审核合并", "depends_on": ["写代码", "写测试"]}
  ]
}
```

Hermes 自动执行 `workflow_execute` 并监控每一步的状态。

### 4.3 跨 worker 状态共享（memory 工具）

Ruflo 的 `memory_store` 可以用于 worker 之间传递中间结果：

```
Worker A: memory_store(key="api-contract", value="...接口规格...")
Worker B: memory_retrieve(key="api-contract") → 拿到规格开始写测试
```

> 注意：只适合小数据（<100KB）。代码仍通过 git 交换。

### 4.4 广播通知（未来）

如果 federation BBS 工具修复后，可以用 `federation_bbs_publish` 广播给所有 worker：

```
federation_bbs_publish(room="#dev", msgType="task-status", payload={"task-001": "completed"})
```

---

## 五、现有代码位置

### 已完成部分

| 文件 | 说明 | 状态 |
|------|------|------|
| `/opt/claude/iccc/orchestrator.py` | 流水线协调器（独立脚本） | ✅ 已实现（基础骨架） |
| Ruflo 连接 | `ruflo_init()`, `ruflo_task()` | ✅ 已测试通过 |
| HTN 分解示例 | `decompose()` 函数 | ✅ 样例实现（需增强） |
| Worktree 管理 | `wt_add()`, `wt_changes()`, `merge_branch()` | ✅ 已实现 |
| iCCC 仓库 | 已推送到 GitHub | ✅ |

### 待实施部分

| 模块 | 说明 | 优先级 |
|------|------|--------|
| **LLM 驱动的 HTN 分解** | 用 Hermes 的真实 LLM 能力代替样例 `decompose()` 函数 | P0 |
| **workflow 集成** | 调用 ruflo `workflow_create/execute` 代替手动轮询 | P1 |
| **失败重试** | task failed 时自动重试或重新分配 | P1 |
| **通知机制** | task 完成时自动通知关联 worker | P1 |
| **Web Dashboard** | 用 iCCC 已有的 dashboard 展示流水线进度 | P2 |
| **Federation 集成** | ruflo 跨机器 BBS 广播（需先修复 handler 缺失） | P3 |

---

## 六、实施计划

### 阶段一：核心链路验证（预计 1 次会话）

- [x] Ruflo task 工具连通性测试
- [x] Worktree 创建脚本
- [x] `orchestrator.py` 骨架
- [ ] 用真实 LLM 分解代替样例分解（Hermes 直接做）
- [ ] 完整跑通一次：指令 → 分解 → Worktree → Ruflo 分派 → 监控 → 合并

### 阶段二：增强稳定性（预计 1 次会话）

- [ ] Workflow 编排代替手动轮询
- [ ] 失败重试机制
- [ ] Worker 完成自动通知
- [ ] 多 Project 支持

### 阶段三：生产化（按需）

- [ ] Dashboard 集成
- [ ] 跨机器 Federation
- [ ] 与 iCCC Redis 总线对接

---

## 七、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Ruflo task 工具 handler 可能缺失（之前验证部分工具报 handler error） | 流水线中断 | 先测试完整工具链，如有缺失回退到手动 task_complete |
| Worktree 分支冲突 | 合并失败 | 每次 `git merge --no-ff`，Hermes 先做 `git diff --stat` 预览 |
| MongoDB 依赖冲突 | iCCC 包无法直接导入 | orchestrator.py 设计为完全独立脚本，不依赖 iccc 包 |
| Worker CLI 不在线 | 任务无人认领 | 超时后自动通知开发者人工干预 |
| Ruflo 容器重启 | 历史任务丢失 | `task_*` 数据在 ruflo 内存中，持久化需配置挂载卷 |

---

## 八、决策事项

1. **任务分解引擎**：用 Hermes 的 LLM 直接分解 vs 修复 iCCC 的 HTN 代码？
   - 建议：**Hermes LLM 直接分解**，更快、更灵活、无依赖冲突
2. **Worker 发现机制**：Ruflo task 轮询 vs Redis vs 直接文件通知？
   - 建议：**Ruflo task 轮询**（已验证），后续可加 Redis
3. **workflow 工具**：是否优先使用 ruflo `workflow_*`？
   - 建议：**阶段二做**，先验证 task 基础链路
