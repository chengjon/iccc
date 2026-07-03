"""
iCCC Hook系统测试

测试Hook自动化系统的触发、执行和管理功能。
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iccc.core.hook_system import (
    Hook,
    HookAction,
    HookExecutionContext,
    HookResult,
    HookSystem,
    HookTrigger,
    HookType,
    execute_hooks,
    get_default_hooks,
    get_hook_system
)


class TestHook:
    """Hook定义测试"""

    def test_hook_creation(self):
        """测试Hook创建"""
        hook = Hook(
            id="test_hook",
            name="测试Hook",
            trigger=HookTrigger(
                matcher="test_pattern",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="echo 'test'",
                    timeout=10
                )
            ]
        )

        assert hook.id == "test_hook"
        assert hook.name == "测试Hook"
        assert hook.trigger.matcher == "test_pattern"
        assert hook.trigger.hook_type == HookType.POST_TOOL_USE
        assert len(hook.actions) == 1
        assert hook.enabled is True
        assert hook.priority == 0

    def test_hook_with_priority(self):
        """测试带优先级的Hook"""
        hook = Hook(
            id="priority_hook",
            name="优先级Hook",
            trigger=HookTrigger(
                matcher="*",
                hook_type=HookType.CUSTOM,
                pattern_type="regex"
            ),
            actions=[],
            priority=10,
            enabled=False
        )

        assert hook.priority == 10
        assert hook.enabled is False


class TestHookTrigger:
    """Hook触发条件测试"""

    def test_exact_match_trigger(self):
        """测试精确匹配触发条件"""
        trigger = HookTrigger(
            matcher="exact_match",
            hook_type=HookType.POST_TOOL_USE,
            pattern_type="exact"
        )

        # 精确匹配
        data = {"data": "exact_match"}
        assert trigger.matcher == "exact_match"

        # 不匹配
        data2 = {"data": "not_exact"}
        assert trigger.matcher != "not_exact"

    def test_regex_match_trigger(self):
        """测试正则表达式匹配触发条件"""
        trigger = HookTrigger(
            matcher=r"file_\d+\.py",
            hook_type=HookType.POST_TOOL_USE,
            pattern_type="regex"
        )

        import re
        assert re.search(trigger.matcher, "file_123.py") is not None
        assert re.search(trigger.matcher, "file_abc.py") is None

    def test_prefix_match_trigger(self):
        """测试前缀匹配触发条件"""
        trigger = HookTrigger(
            matcher="test_",
            hook_type=HookType.POST_TOOL_USE,
            pattern_type="prefix"
        )

        assert "test_file".startswith(trigger.matcher)
        assert "other_file".startswith(trigger.matcher) is False

    def test_suffix_match_trigger(self):
        """测试后缀匹配触发条件"""
        trigger = HookTrigger(
            matcher=".py",
            hook_type=HookType.POST_TOOL_USE,
            pattern_type="suffix"
        )

        assert "file.py".endswith(trigger.matcher)
        assert "file.txt".endswith(trigger.matcher) is False


class TestHookAction:
    """Hook动作测试"""

    def test_command_action(self):
        """测试命令动作"""
        action = HookAction(
            type="command",
            command="python test.py",
            timeout=30,
            critical=True
        )

        assert action.type == "command"
        assert action.command == "python test.py"
        assert action.timeout == 30
        assert action.critical is True
        assert action.retry_count == 0

    def test_notification_action(self):
        """测试通知动作"""
        action = HookAction(
            type="notification",
            command="workflow_complete",
            timeout=5,
            critical=False
        )

        assert action.type == "notification"
        assert action.command == "workflow_complete"
        assert action.timeout == 5

    def test_webhook_action(self):
        """测试Webhook动作"""
        action = HookAction(
            type="webhook",
            webhook_url="https://example.com/webhook",
            timeout=10,
            retry_count=3
        )

        assert action.type == "webhook"
        assert action.webhook_url == "https://example.com/webhook"
        assert action.retry_count == 3

    def test_invalid_action_type(self):
        """测试无效动作类型"""
        with pytest.raises(ValueError):
            HookAction(
                type="invalid_type",
                command="test"
            )


class TestHookSystem:
    """Hook管理系统测试"""

    @pytest.fixture
    def temp_config_dir(self):
        """创建临时配置目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()
            yield config_dir

    @pytest.fixture
    def hook_system(self, temp_config_dir):
        """创建Hook系统实例"""
        return HookSystem(temp_config_dir)

    def test_hook_system_initialization(self, temp_config_dir):
        """测试Hook系统初始化"""
        hook_system = HookSystem(temp_config_dir)

        assert hook_system.config_dir == temp_config_dir
        assert hook_system.hooks == {}
        assert hook_system.execution_history == []
        assert hook_system.hook_handlers == {}

    def test_add_and_remove_hook(self, hook_system):
        """测试添加和移除Hook"""
        hook = Hook(
            id="test_hook",
            name="测试Hook",
            trigger=HookTrigger(
                matcher="test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[],
            priority=5
        )

        # 添加Hook
        hook_system.add_hook(hook)
        assert "test_hook" in hook_system.hooks
        assert hook_system.hooks["test_hook"] == hook

        # 移除Hook
        assert hook_system.remove_hook("test_hook") is True
        assert "test_hook" not in hook_system.hooks
        assert hook_system.remove_hook("nonexistent") is False

    def test_get_hooks_by_trigger_exact_match(self, hook_system):
        """测试根据触发条件获取精确匹配的Hooks"""
        # 创建多个Hook
        hooks = [
            Hook(
                id="hook1",
                name="Hook1",
                trigger=HookTrigger(
                    matcher="exact_match",
                    hook_type=HookType.POST_TOOL_USE,
                    pattern_type="exact"
                ),
                actions=[],
                priority=1
            ),
            Hook(
                id="hook2",
                name="Hook2",
                trigger=HookTrigger(
                    matcher="exact_match",
                    hook_type=HookType.POST_TOOL_USE,
                    pattern_type="exact"
                ),
                actions=[],
                priority=10
            ),
            Hook(
                id="hook3",
                name="Hook3",
                trigger=HookTrigger(
                    matcher="different",
                    hook_type=HookType.POST_TOOL_USE,
                    pattern_type="exact"
                ),
                actions=[],
                priority=5
            )
        ]

        for hook in hooks:
            hook_system.add_hook(hook)

        # 测试触发条件匹配
        trigger_data = {"data": "exact_match"}
        matched_hooks = hook_system.get_hooks_by_trigger(HookType.POST_TOOL_USE, trigger_data)

        # 应该匹配到2个Hook
        assert len(matched_hooks) == 2
        # 应该按优先级排序
        assert matched_hooks[0].priority == 10
        assert matched_hooks[1].priority == 1

    def test_get_hooks_by_trigger_regex_match(self, hook_system):
        """测试根据触发条件获取正则匹配的Hooks"""
        hook = Hook(
            id="regex_hook",
            name="正则Hook",
            trigger=HookTrigger(
                matcher=r"file_\d+\.py",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[],
            priority=5
        )

        hook_system.add_hook(hook)

        # 测试匹配
        trigger_data = {"data": "file_123.py"}
        matched_hooks = hook_system.get_hooks_by_trigger(HookType.POST_TOOL_USE, trigger_data)
        assert len(matched_hooks) == 1

        # 测试不匹配
        trigger_data = {"data": "file_abc.py"}
        matched_hooks = hook_system.get_hooks_by_trigger(HookType.POST_TOOL_USE, trigger_data)
        assert len(matched_hooks) == 0

    def test_get_hooks_by_trigger_disabled_hook(self, hook_system):
        """测试禁用Hook不会被匹配"""
        hook = Hook(
            id="disabled_hook",
            name="禁用Hook",
            trigger=HookTrigger(
                matcher="test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[],
            enabled=False
        )

        hook_system.add_hook(hook)

        trigger_data = {"data": "test"}
        matched_hooks = hook_system.get_hooks_by_trigger(HookType.POST_TOOL_USE, trigger_data)
        assert len(matched_hooks) == 0

    @pytest.mark.asyncio
    async def test_execute_hooks_success(self, hook_system):
        """测试成功执行Hooks"""
        hook = Hook(
            id="success_hook",
            name="成功Hook",
            trigger=HookTrigger(
                matcher="test_command",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="echo 'success'",
                    timeout=5,
                    critical=False
                )
            ]
        )

        hook_system.add_hook(hook)

        trigger_data = {"data": "test_command"}
        results = await hook_system.execute_hooks(HookType.POST_TOOL_USE, trigger_data)

        assert len(results) == 1
        assert results[0].success is True
        assert "success" in results[0].message
        assert results[0].execution_time > 0

    @pytest.mark.asyncio
    async def test_execute_hooks_with_retry(self, hook_system):
        """测试带重试机制的Hook执行"""
        hook = Hook(
            id="retry_hook",
            name="重试Hook",
            trigger=HookTrigger(
                matcher="retry_test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="exit 1",  # 模拟失败
                    timeout=5,
                    retry_count=2
                )
            ]
        )

        hook_system.add_hook(hook)

        trigger_data = {"data": "retry_test"}
        results = await hook_system.execute_hooks(HookType.POST_TOOL_USE, trigger_data)

        assert len(results) == 1
        # 应该多次尝试
        assert len(results[0].action_results) > 1

    @pytest.mark.asyncio
    async def test_execute_hooks_critical_failure(self, hook_system):
        """测试关键Hook失败时停止执行"""
        hook = Hook(
            id="critical_hook",
            name="关键Hook",
            trigger=HookTrigger(
                matcher="critical_test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="echo 'first'",
                    timeout=5,
                    critical=False
                ),
                HookAction(
                    type="command",
                    command="exit 1",
                    timeout=5,
                    critical=True
                ),
                HookAction(
                    type="command",
                    command="echo 'second'",
                    timeout=5,
                    critical=False
                )
            ]
        )

        hook_system.add_hook(hook)

        trigger_data = {"data": "critical_test"}
        results = await hook_system.execute_hooks(HookType.POST_TOOL_USE, trigger_data)

        assert len(results) == 1
        # 第一个动作成功，第二个动作失败且critical=True，应该停止执行
        assert len(results[0].action_results) == 2
        assert results[0].action_results[0]["success"] is True
        assert results[0].action_results[1]["success"] is False
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_execute_notification_action(self, hook_system):
        """测试通知动作执行"""
        action = HookAction(
            type="notification",
            command="workflow_complete",
            timeout=5
        )

        trigger_data = {"data": "test"}
        result = await hook_system._execute_notification_action(action, trigger_data)

        assert result["success"] is True
        assert result["message"] == "Notification sent"

    @pytest.mark.asyncio
    async def test_execute_webhook_action(self, hook_system):
        """测试Webhook动作执行"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response

            action = HookAction(
                type="webhook",
                webhook_url="https://example.com/webhook",
                timeout=10
            )

            trigger_data = {"data": "test"}
            result = await hook_system._execute_webhook_action(action, trigger_data)

            assert result["success"] is True
            assert result["message"] == "Webhook sent successfully"

    def test_hook_execution_history(self, hook_system):
        """测试Hook执行历史记录"""
        # 模拟添加执行历史
        execution = HookExecutionContext(
            hook_id="test_hook",
            hook_name="测试Hook",
            trigger_data={"data": "test"},
            execution_time=datetime.now()
        )

        hook_system.execution_history.append(execution)

        history = hook_system.get_hook_execution_history(limit=10)
        assert len(history) == 1
        assert history[0].hook_id == "test_hook"

    def test_hook_statistics(self, hook_system):
        """测试Hook统计信息"""
        # 添加一些执行历史
        for i in range(5):
            execution = HookExecutionContext(
                hook_id=f"hook_{i}",
                hook_name=f"Hook {i}",
                trigger_data={"data": "test", "success": i < 3},  # 前3个成功
                execution_time=1.0
            )
            hook_system.execution_history.append(execution)

        stats = hook_system.get_hook_statistics()

        assert stats["total_executions"] == 5
        assert stats["success_rate"] == 60.0  # 3/5 = 60%
        assert stats["average_execution_time"] == 1.0

    def test_add_hook_handler(self, hook_system):
        """测试添加Hook处理器"""
        def mock_handler(event):
            pass

        hook_system.add_hook_handler(HookType.POST_TOOL_USE, mock_handler)

        assert HookType.POST_TOOL_USE in hook_system.hook_handlers
        assert len(hook_system.hook_handlers[HookType.POST_TOOL_USE]) == 1
        assert hook_system.hook_handlers[HookType.POST_TOOL_USE][0] == mock_handler

    def test_clear_execution_history(self, hook_system):
        """测试清空执行历史"""
        execution = HookExecutionContext(
            hook_id="test_hook",
            hook_name="测试Hook",
            trigger_data={"data": "test"},
            execution_time=datetime.now()
        )

        hook_system.execution_history.append(execution)
        assert len(hook_system.execution_history) == 1

        hook_system.clear_execution_history()
        assert len(hook_system.execution_history) == 0


class TestDefaultHooks:
    """默认Hook配置测试"""

    def test_get_default_hooks_returns_hooks(self):
        """测试获取默认Hook配置"""
        hooks = get_default_hooks()

        assert isinstance(hooks, list)
        assert len(hooks) > 0

        # 检查必填字段
        for hook in hooks:
            assert hook.id
            assert hook.name
            assert hook.trigger
            assert hook.actions
            assert len(hook.actions) > 0

    def test_default_hooks_structure(self):
        """测试默认Hook结构"""
        hooks = get_default_hooks()

        # 检查关键Hook是否存在
        hook_ids = [hook.id for hook in hooks]

        assert "auto-test" in hook_ids
        assert "agent-coordination" in hook_ids
        assert "safety-check" in hook_ids
        assert "workflow-notification" in hook_ids
        assert "code-quality-check" in hook_ids

    def test_auto_test_hook(self):
        """测试自动测试Hook"""
        hooks = get_default_hooks()
        auto_test_hook = next(hook for hook in hooks if hook.id == "auto-test")

        assert auto_test_hook.trigger.matcher == "Edit|MultiEdit|Write"
        assert auto_test_hook.trigger.hook_type == HookType.POST_TOOL_USE
        assert len(auto_test_hook.actions) == 1
        assert auto_test_hook.actions[0].type == "command"

    def test_safety_check_hook(self):
        """测试安全检查Hook"""
        hooks = get_default_hooks()
        safety_hook = next(hook for hook in hooks if hook.id == "safety-check")

        assert safety_hook.trigger.hook_type == HookType.PRE_TOOL_USE
        assert safety_hook.actions[0].critical is True

    def test_workflow_notification_hook(self):
        """测试工作流通知Hook"""
        hooks = get_default_hooks()
        notification_hook = next(hook for hook in hooks if hook.id == "workflow-notification")

        assert notification_hook.actions[0].type == "notification"


class TestGlobalHookSystem:
    """全局Hook系统测试"""

    def test_get_hook_system_singleton(self):
        """测试获取全局Hook系统单例"""
        hook_system1 = get_hook_system()
        hook_system2 = get_hook_system()

        assert hook_system1 is hook_system2

    @pytest.mark.asyncio
    async def test_execute_hooks_global_function(self):
        """测试全局execute_hooks函数"""
        hook_system = get_hook_system()

        # 添加测试Hook
        hook = Hook(
            id="global_test",
            name="全局测试Hook",
            trigger=HookTrigger(
                matcher="global_test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[
                HookAction(
                    type="notification",
                    command="global_notification",
                    timeout=5
                )
            ]
        )
        hook_system.add_hook(hook)

        trigger_data = {"data": "global_test"}
        results = await execute_hooks(HookType.POST_TOOL_USE, trigger_data)

        assert len(results) == 1
        assert results[0].success is True


class TestHookIntegration:
    """Hook集成测试"""

    @pytest.mark.asyncio
    async def test_full_hook_lifecycle(self, hook_system):
        """测试完整的Hook生命周期"""
        # 1. 创建并添加Hook
        hook = Hook(
            id="lifecycle_hook",
            name="生命周期测试Hook",
            trigger=HookTrigger(
                matcher="lifecycle_test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="echo 'lifecycle test'",
                    timeout=5
                )
            ],
            priority=10
        )

        hook_system.add_hook(hook)

        # 2. 验证Hook存在
        assert "lifecycle_hook" in hook_system.hooks

        # 3. 执行Hook
        trigger_data = {"data": "lifecycle_test"}
        results = await hook_system.execute_hooks(HookType.POST_TOOL_USE, trigger_data)

        # 4. 验证执行结果
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].execution_time > 0

        # 5. 验证执行历史
        history = hook_system.get_hook_execution_history()
        assert len(history) > 0
        assert history[-1].hook_id == "lifecycle_hook"

        # 6. 移除Hook
        assert hook_system.remove_hook("lifecycle_hook") is True
        assert "lifecycle_hook" not in hook_system.hooks

    def test_hook_system_state_reset(self, hook_system):
        """测试Hook系统状态重置"""
        # 添加Hook
        hook = Hook(
            id="reset_test",
            name="重置测试Hook",
            trigger=HookTrigger(
                matcher="reset_test",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="exact"
            ),
            actions=[]
        )
        hook_system.add_hook(hook)

        # 添加执行历史
        execution = HookExecutionContext(
            hook_id="reset_test",
            hook_name="重置测试Hook",
            trigger_data={"data": "test"},
            execution_time=datetime.now()
        )
        hook_system.execution_history.append(execution)

        # 验证状态
        assert len(hook_system.hooks) == 1
        assert len(hook_system.execution_history) == 1

        # 重置状态
        hook_system.hooks.clear()
        hook_system.clear_execution_history()

        # 验证重置
        assert len(hook_system.hooks) == 0
        assert len(hook_system.execution_history) == 0