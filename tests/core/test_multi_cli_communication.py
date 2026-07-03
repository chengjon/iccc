"""
iCCC 多CLI通信系统测试

测试Redis Streams事件总线和多CLI协作机制。
"""

import asyncio
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import redis.asyncio as redis

from iccc.core.multi_cli_communication import (
    Event,
    EventType,
    EventPriority,
    InstructionEvent,
    InstructionDispatcher,
    MultiCLIBus,
    WorkflowCoordinator,
    WorkflowEvent,
    initialize_multi_cli_system
)


class TestEvent:
    """事件测试"""

    def test_event_creation(self):
        """测试事件创建"""
        event = Event(
            type=EventType.WORKFLOW_START,
            source_cli="cli-123",
            data={"workflow_id": "wf-456", "name": "Test Workflow"}
        )

        assert event.type == EventType.WORKFLOW_START
        assert event.source_cli == "cli-123"
        assert event.data == {"workflow_id": "wf-456", "name": "Test Workflow"}
        assert event.id is not None
        assert event.timestamp is not None
        assert event.priority == EventPriority.NORMAL
        assert event.target_cli is None
        assert event.correlation_id is None
        assert event.reply_to is None

    def test_event_with_optional_fields(self):
        """测试带可选字段的事件"""
        correlation_id = str(uuid.uuid4())
        reply_to = "response_stream"

        event = Event(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli="cli-123",
            target_cli="cli-456",
            priority=EventPriority.HIGH,
            data={"instruction": "test"},
            correlation_id=correlation_id,
            reply_to=reply_to
        )

        assert event.target_cli == "cli-456"
        assert event.priority == EventPriority.HIGH
        assert event.correlation_id == correlation_id
        assert event.reply_to == reply_to

    def test_event_auto_id_generation(self):
        """测试事件ID自动生成"""
        event1 = Event(type=EventType.WORKFLOW_START, source_cli="cli-123")
        event2 = Event(type=EventType.WORKFLOW_START, source_cli="cli-123")

        assert event1.id != event2.id
        assert len(event1.id) > 0

    def test_event_auto_timestamp(self):
        """测试事件时间戳自动生成"""
        event = Event(type=EventType.WORKFLOW_START, source_cli="cli-123")
        before = datetime.now()
        after = datetime.now()

        assert before <= event.timestamp <= after


class TestWorkflowEvent:
    """工作流事件测试"""

    def test_workflow_event_creation(self):
        """测试工作流事件创建"""
        event = WorkflowEvent(
            type=EventType.WORKFLOW_START,
            source_cli="cli-123",
            workflow_id="wf-456",
            workflow_type="feature_development",
            step="initialization",
            progress=0.0,
            data={"description": "User authentication system"}
        )

        assert isinstance(event, Event)
        assert event.type == EventType.WORKFLOW_START
        assert event.workflow_id == "wf-456"
        assert event.workflow_type == "feature_development"
        assert event.step == "initialization"
        assert event.progress == 0.0

    def test_workflow_event_progress_update(self):
        """测试工作流进度更新"""
        event = WorkflowEvent(
            type=EventType.WORKFLOW_PROGRESS,
            source_cli="cli-123",
            workflow_id="wf-456",
            workflow_type="feature_development",
            step="implementation",
            progress=50.0
        )

        assert event.progress == 50.0


class TestInstructionEvent:
    """指令事件测试"""

    def test_instruction_event_creation(self):
        """测试指令事件创建"""
        event = InstructionEvent(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli="cli-123",
            instruction_id="inst-789",
            instruction_type="workflow",
            status="received",
            result={"status": "ok"}
        )

        assert isinstance(event, Event)
        assert event.type == EventType.INSTRUCTION_RECEIVED
        assert event.instruction_id == "inst-789"
        assert event.instruction_type == "workflow"
        assert event.status == "received"
        assert event.result == {"status": "ok"}


class TestEventPriority:
    """事件优先级测试"""

    def test_priority_enum_values(self):
        """测试优先级枚举值"""
        assert EventPriority.LOW.value == 1
        assert EventPriority.NORMAL.value == 2
        assert EventPriority.HIGH.value == 3
        assert EventPriority.CRITICAL.value == 4

    def test_priority_ordering(self):
        """测试优先级排序"""
        assert EventPriority.LOW < EventPriority.NORMAL
        assert EventPriority.NORMAL < EventPriority.HIGH
        assert EventPriority.HIGH < EventPriority.CRITICAL


class TestEventType:
    """事件类型测试"""

    def test_event_type_enum_values(self):
        """测试事件类型枚举值"""
        assert EventType.WORKFLOW_START.value == "workflow_start"
        assert EventType.WORKFLOW_PROGRESS.value == "workflow_progress"
        assert EventType.WORKFLOW_COMPLETE.value == "workflow_complete"
        assert EventType.WORKFLOW_FAILED.value == "workflow_failed"

        assert EventType.INSTRUCTION_RECEIVED.value == "instruction_received"
        assert EventType.INSTRUCTION_START.value == "instruction_start"
        assert EventType.INSTRUCTION_COMPLETE.value == "instruction_complete"
        assert EventType.INSTRUCTION_CANCELLED.value == "instruction_cancelled"

        assert EventType.SYSTEM_STARTUP.value == "system_startup"
        assert EventType.SYSTEM_SHUTDOWN.value == "system_shutdown"
        assert EventType.ERROR_OCCURRED.value == "error_occurred"


class TestMultiCLIBus:
    """多CLI事件总线测试"""

    @pytest.fixture
    def bus(self):
        """创建事件总线实例"""
        bus = MultiCLIBus("redis://localhost:6379")
        bus.cli_id = "cli-test"
        return bus

    @pytest.mark.asyncio
    async def test_bus_connection(self, bus):
        """测试事件总线连接"""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=b"PONG")
        bus.redis_client = mock_redis

        await bus.connect()

        assert bus.running is True
        mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_bus_disconnection(self, bus):
        """测试事件总线断开连接"""
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        bus.redis_client = mock_redis
        bus.running = True

        await bus.disconnect()

        assert bus.running is False
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_bus_publish_event(self, bus):
        """测试发布事件"""
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"message_123")
        bus.redis_client = mock_redis

        # Create event
        event = Event(
            type=EventType.WORKFLOW_START,
            source_cli=bus.cli_id,
            data={"workflow_id": "wf-456"}
        )

        # Publish event
        message_id = await bus.publish_event(event)

        assert message_id == "message_123"

        # Verify Redis call
        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == bus.stream_name
        assert "id" in call_args[1][0]
        assert call_args[1][0]["type"] == EventType.WORKFLOW_START.value

    @pytest.mark.asyncio
    async def test_bus_publish_event_with_reply(self, bus):
        """测试发布带回复地址的事件"""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock()
        bus.redis_client = mock_redis

        event = Event(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli=bus.cli_id,
            reply_to=bus.response_stream
        )

        await bus.publish_event(event)

        # Should add to subscription stream
        assert mock_redis.xadd.call_count == 2
        call_args = mock_redis.xadd.call_args_list
        assert call_args[1][0][0] == bus.subscription_stream

    @pytest.mark.asyncio
    async def test_bus_request_response(self, bus):
        """测试请求-响应模式"""
        mock_redis = AsyncMock()

        # Mock response
        response_data = {
            "id": "response_123",
            "type": "instruction_complete",
            "source_cli": "cli-target",
            "data": {"result": "success"}
        }

        # Mock xread to return response
        mock_redis.xread = AsyncMock(return_value=[
            (b"response_stream", [(b"response_456", {"event_data": json.dumps(response_data), "request_id": "request_123"})])
        ])
        bus.redis_client = mock_redis

        # Create request event
        request_event = Event(
            type=EventType.WORKFLOW_START,
            source_cli=bus.cli_id,
            reply_to=bus.response_stream
        )

        # Send request
        response_event = await bus.request_response(request_event, timeout=1.0)

        assert response_event is not None
        assert response_event.type.value == "instruction_complete"
        assert response_event.source_cli == "cli-target"

    @pytest.mark.asyncio
    async def test_bus_request_response_timeout(self, bus):
        """测试请求-响应超时"""
        mock_redis = AsyncMock()
        mock_redis.xread = AsyncMock(return_value=[])  # No response
        bus.redis_client = mock_redis

        event = Event(
            type=EventType.WORKFLOW_START,
            source_cli=bus.cli_id,
            reply_to=bus.response_stream
        )

        response = await bus.request_response(event, timeout=0.1)
        assert response is None

    @pytest.mark.asyncio
    async def test_bus_subscribe_all_events(self, bus):
        """测试订阅所有事件"""
        mock_redis = AsyncMock()
        bus.redis_client = mock_redis
        bus.running = True

        # Mock event handler
        mock_handler = AsyncMock()
        bus.event_handlers[EventType.WORKFLOW_START] = [mock_handler]

        # Mock xread to return events
        event_data = {
            "id": "msg_123",
            "type": "workflow_start",
            "source_cli": "cli-source",
            "priority": "2",
            "timestamp": datetime.now().isoformat(),
            "data": "{}"
        }

        mock_redis.xread = AsyncMock(return_value=[
            (bus.stream_name, [(b"msg_123", event_data)])
        ])

        # Start subscription (mock the async loop)
        with patch('asyncio.sleep', side_effect=asyncio.CancelledError):
            try:
                await bus.subscribe()
            except asyncio.CancelledError:
                pass

        # Verify handler was called
        mock_handler.assert_called_once()
        call_arg = mock_handler.call_args[0][0]
        assert call_arg.type == EventType.WORKFLOW_START

    @pytest.mark.asyncio
    async def test_bus_subscribe_specific_events(self, bus):
        """测试订阅特定事件"""
        mock_redis = AsyncMock()
        bus.redis_client = mock_redis
        bus.running = True

        event_types = [EventType.WORKFLOW_START, EventType.INSTRUCTION_RECEIVED]

        with patch('asyncio.sleep', side_effect=asyncio.CancelledError):
            try:
                await bus.subscribe(event_types)
            except asyncio.CancelledError:
                pass

        # Verify the pattern includes both event types
        call_args = mock_redis.xread.call_args
        assert call_args[0][0][bus.stream_name] == "$"

    @pytest.mark.asyncio
    async def test_bus_handle_event(self, bus):
        """测试事件处理"""
        mock_handler = AsyncMock()
        bus.event_handlers[EventType.WORKFLOW_START] = [mock_handler]

        event = Event(
            type=EventType.WORKFLOW_START,
            source_cli="cli-source",
            data={"test": "data"}
        )

        await bus._handle_event(event)

        mock_handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_bus_handle_event_no_handlers(self, bus):
        """测试处理无处理器的事件"""
        event = Event(
            type=EventType.WORKFLOW_START,
            source_cli="cli-source"
        )

        # Should not raise exception
        await bus._handle_event(event)

    def test_bus_add_event_handler(self, bus):
        """测试添加事件处理器"""
        mock_handler = lambda e: None

        bus.add_event_handler(EventType.WORKFLOW_START, mock_handler)

        assert EventType.WORKFLOW_START in bus.event_handlers
        assert len(bus.event_handlers[EventType.WORKFLOW_START]) == 1
        assert bus.event_handlers[EventType.WORKFLOW_START][0] == mock_handler

    def test_bus_remove_event_handler(self, bus):
        """测试移除事件处理器"""
        mock_handler = lambda e: None

        bus.add_event_handler(EventType.WORKFLOW_START, mock_handler)
        assert len(bus.event_handlers[EventType.WORKFLOW_START]) == 1

        bus.remove_event_handler(EventType.WORKFLOW_START, mock_handler)
        assert len(bus.event_handlers[EventType.WORKFLOW_START]) == 0

    @pytest.mark.asyncio
    async def test_bus_register_cli(self, bus):
        """测试注册CLI"""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock()
        bus.redis_client = mock_redis

        await bus.register_cli()

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == bus.stream_name
        assert call_args[1][0]["type"] == EventType.SYSTEM_STARTUP.value
        assert call_args[1][0]["source_cli"] == bus.cli_id
        assert "cli_version" in call_args[1][0]["data"]

    @pytest.mark.asyncio
    async def test_bus_unregister_cli(self, bus):
        """测试注销CLI"""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock()
        bus.redis_client = mock_redis

        await bus.unregister_cli()

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[1][0]["type"] == EventType.SYSTEM_SHUTDOWN.value


class TestWorkflowCoordinator:
    """工作流协调器测试"""

    @pytest.fixture
    def coordinator(self):
        """创建工作流协调器"""
        mock_bus = AsyncMock()
        mock_bus.cli_id = "cli-test"
        mock_bus.publish_event = AsyncMock()
        return WorkflowCoordinator(mock_bus)

    @pytest.mark.asyncio
    async def test_start_workflow(self, coordinator):
        """测试启动工作流"""
        workflow_id = "wf-123"
        workflow_type = "feature_development"
        initial_data = {"description": "User auth system"}

        await coordinator.start_workflow(workflow_id, workflow_type, initial_data)

        # Verify workflow registered
        assert workflow_id in coordinator.active_workflows
        workflow = coordinator.active_workflows[workflow_id]
        assert workflow["type"] == workflow_type
        assert workflow["status"] == "running"
        assert workflow["start_time"] is not None

        # Verify event published
        coordinator.bus.publish_event.assert_called_once()
        call_arg = coordinator.bus.publish_event.call_args[0][0]
        assert call_arg.type == EventType.WORKFLOW_START
        assert call_arg.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_update_workflow_progress(self, coordinator):
        """测试更新工作流进度"""
        # Start workflow first
        workflow_id = "wf-123"
        await coordinator.start_workflow(workflow_id, "feature_development", {})

        # Update progress
        step = "implementation"
        progress = 50.0
        data = {"completed": True}

        await coordinator.update_workflow_progress(workflow_id, step, progress, data)

        # Verify workflow updated
        workflow = coordinator.active_workflows[workflow_id]
        assert len(workflow["steps"]) == 1
        step_info = workflow["steps"][0]
        assert step_info["step"] == step
        assert step_info["progress"] == progress

        # Verify event published
        assert coordinator.bus.publish_event.call_count == 2
        call_arg = coordinator.bus.publish_event.call_args[0][0]
        assert call_arg.type == EventType.WORKFLOW_PROGRESS
        assert call_arg.progress == progress

    @pytest.mark.asyncio
    async def test_update_workflow_progress_nonexistent(self, coordinator):
        """测试更新不存在工作流进度"""
        await coordinator.update_workflow_progress("nonexistent", "test", 0.0, {})
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_complete_workflow(self, coordinator):
        """测试完成工作流"""
        # Start workflow first
        workflow_id = "wf-123"
        await coordinator.start_workflow(workflow_id, "feature_development", {})

        # Complete workflow
        result = {"status": "completed", "message": "Success"}

        await coordinator.complete_workflow(workflow_id, result)

        # Verify workflow completed
        assert workflow_id not in coordinator.active_workflows

        # Verify event published
        assert coordinator.bus.publish_event.call_count == 2
        call_arg = coordinator.bus.publish_event.call_args[0][0]
        assert call_arg.type == EventType.WORKFLOW_COMPLETE
        assert call_arg.progress == 100.0

    @pytest.mark.asyncio
    async def test_complete_workflow_nonexistent(self, coordinator):
        """测试完成不存在工作流"""
        await coordinator.complete_workflow("nonexistent", {})
        # Should not raise exception

    @pytest.mark.asyncio
    async def test_fail_workflow(self, coordinator):
        """测试工作流失败"""
        # Start workflow first
        workflow_id = "wf-123"
        await coordinator.start_workflow(workflow_id, "feature_development", {})

        # Fail workflow
        error = "Implementation failed"

        await coordinator.fail_workflow(workflow_id, error)

        # Verify workflow failed
        assert workflow_id not in coordinator.active_workflows

        # Verify event published
        assert coordinator.bus.publish_event.call_count == 2
        call_arg = coordinator.bus.publish_event.call_args[0][0]
        assert call_arg.type == EventType.WORKFLOW_FAILED
        assert call_arg.data["error"] == error


class TestInstructionDispatcher:
    """指令分发器测试"""

    @pytest.fixture
    def dispatcher(self):
        """创建指令分发器"""
        mock_bus = AsyncMock()
        mock_bus.cli_id = "cli-test"
        mock_bus.publish_event = AsyncMock()
        return InstructionDispatcher(mock_bus)

    @pytest.mark.asyncio
    async def test_dispatch_instruction(self, dispatcher):
        """测试分发指令"""
        instruction = {
            "type": "workflow",
            "command": "/iccc/workflow 'Create user API'",
            "args": ["Create", "user API"]
        }

        instruction_id = await dispatcher.dispatch_instruction(instruction)

        # Verify instruction registered
        assert instruction_id in dispatcher.active_instructions
        instruction_state = dispatcher.active_instructions[instruction_id]
        assert instruction_state["instruction"] == instruction
        assert instruction_state["status"] == "dispatched"

        # Verify event published
        dispatcher.bus.publish_event.assert_called_once()
        call_arg = dispatcher.bus.publish_event.call_args[0][0]
        assert call_arg.type == EventType.INSTRUCTION_RECEIVED
        assert call_arg.instruction_id == instruction_id

    @pytest.mark.asyncio
    async def test_dispatch_instruction_with_custom_id(self, dispatcher):
        """测试分发带自定义ID的指令"""
        instruction_id = "custom-123"
        instruction = {"type": "workflow", "command": "test"}

        result = await dispatcher.dispatch_instruction(instruction, instruction_id)

        assert result == instruction_id

    @pytest.mark.asyncio
    async def test_update_instruction_status(self, dispatcher):
        """测试更新指令状态"""
        instruction_id = "inst-123"
        instruction = {"type": "workflow", "command": "test"}

        # Dispatch instruction first
        await dispatcher.dispatch_instruction(instruction)

        # Update status
        status = "in_progress"
        result = {"progress": 50}

        await dispatcher.update_instruction_status(instruction_id, status, result)

        # Verify status updated
        instruction_state = dispatcher.active_instructions[instruction_id]
        assert instruction_state["status"] == status
        assert instruction_state["result"] == result

        # Verify event published
        assert dispatcher.bus.publish_event.call_count == 2
        call_arg = dispatcher.bus.publish_event.call_args[0][0]
        assert call_arg.type == EventType.INSTRUCTION_START
        assert call_arg.status == status

    @pytest.mark.asyncio
    async def test_update_instruction_status_complete(self, dispatcher):
        """测试更新指令状态为完成"""
        instruction_id = "inst-123"
        instruction = {"type": "workflow", "command": "test"}

        # Dispatch instruction first
        await dispatcher.dispatch_instruction(instruction)

        # Update to complete
        await dispatcher.update_instruction_status(instruction_id, "completed")

        # Verify instruction cleaned up
        assert instruction_id not in dispatcher.active_instructions


class TestGlobalFunctions:
    """全局函数测试"""

    def test_get_event_bus_singleton(self):
        """测试获取事件总线单例"""
        from iccc.core.multi_cli_communication import _bus

        # Reset global bus
        _bus = None

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_get_workflow_coordinator(self):
        """测试获取工作流协调器"""
        from iccc.core.multi_cli_communication import _workflow_coordinator

        # Reset global coordinator
        _workflow_coordinator = None

        coordinator = get_workflow_coordinator()
        assert coordinator is not None

    def test_get_instruction_dispatcher(self):
        """测试获取指令分发器"""
        from iccc.core.multi_cli_communication import _instruction_dispatcher

        # Reset global dispatcher
        _instruction_dispatcher = None

        dispatcher = get_instruction_dispatcher()
        assert dispatcher is not None

    @pytest.mark.asyncio
    async def test_initialize_multi_cli_system(self):
        """测试初始化多CLI系统"""
        mock_bus = AsyncMock()
        mock_bus.connect = AsyncMock()
        mock_bus.register_cli = AsyncMock()
        mock_bus.add_event_handler = AsyncMock()

        with patch('iccc.core.multi_cli_communication.get_event_bus', return_value=mock_bus):
            with patch('iccc.core.multi_cli_communication._handle_workflow_start'):
                with patch('iccc.core.multi_cli_communication._handle_instruction_received'):
                    await initialize_multi_cli_system("redis://localhost:6379")

        mock_bus.connect.assert_called_once()
        mock_bus.register_cli.assert_called_once()
        assert mock_bus.add_event_handler.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_workflow_start(self):
        """测试处理工作流开始事件"""
        event = WorkflowEvent(
            type=EventType.WORKFLOW_START,
            source_cli="cli-123",
            workflow_id="wf-456",
            workflow_type="test",
            step="initialization"
        )

        with patch('builtins.print') as mock_print:
            await _handle_workflow_start(event)

        mock_print.assert_called_once()
        assert "Workflow started" in mock_print.call_args[0][0]
        assert "wf-456" in mock_print.call_args[0][0]
        assert "cli-123" in mock_print.call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_instruction_received(self):
        """测试处理指令接收事件"""
        event = InstructionEvent(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli="cli-123",
            instruction_id="inst-789",
            instruction_type="workflow",
            status="received"
        )

        with patch('builtins.print') as mock_print:
            await _handle_instruction_received(event)

        mock_print.assert_called_once()
        assert "Instruction received" in mock_print.call_args[0][0]
        assert "inst-789" in mock_print.call_args[0][0]
        assert "cli-123" in mock_print.call_args[0][0]


class TestMultiCLIIntegration:
    """多CLI集成测试"""

    @pytest.mark.asyncio
    async def test_full_event_lifecycle(self):
        """测试完整的事件生命周期"""
        # 1. 初始化系统
        mock_bus = MultiCLIBus()
        mock_bus.cli_id = "cli-1"
        mock_bus.redis_client = AsyncMock()
        mock_bus.running = True

        # Mock Redis operations
        mock_bus.redis_client.ping = AsyncMock(return_value=b"PONG")
        mock_bus.redis_client.xadd = AsyncMock(return_value=b"msg_123")
        mock_bus.redis_client.xread = AsyncMock(return_value=[])

        # 2. 连接系统
        await mock_bus.connect()

        # 3. 创建协调器和分发器
        coordinator = WorkflowCoordinator(mock_bus)
        dispatcher = InstructionDispatcher(mock_bus)

        # 4. 启动工作流
        workflow_id = "wf-123"
        await coordinator.start_workflow(workflow_id, "feature_development", {})

        # 5. 更新工作流进度
        await coordinator.update_workflow_progress(workflow_id, "implementation", 50.0, {})

        # 6. 分发指令
        instruction = {"type": "workflow", "command": "test"}
        instruction_id = await dispatcher.dispatch_instruction(instruction)

        # 7. 更新指令状态
        await dispatcher.update_instruction_status(instruction_id, "completed")

        # 8. 完成工作流
        await coordinator.complete_workflow(workflow_id, {"status": "success"})

        # 9. 验证事件调用次数
        assert mock_bus.publish_event.call_count >= 5

        # 10. 清理
        await mock_bus.disconnect()

    @pytest.mark.asyncio
    async def test_cli_registration_and_communication(self):
        """测试CLI注册和通信"""
        # 创建两个CLI实例
        cli1_bus = MultiCLIBus()
        cli2_bus = MultiCLIBus()

        cli1_bus.cli_id = "cli-1"
        cli2_bus.cli_id = "cli-2"

        # Mock Redis
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=b"PONG")
        mock_redis.xadd = AsyncMock()

        cli1_bus.redis_client = mock_redis
        cli2_bus.redis_client = mock_redis

        # 连接两个CLI
        await cli1_bus.connect()
        await cli2_bus.connect()

        # CLI1注册
        await cli1_bus.register_cli()

        # CLI2注册
        await cli2_bus.register_cli()

        # 验证注册事件
        assert mock_redis.xadd.call_count == 2

        # 断开连接
        await cli1_bus.disconnect()
        await cli2_bus.disconnect()

    @pytest.mark.asyncio
    async def test_event_priority_handling(self):
        """测试事件优先级处理"""
        bus = MultiCLIBus()
        bus.cli_id = "cli-test"
        bus.redis_client = AsyncMock()

        # 创建不同优先级的事件
        normal_event = Event(
            type=EventType.WORKFLOW_START,
            source_cli=bus.cli_id,
            priority=EventPriority.NORMAL,
            data={"workflow_id": "wf-1"}
        )

        high_event = Event(
            type=EventType.WORKFLOW_START,
            source_cli=bus.cli_id,
            priority=EventPriority.HIGH,
            data={"workflow_id": "wf-2"}
        )

        critical_event = Event(
            type=EventType.WORKFLOW_START,
            source_cli=bus.cli_id,
            priority=EventPriority.CRITICAL,
            data={"workflow_id": "wf-3"}
        )

        # 验证优先级顺序
        events = [normal_event, high_event, critical_event]
        sorted_events = sorted(events, key=lambda e: e.priority.value, reverse=True)

        assert sorted_events[0].priority == EventPriority.CRITICAL
        assert sorted_events[1].priority == EventPriority.HIGH
        assert sorted_events[2].priority == EventPriority.NORMAL

    def test_event_serialization(self):
        """测试事件序列化"""
        event = Event(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli="cli-123",
            data={"instruction": "test"}
        )

        # 序列化
        event_data = {
            "id": event.id,
            "type": event.type.value,
            "source_cli": event.source_cli,
            "priority": event.priority.value,
            "timestamp": event.timestamp.isoformat(),
            "data": json.dumps(event.data)
        }

        # 反序列化
        restored_event = Event(
            id=event_data["id"],
            type=EventType(event_data["type"]),
            source_cli=event_data["source_cli"],
            priority=EventPriority(event_data["priority"]),
            timestamp=datetime.fromisoformat(event_data["timestamp"]),
            data=json.loads(event_data["data"])
        )

        assert restored_event.id == event.id
        assert restored_event.type == event.type
        assert restored_event.source_cli == event.source_cli
        assert restored_event.priority == event.priority
        assert restored_event.data == event.data