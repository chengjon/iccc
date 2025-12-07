#!/usr/bin/env python3
"""
Safety check hook for PreToolUse events.

This script validates commands before execution to prevent dangerous operations.
It should be registered as a critical PreToolUse hook in Claude Code.

Usage:
    Set environment variables:
    - TOOL_NAME: Name of the tool being executed
    - TOOL_COMMAND: Command to be executed (for Bash tool)
    - HOOK_DATA: JSON data about the tool execution

Exit codes:
    0: Command is safe, allow execution
    1: Command is dangerous, block execution
"""

import json
import os
import re
import sys

# ============================================================================
# DANGEROUS PATTERNS - Commands that should be blocked
# ============================================================================

DANGEROUS_PATTERNS = [
    # File system destruction
    r"rm\s+-rf\s+/",  # Delete root
    r"rm\s+-rf\s+~",  # Delete home
    r"rm\s+-rf\s+\*",  # Delete all in current dir
    r"rm\s+-rf\s+.*\*.*\*.*\*",  # Too many wildcards
    r"sudo\s+rm",  # Privileged deletion
    r"chmod\s+-R\s+777",  # Dangerous permissions
    r"chown\s+-R\s+",  # Recursive ownership change
    # Fork bomb
    r":\(\)\{:\|:&\};:",  # Classic fork bomb
    r"while\s*:\s*;\s*do.*fork",  # Fork in infinite loop
    # Disk destruction
    r"dd\s+if=/dev/zero",  # Write zeros
    r"dd\s+if=/dev/random",  # Write random data
    r"mkfs\.",  # Format filesystem
    # Network attacks
    r"curl.*\|.*sh",  # Download and execute
    r"wget.*\|.*bash",  # Download and execute
    r"curl.*\|.*python",  # Download and execute Python
    r"wget.*\|.*python",  # Download and execute Python
    # Data exfiltration
    r"curl.*env",  # Send environment variables
    r"curl.*\.aws",  # Send AWS credentials
    r"curl.*\.ssh",  # Send SSH keys
    r"curl.*id_rsa",  # Send SSH private key
    r"wget.*env",  # Download environment
    r"wget.*\.ssh",  # Download SSH keys
    # Git dangers
    r"git\s+push\s+--force\s+(origin\s+)?(main|master)",  # Force push to main
    r"git\s+push\s+-f\s+(origin\s+)?(main|master)",  # Force push short form
    r"git\s+reset\s+--hard\s+HEAD~\d+",  # Hard reset multiple commits
    # System compromise
    r">/etc/passwd",  # Modify system users
    r">/etc/shadow",  # Modify system passwords
    r">/etc/sudoers",  # Modify sudo permissions
    r"systemctl\s+stop",  # Stop system services
    r"systemctl\s+disable",  # Disable system services
    r"kill\s+-9\s+1",  # Kill init process
    # Crypto mining
    r"xmrig",  # Monero miner
    r"cpuminer",  # Generic CPU miner
    # Container escape
    r"docker\s+run.*--privileged",  # Privileged container
    r"docker\s+run.*-v\s+/:/",  # Mount host root
]

# ============================================================================
# PRODUCTION PATHS - Paths that should be protected
# ============================================================================

PRODUCTION_PATHS = [
    "/etc/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/boot/",
    "/sys/",
    "/proc/",
    "/var/lib/",
    "/var/run/",
    "/var/log/",
    "/root/",
]

# ============================================================================
# WILDCARD LIMITS - Maximum wildcards allowed per command type
# ============================================================================

WILDCARD_LIMITS = {
    "rm": 2,  # Max 2 wildcards in rm commands
    "chmod": 1,  # Max 1 wildcard in chmod
    "chown": 1,  # Max 1 wildcard in chown
}

# ============================================================================
# SAFETY CHECK FUNCTIONS
# ============================================================================


def load_hook_data() -> dict:
    """Load hook data from environment variable."""
    hook_data_str = os.getenv("HOOK_DATA", "{}")
    try:
        return json.loads(hook_data_str)
    except json.JSONDecodeError:
        return {}


def get_tool_info() -> tuple[str, str | None]:
    """
    Get tool name and command from environment.

    Returns:
        Tuple of (tool_name, command)
    """
    tool_name = os.getenv("TOOL_NAME", "")
    tool_command = os.getenv("TOOL_COMMAND", "")

    # Also try from HOOK_DATA
    hook_data = load_hook_data()
    if not tool_name and "tool_name" in hook_data:
        tool_name = hook_data["tool_name"]
    if not tool_command and "tool_command" in hook_data:
        tool_command = hook_data["tool_command"]

    return tool_name, tool_command if tool_command else None


def check_dangerous_patterns(command: str) -> str | None:
    """
    Check if command matches any dangerous patterns.

    Args:
        command: Command to check

    Returns:
        Error message if dangerous, None if safe
    """
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Blocked: Command matches dangerous pattern '{pattern}'"
    return None


def check_wildcard_limits(command: str) -> str | None:
    """
    Check if command exceeds wildcard limits.

    Args:
        command: Command to check

    Returns:
        Error message if too many wildcards, None if safe
    """
    for cmd_type, limit in WILDCARD_LIMITS.items():
        if command.startswith(cmd_type) or f" {cmd_type} " in command:
            wildcard_count = command.count("*")
            if wildcard_count > limit:
                return (
                    f"Blocked: '{cmd_type}' command has {wildcard_count} wildcards "
                    f"(max {limit} allowed)"
                )
    return None


def check_production_paths(command: str) -> str | None:
    """
    Check if command operates on production paths.

    Args:
        command: Command to check

    Returns:
        Error message if accessing production path, None if safe
    """
    # Detect if in production environment
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development"))
    if env.lower() not in ["production", "prod"]:
        # Not in production, allow
        return None

    # Check if any production path is referenced
    for path in PRODUCTION_PATHS:
        if path in command:
            # Check if it's a destructive operation
            destructive_ops = ["rm", "rmdir", "delete", ">", "chmod", "chown"]
            if any(op in command for op in destructive_ops):
                return (
                    f"Blocked: Destructive operation on production path '{path}' "
                    f"(ENV={env})"
                )

    return None


def check_bash_command(command: str) -> str | None:
    """
    Run all safety checks on a Bash command.

    Args:
        command: Command to check

    Returns:
        Error message if dangerous, None if safe
    """
    # Check dangerous patterns
    error = check_dangerous_patterns(command)
    if error:
        return error

    # Check wildcard limits
    error = check_wildcard_limits(command)
    if error:
        return error

    # Check production paths
    error = check_production_paths(command)
    if error:
        return error

    return None


def main() -> int:
    """
    Main safety check logic.

    Returns:
        Exit code (0 = safe, 1 = dangerous)
    """
    tool_name, tool_command = get_tool_info()

    # Only check Bash commands
    if tool_name != "Bash":
        # Other tools are considered safe
        return 0

    if not tool_command:
        # No command provided, allow
        return 0

    # Run safety checks
    error = check_bash_command(tool_command)

    if error:
        # Dangerous command detected
        print(f"[SAFETY CHECK FAILED] {error}", file=sys.stderr)
        print(f"Command: {tool_command}", file=sys.stderr)
        return 1

    # Command is safe
    return 0


if __name__ == "__main__":
    sys.exit(main())
