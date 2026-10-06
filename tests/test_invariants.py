"""State invariants hold after every command, and any corrupted state
can always be repaired back to consistency (docs/state-machine.md)."""

import random

from gitgood.core.github_api import SimulatedGitHub
from gitgood.core.models import PRStatus, PullRequest, RebaseStatus
from gitgood.core.repository import VirtualRepository
from gitgood.parser.executor import CommandExecutor
from gitgood.parser.lexer import CommandLexer, ParseError

COMMANDS = [
    "git status",
    "git log --oneline",
    "git branch",
    "git branch b1",
    "git branch -d b1",
    "git branch -D main",
    "git checkout main",
    "git checkout ghost",
    "git checkout -b f1",
    "git checkout -b f2",
    "git switch f1",
    "git add .",
    "git add x.txt",
    "git reset",
    "git reset x.txt",
    "git reset --hard",
    "git commit -m work",
    "git commit -am more",
    "git merge f1",
    "git merge f2",
    "git merge ghost",
    "git merge main",
    "git rebase main",
    "git rebase f1",
    "git rebase --continue",
    "git rebase --abort",
    "git push -u origin f1",
    "git push",
    "git pull",
    "gh pr create --title T --body B",
    "gh pr list",
    "gh pr merge 1",
    "gh pr merge 99",
    "gh pr close 1",
]


def test_random_command_sequences_stay_consistent():
    rng = random.Random(1234)
    lexer = CommandLexer()

    for _ in range(300):
        repo = VirtualRepository()
        executor = CommandExecutor(repo, SimulatedGitHub(repo))
        for _ in range(rng.randint(1, 20)):
            command = rng.choice(COMMANDS)
            try:
                result = executor.execute(lexer.parse(command))
            except ParseError:
                continue
            # Commands succeed or fail, but the executor must report it
            assert hasattr(result, "success")
            # No sequence may leave the repository inconsistent
            assert repo.check_invariants() == []


def test_executor_never_raises():
    repo = VirtualRepository()
    executor = CommandExecutor(repo, SimulatedGitHub(repo))
    lexer = CommandLexer()
    for command in COMMANDS:
        try:
            parsed = lexer.parse(command)
        except ParseError:
            continue
        result = executor.execute(parsed)  # must not raise
        assert result is not None


class TestRestoreConsistency:
    def test_dangling_head_restored(self):
        repo = VirtualRepository()
        repo.state.head = "missing"

        actions = repo.restore_consistency()

        assert repo.check_invariants() == []
        assert repo.state.head in repo.state.branches
        assert any("HEAD" in a for a in actions)
        # Read paths must work after recovery
        assert repo.get_status_output().success
        assert repo.get_log().success

    def test_dangling_branch_repointed(self):
        repo = VirtualRepository()
        repo.state.branches["main"].commit_sha = "deadbeef"

        actions = repo.restore_consistency()

        assert repo.check_invariants() == []
        assert (
            repo.state.branches["main"].commit_sha
            in repo.state.commits
        )
        assert actions

    def test_dangling_parents_rerooted(self):
        repo = VirtualRepository()
        commit = next(iter(repo.state.commits.values()))
        commit.parent_sha = "ghost12"

        repo.restore_consistency()

        assert repo.check_invariants() == []
        assert commit.parent_sha is None

    def test_duplicate_index_entries_deduped(self):
        repo = VirtualRepository()
        repo.add_working_change("a.txt")
        repo.add_file("a.txt")
        # Inject a duplicate directly
        repo.state.working_changes.append("a.txt")
        repo.state.working_changes.append("a.txt")

        repo.restore_consistency()

        assert repo.check_invariants() == []
        assert repo.state.working_changes == ["a.txt"]

    def test_open_pr_with_missing_branch_is_closed(self):
        repo = VirtualRepository()
        repo.state.pull_requests[7] = PullRequest(
            number=7,
            title="t",
            body="",
            source_branch="gone",
            target_branch="main",
            status=PRStatus.OPEN,
        )
        assert repo.check_invariants() != []

        repo.restore_consistency()

        assert repo.check_invariants() == []
        assert repo.state.pull_requests[7].status == PRStatus.CLOSED

    def test_broken_rebase_state_cleared(self):
        repo = VirtualRepository()
        repo.state.rebase.original_branch = "gone"
        repo.state.rebase.original_sha = "ghostsha"
        repo.state.rebase.status = RebaseStatus.CONFLICT

        repo.restore_consistency()

        assert repo.check_invariants() == []
        assert repo.state.rebase.status == RebaseStatus.IDLE

    def test_valid_conflict_rebase_preserved_by_restore(self):
        repo = VirtualRepository()
        repo.create_branch("feature")
        repo.checkout("main")
        repo.add_working_change("s.txt")
        repo.add_file("s.txt")
        repo.commit("m")
        repo.checkout("feature")
        repo.add_working_change("s.txt")
        repo.add_file("s.txt")
        repo.commit("f")
        repo.rebase("main")
        assert repo.state.rebase.status == RebaseStatus.CONFLICT

        actions = repo.restore_consistency()

        assert actions == []
        assert repo.state.rebase.status == RebaseStatus.CONFLICT
        assert repo.check_invariants() == []

    def test_export_import_roundtrip_keeps_invariants(self):
        repo = VirtualRepository()
        repo.create_branch("feature")
        repo.checkout("feature")
        repo.add_working_change("s.txt")
        repo.add_file("s.txt")
        repo.commit("work")
        repo.push(set_upstream=True)

        data = repo.export_state()
        clone = VirtualRepository()
        clone.import_state(data)

        assert clone.check_invariants() == []
        assert clone.state.head == "feature"
        assert "origin/feature" in clone.state.remote_branches
