"""Virtual git repository simulation."""

import hashlib
import random
import string
from datetime import datetime
from typing import Optional

from .models import (
    Branch,
    Commit,
    CommandResult,
    RepositoryState,
    RepositoryStatus,
    StagedChange,
)


class VirtualRepository:
    """
    Manages the simulated git repository state.
    All git operations modify this state without touching the filesystem.
    """

    def __init__(self):
        self.state = RepositoryState()
        self._initialize_repo()

    def _initialize_repo(self) -> None:
        """Create initial commit and main branch."""
        initial_commit = Commit(
            sha=self._generate_sha(),
            message="Initial commit",
            parent_sha=None,
            files_changed=["README.md"],
        )
        self.state.commits[initial_commit.sha] = initial_commit
        self.state.branches["main"] = Branch(
            name="main",
            commit_sha=initial_commit.sha,
        )
        self.state.head = "main"
        self.state.remote_url = "https://github.com/learner/my-project.git"

    def _generate_sha(self) -> str:
        """Generate a random 7-character SHA-like string."""
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choices(chars, k=7))

    def get_current_branch(self) -> str:
        """Get the name of the current branch."""
        return self.state.head

    def get_current_commit(self) -> Commit:
        """Get the current HEAD commit."""
        branch = self.state.branches[self.state.head]
        return self.state.commits[branch.commit_sha]

    # Branch operations

    def create_branch(
        self, name: str, start_point: Optional[str] = None
    ) -> CommandResult:
        """Create a new branch."""
        if name in self.state.branches:
            return CommandResult(
                success=False,
                message=f"fatal: a branch named '{name}' already exists",
            )

        if start_point:
            if start_point in self.state.branches:
                base_sha = self.state.branches[start_point].commit_sha
            elif start_point in self.state.commits:
                base_sha = start_point
            else:
                return CommandResult(
                    success=False,
                    message=f"fatal: not a valid object name: '{start_point}'",
                )
        else:
            base_sha = self.state.branches[self.state.head].commit_sha

        self.state.branches[name] = Branch(name=name, commit_sha=base_sha)
        return CommandResult(success=True, message="")

    def delete_branch(self, name: str, force: bool = False) -> CommandResult:
        """Delete a branch."""
        if name not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"error: branch '{name}' not found",
            )

        if name == self.state.head:
            return CommandResult(
                success=False,
                message=f"error: cannot delete branch '{name}' used by worktree",
            )

        if name == "main" and not force:
            return CommandResult(
                success=False,
                message="error: cannot delete the main branch",
            )

        del self.state.branches[name]
        return CommandResult(
            success=True,
            output=f"Deleted branch {name}.",
        )

    def checkout(self, target: str, create: bool = False) -> CommandResult:
        """Switch to a branch or create and switch."""
        if create:
            if target in self.state.branches:
                return CommandResult(
                    success=False,
                    message=f"fatal: a branch named '{target}' already exists",
                )
            result = self.create_branch(target)
            if not result.success:
                return result

        if target not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"error: pathspec '{target}' did not match any branch",
                hints=[f"Did you mean to create branch '{target}'? Use: git checkout -b {target}"],
            )

        self.state.head = target
        return CommandResult(
            success=True,
            output=f"Switched to branch '{target}'",
        )

    def list_branches(self, all_branches: bool = False) -> CommandResult:
        """List all branches."""
        lines = []
        for name in sorted(self.state.branches.keys()):
            if self.state.branches[name].is_remote and not all_branches:
                continue
            prefix = "* " if name == self.state.head else "  "
            lines.append(f"{prefix}{name}")

        if all_branches:
            for name in sorted(self.state.remote_branches.keys()):
                lines.append(f"  remotes/{name}")

        return CommandResult(success=True, output="\n".join(lines))

    # Staging operations

    def add_file(self, filename: str) -> CommandResult:
        """Stage a file for commit."""
        if filename in (".", "-A", "--all"):
            # Stage all working changes
            for f in self.state.working_changes:
                self.state.staged_changes.append(
                    StagedChange(filename=f, change_type="modified")
                )
            self.state.working_changes = []
            return CommandResult(success=True, message="")

        # Add specific file
        change_type = "modified"
        if filename in self.state.working_changes:
            self.state.working_changes.remove(filename)
            change_type = "modified"
        else:
            change_type = "added"

        # Check if already staged
        for change in self.state.staged_changes:
            if change.filename == filename:
                return CommandResult(success=True, message="")

        self.state.staged_changes.append(
            StagedChange(filename=filename, change_type=change_type)
        )
        return CommandResult(success=True, message="")

    def unstage_file(self, filename: str) -> CommandResult:
        """Remove a file from staging."""
        for i, change in enumerate(self.state.staged_changes):
            if change.filename == filename:
                self.state.staged_changes.pop(i)
                self.state.working_changes.append(filename)
                return CommandResult(success=True, message="")

        return CommandResult(
            success=False,
            message=f"error: pathspec '{filename}' is not staged",
        )

    # Commit operations

    def commit(self, message: str, add_all: bool = False) -> CommandResult:
        """Create a new commit."""
        if add_all:
            self.add_file("-A")

        if not self.state.staged_changes:
            return CommandResult(
                success=False,
                message="nothing to commit, working tree clean",
                hints=["Use 'git add <file>' to stage changes"],
            )

        files = [c.filename for c in self.state.staged_changes]
        parent_sha = self.state.branches[self.state.head].commit_sha

        new_commit = Commit(
            sha=self._generate_sha(),
            message=message,
            parent_sha=parent_sha,
            files_changed=files,
        )

        self.state.commits[new_commit.sha] = new_commit
        self.state.branches[self.state.head].commit_sha = new_commit.sha
        self.state.staged_changes = []

        file_count = len(files)
        file_word = "file" if file_count == 1 else "files"
        return CommandResult(
            success=True,
            output=f"[{self.state.head} {new_commit.sha}] {message}\n {file_count} {file_word} changed",
        )

    def get_log(self, count: int = 10, oneline: bool = False) -> CommandResult:
        """Get commit history."""
        lines = []
        current_sha = self.state.branches[self.state.head].commit_sha

        visited = 0
        while current_sha and visited < count:
            commit = self.state.commits.get(current_sha)
            if not commit:
                break

            decorations = self._get_decorations(current_sha)
            dec_str = f" ({', '.join(decorations)})" if decorations else ""

            if oneline:
                lines.append(f"{commit.sha}{dec_str} {commit.message}")
            else:
                lines.append(f"commit {commit.sha}{dec_str}")
                lines.append(f"Author: {commit.author}")
                lines.append(f"Date:   {commit.timestamp.strftime('%a %b %d %H:%M:%S %Y')}")
                lines.append("")
                lines.append(f"    {commit.message}")
                lines.append("")

            current_sha = commit.parent_sha
            visited += 1

        return CommandResult(success=True, output="\n".join(lines))

    def _get_decorations(self, sha: str) -> list[str]:
        """Get branch decorations for a commit."""
        decorations = []

        if self.state.branches[self.state.head].commit_sha == sha:
            decorations.append(f"HEAD -> {self.state.head}")

        for name, branch in self.state.branches.items():
            if branch.commit_sha == sha and name != self.state.head:
                decorations.append(name)

        for name, branch in self.state.remote_branches.items():
            if branch.commit_sha == sha:
                decorations.append(name)

        return decorations

    # Remote operations

    def push(
        self,
        remote: str = "origin",
        branch: Optional[str] = None,
        set_upstream: bool = False,
    ) -> CommandResult:
        """Push branch to remote."""
        branch_name = branch or self.state.head

        if branch_name not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"error: src refspec {branch_name} does not match any",
            )

        local_branch = self.state.branches[branch_name]
        remote_name = f"{remote}/{branch_name}"

        # Simulate push by creating/updating remote branch
        self.state.remote_branches[remote_name] = Branch(
            name=remote_name,
            commit_sha=local_branch.commit_sha,
            is_remote=True,
        )

        if set_upstream:
            local_branch.upstream = remote_name

        output_lines = [
            f"Enumerating objects: 5, done.",
            f"Counting objects: 100% (5/5), done.",
            f"Writing objects: 100% (3/3), 298 bytes | 298.00 KiB/s, done.",
            f"Total 3 (delta 0), reused 0 (delta 0)",
            f"remote: Create a pull request for '{branch_name}' on GitHub by visiting:",
            f"remote:      https://github.com/learner/my-project/pull/new/{branch_name}",
            f"To {self.state.remote_url}",
        ]

        if remote_name not in self.state.remote_branches:
            output_lines.append(f" * [new branch]      {branch_name} -> {branch_name}")
        else:
            output_lines.append(f"   {local_branch.commit_sha[:7]}..{local_branch.commit_sha[:7]}  {branch_name} -> {branch_name}")

        if set_upstream:
            output_lines.append(f"branch '{branch_name}' set up to track '{remote_name}'")

        return CommandResult(success=True, output="\n".join(output_lines))

    def pull(self, remote: str = "origin", branch: Optional[str] = None) -> CommandResult:
        """Pull changes from remote."""
        branch_name = branch or self.state.head
        remote_name = f"{remote}/{branch_name}"

        if remote_name not in self.state.remote_branches:
            return CommandResult(
                success=True,
                output="Already up to date.",
            )

        return CommandResult(
            success=True,
            output="Already up to date.",
        )

    def fetch(self, remote: str = "origin") -> CommandResult:
        """Fetch from remote."""
        return CommandResult(
            success=True,
            output=f"From {self.state.remote_url}\n * branch            main       -> FETCH_HEAD",
        )

    # Merge operations

    def merge(self, branch: str, no_ff: bool = False) -> CommandResult:
        """Merge a branch into current branch."""
        if branch not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"merge: {branch} - not something we can merge",
            )

        source_branch = self.state.branches[branch]
        target_branch = self.state.branches[self.state.head]

        # Simple simulation: just update the commit pointer
        source_commit = self.state.commits[source_branch.commit_sha]

        if no_ff or True:  # Always create merge commit for learning purposes
            merge_commit = Commit(
                sha=self._generate_sha(),
                message=f"Merge branch '{branch}' into {self.state.head}",
                parent_sha=target_branch.commit_sha,
                files_changed=source_commit.files_changed,
            )
            self.state.commits[merge_commit.sha] = merge_commit
            target_branch.commit_sha = merge_commit.sha

        return CommandResult(
            success=True,
            output=f"Merge made by the 'ort' strategy.\n {len(source_commit.files_changed)} file(s) changed",
        )

    # Status

    def status(self) -> RepositoryStatus:
        """Get repository status."""
        current_branch = self.state.branches[self.state.head]
        upstream = current_branch.upstream

        ahead = 0
        behind = 0
        if upstream and upstream in self.state.remote_branches:
            # Simplified: compare commit SHAs
            local_sha = current_branch.commit_sha
            remote_sha = self.state.remote_branches[upstream].commit_sha
            if local_sha != remote_sha:
                ahead = 1

        return RepositoryStatus(
            current_branch=self.state.head,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            staged=list(self.state.staged_changes),
            unstaged=list(self.state.working_changes),
        )

    def get_status_output(self) -> CommandResult:
        """Get formatted status output."""
        status = self.status()
        lines = [f"On branch {status.current_branch}"]

        if status.upstream:
            if status.ahead > 0:
                lines.append(
                    f"Your branch is ahead of '{status.upstream}' by {status.ahead} commit(s)."
                )
                lines.append('  (use "git push" to publish your local commits)')
            elif status.behind > 0:
                lines.append(
                    f"Your branch is behind '{status.upstream}' by {status.behind} commit(s)."
                )
            else:
                lines.append(f"Your branch is up to date with '{status.upstream}'.")
        else:
            lines.append("")

        if status.staged:
            lines.append("")
            lines.append("Changes to be committed:")
            lines.append('  (use "git restore --staged <file>..." to unstage)')
            for change in status.staged:
                lines.append(f"        {change.change_type}:   {change.filename}")

        if status.unstaged:
            lines.append("")
            lines.append("Changes not staged for commit:")
            lines.append('  (use "git add <file>..." to update what will be committed)')
            for filename in status.unstaged:
                lines.append(f"        modified:   {filename}")

        if not status.staged and not status.unstaged:
            lines.append("")
            lines.append("nothing to commit, working tree clean")

        return CommandResult(success=True, output="\n".join(lines))

    # State management

    def add_working_change(self, filename: str) -> None:
        """Add a simulated file change to working directory."""
        if filename not in self.state.working_changes:
            self.state.working_changes.append(filename)

    def export_state(self) -> dict:
        """Export repository state for saving."""
        return {
            "commits": {
                sha: {
                    "sha": c.sha,
                    "message": c.message,
                    "parent_sha": c.parent_sha,
                    "files_changed": c.files_changed,
                }
                for sha, c in self.state.commits.items()
            },
            "branches": {
                name: {"name": b.name, "commit_sha": b.commit_sha, "upstream": b.upstream}
                for name, b in self.state.branches.items()
            },
            "head": self.state.head,
            "staged_changes": [
                {"filename": s.filename, "change_type": s.change_type}
                for s in self.state.staged_changes
            ],
            "working_changes": self.state.working_changes,
        }

    def import_state(self, data: dict) -> None:
        """Import repository state."""
        self.state = RepositoryState()

        for sha, commit_data in data.get("commits", {}).items():
            self.state.commits[sha] = Commit(
                sha=commit_data["sha"],
                message=commit_data["message"],
                parent_sha=commit_data.get("parent_sha"),
                files_changed=commit_data.get("files_changed", []),
            )

        for name, branch_data in data.get("branches", {}).items():
            self.state.branches[name] = Branch(
                name=branch_data["name"],
                commit_sha=branch_data["commit_sha"],
                upstream=branch_data.get("upstream"),
            )

        self.state.head = data.get("head", "main")

        for change_data in data.get("staged_changes", []):
            self.state.staged_changes.append(
                StagedChange(
                    filename=change_data["filename"],
                    change_type=change_data["change_type"],
                )
            )

        self.state.working_changes = data.get("working_changes", [])
