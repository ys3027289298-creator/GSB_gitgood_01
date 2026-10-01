"""Commit tree visualization."""

from rich.panel import Panel
from rich.text import Text
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.repository import VirtualRepository
    from ..core.models import Commit


class CommitTreeRenderer:
    """
    Renders a visualization of the commit graph.
    Similar to 'git log --oneline --graph'.
    """

    def __init__(self, repo: "VirtualRepository"):
        self.repo = repo

    def render(self, max_commits: int = 8) -> Panel:
        """
        Generate a visual representation of the commit tree.

        Example output:

        * a1b2c3d (HEAD -> feature) Add login form
        * e4f5g6h Implement authentication
        * h7i8j9k (main, origin/main) Initial commit
        """
        lines = []

        # Get commits starting from current branch
        current_sha = self.repo.state.branches[self.repo.state.head].commit_sha

        visited = 0
        sha = current_sha

        while sha and visited < max_commits:
            commit = self.repo.state.commits.get(sha)
            if not commit:
                break

            line = self._format_commit_line(commit)
            lines.append(line)

            sha = commit.parent_sha
            visited += 1

        if not lines:
            lines.append("[dim]No commits yet[/dim]")

        # Show branch pointers at bottom
        branch_info = self._get_branch_summary()
        if branch_info:
            lines.append("")
            lines.append(branch_info)

        return Panel(
            "\n".join(lines),
            title="[bold]Commit History[/bold]",
            border_style="yellow",
            padding=(0, 1),
        )

    def _format_commit_line(self, commit: "Commit") -> str:
        """Format a single commit line with decorations."""
        decorations = self._get_decorations(commit.sha)

        # Build the line
        parts = ["[dim]*[/dim]", f"[yellow]{commit.sha}[/yellow]"]

        if decorations:
            dec_str = ", ".join(decorations)
            parts.append(f"[orange1]({dec_str})[/orange1]")

        # Truncate message if too long
        message = commit.message
        if len(message) > 40:
            message = message[:37] + "..."

        parts.append(message)

        return " ".join(parts)

    def _get_decorations(self, sha: str) -> list[str]:
        """Get branch/HEAD decorations for a commit."""
        decorations = []

        # Check if HEAD points here
        current_branch = self.repo.state.head
        if self.repo.state.branches[current_branch].commit_sha == sha:
            decorations.append(f"[bold green]HEAD -> {current_branch}[/bold green]")

        # Check other local branches
        for name, branch in self.repo.state.branches.items():
            if branch.commit_sha == sha and name != current_branch:
                decorations.append(f"[green]{name}[/green]")

        # Check remote branches
        for name, branch in self.repo.state.remote_branches.items():
            if branch.commit_sha == sha:
                decorations.append(f"[red]{name}[/red]")

        return decorations

    def _get_branch_summary(self) -> str:
        """Get a summary of all branches."""
        branches = []

        for name in sorted(self.repo.state.branches.keys()):
            if name == self.repo.state.head:
                branches.append(f"[green bold]* {name}[/green bold]")
            else:
                branches.append(f"[dim]  {name}[/dim]")

        return "Branches: " + " ".join(
            f"[green]{name}[/green]" if name == self.repo.state.head else f"[dim]{name}[/dim]"
            for name in sorted(self.repo.state.branches.keys())
        )


class SimpleTreeView:
    """A simpler tree view for quick status checks."""

    def __init__(self, repo: "VirtualRepository"):
        self.repo = repo

    def render_oneline(self) -> str:
        """Render a single-line branch status."""
        current = self.repo.state.head
        branches = list(self.repo.state.branches.keys())

        parts = []
        for name in sorted(branches):
            if name == current:
                parts.append(f"[green bold]*{name}[/green bold]")
            else:
                parts.append(f"[dim]{name}[/dim]")

        return " ".join(parts)
