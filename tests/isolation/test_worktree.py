"""Tests for Git worktree management."""

import asyncio
from pathlib import Path
import tempfile
import shutil

import pytest

from iccc.isolation.worktree import WorktreeManager


@pytest.fixture
async def temp_git_repo():
    """Create a temporary git repository for testing."""
    temp_dir = Path(tempfile.mkdtemp())

    try:
        # Initialize git repo
        proc = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Configure git
        proc = await asyncio.create_subprocess_exec(
            "git", "config", "user.name", "Test User",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git", "config", "user.email", "test@example.com",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # Create initial commit
        readme = temp_dir / "README.md"
        readme.write_text("# Test Repo")

        proc = await asyncio.create_subprocess_exec(
            "git", "add", "README.md",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", "Initial commit",
            cwd=str(temp_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        yield temp_dir

    finally:
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_create_worktree(temp_git_repo):
    """Test creating a worktree."""
    manager = WorktreeManager(str(temp_git_repo))

    # Create worktree
    worktree_path = await manager.create_worktree("agent-001")

    assert worktree_path.exists()
    assert worktree_path.is_dir()
    assert (worktree_path / "README.md").exists()

    # Cleanup
    await manager.remove_worktree("agent-001")


@pytest.mark.asyncio
async def test_create_worktree_with_custom_branch(temp_git_repo):
    """Test creating a worktree with custom branch name."""
    manager = WorktreeManager(str(temp_git_repo))

    # Create worktree with custom branch
    worktree_path = await manager.create_worktree("agent-002", branch="feature/test")

    assert worktree_path.exists()

    # Verify branch was created
    proc = await asyncio.create_subprocess_exec(
        "git", "branch", "--list", "feature/test",
        cwd=str(temp_git_repo),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    assert "feature/test" in stdout.decode()

    # Cleanup
    await manager.remove_worktree("agent-002")


@pytest.mark.asyncio
async def test_remove_worktree(temp_git_repo):
    """Test removing a worktree."""
    manager = WorktreeManager(str(temp_git_repo))

    # Create and then remove worktree
    worktree_path = await manager.create_worktree("agent-003")
    assert worktree_path.exists()

    await manager.remove_worktree("agent-003")
    assert not worktree_path.exists()


@pytest.mark.asyncio
async def test_list_worktrees(temp_git_repo):
    """Test listing worktrees."""
    manager = WorktreeManager(str(temp_git_repo))

    # Create multiple worktrees
    await manager.create_worktree("agent-004")
    await manager.create_worktree("agent-005")

    # List worktrees
    worktrees = await manager.list_worktrees()

    # Should have main worktree + 2 agent worktrees
    assert len(worktrees) >= 3

    # Check that our agent worktrees are in the list
    worktree_paths = [wt["path"] for wt in worktrees]
    assert any("agent-004" in path for path in worktree_paths)
    assert any("agent-005" in path for path in worktree_paths)

    # Cleanup
    await manager.remove_worktree("agent-004")
    await manager.remove_worktree("agent-005")


@pytest.mark.asyncio
async def test_get_worktree_path(temp_git_repo):
    """Test getting worktree path."""
    manager = WorktreeManager(str(temp_git_repo))

    # Before creation, should return None
    path = await manager.get_worktree_path("agent-006")
    assert path is None

    # After creation, should return valid path
    await manager.create_worktree("agent-006")
    path = await manager.get_worktree_path("agent-006")
    assert path is not None
    assert path.exists()

    # Cleanup
    await manager.remove_worktree("agent-006")


@pytest.mark.asyncio
async def test_worktree_configuration(temp_git_repo):
    """Test that worktree is configured with correct Git settings."""
    manager = WorktreeManager(str(temp_git_repo))

    # Create worktree
    worktree_path = await manager.create_worktree("agent-014")

    # Check git config in worktree
    proc = await asyncio.create_subprocess_exec(
        "git", "config", "user.name",
        cwd=str(worktree_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    assert "Agent agent-014" in stdout.decode()

    proc = await asyncio.create_subprocess_exec(
        "git", "config", "user.email",
        cwd=str(worktree_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    assert "agent-014@iccc.local" in stdout.decode()

    # Cleanup
    await manager.remove_worktree("agent-014")


@pytest.mark.asyncio
async def test_recreate_existing_worktree(temp_git_repo):
    """Test that creating a worktree removes old one if it exists."""
    manager = WorktreeManager(str(temp_git_repo))

    # Create worktree
    path1 = await manager.create_worktree("agent-015")

    # Create marker file
    marker = path1 / "marker.txt"
    marker.write_text("first")

    # Recreate worktree with same agent_id
    path2 = await manager.create_worktree("agent-015")

    # Should be same path
    assert path1 == path2

    # Marker file should be gone (fresh worktree)
    assert not (path2 / "marker.txt").exists()

    # Cleanup
    await manager.remove_worktree("agent-015")
