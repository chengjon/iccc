"""
iCCC 指令处理器测试

测试指令解析、处理和执行的核心功能。
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from iccc.core.instruction_processor import (
    Instruction,
    InstructionProcessor,
    InstructionStatus,
    InstructionType,
    WorkflowInstruction,
    ThinkingInstruction,
    process_instruction
)


class TestInstructionProcessor:
    """指令处理器测试"""

    @pytest.fixture
    def processor(self):
        """创建指令处理器实例"""
        config_dir = Path("/tmp/test_config")
        config_dir.mkdir(exist_ok=True)
        return InstructionProcessor(config_dir)

    @pytest.fixture
    def sample_commands(self):
        """测试命令样例"""
        return [
            "/iccc/workflow \"创建用户注册API\"",
            "/iccc/multi-workflow \"重构项目架构\"",
            "/iccc/spec \"实现支付系统\"",
            "/iccc/ultra \"分析数据库性能\"",
            "/iccc/reflection \"代码重构总结\"",
            "/iccc/review \"src/components\"",
            "/iccc/config set model opus",
            "/iccc/project create \"电商系统\""
        ]

    def test_parse_workflow_instruction(self, processor):
        """测试工作流指令解析"""
        instruction = processor.parse_instruction("/iccc/workflow \"创建用户注册API\"")

        assert isinstance(instruction, WorkflowInstruction)
        assert instruction.type == InstructionType.WORKFLOW
        assert instruction.command == "workflow"
        assert instruction.args == ["创建", "用户注册API"]
        assert instruction.kwargs["workflow_type"] == "standard"

    def test_parse_multi_workflow_instruction(self, processor):
        """测试多工作流指令解析"""
        instruction = processor.parse_instruction("/iccc/multi-workflow \"重构项目架构\"")

        assert isinstance(instruction, WorkflowInstruction)
        assert instruction.type == InstructionType.WORKFLOW
        assert instruction.command == "multi-workflow"
        assert instruction.kwargs["workflow_type"] == "complex"
        assert instruction.kwargs["parallel_enabled"] == True

    def test_parse_thinking_instruction(self, processor):
        """测试思考指令解析"""
        instruction = processor.parse_instruction("/iccc/ultra \"分析数据库性能\"")

        assert isinstance(instruction, ThinkingInstruction)
        assert instruction.type == InstructionType.THINKING
        assert instruction.command == "ultra"
        assert instruction.kwargs["analysis_depth"] == "deep"
        assert "architecture" in instruction.kwargs["focus_areas"]

    def test_parse_invalid_instruction(self, processor):
        """测试无效指令解析"""
        with pytest.raises(ValueError, match="Empty command"):
            processor.parse_instruction("")

        with pytest.raises(ValueError, match="Unknown instruction"):
            processor.parse_instruction("/iccc/unknown_command")

    @pytest.mark.asyncio
    async def test_execute_workflow_instruction(self, processor):
        """测试工作流指令执行"""
        instruction = processor.parse_instruction("/iccc/workflow \"创建用户注册API\"")
        result = await processor.execute_instruction(instruction)

        assert result["workflow_type"] == "standard"
        assert result["status"] == "started"
        assert "需求分析" in result["steps"]
        assert instruction.status == InstructionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_spec_instruction(self, processor, tmp_path):
        """测试规格创建指令执行"""
        with patch('iccc.core.instruction_processor.Path') as mock_path:
            mock_path.return_value = tmp_path
            mock_path.return_value.mkdir = mock.Mock()

            instruction = processor.parse_instruction("/iccc/spec \"实现支付系统\"")
            result = await processor.execute_instruction(instruction)

            assert result["status"] == "created"
            assert "spec_file" in result
            assert instruction.status == InstructionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_thinking_instruction(self, processor):
        """测试思考指令执行"""
        instruction = processor.parse_instruction("/iccc/ultra \"分析数据库性能\"")
        result = await processor.execute_instruction(instruction)

        assert result["analysis_type"] == "ultra"
        assert result["depth"] == "deep"
        assert "architecture" in result["focus_areas"]
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_instruction_error_handling(self, processor):
        """测试指令错误处理"""
        instruction = processor.parse_instruction("/iccc/workflow \"测试错误处理\"")

        # 模拟执行错误
        with patch.object(processor, '_execute_workflow_instruction', side_effect=Exception("执行错误")):
            with pytest.raises(Exception):
                await processor.execute_instruction(instruction)

            assert instruction.status == InstructionStatus.FAILED
            assert instruction.error == "执行错误"

    def test_instruction_status_management(self, processor):
        """测试指令状态管理"""
        instruction = processor.parse_instruction("/iccc/workflow \"测试状态管理\"")

        # 初始状态
        assert instruction.status == InstructionStatus.PENDING

        # 手动设置状态
        processor.cancel_instruction(instruction.id)
        assert instruction.status == InstructionStatus.CANCELLED

        # 测试不存在的指令
        assert processor.cancel_instruction("nonexistent") == False

    def test_active_instructions_tracking(self, processor):
        """测试活跃指令跟踪"""
        # 添加几个活跃指令
        processor.parse_instruction("/iccc/workflow \"任务1\"")
        processor.parse_instruction("/iccc/ultra \"任务2\"")

        active_list = processor.list_active_instructions()
        assert len(active_list) == 2

        # 验证指令信息
        for inst in active_list:
            assert "id" in inst
            assert "type" in inst
            assert "command" in inst
            assert "status" in inst

    @pytest.mark.asyncio
    async def test_instruction_id_generation(self, processor):
        """测试指令ID生成"""
        instruction1 = processor.parse_instruction("/iccc/workflow \"任务1\"")
        instruction2 = processor.parse_instruction("/iccc/workflow \"任务2\"")

        assert instruction1.id != instruction2.id
        assert instruction1.id.startswith("workflow_")
        assert instruction2.id.startswith("workflow_")

    @pytest.mark.asyncio
    async def test_concurrent_instruction_execution(self, processor):
        """测试并发指令执行"""
        import asyncio

        async def execute_instruction(command):
            instruction = processor.parse_instruction(command)
            return await processor.execute_instruction(instruction)

        # 并发执行多个指令
        tasks = [
            execute_instruction("/iccc/workflow \"任务1\""),
            execute_instruction("/iccc/ultra \"分析任务\""),
            execute_instruction("/iccc/spec \"规格任务\"")
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 验证所有指令都成功执行
        for result in results:
            if not isinstance(result, Exception):
                assert result["status"] in ["started", "created", "completed"]

    def test_instruction_metadata(self, processor):
        """测试指令元数据"""
        instruction = processor.parse_instruction("/iccc/workflow \"带元数据的任务\"")

        # 设置元数据
        instruction.metadata["priority"] = "high"
        instruction.metadata["tags"] = ["api", "backend"]

        # 验证元数据
        assert instruction.metadata["priority"] == "high"
        assert "tags" in instruction.metadata
        assert "backend" in instruction.metadata["tags"]


class TestWorkflowInstruction:
    """工作流指令测试"""

    def test_workflow_instruction_creation(self):
        """测试工作流指令创建"""
        instruction = WorkflowInstruction(
            id="test_123",
            type=InstructionType.WORKFLOW,
            command="workflow",
            args=["测试", "工作流"],
            workflow_type="complex"
        )

        assert instruction.workflow_type == "complex"
        assert instruction.parallel_enabled == True  # 默认值

    def test_workflow_instruction_with_input_specs(self):
        """测试带输入规格的工作流指令"""
        instruction = WorkflowInstruction(
            id="test_123",
            type=InstructionType.WORKFLOW,
            command="spec",
            args=["@specs/user-auth.md", "实现用户认证"],
            input_specs=["@specs/user-auth.md"]
        )

        assert len(instruction.input_specs) == 1
        assert instruction.input_specs[0] == "@specs/user-auth.md"


class TestThinkingInstruction:
    """思考指令测试"""

    def test_thinking_instruction_creation(self):
        """测试思考指令创建"""
        instruction = ThinkingInstruction(
            id="test_123",
            type=InstructionType.THINKING,
            command="ultra",
            args=["分析复杂问题"],
            analysis_depth="deep"
        )

        assert instruction.analysis_depth == "deep"
        assert "architecture" in instruction.kwargs["focus_areas"]

    def test_reflection_instruction_target(self):
        """测试反思指令目标"""
        instruction = ThinkingInstruction(
            id="test_123",
            type=InstructionType.THINKING,
            command="reflection",
            args=["刚刚完成的用户认证实现"],
            reflection_target="用户认证实现"
        )

        assert instruction.reflection_target == "用户认证实现"


@pytest.mark.asyncio
async def test_process_instruction_function():
    """测试process_instruction便捷函数"""
    from iccc.core.instruction_processor import get_instruction_processor

    # 模拟获取处理器
    processor = get_instruction_processor()

    # 测试指令处理
    instruction = await process_instruction("/iccc/workflow \"测试便捷函数\"")

    assert isinstance(instruction, Instruction)
    assert instruction.type == InstructionType.WORKFLOW
    assert instruction.status == InstructionStatus.COMPLETED


class TestInstructionIntegration:
    """指令集成测试"""

    @pytest.mark.asyncio
    async def test_full_instruction_lifecycle(self, processor):
        """测试完整指令生命周期"""
        # 1. 解析指令
        instruction = processor.parse_instruction("/iccc/workflow \"完整生命周期测试\"")

        # 2. 验证指令状态
        assert instruction.status == InstructionStatus.PENDING

        # 3. 执行指令
        result = await processor.execute_instruction(instruction)

        # 4. 验证执行结果
        assert instruction.status == InstructionStatus.COMPLETED
        assert result["status"] == "started"

        # 5. 验证历史记录
        active_list = processor.list_active_instructions()
        # 指令已完成，不应在活跃列表中

    def test_instruction_processor_state_reset(self, processor):
        """测试指令处理器状态重置"""
        # 添加一些指令
        processor.parse_instruction("/iccc/workflow \"任务1\"")
        processor.parse_instruction("/iccc/workflow \"任务2\"")

        # 验证有活跃指令
        assert len(processor.list_active_instructions()) > 0

        # 清空活跃指令（模拟重启）
        processor.active_instructions.clear()

        # 验证清空成功
        assert len(processor.list_active_instructions()) == 0