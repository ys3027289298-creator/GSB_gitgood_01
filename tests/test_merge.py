"""Merge behaviour and recovery after failed merges."""

from gitgood.core.models import PRStatus


def test_merge_creates_merge_commit(session):
    session.run("git checkout -b feature")
    session.commit_file("a.txt", "feature work")
    session.run("git checkout main")
    main_tip = session.repo.state.branches["main"].commit_sha

    result = session.run("git merge feature")

    assert result.success
    head = session.repo.get_current_commit()
    assert head.message == "Merge branch 'feature' into main"
    assert head.parent_sha == main_tip
    assert head.files_changed == ["a.txt"]


def test_merge_unknown_branch_fails_and_keeps_state(session):
    session.run("git checkout -b feature")
    session.commit_file("a.txt", "feature work")
    tip_before = session.repo.state.branches["feature"].commit_sha

    result = session.run("git merge ghost")

    assert not result.success
    assert "not something we can merge" in result.message
    assert session.repo.state.head == "feature"
    assert session.repo.state.branches["feature"].commit_sha == tip_before


def test_merge_branch_into_itself_is_up_to_date(session):
    result = session.run("git merge main")
    assert result.success
    assert "Already up to date" in (result.output or "")


def test_merge_already_merged_branch_is_up_to_date(session):
    session.run("git checkout -b feature")
    session.commit_file("a.txt", "feature work")
    session.run("git checkout main")
    assert session.run("git merge feature").success

    result = session.run("git merge feature")
    assert result.success
    assert "Already up to date" in (result.output or "")


def test_merge_no_ff_flag_does_not_swallow_branch_name(session):
    session.run("git checkout -b feature")
    session.commit_file("a.txt", "feature work")
    session.run("git checkout main")

    result = session.run("git merge --no-ff feature")

    assert result.success
    assert "Merge made" in (result.output or "")


def _open_pr(session) -> int:
    session.run("git checkout -b feature")
    session.commit_file("x.txt", "work")
    session.run("git push -u origin feature")
    result = session.run('gh pr create --title "T" --body "B"')
    assert result.success
    return 1


def test_pr_merge_success_marks_pr_merged(session):
    pr_number = _open_pr(session)

    result = session.run(f"gh pr merge {pr_number}")

    assert result.success
    assert session.repo.state.pull_requests[pr_number].status == PRStatus.MERGED
    assert session.repo.state.head == "main"


def test_pr_merge_with_deleted_target_rolls_back(session):
    pr_number = _open_pr(session)
    session.run("git branch -D main")
    feature_tip = session.repo.state.branches["feature"].commit_sha

    result = session.run(f"gh pr merge {pr_number}")

    assert not result.success
    # Rolled back: still on feature, feature untouched, PR still open.
    assert session.repo.state.head == "feature"
    assert session.repo.state.branches["feature"].commit_sha == feature_tip
    assert session.repo.state.pull_requests[pr_number].status == PRStatus.OPEN
    assert session.repo.check_invariant() == []


def test_pr_merge_with_deleted_source_fails_cleanly(session):
    pr_number = _open_pr(session)
    session.run("git checkout main")
    session.run("git branch -D feature")

    result = session.run(f"gh pr merge {pr_number}")

    assert not result.success
    assert session.repo.state.head == "main"
    assert session.repo.state.pull_requests[pr_number].status == PRStatus.OPEN
    assert session.repo.check_invariant() == []


def test_merge_blocked_during_rebase(session):
    session.run("git checkout -b feature")
    session.commit_file("shared.txt", "feature change")
    session.run("git checkout main")
    session.commit_file("shared.txt", "main change")
    session.run("git checkout feature")
    assert not session.run("git rebase main").success  # conflict

    result = session.run("git merge main")

    assert not result.success
    assert "rebase is in progress" in result.message
    # Recovery path still available afterwards.
    assert session.run("git rebase --abort").success
    assert session.repo.check_invariant() == []
