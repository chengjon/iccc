#!/usr/bin/env python3
"""
Automatic test trigger hook for PostToolUse events.

This script automatically runs appropriate tests based on file modifications.
Designed to run after Write/Edit tool usage to ensure code quality.

Triggers:
- TypeScript files (.ts, .tsx) -> npm run typecheck
- Test files (*test*.py, *spec*.js) -> Run the specific test
- Component files (*.tsx, *.jsx) -> Run component tests
- Python files (*.py) -> mypy type check

Usage:
    Set in Claude Code hooks configuration:
    {
      "PostToolUse": {
        "command": "python iccc/hooks/scripts/auto_test.py",
        "critical": false
      }
    }

Environment variables:
    - TOOL_NAME: Name of tool executed (Write, Edit, etc.)
    - FILE_PATH: Path to modified file
    - HOOK_DATA: JSON data about tool execution
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def get_file_path() -> Path | None:
    """Extract file path from hook data."""
    hook_data_str = os.environ.get("HOOK_DATA", "{}")
    try:
        hook_data = json.loads(hook_data_str)
        file_path = hook_data.get("file_path")
        if file_path:
            return Path(file_path)
    except json.JSONDecodeError:
        pass

    # Fallback to FILE_PATH env var
    file_path = os.environ.get("FILE_PATH")
    if file_path:
        return Path(file_path)

    return None


def is_typescript_file(path: Path) -> bool:
    """Check if file is TypeScript."""
    return path.suffix in [".ts", ".tsx"]


def is_javascript_file(path: Path) -> bool:
    """Check if file is JavaScript."""
    return path.suffix in [".js", ".jsx"]


def is_python_file(path: Path) -> bool:
    """Check if file is Python."""
    return path.suffix == ".py"


def is_test_file(path: Path) -> bool:
    """Check if file is a test file."""
    name_lower = path.name.lower()
    return (
        "test" in name_lower
        or "spec" in name_lower
        or path.parent.name == "tests"
    )


def is_component_file(path: Path) -> bool:
    """Check if file is a React/Vue component."""
    return path.suffix in [".tsx", ".jsx", ".vue"]


def run_command(cmd: list[str], description: str) -> bool:
    """
    Run a command and report results.

    Args:
        cmd: Command to execute
        description: Human-readable description

    Returns:
        True if command succeeded, False otherwise
    """
    print(f"\n🔍 Auto-test: {description}")
    print(f"   Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # 1 minute timeout
        )

        if result.returncode == 0:
            print(f"   ✅ {description} passed")
            if result.stdout:
                print(f"   Output: {result.stdout[:200]}")
            return True
        else:
            print(f"   ❌ {description} failed")
            if result.stderr:
                print(f"   Error: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        print(f"   ⏱️  {description} timed out (>60s)")
        return False
    except FileNotFoundError:
        print(f"   ⚠️  Command not found: {cmd[0]}")
        return False
    except Exception as e:
        print(f"   ⚠️  Error running {description}: {e}")
        return False


def trigger_tests_for_file(file_path: Path) -> int:
    """
    Trigger appropriate tests based on file type.

    Returns:
        0 if all tests pass, 1 if any fail
    """
    print(f"\n📝 File modified: {file_path}")

    results = []

    # TypeScript type checking
    if is_typescript_file(file_path):
        # Check if package.json has typecheck script
        if Path("package.json").exists():
            results.append(
                run_command(
                    ["npm", "run", "typecheck"],
                    "TypeScript type check"
                )
            )

    # Python type checking
    elif is_python_file(file_path):
        # Run mypy on specific file
        results.append(
            run_command(
                ["mypy", str(file_path)],
                f"Python type check for {file_path.name}"
            )
        )

    # Test files - run the specific test
    if is_test_file(file_path):
        if is_python_file(file_path):
            results.append(
                run_command(
                    ["pytest", str(file_path), "-v"],
                    f"Run Python tests in {file_path.name}"
                )
            )
        elif is_javascript_file(file_path) or is_typescript_file(file_path):
            # Try Jest
            results.append(
                run_command(
                    ["npm", "test", "--", str(file_path)],
                    f"Run JS/TS tests in {file_path.name}"
                )
            )

    # Component tests
    elif is_component_file(file_path):
        # Check for component test file
        test_patterns = [
            file_path.with_suffix(".test.tsx"),
            file_path.with_suffix(".test.jsx"),
            file_path.parent / f"{file_path.stem}.test.tsx",
            file_path.parent / "tests" / f"{file_path.stem}.test.tsx",
        ]

        for test_file in test_patterns:
            if test_file.exists():
                results.append(
                    run_command(
                        ["npm", "test", "--", str(test_file)],
                        f"Component tests for {file_path.name}"
                    )
                )
                break

    # Summary
    if results:
        passed = sum(results)
        total = len(results)
        print(f"\n{'='*60}")
        print(f"Auto-test summary: {passed}/{total} checks passed")
        print(f"{'='*60}")

        return 0 if all(results) else 1
    else:
        print("\n⚠️  No automatic tests configured for this file type")
        return 0


def main() -> int:
    """Main entry point."""
    tool_name = os.environ.get("TOOL_NAME", "")

    # Only trigger on file write/edit operations
    if tool_name not in ["Write", "Edit", "MultiEdit"]:
        return 0

    file_path = get_file_path()
    if not file_path:
        print("⚠️  No file path found in hook data")
        return 0

    if not file_path.exists():
        print(f"⚠️  File does not exist: {file_path}")
        return 0

    return trigger_tests_for_file(file_path)


if __name__ == "__main__":
    sys.exit(main())
