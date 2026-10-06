"""Checkout failure handling and crash recovery."""


def test_checkout_unknown_branch_fails_without_crash(session):
    result = session.run("git checkout nope")

    assert not result.success
    assert "did not match any branch" in result.message
    assert result.hints  # tells learner how to recover
    assert session.repo.state.head == "main"


def test_switch_unknown_branch_fails_without_crash(session):
    result = session.run("git switch nope")

    assert not result.success
    assert "did not match any branch" in result.message
    assert session.repo.state.head == "main"



def test_checkout_existing_branch_name_with_b_fails(session):
    result = session.run("git checkout -b main")

    assert not result.success
    assert "already exists" in result.message
    assert session.repo.state.head == "main"


def test_checkout_unknown_after_branch_work_still_works(session):
    session.run("git checkout -b feature")
    session.commit_file("a.txt", "feature work")

    failed = session.run("git checkout main-typo")
    assert not failed.success

    recovered = session.run("git checkout main")
    assert recovered.success
    assert recovered.output == "Switched to branch 'main'"


def test_dangling_head_is_repaired_and_commands_work(session):
    # Simulate a corrupted/imported state: HEAD names a missing branch.
    session.repo.state.head = "ghost"

    repairs = session.repo.recover()

    assert session.repo.state.head == "main"
    assert any("HEAD" in repair for repair in repairs)
    assert session.repo.check_invariant() == []
    assert session.run("git status").success
    assert session.run("git checkout -b fresh").success
    assert session.run("git log --oneline").success


def test_checkout_does_not_move_head_when_target_commit_missing(session):
    session.run("git branch broken")
    session.repo.state.branches["broken"].commit_sha = "zzzzzzz"

    # State is deliberately corrupted; run the command without the
    # fixture's post-command invariant assertion.
    parsed = session.lexer.parse("git checkout broken")
    result = session.executor.execute(parsed)

    assert not result.success
    assert "inconsistent" in result.message
    assert session.repo.state.head == "main"
    assert session.repo.check_invariant() == ["branch 'broken' points to missing commit zzzzzzz"]
    # And recovery returns to a fully consistent, usable state.
    session.repo.recover()
    assert session.repo.check_invariant() == []
    assert session.run("git checkout main").success


def test_checkout_blocked_during_rebase_then_abort_recovers(session):
    session.run("git checkout -b feature")
    session.commit_file("shared.txt", "feature change")
    session.run("git checkout main")
    session.commit_file("shared.txt", "main change")
    session.run("git checkout feature")
    session.run("git rebase main")

    blocked = session.run("git checkout main")
    assert not blocked.success

    abort = session.run("git rebase --abort")
    assert abort.success

    checkout = session.run("git checkout main")
    assert checkout.success


def test_imported_state_with_dangling_head_is_repaired(session):
    session.repo.import_state(
        {
            "commits": {},
            "branches": {},
            "head": "missing",
            "staged_changes": [],
            "working_changes": [],
        }
    )

    assert session.repo.state.head in session.repo.state.branches
    assert session.repo.check_invariant() == []
    assert session.run("git status").success
