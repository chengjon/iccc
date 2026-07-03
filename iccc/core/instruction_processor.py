"""
iCCC 指令处理器

基于多CLI协作平台的指令处理系统，支持各种工作流指令的解析和执行。
"""

import asyncio
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field


class InstructionType(Enum):
    """指令类型枚举"""
    WORKFLOW = "workflow"
    THINKING = "thinking"
    COLLABORATION = "collaboration"
    MANAGEMENT = "management"
    CONFIGURATION = "configuration"


class InstructionStatus(Enum):
    """指令状态枚举"""
    PENDING = "pending"
    PARSING = "parsing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Instruction(BaseModel):
    """指令基类"""
    id: str = Field(..., description="指令唯一标识")
    type: InstructionType = Field(..., description="指令类型")
    command: str = Field(..., description="原始命令")
    args: List[str] = Field(default_factory=list, description="命令参数")
    kwargs: Dict[str, Any] = Field(default_factory=dict, description="命令关键字参数")
    status: InstructionStatus = Field(default=InstructionStatus.PENDING, description="指令状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始执行时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    result: Optional[Any] = Field(None, description="执行结果")
    error: Optional[str] = Field(None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class WorkflowInstruction(Instruction):
    """工作流指令"""
    workflow_type: str = Field(..., description="工作流类型")
    input_specs: List[str] = Field(default_factory=list, description="输入规格文件")
    output_dir: Optional[str] = Field(None, description="输出目录")
    parallel_enabled: bool = Field(default=True, description="是否启用并行执行")


class ThinkingInstruction(Instruction):
    """思考分析指令"""
    analysis_depth: str = Field(default="medium", description="分析深度")
    focus_areas: List[str] = Field(default_factory=list, description="关注领域")
    reflection_target: Optional[str] = Field(None, description="反思目标")


class CollaborationInstruction(Instruction):
    """协作指令"""
    collaboration_type: str = Field(..., description="协作类型")
    target: str = Field(..., description="目标")
    team_members: List[str] = Field(default_factory=list, description="团队成员")


class ManagementInstruction(Instruction):
    """管理指令"""
    resource_type: str = Field(..., description="资源类型")
    action: str = Field(..., description="操作")
    scope: Optional[str] = Field(None, description="作用范围")


class ConfigurationInstruction(Instruction):
    """配置指令"""
    config_target: str = Field(..., description="配置目标")
    config_values: Dict[str, Any] = Field(..., description="配置值")


class InstructionProcessor:
    """指令处理器"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.instruction_registry = self._load_instruction_registry()
        self.active_instructions: Dict[str, Instruction] = {}

    def _load_instruction_registry(self) -> Dict[str, Tuple[InstructionType, type]]:
        """加载指令注册表"""
        return {
            # Workflow instructions
            "workflow": (InstructionType.WORKFLOW, WorkflowInstruction),
            "multi-workflow": (InstructionType.WORKFLOW, WorkflowInstruction),
            "spec": (InstructionType.WORKFLOW, WorkflowInstruction),
            "execute": (InstructionType.WORKFLOW, WorkflowInstruction),

            # Thinking instructions
            "ultra": (InstructionType.THINKING, ThinkingInstruction),
            "reflection": (InstructionType.THINKING, ThinkingInstruction),
            "eureka": (InstructionType.THINKING, ThinkingInstruction),
            "design": (InstructionType.THINKING, ThinkingInstruction),

            # Collaboration instructions
            "gh-fix": (InstructionType.COLLABORATION, CollaborationInstruction),
            "gh-review": (InstructionType.COLLABORATION, CollaborationInstruction),
            "review": (InstructionType.COLLABORATION, CollaborationInstruction),
            "create": (InstructionType.COLLABORATION, CollaborationInstruction),

            # Management instructions
            "project": (InstructionType.MANAGEMENT, ManagementInstruction),
            "task": (InstructionType.MANAGEMENT, ManagementInstruction),
            "status": (InstructionType.MANAGEMENT, ManagementInstruction),
            "quality": (InstructionType.MANAGEMENT, ManagementInstruction),

            # Configuration instructions
            "config": (InstructionType.CONFIGURATION, ConfigurationInstruction),
            "agent": (InstructionType.CONFIGURATION, ConfigurationInstruction),
            "hook": (InstructionType.CONFIGURATION, ConfigurationInstruction),
            "mcp": (InstructionType.CONFIGURATION, ConfigurationInstruction),
        }

    def parse_instruction(self, command: str) -> Instruction:
        """解析指令"""
        # 移除前缀
        if command.startswith("/iccc/"):
            command = command[6:]

        # 解析命令和参数
        parts = command.strip().split()
        if not parts:
            raise ValueError("Empty command")

        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # 获取指令类型和类
        if cmd not in self.instruction_registry:
            raise ValueError(f"Unknown instruction: {cmd}")

        instruction_type, instruction_class = self.instruction_registry[cmd]

        # 创建基础指令对象
        instruction_id = f"{cmd}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        if instruction_class == WorkflowInstruction:
            instruction = self._parse_workflow_instruction(instruction_id, cmd, args)
        elif instruction_class == ThinkingInstruction:
            instruction = self._parse_thinking_instruction(instruction_id, cmd, args)
        elif instruction_class == CollaborationInstruction:
            instruction = self._parse_collaboration_instruction(instruction_id, cmd, args)
        elif instruction_class == ManagementInstruction:
            instruction = self._parse_management_instruction(instruction_id, cmd, args)
        elif instruction_class == ConfigurationInstruction:
            instruction = self._parse_configuration_instruction(instruction_id, cmd, args)
        else:
            instruction = Instruction(
                id=instruction_id,
                type=instruction_type,
                command=cmd,
                args=args
            )

        self.active_instructions[instruction_id] = instruction
        return instruction

    def _parse_workflow_instruction(self, instruction_id: str, cmd: str, args: List[str]) -> WorkflowInstruction:
        """解析工作流指令"""
        kwargs = {}

        if cmd == "workflow":
            kwargs["workflow_type"] = "standard"
        elif cmd == "multi-workflow":
            kwargs["workflow_type"] = "complex"
            kwargs["parallel_enabled"] = True
        elif cmd == "spec":
            kwargs["workflow_type"] = "spec_creation"
        elif cmd == "execute":
            kwargs["workflow_type"] = "execution"

        # 解析规格文件引用
        input_specs = []
        for arg in args:
            if arg.startswith("@specs/"):
                input_specs.append(arg)

        if input_specs:
            kwargs["input_specs"] = input_specs

        return WorkflowInstruction(
            id=instruction_id,
            type=InstructionType.WORKFLOW,
            command=cmd,
            args=args,
            kwargs=kwargs
        )

    def _parse_thinking_instruction(self, instruction_id: str, cmd: str, args: List[str]) -> ThinkingInstruction:
        """解析思考分析指令"""
        kwargs = {}

        if cmd == "ultra":
            kwargs["analysis_depth"] = "deep"
            kwargs["focus_areas"] = ["architecture", "performance", "scalability"]
        elif cmd == "reflection":
            kwargs["analysis_depth"] = "medium"
            if args:
                kwargs["reflection_target"] = " ".join(args)
        elif cmd == "eureka":
            kwargs["analysis_depth"] = "innovative"
            kwargs["focus_areas"] = ["breakthrough", "innovation"]
        elif cmd == "design":
            kwargs["analysis_depth"] = "strategic"
            kwargs["focus_areas"] = ["architecture", "design_patterns"]

        return ThinkingInstruction(
            id=instruction_id,
            type=InstructionType.THINKING,
            command=cmd,
            args=args,
            kwargs=kwargs
        )

    def _parse_collaboration_instruction(self, instruction_id: str, cmd: str, args: List[str]) -> CollaborationInstruction:
        """解析协作指令"""
        kwargs = {}

        if cmd == "gh-fix":
            kwargs["collaboration_type"] = "github_issue"
            kwargs["target"] = args[0] if args else ""
        elif cmd == "gh-review":
            kwargs["collaboration_type"] = "github_pr"
            kwargs["target"] = args[0] if args else ""
        elif cmd == "review":
            kwargs["collaboration_type"] = "code_review"
            kwargs["target"] = args[0] if args else "current_project"
        elif cmd == "create":
            kwargs["collaboration_type"] = "custom_command"
            kwargs["target"] = args[0] if args else ""

        return CollaborationInstruction(
            id=instruction_id,
            type=InstructionType.COLLABORATION,
            command=cmd,
            args=args,
            kwargs=kwargs
        )

    def _parse_management_instruction(self, instruction_id: str, cmd: str, args: List[str]) -> ManagementInstruction:
        """解析管理指令"""
        kwargs = {}

        if cmd == "project":
            kwargs["resource_type"] = "project"
            kwargs["action"] = args[0] if args else "list"
            kwargs["scope"] = args[1] if len(args) > 1 else None
        elif cmd == "task":
            kwargs["resource_type"] = "task"
            kwargs["action"] = args[0] if args else "list"
            kwargs["scope"] = args[1] if len(args) > 1 else None
        elif cmd == "status":
            kwargs["resource_type"] = "status"
            kwargs["action"] = args[0] if args else "show"
            kwargs["scope"] = args[1] if len(args) > 1 else None
        elif cmd == "quality":
            kwargs["resource_type"] = "quality"
            kwargs["action"] = args[0] if args else "check"
            kwargs["scope"] = args[1] if len(args) > 1 else None

        return ManagementInstruction(
            id=instruction_id,
            type=InstructionType.MANAGEMENT,
            command=cmd,
            args=args,
            kwargs=kwargs
        )

    def _parse_configuration_instruction(self, instruction_id: str, cmd: str, args: List[str]) -> ConfigurationInstruction:
        """解析配置指令"""
        kwargs = {}

        if cmd == "config":
            kwargs["config_target"] = "system"
            kwargs["config_values"] = {"action": args[0] if args else "show"}
        elif cmd == "agent":
            kwargs["config_target"] = "agent"
            kwargs["config_values"] = {"action": args[0] if args else "list"}
        elif cmd == "hook":
            kwargs["config_target"] = "hook"
            kwargs["config_values"] = {"action": args[0] if args else "list"}
        elif cmd == "mcp":
            kwargs["config_target"] = "mcp"
            kwargs["config_values"] = {"action": args[0] if args else "list"}

        return ConfigurationInstruction(
            id=instruction_id,
            type=InstructionType.CONFIGURATION,
            command=cmd,
            args=args,
            kwargs=kwargs
        )

    async def execute_instruction(self, instruction: Instruction) -> Any:
        """执行指令"""
        instruction.status = InstructionStatus.EXECUTING
        instruction.started_at = datetime.now()

        try:
            result = await self._execute_instruction_impl(instruction)
            instruction.result = result
            instruction.status = InstructionStatus.COMPLETED
            instruction.completed_at = datetime.now()
            return result
        except Exception as e:
            instruction.error = str(e)
            instruction.status = InstructionStatus.FAILED
            instruction.completed_at = datetime.now()
            raise

    async def _execute_instruction_impl(self, instruction: Instruction) -> Any:
        """执行指令的具体实现"""
        # 这里可以根据不同的指令类型调用相应的处理器
        if instruction.type == InstructionType.WORKFLOW:
            return await self._execute_workflow_instruction(instruction)
        elif instruction.type == InstructionType.THINKING:
            return await self._execute_thinking_instruction(instruction)
        elif instruction.type == InstructionType.COLLABORATION:
            return await self._execute_collaboration_instruction(instruction)
        elif instruction.type == InstructionType.MANAGEMENT:
            return await self._execute_management_instruction(instruction)
        elif instruction.type == InstructionType.CONFIGURATION:
            return await self._execute_configuration_instruction(instruction)
        else:
            raise ValueError(f"Unsupported instruction type: {instruction.type}")

    async def _execute_workflow_instruction(self, instruction: WorkflowInstruction) -> Any:
        """执行工作流指令"""
        if instruction.command == "workflow":
            return await self._execute_standard_workflow(instruction)
        elif instruction.command == "multi-workflow":
            return await self._execute_complex_workflow(instruction)
        elif instruction.command == "spec":
            return await self._create_spec(instruction)
        elif instruction.command == "execute":
            return await self._execute_task(instruction)

    async def _execute_standard_workflow(self, instruction: WorkflowInstruction) -> Dict[str, Any]:
        """执行标准工作流"""
        return {
            "workflow_type": "standard",
            "status": "started",
            "steps": [
                "需求分析",
                "架构设计",
                "代码实现",
                "质量验证",
                "测试验证"
            ],
            "estimated_duration": "30-60分钟"
        }

    async def _execute_complex_workflow(self, instruction: WorkflowInstruction) -> Dict[str, Any]:
        """执行复杂工作流"""
        if instruction.kwargs.get("parallel_enabled", False):
            return {
                "workflow_type": "complex_parallel",
                "status": "started",
                "parallel_workers": 4,
                "coordination_required": True
            }
        else:
            return {
                "workflow_type": "complex_sequential",
                "status": "started",
                "coordination_required": False
            }

    async def _create_spec(self, instruction: WorkflowInstruction) -> Dict[str, Any]:
        """创建规格文档"""
        spec_content = f"# 规格文档\n\n创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        spec_content += f"## 需求描述\n\n{instruction.command}\n\n"
        spec_content += "## 功能需求\n\n待定\n\n"
        spec_content += "## 技术方案\n\n待定\n\n"
        spec_content += "## 实现计划\n\n待定\n"

        # 保存规格文件
        spec_dir = Path("specs")
        spec_dir.mkdir(exist_ok=True)
        spec_file = spec_dir / f"spec_{instruction.id}.md"

        with open(spec_file, 'w', encoding='utf-8') as f:
            f.write(spec_content)

        return {
            "status": "created",
            "spec_file": str(spec_file),
            "instruction_id": instruction.id
        }

    async def _execute_task(self, instruction: WorkflowInstruction) -> Dict[str, Any]:
        """执行任务"""
        return {
            "status": "queued",
            "task_id": instruction.id,
            "estimated_start": "马上开始"
        }

    async def _execute_thinking_instruction(self, instruction: ThinkingInstruction) -> Dict[str, Any]:
        """执行思考分析指令"""
        return {
            "analysis_type": instruction.command,
            "depth": instruction.kwargs.get("analysis_depth", "medium"),
            "focus_areas": instruction.kwargs.get("focus_areas", []),
            "status": "completed"
        }

    async def _execute_collaboration_instruction(self, instruction: CollaborationInstruction) -> Dict[str, Any]:
        """执行协作指令"""
        return {
            "collaboration_type": instruction.kwargs.get("collaboration_type"),
            "target": instruction.kwargs.get("target"),
            "status": "initiated"
        }

    async def _execute_management_instruction(self, instruction: ManagementInstruction) -> Dict[str, Any]:
        """执行管理指令"""
        return {
            "resource_type": instruction.kwargs.get("resource_type"),
            "action": instruction.kwargs.get("action"),
            "scope": instruction.kwargs.get("scope"),
            "status": "completed"
        }

    async def _execute_configuration_instruction(self, instruction: ConfigurationInstruction) -> Dict[str, Any]:
        """执行配置指令"""
        return {
            "config_target": instruction.kwargs.get("config_target"),
            "config_values": instruction.kwargs.get("config_values"),
            "status": "updated"
        }

    def get_instruction_status(self, instruction_id: str) -> Optional[InstructionStatus]:
        """获取指令状态"""
        instruction = self.active_instructions.get(instruction_id)
        return instruction.status if instruction else None

    def cancel_instruction(self, instruction_id: str) -> bool:
        """取消指令"""
        if instruction_id in self.active_instructions:
            instruction = self.active_instructions[instruction_id]
            if instruction.status in [InstructionStatus.PENDING, InstructionStatus.EXECUTING]:
                instruction.status = InstructionStatus.CANCELLED
                instruction.completed_at = datetime.now()
                return True
        return False

    def list_active_instructions(self) -> List[Dict[str, Any]]:
        """列出活跃指令"""
        return [
            {
                "id": inst.id,
                "type": inst.type.value,
                "command": inst.command,
                "status": inst.status.value,
                "created_at": inst.created_at.isoformat(),
                "started_at": inst.started_at.isoformat() if inst.started_at else None,
                "completed_at": inst.completed_at.isoformat() if inst.completed_at else None
            }
            for inst in self.active_instructions.values()
            if inst.status != InstructionStatus.COMPLETED
        ]


# 全局指令处理器实例
_instruction_processor: Optional[InstructionProcessor] = None


def get_instruction_processor() -> InstructionProcessor:
    """获取全局指令处理器实例"""
    global _instruction_processor
    if _instruction_processor is None:
        config_dir = Path(__file__).parent.parent / ".iccc" / "config"
        _instruction_processor = InstructionProcessor(config_dir)
    return _instruction_processor


async def process_instruction(command: str) -> Instruction:
    """处理指令的便捷函数"""
    processor = get_instruction_processor()
    instruction = processor.parse_instruction(command)
    await processor.execute_instruction(instruction)
    return instruction