"""
多级审核系统
实现自动化检查、Manager审核、Brain终审的三级质量保障
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ReviewLevel(Enum):
    """审核级别"""
    AUTOMATED = "automated"
    MANAGER = "manager"
    BRAIN = "brain"


class ReviewStatus(Enum):
    """审核状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class ReviewResult:
    """审核结果"""
    level: ReviewLevel
    status: ReviewStatus
    score: Optional[float] = None
    issues: List[Dict] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    reviewer: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    comment: Optional[str] = None


@dataclass
class QualityGate:
    """质量门禁"""
    name: str
    level: ReviewLevel
    checks: List[Dict]
    threshold: Dict[str, Any]
    required: bool = True


class MultiLevelReviewSystem:
    """多级审核系统"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.iccc_dir = project_root / ".iccc"
        self.state_dir = self.iccc_dir / ".state" / "quality-reviews"
        self.config_dir = self.iccc_dir / ".config"

        # 确保目录存在
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.quality_gates = self._load_quality_gates()

    def _load_quality_gates(self) -> List[QualityGate]:
        """加载质量门禁配置"""
        gates = []

        # 自动化检查门禁
        gates.append(QualityGate(
            name="automated_checks",
            level=ReviewLevel.AUTOMATED,
            checks=[
                {"name": "linting", "tool": "flake8"},
                {"name": "type_check", "tool": "mypy"},
                {"name": "security_scan", "tool": "bandit"},
                {"name": "test_coverage", "tool": "pytest-cov"},
                {"name": "performance_check", "tool": "locust"}
            ],
            threshold={
                "test_coverage": 90,
                "security_issues": 0,
                "type_errors": 0,
                "performance_score": 80
            }
        ))

        # Manager审核门禁
        gates.append(QualityGate(
            name="manager_review",
            level=ReviewLevel.MANAGER,
            checks=[
                {"name": "code_review", "type": "manual"},
                {"name": "architecture_review", "type": "manual", "specialist": "architecture"},
                {"name": "test_review", "type": "manual", "specialist": "quality"}
            ],
            threshold={
                "min_review_score": 8.0,
                "required_reviewers": 2
            }
        ))

        # Brain终审门禁
        gates.append(QualityGate(
            name="brain_final_approval",
            level=ReviewLevel.BRAIN,
            checks=[
                {"name": "overall_quality", "type": "ai_review"},
                {"name": "requirement_compliance", "type": "ai_check"},
                {"name": "innovation_assessment", "type": "ai_assess"}
            ],
            threshold={
                "min_approval_score": 9.0,
                "must_meet_requirements": True
            }
        ))

        return gates

    async def run_review(
        self,
        task_id: str,
        deliverables: List[Path],
        review_level: Optional[ReviewLevel] = None
    ) -> Dict[str, ReviewResult]:
        """
        运行多级审核

        Args:
            task_id: 任务ID
            deliverables: 交付物路径列表
            review_level: 指定审核级别（可选）

        Returns:
            各级审核结果
        """
        print(f"🔍 开始对任务 {task_id} 进行多级审核...")

        results = {}

        # 确定需要执行的审核级别
        if review_level:
            gates = [g for g in self.quality_gates if g.level == review_level]
        else:
            gates = self.quality_gates

        # 逐级执行审核
        for gate in gates:
            print(f"\n{'='*50}")
            print(f"执行 {gate.level.value.upper()} 级审核: {gate.name}")
            print(f"{'='*50}")

            result = await self._run_quality_gate(gate, task_id, deliverables)
            results[gate.level.value] = result

            # 如果某级审核失败且是必需的，停止后续审核
            if result.status == ReviewStatus.FAILED and gate.required:
                print(f"\n❌ {gate.level.value} 审核失败，停止后续审核")
                break

        # 保存审核结果
        await self._save_review_results(task_id, results)

        # 生成审核报告
        await self._generate_review_report(task_id, results)

        return results

    async def _run_quality_gate(
        self,
        gate: QualityGate,
        task_id: str,
        deliverables: List[Path]
    ) -> ReviewResult:
        """执行单个质量门禁检查"""

        if gate.level == ReviewLevel.AUTOMATED:
            return await self._run_automated_checks(gate, deliverables)
        elif gate.level == ReviewLevel.MANAGER:
            return await self._run_manager_review(gate, task_id, deliverables)
        elif gate.level == ReviewLevel.BRAIN:
            return await self._run_brain_review(gate, task_id, deliverables)

    async def _run_automated_checks(
        self,
        gate: QualityGate,
        deliverables: List[Path]
    ) -> ReviewResult:
        """运行自动化检查"""
        print("🤖 执行自动化检查...")

        issues = []
        scores = {}
        total_score = 0

        for check in gate.checks:
            check_name = check["name"]
            tool = check.get("tool", check_name)

            print(f"\n  运行 {check_name} ({tool})...")

            # 模拟运行检查工具
            result = await self._run_check_tool(tool, deliverables)

            # 评估结果
            threshold = gate.threshold.get(check_name, 0)
            if check_name == "test_coverage":
                if result < threshold:
                    issues.append({
                        "type": "coverage",
                        "severity": "high",
                        "message": f"测试覆盖率 {result}% 低于阈值 {threshold}%"
                    })
                scores[check_name] = result

            elif check_name == "security_scan":
                if result > threshold:
                    issues.append({
                        "type": "security",
                        "severity": "critical",
                        "message": f"发现 {result} 个安全问题"
                    })
                scores[check_name] = max(0, 100 - result * 10)

            elif check_name == "linting":
                if result > threshold:
                    issues.append({
                        "type": "style",
                        "severity": "medium",
                        "message": f"发现 {result} 个代码风格问题"
                    })
                scores[check_name] = max(0, 100 - result * 2)

            else:
                scores[check_name] = result

            print(f"    结果: {result}")

        # 计算总分
        if scores:
            total_score = sum(scores.values()) / len(scores)

        # 判断是否通过
        status = ReviewStatus.PASSED if not issues else ReviewStatus.FAILED

        return ReviewResult(
            level=ReviewLevel.AUTOMATED,
            status=status,
            score=total_score,
            issues=issues,
            suggestions=self._generate_suggestions(issues),
            reviewer="System",
            comment=f"自动化检查完成，总分: {total_score:.1f}"
        )

    async def _run_manager_review(
        self,
        gate: QualityGate,
        task_id: str,
        deliverables: List[Path]
    ) -> ReviewResult:
        """运行Manager审核"""
        print("👨‍💼 执行Manager审核...")

        # 模拟分配审核任务给不同的Manager
        manager_reviews = {}

        for check in gate.checks:
            if check.get("specialist") == "architecture":
                manager_reviews["architecture"] = await self._get_architecture_review(
                    deliverables
                )
            elif check.get("specialist") == "quality":
                manager_reviews["quality"] = await self._get_quality_review(
                    deliverables
                )
            else:
                manager_reviews["code"] = await self._get_code_review(deliverables)

        # 汇总审核结果
        all_issues = []
        all_suggestions = []
        total_score = 0
        reviewers = []

        for review_type, review in manager_reviews.items():
            all_issues.extend(review.get("issues", []))
            all_suggestions.extend(review.get("suggestions", []))
            total_score += review.get("score", 0)
            reviewers.append(review.get("reviewer", f"{review_type}_manager"))

        # 计算平均分
        if manager_reviews:
            total_score /= len(manager_reviews)

        # 判断是否通过
        min_score = gate.threshold.get("min_review_score", 7.0)
        status = ReviewStatus.PASSED if total_score >= min_score else ReviewStatus.FAILED

        return ReviewResult(
            level=ReviewLevel.MANAGER,
            status=status,
            score=total_score,
            issues=all_issues,
            suggestions=all_suggestions,
            reviewer=", ".join(reviewers),
            comment=f"Manager审核完成，平均分: {total_score:.1f}"
        )

    async def _run_brain_review(
        self,
        gate: QualityGate,
        task_id: str,
        deliverables: List[Path]
    ) -> ReviewResult:
        """运行Brain终审"""
        print("🧠 执行Brain终审...")

        # 加载任务相关文档
        ideas_path = self.iccc_dir / ".plans" / "current" / "IDEAS.md"
        institution_path = self.iccc_dir / ".plans" / "current" / "INSTITUTION.md"

        # Brain进行全方位评估
        assessments = {}

        # 1. 需求符合度评估
        assessments["requirement_compliance"] = await self._assess_requirement_compliance(
            deliverables, ideas_path
        )

        # 2. 质量评估
        assessments["quality"] = await self._assess_quality(deliverables)

        # 3. 创新性评估
        assessments["innovation"] = await self._assess_innovation(deliverables)

        # 4. 可维护性评估
        assessments["maintainability"] = await self._assess_maintainability(deliverables)

        # 计算综合评分
        weights = {
            "requirement_compliance": 0.4,
            "quality": 0.3,
            "innovation": 0.15,
            "maintainability": 0.15
        }

        total_score = sum(
            assessments[key] * weights[key]
            for key in assessments
        )

        # 生成审核建议
        suggestions = []
        if total_score < 8:
            suggestions.append("建议进一步优化代码结构和性能")
        if assessments.get("requirement_compliance", 0) < 9:
            suggestions.append("请再次确认是否满足所有需求")
        if assessments.get("innovation", 0) > 8:
            suggestions.append("创新性表现优秀，值得推广")

        # 判断是否通过
        min_score = gate.threshold.get("min_approval_score", 8.5)
        status = ReviewStatus.PASSED if total_score >= min_score else ReviewStatus.REJECTED

        return ReviewResult(
            level=ReviewLevel.BRAIN,
            status=status,
            score=total_score,
            issues=[],
            suggestions=suggestions,
            reviewer="Brain",
            comment=f"Brain终审完成，综合评分: {total_score:.2f}"
        )

    async def _run_check_tool(self, tool: str, deliverables: List[Path]) -> float:
        """模拟运行检查工具"""
        # 这里应该实际运行对应的工具
        # 暂时返回模拟数据

        if tool == "pytest-cov":
            # 模拟测试覆盖率
            return 92.5
        elif tool == "bandit":
            # 模拟安全问题数
            return 0
        elif tool == "mypy":
            # 模拟类型错误数
            return 0
        elif tool == "flake8":
            # 模拟代码风格问题数
            return 2
        elif tool == "locust":
            # 模拟性能分数
            return 85.0
        else:
            return 90.0

    async def _get_architecture_review(self, deliverables: List[Path]) -> Dict:
        """获取架构Manager的审核"""
        return {
            "score": 8.5,
            "reviewer": "architecture-manager-001",
            "issues": [
                {
                    "type": "architecture",
                    "severity": "medium",
                    "message": "建议将数据库访问层抽象为独立的服务"
                }
            ],
            "suggestions": [
                "考虑使用Repository模式",
                "增加缓存层以提高性能"
            ]
        }

    async def _get_quality_review(self, deliverables: List[Path]) -> Dict:
        """获取质量Manager的审核"""
        return {
            "score": 9.0,
            "reviewer": "quality-manager-001",
            "issues": [],
            "suggestions": [
                "增加更多的边界测试用例",
                "考虑添加性能基准测试"
            ]
        }

    async def _get_code_review(self, deliverables: List[Path]) -> Dict:
        """获取代码审核"""
        return {
            "score": 8.0,
            "reviewer": "development-manager-001",
            "issues": [
                {
                    "type": "code",
                    "severity": "low",
                    "message": "部分函数缺少文档字符串"
                }
            ],
            "suggestions": [
                "完善函数文档",
                "优化算法复杂度"
            ]
        }

    async def _assess_requirement_compliance(
        self,
        deliverables: List[Path],
        ideas_path: Path
    ) -> float:
        """评估需求符合度"""
        # 模拟评估
        return 9.2

    async def _assess_quality(self, deliverables: List[Path]) -> float:
        """评估代码质量"""
        # 模拟评估
        return 8.8

    async def _assess_innovation(self, deliverables: List[Path]) -> float:
        """评估创新性"""
        # 模拟评估
        return 7.5

    async def _assess_maintainability(self, deliverables: List[Path]) -> float:
        """评估可维护性"""
        # 模拟评估
        return 8.3

    def _generate_suggestions(self, issues: List[Dict]) -> List[str]:
        """根据问题生成改进建议"""
        suggestions = []

        for issue in issues:
            if issue["type"] == "coverage":
                suggestions.append("增加单元测试和集成测试以提高覆盖率")
            elif issue["type"] == "security":
                suggestions.append("修复所有安全问题，使用安全扫描工具定期检查")
            elif issue["type"] == "style":
                suggestions.append("使用代码格式化工具（如black）统一代码风格")
            elif issue["type"] == "architecture":
                suggestions.append("重构架构设计，遵循SOLID原则")

        return list(set(suggestions))

    async def _save_review_results(
        self,
        task_id: str,
        results: Dict[str, ReviewResult]
    ):
        """保存审核结果"""
        review_file = self.state_dir / f"review_{task_id}.json"

        review_data = {
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "results": {
                level: {
                    "status": result.status.value,
                    "score": result.score,
                    "issues": result.issues,
                    "suggestions": result.suggestions,
                    "reviewer": result.reviewer,
                    "comment": result.comment,
                    "timestamp": result.timestamp.isoformat()
                }
                for level, result in results.items()
            }
        }

        with open(review_file, 'w', encoding='utf-8') as f:
            json.dump(review_data, f, ensure_ascii=False, indent=2)

    async def _generate_review_report(
        self,
        task_id: str,
        results: Dict[str, ReviewResult]
    ):
        """生成审核报告"""
        report_dir = self.iccc_dir / ".plans" / "current"
        report_path = report_dir / f"REVIEW_REPORT_{task_id}.md"

        # 构建报告内容
        report_content = f"""# 审核报告 - {task_id}

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> 任务ID: {task_id}

## 审核概览

| 审核级别 | 状态 | 评分 | 审核人 | 备注 |
|---------|------|------|--------|------|
"""

        for level, result in results.items():
            status_icon = "✅" if result.status == ReviewStatus.PASSED else "❌"
            report_content += f"| {level} | {status_icon} {result.status.value} | {result.score or 'N/A'} | {result.reviewer or 'N/A'} | {result.comment or ''} |\n"

        # 详细问题
        report_content += "\n## 发现的问题\n\n"

        for level, result in results.items():
            if result.issues:
                report_content += f"### {level.upper()} 级问题\n\n"
                for issue in result.issues:
                    severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢", "critical": "🚨"}.get(issue.get("severity"), "⚪")
                    report_content += f"- {severity_icon} **{issue.get('type', 'Unknown')}**: {issue.get('message', '')}\n"
                report_content += "\n"

        # 改进建议
        report_content += "\n## 改进建议\n\n"

        all_suggestions = set()
        for result in results.values():
            all_suggestions.update(result.suggestions)

        for suggestion in sorted(all_suggestions):
            report_content += f"- {suggestion}\n"

        # 审核结论
        report_content += "\n## 审核结论\n\n"

        final_status = "通过" if all(r.status == ReviewStatus.PASSED for r in results.values()) else "未通过"

        report_content += f"**最终状态**: {final_status}\n\n"

        if final_status == "通过":
            report_content += "✅ 任务已通过所有质量门禁，可以继续下一步流程。\n"
        else:
            report_content += "❌ 任务未完全通过质量门禁，请根据上述问题进行修复后重新提交审核。\n"

        # 保存报告
        report_path.write_text(report_content, encoding='utf-8')
        print(f"\n📋 审核报告已保存: {report_path}")


async def main():
    """主函数 - 用于测试"""
    import argparse

    parser = argparse.ArgumentParser(description='多级审核系统')
    parser.add_argument(
        '--task-id',
        required=True,
        help='任务ID'
    )
    parser.add_argument(
        '--deliverables',
        nargs='+',
        required=True,
        help='交付物文件路径'
    )
    parser.add_argument(
        '--level',
        choices=['automated', 'manager', 'brain'],
        help='指定审核级别'
    )
    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path.cwd(),
        help='项目根目录'
    )

    args = parser.parse_args()

    # 创建审核系统
    review_system = MultiLevelReviewSystem(args.project_root)

    # 准备交付物路径
    deliverables = [Path(d) for d in args.deliverables]

    # 运行审核
    results = await review_system.run_review(
        task_id=args.task_id,
        deliverables=deliverables,
        review_level=ReviewLevel(args.level) if args.level else None
    )

    # 显示结果摘要
    print("\n" + "="*60)
    print("审核结果摘要")
    print("="*60)

    for level, result in results.items():
        print(f"\n{level.upper()}:")
        print(f"  状态: {result.status.value}")
        print(f"  评分: {result.score}")
        print(f"  问题数: {len(result.issues)}")


if __name__ == '__main__':
    asyncio.run(main())