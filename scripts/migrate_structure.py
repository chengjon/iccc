#!/usr/bin/env python3
"""
目录结构迁移脚本
将所有.iccc相关目录迁移到.iccc下统一管理
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime

class StructureMigrator:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.iccc_dir = project_root / '.iccc'
        self.migration_log = []

    def migrate(self):
        """执行完整的目录结构迁移"""

        print("🚀 开始迁移iCCC目录结构...")

        # 1. 创建.iccc目录
        self._create_iccc_directory()

        # 2. 迁移现有目录
        self._migrate_existing_directories()

        # 3. 创建新目录结构
        self._create_directory_structure()

        # 4. 创建软链接
        self._create_symlinks()

        # 5. 生成迁移报告
        self._generate_migration_report()

        print("✅ 迁移完成！")

    def _create_iccc_directory(self):
        """创建.iccc主目录"""
        if self.iccc_dir.exists():
            print("  .iccc 目录已存在")
        else:
            self.iccc_dir.mkdir(exist_ok=True)
            print("  ✅ 创建 .iccc 目录")

    def _migrate_existing_directories(self):
        """迁移现有目录到.iccc下"""

        migrations = [
            ('agents', '.iccc/agents'),
            ('plans', '.iccc/.plans'),
            ('workspaces', '.iccc/.workspaces'),
            ('state', '.iccc/.state'),
            ('logs', '.iccc/.logs'),
            ('shared', '.iccc/.shared'),
            ('hooks', '.iccc/.hooks')
        ]

        for src, dst in migrations:
            src_path = self.project_root / src
            dst_path = self.project_root / dst

            if src_path.exists() and not dst_path.exists():
                shutil.move(str(src_path), str(dst_path))
                self.migration_log.append(f"移动 {src} → {dst}")
                print(f"  ✅ 迁移 {src} 到 .iccc/")

    def _create_directory_structure(self):
        """创建完整的目录结构"""

        directories = [
            '.iccc/.plans/current',
            '.iccc/.plans/archive',
            '.iccc/.workspaces/agents/brain',
            '.iccc/.workspaces/agents/managers',
            '.iccc/.workspaces/agents/workers',
            '.iccc/.workspaces/cli-instances',
            '.iccc/.workspaces/git',
            '.iccc/.state/agent-states',
            '.iccc/.state/task-states',
            '.iccc/.state/quality-reviews',
            '.iccc/.state/checkpoints',
            '.iccc/.logs/managers',
            '.iccc/.logs/workers',
            '.iccc/.shared/knowledge-base/standards',
            '.iccc/.shared/knowledge-base/patterns',
            '.iccc/.shared/knowledge-base/best-practices',
            '.iccc/.shared/templates/spec',
            '.iccc/.shared/templates/code',
            '.iccc/.shared/templates/docs',
            '.iccc/.shared/tools',
            '.iccc/.config',
            '.iccc/.config/workflows',
            '.iccc/hooks/pre',
            '.iccc/hooks/post',
            '.iccc/hooks/subagent'
        ]

        for directory in directories:
            (self.project_root / directory).mkdir(parents=True, exist_ok=True)

    def _create_symlinks(self):
        """创建根目录的软链接，保持向后兼容"""

        links = [
            ('.iccc/.plans', 'plans'),
            ('.iccc/.workspaces', 'workspaces'),
            ('.iccc/.state', 'state'),
            ('.iccc/.logs', 'logs'),
            ('.iccc/.shared', 'shared'),
            ('.iccc/.hooks', 'hooks'),
            ('.iccc/.config', 'config')
        ]

        for src, dst in links:
            src_path = self.project_root / src
            dst_path = self.project_root / dst

            # 如果目标已存在且不是软链接，先备份
            if dst_path.exists() and not dst_path.is_symlink():
                backup_path = dst_path.with_suffix('.backup')
                shutil.move(str(dst_path), str(backup_path))
                self.migration_log.append(f"备份 {dst} → {backup_path}")

            # 创建软链接
            if not dst_path.is_symlink():
                dst_path.symlink_to(src_path)
                self.migration_log.append(f"创建软链接 {dst} → {src}")
                print(f"  ✅ 创建软链接: {dst}")

    def _generate_migration_report(self):
        """生成迁移报告"""
        report_path = self.project_root / '.iccc/migration_report.json'

        report = {
            "migration": {
                "timestamp": datetime.now().isoformat(),
                "version": "2.0.0",
                "project_root": str(self.project_root),
                "actions": self.migration_log
            },
            "structure": {
                "root": ".iccc",
                "subdirectories": [
                    "agents",
                    ".plans/current",
                    ".workspaces",
                    ".state",
                    ".logs",
                    ".shared",
                    ".config",
                    "hooks"
                ]
            }
        }

        report_path.write_text(json.dumps(report, indent=2))
        print(f"  📝 生成迁移报告: {report_path}")

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='迁移iCCC目录结构')
    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path.cwd(),
        help='项目根目录路径'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只显示将要执行的操作，不实际执行'
    )

    args = parser.parse_args()

    migrator = StructureMigrator(args.project_root)

    if args.dry_run:
        print("🔍 Dry Run - 以下操作将被执行：")
        # 这里可以添加预览逻辑
    else:
        migrator.migrate()

if __name__ == '__main__':
    main()