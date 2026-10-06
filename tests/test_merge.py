"""Merge semantics, PR merge atomicity, and failure-recovery tests."""

from gitgood.core.github_api import SimulatedGitHub
from gitgood.core.models import PRStatus
from gitgood.core.repository import VirtualRepository
from gitgood.parser.executor import CommandExecutor
from gitgood.parser.lexer import CommandLexer


def make_executor():
    repo = VirtualRepository()
    github = SimulatedGitHub(repo)
    return repo, github, CommandExecutor(repo, github), CommandLexer()


def commit_on(repo, branch, files, message):
    repo.checkout(branch)
    for filename in files:
        repo.add_working_change(filename)
        repo.add_file(filename)
    result = repo.commit(message)
    assert result.success


class TestMerge:
    def test_missing_branch_fails_atomically(self):
        repo = VirtualRepository()
        main_sha = repo.state.branches["main"].commit_sha
        commits_before = set(repo.state.commits)

        result = repo.merge("ghost")

        assert not result.success
        assert repo.state.head == "main"
        assert repo.state.branches["main"].commit_sha == main_sha
        assert set(repo.state.commits) == commits_before
        assert repo.check_invariants() == []

    def test_fast_forward_when_ahead(self):
        repo = VirtualRepository()
        repo.create_branch("feature")
        commit_on(repo, "feature", ["f.txt"], "feature work")
        repo.checkout("main")
        feature_sha = repo.state.branches["feature"].commit_sha

        result = repo.merge("feature")

        assert result.success
        assert "Fast-forward" in result.output
        assert repo.state.branches["main"].commit_sha == feature_sha

    def test_already_up_to_date(self):
        repo = VirtualRepository()
        result = repo.merge("main")
        assert result.success
        assert "Already up to date" in result.output

        # After a fast-forward, merging again is a no-op
        repo.create_branch("feature")
        commit_on(repo, "feature", ["f.txt"], "work")
        repo.checkout("main")
        repo.merge("feature")
        again = repo.merge("feature")
        assert "Already up to date" in again.output

    def test_no_ff_creates_merge_commit_with_two_parents(self):
        repo = VirtualRepository()
        base_sha = repo.state.branches["main"].commit_sha
        repo.create_branch("feature")
        # Diverge: commit on main and on feature
        commit_on(repo, "main", ["m.txt"], "main work")
        commit_on(repo, "feature", ["f.txt"], "feature work")
        repo.checkout("main")

        result = repo.merge("feature", no_ff=True)
        assert result.success
        assert "Merge made" in result.output

        merge_sha = repo.state.branches["main"].commit_sha
        merge_commit = repo.state.commits[merge_sha]
        assert merge_commit.parent_sha is not None
        assert merge_commit.merge_parent_sha is not None
        assert merge_commit.parent_sha != merge_commit.merge_parent_sha
        assert repo._is_ancestor(base_sha, merge_sha)
        assert repo.check_invariants() == []


class TestPRMergeRecovery:
    def test_pr_merge_failure_keeps_pr_open(self):
        """If the merge cannot proceed (rebase conflict), PR stays OPEN."""
        repo, _, executor, lexer = make_executor()

        def run(command):
            return executor.execute(lexer.parse(command))

        # Create a pushed feature branch and an open PR
        run("git checkout -b feature")
        commit_on(repo, "feature", ["shared.txt"], "feature work")
        run("git push -u origin feature")
        assert run("gh pr create --title T --body B").success

        # Block the merge with an in-progress rebase conflict: diverge main
        repo.checkout("main")
        commit_on(repo, "main", ["shared.txt"], "main work")
        repo.checkout("feature")
        rebase_result = run("git rebase main")
        assert not rebase_result.success  # conflict

        result = run("gh pr merge 1")

        assert not result.success
        assert repo.state.pull_requests[1].status == PRStatus.OPEN
        assert repo.check_invariants() == []

    def test_pr_merge_does_not_move_head(self):
        repo, _, executor, lexer = make_executor()

        def run(command):
            return executor.execute(lexer.parse(command))

        run("git checkout -b feature")
        commit_on(repo, "feature", ["f.txt"], "work")
        run("git push -u origin feature")
        run("gh pr create --title T --body B")

        head_before = repo.state.head
        result = run("gh pr merge 1")

        assert result.success
        assert repo.state.head == head_before  # stays on feature
        assert repo.state.pull_requests[1].status == PRStatus.MERGED
        assert repo.state.branches["main"].commit_sha != (
            repo.state.branches["feature"].commit_sha
        )

    def test_pr_merge_missing_number_fails(self):
        repo, _, executor, lexer = make_executor()
        result = executor.execute(lexer.parse("gh pr merge 99"))
        assert not result.success
        assert repo.check_invariants() == []
