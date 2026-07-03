"""
iCCC MCP服务管理器测试

测试MCP服务的集成、管理和功能。
"""

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from iccc.core.mcp_service_manager import (
    MCPServiceConfig,
    MCPServiceInstance,
    MCPServiceManager,
    MCPServiceStatus,
    MCPServiceType,
    get_mcp_manager,
    initialize_mcp_services
)


class TestMCPServiceConfig:
    """MCP服务配置测试"""

    def test_service_config_creation(self):
        """测试服务配置创建"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            version="1.0.0",
            command="python test_service.py",
            install_command="pip install test-service",
            env_vars={"TEST_VAR": "value"},
            port=3000,
            host="localhost",
            health_check_url="http://localhost:3000/health",
            timeout=30,
            auto_start=True,
            enabled=True
        )

        assert config.name == "Test Service"
        assert config.service_type == MCPServiceType.FILE_SYSTEM
        assert config.version == "1.0.0"
        assert config.command == "python test_service.py"
        assert config.install_command == "pip install test-service"
        assert config.env_vars == {"TEST_VAR": "value"}
        assert config.port == 3000
        assert config.host == "localhost"
        assert config.health_check_url == "http://localhost:3000/health"
        assert config.timeout == 30
        assert config.auto_start is True
        assert config.enabled is True

    def test_service_config_defaults(self):
        """测试服务配置默认值"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test_service.py"
        )

        assert config.version == "latest"
        assert config.install_command is None
        assert config.env_vars == {}
        assert config.port is None
        assert config.host == "localhost"
        assert config.health_check_url is None
        assert config.timeout == 30
        assert config.auto_start is False
        assert config.enabled is True


class TestMCPServiceInstance:
    """MCP服务实例测试"""

    def test_service_instance_creation(self):
        """测试服务实例创建"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test_service.py"
        )

        instance = MCPServiceInstance(
            config=config,
            status=MCPServiceStatus.RUNNING,
            process=Mock(),
            start_time=datetime.now(),
            last_check=datetime.now(),
            capabilities=["read", "write"]
        )

        assert instance.config == config
        assert instance.status == MCPServiceStatus.RUNNING
        assert instance.process is not None
        assert instance.start_time is not None
        assert instance.last_check is not None
        assert instance.capabilities == ["read", "write"]

    def test_service_instance_defaults(self):
        """测试服务实例默认值"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test_service.py"
        )

        instance = MCPServiceInstance(config=config)

        assert instance.config == config
        assert instance.status == MCPServiceStatus.NOT_INSTALLED
        assert instance.process is None
        assert instance.start_time is None
        assert instance.last_check is None
        assert instance.capabilities == []


class TestMCPServiceType:
    """MCP服务类型测试"""

    def test_service_type_enum_values(self):
        """测试服务类型枚举值"""
        assert MCPServiceType.BROWSER_AUTOMATION.value == "browser_automation"
        assert MCPServiceType.FILE_SYSTEM.value == "file_system"
        assert MCPServiceType.DATABASE.value == "database"
        assert MCPServiceType.API_INTEGRATION.value == "api_integration"
        assert MCPServiceType.CLOUD_SERVICES.value == "cloud_services"
        assert MCPServiceType.DEVELOPMENT_TOOLS.value == "development_tools"
        assert MCPServiceType.MONITORING.value == "monitoring"
        assert MCPServiceType.MEMORY.value == "memory"
        assert MCPServiceType.SEQUENTIAL_THINKING.value == "sequential_thinking"

    def test_service_type_from_value(self):
        """测试从值获取服务类型"""
        assert MCPServiceType("browser_automation") == MCPServiceType.BROWSER_AUTOMATION
        assert MCPServiceType("file_system") == MCPServiceType.FILE_SYSTEM


class TestMCPServiceStatus:
    """MCP服务状态测试"""

    def test_service_status_enum_values(self):
        """测试服务状态枚举值"""
        assert MCPServiceStatus.NOT_INSTALLED.value == "not_installed"
        assert MCPServiceStatus.INSTALLING.value == "installing"
        assert MCPServiceStatus.RUNNING.value == "running"
        assert MCPServiceStatus.STOPPED.value == "stopped"
        assert MCPServiceStatus.ERROR.value == "error"

    def test_service_status_from_value(self):
        """测试从值获取服务状态"""
        assert MCPServiceStatus("running") == MCPServiceStatus.RUNNING
        assert MCPServiceStatus("stopped") == MCPServiceStatus.STOPPED


class TestMCPServiceManager:
    """MCP服务管理器测试"""

    @pytest.fixture
    def temp_config_dir(self):
        """创建临时配置目录"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()
            yield config_dir

    @pytest.fixture
    def mcp_manager(self, temp_config_dir):
        """创建MCP服务管理器实例"""
        return MCPServiceManager(temp_config_dir)

    def test_mcp_manager_initialization(self, temp_config_dir):
        """测试MCP服务管理器初始化"""
        manager = MCPServiceManager(temp_config_dir)

        assert manager.config_dir == temp_config_dir
        assert manager.services == {}
        assert manager.service_configs == {}
        assert len(manager.available_services) > 0  # 应该有内置服务

    def test_initialize_builtin_services(self, mcp_manager):
        """测试初始化内置服务"""
        # 验证内置服务存在
        assert "playwright" in mcp_manager.available_services
        assert "memory" in mcp_manager.available_services
        assert "sequential-thinking" in mcp_manager.available_services
        assert "filesystem" in mcp_manager.available_services
        assert "git" in mcp_manager.available_services

    def test_builtin_service_configurations(self, mcp_manager):
        """测试内置服务配置"""
        # 测试Playwright配置
        playwright_config = mcp_manager.available_services["playwright"]
        assert playwright_config.name == "Playwright Browser Automation"
        assert playwright_config.service_type == MCPServiceType.BROWSER_AUTOMATION
        assert playwright_config.command == "npx @modelcontextprotocol/server-playwright"
        assert playwright_config.install_command == "npm install -g @modelcontextprotocol/server-playwright"
        assert playwright_config.port == 3001
        assert playwright_config.auto_start is True

        # 测试Memory配置
        memory_config = mcp_manager.available_services["memory"]
        assert memory_config.name == "Long-term Memory Storage"
        assert memory_config.service_type == MCPServiceType.MEMORY
        assert memory_config.port == 3002

        # 测试Sequential Thinking配置
        thinking_config = mcp_manager.available_services["sequential-thinking"]
        assert thinking_config.name == "Sequential Thinking Enhancement"
        assert thinking_config.service_type == MCPServiceType.SEQUENTIAL_THINKING
        assert thinking_config.port == 3003

    def test_get_service_description(self, mcp_manager):
        """测试获取服务描述"""
        descriptions = {
            MCPServiceType.BROWSER_AUTOMATION: "浏览器自动化控制",
            MCPServiceType.FILE_SYSTEM: "文件系统访问",
            MCPServiceType.DATABASE: "数据库操作",
            MCPServiceType.MEMORY: "长期记忆存储",
            MCPServiceType.SEQUENTIAL_THINKING: "结构化思维增强"
        }

        for service_type, expected_desc in descriptions.items():
            assert mcp_manager._get_service_description(service_type) == expected_desc

    def test_list_available_services(self, mcp_manager):
        """测试列出可用服务"""
        services = mcp_manager.list_available_services()

        assert isinstance(services, list)
        assert len(services) > 0

        # 检查服务信息结构
        for service in services:
            assert "name" in service
            assert "type" in service
            assert "version" in service
            assert "enabled" in service
            assert "auto_start" in service
            assert "description" in service

    def test_get_service_status_running_service(self, mcp_manager):
        """测试获取正在运行的服务状态"""
        # 模拟正在运行的服务
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test_service.py"
        )

        instance = MCPServiceInstance(
            config=config,
            status=MCPServiceStatus.RUNNING,
            start_time=datetime.now(),
            last_check=datetime.now(),
            capabilities=["read", "write"]
        )

        mcp_manager.services["test_service"] = instance

        status = mcp_manager.get_service_status("test_service")

        assert status is not None
        assert status["name"] == "test_service"
        assert status["status"] == "running"
        assert status["start_time"] is not None
        assert status["last_check"] is not None
        assert status["capabilities"] == ["read", "write"]

    def test_get_service_status_not_running_service(self, mcp_manager):
        """测试获取未运行的服务状态"""
        status = mcp_manager.get_service_status("filesystem")

        assert status is not None
        assert status["name"] == "filesystem"
        assert status["status"] == "not_running"
        assert status["enabled"] is True
        assert status["auto_start"] is True
        assert "description" in status

    def test_get_service_status_nonexistent_service(self, mcp_manager):
        """测试获取不存在服务的状态"""
        status = mcp_manager.get_service_status("nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_service_capabilities(self, mcp_manager):
        """测试获取服务能力"""
        capabilities = await mcp_manager.get_service_capabilities("playwright")

        assert isinstance(capabilities, list)
        assert "browser_navigate" in capabilities
        assert "browser_click" in capabilities
        assert "browser_fill" in capabilities
        assert "browser_screenshot" in capabilities

    @pytest.mark.asyncio
    async def test_get_service_capabilities_nonexistent_service(self, mcp_manager):
        """测试获取不存在服务的能力"""
        capabilities = await mcp_manager.get_service_capabilities("nonexistent")
        assert capabilities == []

    def test_create_service_config(self, mcp_manager, temp_config_dir):
        """测试创建服务配置文件"""
        config_file = temp_config_dir / "mcp_services.json"

        # 确保文件不存在
        if config_file.exists():
            config_file.unlink()

        mcp_manager.create_service_config()

        assert config_file.exists()

        # 读取并验证配置
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        assert "services" in config
        assert "playwright" in config["services"]
        assert "memory" in config["services"]

    @pytest.mark.asyncio
    async def test_load_service_configs(self, mcp_manager, temp_config_dir):
        """测试从配置文件加载服务配置"""
        # 创建配置文件
        config_data = {
            "services": {
                "playwright": {
                    "version": "1.2.3",
                    "enabled": False,
                    "auto_start": False,
                    "port": 3005
                },
                "memory": {
                    "version": "2.0.0",
                    "enabled": True,
                    "auto_start": True,
                    "timeout": 60
                }
            }
        }

        config_file = temp_config_dir / "mcp_services.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)

        # 加载配置
        mcp_manager.load_service_configs()

        # 验证配置更新
        assert mcp_manager.available_services["playwright"].version == "1.2.3"
        assert mcp_manager.available_services["playwright"].enabled is False
        assert mcp_manager.available_services["playwright"].auto_start is False
        assert mcp_manager.available_services["playwright"].port == 3005

        assert mcp_manager.available_services["memory"].version == "2.0.0"
        assert mcp_manager.available_services["memory"].enabled is True
        assert mcp_manager.available_services["memory"].auto_start is True
        assert mcp_manager.available_services["memory"].timeout == 60

    @pytest.mark.asyncio
    async def test_get_service_statistics(self, mcp_manager):
        """测试获取服务统计信息"""
        # 添加一些模拟服务
        config = MCPServiceConfig(
            name="Test Service 1",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test1.py"
        )
        instance1 = MCPServiceInstance(config=config, status=MCPServiceStatus.RUNNING)

        config2 = MCPServiceConfig(
            name="Test Service 2",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test2.py"
        )
        instance2 = MCPServiceInstance(config=config2, status=MCPServiceStatus.STOPPED)

        mcp_manager.services["service1"] = instance1
        mcp_manager.services["service2"] = instance2

        stats = mcp_manager.get_service_statistics()

        assert stats["total_services"] == len(mcp_manager.available_services)
        assert stats["running_services"] == 1
        assert stats["enabled_services"] == len([s for s in mcp_manager.available_services.values() if s.enabled])
        assert stats["auto_start_services"] == len([s for s in mcp_manager.available_services.values() if s.auto_start])
        assert "services_status" in stats
        assert "service1" in stats["services_status"]
        assert "service2" in stats["services_status"]


class TestMCPServiceLifecycle:
    """MCP服务生命周期测试"""

    @pytest.fixture
    def mcp_manager(self):
        """创建MCP服务管理器实例"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()
            yield MCPServiceManager(config_dir)

    @pytest.mark.asyncio
    async def test_install_service_success(self, mcp_manager):
        """测试成功安装服务"""
        # 模拟安装命令成功
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"success", b"")
            mock_subprocess.return_value = mock_process

            result = await mcp_manager.install_service("memory")

            assert result is True
            mock_subprocess.assert_called_once()

    @pytest.mark.asyncio
    async def test_install_service_failure(self, mcp_manager):
        """测试安装服务失败"""
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"Install failed")
            mock_subprocess.return_value = mock_process

            result = await mcp_manager.install_service("memory")

            assert result is False

    @pytest.mark.asyncio
    async def test_install_service_no_install_command(self, mcp_manager):
        """测试没有安装命令的服务"""
        result = await mcp_manager.install_service("filesystem")
        assert result is True  # 没有安装命令，直接返回成功

    @pytest.mark.asyncio
    async def test_install_nonexistent_service(self, mcp_manager):
        """测试安装不存在服务"""
        result = await mcp_manager.install_service("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_start_service_success(self, mcp_manager):
        """测试成功启动服务"""
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with patch.object(mcp_manager, '_check_service_health', return_value=True):
                result = await mcp_manager.start_service("memory")

                assert result is True
                assert "memory" in mcp_manager.services
                assert mcp_manager.services["memory"].status == MCPServiceStatus.RUNNING

    @pytest.mark.asyncio
    async def test_start_service_health_check_failure(self, mcp_manager):
        """测试服务启动后健康检查失败"""
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with patch.object(mcp_manager, '_check_service_health', return_value=False):
                result = await mcp_manager.start_service("memory")

                assert result is False
                assert "memory" not in mcp_manager.services  # 应该被清理

    @pytest.mark.asyncio
    async def test_stop_service_success(self, mcp_manager):
        """测试成功停止服务"""
        # 添加一个运行中的服务
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test.py"
        )
        process = Mock()
        instance = MCPServiceInstance(
            config=config,
            status=MCPServiceStatus.RUNNING,
            process=process,
            start_time=datetime.now()
        )
        mcp_manager.services["test_service"] = instance

        result = await mcp_manager.stop_service("test_service")

        assert result is True
        assert process.terminate.called
        assert process.wait.called
        assert "test_service" not in mcp_manager.services

    @pytest.mark.asyncio
    async def test_stop_nonexistent_service(self, mcp_manager):
        """测试停止不存在服务"""
        result = await mcp_manager.stop_service("nonexistent")
        assert result is True  # 不存在的服务应该返回成功

    @pytest.mark.asyncio
    async def test_stop_service_not_running(self, mcp_manager):
        """测试停止未运行的服务"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test.py"
        )
        instance = MCPServiceInstance(config=config, status=MCPServiceStatus.STOPPED)
        mcp_manager.services["test_service"] = instance

        result = await mcp_manager.stop_service("test_service")

        assert result is True
        assert instance.status == MCPServiceStatus.STOPPED

    @pytest.mark.asyncio
    async def test_service_stopping_failure(self, mcp_manager):
        """测试服务停止失败"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test.py"
        )
        process = Mock()
        process.terminate.side_effect = Exception("Stop failed")
        instance = MCPServiceInstance(
            config=config,
            status=MCPServiceStatus.RUNNING,
            process=process,
            start_time=datetime.now()
        )
        mcp_manager.services["test_service"] = instance

        result = await mcp_manager.stop_service("test_service")

        assert result is False
        assert process.terminate.called

    @pytest.mark.asyncio
    async def test_check_service_health_success(self, mcp_manager):
        """测试成功检查服务健康状态"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            config = MCPServiceConfig(
                name="Test Service",
                service_type=MCPServiceType.FILE_SYSTEM,
                command="python test.py",
                health_check_url="http://localhost:3000/health"
            )

            result = await mcp_manager._check_service_health("test_service", config)

            assert result is True
            assert mock_session.return_value.__aenter__.return_value.get.called

    @pytest.mark.asyncio
    async def test_check_service_health_failure(self, mcp_manager):
        """测试服务健康检查失败"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            config = MCPServiceConfig(
                name="Test Service",
                service_type=MCPServiceType.FILE_SYSTEM,
                command="python test.py",
                health_check_url="http://localhost:3000/health"
            )

            result = await mcp_manager._check_service_health("test_service", config)

            assert result is False

    @pytest.mark.asyncio
    async def test_check_service_health_no_health_check_url(self, mcp_manager):
        """测试没有健康检查URL的服务"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test.py"
        )

        result = await mcp_manager._check_service_health("test_service", config)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_service_health_exception(self, mcp_manager):
        """测试健康检查异常"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session.side_effect = Exception("Connection failed")

            config = MCPServiceConfig(
                name="Test Service",
                service_type=MCPServiceType.FILE_SYSTEM,
                command="python test.py",
                health_check_url="http://localhost:3000/health"
            )

            result = await mcp_manager._check_service_health("test_service", config)
            assert result is False


class TestMCPServiceCommandExecution:
    """MCP服务命令执行测试"""

    @pytest.fixture
    def mcp_manager(self):
        """创建MCP服务管理器实例"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / "config"
            config_dir.mkdir()
            yield MCPServiceManager(config_dir)

    @pytest.mark.asyncio
    async def test_execute_service_command_success(self, mcp_manager):
        """测试成功执行服务命令"""
        # 添加运行中的服务
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test.py"
        )
        instance = MCPServiceInstance(
            config=config,
            status=MCPServiceStatus.RUNNING,
            process=Mock()
        )
        mcp_manager.services["test_service"] = instance

        result = await mcp_manager.execute_service_command("test_service", "test_command", {"param": "value"})

        assert result["success"] is True
        assert "Command executed successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_service_command_not_running(self, mcp_manager):
        """测试执行未运行服务的命令"""
        result = await mcp_manager.execute_service_command("not_running", "test_command", {})

        assert result["success"] is False
        assert "Service not running" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_service_command_error(self, mcp_manager):
        """测试执行服务命令错误"""
        config = MCPServiceConfig(
            name="Test Service",
            service_type=MCPServiceType.FILE_SYSTEM,
            command="python test.py"
        )
        instance = MCPServiceInstance(
            config=config,
            status=MCPServiceStatus.RUNNING,
            process=Mock()
        )
        mcp_manager.services["test_service"] = instance

        # 模拟执行错误
        with patch('iccc.core.mcp_service_manager.asyncio.sleep', side_effect=Exception("Execution error")):
            result = await mcp_manager.execute_service_command("test_service", "test_command", {})

            assert result["success"] is False
            assert "Command execution error" in result["message"]


class TestGlobalMCPManager:
    """全局MCP管理器测试"""

    def test_get_mcp_manager_singleton(self):
        """测试获取全局MCP管理器单例"""
        manager1 = get_mcp_manager()
        manager2 = get_mcp_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_initialize_mcp_services(self):
        """测试初始化MCP服务"""
        with patch.object(get_mcp_manager(), 'start_all_services') as mock_start:
            mock_start.return_value = {"service1": True, "service2": False}

            result = await initialize_mcp_services()

            assert result == {"service1": True, "service2": False}
            mock_start.assert_called_once()


class TestMCPIntegration:
    """MCP集成测试"""

    @pytest.mark.asyncio
    async def test_full_service_lifecycle(self, mcp_manager):
        """测试完整的服务生命周期"""
        # 1. 初始化时应该有内置服务
        assert len(mcp_manager.available_services) > 0

        # 2. 获取服务状态（未运行）
        status = mcp_manager.get_service_status("memory")
        assert status is not None
        assert status["status"] == "not_running"

        # 3. 尝试启动服务
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with patch.object(mcp_manager, '_check_service_health', return_value=True):
                result = await mcp_manager.start_service("memory")
                assert result is True

        # 4. 获取服务状态（运行中）
        status = mcp_manager.get_service_status("memory")
        assert status is not None
        assert status["status"] == "running"

        # 5. 获取服务能力
        capabilities = await mcp_manager.get_service_capabilities("memory")
        assert isinstance(capabilities, list)
        assert len(capabilities) > 0

        # 6. 执行服务命令
        command_result = await mcp_manager.execute_service_command("memory", "test", {"param": "value"})
        assert command_result["success"] is True

        # 7. 停止服务
        result = await mcp_manager.stop_service("memory")
        assert result is True

        # 8. 验证服务已停止
        status = mcp_manager.get_service_status("memory")
        assert status is not None
        assert status["status"] == "not_running"

        # 9. 获取统计信息
        stats = mcp_manager.get_service_statistics()
        assert isinstance(stats, dict)
        assert "total_services" in stats
        assert "running_services" in stats

    @pytest.mark.asyncio
    async def test_multiple_service_management(self, mcp_manager):
        """测试多服务管理"""
        results = {}

        # 并发启动多个服务
        with patch('asyncio.create_subprocess_shell') as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with patch.object(mcp_manager, '_check_service_health', return_value=True):
                # 启动多个服务
                for service_name in ["memory", "filesystem", "sequential-thinking"]:
                    results[service_name] = await mcp_manager.start_service(service_name)

        # 验证所有服务都启动成功
        assert all(results.values())

        # 验证所有服务都在运行
        for service_name in ["memory", "filesystem", "sequential-thinking"]:
            status = mcp_manager.get_service_status(service_name)
            assert status["status"] == "running"

        # 并发停止所有服务
        stop_results = {}
        for service_name in ["memory", "filesystem", "sequential-thinking"]:
            stop_results[service_name] = await mcp_manager.stop_service(service_name)

        # 验证所有服务都停止成功
        assert all(stop_results.values())

        # 验证所有服务都已停止
        for service_name in ["memory", "filesystem", "sequential-thinking"]:
            status = mcp_manager.get_service_status(service_name)
            assert status["status"] == "not_running"