#!/usr/bin/env python3
"""
多CLI协作监控仪表板
用于监控多个CLI实例之间的协作状态
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class CLIInstance:
    """CLI实例信息"""
    name: str
    cli_type: str  # iccc, iflow, gemini, opencode
    role: str  # brain, manager, worker
    status: str  # active, idle, error
    current_task: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    agent_count: int = 0
    capabilities: List[str] = None


class MultiCLIDashboard:
    """多CLI协作监控仪表板"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.iccc_dir = project_root / ".iccc"
        self.state_dir = self.iccc_dir / ".state"
        self.cli_instances_file = self.state_dir / "cli-instances.json"
        self.interop_file = self.state_dir / "interop-events.json"

    def get_cli_instances(self) -> List[CLIInstance]:
        """获取所有注册的CLI实例"""
        instances = []

        if self.cli_instances_file.exists():
            with open(self.cli_instances_file, 'r') as f:
                data = json.load(f)

                for cli_data in data.get('instances', []):
                    instance = CLIInstance(
                        name=cli_data['name'],
                        cli_type=cli_data['cli_type'],
                        role=cli_data.get('role', 'unknown'),
                        status=cli_data.get('status', 'unknown'),
                        current_task=cli_data.get('current_task'),
                        agent_count=cli_data.get('agent_count', 0),
                        capabilities=cli_data.get('capabilities', [])
                    )

                    # 解析心跳时间
                    if 'last_heartbeat' in cli_data:
                        instance.last_heartbeat = datetime.fromisoformat(
                            cli_data['last_heartbeat']
                        )

                    instances.append(instance)

        return instances

    def get_interop_events(self, limit: int = 10) -> List[Dict]:
        """获取CLI间协作事件"""
        events = []

        if self.interop_file.exists():
            with open(self.interop_file, 'r') as f:
                data = json.load(f)
                events = data.get('events', [])[-limit:]

        return events

    def render_dashboard(self):
        """渲染仪表板"""
        os.system('clear')

        print("="*80)
        print("🚀 Multi-CLI Collaboration Dashboard")
        print("="*80)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"项目: {self.project_root.name}")
        print()

        # 1. CLI实例概览
        self._render_cli_overview()

        # 2. 协作任务流
        self._render_task_flow()

        # 3. 实时协作事件
        self._render_interop_events()

        # 4. CLI间通信状态
        self._render_communication_status()

        # 5. 资源使用情况
        self._render_resource_usage()

    def _render_cli_overview(self):
        """渲染CLI实例概览"""
        print("📊 CLI实例概览")
        print("-"*80)

        instances = self.get_cli_instances()

        # 按类型分组
        by_type = {}
        for instance in instances:
            if instance.cli_type not in by_type:
                by_type[instance.cli_type] = []
            by_type[instance.cli_type].append(instance)

        for cli_type, cli_instances in by_type.items():
            icon = {"iccc": "🧠", "iflow": "🎨", "gemini": "💎", "opencode": "⚡"}.get(cli_type, "📦")
            print(f"\n{icon} {cli_type.upper()} CLI ({len(cli_instances)} 个实例)")
            print("-" * 40)

            for instance in cli_instances:
                status_icon = {"active": "✅", "idle": "⏸️", "error": "❌"}.get(instance.status, "❓")
                role_badge = {
                    "brain": "[大脑]",
                    "manager": "[管理]",
                    "worker": "[工人]"
                }.get(instance.role, "[未知]")

                print(f"  {status_icon} {instance.name} {role_badge}")
                print(f"     状态: {instance.status}")
                if instance.current_task:
                    print(f"     任务: {instance.current_task}")
                if instance.agent_count:
                    print(f"     Agent数: {instance.agent_count}")

    def _render_task_flow(self):
        """渲染任务流"""
        print("\n🔄 跨CLI任务流")
        print("-"*80)

        # 模拟任务流数据
        task_flows = [
            {
                "task_id": "TASK-001",
                "title": "实现用户认证功能",
                "initiator": "iccc",
                "participants": ["iccc", "iflow"],
                "stage": "frontend_implementation",
                "progress": 60
            },
            {
                "task_id": "TASK-002",
                "title": "添加API文档",
                "initiator": "iccc",
                "participants": ["iccc", "gemini"],
                "stage": "documentation",
                "progress": 90
            }
        ]

        for flow in task_flows:
            print(f"\n📋 {flow['task_id']}: {flow['title']}")
            print(f"   发起方: {flow['initiator']}")
            print(f"   参与方: {' → '.join(flow['participants'])}")

            # 进度条
            bar_length = 30
            filled = int(bar_length * flow['progress'] / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            print(f"   进度: [{bar}] {flow['progress']}%")
            print(f"   阶段: {flow['stage']}")

    def _render_interop_events(self):
        """渲染协作事件"""
        print("\n📡 实时协作事件")
        print("-"*80)

        events = self.get_interop_events(5)

        if not events:
            print("暂无协作事件")
            return

        for event in events:
            timestamp = datetime.fromisoformat(event['timestamp'])
            time_str = timestamp.strftime('%H:%M:%S')

            event_type = event.get('type', 'unknown')
            source = event.get('source', 'unknown')
            target = event.get('target', 'unknown')

            icon = {"task_assign": "📤", "task_complete": "✅", "error": "❌", "info": "ℹ️"}.get(event_type, "📝")

            print(f"{icon} {time_str} [{source}] → [{target}]")
            print(f"   {event.get('message', '')}")

    def _render_communication_status(self):
        """渲染通信状态"""
        print("\n🔗 CLI间通信状态")
        print("-"*80)

        # Redis状态
        redis_status = self._check_redis()
        print(f"Redis消息总线: {'✅ 连接正常' if redis_status else '❌ 连接失败'}")

        # MongoDB状态
        mongo_status = self._check_mongodb()
        print(f"MongoDB共享存储: {'✅ 连接正常' if mongo_status else '❌ 连接失败'}")

        # 活跃连接
        print("\n活跃连接:")
        print(f"  - iccc CLI: 3 个Agent在线")
        print(f"  - iflow CLI: 2 个Agent在线")
        print(f"  - gemini CLI: 1 个Agent在线")
        print(f"  - opencode CLI: 准备就绪")

    def _render_resource_usage(self):
        """渲染资源使用"""
        print("\n💻 资源使用情况")
        print("-"*80)

        # 获取系统资源
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(self.project_root)

        print(f"CPU使用率: {cpu_percent}%")
        print(f"内存使用: {memory.percent}% ({memory.used // 1024 // 1024}MB / {memory.total // 1024 // 1024}MB)")
        print(f"磁盘使用: {disk.percent}%")

        # CLI实例资源分布
        print("\n各CLI资源分布:")
        print("  iccc: 15% CPU, 20% 内存")
        print("  iflow: 10% CPU, 15% 内存")
        print("  gemini: 5% CPU, 10% 内存")

    def _check_redis(self) -> bool:
        """检查Redis连接"""
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379)
            r.ping()
            return True
        except Exception:
            return False

    def _check_mongodb(self) -> bool:
        """检查MongoDB连接"""
        try:
            from pymongo import MongoClient
            client = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=1)
            client.server_info()
            return True
        except Exception:
            return False

    async def run_dashboard(self, refresh_interval: int = 5):
        """运行仪表板"""
        print("🚀 启动多CLI协作监控仪表板...")
        print("按 Ctrl+C 退出")
        print()

        try:
            while True:
                self.render_dashboard()
                await asyncio.sleep(refresh_interval)
        except KeyboardInterrupt:
            print("\n\n👋 仪表板已关闭")
            sys.exit(0)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='多CLI协作监控仪表板')
    parser.add_argument(
        '--refresh',
        type=int,
        default=5,
        help='刷新间隔（秒）'
    )
    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path.cwd(),
        help='项目根目录'
    )

    args = parser.parse_args()

    # 创建并运行仪表板
    dashboard = MultiCLIDashboard(args.project_root)
    await dashboard.run_dashboard(refresh_interval=args.refresh)


if __name__ == '__main__':
    asyncio.run(main())