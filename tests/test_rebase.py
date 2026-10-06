"""Rebase state machine: conflicts, continue, abort, and recovery."""

from gitgood.core.github_api import SimulatedGitHub
from gitgood.core.models import RebaseStatus
from gitgood.core.repository import VirtualRepository
from gitgood.parser.executor import CommandExecutor
from gitgood.parser.lexer import CommandLexer


def diverged_repo(shared_file="shared.txt"):
    """main and feature diverge, both having committed the same file."""
    repo = VirtualRepository()
    repo.create_branch("feature")
    repo.checkout("main")
    repo.add_working_change(shared_file)
    repo.add_file(shared_file)
    assert repo.commit("main-side work").success

    repo.checkout("feature")
    repo.add_working_change(shared_file)
    repo.add_file(shared_file)
    assert repo.commit("feature-side work").success
    return repo


class TestRebaseSuccess:
    def test_unknown_upstream_fails(self):
        repo = VirtualRepository()
        result = repo.rebase("ghost")
        assert not result.success
        assert repo.state.rebase.status == RebaseStatus.IDLE

    def test_up_to_date_is_noop(self):
        repo = VirtualRepository()
        repo.create_branch("feature")
        repo.checkout("feature")
        # feature is based on an older main (main is ancestor of nothing new):
        # main has not moved, so there is nothing to do
        result = repo.rebase("main")
        assert result.success
        assert "up to date" in result.output
        assert repo.state.rebase.status == RebaseStatus.IDLE

    def test_fast_forward_rebase(self):
        repo = VirtualRepository()
        repo.create_branch("feature")
        repo.checkout("main")
        repo.add_working_change("m.txt")
        repo.add_file("m.txt")
        repo.commit("main advanced")
        repo.checkout("feature")

        main_sha = repo.state.branches["main"].commit_sha
        result = repo.rebase("main")

        assert result.success
        assert repo.state.branches["feature"].commit_sha == main_sha
        assert repo.state.rebase.status == RebaseStatus.IDLE

    def test_clean_replay(self):
        repo = VirtualRepository()
        repo.create_branch("feature")
        repo.checkout("main")
        repo.add_working_change("m.txt")
        repo.add_file("m.txt")
        repo.commit("main work")
        repo.checkout("feature")
        repo.add_working_change("f.txt")
        repo.add_file("f.txt")
        repo.commit("feature work")

        result = repo.rebase("main")

        assert result.success
        assert repo.state.rebase.status == RebaseStatus.IDLE
        tip = repo.state.commits[repo.state.branches["feature"].commit_sha]
        assert tip.message == "feature work"
        assert tip.parent_sha == repo.state.branches["main"].commit_sha
        assert repo.check_invariants() == []


class TestRebaseConflict:
    def test_conflict_halts_rebase(self):
        repo = diverged_repo()
        original_sha = repo.state.branches["feature"].commit_sha

        result = repo.rebase("main")

        assert not result.success
        assert "CONFLICT" in result.message
        assert repo.state.rebase.status == RebaseStatus.CONFLICT
        assert repo.state.rebase.original_sha == original_sha
        assert repo.state.rebase.original_branch == "feature"
        assert repo.state.branches["feature"].commit_sha == repo.state.branches["main"].commit_sha
        assert repo.check_invariants() == []

    def test_mutating_commands_blocked_during_conflict(self):
        repo = diverged_repo()
        repo.rebase("main")

        assert not repo.checkout("main").success
        assert not repo.commit("sneaky").success
        assert not repo.merge("main").success
        assert not repo.rebase("main").success

        # Status surfaces the conflict
        output = repo.get_status_output().output
        assert "rebasing" in output
        assert "shared.txt" in output

    def test_continue_without_resolution_fails(self):
        repo = diverged_repo()
        repo.rebase("main")

        result = repo.rebase_continue()

        assert not result.success
        assert "unresolved" in result.message
        assert repo.state.rebase.status == RebaseStatus.CONFLICT
        assert repo.check_invariants() == []

    def test_resolve_and_continue(self):
        repo = diverged_repo()
        repo.rebase("main")

        repo.add_file("shared.txt")  # mark resolution
        result = repo.rebase_continue()

        assert result.success
        assert repo.state.rebase.status == RebaseStatus.IDLE
        assert repo.state.staged_changes == []
        tip = repo.state.commits[repo.state.branches["feature"].commit_sha]
        assert tip.message == "feature-side work"
        assert tip.parent_sha == repo.state.branches["main"].commit_sha
        assert repo.check_invariants() == []

    def test_abort_rolls_back_to_anchor(self):
        repo = diverged_repo()
        original_sha = repo.state.branches["feature"].commit_sha

        repo.rebase("main")
        result = repo.rebase_abort()

        assert result.success
        assert repo.state.rebase.status == RebaseStatus.IDLE
        assert repo.state.branches["feature"].commit_sha == original_sha
        assert repo.state.head == "feature"
        assert repo.state.staged_changes == []
        assert repo.check_invariants() == []

    def test_continue_and_abort_when_idle_fail(self):
        repo = VirtualRepository()
        assert not repo.rebase_continue().success
        assert not repo.rebase_abort().success


class TestRebaseExecutor:
    def test_executor_routes_continue_and_abort(self):
        repo = VirtualRepository()
        executor = CommandExecutor(repo, SimulatedGitHub(repo))
        lexer = CommandLexer()

        diverged = diverged_repo()
        repo.state = diverged.state

        conflict = executor.execute(lexer.parse("git rebase main"))
        assert not conflict.success

        assert not executor.execute(lexer.parse("git rebase --continue")).success

        executor.execute(lexer.parse("git add shared.txt"))
        continued = executor.execute(lexer.parse("git rebase --continue"))
        assert continued.success
        assert repo.state.rebase.status == RebaseStatus.IDLE
        assert repo.check_invariants() == []
