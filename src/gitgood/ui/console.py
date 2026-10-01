"""Rich console wrapper with app-specific styling."""

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum

from rich.console import Console
from rich.theme import Theme
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

from .regions import RegionManager


# Custom theme for the application (Claude Code inspired: orange/terracotta)
GITGOOD_THEME = Theme({
    "info": "orange1",
    "success": "green bold",
    "success_faded": "dim green",
    "warning": "yellow",
    "error": "red bold",
    "error_faded": "dim red",
    "command": "bright_white on grey23",
    "branch": "orange1 bold",
    "commit": "yellow",
    "instruction": "orange1",
    "hint": "dim orange1 italic",
    "hint_faded": "dim grey50 italic",
    "prompt": "green bold",
    "header": "bold orange1",
})


WELCOME_ART = """
   _____ _ _    _____                 _
  / ____(_) |  / ____|               | |
 | |  __ _| |_| |  __  ___   ___   __| |
 | | |_ | | __| | |_ |/ _ \\ / _ \\ / _` |
 | |__| | | |_| |__| | (_) | (_) | (_| |
  \\_____|_|\\__|\\_____|\\___/ \\___/ \\__,_|
"""

# Minimum height for instruction panel (can expand for longer content)
MIN_INSTRUCTION_PANEL_HEIGHT = 13

# Fixed height for comments panel
COMMENTS_PANEL_HEIGHT = 10
MAX_COMMENTS = 3  # Maximum number of comments to display


class CommentType(Enum):
    """Type of comment message."""

    SUCCESS = "success"
    ERROR = "error"
    HINT = "hint"


@dataclass
class Comment:
    """A single comment in the comments panel."""

    comment_type: CommentType
    text: str

    def render(self) -> str:
        """Render the comment with appropriate styling."""
        if self.comment_type == CommentType.SUCCESS:
            return f"[success]✓ {self.text}[/success]"
        elif self.comment_type == CommentType.ERROR:
            return f"[error]✗ {self.text}[/error]"
        elif self.comment_type == CommentType.HINT:
            return f"[hint]  → {self.text}[/hint]"
        return self.text


class GitGoodConsole:
    """Wrapper around Rich console with app-specific methods."""

    def __init__(self):
        self.console = Console(theme=GITGOOD_THEME)
        self._output_buffer: list = []  # Accumulated output history
        self._current_instruction: str | None = None  # Current instruction text
        self._region_manager = RegionManager(self.console)
        self._comments_buffer: deque[Comment] = deque(maxlen=MAX_COMMENTS)

    def _is_buffered_mode(self) -> bool:
        """Check if we're in buffered mode (instruction is active)."""
        return self._current_instruction is not None

    def _clear_screen(self) -> None:
        """Clear screen including scrollback buffer."""
        self.console.file.write("\033[2J")  # Clear screen
        self.console.file.write("\033[3J")  # Clear scrollback buffer
        self.console.file.write("\033[H")   # Move cursor to home
        self.console.file.flush()

    def _render_title(self) -> None:
        """Render title region at top of screen."""
        self._region_manager.move_home()
        art = Text(WELCOME_ART)
        art.stylize("#c15f3c")
        self.console.print(art, justify="center")
        self.console.print("[bold #ffffff]Learn GitHub Flow interactively![/bold #ffffff]", justify="center")
        self.console.print()
        self.console.rule(style="grey50")
        self._region_manager._title_rendered = True

    def _render_comment(self, comment: Comment, is_newest: bool) -> str:
        """Render a comment with appropriate styling based on age."""
        if comment.comment_type == CommentType.SUCCESS:
            style = "success" if is_newest else "success_faded"
            return f"[{style}]✓ {comment.text}[/{style}]"
        elif comment.comment_type == CommentType.ERROR:
            style = "error" if is_newest else "error_faded"
            return f"[{style}]✗ {comment.text}[/{style}]"
        elif comment.comment_type == CommentType.HINT:
            style = "hint" if is_newest else "hint_faded"
            return f"[{style}]  → {comment.text}[/{style}]"
        return comment.text

    def _render_comments_panel(self) -> None:
        """Render the comments panel with current comments."""
        if self._comments_buffer:
            lines = []
            num_comments = len(self._comments_buffer)
            for i, comment in enumerate(self._comments_buffer):
                is_newest = (i == num_comments - 1)
                lines.append(self._render_comment(comment, is_newest))
            content = "\n".join(lines)
        else:
            content = "[dim]No feedback yet.[/dim]"

        panel = Panel(
            content,
            title="[bold #c15f3c]Comments[/bold #c15f3c]",
            border_style="#c15f3c",
            padding=(0, 2),
            height=COMMENTS_PANEL_HEIGHT,
        )
        self.console.print(panel)
        self.console.rule(style="grey50")

    def _redraw(self) -> None:
        """Clear screen and redraw everything: title + instruction + comments + output history."""
        # Clear entire screen including scrollback buffer and re-render from scratch
        self._clear_screen()
        self._region_manager._title_rendered = False
        self._render_title()

        # 1. Print instruction panel with minimum height (expands for longer content)
        if self._current_instruction:
            content = Markdown(self._current_instruction)
            # Calculate content height accounting for line wrapping in narrow windows
            # Panel overhead: 2 for borders + 2 for padding (1 top, 1 bottom)
            panel_overhead = 4
            # Available width: terminal width - borders (2) - horizontal padding (4)
            available_width = max(self.console.width - 6, 10)  # min 10 to avoid division issues

            # Count wrapped lines for each line of content
            content_lines = 0
            for line in self._current_instruction.split('\n'):
                if len(line) == 0:
                    content_lines += 1
                else:
                    content_lines += math.ceil(len(line) / available_width)

            needed_height = content_lines + panel_overhead
            panel_height = max(MIN_INSTRUCTION_PANEL_HEIGHT, needed_height)

            panel = Panel(
                content,
                title="[bold #c15f3c]Instruction[/bold #c15f3c]",
                border_style="#c15f3c",
                padding=(1, 2),
                height=panel_height,
            )
            self.console.print(panel)

            # 2. Print comments panel with FIXED HEIGHT
            self._render_comments_panel()

        # 3. Print accumulated output (always starts at same row due to fixed panel heights)
        for line in self._output_buffer:
            self.console.print(line)

    def redraw(self) -> None:
        """Public method to trigger a redraw (e.g., on terminal resize)."""
        # On resize, re-render everything with new terminal dimensions
        self.console.clear()
        self._region_manager._title_rendered = False
        self._render_title()
        if self._is_buffered_mode():
            self._redraw()

    def print_welcome(self) -> None:
        """Display welcome message and ASCII art."""
        self._clear_screen()
        self._render_title()
        self.console.print(
            "Type [command]help[/command] to see available commands, "
            "or [command]lessons[/command] to start learning.",
            style="dim",
        )
        self.console.print()

    def print_instruction(self, text: str) -> None:
        """Set current instruction and redraw."""
        self._current_instruction = text
        self._redraw()

    def clear_instruction(self) -> None:
        """Clear the current instruction."""
        self._current_instruction = None

    def add_input_line(self, line: str) -> None:
        """Add a user input line to the output buffer."""
        if self._is_buffered_mode():
            self._output_buffer.append(f"[bright_white]{line}[/bright_white]")
            # Don't redraw here - will redraw after command output

    def print_success(self, text: str) -> None:
        """Print a success message."""
        if self._is_buffered_mode():
            self._comments_buffer.append(Comment(CommentType.SUCCESS, text))
            self._redraw()
        else:
            self.console.print()
            self.console.print(f"[success]✓ {text}[/success]")

    def print_error(self, text: str) -> None:
        """Print an error message."""
        if self._is_buffered_mode():
            self._comments_buffer.append(Comment(CommentType.ERROR, text))
            self._redraw()
        else:
            self.console.print(f"[error]✗ {text}[/error]")

    def print_warning(self, text: str) -> None:
        """Print a warning message."""
        if self._is_buffered_mode():
            self._output_buffer.append(f"[warning]⚠ {text}[/warning]")
            self._redraw()
        else:
            self.console.print(f"[warning]⚠ {text}[/warning]")

    def print_hint(self, hints: list[str]) -> None:
        """Print helpful hints."""
        if not hints:
            return
        if self._is_buffered_mode():
            for hint in hints:
                self._comments_buffer.append(Comment(CommentType.HINT, hint))
            self._redraw()
        else:
            self.console.print()
            for hint in hints:
                self.console.print(f"[hint]  → {hint}[/hint]")

    def print_command_output(self, output: str) -> None:
        """Print simulated git command output."""
        if not output:
            return
        if self._is_buffered_mode():
            self._output_buffer.append("")  # Blank line
            self._output_buffer.append(output)
            self._redraw()
        else:
            self.console.print()
            self.console.print(output)

    def print_info(self, text: str) -> None:
        """Print informational text."""
        if self._is_buffered_mode():
            self._output_buffer.append(f"[white]⏺ {text}[/white]")
            self._redraw()
        else:
            self.console.print(f"[white]⏺ {text}[/white]")

    def print_divider(self) -> None:
        """Print a visual divider in the output."""
        if self._is_buffered_mode():
            self._output_buffer.append("")
            self._output_buffer.append("[dim]" + "─" * 40 + "[/dim]")
            self._output_buffer.append("")
            self._redraw()
        else:
            self.console.print()
            self.console.rule(style="dim")
            self.console.print()

    def print_panel(self, panel) -> None:
        """Print a panel to output buffer."""
        if self._is_buffered_mode():
            self._output_buffer.append(panel)
            self._redraw()
        else:
            self.console.print(panel)

    def print_lesson_complete(self, title: str) -> None:
        """Print lesson completion message."""
        panel = Panel(
            f"[success]🎉 Congratulations![/success]\n\n"
            f"You've completed: [bold]{title}[/bold]\n\n"
            f"Type [command]lessons[/command] to continue to the next lesson.",
            border_style="green",
            padding=(1, 2),
        )
        if self._is_buffered_mode():
            self._output_buffer.append("")
            self._output_buffer.append(panel)
            self._redraw()
        else:
            self.console.print()
            self.console.print(panel)

    def print_all_complete(self) -> None:
        """Print message when all lessons are complete."""
        panel = Panel(
            "[success]🎉 Amazing work![/success]\n\n"
            "You've completed all GitHub Flow lessons!\n\n"
            "You now know how to:\n"
            "• Create feature branches\n"
            "• Make commits with good messages\n"
            "• Push branches to remote\n"
            "• Create and manage pull requests\n"
            "• Handle code reviews\n"
            "• Merge and clean up branches\n\n"
            "Go forth and collaborate!",
            title="[bold]Course Complete[/bold]",
            border_style="green",
            padding=(1, 2),
        )
        if self._is_buffered_mode():
            self._output_buffer.append("")
            self._output_buffer.append(panel)
            self._redraw()
        else:
            self.console.print()
            self.console.print(panel)

    def clear_output_buffer(self) -> None:
        """Clear the output buffer (e.g., when starting a new lesson)."""
        self._output_buffer.clear()
        self._comments_buffer.clear()

    def clear_with_title(self) -> None:
        """Clear screen, exit buffered mode, and render the title banner."""
        # Exit buffered mode if active
        self._current_instruction = None
        self._output_buffer.clear()
        self._comments_buffer.clear()

        self._clear_screen()
        self._region_manager._title_rendered = False
        self._render_title()
