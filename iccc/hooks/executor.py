"""Parallel hook executor with retry and timeout support."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from iccc.models.entities import HookEvent


class HookPriority(str, Enum):
    """Hook execution priority."""

    CRITICAL = "critical"  # Executes serially, blocks on failure
    NORMAL = "normal"  # Executes in parallel


@dataclass
class HookExecutionResult:
    """Result of executing a single hook."""

    hook_name: str
    success: bool
    execution_time_ms: float
    output: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    timed_out: bool = False


@dataclass
class HookConfig:
    """Enhanced hook configuration."""

    name: str
    command: str
    priority: HookPriority = HookPriority.NORMAL
    timeout_ms: int = 100
    max_retries: int = 0
    retry_delay_ms: int = 100
    env: Optional[dict[str, str]] = None


class HookExecutor:
    """
    Executes hooks with support for:
    - Parallel execution (non-critical hooks)
    - Serial execution (critical hooks)
    - Retry mechanism
    - Timeout control
    - Performance monitoring
    """

    def __init__(self, max_workers: int = 3) -> None:
        """
        Initialize executor.

        Args:
            max_workers: Maximum number of parallel hook executions
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def execute_hooks(
        self,
        hooks: list[HookConfig],
        data: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Execute a list of hooks with proper ordering and parallelization.

        Critical hooks execute serially in order.
        Normal hooks execute in parallel.

        Args:
            hooks: List of hook configurations
            data: Data to pass to hooks
            session_id: Optional session ID for tracking

        Returns:
            Dictionary with results: {
                'success': bool,
                'results': list[HookExecutionResult],
                'total_time_ms': float,
                'critical_failed': bool
            }
        """
        start_time = time.time()

        # Separate critical and normal hooks
        critical_hooks = [h for h in hooks if h.priority == HookPriority.CRITICAL]
        normal_hooks = [h for h in hooks if h.priority == HookPriority.NORMAL]

        results: list[HookExecutionResult] = []
        critical_failed = False

        # Execute critical hooks serially
        for hook in critical_hooks:
            result = await self._execute_single_hook(hook, data)
            results.append(result)

            if not result.success:
                critical_failed = True
                # Stop execution if critical hook fails
                break

        # Only execute normal hooks if no critical failure
        if not critical_failed:
            # Execute normal hooks in parallel
            if normal_hooks:
                normal_results = await self._execute_parallel(normal_hooks, data)
                results.extend(normal_results)

        total_time_ms = (time.time() - start_time) * 1000

        return {
            "success": not critical_failed and all(r.success for r in results),
            "results": results,
            "total_time_ms": total_time_ms,
            "critical_failed": critical_failed,
        }

    async def _execute_parallel(
        self, hooks: list[HookConfig], data: dict[str, Any]
    ) -> list[HookExecutionResult]:
        """
        Execute hooks in parallel using ThreadPoolExecutor.

        Args:
            hooks: List of hooks to execute
            data: Data to pass to hooks

        Returns:
            List of execution results
        """
        # Create tasks for all hooks
        tasks = [self._execute_single_hook(hook, data) for hook in hooks]

        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=False)

        return results

    async def _execute_single_hook(
        self, hook: HookConfig, data: dict[str, Any]
    ) -> HookExecutionResult:
        """
        Execute a single hook with retry logic.

        Args:
            hook: Hook configuration
            data: Data to pass to hook

        Returns:
            Execution result
        """
        retry_count = 0
        last_error = None

        while retry_count <= hook.max_retries:
            try:
                result = await self._execute_with_timeout(hook, data)

                # Success - return result
                if result.success:
                    result.retry_count = retry_count
                    return result

                # Failed but can retry
                last_error = result.error
                retry_count += 1

                if retry_count <= hook.max_retries:
                    # Wait before retry
                    await asyncio.sleep(hook.retry_delay_ms / 1000)

            except Exception as e:
                last_error = str(e)
                retry_count += 1

                if retry_count <= hook.max_retries:
                    await asyncio.sleep(hook.retry_delay_ms / 1000)

        # All retries exhausted
        return HookExecutionResult(
            hook_name=hook.name,
            success=False,
            execution_time_ms=0,
            error=f"Failed after {retry_count} retries: {last_error}",
            retry_count=retry_count,
        )

    async def _execute_with_timeout(
        self, hook: HookConfig, data: dict[str, Any]
    ) -> HookExecutionResult:
        """
        Execute hook with timeout.

        Args:
            hook: Hook configuration
            data: Data to pass to hook

        Returns:
            Execution result
        """
        start_time = time.time()
        timeout_seconds = hook.timeout_ms / 1000

        try:
            # Prepare environment
            env = {**(hook.env or {})}
            import json

            env["HOOK_DATA"] = json.dumps(data)

            # Add specific fields if available
            for key in ["tool_name", "tool_command", "file_path"]:
                if key in data:
                    env[key.upper()] = str(data[key])

            # Execute command with timeout
            process = await asyncio.create_subprocess_shell(
                hook.command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )

                execution_time_ms = (time.time() - start_time) * 1000

                return HookExecutionResult(
                    hook_name=hook.name,
                    success=process.returncode == 0,
                    execution_time_ms=execution_time_ms,
                    output=stdout.decode("utf-8") if stdout else None,
                    error=stderr.decode("utf-8") if stderr and process.returncode != 0 else None,
                )

            except asyncio.TimeoutError:
                # Kill the process
                process.kill()
                await process.wait()

                execution_time_ms = (time.time() - start_time) * 1000

                return HookExecutionResult(
                    hook_name=hook.name,
                    success=False,
                    execution_time_ms=execution_time_ms,
                    error=f"Hook timed out after {timeout_seconds}s",
                    timed_out=True,
                )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            return HookExecutionResult(
                hook_name=hook.name,
                success=False,
                execution_time_ms=execution_time_ms,
                error=f"Execution error: {str(e)}",
            )

    def shutdown(self) -> None:
        """Shutdown the executor and clean up resources."""
        self.executor.shutdown(wait=True)

    def get_performance_stats(self, results: list[HookExecutionResult]) -> dict[str, Any]:
        """
        Calculate performance statistics from execution results.

        Args:
            results: List of execution results

        Returns:
            Statistics dictionary
        """
        if not results:
            return {
                "total_hooks": 0,
                "successful_hooks": 0,
                "failed_hooks": 0,
                "total_time_ms": 0,
                "avg_time_ms": 0,
                "max_time_ms": 0,
                "min_time_ms": 0,
                "timeouts": 0,
                "retries": 0,
            }

        execution_times = [r.execution_time_ms for r in results]

        return {
            "total_hooks": len(results),
            "successful_hooks": sum(1 for r in results if r.success),
            "failed_hooks": sum(1 for r in results if not r.success),
            "total_time_ms": sum(execution_times),
            "avg_time_ms": sum(execution_times) / len(execution_times),
            "max_time_ms": max(execution_times),
            "min_time_ms": min(execution_times),
            "timeouts": sum(1 for r in results if r.timed_out),
            "retries": sum(r.retry_count for r in results),
        }


# Helper function to create hook configs from dict
def hook_config_from_dict(data: dict[str, Any]) -> HookConfig:
    """
    Create HookConfig from dictionary.

    Args:
        data: Dictionary with hook configuration

    Returns:
        HookConfig instance
    """
    return HookConfig(
        name=data.get("name", "unnamed"),
        command=data["command"],
        priority=HookPriority(data.get("priority", "normal")),
        timeout_ms=data.get("timeout_ms", 100),
        max_retries=data.get("max_retries", 0),
        retry_delay_ms=data.get("retry_delay_ms", 100),
        env=data.get("env"),
    )
