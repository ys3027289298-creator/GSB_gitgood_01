"""Rebase state machine: conflicts, continue, abort and guards."""


def _diverge(session, filename: str = "shared.txt") -> None:
    """Create feature/main that both changed the same file (conflict)."""
    session.run("git checkout -b feature")
    session.commit_file(filename, "feature change")
    session.run("git checkout main")
    session.commit_file(filename, "main change")
    session.run("git checkout feature")


def test_rebase_unknown_upstream_fails(session):
    session.run("git checkout -b feature")
    result = session.run("git rebase ghost")

    assert not result.success
    assert "invalid upstream" in result.message
    assert session.repo.state.rebase is None


def test_rebase_conflict_enters_rebase_state(session):
    _diverge(session)

    result = session.run("git rebase main")

    assert not result.success
    assert "CONFLICT" in result.message
    rebase = session.repo.state.rebase
    assert rebase is not None
    assert rebase.branch == "feature"
    assert rebase.onto == "main"
    assert rebase.conflicted_files == ["shared.txt"]
    assert "shared.txt" in session.repo.state.working_changes


def test_rebase_cannot_continue_before_resolving(session):
    _diverge(session)
    session.run("git rebase main")

    result = session.run("git rebase --continue")

    assert not result.success
    assert "unmerged" in result.message
    assert session.repo.state.rebase is not None


def test_rebase_resolve_then_continue(session):
    _diverge(session)
    feature_original = session.repo.state.branches["feature"].commit_sha
    main_tip = session.repo.state.branches["main"].commit_sha

    session.run("git rebase main")
    assert session.run("git add shared.txt").success
    result = session.run("git rebase --continue")

    assert result.success
    assert "replayed" in (result.output or "")
    assert session.repo.state.rebase is None
    new_tip = session.repo.state.branches["feature"].commit_sha
    assert new_tip != feature_original
    replayed = session.repo.state.commits[new_tip]
    assert replayed.parent_sha == main_tip
    assert replayed.message == "feature change"
    assert session.repo.state.head == "feature"
    assert session.repo.check_invariant() == []


def test_continue_consumes_only_conflict_resolutions(session):
    _diverge(session)
    session.run("git rebase main")
    # An unrelated staged change exists while the user resolves the conflict.
    session.repo.add_working_change("other.txt")
    session.run("git add other.txt")

    session.run("git add shared.txt")
    assert session.run("git rebase --continue").success

    assert session.repo.state.rebase is None
    staged = [c.filename for c in session.repo.state.staged_changes]
    assert staged == ["other.txt"]
    assert "other.txt" not in session.repo.state.working_changes


def test_rebase_abort_rolls_back_to_original_state(session):
    _diverge(session)
    saved_tip = session.repo.state.branches["feature"].commit_sha

    session.run("git rebase main")
    result = session.run("git rebase --abort")

    assert result.success
    assert session.repo.state.rebase is None
    assert session.repo.state.head == "feature"
    assert session.repo.state.branches["feature"].commit_sha == saved_tip
    assert session.repo.state.working_changes == []
    assert session.repo.state.staged_changes == []


def test_rebase_blocked_commands_during_conflict(session):
    _diverge(session)
    session.run("git rebase main")

    for command in (
        "git checkout main",
        "git switch main",
        "git merge main",
        'git commit -m "x"',
        "git push",
    ):
        result = session.run(command)
        assert not result.success, command
        assert "rebase is in progress" in result.message, command

    assert session.repo.state.head == "feature"
    assert session.run("git rebase --abort").success


def test_cannot_delete_rebase_branches_during_rebase(session):
    _diverge(session)
    session.run("git rebase main")

    result = session.run("git branch -D main")

    assert not result.success
    assert "rebase is in progress" in result.message
    assert "main" in session.repo.state.branches
    assert session.run("git rebase --abort").success


def test_rebase_continue_without_rebase_fails(session):
    result = session.run("git rebase --continue")
    assert not result.success
    assert "no rebase in progress" in result.message


def test_rebase_abort_without_rebase_fails(session):
    result = session.run("git rebase --abort")
    assert not result.success
    assert "no rebase in progress" in result.message


def test_starting_second_rebase_is_guarded(session):
    _diverge(session)
    session.run("git rebase main")

    result = session.run("git rebase main")

    assert not result.success
    assert "in progress" in result.message


def test_non_conflicting_rebase_replays_automatically(session):
    session.run("git checkout -b feature")
    session.commit_file("f.txt", "feature only")
    session.run("git checkout main")
    session.commit_file("m.txt", "main only")
    session.run("git checkout feature")
    main_tip = session.repo.state.branches["main"].commit_sha

    result = session.run("git rebase main")

    assert result.success
    new_tip = session.repo.state.branches["feature"].commit_sha
    assert session.repo.state.commits[new_tip].parent_sha == main_tip
    assert session.repo.state.rebase is None


def test_rebase_fast_forwards_branch_without_own_commits(session):
    session.commit_file("m.txt", "main advances")
    session.run("git branch feature")
    session.run("git checkout feature")
    main_tip = session.repo.state.branches["main"].commit_sha

    result = session.run("git rebase main")

    assert result.success
    assert session.repo.state.branches["feature"].commit_sha == main_tip
    assert session.repo.state.rebase is None


def test_rebase_onto_current_branch_is_up_to_date(session):
    result = session.run("git rebase main")
    assert result.success
    assert "up to date" in (result.output or "")
    assert session.repo.state.rebase is None


def test_reset_hard_during_rebase_aborts_and_restores(session):
    _diverge(session)
    saved_tip = session.repo.state.branches["feature"].commit_sha
    session.run("git rebase main")

    result = session.run("git reset --hard")

    assert result.success
    assert session.repo.state.rebase is None
    assert session.repo.state.branches["feature"].commit_sha == saved_tip
    assert session.repo.check_invariant() == []
