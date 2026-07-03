"""
iCCC MCP服务管理器

管理MCP (Model Context Protocol) 服务的集成，为AI代理提供丰富的外部能力。
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiohttp
from pydantic import BaseModel, Field


class MCPServiceType(Enum):
    """MCP服务类型"""
    BROWSER_AUTOMATION = "browser_automation"
    FILE_SYSTEM = "file_system"
    DATABASE = "database"
    API_INTEGRATION = "api_integration"
    CLOUD_SERVICES = "cloud_services"
    DEVELOPMENT_TOOLS = "development_tools"
    MONITORING = "monitoring"
    MEMORY = "memory"
    SEQUENTIAL_THINKING = "sequential_thinking"


class MCPServiceStatus(Enum):
    """MCP服务状态"""
    NOT_INSTALLED = "not_installed"
    INSTALLING = "installing"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class MCPServiceConfig(BaseModel):
    """MCP服务配置"""
    name: str = Field(..., description="服务名称")
    service_type: MCPServiceType = Field(..., description="服务类型")
    version: str = Field(default="latest", description="服务版本")
    command: str = Field(..., description="启动命令")
    install_command: Optional[str] = Field(None, description="安装命令")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    port: Optional[int] = Field(None, description="服务端口")
    host: str = Field(default="localhost", description="服务主机")
    health_check_url: Optional[str] = Field(None, description="健康检查URL")
    timeout: int = Field(default=30, description="超时时间（秒）")
    auto_start: bool = Field(default=False, description="是否自动启动")
    enabled: bool = Field(default=True, description="是否启用")


class MCPServiceInstance(BaseModel):
    """MCP服务实例"""
    config: MCPServiceConfig = Field(..., description="服务配置")
    status: MCPServiceStatus = Field(default=MCPServiceStatus.NOT_INSTALLED, description="服务状态")
    process: Optional[Any] = Field(None, description="进程实例")
    start_time: Optional[datetime] = Field(None, description="启动时间")
    last_check: Optional[datetime] = Field(None, description="最后检查时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    capabilities: List[str] = Field(default_factory=list, description="服务能力")


class MCPServiceManager:
    """MCP服务管理器"""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.services: Dict[str, MCPServiceInstance] = {}
        self.service_configs: Dict[str, MCPServiceConfig] = {}
        self.available_services: Dict[str, MCPServiceConfig] = {}

        # 初始化内置服务
        self._initialize_builtin_services()

    def _initialize_builtin_services(self) -> None:
        """初始化内置MCP服务"""
        # Playwright MCP服务
        self.available_services["playwright"] = MCPServiceConfig(
            name="Playwright Browser Automation",
            service_type=MCPServiceType.BROWSER_AUTOMATION,
            version="latest",
            command="npx @modelcontextprotocol/server-playwright",
            install_command="npm install -g @modelcontextprotocol/server-playwright",
            env_vars={"PLAYWRIGHT_HEADLESS": "true"},
            port=3001,
            health_check_url="http://localhost:3001/health",
            timeout=60,
            auto_start=True,
            enabled=True
        )

        # Memory MCP服务
        self.available_services["memory"] = MCPServiceConfig(
            name="Long-term Memory Storage",
            service_type=MCPServiceType.MEMORY,
            version="latest",
            command="npx @modelcontextprotocol/server-memory",
            install_command="npm install -g @modelcontextprotocol/server-memory",
            port=3002,
            health_check_url="http://localhost:3002/health",
            timeout=30,
            auto_start=True,
            enabled=True
        )

        # Sequential Thinking MCP服务
        self.available_services["sequential-thinking"] = MCPServiceConfig(
            name="Sequential Thinking Enhancement",
            service_type=MCPServiceType.SEQUENTIAL_THINKING,
            version="latest",
            command="npx @modelcontextprotocol/server-sequential-thinking",
            install_command="npm install -g @modelcontextprotocol/server-sequential-thinking",
            port=3003,
            health_check_url="http://localhost:3003/health",
            timeout=30,
            auto_start=True,
            enabled=True
        )

        # 文件系统服务
        self.available_services["filesystem"] = MCPServiceConfig(
            name="File System Access",
            service_type=MCPServiceType.FILE_SYSTEM,
            version="latest",
            command="python -m iccc.mcp.server.filesystem",
            install_command="pip install -r requirements.txt",
            env_vars={"PYTHONPATH": str(Path(__file__).parent.parent)},
            port=3004,
            health_check_url="http://localhost:3004/health",
            timeout=30,
            auto_start=True,
            enabled=True
        )

        # Git服务
        self.available_services["git"] = MCPServiceConfig(
            name="Git Integration",
            service_type=MCPServiceType.DEVELOPMENT_TOOLS,
            version="latest",
            command="python -m iccc.mcp.server.git",
            install_command="pip install -r requirements.txt",
            env_vars={"PYTHONPATH": str(Path(__file__).parent.parent)},
            port=3005,
            health_check_url="http://localhost:3005/health",
            timeout=30,
            auto_start=False,
            enabled=True
        )

    def load_service_configs(self) -> None:
        """从配置文件加载服务配置"""
        services_config = self.config_dir / "mcp_services.json"
        if not services_config.exists():
            return

        try:
            with open(services_config, 'r', encoding='utf-8') as f:
                config = json.load(f)

            for service_name, service_config in config.get("services", {}).items():
                # 更新可用服务的配置
                if service_name in self.available_services:
                    self.available_services[service_name].update(**service_config)

        except Exception as e:
            print(f"Error loading MCP services config: {e}")

    def list_available_services(self) -> List[Dict[str, Any]]:
        """列出可用服务"""
        return [
            {
                "name": name,
                "type": service.service_type.value,
                "version": service.version,
                "enabled": service.enabled,
                "auto_start": service.auto_start,
                "description": self._get_service_description(service.service_type)
            }
            for name, service in self.available_services.items()
        ]

    def _get_service_description(self, service_type: MCPServiceType) -> str:
        """获取服务描述"""
        descriptions = {
            MCPServiceType.BROWSER_AUTOMATION: "浏览器自动化控制",
            MCPServiceType.FILE_SYSTEM: "文件系统访问",
            MCPServiceType.DATABASE: "数据库操作",
            MCPServiceType.API_INTEGRATION: "API集成",
            MCPServiceType.CLOUD_SERVICES: "云服务集成",
            MCPServiceType.DEVELOPMENT_TOOLS: "开发工具",
            MCPServiceType.MONITORING: "监控和日志",
            MCPServiceType.MEMORY: "长期记忆存储",
            MCPServiceType.SEQUENTIAL_THINKING: "结构化思维增强"
        }
        return descriptions.get(service_type, "未知服务")

    async def install_service(self, service_name: str) -> bool:
        """安装MCP服务"""
        if service_name not in self.available_services:
            return False

        service_config = self.available_services[service_name]
        if not service_config.install_command:
            return True

        try:
            process = await asyncio.create_subprocess_shell(
                service_config.install_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                print(f"✅ Service {service_name} installed successfully")
                return True
            else:
                print(f"❌ Service {service_name} installation failed: {stderr.decode('utf-8')}")
                return False

        except Exception as e:
            print(f"❌ Error installing service {service_name}: {e}")
            return False

    async def start_service(self, service_name: str) -> bool:
        """启动MCP服务"""
        if service_name not in self.available_services:
            return False

        service_config = self.available_services[service_name]

        # 如果服务已存在，先停止
        if service_name in self.services:
            await self.stop_service(service_name)

        try:
            # 构建环境变量
            env = {**service_config.env_vars, **os.environ.copy()}

            # 启动服务
            process = await asyncio.create_subprocess_shell(
                service_config.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            # 创建服务实例
            service_instance = MCPServiceInstance(
                config=service_config,
                status=MCPServiceStatus.RUNNING,
                process=process,
                start_time=datetime.now()
            )

            self.services[service_name] = service_instance

            # 等待服务启动
            await asyncio.sleep(2)

            # 检查服务状态
            if await self._check_service_health(service_name):
                print(f"✅ Service {service_name} started successfully")
                return True
            else:
                await self.stop_service(service_name)
                return False

        except Exception as e:
            print(f"❌ Error starting service {service_name}: {e}")
            return False

    async def stop_service(self, service_name: str) -> bool:
        """停止MCP服务"""
        if service_name not in self.services:
            return True

        service_instance = self.services[service_name]

        try:
            if service_instance.process:
                service_instance.process.terminate()
                await service_instance.process.wait(timeout=10)
                service_instance.process = None

            service_instance.status = MCPServiceStatus.STOPPED
            service_instance.start_time = None
            del self.services[service_name]

            print(f"✅ Service {service_name} stopped successfully")
            return True

        except Exception as e:
            print(f"❌ Error stopping service {service_name}: {e}")
            return False

    async def _check_service_health(self, service_name: str) -> bool:
        """检查服务健康状态"""
        if service_name not in self.available_services:
            return False

        service_config = self.available_services[service_name]
        if not service_config.health_check_url:
            return True

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(service_config.health_check_url, timeout=5) as response:
                    if response.status == 200:
                        # 更新服务状态
                        if service_name in self.services:
                            self.services[service_name].status = MCPServiceStatus.RUNNING
                            self.services[service_name].last_check = datetime.now()
                        return True
                    else:
                        if service_name in self.services:
                            self.services[service_name].status = MCPServiceStatus.ERROR
                            self.services[service_name].error_message = f"Health check failed: {response.status}"
                        return False

        except Exception as e:
            if service_name in self.services:
                self.services[service_name].status = MCPServiceStatus.ERROR
                self.services[service_name].error_message = str(e)
            return False

    async def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """获取服务状态"""
        if service_name not in self.available_services:
            return None

        if service_name in self.services:
            service_instance = self.services[service_name]
            return {
                "name": service_name,
                "status": service_instance.status.value,
                "start_time": service_instance.start_time.isoformat() if service_instance.start_time else None,
                "last_check": service_instance.last_check.isoformat() if service_instance.last_check else None,
                "error_message": service_instance.error_message,
                "capabilities": service_instance.capabilities
            }
        else:
            service_config = self.available_services[service_name]
            return {
                "name": service_name,
                "status": "not_running",
                "enabled": service_config.enabled,
                "auto_start": service_config.auto_start,
                "description": self._get_service_description(service_config.service_type)
            }

    async def start_all_services(self) -> Dict[str, bool]:
        """启动所有启用的服务"""
        results = {}

        # 先安装未安装的服务
        for service_name in self.available_services:
            service_config = self.available_services[service_name]
            if service_config.auto_start and service_config.install_command:
                results[service_name] = await self.install_service(service_name)

        # 启动服务
        for service_name in self.available_services:
            service_config = self.available_services[service_name]
            if service_config.auto_start and service_config.enabled:
                results[service_name] = await self.start_service(service_name)

        return results

    async def stop_all_services(self) -> Dict[str, bool]:
        """停止所有服务"""
        results = {}

        for service_name in list(self.services.keys()):
            results[service_name] = await self.stop_service(service_name)

        return results

    async def get_service_capabilities(self, service_name: str) -> List[str]:
        """获取服务能力"""
        if service_name not in self.available_services:
            return []

        # 这里可以根据服务类型返回默认能力
        # 实际应该从服务API获取
        capabilities_map = {
            "playwright": ["browser_navigate", "browser_click", "browser_fill", "browser_screenshot"],
            "memory": ["store_memory", "retrieve_memory", "search_memory", "delete_memory"],
            "sequential-thinking": ["think_step_by_step", "break_down_complex", "reason_systematically"],
            "filesystem": ["read_file", "write_file", "list_files", "create_directory"],
            "git": ["commit_changes", "create_branch", "merge_branch", "push_changes"]
        }

        return capabilities_map.get(service_name, [])

    def create_service_config(self) -> None:
        """创建服务配置文件"""
        config = {
            "services": {
                name: {
                    "version": service.version,
                    "enabled": service.enabled,
                    "auto_start": service.auto_start,
                    "env_vars": service.env_vars,
                    "port": service.port,
                    "timeout": service.timeout
                }
                for name, service in self.available_services.items()
            }
        }

        with open(self.config_dir / "mcp_services.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    async def execute_service_command(self, service_name: str, command: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行服务命令"""
        if service_name not in self.services:
            return {"success": False, "message": f"Service {service_name} not running"}

        service_instance = self.services[service_name]
        if service_instance.status != MCPServiceStatus.RUNNING:
            return {"success": False, "message": f"Service {service_name} not running"}

        try:
            # 这里应该调用服务的API
            # 现在返回模拟结果
            return {
                "success": True,
                "message": "Command executed successfully",
                "result": {"command": command, "params": params}
            }

        except Exception as e:
            return {"success": False, "message": f"Command execution failed: {str(e)}"}

    def get_service_statistics(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        total_services = len(self.available_services)
        running_services = len([s for s in self.services.values() if s.status == MCPServiceStatus.RUNNING])
        enabled_services = len([s for s in self.available_services.values() if s.enabled])
        auto_start_services = len([s for s in self.available_services.values() if s.auto_start])

        return {
            "total_services": total_services,
            "running_services": running_services,
            "enabled_services": enabled_services,
            "auto_start_services": auto_start_services,
            "services_status": {
                name: instance.status.value for name, instance in self.services.items()
            }
        }


# 全局MCP服务管理器实例
_mcp_manager: Optional[MCPServiceManager] = None


def get_mcp_manager() -> MCPServiceManager:
    """获取全局MCP服务管理器"""
    global _mcp_manager
    if _mcp_manager is None:
        config_dir = Path(__file__).parent.parent / ".iccc" / "config"
        _mcp_manager = MCPServiceManager(config_dir)
        _mcp_manager.load_service_configs()
    return _mcp_manager


async def initialize_mcp_services() -> Dict[str, bool]:
    """初始化MCP服务"""
    manager = get_mcp_manager()
    return await manager.start_all_services()


async def example_usage():
    """使用示例"""
    # 获取MCP服务管理器
    manager = get_mcp_manager()

    # 列出可用服务
    print("Available services:")
    for service in manager.list_available_services():
        print(f"  - {service['name']} ({service['type']})")

    # 启动所有服务
    print("\nStarting services...")
    results = await manager.start_all_services()
    for service_name, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {service_name}")

    # 检查服务状态
    print("\nService status:")
    for service_name in manager.available_services:
        status_info = await manager.get_service_status(service_name)
        if status_info:
            print(f"  {service_name}: {status_info['status']}")

    # 获取服务统计
    stats = manager.get_service_statistics()
    print(f"\nService statistics: {stats}")

    # 停止所有服务
    print("\nStopping services...")
    stop_results = await manager.stop_all_services()
    for service_name, success in stop_results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {service_name}")