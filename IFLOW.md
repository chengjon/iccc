# iFlow CLI 上下文概览

本文档记录了 iFlow CLI 的配置、用户偏好和项目特定信息。

---

## 用户偏好

- **语言**: 中文对话和内容生成
- **UI 框架偏好**: shadcn-ui

---

## 项目概览

**iCCC (i-Claude Code CLI)** 是一个多智能体编排系统，用于管理和运行多个 AI CLI 实例（Claude Code、iflow、Gemini、Opencode）以协作完成软件开发任务。

---

## 最近更新 (2025-12-28)

### Worktree 管理功能实现

根据 `docs/MULTI_CLI_WORKTREE_MANAGEMENT.md` 文档，实现了完整的 Git Worktree 多 CLI 协作管理功能：

#### 核心模块 (`iccc/coordination/worktree_manager.py`)

**任务管理**:
- `TaskInfo` 数据类：任务目标、验收标准、工作范围、优先级、工作量估算
- `create_worktree_with_task()`：创建 worktree 并自动生成任务 README
- `_generate_task_readme_template()`：符合文档规范的任务文档模板

**进度追踪**:
- `update_task_progress()`：更新任务进度（25%、50%、75%、100%）
- `get_worktree_status()`：获取 worktree 详细状态
- `generate_progress_report()`：生成 Markdown 进度报告

**合并与清理**:
- `merge_all_branches_to_main()`：合并所有 worker 分支到 main
- `cleanup_all_worktrees()`：清理所有 worktree

**Redis 集成**:
- `publish_task_event()`：发布任务事件（TASK_ASSIGNED、TASK_PROGRESS、TASK_COMPLETED）

#### Bash 脚本 (`bin/`)

- `create_worktrees.sh`：批量创建 worktree
- `monitor_worktrees.sh`：监控 worktree 状态
- `merge_and_cleanup.sh`：合并分支并清理

#### 测试

- `tests/coordination/test_worktree_manager.py`：12 个测试用例
- 所有测试通过：19 passed

---

## 使用方法

### Python API

```python
from iccc.coordination.worktree_manager import WorktreeManager, TaskInfo, ProgressReportGenerator

# 初始化管理器
manager = WorktreeManager("/path/to/project")

# 创建带任务信息的 worktree
task = TaskInfo(
    task_id="feature-auth-001",
    description="实现用户认证系统",
    acceptance_criteria=["实现登录功能", "实现注册功能", "通过安全测试"],
    work_scope=["代码开发", "测试编写"],
    priority="high",
    estimated_hours=8
)
worktree_path = await manager.create_worktree_with_task("auth-worker", task)

# 更新进度
await manager.update_task_progress("auth-worker", progress=50, status="running")

# 生成进度报告
report = await manager.generate_progress_report()
```

### Bash 脚本

```bash
# 创建 worktree（从任务文件）
./bin/create_worktrees.sh tasks.txt

# 监控状态
./bin/monitor_worktrees.sh

# 合并并清理
./bin/merge_and_cleanup.sh
```

---

## 技术栈

| 组件 | 技术 |
|-----|-----|
| 语言 | Python 3.12+ |
| Git 集成 | Git Worktree |
| 消息总线 | Redis Streams |
| 测试 | pytest + pytest-asyncio |

---

## 测试状态

- **总测试数**: 19+
- **通过率**: 100%
- **Linting**: ruff 通过

---

*最后更新: 2025-12-28*
