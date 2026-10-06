"""Shared fixtures: a command-line style runner over the simulator."""

import pytest

from gitgood.core.github_api import SimulatedGitHub
from gitgood.core.models import CommandResult
from gitgood.core.repository import VirtualRepository
from gitgood.parser.executor import CommandExecutor
from gitgood.parser.lexer import CommandLexer


class GitSession:
    """Runs git/gh command strings against a fresh virtual repository."""

    def __init__(self):
        self.repo = VirtualRepository()
        self.github = SimulatedGitHub(self.repo)
        self.lexer = CommandLexer()
        self.executor = CommandExecutor(self.repo, self.github)

    def run(self, command: str) -> CommandResult:
        parsed = self.lexer.parse(command)
        result = self.executor.execute(parsed)
        assert self.repo.check_invariant() == [], (
            f"invariant broken after {command!r}: {self.repo.check_invariant()}"
        )
        return result

    def commit_file(self, filename: str, message: str) -> None:
        self.repo.add_working_change(filename)
        assert self.run(f"git add {filename}").success
        assert self.run(f'git commit -m "{message}"').success


@pytest.fixture
def session() -> GitSession:
    return GitSession()
