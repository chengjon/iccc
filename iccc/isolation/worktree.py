"""Git worktree manager for agent isolation."""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional


class WorktreeManager:
    """Manages Git worktrees for agent isolation."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)
        self.worktrees_dir = self.project_dir / "worktrees"

    async def create_worktree(
        self, agent_id: str, branch: Optional[str] = None
    ) -> Path:
        """
        Create a new worktree for an agent.

        Args:
            agent_id: ID of the agent
            branch: Optional branch name (defaults to agent_id)

        Returns:
            Path to the created worktree

        Raises:
            RuntimeError: If worktree creation fails
        """
        # Create worktrees directory if it doesn't exist
        self.worktrees_dir.mkdir(exist_ok=True)

        # Determine branch name
        if branch is None:
            branch = f"agent/{agent_id}"

        # Worktree path
        worktree_path = self.worktrees_dir / agent_id

        # Check if worktree already exists
        if worktree_path.exists():
            # Remove old worktree
            await self.remove_worktree(agent_id)

        # Create new branch if it doesn't exist
        branch_exists = await self._branch_exists(branch)
        if not branch_exists:
            await self._run_git(["git", "branch", branch])

        # Create worktree
        cmd = ["git", "worktree", "add", str(worktree_path), branch]
        result = await self._run_git(cmd)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        # Configure worktree
        await self._configure_worktree(worktree_path, agent_id)

        return worktree_path

    async def remove_worktree(self, agent_id: str) -> None:
        """
        Remove an agent's worktree.

        Args:
            agent_id: ID of the agent
        """
        worktree_path = self.worktrees_dir / agent_id

        if not worktree_path.exists():
            return

        # Remove worktree
        cmd = ["git", "worktree", "remove", str(worktree_path), "--force"]
        await self._run_git(cmd)

        # Clean up directory if it still exists
        if worktree_path.exists():
            shutil.rmtree(worktree_path)

    async def list_worktrees(self) -> list[dict]:
        """
        List all worktrees.

        Returns:
            List of worktree information dictionaries
        """
        cmd = ["git", "worktree", "list", "--porcelain"]
        result = await self._run_git(cmd)

        if result.returncode != 0:
            return []

        # Parse output
        worktrees = []
        current_worktree = {}

        for line in result.stdout.strip().split("\n"):
            if not line:
                if current_worktree:
                    worktrees.append(current_worktree)
                    current_worktree = {}
                continue

            if line.startswith("worktree "):
                current_worktree["path"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                current_worktree["branch"] = line.split(" ", 1)[1]
            elif line.startswith("HEAD "):
                current_worktree["commit"] = line.split(" ", 1)[1]

        if current_worktree:
            worktrees.append(current_worktree)

        return worktrees

    async def get_worktree_path(self, agent_id: str) -> Optional[Path]:
        """
        Get the path to an agent's worktree.

        Args:
            agent_id: ID of the agent

        Returns:
            Path to worktree or None if doesn't exist
        """
        worktree_path = self.worktrees_dir / agent_id

        if worktree_path.exists():
            return worktree_path

        return None

    async def sync_worktree(self, agent_id: str, source_branch: str = "main") -> None:
        """
        Sync a worktree with the source branch.

        Args:
            agent_id: ID of the agent
            source_branch: Branch to sync from (default: main)
        """
        worktree_path = await self.get_worktree_path(agent_id)

        if not worktree_path:
            raise RuntimeError(f"Worktree for agent {agent_id} not found")

        # Run git commands in worktree directory
        async def run_in_worktree(cmd: list[str]) -> asyncio.subprocess.Process:
            return await self._run_git(cmd, cwd=worktree_path)

        # Fetch latest changes
        await run_in_worktree(["git", "fetch", "origin", source_branch])

        # Merge or rebase
        await run_in_worktree(["git", "merge", f"origin/{source_branch}"])

    async def commit_changes(
        self, agent_id: str, message: str, files: Optional[list[str]] = None
    ) -> bool:
        """
        Commit changes in an agent's worktree.

        Args:
            agent_id: ID of the agent
            message: Commit message
            files: Optional list of files to commit (defaults to all)

        Returns:
            True if changes were committed, False if nothing to commit
        """
        worktree_path = await self.get_worktree_path(agent_id)

        if not worktree_path:
            raise RuntimeError(f"Worktree for agent {agent_id} not found")

        async def run_in_worktree(cmd: list[str]) -> asyncio.subprocess.Process:
            return await self._run_git(cmd, cwd=worktree_path)

        # Add files
        if files:
            for file_path in files:
                await run_in_worktree(["git", "add", file_path])
        else:
            await run_in_worktree(["git", "add", "-A"])

        # Check if there are changes to commit
        status_result = await run_in_worktree(["git", "status", "--porcelain"])
        if not status_result.stdout.strip():
            return False

        # Commit
        result = await run_in_worktree(["git", "commit", "-m", message])

        return result.returncode == 0

    async def _branch_exists(self, branch: str) -> bool:
        """Check if a branch exists."""
        result = await self._run_git(["git", "rev-parse", "--verify", branch])
        return result.returncode == 0

    async def _run_git(
        self, cmd: list[str], cwd: Optional[Path] = None
    ) -> asyncio.subprocess.Process:
        """
        Run a git command.

        Args:
            cmd: Command to run
            cwd: Working directory (defaults to project_dir)

        Returns:
            Completed process
        """
        if cwd is None:
            cwd = self.project_dir

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        # Create a mock process object with the results
        class ProcessResult:
            def __init__(self, returncode: int, stdout: str, stderr: str):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        return ProcessResult(
            process.returncode or 0,
            stdout.decode("utf-8") if stdout else "",
            stderr.decode("utf-8") if stderr else "",
        )

    async def cleanup_all_worktrees(self) -> None:
        """Remove all worktrees (useful for cleanup)."""
        worktrees = await self.list_worktrees()

        for worktree in worktrees:
            worktree_path = Path(worktree["path"])

            # Skip the main worktree
            if worktree_path == self.project_dir:
                continue

            # Extract agent_id from path
            if self.worktrees_dir in worktree_path.parents:
                agent_id = worktree_path.name
                await self.remove_worktree(agent_id)

    async def _configure_worktree(self, worktree_path: Path, agent_id: str) -> None:
        """
        Configure Git settings for a worktree.

        Args:
            worktree_path: Path to the worktree
            agent_id: ID of the agent
        """
        # Set user info for commits
        await self._run_git(
            ["git", "config", "user.name", f"Agent {agent_id}"], cwd=worktree_path
        )
        await self._run_git(
            ["git", "config", "user.email", f"{agent_id}@iccc.local"], cwd=worktree_path
        )

        # Optional: Disable certain hooks in worktree if needed
        # This prevents hooks from interfering with automated agent workflows
