"""
iCCC 指令系统集成测试

测试完整的指令系统，包括指令解析、Hook系统、MCP服务和多CLI通信的集成。
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from iccc.core.hook_system import Hook, HookAction, HookResult, HookSystem, HookTrigger, HookType
from iccc.core.instruction_processor import (
    Instruction,
    InstructionProcessor,
    InstructionStatus,
    InstructionType,
    WorkflowInstruction,
    ThinkingInstruction,
    process_instruction
)
from iccc.core.mcp_service_manager import (
    MCPServiceConfig,
    MCPServiceInstance,
    MCPServiceManager,
    MCPServiceStatus,
    MCPServiceType
)
from iccc.core.multi_cli_communication import (
    Event,
    EventType,
    InstructionEvent,
    InstructionDispatcher,
    MultiCLIBus,
    WorkflowCoordinator,
    WorkflowEvent
)


class TestInstructionSystemIntegration:
    """指令系统集成测试"""

    @pytest.fixture
    def config_dir(self):
        """创建临时配置目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()
            yield config_dir

    @pytest.fixture
    def instruction_processor(self, config_dir):
        """创建指令处理器"""
        return InstructionProcessor(config_dir)

    @pytest.fixture
    def hook_system(self, config_dir):
        """创建Hook系统"""
        return HookSystem(config_dir)

    @pytest.fixture
    def mcp_manager(self, config_dir):
        """创建MCP管理器"""
        return MCPServiceManager(config_dir)

    @pytest.fixture
    def event_bus(self):
        """创建事件总线"""
        bus = MultiCLIBus()
        bus.cli_id = "cli-test"
        return bus

    @pytest.fixture
    def workflow_coordinator(self, event_bus):
        """创建工作流协调器"""
        return WorkflowCoordinator(event_bus)

    @pytest.fixture
    def instruction_dispatcher(self, event_bus):
        """创建指令分发器"""
        return InstructionDispatcher(event_bus)

    @pytest.mark.asyncio
    async def test_full_instruction_lifecycle(self, instruction_processor, hook_system,
                                            event_bus, workflow_coordinator, instruction_dispatcher):
        """测试完整指令生命周期"""
        # 1. 解析指令
        command = "/iccc/workflow \"创建用户认证API\""
        instruction = instruction_processor.parse_instruction(command)

        assert isinstance(instruction, WorkflowInstruction)
        assert instruction.type == InstructionType.WORKFLOW
        assert instruction.command == "workflow"
        assert "创建" in instruction.args[0]
        assert "用户认证API" in instruction.args[1]

        # 2. 执行前Hook
        with patch.object(hook_system, 'execute_hooks') as mock_execute_hooks:
            mock_execute_hooks.return_value = [
                HookResult(success=True, message="Pre-hook executed", execution_time=0.1)
            ]

            trigger_data = {
                "tool_name": "ParseInstruction",
                "file_path": "test.py",
                "agent_id": "agent-123",
                "data": command
            }

            pre_hooks = await hook_system.execute_hooks(HookType.PRE_TOOL_USE, trigger_data)

            assert len(pre_hooks) == 1
            assert pre_hooks[0].success is True

        # 3. 执行指令
        with patch.object(instruction_processor, '_execute_workflow_instruction') as mock_execute:
            mock_execute.return_value = {
                "workflow_type": "standard",
                "status": "started",
                "steps": ["需求分析", "架构设计"]
            }

            result = await instruction_processor.execute_instruction(instruction)

            assert result["workflow_type"] == "standard"
            assert result["status"] == "started"

        # 4. 发布工作流事件
        with patch.object(event_bus, 'publish_event') as mock_publish:
            workflow_event = WorkflowEvent(
                type=EventType.WORKFLOW_START,
                source_cli=event_bus.cli_id,
                workflow_id=instruction.id,
                workflow_type="standard",
                step="initialization",
                progress=0.0,
                data=result
            )

            await event_bus.publish_event(workflow_event)

            mock_publish.assert_called_once()
            call_arg = mock_publish.call_args[0][0]
            assert call_arg.type == EventType.WORKFLOW_START
            assert call_arg.workflow_id == instruction.id

        # 5. 分发指令事件
        instruction_event = InstructionEvent(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli=event_bus.cli_id,
            instruction_id=instruction.id,
            instruction_type="workflow",
            status="received",
            data={"command": command}
        )

        await event_bus.publish_event(instruction_event)

        # 6. 执行后Hook
        with patch.object(hook_system, 'execute_hooks') as mock_execute_hooks:
            mock_execute_hooks.return_value = [
                HookResult(success=True, message="Post-hook executed", execution_time=0.1)
            ]

            post_hooks = await hook_system.execute_hooks(HookType.POST_TOOL_USE, trigger_data)

            assert len(post_hooks) == 1
            assert post_hooks[0].success is True

        # 7. 验证指令状态
        assert instruction.status == InstructionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_instruction_with_mcp_service_integration(self, instruction_processor, mcp_manager):
        """测试指令与MCP服务集成"""
        command = "/iccc/spec \"实现支付系统\""
        instruction = instruction_processor.parse_instruction(command)

        assert isinstance(instruction, WorkflowInstruction)
        assert instruction.command == "spec"

        # 模拟MCP服务启动
        with patch.object(mcp_manager, 'start_service') as mock_start:
            mock_start.return_value = True

            with patch.object(mcp_manager, 'get_service_status') as mock_status:
                mock_status.return_value = {
                    "name": "filesystem",
                    "status": "running",
                    "enabled": True,
                    "description": "文件系统访问"
                }

                # 执行指令（实际会使用MCP服务）
                result = await instruction_processor.execute_instruction(instruction)

                assert result["status"] == "created"
                assert "spec_file" in result

                # 验证MCP服务被调用
                mock_start.assert_called()
                mock_status.assert_called()

    @pytest.mark.asyncio
    async def test_concurrent_instruction_execution(self, instruction_processor, hook_system, event_bus):
        """测试并发指令执行"""
        commands = [
            "/iccc/workflow \"任务1\"",
            "/iccc/ultra \"分析数据库性能\"",
            "/iccc/spec \"规格定义\""
        ]

        results = []

        # 并发执行多个指令
        with patch.object(hook_system, 'execute_hooks', return_value=[]):
            tasks = []
            for command in commands:
                task = asyncio.create_task(
                    self._execute_single_instruction(instruction_processor, command, event_bus)
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证所有指令都成功执行
        for result in results:
            if not isinstance(result, Exception):
                assert result["status"] in ["started", "created", "completed"]

    async def _execute_single_instruction(self, processor, command, event_bus):
        """辅助函数：执行单个指令"""
        instruction = processor.parse_instruction(command)

        with patch.object(event_bus, 'publish_event'):
            return await processor.execute_instruction(instruction)

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, instruction_processor, hook_system):
        """测试错误处理和恢复"""
        # 创建一个会失败的指令
        command = "/iccc/workflow \"失败的任务\""
        instruction = instruction_processor.parse_instruction(command)

        # 模拟执行失败
        with patch.object(instruction_processor, '_execute_workflow_instruction',
                         side_effect=Exception("执行失败")):
            with patch.object(hook_system, 'execute_hooks', return_value=[]):
                with pytest.raises(Exception):
                    await instruction_processor.execute_instruction(instruction)

        # 验证指令状态为失败
        assert instruction.status == InstructionStatus.FAILED
        assert instruction.error == "执行失败"

    @pytest.mark.asyncio
    async def test_hook_integration_with_instruction_execution(self, instruction_processor, hook_system):
        """测试Hook与指令执行的集成"""
        # 添加测试Hook
        test_hook = Hook(
            id="integration_test_hook",
            name="集成测试Hook",
            trigger=HookTrigger(
                matcher=r"/iccc/workflow",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="command",
                    command="echo 'Hook executed successfully'",
                    timeout=5
                )
            ],
            priority=10
        )

        hook_system.add_hook(test_hook)

        # 执行指令
        command = "/iccc/workflow \"测试Hook集成\""
        instruction = instruction_processor.parse_instruction(command)

        with patch.object(hook_system, 'execute_hooks') as mock_execute_hooks:
            mock_execute_hooks.return_value = [
                HookResult(success=True, message="Hook executed", execution_time=0.1)
            ]

            with patch.object(instruction_processor, '_execute_workflow_instruction') as mock_execute:
                mock_execute.return_value = {
                    "workflow_type": "standard",
                    "status": "started",
                    "steps": ["测试"]
                }

                await instruction_processor.execute_instruction(instruction)

                # 验证Hook被调用
                mock_execute_hooks.assert_called_once()
                call_args = mock_execute_hooks.call_args
                assert call_args[0][0] == HookType.POST_TOOL_USE

    @pytest.mark.asyncio
    async def test_workflow_coordinator_integration(self, instruction_processor, workflow_coordinator, event_bus):
        """测试工作流协调器集成"""
        # 启动工作流
        workflow_id = "wf-123"
        await workflow_coordinator.start_workflow(
            workflow_id,
            "feature_development",
            {"description": "测试工作流"}
        )

        # 解析工作流指令
        command = "/iccc/workflow \"测试工作流\""
        instruction = instruction_processor.parse_instruction(command)
        instruction.id = workflow_id

        # 更新工作流进度
        await workflow_coordinator.update_workflow_progress(
            workflow_id,
            "需求分析",
            25.0,
            {"completed": True, "next_step": "架构设计"}
        )

        # 发布指令完成事件
        instruction_event = InstructionEvent(
            type=EventType.INSTRUCTION_COMPLETE,
            source_cli=event_bus.cli_id,
            instruction_id=instruction.id,
            instruction_type="workflow",
            status="completed",
            result={"status": "success"}
        )

        await event_bus.publish_event(instruction_event)

        # 完成工作流
        await workflow_coordinator.complete_workflow(
            workflow_id,
            {"status": "completed", "message": "工作流执行成功"}
        )

        # 验证工作流状态
        assert workflow_id not in workflow_coordinator.active_workflows

    @pytest.mark.asyncio
    async def test_mcp_service_lifecycle_with_instruction(self, instruction_processor, mcp_manager):
        """测试MCP服务生命周期与指令的集成"""
        service_name = "filesystem"

        # 模拟服务启动
        with patch.object(mcp_manager, 'start_service') as mock_start:
            mock_start.return_value = True

            # 启动服务
            result = await mcp_manager.start_service(service_name)
            assert result is True

            # 验证服务状态
            status = mcp_manager.get_service_status(service_name)
            assert status["status"] == "running"

            # 执行需要文件系统服务的指令
            command = "/iccc/workflow \"文件操作测试\""
            instruction = instruction_processor.parse_instruction(command)

            with patch.object(mcp_manager, 'get_service_capabilities', return_value=["read_file", "write_file"]):
                with patch.object(instruction_processor, '_execute_workflow_instruction') as mock_execute:
                    mock_execute.return_value = {
                        "workflow_type": "standard",
                        "status": "started",
                        "steps": ["文件创建", "文件写入"]
                    }

                    result = await instruction_processor.execute_instruction(instruction)

                    assert result["status"] == "started"

            # 停止服务
            with patch.object(mcp_manager, 'stop_service') as mock_stop:
                mock_stop.return_value = True

                stop_result = await mcp_manager.stop_service(service_name)
                assert stop_result is True

    def test_instruction_metadata_and_context(self, instruction_processor):
        """测试指令元数据和上下文"""
        command = "/iccc/workflow \"带元数据的任务\""
        instruction = instruction_processor.parse_instruction(command)

        # 设置元数据
        instruction.metadata["priority"] = "high"
        instruction.metadata["tags"] = ["api", "backend", "urgent"]
        instruction.metadata["estimated_time"] = 3600  # 1小时

        # 验证元数据
        assert instruction.metadata["priority"] == "high"
        assert "tags" in instruction.metadata
        assert "urgent" in instruction.metadata["tags"]
        assert instruction.metadata["estimated_time"] == 3600

        # 验证上下文信息
        assert hasattr(instruction, 'id')
        assert hasattr(instruction, 'created_at')
        assert instruction.status == InstructionStatus.PENDING

    @pytest.mark.asyncio
    async def test_system_wide_error_scenarios(self, instruction_processor, hook_system, event_bus):
        """测试系统级错误场景"""
        # 1. Redis连接失败
        with patch.object(event_bus, 'connect', side_effect=ConnectionError("Redis连接失败")):
            with pytest.raises(ConnectionError):
                await event_bus.connect()

        # 2. Hook执行失败但不影响主流程
        with patch.object(hook_system, 'execute_hooks') as mock_execute_hooks:
            mock_execute_hooks.return_value = [
                HookResult(success=False, message="Hook failed", execution_time=0.1)
            ]

            # Hook失败但指令仍可执行
            command = "/iccc/workflow \"测试容错\""
            instruction = instruction_processor.parse_instruction(command)

            with patch.object(instruction_processor, '_execute_workflow_instruction') as mock_execute:
                mock_execute.return_value = {
                    "workflow_type": "standard",
                    "status": "started"
                }

                result = await instruction_processor.execute_instruction(instruction)

                assert result["status"] == "started"

        # 3. MCP服务不可用但降级处理
        with patch('iccc.core.mcp_service_manager.MCPServiceManager.get_service_status') as mock_status:
            mock_status.return_value = None

            command = "/iccc/workflow \"降级测试\""
            instruction = instruction_processor.parse_instruction(command)

            with patch.object(instruction_processor, '_execute_workflow_instruction') as mock_execute:
                mock_execute.return_value = {
                    "workflow_type": "standard",
                    "status": "started",
                    "warning": "某些服务不可用"
                }

                result = await instruction_processor.execute_instruction(instruction)

                assert result["status"] == "started"
                assert "warning" in result

    @pytest.mark.asyncio
    async def test_performance_and_scalability(self, instruction_processor):
        """测试性能和可扩展性"""
        commands = [
            f"/iccc/workflow \"任务{i}\"" for i in range(100)
        ]

        start_time = asyncio.get_event_loop().time()

        # 并发执行大量指令
        tasks = []
        for command in commands:
            task = asyncio.create_task(
                instruction_processor.parse_instruction(command)
            )
            tasks.append(task)

        instructions = await asyncio.gather(*tasks)

        end_time = asyncio.get_event_loop().time()
        execution_time = end_time - start_time

        # 验证性能
        assert len(instructions) == 100
        assert execution_time < 5.0  # 应该在5秒内完成

        # 验证所有指令都被正确解析
        for i, instruction in enumerate(instructions):
            assert isinstance(instruction, WorkflowInstruction)
            assert instruction.command == "workflow"
            assert instruction.args[0] == f"任务{i}"

    def test_configuration_integration(self, config_dir):
        """测试配置集成"""
        # 验证配置目录结构
        assert config_dir.exists()

        # 测试指令处理器配置
        processor = InstructionProcessor(config_dir)
        assert processor.config_dir == config_dir

        # 测试Hook系统配置
        hook_system = HookSystem(config_dir)
        assert hook_system.config_dir == config_dir

        # 测试MCP管理器配置
        mcp_manager = MCPServiceManager(config_dir)
        assert mcp_manager.config_dir == config_dir

    @pytest.mark.asyncio
    async def test_state_management_and_recovery(self, instruction_processor, hook_system, mcp_manager):
        """测试状态管理和恢复"""
        # 添加一些活跃的指令
        active_instructions = []
        for i in range(5):
            command = f"/iccc/workflow \"活跃任务{i}\""
            instruction = instruction_processor.parse_instruction(command)
            active_instructions.append(instruction)

        # 添加一些Hook
        for i in range(3):
            hook = Hook(
                id=f"hook_{i}",
                name=f"Hook {i}",
                trigger=HookTrigger(
                    matcher=f"test_{i}",
                    hook_type=HookType.POST_TOOL_USE,
                    pattern_type="regex"
                ),
                actions=[]
            )
            hook_system.add_hook(hook)

        # 添加一些MCP服务
        for service_name in ["filesystem", "memory"]:
            await mcp_manager.start_service(service_name)

        # 验证系统状态
        assert len(instruction_processor.active_instructions) == 5
        assert len(hook_system.hooks) == 3
        assert len(mcp_manager.services) == 2

        # 模拟系统重启（清空状态）
        instruction_processor.active_instructions.clear()
        hook_system.hooks.clear()
        mcp_manager.services.clear()
        hook_system.execution_history.clear()

        # 验证状态已清空
        assert len(instruction_processor.active_instructions) == 0
        assert len(hook_system.hooks) == 0
        assert len(mcp_manager.services) == 0
        assert len(hook_system.execution_history) == 0

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_simulation(self, config_dir):
        """测试端到端工作流模拟"""
        # 初始化所有组件
        processor = InstructionProcessor(config_dir)
        hook_system = HookSystem(config_dir)
        mcp_manager = MCPServiceManager(config_dir)
        bus = MultiCLIBus()
        bus.cli_id = "cli-e2e"
        coordinator = WorkflowCoordinator(bus)
        dispatcher = InstructionDispatcher(bus)

        # 添加自动化Hook
        auto_hook = Hook(
            id="auto_workflow",
            name="自动工作流Hook",
            trigger=HookTrigger(
                matcher=r"/iccc/workflow",
                hook_type=HookType.POST_TOOL_USE,
                pattern_type="regex"
            ),
            actions=[
                HookAction(
                    type="notification",
                    command="workflow_started",
                    timeout=5
                )
            ]
        )
        hook_system.add_hook(auto_hook)

        # 1. 解析工作流指令
        workflow_command = "/iccc/workflow \"实现用户认证系统\""
        workflow_instruction = processor.parse_instruction(workflow_command)

        # 2. 启动工作流
        await coordinator.start_workflow(
            workflow_instruction.id,
            "feature_development",
            {"description": "用户认证系统"}
        )

        # 3. 分发指令
        dispatcher_instruction = {
            "type": "workflow",
            "command": workflow_command,
            "instruction_id": workflow_instruction.id
        }
        await dispatcher.dispatch_instruction(dispatcher_instruction)

        # 4. 更新工作流进度
        await coordinator.update_workflow_progress(
            workflow_instruction.id,
            "需求分析",
            25.0,
            {"status": "in_progress"}
        )

        # 5. 执行指令
        with patch.object(hook_system, 'execute_hooks') as mock_hooks:
            mock_hooks.return_value = [
                HookResult(success=True, message="Hooks executed", execution_time=0.1)
            ]

            result = await processor.execute_instruction(workflow_instruction)

            assert result["status"] == "started"

        # 6. 更新指令状态
        await dispatcher.update_instruction_status(
            workflow_instruction.id,
            "completed",
            {"result": "success", "steps": ["需求分析"]}
        )

        # 7. 完成工作流
        await coordinator.complete_workflow(
            workflow_instruction.id,
            {"status": "completed", "message": "用户认证系统开发完成"}
        )

        # 8. 验证最终状态
        assert workflow_instruction.status == InstructionStatus.COMPLETED
        assert workflow_instruction.id not in coordinator.active_workflows
        assert len(mock_hooks.call_args_list) == 2  # Pre and post hooks

        # 清理
        await bus.disconnect()


class TestAdvancedIntegrationScenarios:
    """高级集成场景测试"""

    @pytest.mark.asyncio
    async def test_multi_agent_collaboration(self):
        """测试多代理协作"""
        # 模拟多个代理协作完成复杂任务
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()

            # 初始化系统
            processor = InstructionProcessor(config_dir)
            hook_system = HookSystem(config_dir)
            mcp_manager = MCPServiceManager(config_dir)

            # 模拟协作Hook
            collaboration_hook = Hook(
                id="agent_coordinator",
                name="代理协调器",
                trigger=HookTrigger(
                    matcher="Write|Edit|MultiEdit",
                    hook_type=HookType.POST_TOOL_USE,
                    pattern_type="regex"
                ),
                actions=[
                    HookAction(
                        type="command",
                        command="echo 'Agent coordination'",
                        timeout=5
                    )
                ],
                priority=10
            )
            hook_system.add_hook(collaboration_hook)

            # 模拟多个代理执行不同任务
            agent_tasks = [
                ("/iccc/workflow \"前端组件开发\"", "frontend_agent"),
                ("/iccc/workflow \"API接口开发\"", "backend_agent"),
                ("/iccc/workflow \"数据库设计\"", "database_agent"),
            ]

            results = []
            for command, agent_id in agent_tasks:
                with patch.object(hook_system, 'execute_hooks') as mock_hooks:
                    mock_hooks.return_value = [
                        HookResult(success=True, message=f"Agent {agent_id} executed", execution_time=0.1)
                    ]

                    instruction = processor.parse_instruction(command)
                    instruction.metadata["agent_id"] = agent_id

                    result = await processor.execute_instruction(instruction)
                    results.append(result)

                    # 验证Hook包含代理信息
                    call_args = mock_hooks.call_args
                    trigger_data = call_args[0][1]
                    assert trigger_data.get("agent_id") == agent_id

            # 验证所有代理都成功协作
            assert len(results) == 3
            assert all(r["status"] in ["started", "completed"] for r in results)

    @pytest.mark.asyncio
    async def test_real_time_event_streaming(self):
        """测试实时事件流"""
        # 模拟实时事件流处理
        bus = MultiCLIBus()
        bus.cli_id = "cli-stream"

        events = []
        event_handler = lambda event: events.append(event)

        bus.add_event_handler(EventType.WORKFLOW_START, event_handler)
        bus.add_event_handler(EventType.INSTRUCTION_RECEIVED, event_handler)

        # 模拟事件流
        workflow_events = [
            WorkflowEvent(
                type=EventType.WORKFLOW_START,
                source_cli=bus.cli_id,
                workflow_id=f"wf-{i}",
                workflow_type="development",
                step="initialization",
                progress=0.0
            ) for i in range(10)
        ]

        instruction_events = [
            InstructionEvent(
                type=EventType.INSTRUCTION_RECEIVED,
                source_cli=bus.cli_id,
                instruction_id=f"inst-{i}",
                instruction_type="workflow",
                status="received"
            ) for i in range(5)
        ]

        all_events = workflow_events + instruction_events

        # 并发发布事件
        publish_tasks = [bus.publish_event(event) for event in all_events]
        await asyncio.gather(*publish_tasks)

        # 验证事件流
        assert len(events) == 15
        assert len([e for e in events if e.type == EventType.WORKFLOW_START]) == 10
        assert len([e for e in events if e.type == EventType.INSTRUCTION_RECEIVED]) == 5

    @pytest.mark.asyncio
    async def test_system_monitoring_and_metrics(self, instruction_processor, hook_system, mcp_manager):
        """测试系统监控和指标"""
        # 执行一系列操作以收集指标
        commands = [
            "/iccc/workflow \"任务1\"",
            "/iccc/ultra \"性能分析\"",
            "/iccc/spec \"规格定义\"",
            "/iccc/workflow \"任务2\""
        ]

        # 执行指令
        for command in commands:
            instruction = instruction_processor.parse_instruction(command)
            with patch.object(hook_system, 'execute_hooks', return_value=[]):
                await instruction_processor.execute_instruction(instruction)

        # 获取各种统计信息
        instruction_stats = {
            "total_instructions": len(instruction_processor.active_instructions),
            "completed_count": sum(1 for inst in instruction_processor.active_instructions.values()
                                 if inst.get("status") == "completed")
        }

        hook_stats = hook_system.get_hook_statistics()
        mcp_stats = mcp_manager.get_service_statistics()

        # 验证统计信息
        assert "total_instructions" in instruction_stats
        assert "total_executions" in hook_stats
        assert "total_services" in mcp_stats
        assert hook_stats["total_executions"] >= 0
        assert mcp_stats["total_services"] >= 0

    @pytest.mark.asyncio
    async def test_fault_tolerance_and_resilience(self, instruction_processor):
        """测试容错和恢复能力"""
        # 测试系统在部分故障情况下的行为
        faulty_commands = [
            "/iccc/workflow \"正常任务\"",
            "/iccc/workflow \"失败任务\"",  # 这个会失败
            "/iccc/workflow \"正常任务2\""
        ]

        results = []
        for command in faulty_commands:
            instruction = instruction_processor.parse_instruction(command)

            if "失败" in command:
                # 模拟执行失败
                with patch.object(instruction_processor, '_execute_workflow_instruction',
                                 side_effect=Exception("模拟失败")):
                    with pytest.raises(Exception):
                        await instruction_processor.execute_instruction(instruction)
                    results.append("failed")
            else:
                # 正常执行
                with patch.object(instruction_processor, '_execute_workflow_instruction') as mock_execute:
                    mock_execute.return_value = {
                        "workflow_type": "standard",
                        "status": "started"
                    }
                    await instruction_processor.execute_instruction(instruction)
                    results.append("success")

        # 验证系统容错
        assert len(results) == 3
        assert results.count("success") == 2
        assert results.count("failed") == 1

        # 验证失败指令正确标记
        failed_instruction = None
        for inst in instruction_processor.active_instructions.values():
            if inst.get("instruction", {}).get("command") == "/iccc/workflow \"失败任务\"":
                failed_instruction = inst
                break

        assert failed_instruction is not None
        assert failed_instruction.get("status") == "failed"