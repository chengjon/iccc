#!/usr/bin/env python3
"""PostToolUse hook for code quality validation."""

import os
import subprocess
import sys


def run_linter(file_path: str) -> tuple[bool, str]:
    """Run linter on a modified file."""
    # Determine file type and appropriate linter
    if file_path.endswith(".py"):
        try:
            result = subprocess.run(
                ["ruff", "check", file_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False, f"Ruff linting failed:\n{result.stdout}"
            return True, "Python linting passed"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, "Linter not available or timed out"

    elif file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
        try:
            result = subprocess.run(
                ["eslint", file_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False, f"ESLint failed:\n{result.stdout}"
            return True, "JavaScript/TypeScript linting passed"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, "Linter not available or timed out"

    return True, f"No linter configured for {file_path}"


def main() -> int:
    """Main quality check function."""
    # Get hook data from environment
    tool_name = os.getenv("TOOL_NAME", "")

    # Only check file modifications
    if tool_name not in ("Write", "Edit"):
        return 0

    # Get modified files from HOOK_DATA
    import json

    hook_data_str = os.getenv("HOOK_DATA", "{}")
    try:
        hook_data = json.loads(hook_data_str)
    except json.JSONDecodeError:
        return 0

    file_path = hook_data.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return 0

    # Run quality checks
    success, message = run_linter(file_path)

    if not success:
        print(f"⚠️  Quality check failed: {message}", file=sys.stderr)
        # Don't block - just warn
        return 0

    print(f"✅ {message}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
