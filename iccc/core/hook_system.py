"""
iCCC Hook自动化系统

基于事件的Hook机制，支持自动化的工作流、代码检查、通知等功能。
"""

import asyncio
import json
import os
import subprocess
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class HookType(Enum):
    """Hook类型枚举"""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    WORKFLOW_START = "WorkflowStart"
    WORKFLOW_COMPLETE = "WorkflowComplete"
    WORKFLOW_FAILED = "WorkflowFailed"
    INSTRUCTION_RECEIVED = "InstructionReceived"
    INSTRUCTION_COMPLETE = "InstructionComplete"
    CUSTOM = "Custom"


class HookTrigger(BaseModel):
    """Hook触发条件"""
    matcher: str = Field(..., description="匹配模式")
    hook_type: HookType = Field(..., description="Hook类型")
    pattern_type: str = Field(default="regex", description="匹配模式类型: regex, exact, prefix, suffix")


class HookAction(BaseModel):
    """Hook动作"""
    type: str = Field(..., description="动作类型: command, notification, webhook")
    command: Optional[str] = Field(None, description="执行命令")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    timeout: int = Field(default=30, description="超时时间（秒）")
    critical: bool = Field(default=False, description="是否为关键Hook")
    retry_count: int = Field(default=0, description="重试次数")


class Hook(BaseModel):
    """Hook定义"""
    id: str = Field(..., description="Hook唯一标识")
    name: str = Field(..., description="Hook名称")
    trigger: HookTrigger = Field(..., description="触发条件")
    actions: List[HookAction] = Field(..., description="执行动作")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=0, description="执行优先级")
    description: Optional[str] = Field(None, description="描述")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class HookExecutionContext(BaseModel):
    """Hook执行上下文"""
    hook_id: str = Field(..., description="Hook ID")
    hook_name: str = Field(..., description="Hook名称")
    trigger_data: Dict[str, Any] = Field(default_factory=dict, description="触发数据")
    execution_time: datetime = Field(default_factory=datetime.now, description="执行时间")
    agent_id: Optional[str] = Field(None, description="Agent ID")
    file_path: Optional[str] = Field(None, description="文件路径")
    tool_name: Optional[str] = Field(None, description="工具名称")
    workflow_id: Optional[str] = Field(None, description="工作流ID")
    instruction_id: Optional[str] = Field(None, description="指令ID")


class HookResult(BaseModel):
    """Hook执行结果"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="执行消息")
    output: Optional[str] = Field(None, description="输出内容")
    execution_time: float = Field(..., description="执行时间（秒）")
    action_results: List[Dict[str, Any]] = Field(default_factory=list, description="各动作执行结果")


class HookSystem:
    """Hook管理系统"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.hooks: Dict[str, Hook] = {}
        self.execution_history: List[HookExecutionContext] = []
        self.hooks_dir = config_dir.parent / "scripts"
        self.event_bus = None

        # 注册的Hook处理器
        self.hook_handlers: Dict[HookType, List[Callable]] = {}

    def load_hooks_from_config(self) -> None:
        """从配置文件加载Hook"""
        hooks_config = self.config_dir / "hooks.json"
        if not hooks_config.exists():
            return

        try:
            with open(hooks_config, 'r', encoding='utf-8') as f:
                config = json.load(f)

            for hook_data in config.get("hooks", []):
                hook = Hook(**hook_data)
                self.hooks[hook.id] = hook

        except Exception as e:
            print(f"Error loading hooks config: {e}")

    def add_hook(self, hook: Hook) -> None:
        """添加Hook"""
        self.hooks[hook.id] = hook

    def remove_hook(self, hook_id: str) -> bool:
        """移除Hook"""
        if hook_id in self.hooks:
            del self.hooks[hook_id]
            return True
        return False

    def get_hooks_by_trigger(self, hook_type: HookType, trigger_data: Dict[str, Any]) -> List[Hook]:
        """根据触发条件获取匹配的Hooks"""
        matched_hooks = []

        for hook in self.hooks.values():
            if not hook.enabled:
                continue

            # 类型匹配
            if hook.trigger.hook_type != hook_type:
                continue

            # 模式匹配
            matcher = hook.trigger.matcher
            data = trigger_data.get("data", "")

            if hook.trigger.pattern_type == "exact":
                if data == matcher:
                    matched_hooks.append(hook)
            elif hook.trigger.pattern_type == "regex":
                import re
                if re.search(matcher, data):
                    matched_hooks.append(hook)
            elif hook.trigger.pattern_type == "prefix":
                if data.startswith(matcher):
                    matched_hooks.append(hook)
            elif hook.trigger.pattern_type == "suffix":
                if data.endswith(matcher):
                    matched_hooks.append(hook)

        # 按优先级排序
        matched_hooks.sort(key=lambda h: h.priority, reverse=True)
        return matched_hooks

    async def execute_hooks(self, hook_type: HookType, trigger_data: Dict[str, Any]) -> List[HookResult]:
        """执行匹配的Hooks"""
        matched_hooks = self.get_hooks_by_trigger(hook_type, trigger_data)

        results = []
        for hook in matched_hooks:
            try:
                result = await self._execute_hook(hook, trigger_data)
                results.append(result)
                self.execution_history.append(
                    HookExecutionContext(
                        hook_id=hook.id,
                        hook_name=hook.name,
                        trigger_data=trigger_data,
                        execution_time=datetime.now()
                    )
                )
            except Exception as e:
                print(f"Error executing hook {hook.id}: {e}")
                results.append(HookResult(
                    success=False,
                    message=str(e),
                    execution_time=0.0
                ))

        return results

    async def _execute_hook(self, hook: Hook, trigger_data: Dict[str, Any]) -> HookResult:
        """执行单个Hook"""
        start_time = time.time()
        action_results = []

        for action in hook.actions:
            try:
                if action.type == "command":
                    result = await self._execute_command_action(action, trigger_data)
                elif action.type == "notification":
                    result = await self._execute_notification_action(action, trigger_data)
                elif action.type == "webhook":
                    result = await self._execute_webhook_action(action, trigger_data)
                else:
                    result = {"success": False, "message": f"Unknown action type: {action.type}"}

                action_results.append(result)

                # 如果是关键Hook且执行失败，停止执行后续动作
                if action.critical and not result.get("success", False):
                    raise Exception(f"Critical action failed: {result.get('message', 'Unknown error')}")

            except Exception as e:
                action_results.append({
                    "success": False,
                    "message": str(e)
                })

                # 重试机制
                if action.retry_count > 0:
                    for retry in range(action.retry_count):
                        try:
                            if action.type == "command":
                                result = await self._execute_command_action(action, trigger_data)
                                action_results.append(result)
                                break
                            elif action.type == "notification":
                                result = await self._execute_notification_action(action, trigger_data)
                                action_results.append(result)
                                break
                            elif action.type == "webhook":
                                result = await self._execute_webhook_action(action, trigger_data)
                                action_results.append(result)
                                break
                        except Exception as retry_e:
                            action_results.append({
                                "success": False,
                                "message": f"Retry {retry + 1} failed: {str(retry_e)}"
                            })

        execution_time = time.time() - start_time

        # 判断整体执行结果
        all_success = all(result.get("success", False) for result in action_results)

        return HookResult(
            success=all_success,
            message=f"Hook executed successfully" if all_success else f"Hook execution failed",
            output=json.dumps(action_results, indent=2),
            execution_time=execution_time,
            action_results=action_results
        )

    async def _execute_command_action(self, action: HookAction, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行命令动作"""
        if not action.command:
            return {"success": False, "message": "No command specified"}

        # 构建环境变量
        env = os.environ.copy()
        env.update({
            "HOOK_DATA": json.dumps(trigger_data),
            "ICCC_HOOK_ID": trigger_data.get("hook_id", ""),
            "ICCC_AGENT_ID": trigger_data.get("agent_id", ""),
            "ICCC_FILE_PATH": trigger_data.get("file_path", ""),
            "ICCC_TOOL_NAME": trigger_data.get("tool_name", ""),
            "ICCC_WORKFLOW_ID": trigger_data.get("workflow_id", ""),
            "ICCC_INSTRUCTION_ID": trigger_data.get("instruction_id", "")
        })

        try:
            # 执行命令
            process = await asyncio.create_subprocess_shell(
                action.command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=action.timeout
            )

            stdout, stderr = await process.communicate()

            return {
                "success": process.returncode == 0,
                "message": "Command executed successfully" if process.returncode == 0 else "Command failed",
                "output": stdout.decode('utf-8'),
                "error": stderr.decode('utf-8'),
                "return_code": process.returncode
            }

        except asyncio.TimeoutError:
            return {"success": False, "message": "Command timeout"}
        except Exception as e:
            return {"success": False, "message": f"Command execution error: {str(e)}"}

    async def _execute_notification_action(self, action: HookAction, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行通知动作"""
        # 这里可以实现邮件、Slack、Discord等通知
        notification_data = {
            "hook_name": action.command,
            "trigger_data": trigger_data,
            "timestamp": datetime.now().isoformat()
        }

        print(f"📧 Notification: {json.dumps(notification_data, indent=2)}")

        return {"success": True, "message": "Notification sent"}

    async def _execute_webhook_action(self, action: HookAction, trigger_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行Webhook动作"""
        if not action.webhook_url:
            return {"success": False, "message": "No webhook URL specified"}

        import aiohttp

        try:
            payload = {
                "hook_name": action.command,
                "trigger_data": trigger_data,
                "timestamp": datetime.now().isoformat()
            }

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=action.timeout)) as session:
                async with session.post(action.webhook_url, json=payload) as response:
                    if response.status == 200:
                        return {"success": True, "message": "Webhook sent successfully"}
                    else:
                        return {"success": False, "message": f"Webhook failed with status {response.status}"}

        except Exception as e:
            return {"success": False, "message": f"Webhook error: {str(e)}"}

    def add_hook_handler(self, hook_type: HookType, handler: Callable) -> None:
        """添加Hook处理器"""
        if hook_type not in self.hook_handlers:
            self.hook_handlers[hook_type] = []
        self.hook_handlers[hook_type].append(handler)

    def get_hook_execution_history(self, limit: int = 100) -> List[HookExecutionContext]:
        """获取Hook执行历史"""
        return self.execution_history[-limit:]

    def clear_execution_history(self) -> None:
        """清空执行历史"""
        self.execution_history.clear()

    def get_hook_statistics(self) -> Dict[str, Any]:
        """获取Hook统计信息"""
        total_executions = len(self.execution_history)
        successful_executions = sum(1 for h in self.execution_history if "success" in str(h.trigger_data))

        return {
            "total_hooks": len(self.hooks),
            "enabled_hooks": sum(1 for h in self.hooks.values() if h.enabled),
            "total_executions": total_executions,
            "success_rate": (successful_executions / total_executions * 100) if total_executions > 0 else 0,
            "average_execution_time": sum(
                h.trigger_data.get("execution_time", 0) for h in self.execution_history[-100:]
            ) / min(total_executions, 100)
        }


# 预定义的Hook模板
def get_default_hooks() -> List[Hook]:
    """获取默认Hook配置"""
    return [
        Hook(
            id="auto-test",
            name="自动测试",
            trigger=HookTrigger(
                matcher="Edit|MultiEdit|Write",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="python iccc/hooks/scripts/auto_test.py",
                    timeout=30,
                    critical=False
                )
            ],
            description="代码修改后自动运行测试"
        ),
        Hook(
            id="agent-coordination",
            name="代理协调",
            trigger=HookTrigger(
                matcher="Edit|MultiEdit|Write",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="python iccc/hooks/scripts/agent_coordinator.py post",
                    timeout=45,
                    critical=False
                )
            ],
            description="代理间协调和事件发布"
        ),
        Hook(
            id="safety-check",
            name="安全检查",
            trigger=HookTrigger(
                matcher="*",
                hook_type=HookType.PRE_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="python iccc/hooks/scripts/safety_check.py",
                    timeout=10,
                    critical=True
                )
            ],
            description="执行安全检查"
        ),
        Hook(
            id="workflow-notification",
            name="工作流通知",
            trigger=HookTrigger(
                matcher="WorkflowStart|WorkflowComplete|WorkflowFailed",
                hook_type=HookType.CUSTOM,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="notification",
                    command="workflow_status",
                    timeout=5,
                    critical=False
                )
            ],
            description="工作流状态变更通知"
        ),
        Hook(
            id="code-quality-check",
            name="代码质量检查",
            trigger=HookTrigger(
                matcher="*",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="python -m flake8 --max-line-length=88 --extend-ignore=E203,W503",
                    timeout=15,
                    critical=False
                ),
                HookAction(
                    type="command",
                    command="python -m black --check --diff .",
                    timeout=20,
                    critical=False
                )
            ],
            priority=10,
            description="代码风格和质量检查"
        ),
        Hook(
            id="git-auto-commit",
            name="Git自动提交",
            trigger=HookTrigger(
                matcher="*",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="git add . && git commit -m \"Auto-commit: $(date)\"",
                    timeout=20,
                    critical=False
                )
            ],
            priority=5,
            description="自动提交代码变更"
        )
    ]


# 全局Hook系统实例
_hook_system: Optional[HookSystem] = None


def get_hook_system() -> HookSystem:
    """获取全局Hook系统"""
    global _hook_system
    if _hook_system is None:
        config_dir = Path(__file__).parent.parent / ".iccc" / "config"
        _hook_system = HookSystem(config_dir)
        _hook_system.load_hooks_from_config()
    return _hook_system


async def execute_hooks(hook_type: HookType, trigger_data: Dict[str, Any]) -> List[HookResult]:
    """执行Hooks的便捷函数"""
    hook_system = get_hook_system()
    return await hook_system.execute_hooks(hook_type, trigger_data)


# 使用示例
async def example_usage():
    """Hook系统使用示例"""
    # 获取Hook系统
    hook_system = get_hook_system()

    # 添加自定义Hook
    custom_hook = Hook(
        id="custom-webhook",
        name="自定义Webhook",
        trigger=HookTrigger(
            matcher="*",
            hook_type=HookType.POST_TOOL_USE,
            pattern_type="regex"
        ),
        actions=[
            HookAction(
                type="webhook",
                webhook_url="https://example.com/webhook",
                timeout=10,
                critical=False
            )
        ]
    )
    hook_system.add_hook(custom_hook)

    # 触发Hook
    trigger_data = {
        "tool_name": "Write",
        "file_path": "test.py",
        "agent_id": "agent-123",
        "data": "修改了测试文件"
    }

    results = await execute_hooks(HookType.POST_TOOL_USE, trigger_data)

    # 显示执行结果
    for result in results:
        print(f"Hook执行结果: {result.success} - {result.message}")

    # 显示统计信息
    stats = hook_system.get_hook_statistics()
    print(f"Hook统计: {stats}")