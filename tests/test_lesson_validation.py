"""Lesson validation must be order-sensitive, and the app must not
advance (or show a success message) when execution fails."""

from gitgood.app import GitGoodApp
from gitgood.core.repository import VirtualRepository
from gitgood.lessons.engine import Lesson, LessonEngine, LessonStep, StepType


def make_engine(expected):
    repo = VirtualRepository()
    engine = LessonEngine(repo)
    engine.add_lesson(
        Lesson(
            lesson_id="t",
            title="t",
            description="",
            objectives=[],
            steps=[
                LessonStep(
                    step_id="s1",
                    step_type=StepType.COMMAND,
                    instruction="i",
                    expected_commands=expected,
                )
            ],
        )
    )
    engine.start_lesson("t")
    return engine


class TestOrderSensitiveMatching:
    def test_reversed_tokens_rejected(self):
        engine = make_engine(["git add login.html"])
        assert not engine.validate_command("git login.html add").success

    def test_reversed_flag_and_branch_rejected(self):
        engine = make_engine(["git checkout -b add-login"])
        assert not engine.validate_command("git checkout add-login -b").success
        assert not engine.validate_command("git add-login checkout -b").success

    def test_exact_command_accepted(self):
        engine = make_engine(["git add login.html"])
        assert engine.validate_command("git add login.html").success

    def test_quote_styles_normalized(self):
        engine = make_engine(['git commit -m "Add login form"'])
        assert engine.validate_command("git commit -m 'Add login form'").success

    def test_wrong_message_rejected(self):
        engine = make_engine(['git commit -m "Add login form"'])
        assert not engine.validate_command('git commit -m "wrong"').success

    def test_missing_flag_value_rejected(self):
        engine = make_engine(["git checkout -b add-login"])
        assert not engine.validate_command("git checkout -b").success


class FailingCommandApp:
    """Builds a GitGoodApp wired to scripted input for lesson-flow tests."""

    def __init__(self, inputs):
        self.app = GitGoodApp()
        self.inputs = iter(inputs)
        self.app.prompt.get_input = lambda branch="main": next(self.inputs, "quit")
        self.app.prompt.get_simple_input = lambda prompt="": ""

    def add_lesson(self, expected_commands):
        engine = self.app.lesson_engine
        engine.add_lesson(
            Lesson(
                lesson_id="t",
                title="t",
                description="",
                objectives=[],
                steps=[
                    LessonStep(
                        step_id="s1",
                        step_type=StepType.COMMAND,
                        instruction="i",
                        expected_commands=expected_commands,
                    )
                ],
            )
        )
        engine.start_lesson("t")


class TestAppDoesNotAdvanceOnFailure:
    def test_failed_execution_does_not_advance(self):
        """'git checkout -b dup' validates but fails (branch exists):
        the step must not advance and no success is shown."""
        harness = FailingCommandApp(["git checkout -b dup", "quit"])
        app = harness.app
        app.repo.create_branch("dup")  # make the expected command fail
        harness.add_lesson(["git checkout -b dup"])

        app._run_iteration()

        assert app.lesson_engine.current_lesson is not None
        assert app.lesson_engine.current_step_index == 0

    def test_successful_execution_advances(self):
        harness = FailingCommandApp(["git checkout -b ok-branch", "quit"])
        app = harness.app
        harness.add_lesson(["git checkout -b ok-branch"])

        app._run_iteration()

        # Lesson had a single step; completing it ends the lesson
        assert app.lesson_engine.current_lesson is None
        assert "ok-branch" in app.repo.state.branches

    def test_reversed_command_rejected_at_app_level(self):
        harness = FailingCommandApp(["git login.html add", "quit"])
        app = harness.app
        harness.add_lesson(["git add login.html"])

        app._run_iteration()

        assert app.lesson_engine.current_step_index == 0
        assert app.repo.state.staged_changes == []
