"""Status and information panels."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.repository import VirtualRepository
    from ..lessons.engine import Lesson


class StatusPanel:
    """Displays current repository status."""

    def __init__(self, repo: "VirtualRepository"):
        self.repo = repo

    def render(self) -> Panel:
        """Generate a status panel showing current repo state."""
        status = self.repo.status()

        lines = []

        # Current branch
        lines.append(f"On branch [orange1 bold]{status.current_branch}[/orange1 bold]")

        # Remote tracking info
        if status.upstream:
            if status.ahead > 0:
                lines.append(
                    f"Your branch is ahead of '[orange1]{status.upstream}[/orange1]' "
                    f"by {status.ahead} commit(s)"
                )
            elif status.behind > 0:
                lines.append(
                    f"Your branch is behind '[orange1]{status.upstream}[/orange1]' "
                    f"by {status.behind} commit(s)"
                )
            else:
                lines.append(
                    f"Your branch is up to date with '[orange1]{status.upstream}[/orange1]'"
                )

        # Staged changes
        if status.staged:
            lines.append("")
            lines.append("[green]Changes to be committed:[/green]")
            for change in status.staged:
                lines.append(f"  [green]{change.change_type}:[/green] {change.filename}")

        # Unstaged changes
        if status.unstaged:
            lines.append("")
            lines.append("[yellow]Changes not staged for commit:[/yellow]")
            for filename in status.unstaged:
                lines.append(f"  [yellow]modified:[/yellow] {filename}")

        # Clean state
        if not status.staged and not status.unstaged:
            lines.append("")
            lines.append("[dim]nothing to commit, working tree clean[/dim]")

        return Panel(
            "\n".join(lines),
            title="[bold #c15f3c]Repository Status[/bold #c15f3c]",
            border_style="#c15f3c",
            padding=(0, 1),
        )


class LessonProgressPanel:
    """Shows current lesson progress."""

    def render(self, lesson: "Lesson", step_index: int) -> Panel:
        """Generate lesson progress display."""
        total = len(lesson.steps)
        current = step_index + 1

        # Progress bar
        bar_width = 20
        filled = int((step_index / max(total, 1)) * bar_width)
        remaining = bar_width - filled

        bar = "[green]" + "█" * filled + "[/green]" + "[dim]░[/dim]" * remaining
        progress_text = f"{bar} {current}/{total}"

        lines = [
            f"[bold]{lesson.title}[/bold]",
            "",
            progress_text,
            "",
            "[bold]Objectives:[/bold]",
        ]

        for i, obj in enumerate(lesson.objectives):
            if i < step_index:
                lines.append(f"  [green]✓[/green] [dim]{obj}[/dim]")
            elif i == step_index:
                lines.append(f"  [yellow]→[/yellow] {obj}")
            else:
                lines.append(f"  [dim]○ {obj}[/dim]")

        return Panel(
            "\n".join(lines),
            title="[bold #c15f3c]Lesson Progress[/bold #c15f3c]",
            border_style="#c15f3c",
            padding=(0, 1),
        )


class LessonListPanel:
    """Shows all available lessons."""

    def render(self, lessons: list["Lesson"], completed: set[str]) -> Panel:
        """Generate lesson list display."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Status", width=3)
        table.add_column("Number", width=4)
        table.add_column("Title")

        for i, lesson in enumerate(lessons, 1):
            if lesson.lesson_id in completed:
                status = "[green]✓[/green]"
                style = "dim"
            else:
                status = "[dim]○[/dim]"
                style = ""

            table.add_row(
                status,
                f"[bold]{i}.[/bold]",
                f"[{style}]{lesson.title}[/{style}]" if style else lesson.title,
            )

        content = Text()
        content.append("Available Lessons\n\n", style="bold")

        return Panel(
            table,
            title="[bold #c15f3c]GitHub Flow Lessons[/bold #c15f3c]",
            border_style="#c15f3c",
            padding=(1, 2),
        )
