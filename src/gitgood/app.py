"""Main application orchestrator."""

import signal

from .core.repository import VirtualRepository
from .core.github_api import SimulatedGitHub
from .parser.lexer import CommandLexer, ParseError
from .parser.executor import CommandExecutor
from .lessons.engine import LessonEngine, StepType, Lesson
from .lessons.loader import load_lessons_from_directory, get_default_lessons_dir
from .ui.console import GitGoodConsole
from .ui.prompt import CommandPrompt
from .ui.panels import StatusPanel, LessonListPanel
from .ui.tree_view import CommitTreeRenderer


class GitGoodApp:
    """Main application orchestrator."""

    def __init__(self):
        self.console = GitGoodConsole()
        self.repo = VirtualRepository()
        self.github = SimulatedGitHub(self.repo)
        self.lexer = CommandLexer()
        self.executor = CommandExecutor(self.repo, self.github)
        self.lesson_engine = LessonEngine(self.repo)
        self.prompt = CommandPrompt()
        self.tree_renderer = CommitTreeRenderer(self.repo)
        self.running = True

        # Register resize handler
        signal.signal(signal.SIGWINCH, self._on_resize)

    def _on_resize(self, signum, frame) -> None:
        """Handle terminal resize by redrawing."""
        self.console.redraw()

    def run(self) -> None:
        """Main application loop."""
        self.console.print_welcome()

        # Load lessons
        lessons_dir = get_default_lessons_dir()
        count = load_lessons_from_directory(lessons_dir, self.lesson_engine)

        if count > 0:
            self.console.print_info(f"Loaded {count} lesson(s). Type 'lessons' to start learning!")
        else:
            self.console.print_warning(
                "No lessons found. You can still practice git commands freely."
            )

        self.console.print_divider()

        # Main REPL loop
        while self.running:
            try:
                self._run_iteration()
            except KeyboardInterrupt:
                self.console.console.print()
                continue
            except EOFError:
                break

        self.console.console.print("\nGoodbye! Happy coding!\n")

    def _run_iteration(self) -> None:
        """Run one iteration of the main loop."""
        # Show lesson instruction if active
        step = self.lesson_engine.get_current_step()
        if step:
            self.console.print_instruction(step.instruction)

            # For explanation steps, just wait for enter
            if step.step_type == StepType.EXPLANATION:
                self.prompt.get_simple_input("Press Enter to continue...")

                # Save current lesson before advancing (it gets cleared on completion)
                completed_lesson = self.lesson_engine.current_lesson

                self.lesson_engine.advance_step()

                # Check if lesson is complete
                if not self.lesson_engine.get_current_step():
                    self._handle_lesson_complete(completed_lesson)
                return

        # Get user input
        current_branch = self.repo.get_current_branch()
        user_input = self.prompt.get_input(current_branch)

        if not user_input:
            return

        # Track the input in output buffer
        self.console.add_input_line(f"$ ({current_branch}) {user_input}")

        # Handle internal commands
        if user_input.lower() in ("quit", "exit"):
            self.running = False
            return

        if user_input.lower() == "lessons":
            self.lesson_engine.end_lesson()
            self._show_lessons()
            return

        if user_input.lower().startswith("lesson "):
            parts = user_input.split(maxsplit=1)
            if len(parts) > 1:
                self._start_lesson(parts[1])
            return

        if user_input.lower() == "hint":
            hint = self.lesson_engine.get_hint()
            self.console.print_info(hint)
            return

        if user_input.lower() == "skip":
            if self.lesson_engine.is_lesson_active():
                # Save current lesson before advancing (it gets cleared on completion)
                completed_lesson = self.lesson_engine.current_lesson

                self.lesson_engine.advance_step()
                self.console.print_warning("Skipped current step.")
                if not self.lesson_engine.get_current_step():
                    self._handle_lesson_complete(completed_lesson)
            return

        if user_input.lower() == "status":
            self._show_status()
            return

        if user_input.lower() == "tree":
            self._show_tree()
            return

        # Validate against lesson if active
        if step and step.step_type == StepType.COMMAND:
            validation = self.lesson_engine.validate_command(user_input)

            if validation.success:
                # Execute the command in simulator
                self._execute_command(user_input)
                self.console.print_success(validation.message)

                # Save current lesson before advancing (it gets cleared on completion)
                completed_lesson = self.lesson_engine.current_lesson

                # Advance to next step
                self.lesson_engine.advance_step()

                # Check if lesson is complete
                if not self.lesson_engine.get_current_step():
                    self._handle_lesson_complete(completed_lesson)
            else:
                self.console.print_error(validation.message)
                self.console.print_hint(validation.hints)
        else:
            # Free-form mode - just execute
            self._execute_command(user_input)

    def _execute_command(self, user_input: str) -> None:
        """Parse and execute a command."""
        try:
            parsed = self.lexer.parse(user_input)
            result = self.executor.execute(parsed)

            if result.message == "__EXIT__":
                self.running = False
                return

            if result.output:
                self.console.print_command_output(result.output)

            if not result.success and result.message:
                self.console.print_error(result.message)
                if result.hints:
                    self.console.print_hint(result.hints)

        except ParseError as e:
            self.console.print_error(str(e))

    def _show_lessons(self) -> None:
        """Show the lesson list with full screen clear."""
        lessons = self.lesson_engine.get_all_lessons()

        if not lessons:
            self.console.print_warning("No lessons available.")
            return

        # Clear screen and show title banner
        self.console.clear_with_title()

        panel = LessonListPanel().render(lessons, self.lesson_engine.completed_lessons)
        self.console.console.print(panel)

        self.console.console.print("[white]⏺ Type 'lesson <number>' to start a lesson.[/white]")

    def _start_lesson(self, lesson_ref: str) -> None:
        """Start a lesson by number or ID."""
        lessons = self.lesson_engine.get_all_lessons()

        # Try by number first
        try:
            num = int(lesson_ref) - 1
            if 0 <= num < len(lessons):
                lesson = lessons[num]
                self._begin_lesson(lesson.lesson_id)
                return
        except ValueError:
            pass

        # Try by ID
        for lesson in lessons:
            if lesson.lesson_id == lesson_ref:
                self._begin_lesson(lesson.lesson_id)
                return

        self.console.print_error(f"Lesson not found: {lesson_ref}")

    def _begin_lesson(self, lesson_id: str) -> None:
        """Begin a specific lesson."""
        # Reset repo state for fresh start
        self.repo = VirtualRepository()
        self.github = SimulatedGitHub(self.repo)
        self.executor = CommandExecutor(self.repo, self.github)
        self.lesson_engine.repo = self.repo
        self.tree_renderer = CommitTreeRenderer(self.repo)

        # Clear output buffer for fresh lesson
        self.console.clear_output_buffer()

        step = self.lesson_engine.start_lesson(lesson_id)

        if not step:
            lesson = self.lesson_engine.get_lesson(lesson_id)
            if lesson and lesson.required_lessons:
                self.console.print_error(
                    f"Complete prerequisite lessons first: {', '.join(lesson.required_lessons)}"
                )
            else:
                self.console.print_error("Failed to start lesson.")
            return

    def _handle_lesson_complete(self, lesson: Lesson | None) -> None:
        """Handle lesson completion."""
        if lesson:
            self.console.print_lesson_complete(lesson.title)

        # Check if all lessons are complete
        if len(self.lesson_engine.completed_lessons) == len(self.lesson_engine.lessons):
            self.console.print_all_complete()

    def _show_status(self) -> None:
        """Show repository status panel."""
        panel = StatusPanel(self.repo).render()
        self.console.print_panel(panel)

    def _show_tree(self) -> None:
        """Show commit tree."""
        panel = self.tree_renderer.render()
        self.console.print_panel(panel)


def main() -> None:
    """Entry point."""
    app = GitGoodApp()
    app.run()
