"""Lesson engine for managing tutorial progression."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.repository import VirtualRepository


class StepType(Enum):
    """Type of lesson step."""
    EXPLANATION = "explanation"  # Show info, press enter to continue
    COMMAND = "command"  # User must type a specific command
    FREE_PRACTICE = "free_practice"  # User can experiment freely


@dataclass
class LessonStep:
    """A single step in a lesson."""
    step_id: str
    step_type: StepType
    instruction: str

    # For COMMAND type
    expected_commands: list[str] = field(default_factory=list)
    command_pattern: Optional[str] = None  # Regex pattern

    # Feedback
    success_message: str = "Correct!"
    failure_hints: list[str] = field(default_factory=list)

    # Setup for this step (simulated file changes, etc.)
    setup_changes: list[str] = field(default_factory=list)


@dataclass
class Lesson:
    """A complete lesson on a GitHub flow topic."""
    lesson_id: str
    title: str
    description: str
    objectives: list[str]
    steps: list[LessonStep] = field(default_factory=list)

    # Prerequisites
    required_lessons: list[str] = field(default_factory=list)

    # Initial repo state
    initial_state: Optional[dict] = None


@dataclass
class ValidationResult:
    """Result of validating a user command."""
    success: bool
    message: str = ""
    hints: list[str] = field(default_factory=list)
    advance: bool = False


class LessonEngine:
    """Manages lesson progression and user guidance."""

    def __init__(self, repo: "VirtualRepository"):
        self.repo = repo
        self.lessons: dict[str, Lesson] = {}
        self.lesson_order: list[str] = []
        self.current_lesson: Optional[Lesson] = None
        self.current_step_index: int = 0
        self.completed_lessons: set[str] = set()
        self.attempt_count: int = 0

    def add_lesson(self, lesson: Lesson) -> None:
        """Add a lesson to the engine."""
        self.lessons[lesson.lesson_id] = lesson
        self.lesson_order.append(lesson.lesson_id)

    def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
        """Get a lesson by ID."""
        return self.lessons.get(lesson_id)

    def get_all_lessons(self) -> list[Lesson]:
        """Get all lessons in order."""
        return [self.lessons[lid] for lid in self.lesson_order]

    def start_lesson(self, lesson_id: str) -> Optional[LessonStep]:
        """Begin a lesson, setting up initial state."""
        lesson = self.lessons.get(lesson_id)
        if not lesson:
            return None

        self.current_lesson = lesson
        self.current_step_index = 0
        self.attempt_count = 0

        # Set up initial repo state if specified
        if lesson.initial_state:
            self.repo.import_state(lesson.initial_state)

        # Apply setup for first step
        step = self.get_current_step()
        if step and step.setup_changes:
            self._apply_step_setup(step)

        return step

    def get_current_step(self) -> Optional[LessonStep]:
        """Get the current step in the lesson."""
        if not self.current_lesson:
            return None
        if self.current_step_index >= len(self.current_lesson.steps):
            return None
        return self.current_lesson.steps[self.current_step_index]

    def validate_command(self, user_input: str) -> ValidationResult:
        """
        Check if the user's command is correct for the current step.
        """
        step = self.get_current_step()
        if not step:
            return ValidationResult(success=False, message="No active lesson step")

        self.attempt_count += 1

        # Explanation steps advance on any input (enter)
        if step.step_type == StepType.EXPLANATION:
            return ValidationResult(
                success=True,
                message="",
                advance=True,
            )

        # Free practice doesn't validate
        if step.step_type == StepType.FREE_PRACTICE:
            return ValidationResult(success=True, message="", advance=False)

        # Command validation
        if step.step_type == StepType.COMMAND:
            normalized_input = self._normalize_command(user_input)

            # Check against expected commands
            for expected in step.expected_commands:
                normalized_expected = self._normalize_command(expected)
                if self._commands_match(normalized_input, normalized_expected):
                    return ValidationResult(
                        success=True,
                        message=step.success_message,
                        advance=True,
                    )

            # Check pattern if specified
            if step.command_pattern:
                if re.match(step.command_pattern, user_input, re.IGNORECASE):
                    return ValidationResult(
                        success=True,
                        message=step.success_message,
                        advance=True,
                    )

            # Generate feedback
            return self._generate_feedback(user_input, step)

        return ValidationResult(success=False, message="Unknown step type")

    def advance_step(self) -> Optional[LessonStep]:
        """Move to the next step in the lesson."""
        if not self.current_lesson:
            return None

        self.current_step_index += 1
        self.attempt_count = 0

        if self.current_step_index >= len(self.current_lesson.steps):
            self._complete_lesson()
            return None

        step = self.get_current_step()

        # Apply setup for this step
        if step and step.setup_changes:
            self._apply_step_setup(step)

        return step

    def get_next_lesson(self) -> Optional[Lesson]:
        """Get the next uncompleted lesson."""
        for lesson_id in self.lesson_order:
            if lesson_id not in self.completed_lessons:
                return self.lessons[lesson_id]
        return None

    def is_lesson_active(self) -> bool:
        """Check if a lesson is currently active."""
        return self.current_lesson is not None

    def end_lesson(self) -> None:
        """End the current lesson without marking it complete."""
        self.current_lesson = None
        self.current_step_index = 0
        self.attempt_count = 0

    def get_hint(self) -> str:
        """Get a hint for the current step."""
        step = self.get_current_step()
        if not step:
            return "No active lesson step."

        if step.step_type == StepType.EXPLANATION:
            return "Press Enter to continue."

        if step.failure_hints:
            # Return progressively more hints based on attempts
            hint_index = min(self.attempt_count - 1, len(step.failure_hints) - 1)
            return step.failure_hints[hint_index]

        if step.expected_commands:
            # Give a partial hint
            cmd = step.expected_commands[0]
            words = cmd.split()
            if len(words) > 2:
                return f"The command starts with: {words[0]} {words[1]} ..."
            return f"The command starts with: {words[0]} ..."

        return "Keep trying!"

    def skip_step(self) -> Optional[LessonStep]:
        """Skip the current step (for debugging/stuck users)."""
        return self.advance_step()

    def _complete_lesson(self) -> None:
        """Mark current lesson as complete."""
        if self.current_lesson:
            self.completed_lessons.add(self.current_lesson.lesson_id)
            self.current_lesson = None
            self.current_step_index = 0

    def _normalize_command(self, cmd: str) -> str:
        """Normalize a command for comparison."""
        # Remove extra whitespace
        cmd = " ".join(cmd.split())
        # Lowercase
        cmd = cmd.lower()
        return cmd

    def _commands_match(self, input_cmd: str, expected_cmd: str) -> bool:
        """Check if two commands match (with some flexibility)."""
        # Exact match
        if input_cmd == expected_cmd:
            return True

        # Handle quote variations
        input_cmd = input_cmd.replace("'", '"')
        expected_cmd = expected_cmd.replace("'", '"')

        if input_cmd == expected_cmd:
            return True

        # Handle flag order variations for git commands
        if input_cmd.startswith("git ") and expected_cmd.startswith("git "):
            input_parts = set(input_cmd.split())
            expected_parts = set(expected_cmd.split())
            if input_parts == expected_parts:
                return True

        return False

    def _generate_feedback(self, user_input: str, step: LessonStep) -> ValidationResult:
        """Generate helpful feedback when user command is incorrect."""
        hints = []

        # Check for common mistakes
        if not user_input:
            hints.append("Please type a command.")
        elif not user_input.startswith("git") and not user_input.startswith("gh"):
            hints.append("Git commands start with 'git' or 'gh'.")
        else:
            # Add step-specific hints
            hints.extend(step.failure_hints[:2])

        # After several attempts, give bigger hints
        if self.attempt_count >= 3:
            hints.append("Type 'hint' for more help.")

        if self.attempt_count >= 5 and step.expected_commands:
            # Reveal the command after many attempts
            hints.append(f"Try: {step.expected_commands[0]}")

        return ValidationResult(
            success=False,
            message="That's not quite right.",
            hints=hints,
            advance=False,
        )

    def _apply_step_setup(self, step: LessonStep) -> None:
        """Apply setup changes for a step (e.g., simulate file changes)."""
        for filename in step.setup_changes:
            self.repo.add_working_change(filename)
