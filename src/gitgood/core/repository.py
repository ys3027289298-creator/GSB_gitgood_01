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
    PRStatus,
    RebaseState,
    RebaseStatus,
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

    def _rebase_guard(self) -> Optional[CommandResult]:
        """Return an error result if a rebase is in progress, else None."""
        if self.state.rebase.status != RebaseStatus.IDLE:
            return CommandResult(
                success=False,
                message="error: cannot run this command while a rebase is in progress",
                hints=[
                    "Resolve conflicts with 'git add <file>' then 'git rebase --continue'",
                    "Or roll back with 'git rebase --abort'",
                ],
            )
        return None

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
        guard = self._rebase_guard()
        if guard:
            return guard

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
                self._stage_file(f, "modified")
            self.state.working_changes = []
            return CommandResult(success=True, message="")

        # Add specific file
        change_type = "modified"
        if filename in self.state.working_changes:
            self.state.working_changes.remove(filename)
            change_type = "modified"
        else:
            change_type = "added"

        self._stage_file(filename, change_type)
        return CommandResult(success=True, message="")

    def _stage_file(self, filename: str, change_type: str) -> None:
        """Stage a file, replacing any existing staged entry (idempotent)."""
        for change in self.state.staged_changes:
            if change.filename == filename:
                change.change_type = change_type
                return
        self.state.staged_changes.append(
            StagedChange(filename=filename, change_type=change_type)
        )

    def unstage_file(self, filename: str) -> CommandResult:
        """Remove a file from staging."""
        for i, change in enumerate(self.state.staged_changes):
            if change.filename == filename:
                self.state.staged_changes.pop(i)
                if filename not in self.state.working_changes:
                    self.state.working_changes.append(filename)
                return CommandResult(success=True, message="")

        return CommandResult(
            success=False,
            message=f"error: pathspec '{filename}' is not staged",
        )

    # Commit operations

    def commit(self, message: str, add_all: bool = False) -> CommandResult:
        """Create a new commit."""
        if self.state.rebase.status == RebaseStatus.CONFLICT:
            return CommandResult(
                success=False,
                message="error: cannot commit during a rebase conflict",
                hints=[
                    "Resolve conflicts with 'git add <file>' then 'git rebase --continue'",
                    "Or roll back with 'git rebase --abort'",
                ],
            )

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

        is_new_remote = remote_name not in self.state.remote_branches
        old_remote_sha = (
            self.state.remote_branches[remote_name].commit_sha
            if not is_new_remote
            else None
        )

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

        if is_new_remote:
            output_lines.append(f" * [new branch]      {branch_name} -> {branch_name}")
        elif old_remote_sha is not None:
            output_lines.append(f"   {old_remote_sha[:7]}..{local_branch.commit_sha[:7]}  {branch_name} -> {branch_name}")

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
        return self.merge_into(self.state.head, branch, no_ff=no_ff)

    def merge_into(self, target: str, branch: str, no_ff: bool = False) -> CommandResult:
        """Merge ``branch`` into ``target`` without moving HEAD.

        Atomic: on any failure the repository state is left untouched.
        """
        guard = self._rebase_guard()
        if guard:
            return guard

        if branch not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"merge: {branch} - not something we can merge",
            )

        if target not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"merge: {target} - not something we can merge into",
            )

        source_branch = self.state.branches[branch]
        target_branch = self.state.branches[target]
        source_commit = self.state.commits[source_branch.commit_sha]

        if source_branch.commit_sha == target_branch.commit_sha or self._is_ancestor(
            source_branch.commit_sha, target_branch.commit_sha
        ):
            return CommandResult(success=True, output="Already up to date.")

        if not no_ff and self._is_ancestor(
            target_branch.commit_sha, source_branch.commit_sha
        ):
            target_branch.commit_sha = source_branch.commit_sha
            return CommandResult(
                success=True,
                output=f"Fast-forward\n {source_commit.sha[:7]}..{target_branch.commit_sha[:7]}  {target} -> {branch}",
            )

        merge_commit = Commit(
            sha=self._generate_sha(),
            message=f"Merge branch '{branch}' into {target}",
            parent_sha=target_branch.commit_sha,
            merge_parent_sha=source_branch.commit_sha,
            files_changed=source_commit.files_changed,
        )
        self.state.commits[merge_commit.sha] = merge_commit
        target_branch.commit_sha = merge_commit.sha

        return CommandResult(
            success=True,
            output=f"Merge made by the 'ort' strategy.\n {len(source_commit.files_changed)} file(s) changed",
        )

    # Rebase operations

    def _reachable_shas(self, start_sha: str) -> set[str]:
        """All commit SHAs reachable from start (following both parents)."""
        seen: set[str] = set()
        stack = [start_sha]
        while stack:
            sha = stack.pop()
            if sha in seen or sha not in self.state.commits:
                continue
            seen.add(sha)
            commit = self.state.commits[sha]
            if commit.parent_sha:
                stack.append(commit.parent_sha)
            if commit.merge_parent_sha:
                stack.append(commit.merge_parent_sha)
        return seen

    def _is_ancestor(self, ancestor_sha: str, sha: str) -> bool:
        """Check whether ancestor_sha is reachable from sha."""
        return ancestor_sha in self._reachable_shas(sha)

    def _commits_to_replay(self, head_sha: str, upstream_sha: str) -> list[str]:
        """Commits on the current branch that are not on upstream, oldest first."""
        upstream_reachable = self._reachable_shas(upstream_sha)
        replay: list[str] = []
        sha: Optional[str] = head_sha
        while sha and sha not in upstream_reachable:
            commit = self.state.commits.get(sha)
            if not commit:
                break
            replay.append(sha)
            sha = commit.parent_sha
        replay.reverse()
        return replay

    def rebase(self, upstream: str) -> CommandResult:
        """Rebase the current branch onto another branch."""
        if self.state.rebase.status != RebaseStatus.IDLE:
            return CommandResult(
                success=False,
                message="fatal: a rebase is already in progress",
                hints=["Use 'git rebase --continue' or 'git rebase --abort'"],
            )

        if upstream not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"fatal: invalid upstream '{upstream}'",
            )

        if self.state.staged_changes or self.state.working_changes:
            return CommandResult(
                success=False,
                message="error: cannot rebase: you have unstaged or uncommitted changes",
                hints=["Commit or reset your changes before rebasing"],
            )

        branch_name = self.state.head
        branch = self.state.branches[branch_name]
        onto_sha = self.state.branches[upstream].commit_sha

        if branch_name == upstream or self._is_ancestor(onto_sha, branch.commit_sha):
            return CommandResult(
                success=True,
                output=f"Current branch {branch_name} is up to date.",
            )

        if self._is_ancestor(branch.commit_sha, onto_sha):
            branch.commit_sha = onto_sha
            return CommandResult(
                success=True,
                output=f"Successfully rebased and updated refs/heads/{branch_name}.",
            )

        replay = self._commits_to_replay(branch.commit_sha, onto_sha)

        # Conflict simulation: a replayed commit and an upstream-only commit
        # touched the same file.
        upstream_files: set[str] = set()
        for sha in self._reachable_shas(onto_sha) - self._reachable_shas(branch.commit_sha):
            upstream_files.update(self.state.commits[sha].files_changed)
        replay_files: set[str] = set()
        for sha in replay:
            replay_files.update(self.state.commits[sha].files_changed)
        conflicted = sorted(upstream_files & replay_files)

        self.state.rebase = RebaseState(
            status=RebaseStatus.IN_PROGRESS,
            original_branch=branch_name,
            original_sha=branch.commit_sha,
            onto=onto_sha,
            remaining_shas=list(replay),
            conflicted_files=conflicted,
        )
        branch.commit_sha = onto_sha

        if conflicted:
            self.state.rebase.status = RebaseStatus.CONFLICT
            for filename in conflicted:
                self._stage_file(filename, "both modified")
            return CommandResult(
                success=False,
                message=(
                    f"CONFLICT: rebase of '{branch_name}' onto '{upstream}' "
                    f"stopped at conflicting file(s): {', '.join(conflicted)}"
                ),
                hints=[
                    "Resolve with 'git add <file>' then 'git rebase --continue'",
                    "Or roll back with 'git rebase --abort'",
                ],
            )

        self._replay_commits()
        self.state.rebase = RebaseState()
        return CommandResult(
            success=True,
            output=f"Successfully rebased and updated refs/heads/{branch_name}.",
        )

    def _replay_commits(self) -> None:
        """Replay remaining rebase commits on top of the current branch tip."""
        rebase = self.state.rebase
        branch = self.state.branches[rebase.original_branch]
        parent_sha = branch.commit_sha
        for old_sha in rebase.remaining_shas:
            old_commit = self.state.commits[old_sha]
            new_commit = Commit(
                sha=self._generate_sha(),
                message=old_commit.message,
                parent_sha=parent_sha,
                files_changed=list(old_commit.files_changed),
            )
            self.state.commits[new_commit.sha] = new_commit
            parent_sha = new_commit.sha
        branch.commit_sha = parent_sha
        rebase.remaining_shas = []

    def rebase_continue(self) -> CommandResult:
        """Continue a rebase after conflicts were resolved and staged."""
        rebase = self.state.rebase
        if rebase.status == RebaseStatus.IDLE:
            return CommandResult(
                success=False,
                message="fatal: no rebase in progress",
            )

        # A conflict is resolved once the user re-stages the file, which
        # replaces the "both modified" unmerged marker.
        unresolved = [
            c.filename
            for c in self.state.staged_changes
            if c.filename in rebase.conflicted_files
            and c.change_type == "both modified"
        ]
        if unresolved:
            return CommandResult(
                success=False,
                message=f"error: unresolved conflict(s): {', '.join(unresolved)}",
                hints=[
                    "Mark conflicts resolved with 'git add <file>'",
                    "Or roll back with 'git rebase --abort'",
                ],
            )

        branch_name = rebase.original_branch
        conflicted = list(rebase.conflicted_files)
        self._replay_commits()
        self.state.staged_changes = [
            c for c in self.state.staged_changes if c.filename not in conflicted
        ]
        self.state.rebase = RebaseState()
        return CommandResult(
            success=True,
            output=f"Successfully rebased and updated refs/heads/{branch_name}.",
        )

    def rebase_abort(self) -> CommandResult:
        """Abort a rebase, rolling back to the recorded anchor."""
        rebase = self.state.rebase
        if rebase.status == RebaseStatus.IDLE:
            return CommandResult(
                success=False,
                message="fatal: no rebase in progress",
            )

        branch = self.state.branches.get(rebase.original_branch or "")
        if branch and rebase.original_sha in self.state.commits:
            branch.commit_sha = rebase.original_sha
            self.state.head = branch.name

        # Drop conflict markers staged by the rebase
        self.state.staged_changes = [
            c for c in self.state.staged_changes
            if not (c.filename in rebase.conflicted_files and c.change_type == "both modified")
        ]

        self.state.rebase = RebaseState()
        return CommandResult(
            success=True,
            output="Rebase aborted. You are back to where you started.",
        )

    # Reset operations

    def reset(self, filename: Optional[str] = None, hard: bool = False) -> CommandResult:
        """Reset staging area (and optionally working changes)."""
        if hard:
            self.state.staged_changes = []
            self.state.working_changes = []
            return CommandResult(
                success=True,
                output="HEAD is now at " + self.state.branches[self.state.head].commit_sha[:7],
            )

        if filename:
            return self.unstage_file(filename)

        for change in list(self.state.staged_changes):
            self.unstage_file(change.filename)
        return CommandResult(success=True, output="Unstaged changes after reset")

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
            rebasing=self.state.rebase.status != RebaseStatus.IDLE,
            rebase_conflicts=list(self.state.rebase.conflicted_files)
            if self.state.rebase.status == RebaseStatus.CONFLICT
            else [],
        )

    def get_status_output(self) -> CommandResult:
        """Get formatted status output."""
        status = self.status()
        lines = [f"On branch {status.current_branch}"]

        if status.rebasing:
            if status.rebase_conflicts:
                lines.append("You are currently rebasing (conflicts detected).")
                lines.append('  (resolve conflicts and run "git rebase --continue")')
                lines.append('  (use "git rebase --abort" to roll back)')
            else:
                lines.append("You are currently rebasing.")

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

        unmerged = [c for c in status.staged if c.change_type == "both modified"]
        regular_staged = [c for c in status.staged if c.change_type != "both modified"]

        if unmerged:
            lines.append("")
            lines.append("Unmerged paths:")
            lines.append('  (use "git add <file>..." to mark resolution)')
            for change in unmerged:
                lines.append(f"        both modified:   {change.filename}")

        if regular_staged:
            lines.append("")
            lines.append("Changes to be committed:")
            lines.append('  (use "git restore --staged <file>..." to unstage)')
            for change in regular_staged:
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

    # Consistency invariants

    def check_invariants(self) -> list[str]:
        """Check repository consistency invariants.

        Returns a list of human-readable violations (empty means consistent).
        See docs/state-machine.md for the invariant definitions.
        """
        violations = []
        state = self.state

        # INV-1: references are closed under commits
        if state.head not in state.branches:
            violations.append(f"HEAD points to missing branch '{state.head}'")
        for name, branch in state.branches.items():
            if branch.commit_sha not in state.commits:
                violations.append(
                    f"branch '{name}' points to missing commit {branch.commit_sha}"
                )
        for name, branch in state.remote_branches.items():
            if branch.commit_sha not in state.commits:
                violations.append(
                    f"remote branch '{name}' points to missing commit {branch.commit_sha}"
                )

        # INV-2: commit objects reference existing parents
        for sha, commit in state.commits.items():
            if commit.parent_sha is not None and commit.parent_sha not in state.commits:
                violations.append(f"commit {sha} has missing parent {commit.parent_sha}")
            if (
                commit.merge_parent_sha is not None
                and commit.merge_parent_sha not in state.commits
            ):
                violations.append(
                    f"commit {sha} has missing merge parent {commit.merge_parent_sha}"
                )

        # INV-3: staging area and working tree have unique filenames
        staged_names = [c.filename for c in state.staged_changes]
        if len(staged_names) != len(set(staged_names)):
            violations.append("staged changes contain duplicate filenames")
        if len(state.working_changes) != len(set(state.working_changes)):
            violations.append("working changes contain duplicate filenames")

        # INV-4: open PRs reference existing branches
        for pr in state.pull_requests.values():
            if pr.status.value == "open":
                for ref in (pr.source_branch, pr.target_branch):
                    if ref not in state.branches:
                        violations.append(
                            f"open PR #{pr.number} references missing branch '{ref}'"
                        )

        # INV-5: an active rebase has a valid rollback anchor
        rebase = state.rebase
        if rebase.status != RebaseStatus.IDLE and (
                rebase.original_branch not in state.branches
                or rebase.original_sha not in state.commits
        ):
            violations.append("rebase state has an invalid rollback anchor")

        return violations

    def restore_consistency(self) -> list[str]:
        """Repair invariant violations, returning a list of actions taken.

        After this method runs, check_invariants() is guaranteed to pass, so
        the repository always returns to a consistent state after errors.
        """
        actions = []
        state = self.state

        # INV-5: a valid in-progress rebase must be preserved; only a broken
        # one (missing anchor objects) gets rolled back/cleared.
        rebase = state.rebase
        if rebase.status != RebaseStatus.IDLE:
            anchor_ok = (
                rebase.original_branch in state.branches
                and rebase.original_sha in state.commits
            )
            if not anchor_ok:
                state.rebase = RebaseState()
                actions.append("cleared broken rebase state")

        # INV-2: re-root commits whose parents no longer exist
        for commit in state.commits.values():
            if commit.parent_sha is not None and commit.parent_sha not in state.commits:
                commit.parent_sha = None
                actions.append(f"re-rooted commit {commit.sha} with missing parent")
            if (
                commit.merge_parent_sha is not None
                and commit.merge_parent_sha not in state.commits
            ):
                commit.merge_parent_sha = None
                actions.append(f"cleared missing merge parent of commit {commit.sha}")

        # INV-1: repoint dangling branches to a root commit, or drop them
        root_sha = next(
            (sha for sha, c in state.commits.items() if c.parent_sha is None),
            None,
        )
        for branches, label in (
            (state.branches, "branch"),
            (state.remote_branches, "remote branch"),
        ):
            for name in list(branches):
                if branches[name].commit_sha not in state.commits:
                    if root_sha is not None:
                        branches[name].commit_sha = root_sha
                        actions.append(f"repointed dangling {label} '{name}' to root")
                    else:
                        del branches[name]
                        actions.append(f"removed dangling {label} '{name}'")

        if state.head not in state.branches:
            if "main" in state.branches:
                state.head = "main"
            elif state.branches:
                state.head = next(iter(state.branches))
            else:
                self._initialize_repo()
            actions.append(f"restored HEAD to '{state.head}'")

        # INV-3: deduplicate staging area and working tree
        seen: set[str] = set()
        deduped = []
        for change in state.staged_changes:
            if change.filename not in seen:
                seen.add(change.filename)
                deduped.append(change)
        if len(deduped) != len(state.staged_changes):
            state.staged_changes = deduped
            actions.append("removed duplicate staged changes")

        deduped_working = list(dict.fromkeys(state.working_changes))
        if len(deduped_working) != len(state.working_changes):
            state.working_changes = deduped_working
            actions.append("removed duplicate working changes")

        # INV-4: close open PRs whose branches no longer exist
        for pr in state.pull_requests.values():
            if pr.status.value == "open" and (
                pr.source_branch not in state.branches
                or pr.target_branch not in state.branches
            ):
                pr.status = PRStatus.CLOSED
                actions.append(f"closed PR #{pr.number} with missing branch")

        return actions

    def export_state(self) -> dict:
        """Export repository state for saving."""
        return {
            "commits": {
                sha: {
                    "sha": c.sha,
                    "message": c.message,
                    "parent_sha": c.parent_sha,
                    "merge_parent_sha": c.merge_parent_sha,
                    "files_changed": c.files_changed,
                }
                for sha, c in self.state.commits.items()
            },
            "branches": {
                name: {"name": b.name, "commit_sha": b.commit_sha, "upstream": b.upstream}
                for name, b in self.state.branches.items()
            },
            "remote_branches": {
                name: {"name": b.name, "commit_sha": b.commit_sha}
                for name, b in self.state.remote_branches.items()
            },
            "head": self.state.head,
            "staged_changes": [
                {"filename": s.filename, "change_type": s.change_type}
                for s in self.state.staged_changes
            ],
            "working_changes": self.state.working_changes,
            "remote_url": self.state.remote_url,
            "next_pr_number": self.state.next_pr_number,
            "rebase": {
                "status": self.state.rebase.status.value,
                "original_branch": self.state.rebase.original_branch,
                "original_sha": self.state.rebase.original_sha,
                "onto": self.state.rebase.onto,
                "remaining_shas": list(self.state.rebase.remaining_shas),
                "conflicted_files": list(self.state.rebase.conflicted_files),
            },
        }

    def import_state(self, data: dict) -> None:
        """Import repository state."""
        self.state = RepositoryState()

        for sha, commit_data in data.get("commits", {}).items():
            self.state.commits[sha] = Commit(
                sha=commit_data["sha"],
                message=commit_data["message"],
                parent_sha=commit_data.get("parent_sha"),
                merge_parent_sha=commit_data.get("merge_parent_sha"),
                files_changed=commit_data.get("files_changed", []),
            )

        for name, branch_data in data.get("branches", {}).items():
            self.state.branches[name] = Branch(
                name=branch_data["name"],
                commit_sha=branch_data["commit_sha"],
                upstream=branch_data.get("upstream"),
            )

        for name, branch_data in data.get("remote_branches", {}).items():
            self.state.remote_branches[name] = Branch(
                name=branch_data["name"],
                commit_sha=branch_data["commit_sha"],
                is_remote=True,
            )

        self.state.head = data.get("head", "main")
        self.state.remote_url = data.get("remote_url", self.state.remote_url)
        self.state.next_pr_number = data.get("next_pr_number", 1)

        for change_data in data.get("staged_changes", []):
            self.state.staged_changes.append(
                StagedChange(
                    filename=change_data["filename"],
                    change_type=change_data["change_type"],
                )
            )

        self.state.working_changes = data.get("working_changes", [])

        rebase_data = data.get("rebase", {})
        self.state.rebase = RebaseState(
            status=RebaseStatus(rebase_data.get("status", "idle")),
            original_branch=rebase_data.get("original_branch"),
            original_sha=rebase_data.get("original_sha"),
            onto=rebase_data.get("onto"),
            remaining_shas=rebase_data.get("remaining_shas", []),
            conflicted_files=rebase_data.get("conflicted_files", []),
        )

        # Imported state can be corrupt (e.g. HEAD points at a missing
        # branch); always land on a consistent state.
        self.restore_consistency()
