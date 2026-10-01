"""Region-based screen management for persistent header layout."""

from dataclasses import dataclass
from rich.console import Console


# ANSI escape sequences for cursor control
ANSI_CLEAR_TO_END = "\033[J"


@dataclass
class LayoutConfig:
    """Fixed layout dimensions."""

    title_height: int = 11  # ASCII art (7 lines) + tagline + blank + separator
    instruction_height: int = 19  # Minimum panel height (can expand for longer content)
    separator_height: int = 1  # Grey horizontal lines
    comments_height: int = 10  # Comments panel height (title + border + 6 comments)


class RegionManager:
    """Manages fixed screen regions with cursor positioning."""

    def __init__(self, console: Console, config: LayoutConfig | None = None):
        self.console = console
        self.config = config or LayoutConfig()
        self._title_rendered: bool = False

    @property
    def content_start_row(self) -> int:
        """Row where output content begins (fixed position)."""
        return (
            self.config.title_height
            + self.config.separator_height
            + self.config.instruction_height
            + self.config.comments_height
            + self.config.separator_height
        )

    def clear_from_row(self, row: int) -> None:
        """Clear screen from specified row to bottom."""
        # Move cursor to row, column 0 (ANSI uses 1-based indexing)
        self.console.file.write(f"\033[{row + 1};1H")
        # Clear from cursor to end of screen
        self.console.file.write(ANSI_CLEAR_TO_END)
        self.console.file.flush()

    def move_to_row(self, row: int) -> None:
        """Move cursor to specified row."""
        self.console.file.write(f"\033[{row + 1};1H")
        self.console.file.flush()

    def move_home(self) -> None:
        """Move cursor to top-left corner."""
        self.console.file.write("\033[H")
        self.console.file.flush()
