"""Git-aware file tracking for incremental indexing."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileChange:
    """Represents a file change."""

    path: str
    status: str  # 'A' (added), 'M' (modified), 'D' (deleted), 'R' (renamed)
    old_path: str | None = None  # For renames


class GitTracker:
    """Track file changes using git."""

    def __init__(self, repo_path: Path):
        """Initialize with repository path."""
        self.repo_path = repo_path
        self._git_dir = repo_path / ".git"

    def is_git_repo(self) -> bool:
        """Check if the path is a git repository."""
        return self._git_dir.exists()

    def get_current_commit(self) -> str | None:
        """Get current HEAD commit hash."""
        if not self.is_git_repo():
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_changes_since(self, commit: str) -> list[FileChange]:
        """Get list of files changed since a specific commit."""
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", commit, "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []

            changes = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                status = parts[0]

                if status.startswith("R"):
                    # Rename: R100	old_path	new_path
                    old_path = parts[1] if len(parts) > 1 else None
                    new_path = parts[2] if len(parts) > 2 else None
                    if new_path:
                        changes.append(FileChange(path=new_path, status="R", old_path=old_path))
                else:
                    path = parts[1] if len(parts) > 1 else None
                    if path:
                        changes.append(FileChange(path=path, status=status[0]))

            return changes
        except Exception:
            return []

    def get_staged_changes(self) -> list[FileChange]:
        """Get list of staged (uncommitted) changes."""
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", "--cached"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []

            changes = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                status = parts[0]
                path = parts[1] if len(parts) > 1 else None

                if path:
                    changes.append(FileChange(path=path, status=status[0]))

            return changes
        except Exception:
            return []

    def get_unstaged_changes(self) -> list[FileChange]:
        """Get list of unstaged (working directory) changes."""
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ["git", "diff", "--name-status"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []

            changes = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                status = parts[0]
                path = parts[1] if len(parts) > 1 else None

                if path:
                    changes.append(FileChange(path=path, status=status[0]))

            return changes
        except Exception:
            return []

    def get_untracked_files(self) -> list[str]:
        """Get list of untracked files."""
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []

            return [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            return []

    def get_all_tracked_files(self) -> list[str]:
        """Get list of all tracked files."""
        if not self.is_git_repo():
            return []

        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []

            return [f for f in result.stdout.strip().split("\n") if f]
        except Exception:
            return []

    def is_ignored(self, path: str) -> bool:
        """Check if a path is ignored by git."""
        if not self.is_git_repo():
            return False

        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", path],
                cwd=self.repo_path,
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
