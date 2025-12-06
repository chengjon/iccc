#!/usr/bin/env python3
"""PreToolUse hook for safety checking dangerous commands."""

import os
import re
import sys

# Dangerous command patterns to block
DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r"sudo\s+rm",
    r"chmod\s+-R\s+777",
    r"chown\s+-R",
    # System attacks
    r":\(\)\{:\|:&\};:",  # Fork bomb
    r"dd\s+if=/dev/zero",
    r"mkfs\.",
    # Network attacks
    r"curl.*\|.*sh",
    r"wget.*\|.*bash",
    # Data exfiltration
    r"curl.*\.env",
    r"curl.*\.aws",
    r"curl.*\.ssh",
    # Dangerous git operations
    r"git\s+push\s+--force\s+origin\s+main",
    r"git\s+push\s+--force\s+origin\s+master",
]

# Wildcard limits for destructive commands
WILDCARD_LIMITS = {
    "rm": 2,
    "mv": 3,
    "cp": 5,
}


def check_dangerous_patterns(command: str) -> tuple[bool, str]:
    """Check if command matches dangerous patterns."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Blocked dangerous pattern: {pattern}"
    return True, "OK"


def check_wildcard_abuse(command: str) -> tuple[bool, str]:
    """Check for excessive wildcards in destructive commands."""
    for cmd, max_wildcards in WILDCARD_LIMITS.items():
        if cmd in command:
            wildcard_count = command.count("*")
            if wildcard_count > max_wildcards:
                return False, f"Too many wildcards ({wildcard_count}) in {cmd} command"
    return True, "OK"


def check_production_protection(command: str) -> tuple[bool, str]:
    """Check if we're in production and blocking destructive ops."""
    cwd = os.getcwd().lower()
    if "production" in cwd or "prod" in cwd:
        dangerous_verbs = ["rm", "drop", "delete", "truncate"]
        if any(verb in command.lower() for verb in dangerous_verbs):
            return False, "Destructive operations blocked in production environment"
    return True, "OK"


def main() -> int:
    """Main safety check function."""
    # Get command from environment variable
    command = os.getenv("TOOL_COMMAND", "")

    if not command:
        print("No command to check", file=sys.stderr)
        return 0

    # Run all safety checks
    checks = [
        check_dangerous_patterns,
        check_wildcard_abuse,
        check_production_protection,
    ]

    for check_func in checks:
        is_safe, reason = check_func(command)
        if not is_safe:
            print(f"🛑 BLOCKED: {reason}", file=sys.stderr)
            print(f"Command: {command}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
