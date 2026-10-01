"""Data models for the virtual git repository."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class PRStatus(Enum):
    """Pull request status."""
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass
class Commit:
    """Represents a single commit in the virtual repository."""
    sha: str
    message: str
    parent_sha: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    author: str = "learner"
    files_changed: list[str] = field(default_factory=list)


@dataclass
class Branch:
    """Represents a branch pointer."""
    name: str
    commit_sha: str
    upstream: Optional[str] = None
    is_remote: bool = False


@dataclass
class StagedChange:
    """Represents a file staged for commit."""
    filename: str
    change_type: str  # "added", "modified", "deleted"


@dataclass
class PullRequest:
    """Represents a GitHub pull request."""
    number: int
    title: str
    body: str
    source_branch: str
    target_branch: str = "main"
    status: PRStatus = PRStatus.OPEN
    reviews: list[dict] = field(default_factory=list)
    approved: bool = False
    merge_conflicts: bool = False


@dataclass
class RepositoryState:
    """Complete state of the virtual repository."""
    commits: dict[str, Commit] = field(default_factory=dict)
    branches: dict[str, Branch] = field(default_factory=dict)
    remote_branches: dict[str, Branch] = field(default_factory=dict)

    head: str = "main"
    detached_head: bool = False

    staged_changes: list[StagedChange] = field(default_factory=list)
    working_changes: list[str] = field(default_factory=list)

    remote_url: Optional[str] = None
    pull_requests: dict[int, PullRequest] = field(default_factory=dict)
    next_pr_number: int = 1


@dataclass
class CommandResult:
    """Result of executing a command."""
    success: bool
    message: str = ""
    output: Optional[str] = None
    hints: list[str] = field(default_factory=list)


@dataclass
class RepositoryStatus:
    """Status information about the repository."""
    current_branch: str
    upstream: Optional[str] = None
    ahead: int = 0
    behind: int = 0
    staged: list[StagedChange] = field(default_factory=list)
    unstaged: list[str] = field(default_factory=list)
