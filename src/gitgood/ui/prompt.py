"""Interactive command prompt."""

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML


# Prompt style (Claude Code inspired: orange/terracotta)
PROMPT_STYLE = Style.from_dict({
    "prompt": "ansiwhite bold",
    "branch": "ansiwhite",
})


class CommandPrompt:
    """Interactive command prompt with history and suggestions."""

    def __init__(self):
        self.history = InMemoryHistory()
        self.session = PromptSession(
            history=self.history,
            auto_suggest=AutoSuggestFromHistory(),
            style=PROMPT_STYLE,
        )

    def get_input(self, current_branch: str = "main") -> str:
        """Get user input with a git-style prompt."""
        prompt_text = HTML(
            f'<prompt>$</prompt> <branch>({current_branch})</branch> '
        )

        try:
            return self.session.prompt(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

    def get_simple_input(self, prompt: str = "$ ") -> str:
        """Get simple user input."""
        try:
            return self.session.prompt(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return ""
