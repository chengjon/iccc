"""Tests for quality gate system."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iccc.quality.gates import (
    GateStatus,
    GateResult,
    QualityGate,
    LintGate,
    TypeCheckGate,
    TestGate,
    SecurityGate,
    QualityGateRunner,
)


class TestGateStatus:
    """Test GateStatus enum."""

    def test_status_values(self):
        """Test status enum values."""
        assert GateStatus.PASSED == "passed"
        assert GateStatus.FAILED == "failed"
        assert GateStatus.SKIPPED == "skipped"


class TestGateResult:
    """Test GateResult dataclass."""

    def test_gate_result_creation(self):
        """Test creating a gate result."""
        result = GateResult(
            gate_name="Test",
            status=GateStatus.PASSED,
            message="All tests passed",
        )
        assert result.gate_name == "Test"
        assert result.status == GateStatus.PASSED
        assert result.message == "All tests passed"
        assert result.details is None

    def test_gate_result_with_details(self):
        """Test creating a gate result with details."""
        result = GateResult(
            gate_name="Lint",
            status=GateStatus.FAILED,
            message="Linting failed",
            details="Error at line 10",
        )
        assert result.details == "Error at line 10"


class TestQualityGate:
    """Test base QualityGate class."""

    def test_quality_gate_initialization(self):
        """Test initializing a quality gate."""

        class TestableGate(QualityGate):
            async def check(self, project_dir: Path) -> GateResult:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASSED,
                    message="OK",
                )

        gate = TestableGate("CustomGate", required=False)
        assert gate.name == "CustomGate"
        assert gate.required is False

    @pytest.mark.asyncio
    async def test_quality_gate_check_not_implemented(self):
        """Test that base check raises NotImplementedError."""
        gate = QualityGate("Base", required=True)
        with pytest.raises(NotImplementedError):
            await gate.check(Path("/tmp"))


@pytest.mark.asyncio
class TestLintGate:
    """Test LintGate."""

    async def test_lint_gate_initialization(self):
        """Test initializing lint gate."""
        gate = LintGate(required=True)
        assert gate.name == "Lint"
        assert gate.required is True

    async def test_lint_gate_passed(self):
        """Test lint gate when linting passes."""
        gate = LintGate()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.PASSED
        assert result.message == "Linting passed"

    async def test_lint_gate_failed(self):
        """Test lint gate when linting fails."""
        gate = LintGate()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"Error: unused variable", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.FAILED
        assert result.message == "Linting failed"
        assert "unused variable" in result.details

    async def test_lint_gate_not_available(self):
        """Test lint gate when linter is not installed."""
        gate = LintGate()

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError
        ):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.SKIPPED
        assert result.message == "Linter not available"


@pytest.mark.asyncio
class TestTypeCheckGate:
    """Test TypeCheckGate."""

    async def test_type_check_gate_initialization(self):
        """Test initializing type check gate."""
        gate = TypeCheckGate(required=False)
        assert gate.name == "TypeCheck"
        assert gate.required is False

    async def test_type_check_passed(self):
        """Test type check when it passes."""
        gate = TypeCheckGate()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"Success", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.PASSED
        assert result.message == "Type checking passed"

    async def test_type_check_failed(self):
        """Test type check when it fails."""
        gate = TypeCheckGate()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"error: Incompatible types", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.FAILED
        assert "Incompatible types" in result.details

    async def test_type_check_not_available(self):
        """Test type check when mypy is not installed."""
        gate = TypeCheckGate()

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError
        ):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.SKIPPED


@pytest.mark.asyncio
class TestTestGate:
    """Test TestGate."""

    async def test_test_gate_initialization(self):
        """Test initializing test gate."""
        gate = TestGate(required=True)
        assert gate.name == "Test"
        assert gate.required is True

    async def test_tests_passed(self):
        """Test gate when all tests pass."""
        gate = TestGate()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"10 passed", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.PASSED
        assert result.message == "All tests passed"

    async def test_tests_failed(self):
        """Test gate when some tests fail."""
        gate = TestGate()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"3 failed, 7 passed", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.FAILED
        assert result.message == "Some tests failed"
        assert "3 failed" in result.details

    async def test_test_runner_not_available(self):
        """Test gate when pytest is not installed."""
        gate = TestGate()

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError
        ):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.SKIPPED


@pytest.mark.asyncio
class TestSecurityGate:
    """Test SecurityGate."""

    async def test_security_gate_initialization(self):
        """Test initializing security gate."""
        gate = SecurityGate(required=False)
        assert gate.name == "Security"
        assert gate.required is False

    async def test_security_passed(self):
        """Test security gate when no issues found."""
        gate = SecurityGate()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"No issues", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.PASSED
        assert result.message == "No security issues found"

    async def test_security_failed(self):
        """Test security gate when issues found."""
        gate = SecurityGate()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"Issue: SQL injection risk", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.FAILED
        assert result.message == "Security issues detected"
        assert "SQL injection" in result.details

    async def test_security_scanner_not_available(self):
        """Test security gate when bandit is not installed."""
        gate = SecurityGate()

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError
        ):
            result = await gate.check(Path("/tmp/project"))

        assert result.status == GateStatus.SKIPPED


@pytest.mark.asyncio
class TestQualityGateRunner:
    """Test QualityGateRunner."""

    async def test_runner_initialization(self):
        """Test initializing runner with default gates."""
        runner = QualityGateRunner()
        assert len(runner.gates) == 4
        gate_names = [g.name for g in runner.gates]
        assert "Lint" in gate_names
        assert "TypeCheck" in gate_names
        assert "Test" in gate_names
        assert "Security" in gate_names

    async def test_runner_custom_gates(self):
        """Test initializing runner with custom gates."""
        custom_gates = [LintGate(), TestGate()]
        runner = QualityGateRunner(gates=custom_gates)
        assert len(runner.gates) == 2

    async def test_default_gates(self):
        """Test default_gates static method."""
        gates = QualityGateRunner.default_gates()
        assert len(gates) == 4

        # Check required flags
        lint_gate = next(g for g in gates if g.name == "Lint")
        assert lint_gate.required is True

        type_check_gate = next(g for g in gates if g.name == "TypeCheck")
        assert type_check_gate.required is False

    async def test_run_all_gates(self):
        """Test running all gates."""
        runner = QualityGateRunner(gates=[LintGate(), TestGate()])

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"OK", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            results = await runner.run_all(Path("/tmp/project"))

        assert len(results) == 2
        assert all(r.status == GateStatus.PASSED for r in results)

    async def test_check_passing_all_passed(self):
        """Test check_passing when all required gates pass."""
        runner = QualityGateRunner(
            gates=[LintGate(required=True), TestGate(required=True)]
        )

        results = [
            GateResult("Lint", GateStatus.PASSED, "OK"),
            GateResult("Test", GateStatus.PASSED, "OK"),
        ]

        assert runner.check_passing(results) is True

    async def test_check_passing_required_failed(self):
        """Test check_passing when a required gate fails."""
        runner = QualityGateRunner(
            gates=[LintGate(required=True), TestGate(required=True)]
        )

        results = [
            GateResult("Lint", GateStatus.PASSED, "OK"),
            GateResult("Test", GateStatus.FAILED, "Failed"),
        ]

        assert runner.check_passing(results) is False

    async def test_check_passing_optional_failed(self):
        """Test check_passing when only optional gate fails."""
        runner = QualityGateRunner(
            gates=[LintGate(required=True), SecurityGate(required=False)]
        )

        results = [
            GateResult("Lint", GateStatus.PASSED, "OK"),
            GateResult("Security", GateStatus.FAILED, "Issues found"),
        ]

        assert runner.check_passing(results) is True

    async def test_check_passing_skipped(self):
        """Test check_passing when gate is skipped."""
        runner = QualityGateRunner(
            gates=[LintGate(required=True), TestGate(required=True)]
        )

        results = [
            GateResult("Lint", GateStatus.PASSED, "OK"),
            GateResult("Test", GateStatus.SKIPPED, "Not available"),
        ]

        # Skipped gates don't cause failure
        assert runner.check_passing(results) is True

    async def test_format_report(self):
        """Test formatting a quality gate report."""
        runner = QualityGateRunner(
            gates=[
                LintGate(required=True),
                TypeCheckGate(required=False),
                TestGate(required=True),
            ]
        )

        results = [
            GateResult("Lint", GateStatus.PASSED, "Linting passed"),
            GateResult("TypeCheck", GateStatus.SKIPPED, "Not available"),
            GateResult("Test", GateStatus.FAILED, "Failed", details="2 tests failed"),
        ]

        report = runner.format_report(results)

        assert "Quality Gate Report" in report
        assert "Lint" in report
        assert "(required)" in report
        assert "(optional)" in report
        assert "FAILED" in report
        assert "2 tests failed" in report

    async def test_format_report_all_passed(self):
        """Test format_report when all gates pass."""
        runner = QualityGateRunner(gates=[LintGate(required=True)])

        results = [GateResult("Lint", GateStatus.PASSED, "OK")]

        report = runner.format_report(results)
        assert "PASSED" in report
