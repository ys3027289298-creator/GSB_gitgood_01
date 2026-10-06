"""Staging-area / working-tree consistency and checkout atomicity tests."""

from gitgood.core.repository import VirtualRepository


def make_repo() -> VirtualRepository:
    return VirtualRepository()


class TestStagingConsistency:
    def test_stage_all_is_idempotent(self):
        repo = make_repo()
        repo.add_working_change("a.txt")
        repo.add_file("a.txt")
        # File modified again after staging, then stage everything
        repo.add_working_change("a.txt")
        repo.add_file(".")

        staged = [c.filename for c in repo.state.staged_changes]
        assert staged == ["a.txt"]
        assert repo.state.working_changes == []
        assert repo.check_invariants() == []

    def test_restage_replaces_entry(self):
        repo = make_repo()
        repo.add_working_change("a.txt")
        repo.add_file("a.txt")
        repo.add_file("a.txt")
        repo.add_file("-A")

        staged = [c.filename for c in repo.state.staged_changes]
        assert staged == ["a.txt"]

    def test_unstage_does_not_duplicate_working_changes(self):
        repo = make_repo()
        repo.add_working_change("a.txt")
        repo.add_file("a.txt")
        repo.unstage_file("a.txt")

        assert repo.state.working_changes == ["a.txt"]
        # Unstaging again fails gracefully and does not duplicate
        result = repo.unstage_file("a.txt")
        assert not result.success
        assert repo.state.working_changes == ["a.txt"]

    def test_commit_clears_staging(self):
        repo = make_repo()
        repo.add_working_change("a.txt")
        repo.add_file("a.txt")
        result = repo.commit("add a")

        assert result.success
        assert repo.state.staged_changes == []
        assert repo.state.working_changes == []
        assert repo.check_invariants() == []

    def test_reset_file_and_hard(self):
        repo = make_repo()
        repo.add_working_change("a.txt")
        repo.add_file("a.txt")
        repo.reset(filename="a.txt")
        assert repo.state.staged_changes == []
        assert repo.state.working_changes == ["a.txt"]

        repo.add_file("a.txt")
        repo.reset(hard=True)
        assert repo.state.staged_changes == []
        assert repo.state.working_changes == []


class TestCheckoutAtomicity:
    def snapshot(self, repo):
        state = repo.state
        return (
            state.head,
            {k: v.commit_sha for k, v in state.branches.items()},
            list(state.staged_changes),
            list(state.working_changes),
            set(state.commits),
        )

    def test_checkout_missing_branch_changes_nothing(self):
        repo = make_repo()
        repo.add_working_change("wip.txt")
        before = self.snapshot(repo)

        result = repo.checkout("does-not-exist")

        assert not result.success
        assert result.hints  # suggests git checkout -b
        assert self.snapshot(repo) == before
        assert repo.check_invariants() == []

    def test_checkout_b_existing_branch_fails_atomically(self):
        repo = make_repo()
        repo.create_branch("feature")
        before = self.snapshot(repo)

        result = repo.checkout("feature", create=True)

        assert not result.success
        assert self.snapshot(repo) == before

    def test_checkout_existing_branch_succeeds(self):
        repo = make_repo()
        repo.create_branch("feature")
        result = repo.checkout("feature")
        assert result.success
        assert repo.state.head == "feature"

    def test_status_survives_failed_checkout(self):
        repo = make_repo()
        repo.checkout("ghost")
        status = repo.status()
        assert status.current_branch == "main"
        output = repo.get_status_output()
        assert output.success

    def test_import_with_dangling_head_is_healed(self):
        """Regression: corrupt imported state must not crash status/log."""
        repo = make_repo()
        data = repo.export_state()
        data["head"] = "ghost-branch"

        repo.import_state(data)

        assert repo.check_invariants() == []
        assert repo.state.head in repo.state.branches
        # These used to raise KeyError on a dangling HEAD
        assert repo.get_status_output().success
        assert repo.get_log().success
