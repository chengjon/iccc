"""
iCCC 核心模块

包含指令处理、通信机制、Hook系统等核心功能。
"""

from .instruction_processor import (
    Instruction,
    InstructionProcessor,
    InstructionStatus,
    InstructionType,
    get_instruction_processor,
    process_instruction
)

from .multi_cli_communication import (
    Event,
    EventType,
    EventPriority,
    MultiCLIBus,
    WorkflowCoordinator,
    get_event_bus,
    get_workflow_coordinator,
    initialize_multi_cli_system
)

from .hook_system import (
    Hook,
    HookAction,
    HookResult,
    HookSystem,
    HookType,
    get_hook_system,
    execute_hooks,
    get_default_hooks
)

from .mcp_service_manager import (
    MCPServiceConfig,
    MCPServiceManager,
    MCPServiceStatus,
    MCPServiceType,
    get_mcp_manager,
    initialize_mcp_services
)

__all__ = [
    # Instruction processing
    "Instruction",
    "InstructionProcessor",
    "InstructionStatus",
    "InstructionType",
    "get_instruction_processor",
    "process_instruction",

    # Multi-CLI communication
    "Event",
    "EventType",
    "EventPriority",
    "MultiCLIBus",
    "WorkflowCoordinator",
    "get_event_bus",
    "get_workflow_coordinator",
    "initialize_multi_cli_system",

    # Hook system
    "Hook",
    "HookAction",
    "HookResult",
    "HookSystem",
    "HookType",
    "get_hook_system",
    "execute_hooks",
    "get_default_hooks",

    # MCP service management
    "MCPServiceConfig",
    "MCPServiceManager",
    "MCPServiceStatus",
    "MCPServiceType",
    "get_mcp_manager",
    "initialize_mcp_services"
]