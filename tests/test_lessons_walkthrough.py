"""All six shipped lessons must remain completable end-to-end after the
state-machine fixes (course copy and keyboard flow untouched)."""

from gitgood.core.github_api import SimulatedGitHub
from gitgood.core.repository import VirtualRepository
from gitgood.lessons.engine import LessonEngine, StepType
from gitgood.lessons.loader import get_default_lessons_dir, load_lessons_from_directory
from gitgood.parser.executor import CommandExecutor
from gitgood.parser.lexer import CommandLexer

ALL_LESSON_IDS = [
    "01_branching",
    "02_commits",
    "03_pushing",
    "04_pull_requests",
    "05_code_review",
    "06_merging",
]


def _walk_lesson(lesson_id):
    repo = VirtualRepository()
    github = SimulatedGitHub(repo)
    executor = CommandExecutor(repo, github)
    lexer = CommandLexer()
    engine = LessonEngine(repo)
    load_lessons_from_directory(get_default_lessons_dir(), engine)

    step = engine.start_lesson(lesson_id)
    assert step is not None, lesson_id

    while step:
        if step.step_type in (StepType.EXPLANATION, StepType.FREE_PRACTICE):
            step = engine.advance_step()
            continue

        command = step.expected_commands[0]
        validation = engine.validate_command(command)
        assert validation.success, f"{lesson_id}/{step.step_id}: {command} rejected"

        parsed = lexer.parse(command)
        result = executor.execute(parsed)
        assert result.success, (
            f"{lesson_id}/{step.step_id}: {command} failed: {result.message}"
        )
        assert repo.check_invariants() == []

        step = engine.advance_step()

    assert lesson_id in engine.completed_lessons
    return repo


def test_all_lessons_completable():
    for lesson_id in ALL_LESSON_IDS:
        _walk_lesson(lesson_id)


def test_lesson_six_merge_lands_on_main():
    repo = _walk_lesson("06_merging")
    main_tip = repo.state.commits[repo.state.branches["main"].commit_sha]
    # GitHub merge commit (never a fast-forward) carrying the login commit
    assert main_tip.message.startswith("Merge branch 'add-login'")
    assert main_tip.merge_parent_sha is not None
    assert "add-login" not in repo.state.branches
