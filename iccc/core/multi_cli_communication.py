"""
多CLI通信机制

基于Redis Streams的跨CLI事件总线，实现多个CLI实例间的实时通信和事件协调。
"""

import asyncio
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

import redis.asyncio as redis
from pydantic import BaseModel, Field


class EventType(Enum):
    """事件类型枚举"""
    # 工作流事件
    WORKFLOW_START = "workflow_start"
    WORKFLOW_PROGRESS = "workflow_progress"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_FAILED = "workflow_failed"

    # 指令事件
    INSTRUCTION_RECEIVED = "instruction_received"
    INSTRUCTION_START = "instruction_start"
    INSTRUCTION_COMPLETE = "instruction_complete"
    INSTRUCTION_CANCELLED = "instruction_cancelled"

    # 代理事件
    AGENT_REGISTERED = "agent_registered"
    AGENT_STATUS_CHANGE = "agent_status_change"
    AGENT_TASK_ASSIGNED = "agent_task_assigned"
    AGENT_TASK_COMPLETED = "agent_task_completed"

    # 项目事件
    PROJECT_CREATED = "project_created"
    PROJECT_UPDATED = "project_updated"
    PROJECT_DELETED = "project_deleted"

    # 系统事件
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    ERROR_OCCURRED = "error_occurred"

    # 协作事件
    COLLABORATION_REQUEST = "collaboration_request"
    COLLABORATION_ACCEPTED = "collaboration_accepted"
    COLLABORATION_REJECTED = "collaboration_rejected"
    CODE_REVIEW_REQUEST = "code_review_request"


class EventPriority(Enum):
    """事件优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class Event(BaseModel):
    """事件基类"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType = Field(..., description="事件类型")
    source_cli: str = Field(..., description="源CLI标识")
    target_cli: Optional[str] = Field(None, description="目标CLI标识（可选）")
    priority: EventPriority = Field(default=EventPriority.NORMAL, description="事件优先级")
    timestamp: datetime = Field(default_factory=datetime.now, description="事件时间戳")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")
    correlation_id: Optional[str] = Field(None, description="关联ID（用于事件追踪）")
    reply_to: Optional[str] = Field(None, description="回复地址（用于响应事件）")


class WorkflowEvent(Event):
    """工作流事件"""
    workflow_id: str = Field(..., description="工作流ID")
    workflow_type: str = Field(..., description="工作流类型")
    step: str = Field(..., description="当前步骤")
    progress: float = Field(default=0.0, description="进度（0-100）")


class InstructionEvent(Event):
    """指令事件"""
    instruction_id: str = Field(..., description="指令ID")
    instruction_type: str = Field(..., description="指令类型")
    status: str = Field(..., description="指令状态")
    result: Optional[Any] = Field(None, description="执行结果")


class MultiCLIBus:
    """多CLI事件总线"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.event_handlers: Dict[EventType, List[Callable]] = {}
        self.cli_id: str = f"cli-{uuid.uuid4().hex[:8]}"
        self.running = False

        # Stream names
        self.stream_name = "iccc_events"
        self.response_stream = "iccc_responses"
        self.subscription_stream = f"iccc_subscription_{self.cli_id}"

    async def connect(self) -> None:
        """连接到Redis"""
        self.redis_client = redis.from_url(self.redis_url)
        await self.redis_client.ping()
        self.running = True

    async def disconnect(self) -> None:
        """断开连接"""
        self.running = False
        if self.redis_client:
            await self.redis_client.close()

    async def publish_event(self, event: Event) -> str:
        """发布事件"""
        if not self.redis_client:
            raise RuntimeError("Redis client not connected")

        # 序列化事件
        event_data = {
            "id": event.id,
            "type": event.type.value,
            "source_cli": event.source_cli,
            "target_cli": event.target_cli,
            "priority": event.priority.value,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "correlation_id": event.correlation_id,
            "reply_to": event.reply_to
        }

        # 发布到事件流
        message_id = await self.redis_client.xadd(self.stream_name, event_data)

        # 如果是请求事件，同时添加到订阅流
        if event.reply_to:
            await self.redis_client.xadd(
                self.subscription_stream,
                {"event_id": str(message_id), "status": "published"}
            )

        return str(message_id)

    async def request_response(
        self,
        event: Event,
        timeout: float = 30.0
    ) -> Optional[Event]:
        """发送请求并等待响应"""
        if not self.redis_client:
            raise RuntimeError("Redis client not connected")

        # 设置回复地址
        event.reply_to = self.response_stream
        event_id = await self.publish_event(event)

        # 等待响应
        start_time = asyncio.get_event_loop().time()
        while True:
            if not self.running:
                return None

            # 检查超时
            if asyncio.get_event_loop().time() - start_time > timeout:
                return None

            # 读取响应
            messages = await self.redis_client.xread(
                {self.response_stream: "$"},
                count=1,
                block=int(timeout * 1000)
            )

            if messages:
                stream, data = messages[0]
                for msg_id, fields in data:
                    # 检查是否是对应请求的响应
                    if fields.get("request_id") == event_id:
                        response_data = json.loads(fields["event_data"])
                        return Event(**response_data)

            await asyncio.sleep(0.1)

    async def subscribe(self, event_types: List[EventType] = None) -> None:
        """订阅事件"""
        if not self.redis_client:
            raise RuntimeError("Redis client not connected")

        # 读取事件流
        if event_types is None:
            pattern = "*"
        else:
            pattern = "|".join([et.value for et in event_types])

        while self.running:
            try:
                messages = await self.redis_client.xread(
                    {self.stream_name: "$"},
                    count=10,
                    block=1000
                )

                if messages:
                    for stream, data in messages:
                        for msg_id, fields in data:
                            try:
                                # 解析事件
                                event_data = {
                                    "id": msg_id,
                                    "type": fields["type"],
                                    "source_cli": fields["source_cli"],
                                    "target_cli": fields.get("target_cli"),
                                    "priority": EventPriority(int(fields["priority"])),
                                    "timestamp": datetime.fromisoformat(fields["timestamp"]),
                                    "data": json.loads(fields["data"]),
                                    "correlation_id": fields.get("correlation_id"),
                                    "reply_to": fields.get("reply_to")
                                }

                                event = Event(**event_data)

                                # 如果指定了目标CLI且不是当前CLI，跳过
                                if event.target_cli and event.target_cli != self.cli_id:
                                    continue

                                # 处理事件
                                await self._handle_event(event)

                            except Exception as e:
                                print(f"Error processing event: {e}")

            except Exception as e:
                print(f"Error in event subscription: {e}")
                await asyncio.sleep(1)

    async def _handle_event(self, event: Event) -> None:
        """处理接收到的事件"""
        # 获取对应的事件处理器
        handlers = self.event_handlers.get(event.type, [])

        # 并发执行所有处理器
        if handlers:
            await asyncio.gather(*[handler(event) for handler in handlers], return_exceptions=True)

    def add_event_handler(self, event_type: EventType, handler: Callable) -> None:
        """添加事件处理器"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def remove_event_handler(self, event_type: EventType, handler: Callable) -> None:
        """移除事件处理器"""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].remove(handler)

    async def register_cli(self) -> None:
        """注册CLI实例"""
        event = Event(
            type=EventType.SYSTEM_STARTUP,
            source_cli=self.cli_id,
            data={"cli_version": "1.0.0", "capabilities": ["workflow", "collaboration", "monitoring"]}
        )
        await self.publish_event(event)

    async def unregister_cli(self) -> None:
        """注销CLI实例"""
        event = Event(
            type=EventType.SYSTEM_SHUTDOWN,
            source_cli=self.cli_id
        )
        await self.publish_event(event)


class WorkflowCoordinator:
    """工作流协调器"""

    def __init__(self, bus: MultiCLIBus):
        self.bus = bus
        self.active_workflows: Dict[str, Dict] = {}

    async def start_workflow(self, workflow_id: str, workflow_type: str, initial_data: Dict) -> None:
        """启动工作流"""
        # 注册工作流
        self.active_workflows[workflow_id] = {
            "type": workflow_type,
            "status": "running",
            "steps": [],
            "start_time": datetime.now().isoformat()
        }

        # 发布工作流开始事件
        event = WorkflowEvent(
            type=EventType.WORKFLOW_START,
            source_cli=self.bus.cli_id,
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            step="initialization",
            progress=0.0,
            data=initial_data
        )
        await self.bus.publish_event(event)

    async def update_workflow_progress(self, workflow_id: str, step: str, progress: float, data: Dict) -> None:
        """更新工作流进度"""
        if workflow_id not in self.active_workflows:
            return

        workflow = self.active_workflows[workflow_id]
        workflow["steps"].append({
            "step": step,
            "progress": progress,
            "timestamp": datetime.now().isoformat()
        })

        # 发布进度更新事件
        event = WorkflowEvent(
            type=EventType.WORKFLOW_PROGRESS,
            source_cli=self.bus.cli_id,
            workflow_id=workflow_id,
            workflow_type=workflow["type"],
            step=step,
            progress=progress,
            data=data
        )
        await self.bus.publish_event(event)

    async def complete_workflow(self, workflow_id: str, result: Dict) -> None:
        """完成工作流"""
        if workflow_id not in self.active_workflows:
            return

        workflow = self.active_workflows[workflow_id]
        workflow["status"] = "completed"
        workflow["end_time"] = datetime.now().isoformat()

        # 发布完成事件
        event = WorkflowEvent(
            type=EventType.WORKFLOW_COMPLETE,
            source_cli=self.bus.cli_id,
            workflow_id=workflow_id,
            workflow_type=workflow["type"],
            step="completion",
            progress=100.0,
            data=result
        )
        await self.bus.publish_event(event)

        # 清理工作流状态
        del self.active_workflows[workflow_id]

    async def fail_workflow(self, workflow_id: str, error: str) -> None:
        """失败工作流"""
        if workflow_id not in self.active_workflows:
            return

        workflow = self.active_workflows[workflow_id]
        workflow["status"] = "failed"
        workflow["error"] = error
        workflow["end_time"] = datetime.now().isoformat()

        # 发布失败事件
        event = WorkflowEvent(
            type=EventType.WORKFLOW_FAILED,
            source_cli=self.bus.cli_id,
            workflow_id=workflow_id,
            workflow_type=workflow["type"],
            step="error",
            progress=0.0,
            data={"error": error}
        )
        await self.bus.publish_event(event)

        # 清理工作流状态
        del self.active_workflows[workflow_id]


class InstructionDispatcher:
    """指令分发器"""

    def __init__(self, bus: MultiCLIBus):
        self.bus = bus
        self.active_instructions: Dict[str, Dict] = {}

    async def dispatch_instruction(self, instruction: Dict) -> str:
        """分发指令"""
        instruction_id = instruction.get("id", str(uuid.uuid4()))

        # 注册指令
        self.active_instructions[instruction_id] = {
            "instruction": instruction,
            "status": "dispatched",
            "dispatch_time": datetime.now().isoformat()
        }

        # 发布指令接收事件
        event = InstructionEvent(
            type=EventType.INSTRUCTION_RECEIVED,
            source_cli=self.bus.cli_id,
            instruction_id=instruction_id,
            instruction_type=instruction.get("type", "unknown"),
            status="dispatched",
            data=instruction
        )
        await self.bus.publish_event(event)

        return instruction_id

    async def update_instruction_status(self, instruction_id: str, status: str, result: Any = None) -> None:
        """更新指令状态"""
        if instruction_id not in self.active_instructions:
            return

        instruction_state = self.active_instructions[instruction_id]
        instruction_state["status"] = status
        instruction_state["update_time"] = datetime.now().isoformat()

        if result is not None:
            instruction_state["result"] = result

        # 发布状态更新事件
        event = InstructionEvent(
            type=EventType.INSTRUCTION_COMPLETE if status == "completed" else EventType.INSTRUCTION_START,
            source_cli=self.bus.cli_id,
            instruction_id=instruction_id,
            instruction_type=instruction_state["instruction"].get("type", "unknown"),
            status=status,
            result=result
        )
        await self.bus.publish_event(event)

        # 如果指令完成，清理状态
        if status == "completed" or status == "failed":
            del self.active_instructions[instruction_id]


# 全局实例
_bus: Optional[MultiCLIBus] = None
_workflow_coordinator: Optional[WorkflowCoordinator] = None
_instruction_dispatcher: Optional[InstructionDispatcher] = None


def get_event_bus() -> MultiCLIBus:
    """获取全局事件总线"""
    global _bus
    if _bus is None:
        _bus = MultiCLIBus()
    return _bus


def get_workflow_coordinator() -> WorkflowCoordinator:
    """获取全局工作流协调器"""
    global _workflow_coordinator
    if _workflow_coordinator is None:
        _workflow_coordinator = WorkflowCoordinator(get_event_bus())
    return _workflow_coordinator


def get_instruction_dispatcher() -> InstructionDispatcher:
    """获取全局指令分发器"""
    global _instruction_dispatcher
    if _instruction_dispatcher is None:
        _instruction_dispatcher = InstructionDispatcher(get_event_bus())
    return _instruction_dispatcher


async def initialize_multi_cli_system(redis_url: str = "redis://localhost:6379") -> None:
    """初始化多CLI系统"""
    bus = get_event_bus()
    await bus.connect()
    await bus.register_cli()

    # 设置事件处理器
    coordinator = get_workflow_coordinator()
    dispatcher = get_instruction_dispatcher()

    # 添加默认事件处理器
    bus.add_event_handler(EventType.WORKFLOW_START, _handle_workflow_start)
    bus.add_event_handler(EventType.INSTRUCTION_RECEIVED, _handle_instruction_received)


async def _handle_workflow_start(event: WorkflowEvent) -> None:
    """处理工作流开始事件"""
    print(f"🚀 Workflow started: {event.workflow_id} by {event.source_cli}")


async def _handle_instruction_received(event: InstructionEvent) -> None:
    """处理指令接收事件"""
    print(f"📝 Instruction received: {event.instruction_id} by {event.source_cli}")


# 使用示例
async def example_usage():
    """使用示例"""
    # 初始化系统
    await initialize_multi_cli_system()

    # 获取协调器
    coordinator = get_workflow_coordinator()

    # 启动工作流
    await coordinator.start_workflow(
        "workflow-123",
        "feature_development",
        {"description": "实现用户认证系统"}
    )

    # 更新进度
    await coordinator.update_workflow_progress(
        "workflow-123",
        "代码实现",
        50.0,
        {"completed_steps": ["需求分析", "架构设计"], "current_step": "代码实现"}
    )

    # 完成工作流
    await coordinator.complete_workflow(
        "workflow-123",
        {"result": "用户认证系统开发完成", "status": "success"}
    )

    # 断开连接
    await get_event_bus().disconnect()