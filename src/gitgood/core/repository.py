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
    RebaseState,
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

    def _head_branch(self) -> Optional[Branch]:
        """Get the branch HEAD points to, or None if HEAD is dangling."""
        return self.state.branches.get(self.state.head)

    def get_current_commit(self) -> Commit:
        """Get the current HEAD commit."""
        branch = self._head_branch()
        if branch is None:
            raise KeyError(f"HEAD points to unknown branch '{self.state.head}'")
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
            head_branch = self._head_branch()
            if head_branch is None:
                return CommandResult(
                    success=False,
                    message="fatal: HEAD is detached from any known branch; repository state is inconsistent",
                )
            base_sha = head_branch.commit_sha

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

        if self.state.rebase and name in (
            self.state.rebase.branch,
            self.state.rebase.onto,
        ):
            return CommandResult(
                success=False,
                message=f"error: cannot delete branch '{name}' while a rebase is in progress",
                hints=["Finish with 'git rebase --continue' or undo with 'git rebase --abort'"],
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
        if self.state.rebase:
            return CommandResult(
                success=False,
                message="error: cannot switch branches while a rebase is in progress",
                hints=[
                    "Resolve conflicts and run 'git rebase --continue'",
                    "Or undo the rebase with 'git rebase --abort'",
                ],
            )

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

        # Never leave HEAD dangling: only move HEAD once we know the
        # target branch and its commit both exist.
        if self.state.branches[target].commit_sha not in self.state.commits:
            return CommandResult(
                success=False,
                message=f"error: branch '{target}' points at an unknown commit; repository state is inconsistent",
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
            # Stage all working changes. A file that is already staged
            # (and was modified again) keeps its single staged entry -
            # staging must never create duplicates.
            already_staged = {c.filename for c in self.state.staged_changes}
            for f in self.state.working_changes:
                if f not in already_staged:
                    self.state.staged_changes.append(
                        StagedChange(filename=f, change_type="modified")
                    )
                    already_staged.add(f)
            self.state.working_changes = []
            return CommandResult(success=True, message="")

        # Add specific file
        was_modified = filename in self.state.working_changes
        if was_modified:
            self.state.working_changes.remove(filename)

        # Check if already staged: staging is idempotent per file.
        for change in self.state.staged_changes:
            if change.filename == filename:
                return CommandResult(success=True, message="")

        change_type = "modified" if was_modified else "added"
        self.state.staged_changes.append(
            StagedChange(filename=filename, change_type=change_type)
        )
        return CommandResult(success=True, message="")

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

    def reset(self, filename: Optional[str] = None, hard: bool = False) -> CommandResult:
        """Reset staging area (and optionally working changes)."""
        if hard:
            self.state.staged_changes = []
            self.state.working_changes = []
            if self.state.rebase:
                # Panic rollback: a hard reset during a rebase abandons the
                # rebase and restores the original branch tip.
                rebase = self.state.rebase
                branch = self.state.branches.get(rebase.branch)
                if branch and rebase.original_sha in self.state.commits:
                    branch.commit_sha = rebase.original_sha
                self.state.rebase = None
            head_branch = self._head_branch()
            sha = head_branch.commit_sha if head_branch else "unknown"
            return CommandResult(
                success=True,
                output=f"HEAD is now at {sha}",
            )

        if filename:
            return self.unstage_file(filename)

        # Unstage everything back to the working directory.
        for change in self.state.staged_changes:
            if change.filename not in self.state.working_changes:
                self.state.working_changes.append(change.filename)
        self.state.staged_changes = []
        return CommandResult(success=True, output="Unstaged changes after reset.")

    # Commit operations

    def commit(self, message: str, add_all: bool = False) -> CommandResult:
        """Create a new commit."""
        if self.state.rebase:
            return CommandResult(
                success=False,
                message="error: cannot commit while a rebase is in progress",
                hints=[
                    "Use 'git rebase --continue' after resolving conflicts",
                    "Or use 'git rebase --abort' to return to the original state",
                ],
            )

        head_branch = self._head_branch()
        if head_branch is None:
            return CommandResult(
                success=False,
                message="fatal: HEAD points to an unknown branch; repository state is inconsistent",
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
        parent_sha = head_branch.commit_sha

        new_commit = Commit(
            sha=self._generate_sha(),
            message=message,
            parent_sha=parent_sha,
            files_changed=files,
        )

        self.state.commits[new_commit.sha] = new_commit
        head_branch.commit_sha = new_commit.sha
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
        head_branch = self._head_branch()
        if head_branch is None:
            return CommandResult(
                success=False,
                message="fatal: HEAD points to an unknown branch; repository state is inconsistent",
            )
        current_sha: Optional[str] = head_branch.commit_sha

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

        head_branch = self._head_branch()
        if head_branch and head_branch.commit_sha == sha:
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
        if self.state.rebase:
            return CommandResult(
                success=False,
                message="error: cannot merge while a rebase is in progress",
                hints=["Use 'git rebase --continue' or 'git rebase --abort'"],
            )

        if branch not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"merge: {branch} - not something we can merge",
            )

        target_branch = self._head_branch()
        if target_branch is None:
            return CommandResult(
                success=False,
                message="fatal: HEAD points to an unknown branch; repository state is inconsistent",
            )

        source_branch = self.state.branches[branch]

        if branch == self.state.head or self._is_ancestor(
            source_branch.commit_sha, target_branch.commit_sha
        ):
            return CommandResult(
                success=True,
                output="Already up to date.",
            )

        # Simple simulation: just update the commit pointer
        source_commit = self.state.commits[source_branch.commit_sha]

        if no_ff or True:  # Always create merge commit for learning purposes
            merge_commit = Commit(
                sha=self._generate_sha(),
                message=f"Merge branch '{branch}' into {self.state.head}",
                parent_sha=target_branch.commit_sha,
                parent2_sha=source_branch.commit_sha,
                files_changed=source_commit.files_changed,
            )
            self.state.commits[merge_commit.sha] = merge_commit
            target_branch.commit_sha = merge_commit.sha

        return CommandResult(
            success=True,
            output=f"Merge made by the 'ort' strategy.\n {len(source_commit.files_changed)} file(s) changed",
        )

    # Rebase operations

    def _is_ancestor(self, ancestor_sha: Optional[str], descendant_sha: Optional[str]) -> bool:
        """True if ancestor_sha is reachable from descendant_sha (both parents)."""
        if not ancestor_sha or not descendant_sha:
            return False
        queue = [descendant_sha]
        seen: set[str] = set()
        while queue:
            sha = queue.pop()
            if sha == ancestor_sha:
                return True
            if sha in seen:
                continue
            seen.add(sha)
            commit = self.state.commits.get(sha)
            if commit:
                if commit.parent_sha:
                    queue.append(commit.parent_sha)
                if commit.parent2_sha:
                    queue.append(commit.parent2_sha)
        return False

    def _replay_commits(
        self, original_sha: str, onto_tip: str
    ) -> tuple[list[Commit], Optional[str]]:
        """Collect branch-only commits oldest-first and the shared base."""
        replay = []
        sha: Optional[str] = original_sha
        while sha and sha != onto_tip and not self._is_ancestor(sha, onto_tip):
            commit = self.state.commits.get(sha)
            if not commit:
                break
            replay.append(commit)
            sha = commit.parent_sha
        replay.reverse()
        return replay, sha

    def rebase(self, onto: str) -> CommandResult:
        """Rebase the current branch on top of another branch."""
        if self.state.rebase:
            return CommandResult(
                success=False,
                message="interactive rebase in progress",
                hints=[
                    "git rebase --continue",
                    "git rebase --abort",
                ],
            )

        if onto not in self.state.branches:
            return CommandResult(
                success=False,
                message=f"fatal: invalid upstream '{onto}'",
                hints=[f"Available branches: {', '.join(sorted(self.state.branches))}"],
            )

        head_branch = self._head_branch()
        if head_branch is None:
            return CommandResult(
                success=False,
                message="fatal: HEAD points to an unknown branch; repository state is inconsistent",
            )

        original_sha = head_branch.commit_sha
        onto_tip = self.state.branches[onto].commit_sha
        replay, _base = self._replay_commits(original_sha, onto_tip)

        if not replay:
            if original_sha != onto_tip and self._is_ancestor(
                original_sha, onto_tip
            ):
                # Fast-forward: current branch had no own commits.
                head_branch.commit_sha = onto_tip
                return CommandResult(
                    success=True,
                    output=f"Successfully rebased and updated refs/heads/{self.state.head}.",
                )
            return CommandResult(
                success=True,
                output=f"Current branch {self.state.head} is up to date.",
            )

        onto_commits, _ = self._replay_commits(onto_tip, original_sha)
        onto_files = {f for commit in onto_commits for f in commit.files_changed}
        branch_files = {f for commit in replay for f in commit.files_changed}
        conflict_files = sorted(onto_files & branch_files)

        self.state.rebase = RebaseState(
            branch=self.state.head,
            onto=onto,
            original_sha=original_sha,
            conflicted_files=conflict_files,
        )

        if conflict_files:
            for filename in conflict_files:
                if filename not in self.state.working_changes:
                    self.state.working_changes.append(filename)
            file_list = " ".join(conflict_files)
            return CommandResult(
                success=False,
                message=(
                    f"CONFLICT (content): Merge conflict in {file_list}\n"
                    f"error: could not apply onto '{onto}'. Resolve all conflicts manually."
                ),
                hints=[
                    f"Fix the conflict in: {file_list}",
                    "Mark resolved files with 'git add <file>', then 'git rebase --continue'",
                    "Give up with 'git rebase --abort' to return to the pre-rebase state",
                ],
            )

        return self._finish_rebase()

    def rebase_continue(self) -> CommandResult:
        """Continue an in-progress rebase after conflicts were resolved."""
        rebase = self.state.rebase
        if not rebase:
            return CommandResult(
                success=False,
                message="fatal: no rebase in progress",
            )

        if rebase.conflicted_files:
            staged_files = {c.filename for c in self.state.staged_changes}
            unresolved = [
                f
                for f in rebase.conflicted_files
                if f in self.state.working_changes and f not in staged_files
            ]
            if unresolved:
                return CommandResult(
                    success=False,
                    message=(
                        "error: could not continue because of unmerged files.\n"
                        f"Unmerged paths: {', '.join(unresolved)}"
                    ),
                    hints=[
                        "Resolve the conflicts, then run 'git add <file>'",
                        "Then run 'git rebase --continue'",
                        "Or run 'git rebase --abort' to return to the pre-rebase state",
                    ],
                )

        return self._finish_rebase()

    def rebase_abort(self) -> CommandResult:
        """Abort an in-progress rebase and roll back to the original state."""
        rebase = self.state.rebase
        if not rebase:
            return CommandResult(
                success=False,
                message="fatal: no rebase in progress",
            )

        # Restore the branch pointer recorded at rebase start...
        branch = self.state.branches.get(rebase.branch)
        if branch and rebase.original_sha in self.state.commits:
            branch.commit_sha = rebase.original_sha
        # ...HEAD, the working directory and the index.
        if rebase.branch in self.state.branches:
            self.state.head = rebase.branch
        self.state.working_changes = [
            f for f in self.state.working_changes if f not in rebase.conflicted_files
        ]
        self.state.staged_changes = [
            c
            for c in self.state.staged_changes
            if c.filename not in rebase.conflicted_files
        ]
        self.state.rebase = None

        return CommandResult(
            success=True,
            output=f"Rebase aborted, {rebase.branch} reset to {rebase.original_sha}.",
        )

    def _finish_rebase(self) -> CommandResult:
        """Replay captured commits on top of the target and finish the rebase."""
        rebase = self.state.rebase
        assert rebase is not None

        onto_tip = self.state.branches[rebase.onto].commit_sha
        replay, _base = self._replay_commits(rebase.original_sha, onto_tip)

        parent_sha: Optional[str] = onto_tip
        new_count = 0
        for original in replay:
            new_commit = Commit(
                sha=self._generate_sha(),
                message=original.message,
                parent_sha=parent_sha,
                files_changed=list(original.files_changed),
            )
            self.state.commits[new_commit.sha] = new_commit
            parent_sha = new_commit.sha
            new_count += 1

        branch = self.state.branches.get(rebase.branch)
        if branch is None:
            # Branch vanished mid-rebase: nothing to update; rebase ends.
            self.state.rebase = None
            return CommandResult(
                success=False,
                message="error: rebased branch no longer exists; rebase abandoned",
            )

        branch.commit_sha = parent_sha
        self.state.head = rebase.branch
        # Only the staged conflict resolutions are consumed by the replayed
        # commits; unrelated staged/working changes are left untouched.
        resolved_files = set(rebase.conflicted_files)
        self.state.staged_changes = [
            change
            for change in self.state.staged_changes
            if change.filename not in resolved_files
        ]
        self.state.working_changes = [
            filename
            for filename in self.state.working_changes
            if filename not in resolved_files
        ]
        self.state.rebase = None

        return CommandResult(
            success=True,
            output=(
                f"Successfully rebased and updated refs/heads/{rebase.branch}. "
                f"({new_count} commit(s) replayed)"
            ),
        )

    # Status

    def status(self) -> RepositoryStatus:
        """Get repository status."""
        current_branch = self._head_branch()
        upstream = current_branch.upstream if current_branch else None

        ahead = 0
        behind = 0
        if current_branch and upstream and upstream in self.state.remote_branches:
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

    def check_invariant(self) -> list[str]:
        """
        Verify the repository invariant:

        1. HEAD always names an existing branch whose commit exists.
        2. Every local/remote branch points at an existing commit.
        3. Every commit parent exists (or is None).
        4. The index has no duplicate filenames.
        5. The working directory lists each changed file at most once.
        6. Every configured upstream names an existing remote branch.
        7. A rebase, if in progress, references existing branches/commits
           and every conflicted file is tracked in the index or worktree.

        Returns a list of human-readable violations (empty == consistent).
        """
        violations: list[str] = []

        head_branch = self._head_branch()
        if head_branch is None:
            violations.append(f"HEAD points to missing branch '{self.state.head}'")
        elif head_branch.commit_sha not in self.state.commits:
            violations.append(
                f"branch '{self.state.head}' points to missing commit {head_branch.commit_sha}"
            )

        for name, branch in self.state.branches.items():
            if branch.commit_sha not in self.state.commits:
                violations.append(
                    f"branch '{name}' points to missing commit {branch.commit_sha}"
                )
            if branch.upstream and branch.upstream not in self.state.remote_branches:
                violations.append(
                    f"branch '{name}' tracks missing upstream '{branch.upstream}'"
                )

        for name, branch in self.state.remote_branches.items():
            if branch.commit_sha not in self.state.commits:
                violations.append(
                    f"remote branch '{name}' points to missing commit {branch.commit_sha}"
                )

        for sha, commit in self.state.commits.items():
            if commit.parent_sha is not None and commit.parent_sha not in self.state.commits:
                violations.append(
                    f"commit {sha} has missing parent {commit.parent_sha}"
                )
            if commit.parent2_sha is not None and commit.parent2_sha not in self.state.commits:
                violations.append(
                    f"commit {sha} has missing second parent {commit.parent2_sha}"
                )

        staged_names = [c.filename for c in self.state.staged_changes]
        if len(staged_names) != len(set(staged_names)):
            duplicates = sorted({n for n in staged_names if staged_names.count(n) > 1})
            violations.append(f"duplicate staged entries: {', '.join(duplicates)}")

        if len(self.state.working_changes) != len(set(self.state.working_changes)):
            violations.append("duplicate entries in working directory changes")

        rebase = self.state.rebase
        if rebase is not None:
            if rebase.branch not in self.state.branches:
                violations.append(f"rebase references missing branch '{rebase.branch}'")
            if rebase.onto not in self.state.branches:
                violations.append(f"rebase references missing upstream '{rebase.onto}'")
            if rebase.original_sha not in self.state.commits:
                violations.append(
                    f"rebase saved unknown commit {rebase.original_sha}"
                )
            tracked = set(staged_names) | set(self.state.working_changes)
            orphan = [f for f in rebase.conflicted_files if f not in tracked]
            if orphan:
                violations.append(
                    f"rebase conflicts not tracked in index/worktree: {', '.join(orphan)}"
                )

        return violations

    def recover(self) -> list[str]:
        """
        Repair the state so check_invariant() passes after any failure.

        This is the universal rollback used by the REPL after an unexpected
        error and by import_state(): de-duplicate the index/worktree, drop
        dangling references, finish or abandon an un-fixable rebase, and
        repoint HEAD at a valid branch.
        """
        repairs: list[str] = []

        unique_working: list[str] = []
        for filename in self.state.working_changes:
            if filename not in unique_working:
                unique_working.append(filename)
        if len(unique_working) != len(self.state.working_changes):
            repairs.append("removed duplicate working-directory entries")
        self.state.working_changes = unique_working

        unique_staged: list[StagedChange] = []
        seen: set[str] = set()
        for change in self.state.staged_changes:
            if change.filename not in seen:
                unique_staged.append(change)
                seen.add(change.filename)
        if len(unique_staged) != len(self.state.staged_changes):
            repairs.append("removed duplicate staged entries")
        self.state.staged_changes = unique_staged

        for name, branch in self.state.branches.items():
            if branch.upstream and branch.upstream not in self.state.remote_branches:
                branch.upstream = None
                repairs.append(f"cleared dangling upstream on branch '{name}'")

        # A broken rebase cannot be continued: abort it if possible,
        # otherwise drop it together with its conflict markers.
        rebase = self.state.rebase
        if rebase is not None:
            salvageable = (
                rebase.branch in self.state.branches
                and rebase.original_sha in self.state.commits
                and rebase.onto in self.state.branches
            )
            if salvageable:
                self.state.branches[rebase.branch].commit_sha = rebase.original_sha
                self.state.head = rebase.branch
                repairs.append(f"aborted rebase on '{rebase.branch}'")
            else:
                repairs.append("dropped un-salvageable rebase state")
            self.state.working_changes = [
                f for f in self.state.working_changes if f not in rebase.conflicted_files
            ]
            self.state.staged_changes = [
                c
                for c in self.state.staged_changes
                if c.filename not in rebase.conflicted_files
            ]
            self.state.rebase = None

        # Drop refs pointing at vanished commits. A local branch whose tip
        # no longer exists is unrecoverable (its history is gone), so it is
        # removed unless HEAD is attached to it (handled below).
        for name in list(self.state.remote_branches):
            if self.state.remote_branches[name].commit_sha not in self.state.commits:
                del self.state.remote_branches[name]
                repairs.append(f"removed dangling remote branch '{name}'")

        for name in list(self.state.branches):
            if name == self.state.head:
                continue
            if self.state.branches[name].commit_sha not in self.state.commits:
                del self.state.branches[name]
                repairs.append(f"removed branch '{name}' pointing at a missing commit")

        if self._head_branch() is None:
            if "main" in self.state.branches:
                self.state.head = "main"
            elif self.state.branches:
                self.state.head = min(self.state.branches)
            else:
                self._initialize_repo()
            repairs.append(f"repointed HEAD to '{self.state.head}'")

        head_branch = self._head_branch()
        if head_branch is not None and head_branch.commit_sha not in self.state.commits:
            # Resurrect a safe anchor: prefer the initial commit.
            fallback = next(
                (c.sha for c in self.state.commits.values() if c.parent_sha is None),
                next(iter(self.state.commits), None),
            )
            if fallback is None:
                self._initialize_repo()
                repairs.append("re-initialized empty repository")
            else:
                head_branch.commit_sha = fallback
                repairs.append(f"repointed '{self.state.head}' at valid commit {fallback}")

        return repairs

    def export_state(self) -> dict:
        """Export repository state for saving."""
        return {
            "commits": {
                sha: {
                    "sha": c.sha,
                    "message": c.message,
                    "parent_sha": c.parent_sha,
                    "parent2_sha": c.parent2_sha,
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
                parent2_sha=commit_data.get("parent2_sha"),
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

        # Never start from an inconsistent state (dangling HEAD, duplicate
        # index entries, ...); repair instead of crashing later.
        self.recover()
