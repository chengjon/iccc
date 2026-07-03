"""
多CLI Worktree 协作管理器

基于Git Worktree的多CLI协作管理实现，包括：
- Worktree创建与管理
- 任务分配与README模板生成
- 进度监控与报告
- 分支合并与清理
- 与Redis事件总线集成
"""

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class WorktreeEventType(Enum):
    """Worktree相关事件类型"""
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    WORKTREE_CREATED = "WORKTREE_CREATED"
    WORKTREE_REMOVED = "WORKTREE_REMOVED"
    BRANCH_MERGED = "BRANCH_MERGED"
    HEARTBEAT = "HEARTBEAT"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    task_name: str
    branch_name: str
    description: str
    priority: TaskPriority
    estimated_hours: float
    assignee: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    acceptance_criteria: list[str] = field(default_factory=list)
    scope_included: list[str] = field(default_factory=list)
    scope_excluded: list[str] = field(default_factory=list)
    problems: list[dict] = field(default_factory=list)


@dataclass
class ProcessResult:
    """子进程执行结果"""
    returncode: int
    stdout: str
    stderr: str


class WorktreeEventBus:
    """Worktree事件总线（轻量级事件发布系统）"""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url
        self.redis_client = None
        self.handlers: dict[WorktreeEventType, list] = {}
        self.cli_id = f"worktree-manager-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    async def connect(self) -> bool:
        """连接到Redis（如果配置了URL）"""
        if self.redis_url:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(self.redis_url)
                await self.redis_client.ping()
                return True
            except Exception:
                return False
        return False

    async def disconnect(self) -> None:
        """断开Redis连接"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

    async def publish_event(
        self,
        event_type: WorktreeEventType,
        data: dict[str, Any],
        source_cli: str | None = None,
        target_cli: str | None = None,
    ) -> str | None:
        """发布事件"""
        event_data = {
            "id": f"{datetime.now().isoformat()}-{id(data)}",
            "type": event_type.value,
            "source_cli": source_cli or self.cli_id,
            "target_cli": target_cli,
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        if self.redis_client:
            try:
                stream_name = "iccc_worktree_events"
                msg_id = await self.redis_client.xadd(stream_name, event_data)
                return str(msg_id)
            except Exception:
                pass

        # 本地事件处理
        for handler in self.handlers.get(event_type, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_data)
                else:
                    handler(event_data)
            except Exception:
                pass

        return None

    def subscribe(self, event_type: WorktreeEventType, handler) -> None:
        """订阅事件"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)


class WorktreeManager:
    """增强的Git Worktree管理器

    支持多CLI协作开发，包括任务分配、进度跟踪、合并清理等功能。
    """

    def __init__(
        self,
        project_dir: str,
        worktrees_dir: str | None = None,
        branch_prefix: str = "iccc-",
        event_bus: WorktreeEventBus | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.branch_prefix = branch_prefix
        self.event_bus = event_bus or WorktreeEventBus()

        # Worktree基础目录
        if worktrees_dir:
            self.worktrees_dir = Path(worktrees_dir)
        else:
            self.worktrees_dir = self.project_dir / "worktrees"

        # 任务信息存储
        self.tasks_file = self.project_dir / ".iccc" / "tasks.json"

        # 确保目录存在
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_iccc_dir()

    def _ensure_iccc_dir(self) -> None:
        """确保.iccc目录存在"""
        iccc_dir = self.project_dir / ".iccc"
        iccc_dir.mkdir(parents=True, exist_ok=True)

    async def _run_git(
        self, cmd: list[str], cwd: Path | None = None
    ) -> ProcessResult:
        """执行git命令"""
        if cwd is None:
            cwd = self.project_dir

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            return ProcessResult(
                process.returncode or 0,
                stdout.decode("utf-8") if stdout else "",
                stderr.decode("utf-8") if stderr else "",
            )
        except FileNotFoundError:
            return ProcessResult(1, "", f"Command not found: {cmd[0]}")

    async def ensure_main_updated(self) -> bool:
        """确保main分支是最新的"""
        # 切换到main分支
        result = await self._run_git(["git", "checkout", "main"])
        if result.returncode != 0:
            return False

        # 拉取最新
        result = await self._run_git(["git", "pull", "origin", "main"])
        return result.returncode == 0

    async def branch_exists(self, branch: str) -> bool:
        """检查分支是否存在"""
        result = await self._run_git(["git", "rev-parse", "--verify", branch])
        return result.returncode == 0

    async def create_worktree(
        self,
        agent_id: str,
        branch: str | None = None,
        task_info: TaskInfo | None = None,
    ) -> Path:
        """创建新的worktree

        Args:
            agent_id: Agent标识符
            branch: 分支名称（默认为agent/{agent_id}）
            task_info: 任务信息（用于生成README模板）

        Returns:
            Worktree路径
        """
        self.worktrees_dir.mkdir(exist_ok=True)

        # 确定分支名称
        branch = f"agent/{agent_id}" if branch is None else f"{self.branch_prefix}{branch}"

        # Worktree路径
        worktree_path = self.worktrees_dir / agent_id

        # 如果已存在，先删除
        if worktree_path.exists():
            await self.remove_worktree(agent_id)

        # 如果分支不存在，创建它
        if not await self.branch_exists(branch):
            await self._run_git(["git", "branch", branch])

        # 创建worktree
        cmd = ["git", "worktree", "add", str(worktree_path), branch]
        result = await self._run_git(cmd)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        # 配置worktree
        await self._configure_worktree(worktree_path, agent_id)

        # 如果提供了任务信息，生成README
        if task_info:
            await self._generate_task_readme(worktree_path, task_info)

        # 发布事件
        await self.event_bus.publish_event(
            WorktreeEventType.WORKTREE_CREATED,
            {"agent_id": agent_id, "branch": branch, "path": str(worktree_path)},
            source_cli="worktree-manager",
        )

        return worktree_path

    async def _configure_worktree(self, worktree_path: Path, agent_id: str) -> None:
        """配置worktree的Git设置"""
        # 设置用户信息
        await self._run_git(
            ["git", "config", "user.name", f"Agent {agent_id}"],
            cwd=worktree_path,
        )
        await self._run_git(
            ["git", "config", "user.email", f"{agent_id}@iccc.local"],
            cwd=worktree_path,
        )

    def _generate_task_readme_template(self, task: TaskInfo) -> str:
        """生成任务README模板"""
        priority_emoji = {1: "🟢", 2: "🟡", 3: "🔴", 4: "🔴"}.get(task.priority.value, "⚪")

        acceptance_criteria_md = "\n".join(
            f"- [ ] {criterion}" for criterion in task.acceptance_criteria
        )

        scope_included_md = "\n".join(f"- ✅ {item}" for item in task.scope_included)
        scope_excluded_md = "\n".join(f"- ⚠️ {item}" for item in task.scope_excluded)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

        return f"""# iCCC项目 - {task.description}

## 任务目标
{task.description}

## 任务分配信息
- **分配给**: {task.assignee or f"Worker CLI - {task.agent_id}"}
- **分配时间**: {current_time}
- **主CLI**: iCCC (Manager)
- **项目**: {self.project_dir.name}
- **分支**: {task.branch_name}
- **任务ID**: {task.task_id}

## 验收标准
{acceptance_criteria_md}

## 工作范围
### 本Worktree范围内
{scope_included_md}

### 超出本Worktree范围（需要请示主CLI）
{scope_excluded_md}

## 优先级
{priority_emoji} {"高" if task.priority == TaskPriority.HIGH else "中" if task.priority == TaskPriority.MEDIUM else "低"}

## 预计工作量
- **总计**: {task.estimated_hours}小时

## 预计完成时间
T+{int(task.estimated_hours)}h

## 问题请示流程
如果遇到以下情况，请向主CLI请示：
1. 需要修改其他Worktree的文件
2. 需要调整任务优先级
3. 需要额外的资源或协助
4. 发现无法独立解决的技术问题

## 进度更新

### T+0h（任务开始）
- **状态**: 任务理解中
- **进度**: 0%

---

## 进度更新记录

<!-- 请在此处添加进度更新，使用以下格式：

### T+Xh
- **状态**: 进行中/阻塞/完成
- **进度**: X%
- **已完成**:
  - [x] 完成项1
  - [x] 完成项2
- **进行中**:
  - 🔄 进行项1
- **待开始**:
  - ⏳ 待开始项
- **遇到的问题**:
  - 问题描述和解决方案

-->

---

*文档由iCCC Worktree Manager生成*
*最后更新: {current_time}*
"""

    async def _generate_task_readme(self, worktree_path: Path, task: TaskInfo) -> None:
        """为worktree生成任务README"""
        readme_path = worktree_path / "README.md"

        # 从task_info获取agent_id (如果存在)
        getattr(task, "agent_id", task.task_id.split("-")[0])

        template = self._generate_task_readme_template(task)
        readme_path.write_text(template)

    async def remove_worktree(self, agent_id: str) -> bool:
        """删除worktree"""
        worktree_path = self.worktrees_dir / agent_id

        if not worktree_path.exists():
            return False

        # 删除worktree
        cmd = ["git", "worktree", "remove", str(worktree_path), "--force"]
        result = await self._run_git(cmd)

        # 如果目录仍然存在，强制删除
        if worktree_path.exists():
            shutil.rmtree(worktree_path)

        # 发布事件
        await self.event_bus.publish_event(
            WorktreeEventType.WORKTREE_REMOVED,
            {"agent_id": agent_id, "path": str(worktree_path)},
            source_cli="worktree-manager",
        )

        return result.returncode == 0

    async def list_worktrees(self) -> list[dict[str, str]]:
        """列出所有worktree"""
        cmd = ["git", "worktree", "list", "--porcelain"]
        result = await self._run_git(cmd)

        if result.returncode != 0:
            return []

        worktrees: list[dict[str, str]] = []
        current_worktree: dict[str, str] = {}

        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    if current_worktree:
                        worktrees.append(current_worktree)
                        current_worktree = {}
                    continue

                if line.startswith("worktree "):
                    current_worktree["path"] = line.split(" ", 1)[1]
                elif line.startswith("branch "):
                    current_worktree["branch"] = line.split(" ", 1)[1]
                elif line.startswith("HEAD "):
                    current_worktree["commit"] = line.split(" ", 1)[1]

            if current_worktree:
                worktrees.append(current_worktree)

        return worktrees

    async def get_worktree_path(self, agent_id: str) -> Path | None:
        """获取worktree路径"""
        worktree_path = self.worktrees_dir / agent_id
        if worktree_path.exists():
            return worktree_path
        return None

    async def sync_worktree(self, agent_id: str, source_branch: str = "main") -> bool:
        """同步worktree与源分支"""
        worktree_path = await self.get_worktree_path(agent_id)

        if not worktree_path:
            raise RuntimeError(f"Worktree for agent {agent_id} not found")

        # 获取最新变更
        await self._run_git(["git", "fetch", "origin", source_branch], cwd=worktree_path)

        # 合并
        result = await self._run_git(
            ["git", "merge", f"origin/{source_branch}"], cwd=worktree_path
        )

        return result.returncode == 0

    async def commit_changes(
        self,
        agent_id: str,
        message: str,
        files: list[str] | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> bool:
        """在worktree中提交更改"""
        worktree_path = await self.get_worktree_path(agent_id)

        if not worktree_path:
            raise RuntimeError(f"Worktree for agent {agent_id} not found")

        # 设置作者（如果提供）
        if author_name:
            await self._run_git(
                ["git", "config", "user.name", author_name], cwd=worktree_path
            )
        if author_email:
            await self._run_git(
                ["git", "config", "user.email", author_email], cwd=worktree_path
            )

        # 添加文件
        if files:
            for file_path in files:
                await self._run_git(["git", "add", file_path], cwd=worktree_path)
        else:
            await self._run_git(["git", "add", "-A"], cwd=worktree_path)

        # 检查是否有更改需要提交
        status_result = await self._run_git(
            ["git", "status", "--porcelain"], cwd=worktree_path
        )
        if not status_result.stdout.strip():
            return False

        # 提交
        result = await self._run_git(
            ["git", "commit", "-m", message], cwd=worktree_path
        )

        return result.returncode == 0

    async def push_worktree_branch(self, agent_id: str, remote: str = "origin") -> bool:
        """推送worktree分支到远程"""
        worktree_path = await self.get_worktree_path(agent_id)

        if not worktree_path:
            raise RuntimeError(f"Worktree for agent {agent_id} not found")

        # 获取当前分支
        result = await self._run_git(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path
        )
        branch = result.stdout.strip()

        # 推送
        result = await self._run_git(
            ["git", "push", remote, branch], cwd=worktree_path
        )

        return result.returncode == 0

    async def merge_branch_to_main(
        self, branch: str, message: str | None = None, no_ff: bool = True
    ) -> bool:
        """将分支合并到main"""
        # 确保在main分支
        await self._run_git(["git", "checkout", "main"])
        await self.ensure_main_updated()

        # 构建合并消息
        if message is None:
            message = f"Merge {branch}: 完成协作任务\n\n🤖 Generated with iCCC Worktree Manager"

        # 执行合并
        cmd = ["git", "merge", branch]
        if no_ff:
            cmd.extend(["--no-ff", "-m", message])

        result = await self._run_git(cmd)

        if result.returncode == 0:
            # 发布事件
            await self.event_bus.publish_event(
                WorktreeEventType.BRANCH_MERGED,
                {"branch": branch, "message": message},
                source_cli="worktree-manager",
            )

        return result.returncode == 0

    async def merge_all_worktree_branches(
        self, skip_branches: list[str] | None = None
    ) -> dict[str, bool]:
        """合并所有worktree分支到main

        Args:
            skip_branches: 要跳过的分支列表

        Returns:
            各分支的合并结果
        """
        skip_branches = skip_branches or ["main", "HEAD"]
        results: dict[str, bool] = {}

        worktrees = await self.list_worktrees()

        for worktree in worktrees:
            path = Path(worktree.get("path", ""))

            # 跳过main和特殊分支
            branch = worktree.get("branch", "")
            if any(skip in branch for skip in skip_branches):
                continue

            # 跳过非worktree分支
            if str(self.worktrees_dir) not in str(path):
                continue

            # 获取agent_id
            agent_id = path.name

            # 验证worktree是否已完成（通过检查README状态）
            if await self._is_worktree_completed(path):
                result = await self.merge_branch_to_main(
                    branch, message=f"Merge {branch}: Worker {agent_id} 完成协作任务"
                )
                results[agent_id] = result

        return results

    async def _is_worktree_completed(self, worktree_path: Path) -> bool:
        """检查worktree是否标记为完成"""
        readme_path = worktree_path / "README.md"
        if not readme_path.exists():
            return False

        content = readme_path.read_text()
        return "状态: 完成" in content or "**状态**: completed" in content

    async def cleanup_all_worktrees(
        self, keep_main: bool = True, force: bool = False
    ) -> list[str]:
        """清理所有worktree

        Args:
            keep_main: 是否保留main分支的worktree
            force: 是否强制删除

        Returns:
            已删除的worktree列表
        """
        deleted: list[str] = []
        worktrees = await self.list_worktrees()

        for worktree in worktrees:
            path = Path(worktree.get("path", ""))

            # 跳过main
            if keep_main and path == self.project_dir:
                continue

            # 检查是否是我们的worktree
            if str(self.worktrees_dir) in str(path):
                agent_id = path.name
                await self.remove_worktree(agent_id)
                deleted.append(agent_id)

        # 清理过期元数据
        await self._run_git(["git", "worktree", "prune"])

        return deleted

    async def publish_task_progress(
        self,
        agent_id: str,
        task_id: str,
        progress: int,
        status: TaskStatus,
        completed_items: list[str] | None = None,
        current_items: list[str] | None = None,
        pending_items: list[str] | None = None,
        problems: list[dict] | None = None,
    ) -> None:
        """发布任务进度事件"""
        worktree_path = await self.get_worktree_path(agent_id)

        data = {
            "task_id": task_id,
            "agent_id": agent_id,
            "worktree": str(worktree_path) if worktree_path else None,
            "progress": progress,
            "status": status.value,
            "timestamp": datetime.now().isoformat(),
            "completed_items": completed_items or [],
            "current_items": current_items or [],
            "pending_items": pending_items or [],
            "problems": problems or [],
        }

        await self.event_bus.publish_event(
            WorktreeEventType.TASK_PROGRESS,
            data,
            source_cli=agent_id,
        )

    async def get_worktree_status(self, agent_id: str) -> dict[str, Any]:
        """获取worktree的详细状态"""
        worktree_path = await self.get_worktree_path(agent_id)

        if not worktree_path:
            return {"error": f"Worktree {agent_id} not found"}

        status: dict[str, Any] = {
            "agent_id": agent_id,
            "path": str(worktree_path),
        }

        # 获取Git状态
        result = await self._run_git(
            ["git", "status", "--short"], cwd=worktree_path
        )
        modified_files = [
            line for line in result.stdout.strip().split("\n") if line
        ]
        status["modified_files_count"] = len(modified_files)
        status["modified_files"] = modified_files[:10]  # 只保留前10个

        # 获取最新提交
        result = await self._run_git(
            ["git", "log", "--oneline", "-1"], cwd=worktree_path
        )
        status["latest_commit"] = result.stdout.strip()

        # 获取当前分支
        result = await self._run_git(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree_path
        )
        status["branch"] = result.stdout.strip()

        # 解析README进度
        readme_path = worktree_path / "README.md"
        if readme_path.exists():
            progress_info = self._parse_readme_progress(readme_path)
            status["progress"] = progress_info

        return status

    def _parse_readme_progress(self, readme_path: Path) -> dict[str, Any]:
        """解析README中的进度信息"""
        content = readme_path.read_text()

        # 提取状态
        status = "unknown"
        if "状态: 进行中" in content or "**状态**: in_progress" in content:
            status = "in_progress"
        elif "状态: 阻塞" in content or "**状态**: blocked" in content:
            status = "blocked"
        elif "状态: 完成" in content or "**状态**: completed" in content:
            status = "completed"
        elif "**状态**: pending" in content:
            status = "pending"

        # 提取进度百分比
        import re

        progress_match = re.search(r"进度[:：]\s*(\d+)%", content)
        progress = int(progress_match.group(1)) if progress_match else 0

        return {"status": status, "progress": progress}

    async def generate_progress_report(self, output_path: Path | None = None) -> dict:
        """生成进度报告

        Args:
            output_path: 可选的输出文件路径

        Returns:
            报告数据字典
        """
        worktrees = await self.list_worktrees()

        statuses = []
        for worktree in worktrees:
            path = Path(worktree.get("path", ""))

            # 只处理我们的worktree
            if str(self.worktrees_dir) not in str(path):
                continue

            agent_id = path.name
            status = await self.get_worktree_status(agent_id)
            statuses.append(status)

        # 统计
        completed = sum(1 for s in statuses if s.get("progress", {}).get("status") == "completed")
        running = sum(1 for s in statuses if s.get("progress", {}).get("status") == "in_progress")
        blocked = sum(1 for s in statuses if s.get("progress", {}).get("status") == "blocked")
        total = len(statuses)

        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_worktrees": total,
                "completed": completed,
                "in_progress": running,
                "blocked": blocked,
                "completion_rate": (completed / total * 100) if total > 0 else 0,
                "average_progress": sum(s.get("progress", {}).get("progress", 0) for s in statuses) / total if total > 0 else 0,
            },
            "worktrees": statuses,
        }

        # 保存报告
        if output_path:
            output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

        return report


class TaskManager:
    """任务管理器 - 用于管理多个任务的分配和跟踪"""

    def __init__(self, manager: WorktreeManager):
        self.manager = manager
        self.tasks: dict[str, TaskInfo] = {}

    def create_task(
        self,
        task_id: str,
        task_name: str,
        branch_name: str,
        description: str,
        priority: TaskPriority,
        estimated_hours: float,
        acceptance_criteria: list[str],
        scope_included: list[str],
        scope_excluded: list[str],
    ) -> TaskInfo:
        """创建任务"""
        task = TaskInfo(
            task_id=task_id,
            task_name=task_name,
            branch_name=f"{self.manager.branch_prefix}{branch_name}",
            description=description,
            priority=priority,
            estimated_hours=estimated_hours,
            acceptance_criteria=acceptance_criteria,
            scope_included=scope_included,
            scope_excluded=scope_excluded,
        )
        self.tasks[task_id] = task
        return task

    async def assign_task(
        self,
        task_id: str,
        agent_id: str,
    ) -> tuple[Path, TaskInfo]:
        """分配任务给agent并创建worktree"""
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.assignee = agent_id
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now()

        # 创建worktree
        worktree_path = await self.manager.create_worktree(
            agent_id, branch=task.branch_name.replace(self.manager.branch_prefix, ""), task_info=task
        )

        # 发布任务分配事件
        await self.manager.event_bus.publish_event(
            WorktreeEventType.TASK_ASSIGNED,
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "worktree": str(worktree_path),
                "branch": task.branch_name,
            },
            source_cli="task-manager",
        )

        return worktree_path, task

    async def update_task_progress(
        self,
        agent_id: str,
        progress: int,
        completed_items: list[str] | None = None,
        current_items: list[str] | None = None,
        pending_items: list[str] | None = None,
        problem: dict | None = None,
    ) -> None:
        """更新任务进度"""
        # 找到对应的任务
        task = None
        for t in self.tasks.values():
            if t.assignee == agent_id:
                task = t
                break

        if not task:
            return

        task.progress = progress

        if problem:
            task.problems.append(problem)

        await self.manager.publish_task_progress(
            agent_id=agent_id,
            task_id=task.task_id,
            progress=progress,
            status=TaskStatus.IN_PROGRESS,
            completed_items=completed_items,
            current_items=current_items,
            pending_items=pending_items,
            problems=[problem] if problem else None,
        )

    async def complete_task(self, agent_id: str) -> None:
        """标记任务完成"""
        task = None
        for t in self.tasks.values():
            if t.assignee == agent_id:
                task = t
                break

        if not task:
            return

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.completed_at = datetime.now()

        await self.manager.publish_task_progress(
            agent_id=agent_id,
            task_id=task.task_id,
            progress=100,
            status=TaskStatus.COMPLETED,
        )

        # 发布完成事件
        await self.manager.event_bus.publish_event(
            WorktreeEventType.TASK_COMPLETED,
            {
                "task_id": task.task_id,
                "agent_id": agent_id,
                "completed_at": task.completed_at.isoformat(),
            },
            source_cli="task-manager",
        )

    def get_task_status(self, task_id: str) -> TaskInfo | None:
        """获取任务状态"""
        return self.tasks.get(task_id)


async def create_worktrees_from_file(
    project_dir: str,
    task_file: str,
    worktrees_dir: str | None = None,
    redis_url: str | None = None,
) -> dict[str, tuple[Path, TaskInfo]]:
    """从任务文件创建多个worktree

    Args:
        project_dir: 项目根目录
        task_file: 任务文件路径（格式：TASK_NAME,BRANCH_NAME,DESCRIPTION）
        worktrees_dir: worktree目录
        redis_url: Redis URL

    Returns:
        agent_id到(worktree_path, task_info)的映射
    """
    event_bus = WorktreeEventBus(redis_url)
    await event_bus.connect()

    manager = WorktreeManager(
        project_dir=project_dir,
        worktrees_dir=worktrees_dir,
        event_bus=event_bus,
    )

    task_manager = TaskManager(manager)

    # 确保main分支已更新
    await manager.ensure_main_updated()

    results: dict[str, tuple[Path, TaskInfo]] = {}

    # 读取任务文件
    task_path = Path(task_file)
    if not task_path.exists():
        raise FileNotFoundError(f"Task file not found: {task_file}")

    lines = task_path.read_text().strip().split("\n")
    line_num = 0

    for line in lines:
        line_num += 1

        # 跳过注释和空行
        if line.strip().startswith("#") or not line.strip():
            continue

        # 解析任务信息 (格式: TASK_NAME,BRANCH_NAME,DESCRIPTION)
        parts = line.split(",", 2)
        if len(parts) < 3:
            continue

        task_name = parts[0].strip()
        branch_name = parts[1].strip()
        description = parts[2].strip()

        agent_id = f"worker-{line_num}"

        # 创建任务
        task = task_manager.create_task(
            task_id=f"task-{line_num:03d}",
            task_name=task_name,
            branch_name=branch_name,
            description=description,
            priority=TaskPriority.HIGH,
            estimated_hours=4.0,
            acceptance_criteria=[
                f"完成{description}的功能开发",
                "编写单元测试并通过",
                "更新相关文档",
            ],
            scope_included=["代码开发", "测试编写", "文档编写"],
            scope_excluded=["修改其他模块的代码", "修改项目配置"],
        )

        # 分配任务并创建worktree
        worktree_path, task_info = await task_manager.assign_task(task.task_id, agent_id)

        results[agent_id] = (worktree_path, task_info)

    return results


# ==================== Bash脚本助手 ====================

def generate_create_worktrees_script(
    project_root: str = "/opt/iflow/iccc",
    worktree_base: str = "/opt/claude",
    branch_prefix: str = "iccc-",
) -> str:
    """生成create_worktrees.sh脚本"""
    return f'''#!/bin/bash
# create_worktrees.sh - 创建多个Worktree用于多CLI协作
# 由iCCC Worktree Manager生成

set -e  # 遇到错误立即退出

PROJECT_ROOT="{project_root}"
WORKTREE_BASE="{worktree_base}"
BRANCH_PREFIX="{branch_prefix}"

TASK_FILE="${{1:-tasks.txt}}"

if [ ! -f "$TASK_FILE" ]; then
    echo "错误: 任务文件不存在: $TASK_FILE"
    echo "用法: ./create_worktrees.sh <任务文件>"
    exit 1
fi

echo "=== iCCC Worktree 创建工具 ==="
echo "项目根目录: $PROJECT_ROOT"
echo "任务文件: $TASK_FILE"
echo ""

cd "$PROJECT_ROOT"

# 确保主分支是最新的
echo "步骤1: 更新主分支"
git checkout main
git pull origin main
echo ""

# 读取任务列表并创建Worktree
echo "步骤2: 创建Worktree"
LINE_NUM=0
while IFS= read -r line || [ -n "$line" ]; do
    LINE_NUM=$((LINE_NUM + 1))

    # 跳过注释和空行
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "${{line// }}" ]] && continue

    # 解析任务信息 (格式: TASK_NAME,BRANCH_NAME,DESCRIPTION)
    TASK_NAME=$(echo "$line" | cut -d',' -f1)
    BRANCH_NAME=$(echo "$line" | cut -d',' -f2)
    DESCRIPTION=$(echo "$line" | cut -d',' -f3-)

    WORKTREE_PATH="${{WORKTREE_BASE}}/iccc_${{TASK_NAME}}"

    echo "创建Worktree #$LINE_NUM: $TASK_NAME"
    echo "  路径: $WORKTREE_PATH"
    echo "  分支: ${{BRANCH_PREFIX}}${{BRANCH_NAME}}"
    echo "  描述: $DESCRIPTION"

    # 创建Worktree和新分支
    git worktree add -b "${{BRANCH_PREFIX}}${{BRANCH_NAME}}" "$WORKTREE_PATH"

    # 创建README
    cat > "$WORKTREE_PATH/README.md" <<EOF
# iCCC项目 - $DESCRIPTION

## 任务目标
$DESCRIPTION

## 任务分配信息
- 分配给: Worker CLI-$LINE_NUM
- 分配时间: $(date '+%Y-%m-%d %H:%M')
- 主CLI: iCCC (Manager)
- 项目: iCCC
- 分支: ${{BRANCH_PREFIX}}${{BRANCH_NAME}}

## 验收标准
- [ ] 标准1: [具体描述]
- [ ] 标准2: [具体描述]
- [ ] 标准3: [具体描述]

## 工作范围
### 本Worktree范围内
- ✅ 代码开发
- ✅ 测试编写
- ✅ 文档编写

### 超出本Worktree范围（需要请示主CLI）
- ⚠️ 修改其他模块的代码
- ⚠️ 修改项目配置

## 优先级
🔴 高

## 预计工作量
- 总计: X小时

## 预计完成时间
T+Xh

## 问题请示流程
如果遇到以下情况，请向主CLI请示：
1. 需要修改其他Worktree的文件
2. 需要调整任务优先级
3. 需要额外的资源或协助

## 进度更新
### T+0h（任务开始）
- 状态: 任务理解中
- 进度: 0%

EOF

    echo "  ✅ README创建完成"
    echo ""

done < "$TASK_FILE"

# 验证所有Worktree
echo "步骤3: 验证Worktree创建"
git worktree list

echo ""
echo "=== Worktree创建完成 ==="
echo "总计创建: $LINE_NUM 个Worktree"
echo "下一步: 为每个Worker CLI提供对应的Worktree路径和分支信息"
'''


def generate_monitor_worktrees_script(
    project_root: str = "/opt/iflow/iccc",
    worktree_base: str = "/opt/claude",
) -> str:
    """生成monitor_worktrees.sh脚本"""
    return f'''#!/bin/bash
# monitor_worktrees.sh - 监控所有Worktree的状态
# 由iCCC Worktree Manager生成

set -e

PROJECT_ROOT="{project_root}"
WORKTREE_BASE="{worktree_base}"

cd "$PROJECT_ROOT"

echo "=== iCCC Worktree 状态监控 ==="
echo "监控时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 列出所有Worktree
echo "1. Worktree列表:"
git worktree list
echo ""

# 检查每个Worktree的未提交修改
echo "2. 各Worktree文件修改统计:"
for worktree in "$WORKTREE_BASE"/iccc_*; do
    if [ -d "$worktree" ] && [ -d "$worktree/.git" ]; then
        echo ""
        echo "=== $(basename "$worktree") ==="
        cd "$worktree"

        MODIFIED=$(git status --short 2>/dev/null | wc -l)
        echo "  未提交文件数: $MODIFIED"

        LATEST_COMMIT=$(git log --oneline -1 2>/dev/null)
        echo "  最新提交: $LATEST_COMMIT"

        # 检查README进度更新
        if [ -f "README.md" ]; then
            if grep -q "状态: 进行中" README.md 2>/dev/null; then
                echo "  状态: 🔄 进行中"
            elif grep -q "状态: 阻塞" README.md 2>/dev/null; then
                echo "  状态: ⚠️ 阻塞"
            elif grep -q "状态: 完成" README.md 2>/dev/null; then
                echo "  状态: ✅ 完成"
            fi
        fi
    fi
done

echo ""
echo "=== 监控完成 ==="
'''


def generate_merge_cleanup_script(
    project_root: str = "/opt/iflow/iccc",
    worktree_base: str = "/opt/claude",
    branch_prefix: str = "iccc-",
) -> str:
    """生成merge_and_cleanup.sh脚本"""
    return f'''#!/bin/bash
# merge_and_cleanup.sh - 合并所有Worktree分支并清理
# 由iCCC Worktree Manager生成

set -e

PROJECT_ROOT="{project_root}"
WORKTREE_BASE="{worktree_base}"
BRANCH_PREFIX="{branch_prefix}"

cd "$PROJECT_ROOT"

echo "=== iCCC Worktree 合并与清理工具 ==="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 步骤1: 切换到main分支并更新
echo "步骤1: 切换到main分支并更新"
git checkout main
git pull origin main
echo ""

# 步骤2: 收集所有Worktree分支
echo "步骤2: 收集Worktree分支"
WORKTREE_BRANCHES=()
for worktree in "$WORKTREE_BASE"/iccc_*; do
    if [ -d "$worktree" ] && [ -d "$worktree/.git" ]; then
        cd "$worktree"
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        WORKTREE_BRANCHES+=("$CURRENT_BRANCH")
        echo "  - $(basename "$worktree"): $CURRENT_BRANCH"
    fi
done
echo ""

# 步骤3: 验证每个Worktree已完成
echo "步骤3: 验证Worktree完成状态"
for branch in "${{WORKTREE_BRANCHES[@]}}"; do
    echo "  检查分支: $branch"
done
echo ""

# 步骤4: 合并所有分支
echo "步骤4: 合并所有分支到main"
for branch in "${{WORKTREE_BRANCHES[@]}}"; do
    echo "  合并: $branch"

    MERGE_MESSAGE="Merge $branch: 完成协作任务

- 合并来自Worker CLI的工作成果
- 经过测试验证
- 符合项目标准

🤖 Generated with iCCC Worktree Manager
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

    git merge "$branch" --no-ff -m "$MERGE_MESSAGE" || {{
        echo "  ⚠️  合并冲突，需要手动解决: $branch"
        echo "  解决冲突后，请运行: git merge --continue"
        exit 1
    }}
done
echo ""

# 步骤5: 推送到远程
echo "步骤5: 推送到远程"
git push origin main
echo ""

# 步骤6: 清理Worktree
echo "步骤6: 清理Worktree"
for worktree in "$WORKTREE_BASE"/iccc_*; do
    if [ -d "$worktree" ]; then
        WORKTREE_NAME=$(basename "$worktree")
        echo "  删除: $WORKTREE_NAME"
        git worktree remove "$worktree" --force 2>/dev/null || true
    fi
done
echo ""

# 步骤7: 验证清理结果
echo "步骤7: 验证清理结果"
git worktree list
echo ""

echo "=== 合并与清理完成 ==="
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
'''
