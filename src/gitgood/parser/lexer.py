"""Command tokenization and parsing."""

import shlex
from dataclasses import dataclass, field
from typing import Optional


class ParseError(Exception):
    """Error during command parsing."""
    pass


@dataclass
class ParsedCommand:
    """Result of parsing a user command."""
    command_type: str  # "git", "gh", "internal"
    command: str  # "checkout", "commit", "pr", etc.
    subcommand: Optional[str] = None  # For "gh pr create"
    args: list[str] = field(default_factory=list)
    flags: dict[str, Optional[str]] = field(default_factory=dict)
    raw_input: str = ""


INTERNAL_COMMANDS = {"help", "quit", "exit", "lesson", "lessons", "hint", "skip", "reset"}


class CommandLexer:
    """Tokenize and parse user input into structured commands."""

    def parse(self, user_input: str) -> ParsedCommand:
        """
        Parse a command string into a structured ParsedCommand.

        Examples:
            "git checkout -b feature" -> ParsedCommand(
                command_type="git",
                command="checkout",
                flags={"-b": "feature"}
            )

            "git commit -m 'Fix bug'" -> ParsedCommand(
                command_type="git",
                command="commit",
                flags={"-m": "Fix bug"}
            )
        """
        user_input = user_input.strip()
        if not user_input:
            raise ParseError("Empty command")

        try:
            tokens = shlex.split(user_input)
        except ValueError as e:
            raise ParseError(f"Invalid command syntax: {e}")

        if not tokens:
            raise ParseError("Empty command")

        cmd_type = tokens[0].lower()

        # Check for internal commands
        if cmd_type in INTERNAL_COMMANDS:
            return ParsedCommand(
                command_type="internal",
                command=cmd_type,
                args=tokens[1:],
                raw_input=user_input,
            )

        # Check for git or gh commands
        if cmd_type not in ("git", "gh"):
            raise ParseError(
                f"Unknown command: '{cmd_type}'. Commands should start with 'git' or 'gh'."
            )

        if len(tokens) < 2:
            raise ParseError(f"'{cmd_type}' requires a subcommand")

        return self._parse_git_or_gh(tokens, cmd_type, user_input)

    def _parse_git_or_gh(
        self, tokens: list[str], cmd_type: str, raw_input: str
    ) -> ParsedCommand:
        """Parse git or gh commands."""
        command = tokens[1]
        remaining = tokens[2:]

        # Check for sub-subcommand (gh pr create)
        subcommand = None
        if cmd_type == "gh" and command == "pr" and remaining:
            subcommand = remaining[0]
            remaining = remaining[1:]

        # Parse flags and arguments
        flags = {}
        args = []
        i = 0
        while i < len(remaining):
            token = remaining[i]
            if token.startswith("--"):
                # Long flag
                if "=" in token:
                    key, value = token.split("=", 1)
                    flags[key] = value
                elif i + 1 < len(remaining) and not remaining[i + 1].startswith("-"):
                    flags[token] = remaining[i + 1]
                    i += 1
                else:
                    flags[token] = None
            elif token.startswith("-") and len(token) > 1:
                # Short flag
                flag = token
                if i + 1 < len(remaining) and not remaining[i + 1].startswith("-"):
                    flags[flag] = remaining[i + 1]
                    i += 1
                else:
                    flags[flag] = None
            else:
                args.append(token)
            i += 1

        return ParsedCommand(
            command_type=cmd_type,
            command=command,
            subcommand=subcommand,
            args=args,
            flags=flags,
            raw_input=raw_input,
        )

    def normalize(self, user_input: str) -> str:
        """Normalize a command for comparison."""
        try:
            parsed = self.parse(user_input)
            parts = [parsed.command_type, parsed.command]
            if parsed.subcommand:
                parts.append(parsed.subcommand)

            # Sort flags for consistent comparison
            for flag in sorted(parsed.flags.keys()):
                parts.append(flag)
                if parsed.flags[flag]:
                    parts.append(parsed.flags[flag])

            parts.extend(parsed.args)
            return " ".join(parts)
        except ParseError:
            return user_input.lower().strip()
