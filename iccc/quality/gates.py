"""Quality gate system for code validation."""

import asyncio
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class GateStatus(str, Enum):
    """Status of a quality gate."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class GateResult:
    """Result of a quality gate check."""

    gate_name: str
    status: GateStatus
    message: str
    details: Optional[str] = None


class QualityGate:
    """Base class for quality gates."""

    def __init__(self, name: str, required: bool = True) -> None:
        self.name = name
        self.required = required

    async def check(self, project_dir: Path) -> GateResult:
        """
        Check the quality gate.

        Args:
            project_dir: Project directory to check

        Returns:
            GateResult with check status
        """
        raise NotImplementedError


class LintGate(QualityGate):
    """Linting quality gate."""

    def __init__(self, required: bool = True) -> None:
        super().__init__("Lint", required)

    async def check(self, project_dir: Path) -> GateResult:
        """Run linter on the project."""
        try:
            # Try ruff for Python
            result = await asyncio.create_subprocess_exec(
                "ruff",
                "check",
                str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASSED,
                    message="Linting passed",
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAILED,
                    message="Linting failed",
                    details=stdout.decode("utf-8") if stdout else stderr.decode("utf-8"),
                )

        except FileNotFoundError:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIPPED,
                message="Linter not available",
            )


class TypeCheckGate(QualityGate):
    """Type checking quality gate."""

    def __init__(self, required: bool = False) -> None:
        super().__init__("TypeCheck", required)

    async def check(self, project_dir: Path) -> GateResult:
        """Run type checker on the project."""
        try:
            # Try mypy for Python
            result = await asyncio.create_subprocess_exec(
                "mypy",
                str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASSED,
                    message="Type checking passed",
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAILED,
                    message="Type checking failed",
                    details=stdout.decode("utf-8") if stdout else stderr.decode("utf-8"),
                )

        except FileNotFoundError:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIPPED,
                message="Type checker not available",
            )


class TestGate(QualityGate):
    """Testing quality gate."""

    def __init__(self, required: bool = True) -> None:
        super().__init__("Test", required)

    async def check(self, project_dir: Path) -> GateResult:
        """Run tests on the project."""
        try:
            # Try pytest for Python
            result = await asyncio.create_subprocess_exec(
                "pytest",
                "--tb=short",
                "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )

            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASSED,
                    message="All tests passed",
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAILED,
                    message="Some tests failed",
                    details=stdout.decode("utf-8") if stdout else stderr.decode("utf-8"),
                )

        except FileNotFoundError:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIPPED,
                message="Test runner not available",
            )


class SecurityGate(QualityGate):
    """Security scanning quality gate."""

    def __init__(self, required: bool = False) -> None:
        super().__init__("Security", required)

    async def check(self, project_dir: Path) -> GateResult:
        """Run security checks on the project."""
        try:
            # Try bandit for Python security checks
            result = await asyncio.create_subprocess_exec(
                "bandit",
                "-r",
                str(project_dir),
                "-f",
                "txt",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )

            stdout, stderr = await result.communicate()

            # Bandit returns 0 if no issues, 1 if issues found
            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASSED,
                    message="No security issues found",
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAILED,
                    message="Security issues detected",
                    details=stdout.decode("utf-8") if stdout else stderr.decode("utf-8"),
                )

        except FileNotFoundError:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIPPED,
                message="Security scanner not available",
            )


class QualityGateRunner:
    """Runner for multiple quality gates."""

    def __init__(self, gates: Optional[list[QualityGate]] = None) -> None:
        self.gates = gates or self.default_gates()

    @staticmethod
    def default_gates() -> list[QualityGate]:
        """Get default quality gates."""
        return [
            LintGate(required=True),
            TypeCheckGate(required=False),
            TestGate(required=True),
            SecurityGate(required=False),
        ]

    async def run_all(self, project_dir: Path) -> list[GateResult]:
        """
        Run all quality gates.

        Args:
            project_dir: Project directory to check

        Returns:
            List of gate results
        """
        results = []

        for gate in self.gates:
            result = await gate.check(project_dir)
            results.append(result)

        return results

    def check_passing(self, results: list[GateResult]) -> bool:
        """
        Check if all required gates passed.

        Args:
            results: List of gate results

        Returns:
            True if all required gates passed
        """
        for result in results:
            gate = next((g for g in self.gates if g.name == result.gate_name), None)

            if gate and gate.required and result.status == GateStatus.FAILED:
                return False

        return True

    def format_report(self, results: list[GateResult]) -> str:
        """
        Format quality gate results into a readable report.

        Args:
            results: List of gate results

        Returns:
            Formatted report string
        """
        lines = ["Quality Gate Report", "=" * 50, ""]

        for result in results:
            gate = next((g for g in self.gates if g.name == result.gate_name), None)
            required_marker = "(required)" if gate and gate.required else "(optional)"

            status_icon = {
                GateStatus.PASSED: "✅",
                GateStatus.FAILED: "❌",
                GateStatus.SKIPPED: "⏭️",
            }[result.status]

            lines.append(f"{status_icon} {result.gate_name} {required_marker}: {result.message}")

            if result.details:
                lines.append(f"   Details: {result.details[:200]}...")

            lines.append("")

        # Overall status
        passed = self.check_passing(results)
        lines.append("=" * 50)
        lines.append(f"Overall: {'✅ PASSED' if passed else '❌ FAILED'}")

        return "\n".join(lines)
