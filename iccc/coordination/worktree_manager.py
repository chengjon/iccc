"""Git worktree manager for agent isolation."""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WorktreeInfo:
    """Information about a Git worktree."""

    path: Path
    branch: str
    commit: str
    is_bare: bool
    is_detached: bool


class WorktreeManager:
    """
    Manages Git worktrees for agent isolation.

    Each agent gets its own worktree to avoid conflicts.
    """

    def __init__(self, project_root: Path) -> None:
        """
        Initialize worktree manager.

        Args:
            project_root: Root directory of the Git repository
        """
        self.project_root = project_root

        if not self._is_git_repo():
            raise ValueError(f"{project_root} is not a Git repository")

    def create_worktree(
        self,
        agent_id: str,
        branch_name: str,
        base_branch: str = "main",
    ) -> Path:
        """
        Create a new worktree for an agent.

        Args:
            agent_id: ID of the agent
            branch_name: Name of the branch to create
            base_branch: Base branch to branch from

        Returns:
            Path to the created worktree

        Raises:
            RuntimeError: If worktree creation fails
        """
        worktree_path = self.project_root / ".worktrees" / agent_id

        # Ensure worktrees directory exists
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Create new branch from base
            self._run_git(["branch", branch_name, base_branch])

            # Create worktree
            self._run_git(
                ["worktree", "add", str(worktree_path), branch_name]
            )

            # Configure worktree
            self._configure_worktree(worktree_path, agent_id)

            logger.info(
                f"Created worktree for {agent_id} at {worktree_path} (branch: {branch_name})"
            )

            return worktree_path

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create worktree: {e}")
            raise RuntimeError(f"Worktree creation failed: {e}")

    def sync_worktree(self, worktree_path: Path, base_branch: str = "main") -> None:
        """
        Sync worktree with base branch.

        Args:
            worktree_path: Path to worktree
            base_branch: Base branch to sync with

        Raises:
            RuntimeError: If sync fails
        """
        try:
            # Fetch latest changes
            self._run_git(["fetch", "origin"], cwd=worktree_path)

            # Rebase on base branch
            self._run_git(
                ["rebase", f"origin/{base_branch}"], cwd=worktree_path
            )

            logger.info(f"Synced worktree {worktree_path} with {base_branch}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to sync worktree: {e}")
            raise RuntimeError(f"Worktree sync failed: {e}")

    def cleanup_worktree(self, agent_id: str) -> None:
        """
        Remove a worktree.

        Args:
            agent_id: ID of the agent

        Raises:
            RuntimeError: If cleanup fails
        """
        worktree_path = self.project_root / ".worktrees" / agent_id

        if not worktree_path.exists():
            logger.warning(f"Worktree {worktree_path} does not exist")
            return

        try:
            # Get branch name before removing worktree
            branch_name = self._get_worktree_branch(worktree_path)

            # Remove worktree
            self._run_git(["worktree", "remove", str(worktree_path), "--force"])

            # Delete branch
            if branch_name:
                try:
                    self._run_git(["branch", "-D", branch_name])
                except subprocess.CalledProcessError:
                    logger.warning(f"Failed to delete branch {branch_name}")

            logger.info(f"Cleaned up worktree for {agent_id}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to cleanup worktree: {e}")
            raise RuntimeError(f"Worktree cleanup failed: {e}")

    def list_worktrees(self) -> list[WorktreeInfo]:
        """
        List all worktrees.

        Returns:
            List of worktree information
        """
        try:
            output = self._run_git(["worktree", "list", "--porcelain"])

            worktrees = []
            current_worktree = {}

            for line in output.strip().split("\n"):
                if not line:
                    if current_worktree:
                        worktrees.append(self._parse_worktree_info(current_worktree))
                        current_worktree = {}
                    continue

                if line.startswith("worktree "):
                    current_worktree["path"] = line.split(" ", 1)[1]
                elif line.startswith("HEAD "):
                    current_worktree["commit"] = line.split(" ", 1)[1]
                elif line.startswith("branch "):
                    current_worktree["branch"] = line.split(" ", 1)[1]
                elif line == "bare":
                    current_worktree["bare"] = True
                elif line == "detached":
                    current_worktree["detached"] = True

            # Add last worktree
            if current_worktree:
                worktrees.append(self._parse_worktree_info(current_worktree))

            return worktrees

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list worktrees: {e}")
            return []

    def get_worktree_path(self, agent_id: str) -> Path | None:
        """Get worktree path for an agent."""
        worktree_path = self.project_root / ".worktrees" / agent_id

        if worktree_path.exists():
            return worktree_path

        return None

    def _configure_worktree(self, worktree_path: Path, agent_id: str) -> None:
        """Configure Git settings for worktree."""
        # Set user info for commits
        self._run_git(
            ["config", "user.name", f"Agent {agent_id}"],
            cwd=worktree_path,
        )

        # Optional: Set other worktree-specific configs
        # e.g., disable certain hooks, set branch tracking, etc.

    def _get_worktree_branch(self, worktree_path: Path) -> str | None:
        """Get branch name for a worktree."""
        try:
            branch = self._run_git(
                ["rev-parse", "--abbrev-ref", "HEAD"],
                cwd=worktree_path,
            ).strip()
            return branch if branch != "HEAD" else None
        except subprocess.CalledProcessError:
            return None

    def _is_git_repo(self) -> bool:
        """Check if directory is a Git repository."""
        try:
            self._run_git(["rev-parse", "--git-dir"])
            return True
        except subprocess.CalledProcessError:
            return False

    def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
    ) -> str:
        """
        Run a Git command.

        Args:
            args: Git command arguments
            cwd: Working directory (defaults to project_root)

        Returns:
            Command output

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        cmd = ["git"] + args
        cwd = cwd or self.project_root

        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout

    def _parse_worktree_info(self, data: dict) -> WorktreeInfo:
        """Parse worktree info from git worktree list output."""
        return WorktreeInfo(
            path=Path(data.get("path", "")),
            branch=data.get("branch", ""),
            commit=data.get("commit", ""),
            is_bare=data.get("bare", False),
            is_detached=data.get("detached", False),
        )
