"""The state invariant: staging consistency, recovery, fuzz sequences."""

import random

from gitgood.core.models import RebaseState, StagedChange


def test_add_all_never_duplicates_staged_entries(session):
    session.repo.add_working_change("a.txt")
    session.run("git add a.txt")
    session.repo.add_working_change("a.txt")  # re-modified after staging

    session.run("git add .")

    staged = [c.filename for c in session.repo.state.staged_changes]
    assert staged == ["a.txt"]
    assert session.repo.state.working_changes == []


def test_staging_is_idempotent_per_file(session):
    session.repo.add_working_change("a.txt")
    session.run("git add a.txt")
    session.run("git add a.txt")

    staged = [c.filename for c in session.repo.state.staged_changes]
    assert staged == ["a.txt"]


def test_unstage_does_not_duplicate_working_entries(session):
    session.repo.add_working_change("a.txt")
    session.run("git add a.txt")
    session.repo.add_working_change("a.txt")

    session.run("git reset a.txt")

    assert session.repo.state.staged_changes == []
    assert session.repo.state.working_changes == ["a.txt"]


def test_reset_unstages_everything(session):
    session.repo.add_working_change("a.txt")
    session.repo.add_working_change("b.txt")
    session.run("git add .")

    result = session.run("git reset")

    assert result.success
    assert session.repo.state.staged_changes == []
    assert sorted(session.repo.state.working_changes) == ["a.txt", "b.txt"]


def test_reset_hard_clears_index_and_worktree(session):
    session.repo.add_working_change("a.txt")
    session.run("git add a.txt")
    session.repo.add_working_change("b.txt")

    result = session.run("git reset --hard")

    assert result.success
    assert session.repo.state.staged_changes == []
    assert session.repo.state.working_changes == []


def test_recover_repairs_duplicate_index_entries(session):
    session.repo.state.staged_changes = [
        StagedChange(filename="a.txt", change_type="modified"),
        StagedChange(filename="a.txt", change_type="modified"),
    ]
    session.repo.state.working_changes = ["b.txt", "b.txt"]

    repairs = session.repo.recover()

    assert repairs
    assert session.repo.check_invariant() == []
    assert [c.filename for c in session.repo.state.staged_changes] == ["a.txt"]
    assert session.repo.state.working_changes == ["b.txt"]


def test_recover_aborts_unsalvageable_rebase(session):
    session.repo.state.rebase = RebaseState(
        branch="gone",
        onto="also-gone",
        original_sha="zzzzzzz",
        conflicted_files=["c.txt"],
    )
    session.repo.state.working_changes.append("c.txt")

    repairs = session.repo.recover()

    assert any("rebase" in repair for repair in repairs)
    assert session.repo.state.rebase is None
    assert "c.txt" not in session.repo.state.working_changes
    assert session.repo.check_invariant() == []


def test_recover_clears_dangling_upstream(session):
    session.run("git checkout -b feature")
    session.run("git push -u origin feature")
    del session.repo.state.remote_branches["origin/feature"]

    session.repo.recover()

    assert session.repo.state.branches["feature"].upstream is None
    assert session.repo.check_invariant() == []


def test_fuzz_random_command_sequences_keep_invariant(session):
    """Random legal/illegal command mixes must never break the invariant."""
    rng = random.Random(20261007)
    commands = [
        "git status",
        "git add a.txt",
        "git add .",
        "git add missing.txt",
        "git commit -m work",
        "git commit -a -m auto",
        "git commit",
        "git branch",
        "git branch b1",
        "git branch -d b1",
        "git branch -D main",
        "git checkout b1",
        "git checkout -b b2",
        "git checkout nope",
        "git switch b2",
        "git merge b1",
        "git merge --no-ff b2",
        "git merge ghost",
        "git rebase main",
        "git rebase b1",
        "git rebase --continue",
        "git rebase --abort",
        "git reset",
        "git reset --hard",
        "git reset a.txt",
        "git log --oneline",
        "git push -u origin main",
        "git pull",
        "git fetch",
        "git diff --staged",
        "git remote -v",
        "gh pr list",
        "gh pr create --title T --body B",
        "gh pr merge 1",
        "gh pr close 1",
        "git frobnicate",
    ]
    files = ["a.txt", "b.txt", "c.txt"]

    for step in range(300):
        if rng.random() < 0.35:
            session.repo.add_working_change(rng.choice(files))
        command = rng.choice(commands)
        session.run(command)  # GitSession.run asserts the invariant
        assert session.repo.check_invariant() == [], (
            f"invariant broken at step {step} by {command!r}: "
            f"{session.repo.check_invariant()}"
        )


def test_fuzz_recovery_after_random_corruption(session):
    """Inject corruption, recover, and require a consistent state."""
    rng = random.Random(7)

    for _ in range(50):
        corruption = rng.choice(["head", "staged", "upstream", "rebase"])
        if corruption == "head":
            session.repo.state.head = rng.choice(["ghost", "main", ""])
        elif corruption == "staged":
            session.repo.state.staged_changes.append(
                StagedChange(filename="dup.txt", change_type="modified")
            )
            session.repo.state.staged_changes.append(
                StagedChange(filename="dup.txt", change_type="added")
            )
        elif corruption == "upstream":
            session.repo.state.branches["main"].upstream = "origin/nowhere"
        else:
            session.repo.state.rebase = RebaseState(
                branch="main",
                onto="missing",
                original_sha="zzzzzzz",
                conflicted_files=["x.txt"],
            )

        session.repo.recover()
        assert session.repo.check_invariant() == []
