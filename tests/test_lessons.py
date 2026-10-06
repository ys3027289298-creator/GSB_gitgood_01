"""Lesson validation: order-sensitive matching and full play-throughs."""

import pytest

from gitgood.core.github_api import SimulatedGitHub
from gitgood.core.repository import VirtualRepository
from gitgood.lessons.engine import Lesson, LessonEngine, LessonStep, StepType
from gitgood.lessons.loader import get_default_lessons_dir, load_lessons_from_directory
from gitgood.parser.executor import CommandExecutor
from gitgood.parser.lexer import CommandLexer


def _engine_with_checkout_step() -> LessonEngine:
    engine = LessonEngine(VirtualRepository())
    engine.add_lesson(
        Lesson(
            lesson_id="t",
            title="t",
            description="",
            objectives=[],
            steps=[
                LessonStep(
                    step_id="s",
                    step_type=StepType.COMMAND,
                    instruction="",
                    expected_commands=["git checkout -b add-login"],
                )
            ],
        )
    )
    engine.start_lesson("t")
    return engine


@pytest.mark.parametrize(
    "command",
    ["git checkout -b add-login", "git checkout add-login -b"],
)
def test_correct_command_and_flag_reorder_accepted(command):
    engine = _engine_with_checkout_step()
    assert engine.validate_command(command).success


@pytest.mark.parametrize(
    "command",
    [
        "git add-login checkout -b",  # positional order reversed
        "git -b add-login checkout",
        "git checkout -b other-name",
    ],
)
def test_reversed_command_order_rejected(command):
    engine = _engine_with_checkout_step()
    assert not engine.validate_command(command).success


def test_commit_step_rejects_stage_commit_swap():
    engine = LessonEngine(VirtualRepository())
    engine.add_lesson(
        Lesson(
            lesson_id="t",
            title="t",
            description="",
            objectives=[],
            steps=[
                LessonStep(
                    step_id="s",
                    step_type=StepType.COMMAND,
                    instruction="",
                    expected_commands=['git commit -m "Add login form"'],
                )
            ],
        )
    )
    engine.start_lesson("t")

    # Tokens present but in the wrong positional order must not pass.
    assert not engine.validate_command('git "Add login form" commit -m').success
    assert engine.validate_command('git commit -m "Add login form"').success
    # Flag-after-argument is still acceptable (same positional order).
    assert engine.validate_command('git commit "Add login form" -m').success


def test_all_lessons_play_through_and_keep_state_consistent():
    lexer = CommandLexer()
    engine = LessonEngine(VirtualRepository())
    count = load_lessons_from_directory(get_default_lessons_dir(), engine)
    assert count == 6
    engine.completed_lessons.update(engine.lesson_order)

    for lesson in engine.get_all_lessons():
        repo = VirtualRepository()
        executor = CommandExecutor(repo, SimulatedGitHub(repo))
        engine.repo = repo
        engine.start_lesson(lesson.lesson_id)

        step = engine.get_current_step()
        while step:
            if step.step_type == StepType.COMMAND:
                command = step.expected_commands[0]
                validation = engine.validate_command(command)
                assert validation.success, (
                    f"{lesson.lesson_id}/{step.step_id}: expected {command!r}"
                )
                result = executor.execute(lexer.parse(command))
                assert result.success, (
                    f"{lesson.lesson_id}/{step.step_id}: {command!r} failed: "
                    f"{result.message}"
                )
            engine.advance_step()
            step = engine.get_current_step()

        assert repo.check_invariant() == [], lesson.lesson_id
