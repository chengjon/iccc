#!/usr/bin/env python3
"""
规格驱动开发流程示例
演示如何使用Brain工作流引擎进行需求分析和任务分解
"""

import asyncio
from pathlib import Path
import sys

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from brain.workflow_engine import BrainWorkflowEngine


async def demo_spec_driven_development():
    """演示规格驱动开发流程"""

    print("=" * 60)
    print("iCCC 规格驱动开发流程演示")
    print("=" * 60)

    # 1. 创建工作流引擎
    engine = BrainWorkflowEngine(project_root)

    # 2. 准备输入文档
    input_docs = ['README.md', 'CLAUDE.md']
    user_request = """
    额外需求：
    1. 实现实时协作功能，允许多用户同时编辑
    2. 添加AI代码建议功能
    3. 支持插件系统
    """

    print("\n📋 输入文档:")
    for doc in input_docs:
        path = project_root / doc
        if path.exists():
            print(f"  ✓ {doc}")
        else:
            print(f"  ✗ {doc} (不存在)")

    print("\n💬 用户需求:")
    print(user_request)

    # 3. 运行规格驱动开发流程
    print("\n🚀 开始运行规格驱动开发流程...")
    print("-" * 60)

    results = await engine.run_workflow(
        input_docs=input_docs,
        user_request=user_request,
        workflow_type="feature_development"
    )

    # 4. 展示结果
    print("\n" + "=" * 60)
    print("✅ 规格驱动开发流程完成!")
    print("=" * 60)

    print("\n📄 生成的文档:")
    for doc_type, path in results.items():
        print(f"\n  {doc_type}:")
        print(f"    路径: {path}")

        # 显示文档摘要
        if path.endswith('.md'):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                print(f"    大小: {len(content)} 字符")
                print(f"    行数: {len(lines)} 行")
                # 显示文档标题
                for line in lines[:5]:
                    if line.startswith('# '):
                        print(f"    标题: {line[2:]}")
                        break

    # 5. 展示使用建议
    print("\n" + "=" * 60)
    print("📌 下一步操作建议")
    print("=" * 60)

    print("\n1️⃣ 审核需求文档:")
    print("   - 查看 .iccc/.plans/current/IDEAS.md")
    print("   - 确认所有需求都被正确理解")
    print("   - 验证优先级排序是否合理")

    print("\n2️⃣ 确认技术规范:")
    print("   - 查看 .iccc/.plans/current/INSTITUTION.md")
    print("   - 检查架构决策是否合理")
    print("   - 确认技术选型符合项目需求")

    print("\n3️⃣ 任务分配:")
    print("   - 查看 .iccc/.plans/current/MAINTASK.md")
    print("   - 使用 iCCC CLI 分配任务:")
    print("     $ iccc task assign TASK-001 --agent worker-frontend")
    print("     $ iccc task assign TASK-002 --agent worker-backend")

    print("\n4️⃣ 开始开发:")
    print("   - Worker执行分配的任务")
    print("   - 通过Redis/MongoDB同步进度")
    print("   - 遵循多级审核流程")

    print("\n5️⃣ 质量保障:")
    print("   - 自动化检查会自动触发")
    print("   - Manager进行代码审核")
    print("   - Brain进行最终审核")

    print("\n" + "=" * 60)


async def demo_different_workflows():
    """演示不同的工作流"""

    print("\n\n🔄 不同工作流演示")
    print("=" * 60)

    engine = BrainWorkflowEngine(project_root)

    workflows = [
        ('feature_development', '功能开发', ['README.md']),
        ('bug_fix', 'Bug修复', ['BUG_REPORT.md']),
        ('refactoring', '代码重构', ['REFACTORING_PLAN.md'])
    ]

    for workflow_type, description, docs in workflows:
        print(f"\n📌 {description}工作流:")
        print(f"   输入文档: {', '.join(docs)}")
        print(f"   命令: brain --workflow {workflow_type} --docs {' '.join(docs)}")


if __name__ == '__main__':
    print("开始演示规格驱动开发流程...")

    # 运行主演示
    asyncio.run(demo_spec_driven_development())

    # 运行工作流演示
    asyncio.run(demo_different_workflows())

    print("\n\n✨ 演示完成!")
    print("更多使用方法请参考:")
    print("  - .iccc/README.md 系统文档")
    print("  - brain --help CLI帮助")
    print("  - .config/workflows/ 工作流配置")